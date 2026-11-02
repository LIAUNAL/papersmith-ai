"""manuscript_qa: a visual QA pass over the compiled manuscript.

Spec S6 of `odd/tasks/figure-and-table-quality.md`. Given `paper/main.pdf`,
`paper/main.tex` and `paper/main.log`, it measures the PDF itself and writes
`paper/.qa/qa.json` plus one PNG per page under `paper/.qa/pages/`:

- **overflow**: the text block of each page is inferred from the body text
  lines (the left/right edges shared by many lines, the top/bottom of the
  body lines once running headers, footers and page numbers are set
  apart); any text span, image, form XObject or drawn path extending past
  it by more than `OVERFLOW_TOLERANCE_PT` is a finding (page, kind, bbox,
  snippet). Horizontally every object is checked; vertically only an
  object that starts inside the block and runs past it, so a running
  header or footer is never a finding.
- **figure-font** / **table-font**: the printed size of every text span
  inside a figure placement (an image or form XObject, i.e. an
  `\\includegraphics`) or a table region (a stack of horizontal rules:
  booktabs or `\\hline`) against the printed range
  [`print_scale.min_printed_pt(body)`, `print_scale.max_printed_pt(body)`]
  = [0.70, 0.90] x body (the cap is spec S2 of
  `odd/tasks/manuscript-polish-0-54.md`). Each finding names its `bound`
  (`floor` or `cap`). Spans read from the compiled page already carry
  the placement transform, so the size measured is the printed size.
- **overfull**: every `Overfull \\hbox` of `main.log`, with its source lines
  and the page it was shipped on.
- **language** / **placeholder**: Spanish prose and placeholder markers
  (`por definir`, `TODO`, `TBD`, `FIXME`) in `main.tex`'s prose, through
  `paper-writing/scripts/paper_language.py` (spec S4 of
  `odd/tasks/manuscript-polish-0-54.md`): the manuscript is English unless
  it declares another language. Each names its source line and, when found
  in the compiled text, its page.

Why the PDF and not a browser: Playwright renders HTML, not PDFs, so it
cannot see where pdfTeX put a glyph. The geometry comes from pypdfium2
(declared; PyMuPDF is AGPL and undeclared) through `print_scale` (imported,
never copied) and the page images from poppler's `pdftoppm` (100 dpi).
Playwright stays for the dashboard UI (`ui/e2e`).

`qa.json` records the sha256 of `main.pdf` it measured: `read()` reports it
stale as soon as the PDF changes. The pass reports; it never repairs.

Usage: `python manuscript_qa.py --root <workspace> [--json]` (what
`smith paper qa` runs).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import print_scale  # noqa: E402

import pypdfium2 as pdfium  # noqa: E402
import pypdfium2.raw as pdfium_c  # noqa: E402

QA_DIR_REL = Path("paper") / ".qa"
QA_JSON_NAME = "qa.json"
PAGES_DIR_NAME = "pages"
RENDER_DPI = 100
SCHEMA_VERSION = 1
#: An object may pass the inferred text block by this much (PDF points).
OVERFLOW_TOLERANCE_PT = 1.0
#: Span sizes carry 3 decimals; a span set exactly at the 0.90 x body
#: cap must not fail on that rounding (PDF points).
CAP_TOLERANCE_PT = 1e-3
#: The first body glyph sits below the block top by the ascender gap
#: (`\topskip` minus the cap height); a float flush with the block top
#: must not read as an overflow, so the top edge allows half a body size.
TOP_ALLOWANCE_BODY = 0.5
#: A body line is a span within this distance of the body size.
BODY_SIZE_TOLERANCE_PT = 0.6
#: A table rule is a filled or stroked path at most this tall and this wide.
RULE_MAX_HEIGHT_PT = 2.5
RULE_MIN_WIDTH_PT = 20.0
#: Findings kept per page and kind; the summary still counts every one.
MAX_FINDINGS_PER_PAGE_KIND = 40
PDFTOPPM_TIMEOUT_SECONDS = 120

_OVERFULL_RE = re.compile(
    r"Overfull \\hbox \((?P<amount>[0-9.]+)pt too wide\) in (?P<where>paragraph|alignment) "
    r"at lines (?P<start>\d+)--(?P<end>\d+)"
)
_SHIPOUT_RE = re.compile(r"\[(\d+)(?=[\s\]{<]|$)")


# ---------------------------------------------------------------------------
# geometry
# ---------------------------------------------------------------------------

def _round_box(box) -> list[float]:
    return [round(float(value), 2) for value in box]


def _lines(spans: list[dict], body_pdf: float) -> list[dict]:
    """Body-size, unrotated spans grouped into lines by vertical overlap."""
    body = [s for s in spans
            if abs(s["size_pt"] - body_pdf) <= BODY_SIZE_TOLERANCE_PT and abs(s["angle_deg"]) < 1]
    body.sort(key=lambda s: -(s["bbox"][1] + s["bbox"][3]) / 2)
    lines: list[dict] = []
    for span in body:
        middle = (span["bbox"][1] + span["bbox"][3]) / 2
        if lines and abs(lines[-1]["middle"] - middle) <= 0.5 * body_pdf:
            line = lines[-1]
            line["bbox"] = [min(line["bbox"][0], span["bbox"][0]), min(line["bbox"][1], span["bbox"][1]),
                            max(line["bbox"][2], span["bbox"][2]), max(line["bbox"][3], span["bbox"][3])]
            line["text"] += " " + span["text"]
        else:
            lines.append({"bbox": list(span["bbox"]), "middle": middle, "text": span["text"]})
    return lines


def _strip_running(lines: list[dict], page_height: float, body_pdf: float) -> list[dict]:
    """Drop a running header (topmost line) and footer/page number
    (bottommost line) when each stands apart from the rest of the page by
    more than twice the body size inside the outer 15 % band."""
    kept = list(lines)
    if len(kept) >= 2 and kept[0]["bbox"][1] > 0.85 * page_height \
            and kept[0]["bbox"][1] - kept[1]["bbox"][3] > 2 * body_pdf:
        kept = kept[1:]
    if len(kept) >= 2 and kept[-1]["bbox"][3] < 0.15 * page_height \
            and kept[-2]["bbox"][1] - kept[-1]["bbox"][3] > 2 * body_pdf:
        kept = kept[:-1]
    return kept


def _frequent_extreme(values: list[float], *, lowest: bool) -> float | None:
    """The smallest (or largest) edge shared by many lines: edges are
    rounded to 0.5 pt, an edge is frequent when at least a quarter of the
    most common edge's lines (and at least two) share it. A two-column
    page yields both columns' edges; the extreme one bounds the block."""
    if not values:
        return None
    counts = Counter(round(value * 2) / 2 for value in values)
    top = max(counts.values())
    frequent = [edge for edge, count in counts.items() if count >= max(2, 0.25 * top)]
    if not frequent:
        frequent = list(counts)
    return min(frequent) if lowest else max(frequent)


