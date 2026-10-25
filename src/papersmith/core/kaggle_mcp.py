"""``smith mcp kaggle`` — activate Kaggle's official MCP server for this user.

The workspace MCP files (see ``generators.ensure_mcp_servers``) name the
server and read its token from :data:`TOKEN_ENV`; no project file ever holds
the token. ``activate`` stores it once per user, outside every workspace, where
Kaggle's own client keeps it: ``~/.kaggle/access_token`` (directory ``0700``,
file ``0600`` on POSIX), so the same token also serves the ``kaggle`` CLI and
``kagglesdk``. A token the official client already left there (or in
``access_token.txt``) is used as is, and the location an earlier papersmith
release used (``$XDG_CONFIG_HOME/papersmith/kaggle-mcp-token``) still reads.

The command center injects the token into the sessions its CLI assistant
starts when :data:`TOKEN_ENV` is not already exported
(``skills/_core/command_center/terminal.py``, which mirrors
:func:`token_candidates` and :func:`detect_environment`; tests hold the two
equal). On POSIX a file that is a symlink, is not a regular file, belongs to
someone else or is readable by group or others is never used. Native Windows
has no POSIX mode bits, so there the user profile's own ACL is what protects it.

Every instruction this module prints is derived from the running environment
(:func:`detect_environment`): macOS, Linux, WSL or Windows, the login shell,
the user and the real token path — never a fixed string.
"""

from __future__ import annotations

import getpass
import json
import os
import platform
import shutil
import stat
import sys
import urllib.error
import urllib.request
from pathlib import Path

from ..errors import UserError
from ..generators import KAGGLE_MCP_URL, KAGGLE_TOKEN_ENV, MCP_CONFIG_FILES, ensure_mcp_servers

TOKEN_ENV = KAGGLE_TOKEN_ENV
#: Kaggle's official client reads the token here (kaggle-api, "Generate New Token").
OFFICIAL_DIR = ".kaggle"
OFFICIAL_FILES = ("access_token", "access_token.txt")
LEGACY_FILENAME = "kaggle-mcp-token"
TOKEN_PAGE = "https://www.kaggle.com/settings"
#: An account tool that answers only with a valid token and changes nothing.
VERIFY_TOOL = "get_accelerator_quota"
VERIFY_TIMEOUT_SECONDS = 20


class _RefuseRedirects(urllib.request.HTTPRedirectHandler):
    """Follow no redirect: the verify request carries the token, and a redirect
    would hand it to whatever host ``Location`` names. Returning ``None`` makes
    urllib raise the 3xx as an ``HTTPError`` (#106)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


#: The only opener a request carrying the Kaggle token goes through.
_OPENER = urllib.request.build_opener(_RefuseRedirects)


def token_path() -> Path:
    """Where ``activate`` writes: the official client's own file."""
    return Path.home() / OFFICIAL_DIR / OFFICIAL_FILES[0]


def token_candidates() -> list[Path]:
    """Every file a token is read from, first match wins."""
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    official = [Path.home() / OFFICIAL_DIR / name for name in OFFICIAL_FILES]
    return [*official, Path(base).expanduser() / "papersmith" / LEGACY_FILENAME]


def _posix() -> bool:
    return os.name != "nt"


def token_file_problem(path: Path | None = None) -> str | None:
    """Why the token file may not be used, or ``None`` when it may."""
    path = path or token_path()
    try:
        info = path.lstat()
    except FileNotFoundError:
        return "absent"
    except OSError as exc:
        return f"unreadable ({exc.strerror})"
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        return "insecure: not a regular file"
    if _posix():
        if hasattr(os, "getuid") and info.st_uid != os.getuid():
            return "insecure: owned by another user"
        if stat.S_IMODE(info.st_mode) & 0o077:
            return f"insecure: mode {stat.S_IMODE(info.st_mode):04o}, expected 0600"
        if path.parent.is_symlink():
            return "insecure: its directory is a symlink"
    return None


def _read_one(path: Path) -> str | None:
    if token_file_problem(path) is not None:
        return None
    try:
        token = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return None
    return token or None


def stored_token() -> tuple[str, Path] | tuple[None, None]:
    for path in token_candidates():
        token = _read_one(path)
        if token:
            return token, path
    return None, None


def read_token(path: Path | None = None) -> str | None:
    if path is not None:
        return _read_one(path)
    return stored_token()[0]


def store_token(token: str, *, replace: bool = False) -> Path:
    path = token_path()
    if path.parent.is_symlink():
        raise UserError(f"{path.parent} is a symlink; refusing to store a token through it")
    # Read the raw bytes, not the security-filtered token: an existing token
    # in a too-open file or behind a symlink is still someone's token.
    try:
        current = path.read_text(encoding="utf-8").strip() if (path.exists() or path.is_symlink()) else ""
    except (OSError, UnicodeDecodeError):
        current = "<unreadable>"
    if current and current != token and not replace:
        raise UserError(f"{path} already holds a different Kaggle token (the official client's); "
                        "pass --replace to overwrite it")
    path.parent.mkdir(parents=True, exist_ok=True)
    if _posix():
        os.chmod(path.parent, 0o700)
    if path.is_symlink():
        path.unlink()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0), 0o600)
    # A pre-existing file keeps its old mode under O_CREAT: tighten it before
    # the token is written, never after.
    if _posix():
        os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(token + "\n")
    return path


