"""The shared diagram audit (`skills/_core/figure/diagram_audit.py`), specs S1
and S3 of `odd/tasks/figure-and-table-quality.md`: no relative size switch,
no overfull box, no overlapping text, every label within [0.70, 0.90] x the
body size at the printed width (the cap is spec S2 of
`odd/tasks/manuscript-polish-0-54.md`), no background and no wasted margin.

Each crafted TikZ source under `tests/fixtures/diagram_audit/` is compiled
with the machine's `pdflatex` into a temporary directory; the PDF checks are
skipped when no TeX is installed (CI may have none), the source and log
checks are not.
"""
from __future__ import annotations

import glob
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "skills" / "_core" / "figure"))
import diagram_audit  # noqa: E402
import print_scale  # noqa: E402

FIXTURES = REPO / "tests" / "fixtures" / "diagram_audit"
TEX_DIRS = ("/Library/TeX/texbin", "/usr/local/texlive/*/bin/*", "/opt/homebrew/bin")


def _pdflatex() -> str | None:
    found = shutil.which("pdflatex")
    if found:
        return found
    for pattern in TEX_DIRS:
        for directory in sorted(glob.glob(pattern), reverse=True):
            candidate = Path(directory) / "pdflatex"
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)
    return None


PDFLATEX = _pdflatex()


class _Compiled:
    """Every fixture compiled once, into one temporary directory."""

    _dir: Path | None = None

    @classmethod
    def get(cls, name: str) -> tuple[Path, str, str]:
        if cls._dir is None:
            cls._dir = Path(tempfile.mkdtemp(prefix="diagram-audit-"))
        pdf = cls._dir / f"{name}.pdf"
        if not pdf.is_file():
            shutil.copyfile(FIXTURES / f"{name}.tex", cls._dir / f"{name}.tex")
            subprocess.run([PDFLATEX, "-no-shell-escape", "-interaction=nonstopmode", f"{name}.tex"],
                           cwd=cls._dir, capture_output=True, timeout=120, check=False)
        tex = (FIXTURES / f"{name}.tex").read_text(encoding="utf-8")
        log = (cls._dir / f"{name}.log").read_text(encoding="utf-8", errors="replace")
        return pdf, tex, log


def tearDownModule() -> None:
    if _Compiled._dir is not None:
        shutil.rmtree(_Compiled._dir, ignore_errors=True)


def _audit(name: str, *, body_pt: float = 10.0, printed_width_pt: float | None = None) -> dict:
    pdf, tex, log = _Compiled.get(name)
    return diagram_audit.audit_diagram(pdf, body_pt=body_pt, printed_width_pt=printed_width_pt,
                                       tex_text=tex, log_text=log)


class SourceRuleTests(unittest.TestCase):
    """The source and log rules, measurable without TeX."""

    def test_a_relative_size_switch_is_found_with_its_line(self) -> None:
        tex = (FIXTURES / "relative_switch.tex").read_text(encoding="utf-8")
        found = diagram_audit.find_size_switches(tex)
        self.assertEqual(found, [{"switch": "\\small", "line": 6}])

    def test_every_relative_switch_counts_and_an_explicit_fontsize_does_not(self) -> None:
        for switch in diagram_audit.RELATIVE_SIZE_SWITCHES:
            with self.subTest(switch=switch):
                self.assertEqual(len(diagram_audit.find_size_switches(f"\\node[font=\\{switch}] {{x}};")), 1)
        self.assertEqual(diagram_audit.find_size_switches(r"\fontsize{8}{9.6}\selectfont \smallskip"), [])
        self.assertEqual(diagram_audit.find_size_switches(r"a \% b % \tiny"), [])

    def test_an_overfull_box_in_the_log_is_reported_verbatim(self) -> None:
        log = ("Overfull \\hbox (4.1pt too wide) in paragraph at lines 7--7\n"
               "Underfull \\hbox (badness 10000)\nOverfull \\vbox (2.0pt too high) detected at line 9\n")
        self.assertEqual(diagram_audit.parse_overfull(log), [
            "Overfull \\hbox (4.1pt too wide) in paragraph at lines 7--7",
            "Overfull \\vbox (2.0pt too high) detected at line 9",
        ])

    def test_every_role_font_lies_inside_the_print_range(self) -> None:
        self.assertEqual(diagram_audit.ROLE_RATIOS, {"claim": 0.88, "spine": 0.82, "note": 0.76})
        for body in (10.0, 11.0, 12.0):
            sizes = diagram_audit.role_font_pt(body)
            for role, size in sizes.items():
                with self.subTest(body=body, role=role):
                    self.assertGreaterEqual(size, print_scale.min_printed_pt(body))
                    self.assertLessEqual(size, print_scale.max_printed_pt(body))
        self.assertEqual(diagram_audit.role_font_pt(11.0), {"claim": 9.68, "spine": 9.02, "note": 8.36})

    def test_role_fonts_print_in_range_when_the_figure_is_shrunk_or_enlarged(self) -> None:
        for scale in (0.5, 1.25):
            sizes = diagram_audit.role_font_pt(10.0, scale=scale)
            with self.subTest(scale=scale):
                self.assertGreaterEqual(min(sizes.values()) * scale, print_scale.min_printed_pt(10.0) - 0.01)
                self.assertLessEqual(max(sizes.values()) * scale, print_scale.max_printed_pt(10.0) + 0.01)
        self.assertEqual(diagram_audit.fontsize_command(9), r"\fontsize{9.00}{10.80}\selectfont")

    def test_an_unreadable_pdf_measures_nothing_and_never_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stub = Path(tmp) / "stub.pdf"
            stub.write_bytes(b"%PDF-1.4 stub\n")
            report = diagram_audit.audit_diagram(stub, body_pt=10, printed_width_pt=None,
                                                 tex_text="% node: box\n", log_text="")
        self.assertEqual(report["verdict"], "unmeasured")
        for name in ("text_overlap", "font_range", "margins"):
            self.assertEqual(report["checks"][name]["verdict"], "unmeasured")
            self.assertTrue(report["checks"][name]["reason"].startswith("PDF_UNREADABLE"))


