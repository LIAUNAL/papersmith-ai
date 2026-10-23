"""Compute-target listing, selection, and connectivity checks."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from ..bridges.python import run_script
from ..core.exit_codes import EXECUTION_ERROR, SUCCESS
from ..errors import ExecutionError, UserError
from . import config


def ssh_destination(host: str | None, *, missing_message: str) -> str:
    """Accept one native SSH destination token, never options or whitespace/control characters."""
    if not isinstance(host, str) or not host:
        raise UserError(missing_message)
    if host.startswith("-") or any(
        char.isspace() or ord(char) < 32 or 127 <= ord(char) <= 159 for char in host
    ):
        raise UserError(
            "remote-ssh host must be a single destination token without a leading '-' or whitespace/control characters"
        )
    return host


def list_targets(workspace: str | Path = ".") -> list[dict]:
    root = Path(workspace).expanduser().resolve()
    yaml = config.load_papersmith_yaml(root)
    current = config.load_workspace_config(root)["execution_engine"]["active_compute_target"]
    return [
        {"name": name, "provider": target.get("provider"), "active": name == current}
        for name, target in yaml["compute_targets"]["targets"].items()
    ]


def set_target(workspace: str | Path, name: str) -> dict:
    root = Path(workspace).expanduser().resolve()
    yaml = config.load_papersmith_yaml(root)
    if name not in yaml["compute_targets"]["targets"]:
        raise UserError(f"unknown compute target: {name}")
    data = config.load_workspace_config(root)
    data["execution_engine"]["active_compute_target"] = name
    data["updated_at"] = config.utc_timestamp()
    config.write_json(root / ".papersmith" / "config.json", data)
    return {"name": name, "provider": yaml["compute_targets"]["targets"][name]["provider"]}


def check_target(workspace: str | Path, name: str | None = None) -> tuple[int, dict]:
    root = Path(workspace).expanduser().resolve()
    yaml = config.load_papersmith_yaml(root)
    data = config.load_workspace_config(root)
    target_name = name or data["execution_engine"]["active_compute_target"]
    target = yaml["compute_targets"]["targets"].get(target_name)
    if target is None:
        raise UserError(f"unknown compute target: {target_name}")
    provider = target["provider"]
    if provider == "local":
        return SUCCESS, {"name": target_name, "provider": provider, "reachable": shutil.which("python") is not None or bool(sys.executable)}
    if provider == "kaggle":
        script = root / "skills/kaggle-accounts/scripts/accounts_cli.py"
        result = run_script(root, script, ["list", "--json"], timeout=30)
        return (SUCCESS if result.returncode == 0 else EXECUTION_ERROR), {
            "name": target_name, "provider": provider, "reachable": result.returncode == 0,
            "detail": (result.stdout or result.stderr).strip(),
        }
    if provider == "remote-ssh":
        host = ssh_destination(target.get("host"), missing_message=f"target {target_name} has no host")
        result = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", "--", host, "true"],
            cwd=root, capture_output=True, text=True, check=False,
        )
        return (SUCCESS if result.returncode == 0 else EXECUTION_ERROR), {
            "name": target_name, "provider": provider, "reachable": result.returncode == 0,
            "detail": (result.stderr or result.stdout).strip(),
        }
    raise UserError(f"unsupported target provider: {provider}")


def register(subparsers) -> None:
    parser = subparsers.add_parser("target", help="inspect and select compute targets")
    commands = parser.add_subparsers(dest="target_command", required=True)
    listed = commands.add_parser("list", help="list configured targets")
    listed.add_argument("directory", nargs="?", default=".", metavar="<dir>")
    listed.set_defaults(handler=run_cli)
    selected = commands.add_parser("set", help="select the default target")
    selected.add_argument("name")
    selected.add_argument("directory", nargs="?", default=".", metavar="<dir>")
    selected.set_defaults(handler=run_cli)
    checked = commands.add_parser("check", help="test target connectivity")
    checked.add_argument("name", nargs="?", default=None)
    checked.add_argument("directory", nargs="?", default=".", metavar="<dir>")
    checked.set_defaults(handler=run_cli)


def run_cli(args) -> int:
    if args.target_command == "list":
        for target in list_targets(args.directory):
            marker = " *" if target["active"] else ""
            print(f"{target['name']}: {target['provider']}{marker}")
        return SUCCESS
    if args.target_command == "set":
        target = set_target(args.directory, args.name)
        print(f"Active target: {target['name']} ({target['provider']})")
        return SUCCESS
    code, result = check_target(args.directory, args.name)
    print(result)
    return code
