"""The paper-construction flow is stated once and reaches every harness: the
generated entrypoints of a new workspace, this repository's own entrypoints,
and the dashboard's phase actions all name the same stages."""

from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

from papersmith.generators import ALL_TOOLS, render_files
from papersmith.render import package_template_path
from skills._core.command_center import phase_actions

REPO = Path(__file__).resolve().parents[1]
FLOW = package_template_path("paper-flow.md.tpl").read_text(encoding="utf-8").strip()
ENTRYPOINTS = ("CLAUDE.md", "OPENCODE.md", ".pi/APPEND_SYSTEM.md", ".agents/AGENTS.md")


class PaperFlowRulesTests(unittest.TestCase):
    def test_a_new_workspace_states_the_flow_in_every_harness(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rendered = render_files(Path(tmp), {"name": "fresh-paper"}, tools=ALL_TOOLS)
        for path in ENTRYPOINTS:
            with self.subTest(path=path):
                self.assertIn(FLOW, rendered[path])

    def test_this_repository_states_the_same_flow(self) -> None:
        for path in ENTRYPOINTS:
            with self.subTest(path=path):
                self.assertIn(FLOW, (REPO / path).read_text(encoding="utf-8"))

    def test_the_flow_has_the_dashboards_phases_and_their_commands(self) -> None:
        numbered = re.findall(r"^\s*(\d+)\. \*\*", FLOW, re.M)
        self.assertEqual(numbered, [str(i) for i in range(1, len(phase_actions.STAGES) + 1)])
        for stage, entry in phase_actions.ACTIONS.items():
            for action in entry["actions"]:
                if action["kind"] == "prompt":
                    with self.subTest(stage=stage, slash=action["slash"]):
                        self.assertIn(f"`{action['slash']}", FLOW)
        self.assertIn("/math-tutor", FLOW)
        phase5 = FLOW[FLOW.index("5. **"):FLOW.index("6. **")]
        for needle in ("`/datasets", "toy", "paper-replicator", "published code"):
            with self.subTest(needle=needle):
                self.assertIn(needle, phase5)
        self.assertIn("Mapa Conceptual", FLOW)

    def test_the_writing_phase_names_where_references_come_from(self) -> None:
        writing = FLOW[FLOW.index("8. **"):FLOW.index("9. **")]
        for needle in ("`bib build`", "`resolve --references`", "references.json"):
            with self.subTest(needle=needle):
                self.assertIn(needle, writing)


if __name__ == "__main__":
    unittest.main()
