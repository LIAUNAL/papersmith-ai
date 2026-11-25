"""``smith idea``: the idea-shaping CLI through ``papersmith.cli.main`` (the
verbs, the gated draft, the interactive ``start`` on scripted stdin, the
non-interactive ``--answers`` run). OpenAlex is a fake fetcher and no bank is
contacted (the choice is ``none``, and contacting one fails the test)."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from papersmith.cli import main as smith
from skills._core.idea import bank, brief, idea_cli, profile

GOOD = ("Current EEG classifiers lose accuracy when the recording site changes, a limitation that blocks "
        "clinical use. I propose to align graph representations across sites with a transfer learning step.")
AUTHOR = {"id": "https://openalex.org/A1234567", "display_name": "Ada Lovelace", "works_count": 7,
          "topics": [{"display_name": "EEG signal analysis", "count": 5}]}


def fetch(url: str):
    if "/authors" in url:
        return {"results": [AUTHOR]} if "/authors?" in url else AUTHOR
    return {"meta": {"count": 12}}


def forbidden(*args, **kwargs):
    raise AssertionError("no bank may be contacted in these tests")


class SmithIdeaCase(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "ws"
        (self.root / ".papersmith").mkdir(parents=True)
        self.scratch = Path(tmp.name)
        for target, value in ((profile, fetch), (bank, forbidden)):
            patcher = mock.patch.object(target, "FETCH" if target is profile else "CONNECT", value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def smith(self, *argv: str, stdin: str = "") -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                mock.patch("sys.stdin", io.StringIO(stdin)):
            code = smith(["idea", *argv])
        return code, out.getvalue(), err.getvalue()

    def json(self, *argv: str) -> tuple[int, dict]:
        code, out, _ = self.smith(*argv, str(self.root), "--json")
        return code, json.loads(out)


class HelpTests(SmithIdeaCase):
    def test_help_lists_every_verb(self) -> None:
        code, out, _ = self.smith("--help")
        self.assertEqual(code, 0)
        self.assertIn("usage: smith idea [VERB] [ROOT] [options]", out)
        for verb in idea_cli.VERBS:
            self.assertIn(verb, out)

    def test_each_verb_has_its_own_help(self) -> None:
        code, out, _ = self.smith("bank", "--help")
        self.assertEqual(code, 0)
        for option in ("--list", "--probe", "--choose", "--add", "--command", "--url", "--json"):
            self.assertIn(option, out)
        code, out, _ = self.smith("start", "--help")
        for option in ("--answers", "--bank", "--yes"):
            self.assertIn(option, out)

    def test_smith_help_names_the_command(self) -> None:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
            smith(["--help"])
        self.assertIn("idea", out.getvalue())


class DraftGateTests(SmithIdeaCase):
    def test_the_gate_refuses_one_sentence_and_approval_waits_for_it(self) -> None:
        code, body = self.json("draft", "--text", "Make EEG models better.")
        self.assertEqual(code, 0)
        self.assertFalse(body["draft"]["gate"]["ok"])
        self.assertTrue(any("2 sentences" in m for m in body["draft"]["gate"]["missing"]))
        code, body = self.json("approve")
        self.assertEqual((code, body["error"]), (1, "DRAFT_GATE_FAILED"))
        code, body = self.json("handoff")
        self.assertEqual((code, body["error"]), (1, "DRAFT_NOT_APPROVED"))
        self.assertFalse(brief.load(self.root)["draft"]["approved"])

    def test_check_only_scores_without_recording(self) -> None:
        code, body = self.json("draft", "--check", "--text", GOOD)
        self.assertEqual(code, 0)
        self.assertTrue(body["gate"]["ok"])
        self.assertEqual(brief.load(self.root)["draft"]["text"], "")

    def test_handoff_prints_the_plausibility_line_once_approved(self) -> None:
        self.assertEqual(self.json("draft", "--text", GOOD)[0], 0)
        code, out, _ = self.smith("handoff", str(self.root))
        self.assertEqual(code, 1)
        code, out, _ = self.smith("approve", str(self.root))
        self.assertEqual(code, 0)
        self.assertIn(f"/plausibility {GOOD}", out)
        code, out, _ = self.smith("handoff", str(self.root))
        self.assertEqual((code, out.strip()), (0, f"/plausibility {GOOD}"))
        self.assertIsNotNone(brief.load(self.root)["draft"]["approved_at"])

    def test_a_new_text_withdraws_the_approval(self) -> None:
        self.json("draft", "--text", GOOD)
        self.json("approve")
        self.json("draft", "--text", GOOD + " It runs on public data.")
        self.assertEqual(self.json("handoff")[1]["error"], "DRAFT_NOT_APPROVED")

    def test_compose_needs_a_chosen_topic(self) -> None:
        code, body = self.json("draft", "--compose")
        self.assertEqual((code, body["error"]), (1, "TOPICS_ABSENT"))


SCRIPT = "\n".join([
    "3",                                    # 1 sources: none
    "Ada Lovelace",                         # 2 profile
    "2", "graph neural networks", "a public EEG dataset", "6 months",  # 3 experience
    "eeg, domain shift, transfer learning", "clinical neurology", "",  # 4 interests
    "1,2", "",                              # 5 topics: combine 1 and 2, no note
    "y",                                    # 6 approve
]) + "\n"


class StartTests(SmithIdeaCase):
    def test_interactive_start_asks_one_question_at_a_time_and_hands_off(self) -> None:
        code, out, err = self.smith(str(self.root), stdin=SCRIPT)
        self.assertEqual(code, 0, err)
        for prompt in ("1/6 Sources", "2/6 Profile", "3/6 Experience", "4/6 Interests", "5/6 Topics", "6/6 Draft"):
            self.assertIn(prompt, out)
        self.assertLess(out.index("1/6 Sources"), out.index("2/6 Profile"))
        recorded = brief.load(self.root)
        self.assertEqual(recorded["bank"]["choice"], "none")
        self.assertEqual(recorded["profile"]["display_name"], "Ada Lovelace")
        self.assertEqual(recorded["experience"]["level"], "early-career")
        self.assertEqual(recorded["chosen"]["topic_ids"], ["t1", "t2"])
        self.assertTrue(recorded["draft"]["approved"])
        self.assertEqual(recorded["draft"]["source_topics"], ["t1", "t2"])
        line = f"/plausibility {recorded['draft']['text']}"
        self.assertIn(line + "\n", out)
        self.assertIn("smith ui", out.split(line, 1)[1])
        self.assertIn("Idea tab", out.split(line, 1)[1])

    def test_eof_keeps_the_answers_so_far_and_exits_cleanly(self) -> None:
        code, out, err = self.smith(str(self.root), stdin="3\nAda Lovelace\n")
        self.assertEqual(code, 0)
        self.assertIn("Stopped", out)
        self.assertNotIn("Traceback", out + err)
        recorded = brief.load(self.root)
        self.assertEqual(recorded["bank"]["choice"], "none")
        self.assertEqual(recorded["profile"]["display_name"], "Ada Lovelace")
        self.assertEqual(recorded["topics"], [])

    def test_ctrl_c_keeps_the_answers_so_far(self) -> None:
        answers = iter(["3"])

        def ask(prompt: str) -> str:
            try:
                return next(answers)
            except StopIteration:
                raise KeyboardInterrupt from None

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = idea_cli.main(["start", str(self.root)], prog="smith idea", ask=ask)
        self.assertEqual(code, 130)
        self.assertIn("Stopped", out.getvalue())
        self.assertEqual(brief.load(self.root)["bank"]["choice"], "none")

    def test_bank_option_skips_the_first_question(self) -> None:
        code, out, _ = self.smith("start", str(self.root), "--bank", "none", stdin="")
        self.assertEqual(code, 0)
        self.assertIn("1/6 Sources: none", out)
        self.assertNotIn("Choose 1, 2 or 3", out)

    def answers(self, **extra) -> Path:
        data = {"bank": "none", "profile": {"name": "Ada Lovelace"},
                "experience": {"level": "student", "methods": ["SVM"]},
                "interests": {"keywords": ["eeg", "domain shift"], "domain": "clinical neurology"},
                "chosen": [1], **extra}
        target = self.scratch / "answers.json"
        target.write_text(json.dumps(data), encoding="utf-8")
        return target

    def test_answers_run_without_questions_and_write_the_brief(self) -> None:
        code, out, _ = self.smith("start", str(self.root), "--answers", str(self.answers()), "--yes", "--json")
        self.assertEqual(code, 0)
        body = json.loads(out)
        self.assertTrue(body["ok"])
        recorded = brief.load(self.root)
        self.assertEqual(body["brief"], recorded)
        self.assertEqual(recorded["bank"]["choice"], "none")
        self.assertEqual(recorded["profile"]["source"], "openalex")
        self.assertEqual(recorded["interests"]["domain"], "clinical neurology")
        self.assertEqual(len(recorded["topics"]), 3)
        self.assertEqual(recorded["chosen"]["topic_ids"], ["t1"])
        self.assertTrue(recorded["draft"]["gate"]["ok"], recorded["draft"])
        self.assertTrue(recorded["draft"]["approved"])
        self.assertEqual(body["handoff"], f"/plausibility {recorded['draft']['text']}")

    def test_answers_with_a_failing_draft_record_it_but_refuse_approval(self) -> None:
        path = self.answers(draft="EEG is hard.")
        code, out, _ = self.smith("start", str(self.root), "--answers", str(path), "--yes", "--json")
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out)["error"], "DRAFT_GATE_FAILED")
        recorded = brief.load(self.root)["draft"]
        self.assertEqual((recorded["text"], recorded["approved"]), ("EEG is hard.", False))

    def test_unreadable_answers_are_refused(self) -> None:
        code, body = self.json("start", "--answers", str(self.scratch / "missing.json"))
        self.assertEqual((code, body["error"]), (1, "ANSWERS_UNREADABLE"))


if __name__ == "__main__":
    unittest.main()
