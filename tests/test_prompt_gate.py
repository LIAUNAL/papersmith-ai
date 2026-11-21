"""The deterministic prompt quality gate: every phase prompt gets a 0-100
score from a generic rubric plus the input contract of the skill it is sent
to, and fails on a critical issue or a score under the threshold. No model
is called; the same check runs from the dashboard, the CLI and the agents."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from skills._core.command_center import prompt_gate

REPO = Path(__file__).resolve().parents[1]


def ids(result: dict) -> set[str]:
    return {issue["id"] for issue in result["issues"]}


class GenericRubric(unittest.TestCase):
    def test_empty_prompt_is_a_critical_failure(self) -> None:
        result = prompt_gate.check("plausibility", "   ")
        self.assertEqual(result["verdict"], "fail")
        self.assertTrue(result["critical"])
        self.assertIn("empty", ids(result))

    def test_empty_is_allowed_for_an_optional_skill(self) -> None:
        result = prompt_gate.check("upgrade-project", "")
        self.assertEqual(result["verdict"], "pass")
        self.assertEqual(result["issues"], [])

    def test_vague_prompt_fails(self) -> None:
        for text in ("hazlo", "fix it", "mejora esto por favor", "continue"):
            with self.subTest(text=text):
                result = prompt_gate.check("proposal-deliberation", text)
                self.assertEqual(result["verdict"], "fail")
                self.assertIn("vague", ids(result))

    def test_leftover_example_or_placeholder_is_flagged(self) -> None:
        result = prompt_gate.check("paper-ingestion", "E.g.: ingest guidance/reference-papers/inbox/*.pdf")
        self.assertIn("placeholder", ids(result))
        result = prompt_gate.check("paper-ingestion", "ingest <path-or-url> now")
        self.assertIn("placeholder", ids(result))

    def test_result_shape(self) -> None:
        result = prompt_gate.check("/plausibility", "x")
        self.assertEqual(result["skill"], "plausibility")
        self.assertEqual(result["threshold"], prompt_gate.THRESHOLD)
        self.assertIsInstance(result["score"], int)
        self.assertTrue(0 <= result["score"] <= 100)
        self.assertIsInstance(result["needs"], list)
        for issue in result["issues"]:
            self.assertEqual(set(issue), {"id", "severity", "message"})
            self.assertIn(issue["severity"], ("critical", "major", "minor"))

    def test_unknown_skill_uses_the_generic_rubric(self) -> None:
        self.assertEqual(prompt_gate.check("journal-finder", "Q1 Q2 journals for EEG decoding")["verdict"], "pass")
        self.assertEqual(prompt_gate.check("journal-finder", "fix it")["verdict"], "fail")

    def test_a_skill_without_a_contract_handles_its_own_empty_input(self) -> None:
        for skill in ("math-tutor", "experiments-tutor", "journal-finder", "pixelrag", "ui-github",
                      "proposal-deliberation"):
            with self.subTest(skill=skill):
                self.assertEqual(prompt_gate.check(skill, "")["verdict"], "pass")
        self.assertEqual(prompt_gate.check("plausibility", "")["verdict"], "fail")

    def test_approval_marker_passes_and_is_stripped(self) -> None:
        result = prompt_gate.check("plausibility", f"hazlo {prompt_gate.APPROVED_MARKER}")
        self.assertEqual(result["verdict"], "pass")
        self.assertTrue(result["approved"])
        self.assertEqual(result["text"], "hazlo")
        self.assertEqual(prompt_gate.strip_marker(f"a b {prompt_gate.APPROVED_MARKER}"), "a b")


class SkillContracts(unittest.TestCase):
    def test_plausibility_needs_two_sentences(self) -> None:
        result = prompt_gate.check("plausibility", "Quantum EEG classification.")
        self.assertEqual(result["verdict"], "fail")
        self.assertTrue(result["critical"])
        self.assertIn("sentences", ids(result))

    def test_plausibility_needs_the_problem_and_the_proposal(self) -> None:
        result = prompt_gate.check(
            "plausibility", "EEG is a signal recorded from the scalp. Many datasets exist for it today.")
        self.assertIn("proposal", ids(result))
        self.assertEqual(result["verdict"], "fail")

    def test_good_plausibility_passes_in_english_and_spanish(self) -> None:
        for text in (
            "Current EEG motor-imagery classifiers lose accuracy across subjects. "
            "I propose a quantum kernel that aligns subject covariances before classification.",
            "Los clasificadores EEG de imaginación motora pierden precisión entre sujetos. "
            "Propongo un kernel cuántico que alinea las covarianzas de cada sujeto antes de clasificar.",
            # Written without accents, as typed on many keyboards.
            "Los clasificadores EEG actuales tienen una limitacion entre sujetos y su precision cae. "
            "Planteo un metodo hibrido que alinea las covarianzas de cada sujeto antes de clasificar.",
        ):
            with self.subTest(text=text[:20]):
                result = prompt_gate.check("plausibility", text)
                self.assertEqual(result["verdict"], "pass", result)
                self.assertGreaterEqual(result["score"], prompt_gate.THRESHOLD)

    def test_common_wordings_of_a_two_sentence_idea_pass(self) -> None:
        # Verifier probes: clear ideas the first keyword lists missed.
        for text in (
            "Graph neural networks oversmooth when stacked deeply. My idea is to add a learnable residual "
            "gate per layer that preserves node identity.",
            "Federated learning is slow on heterogeneous clients. I want to try asynchronous aggregation "
            "with staleness-aware weights.",
            "Las redes neuronales en grafos sobre-suavizan cuando se apilan muchas capas. Mi idea es añadir "
            "una compuerta residual aprendible por capa.",
        ):
            with self.subTest(text=text[:30]):
                self.assertEqual(prompt_gate.check("plausibility", text)["verdict"], "pass")

    def test_paper_writing_single_verbs_pass(self) -> None:
        for verb in ("status", "verify", "reorder", "full_text", "render", "readiness"):
            with self.subTest(verb=verb):
                self.assertEqual(prompt_gate.check("paper-writing", verb)["verdict"], "pass")

    def test_ingestion_needs_a_path_or_url(self) -> None:
        bad = prompt_gate.check("paper-ingestion", "ingest the papers please now")
        self.assertTrue(bad["critical"])
        self.assertIn("source", ids(bad))
        for text in ("ingest guidance/reference-papers/inbox/*.pdf", "https://arxiv.org/abs/2406.06608",
                     "ingest the top 5 accepted in plausibility"):
            with self.subTest(text=text):
                self.assertEqual(prompt_gate.check("paper-ingestion", text)["verdict"], "pass")

    def test_figure_review_needs_a_figure_id(self) -> None:
        self.assertIn("figure", ids(prompt_gate.check("figure-review", "review the main picture")))
        self.assertEqual(prompt_gate.check("figure-review", "review the fig-architecture figure")["verdict"], "pass")

    def test_implementation_needs_a_target_repository(self) -> None:
        self.assertIn("target", ids(prompt_gate.check("proposal-implementation", "implement the proof of concept")))
        self.assertEqual(
            prompt_gate.check("proposal-implementation", "implement the PoC of proposal r03 in ../my-poc")["verdict"],
            "pass")

    def test_needs_lists_the_contract(self) -> None:
        needs = prompt_gate.check("plausibility", "")["needs"]
        self.assertTrue(any("problem" in need for need in needs))


class DashboardBuiltCommandsPass(unittest.TestCase):
    """Commands the dashboard composes itself must never trip the gate."""

    COMMANDS = [
        ("paper-writing", "translate es"),
        ("paper-writing", "skeleton open the skeleton of the paper's sections and blocks."),
        ("paper-writing", "mark manuscript language: English; code availability: public GitHub."),
        ("paper-writing", "write the intro.motivation block"),
        ("kaggle-accounts", "validate "),
        ("math-tutor", "Walk me through the equations of the latest proposal revision."),
        ("proposal-deliberation", "Now the mathematics: formalize the agreed hypotheses as $$ ... \\tag{N} $$ "
                                  "display blocks in the next revision."),
        ("experimental-deliberation", "design the experiment that tests claim C1 against the strongest SOTA baseline."),
        ("experimental-implementation", "full-experiment Run the judge-reviewer now: hand each full-experiment "
                                        "discussion that is complete to the paper-reviewer agent."),
        ("datasets", "synth an 8-subject toy set and look for an official dataset for the task."),
        ("remote-execution", "generate the job for experiments/e1.py and prepare its smoke rehearsal."),
        ("skill-audit", "audit skills/paper-writing"),
        ("proposal-implementation", "Implement the proof of concept of the latest proposal revision on the toy set "
                                    "and close it with a complete Results/discussion.json (hypothesis verdicts, tests, novelty)."),
        ("experimental-implementation", "Implement and measure the full experiments of the current protocol; "
                                        "the proof of concept is verified (G-EXP-POC)."),
        ("experimental-deliberation", "Justify the protocol with SOTA citations now: in .papersmith/citations.json, "
                                      "give every experiment of the latest protocol 2 to 5 references."),
        ("proposal-deliberation", "Let us define the central problem and its pillars first: build the problem tree "
                                  "in novelty.problem_tree, in technical English."),
    ]

    def test_each_passes(self) -> None:
        for skill, text in self.COMMANDS:
            with self.subTest(skill=skill, text=text[:30]):
                self.assertEqual(prompt_gate.check(skill, text)["verdict"], "pass",
                                 prompt_gate.check(skill, text))


class Cli(unittest.TestCase):
    def run_cli(self, *args: str, stdin: str = "") -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, "-m", "skills._core.command_center.prompt_gate", *args],
                              cwd=REPO, input=stdin, capture_output=True, text=True, check=False)

    def test_check_with_text(self) -> None:
        done = self.run_cli("check", "--skill", "plausibility", "--text", "hazlo")
        self.assertEqual(done.returncode, 0, done.stderr)
        payload = json.loads(done.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["verdict"], "fail")

    def test_check_reads_stdin(self) -> None:
        done = self.run_cli("check", "--skill", "figure-review", stdin="review the fig-architecture figure\n")
        self.assertEqual(json.loads(done.stdout)["verdict"], "pass")

    def test_usage_error(self) -> None:
        done = self.run_cli("check")
        self.assertEqual(done.returncode, 2)
        payload = json.loads(done.stdout)
        self.assertEqual(payload, {"ok": False, "error": "USAGE", "message": payload["message"]})


if __name__ == "__main__":
    unittest.main()
