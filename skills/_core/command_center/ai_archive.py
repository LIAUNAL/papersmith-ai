"""The workspace's own record of every conversation with an AI agent.

Harnesses keep their sessions on one machine and may delete them, so the
dashboard's history could lose them. :func:`sync` copies every operator prompt
and every agent answer, in full, into ``.papersmith/ai-history/``:

    <harness>-<session>.jsonl    one JSON object per line
    {"id": "<16 hex>", "ts": "<when>", "role": "user|assistant|error", "text": "..."}

The folder is tracked by git. One file per session is what lets two machines
write at once without a merge conflict, and a file only ever grows. Secrets are
redacted before anything is written: :func:`redact` holds the patterns, and it
catches the common shapes, not every secret a prompt can hold.

A subagent's session is ``<session>-sub-<name>``, and a tutor thread is
``tutor-<math-tutor|experiments-tutor>``. Harness-written turns (reminders,
compaction summaries, interruptions, API errors) are not operator turns and stay
out. :func:`sync` skips a source that has not changed since the last run, using
``.papersmith/cache/ai-archive-state.json``; the ids make it idempotent anyway.

    python -m skills._core.command_center.ai_archive sync --root .
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator

from . import ai_transcripts

ARCHIVE_REL = ".papersmith/ai-history"
STATE_REL = ".papersmith/cache/ai-archive-state.json"
TUTORS = ("math-tutor", "experiments-tutor")
SYNC_INTERVAL_SECONDS = 60
MAX_LINE_BYTES = 8 * 1024 * 1024

REDACTED = "[REDACTED]"
_SECRETS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(r"\bgithub_pat_\w{20,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{30,}"),
    re.compile(r"\bxox[abprs]-[0-9A-Za-z-]{10,}"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{16,}"),
    re.compile(r"(?i)\b(?:password|passwd|secret|token|api[_-]?key|\w*_KEY)\b\s*[:=]\s*[\"']?[^\s\"']{6,}[\"']?"),
)
_UNSAFE = re.compile(r"[^A-Za-z0-9_.-]+")

_sync_lock = threading.Lock()
_last_sync: dict[str, float] = {}


def redact(text: str) -> str:
    """``text`` with what looks like a credential replaced by ``[REDACTED]``."""
    for pattern in _SECRETS:
        text = pattern.sub(REDACTED, text)
    return text


def _file_name(harness: str, session: str) -> str:
    safe = re.sub(r"\.\.+", "", _UNSAFE.sub("-", session))
    return f"{harness}-{re.sub(r'-+', '-', safe).strip('-')}.jsonl"


def _records(harness: str, session: str, turns: Iterable[ai_transcripts.Turn]) -> Iterator[dict[str, Any]]:
    """What a session's raw turns leave in the archive, each with its stable id."""
    previous: tuple[str, str] | None = None
    for ts, role, text in turns:
        if role == "user":
            kept = ai_transcripts.operator_text(text)
            if kept is None:
                continue
            command = ai_transcripts.command_of(kept)
            text = f"/{command[0]} {command[1]}".strip() if command else kept
        elif role == "assistant" and not text.strip():
            continue
        if role == "user" and previous == (role, text):
            continue
        previous = (role, text)
        clean = redact(text)
        stamp = ts if isinstance(ts, str) else None
        ident = hashlib.sha256(f"{harness}|{session}|{stamp}|{role}|{clean}".encode()).hexdigest()[:16]
        yield {"id": ident, "ts": stamp, "role": role, "text": clean}


def _append(root: Path, harness: str, session: str, turns: Iterable[ai_transcripts.Turn]) -> int:
    """Add the turns the session's file does not hold yet; how many were added."""
    folder = root / ARCHIVE_REL
    path = folder / _file_name(harness, session)
    known: set[str] = set()
    if path.is_file():
        known = {r["id"] for r in _read(path)}
    fresh = [r for r in _records(harness, session, turns) if r["id"] not in known]
    if fresh:
        folder.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            for record in fresh:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return len(fresh)


def _read(path: Path) -> list[dict[str, Any]]:
    found = []
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            try:
                record = json.loads(raw)
            except ValueError:
                continue
            if isinstance(record, dict) and isinstance(record.get("id"), str):
                found.append(record)
    except (OSError, UnicodeDecodeError):
        return []
    return found


def _file_turns(path: Path, line_turn: Callable[[dict[str, Any]], Any]) -> Iterator[ai_transcripts.Turn]:
    with path.open("rb") as handle:
        for raw in handle:
            if len(raw) > MAX_LINE_BYTES:
                continue
            try:
                line = json.loads(raw)
            except ValueError:
                continue
            turn = line_turn(line) if isinstance(line, dict) else None
            if turn:
                yield turn


def _sub_line(line: dict[str, Any]) -> Any:
    return ai_transcripts.claude_line({**line, "isSidechain": False})


