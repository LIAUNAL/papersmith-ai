"""The dashboard's Spanish translation of the manuscript (PDF tab).

`GET /api/translations?lang=es` and `POST /api/pdf/ai-audit?translation=es` run
`paper_cli.py translate status|audit --lang es` (a stub script stands in for the
CLI); `POST /api/paper/compile?translation=es` compiles
`paper/translations/es/main.tex` in place with the toolchain mocked; `GET
/api/pdf?translation=es` serves `paper/translations/es/main.pdf`. The panel
(static/translation-panel.js) renders under node.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from skills._core.command_center import server

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "tests" / "fixtures" / "command_center_translation"
STUB = FIXTURES / "stub_paper_cli.py"
SAME = {"Origin": "http://testserver"}
OTHER = {"Origin": "http://evil.example"}
BAD_LANGS = ("en", "fr", "", "ES", "es-CO", "../es")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TranslationCase(unittest.TestCase):
    """A scratch workspace with an English paper and a client."""

    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.tmp = Path(holder.name).resolve()
        self.root = self.tmp / "ws"
        self.paper = self.root / "paper"
        self.paper.mkdir(parents=True)
        (self.paper / "main.tex").write_text("\\documentclass{article}\\begin{document}EN\\end{document}\n",
                                             encoding="utf-8")
        self.es = self.paper / "translations" / "es"
        self.client = TestClient(server.create_app(self.root))
        self.argv_log = self.tmp / "argv.log"

    def stub(self, response: dict | str, exit_code: int = 0, sleep: float = 0.0) -> None:
        path = self.tmp / "response.json"
        if isinstance(response, str) and response.endswith(".json") and (FIXTURES / response).is_file():
            response = (FIXTURES / response).read_text(encoding="utf-8")
        path.write_text(response if isinstance(response, str) else json.dumps(response), encoding="utf-8")
        patches = [
            mock.patch.object(server, "PAPER_CLI", STUB),
            mock.patch.dict(os.environ, {
                "STUB_PAPER_RESPONSE": str(path), "STUB_PAPER_EXIT": str(exit_code),
                "STUB_PAPER_ARGV": str(self.argv_log), "STUB_PAPER_SLEEP": str(sleep)}),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def calls(self) -> list[list[str]]:
        if not self.argv_log.is_file():
            return []
        return [json.loads(line) for line in self.argv_log.read_text(encoding="utf-8").splitlines()]

    def built(self) -> Path:
        self.es.mkdir(parents=True, exist_ok=True)
        tex = self.es / "main.tex"
        tex.write_text("\\documentclass{article}\\begin{document}ES\\end{document}\n", encoding="utf-8")
        return tex


# --------------------------------------------------------------------------
# GET /api/translations
# --------------------------------------------------------------------------
class TranslationStatusTests(TranslationCase):
    def test_status_runs_the_cli_from_the_workspace_and_returns_its_json(self) -> None:
        self.stub("status.json")
        response = self.client.get("/api/translations?lang=es")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["counts"], {"total": 4, "current": 2, "stale": 1, "missing": 1})
        self.assertTrue(body["built"])
        # the workspace paper is named explicitly: never the CLI's own default
        self.assertEqual(self.calls(), [["translate", "status", "--lang", "es", "--paper", str(self.root / "paper")]])

    def test_a_cli_refusal_keeps_its_code_and_maps_to_a_conflict(self) -> None:
        self.stub({"ok": False, "error": "PAPER_ABSENT", "message": "no paper/main.tex"}, exit_code=2)
        response = self.client.get("/api/translations?lang=es")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "PAPER_ABSENT")
        self.assertEqual(response.json()["message"], "no paper/main.tex")

    def test_a_usage_refusal_is_422(self) -> None:
        self.stub({"ok": False, "error": "USAGE", "message": "bad flag"}, exit_code=2)
        self.assertEqual(self.client.get("/api/translations?lang=es").status_code, 422)

    def test_the_cli_language_refusals_are_422(self) -> None:
        for code in ("TRANSLATION_LANGUAGE_UNSUPPORTED", "TRANSLATION_FIDELITY"):
            with self.subTest(code=code):
                self.stub({"ok": False, "error": code, "message": "m"}, exit_code=2)
                self.assertEqual(self.client.get("/api/translations?lang=es").status_code,
                                 422 if code == "TRANSLATION_LANGUAGE_UNSUPPORTED" else 409)

    def test_a_cli_without_json_is_a_typed_502(self) -> None:
        self.stub("Traceback: boom", exit_code=1)
        response = self.client.get("/api/translations?lang=es")
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["error"], "PAPER_CLI_FAILED")

    def test_a_missing_cli_is_a_typed_503(self) -> None:
        with mock.patch.object(server, "PAPER_CLI", self.tmp / "absent.py"):
            response = self.client.get("/api/translations?lang=es")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"], "PAPER_CLI_ABSENT")

    def test_a_slow_cli_is_stopped_at_the_deadline(self) -> None:
        self.stub("status.json", sleep=5)
        with mock.patch.object(server, "TRANSLATE_STATUS_TIMEOUT_SECONDS", 0.5):
            response = self.client.get("/api/translations?lang=es")
        self.assertEqual(response.status_code, 504)
        self.assertEqual(response.json()["error"], "TIMEOUT")

    def test_only_spanish_is_a_valid_language(self) -> None:
        self.stub("status.json")
        for lang in BAD_LANGS:
            with self.subTest(lang=lang):
                response = self.client.get("/api/translations", params={"lang": lang})
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json()["error"], "TRANSLATION_LANG_INVALID")
        self.assertEqual(self.calls(), [])


# --------------------------------------------------------------------------
# POST /api/pdf/ai-audit?translation=es
# --------------------------------------------------------------------------
class TranslationAuditTests(TranslationCase):
    def test_the_spanish_audit_runs_the_cli_and_returns_the_contract(self) -> None:
        self.stub("audit.json")
        response = self.client.post("/api/pdf/ai-audit?translation=es", headers=SAME)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["document"]["index"], 78)
        self.assertIn("not an authorship detector", body["notice"])
        # the workspace paper is named explicitly: never the CLI's own default
        self.assertEqual(self.calls(), [["translate", "audit", "--lang", "es", "--paper", str(self.root / "paper")]])

    def test_the_english_audit_path_is_untouched(self) -> None:
        self.stub("audit.json")
        response = self.client.post("/api/pdf/ai-audit", json={}, headers=SAME)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["scope"], "manuscript")
        self.assertEqual(self.calls(), [])

    def test_a_cross_origin_spanish_audit_is_403(self) -> None:
        self.stub("audit.json")
        self.assertEqual(self.client.post("/api/pdf/ai-audit?translation=es", headers=OTHER).status_code, 403)
        self.assertEqual(self.calls(), [])

    def test_an_audit_refusal_maps_to_a_conflict(self) -> None:
        self.stub({"ok": False, "error": "TRANSLATION_ABSENT", "message": "nothing translated"}, exit_code=2)
        response = self.client.post("/api/pdf/ai-audit?translation=es", headers=SAME)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "TRANSLATION_ABSENT")

    def test_only_spanish_is_a_valid_translation(self) -> None:
        self.stub("audit.json")
        for lang in BAD_LANGS:
            with self.subTest(lang=lang):
                response = self.client.post("/api/pdf/ai-audit", params={"translation": lang}, headers=SAME)
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json()["error"], "TRANSLATION_LANG_INVALID")
        self.assertEqual(self.calls(), [])


# --------------------------------------------------------------------------
# POST /api/paper/compile?translation=es
# --------------------------------------------------------------------------
class TranslationCompileTests(TranslationCase):
    def fake_tex(self, calls: list):
        def fake_run(argv, **kwargs):
            calls.append((argv, kwargs))
            if argv[0] == "pdflatex":
                (Path(kwargs["cwd"]) / "main.pdf").write_bytes(b"%PDF-1.4 spanish build")
            return subprocess.CompletedProcess(argv, 0, stdout="This is pdfTeX", stderr="")
        return fake_run

    def compile(self, query: str = "?translation=es", headers=SAME):
        return self.client.post("/api/paper/compile" + query, headers=headers)

    def test_a_cross_origin_compile_is_403(self) -> None:
        self.built()
        self.assertEqual(self.compile(headers=OTHER).status_code, 403)

    def test_compile_without_a_built_translation_is_409_naming_translate_build(self) -> None:
        response = self.compile()
        self.assertEqual(response.status_code, 409)
        body = response.json()
        self.assertEqual(body["error"], "TRANSLATION_NOT_BUILT")
        self.assertIn("translate build", body["message"])

    def test_the_spanish_compile_runs_in_the_translation_directory_and_leaves_english_alone(self) -> None:
        self.built()
        canonical = sha(self.paper / "main.tex")
        calls: list = []
        with mock.patch.object(server.subprocess, "run", self.fake_tex(calls)):
            response = self.compile()
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["outputs"], ["paper/translations/es/main.pdf"])
        self.assertEqual([argv[0] for argv, _ in calls], ["pdflatex", "bibtex", "pdflatex", "pdflatex"])
        for _, kwargs in calls:
            self.assertEqual(Path(kwargs["cwd"]), self.es)
            # The figures and refs.bib of paper/ stay reachable from the translation directory.
            self.assertIn(str(self.paper), kwargs["env"]["TEXINPUTS"])
            self.assertIn(str(self.paper), kwargs["env"]["BIBINPUTS"])
        self.assertEqual(sha(self.paper / "main.tex"), canonical)
        self.assertFalse((self.paper / "main.pdf").exists())
        self.assertTrue((self.es / "main.pdf").is_file())

    def test_compile_is_409_while_the_paper_lock_is_held(self) -> None:
        self.built()
        self.assertTrue(server._PAPER_LOCK.acquire(blocking=False))
        try:
            response = self.compile()
        finally:
            server._PAPER_LOCK.release()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "PAPER_BUSY")

    def test_only_spanish_is_valid_and_venue_with_translation_is_refused(self) -> None:
        self.built()
        for lang in BAD_LANGS:
            with self.subTest(lang=lang):
                response = self.client.post("/api/paper/compile", params={"translation": lang}, headers=SAME)
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json()["error"], "TRANSLATION_LANG_INVALID")
        both = self.compile("?translation=es&venue=eswa")
        self.assertEqual(both.status_code, 422)
        self.assertEqual(both.json()["error"], "TRANSLATION_WITH_VENUE")

    def test_a_translation_directory_that_escapes_the_workspace_is_not_compiled(self) -> None:
        with tempfile.TemporaryDirectory() as elsewhere:
            (Path(elsewhere) / "main.tex").write_text("x", encoding="utf-8")
            (self.paper / "translations").mkdir()
            (self.paper / "translations" / "es").symlink_to(elsewhere)
            calls: list = []
            with mock.patch.object(server.subprocess, "run", self.fake_tex(calls)):
                response = self.compile()
            self.assertEqual(response.status_code, 409)
            self.assertEqual(calls, [])


# --------------------------------------------------------------------------
# GET /api/pdf?translation=es
# --------------------------------------------------------------------------
class TranslationPdfTests(TranslationCase):
    def test_the_spanish_pdf_is_404_until_compiled_then_served(self) -> None:
        self.assertEqual(self.client.get("/api/pdf?translation=es").status_code, 404)
        self.built()
        (self.es / "main.pdf").write_bytes(b"%PDF-1.4 es")
        (self.paper / "main.pdf").write_bytes(b"%PDF-1.4 en")
        response = self.client.get("/api/pdf?translation=es")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"%PDF-1.4 es")
        self.assertEqual(response.headers["content-type"], "application/pdf")
        # The canonical preview is unchanged.
        self.assertEqual(self.client.get("/api/pdf").content, b"%PDF-1.4 en")

    def test_only_spanish_is_valid_and_venue_with_translation_is_refused(self) -> None:
        for lang in BAD_LANGS:
            with self.subTest(lang=lang):
                response = self.client.get("/api/pdf", params={"translation": lang})
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json()["error"], "TRANSLATION_LANG_INVALID")
        self.assertEqual(self.client.get("/api/pdf?translation=es&venue=eswa").status_code, 422)

    def test_a_pdf_symlinked_out_of_the_translation_directory_is_not_served(self) -> None:
        self.built()
        with tempfile.TemporaryDirectory() as elsewhere:
            target = Path(elsewhere) / "main.pdf"
            target.write_bytes(b"%PDF-1.4 elsewhere")
            (self.es / "main.pdf").symlink_to(target)
            self.assertEqual(self.client.get("/api/pdf?translation=es").status_code, 404)

    def test_a_translation_directory_symlinked_out_is_not_served(self) -> None:
        with tempfile.TemporaryDirectory() as elsewhere:
            (Path(elsewhere) / "main.pdf").write_bytes(b"%PDF-1.4 elsewhere")
            (self.paper / "translations").mkdir()
            (self.paper / "translations" / "es").symlink_to(elsewhere)
            self.assertEqual(self.client.get("/api/pdf?translation=es").status_code, 404)


# --------------------------------------------------------------------------
# the panel under node
# --------------------------------------------------------------------------
STATIC = REPO / "skills" / "_core" / "command_center" / "static"
PAGE = (STATIC / "index.html").read_text(encoding="utf-8")
PANEL = STATIC / "translation-panel.js"
ALLOWED_TAGS = {"div", "span", "strong", "a", "table", "thead", "tbody", "tr", "th", "td", "details", "summary",
                "ul", "li", "button", "label", "select", "option", "code", "p", "em", "h4", "h5", "section"}

PRELUDE = """
const fs = require('fs');
const store = {};
global.window = global;
global.localStorage = { getItem: (k) => store[k] ?? null, setItem: (k, v) => { store[k] = v; } };
global.CustomEvent = class { constructor(type, init) { this.type = type; this.detail = init && init.detail; } };
const host = { innerHTML: '', listeners: {}, addEventListener(type, fn) { this.listeners[type] = fn; } };
global.document = { readyState: 'complete', documentElement: { lang: 'xx' }, querySelectorAll: () => [],
  addEventListener() {}, dispatchEvent() {}, getElementById: (id) => (id === 'translationPanel' ? host : null) };
