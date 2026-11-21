"""The dashboard side of the prompt gate: ``POST /api/prompt/check`` scores a
phase prompt deterministically, and ``POST /api/prompt/review`` asks the
headless prompt-reviewer agent for an improved prompt or for clarifying
questions -- only for a prompt that failed the check. The agent runner is
replaced in every test; none starts a real agent CLI."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from skills._core.command_center import prompt_gate, prompt_review, server, tutor

BAD = "hazlo"
GOOD = ("Current EEG motor-imagery classifiers lose accuracy across subjects. "
        "I propose a quantum kernel that aligns subject covariances before classification.")
IMPROVED = ("Current EEG classifiers lose accuracy across subjects. I propose aligning subject "
            "covariances with a quantum kernel before classification, and testing it on motor imagery.")


def improve_turn(**extra):
    return {"reply": "The idea lacks its problem.", "verdict": "improve",
            "issues": ["No problem stated."], "improved_prompt": IMPROVED,
            "preserved_requirements": ["EEG"], "questions": [], **extra}


def clarify_turn():
    return {"reply": "I need the idea.", "verdict": "clarify", "issues": ["No idea given."],
            "improved_prompt": "", "preserved_requirements": [],
            "questions": [{"id": "q1", "question": "Which problem?", "options": ["Cross-subject drift", "Noise"]}]}


class Endpoints(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "workspace"
        self.root.mkdir()
        self.client = TestClient(server.create_app(self.root))

    def post(self, path, body, **headers):
        return self.client.post(path, json=body, headers=headers)

    # ---- /api/prompt/check -------------------------------------------------
    def test_check_scores_the_prompt(self) -> None:
        response = self.post("/api/prompt/check", {"skill": "/plausibility", "text": BAD})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["verdict"], "fail")
        self.assertEqual(body["skill"], "plausibility")
        self.assertEqual(self.post("/api/prompt/check", {"skill": "plausibility", "text": GOOD}).json()["verdict"],
                         "pass")

    def test_check_honours_optional(self) -> None:
        body = self.post("/api/prompt/check", {"skill": "journal-finder", "text": "", "optional": True}).json()
        self.assertEqual(body["verdict"], "pass")

    def test_check_refuses_cross_origin_and_bad_input(self) -> None:
        self.assertEqual(self.post("/api/prompt/check", {"skill": "x", "text": "y"},
                                   origin="https://evil.example").status_code, 403)
        self.assertEqual(self.post("/api/prompt/check", {"text": "y"}).status_code, 422)
        self.assertEqual(self.post("/api/prompt/check", {"skill": "x", "text": "a" * 20001}).status_code, 422)

    # ---- /api/prompt/review ------------------------------------------------
    def test_review_of_a_passing_prompt_never_calls_the_agent(self) -> None:
        with mock.patch.object(tutor, "run_agent") as run:
            body = self.post("/api/prompt/review", {"skill": "plausibility", "text": GOOD}).json()
        run.assert_not_called()
        self.assertEqual(body["verdict"], "pass")

    def test_review_improves_and_rescores(self) -> None:
        with mock.patch.object(tutor, "run_agent", return_value=(improve_turn(), "claude")) as run:
            body = self.post("/api/prompt/review", {"skill": "plausibility", "text": BAD, "language": "es"}).json()
        self.assertEqual(body["verdict"], "improve")
        self.assertEqual(body["improved_prompt"], IMPROVED)
        self.assertEqual(body["agent"], "claude")
        self.assertEqual(body["check"]["verdict"], "fail")
        self.assertEqual(body["improved_check"]["verdict"], "pass")
        system, prompt = run.call_args.args[1], run.call_args.args[2]
        self.assertIn("Prompt Gate", system)  # the skill doctrine (or its fallback) is the system prompt
        self.assertIn(BAD, prompt)
        self.assertIn('"verdict": "fail"', prompt)  # the check travels with the prompt
        self.assertIn("es", prompt)
        self.assertEqual(run.call_args.kwargs["schema"], prompt_review.REVIEW_SCHEMA)
        self.assertEqual(list(self.root.rglob("*")), [], "the review writes nothing")

    def test_review_asks_questions_then_composes_from_answers(self) -> None:
        with mock.patch.object(tutor, "run_agent", return_value=(clarify_turn(), "claude")):
            body = self.post("/api/prompt/review", {"skill": "plausibility", "text": BAD}).json()
        self.assertEqual(body["verdict"], "clarify")
        self.assertEqual(body["questions"][0]["options"], ["Cross-subject drift", "Noise"])
        answers = [{"id": "q1", "question": "Which problem?", "answer": "Cross-subject drift"}]
        with mock.patch.object(tutor, "run_agent", return_value=(improve_turn(), "claude")) as run:
            body = self.post("/api/prompt/review",
                             {"skill": "plausibility", "text": BAD, "answers": answers}).json()
        self.assertEqual(body["verdict"], "improve")
        self.assertEqual(body["improved_prompt"], IMPROVED)
        self.assertIn("Cross-subject drift", run.call_args.args[2])

    def test_answers_that_still_yield_no_prompt_are_refused(self) -> None:
        answers = [{"id": "q1", "question": "Which problem?", "answer": "?"}]
        with mock.patch.object(tutor, "run_agent", return_value=(clarify_turn(), "claude")):
            response = self.post("/api/prompt/review", {"skill": "plausibility", "text": BAD, "answers": answers})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["verdict"], "clarify")

    def test_an_unavailable_agent_degrades_to_the_check(self) -> None:
        with mock.patch.object(tutor, "run_agent", side_effect=tutor.TutorError("no agent CLI found")):
            body = self.post("/api/prompt/review", {"skill": "plausibility", "text": BAD}).json()
        self.assertFalse(body["available"])
        self.assertIn("no agent CLI", body["reason"])
        self.assertEqual(body["check"]["verdict"], "fail")

    def test_a_malformed_turn_is_unavailable_not_a_crash(self) -> None:
        for turn in (None, {"reply": "x", "verdict": "improve", "improved_prompt": ""}, {"verdict": "maybe"}):
            with self.subTest(turn=turn), mock.patch.object(tutor, "run_agent", return_value=(turn, "pi")):
                body = self.post("/api/prompt/review", {"skill": "plausibility", "text": BAD}).json()
                self.assertFalse(body["available"])

    def test_questions_are_bounded(self) -> None:
        turn = clarify_turn()
        turn["questions"] = [{"id": f"q{i}", "question": f"Q{i}?", "options": [str(j) for j in range(7)]}
                             for i in range(6)]
        with mock.patch.object(tutor, "run_agent", return_value=(turn, "claude")):
            body = self.post("/api/prompt/review", {"skill": "plausibility", "text": BAD}).json()
        self.assertEqual(len(body["questions"]), 4)
        self.assertTrue(all(len(q["options"]) <= 4 for q in body["questions"]))

    def test_review_refuses_cross_origin(self) -> None:
        self.assertEqual(self.post("/api/prompt/review", {"skill": "x", "text": "y"},
                                   origin="https://evil.example").status_code, 403)

    def test_the_marker_is_what_an_approval_appends(self) -> None:
        self.assertEqual(prompt_review.approved(IMPROVED), f"{IMPROVED} {prompt_gate.APPROVED_MARKER}")


if __name__ == "__main__":
    unittest.main()
