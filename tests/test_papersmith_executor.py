"""Execution-profile, ledger, target, remote, and audit contracts."""

from __future__ import annotations

import contextlib
import io
import json
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from papersmith.bridges import audit as audit_bridge
from papersmith.bridges import python as python_bridge
from papersmith.bridges import remote as remote_bridge
from papersmith.cli import main
from papersmith.core import config, executor, init as init_module, ledger, target
from papersmith.core.exit_codes import DRIFT_ERROR, EXECUTION_ERROR, SUCCESS
from papersmith.errors import UserError


def _workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "paper"
    init_module.initialize(workspace, run_npm=False)
    return workspace


#: The interpreter the local `smoke` profile below actually launches.
#: `executor.run_profile()` `shlex.split`s the entrypoint and runs it with
#: no shell, so a bare `python` is resolved by the caller's `PATH` -- and on
#: a machine where `PATH` carries `python3` but no `python`, the job simply
#: failed and the profile reported `failed` over a correct executor. Naming
#: `sys.executable` removes `PATH` from the question entirely, which is the
#: same rule `tests/test_forge_gate.py` holds the repository's own gate to.
LOCAL_INTERPRETER = shlex.quote(sys.executable)


def _write_local_manifest(workspace: Path, *, sharded: bool = False) -> None:
    values = "\n      values: [11, 22]\n      parameter: \"--seed\"" if sharded else ""
    enabled = str(sharded).lower()
    workspace.joinpath("papersmith.yaml").write_text(
        f'''version: "1"
name: "{workspace.name}"
title: "Execution Test"
compute_targets:
  default: "local"
  targets:
    local:
      provider: "local"
    kaggle-gpu-pool:
      provider: "kaggle"
      account_pool: "default"
      accelerator: "GPU_T4_X2"
      internet_access: true
      max_timeout_hours: 9
      auto_pull_artifacts: true
    slurm-cluster:
      provider: "remote-ssh"
      host: "hpc.university.edu"
      partition: "gpu-a100"
      nodes: 1
      gpus_per_node: 2
      walltime: "12:00:00"
execution_profiles:
  smoke:
    target: "local"
    entrypoint: "{LOCAL_INTERPRETER} -c \\\"print(42)\\\""
    timeout_seconds: 30
    sharding:
      enabled: {enabled}{values}
  kaggle-train:
    target: "kaggle-gpu-pool"
    entrypoint: "python implementations/paper/src/train.py"
    timeout_seconds: 30
    sharding:
      enabled: {enabled}{values}
  slurm-train:
    target: "slurm-cluster"
    entrypoint: "python implementations/paper/src/train.py"
    timeout_seconds: 30
''',
        encoding="utf-8",
    )


def _write_broken_ssh_manifest(workspace: Path) -> None:
    workspace.joinpath("papersmith.yaml").write_text(
        f'''version: "1"
name: "{workspace.name}"
title: "Execution Test"
compute_targets:
  default: "broken-ssh"
  targets:
    broken-ssh:
      provider: "remote-ssh"
execution_profiles:
  smoke:
    target: "broken-ssh"
    entrypoint: "python implementations/paper/src/train.py"
    timeout_seconds: 30
''',
        encoding="utf-8",
    )


