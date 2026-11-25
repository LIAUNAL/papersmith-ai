"""Each empirical line has its own Archify flow page, generated from its board.

`scripts/line_flow_candidates.py` dumps every `empirical_board.LINE_TABLES`
entry and `docs/diagrams/papersmith-line-flow.build.mjs` lays each one out, one
lane per board step, with the gates the table lists. The page ships twice,
`docs/diagrams/papersmith-<kind>-flow.html` and the dashboard's
`static/papersmith-<kind>-flow.html`, and `/api/flow` serves the second to a
workspace of that line. These tests read what the rendered page carries (its
lane labels, its nodes in order and the definition each one cites) against the
live table, so a changed table without a regenerated page fails here."""

from __future__ import annotations

import html
import json
import re
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from papersmith.core import init as init_module
from skills._core.command_center import empirical_board, lines, server

REPO = Path(__file__).resolve().parents[1]
DOCS = REPO / "docs" / "diagrams"
STATIC = Path(server.__file__).resolve().parent / "static"
BOARD = Path(empirical_board.__file__).resolve()
KINDS = ("observational-measurement", "hardware", "lab-simulation", "data-resource", "experiment-intervention",
         "qualitative-participatory")


def page(kind: str) -> str:
    return (DOCS / f"papersmith-{kind}-flow.html").read_text(encoding="utf-8")


def evidence(kind: str) -> dict:
    match = re.search(r'<script id="archify-source-evidence-data" type="application/json">(.*?)</script>',
                      page(kind), re.S)
    return json.loads(match.group(1))


class LinePagesTests(unittest.TestCase):
    def test_every_empirical_line_is_drawn(self) -> None:
        self.assertEqual(set(empirical_board.LINE_TABLES), set(KINDS))

    def test_each_line_names_its_own_page(self) -> None:
        for kind in KINDS:
            with self.subTest(kind=kind):
                self.assertEqual(empirical_board.LINE_TABLES[kind].flow_html, f"papersmith-{kind}-flow.html")
                self.assertEqual(lines.board(kind).flow_html, f"papersmith-{kind}-flow.html")

    def test_the_page_ships_with_the_dashboard_and_matches_the_docs(self) -> None:
        for kind in KINDS:
            with self.subTest(kind=kind):
                self.assertEqual((STATIC / f"papersmith-{kind}-flow.html").read_bytes(),
                                 (DOCS / f"papersmith-{kind}-flow.html").read_bytes())

    def test_the_lanes_are_the_board_steps_in_order(self) -> None:
        for kind in KINDS:
            table = empirical_board.LINE_TABLES[kind]
            text = html.unescape(page(kind))
            nodes = list(evidence(kind)["nodes"])
            with self.subTest(kind=kind):
                firsts = [m.group(1) for node in nodes if (m := re.fullmatch(r"act-(.+)-0", node))]
                self.assertEqual(firsts, list(table.steps))
                for number, stage in enumerate(table.steps, 1):
                    self.assertIn(f"{number} · {empirical_board.STEPS[stage].label}", text)
                self.assertNotIn(f"{len(table.steps) + 1} · ", text)

    def test_each_step_draws_its_skills_and_records(self) -> None:
        for kind in KINDS:
            table = empirical_board.LINE_TABLES[kind]
            nodes = list(evidence(kind)["nodes"])
            for stage in table.steps:
                step = empirical_board.STEPS[stage]
                with self.subTest(kind=kind, step=stage):
                    actors = [node for node in nodes if node.startswith(f"act-{stage}-")]
                    self.assertEqual(len(actors), len(step.actions.get("skills") or []) or 1)
                    records = [node for node in nodes if node.startswith(f"rec-{stage}-")]
                    self.assertEqual(len(records), len(step.outputs))

    def test_the_gates_are_the_table_s_gates(self) -> None:
        for kind in KINDS:
            table = empirical_board.LINE_TABLES[kind]
            text = html.unescape(page(kind))
            with self.subTest(kind=kind):
                drawn = [node[len("gate-"):] for node in evidence(kind)["nodes"] if node.startswith("gate-")]
                self.assertEqual(sorted(drawn), sorted(table.gates))
                for gate_id in table.gates:
                    self.assertIn(empirical_board.gate_definition(table, gate_id).name, text)
                for stage, gate_id in table.phase_gates.items():
                    self.assertIn(f"waits for {gate_id}", text, stage)

    def test_the_sources_cite_the_step_and_gate_definitions(self) -> None:
        source = BOARD.read_text(encoding="utf-8").splitlines()
        for kind in KINDS:
            table = empirical_board.LINE_TABLES[kind]
            for node, refs in evidence(kind)["nodes"].items():
                with self.subTest(kind=kind, node=node):
                    (ref,) = refs
                    self.assertEqual(ref["path"], "skills/_core/command_center/empirical_board.py")
                    cited = "\n".join(source[ref["line"] - 1:ref["endLine"]])
                    if node.startswith("gate-"):
                        gate = empirical_board.gate_definition(table, node[len("gate-"):])
                        self.assertIn("Gate(", cited)
                        self.assertIn(f'"{gate.name}"', cited)
                    else:
                        stage = re.fullmatch(r"(?:act|rec)-(.+)-\d+", node).group(1)
                        self.assertTrue(source[ref["line"] - 1].lstrip().startswith(f'Step("{stage}",'), node)


class ApiFlowServesTheLinePageTests(unittest.TestCase):
    def test_a_workspace_of_each_line_gets_its_own_page(self) -> None:
        for kind in KINDS:
            with self.subTest(kind=kind):
                holder = tempfile.TemporaryDirectory(prefix=f"line-flow-{kind}-", ignore_cleanup_errors=True)
                self.addCleanup(holder.cleanup)
                root = Path(holder.name) / "ws"
                init_module.initialize(root, tools=("claude",), run_npm=False, run_env=False, kind=kind)
                response = TestClient(server.create_app(root)).get("/api/flow")
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.headers["content-type"].startswith("text/html"))
                self.assertEqual(response.text,
                                 (STATIC / f"papersmith-{kind}-flow.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
