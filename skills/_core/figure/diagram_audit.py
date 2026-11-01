"""diagram_audit: the one mechanical audit every TikZ diagram passes.

Specs S1 and S3 of `odd/tasks/figure-and-table-quality.md`: a diagram never
overflows, never overlaps, never prints text below 70 % of the manuscript
body size, and exports without a background or wasted margin. Both diagram
producers call this module, so the rules cannot drift between them:

* `skills/experiment-diagrams/scripts/diagram_cli.py` (`render`, `audit`,
  and the `validate` gate);
* `skills/paper-writing/scripts/paper_figure.py` (`render`, after a
  successful compile).

The audit reads only what the compile left behind: the TeX source, the TeX
log and the PDF (its vector text layer and its page objects, through
`print_scale`, never a raster). Nothing here spawns a process.

Checks, each `pass` | `fail` | `unmeasured` (with a reason):

    overfull        no `Overfull \\hbox` / `Overfull \\vbox` in the TeX log
                    (a standalone picture has nothing else on the page, so
                    every overfull box is inside the picture)
    size_switches   no relative size switch (`\\tiny` ... `\\Huge`) in the
                    source: every size is an explicit `\\fontsize{..}{..}`
    text_overlap    no two text spans intersect, and no span crosses the
                    boundary of a drawn closed shape (a node frame, an arrow
                    tip) unless it lies wholly inside it
    font_floor      every span prints at >= 0.70 x the body size at the
                    declared inclusion width (`print_scale.printed_font_report`)
    margins         no background canvas (a full-page fill, or a first-drawn filled
                    shape enclosing every other shape), no content past the
                    page edge, and every content margin to the MediaBox
                    <= `MAX_MARGIN_PT` (`print_scale.content_bbox`)

The overall verdict is `fail` when any check fails, `pass` when every check
passes, and `unmeasured` otherwise (a check that could not run is never a
pass).

Public API:

    MAX_MARGIN_PT: float = 4.0
    RELATIVE_SIZE_SWITCHES: tuple[str, ...]
    default_text_width_pt(body_pt) -> float          (TeX points)
    role_font_pt(body_pt, scale=1.0) -> dict          (TeX points per role)
    fontsize_command(size_pt) -> str                  (`\\fontsize{s}{1.2s}\\selectfont`)
    find_size_switches(tex_text) -> list[dict]
    parse_overfull(log_text) -> list[str]
    text_collisions(pdf, page_index=0) -> dict
    audit_diagram(pdf, *, body_pt, printed_width_pt, tex_text=None,
                  log_text=None, max_margin_pt=MAX_MARGIN_PT) -> dict
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import print_scale  # noqa: E402  (sibling module, resolved above)

#: Largest blank band allowed between the drawn content and the page edge,
#: per side, in PDF points. A `border=2pt` standalone page plus half a
#: stroke stays well inside it; a 14 pt frame or a page-wide canvas does not.
MAX_MARGIN_PT = 4.0

#: LaTeX's relative size switches. Each one means "whatever this class calls
#: small", so the printed size cannot be computed from the source.
RELATIVE_SIZE_SWITCHES = (
    "tiny", "scriptsize", "footnotesize", "small", "normalsize",
    "large", "Large", "LARGE", "huge", "Huge",
)
_SWITCH_RE = re.compile(r"\\(" + "|".join(RELATIVE_SIZE_SWITCHES) + r")(?![A-Za-z@])")
_OVERFULL_RE = re.compile(r"Overfull \\[hv]box \([^)]*\)[^\n]*")

#: Ratio of each diagram role to the body size, before the 0.70 floor.
ROLE_RATIOS = {"claim": 1.0, "spine": 0.9, "note": 0.8}

#: Glyph boxes are tight but anti-aliasing-free; this much interior
#: penetration is the least that counts as a collision (PDF points).
COLLISION_TOLERANCE_PT = 0.3
#: A closed shape smaller than this on either side is not a frame
#: (a dot, a hairline) and is ignored by the boundary check.
MIN_SHAPE_PT = 2.0
#: Content further than this outside the MediaBox is cut off when printed.
CLIP_TOLERANCE_PT = 0.5


def default_text_width_pt(body_pt: float) -> float:
    """`\\textwidth` of an A4 article at this body size (TeX points), from
    `print_scale.TEXTWIDTH_PT`. A measured placement always wins over it."""
    table = print_scale.TEXTWIDTH_PT
    if body_pt >= 12:
        return table["article-a4-12pt"]
    if body_pt >= 11:
        return table["article-a4-11pt"]
    return table["article-a4-10pt"]


def role_font_pt(body_pt: float, scale: float = 1.0) -> dict:
    """Explicit font sizes (TeX points) per diagram role so that each prints
    at >= `print_scale.MIN_RATIO` x body once the figure is scaled by
    `scale` (printed width / natural width). Never below the floor; sizes
    grow when `scale < 1`, they never shrink to fit."""
    scale = max(float(scale), 1e-6)
    floor = print_scale.min_printed_pt(body_pt) / scale
    sizes = {}
    for role, ratio in ROLE_RATIOS.items():
        sizes[role] = round(max(ratio * float(body_pt), floor) + 1e-9, 2)
    return sizes


def fontsize_command(size_pt: float) -> str:
    """`\\fontsize{s}{1.2s}\\selectfont`, the only way a diagram sets a size."""
    return f"\\fontsize{{{size_pt:.2f}}}{{{size_pt * 1.2:.2f}}}\\selectfont"


def _comment_free_lines(tex_text: str):
    for number, line in enumerate(tex_text.splitlines(), start=1):
        cut = None
        for index, char in enumerate(line):
            if char != "%":
                continue
            backslashes = 0
            probe = index - 1
            while probe >= 0 and line[probe] == "\\":
                backslashes += 1
                probe -= 1
            if backslashes % 2 == 0:
                cut = index
                break
        yield number, line if cut is None else line[:cut]


def find_size_switches(tex_text: str) -> list:
    """Every relative size switch outside a comment, with its line."""
    found = []
    for number, line in _comment_free_lines(tex_text):
        for match in _SWITCH_RE.finditer(line):
            found.append({"switch": "\\" + match.group(1), "line": number})
    return found


def parse_overfull(log_text: str) -> list:
    """Every `Overfull \\hbox|\\vbox (...)` line of a TeX log, verbatim."""
    return [match.group(0).strip() for match in _OVERFULL_RE.finditer(log_text)]


def _intersects(a, b, tol: float) -> bool:
    return (a[0] + tol < b[2] and b[0] + tol < a[2]
            and a[1] + tol < b[3] and b[1] + tol < a[3])


def _contains(outer, inner, tol: float) -> bool:
    return (inner[0] >= outer[0] - tol and inner[1] >= outer[1] - tol
            and inner[2] <= outer[2] + tol and inner[3] <= outer[3] + tol)


def _closed_shapes(pdf: Path, page_index: int) -> list:
    """Every drawn page path that closes a subpath (node frames, arrow tips,
    filled label backgrounds), in drawing order: `{"bbox", "filled",
    "order"}`. Open strokes (connectors) are not frames and are left out;
    `order` counts every top-level page object, so `order == 0` means the
    shape is the first thing drawn."""
    import ctypes

    import pypdfium2 as pdfium
    import pypdfium2.raw as pdfium_c

    shapes = []
    document = pdfium.PdfDocument(str(pdf))
    try:
        page = document[page_index]
        for order, obj in enumerate(page.get_objects(max_depth=4)):
            if obj.type != pdfium_c.FPDF_PAGEOBJ_PATH:
                continue
            fill_mode = ctypes.c_int(0)
            stroke = ctypes.c_int(0)
            if not pdfium_c.FPDFPath_GetDrawMode(obj.raw, ctypes.byref(fill_mode), ctypes.byref(stroke)):
                continue
            if fill_mode.value == 0 and not stroke.value:
                continue
            closed = False
            for index in range(pdfium_c.FPDFPath_CountSegments(obj.raw)):
                segment = pdfium_c.FPDFPath_GetPathSegment(obj.raw, index)
                if segment and pdfium_c.FPDFPathSegment_GetClose(segment):
                    closed = True
                    break
            if not closed:
                continue
            box = [round(float(value), 3) for value in obj.get_bounds()]
            if box[2] - box[0] < MIN_SHAPE_PT or box[3] - box[1] < MIN_SHAPE_PT:
                continue
            shapes.append({"bbox": box, "filled": fill_mode.value != 0, "order": order})
    finally:
        document.close()
    return shapes


def _background(shapes: list) -> list | None:
    """A canvas painted behind the picture: the first object drawn is a
    filled closed shape that encloses every other closed shape. A
    standalone `border` keeps it from covering the whole MediaBox, so
    `print_scale.content_bbox`'s 98 % page-coverage rule cannot see it."""
    if len(shapes) < 2 or shapes[0]["order"] != 0 or not shapes[0]["filled"]:
        return None
    outer = shapes[0]["bbox"]
    if all(_contains(outer, shape["bbox"], COLLISION_TOLERANCE_PT) for shape in shapes[1:]):
        return outer
    return None