def _remote_args(**overrides):
    values = {
        "operation": "push",
        "target": "implementations/paper",
        "entrypoint": "implementations/paper/runner.ipynb",
        "backend": "kaggle",
        "account": "worker-a",
        "job": None,
        "submission_id": None,
        "dest": None,
        "consent": "token",
        "smoke": True,
        "unit": ["seed 1", "seed,2"],
        "force": False,
        "resolve": False,
        "service": None,
        "job_name": None,
        "product": None,
        "commit": None,
        "repo_url": None,
        "repo_ref": None,
        "run_module": None,
        "run_function": None,
        "clone_path": [],
        "regenerate": False,
        "extra": [],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class ExecutorTests(unittest.TestCase):
    def new_tmp(self) -> Path:
        """Scratch directory, resolved -- see BridgesTests.new_tmp for why."""
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        return Path(holder.name).resolve()

    def patch(self, target, attribute, value):
        patcher = mock.patch.object(target, attribute, value)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_ledger_is_append_only_and_jsonl(self) -> None:
        tmp_path = self.new_tmp()
        ledger.append(tmp_path, {"profile": "smoke", "exit": 0})
        ledger.append(tmp_path, {"profile": "sweep", "exit": 4})
        records = ledger.read(tmp_path)
        assert [record["profile"] for record in records] == ["smoke", "sweep"]
        assert all("timestamp" in record for record in records)
        assert len((tmp_path / ".papersmith/runs_ledger.jsonl").read_text().splitlines()) == 2

    def test_local_profile_runs_and_records_success(self) -> None:
        workspace = _workspace(self.new_tmp())
        _write_local_manifest(workspace)

        result = executor.run_profile(workspace, "smoke")

        assert result["status"] == "ok"
        assert result["jobs"][0]["exit"] == SUCCESS
        assert ledger.read(workspace)[0]["dry_run"] is False

    def test_dry_run_and_shard_selection_are_recorded_without_dispatch(self) -> None:
        workspace = _workspace(self.new_tmp())
        _write_local_manifest(workspace, sharded=True)
        called = False

        def fail_if_called(*args, **kwargs):
            nonlocal called
            called = True
            raise AssertionError("dry-run dispatched a subprocess")

        self.patch(executor.subprocess, "run", fail_if_called)
        result = executor.run_profile(workspace, "smoke", dry_run=True, shard=1)

        assert called is False
        assert result["status"] == "ok"
        assert result["jobs"][0]["shard_value"] == 22
        assert result["jobs"][0]["command"][-2:] == ["--seed", "22"]
        assert ledger.read(workspace)[0]["dry_run"] is True

    def test_profile_rejects_invalid_shard_and_profile(self) -> None:
        workspace = _workspace(self.new_tmp())
        _write_local_manifest(workspace, sharded=True)
        with self.assertRaisesRegex(UserError, "outside"):
            executor.run_profile(workspace, "smoke", shard=3)
        with self.assertRaisesRegex(UserError, "unknown execution profile"):
            executor.run_profile(workspace, "missing", dry_run=True)

    def test_target_list_set_and_local_check(self) -> None:
        workspace = _workspace(self.new_tmp())
        data = config.load_papersmith_yaml(workspace)
        listed = target.list_targets(workspace)
        assert {item["name"] for item in listed} == set(data["compute_targets"]["targets"])
        selected = target.set_target(workspace, "local-workstation")
        assert selected["provider"] == "local"
        code, result = target.check_target(workspace)
        assert code == SUCCESS
        assert result["reachable"] is True

    def test_target_rejects_unknown_name(self) -> None:
        workspace = _workspace(self.new_tmp())
        with self.assertRaisesRegex(UserError, "unknown compute target"):
            target.set_target(workspace, "does-not-exist")

    def test_cli_run_dry_run_and_target_list(self) -> None:
        workspace = _workspace(self.new_tmp())
        _write_local_manifest(workspace)
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            assert main(["run", "smoke", "--dry-run", str(workspace)]) == SUCCESS
        output = buffer.getvalue()
        assert '"dry_run": true' in output
        buffer2 = io.StringIO()
        with contextlib.redirect_stdout(buffer2):
            assert main(["target", "list", str(workspace)]) == SUCCESS
        assert "local: local" in buffer2.getvalue()

    def test_remote_push_maps_account_job_and_repeatable_units(self) -> None:
        command = remote_bridge.command_args(_remote_args())
        assert command[:2] == ["submit", "--target"]
        assert "--worker" in command and "worker-a" in command
        assert command.count("--unit") == 2
        assert "seed,2" in command
        assert "--consent" in command

    def test_remote_pack_requires_generator_metadata(self) -> None:
        with self.assertRaisesRegex(UserError, "remote pack requires"):
            remote_bridge.command_args(_remote_args(
                operation="pack", service=None, job_name=None, product=None,
                repo_url=None, repo_ref=None, run_module=None, run_function=None,
            ))

    def test_remote_pull_maps_job_to_submission_id(self) -> None:
        command = remote_bridge.command_args(_remote_args(
            operation="pull", target="target", entrypoint="runner.ipynb",
            backend="kaggle", account=None, job="sub-1", dest="inbox/sub-1",
            unit=[], consent=None, smoke=False,
        ))
        assert command == [
            "fetch", "--target", "target", "--entrypoint", "runner.ipynb",
            "--submission-id", "sub-1", "--dest", "inbox/sub-1", "--backend", "kaggle",
        ]

    def test_audit_check_drift_returns_exit_three_without_mutation(self) -> None:
        workspace = _workspace(self.new_tmp())
        (workspace / "skills/skill-audit/references/probes/skill-audit.subcommands.json").write_text("{}")
        self.patch(audit_bridge, "run_script", lambda *args, **kwargs: subprocess.CompletedProcess([], 0, "audit ok\n", ""))
        self.patch(audit_bridge, "check_generated", lambda *args, **kwargs: [".pi/APPEND_SYSTEM.md"])
        result = audit_bridge.execute(workspace, check_drift=True)
        assert result == DRIFT_ERROR

    # Phase 1: Fixture Foundation (tasks 1.1-1.2)

    def test_manifest_helper_includes_kaggle_and_slurm_shapes(self) -> None:
        workspace = _workspace(self.new_tmp())
        _write_local_manifest(workspace)
        data = config.load_papersmith_yaml(workspace)
        targets = data["compute_targets"]["targets"]
        assert {"local", "kaggle-gpu-pool", "slurm-cluster"} <= set(targets)
        kaggle = targets["kaggle-gpu-pool"]
        assert kaggle["provider"] == "kaggle"
        assert kaggle["account_pool"] == "default"
        assert kaggle["accelerator"] == "GPU_T4_X2"
        assert kaggle["internet_access"] is True
        assert kaggle["max_timeout_hours"] == 9
        assert kaggle["auto_pull_artifacts"] is True
        slurm = targets["slurm-cluster"]
        assert slurm["provider"] == "remote-ssh"
        assert slurm["host"] == "hpc.university.edu"
        assert slurm["partition"] == "gpu-a100"
        assert slurm["walltime"] == "12:00:00"
        profiles = data["execution_profiles"]
        assert profiles["kaggle-train"]["target"] == "kaggle-gpu-pool"
        assert profiles["slurm-train"]["target"] == "slurm-cluster"

    def test_hermetic_mock_idiom_seals_all_seams(self) -> None:
        workspace = _workspace(self.new_tmp())
        _write_local_manifest(workspace)

        def _fail_if_called(*args, **kwargs):
            raise AssertionError("hermetic boundary breached: subprocess dispatched")

        with mock.patch.object(executor.subprocess, "run", _fail_if_called):
            with mock.patch.object(target.subprocess, "run", _fail_if_called):
                with mock.patch.object(target, "run_script", _fail_if_called):
                    with mock.patch.object(python_bridge, "run_script", _fail_if_called):
                        with mock.patch.object(shutil, "which", return_value="/usr/bin/python"):
                            assert shutil.which("python") == "/usr/bin/python"
                            code, result = target.check_target(workspace, "local")
                            assert code == SUCCESS
                            assert result["reachable"] is True
                            dry = executor.run_profile(workspace, "smoke", dry_run=True)
                            assert dry["status"] == "ok"
                            assert ledger.read(workspace)[-1]["dry_run"] is True

    # Phase 2: Target Check/Set Matrix (tasks 2.1-2.4)

    def test_target_check_local_unknown_and_unsupported(self) -> None:
        workspace = _workspace(self.new_tmp())
        _write_local_manifest(workspace)
        with mock.patch.object(shutil, "which", return_value="/usr/bin/python"):
            code, result = target.check_target(workspace, "local")
            assert code == SUCCESS
            assert result["name"] == "local"
            assert result["provider"] == "local"
            assert result["reachable"] is True
        with mock.patch.object(shutil, "which", return_value=None):
            code, result = target.check_target(workspace, "local")
            assert code == SUCCESS
            assert result["reachable"] is True
        with self.assertRaisesRegex(UserError, "unknown compute target"):
            target.check_target(workspace, "does-not-exist")
        fake_yaml = {
            "compute_targets": {
                "default": "weird-cloud",
                "targets": {"weird-cloud": {"provider": "quantum"}},
            }
        }
        with mock.patch.object(config, "load_papersmith_yaml", lambda *args, **kwargs: fake_yaml):
            with self.assertRaisesRegex(UserError, "unsupported target provider"):
                target.check_target(workspace, "weird-cloud")

    def test_target_check_kaggle_up_and_down(self) -> None:
        workspace = _workspace(self.new_tmp())
        _write_local_manifest(workspace)
        seen: dict = {}

        def _fake_ok(root, script, args=(), **kwargs):
            seen["args"] = list(args)
            seen["script"] = str(script)
            return subprocess.CompletedProcess(args=list(args), returncode=0, stdout='{"ok": true}\n', stderr="")

        with mock.patch.object(target, "run_script", _fake_ok):
            with mock.patch.object(python_bridge, "run_script", _fake_ok):
                code, result = target.check_target(workspace, "kaggle-gpu-pool")
                assert code == SUCCESS
                assert result["reachable"] is True
                assert result["provider"] == "kaggle"
                assert seen["args"] == ["list", "--json"]
                assert seen["script"].endswith("accounts_cli.py")

        def _fake_down(root, script, args=(), **kwargs):
            return subprocess.CompletedProcess(args=list(args), returncode=1, stdout="", stderr="auth failed\n")

        with mock.patch.object(target, "run_script", _fake_down):
            with mock.patch.object(python_bridge, "run_script", _fake_down):
                code, result = target.check_target(workspace, "kaggle-gpu-pool")
                assert code == EXECUTION_ERROR
                assert result["reachable"] is False
                assert "auth failed" in result["detail"]

    def test_target_check_ssh_up_down_and_missing_host(self) -> None:
        workspace = _workspace(self.new_tmp())
        _write_local_manifest(workspace)
        seen: dict = {}

        def _fake_ok(*args, **kwargs):
            seen["argv"] = list(args[0])
            return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="", stderr="")

        with mock.patch.object(target.subprocess, "run", _fake_ok):
            code, result = target.check_target(workspace, "slurm-cluster")
            assert code == SUCCESS
            assert result["reachable"] is True
            assert seen["argv"][0] == "ssh"
            assert "hpc.university.edu" in seen["argv"]
            assert "true" in seen["argv"]

        def _fake_down(*args, **kwargs):
            return subprocess.CompletedProcess(args=args[0], returncode=1, stdout="", stderr="timeout\n")

        with mock.patch.object(target.subprocess, "run", _fake_down):
            code, result = target.check_target(workspace, "slurm-cluster")
            assert code == EXECUTION_ERROR
            assert result["reachable"] is False

        broken = _workspace(self.new_tmp())
        _write_broken_ssh_manifest(broken)

        def _must_not_run(*args, **kwargs):
            raise AssertionError("missing host must refuse before ssh")

        with mock.patch.object(target.subprocess, "run", _must_not_run):
            with self.assertRaisesRegex(UserError, "has no host"):
                target.check_target(broken, "broken-ssh")

    def test_target_set_persistence_round_trip(self) -> None:
        workspace = _workspace(self.new_tmp())
        selected = target.set_target(workspace, "slurm-cluster")
        assert selected == {"name": "slurm-cluster", "provider": "remote-ssh"}
        assert config.load_workspace_config(workspace)["execution_engine"]["active_compute_target"] == "slurm-cluster"
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            assert main(["target", "set", "kaggle-gpu-pool", str(workspace)]) == SUCCESS
        assert "kaggle-gpu-pool" in buffer.getvalue()
        assert config.load_workspace_config(workspace)["execution_engine"]["active_compute_target"] == "kaggle-gpu-pool"

    # Phase 3: Run Dispatch Matrix (tasks 3.1-3.5)

    def test_run_profile_local_failure_mapping(self) -> None:
        workspace = _workspace(self.new_tmp())
        _write_local_manifest(workspace)
        with mock.patch.object(
            executor.subprocess, "run",
            return_value=subprocess.CompletedProcess(args=["python"], returncode=0, stdout="", stderr=""),
        ):
            result = executor.run_profile(workspace, "smoke")
            assert result["status"] == "ok"
            assert result["jobs"][0]["exit"] == SUCCESS
        with mock.patch.object(
            executor.subprocess, "run",
            return_value=subprocess.CompletedProcess(args=["python"], returncode=1, stdout="", stderr="boom"),
        ):
            result = executor.run_profile(workspace, "smoke")
            assert result["status"] == "failed"
            assert result["jobs"][0]["exit"] == EXECUTION_ERROR
        with mock.patch.object(
            executor.subprocess, "run",
            side_effect=subprocess.TimeoutExpired(cmd=["python"], timeout=30),
        ):
            result = executor.run_profile(workspace, "smoke")
            assert result["status"] == "failed"
            assert result["jobs"][0]["exit"] == EXECUTION_ERROR
        with mock.patch.object(executor.subprocess, "run", side_effect=OSError("boom")):
            result = executor.run_profile(workspace, "smoke")
            assert result["status"] == "failed"
            assert result["jobs"][0]["exit"] == EXECUTION_ERROR

    def test_run_profile_kaggle_dry_run_and_consented_unit_forwarding(self) -> None:
        workspace = _workspace(self.new_tmp())
        _write_local_manifest(workspace, sharded=True)

        def _must_not_dispatch(*args, **kwargs):
            raise AssertionError("dry-run dispatched a subprocess")

        with mock.patch.object(executor.subprocess, "run", _must_not_dispatch):
            dry = executor.run_profile(workspace, "kaggle-train", dry_run=True, shard=0)
            assert dry["status"] == "ok"
            command = dry["jobs"][0]["command"]
            assert "submit" in command
            assert "--target" in command
            assert "--entrypoint" in command
            assert "--backend" in command
            backend = command[command.index("--backend") + 1]
            assert backend == "kaggle"
            entrypoint = command[command.index("--entrypoint") + 1]
            assert entrypoint.endswith("train.py")
            assert "--worker" not in command
            assert "--smoke" not in command

        captured: dict = {}

        def _fake_run(command, **kwargs):
            captured["argv"] = list(command)
            return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")

        with mock.patch.object(executor.subprocess, "run", _fake_run):
            result = executor.run_profile(workspace, "kaggle-train", shard=0, consent="tok123")
            assert result["status"] == "ok"
            argv = captured["argv"]
            assert "submit" in argv
            assert "--target" in argv
            assert "--entrypoint" in argv
            assert "--backend" in argv
            assert "--unit" in argv
            assert "11" in argv
            assert "--consent" in argv
            assert argv[argv.index("--consent") + 1] == "tok123"

        captured_none: dict = {}

        def _fake_run_none(command, **kwargs):
            captured_none["argv"] = list(command)
            return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")

        with mock.patch.object(executor.subprocess, "run", _fake_run_none):
            result = executor.run_profile(workspace, "kaggle-train", shard=1, consent=None)
            assert result["status"] == "ok"
            argv = captured_none["argv"]
            assert "submit" in argv
            assert "--consent" not in argv
            assert "--unit" in argv
            assert "22" in argv

    def test_run_profile_ssh_sbatch_argv_and_dispatch(self) -> None:
        workspace = _workspace(self.new_tmp())
        _write_local_manifest(workspace)
        dry = executor.run_profile(workspace, "slurm-train", dry_run=True)
        assert dry["status"] == "ok"
        command = dry["jobs"][0]["command"]
        assert command[0] == "ssh"
        assert "hpc.university.edu" in command
        assert "sbatch" in command
        assert "--partition" in command
        assert "gpu-a100" in command
        assert "--time" in command
        assert "12:00:00" in command
        assert "--wrap" in command
        captured: dict = {}

        def _fake_run(command, **kwargs):
            captured["argv"] = list(command)
            return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")

        with mock.patch.object(executor.subprocess, "run", _fake_run):
            result = executor.run_profile(workspace, "slurm-train", dry_run=False)
            assert result["status"] == "ok"
            assert captured["argv"][0] == "ssh"
            assert "sbatch" in captured["argv"]
        broken = _workspace(self.new_tmp())
        _write_broken_ssh_manifest(broken)
        with self.assertRaisesRegex(UserError, "requires host"):
            executor.run_profile(broken, "smoke", dry_run=True)

    def test_target_override_precedence_and_entrypoint_fallback(self) -> None:
        workspace = _workspace(self.new_tmp())
        _write_local_manifest(workspace)
        overridden = executor.run_profile(workspace, "smoke", target_override="kaggle-gpu-pool", dry_run=True)
        assert overridden["target"] == "kaggle-gpu-pool"
        assert overridden["jobs"][0]["provider"] == "kaggle"
        assert "submit" in overridden["jobs"][0]["command"]
        overridden_ssh = executor.run_profile(workspace, "smoke", target_override="slurm-cluster", dry_run=True)
        assert overridden_ssh["target"] == "slurm-cluster"
        assert overridden_ssh["jobs"][0]["command"][0] == "ssh"
        fallback_job = {
            "entrypoint": "echo hello world",
            "command": ["echo", "hello", "world"],
            "command_text": "echo hello world",
            "shard_value": None,
        }
        fallback = executor._remote_command(workspace, fallback_job, {"backend": "kaggle"}, consent=None)
        entrypoint = fallback[fallback.index("--entrypoint") + 1]
        assert entrypoint.endswith("runner.ipynb")
        normal_job = {
            "entrypoint": "python implementations/paper/src/train.py",
            "command": ["python", "implementations/paper/src/train.py"],
            "command_text": "python implementations/paper/src/train.py",
            "shard_value": None,
        }
        normal = executor._remote_command(workspace, normal_job, {"backend": "kaggle"}, consent="tok")
        entrypoint = normal[normal.index("--entrypoint") + 1]
        assert entrypoint.endswith("train.py")
        assert "--consent" in normal

    def test_failing_exit_ledger_rows(self) -> None:
        workspace = _workspace(self.new_tmp())
        _write_local_manifest(workspace)
        with mock.patch.object(
            executor.subprocess, "run",
            return_value=subprocess.CompletedProcess(args=["python"], returncode=1, stdout="", stderr="fail"),
        ):
            result = executor.run_profile(workspace, "smoke", dry_run=False)
            assert result["status"] == "failed"
            assert result["jobs"][0]["exit"] == EXECUTION_ERROR
        rows = ledger.read(workspace)
        assert rows[-1]["dry_run"] is False
        assert rows[-1]["exit"] == EXECUTION_ERROR
        assert rows[-1]["exit"] != 0
        assert rows[-1]["profile"] == "smoke"
        kaggle_workspace = _workspace(self.new_tmp())
        _write_local_manifest(kaggle_workspace)
        with mock.patch.object(
            executor.subprocess, "run",
            return_value=subprocess.CompletedProcess(args=["submit"], returncode=1, stdout="", stderr="remote fail"),
        ):
            result = executor.run_profile(kaggle_workspace, "kaggle-train", dry_run=False, consent="tok")
            assert result["status"] == "failed"
        rows = ledger.read(kaggle_workspace)
        assert rows[-1]["dry_run"] is False
        assert rows[-1]["exit"] != 0

    # Phase 4: CLI Wiring (task 4.1)

    def test_cli_main_wiring_for_target_and_run(self) -> None:
        workspace = _workspace(self.new_tmp())
        _write_local_manifest(workspace)
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            assert main(["target", "set", "slurm-cluster", str(workspace)]) == SUCCESS
        assert "slurm-cluster" in buffer.getvalue()
        with mock.patch.object(shutil, "which", return_value="/usr/bin/python"):
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                assert main(["target", "check", "local", str(workspace)]) == SUCCESS
            assert "reachable" in buffer.getvalue()

        def _must_not_dispatch(*args, **kwargs):
            raise AssertionError("dry-run dispatched a subprocess")

        with mock.patch.object(executor.subprocess, "run", _must_not_dispatch):
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                assert main([
                    "run", "smoke", "--target", "kaggle-gpu-pool",
                    "--consent", "tok123", "--dry-run", str(workspace),
                ]) == SUCCESS
            output = buffer.getvalue()
            assert '"dry_run": true' in output
            assert "submit" in output
            assert "tok123" in output
