"""The dashboard's final-judge panel: `GET /api/paper/review`.

It reads `.papersmith/paper_review.json` (the paper-reviewer's rounds over the
assembled manuscript) and never writes it; an absent, malformed or oversized
file is reported in `status`, never raised.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from skills._core.command_center import server

ROUND = {"round": 3, "overall": 5, "confidence": 4, "recommendation": "Accept",
         "ratings": {"Quality": 3}, "items": [{"item": "1", "verdict": "resolved"}],
         "revisions": [{"rank": 1, "text": "References", "status": "applied"}], "report": "text"}


class PaperReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.root = Path(holder.name).resolve() / "ws"
        (self.root / ".papersmith").mkdir(parents=True)
        self.client = TestClient(server.create_app(self.root))
        self.file = self.root / ".papersmith" / "paper_review.json"

    def get(self) -> dict:
        response = self.client.get("/api/paper/review")
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_an_absent_file_answers_no_rounds(self) -> None:
        self.assertEqual(self.get(), {"status": "absent", "rounds": []})

    def test_every_round_is_returned_with_its_fields(self) -> None:
        self.file.write_text(json.dumps({"rounds": [ROUND, "not a round"]}), encoding="utf-8")
        state = self.get()
        self.assertEqual(state["status"], "ok")
        self.assertEqual(state["rounds"], [ROUND])

    def test_malformed_json_is_reported_not_raised(self) -> None:
        self.file.write_text("{", encoding="utf-8")
        self.assertEqual(self.get(), {"status": "invalid", "rounds": []})

    def test_rounds_that_are_not_a_list_are_invalid(self) -> None:
        self.file.write_text(json.dumps({"rounds": {}}), encoding="utf-8")
        self.assertEqual(self.get()["status"], "invalid")

    def test_an_oversized_file_is_not_read(self) -> None:
        with self.file.open("wb") as handle:
            handle.truncate(server.PAPER_REVIEW_MAX_BYTES + 1)
        self.assertEqual(self.get(), {"status": "too_large", "rounds": []})

    def test_a_symlink_out_of_the_workspace_is_not_followed(self) -> None:
        outside = self.root.parent / "outside.json"
        outside.write_text(json.dumps({"rounds": [ROUND]}), encoding="utf-8")
        os.symlink(outside, self.file)
        state = self.get()
        self.assertEqual(state["rounds"], [])
        self.assertNotEqual(state["status"], "ok")

    def test_the_page_loads_the_panel_script(self) -> None:
        index = (Path(server.__file__).parent / "static" / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="paperReviewPanel"', index)
        self.assertIn("paper-review-panel.js", index)


if __name__ == "__main__":
    unittest.main()
