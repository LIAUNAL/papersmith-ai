"""Chat turns of every harness, attributed to dashboard phases.

Each reader turns one harness's local session store into ``(ts, role, text)``
turns (``role`` is ``user``, ``assistant`` or ``error``); :func:`attribute`
assigns them to phases the same way for every harness: a phase command opens
its phase and the turns that follow belong to it until the next one.

Stores (read-only, bounded; a missing store is ``absent``, never an error):

* ``claude-code``: ``$CLAUDE_CONFIG_DIR`` or ``~/.claude``, then
  ``projects/<path with every non-alphanumeric character as '-'>/*.jsonl``.
* ``pi``: ``$PI_CODING_AGENT_DIR`` or ``~/.pi/agent``, then
  ``sessions/--<path with '/', '\\' and ':' as '-'>--/*.jsonl``.
* ``opencode``: ``$XDG_DATA_HOME`` or ``~/.local/share``, then
  ``opencode/opencode.db`` (SQLite, opened read-only), sessions whose
  ``directory`` is the workspace.
* ``antigravity``: no readable store; reported as ``unsupported``.

When the slug directory is missing (a renamed or long path), the Claude Code
and Pi readers fall back to the session whose recorded ``cwd`` is the
workspace. Inside WSL every store is the Linux one; an agent running on the
Windows side keeps its sessions under ``/mnt/c/Users/...``, which the
``PAPERSMITH_<HARNESS>_SESSIONS`` variables point the reader to.

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
from datetime import datetime, timezone
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

Turn = tuple["str | None", str, str]

_COMMAND_RE = re.compile(r"<command-name>\s*/?([\w:.-]+)\s*</command-name>")
_ARGS_RE = re.compile(r"<command-args>(.*?)</command-args>", re.S)
_PI_SKILL_RE = re.compile(r"^<skill\s+name=\"([\w:.-]+)\"[^>]*>.*?</skill>(.*)$", re.S)
_EXPANDED_RE = re.compile(
    r"^Read `skills/([\w.-]+)/SKILL\.md` and follow it.*?`\$ARGUMENTS`:\s*(.*)$", re.S)
_SLASH_RE = re.compile(r"^/([\w:.-]+)(?:\s+(.*))?$", re.S)
_TAG_RE = re.compile(r"<[^>]+>")


def _clip(text: Any, limit: int = TEXT_MAX) -> str:
    value = " ".join(str(text or "").split())
    return value if len(value) <= limit else value[: limit - 1] + "…"


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


def attribute(turns: Iterable[Turn], ref: str, skills: dict[str, str],
              events: dict[str, list[dict[str, Any]]]) -> None:
    """Assign one session's turns to phases. Only the agent's last reply
    before the next user turn is kept."""
    stage: str | None = None
    reply: dict[str, Any] | None = None

    def flush() -> None:
        nonlocal reply
        if reply is not None and stage is not None:
            events.setdefault(stage, []).append(reply)
        reply = None

    for ts, role, text in turns:
        if role == "assistant":
            if text.strip() and stage is not None:
                reply = _event(ts, "agent_reply", _clip(text), ref, "agente")
            continue
        if role == "error":
            if stage is not None:
                events.setdefault(stage, []).append(
                    _event(ts, "error", "Una herramienta falló durante la fase", ref, "herramienta"))
            continue
        if (not text.strip() or "<local-command-stdout>" in text
                or text.lstrip().startswith("<system-reminder>")):
            continue
        command = command_of(text)
        target = stage_for(*command, skills) if command else None
        flush()
        if target is not None:
            stage = target
            events.setdefault(stage, []).append(
                _event(ts, "command", _clip(f"/{command[0]} {command[1]}".strip()), ref, "operador"))
        elif stage is not None and command is None:
            events.setdefault(stage, []).append(
                _event(ts, "user_message", _clip(_TAG_RE.sub(" ", text)), ref, "operador"))
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


def claude_dir(roots: set[str]) -> Path | None:
    override = os.environ.get("PAPERSMITH_CLAUDE_CODE_SESSIONS")
    if override:
        return Path(override).expanduser()
    base = _env_dir("CLAUDE_CONFIG_DIR", Path.home() / ".claude") / "projects"
    return _locate(base, [re.sub(r"[^A-Za-z0-9]", "-", r) for r in sorted(roots)], roots)


def pi_dir(roots: set[str]) -> Path | None:
    override = os.environ.get("PAPERSMITH_PI_SESSIONS")
    if override:
        return Path(override).expanduser()
    base = _env_dir("PI_CODING_AGENT_DIR", Path.home() / ".pi" / "agent") / "sessions"
    slugs = ["--" + re.sub(r"[/\\:]", "-", r.lstrip("/\\")) + "--" for r in sorted(roots)]
    return _locate(base, slugs, roots)


def opencode_db() -> Path:
    override = os.environ.get("PAPERSMITH_OPENCODE_SESSIONS")
    if override:
        return Path(override).expanduser()
    return _env_dir("XDG_DATA_HOME", Path.home() / ".local" / "share") / "opencode" / "opencode.db"


# --- per-harness turn readers ----------------------------------------------

def _jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open("rb") as handle:
        for raw in handle:
            if len(raw) > MAX_LINE_BYTES:
                continue
            try:
                line = json.loads(raw)
            except ValueError:
                continue
            if isinstance(line, dict):
                yield line


def _blocks(content: Any, text_type: str = "text") -> tuple[str, list[dict[str, Any]]]:
    if isinstance(content, str):
        return content, []
    blocks = [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []
    return "\n".join(str(b.get("text") or "") for b in blocks if b.get("type") == text_type), blocks


def claude_turns(path: Path) -> Iterator[Turn]:
    for line in _jsonl(path):
        if line.get("isSidechain") or line.get("isMeta"):
            continue
        kind, message = line.get("type"), line.get("message")
        if kind not in ("user", "assistant") or not isinstance(message, dict):
            continue
        text, blocks = _blocks(message.get("content"))
        if any(b.get("type") == "tool_result" and b.get("is_error") for b in blocks):
            yield line.get("timestamp"), "error", ""
        elif text:
            yield line.get("timestamp"), kind, text


def pi_turns(path: Path) -> Iterator[Turn]:
    for line in _jsonl(path):
        message = line.get("message")
        if line.get("type") != "message" or not isinstance(message, dict):
            continue
        role, ts = message.get("role"), line.get("timestamp")
        if role == "toolResult":
            if message.get("isError"):
                yield ts, "error", ""
        elif role in ("user", "assistant"):
            text, _ = _blocks(message.get("content"))
            if text:
                yield ts, role, text


def _iso(ms: Any) -> str | None:
    if not isinstance(ms, (int, float)) or isinstance(ms, bool):
        return None
    try:
        stamp = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None
    return stamp.strftime("%Y-%m-%dT%H:%M:%S.") + f"{stamp.microsecond // 1000:03d}Z"


def opencode_sessions(db: Path, roots: set[str]) -> tuple[list[tuple[str, list[Turn]]], str]:
    """``[(session id, turns)]`` of the workspace's OpenCode sessions."""
    if not db.is_file():
        return [], "absent"
    uri = "file:" + db.resolve().as_posix() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=2)
    try:
        marks = ",".join("?" for _ in roots)
        sessions = connection.execute(
            f"SELECT id FROM session WHERE directory IN ({marks}) AND parent_id IS NULL "
            "ORDER BY time_updated DESC LIMIT ?", (*sorted(roots), MAX_SESSIONS)).fetchall()
        out = []
        for (session_id,) in sessions:
            rows = connection.execute(
                "SELECT m.data, p.data, p.time_created FROM part p JOIN message m ON m.id = p.message_id "
                "WHERE p.session_id = ? ORDER BY p.time_created, p.id LIMIT ?",
                (session_id, MAX_DB_ROWS)).fetchall()
            out.append((session_id, list(_opencode_turns(rows))))
        return out, "ok" if sessions else "absent"
    finally:
        connection.close()


