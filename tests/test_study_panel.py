"""The Study pane (paper-type-lines S8, T8-O5), run under node with the real
i18n runtime: every section of `GET /api/study` drawn with escaped values in
English and Spanish, an unreadable section drawn as unavailable while the rest
render, the participant-flow figure embedded through `/api/artifact`, a
non-empirical workspace's 409 stated, and the variant's checklist fetched only
on the operator's click ("no checklist data yet" when no guideline applies).
A hardware workspace adds the measurement sections (instruments, data files,
uncertainty budgets, agreement) and a second guideline, gum-reporting, run from
its own button. A data-resource workspace adds the deposit section (repository,
identifier with its scheme, licence, landing page, version, date, who recorded
it, current or stale with the reasons). An experiment-intervention workspace
adds the allocation section (method, block size, strata, concealment, the
list's path, rows and short sha256, the protocol revision, current, stale with
the reasons, or corrupt), the list itself never shown. A qualitative-participatory
workspace adds the transcripts (codes, kinds, consent, de-identification,
totals), codebook and themes (versions, the theme sign-off) and consensus
(panel, plan, agreement per round and item, MICMAC ranking and quadrant)
sections, never a transcript's text, a comment or an individual rating."""

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
from tests.test_study_view_measurement import RAW, agree as agree_type, measurement_records
from tests.test_study_view_deposit import DOI, deposit as record_deposit, own as own_resource
from tests.test_study_view import lock as lock_protocol
from tests.test_study_view_allocation import CONCEALMENT, TOKENS, allocate
from tests.test_study_view_qualitative import TOKENS as QUAL_TOKENS, codebook, consensus_records, signoff, \
    transcripts as register_transcripts
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
    if (step.action) await window.StudyPanel.act(step.action, step.guideline);
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