def _state(root: Path) -> dict[str, list[int]]:
    try:
        data = json.loads((root / STATE_REL).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _forget_state(root: Path) -> None:
    (root / STATE_REL).unlink(missing_ok=True)


def _sync_file(root: Path, state: dict[str, list[int]], harness: str, session: str, path: Path,
               reader: Callable[[Path], Iterable[ai_transcripts.Turn]]) -> int:
    stat = path.stat()
    mark = [stat.st_size, stat.st_mtime_ns]
    if state.get(str(path)) == mark:
        return 0
    added = _append(root, harness, session, reader(path))
    state[str(path)] = mark
    return added


def _sync_directory(root: Path, state: dict[str, list[int]], harness: str, directory: Path) -> int:
    line_turn = ai_transcripts.LINE_READERS[harness][0]
    added = 0
    for path in sorted(directory.glob("*.jsonl")):
        added += _sync_file(root, state, harness, path.stem, path, lambda p: _file_turns(p, line_turn))
        for sub in sorted((directory / path.stem / "subagents").glob("*.jsonl")):
            added += _sync_file(root, state, harness, f"{path.stem}-sub-{sub.stem}", sub,
                                lambda p: _file_turns(p, _sub_line))
    return added


def _tutor_turns(path: Path) -> Iterator[ai_transcripts.Turn]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    roles = {"reader": "user", "tutor": "assistant"}
    for turn in data.get("turns") or [] if isinstance(data, dict) else []:
        if isinstance(turn, dict) and turn.get("role") in roles and isinstance(turn.get("message"), str):
            yield turn.get("at"), roles[turn["role"]], turn["message"]


def sync(root: Path | str, locations: dict[str, Any] | None = None,
         original: Path | None = None) -> dict[str, Any]:
    """Copy what is new from every harness into the archive. Never raises: a
    store that cannot be read is reported and the others still run."""
    root = Path(root).expanduser().resolve()
    roots = {str(root)} | ({str(original).rstrip("/\\")} if original else set())
    overrides = locations or {}
    state = _state(root)
    added = 0
    problems: dict[str, str] = {}

    def guarded(name: str, run: Callable[[], int]) -> None:
        nonlocal added
        try:
            added += run()
        except Exception as exc:  # noqa: BLE001 - one broken store never stops the others
            problems[name] = type(exc).__name__

    def files(harness: str, finder: Callable[[set[str]], Path | None], base: Path) -> int:
        chosen = overrides[harness] if harness in overrides else finder(roots)
        folders = [chosen] if chosen else []
        if harness not in overrides:
            folders += [d for d in ai_transcripts.related_dirs(base, roots) if d not in folders]
        return sum(_sync_directory(root, state, harness, Path(d)) for d in folders if Path(d).is_dir())

    guarded("claude-code", lambda: files("claude-code", ai_transcripts.claude_dir, ai_transcripts.claude_projects()))
    guarded("pi", lambda: files("pi", ai_transcripts.pi_dir, ai_transcripts.pi_sessions_base()))

    def database(harness: str, default: Callable[[], Path],
                 reader: Callable[[Path, set[str]], Iterable[tuple[str, list[ai_transcripts.Turn]]]]) -> int:
        db = overrides[harness] if harness in overrides else default()
        if db is None or not Path(db).is_file():
            return 0
        return sum(_append(root, harness, session, turns) for session, turns in reader(Path(db), roots))

    guarded("opencode", lambda: database("opencode", ai_transcripts.opencode_db, ai_transcripts.opencode_raw))
    guarded("antigravity", lambda: database("antigravity", ai_transcripts.antigravity_db,
                                            ai_transcripts.antigravity_raw))
    for tutor in TUTORS:
        thread = root / ".papersmith" / tutor / "thread.json"
        if thread.is_file():
            guarded(tutor, lambda t=tutor, p=thread: _sync_file(root, state, "tutor", t, p, _tutor_turns))
    try:
        path = root / STATE_REL
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state), encoding="utf-8")
    except OSError as exc:
        problems["state"] = type(exc).__name__
    return {"added": added, "problems": problems, "folder": ARCHIVE_REL}


def sync_throttled(root: Path | str) -> None:
    """:func:`sync` at most once a minute per workspace, for a dashboard that polls."""
    key = str(root)
    with _sync_lock:
        if time.monotonic() - _last_sync.get(key, -SYNC_INTERVAL_SECONDS) < SYNC_INTERVAL_SECONDS:
            return
        _last_sync[key] = time.monotonic()
    sync(root)


def _harness_of(name: str) -> tuple[str, str] | None:
    for harness in (*ai_transcripts.HARNESSES, "tutor"):
        if name.startswith(harness + "-"):
            return harness, name[len(harness) + 1:]
    return None


def archived_sessions(root: Path) -> Iterator[tuple[str, str, list[dict[str, Any]]]]:
    """``(harness, session, records)`` of each archived main session."""
    try:
        paths = sorted((root / ARCHIVE_REL).glob("*.jsonl"))
    except OSError:
        return
    for path in paths:
        named = _harness_of(path.stem)
        if named and named[0] != "tutor" and "-sub-" not in named[1]:
            yield named[0], named[1], _read(path)


def session(root: Path, ref: str) -> list[dict[str, Any]] | None:
    """The full turns behind a chat event's ``ref``, ``None`` when none matches."""
    harness, _, tail = ref.partition(":")
    if harness not in ai_transcripts.HARNESSES or not re.fullmatch(r"[\w.-]+", tail):
        return None
    for name, stem, records in archived_sessions(root):
        if name == harness and stem.endswith(tail):
            return records
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ai_archive", description="The workspace's AI conversation record")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("sync", help="Copy new prompts and answers into .papersmith/ai-history/")
    run.add_argument("--root", default=".", help="Workspace root (default: current dir)")
    run.add_argument("--claude-sessions", help="Read Claude Code sessions from this folder instead")
    run.add_argument("--pi-sessions", help="Read Pi sessions from this folder instead")
    args = parser.parse_args(argv)
    locations: dict[str, Any] = {}
    if args.claude_sessions:
        locations.update({"claude-code": Path(args.claude_sessions), "pi": None, "opencode": None, "antigravity": None})
    if args.pi_sessions:
        locations.update({"pi": Path(args.pi_sessions), "opencode": None, "antigravity": None})
        locations.setdefault("claude-code", None)
    print(json.dumps(sync(args.root, locations or None), ensure_ascii=False, indent=2))
    return 0


__all__ = ["ARCHIVE_REL", "archived_sessions", "main", "redact", "session", "sync", "sync_throttled"]


if __name__ == "__main__":
    raise SystemExit(main())
