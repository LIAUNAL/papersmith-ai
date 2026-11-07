"""Chat turns of every harness, attributed to dashboard phases.

Each reader turns one harness's local session store into ``(ts, role, text)``
turns (``role`` is ``user``, ``assistant`` or ``error``); :func:`attribute`
assigns them to phases the same way for every harness: a phase command opens
its phase and the turns that follow belong to it until the next one; what comes
before the first one is ``unassigned``. These turns are clipped for the graph:
:mod:`ai_archive` keeps them in full.

Stores (read-only, bounded; a missing store is ``absent``, never an error):

* ``claude-code``: ``$CLAUDE_CONFIG_DIR`` or ``~/.claude``, then
  ``projects/<path with every non-alphanumeric character as '-'>/*.jsonl``.
* ``pi``: ``$PI_CODING_AGENT_DIR`` or ``~/.pi/agent``, then
  ``sessions/--<path with '/', '\\' and ':' as '-'>--/*.jsonl``.
* ``opencode``: ``$XDG_DATA_HOME`` or ``~/.local/share``, then
  ``opencode/opencode.db`` (SQLite, opened read-only), sessions whose
  ``directory`` is the workspace.
* ``antigravity``: ``~/.gemini/antigravity-cli/conversation_summaries.db`` and
  ``brain/<id>/.system_generated/logs/transcript.jsonl``.

When the slug directory is missing (a renamed or long path), the Claude Code
and Pi readers fall back to the session whose recorded ``cwd`` is the
workspace. Inside WSL every store is the Linux one; an agent running on the
Windows side keeps its sessions under ``/mnt/c/Users/...``, which the
``PAPERSMITH_<HARNESS>_SESSIONS`` variables point the reader to.

Reads are incremental: each session file keeps, per server process, the
byte offset it was read up to and its compacted turns, so a request parses
only the lines appended since the last one (a session that shrank or was
replaced is read again from the start). Lines that cannot hold a turn are
skipped before JSON parsing. OpenCode sessions are reused until their
``time_updated`` moves.

Each reply carries the model that wrote it, as far as its harness records it:
Claude Code's ``message.model`` and ``effort``, Pi's ``model`` and its last
``thinking_level_change``, OpenCode's ``modelID`` and ``variant``. Antigravity does
not write it in a transcript, so it is inferred from the selection its
``cli-*.log`` logged last (``inferred``). What is not recorded stays absent.

A command is recognised in the four shapes harnesses write it: Claude Code's
``<command-name>/x</command-name>``, Pi's ``<skill name="x">`` block, the
expanded projected prompt ``Read `skills/x/SKILL.md` and follow it`` (Pi
prompts, OpenCode commands) and a literal ``/x args``.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import time
from bisect import bisect_right
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator

from . import phase_actions

MAX_SESSIONS = 40
SESSION_MAX_BYTES = 64 * 1024 * 1024
MAX_LINE_BYTES = 1024 * 1024
MAX_SCAN_DIRS = 500
MAX_DB_ROWS = 20000
TEXT_MAX = 240

HARNESSES = ("claude-code", "pi", "opencode", "antigravity")

#: user turns the harness writes on the operator's behalf (reminders, the
#: notice of a finished background task, a command's echoed output): never
#: an operator turn.
HARNESS_PREFIXES = ("<system-reminder>", "<task-notification>", "<local-command-caveat>",
                    "<persisted-output>", "<bash-notification>", "<bash-input>", "<bash-stdout>",
                    "<bash-stderr>", "[Request interrupted")
#: The phase of the turns a session has before its first phase command.
UNASSIGNED = "unassigned"

#: ``role`` is ``user``, ``assistant``, ``error`` or ``phase`` (the agent loaded
#: a skill, named by the text).
Turn = tuple["str | None", str, str]
#: ``(ts, role, text, command)``: what :func:`attribute` needs of a turn, with
#: the text already clipped and the command (``(skill, args)``) already parsed.
Compact = tuple["str | None", str, str, "tuple[str, str] | None"]

_cache_lock = threading.Lock()
_file_cache: dict[str, dict[str, Any]] = {}
_opencode_cache: dict[tuple[str, str], tuple[Any, list[Compact]]] = {}

_COMMAND_RE = re.compile(r"<command-name>\s*/?([\w:.-]+)\s*</command-name>")
_ARGS_RE = re.compile(r"<command-args>(.*?)</command-args>", re.S)
_PI_SKILL_RE = re.compile(r"^<skill\s+name=\"([\w:.-]+)\"[^>]*>.*?</skill>(.*)$", re.S)
_EXPANDED_RE = re.compile(
    r"^Read `skills/([\w.-]+)/SKILL\.md` and follow it.*?`\$ARGUMENTS`:\s*(.*)$", re.S)
_SLASH_RE = re.compile(r"^/([\w:.-]+)(?:\s+(.*))?$", re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_CLAUDE_MODEL_RE = re.compile(r"^claude-([a-z]+)-(\d{1,2})-(\d{1,2})(?!\d)")
_LOG_LABEL_RE = re.compile(r"^I(\d{2})(\d{2}) (\d{2}:\d{2}:\d{2}).*Propagating selected model.*label[=:]?\s*\"?([^\",}\n]+)")
_LOG_NAME_RE = re.compile(r"^cli-(\d{4})\d{4}_")
_LABEL_EFFORT_RE = re.compile(r"^(.*?)\s*\(([^()]+)\)\s*$")
HARNESS_NAMES = {"claude-code": "Claude Code", "pi": "Pi", "opencode": "OpenCode", "antigravity": "Antigravity"}
_INJECTED_RE = re.compile(r"^\s*(?:<system-reminder>.*?</system-reminder>\s*)+", re.S)


def _clip(text: Any, limit: int = TEXT_MAX) -> str:
    value = " ".join(str(text or "").split())
    return value if len(value) <= limit else value[: limit - 1] + "…"


def model_label(harness: str, meta: dict[str, Any] | None) -> str:
    """How a reply's agent reads: ``Claude Code · opus 5.5 - medium``."""
    meta = meta or {}
    model = str(meta.get("model") or "")
    short = _CLAUDE_MODEL_RE.match(model)
    if short:
        model = f"{short.group(1)} {short.group(2)}.{short.group(3)}"
    detail = " - ".join(str(part) for part in (model, meta.get("effort")) if part)
    name = HARNESS_NAMES.get(harness, harness)
    return f"{name} · {detail}" if detail else name


