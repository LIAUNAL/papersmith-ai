"""The empirical board's qualitative-participatory table (paper-type-lines S8, T8-B6, decisions K2-K5).

A `qualitative-participatory` workspace shows the ten steps of
`src/papersmith/templates/paper-flow-qualitative-participatory.md.tpl` with the
line's own G-STUDY-PROTOCOL, G-ETHICS, G-TRANSCRIPTS, G-ROUNDS and G-ANALYSIS.
The agreed variant (`.papersmith/paper_type.json`) decides each of them:

* qualitative-mixed: protocol, ethics, current transcripts and a current theme
  sign-off are required; G-ROUNDS is not listed;
* consensus-foresight: protocol, ethics, G-ROUNDS and the consensus results
  (a recorded MICMAC analysis must be current); transcripts are optional;
* experience-report: protocol and transcripts optional, G-ANALYSIS not
  applicable, G-ETHICS as shared (a not-applicable record passes).

With no variant agreed the qualitative-mixed rules apply and the gates say so.
Every record is written through the real CLIs (`study_cli.py`, `qual_cli.py`,
`consensus_cli.py`, `paper_type_cli.py`); the board only reads them and never
shows a transcript's text, a response or a comment.
"""

from __future__ import annotations

import json
import re
import shlex
import shutil
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from papersmith.core.init import initialize
from skills._core.command_center import empirical_board, lines, localize, server
from tests import test_empirical_board as base

REPO, TABS = base.REPO, base.TABS

KIND = "qualitative-participatory"
STEPS = ["harness", "plausibility_qualitative", "case_framework", "ethics_consent_quotes", "fieldwork",
         "coding_consensus", "integration", "writing", "paper", "reporting_qualitative"]
LINE_GATES = ["G-STUDY-PROTOCOL", "G-ETHICS", "G-TRANSCRIPTS", "G-ANALYSIS"]
CONSENSUS_GATES = ["G-STUDY-PROTOCOL", "G-ETHICS", "G-TRANSCRIPTS", "G-ROUNDS", "G-ANALYSIS"]
SHARED = ["G1", "G2", "G3", "G4"]
PAPER_TYPE = "skills/_core/paper_types/paper_type_cli.py"
QUAL = "skills/_core/qualitative/qual_cli.py"
CONSENSUS = "skills/_core/qualitative/consensus_cli.py"
IDEA = ("Rural nurses adapt telehealth to their communities in ways the guidelines do not foresee. We interview "
        "twenty nurses in three districts and analyse the interviews thematically.")
#: Recognizable tokens of what participants said: they must never reach the board.
TRANSCRIPT_TOKEN = "QUOKKA-ZEBRA-4411"
COMMENT_TOKEN = "PANGOLIN-MARMOT-9902"
TRANSCRIPT = f"Interviewer: how do you use the tablet?\nP01: {TRANSCRIPT_TOKEN} we carry it to the farms.\n"
PANEL = ("E01", "E02", "E03", "E04")
ROUND_1 = ["E01,I1,5,", f"E02,I1,4,{COMMENT_TOKEN} first", "E03,I1,4,", "E04,I1,2,",
           "E01,I2,1,", "E02,I2,2,", f"E03,I2,4,\"{COMMENT_TOKEN}, quoted\"", "E04,I2,3,"]
ROUND_2 = ["E01,I2,4,", "E02,I2,4,", "E03,I2,5,", f"E04,I2,3,{COMMENT_TOKEN} again"]
MATRIX = ["x,A,B,C,D", "A,0,P,3,1", "B,2,0,3,1", "C,0,1,0,0", "D,0,1,0,0"]
NO_VARIANT = "No variant agreed yet, treated as a qualitative or mixed study (the strictest case for transcripts)"

_TEMPLATES: dict[str, Path] = {}


def _template() -> Path:
    if "ws" not in _TEMPLATES:
        ws = Path(tempfile.mkdtemp(prefix="b6-template-")) / "ws"
        initialize(ws, tools=("claude",), run_npm=False, run_env=False, kind=KIND)
        _TEMPLATES["ws"] = ws
    return _TEMPLATES["ws"]


def tearDownModule() -> None:  # noqa: N802 - unittest hook
    for ws in _TEMPLATES.values():
        shutil.rmtree(ws.parent, ignore_errors=True)


