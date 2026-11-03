"""print_scale: how large a figure's text prints in the manuscript.

One measured rule (spec S3 of `odd/tasks/figure-and-table-quality.md`,
widened to a range by spec S2 of `odd/tasks/manuscript-polish-0-54.md`):
every text span of a figure or table, at its printed scale, is between
`MIN_RATIO` (0.70) and `MAX_RATIO` (0.90) times the manuscript's body font
size. Diagrams, experiment plots, `place`, `figure-review measure` and the
manuscript QA pass all read the range from here, so the thresholds, the
units and the measurement cannot drift apart.

No glyph class is exempt from the cap: TeX's math size variants
(sub/superscripts) only ever print smaller than the surrounding text, and a
display operator from `cmex` is set with the same `Tf` size as its line, so
a figure set at in-range sizes measures in range.

Units. LaTeX sizes (`10pt`, `\\textwidth = 345pt`) are TeX points
(1/72.27 in); everything read from a PDF (MediaBox, glyph sizes, bounding
boxes) is in PDF points (1/72 in). `TEX_PT_TO_PDF_PT` converts. Verdicts
compare in PDF points, so a 7 pt TeX font in a 10 pt document passes at
exactly 70 %.

Public API (stable; later writers import it, never copy it):

    MIN_RATIO: float = 0.70
    MAX_RATIO: float = 0.90
    TEX_PT_TO_PDF_PT: float = 72 / 72.27
    TEXTWIDTH_PT: dict[str, float]
        `\\textwidth` / `\\columnwidth` in TeX points for common setups.
        A measurement of the placed width in a compiled `main.pdf` always
        wins over this table; the table is for standalone checks only.

    body_font_pt(main_tex: Path) -> tuple[float, str]
        (size in TeX points, source); source is "option" (an explicit
        `10pt`/`11pt`/`12pt`... class option), "class-default" (a known
        class without a size option) or "fallback" (10.0: no
        `\\documentclass`, or an unknown class without a size option).
    geometry_text_width_pt(main_tex: Path) -> float | None
        `\\textwidth` in TeX points as `main.tex`'s `geometry` options
        set it (textwidth/width, else paper width minus the margins);
        None when no geometry fixes it.
    min_printed_pt(body_pt: float) -> float
        MIN_RATIO * body_pt, in TeX points.
    max_printed_pt(body_pt: float) -> float
        MAX_RATIO * body_pt, in TeX points.
    declared_width_pt(text_width_pt: float, fraction: float) -> float
        An inclusion width such as `0.8\\textwidth`, given the text width
        in TeX points, returned in PDF points (comparable to a MediaBox).
    pdf_text_spans(pdf: Path, page_index: int = 0) -> list[dict]
        Words/runs of the page's text layer. Each dict:
        {"text": str, "size_pt": float, "font_size": float,
         "angle_deg": float, "bbox": [left, bottom, right, top]}
        `size_pt` is the effective rendered size in PDF points.
    printed_font_report(figure_pdf: Path, printed_width_pt: float | None,
                        body_pt: float) -> dict
        {"verdict": "pass" | "fail" | "unmeasured", "reason": str | None,
         "scale": float, "mediabox_width_pt": float,
         "printed_width_pt": float | None, "body_pt": float,
         "min_printed_pt": float, "min_printed_pdf_pt": float,
         "max_printed_pt": float, "max_printed_pdf_pt": float,
         "smallest_printed_pt": float | None,
         "largest_printed_pt": float | None, "span_count": int,
         "offending": [{"text", "size_pt", "printed_pt", "bbox",
                        "bound": "floor" | "cap"}]}
        `fail` when any span prints below the floor or above the cap.
    content_bbox(pdf: Path, page_index: int = 0) -> dict
        {"mediabox": [l, b, r, t], "bbox": [l, b, r, t] | None,
         "margins": {"left", "right", "bottom", "top"} | None,
         "full_page_background": bool,
         "counts": {"text": int, "image": int, "path": int, "other": int}}
        Top-level page objects only: a form XObject (an included PDF)
        counts once, as "other", by its page-space bounds.
    drawn_path_boxes(pdf: Path, page_index: int = 0) -> list[list[float]]
        [l, b, r, t] of every drawn (filled or stroked) top-level path, in
        drawing order, without the full-page background `content_bbox`
        reports.
    path_is_drawn(obj) -> tuple[bool, bool]
        (filled, stroked) of a pypdfium2 path object; (False, False) for a
        path neither filled nor stroked.

How the text layer is read (pypdfium2, Apache-2.0/BSD-3; PyMuPDF is not
used: AGPL and undeclared):

    PdfDocument(pdf)[page_index].get_textpage()   -> PdfTextPage
    PdfTextPage.count_chars()                     -> char count
    raw.FPDFText_GetUnicode(textpage, i)          -> code point
    raw.FPDFText_IsGenerated(textpage, i)         -> synthetic space/newline
    raw.FPDFText_GetFontSize(textpage, i)         -> font size in text space
                                                     (the `Tf` operand; it
                                                     ignores every matrix)
    raw.FPDFText_GetMatrix(textpage, i, FS_MATRIX) -> char matrix to page
                                                     space (text matrix
                                                     times CTM)
    PdfTextPage.get_charbox(i)                    -> tight glyph box, page
                                                     space

The effective size is `font_size * |(c, d)|`: the length of the matrix's
glyph-vertical axis. That is rotation invariant (a 90 degree label keeps its
size, and `angle_deg` = atan2(b, a) records the rotation) and, for a
non-uniform scale such as `\\scalebox{1.5}[3]`, follows the glyph height,
which is what legibility depends on. Spans break at whitespace, generated
characters, and any change of size or matrix.

A figure included at `printed_width_pt` prints at
`scale = printed_width_pt / MediaBox width` (`\\includegraphics[width=..]`
scales the box, not the ink); `None` means natural size (scale 1.0). A
page with no text layer (a raster image, or text converted to outlines)
yields `unmeasured`, never `pass`: the rule cannot be checked from pixels.
"""

