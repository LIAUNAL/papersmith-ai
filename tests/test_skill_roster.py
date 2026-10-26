"""A skill count written in the harness guides matches `skills/*/SKILL.md` (#70).

CLAUDE.md and OPENCODE.md once declared "eleven top-level skills" while the
roster had grown to sixteen.
The guides now point at `skills/*/SKILL.md` instead of counting; this guard
derives the roster from disk and fails if a spelled-out count comes back wrong.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUIDES = [ROOT / "CLAUDE.md", ROOT / "OPENCODE.md", ROOT / ".agents" / "AGENTS.md",
          *sorted((ROOT / "src" / "papersmith" / "templates").glob("*.md.tpl"))]
NUMBERS = ("zero one two three four five six seven eight nine ten eleven twelve "
           "thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty"
           ).split()
COUNT = re.compile(r"\b(" + "|".join(NUMBERS) + r"|\d+)\s+(?:top-level\s+|canonical\s+)?"
                   r"skills\b", re.IGNORECASE)


def roster() -> int:
    return len(list((ROOT / "skills").glob("*/SKILL.md")))


def as_int(token: str) -> int:
    return int(token) if token.isdigit() else NUMBERS.index(token.lower())


class SkillRosterTest(unittest.TestCase):
    def test_declared_skill_roster_matches_canonical_skills(self) -> None:
        n = roster()
        self.assertGreater(n, 0)
        for guide in GUIDES:
            text = guide.read_text(encoding="utf-8")
            with self.subTest(guide=guide.relative_to(ROOT).as_posix()):
                wrong = [m.group(0) for m in COUNT.finditer(text)
                         if as_int(m.group(1)) != n]
                self.assertEqual(wrong, [], f"the roster has {n} skills")


if __name__ == "__main__":
    unittest.main()
