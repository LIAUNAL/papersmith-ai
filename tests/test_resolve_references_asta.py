"""`resolve --references` with Ai2's Asta in the role, through the same fake
transport `test_resolve_references.py` uses (no network).

The role names Asta first. Without the Asta key nothing changes: the exact
request sequence of a role that does not name it. With the key, Asta answers
first; a record without an abstract falls through to OpenAlex whole; a refused
key sets Asta aside for the rest of the run and the summary says so.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import tempfile
import unittest
import uuid
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from test_api_keys import load_api_keys
from test_resolve_references import CONFIG, FORGE_ROOT, Response, Transport, js, work

import paper_bib  # noqa: E402  (test_resolve_references put the scripts on sys.path)
import paper_cli  # noqa: E402
import paper_resolve  # noqa: E402

api_keys = load_api_keys()
ASTA_KEY = "asta-key-0123456789abcdef"
ASTA_CONFIG = {"paper_writing": {"contact": "", "roles": {
    "resolution": ["asta", "openalex", "crossref", "arxiv"], "full-text": [], "discovery": []}}}


def sse(result: dict) -> bytes:
    return ("event: message\n" + "data: " + json.dumps({"jsonrpc": "2.0", "id": 1, "result": result})
            + "\n\n").encode("utf-8")


def asta_paper(title: str, *, doi: str | None = None, abstract: str | None = None) -> bytes:
    paper = {"paperId": "p1", "title": title, "year": 2020, "externalIds": {"DOI": doi} if doi else {},
             "journal": {"name": "Asta Venue"}, "authors": [{"name": "A. Author"}], "abstract": abstract}
    return sse({"content": [{"type": "text", "text": json.dumps(paper)}], "isError": False})


class AstaTransport(Transport):
    """Routes Asta's POSTs by their `paper_id`/`title`; everything else as before."""

    def __init__(self, routes=None, asta=None) -> None:
        super().__init__(routes)
        self.asta = asta or {}
        self.calls: list[str] = []

    def open(self, request, timeout=None):
        if "asta-tools.allen.ai" not in request.full_url:
            return super().open(request, timeout)
        arguments = json.loads(request.data)["params"]["arguments"]
        target = arguments.get("paper_id") or f"title:{arguments.get('title')}"
        self.urls.append(request.full_url)
        self.calls.append(target)
        answer = self.asta.get(target)
        if answer is None:
            answer = sse({"content": [{"type": "text", "text": f"Paper with id {target} not found"}],
                          "isError": True})
        if isinstance(answer, Exception):
            raise answer
        return Response(answer)


class AstaReferencesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = FORGE_ROOT / ".scratch" / f".resolve-references-asta-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.paper = self.root / "paper"
        self.paper.mkdir(parents=True)
        self.sidecar = self.paper / ".paper-writing" / "references.json"
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        for patcher in (mock.patch.dict(os.environ, {api_keys.STORE_DIR_ENV: str(Path(holder.name) / "keys")}),
                        mock.patch.object(paper_resolve, "load_config", return_value=dict(ASTA_CONFIG)),
                        mock.patch.object(paper_resolve, "_RETRY_DELAY_SECONDS", 0),
                        mock.patch.object(paper_resolve, "_REQUEST_PAUSE_SECONDS", 0),
                        mock.patch.object(paper_resolve, "_ASTA_MIN_INTERVAL_SECONDS", 0)):
            patcher.start()
            self.addCleanup(patcher.stop)
        for variable in ("ASTA_API_KEY", "OPENALEX_API_KEY"):
            os.environ.pop(variable, None)

    def workspace(self, tex: str, bib: str) -> None:
        (self.paper / "main.tex").write_text(tex, encoding="utf-8")
        (self.paper / "refs.bib").write_text(bib, encoding="utf-8")

    def run_cli(self, transport, *extra: str) -> tuple[int, dict]:
        out = io.StringIO()
        with mock.patch.object(paper_resolve, "OPENER", transport), redirect_stdout(out):
            code = paper_cli.main(["resolve", "--references", "--paper", str(self.paper), *extra])
        return code, json.loads(out.getvalue())

    def records(self) -> dict:
        return json.loads(self.sidecar.read_text(encoding="utf-8"))["references"]

    def test_without_the_key_the_requests_are_exactly_todays(self) -> None:
        self.workspace("\\cite{a}", "@article{a, title={T}, doi={10.1/A}}\n")
        routes = {"api.openalex.org/works/https://doi.org/10.1/a": js(work("T", doi="10.1/a"))}
        with_asta = AstaTransport(dict(routes))
        self.run_cli(with_asta)
        with mock.patch.object(paper_resolve, "load_config", return_value=dict(CONFIG)):
            without = Transport(dict(routes))
            self.run_cli(without, "--force")
        assert with_asta.calls == []
        assert with_asta.urls == without.urls

    def test_with_the_key_asta_answers_first_with_its_abstract(self) -> None:
        api_keys.store("asta", ASTA_KEY)
        self.workspace("\\cite{a}", "@article{a, title={T}, doi={10.1/A}}\n")
        transport = AstaTransport(asta={"DOI:10.1/a": asta_paper("T", doi="10.1/a", abstract="Asta abstract.")})

        code, out = self.run_cli(transport)

        assert code == 0 and out["with_abstract"] == 1
        record = self.records()["a"]
        assert (record["resolver"], record["abstract"], record["venue"]) == ("asta", "Asta abstract.", "Asta Venue")
        assert record["link"] == "https://doi.org/10.1/a"
        assert transport.calls == ["DOI:10.1/a"] and len(transport.urls) == 1

    def test_an_asta_record_without_an_abstract_yields_to_openalex_whole(self) -> None:
        api_keys.store("asta", ASTA_KEY)
        self.workspace("\\cite{a}", "@article{a, title={T}, doi={10.1/A}}\n")
        transport = AstaTransport(
            {"api.openalex.org/works/https://doi.org/10.1/a": js(work("T", doi="10.1/a", abstract="OA words"))},
            asta={"DOI:10.1/a": asta_paper("T", doi="10.1/a")})

        self.run_cli(transport)

        record = self.records()["a"]
        assert (record["resolver"], record["abstract"], record["venue"]) == ("openalex", "OA words", "Venue")

    def test_a_refused_key_sets_asta_aside_for_the_run(self) -> None:
        api_keys.store("asta", ASTA_KEY)
        self.workspace("\\cite{a,b}", "@article{a, title={T}, doi={10.1/A}}\n@article{b, title={U}, doi={10.1/B}}\n")
        refused = sse({"content": [{"type": "text", "text": "HTTP status 403 Forbidden."}], "isError": True})
        transport = AstaTransport(
            {"api.openalex.org/works/https://doi.org/10.1/a": js(work("T", doi="10.1/a", abstract="One")),
             "api.openalex.org/works/https://doi.org/10.1/b": js(work("U", doi="10.1/b", abstract="Two"))},
            asta={"DOI:10.1/a": refused, "DOI:10.1/b": refused})

        code, out = self.run_cli(transport)

        assert code == 0 and out["resolved"] == 2
        assert transport.calls == ["DOI:10.1/a"]  # asked once, then set aside
        assert out["connectors_down"] == ["asta (identifier): RESOLVER_REFUSED"]
        assert {record["resolver"] for record in self.records().values()} == {"openalex"}
        assert ASTA_KEY not in json.dumps(out)


class IdentityTests(unittest.TestCase):
    def test_an_asta_record_names_its_kind_by_its_identifier(self) -> None:
        assert paper_bib.source_identity("https://doi.org/10.1/X", "asta") == ("doi", "10.1/x")
        assert paper_bib.source_identity("arXiv:2401.00001v2", "asta") == ("arxiv", "2401.00001v2")
        assert paper_bib.source_identity("https://www.semanticscholar.org/paper/abc", "asta") is None

    def test_an_asta_arxiv_record_links_to_arxiv(self) -> None:
        link = paper_bib._reference_link({"resolver": "asta", "identifier": "arXiv:2401.00001"})
        assert link == "https://arxiv.org/abs/2401.00001"
        page = "https://www.semanticscholar.org/paper/abc"
        assert paper_bib._reference_link({"resolver": "asta", "identifier": page}) == page


if __name__ == "__main__":
    unittest.main()
