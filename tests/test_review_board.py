"""The command center's board for a review workspace (paper-type-lines S6, T6a).

A review workspace (`smith init --kind review`) is a PRISMA 2020 systematic
review: `/api/status` names its paper kind and shows the ten steps of the
review flow (`src/papersmith/templates/paper-flow-review.md.tpl`) with the
review's own gates, sections, artifacts and telemetry labels, while an
experimental workspace keeps exactly the board it had (the characterization
test pins it byte for byte).
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import re
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from papersmith.cli import build_parser
from papersmith.core import init as init_module, manifest
from papersmith.kit import resolve_and_validate
from skills._core.command_center import localize, paper_preview, phase_actions, review_board, server, state_extractor

REPO = Path(__file__).resolve().parents[1]
PAGE = (REPO / "skills/_core/command_center/static/index.html").read_text(encoding="utf-8")
TABS = set(re.findall(r"onclick=\"navigateTab\('([a-z]+)'\)\"", PAGE))
HIDDEN_TABS = ("modelo", "experiments", "novelty")

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
        "exclusion": [{"id": "E1", "text": "No empirical evaluation", "reason": "no evidence"}],
    },
    "sources": [{"name": "openalex", "query": "graph neural network drug discovery"}],
    "date_range": {"from": "2018-01-01", "to": "2025-12-31"},
    "languages": ["en"],
    "publication_types": ["journal article"],
    "screening": {"reviewers": 2},
    "appraisal": {"tool": "Kitchenham", "questions": [{"id": "QA1", "text": "Aims clear?"}],
                  "scale": {"yes": 1, "no": 0}, "threshold": 1},
    "extraction": {"fields": [{"id": "architecture", "description": "GNN family", "type": "text"}]},
    "amendments": [],
}


def _review_cli(root: Path):
    path = root / "skills" / "systematic-review" / "scripts" / "review_cli.py"
    spec = importlib.util.spec_from_file_location("review_cli_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BoardCase(unittest.TestCase):
    def workspace(self, kind: str = "review") -> Path:
        holder = tempfile.TemporaryDirectory(prefix="review-board-", ignore_cleanup_errors=True)
        self.addCleanup(holder.cleanup)
        root = Path(holder.name).resolve() / "ws"
        init_module.initialize(root, tools=("claude",), run_npm=False, run_env=False, kind=kind)
        return root

    def status(self, root: Path, lang: str = "") -> dict:
        response = TestClient(server.create_app(root)).get("/api/status" + (f"?lang={lang}" if lang else ""))
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def cli(self, root: Path, *args: str) -> dict:
        module = _review_cli(root)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = module.main(["--root", str(root), *args])
        payload = json.loads(out.getvalue())
        self.assertEqual(code, 0, payload)
        return payload

    def spanish_gaps(self, status: dict) -> list[str]:
        """Board labels with no Spanish entry; the workspace's own words (the
        contracts' questions, file names) stay as written."""
        own = {b["question"] for s in status["sections"] for b in s["canonical_blocks"]}
        own |= {a["name"] for a in status["artifacts"]}
        fields = localize.DISPLAY_FIELDS["/api/status"]
        return sorted({text for text in localize.display_strings(status, fields)
                       if text not in own and localize.lookup(text) is None})

    @staticmethod
    def phase(status: dict, stage: str) -> dict:
        return next(f for f in status["fases"] if f["stage_id"] == stage)

    @staticmethod
    def gate(status: dict, gate_id: str) -> dict:
        return next(g for g in status["gates"] if g["id"] == gate_id)

    def approved(self, root: Path) -> None:
        (root / "review" / "protocol.json").write_text(json.dumps(PROTOCOL), encoding="utf-8")
        self.cli(root, "protocol", "approve", "--by", "Operator")

    @staticmethod
    def records(root: Path) -> None:
        """Two identified records and their logged search, as `search` leaves them."""
        rows = [{"id": f"R000{i}", "search_id": "S1", "source": "openalex", "title": title, "year": 2021,
                 "venue": "J. Chem. Inf.", "doi": f"10.1/{i}", "abstract": "Graph networks", "authors": [],
                 "keywords": [], "type": "article", "duplicate_of": None}
                for i, title in ((1, "Message passing for molecules"), (2, "Graph kernels revisited"))]
        (root / "review" / "records.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        search = {"id": "S1", "source": "openalex", "query": "graph neural network drug discovery",
                  "method": "api", "run_at": "2026-01-01T00:00:00Z", "total": 2, "retrieved": 2}
        (root / "review" / "searches.jsonl").write_text(json.dumps(search) + "\n", encoding="utf-8")

    def screen(self, root: Path, stage: str, record: str, decision: str, *extra: str) -> None:
        for reviewer in ("agent", "operator"):
            self.cli(root, "screen", "--stage", stage, "--record", record, "--reviewer", reviewer,
                     "--decision", decision, *extra)


