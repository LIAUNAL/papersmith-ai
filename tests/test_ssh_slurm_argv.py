"""Issue #82: destination refusal and the actual SSH remote-shell boundary."""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

from papersmith.cli import main
from papersmith.core import executor, target
from papersmith.core import init as init_module
from papersmith.core.exit_codes import EXECUTION_ERROR, SUCCESS


def _workspace(root: Path, host: str | int | None = "cluster") -> Path:
    (root / ".papersmith").mkdir()
    data = init_module._default_config("paper", ["claude"], "cluster", "2026-10-18")
    (root / ".papersmith/config.json").write_text(json.dumps(data), encoding="utf-8")
    _manifest(root, host)
    return root


def _manifest(
    root: Path,
    host: str | int | None,
    entrypoint: str = "printf hello",
    *,
    partition: str = "gpu",
    walltime: str = "01:00:00",
) -> None:
    host_yaml = (
        json.dumps(host, ensure_ascii=False).replace("\\u0000", "\x00").replace("\\u001b", "\x1b")
    )
    (root / "papersmith.yaml").write_text(
        'version: "1"\nname: "paper"\ntitle: "SSH regression"\n'
        'compute_targets:\n  default: "cluster"\n  targets:\n    cluster:\n'
        f'      provider: "remote-ssh"\n      host: {host_yaml}\n'
        f"      partition: {json.dumps(partition)}\n      walltime: {json.dumps(walltime)}\n"
        'execution_profiles:\n  smoke:\n    target: "cluster"\n'
        f"    entrypoint: {json.dumps(entrypoint)}\n",
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    "host",
    [
        "-V",
        "--help",
        "-oBatchMode=yes",
        "two hosts",
        " host",
        "host\tname",
        "host\nname",
        "host\x00",
        "host\x1b",
        "host\x7f",
        "host\x85",
        "",
        None,
        42,
    ],
)
@pytest.mark.parametrize("operation", ["check", "run", "dry-run"])
def test_ssh_target_rejects_option_like_hosts(tmp_path, capsys, host, operation) -> None:
    # Given: malformed configuration and a narrow, inert process seam.
    root = _workspace(tmp_path, host)
    argv = (
        ["target", "check", "cluster", str(root)]
        if operation == "check"
        else ["run", "smoke", str(root)] + (["--dry-run"] if operation == "dry-run" else [])
    )
    with mock.patch.object(
        subprocess,
        "run",
        return_value=subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
    ) as launch:
        # When: the real CLI resolves and dispatches the target.
        code = main(argv)
    # Then: the established error envelope precedes every remote launch.
    assert code == 1
    assert capsys.readouterr().err.startswith("papersmith: error:")
    launch.assert_not_called()


@pytest.mark.parametrize(
    "host",
    [
        "cluster",
        "hpc.example.edu",
        "alice@cluster",
        "192.0.2.1",
        "2001:db8::1",
        "alice@2001:db8::1",
        "ssh://alice@cluster:2222",
        "ssh://alice@[2001:db8::1]:2222",
    ],
)
@pytest.mark.parametrize("operation", ["check", "run", "dry-run"])
def test_supported_remote_targets_keep_expected_dispatch(tmp_path, host, operation) -> None:
    # Given: native SSH destinations, including the native URI port notation.
    root = _workspace(tmp_path, host)
    with mock.patch.object(
        subprocess,
        "run",
        return_value=subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
    ) as launch:
        # When: target check or execution resolves the configured destination.
        if operation == "check":
            code, result = target.check_target(root, "cluster")
            command = launch.call_args.args[0]
            assert code == SUCCESS and result["reachable"] is True
        else:
            result = executor.run_profile(root, "smoke", dry_run=operation == "dry-run")
            command = result["jobs"][0]["command"]
            assert result["status"] == "ok"
        # Then: no destination is reinterpreted as SSH options.
        assert command[command.index(host) - 1] == "--"
        if operation == "dry-run":
            launch.assert_not_called()
        else:
            launch.assert_called_once()
        if operation != "check":
            assert shlex.split(command[-1]) == [
                "sbatch",
                "--partition",
                "gpu",
                "--time",
                "01:00:00",
                "--wrap",
                "printf hello",
            ]


