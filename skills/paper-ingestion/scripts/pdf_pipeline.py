"""Per-page routing for paper ingestion, and the fast path behind it.

Most pages of a paper are prose: a digital text layer that PDFium reads exactly
in milliseconds. Only some pages need a layout model -- display equations that
must become LaTeX, tables that must stay tables, scanned pages that need OCR.
Sending the whole paper through the heavy engine pays model time for every
page; this module decides page by page, without loading any model.

``probe_document`` reads each page's characters, fonts and image objects with
pypdfium2 and gives it a route:

    text   digital prose              -> fast path here (pypdfium2)
    empty  no text and no raster      -> fast path (nothing to read)
    math   many math-font glyphs      -> heavy engine (formulas as LaTeX)
    table  a table caption or rows    -> heavy engine (tables as tables)
    scan   images and no text layer   -> heavy engine with OCR

``fast_page_markdown`` turns a ``text`` page into Markdown: headings from
font size and weight, paragraphs from line spacing, hyphenation undone, and
embedded raster figures written as files.

Licenses (checked 2026-10-21): pypdfium2 is Apache-2.0 / BSD-3-Clause and
PDFium is BSD-style, with no copyleft and no revenue or user thresholds.
"""
from __future__ import annotations

import ctypes
import re
import statistics
from dataclasses import dataclass, field
from pathlib import Path

#: Bumped whenever routing or fast-path output changes, so cached pages from an
#: older pipeline are never mistaken for current ones. 5: pages a partial
#: Docling run failed on were cached empty by 4, so its entries are dropped.
PIPELINE_VERSION = "5"

#: Fonts that only typeset mathematics: TeX's math italic, symbols and
#: extensions (CMMI, CMSY, CMEX and their Latin Modern / AMS / Euler kin), and
#: OpenType math faces. Body faces (CMR, CMBX, Times, Nimbus) are not here, so
#: a TeX paper's prose never counts as math. A subset prefix ("ABCDEF+") is
#: stripped before matching.
MATH_FONT = re.compile(
    r"^(?:CMMI|CMSY|CMEX|CMBSY|CMMIB|LMMI|LMSY|LMEX|MSAM|MSBM|EUFM|EUFB|EUSM|EUEX|RSFS|STMARY|WASY"
    r"|.*Math|.*Symbol|Euclid|MTSY|MTEX|MTMI|RMTMI)",
    re.IGNORECASE)

#: Characters that are mathematics wherever they appear: operators, relations,
#: arrows, mathematical alphanumerics. Greek is left out on purpose: a word in
#: Greek, or a unit like the micro sign, is prose.
_MATH_RANGES = ((0x2200, 0x22FF), (0x27C0, 0x27EF), (0x2980, 0x2AFF), (0x1D400, 0x1D7FF), (0x2190, 0x21FF))

#: A display equation is a line mostly set in math fonts: at least this many
#: math glyphs making at least this share of the line. Inline mathematics in a
#: prose line never reaches the share, so a page whose only mathematics is
#: inline stays on the fast path, where it reads as Unicode. Measured on arXiv
#: 1706.03762, counting glyphs per page instead sent 9 of 15 pages to the heavy
#: engine; most carried only inline symbols such as d_model.
#: A display set mostly outside the page's body font counts too: in a paper set
#: in Times, an equation's operator names and digits come in TeX's roman (CMR),
#: so its math-font share alone misses it (Attention(Q,K,V) = softmax(...) in
#: 1706.03762 is 29 % math fonts and 0 % body font).
DISPLAY_GLYPHS_MIN = 6
DISPLAY_SHARE_MIN = 0.4
DISPLAY_BODY_SHARE_MAX = 0.3
DISPLAY_LINE_MIN = 6
DISPLAY_MATH_SHARE_FLOOR = 0.15
#: Fewer characters than this and the page has no usable text layer.
TEXT_CHARS_MIN = 20
#: A raster covering this share of a text-less page makes it a scan.
SCAN_IMAGE_COVER = 0.3
#: Embedded rasters smaller than this share of the page are logos or icons.
FIGURE_IMAGE_COVER = 0.03
#: Lines with three or more numeric cells; this many of them make a table.
TABLE_ROWS_MIN = 4
_CITATION = re.compile(r"\[[\d,\s\u2013-]+\]")
_TABLE_CAPTION = re.compile(r"^\s*(?:Table|Tabla)\s+[0-9IVX]+\b", re.MULTILINE)
_NUMERIC_CELL = re.compile(r"(?<![\w.])[-+]?\d+(?:[.,]\d+)?%?(?![\w.])")