class PaperKindTests(BoardCase):
    def test_the_status_names_the_paper_kind(self) -> None:
        self.assertEqual(self.status(self.workspace("review"))["paper_kind"], "review")
        experimental = self.status(self.workspace("experimental"))
        self.assertEqual(experimental["paper_kind"], "experimental")
        self.assertEqual([f["stage_id"] for f in experimental["fases"]], list(phase_actions.STAGES))

    def test_the_kind_is_read_on_every_request(self) -> None:
        root = self.workspace("review")
        client = TestClient(server.create_app(root))
        self.assertEqual(client.get("/api/status").json()["paper_kind"], "review")
        config_path = root / ".papersmith" / "config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config["paper_kind"] = "experimental"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        status = client.get("/api/status").json()
        self.assertEqual(status["paper_kind"], "experimental")
        self.assertEqual([f["stage_id"] for f in status["fases"]], list(phase_actions.STAGES))


class ReviewPipelineTests(BoardCase):
    def test_the_board_shows_the_ten_review_steps(self) -> None:
        status = self.status(self.workspace())
        self.assertEqual([f["stage_id"] for f in status["fases"]], list(review_board.REVIEW_STAGES))
        self.assertEqual(len(review_board.REVIEW_STAGES), 10)
        self.assertEqual([f["id"] for f in status["fases"]], [f"Fase {n}" for n in range(1, 11)])
        self.assertEqual(status["pipeline_stages"], status["fases"])
        for phase in status["fases"]:
            with self.subTest(stage=phase["stage_id"]):
                self.assertTrue(phase["name"].startswith(f"Phase {phase['id'].split()[1]}: "))
                self.assertTrue(phase["actions"])
                self.assertTrue(phase["skills"])
                self.assertTrue(phase["evidence"])
                self.assertIn(phase["status"], ("PASS", "ACTIVE", "PENDING"))
                self.assertTrue(phase["subfases"])
        self.assertEqual(status["fases"][0]["status"], "PASS")
        self.assertEqual(self.phase(status, "protocol")["cli_command"], "/systematic-review")
        self.assertEqual(self.phase(status, "scoping")["cli_command"], "/systematic-review <text>")
        totals = status["totals"]
        self.assertEqual((totals["phases_total"], totals["gates_total"]), (10, len(status["gates"])))
        self.assertEqual(totals["phases_completed"], sum(1 for f in status["fases"] if f["status"] == "PASS"))

    def test_the_review_gates_replace_the_experimental_ones(self) -> None:
        status = self.status(self.workspace())
        self.assertEqual([g["id"] for g in status["gates"]],
                         ["G-PROTOCOL", "G-SCREENING", "G-SYNTHESIS", "G1", "G2", "G3", "G4"])
        self.assertEqual(set(status["gates_map"]), {g["id"] for g in status["gates"]})
        for phase in status["fases"]:
            self.assertNotIn(phase["blocked_by"], ("G-NOVELTY", "G-EXP-POC"), phase["stage_id"])
        self.assertFalse(any(g["id"] in ("G-NOVELTY", "G-EXP-POC") for g in status["gates"]))

    def test_each_step_unlocks_from_its_own_records_and_the_operator_gates(self) -> None:
        root = self.workspace()
        seen: list[dict] = []
        original = self.status

        def status_of(path: Path) -> dict:
            seen.append(original(path))
            return seen[-1]

        self.status = status_of  # every state below must also read in Spanish
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-PROTOCOL")["status"], "PENDING")
        self.assertEqual(self.phase(status, "protocol")["status"], "PENDING")

        (root / "review" / "scope.json").write_text(json.dumps({"total": 1, "reviews": [{"title": "x"}]}),
                                                    encoding="utf-8")
        (root / "review" / "protocol.json").write_text(json.dumps(PROTOCOL), encoding="utf-8")
        status = self.status(root)
        self.assertEqual(self.phase(status, "scoping")["status"], "PASS")
        self.assertEqual(self.phase(status, "protocol")["status"], "ACTIVE")
        self.assertEqual(self.gate(status, "G-PROTOCOL")["status"], "ACTIVE")
        self.assertFalse(self.phase(status, "identification")["unlocked"])

        self.cli(root, "protocol", "approve", "--by", "Operator")
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-PROTOCOL")["status"], "PASS")
        self.assertEqual(self.phase(status, "protocol")["status"], "PASS")
        self.assertTrue(self.phase(status, "identification")["unlocked"])

        # An edit after the approval reopens the gate until it is amended.
        changed = json.loads(json.dumps(PROTOCOL))
        changed["date_range"]["to"] = "2026-06-30"
        (root / "review" / "protocol.json").write_text(json.dumps(changed), encoding="utf-8")
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-PROTOCOL")["status"], "ACTIVE")
        self.assertIn("amendment", self.phase(status, "protocol")["detail"])
        self.assertFalse(self.phase(status, "identification")["unlocked"])
        self.cli(root, "protocol", "amend", "--by", "Operator", "--reason", "extend to 2026")

        self.records(root)
        status = self.status(root)
        self.assertEqual(self.phase(status, "identification")["status"], "PASS")
        self.assertEqual(self.phase(status, "screening")["status"], "ACTIVE")

        self.screen(root, "ta", "R0001", "include")
        self.screen(root, "ta", "R0002", "exclude", "--reason", "E1")
        self.screen(root, "ft", "R0001", "include")
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-SCREENING")["status"], "ACTIVE")
        self.assertEqual(self.phase(status, "screening")["status"], "ACTIVE")
        self.assertFalse(self.phase(status, "appraisal_extraction")["unlocked"])

        self.cli(root, "signoff", "--gate", "screening", "--by", "Operator")
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-SCREENING")["status"], "PASS")
        self.assertEqual(self.phase(status, "screening")["status"], "PASS")
        self.assertIn("Operator", self.phase(status, "screening")["detail"])
        self.assertTrue(self.phase(status, "appraisal_extraction")["unlocked"])

        self.cli(root, "appraise", "--record", "R0001", "--reviewer", "agent", "--answers", '{"QA1": "yes"}')
        self.cli(root, "extract", "--record", "R0001", "--extractor", "agent",
                 "--data", '{"architecture": {"value": "MPNN", "quote": "a message passing network"}}')
        status = self.status(root)
        self.assertEqual(self.phase(status, "appraisal_extraction")["status"], "PASS")
        self.assertEqual(self.phase(status, "synthesis")["status"], "PENDING")
        self.assertTrue(self.phase(status, "synthesis")["unlocked"])

        self.cli(root, "prisma")
        self.cli(root, "flow")
        status = self.status(root)
        self.assertEqual(self.phase(status, "synthesis")["status"], "ACTIVE")
        self.assertEqual(self.gate(status, "G-SYNTHESIS")["status"], "ACTIVE")
        self.assertFalse(self.phase(status, "writing")["unlocked"])

        self.cli(root, "signoff", "--gate", "synthesis", "--by", "Operator")
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-SYNTHESIS")["status"], "PASS")
        self.assertEqual(self.phase(status, "synthesis")["status"], "PASS")
        # Writing opens once the synthesis is accepted; no G-NOVELTY holds it.
        writing = self.phase(status, "writing")
        self.assertTrue(writing["unlocked"])
        self.assertIsNone(writing["blocked_by"])

        # A new screening decision makes both sign-offs stale.
        self.cli(root, "screen", "--stage", "ft", "--record", "R0001", "--reviewer", "operator",
                 "--decision", "exclude", "--reason", "E1", "--final")
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-SCREENING")["status"], "ACTIVE")
        self.assertEqual(self.phase(status, "screening")["status"], "ACTIVE")
        self.assertFalse(self.phase(status, "appraisal_extraction")["unlocked"])
        self.assertEqual(sorted({gap for state in seen for gap in self.spanish_gaps(state)}), [])

    def test_unreadable_records_degrade_one_step_not_the_board(self) -> None:
        root = self.workspace()
        self.approved(root)
        (root / "review" / "screening.jsonl").write_text("{not json\n", encoding="utf-8")
        status = self.status(root)
        screening = self.phase(status, "screening")
        self.assertEqual(screening["status"], "PENDING")
        self.assertIn("RECORDS_CORRUPT", screening["detail"])
        self.assertEqual(self.phase(status, "protocol")["status"], "PASS")

    def test_without_review_cli_the_board_still_answers(self) -> None:
        root = self.workspace()
        (root / "skills" / "systematic-review" / "scripts" / "review_cli.py").unlink()
        original = review_board.DASHBOARD_REVIEW_CLI
        review_board.DASHBOARD_REVIEW_CLI = root / "absent.py"
        self.addCleanup(setattr, review_board, "DASHBOARD_REVIEW_CLI", original)
        status = self.status(root)
        self.assertEqual([f["stage_id"] for f in status["fases"]], list(review_board.REVIEW_STAGES))
        self.assertIn("review_cli.py", self.phase(status, "protocol")["detail"])

    def test_a_broken_workspace_review_cli_falls_back_visibly(self) -> None:
        root = self.workspace()
        self.approved(root)
        workspace_cli = root / "skills" / "systematic-review" / "scripts" / "review_cli.py"
        workspace_cli.write_text("def broken(:\n", encoding="utf-8")
        status = self.status(root)
        protocol = self.phase(status, "protocol")
        # The bundled copy still reads the records...
        self.assertEqual(protocol["status"], "PASS")
        # ...and every step it read says why the workspace's own copy was not used.
        for stage in ("scoping", "protocol", "identification", "screening", "appraisal_extraction", "synthesis"):
            with self.subTest(stage=stage):
                detail = self.phase(status, stage)["detail"]
                self.assertIn("the workspace's review_cli.py did not load (SyntaxError", detail)
                self.assertIn(str(workspace_cli), detail)
        for stage in ("harness", "writing", "paper", "reporting_audit"):
            with self.subTest(stage=stage):
                self.assertNotIn("did not load", self.phase(status, stage)["detail"])
        self.assertEqual(self.spanish_gaps(status), [])
        spanish = self.phase(self.status(root, "es"), "protocol")["detail"]
        self.assertIn("SyntaxError", spanish)
        self.assertNotIn("did not load", spanish)
        # Repaired, the warning goes away.
        workspace_cli.write_text((REPO / "skills/systematic-review/scripts/review_cli.py").read_text(encoding="utf-8"),
                                 encoding="utf-8")
        self.assertNotIn("did not load", self.phase(self.status(root), "protocol")["detail"])

    def test_every_review_card_runs_a_real_command(self) -> None:
        root = self.workspace()
        smith = {a for a in build_parser()._actions if a.__class__.__name__ == "_SubParsersAction"}
        smith_verbs = set(next(iter(smith)).choices)
        review_parser = _review_cli(root).build_parser()
        review_verbs = set(next(a for a in review_parser._actions
                                if a.__class__.__name__ == "_SubParsersAction").choices)
        cli = "python skills/systematic-review/scripts/review_cli.py"
        for stage, entry in review_board.REVIEW_ACTIONS.items():
            for action in entry["actions"]:
                with self.subTest(stage=stage, action=action["label"]):
                    if action["kind"] == "prompt":
                        self.assertTrue(action["guide"])
                        name = action["slash"].lstrip("/")
                        self.assertTrue((root / ".claude" / "commands" / f"{name}.md").is_file(), name)
                    elif action["kind"] == "command":
                        command = action["command"]
                        if command.startswith(cli):
                            self.assertIn(command[len(cli):].split()[0], review_verbs)
                        else:
                            words = command.split()
                            self.assertEqual(words[0], "smith")
                            self.assertIn(words[1], smith_verbs)
                    else:
                        self.assertIn(action["tab"], TABS)
                        self.assertNotIn(action["tab"], HIDDEN_TABS)
        self.assertEqual(set(review_board.REVIEW_ACTIONS), set(review_board.REVIEW_STAGES))
        self.assertEqual(set(review_board.REVIEW_EVIDENCE), set(review_board.REVIEW_STAGES))

    def test_a_signoff_card_is_typed_for_the_operator_never_run(self) -> None:
        commands = [a["command"] for entry in review_board.REVIEW_ACTIONS.values() for a in entry["actions"]
                    if a["kind"] == "command" and " signoff " in a["command"]]
        self.assertEqual(len(commands), 2)
        for command in commands:
            self.assertRegex(command, r'--by "<[^>]+>"')

    def test_a_review_phase_check_answers_with_its_review_step(self) -> None:
        root = self.workspace()
        client = TestClient(server.create_app(root))
        body = client.post("/api/phase/run", json={"phase_id": "Fase 3"}).json()
        self.assertEqual((body["stage"], body["status"], body["verified"]), ("protocol", "PENDING", False))
        self.assertIn("Phase 3", body["message"])


    def test_a_phase_run_reads_the_paper_line_once(self) -> None:
        # `smith kind set` moves the line while the request runs: the stage is
        # resolved, dispatched and verified under the line read first.
        root = self.workspace()
        client = TestClient(server.create_app(root))
        lines = iter(["review"])
        calls = []

        def moving_line(path):
            calls.append(path)
            return next(lines, "experimental")

        original = server.paper_line.current_line
        server.paper_line.current_line = moving_line
        self.addCleanup(setattr, server.paper_line, "current_line", original)
        body = client.post("/api/phase/run", json={"phase_id": "Fase 3"}).json()
        self.assertEqual((body["stage"], body["status"], body["verified"]), ("protocol", "PENDING", False))
        self.assertIn("Phase 3: it runs from its card", body["message"])
        self.assertTrue(calls)


