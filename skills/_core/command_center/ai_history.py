"""The "AI History" pane: what happened in each phase, with whom.

``build_ai_history(root, fases)`` answers, per dashboard phase (the ``fases``
list of ``/api/status``): its gate, a colour and a short timeline of the
interactions that phase had. Read-only and bounded; it never raises. Sources:

* ``decisions``: :func:`decisions.build_decisions` (declarations, the proposal
  and experimental deliberation sidecars, the remote-execution ledgers).
* ``revisions``: managed proposal revisions ``proposals/*-rNN.md``.
* ``chats``: this workspace's sessions of every harness (Claude Code, Pi,
  OpenCode; see :mod:`ai_transcripts`), plus the sessions only the archive still
  holds (:mod:`ai_archive`), such as those of another machine. A phase command
  opens that phase; the operator's follow-up messages, the agent's replies and
  failed tool calls are attributed to it until the next phase command, and what
  comes before the first one is reported as ``unassigned``.

Each phase reports ``metrics``: rounds, prompts, replies, corrections, approvals,
tool errors, sessions, each outcome, and ``first_pass_rate``, the share of rounds
that needed no rework.

Colour: ``red`` when the phase has not passed and shows no friction;
``orange`` when it shows errors, rework (more than one revision) or user
iterations (a follow-up message, a repeated command, a deliberation edit);
``green`` when it passed with none of those.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from . import ai_archive, ai_transcripts, decisions, phase_actions

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


MAX_PHASE_ARTIFACTS = 50


def _workspace_file(root: Path, ref: Any) -> str | None:
    """``ref`` (``path`` or ``path#anchor``) as a workspace-relative POSIX path
    when it names a regular file inside the workspace, else ``None``."""
    if not isinstance(ref, str) or not ref or ":" in ref.split("#", 1)[0]:
        return None
    try:
        target = (root / ref.split("#", 1)[0]).resolve()
        return target.relative_to(root).as_posix() if target.is_file() else None
    except (OSError, RuntimeError, ValueError):
        return None


def phase_artifacts(root: Path, stage: str) -> list[dict[str, Any]]:
    """The files that evidence ``stage`` (``phase_actions.EVIDENCE``), newest
    first; a matched directory contributes its direct, visible files."""
    seen: dict[str, dict[str, Any]] = {}
    for label, pattern in phase_actions.EVIDENCE.get(stage, ()):
        try:
            matches = list(root.glob(pattern))[:phase_actions.MAX_MATCHES]
        except (OSError, ValueError):
            continue
        for match in matches:
            try:
                files = ([match] if match.is_file()
                         else sorted(p for p in match.iterdir() if p.is_file())[:MAX_PHASE_ARTIFACTS])
            except OSError:
                continue
            for path in files:
                if path.name.startswith("."):
                    continue
                rel = _workspace_file(root, path.relative_to(root).as_posix())
                if rel is None or rel in seen:
                    continue
                try:
                    stat = path.stat()
                except OSError:
                    continue
                seen[rel] = {"path": rel, "label": label, "size": stat.st_size,
                             "mtime": int(stat.st_mtime * 1000)}
    ordered = sorted(seen.values(), key=lambda a: (-a["mtime"], a["path"]))
    return ordered[:MAX_PHASE_ARTIFACTS]


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
                        "summary": f"Proposal revision r{found.group(1)}",
                        "ref": f"proposals/{name}", "actor": "agent"})
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
        reasons.append(f"{counts['errors']} error(s) recorded")
    if counts["revisions"] > 1:
        reasons.append(f"{counts['revisions']} revisions (refactoring)")
    if counts["edits"] > 1:
        reasons.append(f"{counts['edits']} deliberated edits")
    if counts["commands"] > 1:
        reasons.append(f"{counts['commands']} invocations of the phase command")
    iterations = sum(1 for e in events if e.get("kind") == "user_message" and not _is_approval(e))
    if iterations:
        reasons.append(f"{iterations} iteration(s) with the operator")
    if reasons:
        return "orange", reasons, counts
    if status == "PASS":
        return "green", ["Passed directly"], counts
    return "red", ["Still to run" if status != "ACTIVE" else "In progress, not closed"], counts


MAX_PHASE_ROUNDS = 40
OUTCOMES = ("success", "rework", "iteration", "pending")
OPERATOR_KINDS = frozenset({"command", "user_message"})
#: persisted decisions that open a round of their own when no operator turn
#: holds them (a deliberation edit, a fact, a remote submission).
DECISION_KINDS = frozenset({"revision_receipt", "lifecycle_transition", "declaration",
                            "fact_resolved", "fact_declined", "submitted"})

_CORRECTION_RE = re.compile(
    r"\b(corrig|correg|arregl|mal\b|error|equivoc|fall|no funciona|rehac|rehaz|reintent|"
    r"otra vez|de nuevo|vuelve a|cambia|revierte|fix|wrong|redo|retry|again|broken|revert)",
    re.I)
_APPROVAL_RE = re.compile(
    r"^\s*(aprob|acept|ok\b|okay|listo|perfecto|de acuerdo|s[i\u00ed]\b|dale\b|bien\b|correcto|"
    r"approve|accept|lgtm|looks good|yes\b)", re.I)
APPROVAL_MAX = 80


def _is_approval(event: dict[str, Any]) -> bool:
    text = str(event.get("summary") or "")
    return (event.get("kind") == "user_message" and len(text) <= APPROVAL_MAX
            and bool(_APPROVAL_RE.search(text)) and not _CORRECTION_RE.search(text))


def decision_rounds(status: str, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Split a phase's sorted ``events`` into operator rounds and classify them.

    A round opens with an operator turn (the phase command or a follow-up
    message) and holds what follows until the next one; a short approval
    ("aprobado", "ok", "lgtm") closes the round before it instead of opening
    one. A persisted decision (:data:`DECISION_KINDS`) opens a ``decision``
    round when no operator round is open, or always when it has no timestamp
    (it cannot be placed inside one); its reply is the last event that joined
    it. Each event gets an ``id``, its ``round`` and ``key`` (an operator turn
    or decision, the reply that answers it, or an error: the phase's main
    interactions).

    Outcome: ``rework`` when the round shows a recorded error or a declined
    fact, or the next round asks to correct or redo it or relaunches the phase
    command (or the same remote submission). A failed tool call alone is no
    rework, since the agent often recovers: it counts in ``tool_errors``.
    ``success`` when the
    operator approved it or it is the last round of a passed phase;
    ``pending`` when it is the last round of a phase that has not passed;
    ``iteration`` otherwise (the operator kept refining)."""
    rounds: list[dict[str, Any]] = []
    for index, event in enumerate(events):
        event["id"] = f"e{index}"
        event["key"] = False
        event["round"] = None
        kind = event.get("kind")
        opens = kind in OPERATOR_KINDS and not (rounds and _is_approval(event))
        decides = kind in DECISION_KINDS and (
            not rounds or rounds[-1]["kind"] == "decision" or not event.get("ts"))
        if opens or decides:
            rounds.append({"n": len(rounds) + 1, "ts": event.get("ts"),
                           "kind": kind if opens else "decision", "opener": kind,
                           "prompt": event.get("summary", ""), "reply": "", "errors": 0, "tool_errors": 0,
                           "approved": False, "events": []})
        elif not rounds or (event.get("source") != "chats" and not event.get("ts")):
            continue
        current = rounds[-1]
        event["round"] = current["n"]
        current["events"].append(event["id"])
        if opens or decides or kind in OPERATOR_KINDS:
            event["key"] = True
            current["approved"] = current["approved"] or _is_approval(event)
        elif kind == "agent_reply" or current["kind"] == "decision":
            current["reply"] = event.get("summary", "")
            current["reply_event"] = event
        if _is_error(event) or kind == "fact_declined":
            event["key"] = True
            current["tool_errors" if event.get("source") == "chats" else "errors"] += 1
    for current in rounds:
        if "reply_event" in current:
            current.pop("reply_event")["key"] = True
    for i, current in enumerate(rounds):
        nxt = rounds[i + 1] if i + 1 < len(rounds) else None
        if current["errors"]:
            outcome, reason = "rework", f"{current['errors']} error(s) or rejection(s) during the iteration"
        elif nxt and nxt["kind"] == "command":
            outcome, reason = "rework", "The phase command was run again"
        elif nxt and current["opener"] == nxt["opener"] == "submitted" and current["prompt"] == nxt["prompt"]:
            outcome, reason = "rework", "The remote run was launched again"
        elif nxt and _CORRECTION_RE.search(nxt["prompt"]):
            outcome, reason = "rework", (f"{current['tool_errors']} tool error(s), then the operator asked to fix it"
                                         if current["tool_errors"] else "The operator asked to fix or redo it")
        elif current["approved"]:
            outcome, reason = "success", "The operator approved it"
        elif nxt:
            outcome, reason = "iteration", ("The decision kept being refined" if current["kind"] == "decision"
                                            else "The operator kept refining")
        elif status == "PASS":
            outcome, reason = "success", "The phase passed its gate"
        else:
            outcome, reason = "pending", "To be decided: the phase has not closed"
        current.update(outcome=outcome, reason=reason)
        del current["approved"], current["opener"]
    return rounds


def _metrics(events: list[dict[str, Any]], rounds: list[dict[str, Any]]) -> dict[str, Any]:
    """What the operator and the agent did in a phase, and how it went."""
    outcomes = {name: sum(1 for r in rounds if r["outcome"] == name) for name in OUTCOMES}
    approvals = sum(1 for e in events if _is_approval(e))
    operator = sum(1 for e in events if e.get("kind") in OPERATOR_KINDS)
    return {
        "rounds": len(rounds), "prompts": operator - approvals, "approvals": approvals,
        "replies": sum(1 for e in events if e.get("kind") == "agent_reply"),
        "corrections": sum(1 for e in events if e.get("kind") == "user_message" and not _is_approval(e)
                           and _CORRECTION_RE.search(str(e.get("summary") or ""))),
        "tool_errors": sum(r["tool_errors"] for r in rounds),
        "sessions": len({e.get("ref") for e in events if e.get("source") == "chats"}),
        **outcomes,
        "first_pass_rate": round((len(rounds) - outcomes["rework"]) / len(rounds), 2) if rounds else None,
    }


def _sort_key(event: dict[str, Any]) -> tuple[int, str]:
    return (0, event["ts"]) if event.get("ts") else (1, "")


def _collect(root: Path | str, sessions: dict[str, Path | None] | None
             ) -> tuple[Path, dict[str, list[dict[str, Any]]], dict[str, Any]]:
    """Every phase's events (decisions, revisions, chats) and each source's
    status: the one read both the pane and the AI-usage record build on."""
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
                    {**event, "summary": _clip(event.get("summary")), "actor": "agent"})
    except Exception as exc:  # noqa: BLE001 - one broken source never fails the pane
        sources["decisions"] = {"status": "unreadable", "detail": type(exc).__name__}

    revisions = _revision_events(root)
    by_stage.setdefault("proposal", []).extend(revisions)
    sources["revisions"] = {"status": "ok" if revisions else "absent", "count": len(revisions)}

    chats, sources["chats"] = ai_transcripts.read_all(root, sessions, original)
    live = {event.get("ref") for items in chats.values() for event in items}
    skills = ai_transcripts.skill_stages()
    kept = 0
    for harness, name, records in ai_archive.archived_sessions(root):
        ref = f"{harness}:{name[-8:]}"
        if ref in live:
            continue
        turns = [ai_transcripts.compact(r.get("ts"), r.get("role", ""), r.get("text", "")) for r in records]
        ai_transcripts.attribute([t for t in turns if t is not None], ref, skills, chats)
        kept += 1
    sources["archive"] = {"status": "ok" if kept else "absent", "sessions": kept}
    for stage, items in chats.items():
        by_stage.setdefault(stage, []).extend(items)
    return root, by_stage, sources


