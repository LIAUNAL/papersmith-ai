"""A fresh workspace's dashboard shows its own data or neutral defaults, never
an older project's: the model spec, the novelty graph and its viewer."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from skills._core.command_center import model_spec, novelty_graph

FIXTURES = Path(__file__).resolve().parent / "fixtures"


class NeutralDefaultsTests(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.root = Path(holder.name).resolve() / "moneeg-like-name"
        self.root.mkdir()
        (self.root / "papersmith.yaml").write_text("title: Fresh Paper\n", encoding="utf-8")

    def test_no_root_and_a_suggestive_name_both_get_the_neutral_spec(self) -> None:
        for spec in (model_spec.get_model_specification(None),
                     model_spec.get_model_specification(self.root)):
            text = json.dumps(spec, ensure_ascii=False)
            self.assertNotIn("ADS1299", text)
            self.assertEqual(spec["mathematical_model"]["equations"], [])
        self.assertEqual(model_spec.get_model_specification(self.root)["title"], "Fresh Paper")

    def test_the_novelty_graph_is_neutral_unless_the_workspace_provides_one(self) -> None:
        graph = novelty_graph.build_novelty_graph(self.root)
        self.assertEqual(graph["project"], "moneeg-like-name")
        self.assertNotIn("ADS1299", json.dumps(graph, ensure_ascii=False))
        (self.root / ".papersmith").mkdir()
        shutil.copy(FIXTURES / "moneeg" / "novelty_graph.json", self.root / ".papersmith" / "novelty_graph.json")
        own = novelty_graph.build_novelty_graph(self.root)
        self.assertGreater(len(own["nodes"]), 10)

    def test_the_viewer_names_the_project_and_escapes_its_title(self) -> None:
        (self.root / ".papersmith").mkdir()
        (self.root / ".papersmith" / "novelty_graph.json").write_text(json.dumps({
            "title": "<script>x</script>", "project": "Fresh", "nodes": [], "links": []}), encoding="utf-8")
        page = novelty_graph.build_novelty_viewer_html(self.root)
        self.assertIn("&lt;script&gt;x&lt;/script&gt;", page)
        self.assertIn("{ id: 'core', label: \"Fresh\"", page)


if __name__ == "__main__":
    unittest.main()


class ServerNeutralTests(unittest.TestCase):
    REPO = Path(__file__).resolve().parents[1]
    OLD = ("MONEEG", "moneeg", "Parias", "Elsevier", "18 candidatos", "46 bloques", "/Users/")

    def setUp(self) -> None:
        import asyncio
        from skills._core.command_center import server
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.root = Path(holder.name).resolve() / "fresh-paper"
        self.root.mkdir()
        self.app = server.create_app(self.root, history_store=None)
        self.asyncio = asyncio

    def route(self, path: str, method: str = "GET"):
        return next(r.endpoint for r in self.app.routes
                    if getattr(r, "path", None) == path and method in (getattr(r, "methods", None) or ()))

    def test_phase_actions_report_this_workspace_only(self) -> None:
        class Req:
            def __init__(self, body):
                self.body = body
                self.headers = {}  # origin_is_same reads it; no Origin header, as from curl

            async def json(self):
                return self.body

        endpoint = self.route("/api/phase/run", "POST")
        for phase in ("Fase 2", "Fase 3", "Fase 4", "Fase 6", "Fase 7", "Fase 10", "Fase 11"):
            with self.subTest(phase=phase):
                response = self.asyncio.run(endpoint(Req({"phase_id": phase})))
                text = bytes(response.body).decode("utf-8")
                for marker in self.OLD:
                    self.assertNotIn(marker, text)
        response = self.asyncio.run(endpoint(Req({"phase_id": "Fase 2"})))
        self.assertIn("0 candidatos", bytes(response.body).decode("utf-8"))

    def test_the_flow_diagram_ships_with_the_dashboard_and_matches_the_docs(self) -> None:
        from skills._core.command_center import server
        shipped = Path(server.__file__).resolve().parent / "static" / "papersmith-flow.html"
        self.assertEqual(shipped.read_bytes(),
                         (self.REPO / "docs" / "diagrams" / "papersmith-pi-flow.html").read_bytes())
        response = self.route("/api/flow")()
        self.assertEqual(response.status_code, 200)

    def test_the_candidates_view_is_titled_with_the_workspace(self) -> None:
        page = bytes(self.route("/api/atlas/candidates/view")().body).decode("utf-8")
        self.assertIn("fresh-paper", page)
        self.assertNotIn("MONEEG", page)
