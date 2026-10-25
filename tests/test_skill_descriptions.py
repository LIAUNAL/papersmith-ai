"""Every skill description fits the ceiling the runtime that reads it enforces.

Pi validates a skill's `description` against the Agent Skills spec and caps it
at `MAX_DESCRIPTION_LENGTH = 1024` (`dist/core/skills.js:11`). Past the cap Pi
warns and loads the skill anyway, so nothing fails and the excess simply lives
on -- which is how two descriptions came to sit at 1680 and 1814 units while
every suite stayed green.

The unit is the one JS `length` counts: UTF-16 code units. Measuring in Python
characters would call a description legal that the runtime measures as over,
which is the whole difference the guard exists to catch.

OpenCode adds the other half of its loading contract (#14): a skill's `name`
must match its directory and be lowercase alphanumeric with single hyphens.
A skill that breaks it does not error, it simply never appears.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from papersmith.generators import derive_command_description

FORGE_ROOT = Path(__file__).resolve().parents[1]
SKILLS = FORGE_ROOT / "skills"

#: Pi's ceiling, mirroring `MAX_DESCRIPTION_LENGTH` in `dist/core/skills.js`.
PI_DESCRIPTION_LIMIT = 1024

#: Skill front matter carries a long `Trigger: ...` paragraph on one line.
#: Single-line is the shape every harness's parser reads, so it is asserted
#: rather than assumed.
DESCRIPTION_RE = re.compile(r'^description:[ \t]*"(?P<value>.*)"[ \t]*$', re.MULTILINE)
NAME_RE = re.compile(r'^name:[ \t]*"?(?P<value>[^"\n]*?)"?[ \t]*$', re.MULTILINE)
#: OpenCode's `name` rule: 1-64 chars, lowercase alphanumerics joined by single hyphens.
OPENCODE_NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def _utf16_length(text: str) -> int:
    """The length JS `length` sees -- the unit the ceiling is written in."""
    return len(text.encode("utf-16-le")) // 2


def _skill_files() -> list[Path]:
    return sorted(SKILLS.glob("*/SKILL.md"))


def _description(path: Path) -> str:
    matched = DESCRIPTION_RE.search(path.read_text(encoding="utf-8"))
    if matched is None:
        raise AssertionError(
            f"{path.relative_to(FORGE_ROOT)} has no single-line double-quoted "
            "`description:` in its front matter")
    return matched.group("value")


def _name(path: Path) -> str | None:
    text = path.read_text(encoding="utf-8")
    front = text.split("---", 2)[1] if text.startswith("---") else ""
    matched = NAME_RE.search(front)
    return matched.group("value") if matched else None


def _measured() -> list[tuple[Path, str, int]]:
    return [(path, text, _utf16_length(text))
            for path, text in ((p, _description(p)) for p in _skill_files())]


class SkillDescriptionTests(unittest.TestCase):
    def test_there_is_a_description_to_measure_at_all(self) -> None:
        """A guard that measures nothing passes vacuously."""
        self.assertGreaterEqual(len(_skill_files()), 11)

    def test_every_skill_description_fits_the_pi_limit(self) -> None:
        over = [(path.relative_to(FORGE_ROOT).as_posix(), length)
                for path, _, length in _measured()
                if length > PI_DESCRIPTION_LIMIT]
        self.assertEqual(
            over, [],
            f"a skill description exceeds Pi's {PI_DESCRIPTION_LIMIT}-unit "
            f"ceiling (measured in UTF-16 code units, the unit JS `length` "
            f"counts): {over}")

    def test_every_skill_name_matches_its_directory(self) -> None:
        mismatched = [(path.parent.name, _name(path)) for path in _skill_files()
                      if _name(path) != path.parent.name]
        self.assertEqual(
            mismatched, [],
            "a skill's front-matter `name` differs from its directory, so "
            f"OpenCode does not load it: {mismatched}")

    def test_every_skill_name_satisfies_the_opencode_format(self) -> None:
        offenders = [path.parent.name for path in _skill_files()
                     if len(path.parent.name) > 64
                     or not OPENCODE_NAME_RE.fullmatch(path.parent.name)]
        self.assertEqual(
            offenders, [],
            "a skill name is not 1-64 lowercase alphanumerics joined by single "
            f"hyphens, so OpenCode does not load it: {offenders}")

    def test_every_skill_description_starts_with_the_trigger_convention(self) -> None:
        offenders = [path.relative_to(FORGE_ROOT).as_posix()
                     for path, text, _ in _measured()
                     if not text.startswith("Trigger:")]
        self.assertEqual(
            offenders, [],
            "a skill description does not open with the `Trigger:` convention "
            f"every harness routes on: {offenders}")

    def test_every_derived_command_description_is_non_empty(self) -> None:
        """`derive_command_description` keeps the first sentence, so a
        description with no sentence boundary still has to yield something."""
        empties = [path.relative_to(FORGE_ROOT).as_posix()
                   for path, text, _ in _measured()
                   if not derive_command_description(text).strip()]
        self.assertEqual(
            empties, [],
            f"a skill description derives an empty command description: {empties}")


if __name__ == "__main__":
    unittest.main()
