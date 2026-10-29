"""`GET /api/doctor` and the "Smith Doctor" tab of the dashboard."""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from papersmith.cli import main
from papersmith.core import init as init_module
from papersmith.core import ui
from skills._core.command_center import doctor_view, server

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


    def test_an_expired_report_is_served_while_one_refresh_runs(self) -> None:
        calls = []

        def build(*_args, **_kwargs):
            calls.append(None)
            return {"summary": {"n": len(calls)}, "rows": []}

        with mock.patch.object(server.doctor_view, "get_doctor_view", side_effect=build), \
                mock.patch.object(server, "DOCTOR_TTL_SECONDS", 0.0):
            app = server.create_app(self.workspace, history_store=None)
            route = _routes(app)["/api/doctor"]
            self.assertEqual(json.loads(bytes(route().body))["summary"]["n"], 1)
            self.assertEqual(json.loads(bytes(route().body))["summary"]["n"], 1)
            deadline = time.monotonic() + 10
            while len(calls) < 2 and time.monotonic() < deadline:
                time.sleep(0.02)
            time.sleep(0.05)
            self.assertEqual(json.loads(bytes(route().body))["summary"]["n"], 2)
            self.assertEqual(json.loads(bytes(route(fresh=True).body))["summary"]["n"], len(calls))

    def test_startup_warming_fills_the_doctor_report(self) -> None:
        app = server.create_app(self.workspace, history_store=None)
        with mock.patch.object(server.experiments_view, "get_experiments_view"), \
                mock.patch.object(server.ai_transcripts, "read_all"):
            server.warm_caches(self.workspace, app.state.warm_doctor)
        with mock.patch.object(server.doctor_view, "get_doctor_view",
                               side_effect=AssertionError("not cached")):
            payload = json.loads(bytes(_routes(app)["/api/doctor"]().body))
        self.assertIn("rows", payload)

class DoctorTabTests(unittest.TestCase):
    def test_the_tab_comes_right_after_telemetria(self) -> None:
        tabs = re.findall(r"onclick=\"navigateTab\('([a-z]+)'\)\"[^>]*>([^<]*)<", PAGE)
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
        self.assertTrue("Volver a revisar" in script or "doctor.recheck" in script)
        self.assertIn("&amp;", script)
        self.assertIn("window.refreshDoctorPanel", script)


class DoctorWithoutPapersmithTests(unittest.TestCase):
    """The dashboard runs under the workspace's environment, which does not
    hold the `papersmith` package: the CLI lives in its own (pipx) venv."""

    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.workspace = Path(holder.name).resolve() / "doctor-env"
        init_module.initialize(self.workspace, run_npm=False, run_env=False)
        self.backend = {"wiring": {}, "phases": [], "phases_error": None}

    def _view(self, cli_python: str | None) -> dict:
        env = {k: v for k, v in os.environ.items() if k != doctor_view.CLI_PYTHON_ENV}
        if cli_python is not None:
            env[doctor_view.CLI_PYTHON_ENV] = cli_python
        with mock.patch.dict(sys.modules, {"papersmith.core.doctor": None}), \
                mock.patch.dict(os.environ, env, clear=True):
            return doctor_view.get_doctor_view(self.workspace, **self.backend)

    def test_rows_come_from_the_cli_interpreter_when_papersmith_is_not_importable(self) -> None:
        payload = self._view(sys.executable)
        areas = {row["area"] for row in payload["rows"]}
        self.assertIn("tools", areas)
        self.assertFalse(any("not importable" in row["detail"] for row in payload["rows"]))
        self.assertEqual(payload["summary"]["workspace"], str(self.workspace))

    def test_without_a_cli_interpreter_the_panel_says_so_in_one_warn_row(self) -> None:
        payload = self._view(None)
        self.assertEqual(payload["summary"]["state"], "warn")
        self.assertEqual(len(payload["rows"]), 1)
        self.assertIn("papersmith is not importable", payload["rows"][0]["detail"])

    def test_a_broken_cli_interpreter_degrades_to_one_warn_row(self) -> None:
        payload = self._view(str(self.workspace / "no-such-python"))
        self.assertEqual(payload["summary"]["state"], "warn")
        self.assertEqual(len(payload["rows"]), 1)
        self.assertIn("no-such-python", payload["rows"][0]["detail"])

    def test_smith_ui_hands_its_own_interpreter_to_the_dashboard(self) -> None:
        env = ui._child_env(self.workspace)
        self.assertEqual(env[doctor_view.CLI_PYTHON_ENV], sys.executable)
        self.assertEqual(env["PYTHONDONTWRITEBYTECODE"], "1")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
