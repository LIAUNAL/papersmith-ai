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
    ``mem_context``, …) was observed in that agent's transcript entry within
    the last ``MEMORY_ACTIVE_S`` seconds. Claude Code folds these calls into
    ``Called engram``; the direction is then measured from the Engram store's
    observation count (it grew: a save; else a read);
``available``
    defined and ready to be called.

The orchestrator is ``absent`` without a live agent session, otherwise
``working`` while any of its agents works, ``saving``/``loading`` when an
Engram call is attributed to it, and ``available`` otherwise. The only
process spawned is ``engram stats --all`` (read-only, its count only), and
only when a folded Engram call needs its direction; nothing closes, writes
to, or injects anything into a session.

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

import codecs
import re
import shutil
import subprocess
import time
from typing import Any, Callable

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
#: Full-screen CLIs (Claude Code) start a line with cursor moves, not "\n":
#: ``\r ESC[1B`` (down), ``ESC[21;1H`` (position). Each becomes a line break,
#: and a column jump (``ESC[19G``, ``ESC[2C``) a space between words.
_LINE_MOVE_RE = re.compile(r"\x1b\[[0-9]*[BEd]|\x1b\[[0-9]*(?:;[0-9]*)?[Hf]")
_COLUMN_MOVE_RE = re.compile(r"\x1b\[[0-9]*[CG]")

#: Engram tools that write memory, and those that read it.
_SAVE_VERBS = ("save", "update", "session_summary", "capture_passive", "save_prompt",
               "session_finalize", "consolidate", "pin", "judge", "compare")
_LOAD_VERBS = ("search", "context", "get_observation", "timeline", "review",
               "search_prompts", "current_project", "list_projects")
#: Only this many characters of one output line are read: a scanner of an
#: untrusted terminal tail must stay linear whatever a program prints.
LINE_SCAN_CHARS = 400
#: An Engram tool call as the CLIs print it: at the start of the line, behind
#: an optional bullet and an optional ``engram -``/``engram_`` server prefix
#: (the Claude Code MCP line ``● engram - mem_<verb> (MCP)``, OpenCode's ``engram_mem_<verb>``, or a bare ``mem_<verb>``).
#: A ``mem_*`` word inside prose or a shell argument is not a call.
_MEM_TOOL_RE = re.compile(r"^[ \t]*(?:[●⏺•*⎿][ \t]*)?(?:engram[ \t]*-[ \t]*|engram_)?mem_([a-z_]+)\b")
#: Claude Code folds MCP calls into ``Calling engram…`` (in progress) and
#: ``Called engram`` (done) without the tool name.
_ENGRAM_FOLDED_RE = re.compile(r"^[ \t]*(?:[●⏺⎿][ \t]*)?Call(ing|ed)[ \t]+engram\b")
#: An ``engram`` CLI command line, possibly behind a shell prompt.
_ENGRAM_CLI_RE = re.compile(
    r"^[ \t]*(?:(?:[(\[]?[a-z0-9_.-]+@[a-z0-9_.-]+[:~$)\]]*|[$>#●⏺])[ \t]*)?engram[ \t]+([a-z_-]+)",
    re.IGNORECASE)
_ENGRAM_CLI_SAVE = {"save", "update", "import", "sync"}
_ENGRAM_CLI_LOAD = {"search", "context", "get", "show", "timeline", "export", "stats"}

#: A finished subagent: Claude Code's ``● Agent "Scout the idea" finished``
#: (background agents) or ``⎿  Done (12 tool uses · …)``.
_DONE_RE = re.compile(
    r"^[ \t]*(?:⎿[ \t]*)?(?:Done|Completed|Finished)\b[ \t]*(?:\(|$)"
    r"|^[ \t]*(?:[●⏺][ \t]*)?Agent[ \t]*\"[^\"\n]{0,200}\"[ \t]*(?:finished|completed|failed)\b",
    re.IGNORECASE)
#: A top-level transcript entry, and the CLI's input prompt.
_BULLET_RE = re.compile(r"^[ \t]*[●⏺]")
_PROMPT_RE = re.compile(r"^[ \t]*[❯>]")


def strip_ansi(text: str) -> str:
    """Terminal output without escape sequences and carriage-return overdraws."""
    moved = _COLUMN_MOVE_RE.sub(" ", _LINE_MOVE_RE.sub("\n", text or ""))
    plain = _ANSI_RE.sub("", moved)
    return "\n".join(line.rstrip(" \t\r").rsplit("\r", 1)[-1] for line in plain.split("\n"))


