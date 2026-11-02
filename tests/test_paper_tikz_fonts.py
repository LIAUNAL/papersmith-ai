"""Paper diagrams at print size (specs S1 and S3 of
`odd/tasks/figure-and-table-quality.md`), through `paper_tikz.optimize` and
`paper_figure.render`: explicit `\\fontsize` only, and the shared audit
(`skills/_core/figure/diagram_audit.py`) after every successful compile —
a failing audit is a repairable failure that spends one attempt and never
reaches `Figures/<id>.pdf`.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "skills" / "paper-writing" / "scripts"))
import paper_figure  # noqa: E402
import paper_latex  # noqa: E402
import paper_tikz  # noqa: E402

sys.path.insert(0, str(REPO / "skills" / "_core" / "implementation"))
from impl_refusals import Refused  # noqa: E402

sys.path.insert(0, str(REPO / "tests"))
from test_paper_figure import _install_stub_latexmk  # noqa: E402

HEADER = "\\documentclass[tikz,border=2pt]{standalone}\n\\usepackage[T1]{fontenc}\n\\usepackage{lmodern}\n"


def _source(body: str) -> str:
    return (HEADER + "\\begin{document}\n\\begin{tikzpicture}\n% node: box\n"
            + body + "\n\\end{tikzpicture}\n\\end{document}\n")


#: Each picture is drawn at the printed size: a 12.5 cm frame plus the 2 pt
#: border is the 11 pt article text width (~360 pt), so `render`'s default
#: full-width inclusion prints it at scale ~1 and the 9 pt label lands
#: inside [0.70, 0.90] x 11 pt. A tiny picture stretched to the text width
#: would print above the 0.90 x body cap.
WIDE = "draw, minimum width=12.5cm"
CLEAN = _source(r"\node[" + WIDE + r", font=\fontsize{9}{10.8}\selectfont] (box) {Train every arm};")
RELATIVE = _source(r"\node[" + WIDE + r", font=\small] (box) {Train every arm};")
OVERLAP = _source(r"\node[" + WIDE + r", font=\fontsize{9}{10.8}\selectfont] (box) {Train every arm};"
                  "\n" r"\node[font=\fontsize{9}{10.8}\selectfont] at (0.2,0) {Overlap};")


def _latexmk_present() -> bool:
    try:
        paper_latex.discover_latexmk(None)
    except Refused:
        return False
    return True


class _Paper(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory(prefix="paper-tikz-fonts-")
        self.addCleanup(holder.cleanup)
        self.root = Path(holder.name)
        self.paper_dir = self.root / "paper"
        (self.paper_dir / "Figures").mkdir(parents=True)
        (self.paper_dir / "main.tex").write_text(
            "\\documentclass[11pt]{article}\n\\begin{document}\n\\end{document}\n", encoding="utf-8")

    def write(self, figure_id: str, tex: str, **manifest) -> None:
        (self.paper_dir / "Figures" / f"{figure_id}.tex").write_text(tex, encoding="utf-8")
        (self.paper_dir / "Figures" / f"{figure_id}.diagram.json").write_text(
            json.dumps({"components": ["box"], **manifest}), encoding="utf-8")


class OptimizeWarningTests(unittest.TestCase):

    def test_a_relative_switch_is_warned_with_its_line_and_left_as_authored(self) -> None:
        result = paper_tikz.optimize(RELATIVE)
        warnings = [w for w in result.warnings if "relative size switch" in w]
        self.assertEqual(len(warnings), 1)
        self.assertIn("\\small on line 7", warnings[0])
        self.assertIn("\\small", result.text)

    def test_an_explicit_fontsize_is_not_warned(self) -> None:
        self.assertEqual([w for w in paper_tikz.optimize(CLEAN).warnings if "size switch" in w], [])


class StubCompileTests(_Paper):
    """Prior behaviour: a compile the stub reports clean still succeeds; its
    PDF is not a real one, so the audit reads `unmeasured` and does not block."""

    def test_a_stub_success_still_succeeds_with_an_unmeasured_audit(self) -> None:
        bin_dir = self.root / "bin"
        _install_stub_latexmk(bin_dir)
        os.environ["STUB_MODE"] = "success"
        self.addCleanup(os.environ.pop, "STUB_MODE", None)
        self.write("stub", "% node: box\n")
        result = paper_figure.render(self.paper_dir, "stub", path=str(bin_dir))
        self.assertEqual(result["verdict"], "success")
        self.assertEqual(result["audit"]["verdict"], "unmeasured")
        self.assertTrue((self.paper_dir / "Figures" / "stub.pdf").is_file())


@unittest.skipUnless(_latexmk_present(), "needs latexmk")
class RealCompileAuditTests(_Paper):

    def test_a_clean_diagram_succeeds_with_a_passing_audit(self) -> None:
        self.write("clean", CLEAN)
        result = paper_figure.render(self.paper_dir, "clean")
        self.assertEqual(result["verdict"], "success", result)
        self.assertEqual(result["audit"]["verdict"], "pass")
        self.assertEqual(result["audit"]["print"]["body_pt"], 11.0)
        self.assertTrue((self.paper_dir / "Figures" / "clean.pdf").is_file())

    def test_a_relative_switch_is_a_repairable_failure_that_spends_an_attempt(self) -> None:
        self.write("relative", RELATIVE)
        result = paper_figure.render(self.paper_dir, "relative")
        self.assertEqual((result["verdict"], result["attemptsUsed"]), ("failure", 1))
        # Only the switch: `\small` prints 9 pt here, inside the range, so the
        # source rule alone fails it.
        self.assertEqual(result["audit"]["failures"], ["size_switches"])
        self.assertTrue(any(d.startswith("size_switches: \\small") for d in result["diagnostics"]))
        self.assertFalse((self.paper_dir / "Figures" / "relative.pdf").exists())
        self.assertTrue(Path(result["preview"]).is_file())

    def test_overlapping_text_is_a_repairable_failure(self) -> None:
        self.write("overlap", OVERLAP)
        result = paper_figure.render(self.paper_dir, "overlap")
        self.assertEqual(result["verdict"], "failure")
        self.assertEqual(result["audit"]["failures"], ["text_overlap"])

    def test_the_floor_is_read_at_the_manifests_width_fraction(self) -> None:
        """A 9 pt label drawn at the printed width passes; squeezed to 5 % of
        the text width it prints far smaller than 0.70 x 11 pt."""
        self.write("narrow", CLEAN, widthFraction=0.05)
        result = paper_figure.render(self.paper_dir, "narrow")
        self.assertEqual(result["verdict"], "failure")
        self.assertIn("font_range", result["audit"]["failures"])


if __name__ == "__main__":
    unittest.main()
