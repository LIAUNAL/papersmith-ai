"""The experiment flow plans and records the illustrative results (spec S3
of `odd/tasks/illustrative-results.md`).

* `experimental-deliberation`: the protocol declares the illustrative
  artefacts per item (a)-(d) that applies, in each experiment's expected
  report, before any aggregate performance artefact.
* `experimental-implementation`: the runs record their raw material under
  `Results/` and draw them with the kit's helpers.
* `experiments-reviewer`: missing illustrative records is a finding.

Stdlib only, like `test_experiments_reviewer_agent.py`.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DELIBERATION = ROOT / "skills" / "experimental-deliberation" / "SKILL.md"
USAGE = ROOT / "skills" / "experimental-deliberation" / "references" / "usage.md"
IMPLEMENTATION = ROOT / "skills" / "experimental-implementation" / "SKILL.md"
KIT = ROOT / "skills" / "experimental-implementation" / "assets" / "kit" / "ps_figures.py"
REVIEWER = ROOT / ".claude" / "agents" / "experiments-reviewer.md"

HELPERS = ("forecast_plot", "loss_terms_plot", "heatmap_plot", "embedding_plot",
           "confusion_matrix_plot", "roc_plot")


def flat(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


class DeliberationDeclaresTheIllustrativeArtefactsTests(unittest.TestCase):

    def setUp(self) -> None:
        self.doc = flat(DELIBERATION)

    def test_the_section_declares_each_item_a_to_d(self) -> None:
        self.assertIn("## Declaring the illustrative results", self.doc)
        for fragment in ("**(a) The improved representation.**", "**(b) The loss or regularizer.**",
                         "**(c) Prediction examples.**", "**(d) Representation and separability.**",
                         "imshow", "Monte Carlo dropout", "UMAP, t-SNE", "confusion matrices", "ROC curves"):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, self.doc)

    def test_the_expected_report_opens_with_them_before_any_aggregate_artefact(self) -> None:
        self.assertIn("opening with the [illustrative artefacts](#declaring-the-illustrative-results) "
                      "for each item (a)-(d) that applies (or the reason it does not), before any aggregate "
                      "performance table or figure", self.doc)

    def test_usage_links_the_section_by_a_heading_skill_md_has(self) -> None:
        self.assertIn("../SKILL.md#declaring-the-illustrative-results", flat(USAGE))


class ImplementationRecordsTheRawMaterialTests(unittest.TestCase):

    def setUp(self) -> None:
        self.doc = flat(IMPLEMENTATION)

    def test_the_results_layout_names_the_records_s3_lists(self) -> None:
        self.assertIn("### Recording the illustrative results", self.doc)
        for fragment in ("Per-term loss histories", "Representative input windows, predictions, targets, "
                         "comparator predictions and bands", "Representation snapshots",
                         "2-D embeddings with labels", "confusion counts", "ROC points",
                         "`Results/illustrative/**`"):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, self.doc)

    def test_every_helper_the_skill_names_is_defined_by_the_kit(self) -> None:
        defined = {node.name for node in ast.parse(KIT.read_text(encoding="utf-8")).body
                   if isinstance(node, ast.FunctionDef)}
        for helper in HELPERS:
            with self.subTest(helper=helper):
                self.assertIn(f"`{helper}(", self.doc)
                self.assertIn(helper, defined)


class ReviewerFindsMissingIllustrativeRecordsTests(unittest.TestCase):

    def test_a_declared_artefact_never_recorded_is_a_major_finding(self) -> None:
        doc = flat(REVIEWER)
        self.assertIn("**Declaring the illustrative results**", doc)
        self.assertIn("A declared illustrative artefact the code never records is a `major` finding", doc)
        self.assertIn("`Results/illustrative/`", doc)


if __name__ == "__main__":
    unittest.main()
