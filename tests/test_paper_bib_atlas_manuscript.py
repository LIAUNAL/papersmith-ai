"""`bib build` refreshes the atlas manuscript layer, and never fails for it.

When the workspace holding `paper/` also holds `sota-pool/atlas.json`, a
clean `bib build` (reciprocal check passed) rebuilds
`sota-pool/atlas.manuscript.json` and reports it under `atlas_manuscript`. A
builder error is a warning in that key; the verb still exits 0. Without an
atlas the output carries no such key, exactly as before. Runs the real
`paper_cli.py` under the gitignored `.scratch/` tree.
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
FIXTURE = FORGE_ROOT / "tests" / "fixtures" / "atlas_manuscript"
sys.path.insert(0, str(SKILL_SCRIPTS))
import paper_evidence  # noqa: E402
import paper_resolve  # noqa: E402

DIGEST = "c" * 64
QUOTE = "weights each instance by its attention score"


class BibBuildAtlasLayerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = FORGE_ROOT / ".scratch" / f".paper-bib-atlas-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.paper_dir = self.root / "paper"
        self.guidance = self.root / "guidance"
        folder = self.guidance / "methods" / "smith2024"
        folder.mkdir(parents=True)
        source_md = folder / "smith2024.md"
        source_md.write_text(f"The model {QUOTE} before pooling.\n", encoding="utf-8")
        proc = self._run("scaffold", "--paper", str(self.paper_dir))
        self.assertEqual(proc.returncode, 0, proc.stdout)
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
        (self.paper_dir / "main.tex").write_text("See \\cite{smith2024}.\n", encoding="utf-8")

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(CLI), *args], capture_output=True, text=True,
                              timeout=60)

    def _build(self) -> subprocess.CompletedProcess:
        return self._run("bib", "build", "--paper", str(self.paper_dir), "--guidance", str(self.guidance))

    def _with_atlas(self) -> Path:
        shutil.copytree(FIXTURE / "sota-pool", self.root / "sota-pool")
        return self.root / "sota-pool"

    def test_a_clean_build_rebuilds_the_layer(self) -> None:
        pool = self._with_atlas()
        atlas_before = (pool / "atlas.json").read_bytes()

        proc = self._build()

        self.assertEqual((proc.returncode, proc.stderr), (0, ""), proc.stdout)
        out = json.loads(proc.stdout)
        self.assertEqual(out["entries"], ["smith2024"])
        self.assertEqual(out["atlas_manuscript"]["status"], "written")
        self.assertEqual(out["atlas_manuscript"]["summary"]["uncited_systems"], ["sys-a", "sys-c"])
        layer = json.loads((pool / "atlas.manuscript.json").read_text("utf-8"))
        by_id = {s["id"]: s for s in layer["systems"]}
        self.assertEqual(by_id["sys-b"]["cite_keys"], ["smith2024"])
        self.assertEqual(by_id["sys-b"]["blocks"], ["methods"])
        self.assertEqual((pool / "atlas.json").read_bytes(), atlas_before)

    def test_a_builder_error_is_a_warning_and_the_exit_code_holds(self) -> None:
        pool = self._with_atlas()
        (pool / "atlas.json").write_text("{broken", encoding="utf-8")

        proc = self._build()

        self.assertEqual(proc.returncode, 0, proc.stdout)
        out = json.loads(proc.stdout)
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["atlas_manuscript"]["status"], "error")
        self.assertIn("warning", out["atlas_manuscript"])
        self.assertFalse((pool / "atlas.manuscript.json").exists())

    def test_without_an_atlas_the_output_is_unchanged(self) -> None:
        proc = self._build()

        self.assertEqual(proc.returncode, 0, proc.stdout)
        out = json.loads(proc.stdout)
        self.assertEqual(sorted(out), ["command", "entries", "path", "reciprocal", "status"])
        self.assertFalse((self.root / "sota-pool").exists())

    def test_a_refused_build_writes_no_layer(self) -> None:
        pool = self._with_atlas()
        (self.paper_dir / "main.tex").write_text("See \\cite{smith2024,nobody1999}.\n", encoding="utf-8")

        proc = self._build()

        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertFalse((pool / "atlas.manuscript.json").exists())


if __name__ == "__main__":
    unittest.main()
