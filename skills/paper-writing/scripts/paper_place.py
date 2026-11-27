"""paper_place: the print-quality gate `place` runs before a measured
figure enters the manuscript (specs S2, S3, S4 of
`odd/tasks/figure-and-table-quality.md`; the print cap is spec S2 of
`odd/tasks/manuscript-polish-0-54.md`).

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
    FIGURE_TEXT_ABOVE_PRINT_CAP a text span prints above 0.90 x body

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

Venue layouts (spec S2 of `odd/tasks/venue-figures-and-content-tracking.md`):
`layout` reads one manuscript file's body size and text width, the canonical
`paper/main.tex` or a built venue's `paper/venues/<slug>/main.tex`
(`venue_layouts`). `venue_warnings` measures a figure being placed on every
built venue's page (`place`'s `venueWarnings`); `venue_figure_report`
measures every figure a venue file includes (`venue build`'s
`figure_print`). Both report, neither refuses: the canonical gate above is
the only one that does.
"""
from __future__ import annotations

import json
import re
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
    "FIGURE_TEXT_ABOVE_PRINT_CAP",
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
    """`(\\textwidth in TeX points, source)`: the width `geometry` sets in
    `main.tex`'s preamble (`"geometry"`) when it fixes one, else the width of
    the class and options (`"class"`); `("fallback")` 345 pt (article, a4,
    10 pt) when absent. A plot is measured at the width it actually prints."""
    try:
        text = Path(main_tex).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return print_scale.TEXTWIDTH_PT["article-a4-10pt"], "fallback"
    geometry_width = print_scale.geometry_text_width_pt(Path(main_tex))
    if geometry_width is not None:
        return geometry_width, "geometry"
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


def layout(main_tex: Path, print_scale) -> dict:
    """The page a figure prints on, read from one manuscript file: its body
    size (`print_scale.body_font_pt`; `FALLBACK_BODY_PT` when the file is
    absent) and its `\\textwidth` (`text_width_pt`), each with its source.
    The canonical gate reads `paper/main.tex`; a venue reads its own
    `paper/venues/<slug>/main.tex`, so both are measured the same way."""
    main_tex = Path(main_tex)
    if main_tex.is_file():
        body_pt, body_source = print_scale.body_font_pt(main_tex)
    else:
        body_pt, body_source = print_scale.FALLBACK_BODY_PT, "fallback"
    width_pt, width_source = text_width_pt(main_tex, print_scale)
    return {"bodyPt": float(body_pt), "bodySource": body_source,
            "textWidthPt": float(width_pt), "textWidthSource": width_source}


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
    if first == "FIGURE_TEXT_BELOW_PRINT_FLOOR":
        raise Refused("FIGURE_TEXT_BELOW_PRINT_FLOOR", detail)
    raise Refused("FIGURE_TEXT_ABOVE_PRINT_CAP", detail)


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
    """Measure `pdf` and refuse when it breaks S2/S3/S4 or the print
    range; return the
    measurements when it passes. Writes nothing."""
    kind, fraction = _provenance_fields(provenance)
    print_scale = _print_scale()
    canonical = layout(Path(paper_dir) / "main.tex", print_scale)
    body_pt, body_source = canonical["bodyPt"], canonical["bodySource"]
    width_tex, width_source = canonical["textWidthPt"], canonical["textWidthSource"]
    printed_width = print_scale.declared_width_pt(width_tex, fraction)
    try:
        bounds = print_scale.content_bbox(pdf)
        spans = print_scale.pdf_text_spans(pdf)
        font = print_scale.printed_font_report(pdf, printed_width, body_pt)
        path_boxes = print_scale.drawn_path_boxes(pdf)
    except print_scale.PdfReaderAbsent as exc:
        raise Refused("FIGURE_MEASUREMENT_UNAVAILABLE", f"cannot measure the figure: {exc}") from exc
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
    font_range = figure_dimensions.printed_font_range_verdict(font)
    placed = f"{fraction:g}\\textwidth ({printed_width:.1f} pt, scale {font_range['scale']:.3f})"
    below = [item for item in font_range["offending"] if item.get("bound") == "floor"]
    above = [item for item in font_range["offending"] if item.get("bound") == "cap"]
    if below:
        worst = sorted(below, key=lambda item: item["printed_pt"])[:5]
        listed = ", ".join(f"{item['text']!r} {item['printed_pt']:.2f} pt" for item in worst)
        failures["FIGURE_TEXT_BELOW_PRINT_FLOOR"] = (
            f"text prints below 0.70 x the {body_pt:g} pt body ({font_range['minPrintedPt']:g} pt) at "
            f"{placed}: {listed}; enlarge the fonts (ps_figures.apply_style) or include the figure wider"
        )
    if above:
        worst = sorted(above, key=lambda item: -item["printed_pt"])[:5]
        listed = ", ".join(f"{item['text']!r} {item['printed_pt']:.2f} pt" for item in worst)
        failures["FIGURE_TEXT_ABOVE_PRINT_CAP"] = (
            f"text prints above 0.90 x the {body_pt:g} pt body ({font_range['maxPrintedPt']:g} pt) at "
            f"{placed}: {listed}; reduce the fonts (ps_figures.apply_style sizes every role inside "
            "[0.70, 0.90] x body) or include the figure narrower"
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
            "printed-font-range": font_range,
            "background": background,
            "whitespace": whitespace,
            "in-figure-title": title,
        },
    }


