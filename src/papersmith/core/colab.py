"""``smith colab login|status`` — the official Colab CLI, signed in once per team owner.

Each team member with a Colab account (``smith team add --colab``) gets a
private state directory, ``$XDG_CONFIG_HOME/papersmith/colab/<owner>/``
(``0700``). ``google-colab-cli`` (pinned at :data:`PINNED_VERSION`) keeps its
oauth token at ``~/.config/colab-cli/token.json`` resolved from ``HOME`` at
import time; its global ``--config PATH`` names the session STATE FILE
(``sessions.json``) and does not move the token (measured against the 0.7.5
source and ``colab --help``; the remote-execution Colab adapter records the
same in the 0.6.0 source). So an owner's isolation is the child's ``HOME``: every invocation
runs ``HOME=<configDir> colab --config <configDir>/.config/colab-cli/sessions.json
<command>``, and the token lands at ``<configDir>/.config/colab-cli/token.json``.

**Nothing here opens, copies or prints a file inside a configDir.** The token
and ``sessions.json`` are credential-grade; papersmith only creates the
directory, checks that it exists, and reads the CLI's own exit status. The
child receives ``PATH``, ``HOME`` (and ``USERPROFILE`` on Windows, where
``expanduser`` reads it) plus the terminal's ``TERM``/``LANG``; nothing else
from this process's environment.

``login`` runs the CLI's own interactive consent (:data:`LOGIN_ARGS`): the CLI
prints a Google sign-in URL, the owner approves it in a browser signed in as
their own Google account, and pastes the code back. ``status`` asks the same
command with stdin closed and a short timeout: exit 0 means the CLI holds a
working sign-in for that owner, anything else means it does not.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ..errors import UserError
from . import team
from .kaggle_mcp import detect_environment

CLI_NAME = "colab"
PINNED_VERSION = "0.6.0"
#: The install line ``skills/remote-execution/SKILL.md`` documents; the two are
#: the same pin and must change together.
INSTALL_COMMAND = (f'uv tool install --force --python 3.14 "google-colab-cli=={PINNED_VERSION}" '
                   '--with "jupyter-kernel-client<1"')
#: The login ritual: any command that reaches the Colab API makes the CLI run
#: its oauth2 consent when it holds no valid token. ``sessions`` lists the
#: owner's sessions and changes nothing on the service, so it is the one used
#: to sign in and, with stdin closed, to ask whether the sign-in still works.
LOGIN_ARGS = ("sessions",)
STATUS_ARGS = LOGIN_ARGS
VERSION_ARGS = ("version",)
STATUS_TIMEOUT_SECONDS = 20
VERSION_TIMEOUT_SECONDS = 10
#: The CLI's own layout under the HOME it is given.
STATE_SUBDIR = (".config", "colab-cli")
FORWARDED_ENV = ("PATH", "TERM", "LANG", "LC_ALL")


def sessions_file(config_dir: Path) -> Path:
    """The path handed to ``--config``. A name only: it is never opened here."""
    return Path(config_dir, *STATE_SUBDIR, "sessions.json")


def child_env(config_dir: Path) -> dict[str, str]:
    env = {key: os.environ[key] for key in FORWARDED_ENV if os.environ.get(key)}
    env["HOME"] = str(config_dir)
    if os.name == "nt":
        env["USERPROFILE"] = str(config_dir)
    return env


def cli_argv(executable: str, config_dir: Path, args: tuple[str, ...]) -> list[str]:
    return [executable, "--config", str(sessions_file(config_dir)), *args]


def shell_command(config_dir: Path, args: tuple[str, ...] = LOGIN_ARGS) -> str:
    """The same invocation as a line a person can paste into their own shell."""
    argv = cli_argv(CLI_NAME, config_dir, args)
    if os.name == "nt":
        quoted = " ".join(f'"{part}"' if " " in part else part for part in argv)
        return f'$env:USERPROFILE = "{config_dir}"; $env:HOME = "{config_dir}"; {quoted}'
    return f"HOME={shlex.quote(str(config_dir))} {shlex.join(argv)}"


def find_cli() -> str | None:
    return shutil.which(CLI_NAME)


def cli_version(executable: str) -> str | None:
    env = {key: os.environ[key] for key in ("PATH", "HOME") if os.environ.get(key)}
    try:
        completed = subprocess.run([executable, *VERSION_ARGS], env=env, stdin=subprocess.DEVNULL,
                                   capture_output=True, text=True, timeout=VERSION_TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.search(r"(\d+\.\d+\.\d+\S*)", completed.stdout or "")
    return match.group(1) if completed.returncode == 0 and match else None


def signed_in(executable: str, config_dir: Path) -> tuple[str, str]:
    """``("yes"|"no"|"unknown", detail)`` from the CLI's own exit status only.

    stdin is closed, so a missing sign-in makes the CLI's consent prompt abort
    instead of waiting; its output (which then carries a sign-in URL) is
    discarded unread.
    """
    try:
        completed = subprocess.run(cli_argv(executable, config_dir, STATUS_ARGS),
                                   env=child_env(config_dir), stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   timeout=STATUS_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return "unknown", f"the CLI did not answer within {STATUS_TIMEOUT_SECONDS} s"
    except OSError as exc:
        return "unknown", f"the CLI could not start ({exc.strerror or exc})"
    if completed.returncode == 0:
        return "yes", f"`colab {' '.join(STATUS_ARGS)}` succeeded"
    return "no", f"`colab {' '.join(STATUS_ARGS)}` exited {completed.returncode}"


def _colab_members(root: Path, owner: str | None) -> list[dict[str, Any]]:
    if owner is not None:
        member = team.find(root, owner)
        if team.colab_account(member) is None:
            raise UserError(f"owner {owner!r} lists no Colab account; add one with "
                            f"`smith team remove --owner {owner}` and `smith team add ... --colab`")
        return [member]
    return [m for m in team.members(root) if team.colab_account(m) is not None]


def _config_dir(member: dict[str, Any]) -> Path:
    raw = (team.colab_account(member) or {}).get("configDir")
    if not isinstance(raw, str) or not raw or not Path(raw).is_absolute():
        raise UserError(f"owner {member.get('owner')!r} has no absolute Colab configDir in {team.TEAM_FILE}")
    return Path(raw)


def login_instructions(member: dict[str, Any], env: dict[str, str]) -> list[str]:
    name = member.get("displayName") or member.get("owner")
    browser = {
        "wsl": "open it in a browser on Windows (WSL cannot open one itself)",
        "windows": "open it in your browser",
        "macos": "open it in a browser (Cmd-click it in most terminals)",
    }.get(env["system"], "open it in any browser, on this machine or another one")
    return [
        f"Signing in {name}'s own Colab account (owner {member.get('owner')}).",
        f"The Colab CLI prints a Google sign-in URL: {browser}, sign in as {name} — never as "
        "another person — approve, and paste the authorization code back here.",
        "One account per person per service: this sign-in is stored only in this owner's state "
        "directory and papersmith never reads it.",
    ]


# --- CLI --------------------------------------------------------------------


def register(subparsers) -> None:
    parser = subparsers.add_parser(
        "colab", help="sign team owners in to the official Colab CLI and report their state")
    commands = parser.add_subparsers(dest="colab_command", required=True)
    login = commands.add_parser("login", help="run the Colab CLI's own consent for one owner")
    login.add_argument("--owner", required=True)
    login.add_argument("--print-command", action="store_true",
                       help="print the sign-in command for your own terminal and run nothing")
    login.add_argument("--workspace", default=None, help="workspace root (default: current directory)")
    login.set_defaults(handler=run_login)
    status = commands.add_parser("status", help="per owner: CLI, state directory, sign-in, tier")
    status.add_argument("--owner", default=None)
    status.add_argument("--json", action="store_true", help="machine-readable output")
    status.add_argument("--workspace", default=None, help="workspace root (default: current directory)")
    status.set_defaults(handler=run_status)


def run_login(args) -> int:
    root = team.workspace_root(args.workspace)
    [member] = _colab_members(root, args.owner)
    config_dir = _config_dir(member)
    env = detect_environment()
    if args.print_command:
        print(shell_command(config_dir))
        return 0
    executable = find_cli()
    if executable is None:
        raise UserError(f"the `{CLI_NAME}` CLI is not on PATH; install the pinned version with: "
                        f"{INSTALL_COMMAND}")
    team._make_private_dir(config_dir)
    for line in login_instructions(member, env):
        print(line)
    if env["note"]:
        print(f"note: {env['note']}")
    print(f"running: {shell_command(config_dir)}", flush=True)
    completed = subprocess.run(cli_argv(executable, config_dir, LOGIN_ARGS), env=child_env(config_dir))
    if completed.returncode != 0:
        print(f"the Colab CLI exited {completed.returncode}; nothing was signed in. "
              f"Retry with `smith colab login --owner {member['owner']}`.")
        return completed.returncode or 1
    print(f"signed in: {member['owner']}. Check any time with `smith colab status --owner {member['owner']}`.")
    return 0


def run_status(args) -> int:
    root = team.workspace_root(args.workspace)
    rows_members = _colab_members(root, args.owner)
    env = detect_environment()
    executable = find_cli()
    version = cli_version(executable) if executable else None
    cli = {"found": executable is not None, "path": executable, "version": version,
           "pinned": PINNED_VERSION, "install": INSTALL_COMMAND}
    rows = []
    for member in rows_members:
        config_dir = _config_dir(member)
        tier = (team.colab_account(member) or {}).get("tier")
        exists = config_dir.is_dir() and not config_dir.is_symlink()
        if not exists:
            state, detail = "no", "state directory missing; run `smith colab login`"
        elif executable is None:
            state, detail = "unknown", "the CLI is not installed"
        else:
            state, detail = signed_in(executable, config_dir)
        rows.append({"owner": member.get("owner"), "displayName": member.get("displayName"),
                     "configDir": str(config_dir), "configDirExists": exists,
                     "signedIn": state, "detail": detail, "tier": tier,
                     "splitCampaignEligible": team.split_eligible(tier)})
    if args.json:
        print(json.dumps({"cli": cli, "owners": rows, "environment": env["system"]}, indent=2,
                         ensure_ascii=False))
        return 0
    if executable is None:
        print(f"colab CLI: not found on PATH; install: {INSTALL_COMMAND}")
    else:
        drift = "" if version == PINNED_VERSION else f" (pinned {PINNED_VERSION})"
        print(f"colab CLI: {executable}, version {version or 'unknown'}{drift}")
    if not rows:
        print("No team owner lists a Colab account; add one with "
              "`smith team add --owner <slug> --name \"<display>\" --colab --colab-tier <tier> --attest`.")
    for row in rows:
        signed = {"yes": "signed in", "no": "not signed in"}.get(row["signedIn"], "sign-in unknown")
        split = "split campaigns: eligible" if row["splitCampaignEligible"] else \
            "split campaigns: not eligible (free tier: interactive work only)"
        print(f"  {row['owner']}: {signed} ({row['detail']}); tier {row['tier']}; {split}")
        if row["signedIn"] != "yes":
            print(f"    sign in: smith colab login --owner {row['owner']}")
    print(f"environment: {env['system']}, shell {env['shell']}")
    return 0
