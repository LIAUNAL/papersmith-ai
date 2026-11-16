"""The `asta` resolver and the OpenAlex key, through the resolver's own seam.

Every request goes through `paper_resolve.OPENER`, replaced here by a
recording fake, so no test touches the network. The key store is the suite's
throwaway one (`PAPERSMITH_KEYS_DIR`, set by conftest); a test that needs a key
stores one there, exactly as `smith keys set` would.

What these pin, from the live server's behaviour (2026-11-09): Asta is asked
only with its key; it answers over an event stream whose pings must not change
the record's digest; a missing paper and a refused key both arrive as HTTP 200
with `isError`; a model-written `tldr` is never an abstract; and no key ever
reaches a result, a cache file, a refusal or stdout.
"""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import time
import unittest
import urllib.error
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

FORGE_ROOT = Path(__file__).resolve().parents[1]
SKILL_SCRIPTS = FORGE_ROOT / "skills" / "paper-writing" / "scripts"
sys.path.insert(0, str(SKILL_SCRIPTS))
import paper_bib  # noqa: E402
import paper_cli  # noqa: E402
import paper_resolve  # noqa: E402
from impl_refusals import Refused  # noqa: E402

from test_api_keys import load_api_keys  # noqa: E402

api_keys = load_api_keys()
ASTA_KEY = "asta-key-0123456789abcdef"
OPENALEX_KEY = "openalex-key-ABCDEFGH"
CONFIG = {"paper_writing": {"contact": "", "roles": {
    "resolution": ["asta", "openalex", "crossref", "arxiv"], "full-text": ["openalex", "arxiv"],
    "discovery": ["asta"]}}}

PAPER = {"paperId": "64a2", "externalIds": {"DOI": "10.1016/j.neunet.2014.09.003", "CorpusId": 1},
         "title": "Deep learning in neural networks: An overview", "year": 2014,
         "venue": "Neural Networks", "journal": {"name": "Neural Networks"},
         "publicationVenue": {"name": "Neural Networks", "issn": "0893-6080"},
         "authors": [{"authorId": "1", "name": "J. Schmidhuber"}],
         "abstract": "In recent years,\n deep artificial neural networks have won numerous contests.",
         "tldr": {"text": "A model wrote this summary."}}


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def sse(result: dict, *, pings: int = 0, stamp: str = "15:00") -> bytes:
    message = {"jsonrpc": "2.0", "id": 1, "result": result}
    lines = "".join(f": ping - 2026-11-09 {stamp}:{i:02d}\n\n" for i in range(pings))
    return (lines + "event: message\n" + f"data: {json.dumps(message)}\n\n").encode("utf-8")


def tool_ok(payload) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(payload, indent=2)}], "isError": False}


def tool_error(text: str) -> dict:
    return {"content": [{"type": "text", "text": text}], "isError": True}


class Recorder:
    """Answers each request from `reply(request)`; records every request."""

    def __init__(self, reply) -> None:
        self.reply = reply
        self.requests = []

    def open(self, request, timeout=None):
        self.requests.append(request)
        answer = self.reply(request)
        if isinstance(answer, Exception):
            raise answer
        return Response(answer)

    def calls(self) -> list[dict]:
        found = []
        for request in self.requests:
            body = json.loads(request.data) if request.data else None
            found.append({"url": request.full_url, "method": request.get_method(),
                          "headers": {k.lower(): v for k, v in request.header_items()}, "body": body})
        return found


class AstaCase(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.tmp = Path(holder.name).resolve()
        patchers = [mock.patch.dict(os.environ, {api_keys.STORE_DIR_ENV: str(self.tmp / "keys")}),
                    mock.patch.object(paper_resolve, "_RETRY_DELAY_SECONDS", 0),
                    mock.patch.object(paper_resolve, "_ASTA_MIN_INTERVAL_SECONDS", 0)]
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)
        for variable in ("ASTA_API_KEY", "OPENALEX_API_KEY"):
            os.environ.pop(variable, None)
        self._opener = paper_resolve.OPENER
        self.addCleanup(setattr, paper_resolve, "OPENER", self._opener)

    def use(self, reply) -> Recorder:
        recorder = Recorder(reply)
        paper_resolve.OPENER = recorder
        return recorder

    def resolve(self, identifier: str, resolver: str = "asta", config: dict | None = None) -> dict:
        return paper_resolve.resolve_identifier(identifier, resolver=resolver, role="resolution",
                                                config=config or CONFIG)


