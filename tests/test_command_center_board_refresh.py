"""The board refresh: regenerate the derived artifacts, then say where the
project stands (current phase, missing steps, open gates).

``smith ui`` runs it once in the background when the server starts, and the
topbar's "Update board" button runs it on demand through
``POST /api/board/refresh``.
"""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from skills._core.command_center import board_refresh, server
from papersmith.core import ui as ui_command


def _routes(app) -> dict:
    return {route.path: route.endpoint for route in app.routes
            if hasattr(route, "path") and hasattr(route, "endpoint")}


def _json(response) -> dict:
    return json.loads(bytes(response.body).decode("utf-8"))


class _FakeRequest:
    def __init__(self, headers: dict | None = None) -> None:
        self.headers = headers or {}


def _status(fases: list[dict], gates: list[dict]) -> dict:
    return {"fases": fases, "gates": gates}


PHASES = [
    {"id": "Fase 1", "stage_id": "harness", "name": "Phase 1: Harness", "status": "PASS",
     "detail": "ok", "subfases": [{"id": "1.1", "name": "Workspace", "status": "PASS", "detail": ""}],
     "unlocked": True, "blocked_by": None},
    {"id": "Fase 2", "stage_id": "plausibility", "name": "Phase 2: Plausibility", "status": "ACTIVE",
     "detail": "Atlas pending", "unlocked": True, "blocked_by": None,
     "subfases": [{"id": "2.1", "name": "SOTA scouting", "status": "PASS", "detail": "25 refs"},
                  {"id": "2.2", "name": "3D atlas", "status": "PENDING", "detail": "atlas.html missing"}]},
    {"id": "Fase 3", "stage_id": "ingestion", "name": "Phase 3: Ingestion", "status": "LOCKED",
     "detail": "", "subfases": [], "unlocked": False, "blocked_by": "Fase 2"},
    {"id": "Fase 11", "stage_id": "audit", "name": "Phase 11: Audit", "status": "PENDING",
     "detail": "Cross-cutting audit pending", "subfases": [], "unlocked": True, "blocked_by": None},
]


class SummarizeTests(unittest.TestCase):
    def test_the_current_phase_is_the_first_unpassed_one_with_its_missing_steps(self) -> None:
        gates = [{"id": "G-EXP-POC", "name": "PoC gate", "status": "PENDING", "phase": "Fase 5"},
                 {"id": "G1", "name": "Writing readiness", "status": "PASS", "phase": "Fase 6"}]
        summary = board_refresh.summarize(_status(PHASES, gates))

        self.assertEqual(summary["current"]["id"], "Fase 2")
        self.assertEqual(summary["current"]["name"], "Phase 2: Plausibility")
        self.assertEqual(summary["current"]["detail"], "Atlas pending")
        self.assertEqual([step["id"] for step in summary["missing"]], ["2.2"])
        self.assertEqual(summary["missing"][0]["detail"], "atlas.html missing")
        self.assertEqual(summary["phases_completed"], 1)
        self.assertEqual(summary["phases_total"], 4)
        self.assertEqual([gate["id"] for gate in summary["open_gates"]], ["G-EXP-POC"])
        self.assertEqual(summary["blocked"], [{"id": "Fase 3", "name": "Phase 3: Ingestion",
                                               "blocked_by": "Fase 2"}])
        self.assertEqual(summary["tone"], "info")

    def test_a_failed_gate_raises_an_alert(self) -> None:
        gates = [{"id": "G1", "name": "Writing readiness", "status": "FAIL", "phase": "Fase 6"}]
        summary = board_refresh.summarize(_status(PHASES, gates))

        self.assertEqual(summary["tone"], "alert")
        self.assertEqual(summary["failed_gates"][0]["id"], "G1")

    def test_a_failed_artifact_raises_a_warning(self) -> None:
        artifacts = [{"id": "atlas", "state": "failed", "detail": "check_atlas.py refused"}]
        summary = board_refresh.summarize(_status(PHASES, []), artifacts)

        self.assertEqual(summary["tone"], "warn")
        self.assertEqual(summary["failed_artifacts"], ["atlas"])

    def test_every_phase_passed_is_done(self) -> None:
        fases = [dict(phase, status="PASS", subfases=[]) for phase in PHASES]
        summary = board_refresh.summarize(_status(fases, [{"id": "G1", "status": "PASS"}]))

        self.assertIsNone(summary["current"])
        self.assertEqual(summary["missing"], [])
        self.assertEqual(summary["tone"], "done")

    def test_the_transversal_audit_is_never_the_current_phase(self) -> None:
        fases = [dict(phase, status="PASS") if phase["stage_id"] != "audit" else phase
                 for phase in PHASES]
        summary = board_refresh.summarize(_status(fases, []))

        self.assertIsNone(summary["current"])
        self.assertEqual(summary["tone"], "done")


