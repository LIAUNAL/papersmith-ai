"""Public CLI checks for section-specific evidence folders, in isolated state."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "skills/paper-writing/scripts/paper_cli.py"


class MultipleEvidenceCLITests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / ".scratch"
        scratch.mkdir(exist_ok=True)
        self.base = Path(tempfile.mkdtemp(prefix="multi-evidence-", dir=scratch))
        self.addCleanup(shutil.rmtree, self.base)
        self.paper = self.base / "paper"
        self.guidance = self.base / "guidance"
        self.guidance.mkdir()
        self.run_ok("scaffold", "--paper", str(self.paper))

    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(CLI), *args],
                              capture_output=True, text=True, timeout=30)

    def run_ok(self, *args):
        result = self.run_cli(*args)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(result.stderr, "")
        payload = json.loads(result.stdout)
        self.assertIn(payload["status"], ("ok", "pending", "satisfied"))
        return payload

    def add_source(self, folder, paper, klass="evidence"):
        target = self.guidance / folder
        target.mkdir(exist_ok=True)
        self.run_ok("mark", "class", "--guidance", str(self.guidance),
                    "--folder", folder, "--class", klass)
        document = target / paper / (paper + ".md")
        document.parent.mkdir()
        document.write_text("# Evidence\nThe measured quantity is bounded.\n")
        return document

    def snapshot(self):
        return {str(p.relative_to(self.base)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in self.base.rglob("*") if p.is_file()}

    def test_plan_combines_roots_and_validate_accepts_second_root(self):
        self.add_source("introduction", "first")
        source = self.add_source("methods-evidence", "second")
        before = self.snapshot()
        report = self.run_ok("plan", "--paper", str(self.paper),
                             "--guidance", str(self.guidance))
        self.assertEqual(report["sourceRoots"]["evidence"]["documents"], 2)
        self.assertEqual(self.snapshot(), before)
        report = self.run_ok("validate", "--paper", str(self.paper),
                             "--guidance", str(self.guidance), "--block", "sample",
                             "--claim", "The quantity is bounded.",
                             "--quote", "The measured quantity is bounded.",
                             "--source-md", str(source), "--verdict", "holds",
                             "--cite-key", "second")
        self.assertIn(report["status"], ("satisfied", "pending"))

    def test_style_reference_still_refuses_without_any_write(self):
        self.add_source("introduction", "first")
        source = self.add_source("style", "style-paper", "style-reference")
        before = self.snapshot()
        result = self.run_cli("validate", "--paper", str(self.paper),
                              "--guidance", str(self.guidance), "--block", "sample",
                              "--claim", "The quantity is bounded.",
                              "--quote", "The measured quantity is bounded.",
                              "--source-md", str(source), "--verdict", "holds")
        self.assertNotEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["code"], "SOURCE_STYLE_REFERENCE")
        self.assertEqual(result.stderr, "")
        self.assertEqual(self.snapshot(), before)
