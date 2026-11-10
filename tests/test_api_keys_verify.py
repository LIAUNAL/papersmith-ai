"""`api_keys.verify`: one explicit, read-only call, against local fake servers.

The fakes answer the way the live services did on 2026-11-09: Asta streams
`: ping` comments and then one `data:` line, reports a refused key as HTTP 200
with `isError` and "HTTP status 403 Forbidden."; OpenAlex answers a bad
`api_key` with HTTP 401 and reports its budget in `x-ratelimit-*-usd` headers.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from test_api_keys import KEY, OTHER, load_api_keys

api_keys = load_api_keys()


class _Server:
    def __init__(self, handler_factory) -> None:
        self.hits: list[dict] = []
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args) -> None:  # quiet
                pass

            def _record(self, body: bytes) -> None:
                server.hits.append({"method": self.command, "path": self.path,
                                    "headers": {k.lower(): v for k, v in self.headers.items()},
                                    "body": body})

            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length)
                self._record(body)
                handler_factory(self, body)

            def do_GET(self) -> None:  # noqa: N802
                self._record(b"")
                handler_factory(self, b"")

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.httpd.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}/mcp/v1"
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


def _sse(handler, message: dict, *, pings: int = 0, ping_gap: float = 0.0) -> None:
    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream")
    handler.end_headers()
    for _ in range(pings):
        handler.wfile.write(b": ping - 2026-11-09\n\n")
        handler.wfile.flush()
        time.sleep(ping_gap)
    handler.wfile.write(b"event: message\n")
    handler.wfile.write(f"data: {json.dumps(message)}\n\n".encode("utf-8"))
    handler.wfile.flush()


def _tool(text: str, *, error: bool) -> dict:
    return {"jsonrpc": "2.0", "id": 1,
            "result": {"content": [{"type": "text", "text": text}], "isError": error}}


class VerifyCase(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        patcher = mock.patch.dict(os.environ, {api_keys.STORE_DIR_ENV: str(Path(holder.name) / "keys")})
        patcher.start()
        self.addCleanup(patcher.stop)
        for variable in ("ASTA_API_KEY", "OPENALEX_API_KEY"):
            os.environ.pop(variable, None)

    def serve(self, handler) -> _Server:
        server = _Server(handler)
        self.addCleanup(server.close)
        return server

    def assert_no_key(self, result: dict, *keys: str) -> None:
        rendered = json.dumps(result)
        for key in keys:
            assert key not in rendered


class AstaVerifyTests(VerifyCase):
    def test_a_working_key_is_ok_after_the_pings(self) -> None:
        server = self.serve(lambda h, body: _sse(h, _tool('{"title": "EEGNet"}', error=False), pings=2))
        api_keys.store("asta", KEY)

        result = api_keys.verify("asta", url=server.url)

        assert result["state"] == "ok" and result["source"] == "store"
        hit = server.hits[0]
        assert hit["method"] == "POST" and hit["headers"]["x-api-key"] == KEY
        call = json.loads(hit["body"])
        assert call["method"] == "tools/call" and call["params"]["name"] == "get_paper"
        assert call["params"]["arguments"]["paper_id"] == api_keys.ASTA_VERIFY_PAPER
        assert KEY.encode() not in hit["body"]
        self.assert_no_key(result, KEY)

    def test_a_refused_key_arrives_as_http_200_and_reads_refused(self) -> None:
        server = self.serve(lambda h, body: _sse(
            h, _tool("Error executing tool get_paper: HTTP status 403 Forbidden.", error=True)))
        result = api_keys.verify("asta", "bogus-key-00000000", url=server.url)
        assert result["state"] == "refused" and result["source"] == "given"

    def test_endless_pings_end_at_the_deadline(self) -> None:
        def handler(h, body):
            h.send_response(200)
            h.send_header("Content-Type", "text/event-stream")
            h.end_headers()
            try:
                for _ in range(200):
                    h.wfile.write(b": ping\n\n")
                    h.wfile.flush()
                    time.sleep(0.05)
            except (BrokenPipeError, ConnectionResetError):
                pass

        server = self.serve(handler)
        started = time.monotonic()
        result = api_keys.verify("asta", KEY, url=server.url, deadline=0.5)
        assert result["state"] == "unreachable"
        assert time.monotonic() - started < 5

    def test_a_redirect_is_never_followed(self) -> None:
        elsewhere = self.serve(lambda h, body: _sse(h, _tool("{}", error=False)))

        def redirect(h, body):
            h.send_response(307)
            h.send_header("Location", elsewhere.url)
            h.end_headers()

        server = self.serve(redirect)
        result = api_keys.verify("asta", KEY, url=server.url)
        assert result["state"] == "unreachable" and "redirect" in result["detail"]
        assert elsewhere.hits == []

    def test_a_server_error_is_unreachable_and_never_echoes_the_key(self) -> None:
        def broken(h, body):
            h.send_response(503)
            h.end_headers()
            h.wfile.write(f"upstream rejected {KEY}".encode())

        server = self.serve(broken)
        result = api_keys.verify("asta", KEY, url=server.url)
        assert result["state"] == "unreachable" and result["detail"] == "HTTP 503"
        self.assert_no_key(result, KEY)

    def test_no_key_means_no_call(self) -> None:
        server = self.serve(lambda h, body: _sse(h, _tool("{}", error=False)))
        result = api_keys.verify("asta", url=server.url)
        assert result["state"] == "unconfigured"
        assert server.hits == []


class OpenAlexVerifyTests(VerifyCase):
    def test_a_working_key_reports_the_budget(self) -> None:
        def ok(h, body):
            h.send_response(200)
            h.send_header("Content-Type", "application/json")
            h.send_header("x-ratelimit-remaining-usd", "0.97")
            h.send_header("x-ratelimit-limit-usd", "1.0")
            h.end_headers()
            h.wfile.write(b'{"results": []}')

        server = self.serve(ok)
        exported = mock.patch.dict(os.environ, {"OPENALEX_API_KEY": OTHER})
        exported.start()
        self.addCleanup(exported.stop)

        result = api_keys.verify("openalex", url=server.url)

        assert result["state"] == "ok" and result["source"] == "env"
        assert result["budget"] == {"remaining_usd": "0.97", "limit_usd": "1.0"}
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(server.hits[0]["path"]).query)
        assert query["api_key"] == [OTHER] and query["per-page"] == ["1"]
        self.assert_no_key(result, OTHER)

    def test_a_bad_key_is_refused_not_unreachable(self) -> None:
        def unauthorized(h, body):
            h.send_response(401)
            h.send_header("Content-Type", "application/json")
            h.end_headers()
            h.wfile.write(b'{"error": "Invalid or missing API key"}')

        server = self.serve(unauthorized)
        result = api_keys.verify("openalex", "bogus-key-00000000", url=server.url)
        assert result["state"] == "refused"

    def test_a_spent_quota_is_unreachable(self) -> None:
        def throttled(h, body):
            h.send_response(429)
            h.end_headers()

        server = self.serve(throttled)
        result = api_keys.verify("openalex", OTHER, url=server.url)
        assert result["state"] == "unreachable" and result["detail"] == "HTTP 429"

    def test_an_invalid_given_key_is_refused_before_any_call(self) -> None:
        server = self.serve(lambda h, body: None)
        with self.assertRaises(api_keys.KeyRefused):
            api_keys.verify("openalex", "bad key", url=server.url)
        assert server.hits == []


if __name__ == "__main__":
    unittest.main()
