"""The lab's house style travels inside each section contract.

The redactor reads only its own section's contract, so the writing and
notation guide measured on the group's Q1 method papers lives in every
contract that governs prose, as a `## LIA house style` section placed before
the parts the engine reads by position.
"""

from __future__ import annotations

import json
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

    def test_the_conclusions_extent_follows_the_group(self) -> None:
        text = body(SECTIONS / "07-conclusions.md")
        self.assertIn("**Extent** 350–950 words · 3 to 6 paragraphs", text)
        self.assertEqual(state_extractor._extent(text), (350, 950))

    def test_the_conclusions_answer_each_contribution_once(self) -> None:
        text = body(SECTIONS / "07-conclusions.md")
        self.assertIn("**One paragraph per contribution, in the order the methods and the results", text)
        self.assertIn("**At most one headline number per contribution, identical to the results.**", text)
        disqualifiers = text.split("\n## Disqualifiers\n", 1)[1]
        for rule in ("A number that differs from the results section",
                     "New evidence:", "A contribution with no finding paragraph"):
            with self.subTest(rule=rule):
                self.assertIn(rule, disqualifiers)

    def test_the_extents_match_their_slot_tables(self) -> None:
        self.assertIn("**Extent** 1000–3950 words · 2 to 9 subsections",
                      body(SECTIONS / "01-materials-and-methods.md"))
        self.assertEqual(state_extractor._extent(body(SECTIONS / "02-experimental-setup.md")), (800, 3500))


class BackMatterTests(unittest.TestCase):
    def setUp(self) -> None:
        text = (SECTIONS / "10-back-matter.md").read_text(encoding="utf-8")
        header, self.text = text.split("\n---\n", 1)
        self.blocks = {b["id"]: b for b in json.loads(header[4:])["blocks"]}

    def test_the_ai_use_declaration_is_always_present(self) -> None:
        self.assertNotIn("optional", self.blocks["bm-ai-use-declaration"])
        self.assertIn("**Always present.**", self.text)

    def test_the_venue_templates_are_quoted_verbatim(self) -> None:
        flat = " ".join(self.text.split())
        for template in (
            "Declaration of generative AI and AI-assisted technologies in the manuscript preparation process",
            "During the preparation of this work the author(s) used [NAME OF TOOL / SERVICE] in order to "
            "[REASON]. After using this tool/service, the author(s) reviewed and edited the content as needed "
            "and take(s) full responsibility for the content of the published article.",
            "During the preparation of this manuscript/study, the author(s) used [tool name, version "
            "information] for the purposes of [description of use]. The authors have reviewed and edited the "
            "output and take full responsibility for the content of this publication.",
        ):
            with self.subTest(template=template[:40]):
                self.assertIn(template, flat)

    def test_conditional_blocks_are_optional_and_code_is_separate_from_data(self) -> None:
        for block_id in ("bm-ethics-statement", "bm-informed-consent", "bm-supplementary-materials",
                         "bm-abbreviations", "bm-highlights", "bm-graphical-abstract"):
            with self.subTest(block=block_id):
                self.assertTrue(self.blocks[block_id].get("optional"))
        self.assertNotIn("optional", self.blocks["bm-code-availability"])
        self.assertEqual([d["value"] for d in self.blocks["bm-code-availability"]["requires_declarations"]],
                         ["repository-url"])
        for block_id in ("bm-ethics-statement", "bm-informed-consent"):
            self.assertEqual([d["value"] for d in self.blocks[block_id]["requires_declarations"]],
                             ["ethics-approval"])

    def test_the_ai_disqualifiers_are_stated(self) -> None:
        disqualifiers = self.text.split("\n## Disqualifiers\n", 1)[1]
        for rule in ("An AI tool listed as an author", "No AI-use declaration.",
                     "contradict the pipeline's\n  AI-usage record"):
            with self.subTest(rule=rule):
                self.assertIn(rule, disqualifiers)


if __name__ == "__main__":
    unittest.main()
