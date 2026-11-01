"""figure_dimensions: the visual-dimension roster and its reason-code
vocabulary, declared exactly once so the producer (`figure-review`) and
the consumer (`paper-writing`'s `audit_semantics` default) cannot drift
apart (design.md, Decision 4: "The dimension roster and reason-code
vocabulary are declared once, in a shared `skills/_core/figure/` shelf
both sides import").

Zero imports, by construction and by test: this module's AST is checked
for zero `Import`/`ImportFrom` nodes (design.md lock 12), which is what
makes the forge gate's `IMPORT_SCOPE_PATHSPECS` scan (scoped to
`skills/*/scripts/*.py`, and therefore blind to `skills/_core/figure/`)
unnecessary rather than merely absent -- a module that cannot import
anything needs no import scan. That is also why this file carries no
`from __future__ import annotations`: that statement is itself an
`ImportFrom` node.

Three tiers (`visual-finding-boundary` spec, `Requirement: Every Visual
Dimension Is Classified Into Exactly One Tier`):

    VERDICT_DIMENSIONS  -- a computed pass/fail, naming an edge or a
                            collision when it fails.
    EVIDENCE_DIMENSIONS -- a number worth reporting, carrying no verdict.
    SILENT_DIMENSIONS   -- an announced silence: unmeasured, with a
                            named reason, because the thing it would
                            answer is a judgement, not a pixel property.

The vector verdicts (specs S2-S4 of `odd/tasks/figure-and-table-quality.md`)
read the figure PDF itself, not its raster: `min-printed-font` (every text
span, at its printed size, is at least 0.70 x the body font; the verdict is
`print_scale.printed_font_report`'s), `background` (no filled rectangle
covering the page), `whitespace` (no margin wider than `MAX_MARGIN_PT`
between the drawn content and the MediaBox) and `in-figure-title` (no title
row above the plotting area: the caption carries it). The rule functions at
the end of this module decide those verdicts from plain data (spans, path
boxes, margins), so `paper-writing`'s `place` and `figure-review`'s
`measure` cannot disagree about what a title or a wasted margin is; reading
the PDF stays with each caller.
"""

VERDICT_DIMENSIONS = (
    "out-of-bounds",
    "overlap",
    "min-printed-font",
    "background",
    "whitespace",
    "in-figure-title",
)
EVIDENCE_DIMENSIONS = ("canvas-occupancy",)
SILENT_DIMENSIONS = (
    "connection-correctness",
    "style-quality",
    "overlap-ownership",
)

#: Every classified dimension, in the fixed order the roster declares
#: them. `default_visual` and every consumer that iterates "every
#: dimension" reads this tuple rather than re-deriving it.
ALL_DIMENSIONS = VERDICT_DIMENSIONS + EVIDENCE_DIMENSIONS + SILENT_DIMENSIONS

#: The reason a dimension is `unmeasured` by default. The former
#: `legibility` silence (`LEGIBILITY_IS_A_THRESHOLD_JUDGEMENT`) is gone:
#: spec S3 turned the threshold into a declared rule (0.70 x body at the
#: printed size), so `min-printed-font` is a computed verdict whenever the
#: figure PDF carries a text layer.
DEFAULT_REASONS = {
    "out-of-bounds": "RASTER_NOT_MEASURED",
    "overlap": "RASTER_NOT_MEASURED",
    "min-printed-font": "PDF_NOT_MEASURED",
    "background": "PDF_NOT_MEASURED",
    "whitespace": "PDF_NOT_MEASURED",
    "in-figure-title": "PDF_NOT_MEASURED",
    "canvas-occupancy": "RASTER_NOT_MEASURED",
    "connection-correctness": "VISUAL_MEANING_NOT_A_PIXEL_PROPERTY",
    "style-quality": "VISUAL_JUDGEMENT_NOT_MEASURED",
    "overlap-ownership": "UNATTRIBUTED_INK",
}


def default_visual():
    """Every classified dimension, present and unmeasured -- the shape
    `audit_semantics` returns when no caller supplies a `visual` dict
    (`diagram-obligation` spec, `Requirement: Figure-Prose Semantic
    Audit`), and the shape `figure-review`'s own `findings.py` starts
    from before it overwrites what it actually measured. Reading any
    dimension by key never raises (`visual-finding-boundary`,
    `Requirement: Every Dimension Is Always Present, Never Absent or
    Null`)."""
    dimensions = {
        name: {"verdict": "unmeasured", "reason": DEFAULT_REASONS[name]}
        for name in ALL_DIMENSIONS
    }
    return {"provenance": None, "dimensions": dimensions}


# ---------------------------------------------------------------------
# Vector-verdict rules (S2-S4): plain data in, plain data out.
# ---------------------------------------------------------------------

#: The widest margin, in PDF points, allowed between a figure's drawn
#: content and its MediaBox on any side. `savefig(..., bbox_inches="tight",
#: pad_inches=0.02)` leaves about 1.44 pt; a `standalone` figure with
#: `border=0pt` leaves the node inner sep (about 3 pt).
MAX_MARGIN_PT = 4.0

#: A title row spans at least this fraction of the figure width.
TITLE_MIN_WIDTH_FRACTION = 0.30

