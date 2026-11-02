"""figure-review `measure`: the vector verdicts read from the figure PDF
(specs S2, S3, S4 of `odd/tasks/figure-and-table-quality.md`).

`printed-font-range` (formerly `min-printed-font`; spec S2 of
`odd/tasks/manuscript-polish-0-54.md` added the 0.90 x body cap)
replaces the old `legibility: unmeasured
(LEGIBILITY_IS_A_THRESHOLD_JUDGEMENT)` silence; `background`,
`whitespace` and `in-figure-title` are new verdict dimensions. Every case
runs the public verb (`review_cli.py measure`) as a subprocess against a
raster stand-in (a real PNG plus `raster-provenance.json`, the two files a
prior `raster` call writes) and a figure PDF compiled at test time with
`pdflatex` from `tests/fixtures/plot_figures/`. PDF cases skip with a
stated reason when `pdflatex` is not on PATH.
"""

from __future__ import annotations

import json
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

FORGE_ROOT = Path(__file__).resolve().parents[1]
REVIEW_CLI = FORGE_ROOT / "skills" / "figure-review" / "scripts" / "review_cli.py"
FIXTURES = FORGE_ROOT / "tests" / "fixtures" / "plot_figures"
sys.path.insert(0, str(FORGE_ROOT / "skills" / "_core" / "figure"))
import figure_dimensions  # noqa: E402

PDFLATEX = shutil.which("pdflatex")
NO_PDFLATEX = "pdflatex is not on PATH; the figure PDFs are compiled at test time"

VECTOR = ("printed-font-range", "background", "whitespace", "in-figure-title")


