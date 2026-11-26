"""The canonical document frame of `paper/main.tex` (`odd/tasks/paper-frame-
venue-front-matter.md`, S2).

`scaffold` writes an empty `main.tex` and `skeleton` opens only block markers,
so nothing wrote the frame a venue build and `verify`'s `back-matter-order`
depend on: the preamble, `\\begin{document}`, one `\\section{...}\\label{...}`
line per body section OUTSIDE the blocks, the back-matter heading, the
bibliography lines and `\\end{document}`. `skeleton --frame` now writes it,
and frames an existing frameless paper around its blocks without changing a
block's bytes or digest; `write` refuses a body draft that carries a section
heading, so the heading cannot drift back inside a block.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "skills" / "paper-writing" / "scripts"))
sys.path.insert(0, str(REPO / "tests"))
import test_paper_writing as tpw  # noqa: E402

import paper_block  # noqa: E402
import paper_cli  # noqa: E402
import paper_declarations  # noqa: E402
import paper_frame  # noqa: E402
import paper_scaffold  # noqa: E402
import paper_venue  # noqa: E402
import paper_verify  # noqa: E402
import paper_write  # noqa: E402
from impl_refusals import Refused  # noqa: E402

SECTIONS = REPO / "sections"


def _regions(data: bytes) -> dict:
    parsed = paper_block.parse(data)
    return {block_id: data[begin["start"]:end["end"]] for block_id, (begin, end) in parsed.pairs.items()}


def _digests(data: bytes) -> dict:
    return {block["id"]: block["digest"] for block in paper_block.status(data)["blocks"]}


class _PaperCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.forge_root = Path(self._tmp.name) / "repo"
        self.forge_root.mkdir()
        self.paper_dir = paper_scaffold.resolve_paper_dir(None, forge_root=self.forge_root)
        paper_scaffold.scaffold(self.paper_dir)
        self.tex = self.paper_dir / "main.tex"

    def skeleton(self, *, related_work="yes", dataset_in="materials", frame=False) -> dict:
        return paper_cli.build_skeleton(
            self.paper_dir, SECTIONS, related_work=related_work, dataset_in=dataset_in, frame=frame,
        )


class FreshFrameTests(_PaperCase):
    """A fresh scaffold + `skeleton --frame` yields the whole frame."""

    def test_every_block_sits_between_begin_and_end_document(self) -> None:
        result = self.skeleton(frame=True)
        data = self.tex.read_bytes()

        self.assertTrue(result["frame"]["framed"])
        self.assertTrue(data.startswith(b"\\documentclass[11pt,onecolumn,a4paper]{article}\n"))
        begin = data.index(b"\\begin{document}\n")
        end = data.index(b"\\end{document}\n")
        regions = paper_block.parse(data).pairs
        self.assertTrue(regions)
        for block_id, (first, last) in regions.items():
            with self.subTest(block=block_id):
                self.assertLess(begin, first["start"])
                self.assertLess(last["end"], end + 1)

    def test_each_body_heading_is_outside_the_blocks_before_its_first_block(self) -> None:
        self.skeleton(frame=True)
        data = self.tex.read_bytes()
        outside = paper_block.project(data)
        expected = {
            "introduction": b"\\section{Introduction}\\label{sec:introduction}",
            "related-work": b"\\section{Related Work}\\label{sec:related-work}",
            "materials-and-methods": b"\\section{Materials and Methods}\\label{sec:materials-and-methods}",
            "experimental-setup": b"\\section{Experimental Set-Up}\\label{sec:experimental-setup}",
            "results-and-discussion": b"\\section{Results and Discussion}\\label{sec:results-and-discussion}",
            "limitations": b"\\section{Limitations}\\label{sec:limitations}",
            "conclusions": b"\\section{Conclusions}\\label{sec:conclusions}",
        }
        parsed = paper_block.parse(data)
        for section, line in expected.items():
            with self.subTest(section=section):
                self.assertEqual(outside.count(line + b"\n"), 1)
                at = data.index(line)
                first = min(begin["start"] for block_id, (begin, _end) in parsed.pairs.items()
                            if block_id.startswith(section + "."))
                self.assertLess(at, first)
                # nothing but the heading separates it from the section's first block
                self.assertEqual(data[at:first], line + b"\n")
        # the headings follow the contracts' document order (`position`)
        positions = [data.index(line) for line in expected.values()]
        self.assertEqual(positions, sorted(positions))

    def test_blocks_follow_document_order_not_writing_order(self) -> None:
        self.skeleton(frame=True)
        order = paper_block.parse(self.tex.read_bytes()).order
        sections = []
        for block_id in order:
            section = block_id.split(".", 1)[0]
            if not sections or sections[-1] != section:
                sections.append(section)
        # every section's blocks are contiguous (the keywords follow the abstract)
        self.assertEqual(sections, [
            "title-and-keywords", "abstract", "title-and-keywords", "introduction", "related-work",
            "materials-and-methods", "experimental-setup", "results-and-discussion", "limitations",
            "conclusions", "back-matter",
        ])
        intro = [b for b in order if b.startswith("introduction.")]
        self.assertEqual(intro, [f"introduction.{b}" for b in
                                 ("block-1", "block-2", "block-3", "block-4a", "block-4b", "block-5", "block-6")])

    def test_front_matter_and_back_matter_follow_the_canonical_layout(self) -> None:
        self.skeleton(frame=True)
        data = self.tex.read_bytes()
        title_end = paper_block.parse(data).pairs["title-and-keywords.title"][1]["end"]
        self.assertEqual(data[title_end:title_end + len(b"\\maketitle\n\\begin{abstract}\n")],
                         b"\\maketitle\n\\begin{abstract}\n")
        self.assertIn(b"\\section*{Back matter}\n%% paper-writing block back-matter.bm-author-contributions begin",
                      data)
        order = paper_block.parse(data).order
        declarations = [b for b in order if b.startswith("back-matter.") and b != "back-matter.bm-appendices"]
        self.assertEqual(declarations[-1], "back-matter.bm-ai-use-declaration")
        bibliography = data.index(b"\\bibliographystyle{unsrtnat}\n\\bibliography{refs}\n")
        appendices = paper_block.parse(data).pairs["back-matter.bm-appendices"][0]["start"]
        self.assertLess(bibliography, appendices)
        self.assertTrue(data.endswith(b"\\end{document}\n"))

    def test_verify_back_matter_order_passes_on_the_fresh_frame(self) -> None:
        self.skeleton(frame=True)
        evidence = type("Evidence", (), {"main_tex_bytes": self.tex.read_bytes()})()
        self.assertEqual(paper_verify.check_back_matter_order(evidence)["verdict"], "pass")

    def test_a_venue_build_reads_the_frame_headings(self) -> None:
        self.skeleton(frame=True)
        manuscript = paper_venue.Manuscript(self.paper_dir)
        self.assertEqual(manuscript.headings["introduction"], "\\section{Introduction}\\label{sec:introduction}")
        self.assertEqual(manuscript.headings["back-matter"], "\\section*{Back matter}")
        self.assertEqual(manuscript.document_class, "article")
        self.assertEqual(manuscript.bibliography_style, "unsrtnat")

    def test_related_work_no_frames_no_related_work_heading(self) -> None:
        self.skeleton(related_work="no", frame=True)
        self.assertNotIn(b"Related Work", self.tex.read_bytes())

    def test_skeleton_without_frame_still_opens_markers_only(self) -> None:
        """The previous behavior of `skeleton` holds without `--frame`."""
        result = self.skeleton()
        data = self.tex.read_bytes()
        self.assertNotIn("frame", result)
        self.assertEqual(paper_block.project(data), b"")
        self.assertNotIn(b"\\begin{document}", data)


class ExistingPaperFrameTests(_PaperCase):
    """A paper whose blocks were opened without a frame obtains it later."""

    def _write_bodies(self) -> None:
        bodies = {
            "introduction.block-1": b"Opening paragraph.\n",
            "materials-and-methods.mm-proposal": b"\\subsection{Proposal}\nThe method.\n",
            "back-matter.bm-funding": b"\\section*{Funding}\nNo funding.\n",
            "conclusions.concl-block-1": b"Closing.",
        }
        for block_id, body in bodies.items():
            paper_block.substitute(self.paper_dir, block_id, new_body=body)

    def test_frame_keeps_every_block_body_and_digest(self) -> None:
        self.skeleton()
        self._write_bodies()
        paper_declarations.set_declaration(self.paper_dir, "repository-url", "https://example.org/code")
        before = self.tex.read_bytes()
        region_before = paper_frame._region_bytes(before)

        result = paper_cli.build_skeleton(self.paper_dir, SECTIONS, related_work=None, dataset_in=None,
                                          frame=True)

        after = self.tex.read_bytes()
        self.assertTrue(result["frame"]["framed"])
        self.assertEqual(result["opened"], [])
        self.assertEqual(_digests(after), _digests(before))
        self.assertEqual(_regions(after), _regions(before))
        self.assertEqual(paper_frame._region_bytes(after), region_before)
        self.assertIn(b"\\begin{document}\n", after)
        # the one-deep pre-image holds the frameless file
        self.assertEqual((self.paper_dir / ".paper-writing" / "main.tex.prev").read_bytes(), before)
        # the declarations region still reads back
        self.assertEqual(paper_declarations.read_declaration(self.paper_dir, "repository-url"),
                         "https://example.org/code")

    def test_a_second_frame_is_a_no_op(self) -> None:
        self.skeleton(frame=True)
        before = self.tex.read_bytes()
        result = self.skeleton(frame=True)
        self.assertFalse(result["frame"]["framed"])
        self.assertEqual(result["frame"]["frame"], "present")
        self.assertEqual(self.tex.read_bytes(), before)

    def test_a_body_block_carrying_a_heading_refuses_and_names_it(self) -> None:
        self.skeleton()
        paper_block.substitute(self.paper_dir, "introduction.block-1",
                               new_body=b"\\section{Introduction}\nOpening paragraph.\n")
        paper_block.substitute(self.paper_dir, "conclusions.concl-block-1",
                               new_body=b"\\section*{Conclusions}\nClosing.\n")
        before = self.tex.read_bytes()

        with self.assertRaises(Refused) as caught:
            self.skeleton(frame=True)

        self.assertEqual(caught.exception.code, "FRAME_BLOCK_CARRIES_HEADING")
        self.assertIn("introduction.block-1", caught.exception.detail)
        self.assertIn("conclusions.concl-block-1", caught.exception.detail)
        self.assertEqual(self.tex.read_bytes(), before)

    def test_text_outside_the_blocks_without_a_frame_refuses(self) -> None:
        self.skeleton()
        self.tex.write_bytes(b"\\documentclass{article}\n" + self.tex.read_bytes())
        before = self.tex.read_bytes()

        with self.assertRaises(Refused) as caught:
            self.skeleton(frame=True)

        self.assertEqual(caught.exception.code, "FRAME_OUTSIDE_TEXT")
        self.assertIn("line 1", caught.exception.detail)
        self.assertEqual(self.tex.read_bytes(), before)

    def test_a_block_the_contracts_do_not_declare_refuses(self) -> None:
        self.skeleton()
        paper_block.open_block(self.paper_dir, "introduction.block-99", at_end=True)
        before = self.tex.read_bytes()

        with self.assertRaises(Refused) as caught:
            self.skeleton(frame=True)

        self.assertEqual(caught.exception.code, "FRAME_BLOCK_UNDECLARED")
        self.assertIn("introduction.block-99", caught.exception.detail)
        self.assertEqual(self.tex.read_bytes(), before)

    def test_a_fresh_paper_without_answers_still_refuses(self) -> None:
        """`--frame` never stands in for the two answers on a paper with no block."""
        with self.assertRaises(Refused) as caught:
            paper_cli.build_skeleton(self.paper_dir, SECTIONS, related_work=None, dataset_in=None, frame=True)
        self.assertEqual(caught.exception.code, "SKELETON_ANSWER_REQUIRED")
        self.assertEqual(self.tex.read_bytes(), b"")


class SectionTitleTests(unittest.TestCase):
    def test_title_is_the_contract_heading_without_the_line_suffix(self) -> None:
        self.assertEqual(paper_frame.section_title("# Methods (review line)\n\nProse.\n", "methods"), "Methods")
        self.assertEqual(paper_frame.section_title("Prose.\n\n# Experimental Set-Up\n", "x"), "Experimental Set-Up")

    def test_a_contract_without_a_heading_falls_back_to_its_id(self) -> None:
        self.assertEqual(paper_frame.section_title("No heading.\n", "related-work"), "Related Work")

    def test_every_shipped_line_derives_its_titles(self) -> None:
        for directory in sorted(REPO.glob("sections*")):
            with self.subTest(line=directory.name):
                layout = paper_frame.read_layout(directory)
                self.assertTrue(layout)
                for section in layout:
                    self.assertNotIn("line)", section["title"])


class WriteHeadingGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.paper_dir = Path(self._tmp.name) / "paper"

    def _contract(self, block_id: str):
        tpw._write_fixture(self.paper_dir, tpw._marker_pair(block_id, b"Old body.\n"))
        return tpw._write_contract(block_id=block_id, citations_regime="none", evidence_set=())

    @staticmethod
    def _draft(latex: str) -> dict:
        return {"latex": latex, "bindings": [{"sentence": latex, "binding": "structural"}]}

    def test_a_body_draft_carrying_a_section_heading_refuses_and_keeps_main_tex(self) -> None:
        for heading in ("\\section{Methods}", "\\section*{Methods}", "  \\section[Short]{Methods}"):
            with self.subTest(heading=heading):
                contract = self._contract("materials-and-methods.mm-proposal")
                before = (self.paper_dir / "main.tex").read_bytes()
                with self.assertRaises(Refused) as caught:
                    paper_write.write_block(self.paper_dir, contract,
                                            self._draft(heading + "\nThis paragraph closes the section."),
                                            tpw._CLEAN_AUDIT)
                self.assertEqual(caught.exception.code, "DRAFT_SECTION_HEADING")
                self.assertIn("line 1", caught.exception.detail)
                self.assertEqual((self.paper_dir / "main.tex").read_bytes(), before)
                self.assertFalse(paper_write._ledger_path(self.paper_dir, contract.block_id).exists())

    def test_a_declaration_keeps_its_own_section_star(self) -> None:
        contract = self._contract("back-matter.bm-funding")
        result = paper_write.write_block(
            self.paper_dir, contract,
            self._draft("\\section*{Funding}\nThis paragraph closes the section."), tpw._CLEAN_AUDIT)
        self.assertEqual(result["status"], "written")

    def test_subsections_and_commented_headings_stay_free(self) -> None:
        """The previous behavior of `write` holds for every draft without a heading."""
        for latex in ("\\subsection{Proposal}\nThis paragraph closes the section.",
                      "% \\section{Old}\nThis paragraph closes the section.",
                      "This paragraph closes the section."):
            with self.subTest(latex=latex):
                contract = self._contract("materials-and-methods.mm-proposal")
                result = paper_write.write_block(self.paper_dir, contract, self._draft(latex), tpw._CLEAN_AUDIT)
                self.assertEqual(result["status"], "written")


class FrontDoorTests(unittest.TestCase):
    def test_new_codes_are_classified_work_state(self) -> None:
        for code in ("DRAFT_SECTION_HEADING", "FRAME_BLOCK_CARRIES_HEADING", "FRAME_OUTSIDE_TEXT",
                     "FRAME_BLOCK_UNDECLARED"):
            with self.subTest(code=code):
                self.assertEqual(paper_cli.REFUSAL_CLASSIFICATION[code], paper_cli.WORK_STATE)

    def test_skeleton_accepts_the_frame_flag(self) -> None:
        parser = paper_cli.build_parser()
        self.assertTrue(parser.parse_args(["skeleton", "--frame"]).frame)
        self.assertFalse(parser.parse_args(["skeleton"]).frame)
        help_text = parser._subparsers._group_actions[0].choices["skeleton"].format_help()
        self.assertIn("--frame", help_text)

    def test_the_preamble_is_the_canonical_review_layout(self) -> None:
        self.assertTrue(paper_frame.PREAMBLE.startswith("\\documentclass[11pt,onecolumn,a4paper]{article}\n"))
        self.assertIn("\\usepackage[english]{babel}", paper_frame.PREAMBLE)


if __name__ == "__main__":
    unittest.main()
