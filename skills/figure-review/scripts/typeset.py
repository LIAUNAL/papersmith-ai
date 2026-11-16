"""typeset: the vector verdicts `measure` reads from the figure PDF itself,
not from its raster (specs S2, S3, S4 of
`odd/tasks/figure-and-table-quality.md`).

    printed-font-range  every text span, at its printed size, is between
                        0.70 and 0.90 x the manuscript body (`print_scale`)
    background        no filled rectangle covering the page
    whitespace        no margin wider than `figure_dimensions.MAX_MARGIN_PT`
    in-figure-title   no title row above the plotting area

and one advisory beside them (spec S2 of `odd/tasks/daprosero-backlog.md`):

    numeric-text      values printed inside the figure (a score in a panel
                      title, an isolated value annotation): they duplicate
                      the prose and belong in the text or a table. Aligned
                      tick labels are not values. Reported, never a failure.

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
#: Advisory checks read from the figure PDF; they report, never fail.
VECTOR_ADVISORIES = ("numeric-text",)
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


TEX_PT_TO_PDF_PT = 72.0 / 72.27


def _mediabox_width(pdf: Path) -> float | None:
    try:
        import print_scale
        document = print_scale.pdfium.PdfDocument(str(pdf))
    except Exception:  # an absent reader or an unreadable PDF: the width stays unknown
        return None
    try:
        left, _, right, _ = document[0].get_mediabox()
        return float(right - left)
    except Exception:
        return None
    finally:
        document.close()


def printed_width_from_manuscript(pdf: Path, placement: dict | None) -> tuple:
    """`(printed width in PDF points or None, source, detail)` for the
    figure's first `\\includegraphics` in the manuscript (`page_space`).
    `None` with source `natural` when the manuscript does not place it or
    its width cannot be resolved; `detail` says why."""
    if placement is None:
        return None, "natural", "the manuscript does not include this figure"
    first = placement["first"]
    detail = {"includegraphics": first["path"], "options": first["source"],
              "placements": placement["count"]}
    if first["widthPt"] is not None:
        return round(first["widthPt"] * TEX_PT_TO_PDF_PT, 3), "manuscript", detail
    if first.get("scale") is not None:
        natural = _mediabox_width(pdf)
        if natural is not None:
            return round(first["scale"] * natural, 3), "manuscript", detail
    detail["reason"] = "WIDTH_UNRESOLVED"
    return None, "natural", detail


def _unmeasured(reason: str) -> dict:
    return {name: {"verdict": "unmeasured", "reason": reason}
            for name in VECTOR_DIMENSIONS + VECTOR_ADVISORIES}


#: A value: a decimal number, a percentage, or a number after a relation sign.
_VALUE_RE = re.compile(r"(?<![\w.])[-\u2212+]?\d+\.\d+|\d+(?:\.\d+)?\s?%|[=<>\u2248\u2264\u2265\u00b1]\s*[-\u2212]?\.?\d")
_WORD_RE = re.compile(r"[A-Za-z]{2,}")
_STANDALONE_RE = re.compile(r"^[-\u2212+]?(?:\d+\.\d+|\d+(?:\.\d+)?%)$")
_ALIGN_PT = 1.0


def _text_rows(spans: list) -> list:
    """Upright spans grouped into rows by vertical overlap; every rotated
    span is a row of its own."""
    rows: list = []
    for span in sorted(spans, key=lambda item: (-item["bbox"][3], item["bbox"][0])):
        if abs(span.get("angle_deg", 0.0)) >= 1.0:
            rows.append([span])
            continue
        bottom, top = span["bbox"][1], span["bbox"][3]
        for row in rows:
            if abs(row[0].get("angle_deg", 0.0)) >= 1.0:
                continue
            r_bottom = min(item["bbox"][1] for item in row)
            r_top = max(item["bbox"][3] for item in row)
            overlap = min(top, r_top) - max(bottom, r_bottom)
            if overlap >= 0.5 * min(top - bottom, r_top - r_bottom):
                row.append(span)
                break
        else:
            rows.append([span])
    return [sorted(row, key=lambda item: item["bbox"][0]) for row in rows]


def _aligned(span: dict, others: list) -> bool:
    """True when at least two other numeric spans share this span's row
    (bottom edge) or column (right edge or centre): a tick-label set."""
    left, bottom, right, _ = span["bbox"]
    centre = (left + right) / 2
    same_row = sum(1 for other in others if abs(other["bbox"][1] - bottom) <= _ALIGN_PT)
    same_col = sum(1 for other in others
                   if abs(other["bbox"][2] - right) <= _ALIGN_PT
                   or abs((other["bbox"][0] + other["bbox"][2]) / 2 - centre) <= _ALIGN_PT)
    return same_row >= 2 or same_col >= 2


def numeric_text(spans: list) -> dict:
    """`numeric-text`: a row of words carrying a value (`Model A (acc =
    0.93)`, `n = 120`, `87.5%`), or an isolated decimal or percentage not
    aligned with two other numbers the way tick labels are. Advisory."""
    if not spans:
        return {"verdict": "unmeasured", "reason": "NO_TEXT_LAYER", "items": []}
    numeric = [span for span in spans if _STANDALONE_RE.match(span["text"].strip())
               or re.fullmatch(r"[-\u2212+]?\d+", span["text"].strip())]
    items = []
    for row in _text_rows(spans):
        text = " ".join(span["text"] for span in row)
        box = [min(s["bbox"][0] for s in row), min(s["bbox"][1] for s in row),
               max(s["bbox"][2] for s in row), max(s["bbox"][3] for s in row)]
        if _WORD_RE.search(text) and _VALUE_RE.search(text):
            items.append({"text": text, "kind": "value-in-text", "bbox": [round(v, 3) for v in box]})
            continue
        for span in row:
            if not _STANDALONE_RE.match(span["text"].strip()):
                continue
            others = [other for other in numeric if other is not span]
            if not _aligned(span, others):
                items.append({"text": span["text"], "kind": "value-annotation",
                              "bbox": [round(v, 3) for v in span["bbox"]]})
    return {
        "verdict": "advisory" if items else "pass",
        "reason": "NUMERIC_TEXT_IN_FIGURE" if items else None,
        "items": items,
    }


def measure_pdf(pdf: Path, *, body_pt: float, body_source: str,
                printed_width_pt: float | None, printed_width_source: str = "natural") -> dict:
    """The four vector dimensions for `pdf`, keyed by roster name, plus the
    `numeric-text` advisory."""
    try:
        import print_scale
    except ImportError:
        return _unmeasured("PDF_READER_ABSENT")
    if not getattr(print_scale, "pdf_reader_available", lambda: True)():
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
    font_range["printedWidthSource"] = printed_width_source
    return {
        "printed-font-range": font_range,
        "background": figure_dimensions.background_verdict(bounds["full_page_background"]),
        "whitespace": figure_dimensions.whitespace_verdict(bounds["margins"]),
        "in-figure-title": figure_dimensions.in_figure_title(spans, path_boxes, bounds["mediabox"]),
        "numeric-text": numeric_text(spans),
    }
