"""Two `figure` defects found while drawing a real acquisition diagram.

1. `figure optimize` pruned `arrows.meta` from a source whose arrow tips
   carry options (`-{Stealth[length=2mm]}`) or are written bare (`-Stealth`),
   so the optimized source no longer compiled.
2. `render`'s audit assumed the A4 article text width (360 pt at 11 pt) when
   the manifest carried no `textWidthPt`, although `paper/main.tex` sets its
   own margins through `geometry`; labels were then measured at the wrong
   print scale.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "skills" / "paper-writing" / "scripts"))
sys.path.insert(0, str(REPO / "skills" / "_core" / "figure"))
import paper_figure  # noqa: E402
import paper_tikz  # noqa: E402
import print_scale  # noqa: E402

HEADER = "\\documentclass[tikz,border=2pt]{standalone}\n\\usetikzlibrary{arrows.meta}\n\\begin{document}\n"
FOOTER = "\\end{document}\n"


def source(body: str) -> str:
    return HEADER + "\\begin{tikzpicture}\n" + body + "\n\\end{tikzpicture}\n" + FOOTER


class ArrowTipDetectionTests(unittest.TestCase):
    def assert_kept(self, body: str) -> None:
        tex = source(body)
        self.assertIn("arrows.meta", paper_tikz.detect_required_libraries(tex))
        self.assertIn("arrows.meta", paper_tikz.optimize(tex).text)

    def test_a_tip_with_options_keeps_the_library(self) -> None:
        self.assert_kept("\\tikzset{flow/.style={-{Stealth[length=2mm]}, draw}}\n\\draw[flow] (0,0) -- (1,0);")

    def test_a_bare_tip_keeps_the_library(self) -> None:
        self.assert_kept("\\draw[-Stealth] (0,0) -- (1,0);")

    def test_a_tip_on_both_ends_keeps_the_library(self) -> None:
        self.assert_kept("\\draw[Latex-Latex] (0,0) -- (1,0);")

    def test_the_braced_tip_without_options_still_keeps_it(self) -> None:
        self.assert_kept("\\draw[-{Stealth}] (0,0) -- (1,0);")

    def test_a_plain_arrow_still_prunes_the_library(self) -> None:
        tex = source("\\draw[->] (0,0) -- (1,0);")
        self.assertNotIn("arrows.meta", paper_tikz.detect_required_libraries(tex))
        self.assertNotIn("arrows.meta", paper_tikz.optimize(tex).text)


A4_TEX_PT = 210 / 25.4 * 72.27


def main_tex(directory: Path, preamble: str) -> Path:
    path = directory / "main.tex"
    path.write_text(preamble + "\\begin{document}\nx\n\\end{document}\n", encoding="utf-8")
    return path


class GeometryTextWidthTests(unittest.TestCase):
    def width(self, preamble: str, manifest: dict | None = None) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            main_tex(Path(tmp), preamble)
            return paper_figure.print_width(Path(tmp), manifest or {})

    def test_geometry_margins_set_the_text_width(self) -> None:
        result = self.width("\\documentclass[11pt,a4paper]{article}\n\\usepackage{geometry}\n"
                            "\\geometry{top=2.5cm,bottom=2.5cm,left=2.5cm,right=2.5cm}\n")
        self.assertAlmostEqual(result["text_width_pt"], A4_TEX_PT - 2 * 2.5 / 2.54 * 72.27, places=2)
        self.assertEqual(result["text_width_source"], "geometry")

    def test_package_options_and_a_shared_margin_are_read(self) -> None:
        result = self.width("\\documentclass[11pt]{article}\n\\usepackage[a4paper,margin=1in]{geometry}\n")
        self.assertAlmostEqual(result["text_width_pt"], A4_TEX_PT - 2 * 72.27, places=2)

    def test_an_explicit_textwidth_wins_over_margins(self) -> None:
        result = self.width("\\documentclass{article}\n\\usepackage[textwidth=400pt,left=1cm]{geometry}\n")
        self.assertAlmostEqual(result["text_width_pt"], 400.0, places=3)

    def test_letter_paper_is_honoured(self) -> None:
        result = self.width("\\documentclass[letterpaper]{article}\n\\usepackage[margin=1in]{geometry}\n")
        self.assertAlmostEqual(result["text_width_pt"], 8.5 * 72.27 - 2 * 72.27, places=2)

    def test_the_manifest_width_still_wins(self) -> None:
        result = self.width("\\documentclass{article}\n\\usepackage[margin=1in]{geometry}\n",
                            {"textWidthPt": 300})
        self.assertEqual((result["text_width_pt"], result["text_width_source"]), (300.0, "manifest"))

    def test_without_geometry_the_class_default_holds(self) -> None:
        result = self.width("\\documentclass[11pt]{article}\n")
        self.assertEqual((result["text_width_pt"], result["text_width_source"]),
                         (print_scale.TEXTWIDTH_PT["article-a4-11pt"], "default"))

    def test_an_unreadable_geometry_falls_back_to_the_default(self) -> None:
        result = self.width("\\documentclass[11pt]{article}\n\\usepackage[top=2cm]{geometry}\n")
        self.assertEqual(result["text_width_source"], "default")


if __name__ == "__main__":
    unittest.main()
