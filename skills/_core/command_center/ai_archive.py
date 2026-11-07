"""The workspace's own record of every conversation with an AI agent.

Harnesses keep their sessions on one machine and may delete them, so the
dashboard's history could lose them. :func:`sync` copies every operator prompt
and every agent answer, in full, into ``.papersmith/ai-history/``:

    <harness>-<session>.jsonl    one JSON object per line
    {"id": "<16 hex>", "ts": "<when>", "role": "user|assistant|error|phase", "text": "...",
     "model": "...", "effort": "...", "provider": "...", "inferred": true}

The last four appear on an agent's reply as far as its harness records them;
``inferred`` marks a model taken from a log rather than written with the reply.

The folder is tracked by git. One file per session is what lets two machines
write at once without a merge conflict, and a file only ever grows. Secrets are
redacted before anything is written: :func:`redact` holds the patterns, and it
catches the common shapes, not every secret a prompt can hold. A record's id comes
from the turn's place in its session, never from its text, so it reveals nothing
of what was redacted, and a new pattern rewrites the old records on the next sync
of the session (or ``scrub``, for all of them) instead of doubling them.

Personal data is masked the same way: email addresses, private and Tailscale IP
addresses, the user name inside home paths, phone numbers and SSH fingerprints.
Each workspace also masks its own people (:func:`private_terms`): the owners, names
and usernames of ``.papersmith/team.json``, the system user and git's ``user.name``.
Any other name in plain prose stays: no pattern can tell it from content.

When the dashboard syncs a workspace it also commits the folder, at most every ten
minutes, on the current branch and touching nothing else. It never pushes, and it
waits while a merge, rebase or similar is under way. Set
``PAPERSMITH_AI_HISTORY_COMMIT=0`` to turn it off.

A subagent's session is ``<session>-sub-<name>``, and a tutor thread is
``tutor-<math-tutor|experiments-tutor>``. Harness-written turns (reminders,
compaction summaries, interruptions, API errors) are not operator turns and stay
out. :func:`sync` skips a source that has not changed since the last run, using
``.papersmith/cache/ai-archive-state.json``; the ids make it idempotent anyway.

    python -m skills._core.command_center.ai_archive sync --root .
    python -m skills._core.command_center.ai_archive scrub --root .
    python -m skills._core.command_center.ai_archive commit --root .
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator

from . import ai_transcripts

ARCHIVE_REL = ".papersmith/ai-history"
STATE_REL = ".papersmith/cache/ai-archive-state.json"
TUTORS = ("math-tutor", "experiments-tutor")
SYNC_INTERVAL_SECONDS = 60
COMMIT_INTERVAL_SECONDS = 600
GIT_TIMEOUT_SECONDS = 30
#: How long git gets to release its locks once told to stop.
GIT_GRACE_SECONDS = 5
COMMIT_MESSAGE = "chore(history): archive AI conversations"
#: Markers under the git directory of an operation that must finish undisturbed.
GIT_BUSY = ("index.lock", "MERGE_HEAD", "REBASE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "BISECT_LOG", "rebase-merge", "rebase-apply")
MAX_LINE_BYTES = 8 * 1024 * 1024

REDACTED = "[REDACTED]"
MIN_TERM = 5
#: Shapes that are a credential wherever they appear.
_SECRETS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|\Z)", re.S),
    re.compile(r"\bsk-(?=[\w-]*\d)[A-Za-z0-9_-]{20,}"),
    re.compile(r"\b[spr]k_(?:live|test)_[A-Za-z0-9]{10,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(r"\bgithub_pat_\w{20,}"),
    re.compile(r"\bglpat-[\w-]{12,}"),
    re.compile(r"\bnpm_[A-Za-z0-9]{20,}"),
    re.compile(r"\bhf_[A-Za-z0-9]{20,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{30,}"),
    re.compile(r"\bya29\.[\w.-]{12,}"),
    re.compile(r"\bGOCSPX-[\w-]{12,}"),
    re.compile(r"\bKGAT_[A-Za-z0-9_-]{8,}"),
    re.compile(r"\btskey-[\w-]{12,}"),
    re.compile(r"\bxox[abprs]-[0-9A-Za-z-]{10,}"),
    re.compile(r"\beyJ[\w-]{8,}\.eyJ[\w-]{8,}\.[\w-]{8,}"),
    re.compile(r"hooks\.slack\.com/services/\S+"),
    re.compile(r"(?i)\bbearer\s+(?=[\w.~+/=-]*\d)[A-Za-z0-9._~+/=-]{16,}"),
    re.compile(r"(?i)\bbasic\s+[A-Za-z0-9+/]{12,}={0,2}"),
    re.compile(r"(?<=://)[^\s/:@]+:[^\s/@]+(?=@)"),
    re.compile(r"(?i)\blogin\s+\S+\s+password\s+\S+"),
    re.compile(r"\bsshpass\s+-p\s*\S+"),
    re.compile(r"(?<=\s)-u\s+[^\s:]+:\S+"),
    re.compile(r"--(?:password|passwd|token|api-key|secret)[= ]\S+"),
    re.compile(r"\"key\"\s*:\s*\"[0-9a-fA-F]{24,}\""),
)
#: ``name = value``, whose value decides: a code or prose assignment such as
#: ``sort_key=lambda`` is not a credential.
_ASSIGNED = re.compile(
    r"""(?i)(?<![\w-])(["']?)([\w-]{0,64}?(?:password|passwd|pwd|contrase\u00f1a|secret|token|api[_-]?key|access[_-]?key|private[_-]?key|_key))\1"""
    r"""\s*[:=]\s*(?:"([^"\n]+)"|'([^'\n]+)'|([^\s"',;]+))""")
#: Personal data: the pattern and what replaces it.
_PRIVATE = (
    (re.compile(r"(?<![\w.+-])(?!git@)[\w.+-]+@(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}\b"), "[EMAIL]"),
    (re.compile(r"(?<![\w.+-])[\w.+-]+@(?:gmail|hotmail|outlook|yahoo|icloud|proton|protonmail|unal)\b"), "[EMAIL]"),
    (re.compile(r"(?<![\d.])(?:10\.\d{1,3}|192\.168|172\.(?:1[6-9]|2\d|3[01])|100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7]))"
                r"\.\d{1,3}\.\d{1,3}(?:(?<=\.\d)|(?<=\.\d\d)|(?<=\.\d\d\d))(?![\d.]*\d)"), "[IP]"),
    (re.compile(r"(?<![\w.+-])[\w.-]+@(?=\[IP\])"), "[USER]@"),
    (re.compile(r"(/(?:Users|home)/)[A-Za-z0-9._-]+(?=/)"), r"\1[USER]"),
    (re.compile(r"(-Users-|-home-)[A-Za-z0-9._]+(?=-)"), r"\1[USER]"),
    (re.compile(r"([A-Za-z]:\\+Users\\+)[^\\\s]+"), r"\1[USER]"),
    (re.compile(r"(?<![\w.])\+\d{1,3}[\s.-]?(?:\(?\d{1,4}\)?[\s.-]?){2,4}\d{2,4}(?!\w)"), "[PHONE]"),
    (re.compile(r"\bSHA256:[A-Za-z0-9+/]{43}=?"), "[FINGERPRINT]"),
)
_PASSWORD_NAMES = ("password", "passwd", "pwd", "contrase\u00f1a")
_NOT_A_VALUE = frozenset({"none", "null", "true", "false", "str", "string"})
_UNSAFE = re.compile(r"[^A-Za-z0-9_.-]+")

_sync_lock = threading.Lock()
_last_sync: dict[str, float] = {}
_last_commit: dict[str, float] = {}
_reports: dict[str, dict[str, Any]] = {}
_syncing: set[str] = set()


def private_terms(root: Path) -> tuple[str, ...]:
    """The people of this workspace, longest first: what no pattern can recognize."""
    found: set[str] = set()
    try:
        team = json.loads((root / ".papersmith" / "team.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        team = None
    for member in team.get("members") or [] if isinstance(team, dict) else []:
        if not isinstance(member, dict):
            continue
        found.update(member.get(key) for key in ("owner", "displayName", "email"))
        accounts = member.get("accounts") if isinstance(member.get("accounts"), dict) else {}
        for account in accounts.values():
            if isinstance(account, dict):
                found.update(account.get(key) for key in ("username", "email"))
    try:
        found.add(getpass.getuser())
        found.add(_git(root, "config", "user.name").stdout.strip())
    except (OSError, KeyError, ValueError, subprocess.SubprocessError):
        pass
    kept = {term.strip() for term in found if isinstance(term, str) and len(term.strip()) >= MIN_TERM}
    return tuple(sorted(kept, key=lambda term: (-len(term), term)))


def redact(text: str, terms: Iterable[str] = ()) -> str:
    """``text`` with what looks like a credential replaced by ``[REDACTED]`` and
    personal data by its mask; ``terms`` are this workspace's people."""
    for pattern in _SECRETS:
        text = pattern.sub(REDACTED, text)
    text = _ASSIGNED.sub(_assigned, text)
    for pattern, mask in _PRIVATE:
        text = pattern.sub(mask, text)
    for term in terms:
        if len(term) >= MIN_TERM:
            text = re.sub(rf"(?<![\w-]){re.escape(term)}(?![\w-])", "[ACCOUNT]", text, flags=re.IGNORECASE)
    return text


def _assigned(match: re.Match[str]) -> str:
    name, value = match.group(2).lower(), match.group(3) or match.group(4) or match.group(5)
    if value.lower() in _NOT_A_VALUE or value == REDACTED:
        return match.group(0)
    has_letter, has_digit = re.search(r"[A-Za-z]", value), re.search(r"\d", value)
    quoted = bool(match.group(3) or match.group(4))
    secret = (len(value) >= 4 if any(word in name for word in _PASSWORD_NAMES)
              else (len(value) >= 12 and has_letter and has_digit) or (len(value) >= 24 and value.isalnum())
              or (quoted and " " not in value and len(value) >= 16))
    return match.group(0).replace(value, REDACTED) if secret else match.group(0)


def _file_name(harness: str, session: str) -> str:
    safe = re.sub(r"\.\.+", "", _UNSAFE.sub("-", session))
    return f"{harness}-{re.sub(r'-+', '-', safe).strip('-')}.jsonl"


def _records(harness: str, session: str, turns: Iterable[ai_transcripts.Turn],
             terms: Iterable[str] = ()) -> Iterator[dict[str, Any]]:
    """What a session's raw turns leave in the archive, each with its stable id."""
    previous: tuple[str, str] | None = None
    seen: dict[tuple[Any, str], int] = {}
    for turn in turns:
        ts, role, text = turn[:3]
        meta = turn[3] if len(turn) > 3 and isinstance(turn[3], dict) else {}
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
        # A lone surrogate can reach a transcript and cannot be written as UTF-8.
        text = text.encode("utf-8", "replace").decode("utf-8")
        stamp = ts if isinstance(ts, str) else None
        place = seen[(stamp, role)] = seen.get((stamp, role), 0) + 1
        ident = hashlib.sha256(f"{harness}|{session}|{stamp}|{role}|{place}".encode()).hexdigest()[:16]
        yield {"id": ident, "ts": stamp, "role": role, "text": redact(text, terms), **meta}


def _append(root: Path, harness: str, session: str, turns: Iterable[ai_transcripts.Turn],
            terms: Iterable[str] = ()) -> int:
    """Add the turns the session's file does not hold yet; how many were added."""
    folder = root / ARCHIVE_REL
    path = folder / _file_name(harness, session)
    if folder.is_symlink() or path.is_symlink():
        return 0
    known: dict[str, dict[str, Any]] = {}
    records = list(_records(harness, session, turns, terms))
    if path.is_file():
        _scrub_file(path, terms)
        known = {r["id"]: r for r in _read(path)}
        _add_models(path, known, records)
    fresh = [r for r in records if r["id"] not in known]
    if fresh:
        folder.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            for record in fresh:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return len(fresh)


def _write_records(path: Path, records: Iterable[dict[str, Any]]) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
    temporary.replace(path)


def _add_models(path: Path, known: dict[str, dict[str, Any]], records: list[dict[str, Any]]) -> None:
    """Give a record archived before its model was read the model it now has."""
    changed = False
    for record in records:
        old = known.get(record["id"])
        if old is not None and "model" in record and "model" not in old:
            old.update({k: v for k, v in record.items() if k not in ("id", "ts", "role", "text")})
            changed = True
    if changed:
        _write_records(path, known.values())


def _scrub_file(path: Path, terms: Iterable[str] = ()) -> bool:
    """Apply today's patterns to a session's records; whether anything changed."""
    records = _read(path)
    changed = False
    for record in records:
        clean = redact(str(record.get("text") or ""), terms)
        if clean != record.get("text"):
            record["text"] = clean
            changed = True
    if changed:
        _write_records(path, records)
    return changed


def scrub(root: Path | str) -> int:
    """Apply today's patterns to the whole archive; how many files changed."""
    root = Path(root).expanduser().resolve()
    terms = private_terms(root)
    return sum(1 for path in sorted((root / ARCHIVE_REL).glob("*.jsonl"))
               if not path.is_symlink() and _scrub_file(path, terms))


def _read(path: Path) -> list[dict[str, Any]]:
    """A session's records, each once: one bad line never costs the others."""
    found: dict[str, dict[str, Any]] = {}
    try:
        lines = path.read_bytes().splitlines()
    except OSError:
        return []
    for raw in lines:
        try:
            record = json.loads(raw.decode("utf-8"))
        except ValueError:
            continue
        if isinstance(record, dict) and isinstance(record.get("id"), str):
            found.setdefault(record["id"], record)
    return list(found.values())


def _file_turns(path: Path, line_turn: Callable[[dict[str, Any]], Any],
                line_model: Callable[[dict[str, Any], dict[str, Any]], Any] | None = None) -> Iterator[tuple[Any, ...]]:
    state: dict[str, Any] = {}
    with path.open("rb") as handle:
        for raw in handle:
            if len(raw) > MAX_LINE_BYTES:
                continue
            try:
                line = json.loads(raw)
            except ValueError:
                continue
            turn = line_turn(line) if isinstance(line, dict) else None
            meta = line_model(line, state) if line_model and isinstance(line, dict) else None
            if turn:
                yield (*turn, meta)


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
               reader: Callable[[Path], Iterable[ai_transcripts.Turn]], terms: Iterable[str] = ()) -> int:
    stat = path.stat()
    mark = [stat.st_size, stat.st_mtime_ns]
    if state.get(str(path)) == mark:
        return 0
    added = _append(root, harness, session, reader(path), terms)
    state[str(path)] = mark
    return added


def _sync_directory(root: Path, state: dict[str, list[int]], harness: str, directory: Path,
                    terms: Iterable[str] = ()) -> int:
    line_turn = ai_transcripts.LINE_READERS[harness][0]
    line_model = ai_transcripts.LINE_MODELS.get(harness)
    added = 0
    for path in sorted(directory.glob("*.jsonl")):
        added += _sync_file(root, state, harness, path.stem, path,
                            lambda p: _file_turns(p, line_turn, line_model), terms)
        for sub in sorted((directory / path.stem / "subagents").glob("*.jsonl")):
            added += _sync_file(root, state, harness, f"{path.stem}-sub-{sub.stem}", sub,
                                lambda p: _file_turns(p, _sub_line, line_model), terms)
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
    terms = private_terms(root)
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
        return sum(_sync_directory(root, state, harness, Path(d), terms) for d in folders if Path(d).is_dir())

    guarded("claude-code", lambda: files("claude-code", ai_transcripts.claude_dir, ai_transcripts.claude_projects()))
    guarded("pi", lambda: files("pi", ai_transcripts.pi_dir, ai_transcripts.pi_sessions_base()))

    def database(harness: str, default: Callable[[], Path],
                 reader: Callable[[Path, set[str]], Iterable[tuple[str, list[ai_transcripts.Turn]]]]) -> int:
        db = overrides[harness] if harness in overrides else default()
        if db is None or not Path(db).is_file():
            return 0
        return sum(_append(root, harness, session, turns, terms) for session, turns in reader(Path(db), roots))

    guarded("opencode", lambda: database("opencode", ai_transcripts.opencode_db, ai_transcripts.opencode_raw))
    guarded("antigravity", lambda: database("antigravity", ai_transcripts.antigravity_db,
                                            ai_transcripts.antigravity_raw))
    for tutor in TUTORS:
        thread = root / ".papersmith" / tutor / "thread.json"
        if thread.is_file():
            guarded(tutor, lambda t=tutor, p=thread: _sync_file(root, state, "tutor", t, p, _tutor_turns, terms))
    try:
        path = root / STATE_REL
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state), encoding="utf-8")
    except OSError as exc:
        problems["state"] = type(exc).__name__
    return {"added": added, "problems": problems, "folder": ARCHIVE_REL}