class RefreshArtifactsTests(unittest.TestCase):
    def new_workspace(self) -> Path:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        return Path(holder.name).resolve()

    def test_an_empty_workspace_skips_what_it_has_no_input_for(self) -> None:
        root = self.new_workspace()
        results = board_refresh.refresh_artifacts(root)

        by_id = {item["id"]: item for item in results}
        self.assertEqual(list(by_id), list(board_refresh.ARTIFACT_IDS))
        self.assertEqual(by_id["atlas"]["state"], "skipped")
        self.assertEqual(by_id["atlas_manuscript"]["state"], "skipped")
        self.assertEqual(by_id["manuscript_graph"]["state"], "skipped")
        self.assertEqual(by_id["novelty_graph"]["state"], "skipped")
        self.assertEqual(list(root.iterdir()), [])

    def test_a_generator_that_raises_is_reported_and_the_rest_still_run(self) -> None:
        root = self.new_workspace()
        with mock.patch.object(board_refresh.atlas_build, "build", side_effect=RuntimeError("boom")):
            results = board_refresh.refresh_artifacts(root)

        by_id = {item["id"]: item for item in results}
        self.assertEqual(by_id["atlas"]["state"], "failed")
        self.assertIn("boom", by_id["atlas"]["detail"])
        self.assertIn("manuscript_graph", by_id)

    def test_a_rendered_atlas_is_ok(self) -> None:
        root = self.new_workspace()
        (root / "sota-pool").mkdir()
        (root / "sota-pool" / "atlas.json").write_text("{}", encoding="utf-8")
        rendered = {"ok": True, "stage": "rendered", "detail": "atlas rendered",
                    "systems": 3, "planets": 9, "links": 4}
        with mock.patch.object(board_refresh.atlas_build, "build", return_value=rendered):
            results = board_refresh.refresh_artifacts(root)

        atlas = next(item for item in results if item["id"] == "atlas")
        self.assertEqual(atlas["state"], "ok")

    def test_the_health_callable_is_forced(self) -> None:
        root = self.new_workspace()
        calls = []
        results = board_refresh.refresh_artifacts(root, health=lambda: calls.append(1) or {})

        self.assertEqual(calls, [1])
        self.assertEqual(next(i for i in results if i["id"] == "health")["state"], "ok")


