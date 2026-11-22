"""The agents table of the Archify Flow pane.

``get_agents_view(root)`` reads every ``.claude/agents/*.md`` of the workspace
and answers, per agent: its name, its role (the description's first sentence)
and full description, the skill it is bound to (the first ``skills/<x>/SKILL.md``
its body names), its stretch, its tools, its tramo (``AGENT_STAGES``), the
dashboard phase(s) it acts in as ``"Phase N — <label>"`` and the harness
projections that carry it. Bounded and contained: it never raises; whatever it
cannot read becomes a line in ``warnings``.

In a review workspace (``paper_kind: "review"``, read from the workspace on
every call) the view says ``paper_kind`` and an agent's phases are the review
steps (``review_board``) that use it, as ``"Phase N — <step label>"``:

* the steps that reuse the actions of the experimental phases its tramo and
  :data:`EXTRA_PHASES` give it (the review's writing step reuses the
  scaffolding, declarations and writing actions, and so on);
* the steps whose ``agent`` text names it (``diagram-author`` in synthesis);
* the prompt reviewer, every step with a prompt;
* only when none of those holds, the steps whose skills hold its bound skill.

``agents`` still lists every agent (the office shows them all); an agent no
review step uses has no phase, and the table leaves it out.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from . import phase_actions, review_board
from .health_inspector import _frontmatter
from .state_extractor import AGENT_STAGES, decision

REVIEW = "review"

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
    # The prompt gate reviews the prompt of every phase box that runs a skill.
    "prompt-reviewer": tuple(stage for stage, entry in phase_actions.ACTIONS.items()
                             if any(action["kind"] == "prompt" for action in entry["actions"])),
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


def _review_label(step: str) -> str:
    number = review_board.REVIEW_STAGES.index(step) + 1
    return f"Phase {number} — {review_board.REVIEW_LABELS.get(step, step)}"


def _review_steps_of(stage: str) -> set[str]:
    """The review steps that reuse an action of the experimental ``stage``."""
    own = (phase_actions.ACTIONS.get(stage) or {}).get("actions", ())
    return {step for step in review_board.REVIEW_STAGES
            if any(action in own for action in review_board.REVIEW_ACTIONS[step]["actions"])}


#: The review steps whose box runs a skill: the prompt reviewer reviews them.
REVIEW_PROMPT_STEPS: tuple[str, ...] = tuple(
    step for step in review_board.REVIEW_STAGES
    if any(action["kind"] == "prompt" for action in review_board.REVIEW_ACTIONS[step]["actions"]))

_NAME_RE = re.compile(r"[a-z0-9][a-z0-9-]*")


def _review_phases(name: str, tramo: str | None, skill: str) -> list[str]:
    extra = () if name == "prompt-reviewer" else EXTRA_PHASES.get(name, ())
    steps: set[str] = set()
    for stage in (*TRAMO_PHASES.get(tramo or "", ()), *extra):
        steps |= _review_steps_of(stage)
    steps |= {step for step in review_board.REVIEW_STAGES
              if name in _NAME_RE.findall(str(review_board.REVIEW_ACTIONS[step].get("agent", "")))}
    if name == "prompt-reviewer":
        steps |= set(REVIEW_PROMPT_STEPS)
    if not steps and skill:
        steps = {step for step in review_board.REVIEW_STAGES
                 if skill in review_board.REVIEW_ACTIONS[step].get("skills", ())}
    return [_review_label(step) for step in review_board.REVIEW_STAGES if step in steps]


def _first_sentence(text: str) -> str:
    match = _SENTENCE_RE.match(text.strip())
    return (match.group(1) if match else text).strip()


def _agent(root: Path, path: Path, warnings: list[str], kind: str = "experimental") -> dict[str, Any]:
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
        "model": str(meta.get("model", "")).strip(),
        "tramo": tramo or "",
        "phases": (_review_phases(name, tramo, skill_match.group(1) if skill_match else "")
                   if kind == REVIEW else _phases(name, tramo)),
        "harnesses": [d for d in HARNESS_DIRS if (root / d / path.name).is_file()],
    }


def get_agents_view(root: Path | str) -> dict[str, Any]:
    """Every shipped agent with its role, skill, stretch, tools, phases and
    harnesses; in a review workspace the phases are review steps."""
    warnings: list[str] = []
    agents: list[dict[str, Any]] = []
    line: dict[str, str] = {}
    try:
        base = Path(root)
        kind = REVIEW if decision.current_line(base) == REVIEW else "experimental"
        line = {"paper_kind": REVIEW} if kind == REVIEW else {}
        agents_dir = base / ".claude" / "agents"
        if not agents_dir.is_dir():
            return {"agents": [], "warnings": ["no .claude/agents/ directory in this workspace"], **line}
        paths = sorted(agents_dir.glob("*.md"))
        if len(paths) > MAX_AGENTS:
            warnings.append(f"{len(paths)} agent definitions; showing the first {MAX_AGENTS}")
            paths = paths[:MAX_AGENTS]
        for path in paths:
            try:
                agents.append(_agent(base, path, warnings, kind))
            except Exception as exc:  # noqa: BLE001 - one bad file never hides the rest
                warnings.append(f"{path.stem}: {exc.__class__.__name__}")
    except Exception as exc:  # noqa: BLE001 - the dashboard never fails on this table
        warnings.append(f"agents view unavailable: {exc.__class__.__name__}")
    return {"agents": agents, "warnings": warnings, **line}
