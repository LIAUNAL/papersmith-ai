"""The one reader every doctrine pin goes through.

A skill's `SKILL.md` may move a per-stage section into `references/` and leave
one `Stage reference:` line where the section stood. A pin that read the raw
`SKILL.md` would then lose the moved text, and a pin that read the references
on its own would lose where the text sits. `skill_text` reads both at once: it
returns the `SKILL.md` with every such line replaced, in place, by the file the
line names, so a pure move leaves every pin reading the same bytes it read
before the move. Any other file is returned as it is.
"""

from __future__ import annotations

import re
from pathlib import Path

#: The one-line pointer a moved section leaves behind in `SKILL.md`.
STAGE_REFERENCE_RE = re.compile(
    r'^Stage reference: `nextStep: "(?P<step>[a-z0-9-]+)"` is in '
    r'`(?P<path>references/[a-z0-9-]+\.md)`\. '
    r'Read it when `probe` reports this `nextStep`\.$',
    re.MULTILINE)


def stage_references(skill_md: Path) -> list[tuple[str, Path]]:
    """`(nextStep, reference path)` for every `Stage reference:` line, in order."""
    text = skill_md.read_text(encoding="utf-8")
    return [(match["step"], skill_md.parent / match["path"])
            for match in STAGE_REFERENCE_RE.finditer(text)]


def skill_text(path: Path) -> str:
    """`path`'s text, with a `SKILL.md`'s stage references expanded in place."""
    text = Path(path).read_text(encoding="utf-8")
    if Path(path).name != "SKILL.md":
        return text

    def expand(match: re.Match) -> str:
        reference = Path(path).parent / match["path"]
        return reference.read_text(encoding="utf-8").rstrip("\n")

    return STAGE_REFERENCE_RE.sub(expand, text)
