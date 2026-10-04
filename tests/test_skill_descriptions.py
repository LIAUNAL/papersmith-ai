"""The Agent Skills description budget, enforced over every shipped skill.

A skill's ``description`` is its routing signal: Pi tells the agent to load a
skill when the task matches its description, and
:func:`papersmith.generators.derive_command_description` derives each slash
command's own description from the same value's first sentence. Pi validates it
against the Agent Skills spec and rejects anything longer than
``MAX_DESCRIPTION_LENGTH = 1024`` (``dist/core/skills.js:11``; the check is
``validateDescription`` at 80-87). Pi warns and still loads, so the defect is
invisible in a run and other harnesses may simply enforce it.

Two of the ten shipped skills were over that budget when this test was
written -- ``remote-execution`` 1814 and ``paper-writing`` 1680, against a next
longest of 624 -- so the ceiling is a real bound rather than a tight one. It is
a test and not a lint on purpose: the next description that grows past it fails
here, instead of printing a warning nobody reads.

Counted in UTF-16 code units, which is the unit JavaScript's ``length`` uses,
because the runtime that defines the ceiling is the one that has to agree with
the count.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from papersmith.generators import derive_command_description

#: The Agent Skills spec's own ceiling, as Pi implements it.
MAX_DESCRIPTION_LENGTH = 1024

FORGE_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = FORGE_ROOT / "skills"

#: Enough to prove the discovery below is not silently matching nothing. The
#: roster itself is asserted in ``test_workspace_skills_e2e``, so adding a skill
#: needs no edit here.
MINIMUM_SKILLS = 10


def skill_docs() -> list[Path]:
    """Every top-level skill's ``SKILL.md``, sorted by name.

    ``_``-prefixed directories are engine shelves, not commands
    (``generators.collect_commands`` skips them silently), so they are skipped
    here for the same reason.
    """
    return sorted(
        path / "SKILL.md"
        for path in SKILLS_DIR.iterdir()
        if path.is_dir() and not path.name.startswith("_")
        and (path / "SKILL.md").is_file()
    )


def frontmatter_lines(path: Path) -> list[str]:
    """The lines between the opening and closing ``---``, or a failure."""
    lines = path.read_text(encoding="utf-8").split("\n")
    if not lines or lines[0] != "---":
        raise AssertionError(f"{path} does not open its frontmatter on line 1")
    try:
        closing = lines.index("---", 1)
    except ValueError:  # pragma: no cover - only reachable through a defect
        raise AssertionError(f"{path} never closes its frontmatter") from None
    return lines[1:closing]


def description_value(path: Path) -> str:
    """The ``description`` value, unquoted, exactly as a harness reads it."""
    line = frontmatter_lines(path)[1]
    raw = line[len("description:"):].strip()
    if raw[:1] in {'"', "'"}:
        return str(ast.literal_eval(raw))
    return raw


class SkillDescriptionTests(unittest.TestCase):
    def test_the_discovery_finds_the_shipped_skills(self) -> None:
        """A discovery that silently matched nothing would make every check
        below vacuously pass, so the count is asserted first."""
        found = [path.parent.name for path in skill_docs()]
        self.assertGreaterEqual(
            len(found), MINIMUM_SKILLS,
            f"only found {found}; the skill tree is not where this test looks")
        self.assertNotIn("_core", found)

    def test_every_frontmatter_is_exactly_name_then_description(self) -> None:
        """One shape for every skill: ``---``, ``name``, ``description``, ``---``.

        The single line matters beyond tidiness: a folded or multi-line scalar
        would be read differently by the harnesses that consume it, and
        ``derive_command_description`` would derive a command description from
        a fragment.
        """
        for path in skill_docs():
            with self.subTest(skill=path.parent.name):
                lines = frontmatter_lines(path)
                self.assertEqual(len(lines), 2, f"{path}: extra frontmatter key in {lines!r}")
                self.assertEqual(lines[0], f"name: {path.parent.name}", path)
                self.assertTrue(lines[1].startswith("description: "), path)

    def test_every_description_fits_the_spec_budget(self) -> None:
        """Pi's own ceiling, counted the way Pi counts it."""
        for path in skill_docs():
            with self.subTest(skill=path.parent.name):
                value = description_value(path)
                units = len(value.encode("utf-16-le")) // 2
                self.assertLessEqual(
                    units, MAX_DESCRIPTION_LENGTH,
                    f"{path.parent.name}: description is {units} UTF-16 code "
                    f"units, {units - MAX_DESCRIPTION_LENGTH} over the "
                    f"{MAX_DESCRIPTION_LENGTH} the Agent Skills spec allows")

    def test_every_description_states_its_own_trigger(self) -> None:
        """The routing convention every shipped skill follows: the description
        opens with ``Trigger:`` so the matched task, not the skill's internals,
        is what a reader sees first."""
        for path in skill_docs():
            with self.subTest(skill=path.parent.name):
                value = description_value(path)
                self.assertTrue(value.startswith("Trigger: "), f"{path}: {value[:60]!r}")
                self.assertGreater(len(value), len("Trigger: "), path)

    def test_the_derived_command_description_is_never_empty(self) -> None:
        """The command front door reads the first sentence of this value, so a
        description whose first sentence is empty is a command with no
        description."""
        for path in skill_docs():
            with self.subTest(skill=path.parent.name):
                derived = derive_command_description(description_value(path))
                self.assertTrue(derived.strip(), path)
                self.assertLessEqual(len(derived), len(description_value(path)))


if __name__ == "__main__":
    unittest.main()
