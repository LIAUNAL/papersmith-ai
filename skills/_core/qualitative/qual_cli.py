#!/usr/bin/env python3
"""Operator records of a qualitative study: transcripts, codebook, themes sign-off, quotes.

    qual_cli.py transcripts add --file <path> --participant <code> --consent <how consent was given> \
        --deidentified <how it was de-identified> --by <operator> \
        [--kind interview|focus-group|field-note|document] [--note <text>] [--replace] --root .
    qual_cli.py transcripts status --root .
    qual_cli.py codebook record --file <codebook path> --by <operator> [--note <text>] --root .
    qual_cli.py codebook status --root .
    qual_cli.py themes signoff --file <themes path> --by <operator> [--note <text>] --root .
    qual_cli.py themes status --root .
    qual_cli.py quotes check [--paper paper/] --root .
    qual_cli.py status --root .

``transcripts add`` registers a de-identified transcript or field note the
operator holds (gate G-TRANSCRIPTS) by its sha256 and character count in
``study/transcripts.json``, with its participant code, how consent was given and
how it was de-identified. One file may hold several participants (a focus
group): each code is registered once per file, and a changed file is registered
again with ``--replace``. ``codebook record`` binds a codebook version by its
sha256 in ``study/codebook.json``. ``themes signoff`` (gate G-ANALYSIS) records
in ``study/themes.json`` the operator's sign-off of the themes file, bound to the
current codebook version and to the sha256 of every registered transcript: a
change to any of them, or a new transcript, makes it stale. ``quotes check``
finds every ``\\pquote{<participant code>}{<text>}`` in the paper's ``.tex``
sources and checks that each occurs verbatim (whitespace and quote ligatures
normalised) in a registered, current transcript of that participant.

The assistant may propose codes and themes in files; only the operator records
or signs them off, with ``--by``. No verb writes or edits a transcript, and no
output carries a transcript's text: a failing quote is reported with its file,
line and the paper's own words.

Each verb prints one JSON object. A refusal prints ``{"ok": false, "error":
<CODE>, "message": ...}`` and exits 1 (usage errors exit 2). Refusal codes:
``USAGE``, ``APPROVER_MISSING``, ``TEXT_INVALID``, ``FIELD_MISSING``,
``PARTICIPANT_INVALID``, ``CONSENT_MISSING``, ``DEIDENTIFICATION_MISSING``,
``FILE_OUTSIDE``, ``FILE_MISSING``, ``FILE_UNREADABLE``, ``FILE_EMPTY``,
``TRANSCRIPT_NOT_TEXT``, ``TRANSCRIPT_DUPLICATE``, ``TRANSCRIPT_NOT_REGISTERED``,
``RECORD_UNCHANGED``, ``TRANSCRIPTS_CORRUPT``, ``TRANSCRIPTS_ABSENT``,
``TRANSCRIPTS_STALE``, ``CODEBOOK_CORRUPT``, ``CODEBOOK_NOT_RECORDED``,
``CODEBOOK_STALE``, ``THEMES_CORRUPT``, ``PAPER_OUTSIDE``, ``PAPER_MISSING``,
``QUOTE_NOT_FOUND``, ``INTERNAL_ERROR``.
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
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

if __package__ in (None, ""):  # run as a script: make `skills._core.qualitative` importable
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from skills._core.qualitative import records  # noqa: E402
else:
    from . import records

QualitativeError = records.QualitativeError
ENTRY_META = ("by", "at", "action")


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


def _text(value: str | None, flag: str) -> str:
    value = (value or "").strip()
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise QualitativeError("TEXT_INVALID", f"{flag} holds a control character")
    return value


def _operator(args) -> str:
    by = _text(args.by, "--by")
    if not by:
        raise QualitativeError("APPROVER_MISSING", "--by names the operator who acts; an agent never registers, "
                                                   "records or signs off on the operator's behalf")
    return by


def _note(args) -> str | None:
    return _text(args.note, "--note") or None


def _workspace_file(root: Path, given: str | None, what: str) -> tuple[str, bytes]:
    """(workspace-relative path, bytes) of an operator file. Confined before any stat: an
    absolute path outside the workspace, a traversal out or a link pointing out is refused."""
    given = (given or "").strip()
    if not given:
        raise QualitativeError("FIELD_MISSING", f"--file names the {what}")
    workspace = root.resolve()
    candidate = Path(given)
    try:
        resolved = (candidate if candidate.is_absolute() else workspace / candidate).resolve()
    except (OSError, ValueError, RuntimeError):
        resolved = None
    if resolved is None or not resolved.is_relative_to(workspace) or resolved == workspace:
        raise QualitativeError("FILE_OUTSIDE", f"{given} lies outside the workspace; keep the {what} inside it "
                                               "so the record can follow it")
    try:
        is_file = resolved.is_file()
    except OSError:
        is_file = False
    if not is_file:
        raise QualitativeError("FILE_MISSING", f"{given} is not a file of the workspace")
    try:
        data = resolved.read_bytes()
    except OSError as error:
        raise QualitativeError("FILE_UNREADABLE", f"{given} cannot be read ({error.strerror or error})") from None
    if not data.strip():
        raise QualitativeError("FILE_EMPTY", f"{given} is empty: record the {what} once it holds something")
    return resolved.relative_to(workspace).as_posix(), data


def _unchanged(history: list[dict], entry: dict) -> bool:
    return bool(history) and {k: v for k, v in history[-1].items() if k not in ENTRY_META} == entry


# --------------------------------------------------------------------------- transcripts


def cmd_transcripts(args, root: Path) -> dict:
    if args.action == "status":
        return {"ok": True, "transcripts": records.transcripts_state(root)}
    by = _operator(args)
    participant = _text(args.participant, "--participant")
    if not participant:
        raise QualitativeError("FIELD_MISSING", "--participant gives the participant's code")
    if not records.PARTICIPANT_CODE.match(participant):
        raise QualitativeError("PARTICIPANT_INVALID", "--participant is a code (letters, digits, '.', '_', '-', "
                                                      "at most 40), never a name")
    consent = _text(args.consent, "--consent")
    if not consent:
        raise QualitativeError("CONSENT_MISSING", "--consent states how the participant's consent was given")
    deidentified = _text(args.deidentified, "--deidentified")
    if not deidentified:
        raise QualitativeError("DEIDENTIFICATION_MISSING", "--deidentified states how the transcript was "
                                                           "de-identified")
    note = _note(args)
    data = records.read_transcripts(root)
    file, content = _workspace_file(root, args.file, "de-identified transcript")
    try:
        characters = len(content.decode("utf-8"))
    except UnicodeDecodeError:
        raise QualitativeError("TRANSCRIPT_NOT_TEXT", f"{file} is not UTF-8 text: register the de-identified "
                                                      "transcript as a text file") from None
    current = {(e["participant"], e["file"]): e for e in records.registered(data["history"])}
    known = current.get((participant, file))
    if known is not None and not args.replace:
        raise QualitativeError("TRANSCRIPT_DUPLICATE", f"{participant} is already registered for {file}; "
                                                       "a changed file is registered again with --replace")
    if known is None and args.replace:
        raise QualitativeError("TRANSCRIPT_NOT_REGISTERED", f"{participant} has no registration for {file} to "
                                                            "replace; drop --replace")
    entry = {"participant": participant, "file": file, "kind": args.kind, "sha256": hashlib.sha256(content).hexdigest(),
             "characters": characters, "consent": consent, "deidentified": deidentified, "note": note}
    if known is not None and {k: v for k, v in known.items() if k not in ENTRY_META} == entry:
        raise QualitativeError("RECORD_UNCHANGED", f"the registration of {file} for {participant} is already "
                                                   "current: nothing changed since it was registered")
    data["history"].append({"by": by, "at": _now(), "action": "replace" if known else "add", **entry})
    data["schema"] = records.SCHEMA
    _write_json(root / records.TRANSCRIPTS_PATH, data)
    state = records.transcripts_state(root)
    shown = next(t for t in state["transcripts"] if t["participant"] == participant and t["file"] == file)
    return {"ok": True, "path": records.TRANSCRIPTS_PATH, "registered": shown, "replaced": known is not None,
            "gate": {"id": state["gate"], "passed": state["passed"], "state": state["state"]},
            "counts": state["counts"]}


# --------------------------------------------------------------------------- codebook and themes


def cmd_codebook(args, root: Path) -> dict:
    if args.action == "status":
        return {"ok": True, "codebook": records.codebook_state(root)}
    by = _operator(args)
    note = _note(args)
    data = records.read_codebook(root)
    file, content = _workspace_file(root, args.file, "codebook")
    entry = {"file": file, "sha256": hashlib.sha256(content).hexdigest(), "note": note}
    if _unchanged(data["history"], entry):
        raise QualitativeError("RECORD_UNCHANGED", f"codebook {file} is already recorded as version "
                                                   f"{len(data['history'])}: nothing changed")
    data["history"].append({"by": by, "at": _now(), **entry})
    data["schema"] = records.SCHEMA
    _write_json(root / records.CODEBOOK_PATH, data)
    return {"ok": True, "path": records.CODEBOOK_PATH, "codebook": records.codebook_state(root)}


def cmd_themes(args, root: Path) -> dict:
    if args.action == "status":
        return {"ok": True, "themes": records.themes_state(root)}
    by = _operator(args)
    note = _note(args)
    data = records.read_themes(root)
    file, content = _workspace_file(root, args.file, "themes file")
    codebook = records.codebook_state(root)
    if codebook["state"] == "corrupt":
        raise QualitativeError("CODEBOOK_CORRUPT", codebook["message"])
    if codebook["state"] == "absent":
        raise QualitativeError("CODEBOOK_NOT_RECORDED", "no codebook version is recorded: the operator records "
                                                        "it with `codebook record --by` before signing off")
    if codebook["state"] != "current":
        raise QualitativeError("CODEBOOK_STALE", f"the codebook {codebook['file']} is {codebook['reasons'][0]} "
                                                 "since it was recorded; record its current version first")
    transcripts = records.transcripts_state(root)
    if transcripts["state"] == "corrupt":
        raise QualitativeError("TRANSCRIPTS_CORRUPT", transcripts["message"])
    if transcripts["state"] == "absent":
        raise QualitativeError("TRANSCRIPTS_ABSENT", "no transcript is registered: the themes rest on the "
                                                     "registered transcripts (`transcripts add --by`)")
    if transcripts["state"] != "current":
        stale = [f"{t['file']} ({t['participant']}: {t['reasons'][0]})" for t in transcripts["transcripts"]
                 if t["state"] != "current"]
        raise QualitativeError("TRANSCRIPTS_STALE", "registered transcripts changed since their registration: "
                                                    + ", ".join(stale) + "; register them again with --replace")
    entry = {"file": file, "sha256": hashlib.sha256(content).hexdigest(),
             "codebook": {"version": codebook["version"], "file": codebook["file"], "sha256": codebook["sha256"]},
             "transcripts": records.binding(transcripts["transcripts"]), "note": note}
    if _unchanged(data["history"], entry) and records.themes_state(root)["state"] == "current":
        raise QualitativeError("RECORD_UNCHANGED", f"the sign-off of {file} is already current: nothing changed")
    data["history"].append({"by": by, "at": _now(), **entry})
    data["schema"] = records.SCHEMA
    _write_json(root / records.THEMES_PATH, data)
    return {"ok": True, "path": records.THEMES_PATH, "themes": records.themes_state(root)}


# --------------------------------------------------------------------------- quotes


def cmd_quotes(args, root: Path) -> dict:
    workspace = root.resolve()
    given = (args.paper or "").strip() or "paper"
    try:
        paper = (Path(given) if Path(given).is_absolute() else workspace / given).resolve()
    except (OSError, ValueError, RuntimeError):
        paper = None
    if paper is None or not paper.is_relative_to(workspace):
        raise QualitativeError("PAPER_OUTSIDE", f"{given} lies outside the workspace")
    if not paper.is_dir():
        raise QualitativeError("PAPER_MISSING", f"{given} is not a directory of the workspace")
    result = records.check_quotes(root, paper)
    if "corrupt" in result:
        raise QualitativeError("TRANSCRIPTS_CORRUPT", result["corrupt"])
    if result["failures"]:
        return {"ok": False, "error": "QUOTE_NOT_FOUND",
                "message": f"{len(result['failures'])} of {result['quotes']} participant quote(s) are not found "
                           "verbatim in a registered, current transcript of their participant",
                **result}
    return {"ok": True, **result}


def cmd_status(args, root: Path) -> dict:
    return {"ok": True, **records.qualitative_status(root)}


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(prog="qual_cli.py",
                     description="Transcripts, codebook, themes sign-off and verbatim quotes of a qualitative study.")
    sub = parser.add_subparsers(dest="verb", required=True)
    verbs = {"transcripts": (cmd_transcripts, ("add", "status")), "codebook": (cmd_codebook, ("record", "status")),
             "themes": (cmd_themes, ("signoff", "status")), "quotes": (cmd_quotes, ("check",)),
             "status": (cmd_status, ())}
    actions = {}
    for name, (_, names) in verbs.items():
        verb = sub.add_parser(name)
        verb.error = parser.error  # type: ignore[method-assign]
        verb.add_argument("--root", default=".")
        if not names:
            continue
        # Each action is a subparser of its own, so `status` refuses a record option (a
        # usage error) instead of ignoring it.
        group = verb.add_subparsers(dest="action", required=True)
        for action_name in names:
            action = group.add_parser(action_name)
            action.error = parser.error  # type: ignore[method-assign]
            # `--root` is accepted before or after the action; SUPPRESS keeps an absent one
            # from overriding the value given before it.
            action.add_argument("--root", default=argparse.SUPPRESS)
            actions[(name, action_name)] = action
    add = actions[("transcripts", "add")]
    add.add_argument("--file", default=None)
    add.add_argument("--participant", default=None)
    add.add_argument("--consent", default=None)
    add.add_argument("--deidentified", default=None)
    add.add_argument("--kind", choices=records.KINDS, default="interview")
    add.add_argument("--replace", action="store_true")
    for key in (("transcripts", "add"), ("codebook", "record"), ("themes", "signoff")):
        actions[key].add_argument("--by", default="")
        actions[key].add_argument("--note", default=None)
    for key in (("codebook", "record"), ("themes", "signoff")):
        actions[key].add_argument("--file", default=None)
    actions[("quotes", "check")].add_argument("--paper", default="paper")
    args = parser.parse_args(argv)
    try:
        result = verbs[args.verb][0](args, Path(args.root))
    except QualitativeError as error:
        return _out({"ok": False, "error": error.code, "message": error.message}, 1)
    except Exception as exc:  # a bug, reported typed so a caller can quote it
        return _out({"ok": False, "error": "INTERNAL_ERROR", "message": f"{type(exc).__name__}: {exc}"}, 1)
    return _out(result, 0 if result.get("ok") else 1)


if __name__ == "__main__":
    sys.exit(main())
