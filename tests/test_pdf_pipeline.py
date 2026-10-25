"""Page routing, the fast path, the page cache, the sidecar map and fragments.

Every PDF here is written by hand (`make_pdf`), so the suite needs neither a
fixture file nor a model: Helvetica is the body face, Symbol is a math face
(as TeX's CMMI/CMSY are in a real paper), a page drawn only with an image is a
scan. The heavy engine is a stub wherever it would run; what is under test is
which pages reach it, what comes back, and what is cached.
"""
from __future__ import annotations

import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import zlib
from contextlib import redirect_stderr
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "skills" / "paper-ingestion" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import extract_pdf  # noqa: E402
import pdf_fragment  # noqa: E402
import pdf_pipeline  # noqa: E402
import pypdfium2  # noqa: E402

PAGE_W, PAGE_H = 612, 792


def _text(lines: list[tuple[str, float, float, float, str]]) -> str:
    """Content-stream text: (font, size, x, y, string) per line."""
    out = []
    for font, size, x, y, string in lines:
        escaped = string.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        out.append(f"BT /{font} {size} Tf {x} {y} Td ({escaped}) Tj ET")
    return "\n".join(out)


def make_pdf(path: Path, pages: list[dict]) -> Path:
    """A minimal valid PDF. Each page is {"lines": [...]} or {"image": True}."""
    objects: list[bytes] = []

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    catalog = add(b"")  # placeholder, filled last
    pages_id = add(b"")
    helvetica = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    bold = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")
    symbol = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Symbol >>")
    # Helvetica whose ToUnicode map sends x and y outside the BMP (math italic
    # U+1D465, U+1D466), as unicode-math output does, and z to a lone surrogate.
    cmap = (b"/CIDInit /ProcSet findresource begin 12 dict begin begincmap /CMapName /Astral def "
            b"1 begincodespacerange <00> <FF> endcodespacerange 3 beginbfchar "
            b"<78> <D835DC65> <79> <D835DC66> <7A> <D835> endbfchar endcmap "
            b"CMapName currentdict /CMap defineresource pop end end")
    to_unicode = add(b"<< /Length " + str(len(cmap)).encode() + b" >>\nstream\n" + cmap + b"\nendstream")
    astral = add(f"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /ToUnicode {to_unicode} 0 R >>".encode())
    pixels = zlib.compress(bytes([90, 90, 90] * 64 * 64))
    image = add(b"<< /Type /XObject /Subtype /Image /Width 64 /Height 64 /ColorSpace /DeviceRGB "
                b"/BitsPerComponent 8 /Filter /FlateDecode /Length " + str(len(pixels)).encode()
                + b" >>\nstream\n" + pixels + b"\nendstream")
    kids = []
    for page in pages:
        if page.get("image"):
            stream = f"q {PAGE_W - 40} 0 0 {PAGE_H - 40} 20 20 cm /Im1 Do Q".encode()
        else:
            stream = _text(page["lines"]).encode("latin-1")
            if page.get("figure"):
                stream += b"\nq 300 0 0 200 150 80 cm /Im1 Do Q"
        content = add(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")
        kids.append(add(
            f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 {PAGE_W} {PAGE_H}] /Contents {content} 0 R "
            f"/Resources << /Font << /F1 {helvetica} 0 R /F2 {bold} 0 R /F3 {symbol} 0 R /F4 {astral} 0 R >> "
            f"/XObject << /Im1 {image} 0 R >> >> >>".encode()))
    objects[pages_id - 1] = (f"<< /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in kids)}] "
                             f"/Count {len(kids)} >>").encode()
    objects[catalog - 1] = f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode()
    data = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(data))
        data += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(data)
    data += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        data += f"{offset:010d} 00000 n \n".encode()
    data += f"trailer\n<< /Size {len(objects) + 1} /Root {catalog} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(bytes(data))
    return path


def prose(y: float, text: str, size: float = 10) -> tuple:
    return ("F1", size, 72, y, text)


SENTENCE = "The method reads the text layer of each page and keeps the order of its lines intact."

