"""figure-review `measure` against the real document (spec S2 of
`odd/tasks/daprosero-backlog.md`, issue #181 items 1-4).

1. The body size comes from the compiled `main.log` when the class sets it
   internally, and the printed width from the figure's `\\includegraphics`
   in `main.tex`; `--printed-width-pt` and `--body-pt` still override, and
   the output names where each value came from.
2. `width-share`: a figure or table printed under 90 % of `\\textwidth` is
   an advisory, never a failure.
3. `page-whitespace`: per page of `main.pdf`, float-only pages and large gaps.
4. `numeric-text`: values printed inside the figure.

Every case runs the public verb (`review_cli.py measure`) as a subprocess and
reads its JSON. The figure and manuscript PDFs are checked in (compiled from
the `.tex` beside them), and the logs are excerpts of real pdfTeX logs, so no
case needs TeX.
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
FIXTURES = FORGE_ROOT / "tests" / "fixtures" / "figure_review_measure"
COMPLIANT_PDF = FORGE_ROOT / "tests" / "fixtures" / "plot_figures" / "compliant.pdf"
sys.path.insert(0, str(FORGE_ROOT / "skills" / "_core" / "figure"))
import figure_dimensions  # noqa: E402

TEX_TO_PDF = 72.0 / 72.27


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


class _Case(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.tmp = Path(holder.name).resolve()
        self.paper = self.tmp / "paper"
        self.figures = self.paper / "Figures"
        self.figures.mkdir(parents=True)

    def _figure(self, source: Path, stem: str | None = None) -> Path:
        pdf = self.figures / f"{stem or source.stem}.pdf"
        shutil.copy(source, pdf)
        return pdf

    def _stub_figure(self, stem: str) -> Path:
        pdf = self.figures / f"{stem}.pdf"
        pdf.write_bytes(b"%PDF-1.4 stub\n%%EOF\n")
        return pdf

    def _manuscript(self, directory: Path) -> None:
        for path in directory.rglob("*"):
            if path.is_file():
                target = self.paper / path.relative_to(directory)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(path, target)

    def _log(self, name: str) -> None:
        shutil.copy(FIXTURES / "logs" / name, self.paper / "main.log")

    def _run(self, pdf: Path, *extra: str) -> tuple:
        out = self.tmp / "scratch" / pdf.stem
        out.mkdir(parents=True, exist_ok=True)
        (out / f"{pdf.stem}.png").write_bytes(_gray_png())
        (out / "raster-provenance.json").write_text(json.dumps({
            "tool": "pdftoppm", "dpi": 150, "dpiSource": "flag", "colorModel": "gray",
        }), encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(REVIEW_CLI), "measure", "--pdf", str(pdf), "--out", str(out), *extra],
            capture_output=True, text=True, timeout=120,
        )
        return proc, out

    def _measure(self, pdf: Path, *extra: str) -> dict:
        proc, out = self._run(pdf, *extra)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        on_disk = json.loads((out / "visual-report.json").read_text(encoding="utf-8"))
        self.assertEqual(on_disk["advisories"], payload["advisories"])
        self.assertEqual(on_disk["sources"], payload["sources"])
        return payload


class BodySizeFromTheLogTests(_Case):
    """Item 1: a class that sets its size internally is read from `main.log`."""

    def test_a_koma_class_without_a_size_option_reads_eleven_points_from_the_log(self) -> None:
        self._manuscript(FIXTURES / "manuscript-koma")
        self._log("scrartcl-internal-11pt.log")
        payload = self._measure(self._stub_figure("numeric"))
        body = payload["sources"]["bodyPt"]
        self.assertEqual((body["value"], body["source"]), (11.0, "log"))
        self.assertIn("scrsize11pt.clo", body["evidence"])

    def test_ieeetran_states_its_size_in_the_log(self) -> None:
        (self.paper / "main.tex").write_text(
            "\\documentclass[conference]{IEEEtran}\n\\begin{document}\n\\end{document}\n",
            encoding="utf-8")
        self._log("ieeetran-10pt.log")
        body = self._measure(self._stub_figure("numeric"))["sources"]["bodyPt"]
        self.assertEqual((body["value"], body["source"]), (10.0, "log"))

    def test_the_log_body_reaches_the_printed_font_verdict(self) -> None:
        self._manuscript(FIXTURES / "manuscript-koma")
        self._log("scrartcl-internal-11pt.log")
        pdf = self._figure(COMPLIANT_PDF, "numeric")
        font = self._measure(pdf)["dimensions"]["printed-font-range"]
        self.assertEqual((font["bodyPt"], font["bodySource"]), (11.0, "log"))

    def test_body_pt_flag_still_wins_over_the_log(self) -> None:
        self._manuscript(FIXTURES / "manuscript-koma")
        self._log("scrartcl-internal-11pt.log")
        body = self._measure(self._stub_figure("numeric"), "--body-pt", "12")["sources"]["bodyPt"]
        self.assertEqual((body["value"], body["source"]), (12.0, "flag"))


class PrintedWidthFromTheManuscriptTests(_Case):
    """Item 1: the printed width is the figure's `\\includegraphics` width."""

    def test_a_textwidth_fraction_resolves_against_the_logged_textwidth(self) -> None:
        self._manuscript(FIXTURES / "manuscript-koma")
        self._log("scrartcl-internal-11pt.log")
        pdf = self._figure(COMPLIANT_PDF, "numeric")
        payload = self._measure(pdf)
        width = payload["sources"]["printedWidthPt"]
        self.assertEqual(width["source"], "manuscript")
        self.assertAlmostEqual(width["value"], 0.5 * 418.25555 * TEX_TO_PDF, places=2)
        self.assertEqual(payload["sources"]["textWidthPt"]["value"], 418.25555)
        self.assertEqual(payload["sources"]["textWidthPt"]["source"], "log")
        font = payload["dimensions"]["printed-font-range"]
        self.assertEqual(font["printedWidthSource"], "manuscript")
        self.assertAlmostEqual(font["printedWidthPt"], width["value"], places=2)

    def test_linewidth_inside_a_minipage_is_the_minipage_width(self) -> None:
        self._manuscript(FIXTURES / "manuscript-koma")
        self._log("scrartcl-internal-11pt.log")
        width = self._measure(self._stub_figure("plain"))["sources"]["printedWidthPt"]
        self.assertAlmostEqual(width["value"], 0.45 * 418.25555 * TEX_TO_PDF, places=2)

    def test_an_input_file_is_read_and_commented_includes_are_not(self) -> None:
        self._manuscript(FIXTURES / "manuscript-koma")
        self._log("scrartcl-internal-11pt.log")
        width = self._measure(self._stub_figure("full"))["sources"]["printedWidthPt"]
        self.assertAlmostEqual(width["value"], 418.25555 * TEX_TO_PDF, places=2)
        absent = self._measure(self._stub_figure("commented-out"))["sources"]["printedWidthPt"]
        self.assertEqual((absent["value"], absent["source"]), (None, "natural"))

    def test_the_geometry_textwidth_is_read_from_the_log(self) -> None:
        (self.paper / "main.tex").write_text(
            "\\documentclass{article}\n\\usepackage[margin=2cm]{geometry}\n"
            "\\usepackage{graphicx}\n\\begin{document}\n\\begin{figure}\n"
            "\\includegraphics[width=0.8\\textwidth]{Figures/numeric}\n\\caption{x}\n"
            "\\end{figure}\n\\end{document}\n", encoding="utf-8")
        self._log("article-geometry.log")
        payload = self._measure(self._stub_figure("numeric"))
        self.assertEqual(payload["sources"]["textWidthPt"]["value"], 500.484)
        self.assertAlmostEqual(payload["sources"]["printedWidthPt"]["value"],
                               0.8 * 500.484 * TEX_TO_PDF, places=2)

    def test_previous_behavior_holds_with_the_flag_and_a_size_option(self) -> None:
        """`--printed-width-pt` overrides the manuscript, and `\\documentclass[11pt]`
        without a log keeps the option as the body source; the roster is unchanged."""
        (self.paper / "main.tex").write_text(
            "\\documentclass[11pt]{article}\n\\usepackage{graphicx}\n\\begin{document}\n"
            "\\begin{figure}\n\\includegraphics[width=0.5\\textwidth]{Figures/numeric}\n"
            "\\caption{x}\n\\end{figure}\n\\end{document}\n", encoding="utf-8")
        pdf = self._figure(COMPLIANT_PDF, "numeric")
        payload = self._measure(pdf, "--printed-width-pt", "200")
        self.assertEqual(sorted(payload["dimensions"]), sorted(figure_dimensions.ALL_DIMENSIONS))
        font = payload["dimensions"]["printed-font-range"]
        self.assertEqual((font["bodyPt"], font["bodySource"]), (11.0, "option"))
        self.assertEqual((font["printedWidthPt"], font["printedWidthSource"]), (200.0, "flag"))
        self.assertIn(font["verdict"], ("pass", "fail"))


