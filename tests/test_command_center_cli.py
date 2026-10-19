"""`papersmith ui` resolves the workspace backend, picks a port, and spawns it."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from papersmith.cli import build_parser
from papersmith.core import init as init_module
from papersmith.core import ui as ui_command
from papersmith.errors import SourceError, UserError

REPOSITORY = Path(__file__).resolve().parent.parent
COMMAND_CENTER = REPOSITORY / "skills" / "_core" / "command_center"


def _seed_command_center(root: Path) -> None:
    destination = root / ui_command.COMMAND_CENTER_ENTRY.parent
    shutil.copytree(COMMAND_CENTER, destination)


class ProvisionerAgreementTests(unittest.TestCase):
    """The thing that BUILDS the environment and the thing that FINDS it must
    name the same path.

    The defect this feature fixed was exactly that disagreement: the shipped
    `scripts/setup_env.py` built `.micromamba/envs/papersmith` while
    `workspace_interpreter` looked for a `.venv/` that nothing creates, and a
    `pipx install .` user got a raw `ModuleNotFoundError` from a child process.
    Stub-level tests could not catch it, because each side was checked against
    its own fixture. This drives the workspace's own provisioning script and then
    asks the resolver where the interpreter is.
    """

    def new_dir(self) -> Path:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        return Path(holder.name).resolve()

    def seed_creating_script(self, root: Path) -> Path:
        """A stand-in that CREATES the interpreter at the path it declares.

        The real script downloads an environment; this one only has to make the
        same promise about where the interpreter lands, which is the property
        under test.
        """
        script = root / "scripts" / "setup_env.py"
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text(
            "from pathlib import Path\n"
            "PROJECT_ROOT = Path(__file__).resolve().parent.parent\n"
            "MAMBA_ROOT = PROJECT_ROOT / '.micromamba'\n"
            "ENV_NAME = 'papersmith'\n"
            "binary = MAMBA_ROOT / 'envs' / ENV_NAME / 'bin'\n"
            "binary.mkdir(parents=True, exist_ok=True)\n"
            "target = binary / 'python'\n"
            "target.write_text('#!/bin/sh\\n')\n"
            "target.chmod(0o755)\n",
            encoding="utf-8")
        return root / ".micromamba" / "envs" / "papersmith" / "bin" / "python"

    def test_the_provisioned_path_is_the_resolved_path(self) -> None:
        root = self.new_dir()
        created = self.seed_creating_script(root)

        assert init_module._run_env_install(root) is None

        assert created.is_file(), "the provisioning stand-in created nothing"
        assert ui_command.provisioned_interpreters(root)[0] == created, (
            "the resolver derives a different path than the provisioner "
            "creates -- the disagreement that made `papersmith ui` fail for "
            "every pipx user")
        assert ui_command.workspace_interpreter(root) == str(created)

    def test_init_provisions_the_path_ui_then_resolves(self) -> None:
        """The same property through init's own wiring, with only the heavy
        download replaced: a real `init` writes the real kit, whose
        `scripts/setup_env.py` is the declaration both sides read."""
        root = self.new_dir() / "paper"
        calls: list[Path] = []
        original = init_module._run_env_install
        init_module._run_env_install = (
            lambda workspace, report=None: calls.append(workspace) or None)
        self.addCleanup(setattr, init_module, "_run_env_install", original)

        init_module.initialize(root, run_npm=False, run_env=True)

        assert calls == [root.resolve()], calls
        assert ui_command.provisioned_interpreters(root), (
            "a freshly initialized workspace declares no interpreter path, so "
            "`papersmith ui` would fall back to an interpreter with no "
            "runtime dependencies")


class LiveServerEndToEndTests(unittest.TestCase):
    """`papersmith ui` must reach a running dashboard in a workspace it created.

    The row this closes: every piece of evidence for the interpreter fix was
    stub-level -- a hand-seeded `setup_env.py`, a `#!/bin/sh` file at the derived
    path, and `_run_child` replaced wholesale -- so nothing ever observed a
    server starting. This drives the real command in a freshly initialized
    workspace, with no stubs, and asks the backend for its own state.

    It is offline: with no workspace environment the resolver falls back to this
    test's own interpreter, which carries the backend's dependencies.
    """

    def new_workspace(self) -> Path:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        workspace = Path(holder.name).resolve() / "paper"
        init_module.initialize(workspace, run_npm=False, run_env=False)
        return workspace

    def free_port(self) -> int:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    def poll_state(self, port: int, process: subprocess.Popen) -> dict | None:
        deadline = time.monotonic() + 60
        url = f"http://127.0.0.1:{port}/api/state"
        while time.monotonic() < deadline:
            if process.poll() is not None:
                return None                     # it exited instead of serving
            try:
                with urllib.request.urlopen(url, timeout=5) as response:
                    if response.status == 200:
                        return json.loads(response.read().decode("utf-8"))
            except (urllib.error.URLError, OSError, json.JSONDecodeError):
                time.sleep(0.25)
        return None

    def test_the_dashboard_answers_in_a_workspace_this_framework_created(self) -> None:
        workspace = self.new_workspace()
        port = self.free_port()
        environment = dict(os.environ, PYTHONPATH=str(REPOSITORY / "src"))
        process = subprocess.Popen(
            [sys.executable, "-m", "papersmith.cli", "ui", str(workspace),
             "--port", str(port), "--no-browser"],
            cwd=str(workspace), env=environment,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        self.addCleanup(process.kill)

        payload = self.poll_state(port, process)
        output = ""
        if payload is None and process.poll() is not None:
            output = (process.stdout.read() if process.stdout else "")[-800:]
        process.terminate()
        try:
            code = process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            process.kill()
            code = None

        assert payload is not None, (
            "`papersmith ui` never served `/api/state` in a workspace this "
            f"framework created. Exit {process.returncode}, output tail:\n{output}")
        for key in ("workspace", "sections", "gates", "pipeline_stages"):
            assert key in payload, (key, sorted(payload))
        assert payload["workspace"]["root"] == str(workspace), payload["workspace"]
        assert code == 0, f"`papersmith ui` exited {code} after SIGTERM"


class CommandCenterResolutionTests(unittest.TestCase):
    def new_dir(self) -> Path:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        return Path(holder.name).resolve()

    def test_ui_is_registered_on_the_top_level_parser(self) -> None:
        parser = build_parser()
        subparsers = next(
            action for action in parser._actions
            if isinstance(action, argparse._SubParsersAction)
        )
        assert "ui" in subparsers.choices

    def test_missing_command_center_refuses_with_a_source_error(self) -> None:
        root = self.new_dir()
        with self.assertRaises(SourceError):
            ui_command.command_center_entry(root)

    def test_command_center_entry_resolves_when_present(self) -> None:
        root = self.new_dir()
        _seed_command_center(root)
        entry = ui_command.command_center_entry(root)
        assert entry.name == "server.py"
        assert entry.is_file()

    def test_run_cli_rejects_a_missing_workspace(self) -> None:
        args = argparse.Namespace(directory="/does/not/exist", host="127.0.0.1",
                                  port=8080, no_browser=True, export_static=None)
        with self.assertRaises(UserError):
            ui_command.run_cli(args)


class PortSelectionTests(unittest.TestCase):
    def test_port_is_free_after_the_probe_releases_it(self) -> None:
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        probe.close()
        assert ui_command.port_is_free("127.0.0.1", port)

    def test_find_available_port_skips_an_occupied_port(self) -> None:
        occupied = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.addCleanup(occupied.close)
        occupied.bind(("127.0.0.1", 0))
        occupied.listen(1)
        port = occupied.getsockname()[1]

        chosen = ui_command.find_available_port("127.0.0.1", port)

        assert chosen > port

    def test_find_available_port_refuses_when_the_scan_is_exhausted(self) -> None:
        with self.assertRaises(UserError):
            ui_command.find_available_port("127.0.0.1", 9000, attempts=0)


class ServerArgvTests(unittest.TestCase):
    def test_argv_carries_root_host_and_port(self) -> None:
        argv = ui_command.build_server_argv(Path("/tmp/paper"), "127.0.0.1", 8123,
                                            no_browser=True)

        assert argv[0].endswith("python") or "python" in argv[0]
        assert ui_command.COMMAND_CENTER_MODULE in argv
        assert "--root" in argv and "/tmp/paper" in argv
        assert "--port" in argv and "8123" in argv
        assert "--no-browser" in argv

    def test_argv_omits_no_browser_when_a_browser_is_wanted(self) -> None:
        argv = ui_command.build_server_argv(Path("/tmp/paper"), "127.0.0.1", 8123,
                                            no_browser=False)
        assert "--no-browser" not in argv

    def test_argv_carries_export_static(self) -> None:
        argv = ui_command.build_server_argv(Path("/tmp/paper"), "127.0.0.1", 8123,
                                            no_browser=True, export_static="/tmp/out")
        assert "--export-static" in argv and "/tmp/out" in argv


class AllowedHostArgvTests(unittest.TestCase):
    def test_argv_forwards_each_allowed_host(self) -> None:
        argv = ui_command.build_server_argv(
            Path("/tmp/paper"), "127.0.0.1", 8123, no_browser=True,
            allowed_hosts=["localhost:5173", "example.test:80"])
        pairs = [argv[i + 1] for i, a in enumerate(argv) if a == "--allowed-host"]
        assert pairs == ["localhost:5173", "example.test:80"]

    def test_argv_omits_the_flag_when_none_is_given(self) -> None:
        for given in (None, []):
            argv = ui_command.build_server_argv(
                Path("/tmp/paper"), "127.0.0.1", 8123, no_browser=True, allowed_hosts=given)
            assert "--allowed-host" not in argv

    def test_parser_accepts_a_repeatable_allowed_host(self) -> None:
        import argparse
        parser = argparse.ArgumentParser()
        ui_command.register(parser.add_subparsers())
        args = parser.parse_args(["ui", "--allowed-host", "a:1", "--allowed-host", "b:2"])
        assert args.allowed_host == ["a:1", "b:2"]


class NetworkOptInArgvTests(unittest.TestCase):
    """#61: the backend refuses a non-loopback bind unless asked by flag; the
    wrapper forwards that flag only when given, like ``--allowed-host``."""

    def argv(self, **kwargs) -> list[str]:
        return ui_command.build_server_argv(
            Path("/tmp/paper"), "0.0.0.0", 8123, no_browser=True, **kwargs)

    def test_argv_forwards_the_opt_in_only_when_set(self) -> None:
        assert "--allow-unauthenticated-network" in self.argv(allow_unauthenticated_network=True)
        assert "--allow-unauthenticated-network" not in self.argv()

    def test_parser_accepts_the_opt_in(self) -> None:
        parser = argparse.ArgumentParser()
        ui_command.register(parser.add_subparsers())

        assert parser.parse_args(["ui", "--allow-unauthenticated-network"]).allow_unauthenticated_network
        assert parser.parse_args(["ui"]).allow_unauthenticated_network is False

    def test_run_cli_forwards_the_opt_in_to_the_backend(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        root = Path(holder.name).resolve()
        _seed_command_center(root)
        captured: list[list[str]] = []
        stubs = {
            "_run_child": lambda argv, workspace: captured.append(argv) or 0,
            "require_runnable_backend": lambda workspace, interpreter: None,
            "port_is_free": lambda host, port: True,
        }
        for name, stub in stubs.items():
            self.addCleanup(setattr, ui_command, name, getattr(ui_command, name))
            setattr(ui_command, name, stub)

        args = argparse.Namespace(directory=str(root), host="0.0.0.0", port=8080,
                                  no_browser=True, export_static=None,
                                  allowed_host=None, allow_unauthenticated_network=True)

        assert ui_command.run_cli(args) == 0
        assert "--allow-unauthenticated-network" in captured[0]


class WorkspaceInterpreterTests(unittest.TestCase):
    def new_dir(self) -> Path:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        return Path(holder.name).resolve()

    def seed_venv(self, root: Path) -> Path:
        interpreter = root / ".venv" / "bin" / "python"
        interpreter.parent.mkdir(parents=True)
        interpreter.write_text("#!/bin/sh\n", encoding="utf-8")
        interpreter.chmod(0o755)
        return interpreter

    def seed_provisioning(self, root: Path) -> Path:
        """A workspace carrying the shipped provisioning script and its env."""
        script = root / "scripts" / "setup_env.py"
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text(
            "from pathlib import Path\n"
            "PROJECT_ROOT = Path(__file__).resolve().parent.parent\n"
            "MAMBA_ROOT = PROJECT_ROOT / '.micromamba'\n"
            "ENV_NAME = 'papersmith'\n",
            encoding="utf-8")
        binary = root / ".micromamba" / "envs" / "papersmith" / "bin"
        binary.mkdir(parents=True)
        interpreter = binary / "python"
        interpreter.write_text("#!/bin/sh\n", encoding="utf-8")
        interpreter.chmod(0o755)
        return interpreter

    def test_workspace_venv_interpreter_is_preferred(self) -> None:
        root = self.new_dir()
        interpreter = self.seed_venv(root)

        assert ui_command.workspace_interpreter(root) == str(interpreter)

    def test_the_provisioned_environment_outranks_a_venv(self) -> None:
        """The path nothing creates used to be preferred over the one the shipped
        script builds, which is how `papersmith ui` failed for every
        `pipx install .` user while passing in this repository's own checkout."""
        root = self.new_dir()
        self.seed_venv(root)
        interpreter = self.seed_provisioning(root)

        assert ui_command.workspace_interpreter(root) == str(interpreter)

    def test_the_interpreter_path_is_read_from_the_workspace_script(self) -> None:
        """Derived, never restated: the script that builds the environment is the
        one declaration of where it lives."""
        root = self.new_dir()
        self.seed_provisioning(root)

        derived = ui_command.provisioned_interpreters(root)

        assert derived, "the derivation found nothing in a workspace carrying the script"
        # Absolute, because the workspace's own script resolves it against its own
        # root; the caller must not re-join it to the workspace.
        assert derived[0] == root / ".micromamba" / "envs" / "papersmith" / "bin" / "python"

    def test_no_provisioning_script_derives_nothing(self) -> None:
        """Non-vacuity the other way: the derivation must not invent a path."""
        assert ui_command.provisioned_interpreters(self.new_dir()) == ()

    def test_a_backend_that_cannot_be_imported_is_refused_with_a_remedy(self) -> None:
        """A child dying on ModuleNotFoundError reports a Python fact to somebody
        who asked for a dashboard and names no remedy. This must name one."""
        root = self.new_dir()
        self.seed_provisioning(root)

        with self.assertRaises(UserError) as caught:
            ui_command.require_runnable_backend(root, "/bin/false")

        message = str(caught.exception)
        assert "setup_env.py install" in message, message
        assert "fastapi" in message, message

    def test_a_runnable_interpreter_is_not_refused(self) -> None:
        """The preflight must not block the command it is protecting."""
        root = self.new_dir()
        self.seed_provisioning(root)
        capable = ui_command.workspace_interpreter(
            REPOSITORY) if ui_command.backend_is_importable(sys.executable) else None

        if capable is None:
            self.skipTest("the running interpreter cannot import the backend here")
        ui_command.require_runnable_backend(root, sys.executable)

    def test_missing_venv_falls_back_to_the_running_interpreter(self) -> None:
        root = self.new_dir()

        assert ui_command.workspace_interpreter(root) == sys.executable

    def test_run_cli_spawns_the_workspace_interpreter(self) -> None:
        root = self.new_dir()
        _seed_command_center(root)
        interpreter = self.seed_venv(root)
        captured: list[list[str]] = []
        original = ui_command._run_child
        ui_command._run_child = lambda argv, workspace: captured.append(argv) or 0
        self.addCleanup(setattr, ui_command, "_run_child", original)

        args = argparse.Namespace(directory=str(root), host="127.0.0.1", port=8080,
                                  no_browser=True, export_static=str(root / "out"))
        code = ui_command.run_cli(args)

        assert code == 0
        assert captured[0][0] == str(interpreter)


class ExportStaticEndToEndTests(unittest.TestCase):
    def test_export_static_spawns_the_workspace_backend(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        root = Path(holder.name).resolve()
        _seed_command_center(root)
        build = root / "ui" / "dist"
        build.mkdir(parents=True)
        (build / "index.html").write_text("<html>dashboard</html>", encoding="utf-8")
        destination = root / "exported"

        args = argparse.Namespace(directory=str(root), host="127.0.0.1", port=8080,
                                  no_browser=True, export_static=str(destination))
        code = ui_command.run_cli(args)

        assert code == 0
        assert (destination / "index.html").read_text(encoding="utf-8") == "<html>dashboard</html>"
