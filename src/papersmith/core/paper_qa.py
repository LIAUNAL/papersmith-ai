"""``smith paper qa [--json] [<dir>]``: the visual QA of the compiled manuscript.

The pass lives in the workspace's kit copy
(``skills/_core/figure/manuscript_qa.py``): it measures ``paper/main.pdf`` with
pypdfium2, renders the pages with ``pdftoppm`` and writes
``paper/.qa/qa.json``. pypdfium2 is a workspace dependency, not a CLI one, so
the module runs under the workspace's provisioned interpreter (the same one
``smith ui`` runs the dashboard with). The dashboard runs the same pass after
every successful compile.

``audit_line`` is the read-only summary ``smith audit`` prints: the stored
report's finding count and whether ``main.pdf`` changed since (stdlib only,
nothing is measured or written).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from ..bridges.python import script_environment
from ..errors import UserError
from . import fs
from .ui import workspace_interpreter

#: The workspace module that performs the pass.
MANUSCRIPT_QA_ENTRY = Path("skills") / "_core" / "figure" / "manuscript_qa.py"
QA_JSON = Path("paper") / ".qa" / "qa.json"
PDF = Path("paper") / "main.pdf"


def run_qa(args) -> int:
    workspace = Path(args.directory).expanduser().resolve()
    if not fs.is_dir(workspace):
        raise UserError(f"not a directory: {workspace}")
    entry = workspace / MANUSCRIPT_QA_ENTRY
    if not fs.is_regular_file(entry):
        raise UserError(f"{MANUSCRIPT_QA_ENTRY} not found in {workspace}: "
                        "run `smith upgrade` to refresh the workspace kit")
    argv = [workspace_interpreter(workspace), "-B", str(entry), "--root", str(workspace)]
    if args.json:
        argv.append("--json")
    completed = subprocess.run(argv, cwd=str(workspace), capture_output=True, text=True,
                               check=False, env=script_environment())
    print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="", file=sys.stderr)
    return 0 if completed.returncode == 0 else 1


def audit_line(workspace: Path) -> str | None:
    """One line for ``smith audit``, or ``None`` when there is no compiled
    manuscript (the audit output is then unchanged)."""
    root = Path(workspace).expanduser().resolve()
    pdf = root / PDF
    if not fs.is_regular_file(pdf):
        return None
    path = root / QA_JSON
    if not fs.is_regular_file(path):
        return "manuscript qa: not run: run smith paper qa"
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
        summary = report["summary"]
        count = int(summary["findings"])
        kinds = ", ".join(f"{kind} {n}" for kind, n in sorted((summary.get("by_kind") or {}).items()))
        stale = hashlib.sha256(pdf.read_bytes()).hexdigest() != report.get("pdf_sha256")
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return "manuscript qa: report unreadable: run smith paper qa"
    head = f"manuscript qa: {count} finding(s)" + (f" ({kinds})" if kinds and count else "")
    return head + (", stale (main.pdf changed): run smith paper qa" if stale else ", current")


def register(subparsers) -> None:
    parser = subparsers.add_parser(
        "paper",
        help="manuscript checks on the compiled paper",
        description="Checks on the compiled manuscript (paper/main.pdf).",
    )
    actions = parser.add_subparsers(dest="paper_action", metavar="<action>")
    actions.required = True
    qa = actions.add_parser(
        "qa",
        help="visual QA of paper/main.pdf: overflow past the text block, small figure "
             "and table text, Overfull boxes",
        description=("Measure paper/main.pdf (pypdfium2) against the text block inferred from "
                     "its body lines and the 0.70 x body font floor, read the Overfull boxes of "
                     "paper/main.log, render the pages with pdftoppm, and write "
                     "paper/.qa/qa.json and paper/.qa/pages/. Reports; never repairs. Exit 0 "
                     "when the report was written (findings or not), 1 otherwise."),
    )
    qa.add_argument("--json", action="store_true", help="print the full report as JSON")
    qa.add_argument("directory", nargs="?", default=".", metavar="<dir>")
    qa.set_defaults(handler=run_qa)


__all__ = ["register", "run_qa", "audit_line", "MANUSCRIPT_QA_ENTRY"]
