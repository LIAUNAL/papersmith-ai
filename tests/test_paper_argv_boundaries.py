"""#81: citation validation covers its declared TeX command vocabulary, and a
figure identifier never reaches `latexmk` where it could act as an option.

Two independent boundaries of the `argv-boundaries` root:

* `paper_bib.check_reciprocal` reads cited keys with `CITE_COMMANDS`, the
  declared vocabulary. Before this test a `\\citep{...}` or `\\citet{...}`
  key with no `refs.bib` entry passed the reciprocal check silently.
* `paper_figure.figure_paths` (every `--figure-id` caller) and
  `paper_latex.compile` (the one subprocess call, also reached by
  `figure optimize --file`, whose id is the file stem) refuse an id that
  begins with `-`. Rejection is the supported policy: `latexmk` would
  otherwise read `-<id>.tex` as an option. Argv is captured through an inert
  stub `latexmk`; no real compiler option is ever executed.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

FORGE_ROOT = Path(__file__).resolve().parents[1]
SKILL_SCRIPTS = FORGE_ROOT / "skills" / "paper-writing" / "scripts"
sys.path.insert(0, str(SKILL_SCRIPTS))
import paper_bib  # noqa: E402
import paper_figure  # noqa: E402
import paper_latex  # noqa: E402

sys.path.insert(0, str(FORGE_ROOT / "skills" / "_core" / "implementation"))
from impl_refusals import Refused  # noqa: E402

#: Records its argv and writes the log/pdf a successful compile leaves behind.
_STUB_LATEXMK = '''#!/usr/bin/env python3
import json, os, sys
record = os.environ["STUB_RECORD_PATH"]
with open(record, "a", encoding="utf-8") as handle:
    handle.write(json.dumps({"argv": sys.argv}) + "\\n")
outdir = next(a[len("-outdir="):] for a in sys.argv if a.startswith("-outdir="))
stem = sys.argv[-1][:-4]
os.makedirs(outdir, exist_ok=True)
with open(os.path.join(outdir, stem + ".log"), "w", encoding="utf-8") as handle:
    handle.write("This is pdfTeX, Version stub\\n")
with open(os.path.join(outdir, stem + ".pdf"), "wb") as handle:
    handle.write(b"%PDF-1.4 stub\\n")
'''


class CitationVocabularyTests(unittest.TestCase):
    def test_citation_validation_rejects_missing_keys_in_citep_and_citet(self) -> None:
        for command in ("cite", "citep", "citet"):
            with self.subTest(command=command):
                main_tex = f"text \\{command}{{missing-{command}}} more".encode()
                with self.assertRaises(Refused) as ctx:
                    paper_bib.check_reciprocal(main_tex, b"")
                self.assertEqual(ctx.exception.code, "CITE_WITHOUT_ENTRY")
                self.assertIn(f"missing-{command}", ctx.exception.detail)

    def test_citation_inventory_matches_declared_command_vocabulary(self) -> None:
        self.assertEqual(
            paper_bib.CITE_COMMANDS,
            ("cite", "citep", "citet", "citealp", "citealt", "citeauthor", "citeyear"),
        )
        main_tex = (
            rb"\cite{a} \citep{b, c} \citet[p.~4]{d} \citep[see][ch.~2]{e}"
            rb" \citet*{f} \citealp{g} \citealt{h} \citeauthor{i} \citeyear{j}"
        )
        self.assertEqual(
            paper_bib.cited_keys(main_tex), {"a", "b", "c", "d", "e", "f", "g", "h", "i", "j"}
        )
        # Declared unsupported: `\nocite` lists entries without citing them,
        # and an unknown `\cite...` macro is not read as a citation.
        self.assertEqual(paper_bib.cited_keys(rb"\nocite{k} \citexyz{l}"), set())

    def test_a_fully_reciprocal_bibliography_still_passes(self) -> None:
        main_tex = rb"\cite{a-key} and \citep{b-key}"
        refs_bib = b"@misc{a-key,\n}\n@misc{b-key,\n}\n"
        report = paper_bib.check_reciprocal(main_tex, refs_bib)
        self.assertEqual(report["cited"], ["a-key", "b-key"])


class VerifyCitationVocabularyTests(unittest.TestCase):
    """`paper_verify.check_citations` reads the same vocabulary as `paper_bib`."""

    def _check(self, tex: bytes, bib: bytes) -> dict:
        import types

        import paper_verify

        evidence = types.SimpleNamespace(main_tex_bytes=tex, refs_bib_bytes=bib)
        return paper_verify.check_citations(evidence)

    def test_a_dangling_citep_or_citet_key_fails_the_check(self) -> None:
        tex = b"\\citep[see][ch.~2]{ghost} and \\citet*{known}"
        result = self._check(tex, b"@article{known,\n}")
        self.assertEqual(result["verdict"], "fail")
        self.assertEqual(result["evidence"]["dangling"], ["ghost"])

    def test_a_plain_cite_with_its_entry_still_passes(self) -> None:
        result = self._check(b"\\cite{known}", b"@article{known,\n}")
        self.assertEqual(result["verdict"], "pass")

    def test_verify_and_bib_declare_the_same_vocabulary(self) -> None:
        import paper_verify

        self.assertEqual(paper_verify.CITE_COMMANDS, paper_bib.CITE_COMMANDS)


class FigureIdOptionTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.bin_dir = self.root / "bin"
        self.bin_dir.mkdir()
        stub = self.bin_dir / "latexmk"
        stub.write_text(_STUB_LATEXMK, encoding="utf-8")
        stub.chmod(0o755)
        self.record = self.root / "record.jsonl"
        os.environ["STUB_RECORD_PATH"] = str(self.record)
        self.addCleanup(os.environ.pop, "STUB_RECORD_PATH", None)
        self.paper = self.root / "paper"
        (self.paper / "Figures").mkdir(parents=True)

    def _write_figure(self, figure_id: str) -> None:
        figures = self.paper / "Figures"
        (figures / f"{figure_id}.tex").write_text("% node: a\n", encoding="utf-8")
        (figures / f"{figure_id}.diagram.json").write_text(
            json.dumps({"components": ["a"]}), encoding="utf-8"
        )

    def test_figure_id_cannot_be_interpreted_as_latexmk_option(self) -> None:
        figure_id = "-norc"
        self._write_figure(figure_id)
        with self.assertRaises(Refused) as ctx:
            paper_figure.render(self.paper, figure_id, path=str(self.bin_dir))
        self.assertEqual(ctx.exception.code, "DIAGRAM_SOURCE_ABSENT")
        # The subprocess boundary refuses on its own too (`figure optimize
        # --file -x.tex` reaches it with the file stem, never figure_paths).
        with self.assertRaises(Refused) as ctx:
            paper_latex.compile(
                self.paper / "Figures", figure_id, self.root / "scratch", path=str(self.bin_dir)
            )
        self.assertEqual(ctx.exception.code, "DIAGRAM_SOURCE_ABSENT")
        self.assertFalse(self.record.exists(), "latexmk was invoked with an option-like id")
        self.assertFalse((self.root / "scratch").exists())

    def test_valid_figure_id_compiles_expected_artifact(self) -> None:
        self._write_figure("diag-1")
        result = paper_figure.render(self.paper, "diag-1", path=str(self.bin_dir))
        self.assertEqual(result["verdict"], "success")
        argv = json.loads(self.record.read_text(encoding="utf-8").splitlines()[0])["argv"]
        self.assertEqual(argv[-1], "diag-1.tex")
        scratch = self.paper / ".paper-writing" / "figures" / "diag-1"
        self.assertTrue((scratch / "diag-1.pdf").is_file())


if __name__ == "__main__":
    unittest.main()
