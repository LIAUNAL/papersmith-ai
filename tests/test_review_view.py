"""The Review tab's data (paper-type-lines S6, T6b).

`GET /api/review` answers, for a review workspace, one JSON object with the
protocol and its registration, the search log, the screening progress
(pending per reviewer, conflicts, kappa), the PRISMA flow, the extraction
table, the risk of bias (the appraisal scores against the protocol's
threshold) and the sign-offs, all read through the workspace's own
`review_cli.py`. A malformed or absent record turns its section unavailable
with the reason, never the response into a 500. `GET /api/review/checklist`
serves the slow 27-item PRISMA checklist on demand only. An experimental
workspace answers 409 on both routes and keeps its `/api/status`.
"""

from __future__ import annotations

import contextlib
import importlib.util
import inspect
import io
import json
import re
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

import tests.test_experimental_line_characterization as characterization
from papersmith.core import init as init_module
from skills._core.command_center import review_board, review_view, server

REPO = Path(__file__).resolve().parents[1]
PAGE = (REPO / "skills/_core/command_center/static/index.html").read_text(encoding="utf-8")
SECTIONS = ("summary", "protocol", "searches", "screening", "prisma", "extraction", "appraisal", "signoffs")

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
        {"id": "RQ2", "question": "Which datasets & benchmarks are reused?", "picoc": {}},
    ],
    "criteria": {
        "inclusion": [{"id": "I1", "text": "Peer-reviewed study evaluating a GNN", "reason": "scope"}],
        "exclusion": [{"id": "E1", "text": "No empirical evaluation", "reason": "no evidence"}],
    },
    "sources": [{"name": "openalex", "query": "graph neural network drug discovery"},
                {"name": "crossref", "query": "graph neural network AND drug"}],
    "date_range": {"from": "2018-01-01", "to": "2025-12-31"},
    "languages": ["en"],
    "publication_types": ["journal article"],
    "screening": {"reviewers": 2},
    "appraisal": {"tool": "Kitchenham", "questions": [{"id": "QA1", "text": "Aims clear?"},
                                                     {"id": "QA2", "text": "Validation described?"}],
                  "scale": {"yes": 1, "partly": 0.5, "no": 0}, "threshold": 1.5},
    "extraction": {"fields": [{"id": "architecture", "description": "GNN family", "type": "text"},
                              {"id": "datasets", "description": "Benchmarks used", "type": "list"}]},
    "amendments": [],
}


def workspace(case: unittest.TestCase, kind: str = "review") -> Path:
    holder = tempfile.TemporaryDirectory(prefix="review-view-", ignore_cleanup_errors=True)
    case.addCleanup(holder.cleanup)
    root = Path(holder.name).resolve() / "ws"
    init_module.initialize(root, tools=("claude",), run_npm=False, run_env=False, kind=kind)
    return root


