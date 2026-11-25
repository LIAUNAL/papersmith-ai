"""Step 1 of idea shaping, sources (``skills/_core/idea/bank.py`` through
``idea_cli``): banco-lia, another bank MCP server, or none. Every server is a
local fake (stdio scripts, or a localhost HTTP server); OpenAlex is a fake
fetcher; nothing reaches the network."""

from __future__ import annotations

import contextlib
import io
import json
import os
import stat
import sys
import tempfile
import textwrap
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from skills._core.command_center import banco_suggest
from skills._core.idea import bank, brief, idea_cli, profile, topics

BANCO_FAKE = Path(__file__).resolve().parent / "fixtures" / "banco_lia" / "fake_mcp.py"

#: A stdio MCP server whose tools come from FAKE_TOOLS (JSON list); every
#: request's method is appended to FAKE_LOG.
GENERIC_FAKE = textwrap.dedent('''
    import json, os, sys
    TOOLS = json.loads(os.environ.get("FAKE_TOOLS", '["search_bank"]'))
    LOG = os.environ.get("FAKE_LOG")
    def say(m):
        sys.stdout.write(json.dumps(m) + "\\n"); sys.stdout.flush()
    for line in sys.stdin:
        if not line.strip():
            continue
        req = json.loads(line)
        if LOG:
            with open(LOG, "a") as fh:
                fh.write(json.dumps({"method": req.get("method"), "params": req.get("params")}) + "\\n")
        ident, method = req.get("id"), req.get("method")
        if ident is None:
            continue
        if method == "initialize":
            say({"jsonrpc": "2.0", "id": ident, "result": {"protocolVersion": "2025-03-26", "capabilities": {}}})
        elif method == "tools/list":
            say({"jsonrpc": "2.0", "id": ident, "result": {"tools": [{"name": n} for n in TOOLS]}})
        elif method == "tools/call":
            hits = [{"id": "P1", "kind": "articulo", "title": "Graph models for EEG transfer", "year": 2024,
                     "cluster": "K1", "doi": "10.1/x", "score": 0.9},
                    {"id": "P2", "kind": "proyecto", "title": "Domain shift in clinical EEG", "year": 2022,
                     "cluster": "K1", "score": 0.5}]
            say({"jsonrpc": "2.0", "id": ident, "result": {"content": [{"type": "text", "text": json.dumps(hits)}],
                                                          "structuredContent": {"result": hits}}})
''')


class FakeOpenAlex:
    def __init__(self, count: int = 30) -> None:
        self.count = count
        self.calls: list[str] = []

    def __call__(self, url: str):
        self.calls.append(url)
        if "/works?" in url:
            return {"meta": {"count": self.count}}
        raise AssertionError(f"unexpected OpenAlex request {url}")


