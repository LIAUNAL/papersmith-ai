"""Phase 4 forces its steps in order: the problem and its pillars, then the
hypotheses, then the mathematics. Each step reads its own evidence on disk,
each is locked until the one before it passed, the phase passes only with all
three, and the Concept Map tab offers a "Generate & deliberate" button per
step that types the step's slash command into the agent terminal."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from skills._core.command_center import phase_steps, server

STATIC = Path(server.__file__).resolve().parent / "static"
EN_JS, ES_JS, I18N_JS = STATIC / "i18n" / "en.js", STATIC / "i18n" / "es.js", STATIC / "i18n.js"
MARKER = "<!-- proposal-workspace:artifact:v1 -->\n"
EQUATION = "$$\nL = \\sum_i \\ell_i\n\\tag{1}\n$$\n"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class _Workspace(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.root = Path(holder.name).resolve() / "ws"
        self.root.mkdir()

    def spec(self, **novelty) -> None:
        _write(self.root / ".papersmith" / "model_spec.json", json.dumps({"novelty": novelty}))

    def revision(self, body: str = "# Proposal\n", n: int = 1, sky: dict | None = None) -> None:
        name = f"research-concept-eeg-r{n:02d}"
        _write(self.root / "proposals" / f"{name}.md", MARKER + body)
        if sky is not None:
            _write(self.root / "proposals" / f"{name}.sky.json", json.dumps(sky))

    def steps(self) -> dict:
        return {s["id"]: s for s in phase_steps.proposal_steps(self.root)}

    def status(self) -> dict:
        return TestClient(server.create_app(self.root, history_store=None)).get("/api/status").json()

    def fase4(self) -> dict:
        return next(f for f in self.status()["fases"] if f["stage_id"] == "proposal")


class StepDerivationTests(_Workspace):
    def test_an_empty_workspace_opens_the_first_step_and_locks_the_rest(self) -> None:
        steps = phase_steps.proposal_steps(self.root)
        self.assertEqual([s["id"] for s in steps], ["problem_pillars", "hypotheses", "mathematics"])
        self.assertEqual([s["status"] for s in steps], ["ACTIVE", "LOCKED", "LOCKED"])
        self.assertEqual([s["requires"] for s in steps], [None, "problem_pillars", "hypotheses"])

    def test_the_placeholder_specification_is_not_evidence(self) -> None:
        _write(self.root / "papersmith.yaml", "title: A paper\ntopic: eeg\n")
        self.assertEqual(self.steps()["problem_pillars"]["status"], "ACTIVE")

    def test_a_problem_without_pillars_does_not_pass(self) -> None:
        self.spec(problem_statement="The gap.", pillars=[])
        steps = self.steps()
        self.assertEqual(steps["problem_pillars"]["status"], "ACTIVE")
        self.assertTrue(steps["problem_pillars"]["started"])
        self.assertEqual(steps["hypotheses"]["status"], "LOCKED")

    def test_each_step_unlocks_the_next_in_order(self) -> None:
        self.spec(problem_statement="The gap.", pillars=[{"name": "P1"}])
        self.assertEqual([s["status"] for s in phase_steps.proposal_steps(self.root)],
                         ["PASS", "ACTIVE", "LOCKED"])
        self.spec(problem_statement="The gap.", pillars=[{"name": "P1"}], hypotheses=[{"statement": "H1"}])
        self.assertEqual([s["status"] for s in phase_steps.proposal_steps(self.root)],
                         ["PASS", "PASS", "ACTIVE"])
        self.revision("# Proposal\n" + EQUATION)
        self.assertEqual([s["status"] for s in phase_steps.proposal_steps(self.root)],
                         ["PASS", "PASS", "PASS"])

    def test_hypotheses_without_the_problem_stay_locked(self) -> None:
        self.spec(hypotheses=[{"statement": "H1"}])
        self.revision(EQUATION)
        steps = self.steps()
        self.assertEqual(steps["hypotheses"]["status"], "LOCKED")
        self.assertTrue(steps["hypotheses"]["done"])
        self.assertEqual(steps["mathematics"]["status"], "LOCKED")

    def test_an_untagged_equation_is_not_the_mathematics(self) -> None:
        self.spec(problem_statement="The gap.", pillars=[{"name": "P1"}], hypotheses=[{"statement": "H1"}])
        self.revision("$$\nx = y\n$$\n")
        self.assertEqual(self.steps()["mathematics"]["status"], "ACTIVE")

    def test_the_latest_revision_sky_overlay_is_evidence(self) -> None:
        sky = {"system": {"planets": [{"slot": "problem", "label": "The gap"}]},
               "pillars": [{"id": "P1", "label": "Pillar"}],
               "hypotheses": [{"id": "H1", "statement": "It improves", "pillar": "P1"}]}
        self.revision("# Proposal\n" + EQUATION, sky=sky)
        steps = self.steps()
        self.assertEqual([steps[i]["status"] for i in phase_steps.STEP_IDS], ["PASS", "PASS", "PASS"])
        self.assertEqual(steps["hypotheses"]["evidence"]["source"], "proposals/research-concept-eeg-r01.sky.json")
        self.assertEqual(steps["mathematics"]["evidence"]["equations"], 1)

    def test_the_api_route_answers_the_steps(self) -> None:
        client = TestClient(server.create_app(self.root, history_store=None))
        body = client.get("/api/model/steps").json()
        self.assertEqual([s["status"] for s in body["steps"]], ["ACTIVE", "LOCKED", "LOCKED"])


class Phase4StatusTests(_Workspace):
    def test_a_revision_alone_no_longer_passes_the_phase(self) -> None:
        self.revision()
        fase = self.fase4()
        self.assertEqual(fase["status"], "ACTIVE")
        self.assertIn("0 of 3", fase["detail"])

    def test_the_phase_passes_with_the_revision_and_every_step(self) -> None:
        self.spec(problem_statement="The gap.", pillars=[{"name": "P1"}], hypotheses=[{"statement": "H1"}])
        self.revision("# Proposal\n" + EQUATION)
        fase = self.fase4()
        self.assertEqual((fase["status"], fase["progress"]), ("PASS", 1.0))
        self.assertEqual([s["status"] for s in fase["steps"]], ["PASS", "PASS", "PASS"])

    def test_phase_five_stays_locked_until_phase_four_passes(self) -> None:
        self.revision()
        fase5 = next(f for f in self.status()["fases"] if f["stage_id"] == "poc_experiments")
        self.assertFalse(fase5["unlocked"])
        self.assertEqual(fase5["blocked_by"], "Fase 4")

    def test_sub_phases_read_their_own_step(self) -> None:
        self.spec(problem_statement="The gap.", pillars=[{"name": "P1"}])
        self.revision()
        subs = {s["id"]: s["status"] for s in self.fase4()["subfases"]}
        self.assertEqual(subs, {"4.1": "PASS", "4.2": "PENDING", "4.3": "LOCKED", "4.4": "PASS",
                                "4.5": "PENDING", "4.6": "LOCKED"})


HARNESS = r"""
const fs = require('fs');
const els = {};
const calls = [];
function el(id) { return els[id] || (els[id] = { id, innerHTML: '', hidden: false }); }
const listeners = {};
global.localStorage = { getItem: (k) => (k === 'papersmith-lang' ? process.argv[5] : null), setItem() {} };
global.window = { localStorage: global.localStorage,
  sendToCli: (text, run, opts) => { calls.push([text, run, opts && opts.kind]); return true; } };
