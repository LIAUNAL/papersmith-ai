"""Unit tests for the novelty-gate contract, CLI, and evaluation overview."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from papersmith.core import novelty
from skills._core.results import novelty_gate, novelty_cli


class TestNoveltyGate(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / ".papersmith").mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_default_gate_is_pending(self) -> None:
        gate = novelty_gate.read_gate(self.root)
        self.assertEqual(gate["status"], "pending")
        self.assertIsNone(gate["decided_at"])
        self.assertEqual(gate["history"], [])

    def test_approve_records_decision(self) -> None:
        record = novelty_gate.record_decision(self.root, "approve", rationale="Strong empirical evidence")
        self.assertEqual(record["status"], "approved")
        self.assertEqual(record["target_stage"], "scaffolding")
        self.assertEqual(record["rationale"], "Strong empirical evidence")
        self.assertIsNotNone(record["decided_at"])

        # Re-read
        gate = novelty_gate.read_gate(self.root)
        self.assertEqual(gate["status"], "approved")
        self.assertEqual(gate["rationale"], "Strong empirical evidence")

    def test_iterate_decisions_record_target_stages(self) -> None:
        for action, expected_target, expected_status in [
            ("iterate_experiments", "poc_experiments", "iterating_experiments"),
            ("iterate_proposal", "proposal", "iterating_proposal"),
            ("iterate_plausibility", "plausibility", "iterating_plausibility"),
        ]:
            record = novelty_gate.record_decision(self.root, action, rationale=f"Iterating for {action}")
            self.assertEqual(record["status"], expected_status)
            self.assertEqual(record["target_stage"], expected_target)

        # History should hold prior decisions
        gate = novelty_gate.read_gate(self.root)
        self.assertEqual(len(gate["history"]), 2)

    def test_invalid_action_refuses(self) -> None:
        with self.assertRaises(novelty_gate.NoveltyRefusal) as ctx:
            novelty_gate.record_decision(self.root, "invalid_action")
        self.assertEqual(ctx.exception.code, "INVALID_ACTION")

    def test_novelty_cli_status_and_approve(self) -> None:
        exit_code = novelty_cli.main(["status", "--root", str(self.root)])
        self.assertEqual(exit_code, 0)

        exit_code = novelty_cli.main(["approve", "--root", str(self.root), "--notes", "CLI approval"])
        self.assertEqual(exit_code, 0)

        gate = novelty_gate.read_gate(self.root)
        self.assertEqual(gate["status"], "approved")
        self.assertEqual(gate["rationale"], "CLI approval")

    def test_smith_novelty_cli_status_json(self) -> None:
        class Args:
            workspace = str(self.root)
            json = True
        code = novelty.run_status(Args())
        self.assertEqual(code, 0)

    def test_smith_novelty_cli_approve_and_iterate(self) -> None:
        class ApproveArgs:
            workspace = str(self.root)
            notes = "Approved via core CLI"
        code = novelty.run_approve(ApproveArgs())
        self.assertEqual(code, 0)
        self.assertEqual(novelty_gate.read_gate(self.root)["status"], "approved")

        class IterateArgs:
            workspace = str(self.root)
            stage = "experiments"
            notes = "Need more seeds"
        code = novelty.run_iterate(IterateArgs())
        self.assertEqual(code, 0)
        self.assertEqual(novelty_gate.read_gate(self.root)["status"], "iterating_experiments")


if __name__ == "__main__":
    unittest.main()