class BankCase(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "ws"
        (self.root / ".papersmith").mkdir(parents=True)
        self.scratch = Path(tmp.name)
        self.fake = self.scratch / "fake_server.py"
        self.fake.write_text(GENERIC_FAKE, encoding="utf-8")
        self.log = self.scratch / "calls.jsonl"
        env = mock.patch.dict(os.environ, {"FAKE_LOG": str(self.log), "PAPERSMITH_BANCO_LIA_TIMEOUT": "10"})
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop(banco_suggest.COMMAND_ENV, None)
        self.openalex = FakeOpenAlex()
        fetch = mock.patch.object(profile, "FETCH", self.openalex)
        fetch.start()
        self.addCleanup(fetch.stop)

    def mcp(self, servers: dict) -> None:
        (self.root / ".mcp.json").write_text(json.dumps({"mcpServers": servers}, indent=2), encoding="utf-8")

    def stdio(self, tools: list[str]) -> dict:
        return {"type": "stdio", "command": sys.executable, "args": [str(self.fake)],
                "env": {"FAKE_TOOLS": json.dumps(tools)}}

    def cli(self, *argv: str) -> tuple[int, dict]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = idea_cli.main([*argv, str(self.root), "--json"])
        return code, json.loads(out.getvalue())

    def methods(self) -> list[str]:
        if not self.log.exists():
            return []
        return [json.loads(line)["method"] for line in self.log.read_text(encoding="utf-8").splitlines()]

    def interests(self) -> None:
        brief.record(self.root, "interests", {"keywords": ["eeg", "domain shift", "transfer learning"]})


class ChoiceTests(BankCase):
    def test_banco_lia_is_probed_when_chosen(self) -> None:
        with mock.patch.dict(os.environ, {banco_suggest.COMMAND_ENV: json.dumps([sys.executable, str(BANCO_FAKE)])}):
            code, body = self.cli("bank", "--choose", "banco-lia")
        self.assertEqual(code, 0)
        self.assertEqual(body["bank"]["choice"], "banco-lia")
        self.assertEqual(body["bank"]["server"], "banco-lia")
        self.assertTrue(body["bank"]["available"])
        self.assertTrue(body["bank"]["compatible"])
        self.assertIn("search_bank", body["bank"]["tools"])
        self.assertIsNotNone(body["bank"]["checked_at"])
        self.assertEqual(brief.load(self.root)["bank"], body["bank"])

    def test_an_unreachable_bank_records_the_reason(self) -> None:
        with mock.patch.dict(os.environ, {banco_suggest.COMMAND_ENV: json.dumps(["/nonexistent/banco-lia-mcp"])}):
            code, body = self.cli("bank", "--choose", "banco-lia")
        self.assertEqual(code, 0)
        self.assertFalse(body["bank"]["available"])
        self.assertIn("cannot start", body["bank"]["reason"])
        self.assertEqual(brief.load(self.root)["bank"]["reason"], body["bank"]["reason"])

    def test_another_compatible_server_is_used_like_banco_lia(self) -> None:
        self.mcp({"banco-lia": {"command": "uvx"}, "labbank": self.stdio(["search_bank", "taxonomy"])})
        code, body = self.cli("bank", "--list")
        self.assertEqual(body["managed"], "banco-lia")
        self.assertEqual([o["server"] for o in body["others"]], ["labbank"])
        code, body = self.cli("bank", "--choose", "labbank")
        self.assertEqual(code, 0)
        self.assertEqual((body["bank"]["choice"], body["bank"]["server"]), ("other", "labbank"))
        self.assertTrue(body["bank"]["compatible"])
        self.interests()
        proposed = topics.propose(self.root)
        cited = [e for t in proposed for e in t["evidence"] if e["source"] == "bank:labbank"]
        self.assertTrue(cited, "a compatible bank grounds a topic")
        self.assertIn("Graph models for EEG transfer", cited[0]["detail"])
        self.assertIn("tools/call", self.methods())

    def test_another_server_without_search_bank_is_not_compatible(self) -> None:
        self.mcp({"papers": self.stdio(["get_paper", "find"])})
        code, body = self.cli("bank", "--choose", "papers")
        self.assertEqual(code, 0)
        self.assertTrue(body["bank"]["available"])
        self.assertFalse(body["bank"]["compatible"])
        self.assertIn("mcp__papers__*", body["bank"]["reason"])
        self.interests()
        proposed = topics.propose(self.root)
        self.assertFalse([e for t in proposed for e in t["evidence"] if e["source"].startswith("bank:")])
        self.assertNotIn("tools/call", self.methods(), "an incompatible bank is never queried")
        self.assertFalse(bank.search(self.root, "eeg")["available"])

    def test_none_never_queries_a_bank(self) -> None:
        self.mcp({"labbank": self.stdio(["search_bank"])})

        def forbidden(*args, **kwargs):
            raise AssertionError("a bank was contacted although the choice is none")

        with mock.patch.object(bank, "CONNECT", forbidden):
            code, body = self.cli("bank", "--choose", "none")
            self.interests()
            proposed = topics.propose(self.root)
            self.assertEqual(bank.search(self.root, "eeg")["hits"], [])
        self.assertEqual(code, 0)
        self.assertEqual(body["bank"]["choice"], "none")
        self.assertEqual(len(proposed), 3)
        self.assertFalse([e for t in proposed for e in t["evidence"] if e["source"].startswith("bank:")])
        self.assertEqual(self.methods(), [])

    def test_a_managed_or_unknown_server_is_refused_as_another_bank(self) -> None:
        self.mcp({"asta": {"type": "http", "url": "https://example.invalid/mcp"}})
        code, body = self.cli("bank", "--choose", "asta")
        self.assertEqual((code, body["error"]), (1, "SERVER_MANAGED"))
        code, body = self.cli("bank", "--choose", "ghost")
        self.assertEqual((code, body["error"]), (1, "SERVER_UNKNOWN"))
        self.assertIsNone(brief.load(self.root)["bank"]["choice"])

    def test_the_managed_list_is_smiths_own(self) -> None:
        from papersmith import generators
        self.assertEqual(tuple(bank.MANAGED_MCP_SERVERS), tuple(generators.MANAGED_MCP_SERVERS))


class AddServerTests(BankCase):
    def test_add_keeps_every_other_server_and_key_order(self) -> None:
        original = {"//": "operator note", "mcpServers": {
            "banco-lia": {"type": "stdio", "command": "uvx", "args": ["banco-lia-mcp"]},
            "asta": {"type": "http", "url": "https://asta.example/mcp", "headers": {"x-api-key": "${ASTA_API_KEY:-}"}},
            "mine": {"command": "node", "args": ["mine.js"]}}, "extra": [1, 2]}
        (self.root / ".mcp.json").write_text(json.dumps(original, indent=2), encoding="utf-8")
        code, body = self.cli("bank", "--add", "labbank", "--command", "uvx lab-bank-mcp --index 'my index'")
        self.assertEqual(code, 0)
        self.assertEqual(body["added"], {"server": "labbank", "transport": "stdio", "command": "uvx",
                                         "args": ["lab-bank-mcp", "--index", "my index"]})
        written = json.loads((self.root / ".mcp.json").read_text(encoding="utf-8"))
        self.assertEqual(list(written), ["//", "mcpServers", "extra"])
        self.assertEqual(list(written["mcpServers"]), ["banco-lia", "asta", "mine", "labbank"])
        for name, entry in original["mcpServers"].items():
            self.assertEqual(written["mcpServers"][name], entry)
        self.assertEqual(written["extra"], [1, 2])
        code, body = self.cli("bank", "--add", "labbank", "--url", "https://x.example/mcp")
        self.assertEqual((code, body["error"]), (1, "SERVER_EXISTS"))
        code, body = self.cli("bank", "--add", "kaggle", "--url", "https://x.example/mcp")
        self.assertEqual((code, body["error"]), (1, "SERVER_MANAGED"))
        code, body = self.cli("bank", "--add", "web", "--url", "https://bank.example/mcp")
        self.assertEqual(body["added"], {"server": "web", "transport": "http", "url": "https://bank.example/mcp"})

    def test_add_creates_the_file_when_absent(self) -> None:
        code, body = self.cli("bank", "--add", "labbank", "--command", f"{sys.executable} {self.fake}")
        self.assertEqual(code, 0)
        self.assertIn("labbank", json.loads((self.root / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"])
        self.assertEqual(self.cli("bank", "--probe", "labbank")[1]["compatible"], True)

    def test_command_without_add_is_a_usage_error(self) -> None:
        code, body = self.cli("bank", "--command", "uvx x")
        self.assertEqual((code, body["error"]), (2, "USAGE"))


class _Umask:
    """Run a block under a known umask (restored afterwards)."""

    def __init__(self, mask: int) -> None:
        self.mask = mask

    def __enter__(self) -> None:
        self.old = os.umask(self.mask)

    def __exit__(self, *exc) -> None:
        os.umask(self.old)


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


class AddServerSafetyTests(BankCase):
    """``add_server`` keeps the file's mode, refuses a linked or malformed
    config and every bad name without touching the file, and writes atomically."""

    URL = "https://bank.example/mcp"

    def config(self) -> Path:
        return self.root / ".mcp.json"

    def snapshot(self) -> bytes:
        return self.config().read_bytes()

    def test_add_server_keeps_file_mode(self) -> None:
        self.mcp({"mine": {"command": "node"}})
        for index, mode in enumerate((0o644, 0o640, 0o600)):
            with self.subTest(mode=oct(mode)):
                os.chmod(self.config(), mode)
                bank.add_server(self.root, f"bank{index}", url=self.URL)
                self.assertEqual(_mode(self.config()), mode)
        self.config().unlink()
        for mask, expected in ((0o022, 0o644), (0o027, 0o640)):
            with self.subTest(umask=oct(mask)):
                if self.config().exists():
                    self.config().unlink()
                with _Umask(mask):
                    bank.add_server(self.root, "fresh", url=self.URL)
                self.assertEqual(_mode(self.config()), expected)
        self.assertEqual([p.name for p in self.root.iterdir() if p.name.endswith(".tmp")], [])

    def test_add_server_refuses_symlinked_config_unchanged(self) -> None:
        real = self.scratch / "shared-mcp.json"
        real.write_text(json.dumps({"mcpServers": {"mine": {"command": "node"}}}), encoding="utf-8")
        before = real.read_bytes()
        self.config().symlink_to(real)
        with self.assertRaises(brief.IdeaError) as ctx:
            bank.add_server(self.root, "labbank", url=self.URL)
        self.assertEqual(ctx.exception.code, "MCP_CONFIG_SYMLINK")
        self.assertIn("edit its target", ctx.exception.message)
        code, body = self.cli("bank", "--add", "labbank", "--url", self.URL)
        self.assertEqual((code, body["error"]), (1, "MCP_CONFIG_SYMLINK"))
        self.assertTrue(self.config().is_symlink())
        self.assertEqual(os.readlink(self.config()), str(real))
        self.assertEqual(real.read_bytes(), before)

    def test_add_server_preserves_unmanaged_servers_and_key_order(self) -> None:
        original = {"z-note": "first", "mcpServers": {
            "zeta": {"command": "z", "args": ["1"], "env": {"K": "v"}},
            "banco-lia": {"command": "uvx", "args": ["banco-lia-mcp"]},
            "alpha": {"type": "http", "url": "https://a.example/mcp", "headers": {"h": "${H:-x}"}},
            "kaggle": {"command": "kaggle-mcp"}}, "a-last": {"nested": [1, {"b": 2}]}}
        self.config().write_text(json.dumps(original, indent=2), encoding="utf-8")
        bank.add_server(self.root, "labbank", command="uvx lab-bank", args=["--index", "main"])
        written = json.loads(self.config().read_text(encoding="utf-8"))
        self.assertEqual(list(written), ["z-note", "mcpServers", "a-last"])
        self.assertEqual(list(written["mcpServers"]), ["zeta", "banco-lia", "alpha", "kaggle", "labbank"])
        for name, entry in original["mcpServers"].items():
            self.assertEqual(written["mcpServers"][name], entry)
            self.assertEqual(list(written["mcpServers"][name]), list(entry))
        self.assertEqual(written["a-last"], original["a-last"])
        self.assertEqual(written["mcpServers"]["labbank"],
                         {"type": "stdio", "command": "uvx", "args": ["lab-bank", "--index", "main"]})

    def test_add_server_atomic_on_replace_and_dump_failure(self) -> None:
        self.mcp({"mine": {"command": "node"}})
        before = self.snapshot()

        def broken_replace(*args, **kwargs):
            raise OSError("disk full")

        def broken_dump(*args, **kwargs):
            raise ValueError("cannot serialise")

        for label, patcher in (("replace", mock.patch.object(bank.os, "replace", broken_replace)),
                               ("dump", mock.patch.object(bank.json, "dump", broken_dump))):
            with self.subTest(seam=label), patcher, self.assertRaises((OSError, ValueError)):
                bank.add_server(self.root, "labbank", url=self.URL)
            self.assertEqual(self.snapshot(), before)
            self.assertEqual(sorted(p.name for p in self.root.iterdir()), [".mcp.json", ".papersmith"])

    def test_add_server_refuses_malformed_config_unchanged(self) -> None:
        variants = {"not json": b"{not json", "a list": b"[1, 2]", "a string": b'"servers"',
                    "servers a list": b'{"mcpServers": []}', "servers a string": b'{"mcpServers": "x"}',
                    "empty": b"", "not utf-8": b'{"mcpServers": {"caf\xe9": {}}}'}
        for label, raw in variants.items():
            with self.subTest(variant=label):
                self.config().write_bytes(raw)
                with self.assertRaises(brief.IdeaError) as ctx:
                    bank.add_server(self.root, "labbank", url=self.URL)
                self.assertEqual(ctx.exception.code, "MCP_CONFIG_UNREADABLE")
                self.assertEqual(self.config().read_bytes(), raw)
                self.assertEqual(sorted(p.name for p in self.root.iterdir()), [".mcp.json", ".papersmith"])

    def test_add_server_refuses_managed_and_existing_names_unchanged(self) -> None:
        self.mcp({"labbank": {"command": "node"}})
        before = self.snapshot()
        for name, code in (("banco-lia", "SERVER_MANAGED"), ("kaggle", "SERVER_MANAGED"),
                           ("colab", "SERVER_MANAGED"), ("asta", "SERVER_MANAGED"),
                           ("labbank", "SERVER_EXISTS"), ("../evil", "SERVER_NAME_INVALID"),
                           ("a/b", "SERVER_NAME_INVALID")):
            with self.subTest(name=name):
                with self.assertRaises(brief.IdeaError) as ctx:
                    bank.add_server(self.root, name, url=self.URL)
                self.assertEqual(ctx.exception.code, code)
                self.assertEqual(self.snapshot(), before)
        self.assertFalse((self.root.parent / "evil").exists())

    def test_add_server_refuses_non_string_fields(self) -> None:
        self.mcp({"mine": {"command": "node"}})
        before = self.snapshot()
        for kwargs in ({"name": 123, "url": self.URL}, {"name": "x", "command": ["a"]},
                       {"name": "x", "url": {"u": 1}}, {"name": "x", "command": "a", "args": "b"},
                       {"name": "x", "command": "a", "args": [1]}, {"name": True, "command": "a"}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(brief.IdeaError) as ctx:
                    bank.add_server(self.root, **kwargs)
                self.assertEqual(ctx.exception.code, "FIELD_TYPE")
                self.assertEqual(self.snapshot(), before)

    def test_ensure_mcp_servers_keeps_idea_added_server(self) -> None:
        from papersmith import generators
        self.mcp({"mine": {"command": "node"}})
        bank.add_server(self.root, "labbank", command="uvx lab-bank")
        added = json.loads(self.snapshot())["mcpServers"]["labbank"]
        generators.ensure_mcp_servers(self.root, ["claude"])
        servers = json.loads(self.snapshot())["mcpServers"]
        self.assertEqual(servers["labbank"], added)
        self.assertEqual(servers["mine"], {"command": "node"})
        self.assertIn("banco-lia", servers)
        self.assertEqual([o["server"] for o in bank.choices(self.root)["others"]], ["mine", "labbank"])


class _McpHttp(BaseHTTPRequestHandler):
    tools: list[str] = ["search_bank"]

    def log_message(self, *args) -> None:  # keep the test output quiet
        pass

    def do_POST(self) -> None:  # noqa: N802
        message = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if "id" not in message:
            self.send_response(202)
            self.end_headers()
            return
        if message["method"] == "initialize":
            result = {"protocolVersion": "2025-03-26", "capabilities": {}}
        else:
            result = {"tools": [{"name": name} for name in self.tools]}
        body = f"event: message\ndata: {json.dumps({'jsonrpc': '2.0', 'id': message['id'], 'result': result})}\n\n"
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Mcp-Session-Id", "s1")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def do_DELETE(self) -> None:  # noqa: N802
        self.send_response(200)
        self.end_headers()


class HttpServerTests(BankCase):
    def test_an_http_bank_added_by_url_is_probed(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), _McpHttp)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        url = f"http://127.0.0.1:{server.server_address[1]}/mcp"
        self.assertEqual(self.cli("bank", "--add", "webbank", "--url", url)[0], 0)
        code, body = self.cli("bank", "--choose", "webbank")
        self.assertEqual(code, 0)
        self.assertTrue(body["bank"]["available"])
        self.assertTrue(body["bank"]["compatible"])

    def test_an_unreachable_http_bank_says_why(self) -> None:
        self.mcp({"down": {"type": "http", "url": "http://127.0.0.1:9/mcp"}})
        result = bank.probe(self.root, "down")
        self.assertFalse(result["available"])
        self.assertIn("down", result["reason"])


class StdioLaunchTests(BankCase):
    def test_server_launch_reads_any_stdio_entry_and_keeps_banco_lia_resolution(self) -> None:
        self.mcp({"labbank": self.stdio(["search_bank"]), "web": {"url": "https://x.example"}})
        argv, env = banco_suggest.server_launch(self.root, "labbank")
        self.assertEqual(argv, [sys.executable, str(self.fake)])
        self.assertEqual(env, {"FAKE_TOOLS": '["search_bank"]'})
        self.assertEqual(banco_suggest.server_launch(self.root, "banco-lia")[0], banco_suggest.DEFAULT_COMMAND)
        with self.assertRaises(banco_suggest.Unavailable):
            banco_suggest.server_launch(self.root, "web")
        with self.assertRaises(banco_suggest.Unavailable):
            banco_suggest.server_launch(self.root, "ghost")


if __name__ == "__main__":
    unittest.main()