def text_collisions(pdf: Path, page_index: int = 0) -> dict:
    """Text spans that intersect each other, and spans that cross the
    boundary of a drawn closed shape without lying wholly inside it."""
    spans = print_scale.pdf_text_spans(pdf, page_index)
    shapes = _closed_shapes(pdf, page_index)
    tol = COLLISION_TOLERANCE_PT
    span_collisions = []
    for i, first in enumerate(spans):
        for second in spans[i + 1:]:
            if _intersects(first["bbox"], second["bbox"], tol):
                span_collisions.append({"texts": [first["text"], second["text"]],
                                        "bboxes": [first["bbox"], second["bbox"]]})
    crossings = []
    for span in spans:
        for shape in shapes:
            box = shape["bbox"]
            if _intersects(span["bbox"], box, tol) and not _contains(box, span["bbox"], tol):
                crossings.append({"text": span["text"], "bbox": span["bbox"], "shape": box})
    return {"span_count": len(spans), "shape_count": len(shapes),
            "span_collisions": span_collisions, "boundary_crossings": crossings,
            "background_shape": _background(shapes)}


def _check(verdict: str, reason: str | None = None, **evidence) -> dict:
    return {"verdict": verdict, "reason": reason, **evidence}


def audit_diagram(pdf: Path, *, body_pt: float, printed_width_pt: float | None,
                  tex_text: str | None = None, log_text: str | None = None,
                  max_margin_pt: float = MAX_MARGIN_PT) -> dict:
    """Every check above for one compiled diagram. `printed_width_pt` is the
    declared inclusion width in PDF points (`None`: natural size)."""
    checks: dict = {}

    if log_text is None:
        checks["overfull"] = _check("unmeasured", "NO_TEX_LOG", lines=[])
    else:
        lines = parse_overfull(log_text)
        checks["overfull"] = _check("fail" if lines else "pass", lines=lines)

    if tex_text is None:
        checks["size_switches"] = _check("unmeasured", "NO_TEX_SOURCE", found=[])
    else:
        found = find_size_switches(tex_text)
        checks["size_switches"] = _check("fail" if found else "pass", found=found)

    pdf = Path(pdf)
    try:
        collisions = text_collisions(pdf)
        floor = print_scale.printed_font_report(pdf, printed_width_pt, body_pt)
        box = print_scale.content_bbox(pdf)
    except Exception as exc:  # an unreadable PDF measures nothing, never passes
        reason = f"PDF_UNREADABLE: {type(exc).__name__}: {exc}"
        for name in ("text_overlap", "font_floor", "margins"):
            checks[name] = _check("unmeasured", reason)
    else:
        if collisions["span_count"] == 0:
            checks["text_overlap"] = _check("unmeasured", "NO_TEXT_LAYER", **collisions)
        else:
            failed = collisions["span_collisions"] or collisions["boundary_crossings"]
            checks["text_overlap"] = _check("fail" if failed else "pass", **collisions)
        checks["font_floor"] = _check(floor["verdict"], floor["reason"],
                                      **{k: v for k, v in floor.items() if k not in ("verdict", "reason")})
        margins = box["margins"]
        if margins is None:
            checks["margins"] = _check("unmeasured", "EMPTY_PAGE", **box, max_margin_pt=max_margin_pt)
        else:
            wide = {side: value for side, value in margins.items() if value > max_margin_pt + 1e-6}
            clipped = {side: value for side, value in margins.items() if value < -CLIP_TOLERANCE_PT}
            background = collisions["background_shape"]
            failed = box["full_page_background"] or background is not None or bool(wide) or bool(clipped)
            checks["margins"] = _check("fail" if failed else "pass", **box,
                                       background_shape=background, max_margin_pt=max_margin_pt,
                                       wide_sides=wide, clipped_sides=clipped)

    verdicts = [check["verdict"] for check in checks.values()]
    if "fail" in verdicts:
        verdict = "fail"
    elif all(value == "pass" for value in verdicts):
        verdict = "pass"
    else:
        verdict = "unmeasured"
    return {
        "verdict": verdict,
        "failures": [name for name, check in checks.items() if check["verdict"] == "fail"],
        "body_pt": float(body_pt),
        "printed_width_pt": None if printed_width_pt is None else round(float(printed_width_pt), 3),
        "min_printed_pt": print_scale.min_printed_pt(body_pt),
        "checks": checks,
    }