def _page_objects(page) -> list[dict]:
    """Top-level drawn objects of a page: images, form XObjects (an
    `\\includegraphics` of a PDF) and visible paths."""
    objects = []
    # max_depth=0: top-level objects only; the children of a form XObject
    # report bounds in the form's own space, not the page's.
    for obj in page.get_objects(max_depth=0):
        kind = obj.type
        if kind == pdfium_c.FPDF_PAGEOBJ_TEXT:
            continue
        box = [float(value) for value in obj.get_bounds()]
        if kind == pdfium_c.FPDF_PAGEOBJ_IMAGE:
            objects.append({"kind": "image", "bbox": box})
        elif kind == pdfium_c.FPDF_PAGEOBJ_FORM:
            objects.append({"kind": "figure", "bbox": box})
        elif kind == pdfium_c.FPDF_PAGEOBJ_PATH:
            # `print_scale`'s own visibility test (fill mode or stroke),
            # shared so a path invisible to one measure is invisible to all.
            filled, stroked = print_scale.path_is_drawn(obj)
            if filled or stroked:
                objects.append({"kind": "drawing", "bbox": box})
    return objects


def _table_regions(objects: list[dict], body_pdf: float) -> list[list[float]]:
    """Stacks of horizontal rules: each rule thin and wide, consecutive
    rules overlapping horizontally and closer than eight body lines. A
    stack of two or more rules is one table region."""
    rules = sorted((o["bbox"] for o in objects
                    if o["kind"] == "drawing"
                    and o["bbox"][3] - o["bbox"][1] <= RULE_MAX_HEIGHT_PT
                    and o["bbox"][2] - o["bbox"][0] >= RULE_MIN_WIDTH_PT),
                   key=lambda b: -b[3])
    regions: list[list[list[float]]] = []
    for rule in rules:
        if regions:
            last = regions[-1][-1]
            overlap = min(last[2], rule[2]) - max(last[0], rule[0])
            if overlap > 0 and last[1] - rule[3] < 8 * 1.2 * body_pdf:
                regions[-1].append(rule)
                continue
        regions.append([rule])
    return [[min(b[0] for b in stack), min(b[1] for b in stack),
             max(b[2] for b in stack), max(b[3] for b in stack)]
            for stack in regions if len(stack) >= 2]


