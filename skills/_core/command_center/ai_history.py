"""The "Historia con IA" pane: what happened in each phase, with whom.

``build_ai_history(root, fases)`` answers, per dashboard phase (the ``fases``
list of ``/api/status``): its gate, a colour and a short timeline of the
interactions that phase had. Read-only and bounded; it never raises. Sources:

* ``decisions``: :func:`decisions.build_decisions` (declarations, the proposal
  and experimental deliberation sidecars, the remote-execution ledgers).
* ``revisions``: managed proposal revisions ``proposals/*-rNN.md``.
* ``chats``: this workspace's sessions of every harness (Claude Code, Pi,
  OpenCode; see :mod:`ai_transcripts`). A phase command opens that phase; the
  operator's follow-up messages, the agent's replies and failed tool calls
  are attributed to it until the next phase command.

Colour: ``red`` when the phase has not passed and shows no friction;
``orange`` when it shows errors, rework (more than one revision) or user
iterations (a follow-up message, a repeated command, a deliberation edit);
``green`` when it passed with none of those.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from . import ai_transcripts, decisions, phase_actions

MAX_PHASE_EVENTS = 60
TEXT_MAX = 240

#: decisions source -> the phase it belongs to.
SOURCE_STAGES = {
    "declarations": "declarations",
    "proposal": "proposal",
    "experiment": "poc_experiments",
    "remote-execution": "poc_experiments",
}

#: decisions event kinds that count as an error.
ERROR_KINDS = frozenset({"errored"})
_ERROR_OUTCOMES = ("Rejected", "Inconsistent", "Recovery required")

_REVISION_RE = re.compile(r"-r(\d+)\.md$")


def _clip(text: Any, limit: int = TEXT_MAX) -> str:
    value = " ".join(str(text or "").split())
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _revision_events(root: Path) -> list[dict[str, Any]]:
    out = []
    try:
        names = sorted(p.name for p in (root / "proposals").glob("*-r*.md") if p.is_file())
    except OSError:
        return out
    for name in names[:200]:
        found = _REVISION_RE.search(name)
        if found:
            out.append({"ts": None, "source": "revisions", "kind": "revision",
                        "summary": f"Revisión r{found.group(1)} de la propuesta",
                        "ref": f"proposals/{name}", "actor": "agente"})
    return out


def _is_error(event: dict[str, Any]) -> bool:
    return (event.get("kind") in ERROR_KINDS or event.get("kind") == "error"
            or str(event.get("summary", "")).startswith(_ERROR_OUTCOMES))


def _assess(status: str, events: list[dict[str, Any]]) -> tuple[str, list[str], dict[str, int]]:
    counts = {
        "errors": sum(1 for e in events if _is_error(e)),
        "revisions": sum(1 for e in events if e.get("kind") == "revision"),
        "edits": sum(1 for e in events if e.get("kind") == "revision_receipt"),
        "commands": sum(1 for e in events if e.get("kind") == "command"),
        "user_messages": sum(1 for e in events if e.get("kind") == "user_message"),
        "decisions": sum(1 for e in events if e.get("source") in SOURCE_STAGES),
    }
    reasons = []
    if counts["errors"]:
        reasons.append(f"{counts['errors']} error(es) registrados")
    if counts["revisions"] > 1:
        reasons.append(f"{counts['revisions']} revisiones (refactorización)")
    if counts["edits"] > 1:
        reasons.append(f"{counts['edits']} ediciones deliberadas")
    if counts["commands"] > 1:
        reasons.append(f"{counts['commands']} invocaciones del comando de la fase")
    if counts["user_messages"]:
        reasons.append(f"{counts['user_messages']} iteración(es) con el operador")
    if reasons:
        return "orange", reasons, counts
    if status == "PASS":
        return "green", ["Pasó de forma directa"], counts
    return "red", ["Falta por ejecutar" if status != "ACTIVE" else "En curso, sin cerrar"], counts


def _sort_key(event: dict[str, Any]) -> tuple[int, str]:
    return (0, event["ts"]) if event.get("ts") else (1, "")


def build_ai_history(root: Path | str, fases: list[dict[str, Any]],
                     sessions: dict[str, Path | None] | None = None) -> dict[str, Any]:
    """``sessions`` overrides each harness's store (see :func:`ai_transcripts.read_all`)."""
    original = Path(root).expanduser().absolute()
    root = original.resolve()
    by_stage: dict[str, list[dict[str, Any]]] = {}
    sources: dict[str, Any] = {}

    try:
        merged = decisions.build_decisions(root)
        sources["decisions"] = merged.get("sources", {})
        for event in merged.get("events", []):
            stage = SOURCE_STAGES.get(event.get("source"))
            if stage:
                by_stage.setdefault(stage, []).append(
                    {**event, "summary": _clip(event.get("summary")), "actor": "agente"})
    except Exception as exc:  # noqa: BLE001 - one broken source never fails the pane
        sources["decisions"] = {"status": "unreadable", "detail": type(exc).__name__}

    revisions = _revision_events(root)
    by_stage.setdefault("proposal", []).extend(revisions)
    sources["revisions"] = {"status": "ok" if revisions else "absent", "count": len(revisions)}

    chats, sources["chats"] = ai_transcripts.read_all(root, sessions, original)
    for stage, items in chats.items():
        by_stage.setdefault(stage, []).extend(items)

    phases = []
    for fase in fases or []:
        stage = fase.get("stage_id", "")
        status = str(fase.get("status") or "PENDING")
        events = sorted(by_stage.get(stage, []), key=_sort_key)
        colour, reasons, counts = _assess(status, events)
        phases.append({
            "id": fase.get("id"), "stage_id": stage,
            "label": phase_actions.PHASE_LABELS.get(stage, stage),
            "name": fase.get("name"), "gate": fase.get("gate"), "status": status,
            "agent": fase.get("agent"), "color": colour, "reasons": reasons, "counts": counts,
            "total_events": len(events), "events": events[-MAX_PHASE_EVENTS:],
        })
    return {"phases": phases, "sources": sources,
            "note": ("Resumen de solo lectura: decisiones persistidas, revisiones y "
                     "sesiones de chat (Claude Code, Pi, OpenCode) de este espacio de trabajo.")}


__all__ = ["build_ai_history"]