@unittest.skipUnless(NODE, "node is required to run the panel")
class MeasurementPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        holder = tempfile.TemporaryDirectory(prefix="study-panel-hw-", ignore_cleanup_errors=True)
        cls.addClassCleanup(holder.cleanup)
        root = Path(holder.name).resolve() / "ws"
        init_module.initialize(root, tools=("claude",), run_npm=False, run_env=False, kind="hardware")
        measurement_records(root)
        agree_type(root, None, "hardware")
        client = TestClient(server.create_app(root))
        cls.view = client.get("/api/study").json()
        cls.gum = client.get("/api/study/checklist?guideline=gum-reporting").json()
        assert cls.view["uncertainty"]["available"] and cls.gum["available"], (cls.view, cls.gum)

    def test_the_measurement_sections_in_english(self) -> None:
        out = run(self.view)["html"]
        for title in ("Instruments", "Measurement data files", "Uncertainty budgets",
                      "Agreement with a reference device"):
            with self.subTest(title=title):
                self.assertIn(f"<h3>{title}</h3>", out)
        self.assertIn("<td>caliper-1</td><td>Mitutoyo &lt;500&gt;</td><td>S-caliper-1</td><td>0.01 mm</td>"
                      "<td>0.02 mm (normal, k = 2)</td><td>CERT &lt;9&gt;</td><td>2026-01-10</td><td>2099-01-10</td>"
                      '<td><span class="rv-ok">current</span></td>', out)
        self.assertIn("<td>data/length.csv</td><td>length</td><td>mm</td><td>caliper-1</td><td>4</td>"
                      "<td>temperature=20 C</td>", out)
        self.assertIn("its readings are never shown here", out)
        self.assertIn("<h4>length (temperature=20 C)</h4>", out)
        self.assertRegex(out, r"n = 4, mean = [0-9.]+ mm; combined standard uncertainty u_c = [0-9.e-]+ mm; "
                              r"effective degrees of freedom [0-9.]+; coverage factor k = [0-9.]+ \(Student t, level "
                              r"0\.95, \d+ degrees of freedom\); expanded uncertainty U = [0-9.e-]+ mm\.")
        self.assertIn("<td>repeatability</td><td>A</td><td>replicates</td>", out)
        self.assertIn("<td>resolution</td><td>B</td>", out)
        self.assertIn("Calibration current (due 2099-01-10, checked on", out)
        self.assertIn("<td>data/device.csv (device-1)</td><td>data/reference.csv (ref-1)</td><td>force [N]</td>"
                      "<td>4</td>", out)
        self.assertRegex(out, r"<td>-?[0-9.e-]+ to -?[0-9.e-]+</td><td>-?[0-9.e-]+</td><td><span class=\"rv-ok\">current</span>")
        self.assertIn("Agreed type: hardware; reporting guideline: hardwarex.", out)
        self.assertIn("gum-reporting also applies: how the uncertainty is reported (GUM clause 7).", out)
        self.assertIn('data-study-guideline="gum-reporting"', out)
        self.assertIn("Run gum-reporting", out)

    def test_no_reading_and_no_unescaped_value(self) -> None:
        out = run(self.view)["html"]
        for raw in (*RAW, "<500>", "<9>"):
            with self.subTest(raw=raw):
                self.assertNotIn(raw, out)

    def test_stale_reasons_and_a_past_due_override(self) -> None:
        view = json.loads(json.dumps(self.view))
        budget = view["uncertainty"]["budgets"][0]
        budget.update(state="stale", reasons=["input-changed", "instrument-changed"])
        budget["calibration"].update(state="past-due", override={"by": "Ana Ruiz", "at": "2026-11-20",
                                                                 "reason": "Checked against a <gauge> block"})
        view["agreement"]["analyses"][0].update(state="stale", reasons=["device-changed"])
        view["measurements"]["files"][0]["state"] = "changed"
        out = run(view)["html"]
        self.assertIn("stale: an input file changed, the instrument record changed", out)
        self.assertIn("Past-due calibration accepted by Ana Ruiz on 2026-11-20: Checked against a &lt;gauge&gt; block",
                      out)
        self.assertIn("stale: the device file changed", out)
        self.assertIn("changed since its registration", out)
        es = run(view, lang="es")["html"]
        self.assertIn("desactualizado: cambió un archivo de entrada, cambió el registro del instrumento", es)
        self.assertIn("Calibración vencida aceptada por Ana Ruiz el 2026-11-20", es)

    def test_spanish(self) -> None:
        out = run(self.view, lang="es")["html"]
        for title in ("Instrumentos", "Archivos de datos de medición", "Presupuestos de incertidumbre",
                      "Concordancia con un dispositivo de referencia"):
            with self.subTest(title=title):
                self.assertIn(f"<h3>{title}</h3>", out)
        self.assertIn("incertidumbre expandida U =", out)
        self.assertIn("<td>repetibilidad</td>", out)
        self.assertIn("Tipo acordado: hardware; guía de reporte: hardwarex.", out)
        self.assertIn("También aplica gum-reporting", out)
        self.assertNotIn("Uncertainty budgets", out)

    def test_the_second_guideline_is_fetched_only_on_its_click(self) -> None:
        url = "/api/study/checklist?guideline=gum-reporting"
        out = run(self.view, steps=[{"action": "checklist", "guideline": "gum-reporting"}],
                  responses={url: {"status": 200, "body": self.gum}})
        self.assertEqual(out["before"], [])
        self.assertEqual(out["calls"], [url])
        self.assertIn("Items: 18", out["rendered"])
        self.assertIn("Run gum-reporting again", out["rendered"])
        self.assertIn(">Run the checklist<", out["rendered"])

    def test_a_view_without_measurement_sections_draws_none(self) -> None:
        view = {key: value for key, value in self.view.items()
                if key not in ("instruments", "measurements", "uncertainty", "agreement")}
        out = run(view)["html"]
        self.assertNotIn('data-study-section="instruments"', out)
        self.assertNotIn("<h3>Uncertainty budgets</h3>", out)


