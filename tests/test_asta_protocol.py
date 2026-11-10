"""The Asta wire format, against the shapes the live server answered with.

`skills/_core/literature/asta_protocol.py` holds no transport and no key, so
every case here feeds it bytes: event streams with the server's 15-second
`: ping` comments, a plain JSON body, the tool errors that arrive as HTTP 200
("... not found", "HTTP status 403 Forbidden."), and a stall that only a TOTAL
deadline can end.
"""

from __future__ import annotations

import ast
import importlib.util
import io
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "skills" / "_core" / "literature" / "asta_protocol.py"


def _load():
    spec = importlib.util.spec_from_file_location("test_asta_protocol_module", MODULE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


asta = _load()


def _reply(result: dict, request_id: int = 1) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _event(message: dict, *, pings: int = 0) -> bytes:
    lines = [f": ping - 2026-11-09 15:0{index}:00\n\n" for index in range(pings)]
    lines.append("event: message\n")
    lines.append(f"data: {json.dumps(message)}\n\n")
    return "".join(lines).encode("utf-8")


def _readline(raw: bytes):
    return io.BytesIO(raw).readline


PAPER = {"paperId": "64a2", "externalIds": {"DOI": "10.1088/1741-2552/aace8c", "CorpusId": 1},
         "title": "EEGNet", "year": 2016, "abstract": "Brain computer interfaces ...",
         "tldr": {"text": "A model wrote this."}}


class RequestTests(unittest.TestCase):
    def test_a_call_is_one_tools_call_with_the_key_only_in_its_header(self) -> None:
        url, body, headers = asta.request("get_paper", {"paper_id": "DOI:10.1/x", "fields": "title"},
                                          key="  secret-key-1234  ")
        payload = json.loads(body)
        assert url == asta.ENDPOINT == "https://asta-tools.allen.ai/mcp/v1"
        assert payload == {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                           "params": {"name": "get_paper",
                                      "arguments": {"paper_id": "DOI:10.1/x", "fields": "title"}}}
        assert headers["x-api-key"] == "secret-key-1234"
        assert headers["Accept"] == "application/json, text/event-stream"
        assert headers["MCP-Protocol-Version"] == "2025-06-18"
        assert b"secret-key" not in body

    def test_no_key_means_no_header_at_all(self) -> None:
        for key in (None, "", "   "):
            _url, _body, headers = asta.request("get_paper", {}, key=key)
            assert "x-api-key" not in headers

    def test_paper_ids_name_the_work_not_one_upload(self) -> None:
        assert asta.paper_id("doi", " 10.1016/j.neunet.2014.09.003 ") == "DOI:10.1016/j.neunet.2014.09.003"
        assert asta.paper_id("arxiv", "2106.15928v2") == "ARXIV:2106.15928"
        with self.assertRaises(ValueError):
            asta.paper_id("title", "x")


class ReadMessageTests(unittest.TestCase):
    def test_pings_are_skipped_and_the_reply_is_returned(self) -> None:
        message = _reply({"content": [{"type": "text", "text": json.dumps(PAPER)}], "isError": False})
        got = asta.read_message(_readline(_event(message, pings=3)), deadline=float("inf"))
        assert got == message

    def test_a_plain_json_body_is_read_too(self) -> None:
        message = _reply({"content": [], "isError": False})
        raw = json.dumps(message, indent=2).encode("utf-8")
        assert asta.read_message(_readline(raw), deadline=float("inf")) == message

    def test_multi_line_data_and_notifications_are_handled(self) -> None:
        notification = {"jsonrpc": "2.0", "method": "notifications/progress", "params": {}}
        message = _reply({"content": [], "isError": False})
        text = json.dumps(message, indent=1).splitlines()
        raw = (f"data: {json.dumps(notification)}\n\n"
               + "".join(f"data: {line}\n" for line in text) + "\n").encode("utf-8")
        assert asta.read_message(_readline(raw), deadline=float("inf")) == message

    def test_a_final_event_without_a_blank_line_still_dispatches(self) -> None:
        message = _reply({"content": [], "isError": False})
        raw = f"event: message\ndata: {json.dumps(message)}\n".encode("utf-8")
        assert asta.read_message(_readline(raw), deadline=float("inf")) == message

    def test_a_stream_of_pings_ends_at_the_total_deadline(self) -> None:
        """Each ping returns a line, so a per-read timeout never fires; the
        deadline is checked after every line instead."""
        ticks = iter(range(100))

        def readline() -> bytes:
            return b": ping - 2026-11-09\n"

        with self.assertRaises(asta.AstaError) as caught:
            asta.read_message(readline, deadline=5, clock=lambda: next(ticks))
        assert caught.exception.kind == asta.UNAVAILABLE
        assert "deadline" in str(caught.exception)

    def test_end_of_stream_without_the_reply_is_unavailable(self) -> None:
        other = _reply({"content": [], "isError": False}, request_id=7)
        for raw in (b"", b": ping\n\n", _event(other)):
            with self.subTest(raw=raw[:20]):
                with self.assertRaises(asta.AstaError) as caught:
                    asta.read_message(_readline(raw), deadline=float("inf"))
                assert caught.exception.kind == asta.UNAVAILABLE

    def test_an_oversized_answer_is_refused(self) -> None:
        raw = b": " + b"x" * (asta.MAX_RESPONSE_BYTES + 10) + b"\n"
        with self.assertRaises(asta.AstaError):
            asta.read_message(_readline(raw), deadline=float("inf"))

    def test_an_event_that_is_not_json_is_unavailable(self) -> None:
        with self.assertRaises(asta.AstaError) as caught:
            asta.read_message(_readline(b"data: {not json\n\n"), deadline=float("inf"))
        assert caught.exception.kind == asta.UNAVAILABLE


class ToolResultTests(unittest.TestCase):
    def test_texts_of_a_successful_call(self) -> None:
        message = _reply({"content": [{"type": "text", "text": "a"}, {"type": "image"},
                                      {"type": "text", "text": "b"}], "isError": False})
        assert asta.tool_texts(message) == ["a", "b"]

    def test_tool_errors_are_classified_from_their_text(self) -> None:
        cases = {
            "Error executing tool get_paper: Paper with id DOI:10.1038/nature14539 not found": asta.NOT_FOUND,
            "Error executing tool get_paper: Paper with id DOI:10.403/x not found": asta.NOT_FOUND,
            "Error executing tool get_paper: HTTP status 403 Forbidden.": asta.REFUSED,
            "Error executing tool search: HTTP status 401 Unauthorized": asta.REFUSED,
            "Error executing tool search: HTTP status 429 Too Many Requests": asta.UNAVAILABLE,
            "Error executing tool search: HTTP status 503 Service Unavailable": asta.UNAVAILABLE,
            "something nobody anticipated": asta.UNAVAILABLE,
        }
        for text, kind in cases.items():
            with self.subTest(text=text):
                message = _reply({"content": [{"type": "text", "text": text}], "isError": True})
                with self.assertRaises(asta.AstaError) as caught:
                    asta.tool_texts(message)
                assert caught.exception.kind == kind
                assert asta.classify(text) == kind

    def test_a_json_rpc_error_is_unavailable(self) -> None:
        with self.assertRaises(asta.AstaError) as caught:
            asta.tool_texts({"jsonrpc": "2.0", "id": 1, "error": {"code": -32602, "message": "bad"}})
        assert caught.exception.kind == asta.UNAVAILABLE

    def test_papers_accepts_one_paper_a_list_and_a_page(self) -> None:
        one = json.dumps(PAPER)
        assert asta.papers([one]) == [PAPER]
        assert asta.papers([json.dumps([PAPER, PAPER, "junk"])]) == [PAPER, PAPER]
        assert asta.papers([json.dumps({"total": 2, "data": [PAPER, PAPER]})]) == [PAPER, PAPER]
        assert asta.papers([one, "a note, not JSON"]) == [PAPER]
        assert asta.papers([]) == []

    def test_an_answer_that_is_all_prose_is_unavailable_not_empty(self) -> None:
        with self.assertRaises(asta.AstaError) as caught:
            asta.papers(["No papers matched, sorry."])
        assert caught.exception.kind == asta.UNAVAILABLE

    def test_redact_masks_each_secret(self) -> None:
        assert asta.redact("key=abc12345 and abc12345", "abc12345", None, "") == \
            "key=<redacted> and <redacted>"


def _import_roots() -> set[str]:
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


class ModuleShapeTests(unittest.TestCase):
    def test_it_imports_only_the_standard_library(self) -> None:
        roots = _import_roots()
        assert roots <= set(sys.stdlib_module_names), roots - set(sys.stdlib_module_names)

    def test_it_opens_no_connection_of_its_own(self) -> None:
        """Each caller keeps its own transport (and its own test seam)."""
        assert not _import_roots() & {"urllib", "socket", "http", "ssl", "asyncio"}


if __name__ == "__main__":
    unittest.main()