def detect_environment() -> dict[str, str]:
    """The running system, shell, user and the commands that fit them."""
    if os.name == "nt" or sys.platform.startswith("win"):
        system = "windows"
    elif sys.platform == "darwin":
        system = "macos"
    elif os.environ.get("WSL_DISTRO_NAME") or "microsoft" in platform.release().lower():
        system = "wsl"
    else:
        system = "linux"
    if system == "windows":
        shell = "powershell"
    else:
        shell = Path(os.environ.get("SHELL") or "sh").name or "sh"
        if shell not in ("zsh", "bash", "fish"):
            shell = "sh"
    try:
        user = getpass.getuser()
    except Exception:  # KeyError/OSError, or ImportError without `pwd`
        user = os.environ.get("USER") or os.environ.get("USERNAME") or ""
    rel = f"~/{OFFICIAL_DIR}/{OFFICIAL_FILES[0]}"
    if shell == "powershell":
        export = f'$env:{TOKEN_ENV} = Get-Content "$HOME\\{OFFICIAL_DIR}\\{OFFICIAL_FILES[0]}"'
        profile = "$PROFILE"
    elif shell == "fish":
        export = f"set -gx {TOKEN_ENV} (cat {rel})"
        profile = "~/.config/fish/config.fish"
    else:
        export = f'export {TOKEN_ENV}="$(cat {rel})"'
        profile = {"zsh": "~/.zshrc", "bash": "~/.bash_profile" if system == "macos" else "~/.bashrc"}.get(
            shell, "~/.profile")
    note = {
        "wsl": "WSL: the token lives in the Linux filesystem of this distribution; run the dashboard "
               "and the agents inside WSL, not from Windows.",
        "windows": "Windows: the dashboard's CLI assistant needs macOS, Linux or WSL; on native Windows "
                   "run smith from PowerShell and set the variable there.",
    }.get(system, "")
    return {"system": system, "shell": shell, "user": user, "token_path": str(token_path()),
            "export_command": export, "profile_file": profile, "note": note}


def verify_token(token: str) -> tuple[bool, str]:
    """Call :data:`VERIFY_TOOL` with the token; ``(ok, detail)``, never the token."""
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": VERIFY_TOOL, "arguments": {"request": {}}}}).encode()
    request = urllib.request.Request(KAGGLE_MCP_URL, data=body, method="POST", headers={
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "Authorization": f"Bearer {token}",
    })
    try:
        with _OPENER.open(request, timeout=VERIFY_TIMEOUT_SECONDS) as response:
            text = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}"
    except (urllib.error.URLError, OSError) as exc:
        return False, f"unreachable: {getattr(exc, 'reason', exc)}"
    payload = next((line[5:].strip() for line in text.splitlines() if line.startswith("data:")), text)
    try:
        result = json.loads(payload).get("result") or {}
    except ValueError:
        return False, "unexpected response"
    detail = " ".join(part.get("text", "") for part in result.get("content", [])
                      if isinstance(part, dict))[:200]
    if result.get("isError"):
        return False, detail or "rejected"
    return True, "accelerator quota read"


def summary_lines(tools: list[str] | tuple[str, ...]) -> list[str]:
    """Offline lines for ``init`` and ``upgrade``: activation state and what is missing.
    No network call — a token is verified only when someone asks."""
    env = detect_environment()
    if os.environ.get(TOKEN_ENV):
        lines = [f"Kaggle MCP: activated through the exported {TOKEN_ENV}"]
    else:
        _token, path = stored_token()
        if path is not None:
            lines = [f"Kaggle MCP: activated, token at {path}"]
        else:
            lines = ["Kaggle MCP: registered, not activated; run `smith mcp kaggle activate` "
                     f"(or the dashboard's Experimentos tab) with a token from {TOKEN_PAGE}"]
    bridged = [tool for tool in tools if tool in ("pi", "antigravity")]
    if bridged and shutil.which("npx") is None:
        lines.append(f"Kaggle MCP: `npx` not found; {', '.join(bridged)} reach the server through "
                     "`npx mcp-remote`, so install Node.js to use it there")
    if env["note"]:
        lines.append(f"Kaggle MCP: {env['note']}")
    return lines


def _workspace_tools(root: Path) -> list[str]:
    try:
        tools = json.loads((root / ".papersmith" / "config.json").read_text(encoding="utf-8"))["active_tools"]
    except (OSError, ValueError, KeyError, TypeError):
        tools = None
    if not isinstance(tools, list):
        return ["claude"]
    return [tool for tool in tools if isinstance(tool, str) and tool in MCP_CONFIG_FILES]