def skill_stages() -> dict[str, str]:
    """Skill name -> the first phase whose actions list it."""
    out: dict[str, str] = {}
    for stage in phase_actions.STAGES:
        for skill in (phase_actions.ACTIONS.get(stage) or {}).get("skills", ()):
            out.setdefault(skill, stage)
    return out


def command_of(text: str) -> tuple[str, str] | None:
    """The ``(skill, args)`` a user turn invokes, in any harness's shape."""
    found = _COMMAND_RE.search(text)
    if found:
        args = _ARGS_RE.search(text)
        return found.group(1).split(":")[-1], args.group(1) if args else ""
    stripped = text.strip()
    for pattern in (_PI_SKILL_RE, _EXPANDED_RE, _SLASH_RE):
        found = pattern.match(stripped)
        if found:
            return found.group(1).split(":")[-1], (found.group(2) or "").strip()
    return None


def stage_for(name: str, args: str, skills: dict[str, str]) -> str | None:
    if name == "paper-writing":
        head = args.strip().split(" ", 1)[0].lower()
        return "declarations" if head == "mark" else "writing"
    return skills.get(name)


def _event(ts: Any, kind: str, summary: str, ref: str, actor: str) -> dict[str, Any]:
    return {"ts": ts if isinstance(ts, str) else None, "source": "chats", "kind": kind,
            "summary": summary, "ref": ref, "actor": actor}


def operator_text(text: str) -> str | None:
    """What the operator wrote in a user turn, ``None`` when the harness wrote
    it: a reminder in front of a real prompt goes, the prompt stays."""
    cleaned = _INJECTED_RE.sub("", text)
    if (not cleaned.strip() or "<local-command-stdout>" in cleaned
            or cleaned.lstrip().startswith(HARNESS_PREFIXES)):
        return None
    return cleaned