global.document = { getElementById: el, querySelectorAll: () => [],
  addEventListener: (type, fn) => { (listeners[type] = listeners[type] || []).push(fn); } };
eval(fs.readFileSync(process.argv[2], 'utf8'));
eval(fs.readFileSync(process.argv[3], 'utf8'));
eval(fs.readFileSync(process.argv[4], 'utf8'));
eval(fs.readFileSync(process.argv[1], 'utf8'));
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
window.renderModelSteps(input.steps);
for (const id of input.clicks || []) {
  (listeners.click || []).forEach((fn) => fn({ target: { closest: (sel) => (sel === '[data-model-step]' ? { dataset: { modelStep: id }, disabled: false } : null) } }));
}
console.log(JSON.stringify({ html: el('modelFlowSteps').innerHTML, calls }));
"""


def render(steps: list[dict], lang: str = "en", clicks: list[str] | None = None) -> dict:
    out = subprocess.run(["node", "-e", HARNESS, str(STATIC / "model-panel.js"), str(EN_JS), str(ES_JS),
                          str(I18N_JS), lang],
                         input=json.dumps({"steps": steps, "clicks": clicks or []}),
                         capture_output=True, text=True, cwd=tempfile.gettempdir(), check=True)
    return json.loads(out.stdout)


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class ConceptMapStepperTests(_Workspace):
    def test_the_stepper_names_the_three_steps_in_order(self) -> None:
        html = render(phase_steps.proposal_steps(self.root))["html"]
        positions = [html.index(f'data-model-step="{i}"') for i in phase_steps.STEP_IDS]
        self.assertEqual(positions, sorted(positions))

    def test_a_locked_step_disables_its_button_and_says_what_it_requires(self) -> None:
        html = render(phase_steps.proposal_steps(self.root))["html"]
        button = re.search(r'<button[^>]*data-model-step="hypotheses"[^>]*>', html).group(0)
        self.assertIn("disabled", button)
        self.assertIn("Requires: Problem and pillars", html)
        first = re.search(r'<button[^>]*data-model-step="problem_pillars"[^>]*>', html).group(0)
        self.assertNotIn("disabled", first)

    def test_spanish_names_the_requirement_too(self) -> None:
        html = render(phase_steps.proposal_steps(self.root), "es")["html"]
        self.assertIn("Requiere: Problema y pilares", html)

    def test_buttons_type_the_step_slash_command(self) -> None:
        self.spec(problem_statement="The gap.", pillars=[{"name": "P1"}], hypotheses=[{"statement": "H1"}])
        result = render(phase_steps.proposal_steps(self.root),
                        clicks=["problem_pillars", "hypotheses", "mathematics", "math-tutor"])
        texts = [c[0] for c in result["calls"]]
        self.assertEqual(len(texts), 4)
        self.assertTrue(texts[0].startswith("/proposal-deliberation ") and "pillars" in texts[0])
        self.assertTrue(texts[1].startswith("/proposal-deliberation ") and "hypothes" in texts[1])
        self.assertTrue(texts[2].startswith("/proposal-deliberation ") and "\\tag" in texts[2])
        self.assertTrue(texts[3].startswith("/math-tutor"))
        self.assertTrue(all(c[2] == "slash" and c[1] is False for c in result["calls"]))

    def test_a_locked_step_sends_nothing(self) -> None:
        result = render(phase_steps.proposal_steps(self.root), clicks=["mathematics", "math-tutor"])
        self.assertEqual(result["calls"], [])

    def test_evidence_values_are_escaped(self) -> None:
        steps = phase_steps.proposal_steps(self.root)
        steps[0]["evidence"]["source"] = "<img src=x onerror=alert(1)>"
        steps[0]["evidence"]["pillars"] = 1
        html = render(steps)["html"]
        self.assertNotIn("<img", html)


if __name__ == "__main__":
    unittest.main()