def _inside(span_box, region) -> bool:
    x = (span_box[0] + span_box[2]) / 2
    y = (span_box[1] + span_box[3]) / 2
    return region[0] - 0.5 <= x <= region[2] + 0.5 and region[1] - 0.5 <= y <= region[3] + 0.5


def _overflow(box, block, *, vertical: bool, top_allowance: float) -> float:
    """How far `box` passes `block` (PDF points); 0 when it does not."""
    left, bottom, right, top = block
    excess = max(left - box[0], box[2] - right, 0.0)
    if vertical and box[1] < top and box[3] > bottom:
        # Starts inside the block vertically and runs past it.
        excess = max(excess, box[3] - (top + top_allowance), bottom - box[1])
    return excess


# ---------------------------------------------------------------------------
# log
# ---------------------------------------------------------------------------

def overfull_boxes(log_text: str) -> list[dict]:
    """Every `Overfull \\hbox` in a pdfTeX log, with the page it landed on:
    the page after the last `[N` shipout marker seen before it."""
    findings = []
    shipped = 0
    for line in log_text.splitlines():
        for match in _SHIPOUT_RE.finditer(line):
            shipped = max(shipped, int(match.group(1)))
        overfull = _OVERFULL_RE.search(line)
        if overfull:
            findings.append({
                "kind": "overfull",
                "page": shipped + 1,
                "lines": [int(overfull.group("start")), int(overfull.group("end"))],
                "where": overfull.group("where"),
                "excess_pt": round(float(overfull.group("amount")), 2),
                "snippet": line.strip()[:160],
            })
    return findings


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------

