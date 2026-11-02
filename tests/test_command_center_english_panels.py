"""With the dashboard in English, every panel speaks English.

The dashboard's own labels come from the catalogues, so they follow the
language selector. Two surfaces escaped that rule: the 3D atlas page wrote its
group-layout button in Spanish, and the Concept Map & Model panel draws the
workspace's `.papersmith/model_spec.json` as written, so a specification an
agent wrote in Spanish showed Spanish under English. The atlas button is now
English, the model panel repaints on a language switch, and a specification
that is not English carries a notice that names its fields and how to rewrite
it.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from papersmith.render import package_template_path
from skills._core.command_center import model_spec, server

REPO = Path(__file__).resolve().parents[1]
STATIC = Path(server.__file__).resolve().parent / "static"
PAGE = (STATIC / "index.html").read_text(encoding="utf-8")
RENDERER = REPO / "skills" / "plausibility" / "scripts" / "render_atlas.py"

SPANISH_SPEC = {
    "title": "Hybrid Quantum-Classical Neural Network",
    "authors": "Andrés Álvarez",
    "executive_summary": "Arquitectura híbrida clásica-cuántica para la clasificación diagnóstica de TDAH "
                         "a partir de registros EEG de 19 canales.",
    "novelty": {
        "problem_statement": "La alta variabilidad inter-sujeto del EEG y la escasa expresividad de las "
                             "codificaciones cuánticas limitan el rendimiento diagnóstico.",
        "pillars": [{"name": "Compresión Espacio-Temporal",
                     "details": "Evita mesetas estériles al emparejar el número de dimensiones latentes "
                                "con los 4 qubits del registro."}],
        "hypotheses": [{"id": "H1", "title": "Ventaja DRU",
                        "statement": "El circuito DRU de L capas sobre 4 qubits alcanzará mayor precisión y "
                                     "convergencia que un circuito variacional estándar."}],
    },
    "conceptual_map": {"layers": [{"name": "Capa 1", "nodes": [{"name": "Señal Cruda X"}]}]},
}
ENGLISH_SPEC = {
    "title": "Hybrid Quantum-Classical Neural Network",
    "authors": "Andrés Álvarez",
    "executive_summary": "A hybrid classical-quantum architecture for ADHD classification.",
    "novelty": {"problem_statement": "Inter-subject EEG variability limits performance.",
                "pillars": [{"name": "Spatio-temporal compression", "summary": "Maps the Theta and Beta bands."}]},
}


def workspace(spec: dict | None) -> Path:
    root = Path(tempfile.mkdtemp())
    (root / "papersmith.yaml").write_text("title: Fresh Paper\n", encoding="utf-8")
    if spec is not None:
        (root / ".papersmith").mkdir()
        (root / ".papersmith" / "model_spec.json").write_text(json.dumps(spec), encoding="utf-8")
    return root


def render_model_panel(spec: dict, lang: str = "en") -> dict:
    """Run model-panel.js under a DOM stub with both catalogues loaded."""
    script = (
        "const fs=require('fs');const els={};const listeners={};"
        "global.localStorage={getItem:()=>" + json.dumps(lang) + ",setItem(){}};"
        "global.window={localStorage:global.localStorage,location:{href:'http://x/',origin:'http://x'}};"
        "global.CustomEvent=function(n,o){this.type=n;this.detail=o&&o.detail;};"
        "global.document={readyState:'complete',documentElement:{},"
        "addEventListener:(n,f)=>{(listeners[n]=listeners[n]||[]).push(f);},"
        "dispatchEvent:(e)=>{(listeners[e.type]||[]).forEach((f)=>f(e));},"
        "getElementById:(id)=>(els[id]=els[id]||{innerHTML:'',hidden:false})};"
        "for (const f of ['i18n/en.js','i18n/es.js','i18n.js','model-panel.js'])"
        f"  eval(fs.readFileSync({json.dumps(str(STATIC))}+'/'+f,'utf8'));"
        f"window.renderModelModules({json.dumps(spec)});"
        "const first={notice:els.modelLanguageNotice.innerHTML,hidden:els.modelLanguageNotice.hidden,"
        "pillars:els.modelPillarGrid.innerHTML};"
        "window.i18n.setLanguage(" + json.dumps("es" if lang == "en" else "en") + ");"
        "console.log(JSON.stringify({first,switched:{notice:els.modelLanguageNotice.innerHTML,"
        "pillars:els.modelPillarGrid.innerHTML}}));"
    )
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True,
                         cwd=tempfile.gettempdir(), check=True).stdout
    return json.loads(out)


class AtlasPageTests(unittest.TestCase):
    def test_the_group_layout_button_is_english(self) -> None:
        import importlib.util
        spec = importlib.util.spec_from_file_location("render_atlas", str(RENDERER))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        page = module.render({"systems": [], "links": []})
        self.assertIn('<button id="grouplayout">Group layout</button>', page)
        self.assertNotIn("Disposición", page)


class ModelSpecLanguageTests(unittest.TestCase):
    def test_a_spanish_specification_carries_a_notice_naming_its_fields(self) -> None:
        spec = model_spec.get_model_specification(workspace(SPANISH_SPEC))
        notice = spec["language_notice"]
        self.assertEqual(notice["expected"], "en")
        self.assertEqual(notice["file"], ".papersmith/model_spec.json")
        # The detector reads prose; a short title-case label carries too few
        # words to judge, so the notice speaks for the whole specification.
        for field in ("executive_summary", "novelty.problem_statement", "novelty.pillars.details",
                      "novelty.hypotheses.statement"):
            self.assertIn(field, notice["fields"])
        self.assertNotIn("novelty.pillars.name", notice["fields"])
        # A name with accents is a person, not Spanish prose.
        self.assertNotIn("authors", notice["fields"])
        # The workspace's content is shown as written, never dropped.
        self.assertEqual(spec["novelty"]["pillars"][0]["name"], "Compresión Espacio-Temporal")

    def test_an_english_specification_and_the_neutral_one_carry_no_notice(self) -> None:
        self.assertNotIn("language_notice", model_spec.get_model_specification(workspace(ENGLISH_SPEC)))
        self.assertNotIn("language_notice", model_spec.get_model_specification(workspace(None)))


class ModelPanelTests(unittest.TestCase):
    def test_the_notice_is_drawn_in_the_dashboard_language(self) -> None:
        spec = model_spec.get_model_specification(workspace(SPANISH_SPEC))
        out = render_model_panel(spec, "en")
        self.assertFalse(out["first"]["hidden"])
        self.assertIn("is not written in English", out["first"]["notice"])
        self.assertIn(".papersmith/model_spec.json", out["first"]["notice"])
        self.assertIn("/proposal-deliberation", out["first"]["notice"])
        # Switching to Spanish repaints the notice from the same spec.
        self.assertIn("no está escrita en inglés", out["switched"]["notice"])

    def test_a_language_switch_repaints_the_empty_states(self) -> None:
        out = render_model_panel({}, "es")
        self.assertIn("pilares", out["first"]["pillars"])
        self.assertIn("The novelty pillars appear", out["switched"]["pillars"])
        self.assertEqual(out["first"]["notice"], "")
        self.assertTrue(out["first"]["hidden"])

    def test_the_page_has_the_notice_and_refetches_the_model_on_a_switch(self) -> None:
        self.assertIn('id="modelLanguageNotice"', PAGE)
        handler = PAGE[PAGE.index("document.addEventListener('languagechange', () => {\n      renderThemeButton"):]
        handler = handler[:handler.index("\n    });")]
        self.assertIn("refreshModelData()", handler)


class LanguageRuleTests(unittest.TestCase):
    def test_the_language_rule_names_the_dashboard_data_files(self) -> None:
        rule = package_template_path("language.md.tpl").read_text(encoding="utf-8")
        self.assertIn(".papersmith/", rule)

    def test_proposal_deliberation_owns_the_model_specification_in_english(self) -> None:
        skill = (REPO / "skills" / "proposal-deliberation" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn(".papersmith/model_spec.json", skill)
        section = skill[skill.index(".papersmith/model_spec.json"):][:2500]
        self.assertIn("English", section)


if __name__ == "__main__":
    unittest.main()
