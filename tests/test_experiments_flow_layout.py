"""The Experiments tab in the order of the flow: the stepper and any launch
warning first, then the protocol, the datasets, the proof of concept, the full
experiments and their comparison, and the execution infrastructure grouped in
one collapsed block at the end. Every section folds and remembers it; each
product shows its discussion first and its detail on demand."""

from __future__ import annotations

import html
import json
import re
import unittest
from pathlib import Path

from skills._core.command_center import experiments_view
from tests import test_command_center_experiments as base
from tests.test_command_center_experiments import PAGE, Workspace, _discussion, _put_discussion


def key(*identity: str) -> str:
    return f'data-exp-disclosure="{html.escape(json.dumps(list(identity), separators=(",", ":")), quote=True)}"'


def details_with(out: str, *identity: str) -> str:
    """The opening tag of the details element carrying that disclosure key."""
    match = re.search(r"<details\b[^>]*" + re.escape(key(*identity)) + r"[^>]*>", out)
    assert match, f"no details for {identity}"
    return match.group(0)


class FlowOrderTests(unittest.TestCase):
    render = base.RenderTests.render

    def view(self) -> dict:
        ws = Workspace(self)
        _put_discussion(ws, "PocModel", _discussion())
        _put_discussion(ws, "FullModel", _discussion("full"))
        return experiments_view.get_experiments_view(ws.root)

    def test_sections_follow_the_flow_and_the_infrastructure_comes_last(self) -> None:
        out = self.render(self.view())
        order = ["exp-flow-steps", key("section", "protocol"), key("section", "datasets"),
                 key("section", "poc"), key("section", "full"), key("section", "comparison"),
                 key("section", "infrastructure"), 'id="expMcpActivation"', 'id="expColabActivation"',
                 'id="expLocalEnv"', 'id="expRunOptions"', 'id="expTeam"']
        positions = [out.index(marker) for marker in order]
        self.assertEqual(positions, sorted(positions))

    def test_the_stepper_names_the_next_action(self) -> None:
        out = self.render(self.view())
        steps = out[out.index("exp-flow-steps"):out.index(key("section", "protocol"))]
        self.assertRegex(steps, r'class="badge badge--info exp-next"[^>]*>Siguiente: ')

    def test_the_working_sections_open_and_the_rest_start_folded(self) -> None:
        out = self.render(self.view())
        for name in ("protocol", "poc"):
            self.assertRegex(details_with(out, "section", name), r"\bopen\b", name)
        for name in ("datasets", "full", "comparison", "infrastructure"):
            self.assertNotRegex(details_with(out, "section", name), r"\bopen\b", name)

    def test_a_product_shows_its_discussion_then_its_detail_on_demand(self) -> None:
        out = self.render(self.view())
        poc = out[out.index(key("section", "poc")):out.index(key("section", "full"))]
        detail = details_with(poc, "detail", "implementations/repo/PocModel")
        self.assertNotRegex(detail, r"\bopen\b")
        self.assertLess(poc.index("Resumen y discusión"), poc.index(detail))
        self.assertLess(poc.index(detail), poc.index("Convergencia"))


class TutorPlacementTests(unittest.TestCase):
    def test_the_tutor_closes_the_tab_folded(self) -> None:
        pane = PAGE[PAGE.index('id="pane-experiments"'):PAGE.index('id="pane-novelty"')]
        self.assertLess(pane.index('id="experimentsRoot"'), pane.index('id="xtutorFold"'))
        self.assertLess(pane.index('id="xtutorFold"'), pane.index('id="xtutorPanel"'))
        self.assertRegex(pane, r'<details id="xtutorFold" class="exp-fold"[^>]*>')
        self.assertNotRegex(re.search(r'<details id="xtutorFold"[^>]*>', pane).group(0), r"\bopen\b")


if __name__ == "__main__":
    unittest.main()
