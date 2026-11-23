"""The Study pane (paper-type-lines S8, T8-O5), run under node with the real
i18n runtime: every section of `GET /api/study` drawn with escaped values in
English and Spanish, an unreadable section drawn as unavailable while the rest
render, the participant-flow figure embedded through `/api/artifact`, a
non-empirical workspace's 409 stated, and the variant's checklist fetched only
on the operator's click ("no checklist data yet" when no guideline applies)."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from skills._core.command_center import server
from tests.test_study_view import KIND, build_study
from papersmith.core import init as init_module

STATIC = Path(server.__file__).resolve().parent / "static"
NODE = shutil.which("node", path="/usr/bin") or shutil.which("node")

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
  const out = { html: window.StudyPanel.html(input.view), snapshots: [] };
  window.StudyPanel.render(input.view);
  out.before = calls.slice();
  for (const step of input.steps || []) {
    if (step.lang) window.i18n.setLanguage(step.lang);
    if (step.action) await window.StudyPanel.act(step.action);
    await new Promise((r) => setTimeout(r, 5));
    out.snapshots.push(el('studyPanel').innerHTML);
  }
  out.calls = calls;
  out.rendered = el('studyPanel').innerHTML;
  console.log(JSON.stringify(out));
})();
"""


def run(view: dict, lang: str = "en", steps=(), responses=None) -> dict:
    files = [str(STATIC / "i18n" / "en.js"), str(STATIC / "i18n" / "es.js"), str(STATIC / "i18n.js"),
             str(STATIC / "study-panel.js")]
    done = subprocess.run([NODE, "-e", HARNESS, *files], capture_output=True, text=True, check=True,
                          input=json.dumps({"view": view, "lang": lang, "steps": list(steps),
                                            "responses": responses or {}}),
                          cwd=tempfile.gettempdir())
    return json.loads(done.stdout)


