"""The manuscript summary graph refreshes with the atlas manuscript layer.

A successful dashboard compile rebuilds ``.papersmith/manuscript_graph.json``
in a workspace (``papersmith.yaml`` present) next to the T3 layer; a builder
error rides along as a warning and never turns a good compile into a failure.
``POST /api/atlas/manuscript-graph/build`` writes it on demand, same-origin
only. ``bib build`` and ``verify`` (the real ``paper_cli.py``) refresh it too,
without changing their status or exit code.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

from skills._core.command_center import server

REPO = Path(__file__).resolve().parent.parent
FIXTURE = REPO / "tests" / "fixtures" / "manuscript_graph"
CLI = REPO / "skills" / "paper-writing" / "scripts" / "paper_cli.py"
GRAPH = Path(".papersmith") / "manuscript_graph.json"
COMPILED = ({"ok": True, "message": "paper/main.pdf compiled (1 pages).",
             "outputs": ["paper/main.pdf"]}, 200)


class _Request:
    def __init__(self, origin: str | None = None) -> None:
        self.headers = {"host": "127.0.0.1:8080"}
        if origin:
            self.headers["origin"] = origin


class CompileTriggerTests(unittest.TestCase):
    def workspace(self) -> Path:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        root = Path(holder.name).resolve() / "ws"
        shutil.copytree(FIXTURE, root)
        return root

    def test_a_successful_compile_rebuilds_the_graph_and_the_layer(self) -> None:
        root = self.workspace()
        with mock.patch.object(server, "_compile_tex", return_value=COMPILED):
            body, status = server._compile_paper(root)
        self.assertEqual((status, body["ok"]), (200, True))
        self.assertEqual(body["manuscript_graph"]["status"], "written")
        self.assertEqual(body["atlas_manuscript"]["status"], "written")
        self.assertTrue((root / GRAPH).is_file())

    def test_a_failed_compile_leaves_the_graph_alone(self) -> None:
        root = self.workspace()
        failed = ({"ok": False, "message": "pdflatex failed", "outputs": []}, 422)
        with mock.patch.object(server, "_compile_tex", return_value=failed):
            self.assertEqual(server._compile_paper(root), failed)
        self.assertFalse((root / GRAPH).exists())

    def test_a_builder_error_is_a_warning_not_a_failed_compile(self) -> None:
        root = self.workspace()
        (root / ".papersmith").write_text("not a directory", encoding="utf-8")
        with mock.patch.object(server, "_compile_tex", return_value=COMPILED):
            body, status = server._compile_paper(root)
        self.assertEqual((status, body["ok"]), (200, True))
        self.assertEqual(body["manuscript_graph"]["status"], "error")
        self.assertIn("warning", body["manuscript_graph"])

    def test_post_build_writes_the_graph_same_origin_only(self) -> None:
        root = self.workspace()
        app = server.create_app(root, history_store=None)
        endpoint = next(r.endpoint for r in app.routes
                        if getattr(r, "path", "") == "/api/atlas/manuscript-graph/build")
        refused = endpoint(_Request(origin="http://evil.example"))
        self.assertEqual(refused.status_code, 403)
        self.assertFalse((root / GRAPH).exists())
        response = endpoint(_Request())
        self.assertEqual(response.status_code, 200)
        body = json.loads(bytes(response.body))
        self.assertEqual((body["ok"], body["status"]), (True, "written"))
        self.assertTrue((root / GRAPH).is_file())


class PaperCliTriggerTests(unittest.TestCase):
    """`verify` and `bib build` through the real CLI, in the gitignored `.scratch/`."""

    def setUp(self) -> None:
        self.root = REPO / ".scratch" / f".manuscript-graph-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        shutil.copytree(FIXTURE, self.root)

    def run_cli(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(CLI), *args], capture_output=True, text=True,
                              timeout=120)

    def _coupling_workspace(self) -> tuple[Path, Path]:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from test_paper_writing import _build_coupling_paper  # noqa: PLC0415

        root = self.root / "coupled"
        _build_coupling_paper(root / "paper", root / "sections")
        return root, root / "sections"

    def _verify(self, root: Path, sections: Path) -> subprocess.CompletedProcess:
        return self.run_cli("verify", "--paper", str(root / "paper"), "--sections", str(sections))

    def test_verify_reports_the_graph_without_changing_its_report_or_exit_code(self) -> None:
        root, sections = self._coupling_workspace()
        baseline = self._verify(root, sections)
        before = json.loads(baseline.stdout)
        self.assertNotIn("manuscript_graph", before)
        (root / "papersmith.yaml").write_text("topic: Coupled paper\n", encoding="utf-8")
        proc = self._verify(root, sections)
        self.assertEqual(proc.returncode, baseline.returncode, proc.stderr)
        after = json.loads(proc.stdout)
        self.assertEqual(after.pop("manuscript_graph")["status"], "written")
        self.assertEqual(after, before)
        graph = json.loads((root / GRAPH).read_text("utf-8"))
        self.assertEqual(graph["nodes"][0]["label"], "Coupled paper")

    def test_a_builder_error_on_bib_build_is_a_warning_only(self) -> None:
        (self.root / ".papersmith").write_text("not a directory", encoding="utf-8")
        (self.root / "paper" / "main.tex").write_text("No citations.\n", encoding="utf-8")
        (self.root / "paper" / "refs.bib").write_text("", encoding="utf-8")
        guidance = self.root / "guidance"
        guidance.mkdir()
        proc = self.run_cli("bib", "build", "--paper", str(self.root / "paper"),
                            "--guidance", str(guidance))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        out = json.loads(proc.stdout)
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["manuscript_graph"]["status"], "error")
        self.assertIn("warning", out["manuscript_graph"])
        self.assertEqual(out["atlas_manuscript"]["status"], "written")


if __name__ == "__main__":
    unittest.main()