class WithoutAKeyTests(AstaCase):
    def test_asta_is_never_asked_without_its_key(self) -> None:
        recorder = self.use(lambda request: AssertionError("no request expected"))
        with self.assertRaises(Refused) as caught:
            self.resolve("10.1016/j.neunet.2014.09.003")
        assert caught.exception.code == "RESOLVER_ROLE_EMPTY"
        assert "smith keys set asta" in caught.exception.detail
        assert recorder.requests == []

    def test_the_active_connectors_drop_a_keyed_one_without_its_key(self) -> None:
        assert paper_resolve.active_connectors(CONFIG, "resolution") == ["openalex", "crossref", "arxiv"]
        api_keys.store("asta", ASTA_KEY)
        assert paper_resolve.active_connectors(CONFIG, "resolution") == ["asta", "openalex", "crossref", "arxiv"]

    def test_a_role_of_keyed_connectors_only_refuses_by_name(self) -> None:
        config = {"paper_writing": {"roles": {"resolution": ["asta"], "discovery": ["asta"]}}}
        for role, code in (("resolution", "RESOLVER_ROLE_EMPTY"), ("discovery", "DISCOVERY_UNAVAILABLE")):
            with self.assertRaises(Refused) as caught:
                paper_resolve.active_connectors(config, role)
            assert caught.exception.code == code


