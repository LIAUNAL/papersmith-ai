"""The Caztor sidecar: the LaTeX editor shown in the dashboard's PDF tab."""

from __future__ import annotations

import asyncio
import json
import os
import stat
import tempfile
import time
import unittest
from pathlib import Path

from unittest import mock

from skills._core.command_center import caztor, caztor_tools, server

_PATCHES: list = []
_CACHE = tempfile.TemporaryDirectory()


def setUpModule() -> None:
    """Every sidecar here runs a fake `node`: it counts as Node 26, nothing is downloaded and no real cache is read."""
    def no_network(url: str) -> bytes:
        raise OSError(f"no network in tests ({url})")
    for patch in (mock.patch.object(caztor_tools, "node_major", lambda _path: 26),
                  mock.patch.object(caztor_tools, "_download", no_network),
                  mock.patch.object(caztor_tools, "default_cache_dir", lambda _env: Path(_CACHE.name))):
        patch.start()
        _PATCHES.append(patch)


def tearDownModule() -> None:
    for patch in _PATCHES:
        patch.stop()
    _CACHE.cleanup()

ORIGIN = "http://127.0.0.1:8080"


def _fake_caztor(base: Path, script: str) -> tuple[Path, Path]:
    """A Caztor checkout and a `node` that runs ``script`` (shell) instead of the server."""
    home = base / "caztor"
    (home / "apps" / "server-local" / "src").mkdir(parents=True)
    (home / "apps" / "server-local" / "src" / "main.ts").write_text("// fake", encoding="utf-8")
    (home / "apps" / "web" / "dist").mkdir(parents=True)
    (home / "apps" / "web" / "dist" / "index.html").write_text("<!doctype html>", encoding="utf-8")
    (home / "node_modules").mkdir()
    bin_dir = base / "bin"
    bin_dir.mkdir()
    node = bin_dir / "node"
    node.write_text("#!/bin/sh\n" + script, encoding="utf-8")
    node.chmod(node.stat().st_mode | stat.S_IEXEC)
    return home, bin_dir


READY_SCRIPT = (
    'echo "$@" > "$(dirname "$0")/args"\n'
    'env > "$(dirname "$0")/env"\n'
    'echo "Caztor is running at http://127.0.0.1:4999 for $3"\n'
    "exec sleep 30\n"
)


