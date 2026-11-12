"""The support terminal on a network bind (`smith ui --network-terminal`).

Off loopback the terminal stays off unless the operator opts in. With the
opt-in, every terminal and API-key route refuses a browser without the session
cookie that only the login secret buys, a state-changing call must carry this
server's `Origin`, the Host allow-list still answers 421, and the secret shows
in no response and no log: uvicorn's access log redacts it, the browser the
server opens never receives it, and the start banner prints a generated one
once and an operator's own never.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import http.client
import io
import json
import logging
import os
import re
import socket
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from skills._core.command_center import server, terminal

from test_api_keys import KEY, load_api_keys

api_keys = load_api_keys()
POSIX = os.name == "posix"
NET = "192.168.1.10:8080"
ORIGIN = f"http://{NET}"
#: What the dashboard's own scripts send on every state-changing call.
WRITE = {"Origin": ORIGIN, "Content-Type": "application/json", "X-Papersmith-Terminal": "1"}
#: Routes under /api/terminal that answer without the cookie by design: the
#: login itself, the self-activation (refused on a network bind) and two status
#: reads that withhold every agent and session byte from an unauthorized page.
OPEN_BY_DESIGN = {("GET", "/api/terminal/login"), ("POST", "/api/terminal/activate"),
                  ("GET", "/api/terminal/agents"), ("GET", "/api/terminal/office")}
SECRET = "operator-secret-" + "k" * 24


def network_app(root: Path, **kwargs):
    """The app main builds for `--host 0.0.0.0 --allowed-host NET --network-terminal`."""
    return server.create_app(root, history_store=None, enable_terminal=True, network_terminal=True,
                             allowed_hosts=server.build_allowed_hosts("0.0.0.0", 8080, [NET]),
                             **kwargs)


def guarded_routes(app) -> list[tuple[str, str]]:
    """Every (method, path) under /api/terminal that must demand the cookie."""
    found = []
    for route in app.routes:
        path = getattr(route, "path", "")
        if not path.startswith("/api/terminal"):
            continue
        for method in sorted(getattr(route, "methods", None) or ()):
            if (method, path) not in OPEN_BY_DESIGN:
                found.append((method, path))
    return found


def concrete(path: str) -> str:
    return re.sub(r"\{(\w+)\}", lambda m: "asta" if m.group(1) == "provider" else "x", path)


def sse_output(text: str) -> tuple[str, list[str]]:
    """(decoded PTY output, event names) of an SSE body."""
    output, events = "", []
    for frame in text.split("\n\n"):
        lines = dict(line.split(": ", 1) for line in frame.splitlines() if ": " in line)
        if "event" not in lines:
            continue
        events.append(lines["event"])
        if lines["event"] == "output":
            data = json.loads(lines["data"])["payload"]["data"]
            output += base64.b64decode(data).decode("utf-8", "replace")
    return output, events


class _KeepRecords(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.NOTSET)  # uvicorn's TRACE (5) included
        self.messages: list[tuple[str, str]] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.messages.append((record.name, record.getMessage()))
        except Exception:  # noqa: BLE001 - a record that cannot format is kept raw
            self.messages.append((record.name, str(record.msg)))


class NetworkCase(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.root = Path(holder.name).resolve()
        patcher = mock.patch.dict(os.environ, {api_keys.STORE_DIR_ENV: str(self.root / "keys")})
        patcher.start()
        self.addCleanup(patcher.stop)
        for variable in ("ASTA_API_KEY", "OPENALEX_API_KEY"):
            os.environ.pop(variable, None)
        (self.root / "ws").mkdir()
        self.app = network_app(self.root / "ws")
        self.addCleanup(self.app.state.terminal.close_all)
        self.app.state.terminal.agents_by_id["shell"] = terminal.Agent("shell", "Shell", ["/bin/sh"])
        self.client = TestClient(self.app, base_url=ORIGIN)

    def login(self, client: TestClient | None = None):
        client = client or self.client
        token = self.app.state.terminal.login_token
        return client.get(f"/api/terminal/login?token={token}", follow_redirects=False)


class NetworkRouteTests(NetworkCase):
    def test_every_terminal_and_key_route_refuses_a_browser_without_the_cookie(self) -> None:
        routes = guarded_routes(self.app)
        for expected in (("POST", "/api/terminal/sessions"), ("POST", "/api/terminal/sessions/{sid}/input"),
                         ("GET", "/api/terminal/sessions/{sid}/stream"),
                         ("DELETE", "/api/terminal/sessions/{sid}"), ("GET", "/api/terminal/sessions/{sid}"),
                         ("GET", "/api/terminal/keys"), ("PUT", "/api/terminal/keys/{provider}"),
                         ("POST", "/api/terminal/launch-external"), ("POST", "/api/terminal/tutor/turn")):
            self.assertIn(expected, routes)
        terminals = self.app.state.terminal
        # No cookie, a wrong one, and the login secret itself presented as a
        # cookie: the login secret buys the cookie, it is not the cookie.
        for cookies in ({}, {server.TERMINAL_COOKIE: "x" * 43},
                        {server.TERMINAL_COOKIE: terminals.login_token}):
            client = TestClient(self.app, base_url=ORIGIN, cookies=cookies)
            for method, path in routes:
                with self.subTest(method=method, path=path, cookies=bool(cookies)):
                    response = client.request(method, concrete(path), headers=WRITE, content=b"{}")
                    self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(terminals.count(), 0)
        self.assertIsNone(api_keys.read("asta"))

    def test_only_the_login_secret_buys_the_cookie(self) -> None:
        terminals = self.app.state.terminal
        # A non-ASCII guess is a wrong one too, never a 500.
        for query in ("", "?token=", "?token=wrong", f"?token={terminals.token}",
                      f"?token={terminals.login_token[:-1]}", "?token=%C3%A9", "?token=%ED%B3%BF"):
            with self.subTest(query=query):
                refused = self.client.get(f"/api/terminal/login{query}", follow_redirects=False)
                self.assertEqual(refused.status_code, 403)
                self.assertNotIn("set-cookie", refused.headers)
        ok = self.login()
        self.assertEqual(ok.status_code, 303)
        self.assertEqual(ok.headers["location"], "/")
        self.assertEqual(ok.headers["cache-control"], "no-store")
        self.assertEqual(ok.headers["referrer-policy"], "no-referrer")
        cookie = ok.headers["set-cookie"]
        self.assertTrue(cookie.startswith(f"{server.TERMINAL_COOKIE}={terminals.token};"), cookie)
        for attribute in ("HttpOnly", "SameSite=strict", "Path=/api/terminal"):
            self.assertIn(attribute, cookie)
        self.assertNotIn(terminals.login_token, json.dumps(dict(ok.headers)) + ok.text)

    def test_the_status_reads_withhold_everything_from_a_page_without_the_cookie(self) -> None:
        agents = self.client.get("/api/terminal/agents").json()
        self.assertEqual((agents["authorized"], agents["agents"]), (False, []))
        self.assertFalse(self.client.get("/api/terminal/office").json()["authorized"])
        self.login()
        self.assertTrue(self.client.get("/api/terminal/agents").json()["authorized"])

    def test_a_state_changing_call_must_carry_this_servers_origin(self) -> None:
        self.login()
        no_origin = {k: v for k, v in WRITE.items() if k != "Origin"}
        for headers in (no_origin, {**WRITE, "Origin": "http://evil.example"},
                        {**WRITE, "Origin": "null"}, {**WRITE, "Origin": "http://192.168.1.10:9090"}):
            with self.subTest(origin=headers.get("Origin")):
                response = self.client.post("/api/terminal/sessions", headers=headers,
                                            json={"agent": "shell"})
                self.assertEqual(response.status_code, 403)
                put = self.client.put("/api/terminal/keys/asta", headers=headers, json={"value": KEY})
                self.assertEqual(put.status_code, 403)
        self.assertIn("missing Origin header",
                      self.client.post("/api/terminal/sessions", headers=no_origin, json={}).text)
        self.assertEqual(self.app.state.terminal.count(), 0)
        self.assertIsNone(api_keys.read("asta"))
        # A same-origin read carries no Origin (browsers send none on a
        # same-origin GET) and still answers.
        self.assertEqual(self.client.get("/api/terminal/keys").status_code, 200)

    def test_the_host_allow_list_still_answers_421(self) -> None:
        self.login()
        for host in ("evil.example", "192.168.1.10:9090", "127.0.0.1:8080"):
            with self.subTest(host=host):
                response = self.client.get("/api/terminal/keys", headers={"Host": host})
                self.assertEqual(response.status_code, 421)

    def test_a_network_bind_never_activates_itself(self) -> None:
        with mock.patch.object(server, "open_browser") as opened:
            response = self.client.post("/api/terminal/activate", headers=WRITE, json={})
        self.assertEqual(response.status_code, 403)
        self.assertIn("login URL", response.json()["detail"])
        opened.assert_not_called()

    def test_the_keys_routes_follow_the_same_rule(self) -> None:
        refused = self.client.put("/api/terminal/keys/asta", headers=WRITE, json={"value": KEY})
        self.assertEqual(refused.status_code, 403)
        self.assertIsNone(api_keys.read("asta"))
        self.login()
        stored = self.client.put("/api/terminal/keys/asta", headers=WRITE, json={"value": KEY})
        self.assertEqual(stored.status_code, 200, stored.text)
        self.assertEqual(api_keys.read("asta"), KEY)
        status = self.client.get("/api/terminal/keys")
        self.assertEqual(status.status_code, 200)
        for response in (stored, status):
            self.assertNotIn(KEY, response.text)
        cleared = self.client.request("DELETE", "/api/terminal/keys/asta", headers=WRITE, content=b"{}")
        self.assertEqual(cleared.status_code, 200)
        self.assertIsNone(api_keys.read("asta"))


@unittest.skipUnless(POSIX, "the support terminal needs a POSIX pty")
class NetworkSessionTests(NetworkCase):
    def test_a_logged_in_browser_starts_drives_and_reads_a_session_and_nothing_leaks(self) -> None:
        terminals = self.app.state.terminal
        login_token, cookie = terminals.login_token, terminals.token
        root = logging.getLogger()
        keep = _KeepRecords()
        level = root.level
        root.addHandler(keep)
        root.setLevel(logging.DEBUG)
        self.addCleanup(root.setLevel, level)
        self.addCleanup(root.removeHandler, keep)

        responses = [self.client.get("/api/terminal/login?token=wrong-guess-0000", follow_redirects=False)]
        login = self.login()
        responses.append(login)
        responses.append(self.client.get("/api/terminal/agents"))
        self.assertTrue(responses[-1].json()["authorized"])
        created = self.client.post("/api/terminal/sessions", headers=WRITE,
                                   json={"agent": "shell", "cols": 80, "rows": 24})
        self.assertEqual(created.status_code, 200, created.text)
        responses.append(created)
        sid = created.json()["id"]
        resized = self.client.post(f"/api/terminal/sessions/{sid}/input", headers=WRITE,
                                   json={"cols": 100, "rows": 30})
        typed = self.client.post(f"/api/terminal/sessions/{sid}/input", headers=WRITE,
                                 json={"data": "stty size; echo net-terminal-$((6*7)); exit\n"})
        responses += [resized, typed]
        self.assertEqual((resized.status_code, typed.status_code), (200, 200))
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            looked_up = self.client.get(f"/api/terminal/sessions/{sid}")
            if not looked_up.json()["alive"]:
                break
            time.sleep(0.05)
        responses.append(looked_up)
        self.assertFalse(looked_up.json()["alive"], "the shell never exited")
        # The stream authenticates with the cookie alone: its URL holds no secret.
        stream_url = f"/api/terminal/sessions/{sid}/stream"
        stream = self.client.get(stream_url)
        responses.append(stream)
        self.assertEqual(stream.status_code, 200)
        self.assertTrue(stream.headers["content-type"].startswith("text/event-stream"))
        output, events = sse_output(stream.text)
        self.assertIn("net-terminal-42", output)
        self.assertIn("30 100", output)
        self.assertEqual(events[-1], "exit")
        self.assertNotIn(login_token, stream_url)
        self.assertNotIn(cookie, stream_url)
        closed = self.client.request("DELETE", f"/api/terminal/sessions/{sid}", headers=WRITE,
                                     content=b"{}")
        responses.append(closed)
        self.assertEqual(closed.status_code, 200)

        for response in responses:
            exposed = json.dumps(dict(response.headers)) + response.text
            self.assertNotIn(login_token, exposed, response.request.url)
            self.assertNotIn("wrong-guess-0000", exposed, response.request.url)
            if response is not login:
                self.assertNotIn(cookie, exposed, response.request.url)
        # httpx logs the URLs the test client itself requests; every record of
        # the server side is checked.
        server_side = [(name, text) for name, text in keep.messages
                       if not name.startswith(("httpx", "httpcore"))]
        for name, text in server_side:
            self.assertNotIn(login_token, text, name)
            self.assertNotIn(cookie, text, name)
            self.assertNotIn("wrong-guess-0000", text, name)


class DefaultsTests(unittest.TestCase):
    def test_off_loopback_the_terminal_needs_the_opt_in(self) -> None:
        for host in ("0.0.0.0", "::", "192.168.1.10", "example.lan"):
            with self.subTest(host=host):
                self.assertFalse(server.terminal_allowed(host))
                self.assertTrue(server.terminal_allowed(host, network_terminal=True))

    def test_an_invalid_operator_secret_keeps_the_terminal_off(self) -> None:
        with tempfile.TemporaryDirectory() as holder:
            for secret in ("short", "has a space " + "x" * 30, "é" * 40, ""):
                with self.subTest(secret=secret), self.assertLogs(server._log, logging.WARNING) as logs:
                    app = server.create_app(holder, history_store=None, enable_terminal=True,
                                            network_terminal=True, terminal_token=secret)
                    self.assertFalse(app.state.terminal_enabled)
                    self.assertFalse(app.state.terminal_network)
                    client = TestClient(app, base_url="http://127.0.0.1:8080")
                    self.assertEqual(client.post("/api/terminal/sessions", headers=WRITE, json={}).status_code, 404)
                    self.assertFalse(client.get("/api/terminal/agents").json()["enabled"])
                    if secret:
                        self.assertNotIn(secret, "\n".join(logs.output))

    def test_the_origin_rule_is_the_network_binds_own(self) -> None:
        # A loopback terminal keeps its rules: Origin is checked when sent.
        with tempfile.TemporaryDirectory() as holder:
            app = server.create_app(holder, history_store=None, enable_terminal=True)
            self.addCleanup(app.state.terminal.close_all)
            self.assertFalse(app.state.terminal_network)
        headers = {"host": "127.0.0.1:8080", "content-type": "application/json",
                   "x-papersmith-terminal": "1"}
        self.assertIsNone(terminal.guard(headers, mutating=True))
        self.assertEqual(terminal.guard(headers, mutating=True, require_origin=True),
                         "missing Origin header")
        self.assertIsNone(terminal.guard({**headers, "origin": "http://127.0.0.1:8080"},
                                         mutating=True, require_origin=True))
        # A read never needs it: browsers send none on a same-origin GET.
        self.assertIsNone(terminal.guard({"host": "127.0.0.1:8080"}, mutating=False, require_origin=True))


def _write_token(directory: Path, content: str | bytes, mode: int = 0o600, name: str = "token") -> Path:
    path = directory / name
    data = content.encode() if isinstance(content, str) else content
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
    os.chmod(path, mode)
    return path


@unittest.skipUnless(POSIX, "POSIX ownership and mode bits")
class TokenFileTests(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.dir = Path(holder.name).resolve()

    def refused(self, path: Path, *fragments: str, secret: str | None = None) -> str:
        with self.assertRaises(terminal.LoginTokenError) as caught:
            terminal.read_login_token(path)
        message = str(caught.exception)
        for fragment in fragments:
            self.assertIn(fragment, message)
        if secret:
            self.assertNotIn(secret, message)
        return message

    def test_a_private_file_gives_its_secret_without_the_line_break(self) -> None:
        path = _write_token(self.dir, f"{SECRET}\n")
        self.assertEqual(terminal.read_login_token(path), SECRET)

    def test_a_file_others_can_read_or_write_is_refused(self) -> None:
        for mode in (0o644, 0o640, 0o604, 0o620, 0o602):
            with self.subTest(mode=oct(mode)):
                path = _write_token(self.dir, SECRET, mode)
                self.refused(path, f"expected 0600", "insecure", secret=SECRET)

    def test_a_symlink_a_directory_or_a_missing_file_is_refused(self) -> None:
        target = _write_token(self.dir, SECRET)
        link = self.dir / "link"
        link.symlink_to(target)
        self.refused(link, "not a regular file", secret=SECRET)
        self.refused(self.dir, "not a regular file")
        self.refused(self.dir / "absent", "cannot read")
        real = self.dir / "real"
        real.mkdir()
        _write_token(real, SECRET)
        (self.dir / "linked-dir").symlink_to(real)
        self.refused(self.dir / "linked-dir" / "token", "its directory is a symlink", secret=SECRET)

    def test_a_file_of_another_user_is_refused(self) -> None:
        path = _write_token(self.dir, SECRET)
        with mock.patch.object(terminal.os, "getuid", return_value=os.getuid() + 1):
            self.refused(path, "owned by another user", secret=SECRET)

    def test_a_secret_that_breaks_the_rule_is_refused_without_being_quoted(self) -> None:
        for content in ("", "\n", "x" * 31, "x" * 257, "two words " + "x" * 30, f"{SECRET}\n{SECRET}",
                        "semi;colon" + "x" * 30, "%41" + "x" * 30, "é" * 40):
            with self.subTest(content=content[:12]):
                path = _write_token(self.dir, content)
                message = self.refused(path, "must hold one secret")
                if content.strip():
                    self.assertNotIn(content.strip(), message)
        path = _write_token(self.dir, b"x" * (terminal.LOGIN_TOKEN_FILE_BYTES + 1))
        self.refused(path, "must hold one secret")

    def test_the_rule_accepts_what_the_generator_produces(self) -> None:
        import secrets
        for _ in range(50):
            self.assertTrue(terminal.valid_login_token(secrets.token_urlsafe(32)))


def run_main(*argv: str) -> dict:
    """``server.main`` with uvicorn, the cache warmer and the browser timer
    stubbed: what it served, printed and opened, and its exit code."""
    seen: dict = {"app": None, "opened": []}
    out, err = io.StringIO(), io.StringIO()

    def serve(app, **kwargs) -> None:
        seen["app"], seen["serve"] = app, kwargs

    def timer(delay, function, args=()):
        seen["opened"].append(args[0])
        return mock.MagicMock()

    with mock.patch("uvicorn.run", serve), mock.patch.object(server, "warm_caches"), \
            mock.patch.object(server.threading, "Timer", side_effect=timer), \
            contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            seen["code"] = server.main(list(argv))
        except SystemExit as exit_:
            seen["code"] = exit_.code
    if seen["app"] is not None:
        seen["app"].state.terminal.close_all()
    seen["out"], seen["err"] = out.getvalue(), err.getvalue()
    return seen


class MainTests(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.dir = Path(holder.name).resolve()
        self.base = ("--root", str(self.dir), "--port", "8080")

    def test_without_the_flag_a_network_bind_keeps_the_terminal_off(self) -> None:
        seen = run_main(*self.base, "--host", "0.0.0.0", "--allow-unauthenticated-network",
                        "--allowed-host", NET)
        self.assertEqual(seen["code"], 0)
        app = seen["app"]
        self.assertFalse(app.state.terminal_enabled)
        self.assertNotIn("support terminal", seen["out"])
        self.assertNotIn(app.state.terminal.login_token, seen["out"] + seen["err"] + "".join(seen["opened"]))
        client = TestClient(app, base_url=ORIGIN)
        self.assertFalse(client.get("/api/terminal/agents").json()["enabled"])
        self.assertEqual(client.post("/api/terminal/sessions", headers=WRITE, json={}).status_code, 404)
        self.assertEqual(client.get("/api/terminal/keys").status_code, 404)

    def test_the_flag_offers_it_behind_a_secret_printed_once(self) -> None:
        seen = run_main(*self.base, "--host", "0.0.0.0", "--allow-unauthenticated-network",
                        "--allowed-host", NET, "--network-terminal")
        self.assertEqual(seen["code"], 0)
        app = seen["app"]
        self.assertTrue(app.state.terminal_enabled)
        self.assertTrue(app.state.terminal_network)
        token = app.state.terminal.login_token
        self.assertIn(f"http://{NET}/api/terminal/login?token={token}", seen["out"])
        self.assertEqual((seen["out"] + seen["err"]).count(token), 1)
        self.assertNotIn(app.state.terminal.token, seen["out"] + seen["err"])
        # The browser main opens gets the plain dashboard, never the secret.
        self.assertEqual(seen["opened"], ["http://0.0.0.0:8080/"])
        self.assertIn("ssh -L 8080:127.0.0.1:8080", seen["out"])

    def test_a_wildcard_bind_without_an_allowed_host_says_how_browsers_reach_it(self) -> None:
        seen = run_main(*self.base, "--host", "0.0.0.0", "--allow-unauthenticated-network",
                        "--network-terminal", "--no-browser")
        token = seen["app"].state.terminal.login_token
        self.assertIn(f"http://0.0.0.0:8080/api/terminal/login?token={token}", seen["out"])
        self.assertIn("--allowed-host <address>:8080", seen["out"])
        self.assertEqual(seen["opened"], [])
        # A specific address is its own login host, and the Host check accepts it.
        seen = run_main(*self.base, "--host", "192.168.1.10", "--allow-unauthenticated-network",
                        "--network-terminal", "--no-browser")
        token = seen["app"].state.terminal.login_token
        self.assertIn(f"http://192.168.1.10:8080/api/terminal/login?token={token}", seen["out"])
        self.assertNotIn("--allowed-host <address>", seen["out"])
        self.assertEqual(server.login_hosts("::", 8080, None), ["[::]:8080"])
        self.assertEqual(server.login_hosts("::", 8080, ["[fe80::1]:8080", " A.lan:8080 "]),
                         ["[fe80::1]:8080", "a.lan:8080"])

    def test_an_operator_secret_is_used_and_never_printed(self) -> None:
        path = _write_token(self.dir, f"{SECRET}\n")
        seen = run_main(*self.base, "--host", "0.0.0.0", "--allow-unauthenticated-network",
                        "--allowed-host", NET, "--network-terminal", "--terminal-token-file", str(path))
        self.assertEqual(seen["code"], 0)
        self.assertEqual(seen["app"].state.terminal.login_token, SECRET)
        self.assertNotIn(SECRET, seen["out"] + seen["err"] + "".join(seen["opened"]))
        self.assertIn(f"http://{NET}/api/terminal/login?token=<secret>", seen["out"])
        self.assertIn(str(path), seen["out"])

    def test_every_half_configured_network_terminal_is_refused(self) -> None:
        loose = _write_token(self.dir, SECRET, 0o644, name="loose")
        short = _write_token(self.dir, "x" * 20, name="short")
        good = _write_token(self.dir, SECRET, name="good")
        net = ("--host", "0.0.0.0", "--allow-unauthenticated-network")
        cases = {
            "without the network opt-in": (("--host", "0.0.0.0", "--network-terminal"),
                                           "puts only the support terminal and the API keys"),
            "on loopback": (("--host", "127.0.0.1", "--network-terminal"), "is for a non-loopback --host"),
            "with --no-terminal": ((*net, "--network-terminal", "--no-terminal"), "contradict"),
            "a token file alone": ((*net, "--terminal-token-file", str(good)), "needs --network-terminal"),
            "a loose token file": ((*net, "--network-terminal", "--terminal-token-file", str(loose)),
                                   "expected 0600"),
            "a short secret": ((*net, "--network-terminal", "--terminal-token-file", str(short)),
                               "must hold one secret"),
            "a missing file": ((*net, "--network-terminal", "--terminal-token-file", str(self.dir / "no")),
                               "cannot read"),
        }
        for label, (argv, reason) in cases.items():
            with self.subTest(label):
                seen = run_main(*self.base, *argv)
                self.assertEqual(seen["code"], 2)
                self.assertIsNone(seen["app"], "nothing may be served")
                self.assertIn(reason, seen["err"])
                self.assertNotIn(SECRET, seen["out"] + seen["err"])
                self.assertNotIn("x" * 20, seen["out"] + seen["err"])

    def test_the_help_names_the_flag_that_enables_a_network_terminal(self) -> None:
        actions = {action.dest: action for action in server.build_parser()._actions}
        self.assertIn("--network-terminal", actions["no_terminal"].help)
        self.assertIn("secret", actions["network_terminal"].help)
        self.assertIn("--network-terminal", actions["terminal_token_file"].help)


class AccessLogTests(unittest.TestCase):
    def test_the_filter_blanks_every_token_query_and_nothing_else(self) -> None:
        record = logging.LogRecord(
            "uvicorn.access", logging.INFO, __file__, 1, '%s - "%s %s HTTP/%s" %d',
            ("10.0.0.2:5000", "GET", f"/api/terminal/login?token={SECRET}&lang=es", "1.1", 303), None)
        self.assertTrue(server.RedactLoginToken().filter(record))
        message = record.getMessage()
        self.assertNotIn(SECRET, message)
        self.assertIn("/api/terminal/login?token=[REDACTED]&lang=es", message)
        for path, expected in (("/?a=1&TOKEN=abc", "/?a=1&TOKEN=[REDACTED]"),
                               ("/api/x?notatoken=1", "/api/x?notatoken=1"),
                               ("/api/terminal/sessions/x/stream", "/api/terminal/sessions/x/stream")):
            record = logging.LogRecord("uvicorn.access", logging.INFO, __file__, 1, "%s", (path,), None)
            server.RedactLoginToken().filter(record)
            self.assertEqual(record.getMessage(), expected)

    def test_the_filter_blanks_the_query_of_a_traced_asgi_scope(self) -> None:
        # uvicorn --log-level trace logs each scope; its headers are masked,
        # its query_string is not.
        scope = {"type": "http", "path": "/api/terminal/login", "headers": "<...>",
                 "query_string": f"token={SECRET}&lang=es".encode()}
        record = logging.LogRecord("uvicorn.asgi", 5, __file__, 1, "%s [%d] Started scope=%s",
                                   ("ASGI", 1, scope), None)
        server.RedactLoginToken().filter(record)
        message = record.getMessage()
        self.assertNotIn(SECRET, message)
        self.assertIn("b'token=[REDACTED]&lang=es'", message)
        self.assertEqual(scope["query_string"], f"token={SECRET}&lang=es".encode(), "the scope itself is untouched")

    def test_the_app_installs_the_filter_once_when_it_starts(self) -> None:
        loggers = [logging.getLogger(name) for name in ("uvicorn.access", "uvicorn.asgi")]
        for logger in loggers:
            for existing in [f for f in logger.filters if isinstance(f, server.RedactLoginToken)]:
                logger.removeFilter(existing)
        with tempfile.TemporaryDirectory() as holder:
            for _ in range(2):
                with TestClient(server.create_app(holder, history_store=None)):
                    pass
        for logger in loggers:
            self.assertEqual(sum(isinstance(f, server.RedactLoginToken) for f in logger.filters), 1,
                             logger.name)

    def test_a_real_uvicorn_log_never_shows_the_login_secret(self) -> None:
        import uvicorn

        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        app = network_app(Path(holder.name))
        self.addCleanup(app.state.terminal.close_all)
        token = app.state.terminal.login_token
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        # log_config=None keeps the suite's own logging configuration; the
        # filter is installed by the app at startup either way. At "trace"
        # uvicorn also logs every ASGI scope, the most it ever writes.
        keep = _KeepRecords()
        for name in ("uvicorn.access", "uvicorn.asgi", "uvicorn.error"):
            logger = logging.getLogger(name)
            self.addCleanup(logger.setLevel, logger.level)
            logger.addHandler(keep)
            self.addCleanup(logger.removeHandler, keep)
        config = uvicorn.Config(app, log_config=None, log_level="trace", lifespan="on")
        served = uvicorn.Server(config)
        thread = threading.Thread(target=served.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()
        self.addCleanup(listener.close)
        deadline = time.monotonic() + 15
        while not served.started and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertTrue(served.started, "uvicorn did not start")
        try:
            for guess in (token, "wrong-guess-0000"):
                connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
                connection.request("GET", f"/api/terminal/login?token={guess}", headers={"Host": NET})
                response = connection.getresponse()
                response.read()
                self.assertEqual(response.status, 303 if guess == token else 403)
                connection.close()
        finally:
            served.should_exit = True
            thread.join(15)
        logged = "\n".join(text for _name, text in keep.messages)
        names = {name for name, _text in keep.messages}
        self.assertTrue({"uvicorn.access", "uvicorn.asgi"} <= names, names)
        self.assertEqual(logged.count("/api/terminal/login?token=[REDACTED]"), 2, logged)
        self.assertEqual(logged.count("'query_string': b'token=[REDACTED]'"), 2, logged)
        self.assertNotIn(token, logged)
        self.assertNotIn("wrong-guess-0000", logged)
        self.assertNotIn(app.state.terminal.token, logged, "the session cookie")


class SmithUiTests(unittest.TestCase):
    def test_the_wrapper_forwards_the_flags_only_when_given(self) -> None:
        from papersmith.core import ui

        base = ui.build_server_argv(Path("/w"), "0.0.0.0", 8080, no_browser=True)
        self.assertNotIn("--network-terminal", base)
        self.assertNotIn("--terminal-token-file", base)
        argv = ui.build_server_argv(Path("/w"), "0.0.0.0", 8080, no_browser=True,
                                    network_terminal=True, terminal_token_file="/home/me/tok")
        self.assertIn("--network-terminal", argv)
        index = argv.index("--terminal-token-file")
        self.assertEqual(argv[index + 1], "/home/me/tok")

    def test_the_wrapper_parses_the_flags_and_explains_them(self) -> None:
        from papersmith.core import ui

        parser = argparse.ArgumentParser()
        ui.register(parser.add_subparsers())
        args = parser.parse_args(["ui", "--network-terminal", "--terminal-token-file", "tok"])
        self.assertTrue(args.network_terminal)
        self.assertEqual(args.terminal_token_file, "tok")
        self.assertFalse(parser.parse_args(["ui"]).network_terminal)
        sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction)).choices["ui"]
        helps = {action.dest: action.help for action in sub._actions}
        self.assertIn("--network-terminal", helps["no_terminal"])

    def test_a_relative_token_file_is_the_operators_not_the_workspaces(self) -> None:
        from papersmith.core import ui

        from test_command_center_cli import _seed_command_center

        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        root = Path(holder.name).resolve() / "paper"
        root.mkdir()
        _seed_command_center(root)
        elsewhere = Path(holder.name).resolve() / "operator"
        elsewhere.mkdir()
        captured: list[list[str]] = []
        stubs = {"_run_child": lambda argv, workspace: captured.append(argv) or 0,
                 "require_runnable_backend": lambda workspace, interpreter: None,
                 "port_is_free": lambda host, port: True}
        for name, stub in stubs.items():
            self.addCleanup(setattr, ui, name, getattr(ui, name))
            setattr(ui, name, stub)
        args = argparse.Namespace(directory=str(root), host="0.0.0.0", port=8080, no_browser=True,
                                  export_static=None, allowed_host=[NET],
                                  allow_unauthenticated_network=True, no_terminal=False,
                                  network_terminal=True, terminal_token_file="secrets/tok")
        with contextlib.chdir(elsewhere), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(ui.run_cli(args), 0)
        argv = captured[0]
        self.assertIn("--network-terminal", argv)
        self.assertEqual(argv[argv.index("--terminal-token-file") + 1], str(elsewhere / "secrets" / "tok"))


class SmithUiLanTests(unittest.TestCase):
    """``smith ui --lan``: one switch for the other machines on the operator's
    network, with the Host check fed this machine's own names (never a
    wildcard) and the terminal behind a secret kept in a private file."""

    LAN = ["192.168.1.15:8080", "intel2.local:8080", "127.0.0.1:8080"]

    def setUp(self) -> None:
        from papersmith.core import ui

        self.ui = ui
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.base = Path(holder.name).resolve()
        self.root = self.base / "paper"
        self.root.mkdir()
        from test_command_center_cli import _seed_command_center

        _seed_command_center(self.root)
        self.captured: list[list[str]] = []
        stubs = {"_run_child": lambda argv, workspace: self.captured.append(argv) or 0,
                 "require_runnable_backend": lambda workspace, interpreter: None,
                 "port_is_free": lambda host, port: True,
                 "lan_hosts": lambda port: list(self.LAN)}
        for name, stub in stubs.items():
            self.addCleanup(setattr, ui, name, getattr(ui, name))
            setattr(ui, name, stub)
        patcher = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.base / "config")})
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop(ui.LAN_ENV, None)

    def args(self, *argv: str) -> argparse.Namespace:
        parser = argparse.ArgumentParser()
        self.ui.register(parser.add_subparsers())
        return parser.parse_args(["ui", *argv, str(self.root)])

    def run_ui(self, *argv: str) -> tuple[list[str], str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(self.ui.run_cli(self.args(*argv)), 0)
        return self.captured[-1], out.getvalue()

    @staticmethod
    def values(argv: list[str], flag: str) -> list[str]:
        return [argv[i + 1] for i, item in enumerate(argv) if item == flag]

    def test_without_lan_nothing_changes(self) -> None:
        argv, _ = self.run_ui()
        self.assertEqual(self.values(argv, "--host"), ["127.0.0.1"])
        for flag in ("--allow-unauthenticated-network", "--network-terminal",
                     "--terminal-token-file", "--allowed-host"):
            self.assertNotIn(flag, argv)
        self.assertFalse((self.base / "config").exists())

    def test_lan_serves_the_network_with_the_terminal_behind_a_private_secret(self) -> None:
        argv, out = self.run_ui("--lan")
        self.assertEqual(self.values(argv, "--host"), ["0.0.0.0"])
        self.assertIn("--allow-unauthenticated-network", argv)
        self.assertIn("--network-terminal", argv)
        self.assertEqual(self.values(argv, "--allowed-host"), self.LAN)
        token_file = Path(self.values(argv, "--terminal-token-file")[0])
        self.assertEqual(token_file, self.base / "config" / "papersmith" / "terminal-token")
        # The file the wrapper creates passes the backend's own private-file rule.
        secret = terminal.read_login_token(token_file)
        if POSIX:
            self.assertEqual(token_file.stat().st_mode & 0o777, 0o600)
            self.assertEqual(token_file.parent.stat().st_mode & 0o777, 0o700)
        self.assertNotIn(secret, " ".join(argv), "argv is readable by every local user")
        # Shown once, at creation, for the bookmarks; never the wildcard.
        self.assertIn(f"http://192.168.1.15:8080/api/terminal/login?token={secret}", out)
        self.assertIn(f"http://intel2.local:8080/api/terminal/login?token={secret}", out)
        self.assertNotIn("127.0.0.1:8080/api/terminal/login", out)

        argv, out = self.run_ui("--lan")
        self.assertNotIn(secret, out, "a later start reads the file and does not print it")
        self.assertEqual(terminal.read_login_token(token_file), secret, "kept across restarts")

    def test_the_environment_makes_lan_the_default_and_no_lan_turns_it_off(self) -> None:
        with mock.patch.dict(os.environ, {self.ui.LAN_ENV: "1"}):
            argv, _ = self.run_ui()
            self.assertEqual(self.values(argv, "--host"), ["0.0.0.0"])
            argv, _ = self.run_ui("--no-lan")
            self.assertEqual(self.values(argv, "--host"), ["127.0.0.1"])
            self.assertNotIn("--network-terminal", argv)
        with mock.patch.dict(os.environ, {self.ui.LAN_ENV: "0"}):
            argv, _ = self.run_ui()
            self.assertNotIn("--allow-unauthenticated-network", argv)

    def test_lan_keeps_an_explicit_host_token_file_and_extra_hosts(self) -> None:
        token = self.base / "mine"
        argv, out = self.run_ui("--lan", "--host", "192.168.1.15", "--allowed-host",
                                "box.example:8080", "--terminal-token-file", str(token))
        self.assertEqual(self.values(argv, "--host"), ["192.168.1.15"])
        self.assertEqual(self.values(argv, "--allowed-host"), ["box.example:8080", *self.LAN])
        self.assertEqual(self.values(argv, "--terminal-token-file"), [str(token)])
        self.assertTrue(token.is_file())

    def test_lan_without_the_terminal_creates_no_secret(self) -> None:
        argv, out = self.run_ui("--lan", "--no-terminal")
        self.assertIn("--no-terminal", argv)
        self.assertNotIn("--network-terminal", argv)
        self.assertNotIn("--terminal-token-file", argv)
        self.assertFalse((self.base / "config").exists())
        self.assertNotIn("token=", out)

    def test_a_public_address_is_warned_about(self) -> None:
        err = io.StringIO()
        self.ui.public_addresses, original = (lambda hosts: ["8.8.4.4"]), self.ui.public_addresses
        self.addCleanup(setattr, self.ui, "public_addresses", original)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            self.ui.run_cli(self.args("--lan"))
        self.assertIn("WARNING: this machine has a public address (8.8.4.4)", err.getvalue())
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            self.ui.run_cli(self.args("--lan", "--host", "192.168.1.15"))
        self.assertNotIn("WARNING", err.getvalue(), "bound to a private address only")

    def test_an_existing_token_file_is_never_rewritten(self) -> None:
        path = self.base / "kept"
        path.write_text("x" * 40 + "\n", encoding="ascii")
        self.assertIsNone(self.ui.ensure_token_file(path))
        self.assertEqual(path.read_text(encoding="ascii"), "x" * 40 + "\n")
        if POSIX:
            link = self.base / "link"
            link.symlink_to(self.base / "nowhere")
            self.assertIsNone(self.ui.ensure_token_file(link))
            self.assertFalse((self.base / "nowhere").exists(), "a dangling symlink is not followed")


class LanHostsTests(unittest.TestCase):
    def test_this_machines_names_and_addresses_never_a_wildcard(self) -> None:
        from papersmith.core import ui

        hosts = ui.lan_hosts(8765, addresses=["192.168.1.15", "2800:e2:1::5"], hostname="Intel2",
                             names=["intel2.tail1234.ts.net"])
        self.assertEqual(hosts, ["192.168.1.15:8765", "[2800:e2:1::5]:8765", "intel2:8765",
                                 "intel2.local:8765", "intel2.tail1234.ts.net:8765", "127.0.0.1:8765", "localhost:8765",
                                 "[::1]:8765"])
        self.assertNotIn("0.0.0.0:8765", hosts)
        self.assertEqual(ui.lan_hosts(1, addresses=[], hostname="box.lan", names=[])[0], "box.lan:1")

    def test_only_addresses_a_browser_can_name(self) -> None:
        from papersmith.core import ui

        for address in ("127.0.0.1", "::1", "0.0.0.0", "fe80::1", "224.0.0.1", "not-an-ip"):
            with self.subTest(address=address):
                self.assertFalse(ui._usable(address))
        self.assertTrue(ui._usable("10.0.0.7"))
        self.assertTrue(ui._usable("100.101.102.103"), "a Tailscale address")
        found = ui.machine_addresses()
        self.assertTrue(all(ui._usable(address) for address in found), found)

    def test_the_tailscale_name_is_read_from_tailscaled_and_checked(self) -> None:
        from papersmith.core import ui

        def status(stdout: str, code: int = 0):
            return mock.patch.object(ui.subprocess, "run", return_value=subprocess.CompletedProcess(
                ["tailscale"], code, stdout=stdout, stderr=""))

        with status('{"Self": {"DNSName": "Intel2.tail1234.ts.net."}}'):
            self.assertEqual(ui.tailscale_names(), ["intel2.tail1234.ts.net"])
        for stdout, code in (("", 1), ("not json", 0), ('{"Self": null}', 0), ("[]", 0),
                             ('{"Self": {"DNSName": "*.evil.example."}}', 0),
                             ('{"Self": {"DNSName": "nodots"}}', 0)):
            with self.subTest(stdout=stdout), status(stdout, code):
                self.assertEqual(ui.tailscale_names(), [])
        with mock.patch.object(ui.subprocess, "run", side_effect=FileNotFoundError):
            self.assertEqual(ui.tailscale_names(), [], "no tailscale installed")

    def test_only_a_public_ipv4_counts_as_public(self) -> None:
        from papersmith.core import ui

        self.assertEqual(ui.public_addresses(
            ["192.168.1.15:1", "100.101.102.103:1", "8.8.4.4:1", "[2800:e2:1::5]:1",
             "intel2.local:1", "10.0.0.1:1"]), ["8.8.4.4"])

    def test_a_lan_host_list_still_refuses_a_rebinding_name(self) -> None:
        from papersmith.core import ui

        allowed = server.build_allowed_hosts(
            "0.0.0.0", 8765, ui.lan_hosts(8765, addresses=["192.168.1.15"], hostname="intel2",
                                        names=[]))
        with tempfile.TemporaryDirectory() as holder:
            app = server.create_app(holder, history_store=None, enable_terminal=False,
                                    allowed_hosts=allowed)
            for host, refused in (("192.168.1.15:8765", False), ("intel2.local:8765", False),
                                  ("attacker.example:8765", True)):
                with self.subTest(host=host):
                    client = TestClient(app, base_url=f"http://{host}")
                    status = client.get("/api/health/wiring").status_code
                    self.assertEqual(status == 421, refused, status)


class DashboardTextTests(unittest.TestCase):
    STATIC = Path(server.__file__).resolve().parent / "static"

    def test_the_disabled_console_names_the_flag(self) -> None:
        for name in ("en.js", "es.js"):
            catalogue = (self.STATIC / "i18n" / name).read_text(encoding="utf-8")
            line = next(line for line in catalogue.splitlines() if '"cli.disabled"' in line)
            with self.subTest(catalogue=name):
                self.assertIn("--network-terminal", line)
                self.assertIn("127.0.0.1", line)


if __name__ == "__main__":
    unittest.main()
