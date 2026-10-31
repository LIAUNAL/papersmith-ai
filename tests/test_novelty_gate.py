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


def _write_discussion(root: Path, product: str, data: object) -> None:
    folder = root / "implementations" / "repo" / product / "Results"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "discussion.json").write_text(json.dumps(data), encoding="utf-8")


class TestNoveltyOverviewSobrietyData(unittest.TestCase):
    """The overview carries what the panel's sobriety box lists: limitations,
    hypothesis verdicts and rationales, and the novelty verdict."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_overview_lists_the_limitations_of_each_product(self) -> None:
        _write_discussion(self.root, "ProdA", {"limitations": ["small sample", "single site"]})
        _write_discussion(self.root, "ProdB", {"limitations": ["no external cohort"]})
        overview = novelty_gate.get_novelty_overview(self.root)
        self.assertEqual(
            [(e["product"], e["text"]) for e in overview["limitations"]],
            [("ProdA", "small sample"), ("ProdA", "single site"), ("ProdB", "no external cohort")],
        )
        self.assertEqual({e["stage"] for e in overview["limitations"]}, {"poc"})

    def test_overview_without_discussions_has_no_limitations(self) -> None:
        self.assertEqual(novelty_gate.get_novelty_overview(self.root)["limitations"], [])

    def test_overview_keeps_verdicts_and_rationales_for_unsupported_findings(self) -> None:
        _write_discussion(self.root, "ProdA", {
            "hypotheses": [
                {"id": "H1", "statement": "s1", "verdict": "not_supported", "rationale": "no effect"},
                {"id": "H2", "statement": "s2", "verdict": "inconclusive", "rationale": "too few seeds"},
            ],
            "novelty": {"claim": "c", "verdict": "not_justified", "rationale": "prior work covers it"},
        })
        overview = novelty_gate.get_novelty_overview(self.root)
        self.assertEqual([(h["id"], h["verdict"], h["rationale"]) for h in overview["hypotheses"]],
                         [("H1", "not_supported", "no effect"), ("H2", "inconclusive", "too few seeds")])
        self.assertEqual(overview["discussions"][0]["verdict"], "not_justified")
        self.assertEqual(overview["discussions"][0]["rationale"], "prior work covers it")

    def test_limitations_are_bounded_and_clipped(self) -> None:
        _write_discussion(self.root, "ProdA", {"limitations": ["x" * 5000] * (novelty_gate.MAX_LIMITATIONS + 20)})
        overview = novelty_gate.get_novelty_overview(self.root)
        self.assertEqual(len(overview["limitations"]), novelty_gate.MAX_LIMITATIONS)
        self.assertLessEqual(max(len(e["text"]) for e in overview["limitations"]), novelty_gate.MAX_LIMITATION_LENGTH)

    def test_malformed_discussions_never_raise(self) -> None:
        _write_discussion(self.root, "BadLimits", {"limitations": "not a list"})
        _write_discussion(self.root, "BadItems", {"limitations": [None, 3, {"a": 1}, "", "  ", "kept"]})
        _write_discussion(self.root, "BadHyp", {"hypotheses": 5, "novelty": "nope"})
        _write_discussion(self.root, "BadHypItems", {"hypotheses": ["x", None, {"id": "H9", "verdict": "inconclusive"}]})
        _write_discussion(self.root, "NotAnObject", ["list"])
        overview = novelty_gate.get_novelty_overview(self.root)
        self.assertEqual([e["text"] for e in overview["limitations"]], ["kept"])
        self.assertEqual([h["id"] for h in overview["hypotheses"]], ["H9"])


class TestNoveltyRigorAuditIsDomainNeutral(unittest.TestCase):
    """The forge carries no paper inside: the audit names no one project's split."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_audit_text_names_no_project_specific_term(self) -> None:
        source = Path(novelty_gate.__file__).read_text(encoding="utf-8").lower()
        for term in ("groupkfold", "subject-level", "segment leakage", "entangle", "barren"):
            self.assertNotIn(term, source)
        _write_discussion(self.root, "ProdA", {"hypotheses": [
            {"id": "H1", "criterion": "held-out groups", "verdict": "supported", "test": "wilcoxon"}]})
        for overview in (novelty_gate.get_novelty_overview(self.root),
                         novelty_gate.get_novelty_overview(self.root / "missing")):
            text = json.dumps(overview["rigor_audit"]).lower()
            for term in ("groupkfold", "subject-level", "segment"):
                self.assertNotIn(term, text)

    def test_leakage_check_still_passes_on_group_or_leak_wording(self) -> None:
        _write_discussion(self.root, "ProdA", {"hypotheses": [
            {"id": "H1", "criterion": "evaluation on held-out groups", "verdict": "pending"}]})
        audit = {r["id"]: r for r in novelty_gate.get_novelty_overview(self.root)["rigor_audit"]}
        self.assertTrue(audit["leakage_free"]["passed"])
        empty = {r["id"]: r for r in novelty_gate.get_novelty_overview(self.root / "missing")["rigor_audit"]}
        self.assertFalse(empty["leakage_free"]["passed"])


if __name__ == "__main__":
    unittest.main()