def memory_kind(line: str) -> str | None:
    """``"save"`` for an Engram write, ``"load"`` for a read, else ``None``."""
    line = (line or "")[:LINE_SCAN_CHARS]
    match = _MEM_TOOL_RE.search(line)
    if match:
        verb = match.group(1)
        if verb in _SAVE_VERBS:
            return "save"
        if verb in _LOAD_VERBS:
            return "load"
        return None
    cli = _ENGRAM_CLI_RE.search(line)
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
    """A subagent call as the CLIs print it: ``● sota-scout(…)`` (the name
    glued to its parenthesis, behind an optional bullet), ``Task(sota-scout: …)``
    or ``subagent_type: "sota-scout"``. Prose that names an agent
    (``* sota-scout (finds papers)``, ``see @sota-scout``) is not a call.
    Every whitespace run is unambiguous, so matching stays linear."""
    if not names:
        return None
    alt = "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
    return re.compile(
        rf"(?:^[ \t]*(?:[●⏺•*][ \t]*)?(?P<a>{alt})\("
        rf"|(?:Task|Agent)\([ \t]*(?P<b>{alt})\b"
        rf"|subagent_type\W{{1,4}}(?P<c>{alt})\b)")


def scan_tail(output_tail: str, names: list[str]) -> dict[str, Any]:
    """What one session's output tail says, in order.

    Answers ``{"running": [names], "memory": [{"agent", "kind", "line"}]}``.
    An invocation opens a running agent; each completion marker closes the
    oldest open one (the CLIs report parallel subagents in launch order).
    Each Engram call belongs to the transcript entry it is printed in: nested
    under an agent's entry (``⎿``, indented) it is that agent's; a top-level
    entry (``●``) is the orchestrator's; text in the input prompt (``❯``) is
    the operator's typing, never a call. A folded ``Called engram`` carries
    kind ``"use"`` until ``observe`` measures whether it saved; an
    in-progress ``Calling engram…`` is kind ``"calling"``.
    """
    pattern = _invocation_re(names)
    running: list[str] = []
    memory: list[dict[str, str]] = []
    owner: str | None = ORCHESTRATOR
    lines = [full[:LINE_SCAN_CHARS] for full in strip_ansi(output_tail).split("\n")]
    for index, raw in enumerate(lines):
        line = raw.strip()
        if not line:
            continue
        if _PROMPT_RE.search(raw):
            owner = None
            continue
        match = pattern.search(raw) if pattern else None
        if match:
            name = next(g for g in match.groups() if g)
            if name in running:
                running.remove(name)
            running.append(name)
            owner = name
            continue
        if _DONE_RE.search(raw):
            if running:
                running.pop(0)
            owner = ORCHESTRATOR
            continue
        kind = memory_kind(line)
        folded = None if kind else _ENGRAM_FOLDED_RE.search(raw)
        if _BULLET_RE.search(raw):
            owner = ORCHESTRATOR
        if not (kind or folded) or owner is None:
            continue
        text = line
        following = next((n.strip() for n in lines[index + 1:index + 3] if n.strip()), "")
        if folded:
            kind = "calling" if folded.group(1) == "ing" else "use"
            if following.startswith("⎿"):
                text = f"{line} {following}"
        memory.append({"agent": owner, "kind": kind, "line": text[:120]})
    return {"running": running, "memory": memory}


def memory_ring_push(ring: list, entry: dict) -> list:
    """Append one observed interaction, keeping the ring bounded and ordered."""
    ring.append(entry)
    overflow = len(ring) - MEMORY_EVENTS_MAX
    if overflow > 0:
        del ring[:overflow]
    return ring


_OBSERVATIONS_RE = re.compile(r"^[ \t]*Observations:[ \t]*([0-9]+)[ \t]*$", re.MULTILINE)


