"""paper_ai_usage: the pipeline record turned into the evidence a paper's
AI-use declaration needs. Read-only; never writes a byte.

    build(paper_dir, *, sessions=None) -> dict

Three sources, each read through its owner:

* the pipeline record -- `command_center.ai_history.build_ai_usage`: per
  phase, the agent roles, the harnesses (tools) whose chat sessions worked on
  it, the operator's commands, follow-ups and approvals, revisions, persisted
  decisions and errors;
* the manuscript -- `paper_venue.Manuscript` over `paper/main.tex`: every
  written block, drafted by the `redactor` agent through `write` (the only
  route a block body gets written), with its write-attempt ledger and
  evidence ledger when they exist;
* the workspace -- `.papersmith/version`: the papersmith release that ran
  the pipeline, cited with its repository URL;
* the selected venues -- `paper_venue.back_matter_placement`: where each
  venue's publisher puts the AI-use declaration and the funding statement.

`packet` attaches the result to every block in `AI_USAGE_BLOCKS`
(`sections/10-back-matter.md`, "AI-use declaration"). A source that cannot
be read degrades to `{"status": "unavailable", ...}`; it never refuses, so a
workspace without the command center still gets a packet.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paper_evidence  # noqa: E402
import paper_venue  # noqa: E402
import paper_write  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_core" / "implementation"))
from impl_refusals import Refused  # noqa: E402

#: The blocks whose packet carries the AI-usage record: the declaration
#: itself, and the set-up block that holds the Methods sentence when agents
#: generated or ran code or experiments.
AI_USAGE_BLOCKS = frozenset({
    "back-matter.bm-ai-use-declaration",
    "experimental-setup.es-training-details",
})

#: Pipeline phases in which agents generate or run code and experiments.
CODE_STAGES = ("poc_experiments",)

#: The agent that drafts every block body and the one that audits it
#: (`write --draft --audit`, `skills/paper-writing/SKILL.md`).
DRAFTING_AGENT = "redactor"
AUDITING_AGENT = "contract-auditor"

_CORE = Path(__file__).resolve().parents[2] / "_core"

#: The framework that ran the pipeline. The declaration cites its repository
#: so a reader can find the workflow that produced the paper.
FRAMEWORK_NAME = "papersmith"
FRAMEWORK_URL = "https://github.com/LIAUNAL/papersmith-ai"


def _framework(workspace: Path) -> dict:
    """The framework's name, repository and the release the workspace records
    in `.papersmith/version` (None when unreadable)."""
    try:
        version = (workspace / ".papersmith" / "version").read_text(encoding="utf-8").strip() or None
    except OSError:
        version = None
    return {"name": FRAMEWORK_NAME, "url": FRAMEWORK_URL, "version": version}


def _pipeline(workspace: Path, sessions) -> dict:
    if str(_CORE) not in sys.path:
        sys.path.insert(0, str(_CORE))
    try:
        from command_center import ai_history  # noqa: PLC0415 - optional, kit-shipped
    except ImportError as exc:
        return {"status": "unavailable", "detail": f"command center not importable: {exc.name}",
                "phases": [], "harnesses": []}
    try:
        usage = ai_history.build_ai_usage(workspace, sessions)
    except Exception as exc:  # noqa: BLE001 - one broken source never fails the packet
        return {"status": "unavailable", "detail": type(exc).__name__, "phases": [], "harnesses": []}
    return {"status": "ok", **usage}


def _drafted_blocks(paper_dir: Path) -> dict:
    try:
        manuscript = paper_venue.Manuscript(paper_dir)
    except Refused as exc:
        return {"status": "unavailable", "detail": exc.code, "blocks": [], "sections": []}
    blocks = []
    for block in manuscript.blocks:
        if not block["written"]:
            continue
        ledger = paper_write._read_ledger(paper_dir, block["id"])
        blocks.append({
            "id": block["id"], "section": block["section"],
            "drafted_by": DRAFTING_AGENT, "audited_by": AUDITING_AGENT,
            "attempts": ledger.get("attempts") if isinstance(ledger, dict) else None,
            "evidence_ledger": paper_evidence._store_path(paper_dir, block["id"]).is_file(),
        })
    sections = []
    for block in blocks:
        if block["section"] not in sections:
            sections.append(block["section"])
    return {"status": "ok", "blocks": blocks, "sections": sections}


def build(paper_dir: Path, *, sessions=None) -> dict:
    """The AI-usage record for the paper under `paper_dir` (its workspace is
    `paper_dir.parent`). `sessions` overrides each harness's session store,
    exactly as `ai_history.build_ai_history` takes it."""
    paper_dir = Path(paper_dir)
    pipeline = _pipeline(paper_dir.parent, sessions)
    drafted = _drafted_blocks(paper_dir)
    code_phases = [p["stage_id"] for p in pipeline.get("phases", []) if p.get("stage_id") in CODE_STAGES]
    return {
        "schema": 1,
        "framework": _framework(paper_dir.parent),
        "pipeline": pipeline,
        "drafted": drafted,
        "tools": pipeline.get("harnesses", []),
        "code_or_experiments_by_agents": bool(code_phases),
        "methods_sentence_required": bool(code_phases),
        "venues": paper_venue.back_matter_placement(paper_dir) if paper_dir.is_dir() else [],
        "note": ("Read-only record: the declaration states what it shows, never more. "
                 "Tool versions are not recorded; the operator supplies them."),
    }


__all__ = ["AI_USAGE_BLOCKS", "build"]
