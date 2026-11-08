"""The Concept Map & Model and Novelty & Findings tabs fold like Experiments:
each block is marked `data-fold` with its title's catalogue key, and
static/section-folds.js wraps it in a bar that folds and remembers it. The
blocks that ask for an action start open, the rest folded."""

from __future__ import annotations

import re
import unittest

from tests.test_command_center_contribution_type import STATIC, _node, _preamble
from tests.test_command_center_experiments import PAGE

MODEL = {"model:problem": ("conceptTree.problem", True), "model:noveltyTree": ("conceptTree.novelty", True),
         "model:pillars": ("model.pillarsTitle", False), "model:hypotheses": ("model.hypothesesTitle", False),
         "model:contribution": ("contribution.title", True), "model:map": ("model.sec2", False),
         "model:math": ("math.title", True)}
NOVELTY = {"novelty:poc": ("novelty.poc.title", True), "novelty:gate": ("novelty.gate.title", True),
           "novelty:hypotheses": ("novelty.hypotheses.title", False),
           "novelty:contribution": ("contribution.title", True), "novelty:sota": ("novelty.sota.title", False),
           "novelty:rigor": ("novelty.rigor.title", False)}


def marks(html: str) -> dict[str, tuple[str, bool]]:
    found = {}
    for tag in re.findall(r"<[a-z]+\b[^>]*\bdata-fold=\"[^\"]+\"[^>]*>", html):
        name = re.search(r'data-fold="([^"]+)"', tag).group(1)
        title = re.search(r'data-fold-title="([^"]+)"', tag)
        found[name] = (title.group(1) if title else "", "data-fold-open" in tag)
    return found


class MarkedBlocksTests(unittest.TestCase):
    def test_the_concept_map_tab_marks_its_blocks_in_flow_order(self) -> None:
        pane = PAGE[PAGE.index('id="pane-modelo"'):PAGE.index('id="pane-experiments"')]
        self.assertEqual(marks(pane), MODEL)
        positions = [pane.index(f'data-fold="{name}"') for name in MODEL]
        self.assertEqual(positions, sorted(positions))
        self.assertLess(pane.index('id="modelFlowSteps"'), pane.index('data-fold="model:problem"'))

    def test_the_novelty_tab_marks_its_summary_and_every_section(self) -> None:
        pane = PAGE[PAGE.index('id="pane-novelty"'):PAGE.index("<!-- TAB 3: SECTIONS -->")]
        self.assertEqual(marks(pane), {"novelty:summary": ("atlas.title.summary", True)})
        script = (_preamble("en")
                  + f"eval(fs.readFileSync({str(STATIC / 'novelty-panel.js')!r},'utf8'));"
                  + "window.NoveltyPanel.render({hypotheses: [], discussions: [], limitations: [],"
                  + " poc_verification: {discussed: 1, decision: {status: 'pending'}}});"
                  + "console.log(els.noveltyRoot.innerHTML);")
        self.assertEqual(marks(_node(script)), NOVELTY)

    def test_every_title_key_is_in_both_catalogues(self) -> None:
        for lang in ("en", "es"):
            catalogue = (STATIC / "i18n" / f"{lang}.js").read_text(encoding="utf-8")
            for key, _ in [*MODEL.values(), *NOVELTY.values(), ("atlas.title.summary", True)]:
                with self.subTest(lang=lang, key=key):
                    self.assertIn(f'"{key}":', catalogue)

    def test_the_page_loads_the_fold_runtime(self) -> None:
        self.assertRegex(PAGE, r'<script src="\./section-folds\.js\?v=[0-9.]+"></script>')
        runtime = (STATIC / "section-folds.js").read_text(encoding="utf-8")
        for needle in ("papersmith.folds", "data-fold", "exp-fold__summary", "localStorage"):
            self.assertIn(needle, runtime)


if __name__ == "__main__":
    unittest.main()
