"""journal-finder with Ai2's Asta: asked only with its key, never presented as OpenAlex.

The CLI runs as a subprocess against `FakeApi` (OpenAlex, Crossref, ...) and a
small Asta stand-in that answers MCP `tools/call` POSTs the way the live server
does: an event stream with a keep-alive ping, then one `data:` line. With the
Asta key, Asta's relevance search picks the works like the paper and OpenAlex
describes the journals that published them; without it nothing changes.
"""

from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from test_journal_finder import JournalFinderCase

KEY = "asta-key-0123456789abcdef"
#: DOIs FakeApi's OpenAlex resolves by `filter=doi:` (tests/fixtures/journal_finder/openalex_cited_works.json).
KNOWN = ("10.1111/nfl.1", "10.5555/cited.1", "10.5555/cited.2")


class AstaStandIn:
    def __init__(self, *, papers=None, error: str | None = None) -> None:
        self.papers = [{"paperId": f"p{i}", "title": f"Work {i}", "year": 2024,
                        "externalIds": {"DOI": doi}} for i, doi in enumerate(KNOWN)] if papers is None else papers
        self.error = error
        self.requests: list[dict] = []
        stand_in = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):  # noqa: N802
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
                stand_in.requests.append({"headers": {k.lower(): v for k, v in self.headers.items()},
                                          "body": body})
                if stand_in.error:
                    result = {"content": [{"type": "text", "text": stand_in.error}], "isError": True}
                else:
                    result = {"content": [{"type": "text", "text": json.dumps({"data": stand_in.papers})}],
                              "isError": False}
                message = {"jsonrpc": "2.0", "id": body.get("id"), "result": result}
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                self.wfile.write(b": ping - 2026-11-09 15:00:00\n\n")
                self.wfile.write(b"event: message\ndata: " + json.dumps(message).encode() + b"\n\n")

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.httpd.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}/mcp/v1"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


class AstaJournalTests(JournalFinderCase):
    def asta(self, **kwargs) -> AstaStandIn:
        stand_in = AstaStandIn(**kwargs)
        self.addCleanup(stand_in.close)
        return stand_in

    def env(self, stand_in: AstaStandIn, *, key: bool = True) -> dict:
        env = {"PAPERSMITH_ASTA_URL": stand_in.url, "PAPERSMITH_FALLBACK_MIN_INTERVAL": "0"}
        if key:
            env["ASTA_API_KEY"] = KEY
        return env

    def test_without_the_key_asta_is_never_called(self) -> None:
        self.start_api()
        stand_in = self.asta()
        result = self.search(extra_env=self.env(stand_in, key=False))
        self.assertEqual(result.code, 0, result.stdout + result.stderr)
        self.assertEqual(stand_in.requests, [])
        self.assertEqual(result.json["query"]["asta"], {"queried": False, "answered": False})
        self.assertNotEqual(result.json["query"]["search_mode"], "asta-relevance")

    def test_source_asta_without_a_key_refuses_by_name(self) -> None:
        self.start_api()
        stand_in = self.asta()
        result = self.search("--source", "asta", extra_env=self.env(stand_in, key=False))
        self.assertEqual(result.code, 2)
        self.assertEqual(result.json["error"], "NETWORK_UNAVAILABLE")
        self.assertIn("smith keys set asta", result.json["message"])
        self.assertEqual(stand_in.requests, [])

    def test_with_the_key_asta_picks_the_works_and_openalex_describes_the_journals(self) -> None:
        api = self.start_api()
        stand_in = self.asta()

        result = self.search(extra_env=self.env(stand_in))

        self.assertEqual(result.code, 0, result.stdout + result.stderr)
        document = result.json
        self.assertEqual(document["query"]["search_mode"], "asta-relevance")
        self.assertEqual(document["query"]["asta"], {"queried": True, "answered": True})
        self.assertEqual(document["providers"]["similar_works"], ["asta", "openalex"])
        self.assertTrue(any("asta" in candidate["sources"] for candidate in document["candidates"]))
        # The works were Asta's: OpenAlex was asked for them by DOI, never searched.
        searches = [hit for hit in api.hits("/openalex/works") if "search" in hit["params"]]
        self.assertEqual(searches, [])
        call = stand_in.requests[0]
        self.assertEqual(call["headers"]["x-api-key"], KEY)
        self.assertEqual(call["body"]["params"]["name"], "search_papers_by_relevance")
        self.assertTrue(call["body"]["params"]["arguments"]["publication_date_range"].endswith(":"))

    def test_source_asta_with_the_key_runs_the_same_path(self) -> None:
        self.start_api()
        stand_in = self.asta()
        result = self.search("--source", "asta", extra_env=self.env(stand_in))
        self.assertEqual(result.code, 0, result.stdout + result.stderr)
        self.assertEqual(result.json["source"], "asta")
        self.assertEqual(result.json["query"]["search_mode"], "asta-relevance")

    def test_a_failed_asta_search_falls_back_to_the_openalex_search_with_a_note(self) -> None:
        self.start_api()
        stand_in = self.asta(error="Error executing tool search_papers_by_relevance: HTTP status 503")
        result = self.search(extra_env=self.env(stand_in))
        self.assertEqual(result.code, 0, result.stdout + result.stderr)
        self.assertNotEqual(result.json["query"]["search_mode"], "asta-relevance")
        self.assertEqual(result.json["query"]["asta"], {"queried": True, "answered": False})
        self.assertTrue(any("Asta's relevance search failed" in note for note in result.json["notes"]))

    def test_a_refused_key_under_source_asta_refuses(self) -> None:
        self.start_api()
        stand_in = self.asta(error="Error executing tool search_papers_by_relevance: HTTP status 403 Forbidden.")
        result = self.search("--source", "asta", extra_env=self.env(stand_in))
        self.assertEqual(result.code, 2)
        self.assertEqual(result.json["error"], "NETWORK_UNAVAILABLE")
        self.assertNotIn(KEY, result.stdout + result.stderr)

    def test_the_key_reaches_no_output_no_file_and_no_cache(self) -> None:
        self.start_api()
        stand_in = self.asta()
        result = self.search(extra_env=self.env(stand_in))
        self.assertEqual(result.code, 0, result.stdout + result.stderr)
        self.assertNotIn(KEY, result.stdout + result.stderr)
        self.assertNotIn(KEY, self.out_file.read_text(encoding="utf-8"))
        for path in self.tmp.rglob("*"):
            if path.is_file():
                self.assertNotIn(KEY.encode(), path.read_bytes(), path)


if __name__ == "__main__":
    unittest.main()
