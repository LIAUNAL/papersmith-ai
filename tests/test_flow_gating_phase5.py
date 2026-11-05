"""Phase 5 forces proof of concept → verification → full experiment.

The operator verifies a proof of concept whose discussion is complete (its
results and contrasted hypotheses) by recording a PoC-stage decision in the
novelty gate record; G-EXP-POC passes only then, and the full experiments
(sub-phase 5.12, the /experimental-implementation action and the Experiments
tab's "Full experiment" button) stay locked until it does."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from papersmith.core import novelty
from skills._core.command_center import phase_actions, server
from skills._core.results import novelty_cli, novelty_gate
from tests.test_phase5_review import _Status, _write_discussion

STATIC = Path(server.__file__).resolve().parent / "static"
EN_JS, ES_JS, I18N_JS = STATIC / "i18n" / "en.js", STATIC / "i18n" / "es.js", STATIC / "i18n.js"


class _Workspace(_Status):
    def poc(self, complete: bool = True) -> Path:
        return self.product("Poc", "AGREED.md", discussion="complete" if complete else "draft")

    def gate(self, gate_id: str) -> dict:
        return next(g for g in self.status()["gates"] if g["id"] == gate_id)


class PocDecisionTests(_Workspace):
    def test_poc_approval_refuses_without_a_complete_poc_discussion(self) -> None:
        self.poc(complete=False)
        with self.assertRaises(novelty_gate.NoveltyRefusal) as ctx:
            novelty_gate.record_decision(self.root, "approve", stage="poc")
        self.assertEqual(ctx.exception.code, "POC_DISCUSSION_INCOMPLETE")
        self.assertEqual(novelty_gate.read_gate(self.root)["poc"]["status"], "pending")

    def test_poc_approval_records_a_sub_record_beside_the_full_decision(self) -> None:
        self.poc()
        novelty_gate.record_decision(self.root, "iterate_experiments", rationale="full: more seeds")
        record = novelty_gate.record_decision(self.root, "approve", rationale="PoC holds", actor="ana", stage="poc")
        self.assertEqual(record["poc"]["status"], "approved")
        self.assertEqual((record["poc"]["actor"], record["poc"]["rationale"]), ("ana", "PoC holds"))
        self.assertIsNotNone(record["poc"]["decided_at"])
        gate = novelty_gate.read_gate(self.root)
        self.assertEqual(gate["status"], "iterating_experiments")
        self.assertEqual(gate["poc"]["status"], "approved")

    def test_a_full_decision_keeps_the_poc_record(self) -> None:
        self.poc()
        novelty_gate.record_decision(self.root, "approve", stage="poc")
        novelty_gate.record_decision(self.root, "approve", rationale="full")
        gate = novelty_gate.read_gate(self.root)
        self.assertEqual((gate["status"], gate["poc"]["status"]), ("approved", "approved"))

    def test_poc_iterate_needs_no_discussion_and_reads_back(self) -> None:
        record = novelty_gate.record_decision(self.root, "iterate", rationale="redo", stage="poc")
        self.assertEqual(record["poc"]["status"], "iterating")
        self.assertEqual(record["status"], "pending")

    def test_an_unknown_stage_refuses(self) -> None:
        with self.assertRaises(novelty_gate.NoveltyRefusal) as ctx:
            novelty_gate.record_decision(self.root, "approve", stage="draft")
        self.assertEqual(ctx.exception.code, "INVALID_STAGE")

    def test_the_overview_reports_the_poc_verification(self) -> None:
        self.poc()
        overview = novelty_gate.get_novelty_overview(self.root)
        self.assertEqual(overview["poc_verification"]["discussed"], 1)
        self.assertEqual(overview["poc_verification"]["decision"]["status"], "pending")

    def test_the_skill_cli_takes_the_gate_flag(self) -> None:
        self.assertEqual(novelty_cli.main(["approve", "--root", str(self.root), "--gate", "poc"]), 1)
        self.poc()
        self.assertEqual(novelty_cli.main(["approve", "--root", str(self.root), "--gate", "poc"]), 0)
        self.assertEqual(novelty_gate.read_gate(self.root)["poc"]["status"], "approved")
        self.assertEqual(novelty_gate.read_gate(self.root)["status"], "pending")
        self.assertEqual(novelty_cli.main(["iterate", "--root", str(self.root), "--gate", "poc",
                                           "--stage", "experiments"]), 0)
        self.assertEqual(novelty_gate.read_gate(self.root)["poc"]["status"], "iterating")

    def test_smith_novelty_takes_the_gate_flag(self) -> None:
        (self.root / ".papersmith").mkdir(exist_ok=True)
        self.poc()

        class Args:
            workspace = str(self.root)
            notes = "PoC verified"
            gate = "poc"
        self.assertEqual(novelty.run_approve(Args()), 0)
        self.assertEqual(novelty_gate.read_gate(self.root)["poc"]["status"], "approved")
        self.assertEqual(novelty_gate.read_gate(self.root)["status"], "pending")

    def test_a_poc_iteration_keeps_the_stage_the_operator_named(self) -> None:
        for stage, target in (("proposal", "proposal"), ("plausibility", "plausibility"),
                              ("experiments", "poc_experiments")):
            with self.subTest(cli="skill", stage=stage):
                self.assertEqual(novelty_cli.main(["iterate", "--root", str(self.root), "--gate", "poc",
                                                   "--stage", stage]), 0)
                self.assertEqual(novelty_gate.read_gate(self.root)["poc"]["target_stage"], target)
        (self.root / ".papersmith").mkdir(exist_ok=True)

        class Args:
            workspace = str(self.root)
            notes = "back to the proposal"
            gate = "poc"
            stage = "proposal"
        self.assertEqual(novelty.run_iterate(Args()), 0)
        poc = novelty_gate.read_gate(self.root)["poc"]
        self.assertEqual((poc["status"], poc["target_stage"]), ("iterating", "proposal"))
        self.poc()
        novelty_gate.record_decision(self.root, "approve", stage="poc")
        self.assertEqual(novelty_gate.read_gate(self.root)["poc"]["target_stage"], "full_experiments")

    def test_the_decision_route_takes_the_stage(self) -> None:
        client = TestClient(self.app)
        res = client.post("/api/novelty/decision", json={"action": "approve", "stage": "poc"})
        self.assertEqual(res.status_code, 422)
        self.assertEqual(res.json()["error"], "POC_DISCUSSION_INCOMPLETE")
        self.poc()
        res = client.post("/api/novelty/decision", json={"action": "approve", "stage": "poc", "notes": "ok"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["gate"]["poc"]["status"], "approved")


class PocGateTests(_Workspace):
    def test_g_exp_poc_is_pending_without_a_complete_poc_discussion(self) -> None:
        self.protocol()
        self.poc(complete=False)
        self.assertEqual(self.gate("G-EXP-POC")["status"], "PENDING")

    def test_g_exp_poc_is_active_while_the_complete_poc_awaits_verification(self) -> None:
        self.poc()
        self.assertEqual(self.gate("G-EXP-POC")["status"], "ACTIVE")
        novelty_gate.record_decision(self.root, "iterate", stage="poc")
        self.assertEqual(self.gate("G-EXP-POC")["status"], "ACTIVE")

    def test_g_exp_poc_passes_once_the_poc_is_approved(self) -> None:
        self.poc()
        novelty_gate.record_decision(self.root, "approve", stage="poc")
        gate = self.gate("G-EXP-POC")
        self.assertEqual(gate["status"], "PASS")
        self.assertIn("verif", gate["name"].lower())

    def test_g_novelty_no_longer_names_sub_phase_5_5(self) -> None:
        phase = self.gate("G-NOVELTY")["phase"]
        self.assertNotIn("5.5", phase)
        self.assertEqual(phase, "Fase 5")

    def test_full_experiments_are_locked_until_the_poc_is_verified(self) -> None:
        sub = self.sub("Full experiments")
        self.assertEqual(sub["status"], "LOCKED")
        self.assertIn("G-EXP-POC", sub["detail"])
        self.poc()
        novelty_gate.record_decision(self.root, "approve", stage="poc")
        self.assertEqual(self.sub("Full experiments")["status"], "PENDING")


class FullActionRequiresTests(_Workspace):
    def action(self) -> dict:
        return next(a for a in self.fase5()["actions"] if a.get("slash") == "/experimental-implementation")

    def test_the_full_action_requires_the_poc_gate(self) -> None:
        declared = next(a for a in phase_actions.ACTIONS["poc_experiments"]["actions"]
                        if a.get("slash") == "/experimental-implementation")
        self.assertEqual(declared["requires"], "G-EXP-POC")
        self.assertTrue(self.action()["locked"])
        self.poc()
        novelty_gate.record_decision(self.root, "approve", stage="poc")
        self.assertFalse(self.action()["locked"])

    def test_the_poc_action_needs_only_the_citations(self) -> None:
        poc = next(a for a in self.fase5()["actions"] if a.get("label") == "Implement the proof of concept")
        self.assertEqual((poc["requires"], poc["locked"]), ("G-SOTA-CITATIONS", False))


CONSOLE = r"""
const fs = require('fs');
const calls = []; const els = {}; const listeners = {};
function el(id) { return els[id] || (els[id] = { id, value: '', textContent: '', hidden: false, checked: false,
  classList: { add(){}, remove(){} }, focus(){} }); }
