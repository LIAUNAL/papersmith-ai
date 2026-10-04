"""Workspace and kit manifests: SHA-256 tracking, filtering, preservation.

Two manifests exist:

* ``kit-manifest.json`` at the kit root — hashes of every framework file the
  kit ships (written by ``scripts/build-kit.py``; computed on the fly when a
  development checkout has none).
* ``<workspace>/.papersmith/manifest.json`` — hashes of every
  framework-managed file as it exists in that workspace, plus the workspace
  version and update timestamp.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from ..errors import UserError
from ..generators import render_files, workspace_tools
from . import fs

MANIFEST_SCHEMA = 1

#: The workspace version marker. It is neither a kit file nor a rendered output,
#: so it is named once here and included in :func:`synchronized_paths`
#: explicitly.
VERSION_MARKER = ".papersmith/version"

# The kit's top-level entries a workspace copies at init and re-syncs on
# upgrade. Everything else a workspace holds is either generated (rendered
# entrypoint docs) or preserved research state.
#
# ``guidance/paper-guide`` is deliberately absent: its real content is
# third-party reference PDFs, and this repository's own ``.gitignore``
# (``guidance/*/*``) keeps them out of git on purpose. ``walk_kit_files``
# walks the filesystem, not git, so listing that directory here would bundle
# whatever a maintainer's checkout happens to hold into every shipped kit. The
# folder still reaches a fresh workspace empty, via ``_create_topology``'s
# ``.gitkeep``.
#
# ``sections`` travels WITH content: the ten ``sections/*.md`` files are
# generic writing contracts, not this paper's own research, so a workspace
# needs the same bytes this repository ships — like ``skills``, not like
# ``guidance/paper-guide``.
KIT_ENTRIES = (
    "skills",
    "sections",
    ".claude/agents",
    "scripts/setup_env.py",
    "scripts/setup-harnesses.sh",
    "requirements.txt",
)

# Paths ``upgrade`` must never overwrite or delete. ``papersmith.yaml``,
# ``package.json`` and ``.pi/settings.json`` are seeded once at init (see
# ``init._write_workspace_seed``) and then belong to the user like ``README.md``
# does; the rest is research state the user produces under the topology
# ``init`` scaffolds.
#
# Preserving is not the same question as seeding. This tuple answers "never
# overwrite or delete", which says nothing about a workspace that predates the
# file and therefore has none -- that is
# :data:`generators.SEED_OUTPUTS`, written only into that absence and never
# baselined, so a seeded path stays exactly as preserved as this tuple makes it.
PRESERVE_PATTERNS = (
    "guidance/**",
    "proposals/**",
    "paper/**",
    "experiments/**",
    "implementations/**",
    "kaggle-inbox/**",
    "papersmith.yaml",
    "package.json",
    ".pi/settings.json",
    "README.md",
    ".env*",
)

_SKIP_DIRS = {".venv", "node_modules", "__pycache__", ".pytest_cache", ".micromamba", ".git"}
_SKIP_SUFFIXES = (".pyc", ".pyo")
_KEEP_HIDDEN = {".gitignore", ".gitkeep"}
_STORE_DIR = "skills/kaggle-accounts/store"


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def is_preserved(relpath: str) -> bool:
    """True when ``upgrade`` must never overwrite or delete the path."""
    posix = relpath.replace("\\", "/")
    name = posix.rsplit("/", 1)[-1]
    for pattern in PRESERVE_PATTERNS:
        if pattern.endswith("/**"):
            prefix = pattern[:-3]
            if posix == prefix or posix.startswith(prefix + "/"):
                return True
        elif pattern.endswith("*") and pattern.startswith("."):
            if name.startswith(pattern[:-1]):
                return True
        elif posix == pattern:
            return True
    return False


def should_skip_file(path: Path) -> bool:
    name = path.name
    if name.startswith(".") and name not in _KEEP_HIDDEN:
        return True
    return path.suffix in _SKIP_SUFFIXES


def should_skip_dir(path: Path) -> bool:
    return path.name in _SKIP_DIRS


def _walk_dir(root: Path, kit_root: Path, files: dict[str, str]) -> None:
    try:
        children = sorted(root.iterdir())
    except OSError:
        return
    for child in children:
        if fs.is_dir(child):
            if should_skip_dir(child):
                continue
            if child.relative_to(kit_root).as_posix() == _STORE_DIR:
                # The credential store ships only its protective .gitignore —
                # a stored token committed is a token burned.
                store = []
                try:
                    store = sorted(child.iterdir())
                except OSError:
                    pass
                for entry in store:
                    if fs.is_regular_file(entry) and entry.name == ".gitignore":
                        files[entry.relative_to(kit_root).as_posix()] = sha256_file(entry)
                continue
            _walk_dir(child, kit_root, files)
            continue
        # A non-regular entry is not a framework file, and hashing one would
        # block forever on a FIFO rather than report the damaged kit source.
        if should_skip_file(child) or not fs.is_regular_file(child):
            continue
        files[child.relative_to(kit_root).as_posix()] = sha256_file(child)


def walk_kit_files(kit_root: Path) -> dict[str, str]:
    """relpath -> sha256 for every file the kit ships, filtered."""
    files: dict[str, str] = {}
    for entry in KIT_ENTRIES:
        path = kit_root / entry
        if not fs.exists(path):
            continue
        if fs.is_regular_file(path):
            files[entry] = sha256_file(path)
        else:
            _walk_dir(path, kit_root, files)
    return files


def copy_kit_file(kit_root: Path, relpath: str, dest_root: Path) -> bool:
    """Copy one kit file into a workspace, or report that it could not be done.

    ``shutil.copyfile`` opens the destination for writing, so a FIFO there would
    block forever and a directory would raise — after earlier paths in the same
    run have already been synchronized. Returns False instead.
    """
    return fs.copy_file(kit_root / relpath, dest_root / relpath)


def load_manifest(workspace: Path) -> dict | None:
    path = workspace / ".papersmith" / "manifest.json"
    if not fs.is_regular_file(path):
        if fs.exists(path):
            raise UserError(f"corrupted manifest {path}: not a readable regular file")
        return None
    text = fs.read_text(path)
    if text is None:
        raise UserError(f"corrupted manifest {path}: unreadable or not valid UTF-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise UserError(f"corrupted manifest {path}: {exc}") from None
    if not isinstance(data, dict) or data.get("kind") != "workspace":
        raise UserError(f"corrupted manifest {path}: missing workspace envelope")
    if data.get("schema") != MANIFEST_SCHEMA or not isinstance(data.get("version"), str):
        raise UserError(f"corrupted manifest {path}: unsupported schema or version")
    files = data.get("files")
    if not isinstance(files, dict) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in files.items()
    ):
        raise UserError(f"corrupted manifest {path}: files must be a string-to-string map")
    return data


def write_manifest(dest_root: Path, version: str, files: dict[str, str], *, kind: str) -> None:
    payload = {
        "schema": MANIFEST_SCHEMA,
        "kind": kind,
        "version": version,
        "files": dict(sorted(files.items())),
    }
    if kind == "workspace":
        payload["updated_at"] = _timestamp()
        path = dest_root / ".papersmith" / "manifest.json"
    elif kind == "kit":
        payload["generated_at"] = _timestamp()
        path = dest_root / "kit-manifest.json"
    else:
        raise ValueError(f"unknown manifest kind {kind!r}")
    if not fs.write_text(path, json.dumps(payload, indent=2) + "\n"):
        raise UserError(f"could not write {path}")


def load_kit_manifest(kit_root: Path) -> dict | None:
    path = kit_root / "kit-manifest.json"
    if not fs.is_regular_file(path):
        if fs.exists(path):
            raise UserError(f"corrupted kit manifest {path}: not a readable regular file")
        return None
    text = fs.read_text(path)
    if text is None:
        raise UserError(f"corrupted kit manifest {path}: unreadable or not valid UTF-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise UserError(f"corrupted kit manifest {path}: {exc}") from None
    if not isinstance(data, dict) or data.get("kind") != "kit":
        raise UserError(f"corrupted kit manifest {path}: missing kit envelope")
    if data.get("schema") != MANIFEST_SCHEMA or not isinstance(data.get("version"), str):
        raise UserError(f"corrupted kit manifest {path}: unsupported schema or version")
    return data


def kit_files(kit_root: Path) -> dict[str, str]:
    """relpath -> sha256 for the kit's framework files.

    A bundled kit answers from its manifest; a development checkout has none
    and is hashed live so ``upgrade`` always tracks the latest dev state.
    """
    cached = load_kit_manifest(kit_root)
    if cached is not None:
        files = cached.get("files")
        if isinstance(files, dict) and all(isinstance(v, str) for v in files.values()):
            return dict(files)
        raise UserError(f"corrupted kit manifest at {kit_root}: bad files map")
    return walk_kit_files(kit_root)


def kit_version(kit_root: Path) -> str:
    cached = load_kit_manifest(kit_root)
    if cached is not None and isinstance(cached.get("version"), str):
        return cached["version"]
    pkg = kit_root / "package.json"
    text = fs.read_text(pkg)
    if text is not None:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict) and isinstance(data.get("version"), str):
            return data["version"]
    return "0.0.0"


def sha256_if_readable(path: Path) -> str | None:
    """``sha256_file`` for a path that may be absent or unreadable.

    A framework-managed file can be missing, permission-denied, or otherwise
    unstatable. The manifest records what it can actually read rather than
    aborting its caller: ``status`` and ``audit`` must report a damaged
    workspace, not die on one.
    """
    if not fs.is_regular_file(path):
        return None
    try:
        return sha256_file(path)
    except OSError:
        return None


def synchronized_paths(workspace: Path, kit_root: Path, context: dict | None = None,
                       tools: list[str] | tuple[str, ...] | None = None) -> set[str]:
    """Every path a run is responsible for *delivering* into a workspace.

    This is the set a baseline writer must sweep: :func:`workspace_framework_files`
    records a hash for each of these, but silently omits any it cannot read, and a
    path absent from both the live and the stored map is invisible to ``status`` —
    which is how a damaged path turns into a false "no drift".

    **Preserved paths are excluded.** ``guidance/**``, ``README.md``,
    ``papersmith.yaml`` and friends are the user's by contract
    (:func:`is_preserved`); a run never delivers them, so it must not demand them.
    Marking one because the user deleted it — or because a newer kit added a file
    the workspace predates — would record drift that no ``upgrade`` can ever
    clear, since ``upgrade`` skips preserved paths on every run.

    Kept here, beside the manifest it describes, so the components cannot drift
    from what :func:`workspace_framework_files` actually records.
    """
    deliverable = {relpath for relpath in kit_files(kit_root) if not is_preserved(relpath)}
    rendered = render_files(workspace, context, tools or workspace_tools(workspace))
    return deliverable | set(rendered) | {VERSION_MARKER}


def workspace_framework_files(workspace: Path, kit_root: Path,
                              context: dict | None = None) -> dict[str, str]:
    """Current hashes of every framework-managed file in a workspace.

    The rendered contribution derives from :func:`generators.render_files` — the
    single path authority — instead of a second, hand-maintained path list. The
    stored baseline, ``status`` and ``audit`` therefore all see the same set,
    dynamic per-skill command files included, and cannot drift apart.

    ``context`` is optional so the existing two-argument callers keep working: a
    caller that already built one may pass it, and it is derived here otherwise.

    A path this cannot read is **omitted**, not marked — see
    :func:`synchronized_paths` for why the baseline writer has to account for
    that.
    """
    files: dict[str, str] = {}
    for relpath in kit_files(kit_root):
        digest = sha256_if_readable(workspace / relpath)
        if digest is not None:
            files[relpath] = digest
    rendered = render_files(workspace, context, workspace_tools(workspace))
    for relpath in rendered:
        digest = sha256_if_readable(workspace / relpath)
        if digest is not None:
            files[relpath] = digest
    version_digest = sha256_if_readable(workspace / VERSION_MARKER)
    if version_digest is not None:
        files[VERSION_MARKER] = version_digest
    return files