from __future__ import annotations

import ctypes
import math
import re
import sys
from pathlib import Path

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c

MIN_RATIO = 0.70
MAX_RATIO = 0.90
TEX_PT_TO_PDF_PT = 72.0 / 72.27
FALLBACK_BODY_PT = 10.0

#: Body size of a known class when no size option is given (TeX points).
CLASS_DEFAULT_BODY_PT = {
    "article": 10.0,
    "report": 10.0,
    "book": 10.0,
    "amsart": 10.0,
    "elsarticle": 10.0,
    "IEEEtran": 10.0,
    "llncs": 10.0,
}

#: `\textwidth` (or `\columnwidth` for a column figure) in TeX points, as
#: `\the\textwidth` prints them, measured with pdflatex on TeX Live.
#: A placed width measured in the compiled `main.pdf` wins over this table.
TEXTWIDTH_PT = {
    "article-a4-10pt": 345.0,
    "article-a4-11pt": 360.0,
    "article-a4-12pt": 390.0,
    "elsarticle-preprint": 345.0,
    "elsarticle-preprint-12pt": 390.0,
    "elsarticle-review": 345.0,
    "elsarticle-1p": 384.0,
    "elsarticle-5p-textwidth": 522.0,
    "elsarticle-5p-columnwidth": 252.0,
    "IEEEtran-onecolumn": 516.0,
    "IEEEtran-twocolumn-textwidth": 516.0,
    "IEEEtran-twocolumn-columnwidth": 252.0,
    "llncs": 347.12354,
}

_SIZE_OPTION_RE = re.compile(r"^(\d+(?:\.\d+)?)pt$")
_BACKGROUND_COVERAGE = 0.98
_EPSILON = 1e-6
#: Span sizes are rounded to 3 decimals (`_read_spans`); a span set exactly
#: at the cap must not fail on that rounding.
_CAP_TOLERANCE_PT = 1e-3


def _parse_documentclass():
    """`paper_venue.parse_documentclass`, the one class/options parser the
    paper tree already uses (imported lazily: only `body_font_pt` needs
    it)."""
    scripts = Path(__file__).resolve().parents[2] / "paper-writing" / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import paper_venue  # noqa: E402  (sibling skill, resolved above)

    return paper_venue.parse_documentclass


def body_font_pt(main_tex: Path) -> tuple[float, str]:
    """The manuscript body size in TeX points and where it came from."""
    text = Path(main_tex).read_text(encoding="utf-8", errors="replace")
    preamble = text.split("\\begin{document}", 1)[0]
    name, options = _parse_documentclass()(preamble)
    for option in options:
        match = _SIZE_OPTION_RE.match(option)
        if match:
            return float(match.group(1)), "option"
    if name in CLASS_DEFAULT_BODY_PT:
        return CLASS_DEFAULT_BODY_PT[name], "class-default"
    return FALLBACK_BODY_PT, "fallback"


