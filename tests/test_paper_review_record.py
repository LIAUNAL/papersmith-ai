"""`paper_cli.py review --input <round.json>`: the writer of the final judge's rounds.

The `paper-reviewer` agent returns its review of the assembled manuscript to
`/paper-writing`, which records it with this verb in
`.papersmith/paper_review.json`; the dashboard's final-judge panel
(`GET /api/paper/review`) only reads that file. A refused round leaves the file
byte for byte as it was.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import unittest
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

FORGE_ROOT = Path(__file__).resolve().parents[1]
CLI = FORGE_ROOT / "skills" / "paper-writing" / "scripts" / "paper_cli.py"

from skills._core.command_center import server  # noqa: E402


def first_round(**overrides) -> dict:
    data = {
        "overall": 4, "confidence": 3, "recommendation": "Borderline accept",
        "ratings": {"Quality": 3, "Clarity": 2, "Significance": 3, "Originality": 3},
        "revisions": [
            {"rank": 1, "text": "Report variance across the five seeds."},
            {"rank": 2, "text": "Quote the closest prior method in the introduction."},
        ],
        "report": "Summary: ... (full review form)",
    }
    data.update(overrides)
    return data


def second_round(**overrides) -> dict:
    data = {
        "overall": 5, "confidence": 4, "recommendation": "Accept",
        "ratings": {"Quality": 3, "Clarity": 3, "Significance": 3, "Originality": 3},
        "items": [
            {"rank": 1, "verdict": "resolved", "evidence": "Table 2 now lists mean and std."},
            {"rank": 2, "verdict": "partly", "evidence": "Cited but not quoted."},
        ],
        "revisions": [{"rank": 1, "text": "Quote the closest prior method."}],
        "report": "Second pass.",
    }
    data.update(overrides)
    return data


class PaperReviewRecordTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = FORGE_ROOT / ".scratch" / f".paper-review-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.paper_dir = self.root / "paper"
        self.paper_dir.mkdir(parents=True)
        self.file = self.root / ".papersmith" / "paper_review.json"

    def record(self, payload) -> tuple[int, dict]:
        source = self.root / f"round-{uuid.uuid4().hex[:6]}.json"
        text = payload if isinstance(payload, str) else json.dumps(payload)
        source.write_text(text, encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(CLI), "review", "--paper", str(self.paper_dir), "--input", str(source)],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(proc.stderr, "")
        return proc.returncode, json.loads(proc.stdout)

    def rounds(self) -> list:
        return json.loads(self.file.read_text(encoding="utf-8"))["rounds"]

    def test_the_first_round_is_numbered_dated_and_written(self) -> None:
        code, out = self.record(first_round())
        self.assertEqual((code, out["status"], out["round"]), (0, "ok", 1))
        stored = self.rounds()
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0]["round"], 1)
        self.assertRegex(stored[0]["date"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertEqual(stored[0]["overall"], 4)
        self.assertEqual(stored[0]["items"], [])
        self.assertEqual([r["status"] for r in stored[0]["revisions"]], ["pending", "pending"])

    def test_a_second_round_judges_every_revision_of_the_first(self) -> None:
        self.record(first_round())
        code, out = self.record(second_round())
        self.assertEqual((code, out["round"]), (0, 2))
        stored = self.rounds()
        self.assertEqual([r["round"] for r in stored], [1, 2])
        items = stored[1]["items"]
        self.assertEqual(items[0]["item"], "Report variance across the five seeds.")
        self.assertEqual(items[1]["verdict"], "partly")
        self.assertEqual(stored[0]["revisions"][0]["status"], "pending")

    def test_the_dashboard_reads_what_was_recorded(self) -> None:
        self.record(first_round())
        self.record(second_round())
        state = TestClient(server.create_app(self.root)).get("/api/paper/review").json()
        self.assertEqual(state["status"], "ok")
        self.assertEqual([r["round"] for r in state["rounds"]], [1, 2])

    def assertRefusedUnchanged(self, payload, code: str) -> None:
        before = self.file.read_bytes() if self.file.exists() else None
        rc, out = self.record(payload)
        self.assertEqual((rc, out["status"], out["code"]), (2, "refused", code), out)
        after = self.file.read_bytes() if self.file.exists() else None
        self.assertEqual(before, after)

    def test_an_out_of_range_score_is_refused(self) -> None:
        self.assertRefusedUnchanged(first_round(overall=7), "REVIEW_ROUND_INVALID")

    def test_a_missing_rating_is_refused(self) -> None:
        self.assertRefusedUnchanged(first_round(ratings={"Quality": 3}), "REVIEW_ROUND_INVALID")

    def test_malformed_json_is_refused(self) -> None:
        self.assertRefusedUnchanged("{", "REVIEW_INPUT_UNREADABLE")

    def test_a_first_round_cannot_judge_items(self) -> None:
        self.assertRefusedUnchanged(first_round(items=[{"rank": 1, "verdict": "resolved"}]),
                                    "REVIEW_ITEM_UNKNOWN")

    def test_a_verdict_on_an_unraised_item_is_refused(self) -> None:
        self.record(first_round())
        items = second_round()["items"] + [{"rank": 9, "verdict": "resolved"}]
        self.assertRefusedUnchanged(second_round(items=items), "REVIEW_ITEM_UNKNOWN")

    def test_a_second_round_must_judge_every_previous_revision(self) -> None:
        self.record(first_round())
        self.assertRefusedUnchanged(second_round(items=second_round()["items"][:1]), "REVIEW_ITEMS_MISSING")

    def test_a_malformed_review_file_is_never_overwritten(self) -> None:
        self.file.parent.mkdir(parents=True)
        self.file.write_text("{", encoding="utf-8")
        self.assertRefusedUnchanged(first_round(), "REVIEW_FILE_INVALID")


    def test_a_review_file_with_a_non_object_round_is_never_rewritten(self) -> None:
        self.file.parent.mkdir(parents=True)
        self.file.write_text(json.dumps({"rounds": [{"round": 1}, "not a round"]}), encoding="utf-8")
        self.assertRefusedUnchanged(first_round(), "REVIEW_FILE_INVALID")

    def test_two_verdicts_on_one_revision_are_refused(self) -> None:
        self.record(first_round())
        items = second_round()["items"] + [{"rank": 1, "verdict": "not resolved"}]
        self.assertRefusedUnchanged(second_round(items=items), "REVIEW_ROUND_INVALID")

    def test_a_null_note_or_evidence_is_stored_as_empty_text(self) -> None:
        self.record(first_round(revisions=[{"rank": 1, "text": "Add seeds.", "note": None}]))
        self.record(second_round(items=[{"rank": 1, "verdict": "resolved", "evidence": None}]))
        stored = self.rounds()
        self.assertEqual(stored[0]["revisions"][0]["note"], "")
        self.assertEqual(stored[1]["items"][0]["evidence"], "")

if __name__ == "__main__":
    unittest.main()
