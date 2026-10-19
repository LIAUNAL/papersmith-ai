"""``papersmith ui``: serve the Paper Command Center for a workspace.

The command center itself lives inside the initialized paper folder at
``skills/_core/command_center/`` (a kit entry). This command resolves that
folder, picks a free port, and launches the backend as a child process so the
dashboard runs standalone without Node/npm in the workspace.
"""

from __future__ import annotations

import ast
import contextlib
import importlib.util
import os
import signal
import socket
import subprocess
import sys
from pathlib import Path

from ..errors import SourceError, UserError
from . import fs
from .exit_codes import SUCCESS, USER_ERROR

#: The standalone module a workspace runs for the dashboard backend.
COMMAND_CENTER_MODULE = "skills._core.command_center.server"

#: The workspace-relative entry point that proves the backend shipped.
COMMAND_CENTER_ENTRY = Path("skills") / "_core" / "command_center" / "server.py"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8080
#: How many consecutive ports to try when the preferred one is taken.
PORT_SCAN_ATTEMPTS = 25

#: The workspace-relative script that BUILDS the environment the backend runs
#: in. Its own declarations are where the interpreter's path is read from.
PROVISIONING_SCRIPT = Path("scripts") / "setup_env.py"

#: Fallbacks, in order. A workspace may carry a hand-made virtualenv -- this
#: repository's own checkouts do -- so one is still honored, but only after the
#: environment the shipped provisioning actually produces.
FALLBACK_INTERPRETERS = (
    Path(".venv") / "bin" / "python",
    Path(".venv") / "Scripts" / "python.exe",
)

#: The modules the backend imports at module scope, asked of the interpreter
#: itself rather than restated as a dependency list. `fastapi` is the one whose
#: absence produces the raw traceback this preflight replaces.
BACKEND_PROBE = (
    "import importlib.util as u, sys;"
    "missing = [m for m in ('fastapi', 'uvicorn') if u.find_spec(m) is None];"
    "sys.exit(1 if missing else 0)"
)


def provisioned_interpreters(workspace: Path) -> tuple[Path, ...]:
    """The interpreter paths the workspace's own provisioning script declares.

    Read by importing ``scripts/setup_env.py`` and asking it, exactly as
    ``tests/test_forge_gate.py`` derives the gate's interpreter from the same
    script. The script that BUILDS the environment is the one declaration of
    where it lives; a path restated here is a path that can disagree with it,
    and it did: this module used to look for a ``.venv/`` that no script in this
    repository creates, while the provisioning script built
    ``.micromamba/envs/<name>``. A ``pipx install .`` user then got a raw
    ``ModuleNotFoundError`` from a child process instead of a dashboard, and the
    repository had already written that exact disagreement down as a lesson.
    """
    script = workspace / PROVISIONING_SCRIPT
    if not script.is_file():
        return ()
    try:
        spec = importlib.util.spec_from_file_location(
            "_papersmith_workspace_setup_env", script)
        if spec is None or spec.loader is None:
            return ()
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        root = Path(module.MAMBA_ROOT)
        env_name = str(module.ENV_NAME)
    except Exception:                      # noqa: BLE001 -- any failure is "cannot derive"
        return ()
    binary = root / "envs" / env_name / "bin"
    return (binary / "python", binary / "python.exe")


def workspace_interpreter(workspace: Path) -> str:
    """Return the interpreter that should run the workspace's backend.

    ``pipx install .`` installs ``papersmith-ai`` with no runtime dependencies,
    so the CLI's own ``sys.executable`` cannot import the dashboard backend.
    The environment the workspace's own provisioning script builds holds those
    dependencies, so it is preferred; a hand-made ``.venv`` is honored next, and
    the running interpreter is the last resort.
    """
    for candidate in provisioned_interpreters(workspace) + tuple(
            workspace / relative for relative in FALLBACK_INTERPRETERS):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return sys.executable


