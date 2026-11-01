"""The proposal overlay's machine-readable pillars and hypotheses.

``proposals/<revision>.sky.json`` may carry ``pillars`` (``{id, label,
detail?, contribution?}``) and ``hypotheses`` (``{id, statement, pillar,
experiments?}``). Both are optional, so every overlay written before them
still merges; when present, ``merge_proposal_sky.py`` holds them to their
shape and the merged atlas is unchanged by them (``check_atlas.py`` never sees
them). ``pillars_and_hypotheses`` is the pure check the manuscript graph reuses.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_proposal_sky import CHECKER, MERGER, atlas, overlay  # noqa: E402

spec = importlib.util.spec_from_file_location("merge_proposal_sky", MERGER)
merger = importlib.util.module_from_spec(spec)
spec.loader.exec_module(merger)


def with_pillars(**over):
    doc = overlay()
    doc["pillars"] = [
        {"id": "P1", "label": "Calibrated attention", "detail": "d", "contribution": "proposal-contrib-0"},
        {"id": "P2", "label": "Graph prior"},
    ]
    doc["hypotheses"] = [
        {"id": "H1", "statement": "Calibration raises AUC.", "pillar": "P1", "experiments": ["e1"]},
    ]
    doc.update(over)
    return doc


class PillarsAndHypothesesTests(unittest.TestCase):
    def test_an_old_overlay_without_pillars_still_merges_unchanged(self) -> None:
        merged, refusal = merger.merge(atlas(), overlay())
        self.assertIsNone(refusal)
        self.assertEqual(merger.pillars_and_hypotheses(overlay()), ({"pillars": [], "hypotheses": []}, None))
        with_new, refusal = merger.merge(atlas(), with_pillars())
        self.assertIsNone(refusal)
        self.assertEqual(with_new, merged)
        self.assertNotIn("pillars", with_new)

    def test_well_formed_pillars_and_hypotheses_are_returned(self) -> None:
        found, refusal = merger.pillars_and_hypotheses(with_pillars())
        self.assertIsNone(refusal)
        self.assertEqual([p["id"] for p in found["pillars"]], ["P1", "P2"])
        self.assertEqual(found["hypotheses"][0]["pillar"], "P1")

    def test_each_malformation_is_refused_by_name(self) -> None:
        cases = {
            "OVERLAY_PILLARS_MALFORMED": with_pillars(pillars={"id": "P1"}),
            "PILLAR_MALFORMED": with_pillars(pillars=[{"id": "P1"}]),
            "PILLAR_ID_DUPLICATED": with_pillars(pillars=[{"id": "P1", "label": "a"},
                                                          {"id": "P1", "label": "b"}]),
            "PILLAR_CONTRIBUTION_UNKNOWN": with_pillars(pillars=[
                {"id": "P1", "label": "a", "contribution": "nowhere"}]),
            "OVERLAY_HYPOTHESES_MALFORMED": with_pillars(hypotheses="H1"),
            "HYPOTHESIS_MALFORMED": with_pillars(hypotheses=[{"id": "H1", "pillar": "P1"}]),
            "HYPOTHESIS_PILLAR_UNKNOWN": with_pillars(hypotheses=[
                {"id": "H1", "statement": "s", "pillar": "P9"}]),
            "HYPOTHESIS_ID_DUPLICATED": with_pillars(hypotheses=[
                {"id": "H1", "statement": "s", "pillar": "P1"},
                {"id": "H1", "statement": "t", "pillar": "P2"}]),
            "HYPOTHESIS_EXPERIMENTS_MALFORMED": with_pillars(hypotheses=[
                {"id": "H1", "statement": "s", "pillar": "P1", "experiments": "e1"}]),
            "HYPOTHESES_WITHOUT_PILLARS": with_pillars(pillars=[]),
        }
        for code, doc in cases.items():
            with self.subTest(code=code):
                _found, refusal = merger.pillars_and_hypotheses(doc)
                self.assertIsNotNone(refusal)
                self.assertTrue(refusal.startswith(code + ":") or refusal == code, refusal)
                merged, merge_refusal = merger.merge(atlas(), doc)
                self.assertIsNone(merged)
                self.assertEqual(merge_refusal, refusal)

    def test_the_cli_merges_an_overlay_with_pillars_and_the_checker_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "atlas.json").write_text(json.dumps(atlas()), encoding="utf-8")
            (tmp / "sky.json").write_text(json.dumps(with_pillars()), encoding="utf-8")
            out = tmp / "merged.json"
            proc = subprocess.run([sys.executable, str(MERGER), str(tmp / "atlas.json"),
                                   str(tmp / "sky.json"), "--out", str(out)],
                                  capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            check = subprocess.run([sys.executable, str(CHECKER), str(out)],
                                   capture_output=True, text=True)
            self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
            bad = copy.deepcopy(with_pillars())
            bad["hypotheses"][0]["pillar"] = "P9"
            (tmp / "sky.json").write_text(json.dumps(bad), encoding="utf-8")
            proc = subprocess.run([sys.executable, str(MERGER), str(tmp / "atlas.json"),
                                   str(tmp / "sky.json"), "--out", str(tmp / "other.json")],
                                  capture_output=True, text=True)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("HYPOTHESIS_PILLAR_UNKNOWN", proc.stderr)
            self.assertFalse((tmp / "other.json").exists())


if __name__ == "__main__":
    unittest.main()