# =====================================================================
# venue layouts (spec S2 of odd/tasks/venue-figures-and-content-tracking.md)
# =====================================================================
#: A figure prints wider than the text when its printed width exceeds the
#: venue `\textwidth` by more than this (TeX points): rounding, never a fit.
WIDTH_TOLERANCE_PT = 0.5

_INCLUDEGRAPHICS_RE = re.compile(r"\\includegraphics\*?\s*(?:\[([^\]]*)\])?\s*\{([^{}]*)\}")
_GRAPHICSPATH_RE = re.compile(r"\\graphicspath\s*\{((?:\s*\{[^{}]*\})*)\s*\}")
_WIDTH_FRACTION_RE = re.compile(r"^(\d*\.?\d*)\s*\\(?:textwidth|linewidth|columnwidth|hsize)$")
_SCALE_RE = re.compile(r"^(\d*\.?\d+)$")
_GRAPHICS_SUFFIXES = (".pdf", ".png", ".jpg", ".jpeg")


def built_venues(paper_dir: Path) -> list:
    """Every venue `venue build` has built (`paper/venues/<slug>/` holding
    both `build.json` and `main.tex`), in slug order."""
    root = Path(paper_dir) / "venues"
    if not root.is_dir():
        return []
    return [entry.name for entry in sorted(root.iterdir())
            if entry.is_dir() and paper_venue.SLUG_RE.match(entry.name)
            and (entry / "build.json").is_file() and (entry / "main.tex").is_file()]


def venue_layouts(paper_dir: Path, print_scale) -> dict:
    """`{slug: layout}` for every built venue: its body size and text width,
    read from the venue's own `main.tex` (the class and options `venue build`
    wrote from the venue requirements, and any `geometry` it kept) by the
    same `layout` the canonical gate uses."""
    return {slug: layout(paper_venue.venue_dir(Path(paper_dir), slug) / "main.tex", print_scale)
            for slug in built_venues(paper_dir)}


