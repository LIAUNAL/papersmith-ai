"""page_space: what `measure` reads from the compiled manuscript around a
figure (spec S2 of `odd/tasks/daprosero-backlog.md`, issue #181 items 1-3).

    body size     the size-option file the class loaded (`size11.clo`,
                  `scrsize11pt.clo`, `mem11.clo`, `bk12.clo`) or IEEEtran's
                  "This is a 10 point document." line in `main.log`
    \\textwidth    geometry's `* \\textwidth=<N>pt` or typearea's
                  `\\textwidth = <N>pt` in `main.log`; else a known class
                  default for one-column standard classes without geometry
    printed width the `width=`/`scale=` of each `\\includegraphics` in
                  `main.tex` (and the files it `\\input`s), resolved against
                  `\\textwidth`, `\\linewidth` and enclosing minipage or
                  subfigure widths
    width share   every figure and table float under `WIDTH_SHARE_FLOOR` of
                  `\\textwidth` (figures from the source, tables from their
                  rules in `main.pdf`) -- an advisory, never a failure
    page space    per page of `main.pdf`: float-only pages and vertical gaps
                  of at least `LARGE_GAP_PT` -- an advisory, never a failure

Every value carries the source it came from. Nothing here compiles LaTeX or
spawns a process: it reads files a compile already wrote. A manuscript PDF
that cannot be read leaves the PDF-read checks `unmeasured` with a reason.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import findings  # noqa: E402

TEX_PT_TO_PDF_PT = 72.0 / 72.27
#: A figure or table printed under this share of `\textwidth` is reported.
WIDTH_SHARE_FLOOR = 0.90
#: A vertical gap on a page at least this tall (PDF points, one inch) is reported.
LARGE_GAP_PT = 72.0
#: pdfTeX wraps its log at `max_print_line` = 79 characters.
_LOG_WRAP = 79
_INPUT_DEPTH = 8

_LOG_BODY_PATTERNS = (
    (re.compile(r"^File: (?:size|bk)(\d+(?:\.\d+)?)\.clo\b", re.M), "size option file"),
    (re.compile(r"^File: scrsize(\d+(?:\.\d+)?)pt\.clo\b", re.M), "KOMA-Script size file"),
    (re.compile(r"^File: mem(\d+(?:\.\d+)?)\.clo\b", re.M), "memoir size file"),
    (re.compile(r"This is an? (\d+(?:\.\d+)?) point document", re.M), "class size line"),
)
_LOG_TEXTWIDTH_PATTERNS = (
    re.compile(r"^\* \\textwidth=(\d+(?:\.\d+)?)pt", re.M),
    re.compile(r"^\(typearea\)\s+\\textwidth\s*=\s*(\d+(?:\.\d+)?)pt", re.M),
)

#: One-column `\textwidth` in TeX points for a class and body size, used only
#: when the preamble loads no geometry and no log states the width. The
#: standard classes give the same width on A4 and letter paper.
_CLASS_TEXTWIDTH_PT = {
    ("article", 10): 345.0, ("article", 11): 360.0, ("article", 12): 390.0,
    ("report", 10): 345.0, ("report", 11): 360.0, ("report", 12): 390.0,
    ("book", 10): 345.0, ("book", 11): 360.0, ("book", 12): 390.0,
    ("llncs", 10): 347.12354,
}
#: Two-column classes whose column width is known (TeX points).
_CLASS_COLUMNWIDTH_PT = {"IEEEtran": 252.0}
_CLASS_TWOCOLUMN_TEXTWIDTH_PT = {"IEEEtran": 516.0}

_UNIT_PT = {"pt": 1.0, "mm": 72.27 / 25.4, "cm": 72.27 / 2.54, "in": 72.27,
            "bp": 72.27 / 72.0, "pc": 12.0}
_NUMBER = r"-?(?:\d+(?:\.\d*)?|\.\d+)"
_ABSOLUTE_RE = re.compile(rf"^({_NUMBER})\s*(pt|mm|cm|in|bp|pc)$")
_RELATIVE_RE = re.compile(rf"^({_NUMBER})?\s*\\(textwidth|linewidth|columnwidth|hsize)$")
_INPUT_RE = re.compile(r"\\(?:input|include)\s*\{([^}]+)\}")
_TOKEN_RE = re.compile(
    r"\\begin\{(?P<benv>figure\*?|table\*?|subfigure|minipage)\}"
    r"(?P<bopts>(?:\s*\[[^\]]*\])*)(?:\s*\{(?P<barg>[^}]*)\})?"
    r"|\\end\{(?P<eenv>figure\*?|table\*?|subfigure|minipage)\}"
    r"|\\includegraphics\s*(?:\[(?P<gopts>[^\]]*)\])?\s*\{(?P<gpath>[^}]*)\}"
    r"|\\begin\{(?P<tenv>tabularx|tabular\*)\}\s*\{(?P<targ>[^}]*)\}"
    r"|\\resizebox\s*\{(?P<rarg>[^}]*)\}"
    r"|\\rule\s*(?:\[[^\]]*\])?\s*\{(?P<ulearg>[^}]*)\}"
    r"|(?P<rowbreak>\\\\|\n[ \t]*\n|\\par\b)"
)
_CAPTION_RE = re.compile(r"\\caption\s*[\[{]")
_FLOAT_LABEL_RE = re.compile(
    r"^(?P<kind>Figure|Fig\.|FIGURE|FIG\.|Table|TABLE)\s+(?P<num>[A-Z]?\d+|[IVXLC]+)(?:\s*[:.|]|\s*$)"
)


# ---------------------------------------------------------------- the log --

def read_log(log_path: Path | None) -> str | None:
    """`main.log` with pdfTeX's 79-column wrapping undone, or `None` when the
    file is absent or unreadable."""
    if log_path is None:
        return None
    try:
        raw = Path(log_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    joined = []
    carry = ""
    for line in raw.splitlines():
        if len(line) == _LOG_WRAP:
            carry += line
            continue
        joined.append(carry + line)
        carry = ""
    if carry:
        joined.append(carry)
    return "\n".join(joined)


def body_pt_from_log(text: str | None) -> tuple | None:
    """`(body size in TeX points, evidence)` from the compiled log, or `None`."""
    if not text:
        return None
    for pattern, label in _LOG_BODY_PATTERNS:
        match = pattern.search(text)
        if match:
            return float(match.group(1)), f"{label}: {match.group(0).strip()}"
    return None


def text_width_from_log(text: str | None) -> float | None:
    """The last `\\textwidth` geometry or typearea wrote to the log, in TeX points."""
    if not text:
        return None
    found = None
    for pattern in _LOG_TEXTWIDTH_PATTERNS:
        for match in pattern.finditer(text):
            found = float(match.group(1))
    return found


# ------------------------------------------------------------- the source --

def _strip_comments(text: str) -> str:
    return "\n".join(re.split(r"(?<!\\)%", line, maxsplit=1)[0] for line in text.splitlines())


def read_manuscript(main_tex: Path | None) -> str | None:
    """`main.tex` with comments stripped and every `\\input`/`\\include` that
    resolves inside its directory spliced in, or `None` when unreadable."""
    if main_tex is None:
        return None
    root = Path(main_tex).resolve().parent

    def load(path: Path, depth: int) -> str | None:
        try:
            text = _strip_comments(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            return None
        if depth >= _INPUT_DEPTH:
            return text

        def splice(match: re.Match) -> str:
            name = match.group(1).strip()
            for candidate in (root / name, root / f"{name}.tex"):
                resolved = candidate.resolve()
                if resolved.is_file() and root in resolved.parents:
                    return load(resolved, depth + 1) or ""
            return match.group(0)

        return _INPUT_RE.sub(splice, text)

    return load(Path(main_tex), 0)


def class_and_options(text: str | None) -> tuple:
    if not text:
        return None, []
    match = findings._DOCUMENTCLASS_RE.search(text)
    if match is None:
        return None, []
    options = [item.strip() for item in (match.group("options") or "").split(",") if item.strip()]
    return match.group("cls").strip(), options


def _is_twocolumn(cls: str | None, options: list) -> bool:
    if "twocolumn" in options:
        return True
    return cls == "IEEEtran" and "onecolumn" not in options


def text_widths(manuscript: str | None, log_text: str | None, body_pt: float) -> dict:
    """`\\textwidth` and `\\columnwidth` in TeX points with their sources."""
    cls, options = class_and_options(manuscript)
    twocolumn = _is_twocolumn(cls, options)
    from_log = text_width_from_log(log_text)
    text_width, source = None, "unknown"
    if from_log is not None:
        text_width, source = from_log, "log"
    elif manuscript and re.search(r"\\usepackage\s*(?:\[[^\]]*\])?\s*\{[^}]*\bgeometry\b", manuscript):
        source = "unknown: geometry sets the width and no log states it"
    elif twocolumn and cls in _CLASS_TWOCOLUMN_TEXTWIDTH_PT:
        text_width, source = _CLASS_TWOCOLUMN_TEXTWIDTH_PT[cls], "class-default"
    elif not twocolumn and (cls, int(body_pt)) in _CLASS_TEXTWIDTH_PT and float(body_pt).is_integer():
        text_width, source = _CLASS_TEXTWIDTH_PT[(cls, int(body_pt))], "class-default"
    if not twocolumn:
        column_width = text_width
    else:
        column_width = _CLASS_COLUMNWIDTH_PT.get(cls)
    return {"textWidthPt": text_width, "textWidthSource": source,
            "columnWidthPt": column_width, "twocolumn": twocolumn}


def length_pt(expr: str, *, line_width, text_width, column_width) -> float | None:
    """A LaTeX width expression in TeX points, or `None` when it cannot be resolved."""
    expr = expr.strip()
    match = _ABSOLUTE_RE.match(expr)
    if match:
        return float(match.group(1)) * _UNIT_PT[match.group(2)]
    match = _RELATIVE_RE.match(expr)
    if match is None:
        return None
    factor = float(match.group(1)) if match.group(1) not in (None, "", "-") else 1.0
    base = {"textwidth": text_width, "linewidth": line_width,
            "columnwidth": column_width, "hsize": line_width}[match.group(2)]
    return None if base is None else factor * base


def _options(text: str | None) -> dict:
    keys = {}
    for item in (text or "").split(","):
        if "=" in item:
            key, value = item.split("=", 1)
            keys[key.strip()] = value.strip().strip("{}")
    return keys


def floats(manuscript: str | None, widths: dict) -> list:
    """Every figure/table float in source order with its placements.

    A placement is one `\\includegraphics` (or a declared table width) with
    its width in TeX points (`None` when unresolved) and the row it sits in;
    rows break at `\\\\`, `\\par` or a blank line. A float's share of the
    text width is its widest row's summed unit widths, where a unit is a
    minipage/subfigure (its declared width) or a bare graphic."""
    if not manuscript:
        return []
    text_width = widths["textWidthPt"]
    column_width = widths["columnWidthPt"]
    result = []
    stack: list = []  # (env, width_pt) for minipage/subfigure, float dicts for floats
    current = None
    for token in _TOKEN_RE.finditer(manuscript):
        env = token.group("benv")
        if env:
            if env.startswith(("figure", "table")):
                star = env.endswith("*")
                line = text_width if (star or not widths["twocolumn"]) else column_width
                current = {"kind": env.rstrip("*"), "env": env, "lineWidthPt": line,
                           "rows": [[]], "placements": [], "captioned": False,
                           "_start": token.end()}
                stack = [("float", line)]
                continue
            if current is None:
                continue
            outer = stack[-1][1] if stack else text_width
            width = length_pt(token.group("barg") or "", line_width=outer,
                              text_width=text_width, column_width=column_width)
            if len(stack) == 1:
                current["rows"][-1].append(width)
            stack.append((env, width))
            continue
        env = token.group("eenv")
        if env:
            if current is None:
                continue
            if env.startswith(("figure", "table")):
                body = manuscript[current.pop("_start"):token.start()]
                current["captioned"] = bool(_CAPTION_RE.search(body))
                result.append(current)
                current, stack = None, []
            elif len(stack) > 1:
                stack.pop()
            continue
        if current is None:
            continue
        line = stack[-1][1] if stack else text_width
        if token.group("gpath") is not None:
            keys = _options(token.group("gopts"))
            width = None
            source = "natural"
            if "width" in keys:
                width = length_pt(keys["width"], line_width=line,
                                  text_width=text_width, column_width=column_width)
                source = "width" if width is not None else f"unresolved width={keys['width']}"
            elif "scale" in keys:
                source = f"scale={keys['scale']}"
            elif keys:
                source = "unresolved: " + ",".join(sorted(keys))
            current["placements"].append({
                "path": token.group("gpath").strip(), "widthPt": width, "source": source,
                "scale": _float_or_none(keys.get("scale")),
            })
            if len(stack) == 1:
                current["rows"][-1].append(width)
        elif any(token.group(name) is not None for name in ("targ", "rarg", "ulearg")):
            expr = next(token.group(name) for name in ("targ", "rarg", "ulearg")
                        if token.group(name) is not None)
            width = length_pt(expr, line_width=line, text_width=text_width,
                              column_width=column_width)
            if token.group("ulearg") is not None and (width is None or width < 1.0):
                continue  # a strut or an unresolvable rule is not the float's content
            current["placements"].append({"path": None, "widthPt": width,
                                          "source": f"declared {expr.strip()}", "scale": None})
            if len(stack) == 1:
                current["rows"][-1].append(width)
        elif token.group("rowbreak") is not None and len(stack) == 1:
            if current["rows"][-1]:
                current["rows"].append([])
    return result


def _float_or_none(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def placement_for(stem: str, float_list: list) -> dict | None:
    """The first `\\includegraphics` whose file stem is `stem`, with every match."""
    matches = []
    for index, item in enumerate(float_list):
        for placement in item["placements"]:
            path = placement["path"]
            if path is None:
                continue
            name = Path(path).name
            if name == stem or Path(name).stem == stem:
                matches.append({**placement, "float": index})
    if not matches:
        return None
    return {"first": matches[0], "count": len(matches)}


# --------------------------------------------------------- the manuscript PDF --

def _rows(spans: list) -> list:
    """Upright spans grouped into lines by vertical overlap, top to bottom."""
    rows: list = []
    for span in sorted(spans, key=lambda item: (-item["bbox"][3], item["bbox"][0])):
        if abs(span.get("angle_deg", 0.0)) >= 1.0:
            continue
        left, bottom, right, top = span["bbox"]
        height = max(top - bottom, 1e-6)
        for row in rows:
            overlap = min(top, row["bbox"][3]) - max(bottom, row["bbox"][1])
            if overlap >= 0.5 * min(height, row["bbox"][3] - row["bbox"][1]):
                row["spans"].append(span)
                row["bbox"] = [min(row["bbox"][0], left), min(row["bbox"][1], bottom),
                               max(row["bbox"][2], right), max(row["bbox"][3], top)]
                row["size_pt"] = max(row["size_pt"], span["size_pt"])
                break
        else:
            rows.append({"bbox": [left, bottom, right, top], "spans": [span],
                         "size_pt": span["size_pt"]})
    for row in rows:
        row["text"] = " ".join(s["text"] for s in sorted(row["spans"], key=lambda s: s["bbox"][0]))
    rows.sort(key=lambda row: -row["bbox"][3])
    return rows


def read_pages(main_pdf: Path) -> list:
    """Per page: its MediaBox, text rows, graphic boxes (images and included
    forms) and drawn path boxes. Raises `print_scale`'s errors unchanged."""
    import print_scale

    pdfium = print_scale.pdfium
    pdfium_c = print_scale.pdfium_c
    document = pdfium.PdfDocument(str(main_pdf))
    try:
        count = len(document)
        pages = []
        for index in range(count):
            page = document[index]
            graphics, paths = [], []
            for obj in page.get_objects(max_depth=0):
                box = [float(value) for value in obj.get_bounds()]
                if obj.type in (pdfium_c.FPDF_PAGEOBJ_IMAGE, pdfium_c.FPDF_PAGEOBJ_FORM):
                    graphics.append(box)
                elif obj.type == pdfium_c.FPDF_PAGEOBJ_PATH:
                    filled, stroked = print_scale.path_is_drawn(obj)
                    if filled or stroked:
                        paths.append(box)
            pages.append({"mediabox": [float(v) for v in page.get_mediabox()],
                          "graphics": graphics, "paths": paths})
    finally:
        document.close()
    for index, page in enumerate(pages):
        page["rows"] = _rows(print_scale.pdf_text_spans(main_pdf, index))
    return pages