class AstaLookupTests(AstaCase):
    def setUp(self) -> None:
        super().setUp()
        api_keys.store("asta", ASTA_KEY)

    def test_a_doi_is_one_keyed_get_paper_call(self) -> None:
        recorder = self.use(lambda request: sse(tool_ok(PAPER), pings=2))

        result = self.resolve("https://doi.org/10.1016/j.neunet.2014.09.003")

        (call,) = recorder.calls()
        assert call["url"] == "https://asta-tools.allen.ai/mcp/v1" and call["method"] == "POST"
        assert call["headers"]["x-api-key"] == ASTA_KEY
        assert call["body"]["params"]["name"] == "get_paper"
        arguments = call["body"]["params"]["arguments"]
        assert arguments["paper_id"] == "DOI:10.1016/j.neunet.2014.09.003"
        fields = arguments["fields"].split(",")
        assert "abstract" in fields and "tldr" not in fields and "openAccessPdf" not in fields
        assert result["resolver"] == "asta"
        assert result["title"] == PAPER["title"] and result["year"] == 2014
        assert result["doi"] == "10.1016/j.neunet.2014.09.003"
        assert result["authors"] == ["J. Schmidhuber"] and result["venue"] == "Neural Networks"
        assert result["abstract"] == "In recent years, deep artificial neural networks have won numerous contests."
        assert result["full_text_url"] is None

    def test_an_arxiv_id_drops_its_version(self) -> None:
        recorder = self.use(lambda request: sse(tool_ok({**PAPER, "externalIds": {"ArXiv": "1706.03762"}})))
        self.resolve("arXiv:1706.03762v5")
        assert recorder.calls()[0]["body"]["params"]["arguments"]["paper_id"] == "ARXIV:1706.03762"

    def test_a_tldr_is_never_an_abstract_and_markup_is_never_stripped(self) -> None:
        for paper, expected in (({**PAPER, "abstract": None}, None),
                                ({**PAPER, "abstract": "<jats:p>Tagged text.</jats:p>"}, None),
                                ({**PAPER, "abstract": "x < y holds when a > b."}, "x < y holds when a > b.")):
            with self.subTest(abstract=paper["abstract"]):
                self.use(lambda request, paper=paper: sse(tool_ok(paper)))
                assert self.resolve("10.1/x")["abstract"] == expected

    def test_the_digest_is_the_tools_text_not_the_stream_framing(self) -> None:
        self.use(lambda request: sse(tool_ok(PAPER), pings=0))
        first = self.resolve("10.1/x")["metadata_digest"]
        self.use(lambda request: sse(tool_ok(PAPER), pings=3, stamp="16:30"))
        second = self.resolve("10.1/x")["metadata_digest"]
        import hashlib

        assert first == second == hashlib.sha256(json.dumps(PAPER, indent=2).encode("utf-8")).hexdigest()

    def test_a_missing_paper_is_unresolved(self) -> None:
        self.use(lambda request: sse(tool_error(
            "Error executing tool get_paper: Paper with id DOI:10.1038/nature14539 not found")))
        with self.assertRaises(Refused) as caught:
            self.resolve("10.1038/nature14539")
        assert caught.exception.code == "IDENTIFIER_UNRESOLVED"

    def test_a_refused_key_is_resolver_refused_and_never_echoed(self) -> None:
        for answer in (sse(tool_error("Error executing tool get_paper: HTTP status 403 Forbidden.")),
                       urllib.error.HTTPError("https://asta-tools.allen.ai/mcp/v1", 401, "no", {}, None)):
            with self.subTest(answer=type(answer).__name__):
                self.use(lambda request, answer=answer: answer)
                with self.assertRaises(Refused) as caught:
                    self.resolve("10.1/x")
                assert caught.exception.code == "RESOLVER_REFUSED"
                assert ASTA_KEY not in str(caught.exception.detail)

    def test_transport_failures_are_unreachable_after_one_retry(self) -> None:
        for failure in (urllib.error.URLError("down"), urllib.error.HTTPError("u", 503, "busy", {}, None),
                        sse(tool_error("Error executing tool get_paper: HTTP status 429 Too Many Requests"))):
            with self.subTest(failure=repr(failure)[:40]):
                recorder = self.use(lambda request, failure=failure: failure)
                with self.assertRaises(Refused) as caught:
                    self.resolve("10.1/x")
                assert caught.exception.code == "RESOLVER_UNREACHABLE"
                assert len(recorder.requests) == 2

    def test_a_silent_lookup_is_asked_again(self) -> None:
        # Live on 2026-11-11, a keyed lookup answered within a second or only
        # after 30 s or more, and a fresh request usually answered at once.
        answers = [TimeoutError("timed out"), TimeoutError("timed out"), sse(tool_ok(PAPER))]
        recorder = self.use(lambda request: answers.pop(0))
        result = self.resolve("10.1016/j.neunet.2014.09.003")
        assert result["resolver"] == "asta" and result["title"] == PAPER["title"]
        assert len(recorder.requests) == 3

    def test_silent_lookups_stop_at_the_deadline(self) -> None:
        with mock.patch.object(paper_resolve, "_ASTA_LOOKUP_DEADLINE_SECONDS", 0.4), \
                mock.patch.object(paper_resolve, "_ASTA_MIN_INTERVAL_SECONDS", 0.05):
            recorder = self.use(lambda request: TimeoutError("timed out"))
            started = time.monotonic()
            with self.assertRaises(Refused) as caught:
                self.resolve("10.1/x")
        assert caught.exception.code == "RESOLVER_UNREACHABLE"
        assert len(recorder.requests) > 2
        assert time.monotonic() - started < 2

    def test_a_spent_deadline_never_blocks(self) -> None:
        with mock.patch.object(paper_resolve, "_ASTA_LOOKUP_DEADLINE_SECONDS", 0):
            recorder = self.use(lambda request: sse(tool_ok(PAPER)))
            with self.assertRaises(Refused) as caught:
                self.resolve("10.1/x")
        assert caught.exception.code == "RESOLVER_UNREACHABLE"
        assert recorder.requests == []

    def test_title_search_names_each_work_by_its_doi_or_arxiv_id(self) -> None:
        papers = [PAPER, {**PAPER, "externalIds": {"ArXiv": "2401.00001"}, "title": "Preprint"},
                  {**PAPER, "externalIds": {}, "paperId": "abc", "title": "Bare"}]
        recorder = self.use(lambda request: sse(tool_ok({"data": papers})))
        works = paper_resolve.search_title("Deep learning", role="resolution", config=CONFIG, connector="asta")
        assert recorder.calls()[0]["body"]["params"]["name"] == "search_paper_by_title"
        assert [work["identifier"] for work in works] == [
            "10.1016/j.neunet.2014.09.003", "arXiv:2401.00001", "https://www.semanticscholar.org/paper/abc"]
        assert {work["resolver"] for work in works} == {"asta"}

    def test_the_key_reaches_no_result_cache_or_stdout(self) -> None:
        self.use(lambda request: sse(tool_ok(PAPER)))
        cache = FORGE_ROOT / ".scratch" / f".asta-cache-{os.getpid()}"
        self.addCleanup(lambda: __import__("shutil").rmtree(cache, ignore_errors=True))
        out = io.StringIO()
        with mock.patch.object(paper_resolve, "load_config", return_value=CONFIG), redirect_stdout(out):
            code = paper_cli.main(["resolve", "--identifier", "10.1/x", "--resolver", "asta",
                                   "--role", "resolution", "--cache-dir", str(cache)])
        assert code == 0, out.getvalue()
        written = "".join(path.read_text(encoding="utf-8") for path in cache.glob("*.json"))
        assert written and ASTA_KEY not in written and ASTA_KEY not in out.getvalue()


