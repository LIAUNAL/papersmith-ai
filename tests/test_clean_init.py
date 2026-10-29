"""A new smith workspace inherits nothing from older projects.

Two halves: nothing the kit ships names an older project (its people, its
hardware, its numbers, its paths), and a workspace fresh from `init` gets a
dashboard that shows only its own data or neutral empty states.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from papersmith.core import init as init_module
from papersmith.core.manifest import walk_kit_files

REPO = Path(__file__).resolve().parents[1]

#: Markers of earlier projects that once leaked into the dashboard. Matched
#: case-insensitively against every text file the kit ships.
OLD_PROJECT_MARKERS = (
    "moneeg", "ads1299", "tm4c", "tdah", "efecto berger", "parias", "minciencias",
    "eje cafetero", "qmleeg", "/users/andresalvarez",
)


class KitTests(unittest.TestCase):
    def test_nothing_the_kit_ships_names_an_older_project(self) -> None:
        hits = []
        for rel in sorted(walk_kit_files(REPO)):
            path = REPO / rel
            try:
                text = path.read_text(encoding="utf-8").lower()
            except (UnicodeDecodeError, OSError):
                continue
            hits.extend(f"{rel}: {m}" for m in OLD_PROJECT_MARKERS if m in text)
        self.assertEqual(hits, [])


class FreshWorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.holder = tempfile.TemporaryDirectory()
        cls.root = Path(cls.holder.name).resolve() / "fresh-paper"
        init_module.initialize(cls.root, title="Fresh Paper", run_npm=False, run_env=False)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.holder.cleanup()

    def test_init_creates_no_artifacts_or_graphs(self) -> None:
        produced = [p.relative_to(self.root).as_posix() for p in self.root.rglob("*")
                    if p.is_file() and p.parts[len(self.root.parts)] in
                    ("proposals", "sota-pool", "experiments", "paper", "implementations")
                    and p.name != ".gitkeep"]
        self.assertEqual(produced, [])
        self.assertFalse((self.root / ".papersmith" / "model_spec.json").exists())
        self.assertFalse((self.root / ".papersmith" / "novelty_graph.json").exists())

    def test_the_dashboard_of_a_fresh_workspace_shows_only_its_own(self) -> None:
        from skills._core.command_center import server
        app = server.create_app(self.root, history_store=None)
        routes = {r.path: r.endpoint for r in app.routes
                  if hasattr(r, "path") and "GET" in (getattr(r, "methods", None) or ())}
        bodies = {path: bytes(routes[path]().body).decode("utf-8")
                  for path in ("/api/model", "/api/model/math", "/api/atlas/novelty",
                               "/api/atlas/novelty/view", "/api/atlas/candidates/view")}
        for path, body in bodies.items():
            for marker in OLD_PROJECT_MARKERS:
                self.assertNotIn(marker, body.lower(), f"{path} shows {marker!r}")
        self.assertEqual(json.loads(bodies["/api/model/math"])["source"], "none")
        self.assertIn("Fresh Paper", bodies["/api/model"])


class ModelPanelTests(unittest.TestCase):
    STATIC = REPO / "skills" / "_core" / "command_center" / "static"

    def test_the_model_modules_are_drawn_from_data_and_escaped(self) -> None:
        page = (self.STATIC / "index.html").read_text(encoding="utf-8")
        for element in ("modelPillarGrid", "modelHypothesisGrid", "modelConceptLayers"):
            self.assertIn(f'id="{element}"', page)
        self.assertIn("if (window.renderModelModules) window.renderModelModules(data);", page)
        i18n_js = self.STATIC / "i18n.js"
        en_js = self.STATIC / "i18n" / "en.js"
        es_js = self.STATIC / "i18n" / "es.js"
        script = (
            "const fs=require('fs');const els={};"
            "global.window={localStorage:{getItem:()=>'es',setItem:()=>{}}};"
            "global.document={addEventListener(){},querySelectorAll:()=>[],getElementById:(id)=>els[id]||(els[id]={innerHTML:'',textContent:'',className:''})};"
            f"eval(fs.readFileSync({json.dumps(str(en_js))},'utf8'));"
            f"eval(fs.readFileSync({json.dumps(str(es_js))},'utf8'));"
            f"eval(fs.readFileSync({json.dumps(str(i18n_js))},'utf8'));"
            f"eval(fs.readFileSync({json.dumps(str(self.STATIC / 'model-panel.js'))},'utf8'));"
            "window.renderModelModules(JSON.parse(fs.readFileSync(0,'utf8')));"
            "console.log(JSON.stringify(els));"
        )
        spec = {"novelty": {"pillars": [{"name": "<img src=x onerror=1>", "color": "red;x:1"}]},
                "conceptual_map": {"layers": [{"layer": "L1", "desc": "d"}]}}
        out = json.loads(subprocess.run(["node", "-e", script], input=json.dumps(spec),
                                        capture_output=True, text=True, check=True,
                                        cwd=tempfile.gettempdir()).stdout)
        self.assertIn("&lt;img src=x onerror=1&gt;", out["modelPillarGrid"]["innerHTML"])
        self.assertNotIn("red;x:1", out["modelPillarGrid"]["innerHTML"])
        self.assertIn("L1", out["modelConceptLayers"]["innerHTML"])
        self.assertIn("Hipótesis pendientes", out["modelHypothesisGrid"]["innerHTML"])
        self.assertNotIn("modelPocGrid", out)

    def test_the_concept_map_tab_no_longer_carries_the_poc_section(self) -> None:
        """The PoC and its experiments live in the Experimentos tab, with their diagrams."""
        page = (self.STATIC / "index.html").read_text(encoding="utf-8")
        for gone in ('id="modelSecPoc"', 'id="modelPocGrid"', 'id="modelPocBadge"',
                     "filterModelView('poc'", "Experimentos de Prueba de Concepto (PoC)"):
            self.assertNotIn(gone, page)
        self.assertNotIn("modelPocGrid", (self.STATIC / "model-panel.js").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
