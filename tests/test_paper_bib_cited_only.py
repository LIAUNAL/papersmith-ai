"""`bib build` writes only the entries the manuscript cites.

The evidence store is append-only: a citation dropped from the text keeps its
records. The bibliography is built from the citations the text carries, each
still required to have sourced, ingested evidence. Every fixture runs the real
`paper_cli.py` subprocess under the gitignored `.scratch/` tree and is removed
afterward.
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
import paper_evidence  # noqa: E402
import paper_resolve  # noqa: E402

DIGEST = "c" * 64
QUOTE = "weights each instance by its attention score"


class BibBuildCitedOnlyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = FORGE_ROOT / ".scratch" / f".paper-bib-cited-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.paper_dir = self.root / "paper"
        self.guidance = self.root / "guidance"
        folder = self.guidance / "methods"
        (folder / "smith2024").mkdir(parents=True)
        self.source_md = folder / "smith2024" / "smith2024.md"
        self.source_md.write_text(f"The model {QUOTE} before pooling.\n", encoding="utf-8")
        self.assertEqual(self._run("scaffold", "--paper", str(self.paper_dir)).returncode, 0)
        paper_resolve.cache_metadata(self.paper_dir, {
            "identifier": "10.1234/abc.5", "resolver": "crossref", "metadata_digest": DIGEST,
            "title": "Attention MIL", "doi": "10.1234/abc.5", "year": 2024,
            "authors": ["Ada Smith"], "venue": "Neural Journal",
        })
        for key in ("smith2024", "jones2023"):
            span = paper_evidence.EvidenceSpan.locate(self.source_md, QUOTE)
            paper_evidence.append_record(self.paper_dir, paper_evidence.EvidenceRecord.from_verdict(
                block_id="methods", regime="resolution", claim=f"claim for {key}", cite_key=key,
                identifier="10.1234/abc.5", resolver="crossref", metadata_digest=DIGEST,
                verdict=paper_evidence.Verdict.holds(span), round=1,
            ))

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(CLI), *args], capture_output=True, text=True, timeout=30)

    def _build(self) -> subprocess.CompletedProcess:
        return self._run("bib", "build", "--paper", str(self.paper_dir), "--guidance", str(self.guidance))

    def test_a_citation_dropped_from_the_text_leaves_the_bibliography(self) -> None:
        (self.paper_dir / "main.tex").write_text("See \\cite{smith2024}.\n", encoding="utf-8")
        store = self.paper_dir / ".paper-writing" / "evidence" / "methods.jsonl"
        before = store.read_bytes()

        proc = self._build()

        self.assertEqual((proc.returncode, proc.stderr), (0, ""), proc.stdout)
        out = json.loads(proc.stdout)
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["entries"], ["smith2024"])
        self.assertEqual(out["reciprocal"], {"cited": ["smith2024"], "entries": ["smith2024"]})
        refs = (self.paper_dir / "refs.bib").read_text(encoding="utf-8")
        self.assertIn("@article{smith2024,", refs)
        self.assertNotIn("jones2023", refs)
        self.assertEqual(store.read_bytes(), before)

    def test_every_cited_key_with_evidence_is_still_written(self) -> None:
        (self.paper_dir / "main.tex").write_text("See \\cite{smith2024,jones2023}.\n", encoding="utf-8")

        proc = self._build()

        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertEqual(json.loads(proc.stdout)["entries"], ["jones2023", "smith2024"])

    def test_a_starred_citep_with_optional_arguments_counts_as_cited(self) -> None:
        (self.paper_dir / "main.tex").write_text(
            "See \\citep*[see][p.~3]{jones2023}.\n", encoding="utf-8",
        )

        proc = self._build()

        self.assertEqual(proc.returncode, 0, proc.stdout)
        out = json.loads(proc.stdout)
        self.assertEqual(out["entries"], ["jones2023"])
        self.assertEqual(out["reciprocal"], {"cited": ["jones2023"], "entries": ["jones2023"]})

    def test_a_cited_key_without_evidence_still_refuses(self) -> None:
        (self.paper_dir / "main.tex").write_text("See \\cite{smith2024,ghost2025}.\n", encoding="utf-8")

        proc = self._build()

        self.assertEqual(proc.returncode, 2, proc.stdout)
        out = json.loads(proc.stdout)
        self.assertEqual(out["code"], "CITE_WITHOUT_ENTRY")
        self.assertIn("ghost2025", out["detail"])


if __name__ == "__main__":
    unittest.main()