@unittest.skipUnless(NODE, "node is required to run the panel")
class DepositPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        holder = tempfile.TemporaryDirectory(prefix="study-panel-dr-", ignore_cleanup_errors=True)
        cls.addClassCleanup(holder.cleanup)
        root = Path(holder.name).resolve() / "ws"
        init_module.initialize(root, tools=("claude",), run_npm=False, run_env=False, kind="data-resource")
        own_resource(root, "notes")
        record_deposit(root, "notes", "--url", "https://zenodo.org/records/7654321", "--version", "v1", "--date",
                       "2026-11-20")
        own_resource(root, "sensors")
        cls.view = TestClient(server.create_app(root)).get("/api/study").json()
        assert cls.view["deposit"]["available"], cls.view["deposit"]

    def test_the_deposit_section_in_english(self) -> None:
        out = run(self.view)["html"]
        self.assertIn("<h3>Deposit</h3>", out)
        self.assertIn("<h4>notes</h4>", out)
        self.assertIn(f"<td>Zenodo &lt;EU&gt;</td><td>{DOI} (doi)</td><td>CC-BY-4.0</td>", out)
        self.assertIn('<a href="https://zenodo.org/records/7654321" target="_blank" rel="noopener">', out)
        self.assertIn("<td>v1</td><td>2026-11-20</td><td>data/notes.csv</td>", out)
        self.assertIn('<p class="rv-ok">Current: every registered file is the one deposited.</p>', out)
        self.assertRegex(out, r"Recorded by Ana Ruiz on \d{4}-\d{2}-\d{2}; 0 earlier record\(s\)\.")
        self.assertIn("<h4>sensors</h4>", out)
        self.assertIn("No deposit recorded yet (datasets_cli.py deposit --by &lt;name&gt;).", out)
        self.assertNotIn("Zenodo <EU>", out)

    def test_a_stale_deposit_names_its_reasons(self) -> None:
        view = json.loads(json.dumps(self.view))
        view["deposit"]["datasets"][0].update(current=False, stale=[
            {"reason": "file-changed", "file": "data/notes.csv"}, {"reason": "file-added", "file": "data/<x>.csv"}])
        out = run(view)["html"]
        self.assertIn("Stale: data/notes.csv changed since the deposit, data/&lt;x&gt;.csv registered after the "
                      "deposit. Deposit the new version and record it again.", out)
        es = run(view, lang="es")["html"]
        self.assertIn("Desactualizado: data/notes.csv cambió desde el depósito", es)

    def test_spanish(self) -> None:
        out = run(self.view, lang="es")["html"]
        self.assertIn("<h3>Depósito</h3>", out)
        self.assertIn("Vigente: cada archivo registrado es el que se depositó.", out)
        self.assertIn("<th>Repositorio</th>", out)
        self.assertNotIn("<h3>Deposit</h3>", out)

    def test_an_unavailable_deposit_and_a_view_without_one(self) -> None:
        view = json.loads(json.dumps(self.view))
        view["deposit"] = {"available": False, "code": "UNREADABLE", "message": "bad <registry>"}
        out = run(view)["html"]
        self.assertIn('data-study-section="deposit"', out)
        self.assertIn("bad &lt;registry&gt;", out)
        self.assertIn('data-study-section="data"', out)
        without = {key: value for key, value in self.view.items() if key != "deposit"}
        self.assertNotIn('data-study-section="deposit"', run(without)["html"])