class WidthShareTests(_Case):
    """Item 2: a float under 90 % of `\\textwidth` is advisory."""

    def test_a_half_width_figure_is_reported_and_a_full_row_is_not(self) -> None:
        self._manuscript(FIXTURES / "manuscript-koma")
        self._log("scrartcl-internal-11pt.log")
        share = self._measure(self._stub_figure("numeric"))["advisories"]["width-share"]
        self.assertEqual((share["verdict"], share["reason"]), ("advisory", "NARROW_FLOAT"))
        self.assertEqual(share["floor"], 0.9)
        floats = share["floats"]
        self.assertEqual([item["share"] for item in floats], [0.5, 0.9, 1.0])
        self.assertEqual([item["reason"] for item in floats], ["NARROW_FLOAT", None, None])
        self.assertEqual([item["holdsFigure"] for item in floats], [True, False, False])

    def test_a_narrow_table_is_measured_from_its_rules_in_the_pdf(self) -> None:
        self._manuscript(FIXTURES / "manuscript-pages")
        share = self._measure(self._stub_figure("numeric"))["advisories"]["width-share"]
        table = [item for item in share["floats"] if item["kind"] == "table"]
        self.assertEqual(len(table), 1)
        self.assertEqual(table[0]["reason"], "NARROW_FLOAT")
        self.assertLess(table[0]["share"], 0.2)
        self.assertTrue(table[0]["source"].startswith("main.pdf rules (Table 1"))
        figures = [item["share"] for item in share["floats"] if item["kind"] == "figure"]
        self.assertEqual(figures, [0.9, 0.95])

    def test_without_a_manuscript_the_width_share_is_unmeasured(self) -> None:
        share = self._measure(self._stub_figure("numeric"))["advisories"]["width-share"]
        self.assertEqual((share["verdict"], share["reason"]), ("unmeasured", "MANUSCRIPT_SOURCE_ABSENT"))

    def test_a_narrow_float_never_fails_the_call(self) -> None:
        self._manuscript(FIXTURES / "manuscript-koma")
        self._log("scrartcl-internal-11pt.log")
        proc, _ = self._run(self._stub_figure("numeric"))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


