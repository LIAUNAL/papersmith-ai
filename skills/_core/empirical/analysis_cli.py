#!/usr/bin/env python3
"""The analysis log of an empirical study: every analysis run, labelled.

    analysis_cli.py run --outcome <id> [--plan <entry>] [--script <file>] [--input <file>]... \
        [--output <file>]... [--note <text>] --root . -- <command ...>
    analysis_cli.py record --by <operator> --tool <name> --outcome <id> [--plan <entry>] \
        [--script <file>] [--input <file>]... --output <file> [--output <file>]... [--note <text>] --root .
    analysis_cli.py status --root .
    analysis_cli.py repair --by <operator> --root .

``run`` wraps an analysis: before running it, it hashes the script (``--script``,
or the first argument after the program that names a file in the workspace,
or the program itself when it is such a file), every ``--input`` (with the
``datasets`` QC hash when the input is a registered dataset file) and takes
the protocol lock's sha256; it runs the command in the workspace root, then
hashes its stdout, stderr (kept under ``analysis/streams/``) and every
``--output``, and appends one entry to ``analysis/log.jsonl``. A ``run-started`` entry is appended before
the command runs and the ``run`` entry after it, so a failed second append
still leaves a trace. ``run`` writes ``analysis/.gitignore`` (``streams/``)
when it is absent, never over the operator's file, and warns
``STREAMS_NOT_IGNORED`` when that file does not ignore the streams. ``record``
appends the operator's attested entry for an analysis run outside smith (a
GUI tool such as SPSS or the R GUI). Decision D8 of
``odd/tasks/paper-type-lines.md``. ``repair --by`` moves a torn final line (an
interrupted append) to ``analysis/torn/<sha256>`` and records the move in
``analysis/repairs.jsonl``; it changes nothing else.

No flag sets the label: each entry is ``confirmatory`` or ``exploratory`` as
``analysis_log.compute_label`` derives it (decision D7). The log is
append-only and chained; a corrupt line refuses every further append.

Each verb prints one JSON object. ``run`` records the command's exit code and
exits 0 once the entry is written, whatever that code was. A refusal prints
``{"ok": false, "error": <CODE>, "message": ...}`` and exits 1 (usage errors
exit 2). Refusal codes: ``USAGE``, ``APPROVER_MISSING``, ``FIELD_MISSING``,
``OUTCOME_INVALID``, ``PLAN_ENTRY_INVALID``, ``TEXT_INVALID``,
``PATH_OUTSIDE_WORKSPACE``, ``SCRIPT_ABSENT``, ``SCRIPT_NOT_FOUND``,
``INPUT_ABSENT``, ``OUTPUT_ABSENT``, ``OUTPUT_MISSING``, ``COMMAND_NOT_FOUND``,
``ANALYSIS_LOG_CORRUPT``, ``ANALYSIS_LOG_TORN``, ``ANALYSIS_LOG_NOT_TORN``,
``PROTOCOL_PARSER_UNAVAILABLE``, ``INTERNAL_ERROR``.
"""

from __future__ import annotations

import sys as _floor_sys
if _floor_sys.version_info < (3, 11):  # the package floor (pyproject requires-python >=3.11)
    _floor_sys.stdout.write('{"ok": false, "error": "PYTHON_VERSION_UNSUPPORTED", "message": "this skill needs '
                            'Python 3.11+; the running interpreter is %d.%d. Run it with the workspace '
                            'environment (.micromamba/envs/papersmith/bin/python) or the smith interpreter."}\n'
                            % _floor_sys.version_info[:2])
    raise SystemExit(2)

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

if __package__ in (None, ""):  # run as a script: make `skills._core.empirical` importable
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from skills._core.empirical import analysis_log, records  # noqa: E402
    from skills._core.empirical.study_cli import _atomic_write, _now, _operator, _out, _Parser, _text  # noqa: E402
else:
    from . import analysis_log, records
    from .study_cli import _atomic_write, _now, _operator, _out, _Parser, _text

try:
    import fcntl
except ImportError:  # not POSIX: appends are still checked, only not serialized
    fcntl = None

StudyError = records.StudyError


