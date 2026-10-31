"""Tests for the novelty & findings command-center endpoints and gates."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from fastapi.testclient import TestClient

from skills._core.command_center.server import create_app


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


if __name__ == "__main__":
    unittest.main()
