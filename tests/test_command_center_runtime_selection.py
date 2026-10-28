"""The command-center smoke picks an interpreter that can run the server.

`scripts/command-center-smoke.sh` used to pin `.venv/bin/python` whenever it
existed, so a `.venv` without fastapi failed readiness even though the
canonical test runtime (`.micromamba/envs/papersmith`) had it. These tests copy
the script into a scratch workspace whose interpreters are stand-ins that
either can or cannot import the dependencies, and read the choice through
`--which-python`, which never starts the server.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "command-center-smoke.sh"
BASH = shutil.which("bash") or "/bin/bash"

CANONICAL = ".micromamba/envs/papersmith/bin/python"
VENV = ".venv/bin/python"
WITH_DEPS = "#!/bin/sh\nexit 0\n"
WITHOUT_DEPS = "#!/bin/sh\necho \"ModuleNotFoundError: No module named 'fastapi'\" >&2\nexit 1\n"


class SmokeRuntimeSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.root = Path(holder.name).resolve()
        (self.root / "scripts").mkdir()
        shutil.copy2(SCRIPT, self.root / "scripts" / SCRIPT.name)
        self.bin = self.root / "path-bin"
        self.bin.mkdir()

    def interpreter(self, rel: str, body: str) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        path.chmod(0o755)
        return path

    def select(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [BASH, str(self.root / "scripts" / SCRIPT.name), "--which-python"],
            cwd=str(self.root),
            env={"PATH": f"{self.bin}:/usr/bin:/bin", "HOME": str(self.root)},
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_canonical_runtime_wins_over_a_venv_without_the_server_deps(self) -> None:
        canonical = self.interpreter(CANONICAL, WITH_DEPS)
        self.interpreter(VENV, WITHOUT_DEPS)

        result = self.select()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(canonical))
        self.assertEqual(result.stderr, "")

    def test_canonical_runtime_comes_first_when_the_venv_also_qualifies(self) -> None:
        canonical = self.interpreter(CANONICAL, WITH_DEPS)
        self.interpreter(VENV, WITH_DEPS)

        result = self.select()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(canonical))

    def test_a_venv_without_the_server_deps_is_skipped_for_path_python(self) -> None:
        self.interpreter(VENV, WITHOUT_DEPS)
        path_python = self.interpreter("path-bin/python3", WITH_DEPS)

        result = self.select()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(path_python))

    def test_a_venv_with_the_server_deps_still_runs_when_no_canonical_runtime(self) -> None:
        venv = self.interpreter(VENV, WITH_DEPS)
        self.interpreter("path-bin/python3", WITH_DEPS)

        result = self.select()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(venv))

    def test_a_canonical_runtime_without_the_deps_falls_back_to_the_venv(self) -> None:
        self.interpreter(CANONICAL, WITHOUT_DEPS)
        venv = self.interpreter(VENV, WITH_DEPS)

        result = self.select()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(venv))

    def test_no_qualifying_interpreter_fails_before_starting_and_names_each_rejection(self) -> None:
        canonical = self.interpreter(CANONICAL, WITHOUT_DEPS)
        venv = self.interpreter(VENV, WITHOUT_DEPS)
        python3 = self.interpreter("path-bin/python3", WITHOUT_DEPS)
        python = self.interpreter("path-bin/python", WITHOUT_DEPS)

        result = self.select()

        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("command-center smoke: FAIL (check runtime): "
                      "no interpreter can import fastapi and uvicorn; rejected:", result.stderr)
        for rejected in (canonical, venv, python3, python):
            self.assertIn(str(rejected), result.stderr)
        self.assertNotIn("command-center smoke: ok", result.stderr)


if __name__ == "__main__":
    unittest.main()
