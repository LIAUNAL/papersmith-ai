"""`smith paper qa [--json] [<dir>]` runs the workspace's manuscript QA, and
`smith audit` reports the stored report's findings and staleness read-only
(spec S6 of `odd/tasks/figure-and-table-quality.md`)."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tests"))
from test_manuscript_qa import PDFLATEX, build_workspace  # noqa: E402

from papersmith.cli import main  # noqa: E402
from papersmith.core import init as init_module  # noqa: E402
from papersmith.core import paper_qa  # noqa: E402


def run_cli(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


@unittest.skipIf(PDFLATEX is None, "pdflatex is not installed: the fixture manuscript cannot be compiled")
class SmithPaperQaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.scratch = Path(tempfile.mkdtemp(prefix="smith-paper-qa-"))
        cls.root = build_workspace(cls.scratch / "ws")
        if not (cls.root / "paper" / "main.pdf").is_file():
            raise unittest.SkipTest("the fixture manuscript did not compile")
        # The workspace's kit copy of the module, as `smith upgrade` lays it out.
        (cls.root / "skills").symlink_to(REPO / "skills", target_is_directory=True)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.scratch, ignore_errors=True)

    def test_json_prints_the_report_and_writes_it(self) -> None:
        code, out, _ = run_cli("paper", "qa", "--json", str(self.root))
        self.assertEqual(code, 0)
        report = json.loads(out)
        self.assertEqual(report["summary"]["pages"], 4)
        self.assertEqual(set(report["summary"]["by_kind"]),
                         {"overflow", "overfull", "table-font", "figure-font"})
        self.assertTrue((self.root / "paper" / ".qa" / "qa.json").is_file())

    def test_the_default_output_is_one_summary_line_and_the_findings(self) -> None:
        code, out, _ = run_cli("paper", "qa", str(self.root))
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("manuscript QA: "))
        self.assertIn("page 2: overfull", out)


class SmithPaperQaRefusalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="smith-paper-qa-absent-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def test_a_workspace_without_the_module_is_told_to_upgrade(self) -> None:
        code, _, err = run_cli("paper", "qa", str(self.root))
        self.assertEqual(code, 1)
        self.assertIn("smith upgrade", err)

    def test_a_workspace_without_a_pdf_exits_one(self) -> None:
        (self.root / "skills").symlink_to(REPO / "skills", target_is_directory=True)
        code, out, _ = run_cli("paper", "qa", "--json", str(self.root))
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out)["error"], "PDF_ABSENT")


class AuditReportsQaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._holder = tempfile.TemporaryDirectory()
        cls.workspace = Path(cls._holder.name).resolve() / "qa-audit"
        init_module.initialize(cls.workspace, run_npm=False, run_env=False)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._holder.cleanup()

    def tearDown(self) -> None:
        shutil.rmtree(self.workspace / "paper" / ".qa", ignore_errors=True)
        pdf = self.workspace / "paper" / "main.pdf"
        if pdf.exists():
            pdf.unlink()

    def test_without_a_compiled_manuscript_the_audit_output_is_unchanged(self) -> None:
        self.assertIsNone(paper_qa.audit_line(self.workspace))
        code, out, _ = run_cli("audit", str(self.workspace), "--check-drift")
        self.assertEqual(code, 0)
        self.assertNotIn("manuscript qa", out)
        self.assertIn("drift: clean", out)

    def write_report(self, findings: int) -> Path:
        pdf = self.workspace / "paper" / "main.pdf"
        pdf.parent.mkdir(exist_ok=True)
        pdf.write_bytes(b"%PDF-1.5 fixture\n")
        qa = self.workspace / "paper" / ".qa"
        qa.mkdir(parents=True, exist_ok=True)
        (qa / "qa.json").write_text(json.dumps({
            "pdf_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
            "summary": {"findings": findings, "by_kind": {"overflow": findings}, "pages": 1},
        }), encoding="utf-8")
        return pdf

    def test_a_current_report_is_reported_and_never_changes_the_exit_code(self) -> None:
        self.write_report(3)
        code, out, _ = run_cli("audit", str(self.workspace), "--check-drift")
        self.assertEqual(code, 0)
        self.assertIn("manuscript qa: 3 finding(s) (overflow 3), current", out)
        self.assertIn("drift: clean", out)

    def test_a_stale_or_missing_report_is_reported(self) -> None:
        pdf = self.write_report(0)
        pdf.write_bytes(b"%PDF-1.5 recompiled\n")
        self.assertEqual(paper_qa.audit_line(self.workspace),
                         "manuscript qa: 0 finding(s), stale (main.pdf changed): run smith paper qa")
        shutil.rmtree(self.workspace / "paper" / ".qa")
        self.assertEqual(paper_qa.audit_line(self.workspace),
                         "manuscript qa: not run: run smith paper qa")


if __name__ == "__main__":
    unittest.main()
