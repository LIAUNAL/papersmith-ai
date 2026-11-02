"""`skills/_core/figure/print_scale.py`: body size, span sizes, printed
scale verdict and content bounds (spec S3 of
`odd/tasks/figure-and-table-quality.md`).

Figures are compiled at test time with `pdflatex` into a temporary
directory outside the worktree; every PDF test skips with a stated reason
when `pdflatex` is not on PATH.
"""

from __future__ import annotations

import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

FORGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FORGE_ROOT / "skills" / "_core" / "figure"))
import print_scale  # noqa: E402

PDFLATEX = shutil.which("pdflatex")
NO_PDFLATEX = "pdflatex is not on PATH; the figure PDFs are compiled at test time"

SIZES_TEX = r"""\documentclass[border=4pt]{standalone}
\usepackage{tikz}
\begin{document}
\begin{tikzpicture}
\node at (0,0) {\fontsize{6}{7}\selectfont Small six};
\node at (0,1) {\fontsize{9}{11}\selectfont Nine label};
\node[rotate=90] at (-3,0.5) {\fontsize{9}{11}\selectfont Rotated};
\end{tikzpicture}
\end{document}
"""

#: Two spans inside the 10 pt range [7, 9]: a 7.5 pt tick and an 8.5 pt label
#: (Latin Modern scales freely; Computer Modern would round to 7 and 8 pt).
IN_RANGE_TEX = r"""\documentclass[border=4pt]{standalone}
\usepackage[T1]{fontenc}
\usepackage{lmodern}
\usepackage{tikz}
\begin{document}
\begin{tikzpicture}
\node at (0,0) {\fontsize{7.5}{9}\selectfont Tick};
\node at (0,1) {\fontsize{8.5}{10}\selectfont Label eight};
\end{tikzpicture}
\end{document}
"""

BACKGROUND_TEX = r"""\documentclass[border=0pt]{standalone}
\usepackage{tikz}
\begin{document}
\begin{tikzpicture}
\fill[white] (0,0) rectangle (6,3);
\draw (1,1) rectangle (2,2);
\end{tikzpicture}
\end{document}
"""


def _border_tex(border_pt: int) -> str:
    return (
        "\\documentclass[border=%dpt]{standalone}\n\\usepackage{tikz}\n"
        "\\begin{document}\n\\begin{tikzpicture}\n"
        "\\draw[line width=0.4pt] (0,0) rectangle (2,1);\n"
        "\\end{tikzpicture}\n\\end{document}\n" % border_pt
    )