def cli(root: Path, *args: str) -> dict:
    """Run the workspace's own review_cli.py, as the skill does."""
    path = root / "skills" / "systematic-review" / "scripts" / "review_cli.py"
    spec = importlib.util.spec_from_file_location("review_cli_view_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = module.main(["--root", str(root), *args])
    payload = json.loads(out.getvalue())
    assert code == 0, payload
    return payload


def approve(root: Path) -> None:
    (root / "review" / "protocol.json").write_text(json.dumps(PROTOCOL), encoding="utf-8")
    cli(root, "protocol", "approve", "--by", "Operator")


def identify(root: Path) -> None:
    """Three identified records (one a duplicate) and their search, as `search` and `dedupe` leave them."""
    titles = ((1, "Message passing for molecules", None), (2, "Graph kernels revisited", None),
              (3, "Message passing for molecules", "R0001"))
    rows = [{"id": f"R000{i}", "search_id": "S1", "source": "openalex", "title": title, "year": 2021,
             "venue": "J. Chem. Inf.", "doi": f"10.1/{i}", "abstract": "Graph networks", "authors": [],
             "keywords": [], "type": "article", "duplicate_of": duplicate}
            for i, title, duplicate in titles]
    (root / "review" / "records.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    search = {"id": "S1", "source": "openalex", "query": "graph neural network drug discovery",
              "method": "api", "run_at": "2026-01-01T00:00:00Z", "total": 120, "retrieved": 3}
    (root / "review" / "searches.jsonl").write_text(json.dumps(search) + "\n", encoding="utf-8")


def screen(root: Path, stage: str, record: str, decisions: dict[str, str]) -> None:
    for reviewer, decision in decisions.items():
        extra = ("--reason", "E1") if decision == "exclude" and stage == "ft" else ()
        cli(root, "screen", "--stage", stage, "--record", record, "--reviewer", reviewer, "--decision", decision,
            *extra)


def build_review(root: Path) -> None:
    """A review half way: protocol approved, one study included and appraised
    below the threshold, extracted with quotes, one title/abstract conflict,
    PRISMA counted and its flow drawn."""
    approve(root)
    identify(root)
    screen(root, "ta", "R0001", {"agent": "include", "operator": "include"})
    screen(root, "ta", "R0002", {"agent": "include", "operator": "exclude"})
    screen(root, "ft", "R0001", {"agent": "include", "operator": "include"})
    cli(root, "appraise", "--record", "R0001", "--reviewer", "operator",
        "--answers", json.dumps({"QA1": "yes", "QA2": "no"}))
    cli(root, "extract", "--record", "R0001", "--extractor", "agent", "--data", json.dumps({
        "architecture": {"value": "GCN <b>", "quote": "We use a <b>graph</b> convolution", "page": 3},
        "datasets": {"value": ["Tox21", "QM9"], "page": 5}}))
    cli(root, "flow")


class ReviewViewCase(unittest.TestCase):
    def get(self, root: Path, route: str = "/api/review", lang: str = "") -> dict:
        response = TestClient(server.create_app(root)).get(route + (f"?lang={lang}" if lang else ""))
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def section(self, view: dict, name: str) -> dict:
        part = view[name]
        self.assertTrue(part["available"], part)
        return part


class ContractTests(ReviewViewCase):
    def test_an_empty_review_workspace_answers_every_section(self) -> None:
        view = self.get(workspace(self))
        self.assertEqual(view["paper_kind"], "review")
        self.assertIsNone(view["cli_warning"])
        self.assertTrue(set(SECTIONS) <= set(view), sorted(view))
        self.assertNotIn("checklist", view)
        self.assertFalse(self.section(view, "protocol")["present"])
        self.assertEqual(self.section(view, "protocol")["approval"]["state"], "absent")
        self.assertEqual(self.section(view, "searches")["rows"], [])
        self.assertIsNone(self.section(view, "prisma")["counts"])
        self.assertFalse(self.section(view, "prisma")["flow"]["exists"])

    def test_the_view_carries_no_server_label_to_translate(self) -> None:
        root = workspace(self)
        build_review(root)
        self.assertEqual(self.get(root, lang="es"), self.get(root))


class ProtocolTests(ReviewViewCase):
    def test_questions_criteria_sources_and_approval(self) -> None:
        root = workspace(self)
        (root / "review" / "protocol.json").write_text(json.dumps(PROTOCOL), encoding="utf-8")
        protocol = self.section(self.get(root), "protocol")
        self.assertTrue(protocol["present"])
        self.assertTrue(protocol["valid"])
        self.assertEqual(protocol["problems"], [])
        self.assertEqual(protocol["title"], PROTOCOL["title"])
        self.assertEqual([q["id"] for q in protocol["research_questions"]], ["RQ1", "RQ2"])
        self.assertEqual(protocol["research_questions"][0]["picoc"]["outcomes"], "AUC")
        self.assertEqual(protocol["criteria"]["exclusion"], [{"id": "E1", "text": "No empirical evaluation",
                                                              "reason": "no evidence"}])
        self.assertEqual([s["name"] for s in protocol["sources"]], ["openalex", "crossref"])
        self.assertEqual(protocol["date_range"], {"from": "2018-01-01", "to": "2025-12-31"})
        self.assertEqual(protocol["reviewers"], 2)
        self.assertEqual(protocol["approval"]["state"], "absent")
        self.assertEqual(protocol["registration"], {"declaration": "review-registration", "checklist_item": 24})

        cli(root, "protocol", "approve", "--by", "Operator")
        approval = self.section(self.get(root), "protocol")["approval"]
        self.assertEqual((approval["state"], approval["by"], approval["amendments"]), ("approved", "Operator", []))

        (root / "review" / "protocol.json").write_text(json.dumps({**PROTOCOL, "languages": ["en", "es"]}),
                                                       encoding="utf-8")
        self.assertEqual(self.section(self.get(root), "protocol")["approval"]["state"], "changed")
        cli(root, "protocol", "amend", "--by", "Operator", "--reason", "Spanish studies are eligible")
        approval = self.section(self.get(root), "protocol")["approval"]
        self.assertEqual(approval["state"], "approved")
        self.assertEqual([(a["by"], a["reason"]) for a in approval["amendments"]],
                         [("Operator", "Spanish studies are eligible")])

    def test_an_invalid_protocol_lists_its_problems(self) -> None:
        root = workspace(self)
        cli(root, "init")
        protocol = self.section(self.get(root), "protocol")
        self.assertFalse(protocol["valid"])
        self.assertIn("title is missing or still a placeholder", protocol["problems"])


class SearchLogTests(ReviewViewCase):
    def test_every_logged_search_and_the_sources_not_searched_yet(self) -> None:
        root = workspace(self)
        approve(root)
        identify(root)
        searches = self.section(self.get(root), "searches")
        self.assertEqual(searches["rows"], [{"id": "S1", "source": "openalex",
                                             "query": "graph neural network drug discovery", "method": "api",
                                             "run_at": "2026-01-01T00:00:00Z", "total": 120, "retrieved": 3,
                                             "file": None}])
        self.assertEqual((searches["records"], searches["duplicates"], searches["unique"]), (3, 1, 2))
        self.assertEqual(searches["not_searched"], ["crossref"])


class ScreeningTests(ReviewViewCase):
    def test_totals_pending_per_reviewer_conflicts_and_kappa(self) -> None:
        root = workspace(self)
        approve(root)
        identify(root)
        screen(root, "ta", "R0001", {"agent": "include", "operator": "include"})
        screen(root, "ta", "R0002", {"agent": "include", "operator": "exclude"})
        screening = self.section(self.get(root), "screening")
        self.assertEqual(screening["required_reviewers"], 2)
        ta, ft = screening["stages"]
        self.assertEqual((ta["stage"], ft["stage"]), ("ta", "ft"))
        self.assertEqual((ta["eligible"], ta["decided"], ta["agreed"], ta["conflict_count"], ta["undecided"]),
                         (2, 1, 1, 1, 0))
        self.assertEqual(ta["decisions"], {"include": 1})
        self.assertEqual(ta["conflicts"], [{"record_id": "R0002", "title": "Graph kernels revisited", "votes": {
            "agent": {"decision": "include", "reason": None, "note": ""},
            "operator": {"decision": "exclude", "reason": None, "note": ""}}}])
        self.assertEqual(ta["reviewers"], ["agent", "operator"])
        self.assertEqual(ta["pending_by_reviewer"], {"agent": 0, "operator": 0})
        self.assertEqual(ta["kappa"]["code"], None)
        self.assertEqual((ta["kappa"]["records"], ta["kappa"]["agreement"]), (2, 0.5))
        self.assertIsInstance(ta["kappa"]["value"], float)
        self.assertEqual((ft["eligible"], ft["undecided"], ft["reviewers"]), (1, 1, []))
        self.assertEqual(ft["kappa"]["code"], "REVIEWERS_AMBIGUOUS")
        self.assertIsNone(ft["kappa"]["value"])

    def test_one_reviewer_makes_kappa_not_computable(self) -> None:
        root = workspace(self)
        approve(root)
        identify(root)
        screen(root, "ta", "R0001", {"agent": "include"})
        ta = self.section(self.get(root), "screening")["stages"][0]
        self.assertEqual((ta["partial"], ta["undecided"]), (1, 1))
        self.assertEqual(ta["pending_by_reviewer"], {"agent": 1})
        self.assertEqual(ta["kappa"]["code"], "REVIEWERS_AMBIGUOUS")
        self.assertIn("kappa compares two reviewers", ta["kappa"]["message"])


class PrismaTests(ReviewViewCase):
    def test_counts_the_saved_record_and_the_flow_figure(self) -> None:
        root = workspace(self)
        approve(root)
        identify(root)
        prisma = self.section(self.get(root), "prisma")
        self.assertEqual(prisma["counts"]["identification"], {"databases": {"openalex": 3}, "records": 3,
                                                              "duplicates_removed": 1})
        self.assertEqual(prisma["pending"], 2)
        self.assertIsNone(prisma["saved"])
        self.assertEqual(prisma["flow"], {"path": "paper/Figures/prisma-flow.svg", "exists": False, "mtime": None})

        root = workspace(self)
        build_review(root)
        prisma = self.section(self.get(root), "prisma")
        self.assertEqual(prisma["counts"]["included"], {"studies": 1})
        self.assertNotIn("generated_at", prisma["counts"])
        self.assertTrue(prisma["saved"]["current"])
        self.assertTrue(prisma["saved"]["generated_at"])
        self.assertTrue(prisma["flow"]["exists"])
        self.assertIsInstance(prisma["flow"]["mtime"], int)
        # A decision after `prisma` makes the saved counts stale.
        cli(root, "screen", "--stage", "ta", "--record", "R0002", "--reviewer", "operator", "--decision",
            "exclude", "--final")
        self.assertFalse(self.section(self.get(root), "prisma")["saved"]["current"])


class ExtractionTests(ReviewViewCase):
    def test_protocol_fields_by_included_study_with_value_quote_and_page(self) -> None:
        root = workspace(self)
        build_review(root)
        extraction = self.section(self.get(root), "extraction")
        self.assertEqual([f["id"] for f in extraction["fields"]], ["architecture", "datasets"])
        self.assertEqual(extraction["fields"][1]["type"], "list")
        self.assertEqual((extraction["included"], extraction["extracted"]), (1, 1))
        study = extraction["studies"][0]
        self.assertEqual((study["record_id"], study["title"], study["included"], study["extractor"]),
                         ("R0001", "Message passing for molecules", True, "agent"))
        self.assertEqual(study["values"]["architecture"],
                         {"value": "GCN <b>", "quote": "We use a <b>graph</b> convolution", "page": 3})
        self.assertEqual(study["values"]["datasets"], {"value": ["Tox21", "QM9"], "quote": "", "page": 5})


class RiskOfBiasTests(ReviewViewCase):
    def test_per_study_scores_against_the_protocol_threshold(self) -> None:
        root = workspace(self)
        build_review(root)
        appraisal = self.section(self.get(root), "appraisal")
        self.assertEqual(appraisal["tool"], "Kitchenham")
        self.assertEqual(appraisal["threshold"], 1.5)
        self.assertEqual([q["id"] for q in appraisal["questions"]], ["QA1", "QA2"])
        self.assertEqual(appraisal["scale"], {"yes": 1, "partly": 0.5, "no": 0})
        self.assertEqual(appraisal["not_appraised"], [])
        study = appraisal["studies"][0]
        self.assertEqual((study["record_id"], study["reviewer"], study["score"], study["max_score"]),
                         ("R0001", "operator", 1, 2))
        self.assertEqual(study["answers"], {"QA1": "yes", "QA2": "no"})
        self.assertTrue(study["below_threshold"])
        self.assertNotIn("domains", appraisal)


class SignoffTests(ReviewViewCase):
    def test_the_sign_offs_and_whether_they_are_current(self) -> None:
        root = workspace(self)
        build_review(root)
        self.assertEqual(self.section(self.get(root), "signoffs")["gates"], {"screening": None, "synthesis": None})
        cli(root, "signoff", "--gate", "synthesis", "--by", "Operator")
        synthesis = self.section(self.get(root), "signoffs")["gates"]["synthesis"]
        self.assertEqual((synthesis["by"], synthesis["current"]), ("Operator", True))
        summary = self.section(self.get(root), "summary")
        self.assertEqual((summary["appraised"], summary["extracted"], summary["searches"]), (1, 1, 1))
        self.assertTrue(summary["protocol"]["approved"])


class DegradationTests(ReviewViewCase):
    def test_a_malformed_record_turns_only_its_section_unavailable(self) -> None:
        root = workspace(self)
        build_review(root)
        (root / "review" / "extraction.jsonl").write_text("{not json\n", encoding="utf-8")
        (root / "review" / "prisma.json").write_text("[", encoding="utf-8")
        view = self.get(root)
        self.assertEqual((view["extraction"]["available"], view["extraction"]["code"]), (False, "RECORDS_CORRUPT"))
        self.assertIn("extraction.jsonl:1", view["extraction"]["message"])
        self.assertEqual(view["prisma"]["saved"]["code"], "PRISMA_CORRUPT")
        for name in ("protocol", "searches", "screening", "appraisal", "signoffs"):
            with self.subTest(section=name):
                self.assertTrue(view[name]["available"], view[name])

    def test_a_corrupt_lock_and_screening_log(self) -> None:
        root = workspace(self)
        build_review(root)
        (root / "review" / "protocol.lock.json").write_text("{", encoding="utf-8")
        (root / "review" / "screening.jsonl").write_text("{not json\n", encoding="utf-8")
        view = self.get(root)
        self.assertEqual(view["protocol"]["approval"]["state"], "corrupt")
        self.assertEqual(view["protocol"]["approval"]["code"], "PROTOCOL_LOCK_CORRUPT")
        self.assertEqual(view["screening"]["code"], "RECORDS_CORRUPT")
        self.assertTrue(view["searches"]["available"])

    def test_without_any_review_cli_every_section_says_why(self) -> None:
        root = workspace(self)
        (root / "skills" / "systematic-review" / "scripts" / "review_cli.py").unlink()
        original = review_board.DASHBOARD_REVIEW_CLI
        review_board.DASHBOARD_REVIEW_CLI = root / "absent.py"
        self.addCleanup(setattr, review_board, "DASHBOARD_REVIEW_CLI", original)
        view = self.get(root)
        for name in SECTIONS:
            with self.subTest(section=name):
                self.assertEqual((view[name]["available"], view[name]["code"]), (False, "REVIEW_CLI_UNAVAILABLE"))
        checklist = self.get(root, "/api/review/checklist")
        self.assertEqual((checklist["available"], checklist["code"]), (False, "REVIEW_CLI_UNAVAILABLE"))

    def test_a_broken_workspace_review_cli_is_named(self) -> None:
        root = workspace(self)
        approve(root)
        workspace_cli = root / "skills" / "systematic-review" / "scripts" / "review_cli.py"
        workspace_cli.write_text("def broken(:\n", encoding="utf-8")
        view = self.get(root)
        self.assertIn("SyntaxError", view["cli_warning"])
        self.assertIn(str(workspace_cli), view["cli_warning"])
        self.assertEqual(self.section(view, "protocol")["approval"]["state"], "approved")


class ChecklistTests(ReviewViewCase):
    def test_the_27_items_are_served_on_demand(self) -> None:
        root = workspace(self)
        build_review(root)
        checklist = self.get(root, "/api/review/checklist")
        self.assertTrue(checklist["available"])
        self.assertEqual([item["item"] for item in checklist["items"]], list(range(1, 28)))
        self.assertFalse(checklist["paper_available"])
        item5 = checklist["items"][4]
        self.assertEqual((item5["topic"], item5["record"], item5["status"]), ("Eligibility criteria", "protocol", "owed"))
        self.assertEqual(item5["missing"], ["text:methods.m-eligibility"])
        self.assertEqual(checklist["owed"], list(range(1, 28)))

    def test_the_panel_get_never_runs_the_checklist(self) -> None:
        root = workspace(self)
        build_review(root)
        module = review_board.review_cli(root)
        original = module.cmd_checklist

        def refuse(args):  # pragma: no cover - must not run
            raise AssertionError("the checklist ran inside GET /api/review")

        module.cmd_checklist = refuse
        self.addCleanup(setattr, module, "cmd_checklist", original)
        self.assertTrue(self.get(root)["protocol"]["available"])
        self.assertNotIn("checklist", self.get(root, "/api/status"))

    def test_the_checklist_route_runs_off_the_event_loop(self) -> None:
        source = inspect.getsource(server.create_app)
        route = source[source.index('"/api/review/checklist"'):][:700]
        self.assertIn("async def", route)
        self.assertIn("asyncio.to_thread(review_view.checklist", route)


class ExperimentalWorkspaceTests(ReviewViewCase):
    def test_an_experimental_workspace_is_refused_with_409(self) -> None:
        root = workspace(self, "experimental")
        client = TestClient(server.create_app(root))
        for route in ("/api/review", "/api/review/checklist"):
            with self.subTest(route=route):
                response = client.get(route)
                self.assertEqual(response.status_code, 409)
                body = response.json()
                self.assertEqual((body["ok"], body["code"], body["paper_kind"]),
                                 (False, review_view.NOT_A_REVIEW_WORKSPACE, "experimental"))

    def test_the_experimental_status_and_tabs_are_unchanged(self) -> None:
        for name, lang in (("status-en.json", "en"), ("status-es.json", "es")):
            with self.subTest(golden=name):
                golden = json.loads((characterization.GOLDEN / name).read_text(encoding="utf-8"))
                self.assertEqual(characterization.undeclared(name, golden, characterization.status(lang)), [])
        experimental = re.findall(r"onclick=\"navigateTab\('([a-z]+)'\)\"[^>]*data-kinds=\"experimental\"", PAGE)
        self.assertEqual(experimental, ["modelo", "experiments", "novelty"])
        self.assertIn('body[data-paper-kind="review"] [data-kinds="experimental"] { display: none !important; }', PAGE)


class ReviewTabMarkupTests(unittest.TestCase):
    def test_the_review_tab_follows_the_pipeline_and_shows_only_for_review(self) -> None:
        buttons = re.findall(r"onclick=\"navigateTab\('([a-z]+)'\)\"", PAGE)
        self.assertEqual(buttons[:3], ["flow", "pipeline", "review"])
        self.assertRegex(PAGE, r"onclick=\"navigateTab\('review'\)\" data-kinds=\"review\"")
        self.assertIn('body:not([data-paper-kind="review"]) [data-kinds="review"] { display: none !important; }', PAGE)
        self.assertIn('<div id="pane-review" class="tab-pane">', PAGE)
        self.assertIn('id="reviewPanel"', PAGE)
        self.assertIn('src="./review-panel.js?v=0.82.0"', PAGE)
        self.assertRegex(PAGE, r"if \(tabId === 'review'\) \{?\s*window\.refreshReviewPanel\?\.\(\)")
        self.assertIn("review: () => window.refreshReviewPanel?.()", PAGE)

    def test_a_hidden_tab_redirects_under_either_line(self) -> None:
        body = PAGE[PAGE.index("function applyPaperKind"):PAGE.index("function navigateTab")]
        self.assertNotIn("if (line !== 'review') return;", body)
        self.assertIn("if (visibleTab(activeTab) !== activeTab) navigateTab(activeTab);", body)
        # `'review'` is a substring of `'preview'`: the active button is matched by its quoted id.
        nav = PAGE[PAGE.index("function navigateTab"):][:900]
        self.assertIn("b.getAttribute('onclick')?.includes(`'${tabId}'`)", nav)


if __name__ == "__main__":
    unittest.main()