def _gray_png(width: int = 6, height: int = 6) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    rows = b"".join(b"\x00" + b"\xff" * width for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


class _MeasureCase(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.tmp = Path(holder.name).resolve()
        self.figures = self.tmp / "paper" / "Figures"
        self.figures.mkdir(parents=True)

    def _figure(self, name: str) -> Path:
        """Compile `<name>.tex` into `paper/Figures/` and leave the raster
        stand-in `measure` requires in `--out`."""
        tex = self.figures / f"{name}.tex"
        shutil.copy(FIXTURES / f"{name}.tex", tex)
        if name == "raster":
            (self.figures / "dot.png").write_bytes(_gray_png(16, 16))
        subprocess.run(
            [PDFLATEX, "-interaction=nonstopmode", "-halt-on-error", tex.name],
            cwd=str(self.figures), capture_output=True, check=True, timeout=120,
        )
        return self.figures / f"{name}.pdf"

    def _raster_stand_in(self, pdf: Path) -> Path:
        out = self.tmp / "scratch" / pdf.stem
        out.mkdir(parents=True)
        (out / f"{pdf.stem}.png").write_bytes(_gray_png())
        (out / "raster-provenance.json").write_text(json.dumps({
            "tool": "pdftoppm", "dpi": 150, "dpiSource": "flag", "colorModel": "gray",
        }), encoding="utf-8")
        return out

    def _measure(self, pdf: Path, *extra: str) -> dict:
        out = self._raster_stand_in(pdf)
        proc = subprocess.run(
            [sys.executable, str(REVIEW_CLI), "measure", "--pdf", str(pdf), "--out", str(out), *extra],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        on_disk = json.loads((out / "visual-report.json").read_text(encoding="utf-8"))
        self.assertEqual(on_disk["dimensions"], payload["dimensions"])
        return payload["dimensions"]


class RosterTests(unittest.TestCase):
    def test_legibility_is_replaced_by_measured_vector_dimensions(self) -> None:
        self.assertNotIn("legibility", figure_dimensions.ALL_DIMENSIONS)
        for name in VECTOR:
            self.assertIn(name, figure_dimensions.VERDICT_DIMENSIONS)
            self.assertEqual(figure_dimensions.DEFAULT_REASONS[name], "PDF_NOT_MEASURED")

    def test_min_printed_font_is_a_deprecated_alias_of_the_range(self) -> None:
        self.assertNotIn("min-printed-font", figure_dimensions.ALL_DIMENSIONS)
        self.assertEqual(figure_dimensions.DEPRECATED_DIMENSION_ALIASES,
                         {"min-printed-font": "printed-font-range"})


class UnreadablePdfTests(_MeasureCase):
    """Prior behavior: `measure` still answers from the raster when the PDF
    beside it cannot be read; the vector dimensions say why they are
    unmeasured instead of failing the call."""

    def test_a_stub_pdf_leaves_the_vector_dimensions_unmeasured(self) -> None:
        pdf = self.figures / "stub.pdf"
        pdf.write_bytes(b"%PDF-1.4 stub\n%%EOF\n")
        dimensions = self._measure(pdf)
        self.assertEqual(sorted(dimensions), sorted(figure_dimensions.ALL_DIMENSIONS))
        for name in VECTOR:
            self.assertEqual(dimensions[name]["verdict"], "unmeasured")
            self.assertEqual(dimensions[name]["reason"], "PDF_UNREADABLE")
        self.assertEqual(dimensions["overlap"]["verdict"], "pass")


@unittest.skipUnless(PDFLATEX, NO_PDFLATEX)
class VectorVerdictTests(_MeasureCase):
    def test_a_compliant_plot_passes_every_vector_dimension(self) -> None:
        dimensions = self._measure(self._figure("compliant"), "--body-pt", "10")
        for name in VECTOR:
            self.assertEqual(dimensions[name]["verdict"], "pass", (name, dimensions[name]))

    def test_an_in_figure_title_fails_naming_the_title(self) -> None:
        dimensions = self._measure(self._figure("titled"))
        title = dimensions["in-figure-title"]
        self.assertEqual(title["verdict"], "fail")
        self.assertEqual(title["reason"], "TITLE_BELONGS_IN_CAPTION")
        self.assertEqual([item["text"] for item in title["titles"]], ["Accuracy versus training epoch"])

    def test_a_legend_row_above_the_axes_is_not_a_title(self) -> None:
        dimensions = self._measure(self._figure("legend-above"))
        self.assertEqual(dimensions["in-figure-title"]["verdict"], "pass")

    def test_a_full_page_background_fails(self) -> None:
        dimensions = self._measure(self._figure("background"))
        self.assertEqual(dimensions["background"]["verdict"], "fail")
        self.assertEqual(dimensions["background"]["reason"], "FULL_PAGE_BACKGROUND")

    def test_wide_margins_fail_whitespace(self) -> None:
        whitespace = self._measure(self._figure("wide-margins"))["whitespace"]
        self.assertEqual(whitespace["verdict"], "fail")
        self.assertEqual(whitespace["wide"], ["bottom", "left", "right", "top"])

    def test_tiny_ticks_fail_the_floor_at_the_declared_width(self) -> None:
        pdf = self._figure("tiny-ticks")
        font = self._measure(pdf, "--printed-width-pt", "343.7", "--body-pt", "10")["printed-font-range"]
        self.assertEqual(font["verdict"], "fail")
        self.assertEqual(font["reason"], "TEXT_BELOW_PRINT_FLOOR")
        self.assertEqual(font["minPrintedPt"], 7.0)
        self.assertEqual(font["maxPrintedPt"], 9.0)
        self.assertIn("floor", {item["bound"] for item in font["offending"]})

    def test_body_size_axis_labels_fail_the_cap(self) -> None:
        font = self._measure(self._figure("large-labels"), "--body-pt", "10")["printed-font-range"]
        self.assertEqual(font["verdict"], "fail")
        self.assertEqual(font["reason"], "TEXT_ABOVE_PRINT_CAP")
        self.assertEqual(font["maxPrintedPt"], 9.0)
        self.assertGreater(font["largestPrintedPt"], 9.0)
        self.assertEqual({item["text"] for item in font["offending"]}, {"Training", "epoch", "Accuracy"})
        self.assertEqual({item["bound"] for item in font["offending"]}, {"cap"})

    def test_a_plot_inside_the_range_reports_both_bounds(self) -> None:
        font = self._measure(self._figure("compliant"), "--body-pt", "10")["printed-font-range"]
        self.assertEqual(font["verdict"], "pass", font)
        self.assertGreaterEqual(font["smallestPrintedPt"], 7.0 * 72 / 72.27)
        self.assertLessEqual(font["largestPrintedPt"], 9.0 * 72 / 72.27)

    def test_the_body_size_is_read_from_the_paper_main_tex(self) -> None:
        # 7.5 pt ticks at natural size pass a 10 pt body (floor 7 pt) and fail
        # a 14 pt one (floor 9.8 pt) declared by `paper/main.tex`.
        (self.tmp / "paper" / "main.tex").write_text(
            "\\documentclass[14pt]{extarticle}\n\\begin{document}\n\\end{document}\n", encoding="utf-8",
        )
        font = self._measure(self._figure("compliant"))["printed-font-range"]
        self.assertEqual(font["bodyPt"], 14.0)
        self.assertEqual(font["verdict"], "fail")

    def test_a_raster_only_pdf_cannot_measure_printed_text(self) -> None:
        dimensions = self._measure(self._figure("raster"))
        self.assertEqual(dimensions["printed-font-range"]["verdict"], "unmeasured")
        self.assertEqual(dimensions["printed-font-range"]["reason"], "NO_TEXT_LAYER")
        self.assertEqual(dimensions["in-figure-title"]["verdict"], "unmeasured")


if __name__ == "__main__":
    unittest.main()