def failure_messages(report: dict) -> list:
    """One human-readable line per failed check, for diagnostics lists."""
    messages = []
    checks = report.get("checks", {})
    for name in report.get("failures", []):
        check = checks.get(name, {})
        if name == "overfull":
            messages += [f"overfull: {line}" for line in check.get("lines", [])]
        elif name == "size_switches":
            messages += [f"size_switches: {item['switch']} on line {item['line']}; use \\fontsize"
                         for item in check.get("found", [])]
        elif name == "text_overlap":
            messages += [f"text_overlap: {' / '.join(item['texts'])}" for item in check.get("span_collisions", [])]
            messages += [f"text_overlap: {item['text']!r} crosses a drawn shape {item['shape']}"
                         for item in check.get("boundary_crossings", [])]
        elif name == "font_floor":
            messages += [f"font_floor: {item['text']!r} prints at {item['printed_pt']} pt < "
                         f"{check.get('min_printed_pdf_pt')} pt" for item in check.get("offending", [])]
        elif name == "margins":
            if check.get("full_page_background") or check.get("background_shape"):
                messages.append("margins: a background canvas is drawn behind the picture; export without one")
            for side, value in (check.get("clipped_sides") or {}).items():
                messages.append(f"margins: content runs {-value} pt past the {side} page edge")
            for side, value in (check.get("wide_sides") or {}).items():
                messages.append(f"margins: {side} margin {value} pt > {check.get('max_margin_pt')} pt")
    return messages


__all__ = [
    "MAX_MARGIN_PT", "RELATIVE_SIZE_SWITCHES", "ROLE_RATIOS", "audit_diagram",
    "default_text_width_pt", "failure_messages", "find_size_switches", "fontsize_command",
    "parse_overfull", "role_font_pt", "text_collisions",
]
