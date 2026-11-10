"""office: the Agents Office's measured state, one snapshot per question.

The office shows the agents *defined in smith* — every ``.claude/agents/*.md``
of the workspace, read through ``agents_view.get_agents_view`` — plus the
orchestrator, which is the main CLI session (claude, opencode, pi, …) that
runs the skills and calls those agents. Each desk carries one state measured
from facts the server already has, never invented:

``working``
    the agent's invocation line was observed in a live CLI session's output
    tail and no completion marker answered it yet;
``saving`` / ``loading``
    an Engram write (``mem_save``, ``mem_update``, …) or read (``mem_search``,
    ``mem_context``, …) was observed while that agent was running, within the
    last ``MEMORY_ACTIVE_S`` seconds;
``available``
    defined and ready to be called.

The orchestrator is ``absent`` without a live agent session, otherwise
``working`` while any of its agents works, ``saving``/``loading`` when an
Engram call is attributed to it, and ``available`` otherwise. Nothing here
spawns a process except the one PATH lookup for the ``engram`` binary, and
nothing closes, writes to, or injects anything into a session.

Public API:

    MEMORY_EVENTS_MAX: int = 20
    MEMORY_SCAN_BYTES: int = 16384
    MEMORY_ACTIVE_S: float = 8.0
    strip_ansi(text) -> str
    memory_kind(line) -> "save" | "load" | None
    detect_memory_interaction(output_tail) -> str | None
    scan_tail(output_tail, names) -> dict
    memory_ring_push(ring, entry) -> list
    observe(ring, session_facts, names, now=None) -> dict
    agent_roster(defined, activity, ring, now=None) -> list
    office_state(*, defined, session_facts, ring, engram_path,
                 enabled, authorized, now=None) -> dict
"""
from __future__ import annotations

import re
import shutil
import time
from typing import Any

#: The memory ring keeps only this many observed Engram interactions.
MEMORY_EVENTS_MAX = 20
#: Only this many bytes at the tail of a live session's output are scanned.
MEMORY_SCAN_BYTES = 16384
#: An observed Engram call keeps its agent "saving"/"loading" this long.
MEMORY_ACTIVE_S = 8.0
#: The orchestrator id; no smith agent definition may take it.
ORCHESTRATOR = "orchestrator"
#: CLI programs that are not an orchestrator (a plain shell runs no agents).
NON_ORCHESTRATOR_CLIS = frozenset({"shell"})

_ANSI_RE = re.compile(r"\x1b\[[0-9;?<>=]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[@-Z\\-_]")

#: Engram tools that write memory, and those that read it.
_SAVE_VERBS = ("save", "update", "session_summary", "capture_passive", "save_prompt",
               "session_finalize", "consolidate", "pin", "judge", "compare")
_LOAD_VERBS = ("search", "context", "get_observation", "timeline", "review",
               "search_prompts", "current_project", "list_projects")
_MEM_TOOL_RE = re.compile(r"(?<![A-Za-z0-9_])mem_([a-z_]+)")
#: An ``engram`` CLI command line, possibly behind a shell prompt.
_ENGRAM_CLI_RE = re.compile(
    r"^\s*(?:[(\[]?[a-z0-9_.-]+@[a-z0-9_.-]+[:~$)\]]*\s*|[$>#●⏺]\s*)?engram\s+([a-z_-]+)",
    re.IGNORECASE)
_ENGRAM_CLI_SAVE = {"save", "update", "import", "sync"}
_ENGRAM_CLI_LOAD = {"search", "context", "get", "show", "timeline", "export", "stats"}

#: A finished subagent: Claude Code's ``⎿  Done (12 tool uses · …)``, or a
#: line that says the agent completed.
_DONE_RE = re.compile(r"^\s*(?:⎿\s*)?(?:Done|Completed|Finished)\b(?:\s*\(|\s*$)", re.IGNORECASE)


def strip_ansi(text: str) -> str:
    """Terminal output without escape sequences and carriage-return overdraws."""
    plain = _ANSI_RE.sub("", text or "")
    return "\n".join(line.rstrip("\r").rsplit("\r", 1)[-1] for line in plain.split("\n"))


def memory_kind(line: str) -> str | None:
    """``"save"`` for an Engram write, ``"load"`` for a read, else ``None``."""
    match = _MEM_TOOL_RE.search(line or "")
    if match:
        verb = match.group(1)
        if verb in _SAVE_VERBS:
            return "save"
        if verb in _LOAD_VERBS:
            return "load"
        return None
    cli = _ENGRAM_CLI_RE.search(line or "")
    if cli:
        verb = cli.group(1).lower()
        if verb in _ENGRAM_CLI_SAVE:
            return "save"
        if verb in _ENGRAM_CLI_LOAD:
            return "load"
    return None


def detect_memory_interaction(output_tail: str) -> str | None:
    """The last Engram interaction line in one session's output tail, or None."""
    for line in reversed(strip_ansi(output_tail).splitlines()):
        if memory_kind(line):
            return line.strip()[:120] or None
    return None


def _invocation_re(names: list[str]) -> re.Pattern[str] | None:
    """A subagent call as the CLIs print it: ``● sota-scout(…)``,
    ``Task(sota-scout: …)``, ``subagent_type: "sota-scout"`` or ``@sota-scout``."""
    if not names:
        return None
    alt = "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
    return re.compile(
        rf"(?:^\s*[●⏺•*]?\s*(?P<a>{alt})\s*\("
        rf"|(?:Task|Agent)\(\s*(?P<b>{alt})\b"
        rf"|subagent_type\W{{1,4}}(?P<c>{alt})\b"
        rf"|(?<![\w/-])@(?P<d>{alt})(?![\w-]))")