def _is_rule(box) -> bool:
    return (box[3] - box[1]) <= 1.5 and (box[2] - box[0]) >= 10.0


def _caption_label(row) -> tuple | None:
    match = _FLOAT_LABEL_RE.match(row["text"])
    if match is None:
        return None
    kind = "table" if match.group("kind").lower().startswith("tab") else "figure"
    return kind, f"{match.group('kind')} {match.group('num')}"


def table_widths(pages: list) -> list:
    """Each table caption in `main.pdf`, in order, with the width of the
    widest horizontal rule nearest to it on its page (PDF points), or `None`
    when no rule sits on that page."""
    tables = []
    for number, page in enumerate(pages, start=1):
        captions = [(row, _caption_label(row)) for row in page["rows"]]
        captions = [(row, label) for row, label in captions if label]
        table_rows = [row for row, (kind, _) in captions if kind == "table"]
        if not table_rows:
            continue
        rules = [box for box in page["paths"] if _is_rule(box)]
        anchors = [row for row, _ in captions]
        owner: dict = {}
        for rule in rules:
            middle = (rule[1] + rule[3]) / 2
            nearest = min(anchors, key=lambda row: abs((row["bbox"][1] + row["bbox"][3]) / 2 - middle))
            owner.setdefault(id(nearest), []).append(rule)
        for row in table_rows:
            owned = owner.get(id(row), [])
            width = max((box[2] - box[0] for box in owned), default=None)
            tables.append({"label": _caption_label(row)[1], "page": number,
                           "widthPt": None if width is None else round(width, 3)})
    return tables