#: Paper widths in TeX points (`\paperwidth`), by geometry/class option.
PAPER_WIDTH_PT = {
    "a4paper": 210 / 25.4 * 72.27,
    "letterpaper": 8.5 * 72.27,
    "a5paper": 148 / 25.4 * 72.27,
    "b5paper": 176 / 25.4 * 72.27,
    "legalpaper": 8.5 * 72.27,
    "executivepaper": 7.25 * 72.27,
}
#: TeX points per unit for the lengths geometry keys take.
_UNIT_PT = {"pt": 1.0, "mm": 72.27 / 25.4, "cm": 72.27 / 2.54, "in": 72.27,
            "bp": 72.27 / 72.0, "pc": 12.0}
_LENGTH_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?|-?\.\d+)\s*(pt|mm|cm|in|bp|pc)\s*$")
_GEOMETRY_PACKAGE_RE = re.compile(r"\\usepackage\s*(?:\[([^\]]*)\])?\s*\{[^}]*\bgeometry\b[^}]*\}")
_GEOMETRY_CMD_RE = re.compile(r"\\geometry\s*\{([^}]*)\}")


def _length_pt(value: str):
    match = _LENGTH_RE.match(value)
    return None if match is None else float(match.group(1)) * _UNIT_PT[match.group(2)]


def _strip_comments(text: str) -> str:
    return "\n".join(re.split(r"(?<!\\)%", line, maxsplit=1)[0] for line in text.splitlines())


def geometry_text_width_pt(main_tex: Path):
    """`\\textwidth` in TeX points as `geometry` sets it in `main.tex`, or
    `None` when the preamble loads no geometry or does not fix the width.

    Reads the package options and every `\\geometry{...}` (later keys win):
    `textwidth`/`width` directly, else the paper width minus the left and
    right margins (`left`/`right`, `lmargin`/`rmargin`, `hmargin`, `margin`;
    one missing margin mirrors the other, as geometry does). The paper is
    the geometry or class paper option, A4 when none is given -- the same
    assumption `TEXTWIDTH_PT` makes."""
    text = Path(main_tex).read_text(encoding="utf-8", errors="replace")
    preamble = _strip_comments(text.split("\\begin{document}", 1)[0])
    chunks = [m.group(1) or "" for m in _GEOMETRY_PACKAGE_RE.finditer(preamble)]
    if not chunks and "\\geometry" not in preamble:
        return None
    chunks += [m.group(1) for m in _GEOMETRY_CMD_RE.finditer(preamble)]
    keys: dict = {}
    flags: list = []
    for chunk in chunks:
        for item in chunk.split(","):
            if "=" in item:
                key, value = item.split("=", 1)
                keys[key.strip()] = value.strip().strip("{}")
            elif item.strip():
                flags.append(item.strip())
    for key in ("textwidth", "width"):
        if key in keys and _length_pt(keys[key]) is not None:
            return round(_length_pt(keys[key]), 5)
    name, class_options = _parse_documentclass()(preamble)
    paper = "a4paper"
    for option in list(class_options) + flags:
        if option in PAPER_WIDTH_PT:
            paper = option
    if "paper" in keys and keys["paper"] in PAPER_WIDTH_PT:
        paper = keys["paper"]
    left = right = None
    for key in ("margin", "hmargin"):
        if key in keys:
            parts = keys[key].split(",") if key == "hmargin" else [keys[key]]
            left = _length_pt(parts[0])
            right = _length_pt(parts[-1])
    for key, side in (("left", "l"), ("lmargin", "l"), ("inner", "l"),
                      ("right", "r"), ("rmargin", "r"), ("outer", "r")):
        if key in keys and _length_pt(keys[key]) is not None:
            if side == "l":
                left = _length_pt(keys[key])
            else:
                right = _length_pt(keys[key])
    if left is None and right is None:
        return None
    left = right if left is None else left
    right = left if right is None else right
    return round(PAPER_WIDTH_PT[paper] - left - right, 5)


def min_printed_pt(body_pt: float) -> float:
    """The smallest printed text size allowed, in TeX points."""
    return round(MIN_RATIO * float(body_pt), 6)


def max_printed_pt(body_pt: float) -> float:
    """The largest printed text size allowed, in TeX points."""
    return round(MAX_RATIO * float(body_pt), 6)


def declared_width_pt(text_width_pt: float, fraction: float) -> float:
    """`fraction * \\textwidth`, from TeX points to PDF points."""
    return float(text_width_pt) * float(fraction) * TEX_PT_TO_PDF_PT


