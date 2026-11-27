#!/usr/bin/env python3
"""CLI for the paper-type decision (``decision.py``, ``score.py`` in this folder).

    paper_type_cli.py accept --root . --by <operator> [--idea-file <f|->] [--top5 <id> ...]
    paper_type_cli.py score  --root . [--idea-file <f|->] [--dry-run]
    paper_type_cli.py agree  --root . --type <id> [--variant <id>] --by <operator> [--rationale <text>]
    paper_type_cli.py show   --root .

``accept`` records the plausibility acceptance (the idea read from
``--idea-file``, ``-`` reads stdin; without it, the approved English idea brief
draft, ``.papersmith/idea_brief.json`` ``draft.text``) in
``.papersmith/plausibility.json`` and scores it; it reads the existing records
and scores first, so a failure writes nothing. The record is English like every
artifact under ``.papersmith/``: an idea, or a ``--by``, that reads as Spanish
prose is refused (``--by`` takes the operator's name or role, never a quote). ``agree`` records the type (and variant) the operator agreed
for the scored idea and answers ``layout``: ``current``, ``switch:<line>``
(``smith kind set`` moves the workspace) or ``planned`` (no flow yet). ``score`` scores the
idea from ``--idea-file`` or, without it, the accepted one, and writes
``.papersmith/paper_type.json`` (``--dry-run`` writes nothing). stdin is read
only when asked with ``-``. Each verb prints one JSON object. A refusal prints
``{"ok": false, "error": <CODE>, "message": ...}`` and exits 1 (usage errors
exit 2). Refusal codes: ``USAGE``, ``IDEA_ABSENT``, ``IDEA_UNREADABLE``,
``IDEA_NOT_ENGLISH``, ``OPERATOR_ABSENT``, ``OPERATOR_NOT_ENGLISH``,
``BRIEF_UNREADABLE``, ``RECORD_UNREADABLE``, ``SCORES_ABSENT``, ``SCORES_STALE``,
``TYPE_UNKNOWN``, ``VARIANT_UNKNOWN``.
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
import sys
from pathlib import Path

if __package__ in (None, ""):  # run as a script: make `skills._core.paper_types` importable
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from skills._core.command_center import model_spec  # noqa: E402
    from skills._core.paper_types import decision  # noqa: E402
else:
    from ..command_center import model_spec
    from . import decision

DRAFT = ".papersmith/idea_brief.json draft.text"


def _out(payload: dict, code: int = 0) -> int:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return code


def _refuse(error: str, message: str, code: int = 1) -> int:
    return _out({"ok": False, "error": error, "message": message}, code)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise SystemExit(_refuse("USAGE", message, 2))


def _idea(args: argparse.Namespace) -> str:
    """The idea from ``--idea-file`` (``-`` is stdin), or ``""`` without one."""
    if not args.idea_file:
        return ""
    if args.idea_file == "-":
        return sys.stdin.read()
    return Path(args.idea_file).read_text(encoding="utf-8")


def _not_english(root: Path, *, from_draft: bool) -> str:
    """The refusal of a Spanish idea, naming the English draft to accept instead."""
    head = "the accepted idea reads as Spanish prose; .papersmith/plausibility.json is English: "
    if from_draft:
        return head + f"rewrite the idea brief draft ({DRAFT}) in English and approve it again (`smith idea approve`)"
    if decision.approved_draft(root):
        return head + f"accept the approved English idea brief draft ({DRAFT}) by running accept without --idea-file"
    return head + (f"pass the idea in English, or approve the English idea brief draft ({DRAFT}, "
                   "`smith idea approve`) and run accept without --idea-file")


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(prog="paper_type_cli.py", description="Paper-type decision: accept, score, agree, show.")
    sub = parser.add_subparsers(dest="verb", required=True)
    for name in ("accept", "score", "agree", "show"):
        verb = sub.add_parser(name)
        verb.error = parser.error  # type: ignore[method-assign]
        verb.add_argument("--root", default=".")
        if name == "accept":
            verb.add_argument("--idea-file", help="the accepted English idea (- reads stdin); without it, "
                                                  f"the approved English idea brief draft ({DRAFT})")
        elif name == "score":
            verb.add_argument("--idea-file")
    sub.choices["accept"].add_argument("--by", default="",
                                       help="the operator's name or role, never a quote of their words")
    sub.choices["agree"].add_argument("--type", required=True)
    sub.choices["agree"].add_argument("--variant")
    sub.choices["agree"].add_argument("--by", default="")
    sub.choices["agree"].add_argument("--rationale", default="")
    sub.choices["accept"].add_argument("--top5", nargs="*", default=[])
    sub.choices["score"].add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    root = Path(args.root)
    try:
        if args.verb == "show":
            return _out({"ok": True, **decision.read(root)})
        if args.verb == "agree":
            return _out({"ok": True, **decision.agree(root, args.type, by=args.by, variant=args.variant,
                                                       rationale=args.rationale)})
        try:
            idea = _idea(args)
        except (OSError, UnicodeDecodeError) as error:
            return _refuse("IDEA_UNREADABLE", f"--idea-file cannot be read: {error}")
        if args.verb == "accept":
            if not str(args.by).strip():
                return _refuse("OPERATOR_ABSENT", "name the operator who accepted the report with --by")
            draft = None if args.idea_file else decision.approved_draft(root)
            idea = idea if args.idea_file else (draft or "")
            if not idea.strip():
                return _refuse("IDEA_ABSENT", "give the accepted idea with --idea-file <file> or --idea-file -, "
                                              f"or approve the English idea brief draft ({DRAFT}, "
                                              "`smith idea approve`) and run accept without --idea-file")
            if model_spec.reads_spanish(args.by):
                return _refuse("OPERATOR_NOT_ENGLISH", "--by reads as Spanish prose; .papersmith/plausibility.json "
                                                       "is English: give the operator's name or role (for example "
                                                       "--by operator), never a quote of the operator's words")
            if model_spec.reads_spanish(idea):
                return _refuse("IDEA_NOT_ENGLISH", _not_english(root, from_draft=not args.idea_file))
            decision.read(root)  # a foreign record refuses here, before anything is written
            decision.compute(root, idea)  # score first: a failure leaves nothing half written
            accepted = decision.record_acceptance(root, idea, by=args.by, top5=args.top5)
            return _out({"ok": True, "plausibility": accepted, **decision.record_scores(root, idea)})
        if not idea.strip():
            accepted = decision.read(root)["plausibility"] or {}
            idea = str(accepted.get("idea") or "")
        if not idea.strip():
            return _refuse("IDEA_ABSENT", "no idea in --idea-file and no accepted plausibility")
        result = decision.compute(root, idea) if args.dry_run else decision.record_scores(root, idea)
        return _out({"ok": True, **result})
    except decision.DecisionError as error:
        return _refuse(error.code, str(error))


if __name__ == "__main__":
    raise SystemExit(main())