class ExperimentalPhaseRunTests(BoardCase):
    """`/api/phase/run` answers an experimental workspace exactly as before the review board."""

    def test_the_experimental_phase_run_keys_are_unchanged(self) -> None:
        root = self.workspace("experimental")
        client = TestClient(server.create_app(root))
        common = ["evidence", "message", "ok", "outputs", "phase_id", "stage", "status", "verified"]
        stages = ["harness", "plausibility", "ingestion", "proposal", "poc_experiments", "scaffolding",
                  "declarations", "writing", "figures", "paper", "audit"]
        for number, stage in enumerate(stages, 1):
            with self.subTest(phase=number):
                response = client.post("/api/phase/run", json={"phase_id": f"Fase {number}"})
                body = response.json()
                self.assertEqual(response.status_code, 200)
                self.assertEqual(sorted(body), sorted(common + (["log"] if stage == "audit" else [])))
                self.assertEqual(body["stage"], stage)
        unknown = client.post("/api/phase/run", json={"phase_id": "Fase 12"})
        self.assertEqual((unknown.status_code, sorted(unknown.json())), (422, ["error", "ok"]))

    def test_a_failed_experimental_build_gets_no_stage_key(self) -> None:
        root = self.workspace("experimental")

        def broken(_root):
            raise RuntimeError("build failed")

        original = server._build_manuscript
        server._build_manuscript = broken
        self.addCleanup(setattr, server, "_build_manuscript", original)
        response = TestClient(server.create_app(root)).post("/api/phase/run", json={"phase_id": "Fase 8"})
        self.assertEqual(response.status_code, 500)
        self.assertEqual(sorted(response.json()), ["error", "evidence", "ok", "status", "verified"])