def render_pages(pdf: Path, out_dir: Path) -> tuple[dict[int, str], str | None]:
    """`pdftoppm -r 100 -png` into `out_dir` (emptied of earlier PNGs
    first). Returns ({page number: file name}, warning)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("page-*.png"):
        old.unlink()
    binary = shutil.which("pdftoppm")
    if binary is None:
        return {}, "pdftoppm not found: install poppler to render page images"
    try:
        done = subprocess.run([binary, "-r", str(RENDER_DPI), "-png", str(pdf), str(out_dir / "page")],
                              capture_output=True, text=True, timeout=PDFTOPPM_TIMEOUT_SECONDS)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {}, f"pdftoppm failed: {type(exc).__name__}: {exc}"[:300]
    pages = {}
    for path in out_dir.glob("page-*.png"):
        try:
            pages[int(path.stem.split("-")[-1])] = path.name
        except ValueError:
            continue
    warning = None if done.returncode == 0 else f"pdftoppm ended with code {done.returncode}"
    return pages, warning


# ---------------------------------------------------------------------------
# the pass
# ---------------------------------------------------------------------------

def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _keep(findings: list[dict], counts: Counter, finding: dict) -> None:
    key = (finding["page"], finding["kind"])
    counts[key] += 1
    if counts[key] <= MAX_FINDINGS_PER_PAGE_KIND:
        findings.append(finding)


# ---------------------------------------------------------------------------
# language (spec S4 of odd/tasks/manuscript-polish-0-54.md)
# ---------------------------------------------------------------------------

def _paper_language():
    """`paper-writing/scripts/paper_language.py`, imported on demand: one
    detector for the write gate, `verify` and this report."""
    scripts = Path(__file__).resolve().parents[2] / "paper-writing" / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import paper_language  # noqa: PLC0415
    return paper_language


def _fold(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def language_findings(tex_text: str, page_texts: list[str] | None = None) -> list[dict]:
    """A `language` finding per Spanish prose line and a `placeholder`
    finding per placeholder marker of `main.tex` (`paper_language.scan`:
    English unless the paper declares another language). Each finding
    names its `main.tex` line and, when `page_texts` (the compiled text of
    each page) holds the line's opening words, the page it printed on;
    otherwise `page` is `None`."""
    report = _paper_language().scan(tex_text)
    folded = [_fold(text) for text in (page_texts or [])]

    def page_of(text: str) -> int | None:
        probe = _fold(" ".join(text.split()[:4]))
        for index, page in enumerate(folded):
            if probe and probe in page:
                return index + 1
        return None

    findings = [{"kind": "language", "page": page_of(hit["text"]), "line": hit["line"],
                 "object": "text", "language": report["language"], "snippet": hit["text"][:80]}
                for hit in report["spanish"]]
    findings += [{"kind": "placeholder", "page": page_of(hit["text"]), "line": hit["line"],
                  "object": "text", "marker": hit["marker"], "snippet": hit["text"][:80]}
                 for hit in report["placeholders"]]
    return findings


def analyze(paper_dir: Path, *, render: bool = True) -> dict[str, Any]:
    """Measure `paper_dir/main.pdf` and return the report (not written)."""
    paper_dir = Path(paper_dir)
    pdf = paper_dir / "main.pdf"
    tex = paper_dir / "main.tex"
    if tex.is_file():
        body_pt, body_source = print_scale.body_font_pt(tex)
    else:
        body_pt, body_source = print_scale.FALLBACK_BODY_PT, "fallback"
    body_pdf = body_pt * print_scale.TEX_PT_TO_PDF_PT
    floor_tex = print_scale.min_printed_pt(body_pt)
    floor_pdf = floor_tex * print_scale.TEX_PT_TO_PDF_PT
    cap_tex = print_scale.max_printed_pt(body_pt)
    cap_pdf = cap_tex * print_scale.TEX_PT_TO_PDF_PT

    document = pdfium.PdfDocument(str(pdf))
    pages: list[dict] = []
    try:
        for index in range(len(document)):
            page = document[index]
            width, height = page.get_size()
            pages.append({"index": index, "width": float(width), "height": float(height),
                          "spans": print_scale.pdf_text_spans(pdf, index),
                          "objects": _page_objects(page)})
    finally:
        document.close()

    # Left/right edges: per page parity (twoside margins alternate), from
    # every body line of those pages; top/bottom: per page when the page
    # has body lines of its own, otherwise the document's extremes.
    for page in pages:
        page["lines"] = _strip_running(_lines(page["spans"], body_pdf), page["height"], body_pdf)
    edges = {}
    for parity in (0, 1):
        lines = [line for page in pages if page["index"] % 2 == parity for line in page["lines"]]
        edges[parity] = (_frequent_extreme([l["bbox"][0] for l in lines], lowest=True),
                         _frequent_extreme([l["bbox"][2] for l in lines], lowest=False))
    tops = [max(l["bbox"][3] for l in p["lines"]) for p in pages if p["lines"]]
    bottoms = [min(l["bbox"][1] for l in p["lines"]) for p in pages if p["lines"]]

    findings: list[dict] = []
    counts: Counter = Counter()
    figures: list[dict] = []
    tables: list[dict] = []
    page_rows: list[dict] = []
    for page in pages:
        number = page["index"] + 1
        left, right = edges[page["index"] % 2]
        if left is None or right is None:
            left, right = edges[1 - page["index"] % 2]
        block = None
        if left is not None and right is not None and tops:
            lines = page["lines"]
            top = max(l["bbox"][3] for l in lines) if len(lines) >= 3 else max(tops)
            bottom = min(l["bbox"][1] for l in lines) if len(lines) >= 3 else min(bottoms)
            block = [left, bottom, right, top]
        page_rows.append({"page": number, "width": round(page["width"], 2),
                          "height": round(page["height"], 2),
                          "text_block": None if block is None else _round_box(block)})
        tables_here = _table_regions(page["objects"], body_pdf)

        if block is not None:
            allowance = TOP_ALLOWANCE_BODY * body_pdf
            for span in page["spans"]:
                excess = _overflow(span["bbox"], block, vertical=True, top_allowance=allowance)
                if excess > OVERFLOW_TOLERANCE_PT:
                    _keep(findings, counts, {"kind": "overflow", "page": number, "object": "text",
                                             "bbox": _round_box(span["bbox"]),
                                             "excess_pt": round(excess, 2),
                                             "snippet": span["text"][:80]})
            for obj in page["objects"]:
                excess = _overflow(obj["bbox"], block, vertical=True, top_allowance=allowance)
                if excess > OVERFLOW_TOLERANCE_PT:
                    in_table = any(_inside(obj["bbox"], region) for region in tables_here)
                    _keep(findings, counts, {"kind": "overflow", "page": number,
                                             "object": "table-rule" if in_table and obj["kind"] == "drawing"
                                             else obj["kind"],
                                             "bbox": _round_box(obj["bbox"]),
                                             "excess_pt": round(excess, 2), "snippet": obj["kind"]})

        for kind, regions in (("figure", [o["bbox"] for o in page["objects"]
                                          if o["kind"] in ("figure", "image")]),
                              ("table", tables_here)):
            for region in regions:
                inside = [s for s in page["spans"] if _inside(s["bbox"], region)]
                outside = []
                for span in inside:
                    if span["size_pt"] + 1e-6 < floor_pdf:
                        outside.append((span, "floor"))
                    elif span["size_pt"] - CAP_TOLERANCE_PT > cap_pdf:
                        outside.append((span, "cap"))
                smallest = min((s["size_pt"] for s in inside), default=None)
                largest = max((s["size_pt"] for s in inside), default=None)
                row = {"page": number, "bbox": _round_box(region), "span_count": len(inside),
                       "smallest_printed_pt": None if smallest is None else round(smallest, 2),
                       "largest_printed_pt": None if largest is None else round(largest, 2),
                       "verdict": "unmeasured" if not inside else ("fail" if outside else "pass")}
                (figures if kind == "figure" else tables).append(row)
                for span, bound in outside:
                    _keep(findings, counts, {"kind": f"{kind}-font", "page": number, "object": "text",
                                             "bbox": _round_box(span["bbox"]),
                                             "printed_pt": round(span["size_pt"], 2),
                                             "min_printed_pt": round(floor_pdf, 2),
                                             "max_printed_pt": round(cap_pdf, 2),
                                             "bound": bound,
                                             "snippet": span["text"][:80]})

    log = paper_dir / "main.log"
    if log.is_file():
        for finding in overfull_boxes(log.read_text(encoding="utf-8", errors="replace")):
            _keep(findings, counts, finding)

    language_warning = None
    if tex.is_file():
        try:
            page_texts = [" ".join(span["text"] for span in page["spans"]) for page in pages]
            for finding in language_findings(tex.read_text(encoding="utf-8", errors="replace"),
                                             page_texts):
                _keep(findings, counts, finding)
        except Exception as exc:  # noqa: BLE001 - a language scan failure never fails the pass
            language_warning = f"language scan not run: {type(exc).__name__}: {exc}"[:300]

    rendered, render_warning = ({}, None)
    if render:
        rendered, render_warning = render_pages(pdf, paper_dir / ".qa" / PAGES_DIR_NAME)
    for row in page_rows:
        name = rendered.get(row["page"])
        row["png"] = None if name is None else f"{PAGES_DIR_NAME}/{name}"

    by_kind = Counter()
    for (_, kind), count in counts.items():
        by_kind[kind] += count
    return {
        "schema": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pdf": "paper/main.pdf",
        "pdf_sha256": _sha256(pdf),
        "body_pt": body_pt,
        "body_source": body_source,
        "min_printed_pt": floor_tex,
        "min_printed_pdf_pt": round(floor_pdf, 3),
        "max_printed_pt": cap_tex,
        "max_printed_pdf_pt": round(cap_pdf, 3),
        "tolerance_pt": OVERFLOW_TOLERANCE_PT,
        "pages": page_rows,
        "figures": figures,
        "tables": tables,
        "findings": findings,
        "summary": {"findings": sum(counts.values()), "by_kind": dict(sorted(by_kind.items())),
                    "pages": len(page_rows)},
        "warnings": [w for w in (render_warning, language_warning) if w],
    }


def run(root: Path | str) -> dict[str, Any]:
    """Measure `<root>/paper/main.pdf` and write `paper/.qa/qa.json`.
    Raises `FileNotFoundError` when there is no compiled manuscript."""
    root = Path(root).expanduser().resolve()
    paper_dir = root / "paper"
    if not (paper_dir / "main.pdf").is_file():
        raise FileNotFoundError("paper/main.pdf does not exist: compile the manuscript first")
    report = analyze(paper_dir)
    out = root / QA_DIR_REL
    out.mkdir(parents=True, exist_ok=True)
    tmp = out / (QA_JSON_NAME + ".tmp")
    tmp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(out / QA_JSON_NAME)
    return report


def refresh(root: Path | str) -> dict[str, Any] | None:
    """The compile trigger: `None` outside a workspace (no
    `papersmith.yaml`) or without `paper/main.pdf`; otherwise a short
    summary, or a warning when the pass failed. Never raises: a QA error
    never fails the compile."""
    try:
        root = Path(root).expanduser().resolve()
        if not (root / "papersmith.yaml").is_file() or not (root / "paper" / "main.pdf").is_file():
            return None
        report = run(root)
        return {"ok": True, "status": "ok", "path": (QA_DIR_REL / QA_JSON_NAME).as_posix(),
                "findings": report["summary"]["findings"], "by_kind": report["summary"]["by_kind"]}
    except Exception as exc:  # noqa: BLE001 - a trigger never fails its command
        return {"ok": False, "status": "error", "path": (QA_DIR_REL / QA_JSON_NAME).as_posix(),
                "warning": f"manuscript QA not run: {type(exc).__name__}: {exc}"[:300]}


def read(root: Path | str) -> dict[str, Any]:
    """`{"status": "absent"|"invalid"|"ok", "stale": bool|None, "report"}`.
    Stale when `paper/main.pdf` no longer has the sha256 the report
    measured (or is gone). Stdlib only."""
    root = Path(root).expanduser().resolve()
    path = root / QA_DIR_REL / QA_JSON_NAME
    if not path.is_file():
        return {"status": "absent", "stale": None, "report": None}
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"status": "invalid", "stale": None, "report": None}
    if not isinstance(report, dict):
        return {"status": "invalid", "stale": None, "report": None}
    pdf = root / "paper" / "main.pdf"
    stale = not pdf.is_file() or _sha256(pdf) != report.get("pdf_sha256")
    return {"status": "ok", "stale": stale, "report": report}


def describe(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    kinds = ", ".join(f"{kind} {count}" for kind, count in summary.get("by_kind", {}).items())
    return (f"manuscript QA: {summary.get('findings', 0)} finding(s) over "
            f"{summary.get('pages', 0)} page(s)" + (f" ({kinds})" if kinds else "")
            + f"; report at {(QA_DIR_REL / QA_JSON_NAME).as_posix()}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Visual QA of the compiled manuscript.")
    parser.add_argument("--root", default=".", help="workspace root (holds paper/main.pdf)")
    parser.add_argument("--json", action="store_true", help="print the full report as JSON")
    args = parser.parse_args(argv)
    try:
        report = run(args.root)
    except FileNotFoundError as exc:
        print(json.dumps({"ok": False, "error": "PDF_ABSENT", "message": str(exc)})
              if args.json else f"error: {exc}", file=sys.stdout if args.json else sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(describe(report))
        for finding in report["findings"]:
            print(f"  page {finding['page']}: {finding['kind']} {finding.get('object', '')} "
                  f"{finding.get('snippet', '')}".rstrip())
        for warning in report["warnings"]:
            print(f"warning: {warning}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