def _rounded_box(box) -> list:
    return [round(float(value), 3) for value in box]


def _char_matrix(textpage, index: int) -> tuple:
    matrix = pdfium_c.FS_MATRIX()
    if not pdfium_c.FPDFText_GetMatrix(textpage, index, matrix):
        return (1.0, 0.0, 0.0, 1.0)
    return (matrix.a, matrix.b, matrix.c, matrix.d)


def _read_spans(page) -> list:
    textpage = page.get_textpage()
    spans = []
    current = None

    def close():
        nonlocal current
        if current is not None:
            spans.append(current)
            current = None

    try:
        for index in range(textpage.count_chars()):
            code = pdfium_c.FPDFText_GetUnicode(textpage, index)
            char = chr(code) if code else ""
            if not char or char.isspace() or pdfium_c.FPDFText_IsGenerated(textpage, index) == 1:
                close()
                continue
            font_size = float(pdfium_c.FPDFText_GetFontSize(textpage, index))
            a, b, c, d = _char_matrix(textpage, index)
            size = font_size * math.hypot(c, d)
            key = (round(font_size, 3), round(a, 4), round(b, 4), round(c, 4), round(d, 4))
            box = textpage.get_charbox(index)
            if current is not None and current["_key"] != key:
                close()
            if current is None:
                current = {
                    "text": char,
                    "size_pt": round(size, 3),
                    "font_size": round(font_size, 3),
                    "angle_deg": round(math.degrees(math.atan2(b, a)), 2),
                    "bbox": list(box),
                    "_key": key,
                }
            else:
                current["text"] += char
                left, bottom, right, top = current["bbox"]
                current["bbox"] = [
                    min(left, box[0]), min(bottom, box[1]),
                    max(right, box[2]), max(top, box[3]),
                ]
        close()
    finally:
        textpage.close()
    for span in spans:
        del span["_key"]
        span["bbox"] = _rounded_box(span["bbox"])
    return spans


def pdf_text_spans(pdf: Path, page_index: int = 0) -> list[dict]:
    """Every word/run of the page's text layer with its effective size."""
    document = pdfium.PdfDocument(str(pdf))
    try:
        return _read_spans(document[page_index])
    finally:
        document.close()


def printed_font_report(figure_pdf: Path, printed_width_pt: float | None, body_pt: float) -> dict:
    """The printed-size range verdict for one figure placed at
    `printed_width_pt`: every span within [floor, cap]."""
    document = pdfium.PdfDocument(str(figure_pdf))
    try:
        page = document[0]
        left, _, right, _ = page.get_mediabox()
        spans = _read_spans(page)
    finally:
        document.close()
    mediabox_width = float(right - left)
    scale = 1.0 if printed_width_pt is None else float(printed_width_pt) / mediabox_width
    floor_tex = min_printed_pt(body_pt)
    floor_pdf = floor_tex * TEX_PT_TO_PDF_PT
    cap_tex = max_printed_pt(body_pt)
    cap_pdf = cap_tex * TEX_PT_TO_PDF_PT
    report = {
        "verdict": "unmeasured",
        "reason": None,
        "scale": round(scale, 6),
        "mediabox_width_pt": round(mediabox_width, 3),
        "printed_width_pt": None if printed_width_pt is None else round(float(printed_width_pt), 3),
        "body_pt": float(body_pt),
        "min_printed_pt": floor_tex,
        "min_printed_pdf_pt": round(floor_pdf, 4),
        "max_printed_pt": cap_tex,
        "max_printed_pdf_pt": round(cap_pdf, 4),
        "smallest_printed_pt": None,
        "largest_printed_pt": None,
        "span_count": len(spans),
        "offending": [],
    }
    if not spans:
        report["reason"] = (
            "NO_TEXT_LAYER: the PDF carries no extractable text (a raster image "
            "or text converted to outlines), so printed sizes cannot be measured"
        )
        return report
    offending = []
    smallest = None
    largest = None
    for span in spans:
        printed = span["size_pt"] * scale
        smallest = printed if smallest is None else min(smallest, printed)
        largest = printed if largest is None else max(largest, printed)
        bound = None
        if printed + _EPSILON < floor_pdf:
            bound = "floor"
        elif printed - _CAP_TOLERANCE_PT > cap_pdf:
            bound = "cap"
        if bound is not None:
            offending.append({
                "text": span["text"],
                "size_pt": span["size_pt"],
                "printed_pt": round(printed, 3),
                "bbox": span["bbox"],
                "bound": bound,
            })
    report["smallest_printed_pt"] = round(smallest, 3)
    report["largest_printed_pt"] = round(largest, 3)
    report["offending"] = offending
    report["verdict"] = "fail" if offending else "pass"
    return report


