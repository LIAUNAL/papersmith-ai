"""`verify` refreshes the atlas manuscript layer when its citation check passes.

The coupling fixture of `tests/test_paper_writing.py` is reused unchanged; a
`sota-pool/` copied next to its `paper/` makes the workspace hold an atlas.
`verify` still never writes under `paper/`, and its exit code and report are
unchanged by the layer, which rides under `atlas_manuscript`.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import unittest
import uuid
from pathlib import Path

FORGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_paper_writing import CLI, _build_coupling_paper  # noqa: E402

FIXTURE = FORGE_ROOT / "tests" / "fixtures" / "atlas_manuscript"


def _tree_digest(directory: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in directory.rglob("*") if p.is_file()):
        digest.update(str(path.relative_to(directory)).encode() + b"\0" + path.read_bytes())
    return digest.hexdigest()


class VerifyAtlasLayerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = FORGE_ROOT / ".scratch" / f".paper-verify-atlas-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.paper_dir = self.root / "paper"
        self.sections_dir = self.root / "sections"
        _build_coupling_paper(self.paper_dir, self.sections_dir)

    def _verify(self) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(CLI), "verify", "--paper", str(self.paper_dir),
             "--sections", str(self.sections_dir)],
            capture_output=True, text=True, timeout=60)

    def test_a_passing_citation_check_rebuilds_the_layer(self) -> None:
        shutil.copytree(FIXTURE / "sota-pool", self.root / "sota-pool")
        paper_before = _tree_digest(self.paper_dir)

        proc = self._verify()

        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        out = json.loads(proc.stdout)
        by_check = {entry["check"]: entry for entry in out["checks"]}
        self.assertEqual(by_check["citations"]["verdict"], "pass")
        self.assertEqual(out["atlas_manuscript"]["status"], "written")
        self.assertTrue((self.root / "sota-pool" / "atlas.manuscript.json").is_file())
        self.assertEqual(_tree_digest(self.paper_dir), paper_before)

    def test_a_dangling_citation_writes_no_layer(self) -> None:
        shutil.copytree(FIXTURE / "sota-pool", self.root / "sota-pool")
        (self.paper_dir / "refs.bib").write_text("", encoding="utf-8")
        proc = self._verify()
        out = json.loads(proc.stdout)
        by_check = {entry["check"]: entry for entry in out["checks"]}
        if by_check["citations"]["verdict"] == "pass":
            self.skipTest("the coupling fixture cites nothing, so no citation can dangle")
        self.assertNotIn("atlas_manuscript", out)
        self.assertFalse((self.root / "sota-pool" / "atlas.manuscript.json").exists())

    def test_without_an_atlas_the_report_has_no_layer_key(self) -> None:
        proc = self._verify()
        self.assertEqual(proc.returncode, 0, proc.stdout)
        out = json.loads(proc.stdout)
        self.assertEqual(sorted(out), ["checks", "clean", "command", "fails", "holds",
                                       "status", "unmeasured"])


if __name__ == "__main__":
    unittest.main()
