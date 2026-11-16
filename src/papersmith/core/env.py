"""Environment management commands (`smith env`).

Provides CLI subcommands to provision, check, and clean the workspace's
micromamba Python environment through its local `scripts/setup_env.py`.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from ..core.exit_codes import EXECUTION_ERROR, SUCCESS
from ..errors import UserError


PROVISIONING_SCRIPT = Path("scripts") / "setup_env.py"


def resolve_provisioner(workspace: str | Path = ".") -> tuple[Path, Path]:
    root = Path(workspace).expanduser().resolve()
    script = root / PROVISIONING_SCRIPT
    if not script.is_file():
        raise UserError(
            f"workspace {root} has no provisioning script at {PROVISIONING_SCRIPT}; "
            "run `smith upgrade` to restore the kit"
        )
    return root, script


def run_env_tool(workspace: str | Path, command: str, extra_args: list[str] | None = None) -> int:
    root, script = resolve_provisioner(workspace)
    interpreter = sys.executable or shutil.which("python3") or shutil.which("python") or "python"
    args = [interpreter, str(script), command, *(extra_args or [])]
    try:
        proc = subprocess.run(args, cwd=root, check=False)
        return proc.returncode
    except OSError as exc:
        raise UserError(f"could not execute environment provisioning: {exc}") from exc


def register(subparsers) -> None:
    parser = subparsers.add_parser("env", help="manage the workspace's micromamba Python environment")
    commands = parser.add_subparsers(dest="env_command", required=True)

    install = commands.add_parser("install", help="create or update the isolated micromamba environment")
    install.add_argument("--cpu", action="store_true", help="force CPU PyTorch")
    install.add_argument("--cuda", action="store_true", help="force CUDA PyTorch")
    install.add_argument("--rocm", action="store_true",
                         help="force AMD's ROCm PyTorch wheels for the detected gfx target")
    install.add_argument(
        "--no-ingestion", action="store_true",
        help="skip docling and heavy ingestion packages; fast pypdfium2 stays",
    )
    install.add_argument("directory", nargs="?", default=".", metavar="<dir>")
    install.set_defaults(handler=run_cli)

    status = commands.add_parser("status", help="show detected hardware and micromamba status")
    status.add_argument("directory", nargs="?", default=".", metavar="<dir>")
    status.set_defaults(handler=run_cli)

    clean = commands.add_parser("clean", help="remove the micromamba environment")
    clean.add_argument("--full", action="store_true", help="also delete bootstrapped micromamba binary")
    clean.add_argument("directory", nargs="?", default=".", metavar="<dir>")
    clean.set_defaults(handler=run_cli)


def run_cli(args: argparse.Namespace) -> int:
    cmd = args.env_command
    directory = getattr(args, "directory", ".")
    extra: list[str] = []
    if cmd == "install":
        if getattr(args, "cpu", False):
            extra.append("--cpu")
        if getattr(args, "cuda", False):
            extra.append("--cuda")
        if getattr(args, "rocm", False):
            extra.append("--rocm")
        if getattr(args, "no_ingestion", False):
            extra.append("--no-ingestion")
    elif cmd == "clean":
        if getattr(args, "full", False):
            extra.append("--full")

    code = run_env_tool(directory, cmd, extra)
    return SUCCESS if code == 0 else EXECUTION_ERROR