global.localStorage = { getItem: (k) => (k === 'papersmith-lang' ? 'en' : null), setItem() {} };
global.window = { localStorage: global.localStorage, smithTerminalActivity: () => ({}),
  sendToCli: async (t, r, o) => { calls.push([t, r, o && o.kind]); return true; } };
global.document = { getElementById: el, querySelectorAll: () => [],
  addEventListener: (type, fn) => { listeners[type] = fn; } };
eval(fs.readFileSync(process.argv[2], 'utf8'));
eval(fs.readFileSync(process.argv[3], 'utf8'));
eval(fs.readFileSync(process.argv[4], 'utf8'));
eval(fs.readFileSync(process.argv[1], 'utf8'));
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
(async () => {
const html = window.renderPhaseActions(input.phase);
if (input.override) el('phaseActionOverride' + input.i).checked = true;
listeners.click({ target: { closest: (sel) => (sel.includes('data-kw-help') ? null : { dataset: { phaseAction: String(input.i) } }) } });
await new Promise((r) => setTimeout(r, 20));
console.log(JSON.stringify({ html, calls, error: el('phaseError' + input.i).textContent }));
})();
"""


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class PhaseConsoleRequiresTests(unittest.TestCase):
    def run_console(self, locked: bool, override: bool = False) -> dict:
        actions = [dict(a) for a in phase_actions.ACTIONS["poc_experiments"]["actions"]]
        i = next(n for n, a in enumerate(actions) if a.get("slash") == "/experimental-implementation")
        actions[i]["locked"] = locked
        phase = {"stage_id": "poc_experiments", "unlocked": True, "actions": actions}
        out = subprocess.run(["node", "-e", CONSOLE, str(STATIC / "phase-console.js"), str(EN_JS), str(ES_JS),
                              str(I18N_JS)], input=json.dumps({"phase": phase, "i": i, "override": override}),
                             capture_output=True, text=True, cwd=tempfile.gettempdir(), check=True)
        return dict(json.loads(out.stdout), i=i)

    def button(self, result: dict) -> str:
        return re.search(rf'<button[^>]*data-phase-action="{result["i"]}"[^>]*>', result["html"]).group(0)

    def test_a_locked_action_renders_disabled_with_its_reason(self) -> None:
        result = self.run_console(locked=True)
        self.assertIn("disabled", self.button(result))
        self.assertIn("Requires the verified proof of concept (G-EXP-POC)", result["html"])
        self.assertEqual(result["calls"], [])
        self.assertIn("G-EXP-POC", result["error"])

    def test_the_override_still_runs_it(self) -> None:
        result = self.run_console(locked=True, override=True)
        self.assertEqual(result["calls"][0][0], "/experimental-implementation")

    def test_an_unlocked_action_is_enabled(self) -> None:
        result = self.run_console(locked=False)
        self.assertNotIn("disabled", self.button(result))
        self.assertEqual(result["calls"][0][0], "/experimental-implementation")


PANEL = r"""
const fs = require('fs');
const calls = []; const listeners = {};
const root = { innerHTML: '' };
global.localStorage = { getItem: (k) => (k === 'papersmith-lang' ? process.argv[6] : null), setItem() {} };
global.window = { localStorage: global.localStorage, location: { hash: '' }, addEventListener() {},
  sendToCli: (t, r, o) => { calls.push(['send', t, r, o && o.kind]); return true; },
  navigateTab: (tab) => calls.push(['tab', tab]) };
