"""The experimental line shows what the novelty does before how well it does.

Spec S2 (illustrative-results): the results contract carries the rule
"Illustrative results before performance" verbatim, a required block
`rd-illustrative` sits before `rd-general-task` and carries those figures,
and a disqualifier names aggregate performance shown first. The
experimental-setup contract declares the illustrative instruments: which
examples, which comparators, which band method, which embedding.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SECTIONS = ROOT / "sections"
RESULTS = SECTIONS / "03-results-and-discussion.md"
SETUP = SECTIONS / "02-experimental-setup.md"
sys.path.insert(0, str(ROOT / "skills" / "paper-writing" / "scripts"))
import paper_graph  # noqa: E402

RULE = (
    "Illustrative results before performance. Before any aggregate performance artefact (error, R², "
    "accuracy and the like), the Results show what the novelty does at its basic stages: (a) the improved "
    "representation: for a physics-informed network, a transformer or a new architecture, imshow maps or "
    "plots of the relevant internal quantities on representative examples; (b) for a new or modified loss "
    "or regularizer, how it converges and how its terms interact during training; (c) for time series, "
    "regression and similar tasks, prediction examples on the toy set and on the most relevant real or "
    "semi-synthetic dataset, showing the input window and the estimated output against the target and the "
    "most relevant state-of-the-art comparators, with a confidence or variability band when the model "
    "provides one or Monte Carlo or Monte Carlo dropout can estimate it; (d) for classification, clustering "
    "and similar tasks, latent spaces at key points of the architecture (UMAP, t-SNE or similar) that show "
    "representation and separability or grouping, plus confusion matrices and ROC curves where they apply."
)

DISQUALIFIER = "Aggregate performance shown before any illustrative result of the novelty."


def _split(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    _, header, body = text.split("---\n", 2)
    return json.loads(header), body


def _flat(text: str) -> str:
    return " ".join(text.replace("**", "").split())


class IllustrativeResultsContractTests(unittest.TestCase):
    def test_the_results_contract_carries_the_rule_verbatim(self) -> None:
        _, body = _split(RESULTS)
        self.assertTrue(RULE in _flat(body), "the S2 rule sentence is missing or reworded")

    def test_the_illustrative_block_is_required_and_precedes_the_general_task(self) -> None:
        header, _ = _split(RESULTS)
        ids = [block["id"] for block in header["blocks"]]
        self.assertIn("rd-illustrative", ids)
        self.assertLess(ids.index("rd-illustrative"), ids.index("rd-general-task"))
        illustrative = header["blocks"][ids.index("rd-illustrative")]
        self.assertFalse(illustrative.get("optional", False))
        self.assertEqual([fact["value"] for fact in illustrative["requires_facts"]][0], "results")
        general = header["blocks"][ids.index("rd-general-task")]
        self.assertIn("results-and-discussion.rd-illustrative",
                      [edge["target"] for edge in general.get("after", [])])

    def test_the_derived_writing_order_puts_the_illustrations_first(self) -> None:
        corpus = paper_graph.assemble_corpus(SECTIONS)
        order = paper_graph.derive_order(corpus, paper_graph.collect_edges(corpus))
        self.assertLess(order.index("results-and-discussion.rd-illustrative"),
                        order.index("results-and-discussion.rd-general-task"))

    def test_the_blocks_list_names_the_illustrative_block_between_scenario_and_general_task(self) -> None:
        _, body = _split(RESULTS)
        scenario = body.index("**0. The controlled scenario**")
        illustrative = body.index("**Illustrative results before performance.**")
        general = body.index("**1. The general task.**")
        self.assertLess(scenario, illustrative)
        self.assertLess(illustrative, general)

    def test_the_results_contract_disqualifies_performance_first(self) -> None:
        _, body = _split(RESULTS)
        self.assertIn(f"- {DISQUALIFIER}\n", body)

    def test_the_setup_declares_the_illustrative_instruments(self) -> None:
        _, body = _split(SETUP)
        flat = _flat(body)
        for phrase in ("The illustrative instruments", "representative examples", "comparators", "model-native",
                       "Monte Carlo dropout", "embedding method"):
            self.assertTrue(phrase in flat, f"setup contract lacks {phrase!r}")


if __name__ == "__main__":
    unittest.main()
