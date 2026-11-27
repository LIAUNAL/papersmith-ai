"""Board language consistency (odd/tasks/board-language-consistency.md, S2-S4).

Whatever the board shows in English mode is English:

* S2: `paper_type_cli.py accept` records an English idea. Without
  `--idea-file` it takes the approved English idea brief draft
  (`.papersmith/idea_brief.json`); it refuses an idea or a `--by` that reads
  as Spanish prose and names the English draft to use; an English acceptance
  keeps working unchanged.
* S3: the paper-type panel and the empirical board step that show
  `plausibility.idea` and `accepted_by` carry a language notice when the stored
  text is not English, naming the command that re-records the acceptance.
* S4: the board's server defaults are English; a language the board passes
  still reaches the agent and the draft.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from skills._core.command_center import banco_suggest, paper_type_view, prompt_review, server, tutor
from skills._core.idea import draft as idea_draft
from skills._core.paper_types import decision

REPO = Path(__file__).resolve().parents[1]
CLI = [sys.executable, "skills/_core/paper_types/paper_type_cli.py"]
PLAUSIBILITY = Path(".papersmith") / "plausibility.json"

ENGLISH_IDEA = ("Current EEG classifiers lose accuracy across subjects. I propose a neural network architecture "
                "that outperforms the state-of-the-art baselines with a new deep learning algorithm.")
SPANISH_IDEA = ("La idea del artículo es partir desde la adquisición de datos de los sensores y proponer una "
                "arquitectura que mejore la clasificación de las señales.")
SPANISH_BY = "El operador dijo: acepto la idea tal como está en el informe"
RERECORD = 'python skills/_core/paper_types/paper_type_cli.py accept --root . --by "<operator>"'


def run_cli(*args: str, stdin: str = "") -> subprocess.CompletedProcess:
    return subprocess.run([*CLI, *args], cwd=REPO, input=stdin, capture_output=True, text=True, check=False)


class AcceptCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def approve_draft(self, text: str = ENGLISH_IDEA) -> str:
        idea_draft.store(self.root, text)
        return idea_draft.approve(self.root)["text"]

    def accept(self, *extra: str, stdin: str = "") -> tuple[subprocess.CompletedProcess, dict]:
        done = run_cli("accept", "--root", str(self.root), *extra, stdin=stdin)
        return done, json.loads(done.stdout)

    def stored(self) -> dict | None:
        path = self.root / PLAUSIBILITY
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


class AcceptFromTheApprovedDraftTests(AcceptCase):
    """S2 (b): `accept` takes the approved brief draft when `--idea-file` is omitted."""

    def test_accept_without_idea_file_records_the_approved_english_draft(self) -> None:
        text = self.approve_draft()
        done, out = self.accept("--by", "operator")
        self.assertEqual(done.returncode, 0, done.stdout)
        self.assertEqual(done.stderr, "")
        self.assertTrue(out["ok"])
        self.assertEqual(out["plausibility"]["idea"], text)
        stored = self.stored()
        self.assertEqual((stored["idea"], stored["accepted_by"]), (text, "operator"))
        self.assertTrue((self.root / ".papersmith" / "paper_type.json").is_file())

    def test_accept_without_idea_file_and_no_approved_draft_refuses_and_writes_nothing(self) -> None:
        idea_draft.store(self.root, ENGLISH_IDEA)  # recorded, never approved
        done, out = self.accept("--by", "operator")
        self.assertEqual(done.returncode, 1)
        self.assertEqual(done.stderr, "")
        self.assertEqual((out["ok"], out["error"]), (False, "IDEA_ABSENT"))
        self.assertIn("--idea-file", out["message"])
        self.assertIn("smith idea approve", out["message"])
        self.assertIsNone(self.stored())
        self.assertFalse((self.root / ".papersmith" / "paper_type.json").exists())


class AcceptRefusesSpanishTests(AcceptCase):
    """S2 (c): `accept` refuses Spanish prose in the idea or in `--by`."""

    def test_a_spanish_idea_is_refused_naming_the_approved_english_draft(self) -> None:
        self.approve_draft()
        done, out = self.accept("--by", "operator", "--idea-file", "-", stdin=SPANISH_IDEA)
        self.assertEqual(done.returncode, 1)
        self.assertEqual(done.stderr, "")
        self.assertEqual((out["ok"], out["error"]), (False, "IDEA_NOT_ENGLISH"))
        self.assertIn(".papersmith/idea_brief.json", out["message"])
        self.assertIn("draft.text", out["message"])
        self.assertIn("without --idea-file", out["message"])
        self.assertIsNone(self.stored())
        self.assertFalse((self.root / ".papersmith" / "paper_type.json").exists())

    def test_a_spanish_idea_without_a_draft_names_the_draft_to_approve(self) -> None:
        done, out = self.accept("--by", "operator", "--idea-file", "-", stdin=SPANISH_IDEA)
        self.assertEqual((done.returncode, out["error"]), (1, "IDEA_NOT_ENGLISH"))
        self.assertIn(".papersmith/idea_brief.json", out["message"])
        self.assertIn("smith idea approve", out["message"])
        self.assertIsNone(self.stored())

    def test_a_spanish_by_is_refused_the_same_way(self) -> None:
        done, out = self.accept("--by", SPANISH_BY, "--idea-file", "-", stdin=ENGLISH_IDEA)
        self.assertEqual(done.returncode, 1)
        self.assertEqual(done.stderr, "")
        self.assertEqual((out["ok"], out["error"]), (False, "OPERATOR_NOT_ENGLISH"))
        self.assertIn("name or role", out["message"])
        self.assertIsNone(self.stored())
        self.assertFalse((self.root / ".papersmith" / "paper_type.json").exists())

    def test_a_name_with_accents_is_a_name_not_spanish(self) -> None:
        done, out = self.accept("--by", "José Gómez", "--idea-file", "-", stdin=ENGLISH_IDEA)
        self.assertEqual(done.returncode, 0, done.stdout)
        self.assertEqual(self.stored()["accepted_by"], "José Gómez")

    def test_an_english_idea_naming_spanish_places_is_english(self) -> None:
        idea = ("A low-cost air-quality sensor network for the Universidad Nacional de Colombia Sede La Paz "
                "campus in Cesar, compared with the Bogotá and Medellín reference stations.")
        done, out = self.accept("--by", "María Gómez", "--idea-file", "-", stdin=idea)
        self.assertEqual(done.returncode, 0, done.stdout)
        self.assertEqual(done.stderr, "")
        self.assertEqual((self.stored()["idea"], self.stored()["accepted_by"]), (idea, "María Gómez"))

    def test_an_approved_spanish_draft_is_refused_asking_to_rewrite_the_draft(self) -> None:
        self.approve_draft(SPANISH_IDEA)
        done, out = self.accept("--by", "operator")
        self.assertEqual(done.returncode, 1)
        self.assertEqual(done.stderr, "")
        self.assertEqual((out["ok"], out["error"]), (False, "IDEA_NOT_ENGLISH"))
        self.assertIn("rewrite the idea brief draft", out["message"])
        self.assertIsNone(self.stored())
        self.assertFalse((self.root / ".papersmith" / "paper_type.json").exists())


class EnglishAcceptanceUnchangedTests(AcceptCase):
    """S2 (d): an English acceptance from `--idea-file` keeps working unchanged."""

    def test_an_english_idea_file_is_recorded_as_before(self) -> None:
        done, out = self.accept("--by", "operator", "--idea-file", "-", "--top5", "a", "b", stdin=ENGLISH_IDEA)
        self.assertEqual(done.returncode, 0, done.stdout)
        self.assertEqual(done.stderr, "")
        stored = self.stored()
        self.assertEqual(set(stored), {"idea", "idea_sha256", "accepted_by", "accepted_at", "pool_sha256", "top5"})
        self.assertEqual((stored["idea"], stored["accepted_by"], stored["top5"]), (ENGLISH_IDEA, "operator", ["a", "b"]))
        self.assertEqual(out["plausibility"], stored)
        self.assertEqual(out["suggested"], "applied-ai")

    def test_an_explicit_idea_file_wins_over_the_approved_draft(self) -> None:
        self.approve_draft("Survey data on rural youth migration are scarce. I propose a cross-sectional "
                           "survey with a probit regression of the intention to stay.")
        done, _out = self.accept("--by", "operator", "--idea-file", "-", stdin=ENGLISH_IDEA)
        self.assertEqual(done.returncode, 0, done.stdout)
        self.assertEqual(self.stored()["idea"], ENGLISH_IDEA)

    def test_operator_absent_still_comes_first(self) -> None:
        done, out = self.accept("--idea-file", "-", stdin=SPANISH_IDEA)
        self.assertEqual((done.returncode, out["error"]), (1, "OPERATOR_ABSENT"))


class PaperTypeViewNoticeTests(unittest.TestCase):
    """S3: the paper-type view flags a stored acceptance that is not English."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "ws"
        self.root.mkdir()

    def test_a_spanish_acceptance_carries_a_notice_with_the_rerecord_command(self) -> None:
        decision.record_acceptance(self.root, SPANISH_IDEA, by=SPANISH_BY)  # an existing workspace's record
        notice = paper_type_view.view(self.root)["language_notice"]
        self.assertEqual(notice, {"expected": "en", "file": ".papersmith/plausibility.json",
                                  "fields": ["idea", "accepted_by"], "command": RERECORD})
        body = TestClient(server.create_app(self.root)).get("/api/paper-type").json()
        self.assertEqual(body["language_notice"], notice)
        self.assertEqual(body["plausibility"]["idea"], SPANISH_IDEA, "the record is shown as written")

    def test_only_the_spanish_field_is_named(self) -> None:
        decision.record_acceptance(self.root, SPANISH_IDEA, by="operator")
        self.assertEqual(paper_type_view.view(self.root)["language_notice"]["fields"], ["idea"])

    def test_an_english_acceptance_and_no_acceptance_carry_no_notice(self) -> None:
        self.assertNotIn("language_notice", paper_type_view.view(self.root))
        decision.record_acceptance(self.root, ENGLISH_IDEA, by="José Gómez")
        view = paper_type_view.view(self.root)
        self.assertNotIn("language_notice", view)
        self.assertEqual(set(view), {"catalogue", "plausibility", "decision", "line", "subphase", "error"})


