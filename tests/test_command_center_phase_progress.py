"""A phase is verified from evidence on disk, unlocks the next one when it
passes, and the audit phase records a verdict the dashboard can check."""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from skills._core.command_center import phase_actions, server


class Req:
    def __init__(self, body):
        self.body = body
        self.headers = {}  # origin_is_same reads it; no Origin header, as from curl

    async def json(self):
        return self.body


class PhaseProgressTests(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.root = Path(holder.name).resolve() / "fresh-paper"
        self.root.mkdir()
        self.app = server.create_app(self.root, history_store=None)

    def route(self, path: str, method: str = "GET"):
        return next(r.endpoint for r in self.app.routes
                    if getattr(r, "path", None) == path and method in (getattr(r, "methods", None) or ()))

    def fases(self) -> dict:
        status = json.loads(bytes(self.route("/api/status")().body))
        return {f["stage_id"]: f for f in status["fases"]}

    def harness(self) -> None:
        (self.root / ".papersmith").mkdir(exist_ok=True)
        (self.root / "papersmith.yaml").write_text("title: Fresh\n", encoding="utf-8")

    def test_a_phase_is_locked_until_its_prerequisite_passes(self) -> None:
        fases = self.fases()
        self.assertTrue(fases["harness"]["unlocked"])
        self.assertTrue(fases["audit"]["unlocked"])
        self.assertFalse(fases["plausibility"]["unlocked"])
        self.assertEqual(fases["plausibility"]["blocked_by"], "Fase 1")
        self.harness()
        fases = self.fases()
        self.assertEqual(fases["harness"]["status"], "PASS")
        self.assertTrue(fases["plausibility"]["unlocked"])
        self.assertIsNone(fases["plausibility"]["blocked_by"])
        self.assertFalse(fases["ingestion"]["unlocked"])

    def test_evidence_names_what_is_checked_and_when_it_changed(self) -> None:
        self.harness()
        atlas = next(e for e in self.fases()["plausibility"]["evidence"] if e["path"] == "sota-pool/atlas.json")
        self.assertEqual((atlas["count"], atlas["mtime"]), (0, 0))
        (self.root / "sota-pool").mkdir()
        (self.root / "sota-pool" / "atlas.json").write_text("{}", encoding="utf-8")
        fases = self.fases()
        atlas = next(e for e in fases["plausibility"]["evidence"] if e["path"] == "sota-pool/atlas.json")
        self.assertEqual(atlas["count"], 1)
        self.assertGreater(atlas["mtime"], 0)
        self.assertEqual(fases["plausibility"]["status"], "PASS")
        self.assertTrue(fases["ingestion"]["unlocked"])

    def test_every_stage_declares_evidence(self) -> None:
        for stage in phase_actions.STAGES:
            with self.subTest(stage=stage):
                self.assertTrue(phase_actions.EVIDENCE[stage])

    def test_the_audit_phase_records_a_verdict_and_passes_only_on_success(self) -> None:
        response = asyncio.run(self.route("/api/phase/run", "POST")(Req({"phase_id": "Fase 11"})))
        result = json.loads(bytes(response.body))
        record = json.loads((self.root / ".papersmith" / "audit.json").read_text(encoding="utf-8"))
        self.assertEqual(set(record) >= {"ok", "returncode", "checked_at", "output"}, True)
        self.assertEqual(result["verified"], record["ok"])
        # A bare directory is not a papersmith workspace, so the audit fails.
        self.assertFalse(record["ok"])
        self.assertNotEqual(self.fases()["audit"]["status"], "PASS")
        (self.root / ".papersmith" / "audit.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
        self.assertEqual(self.fases()["audit"]["status"], "PASS")

    def test_a_clean_audit_passes_and_one_that_cannot_run_says_so(self) -> None:
        import subprocess
        from unittest import mock
        clean = subprocess.CompletedProcess([], 0, stdout="drift: clean\n", stderr="")
        with mock.patch.object(server.subprocess, "run", return_value=clean):
            result = json.loads(bytes(asyncio.run(self.route("/api/phase/run", "POST")(Req({"phase_id": "Fase 11"}))).body))
        self.assertEqual((result["status"], result["verified"]), ("PASS", True))
        self.assertIn("with no findings", result["message"])
        with mock.patch.object(server.subprocess, "run", side_effect=subprocess.TimeoutExpired("audit", 1)):
            result = json.loads(bytes(asyncio.run(self.route("/api/phase/run", "POST")(Req({"phase_id": "Fase 11"}))).body))
        record = json.loads((self.root / ".papersmith" / "audit.json").read_text(encoding="utf-8"))
        self.assertEqual((record["ok"], record["ran"]), (False, False))
        self.assertIn("could not run", result["message"])

    def test_only_one_audit_runs_at_a_time(self) -> None:
        self.assertTrue(server._AUDIT_LOCK.acquire(blocking=False))
        try:
            result = json.loads(bytes(asyncio.run(self.route("/api/phase/run", "POST")(Req({"phase_id": "Fase 11"}))).body))
        finally:
            server._AUDIT_LOCK.release()
        self.assertIn("already running", result["message"])
        self.assertFalse((self.root / ".papersmith" / "audit.json").exists())

    def test_a_phase_run_answers_with_the_phase_verdict(self) -> None:
        self.harness()
        response = asyncio.run(self.route("/api/phase/run", "POST")(Req({"phase_id": "Fase 1"})))
        result = json.loads(bytes(response.body))
        self.assertEqual((result["status"], result["verified"]), ("PASS", True))
        self.assertEqual(result["stage"], "harness")

    def test_experiments_are_listed_as_artifacts(self) -> None:
        (self.root / "experiments").mkdir()
        (self.root / "experiments" / "protocol.md").write_text("# P\n", encoding="utf-8")
        status = json.loads(bytes(self.route("/api/status")().body))
        self.assertIn("experiments/protocol.md", [a["rel_path"] for a in status["artifacts"]])


if __name__ == "__main__":
    unittest.main()
