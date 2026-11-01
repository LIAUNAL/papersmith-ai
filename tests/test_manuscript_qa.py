"""Manuscript QA after compile (spec S6 of
`odd/tasks/figure-and-table-quality.md`).

The fixture manuscript is compiled with pdflatex at test time: page 1 is
clean, page 2 carries a tabular wider than the text block, page 3 a table in
`\\tiny` under an 11 pt body, page 4 a figure whose 5 pt labels are placed at
`0.5\\linewidth`.
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
        self.assertEqual(overfull[0]["lines"], [40, 47])
        self.assertGreater(overfull[0]["excess_pt"], 100)

    def test_a_tiny_table_under_an_eleven_point_body_prints_below_the_floor(self) -> None:
        self.assertEqual(self.report["body_pt"], 11.0)
        fonts = self.on_page(3, "table-font")
        self.assertIn("Accuracy", {f["snippet"] for f in fonts})
        self.assertTrue(all(f["printed_pt"] < f["min_printed_pt"] for f in fonts))
        self.assertEqual(self.on_page(3, "overflow"), [])

    def test_a_figure_with_five_point_labels_prints_below_the_floor(self) -> None:
        fonts = self.on_page(4, "figure-font")
        self.assertIn("Axis", {f["snippet"] for f in fonts})
        self.assertTrue(all(f["printed_pt"] < 7.7 for f in fonts))
        figure = [f for f in self.report["figures"] if f["page"] == 4]
        self.assertEqual([f["verdict"] for f in figure], ["fail"])
        self.assertEqual(self.on_page(4, "overflow"), [])

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


if __name__ == "__main__":
    unittest.main()
