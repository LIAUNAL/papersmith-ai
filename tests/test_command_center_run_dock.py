"""The run dock ticks every second while a phase runs: the tick updates the
elapsed time in place and rebuilds the dock only when something else in it
changed. Runs the real phase-run.js in node with a stub DOM."""

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
const store = { 'papersmith-lang': 'es' };
const els = {};
let builds = 0;
const timeNodes = {};
function el(id) {
  if (els[id]) return els[id];
  let html = '';
  const node = { id, dataset: {}, textContent: '', hidden: false, style: {}, classList: { add() {}, remove() {} },
    setAttribute() {}, matches: () => false,
    get innerHTML() { return html; },
    set innerHTML(v) { html = v; builds += 1; for (const k in timeNodes) delete timeNodes[k]; },
    // The time spans the markup holds, as the browser would find them.
    querySelectorAll(sel) {
      if (sel !== '[data-run-time]') return [];
      return [...html.matchAll(/data-run-time="([^"]+)">([^<]*)</g)].map(([, stage, text]) =>
        timeNodes[stage] || (timeNodes[stage] = { dataset: { runTime: stage }, textContent: text }));
    } };
  return (els[id] = node);
}
global.localStorage = { getItem: (k) => store[k] ?? null, setItem: (k, v) => { store[k] = v; } };
let made = 0;
global.document = { getElementById: (id) => els[id] || null, addEventListener() {},
  createElement: () => el('made' + (made++)), body: { appendChild(n) { els[n.id] = n; } } };
global.window = { localStorage: global.localStorage, smithTerminalActivity: () => ({ agent: 'claude', sessionId: 's1', lastOutputAt: Date.now() }) };
eval(fs.readFileSync(process.argv[2], 'utf8'));
eval(fs.readFileSync(process.argv[3], 'utf8'));
eval(fs.readFileSync(process.argv[4], 'utf8'));
eval(fs.readFileSync(process.argv[1], 'utf8'));
const phase = { stage_id: 'plausibility', id: 'Fase 2', name: 'Plausibilidad', status: 'PENDING', unlocked: true,
  evidence: [{ label: 'Atlas', path: 'sota-pool/atlas.json', count: 0, mtime: 0 }] };
window.currentStatus = { fases: [phase] };
const realNow = Date.now;
let shift = 0;
Date.now = () => realNow() + shift;
window.phaseRuns.start(phase, '/plausibility idea');
const out = { builds: [], times: [] };
const dock = () => els.phaseRunDock;
const timeText = () => (dock().querySelectorAll('[data-run-time]')[0] || {}).textContent;
for (const step of [1000, 2000, 3000]) {
  shift = step;
  window.phaseRuns.renderDock();
  out.builds.push(builds);
  out.times.push(timeText());
}
// The phase passes: the dock's state changes, so it is rebuilt.
const passed = JSON.parse(JSON.stringify(window.currentStatus));
passed.fases[0].status = 'PASS';
window.currentStatus = passed;
window.phaseRuns.onStatus(passed);
window.phaseRuns.renderDock();
out.afterPass = builds;
out.html = dock().innerHTML;
console.log(JSON.stringify(out));
process.exit(0);
"""


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class RunDockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        done = subprocess.run(["node", "-e", HARNESS, str(SCRIPT), str(EN_JS), str(ES_JS), str(I18N_JS)], capture_output=True, text=True,
                              cwd=tempfile.gettempdir(), timeout=60, check=True)
        cls.out = json.loads(done.stdout)

    def test_a_tick_updates_the_time_without_rebuilding_the_dock(self) -> None:
        builds = self.out["builds"]
        self.assertEqual(builds[0], builds[-1])
        self.assertEqual(self.out["times"], ["0:01", "0:02", "0:03"])

    def test_a_change_of_state_rebuilds_the_dock(self) -> None:
        self.assertGreater(self.out["afterPass"], self.out["builds"][-1])
        self.assertIn("verificada", self.out["html"])
        self.assertIn('data-run-open="plausibility"', self.out["html"])


if __name__ == "__main__":
    unittest.main()
