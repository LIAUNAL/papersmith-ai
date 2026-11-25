"""The Caztor sidecar: the LaTeX editor shown in the dashboard's PDF tab."""

from __future__ import annotations

import asyncio
import json
import os
import stat
import tempfile
import threading
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
TWIN = "http://localhost:8080"


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
        self.assertEqual(result, {"available": True, "url": "http://127.0.0.1:4999", "instance": sidecar._process.pid,
                                  "key": result["key"]})
        args = (bin_dir / "args").read_text(encoding="utf-8").split()
        # The loopback twin of the dashboard's address may frame it too: both name the same dashboard.
        self.assertEqual(args[1:], [str(self.root), "--embed-origin", ORIGIN, "--embed-origin", TWIN])
        self.assertTrue(args[0].endswith("apps/server-local/src/main.ts"))

    def test_each_launch_gets_its_own_frame_key_in_the_environment_never_on_the_command_line(self) -> None:
        sidecar, bin_dir = self.sidecar(CAZTOR_EMBED_KEY="inherited-from-the-operator")
        first = sidecar.ensure(ORIGIN)
        self.assertGreaterEqual(len(first["key"]), 32)
        env = (bin_dir / "env").read_text(encoding="utf-8").splitlines()
        self.assertIn(f"CAZTOR_EMBED_KEY={first['key']}", env)
        self.assertNotIn("CAZTOR_EMBED_KEY=inherited-from-the-operator", env)
        self.assertNotIn(first["key"], (bin_dir / "args").read_text(encoding="utf-8"))
        self.assertEqual(sidecar.ensure(ORIGIN)["key"], first["key"], "the running server keeps its key")
        sidecar.stop()
        self.assertNotEqual(sidecar.ensure(ORIGIN)["key"], first["key"], "a new launch has a new key")

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
        first = sidecar.ensure(ORIGIN)
        second = sidecar.ensure("http://127.0.0.1:9090")
        self.assertNotEqual(second["instance"], first["instance"])
        self.assertIn("--embed-origin http://127.0.0.1:9090", (bin_dir / "args").read_text(encoding="utf-8"))

    def test_the_loopback_twin_of_the_origin_reuses_the_running_server(self) -> None:
        sidecar, bin_dir = self.sidecar()
        first = sidecar.ensure(ORIGIN)
        (bin_dir / "args").unlink()
        self.assertEqual(sidecar.ensure(TWIN), first, "a localhost tab does not restart the 127.0.0.1 tab's Caztor")
        self.assertFalse((bin_dir / "args").exists())
        self.assertEqual(caztor.origin_twins(TWIN), (TWIN, ORIGIN))
        self.assertEqual(caztor.origin_twins("http://box.lan:8080"), ("http://box.lan:8080",))

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


class _SlowTools:
    """`find` that waits for ``release`` (a download in progress) and counts its calls."""

    def __init__(self, node: str, *, fail: set[str] | None = None) -> None:
        self.node = node
        self.fail = fail or set()
        self.release = threading.Event()
        self.entered = threading.Event()
        self.calls: list[str] = []
        self.lock = threading.Lock()

    def find(self, name: str) -> str:
        with self.lock:
            self.calls.append(name)
        self.entered.set()
        self.release.wait(10)
        if name in self.fail:
            raise caztor_tools.ToolError(f"downloading {name} failed (offline)")
        return self.node