def build_ai_history(root: Path | str, fases: list[dict[str, Any]],
                     sessions: dict[str, Path | None] | None = None) -> dict[str, Any]:
    """``sessions`` overrides each harness's store (see :func:`ai_transcripts.read_all`)."""
    root, by_stage, sources = _collect(root, sessions)
    phases = []
    totals = dict.fromkeys(OUTCOMES, 0)
    pending = []
    for fase in fases or []:
        stage = fase.get("stage_id", "")
        status = str(fase.get("status") or "PENDING")
        events = sorted(by_stage.get(stage, []), key=_sort_key)
        rounds = decision_rounds(status, events)
        summary = dict.fromkeys(OUTCOMES, 0)
        for item in rounds:
            summary[item["outcome"]] += 1
            totals[item["outcome"]] += 1
        if rounds and rounds[-1]["outcome"] == "pending":
            pending.append({"stage_id": stage, "id": fase.get("id"), "round": rounds[-1]["n"],
                            "prompt": rounds[-1]["prompt"]})
        for event in events[-MAX_PHASE_EVENTS:]:
            path = _workspace_file(root, event.get("ref"))
            if path:
                event["path"] = path
        artifacts = phase_artifacts(root, stage)
        colour, reasons, counts = _assess(status, events)
        phases.append({
            "id": fase.get("id"), "stage_id": stage,
            "label": phase_actions.PHASE_LABELS.get(stage, stage),
            "name": fase.get("name"), "gate": fase.get("gate"), "status": status,
            "agent": fase.get("agent"), "color": colour, "reasons": reasons, "counts": counts,
            "total_events": len(events), "events": events[-MAX_PHASE_EVENTS:],
            "artifacts": artifacts, "rounds": rounds[-MAX_PHASE_ROUNDS:],
            "total_rounds": len(rounds), "decision_summary": summary,
            "metrics": _metrics(events, rounds),
        })
    loose = sorted(by_stage.get(ai_transcripts.UNASSIGNED, []), key=_sort_key)
    unassigned = {"prompts": sum(1 for e in loose if e.get("kind") == "user_message"),
                  "replies": sum(1 for e in loose if e.get("kind") == "agent_reply"),
                  "sessions": len({e.get("ref") for e in loose}), "events": loose[-MAX_PHASE_EVENTS:]}
    return {"phases": phases, "sources": sources, "decision_summary": totals, "pending": pending,
            "unassigned": unassigned,
            "note": ("Summary of the persisted decisions, the revisions and the chat sessions of this "
                     "workspace; full conversations live in .papersmith/ai-history/.")}


