"""The final judge's rubric per paper line (paper-type-lines S6, T6d).

A round declares its rubric: `ml-conference` (the default when `rubric` is
absent, the main-track form of a machine-learning conference) or
`systematic-review` (AMSTAR 2, Shea et al., 2017, BMJ 358:j4008, plus the
PRISMA 2020 reporting gaps, Page et al., 2021, BMJ 372:n71). For the
systematic-review rubric `paper_cli.py review` derives the overall confidence
from the AMSTAR 2 answers itself; an asserted rating that disagrees with the
rule is refused. A refused round leaves `.papersmith/paper_review.json` byte
for byte as it was.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from skills._core.command_center import server

FORGE_ROOT = Path(__file__).resolve().parents[1]
CLI = FORGE_ROOT / "skills" / "paper-writing" / "scripts" / "paper_cli.py"
STATIC = Path(server.__file__).resolve().parent / "static"

CRITICAL = (2, 4, 7, 9, 11, 13, 15)


def ml_round(**overrides) -> dict:
    data = {
        "overall": 4, "confidence": 3, "recommendation": "Borderline accept",
        "ratings": {"Quality": 3, "Clarity": 2, "Significance": 3, "Originality": 3},
        "revisions": [{"rank": 1, "text": "Report variance across the five seeds.", "note": None}],
        "excluded": ["Appendix C"],
        "report": "Summary: ... (full review form)",
    }
    data.update(overrides)
    return data


def amstar(no=(), partial=(), na=()) -> list[dict]:
    def answer(item: int) -> str:
        if item in no:
            return "no"
        if item in partial:
            return "partial yes"
        if item in na:
            return "not applicable"
        return "yes"
    return [{"item": i, "answer": answer(i), "justification": f"Methods section, item {i}."} for i in range(1, 17)]


def review_round(**overrides) -> dict:
    data = {
        "rubric": "systematic-review",
        "recommendation": "Major revision",
        "amstar2": amstar(),
        "prisma_gaps": [{"item": 24, "gap": "The registration number is not given."}],
        "revisions": [{"rank": 1, "text": "State the protocol registration."}],
        "report": "AMSTAR 2 appraisal and PRISMA 2020 reporting check: ...",
    }
    data.update(overrides)
    return data


class RubricRecordTests(unittest.TestCase):
    def setUp(self) -> None:
        # `paper_cli.py` refuses a paper outside the repository, so the workspace
        # lives under the git-ignored `.scratch/` and is removed after the test.
        scratch = FORGE_ROOT / ".scratch"
        scratch.mkdir(exist_ok=True)
        self.root = Path(tempfile.mkdtemp(prefix=".paper-review-rubric-", dir=scratch))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.paper_dir = self.root / "paper"
        self.paper_dir.mkdir(parents=True)
        self.file = self.root / ".papersmith" / "paper_review.json"

    def record(self, payload) -> tuple[int, dict]:
        source = self.root / f"round-{uuid.uuid4().hex[:6]}.json"
        source.write_text(json.dumps(payload), encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(CLI), "review", "--paper", str(self.paper_dir), "--input", str(source)],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(proc.stderr, "")
        return proc.returncode, json.loads(proc.stdout)

    def rounds(self) -> list:
        return json.loads(self.file.read_text(encoding="utf-8"))["rounds"]

    def assertRefusedUnchanged(self, payload, fragment: str, code: str = "REVIEW_ROUND_INVALID") -> None:
        before = self.file.read_bytes() if self.file.exists() else None
        rc, out = self.record(payload)
        self.assertEqual((rc, out["status"], out["code"]), (2, "refused", code), out)
        self.assertIn(fragment, out["detail"])
        after = self.file.read_bytes() if self.file.exists() else None
        self.assertEqual(before, after)

    # --- the default rubric is today's, byte for byte -------------------------

    def test_a_round_without_a_rubric_is_stored_exactly_as_before(self) -> None:
        code, out = self.record(ml_round())
        self.assertEqual((code, out["status"], out["round"], out["pending_revisions"]), (0, "ok", 1, 1))
        entry = self.rounds()[0]
        date = entry["date"]
        self.assertEqual(entry, {
            "round": 1, "date": date, "overall": 4, "confidence": 3, "recommendation": "Borderline accept",
            "ratings": {"Quality": 3, "Clarity": 2, "Significance": 3, "Originality": 3},
            "items": [],
            "revisions": [{"rank": 1, "text": "Report variance across the five seeds.", "status": "pending",
                           "note": ""}],
            "excluded": ["Appendix C"], "report": "Summary: ... (full review form)",
        })
        self.assertEqual(list(entry), ["round", "date", "overall", "confidence", "recommendation", "ratings",
                                       "items", "revisions", "excluded", "report"])

    def test_the_ml_conference_rubric_named_explicitly_is_the_default(self) -> None:
        self.record(ml_round(rubric="ml-conference"))
        self.assertNotIn("rubric", self.rounds()[0])
        self.assertRefusedUnchanged(ml_round(rubric="ml-conference", ratings={"Quality": 3}),
                                    "ratings must hold exactly")

    def test_an_unknown_rubric_is_refused(self) -> None:
        self.assertRefusedUnchanged(ml_round(rubric="neurips"), "rubric must be one of ml-conference, systematic-review")

    # --- the systematic-review rubric -----------------------------------------

    def test_a_review_round_is_stored_with_its_derived_confidence(self) -> None:
        code, out = self.record(review_round(amstar2=amstar(partial=(2, 8), na=(11, 12, 15))))
        self.assertEqual((code, out["status"], out["round"]), (0, "ok", 1))
        entry = self.rounds()[0]
        self.assertEqual(entry["rubric"], "systematic-review")
        self.assertEqual(entry["overall_confidence"], "high")
        self.assertEqual((entry["critical_flaws"], entry["non_critical_weaknesses"]), ([], []))
        self.assertEqual([a["item"] for a in entry["amstar2"]], list(range(1, 17)))
        self.assertEqual([a["item"] for a in entry["amstar2"] if a["critical"]], list(CRITICAL))
        self.assertEqual(entry["amstar2"][1]["answer"], "partial yes")
        self.assertEqual(entry["prisma_gaps"], [{"item": 24, "gap": "The registration number is not given."}])
        self.assertEqual(entry["revisions"][0]["status"], "pending")
        for absent in ("overall", "confidence", "ratings"):
            self.assertNotIn(absent, entry)

    def test_the_overall_confidence_follows_the_amstar2_rule(self) -> None:
        cases = [
            ((), "high"),
            ((1,), "high"),
            ((1, 3), "moderate"),
            ((4,), "low"),
            ((4, 1, 3, 5), "low"),
            ((4, 9), "critically low"),
        ]
        for no, expected in cases:
            with self.subTest(no=no):
                self.file.unlink(missing_ok=True)
                code, _ = self.record(review_round(amstar2=amstar(no=no)))
                entry = self.rounds()[0]
                self.assertEqual((code, entry["overall_confidence"]), (0, expected))
                self.assertEqual(entry["critical_flaws"], sorted(i for i in no if i in CRITICAL))
                self.assertEqual(entry["non_critical_weaknesses"], sorted(i for i in no if i not in CRITICAL))

    def test_an_asserted_confidence_must_match_the_rule(self) -> None:
        self.assertRefusedUnchanged(review_round(amstar2=amstar(no=(7,)), overall_confidence="high"),
                                    'overall_confidence "high" does not match the AMSTAR 2 rule: low')
        code, _ = self.record(review_round(amstar2=amstar(no=(7,)), overall_confidence="low"))
        self.assertEqual(code, 0)

    def test_every_amstar2_item_needs_one_answer_with_a_justification(self) -> None:
        missing = amstar()[:-1]
        self.assertRefusedUnchanged(review_round(amstar2=missing), "amstar2 must answer each item 1-16 once")
        twice = amstar() + [{"item": 3, "answer": "yes", "justification": "again"}]
        self.assertRefusedUnchanged(review_round(amstar2=twice), "amstar2 must answer each item 1-16 once")
        bad = amstar()
        bad[0]["answer"] = "maybe"
        self.assertRefusedUnchanged(review_round(amstar2=bad), "amstar2 item 1 answer must be one of")
        blank = amstar()
        blank[4]["justification"] = " "
        self.assertRefusedUnchanged(review_round(amstar2=blank), "amstar2 item 5 needs a non-empty justification")
        self.assertRefusedUnchanged(review_round(amstar2=None), "amstar2 must answer each item 1-16 once")

    def test_partial_yes_and_not_applicable_only_where_amstar2_offers_them(self) -> None:
        self.assertRefusedUnchanged(review_round(amstar2=amstar(partial=(1,))),
                                    'amstar2 item 1 cannot be "partial yes"')
        self.assertRefusedUnchanged(review_round(amstar2=amstar(na=(9,))),
                                    'amstar2 item 9 cannot be "not applicable"')

    def test_prisma_gaps_name_a_prisma_2020_item(self) -> None:
        self.assertRefusedUnchanged(review_round(prisma_gaps=[{"item": 28, "gap": "x"}]),
                                    "prisma_gaps[1] needs an item 1-27 and non-empty gap text")
        self.assertRefusedUnchanged(review_round(prisma_gaps="none"), "prisma_gaps must be a list")
        code, _ = self.record(review_round(prisma_gaps=[]))
        self.assertEqual(code, 0)

    def test_the_shared_fields_still_apply_to_a_review_round(self) -> None:
        self.assertRefusedUnchanged(review_round(report=""), "report must be non-empty text")
        self.assertRefusedUnchanged(review_round(recommendation=""), "recommendation must be non-empty text")

    def test_a_second_review_round_judges_the_previous_revisions(self) -> None:
        self.record(review_round())
        self.assertRefusedUnchanged(review_round(), "[1]", code="REVIEW_ITEMS_MISSING")
        code, out = self.record(review_round(items=[{"rank": 1, "verdict": "resolved", "evidence": "PROSPERO id."}],
                                             revisions=[]))
        self.assertEqual((code, out["round"]), (0, 2))
        self.assertEqual(self.rounds()[1]["items"][0]["item"], "State the protocol registration.")

    def test_the_dashboard_reads_a_review_round_unchanged(self) -> None:
        self.record(ml_round())
        self.record(review_round(amstar2=amstar(no=(4,)),
                                 items=[{"rank": 1, "verdict": "partly", "evidence": "Seeds listed."}]))
        state = TestClient(server.create_app(self.root)).get("/api/paper/review").json()
        self.assertEqual(state["status"], "ok")
        self.assertEqual(state["rounds"], self.rounds())


HARNESS = r"""
const fs = require('fs');
const els = {};
global.window = {};
global.document = {
  readyState: 'complete', getElementById: (id) => els[id] || (els[id] = { id, innerHTML: '' }),
  addEventListener: () => {},
};
global.fetch = async () => ({ json: async () => ({ status: 'ok', rounds: [] }) });
for (const file of process.argv.slice(1)) eval(fs.readFileSync(file, 'utf8'));
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
console.log(JSON.stringify({ html: window.PaperReviewPanel.render(input) }));
"""


def render(state: dict) -> str:
    done = subprocess.run(["node", "-e", HARNESS, str(STATIC / "paper-review-panel.js")], capture_output=True,
                          text=True, check=True, input=json.dumps(state), cwd=tempfile.gettempdir())
    return json.loads(done.stdout)["html"]


def node_works() -> bool:
    if not shutil.which("node"):
        return False
    try:
        return subprocess.run(["node", "-e", "0"], capture_output=True, timeout=30).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


@unittest.skipUnless(node_works(), "node is not installed or does not run")
class RubricPanelTests(unittest.TestCase):
    """The panel renders either rubric; keys show bare where i18n is not loaded."""

    def test_an_ml_conference_round_renders_its_scores(self) -> None:
        html = render({"status": "ok", "rounds": [{"round": 1, "overall": 4, "confidence": 3,
                                                    "recommendation": "Borderline accept",
                                                    "ratings": {"Quality": 3}, "report": "r"}]})
        self.assertIn("review.overall 4/6", html)
        self.assertIn("review.confidence 3/5", html)
        self.assertIn("Quality 3/4", html)
        self.assertNotIn("review.amstar2", html)

    def test_a_review_round_renders_amstar2_and_the_prisma_gaps_escaped(self) -> None:
        entry = {"round": 1, "rubric": "systematic-review", "recommendation": "Major revision",
                 "overall_confidence": "low", "critical_flaws": [4], "non_critical_weaknesses": [],
                 "amstar2": [{"item": 4, "critical": True, "answer": "no",
                              "justification": "<script>alert(1)</script>"}],
                 "prisma_gaps": [{"item": 24, "gap": "No registration."}], "report": "r"}
        html = render({"status": "ok", "rounds": [entry]})
        self.assertIn("review.amstar2.confidence", html)
        self.assertIn("review.amstar2.level.low", html)
        self.assertIn("review.amstar2.critical", html)
        self.assertIn("No registration.", html)
        self.assertNotIn("<script>alert", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("/6", html)


if __name__ == "__main__":
    unittest.main()