def _git(root: Path, *args: str, lock: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run git, whose output is UTF-8 whatever the locale says. Past its time it is
    asked to stop before it is killed: a killed git leaves ``index.lock`` behind, and
    that blocks every later git command of the operator. ``lock`` is that file, for a
    command that takes it; only a git that could not clean up gets it removed, since
    a git that stopped by itself released it and what is there now is someone else's."""
    command = ["git", "-C", str(root), *args]
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8",
                          errors="replace", env={**os.environ, "GIT_TERMINAL_PROMPT": "0"}) as process:
        try:
            out, err = process.communicate(timeout=GIT_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            process.terminate()
            forced = os.name == "nt"  # where terminate is a kill
            try:
                process.wait(GIT_GRACE_SECONDS)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                forced = True
            if forced and lock:
                lock.unlink(missing_ok=True)
            raise
    return subprocess.CompletedProcess(command, process.returncode, out, err)


def commit(root: Path | str) -> dict[str, Any]:
    """Mask the archive with today's rules, then commit that folder alone: records
    older than a rule never reach history. Nobody is there to answer a signing prompt,
    so this commit is not signed. ``status`` says what happened: ``committed``,
    ``unchanged``, ``disabled``, ``no-repository``, ``busy`` (an operation under way
    or a detached HEAD: the next run tries again) or ``failed``, for example when a
    hook refuses. It never pushes, and what the operator staged stays staged."""
    root = Path(root).expanduser().resolve()
    if os.environ.get("PAPERSMITH_AI_HISTORY_COMMIT") == "0":
        return {"status": "disabled"}
    try:
        located = _git(root, "rev-parse", "--absolute-git-dir")
        if located.returncode:
            return {"status": "no-repository"}
        git_dir = Path(located.stdout.strip())
        if any((git_dir / marker).exists() for marker in GIT_BUSY) or _git(root, "symbolic-ref", "-q", "HEAD").returncode:
            return {"status": "busy"}
        if not (root / ARCHIVE_REL).is_dir():
            return {"status": "unchanged"}
        scrub(root)
        staged = _git(root, "add", "--", ARCHIVE_REL, lock=git_dir / "index.lock")
        if staged.returncode:
            return {"status": "failed", "detail": staged.stderr.strip()[:200]}
        if not _git(root, "diff", "--cached", "--quiet", "--", ARCHIVE_REL).returncode:
            return {"status": "unchanged"}
        done = _git(root, "-c", "commit.gpgsign=false", "commit", "-q", "--only", "-m", COMMIT_MESSAGE,
                    "--", ARCHIVE_REL, lock=git_dir / "index.lock")
    except (OSError, subprocess.SubprocessError) as exc:
        return {"status": "failed", "detail": type(exc).__name__}
    if done.returncode:
        return {"status": "failed", "detail": (done.stderr or done.stdout).strip()[:200]}
    return {"status": "committed"}


def last_report(root: Path | str) -> dict[str, Any] | None:
    """What the last automatic run did, so a failure does not stay silent."""
    return _reports.get(str(Path(root).expanduser().resolve()))


def sync_throttled(root: Path | str) -> None:
    """:func:`sync` at most once a minute per workspace, for a dashboard that polls,
    and :func:`commit` at most every ten minutes."""
    # The kit's own checkout and a test's fixture run the dashboard too: only a
    # real workspace records its conversations by itself.
    if not (Path(root) / ".papersmith" / "version").is_file():
        return
    key = str(Path(root).expanduser().resolve())
    with _sync_lock:
        if key in _syncing or time.monotonic() - _last_sync.get(key, -SYNC_INTERVAL_SECONDS) < SYNC_INTERVAL_SECONDS:
            return
        _last_sync[key] = time.monotonic()
        _syncing.add(key)
    try:
        report = dict(sync(root))
        if time.monotonic() - _last_commit.get(key, -COMMIT_INTERVAL_SECONDS) >= COMMIT_INTERVAL_SECONDS:
            report["commit"] = commit(root)
            _last_commit[key] = time.monotonic()
        _reports[key] = report
    finally:
        with _sync_lock:
            _syncing.discard(key)


def sync_in_background(root: Path | str) -> None:
    """Keep the archive current from a route that must not wait for it."""
    def run() -> None:
        try:
            sync_throttled(root)
        except Exception:  # noqa: BLE001 - the next request tries again
            pass

    threading.Thread(target=run, daemon=True).start()


def _harness_of(name: str) -> tuple[str, str] | None:
    for harness in (*ai_transcripts.HARNESSES, "tutor"):
        if name.startswith(harness + "-"):
            return harness, name[len(harness) + 1:]
    return None


def archived_sessions(root: Path, skip: Iterable[str] = ()) -> Iterator[tuple[str, str, list[dict[str, Any]]]]:
    """``(harness, session, records)`` of each archived main session, in time
    order, leaving out the event refs in ``skip`` without reading them."""
    skipped = set(skip)
    try:
        paths = sorted((root / ARCHIVE_REL).glob("*.jsonl"))
    except OSError:
        return
    for path in paths:
        named = _harness_of(path.stem)
        if (named and named[0] != "tutor" and "-sub-" not in named[1]
                and f"{named[0]}:{named[1][-8:]}" not in skipped):
            # A file only grows, so a turn found later can sit after newer ones.
            yield named[0], named[1], sorted(_read(path), key=lambda r: r.get("ts") or "")


def session(root: Path, ref: str) -> list[dict[str, Any]] | None:
    """The full turns behind a chat event's ``ref``, ``None`` when none matches."""
    harness, _, tail = ref.partition(":")
    if harness not in ai_transcripts.HARNESSES or not re.fullmatch(r"[\w.-]+", tail):
        return None
    for name, stem, records in archived_sessions(root):
        if name == harness and stem.endswith(tail):
            return [{**r, "model_label": ai_transcripts.model_label(name, r)} if r.get("model") else r
                    for r in records]
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ai_archive", description="The workspace's AI conversation record")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("sync", help="Copy new prompts and answers into .papersmith/ai-history/")
    run.add_argument("--root", default=".", help="Workspace root (default: current dir)")
    run.add_argument("--claude-sessions", help="Read Claude Code sessions from this folder instead")
    run.add_argument("--pi-sessions", help="Read Pi sessions from this folder instead")
    clean = sub.add_parser("scrub", help="Apply today's secret patterns to the whole archive")
    clean.add_argument("--root", default=".", help="Workspace root (default: current dir)")
    save = sub.add_parser("commit", help="Commit .papersmith/ai-history/ alone")
    save.add_argument("--root", default=".", help="Workspace root (default: current dir)")
    args = parser.parse_args(argv)
    if args.command == "commit":
        print(json.dumps(commit(args.root)))
        return 0
    if args.command == "scrub":
        print(json.dumps({"files_changed": scrub(args.root)}))
        return 0
    locations: dict[str, Any] = {}
    if args.claude_sessions:
        locations.update({"claude-code": Path(args.claude_sessions), "pi": None, "opencode": None, "antigravity": None})
    if args.pi_sessions:
        locations.update({"pi": Path(args.pi_sessions), "opencode": None, "antigravity": None})
        locations.setdefault("claude-code", None)
    print(json.dumps(sync(args.root, locations or None), ensure_ascii=False, indent=2))
    return 0


__all__ = ["ARCHIVE_REL", "archived_sessions", "commit", "last_report", "main", "redact", "scrub", "session", "sync", "sync_in_background",
           "sync_throttled"]


if __name__ == "__main__":
    raise SystemExit(main())
