"""One tolerant BibTeX reader, and a `bib build` that never loses entries.

`paper_bib.parse_bib` is the reader every consumer shares. `bib build` rebuilds
`refs.bib` from evidence records alone, so a cited entry with no record would
be lost: it refuses before writing, leaving the file byte for byte as it was.
Runs the real `paper_cli.py` under the gitignored `.scratch/` tree, because
`--paper` must resolve inside the repository.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import unittest
import uuid
from pathlib import Path

FORGE_ROOT = Path(__file__).resolve().parents[1]
SKILL_SCRIPTS = FORGE_ROOT / "skills" / "paper-writing" / "scripts"
CLI = SKILL_SCRIPTS / "paper_cli.py"
sys.path.insert(0, str(SKILL_SCRIPTS))
import paper_bib  # noqa: E402
import paper_evidence  # noqa: E402
import paper_resolve  # noqa: E402

DIGEST = "c" * 64
QUOTE = "weights each instance by its attention score"
HAND_WRITTEN = (
    b"@article{smith2024, title={Hand Written}, year={2024}}\n"
    b"@article(jones2023, title={Parenthesised}, year={2023})\n"
)


class SharedParserTests(unittest.TestCase):
    def test_exporter_shapes_are_read(self) -> None:
        parsed = paper_bib.parse_bib(
            '@string{jn = "Neural Journal"}\n'
            "@article{a, title={One Line}, journal=jn}\n"
            '@ARTICLE(b,\n  TITLE = "Multi\n  line",\n)\n')
        self.assertEqual(parsed["a"], {"title": "One Line", "journal": "Neural Journal", "_type": "article"})
        self.assertEqual(parsed["b"]["title"], "Multi\n  line")

    def test_plain_text_is_the_shared_cleaner(self) -> None:
        self.assertEqual(paper_bib.plain_text(r"{P}{\'e}rez \& Sons"), "Pérez & Sons")

    def test_title_key_ignores_case_accents_latex_and_a_leading_article(self) -> None:
        self.assertEqual(paper_bib.title_key(r"The {P}{\'e}rez: Signals!"), paper_bib.title_key("Pérez signals"))
        self.assertNotEqual(paper_bib.title_key("Perez signals"), paper_bib.title_key("Perez signals two"))
        self.assertEqual(paper_bib.title_key(None), "")


class BibBuildGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = FORGE_ROOT / ".scratch" / f".paper-bib-guard-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.paper_dir = self.root / "paper"
        self.guidance = self.root / "guidance"
        proc = self._run("scaffold", "--paper", str(self.paper_dir))
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.refs = self.paper_dir / "refs.bib"

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(CLI), *args], capture_output=True, text=True, timeout=60)

    def _build(self) -> subprocess.CompletedProcess:
        self.guidance.mkdir(exist_ok=True)
        return self._run("bib", "build", "--paper", str(self.paper_dir), "--guidance", str(self.guidance))

    def _evidence_for_smith(self) -> None:
        folder = self.guidance / "methods" / "smith2024"
        folder.mkdir(parents=True)
        source_md = folder / "smith2024.md"
        source_md.write_text(f"The model {QUOTE} before pooling.\n", encoding="utf-8")
        paper_resolve.cache_metadata(self.paper_dir, {
            "identifier": "10.1000/b", "resolver": "crossref", "metadata_digest": DIGEST,
            "title": "Graph Priors", "doi": "10.1000/b", "year": 2023,
            "authors": ["Ada Smith"], "venue": "Neural Journal",
        })
        span = paper_evidence.EvidenceSpan.locate(source_md, QUOTE)
        paper_evidence.append_record(self.paper_dir, paper_evidence.EvidenceRecord.from_verdict(
            block_id="methods", regime="resolution", claim="Graph priors improve recall.",
            cite_key="smith2024", identifier="10.1000/b", resolver="crossref",
            metadata_digest=DIGEST, verdict=paper_evidence.Verdict.holds(span), round=1,
        ))

    def test_no_evidence_at_all_refuses_and_leaves_the_file_byte_identical(self) -> None:
        self.refs.write_bytes(HAND_WRITTEN)
        (self.paper_dir / "main.tex").write_text("See \\cite{smith2024,jones2023}.\n", encoding="utf-8")

        proc = self._build()

        self.assertEqual(proc.returncode, 2, proc.stdout)
        out = json.loads(proc.stdout)
        self.assertEqual((out["status"], out["code"]), ("refused", "ENTRY_UNSOURCED"))
        self.assertIn("jones2023", out["detail"])
        self.assertIn("smith2024", out["detail"])
        self.assertEqual(self.refs.read_bytes(), HAND_WRITTEN)

    def test_one_entry_without_evidence_refuses_the_whole_rebuild(self) -> None:
        self._evidence_for_smith()
        self.refs.write_bytes(HAND_WRITTEN)
        (self.paper_dir / "main.tex").write_text("See \\cite{smith2024,jones2023}.\n", encoding="utf-8")

        proc = self._build()

        out = json.loads(proc.stdout)
        self.assertEqual((proc.returncode, out["code"]), (2, "ENTRY_UNSOURCED"))
        self.assertIn("jones2023", out["detail"])
        self.assertNotIn("smith2024", out["detail"])
        self.assertEqual(self.refs.read_bytes(), HAND_WRITTEN)

    def test_an_entry_no_longer_cited_still_leaves_the_bibliography(self) -> None:
        self._evidence_for_smith()
        self.refs.write_bytes(HAND_WRITTEN)
        (self.paper_dir / "main.tex").write_text("See \\cite{smith2024}.\n", encoding="utf-8")

        proc = self._build()

        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertEqual(json.loads(proc.stdout)["entries"], ["smith2024"])
        written = self.refs.read_text(encoding="utf-8")
        self.assertIn("Graph Priors", written)
        self.assertNotIn("jones2023", written)

    def test_a_cited_key_with_no_entry_keeps_its_previous_refusal(self) -> None:
        self.refs.write_bytes(b"")
        (self.paper_dir / "main.tex").write_text("See \\cite{ghost2025}.\n", encoding="utf-8")

        proc = self._build()

        out = json.loads(proc.stdout)
        self.assertEqual((proc.returncode, out["code"]), (2, "CITE_WITHOUT_ENTRY"))


if __name__ == "__main__":
    unittest.main()
