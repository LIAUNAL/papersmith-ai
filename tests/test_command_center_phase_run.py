"""phase-run.js follows a phase from "Ejecutar" to the server's verdict:
evidence that changed, the PASS that verifies it, the phases it unlocked."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from skills._core.command_center import server

STATIC = Path(server.__file__).resolve().parent / "static"
PAGE = (STATIC / "index.html").read_text(encoding="utf-8")
I18N_JS = STATIC / "i18n.js"
EN_JS = STATIC / "i18n" / "en.js"
ES_JS = STATIC / "i18n" / "es.js"

HARNESS = r"""
const fs = require('fs');
const cfg = JSON.parse(fs.readFileSync(0, 'utf8'));
const store = { 'papersmith-lang': 'es' };
const els = {};
function el(id) { return els[id] || (els[id] = { id, dataset: {}, innerHTML: '', textContent: '', classList: { add() {}, remove() {} }, setAttribute() {}, querySelectorAll: () => [] }); }
global.localStorage = { getItem: (k) => store[k] ?? null, setItem: (k, v) => { store[k] = v; } };
let made = 0;
global.document = { getElementById: (id) => els[id] || null, addEventListener() {}, createElement: () => el('made' + (made++)), body: { appendChild(n) { els[n.id] = n; } } };
let lastOut = Date.now();
global.window = { localStorage: global.localStorage, smithTerminalActivity: () => ({ agent: 'claude', lastOutputAt: lastOut }) };
const phase = (stage, id, status, unlocked, evidence) => ({ stage_id: stage, id, name: id + ' name', status, unlocked, evidence });
eval(fs.readFileSync(process.argv[2], 'utf8'));
eval(fs.readFileSync(process.argv[3], 'utf8'));
eval(fs.readFileSync(process.argv[4], 'utf8'));
eval(fs.readFileSync(process.argv[1], 'utf8'));
const out = {};
const before = { fases: [
  phase('harness', 'Fase 1', 'PASS', true, []),
  phase('plausibility', 'Fase 2', 'PENDING', true, [{ label: 'Atlas', path: 'sota-pool/atlas.json', count: 0, mtime: 0 }]),
  phase('ingestion', 'Fase 3', 'PENDING', false, []),
] };
window.currentStatus = before;
window.phaseRuns.start(before.fases[1], '/plausibility ' + cfg.idea);
out.running = window.phaseRuns.isRunning('plausibility');
out.dock = (els.phaseRunDock || {}).innerHTML || '';
lastOut = Date.now() + 1;
const realNow0 = Date.now;
Date.now = () => realNow0() + 25000;
out.trackerIdle = window.phaseRuns.renderTracker(before.fases[1]);
Date.now = realNow0;
lastOut = Date.now();
out.trackerStart = window.phaseRuns.renderTracker(before.fases[1]);
const middle = JSON.parse(JSON.stringify(before));
middle.fases[1].evidence[0] = { label: 'Atlas', path: 'sota-pool/atlas.json', count: 1, mtime: 5 };
window.currentStatus = middle;
window.phaseRuns.onStatus(middle);
out.trackerMiddle = window.phaseRuns.renderTracker(middle.fases[1]);
out.stillRunning = window.phaseRuns.isRunning('plausibility');
const after = JSON.parse(JSON.stringify(middle));
after.fases[1].status = 'PASS';
after.fases[2].unlocked = true;
window.currentStatus = after;
window.phaseRuns.onStatus(after);
out.trackerAfter = window.phaseRuns.renderTracker(after.fases[1]);
out.verified = !window.phaseRuns.isRunning('plausibility');
out.glow = window.phaseRuns.justUnlocked('ingestion');
out.badge = window.phaseRuns.cardBadge('plausibility');
out.stored = JSON.parse(store['smith_phase_runs@local']).plausibility.unlocked;
window.phaseRuns.dismiss('plausibility');
out.afterDismiss = window.phaseRuns.renderTracker(after.fases[1]);
// Re-running a phase that already passed waits for new evidence.
window.phaseRuns.start(after.fases[1], '/plausibility again');
window.phaseRuns.onStatus(after);
out.rerunWaits = window.phaseRuns.isRunning('plausibility');
const newer = JSON.parse(JSON.stringify(after));
newer.fases[1].evidence[0].mtime = 99;
window.phaseRuns.onStatus(newer);
out.rerunVerified = !window.phaseRuns.isRunning('plausibility');
// A run nothing touches for 30 min stops being followed.
window.phaseRuns.start(after.fases[2], '/paper-ingestion x');
const realNow = Date.now;
Date.now = () => realNow() + 31 * 60 * 1000;
window.phaseRuns.onStatus(after);
out.expired = !window.phaseRuns.isRunning('ingestion');
out.expiredBadge = window.phaseRuns.cardBadge('ingestion');
// The phase passes later (closed dashboard, another session): the server's
// verdict reconciles the expired run instead of leaving it stuck.
const later = JSON.parse(JSON.stringify(after));
later.fases[2].status = 'PASS';
window.phaseRuns.onStatus(later);
out.expiredReconciled = window.phaseRuns.cardBadge('ingestion');
Date.now = realNow;
console.log(JSON.stringify(out));
process.exit(0);
"""


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class PhaseRunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        done = subprocess.run(["node", "-e", HARNESS, str(STATIC / "phase-run.js"), str(EN_JS), str(ES_JS), str(I18N_JS)],
                              input=json.dumps({"idea": "<img src=x onerror=alert(1)>"}),
                              capture_output=True, text=True, cwd=tempfile.gettempdir(), timeout=60, check=True)
        cls.out = json.loads(done.stdout)

    def test_a_run_starts_with_the_command_sent_and_waits_for_evidence(self) -> None:
        self.assertTrue(self.out["running"])
        self.assertIn("Comando enviado", self.out["trackerStart"])
        self.assertIn("En ejecución", self.out["trackerStart"])
        self.assertIn("Trabajando (claude)", self.out["trackerStart"])

    def test_a_floating_dock_shows_the_run_on_any_tab(self) -> None:
        self.assertIn('data-run-open="plausibility"', self.out["dock"])
        self.assertIn("en ejecución", self.out["dock"])

    def test_an_agent_that_stops_writing_is_reported_as_waiting(self) -> None:
        self.assertIn("espera tu respuesta en la terminal", self.out["trackerIdle"])

    def test_changed_evidence_is_shown_but_does_not_verify_the_stage(self) -> None:
        self.assertIn('class="is-new"', self.out["trackerMiddle"])
        self.assertTrue(self.out["stillRunning"])
        self.assertIn("Estado actual: PENDING", self.out["trackerMiddle"])

    def test_the_servers_pass_verifies_and_names_the_unlocked_phase(self) -> None:
        self.assertTrue(self.out["verified"])
        self.assertIn("Etapa verificada en", self.out["trackerAfter"])
        self.assertIn("<strong>Fase 3</strong>", self.out["trackerAfter"])
        self.assertTrue(self.out["glow"])
        self.assertIn("verificada", self.out["badge"])
        self.assertEqual(self.out["stored"], [{"stage": "ingestion", "id": "Fase 3", "name": "Fase 3 name"}])

    def test_a_rerun_of_a_passed_phase_needs_new_evidence(self) -> None:
        self.assertTrue(self.out["rerunWaits"])
        self.assertTrue(self.out["rerunVerified"])

    def test_a_quiet_run_stops_being_followed(self) -> None:
        self.assertTrue(self.out["expired"])
        self.assertIn("sin cambios", self.out["expiredBadge"])

    def test_the_command_is_escaped_and_a_dismissed_run_disappears(self) -> None:
        self.assertNotIn("<img", self.out["trackerStart"])
        self.assertEqual(self.out["afterDismiss"], "")


STOPPED_HARNESS = r"""
const fs = require('fs');
const store = { 'papersmith-lang': 'es', 'smith_phase_runs@local': JSON.stringify({ plausibility: {
  stage: 'plausibility', phaseId: 'Fase 2', command: '/plausibility x', startedAt: 1, lastChangeAt: 1,
  startStatus: 'ACTIVE', status: 'ACTIVE', stoppedAt: 2, verifiedAt: 0, expiredAt: 0,
  baseline: {}, changed: [], unlocked: [], unlockedBefore: [] } }) };
