"""The Review pane (paper-type-lines S6, T6b), run under node with the real
i18n runtime: every section of `GET /api/review` drawn with escaped values in
English and Spanish, an unreadable section drawn as unavailable while the rest
render, kappa's not-computable state stated, the PRISMA figure embedded through
`/api/artifact`, and the 27-item checklist fetched only on the operator's click."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from skills._core.command_center import server
from papersmith.core import init as init_module
from tests.test_review_view import build_review

STATIC = Path(server.__file__).resolve().parent / "static"

HARNESS = r"""
const fs = require('fs');
const store = {};
const listeners = {};
const els = {};
function el(id) { return els[id] || (els[id] = { id, value: '', innerHTML: '' }); }
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
global.fetch = async (url) => {
  calls.push(url);
  const r = (input.responses || {})[url] || { status: 200, body: input.view };
  return { ok: r.status < 400, status: r.status, json: async () => r.body };
};
(async () => {
  const out = { html: window.ReviewPanel.html(input.view), snapshots: [] };
  window.ReviewPanel.render(input.view);
  out.before = calls.slice();
  for (const step of input.steps || []) {
    if (step.lang) window.i18n.setLanguage(step.lang);
    if (step.action) await window.ReviewPanel.act(step.action);
    await new Promise((r) => setTimeout(r, 5));
    out.snapshots.push(el('reviewPanel').innerHTML);
  }
  out.calls = calls;
  out.rendered = el('reviewPanel').innerHTML;
  console.log(JSON.stringify(out));
})();
"""


def run(view: dict, lang: str = "en", steps=(), responses=None) -> dict:
    files = [str(STATIC / "i18n" / "en.js"), str(STATIC / "i18n" / "es.js"), str(STATIC / "i18n.js"),
             str(STATIC / "review-panel.js")]
    done = subprocess.run(["node", "-e", HARNESS, *files], capture_output=True, text=True, check=True,
                          input=json.dumps({"view": view, "lang": lang, "steps": list(steps),
                                            "responses": responses or {}}),
                          cwd=tempfile.gettempdir())
    return json.loads(done.stdout)


@unittest.skipUnless(shutil.which("node"), "node is required to run the panel")
class ReviewPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        holder = tempfile.TemporaryDirectory(prefix="review-panel-", ignore_cleanup_errors=True)
        cls.addClassCleanup(holder.cleanup)
        root = Path(holder.name).resolve() / "ws"
        init_module.initialize(root, tools=("claude",), run_npm=False, run_env=False, kind="review")
        build_review(root)
        client = TestClient(server.create_app(root))
        cls.view = client.get("/api/review").json()
        cls.checklist = client.get("/api/review/checklist").json()
        assert cls.view["protocol"]["available"] and cls.checklist["available"], (cls.view, cls.checklist)

    def test_every_section_is_drawn_in_english(self) -> None:
        out = run(self.view)["html"]
        for title in ("Protocol and registration", "Search log", "Screening progress", "PRISMA 2020 flow",
                      "Extraction table", "Risk of bias (quality appraisal)", "Sign-offs",
                      "PRISMA 2020 checklist (27 items)"):
            with self.subTest(title=title):
                self.assertIn(f"<h3>{title}</h3>", out)
        # Protocol and registration.
        self.assertIn("Graph neural networks in drug discovery: a systematic review", out)
        self.assertIn("Approved by Operator on", out)
        self.assertIn("<strong>RQ2</strong> Which datasets &amp; benchmarks are reused?", out)
        self.assertIn("`review-registration` declaration of /paper-writing; checklist item 24", out)
        # Search log.
        self.assertIn("<td>graph neural network drug discovery</td>", out)
        self.assertIn("3 record(s) identified, 1 marked as duplicates, 2 unique.", out)
        self.assertIn("Protocol sources not searched yet: crossref", out)
        # Screening: totals, pending per reviewer, the conflict, kappa.
        self.assertIn("<h4>Title and abstract</h4>", out)
        self.assertIn("Pending per reviewer: agent: 0, operator: 0", out)
        self.assertIn("<td>R0002</td><td>Graph kernels revisited</td><td>agent: include; operator: exclude</td>", out)
        self.assertIn("Cohen&#39;s kappa: 0", out)
        self.assertIn("Cohen&#39;s kappa: 1 (raw agreement 1, 1 shared record(s)).", out)
        # PRISMA: counts and the figure through /api/artifact.
        self.assertIn("<td>Studies included</td><td>1</td>", out)
        self.assertRegex(out, r'<img alt="PRISMA 2020 flow diagram" src="/api/artifact\?path=paper%2FFigures%2Fprisma-flow\.svg&amp;v=\d+">')
        self.assertIn("matches the records.", out)
        # Extraction table: the protocol's fields as columns, quote and page per value.
        self.assertIn("<th>architecture</th><th>datasets</th>", out)
        self.assertIn("Tox21, QM9<span class=\"rv-quote\">p. 5</span>", out)
        # Risk of bias: the score against the threshold, never invented domains.
        self.assertIn("Exclusion threshold of the protocol: 1.5", out)
        self.assertIn("<td>1 / 2</td><td><span class=\"rv-error\">below</span></td>", out)
        self.assertIn("defines no separate risk-of-bias domains", out)
        # Sign-offs.
        self.assertIn("Screening (G-SCREENING)</strong>: <span class=\"rv-warn\">not signed yet", out)

    def test_values_are_escaped(self) -> None:
        out = run(self.view)["html"]
        self.assertIn("GCN &lt;b&gt;", out)
        self.assertIn("We use a &lt;b&gt;graph&lt;/b&gt; convolution", out)
        self.assertNotIn("<b>", out)

    def test_every_section_is_drawn_in_spanish(self) -> None:
        out = run(self.view, "es")["html"]
        for title in ("Protocolo y registro", "Registro de búsquedas", "Avance del cribado", "Flujo PRISMA 2020",
                      "Tabla de extracción", "Riesgo de sesgo (evaluación de calidad)", "Firmas",
                      "Lista de verificación PRISMA 2020 (27 ítems)"):
            with self.subTest(title=title):
                self.assertIn(f"<h3>{title}</h3>", out)
        for english in ("Search log", "Screening progress", "Pending per reviewer", "Studies included", "below</span>"):
            with self.subTest(english=english):
                self.assertNotIn(english, out)
        self.assertIn("Kappa de Cohen: 0", out)
        self.assertIn("agent: incluir; operator: excluir", out)
        self.assertIn("por debajo", out)
        self.assertIn("Comprobar los 27 ítems", out)

    def test_an_unreadable_section_is_unavailable_and_the_rest_render(self) -> None:
        view = {**self.view, "screening": {"available": False, "code": "RECORDS_CORRUPT",
                                           "message": "review/screening.jsonl:1 is not JSON <x>"}}
        out = run(view)["html"]
        section = re.search(r'data-review-section="screening">(.*?)</section>', out, re.S).group(1)
        self.assertIn('role="alert">Unavailable (RECORDS_CORRUPT): review/screening.jsonl:1 is not JSON &lt;x&gt;', section)
        self.assertIn("<h3>Extraction table</h3>", out)
        self.assertIn("Approved by Operator", out)

    def test_kappa_with_one_reviewer_says_why_it_is_not_computable(self) -> None:
        screening = json.loads(json.dumps(self.view["screening"]))
        screening["stages"][1]["kappa"] = {"value": None, "code": "REVIEWERS_AMBIGUOUS", "records": 0,
                                           "agreement": None,
                                           "message": "kappa compares two reviewers; found agent (use --reviewers a,b)"}
        out = run({**self.view, "screening": screening})["html"]
        self.assertIn('<p class="rv-warn">Kappa not computable: kappa compares two reviewers; found agent', out)

    def test_the_review_cli_fallback_is_named(self) -> None:
        out = run({**self.view, "cli_warning": "SyntaxError at /ws/review_cli.py"})["html"]
        self.assertIn("did not load (SyntaxError at /ws/review_cli.py)", out)

    def test_no_flow_figure_names_the_command(self) -> None:
        prisma = {**self.view["prisma"], "flow": {"path": "paper/Figures/prisma-flow.svg", "exists": False,
                                                  "mtime": None}}
        out = run({**self.view, "prisma": prisma})["html"]
        self.assertNotIn("<img", out)
        self.assertIn("`review_cli.py flow` writes paper/Figures/prisma-flow.svg", out)

    def test_the_checklist_loads_only_on_the_operators_click(self) -> None:
        out = run(self.view, "es", steps=[{"action": "checklist"}],
                  responses={"/api/review/checklist": {"status": 200, "body": self.checklist}})
        self.assertNotIn("/api/review/checklist", out["before"])
        self.assertIn('data-review-action="checklist"', out["html"])
        self.assertNotIn("Criterios de elegibilidad", out["html"])
        self.assertEqual(out["calls"].count("/api/review/checklist"), 1)
        rendered = out["rendered"]
        self.assertEqual(len(re.findall(r"<tr><td>\d+</td>", rendered)), 27)
        self.assertIn("<td>5</td><td>Criterios de elegibilidad</td>", rendered)
        self.assertIn("texto de methods.m-eligibility", rendered)
        self.assertIn("declaración review-registration", rendered)
        self.assertIn("0 de 27 ítems cumplidos; 27 pendientes.", rendered)
        self.assertIn("paper/main.tex aún no tiene estructura", rendered)
        self.assertIn("Comprobar de nuevo", rendered)

    def test_a_language_switch_repaints_the_pane(self) -> None:
        out = run(self.view, "en", steps=[{"lang": "es"}])
        self.assertIn("<h3>Avance del cribado</h3>", out["rendered"])

    def test_an_experimental_workspace_reads_as_not_a_review(self) -> None:
        refused = {"ok": False, "code": "NOT_A_REVIEW_WORKSPACE", "paper_kind": "experimental", "error": "x"}
        out = run(self.view, steps=[{"action": "refresh"}],
                  responses={"/api/review": {"status": 409, "body": refused}})
        self.assertIn("This workspace is not a review (paper line: experimental)", out["rendered"])


if __name__ == "__main__":
    unittest.main()
