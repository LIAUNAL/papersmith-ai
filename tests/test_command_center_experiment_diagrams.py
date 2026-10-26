"""The Experimentos tab shows each product's experiment diagrams (S4).

A product carries one diagram entry per approval it holds -- the proof of
concept (`AGREED.md`) first, then the full experiments
(`Experimental_AGREED.md`) -- with the PNG and PDF that
`skills/experiment-diagrams` wrote under `<product>/diagrams/`, or the command
that draws them when they are still missing.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from skills._core.command_center import experiments_view

REPO = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO / "skills" / "_core" / "command_center" / "static" / "experiments-panel.js"


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class DiagramWorkspace:
    def __init__(self, case: unittest.TestCase) -> None:
        holder = tempfile.TemporaryDirectory()
        case.addCleanup(holder.cleanup)
        base = Path(holder.name).resolve()
        self.root = base / "ws"
        self.outside = base / "outside"
        self.outside.mkdir()
        products = self.root / "implementations" / "repo"
        self.poc = products / "PocModel"
        _write(self.poc / "AGREED.md", "agreed\n")
        _write(self.poc / "diagrams" / "poc.png", "png")
        _write(self.poc / "diagrams" / "poc.pdf", "%PDF-1.4")
        self.full = products / "FullModel"
        _write(self.full / "AGREED.md", "agreed\n")
        _write(self.full / "Experimental_AGREED.md", "agreed\n")
        _write(self.outside / "experiments.png", "png")
        (self.full / "diagrams").mkdir()
        os.symlink(self.outside / "experiments.png", self.full / "diagrams" / "experiments.png")


class DiagramViewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ws = DiagramWorkspace(self)
        view = experiments_view.get_experiments_view(self.ws.root)
        self.products = {p["name"]: p for p in view["products"]}

    def test_a_drawn_poc_diagram_is_listed_with_its_files(self) -> None:
        (entry,) = self.products["PocModel"]["diagrams"]
        self.assertEqual(entry["kind"], "poc")
        self.assertTrue(entry["approved"])
        self.assertEqual(entry["png"], "implementations/repo/PocModel/diagrams/poc.png")
        self.assertEqual(entry["pdf"], "implementations/repo/PocModel/diagrams/poc.pdf")

    def test_the_poc_comes_before_the_full_experiments(self) -> None:
        kinds = [d["kind"] for d in self.products["FullModel"]["diagrams"]]
        self.assertEqual(kinds, ["poc", "experiments"])

    def test_a_missing_diagram_offers_the_command_that_draws_it(self) -> None:
        poc = self.products["FullModel"]["diagrams"][0]
        self.assertIsNone(poc["png"])
        self.assertIn("diagram_cli.py derive --target repo --name FullModel --kind poc", poc["command"])
        self.assertIn("render --spec implementations/repo/FullModel/diagrams/poc.json", poc["command"])

    def test_a_diagram_linked_outside_the_workspace_is_not_shown(self) -> None:
        experiments = self.products["FullModel"]["diagrams"][1]
        self.assertIsNone(experiments["png"])

    def test_a_product_without_an_approval_has_no_diagrams(self) -> None:
        _write(self.ws.root / "implementations" / "repo" / "Draft" / "Results" / "x.txt", "x")
        view = experiments_view.get_experiments_view(self.ws.root)
        draft = next(p for p in view["products"] if p["name"] == "Draft")
        self.assertEqual(draft["diagrams"], [])


@unittest.skipUnless(shutil.which("node"), "node is required to run the panel renderer")
class DiagramRenderTests(unittest.TestCase):
    def render(self, view: dict) -> str:
        script = (
            "const fs=require('fs');global.window={};global.document={addEventListener(){}};"
            f"eval(fs.readFileSync({json.dumps(str(SCRIPT_PATH))},'utf8'));"
            "console.log(window.ExperimentsPanel.render(JSON.parse(fs.readFileSync(0,'utf8'))));"
        )
        return subprocess.run(["node", "-e", script], input=json.dumps(view), capture_output=True,
                              text=True, cwd=tempfile.gettempdir(), check=True).stdout

    def test_the_panel_shows_the_drawn_diagram_and_offers_the_missing_one(self) -> None:
        ws = DiagramWorkspace(self)
        view = experiments_view.get_experiments_view(ws.root)
        out = self.render(view)
        self.assertIn("Diagrama de la prueba de concepto", out)
        self.assertIn("Diagrama de los experimentos completos", out)
        self.assertIn("/api/artifact?path=implementations%2Frepo%2FPocModel%2Fdiagrams%2Fpoc.png", out)
        self.assertIn("Generar diagrama", out)
        self.assertIn("/experiment-diagrams", out)

    def test_diagram_fields_are_escaped(self) -> None:
        ws = DiagramWorkspace(self)
        view = experiments_view.get_experiments_view(ws.root)
        view["products"][0]["diagrams"][0]["command"] = "<img src=x onerror=1>"
        self.assertNotIn("<img src=x", self.render(view))


if __name__ == "__main__":
    unittest.main()
