"""paper_place: the print-quality gate `place` runs before a measured
figure enters the manuscript (specs S2, S3, S4 of
`odd/tasks/figure-and-table-quality.md`).

`paper_figure.place_figure` copies the PDF and its provenance; this module
decides, before that copy, whether the PDF may be placed at all. It reads
the figure through `_core/figure/print_scale.py` (imported, never copied)
and decides each verdict with `_core/figure/figure_dimensions.py`'s rule
functions, the same ones `figure-review measure` reports with, so the
gate and the review cannot disagree.

Checks, in this order (the first failing one names the refusal code; the
detail lists every failing one):

    FIGURE_PDF_UNREADABLE          the PDF cannot be opened
    FIGURE_NO_TEXT_LAYER           a plot without a text layer (raster-only,
                                   or text converted to outlines)
    FIGURE_FULL_PAGE_BACKGROUND    a filled rectangle covers the page
    FIGURE_MARGIN_WASTE            a margin wider than MAX_MARGIN_PT
    FIGURE_IN_FIGURE_TITLE         a title row above the plotting area
    FIGURE_TEXT_BELOW_PRINT_FLOOR  a text span prints below 0.70 x body

`FIGURE_PROVENANCE_INVALID` refuses an out-of-domain provenance field, and
`FIGURE_MEASUREMENT_UNAVAILABLE` an interpreter without `pypdfium2`.
`place` had no override flag before these checks, so none is added: the
fix is the figure (or its declared inclusion width), never a waiver.

Two optional provenance fields feed the checks and are copied with the
record, so what the gate assumed stays on disk beside the figure:

    figureKind            "plot" (default) or "image" (a photograph or
                          micrograph: exempt from the text-layer rule only)
    printedWidthFraction  the `\\includegraphics[width=<f>\\textwidth]` the
                          manuscript will use, 0 < f <= 1 (default 1.0)

The body size comes from `paper/main.tex` (`print_scale.body_font_pt`);
the text width from its class and options (`print_scale.TEXTWIDTH_PT`;
the widest plausible setting when the class is ambiguous, so the gate only
refuses what is too small even at full width). Manuscript QA after compile
measures the width actually placed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paper_venue  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_core" / "figure"))
import figure_dimensions  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_core" / "implementation"))
from impl_refusals import Refused  # noqa: E402

FIGURE_KINDS = ("plot", "image")

#: Refusal codes in the order the checks run.
CHECK_ORDER = (
    "FIGURE_NO_TEXT_LAYER",
    "FIGURE_FULL_PAGE_BACKGROUND",
    "FIGURE_MARGIN_WASTE",
    "FIGURE_IN_FIGURE_TITLE",
    "FIGURE_TEXT_BELOW_PRINT_FLOOR",
)


def _print_scale():
    """`print_scale` loads `pypdfium2` at import; imported here, on the
    `place` path only, so every other `paper_cli` verb keeps running on an
    interpreter without it."""
    try:
        import print_scale  # noqa: WPS433
    except ImportError as exc:
        raise Refused(
            "FIGURE_MEASUREMENT_UNAVAILABLE",
            f"cannot measure the figure: {exc}; install pypdfium2 into this interpreter",
        ) from exc
    return print_scale


def text_width_pt(main_tex: Path, print_scale) -> tuple:
    """`(\\textwidth in TeX points, source)` from `main.tex`'s class and
    options; `("fallback")` 345 pt (article, a4, 10 pt) when absent."""
    try:
        text = Path(main_tex).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return print_scale.TEXTWIDTH_PT["article-a4-10pt"], "fallback"
    name, options = paper_venue.parse_documentclass(text.split("\\begin{document}", 1)[0])
    sizes = [option for option in options if option in ("10pt", "11pt", "12pt")]
    size = sizes[0] if sizes else "10pt"
    table = print_scale.TEXTWIDTH_PT
    if name == "article":
        return table[f"article-a4-{size}"], "class"
    if name == "elsarticle":
        if "5p" in options:
            return table["elsarticle-5p-textwidth"], "class"
        if "1p" in options:
            return table["elsarticle-1p"], "class"
        if size == "12pt":
            return table["elsarticle-preprint-12pt"], "class"
        return table["elsarticle-preprint"], "class"
    if name == "IEEEtran":
        return table["IEEEtran-twocolumn-textwidth"], "class"
    if name == "llncs":
        return table["llncs"], "class"
    return table["article-a4-10pt"], "fallback"


def _drawn_path_boxes(pdf: Path, print_scale) -> list:
    """Bounds of every drawn (filled or stroked) path on page 0, skipping a
    first filled path that covers the page (the background
    `content_bbox` already reports). The same walk `content_bbox` does,
    kept per object because the title rule needs the plotting area's top."""
    document = print_scale.pdfium.PdfDocument(str(pdf))
    try:
        page = document[0]
        mediabox = [float(value) for value in page.get_mediabox()]
        boxes = []
        first = True
        for obj in page.get_objects():
            if obj.type != print_scale.pdfium_c.FPDF_PAGEOBJ_PATH:
                first = False
                continue
            filled, stroked = print_scale._path_is_drawn(obj)
            if not (filled or stroked):
                continue
            box = [float(value) for value in obj.get_bounds()]
            if first and filled and print_scale._coverage(box, mediabox) >= print_scale._BACKGROUND_COVERAGE:
                first = False
                continue
            first = False
            boxes.append(box)
    finally:
        document.close()
    return boxes