def _venue_finding(slug: str, figure: str, kind: str, pdf: Path, page: dict,
                   printed_width_tex: float | None, width_label: str, print_scale) -> tuple:
    """`(measurement, finding or None)`: `pdf` printed at `printed_width_tex`
    (TeX points; `None` = its natural size) on the venue page `page`,
    through the gate's own `printed_font_report` and verdict. A finding
    names each issue -- text below 0.70 x the venue body, a width beyond the
    venue text -- and the remedy: the sizes to redraw at."""
    body = page["bodyPt"]
    text_width = page["textWidthPt"]
    printed_pdf = None if printed_width_tex is None else printed_width_tex * print_scale.TEX_PT_TO_PDF_PT
    font = print_scale.printed_font_report(pdf, printed_pdf, body)
    if printed_width_tex is None:
        printed_width_tex = font["mediabox_width_pt"] / print_scale.TEX_PT_TO_PDF_PT
    verdict = figure_dimensions.printed_font_range_verdict(font)
    below = sorted((item for item in verdict["offending"] if item.get("bound") == "floor"),
                   key=lambda item: item["printed_pt"])
    issues = []
    if below:
        issues.append("below-print-floor")
    if printed_width_tex > text_width + WIDTH_TOLERANCE_PT:
        issues.append("wider-than-text")
    measurement = {
        "slug": slug, "figure": figure, "kind": kind,
        "printedWidthPt": round(printed_width_tex, 2), "width": width_label,
        "smallestPrintedPt": verdict["smallestPrintedPt"], "minPrintedPt": verdict["minPrintedPt"],
        "verdict": "fail" if issues else ("unmeasured" if verdict["verdict"] == "unmeasured" else "pass"),
    }
    if not issues:
        return measurement, None
    target_width = min(printed_width_tex, text_width)
    fraction = target_width / text_width
    floor = verdict["minPrintedPt"]
    details = []
    if below:
        listed = ", ".join(f"{item['text']!r} {item['printed_pt']:.2f} pt" for item in below[:5])
        details.append(f"text prints below 0.70 x the {body:g} pt venue body ({floor:g} pt) at "
                       f"{width_label} ({printed_width_tex:.1f} pt): {listed}")
    if "wider-than-text" in issues:
        details.append(f"it prints {printed_width_tex:.1f} pt wide, wider than the venue "
                       f"\\textwidth ({text_width:g} pt)")
    if kind == "diagram":
        how = (f"redraw the diagram for {slug} at a {body:g} pt body and {target_width:.1f} pt printed "
               f"width (manifest textWidthPt {text_width:g}, widthFraction {fraction:.2f}): every text "
               f"span at least {floor:g} pt printed")
    else:
        how = (f"redraw the figure for {slug} at a {body:g} pt body and {target_width:.1f} pt printed "
               f"width: ps_figures.apply_style({body:g}, printed_width_fraction={fraction:.2f}, "
               f"text_width_pt={text_width:g}), every text span at least {floor:g} pt printed")
    finding = {
        **{key: value for key, value in measurement.items() if key != "verdict"},
        "bodyPt": body, "textWidthPt": text_width, "issues": issues,
        "offending": below[:5], "detail": "; ".join(details), "remedy": how,
    }
    return measurement, finding


