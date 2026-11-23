#!/usr/bin/env python3
"""Operator records of an empirical study: the protocol lock, ethics, registration.

    study_cli.py protocol approve --by <operator> [--revision protocol/<file>] --root .
    study_cli.py protocol amend   --by <operator> --reason <why> [--revision protocol/<file>] --root .
    study_cli.py protocol status  --root .
    study_cli.py ethics record --by <operator> --committee <name> --code <approval code> \
        --date <YYYY-MM-DD> --consent <route> --root .
    study_cli.py ethics record --by <operator> --not-applicable --reason <text> --root .
    study_cli.py registration record --by <operator> --registry <name> --id <id> \
        --date <YYYY-MM-DD> [--first-enrolment <YYYY-MM-DD>] --root .
    study_cli.py registration record --by <operator> --not-applicable --reason <text> --root .
    study_cli.py status --root .

``protocol approve`` passes gate G-STUDY-PROTOCOL: it pins a managed revision
of ``protocol/study-protocol-<slug>-vNN.md`` (the latest by default) by its
sha256 in ``study/protocol.lock.json``; ``protocol amend`` moves the lock to a
newer revision (or to the edited bytes of the locked one) and appends the
amendment with its reason. ``ethics record`` and ``registration record``
append the operator's record to ``study/ethics.json`` and
``study/registration.json``, bound to the lock's sha256: an amendment makes
them stale, reported as a warning. Every verb that records takes ``--by``; an
agent never records any of these on the operator's behalf.

Each verb prints one JSON object. A refusal prints ``{"ok": false, "error":
<CODE>, "message": ...}`` and exits 1 (usage errors exit 2). Refusal codes:
``USAGE``, ``APPROVER_MISSING``, ``PROTOCOL_ABSENT``, ``REVISION_INVALID``,
``REVISION_ABSENT``, ``REVISION_NOT_MANAGED``, ``REVISION_AMBIGUOUS``,
``REVISION_OLDER``, ``PROTOCOL_ALREADY_APPROVED``, ``PROTOCOL_NOT_APPROVED``,
``PROTOCOL_LOCK_CORRUPT``, ``PROTOCOL_CHANGED``, ``PROTOCOL_UNCHANGED``,
``AMENDMENT_REASON_MISSING``, ``FIELD_MISSING``, ``FIELDS_CONFLICT``,
``REASON_MISSING``, ``DATE_INVALID``, ``TEXT_INVALID``, ``RECORD_UNCHANGED``,
``ETHICS_CORRUPT``, ``REGISTRATION_CORRUPT``, ``INTERNAL_ERROR``.
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
import datetime as dt
import json
import os
import sys
import tempfile
from pathlib import Path

if __package__ in (None, ""):  # run as a script: make `skills._core.empirical` importable
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from skills._core.empirical import records  # noqa: E402
else:
    from . import records

StudyError = records.StudyError

ETHICS_FIELDS = (("committee", "--committee"), ("code", "--code"), ("date", "--date"), ("consent", "--consent"))
REGISTRATION_FIELDS = (("registry", "--registry"), ("id", "--id"), ("date", "--date"))
ENTRY_META = ("by", "at")


def _out(payload: dict, code: int = 0) -> int:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return code


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise SystemExit(_out({"ok": False, "error": "USAGE", "message": message}, 2))


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.")
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
        umask = os.umask(0)
        os.umask(umask)
        os.chmod(temp, 0o666 & ~umask)
        os.replace(temp, path)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise


def _write_json(path: Path, data) -> None:
    _atomic_write(path, (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))


def _operator(args) -> str:
    by = (args.by or "").strip()
    if not by:
        raise StudyError("APPROVER_MISSING", "--by names the operator who acts; an agent never approves or "
                                             "records on the operator's behalf")
    return _text(by, "--by")


def _text(value: str, flag: str) -> str:
    value = value.strip()
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise StudyError("TEXT_INVALID", f"{flag} holds a control character")
    return value


def _date(value: str, flag: str) -> str:
    try:
        parsed = dt.date.fromisoformat(value.strip())
    except ValueError:
        parsed = None
    if parsed is None or parsed.isoformat() != value.strip():
        raise StudyError("DATE_INVALID", f"{flag} {value!r} is not a calendar date written YYYY-MM-DD")
    return parsed.isoformat()


# --------------------------------------------------------------------------- protocol lock


def _revision(root: Path, given: str | None) -> str:
    """``protocol/<name>`` of the revision to lock: ``given`` checked, or the latest managed one."""
    if not given:
        latest = records.latest_revision(root)
        if latest is None:
            raise StudyError("PROTOCOL_ABSENT", f"no managed revision {records.PROTOCOL_DIR}/study-protocol-<slug>-vNN.md "
                                                "exists; `/study-protocol-deliberation` publishes one")
        return latest
    candidate = (root / given).resolve()
    folder = (root / records.PROTOCOL_DIR).resolve()
    if candidate.parent != folder or not records.REVISION_NAME.match(candidate.name):
        raise StudyError("REVISION_INVALID", f"{given} is not a {records.PROTOCOL_DIR}/study-protocol-<slug>-vNN.md "
                                             "revision of this workspace")
    if not candidate.is_file():
        raise StudyError("REVISION_ABSENT", f"{given} does not exist")
    if not candidate.read_bytes().startswith(records.MANAGED_MARKER):
        raise StudyError("REVISION_NOT_MANAGED", f"{given} carries no managed-artifact marker: only a revision the "
                                                 "deliberation engine published can be locked")
    return f"{records.PROTOCOL_DIR}/{candidate.name}"


def cmd_protocol(args, root: Path) -> dict:
    if args.action == "status":
        return {"ok": True, "protocol": records.protocol_state(root)}
    by = _operator(args)
    if args.action == "approve":
        if records.read_lock(root) is not None:
            raise StudyError("PROTOCOL_ALREADY_APPROVED", "the protocol is already approved; a later revision is "
                                                          "an amendment (`protocol amend`)")
        revision = _revision(root, args.revision)
        lock = {"schema": records.SCHEMA, "gate": records.GATE, "revision": revision,
                "sha256": records.sha256(root / revision), "approved_by": by, "approved_at": _now(),
                "amendments": []}
    else:  # amend
        reason = _text(args.reason or "", "--reason")
        if not reason:
            raise StudyError("AMENDMENT_REASON_MISSING", "--reason states why the protocol changed")
        lock = records.read_lock(root)
        if lock is None:
            raise StudyError("PROTOCOL_NOT_APPROVED", f"there is no approval to amend (gate {records.GATE}); "
                                                      "`protocol approve --by <name>` comes first")
        revision = _revision(root, args.revision)
        digest = records.sha256(root / revision)
        if digest == lock["sha256"]:
            raise StudyError("PROTOCOL_UNCHANGED", f"{revision} is the approved protocol, unchanged since its approval")
        if (records.revision_version(revision) or 0) < (records.revision_version(lock["revision"]) or 0):
            raise StudyError("REVISION_OLDER", f"{revision} is older than the locked {lock['revision']}; an amendment "
                                               "moves the lock forward")
        lock["amendments"].append({"by": by, "at": _now(), "reason": reason, "from_revision": lock["revision"],
                                   "from_sha256": lock["sha256"], "revision": revision, "sha256": digest})
        lock.update(revision=revision, sha256=digest)
    _write_json(root / records.LOCK_PATH, lock)
    return {"ok": True, "path": records.LOCK_PATH, "approval": lock, "protocol": records.protocol_state(root)}


# --------------------------------------------------------------------------- ethics and registration


def _entry(args, gate: str, fields: tuple, optional: tuple) -> dict:
    given = {key: getattr(args, key) for key, _ in fields + optional if getattr(args, key) is not None}
    if args.not_applicable:
        if given:
            raise StudyError("FIELDS_CONFLICT", "--not-applicable takes only --reason; drop "
                                                + ", ".join(flag for key, flag in fields + optional if key in given))
        reason = _text(args.reason or "", "--reason")
        if not reason:
            raise StudyError("REASON_MISSING", f"--reason states why no {gate} record applies to this study")
        return {"status": "not-applicable", "reason": reason}
    if args.reason is not None:
        raise StudyError("FIELDS_CONFLICT", "--reason goes with --not-applicable only")
    missing = [flag for key, flag in fields if not (given.get(key) or "").strip()]
    if missing:
        raise StudyError("FIELD_MISSING", f"the {gate} record needs {', '.join(missing)} "
                                          "(or --not-applicable --reason <text>)")
    entry = {}
    for key, flag in fields + optional:
        if key in given:
            entry[key] = _date(given[key], flag) if key in ("date", "first_enrolment") else _text(given[key], flag)
    return entry


def _record(root: Path, gate: str, by: str, entry: dict) -> dict:
    data = records.read_record(root, gate)
    lock = records.require_current_lock(root)
    entry.update(protocol_revision=lock["revision"], protocol_sha256=lock["sha256"])
    history = data["history"]
    if history and {k: v for k, v in history[-1].items() if k not in ENTRY_META} == entry:
        raise StudyError("RECORD_UNCHANGED", f"the {gate} record is already current: nothing changed since it was "
                                             "recorded")
    history.append({"by": by, "at": _now(), **entry})
    data["schema"] = records.SCHEMA
    _write_json(root / records.RECORD_PATHS[gate], data)
    return {"ok": True, "path": records.RECORD_PATHS[gate], gate: records.gate_state(root, gate)}


def cmd_ethics(args, root: Path) -> dict:
    by = _operator(args)
    entry = _entry(args, "ethics", ETHICS_FIELDS, ())
    if entry.get("status") != "not-applicable":
        entry = {"status": "approved", **entry}
    return _record(root, "ethics", by, entry)


def cmd_registration(args, root: Path) -> dict:
    by = _operator(args)
    entry = _entry(args, "registration", REGISTRATION_FIELDS, (("first_enrolment", "--first-enrolment"),))
    if entry.get("status") == "not-applicable":
        entry["retrospective"] = None
    else:
        first = entry.get("first_enrolment")
        # ICMJE: registered at or before the first participant's enrolment is prospective.
        entry = {"status": "registered", **entry, "first_enrolment": first,
                 "retrospective": None if first is None else entry["date"] > first}
    return _record(root, "registration", by, entry)


def cmd_status(args, root: Path) -> dict:
    return {"ok": True, **records.study_status(root)}


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(prog="study_cli.py", description="Study protocol lock, ethics and registration records.")
    sub = parser.add_subparsers(dest="verb", required=True)
    verbs = {"protocol": cmd_protocol, "ethics": cmd_ethics, "registration": cmd_registration, "status": cmd_status}
    for name in verbs:
        verb = sub.add_parser(name)
        verb.error = parser.error  # type: ignore[method-assign]
        verb.add_argument("--root", default=".")
    protocol = sub.choices["protocol"]
    protocol.add_argument("action", choices=("approve", "amend", "status"))
    protocol.add_argument("--by", default="")
    protocol.add_argument("--revision", default=None)
    protocol.add_argument("--reason", default="")
    for name, fields in (("ethics", ETHICS_FIELDS), ("registration", REGISTRATION_FIELDS
                                                    + (("first_enrolment", "--first-enrolment"),))):
        verb = sub.choices[name]
        verb.add_argument("action", choices=("record",))
        verb.add_argument("--by", default="")
        for key, flag in fields:
            verb.add_argument(flag, dest=key, default=None)
        verb.add_argument("--not-applicable", action="store_true")
        verb.add_argument("--reason", default=None)
    args = parser.parse_args(argv)
    try:
        result = verbs[args.verb](args, Path(args.root))
    except StudyError as error:
        return _out({"ok": False, "error": error.code, "message": error.message}, 1)
    except Exception as exc:  # a bug, reported typed so a caller can quote it
        return _out({"ok": False, "error": "INTERNAL_ERROR", "message": f"{type(exc).__name__}: {exc}"}, 1)
    return _out(result, 0 if result.get("ok") else 1)


if __name__ == "__main__":
    sys.exit(main())
