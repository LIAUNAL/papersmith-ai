"""The dashboard's API keys: session injection and the four key routes.

The routes live under `/api/terminal/` behind the terminal's own guards: the
per-server cookie, a loopback bind, same-origin headers, and for a write an
`Origin` the browser always sends. A body is parsed by hand and never echoed;
no response ever carries a key.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from skills._core.command_center import keys_view, server, terminal

from test_api_keys import KEY, OTHER, load_api_keys
from test_command_center_terminal import SAME, _body, _call, _Request, _route

api_keys = load_api_keys()
POSIX = os.name == "posix"


class _RawRequest(_Request):
    """A request whose raw body the key routes read (they never use `.json()`)."""

    def __init__(self, headers=None, raw: bytes = b"", cookies=None) -> None:
        super().__init__(headers, None, cookies)
        self._raw = raw

    async def body(self) -> bytes:
        return self._raw


class KeysCase(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.tmp = Path(holder.name).resolve()
        patcher = mock.patch.dict(os.environ, {api_keys.STORE_DIR_ENV: str(self.tmp / "keys")})
        patcher.start()
        self.addCleanup(patcher.stop)
        for variable in ("ASTA_API_KEY", "OPENALEX_API_KEY"):
            os.environ.pop(variable, None)


class SessionEnvTests(KeysCase):
    def test_a_new_session_receives_each_stored_key(self) -> None:
        api_keys.store("asta", KEY)
        api_keys.store("openalex", OTHER)
        env = terminal.session_env("shell", self.tmp)
        assert env["ASTA_API_KEY"] == KEY and env["OPENALEX_API_KEY"] == OTHER

    def test_an_exported_variable_wins(self) -> None:
        api_keys.store("asta", KEY)
        with mock.patch.dict(os.environ, {"ASTA_API_KEY": "mine-exported-1234"}):
            assert terminal.session_env("claude", self.tmp)["ASTA_API_KEY"] == "mine-exported-1234"

    @unittest.skipUnless(POSIX, "POSIX mode bits")
    def test_an_insecure_file_is_never_handed_to_a_session(self) -> None:
        api_keys.store("asta", KEY).chmod(0o644)
        assert "ASTA_API_KEY" not in terminal.session_env("shell", self.tmp)

    def test_a_broken_store_never_stops_a_session(self) -> None:
        api_keys.store("asta", KEY)
        with mock.patch.object(keys_view, "api_keys", side_effect=RuntimeError("boom")):
            env = terminal.session_env("shell", self.tmp)
            assert keys_view.secret_values() == ()  # never raises either
            assert keys_view.scrub("nothing to hide") == "nothing to hide"
        assert "PATH" in env and "ASTA_API_KEY" not in env


@unittest.skipUnless(POSIX, "the support terminal needs a POSIX pty")
class RouteTests(KeysCase):
    def setUp(self) -> None:
        super().setUp()
        self.app = server.create_app(self.tmp / "ws", history_store=None, enable_terminal=True)
        self.addCleanup(self.app.state.terminal.close_all)

    def req(self, headers=None, payload: object = None, *, raw: bytes | None = None,
            cookie: bool = True) -> _RawRequest:
        body = raw if raw is not None else (b"" if payload is None else json.dumps(payload).encode())
        token = self.app.state.terminal.token
        return _RawRequest(SAME if headers is None else headers, body,
                           {server.TERMINAL_COOKIE: token} if cookie else None)

    def put(self, provider: str, payload: object = None, **kwargs):
        return _call(_route(self.app, "/api/terminal/keys/{provider}", "PUT"), provider,
                     self.req(payload=payload, **kwargs))

    def assert_no_key(self, response, *values: str) -> None:
        text = bytes(response.body).decode("utf-8")
        for value in values:
            assert value not in text

    def test_status_needs_the_cookie_and_never_carries_a_key(self) -> None:
        status = _route(self.app, "/api/terminal/keys", "GET")
        assert _call(status, self.req(cookie=False)).status_code == 403
        api_keys.store("asta", KEY)
        response = _call(status, self.req())
        body = _body(response)
        assert [state["provider"] for state in body["keys"]] == ["asta", "openalex"]
        assert body["keys"][0]["configured"] is True and body["keys"][0]["source"] == "store"
        assert "export_command" in body["keys"][0] and body["sessions_open"] == 0
        assert body["asta_mcp"]["server"] == "asta" and isinstance(body["asta_mcp"]["registered"], list)
        self.assert_no_key(response, KEY)
        assert response.headers["cache-control"] == "no-store"

    def test_put_stores_the_key_and_answers_with_status_only(self) -> None:
        response = self.put("asta", {"value": KEY})
        assert response.status_code == 200, _body(response)
        assert _body(response)["status"]["source"] == "store"
        assert api_keys.read("asta") == KEY
        self.assert_no_key(response, KEY)

    def test_writes_refuse_a_missing_origin_a_foreign_one_and_no_cookie(self) -> None:
        no_origin = {k: v for k, v in SAME.items() if k != "Origin"}
        for headers, cookie in ((no_origin, True), ({**SAME, "Origin": "http://evil.example"}, True),
                                ({**SAME, "Sec-Fetch-Site": "cross-site"}, True),
                                ({**SAME, "Content-Type": "text/plain"}, True), (SAME, False)):
            with self.subTest(headers=headers, cookie=cookie):
                response = self.put("asta", {"value": KEY}, headers=headers, cookie=cookie)
                assert response.status_code == 403
        assert api_keys.read("asta") is None

    def test_a_disabled_terminal_hides_the_routes(self) -> None:
        app = server.create_app(self.tmp / "ws2", history_store=None, enable_terminal=False)
        response = _call(_route(app, "/api/terminal/keys", "GET"),
                         _RawRequest(SAME, b"", {server.TERMINAL_COOKIE: "x"}))
        assert response.status_code == 404

    def test_an_invalid_body_is_422_and_never_echoed(self) -> None:
        for payload in ({"value": "has a space here"}, {"value": 12345678}, ["not", "an", "object"]):
            with self.subTest(payload=payload):
                response = self.put("asta", payload)
                assert response.status_code == 422
                self.assert_no_key(response, "has a space here", "12345678")
        response = self.put("asta", raw=b"\xff\xfe not json")
        assert response.status_code == 422
        assert api_keys.read("asta") is None

    def test_an_oversized_body_is_413(self) -> None:
        response = self.put("asta", raw=b'{"value": "' + b"a" * 5000 + b'"}')
        assert response.status_code == 413

    def test_an_unknown_provider_is_404_without_echoing_the_path(self) -> None:
        response = self.put("crossref", {"value": KEY})
        assert response.status_code == 404
        self.assert_no_key(response, "crossref", KEY)

    def test_verify_before_store_stores_nothing_when_refused(self) -> None:
        refused = {"provider": "asta", "state": "refused", "detail": "Asta refused the key",
                   "source": "given", "budget": None, "elapsed_ms": 1}
        with mock.patch.object(keys_view.api_keys(), "verify", return_value=refused):
            response = self.put("asta", {"value": KEY, "verify": True})
        assert response.status_code == 422 and _body(response)["error"] == "KEY_REFUSED"
        assert api_keys.read("asta") is None
        unreachable = dict(refused, state="unreachable", detail="HTTP 503")
        with mock.patch.object(keys_view.api_keys(), "verify", return_value=unreachable):
            response = self.put("asta", {"value": KEY, "verify": True})
        assert response.status_code == 503 and api_keys.read("asta") is None

    def test_delete_removes_the_stored_key(self) -> None:
        api_keys.store("openalex", OTHER)
        delete = _route(self.app, "/api/terminal/keys/{provider}", "DELETE")
        response = _call(delete, "openalex", self.req(payload={}))
        assert response.status_code == 200 and _body(response)["removed"] is True
        assert api_keys.read("openalex") is None
        no_origin = {k: v for k, v in SAME.items() if k != "Origin"}
        assert _call(delete, "openalex", self.req(no_origin, {})).status_code == 403

    def test_verify_uses_the_configured_key_never_one_from_the_body(self) -> None:
        api_keys.store("openalex", OTHER)
        seen = {}

        def fake_verify(provider, value=None, **kwargs):
            seen["args"] = (provider, value)
            return {"provider": provider, "state": "ok", "detail": "key accepted",
                    "source": "store", "budget": None, "elapsed_ms": 2}

        route = _route(self.app, "/api/terminal/keys/{provider}/verify", "POST")
        with mock.patch.object(keys_view.api_keys(), "verify", side_effect=fake_verify):
            response = _call(route, "openalex", self.req(payload={"value": "smuggled-key-0000"}))
        assert response.status_code == 200 and _body(response)["verify"]["state"] == "ok"
        assert seen["args"] == ("openalex", None)


if __name__ == "__main__":
    unittest.main()