def _path_is_drawn(obj) -> tuple:
    fill_mode = ctypes.c_int(0)
    stroke = ctypes.c_int(0)
    if not pdfium_c.FPDFPath_GetDrawMode(obj.raw, ctypes.byref(fill_mode), ctypes.byref(stroke)):
        return False, False
    return fill_mode.value != 0, bool(stroke.value)


#: Public name of the visibility test every measure shares.
path_is_drawn = _path_is_drawn


def _coverage(box, mediabox) -> float:
    width = min(box[2], mediabox[2]) - max(box[0], mediabox[0])
    height = min(box[3], mediabox[3]) - max(box[1], mediabox[1])
    page_area = (mediabox[2] - mediabox[0]) * (mediabox[3] - mediabox[1])
    if width <= 0 or height <= 0 or page_area <= 0:
        return 0.0
    return width * height / page_area


def content_bbox(pdf: Path, page_index: int = 0) -> dict:
    """Union of the drawn top-level page objects and its margins to the
    MediaBox. A filled path covering >= 98 % of the page as the first drawn
    object is reported as `full_page_background` and left out of the union,
    so the margins describe the real content. Paths neither filled nor
    stroked (invisible) are ignored; form XObjects count by their bounds.

    Only top-level objects are walked (`max_depth=0`): the children of a
    form XObject report bounds in the form's own space, not the page's."""
    document = pdfium.PdfDocument(str(pdf))
    try:
        page = document[page_index]
        mediabox = [float(value) for value in page.get_mediabox()]
        counts = {"text": 0, "image": 0, "path": 0, "other": 0}
        boxes = []
        background = False
        first = True
        for obj in page.get_objects(max_depth=0):
            kind = obj.type
            if kind == pdfium_c.FPDF_PAGEOBJ_PATH:
                filled, stroked = _path_is_drawn(obj)
                if not (filled or stroked):
                    continue
                box = [float(value) for value in obj.get_bounds()]
                if first and filled and _coverage(box, mediabox) >= _BACKGROUND_COVERAGE:
                    background = True
                    first = False
                    continue
                counts["path"] += 1
            else:
                box = [float(value) for value in obj.get_bounds()]
                if kind == pdfium_c.FPDF_PAGEOBJ_TEXT:
                    counts["text"] += 1
                elif kind == pdfium_c.FPDF_PAGEOBJ_IMAGE:
                    counts["image"] += 1
                else:
                    counts["other"] += 1
            first = False
            boxes.append(box)
    finally:
        document.close()
    result = {
        "mediabox": _rounded_box(mediabox),
        "bbox": None,
        "margins": None,
        "full_page_background": background,
        "counts": counts,
    }
    if boxes:
        union = [
            min(box[0] for box in boxes), min(box[1] for box in boxes),
            max(box[2] for box in boxes), max(box[3] for box in boxes),
        ]
        result["bbox"] = _rounded_box(union)
        result["margins"] = {
            "left": round(union[0] - mediabox[0], 3),
            "bottom": round(union[1] - mediabox[1], 3),
            "right": round(mediabox[2] - union[2], 3),
            "top": round(mediabox[3] - union[3], 3),
        }
    return result


def drawn_path_boxes(pdf: Path, page_index: int = 0) -> list:
    """Bounds of every drawn (filled or stroked) top-level path on the page,
    in drawing order, skipping a first filled path that covers the page
    (the background `content_bbox` reports). The walk `content_bbox` does,
    kept per object for rules that need one drawing's place, such as the
    top of a plot's axes."""
    document = pdfium.PdfDocument(str(pdf))
    try:
        page = document[page_index]
        mediabox = [float(value) for value in page.get_mediabox()]
        boxes = []
        first = True
        for obj in page.get_objects(max_depth=0):
            if obj.type != pdfium_c.FPDF_PAGEOBJ_PATH:
                first = False
                continue
            filled, stroked = _path_is_drawn(obj)
            if not (filled or stroked):
                continue
            box = [float(value) for value in obj.get_bounds()]
            if first and filled and _coverage(box, mediabox) >= _BACKGROUND_COVERAGE:
                first = False
                continue
            first = False
            boxes.append(box)
    finally:
        document.close()
    return boxes
