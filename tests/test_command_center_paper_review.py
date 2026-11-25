"""The dashboard's final-judge panel: `GET /api/paper/review`.

It reads `.papersmith/paper_review.json` (the paper-reviewer's rounds over the
assembled manuscript) and never writes it; an absent, malformed or oversized
file is reported in `status`, never raised.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
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


STATIC = Path(server.__file__).parent / "static"
# Loads the panel script with a stub DOM, renders a state and clicks the judge
# button once per entry of `clicks`, recording what reaches the agent terminal.
PANEL = r"""
const fs = require('fs'); const path = require('path');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const calls = [];
global.window = { sendToCli: (text, run, options) => { calls.push([text, run, options.kind]); return true; } };
global.document = { readyState: 'complete', addEventListener() {}, getElementById: () => null };
global.fetch = async () => ({ json: async () => input.state });
eval(fs.readFileSync(path.join(process.argv[1], 'paper-review-panel.js'), 'utf8'));
const html = window.PaperReviewPanel.render(input.state);
for (let i = 0; i < input.clicks; i += 1) window.launchPaperJudge();
process.stdout.write(JSON.stringify({ html, calls }));
"""


def render_panel(state: dict, clicks: int = 0) -> dict:
    out = subprocess.run(["node", "-e", PANEL, str(STATIC)], input=json.dumps({"state": state, "clicks": clicks}),
                         capture_output=True, text=True, cwd=tempfile.gettempdir(), check=True)
    return json.loads(out.stdout)


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class JudgeButtonTests(unittest.TestCase):
    def test_without_rounds_the_button_launches_the_first_round(self) -> None:
        result = render_panel({"status": "absent", "rounds": []}, clicks=1)
        self.assertIn('onclick="window.launchPaperJudge()"', result["html"])
        self.assertIn("review.launch", result["html"])
        self.assertIn("review.empty", result["html"])
        self.assertEqual(len(result["calls"]), 1)
        text, run, kind = result["calls"][0]
        self.assertTrue(text.startswith("/paper-writing "))
        self.assertIn("paper-reviewer", text)
        self.assertIn("paper_cli.py review --input", text)
        self.assertIn("round 1", text)
        self.assertNotIn("previous round", text)
        self.assertEqual((run, kind), (False, "slash"))

    def test_after_a_round_it_launches_the_next_one_against_its_revisions(self) -> None:
        result = render_panel({"status": "ok", "rounds": [ROUND]}, clicks=1)
        self.assertIn("review.launchAgain", result["html"])
        self.assertIn("Round", result["html"].replace("review.round", "Round"))
        text = result["calls"][0][0]
        self.assertIn("round 4", text)
        self.assertIn("every revision the previous round raised", text)

    def test_an_unreadable_file_offers_no_button(self) -> None:
        result = render_panel({"status": "invalid", "rounds": []}, clicks=1)
        self.assertNotIn("launchPaperJudge", result["html"])
        self.assertEqual(result["calls"], [])

    def test_both_catalogues_carry_the_button_labels(self) -> None:
        for name in ("en.js", "es.js"):
            text = (STATIC / "i18n" / name).read_text(encoding="utf-8")
            for key in ("review.launch", "review.launchAgain", "review.launchHint"):
                with self.subTest(file=name, key=key):
                    self.assertIn(f'"{key}":', text)


if __name__ == "__main__":
    unittest.main()
