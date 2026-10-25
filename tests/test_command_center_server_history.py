"""History wiring and the Host allow-list on the command center server.

The allow-list tests drive the real ASGI app with a raw ``await app(scope,
receive, send)`` harness, so no HTTP client dependency is needed.
"""

from __future__ import annotations

import asyncio
import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from skills._core.command_center import history, server


def _routes(app) -> dict:
    return {r.path: r.endpoint for r in app.routes
            if hasattr(r, "path") and hasattr(r, "endpoint")}


def _json(response) -> dict:
    return json.loads(bytes(response.body).decode("utf-8"))


class _FakeRequest:
    def __init__(self, headers: dict | None = None) -> None:
        self.headers = headers or {}


def _state(words: int = 0, status: str = "CONTRACTED") -> dict:
    return {
        "generated_at": "t",
        "sections": [{"id": "01-intro", "status": status, "blocks_written": 0,
                      "word_count": words}],
        "gates": [], "pipeline_stages": [],
    }


def _health(overall: str = "HEALTHY") -> dict:
    return {"summary": {"state": overall}, "harness_sync": {"harnesses": []}}


class _Workspace(unittest.TestCase):
    def new_workspace(self) -> Path:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        root = Path(holder.name).resolve()
        (root / "sections").mkdir(parents=True)
        return root

    @staticmethod
    def flush(app, changed: Path) -> list[dict]:
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


class HistoryEndpointTests(_Workspace):
    def test_create_app_owns_a_history_store_unless_one_is_given(self) -> None:
        root = self.new_workspace()
        own = server.create_app(root)
        given = history.HistoryStore()
        injected = server.create_app(root, history_store=given)

        assert isinstance(own.state.history, history.HistoryStore)
        assert injected.state.history is given

    def test_history_endpoint_returns_the_page_shape(self) -> None:
        app = server.create_app(self.new_workspace())
        app.state.history.add("health", None, "x", "A", "B")

        payload = _json(_routes(app)["/api/history"]())

        assert set(payload) == {"boot_id", "entries", "has_more", "reset", "gap"}
        assert payload["entries"][0]["summary"] == "x"

    def test_history_endpoint_passes_filters_through(self) -> None:
        app = server.create_app(self.new_workspace())
        app.state.history.add("gate", "gate:g", "a", 1, 2)
        app.state.history.add("health", None, "b", 1, 2)

        payload = _json(_routes(app)["/api/history"](kind="gate", limit=1))

        assert [e["summary"] for e in payload["entries"]] == ["a"]

    def test_history_endpoint_rejects_invalid_filters_with_422(self) -> None:
        app = server.create_app(self.new_workspace())
        endpoint = _routes(app)["/api/history"]

        bad_element = endpoint(element="edge:x")
        bad_kind = endpoint(kind="bogus")

        assert bad_element.status_code == 422 and bad_kind.status_code == 422
        assert "element" in _json(bad_element)["detail"]


