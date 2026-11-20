"""The programs Caztor runs on, fetched once when the machine lacks them.

Caztor needs ``node`` (Node.js 26 or newer) to run and ``tectonic`` to compile.
A papersmith install does not carry them (they differ per platform and would
make the package six times larger), so the first time the PDF tab opens on a
machine without them, they are downloaded from their official releases, at the
versions pinned below, checked against the SHA-256 pinned beside each, and kept
under ``~/.cache/papersmith/tools/``. A program already on the ``PATH`` is used
as it is (``node`` only when it is version 26 or newer). Only the executable is
taken from each archive.

``PAPERSMITH_NO_TOOL_DOWNLOAD=1`` turns the download off; the PDF tab then says
which program to install.

Stdlib only.
"""

from __future__ import annotations

import hashlib
import http.client
import io
import os
import platform
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping

NO_DOWNLOAD_ENV = "PAPERSMITH_NO_TOOL_DOWNLOAD"
NODE_MIN_MAJOR = 26
#: An archive larger than this is refused before it is read: the pinned ones are under 40 MB.
MAX_ARCHIVE_BYTES = 120 * 1024 * 1024
DOWNLOAD_TIMEOUT = 300


@dataclass(frozen=True)
class Release:
    """One pinned archive: where it is, its SHA-256, and the executable inside it."""

    url: str
    sha256: str
    member: str


NODE_VERSION = "26.13.1"
TECTONIC_VERSION = "0.17.0"
_NODE = f"https://nodejs.org/dist/v{NODE_VERSION}/node-v{NODE_VERSION}"
_TECTONIC = (f"https://github.com/tectonic-typesetting/tectonic/releases/download/"
             f"tectonic%40{TECTONIC_VERSION}/tectonic-{TECTONIC_VERSION}")

#: Per tool, per platform (``<system>-<machine>``): the official archive, from
#: nodejs.org's SHASUMS256.txt and the digests of Tectonic's GitHub release.
RELEASES: dict[str, dict[str, Release]] = {
    "node": {
        "linux-x64": Release(f"{_NODE}-linux-x64.tar.xz",
                             "5c063e46bab0fbc1c17cc445d7ff129cbdcd0471be6ed83b6ab864f8143bc864",
                             f"node-v{NODE_VERSION}-linux-x64/bin/node"),
        "linux-arm64": Release(f"{_NODE}-linux-arm64.tar.xz",
                               "89e1853138db51e8b82d3e98ba9c0d3f2956a28e5e55ea1b7e12d25aae92d5dd",
                               f"node-v{NODE_VERSION}-linux-arm64/bin/node"),
        "darwin-x64": Release(f"{_NODE}-darwin-x64.tar.xz",
                              "2693310b2820f9350d29524f21344e1c623875bab773457d55b2aceb9670716f",
                              f"node-v{NODE_VERSION}-darwin-x64/bin/node"),
        "darwin-arm64": Release(f"{_NODE}-darwin-arm64.tar.xz",
                                "af6202f5370a3a5209e85dc543758dfd9f44c8726626a236730cd603a67a8559",
                                f"node-v{NODE_VERSION}-darwin-arm64/bin/node"),
        "windows-x64": Release(f"{_NODE}-win-x64.zip",
                               "e2edda75bfb089654705cf65a13b58933bfd5f57148e8ebda916f58a2474f1f7",
                               f"node-v{NODE_VERSION}-win-x64/node.exe"),
    },
    "tectonic": {
        "linux-x64": Release(f"{_TECTONIC}-x86_64-unknown-linux-musl.tar.gz",
                             "8533d07f9ccbd7a65824b9e0459041bca34af1eb33daba48f59215593753a3b7",
                             "tectonic"),
        "linux-arm64": Release(f"{_TECTONIC}-aarch64-unknown-linux-musl.tar.gz",
                               "b10954a95404f3ab2328d2fa59a5ebab8e657f893fab096f98be8db7c0c979b8",
                               "tectonic"),
        "darwin-x64": Release(f"{_TECTONIC}-x86_64-apple-darwin.tar.gz",
                              "7c90ef5b6ddb1eb1937e4337add5237b79338e4b9676459fa91187d24d6cdf80",
                              "tectonic"),
        "darwin-arm64": Release(f"{_TECTONIC}-aarch64-apple-darwin.tar.gz",
                                "a3f1cac7c5678f01661a92212f58480ae3b0634115d880dbc59e2953ded45667",
                                "tectonic"),
        "windows-x64": Release(f"{_TECTONIC}-x86_64-pc-windows-msvc.zip",
                               "f61ce51f0b0ade1015b7de7ef368541c5424e9756ecbd0d7af97d6d48030845f",
                               "tectonic.exe"),
    },
}
VERSIONS = {"node": NODE_VERSION, "tectonic": TECTONIC_VERSION}
INSTALL_HINT = {
    "node": f"Install Node.js {NODE_MIN_MAJOR} or newer (https://nodejs.org)",
    "tectonic": "Install Tectonic (https://tectonic-typesetting.github.io)",
}


