"""A successful dashboard compile refreshes the atlas manuscript layer.

``server._compile_paper`` runs the TeX chain (``_compile_tex``, mocked here)
and, only when it succeeds and the workspace has an atlas, rebuilds
``sota-pool/atlas.manuscript.json``. A builder error rides along as a warning;
it never turns a good compile into a failure. ``POST /api/atlas/manuscript/build``
writes the layer on demand.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from skills._core.command_center import server

REPO = Path(__file__).resolve().parent.parent
FIXTURE = REPO / "tests" / "fixtures" / "atlas_manuscript"
COMPILED = ({"ok": True, "message": "paper/main.pdf compiled (1 pages).",
             "outputs": ["paper/main.pdf"]}, 200)


class _Request:
    """Just enough of a Starlette request for `origin_is_same`."""

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

    def test_a_successful_compile_rebuilds_the_layer(self) -> None:
        root = self.workspace()
        before = (root / "sota-pool" / "atlas.json").read_bytes()
        with mock.patch.object(server, "_compile_tex", return_value=COMPILED):
            body, status = server._compile_paper(root)
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["atlas_manuscript"]["status"], "written")
        self.assertEqual(body["atlas_manuscript"]["summary"]["cited_systems"], 2)
        self.assertTrue((root / "sota-pool" / "atlas.manuscript.json").is_file())
        self.assertEqual((root / "sota-pool" / "atlas.json").read_bytes(), before)

    def test_a_failed_compile_leaves_the_layer_alone(self) -> None:
        root = self.workspace()
        failed = ({"ok": False, "message": "pdflatex failed", "outputs": []}, 422)
        with mock.patch.object(server, "_compile_tex", return_value=failed):
            self.assertEqual(server._compile_paper(root), failed)
        self.assertFalse((root / "sota-pool" / "atlas.manuscript.json").exists())

    def test_without_an_atlas_the_compile_answer_is_unchanged(self) -> None:
        root = self.workspace()
        shutil.rmtree(root / "sota-pool")
        with mock.patch.object(server, "_compile_tex", return_value=COMPILED):
            self.assertEqual(server._compile_paper(root), COMPILED)

    def test_a_builder_error_is_a_warning_not_a_failed_compile(self) -> None:
        root = self.workspace()
        (root / "sota-pool" / "atlas.json").write_text("{broken", encoding="utf-8")
        with mock.patch.object(server, "_compile_tex", return_value=COMPILED):
            body, status = server._compile_paper(root)
        self.assertEqual((status, body["ok"]), (200, True))
        self.assertEqual(body["atlas_manuscript"]["status"], "error")
        self.assertIn("warning", body["atlas_manuscript"])

    def test_post_build_writes_the_layer(self) -> None:
        root = self.workspace()
        app = server.create_app(root, history_store=None)
        endpoint = next(r.endpoint for r in app.routes
                        if getattr(r, "path", "") == "/api/atlas/manuscript/build")
        response = endpoint(_Request())
        self.assertEqual(response.status_code, 200)
        self.assertTrue(json.loads(bytes(response.body))["ok"])
        self.assertTrue((root / "sota-pool" / "atlas.manuscript.json").is_file())
        refused = endpoint(_Request(origin="http://evil.example"))
        self.assertEqual(refused.status_code, 403)


if __name__ == "__main__":
    unittest.main()