def compact(ts: Any, role: str, text: str) -> Compact | None:
    """One turn reduced to what attribution reads; ``None`` when it carries
    nothing (an empty or harness-injected user turn, an empty reply)."""
    if role == "assistant":
        return (ts, role, _clip(text), None) if text.strip() else None
    if role == "error":
        return (ts, role, "", None)
    if role == "phase":
        return (ts, role, text, None)
    kept = operator_text(text)
    if kept is None:
        return None
    text = kept
    command = command_of(text)
    if command is not None:
        return (ts, "user", "", (command[0], command[1][: TEXT_MAX * 2]))
    return (ts, "user", _clip(_TAG_RE.sub(" ", text)), None)


def attribute(turns: Iterable[Compact], ref: str, skills: dict[str, str],
              events: dict[str, list[dict[str, Any]]]) -> None:
    """Assign one session's compacted turns to phases. Only the agent's last
    reply before the next user turn is kept."""
    stage: str = UNASSIGNED
    reply: dict[str, Any] | None = None

    def flush() -> None:
        nonlocal reply
        if reply is not None:
            events.setdefault(stage, []).append(reply)
        reply = None

    for ts, role, text, command, *rest in turns:
        if role == "assistant":
            reply = _event(ts, "agent_reply", text, ref, "agent")
            if rest and rest[0]:
                reply["model_label"] = model_label(ref.split(":", 1)[0], rest[0])
            continue
        if role == "error":
            events.setdefault(stage, []).append(
                _event(ts, "error", "A tool failed during the phase", ref, "tool"))
            continue
        if role == "phase":
            # The agent loaded a phase's skill: no command was typed, but the
            # work that follows belongs to that phase.
            if text in skills:
                flush()
                stage = skills[text]
            continue
        target = stage_for(*command, skills) if command else None
        flush()
        if target is not None:
            stage = target
            events.setdefault(stage, []).append(
                _event(ts, "command", _clip(f"/{command[0]} {command[1]}".strip()), ref, "operator"))
        elif command is None:
            events.setdefault(stage, []).append(_event(ts, "user_message", text, ref, "operator"))
    flush()


# --- locating the stores ---------------------------------------------------