class OpenAlexKeyTests(AstaCase):
    def config(self) -> dict:
        return {"paper_writing": {"contact": "me@example.org", "roles": {"resolution": ["openalex"]}}}

    def test_keyless_urls_are_byte_identical_to_before(self) -> None:
        url = paper_resolve._openalex_url("10.1/x", self.config())
        assert url == "https://api.openalex.org/works/https://doi.org/10.1/x?mailto=me%40example.org"

    def test_a_configured_key_rides_only_openalex_calls(self) -> None:
        api_keys.store("openalex", OPENALEX_KEY)
        assert f"api_key={OPENALEX_KEY}" in paper_resolve._openalex_url("10.1/x", self.config())
        recorder = self.use(lambda request: b"%PDF-1.4")
        paper_resolve.fetch_bytes("https://example.org/paper.pdf", config=self.config())
        assert "api_key" not in recorder.requests[0].full_url

    def test_a_refused_key_is_resolver_refused_with_the_key_masked(self) -> None:
        api_keys.store("openalex", OPENALEX_KEY)
        self.use(lambda request: urllib.error.HTTPError(request.full_url, 401, "no", {}, None))
        with self.assertRaises(Refused) as caught:
            self.resolve("10.1/x", resolver="openalex", config=self.config())
        assert caught.exception.code == "RESOLVER_REFUSED"
        assert OPENALEX_KEY not in caught.exception.detail and "<redacted>" in caught.exception.detail

    def test_keyless_401_stays_what_it_was(self) -> None:
        self.use(lambda request: urllib.error.HTTPError(request.full_url, 401, "no", {}, None))
        with self.assertRaises(Refused) as caught:
            self.resolve("10.1/x", resolver="openalex", config=self.config())
        assert caught.exception.code == "IDENTIFIER_UNRESOLVED"


