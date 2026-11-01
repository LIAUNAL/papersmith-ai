"""`place` checks a measured figure's PDF before it enters the manuscript
(specs S2, S3, S4 of `odd/tasks/figure-and-table-quality.md`).

Every case goes through the public verb, `paper_cli.main(["place", ...])`.
The figure PDFs are compiled at test time with `pdflatex` from the TikZ
sources under `tests/fixtures/plot_figures/` (plain TikZ drawn like a
plot: a frame, ticks, axis labels; a title, legend, background, wide
border or tiny ticks where a case needs one) into a temporary directory
outside the worktree. Every PDF case skips with a stated reason when
`pdflatex` is not on PATH.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import uuid
import zlib
from pathlib import Path

FORGE_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = FORGE_ROOT / "tests" / "fixtures" / "plot_figures"
sys.path.insert(0, str(FORGE_ROOT / "skills" / "paper-writing" / "scripts"))
import paper_cli  # noqa: E402

PDFLATEX = shutil.which("pdflatex")
NO_PDFLATEX = "pdflatex is not on PATH; the figure PDFs are compiled at test time"


def _png_bytes(width: int = 16, height: int = 16) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    rows = b"".join(b"\x00" + b"\x30\x60\x90" * width for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


class _Compiled:
    """One temporary build directory for the whole module: each fixture is
    compiled at most once."""

    def __init__(self) -> None:
        self._holder = None
        self._built: dict = {}

    def pdf(self, name: str) -> Path:
        if name in self._built:
            return self._built[name]
        if self._holder is None:
            self._holder = tempfile.TemporaryDirectory()
        build = Path(self._holder.name)
        shutil.copy(FIXTURES / f"{name}.tex", build / f"{name}.tex")
        if name == "raster":
            (build / "dot.png").write_bytes(_png_bytes())
        subprocess.run(
            [PDFLATEX, "-interaction=nonstopmode", "-halt-on-error", f"{name}.tex"],
            cwd=str(build), capture_output=True, check=True, timeout=120,
        )
        self._built[name] = build / f"{name}.pdf"
        return self._built[name]

    def cleanup(self) -> None:
        if self._holder is not None:
            self._holder.cleanup()


COMPILED = _Compiled()


def tearDownModule() -> None:  # noqa: N802 (unittest hook)
    COMPILED.cleanup()


class _PlaceCase(unittest.TestCase):
    """A paper tree under the gitignored `implementations/` (paper_cli
    resolves `--paper` inside the repository root), removed on cleanup."""

    MAIN_TEX = "\\documentclass[10pt]{article}\n\\begin{document}\n\\end{document}\n"

    def setUp(self) -> None:
        self.root = (
            FORGE_ROOT / "implementations"
            / f".paper-place-test-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        )
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.paper = self.root / "paper"
        (self.paper / "Figures").mkdir(parents=True)
        (self.paper / "main.tex").write_text(self.MAIN_TEX, encoding="utf-8")
        self.sources = self.root / "sources"
        self.sources.mkdir()

    def _provenance(self, **extra) -> Path:
        path = self.sources / f"provenance-{uuid.uuid4().hex[:6]}.json"
        path.write_text(json.dumps({"run": "campaign-7", **extra}), encoding="utf-8")
        return path

    def _place(self, pdf: Path, provenance: Path, figure_id: str = "result") -> tuple:
        with contextlib.redirect_stdout(io.StringIO()) as buffer:
            code = paper_cli.main([
                "place", "--paper", str(self.paper), "--figure-id", figure_id,
                "--pdf", str(pdf), "--provenance", str(provenance),
            ])
        return code, json.loads(buffer.getvalue())

    def assertRefused(self, pdf: Path, code: str, **provenance) -> dict:  # noqa: N802
        exit_code, payload = self._place(pdf, self._provenance(**provenance))
        self.assertEqual(exit_code, 2, payload)
        self.assertEqual(payload["code"], code, payload)
        self.assertFalse((self.paper / "Figures" / "result.pdf").exists(), "a refusal wrote the figure")
        self.assertFalse((self.paper / "Figures" / "result.provenance.json").exists())
        return payload


@unittest.skipUnless(PDFLATEX, NO_PDFLATEX)
class CompliantPlotPlacesAsBeforeTests(_PlaceCase):
    """Prior behavior: a compliant figure places exactly as it did before
    the checks existed -- same bytes, same provenance, same envelope."""

    def test_a_compliant_plot_is_copied_with_its_provenance_and_the_same_envelope(self) -> None:
        pdf = COMPILED.pdf("compliant")
        provenance = self._provenance()
        code, payload = self._place(pdf, provenance)
        self.assertEqual(code, 0, payload)
        self.assertEqual(
            sorted(payload), ["command", "figureId", "pdf", "provenance", "status"],
        )
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["figureId"], "result")
        self.assertEqual(Path(payload["pdf"]).read_bytes(), pdf.read_bytes())
        self.assertEqual(
            json.loads(Path(payload["provenance"]).read_text(encoding="utf-8")),
            {"run": "campaign-7"},
        )

    def test_a_legend_row_above_the_axes_is_not_a_title(self) -> None:
        code, payload = self._place(COMPILED.pdf("legend-above"), self._provenance())
        self.assertEqual(code, 0, payload)

    def test_a_missing_provenance_run_still_refuses_diagram_source_absent(self) -> None:
        provenance = self.sources / "empty.json"
        provenance.write_text("{}", encoding="utf-8")
        code, payload = self._place(COMPILED.pdf("compliant"), provenance)
        self.assertEqual(code, 2)
        self.assertEqual(payload["code"], "DIAGRAM_SOURCE_ABSENT")


@unittest.skipUnless(PDFLATEX, NO_PDFLATEX)
class PlaceRefusalTests(_PlaceCase):
    """S2: vector PDF with a text layer, no background, no wasted margin.
    S4: no in-figure title. Each refusal has its own stable code and
    writes nothing."""

    def test_an_in_figure_title_refuses_and_points_to_the_caption(self) -> None:
        payload = self.assertRefused(COMPILED.pdf("titled"), "FIGURE_IN_FIGURE_TITLE")
        self.assertIn("Accuracy versus training epoch", payload["detail"])
        self.assertIn("caption", payload["detail"])

    def test_a_full_page_background_refuses(self) -> None:
        payload = self.assertRefused(COMPILED.pdf("background"), "FIGURE_FULL_PAGE_BACKGROUND")
        self.assertIn("transparent=True", payload["detail"])

    def test_margins_wider_than_four_points_refuse(self) -> None:
        payload = self.assertRefused(COMPILED.pdf("wide-margins"), "FIGURE_MARGIN_WASTE")
        self.assertIn('bbox_inches="tight"', payload["detail"])

    def test_a_raster_only_plot_refuses_no_text_layer(self) -> None:
        self.assertRefused(COMPILED.pdf("raster"), "FIGURE_NO_TEXT_LAYER")

    def test_a_declared_image_figure_is_not_held_to_the_plot_text_layer_rule(self) -> None:
        code, payload = self._place(COMPILED.pdf("raster"), self._provenance(figureKind="image"))
        self.assertEqual(code, 0, payload)

    def test_an_unknown_figure_kind_refuses(self) -> None:
        self.assertRefused(COMPILED.pdf("compliant"), "FIGURE_PROVENANCE_INVALID", figureKind="chart")

    def test_an_unreadable_pdf_refuses(self) -> None:
        bogus = self.sources / "bogus.pdf"
        bogus.write_bytes(b"%PDF-1.4 not really\n")
        self.assertRefused(bogus, "FIGURE_PDF_UNREADABLE")


@unittest.skipUnless(PDFLATEX, NO_PDFLATEX)
class PrintedFontFloorTests(_PlaceCase):
    """S3: every text span at its printed size >= 0.70 x body. The printed
    width is `printedWidthFraction` (default 1.0) x the class text width,
    the body size comes from `paper/main.tex`."""

    def test_tiny_tick_labels_refuse_below_the_print_floor(self) -> None:
        payload = self.assertRefused(COMPILED.pdf("tiny-ticks"), "FIGURE_TEXT_BELOW_PRINT_FLOOR")
        self.assertIn("0.70", payload["detail"])

    def test_the_declared_inclusion_width_decides_the_printed_size(self) -> None:
        # 9 pt ticks on a 268 pt-wide figure print at ~11.5 pt across the full
        # 345 pt text width, but at ~5.7 pt when included at 0.5\textwidth.
        code, payload = self._place(
            COMPILED.pdf("compliant"), self._provenance(printedWidthFraction=1.0), figure_id="full-width",
        )
        self.assertEqual(code, 0, payload)
        self.assertRefused(
            COMPILED.pdf("compliant"), "FIGURE_TEXT_BELOW_PRINT_FLOOR", printedWidthFraction=0.5,
        )

    def test_an_out_of_range_width_fraction_refuses(self) -> None:
        self.assertRefused(COMPILED.pdf("compliant"), "FIGURE_PROVENANCE_INVALID", printedWidthFraction=1.5)


@unittest.skipUnless(PDFLATEX, NO_PDFLATEX)
class BodySizeFromMainTexTests(_PlaceCase):
    """A 12 pt manuscript raises the floor to 8.4 pt: the same figure that
    passes in a 10 pt paper at 0.75\\textwidth fails in a 12 pt one."""

    MAIN_TEX = "\\documentclass[12pt]{article}\n\\begin{document}\n\\end{document}\n"

    def test_a_twelve_point_body_raises_the_floor(self) -> None:
        self.assertRefused(
            COMPILED.pdf("compliant"), "FIGURE_TEXT_BELOW_PRINT_FLOOR", printedWidthFraction=0.6,
        )


if __name__ == "__main__":
    unittest.main()