class ReviewSectionsTests(BoardCase):
    def test_the_review_order_is_the_review_kit_layout(self) -> None:
        layout = manifest.kit_layout(resolve_and_validate(), "review")
        stems = sorted(Path(p).stem for p in layout if p.startswith("sections/"))
        self.assertEqual(sorted(state_extractor.REVIEW_SECTION_ORDER), stems)
        self.assertEqual(state_extractor.REVIEW_SECTION_ORDER, tuple(stems))

    def test_sections_show_the_review_contracts_and_no_missing_experimental_one(self) -> None:
        root = self.workspace()
        status = self.status(root)
        ids = [s["id"] for s in status["sections"]]
        expected = sorted(p.stem for p in (root / "sections").glob("*.md"))
        self.assertEqual(ids, expected)
        self.assertFalse(any(s["id"] == "01-materials-and-methods" for s in status["sections"]))
        self.assertEqual([s["id"] for s in status["state"]["sections"]], expected)
        self.assertNotIn("SCAFFOLDED", {s["status"] for s in status["sections"]})
        by_id = {s["id"]: s for s in status["sections"]}
        methods = by_id["05-methods"]
        self.assertTrue(methods["has_figures"])
        self.assertTrue(by_id["06-results"]["has_figures"])
        self.assertFalse(by_id["08-limitations"]["has_figures"])
        front = json.loads((root / "sections" / "05-methods.md").read_text(encoding="utf-8").split("---")[1])
        self.assertEqual([b["id"] for b in methods["canonical_blocks"]],
                         [f"methods.{b['id']}" for b in front["blocks"]])
        self.assertTrue(all(b["role"] and b["question"] for b in methods["canonical_blocks"]))
        self.assertEqual(methods["canonical_blocks"][0]["role"], "PRISMA 2020 item 24")
        # The shared back matter keeps its experimental metadata.
        self.assertEqual(by_id["10-back-matter"]["principles"],
                         self.status(self.workspace("experimental"))["sections"][-1]["principles"])
        self.assertEqual(status["totals"]["sections_count"], len(expected))

    def test_the_paper_preview_lists_the_review_sections(self) -> None:
        root = self.workspace()
        preview = paper_preview.build_preview(root)
        self.assertEqual([s["id"] for s in preview["sections"]],
                         sorted(p.stem for p in (root / "sections").glob("*.md")))