global.document = { querySelectorAll: () => [], getElementById: (id) => (id === 'noveltyRoot' || id === 'experimentsRoot' ? root : null),
  addEventListener: (type, fn) => { (listeners[type] = listeners[type] || []).push(fn); } };
eval(fs.readFileSync(process.argv[2], 'utf8'));
eval(fs.readFileSync(process.argv[3], 'utf8'));
eval(fs.readFileSync(process.argv[4], 'utf8'));
eval(fs.readFileSync(process.argv[1], 'utf8'));
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
let html;
if (process.argv[5] === 'novelty') { window.NoveltyPanel.render(input.data); html = root.innerHTML; }
else html = window.ExperimentsPanel.render(input.data);
for (const sel of input.clicks || []) {
  const [attr, value] = sel;
  (listeners.click || []).forEach((fn) => fn({ target: { closest: (s) => (s === `[${attr}]` ? { getAttribute: (a) => (a === attr ? value : null), dataset: {} } : null) } }));
}
console.log(JSON.stringify({ html, calls }));
"""


def render_panel(panel: str, data: dict, lang: str = "en", clicks: list | None = None) -> dict:
    script = STATIC / ("novelty-panel.js" if panel == "novelty" else "experiments-panel.js")
    out = subprocess.run(["node", "-e", PANEL, str(script), str(EN_JS), str(ES_JS), str(I18N_JS), panel, lang],
                         input=json.dumps({"data": data, "clicks": clicks or []}),
                         capture_output=True, text=True, cwd=tempfile.gettempdir(), check=True)
    return json.loads(out.stdout)


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class NoveltyPanelPocCardTests(_Workspace):
    def test_no_card_before_a_complete_poc_discussion(self) -> None:
        html = render_panel("novelty", novelty_gate.get_novelty_overview(self.root))["html"]
        self.assertNotIn('id="noveltyPocVerify"', html)

    def test_the_card_offers_approve_and_iterate_for_the_poc(self) -> None:
        self.poc()
        for lang, title in (("en", "Verify the proof of concept"), ("es", "Verificar la prueba de concepto")):
            with self.subTest(lang=lang):
                html = render_panel("novelty", novelty_gate.get_novelty_overview(self.root), lang)["html"]
                self.assertIn('id="noveltyPocVerify"', html)
                self.assertIn(title, html)
                self.assertIn("sendGateDecision('approve', 'poc')", html.replace("window.sendNoveltyDecision", "sendGateDecision"))
                self.assertIn("sendGateDecision('iterate', 'poc')", html.replace("window.sendNoveltyDecision", "sendGateDecision"))

    def test_an_approved_poc_shows_its_state(self) -> None:
        self.poc()
        novelty_gate.record_decision(self.root, "approve", stage="poc")
        html = render_panel("novelty", novelty_gate.get_novelty_overview(self.root))["html"]
        self.assertIn("Proof of concept verified", html)


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class ExperimentsStepperTests(_Workspace):
    def view(self) -> dict:
        return TestClient(self.app).get("/api/experiments").json()

    def test_the_view_carries_the_flow(self) -> None:
        self.assertEqual(self.view()["flow"], {"poc": 0, "poc_discussed": 0, "poc_decision": "pending",
                                               "gate": "PENDING",
                                               "citations": {"ideas": 0, "cited": 0, "owed": 0}})

    def test_the_stepper_orders_poc_verify_full_and_locks_full(self) -> None:
        self.poc()
        html = render_panel("experiments", self.view())["html"]
        positions = [html.index(f'data-exp-step="{s}"') for s in ("poc", "verify", "full")]
        self.assertEqual(positions, sorted(positions))
        full = re.search(r'<button[^>]*data-exp-step="full"[^>]*>', html).group(0)
        self.assertIn("disabled", full)
        self.assertIn("Requires the verified proof of concept (G-EXP-POC)", html)

    def test_buttons_type_the_slash_or_open_the_novelty_tab(self) -> None:
        self.poc()
        novelty_gate.record_decision(self.root, "approve", stage="poc")
        result = render_panel("experiments", self.view(),
                              clicks=[["data-exp-step", "poc"], ["data-exp-step", "verify"], ["data-exp-step", "full"]])
        self.assertNotIn("disabled", re.search(r'<button[^>]*data-exp-step="full"[^>]*>', result["html"]).group(0))
        sends = [c for c in result["calls"] if c[0] == "send"]
        self.assertTrue(sends[0][1].startswith("/proposal-implementation "))
        self.assertTrue(sends[1][1].startswith("/experimental-implementation "))
        self.assertTrue(all(c[2] is False and c[3] == "slash" for c in sends))
        self.assertIn(["tab", "novelty"], result["calls"])

    def test_a_locked_full_button_sends_nothing(self) -> None:
        result = render_panel("experiments", self.view(), clicks=[["data-exp-step", "full"]])
        self.assertEqual(result["calls"], [])

    def test_spanish_stepper(self) -> None:
        html = render_panel("experiments", self.view(), "es")["html"]
        self.assertIn("Requiere la prueba de concepto verificada (G-EXP-POC)", html)


if __name__ == "__main__":
    unittest.main()
