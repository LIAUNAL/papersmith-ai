"""A click on the run dock opens a tracking panel on the current tab: the
run's checkpoints, a link to the agent's terminal and a "Detener proceso"
button that interrupts the agent and stops following the run. Runs the real
phase-run.js in node with a stub DOM."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from skills._core.command_center import server

SCRIPT = Path(server.__file__).resolve().parent / "static" / "phase-run.js"
STATIC = Path(server.__file__).resolve().parent / "static"
I18N_JS = STATIC / "i18n.js"
EN_JS = STATIC / "i18n" / "en.js"
ES_JS = STATIC / "i18n" / "es.js"

HARNESS = r"""
const fs = require('fs');
const cfg = JSON.parse(fs.readFileSync(0, 'utf8'));
const store = { 'papersmith-lang': 'es' };
const els = {};
const calls = [];
function el(id) {
  return els[id] || (els[id] = { id, dataset: {}, innerHTML: '', textContent: '', hidden: false, style: {},
    offsetHeight: 40, classList: { add() {}, remove() {} }, setAttribute() {}, matches: () => false, querySelectorAll: () => [] });
}
global.localStorage = { getItem: (k) => store[k] ?? null, setItem: (k, v) => { store[k] = v; } };
let clickHandler = null;
let made = 0;
global.document = {
  getElementById: (id) => els[id] || null,
  addEventListener: (t, fn) => { if (t === 'click') clickHandler = fn; },
  createElement: () => el('made' + (made++)),
  body: { appendChild(n) { els[n.id] = n; } },
};
let session = 's1';
global.window = {
  localStorage: global.localStorage,
  smithTerminalActivity: () => ({ agent: 'claude', sessionId: session, lastOutputAt: Date.now() }),
  smithTerminalInterrupt: async () => { calls.push('interrupt'); if (cfg.interruptFails) throw new Error('HTTP 403'); return true; },
  openCliConsole: () => calls.push('terminal'),
  navigateTab: (t) => calls.push('tab:' + t),
  openDrawer: (i) => calls.push('drawer:' + i),
  confirm: () => cfg.confirm,
};
// A click on an element carrying `attr`, as the browser's closest() finds it.
function click(attr, value) {
  const target = { dataset: {}, closest: (sel) => (sel === `[${attr}]` ? target : null) };
  const key = attr.replace(/^data-/, '').replace(/-(.)/g, (_, c) => c.toUpperCase());
  target.dataset[key] = value;
  clickHandler({ target });
}
eval(fs.readFileSync(process.argv[2], 'utf8'));
eval(fs.readFileSync(process.argv[3], 'utf8'));
eval(fs.readFileSync(process.argv[4], 'utf8'));
eval(fs.readFileSync(process.argv[1], 'utf8'));
const phase = { stage_id: 'plausibility', id: 'Fase 2', name: 'Plausibilidad', status: 'PENDING', unlocked: true,
  evidence: [{ label: 'Atlas', path: 'sota-pool/atlas.json', count: 0, mtime: 0 }] };
window.currentStatus = { fases: [{ stage_id: 'harness', id: 'Fase 1', status: 'PASS', unlocked: true, evidence: [] }, phase] };
const out = {};
window.phaseRuns.start(phase, '/plausibility idea');
out.anyRunning = window.phaseRuns.anyRunning();
click('data-run-open', 'plausibility');
out.calls = calls.slice();
const panel = els.phaseRunPanel || {};
out.panelHidden = panel.hidden;
out.panel = panel.innerHTML || '';
session = 's2';
window.phaseRuns.onStatus(window.currentStatus);
out.panelOtherSession = (els.phaseRunPanel || {}).innerHTML || '';
session = 's1';
click('data-run-terminal', '1');
(async () => {
  click('data-run-stop', 'plausibility');
  await new Promise((r) => setTimeout(r, 50));
  out.callsAfterStop = calls.slice();
  out.runningAfterStop = window.phaseRuns.isRunning('plausibility');
  out.badge = window.phaseRuns.cardBadge('plausibility');
  out.panelAfterStop = (els.phaseRunPanel || {}).innerHTML || '';
  click('data-run-pipeline', 'plausibility');
  out.callsAfterPipeline = calls.slice();
  out.panelHiddenAfterPipeline = (els.phaseRunPanel || {}).hidden;
  console.log(JSON.stringify(out));
  process.exit(0);
})();
"""


def run(**cfg) -> dict:
    done = subprocess.run(["node", "-e", HARNESS, str(SCRIPT), str(EN_JS), str(ES_JS), str(I18N_JS)], input=json.dumps(cfg),
                          capture_output=True, text=True, cwd=tempfile.gettempdir(),
                          timeout=60, check=True)
    return json.loads(done.stdout)


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class RunPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.out = run(confirm=True)

    def test_the_dock_opens_the_panel_without_leaving_the_tab(self) -> None:
        self.assertTrue(self.out["anyRunning"])
        self.assertEqual(self.out["calls"], [])
        self.assertFalse(self.out["panelHidden"])

    def test_the_panel_shows_the_checkpoints_of_the_run(self) -> None:
        panel = self.out["panel"]
        self.assertIn("Fase 2", panel)
        for checkpoint in ("Comando enviado", "Agente trabajando", "Artefactos de la etapa",
                           "Etapa verificada", "Etapas siguientes"):
            self.assertIn(checkpoint, panel)
        self.assertIn("/plausibility idea", panel)
        self.assertIn("En ejecución", panel)

    def test_the_panel_leads_to_the_agent_terminal(self) -> None:
        self.assertIn('data-run-terminal="1"', self.out["panel"])
        self.assertIn("terminal", self.out["callsAfterStop"])

    def test_the_panel_says_when_the_phase_session_is_gone(self) -> None:
        self.assertNotIn("ya no está abierta", self.out["panel"])
        self.assertIn("ya no está abierta", self.out["panelOtherSession"])

    def test_stop_interrupts_the_agent_and_stops_following_the_run(self) -> None:
        self.assertIn('data-run-stop="plausibility"', self.out["panel"])
        self.assertIn("Detener proceso", self.out["panel"])
        self.assertIn("interrupt", self.out["callsAfterStop"])
        self.assertFalse(self.out["runningAfterStop"])
        self.assertIn("detenida", self.out["badge"])
        self.assertIn("Detenido por el operador", self.out["panelAfterStop"])
        self.assertNotIn('data-run-stop="plausibility"', self.out["panelAfterStop"])

    def test_the_panel_can_still_open_the_phase_in_the_pipeline(self) -> None:
        self.assertEqual(self.out["callsAfterPipeline"][-2:], ["tab:pipeline", "drawer:1"])
        self.assertTrue(self.out["panelHiddenAfterPipeline"])

    def test_a_failed_interrupt_keeps_following_the_run(self) -> None:
        out = run(confirm=True, interruptFails=True)
        self.assertIn("interrupt", out["callsAfterStop"])
        self.assertTrue(out["runningAfterStop"])
        self.assertIn('data-run-stop="plausibility"', out["panelAfterStop"])

    def test_a_declined_stop_changes_nothing(self) -> None:
        out = run(confirm=False)
        self.assertNotIn("interrupt", out["callsAfterStop"])
        self.assertTrue(out["runningAfterStop"])


if __name__ == "__main__":
    unittest.main()