class ToolError(Exception):
    """A program could not be found or fetched; the message says what to do."""


def platform_key(system: str | None = None, machine: str | None = None) -> str | None:
    """``<system>-<machine>`` as `RELEASES` names it, or None for a platform without a pinned release."""
    system = (system or platform.system()).lower()
    machine = (machine or platform.machine()).lower()
    arch = {"x86_64": "x64", "amd64": "x64", "aarch64": "arm64", "arm64": "arm64"}.get(machine)
    if system not in ("linux", "darwin", "windows") or arch is None:
        return None
    return f"{system}-{arch}"


def default_cache_dir(env: Mapping[str, str]) -> Path:
    base = env.get("XDG_CACHE_HOME") or str(Path(env.get("HOME") or Path.home()) / ".cache")
    return Path(base) / "papersmith" / "tools"


def node_major(node: str) -> int | None:
    """The major version of the ``node`` at that path, or None when it does not answer."""
    try:
        done = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.match(r"v(\d+)\.", done.stdout.strip())
    return int(match.group(1)) if match else None


def _download(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=DOWNLOAD_TIMEOUT) as response:  # noqa: S310 - pinned https URLs
        data = response.read(MAX_ARCHIVE_BYTES + 1)
    return data


def _member(archive: bytes, url: str, member: str) -> bytes:
    """The bytes of one regular file inside a .tar.xz, .tar.gz or .zip, by its exact name."""
    if url.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            try:
                return bundle.read(member)
            except KeyError:
                raise ToolError(f"{url} holds no {member}") from None
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:*") as bundle:
        try:
            info = bundle.getmember(member)
        except KeyError:
            raise ToolError(f"{url} holds no {member}") from None
        if not info.isfile():
            raise ToolError(f"{member} in {url} is not a regular file")
        extracted = bundle.extractfile(info)
        assert extracted is not None
        return extracted.read()


@dataclass
class Tools:
    """Finds ``node`` and ``tectonic``, fetching the missing ones into ``cache_dir``."""

    env: Mapping[str, str]
    cache_dir: Path | None = None
    platform: str | None = None
    # Looked up when called, so a test can replace the module's functions.
    fetch: Callable[[str], bytes] = field(default=lambda url: _download(url))
    node_version: Callable[[str], int | None] = field(default=lambda path: node_major(path))

    def __post_init__(self) -> None:
        if self.cache_dir is None:
            self.cache_dir = default_cache_dir(self.env)
        self.cache_dir = Path(self.cache_dir)
        if self.platform is None:
            self.platform = platform_key()

    def _on_path(self, name: str) -> str | None:
        found = shutil.which(name, path=self.env.get("PATH", ""))
        if found is None:
            return None
        if name == "node" and (self.node_version(found) or 0) < NODE_MIN_MAJOR:
            return None
        return found

    def cached(self, name: str) -> Path:
        """Where the fetched program lives: one folder per tool, version and platform."""
        assert self.cache_dir is not None
        exe = Path(RELEASES[name][self.platform].member).name if self.platform in RELEASES[name] else name
        return self.cache_dir / f"{name}-{VERSIONS[name]}-{self.platform}" / exe

    def find(self, name: str) -> str:
        """The program to run: on the PATH, else already fetched, else fetched now."""
        found = self._on_path(name)
        if found is not None:
            return found
        release = RELEASES[name].get(self.platform or "")
        if release is None:
            raise ToolError(f"{INSTALL_HINT[name]}: there is no {name} release pinned for this platform.")
        target = self.cached(name)
        if target.is_file():
            return str(target)
        if self.env.get(NO_DOWNLOAD_ENV, "").strip().lower() in ("1", "true", "yes", "on"):
            raise ToolError(f"{INSTALL_HINT[name]}; {NO_DOWNLOAD_ENV} keeps it from being downloaded.")
        try:
            archive = self.fetch(release.url)
        except (OSError, http.client.HTTPException) as exc:
            raise ToolError(f"{INSTALL_HINT[name]}: downloading {release.url} failed ({exc!r}).") from None
        if len(archive) > MAX_ARCHIVE_BYTES:
            raise ToolError(f"{release.url} is larger than expected; nothing was installed.")
        digest = hashlib.sha256(archive).hexdigest()
        if digest != release.sha256:
            raise ToolError(f"{release.url} does not match its pinned SHA-256 (got {digest}); nothing was installed.")
        program = _member(archive, release.url, release.member)
        # Written beside its final place and renamed, so a half-written program is never found.
        target.parent.mkdir(parents=True, exist_ok=True)
        handle, partial = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.")
        try:
            with os.fdopen(handle, "wb") as out:
                out.write(program)
            os.chmod(partial, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
            os.replace(partial, target)
        except BaseException:
            Path(partial).unlink(missing_ok=True)
            raise
        return str(target)
