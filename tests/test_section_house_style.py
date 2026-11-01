"""The lab's house style travels inside each section contract.

The redactor reads only its own section's contract, so the writing and
notation guide measured on the group's Q1 method papers lives in every
contract that governs prose, as a `## LIA house style` section placed before
the parts the engine reads by position.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from skills._core.command_center import state_extractor

REPO = Path(__file__).resolve().parents[1]
SECTIONS = REPO / "sections"
GUIDED = sorted(path for path in SECTIONS.glob("0*.md"))
HEADING = "\n## LIA house style\n"


def body(path: Path) -> str:
    return path.read_text(encoding="utf-8").split("\n---\n", 1)[1]


class HouseStyleTests(unittest.TestCase):
    def test_every_prose_contract_carries_the_guide_once_before_its_disqualifiers(self) -> None:
        self.assertEqual(len(GUIDED), 9)
        for path in GUIDED:
            with self.subTest(contract=path.name):
                text = body(path)
                self.assertEqual(text.count(HEADING), 1)
                self.assertLess(text.index(HEADING), text.index("\n## Disqualifiers\n"))
                self.assertIn("Measured", text.split(HEADING, 1)[1].split("\n## ", 1)[0])

    def test_the_guide_never_moves_the_extent_the_dashboard_reads(self) -> None:
        for path in GUIDED:
            with self.subTest(contract=path.name):
                text = body(path)
                guide = text.split(HEADING, 1)[1].split("\n## ", 1)[0]
                self.assertNotRegex(guide, r"\*\*Extent\*\*")
                first = re.search(r"^\*\*Extent\*\*.*$", text, re.M).group(0)
                expected = re.match(r"\*\*Extent\*\*\s*(\d+)\s*[–-]\s*(\d+)\s*words", first)
                if expected:
                    self.assertEqual(state_extractor._extent(text),
                                     (int(expected.group(1)), int(expected.group(2))))

    def test_the_methods_guide_fixes_the_notation(self) -> None:
        guide = body(SECTIONS / "01-materials-and-methods.md").split(HEADING, 1)[1]
        for rule in (r"\mathbf{x}", r"\mathbf{X}", r"\mathbb{R}", r"\mathcal{L}",
                     r"^{\top}", r"\odot", r"\operatorname{tr}", "*where*"):
            with self.subTest(rule=rule):
                self.assertIn(rule, guide)
        self.assertIn("**Number every displayed equation.**",
                      body(SECTIONS / "01-materials-and-methods.md"))

    def test_the_title_extent_follows_the_group(self) -> None:
        self.assertIn("**Extent** title 10–13 words · keywords 3–5",
                      body(SECTIONS / "09-title-and-keywords.md"))


if __name__ == "__main__":
    unittest.main()