@unittest.skipUnless(NODE, "node is required to run the panel")
class StudyPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        holder = tempfile.TemporaryDirectory(prefix="study-panel-", ignore_cleanup_errors=True)
        cls.addClassCleanup(holder.cleanup)
        root = Path(holder.name).resolve() / "ws"
        init_module.initialize(root, tools=("claude",), run_npm=False, run_env=False, kind=KIND)
        build_study(root)
        client = TestClient(server.create_app(root))
        cls.view = client.get("/api/study").json()
        cls.checklist = client.get("/api/study/checklist").json()
        assert cls.view["protocol"]["available"] and cls.checklist["available"], (cls.view, cls.checklist)

    def test_every_section_is_drawn_in_english(self) -> None:
        out = run(self.view)["html"]
        for title in ("Protocol and lock", "Ethics approval", "Study registration", "Own data", "Analysis log",
                      "Participant flow", "Reporting checklist"):
            with self.subTest(title=title):
                self.assertIn(f"<h3>{title}</h3>", out)
        # Protocol and lock.
        self.assertIn("Gate G-STUDY-PROTOCOL passed: protocol/study-protocol-walking-v01.md approved by Ana Ruiz on", out)
        self.assertIn("No amendment recorded.", out)
        # Ethics and registration.
        self.assertIn("Approved by Ethics Board &lt;UN&gt;, code EB-12, on 2026-01-10; consent: written.", out)
        self.assertIn("Retrospective: registered after the first enrolment.", out)
        self.assertIn("Bound to the current protocol lock.", out)
        # Own data: statement, dictionary, QC domain checks, de-identification.
        self.assertIn("Data use (by Ana Ruiz,", out)
        self.assertIn("Consented &lt;use&gt; only", out)
        self.assertIn("Dictionary datasets/cohort/dictionary.json: 4 column(s), 1 described; PII columns: name.", out)
        self.assertIn("<td>out-of-range</td><td>age</td><td>warn</td><td>1</td>", out)
        self.assertIn("De-identified by Ana Ruiz on", out)
        # Analysis log.
        self.assertIn("Confirmatory: 1 · Exploratory: 1 · Failed runs: 1", out)
        self.assertIn("<td>A0002</td>", out)
        self.assertIn('<span class="rv-ok">confirmatory</span>', out)
        self.assertIn('<span class="rv-error">1</span>', out)
        # Participant flow: counts, sign-off, the figure through /api/artifact.
        self.assertIn("The counts are valid (strobe).", out)
        self.assertIn("Signed off by Ana Ruiz on", out)
        self.assertIn("Declined &lt;to&gt; take part (50)", out)
        self.assertRegex(out, r'<img alt="Participant flow diagram" src="/api/artifact\?path=paper%2FFigures%2Fparticipant-flow\.svg&amp;v=\d+">')
        # Reporting: the agreed variant and its guideline.
        # The variant's name is catalogue data (another unit may reword it): only the frame is pinned.
        self.assertRegex(out, r"Agreed variant: [^<]+ \(observational-measurement\); reporting guideline: strobe\.")

    def test_no_value_is_inserted_unescaped(self) -> None:
        out = run(self.view)["html"]
        for raw in ("<UN>", "<use>", "<to>"):
            with self.subTest(raw=raw):
                self.assertNotIn(raw, out)

    def test_spanish(self) -> None:
        out = run(self.view, lang="es")["html"]
        for title in ("Protocolo y bloqueo", "Aprobación ética", "Registro del estudio", "Datos propios",
                      "Bitácora de análisis", "Flujo de participantes", "Lista de verificación de reporte"):
            with self.subTest(title=title):
                self.assertIn(f"<h3>{title}</h3>", out)
        self.assertIn("Ejecutar la lista de verificación", out)
        self.assertIn("Retrospectivo: registrado después de la primera inclusión.", out)
        self.assertNotIn("Protocol and lock", out)

    def test_the_checklist_is_fetched_only_on_click(self) -> None:
        out = run(self.view, steps=[{"action": "checklist"}],
                  responses={"/api/study/checklist": {"status": 200, "body": self.checklist}})
        self.assertEqual(out["before"], [])
        self.assertIn("Run the checklist", out["html"])
        self.assertEqual(out["calls"], ["/api/study/checklist"])
        self.assertIn("Items: 22", out["rendered"])
        self.assertIn("Run it again", out["rendered"])
        self.assertIn("<td>1</td>", out["rendered"])

    def test_without_a_guideline_there_is_no_checklist_data_yet(self) -> None:
        body = {"available": True, "type": KIND, "variant": None, "variant_name": None, "guideline": None,
                "code": "NO_CHECKLIST_DATA", "reason": "variant-not-agreed"}
        view = dict(self.view, reporting=dict(body))
        out = run(view, steps=[{"action": "checklist"}], responses={"/api/study/checklist": {"status": 200, "body": body}})
        self.assertIn("No checklist data yet. Agree a variant of the type on the Paper Type tab.", out["html"])
        self.assertIn("No checklist data yet.", out["rendered"])
        self.assertNotIn("Items:", out["rendered"])

    def test_an_unreadable_section_is_drawn_as_unavailable_and_the_rest_render(self) -> None:
        view = dict(self.view, data={"available": False, "code": "UNREADABLE", "message": "registry <broken>"},
                    warnings=["records did not load: <x>"])
        out = run(view)["html"]
        self.assertIn("Unavailable (UNREADABLE): registry &lt;broken&gt;", out)
        self.assertIn("A study module did not load: records did not load: &lt;x&gt;", out)
        self.assertIn("<h3>Analysis log</h3>", out)
        self.assertIn("The counts are valid (strobe).", out)

    def test_a_non_empirical_workspace_says_so(self) -> None:
        refused = {"ok": False, "code": "NOT_A_STUDY_WORKSPACE", "paper_kind": "experimental", "error": "x"}
        out = run(self.view, steps=[{"action": "refresh"}], responses={"/api/study": {"status": 409, "body": refused}})
        self.assertIn("This workspace is not an empirical study (paper line: experimental)", out["rendered"])

    def test_a_language_switch_repaints(self) -> None:
        out = run(self.view, steps=[{"lang": "es"}])
        self.assertIn("Protocolo y bloqueo", out["snapshots"][0])


if __name__ == "__main__":
    unittest.main()