@unittest.skipUnless(PDFLATEX, "needs pdflatex")
class CompiledDiagramTests(unittest.TestCase):

    def test_a_clean_diagram_passes_every_check(self) -> None:
        report = _audit("clean")
        self.assertEqual(report["verdict"], "pass", report["failures"])
        self.assertEqual(set(report["checks"]),
                         {"overfull", "size_switches", "text_overlap", "font_range", "margins"})

    def test_a_relative_switch_fails_the_audit(self) -> None:
        report = _audit("relative_switch")
        self.assertEqual(report["verdict"], "fail")
        self.assertEqual(report["failures"], ["size_switches"])
        self.assertIn("size_switches: \\small on line 6; use \\fontsize",
                      diagram_audit.failure_messages(report))

    def test_an_overfull_box_fails_the_audit(self) -> None:
        report = _audit("overfull")
        self.assertIn("overfull", report["failures"])
        self.assertRegex(report["checks"]["overfull"]["lines"][0], r"^Overfull \\hbox \(")

    def test_overlapping_labels_and_a_label_crossing_a_frame_are_detected(self) -> None:
        check = _audit("overlap")["checks"]["text_overlap"]
        self.assertEqual(check["verdict"], "fail")
        self.assertIn(["Alpha", "Gamma"], [sorted(item["texts"]) for item in check["span_collisions"]])
        self.assertIn("Crossing", [item["text"] for item in check["boundary_crossings"]])

    def test_text_inside_its_own_frame_is_not_an_overlap(self) -> None:
        check = _audit("clean")["checks"]["text_overlap"]
        self.assertEqual(check["verdict"], "pass")
        self.assertGreaterEqual(check["shape_count"], 2)  # both frames were seen
        self.assertEqual(check["boundary_crossings"], [])

    def test_a_six_point_label_fails_the_floor_of_an_eleven_point_manuscript(self) -> None:
        check = _audit("small_label", body_pt=11)["checks"]["font_range"]
        self.assertEqual(check["verdict"], "fail")
        self.assertEqual(check["min_printed_pt"], 7.7)
        self.assertEqual({item["text"] for item in check["offending"]}, {"Pilot", "tables"})

    def test_the_same_label_enlarged_passes_the_floor(self) -> None:
        check = _audit("enlarged_label", body_pt=11)["checks"]["font_range"]
        self.assertEqual(check["verdict"], "pass")
        self.assertGreaterEqual(check["smallest_printed_pt"], 7.7 * print_scale.TEX_PT_TO_PDF_PT)
        self.assertLessEqual(check["largest_printed_pt"], 9.9 * print_scale.TEX_PT_TO_PDF_PT)

    def test_a_body_size_label_fails_the_cap_of_a_ten_point_manuscript(self) -> None:
        report = _audit("large_label", body_pt=10)
        check = report["checks"]["font_range"]
        self.assertEqual(check["verdict"], "fail")
        self.assertEqual(report["failures"], ["font_range"])
        self.assertEqual(check["max_printed_pt"], 9.0)
        self.assertEqual({item["bound"] for item in check["offending"]}, {"cap"})
        self.assertIn("font_range: 'Pilot' prints at 9.963 pt > 8.9664 pt",
                      diagram_audit.failure_messages(report))

    def test_the_floor_is_read_at_the_declared_width(self) -> None:
        """Placed at a third of its natural width, the 8 pt label prints at
        about 2.7 pt: the declared inclusion width decides, not the source."""
        pdf, _, _ = _Compiled.get("enlarged_label")
        natural = print_scale.content_bbox(pdf)["mediabox"][2]
        check = _audit("enlarged_label", body_pt=11, printed_width_pt=natural / 3)["checks"]["font_range"]
        self.assertEqual(check["verdict"], "fail")

    def test_a_background_canvas_fails_the_margins(self) -> None:
        check = _audit("background")["checks"]["margins"]
        self.assertEqual(check["verdict"], "fail")
        self.assertIsNotNone(check["background_shape"])

    def test_a_clean_diagram_has_no_background_and_tight_margins(self) -> None:
        check = _audit("clean")["checks"]["margins"]
        self.assertIsNone(check["background_shape"])
        self.assertFalse(check["full_page_background"])
        self.assertTrue(all(0 <= value <= diagram_audit.MAX_MARGIN_PT for value in check["margins"].values()))

    def test_wasted_margin_fails(self) -> None:
        check = _audit("wide_margin")["checks"]["margins"]
        self.assertEqual(check["verdict"], "fail")
        self.assertEqual(set(check["wide_sides"]), {"left", "right", "top", "bottom"})


if __name__ == "__main__":
    unittest.main()