def _provenance_fields(provenance: dict) -> tuple:
    kind = provenance.get("figureKind", "plot")
    if kind not in FIGURE_KINDS:
        raise Refused(
            "FIGURE_PROVENANCE_INVALID",
            f"figureKind {kind!r} is not one of {list(FIGURE_KINDS)}",
        )
    fraction = provenance.get("printedWidthFraction", 1.0)
    if isinstance(fraction, bool) or not isinstance(fraction, (int, float)) or not 0 < fraction <= 1:
        raise Refused(
            "FIGURE_PROVENANCE_INVALID",
            f"printedWidthFraction {fraction!r} must be a number in (0, 1]: the fraction of "
            "\\textwidth the manuscript's \\includegraphics[width=...] declares",
        )
    return kind, float(fraction)


def _refuse_first(pdf: Path, failures: dict) -> None:
    """Refuse with the first failing check's code (`CHECK_ORDER`); the
    detail lists every failing one. Each code is raised as a literal so
    `paper-writing`'s refusal roster can read it from source."""
    ordered = [code for code in CHECK_ORDER if code in failures]
    detail = f"{pdf}: " + " | ".join(f"{code}: {failures[code]}" for code in ordered)
    first = ordered[0]
    if first == "FIGURE_NO_TEXT_LAYER":
        raise Refused("FIGURE_NO_TEXT_LAYER", detail)
    if first == "FIGURE_FULL_PAGE_BACKGROUND":
        raise Refused("FIGURE_FULL_PAGE_BACKGROUND", detail)
    if first == "FIGURE_MARGIN_WASTE":
        raise Refused("FIGURE_MARGIN_WASTE", detail)
    if first == "FIGURE_IN_FIGURE_TITLE":
        raise Refused("FIGURE_IN_FIGURE_TITLE", detail)
    raise Refused("FIGURE_TEXT_BELOW_PRINT_FLOOR", detail)