class QualBoardCase(base.BoardCase):
    def workspace(self) -> Path:
        holder = tempfile.TemporaryDirectory(prefix="b6-case-", ignore_cleanup_errors=True)
        self.addCleanup(holder.cleanup)
        root = Path(holder.name) / "ws"
        shutil.copytree(_template(), root, symlinks=True)
        return root

    @staticmethod
    def write(root: Path, rel: str, text: str) -> None:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def qual(self, root: Path, *args: str) -> dict:
        return self.run_cli(root, QUAL, *args, "--root", str(root))

    def consensus(self, root: Path, *args: str) -> dict:
        return self.run_cli(root, CONSENSUS, *args, "--root", str(root))

    def agree(self, root: Path, variant: str | None) -> None:
        self.write(root, "idea.txt", IDEA)
        self.run_cli(root, PAPER_TYPE, "accept", "--root", str(root), "--by", "Ana Ruiz", "--idea-file",
                     str(root / "idea.txt"))
        extra = ("--variant", variant) if variant else ()
        self.run_cli(root, PAPER_TYPE, "agree", "--root", str(root), "--type", KIND, *extra, "--by", "Ana Ruiz")

    def ethics(self, root: Path) -> None:
        self.study(root, "ethics", "record", "--by", "Ana Ruiz", "--committee", "District IRB", "--code", "IRB-31",
                   "--date", "2026-01-02", "--consent", "written consent, consent to be quoted included")

    def transcript(self, root: Path, participant: str = "P01", *extra: str) -> None:
        self.write(root, f"data/{participant.lower()}.txt", TRANSCRIPT.replace("P01", participant))
        self.qual(root, "transcripts", "add", "--file", f"data/{participant.lower()}.txt", "--participant",
                  participant, "--consent", "written consent, form C-12", "--deidentified",
                  "names and places replaced by codes", "--by", "Ana Ruiz", *extra)

    def codebook(self, root: Path) -> None:
        self.write(root, "analysis/codebook.md", "# Codebook\n- adaptation\n- distance\n")
        self.qual(root, "codebook", "record", "--file", "analysis/codebook.md", "--by", "Ana Ruiz")

    def themes(self, root: Path) -> None:
        self.write(root, "analysis/themes.md", "# Themes\n1. Carrying the clinic\n")
        self.qual(root, "themes", "signoff", "--file", "analysis/themes.md", "--by", "Ana Ruiz")

    def qualitative_study(self, root: Path) -> None:
        self.agree(root, "qualitative-mixed")
        self.approved(root)
        self.ethics(root)
        self.transcript(root)
        self.codebook(root)
        self.themes(root)

    def plan(self, root: Path) -> None:
        self.consensus(root, "plan", "record", "--rounds", "2", "--threshold", "75", "--scale", "1-5",
                       "--agree-from", "4", "--by", "Ana Ruiz")

    def panel(self, root: Path) -> None:
        for member in PANEL:
            self.consensus(root, "panel", "add", "--member", member, "--expertise", "district nurse", "--by",
                           "Ana Ruiz")

    def round(self, root: Path, k: int, rows: list[str]) -> None:
        self.write(root, f"data/round{k}.csv", "member,item,rating,comment\n" + "\n".join(rows) + "\n")
        self.consensus(root, "round", "record", "--round", str(k), "--file", f"data/round{k}.csv", "--by", "Ana Ruiz")

    def micmac(self, root: Path) -> None:
        self.write(root, "data/matrix.csv", "\n".join(MATRIX) + "\n")
        self.consensus(root, "micmac", "compute", "--file", "data/matrix.csv", "--by", "Ana Ruiz")

    def consensus_study(self, root: Path) -> None:
        self.agree(root, "consensus-foresight")
        self.approved(root)
        self.ethics(root)
        self.plan(root)
        self.panel(root)
        self.round(root, 1, ROUND_1)
        self.round(root, 2, ROUND_2)

    @staticmethod
    def gate_ids(status: dict) -> list[str]:
        return [g["id"] for g in status["gates"]]


# --------------------------------------------------------------------------- steps


class StepsTests(QualBoardCase):
    def test_the_board_shows_the_ten_steps_of_the_flow(self) -> None:
        self.assertTrue(lines.registered(KIND))
        status = self.status(self.workspace())
        self.assertEqual(status["paper_kind"], KIND)
        self.assertNotIn("board_notice", status)
        self.assertEqual([f["stage_id"] for f in status["fases"]], STEPS)
        self.assertEqual(self.gate_ids(status), LINE_GATES + SHARED)
        phases = {g["id"]: g["phase"] for g in status["gates"]}
        self.assertEqual([phases[g] for g in LINE_GATES], ["Fase 3", "Fase 4", "Fase 5", "Fase 6"])
        for gate in LINE_GATES:
            with self.subTest(gate=gate):
                self.assertEqual(self.gate(status, gate)["reviewer"], "operator")
                self.assertNotEqual(self.gate(status, gate)["status"], "PASS")
        self.assertEqual(self.phase(status, "fieldwork")["name"],
                         "Phase 5: Fieldwork, Rounds or Implementation (G-TRANSCRIPTS, G-ROUNDS)")
        for stage in STEPS:
            with self.subTest(stage=stage):
                phase = self.phase(status, stage)
                self.assertTrue(phase["actions"])
                self.assertTrue(phase["evidence"])
                self.assertTrue(phase["subfases"])

    def test_the_steps_follow_the_flow_template(self) -> None:
        flow = (REPO / "src/papersmith/templates/paper-flow-qualitative-participatory.md.tpl").read_text(
            encoding="utf-8")
        self.assertEqual(len(re.findall(r"^\s*(\d+)\. \*\*", flow, re.M)), len(STEPS))
        self.assertEqual(list(empirical_board.LINE_TABLES[KIND].steps), STEPS)
        self.assertEqual(lines.board(KIND).flow_html, "papersmith-flow.html")

    def test_the_agreed_variant_passes_step_two(self) -> None:
        root = self.workspace()
        self.agree(root, "consensus-foresight")
        step = self.phase(self.status(root), "plausibility_qualitative")
        self.assertEqual(step["status"], "PASS", step["detail"])
        self.assertIn(f"Paper type {KIND} (consensus-foresight) agreed by Ana Ruiz", step["detail"])

    def test_the_variant_reader(self) -> None:
        root = self.workspace()
        self.assertEqual(empirical_board.qual_variant(root), ("qualitative-mixed", True))
        self.agree(root, None)
        self.assertEqual(empirical_board.qual_variant(root), ("qualitative-mixed", True))
        for variant in ("qualitative-mixed", "consensus-foresight", "experience-report"):
            self.agree(root, variant)
            self.assertEqual(empirical_board.qual_variant(root), (variant, False))
        # A stale agreement (the idea changed since) gets the default rules again.
        self.write(root, "idea.txt", IDEA + " We add a document analysis.")
        self.run_cli(root, PAPER_TYPE, "accept", "--root", str(root), "--by", "Ana Ruiz", "--idea-file",
                     str(root / "idea.txt"))
        if empirical_board.agreed_type(root)["stale"]:
            self.assertEqual(empirical_board.qual_variant(root), ("qualitative-mixed", True))


