"""Every paper line's Methods and Results contracts favour figures over tables.

Spec S2 (figures-over-tables): the same rule, in the same words, sits in the
Methods and Results/Discussion contracts of every line `manifest.LINES`
offers, and their extent lines allow at least as many figures as tables.
Spec S6: the caption-length rule sits beside it, and in every other contract
whose section holds a figure or a table or speaks of captions.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from papersmith.core import manifest

ROOT = Path(__file__).resolve().parents[1]

RULE = (
    "Figures over tables. In Methods and Results, present comparisons, distributions, trends, effects "
    "with their intervals and time series as data figures (line, bar, dot-and-whisker or forest, violin "
    "or box plots, heat maps) or diagrams. Keep a table only for values a reader must look up exactly "
    "(settings, hyperparameters, dataset, participant or hardware characteristics, metadata) or when the "
    "venue requires one. Among the floats of Methods and Results, aim at about 60 % figures and 40 % tables."
)

CAPTION = (
    "A figure or table caption is at most four lines: a title that says what the float shows, plus the one "
    "definition a reader needs to read it. Notation and further definitions go in a table note below the table "
    "or in the text."
)

#: Sections outside Methods and Results that hold floats: the experimental
#: line's synthesis table, and the hardware line's specifications, context
#: comparison, design files, bill of materials and step figures.
FLOAT_SECTIONS = re.compile(
    r"(related-work|specifications-table|hardware-in-context|design-files|bill-of-materials|"
    r"build-instructions|operation-instructions)$"
)

#: The section names that are a line's Methods or its Results/Discussion: the
#: data-resource line reports in its data records and technical validation, the
#: hardware line in its hardware description and validation/characterization.
METHODS = re.compile(r"(methods|experimental-setup|hardware-description)$")
RESULTS = re.compile(r"(results|discussion|data-records|technical-validation|validation-characterization)$")


def _section(path: Path) -> str:
    return path.stem.split("-", 1)[1]


def _contracts(kind: str) -> tuple[list[Path], list[Path]]:
    directory = ROOT / manifest.LINES[kind].sections_dir
    paths = sorted(directory.glob("*.md"))
    return ([p for p in paths if METHODS.search(_section(p))],
            [p for p in paths if RESULTS.search(_section(p))])


def _flat_body(path: Path) -> str:
    body = path.read_text(encoding="utf-8").split("\n---\n", 1)[1]
    return " ".join(body.split())


class FiguresOverTablesTests(unittest.TestCase):
    def test_every_line_has_methods_and_results_contracts(self) -> None:
        for kind in manifest.LINES:
            with self.subTest(line=kind):
                methods, results = _contracts(kind)
                self.assertTrue(methods, f"{kind}: no Methods contract")
                self.assertTrue(results, f"{kind}: no Results contract")

    def test_every_methods_and_results_contract_carries_the_rule_once(self) -> None:
        for kind in manifest.LINES:
            methods, results = _contracts(kind)
            for path in (*methods, *results):
                with self.subTest(line=kind, contract=path.name):
                    self.assertEqual(_flat_body(path).count(RULE), 1)

    def test_every_extent_line_allows_at_least_as_many_figures_as_tables(self) -> None:
        for kind in manifest.LINES:
            methods, results = _contracts(kind)
            for path in (*methods, *results):
                with self.subTest(line=kind, contract=path.name):
                    body = path.read_text(encoding="utf-8").split("\n---\n", 1)[1]
                    extent = re.search(r"^\*\*Extent\*\*.*$", body, re.M).group(0)
                    self.assertIn("at least as many figures", extent)

    def test_every_contract_holding_floats_carries_the_caption_rule_once(self) -> None:
        for kind in manifest.LINES:
            methods, results = _contracts(kind)
            directory = ROOT / manifest.LINES[kind].sections_dir
            others = [p for p in sorted(directory.glob("*.md")) if FLOAT_SECTIONS.search(_section(p))]
            for path in (*methods, *results, *others):
                with self.subTest(line=kind, contract=path.name):
                    self.assertEqual(_flat_body(path).count(CAPTION), 1)

    def test_every_contract_that_speaks_of_captions_carries_the_caption_rule(self) -> None:
        for kind in manifest.LINES:
            for path in sorted((ROOT / manifest.LINES[kind].sections_dir).glob("*.md")):
                body = _flat_body(path)
                if "caption" in body.replace(CAPTION, "").lower():
                    with self.subTest(line=kind, contract=path.name):
                        self.assertIn(CAPTION, body)


if __name__ == "__main__":
    unittest.main()
