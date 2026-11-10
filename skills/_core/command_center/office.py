"""office: the Agents Office's measured state, one snapshot per question.

Spec S1 of `odd/tasks/agents-office-panel.md`: the panel answers "who is
working, on what, and how does the flow touch Engram" from facts the server
already has — the terminal agent catalog, the live sessions the terminal
manager owns, and Engram command lines actually observed in a live session's
output tail. Nothing here spawns a process except the one PATH lookup for the
`engram` binary, nothing is invented (an unmeasured field stays `None`), and
nothing here closes, writes to, or injects anything into a session.

Public API:

    MEMORY_EVENTS_MAX: int = 20
    MEMORY_SCAN_BYTES: int = 8192
    detect_memory_interaction(output_tail) -> str | None
    memory_ring_push(ring, entry) -> list
    observe_memory(ring, session_facts) -> list
    agent_roster(catalog, sessions) -> list
    office_state(*, catalog, session_facts, ring, engram_path,
                 enabled, authorized) -> dict
"""
from __future__ import annotations

import re
import shutil
import time
from typing import Any

#: The memory ring keeps only this many observed Engram interactions.
MEMORY_EVENTS_MAX = 20
#: Only this many bytes at the tail of a live session's output are scanned.
MEMORY_SCAN_BYTES = 8192

#: A line that *is* an Engram interaction: a `mem_*` tool call or an `engram`
#: CLI command, possibly behind a shell prompt. Tool-finding prose ("member
#: list", "memory foam") never matches: the line must start with the call.
_MEMORY_LINE_RE = re.compile(
    r"^\s*(?:[(\[]?[a-z0-9_.-]+@[a-z0-9_.-]+[:~$)\]]*\s*|[$>#]\s*)?"
    r"(mem_[a-z_]+|engram)\b[^\n]{0,120}$",
    re.IGNORECASE | re.MULTILINE,
)


def detect_memory_interaction(output_tail: str) -> str | None:
    """The last Engram interaction line in one session's output tail, or None."""
    if not output_tail:
        return None
    matches = _MEMORY_LINE_RE.findall(output_tail)
    if not matches:
        return None
    last = matches[-1]
    start = output_tail.rfind(last)
    line = output_tail[start:].strip().splitlines()[0].strip()
    return line[:120] or None


def memory_ring_push(ring: list, entry: dict) -> list:
    """Append one observed interaction, keeping the ring bounded and ordered."""
    ring.append(entry)
    overflow = len(ring) - MEMORY_EVENTS_MAX
    if overflow > 0:
        del ring[:overflow]
    return ring


def observe_memory(ring: list, session_facts: list) -> list:
    """Scan each live session's output tail and record new Engram interactions.

    A line already recorded (same agent and line) is not recorded twice, so a
    poll that re-reads the same tail never duplicates history.
    """
    for fact in session_facts:
        if not fact.get("alive"):
            continue
        line = detect_memory_interaction(fact.get("tail") or "")
        if not line:
            continue
        if any(item["agent"] == fact.get("agent") and item["line"] == line
               for item in ring):
            continue
        memory_ring_push(ring, {"agent": fact.get("agent"), "line": line,
                                "at": round(time.time(), 3)})
    return ring


def agent_roster(catalog: list, sessions: dict) -> list:
    """One desk per catalog agent: role from its own description, model
    `None` until something measured it, and its one live-or-dead session."""
    roster = []
    owned: dict = {}
    for sid, fact in (sessions or {}).items():
        owned.setdefault(fact.get("agent"), {"id": sid, "alive": bool(fact.get("alive"))})
    for agent in catalog or []:
        roster.append({
            "id": agent["id"],
            "label": agent.get("label") or agent["id"],
            "role": agent.get("desc") or "",
            "model": None,
            "available": bool(agent.get("available")),
            "session": owned.get(agent["id"]),
        })
    return roster


def engram_path() -> str | None:
    """The host's `engram` binary on PATH, measured, or None when absent."""
    return shutil.which("engram")


def office_state(*, catalog: list, session_facts: list, ring: list,
                 engram_path: str | None, enabled: bool, authorized: bool) -> dict:
    """The measured snapshot the dashboard's Agents Office panel renders."""
    sessions = {f"fact-{index}": {"agent": fact.get("agent"), "alive": fact.get("alive")}
                for index, fact in enumerate(session_facts or [])}
    return {
        "enabled": bool(enabled),
        "authorized": bool(authorized),
        "orchestrator": {"present": bool(enabled and authorized)},
        "agents": agent_roster(catalog, sessions) if enabled and authorized else [],
        "memory": {
            "engram_path": engram_path,
            "interactions": list(ring or [])[-MEMORY_EVENTS_MAX:],
        },
        "generated_at": round(time.time(), 3),
    }