class EmpiricalBoardNoticeTests(unittest.TestCase):
    """S3: the empirical board's plausibility step names a non-English acceptance."""

    @classmethod
    def setUpClass(cls) -> None:
        from papersmith.core.init import initialize

        cls.holder = Path(tempfile.mkdtemp(prefix="board-language-"))
        cls.template = cls.holder / "ws"
        initialize(cls.template, tools=("claude",), run_npm=False, run_env=False, kind="observational-measurement")

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.holder, ignore_errors=True)

    def workspace(self, name: str) -> Path:
        root = self.holder / name
        shutil.copytree(self.template, root, symlinks=True)
        return root

    @staticmethod
    def step(root: Path, lang: str = "") -> dict:
        status = TestClient(server.create_app(root)).get("/api/status" + (f"?lang={lang}" if lang else "")).json()
        return next(f for f in status["fases"] if f["stage_id"] == "plausibility_type")

    def test_a_spanish_acceptance_is_named_in_the_step_detail_in_both_languages(self) -> None:
        root = self.workspace("spanish")
        decision.record_acceptance(root, SPANISH_IDEA, by=SPANISH_BY)
        detail = self.step(root)["detail"]
        self.assertIn("the accepted idea in .papersmith/plausibility.json is not written in English: "
                      "idea, accepted_by; re-record it with " + RERECORD, detail)
        spanish = self.step(root, "es")["detail"]
        self.assertIn("la idea aceptada en .papersmith/plausibility.json no está escrita en inglés", spanish)
        self.assertIn(RERECORD, spanish)
        self.assertNotIn("is not written in English", spanish)

    def test_an_english_acceptance_keeps_its_detail(self) -> None:
        root = self.workspace("english")
        decision.record_acceptance(root, ENGLISH_IDEA, by="operator")
        self.assertEqual(self.step(root)["detail"], "Plausibility accepted by operator; "
                                                    "the paper type awaits the operator's agreement (/paper-type)")