def _harness_of(ref: Any) -> str | None:
    """``claude-code:1a2b3c4d`` -> ``claude-code``; ``None`` for a non-chat ref."""
    if not isinstance(ref, str) or ":" not in ref:
        return None
    harness = ref.split(":", 1)[0]
    return harness if harness in ai_transcripts.HARNESSES else None


def build_ai_usage(root: Path | str,
                   sessions: dict[str, Path | None] | None = None) -> dict[str, Any]:
    """What the pipeline record shows about AI use, per phase, for a paper's
    AI-use declaration. Read-only; same sources as :func:`build_ai_history`.

    Each phase with any recorded event reports its agent roles
    (``phase_actions.ACTIONS``), the harnesses (tools) whose chat sessions
    worked on it and how many sessions, the operator's commands, follow-up
    messages and approvals, the revisions, the persisted decisions and the
    errors. Phases with nothing recorded are omitted. The harness model or
    version is not part of the record: ``model`` is always ``None`` so a
    declaration never invents one."""
    root, by_stage, sources = _collect(root, sessions)
    phases = []
    harnesses: set[str] = set()
    for stage in phase_actions.STAGES:
        events = by_stage.get(stage, [])
        if not events:
            continue
        refs = {e.get("ref") for e in events if e.get("source") == "chats"}
        tools = sorted({h for h in map(_harness_of, refs) if h})
        harnesses.update(tools)
        counts = {
            "sessions": len({r for r in refs if _harness_of(r)}),
            "commands": sum(1 for e in events if e.get("kind") == "command"),
            "user_messages": sum(1 for e in events if e.get("kind") == "user_message"
                                 and not _is_approval(e)),
            "approvals": sum(1 for e in events if _is_approval(e)),
            "agent_replies": sum(1 for e in events if e.get("kind") == "agent_reply"),
            "revisions": sum(1 for e in events if e.get("kind") == "revision"),
            "decisions": sum(1 for e in events if e.get("source") in SOURCE_STAGES),
            "errors": sum(1 for e in events if _is_error(e)),
        }
        phases.append({
            "stage_id": stage,
            "label": phase_actions.PHASE_LABELS.get(stage, stage),
            "agent": (phase_actions.ACTIONS.get(stage) or {}).get("agent"),
            "harnesses": tools, "model": None, "counts": counts,
        })
    harnesses.update(h for h in (_harness_of(e.get("ref")) for e in by_stage.get(ai_transcripts.UNASSIGNED, [])) if h)
    return {"phases": phases, "harnesses": sorted(harnesses), "sources": sources}


__all__ = ["build_ai_history", "build_ai_usage"]