class DownloadsOutsideTheLockTests(unittest.TestCase):
    """Fetching node and tectonic can take minutes: stop, the editor switch and shutdown never wait for it."""

    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.base = Path(holder.name).resolve()
        self.root = self.base / "workspace"
        self.root.mkdir()
        self.home, self.bin_dir = _fake_caztor(self.base, READY_SCRIPT)
        self.now = [1000.0]

    def sidecar(self, tools) -> caztor.CaztorSidecar:
        sidecar = caztor.CaztorSidecar(self.root, env={"PATH": "/usr/bin:/bin", "CAZTOR_HOME": str(self.home)},
                                       startup_timeout=5.0, tools=tools, clock=lambda: self.now[0])
        self.addCleanup(sidecar.stop)
        return sidecar

    def in_thread(self, call):
        results: list = []
        worker = threading.Thread(target=lambda: results.append(call()), daemon=True)
        worker.start()
        self.addCleanup(worker.join, 10)
        return worker, results

    def test_stop_returns_while_a_download_is_in_progress(self) -> None:
        tools = _SlowTools(str(self.bin_dir / "node"))
        sidecar = self.sidecar(tools)
        worker, results = self.in_thread(lambda: sidecar.ensure(ORIGIN))
        self.assertTrue(tools.entered.wait(5))
        started = time.monotonic()
        sidecar.stop()
        self.assertLess(time.monotonic() - started, 1.0, "stop waited for the download")
        tools.release.set()
        worker.join(10)
        self.assertEqual(results[0], {"available": False, "reason": caztor.STOPPED_REASON},
                         "the editor turned off meanwhile does not come back when the download ends")
        self.assertFalse(sidecar._alive())
        self.assertTrue(sidecar.ensure(ORIGIN)["available"], "the next request opens it")

    def test_stop_during_the_ready_wait_ends_the_starting_server_without_waiting_for_it(self) -> None:
        home, bin_dir = _fake_caztor(Path(tempfile.mkdtemp(dir=self.base)), "sleep 3\n" + READY_SCRIPT)
        sidecar = caztor.CaztorSidecar(self.root, env={"PATH": f"{bin_dir}:/usr/bin:/bin", "CAZTOR_HOME": str(home)},
                                       startup_timeout=10.0)
        self.addCleanup(sidecar.stop)
        worker, results = self.in_thread(lambda: sidecar.ensure(ORIGIN))
        deadline = time.monotonic() + 5
        while sidecar._process is None and time.monotonic() < deadline:
            time.sleep(0.02)
        process = sidecar._process
        self.assertIsNotNone(process)
        started = time.monotonic()
        sidecar.stop()
        self.assertLess(time.monotonic() - started, 2.0)
        worker.join(10)
        self.assertIsNotNone(process.poll(), "the starting server was ended")
        self.assertFalse(results[0]["available"])
        self.assertIn("stopped", results[0]["reason"])
        self.assertFalse(sidecar._alive())

    def test_concurrent_requests_share_one_download(self) -> None:
        tools = _SlowTools(str(self.bin_dir / "node"))
        sidecar = self.sidecar(tools)
        first, first_result = self.in_thread(lambda: sidecar.ensure(ORIGIN))
        self.assertTrue(tools.entered.wait(5))
        second, second_result = self.in_thread(lambda: sidecar.ensure(ORIGIN))
        time.sleep(0.3)
        tools.release.set()
        first.join(10)
        second.join(10)
        self.assertEqual(tools.calls.count("node"), 1, tools.calls)
        self.assertEqual(first_result[0]["instance"], second_result[0]["instance"])

    def test_a_failed_download_is_not_retried_for_five_minutes(self) -> None:
        tools = _SlowTools(str(self.bin_dir / "node"), fail={"node"})
        tools.release.set()
        sidecar = self.sidecar(tools)
        first = sidecar.ensure(ORIGIN)
        self.assertFalse(first["available"])
        self.assertIn("offline", first["reason"])
        self.now[0] += 60
        self.assertEqual(sidecar.ensure(ORIGIN)["reason"], first["reason"])
        self.assertEqual(tools.calls, ["node"], "the failure was remembered")
        self.now[0] += caztor.FAILED_TOOL_RETRY_SECONDS
        sidecar.ensure(ORIGIN)
        self.assertEqual(tools.calls, ["node", "node"], "tried again once the five minutes passed")

    def test_a_failed_tectonic_download_is_remembered_and_caztor_still_opens(self) -> None:
        tools = _SlowTools(str(self.bin_dir / "node"), fail={"tectonic"})
        tools.release.set()
        sidecar = self.sidecar(tools)
        self.assertTrue(sidecar.ensure(ORIGIN)["available"])
        sidecar.stop()
        self.assertTrue(sidecar.ensure(ORIGIN)["available"])
        self.assertEqual(tools.calls.count("tectonic"), 1, tools.calls)


def _post(app, path: str):
    for route in app.routes:
        if getattr(route, "path", None) == path and "POST" in (getattr(route, "methods", None) or ()):
            return route.endpoint
    raise AssertionError(f"no POST {path}")