class ReviewArtifactsAndTelemetryTests(BoardCase):
    def test_the_review_records_are_artifacts(self) -> None:
        root = self.workspace()
        self.approved(root)
        status = self.status(root)
        records = [a for a in status["artifacts"] if a["category"] == "Review Records"]
        self.assertEqual([a["rel_path"] for a in records], ["review/protocol.json", "review/protocol.lock.json"])
        self.assertEqual(records[0]["name"], "protocol.json")

    def test_review_telemetry_has_labels_and_no_invented_numbers(self) -> None:
        root = self.workspace()
        self.approved(root)
        status = self.status(root)
        rows = status["telemetria"]
        measured = [f for f in status["fases"] if f["status"] in ("PASS", "ACTIVE")]
        self.assertEqual([r["fase"] for r in rows], [f["name"] for f in measured])
        for row in rows:
            with self.subTest(row=row["fase"]):
                self.assertEqual((row["tokens"], row["tool_uses"], row["duracion"]), (None, None, None))
                self.assertTrue(row["note"])
                self.assertIn(row["veredicto"], ("PASS", "ACTIVE"))
        self.assertIn("G-PROTOCOL", [r["gate"] for r in rows])
        self.assertEqual((status["totals"]["total_tokens"], status["totals"]["total_tool_uses"]), ("0", 0))


