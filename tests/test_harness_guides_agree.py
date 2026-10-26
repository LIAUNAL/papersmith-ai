"""The four harness entry guides route to the same canonical sources.

Claude Code reads CLAUDE.md, OpenCode OPENCODE.md, Antigravity .agents/AGENTS.md
and Pi .pi/APPEND_SYSTEM.md. Their "Canonical context" lists drifted apart
(release procedure and repository maintenance missing from some), so an agent's
map of the project depended on which harness it ran in.
"""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUIDES = ("CLAUDE.md", "OPENCODE.md", ".agents/AGENTS.md", ".pi/APPEND_SYSTEM.md")


def canonical_context(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    start = lines.index("## Canonical context") + 1
    end = next(i for i in range(start, len(lines)) if lines[i].startswith("## "))
    return [line for line in lines[start:end] if line.strip()]


class HarnessGuidesAgreeTests(unittest.TestCase):
    def test_every_guide_lists_the_same_canonical_context(self) -> None:
        reference = canonical_context(ROOT / GUIDES[0])
        self.assertTrue(reference)
        for guide in GUIDES[1:]:
            self.assertEqual(canonical_context(ROOT / guide), reference, guide)


if __name__ == "__main__":
    unittest.main()
