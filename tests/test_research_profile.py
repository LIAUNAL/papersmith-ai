"""Spec S2/S4 of odd/tasks/journal-two-stage-match.md: the lexical research profile of a paper and of the
works a journal published, and how well a journal's works match the paper."""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "skills" / "journal-finder" / "scripts" / "research_profile.py"


def _load():
    spec = importlib.util.spec_from_file_location("research_profile_under_test", SOURCE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


rp = _load()

QUANT_AI = ("We propose a novel deep learning method for seizure detection. A convolutional neural network was "
            "trained on a dataset of 120 patients and reached 0.91 accuracy under cross-validation, outperforming "
            "the baselines; a regression analysis confirmed the effect was statistically significant.")
QUALITATIVE = ("This qualitative study draws on semi-structured interviews and focus groups with 24 teachers. "
               "A thematic analysis grounded in the participants' narratives describes how rural schools adapt.")
QUALITATIVE_ES = ("Estudio cualitativo basado en entrevistas semiestructuradas y grupos focales con docentes "
                  "rurales; el análisis temático describe la experiencia de adaptación de las escuelas.")
THEORY = ("We prove a convergence theorem for stochastic gradient methods in Hilbert spaces and derive a "
          "closed-form bound on the generalization error; a lemma characterises the optimization landscape.")
REVIEW = ("This systematic review surveys the state of the art in brain-computer interfaces and offers an "
          "overview of open problems.")
APPLIED = ("A case study of a real-world deployment in a clinical setting: the application of a decision support "
           "tool to practice in three hospitals.")


class ClassifyTests(unittest.TestCase):
    def test_quantitative_ai_method_text(self):
        profile = rp.classify(QUANT_AI)
        self.assertEqual(profile["approach"], "quantitative")
        self.assertTrue(profile["ai"])
        self.assertEqual(profile["kind"], "general")

    def test_qualitative_text_in_english_and_spanish(self):
        for text in (QUALITATIVE, QUALITATIVE_ES):
            profile = rp.classify(text)
            self.assertEqual(profile["approach"], "qualitative", text)
            self.assertFalse(profile["ai"], text)
            self.assertEqual(profile["math"], "descriptive", text)

    def test_mixed_methods_named_or_balanced(self):
        self.assertEqual(rp.classify("A mixed-methods design combined a survey with interviews.")["approach"],
                         "mixed")
        self.assertEqual(rp.classify("Interviews and a regression on the measured scores.")["approach"], "mixed")

    def test_theory_is_mathematical(self):
        profile = rp.classify(THEORY)
        self.assertEqual(profile["kind"], "theory")
        self.assertEqual(profile["math"], "mathematical")

    def test_review_and_use_inspired_kinds(self):
        self.assertEqual(rp.classify(REVIEW)["kind"], "review")
        self.assertEqual(rp.classify(APPLIED)["kind"], "use-inspired")

    def test_nothing_recognised_reads_unclear(self):
        profile = rp.classify("Notes on the colour of autumn leaves.")
        self.assertEqual((profile["approach"], profile["kind"], profile["math"]), ("unclear", "unclear", "unclear"))
        self.assertFalse(profile["ai"])

    def test_inverted_index_rebuilds_the_abstract(self):
        index = {"Deep": [0], "learning": [1], "works": [2, 4], "well": [3]}
        self.assertEqual(rp.abstract_from_index(index), "Deep learning works well works")
        self.assertEqual(rp.abstract_from_index(None), "")


class PaperProfileTests(unittest.TestCase):
    BODY = ("\\section{Model}\n" + "The state evolves as described next. " * 20
            + "\\begin{equation} x_{t+1} = A x_t + w_t \\end{equation}\n" * 6 + "where $A$ and $w_t$ are given. " * 4)

    def test_equation_density_sets_the_math_level(self):
        self.assertGreater(rp.math_density(self.BODY), rp.MATH_DENSE)
        profile = rp.paper_profile("A model", QUANT_AI, ["deep learning"], self.BODY)
        self.assertEqual(profile["math"], "mathematical")
        self.assertEqual(profile["math_basis"], "equations")
        light = rp.paper_profile("A study", QUALITATIVE, [], "\\section{Findings}\n" + "Teachers said so. " * 200)
        self.assertEqual(light["math"], "descriptive")

    def test_contribution_type_sets_the_kind(self):
        recorded = {"type": "Use-Inspired", "why": "clinical need"}
        profile = rp.paper_profile("A model", QUANT_AI, [], "", contribution_type=recorded)
        self.assertEqual(profile["kind"], "use-inspired")
        self.assertEqual(profile["kind_basis"], "contribution_type")
        lexical = rp.paper_profile("A model", QUANT_AI, [], "")
        self.assertEqual((lexical["kind"], lexical["kind_basis"]), ("general", "lexical"))
        invalid = rp.paper_profile("A model", QUANT_AI, [], "", contribution_type={"type": "Other"})
        self.assertEqual(invalid["kind_basis"], "lexical")


class MatchTests(unittest.TestCase):
    PAPER = {"approach": "quantitative", "ai": True, "kind": "general", "math": "mathematical"}

    def test_a_journal_of_similar_work_beats_a_descriptive_one(self):
        alike = [rp.classify(QUANT_AI), rp.classify(THEORY), rp.classify(QUANT_AI)]
        unlike = [rp.classify(QUALITATIVE), rp.classify(QUALITATIVE_ES), rp.classify(APPLIED)]
        terms = ["seizure", "convolutional", "learning"]
        good = rp.match(self.PAPER, alike, [QUANT_AI, THEORY, QUANT_AI], terms)
        bad = rp.match(self.PAPER, unlike, [QUALITATIVE, QUALITATIVE_ES, APPLIED], terms)
        self.assertGreater(good["score"], bad["score"])
        self.assertEqual(good["dimensions"]["ai"], round(2 / 3, 4))
        self.assertEqual(bad["dimensions"]["approach"], 0.0)

    def test_adjacent_math_levels_count_half(self):
        works = [{"approach": "quantitative", "ai": True, "kind": "general", "math": "moderate"}]
        result = rp.match(self.PAPER, works, ["x"], [])
        self.assertEqual(result["dimensions"]["math"], 0.5)

    def test_unclear_dimensions_leave_the_score(self):
        paper = {"approach": "unclear", "ai": False, "kind": "unclear", "math": "unclear"}
        result = rp.match(paper, [rp.classify(QUANT_AI)], [QUANT_AI], [])
        self.assertEqual(result["active"], ["ai"])
        self.assertEqual(result["score"], 0.0)

    def test_no_works_means_no_score(self):
        result = rp.match(self.PAPER, [], [], ["seizure"])
        self.assertIsNone(result["score"])
        self.assertEqual(result["active"], [])

    def test_shares_summarise_the_works(self):
        shares = rp.shares([rp.classify(QUANT_AI), rp.classify(QUALITATIVE)])
        self.assertEqual(shares["n"], 2)
        self.assertEqual(shares["approach"], {"quantitative": 0.5, "qualitative": 0.5})
        self.assertEqual(shares["ai"], 0.5)


if __name__ == "__main__":
    unittest.main()