class ReviewSpanishTests(BoardCase):
    def test_every_review_label_has_a_spanish_entry(self) -> None:
        root = self.workspace()
        for step in ("empty", "approved", "changed"):
            if step == "approved":
                self.approved(root)
            if step == "changed":
                (root / "review" / "protocol.json").write_text(json.dumps({**PROTOCOL, "title": "x"}),
                                                               encoding="utf-8")
            with self.subTest(step=step):
                self.assertEqual(self.spanish_gaps(self.status(root)), [])

    def test_the_spanish_board_keeps_its_machine_values(self) -> None:
        root = self.workspace()
        english, spanish = self.status(root), self.status(root, "es")
        self.assertTrue(spanish["fases"][2]["name"].startswith("Fase 3: "))
        self.assertEqual([f["stage_id"] for f in spanish["fases"]], [f["stage_id"] for f in english["fases"]])
        self.assertEqual(spanish["paper_kind"], "review")


class ReviewPageTests(unittest.TestCase):
    """The page hides the experimental-only views under a review workspace (no JS runner here)."""

    def test_the_experimental_only_tabs_and_atlas_views_are_marked(self) -> None:
        for tab in HIDDEN_TABS:
            with self.subTest(tab=tab):
                self.assertRegex(PAGE, rf"onclick=\"navigateTab\('{tab}'\)\"[^>]*data-kinds=\"experimental\"")
        for button in ("btnGraphAtlas", "btnGraphNovelty", "btnBuildGraph", "btnGroupLayout", "btnAtlasManuscript"):
            with self.subTest(button=button):
                self.assertRegex(PAGE, rf'id="{button}"[^>]*data-kinds="experimental"')

    def test_the_page_reads_the_kind_and_redirects_a_hidden_tab(self) -> None:
        self.assertIn('body[data-paper-kind="review"] [data-kinds="experimental"]', PAGE)
        self.assertIn("applyPaperKind(data.paper_kind)", PAGE)
        self.assertIn("document.body.dataset.paperKind", PAGE)
        self.assertRegex(PAGE, r"function navigateTab\(tabId\) \{\s*tabId = visibleTab\(tabId\);")


class ReviewFlowTemplateTests(unittest.TestCase):
    def test_the_review_flow_describes_the_review_board(self) -> None:
        text = (REPO / "src/papersmith/templates/paper-flow-review.md.tpl").read_text(encoding="utf-8")
        self.assertNotIn("still shows the experimental phases", text)
        self.assertIn("signoff --gate screening", text)
        self.assertIn("signoff --gate synthesis", text)


if __name__ == "__main__":
    unittest.main()