# --------------------------------------------------------------------------- G-STUDY-PROTOCOL and G-ETHICS


class ProtocolEthicsTests(QualBoardCase):
    def test_the_protocol_is_required_for_a_qualitative_study_and_says_so_without_a_variant(self) -> None:
        root = self.workspace()
        gate = self.gate(self.status(root), "G-STUDY-PROTOCOL")
        self.assertEqual(gate["status"], "PENDING")
        sub = next(s for s in self.phase(self.status(root), "case_framework")["subfases"]
                   if "G-STUDY-PROTOCOL" in s["name"])
        self.assertIn(NO_VARIANT, sub["detail"])
        self.agree(root, "qualitative-mixed")
        self.approved(root)
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-STUDY-PROTOCOL")["status"], "PASS")
        self.assertEqual(self.phase(status, "case_framework")["status"], "PASS")

    def test_an_experience_report_keeps_the_protocol_optional_until_it_keeps_one(self) -> None:
        root = self.workspace()
        self.agree(root, "experience-report")
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-STUDY-PROTOCOL")["status"], "PASS")
        step = self.phase(status, "case_framework")
        self.assertEqual(step["status"], "PASS", step["detail"])
        self.assertIn("Optional for an experience report (not blocking)", step["detail"])
        # A protocol kept reads as the shared gate.
        self.revision(root, 1)
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-STUDY-PROTOCOL")["status"], "PENDING")
        self.assertEqual(self.phase(status, "case_framework")["status"], "ACTIVE")
        self.study(root, "protocol", "approve", "--by", "Ana Ruiz")
        self.assertEqual(self.gate(self.status(root), "G-STUDY-PROTOCOL")["status"], "PASS")

    def test_a_consensus_study_records_its_plan_in_step_three(self) -> None:
        root = self.workspace()
        self.agree(root, "consensus-foresight")
        self.approved(root)
        step = self.phase(self.status(root), "case_framework")
        self.assertEqual(step["status"], "ACTIVE")
        self.assertIn("No consensus plan recorded yet", step["detail"])
        self.plan(root)
        step = self.phase(self.status(root), "case_framework")
        self.assertEqual(step["status"], "PASS", step["detail"])
        plan = next(s for s in step["subfases"] if s["name"].startswith("Consensus plan"))
        self.assertIn("2 round(s), threshold 75%, scale 1-5, agreement from 4; recorded by Ana Ruiz", plan["detail"])

    def test_the_ethics_gate_is_shared_and_a_not_applicable_record_passes(self) -> None:
        root = self.workspace()
        self.agree(root, "experience-report")
        gate = self.gate(self.status(root), "G-ETHICS")
        self.assertEqual(gate["status"], "PENDING")
        step = self.phase(self.status(root), "ethics_consent_quotes")
        self.assertIn("ethics record --not-applicable --reason <why> --by <name>", step["detail"])
        # With no protocol at all, the report records why no ethics record applies (K5).
        self.study(root, "ethics", "record", "--by", "Ana Ruiz", "--not-applicable", "--reason",
                   "the report describes a course; no participant data")
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-ETHICS")["status"], "PASS")
        self.assertIn("Not applicable, recorded by Ana Ruiz", self.phase(status, "ethics_consent_quotes")["detail"])
        # Once it keeps a protocol, the statement is recorded again against the lock.
        self.approved(root)
        self.assertEqual(self.gate(self.status(root), "G-ETHICS")["status"], "ACTIVE")
        self.study(root, "ethics", "record", "--by", "Ana Ruiz", "--not-applicable", "--reason",
                   "the report describes a course; no participant data")
        self.assertEqual(self.gate(self.status(root), "G-ETHICS")["status"], "PASS")
        # An amendment makes it stale, as for every line.
        self.revision(root, 2)
        self.study(root, "protocol", "amend", "--by", "Ana Ruiz", "--reason", "scope")
        self.assertEqual(self.gate(self.status(root), "G-ETHICS")["status"], "ACTIVE")

    def test_a_qualitative_study_needs_the_ethics_approval(self) -> None:
        root = self.workspace()
        self.agree(root, "qualitative-mixed")
        self.approved(root)
        self.assertEqual(self.gate(self.status(root), "G-ETHICS")["status"], "PENDING")
        self.ethics(root)
        gate = self.phase(self.status(root), "ethics_consent_quotes")
        self.assertEqual(gate["status"], "PASS")
        self.assertIn("Approved by District IRB (IRB-31)", gate["detail"])


