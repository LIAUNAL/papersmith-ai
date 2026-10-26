"""The command center HTTP surface: payloads, SSE framing, static export.

Endpoints are exercised through their ASGI route functions rather than a live
socket, so these stay fast and hermetic. The end-to-end HTTP journey lives in
``scripts/command-center-smoke.sh``.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from skills._core.command_center import server


def _routes(app) -> dict:
    # Mounts (StaticFiles) expose `.app`, not `.endpoint`; keep only API routes.
    return {
        route.path: route.endpoint
        for route in app.routes
        if hasattr(route, "path") and hasattr(route, "endpoint")
    }


def _json(response) -> dict:
    return json.loads(bytes(response.body).decode("utf-8"))


class _FakeRequest:
    """Minimal stand-in for the Starlette request the endpoint reads headers from."""

    def __init__(self, headers: dict | None = None) -> None:
        self.headers = headers or {}


class ServerEndpointTests(unittest.TestCase):
    def new_workspace(self) -> Path:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        root = Path(holder.name).resolve()
        (root / "sections").mkdir(parents=True)
        (root / "paper").mkdir()
        return root

    def test_state_endpoint_returns_the_contract_payload(self) -> None:
        root = self.new_workspace()
        app = server.create_app(root)
        payload = _json(_routes(app)["/api/state"]())

        assert set(payload) >= {"paper_metadata", "sections", "gates", "pipeline_stages"}

    def test_health_endpoint_reports_the_summary(self) -> None:
        root = self.new_workspace()
        app = server.create_app(root)
        payload = _json(_routes(app)["/api/health/wiring"]())

        assert payload["summary"]["components_total"] >= 1
        assert payload["summary"]["state"] in ("HEALTHY", "DEGRADED", "BLOCKED")

    def test_health_endpoint_caches_between_calls(self) -> None:
        root = self.new_workspace()
        app = server.create_app(root, health_ttl=60.0)
        endpoint = _routes(app)["/api/health/wiring"]

        first = _json(endpoint())
        second = _json(endpoint())

        assert first == second

    def test_run_wiring_smoke_reports_absence_without_crashing(self) -> None:
        root = self.new_workspace()
        app = server.create_app(root)
        payload = _json(_routes(app)["/api/health/run-wiring-smoke"](_FakeRequest()))

        assert payload["available"] is False
        assert payload["exit_code"] is None
        assert "cli-paper-wiring-smoke.sh" in payload["detail"]

    def test_run_wiring_smoke_rejects_a_cross_origin_post(self) -> None:
        root = self.new_workspace()
        app = server.create_app(root)
        request = _FakeRequest({"origin": "https://evil.example", "host": "127.0.0.1:8080"})

        response = _routes(app)["/api/health/run-wiring-smoke"](request)

        assert response.status_code == 403
        assert _json(response)["detail"] == "cross-origin request rejected"

    def test_run_wiring_smoke_allows_a_same_origin_post(self) -> None:
        root = self.new_workspace()
        app = server.create_app(root)
        request = _FakeRequest({"origin": "http://127.0.0.1:8080", "host": "127.0.0.1:8080"})

        response = _routes(app)["/api/health/run-wiring-smoke"](request)

        assert response.status_code == 200

    def test_run_wiring_smoke_returns_409_while_one_is_running(self) -> None:
        root = self.new_workspace()
        app = server.create_app(root)
        app.state.smoke_lock.acquire()
        self.addCleanup(app.state.smoke_lock.release)

        response = _routes(app)["/api/health/run-wiring-smoke"](_FakeRequest())

        assert response.status_code == 409
        assert "already in progress" in _json(response)["detail"]

    def test_a_health_path_flush_publishes_health_update(self) -> None:
        """Editing a harness surface must publish `health_update`; otherwise
        the Health tab can never refresh live."""
        root = self.new_workspace()
        (root / ".claude" / "agents").mkdir(parents=True)
        app = server.create_app(root)

        events = self._flush_events(app, root / ".claude" / "agents" / "redactor.md")
        kinds = {event["event"] for event in events}

        assert "state_update" in kinds
        assert "health_update" in kinds

    def test_a_section_flush_does_not_publish_health_update(self) -> None:
        root = self.new_workspace()
        app = server.create_app(root)

        events = self._flush_events(app, root / "sections" / "01-x.md")
        kinds = {event["event"] for event in events}

        assert "state_update" in kinds
        assert "health_update" not in kinds

    @staticmethod
    def _flush_events(app, changed: Path) -> list[dict]:
        async def scenario() -> list[dict]:
            bus = app.state.bus
            bus.bind_loop(asyncio.get_running_loop())
            queue = bus.subscribe()
            app.state.watcher.on_flush([changed])
            await asyncio.sleep(0.1)
            events = []
            while not queue.empty():
                events.append(await queue.get())
            return events

        return asyncio.run(scenario())

    def test_placeholder_root_is_served_without_a_build(self) -> None:
        root = self.new_workspace()
        with mock.patch.object(server, "resolve_static_dir", return_value=None):
            app = server.create_app(root)
        body = _routes(app)["/"]()
        assert "Paper Command Center" in body

    def test_export_static_refuses_an_empty_build(self) -> None:
        root = self.new_workspace()
        destination = root / "exported"
        with mock.patch.object(server, "resolve_static_dir", return_value=None):
            assert server.export_static(root, destination) == 2
        assert not destination.exists()

    def test_export_static_refuses_a_destination_that_is_a_file(self) -> None:
        root = self.new_workspace()
        build = root / "ui" / "dist"
        build.mkdir(parents=True)
        (build / "index.html").write_text("<html>dashboard</html>", encoding="utf-8")
        destination = root / "already-a-file"
        destination.write_text("not a directory", encoding="utf-8")

        assert server.export_static(root, destination) == 2
        assert destination.read_text(encoding="utf-8") == "not a directory"

    def test_export_static_copies_a_workspace_build(self) -> None:
        root = self.new_workspace()
        build = root / "ui" / "dist"
        build.mkdir(parents=True)
        (build / "index.html").write_text("<html>dashboard</html>", encoding="utf-8")
        destination = root / "exported"

        assert server.export_static(root, destination) == 0
        assert (destination / "index.html").read_text(encoding="utf-8") == "<html>dashboard</html>"

    def test_resolve_static_dir_prefers_the_env_override(self) -> None:
        root = self.new_workspace()
        override = root / "override"
        override.mkdir()
        (override / "index.html").write_text("<html>override</html>", encoding="utf-8")
        previous = os.environ.get("PAPERSMITH_UI_DIST")
        os.environ["PAPERSMITH_UI_DIST"] = str(override)
        self.addCleanup(self._restore_env, previous)

        assert server.resolve_static_dir(root) == override

    def test_resolve_static_dir_prefers_a_workspace_build(self) -> None:
        root = self.new_workspace()
        build = root / "ui" / "dist"
        build.mkdir(parents=True)
        (build / "index.html").write_text("<html>workspace</html>", encoding="utf-8")
        previous = os.environ.pop("PAPERSMITH_UI_DIST", None)
        self.addCleanup(self._restore_env, previous)

        assert server.resolve_static_dir(root) == build

    def test_resolve_static_dir_falls_back_to_the_shipped_build(self) -> None:
        root = self.new_workspace()
        previous = os.environ.pop("PAPERSMITH_UI_DIST", None)
        self.addCleanup(self._restore_env, previous)
        shipped = Path(server.__file__).resolve().parent / "static"
        if not (shipped / "index.html").is_file():
            self.skipTest("no shipped dashboard build in this checkout")

        assert server.resolve_static_dir(root) == shipped

    @staticmethod
    def _restore_env(previous: str | None) -> None:
        if previous is None:
            os.environ.pop("PAPERSMITH_UI_DIST", None)
        else:
            os.environ["PAPERSMITH_UI_DIST"] = previous


class SseFramingTests(unittest.TestCase):
    def test_format_sse_repeats_the_event_type_in_the_body(self) -> None:
        frame = server.format_sse("state_update", {"revision": 2})

        assert frame.startswith("event: state_update\ndata: ")
        assert frame.endswith("\n\n")
        body = json.loads(frame.split("data: ", 1)[1].strip())
        assert body == {"type": "state_update", "payload": {"revision": 2}}

    def test_event_stream_emits_ready_then_a_published_event(self) -> None:
        class FakeRequest:
            async def is_disconnected(self) -> bool:
                return False

        async def scenario() -> list[str]:
            bus = server.EventBus()
            bus.bind_loop(asyncio.get_running_loop())
            stream = server._event_stream(FakeRequest(), bus, Path("/tmp/x"))
            frames = [await anext(stream)]
            bus.publish("state_update", {"revision": 1})
            frames.append(await asyncio.wait_for(anext(stream), timeout=1.0))
            await stream.aclose()
            return frames

        frames = asyncio.run(scenario())
        assert "ready" in frames[0]
        assert "state_update" in frames[1]


class BrowserLaunchTests(unittest.TestCase):
    def test_wsl_hands_the_url_to_windows_before_python_webbrowser(self) -> None:
        url = "http://127.0.0.1:8080/api/terminal/login?token=private&next=home"
        explorer = "/mnt/c/Windows/explorer.exe"
        with (mock.patch("webbrowser.open", return_value=False) as browser,
              mock.patch.object(server, "_is_wsl", return_value=True),
              mock.patch.object(server.shutil, "which",
                                lambda name: explorer if name == "explorer.exe" else None),
              mock.patch.object(server.subprocess, "Popen") as launch):
            server.open_browser(url)

        browser.assert_not_called()
        launch.assert_called_once_with(
            [explorer, url], stdin=server.subprocess.DEVNULL,
            stdout=server.subprocess.DEVNULL, stderr=server.subprocess.DEVNULL,
            close_fds=True,
        )

    def test_wsl_without_windows_launchers_uses_python_webbrowser_on_a_display(self) -> None:
        with (mock.patch("webbrowser.open", return_value=True) as browser,
              mock.patch.object(server, "_is_wsl", return_value=True),
              mock.patch.object(server.sys, "platform", "linux"),
              mock.patch.dict(os.environ, {"DISPLAY": ":0"}),
              mock.patch.object(server.shutil, "which", return_value=None),
              mock.patch.object(server.subprocess, "Popen") as launch):
            server.open_browser("http://localhost:8080/")
        browser.assert_called_once_with("http://localhost:8080/")
        launch.assert_not_called()

    def test_non_wsl_does_not_launch_windows_browser(self) -> None:
        with (mock.patch("webbrowser.open", return_value=False),
              mock.patch.object(server, "_is_wsl", return_value=False),
              mock.patch.object(server.subprocess, "Popen") as launch):
            server.open_browser("http://localhost:8080/")
        launch.assert_not_called()

    def test_wsl_detection_uses_kernel_release_not_environment(self) -> None:
        with (mock.patch.object(server.sys, "platform", "linux"),
              mock.patch.object(server.platform, "release", return_value="5.15.0-microsoft-standard-WSL2")):
            assert server._is_wsl()
        with (mock.patch.object(server.sys, "platform", "linux"),
              mock.patch.object(server.platform, "release", return_value="6.8.0-generic"),
              mock.patch.dict(os.environ, {"WSL_DISTRO_NAME": "Ubuntu"})):
            assert not server._is_wsl()
        with (mock.patch.object(server.sys, "platform", "darwin"),
              mock.patch.object(server.platform, "release", return_value="microsoft")):
            assert not server._is_wsl()

    def test_wsl_browser_failure_does_not_expose_login_url(self) -> None:
        url = "http://localhost:8080/api/terminal/login?token=private"
        with (mock.patch("webbrowser.open", side_effect=RuntimeError("no browser")),
              mock.patch.object(server, "_is_wsl", return_value=True),
              mock.patch.object(server.subprocess, "Popen", side_effect=OSError(url))):
            server.open_browser(url)  # No exception with the token escapes.

    def test_no_browser_skips_launch_even_on_wsl(self) -> None:
        root = Path(".")
        app = mock.Mock()
        app.state.terminal_enabled = False
        with (mock.patch.object(server, "create_app", return_value=app),
              mock.patch.object(server.threading, "Timer") as timer,
              mock.patch("uvicorn.run")):
            assert server.main(["--root", str(root), "--no-browser"]) == 0
        timer.assert_not_called()


class CliParserTests(unittest.TestCase):
    def test_parser_defaults_match_the_documented_flags(self) -> None:
        args = server.build_parser().parse_args([])

        assert args.host == "127.0.0.1"
        assert args.port == 8080
        assert args.no_browser is False
        assert args.export_static is None

    def test_parser_accepts_the_smoke_test_invocation(self) -> None:
        args = server.build_parser().parse_args(["--port", "9876", "--no-browser", "--root", "."])

        assert args.port == 9876
        assert args.no_browser is True