class HistoryRecordingTests(_Workspace):
    def test_a_flush_records_a_change_after_publishing_state_update(self) -> None:
        root = self.new_workspace()
        with mock.patch.object(server, "get_workspace_state",
                               side_effect=[_state(0), _state(40)]):
            app = server.create_app(root)
            events = self.flush(app, root / "sections" / "01-intro.md")

        names = [e["event"] for e in events]
        assert names == ["state_update", "history_append"]
        entry = events[1]["data"]
        assert entry["kind"] == "section_words"
        assert entry["element_id"] == "section:01-intro"
        assert app.state.history.page()["entries"][0]["id"] == entry["id"]

    def test_an_unchanged_state_records_nothing(self) -> None:
        root = self.new_workspace()
        with mock.patch.object(server, "get_workspace_state", return_value=_state(5)):
            app = server.create_app(root)
            events = self.flush(app, root / "sections" / "01-intro.md")

        assert [e["event"] for e in events] == ["state_update"]
        assert app.state.history.page()["entries"] == []

    def test_a_raising_extractor_does_not_break_create_app_and_baselines_later(self) -> None:
        root = self.new_workspace()
        with mock.patch.object(server, "get_workspace_state",
                               side_effect=[RuntimeError("boom"), _state(1), _state(2)]):
            app = server.create_app(root)
            first = self.flush(app, root / "sections" / "01-intro.md")
            assert app.state.history.page()["entries"] == []
            second = self.flush(app, root / "sections" / "01-intro.md")

        assert [e["event"] for e in first] == ["state_update"]
        assert [e["event"] for e in second] == ["state_update", "history_append"]

    def test_a_history_failure_never_blocks_state_update(self) -> None:
        root = self.new_workspace()
        with mock.patch.object(server, "get_workspace_state",
                               side_effect=[_state(0), _state(9)]), \
                mock.patch.object(server.history, "diff_states", side_effect=RuntimeError("x")):
            app = server.create_app(root)
            events = self.flush(app, root / "sections" / "01-intro.md")

        assert [e["event"] for e in events] == ["state_update"]

    def test_health_changes_are_recorded_on_the_ttl_path(self) -> None:
        app = server.create_app(self.new_workspace(), health_ttl=0.0)
        values = [_health("HEALTHY"), _health("HEALTHY"), _health("DEGRADED")]
        with mock.patch.object(server, "get_wiring_health", side_effect=values):
            for _ in range(3):
                app.state.measure_health()

        entries = app.state.history.page()["entries"]
        assert [(e["kind"], e["before"], e["after"]) for e in entries] == [
            ("health", "HEALTHY", "DEGRADED")]

    def test_health_changes_are_recorded_on_the_forced_path(self) -> None:
        app = server.create_app(self.new_workspace(), health_ttl=600.0)
        with mock.patch.object(server, "get_wiring_health",
                               side_effect=[_health("HEALTHY"), _health("BLOCKED")]):
            app.state.measure_health()
            app.state.measure_health(force=True)

        assert len(app.state.history.page(kind="health")["entries"]) == 1

    def test_a_cached_health_read_records_nothing(self) -> None:
        app = server.create_app(self.new_workspace(), health_ttl=600.0)
        with mock.patch.object(server, "get_wiring_health",
                               side_effect=[_health("HEALTHY")]) as measured:
            app.state.measure_health()
            app.state.measure_health()

        assert measured.call_count == 1
        assert app.state.history.page()["entries"] == []

    def test_smoke_start_and_done_are_recorded_with_the_exit_code(self) -> None:
        root = self.new_workspace()
        (root / "scripts").mkdir()
        (root / "scripts" / "cli-paper-wiring-smoke.sh").write_text("echo hi\nexit 3\n")
        app = server.create_app(root)

        _routes(app)["/api/health/run-wiring-smoke"](_FakeRequest())

        entries = app.state.history.page(kind="smoke")["entries"]
        assert [e["after"]["phase"] for e in entries] == ["started", "done"]
        assert entries[1]["after"]["exit_code"] == 3
        assert all(e["element_id"] is None for e in entries)

    def test_smoke_events_publish_history_append(self) -> None:
        root = self.new_workspace()
        (root / "scripts").mkdir()
        (root / "scripts" / "cli-paper-wiring-smoke.sh").write_text("exit 0\n")
        app = server.create_app(root)

        async def scenario() -> list[str]:
            app.state.bus.bind_loop(asyncio.get_running_loop())
            queue = app.state.bus.subscribe()
            await asyncio.to_thread(
                _routes(app)["/api/health/run-wiring-smoke"], _FakeRequest())
            await asyncio.sleep(0.1)
            names = []
            while not queue.empty():
                names.append((await queue.get())["event"])
            return names

        assert asyncio.run(scenario()).count("history_append") == 2