class BoardLanguageDefaultTests(unittest.TestCase):
    """S4: the board's server defaults are English; the board-passed language still works."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "ws"
        self.root.mkdir()

    def review(self, body: dict) -> tuple[str, str]:
        turn = {"reply": "r", "verdict": "clarify", "issues": ["i"], "improved_prompt": "",
                "preserved_requirements": [], "questions": [{"id": "q1", "question": "q", "options": ["a", "b"]}]}
        client = TestClient(server.create_app(self.root))
        with mock.patch.object(tutor, "run_agent", return_value=(turn, "claude")) as run:
            self.assertEqual(client.post("/api/prompt/review", json=body).status_code, 200)
        return run.call_args.args[1], run.call_args.args[2]

    def test_prompt_review_defaults_to_the_english_board(self) -> None:
        system, prompt = self.review({"skill": "plausibility", "text": "hazlo"})
        self.assertIn("Board language: en", prompt)
        self.assertNotIn("Board language: es", prompt)
        # The headless rule closes the system prompt, after the generic "reply in the human's language".
        self.assertTrue(system.endswith(prompt_review.HEADLESS))
        self.assertIn("board language", prompt_review.HEADLESS)
        self.assertNotIn("operator's language", prompt_review.HEADLESS)
        self.assertNotIn("in the language the operator wrote the original in", system)

    def test_prompt_review_keeps_a_board_passed_language(self) -> None:
        self.assertIn("Board language: es", self.review({"skill": "plausibility", "text": "hazlo",
                                                         "language": "es"})[1])
        self.assertIn("Board language: en", self.review({"skill": "plausibility", "text": "hazlo",
                                                         "language": "en"})[1])

    def test_banco_suggest_defaults_to_english(self) -> None:
        empty: list = []
        self.assertEqual(banco_suggest.compose_draft(["eeg", "quantum", "kernel"], empty, empty),
                         banco_suggest.compose_draft(["eeg", "quantum", "kernel"], empty, empty, "en"))
        self.assertNotEqual(banco_suggest.compose_draft(["eeg", "quantum", "kernel"], empty, empty, "es"),
                            banco_suggest.compose_draft(["eeg", "quantum", "kernel"], empty, empty, "en"))

    def test_the_phase_console_falls_back_to_english(self) -> None:
        script = (REPO / "skills/_core/command_center/static/phase-console.js").read_text(encoding="utf-8")
        self.assertIn("window.i18n.getLanguage() : 'en')", script)
        self.assertNotIn("window.i18n.getLanguage() : 'es')", script)

    def test_the_headless_contracts_name_the_board_language(self) -> None:
        for rel in ("skills/paper-type/SKILL.md", "skills/prompt-gate/SKILL.md"):
            text = (REPO / rel).read_text(encoding="utf-8")
            contract = text.split("## Headless", 1)[1]
            self.assertNotIn("in their language", contract, rel)
            self.assertNotIn("in the operator's language", contract, rel)
            self.assertIn("board language", contract, rel)


if __name__ == "__main__":
    unittest.main()
