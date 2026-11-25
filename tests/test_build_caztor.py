"""scripts/build-caztor.py: when it builds Caztor, when it refuses and what it says.

`node` and `npm` are faked by shell scripts first on PATH, so no real build
runs. The fake `npm` records its arguments and fails, which stops the script
before it would replace ``src/papersmith/_caztor``.
"""

from __future__ import annotations

import importlib.util
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "build-caztor.py"


def load_script():
    spec = importlib.util.spec_from_file_location("build_caztor", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_executable(path: Path, body: str) -> None:
    path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


class NodeVersionCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="build-caztor-")
        self.bin = Path(self._tmp.name)
        self.npm_log = self.bin / "npm.log"
        write_executable(self.bin / "npm", f'echo "$@" >> "{self.npm_log}"\nexit 1\n')

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def fake_node(self, version_line: str) -> None:
        write_executable(self.bin / "node", f'echo "{version_line}"\n')

    def run_script(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = {**os.environ, "PATH": str(self.bin)}
        return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=REPO, env=env,
                              capture_output=True, text=True)

    def test_node_older_than_26_is_refused_before_npm_runs(self) -> None:
        self.fake_node("v24.11.0")
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        for stream in (result.stdout, result.stderr):
            self.assertIn("build-caztor: skipped", stream)
            self.assertIn("Node.js 26 or newer", stream)
            self.assertIn("v24.11.0", stream)
        self.assertFalse(self.npm_log.exists(), "npm ran although node is too old")

    def test_require_makes_an_old_node_fatal(self) -> None:
        self.fake_node("v25.9.0")
        result = self.run_script("--require")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Node.js 26 or newer", result.stderr)
        self.assertIn("v25.9.0", result.stderr)
        self.assertFalse(self.npm_log.exists())

    def test_an_unreadable_node_version_is_refused(self) -> None:
        self.fake_node("not a version")
        result = self.run_script()
        self.assertEqual(result.returncode, 0)
        self.assertIn("Node.js 26 or newer", result.stdout)
        self.assertIn("not a version", result.stdout)
        self.assertFalse(self.npm_log.exists())

    def test_node_26_passes_the_check_and_the_build_runs(self) -> None:
        self.fake_node("v26.13.1")
        result = self.run_script()
        self.assertTrue(self.npm_log.exists(), "the build did not start with Node.js 26")
        # The fake npm fails, so the script skips with that reason, on stdout too.
        self.assertEqual(result.returncode, 0)
        self.assertIn("building Caztor failed", result.stdout)
        self.assertIn("building Caztor failed", result.stderr)

    def test_quiet_does_not_hide_why_it_skipped(self) -> None:
        self.fake_node("v22.1.0")
        result = self.run_script("--quiet")
        self.assertIn("Node.js 26 or newer", result.stdout)

    def test_missing_node_says_so(self) -> None:
        result = self.run_script()
        self.assertEqual(result.returncode, 0)
        self.assertIn("node and npm are needed", result.stdout)


class AssembleTests(unittest.TestCase):
    """assemble() copies the run-time files, the third-party notices among them."""

    def setUp(self) -> None:
        self.module = load_script()
        self._tmp = tempfile.TemporaryDirectory(prefix="build-caztor-assemble-")
        tmp = Path(self._tmp.name)
        self.caztor, self.target = tmp / "caztor", tmp / "_caztor"
        for relpath in ("apps/server-local/dist/main.mjs",
                        "apps/server-local/dist/THIRD_PARTY_NOTICES.md",
                        "apps/web/dist/index.html",
                        "apps/web/dist/THIRD_PARTY_NOTICES.md",
                        "LICENSES/Apache-2.0.txt", "NOTICE.md", "README.md",
                        "agents/claude.md", "guides/INDEX.md"):
            path = self.caztor / relpath
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(relpath, encoding="utf-8")
        patcher = mock.patch.multiple(self.module, CAZTOR=self.caztor, TARGET=self.target)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_both_notices_are_packaged(self) -> None:
        self.module.assemble()
        for relpath in ("apps/server-local/dist/THIRD_PARTY_NOTICES.md",
                        "apps/web/dist/THIRD_PARTY_NOTICES.md"):
            self.assertTrue((self.target / relpath).is_file(), f"_caztor has no {relpath}")

    def test_a_missing_notice_stops_the_packaging(self) -> None:
        for relpath in ("apps/server-local/dist/THIRD_PARTY_NOTICES.md",
                        "apps/web/dist/THIRD_PARTY_NOTICES.md"):
            with self.subTest(relpath=relpath):
                notice = self.caztor / relpath
                notice.unlink()
                with self.assertRaises(SystemExit) as raised:
                    self.module.assemble()
                self.assertIn(relpath, str(raised.exception))
                self.assertFalse(self.target.exists(), "a package without its notices was written")
                notice.write_text("restored", encoding="utf-8")


class NodeMajorTests(unittest.TestCase):
    def test_reads_the_major_version(self) -> None:
        module = load_script()
        for line, major in (("v26.13.1", 26), ("v24.0.0\n", 24), ("v100.1.2", 100), ("26.1.0", None), ("", None)):
            with self.subTest(line=line):
                self.assertEqual(module.node_major(line), major)


if __name__ == "__main__":
    unittest.main()
