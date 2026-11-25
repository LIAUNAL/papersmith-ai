#!/usr/bin/env python3
"""CLI for the reporting-guideline checklist engine (``engine.py`` in this folder).

    checklist_cli.py list
    checklist_cli.py show <id>
    checklist_cli.py check --guideline <id> --root <dir> [--json]

``list`` and ``show`` print one JSON object. ``check`` evaluates the workspace
at ``--root`` item by item (``satisfied`` | ``missing`` | ``needs-judgment``,
each with the evidence used) and prints a table, or one JSON object with
``--json``. A refusal prints ``{"ok": false, "error": <CODE>, "message": ...}``
and exits 2; codes: ``USAGE``, ``GUIDELINE_UNKNOWN``, ``GUIDELINE_INVALID``,
``NOT_A_WORKSPACE``. An unexpected failure is ``INTERNAL_ERROR`` (exit 1).
Stdlib only.
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

if __package__ in (None, ""):  # run as a script: make `skills._core.checklists` importable
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from skills._core.checklists import engine  # noqa: E402
else:
    from . import engine

_MARK = {"satisfied": "ok", "missing": "MISSING", "needs-judgment": "judge"}


class _Parser(argparse.ArgumentParser):
    def error(self, message: str):  # type: ignore[override]
        raise engine.ChecklistRefusal("USAGE", message)


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(description="Reporting-guideline checklists evaluated against a workspace.")
    sub = parser.add_subparsers(dest="verb", required=True, parser_class=_Parser)
    sub.add_parser("list", help="the guidelines this engine ships")
    show = sub.add_parser("show", help="one guideline's items (numbers, paraphrased topics, targets, rules)")
    show.add_argument("id")
    check = sub.add_parser("check", help="evaluate a workspace item by item")
    check.add_argument("--guideline", required=True)
    check.add_argument("--root", required=True, help="the workspace")
    check.add_argument("--json", action="store_true", help="print one JSON object instead of a table")
    return parser


def table(result: dict) -> str:
    guideline = result["guideline"]
    lines = [f"{guideline['name']} -- {guideline['url']}", f"paper line: {result['line']}", ""]
    for entry in result["items"]:
        lines.append(f"{entry['item']:>2}  {_MARK[entry['status']]:<7}  {entry['section']}: {entry['topic']}")
        for evidence in entry["evidence"]:
            if not evidence["ok"]:
                lines.append(f"              - {evidence['detail']}")
        if entry["status"] == "needs-judgment":
            lines.append(f"              ? {entry['question']}")
    summary = result["summary"]
    lines += ["", f"satisfied {len(summary['satisfied'])}, missing {len(summary['missing'])}, "
                  f"needs judgment {len(summary['needs-judgment'])}"]
    lines += [f"note: {note}" for note in result["notes"]]
    return "\n".join(lines) + "\n"


def run(argv: list[str] | None) -> tuple[int, str]:
    args = build_parser().parse_args(argv)
    if args.verb == "list":
        return 0, json.dumps({"ok": True, "guidelines": engine.list_guidelines()}, indent=2, ensure_ascii=False)
    if args.verb == "show":
        return 0, json.dumps({"ok": True, "guideline": engine.load_guideline(args.id)}, indent=2, ensure_ascii=False)
    result = engine.check(args.guideline, Path(args.root))
    if args.json:
        return 0, json.dumps(result, indent=2, ensure_ascii=False)
    return 0, table(result).rstrip("\n")


def main(argv: list[str] | None = None) -> int:
    try:
        code, text = run(argv)
    except engine.ChecklistRefusal as refusal:
        code, text = 2, json.dumps({"ok": False, "error": refusal.code, "message": refusal.message}, ensure_ascii=False)
    except Exception as exc:  # a bug, reported typed so a caller can quote it
        code, text = 1, json.dumps({"ok": False, "error": "INTERNAL_ERROR", "message": f"{type(exc).__name__}: {exc}"})
    sys.stdout.write(text + "\n")
    return code


if __name__ == "__main__":
    sys.exit(main())