def venue_warnings(paper_dir: Path, pdf_source: Path, provenance_source: Path) -> list | None:
    """`place`'s per-venue report, beside its canonical gate: the figure at
    its declared `printedWidthFraction` on every built venue's page, one
    warning per venue it fails. `None` when no venue is built (or the gate
    measured nothing), so `place` prints what it printed before. Never
    refuses."""
    slugs = built_venues(paper_dir)
    if not slugs or not Path(pdf_source).is_file() or not Path(provenance_source).is_file():
        return None
    try:
        provenance = json.loads(Path(provenance_source).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(provenance, dict) or not provenance.get("run"):
        return None
    kind, fraction = _provenance_fields(provenance)
    print_scale = _print_scale()
    warnings = []
    for slug, page in venue_layouts(paper_dir, print_scale).items():
        _, finding = _venue_finding(
            slug, str(pdf_source), "placed", Path(pdf_source), page,
            fraction * page["textWidthPt"], f"{fraction:g}\\textwidth", print_scale)
        if finding is not None:
            warnings.append(finding)
    return warnings


def _included_graphics(tex: str) -> list:
    """`(options, target)` of every `\\includegraphics` in the document."""
    body = paper_venue.strip_comments(tex)
    return [(match.group(1) or "", match.group(2).strip()) for match in _INCLUDEGRAPHICS_RE.finditer(body)]


def _graphics_dirs(tex: str, base: Path) -> list:
    dirs = [base]
    for match in _GRAPHICSPATH_RE.finditer(paper_venue.strip_comments(tex)):
        dirs += [(base / path).resolve() for path in re.findall(r"\{([^{}]*)\}", match.group(1))]
    return dirs


def _resolve_graphic(target: str, dirs: list) -> Path | None:
    candidates = [target] if Path(target).suffix.lower() in _GRAPHICS_SUFFIXES else \
        [target + suffix for suffix in _GRAPHICS_SUFFIXES] + [target]
    for directory in dirs:
        for candidate in candidates:
            path = Path(directory) / candidate
            if path.is_file():
                return path.resolve()
    return None


def _figure_kind(pdf: Path) -> tuple:
    """`("placed" | "diagram" | "figure", declared width fraction or None)`:
    a placed data figure carries `<id>.provenance.json`, a rendered diagram
    `<id>.diagram.json`."""
    for kind, sidecar, key in (("placed", ".provenance.json", "printedWidthFraction"),
                               ("diagram", ".diagram.json", "widthFraction")):
        path = pdf.with_name(pdf.stem + sidecar)
        if path.is_file():
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                record = {}
            value = record.get(key) if isinstance(record, dict) else None
            ok = isinstance(value, (int, float)) and not isinstance(value, bool) and 0 < value <= 1
            return kind, float(value) if ok else None
    return "figure", None


def _declared_width(options: str, text_width: float, declared_fraction: float | None, print_scale) -> tuple:
    """`(printed width in TeX points or None, label)` from the
    `\\includegraphics` options: `width=<f>\\textwidth` (or `\\linewidth`,
    `\\columnwidth`), `width=<length>`, `scale=<s>` (`("scale", s)`), none
    (natural size: `None`). A width this cannot read falls back to the
    figure's own declared fraction, else the full text width."""
    keys = {}
    for item in options.split(","):
        if "=" in item:
            key, value = item.split("=", 1)
            keys[key.strip()] = value.strip()
    if "width" in keys:
        value = keys["width"]
        match = _WIDTH_FRACTION_RE.match(value)
        if match:
            fraction = float(match.group(1)) if match.group(1) not in ("", ".") else 1.0
            return fraction * text_width, f"{fraction:g}\\textwidth"
        length = print_scale._length_pt(value)
        if length is not None:
            return length, value
        fraction = declared_fraction or 1.0
        return fraction * text_width, f"{fraction:g}\\textwidth (declared; {value!r} not read)"
    if "scale" in keys and _SCALE_RE.match(keys["scale"]):
        return ("scale", float(keys["scale"])), f"scale={keys['scale']}"
    return None, "natural size"


def venue_figure_report(paper_dir: Path, slug: str) -> dict:
    """`venue build`'s figure measurement: every figure the venue's
    `main.tex` includes -- placed data figures and rendered diagrams alike --
    at the width its `\\includegraphics` declares, on the venue's own page
    (`venue_layouts`). Each figure below 0.70 x the venue body or wider than
    the venue text is a finding with its remedy. Never refuses: without
    `pypdfium2` the report reads `unmeasured`."""
    venue_tex = paper_venue.venue_dir(Path(paper_dir), slug) / "main.tex"
    try:
        print_scale = _print_scale()
    except Refused as exc:
        return {"status": "unmeasured", "reason": exc.detail,
                "layout": None, "measured": [], "findings": [], "unresolved": [], "skipped": []}
    page = layout(venue_tex, print_scale)
    tex = venue_tex.read_text(encoding="utf-8", errors="replace")
    dirs = _graphics_dirs(tex, venue_tex.parent)
    measured, findings, unresolved, skipped, seen = [], [], [], [], set()
    for options, target in _included_graphics(tex):
        path = _resolve_graphic(target, dirs)
        if path is None:
            unresolved.append(target)
            continue
        figure = paper_venue._relative_to_repo(Path(paper_dir).resolve(), path)
        if path.suffix.lower() != ".pdf":
            skipped.append(figure)
            continue
        if (figure, options) in seen:
            continue
        seen.add((figure, options))
        kind, declared = _figure_kind(path)
        width, label = _declared_width(options, page["textWidthPt"], declared, print_scale)
        try:
            if isinstance(width, tuple):
                natural = print_scale.printed_font_report(path, None, page["bodyPt"])["mediabox_width_pt"]
                width = width[1] * natural / print_scale.TEX_PT_TO_PDF_PT
            measurement, finding = _venue_finding(slug, figure, kind, path, page, width, label, print_scale)
        except print_scale.pdfium.PdfiumError as exc:
            measured.append({"slug": slug, "figure": figure, "kind": kind, "verdict": "unmeasured",
                             "reason": f"cannot be read as a PDF: {exc}"})
            continue
        measured.append(measurement)
        if finding is not None:
            findings.append(finding)
    return {"status": "measured", "layout": page, "measured": measured, "findings": findings,
            "unresolved": unresolved, "skipped": skipped}
