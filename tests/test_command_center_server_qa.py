"""The dashboard runs the manuscript QA after a successful compile (spec S6
of `odd/tasks/figure-and-table-quality.md`) and serves it read-only.

A QA error rides along as a warning and never changes the compile's status;
a failed compile runs no QA. `GET /api/paper/qa` reports the last report and
whether `paper/main.pdf` changed since; `GET /api/paper/qa/page?n=` serves
its page images.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from skills._core.command_center import server

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tests"))
from test_manuscript_qa import PDFLATEX, build_workspace  # noqa: E402

COMPILED = ({"ok": True, "message": "paper/main.pdf compiled (4 pages).",
             "outputs": ["paper/main.pdf"]}, 200)
QA_JSON = Path("paper") / ".qa" / "qa.json"


def endpoint(app, path: str):
    return next(r.endpoint for r in app.routes if getattr(r, "path", "") == path)


class _Base(unittest.TestCase):
    def scratch(self) -> Path:
        holder = Path(tempfile.mkdtemp(prefix="server-qa-"))
        self.addCleanup(shutil.rmtree, holder, ignore_errors=True)
        return holder


@unittest.skipIf(PDFLATEX is None, "pdflatex is not installed: the fixture manuscript cannot be compiled")
class CompileTriggerTests(_Base):
    def setUp(self) -> None:
        self.root = build_workspace(self.scratch() / "ws")
        if not (self.root / "paper" / "main.pdf").is_file():
            self.skipTest("the fixture manuscript did not compile")

    def test_a_successful_compile_writes_the_qa_report(self) -> None:
        with mock.patch.object(server, "_compile_tex", return_value=COMPILED):
            body, status = server._compile_paper(self.root)
        self.assertEqual((status, body["ok"], body["message"]), (200, True, COMPILED[0]["message"]))
        self.assertTrue(body["manuscript_qa"]["ok"])
        self.assertGreater(body["manuscript_qa"]["findings"], 0)
        self.assertTrue((self.root / QA_JSON).is_file())

    def test_a_failed_compile_runs_no_qa(self) -> None:
        failed = ({"ok": False, "message": "pdflatex failed", "outputs": []}, 422)
        with mock.patch.object(server, "_compile_tex", return_value=failed):
            self.assertEqual(server._compile_paper(self.root), failed)
        self.assertFalse((self.root / QA_JSON).exists())

    def test_the_api_serves_the_report_its_staleness_and_its_pages(self) -> None:
        app = server.create_app(self.root, history_store=None)
        qa = endpoint(app, "/api/paper/qa")
        self.assertEqual(json.loads(bytes(qa().body))["status"], "absent")
        with mock.patch.object(server, "_compile_tex", return_value=COMPILED):
            server._compile_paper(self.root)
        body = json.loads(bytes(qa().body))
        self.assertEqual((body["status"], body["stale"]), ("ok", False))
        self.assertEqual(body["report"]["summary"]["pages"], 4)
        page = endpoint(app, "/api/paper/qa/page")
        if shutil.which("pdftoppm"):
            image = page(n=1)
            self.assertEqual((image.status_code, image.media_type), (200, "image/png"))
            self.assertTrue(bytes(image.body).startswith(b"\x89PNG"))
        self.assertEqual(page(n=99).status_code, 404)
        self.assertEqual(page(n=0).status_code, 404)


class CompileTriggerWithoutAManuscriptTests(_Base):
    def test_an_unreadable_pdf_is_a_warning_not_a_failed_compile(self) -> None:
        root = self.scratch() / "ws"
        (root / "paper").mkdir(parents=True)
        (root / "papersmith.yaml").write_text("name: x\n", encoding="utf-8")
        (root / "paper" / "main.pdf").write_bytes(b"not a pdf")
        with mock.patch.object(server, "_compile_tex", return_value=COMPILED):
            body, status = server._compile_paper(root)
        self.assertEqual((status, body["ok"]), (200, True))
        self.assertFalse(body["manuscript_qa"]["ok"])
        self.assertIn("warning", body["manuscript_qa"])

    def test_outside_a_workspace_the_compile_answer_is_unchanged(self) -> None:
        root = self.scratch() / "plain"
        (root / "paper").mkdir(parents=True)
        with mock.patch.object(server, "_compile_tex", return_value=COMPILED):
            self.assertEqual(server._compile_paper(root), COMPILED)


if __name__ == "__main__":
    unittest.main()