async def _call(app, path: str = "/api/history", *, method: str = "GET",
                headers: list[tuple[bytes, bytes]] | None = None) -> tuple[int, bytes]:
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": method, "scheme": "http", "path": path, "raw_path": path.encode(),
        "query_string": b"", "root_path": "", "headers": headers or [],
        "server": ("127.0.0.1", 8099), "client": ("127.0.0.1", 50000),
    }
    messages: list[dict] = []

    async def receive() -> dict:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict) -> None:
        messages.append(message)

    await app(scope, receive, send)
    status = next(m["status"] for m in messages if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    return status, body


def _host(value: str) -> list[tuple[bytes, bytes]]:
    return [(b"host", value.encode())]


class HostAllowListTests(_Workspace):
    def app(self, allowed):
        return server.create_app(self.new_workspace(), allowed_hosts=allowed)

    def test_an_allowed_host_passes(self) -> None:
        app = self.app(frozenset({"127.0.0.1:8099"}))

        status, _ = asyncio.run(_call(app, headers=_host("127.0.0.1:8099")))

        assert status == 200

    def test_a_foreign_host_gets_421_with_an_explanation(self) -> None:
        app = self.app(frozenset({"127.0.0.1:8099"}))

        status, body = asyncio.run(_call(app, headers=_host("evil.example:8099")))

        assert status == 421
        assert b"--allowed-host" in body and b"evil.example:8099" in body
        assert b"smith ui --allowed-host" in body

    def test_a_missing_host_is_rejected_when_active(self) -> None:
        status, _ = asyncio.run(_call(self.app(frozenset({"127.0.0.1:8099"}))))

        assert status == 421

    def test_the_match_is_case_insensitive(self) -> None:
        app = self.app(frozenset({"localhost:8099"}))

        status, _ = asyncio.run(_call(app, headers=_host("LocalHost:8099")))

        assert status == 200

    def test_none_disables_the_check(self) -> None:
        app = self.app(None)

        assert asyncio.run(_call(app, headers=_host("anything:1")))[0] == 200
        assert asyncio.run(_call(app))[0] == 200

    def test_a_host_without_the_port_is_not_the_allowed_origin(self) -> None:
        app = self.app(frozenset({"127.0.0.1:8099"}))

        assert asyncio.run(_call(app, headers=_host("127.0.0.1")))[0] == 421

    def test_the_dev_proxy_combination_passes_allow_list_and_origin_check(self) -> None:
        app = self.app(frozenset({"127.0.0.1:8080", "localhost:5173"}))
        headers = _host("localhost:5173") + [(b"origin", b"http://localhost:5173")]

        status, body = asyncio.run(_call(
            app, "/api/health/run-wiring-smoke", method="POST", headers=headers))

        assert status == 200, body
        assert json.loads(body)["available"] is False

    def test_a_foreign_origin_on_an_allowed_host_still_fails_the_origin_check(self) -> None:
        app = self.app(frozenset({"localhost:5173"}))
        headers = _host("localhost:5173") + [(b"origin", b"http://evil.example")]

        status, _ = asyncio.run(_call(
            app, "/api/health/run-wiring-smoke", method="POST", headers=headers))

        assert status == 403

    def test_a_network_bind_keeps_the_host_and_origin_checks(self) -> None:
        app = self.app(server.build_allowed_hosts("0.0.0.0", 8099, ["dash.example:443"]))
        foreign = _host("dash.example:443") + [(b"origin", b"http://evil.example")]

        assert asyncio.run(_call(app, headers=_host("dash.example:443")))[0] == 200
        assert asyncio.run(_call(app, headers=_host("0.0.0.0:8099")))[0] == 200
        assert asyncio.run(_call(app, headers=_host("evil.example:8099")))[0] == 421
        assert asyncio.run(_call(app))[0] == 421
        assert asyncio.run(_call(
            app, "/api/health/run-wiring-smoke", method="POST", headers=foreign))[0] == 403


class MainWiringTests(unittest.TestCase):
    def test_parser_collects_repeatable_allowed_hosts(self) -> None:
        args = server.build_parser().parse_args(
            ["--allowed-host", "localhost:5173", "--allowed-host", "box:9"])

        assert args.allowed_host == ["localhost:5173", "box:9"]
        assert server.build_parser().parse_args([]).allowed_host == []

    def test_loopback_binds_get_the_loopback_set_plus_extras(self) -> None:
        hosts = server.build_allowed_hosts("127.0.0.1", 8099, ["Localhost:5173"])

        assert hosts == frozenset({"127.0.0.1:8099", "localhost:8099", "[::1]:8099",
                                   "localhost:5173"})

    def test_non_loopback_binds_keep_the_check_on_their_own_address(self) -> None:
        assert server.build_allowed_hosts("0.0.0.0", 8099, ["X:1"]) == frozenset(
            {"0.0.0.0:8099", "x:1"})
        assert server.build_allowed_hosts("::", 8099) == frozenset({"[::]:8099"})
        assert server.build_allowed_hosts("[fe80::1]", 8099) == frozenset({"[fe80::1]:8099"})

    def test_any_loopback_literal_also_gets_the_loopback_names(self) -> None:
        assert server.build_allowed_hosts("127.0.0.2", 8099) == frozenset(
            {"127.0.0.2:8099", "127.0.0.1:8099", "localhost:8099", "[::1]:8099"})

    def test_main_passes_the_allow_list_to_create_app(self) -> None:
        with mock.patch.object(server, "create_app") as created, \
                mock.patch("uvicorn.run") as run:
            server.main(["--root", ".", "--port", "8099", "--no-browser",
                         "--allowed-host", "localhost:5173"])

        assert created.call_args.kwargs["allowed_hosts"] == frozenset(
            {"127.0.0.1:8099", "localhost:8099", "[::1]:8099", "localhost:5173"})
        run.assert_called_once()


class NetworkExposureTests(unittest.TestCase):
    """#61: the dashboard has no authentication, so a bind the network can
    reach is refused unless named by flag, and the Host check stays on."""

    NETWORK = ("0.0.0.0", "::", "[::]", "192.168.1.5", "dashboard.example", "localhost.example")
    LOOPBACK = ("127.0.0.1", "127.0.0.2", "localhost", "LocalHost", "::1", "[::1]")

    def _main(self, *flags: str):
        stderr = io.StringIO()
        with mock.patch.object(server, "create_app") as created, \
                mock.patch("uvicorn.run") as run, contextlib.redirect_stderr(stderr):
            try:
                code = server.main(["--root", ".", "--port", "8099", "--no-browser", *flags])
            except SystemExit as stop:
                code = stop.code
        return code, created, run, stderr.getvalue()

    def test_only_loopback_names_and_literals_are_loopback_binds(self) -> None:
        for host in self.LOOPBACK:
            with self.subTest(host=host):
                assert server.is_loopback_bind(host)
        for host in (*self.NETWORK, ""):
            with self.subTest(host=host):
                assert not server.is_loopback_bind(host)

    def test_the_terminal_is_offered_on_exactly_the_loopback_binds(self) -> None:
        # main() refuses a network bind and withholds the terminal by one rule,
        # so neither can drift from the other.
        for host in (*self.LOOPBACK, *self.NETWORK, ""):
            with self.subTest(host=host):
                assert server.terminal_allowed(host) == server.is_loopback_bind(host)

    def test_a_network_bind_is_refused_without_the_flag(self) -> None:
        for host in self.NETWORK:
            with self.subTest(host=host):
                code, created, run, stderr = self._main(f"--host={host}")

                assert code == 2
                created.assert_not_called()
                run.assert_not_called()
                assert "no authentication" in stderr
                assert "--allow-unauthenticated-network" in stderr

    def test_the_flag_serves_a_network_bind_with_the_check_still_on(self) -> None:
        code, created, run, _ = self._main(
            "--host", "0.0.0.0", "--allow-unauthenticated-network",
            "--allowed-host", "dash.example:443")

        assert code == 0
        assert created.call_args.kwargs["allowed_hosts"] == frozenset(
            {"0.0.0.0:8099", "dash.example:443"})
        assert run.call_args.kwargs["host"] == "0.0.0.0"

    def test_a_loopback_bind_needs_no_flag(self) -> None:
        for host in self.LOOPBACK:
            with self.subTest(host=host):
                code, created, run, _ = self._main(f"--host={host}")

                assert code == 0
                run.assert_called_once()
                assert "localhost:8099" in created.call_args.kwargs["allowed_hosts"]

    def test_export_static_binds_nothing_so_is_not_refused(self) -> None:
        with mock.patch.object(server, "export_static", return_value=0) as exported, \
                mock.patch("uvicorn.run") as run:
            code = server.main(["--host", "0.0.0.0", "--export-static", "out"])

        assert code == 0
        exported.assert_called_once()
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