_ROW_SLACK = 0.5
_EPSILON = 1e-6


def background_verdict(full_page_background):
    """`background`: a filled rectangle covering the page is a fail."""
    if full_page_background:
        return {"verdict": "fail", "reason": "FULL_PAGE_BACKGROUND"}
    return {"verdict": "pass", "reason": None}


def whitespace_verdict(margins):
    """`whitespace`: fail when any margin (PDF points) exceeds
    `MAX_MARGIN_PT`; unmeasured when the page draws nothing."""
    if margins is None:
        return {"verdict": "unmeasured", "reason": "NO_DRAWN_CONTENT",
                "margins": None, "maxMarginPt": MAX_MARGIN_PT, "wide": []}
    wide = sorted(side for side, value in margins.items() if value > MAX_MARGIN_PT + _EPSILON)
    return {
        "verdict": "fail" if wide else "pass",
        "reason": "MARGIN_WASTE" if wide else None,
        "margins": dict(margins),
        "maxMarginPt": MAX_MARGIN_PT,
        "wide": wide,
    }


def no_text_layer(counts):
    """True when the page carries no text object: a raster-only figure or
    text converted to outlines. Its printed size cannot be measured."""
    return counts.get("text", 0) == 0


def _rows(spans):
    """Upright spans grouped into text rows of one size whose vertical
    extents meet. Spans break at whitespace, so a title is a row of
    spans, never one span."""
    rows = []
    for span in sorted(spans, key=lambda item: (-item["bbox"][3], item["bbox"][0])):
        size = span["size_pt"]
        for row in rows:
            if abs(row["size_pt"] - size) > 0.01 * size + _EPSILON:
                continue
            slack = _ROW_SLACK * size
            if span["bbox"][1] <= row["bbox"][3] + slack and span["bbox"][3] >= row["bbox"][1] - slack:
                row["spans"].append(span)
                row["bbox"] = [
                    min(row["bbox"][0], span["bbox"][0]), min(row["bbox"][1], span["bbox"][1]),
                    max(row["bbox"][2], span["bbox"][2]), max(row["bbox"][3], span["bbox"][3]),
                ]
                break
        else:
            rows.append({"size_pt": size, "bbox": list(span["bbox"]), "spans": [span]})
    return rows


def in_figure_title(spans, path_boxes, mediabox):
    """`in-figure-title` (S4): a row of upright text lying entirely above
    every drawn vector path (the top of the plotting area), at least as
    large as the largest text below it (the axis labels), spanning at
    least `TITLE_MIN_WIDTH_FRACTION` of the figure width, and crossed by
    no path (a legend row carries its line samples).

    `spans` are `print_scale.pdf_text_spans` dicts; `path_boxes` are the
    `[left, bottom, right, top]` bounds of every drawn path except a
    full-page background; `mediabox` is the page box. Without a path or an
    upright span there is no plotting area to stand above: unmeasured."""
    if not path_boxes:
        return {"verdict": "unmeasured", "reason": "NO_PLOTTING_AREA", "titles": []}
    upright = [span for span in spans if abs(span.get("angle_deg", 0.0)) < 1.0]
    if not upright:
        return {"verdict": "unmeasured", "reason": "NO_TEXT_LAYER", "titles": []}
    plot_top = max(box[3] for box in path_boxes)
    width = float(mediabox[2]) - float(mediabox[0])
    rows = _rows(upright)
    label_size = max(
        (row["size_pt"] for row in rows if row["bbox"][1] < plot_top - _EPSILON), default=0.0,
    )
    titles = []
    for row in rows:
        left, bottom, right, top = row["bbox"]
        if bottom < plot_top - _EPSILON:
            continue
        if right - left < TITLE_MIN_WIDTH_FRACTION * width - _EPSILON:
            continue
        if row["size_pt"] + _EPSILON < label_size:
            continue
        if any(box[0] < right and box[2] > left and box[1] <= top and box[3] >= bottom
               for box in path_boxes):
            continue
        words = sorted(row["spans"], key=lambda span: span["bbox"][0])
        titles.append({
            "text": " ".join(span["text"] for span in words),
            "size_pt": row["size_pt"],
            "bbox": [round(value, 3) for value in row["bbox"]],
        })
    return {
        "verdict": "fail" if titles else "pass",
        "reason": "TITLE_BELONGS_IN_CAPTION" if titles else None,
        "titles": titles,
    }


def min_printed_font_verdict(report):
    """`min-printed-font` (S3), from a `print_scale.printed_font_report`
    dict: its verdict, with the numbers that decided it."""
    verdict = report["verdict"]
    reason = None
    if verdict == "unmeasured":
        reason = "NO_TEXT_LAYER"
    elif verdict == "fail":
        reason = "TEXT_BELOW_PRINT_FLOOR"
    return {
        "verdict": verdict,
        "reason": reason,
        "bodyPt": report["body_pt"],
        "minPrintedPt": report["min_printed_pt"],
        "scale": report["scale"],
        "printedWidthPt": report["printed_width_pt"],
        "smallestPrintedPt": report["smallest_printed_pt"],
        "offending": list(report["offending"]),
    }