class ChainTests(AstaCase):
    def answer(self, request):
        if "asta-tools" in request.full_url:
            paper_id = json.loads(request.data)["params"]["arguments"]["paper_id"]
            return self.asta.get(paper_id, sse(tool_error(f"Paper with id {paper_id} not found")))
        for fragment, payload in self.others.items():
            if fragment in request.full_url:
                return payload
        return urllib.error.HTTPError(request.full_url, 404, "not found", {}, None)

    def setUp(self) -> None:
        super().setUp()
        self.asta, self.others = {}, {}

    def chain(self, identifier: str):
        recorder = self.use(self.answer)
        record, attempts = paper_resolve.resolve_chain(identifier, role="resolution", config=CONFIG)
        return record, attempts, recorder

    def test_the_chain_follows_the_role_with_abstractless_connectors_last(self) -> None:
        assert paper_resolve.chain_for("doi", ["crossref", "asta", "openalex"]) == ["asta", "openalex", "crossref"]
        assert paper_resolve.chain_for("arxiv", ["arxiv", "asta", "openalex"]) == ["arxiv", "asta"]
        assert paper_resolve.chain_for("title", ["openalex", "crossref", "asta"]) == ["openalex", "asta"]

    def test_the_keyless_semantic_scholar_connector_resolves_either_kind_in_a_chain(self) -> None:
        assert paper_resolve.chain_for("doi", ["crossref", "semantic-scholar"]) == ["semantic-scholar", "crossref"]
        assert paper_resolve.chain_for("arxiv", ["arxiv", "semantic-scholar"]) == ["arxiv", "semantic-scholar"]
        assert paper_resolve.chain_for("title", ["semantic-scholar", "openalex"]) == ["openalex"]
        # The chain hands each connector the bare id; Semantic Scholar must still ask for an arXiv id.
        self.others["api.semanticscholar.org"] = json.dumps({
            "title": "T", "year": 2024, "externalIds": {"ArXiv": "2401.00001"}, "abstract": "An abstract."}).encode()
        config = {"paper_writing": {"contact": "", "roles": {**CONFIG["paper_writing"]["roles"],
                                                             "resolution": ["semantic-scholar"]}}}
        recorder = self.use(self.answer)
        record, attempts = paper_resolve.resolve_chain("arXiv:2401.00001", role="resolution", config=config)
        assert record["resolver"] == "semantic-scholar" and record["abstract"] == "An abstract."
        assert "/paper/ARXIV:2401.00001?" in recorder.requests[0].full_url
        assert attempts == [{"resolver": "semantic-scholar", "outcome": "abstract"}]
        assert paper_bib.source_identity("arXiv:2401.00001", "semantic-scholar") == ("arxiv", "2401.00001")
        assert paper_bib.source_identity("DOI:10.1/X", "semantic-scholar") == ("doi", "10.1/x")

    def test_with_the_key_asta_answers_first(self) -> None:
        api_keys.store("asta", ASTA_KEY)
        self.asta["DOI:10.1/x"] = sse(tool_ok(PAPER))
        record, attempts, recorder = self.chain("10.1/x")
        assert record["resolver"] == "asta" and len(recorder.requests) == 1
        assert attempts == [{"resolver": "asta", "outcome": "abstract"}]

    def test_an_asta_record_without_an_abstract_falls_through_whole(self) -> None:
        api_keys.store("asta", ASTA_KEY)
        self.asta["DOI:10.1/x"] = sse(tool_ok({**PAPER, "abstract": None}))
        index = {"An": [0], "abstract": [1]}
        self.others["api.openalex.org"] = json.dumps({"title": "OA title", "doi": "https://doi.org/10.1/x",
                                                      "publication_year": 2014,
                                                      "abstract_inverted_index": index}).encode()
        record, attempts, _ = self.chain("10.1/x")
        assert (record["resolver"], record["title"], record["abstract"]) == ("openalex", "OA title", "An abstract")
        assert [a["resolver"] for a in attempts] == ["asta", "openalex"]

    def test_without_the_key_the_chain_is_todays(self) -> None:
        self.others["api.openalex.org"] = json.dumps({"title": "T", "doi": "https://doi.org/10.1/x",
                                                      "publication_year": 2020}).encode()
        self.others["api.crossref.org"] = json.dumps({"message": {"title": ["T"], "DOI": "10.1/x"}}).encode()
        record, attempts, recorder = self.chain("10.1/x")
        assert all("asta-tools" not in request.full_url for request in recorder.requests)
        # OpenAlex found the work without an abstract; Crossref never carries one.
        assert record["resolver"] == "openalex" and [a["resolver"] for a in attempts] == ["openalex"]

    def test_nothing_resolves_refuses_by_the_strongest_reason(self) -> None:
        api_keys.store("asta", ASTA_KEY)
        refused = sse(tool_error("HTTP status 403 Forbidden."))
        self.asta["DOI:10.1/x"] = refused
        with self.assertRaises(Refused) as caught:
            self.chain("10.1/x")
        assert caught.exception.code == "IDENTIFIER_UNRESOLVED"  # OpenAlex and Crossref answered "no such work"
        with self.assertRaises(Refused) as caught:
            paper_resolve.resolve_chain("not an id", role="resolution", config=CONFIG)
        assert caught.exception.code == "IDENTIFIER_UNRESOLVED"

    def test_the_cli_auto_mode_caches_only_the_kept_record(self) -> None:
        api_keys.store("asta", ASTA_KEY)
        self.asta["DOI:10.1/x"] = sse(tool_ok(PAPER))
        cache = FORGE_ROOT / ".scratch" / f".asta-auto-{os.getpid()}"
        self.addCleanup(lambda: __import__("shutil").rmtree(cache, ignore_errors=True))
        self.use(self.answer)
        out = io.StringIO()
        with mock.patch.object(paper_resolve, "load_config", return_value=CONFIG), redirect_stdout(out):
            code = paper_cli.main(["resolve", "--identifier", "10.1/x", "--resolver", "auto",
                                   "--role", "resolution", "--cache-dir", str(cache)])
        assert code == 0, out.getvalue()
        payload = json.loads(out.getvalue())
        assert payload["resolver"] == "asta" and payload["attempts"][0]["resolver"] == "asta"
        assert len(list(cache.glob("*.json"))) == 1


if __name__ == "__main__":
    unittest.main()