def _merge(intervals: list) -> list:
    merged: list = []
    for bottom, top in sorted(intervals, key=lambda item: -item[1]):
        if merged and top >= merged[-1][0]:
            merged[-1][0] = min(merged[-1][0], bottom)
        else:
            merged.append([bottom, top])
    return merged


def _caption_rows(rows: list) -> set:
    """Ids of every row in a caption paragraph: the label row and the rows
    directly below it at the same size and line spacing."""
    marked = set()
    for index, row in enumerate(rows):
        if _caption_label(row) is None:
            continue
        marked.add(id(row))
        previous = row
        for following in rows[index + 1:]:
            spacing = previous["bbox"][1] - following["bbox"][3]
            if spacing > 0.8 * previous["size_pt"] or abs(following["size_pt"] - row["size_pt"]) > 0.5:
                break
            marked.add(id(following))
            previous = following
    return marked


def _inside(row, boxes) -> bool:
    middle = (row["bbox"][1] + row["bbox"][3]) / 2
    return any(box[1] <= middle <= box[3] for box in boxes)


def page_whitespace(pages: list, text_width_pdf: float | None) -> dict:
    """Per page: whether it holds only floats, its largest vertical gap, and
    every gap of at least `LARGE_GAP_PT`. The trailing gap above the page
    number on the last page is never reported: a document ends where it ends."""
    if text_width_pdf is None:
        text_width_pdf = max((row["bbox"][2] - row["bbox"][0]
                              for page in pages for row in page["rows"]), default=0.0)
    report = []
    flagged = set()
    for number, page in enumerate(pages, start=1):
        rows = page["rows"]
        height = page["mediabox"][3] - page["mediabox"][1]
        footer = None
        if rows:
            last = rows[-1]
            if last["bbox"][3] < page["mediabox"][1] + 0.15 * height and \
                    last["bbox"][2] - last["bbox"][0] < 60.0:
                footer = last
        intervals = [(row["bbox"][1], row["bbox"][3]) for row in rows]
        intervals += [(box[1], box[3]) for box in page["graphics"] + page["paths"]]
        merged = _merge(intervals)
        gaps = []
        for upper, lower in zip(merged, merged[1:]):
            gap = upper[0] - lower[1]
            trailing = footer is not None and lower[1] <= footer["bbox"][3] + 1e-6 \
                and lower[0] >= footer["bbox"][1] - 1e-6
            if trailing and number == len(pages):
                continue
            gaps.append({"topPt": round(upper[0], 3), "bottomPt": round(lower[1], 3),
                         "heightPt": round(gap, 3)})
        captions = [label for label in (_caption_label(row) for row in rows) if label]
        caption_ids = _caption_rows(rows)
        rule_boxes = [box for box in page["paths"] if _is_rule(box)]
        table_band = []
        if rule_boxes:
            table_band = [[min(b[0] for b in rule_boxes), min(b[1] for b in rule_boxes),
                           max(b[2] for b in rule_boxes), max(b[3] for b in rule_boxes)]]
        body_rows = [
            row for row in rows
            if row is not footer and id(row) not in caption_ids
            and not _inside(row, page["graphics"] + table_band)
            and row["bbox"][2] - row["bbox"][0] >= 0.6 * text_width_pdf
        ]
        float_only = bool(captions) and not body_rows
        large = [gap for gap in gaps if gap["heightPt"] >= LARGE_GAP_PT]
        if float_only:
            flagged.add("FLOAT_ONLY_PAGE")
        if large:
            flagged.add("LARGE_GAP")
        report.append({
            "page": number,
            "floatOnly": float_only,
            "captions": [label for _, label in captions],
            "largestGapPt": max((gap["heightPt"] for gap in gaps), default=0.0),
            "largeGaps": large,
        })
    return {
        "verdict": "advisory" if flagged else "pass",
        "reason": sorted(flagged) or None,
        "largeGapPt": LARGE_GAP_PT,
        "pages": report,
    }