def engram_observations(binary: str | None = None, timeout: float = 3.0) -> int | None:
    """The host Engram store's observation count (``engram stats --all``), or
    None when Engram is absent or does not answer. Only the count is read."""
    path = binary or engram_path()
    if not path:
        return None
    try:
        done = subprocess.run([path, "stats", "--all"], capture_output=True, text=True,
                              timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    match = _OBSERVATIONS_RE.search(done.stdout or "")
    return int(match.group(1)) if match else None


#: The screen model never grows past this, whatever size a client asks for.
SCREEN_MAX_COLS = 400
SCREEN_MAX_ROWS = 200
_SCREEN_TOKEN_RE = re.compile(
    r"\x1b\[([0-9;?<>=]*)[ -/]*([@-~])"        # CSI: params, final byte
    r"|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)?"   # OSC (title, …): ignored
    r"|\x1b([78])"                              # save / restore cursor
    r"|\x1b[()*+][0-9A-Za-z]"                   # charset designation: ignored
    r"|\x1b[@-Z\\-_]?"                          # any other escape: ignored
    r"|([\r\n\b\t])"                            # cursor controls
    r"|[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]+"       # other controls: ignored
    r"|([^\x00-\x1f\x7f]+)")                     # printable text


#: An escape sequence cut off at the end of a chunk.
_UNFINISHED_ESCAPE_RE = re.compile(r"\x1b(?:\[[0-9;?<>=]*[ -/]*|\][^\x07\x1b]*|[()*+])?$")


class Screen:
    """What a terminal shows now, rebuilt from its output: the cursor moves,
    erases and scrolls a full-screen CLI uses (Claude Code repaints only the
    cells that change, so its output read as text repeats old rows and drops
    letters; its screen does neither). Bounded and linear in the input."""

    def __init__(self, cols: int = 100, rows: int = 30) -> None:
        self.cols, self.rows = 0, 0
        self.grid: list[list[str]] = []
        self.r = self.c = 0
        self.saved = (0, 0)
        self._pending = ""
        self._decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self.resize(cols, rows)

    def resize(self, cols: Any, rows: Any) -> None:
        try:
            cols = max(2, min(int(cols), SCREEN_MAX_COLS))
            rows = max(2, min(int(rows), SCREEN_MAX_ROWS))
        except (TypeError, ValueError):
            cols, rows = 100, 30
        if (cols, rows) == (self.cols, self.rows):
            return
        grid = [[" "] * cols for _ in range(rows)]
        for index, row in enumerate(self.grid[-rows:]):
            grid[index][:min(cols, len(row))] = row[:cols]
        self.grid, self.cols, self.rows = grid, cols, rows
        self.r, self.c = min(self.r, rows - 1), min(self.c, cols - 1)
        self.saved = (min(self.saved[0], rows - 1), min(self.saved[1], cols - 1))

    def _linefeed(self) -> None:
        if self.r >= self.rows - 1:
            self.grid.pop(0)
            self.grid.append([" "] * self.cols)
        else:
            self.r += 1

    def _clear(self, row: int, start: int, stop: int) -> None:
        self.grid[row][start:stop] = [" "] * max(0, stop - start)

    def feed(self, text: str) -> None:
        for match in _SCREEN_TOKEN_RE.finditer(text or ""):
            printable, control, final = match.group(5), match.group(4), match.group(2)
            if printable:
                for char in printable:
                    if self.c >= self.cols:
                        self.c = 0
                        self._linefeed()
                    self.grid[self.r][self.c] = char
                    self.c += 1
            elif control:
                if control == "\r":
                    self.c = 0
                elif control == "\n":
                    self._linefeed()
                elif control == "\b":
                    self.c = max(0, self.c - 1)
                else:
                    self.c = min(self.cols - 1, (self.c // 8 + 1) * 8)
            elif match.group(3):
                if match.group(3) == "7":
                    self.saved = (self.r, self.c)
                else:
                    self.r, self.c = min(self.saved[0], self.rows - 1), min(self.saved[1], self.cols - 1)
            elif final:
                self._csi(match.group(1) or "", final)

    def _csi(self, params: str, final: str) -> None:
        private = params.startswith("?")
        # The last six digits bound every count: no conversion of a huge
        # number, no move or erase past what a screen can hold.
        values = [int(v[-6:]) if v.isdigit() else 0 for v in params.lstrip("?<>=").split(";")[:16]] if params else []
        n = max(1, values[0]) if values and values[0] else 1
        top, left = self.rows - 1, self.cols - 1
        if private:
            if final in "hl" and values and values[0] in (47, 1047, 1049):
                self.grid = [[" "] * self.cols for _ in range(self.rows)]
            return
        if final == "A":
            self.r = max(0, self.r - n)
        elif final in "Be":
            self.r = min(top, self.r + n)
        elif final in "Ca":
            self.c = min(left, self.c + n)
        elif final == "D":
            self.c = max(0, self.c - n)
        elif final == "E":
            self.r, self.c = min(top, self.r + n), 0
        elif final == "F":
            self.r, self.c = max(0, self.r - n), 0
        elif final in "G`":
            self.c = min(left, n - 1)
        elif final == "d":
            self.r = min(top, n - 1)
        elif final in "Hf":
            row = values[0] if values else 1
            col = values[1] if len(values) > 1 else 1
            self.r, self.c = min(top, max(1, row) - 1), min(left, max(1, col) - 1)
        elif final == "K":
            mode = values[0] if values else 0
            start, stop = {0: (self.c, self.cols), 1: (0, self.c + 1)}.get(mode, (0, self.cols))
            self._clear(self.r, start, stop)
        elif final == "J":
            mode = values[0] if values else 0
            if mode == 0:
                self._clear(self.r, self.c, self.cols)
                rows = range(self.r + 1, self.rows)
            elif mode == 1:
                self._clear(self.r, 0, self.c + 1)
                rows = range(0, self.r)
            else:
                rows = range(self.rows)
            for row in rows:
                self._clear(row, 0, self.cols)
        elif final == "X":
            self._clear(self.r, self.c, min(self.cols, self.c + n))
        elif final == "P":
            row = self.grid[self.r]
            del row[self.c:self.c + n]
            row.extend([" "] * (self.cols - len(row)))
        elif final == "@":
            row = self.grid[self.r]
            row[self.c:self.c] = [" "] * min(n, self.cols - self.c)
            del row[self.cols:]
        elif final == "S":
            for _ in range(min(n, self.rows)):
                self.grid.pop(0)
                self.grid.append([" "] * self.cols)
        elif final == "T":
            for _ in range(min(n, self.rows)):
                self.grid.pop()
                self.grid.insert(0, [" "] * self.cols)
        elif final == "s":
            self.saved = (self.r, self.c)
        elif final == "u":
            self.r, self.c = min(self.saved[0], self.rows - 1), min(self.saved[1], self.cols - 1)

    def feed_bytes(self, chunk: bytes) -> None:
        """Feed raw output that may end inside a UTF-8 character or an escape
        sequence: the unfinished part waits for the next chunk."""
        text = self._decoder.decode(chunk or b"")
        text = self._pending + text
        cut = _UNFINISHED_ESCAPE_RE.search(text)
        self._pending = text[cut.start():][:64] if cut else ""
        self.feed(text[:cut.start()] if cut else text)

    def lines(self) -> list[str]:
        return ["".join(row).rstrip() for row in self.grid]


#: After Engram fails to give a count, it is not asked again for this long.
COUNTER_BACKOFF_S = 60.0


def _backed_off(counter: Callable[[], int | None] | None, memo: dict,
                stamp: float) -> Callable[[], int | None] | None:
    """``counter`` wrapped so a failed answer (None) silences it for
    ``COUNTER_BACKOFF_S``: a hung or changed ``engram`` costs one timeout a
    minute, not one per poll."""
    if counter is None or stamp - memo.get("counter_failed_at", -COUNTER_BACKOFF_S - 1) < COUNTER_BACKOFF_S:
        return None

    def measured() -> int | None:
        value = counter()
        if value is None:
            memo["counter_failed_at"] = stamp
        return value
    return measured


def observe(ring: list, session_facts: list, names: list[str],
            now: float | None = None, memo: dict | None = None,
            counter: Callable[[], int | None] | None = None) -> dict[str, Any]:
    """Scan every live session and record new Engram interactions in ``ring``.

    Answers ``{"running": set of agent names, "sessions": live CLI ids}``.
    Who runs comes from the output history (invocations and completions).

    A session that reports its ``id`` and absolute output ``end`` keeps a
    ``Screen`` in ``memo`` (kept by the caller across polls), fed only the
    output written since the last poll. A call is a row that appears on that
    screen: a repaint shows the same rows and adds none, two identical calls
    are two rows. The first poll of a session only records its screen: what it
    showed before the office looked is history. A session without ``id`` and
    ``end`` is scanned whole, and a call already in the ring is not recorded
    twice.

    ``counter`` measures the Engram store's observation count: a folded
    ``Called engram`` is a save when the count grew since the last measure
    (taken when its ``Calling engram…`` showed, or at the last call), else a
    read; without a count it stays ``"use"`` (direction unknown).
    """
    from collections import Counter

    stamp = time.time() if now is None else now
    memo = {} if memo is None else memo
    counter = _backed_off(counter, memo, stamp)
    screens: dict = memo.setdefault("screens", {})
    shown_before: dict = memo.setdefault("shown", {})
    spinning: dict = memo.setdefault("spinning", {})
    ends: dict = memo.setdefault("ends", {})
    running: set[str] = set()
    sessions: list[str] = []
    fresh: list[dict] = []
    for fact in session_facts or []:
        if not fact.get("alive"):
            continue
        cli = str(fact.get("agent") or "")
        if cli and cli not in NON_ORCHESTRATOR_CLIS:
            sessions.append(cli)
        tail = fact.get("tail") or ""
        running.update(scan_tail(tail, names)["running"])
        sid, end = fact.get("id"), fact.get("end")
        if sid is None or not isinstance(end, int):
            for event in scan_tail(tail, names)["memory"]:
                if event["kind"] == "calling" or any(
                        item["agent"] == event["agent"] and item["line"] == event["line"] for item in ring):
                    continue
                event.pop("key", None)
                fresh.append({**event, "cli": cli})
            continue
        screen = screens.get(sid)
        raw = fact.get("raw") if isinstance(fact.get("raw"), bytes) else tail.encode("utf-8")
        if screen is None:
            screen = screens[sid] = Screen(fact.get("cols", 100), fact.get("rows", 30))
            chunk = raw
        else:
            screen.resize(fact.get("cols", 100), fact.get("rows", 30))
            written = max(0, end - ends.get(sid, end))
            chunk = raw[-written:] if written else b""
        try:
            screen.feed_bytes(chunk)
        except Exception:  # noqa: BLE001 - untrusted output must never break the office
            screen = screens[sid] = Screen(fact.get("cols", 100), fact.get("rows", 30))
        primed = sid in ends
        ends[sid] = end
        shown = scan_tail("\n".join(screen.lines()), names)["memory"]
        calls = Counter((e["agent"], e["kind"], e["line"]) for e in shown if e["kind"] != "calling")
        is_spinning = any(e["kind"] == "calling" for e in shown)
        if is_spinning and not spinning.get(sid) and counter is not None:
            memo["observations"] = counter()
        spinning[sid] = is_spinning
        if primed:
            for agent, kind, line in (calls - shown_before.get(sid, Counter())).elements():
                fresh.append({"agent": agent, "kind": kind, "line": line, "cli": cli})
        shown_before[sid] = calls
    for sid in [s for s in screens if s not in {f.get("id") for f in session_facts or []}]:
        for store in (screens, shown_before, spinning, ends):
            store.pop(sid, None)
    if any(e["kind"] == "use" for e in fresh) and counter is not None:
        count = counter()
        before_count = memo.get("observations")
        if count is not None and before_count is not None:
            for event in fresh:
                if event["kind"] == "use":
                    event["kind"] = "save" if count > before_count else "load"
        if count is not None:
            memo["observations"] = count
    elif sessions and counter is not None and memo.get("observations") is None:
        memo["observations"] = counter()
    for event in fresh:
        memory_ring_push(ring, {**event, "at": round(stamp, 3)})
    return {"running": running, "sessions": sessions}


def _memory_state(agent: str, ring: list, stamp: float) -> str | None:
    for item in reversed(ring or []):
        if item.get("agent") == agent and stamp - float(item.get("at") or 0) <= MEMORY_ACTIVE_S:
            if item.get("kind") in ("save", "load"):
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
                 now: float | None = None, memo: dict | None = None,
                 counter: Callable[[], int | None] | None = None) -> dict[str, Any]:
    """The measured snapshot the dashboard's Agents Office panel renders.

    The roster of defined agents is the workspace's own files, so it shows
    even when the terminal is off; activity is only read from sessions this
    page is authorized to see.
    """
    stamp = time.time() if now is None else now
    names = [a.get("name") for a in defined or [] if a.get("name")]
    live = bool(enabled and authorized)
    activity = observe(ring, session_facts if live else [], names, stamp, memo, counter)
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
