"""The doctrine every workspace receives carries no one project's findings.

`MAINTENANCE-the-forge-carries-no-paper-inside.md` states the rule: skills and
agent definitions are shipped to every workspace, so an example lifted from one
paper's results reads as a requirement in every other paper. These phrases came
from one project's findings and reached the shipped doctrine once; none of them
is a general methodological term.
"""

from __future__ import annotations

import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

PROJECT_PHRASES = (
    "quantum hype",
    "quantum supremacy",
    "entanglement advantage",
    "parameter-shift saliency",
    "harmonic expressivity",
)


def _doctrine_files() -> list[Path]:
    files = sorted((REPO / "skills").glob("**/SKILL.md"))
    for harness in (".claude", ".agents", ".opencode", ".pi"):
        files.extend(sorted((REPO / harness / "agents").glob("*.md")))
    return files


class DoctrineCarriesNoProjectTests(unittest.TestCase):
    def test_the_scan_reads_the_shipped_doctrine(self) -> None:
        names = {path.name for path in _doctrine_files()}
        self.assertIn("SKILL.md", names)
        self.assertIn("paper-reviewer.md", names)

    def test_no_skill_or_agent_names_one_project_s_findings(self) -> None:
        for path in _doctrine_files():
            text = path.read_text(encoding="utf-8").lower()
            for phrase in PROJECT_PHRASES:
                with self.subTest(file=str(path.relative_to(REPO)), phrase=phrase):
                    self.assertNotIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
