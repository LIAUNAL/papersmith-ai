"""The per-block judge loop of `paper_cli.py write`, through its front door.

The rule (odd/tasks/efficiency-stage-b.md, S4): fewer blind redrafts with
the same or a stronger gate. The deterministic checks run before any LLM
judge (`write --precheck`), the contract judge rules on every disqualifier
bullet, the block is written only when every judge passes, exactly one
bounded re-draft is allowed, and after it the loop stops and escalates to
the operator with the judges' verdicts recorded in the attempt ledger --
never an automatic pass and never another blind redraft.

Every test drives `paper_cli.py write` as a subprocess and asserts its JSON,
its exit code, the bytes of `main.tex` and the attempt ledger on disk. The
fixture paper lives under the gitignored `.scratch/` because `--paper` must
resolve inside the repository; it is removed after each test.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

FORGE_ROOT = Path(__file__).resolve().parents[1]
SKILL_SCRIPTS = FORGE_ROOT / "skills" / "paper-writing" / "scripts"
CLI = SKILL_SCRIPTS / "paper_cli.py"
sys.path.insert(0, str(SKILL_SCRIPTS))
import paper_block  # noqa: E402
import paper_scaffold  # noqa: E402

SECTION_WIDE = "A sentence that names a grant from memory."
BLOCK_SPECIFIC = "Block 2 without its closing statement of conflicts."
BULLETS = (SECTION_WIDE, BLOCK_SPECIFIC)

PROSE = (
    "# Back Matter\n\n"
    "The conflicts block states that the authors declare no conflict of interest.\n\n"
    "### External inputs\n\nNone.\n\n### Internal chain\n\nNone.\n\n"
    "## Disqualifiers\n\n" + "".join(f"- {bullet}\n" for bullet in BULLETS)
)

HEADER = {
    "section": "back-matter",
    "position": 10,
    "mode": {"value": "transposition",
             "source": {"file": "sections/10-back-matter.md", "quote": "The conflicts block"}},
    "blocks": [
        {"id": "bm-conflicts-of-interest", "requires_facts": [], "requires_declarations": [],
         "citations": "none"},
    ],
}

BLOCK = "bm-conflicts-of-interest"
QUALIFIED = f"back-matter.{BLOCK}"
SENTENCE = "The authors declare no conflict of interest."
CLEAN = [(SENTENCE, "structural")]
CLEAR_ALL = [{"bullet": bullet, "verdict": "clear"} for bullet in BULLETS]
FIRES = [{"bullet": SECTION_WIDE, "verdict": "fires", "span": "declare no conflict"},
         {"bullet": BLOCK_SPECIFIC, "verdict": "clear"}]


class _Paper(unittest.TestCase):
    """A scaffolded paper with one back-matter block open and empty."""

    def setUp(self) -> None:
        self.root = (FORGE_ROOT / ".scratch"
                     / f".write-loop-test-{os.getpid()}-{uuid.uuid4().hex[:8]}")
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.paper = self.root / "paper"
        paper_scaffold.scaffold(self.paper)
        self.sections = self.root / "sections"
        self.sections.mkdir()
        self.write_contract(PROSE)
        paper_block.open_block(self.paper, QUALIFIED, at_end=True)
        # No harness session store outside this scratch home is ever read.
        self.home = Path(tempfile.mkdtemp(prefix="write-loop-home-"))
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)

    def write_contract(self, prose: str) -> None:
        (self.sections / "10-back-matter.md").write_text(
            "---\n" + json.dumps(HEADER) + "\n---\n" + prose, encoding="utf-8")

    @property
    def ledger(self) -> Path:
        return self.paper / ".paper-writing" / "attempts" / f"{QUALIFIED}.json"

    def _file(self, prefix: str, payload) -> Path:
        path = self.root / f"{prefix}-{uuid.uuid4().hex[:6]}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def run_write(self, entries, verdicts=None, *, precheck: bool = False,
                  grounding: dict | None = None, evidence_text: str | None = None):
        latex = " ".join(sentence for sentence, _binding in entries)
        draft = self._file("draft", {
            "latex": latex,
            "bindings": [{"sentence": s, "binding": b} for s, b in entries if b is not None],
        })
        argv = [sys.executable, str(CLI), "write", "--paper", str(self.paper),
                "--sections", str(self.sections), "--section", "back-matter",
                "--block", BLOCK, "--draft", str(draft)]
        if precheck:
            argv.append("--precheck")
        if verdicts is not None:
            argv += ["--audit", str(self._file("audit", {"verdicts": verdicts}))]
        if grounding is not None:
            argv += ["--grounding", str(self._file("grounding", grounding))]
        if evidence_text is not None:
            evidence = self.root / f"evidence-{uuid.uuid4().hex[:6]}.json"
            evidence.write_text(evidence_text, encoding="utf-8")
            argv += ["--evidence", str(evidence)]
        before = (self.paper / "main.tex").read_bytes()
        env = {key: value for key, value in os.environ.items()
               if key not in ("CLAUDE_CONFIG_DIR", "PI_CODING_AGENT_DIR", "XDG_DATA_HOME")}
        env["HOME"] = str(self.home)
        proc = subprocess.run(argv, capture_output=True, text=True, cwd=FORGE_ROOT, env=env,
                              timeout=120)
        try:
            payload = json.loads(proc.stdout.strip().splitlines()[-1])
        except (IndexError, json.JSONDecodeError):
            payload = {"stdout": proc.stdout, "stderr": proc.stderr}
        return proc.returncode, payload, before, (self.paper / "main.tex").read_bytes()

    def assertRefused(self, outcome, code: str, *needles: str) -> dict:
        returncode, payload, before, after = outcome
        self.assertEqual(payload.get("code"), code, payload)
        self.assertEqual(payload["status"], "refused")
        self.assertEqual(returncode, 2)
        for needle in needles:
            self.assertIn(needle, payload["detail"])
        self.assertEqual(after, before, "a refused write leaves main.tex byte-identical")
        return payload

    def read_ledger(self) -> dict:
        return json.loads(self.ledger.read_text(encoding="utf-8"))


class PrecheckTests(_Paper):
    """S4 (1): every deterministic check `write` runs, before any LLM judge,
    with no audit, no ledger write and no substitution."""

    def test_a_clean_draft_passes_the_precheck_and_lists_every_bullet_to_judge(self) -> None:
        returncode, payload, before, after = self.run_write(CLEAN, precheck=True)
        self.assertEqual(returncode, 0, payload)
        self.assertEqual(payload["status"], "precheck-passed")
        self.assertEqual(payload["block"], QUALIFIED)
        self.assertEqual(payload["attempt"], 1)
        self.assertEqual(payload["disqualifiers"], list(BULLETS))
        self.assertEqual(payload["groundingSubjects"], [])
        self.assertEqual(after, before, "the precheck never substitutes")
        self.assertFalse(self.ledger.exists(), "the precheck never writes the attempt ledger")

    def test_a_spanish_draft_refuses_draft_not_english_before_any_judge(self) -> None:
        self.assertRefused(
            self.run_write([("Los autores declaran que no existe conflicto de interés.",
                             "structural")], precheck=True),
            "DRAFT_NOT_ENGLISH")
        self.assertFalse(self.ledger.exists())

    def test_an_unbound_sentence_refuses_unbound_sentence_before_any_judge(self) -> None:
        self.assertRefused(
            self.run_write([(SENTENCE, "structural"), ("No funding was received.", None)],
                           precheck=True),
            "UNBOUND_SENTENCE")
        self.assertFalse(self.ledger.exists())

    def test_the_precheck_and_an_audit_together_are_an_invocation_error(self) -> None:
        returncode, _payload, before, after = self.run_write(CLEAN, FIRES, precheck=True)
        self.assertEqual(returncode, 2)
        self.assertEqual(after, before)
        self.assertFalse(self.ledger.exists())

    def test_precheck_with_grounding_is_an_invocation_error(self) -> None:
        returncode, _payload, before, after = self.run_write(
            CLEAN, precheck=True, grounding={"support": []})
        self.assertEqual(returncode, 2)
        self.assertEqual(after, before)
        self.assertFalse(self.ledger.exists())

    def test_precheck_while_open_leaves_ledger_bytes_identical(self) -> None:
        self.run_write(CLEAN, FIRES)
        ledger_before = self.ledger.read_bytes()
        returncode, payload, _before, _after = self.run_write(CLEAN, precheck=True)
        self.assertEqual(returncode, 0, payload)
        self.assertEqual(payload["attempt"], 2)
        self.assertEqual(self.ledger.read_bytes(), ledger_before)

    def test_write_without_audit_or_precheck_is_an_invocation_error(self) -> None:
        returncode, _payload, before, after = self.run_write(CLEAN)
        self.assertEqual(returncode, 2)
        self.assertEqual(after, before)
        self.assertFalse(self.ledger.exists())


class EveryBulletIsJudgedTests(_Paper):
    """S4 (3): contracts carry no machine-readable block marker on their
    bullets, so the contract judge still rules on every bullet; a missing
    verdict refuses and spends no attempt."""

    def test_a_missing_verdict_on_a_block_specific_bullet_refuses_verdict_missing(self) -> None:
        self.assertRefused(
            self.run_write(CLEAN, [{"bullet": SECTION_WIDE, "verdict": "clear"}]),
            "VERDICT_MISSING", BLOCK_SPECIFIC)
        self.assertFalse(self.ledger.exists(), "an incomplete account spends no attempt")


class OneBoundedRedraftTests(_Paper):
    """The existing rule still holds: one fired audit, one re-draft."""

    def test_a_first_firing_audit_reports_feedback_and_a_clean_redraft_is_written(self) -> None:
        returncode, payload, before, after = self.run_write(CLEAN, FIRES)
        self.assertEqual(returncode, 0, payload)
        self.assertEqual(payload["status"], "audit-fired")
        self.assertEqual(payload["attempt"], 1)
        self.assertEqual(payload["fired"], [{"bullet": SECTION_WIDE, "span": "declare no conflict"}])
        self.assertEqual(after, before)
        ledger = self.read_ledger()
        self.assertEqual((ledger["attempts"], ledger["state"]), (1, "open"))

        returncode, payload, _before, after = self.run_write(CLEAN, CLEAR_ALL)
        self.assertEqual(returncode, 0, payload)
        self.assertEqual(payload["status"], "written")
        self.assertIn(SENTENCE.encode("utf-8"), after)


class EscalationTests(_Paper):
    """S4 (5): after the one re-draft the loop stops and escalates to the
    operator, recording a terminal state with the judges' verdicts first."""

    def test_a_second_firing_audit_escalates_and_records_the_terminal_state(self) -> None:
        self.run_write(CLEAN, FIRES)
        payload = self.assertRefused(self.run_write(CLEAN, FIRES), "AUDIT_EXHAUSTED",
                                     SECTION_WIDE, "ask the operator")
        self.assertIn("attempt 2", payload["detail"])
        ledger = self.read_ledger()
        self.assertEqual(ledger["state"], "escalated")
        self.assertEqual(ledger["attempts"], 2)
        self.assertEqual(ledger["fired"], [{"bullet": SECTION_WIDE, "span": "declare no conflict"}])
        self.assertEqual([entry["bullet"] for entry in ledger["verdicts"]], list(BULLETS))

    def test_an_escalated_block_refuses_every_later_submission_even_a_clean_one(self) -> None:
        self.run_write(CLEAN, FIRES)
        self.run_write(CLEAN, FIRES)
        self.assertRefused(self.run_write(CLEAN, CLEAR_ALL), "AUDIT_EXHAUSTED",
                           "ask the operator")
        self.assertRefused(self.run_write(CLEAN, precheck=True), "AUDIT_EXHAUSTED",
                           "ask the operator")
        self.assertEqual(self.read_ledger()["state"], "escalated")

    def test_incomplete_audit_on_the_redraft_spends_nothing(self) -> None:
        self.run_write(CLEAN, FIRES)
        self.assertRefused(self.run_write(CLEAN, [{"bullet": SECTION_WIDE, "verdict": "clear"}]),
                           "VERDICT_MISSING")
        ledger = self.read_ledger()
        self.assertEqual((ledger["attempts"], ledger["state"]), (1, "open"))
        returncode, payload, _before, after = self.run_write(CLEAN, CLEAR_ALL)
        self.assertEqual(returncode, 0, payload)
        self.assertEqual(payload["status"], "written")
        self.assertIn(SENTENCE.encode("utf-8"), after)

    def test_escalated_block_refuses_with_whitespace_only_evidence_file(self) -> None:
        self.run_write(CLEAN, FIRES)
        self.run_write(CLEAN, FIRES)
        self.assertRefused(self.run_write(CLEAN, CLEAR_ALL, evidence_text="[ ]\n"),
                           "AUDIT_EXHAUSTED", "ask the operator")

    def test_a_changed_contract_opens_a_new_attempt_budget(self) -> None:
        self.run_write(CLEAN, FIRES)
        self.run_write(CLEAN, FIRES)
        self.write_contract(PROSE.replace("states that", "says that"))
        returncode, payload, _before, _after = self.run_write(CLEAN, FIRES)
        self.assertEqual(returncode, 0, payload)
        self.assertEqual((payload["status"], payload["attempt"]), ("audit-fired", 1))


if __name__ == "__main__":
    unittest.main()
