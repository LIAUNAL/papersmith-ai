"""Tests for the novelty & findings command-center endpoints and gates."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from fastapi.testclient import TestClient

from skills._core.command_center.server import create_app
from skills._core.results import novelty_gate

STATIC = Path(__file__).resolve().parents[1] / "skills" / "_core" / "command_center" / "static"
PANEL_PATH = STATIC / "novelty-panel.js"
CATALOGUES = (STATIC / "i18n" / "en.js", STATIC / "i18n" / "es.js")

# Terms of one project's findings that the forge must never carry (case-insensitive).
PROJECT_TERMS = ("entangle", "entrelazamiento", "barren", "groupkfold", "L <= 3", "p = 1.0")


class CommandCenterNoveltyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / ".papersmith").mkdir(parents=True, exist_ok=True)
        app = create_app(self.root)
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_novelty_status_endpoint_returns_overview(self) -> None:
        res = self.client.get("/api/novelty/status")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["gate"]["status"], "pending")
        self.assertIn("hypotheses", data)
        self.assertIn("rigor_audit", data)

    def test_novelty_decision_endpoint_approves(self) -> None:
        res = self.client.post("/api/novelty/decision", json={
            "action": "approve",
            "notes": "Empirical results validate novelty",
            "actor": "reviewer"
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["gate"]["status"], "approved")
        self.assertEqual(data["gate"]["rationale"], "Empirical results validate novelty")

        # Verify status endpoint reflects approval
        res2 = self.client.get("/api/novelty/status")
        self.assertEqual(res2.json()["gate"]["status"], "approved")

    def test_novelty_decision_endpoint_iterates(self) -> None:
        res = self.client.post("/api/novelty/decision", json={
            "action": "iterate_experiments",
            "notes": "More ablations required"
        })
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["gate"]["status"], "iterating_experiments")

    def test_novelty_decision_invalid_action_returns_422(self) -> None:
        res = self.client.post("/api/novelty/decision", json={
            "action": "unknown_action"
        })
        self.assertEqual(res.status_code, 422)
        self.assertEqual(res.json()["error"], "INVALID_ACTION")

    def test_api_status_includes_g_novelty_gate(self) -> None:
        res = self.client.get("/api/status")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        gates = data.get("gates", [])
        g_nov = next((g for g in gates if g.get("id") == "G-NOVELTY"), None)
        self.assertIsNotNone(g_nov)
        self.assertEqual(g_nov["name"], "Novelty & Findings Gate")


class SobrietyBoxRenderTests(unittest.TestCase):
    """The sobriety box lists what the product discussions record, nothing else."""

    HEADINGS = {
        "en": "Sobriety: limits and unsupported claims",
        "es": "Sobriedad: límites y afirmaciones no soportadas",
    }
    EMPTY = {
        "en": "No limitations or unsupported hypotheses recorded in Results/discussion.json.",
        "es": "No hay limitaciones ni hipótesis no soportadas registradas en Results/discussion.json.",
    }

    def render(self, overview: dict, lang: str) -> str:
        script = (
            "const fs=require('fs');"
            "const root={innerHTML:''};"
            f"global.window={{localStorage:{{getItem:()=>{json.dumps(lang)},setItem:()=>{{}}}},"
            "location:{hash:''},addEventListener(){}};"
            "global.document={addEventListener(){},querySelectorAll:()=>[],getElementById:(id)=>id==='noveltyRoot'?root:null};"
            f"eval(fs.readFileSync({json.dumps(str(CATALOGUES[0]))},'utf8'));"
            f"eval(fs.readFileSync({json.dumps(str(CATALOGUES[1]))},'utf8'));"
            f"eval(fs.readFileSync({json.dumps(str(STATIC / 'i18n.js'))},'utf8'));"
            f"eval(fs.readFileSync({json.dumps(str(PANEL_PATH))},'utf8'));"
            "window.NoveltyPanel.render(JSON.parse(fs.readFileSync(0,'utf8')));"
            "console.log(root.innerHTML);"
        )
        return subprocess.run(["node", "-e", script], input=json.dumps(overview), capture_output=True,
                              text=True, cwd=tempfile.gettempdir(), check=True).stdout

    def box(self, html: str) -> str:
        start = html.index('id="noveltySobriety"')
        return html[start:html.index("</section>", start)]

    def overview_from_disk(self) -> dict:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        folder = Path(tmp.name) / "implementations" / "repo" / "Prod<b>A" / "Results"
        folder.mkdir(parents=True)
        (folder / "discussion.json").write_text(json.dumps({
            "limitations": ["Only <script>alert(1)</script> one site", "Short training budget"],
            "hypotheses": [
                {"id": "H1", "statement": "Supported claim marker", "verdict": "supported", "rationale": "ok-rationale"},
                {"id": "H2", "statement": "Gain over <i>baseline</i> " + "z" * 400, "verdict": "not_supported",
                 "rationale": "No gain <img src=x onerror=alert(1)>"},
                {"id": "H3", "statement": "Undecided claim", "verdict": "inconclusive", "rationale": "Too few seeds"},
            ],
            "novelty": {"claim": "A claim", "verdict": "not_justified", "rationale": "Prior work covers it"},
        }), encoding="utf-8")
        return novelty_gate.get_novelty_overview(Path(tmp.name))

    def test_lists_limitations_unsupported_hypotheses_and_novelty_verdict(self) -> None:
        overview = self.overview_from_disk()
        for lang, labels in {"en": ("not supported", "inconclusive", "not justified"),
                             "es": ("no soportada", "no concluyente", "no justificada")}.items():
            with self.subTest(lang=lang):
                box = self.box(self.render(overview, lang))
                self.assertIn(self.HEADINGS[lang], box)
                self.assertNotIn(self.EMPTY[lang], box)
                for text in ("one site", "Short training budget", "H2", "H3", "No gain", "Too few seeds",
                             "Prior work covers it", *labels):
                    self.assertIn(text, box)
                self.assertNotIn("Supported claim marker", box)
                self.assertNotIn("ok-rationale", box)
                self.assertNotIn("z" * 200, box)  # statement clipped

    def test_everything_from_the_discussion_is_escaped(self) -> None:
        box = self.box(self.render(self.overview_from_disk(), "en"))
        self.assertNotIn("<script>alert(1)</script>", box)
        self.assertNotIn("<img", box)
        self.assertNotIn("<i>baseline", box)
        self.assertNotIn("<b>A", box)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", box)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", box)
        self.assertIn("Prod&lt;b&gt;A", box)

    def test_empty_state_is_generic(self) -> None:
        overview = novelty_gate.get_novelty_overview(Path(tempfile.gettempdir()) / "papersmith-no-such-workspace")
        for lang in ("en", "es"):
            with self.subTest(lang=lang):
                box = self.box(self.render(overview, lang))
                self.assertIn(self.HEADINGS[lang], box)
                self.assertIn(self.EMPTY[lang], box)
                self.assertNotIn("<li", box)

    def test_supported_findings_alone_leave_the_box_empty(self) -> None:
        overview = {"hypotheses": [{"id": "H1", "statement": "s", "verdict": "supported"}],
                    "discussions": [{"product": "P", "verdict": "justified", "rationale": "r"}], "limitations": []}
        self.assertIn(self.EMPTY["en"], self.box(self.render(overview, "en")))

    def test_neither_panel_nor_catalogues_name_the_project_terms(self) -> None:
        for path in (PANEL_PATH, *CATALOGUES, Path(novelty_gate.__file__)):
            text = path.read_text(encoding="utf-8").lower()
            for term in PROJECT_TERMS:
                with self.subTest(file=path.name, term=term):
                    self.assertNotIn(term.lower(), text)
        for key in ("sobriety_entanglement", "sobriety_leakage", "sobriety_plateaus"):
            self.assertNotIn(key, PANEL_PATH.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