def _png_bytes(width: int = 8, height: int = 8) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    rows = b"".join(b"\x00" + b"\x80\x20\x20" * width for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


RASTER_TEX = r"""\documentclass[border=0pt]{standalone}
\usepackage{graphicx}
\begin{document}
\includegraphics[width=2in]{dot.png}
\end{document}
"""

#: `tight.pdf` (a 2 cm x 1 cm rectangle, no border) placed 4 cm from the left
#: edge as a form XObject. Its rectangle sits at the form's own origin, so a
#: walk that descends into the form would see it at x = 0 of the page.
FORM_TEX = r"""\documentclass[border=0pt]{standalone}
\usepackage{graphicx}
\begin{document}
\hspace*{4cm}\includegraphics[scale=0.5]{tight.pdf}
\end{document}
"""


def _compile(directory: Path, name: str, source: str) -> Path:
    (directory / f"{name}.tex").write_text(source, encoding="utf-8")
    subprocess.run(
        [PDFLATEX, "-interaction=nonstopmode", "-halt-on-error", f"{name}.tex"],
        cwd=str(directory), capture_output=True, check=True, timeout=120,
    )
    return directory / f"{name}.pdf"


class BodyFontTests(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory(prefix="print_scale_tex_")
        self.dir = Path(self._dir.name)

    def tearDown(self) -> None:
        self._dir.cleanup()

    def _main(self, preamble: str) -> Path:
        path = self.dir / "main.tex"
        path.write_text(preamble + "\n\\begin{document}\nx\n\\end{document}\n", encoding="utf-8")
        return path

    def test_explicit_option_wins(self) -> None:
        self.assertEqual(print_scale.body_font_pt(self._main(r"\documentclass[a4paper,11pt]{article}")), (11.0, "option"))
        self.assertEqual(print_scale.body_font_pt(self._main(r"\documentclass[preprint,12pt]{elsarticle}")), (12.0, "option"))

    def test_known_class_defaults(self) -> None:
        for name in ("article", "elsarticle", "IEEEtran", "llncs"):
            with self.subTest(name=name):
                main = self._main(r"\documentclass[a4paper]{%s}" % name)
                self.assertEqual(print_scale.body_font_pt(main), (10.0, "class-default"))

    def test_fallback_for_unknown_class_or_missing_documentclass(self) -> None:
        self.assertEqual(print_scale.body_font_pt(self._main(r"\documentclass{weirdclass}")), (10.0, "fallback"))
        self.assertEqual(print_scale.body_font_pt(self._main(r"% \documentclass[12pt]{article}")), (10.0, "fallback"))

    def test_commented_documentclass_is_ignored(self) -> None:
        main = self._main("% \\documentclass[12pt]{article}\n\\documentclass[11pt]{article}")
        self.assertEqual(print_scale.body_font_pt(main), (11.0, "option"))


class ThresholdTests(unittest.TestCase):
    def test_min_ratio_and_floor(self) -> None:
        self.assertEqual(print_scale.MIN_RATIO, 0.70)
        self.assertAlmostEqual(print_scale.min_printed_pt(11.0), 7.7)
        self.assertAlmostEqual(print_scale.min_printed_pt(10.0), 7.0)

    def test_max_ratio_and_cap(self) -> None:
        self.assertEqual(print_scale.MAX_RATIO, 0.90)
        self.assertAlmostEqual(print_scale.max_printed_pt(11.0), 9.9)
        self.assertAlmostEqual(print_scale.max_printed_pt(10.0), 9.0)

    def test_declared_width_converts_tex_points_to_pdf_points(self) -> None:
        width = print_scale.declared_width_pt(print_scale.TEXTWIDTH_PT["article-a4-10pt"], 0.5)
        self.assertAlmostEqual(width, 172.5 * 72 / 72.27, places=6)
        self.assertEqual(print_scale.TEXTWIDTH_PT["IEEEtran-twocolumn-columnwidth"], 252.0)


@unittest.skipUnless(PDFLATEX, NO_PDFLATEX)
class PdfMeasurementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._dir = tempfile.TemporaryDirectory(prefix="print_scale_pdf_")
        directory = Path(cls._dir.name)
        cls.sizes = _compile(directory, "sizes", SIZES_TEX)
        cls.in_range = _compile(directory, "in_range", IN_RANGE_TEX)
        cls.background = _compile(directory, "background", BACKGROUND_TEX)
        cls.tight = _compile(directory, "tight", _border_tex(0))
        cls.loose = _compile(directory, "loose", _border_tex(10))
        (directory / "dot.png").write_bytes(_png_bytes())
        cls.raster = _compile(directory, "raster", RASTER_TEX)
        cls.form = _compile(directory, "form", FORM_TEX)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._dir.cleanup()

    def _span(self, text: str) -> dict:
        spans = print_scale.pdf_text_spans(self.sizes)
        found = [span for span in spans if span["text"] == text]
        self.assertEqual(len(found), 1, spans)
        return found[0]

    def test_span_sizes_are_effective_sizes(self) -> None:
        self.assertAlmostEqual(self._span("Small")["size_pt"], 6.0, delta=0.2)
        self.assertAlmostEqual(self._span("six")["size_pt"], 6.0, delta=0.2)
        self.assertAlmostEqual(self._span("Nine")["size_pt"], 9.0, delta=0.2)
        self.assertEqual(sorted(self._span("label")), ["angle_deg", "bbox", "font_size", "size_pt", "text"])

    def test_rotated_text_keeps_its_size_and_records_the_angle(self) -> None:
        span = self._span("Rotated")
        self.assertAlmostEqual(span["size_pt"], 9.0, delta=0.2)
        self.assertAlmostEqual(abs(span["angle_deg"]), 90.0, delta=0.5)
        left, bottom, right, top = span["bbox"]
        self.assertGreater(top - bottom, right - left)

    def test_six_point_span_meets_the_floor_at_scale_one_and_a_half_for_an_eleven_point_body(self) -> None:
        width = print_scale.content_bbox(self.sizes)["mediabox"][2] * 1.5
        report = print_scale.printed_font_report(self.sizes, width, 11.0)
        self.assertAlmostEqual(report["scale"], 1.5, places=4)
        self.assertAlmostEqual(report["smallest_printed_pt"], 9.0, delta=0.3)
        self.assertGreaterEqual(report["smallest_printed_pt"], report["min_printed_pdf_pt"])
        self.assertAlmostEqual(report["min_printed_pt"], 7.7)
        self.assertEqual([item for item in report["offending"] if item["bound"] == "floor"], [])

    def test_nine_point_labels_enlarged_by_one_and_a_half_fail_the_cap(self) -> None:
        width = print_scale.content_bbox(self.sizes)["mediabox"][2] * 1.5
        report = print_scale.printed_font_report(self.sizes, width, 11.0)
        self.assertEqual(report["verdict"], "fail")
        self.assertAlmostEqual(report["max_printed_pt"], 9.9)
        self.assertAlmostEqual(report["max_printed_pdf_pt"], 9.9 * print_scale.TEX_PT_TO_PDF_PT, places=3)
        self.assertAlmostEqual(report["largest_printed_pt"], 13.5, delta=0.3)
        self.assertEqual(sorted(item["text"] for item in report["offending"]), ["Nine", "Rotated", "label"])
        self.assertEqual({item["bound"] for item in report["offending"]}, {"cap"})

    def test_every_span_inside_the_range_passes(self) -> None:
        report = print_scale.printed_font_report(self.in_range, None, 10.0)
        self.assertEqual(report["verdict"], "pass", report["offending"])
        self.assertEqual(report["offending"], [])
        self.assertGreaterEqual(report["smallest_printed_pt"], report["min_printed_pdf_pt"])
        self.assertLessEqual(report["largest_printed_pt"], report["max_printed_pdf_pt"])

    def test_a_span_above_ninety_percent_of_the_body_fails_the_cap(self) -> None:
        report = print_scale.printed_font_report(self.in_range, None, 9.0)
        self.assertEqual(report["verdict"], "fail")
        self.assertEqual(sorted(item["text"] for item in report["offending"]), ["Label", "eight"])
        self.assertEqual({item["bound"] for item in report["offending"]}, {"cap"})

    def test_six_point_span_fails_at_natural_size(self) -> None:
        report = print_scale.printed_font_report(self.sizes, None, 11.0)
        self.assertEqual(report["verdict"], "fail")
        self.assertEqual(report["scale"], 1.0)
        self.assertEqual(sorted(item["text"] for item in report["offending"]), ["Small", "six"])
        for item in report["offending"]:
            self.assertAlmostEqual(item["printed_pt"], 6.0, delta=0.2)
            self.assertEqual(len(item["bbox"]), 4)

    def test_raster_only_pdf_is_unmeasured_with_a_reason(self) -> None:
        report = print_scale.printed_font_report(self.raster, None, 10.0)
        self.assertEqual(report["verdict"], "unmeasured")
        self.assertIn("NO_TEXT_LAYER", report["reason"])
        self.assertEqual(report["span_count"], 0)
        self.assertEqual(print_scale.content_bbox(self.raster)["counts"]["image"], 1)

    def test_full_page_background_is_detected_and_left_out_of_the_content(self) -> None:
        result = print_scale.content_bbox(self.background)
        self.assertTrue(result["full_page_background"])
        self.assertGreater(result["margins"]["left"], 20.0)
        self.assertFalse(print_scale.content_bbox(self.tight)["full_page_background"])
        self.assertFalse(print_scale.content_bbox(self.sizes)["full_page_background"])

    def test_margins_follow_the_border(self) -> None:
        tight = print_scale.content_bbox(self.tight)["margins"]
        loose = print_scale.content_bbox(self.loose)["margins"]
        border_pdf = 10 * print_scale.TEX_PT_TO_PDF_PT
        for side in ("left", "right", "bottom", "top"):
            with self.subTest(side=side):
                self.assertAlmostEqual(tight[side], 0.0, delta=0.5)
                self.assertAlmostEqual(loose[side], border_pdf, delta=0.5)

    def test_a_form_xobject_counts_by_its_page_bounds_not_its_children(self) -> None:
        # The children of a form XObject report bounds in the form's own
        # space; counted, the rectangle would land at the page's left edge.
        result = print_scale.content_bbox(self.form)
        offset = 4 * 72.27 / 2.54 * print_scale.TEX_PT_TO_PDF_PT
        self.assertAlmostEqual(result["margins"]["left"], offset, delta=1.0)
        self.assertAlmostEqual(result["margins"]["right"], 0.0, delta=1.0)
        self.assertEqual(result["counts"], {"text": 0, "image": 0, "path": 0, "other": 1})
        self.assertEqual(print_scale.drawn_path_boxes(self.form), [])

    def test_drawn_path_boxes_skip_the_background_and_keep_each_path(self) -> None:
        boxes = print_scale.drawn_path_boxes(self.background)
        self.assertEqual(len(boxes), 1)
        left, bottom, right, top = boxes[0]
        self.assertGreater(left, 20.0)
        self.assertEqual(len(print_scale.drawn_path_boxes(self.tight)), 1)

    def test_path_is_drawn_is_public(self) -> None:
        self.assertIs(print_scale.path_is_drawn, print_scale._path_is_drawn)


if __name__ == "__main__":
    unittest.main()
