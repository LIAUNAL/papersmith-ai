"""The Paper type pane (paper-type-lines S4): one card per catalogue type with
its name and summary in the dashboard's language, the match score, the
relation to the idea, availability and guidelines; the suggestion, the
agreement and its staleness; and the three operator actions."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from skills._core.command_center import server
from skills._core.paper_types import registry, score

STATIC = Path(server.__file__).resolve().parent / "static"
PAGE = (STATIC / "index.html").read_text(encoding="utf-8")

HARNESS = r"""
const fs = require('fs');
const store = {};
const listeners = {};
const els = {};
function el(id) { return els[id] || (els[id] = { id, value: '', innerHTML: '', checked: false }); }
global.localStorage = { getItem: (k) => store[k] ?? null, setItem: (k, v) => { store[k] = v; } };
global.CustomEvent = function (name, init) { this.type = name; this.detail = init && init.detail; };
global.window = { localStorage: global.localStorage };
global.document = {
  documentElement: {}, readyState: 'complete', getElementById: el, querySelectorAll: () => [],
  addEventListener: (type, fn) => { (listeners[type] = listeners[type] || []).push(fn); },
  dispatchEvent: (e) => { (listeners[e.type] || []).forEach((fn) => fn(e)); },
};
for (const file of process.argv.slice(1)) eval(fs.readFileSync(file, 'utf8'));
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
window.i18n.setLanguage(input.lang || 'en');
const calls = [];
window.sendToCli = (t, r, o) => calls.push(['send', t, r, o && o.kind]);
window.navigateTab = (tab) => calls.push(['tab', tab]);
global.fetch = async (url, init) => {
  calls.push(['fetch', url, init && init.body ? JSON.parse(init.body) : null]);
  const r = (input.responses || {})[url] || { status: 200, body: input.view };
  return { ok: r.status < 400, status: r.status, json: async () => r.body };
};
(async () => {
  const out = { html: window.PaperTypePanel.html(input.view) };
  window.PaperTypePanel.render(input.view);
  for (const step of input.steps || []) {
    if (step.values) Object.entries(step.values).forEach(([id, v]) => { el(id).value = v; });
    await window.PaperTypePanel.act(step.action, step.type);
    await new Promise((r) => setTimeout(r, 5));
  }
  out.calls = calls;
  out.rendered = el('paperTypePanel').innerHTML;
  console.log(JSON.stringify(out));
})();
"""

IDEA = ("Encuestamos 368 jóvenes rurales de tres municipios. Con una encuesta y regresión Probit "
        "estudiamos <script>alert(1)</script> qué determina su permanencia.")


def view(**decision_overrides) -> dict:
    result = score.score(IDEA)
    record = {**result, "idea_sha256": "a", "agreed": None, "agreed_variant": None, "agreed_by": None,
              "agreed_stale": False, **decision_overrides}
    return {"catalogue": registry.load(), "line": "experimental", "error": None,
            "plausibility": {"idea": IDEA, "accepted_by": "op", "accepted_at": "2026-11-22T10:00:00Z"},
            "decision": record, "subphase": {}}


def run(data: dict, lang: str = "en", steps=(), responses=None) -> dict:
    files = [str(STATIC / "i18n" / "en.js"), str(STATIC / "i18n" / "es.js"), str(STATIC / "i18n.js"),
             str(STATIC / "paper-type-panel.js")]
    done = subprocess.run(["node", "-e", HARNESS, *files], capture_output=True, text=True, check=True,
                          input=json.dumps({"view": data, "lang": lang, "steps": list(steps),
                                            "responses": responses or {}}),
                          cwd=tempfile.gettempdir())
    return json.loads(done.stdout)


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class PanelRenderTests(unittest.TestCase):
    def test_one_card_per_type_in_catalogue_order(self) -> None:
        html = run(view())["html"]
        positions = [html.index(f'data-pt-card="{t["id"]}"') for t in registry.load()]
        self.assertEqual(positions, sorted(positions))

    def test_the_suggestion_and_relation_in_spanish(self) -> None:
        html = run(view(), lang="es")["html"]
        self.assertIn("Sugerido: Estudio observacional y de medición (Estudio observacional), confianza", html)
        self.assertIn("La idea menciona: ", html)
        self.assertIn("encuesta", html)
        self.assertIn("La idea no muestra señales de este tipo", html)
        self.assertIn("flujo disponible", html)
        # Every shipped type has a line since the qualitative-participatory line; a planned entry still says so.
        self.assertNotIn("flujo planificado", html)
        planned = view()
        planned["catalogue"] = [dict(t, status="planned", line=None) if t["id"] == "qualitative-participatory" else t
                                for t in planned["catalogue"]]
        self.assertIn("flujo planificado", run(planned, lang="es")["html"])
        self.assertIn("Coincidencia 100/100", html)

    def test_every_value_is_escaped(self) -> None:
        html = run(view())["html"]
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_agreed_and_stale(self) -> None:
        html = run(view(agreed="observational-measurement", agreed_variant="observational", agreed_by="op",
                        agreed_stale=True), lang="es")["html"]
        self.assertIn("Acordado: Estudio observacional y de medición (Estudio observacional), por op", html)
        self.assertIn("La idea cambió después de acordar el tipo", html)

    def test_no_accepted_idea_offers_phase_two(self) -> None:
        empty = {"catalogue": registry.load(), "plausibility": None, "decision": None, "line": "experimental"}
        out = run(empty, steps=[{"action": "go-plausibility"}])
        self.assertIn("There is no accepted idea yet", out["html"])
        self.assertIn(["tab", "pipeline"], out["calls"])


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class PanelActionTests(unittest.TestCase):
    def test_discuss_types_paper_type_without_running(self) -> None:
        out = run(view(), steps=[{"action": "discuss"}])
        self.assertIn(["send", "/paper-type", False, "slash"], out["calls"])

    def test_agree_needs_a_name_then_posts_the_choice(self) -> None:
        steps = [{"action": "agree-open", "type": "observational-measurement"},
                 {"action": "agree-confirm", "type": "observational-measurement"}]
        out = run(view(), steps=steps)
        self.assertFalse([c for c in out["calls"] if c[0] == "fetch" and c[1] == "/api/paper-type/agree"])
        self.assertIn("Write your name before agreeing", out["rendered"])
        steps = [{"action": "agree-open", "type": "observational-measurement"},
                 {"action": "agree-confirm", "type": "observational-measurement",
                  "values": {"ptBy": "Juli", "ptVariant": "observational", "ptRationale": "own survey"}}]
        out = run(view(), steps=steps, responses={"/api/paper-type/agree": {"status": 200, "body": {
            "ok": True, "layout": "planned"}}})
        posted = [c for c in out["calls"] if c[0] == "fetch" and c[1] == "/api/paper-type/agree"]
        self.assertEqual(posted[0][2], {"type": "observational-measurement", "variant": "observational",
                                        "by": "Juli", "rationale": "own survey"})

    def test_a_switch_names_the_kind_set_command(self) -> None:
        steps = [{"action": "agree-open", "type": "review"},
                 {"action": "agree-confirm", "type": "review", "values": {"ptBy": "Ana"}}]
        out = run(view(), steps=steps, responses={"/api/paper-type/agree": {"status": 200, "body": {
            "ok": True, "layout": "switch:review"}}})
        self.assertIn('smith kind set review --by &quot;Ana&quot; moves this workspace to it', out["rendered"])
        self.assertIn("smith init --kind review", out["rendered"])

    def test_a_switch_to_the_observational_line_names_its_kind_set_command(self) -> None:
        steps = [{"action": "agree-open", "type": "observational-measurement"},
                 {"action": "agree-confirm", "type": "observational-measurement",
                  "values": {"ptBy": "Juli", "ptVariant": "observational"}}]
        out = run(view(), steps=steps, responses={"/api/paper-type/agree": {"status": 200, "body": {
            "ok": True, "layout": "switch:observational-measurement"}}})
        self.assertIn('smith kind set observational-measurement --by &quot;Juli&quot; moves this workspace to it',
                      out["rendered"])
        self.assertIn("smith init --kind observational-measurement", out["rendered"])

    def test_agree_form_offers_the_family_variants(self) -> None:
        out = run(view(), steps=[{"action": "agree-open", "type": "observational-measurement"}])
        for variant in ("observational", "diagnostic-validation", "measurement-instrument"):
            self.assertIn(f'value="{variant}"', out["rendered"])


class PageWiringTests(unittest.TestCase):
    def test_the_tab_sits_before_concept_map_and_model(self) -> None:
        self.assertLess(PAGE.index("navigateTab('papertype')"), PAGE.index("navigateTab('modelo')"))
        self.assertIn('id="pane-papertype"', PAGE)
        self.assertIn('id="paperTypePanel"', PAGE)
        self.assertIn("window.refreshPaperTypePanel?.()", PAGE)
        self.assertIn('src="./paper-type-panel.js?v=', PAGE)


if __name__ == "__main__":
    unittest.main()