const calls = []; const shown = [];
global.__routes = [];
global.fetch = async (url, init) => {
  const method = (init && init.method) || 'GET';
  calls.push({ url, method });
  const route = global.__routes.find((r) => r[0] === method && url.startsWith(r[1]));
  const reply = route ? route[2] : { status: 404, body: {} };
  return { ok: reply.status < 400, status: reply.status, json: async () => reply.body };
};
global.setPdfTranslation = (lang) => shown.push(lang);
%(files)s
window.i18n.setLanguage(%(lang)s);
const P = window.TranslationPanel;
P.mount();
const out = (value) => console.log(JSON.stringify(value));
const el = (attrs, extra) => Object.assign({ disabled: false, getAttribute: (n) => (n in attrs ? attrs[n] : null),
  closest(selector) { const name = selector.slice(1, -1); return name in attrs ? this : null; } }, extra || {});
const tick = () => new Promise((r) => setTimeout(r, 0));
const click = async (attrs) => { await host.listeners.click({ target: el(attrs) }); await tick(); await tick(); };
const change = async (attrs, value) => { await host.listeners.change({ target: el(attrs, { value }) }); await tick(); await tick(); };
const status = %(status)s; const empty = %(empty)s; const audit = %(audit)s;
"""


@unittest.skipUnless(shutil.which("node"), "node is required to run the panel")
class TranslationPanelTests(unittest.TestCase):
    def node(self, body: str, lang: str = "es"):
        files = "".join(f"eval(fs.readFileSync({json.dumps(str(path))}, 'utf8'));"
                        for path in (STATIC / "i18n" / "en.js", STATIC / "i18n" / "es.js", STATIC / "i18n.js", PANEL))
        fixtures = {name: (FIXTURES / f"{file}.json").read_text(encoding="utf-8")
                    for name, file in (("status", "status"), ("empty", "status-empty"), ("audit", "audit"))}
        script = (PRELUDE % {"files": files, "lang": json.dumps(lang), **fixtures} + "(async () => {" + body
                  + "})().catch((error) => { console.error(error); process.exit(1); });")
        done = subprocess.run(["node", "-e", script], capture_output=True, text=True, cwd=tempfile.gettempdir(),
                              check=False)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout.strip().splitlines()[-1])

    def assert_only_known_markup(self, html: str) -> None:
        tags = set(re.findall(r"</?([a-zA-Z][a-zA-Z0-9]*)", html))
        self.assertLessEqual(tags, ALLOWED_TAGS, f"unexpected tags: {tags - ALLOWED_TAGS}")

    def test_the_selector_defaults_to_the_english_canonical_version(self) -> None:
        en, es = (self.node("out(P.panelHtml(P.state));", lang=lang) for lang in ("en", "es"))
        self.assertIn("English (canonical)", en)
        self.assertIn("Spanish (translation)", en)
        self.assertIn('<option value="en" selected>', en)
        self.assertIn("Inglés (canónico)", es)
        self.assertIn("Español (traducción)", es)
        self.assertNotIn("data-tp-action", en)

    def test_the_status_counts_and_actions_render_when_built(self) -> None:
        es, en = (self.node("out(P.statusHtml({ status, busy: {} }));", lang=lang) for lang in ("es", "en"))
        for expected in ("2 al día", "1 desactualizado", "1 sin traducir", "de 4 bloques", "Ensamblada",
                         'data-tp-action="compile"', 'data-tp-action="preview"', 'data-tp-action="audit"',
                         "78/100"):
            self.assertIn(expected, es)
        for expected in ("2 current", "1 stale", "1 missing", "of 4 blocks", "Built"):
            self.assertIn(expected, en)
        self.assert_only_known_markup(es)

    def test_titles_and_captions_are_counted_and_missing_ones_warn(self) -> None:
        es, en = (self.node("""out(P.statusHtml({ status: { ...status, counts: { total: 4, current: 4, stale: 0, missing: 0 },
          fragment_counts: { total: 6, current: 4, stale: 0, missing: 2 } }, busy: {} }));""", lang=lang) for lang in ("es", "en"))
        self.assertIn("Títulos y leyendas: 4 al día · 0 desactualizados · 2 sin traducir, de 6", es)
        self.assertIn("/paper-writing translate es", es)
        self.assertIn("Titles and captions: 4 current · 0 stale · 2 missing, of 6", en)
        plain = self.node("out(P.statusHtml({ status, busy: {} }));")
        self.assertNotIn("Títulos y leyendas", plain)

    def test_an_unbuilt_translation_has_no_compile_but_names_the_agent_command(self) -> None:
        html = self.node("out(P.statusHtml({ status: { ...status, built: false, pdf: null, main_tex: null }, busy: {} }));")
        self.assertNotIn('data-tp-action="compile"', html)
        self.assertIn("/paper-writing translate es", html)

    def test_nothing_translated_shows_the_empty_state_with_the_english_command(self) -> None:
        es, en = (self.node("out(P.statusHtml({ status: empty, busy: {} }));", lang=lang) for lang in ("es", "en"))
        self.assertIn("Todavía no hay traducción", es)
        self.assertIn("<code>/paper-writing translate es</code>", es)
        self.assertIn("No translation yet", en)
        self.assertIn("<code>/paper-writing translate es</code>", en)
        self.assertNotIn('data-tp-action="audit"', es)

    def test_the_audit_panel_renders_every_part_in_spanish(self) -> None:
        html = self.node("out(P.auditHtml(audit));")
        for expected in ("78", "/100", "Desigual", "Estilo 0.21", "Fluidez 0.18", "Redundancia 0.12",
                         "intro.motivation", "91", "Clara", "method.model", "62", "Requiere revisión",
                         "calque", "juega un rol clave", "Use desempeña un papel or rephrase.",
                         "señales electroencefalográficas", "intro.motivation, method.model",
                         "El modelo propuesto supera a los métodos de referencia.", "Fidelidad",
                         "citation key smith2024 missing", "number 0.93 missing", "Sin diferencias"):
            self.assertIn(expected, html)
        self.assertIn("<details", html)
        self.assert_only_known_markup(html)

    def test_the_notice_is_shown_verbatim_in_both_languages(self) -> None:
        notice = json.loads((FIXTURES / "audit.json").read_text(encoding="utf-8"))["notice"]
        for lang in ("es", "en"):
            with self.subTest(lang=lang):
                self.assertIn(notice, self.node("out(P.auditHtml(audit));", lang=lang))

    def test_the_audit_panel_in_english(self) -> None:
        html = self.node("out(P.auditHtml(audit));", lang="en")
        for expected in ("Uneven", "Needs revision", "Clear", "Style 0.21", "Fidelity", "No differences",
                         "Repeated across blocks"):
            self.assertIn(expected, html)

    def test_hostile_values_never_become_markup(self) -> None:
        html = self.node("""
          const evil = '<script>alert(1)</script>';
          out(P.auditHtml({ ...audit, notice: evil, document: { index: evil, verdict: evil },
            blocks: [{ id: evil, index: evil, verdict: evil, findings: [{ category: evil, fragment: evil, hint: evil }] }],
            cross_block_redundancy: [{ phrase: evil, blocks: [evil] }], fidelity: [{ id: evil, ok: false, differences: [evil] }] })
            + P.statusHtml({ status: { ...status, counts: { total: evil, current: evil } }, busy: {} }));""")
        self.assertNotIn("<script", html)
        self.assertIn("&lt;script&gt;", html)
        self.assert_only_known_markup(html)

    def test_choosing_spanish_loads_the_status_and_the_buttons_call_the_routes(self) -> None:
        result = self.node("""
          __routes.push(['GET', '/api/translations?lang=es', { status: 200, body: status }]);
          __routes.push(['POST', '/api/paper/compile?translation=es', { status: 200, body: { ok: true, message: 'compiled', outputs: [] } }]);
          __routes.push(['POST', '/api/pdf/ai-audit?translation=es', { status: 200, body: audit }]);
          await change({ 'data-tp-field': 'version' }, 'es');
          await click({ 'data-tp-action': 'preview' });
          await click({ 'data-tp-action': 'compile' });
          await click({ 'data-tp-action': 'audit' });
          const html = host.innerHTML;
          await change({ 'data-tp-field': 'version' }, 'en');
          out({ calls, shown, html });""")
        self.assertEqual([(c["method"], c["url"]) for c in result["calls"]][:4], [
            ("GET", "/api/translations?lang=es"), ("POST", "/api/paper/compile?translation=es"),
            ("GET", "/api/translations?lang=es"), ("POST", "/api/pdf/ai-audit?translation=es")])
        self.assertEqual(result["shown"][0], "es")
        self.assertIsNone(result["shown"][-1])
        self.assertIn("juega un rol clave", result["html"])

    def test_a_refused_status_shows_its_message(self) -> None:
        html = self.node("""
          __routes.push(['GET', '/api/translations?lang=es', { status: 409, body: { ok: false, error: 'PAPER_ABSENT', message: 'no paper/main.tex' } }]);
          await change({ 'data-tp-field': 'version' }, 'es');
          out(host.innerHTML);""")
        self.assertIn("no paper/main.tex", html)

    def test_the_page_mounts_the_panel_beside_the_preview(self) -> None:
        self.assertIn('<div id="translationPanel"></div>', PAGE)
        self.assertLess(PAGE.index('id="translationPanel"'), PAGE.index('<div class="pdf-viewer-topbar">'))
        token = re.search(r'src="\./journals-panel\.js\?v=([^"]+)"', PAGE).group(1)
        self.assertIn(f'<script src="./translation-panel.js?v={token}"></script>', PAGE)
        self.assertIn("window.setPdfTranslation = setPdfTranslation;", PAGE)
        self.assertIn("&translation=${encodeURIComponent(pdfTranslation)}", PAGE)
        # The canonical viewer lines stay as they were.
        self.assertIn("native.src = `/api/pdf?v=${token}`;", PAGE)
        self.assertIn("&venue=${encodeURIComponent(pdfVenueSlug)}", PAGE)


if __name__ == "__main__":
    unittest.main()