const els = {};
function el(id) { return els[id] || (els[id] = { id, dataset: {}, innerHTML: '', textContent: '', classList: { add() {}, remove() {} }, setAttribute() {}, querySelectorAll: () => [] }); }
global.localStorage = { getItem: (k) => store[k] ?? null, setItem: (k, v) => { store[k] = v; } };
let made = 0;
global.document = { getElementById: (id) => els[id] || null, addEventListener() {}, createElement: () => el('made' + (made++)), body: { appendChild(n) { els[n.id] = n; } } };
global.window = { localStorage: global.localStorage, smithTerminalActivity: () => ({ agent: 'claude', lastOutputAt: Date.now() }) };
eval(fs.readFileSync(process.argv[2], 'utf8'));
eval(fs.readFileSync(process.argv[3], 'utf8'));
eval(fs.readFileSync(process.argv[4], 'utf8'));
eval(fs.readFileSync(process.argv[1], 'utf8'));
const out = { before: window.phaseRuns.cardBadge('plausibility') };
window.phaseRuns.onStatus({ fases: [{ stage_id: 'plausibility', id: 'Fase 2', name: 'Fase 2 name', status: 'PASS', unlocked: true, evidence: [] }] });
out.after = window.phaseRuns.cardBadge('plausibility');
console.log(JSON.stringify(out));
process.exit(0);
"""


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class StoppedRunReconciliationTests(unittest.TestCase):
    def test_a_stopped_run_whose_phase_passed_reads_verified(self) -> None:
        done = subprocess.run(["node", "-e", STOPPED_HARNESS, str(STATIC / "phase-run.js"), str(EN_JS), str(ES_JS), str(I18N_JS)],
                              capture_output=True, text=True, cwd=tempfile.gettempdir(), timeout=60, check=True)
        out = json.loads(done.stdout)
        self.assertIn("detenida", out["before"])
        self.assertIn("verificada", out["after"])

    def test_an_expired_run_whose_phase_passed_reads_verified(self) -> None:
        done = subprocess.run(["node", "-e", HARNESS, str(STATIC / "phase-run.js"), str(EN_JS), str(ES_JS), str(I18N_JS)],
                              input=json.dumps({"idea": "x"}), capture_output=True, text=True,
                              cwd=tempfile.gettempdir(), timeout=60, check=True)
        self.assertIn("verificada", json.loads(done.stdout)["expiredReconciled"])


class PageWiringTests(unittest.TestCase):
    def test_the_page_feeds_every_status_to_the_tracker(self) -> None:
        self.assertIn('<script src="./phase-run.js?v=', PAGE)
        self.assertIn("if (window.phaseRuns) window.phaseRuns.onStatus(data);", PAGE)
        self.assertIn('<div id="phaseRunTracker" data-stage=', PAGE)
        self.assertIn("artifacts: (data.artifacts || []).map(a => `${a.rel_path}:${a.size_kb}`),", PAGE)
        self.assertTrue("🔒 Requiere ${escapeHtml(p.blocked_by)}" in PAGE or "pipeline.requires" in PAGE)


if __name__ == "__main__":
    unittest.main()
