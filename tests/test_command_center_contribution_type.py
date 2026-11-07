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
        "for (const f of ['i18n/en.js','i18n/es.js','i18n.js','contribution-affinity.js'])"
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


TYPES = ("General", "Theory", "Use-Inspired", "Concept & Feasibility", "Negative Results")


def affinity(**scores: int) -> dict:
    base = dict.fromkeys(TYPES, 10)
    base.update({name.replace("_", " ").replace("Use Inspired", "Use-Inspired")
                 .replace("Concept and Feasibility", "Concept & Feasibility"): value
                 for name, value in scores.items()})
    return {name: {"score": value, "why": f"Why {name} <b>scored</b> {value}."} for name, value in base.items()}


def typed(kind: str = "Theory", **scores: int) -> dict:
    return {"type": kind, "why": "The core is a bound.", "affinity": affinity(**(scores or {"Theory": 90}))}


def load_contract():
    import importlib.util
    spec = importlib.util.spec_from_file_location("ct_for_tests", REPO / "skills/_core/results/contribution_type.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AffinityContractTests(unittest.TestCase):
    """Every type gets a 0-100 affinity and a short reason; the chosen type leads."""

    def setUp(self) -> None:
        self.ct = load_contract()

    def test_a_full_affinity_is_valid_and_kept(self) -> None:
        value = typed()
        self.assertEqual(self.ct.problems(value), [])
        self.assertEqual(self.ct.normalize(value)["affinity"]["Theory"], {"score": 90, "why": "Why Theory <b>scored</b> 90."})

    def test_a_verdict_without_affinity_stays_valid(self) -> None:
        value = {"type": "Theory", "why": "A bound."}
        self.assertEqual(self.ct.problems(value), [])
        self.assertEqual(self.ct.normalize(value), value)

    def test_a_broken_affinity_is_named(self) -> None:
        cases = {
            "missing": ({"type": "Theory", "why": "w", "affinity": {"Theory": {"score": 90, "why": "x"}}},
                        "contribution_type.affinity: must score every type; missing General, Use-Inspired, "
                        "Concept & Feasibility, Negative Results"),
            "range": (typed(Theory=101), "contribution_type.affinity.Theory.score: must be an integer from 0 to 100"),
            "float": (typed(Theory=90.5), "contribution_type.affinity.Theory.score: must be an integer from 0 to 100"),
            "lead": (typed(Theory=40, General=80),
                     "contribution_type.affinity: the chosen type Theory must hold the highest score"),
        }
        for name, (value, message) in cases.items():
            with self.subTest(name):
                self.assertIn(message, self.ct.problems(value))
        long_why = typed()
        long_why["affinity"]["General"]["why"] = "x" * 301
        self.assertIn("contribution_type.affinity.General.why: required, at most 300 characters",
                      self.ct.problems(long_why))

    def test_readers_drop_a_broken_affinity_but_keep_the_type(self) -> None:
        self.assertEqual(self.ct.normalize(typed(Theory=101)), {"type": "Theory", "why": "The core is a bound."})

    def test_the_concept_map_tab_receives_the_affinity(self) -> None:
        spec = model_spec.get_model_specification(_workspace(dict(SPEC, contribution_type=typed())))
        self.assertEqual(spec["contribution_type"]["affinity"]["Theory"]["score"], 90)


class AffinityBarsTests(unittest.TestCase):
    def bars(self, html: str) -> list[tuple[str, str]]:
        return re.findall(r'data-affinity-type="([^"]+)"[^>]*>.*?style="width: (\d+)%', html, re.S)

    def test_the_concept_map_card_shows_a_bar_per_type(self) -> None:
        for lang, heading in {"en": "Affinity by contribution type", "es": "Afinidad por tipo de contribución"}.items():
            with self.subTest(lang=lang):
                html = render_model(dict(SPEC, contribution_type=typed()), lang)["html"]
                self.assertIn(heading, html)
                self.assertEqual(self.bars(html), [("General", "10"), ("Theory", "90"), ("Use-Inspired", "10"),
                                                   ("Concept & Feasibility", "10"), ("Negative Results", "10")])

    def test_a_bar_opens_the_definition_and_the_reason(self) -> None:
        html = render_model(dict(SPEC, contribution_type=typed()), "en")["html"]
        theory = html[html.index('data-affinity-type="Theory"'):html.index('data-affinity-type="Use-Inspired"')]
        self.assertIn("<details", html[:html.index('data-affinity-type="Theory"') + 40])
        self.assertIn("rigor and correctness of the proofs come first", theory)
        self.assertIn("Why Theory &lt;b&gt;scored&lt;/b&gt; 90.", theory)
        self.assertNotIn("<b>scored", html)
        es = render_model(dict(SPEC, contribution_type=typed()), "es")["html"]
        self.assertIn("el rigor y la corrección de las demostraciones van primero", es)

    def test_the_novelty_card_shows_the_bars_too(self) -> None:
        root = Path(tempfile.mkdtemp())
        folder = root / "implementations" / "repo" / "Prod" / "Results"
        folder.mkdir(parents=True)
        (folder / "discussion.json").write_text(json.dumps({
            "hypotheses": [{"id": "H1", "statement": "s", "verdict": "not_supported"}],
            "contribution_type": typed("Negative Results", **{"Negative Results": 85, "Theory": 5}),
        }), encoding="utf-8")
        html = render_novelty(novelty_gate.get_novelty_overview(root), "en")
        card = html[html.index('id="noveltyContributionType"'):]
        self.assertIn(("Negative Results", "85"), self.bars(card))
        self.assertIn(("Theory", "5"), self.bars(card))

    def test_without_affinity_the_types_still_open_their_definitions(self) -> None:
        html = render_model(SPEC, "en")["html"]
        self.assertEqual(html.count("data-affinity-type="), 5)
        self.assertEqual(self.bars(html), [])
        self.assertIn("Run the judge again to score each type.", html)


class AffinityDoctrineTests(unittest.TestCase):
    def test_every_copy_of_the_reviewer_asks_for_the_affinity(self) -> None:
        for folder in (".claude", ".agents", ".opencode", ".pi"):
            with self.subTest(folder=folder):
                text = (REPO / folder / "agents" / "paper-reviewer.md").read_text(encoding="utf-8")
                self.assertIn('"affinity": {<each of the five types>: {"score": <integer 0', text)
                self.assertIn("give the chosen type the\nhighest score", text)


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