HEAVY_ROUTES = ("math", "table", "scan")


@dataclass
class PageProbe:
    page: int  # 1-based, as people and Docling's page_range count
    chars: int
    math_glyphs: int
    display_lines: int
    image_cover: float
    table_rows: int
    caption: bool
    route: str = "text"
    reason: str = ""

    @property
    def has_table(self) -> bool:
        """A table caption or numeric rows: worth TableFormer's time."""
        return self.caption or self.table_rows >= TABLE_ROWS_MIN

    def as_dict(self) -> dict:
        return {"page": self.page, "route": self.route, "reason": self.reason, "chars": self.chars,
                "math_glyphs": self.math_glyphs, "display_lines": self.display_lines,
                "image_cover": round(self.image_cover, 3),
                "table_rows": self.table_rows}


@dataclass
class Line:
    text: str
    size: float
    bold: bool
    top: float
    bottom: float
    hyphen: bool = False


@dataclass
class FastPage:
    markdown: str
    figures: dict = field(default_factory=dict)  # file name -> PIL image


def _font_name(textpage, index: int, buffer) -> tuple[str, int]:
    import pypdfium2.raw as raw

    flags = ctypes.c_int()
    raw.FPDFText_GetFontInfo(textpage, index, buffer, len(buffer), ctypes.byref(flags))
    name = buffer.value.decode("latin-1", "replace")
    return (name.split("+", 1)[1] if "+" in name[:7] else name), flags.value


def _code_points(textpage, count: int):
    """``(index, code point)`` for each character of a text page.

    PDFium hands a character outside the BMP (math italic 𝑥, an emoji) out as
    its two UTF-16 surrogates at consecutive indices; they are joined into one
    code point at the first index. A surrogate without its partner, from a
    broken ToUnicode map, reads as U+FFFD.
    """
    import pypdfium2.raw as raw

    index = 0
    while index < count:
        code = raw.FPDFText_GetUnicode(textpage, index)
        if 0xD800 <= code <= 0xDBFF and index + 1 < count:
            low = raw.FPDFText_GetUnicode(textpage, index + 1)
            if 0xDC00 <= low <= 0xDFFF:
                yield index, 0x10000 + ((code - 0xD800) << 10) + (low - 0xDC00)
                index += 2
                continue
        yield index, 0xFFFD if 0xD800 <= code <= 0xDFFF else code
        index += 1


def _is_math_char(code: int) -> bool:
    return any(low <= code <= high for low, high in _MATH_RANGES)


def _image_cover(page) -> tuple[float, list]:
    """Share of the page covered by raster images, and the images themselves."""
    import pypdfium2.raw as raw

    width, height = page.get_size()
    area = max(1.0, width * height)
    images = []
    covered = 0.0
    for obj in page.get_objects(filter=[raw.FPDF_PAGEOBJ_IMAGE], max_depth=3):
        left, bottom, right, top = obj.get_bounds()
        share = max(0.0, (right - left) * (top - bottom)) / area
        covered += share
        images.append((share, obj))
    return min(1.0, covered), images


def _is_display(math: int, visible: int, body: int) -> bool:
    """Whether one line is a display equation (see DISPLAY_* above)."""
    if math >= DISPLAY_GLYPHS_MIN and math >= DISPLAY_SHARE_MIN * visible:
        return True
    # The share floor keeps out an author line marked with a few footnote
    # symbols (∗ † ‡) and set in a bold face rather than the body one.
    return (math >= 3 and math >= DISPLAY_MATH_SHARE_FLOOR * visible and visible >= DISPLAY_LINE_MIN
            and body <= DISPLAY_BODY_SHARE_MAX * visible)


