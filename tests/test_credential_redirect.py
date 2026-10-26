"""A Kaggle credential goes to the configured Kaggle URL and nowhere else (#106).

Both `smith mcp kaggle activate` (``kaggle_mcp.verify_token``) and the
kaggle-accounts validation (``accounts_cli._attempt``) send an Authorization
header. A redirect from the configured URL to another origin must fail the
check with its status, and the other origin must never see the credential.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from papersmith.cli import main  # noqa: E402
from papersmith.core import kaggle_mcp  # noqa: E402

SPEC = importlib.util.spec_from_file_location(
    "accounts_cli_redirect", REPO / "skills/kaggle-accounts/scripts/accounts_cli.py")
assert SPEC and SPEC.loader
ACCOUNTS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ACCOUNTS)

TOKEN = "KGAT_secret_for_the_test"
QUOTA = json.dumps({"jsonrpc": "2.0", "id": 1,
                    "result": {"content": [{"type": "text", "text": "quota"}]}}).encode()


def _serve(respond) -> tuple[ThreadingHTTPServer, list[dict]]:
    """Start a local server; `respond(handler)` answers every request.
    Returns the server and the list of requests it recorded."""
    seen: list[dict] = []

    class Handler(BaseHTTPRequestHandler):
        def _handle(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            if length:
                self.rfile.read(length)
            seen.append({"method": self.command,
                         "authorization": self.headers.get("Authorization")})
            respond(self)

        do_GET = do_POST = _handle

        def log_message(self, *_args) -> None:  # keep test output quiet
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, seen


class _RedirectToOtherOrigin(unittest.TestCase):
    """A stand-in for Kaggle that redirects every request to a second server
    on another port, which records the Authorization header it receives."""

    def setUp(self) -> None:
        def ok(handler: BaseHTTPRequestHandler) -> None:
            handler.send_response(200)
            handler.send_header("Content-Type", "application/json")
            handler.send_header("Content-Length", str(len(QUOTA)))
            handler.end_headers()
            handler.wfile.write(QUOTA)

        self.other, self.other_seen = _serve(ok)
        other_url = f"http://127.0.0.1:{self.other.server_address[1]}/"

        def redirect(handler: BaseHTTPRequestHandler) -> None:
            handler.send_response(302)
            handler.send_header("Location", other_url)
            handler.send_header("Content-Length", "0")
            handler.end_headers()

        self.kaggle, self.kaggle_seen = _serve(redirect)
        self.kaggle_url = f"http://127.0.0.1:{self.kaggle.server_address[1]}/mcp"
        self.ok_url = other_url
        for server in (self.other, self.kaggle):
            self.addCleanup(server.server_close)
            self.addCleanup(server.shutdown)


class KaggleMcpRedirectTests(_RedirectToOtherOrigin):
    def setUp(self) -> None:
        super().setUp()
        tmp = Path(tempfile.mkdtemp())
        self.home = tmp / "home"
        self.home.mkdir()
        patcher = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": str(tmp / "config"),
                                               "HOME": str(self.home), "SHELL": "/bin/zsh"})
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop(kaggle_mcp.TOKEN_ENV, None)

    def test_activate_refuses_a_cross_origin_redirect_and_stores_nothing(self) -> None:
        out = io.StringIO()
        with mock.patch.object(kaggle_mcp, "KAGGLE_MCP_URL", self.kaggle_url), \
                mock.patch("sys.stdin", io.StringIO(TOKEN + "\n")), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = main(["mcp", "kaggle", "activate", "--token-stdin"])
        self.assertNotEqual(code, 0, out.getvalue())
        self.assertIn("HTTP 302", out.getvalue())
        self.assertNotIn(TOKEN, out.getvalue())
        self.assertFalse((self.home / ".kaggle" / "access_token").exists())
        self.assertEqual(len(self.kaggle_seen), 1)
        self.assertEqual(self.other_seen, [], "the other origin was contacted")

    def test_verify_token_still_reads_a_direct_answer(self) -> None:
        with mock.patch.object(kaggle_mcp, "KAGGLE_MCP_URL", self.ok_url):
            self.assertEqual(kaggle_mcp.verify_token(TOKEN), (True, "accelerator quota read"))
        self.assertEqual(self.other_seen, [{"method": "POST", "authorization": f"Bearer {TOKEN}"}])


class AccountsValidationRedirectTests(_RedirectToOtherOrigin):
    def test_attempt_refuses_a_cross_origin_redirect(self) -> None:
        with mock.patch.object(ACCOUNTS, "VALIDATION_URL", self.kaggle_url):
            with self.assertRaises(ACCOUNTS.CredentialError) as raised:
                ACCOUNTS._attempt("Bearer", TOKEN)
        self.assertIn("HTTP 302", str(raised.exception))
        self.assertNotIn(TOKEN, str(raised.exception))
        self.assertEqual(len(self.kaggle_seen), 1)
        self.assertEqual(self.other_seen, [], "the other origin was contacted")

    def test_attempt_still_accepts_a_direct_200(self) -> None:
        with mock.patch.object(ACCOUNTS, "VALIDATION_URL", self.ok_url):
            self.assertIsNone(ACCOUNTS._attempt("Bearer", TOKEN))
        self.assertEqual(self.other_seen, [{"method": "GET", "authorization": f"Bearer {TOKEN}"}])


if __name__ == "__main__":
    unittest.main()