def scan_tail(output_tail: str, names: list[str]) -> dict[str, Any]:
    """What one session's output tail says, in order.

    Answers ``{"running": [names], "memory": [{"agent", "kind", "line"}]}``:
    an invocation opens a running agent, each completion marker closes the
    oldest open one (the CLIs report parallel subagents in launch order), and
    each Engram call is attributed to the most recently opened agent still
    running at that point, or to the orchestrator.
    """
    pattern = _invocation_re(names)
    running: list[str] = []
    memory: list[dict[str, str]] = []
    for raw in strip_ansi(output_tail).splitlines():
        line = raw.strip()
        if not line:
            continue
        match = pattern.search(raw) if pattern else None
        if match:
            name = next(g for g in match.groups() if g)
            if name in running:
                running.remove(name)
            running.append(name)
            continue
        if _DONE_RE.search(raw) and running:
            running.pop(0)
            continue
        kind = memory_kind(line)
        if kind:
            memory.append({"agent": running[-1] if running else ORCHESTRATOR,
                           "kind": kind, "line": line[:120]})
    return {"running": running, "memory": memory}


def memory_ring_push(ring: list, entry: dict) -> list:
    """Append one observed interaction, keeping the ring bounded and ordered."""
    ring.append(entry)
    overflow = len(ring) - MEMORY_EVENTS_MAX
    if overflow > 0:
        del ring[:overflow]
    return ring


def observe(ring: list, session_facts: list, names: list[str],
            now: float | None = None) -> dict[str, Any]:
    """Scan every live session and record new Engram interactions in ``ring``.

    Answers ``{"running": set of agent names, "sessions": live CLI ids}``. A
    line already in the ring (same agent, kind and line) is not recorded
    again, so a poll that re-reads the same tail never duplicates history.
    """
    stamp = time.time() if now is None else now
    running: set[str] = set()
    sessions: list[str] = []
    for fact in session_facts or []:
        if not fact.get("alive"):
            continue
        cli = str(fact.get("agent") or "")
        if cli and cli not in NON_ORCHESTRATOR_CLIS:
            sessions.append(cli)
        seen = scan_tail(fact.get("tail") or "", names)
        running.update(seen["running"])
        for event in seen["memory"]:
            if any(item["agent"] == event["agent"] and item["kind"] == event["kind"]
                   and item["line"] == event["line"] for item in ring):
                continue
            memory_ring_push(ring, {**event, "cli": cli, "at": round(stamp, 3)})
    return {"running": running, "sessions": sessions}


def _memory_state(agent: str, ring: list, stamp: float) -> str | None:
    for item in reversed(ring or []):
        if item.get("agent") == agent and stamp - float(item.get("at") or 0) <= MEMORY_ACTIVE_S:
            return "saving" if item.get("kind") == "save" else "loading"
    return None


def agent_roster(defined: list, activity: dict, ring: list,
                 now: float | None = None) -> list[dict[str, Any]]:
    """One desk per smith agent definition, with its measured state."""
    stamp = time.time() if now is None else now
    running = activity.get("running") or set()
    roster = []
    for agent in defined or []:
        name = agent.get("name")
        if not name or name == ORCHESTRATOR:
            continue
        state = _memory_state(name, ring, stamp) or ("working" if name in running else "available")
        roster.append({
            "id": name,
            "label": name,
            "role": agent.get("role") or "",
            "tramo": agent.get("tramo") or "",
            "phases": list(agent.get("phases") or []),
            "stages": list(agent.get("stages") or []),
            "skill": agent.get("skill") or "",
            "model": agent.get("model") or None,
            "state": state,
        })
    return roster


def orchestrator_state(activity: dict, roster: list, ring: list,
                       now: float | None = None) -> dict[str, Any]:
    """The orchestrator desk: absent without a live agent CLI session."""
    stamp = time.time() if now is None else now
    sessions = list(activity.get("sessions") or [])
    if not sessions:
        state = "absent"
    else:
        state = (_memory_state(ORCHESTRATOR, ring, stamp)
                 or ("working" if any(a["state"] != "available" for a in roster) else "available"))
    return {"id": ORCHESTRATOR, "present": bool(sessions), "clis": sessions, "state": state}


def engram_path() -> str | None:
    """The host's `engram` binary on PATH, measured, or None when absent."""
    return shutil.which("engram")


def office_state(*, defined: list, session_facts: list, ring: list,
                 engram_path: str | None, enabled: bool, authorized: bool,
                 now: float | None = None) -> dict[str, Any]:
    """The measured snapshot the dashboard's Agents Office panel renders.

    The roster of defined agents is the workspace's own files, so it shows
    even when the terminal is off; activity is only read from sessions this
    page is authorized to see.
    """
    stamp = time.time() if now is None else now
    names = [a.get("name") for a in defined or [] if a.get("name")]
    live = bool(enabled and authorized)
    activity = observe(ring, session_facts if live else [], names, stamp)
    roster = agent_roster(defined, activity, ring if live else [], stamp)
    return {
        "enabled": bool(enabled),
        "authorized": bool(authorized),
        "orchestrator": orchestrator_state(activity, roster, ring if live else [], stamp),
        "agents": roster,
        "memory": {
            "engram_path": engram_path,
            "interactions": list(ring or [])[-MEMORY_EVENTS_MAX:] if live else [],
        },
        "generated_at": round(stamp, 3),
    }
