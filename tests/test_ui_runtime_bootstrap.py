"""`smith ui` right after `smith init`: the dashboard's own light runtime.

`smith init` defers the multi-gigabyte workspace environment, and the pipx
install declares no runtime dependency, so no interpreter could import the
backend and `smith ui` refused on every fresh workspace. The command now
installs the dashboard's four packages once into a shared cache environment and
serves from it; only when that install fails does it refuse, naming both
remedies.
"""

from __future__ import annotations

import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from papersmith.core import ui
from papersmith.errors import UserError


def _fake_python(path: Path, importable: bool) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"#!/bin/sh\nexit {0 if importable else 1}\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


class UiRuntimeBootstrapTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.workspace = self.root / "paper"
        self.workspace.mkdir()
        patcher = mock.patch.dict(os.environ, {"XDG_CACHE_HOME": str(self.root / "cache")})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.broken = str(_fake_python(self.root / "pipx" / "python", importable=False))

    def test_the_cache_environment_lives_outside_the_workspace(self) -> None:
        env_dir = ui.ui_env_dir()
        self.assertTrue(str(env_dir).startswith(str(self.root / "cache" / "papersmith")))
        self.assertFalse(str(env_dir).startswith(str(self.workspace)))

    def test_an_existing_cache_environment_serves_when_the_cli_interpreter_cannot(self) -> None:
        cached = _fake_python(ui.ui_env_interpreter(), importable=True)
        with mock.patch.object(ui, "provision_ui_env") as provision:
            self.assertEqual(ui.require_runnable_backend(self.workspace, self.broken), str(cached))
        provision.assert_not_called()

    def test_a_working_cli_interpreter_is_never_shadowed_by_the_cache(self) -> None:
        _fake_python(ui.ui_env_interpreter(), importable=True)
        with mock.patch.object(ui.sys, "executable", self.broken):
            self.assertEqual(ui.workspace_interpreter(self.workspace), self.broken)

    def test_a_failed_install_names_the_failing_output(self) -> None:
        import subprocess
        def run(argv, **kwargs):
            if "-c" in argv:  # the backend probe: cannot import
                return subprocess.CompletedProcess(argv, 1)
            raise subprocess.CalledProcessError(1, argv, output="", stderr="ERROR: no network\n")

        with mock.patch.object(ui.subprocess, "run", side_effect=run):
            with self.assertRaises(UserError) as caught:
                ui.require_runnable_backend(self.workspace, self.broken)
        self.assertIn("ERROR: no network", str(caught.exception))

    def test_a_workspace_environment_still_wins_over_the_cache(self) -> None:
        _fake_python(ui.ui_env_interpreter(), importable=True)
        venv = _fake_python(self.workspace / ".venv" / "bin" / "python", importable=True)
        self.assertEqual(ui.workspace_interpreter(self.workspace), str(venv))

    def test_a_missing_backend_is_installed_once_and_then_served(self) -> None:
        calls = []

        def provision(report=None):
            calls.append(report)
            return _fake_python(ui.ui_env_interpreter(), importable=True)

        with mock.patch.object(ui, "provision_ui_env", side_effect=provision):
            chosen = ui.require_runnable_backend(self.workspace, self.broken)
        self.assertEqual(chosen, str(ui.ui_env_interpreter()))
        self.assertEqual(len(calls), 1)

    def test_a_working_interpreter_installs_nothing(self) -> None:
        good = str(_fake_python(self.root / "good" / "python", importable=True))
        with mock.patch.object(ui, "provision_ui_env") as provision:
            self.assertEqual(ui.require_runnable_backend(self.workspace, good), good)
        provision.assert_not_called()

    def test_a_failed_install_refuses_naming_both_remedies(self) -> None:
        with mock.patch.object(ui, "provision_ui_env", return_value=None):
            with self.assertRaises(UserError) as caught:
                ui.require_runnable_backend(self.workspace, self.broken)
        message = str(caught.exception)
        self.assertIn("smith env install", message)
        self.assertIn(str(ui.ui_env_dir()), message)

    def test_the_installed_packages_are_the_ones_requirements_declares(self) -> None:
        requirements = (Path(__file__).resolve().parents[1] / "requirements.txt").read_text()
        for spec in ui.UI_ENV_PACKAGES:
            with self.subTest(spec=spec):
                self.assertIn(spec, requirements)


if __name__ == "__main__":
    unittest.main()
