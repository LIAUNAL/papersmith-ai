"""`skills/systematic-review/scripts/review_cli.py`: PRISMA 2020 records.

Runs the CLI as a subprocess against a fake OpenAlex / Crossref / Europe PMC
server, the way an agent runs it in a review workspace.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "skills" / "systematic-review" / "scripts" / "review_cli.py"

PROTOCOL = {
    "schema": 1,
    "title": "Graph neural networks in drug discovery: a systematic review",
    "objective": "Map how graph neural networks are evaluated for molecular property prediction.",
    "review_type": "systematic review",
    "guidelines": ["PRISMA 2020"],
    "research_questions": [
        {"id": "RQ1", "question": "Which architectures are used?",
         "picoc": {"population": "molecules", "intervention": "GNN", "comparison": "", "outcomes": "AUC",
                   "context": "drug discovery"}},
    ],
    "criteria": {
        "inclusion": [{"id": "I1", "text": "Peer-reviewed study evaluating a GNN", "reason": "scope"}],
        "exclusion": [{"id": "E1", "text": "No empirical evaluation", "reason": "no evidence"},
                      {"id": "E2", "text": "Not about molecules", "reason": "scope"}],
    },
    "sources": [{"name": "openalex", "query": "graph neural network drug discovery"},
                {"name": "crossref", "query": "graph neural network molecule"},
                {"name": "europepmc", "query": "graph neural network"}],
    "date_range": {"from": "2018-01-01", "to": "2025-12-31"},
    "languages": ["en"],
    "publication_types": ["journal article"],
    "screening": {"reviewers": 2},
    "appraisal": {"tool": "Kitchenham", "questions": [{"id": "QA1", "text": "Aims clear?"},
                                                      {"id": "QA2", "text": "Data described?"}],
                  "scale": {"yes": 1, "partly": 0.5, "no": 0}, "threshold": 1},
    "extraction": {"fields": [{"id": "architecture", "description": "GNN family", "type": "category",
                               "options": ["GCN", "GAT", "MPNN"]},
                              {"id": "auc", "description": "best AUC", "type": "number"}]},
    "amendments": [],
}


def _openalex_work(i: int, doi: str | None, title: str, year: int, keywords=()) -> dict:
    return {"id": f"https://openalex.org/W{i}", "display_name": title, "publication_year": year,
            "doi": f"https://doi.org/{doi}" if doi else None, "type": "article",
            "abstract_inverted_index": {"Graph": [0], "networks": [1]},
            "authorships": [{"author": {"display_name": "Ada Lovelace"}}],
            "primary_location": {"source": {"display_name": "J. Chem. Inf."}},
            "keywords": [{"display_name": k} for k in keywords]}


class FakeApis:
    def __init__(self):
        self.requests: list[tuple[str, dict]] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                parsed = urlparse(self.path)
                query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
                outer.requests.append((parsed.path, query))
                body = outer.answer(parsed.path, query)
                data = json.dumps(body).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def close(self):
        self.server.shutdown()
        self.server.server_close()

    def answer(self, path: str, query: dict) -> dict:
        if path.startswith("/openalex/works"):
            if "type:review" in query.get("filter", ""):
                return {"meta": {"count": 1, "next_cursor": None},
                        "results": [_openalex_work(9, "10.1/review", "GNNs: a review", 2022)]}
            if query.get("cursor") == "*":
                return {"meta": {"count": 3, "next_cursor": "page2"},
                        "results": [_openalex_work(1, "10.1/a", "Message passing for molecules", 2020, ("gnn", "toxicity")),
                                    _openalex_work(2, "10.1/b", "Attention on molecular graphs", 2021, ("gnn", "attention"))]}
            return {"meta": {"count": 3, "next_cursor": None},
                    "results": [_openalex_work(3, None, "Graph kernels revisited", 2019, ("kernels",))]}
        if path.startswith("/crossref/works"):
            return {"message": {"total-results": 5, "next-cursor": None, "items": [
                {"DOI": "10.1/A", "title": ["Message passing for molecules"], "issued": {"date-parts": [[2020]]},
                 "container-title": ["J. Chem. Inf."], "abstract": "<jats:p>Graph <b>nets</b></jats:p>",
                 "author": [{"given": "Ada", "family": "Lovelace"}], "type": "journal-article"}]}}
        if path.startswith("/europepmc/search"):
            return {"hitCount": 1, "nextCursorMark": "*", "resultList": {"result": [
                {"id": "123", "source": "MED", "title": "Graph kernels revisited.", "pubYear": "2019",
                 "doi": None, "abstractText": "Kernels", "authorString": "Doe J, Roe R.",
                 "journalInfo": {"journal": {"title": "Bioinf"}}, "keywordList": {"keyword": ["kernels"]}}]}}
        return {}


class ReviewCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="systematic-review-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.root = self.tmp / "ws"
        (self.root / "review").mkdir(parents=True)
        self.api = FakeApis()
        self.addCleanup(self.api.close)

    def run_cli(self, *args: str) -> tuple[int, dict]:
        env = {k: v for k, v in os.environ.items() if not k.startswith(("PAPERSMITH_", "OPENALEX_"))}
        env.update({"PAPERSMITH_OPENALEX_URL": f"{self.api.base}/openalex",
                    "PAPERSMITH_CROSSREF_URL": f"{self.api.base}/crossref",
                    "PAPERSMITH_EUROPEPMC_URL": f"{self.api.base}/europepmc",
                    "PAPERSMITH_HTTP_TIMEOUT": "10"})
        completed = subprocess.run([sys.executable, str(CLI), "--root", str(self.root), *args],
                                   capture_output=True, text=True, env=env, timeout=60)
        return completed.returncode, json.loads(completed.stdout)

    def ok(self, *args: str) -> dict:
        code, payload = self.run_cli(*args)
        self.assertEqual(code, 0, payload)
        self.assertTrue(payload["ok"], payload)
        return payload

    def refused(self, error: str, *args: str) -> dict:
        code, payload = self.run_cli(*args)
        self.assertEqual((code, payload.get("error")), (2, error), payload)
        return payload

    def write_protocol(self, protocol=None) -> None:
        (self.root / "review" / "protocol.json").write_text(json.dumps(protocol or PROTOCOL), encoding="utf-8")

    def approved(self) -> None:
        self.write_protocol()
        self.ok("protocol", "approve", "--by", "Operator")

    def jsonl(self, name: str) -> list[dict]:
        path = self.root / "review" / name
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class ProtocolTests(ReviewCase):
    def test_template_lists_its_placeholders_and_a_filled_protocol_checks_clean(self):
        self.ok("init")
        self.refused("PROTOCOL_EXISTS", "init")
        code, payload = self.run_cli("protocol", "check")
        self.assertEqual(code, 0)
        self.assertFalse(payload["ok"])
        self.assertTrue(any("placeholder" in p for p in payload["problems"]))
        self.write_protocol()
        self.assertEqual(self.ok("protocol", "check")["problems"], [])

    def test_no_search_before_approval_and_an_edit_must_be_an_amendment(self):
        self.write_protocol()
        self.refused("PROTOCOL_NOT_APPROVED", "search", "--source", "openalex")
        self.refused("APPROVER_MISSING", "protocol", "approve")
        self.ok("protocol", "approve", "--by", "Operator")
        self.refused("PROTOCOL_ALREADY_APPROVED", "protocol", "approve", "--by", "Operator")
        self.refused("PROTOCOL_UNCHANGED", "protocol", "amend", "--by", "Operator", "--reason", "x")
        changed = json.loads(json.dumps(PROTOCOL))
        changed["date_range"]["to"] = "2026-06-30"
        self.write_protocol(changed)
        self.refused("PROTOCOL_CHANGED", "search", "--source", "openalex")
        self.refused("AMENDMENT_REASON_MISSING", "protocol", "amend", "--by", "Operator")
        lock = self.ok("protocol", "amend", "--by", "Operator", "--reason", "extend to 2026")["approval"]
        self.assertEqual(lock["amendments"][0]["reason"], "extend to 2026")
        self.ok("search", "--source", "openalex")

    def test_a_source_the_protocol_does_not_name_is_refused(self):
        narrow = json.loads(json.dumps(PROTOCOL))
        narrow["sources"] = [narrow["sources"][0]]
        self.write_protocol(narrow)
        self.ok("protocol", "approve", "--by", "Operator")
        self.refused("SOURCE_NOT_IN_PROTOCOL", "search", "--source", "crossref")

    def test_an_invalid_protocol_is_refused_with_its_problems(self):
        broken = json.loads(json.dumps(PROTOCOL))
        broken["criteria"]["exclusion"] = [{"id": "X1", "text": "bad id"}]
        broken["sources"] = []
        self.write_protocol(broken)
        payload = self.refused("PROTOCOL_INVALID", "protocol", "approve", "--by", "Operator")
        self.assertIn("is not E<n>", payload["message"])
        self.assertIn("sources is empty", payload["message"])


class IdentificationTests(ReviewCase):
    def test_each_source_is_queried_with_the_protocol_query_and_logged(self):
        self.approved()
        openalex = self.ok("search", "--source", "openalex")["search"]
        self.assertEqual((openalex["source"], openalex["total"], openalex["retrieved"]), ("openalex", 3, 3))
        self.assertEqual(openalex["query"], "graph neural network drug discovery")
        first = next(q for p, q in self.api.requests if p.startswith("/openalex"))
        self.assertEqual(first["search"], "graph neural network drug discovery")
        self.assertEqual(first["filter"], "from_publication_date:2018-01-01,to_publication_date:2025-12-31")
        crossref = self.ok("search", "--source", "crossref")
        self.assertEqual(crossref["search"]["total"], 5)
        self.assertTrue(crossref["notes"])  # 5 reported, 1 retrieved
        self.ok("search", "--source", "europepmc")
        europe = next(q for p, q in self.api.requests if p.startswith("/europepmc"))
        self.assertEqual(europe["query"], "(graph neural network) AND FIRST_PDATE:[2018-01-01 TO 2025-12-31]")
        records = self.jsonl("records.jsonl")
        self.assertEqual([r["id"] for r in records], ["R0001", "R0002", "R0003", "R0004", "R0005"])
        self.assertEqual(records[0]["doi"], "10.1/a")
        self.assertEqual(records[0]["abstract"], "Graph networks")
        self.assertEqual(records[3]["abstract"], "Graph nets")
        self.assertEqual([s["id"] for s in self.jsonl("searches.jsonl")], ["S1", "S2", "S3"])

    def test_imports_and_deduplication_by_doi_then_title(self):
        self.approved()
        self.ok("search", "--source", "openalex")
        ris = self.tmp / "scopus.ris"
        ris.write_text("TY  - JOUR\nTI  - Message passing for molecules\nAU  - Lovelace, A.\nPY  - 2020\n"
                       "DO  - https://doi.org/10.1/A\nKW  - gnn\nER  - \n"
                       "TY  - JOUR\nTI  - A brand new study\nPY  - 2023\nT2  - Nature\nER  - \n", encoding="utf-8")
        logged = self.ok("import", "--file", str(ris), "--source", "scopus", "--query", "TITLE-ABS(gnn)")["search"]
        self.assertEqual((logged["method"], logged["retrieved"]), ("import:ris", 2))
        bib = self.tmp / "wos.bib"
        bib.write_text("@article{k1, title = {Graph Kernels Revisited}, year = 2019, journal = {Bioinf},\n"
                       " author = {Doe, J. and Roe, R.}, keywords = {kernels; svm}}\n", encoding="utf-8")
        self.ok("import", "--file", str(bib), "--source", "wos", "--query", "TS=(graph kernel)")
        empty = self.tmp / "empty.ris"
        empty.write_text("nothing here", encoding="utf-8")
        self.refused("IMPORT_EMPTY", "import", "--file", str(empty), "--source", "x", "--query", "q")
        result = self.ok("dedupe")
        self.assertEqual((result["records"], result["duplicates_marked"], result["unique"]), (6, 2, 4))
        by_id = {r["id"]: r for r in self.jsonl("records.jsonl")}
        self.assertEqual(by_id["R0004"]["duplicate_of"], "R0001")  # same DOI, different case and prefix
        self.assertEqual(by_id["R0006"]["duplicate_of"], "R0003")  # same title and year, no DOI
        self.assertEqual(self.ok("dedupe")["duplicates_marked"], 0)

    def test_scope_asks_openalex_for_reviews_only(self):
        result = self.ok("scope", "--query", "graph neural networks molecules")
        self.assertEqual(result["reviews"][0]["title"], "GNNs: a review")
        self.assertIn("type:review", self.api.requests[-1][1]["filter"])
        self.assertTrue((self.root / "review" / "scope.json").is_file())
        self.refused("QUERY_TOO_SHORT", "scope", "--query", "gnn")


class ScreeningAndSynthesisTests(ReviewCase):
    def setUp(self):
        super().setUp()
        self.approved()
        self.ok("search", "--source", "openalex")  # R0001-R0003
        self.ok("search", "--source", "europepmc")  # R0004 duplicate of R0003
        self.ok("dedupe")

    def screen(self, stage, record, reviewer, decision, *extra):
        return self.ok("screen", "--stage", stage, "--record", record, "--reviewer", reviewer,
                       "--decision", decision, *extra)

    def test_two_reviewers_conflicts_final_and_kappa(self):
        self.assertEqual(self.ok("queue", "--stage", "ta", "--reviewer", "agent")["pending"], 3)
        self.screen("ta", "R0001", "agent", "include")
        partial = self.screen("ta", "R0001", "operator", "include")
        self.assertEqual(partial["outcome"], {"decision": "include", "state": "agreed", "reason": None})
        self.screen("ta", "R0002", "agent", "include")
        self.screen("ta", "R0002", "operator", "exclude", "--reason", "E2")
        self.screen("ta", "R0003", "agent", "exclude", "--reason", "E1")
        self.screen("ta", "R0003", "operator", "exclude")
        self.assertEqual([c["record_id"] for c in self.ok("conflicts", "--stage", "ta")["conflicts"]], ["R0002"])
        kappa = self.ok("kappa", "--stage", "ta")
        self.assertEqual((kappa["records"], kappa["agreement"], kappa["kappa"]), (3, 0.6667, 0.4))
        self.screen("ta", "R0002", "operator", "include", "--final")
        self.assertEqual(self.ok("conflicts", "--stage", "ta")["conflicts"], [])
        self.refused("RECORD_NOT_ELIGIBLE", "screen", "--stage", "ta", "--record", "R0004", "--reviewer", "a",
                     "--decision", "include")
        self.refused("RECORD_NOT_ELIGIBLE", "screen", "--stage", "ft", "--record", "R0003", "--reviewer", "a",
                     "--decision", "include")
        self.refused("DECISION_INVALID", "screen", "--stage", "ta", "--record", "R0001", "--reviewer", "a",
                     "--decision", "maybe")
        self.refused("REASON_MISSING", "screen", "--stage", "ft", "--record", "R0001", "--reviewer", "a",
                     "--decision", "exclude")
        self.refused("REASON_UNKNOWN", "screen", "--stage", "ft", "--record", "R0001", "--reviewer", "a",
                     "--decision", "exclude", "--reason", "E9")
        self.refused("REASON_UNEXPECTED", "screen", "--stage", "ft", "--record", "R0001", "--reviewer", "a",
                     "--decision", "include", "--reason", "E1")

    def test_flow_counts_appraisal_extraction_and_checklist(self):
        for record in ("R0001", "R0002", "R0003"):
            decision = "exclude" if record == "R0003" else "include"
            extra = ("--reason", "E2") if decision == "exclude" else ()
            for reviewer in ("agent", "operator"):
                self.screen("ta", record, reviewer, decision, *extra)
        self.screen("ft", "R0001", "agent", "include")
        self.screen("ft", "R0001", "operator", "include")
        self.screen("ft", "R0002", "agent", "exclude", "--reason", "E1")
        self.screen("ft", "R0002", "operator", "exclude", "--reason", "E1")
        counts = self.ok("prisma")["counts"]
        self.assertEqual(counts["identification"], {"databases": {"europepmc": 1, "openalex": 3}, "records": 4,
                                                    "duplicates_removed": 1})
        self.assertEqual(counts["screening"], {"records_screened": 3, "records_excluded": 1, "records_pending": 0,
                                               "reports_sought": 2, "reports_not_retrieved": 0,
                                               "reports_assessed": 2, "reports_excluded": {"E1": 1},
                                               "reports_pending": 0})
        self.assertEqual(counts["included"], {"studies": 1})
        svg = (self.root / "paper" / "Figures" / "prisma-flow.svg")
        self.ok("flow")
        text = svg.read_text(encoding="utf-8")
        for fragment in ("Databases (n = 4)", "Duplicate records removed (n = 1)", "Records screened (n = 3)",
                         "E1: No empirical evaluation (n = 1)", "Studies included in review (n = 1)"):
            self.assertIn(fragment, text)
        self.refused("RECORD_NOT_INCLUDED", "appraise", "--record", "R0002", "--reviewer", "a",
                     "--answers", '{"QA1": "yes", "QA2": "yes"}')
        self.refused("ANSWERS_INCOMPLETE", "appraise", "--record", "R0001", "--reviewer", "a",
                     "--answers", '{"QA1": "yes"}')
        self.refused("ANSWER_UNKNOWN", "appraise", "--record", "R0001", "--reviewer", "a",
                     "--answers", '{"QA1": "yes", "QA2": "maybe"}')
        appraisal = self.ok("appraise", "--record", "R0001", "--reviewer", "a",
                            "--answers", '{"QA1": "yes", "QA2": "partly"}')
        self.assertEqual((appraisal["recorded"]["score"], appraisal["below_threshold"]), (1.5, False))
        self.refused("DATA_INVALID", "extract", "--record", "R0001", "--extractor", "a",
                     "--data", '{"architecture": {"value": "CNN", "quote": "we use a CNN"}}')
        self.refused("DATA_INVALID", "extract", "--record", "R0001", "--extractor", "a",
                     "--data", '{"auc": {"value": 0.9}}')
        self.refused("FIELD_UNKNOWN", "extract", "--record", "R0001", "--extractor", "a",
                     "--data", '{"dataset": {"value": "x", "quote": "y"}}')
        extracted = self.ok("extract", "--record", "R0001", "--extractor", "a",
                            "--data", '{"architecture": {"value": "MPNN", "quote": "a message passing network"}}')
        self.assertEqual(extracted["fields_missing"], ["auc"])
        biblio = self.ok("biblio")
        self.assertEqual((biblio["basis"], biblio["count"], biblio["per_year"]), ("included studies", 1, {"2020": 1}))
        cooc = json.loads((self.root / "review" / "biblio.json").read_text())["keyword_cooccurrence"]
        self.assertEqual(cooc, [{"a": "gnn", "b": "toxicity", "count": 1}])
        code, checklist = self.run_cli("checklist")
        self.assertEqual(code, 0)
        self.assertEqual(len(checklist["items"]), 27)
        # Every record is on file, but no paper exists: each item still owes its text.
        self.assertFalse(checklist["ok"])
        self.assertEqual(checklist["owed"], list(range(1, 28)))
        self.assertTrue(checklist["notes"])
        self.assertTrue(all(not m.startswith("record:") for item in checklist["items"] for m in item["missing"]))

    def test_checklist_names_the_records_owed(self):
        code, payload = self.run_cli("checklist")
        self.assertEqual(code, 0)
        self.assertFalse(payload["ok"])
        records = {item["item"]: [m for m in item["missing"] if m.startswith("record:")] for item in payload["items"]}
        self.assertEqual(sorted(n for n, missing in records.items() if missing), [8, 9, 11, 16, 17, 18, 19])
        self.assertEqual(records[8], ["record:screening"])
        item24 = payload["items"][23]
        self.assertIn("declaration:review-registration", item24["missing"])
        self.assertIn("text:methods.m-protocol-registration", item24["missing"])

    def test_review_records_follow_the_umask_like_the_appended_ones(self):
        mode = (self.root / "review" / "protocol.lock.json").stat().st_mode & 0o777
        umask = os.umask(0)
        os.umask(umask)
        self.assertEqual(mode, 0o666 & ~umask)


if __name__ == "__main__":
    unittest.main()