def _classify(probe: PageProbe) -> PageProbe:
    if probe.chars < TEXT_CHARS_MIN:
        if probe.image_cover >= SCAN_IMAGE_COVER:
            probe.route, probe.reason = "scan", f"no text layer, images cover {probe.image_cover:.0%}"
        else:
            probe.route, probe.reason = "empty", "no text layer and no page-sized image"
    elif probe.display_lines:
        probe.route, probe.reason = "math", f"{probe.display_lines} display-equation line(s)"
    elif probe.caption or probe.table_rows >= TABLE_ROWS_MIN:
        probe.route = "table"
        probe.reason = "table caption" if probe.caption else f"{probe.table_rows} numeric rows"
    else:
        probe.route, probe.reason = "text", "digital text layer"
    return probe


def probe_page(page, number: int) -> PageProbe:
    import pypdfium2.raw as raw

    textpage = page.get_textpage()
    try:
        count = textpage.count_chars()
        buffer = ctypes.create_string_buffer(256)
        math = 0
        visible = 0
        fonts: dict[str, int] = {}
        lines: list[tuple[int, int, dict[str, int]]] = []  # (math, visible, fonts) per line
        line_math = line_visible = 0
        line_fonts: dict[str, int] = {}
        for index, code in [*_code_points(textpage, count), (count, 0x0A)]:
            if code == 0x0A:
                lines.append((line_math, line_visible, line_fonts))
                line_math = line_visible = 0
                line_fonts = {}
                continue
            if code in (0x0D, 0x20, 0x09) or raw.FPDFText_IsGenerated(textpage, index) == 1:
                continue
            visible += 1
            line_visible += 1
            font = _font_name(textpage, index, buffer)[0]
            fonts[font] = fonts.get(font, 0) + 1
            line_fonts[font] = line_fonts.get(font, 0) + 1
            if _is_math_char(code) or MATH_FONT.match(font):
                math += 1
                line_math += 1
        body_font = max(fonts, key=fonts.get) if fonts else ""
        displays = sum(1 for line_math, line_visible, line_fonts in lines if _is_display(line_math, line_visible, line_fonts.get(body_font, 0)))
        text = textpage.get_text_range()
    finally:
        textpage.close()
    cover, _images = _image_cover(page)
    rows = sum(1 for line in text.splitlines() if len(_NUMERIC_CELL.findall(_CITATION.sub("", line))) >= 3)
    return _classify(PageProbe(page=number, chars=visible, math_glyphs=math, display_lines=displays, image_cover=cover,
                               table_rows=rows, caption=bool(_TABLE_CAPTION.search(text))))


def probe_document(pdf) -> list[PageProbe]:
    """One probe per page of an open ``pypdfium2.PdfDocument``; no model loads."""
    probes = []
    for index in range(len(pdf)):
        page = pdf[index]
        try:
            probes.append(probe_page(page, index + 1))
        finally:
            page.close()
    return probes