TEXT_PAGE = {"lines": [
    ("F1", 18, 72, 720, "A Study of Routing"),
    ("F2", 10, 72, 690, "1 Introduction"),
    prose(675, SENTENCE), prose(663, SENTENCE), prose(651, "and it ends here."),
    prose(620, "A second paragraph starts after a visible gap in the page."),
    ("F1", 10, 300, 40, "1"),
]}
# A display equation: a line set almost entirely in the math face.
MATH_PAGE = {"lines": [
    prose(720, SENTENCE),
    ("F3", 12, 200, 690, "a b g d e l m s"),
    prose(660, "where each symbol is defined in the text above."),
]}
# Inline symbols only: two math glyphs inside a prose line stay on the fast path.
INLINE_PAGE = {"lines": [
    prose(720, "The rate a depends on b as shown in the analysis of the method."),
    ("F3", 10, 72, 700, "ab"),
    prose(680, SENTENCE),
]}
# An author line in a bold face, marked with footnote symbols from the math
# face: little math and no body font, which is not a display equation.
AUTHOR_PAGE = {"lines": [
    prose(720, SENTENCE), prose(708, SENTENCE),
    ("F2", 10, 72, 690, "Ada Lovelace Analytical Engine Society London"), ("F3", 10, 330, 690, "**"),
]}
TABLE_PAGE = {"lines": [prose(720, "Table 1: Results on the benchmark."), prose(700, "Model 1.0 2.0 3.0")]}
CITED_PAGE = {"lines": [prose(720 - 14 * i, f"Prior work [1, 2, 3] and [4, 5, 6] studied case {i}.") for i in range(6)]}
REFERENCES_PAGE = {"lines": [
    ("F2", 14, 72, 720, "References"),
    prose(700, "[1] A. Author. A first paper. 2020."),
    prose(686, "[2] B. Author. A second paper. 2021."),
]}
APPENDIX_PAGE = {"lines": [("F2", 14, 72, 720, "A Appendix"), prose(700, "The appendix survives the cut.")]}
# Prose whose x and y read as math italic letters outside the BMP (F4's map).
ASTRAL_PAGE = {"lines": [prose(720, SENTENCE), ("F4", 10, 72, 700, "metadata x and the current solution y here"),
                         prose(680, SENTENCE)]}
SCAN_PAGE = {"image": True}
BLANK_PAGE = {"lines": []}