@unittest.skipUnless(NODE, "node is required to run the panel")
class AllocationPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        holder = tempfile.TemporaryDirectory(prefix="study-panel-ei-", ignore_cleanup_errors=True)
        cls.addClassCleanup(holder.cleanup)
        root = Path(holder.name).resolve() / "ws"
        init_module.initialize(root, tools=("claude",), run_npm=False, run_env=False, kind="experiment-intervention")
        lock_protocol(root)
        allocate(root, "--note", "Pharmacy <holds> the key")
        cls.view = TestClient(server.create_app(root)).get("/api/study").json()
        assert cls.view["allocation"]["available"], cls.view["allocation"]

    def test_the_allocation_section_in_english(self) -> None:
        out = run(self.view)["html"]
        self.assertIn('data-study-section="allocation"', out)
        self.assertIn("<h3>Allocation</h3>", out)
        self.assertIn("The allocation list is the operator&#39;s and stays concealed", out)
        self.assertIn("study_cli.py allocation record --by &lt;name&gt;", out)
        self.assertIn("the assistant never generates, reads out or alters it", out)
        self.assertIn('<p class="rv-ok">Gate G-ALLOCATION current: the list is the one recorded and the record is '
                      "bound to the current protocol lock (protocol/study-protocol-walking-v01.md).</p>", out)
        sha = self.view["allocation"]["sha256"]
        self.assertIn(f"<td>Stratified</td><td>4</td><td>site, sex</td><td>{CONCEALMENT.replace('<', '&lt;').replace('>', '&gt;')}"
                      f"</td><td>allocation/sequence.csv</td><td>4</td><td>{sha}</td>"
                      "<td>protocol/study-protocol-walking-v01.md</td>", out)
        self.assertIn("Operator&#39;s note: Pharmacy &lt;holds&gt; the key", out)
        self.assertRegex(out, r"Recorded by Ana Ruiz on \d{4}-\d{2}-\d{2}\S*; 1 record\(s\) in total\.")
        self.assertNotIn("Pharmacy <holds>", out)
        for token in TOKENS:
            self.assertNotIn(token, out)
        self.assertLess(out.index('data-study-section="registration"'), out.index('data-study-section="allocation"'))

    def test_every_stale_reason_is_named(self) -> None:
        view = json.loads(json.dumps(self.view))
        view["allocation"].update(state="stale", current=False, reasons=[
            "file-changed", "file-missing", "file-unreadable", "file-outside", "protocol-amended",
            "protocol-changed"])
        out = run(view)["html"]
        self.assertIn("Stale: allocation/sequence.csv changed since it was recorded, allocation/sequence.csv is "
                      "missing, allocation/sequence.csv cannot be read, allocation/sequence.csv is outside the "
                      "workspace, the protocol was amended since (the record "
                      "covers protocol/study-protocol-walking-v01.md), the protocol is not current. Record the "
                      "allocation again against the current list and lock", out)
        es = run(view, lang="es")["html"]
        self.assertIn("Desactualizada: allocation/sequence.csv cambió desde que se registró", es)
        self.assertIn("el protocolo no está vigente", es)
        self.assertIn("allocation/sequence.csv está fuera del espacio de trabajo", es)

    def test_absent_and_corrupt(self) -> None:
        absent = run({**self.view, "allocation": {"available": True, "gate": "G-ALLOCATION", "state": "absent",
                                                  "path": "study/allocation.json"}})["html"]
        self.assertIn("No allocation recorded yet (gate G-ALLOCATION): study_cli.py allocation record --by &lt;name&gt; "
                      "--file &lt;list&gt; --method &lt;method&gt; --concealment &lt;how&gt;.", absent)
        self.assertNotIn("<th>Method</th>", absent)
        corrupt = run({**self.view, "allocation": {"available": True, "gate": "G-ALLOCATION", "state": "corrupt",
                                                   "path": "study/allocation.json", "code": "ALLOCATION_CORRUPT",
                                                   "message": "bad <json>"}})["html"]
        self.assertIn('<p class="rv-error" role="alert">The allocation record study/allocation.json cannot be read: '
                      "bad &lt;json&gt;</p>", corrupt)
        self.assertIn('data-study-section="protocol"', corrupt)

    def test_spanish(self) -> None:
        out = run(self.view, lang="es")["html"]
        self.assertIn("<h3>Asignación</h3>", out)
        self.assertIn("La lista de asignación es del operador y permanece oculta", out)
        self.assertIn("<th>Ocultamiento</th>", out)
        self.assertIn("<td>Estratificada</td>", out)
        self.assertNotIn("<h3>Allocation</h3>", out)

    def test_an_unavailable_allocation_and_a_view_without_one(self) -> None:
        view = {**self.view, "allocation": {"available": False, "code": "STUDY_MODULE_UNAVAILABLE",
                                            "message": "records <gone>"}}
        out = run(view)["html"]
        self.assertIn('data-study-section="allocation"', out)
        self.assertIn("records &lt;gone&gt;", out)
        without = {key: value for key, value in self.view.items() if key != "allocation"}
        self.assertNotIn('data-study-section="allocation"', run(without)["html"])


