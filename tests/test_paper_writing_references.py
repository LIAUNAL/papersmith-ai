"""`paper-writing` is a core plus slices, and every agent reads only its slices.

The skill used to be one 220 KB `SKILL.md`. Pi and OpenCode read at most
50 KB in one read, and no agent reached `write` (from about line 1,500) in
one read, so the doctrine an agent was told to "load and follow" was, past
its first quarter, doctrine it never saw. The skill is now a core
(`SKILL.md`) plus one file per section under `references/`, each named by a
`Section reference:` line where the section stood, and each agent names the
slices it reads.

These tests hold that shape: every reference a reader is sent to exists,
every reference file is reachable from the core, every file fits in one
read, and no agent is told to load the whole skill again.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from skill_text import (  # noqa: E402  (path set above)
    SECTION_REFERENCE_RE, section_references, skill_text)

ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = ROOT / "skills" / "paper-writing"
SKILL_MD = SKILL_DIR / "SKILL.md"
REFERENCES = SKILL_DIR / "references"
AGENTS = ROOT / ".claude" / "agents"
PROJECTED_AGENT_DIRS = (".opencode/agents", ".agents/agents", ".pi/agents")

#: The one-read cap of Pi's and OpenCode's file reader.
SINGLE_READ_CAP = 50 * 1024

#: Every agent that `paper-writing` delegates a stretch to.
PAPER_WRITING_AGENTS = (
    "redactor", "contract-auditor", "section-grounding-auditor", "ai-auditor",
    "style-sampler", "insumos-observer", "translator",
    "translation-style-reviewer", "diagram-author", "figure-auditor",
    "figure-visual-reviewer", "venue-adapter", "paper-reviewer",
)

#: A path into this skill's `references/`, written relative to the skill
#: (`references/x.md`) or from the repository (`skills/paper-writing/...`,
#: `.claude/skills/paper-writing/...`). Another skill's `references/` does not
#: match: the prefix before `references/` is either this skill or nothing.
REFERENCE_PATH_RE = re.compile(
    r"(?:(?<=[\s`(\"'])|^)(?:(?:\.claude/)?skills/paper-writing/)?"
    r"references/([a-z0-9-]+\.md)", re.MULTILINE)

#: The agent's own line naming each slice it reads.
AGENT_SECTION_LINE_RE = re.compile(
    r"^Section reference: `\.claude/skills/paper-writing/references/"
    r"(?P<name>[a-z0-9-]+\.md)`\. Read it [^\n]+$", re.MULTILINE)


#: Lines the single 220 KB file already repeated in several sections before
#: the split, and that therefore sit in several slices now: the per-stretch
#: "no Task-tool delegation" paragraph (each copy names its own stretch's tool
#: boundary) and two wrapped lines that two unrelated sections happen to share.
#: A line outside this set that shows up in two files was copied, not moved.
REPEATED_BEFORE_THE_SPLIT = frozenset({
    "**On a harness with no Task-tool delegation** (OpenCode projects these",
    "agents as `mode: subagent` per `OPENCODE.md`, Antigravity reads them from",
    "`.agents/agents/` per `.agents/AGENTS.md`, and Pi reads its projection only",
    "when the third-party `pi-subagents` package is installed per",
    "`.pi/APPEND_SYSTEM.md`; a Pi session without that package, or any session",
    "whose agent is not registered, has none):",
    "run this stretch in-process, as one step, in the same order, holding to the",
    "same measure-before-delegating gate before starting. The tool boundary the",
    "the orchestrator's own discipline to hold, not a structural guarantee —",
    "treat any action that would have needed a scoped-out tool as a stop, not a",
    "`repository-url`, `keyword-bounds`, `classification-line`, `ethics-approval`,",
    "exists and no section under `sections/` is empty, and note whether",
})

#: A pointer to a heading by its quoted title: `"Venue adaptation" below`.
HEADING_POINTER_RE = re.compile(r'"([^"]{3,160}?)"\)? (?:below|above)\b')


def slice_files() -> list[Path]:
    return [SKILL_MD, *sorted(REFERENCES.glob("*.md"))]


def map_rows() -> dict[str, str]:
    core = SKILL_MD.read_text(encoding="utf-8")
    rows = {}
    for agent in PAPER_WRITING_AGENTS:
        row = re.search(rf"^\| `{re.escape(agent)}` \|.*$", core, re.MULTILINE)
        assert row, f"the delegation map has no row for {agent}"
        rows[agent] = row.group(0)
    return rows


def agent_body(name: str) -> str:
    return (AGENTS / f"{name}.md").read_text(encoding="utf-8").split("---\n", 2)[2]


class ReferencesExistTests(unittest.TestCase):

    def test_every_reference_the_core_names_exists(self) -> None:
        named = REFERENCE_PATH_RE.findall(SKILL_MD.read_text(encoding="utf-8"))
        self.assertTrue(named, "the core names no reference")
        for name in sorted(set(named)):
            with self.subTest(reference=name):
                self.assertTrue((REFERENCES / name).is_file(),
                                f"SKILL.md names references/{name}, which does not exist")

    def test_every_reference_an_agent_names_exists(self) -> None:
        for agent in PAPER_WRITING_AGENTS:
            named = REFERENCE_PATH_RE.findall(agent_body(agent))
            with self.subTest(agent=agent):
                self.assertTrue(named, f"{agent} names no reference slice")
                for name in sorted(set(named)):
                    self.assertTrue((REFERENCES / name).is_file(),
                                    f"{agent} names references/{name}, which does not exist")

    def test_every_reference_file_is_named_by_the_core(self) -> None:
        named = set(REFERENCE_PATH_RE.findall(SKILL_MD.read_text(encoding="utf-8")))
        files = sorted(path.name for path in REFERENCES.glob("*.md"))
        self.assertTrue(files, "references/ holds no Markdown file")
        self.assertEqual([name for name in files if name not in named], [],
                         "these reference files are reachable from no line of the core")

    def test_every_section_reference_line_names_a_file(self) -> None:
        lines = section_references(SKILL_MD)
        self.assertTrue(lines, "the core carries no `Section reference:` line")
        for path in lines:
            with self.subTest(reference=path.name):
                self.assertTrue(path.is_file(), path)


class SingleReadTests(unittest.TestCase):

    def test_the_core_fits_in_one_read(self) -> None:
        self.assertLess(SKILL_MD.stat().st_size, SINGLE_READ_CAP)

    def test_every_reference_fits_in_one_read(self) -> None:
        for path in sorted(REFERENCES.iterdir()):
            with self.subTest(reference=path.name):
                self.assertLess(path.stat().st_size, SINGLE_READ_CAP)


class AgentsReadSlicesTests(unittest.TestCase):

    def test_no_agent_is_told_to_load_the_whole_skill(self) -> None:
        for agent in PAPER_WRITING_AGENTS:
            with self.subTest(agent=agent):
                flat = " ".join(agent_body(agent).split())
                self.assertNotIn("Load it and follow it", flat)

    def test_the_skill_line_still_comes_first(self) -> None:
        for agent in PAPER_WRITING_AGENTS:
            body = agent_body(agent)
            with self.subTest(agent=agent):
                first = re.search(r"^Skill: (.*)$", body, re.MULTILINE)
                self.assertIsNotNone(first, f"{agent} has no `Skill:` line")
                self.assertTrue(first.group(1).startswith(
                    "`.claude/skills/paper-writing/SKILL.md`"), first.group(0))
                self.assertEqual(
                    re.findall(r"skills/([\w-]+)/SKILL\.md", body)[0], "paper-writing")
                slices = AGENT_SECTION_LINE_RE.search(body)
                self.assertIsNotNone(slices, f"{agent} names no `Section reference:` line")
                self.assertLess(first.start(), slices.start(),
                                f"{agent}: a slice line comes before the `Skill:` line")

    def test_the_core_hands_every_agent_its_slices(self) -> None:
        """The delegation map names, per agent, the exact phrase that makes
        it reachable and the files an agent reads; an agent file and the map
        name the same slices."""
        core = SKILL_MD.read_text(encoding="utf-8")
        for agent in PAPER_WRITING_AGENTS:
            with self.subTest(agent=agent):
                row = re.search(rf"^\| `{re.escape(agent)}` \|.*$", core, re.MULTILINE)
                self.assertIsNotNone(row, f"the delegation map has no row for {agent}")
                self.assertIn(f"delegates to the `{agent}` agent", row.group(0))
                self.assertIn("Measure this before delegating", row.group(0))
                mapped = set(re.findall(r"`references/([a-z0-9-]+\.md)`", row.group(0)))
                read = set(AGENT_SECTION_LINE_RE.findall(agent_body(agent)))
                self.assertEqual(read, mapped)


class SectionReferenceExpansionTests(unittest.TestCase):

    def test_a_section_reference_line_is_the_only_pointer_form(self) -> None:
        """Every `Section reference:` line in the core is the expandable
        form, so `skill_text` never leaves a moved section unread."""
        core = SKILL_MD.read_text(encoding="utf-8")
        loose = [line for line in core.splitlines()
                 if line.startswith("Section reference:")
                 and not SECTION_REFERENCE_RE.fullmatch(line)]
        self.assertEqual(loose, [])


class NothingCopiedTests(unittest.TestCase):

    def test_every_slice_appears_once_verbatim_in_the_expanded_skill(self) -> None:
        expanded = skill_text(SKILL_MD)
        for path in section_references(SKILL_MD):
            with self.subTest(reference=path.name):
                body = path.read_text(encoding="utf-8").rstrip("\n")
                self.assertEqual(expanded.count(body), 1)

    def test_no_long_line_sits_in_two_files(self) -> None:
        seen: dict[str, set[str]] = {}
        for path in slice_files():
            for line in path.read_text(encoding="utf-8").splitlines():
                text = line.strip()
                if len(text) < 40 or re.fullmatch(r"[|\-\s:]+", text):
                    continue
                seen.setdefault(text, set()).add(path.name)
        shared = {text: sorted(names) for text, names in seen.items()
                  if len(names) > 1 and text not in REPEATED_BEFORE_THE_SPLIT}
        self.assertEqual(shared, {})


class DelegationMapTests(unittest.TestCase):

    def test_every_cited_precondition_is_in_the_slice_the_row_names(self) -> None:
        for agent, row in map_rows().items():
            with self.subTest(agent=agent):
                cited = re.search(r"\*\*Measure this before delegating \(([^)]+)\)\*\*, "
                                  r"in `references/([a-z0-9-]+\.md)`", row)
                if cited is None:
                    self.assertIn("No **Measure this before delegating** paragraph", row)
                    for path in slice_files():
                        self.assertNotRegex(
                            path.read_text(encoding="utf-8"),
                            rf"Measure this before delegating \([^)]*\b{re.escape(agent)}\b",
                            f"{agent}'s row says no precondition is written, but {path.name} has one")
                    continue
                label, name = cited.groups()
                self.assertIn(f"**Measure this before delegating ({label}):**",
                              (REFERENCES / name).read_text(encoding="utf-8"))

    def test_every_row_names_the_slices_its_agent_reads(self) -> None:
        for agent, row in map_rows().items():
            with self.subTest(agent=agent):
                mapped = set(re.findall(r"`references/([a-z0-9-]+\.md)`", row))
                read = set(AGENT_SECTION_LINE_RE.findall(
                    (AGENTS / f"{agent}.md").read_text(encoding="utf-8")))
                self.assertEqual(mapped, read)


class PointerTests(unittest.TestCase):

    def test_every_quoted_heading_pointer_names_a_heading_in_its_own_file(self) -> None:
        for path in slice_files():
            text = path.read_text(encoding="utf-8")
            headings = [re.sub(r"^#+ ", "", line).strip()
                        for line in text.splitlines() if re.match(r"#{1,6} ", line)]
            for match in HEADING_POINTER_RE.finditer(" ".join(text.split())):
                with self.subTest(file=path.name, pointer=match.group(1)):
                    self.assertTrue(any(h.startswith(match.group(1)) for h in headings),
                                    f"{path.name} points at {match.group(0)!r}, a heading it does not hold")

    def test_every_projected_reference_path_exists(self) -> None:
        for directory in PROJECTED_AGENT_DIRS:
            for agent in PAPER_WRITING_AGENTS:
                body = (ROOT / directory / f"{agent}.md").read_text(encoding="utf-8")
                named = re.findall(r"skills/paper-writing/references/[\w.-]+", body)
                with self.subTest(agent=f"{directory}/{agent}"):
                    self.assertTrue(named)
                    for rel in sorted(set(named)):
                        self.assertTrue((ROOT / rel).is_file(), rel)


if __name__ == "__main__":
    unittest.main()