class _Tmp(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="pdf-pipeline-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def pdf(self, *pages: dict, name: str = "paper.pdf") -> Path:
        return make_pdf(self.tmp / name, list(pages))

    def probes(self, *pages: dict) -> list:
        document = pypdfium2.PdfDocument(self.pdf(*pages))
        try:
            return pdf_pipeline.probe_document(document)
        finally:
            document.close()


class ProbeTests(_Tmp):
    def test_each_kind_of_page_gets_its_route(self) -> None:
        routes = [p.route for p in self.probes(TEXT_PAGE, MATH_PAGE, TABLE_PAGE, SCAN_PAGE, BLANK_PAGE)]
        self.assertEqual(routes, ["text", "math", "table", "scan", "empty"])

    def test_inline_symbols_do_not_make_a_math_page(self) -> None:
        probe = self.probes(INLINE_PAGE)[0]
        self.assertEqual(probe.route, "text")
        self.assertGreater(probe.math_glyphs, 0)
        self.assertEqual(probe.display_lines, 0)

    def test_footnote_marks_on_an_author_line_are_not_an_equation(self) -> None:
        probe = self.probes(AUTHOR_PAGE)[0]
        self.assertEqual((probe.route, probe.display_lines), ("text", 0))

    def test_citation_brackets_are_not_table_rows(self) -> None:
        probe = self.probes(CITED_PAGE)[0]
        self.assertEqual((probe.route, probe.table_rows), ("text", 0))

    def test_math_letters_outside_the_bmp_count_as_math_glyphs(self) -> None:
        probe = self.probes(ASTRAL_PAGE)[0]
        self.assertEqual((probe.route, probe.math_glyphs), ("text", 2))

    def test_heavy_runs_group_consecutive_pages_that_need_the_same_stages(self) -> None:
        probes = self.probes(TEXT_PAGE, MATH_PAGE, MATH_PAGE, TABLE_PAGE, SCAN_PAGE, TEXT_PAGE, MATH_PAGE)
        self.assertEqual(pdf_pipeline.heavy_runs(probes),
                         [(2, 3, False, False), (4, 4, False, True), (5, 5, True, True), (7, 7, False, False)])


class FastPathTests(_Tmp):
    def markdown(self, page: dict) -> pdf_pipeline.FastPage:
        document = pypdfium2.PdfDocument(self.pdf(page))
        try:
            lines = pdf_pipeline.page_lines(document, 1)
            body = pdf_pipeline.body_size([lines])
            handle = document[0]
            try:
                return pdf_pipeline.fast_page_markdown(handle, 1, body, lines)
            finally:
                handle.close()
        finally:
            document.close()

    def test_headings_paragraphs_and_no_page_number(self) -> None:
        text = self.markdown(TEXT_PAGE).markdown
        blocks = text.split("\n\n")
        self.assertEqual(blocks[0], "# A Study of Routing")
        self.assertEqual(blocks[1], "## 1 Introduction")
        self.assertEqual(blocks[2], " ".join([SENTENCE, SENTENCE, "and it ends here."]))
        self.assertEqual(blocks[3], "A second paragraph starts after a visible gap in the page.")
        self.assertEqual(len(blocks), 4, "the bare page number is furniture, not a paragraph")

    def test_an_embedded_figure_is_written_as_a_file_and_referenced(self) -> None:
        page = self.markdown(dict(TEXT_PAGE, figure=True))
        self.assertEqual(list(page.figures), ["_page_0_Figure_0.png"])
        self.assertIn("![](_page_0_Figure_0.png)", page.markdown)


class PageCacheTests(_Tmp):
    def test_a_stored_page_comes_back_and_a_tampered_one_is_a_miss(self) -> None:
        from PIL import Image

        cache = pdf_pipeline.PageCache(self.tmp / "cache")
        key = cache.key("ab" * 32, 3, "math", "docling", "docling-1", {"ocr": None})
        page = pdf_pipeline.FastPage("$$x$$", {"_page_2_Figure_0.png": Image.new("RGB", (4, 4))})
        cache.put("ab" * 32, key, page, {"page": 3})
        hit = cache.get("ab" * 32, key)
        self.assertEqual(hit.markdown, "$$x$$")
        self.assertEqual(list(hit.figures), ["_page_2_Figure_0.png"])
        self.assertEqual(cache.verify(), (1, []))

        entry = next((self.tmp / "cache").glob("*/*/*/entry.json"))
        (entry.parent / "_page_2_Figure_0.png").write_bytes(b"not the figure")
        self.assertIsNone(cache.get("ab" * 32, key))
        self.assertEqual(cache.verify(), (1, [entry.parent]))

    def test_the_key_changes_with_engine_version_and_options(self) -> None:
        key = pdf_pipeline.PageCache.key
        base = key("ab" * 32, 1, "math", "docling", "v1", {"ocr": None})
        self.assertNotEqual(base, key("ab" * 32, 1, "math", "docling", "v2", {"ocr": None}))
        self.assertNotEqual(base, key("ab" * 32, 1, "math", "docling", "v1", {"ocr": "rapidocr"}))


class _StubHeavy:
    """Stands in for Docling: records the runs it is asked for."""

    name = "docling"
    formula_preset = "granite_docling"
    formula_why = "stub"

    def __init__(self, fail: bool = False):
        self.calls: list[tuple] = []
        self.fail = fail

    @staticmethod
    def version() -> str:
        return "stub-1"

    def options(self, ocr: bool, tables: bool = True) -> dict:
        return {"ocr": ocr, "tables": tables}

    def convert(self, pdf_path, first, last, ocr, tables=True):
        self.calls.append((first, last, ocr, tables))
        if self.fail:
            raise ImportError("No module named 'docling'")
        return {n: pdf_pipeline.FastPage(f"$$\\alpha_{n}$$") for n in range(first, last + 1)}


class RoutedEngineTests(_Tmp):
    def engine(self, kind: str = "auto", heavy: _StubHeavy | None = None, cache: bool = True):
        routed = extract_pdf.RoutedEngine(kind, "fast", False, self.tmp / "cache" if cache else None)
        routed.heavy = heavy or _StubHeavy()
        return routed

    def render(self, engine, pdf: Path, strip_refs: bool = True) -> tuple[str, dict]:
        out = self.tmp / f"out-{len(list(self.tmp.glob('out-*')))}"
        out.mkdir()
        err = io.StringIO()
        with redirect_stderr(err):
            extract_pdf.render_paper(engine, pdf, strip_refs, out)
        self.stderr = err.getvalue()
        return (out / f"{pdf.stem}.md").read_text(encoding="utf-8"), json.loads(
            (out / f"{pdf.stem}.json").read_text(encoding="utf-8"))

    def test_only_heavy_pages_reach_the_heavy_engine_and_every_page_is_marked(self) -> None:
        heavy = _StubHeavy()
        pdf = self.pdf(TEXT_PAGE, MATH_PAGE, MATH_PAGE, TEXT_PAGE)
        text, sidecar = self.render(self.engine(heavy=heavy), pdf)
        self.assertEqual(heavy.calls, [(2, 3, False, False)])
        self.assertEqual([p["engine"] for p in sidecar["pages"]], ["pdfium", "docling", "docling", "pdfium"])
        for number in range(1, 5):
            self.assertIn(f"<!-- page {number} -->", text)
        self.assertIn("$$\\alpha_2$$", text)
        self.assertEqual([e["page"] for e in sidecar["equations"]], [2, 3])
        self.assertEqual(sidecar["schema"], "papersmith.ingestion/v1")
        self.assertEqual(sidecar["source"]["sha256"], pdf_pipeline.sha256_file(pdf))

    def test_a_second_ingestion_of_the_same_content_converts_nothing(self) -> None:
        pdf = self.pdf(TEXT_PAGE, MATH_PAGE)
        first, _ = self.render(self.engine(), pdf)
        heavy = _StubHeavy()
        moved = self.tmp / "renamed.pdf"
        shutil.copyfile(pdf, moved)
        second, sidecar = self.render(self.engine(heavy=heavy), moved)
        self.assertEqual(heavy.calls, [])
        self.assertTrue(all(p["cached"] for p in sidecar["pages"]))
        self.assertEqual(first, second)

    def test_a_missing_entry_reconverts_its_whole_run_not_the_page_alone(self) -> None:
        pdf = self.pdf(TEXT_PAGE, MATH_PAGE, MATH_PAGE)
        first, _ = self.render(self.engine(), pdf)
        entry = next(f for f in (self.tmp / "cache").glob("*/*/p0003-math-*/entry.json"))
        shutil.rmtree(entry.parent)
        heavy = _StubHeavy()
        second, sidecar = self.render(self.engine(heavy=heavy), pdf)
        self.assertEqual(heavy.calls, [(2, 3, False, False)])
        self.assertEqual([p["cached"] for p in sidecar["pages"]], [True, False, False])
        self.assertEqual(first, second)

    def test_without_the_cache_nothing_is_stored(self) -> None:
        self.render(self.engine(cache=False), self.pdf(TEXT_PAGE, MATH_PAGE))
        self.assertFalse((self.tmp / "cache").exists())

    def test_engine_pdfium_keeps_every_page_on_the_fast_path(self) -> None:
        heavy = _StubHeavy()
        _text, sidecar = self.render(self.engine("pdfium", heavy), self.pdf(MATH_PAGE, TABLE_PAGE))
        self.assertEqual(heavy.calls, [])
        self.assertEqual({p["engine"] for p in sidecar["pages"]}, {"pdfium"})

    def test_engine_pdfium_never_looks_for_a_formula_accelerator(self) -> None:
        real = pdf_pipeline.formula_backend
        pdf_pipeline.formula_backend = lambda *_: self.fail("pdfium must not probe for MLX or CUDA")
        try:
            routed = extract_pdf.RoutedEngine("pdfium", "fast", False, None)
            _text, sidecar = self.render(routed, self.pdf(MATH_PAGE))
        finally:
            pdf_pipeline.formula_backend = real
        self.assertIsNone(sidecar["engine"]["formulas"])

    def test_engine_docling_sends_every_page_with_content(self) -> None:
        heavy = _StubHeavy()
        self.render(self.engine("docling", heavy), self.pdf(TEXT_PAGE, TEXT_PAGE, BLANK_PAGE))
        self.assertEqual(heavy.calls, [(1, 2, False, False)])

    def test_auto_without_docling_reads_heavy_pages_on_the_fast_path_and_says_so(self) -> None:
        heavy = _StubHeavy(fail=True)
        text, sidecar = self.render(self.engine(heavy=heavy), self.pdf(TEXT_PAGE, MATH_PAGE))
        self.assertEqual([p["engine"] for p in sidecar["pages"]], ["pdfium", "pdfium"])
        self.assertIn("Docling unavailable", sidecar["pages"][1]["reason"])
        self.assertIn("Docling is not installed", self.stderr)
        self.assertIn("where each symbol is defined", text)

    def test_a_character_outside_the_bmp_reads_as_one_character(self) -> None:
        text, sidecar = self.render(self.engine("pdfium"), self.pdf(ASTRAL_PAGE))
        self.assertIn("metadata \U0001D465 and the current solution \U0001D466 here", text)
        self.assertEqual(sidecar["pages"][0]["engine"], "pdfium")

    def test_a_lone_surrogate_reads_as_a_replacement_character(self) -> None:
        broken = {"lines": [prose(720, SENTENCE), ("F4", 10, 72, 700, "a broken z map"), prose(680, SENTENCE)]}
        text, _sidecar = self.render(self.engine("pdfium"), self.pdf(broken))
        self.assertIn("a broken \ufffd map", text)

    def test_a_page_docling_failed_on_is_read_on_the_fast_path_and_never_cached(self) -> None:
        class Document:
            # Docling's PARTIAL_SUCCESS: page 3 of the 2-4 run failed, so it is
            # absent from document.pages and exports as an empty string.
            pages = {2: object(), 4: object()}

            def iterate_items(self):
                return iter(())

            def export_to_markdown(self, page_no, **_options):
                return f"$$\\beta_{page_no}$$" if page_no in self.pages else ""

        class Converter:
            def convert(self, source, page_range):
                return type("Result", (), {"document": Document()})()

        heavy = pdf_pipeline.HeavyEngine()
        heavy._formula = ("granite_docling", "stub")
        heavy._converters[(False, False)] = Converter()
        routed = self.engine(heavy=heavy)
        heavy.version = lambda: "stub-1"
        text, sidecar = self.render(routed, self.pdf(TEXT_PAGE, MATH_PAGE, MATH_PAGE, MATH_PAGE))
        self.assertEqual([p["engine"] for p in sidecar["pages"]], ["pdfium", "docling", "pdfium", "docling"])
        self.assertIn("read on the fast path", sidecar["pages"][2]["reason"])
        page3 = text.split("<!-- page 3 -->", 1)[1].split("<!-- page 4 -->", 1)[0]
        self.assertIn("where each symbol is defined", page3)
        self.assertIn("$$\\beta_2$$", text)
        cache = self.tmp / "cache"
        self.assertEqual(sorted(e.parent.name[:5] for e in cache.glob("*/*/*/entry.json")), ["p0001", "p0002", "p0004"])

    def _partial_docling(self):
        class Document:
            pages = {2: object(), 4: object()}

            def iterate_items(self):
                return iter(())

            def export_to_markdown(self, page_no, **_options):
                return f"$$\\beta_{page_no}$$" if page_no in self.pages else ""

        class Converter:
            def convert(self, source, page_range):
                return type("Result", (), {"document": Document()})()

        heavy = pdf_pipeline.HeavyEngine()
        heavy._formula = ("granite_docling", "stub")
        heavy._converters[(False, False)] = Converter()
        heavy.version = lambda: "stub-1"
        return heavy

    def test_a_page_docling_failed_on_says_so_rather_than_unavailable(self) -> None:
        text, sidecar = self.render(self.engine(heavy=self._partial_docling()),
                                    self.pdf(TEXT_PAGE, MATH_PAGE, MATH_PAGE, MATH_PAGE))
        reason = sidecar["pages"][2]["reason"]
        self.assertIn("Docling did not convert this page", reason)
        self.assertNotIn("Docling unavailable", reason)

    def test_engine_docling_fails_the_paper_when_docling_drops_a_page(self) -> None:
        with self.assertRaises(extract_pdf.EngineError) as caught:
            self.render(self.engine("docling", self._partial_docling()),
                        self.pdf(TEXT_PAGE, MATH_PAGE, MATH_PAGE, MATH_PAGE))
        self.assertIn("page(s) 1, 3 of", str(caught.exception))
        cache = self.tmp / "cache"
        self.assertNotIn("p0003", [e.parent.name[:5] for e in cache.glob("*/*/*/entry.json")])

    def test_engine_docling_without_docling_is_an_environment_error(self) -> None:
        with self.assertRaises(extract_pdf.EngineError):
            self.render(self.engine("docling", _StubHeavy(fail=True)), self.pdf(TEXT_PAGE))

    def test_references_leave_the_markdown_but_stay_in_the_map_with_their_page(self) -> None:
        text, sidecar = self.render(self.engine(), self.pdf(TEXT_PAGE, REFERENCES_PAGE, APPENDIX_PAGE))
        self.assertNotIn("A first paper", text)
        self.assertIn("The appendix survives the cut.", text)
        self.assertIn("<!-- page 2 -->", text, "a page marker inside the cut survives it")
        self.assertEqual([(r["text"], r["page"]) for r in sidecar["references"]],
                         [("[1] A. Author. A first paper. 2020.", 2), ("[2] B. Author. A second paper. 2021.", 2)])

    def test_bulleted_references_leave_no_empty_rows(self) -> None:
        class Bulleted(_StubHeavy):
            def convert(self, pdf_path, first, last, ocr, tables=True):
                self.calls.append((first, last, ocr, tables))
                return {n: pdf_pipeline.FastPage("## References\n\n- [1] A first paper.\n- [2] A second paper.")
                        for n in range(first, last + 1)}

        _text, sidecar = self.render(self.engine(heavy=Bulleted()), self.pdf(TABLE_PAGE))
        self.assertEqual([r["text"] for r in sidecar["references"]], ["[1] A first paper.", "[2] A second paper."])

    def test_without_a_formula_accelerator_math_pages_stay_fast(self) -> None:
        heavy = _StubHeavy()
        heavy.formula_preset, heavy.formula_why = None, "no formula accelerator"
        _text, sidecar = self.render(self.engine(heavy=heavy), self.pdf(MATH_PAGE, TABLE_PAGE))
        self.assertEqual(heavy.calls, [(2, 2, False, True)])
        self.assertIn("no formula accelerator", sidecar["pages"][0]["reason"])


class FragmentTests(_Tmp):
    def setUp(self) -> None:
        super().setUp()
        engine = extract_pdf.RoutedEngine("auto", "fast", False, None)
        engine.heavy = _StubHeavy()
        self.paper = self.tmp / "paper"
        self.paper.mkdir()
        with redirect_stderr(io.StringIO()):
            extract_pdf.render_paper(engine, self.pdf(TEXT_PAGE, MATH_PAGE), True, self.paper)

    def run_fragment(self, *argv: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(SCRIPTS / "pdf_fragment.py"), *argv],
                              capture_output=True, text=True)

    def test_one_page_one_heading_one_equation_one_search(self) -> None:
        page = self.run_fragment(str(self.paper), "--page", "2", "--json")
        self.assertEqual(page.returncode, 0, page.stderr)
        self.assertEqual(json.loads(page.stdout)["text"], "$$\\alpha_2$$")
        heading = self.run_fragment(str(self.paper), "--heading", "introduction")
        self.assertTrue(heading.stdout.startswith("## 1 Introduction"))
        self.assertNotIn("<!-- page", heading.stdout)
        equation = self.run_fragment(str(self.paper / "paper.md"), "--equation", "0")
        self.assertEqual(equation.stdout.strip(), "\\alpha_2")
        found = self.run_fragment(str(self.paper / "paper.json"), "--search", "visible gap")
        self.assertIn("[page 1] A second paragraph", found.stdout)

    def test_the_answer_is_capped_and_says_so(self) -> None:
        capped = self.run_fragment(str(self.paper), "--page", "1", "--max-chars", "20")
        self.assertEqual(len(capped.stdout.split("\n")[0]), 20)
        self.assertIn("[truncated: 20 of", capped.stdout)

    def test_nothing_matched_is_1_and_an_unreadable_paper_is_2(self) -> None:
        self.assertEqual(self.run_fragment(str(self.paper), "--page", "9").returncode, 1)
        self.assertEqual(self.run_fragment(str(self.paper), "--heading", "nowhere").returncode, 1)
        self.assertEqual(self.run_fragment(str(self.tmp / "missing"), "--outline").returncode, 2)
        self.assertEqual(self.run_fragment(str(self.paper)).returncode, 2, "one selector is required")


if __name__ == "__main__":
    unittest.main()