def _env_dir(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    return Path(value).expanduser() if value else default


def _same_dir(recorded: Any, roots: set[str]) -> bool:
    return isinstance(recorded, str) and recorded.rstrip("/\\") in roots


def _first_cwd(path: Path, limit: int = 40) -> Any:
    try:
        with path.open("rb") as handle:
            for index, raw in enumerate(handle):
                if index >= limit:
                    break
                if len(raw) > MAX_LINE_BYTES:
                    continue
                try:
                    line = json.loads(raw)
                except ValueError:
                    continue
                if isinstance(line, dict) and isinstance(line.get("cwd"), str):
                    return line["cwd"]
    except OSError:
        return None
    return None


def _newest(directory: Path) -> list[Path]:
    try:
        files = [p for p in directory.glob("*.jsonl") if p.is_file()]
        return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return []


def _locate(base: Path, slugs: Iterable[str], roots: set[str]) -> Path | None:
    """The session directory under ``base``: a slug match, else the directory
    whose newest session records the workspace as its ``cwd``."""
    for slug in slugs:
        if (base / slug).is_dir():
            return base / slug
    try:
        candidates = [d for d in base.iterdir() if d.is_dir()][:MAX_SCAN_DIRS]
    except OSError:
        return None
    for directory in candidates:
        files = _newest(directory)
        if files and _same_dir(_first_cwd(files[0]), roots):
            return directory
    return None


def claude_projects() -> Path:
    return _env_dir("CLAUDE_CONFIG_DIR", Path.home() / ".claude") / "projects"


def pi_sessions_base() -> Path:
    return _env_dir("PI_CODING_AGENT_DIR", Path.home() / ".pi" / "agent") / "sessions"


def related_dirs(base: Path, roots: set[str]) -> list[Path]:
    """The session folders under ``base`` whose newest session ran in a
    subdirectory of the workspace or in one of its sibling worktrees."""
    prefixes = tuple(p for r in roots for p in (r + "/", r + "-worktrees/"))
    try:
        candidates = sorted(d for d in base.iterdir() if d.is_dir())[:MAX_SCAN_DIRS]
    except OSError:
        return []
    found = []
    for directory in candidates:
        files = _newest(directory)
        cwd = _first_cwd(files[0]) if files else None
        if isinstance(cwd, str) and cwd.startswith(prefixes):
            found.append(directory)
    return found


def claude_dir(roots: set[str]) -> Path | None:
    override = os.environ.get("PAPERSMITH_CLAUDE_CODE_SESSIONS")
    if override:
        return Path(override).expanduser()
    base = claude_projects()
    return _locate(base, [re.sub(r"[^A-Za-z0-9]", "-", r) for r in sorted(roots)], roots)


def pi_dir(roots: set[str]) -> Path | None:
    override = os.environ.get("PAPERSMITH_PI_SESSIONS")
    if override:
        return Path(override).expanduser()
    base = pi_sessions_base()
    slugs = ["--" + re.sub(r"[/\\:]", "-", r.lstrip("/\\")) + "--" for r in sorted(roots)]
    return _locate(base, slugs, roots)


def opencode_db() -> Path:
    override = os.environ.get("PAPERSMITH_OPENCODE_SESSIONS")
    if override:
        return Path(override).expanduser()
    return _env_dir("XDG_DATA_HOME", Path.home() / ".local" / "share") / "opencode" / "opencode.db"


def antigravity_db() -> Path:
    override = os.environ.get("PAPERSMITH_ANTIGRAVITY_SESSIONS")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".gemini" / "antigravity-cli" / "conversation_summaries.db"


# --- per-harness turn readers ----------------------------------------------

def session_turns(path: Path, line_turn: Callable[[dict[str, Any]], Turn | None],
                  markers: tuple[bytes, ...],
                  line_model: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any] | None] | None = None
                  ) -> list[Compact]:
    """The compacted turns of one JSONL session, parsing only what was
    appended since the last call. A partial last line (still being written)
    waits for the next call."""
    stat = path.stat()
    key, ident = str(path), (stat.st_dev, stat.st_ino)
    with _cache_lock:
        entry = _file_cache.get(key)
    if (entry is None or entry["ident"] != ident or stat.st_size < entry["offset"]
            or (stat.st_size == entry["offset"] and stat.st_mtime_ns != entry["mtime"])):
        entry = {"ident": ident, "offset": 0, "mtime": 0, "turns": [], "model": {}}
    if stat.st_size == entry["offset"]:
        return entry["turns"]
    with path.open("rb") as handle:
        handle.seek(entry["offset"])
        data = handle.read(stat.st_size - entry["offset"])
    end = data.rfind(b"\n") + 1
    tail = data[end:]
    lines = data[:end].split(b"\n")
    # A last line without its newline is complete only when it already parses:
    # a JSON object cut short never does.
    if tail.strip():
        try:
            json.loads(tail)
        except ValueError:
            pass
        else:
            lines.append(tail)
            end = len(data)
    turns = list(entry["turns"])
    state = dict(entry.get("model") or {})
    for raw in lines:
        if not raw or len(raw) > MAX_LINE_BYTES or not any(m in raw for m in markers):
            continue
        try:
            line = json.loads(raw)
        except ValueError:
            continue
        turn = line_turn(line) if isinstance(line, dict) else None
        meta = line_model(line, state) if line_model and isinstance(line, dict) else None
        small = compact(*turn) if turn else None
        if small is not None and not (small[1] == "user" and turns and turns[-1][1:4] == small[1:4]):
            turns.append((*small, meta) if meta and small[1] == "assistant" else small)
    with _cache_lock:
        _file_cache[key] = {"ident": ident, "offset": entry["offset"] + end,
                            "mtime": stat.st_mtime_ns, "turns": turns, "model": state}
    return turns


