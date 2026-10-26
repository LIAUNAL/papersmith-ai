"""The Experimentos tab shows each product's experiment diagrams (S4).

A product carries one diagram entry per approval it holds -- the proof of
concept (`AGREED.md`) first, then the full experiments
(`Experimental_AGREED.md`) -- with the PNG and PDF that
`skills/experiment-diagrams` wrote under `<product>/diagrams/`, or the command
that draws them when they are still missing.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from skills._core.command_center import experiments_view, server

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

    def test_each_diagram_carries_its_validation_state(self) -> None:
        self.assertEqual(self.products["PocModel"]["diagrams"][0]["validation"], "pending")
        self.assertEqual(self.products["FullModel"]["diagrams"][0]["validation"], "absent")

    def test_a_missing_diagram_offers_the_command_that_draws_it_again_with_force(self) -> None:
        drawn = self.products["PocModel"]["diagrams"][0]
        self.assertIn("--kind poc --force", drawn["command"])

    def test_a_product_without_an_approval_has_no_diagrams(self) -> None:
        _write(self.ws.root / "implementations" / "repo" / "Draft" / "Results" / "x.txt", "x")
        view = experiments_view.get_experiments_view(self.ws.root)
        draft = next(p for p in view["products"] if p["name"] == "Draft")
        self.assertEqual(draft["diagrams"], [])


class _Req:
    def __init__(self, body, origin: str | None = "http://127.0.0.1:8765") -> None:
        self.body = body
        self.headers = {"host": "127.0.0.1:8765"}
        if origin is not None:
            self.headers["origin"] = origin

    async def json(self):
        return self.body


class DiagramValidationRouteTests(unittest.TestCase):
    """`POST /api/experiments/diagrams/validate`: the operator's button."""

    def setUp(self) -> None:
        self.ws = DiagramWorkspace(self)
        app = server.create_app(self.ws.root, history_store=None)
        self.route = next(r.endpoint for r in app.routes
                          if getattr(r, "path", None) == "/api/experiments/diagrams/validate")

    def post(self, body, **kwargs) -> tuple[int, dict]:
        response = asyncio.run(self.route(_Req(body, **kwargs)))
        return response.status_code, json.loads(bytes(response.body))

    def state(self, name: str, index: int = 0) -> str:
        view = experiments_view.get_experiments_view(self.ws.root)
        product = next(p for p in view["products"] if p["name"] == name)
        return product["diagrams"][index]["validation"]

    def test_the_button_records_the_validation_of_the_drawn_png(self) -> None:
        code, payload = self.post({"repo": "repo", "name": "PocModel", "kind": "poc"})
        self.assertEqual(code, 200, payload)
        self.assertTrue(payload["ok"])
        record = json.loads((self.ws.poc / "diagrams" / "poc.validated.json").read_text())
        self.assertEqual(record["kind"], "poc")
        self.assertEqual(len(record["png_sha256"]), 64)
        self.assertEqual(self.state("PocModel"), "validated")

    def test_a_request_without_the_dashboard_origin_is_refused(self) -> None:
        for origin in (None, "http://evil.example"):
            with self.subTest(origin=origin):
                code, _ = self.post({"repo": "repo", "name": "PocModel", "kind": "poc"}, origin=origin)
                self.assertEqual(code, 403)
        self.assertFalse((self.ws.poc / "diagrams" / "poc.validated.json").exists())

    def test_a_diagram_not_drawn_yet_cannot_be_validated(self) -> None:
        code, payload = self.post({"repo": "repo", "name": "FullModel", "kind": "poc"})
        self.assertEqual(code, 409, payload)
        self.assertFalse((self.ws.full / "diagrams" / "poc.validated.json").exists())

    def test_an_unknown_product_or_kind_is_refused(self) -> None:
        for body in ({"repo": "repo", "name": "Nobody", "kind": "poc"},
                     {"repo": "../..", "name": "PocModel", "kind": "poc"},
                     {"repo": "repo", "name": "PocModel", "kind": "experiments"},
                     {"repo": "repo", "name": "PocModel", "kind": "other"}):
            with self.subTest(body=body):
                code, _ = self.post(body)
                self.assertIn(code, (404, 409, 422))
        self.assertFalse((self.ws.poc / "diagrams" / "poc.validated.json").exists())


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

    def test_a_drawn_diagram_offers_validation_then_shows_it_validated(self) -> None:
        ws = DiagramWorkspace(self)
        view = experiments_view.get_experiments_view(ws.root)
        out = self.render(view)
        self.assertIn("Validar diagrama", out)
        self.assertIn('data-diagram-validate="poc"', out)
        poc = next(p for p in view["products"] if p["name"] == "PocModel")
        poc["diagrams"][0]["validation"] = "validated"
        out = self.render(view)
        self.assertIn("VALIDADO", out)
        self.assertIn("Regenerar diagrama", out)

    def test_diagram_fields_are_escaped(self) -> None:
        ws = DiagramWorkspace(self)
        view = experiments_view.get_experiments_view(ws.root)
        view["products"][0]["diagrams"][0]["command"] = "<img src=x onerror=1>"
        self.assertNotIn("<img src=x", self.render(view))


if __name__ == "__main__":
    unittest.main()