@unittest.skipUnless(NODE, "node is required to run the panel")
class QualitativePanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        holder = tempfile.TemporaryDirectory(prefix="study-panel-qp-", ignore_cleanup_errors=True)
        cls.addClassCleanup(holder.cleanup)
        root = Path(holder.name).resolve() / "ws"
        init_module.initialize(root, tools=("claude",), run_npm=False, run_env=False, kind="qualitative-participatory")
        register_transcripts(root)
        codebook(root)
        signoff(root)
        consensus_records(root)
        cls.view = TestClient(server.create_app(root)).get("/api/study").json()
        for name in ("transcripts", "themes", "consensus"):
            assert cls.view[name]["available"], cls.view[name]

    def copy(self) -> dict:
        return json.loads(json.dumps(self.view))

    def test_the_transcripts_section_in_english(self) -> None:
        out = run(self.view)["html"]
        self.assertIn('data-study-section="transcripts"', out)
        self.assertIn("<h3>Transcripts</h3>", out)
        self.assertIn("qual_cli.py transcripts add --by &lt;name&gt; --file &lt;file&gt; --participant &lt;code&gt;", out)
        self.assertIn("the assistant never writes, edits or reads out a transcript and never invents or polishes a "
                      "quote", out)
        self.assertIn('<p class="rv-ok">Gate G-TRANSCRIPTS passed: every registered transcript holds the bytes it was '
                      "registered with.</p>", out)
        self.assertIn("<p>3 participant(s), 3 transcript registration(s), 0 stale.</p>", out)
        sha = self.view["transcripts"]["transcripts"][0]["sha256"]
        self.assertIn(f"<td>P01</td><td>Interview</td><td>data/p01.txt</td><td>{self.view['transcripts']['transcripts'][0]['characters']}</td>"
                      f"<td>{sha}</td><td>Written consent &lt;form C-12&gt;</td>"
                      "<td>Names and places replaced by codes</td><td>Ana Ruiz, ", out)
        self.assertIn("<td>P02</td><td>Focus group</td>", out)
        self.assertNotIn("<form C-12>", out)
        for token in QUAL_TOKENS:
            self.assertNotIn(token, out)

    def test_the_themes_section_in_english(self) -> None:
        out = run(self.view)["html"]
        self.assertIn("<h3>Codebook and themes</h3>", out)
        self.assertIn("the assistant may propose codes and themes, only the operator records a codebook version "
                      "(qual_cli.py codebook record --by &lt;name&gt; --file &lt;codebook&gt;) and signs the themes off "
                      "(qual_cli.py themes signoff --by &lt;name&gt; --file &lt;themes&gt;)", out)
        self.assertIn('<p class="rv-ok">Version 1 (analysis/codebook.md) is current: the file holds the bytes '
                      "recorded.</p>", out)
        sign = self.view["themes"]["signoff"]
        self.assertIn('<p class="rv-ok">Gate G-ANALYSIS passed: the operator&#39;s sign-off covers the current themes, '
                      "codebook and transcripts.</p>", out)
        self.assertIn(f"<td>analysis/themes.md</td><td>{sign['sha256']}</td><td>1</td><td>3</td><td>Luis Mora, ", out)
        self.assertIn("1 sign-off(s) in total.", out)

    def test_the_consensus_section_in_english(self) -> None:
        out = run(self.view)["html"]
        self.assertIn("<h3>Consensus rounds</h3>", out)
        for command in ("consensus_cli.py panel add --by &lt;name&gt;", "consensus_cli.py plan record --by &lt;name&gt;",
                        "consensus_cli.py round record --by &lt;name&gt;", "consensus_cli.py micmac compute --by &lt;name&gt;"):
            self.assertIn(command, out)
        self.assertIn("the assistant never enters or edits a rating", out)
        self.assertIn("never a comment or an individual rating", out)
        self.assertIn('<p class="rv-ok">Gate G-ROUNDS passed: the plan is current and its 2 round(s) are recorded and '
                      "current.</p>", out)
        self.assertIn("<p>4 member(s), by code.</p>", out)
        self.assertIn("<td>P01</td><td>nurse &lt;primary care&gt;</td>", out)
        self.assertIn("<td>2</td><td>75%</td><td>1 to 5</td><td>4</td><td>protocol/study-protocol-walking-v01.md</td>", out)
        self.assertIn("<h4>Round 1</h4>", out)
        self.assertIn("Current: 1 of 2 item(s) reached consensus.", out)
        self.assertIn('<td>I1</td><td>4</td><td>75% (3 of 4)</td><td>4</td><td>0.75 (3.5 to 4.25)</td>'
                      '<td><span class="rv-ok">yes</span></td><td>—</td>', out)
        self.assertIn('<td>I2</td><td>4</td><td>75% (3 of 4)</td><td>4</td><td>0.5 (3.75 to 4.25)</td>'
                      '<td><span class="rv-ok">yes</span></td><td>since round 1: agreement +50 points, median +1.5, '
                      "IQR -1; consensus before: no</td>", out)
        self.assertIn("Indirect influence at power 3 (raised until the ranking is stable); ranking stable: yes. "
                      "1 potential (P) entries counted as 4.", out)
        self.assertIn("<th>Influence rank (M^3)</th>", out)
        self.assertIn("<td>A</td><td>1</td><td>3</td><td>Influential</td><td>1</td><td>3</td><td>Influential</td>", out)
        self.assertIn("<td>B</td><td>2</td><td>1</td><td>Relay</td><td>2</td><td>2</td><td>Relay</td>", out)
        for token in QUAL_TOKENS:
            self.assertNotIn(token, out)
        order = [out.index(f'data-study-section="{name}"') for name in ("data", "transcripts", "themes", "consensus",
                                                                       "analysis")]
        self.assertEqual(order, sorted(order))

    def test_every_stale_reason_is_named(self) -> None:
        view = self.copy()
        view["transcripts"].update(state="stale", passed=False)
        view["transcripts"]["counts"]["stale"] = 1
        view["transcripts"]["transcripts"][0].update(state="stale", reasons=["file-changed", "file-outside"])
        view["themes"]["signoff"].update(state="stale", reasons=[
            "themes-file-missing", "codebook-changed", "codebook-stale", "transcript-changed", "transcript-added"])
        view["consensus"]["plan"].update(state="stale", reasons=["protocol-amended", "protocol-changed",
                                                                 "protocol-absent", "protocol-corrupt"])
        view["consensus"]["rounds"]["rounds"][1].update(state="stale", items=None, reasons=[
            "file-unreadable", "file-invalid", "plan-changed", "plan-stale", "plan-missing", "beyond-plan"])
        view["consensus"]["micmac"].update(state="stale", reasons=["file-missing"])
        out = run(view)["html"]
        self.assertIn("Gate G-TRANSCRIPTS open: 1 transcript(s) changed since their registration.", out)
        self.assertIn("Stale: data/p01.txt changed since it was recorded, data/p01.txt is outside the workspace", out)
        self.assertIn("Gate G-ANALYSIS open: the sign-off is stale (analysis/themes.md is missing, another codebook "
                      "version was recorded since, the codebook file changed or its record cannot be read, a "
                      "signed-off transcript was replaced or changed, a transcript was registered since).", out)
        self.assertIn("Stale: the protocol was amended since, the protocol is not current, no protocol lock is "
                      "recorded, the protocol lock cannot be read.", out)
        self.assertIn("Stale: data/round2.csv cannot be read, data/round2.csv no longer reads as a response file, the "
                      "plan was recorded again since, the plan covers an earlier protocol, the plan entry it was "
                      "recorded against is missing, the round lies beyond the planned rounds.", out)
        self.assertIn("The agreement cannot be computed: the response file no longer holds the recorded bytes.", out)
        self.assertIn("Stale: data/matrix.csv is missing.", out)
        es = run(view, lang="es")["html"]
        self.assertIn("Desactualizada: data/p01.txt cambió desde que se registró", es)
        self.assertIn("se registró otra versión del libro de códigos desde entonces", es)
        self.assertIn("la ronda está más allá de las rondas planeadas", es)

    def test_absent_states(self) -> None:
        view = {**self.view,
                "transcripts": {"available": True, "gate": "G-TRANSCRIPTS", "state": "absent", "passed": False,
                                "path": "study/transcripts.json", "transcripts": [], "counts": {}, "kinds": {},
                                "records": 0, "warnings": []},
                "themes": {"available": True, "gate": "G-ANALYSIS", "passed": False,
                           "codebook": {"state": "absent", "path": "study/codebook.json"},
                           "signoff": {"state": "absent", "path": "study/themes.json"}, "warnings": []},
                "consensus": {"available": True, "gate": "G-ROUNDS", "state": "absent", "passed": False,
                              "planned": None, "missing": [], "panel": {"state": "absent", "members": [], "size": 0},
                              "plan": {"state": "absent"}, "rounds": {"state": "absent", "rounds": []},
                              "micmac": {"state": "absent"}, "warnings": []}}
        out = run(view)["html"]
        self.assertIn("No transcript registered yet (gate G-TRANSCRIPTS): qual_cli.py transcripts add --by &lt;name&gt;", out)
        self.assertIn("No codebook version recorded yet: qual_cli.py codebook record --by &lt;name&gt;", out)
        self.assertIn("No theme sign-off recorded yet (gate G-ANALYSIS): qual_cli.py themes signoff --by &lt;name&gt;", out)
        self.assertIn("No consensus plan recorded yet (gate G-ROUNDS).", out)
        self.assertIn("No panel member registered yet: consensus_cli.py panel add --by &lt;name&gt;", out)
        self.assertIn("No round recorded yet: consensus_cli.py round record --by &lt;name&gt;", out)
        self.assertIn("No MICMAC analysis recorded (optional): consensus_cli.py micmac compute --by &lt;name&gt;", out)
        self.assertNotIn("<th>Participant</th>", out)

    def test_open_gate_with_missing_rounds(self) -> None:
        view = self.copy()
        view["consensus"].update(state="open", passed=False, missing=[2])
        out = run(view)["html"]
        self.assertIn('<p class="rv-warn">Gate G-ROUNDS open: 2 round(s) planned, not all recorded and current. '
                      "Rounds not recorded: 2.</p>", out)

    def test_corrupt_parts(self) -> None:
        view = {**self.view,
                "transcripts": {"available": True, "gate": "G-TRANSCRIPTS", "state": "corrupt", "passed": False,
                                "path": "study/transcripts.json", "code": "TRANSCRIPTS_CORRUPT", "message": "bad <json>"},
                "themes": {"available": True, "gate": "G-ANALYSIS", "passed": False,
                           "codebook": {"state": "corrupt", "path": "study/codebook.json", "code": "CODEBOOK_CORRUPT",
                                        "message": "cb <bad>"},
                           "signoff": {"state": "corrupt", "path": "study/themes.json", "code": "THEMES_CORRUPT",
                                       "message": "th <bad>"}, "warnings": []},
                "consensus": {"available": True, "gate": "G-ROUNDS", "state": "corrupt", "passed": False,
                              "planned": None, "missing": [],
                              "panel": {"state": "corrupt", "path": "study/consensus/panel.json", "message": "p <bad>"},
                              "plan": {"state": "corrupt", "path": "study/consensus/plan.json", "message": "pl <bad>"},
                              "rounds": {"state": "corrupt", "path": "study/consensus/rounds.json", "message": "r <bad>",
                                         "rounds": []},
                              "micmac": {"state": "corrupt", "path": "study/consensus/micmac.json", "message": "m <bad>"},
                              "warnings": []}}
        out = run(view)["html"]
        self.assertIn('<p class="rv-error" role="alert">The transcripts record study/transcripts.json cannot be read: '
                      "bad &lt;json&gt;</p>", out)
        self.assertIn("The codebook record study/codebook.json cannot be read: cb &lt;bad&gt;", out)
        self.assertIn("The themes record study/themes.json cannot be read: th &lt;bad&gt;", out)
        self.assertIn("Gate G-ROUNDS cannot be evaluated: a consensus record cannot be read.", out)
        for part, message in (("panel", "p"), ("plan", "pl"), ("rounds", "r"), ("MICMAC", "m")):
            self.assertIn(f"The {part} record study/consensus/{part.lower()}.json cannot be read: {message} &lt;bad&gt;", out)
        self.assertIn('data-study-section="protocol"', out)

    def test_spanish(self) -> None:
        out = run(self.view, lang="es")["html"]
        for text in ("<h3>Transcripciones</h3>", "<h3>Libro de códigos y temas</h3>", "<h3>Rondas de consenso</h3>",
                     "<td>Entrevista</td>", "<td>Grupo focal</td>", "<th>Desidentificación</th>",
                     "el asistente nunca escribe, edita ni lee en voz alta una transcripción",
                     "el asistente nunca ingresa ni edita una calificación", "<td>75 % (3 de 4)</td>",
                     "<td>Influyente</td>", "<td>Enlace</td>", "Vigente: 1 de 2 ítem(s) alcanzaron consenso."):
            self.assertIn(text, out)
        for text in ("<h3>Transcripts</h3>", "<h3>Consensus rounds</h3>", "<td>Interview</td>"):
            self.assertNotIn(text, out)

    def test_unavailable_sections_and_a_view_without_them(self) -> None:
        view = {**self.view, "transcripts": {"available": False, "code": "STUDY_MODULE_UNAVAILABLE",
                                             "message": "qualitative <gone>"}}
        out = run(view)["html"]
        self.assertIn('data-study-section="transcripts"', out)
        self.assertIn("qualitative &lt;gone&gt;", out)
        self.assertIn('data-study-section="consensus"', out)
        without = {key: value for key, value in self.view.items() if key not in ("transcripts", "themes", "consensus")}
        html = run(without)["html"]
        for name in ("transcripts", "themes", "consensus"):
            self.assertNotIn(f'data-study-section="{name}"', html)


if __name__ == "__main__":
    unittest.main()