def _workspace_file(root: Path, given: str, code: str, flag: str, must_exist: bool = True) -> tuple[Path, str]:
    candidate = Path(given) if Path(given).is_absolute() else root / given
    resolved, base = candidate.resolve(), root.resolve()
    if resolved != base and base not in resolved.parents:
        raise StudyError("PATH_OUTSIDE_WORKSPACE", f"{flag} {given} is outside the workspace {base}")
    if must_exist and not resolved.is_file():
        raise StudyError(code, f"{flag} {given} is not a file")
    return resolved, resolved.relative_to(base).as_posix()


def _dataset(root: Path, rel: str, digest: str) -> dict | None:
    """The `datasets` QC record of a registered dataset file (its hash at QC time), or None."""
    try:
        registry = json.loads((root / "datasets" / "registry.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    for entry in registry if isinstance(registry, list) else []:
        if isinstance(entry, dict) and rel in (entry.get("files") or []):
            try:
                qc = json.loads((root / "datasets" / str(entry.get("slug")) / "qc.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                qc = None
            qc = qc if isinstance(qc, dict) and qc.get("file") == rel else {}
            return {"slug": entry.get("slug"), "qc_sha256": qc.get("sha256"), "qc_status": qc.get("status"),
                    "dictionary_sha256": (qc.get("dictionary") or {}).get("sha256"),
                    "matches_qc": qc.get("sha256") == digest if qc.get("sha256") else None}
    return None


def _hashed(root: Path, paths: list[str], code: str, flag: str) -> list[dict]:
    out = []
    for given in paths:
        path, rel = _workspace_file(root, given, code, flag)
        digest = records.sha256(path)
        item = {"path": rel, "sha256": digest}
        if flag == "--input":
            item["dataset"] = _dataset(root, rel, digest)
        out.append(item)
    return out


def _script(root: Path, given: str | None, command: list[str]) -> dict:
    if given:
        path, rel = _workspace_file(root, given, "SCRIPT_ABSENT", "--script")
        return {"path": rel, "sha256": records.sha256(path)}
    for arg in command[1:] + command[:1]:
        try:
            path, rel = _workspace_file(root, arg, "SCRIPT_ABSENT", "the command")
        except (StudyError, OSError, ValueError):
            continue
        return {"path": rel, "sha256": records.sha256(path)}
    raise StudyError("SCRIPT_NOT_FOUND", "no argument of the command names a file in the workspace; name the "
                                         "analysis script with --script")


def _plan(given: str | None) -> str | None:
    if given is None:
        return None
    if given not in analysis_log.PLAN_ENTRIES:
        raise StudyError("PLAN_ENTRY_INVALID", f"--plan {given!r} is not an analysis-plan entry; one of "
                                               f"{', '.join(analysis_log.PLAN_ENTRIES)}")
    return given


def _outcome(given: str) -> str:
    value = (given or "").strip()
    if not analysis_log.OUTCOME_TOKEN.match(value):
        raise StudyError("OUTCOME_INVALID", "--outcome names the outcome analysed: a protocol id (O1) or a short "
                                            "name of letters, digits, '.', '_' or '-'")
    return value


def _append(root: Path, entry: dict) -> dict:
    """Append ``entry`` under an exclusive lock, chained to the last line; refuses a corrupt log."""
    path = root / analysis_log.LOG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a+b") as stream:
        if fcntl is not None:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        stream.seek(0)
        data = stream.read()
        entries = analysis_log.parse_log(data)
        lines = [line for line in data.split(b"\n") if line]
        seq = len(entries) + 1
        entry = {"schema": analysis_log.SCHEMA, "seq": seq, "id": f"A{seq:04d}", **entry,
                 "prev": analysis_log.sha256_bytes(lines[-1]) if lines else None}
        stream.seek(0, os.SEEK_END)
        # A complete last entry may lack its newline (a write cut right after it): start a new line.
        lead = b"\n" if data and not data.endswith(b"\n") else b""
        stream.write(lead + json.dumps(entry, ensure_ascii=False, sort_keys=True).encode("utf-8") + b"\n")
        stream.flush()
        os.fsync(stream.fileno())
    return entry


def _stream(root: Path, data: bytes) -> str:
    digest = analysis_log.sha256_bytes(data)
    target = root / analysis_log.STREAMS_DIR / digest
    if not target.is_file():
        _atomic_write(target, data)
    return digest


def _ignore_streams(root: Path) -> list[dict]:
    """Write ``analysis/.gitignore`` ignoring the streams when it is absent; warn when the
    operator's own file does not ignore them (it is never overwritten)."""
    path = root / analysis_log.STREAMS_IGNORE
    if not path.exists():
        _atomic_write(path, b"streams/\n")
        return []
    try:
        lines = {line.strip() for line in path.read_text(encoding="utf-8").splitlines()}
    except (OSError, UnicodeDecodeError):
        lines = set()
    if lines & {"streams", "streams/", "/streams", "/streams/", "streams/*", "/streams/*"}:
        return []
    return [{"code": "STREAMS_NOT_IGNORED",
             "message": f"{analysis_log.STREAMS_IGNORE} does not ignore streams/; the captured stdout and stderr "
                        "may hold participant data: add `streams/` to it"}]


def _launchable(root: Path, program: str) -> None:
    """Refuse a command that cannot start before any entry is written."""
    candidate = Path(program) if Path(program).is_absolute() else root / program
    if os.sep in program or "/" in program:
        found = candidate.is_file() and os.access(candidate, os.X_OK)
    else:
        found = shutil.which(program) is not None
    if not found:
        raise StudyError("COMMAND_NOT_FOUND", f"{program} cannot be run (not found or not executable)")


def _labelled(root: Path, args) -> dict:
    outcome, plan = _outcome(args.outcome), _plan(args.plan)
    label, reason, protocol = analysis_log.compute_label(root, outcome, plan)
    note = _text(args.note or "", "--note") or None
    return {"outcome": outcome, "plan": plan, "label": label, "label_reason": reason, "protocol": protocol,
            "note": note}


def cmd_run(args, root: Path) -> dict:
    command = args.command
    if not command:
        raise StudyError("USAGE", "the analysis command follows `--`: `run --outcome O1 -- python analysis.py`")
    analysis_log.read_log(root)  # a corrupt log refuses before anything runs
    head = _labelled(root, args)
    script = _script(root, args.script, command)
    inputs = _hashed(root, args.input, "INPUT_ABSENT", "--input")
    def hashed_outputs() -> list[dict]:
        out = []
        for given in args.output:
            path, rel = _workspace_file(root, given, "OUTPUT_ABSENT", "--output", must_exist=False)
            out.append({"path": rel, "sha256": records.sha256(path) if path.is_file() else None})
        return out

    prior = hashed_outputs()
    _launchable(root, command[0])
    warnings = _ignore_streams(root)
    started = _now()
    # Logged before the command runs: if the completing append fails, this entry still records the run.
    opened = _append(root, {"kind": analysis_log.STARTED, "at": started, "attested": False, "by": None, "tool": None,
                            **head, "script": script, "inputs": inputs, "outputs": prior, "command": command,
                            "exit_code": None, "duration_s": None, "stdout_sha256": None, "stderr_sha256": None})
    clock = time.perf_counter()
    try:
        proc = subprocess.run(command, cwd=str(root), capture_output=True, check=False)
    except (FileNotFoundError, PermissionError) as exc:
        raise StudyError("COMMAND_NOT_FOUND", f"{command[0]} cannot be run ({exc.strerror or exc}); "
                                              f"{opened['id']} stays an interrupted run") from None
    duration = round(time.perf_counter() - clock, 3)
    entry = _append(root, {"kind": "run", "at": started, "attested": False, "by": None, "tool": None, **head,
                           "script": script, "inputs": inputs, "outputs": hashed_outputs(), "command": command,
                           "exit_code": proc.returncode, "duration_s": duration, "started": opened["id"],
                           "stdout_sha256": _stream(root, proc.stdout), "stderr_sha256": _stream(root, proc.stderr)})
    result = {"ok": True, "path": analysis_log.LOG_PATH, "entry": entry}
    if warnings:
        result["warnings"] = warnings
    return result


def cmd_record(args, root: Path) -> dict:
    by = _operator(args)
    tool = _text(args.tool or "", "--tool")
    if not tool:
        raise StudyError("FIELD_MISSING", "--tool names the program the analysis ran in (SPSS, R GUI, ...)")
    if not args.output:
        raise StudyError("OUTPUT_MISSING", "an attested analysis names at least one --output it produced")
    analysis_log.read_log(root)
    head = _labelled(root, args)
    script = _hashed(root, [args.script], "SCRIPT_ABSENT", "--script")[0] if args.script else None
    entry = _append(root, {"kind": "record", "at": _now(), "attested": True, "by": by, "tool": tool, **head,
                           "script": script, "inputs": _hashed(root, args.input, "INPUT_ABSENT", "--input"),
                           "outputs": _hashed(root, args.output, "OUTPUT_ABSENT", "--output"), "command": None,
                           "exit_code": None, "duration_s": None, "stdout_sha256": None, "stderr_sha256": None})
    return {"ok": True, "path": analysis_log.LOG_PATH, "entry": entry}


def cmd_status(args, root: Path) -> dict:
    return {"ok": True, **analysis_log.status(root)}


def cmd_repair(args, root: Path) -> dict:
    """Move a torn final line (an interrupted append) aside, record the move, keep every entry."""
    by = _operator(args)
    path = root / analysis_log.LOG_PATH
    if not path.is_file():
        raise StudyError("ANALYSIS_LOG_NOT_TORN", f"{analysis_log.LOG_PATH} does not exist; there is nothing to repair")
    with open(path, "r+b") as stream:
        if fcntl is not None:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        data = stream.read()
        tail = analysis_log.torn_tail(data)
        if not tail:
            analysis_log.parse_log(data)  # a corrupt log keeps its own refusal
            raise StudyError("ANALYSIS_LOG_NOT_TORN", f"{analysis_log.LOG_PATH} ends with a complete entry; "
                                                      "there is no torn line to repair")
        kept = data[:len(data) - len(tail)]
        entries = analysis_log.parse_log(kept)  # refuses ANALYSIS_LOG_CORRUPT, changing nothing
        digest = analysis_log.sha256_bytes(tail)
        moved = f"{analysis_log.TORN_DIR}/{digest}"
        if not (root / moved).is_file():
            _atomic_write(root / moved, tail)  # the bytes are kept before the log changes
        repair = {"at": _now(), "by": by, "log": analysis_log.LOG_PATH, "log_bytes_before": len(data),
                  "tail_bytes": len(tail), "tail_sha256": digest, "moved_to": moved, "entries_kept": len(entries)}
        repairs = root / analysis_log.REPAIRS_PATH
        with open(repairs, "ab") as record:
            record.write(json.dumps(repair, ensure_ascii=False, sort_keys=True).encode("utf-8") + b"\n")
            record.flush()
            os.fsync(record.fileno())
        stream.truncate(len(kept))
        stream.flush()
        os.fsync(stream.fileno())
    return {"ok": True, "path": analysis_log.LOG_PATH, "repair": repair}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    command: list[str] = []
    if "--" in argv:
        split = argv.index("--")
        argv, command = argv[:split], argv[split + 1:]
    parser = _Parser(prog="analysis_cli.py", description="The labelled analysis log of an empirical study.",
                     allow_abbrev=False)
    sub = parser.add_subparsers(dest="verb", required=True)
    verbs = {"run": cmd_run, "record": cmd_record, "status": cmd_status, "repair": cmd_repair}
    for name in verbs:
        verb = sub.add_parser(name, allow_abbrev=False)
        verb.error = parser.error  # type: ignore[method-assign]
        verb.add_argument("--root", default=".")
        if name == "repair":
            verb.add_argument("--by", default="")
        if name in ("status", "repair"):
            continue
        verb.add_argument("--outcome", required=True)
        verb.add_argument("--plan", default=None)
        verb.add_argument("--script", default=None)
        verb.add_argument("--input", action="append", default=[])
        verb.add_argument("--output", action="append", default=[])
        verb.add_argument("--note", default=None)
    sub.choices["record"].add_argument("--by", default="")
    sub.choices["record"].add_argument("--tool", default=None)
    args = parser.parse_args(argv)
    if args.verb != "run" and command:
        parser.error(f"`{args.verb}` runs no command; drop everything after `--`")
    args.command = command
    try:
        result = verbs[args.verb](args, Path(args.root))
    except StudyError as error:
        return _out({"ok": False, "error": error.code, "message": error.message}, 2 if error.code == "USAGE" else 1)
    except Exception as exc:  # a bug, reported typed so a caller can quote it
        return _out({"ok": False, "error": "INTERNAL_ERROR", "message": f"{type(exc).__name__}: {exc}"}, 1)
    return _out(result, 0 if result.get("ok") else 1)


if __name__ == "__main__":
    sys.exit(main())
