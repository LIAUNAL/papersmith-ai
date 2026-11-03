"""No paragraph or contribution item opens in bold in the introduction or
the experimental set-up.

Drafts copied the contracts' block names into the manuscript as run-in labels
(`\\textbf{Scenarios.}`, `\\textbf{Partition.}`, `\\item \\textbf{Name:}`), which
reads as a generated outline instead of prose. The two contracts now ask for
paragraphs that open on a sentence carrying the transition from the previous
one, and `write` refuses a draft of those sections that still opens a paragraph
or an item with emphasis -- before any attempt is spent, leaving `main.tex`
untouched. Table cells and in-sentence emphasis stay free.
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

import paper_cli  # noqa: E402
import paper_language  # noqa: E402
import paper_write  # noqa: E402
from impl_refusals import Refused  # noqa: E402

LEAD_INS = {
    "bold paragraph label": "\\textbf{Scenarios.} Two scenarios were evaluated.",
    "noindent bold label": "\\noindent\\textbf{Partition.} The children were split by subject.",
    "bf group": "{\\bf Competing methods.} Two networks were compared.",
    "run-in paragraph heading": "\\paragraph{Metrics} The task is scored per subject.",
    "bold item": "\\begin{itemize}\n\\item \\textbf{Circular re-uploading:} re-uploads the features.\n\\end{itemize}",
    "description label": "\\begin{description}\n\\item[Circular re-uploading:] re-uploads the features.\n\\end{description}",
}
FREE = {
    "plain item": "\\begin{itemize}\n\\item Circular re-uploading: re-uploads the features in every layer.\n\\end{itemize}",
    "emphasis inside a sentence": "The split keeps \\textbf{subjects} apart across folds.",
    "table header and cell": ("\\begin{tabular}{ll}\n\\textbf{Arm} & \\textbf{Readout} \\\\\n"
                              "Hybrid & \\textbf{0.925} \\\\\n\\end{tabular}"),
    "flowing paragraph": "With the scenarios fixed, the partition keeps every child in a single fold.",
}


#: The shared fixture's sentence passes every other gate, so these drafts
#: measure the lead-in rule alone.
CLEAN = "This paragraph closes the section."
LABELLED_CLEAN = "\\textbf{Scenarios.} " + CLEAN


class DetectorTests(unittest.TestCase):
    def test_every_lead_in_form_is_found(self) -> None:
        for name, latex in LEAD_INS.items():
            with self.subTest(form=name):
                self.assertEqual(len(paper_language.bold_lead_ins(latex)), 1, latex)

    def test_tables_and_in_sentence_emphasis_are_free(self) -> None:
        for name, latex in FREE.items():
            with self.subTest(form=name):
                self.assertEqual(paper_language.bold_lead_ins(latex), [], latex)

    def test_a_hit_names_its_line(self) -> None:
        hits = paper_language.bold_lead_ins("First paragraph.\n\n\\textbf{Partition.} Second one.")
        self.assertEqual(hits[0]["line"], 3)
        self.assertIn("Partition", hits[0]["text"])


class WriteGateTests(unittest.TestCase):
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

    def test_both_sections_refuse_a_bold_lead_in_and_keep_main_tex(self) -> None:
        for block_id in ("introduction.block-4b", "experimental-setup.es-assessment"):
            with self.subTest(block=block_id):
                contract = self._contract(block_id)
                before = (self.paper_dir / "main.tex").read_bytes()
                with self.assertRaises(Refused) as caught:
                    paper_write.write_block(self.paper_dir, contract,
                                            self._draft(LABELLED_CLEAN), tpw._CLEAN_AUDIT)
                self.assertEqual(caught.exception.code, "DRAFT_BOLD_LEAD_IN")
                self.assertIn("Scenarios", caught.exception.detail)
                self.assertEqual((self.paper_dir / "main.tex").read_bytes(), before)
                self.assertFalse(paper_write._ledger_path(self.paper_dir, contract.block_id).exists())

    def test_a_flowing_draft_of_those_sections_is_written(self) -> None:
        contract = self._contract("experimental-setup.es-assessment")
        result = paper_write.write_block(self.paper_dir, contract,
                                         self._draft(CLEAN), tpw._CLEAN_AUDIT)
        self.assertEqual(result["status"], "written")

    def test_other_sections_keep_their_previous_behavior(self) -> None:
        contract = self._contract("results-and-discussion.rd-findings")
        result = paper_write.write_block(self.paper_dir, contract,
                                         self._draft(LABELLED_CLEAN), tpw._CLEAN_AUDIT)
        self.assertEqual(result["status"], "written")

    def test_the_refusal_is_classified(self) -> None:
        self.assertEqual(paper_cli.REFUSAL_CLASSIFICATION["DRAFT_BOLD_LEAD_IN"], paper_cli.WORK_STATE)


class ContractTests(unittest.TestCase):
    def body(self, name: str) -> str:
        return " ".join((REPO / "sections" / name).read_text(encoding="utf-8").split())

    def test_the_introduction_list_opens_items_on_the_plain_name(self) -> None:
        body = self.body("06-introduction.md")
        self.assertIn("in plain text, never in bold", body)
        self.assertIn("DRAFT_BOLD_LEAD_IN", body)

    def test_the_set_up_opens_paragraphs_on_a_transition(self) -> None:
        body = self.body("02-experimental-setup.md")
        self.assertIn("never as a bold label", body)
        self.assertIn("DRAFT_BOLD_LEAD_IN", body)


if __name__ == "__main__":
    unittest.main()
