"""Manuscript QA after compile (spec S6 of
`odd/tasks/figure-and-table-quality.md`).

The fixture manuscript is compiled with pdflatex at test time: page 1 is
clean, page 2 carries a tabular wider than the text block, page 3 a table in
`\\tiny` under an 11 pt body, page 4 a figure whose 5 pt labels are placed at
`0.5\\linewidth`. Spec S2 of `odd/tasks/manuscript-polish-0-54.md` adds a
table left at the body size on page 3 and the same figure at the full
`\\linewidth` on page 4, both above the 0.90 x body cap.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests" / "fixtures" / "manuscript_qa"
sys.path.insert(0, str(REPO / "skills" / "_core" / "figure"))
import manuscript_qa  # noqa: E402

PDFLATEX = shutil.which("pdflatex")


def build_workspace(root: Path) -> Path:
    """`root` as a workspace whose `paper/` holds the compiled fixture."""
    paper = root / "paper"
    paper.mkdir(parents=True)
    (root / "papersmith.yaml").write_text("name: qa-fixture\n", encoding="utf-8")
    for source in FIXTURE.glob("*.tex"):
        shutil.copyfile(source, paper / source.name)
    for name in ("small-text-figure.tex", "main.tex"):
        subprocess.run([PDFLATEX, "-interaction=nonstopmode", name], cwd=paper,
                       capture_output=True, timeout=120, check=False)
    return root


@unittest.skipIf(PDFLATEX is None, "pdflatex is not installed: the fixture manuscript cannot be compiled")
class ManuscriptQaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.scratch = Path(tempfile.mkdtemp(prefix="manuscript-qa-"))
        cls.root = build_workspace(cls.scratch / "ws")
        if not (cls.root / "paper" / "main.pdf").is_file():
            raise unittest.SkipTest("the fixture manuscript did not compile")
        cls.report = manuscript_qa.run(cls.root)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.scratch, ignore_errors=True)

    def on_page(self, page: int, kind: str) -> list[dict]:
        return [f for f in self.report["findings"] if f["page"] == page and f["kind"] == kind]

    def test_the_clean_page_has_no_findings(self) -> None:
        self.assertEqual([f for f in self.report["findings"] if f["page"] == 1], [])
        self.assertEqual([t["verdict"] for t in self.report["tables"] if t["page"] == 1], ["pass"])

    def test_the_text_block_is_inferred_from_the_body_lines(self) -> None:
        # 30 mm margins on A4: the block runs from 85.04 to 510.24 PDF points.
        left, _, right, _ = self.report["pages"][0]["text_block"]
        self.assertAlmostEqual(left, 85.0, delta=1.5)
        self.assertAlmostEqual(right, 510.2, delta=1.5)

    def test_a_table_wider_than_the_text_block_is_flagged_with_its_overfull_box(self) -> None:
        overflow = self.on_page(2, "overflow")
        self.assertTrue({"text", "table-rule"} <= {f["object"] for f in overflow})
        self.assertTrue(all(f["excess_pt"] > manuscript_qa.OVERFLOW_TOLERANCE_PT for f in overflow))
        self.assertIn("Sixth", {f["snippet"] for f in overflow})
        overfull = self.on_page(2, "overfull")
        self.assertEqual(len(overfull), 1)
        self.assertEqual(overfull[0]["lines"], [45, 52])
        self.assertGreater(overfull[0]["excess_pt"], 100)

    def test_a_tiny_table_under_an_eleven_point_body_prints_below_the_floor(self) -> None:
        self.assertEqual(self.report["body_pt"], 11.0)
        fonts = [f for f in self.on_page(3, "table-font") if f["bound"] == "floor"]
        self.assertIn("Accuracy", {f["snippet"] for f in fonts})
        self.assertNotIn("Precision", {f["snippet"] for f in fonts})
        self.assertTrue(all(f["printed_pt"] < f["min_printed_pt"] for f in fonts))
        self.assertEqual(self.on_page(3, "overflow"), [])

    def test_a_figure_with_five_point_labels_prints_below_the_floor(self) -> None:
        fonts = [f for f in self.on_page(4, "figure-font") if f["bound"] == "floor"]
        self.assertIn("Axis", {f["snippet"] for f in fonts})
        self.assertTrue(all(f["printed_pt"] < 7.7 for f in fonts))
        figure = [f for f in self.report["figures"] if f["page"] == 4]
        self.assertEqual([f["verdict"] for f in figure], ["fail", "fail"])
        self.assertEqual(self.on_page(4, "overflow"), [])

    def test_the_report_states_both_bounds_of_the_printed_range(self) -> None:
        self.assertEqual((self.report["min_printed_pt"], self.report["max_printed_pt"]), (7.7, 9.9))
        self.assertAlmostEqual(self.report["max_printed_pdf_pt"], 9.9 * 72 / 72.27, places=3)
        clean = [t for t in self.report["tables"] if t["page"] == 1]
        self.assertLessEqual(clean[0]["largest_printed_pt"], 9.9 * 72 / 72.27)

    def test_a_table_at_the_body_size_prints_above_the_cap(self) -> None:
        fonts = [f for f in self.on_page(3, "table-font") if f["bound"] == "cap"]
        self.assertIn("Precision", {f["snippet"] for f in fonts})
        self.assertNotIn("Accuracy", {f["snippet"] for f in fonts})
        self.assertTrue(all(f["printed_pt"] > f["max_printed_pt"] for f in fonts))
        table = [t for t in self.report["tables"] if t["page"] == 3]
        self.assertEqual([t["verdict"] for t in table], ["fail", "fail"])

    def test_a_figure_stretched_past_the_cap_fails(self) -> None:
        fonts = [f for f in self.on_page(4, "figure-font") if f["bound"] == "cap"]
        self.assertIn("Axis", {f["snippet"] for f in fonts})
        self.assertTrue(all(f["printed_pt"] > 9.9 for f in fonts))
        self.assertEqual(len({tuple(f["bbox"]) for f in fonts}), len(fonts))

    def test_the_report_is_written_with_the_pdf_digest_and_page_images(self) -> None:
        written = json.loads((self.root / "paper" / ".qa" / "qa.json").read_text(encoding="utf-8"))
        pdf = self.root / "paper" / "main.pdf"
        self.assertEqual(written["pdf_sha256"], hashlib.sha256(pdf.read_bytes()).hexdigest())
        self.assertEqual(written["summary"]["pages"], 4)
        if shutil.which("pdftoppm"):
            for page in written["pages"]:
                self.assertTrue((self.root / "paper" / ".qa" / page["png"]).is_file())

    def test_read_reports_staleness_against_the_current_pdf(self) -> None:
        copy = self.scratch / "stale"
        shutil.copytree(self.root, copy)
        self.assertFalse(manuscript_qa.read(copy)["stale"])
        with (copy / "paper" / "main.pdf").open("ab") as handle:
            handle.write(b"\n% changed\n")
        self.assertTrue(manuscript_qa.read(copy)["stale"])
        shutil.rmtree(copy / "paper" / ".qa")
        self.assertEqual(manuscript_qa.read(copy)["status"], "absent")

    def test_the_cli_prints_the_report_as_json(self) -> None:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = manuscript_qa.main(["--root", str(self.root), "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue())["summary"]["findings"],
                         self.report["summary"]["findings"])


class ManuscriptQaTriggerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="manuscript-qa-trigger-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def test_outside_a_workspace_or_without_a_pdf_the_trigger_does_nothing(self) -> None:
        self.assertIsNone(manuscript_qa.refresh(self.root))
        (self.root / "papersmith.yaml").write_text("name: x\n", encoding="utf-8")
        self.assertIsNone(manuscript_qa.refresh(self.root))

    def test_an_unreadable_pdf_becomes_a_warning_never_an_exception(self) -> None:
        (self.root / "papersmith.yaml").write_text("name: x\n", encoding="utf-8")
        (self.root / "paper").mkdir()
        (self.root / "paper" / "main.pdf").write_bytes(b"not a pdf")
        result = manuscript_qa.refresh(self.root)
        self.assertFalse(result["ok"])
        self.assertIn("manuscript QA not run", result["warning"])

    def test_the_cli_without_a_pdf_exits_one(self) -> None:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = manuscript_qa.main(["--root", str(self.root), "--json"])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out.getvalue())["error"], "PDF_ABSENT")


class OverfullLogTests(unittest.TestCase):
    def test_an_overfull_box_lands_on_the_page_after_the_last_shipout(self) -> None:
        log = ("[1{/usr/local/pdftex.map}] [2]\n"
               "Overfull \\hbox (12.5pt too wide) in alignment at lines 7--9\n"
               "[3]\n")
        self.assertEqual(manuscript_qa.overfull_boxes(log), [{
            "kind": "overfull", "page": 3, "lines": [7, 9], "where": "alignment",
            "excess_pt": 12.5,
            "snippet": "Overfull \\hbox (12.5pt too wide) in alignment at lines 7--9"}])


def _manuscript(body: str, preamble: str = r"\documentclass[11pt,onecolumn]{article}") -> str:
    return preamble + "\n\\begin{document}\n" + body + "\n\\end{document}\n"


class TableShapeTests(unittest.TestCase):
    """Spec S5 of odd/tasks/review-prose-and-length.md: two columns or two rows suggest a chart."""

    def test_a_two_column_table_and_a_two_row_table_are_flagged(self) -> None:
        tex = _manuscript("\n".join([
            r"\begin{table}\begin{tabular}{@{}lr@{}}\toprule Venue & Studies \\ \midrule",
            r"Journal & 40 \\ Conference & 12 \\ \bottomrule\end{tabular}\end{table}",
            r"\begin{table}\begin{tabularx}{\linewidth}{lXcc}\toprule A & B & C & D \\ \midrule",
            r"1 & 2 & 3 & 4 \\ \bottomrule\end{tabularx}\end{table}",
            r"\begin{table}\begin{tabular}{lcc}\toprule A & B & C \\ \midrule 1 & 2 & 3 \\",
            r"4 & 5 & 6 \\ \bottomrule\end{tabular}\end{table}",
        ]))
        findings = manuscript_qa.table_shape_findings(tex)
        self.assertEqual([(f["kind"], f["columns"], f["rows"]) for f in findings],
                         [("table-shape", 2, 3), ("table-shape", 4, 2)])
        self.assertEqual(findings[0]["line"], 3)
        self.assertIn("bar or pie chart", findings[0]["advice"])

    def test_p_and_x_columns_count_and_decorations_do_not(self) -> None:
        tex = _manuscript(r"\begin{tabular}{|p{2cm}|>{\centering}m{1cm}|c|}a & b & c \\ d & e & f \\ g & h & i \\ \end{tabular}")
        self.assertEqual(manuscript_qa.table_shape_findings(tex), [])


class ElsevierPageEstimateTests(unittest.TestCase):
    """Spec S7: at most 45 single-column (25 two-column) Elsevier pages, references included."""

    def test_a_short_manuscript_is_within_both_limits(self) -> None:
        estimate = manuscript_qa.elsevier_page_estimate(_manuscript("Short text " * 50 + r"\cite{a,b}\citep{b,c}"))
        self.assertEqual((estimate["words"], estimate["references"], estimate["floats"]), (100, 3, 0))
        self.assertEqual((estimate["limit_single_column"], estimate["limit_two_column"]), (45, 25))
        self.assertTrue(estimate["within"])
        self.assertEqual(manuscript_qa.page_budget_findings(estimate), [])

    def test_words_references_and_floats_add_up_and_an_excess_is_a_finding(self) -> None:
        cites = "".join(f"\\cite{{r{i}}} " for i in range(210))
        floats = r"\begin{figure}x\end{figure}\begin{table*}y\end{table*}" * 5
        body = ("word " * 15000) + cites + floats
        estimate = manuscript_qa.elsevier_page_estimate(_manuscript(body))
        self.assertEqual((estimate["references"], estimate["floats"]), (210, 10))
        a = estimate["assumptions"]
        expected = round(a["front_matter_pages"] + estimate["words"] / a["words_per_page"]
                         + 10 * a["pages_per_float"] + 210 / a["references_per_page"], 1)
        self.assertEqual(estimate["estimated_pages_single_column"], expected)
        self.assertGreater(estimate["estimated_pages_single_column"], 45)
        self.assertFalse(estimate["within"])
        [finding] = manuscript_qa.page_budget_findings(estimate)
        self.assertEqual((finding["kind"], finding["limit"], finding["page"]), ("page-budget", 45, None))

    def test_preamble_comments_and_floats_are_not_prose(self) -> None:
        tex = _manuscript("one two three % four five\n" + r"\begin{figure}\caption{six seven}\end{figure}",
                          preamble=r"\documentclass{article}\title{eight nine}")
        self.assertEqual(manuscript_qa.elsevier_page_estimate(tex)["words"], 3)

    def test_input_and_include_files_count_toward_the_length(self) -> None:
        # LaTeX resolves a nested \input against the main document's folder, not the including file's.
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            (base / "sections").mkdir()
            (base / "sections" / "intro.tex").write_text("alpha beta gamma \\input{sections/deeper}", encoding="utf-8")
            (base / "sections" / "deeper.tex").write_text("delta", encoding="utf-8")
            (base / "methods.tex").write_text("epsilon zeta", encoding="utf-8")
            tex = _manuscript(r"one \input{sections/intro} \include{methods} \input{absent}")
            expanded = manuscript_qa.expand_inputs(tex, base)
            self.assertEqual(manuscript_qa.elsevier_page_estimate(expanded)["words"], 7)

    def test_a_compiled_elsarticle_is_measured_against_its_own_layout(self) -> None:
        two = manuscript_qa.elsevier_page_estimate(_manuscript("x", r"\documentclass[5p,times]{elsarticle}"), pages=26)
        self.assertEqual((two["measured_layout"], two["measured_pages"], two["within"]), ("two-column", 26, False))
        one = manuscript_qa.elsevier_page_estimate(_manuscript("x", r"\documentclass[preprint,12pt]{elsarticle}"), pages=44)
        self.assertEqual((one["measured_layout"], one["within"]), ("single-column", True))
        canonical = manuscript_qa.elsevier_page_estimate(_manuscript("x"), pages=80)
        self.assertIsNone(canonical["measured_layout"])
        self.assertTrue(canonical["within"])  # 80 review-mode article pages are not Elsevier pages


if __name__ == "__main__":
    unittest.main()