# --------------------------------------------------------------------------- G-TRANSCRIPTS


class TranscriptsTests(QualBoardCase):
    def test_absent_current_stale_and_corrupt(self) -> None:
        root = self.workspace()
        self.agree(root, "qualitative-mixed")
        gate = self.gate(self.status(root), "G-TRANSCRIPTS")
        self.assertEqual(gate["status"], "PENDING")
        self.assertIn("No transcript registered yet", self.phase(self.status(root), "fieldwork")["detail"])
        self.transcript(root)
        self.transcript(root, "P02", "--kind", "focus-group")
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-TRANSCRIPTS")["status"], "PASS")
        step = self.phase(status, "fieldwork")
        self.assertEqual(step["status"], "PASS", step["detail"])
        self.assertIn("2 transcript(s) of 2 participant(s)", step["detail"])
        self.write(root, "data/p02.txt", "edited\n")
        (root / "data" / "p01.txt").unlink()
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-TRANSCRIPTS")["status"], "ACTIVE")
        detail = self.phase(status, "fieldwork")["detail"]
        self.assertIn("transcript missing: data/p01.txt (P01)", detail)
        self.assertIn("transcript changed since its registration: data/p02.txt (P02)", detail)
        self.write(root, "study/transcripts.json", "{not json")
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-TRANSCRIPTS")["status"], "FAIL")
        self.assertIn("The transcript registrations are unreadable", self.phase(status, "fieldwork")["detail"])

    def test_with_no_variant_the_transcripts_are_required_and_say_so(self) -> None:
        root = self.workspace()
        sub = self.phase(self.status(root), "fieldwork")["subfases"][0]
        self.assertEqual(sub["status"], "PENDING")
        self.assertIn(NO_VARIANT, sub["detail"])

    def test_the_transcripts_are_optional_for_a_consensus_study_and_an_experience_report(self) -> None:
        for variant, text in (("consensus-foresight", "Optional for a consensus study (not blocking)"),
                              ("experience-report", "Optional for an experience report (not blocking)")):
            with self.subTest(variant=variant):
                root = self.workspace()
                self.agree(root, variant)
                gate = self.gate(self.status(root), "G-TRANSCRIPTS")
                self.assertEqual(gate["status"], "PASS")
                sub = self.phase(self.status(root), "fieldwork")["subfases"][0]
                self.assertIn(f"{text}: no transcript registered", sub["detail"])
                # A registration kept is shown as it stands and still never blocks.
                self.transcript(root)
                self.write(root, "data/p01.txt", "edited\n")
                status = self.status(root)
                self.assertEqual(self.gate(status, "G-TRANSCRIPTS")["status"], "PASS")
                sub = self.phase(status, "fieldwork")["subfases"][0]
                self.assertIn(f"{text}: Stale (transcript changed since its registration: data/p01.txt (P01))", sub["detail"])

    def test_an_experience_report_passes_its_fieldwork_step(self) -> None:
        root = self.workspace()
        self.agree(root, "experience-report")
        step = self.phase(self.status(root), "fieldwork")
        self.assertEqual(step["status"], "PASS", step["detail"])


# --------------------------------------------------------------------------- G-ROUNDS


class RoundsTests(QualBoardCase):
    def test_listed_only_for_a_consensus_study(self) -> None:
        for variant in (None, "qualitative-mixed", "experience-report"):
            with self.subTest(variant=variant):
                root = self.workspace()
                if variant:
                    self.agree(root, variant)
                status = self.status(root)
                self.assertNotIn("G-ROUNDS", self.gate_ids(status))
                self.assertNotIn("Consensus rounds (G-ROUNDS, operator)",
                                 [s["name"] for s in self.phase(status, "fieldwork")["subfases"]])
        root = self.workspace()
        self.agree(root, "consensus-foresight")
        status = self.status(root)
        self.assertEqual(self.gate_ids(status), CONSENSUS_GATES + SHARED)
        self.assertEqual(self.gate(status, "G-ROUNDS")["phase"], "Fase 5")

    def test_absent_open_passed_stale_and_corrupt(self) -> None:
        root = self.workspace()
        self.agree(root, "consensus-foresight")
        self.approved(root)
        self.ethics(root)
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-ROUNDS")["status"], "PENDING")
        self.assertIn("No consensus plan recorded yet", self.phase(status, "fieldwork")["detail"])
        self.plan(root)
        self.panel(root)
        self.round(root, 1, ROUND_1)
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-ROUNDS")["status"], "ACTIVE")
        step = self.phase(status, "fieldwork")
        self.assertIn("planned round(s) not recorded: 2", step["detail"])
        panel = next(s for s in step["subfases"] if s["name"].startswith("Consensus panel"))
        self.assertIn("4 panel member(s) registered by anonymised code", panel["detail"])
        self.round(root, 2, ROUND_2)
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-ROUNDS")["status"], "PASS")
        step = self.phase(status, "fieldwork")
        self.assertEqual(step["status"], "PASS", step["detail"])
        self.assertIn("All 2 planned round(s) recorded and current; round 2: 4 responder(s), 1 of 1 item(s) at "
                      "consensus", step["detail"])
        self.write(root, "data/round1.csv", "member,item,rating,comment\nE01,I1,1,\n")
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-ROUNDS")["status"], "ACTIVE")
        self.assertIn("round 1: its response file changed since it was recorded",
                      self.phase(status, "fieldwork")["detail"])
        self.revision(root, 2)
        self.study(root, "protocol", "amend", "--by", "Ana Ruiz", "--reason", "threshold wording")
        detail = self.phase(self.status(root), "fieldwork")["detail"]
        self.assertIn("the consensus plan covers an earlier protocol", detail)
        self.write(root, "study/consensus/rounds.json", "{broken")
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-ROUNDS")["status"], "FAIL")
        self.assertIn("The consensus records are unreadable", self.phase(status, "fieldwork")["detail"])


