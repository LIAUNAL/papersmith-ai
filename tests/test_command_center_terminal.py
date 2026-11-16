"""The support terminal ("CLI de apoyo"): a PTY per session, output over SSE,
input over POST, and request guards that keep other origins out."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import time
import unittest
from unittest import mock
from pathlib import Path

from skills._core.command_center import server, terminal

POSIX = os.name == "posix"


class _Request:
    def __init__(self, headers: dict[str, str] | None = None, body: object = None,
                 cookies: dict[str, str] | None = None) -> None:
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}
        self._body = body
        self.cookies = dict(cookies or {})
        self.scope = {"server": ("127.0.0.1", 8080)}

    async def json(self) -> object:
        if isinstance(self._body, Exception):
            raise self._body
        return self._body

    async def is_disconnected(self) -> bool:
        return False


SAME = {"Host": "127.0.0.1:8080", "Origin": "http://127.0.0.1:8080",
        "Sec-Fetch-Site": "same-origin", "Content-Type": "application/json",
        "X-Papersmith-Terminal": "1"}


def _route(app, path: str, method: str):
    for route in app.routes:
        if getattr(route, "path", None) == path and method in (getattr(route, "methods", None) or ()):
            return route.endpoint
    raise AssertionError(f"no {method} {path}")


def _call(endpoint, *args, **kwargs):
    result = endpoint(*args, **kwargs)
    if asyncio.iscoroutine(result):
        result = asyncio.run(result)
    return result


def _body(response) -> dict:
    return json.loads(bytes(response.body).decode("utf-8"))


@unittest.skipUnless(POSIX, "the support terminal needs a POSIX pty")
class ManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.root = Path(holder.name).resolve()
        self.manager = terminal.TerminalManager(self.root, agents={
            "shell": terminal.Agent("shell", "Shell", ["/bin/sh"]),
            "missing": terminal.Agent("missing", "Missing", ["definitely-not-on-path-xyz"]),
        })
        self.addCleanup(self.manager.close_all)

    def read_until(self, sid: str, needle: bytes, timeout: float = 5.0) -> bytes:
        seen, offset, deadline = b"", 0, time.monotonic() + timeout
        while time.monotonic() < deadline:
            chunk, offset, _alive = self.manager.read_since(sid, offset)
            seen += chunk
            if needle in seen:
                return seen
            time.sleep(0.02)
        self.fail(f"{needle!r} never arrived; saw {seen[-300:]!r}")

    def test_only_agents_on_path_are_available(self) -> None:
        listed = {a["id"]: a["available"] for a in self.manager.agents()}
        self.assertEqual(listed, {"shell": True, "missing": False})

    def test_a_session_runs_in_the_workspace_and_echoes_input(self) -> None:
        session = self.manager.create("shell", cols=100, rows=30)
        self.manager.write(session.id, "pwd; echo papersmith-$((40+2))\n")
        out = self.read_until(session.id, b"papersmith-42")
        self.assertIn(str(self.root).encode(), out)

    def test_resize_reaches_the_pty(self) -> None:
        session = self.manager.create("shell", cols=80, rows=24)
        self.manager.resize(session.id, cols=123, rows=45)
        self.manager.write(session.id, "stty size\n")
        self.read_until(session.id, b"45 123")

    def test_sessions_that_ended_on_their_own_free_the_cap(self) -> None:
        for _ in range(terminal.MAX_SESSIONS):
            session = self.manager.create("shell", cols=80, rows=24)
            self.manager.write(session.id, "exit\n")
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and any(
                s.alive for s in list(self.manager._sessions.values())):
            time.sleep(0.05)
        fresh = self.manager.create("shell", cols=80, rows=24)
        self.assertEqual(self.manager.count(), 1)
        self.assertEqual(self.manager.get(fresh.id).agent, "shell")

    def test_the_token_is_secret_and_checked_in_constant_time(self) -> None:
        self.assertGreaterEqual(len(self.manager.token), 40)
        self.assertTrue(self.manager.authorized(self.manager.token))
        self.assertFalse(self.manager.authorized(None))
        token = self.manager.token
        altered = ("A" if token[0] != "A" else "B") + token[1:]
        self.assertFalse(self.manager.authorized(altered))
        # A malformed value is a wrong one, never an error (compare_digest
        # raises on non-ASCII str).
        for odd in ("é" * 43, "\udcff", 42, ""):
            self.assertFalse(self.manager.authorized(odd))
            self.assertFalse(self.manager.accepts_login(odd))

    def test_the_login_secret_is_never_the_cookie(self) -> None:
        # The login secret buys the cookie; neither opens the other's door.
        login, cookie = self.manager.login_token, self.manager.token
        self.assertGreaterEqual(len(login), 40)
        self.assertNotEqual(login, cookie)
        self.assertTrue(self.manager.accepts_login(login))
        self.assertFalse(self.manager.accepts_login(cookie))
        self.assertFalse(self.manager.authorized(login))

    def test_an_operator_secret_is_the_login_secret_only(self) -> None:
        secret = "s3cr3t-" + "x" * 30
        manager = terminal.TerminalManager(self.root, login_token=secret)
        self.assertEqual(manager.login_token, secret)
        self.assertNotEqual(manager.token, secret)
        with self.assertRaises(terminal.LoginTokenError):
            terminal.TerminalManager(self.root, login_token="too-short")

    def test_close_ends_the_process(self) -> None:
        session = self.manager.create("shell", cols=80, rows=24)
        self.manager.close(session.id)
        with self.assertRaises(KeyError):
            self.manager.get(session.id)

    def test_an_unknown_or_unavailable_agent_is_refused(self) -> None:
        with self.assertRaises(terminal.TerminalError):
            self.manager.create("nope", cols=80, rows=24)
        with self.assertRaises(terminal.TerminalError):
            self.manager.create("missing", cols=80, rows=24)

    def test_a_shell_keeps_the_herdr_variables_it_inherits(self) -> None:
        os.environ["HERDR_ENV"] = "from-outside"
        self.addCleanup(os.environ.pop, "HERDR_ENV", None)
        session = self.manager.create("shell", cols=100, rows=30)
        self.manager.write(session.id, "echo env=[$HERDR_ENV] ws=[$PAPERSMITH_WORKSPACE]\n")
        self.assertIn(b"env=[from-outside]", self.read_until(session.id, b"ws=[/"))

    def test_only_the_herdr_agent_drops_the_herdr_variables(self) -> None:
        os.environ.update({"HERDR_ENV": "x", "HERDR_PANE_ID": "p", "TERM_PROGRAM": "herdr"})
        for key in ("HERDR_ENV", "HERDR_PANE_ID", "TERM_PROGRAM"):
            self.addCleanup(os.environ.pop, key, None)
        herdr = terminal.session_env("herdr", self.root)
        self.assertFalse({"HERDR_ENV", "HERDR_PANE_ID", "TERM_PROGRAM"} & set(herdr))
        shell = terminal.session_env("shell", self.root)
        self.assertEqual((shell["HERDR_ENV"], shell["TERM_PROGRAM"]), ("x", "herdr"))

    def test_tool_dirs_are_appended_and_an_empty_path_adds_no_cwd(self) -> None:
        self.addCleanup(os.environ.__setitem__, "PATH", os.environ["PATH"])
        os.environ["PATH"] = "/usr/bin"
        parts = terminal.session_env("shell", self.root)["PATH"].split(os.pathsep)
        self.assertEqual(parts[0], "/usr/bin")
        os.environ["PATH"] = ""
        self.assertNotIn("", terminal.session_env("shell", self.root)["PATH"].split(os.pathsep))

    def test_the_session_cap_holds(self) -> None:
        for _ in range(terminal.MAX_SESSIONS):
            self.manager.create("shell", cols=80, rows=24)
        with self.assertRaises(terminal.TerminalError):
            self.manager.create("shell", cols=80, rows=24)


@unittest.skipUnless(POSIX, "the support terminal needs a POSIX pty")
class LauncherPlatformTests(unittest.TestCase):
    """S5: cross-platform external terminal launching (macOS unchanged, Linux added)."""

    ALL = {"ghostty", "wezterm", "gnome-terminal", "konsole",
           "x-terminal-emulator", "herdr"}

    def _detect(self, platform_name: str, available: set[str]) -> dict:
        finder = lambda name: f"/usr/bin/{name}" if name in available else None  # noqa: E731
        with mock.patch.object(terminal, "find_executable", side_effect=finder), \
                mock.patch.object(terminal, "_herdr_running_text", return_value=True), \
                mock.patch.object(sys, "platform", platform_name):
            return terminal.detect_tools(Path("/tmp/workspace"))

    def test_linux_detects_gnome_terminal(self) -> None:
        tools = self._detect("linux", {"herdr", "gnome-terminal", "konsole"})
        self.assertTrue(tools["ready"])
        self.assertEqual(tools["preferred_terminal"], "gnome-terminal")

    def test_linux_priority_prefers_ghostty_then_wezterm(self) -> None:
        self.assertEqual(self._detect("linux", {"herdr", "wezterm",
                                                "x-terminal-emulator"})["preferred_terminal"], "wezterm")
        self.assertEqual(self._detect("linux", {"herdr", "x-terminal-emulator"})["preferred_terminal"],
                         "x-terminal-emulator")

    def test_linux_without_a_terminal_reports_it_missing(self) -> None:
        tools = self._detect("linux", {"herdr"})
        self.assertFalse(tools["ready"])
        self.assertIn("terminal emulator", tools["missing"])

    def test_linux_launch_uses_gnome_terminal_without_open(self) -> None:
        with mock.patch.object(terminal, "find_executable",
                               side_effect=lambda n: f"/usr/bin/{n}" if n in {"herdr", "gnome-terminal"} else None), \
                mock.patch.object(terminal, "_herdr_running_text", return_value=True), \
                mock.patch.object(terminal, "ensure_herdr_workspace",
                                  return_value={"ok": True, "action": "focused"}), \
                mock.patch.object(sys, "platform", "linux"), \
                mock.patch.object(terminal.subprocess, "Popen") as popen:
            result = terminal.launch_external(Path("/tmp/workspace"))
        self.assertTrue(result["ok"])
        self.assertEqual(result["terminal"], "gnome-terminal")
        argv = popen.call_args[0][0]
        self.assertEqual(argv, ["gnome-terminal", "--working-directory=/tmp/workspace",
                                "--", "/usr/bin/herdr"])
        self.assertNotIn("open", argv)

    def test_linux_x_terminal_wraps_the_command_in_a_shell(self) -> None:
        with mock.patch.object(terminal, "find_executable",
                               side_effect=lambda n: f"/usr/bin/{n}" if n in {"herdr", "x-terminal-emulator"} else None), \
                mock.patch.object(terminal, "_herdr_running_text", return_value=True), \
                mock.patch.object(terminal, "ensure_herdr_workspace",
                                  return_value={"ok": True, "action": "focused"}), \
                mock.patch.object(sys, "platform", "linux"), \
                mock.patch.object(terminal.subprocess, "Popen") as popen:
            result = terminal.launch_external(Path("/tmp/workspace"))
        self.assertTrue(result["ok"])
        argv = popen.call_args[0][0]
        self.assertEqual(argv[:2], ["x-terminal-emulator", "-e"])
        self.assertIn("cd /tmp/workspace", argv[-1])

    def test_macos_launch_still_uses_open(self) -> None:
        with mock.patch.object(terminal, "find_executable",
                               side_effect=lambda n: "/usr/bin/herdr" if n == "herdr" else None), \
                mock.patch.object(terminal, "_herdr_running_text", return_value=True), \
                mock.patch.object(terminal, "ensure_herdr_workspace",
                                  return_value={"ok": True, "action": "focused"}), \
                mock.patch.object(terminal, "_app_installed",
                                  side_effect=lambda name: name == "Ghostty"), \
                mock.patch.object(sys, "platform", "darwin"), \
                mock.patch.object(terminal.subprocess, "run") as run:
            result = terminal.launch_external(Path("/tmp/workspace"))
        self.assertTrue(result["ok"])
        self.assertEqual(result["terminal"], "ghostty")
        self.assertEqual(run.call_args[0][0][0], "open")


class RouteTests(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.root = Path(holder.name).resolve()
        self.app = server.create_app(self.root, history_store=None, enable_terminal=True)
        self.addCleanup(self.app.state.terminal.close_all)
        self.app.state.terminal.agents_by_id["shell"] = terminal.Agent("shell", "Shell", ["/bin/sh"])

    def req(self, headers: dict[str, str], body: object = None, *, cookie: bool = True) -> _Request:
        token = self.app.state.terminal.token
        return _Request(headers, body, {server.TERMINAL_COOKIE: token} if cookie else None)

    def create(self, headers: dict[str, str], body: object = None, *, cookie: bool = True):
        return _call(_route(self.app, "/api/terminal/sessions", "POST"),
                     self.req(headers, body if body is not None else {"agent": "shell"}, cookie=cookie))

    def test_herdr_is_the_default_agent_when_installed(self) -> None:
        manager = terminal.TerminalManager(self.root)
        listed = [a["id"] for a in manager.agents()]
        self.assertEqual(listed[0], "herdr")
        self.assertEqual(listed, ["herdr", "claude", "opencode", "pi", "antigravity", "shell"])

    def test_tools_and_external_launch_require_the_token_and_same_origin(self) -> None:
        tools = _route(self.app, "/api/terminal/tools", "GET")
        self.assertEqual(_call(tools, self.req(SAME, cookie=False)).status_code, 403)
        body = _body(_call(tools, self.req(SAME)))
        self.assertIn("preferred_terminal", body["tools"])
        launch = _route(self.app, "/api/terminal/launch-external", "POST")
        self.assertEqual(_call(launch, self.req({**SAME, "Origin": "http://evil.example"}, {})).status_code, 403)
        self.assertEqual(_call(launch, self.req(SAME, {}, cookie=False)).status_code, 403)

    def test_a_local_client_without_the_token_is_refused(self) -> None:
        self.assertEqual(self.create(SAME, cookie=False).status_code, 403)
        agents = _body(_call(_route(self.app, "/api/terminal/agents", "GET"), self.req(SAME, cookie=False)))
        self.assertFalse(agents["authorized"])
        self.assertEqual(agents["agents"], [])
        self.assertEqual(self.app.state.terminal.count(), 0)

    def test_an_unauthorized_page_can_ask_the_server_to_reopen_its_login_url(self) -> None:
        activate = _route(self.app, "/api/terminal/activate", "POST")
        with mock.patch.object(server, "open_browser", return_value=True) as opened:
            response = _call(activate, self.req(SAME, {}, cookie=False))
        self.assertEqual(response.status_code, 200)
        body = _body(response)
        self.assertEqual(body, {"ok": True, "opened": True, "origin": "http://127.0.0.1:8080"})
        # The token goes to the OS browser only, for the host the page uses.
        url = opened.call_args[0][0]
        self.assertEqual(url, "http://127.0.0.1:8080/api/terminal/login?token="
                         + self.app.state.terminal.login_token)
        self.assertNotIn(self.app.state.terminal.login_token, json.dumps(body))
        self.assertNotIn(self.app.state.terminal.token, json.dumps(body))

    def test_activation_is_same_origin_only_and_throttled(self) -> None:
        activate = _route(self.app, "/api/terminal/activate", "POST")
        with mock.patch.object(server, "open_browser", return_value=True) as opened:
            foreign = _call(activate, self.req({**SAME, "Origin": "http://evil.example"}, {}, cookie=False))
            no_header = _call(activate, self.req({k: v for k, v in SAME.items()
                                                  if k != "X-Papersmith-Terminal"}, {}, cookie=False))
            first = _call(activate, self.req(SAME, {}, cookie=False))
            second = _call(activate, self.req(SAME, {}, cookie=False))
        self.assertEqual(foreign.status_code, 403)
        self.assertEqual(no_header.status_code, 403)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(_body(second), {"ok": True, "opened": False, "throttled": True})
        self.assertEqual(opened.call_count, 1)

    def test_activation_sends_the_token_only_to_the_bound_socket(self) -> None:
        # Host is never trusted: [::1] is a free socket on an IPv4-only bind,
        # which another local user could listen on to catch the token.
        for host in ("[::1]:8080", "localhost:8080", "evil.example", "127.0.0.1:80@evil.example", ""):
            self.app = server.create_app(self.root, history_store=None, enable_terminal=True)
            self.addCleanup(self.app.state.terminal.close_all)
            token = self.app.state.terminal.login_token
            headers = {**SAME, "Host": host}
            headers.pop("Origin")
            with mock.patch.object(server, "open_browser", return_value=True) as opened:
                _call(_route(self.app, "/api/terminal/activate", "POST"), self.req(headers, {}, cookie=False))
            self.assertEqual(opened.call_args[0][0],
                             f"http://127.0.0.1:8080/api/terminal/login?token={token}", host)

    def test_activation_refuses_a_server_off_loopback(self) -> None:
        activate = _route(self.app, "/api/terminal/activate", "POST")
        for bound in (("0.0.0.0", 8080), ("192.168.1.4", 8080), None, ("127.0.0.1", 0)):
            request = self.req(SAME, {}, cookie=False)
            request.scope = {"server": bound}
            with mock.patch.object(server, "open_browser") as opened:
                self.assertEqual(_call(activate, request).status_code, 403, bound)
            opened.assert_not_called()

    def test_an_ipv6_loopback_bind_is_bracketed(self) -> None:
        self.assertEqual(server._bound_origin(("::1", 9000)), "http://[::1]:9000")

    def test_activation_reports_a_login_url_it_could_only_print(self) -> None:
        activate = _route(self.app, "/api/terminal/activate", "POST")
        with mock.patch.object(server, "open_browser", return_value=False):
            body = _body(_call(activate, self.req(SAME, {}, cookie=False)))
        self.assertEqual(body, {"ok": True, "opened": False, "origin": "http://127.0.0.1:8080"})

    def test_activation_is_refused_when_the_terminal_is_disabled(self) -> None:
        app = server.create_app(self.root, history_store=None, enable_terminal=False)
        with mock.patch.object(server, "open_browser") as opened:
            response = _call(_route(app, "/api/terminal/activate", "POST"), _Request(SAME, {}))
        self.assertEqual(response.status_code, 404)
        opened.assert_not_called()

    def test_the_login_url_sets_the_cookie_only_for_the_right_token(self) -> None:
        login = _route(self.app, "/api/terminal/login", "GET")
        self.assertEqual(login("wrong").status_code, 403)
        # The cookie's own value buys nothing: only the login secret does.
        self.assertEqual(login(self.app.state.terminal.token).status_code, 403)
        ok = login(self.app.state.terminal.login_token)
        self.assertEqual(ok.status_code, 303)
        cookie = ok.headers["set-cookie"]
        self.assertIn(f"{server.TERMINAL_COOKIE}={self.app.state.terminal.token};", cookie)
        self.assertNotIn(self.app.state.terminal.login_token, cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=strict", cookie)

    def test_agents_are_listed_with_quick_commands(self) -> None:
        body = _body(_call(_route(self.app, "/api/terminal/agents", "GET"), self.req(SAME)))
        self.assertTrue(body["enabled"])
        self.assertIn("shell", {a["id"] for a in body["agents"]})
        self.assertIn("smith status", body["quick"]["shell"])

    def test_a_same_origin_client_opens_writes_and_closes(self) -> None:
        response = self.create(SAME)
        self.assertEqual(response.status_code, 200)
        sid = _body(response)["id"]
        write = _call(_route(self.app, "/api/terminal/sessions/{sid}/input", "POST"),
                      sid, self.req(SAME, {"data": "echo via-route\n"}))
        self.assertEqual(write.status_code, 200)
        closed = _call(_route(self.app, "/api/terminal/sessions/{sid}", "DELETE"), sid, self.req(SAME))
        self.assertEqual(closed.status_code, 200)

    def test_a_cross_origin_page_is_refused(self) -> None:
        for headers in (
            {**SAME, "Origin": "http://evil.example"},
            {**SAME, "Sec-Fetch-Site": "cross-site"},
            {k: v for k, v in SAME.items() if k != "X-Papersmith-Terminal"},
            {**SAME, "Content-Type": "text/plain"},
        ):
            with self.subTest(headers=headers):
                self.assertEqual(self.create(headers).status_code, 403)
        self.assertEqual(self.app.state.terminal.count(), 0)

    def test_the_stream_is_refused_cross_site(self) -> None:
        response = _call(_route(self.app, "/api/terminal/sessions/{sid}/stream", "GET"),
                         "x", self.req({**SAME, "Sec-Fetch-Site": "cross-site"}))
        self.assertEqual(response.status_code, 403)

    def test_a_session_can_be_looked_up_to_reattach_after_a_reload(self) -> None:
        sid = _body(self.create(SAME))["id"]
        lookup = _route(self.app, "/api/terminal/sessions/{sid}", "GET")
        self.assertEqual(_body(_call(lookup, sid, self.req(SAME))),
                         {"id": sid, "agent": "shell", "alive": True})
        self.assertEqual(_call(lookup, "nope", self.req(SAME)).status_code, 404)
        self.assertEqual(_call(lookup, sid, self.req(SAME, cookie=False)).status_code, 403)

    def test_an_unknown_session_is_404(self) -> None:
        response = _call(_route(self.app, "/api/terminal/sessions/{sid}/input", "POST"),
                         "nope", self.req(SAME, {"data": "x"}))
        self.assertEqual(response.status_code, 404)

    def test_a_malformed_body_is_422_and_opens_nothing(self) -> None:
        response = self.create(SAME, ValueError("not json"))
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.app.state.terminal.count(), 0)

    def test_an_unknown_agent_is_422(self) -> None:
        self.assertEqual(self.create(SAME, {"agent": "rm -rf"}).status_code, 422)


class DisabledTests(unittest.TestCase):
    def test_the_terminal_is_off_unless_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as holder:
            app = server.create_app(Path(holder), history_store=None)
            body = _body(_call(_route(app, "/api/terminal/agents", "GET"), _Request(SAME)))
            self.assertFalse(body["enabled"])
            response = _call(_route(app, "/api/terminal/sessions", "POST"),
                             _Request(SAME, {"agent": "shell"}))
            self.assertEqual(response.status_code, 404)

    def test_main_enables_it_only_on_loopback(self) -> None:
        self.assertTrue(server.terminal_allowed("127.0.0.1"))
        self.assertTrue(server.terminal_allowed("localhost"))
        self.assertFalse(server.terminal_allowed("0.0.0.0"))
        self.assertFalse(server.terminal_allowed("192.168.1.10"))
        # Off loopback only on the operator's explicit opt-in (--network-terminal).
        self.assertTrue(server.terminal_allowed("0.0.0.0", network_terminal=True))
        self.assertTrue(server.terminal_allowed("192.168.1.10", network_terminal=True))


    def test_smith_ui_forwards_no_terminal_only_when_asked(self) -> None:
        from papersmith.core import ui
        base = ui.build_server_argv(Path("/w"), "127.0.0.1", 8080, no_browser=True)
        self.assertNotIn("--no-terminal", base)
        off = ui.build_server_argv(Path("/w"), "127.0.0.1", 8080, no_browser=True, no_terminal=True)
        self.assertEqual(off[-1], "--no-terminal")
        self.assertTrue(server.build_parser().parse_args(["--no-terminal"]).no_terminal)


class DashboardWiringTests(unittest.TestCase):
    STATIC = Path(server.__file__).resolve().parent / "static"

    def page(self) -> str:
        return (self.STATIC / "index.html").read_text(encoding="utf-8")

    def test_the_console_ships_with_xterm_and_the_smith_face(self) -> None:
        for name in ("vendor/xterm.js", "vendor/xterm-addon-fit.js", "vendor/xterm.css",
                     "vendor/xterm-LICENSE", "cli-console.js", "smith-face.png"):
            self.assertTrue((self.STATIC / name).is_file(), name)

    def test_the_fab_sits_bottom_right_with_the_smith_face(self) -> None:
        page = self.page()
        self.assertIn('<script src="./cli-console.js?v=', page)
        self.assertIn('id="smithAssistantFab" class="smith-fab"', page)
        self.assertIn('<img src="./smith-face.png" alt="Smith" class="smith-fab__logo">', page)
        self.assertIn("position: fixed; right: var(--fab-offset); bottom: var(--fab-offset);", page)
        for control in ("terminalAgentSelect", "btnLaunchExternalTerm", "btnTerminalRestart",
                        "btnTerminalMaximize", "btnTerminalClose", "terminalContainer",
                        "terminalFooterAgent", "terminalFooterRun", "terminalQuickSelect",
                        "btnTerminalClear", "terminalStatusDot", "smithFabBadge"):
            self.assertIn(f'id="{control}"', page)

    def test_phase_cards_still_reach_the_console_and_keep_their_run_button(self) -> None:
        page = self.page()
        self.assertIn('onclick="sendToCli(this.dataset.cli, false)"', page)
        self.assertIn("onclick=\"triggerRunPhase('${escapeHtml(p.id)}', this)\"", page)

    def test_the_console_sends_the_guard_header_and_remembers_the_agent(self) -> None:
        script = (self.STATIC / "cli-console.js").read_text(encoding="utf-8")
        self.assertIn("'X-Papersmith-Terminal': '1'", script)
        self.assertIn("'Content-Type': 'application/json'", script)
        self.assertIn("const AGENT_KEY = 'smith_terminal_agent';", script)
        self.assertIn("api(`/api/terminal/sessions/${sessionId}`, 'DELETE', {})", script)


class ProblemTreeOrderTests(unittest.TestCase):
    """S6: problem tree order and CLI activation affordances in the static panels."""

    @staticmethod
    def _static(name: str) -> str:
        return (Path(server.__file__).parent / "static" / name).read_text()

    def _problem_tree(self) -> str:
        body = self._static("model-panel.js")
        return body[body.index("function problemTree"):body.index("function noveltyTree")]

    def test_problem_tree_rows_run_causes_central_effects(self) -> None:
        block = self._problem_tree()
        rows = [block.index(f"treeRow(t('conceptTree.{level}')")
                for level in ("causes", "central", "effects")]
        self.assertEqual(rows, sorted(rows))

    def test_effect_nodes_still_cite_their_causes(self) -> None:
        self.assertIn("conceptTree.causedBy", self._problem_tree())

    def test_an_unauthorized_page_gets_a_dismissible_activation_banner(self) -> None:
        source = self._static("cli-console.js")
        self.assertIn("cli.activateBanner", source)
        self.assertIn("showActivationBanner", source)
        self.assertIn("cliActivationBanner", source)
        self.assertIn("remove()", source)

    def test_the_launch_button_knows_the_linux_terminals(self) -> None:
        source = self._static("cli-console.js")
        for name in ("gnome-terminal", "konsole", "x-terminal-emulator"):
            self.assertIn(name, source)


class BrandingTests(unittest.TestCase):
    STATIC = Path(server.__file__).resolve().parent / "static"

    def test_the_lab_logo_is_only_in_the_bottom_center_footer(self) -> None:
        page = (self.STATIC / "index.html").read_text(encoding="utf-8")
        body = page[page.index("<body"):]
        self.assertTrue((self.STATIC / "logo_labIA.png").is_file())
        self.assertEqual(body.count('src="./logo_labIA.png"'), 1)
        footer = body[body.index('<footer class="dashboard-footer">'):body.index("</footer>")]
        self.assertIn('class="footer__col footer__col--center"', footer)
        self.assertIn('src="./logo_labIA.png"', footer)
        self.assertNotIn('class="topbar__lab-badge"', body)

    def test_the_footer_version_follows_the_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as holder:
            root = Path(holder)
            (root / ".papersmith").mkdir()
            (root / ".papersmith" / "version").write_text("0.16.0\n", encoding="utf-8")
            app = server.create_app(root, history_store=None)
            # A `version` file makes this a real workspace, so the route would
            # start an AI-archive sync thread that reads the home's transcripts
            # and writes here while the directory is being removed.
            with mock.patch.object(server.ai_archive, "sync_in_background"):
                status = _body(_route(app, "/api/status", "GET")())
            self.assertEqual(status["framework_version"], "0.16.0")


class CapabilityQueryTests(unittest.TestCase):
    def test_queries_are_answered_and_stripped(self) -> None:
        clean, replies = terminal.answer_queries(b"a\x1b[cb\x1b]11;?\x07c\x1b[?uD")
        self.assertEqual(clean, b"abcD")
        self.assertEqual(replies, [b"\x1b[?62;22c", b"\x1b]11;rgb:0808/0c0c/1414\x1b\\",
                                   b"\x1b[?0u"])

    def test_plain_output_passes_untouched(self) -> None:
        self.assertEqual(terminal.answer_queries(b"\x1b[31mred\x1b[0m"), (b"\x1b[31mred\x1b[0m", []))


if __name__ == "__main__":
    unittest.main()
