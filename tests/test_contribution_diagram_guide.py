"""The figure that closes Materials and Methods summarizes the contribution in
detail, and one guide says how.

The contract keeps its mechanical boundary: the diagram's marked components are
the contribution roster, in order, and no dataset or baseline is one of them.
Around them the figure now carries the method's context -- the input data as
mathematical objects, the stages, the losses with their basic mathematics, and
the outputs -- following `skills/paper-writing/references/contribution-diagram.md`,
which the `diagram-author` agent loads before drafting it. The guide's own example
manifest passes the same obligation checks a real figure meets.
"""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GUIDE_REL = "skills/paper-writing/references/contribution-diagram.md"
GUIDE = REPO / GUIDE_REL
CONTRACT = REPO / "sections" / "01-materials-and-methods.md"
SPANISH_CONTRACT = (REPO / "skills" / "_core" / "command_center" / "static" / "i18n" / "es"
                    / "sections" / "01-materials-and-methods.md")
AGENT_COPIES = (".claude/agents/diagram-author.md", ".agents/agents/diagram-author.md",
                ".opencode/agents/diagram-author.md", ".pi/agents/diagram-author.md")

sys.path.insert(0, str(REPO / "skills" / "paper-writing" / "scripts"))
import paper_obligation  # noqa: E402


def guide() -> str:
    return GUIDE.read_text(encoding="utf-8")


def section(text: str, heading: str) -> str:
    start = text.index(heading)
    following = re.search(r"\n#{2,3} ", text[start + len(heading):])
    body = text[start:start + len(heading) + following.start()] if following else text[start:]
    return " ".join(body.split()) if heading.startswith("###") else body


class GuideTests(unittest.TestCase):
    def test_the_guide_names_every_part_of_the_diagram(self) -> None:
        text = guide()
        for heading in ("## 1. Inputs", "## 2. Representation", "## 3. Core stages",
                        "## 4. Contribution panels", "## 5. Mathematics inside the figure",
                        "## 6. Objectives", "## 7. Outputs", "## 8. Auxiliary flows",
                        "## 9. Legend and caption"):
            with self.subTest(heading=heading):
                self.assertIn(heading, text)

    def test_the_core_stages_choose_architecture_or_flowchart(self) -> None:
        stages = section(guide(), "## 3. Core stages")
        self.assertIn("network architecture", stages)
        self.assertIn("flowchart", stages)

    def test_the_guide_restates_the_configured_style_rules(self) -> None:
        text = guide()
        for rule in ("0.70", "0.90", "widthFraction", "\\fontsize", "Overfull", "sentence case",
                     "% node:", "\\tikzset", "#4F7CAC", "#D96855", "#20252B", "grayscale"):
            with self.subTest(rule=rule):
                self.assertIn(rule, text)

    def test_the_guide_names_what_never_enters_the_figure(self) -> None:
        never = section(guide(), "## Never in the figure")
        for item in ("dataset", "baseline", "metric", "measured"):
            with self.subTest(item=item):
                self.assertIn(item, never)

    def test_the_example_manifest_passes_the_obligation_checks(self) -> None:
        block = re.search(r"```json\n(\{.*?\})\n```", section(guide(), "## The manifest"), re.S)
        self.assertIsNotNone(block, "the guide shows its example manifest as a json block")
        manifest = json.loads(block.group(1))
        contract = json.loads(CONTRACT.read_text(encoding="utf-8").split("\n---\n")[0].lstrip("-\n"))
        figure = next(b["figure"] for b in contract["blocks"] if b.get("figure"))
        roster = list(manifest["components"])
        paper_obligation.check_components(figure, manifest["components"], roster)
        paper_obligation.check_excluded(figure, manifest["components"])
        paper_obligation.check_caption(figure, manifest["components"], manifest["encodings"],
                                       manifest["caption"])
        self.assertGreaterEqual(manifest["widthFraction"], 0.9)


class ContractTests(unittest.TestCase):
    def test_the_summary_diagram_points_to_the_guide_and_its_parts(self) -> None:
        summary = section(CONTRACT.read_text(encoding="utf-8"), "### The summary diagram")
        self.assertIn(GUIDE_REL, summary)
        for part in ("as mathematical objects", "losses", "outputs", "% node:"):
            with self.subTest(part=part):
                self.assertIn(part, summary)

    def test_the_spanish_copy_carries_the_same_rule(self) -> None:
        summary = section(SPANISH_CONTRACT.read_text(encoding="utf-8"), "### El diagrama de síntesis")
        self.assertIn(GUIDE_REL, summary)
        self.assertIn("como objetos matemáticos", summary)


class AgentTests(unittest.TestCase):
    def test_every_harness_copy_of_the_author_loads_the_guide(self) -> None:
        for rel in AGENT_COPIES:
            with self.subTest(agent=rel):
                self.assertIn(GUIDE_REL, (REPO / rel).read_text(encoding="utf-8"))

    def test_the_skill_names_the_guide_where_it_delegates_the_drawing(self) -> None:
        skill = (REPO / "skills" / "paper-writing" / "SKILL.md").read_text(encoding="utf-8")
        start = skill.index("**Drafting the diagram itself delegates to the `diagram-author` agent.**")
        self.assertIn(GUIDE_REL, skill[start:start + 1500])


if __name__ == "__main__":
    unittest.main()