class SidecarTests(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.base = Path(holder.name).resolve()
        self.root = self.base / "workspace"
        self.root.mkdir()

    def sidecar(self, script: str = READY_SCRIPT, **env: str) -> tuple[caztor.CaztorSidecar, Path]:
        home, bin_dir = _fake_caztor(self.base, script)
        full_env = {"PATH": f"{bin_dir}:/usr/bin:/bin", "CAZTOR_HOME": str(home), **env}
        sidecar = caztor.CaztorSidecar(self.root, env=full_env, startup_timeout=5.0)
        self.addCleanup(sidecar.stop)
        return sidecar, bin_dir

    def test_it_starts_caztor_on_the_workspace_for_the_dashboard_origin(self) -> None:
        sidecar, bin_dir = self.sidecar()
        result = sidecar.ensure(ORIGIN)
        self.assertEqual(result, {"available": True, "url": "http://127.0.0.1:4999", "instance": sidecar._process.pid})
        args = (bin_dir / "args").read_text(encoding="utf-8").split()
        self.assertEqual(args[1:], [str(self.root), "--embed-origin", ORIGIN])
        self.assertTrue(args[0].endswith("apps/server-local/src/main.ts"))

    def test_a_second_call_reuses_the_running_server(self) -> None:
        sidecar, bin_dir = self.sidecar()
        first = sidecar.ensure(ORIGIN)
        (bin_dir / "args").unlink()
        self.assertEqual(sidecar.ensure(ORIGIN), first)
        self.assertFalse((bin_dir / "args").exists())

    def test_a_server_that_died_is_started_again_as_a_new_instance(self) -> None:
        sidecar, _ = self.sidecar()
        first = sidecar.ensure(ORIGIN)
        sidecar._process.kill()
        sidecar._process.wait()
        second = sidecar.ensure(ORIGIN)
        self.assertTrue(second["available"])
        self.assertNotEqual(second["instance"], first["instance"])

    def test_another_origin_restarts_it_for_that_origin(self) -> None:
        sidecar, bin_dir = self.sidecar()
        sidecar.ensure(ORIGIN)
        sidecar.ensure("http://localhost:8080")
        self.assertIn("http://localhost:8080", (bin_dir / "args").read_text(encoding="utf-8"))

    def test_it_never_exposes_caztor_beyond_loopback(self) -> None:
        sidecar, bin_dir = self.sidecar(CAZTOR_HOST="0.0.0.0", CAZTOR_PUBLIC_NAME="box.lan", CAZTOR_SECURE="1", INIT_CWD="/elsewhere")
        sidecar.ensure(ORIGIN)
        env = (bin_dir / "env").read_text(encoding="utf-8")
        for name in ("CAZTOR_HOST=", "CAZTOR_PUBLIC_NAME=", "CAZTOR_SECURE=", "INIT_CWD="):
            self.assertNotIn(name, env)

    def test_stop_ends_the_process(self) -> None:
        sidecar, _ = self.sidecar()
        sidecar.ensure(ORIGIN)
        process = sidecar._process
        sidecar.stop()
        self.assertIsNotNone(process.poll())

    def test_a_server_that_exits_reports_its_last_words(self) -> None:
        sidecar, _ = self.sidecar('echo "Node.js 18 cannot run TypeScript" >&2\nexit 1\n')
        result = sidecar.ensure(ORIGIN)
        self.assertFalse(result["available"])
        self.assertIn("Node.js 18 cannot run TypeScript", result["reason"])

    def test_a_missing_checkout_is_reported_without_starting_anything(self) -> None:
        sidecar = caztor.CaztorSidecar(self.root, env={"PATH": "/usr/bin:/bin", "CAZTOR_HOME": str(self.base / "nowhere")})
        result = sidecar.ensure(ORIGIN)
        self.assertFalse(result["available"])
        self.assertIn("CAZTOR_HOME", result["reason"])

    def test_an_unbuilt_web_app_or_missing_dependencies_name_the_setup_command(self) -> None:
        for missing in (Path("apps") / "web" / "dist" / "index.html", Path("node_modules")):
            with self.subTest(missing=str(missing)):
                base = Path(tempfile.mkdtemp(dir=self.base))
                home, _ = _fake_caztor(base, READY_SCRIPT)
                target = home / missing
                target.rmdir() if target.is_dir() else target.unlink()
                sidecar = caztor.CaztorSidecar(self.root, env={"PATH": "/usr/bin:/bin", "CAZTOR_HOME": str(home)})
                result = sidecar.ensure(ORIGIN)
                self.assertFalse(result["available"])
                self.assertIn("npm run setup:caztor", result["reason"])

    def test_without_caztor_home_it_runs_the_bundled_copy(self) -> None:
        home, bin_dir = _fake_caztor(self.base, READY_SCRIPT)
        sidecar = caztor.CaztorSidecar(self.root, env={"PATH": f"{bin_dir}:/usr/bin:/bin"}, startup_timeout=5.0,
                                       bundled=lambda: home)
        self.addCleanup(sidecar.stop)
        self.assertEqual(sidecar.locate(), (home, None))
        self.assertTrue(sidecar.ensure(ORIGIN)["available"])

    def test_an_installed_copy_runs_its_one_file_server_without_node_modules(self) -> None:
        home, bin_dir = _fake_caztor(self.base, READY_SCRIPT)
        (home / "node_modules").rmdir()
        (home / "apps" / "server-local" / "src" / "main.ts").unlink()
        (home / caztor.SERVER_BUNDLE).parent.mkdir(parents=True)
        (home / caztor.SERVER_BUNDLE).write_text("// bundle", encoding="utf-8")
        sidecar = caztor.CaztorSidecar(self.root, env={"PATH": f"{bin_dir}:/usr/bin:/bin", "CAZTOR_HOME": str(home)},
                                       startup_timeout=5.0)
        self.addCleanup(sidecar.stop)
        self.assertTrue(sidecar.ensure(ORIGIN)["available"])
        self.assertTrue((bin_dir / "args").read_text(encoding="utf-8").startswith(str(home / caztor.SERVER_BUNDLE)))

    def test_a_set_up_checkout_runs_its_source_even_with_a_bundle_beside_it(self) -> None:
        home, bin_dir = _fake_caztor(self.base, READY_SCRIPT)
        (home / caztor.SERVER_BUNDLE).parent.mkdir(parents=True)
        (home / caztor.SERVER_BUNDLE).write_text("// bundle", encoding="utf-8")
        self.assertEqual(caztor.server_entry(home), home / caztor.SERVER_ENTRY)
        (home / "node_modules").rmdir()
        self.assertEqual(caztor.server_entry(home), home / caztor.SERVER_BUNDLE)

    def test_the_folders_of_the_programs_found_come_first_on_caztors_path(self) -> None:
        home, bin_dir = _fake_caztor(self.base, READY_SCRIPT)
        fetched = self.base / "cache" / "tectonic-0.17.0-linux-x64"
        fetched.mkdir(parents=True)

        class Found:
            def find(self, name: str) -> str:
                return str(bin_dir / "node") if name == "node" else str(fetched / "tectonic")

        sidecar = caztor.CaztorSidecar(self.root, env={"PATH": "/usr/bin:/bin", "CAZTOR_HOME": str(home)},
                                       startup_timeout=5.0, tools=Found())
        self.addCleanup(sidecar.stop)
        self.assertTrue(sidecar.ensure(ORIGIN)["available"])
        path = next(line for line in (bin_dir / "env").read_text(encoding="utf-8").splitlines()
                    if line.startswith("PATH="))
        self.assertEqual(path, f"PATH={bin_dir}:{fetched}:/usr/bin:/bin")

    def test_a_program_already_on_the_path_leaves_the_path_order_alone(self) -> None:
        home, bin_dir = _fake_caztor(self.base, READY_SCRIPT)

        class OnPath:
            def find(self, name: str) -> str:
                return str(bin_dir / name)

        sidecar = caztor.CaztorSidecar(self.root, env={"PATH": f"/opt/first:{bin_dir}:/usr/bin", "CAZTOR_HOME": str(home)},
                                       startup_timeout=5.0, tools=OnPath())
        self.addCleanup(sidecar.stop)
        self.assertTrue(sidecar.ensure(ORIGIN)["available"])
        path = next(line for line in (bin_dir / "env").read_text(encoding="utf-8").splitlines()
                    if line.startswith("PATH="))
        self.assertEqual(path, f"PATH=/opt/first:{bin_dir}:/usr/bin")

    def test_without_tectonic_caztor_still_opens(self) -> None:
        home, bin_dir = _fake_caztor(self.base, READY_SCRIPT)

        class NoTectonic:
            def find(self, name: str) -> str:
                if name == "tectonic":
                    raise caztor_tools.ToolError("Install Tectonic")
                return str(bin_dir / "node")

        sidecar = caztor.CaztorSidecar(self.root, env={"PATH": "/usr/bin:/bin", "CAZTOR_HOME": str(home)},
                                       startup_timeout=5.0, tools=NoTectonic())
        self.addCleanup(sidecar.stop)
        self.assertTrue(sidecar.ensure(ORIGIN)["available"])

    def test_caztor_home_wins_over_the_bundled_copy(self) -> None:
        home, _ = _fake_caztor(self.base, READY_SCRIPT)
        sidecar = caztor.CaztorSidecar(self.root, env={"CAZTOR_HOME": str(home)}, bundled=lambda: self.base / "other")
        self.assertEqual(sidecar.locate(), (home, None))

    def test_no_bundled_copy_and_no_caztor_home_is_reported(self) -> None:
        sidecar = caztor.CaztorSidecar(self.root, env={"PATH": "/usr/bin:/bin"}, bundled=lambda: None)
        result = sidecar.ensure(ORIGIN)
        self.assertFalse(result["available"])
        self.assertIn("papersmith checkout", result["reason"])
        self.assertIn("CAZTOR_HOME", result["reason"])

    def test_the_bundled_copy_is_this_checkouts_caztor_folder(self) -> None:
        found = caztor.bundled_home()
        if found is not None:
            self.assertEqual(found.name, "caztor")
            self.assertTrue((found / caztor.SERVER_ENTRY).is_file())

    def test_missing_node_is_reported(self) -> None:
        sidecar, bin_dir = self.sidecar()
        (bin_dir / "node").unlink()
        sidecar.env["PATH"] = str(bin_dir)
        result = sidecar.ensure(ORIGIN)
        self.assertFalse(result["available"])
        self.assertIn("node", result["reason"].lower())

    def test_a_malformed_origin_is_refused(self) -> None:
        sidecar, bin_dir = self.sidecar()
        result = sidecar.ensure("http://evil host/;x")
        self.assertFalse(result["available"])
        self.assertFalse((bin_dir / "args").exists())


def _post(app, path: str):
    for route in app.routes:
        if getattr(route, "path", None) == path and "POST" in (getattr(route, "methods", None) or ()):
            return route.endpoint
    raise AssertionError(f"no POST {path}")


class _Request:
    def __init__(self, headers: dict[str, str]) -> None:
        self.headers = {k.lower(): v for k, v in headers.items()}


class CaztorRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.base = Path(holder.name).resolve()
        root = self.base / "workspace"
        root.mkdir()
        home, bin_dir = _fake_caztor(self.base, READY_SCRIPT)
        self.bin_dir = bin_dir
        self.app = server.create_app(root, history_store=None)
        self.app.state.caztor.env = {"PATH": f"{bin_dir}:/usr/bin:/bin", "CAZTOR_HOME": str(home)}
        self.addCleanup(self.app.state.caztor.stop)

    def call(self, headers: dict[str, str]):
        response = asyncio.run(_post(self.app, "/api/caztor")(_Request(headers)))
        return response.status_code, json.loads(bytes(response.body))

    def test_the_dashboard_gets_caztor_for_the_address_it_was_opened_at(self) -> None:
        status, body = self.call({"Host": "127.0.0.1:8080", "Origin": "http://127.0.0.1:8080"})
        self.assertEqual(status, 200)
        self.assertEqual(body["url"], "http://127.0.0.1:4999")
        self.assertTrue(body["available"])
        self.assertIn("--embed-origin http://127.0.0.1:8080", (self.bin_dir / "args").read_text(encoding="utf-8"))

    def test_a_dashboard_reached_by_another_name_than_loopback_does_not_start_it(self) -> None:
        status, body = self.call({"Host": "rebound.example:8080", "Origin": "http://rebound.example:8080"})
        self.assertEqual(status, 200)
        self.assertFalse(body["available"])
        self.assertIn("loopback", body["reason"])
        self.assertFalse((self.bin_dir / "args").exists())

    def test_localhost_is_loopback_too(self) -> None:
        status, body = self.call({"Host": "localhost:8080", "Origin": "http://localhost:8080"})
        self.assertTrue(body["available"])

    def test_a_cross_origin_page_cannot_start_it(self) -> None:
        status, _ = self.call({"Host": "127.0.0.1:8080", "Origin": "http://evil.example"})
        self.assertEqual(status, 403)
        self.assertFalse((self.bin_dir / "args").exists())


if __name__ == "__main__":
    unittest.main()


class SmithUiHandsTheBundledCaztorTests(unittest.TestCase):
    """The dashboard runs in the workspace's environment, which does not hold papersmith; smith ui names Caztor."""

    def test_smith_ui_names_this_checkouts_caztor_unless_caztor_home_is_set(self) -> None:
        from unittest import mock
        from papersmith.core import ui

        with tempfile.TemporaryDirectory() as holder:
            home = Path(holder) / "caztor"
            with mock.patch.object(ui, "bundled_caztor", return_value=home), \
                    mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("CAZTOR_HOME", None)
                self.assertEqual(ui._child_env(Path(holder))["CAZTOR_HOME"], str(home))
                os.environ["CAZTOR_HOME"] = "/mine"
                self.assertEqual(ui._child_env(Path(holder))["CAZTOR_HOME"], "/mine")
            with mock.patch.object(ui, "bundled_caztor", return_value=None), \
                    mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("CAZTOR_HOME", None)
                self.assertNotIn("CAZTOR_HOME", ui._child_env(Path(holder)))

    def test_without_a_set_up_checkout_it_names_the_installed_package_copy(self) -> None:
        from papersmith.core import ui

        with tempfile.TemporaryDirectory() as holder:
            package = Path(holder) / "site-packages" / "papersmith"
            bundle = package / "_caztor" / "apps" / "server-local" / "dist" / "main.mjs"
            bundle.parent.mkdir(parents=True)
            self.assertIsNone(ui.bundled_caztor(package))
            bundle.write_text("// bundle", encoding="utf-8")
            self.assertEqual(ui.bundled_caztor(package), package / "_caztor")
            # A checkout's caztor/ wins once its dependencies are installed.
            checkout = Path(holder) / "caztor"
            (checkout / "apps" / "server-local" / "src").mkdir(parents=True)
            (checkout / "apps" / "server-local" / "src" / "main.ts").write_text("//", encoding="utf-8")
            self.assertEqual(ui.bundled_caztor(package), package / "_caztor")
            (checkout / "node_modules").mkdir()
            self.assertEqual(ui.bundled_caztor(package), checkout)

    def test_the_bundled_caztor_is_the_checkouts_caztor_folder(self) -> None:
        from papersmith.core import ui

        found = ui.bundled_caztor()
        if found is not None:
            self.assertEqual(found.name, "caztor")