def _blocks(content: Any, text_type: str = "text") -> tuple[str, list[dict[str, Any]]]:
    if isinstance(content, str):
        return content, []
    blocks = [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []
    return "\n".join(str(b.get("text") or "") for b in blocks if b.get("type") == text_type), blocks


def claude_line(line: dict[str, Any]) -> Turn | None:
    if (line.get("isSidechain") or line.get("isMeta") or line.get("isCompactSummary")
            or line.get("isApiErrorMessage")):
        return None
    kind, message = line.get("type"), line.get("message")
    attachment = line.get("attachment")
    if kind == "attachment" and isinstance(attachment, dict):
        # A prompt typed while the agent works waits here until it is delivered.
        prompt = attachment.get("prompt")
        if attachment.get("type") == "queued_command" and isinstance(prompt, str) and prompt.strip():
            return attachment.get("timestamp") or line.get("timestamp"), "user", prompt
        return None
    if kind not in ("user", "assistant") or not isinstance(message, dict):
        return None
    text, blocks = _blocks(message.get("content"))
    if any(b.get("type") == "tool_result" and b.get("is_error") for b in blocks):
        return line.get("timestamp"), "error", ""
    if not text:
        for block in blocks:
            skill = (block.get("input") or {}).get("skill") if block.get("name") == "Skill" else None
            if block.get("type") == "tool_use" and isinstance(skill, str):
                return line.get("timestamp"), "phase", skill.split(":")[-1]
    return (line.get("timestamp"), kind, text) if text else None


def pi_line(line: dict[str, Any]) -> Turn | None:
    message = line.get("message")
    if line.get("type") != "message" or not isinstance(message, dict):
        return None
    role, ts = message.get("role"), line.get("timestamp")
    if role == "toolResult":
        return (ts, "error", "") if message.get("isError") else None
    if role in ("user", "assistant"):
        text, _ = _blocks(message.get("content"))
        return (ts, role, text) if text else None
    return None


def claude_model(line: dict[str, Any], _state: dict[str, Any]) -> dict[str, Any] | None:
    message = line.get("message")
    model = message.get("model") if isinstance(message, dict) and line.get("type") == "assistant" else None
    if not isinstance(model, str) or model.startswith("<"):
        return None
    effort = line.get("effort")
    return {"model": model, **({"effort": effort} if isinstance(effort, str) and effort else {})}


def pi_model(line: dict[str, Any], state: dict[str, Any]) -> dict[str, Any] | None:
    """A Pi reply's model; its thinking level is the last one the session set."""
    if line.get("type") == "thinking_level_change" and isinstance(line.get("thinkingLevel"), str):
        state["effort"] = line["thinkingLevel"]
    message = line.get("message")
    if line.get("type") != "message" or not isinstance(message, dict) or message.get("role") != "assistant":
        return None
    meta = {key: message[key] for key in ("model", "provider") if isinstance(message.get(key), str)}
    if meta and state.get("effort"):
        meta["effort"] = state["effort"]
    return meta or None


LINE_MODELS: dict[str, Callable[[dict[str, Any], dict[str, Any]], dict[str, Any] | None]] = {
    "claude-code": claude_model, "pi": pi_model}


#: Per harness: how one JSONL line becomes a turn, and the bytes a line must
#: contain to be worth parsing at all.
LINE_READERS: dict[str, tuple[Callable[[dict[str, Any]], Turn | None], tuple[bytes, ...]]] = {
    "claude-code": (claude_line, (b'"user"', b'"assistant"', b'"queued_command"')),
    "pi": (pi_line, (b'"message"', b'"thinking_level_change"')),
}


def _iso(ms: Any) -> str | None:
    if not isinstance(ms, (int, float)) or isinstance(ms, bool):
        return None
    try:
        stamp = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None
    return stamp.strftime("%Y-%m-%dT%H:%M:%S.") + f"{stamp.microsecond // 1000:03d}Z"


def _compacted(turns: Iterable[tuple[Any, ...]]) -> list[Compact]:
    """Turns with an optional fourth item, the reply's model, compacted."""
    found = []
    for turn in turns:
        small = compact(*turn[:3])
        if small is not None:
            found.append((*small, turn[3]) if len(turn) > 3 and turn[3] else small)
    return found


def opencode_sessions(db: Path, roots: set[str]) -> tuple[list[tuple[str, list[Compact]]], str]:
    """``[(session id, turns)]`` of the workspace's OpenCode sessions."""
    if not db.is_file():
        return [], "absent"
    uri = "file:" + db.resolve().as_posix() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=2)
    try:
        marks = ",".join("?" for _ in roots)
        sessions = connection.execute(
            f"SELECT id, time_updated FROM session WHERE directory IN ({marks}) AND parent_id IS NULL "
            "ORDER BY time_updated DESC LIMIT ?", (*sorted(roots), MAX_SESSIONS)).fetchall()
        out = []
        for session_id, updated in sessions:
            key = (str(db), session_id)
            with _cache_lock:
                cached = _opencode_cache.get(key)
            if cached is not None and cached[0] == updated:
                out.append((session_id, cached[1]))
                continue
            rows = connection.execute(
                "SELECT m.data, p.data, p.time_created FROM part p JOIN message m ON m.id = p.message_id "
                "WHERE p.session_id = ? ORDER BY p.time_created DESC, p.id DESC LIMIT ?",
                (session_id, MAX_DB_ROWS)).fetchall()
            rows.reverse()
            turns = _compacted(_opencode_turns(rows))
            with _cache_lock:
                _opencode_cache[key] = (updated, turns)
            out.append((session_id, turns))
        return out, "ok" if sessions else "absent"
    finally:
        connection.close()


