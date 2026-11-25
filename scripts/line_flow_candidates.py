#!/usr/bin/env python3
"""Dump the empirical lines' board tables for their Archify flow diagrams.

Each empirical line (``empirical_board.LINE_TABLES``) gets its own flow page,
``docs/diagrams/papersmith-<kind>-flow.html``, which the dashboard serves from
``skills/_core/command_center/static/`` in the *Flujo Archify* tab of a
workspace of that line. The pages are generated, never hand-drawn: this script
writes every table -- its steps in order (label, title, tools, outputs, skills,
who acts), the gates it lists (name, criteria, the step it is listed under,
whether it is listed only for some workspaces), the gate each step waits for
and the steps that wait for nothing -- to one JSON file, and
``docs/diagrams/papersmith-line-flow.build.mjs`` turns that file into one
Archify candidate per line. A changed table is a changed drawing, and
``tests/test_line_flow_diagrams.py`` fails until the pages are regenerated.

Every step and gate carries the line range of its definition in
``empirical_board.py`` at ``--revision`` (default: ``HEAD``), found with
``ast`` in that revision's text, because Archify's strict provenance gate
checks the ranges at the revision the candidate pins. The script refuses when
a cited range reads differently in the working tree: commit first, so the
drawing and the code it cites are the same bytes.

    python scripts/line_flow_candidates.py "$SCRATCH/lines.json"

Run it from the repository root with the repository on ``PYTHONPATH`` (and
``src/`` for ``papersmith``), as the tests run. It ships nowhere.
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
import tempfile
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BOARD = "skills/_core/command_center/empirical_board.py"


def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(REPO), *args], check=True, capture_output=True, text=True).stdout


def definitions(text: str, module) -> tuple[dict[str, tuple[int, int]], dict[int, tuple[int, int]]]:
    """``step id -> (line, end_line)`` and ``id(Gate object) -> (line, end_line)``
    for the ``Step(...)`` and ``Gate(...)`` calls of ``text``."""
    tree = ast.parse(text)
    steps: dict[str, tuple[int, int]] = {}
    gates: dict[int, tuple[int, int]] = {}
    assigned: set[int] = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)
                and getattr(node.value.func, "id", None) == "Gate" and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)):
            gate = getattr(module, node.targets[0].id)
            gates[id(gate)] = (node.lineno, node.end_lineno)
            assigned.add(id(node.value))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        name = getattr(node.func, "id", None)
        first = node.args[0]
        if name == "Step" and isinstance(first, ast.Constant):
            steps[first.value] = (node.lineno, node.end_lineno)
        elif name == "Gate" and id(node) not in assigned and isinstance(first, ast.Name):
            gate = module.GATES[getattr(module, first.id)]
            gates[id(gate)] = (node.lineno, node.end_lineno)
    return steps, gates


def _source(span: tuple[int, int]) -> dict[str, object]:
    return {"path": BOARD, "line": span[0], "end_line": span[1]}


def dump(revision: str) -> dict:
    from papersmith.core import manifest
    from skills._core.command_center import empirical_board as eb

    sha = _git("rev-parse", f"{revision}^{{commit}}").strip()
    text = _git("show", f"{sha}:{BOARD}")
    steps_at, gates_at = definitions(text, eb)
    here = (REPO / BOARD).read_text(encoding="utf-8").splitlines()
    there = text.splitlines()

    def checked(span: tuple[int, int], what: str) -> dict[str, object]:
        if here[span[0] - 1:span[1]] != there[span[0] - 1:span[1]]:
            raise SystemExit(f"{what}: {BOARD}:{span[0]}-{span[1]} differs from revision {sha[:7]}; "
                             "commit the change (or pass --revision) and run again")
        return _source(span)

    holder = tempfile.TemporaryDirectory(prefix="line-flow-")
    empty = types.SimpleNamespace(root=Path(holder.name))  # a workspace with no agreement: the default variant
    lines = {}
    for kind, table in eb.LINE_TABLES.items():
        steps = []
        for stage in table.steps:
            step = eb.STEPS[stage]
            steps.append({
                "id": step.id, "label": step.label, "title": step.title, "tools": list(step.tools),
                "outputs": list(step.outputs), "skills": list(step.actions.get("skills") or []),
                "agent": step.actions.get("agent") or "", "source": checked(steps_at[step.id], f"step {step.id}"),
            })
        gates = []
        for gate_id in table.gates:
            gate = eb.gate_definition(table, gate_id)
            listed_always = table.lists_gate is None or table.lists_gate(empty, gate_id)
            gates.append({
                "id": gate_id, "name": gate.name, "criteria": gate.criteria,
                "step": table.gate_steps.get(gate_id, gate.step),
                "with_people_only": gate_id in table.conditional_gates,
                "per_variant": not listed_always,
                "source": checked(gates_at[id(gate)], f"gate {gate_id} of {kind}"),
            })
        line = manifest.LINES[kind]
        lines[kind] = {
            "kind": kind, "label": line.label, "summary": line.summary, "steps": steps, "gates": gates,
            "phase_gates": dict(table.phase_gates), "ungated": sorted(table.ungated),
            "transversal": table.transversal, "extra_checklists": list(table.extra_checklists),
            "flow_html": table.flow_html,
        }
    holder.cleanup()
    return {"schema": 1, "revision": sha, "source": BOARD, "lines": lines}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("out", help="the JSON file to write")
    parser.add_argument("--revision", default="HEAD", help="the commit the ranges are taken at (default HEAD)")
    args = parser.parse_args(argv)
    data = dump(args.revision)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    print(f"lines: {out} ({', '.join(data['lines'])}) at {data['revision'][:7]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