class _Request:
    def __init__(self, headers: dict[str, str], cookies: dict[str, str] | None = None) -> None:
        self.headers = {k.lower(): v for k, v in headers.items()}
        self.cookies = dict(cookies or {})


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
        # Without the terminal there is no per-browser secret: the frame key goes to any same-origin page.
        self.assertEqual(body["key"], self.app.state.caztor._key)
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

    def stop(self, headers: dict[str, str]):
        response = asyncio.run(_post(self.app, "/api/caztor/stop")(_Request(headers)))
        return response.status_code, json.loads(bytes(response.body))

    def test_turning_the_editor_off_stops_caztor_and_a_later_visit_starts_a_new_one(self) -> None:
        here = {"Host": "127.0.0.1:8080", "Origin": "http://127.0.0.1:8080"}
        _, first = self.call(here)
        status, body = self.stop(here)
        self.assertEqual((status, body), (200, {"stopped": True}))
        self.assertFalse(self.app.state.caztor._alive())
        _, again = self.call(here)
        self.assertTrue(again["available"])
        self.assertNotEqual(again["instance"], first["instance"])

    def test_a_cross_origin_page_cannot_stop_it(self) -> None:
        self.call({"Host": "127.0.0.1:8080", "Origin": "http://127.0.0.1:8080"})
        status, _ = self.stop({"Host": "127.0.0.1:8080", "Origin": "http://evil.example"})
        self.assertEqual(status, 403)
        self.assertTrue(self.app.state.caztor._alive())


class CaztorRouteWithTheTerminalTests(unittest.TestCase):
    """With the terminal on, only the browser holding its login cookie learns Caztor's frame key."""

    HERE = {"Host": "127.0.0.1:8080", "Origin": "http://127.0.0.1:8080"}

    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.base = Path(holder.name).resolve()
        root = self.base / "workspace"
        root.mkdir()
        home, bin_dir = _fake_caztor(self.base, READY_SCRIPT)
        self.bin_dir = bin_dir
        self.app = server.create_app(root, history_store=None, enable_terminal=True)
        self.app.state.caztor.env = {"PATH": f"{bin_dir}:/usr/bin:/bin", "CAZTOR_HOME": str(home)}
        self.addCleanup(self.app.state.caztor.stop)
        self.cookie = {server.TERMINAL_COOKIE: self.app.state.terminal.token}

    def post(self, path: str, cookies: dict[str, str] | None = None):
        response = asyncio.run(_post(self.app, path)(_Request(self.HERE, cookies)))
        return response.status_code, json.loads(bytes(response.body))

    def test_the_logged_in_browser_gets_the_frame_key(self) -> None:
        status, body = self.post("/api/terminal/caztor", self.cookie)
        self.assertEqual(status, 200)
        self.assertTrue(body["available"])
        self.assertEqual(body["key"], self.app.state.caztor._key)
        self.assertGreaterEqual(len(body["key"]), 32)

    def test_without_the_cookie_it_is_refused_and_nothing_starts(self) -> None:
        for path in ("/api/terminal/caztor", "/api/caztor"):
            for cookies in (None, {server.TERMINAL_COOKIE: "not-the-secret"}):
                with self.subTest(path=path, cookies=cookies):
                    status, body = self.post(path, cookies)
                    self.assertEqual(status, 403)
                    self.assertEqual(body["error"], "TERMINAL_LOGIN_REQUIRED")
                    self.assertFalse(body["available"])
                    self.assertIn("access link", body["reason"])
                    self.assertNotIn("key", body)
        self.assertFalse((self.bin_dir / "args").exists())

    def test_stop_needs_the_cookie_too(self) -> None:
        self.post("/api/terminal/caztor", self.cookie)
        for path in ("/api/terminal/caztor/stop", "/api/caztor/stop"):
            with self.subTest(path=path):
                status, body = self.post(path)
                self.assertEqual(status, 403)
                self.assertEqual(body["error"], "TERMINAL_LOGIN_REQUIRED")
                self.assertTrue(self.app.state.caztor._alive())
        self.assertEqual(self.post("/api/terminal/caztor/stop", self.cookie), (200, {"stopped": True}))
        self.assertFalse(self.app.state.caztor._alive())


if __name__ == "__main__":
    unittest.main()


class ShutdownStopsCaztorTests(unittest.TestCase):
    """An open event stream kept uvicorn waiting forever on shutdown, so the lifespan never stopped Caztor and it
    kept its port: the dashboard bounds that wait and stops Caztor when the process exits in any case."""

    def test_main_bounds_the_shutdown_wait_and_stops_caztor_at_exit(self) -> None:
        from unittest import mock

        with mock.patch.object(server, "create_app") as created, \
                mock.patch("uvicorn.run") as run, \
                mock.patch.object(server.atexit, "register") as register:
            server.main(["--root", ".", "--port", "8099", "--no-browser", "--no-refresh"])

        self.assertEqual(run.call_args.kwargs["timeout_graceful_shutdown"], server.SHUTDOWN_GRACE_SECONDS)
        self.assertLessEqual(server.SHUTDOWN_GRACE_SECONDS, 5)
        register.assert_any_call(created.return_value.state.caztor.stop)


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