# --------------------------------------------------------------------------- G-ANALYSIS


class AnalysisTests(QualBoardCase):
    def test_a_qualitative_study_needs_a_current_theme_signoff(self) -> None:
        root = self.workspace()
        self.agree(root, "qualitative-mixed")
        self.approved(root)
        self.transcript(root)
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-ANALYSIS")["status"], "PENDING")
        self.codebook(root)
        step = self.phase(self.status(root), "coding_consensus")
        self.assertEqual(step["status"], "ACTIVE")
        self.assertIn("Codebook version 1 recorded; the themes await the operator's sign-off", step["detail"])
        self.themes(root)
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-ANALYSIS")["status"], "PASS")
        step = self.phase(status, "coding_consensus")
        self.assertIn("Themes signed off by Ana Ruiz on codebook version 1, bound to 1 transcript(s)", step["detail"])
        self.assertEqual([s["name"] for s in step["subfases"]],
                         ["Codebook versions (operator)", "Theme sign-off (G-ANALYSIS, operator)"])
        # A transcript registered after the sign-off and a changed codebook make it stale, named.
        self.transcript(root, "P02")
        self.write(root, "analysis/codebook.md", "# Codebook\n- changed\n")
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-ANALYSIS")["status"], "ACTIVE")
        detail = self.phase(status, "coding_consensus")["detail"]
        self.assertIn("a transcript was registered after the sign-off", detail)
        self.assertIn("the codebook file changed or its record is unreadable", detail)
        self.write(root, "study/themes.json", "[]")
        self.assertEqual(self.gate(self.status(root), "G-ANALYSIS")["status"], "FAIL")

    def test_a_consensus_study_needs_its_rounds_and_a_current_micmac(self) -> None:
        root = self.workspace()
        self.agree(root, "consensus-foresight")
        self.approved(root)
        self.plan(root)
        gate = self.phase(self.status(root), "coding_consensus")
        self.assertEqual(gate["status"], "ACTIVE")
        self.assertIn("Waits for G-ROUNDS", gate["detail"])
        self.panel(root)
        self.round(root, 1, ROUND_1)
        self.round(root, 2, ROUND_2)
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-ANALYSIS")["status"], "PASS")
        self.assertIn("no MICMAC analysis recorded", self.phase(status, "coding_consensus")["detail"])
        self.micmac(root)
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-ANALYSIS")["status"], "PASS")
        self.assertIn("MICMAC analysis current, computed by Ana Ruiz", self.phase(status, "coding_consensus")["detail"])
        self.write(root, "data/matrix.csv", "\n".join(MATRIX[:-1]) + "\nD,0,0,0,0\n")
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-ANALYSIS")["status"], "ACTIVE")
        self.assertIn("the influence matrix changed since it was computed",
                      self.phase(status, "coding_consensus")["detail"])

    def test_an_experience_report_passes_as_not_applicable(self) -> None:
        root = self.workspace()
        self.agree(root, "experience-report")
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-ANALYSIS")["status"], "PASS")
        step = self.phase(status, "coding_consensus")
        self.assertEqual(step["status"], "PASS")
        self.assertIn("Not applicable to an experience report: the reflection is the paper's own text", step["detail"])

    def test_with_no_variant_the_signoff_is_required_and_says_so(self) -> None:
        root = self.workspace()
        gate = self.phase(self.status(root), "coding_consensus")["subfases"][1]
        self.assertEqual(gate["status"], "PENDING")
        self.assertIn(NO_VARIANT, gate["detail"])


# --------------------------------------------------------------------------- locks