def gate(paper_dir: Path, pdf_source: Path, provenance_source: Path) -> dict | None:
    """`place`'s pre-copy gate. A missing PDF or provenance, an unparsable
    record, or one naming no run is left to `place_figure`, whose own
    refusals (`DIAGRAM_SOURCE_ABSENT`) are unchanged; everything else is
    measured by `check_figure`."""
    if not pdf_source.is_file() or not provenance_source.is_file():
        return None
    try:
        provenance = json.loads(provenance_source.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(provenance, dict) or not provenance.get("run"):
        return None
    return check_figure(paper_dir, pdf_source, provenance)


def check_figure(paper_dir: Path, pdf: Path, provenance: dict) -> dict:
    """Measure `pdf` and refuse when it breaks S2/S3/S4; return the
    measurements when it passes. Writes nothing."""
    kind, fraction = _provenance_fields(provenance)
    print_scale = _print_scale()
    main_tex = Path(paper_dir) / "main.tex"
    if main_tex.is_file():
        body_pt, body_source = print_scale.body_font_pt(main_tex)
    else:
        body_pt, body_source = print_scale.FALLBACK_BODY_PT, "fallback"
    width_tex, width_source = text_width_pt(main_tex, print_scale)
    printed_width = print_scale.declared_width_pt(width_tex, fraction)
    try:
        bounds = print_scale.content_bbox(pdf)
        spans = print_scale.pdf_text_spans(pdf)
        font = print_scale.printed_font_report(pdf, printed_width, body_pt)
        path_boxes = _drawn_path_boxes(pdf, print_scale)
    except print_scale.pdfium.PdfiumError as exc:
        raise Refused("FIGURE_PDF_UNREADABLE", f"{pdf} cannot be read as a PDF: {exc}") from exc

    failures = {}
    if kind == "plot" and figure_dimensions.no_text_layer(bounds["counts"]):
        failures["FIGURE_NO_TEXT_LAYER"] = (
            "the plot carries no text layer (a raster image, or text converted to outlines), "
            "so its labels cannot be measured: save the plot as a vector PDF with embedded text "
            "(ps_figures.save_figure; matplotlib pdf.fonttype 42). A photograph or micrograph "
            "declares \"figureKind\": \"image\" in its provenance"
        )
    background = figure_dimensions.background_verdict(bounds["full_page_background"])
    if background["verdict"] == "fail":
        failures["FIGURE_FULL_PAGE_BACKGROUND"] = (
            "a filled rectangle covers the whole page: save with transparent=True and no "
            "facecolor (ps_figures.save_figure)"
        )
    whitespace = figure_dimensions.whitespace_verdict(bounds["margins"])
    if whitespace["verdict"] == "fail":
        margins = ", ".join(f"{side} {whitespace['margins'][side]:.1f} pt" for side in whitespace["wide"])
        failures["FIGURE_MARGIN_WASTE"] = (
            f"margins wider than {figure_dimensions.MAX_MARGIN_PT:g} pt ({margins}): save with "
            'bbox_inches="tight", pad_inches=0.02 (ps_figures.save_figure)'
        )
    title = figure_dimensions.in_figure_title(spans, path_boxes, bounds["mediabox"])
    if title["verdict"] == "fail":
        texts = "; ".join(repr(item["text"]) for item in title["titles"])
        failures["FIGURE_IN_FIGURE_TITLE"] = (
            f"in-figure title {texts}: remove it (no set_title/suptitle) and say it in the "
            "caption, which carries the figure's title"
        )
    floor = figure_dimensions.min_printed_font_verdict(font)
    if floor["verdict"] == "fail":
        worst = sorted(floor["offending"], key=lambda item: item["printed_pt"])[:5]
        listed = ", ".join(f"{item['text']!r} {item['printed_pt']:.2f} pt" for item in worst)
        failures["FIGURE_TEXT_BELOW_PRINT_FLOOR"] = (
            f"text prints below 0.70 x the {body_pt:g} pt body ({floor['minPrintedPt']:g} pt) at "
            f"{fraction:g}\\textwidth ({printed_width:.1f} pt, scale {floor['scale']:.3f}): {listed}; "
            "enlarge the fonts (ps_figures.apply_style) or include the figure wider"
        )
    if failures:
        _refuse_first(pdf, failures)
    return {
        "figureKind": kind,
        "bodyPt": body_pt,
        "bodySource": body_source,
        "textWidthPt": width_tex,
        "textWidthSource": width_source,
        "printedWidthFraction": fraction,
        "dimensions": {
            "min-printed-font": floor,
            "background": background,
            "whitespace": whitespace,
            "in-figure-title": title,
        },
    }
