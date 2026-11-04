"""The NeurIPS contribution type the paper-reviewer assigns at each phase, shown
right after that phase's hypotheses: the concept-map panel reads it from
`.papersmith/model_spec.json`, the novelty-and-findings panel from each
product's `Results/discussion.json`."""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from skills._core.command_center import model_spec, server
from skills._core.results import novelty_gate

STATIC = Path(server.__file__).resolve().parent / "static"
REPO = Path(__file__).resolve().parents[1]
CATALOGUES = {"en": STATIC / "i18n" / "en.js", "es": STATIC / "i18n" / "es.js"}

SPEC = {
    "title": "A paper",
    "novelty": {"hypotheses": [{"id": "H1", "title": "Gain", "statement": "It helps."}]},
    "contribution_type": {"type": "Theory", "why": "The core is a <b>convergence</b> bound."},
}


def _workspace(spec: dict) -> Path:
    root = Path(tempfile.mkdtemp())
    (root / ".papersmith").mkdir()
    (root / ".papersmith" / "model_spec.json").write_text(json.dumps(spec), encoding="utf-8")
    return root


def _node(script: str, stdin: str = "") -> str:
    return subprocess.run(["node", "-e", script], input=stdin, capture_output=True, text=True,
                          cwd=tempfile.gettempdir(), check=True).stdout


def _preamble(lang: str) -> str:
    return (
        "const fs=require('fs');const els={};"
        f"global.localStorage={{getItem:()=>{json.dumps(lang)},setItem(){{}}}};"
        "global.window={localStorage:global.localStorage,location:{href:'http://x/',origin:'http://x',hash:''},"
        "addEventListener(){}};"
        "global.CustomEvent=function(n,o){this.type=n;this.detail=o&&o.detail;};"
        "global.document={readyState:'complete',documentElement:{},addEventListener(){},dispatchEvent(){},"
        "querySelectorAll:()=>[],getElementById:(id)=>(els[id]=els[id]||{innerHTML:'',hidden:false})};"
        "for (const f of ['i18n/en.js','i18n/es.js','i18n.js'])"
        f"  eval(fs.readFileSync({json.dumps(str(STATIC))}+'/'+f,'utf8'));"
    )


def render_model(spec: dict, lang: str) -> dict:
    script = (_preamble(lang)
              + f"eval(fs.readFileSync({json.dumps(str(STATIC / 'model-panel.js'))},'utf8'));"
              + "window.renderModelModules(JSON.parse(fs.readFileSync(0,'utf8')));"
              + "console.log(JSON.stringify({html:els.modelContributionType.innerHTML,"
              + "hidden:els.modelContributionType.hidden}));")
    return json.loads(_node(script, json.dumps(spec)))


def render_novelty(overview: dict, lang: str) -> str:
    script = (_preamble(lang)
              + f"eval(fs.readFileSync({json.dumps(str(STATIC / 'novelty-panel.js'))},'utf8'));"
              + "window.NoveltyPanel.render(JSON.parse(fs.readFileSync(0,'utf8')));"
              + "console.log(els.noveltyRoot.innerHTML);")
    return _node(script, json.dumps(overview))


class ModelSpecTests(unittest.TestCase):
    def test_a_valid_type_is_served_as_written(self) -> None:
        spec = model_spec.get_model_specification(_workspace(SPEC))
        self.assertEqual(spec["contribution_type"], SPEC["contribution_type"])

    def test_an_unknown_type_is_dropped(self) -> None:
        bad = dict(SPEC, contribution_type={"type": "Survey", "why": "x"})
        self.assertNotIn("contribution_type", model_spec.get_model_specification(_workspace(bad)))


