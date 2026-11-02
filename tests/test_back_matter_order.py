"""Back matter renders after the conclusions and before the references;
appendices follow the references (`odd/tasks/manuscript-polish-0-54.md`, S3:
the declarations, written after the references, must come before them).

The rule is checked deterministically over the canonical `paper/main.tex`
by `paper_verify.check_back_matter_order`, reported by `verify` under its
own `structure` key so the closed `CHECKS` roster of couplings is unchanged.
"""
from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path

FORGE_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = FORGE_ROOT / "skills" / "paper-writing" / "scripts"
CONTRACT = FORGE_ROOT / "sections" / "10-back-matter.md"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(FORGE_ROOT / "skills" / "_core" / "implementation"))
import paper_coupling_evidence  # noqa: E402
import paper_venue  # noqa: E402
import paper_verify  # noqa: E402


def block(block_id: str, body: str) -> str:
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    return (f"%% paper-writing block {block_id} begin sha256={digest}\n{body}"
            f"%% paper-writing block {block_id} end\n")


BIBLIOGRAPHY = "\\bibliographystyle{ieeetr}\n\\bibliography{refs}\n"
DECLARATIONS = (
    "\\section*{Declarations}\n"
    + block("back-matter.bm-author-contributions", "\\textbf{Author Contributions:} A.L.\n")
    + block("back-matter.bm-funding", "\\textbf{Funding:} None.\n")
    + block("back-matter.bm-ai-use-declaration", "\\section*{Declaration of AI use}\nTools.\n")
)
APPENDIX = block("back-matter.bm-appendices", "\\appendix\n\\section{Parameters}\nTable.\n")


def manuscript(*parts: str) -> bytes:
    head = ("\\documentclass{article}\n\\begin{document}\n\\section{Conclusions}\n"
            + block("conclusions.concl-block-1", "We conclude.\n"))
    return (head + "".join(parts) + "\\end{document}\n").encode("utf-8")


def evidence(tex: bytes) -> paper_coupling_evidence.Evidence:
    return paper_coupling_evidence.Evidence(
        paper_dir=Path("paper"), sections_dir=Path("sections"),
        main_tex_bytes=tex, refs_bib_bytes=b"",
    )


class BackMatterOrderCheckTests(unittest.TestCase):
    def check(self, tex: bytes) -> dict:
        return paper_verify.check_back_matter_order(evidence(tex))

    def test_declarations_after_the_bibliography_fail(self) -> None:
        entry = self.check(manuscript(BIBLIOGRAPHY, DECLARATIONS))
        self.assertEqual(entry["check"], "back-matter-order")
        self.assertEqual(entry["verdict"], "fail")
        self.assertEqual(entry["evidence"]["declarations_after_references"], [
            "back-matter.bm-author-contributions", "back-matter.bm-funding",
            "back-matter.bm-ai-use-declaration",
        ])
        self.assertEqual(entry["evidence"]["appendices_before_references"], [])

    def test_one_declaration_left_after_the_bibliography_still_fails(self) -> None:
        # the QMLEEG shape: the AI declaration before the references, the rest after
        ai = block("back-matter.bm-ai-use-declaration", "\\section*{Declaration of AI use}\nTools.\n")
        rest = ("\\section*{Declarations}\n"
                + block("back-matter.bm-author-contributions", "\\textbf{Author Contributions:} A.L.\n"))
        entry = self.check(manuscript(ai, BIBLIOGRAPHY, rest))
        self.assertEqual(entry["verdict"], "fail")
        self.assertEqual(entry["evidence"]["declarations_after_references"],
                         ["back-matter.bm-author-contributions"])

    def test_declarations_before_the_bibliography_and_appendices_after_pass(self) -> None:
        entry = self.check(manuscript(DECLARATIONS, BIBLIOGRAPHY, APPENDIX))
        self.assertEqual(entry["verdict"], "pass")
        self.assertIsNone(entry["unmeasured_reason"])
        self.assertEqual(entry["evidence"]["declarations_after_references"], [])

    def test_an_appendix_before_the_bibliography_fails(self) -> None:
        entry = self.check(manuscript(DECLARATIONS, APPENDIX, BIBLIOGRAPHY))
        self.assertEqual(entry["verdict"], "fail")
        self.assertEqual(entry["evidence"]["appendices_before_references"], ["back-matter.bm-appendices"])

    def test_thebibliography_and_printbibliography_count_as_the_references(self) -> None:
        for references in ("\\begin{thebibliography}{9}\n\\bibitem{a} A.\n\\end{thebibliography}\n",
                           "\\printbibliography\n"):
            with self.subTest(references=references.split("\n")[0]):
                self.assertEqual(self.check(manuscript(references, DECLARATIONS))["verdict"], "fail")
                self.assertEqual(self.check(manuscript(DECLARATIONS, references))["verdict"], "pass")

    def test_a_commented_out_bibliography_is_not_the_references(self) -> None:
        entry = self.check(manuscript("% \\bibliography{old}\n", DECLARATIONS, BIBLIOGRAPHY))
        self.assertEqual(entry["verdict"], "pass")

    def test_no_bibliography_is_unmeasured_never_pass(self) -> None:
        entry = self.check(manuscript(DECLARATIONS))
        self.assertEqual(entry["verdict"], "unmeasured")
        self.assertEqual(entry["unmeasured_reason"], "NO_BIBLIOGRAPHY")
        self.assertIn("NO_BIBLIOGRAPHY", paper_verify.UNMEASURED_REASONS)


class VerifyReportTests(unittest.TestCase):
    def test_run_reports_the_order_under_structure_and_keeps_the_couplings_roster(self) -> None:
        report = paper_verify.run(evidence(manuscript(BIBLIOGRAPHY, DECLARATIONS)))
        # the coupling roster and its arithmetic are unchanged
        self.assertEqual([entry["check"] for entry in report["checks"]], list(paper_verify.CHECKS))
        self.assertNotIn("back-matter-order", paper_verify.CHECKS)
        self.assertEqual(report["holds"] + report["fails"] + report["unmeasured"], len(paper_verify.CHECKS))
        [entry] = report["structure"]
        self.assertEqual(entry["check"], "back-matter-order")
        self.assertEqual(entry["verdict"], "fail")
        self.assertFalse(report["clean"])

    def test_a_correct_order_adds_no_failure(self) -> None:
        report = paper_verify.run(evidence(manuscript(DECLARATIONS, BIBLIOGRAPHY, APPENDIX)))
        self.assertEqual([entry["verdict"] for entry in report["structure"]], ["pass"])


class RuleTextTests(unittest.TestCase):
    def test_the_contract_states_the_order_and_the_appendix_rule(self) -> None:
        text = CONTRACT.read_text(encoding="utf-8")
        self.assertIn("The administrative block that sits after the conclusions and before the references.", text)
        self.assertIn("**Back matter renders after the conclusions and before the references, for every venue", text)
        self.assertIn("**Appendices follow the references**", text)
        self.assertNotIn("back matter renders last", text)

    def test_every_publisher_family_places_declarations_before_and_appendices_after(self) -> None:
        for family, placement in paper_venue.BACK_MATTER_PLACEMENT.items():
            with self.subTest(family=family):
                self.assertEqual(placement["declarations"], "before-references")
                self.assertEqual(placement["appendices"], "after-references")


if __name__ == "__main__":
    unittest.main()
