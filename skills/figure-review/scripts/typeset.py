"""typeset: the vector verdicts `measure` reads from the figure PDF itself,
not from its raster (specs S2, S3, S4 of
`odd/tasks/figure-and-table-quality.md`).

    printed-font-range  every text span, at its printed size, is between
                        0.70 and 0.90 x the manuscript body (`print_scale`)
    background        no filled rectangle covering the page
    whitespace        no margin wider than `figure_dimensions.MAX_MARGIN_PT`
    in-figure-title   no title row above the plotting area

The PDF is read through `skills/_core/figure/print_scale.py` (imported,
never copied); every verdict is decided by `figure_dimensions`' rule
functions, the same ones `paper-writing`'s `place` refuses with. Nothing
here imports `paper-writing`: the body size is read from the paper's own
`\\documentclass[<N>pt]` with this skill's local regex (`findings`), and
the class defaults print_scale knows are all 10 pt.

A PDF that cannot be read (or an interpreter without `pypdfium2`) leaves
the four dimensions `unmeasured` with a named reason; the raster
dimensions are still reported.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import findings  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_core" / "figure"))
import figure_dimensions  # noqa: E402

VECTOR_DIMENSIONS = ("printed-font-range", "background", "whitespace", "in-figure-title")
DEFAULT_BODY_PT = 10.0
_SIZE_OPTION_RE = re.compile(r"^(\d+(?:\.\d+)?)pt$")


def body_pt_from_main_tex(main_tex: Path | None) -> tuple:
    """`(body size in TeX points, source)` from `\\documentclass[<N>pt]`;
    `(10.0, "fallback")` when the file, the class or the option is absent."""
    if main_tex is None:
        return DEFAULT_BODY_PT, "fallback"
    try:
        text = Path(main_tex).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return DEFAULT_BODY_PT, "fallback"
    match = findings._DOCUMENTCLASS_RE.search(text)
    if match is None:
        return DEFAULT_BODY_PT, "fallback"
    for option in (match.group("options") or "").split(","):
        size = _SIZE_OPTION_RE.match(option.strip())
        if size:
            return float(size.group(1)), "option"
    return DEFAULT_BODY_PT, "class-default"


def _unmeasured(reason: str) -> dict:
    return {name: {"verdict": "unmeasured", "reason": reason} for name in VECTOR_DIMENSIONS}


def measure_pdf(pdf: Path, *, body_pt: float, body_source: str,
                printed_width_pt: float | None) -> dict:
    """The four vector dimensions for `pdf`, keyed by roster name."""
    try:
        import print_scale
    except ImportError:
        return _unmeasured("PDF_READER_ABSENT")
    try:
        bounds = print_scale.content_bbox(pdf)
        spans = print_scale.pdf_text_spans(pdf)
        font = print_scale.printed_font_report(pdf, printed_width_pt, body_pt)
        path_boxes = print_scale.drawn_path_boxes(pdf)
    except (print_scale.pdfium.PdfiumError, OSError):
        return _unmeasured("PDF_UNREADABLE")
    font_range = figure_dimensions.printed_font_range_verdict(font)
    font_range["bodySource"] = body_source
    return {
        "printed-font-range": font_range,
        "background": figure_dimensions.background_verdict(bounds["full_page_background"]),
        "whitespace": figure_dimensions.whitespace_verdict(bounds["margins"]),
        "in-figure-title": figure_dimensions.in_figure_title(spans, path_boxes, bounds["mediabox"]),
    }