def _lines(page) -> list[Line]:
    """The page's text as lines with their font size, weight and vertical span."""
    import pypdfium2.raw as raw

    textpage = page.get_textpage()
    try:
        buffer = ctypes.create_string_buffer(256)
        lines: list[Line] = []
        chars: list[str] = []
        sizes: list[float] = []
        bold: list[bool] = []
        tops: list[float] = []
        bottoms: list[float] = []
        hyphen = False
        left, right, bottom, top = (ctypes.c_double() for _ in range(4))

        def flush() -> None:
            text = "".join(chars).strip()
            if text:
                lines.append(Line(text=text, size=statistics.median(sizes) if sizes else 0.0,
                                  bold=bool(bold) and sum(bold) > len(bold) / 2,
                                  top=max(tops) if tops else 0.0, bottom=min(bottoms) if bottoms else 0.0,
                                  hyphen=hyphen))
            chars.clear(); sizes.clear(); bold.clear(); tops.clear(); bottoms.clear()

        for index, code in _code_points(textpage, textpage.count_chars()):
            if code == 0x0A:
                flush()
                hyphen = False
                continue
            if code == 0x0D:
                continue
            if raw.FPDFText_IsHyphen(textpage, index) == 1:
                hyphen = True
                continue
            if code in (0xFFFE, 0x02):  # PDFium's markers for a soft line-break hyphen
                hyphen = True
                continue
            hyphen = False
            chars.append(chr(code))
            if code == 0x20 or raw.FPDFText_IsGenerated(textpage, index) == 1:
                continue
            sizes.append(round(raw.FPDFText_GetFontSize(textpage, index), 1))
            name, flags = _font_name(textpage, index, buffer)
            weight = raw.FPDFText_GetFontWeight(textpage, index)
            bold.append(weight >= 600 or bool(re.search(r"Bold|Medi|Semibold|Black|CMBX|-BX", name)))
            raw.FPDFText_GetCharBox(textpage, index, ctypes.byref(left), ctypes.byref(right),
                                    ctypes.byref(bottom), ctypes.byref(top))
            tops.append(top.value)
            bottoms.append(bottom.value)
        flush()
        return lines
    finally:
        textpage.close()


def body_size(line_groups: list[list[Line]]) -> float:
    """The body text size: the size most characters are set in."""
    weights: dict[float, int] = {}
    for lines in line_groups:
        for line in lines:
            weights[line.size] = weights.get(line.size, 0) + len(line.text)
    return max(weights, key=weights.get) if weights else 10.0


#: Lines that are page furniture, not content: a bare page number, and the
#: arXiv identifier stamped down the margin of every preprint.
_FURNITURE = re.compile(r"^(?:\d{1,4}|arXiv:\d{4}\.\d{4,5}(?:v\d+)?\s.*)$")
_NUMBERED_HEADING = re.compile(r"^(?:\d+(?:\.\d+)*\.?|[A-Z]\.?(?:\d+(?:\.\d+)*)?|[IVX]+\.)\s+\S")
_MARKDOWN_START = re.compile(r"^(#|>|[-*+]\s|\d+\.\s|```|\|)")


def _heading_level(line: Line, body: float) -> int:
    if len(line.text) > 120 or line.text.endswith((".", ",", ";")) and not _NUMBERED_HEADING.match(line.text):
        return 0
    ratio = line.size / body if body else 1.0
    if ratio >= 1.6:
        return 1
    # A long line set a little larger is a notice or a caption, not a heading.
    if len(line.text.split()) >= 10:
        return 0
    if ratio >= 1.3:
        return 2
    if ratio >= 1.12:
        return 3
    if line.bold and _NUMBERED_HEADING.match(line.text) and len(line.text) <= 80:
        return 2 if line.text.split()[0].count(".") <= 1 else 3
    return 0


def _escape(text: str) -> str:
    """Keep a prose line that happens to start like Markdown from becoming markup."""
    return "\\" + text if _MARKDOWN_START.match(text) else text


def lines_markdown(lines: list[Line], body: float) -> str:
    """Headings and paragraphs from positioned lines."""
    gaps = [above.bottom - below.top for above, below in zip(lines, lines[1:])
            if 0 <= above.bottom - below.top < 3 * body]
    usual_gap = statistics.median(gaps) if gaps else body * 0.3
    blocks: list[str] = []
    paragraph = ""
    previous: Line | None = None

    def close() -> None:
        nonlocal paragraph
        if paragraph.strip():
            blocks.append(_escape(paragraph.strip()))
        paragraph = ""

    for line in lines:
        if _FURNITURE.match(line.text):
            continue
        level = _heading_level(line, body)
        if level:
            close()
            blocks.append("#" * level + " " + line.text)
            previous = None
            continue
        gap = (previous.bottom - line.top) if previous else 0.0
        if previous and (gap > usual_gap + body * 0.6 or gap < -body * 2):
            close()  # a vertical break, or a jump to the next column
        if not paragraph:
            paragraph = line.text
        elif previous and previous.hyphen:
            paragraph += line.text
        else:
            paragraph += " " + line.text
        previous = line
    close()
    return "\n\n".join(blocks)