class BoardEndpointTests(unittest.TestCase):
    def new_workspace(self) -> Path:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        root = Path(holder.name).resolve()
        (root / "sections").mkdir(parents=True)
        (root / "paper").mkdir()
        return root

    def test_the_refresh_regenerates_and_reports_the_status(self) -> None:
        root = self.new_workspace()
        app = server.create_app(root)
        response = _routes(app)["/api/board/refresh"](_FakeRequest())
        payload = _json(response)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual([item["id"] for item in payload["artifacts"]], list(board_refresh.ARTIFACT_IDS))
        self.assertIn("current", payload["summary"])
        self.assertGreater(payload["summary"]["phases_total"], 0)
        self.assertIn(payload["summary"]["tone"], ("info", "warn", "alert", "done"))
        self.assertIsNotNone(payload["finished_at"])

    def test_the_refresh_refuses_another_origin(self) -> None:
        root = self.new_workspace()
        app = server.create_app(root)
        request = _FakeRequest({"origin": "https://evil.example", "host": "127.0.0.1:8080"})
        response = _routes(app)["/api/board/refresh"](request)

        self.assertEqual(response.status_code, 403)

    def test_a_refresh_already_running_answers_busy(self) -> None:
        root = self.new_workspace()
        app = server.create_app(root)
        app.state.board_refresh_lock.acquire()
        self.addCleanup(app.state.board_refresh_lock.release)
        response = _routes(app)["/api/board/refresh"](_FakeRequest())

        self.assertEqual(response.status_code, 409)
        self.assertTrue(_json(response)["busy"])

    def test_the_summary_reports_the_last_refresh(self) -> None:
        root = self.new_workspace()
        app = server.create_app(root)
        before = _json(_routes(app)["/api/board/summary"]())
        self.assertIsNone(before["last_refresh"])
        self.assertIn("current", before["summary"])

        _routes(app)["/api/board/refresh"](_FakeRequest())
        after = _json(_routes(app)["/api/board/summary"]())
        self.assertEqual([item["id"] for item in after["last_refresh"]["artifacts"]],
                         list(board_refresh.ARTIFACT_IDS))

    def test_the_summary_speaks_spanish_on_request(self) -> None:
        from fastapi.testclient import TestClient

        root = self.new_workspace()
        client = TestClient(server.create_app(root, allowed_hosts=["testserver"]))
        english = client.get("/api/board/summary").json()["summary"]["current"]["name"]
        spanish = client.get("/api/board/summary?lang=es").json()["summary"]["current"]["name"]

        self.assertTrue(english.startswith("Phase 1"))
        self.assertTrue(spanish.startswith("Fase 1"))


class StartupRefreshTests(unittest.TestCase):
    def run_main(self, *extra: str) -> list[str]:
        started: list[str] = []
        real_thread = threading.Thread

        def fake_thread(*args, **kwargs):
            started.append(kwargs.get("name", ""))
            return real_thread(target=lambda: None)

        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        with mock.patch.object(server.threading, "Thread", side_effect=fake_thread), \
                mock.patch("uvicorn.run"):
            server.main(["--root", holder.name, "--no-browser", "--no-terminal", *extra])
        return started

    def test_the_server_refreshes_the_board_when_it_starts(self) -> None:
        self.assertIn("board-refresh", self.run_main())

    def test_no_refresh_keeps_the_read_only_start(self) -> None:
        started = self.run_main("--no-refresh")
        self.assertNotIn("board-refresh", started)
        self.assertIn("warm-caches", started)

    def test_smith_ui_forwards_no_refresh_only_when_given(self) -> None:
        plain = ui_command.build_server_argv(Path("/tmp/paper"), "127.0.0.1", 8123, no_browser=True)
        quiet = ui_command.build_server_argv(Path("/tmp/paper"), "127.0.0.1", 8123, no_browser=True,
                                             no_refresh=True)
        self.assertNotIn("--no-refresh", plain)
        self.assertIn("--no-refresh", quiet)


if __name__ == "__main__":
    unittest.main()


STATIC = Path(server.__file__).resolve().parent / "static"
PAGE = (STATIC / "index.html").read_text(encoding="utf-8")

