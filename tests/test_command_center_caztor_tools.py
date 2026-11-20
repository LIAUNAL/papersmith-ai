"""Caztor's programs (node, tectonic): found on the PATH, else fetched once, pinned and checked."""

from __future__ import annotations

import hashlib
import io
import os
import re
import stat
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from skills._core.command_center import caztor_tools
from skills._core.command_center.caztor_tools import Release, ToolError, Tools


def _tar(member: str, payload: bytes) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as bundle:
        info = tarfile.TarInfo(member)
        info.size = len(payload)
        bundle.addfile(info, io.BytesIO(payload))
    return buffer.getvalue()


def _zip(member: str, payload: bytes) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        bundle.writestr(member, payload)
    return buffer.getvalue()


class ToolsTests(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.base = Path(holder.name)
        self.cache = self.base / "cache"
        self.bin = self.base / "bin"
        self.bin.mkdir()
        self.archive = _tar("node-v1/bin/node", b"#!/bin/sh\necho fetched\n")
        self.release = Release("https://example.invalid/node.tar.gz", hashlib.sha256(self.archive).hexdigest(),
                               "node-v1/bin/node")
        patch = mock.patch.dict(caztor_tools.RELEASES, {"node": {"linux-x64": self.release},
                                                         "tectonic": {"linux-x64": self.release}})
        patch.start()
        self.addCleanup(patch.stop)
        self.fetched: list[str] = []

    def tools(self, archive: bytes | None = None, env: dict[str, str] | None = None, node_major: int = 26,
              plat: str = "linux-x64") -> Tools:
        def fetch(url: str) -> bytes:
            self.fetched.append(url)
            return self.archive if archive is None else archive
        return Tools(env if env is not None else {"PATH": str(self.bin)}, cache_dir=self.cache, platform=plat,
                     fetch=fetch, node_version=lambda _path: node_major)

    def put_on_path(self, name: str) -> Path:
        program = self.bin / name
        program.write_text("#!/bin/sh\n", encoding="utf-8")
        program.chmod(program.stat().st_mode | stat.S_IEXEC)
        return program

    def test_a_program_on_the_path_is_used_as_it_is(self) -> None:
        tectonic = self.put_on_path("tectonic")
        self.assertEqual(self.tools().find("tectonic"), str(tectonic))
        self.assertEqual(self.fetched, [])

    def test_node_on_the_path_older_than_26_is_passed_over_and_26_is_fetched(self) -> None:
        self.put_on_path("node")
        found = self.tools(node_major=22).find("node")
        self.assertEqual(self.fetched, [self.release.url])
        self.assertTrue(found.startswith(str(self.cache)))

    def test_a_missing_program_is_fetched_checked_and_kept_executable_then_reused(self) -> None:
        tools = self.tools()
        found = Path(tools.find("node"))
        self.assertEqual(found, self.cache / f"node-{caztor_tools.NODE_VERSION}-linux-x64" / "node")
        self.assertEqual(found.read_bytes(), b"#!/bin/sh\necho fetched\n")
        self.assertTrue(os.access(found, os.X_OK))
        self.assertEqual(tools.find("node"), str(found))
        self.assertEqual(self.fetched, [self.release.url], "the second call reuses the fetched copy")
        self.assertEqual([p.name for p in found.parent.iterdir()], ["node"], "no partial file is left behind")

    def test_an_archive_that_does_not_match_its_pinned_checksum_installs_nothing(self) -> None:
        with self.assertRaisesRegex(ToolError, "does not match its pinned SHA-256"):
            self.tools(archive=_tar("node-v1/bin/node", b"tampered")).find("node")
        self.assertFalse(self.cache.exists() and any(self.cache.rglob("node")))

    def test_an_archive_without_the_program_installs_nothing(self) -> None:
        archive = _tar("elsewhere/node", b"x")
        with mock.patch.dict(caztor_tools.RELEASES, {"node": {"linux-x64": Release(
                self.release.url, hashlib.sha256(archive).hexdigest(), "node-v1/bin/node")}}):
            with self.assertRaisesRegex(ToolError, "holds no node-v1/bin/node"):
                self.tools(archive=archive).find("node")
        self.assertFalse(self.cache.exists() and any(self.cache.rglob("node")))

    def test_a_zip_archive_is_read_too(self) -> None:
        archive = _zip("node-v1/node.exe", b"MZ")
        with mock.patch.dict(caztor_tools.RELEASES, {"node": {"windows-x64": Release(
                "https://example.invalid/node.zip", hashlib.sha256(archive).hexdigest(), "node-v1/node.exe")}}):
            found = self.tools(archive=archive, plat="windows-x64").find("node")
        self.assertEqual(Path(found).name, "node.exe")
        self.assertEqual(Path(found).read_bytes(), b"MZ")

    def test_downloads_can_be_turned_off_and_then_name_what_to_install(self) -> None:
        with self.assertRaisesRegex(ToolError, "Install Tectonic.*PAPERSMITH_NO_TOOL_DOWNLOAD"):
            self.tools(env={"PATH": str(self.bin), caztor_tools.NO_DOWNLOAD_ENV: "1"}).find("tectonic")
        self.assertEqual(self.fetched, [])

    def test_a_failed_download_says_what_to_install(self) -> None:
        def offline(_url: str) -> bytes:
            raise OSError("network unreachable")
        tools = Tools({"PATH": str(self.bin)}, cache_dir=self.cache, platform="linux-x64", fetch=offline,
                      node_version=lambda _path: 26)
        with self.assertRaisesRegex(ToolError, "Install Node.js 26.*network unreachable"):
            tools.find("node")

    def test_a_platform_without_a_pinned_release_says_what_to_install(self) -> None:
        with self.assertRaisesRegex(ToolError, "no node release pinned for this platform"):
            self.tools(plat=None or "plan9-mips").find("node")


class PinnedReleasesTests(unittest.TestCase):
    def test_every_platform_pins_both_programs_over_https_with_a_sha256(self) -> None:
        self.assertEqual(set(caztor_tools.RELEASES["node"]), set(caztor_tools.RELEASES["tectonic"]))
        for name, releases in caztor_tools.RELEASES.items():
            for plat, release in releases.items():
                with self.subTest(name=name, platform=plat):
                    self.assertTrue(release.url.startswith(("https://nodejs.org/dist/",
                                                            "https://github.com/tectonic-typesetting/")))
                    self.assertRegex(release.sha256, r"^[0-9a-f]{64}$")
                    self.assertIn(caztor_tools.VERSIONS[name], release.url.replace("%40", "@"))

    def test_platform_names(self) -> None:
        self.assertEqual(caztor_tools.platform_key("Linux", "x86_64"), "linux-x64")
        self.assertEqual(caztor_tools.platform_key("Darwin", "arm64"), "darwin-arm64")
        self.assertEqual(caztor_tools.platform_key("Windows", "AMD64"), "windows-x64")
        self.assertEqual(caztor_tools.platform_key("Linux", "aarch64"), "linux-arm64")
        self.assertIsNone(caztor_tools.platform_key("Linux", "riscv64"))

    def test_node_major_reads_the_version_line(self) -> None:
        with tempfile.TemporaryDirectory() as holder:
            node = Path(holder) / "node"
            node.write_text("#!/bin/sh\necho v26.13.1\n", encoding="utf-8")
            node.chmod(0o755)
            self.assertEqual(caztor_tools.node_major(str(node)), 26)
            self.assertIsNone(caztor_tools.node_major(str(Path(holder) / "missing")))
        self.assertTrue(re.fullmatch(r"\d+\.\d+\.\d+", caztor_tools.NODE_VERSION))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