def register(subparsers) -> None:
    parser = subparsers.add_parser(
        "kaggle", help="activate Kaggle's official MCP server with a private token")
    commands = parser.add_subparsers(dest="kaggle_command", required=True)
    activate = commands.add_parser("activate", help="verify and store a KGAT_ token for this user")
    activate.add_argument("--token-stdin", action="store_true",
                          help="read the token from stdin instead of a hidden prompt")
    activate.add_argument("--no-verify", action="store_true",
                          help="store without calling Kaggle to check the token")
    activate.add_argument("--replace", action="store_true",
                          help="overwrite a different token already in ~/.kaggle/access_token")
    activate.add_argument("--workspace", default=None,
                          help="workspace whose MCP files get the kaggle entry (default: current directory)")
    activate.set_defaults(handler=run_activate)
    status = commands.add_parser("status", help="report whether the token is configured, never its value")
    status.add_argument("--verify", action="store_true", help="also check the token against Kaggle")
    status.set_defaults(handler=run_status)
    deactivate = commands.add_parser(
        "deactivate", help="remove the stored token files (the kaggle CLI reads the same file)")
    deactivate.set_defaults(handler=run_deactivate)


def _print_environment(env: dict[str, str], token_file: Path | None = None) -> None:
    print(f"environment: {env['system']}, shell {env['shell']}, user {env['user']}")
    export = env["export_command"]
    if token_file is not None and token_file != token_path():
        export = export.replace(f"~/{OFFICIAL_DIR}/{OFFICIAL_FILES[0]}", str(token_file)).replace(
            f"$HOME\\{OFFICIAL_DIR}\\{OFFICIAL_FILES[0]}", str(token_file))
    print(f"outside the dashboard: {export}")
    print(f"  (add that line to {env['profile_file']} to keep it in new shells)")
    if env["note"]:
        print(f"note: {env['note']}")


def run_activate(args) -> int:
    if args.token_stdin:
        token = sys.stdin.read().strip()
    else:
        print(f"Create a token at {TOKEN_PAGE} (Account → API → Generate New Token).")
        token = getpass.getpass("Kaggle API token (KGAT_…, hidden): ").strip()
    if not token:
        raise UserError("no token given; nothing was stored")
    if not args.no_verify:
        ok, detail = verify_token(token)
        if not ok:
            raise UserError(f"Kaggle rejected the token ({detail}); nothing was stored")
        print(f"verified: {detail}")
    path = store_token(token, replace=args.replace)
    print(f"stored: {path}" + (" (mode 0600)" if _posix() else ""))
    root = Path(args.workspace).expanduser().resolve() if args.workspace else Path.cwd().resolve()
    if args.workspace and not root.is_dir():
        print(f"warning: --workspace {root} is not a directory; no MCP file was updated")
    elif root.is_dir() and ((root / ".papersmith").is_dir() or args.workspace):
        written = ensure_mcp_servers(root, _workspace_tools(root))
        print("workspace MCP files: " + (", ".join(written) if written else "already carry the kaggle server"))
    print("Restart the agent (or open a new session in the dashboard CLI assistant) to load it.")
    _print_environment(detect_environment())
    return 0


def run_status(args) -> int:
    env = detect_environment()
    _token, stored = stored_token()
    if os.environ.get(TOKEN_ENV):
        print(f"kaggle MCP: activated through the exported {TOKEN_ENV}")
    elif stored is not None:
        print(f"kaggle MCP: activated, token stored at {stored}")
    else:
        path, problem = token_path(), "absent"
        for candidate in token_candidates():
            found = token_file_problem(candidate)
            if found and found != "absent":
                path, problem = candidate, found
                break
        print(f"kaggle MCP: not activated ({path}: {problem})")
        if problem.startswith("insecure"):
            print(f"fix: chmod 600 {path}, or run `smith mcp kaggle activate` again")
        else:
            print(f"activate: smith mcp kaggle activate (token from {TOKEN_PAGE})")
    _print_environment(env, stored)
    if args.verify:
        token = os.environ.get(TOKEN_ENV) or read_token()
        if token:
            ok, detail = verify_token(token)
            print(f"verify: {'ok' if ok else 'failed'} ({detail})")
            return 0 if ok else 1
        print("verify: skipped, no usable token")
        return 1
    return 0


def run_deactivate(args) -> int:
    removed = False
    for path in token_candidates():
        if path.is_dir() and not path.is_symlink():
            raise UserError(f"{path} is a directory, not a token file; remove it by hand")
        if path.is_symlink() or path.exists():
            path.unlink()
            print(f"removed: {path}")
            removed = True
    if not removed:
        print(f"nothing to remove: {token_path()}")
    if os.environ.get(TOKEN_ENV):
        print(f"note: {TOKEN_ENV} is still exported in this shell")
    return 0