MESSAGE_HARNESS = r"""
const fs = require('fs');
const store = { 'papersmith-lang': 'es' };
global.localStorage = { getItem: (k) => store[k] ?? null, setItem: (k, v) => { store[k] = v; } };
global.document = { readyState: 'complete', getElementById: () => null, addEventListener() {},
                    documentElement: {}, querySelectorAll: () => [] };
global.window = { localStorage: global.localStorage, sessionStorage: global.localStorage };
global.fetch = async () => ({ ok: false });
eval(fs.readFileSync(process.argv[2], 'utf8'));
eval(fs.readFileSync(process.argv[3], 'utf8'));
eval(fs.readFileSync(process.argv[4], 'utf8'));
global.t = window.t;
eval(fs.readFileSync(process.argv[1], 'utf8'));
const result = JSON.parse(fs.readFileSync(0, 'utf8'));
console.log(JSON.stringify(window.boardRefresh.message(result, 'manual')));
process.exit(0);
"""


@unittest.skipUnless(__import__("shutil").which("node"), "node is not installed")
class BoardMessageTests(unittest.TestCase):
    def message(self, result: dict) -> dict:
        import subprocess

        done = subprocess.run(
            ["node", "-e", MESSAGE_HARNESS, str(STATIC / "board-refresh.js"),
             str(STATIC / "i18n" / "en.js"), str(STATIC / "i18n" / "es.js"), str(STATIC / "i18n.js")],
            input=json.dumps(result), capture_output=True, text=True, timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout.strip().splitlines()[-1])

    def test_the_message_names_the_phase_its_missing_steps_gates_and_artifacts(self) -> None:
        gates = [{"id": "G-EXP-POC", "name": "PoC gate", "status": "PENDING", "phase": "Fase 5"}]
        artifacts = [{"id": "atlas", "state": "ok", "detail": ""},
                     {"id": "manuscript_graph", "state": "failed", "detail": "bad yaml"},
                     {"id": "novelty_graph", "state": "skipped", "detail": ""}]
        summary = board_refresh.summarize(_status(PHASES, gates), artifacts)
        out = self.message({"summary": summary, "artifacts": artifacts})

        self.assertEqual(out["tone"], "warn")
        html = out["html"]
        self.assertIn("Tablero actualizado con advertencias: el proyecto está en Phase 2: Plausibility", html)
        self.assertIn("Fase actual: Phase 2: Plausibility (en curso)", html)
        self.assertIn("Pasos que aún faltan en esta fase:", html)
        self.assertIn("<strong>2.2</strong> 3D atlas", html)
        self.assertIn("atlas.html missing", html)
        self.assertIn("Compuertas pendientes: G-EXP-POC · PoC gate", html)
        self.assertIn("Regenerados: atlas SOTA", html)
        self.assertIn("No se pudieron regenerar: grafo del manuscrito: bad yaml", html)
        self.assertIn("Aún no disponibles (falta su entrada): grafo de novedad", html)
        self.assertIn("1 de 4 fases aprobadas", html)

    def test_a_failed_gate_is_an_alert_and_the_text_is_escaped(self) -> None:
        gates = [{"id": "G1", "name": "<b>Writing</b>", "status": "FAIL", "phase": "Fase 6"}]
        out = self.message({"summary": board_refresh.summarize(_status(PHASES, gates)), "artifacts": []})

        self.assertEqual(out["tone"], "alert")
        self.assertIn("Atención: una compuerta falló", out["html"])
        self.assertIn("&lt;b&gt;Writing&lt;/b&gt;", out["html"])
        self.assertNotIn("<b>Writing</b>", out["html"])


class BoardButtonPageTests(unittest.TestCase):
    def test_the_topbar_carries_the_update_board_button_and_its_report(self) -> None:
        topbar = PAGE[PAGE.index('<div class="topbar__actions">'):PAGE.index("</header>")]
        self.assertIn('id="boardRefreshBtn"', topbar)
        self.assertIn('onclick="refreshBoard()"', topbar)
        self.assertIn('data-i18n="board.refreshButton"', topbar)
        self.assertIn('<div id="boardStatus" class="board-status" role="status"', PAGE)
        self.assertIn('<script src="./board-refresh.js?v=', PAGE)
        self.assertIn("window.reloadBoardViews", PAGE)
