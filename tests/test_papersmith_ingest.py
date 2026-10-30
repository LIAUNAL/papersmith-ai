"""Ingestion source classification and index/bridge behavior."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from papersmith.core import ingest as ingest_module
from papersmith.core import init as init_module
from papersmith.errors import UserError


ROOT = Path(__file__).resolve().parents[1]


class IngestTests(unittest.TestCase):
    def new_tmp(self) -> Path:
        """Scratch directory, resolved -- see BridgesTests.new_tmp for why."""
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        return Path(holder.name).resolve()

    def patch(self, target, attribute, value):
        patcher = mock.patch.object(target, attribute, value)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_classify_supported_sources(self) -> None:
        cases = [
            (
                "https://arxiv.org/abs/2401.12345",
                "url",
                "https://arxiv.org/pdf/2401.12345.pdf",
                "2401.12345",
            ),
            (
                "https://arxiv.org/pdf/2401.12345.pdf",
                "url",
                "https://arxiv.org/pdf/2401.12345.pdf",
                "2401.12345",
            ),
            (
                "https://example.org/papers/method.pdf?download=1",
                "url",
                "https://example.org/papers/method.pdf?download=1",
                "method",
            ),
            (
                "https://openreview.net/forum?id=abc123",
                "openreview",
                "https://openreview.net/forum?id=abc123",
                "abc123",
            ),
        ]
        for source, kind, url, slug in cases:
            with self.subTest(source=source):
                result = ingest_module.classify_source(source)
                assert result == {"kind": kind, "url": url, "slug": slug}

    def test_classify_local_pdf(self) -> None:
        tmp_path = self.new_tmp()
        path = tmp_path / "my paper.pdf"
        path.write_bytes(b"pdf")
        assert ingest_module.classify_source(str(path)) == {
            "kind": "file", "url": "", "slug": "my-paper"
        }

    def test_classify_rejects_unknown_sources(self) -> None:
        with self.assertRaisesRegex(UserError, "must be a PDF path"):
            ingest_module.classify_source("notes.txt")
        with self.assertRaisesRegex(UserError, "must point to a PDF"):
            ingest_module.classify_source("https://example.org/landing-page")

    def test_a_non_pdf_refusal_names_the_deliberation_seeding_routes(self) -> None:
        for source in ("notes.md", "draft.txt", "https://example.org/landing-page"):
            with self.subTest(source=source):
                with self.assertRaises(UserError) as caught:
                    ingest_module.classify_source(source)
                message = str(caught.exception)
                self.assertIn("PDFs only", message)
                self.assertIn("guidance/paper-guide/", message)
                self.assertIn("ADOPT_INITIAL_REVISION", message)

    def test_refresh_index_scans_ingested_markdown(self) -> None:
        tmp_path = self.new_tmp()
        workspace = tmp_path / "paper"
        reference = workspace / "guidance/reference-papers/method"
        reference.mkdir(parents=True)
        (reference / "method.md").write_text("# A Reproducible Method\n\nBody.\n", encoding="utf-8")
        (reference / "figure.png").write_bytes(b"image")
        (workspace / "guidance/reference-papers/README.md").parent.mkdir(parents=True, exist_ok=True)
        (workspace / "guidance/reference-papers/README.md").write_text("# References", encoding="utf-8")

        index = ingest_module.refresh_index(workspace)

        assert len(index["entries"]) == 1
        entry = index["entries"][0]
        assert entry["id"] == "method"
        assert entry["title"] == "A Reproducible Method"
        assert entry["path"] == "guidance/reference-papers/method/method.md"
        assert (workspace / "guidance/reference-papers/index.json").is_file()

    def test_ingest_delegates_pdf_and_refreshes_index(self) -> None:
        tmp_path = self.new_tmp()
        workspace = tmp_path / "paper"
        init_module.initialize(workspace, run_npm=False, run_env=False)
        source = tmp_path / "source.pdf"
        source.write_bytes(b"pdf")
        captured: dict[str, object] = {}

        def fake_run(root, script, args, **kwargs):
            captured["root"] = root
            captured["script"] = script
            captured["args"] = list(args)
            output = workspace / "guidance/reference-papers/source/source.md"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text("# Extracted Source\n", encoding="utf-8")
            return subprocess.CompletedProcess([], 0, "ingested\n", "")

        self.patch(ingest_module, "run_script", fake_run)
        result = ingest_module.ingest(str(source), workspace, ocr=True)

        assert captured["script"] == "skills/paper-ingestion/scripts/extract_pdf.py"
        assert captured["args"] == [
            "guidance/reference-papers/source.pdf", "--mode", "balanced"
        ]
        assert result["index"]["entries"][0]["title"] == "Extracted Source"

    def test_extract_pdf_accepts_mode_override_and_rejects_invalid_mode(self) -> None:
        script = ROOT / "skills/paper-ingestion/scripts/extract_pdf.py"
        valid = subprocess.run(
            [sys.executable, str(script), "--list", "--mode", "balanced"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        assert valid.returncode == 0, valid.stderr
        invalid = subprocess.run(
            [sys.executable, str(script), "--list", "--mode", "invalid"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        assert invalid.returncode == 2

    def test_extract_pdf_defaults_cpu_on_intel_mac(self) -> None:
        script = (
            "import os, sys, platform\n"
            "os.environ.pop('TORCH_DEVICE', None)\n"
            "platform.machine = lambda: 'x86_64'\n"
            "sys.platform = 'darwin'\n"
            "import runpy\n"
            "runpy.run_path('skills/paper-ingestion/scripts/extract_pdf.py', run_name='fake')\n"
            "print(os.environ.get('TORCH_DEVICE', ''))\n"
        )
        res = subprocess.run(
            [sys.executable, "-c", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout.strip(), "cpu")