@pytest.mark.parametrize("shell_job", [False, True])
@pytest.mark.parametrize("options", [False, True])
def test_ssh_slurm_wrap_preserves_command_semantics(tmp_path, shell_job, options) -> None:
    # Given: recorders only; a damaged wrap is recorded but NEVER executed.
    root = _workspace(tmp_path)
    arguments = ["two words", "single'quote", 'double"quote', "$LITERAL", ";", "*", "$(literal)"]
    recorder = root / "job.py"
    recorder.write_text(
        "import json, pathlib, sys\npathlib.Path('job.json').write_text(json.dumps(sys.argv[1:]))\n"
    )
    command = (
        ["sh", "-c", "printf '%s' 'intentional shell' > intentional.txt"]
        if shell_job
        else [sys.executable, str(recorder), *arguments]
    )
    entrypoint = shlex.join(command)
    # Quotes keep the unfixed outer shell inert while still exposing quote loss.
    partition = "queue 'space;$VAR*$(literal)'" if options else "gpu"
    walltime = "time 'space;$VAR*$(literal)'" if options else "01:00:00"
    _manifest(root, "cluster", entrypoint, partition=partition, walltime=walltime)
    expected = ["--partition", partition, "--time", walltime, "--wrap", entrypoint]
    (root / "expected.json").write_text(json.dumps(expected))
    stub = root / "sbatch.py"
    stub.write_text(
        "import json, pathlib, subprocess, sys\n"
        "args = sys.argv[1:]\n"
        "pathlib.Path('sbatch.json').write_text(json.dumps(args))\n"
        "if args == json.loads(pathlib.Path('expected.json').read_text()):\n"
        "    sys.exit(subprocess.run(['/bin/sh', '-c', args[-1]], check=False).returncode)\n"
    )
    real_run = subprocess.run

    def fake_ssh(argv, **kwargs):
        assert argv[0] == "ssh"
        remote = argv[argv.index("cluster") + 1 :]
        prefix = f'sbatch() {{ {shlex.join([sys.executable, str(stub)])} "$@"; }}; '
        # SSH joins remote arguments with SPACES, not shlex.join.
        return real_run(["/bin/sh", "-c", prefix + " ".join(remote)], **kwargs)

    # When: the real executor crosses an SSH-like shell into the sbatch recorder.
    with mock.patch.object(subprocess, "run", fake_ssh):
        result = executor.run_profile(root, "smoke")
    # Then: options and wrap arrive byte-exact, and only the intended job runs.
    assert json.loads((root / "sbatch.json").read_text()) == expected
    assert result["status"] == "ok"
    if shell_job:
        assert (root / "intentional.txt").read_text() == "intentional shell"
    else:
        assert json.loads((root / "job.json").read_text()) == arguments


@pytest.mark.parametrize("returncode", [0, 1, 255])
def test_remote_return_mapping(tmp_path, returncode) -> None:
    # Given: a successful SSH check/submission or a transport failure.
    root = _workspace(tmp_path)
    with mock.patch.object(
        subprocess,
        "run",
        return_value=subprocess.CompletedProcess(
            args=[], returncode=returncode, stdout="", stderr="transport detail"
        ),
    ):
        # When: check and run map the process result.
        code, checked = target.check_target(root, "cluster")
        result = executor.run_profile(root, "smoke")
    # Then: transport errors remain execution errors, not user errors.
    expected = SUCCESS if returncode == 0 else EXECUTION_ERROR
    assert code == result["jobs"][0]["exit"] == expected
    assert checked["reachable"] == (returncode == 0)
