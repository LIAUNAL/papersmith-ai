"""`resolve --references`: metadata for every cited key, in one sidecar.

The verb runs in process through `paper_cli.main`, with the module-level
`paper_resolve.OPENER` seam replaced by a fake transport, so no test touches
the network. `--paper` must resolve inside the repository, so the workspace
sits under the gitignored `.scratch/` tree.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import sys
import unittest
import urllib.error
import urllib.parse
import uuid
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

FORGE_ROOT = Path(__file__).resolve().parents[1]
SKILL_SCRIPTS = FORGE_ROOT / "skills" / "paper-writing" / "scripts"
sys.path.insert(0, str(SKILL_SCRIPTS))
import paper_cli  # noqa: E402
import paper_resolve  # noqa: E402

CONFIG = {"paper_writing": {"contact": "", "roles": {
    "resolution": ["openalex", "crossref", "arxiv"], "full-text": [], "discovery": []}}}


def work(title: str, *, doi: str | None = None, abstract: str | None = None, year: int = 2020) -> dict:
    inverted = {word: [i] for i, word in enumerate(abstract.split())} if abstract else None
    return {"id": "https://openalex.org/W1", "title": title, "doi": doi and f"https://doi.org/{doi}",
            "publication_year": year, "abstract_inverted_index": inverted, "authorships": [],
            "primary_location": {"source": {"display_name": "Venue"}}}


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class Transport:
    """`routes` maps a URL fragment to bytes, an exception, or a 404 marker."""

    def __init__(self, routes: dict | None = None) -> None:
        self.routes = routes or {}
        self.urls: list[str] = []

    def open(self, request, timeout=None):
        url = request.full_url
        self.urls.append(url)
        for fragment, answer in self.routes.items():
            if fragment in url:
                if isinstance(answer, Exception):
                    raise answer
                return Response(answer)
        raise urllib.error.HTTPError(url, 404, "not found", {}, None)


def js(value) -> bytes:
    return json.dumps(value).encode("utf-8")


class ResolveReferencesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = FORGE_ROOT / ".scratch" / f".resolve-references-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.paper = self.root / "paper"
        self.paper.mkdir(parents=True)
        self.sidecar = self.paper / ".paper-writing" / "references.json"
        for patcher in (mock.patch.object(paper_resolve, "load_config", return_value=dict(CONFIG)),
                        mock.patch.object(paper_resolve, "_RETRY_DELAY_SECONDS", 0),
                        mock.patch.object(paper_resolve, "_REQUEST_PAUSE_SECONDS", 0)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def workspace(self, tex: str, bib: str) -> None:
        (self.paper / "main.tex").write_text(tex, encoding="utf-8")
        (self.paper / "refs.bib").write_text(bib, encoding="utf-8")

    def run_cli(self, transport: Transport, *extra: str) -> tuple[int, dict]:
        out = io.StringIO()
        with mock.patch.object(paper_resolve, "OPENER", transport), redirect_stdout(out):
            code = paper_cli.main(["resolve", "--references", "--paper", str(self.paper), *extra])
        return code, json.loads(out.getvalue())

    def records(self) -> dict:
        return json.loads(self.sidecar.read_text(encoding="utf-8"))["references"]

    def test_a_doi_resolves_through_openalex_with_its_abstract(self) -> None:
        self.workspace("\\cite{a}", "@article{a, title={T}, doi={10.1/A}}\n")
        transport = Transport({"api.openalex.org/works/https://doi.org/10.1/a":
                               js(work("T", doi="10.1/a", abstract="An abstract here"))})

        code, out = self.run_cli(transport)

        self.assertEqual((code, out["status"], out["command"]), (0, "ok", "resolve"))
        self.assertEqual((out["resolved"], out["with_abstract"], out["not_found"], out["unreachable"]), (1, 1, 0, 0))
        record = self.records()["a"]
        self.assertEqual((record["status"], record["resolver"], record["abstract"], record["year"], record["venue"]),
                         ("resolved", "openalex", "An abstract here", 2020, "Venue"))
        self.assertEqual(record["link"], "https://doi.org/10.1/a")
        self.assertEqual(set(record), {"status", "resolver", "identifier", "title", "abstract", "year",
                                       "venue", "link", "digest", "retrieved"})
        self.assertEqual(len(record["digest"]), 64)
        self.assertEqual(len(transport.urls), 1)

    def test_a_doi_openalex_does_not_know_falls_to_crossref(self) -> None:
        self.workspace("\\cite{a}", "@article{a, doi={10.1/a}}\n")
        crossref = js({"message": {"title": ["T"], "DOI": "10.1/a", "container-title": ["J"]}})

        code, _ = self.run_cli(Transport({"api.crossref.org": crossref}))

        record = self.records()["a"]
        self.assertEqual((code, record["status"], record["resolver"], record["abstract"]),
                         (0, "resolved", "crossref", None))

    def test_an_arxiv_identifier_resolves_through_arxiv(self) -> None:
        self.workspace("\\cite{a}", "@misc{a, eprint={1512.03385}, archivePrefix={arXiv}}\n")
        feed = (b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Deep</title>'
                b"<summary>Residual words.</summary></entry></feed>")

        self.run_cli(Transport({"export.arxiv.org": feed}))

        record = self.records()["a"]
        self.assertEqual((record["resolver"], record["abstract"], record["link"]),
                         ("arxiv", "Residual words.", "https://arxiv.org/abs/1512.03385"))

    def test_a_title_search_accepts_only_an_exact_normalized_title(self) -> None:
        self.workspace("\\cite{a,b}", "@misc{a, title={The {P}{\\'e}rez Signals}}\n@misc{b, title={Other Paper}}\n")
        search = js({"results": [work("Perez Signals in Depth", abstract="wrong one"),
                                 work("Pérez signals", doi="10.1/p", abstract="right one")]})
        transport = Transport({"search=The": search, "search=Other": js({"results": [work("Other Paper Two")]})})

        _, out = self.run_cli(transport)

        records = self.records()
        self.assertEqual((records["a"]["status"], records["a"]["abstract"], records["a"]["identifier"]),
                         ("resolved", "right one", "10.1/p"))
        self.assertEqual(records["b"]["status"], "not_found")
        self.assertIsNone(records["b"]["abstract"])
        self.assertEqual((out["resolved"], out["not_found"]), (1, 1))

    def test_among_equal_titles_the_bib_year_decides(self) -> None:
        self.workspace("\\cite{a}", "@misc{a, title={Same Title}, year={2021}}\n")
        search = js({"results": [work("Same Title", abstract="older", year=1999),
                                 work("Same Title", abstract="newer", year=2021)]})

        self.run_cli(Transport({"search=Same": search}))

        self.assertEqual(self.records()["a"]["abstract"], "newer")

    def test_a_cited_key_without_a_bib_entry_is_not_found_with_no_request(self) -> None:
        self.workspace("\\cite{ghost}", "")
        transport = Transport()

        code, out = self.run_cli(transport)

        self.assertEqual((code, out["not_found"], transport.urls), (0, 1, []))
        self.assertEqual(self.records()["ghost"]["status"], "not_found")

    def test_offline_records_unreachable_and_stops_asking(self) -> None:
        keys = [f"k{i}" for i in range(8)]
        self.workspace("\\cite{" + ",".join(keys) + "}",
                       "".join(f"@misc{{{k}, doi={{10.1/{k}}}}}\n" for k in keys))
        transport = Transport({"": urllib.error.URLError("offline")})

        code, out = self.run_cli(transport)

        self.assertEqual((code, out["status"], out["unreachable"], out["resolved"]), (0, "ok", 8, 0))
        self.assertEqual({r["status"] for r in self.records().values()}, {"unreachable"})
        self.assertLess(len(transport.urls), 8 * 4)

    def test_a_malformed_answer_is_unreachable_and_never_a_crash(self) -> None:
        self.workspace("\\cite{a}", "@misc{a, doi={10.1/a}}\n")

        code, out = self.run_cli(Transport({"": b"<html>not json"}))

        self.assertEqual((code, out["unreachable"]), (0, 1))

    def test_a_rerun_reuses_resolved_and_retries_the_rest(self) -> None:
        self.workspace("\\cite{a,b}", "@misc{a, doi={10.1/a}}\n@misc{b, doi={10.1/b}}\n")
        found = js(work("T", doi="10.1/a", abstract="Words"))
        self.run_cli(Transport({"doi.org/10.1/a": found, "10.1%2Fb": urllib.error.URLError("x"),
                                "doi.org/10.1/b": urllib.error.URLError("x")}))
        self.assertEqual(self.records()["b"]["status"], "unreachable")
        first = self.records()["a"]

        transport = Transport({"doi.org/10.1/b": js(work("U", doi="10.1/b", abstract="Later"))})
        _, out = self.run_cli(transport)

        records = self.records()
        self.assertEqual(records["a"], first)
        self.assertEqual((records["b"]["status"], out["reused"]), ("resolved", 1))
        self.assertFalse([u for u in transport.urls if "10.1/a" in u])

    def test_a_rerun_with_nothing_to_do_is_byte_identical(self) -> None:
        self.workspace("\\cite{b,a}", "@misc{a, doi={10.1/a}}\n@misc{b, doi={10.1/b}}\n")
        self.run_cli(Transport({"10.1/": js(work("T", abstract="Words"))}))
        before = self.sidecar.read_bytes()
        self.assertEqual(list(self.records()), ["a", "b"])

        transport = Transport()
        self.run_cli(transport)

        self.assertEqual(self.sidecar.read_bytes(), before)
        self.assertEqual(transport.urls, [])

    def test_force_asks_again_and_a_failure_never_loses_a_resolved_record(self) -> None:
        self.workspace("\\cite{a}", "@misc{a, doi={10.1/a}}\n")
        self.run_cli(Transport({"10.1/a": js(work("T", abstract="First"))}))

        self.run_cli(Transport({"10.1/a": js(work("T", abstract="Second"))}), "--force")
        self.assertEqual(self.records()["a"]["abstract"], "Second")

        self.run_cli(Transport({"": urllib.error.URLError("offline")}), "--force")
        self.assertEqual((self.records()["a"]["status"], self.records()["a"]["abstract"]), ("resolved", "Second"))

    def test_a_manuscript_with_unknown_cite_commands_falls_back_to_the_bibliography(self) -> None:
        self.workspace("\\parencite{a}", "@misc{a, doi={10.1/a}}\n")

        self.run_cli(Transport({"10.1/a": js(work("T", abstract="Words"))}))

        self.assertEqual(list(self.records()), ["a"])

    def test_an_emptied_role_refuses_and_writes_nothing(self) -> None:
        self.workspace("\\cite{a}", "@misc{a, doi={10.1/a}}\n")
        empty = {"paper_writing": {"roles": {"resolution": []}}}
        transport = Transport()

        with mock.patch.object(paper_resolve, "load_config", return_value=empty):
            code, out = self.run_cli(transport)

        self.assertEqual((code, out["status"], out["code"]), (2, "refused", "RESOLVER_ROLE_EMPTY"))
        self.assertEqual(transport.urls, [])
        self.assertFalse(self.sidecar.exists())

    def test_a_role_without_openalex_never_reaches_it(self) -> None:
        self.workspace("\\cite{a}", "@misc{a, title={T}, doi={10.1/a}}\n")
        only = {"paper_writing": {"roles": {"resolution": ["crossref"]}}}
        transport = Transport({"api.crossref.org": js({"message": {"title": ["T"], "DOI": "10.1/a"}})})

        with mock.patch.object(paper_resolve, "load_config", return_value=only):
            self.run_cli(transport)

        self.assertFalse([u for u in transport.urls if "openalex" in u])
        self.assertEqual(self.records()["a"]["resolver"], "crossref")

    def test_requests_pause_between_each_other(self) -> None:
        self.workspace("\\cite{a,b}", "@misc{a, doi={10.1/a}}\n@misc{b, doi={10.1/b}}\n")
        with mock.patch.object(paper_resolve.time, "sleep") as sleep, \
                mock.patch.object(paper_resolve, "_REQUEST_PAUSE_SECONDS", 0.25):
            self.run_cli(Transport({"10.1/": js(work("T", abstract="Words"))}))
        self.assertEqual(sleep.call_count, 2)
        sleep.assert_called_with(0.25)


class ResolveArgumentTests(unittest.TestCase):
    def fails(self, *argv: str) -> None:
        stderr = io.StringIO()
        with mock.patch("sys.stderr", stderr), self.assertRaises(SystemExit) as raised:
            paper_cli.main(["resolve", *argv])
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("error:", stderr.getvalue())

    def test_one_identifier_still_needs_both_flags(self) -> None:
        self.fails("--identifier", "10.1/a")
        self.fails("--resolver", "crossref")
        self.fails()

    def test_references_takes_no_identifier_and_force_needs_references(self) -> None:
        self.fails("--references", "--identifier", "10.1/a")
        self.fails("--references", "--cache-dir", ".scratch/x")
        self.fails("--identifier", "10.1/a", "--resolver", "crossref", "--force")

    def test_one_identifier_behaves_as_before(self) -> None:
        root = FORGE_ROOT / ".scratch" / f".resolve-one-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        (root / "paper").mkdir(parents=True)
        transport = Transport({"api.crossref.org": js({"message": {"title": ["T"], "DOI": "10.1/a"}})})
        out = io.StringIO()
        with mock.patch.object(paper_resolve, "load_config", return_value=dict(CONFIG)), \
                mock.patch.object(paper_resolve, "OPENER", transport), redirect_stdout(out):
            code = paper_cli.main(["resolve", "--identifier", "10.1/a", "--resolver", "crossref",
                                   "--paper", str(root / "paper")])
        body = json.loads(out.getvalue())
        self.assertEqual((code, body["status"], body["title"]), (0, "ok", "T"))
        self.assertEqual(len(list((root / "paper" / ".paper-writing" / "metadata").glob("*.json"))), 1)
        self.assertFalse((root / "paper" / ".paper-writing" / "references.json").exists())


if __name__ == "__main__":
    unittest.main()