class PageWhitespaceTests(_Case):
    """Item 3: float-only pages and large gaps, per page of `main.pdf`."""

    def test_a_forced_float_gap_and_a_float_only_page_are_reported(self) -> None:
        self._manuscript(FIXTURES / "manuscript-pages")
        space = self._measure(self._stub_figure("numeric"))["advisories"]["page-whitespace"]
        self.assertEqual(space["verdict"], "advisory")
        self.assertEqual(space["reason"], ["FLOAT_ONLY_PAGE", "LARGE_GAP"])
        pages = {page["page"]: page for page in space["pages"]}
        self.assertEqual(sorted(pages), [1, 2, 3, 4])
        self.assertTrue(pages[1]["largeGaps"])
        self.assertGreaterEqual(pages[1]["largestGapPt"], 200.0)
        self.assertFalse(pages[1]["floatOnly"])
        self.assertFalse(pages[2]["floatOnly"])
        self.assertTrue(pages[3]["floatOnly"])
        self.assertEqual(pages[3]["captions"], ["Figure 2", "Table 1"])
        self.assertEqual(pages[4]["largeGaps"], [])
        self.assertFalse(pages[4]["floatOnly"])

    def test_without_a_manuscript_pdf_the_report_is_unmeasured(self) -> None:
        (self.paper / "main.tex").write_text(
            "\\documentclass{article}\n\\begin{document}\n\\end{document}\n", encoding="utf-8")
        space = self._measure(self._stub_figure("numeric"))["advisories"]["page-whitespace"]
        self.assertEqual((space["verdict"], space["reason"]), ("unmeasured", "MANUSCRIPT_PDF_ABSENT"))

    def test_an_unreadable_manuscript_pdf_is_unmeasured(self) -> None:
        (self.paper / "main.pdf").write_bytes(b"%PDF-1.4 stub\n%%EOF\n")
        space = self._measure(self._stub_figure("numeric"))["advisories"]["page-whitespace"]
        self.assertEqual((space["verdict"], space["reason"]), ("unmeasured", "PDF_UNREADABLE"))


class NumericTextTests(_Case):
    """Item 4: values printed inside the figure are flagged; tick labels are not."""

    def test_a_score_in_a_title_and_an_isolated_value_are_flagged(self) -> None:
        pdf = self._figure(FIXTURES / "figures" / "numeric.pdf")
        numeric = self._measure(pdf)["advisories"]["numeric-text"]
        self.assertEqual((numeric["verdict"], numeric["reason"]), ("advisory", "NUMERIC_TEXT_IN_FIGURE"))
        found = {(item["kind"], item["text"]) for item in numeric["items"]}
        self.assertIn(("value-in-text", "Model A (acc = 0.93)"), found)
        self.assertIn(("value-annotation", "0.87"), found)
        self.assertEqual(len(found), 2, found)

    def test_tick_labels_alone_are_not_values(self) -> None:
        pdf = self._figure(FIXTURES / "figures" / "plain.pdf")
        numeric = self._measure(pdf)["advisories"]["numeric-text"]
        self.assertEqual((numeric["verdict"], numeric["items"]), ("pass", []))

    def test_an_unreadable_figure_leaves_the_check_unmeasured(self) -> None:
        numeric = self._measure(self._stub_figure("numeric"))["advisories"]["numeric-text"]
        self.assertEqual((numeric["verdict"], numeric["reason"]), ("unmeasured", "PDF_UNREADABLE"))


if __name__ == "__main__":
    unittest.main()