def fast_page_markdown(page, number: int, body: float, lines: list[Line] | None = None) -> FastPage:
    """Markdown for one digital page, with its embedded raster figures as files."""
    lines = _lines(page) if lines is None else lines
    text = lines_markdown(lines, body)
    figures: dict = {}
    _cover, images = _image_cover(page)
    for share, obj in images:
        if share < FIGURE_IMAGE_COVER:
            continue
        try:
            image = obj.get_bitmap(render=False).to_pil()
        except Exception:  # an image PDFium cannot decode is skipped, not fatal
            continue
        name = f"_page_{number - 1}_Figure_{len(figures)}.png"
        figures[name] = image
    if figures:
        text = (text + "\n\n" if text else "") + "\n\n".join(f"![]({name})" for name in figures)
    return FastPage(markdown=text, figures=figures)


def page_lines(pdf, number: int) -> list[Line]:
    page = pdf[number - 1]
    try:
        return _lines(page)
    finally:
        page.close()


def heavy_runs(probes: list[PageProbe]) -> list[tuple[int, int, bool, bool]]:
    """Consecutive heavy pages as ``(first, last, needs_ocr, needs_tables)`` runs.

    One run is one call to the heavy engine, so pages share a run only when
    they need the same stages: OCR only for scanned pages, and table structure
    only where the probe saw a table. Table structure was 90 % of Docling's
    time on five pages of arXiv 1706.03762 (32.8 of 36.3 s), so a page of
    equations alone never pays for it.
    """
    runs: list[tuple[int, int, bool, bool]] = []
    for probe in probes:
        if probe.route not in HEAVY_ROUTES:
            continue
        ocr = probe.route == "scan"
        tables = ocr or probe.has_table
        if runs and runs[-1][1] == probe.page - 1 and runs[-1][2:] == (ocr, tables):
            runs[-1] = (runs[-1][0], probe.page, ocr, tables)
        else:
            runs.append((probe.page, probe.page, ocr, tables))
    return runs


def page_marker(number: int) -> str:
    """The comment that opens each page's block in the Markdown."""
    return f"<!-- page {number} -->"


PAGE_MARKER = re.compile(r"^<!-- page (\d+) -->$", re.MULTILINE)


# --------------------------------------------------------------------------- #
# Heavy engine: Docling, only for the pages the probe routes to it.
#
# Docling is MIT; the models it runs here are docling-layout-heron
# (Apache-2.0), TableFormer from docling-models, a formula model and RapidOCR
# (Apache-2.0) for scanned pages. None of them carries a revenue or user
# threshold. OCR is named explicitly rather than left to Docling's automatic
# choice, so the engine that runs -- and its license -- is the one written here.
#
# The formula model is chosen by the hardware, because on the wrong device it
# is unusable. Measured on one page of arXiv 1312.6114 (6 display equations):
#   Apple Silicon, Granite-Docling-258M (Apache-2.0) on MLX:   7 s
#   CPU, CodeFormulaV2 (CDLA-Permissive-2.0) via transformers: 253 s
# CodeFormulaV2 does not run on Apple's MPS. So: MLX on Apple Silicon when
# mlx-vlm is installed, CodeFormulaV2 on CUDA, and on a CPU-only machine no
# formula model at all -- its math pages stay on the fast path (formulas as
# Unicode) unless ``formulas_on_cpu`` asks for the slow road.
# --------------------------------------------------------------------------- #


def formula_backend(allow_cpu: bool = False) -> tuple[str | None, str]:
    """``(preset, why)``: the Docling formula preset this machine can run fast."""
    import importlib.util
    import platform

    if platform.system() == "Darwin" and platform.machine() == "arm64" and importlib.util.find_spec("mlx_vlm"):
        return "granite_docling", "Granite-Docling-258M on MLX (Apple Silicon)"
    try:
        import torch

        if torch.cuda.is_available():
            return "codeformulav2", "CodeFormulaV2 on CUDA"
    except ImportError:
        pass
    if allow_cpu:
        return "codeformulav2", "CodeFormulaV2 on CPU (slow: about 40 s per formula)"
    return None, "no formula accelerator (MLX on Apple Silicon, or CUDA); math pages read on the fast path"


