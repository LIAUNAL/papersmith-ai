"""The agents table of the Archify Flow pane.

``get_agents_view(root)`` reads every ``.claude/agents/*.md`` of the workspace
and answers, per agent: its name, its role (the description's first sentence)
and full description, the skill it is bound to (the first ``skills/<x>/SKILL.md``
its body names), its stretch, its tools, its tramo (``AGENT_STAGES``), the
dashboard phase(s) it acts in as ``"Phase N — <label>"`` and the harness
projections that carry it. Bounded and contained: it never raises; whatever it
cannot read becomes a line in ``warnings``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from . import phase_actions
from .health_inspector import _frontmatter
from .state_extractor import AGENT_STAGES

#: Harness projections an agent definition can be generated into.
HARNESS_DIRS: tuple[str, ...] = (".claude/agents", ".opencode/agents", ".pi/agents", ".agents/agents")

#: Tramo (``AGENT_STAGES`` value) -> the ``phase_actions.STAGES`` phase it runs in.
TRAMO_PHASES: dict[str, tuple[str, ...]] = {
    "plausibility": ("plausibility",),
    "ingestion": ("ingestion",),
    "proposal": ("proposal",),
    "implementation": ("poc_experiments",),
    "experimental-deliberation": ("poc_experiments",),
    "experimental-implementation": ("poc_experiments",),
    "credentials": ("poc_experiments",),
    "remote": ("poc_experiments",),
    "writing": ("writing",),
    "figures": ("figures",),
    "paper": ("paper",),
    "audit": ("audit",),
}

#: Agents that also act in a phase beyond their tramo's.
EXTRA_PHASES: dict[str, tuple[str, ...]] = {
    # Its report is what the operator reads before running `declare`.
    "insumos-observer": ("declarations",),
}

MAX_AGENTS = 200
MAX_BYTES = 256_000

_SKILL_RE = re.compile(r"(?<![\w-])skills/([a-z0-9][a-z0-9_-]*)/SKILL\.md")
_SENTENCE_RE = re.compile(r"^(.+?[.!?])(?=\s|$)", re.S)


def _phase_label(stage: str) -> str:
    number = phase_actions.STAGES.index(stage) + 1
    return f"Phase {number} — {phase_actions.PHASE_LABELS.get(stage, stage)}"


def _phases(name: str, tramo: str | None) -> list[str]:
    stages = list(TRAMO_PHASES.get(tramo or "", ())) + list(EXTRA_PHASES.get(name, ()))
    ordered = sorted({s for s in stages if s in phase_actions.STAGES}, key=phase_actions.STAGES.index)
    return [_phase_label(stage) for stage in ordered]


def _first_sentence(text: str) -> str:
    match = _SENTENCE_RE.match(text.strip())
    return (match.group(1) if match else text).strip()


def _agent(root: Path, path: Path, warnings: list[str]) -> dict[str, Any]:
    name = path.stem
    try:
        if path.stat().st_size > MAX_BYTES:
            warnings.append(f"{name}: definition larger than {MAX_BYTES} bytes, skipped")
            body, meta = "", {}
        else:
            body = path.read_text(encoding="utf-8", errors="replace")
            meta = _frontmatter(path)
    except OSError as exc:
        warnings.append(f"{name}: unreadable ({exc.__class__.__name__})")
        body, meta = "", {}
    if not meta:
        warnings.append(f"{name}: no frontmatter")
    description = str(meta.get("description", "")).replace('\\"', '"').strip()
    skill_match = _SKILL_RE.search(body)
    tools = [t.strip() for t in str(meta.get("tools", "")).split(",") if t.strip()]
    tramo = AGENT_STAGES.get(name)
    if tramo is None:
        warnings.append(f"{name}: not mapped to a tramo (AGENT_STAGES)")
    return {
        "name": name,
        "role": _first_sentence(description),
        "description": description,
        "skill": skill_match.group(1) if skill_match else "",
        "stretch": str(meta.get("stretch", "")),
        "tools": tools,
        "tramo": tramo or "",
        "phases": _phases(name, tramo),
        "harnesses": [d for d in HARNESS_DIRS if (root / d / path.name).is_file()],
    }


def get_agents_view(root: Path | str) -> dict[str, Any]:
    """Every shipped agent with its role, skill, stretch, tools, phases and harnesses."""
    warnings: list[str] = []
    agents: list[dict[str, Any]] = []
    try:
        base = Path(root)
        agents_dir = base / ".claude" / "agents"
        if not agents_dir.is_dir():
            return {"agents": [], "warnings": ["no .claude/agents/ directory in this workspace"]}
        paths = sorted(agents_dir.glob("*.md"))
        if len(paths) > MAX_AGENTS:
            warnings.append(f"{len(paths)} agent definitions; showing the first {MAX_AGENTS}")
            paths = paths[:MAX_AGENTS]
        for path in paths:
            try:
                agents.append(_agent(base, path, warnings))
            except Exception as exc:  # noqa: BLE001 - one bad file never hides the rest
                warnings.append(f"{path.stem}: {exc.__class__.__name__}")
    except Exception as exc:  # noqa: BLE001 - the dashboard never fails on this table
        warnings.append(f"agents view unavailable: {exc.__class__.__name__}")
    return {"agents": agents, "warnings": warnings}