def _opencode_turns(rows: Iterable[tuple[str, str, Any]]) -> Iterator[Turn]:
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
                yield ts, role, str(part["text"])


# --- the combined read -----------------------------------------------------

def _read_files(directory: Path | None, reader: Callable[[Path], Iterator[Turn]], harness: str,
                skills: dict[str, str], events: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    if directory is None or not directory.is_dir():
        return {"status": "absent", "sessions": 0}
    read, skipped = 0, 0
    for path in _newest(directory)[:MAX_SESSIONS]:
        try:
            if path.stat().st_size > SESSION_MAX_BYTES:
                skipped += 1
                continue
            attribute(reader(path), f"{harness}:{path.stem[-8:]}", skills, events)
            read += 1
        except OSError:
            skipped += 1
    info: dict[str, Any] = {"status": "ok" if read else "absent", "sessions": read}
    if skipped:
        info["detail"] = f"{skipped} sesión(es) omitida(s): muy grandes o ilegibles"
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
        claude_turns, "claude-code", skills, events))
    guarded("pi", lambda: _read_files(
        overrides["pi"] if "pi" in overrides else pi_dir(roots), pi_turns, "pi", skills, events))

    def opencode() -> dict[str, Any]:
        db = overrides["opencode"] if "opencode" in overrides else opencode_db()
        if db is None:
            return {"status": "absent", "sessions": 0}
        sessions, state = opencode_sessions(db, roots)
        for session_id, turns in sessions:
            attribute(turns, f"opencode:{session_id[-8:]}", skills, events)
        return {"status": state, "sessions": len(sessions)}

    guarded("opencode", opencode)
    status["antigravity"] = {"status": "unsupported", "sessions": 0,
                             "detail": "Antigravity no deja un historial de chat legible en disco"}
    return events, status


__all__ = ["HARNESSES", "attribute", "command_of", "read_all", "skill_stages", "stage_for"]
