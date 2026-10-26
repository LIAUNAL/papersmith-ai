"""`GET /api/doctor` and the "Smith Doctor" tab of the dashboard."""

from __future__ import annotations

import contextlib
import io
import json
import re
import tempfile
import unittest
from pathlib import Path

from papersmith.cli import main
from papersmith.core import init as init_module
from skills._core.command_center import server

REPO = Path(__file__).resolve().parents[1]
STATIC = REPO / "skills/_core/command_center/static"
PAGE = (STATIC / "index.html").read_text(encoding="utf-8")


def _routes(app) -> dict:
    return {route.path: route.endpoint for route in app.routes
            if hasattr(route, "path") and hasattr(route, "endpoint")}


class DoctorRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.workspace = Path(holder.name).resolve() / "doctor-ui"
        init_module.initialize(self.workspace, run_npm=False, run_env=False)

    def test_api_doctor_returns_the_same_rows_as_the_cli(self) -> None:
        app = server.create_app(self.workspace, history_store=None)
        payload = json.loads(bytes(_routes(app)["/api/doctor"](fresh=True).body))
        self.assertEqual(set(payload), {"summary", "rows"})
        status = json.loads(bytes(_routes(app)["/api/status"]().body))
        flows = [r for r in payload["rows"] if r["area"] == "flows"]
        self.assertEqual([r["item"] for r in flows], [f["name"] for f in status["fases"]])

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            main(["doctor", str(self.workspace), "--json"])
        cli = json.loads(out.getvalue())
        self.assertEqual(payload["rows"], cli["rows"])
        self.assertEqual(payload["summary"]["state"], cli["summary"]["state"])

    def test_api_doctor_is_cached_until_asked_fresh(self) -> None:
        app = server.create_app(self.workspace, history_store=None)
        route = _routes(app)["/api/doctor"]
        first = json.loads(bytes(route().body))
        second = json.loads(bytes(route().body))
        self.assertEqual(first["summary"]["generated_at"], second["summary"]["generated_at"])


class DoctorTabTests(unittest.TestCase):
    def test_the_tab_comes_right_after_telemetria(self) -> None:
        tabs = re.findall(r"onclick=\"navigateTab\('([a-z]+)'\)\">([^<]*)<", PAGE)
        names = [name for name, _ in tabs]
        self.assertEqual(names[-2:], ["telemetria", "doctor"])
        self.assertEqual(dict(tabs)["doctor"], "Smith Doctor")

    def test_the_pane_allow_list_hook_and_script_are_wired(self) -> None:
        self.assertTrue('<div id="pane-doctor" class="tab-pane">' in PAGE, '<div id="pane-doctor" class="tab-pane">')
        self.assertTrue('id="doctorPanel"' in PAGE, 'id="doctorPanel"')
        allow = re.search(r"\[('pipeline'[^\]]*)\]\.includes\(hash\)", PAGE)
        self.assertIsNotNone(allow)
        self.assertIn("'doctor'", allow.group(1))
        self.assertTrue('<script src="./doctor-panel.js' in PAGE, '<script src="./doctor-panel.js')
        hook = PAGE.split("function navigateTab(tabId)", 1)[1].split("\n    }\n", 1)[0]
        self.assertIn("tabId === 'doctor'", hook)
        self.assertIn("refreshDoctorPanel", hook)

    def test_the_panel_fetches_the_route_and_escapes_text(self) -> None:
        script = (STATIC / "doctor-panel.js").read_text(encoding="utf-8")
        self.assertIn("/api/doctor", script)
        self.assertIn("fresh=1", script)
        self.assertIn("Volver a revisar", script)
        self.assertIn("&amp;", script)
        self.assertIn("window.refreshDoctorPanel", script)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