class LockTests(QualBoardCase):
    def test_the_phase_gates_of_the_line(self) -> None:
        board = lines.board(KIND)
        self.assertEqual(dict(board.phase_gates), {"writing": "G-ANALYSIS"})
        self.assertEqual(board.transversal, "reporting_qualitative")
        self.assertEqual(board.ungated, frozenset({"harness", "reporting_qualitative"}))

    def test_writing_of_a_qualitative_study_waits_for_every_gate(self) -> None:
        root = self.workspace()
        self.agree(root, "qualitative-mixed")
        self.approved(root)
        self.transcript(root)
        self.codebook(root)
        self.themes(root)
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-ANALYSIS")["status"], "PASS")
        writing = self.phase(status, "writing")
        self.assertFalse(writing["unlocked"])
        self.assertEqual(writing["blocked_by"], "Fase 7")
        self.assertIn("Waits for the gates before the writing: G-ETHICS", self.phase(status, "integration")["detail"])
        self.ethics(root)
        status = self.status(root)
        self.assertEqual(self.phase(status, "integration")["status"], "PASS")
        self.assertTrue(self.phase(status, "writing")["unlocked"], self.phase(status, "writing")["blocked_by"])
        # A changed transcript locks the writing again (G-TRANSCRIPTS and the sign-off go stale).
        self.write(root, "data/p01.txt", "edited\n")
        self.assertFalse(self.phase(self.status(root), "writing")["unlocked"])

    def test_writing_of_a_consensus_study_waits_for_its_rounds(self) -> None:
        root = self.workspace()
        self.agree(root, "consensus-foresight")
        self.approved(root)
        self.ethics(root)
        self.plan(root)
        self.panel(root)
        self.round(root, 1, ROUND_1)
        writing = self.phase(self.status(root), "writing")
        self.assertFalse(writing["unlocked"])
        self.round(root, 2, ROUND_2)
        status = self.status(root)
        self.assertTrue(self.phase(status, "writing")["unlocked"], self.phase(status, "writing")["blocked_by"])
        self.assertNotEqual(self.gate(status, "G-TRANSCRIPTS")["status"], "PENDING")

    def test_writing_of_an_experience_report_waits_only_for_its_ethics_record(self) -> None:
        root = self.workspace()
        self.agree(root, "experience-report")
        self.assertFalse(self.phase(self.status(root), "writing")["unlocked"])
        self.approved(root)
        self.study(root, "ethics", "record", "--by", "Ana Ruiz", "--not-applicable", "--reason",
                   "no participant data")
        status = self.status(root)
        self.assertTrue(self.phase(status, "writing")["unlocked"], self.phase(status, "writing")["blocked_by"])

    def test_with_no_variant_the_writing_waits_for_the_transcripts(self) -> None:
        root = self.workspace()
        self.approved(root)
        self.ethics(root)
        status = self.status(root)
        self.assertFalse(self.phase(status, "writing")["unlocked"])
        self.assertIn("G-TRANSCRIPTS", self.phase(status, "integration")["detail"])


# --------------------------------------------------------------------------- checklist, read-only, cards


class ChecklistTests(QualBoardCase):
    def test_the_variant_chooses_the_checklist(self) -> None:
        for variant, guideline, items in (("qualitative-mixed", "srqr", 21), ("consensus-foresight", "accord", 35)):
            with self.subTest(variant=variant):
                root = self.workspace()
                sub = self.phase(self.status(root), "reporting_qualitative")["subfases"][0]
                self.assertIn("No variant agreed yet", sub["detail"])
                self.agree(root, variant)
                subfases = self.phase(self.status(root), "reporting_qualitative")["subfases"]
                self.assertEqual(subfases[0]["name"], f"Reporting checklist ({guideline})")
                self.assertIn(f"{items} items", subfases[0]["detail"])
                names = [s["name"] for s in subfases]
                self.assertIn("Verbatim quotes (qual_cli.py quotes check, paper_cli.py verify)", names)
                self.assertEqual("Reporting checklist (coreq), the alternative for interviews or focus groups" in names,
                                 variant == "qualitative-mixed")

    def test_an_experience_report_has_no_checklist(self) -> None:
        root = self.workspace()
        self.agree(root, "experience-report")
        sub = self.phase(self.status(root), "reporting_qualitative")["subfases"][0]
        self.assertEqual(sub["name"], "Reporting checklist")
        self.assertIn("An experience report has no reporting checklist", sub["detail"])


