"""Protocol visibility and disclosure state use only the existing browser surface.

The Node fixture models the details elements replaced by the panel's paint cycle;
real-browser refresh, navigation and language checks complement it at delivery.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "skills/_core/command_center/static/experiments-panel.js"
VIEW = {
    "dashboard": {"stale": True},
    "protocol": {"file": "experiments/experiments-demo-v01.md", "revision": 1,
                 "experiments": [
                     {"id": "E1", "title": "First", "hypothesis": "Existing hypothesis",
                      "success_criterion": "Existing criterion", "expected_reports": []},
                     {"id": "E2", "title": "Second", "hypothesis": "Other hypothesis",
                      "expected_reports": []}]},
    "products": [{"name": name, "path": f"implementations/{name}", "kind": "poc",
                  "runs": {"count": 1, "by_state": {}, "latest": []},
                  "remote_workers": [{"worker": "example-worker", "lanes": []}],
                  "hpo": [{"study": "shared-study", "file": "Results/hpo/shared/summary.json"}]}
                 for name in ("Alpha", "Beta")],
}
HARNESS = r"""
const fs = require('fs');
const assert = require('node:assert/strict');
const {source, view, action} = JSON.parse(fs.readFileSync(0, 'utf8'));
const events = {};
const decode = s => s.replace(/&quot;/g, '"').replace(/&#39;/g, "'")
    .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
let html = '', nodes = [];
const host = {
  get innerHTML() { return html; },
  set innerHTML(value) {
    html = value;
    nodes = [...value.matchAll(/<details\b([^>]*)>/g)].map((m) => {
      const key = m[1].match(/data-exp-disclosure="([^"]*)"/);
      return key ? {dataset: {expDisclosure: decode(key[1])}, open: /\bopen(?:\s|$)/.test(m[1])} : null;
    }).filter(Boolean);
  },
  querySelectorAll() { return nodes; },
};
global.window = {i18n: {t: k => k, has: () => false}};
global.document = {getElementById: () => host, addEventListener: (name, fn) => {events[name] = fn;}};
global.fetch = async () => ({ok: true, json: async () => view});
eval(source);
const find = (kind, value) => nodes.find(n => {
  const key = JSON.parse(n.dataset.expDisclosure);
  return key[0] === kind && key.includes(value);
});
(async () => {
  await window.refreshExperimentsPanel();
  if (action === 'order') {
    assert(html.indexOf('exp.beforeLaunch') < html.indexOf('exp.protocol'));
    assert(html.indexOf('exp.protocol') < html.indexOf('exp.mcp'));
  } else if (action === 'legacy') {
    assert(html.includes('Existing hypothesis') && html.includes('Existing criterion'));
    assert(html.includes('exp.beforeLaunch') && html.includes('exp.group.poc'));
    assert.equal(find('protocol', 'E2')?.open ?? false, false);
    assert(!html.includes('undefined'));
  } else if (action === 'refresh' || action === 'language') {
    const first = find('protocol', 'E1'); assert(first, 'experiment needs a stable disclosure key');
    first.open = true;
    if (action === 'language') {
      window.i18n.t = k => 'translated ' + k;
      events.languagechange();
      await new Promise(setImmediate);
    } else { await window.refreshExperimentsPanel(); }
    assert.equal(find('protocol', 'E1').open, true);
    assert.equal(find('protocol', 'E2').open, false);
    find('protocol', 'E1').open = false;
    await window.refreshExperimentsPanel();
    assert.equal(find('protocol', 'E1').open, false);
  } else {
    const first = find(action, 'implementations/Alpha');
    const second = find(action, 'implementations/Beta');
    assert(first && second, action + ' needs product-scoped stable keys');
    assert.notEqual(first.dataset.expDisclosure, second.dataset.expDisclosure);
    first.open = true;
    await window.refreshExperimentsPanel();
    assert.equal(find(action, 'implementations/Alpha').open, true);
    assert.equal(find(action, 'implementations/Beta').open, false);
  }
  console.log('PASS');
})().catch(e => { console.error(e); process.exitCode = 1; });
"""


@unittest.skipUnless(shutil.which("node"), "node is required for panel interaction checks")
class DisclosureVisibilityTests(unittest.TestCase):
    def check_action(self, action: str) -> None:
        result = subprocess.run(
            ["node", "-e", HARNESS],
            input=json.dumps({"source": SCRIPT.read_text(encoding="utf-8"), "view": VIEW, "action": action}),
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "PASS")

    def test_protocol_precedes_service_panels_without_hiding_launch_warnings(self) -> None:
        self.check_action("order")

    def test_open_and_closed_protocol_items_survive_refetch(self) -> None:
        self.check_action("refresh")

    def test_language_repaint_preserves_machine_keyed_protocol_state(self) -> None:
        self.check_action("language")

    def test_hpo_state_is_scoped_by_product_even_with_shared_study_names(self) -> None:
        self.check_action("hpo")

    def test_remote_run_disclosures_survive_refetch(self) -> None:
        self.check_action("runs")

    def test_worker_disclosures_survive_refetch(self) -> None:
        self.check_action("workers")

    def test_existing_hypothesis_criterion_and_safety_content_is_retained(self) -> None:
        self.check_action("legacy")