# ------------------------------------------------------------- width share --

def width_share(float_list: list, widths: dict, pdf_tables: list | None,
                figure_stem: str | None = None) -> dict:
    """Each float's printed share of `\\textwidth`; under `WIDTH_SHARE_FLOOR`
    is reported. Figures use their source widths; a table uses its declared
    width (`tabularx`, `tabular*`, `\\resizebox`), else the rule width of the
    table with the same ordinal among captioned tables in `main.pdf`."""
    text_width = widths["textWidthPt"]
    if text_width is None:
        return {"verdict": "unmeasured", "reason": "TEXT_WIDTH_UNKNOWN",
                "detail": widths["textWidthSource"], "floor": WIDTH_SHARE_FLOOR, "floats": []}
    text_width_pdf = text_width * TEX_PT_TO_PDF_PT
    entries = []
    narrow = False
    table_ordinal = 0
    for index, item in enumerate(float_list):
        entry = {"index": index, "kind": item["kind"], "env": item["env"],
                 "share": None, "widthPt": None, "source": None, "reason": None}
        row_widths = [row for row in item["rows"] if row]
        resolved = [row for row in row_widths if all(w is not None for w in row)]
        if item["kind"] == "table" and item["captioned"]:
            table_ordinal += 1
        if resolved and len(resolved) == len(row_widths):
            width = max(sum(row) for row in resolved)
            entry.update(widthPt=round(width, 3), source="main.tex")
        elif item["kind"] == "table" and item["captioned"] and pdf_tables is not None \
                and table_ordinal <= len(pdf_tables) \
                and pdf_tables[table_ordinal - 1]["widthPt"] is not None:
            measured = pdf_tables[table_ordinal - 1]
            width = measured["widthPt"] / TEX_PT_TO_PDF_PT
            entry.update(widthPt=round(width, 3), source=f"main.pdf rules ({measured['label']},"
                                                          f" page {measured['page']})")
        else:
            entry["reason"] = "WIDTH_UNRESOLVED"
        if entry["widthPt"] is not None:
            share = round(min(entry["widthPt"] / text_width, 9.99), 4)
            entry["share"] = share
            if share < WIDTH_SHARE_FLOOR - 1e-9:
                entry["reason"] = "NARROW_FLOAT"
                narrow = True
        if figure_stem is not None:
            entry["holdsFigure"] = any(
                p["path"] and (Path(p["path"]).name == figure_stem
                               or Path(Path(p["path"]).name).stem == figure_stem)
                for p in item["placements"])
        entries.append(entry)
    return {
        "verdict": "advisory" if narrow else "pass",
        "reason": "NARROW_FLOAT" if narrow else None,
        "floor": WIDTH_SHARE_FLOOR,
        "textWidthPt": text_width,
        "textWidthPdfPt": round(text_width_pdf, 3),
        "floats": entries,
    }
