"""The manuscript is English and carries no placeholder text (spec S4 of
`odd/tasks/manuscript-polish-0-54.md`).

One detector (`paper_language.py`) serves four places: the title contract's
author placeholder, the write gate, `verify`'s `language` check and the
manuscript QA report. A paper that declares another main language
(babel/polyglossia) is exempt from the Spanish check, never from the
placeholder check.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tests"))
import test_paper_writing as tpw  # noqa: E402 -- shared fixtures; its own tests run in that module

import paper_cli  # noqa: E402
import paper_coupling_evidence  # noqa: E402
import paper_language  # noqa: E402
import paper_verify  # noqa: E402
import paper_write  # noqa: E402
from impl_refusals import Refused  # noqa: E402

sys.path.insert(0, str(REPO / "skills" / "_core" / "figure"))

ENGLISH_PLACEHOLDER = r"\author{Author names withheld \\ \textit{Affiliations and contact e-mails to be provided}}"
BLINDING_SURFACES = (
    "sections/09-title-and-keywords.md",
    "skills/paper-writing/SKILL.md",
    ".claude/agents/redactor.md",
    ".agents/agents/redactor.md",
    ".opencode/agents/redactor.md",
    ".pi/agents/redactor.md",
)
REVIEWER_SURFACES = tuple(f"{tool}/agents/paper-reviewer.md"
                          for tool in (".claude", ".agents", ".opencode", ".pi"))

SPANISH_LINE = "Esta sección presenta el método y los resultados más relevantes."
ENGLISH_WITH_NAMES = (
    "\\documentclass{article}\n"
    "\\title{Kernel Methods for EEG Decoding}\n"
    "\\author{Andrés Marino Álvarez Meza \\\\ \\textit{Departamento de Ingeniería Eléctrica, "
    "Electrónica y Computación, Universidad Nacional de Colombia}}\n"
    "\\begin{document}\n"
    "\\maketitle\n"
    "%% paper-writing:begin intro.p1 este comentario está en español\n"
    "As shown by Álvarez-Meza et al.~\\cite{alvarez2024} and Cárdenas-Peña~\\cite{cardenas2023},\n"
    "the kernel $\\kappa(x, y) = \\exp(-\\|x - y\\|^2)$ preserves the signal.\n"
    "\\begin{equation} f(x) = \\sum_{i} \\alpha_i \\end{equation}\n"
    "\\begin{thebibliography}{9}\n"
    "\\bibitem{x} J. Pérez, Análisis de señales para la clasificación, Revista de Ingeniería, 2020.\n"
    "\\end{thebibliography}\n"
    "\\end{document}\n"
)


class BlindingPlaceholderIsEnglishTests(unittest.TestCase):
    def test_the_title_contract_and_its_readers_prescribe_an_english_placeholder(self) -> None:
        for rel in BLINDING_SURFACES:
            with self.subTest(rel=rel):
                text = (REPO / rel).read_text(encoding="utf-8")
                self.assertIn(ENGLISH_PLACEHOLDER, text)
                self.assertNotIn("por definir", text.lower())
                self.assertNotIn("Afiliaciones", text)
        for rel in REVIEWER_SURFACES:
            with self.subTest(rel=rel):
                text = (REPO / rel).read_text(encoding="utf-8")
                self.assertIn('"Author names withheld"', text)
                self.assertNotIn("por definir", text.lower())

    def test_the_english_placeholder_passes_the_scan(self) -> None:
        report = paper_language.scan("\\begin{document}\n" + ENGLISH_PLACEHOLDER + "\n\\end{document}\n")
        self.assertTrue(report["clean"], report)

    def test_the_old_spanish_placeholder_is_flagged(self) -> None:
        old = r"\author{Por definir \\ \textit{Afiliaciones y correos por definir}}"
        report = paper_language.scan("\\documentclass{article}\n" + old + "\n\\begin{document}\n\\end{document}\n")
        self.assertEqual([hit["marker"] for hit in report["placeholders"]], ["por definir"])
        self.assertEqual(report["placeholders"][0]["line"], 2)


class ManuscriptScanTests(unittest.TestCase):
    def test_spanish_prose_is_reported_with_its_line(self) -> None:
        tex = "\\begin{document}\nThe method is described below.\n" + SPANISH_LINE + "\n\\end{document}\n"
        report = paper_language.scan(tex)
        self.assertEqual([hit["line"] for hit in report["spanish"]], [3])
        self.assertFalse(report["clean"])

    def test_english_with_accented_names_citations_math_and_bibliography_is_clean(self) -> None:
        report = paper_language.scan(ENGLISH_WITH_NAMES)
        self.assertEqual(report["spanish"], [])
        self.assertEqual(report["placeholders"], [])
        self.assertTrue(report["clean"])

    def test_placeholder_markers_are_reported(self) -> None:
        tex = ("\\begin{document}\nTODO: add the ablation.\nThe gain is TBD.\n"
               "\\todo{check this}\nFIXME later.\n\\end{document}\n")
        markers = [hit["marker"] for hit in paper_language.scan(tex)["placeholders"]]
        self.assertEqual(markers, ["TODO", "TBD", "TODO", "FIXME"])

    def test_a_comment_or_marker_never_counts(self) -> None:
        tex = "\\begin{document}\n% TODO " + SPANISH_LINE + "\nEnglish prose only.\n\\end{document}\n"
        self.assertTrue(paper_language.scan(tex)["clean"])

    def test_a_declared_non_english_paper_is_exempt_from_the_spanish_check_only(self) -> None:
        for preamble in ("\\usepackage[english,spanish]{babel}\n",
                         "\\usepackage[main=spanish,english]{babel}\n",
                         "\\usepackage{polyglossia}\n\\setmainlanguage{spanish}\n"):
            with self.subTest(preamble=preamble):
                tex = ("\\documentclass{article}\n" + preamble + "\\begin{document}\n"
                       + SPANISH_LINE + "\nPendiente por definir.\n\\end{document}\n")
                report = paper_language.scan(tex)
                self.assertEqual(report["language"], "spanish")
                self.assertEqual(report["spanish"], [])
                self.assertEqual(len(report["placeholders"]), 1)

    def test_babel_with_english_as_main_language_is_still_checked(self) -> None:
        tex = ("\\documentclass{article}\n\\usepackage[spanish,english]{babel}\n\\begin{document}\n"
               + SPANISH_LINE + "\n\\end{document}\n")
        self.assertEqual(len(paper_language.scan(tex)["spanish"]), 1)


class WriteGateLanguageTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.paper_dir = Path(self._tmp.name) / "paper"
        tpw._write_fixture(self.paper_dir, tpw._marker_pair("mm-proposal", b"Old body.\n"))
        self.contract = tpw._write_contract(citations_regime="none", evidence_set=())

    def _draft(self, latex: str) -> dict:
        return {"latex": latex, "bindings": [{"sentence": latex, "binding": "structural"}]}

    def test_a_spanish_draft_is_refused_and_main_tex_is_untouched(self) -> None:
        before = (self.paper_dir / "main.tex").read_bytes()
        with self.assertRaises(Refused) as caught:
            paper_write.write_block(self.paper_dir, self.contract, self._draft(SPANISH_LINE), tpw._CLEAN_AUDIT)
        self.assertEqual(caught.exception.code, "DRAFT_NOT_ENGLISH")
        self.assertEqual((self.paper_dir / "main.tex").read_bytes(), before)
        self.assertFalse(paper_write._ledger_path(self.paper_dir, self.contract.block_id).exists())

    def test_a_draft_with_placeholder_text_is_refused(self) -> None:
        with self.assertRaises(Refused) as caught:
            paper_write.write_block(self.paper_dir, self.contract,
                                    self._draft("The gain is TODO."), tpw._CLEAN_AUDIT)
        self.assertEqual(caught.exception.code, "DRAFT_PLACEHOLDER_TEXT")

    def test_an_english_draft_citing_accented_authors_is_written(self) -> None:
        latex = "As Álvarez-Meza et al. showed, this paragraph closes the section."
        result = paper_write.write_block(self.paper_dir, self.contract, self._draft(latex), tpw._CLEAN_AUDIT)
        self.assertEqual(result["status"], "written")
        self.assertEqual(result["language"], {"status": "pass", "language": "english"})

    def test_the_existing_clean_draft_is_written_unchanged(self) -> None:
        result = paper_write.write_block(self.paper_dir, self.contract, tpw._CLEAN_DRAFT, tpw._CLEAN_AUDIT)
        self.assertEqual(result["status"], "written")
        self.assertIn(b"This paragraph closes the section.", (self.paper_dir / "main.tex").read_bytes())

    def test_a_paper_declaring_spanish_accepts_a_spanish_draft(self) -> None:
        main_tex = self.paper_dir / "main.tex"
        main_tex.write_bytes(b"\\usepackage[spanish]{babel}\n" + main_tex.read_bytes())
        result = paper_write.write_block(self.paper_dir, self.contract, self._draft(SPANISH_LINE), tpw._CLEAN_AUDIT)
        self.assertEqual(result["status"], "written")
        self.assertEqual(result["language"]["language"], "spanish")

    def test_the_refusals_are_classified(self) -> None:
        for code in ("DRAFT_NOT_ENGLISH", "DRAFT_PLACEHOLDER_TEXT"):
            with self.subTest(code=code):
                self.assertEqual(paper_cli.REFUSAL_CLASSIFICATION[code], paper_cli.WORK_STATE)


class VerifyLanguageCheckTests(unittest.TestCase):
    """`cmd_verify` resolves `--paper` against the repository root, so the
    fixture lives under the gitignored `.scratch/` tree, as
    `OptionalVerifyWiringTests` does."""

    def setUp(self) -> None:
        test_root = tpw.FORGE_ROOT / ".scratch" / f".paper-language-verify-{os.getpid()}-{id(self)}"
        self.addCleanup(shutil.rmtree, test_root, ignore_errors=True)
        self.paper_dir = test_root / "paper"
        self.sections_dir = test_root / "sections"

    def _verify(self, bodies: dict | None = None) -> dict:
        tpw._build_coupling_paper(self.paper_dir, self.sections_dir, bodies=bodies)
        args = argparse.Namespace(paper=str(self.paper_dir), sections=str(self.sections_dir))
        report = paper_cli.cmd_verify(args)
        return {entry["check"]: entry for entry in report["checks"]}

    def test_an_english_paper_passes_and_every_other_check_is_unchanged(self) -> None:
        by_check = self._verify()
        self.assertEqual(by_check["language"]["verdict"], "pass")
        evidence = paper_coupling_evidence.gather(self.paper_dir, self.sections_dir)
        without = {entry["check"]: entry for entry in paper_verify.run(evidence)["checks"]}
        for check in paper_verify.CHECKS:
            if check != "language":
                with self.subTest(check=check):
                    self.assertEqual(by_check[check]["verdict"], without[check]["verdict"])

    def test_a_spanish_block_fails_with_its_line(self) -> None:
        bodies = dict(tpw._COUPLING_BODIES)
        first = next(iter(bodies))
        bodies[first] = bodies[first] + SPANISH_LINE.encode("utf-8") + b"\n"
        entry = self._verify(bodies)["language"]
        self.assertEqual(entry["verdict"], "fail")
        self.assertEqual([hit["text"] for hit in entry["evidence"]["spanish"]], [SPANISH_LINE])
        self.assertIsInstance(entry["evidence"]["spanish"][0]["line"], int)

    def test_run_without_a_scan_reports_unmeasured(self) -> None:
        tpw._build_coupling_paper(self.paper_dir, self.sections_dir)
        evidence = paper_coupling_evidence.gather(self.paper_dir, self.sections_dir)
        entry = {e["check"]: e for e in paper_verify.run(evidence)["checks"]}["language"]
        self.assertEqual(entry["verdict"], "unmeasured")
        self.assertEqual(entry["unmeasured_reason"], "LANGUAGE_NOT_SCANNED")


class ManuscriptQaLanguageTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            import manuscript_qa  # noqa: PLC0415
        except ImportError as exc:  # pypdfium2 is a declared dependency; skip only if absent
            self.skipTest(f"manuscript_qa unavailable: {exc}")
        self.qa = manuscript_qa

    def test_spanish_and_placeholders_become_findings_located_on_their_page(self) -> None:
        tex = "\\begin{document}\nEnglish opening line.\n" + SPANISH_LINE + "\nThe gain is TBD.\n\\end{document}\n"
        pages = ["English opening line.", SPANISH_LINE + " The gain is TBD."]
        findings = self.qa.language_findings(tex, pages)
        self.assertEqual([(f["kind"], f["line"], f["page"]) for f in findings],
                         [("language", 3, 2), ("placeholder", 4, 2)])

    def test_an_english_manuscript_with_accented_names_has_no_language_findings(self) -> None:
        self.assertEqual(self.qa.language_findings(ENGLISH_WITH_NAMES, []), [])


if __name__ == "__main__":
    unittest.main()
