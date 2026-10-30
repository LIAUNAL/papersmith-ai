"""The dashboard speaks English by default and Spanish on request.

The page served at ``/`` (``static/index.html`` and its panel scripts) reads
every visible string from two catalogues, ``static/i18n/en.js`` and
``static/i18n/es.js``, through ``static/i18n.js``; a selector in the header
switches between them. The server answers in English and localizes its display
labels when a request carries ``?lang=es`` (``command_center/localize.py``),
never a machine value. The headless tutors answer the reader in the reader's
language and keep everything else English.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from skills._core.command_center import experiments_tutor, localize, server, terminal, tutor

STATIC = Path(server.__file__).resolve().parent / "static"
PAGE = (STATIC / "index.html").read_text(encoding="utf-8")
CATALOGUE_DIR = STATIC / "i18n"
PANELS = sorted(path for path in STATIC.glob("*.js") if path.name != "i18n.js")
SPANISH_ACCENTS = re.compile(r"[áéíóúñÁÉÍÓÚÑ¿¡]")
# Unaccented words that only Spanish UI text uses; the accented ones are
# caught by SPANISH_ACCENTS.
SPANISH_WORDS = re.compile(
    r"\b(?:Cargando|Actualizar|corridas?|Abrir|pendientes?|Guardar|Cancelar|Ejecutar|Desmarcar"
    r"|Buscar|Ninguno|todavia|para|del|los|las|una|con|sin|Sin|Ver|desde|hasta|cuando)\b")


def catalogue(lang: str) -> dict[str, str]:
    """The ``{key: text}`` object a catalogue script assigns."""
    text = (CATALOGUE_DIR / f"{lang}.js").read_text(encoding="utf-8")
    match = re.search(rf"window\.PAPERSMITH_I18N\.{lang}\s*=\s*(\{{.*\}})\s*;\s*\Z", text, re.S)
    assert match, f"i18n/{lang}.js assigns one JSON object literal"
    return json.loads(match.group(1))


EN = catalogue("en")
ES = catalogue("es")


def placeholders(text: str) -> set[str]:
    return set(re.findall(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", text))


def inline_script() -> str:
    return PAGE[PAGE.index("<script>", PAGE.index("<body>")):]


def markup() -> str:
    return PAGE[PAGE.index("<body>"):PAGE.index("<script>", PAGE.index("<body>"))]


def code_keys(source: str) -> set[str]:
    """Every literal key passed to ``t(...)``."""
    return {match[1] for match in re.findall(r"(?<![\w.$])t\(\s*(['\"])([A-Za-z0-9_.\-]+)\1", source)}


class CatalogueTests(unittest.TestCase):
    def test_both_catalogues_hold_the_same_keys(self) -> None:
        self.assertEqual(sorted(set(EN) - set(ES)), [], "keys missing from i18n/es.js")
        self.assertEqual(sorted(set(ES) - set(EN)), [], "keys missing from i18n/en.js")
        self.assertGreater(len(EN), 300)

    def test_no_text_is_empty_and_placeholders_agree(self) -> None:
        for key, english in EN.items():
            with self.subTest(key=key):
                self.assertTrue(english.strip())
                self.assertTrue(ES[key].strip())
                self.assertEqual(placeholders(english), placeholders(ES[key]))

    def test_the_english_catalogue_is_english(self) -> None:
        accented = {key: text for key, text in EN.items() if SPANISH_ACCENTS.search(text)}
        self.assertEqual(accented, {})

    def test_every_markup_key_exists(self) -> None:
        body = markup()
        keys = set(re.findall(r'data-i18n(?:-html)?="([^"]+)"', body))
        for spec in re.findall(r'data-i18n-attr="([^"]+)"', body):
            keys |= {pair.split(":", 1)[1].strip() for pair in spec.split(";") if ":" in pair}
        self.assertGreater(len(keys), 150)
        self.assertEqual(sorted(keys - set(EN)), [])

    def test_every_key_the_scripts_ask_for_exists(self) -> None:
        sources = {path.name: path.read_text(encoding="utf-8") for path in PANELS}
        sources["index.html"] = inline_script()
        for name, source in sources.items():
            with self.subTest(script=name):
                self.assertEqual(sorted(code_keys(source) - set(EN)), [])

    def test_every_panel_reads_the_catalogue(self) -> None:
        for path in PANELS:
            with self.subTest(panel=path.name):
                self.assertRegex(path.read_text(encoding="utf-8"), r"(?<![\w.$])t\(\s*'")


class NoSpanishLeftTests(unittest.TestCase):
    def shipped(self) -> list[Path]:
        return sorted(list(STATIC.glob("*.html")) + list(STATIC.glob("*.js")))

    def test_no_accented_spanish_outside_the_spanish_catalogue(self) -> None:
        for path in self.shipped():
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if SPANISH_ACCENTS.search(line):
                    self.fail(f"{path.name}:{lineno}: {line.strip()[:160]}")

    def test_no_spanish_words_in_the_page_or_its_panels(self) -> None:
        sources = [STATIC / "index.html", *PANELS]
        for path in sources:
            text = path.read_text(encoding="utf-8")
            if path.name == "index.html":
                text = text[text.index("<body>"):]
            for lineno, line in enumerate(text.splitlines(), 1):
                hit = SPANISH_WORDS.search(line)
                if hit:
                    self.fail(f"{path.name}:{lineno}: {hit.group(0)!r} in {line.strip()[:160]}")


class PageTests(unittest.TestCase):
    def test_the_page_starts_in_english(self) -> None:
        self.assertRegex(PAGE, r'<html lang="en"')

    def test_the_header_has_an_accessible_language_selector(self) -> None:
        header = PAGE[PAGE.index('<header class="topbar">'):PAGE.index("</header>", PAGE.index('<header class="topbar">'))]
        match = re.search(r"<select\b[^>]*\bid=\"langSelect\"[^>]*>(.*?)</select>", header, re.S)
        self.assertIsNotNone(match, "the topbar holds the #langSelect selector")
        tag = match.group(0)
        self.assertIn("data-lang-select", tag)
        self.assertRegex(tag, r'aria-label="[^"]*Language[^"]*"')
        self.assertEqual(re.findall(r'<option value="(\w+)"', match.group(1)), ["en", "es"])

    def test_the_runtime_and_catalogues_load_before_every_panel(self) -> None:
        head = PAGE[:PAGE.index("</head>")]
        order = re.findall(r'<script src="\./([^"?]+)', head)
        runtime = order.index("i18n.js")
        self.assertLess(order.index("i18n/en.js"), runtime)
        self.assertLess(order.index("i18n/es.js"), runtime)
        for panel in PANELS:
            with self.subTest(panel=panel.name):
                self.assertLess(runtime, order.index(panel.name))

    def test_changed_scripts_are_cache_busted_for_this_release(self) -> None:
        for name in ["i18n/en.js", "i18n/es.js", "i18n.js", *(path.name for path in PANELS)]:
            with self.subTest(script=name):
                self.assertIn(f'src="./{name}?v=0.44.0"', PAGE)

    def test_the_runtime_persists_the_choice_and_announces_it(self) -> None:
        runtime = (STATIC / "i18n.js").read_text(encoding="utf-8")
        for needle in ("localStorage", "documentElement.lang", "'languagechange'",
                       "function setLanguage", "function getLanguage", "function t(",
                       "DEFAULT_LANGUAGE = 'en'"):
            with self.subTest(needle=needle):
                self.assertIn(needle, runtime)


@unittest.skipUnless(shutil.which("node"), "node is required to run the runtime")
class RuntimeTests(unittest.TestCase):
    def run_node(self, body: str, saved: str | None = None) -> str:
        store = json.dumps({"papersmith-lang": saved} if saved else {})
        script = (
            "const fs=require('fs');const events=[];"
            f"const store={store};"
            "global.window={localStorage:{getItem:(k)=>store[k]??null,setItem:(k,v)=>{store[k]=v;}}};"
            "global.CustomEvent=class{constructor(type,init){this.type=type;this.detail=init.detail;}};"
            "global.document={readyState:'complete',documentElement:{lang:'xx'},"
            "querySelectorAll:()=>[],addEventListener(){},dispatchEvent:(e)=>events.push(e)};"
            + "".join(f"eval(fs.readFileSync({json.dumps(str(path))},'utf8'));"
                      for path in (CATALOGUE_DIR / "en.js", CATALOGUE_DIR / "es.js", STATIC / "i18n.js"))
            + body
        )
        return subprocess.run(["node", "-e", script], capture_output=True, text=True,
                              cwd=tempfile.gettempdir(), check=True).stdout.strip()

    def test_english_is_the_default_and_spanish_persists(self) -> None:
        key = next(iter(EN))
        out = self.run_node(
            "const a=[window.i18n.getLanguage(),document.documentElement.lang,window.t(" + json.dumps(key) + ")];"
            "window.i18n.setLanguage('es');"
            "a.push(window.i18n.getLanguage(),document.documentElement.lang,window.t(" + json.dumps(key) + "),"
            "store['papersmith-lang'],events.length,events[0].type,events[0].detail.lang);"
            "console.log(JSON.stringify(a));")
        self.assertEqual(json.loads(out), ["en", "en", EN[key], "es", "es", ES[key], "es", 1,
                                           "languagechange", "es"])
        self.assertEqual(self.run_node("console.log(window.i18n.getLanguage())", saved="es"), "es")
        self.assertEqual(self.run_node("console.log(window.i18n.getLanguage())", saved="fr"), "en")

    def test_a_missing_key_falls_back_to_english_then_to_the_key(self) -> None:
        out = self.run_node(
            "window.PAPERSMITH_I18N.es={};window.i18n.setLanguage('es');"
            f"console.log(JSON.stringify([window.t({json.dumps(next(iter(EN)))}),window.t('no.such.key')]))")
        self.assertEqual(json.loads(out), [next(iter(EN.values())), "no.such.key"])

    def test_variables_fill_placeholders(self) -> None:
        out = self.run_node(
            "window.PAPERSMITH_I18N.en['probe.vars']='{n} of {total}';"
            "console.log(window.t('probe.vars',{n:3,total:7}))")
        self.assertEqual(out, "3 of 7")


# --------------------------------------------------------------------------
# server labels
# --------------------------------------------------------------------------
SERVER_CATALOGUE = json.loads((CATALOGUE_DIR / "server-es.json").read_text(encoding="utf-8"))


def probe_app(payload: dict, fields: frozenset[str]) -> TestClient:
    app = FastAPI()

    @app.get("/api/probe")
    def probe() -> JSONResponse:
        return JSONResponse(payload)

    app.add_middleware(localize.LocalizeMiddleware, fields={"/api/probe": fields})
    return TestClient(app)


class LocalizeMiddlewareTests(unittest.TestCase):
    def setUp(self) -> None:
        self.english = next(key for key in SERVER_CATALOGUE if not placeholders(key))
        self.template = next(key for key in SERVER_CATALOGUE if placeholders(key))

    def test_a_machine_value_stays_byte_identical(self) -> None:
        client = probe_app({"state": self.english, "kind": "running", "id": self.english}, frozenset({"label"}))
        plain = client.get("/api/probe").content
        self.assertEqual(client.get("/api/probe?lang=es").content, plain)

    def test_an_allowlisted_field_is_translated(self) -> None:
        client = probe_app({"label": self.english, "state": self.english}, frozenset({"label"}))
        body = client.get("/api/probe?lang=es").json()
        self.assertEqual(body["label"], SERVER_CATALOGUE[self.english])
        self.assertEqual(body["state"], self.english)

    def test_a_list_under_an_allowlisted_field_is_translated(self) -> None:
        client = probe_app({"guide": [self.english, "Not in the catalogue."]}, frozenset({"guide"}))
        self.assertEqual(client.get("/api/probe?lang=es").json()["guide"],
                         [SERVER_CATALOGUE[self.english], "Not in the catalogue."])

    def test_an_unknown_string_falls_back_to_english(self) -> None:
        client = probe_app({"label": "A label nobody translated"}, frozenset({"label"}))
        self.assertEqual(client.get("/api/probe?lang=es").json()["label"], "A label nobody translated")

    def test_a_template_keeps_its_values(self) -> None:
        names = sorted(placeholders(self.template))
        values = {name: f"{index + 17}" for index, name in enumerate(names)}
        english = self.template.format(**values)
        client = probe_app({"detail": english}, frozenset({"detail"}))
        self.assertEqual(client.get("/api/probe?lang=es").json()["detail"],
                         SERVER_CATALOGUE[self.template].format(**values))

    def test_english_requests_are_untouched(self) -> None:
        payload = {"label": self.english, "nested": [{"label": "x", "n": 1.5}], "s": "ñ"}
        client = probe_app(payload, frozenset({"label"}))
        plain = client.get("/api/probe").content
        self.assertEqual(client.get("/api/probe?lang=en").content, plain)
        self.assertEqual(plain, JSONResponse(payload).body)

    def test_a_non_json_response_passes_through(self) -> None:
        app = FastAPI()

        @app.get("/api/text")
        def text() -> str:
            return self.english

        app.add_middleware(localize.LocalizeMiddleware, fields={"/api/text": frozenset({"label"})})
        client = TestClient(app)
        self.assertEqual(client.get("/api/text?lang=es").content, client.get("/api/text").content)


class ServerCatalogueTests(unittest.TestCase):
    def test_entries_are_english_keys_with_spanish_values_and_matching_placeholders(self) -> None:
        for english, spanish in SERVER_CATALOGUE.items():
            with self.subTest(english=english):
                self.assertFalse(SPANISH_ACCENTS.search(english))
                self.assertTrue(spanish.strip())
                self.assertEqual(placeholders(english), placeholders(spanish))

    def test_the_command_center_sources_carry_no_spanish(self) -> None:
        for path in sorted(STATIC.parent.glob("*.py")):
            with self.subTest(module=path.name):
                source = path.read_text(encoding="utf-8")
                # Stored enum values of the math tutor's assessment scale are
                # machine values the threads on disk already hold.
                source = source.replace('"sin-evidencia"', '""')
                hits = [line.strip() for line in source.splitlines() if SPANISH_ACCENTS.search(line)]
                self.assertEqual(hits, [])


class ServerEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.client = TestClient(server.create_app(cls.tmp.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def status(self, query: str = "") -> dict:
        response = self.client.get("/api/status" + query)
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_status_is_english_by_default_and_spanish_on_request(self) -> None:
        english = self.status()["fases"]
        spanish = self.status("?lang=es")["fases"]
        self.assertTrue(english[0]["name"].startswith("Phase 1: "))
        self.assertTrue(spanish[0]["name"].startswith("Fase 1: "))
        # Machine values do not move.
        for en_phase, es_phase in zip(english, spanish):
            for key in ("id", "status", "stage_id", "progress", "gate"):
                self.assertEqual(en_phase.get(key), es_phase.get(key))

    def test_every_status_label_has_a_spanish_entry(self) -> None:
        fields = localize.DISPLAY_FIELDS["/api/status"]
        missing = sorted({text for text in localize.display_strings(self.status(), fields)
                          if localize.lookup(text) is None})
        self.assertEqual(missing, [])

    def test_phase_actions_are_english_by_default_and_spanish_on_request(self) -> None:
        english = self.status()["fases"][1]["actions"][0]
        spanish = self.status("?lang=es")["fases"][1]["actions"][0]
        self.assertEqual(english["kind"], spanish["kind"])
        self.assertEqual(english["slash"], spanish["slash"])
        self.assertNotEqual(english["label"], spanish["label"])
        self.assertEqual(spanish["label"], SERVER_CATALOGUE[english["label"]])

    def test_terminal_agents_are_described_in_english_and_spanish(self) -> None:
        agents = terminal.default_agents()
        self.assertEqual(agents["shell"].desc, "Login shell")
        for agent in agents.values():
            with self.subTest(agent=agent.id):
                self.assertFalse(SPANISH_ACCENTS.search(agent.desc))
                self.assertIn(agent.desc, SERVER_CATALOGUE)


class ReplyLanguageTests(unittest.TestCase):
    RULE = ("Reply to the human in the language they write in (Spanish or English). "
            "Everything else stays English regardless of the conversation language: skills, "
            "agent definitions, delegations and messages between agents, tool inputs, and "
            "every generated artifact.")

    def test_both_headless_tutors_carry_the_reply_language_rule(self) -> None:
        self.assertEqual(tutor.REPLY_LANGUAGE_RULE, self.RULE)
        with tempfile.TemporaryDirectory() as tmp:
            for profile in (tutor.MATH, experiments_tutor.PROFILE):
                with self.subTest(profile=profile.name):
                    prompt = tutor.system_prompt(Path(tmp), profile)
                    self.assertTrue(prompt.endswith(self.RULE))
                    self.assertIn(profile.headless, prompt)


if __name__ == "__main__":
    unittest.main()