class ReadOnlyAndCardTests(QualBoardCase):
    def test_the_board_never_writes_a_record(self) -> None:
        root = self.workspace()
        self.qualitative_study(root)
        self.plan(root)
        self.panel(root)
        self.round(root, 1, ROUND_1)
        self.micmac(root)
        watched = ["study", "protocol", "analysis", "data", "paper", ".papersmith/paper_type.json"]

        def snapshot() -> dict:
            out = {}
            for rel in watched:
                folder = root / rel
                paths = [folder] if folder.is_file() else sorted(p for p in folder.rglob("*") if p.is_file())
                out.update({p.relative_to(root).as_posix(): p.read_bytes() for p in paths})
            return out

        before = snapshot()
        self.assertIn("study/transcripts.json", before)
        self.assertIn("study/consensus/rounds.json", before)
        for variant in ("qualitative-mixed", "consensus-foresight", "experience-report"):
            self.run_cli(root, PAPER_TYPE, "agree", "--root", str(root), "--type", KIND, "--variant", variant,
                         "--by", "Ana Ruiz")
            before = snapshot()
            self.status(root)
            self.status(root, "es")
            TestClient(server.create_app(root)).post("/api/phase/run", json={"phase_id": "Fase 5"})
            self.assertEqual(snapshot(), before, variant)

    def test_no_transcript_text_response_or_comment_reaches_the_board(self) -> None:
        root = self.workspace()
        self.qualitative_study(root)
        self.write(root, "study/p09.txt", TRANSCRIPT.replace("P01", "P09"))
        self.qual(root, "transcripts", "add", "--file", "study/p09.txt", "--participant", "P09", "--consent",
                  "oral", "--deidentified", "coded", "--by", "Ana Ruiz")
        self.plan(root)
        self.panel(root)
        self.write(root, "study/round1.csv", "member,item,rating,comment\n" + "\n".join(ROUND_1) + "\n")
        self.consensus(root, "round", "record", "--round", "1", "--file", "study/round1.csv", "--by", "Ana Ruiz")
        self.round(root, 2, ROUND_2)
        client = TestClient(server.create_app(root))
        for variant in ("qualitative-mixed", "consensus-foresight", "experience-report"):
            self.run_cli(root, PAPER_TYPE, "agree", "--root", str(root), "--type", KIND, "--variant", variant,
                         "--by", "Ana Ruiz")
            for lang in ("", "es"):
                with self.subTest(variant=variant, lang=lang):
                    text = json.dumps(self.status(root, lang))
                    self.assertNotIn(TRANSCRIPT_TOKEN, text)
                    self.assertNotIn(COMMENT_TOKEN, text)
                    self.assertNotIn("we carry it to the farms", text)
                    self.assertNotIn("study/p09.txt", text)  # a transcript kept under study/ is never an artifact
                    self.assertNotIn("study/round1.csv", text)
            for number in range(1, len(STEPS) + 1):
                body = json.dumps(client.post("/api/phase/run", json={"phase_id": f"Fase {number}"}).json())
                self.assertNotIn(TRANSCRIPT_TOKEN, body)
                self.assertNotIn(COMMENT_TOKEN, body)
        artifacts = {a["rel_path"] for a in empirical_board.artifacts(root)}
        self.assertIn("study/transcripts.json", artifacts)
        self.assertIn("study/consensus/rounds.json", artifacts)
        self.assertNotIn("study/p09.txt", artifacts)

    def test_a_full_study_passes_every_operator_gate_per_variant(self) -> None:
        root = self.workspace()
        self.qualitative_study(root)
        status = self.status(root)
        for gate in LINE_GATES:
            with self.subTest(variant="qualitative-mixed", gate=gate):
                self.assertEqual(self.gate(status, gate)["status"], "PASS")
        self.assertTrue(self.phase(status, "writing")["unlocked"])
        root = self.workspace()
        self.consensus_study(root)
        self.micmac(root)
        status = self.status(root)
        for gate in CONSENSUS_GATES:
            with self.subTest(variant="consensus-foresight", gate=gate):
                self.assertEqual(self.gate(status, gate)["status"], "PASS")
        self.assertTrue(self.phase(status, "writing")["unlocked"])

    def test_a_phase_check_answers_with_its_step(self) -> None:
        root = self.workspace()
        client = TestClient(server.create_app(root))
        body = client.post("/api/phase/run", json={"phase_id": "Fase 5"}).json()
        self.assertEqual(body["stage"], "fieldwork")
        self.assertIn("Phase 5: it runs from its card", body["message"])
        self.assertEqual(client.post("/api/phase/run", json={"phase_id": "Fase 11"}).status_code, 422)
        self.assertEqual(lines.board(KIND).stage_for("integration"), "integration")
        self.assertEqual(client.get("/api/flow").status_code, 200)

    def test_every_card_runs_a_real_command(self) -> None:
        root = self.workspace()
        clis = {
            "python skills/_core/empirical/study_cli.py": "skills/_core/empirical/study_cli.py",
            "python skills/_core/qualitative/qual_cli.py": "skills/_core/qualitative/qual_cli.py",
            "python skills/_core/qualitative/consensus_cli.py": "skills/_core/qualitative/consensus_cli.py",
            "python skills/_core/checklists/checklist_cli.py": "skills/_core/checklists/checklist_cli.py",
        }
        board = lines.board(KIND)
        for stage in board.stages:
            for action in board.actions[stage]["actions"]:
                with self.subTest(stage=stage, action=action["label"]):
                    if action["kind"] == "prompt":
                        self.assertTrue(action["guide"])
                        name = action["slash"].lstrip("/")
                        self.assertTrue((root / ".claude" / "commands" / f"{name}.md").is_file(), name)
                    elif action["kind"] == "redirect":
                        self.assertIn(action["tab"], TABS)
                    else:
                        words = shlex.split(action["command"])
                        if words[0] == "smith":
                            self.assertIn(words[1], {"status", "audit"})
                            continue
                        prefix = " ".join(words[:2])
                        self.assertIn(prefix, clis)
                        self.assertEqual(base.CardTests._parse(root / clis[prefix], words[2:]), "parsed",
                                         action["command"])
        self.assertEqual(set(board.actions), set(board.stages))
        self.assertEqual(set(board.evidence), set(board.stages))

    def test_every_operator_record_names_the_operator(self) -> None:
        board = lines.board(KIND)
        commands = [a["command"] for stage in board.stages for a in board.actions[stage]["actions"]
                    if a["kind"] == "command" and re.search(r" (approve|amend|record|add|signoff|compute) ",
                                                            a["command"] + " ")]
        self.assertGreaterEqual(len(commands), 11)
        for command in commands:
            with self.subTest(command=command):
                self.assertRegex(command, r'--by "<operator name>"')