def opencode_raw(db: Path, roots: set[str]) -> Iterator[tuple[str, list[Turn]]]:
    """Every OpenCode session of the workspace with its uncut turns."""
    connection = sqlite3.connect("file:" + db.resolve().as_posix() + "?mode=ro", uri=True, timeout=2)
    try:
        marks = ",".join("?" for _ in roots)
        sessions = connection.execute(f"SELECT id FROM session WHERE directory IN ({marks}) AND parent_id IS NULL",
                                      tuple(sorted(roots))).fetchall()
        for (session_id,) in sessions:
            rows = connection.execute(
                "SELECT m.data, p.data, p.time_created FROM part p JOIN message m ON m.id = p.message_id "
                "WHERE p.session_id = ? ORDER BY p.time_created, p.id", (session_id,)).fetchall()
            yield session_id, list(_opencode_turns(rows))
    finally:
        connection.close()


def _opencode_model(message: dict[str, Any]) -> dict[str, Any] | None:
    fields = {"model": "modelID", "provider": "providerID", "effort": "variant"}
    meta = {name: message[key] for name, key in fields.items() if isinstance(message.get(key), str)}
    return meta if meta.get("model") else None


def _opencode_turns(rows: Iterable[tuple[str, str, Any]]) -> Iterator[tuple[Any, ...]]:
    for message_raw, part_raw, created in rows:
        try:
            message, part = json.loads(message_raw), json.loads(part_raw)
        except ValueError:
            continue
        if not isinstance(message, dict) or not isinstance(part, dict):
            continue
        ts = _iso(created)
        if part.get("type") == "tool" and (part.get("state") or {}).get("status") == "error":
            yield ts, "error", ""
        elif part.get("type") == "text" and not part.get("synthetic"):
            role = message.get("role")
            if role in ("user", "assistant") and part.get("text"):
                yield ts, role, str(part["text"]), _opencode_model(message) if role == "assistant" else None


_antigravity_cache: dict[tuple[str, str], tuple[str, list[Compact]]] = {}


def _in_workspace(uris_raw: Any, roots: set[str]) -> bool:
    """Whether an Antigravity conversation ran in the workspace, under it, in a
    sibling worktree or in a folder that holds it, but not in a look-alike name."""
    try:
        uris = json.loads(uris_raw)
    except (ValueError, TypeError):
        return False
    if not isinstance(uris, list):
        return False
    cleaned = [u.removeprefix("file://").rstrip("/\\") for u in uris if isinstance(u, str)]
    return any(c == r or c.startswith((r + "/", r + "-worktrees/")) or r.startswith(c + "/")
               for c in cleaned for r in roots)


