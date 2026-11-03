"""Paragraphs the reader sees, appendices that earn their place, and diagram
markers that carry a contribution's real name.

- Blocks sit back to back in `main.tex`, and their markers are comments, so
  LaTeX ran the last paragraph of one block into the first of the next: the
  future-work block continued the paragraph before it, and every back-matter
  declaration printed as one run-on paragraph. Those blocks now open their own
  paragraph -- `write` and `humanize --apply` begin their body with a blank
  line -- and `verify` reports any that does not (`own-paragraph`).
- An appendix that prints in one page or less belongs in the body section
  that needs it; `verify` reports it (`appendix-length`).
- `humanize --apply` refuses a bold lead-in in the introduction and the
  experimental set-up, as `write` does.
- A `% node:` marker takes the rest of its line, so a diagram marks a
  contribution by the roster name the Components and caption checks read.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "skills" / "paper-writing" / "scripts"))
sys.path.insert(0, str(REPO / "tests"))
import test_paper_writing as tpw  # noqa: E402

import paper_cli  # noqa: E402
import paper_figure  # noqa: E402
import paper_verify  # noqa: E402
import paper_write  # noqa: E402
from impl_refusals import Refused  # noqa: E402

CLEAN = "This paragraph closes the section."


class Evidence:
    """The one field the structural checks read."""

    def __init__(self, tex: str) -> None:
        self.main_tex_bytes = tex.encode("utf-8")


def block(block_id: str, body: str) -> str:
    return (f"%% paper-writing block {block_id} begin sha256={'0' * 64}\n{body}"
            f"%% paper-writing block {block_id} end\n")


class OwnParagraphCheckTests(unittest.TestCase):
    def test_back_to_back_declarations_fail(self) -> None:
        tex = ("\\section*{Declarations}\n"
               + block("back-matter.bm-funding", "\\textbf{Funding:} None.\n")
               + block("back-matter.bm-conflicts-of-interest", "\\textbf{Conflicts of Interest:} None.\n")
               + "\\bibliography{refs}\n")
        report = paper_verify.check_own_paragraph(Evidence(tex))
        self.assertEqual(report["verdict"], "fail")
        self.assertEqual(report["evidence"]["run_on"], ["back-matter.bm-conflicts-of-interest"])

    def test_a_blank_line_opening_the_body_passes(self) -> None:
        tex = ("\\section*{Declarations}\n"
               + block("back-matter.bm-funding", "\n\\textbf{Funding:} None.\n")
               + block("back-matter.bm-conflicts-of-interest", "\n\\textbf{Conflicts of Interest:} None.\n")
               + block("conclusions.concl-block-4", "\nFuture work follows two directions.\n"))
        self.assertEqual(paper_verify.check_own_paragraph(Evidence(tex))["verdict"], "pass")

    def test_future_work_after_a_paragraph_fails_and_a_blank_line_between_passes(self) -> None:
        run_on = block("conclusions.concl-block-3", "The consequence is clear.\n") \
            + block("conclusions.concl-block-4", "Future work follows two directions.\n")
        self.assertEqual(paper_verify.check_own_paragraph(Evidence(run_on))["verdict"], "fail")
        apart = block("conclusions.concl-block-3", "The consequence is clear.\n") + "\n" \
            + block("conclusions.concl-block-4", "Future work follows two directions.\n")
        self.assertEqual(paper_verify.check_own_paragraph(Evidence(apart))["verdict"], "pass")

    def test_other_blocks_may_continue_a_paragraph(self) -> None:
        tex = block("introduction.block-4a", "The contributions are as follows:\n") \
            + block("introduction.block-4b", "\\begin{itemize}\n\\item A: does a.\n\\end{itemize}\n")
        self.assertEqual(paper_verify.check_own_paragraph(Evidence(tex))["verdict"], "pass")

    def test_both_checks_are_structural(self) -> None:
        for check in ("own-paragraph", "appendix-length"):
            self.assertIn(check, paper_verify.STRUCTURE_CHECKS)


class AppendixLengthTests(unittest.TestCase):
    def appendix(self, body: str) -> str:
        return "\\bibliography{refs}\n" + block("back-matter.bm-appendices", body)

    def test_a_short_appendix_with_an_equation_belongs_in_the_methods(self) -> None:
        body = ("\\appendix\n\\section{Derivations}\nFor any generator the derivative is\n"
                "\\begin{equation}\n a = b\n\\end{equation}\nwhich reduces to the rule.\n")
        report = paper_verify.check_appendix_length(Evidence(self.appendix(body)))
        self.assertEqual(report["verdict"], "fail")
        self.assertEqual(report["evidence"]["move_to"], "materials-and-methods")

    def test_a_short_parameter_table_belongs_in_the_set_up(self) -> None:
        body = ("\\appendix\n\\section{Settings}\n\\begin{tabular}{ll}\nRate & 0.1 \\\\\nEpochs & 100 \\\\\n"
                "\\end{tabular}\n")
        report = paper_verify.check_appendix_length(Evidence(self.appendix(body)))
        self.assertEqual(report["evidence"]["move_to"], "experimental-setup")

    def test_a_dollar_display_counts_once(self) -> None:
        body = "\\appendix\n\\section{Rule}\nThe rule is\n$$ a = b $$\nfor every angle.\n"
        report = paper_verify.check_appendix_length(Evidence(self.appendix(body)))
        self.assertEqual(report["evidence"]["display_equations"], 1)

    def test_a_long_appendix_and_no_appendix_pass(self) -> None:
        long_body = "\\appendix\n\\section{Proof}\n" + ("word " * 900) + "\n"
        self.assertEqual(paper_verify.check_appendix_length(Evidence(self.appendix(long_body)))["verdict"], "pass")
        self.assertEqual(paper_verify.check_appendix_length(Evidence("\\bibliography{refs}\n"))["verdict"], "pass")


class WriterNormalizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.paper_dir = Path(self._tmp.name) / "paper"

    @staticmethod
    def _draft(latex: str) -> dict:
        return {"latex": latex, "bindings": [{"sentence": latex, "binding": "structural"}]}

    def test_write_opens_an_own_paragraph_block_on_a_blank_line(self) -> None:
        block_id = "conclusions.concl-block-4"
        tpw._write_fixture(self.paper_dir, tpw._marker_pair(block_id, b"Old body.\n"))
        contract = tpw._write_contract(block_id=block_id, citations_regime="none", evidence_set=())
        paper_write.write_block(self.paper_dir, contract, self._draft(CLEAN), tpw._CLEAN_AUDIT)
        tex = (self.paper_dir / "main.tex").read_text(encoding="utf-8")
        self.assertIn(f"{block_id} begin", tex)
        self.assertIn(f"\n\n{CLEAN}", tex)

    def test_write_leaves_other_blocks_unchanged(self) -> None:
        block_id = "introduction.block-4b"
        tpw._write_fixture(self.paper_dir, tpw._marker_pair(block_id, b"Old body.\n"))
        contract = tpw._write_contract(block_id=block_id, citations_regime="none", evidence_set=())
        paper_write.write_block(self.paper_dir, contract, self._draft(CLEAN), tpw._CLEAN_AUDIT)
        tex = (self.paper_dir / "main.tex").read_text(encoding="utf-8")
        self.assertNotIn(f"\n\n{CLEAN}", tex)

    def _humanize(self, block_id: str, body: str) -> dict:
        # `humanize` resolves --paper inside the repository, so the fixture
        # lives under the gitignored `.scratch/` tree.
        (REPO / ".scratch").mkdir(exist_ok=True)
        holder = tempfile.TemporaryDirectory(dir=REPO / ".scratch")
        self.addCleanup(holder.cleanup)
        self.paper_dir = Path(holder.name) / "paper"
        tpw._write_fixture(self.paper_dir, tpw._marker_pair(block_id, b"Old body. This paragraph closes the section.\n"))
        args = argparse.Namespace(block=block_id, draft=None, replacement=body, style_target=None,
                                  apply=True, inplace=False, force=True, contract=None,
                                  paper=str(self.paper_dir))
        return paper_cli.cmd_humanize(args)

    def test_humanize_refuses_a_bold_lead_in_in_the_set_up(self) -> None:
        with self.assertRaises(Refused) as caught:
            self._humanize("experimental-setup.es-assessment", "\\textbf{Partition.} " + CLEAN + "\n")
        self.assertEqual(caught.exception.code, "DRAFT_BOLD_LEAD_IN")

    def test_humanize_opens_a_declaration_on_a_blank_line(self) -> None:
        self._humanize("back-matter.bm-funding", "\\textbf{Funding:} " + CLEAN + "\n")
        tex = (self.paper_dir / "main.tex").read_text(encoding="utf-8")
        self.assertIn("\n\n\\textbf{Funding:}", tex)


class DiagramMarkerTests(unittest.TestCase):
    def test_a_marker_takes_the_rest_of_its_line(self) -> None:
        tex = "% node: Circular Data Re-Uploading (CDRU)\n% node: data\n"
        self.assertEqual(paper_figure._tex_nodes(tex), {"Circular Data Re-Uploading (CDRU)", "data"})
        paper_figure.cross_check_manifest(
            {"components": ["Circular Data Re-Uploading (CDRU)", "data"]}, tex)

    def test_a_windows_line_ending_does_not_hide_a_marker(self) -> None:
        tex = "% node: Circular Data Re-Uploading (CDRU)\r\n% node: data\r\n"
        self.assertEqual(paper_figure._tex_nodes(tex), {"Circular Data Re-Uploading (CDRU)", "data"})


if __name__ == "__main__":
    unittest.main()