# --------------------------------------------------------------------------- Spanish


class SpanishTests(QualBoardCase):
    def test_every_label_has_a_spanish_entry(self) -> None:
        for variant in (None, "qualitative-mixed", "consensus-foresight", "experience-report"):
            root = self.workspace()
            states = {
                "empty": lambda: None,
                "agreed": lambda: self.agree(root, variant) if variant else None,
                "revision": lambda: self.revision(root, 1),
                "approved": lambda: self.study(root, "protocol", "approve", "--by", "Ana Ruiz"),
                "ethics": lambda: self.ethics(root),
                "transcripts": lambda: (self.transcript(root), self.transcript(root, "P02")),
                "codebook": lambda: self.codebook(root),
                "themes": lambda: self.themes(root),
                "plan": lambda: self.plan(root),
                "panel": lambda: self.panel(root),
                "round 1": lambda: self.round(root, 1, ROUND_1),
                "round 2": lambda: self.round(root, 2, ROUND_2),
                "micmac": lambda: self.micmac(root),
                "stale": lambda: (self.write(root, "data/p02.txt", "edited\n"), (root / "data/p01.txt").unlink(),
                                  self.write(root, "data/round1.csv", "member,item,rating,comment\nE01,I1,1,\n"),
                                  self.write(root, "data/matrix.csv", "x,A\nA,0\n"),
                                  self.write(root, "analysis/themes.md", "changed\n")),
                "amended": lambda: (self.revision(root, 2),
                                    self.study(root, "protocol", "amend", "--by", "Ana Ruiz", "--reason", "more")),
                "corrupt": lambda: (self.write(root, "study/transcripts.json", "{x"),
                                    self.write(root, "study/consensus/rounds.json", "{x"),
                                    self.write(root, "study/themes.json", "{x")),
            }
            for name, step in states.items():
                step()
                with self.subTest(variant=variant, state=name):
                    self.assertEqual(self.spanish_gaps(self.status(root)), [])

    def test_an_experience_report_without_a_protocol_reads_in_spanish(self) -> None:
        root = self.workspace()
        self.agree(root, "experience-report")
        self.assertEqual(self.spanish_gaps(self.status(root)), [])
        self.transcript(root)
        self.write(root, "data/p01.txt", "edited\n")
        self.assertEqual(self.spanish_gaps(self.status(root)), [])

    def test_the_new_texts_have_exact_entries(self) -> None:
        catalogue = json.loads(localize.CATALOGUE.read_text(encoding="utf-8"))
        table = empirical_board.LINE_TABLES[KIND]
        for stage in table.steps:
            step = empirical_board.STEPS[stage]
            with self.subTest(stage=stage):
                self.assertIn(f"Phase {{n}}: {step.title}", catalogue)
                self.assertIn(step.label, catalogue)
                self.assertIn(step.desc, catalogue)
                for label, _ in step.evidence:
                    self.assertIn(label, catalogue)
                for action in step.actions["actions"]:
                    for text in (action["label"], action.get("desc") or action["label"], *action.get("guide", ()),
                                 *((action["placeholder"],) if action.get("placeholder") else ())):
                        self.assertIn(text, catalogue)
        for gate in table.gates:
            with self.subTest(gate=gate):
                definition = empirical_board.gate_definition(table, gate)
                self.assertIn(definition.criteria, catalogue)
        for gate in ("G-TRANSCRIPTS", "G-ROUNDS"):
            self.assertIn(empirical_board.GATES[gate].criteria, catalogue)

    def test_the_spanish_reasons_read_as_spanish(self) -> None:
        root = self.workspace()
        self.qualitative_study(root)
        self.write(root, "data/p01.txt", "edited\n")
        spanish = self.status(root, "es")
        self.assertIn("transcripción cambiada desde su registro: data/p01.txt (P01)", self.phase(spanish, "fieldwork")["detail"])
        self.assertIn("una transcripción firmada fue reemplazada, cambió o se eliminó",
                      self.phase(spanish, "coding_consensus")["detail"])
        self.assertEqual([f["stage_id"] for f in spanish["fases"]], STEPS)


class OtherBoardsTests(unittest.TestCase):
    def test_the_other_tables_keep_their_gates(self) -> None:
        for kind in ("observational-measurement", "hardware", "lab-simulation", "data-resource",
                     "experiment-intervention"):
            table = empirical_board.LINE_TABLES[kind]
            with self.subTest(kind=kind):
                self.assertIsNone(table.lists_gate)
                self.assertNotIn("G-TRANSCRIPTS", table.gates)
                self.assertNotIn("G-ROUNDS", table.gates)
                for gate in table.gates:
                    if gate not in table.gate_defs:
                        self.assertIs(empirical_board.gate_definition(table, gate), empirical_board.GATES[gate])

    def test_the_line_defines_its_own_gates(self) -> None:
        table = empirical_board.LINE_TABLES[KIND]
        self.assertEqual(sorted(table.gate_defs), sorted(CONSENSUS_GATES))
        self.assertEqual(empirical_board.GATES["G-TRANSCRIPTS"].step, "fieldwork")
        self.assertEqual(empirical_board.GATES["G-ROUNDS"].step, "fieldwork")


if __name__ == "__main__":
    unittest.main()
