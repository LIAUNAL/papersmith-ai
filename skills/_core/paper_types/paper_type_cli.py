#!/usr/bin/env python3
"""CLI for the paper-type decision (``decision.py``, ``score.py`` in this folder).

    paper_type_cli.py accept --root . --by <operator> [--top5 <id> ...] [--idea-file <f>]
    paper_type_cli.py score  --root . [--idea-file <f>] [--dry-run]
    paper_type_cli.py show   --root .

``accept`` records the plausibility acceptance (the idea, read from
``--idea-file`` or stdin) in ``.papersmith/plausibility.json`` and scores it.
``score`` scores an idea from ``--idea-file``, stdin, or else the accepted one,
and writes ``.papersmith/paper_type.json`` (``--dry-run`` writes nothing).
Each verb prints one JSON object. A refusal prints ``{"ok": false, "error":
<CODE>, "message": ...}`` and exits 1 (usage errors exit 2). Refusal codes:
``USAGE``, ``IDEA_ABSENT``, ``OPERATOR_ABSENT``, ``RECORD_UNREADABLE``.
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
    from skills._core.paper_types import decision  # noqa: E402
else:
    from . import decision


def _out(payload: dict, code: int = 0) -> int:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return code


def _refuse(error: str, message: str, code: int = 1) -> int:
    return _out({"ok": False, "error": error, "message": message}, code)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise SystemExit(_refuse("USAGE", message, 2))


def _idea(args: argparse.Namespace) -> str:
    if args.idea_file:
        return Path(args.idea_file).read_text(encoding="utf-8")
    if not sys.stdin.isatty():
        text = sys.stdin.read()
        if text.strip():
            return text
    return ""


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(prog="paper_type_cli.py", description="Paper-type decision: accept, score, show.")
    sub = parser.add_subparsers(dest="verb", required=True)
    for name in ("accept", "score", "show"):
        verb = sub.add_parser(name)
        verb.error = parser.error  # type: ignore[method-assign]
        verb.add_argument("--root", default=".")
        if name != "show":
            verb.add_argument("--idea-file")
    sub.choices["accept"].add_argument("--by", default="")
    sub.choices["accept"].add_argument("--top5", nargs="*", default=[])
    sub.choices["score"].add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    root = Path(args.root)
    try:
        if args.verb == "show":
            return _out({"ok": True, **decision.read(root)})
        idea = _idea(args)
        if args.verb == "accept":
            if not str(args.by).strip():
                return _refuse("OPERATOR_ABSENT", "name the operator who accepted the report with --by")
            if not idea.strip():
                return _refuse("IDEA_ABSENT", "give the accepted idea on stdin or with --idea-file")
            accepted = decision.record_acceptance(root, idea, by=args.by, top5=args.top5)
            return _out({"ok": True, "plausibility": accepted, **decision.record_scores(root, idea)})
        if not idea.strip():
            accepted = decision.read(root)["plausibility"] or {}
            idea = str(accepted.get("idea") or "")
        if not idea.strip():
            return _refuse("IDEA_ABSENT", "no idea on stdin or --idea-file and no accepted plausibility")
        result = decision.compute(root, idea) if args.dry_run else decision.record_scores(root, idea)
        return _out({"ok": True, **result})
    except decision.DecisionError as error:
        return _refuse("RECORD_UNREADABLE", str(error))


if __name__ == "__main__":
    raise SystemExit(main())