def antigravity_models(base: Path, offset_minutes: int | None = None) -> list[tuple[str, str]]:
    """``[(UTC time, label)]`` of the models Antigravity's logs say were selected,
    oldest first. A log line has local time and no year: the year comes from its
    file name and the offset from this machine, so logs copied from another time
    zone need ``offset_minutes``."""
    if offset_minutes is None:
        offset_minutes = int((time.localtime().tm_gmtoff or 0) / 60)
    found = []
    try:
        paths = sorted(base.rglob("cli-*.log"))
    except OSError:
        return []
    for path in paths:
        named = _LOG_NAME_RE.match(path.name)
        if not named:
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            match = _LOG_LABEL_RE.match(line)
            if not match:
                continue
            try:
                local = datetime.strptime(f"{named.group(1)}-{match.group(1)}-{match.group(2)} {match.group(3)}",
                                          "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
            stamp = (local - timedelta(minutes=offset_minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")
            found.append((stamp, match.group(4).strip()))
    return sorted(found)


def antigravity_model_at(timeline: list[tuple[str, str]], ts: Any) -> dict[str, Any] | None:
    """The model last selected before ``ts``, ``None`` when no log reaches back."""
    if not isinstance(ts, str):
        return None
    index = bisect_right([stamp for stamp, _ in timeline], ts) - 1
    if index < 0:
        return None
    label = timeline[index][1]
    split = _LABEL_EFFORT_RE.match(label)
    model = {"model": split.group(1), "effort": split.group(2)} if split else {"model": label}
    return {**model, "inferred": True}


def antigravity_raw(db: Path, roots: set[str]) -> Iterator[tuple[str, list[Turn]]]:
    """Every Antigravity conversation of the workspace with its uncut turns."""
    connection = sqlite3.connect("file:" + db.resolve().as_posix() + "?mode=ro", uri=True, timeout=2)
    try:
        rows = connection.execute("SELECT conversation_id, workspace_uris FROM conversation_summaries").fetchall()
    finally:
        connection.close()
    for session_id, uris_raw in rows:
        path = db.parent / "brain" / session_id / ".system_generated" / "logs" / "transcript.jsonl"
        if _in_workspace(uris_raw, roots) and path.is_file():
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            yield session_id, list(_antigravity_turns(lines, antigravity_models(db.parent)))


def antigravity_sessions(db: Path, roots: set[str]) -> tuple[list[tuple[str, list[Compact]]], str]:
    """``[(session id, turns)]`` of the workspace's Antigravity sessions."""
    if not db.is_file():
        return [], "absent"
    uri = "file:" + db.resolve().as_posix() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=2)
    brain_dir = db.parent / "brain"
    try:
        rows = connection.execute(
            "SELECT conversation_id, workspace_uris, datetime(last_modified_time) "
            "FROM conversation_summaries ORDER BY last_modified_time DESC").fetchall()
        out = []
        for session_id, uris_raw, updated in rows:
            if len(out) >= MAX_SESSIONS:
                break
            if not _in_workspace(uris_raw, roots):
                continue

            key = (str(db), session_id)
            with _cache_lock:
                cached = _antigravity_cache.get(key)
            if cached is not None and cached[0] == updated:
                out.append((session_id, cached[1]))
                continue

            tpath = brain_dir / session_id / ".system_generated" / "logs" / "transcript.jsonl"
            if not tpath.is_file():
                continue
            try:
                lines = tpath.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            turns = _compacted(_antigravity_turns(lines, antigravity_models(db.parent)))
            with _cache_lock:
                _antigravity_cache[key] = (updated, turns)
            out.append((session_id, turns))
        return out, "ok" if out else "absent"
    finally:
        connection.close()


def _antigravity_turns(lines: Iterable[str],
                       timeline: list[tuple[str, str]] | None = None) -> Iterator[tuple[Any, ...]]:
    for line in lines:
        if not line.strip():
            continue
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if not isinstance(d, dict):
            continue
        ts = d.get("created_at")
        if d.get("status") == "ERROR":
            yield ts, "error", ""
        elif d.get("source") == "USER_EXPLICIT" and d.get("type") == "USER_INPUT":
            c = d.get("content", "")
            if "<USER_REQUEST>" in c:
                c = c.split("<USER_REQUEST>")[1].split("</USER_REQUEST>")[0].strip()
            yield ts, "user", str(c)
        elif d.get("source") == "MODEL" and d.get("type") == "PLANNER_RESPONSE" and d.get("content"):
            yield ts, "assistant", str(d["content"]), antigravity_model_at(timeline or [], ts)


# --- the combined read -----------------------------------------------------

def _read_files(directory: Path | None, harness: str,
                skills: dict[str, str], events: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    if directory is None or not directory.is_dir():
        return {"status": "absent", "sessions": 0}
    line_turn, markers = LINE_READERS[harness]
    read, skipped = 0, 0
    current = _newest(directory)[:MAX_SESSIONS]
    for path in current:
        try:
            if path.stat().st_size > SESSION_MAX_BYTES:
                skipped += 1
                continue
            turns = session_turns(path, line_turn, markers, LINE_MODELS.get(harness))
            attribute(turns, f"{harness}:{path.stem[-8:]}", skills, events)
            read += 1
        except OSError:
            skipped += 1
    # Sessions that dropped out of the newest ones leave the cache.
    keep, prefix = {str(p) for p in current}, str(directory)
    with _cache_lock:
        for key in [k for k in _file_cache if k.startswith(prefix) and k not in keep]:
            del _file_cache[key]
    info: dict[str, Any] = {"status": "ok" if read else "absent", "sessions": read}
    if skipped:
        info["detail"] = f"{skipped} session(s) skipped: too large or unreadable"
    return info


def read_all(root: Path, locations: dict[str, Path | None] | None = None,
             original: Path | None = None) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    """Phase events from every harness and a per-harness status.

    ``locations`` overrides where each harness's store is (tests, unusual
    installs); a harness mapped to ``None`` is skipped as ``absent``.
    """
    roots = {str(root).rstrip("/\\")}
    if original is not None:
        roots.add(str(original).rstrip("/\\"))
    skills = skill_stages()
    events: dict[str, list[dict[str, Any]]] = {}
    status: dict[str, Any] = {}
    overrides = locations or {}

    def guarded(name: str, run: Callable[[], dict[str, Any]]) -> None:
        try:
            status[name] = run()
        except Exception as exc:  # noqa: BLE001 - one broken store never fails the pane
            status[name] = {"status": "unreadable", "detail": type(exc).__name__}

    guarded("claude-code", lambda: _read_files(
        overrides["claude-code"] if "claude-code" in overrides else claude_dir(roots),
        "claude-code", skills, events))
    guarded("pi", lambda: _read_files(
        overrides["pi"] if "pi" in overrides else pi_dir(roots), "pi", skills, events))

    def opencode() -> dict[str, Any]:
        db = overrides["opencode"] if "opencode" in overrides else opencode_db()
        if db is None:
            return {"status": "absent", "sessions": 0}
        sessions, state = opencode_sessions(db, roots)
        for session_id, turns in sessions:
            attribute(turns, f"opencode:{session_id[-8:]}", skills, events)
        return {"status": state, "sessions": len(sessions)}

    guarded("opencode", opencode)

    def antigravity() -> dict[str, Any]:
        db = overrides["antigravity"] if "antigravity" in overrides else antigravity_db()
        if db is None or not db.is_file():
            return {"status": "absent", "sessions": 0}
        sessions, state = antigravity_sessions(db, roots)
        for session_id, turns in sessions:
            attribute(turns, f"antigravity:{session_id[-8:]}", skills, events)
        return {"status": state, "sessions": len(sessions)}

    guarded("antigravity", antigravity)
    return events, status


def clear_cache() -> None:
    """Forget every cached session (tests, or a fresh install)."""
    with _cache_lock:
        _file_cache.clear()
        _opencode_cache.clear()
        _antigravity_cache.clear()


__all__ = ["HARNESSES", "HARNESS_NAMES", "LINE_MODELS", "UNASSIGNED", "antigravity_model_at", "antigravity_models",
           "attribute", "clear_cache", "command_of", "compact", "model_label",
           "operator_text", "read_all", "related_dirs", "session_turns", "skill_stages", "stage_for"]
