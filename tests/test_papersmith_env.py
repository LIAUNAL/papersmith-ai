"""Tests for `smith env` management and executor environment gate."""

from __future__ import annotations

import io
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from papersmith.cli import build_parser, main
from papersmith.core import env as env_module, executor
from papersmith.core.exit_codes import SUCCESS
from papersmith.errors import UserError


class EnvCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(__import__("tempfile").mkdtemp(prefix="papersmith-env-test-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))

    def seed_script(self, workspace: Path) -> Path:
        script = workspace / "scripts" / "setup_env.py"
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
        return script

    def test_parser_exposes_env_subcommands(self) -> None:
        parser = build_parser()
        install_args = parser.parse_args(["env", "install", "--cpu", "--no-ingestion", "my-workspace"])
        self.assertEqual(install_args.env_command, "install")
        self.assertTrue(install_args.cpu)
        self.assertTrue(install_args.no_ingestion)
        self.assertEqual(install_args.directory, "my-workspace")

        status_args = parser.parse_args(["env", "status"])
        self.assertEqual(status_args.env_command, "status")

        clean_args = parser.parse_args(["env", "clean", "--full"])
        self.assertEqual(clean_args.env_command, "clean")
        self.assertTrue(clean_args.full)

    def test_missing_script_raises_user_error(self) -> None:
        with self.assertRaisesRegex(UserError, "no provisioning script"):
            env_module.run_env_tool(self.tmp, "status")

    def test_env_install_dispatches_correct_arguments(self) -> None:
        self.seed_script(self.tmp)
        captured = []

        def fake_run(args, cwd, check=False):
            captured.append((args, cwd))
            return subprocess.CompletedProcess(args=args, returncode=0)

        with mock.patch("subprocess.run", side_effect=fake_run):
            rc = main(["env", "install", "--cuda", "--no-ingestion", str(self.tmp)])
            self.assertEqual(rc, SUCCESS)

        self.assertEqual(len(captured), 1)
        cmd, cwd = captured[0]
        self.assertEqual(cwd, self.tmp.resolve())
        self.assertIn("install", cmd)
        self.assertIn("--cuda", cmd)
        self.assertIn("--no-ingestion", cmd)

    def test_env_install_passes_rocm_through(self) -> None:
        self.seed_script(self.tmp)
        captured = []

        def fake_run(args, cwd, check=False):
            captured.append(args)
            return subprocess.CompletedProcess(args=args, returncode=0)

        with mock.patch("subprocess.run", side_effect=fake_run):
            self.assertEqual(main(["env", "install", "--rocm", str(self.tmp)]), SUCCESS)
        self.assertIn("--rocm", captured[0])
        self.assertNotIn("--cuda", captured[0])

    def test_env_clean_dispatches_full_flag(self) -> None:
        self.seed_script(self.tmp)
        captured = []

        def fake_run(args, cwd, check=False):
            captured.append(args)
            return subprocess.CompletedProcess(args=args, returncode=0)

        with mock.patch("subprocess.run", side_effect=fake_run):
            rc = main(["env", "clean", "--full", str(self.tmp)])
            self.assertEqual(rc, SUCCESS)

        self.assertEqual(len(captured), 1)
        self.assertIn("clean", captured[0])
        self.assertIn("--full", captured[0])


class ExecutorEnvGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(__import__("tempfile").mkdtemp(prefix="papersmith-gate-test-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))

    def seed_script(self) -> Path:
        script = self.tmp / "scripts" / "setup_env.py"
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
        return script

    def test_remote_passes_silently_when_non_interactive(self) -> None:
        with mock.patch.object(sys.stdin, "isatty", return_value=False):
            # Non-interactive does not block or fail, falls back gracefully
            executor._prompt_env_if_interactive(self.tmp, "sweep_training")

    def test_remote_interactive_prompt_declined(self) -> None:
        self.seed_script()
        with mock.patch.object(sys.stdin, "isatty", return_value=True):
            with mock.patch.object(sys.stdin, "readline", return_value="n\n"):
                err = io.StringIO()
                with mock.patch("sys.stderr", err):
                    executor._prompt_env_if_interactive(self.tmp, "sweep_training")
                self.assertIn("Continuing with host interpreter", err.getvalue())

    def test_remote_interactive_prompt_accepted_and_provisioned(self) -> None:
        self.seed_script()
        captured = []

        def fake_run(args, cwd, check=False):
            captured.append(args)
            return subprocess.CompletedProcess(args=args, returncode=0)

        with mock.patch.object(sys.stdin, "isatty", return_value=True):
            with mock.patch.object(sys.stdin, "readline", return_value="y\n"):
                with mock.patch("subprocess.run", side_effect=fake_run):
                    err = io.StringIO()
                    with mock.patch("sys.stderr", err):
                        executor._prompt_env_if_interactive(self.tmp, "sweep_training")
                    self.assertIn("Environment provisioning complete", err.getvalue())
        self.assertEqual(len(captured), 1)
        self.assertIn("install", captured[0])

    def test_already_provisioned_passes_silently(self) -> None:
        with mock.patch.object(executor, "_env_is_provisioned", return_value=True):
            executor._prompt_env_if_interactive(self.tmp, "sweep_training")


class CrossPlatformCompatibilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(__import__("tempfile").mkdtemp(prefix="papersmith-cross-test-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))

    def test_windows_micromamba_exe_detection(self) -> None:
        from papersmith.bridges.python import interpreter_for
        from papersmith.core.status import _runtime_status

        # Simulate Windows directory structure with micromamba.exe
        mamba_bin = self.tmp / ".micromamba" / "bin" / "micromamba.exe"
        mamba_bin.parent.mkdir(parents=True, exist_ok=True)
        mamba_bin.write_text("", encoding="utf-8")

        env_dir = self.tmp / ".micromamba" / "envs" / "papersmith"
        env_dir.mkdir(parents=True, exist_ok=True)

        with mock.patch("os.name", "nt"):
            self.assertTrue(executor._env_is_provisioned(self.tmp))
            status = _runtime_status(self.tmp)
            self.assertTrue(status["micromamba"])
            cmd = interpreter_for(self.tmp, prefer_micromamba=True)
            self.assertIn("micromamba.exe", cmd[0])

    def test_linux_wsl_micromamba_detection(self) -> None:
        from papersmith.bridges.python import interpreter_for
        from papersmith.core.status import _runtime_status

        mamba_bin = self.tmp / ".micromamba" / "bin" / "micromamba"
        mamba_bin.parent.mkdir(parents=True, exist_ok=True)
        mamba_bin.write_text("", encoding="utf-8")

        env_dir = self.tmp / ".micromamba" / "envs" / "papersmith"
        env_dir.mkdir(parents=True, exist_ok=True)

        with mock.patch("os.name", "posix"):
            self.assertTrue(executor._env_is_provisioned(self.tmp))
            status = _runtime_status(self.tmp)
            self.assertTrue(status["micromamba"])
            cmd = interpreter_for(self.tmp, prefer_micromamba=True)
            self.assertIn("micromamba", cmd[0])

    def test_ui_provisioned_interpreters_includes_windows_layout(self) -> None:
        from papersmith.core.ui import provisioned_interpreters

        script = self.tmp / "scripts" / "setup_env.py"
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text(
            "MAMBA_ROOT = '.micromamba'\nENV_NAME = 'papersmith'\n", encoding="utf-8"
        )
        interpreters = provisioned_interpreters(self.tmp)
        # Verify both bin/python and root env/python.exe (Windows Conda layout) are listed
        paths_str = [str(p).replace("\\", "/") for p in interpreters]
        self.assertTrue(any("envs/papersmith/python.exe" in p for p in paths_str))
        self.assertTrue(any("envs/papersmith/bin/python" in p for p in paths_str))