def backend_is_importable(interpreter: str) -> bool:
    """Whether this interpreter can import the backend's own dependencies.

    Asked of the interpreter as a process, so the answer is a measurement rather
    than a version number somebody chose.
    """
    try:
        done = subprocess.run([interpreter, "-c", BACKEND_PROBE],
                              capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return done.returncode == 0


def require_runnable_backend(workspace: Path, interpreter: str) -> None:
    """Refuse with a papersmith-level diagnostic, never a child traceback.

    A child that dies on ``ModuleNotFoundError`` reports a Python fact to a
    person who asked for a dashboard, and names no remedy. This says which
    interpreter was tried, that it cannot import the backend, and the one command
    that provisions the environment the workspace's own kit ships.
    """
    if backend_is_importable(interpreter):
        return
    provisioned = provisioned_interpreters(workspace)
    expected = str(provisioned[0]) if provisioned else \
        f"the environment {PROVISIONING_SCRIPT} builds"
    raise UserError(
        f"no interpreter in {workspace} can run the command center: "
        f"{interpreter} cannot import fastapi.\n"
        f"Provision the workspace's environment and run this again:\n"
        f"  python3 {PROVISIONING_SCRIPT} install\n"
        f"That creates {expected}. `papersmith init` runs this step itself "
        "unless it is given `--no-env`."
    )


def command_center_entry(workspace: Path) -> Path:
    """Resolve the workspace-local backend entry point, or refuse."""
    entry = workspace / COMMAND_CENTER_ENTRY
    if not fs.is_regular_file(entry):
        raise SourceError(
            f"{workspace} has no command center at {COMMAND_CENTER_ENTRY}; "
            "run `papersmith upgrade` to restore the kit"
        )
    return entry


def port_is_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def find_available_port(host: str, preferred: int,
                        attempts: int = PORT_SCAN_ATTEMPTS) -> int:
    """Return the first free port at or after ``preferred``.

    A local dashboard is a convenience, not a service contract: when the
    preferred port is occupied the command center moves to the next one
    instead of failing the operator's `papersmith ui`.
    """
    for candidate in range(preferred, preferred + attempts):
        if port_is_free(host, candidate):
            return candidate
    raise UserError(
        f"no free port in {preferred}..{preferred + attempts - 1} on {host}"
    )


def build_server_argv(workspace: Path, host: str, port: int, *, no_browser: bool,
                      export_static: str | None = None,
                      interpreter: str | None = None,
                      allowed_hosts: list[str] | None = None,
                      allow_unauthenticated_network: bool = False) -> list[str]:
    """Build the child command that runs the workspace's backend."""
    argv = [
        interpreter or sys.executable,
        "-m",
        COMMAND_CENTER_MODULE,
        "--root",
        str(workspace),
        "--host",
        host,
        "--port",
        str(port),
    ]
    if no_browser:
        argv.append("--no-browser")
    if export_static is not None:
        argv.extend(["--export-static", str(export_static)])
    # Only forwarded when given, so an older workspace backend without the
    # flag keeps working.
    for allowed in allowed_hosts or []:
        argv.extend(["--allowed-host", allowed])
    if allow_unauthenticated_network:
        argv.append("--allow-unauthenticated-network")
    return argv


def _child_env(workspace: Path) -> dict[str, str]:
    env = dict(os.environ)
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(workspace) + (os.pathsep + existing if existing else "")
    # The dashboard reads a workspace and must not write into it. Importing the
    # workspace's own modules would otherwise leave `__pycache__` directories
    # behind, which is how a read-only observer quietly modifies the paper
    # folder it was pointed at. The MCP bridge already sets this; the child here
    # did not.
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _run_child(argv: list[str], workspace: Path) -> int:
    """Run the backend, forwarding SIGINT/SIGTERM and reaping the child.

    Returns ``0`` when the child exited because the operator interrupted it,
    otherwise the child's own exit code mapped onto the papersmith contract.
    """
    try:
        process = subprocess.Popen(argv, cwd=str(workspace), env=_child_env(workspace))
    except OSError as exc:
        raise UserError(f"could not start the command center: {exc}") from None

    interrupted = {"value": False}

    def _forward(signum, _frame) -> None:
        interrupted["value"] = True
        with contextlib.suppress(OSError):
            process.send_signal(signum)

    previous: dict[int, object] = {}
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(ValueError, OSError):
            previous[sig] = signal.signal(sig, _forward)
    try:
        code = process.wait()
    except KeyboardInterrupt:  # pragma: no cover - a handler is installed
        interrupted["value"] = True
        with contextlib.suppress(OSError):
            process.terminate()
        code = process.wait()
    finally:
        for sig, handler in previous.items():
            with contextlib.suppress(ValueError, OSError):
                signal.signal(sig, handler)

    if interrupted["value"]:
        return SUCCESS
    if code == 0:
        return SUCCESS
    return code if code > 0 else USER_ERROR


def run_cli(args) -> int:
    workspace = Path(args.directory).expanduser().resolve()
    if not fs.is_dir(workspace):
        raise UserError(f"not a directory: {workspace}")
    command_center_entry(workspace)
    interpreter = workspace_interpreter(workspace)

    if args.export_static:
        argv = build_server_argv(
            workspace, args.host, args.port, no_browser=True,
            export_static=args.export_static, interpreter=interpreter,
        )
        return _run_child(argv, workspace)

    if args.port < 1 or args.port > 65535:
        raise UserError(f"port out of range: {args.port}")
    port = args.port if port_is_free(args.host, args.port) else find_available_port(args.host, args.port)
    if port != args.port:
        print(f"papersmith ui: port {args.port} is busy; using {port}", file=sys.stderr)

    url = f"http://{args.host}:{port}/"
    require_runnable_backend(workspace, interpreter)
    print(f"papersmith ui: serving {workspace} at {url}")
    print("papersmith ui: press Ctrl+C to stop")
    argv = build_server_argv(workspace, args.host, port, no_browser=args.no_browser,
                             interpreter=interpreter,
                             allowed_hosts=getattr(args, "allowed_host", None),
                             allow_unauthenticated_network=getattr(
                                 args, "allow_unauthenticated_network", False))
    return _run_child(argv, workspace)


def register(subparsers) -> None:
    parser = subparsers.add_parser(
        "ui",
        help="serve the Paper Command Center dashboard for this workspace",
        description=(
            "Launch the local Paper Command Center: pipeline DAG, quality gates, "
            "section matrix, and harness wiring health, updated live as files change."
        ),
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help="bind address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help="preferred port; a busy port moves to the next free one")
    parser.add_argument("--no-browser", action="store_true", help="never open a browser window")
    parser.add_argument("--export-static", metavar="<dir>", default=None,
                        help="copy the dashboard build to <dir> and exit")
    parser.add_argument("--allowed-host", action="append", default=None, metavar="HOST:PORT",
                        help="also accept this Host header (repeatable), e.g. when forwarding "
                             "the port or running the Vite dev server")
    parser.add_argument("--allow-unauthenticated-network", action="store_true",
                        help="permit a non-loopback --host; the dashboard has no "
                             "authentication, so only on a network you trust")
    parser.add_argument("directory", nargs="?", default=".", metavar="<dir>")
    parser.set_defaults(handler=run_cli)


__all__ = [
    "register", "run_cli", "find_available_port", "port_is_free",
    "build_server_argv", "command_center_entry", "COMMAND_CENTER_ENTRY",
    "COMMAND_CENTER_MODULE", "workspace_interpreter",
]