class HeavyEngine:
    """Docling converters built lazily, one per OCR need, and reused for every
    run of heavy pages in the session; nothing loads unless a page needs it."""

    name = "docling"

    def __init__(self, images_scale: float = 2.0, formulas_on_cpu: bool = False, table_mode: str = "fast",
                 ocr_lang: tuple[str, ...] = ("en",)):
        self.images_scale = images_scale
        self.formulas_on_cpu = formulas_on_cpu
        self._formula: tuple[str | None, str] | None = None
        # RapidOCR on its torch backend: torch is already here, so OCR adds no
        # runtime; its default language is Chinese, so name the one we read.
        self.ocr_lang = list(ocr_lang)
        self.table_mode = table_mode
        self._converters: dict[tuple[bool, bool], object] = {}

    @staticmethod
    def version() -> str:
        from importlib.metadata import version

        return version("docling")

    # Decided on first use, not at construction: `engine: pdfium` builds this
    # object but never asks, so it never imports torch to look for CUDA.
    @property
    def formula_preset(self) -> str | None:
        if self._formula is None:
            self._formula = formula_backend(self.formulas_on_cpu)
        return self._formula[0]

    @property
    def formula_why(self) -> str:
        self.formula_preset  # noqa: B018 -- decides the backend once
        return self._formula[1]

    def options(self, ocr: bool, tables: bool = True) -> dict:
        return {"ocr": f"rapidocr-torch-{'+'.join(self.ocr_lang)}" if ocr else None, "formulas": self.formula_preset,
                "tables": self.table_mode if tables else None, "images_scale": self.images_scale}

    def _converter(self, ocr: bool, tables: bool = True):
        if (ocr, tables) not in self._converters:
            try:  # optional: a core install has only the fast path, and auto then says so
                from docling.datamodel.base_models import InputFormat
                from docling.datamodel.pipeline_options import (CodeFormulaVlmOptions, PdfPipelineOptions,
                                                                RapidOcrOptions, TableFormerMode)
                from docling.document_converter import DocumentConverter, PdfFormatOption
            except ImportError:
                raise

            options = PdfPipelineOptions()
            options.do_ocr = ocr
            if ocr:
                options.ocr_options = RapidOcrOptions(backend="torch", lang=self.ocr_lang)
            options.do_formula_enrichment = self.formula_preset is not None
            if self.formula_preset:
                options.code_formula_options = CodeFormulaVlmOptions.from_preset(self.formula_preset)
            options.do_table_structure = tables
            options.table_structure_options.mode = (TableFormerMode.ACCURATE if self.table_mode == "accurate"
                                                    else TableFormerMode.FAST)
            options.generate_picture_images = True
            options.images_scale = self.images_scale
            converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)})
            converter.initialize_pipeline(InputFormat.PDF)
            self._converters[(ocr, tables)] = converter
        return self._converters[(ocr, tables)]

    def convert(self, pdf_path: Path, first: int, last: int, ocr: bool, tables: bool = True) -> dict[int, FastPage]:
        """Markdown and figures for the pages of ``first..last`` (1-based,
        inclusive) that Docling converted.

        When a stage fails on some pages of a run, Docling still returns
        (``PARTIAL_SUCCESS``) but leaves those pages out of the document, and
        exporting one gives an empty string. Such a page is left out of the
        result too, so the caller reads it another way and never caches it
        as an empty page.
        """
        try:  # docling_core ships with docling, which is optional
            from docling_core.types.doc import PictureItem
        except ImportError:
            raise

        result = self._converter(ocr, tables).convert(str(pdf_path), page_range=(first, last))
        document = result.document
        pictures: dict[int, list] = {}
        for item, _level in document.iterate_items():
            if isinstance(item, PictureItem) and item.prov:
                pictures.setdefault(item.prov[0].page_no, []).append(item)
        pages: dict[int, FastPage] = {}
        for number in range(first, last + 1):
            if number not in document.pages:
                continue
            text = document.export_to_markdown(page_no=number, escape_underscores=False, compact_tables=True)
            figures: dict = {}
            for picture in pictures.get(number, []):
                image = picture.get_image(document)
                name = f"_page_{number - 1}_Figure_{len(figures)}.png"
                if image is None or "<!-- image -->" not in text:
                    continue
                figures[name] = image
                text = text.replace("<!-- image -->", f"![]({name})", 1)
            text = text.replace("<!-- image -->", "").strip()
            pages[number] = FastPage(markdown=text, figures=figures)
        return pages