class ConceptMapPanelTests(unittest.TestCase):
    def test_the_card_follows_the_hypotheses_in_the_page(self) -> None:
        page = (STATIC / "index.html").read_text(encoding="utf-8")
        self.assertLess(page.index('id="modelHypothesisGrid"'), page.index('id="modelContributionType"'))
        self.assertLess(page.index('id="modelContributionType"'), page.index('id="modelSecMapa"'))

    def test_it_names_the_type_and_why_escaped_in_both_languages(self) -> None:
        for lang, heading in {"en": "NeurIPS contribution type", "es": "Tipo de contribución NeurIPS"}.items():
            with self.subTest(lang=lang):
                out = render_model(SPEC, lang)
                self.assertFalse(out["hidden"])
                self.assertIn(heading, out["html"])
                self.assertIn("Theory", out["html"])
                self.assertIn("&lt;b&gt;convergence&lt;/b&gt;", out["html"])
                self.assertNotIn("<b>convergence", out["html"])

    def test_without_a_type_the_card_says_the_review_is_owed(self) -> None:
        out = render_model({"title": "A paper"}, "en")
        self.assertIn("paper-reviewer", out["html"])
        self.assertNotIn("Theory", out["html"])


class NoveltyPanelTests(unittest.TestCase):
    def overview(self) -> dict:
        root = Path(tempfile.mkdtemp())
        folder = root / "implementations" / "repo" / "Prod" / "Results"
        folder.mkdir(parents=True)
        (folder / "discussion.json").write_text(json.dumps({
            "hypotheses": [{"id": "H1", "statement": "s", "verdict": "not_supported"}],
            "contribution_type": {"type": "Negative Results", "why": "H1 failed <i>robustly</i>."},
        }), encoding="utf-8")
        return novelty_gate.get_novelty_overview(root)

    def test_it_follows_the_hypotheses_matrix_in_both_languages(self) -> None:
        for lang, (hyp, heading) in {"en": ("Hypotheses vs. Empirical Evidence", "NeurIPS contribution type"),
                                     "es": ("Hipótesis vs Evidencia Empírica", "Tipo de contribución NeurIPS")}.items():
            with self.subTest(lang=lang):
                html = render_novelty(self.overview(), lang)
                card = html.index('id="noveltyContributionType"')
                self.assertLess(html.index(hyp), card)
                self.assertIn(heading, html[card:])
                self.assertIn("Negative Results", html[card:])
                self.assertIn("&lt;i&gt;robustly&lt;/i&gt;", html)
                self.assertNotIn("<i>robustly", html)

    def test_without_a_type_the_card_says_the_review_is_owed(self) -> None:
        html = render_novelty({"hypotheses": [], "discussions": [], "limitations": []}, "en")
        card = html[html.index('id="noveltyContributionType"'):]
        self.assertIn("paper-reviewer", card)


class CatalogueTests(unittest.TestCase):
    def test_both_catalogues_carry_the_new_keys(self) -> None:
        for lang, path in CATALOGUES.items():
            text = path.read_text(encoding="utf-8")
            for key in ("contribution.title", "contribution.why", "contribution.owed",
                        "contribution.type.General", "contribution.type.Theory",
                        "contribution.type.Use-Inspired", "contribution.type.Concept & Feasibility",
                        "contribution.type.Negative Results"):
                with self.subTest(lang=lang, key=key):
                    self.assertRegex(text, r'"' + re.escape(key) + r'"\s*:')


class DoctrineTests(unittest.TestCase):
    def test_the_reviewer_and_both_phases_name_the_artifact_they_fill(self) -> None:
        reviewer = (REPO / ".claude" / "agents" / "paper-reviewer.md").read_text(encoding="utf-8")
        self.assertIn("## Findings mode", reviewer)
        self.assertIn("contribution_type", reviewer)
        for skill in ("proposal-deliberation", "proposal-implementation", "experimental-implementation"):
            with self.subTest(skill=skill):
                text = (REPO / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")
                self.assertIn("contribution_type", text)
                self.assertIn("paper-reviewer", text)


if __name__ == "__main__":
    unittest.main()
