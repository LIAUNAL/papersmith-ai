"""The math panel's page wiring: KaTeX loaded, the static MONEEG pseudo-math
gone, and the tutor's composer and safe rendering in place."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from skills._core.command_center import server

STATIC = Path(server.__file__).resolve().parent / "static"
PAGE = (STATIC / "index.html").read_text(encoding="utf-8")
SCRIPT = (STATIC / "math-panel.js").read_text(encoding="utf-8")


class PageTests(unittest.TestCase):
    def section(self) -> str:
        start = PAGE.index('<div id="modelSecMatematico"')
        return PAGE[start:PAGE.index('<!-- TAB: EXPERIMENTS', start)]

    def test_katex_and_the_panel_script_are_loaded(self) -> None:
        self.assertIn('<link rel="stylesheet" href="./vendor/katex/katex.min.css">', PAGE)
        self.assertIn('<script src="./vendor/katex/katex.min.js"></script>', PAGE)
        self.assertIn('<script src="./math-panel.js?v=', PAGE)

    def test_the_math_section_is_data_driven_not_hand_typed(self) -> None:
        section = self.section()
        for element in ("mathLema", "mathStack", "mathNoveltyCard", "tutorPanel", "tutorThread",
                        "tutorInput", "tutorSend", "tutorAttach", "tutorFile", "tutorMeter"):
            self.assertIn(f'id="{element}"', section)
        for pseudo in ("v_meas,i(t)", "min_{", "log10 [", "ADS1299"):
            self.assertNotIn(pseudo, section)
        for mode in ("ask", "explain", "evaluate"):
            self.assertIn(f'data-tutor-mode="{mode}"', section)

    def test_the_other_model_modules_and_the_tab_survive(self) -> None:
        for module in ("modelSecPropuesta", "modelSecMapa"):
            self.assertIn(f'id="{module}"', PAGE)
        self.assertIn("if (window.refreshMathPanel) window.refreshMathPanel();", PAGE)

    def test_math_and_concept_map_panels_offer_the_tex_source_toggle(self) -> None:
        math = self.section()
        start = PAGE.index('<div id="modelSecMapa"')
        concept_map = PAGE[start:PAGE.index('<div id="modelSecMatematico"')]
        for panel in (math, concept_map):
            self.assertIn('data-math-toggle', panel)
            self.assertIn('aria-pressed="false"', panel)
        self.assertIn('[data-math-view="source"] .tex-dual__out', PAGE)
        self.assertIn('[data-math-view="source"] .tex-dual__src', PAGE)

    def test_the_banner_follows_the_theme(self) -> None:
        start = PAGE.index('<div class="model-header-banner">')
        banner = PAGE[start:PAGE.index('<!-- Sub-navigation Filter Bar -->')]
        for fixed in ("color: #fff", "color: #94a3b8", "color: #f59e0b"):
            self.assertNotIn(fixed, banner)
        self.assertIn('[data-theme="light"] .model-header-banner', PAGE)


class SafeRenderingTests(unittest.TestCase):
    def render(self, text: str) -> str:
        """Run math-panel.js's richText in node with a stub KaTeX."""
        script = (
            "const fs=require('fs');global.window={katex:{renderToString:(t,o)=>'<K'+(o.displayMode?'D':'I')+'>'+t+'</K>'}};"
            "global.document={addEventListener(){}};"
            f"eval(fs.readFileSync({json.dumps(str(STATIC / 'math-panel.js'))},'utf8'));"
            "console.log(window.mathRichText(fs.readFileSync(0,'utf8')));"
        )
        return subprocess.run(["node", "-e", script], input=text, capture_output=True, text=True,
                              cwd=tempfile.gettempdir(), check=True).stdout.strip()

    def test_model_text_cannot_inject_html(self) -> None:
        out = self.render('<img src=x onerror=alert(1)> **ok**')
        self.assertNotIn("<img", out)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", out)
        self.assertIn("<strong>ok</strong>", out)

    def test_inline_and_display_math_go_to_katex(self) -> None:
        out = self.render("Mira $k(x,x')$ y\n\n$$\\lvert a \\rvert^2$$")
        self.assertIn("<KI>k(x,x')</K>", out)
        self.assertIn("<KD>\\lvert a \\rvert^2</K>", out)

    def test_every_formula_keeps_its_escaped_latex_source_beside_the_rendering(self) -> None:
        out = self.render("Mira $a<b$ y\n\n$$\\frac{1}{2}$$")
        self.assertIn('<span class="tex-dual"><span class="tex-dual__out"><KI>a<b</K></span>'
                      '<code class="tex-dual__src" translate="no">$a&lt;b$</code></span>', out)
        self.assertIn('<code class="tex-dual__src" translate="no">$$\\frac{1}{2}$$</code>', out)
        self.assertIn('class="tex-dual tex-dual--block"', out)

    def test_concept_map_text_renders_math_and_stays_escaped(self) -> None:
        script = (
            "const fs=require('fs');global.window={katex:{renderToString:(t,o)=>'<K>'+t+'</K>'}};"
            "const els={};global.document={addEventListener(){},getElementById:(id)=>(els[id]=els[id]||{})};"
            f"eval(fs.readFileSync({json.dumps(str(STATIC / 'math-panel.js'))},'utf8'));"
            f"eval(fs.readFileSync({json.dumps(str(STATIC / 'model-panel.js'))},'utf8'));"
            "window.renderModelModules({conceptual_map:{layers:[{layer:'L1',desc:'Mapa $x_i$ <b>'}]},"
            "novelty:{pillars:[{name:'P',summary:'Usa $\\\\theta$'}],hypotheses:[{title:'H',statement:'$y$'}]}});"
            "console.log(els.modelConceptLayers.innerHTML+els.modelPillarGrid.innerHTML+els.modelHypothesisGrid.innerHTML);"
        )
        out = subprocess.run(["node", "-e", script], capture_output=True, text=True,
                             cwd=tempfile.gettempdir(), check=True).stdout
        self.assertIn("<K>x_i</K>", out)
        self.assertIn("<K>\\theta</K>", out)
        self.assertIn("<K>y</K>", out)
        self.assertIn("&lt;b&gt;", out)
        self.assertNotIn("<b>", out)


if __name__ == "__main__":
    unittest.main()


class HelperShadowingTests(unittest.TestCase):
    """A parameter named like a top-level helper hides it inside that
    function: `renderMeter(level)` called `level(i)` on a number and the
    tutor meter threw `level is not a function` on every render."""

    def test_no_function_parameter_shadows_a_top_level_helper(self) -> None:
        import re
        for name in ("math-panel.js", "experiments-tutor.js"):
            source = (STATIC / name).read_text(encoding="utf-8")
            helpers = set(re.findall(r"^  const (\w+) = \(", source, re.M))
            for match in re.finditer(r"function \w+\(([^)]*)\)", source):
                params = {p.strip().split("=")[0].strip() for p in match.group(1).split(",") if p.strip()}
                with self.subTest(script=name, signature=match.group(0)):
                    self.assertFalse(params & helpers, f"{params & helpers} shadows a helper")