# --------------------------------------------------------------------------- #
# Page cache: keyed by the PDF's content, never by its name or location.
# --------------------------------------------------------------------------- #


def sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


class PageCache:
    """One entry per (PDF content, page, route, engine, engine version, options).

    An entry is a folder holding ``entry.json`` and the page's figure files.
    The JSON records the SHA-256 of the Markdown and of every figure, so a
    read verifies the entry before trusting it: an edited, truncated or
    half-written entry is a miss, never a wrong page. Writes go to a temporary
    folder that is renamed into place, so a crash never leaves half an entry.
    """

    def __init__(self, root: Path):
        self.root = root

    @staticmethod
    def key(pdf_sha: str, page: int, route: str, engine: str, engine_version: str, options: dict) -> str:
        import hashlib
        import json

        material = json.dumps({"pipeline": PIPELINE_VERSION, "engine": engine, "version": engine_version,
                               "route": route, "options": options}, sort_keys=True)
        return f"p{page:04d}-{route}-{hashlib.sha256(material.encode()).hexdigest()[:16]}"

    def _folder(self, pdf_sha: str, key: str) -> Path:
        return self.root / pdf_sha[:2] / pdf_sha / key

    def get(self, pdf_sha: str, key: str) -> FastPage | None:
        import hashlib
        import json

        folder = self._folder(pdf_sha, key)
        try:
            entry = json.loads((folder / "entry.json").read_text(encoding="utf-8"))
            markdown = entry["markdown"]
            if hashlib.sha256(markdown.encode("utf-8")).hexdigest() != entry["markdown_sha256"]:
                return None
            figures = {}
            for name, digest in entry["figures"].items():
                if Path(name).name != name or sha256_file(folder / name) != digest:
                    return None
                figures[name] = folder / name
            return FastPage(markdown=markdown, figures=figures)
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def put(self, pdf_sha: str, key: str, page: FastPage, meta: dict) -> None:
        import hashlib
        import json
        import shutil
        import tempfile

        folder = self._folder(pdf_sha, key)
        folder.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".entry-", dir=folder.parent))
        try:
            figures = {}
            for name, image in page.figures.items():
                write_figure(image, staging / name)
                figures[name] = sha256_file(staging / name)
            entry = dict(meta, markdown=page.markdown, figures=figures,
                         markdown_sha256=hashlib.sha256(page.markdown.encode("utf-8")).hexdigest())
            (staging / "entry.json").write_text(json.dumps(entry, sort_keys=True), encoding="utf-8")
            if folder.exists():
                shutil.rmtree(folder)
            staging.rename(folder)
        except Exception:  # an unwritable entry (disk, an image codec) is only a miss later
            shutil.rmtree(staging, ignore_errors=True)

    def verify(self) -> tuple[int, list[Path]]:
        """Re-check every entry; returns (entries checked, entries that fail)."""
        bad: list[Path] = []
        checked = 0
        for entry in sorted(self.root.glob("*/*/*/entry.json")) if self.root.is_dir() else []:
            checked += 1
            folder = entry.parent
            if self.get(folder.parent.name, folder.name) is None:
                bad.append(folder)
        return checked, bad


def write_figure(image, path: Path) -> None:
    """A figure is a PIL image (fresh) or a path (from the cache)."""
    import shutil

    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(image, Path):
        shutil.copyfile(image, path)
        return
    if path.suffix.lower() == ".png":
        image.save(path, format="PNG")
    else:
        (image if image.mode in ("RGB", "L") else image.convert("RGB")).save(path, format="JPEG")
