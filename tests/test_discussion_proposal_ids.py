"""Discussion hypotheses carry their proposal ids (board-follows-iteration S3).

``skills/_core/results/discussion.py`` keeps the positional ``H1``..``Hn`` ids
of a discussion (a recorded contract) and adds ``proposal_hypotheses``: the ids
of the proposal hypotheses whose ``experiments`` (in the latest
``proposals/research-concept-*-rNN.sky.json``) name the protocol experiment.
``scaffold`` writes it, ``link_proposal_hypotheses`` backfills an existing
discussion without touching its verdicts, and ``discussion_cli.py link`` runs
that backfill. These tests go through the module and the command line.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RESULTS = REPO / "skills" / "_core" / "results"


def _load(filename: str, name: str):
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, RESULTS / filename)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


discussion = _load("discussion.py", "papersmith_results_discussion")
cli = _load("discussion_cli.py", "papersmith_results_discussion_cli")

PROTOCOL = """# Protocol v23

## Experiment [exp:E1] — Baseline gain

- **Hypothesis:** The model beats the baseline.
- **Success criterion:** MAE lower by 5%.

## Experiment [exp:E10] — Two-sided check

- **Hypothesis:** Both sides hold.

## Experiment [exp:E14] — Transfer

- **Hypothesis:** It transfers.
"""

SKY = {
    "system": {"id": "proposal", "title": "r21", "planets": []},
    "links": [],
    "pillars": [{"id": "P1", "label": "Physics prior"}, {"id": "P2", "label": "Transfer"}],
    "hypotheses": [
        {"id": "H1", "statement": "Gain over the baseline.", "pillar": "P1", "experiments": ["E1"]},
        {"id": "H7a", "statement": "First side.", "pillar": "P1", "experiments": ["E10"]},
        {"id": "H7b", "statement": "Second side.", "pillar": "P1", "experiments": ["exp:E10"]},
        {"id": "H11", "statement": "Transfer holds.", "pillar": "P2", "experiments": ["E14"]},
    ],
}


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class _Workspace(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.root = Path(holder.name).resolve()
        self.product = self.root / "implementations" / "repo" / "Full"
        _write(self.product / "Experimental_AGREED.md", "agreed\n")
        _write(self.root / "experiments" / "experiments-demo-v23.md", PROTOCOL)

    def sky(self, revision: int = 21, data: dict | None = None) -> None:
        name = f"research-concept-demo-r{revision:02d}"
        _write(self.root / "proposals" / f"{name}.md", "# proposal\n")
        _write(self.root / "proposals" / f"{name}.sky.json", json.dumps(SKY if data is None else data))

    def discussion_file(self) -> Path:
        return self.product / "Results" / "discussion.json"

    def write_discussion(self, data: dict) -> Path:
        return _write(self.discussion_file(), json.dumps(data, indent=2))

    def run_cli(self, *argv: str) -> tuple[int, dict]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(list(argv))
        return code, json.loads(out.getvalue())


def _filled() -> dict:
    """A discussion written before the field existed, with decided verdicts."""
    return {
        "schema": 1, "stage": "full", "protocol": "experiments/experiments-demo-v23.md",
        "summary": "Done.", "metrics": [{"name": "MAE", "why": "error"}],
        "hypotheses": [
            {"id": "H1", "experiment": "E1", "statement": "The model beats the baseline.",
             "verdict": "inconclusive", "rationale": "kept"},
            {"id": "H2", "experiment": "E10", "statement": "Both sides hold.", "verdict": "pending"},
            {"id": "H3", "experiment": "E14", "statement": "It transfers.", "verdict": "inconclusive",
             "observed": "0.41"},
            {"id": "H4", "experiment": "E99", "statement": "Not in the sky.", "verdict": "pending"},
        ],
        "novelty": {"claim": "New.", "verdict": "pending", "evidence": [], "rationale": ""},
        "qualitative_not_applicable": "tabular",
    }


class ScaffoldMappingTests(_Workspace):
    def test_the_scaffold_keeps_positional_ids_and_adds_the_proposal_ids(self) -> None:
        self.sky()
        data = discussion.scaffold(self.product)
        self.assertEqual([(h["id"], h["experiment"], h["proposal_hypotheses"]) for h in data["hypotheses"]],
                         [("H1", "E1", ["H1"]), ("H2", "E10", ["H7a", "H7b"]), ("H3", "E14", ["H11"])])

    def test_the_latest_revision_decides_the_mapping(self) -> None:
        self.sky(20, {**SKY, "hypotheses": [{"id": "H9", "statement": "Old.", "pillar": "P1",
                                             "experiments": ["E14"]}]})
        self.sky(21)
        mapped = {h["experiment"]: h["proposal_hypotheses"] for h in discussion.scaffold(self.product)["hypotheses"]}
        self.assertEqual(mapped["E14"], ["H11"])

    def test_without_a_sky_every_hypothesis_is_unmapped(self) -> None:
        data = discussion.scaffold(self.product)
        self.assertEqual([h["proposal_hypotheses"] for h in data["hypotheses"]], [[], [], []])
        self.assertEqual(discussion.finding_ids(data["hypotheses"][0]), [("H1", True)])

    def test_the_cli_scaffold_writes_the_mapping(self) -> None:
        self.sky()
        code, out = self.run_cli("scaffold", "--product", str(self.product))
        self.assertEqual((code, out["ok"]), (0, True))
        written = json.loads(self.discussion_file().read_text("utf-8"))
        self.assertEqual(written["hypotheses"][2]["proposal_hypotheses"], ["H11"])


class BackfillTests(_Workspace):
    def test_the_backfill_sets_only_the_proposal_ids(self) -> None:
        self.sky()
        before = _filled()
        self.write_discussion(before)
        result = discussion.link_proposal_hypotheses(self.product)
        self.assertTrue(result["written"])
        self.assertEqual(result["sky"], "proposals/research-concept-demo-r21.sky.json")
        self.assertEqual([c["id"] for c in result["changed"]], ["H1", "H2", "H3", "H4"])
        after = json.loads(self.discussion_file().read_text("utf-8"))
        self.assertEqual([h["proposal_hypotheses"] for h in after["hypotheses"]],
                         [["H1"], ["H7a", "H7b"], ["H11"], []])
        for item in after["hypotheses"]:
            del item["proposal_hypotheses"]
        self.assertEqual(after, before)

    def test_a_second_backfill_changes_nothing_and_writes_nothing(self) -> None:
        self.sky()
        self.write_discussion(_filled())
        discussion.link_proposal_hypotheses(self.product)
        text = self.discussion_file().read_text("utf-8")
        again = discussion.link_proposal_hypotheses(self.product)
        self.assertEqual((again["changed"], again["written"]), ([], False))
        self.assertEqual(self.discussion_file().read_text("utf-8"), text)

    def test_the_backfill_refuses_without_a_sky_or_a_discussion(self) -> None:
        with self.assertRaises(discussion.DiscussionRefusal) as ctx:
            discussion.link_proposal_hypotheses(self.product)
        self.assertEqual(ctx.exception.code, "DISCUSSION_ABSENT")
        self.write_discussion(_filled())
        with self.assertRaises(discussion.DiscussionRefusal) as ctx:
            discussion.link_proposal_hypotheses(self.product)
        self.assertEqual(ctx.exception.code, "SKY_ABSENT")
        self.sky(data={**SKY, "hypotheses": [{"id": "H1", "statement": "x", "pillar": "P9"}]})
        with self.assertRaises(discussion.DiscussionRefusal) as ctx:
            discussion.link_proposal_hypotheses(self.product)
        self.assertEqual(ctx.exception.code, "SKY_REFUSED")
        self.assertNotIn("proposal_hypotheses", self.discussion_file().read_text("utf-8"))


class LinkCliTests(_Workspace):
    def test_link_backfills_and_reports_the_change(self) -> None:
        self.sky()
        self.write_discussion(_filled())
        code, out = self.run_cli("link", "--product", str(self.product))
        self.assertEqual((code, out["ok"], out["written"]), (0, True, True))
        self.assertEqual(out["changed"][2], {"id": "H3", "experiment": "E14", "before": None, "after": ["H11"]})
        written = json.loads(self.discussion_file().read_text("utf-8"))
        self.assertEqual(written["hypotheses"][2]["proposal_hypotheses"], ["H11"])
        self.assertEqual(written["hypotheses"][2]["verdict"], "inconclusive")

    def test_link_dry_run_writes_nothing(self) -> None:
        self.sky()
        self.write_discussion(_filled())
        text = self.discussion_file().read_text("utf-8")
        code, out = self.run_cli("link", "--product", str(self.product), "--dry-run")
        self.assertEqual((code, out["ok"], out["written"], len(out["changed"])), (0, True, False, 4))
        self.assertEqual(self.discussion_file().read_text("utf-8"), text)

    def test_link_refuses_without_a_sky(self) -> None:
        self.write_discussion(_filled())
        code, out = self.run_cli("link", "--product", str(self.product))
        self.assertEqual((code, out["ok"], out["error"]), (1, False, "SKY_ABSENT"))

    def test_check_still_reads_the_old_verbs(self) -> None:
        # The verbs that existed before link keep their behaviour.
        code, out = self.run_cli("check", "--product", str(self.product))
        self.assertEqual((code, out["error"]), (1, "DISCUSSION_ABSENT"))
        code, out = self.run_cli("bogus", "--product", str(self.product))
        self.assertEqual((code, out["error"]), (2, "USAGE"))


class CheckTests(_Workspace):
    def test_check_accepts_the_proposal_ids(self) -> None:
        self.sky()
        self.write_discussion(_filled())
        self.run_cli("link", "--product", str(self.product))
        code, out = self.run_cli("check", "--product", str(self.product))
        self.assertEqual(code, 0, out)
        self.assertFalse([w for w in out["warnings"] if "proposal_hypotheses" in w])

    def test_check_refuses_malformed_proposal_ids(self) -> None:
        data = _filled()
        data["hypotheses"][0]["proposal_hypotheses"] = "H1"
        data["hypotheses"][1]["proposal_hypotheses"] = ["H7a", ""]
        result = discussion.check_discussion(self.product, data)
        self.assertEqual(result["status"], "invalid")
        self.assertIn("hypotheses[0].proposal_hypotheses: must be a list of proposal hypothesis ids",
                      result["errors"])
        self.assertIn("hypotheses[1].proposal_hypotheses: must be a list of proposal hypothesis ids",
                      result["errors"])

    def test_check_accepts_the_judged_protocol_beside_the_type(self) -> None:
        affinity = {name: {"score": 90 if name == "General" else 10, "why": "w"}
                    for name in ("General", "Theory", "Use-Inspired", "Concept & Feasibility",
                                 "Negative Results")}
        data = _filled()
        data["contribution_type"] = {"type": "General", "why": "H1 holds.", "affinity": affinity}
        data["contribution_type_protocol"] = "experiments/experiments-demo-v23.md"
        result = discussion.check_discussion(self.product, data)
        self.assertEqual(result["errors"], [])
        self.assertFalse([w for w in result["warnings"] if "contribution_type_protocol" in w])
        data["contribution_type_protocol"] = ""
        self.assertIn("contribution_type_protocol: a non-empty path of at most 1024 characters",
                      discussion.check_discussion(self.product, data)["errors"])
        # The shared contract still refuses an unknown key inside the type.
        data["contribution_type"]["basis"] = "r21"
        self.assertIn("contribution_type: unknown key 'basis'",
                      discussion.check_discussion(self.product, data)["errors"])


class StatusTests(unittest.TestCase):
    def test_one_status_from_the_verdicts_of_an_id(self) -> None:
        cases = {
            (): "pending",
            ("supported",): "supported",
            ("supported", "supported"): "supported",
            ("supported", "not_supported"): "partially_supported",
            ("partially_supported",): "partially_supported",
            ("not_supported", "not_supported"): "not_supported",
            ("not_supported", "pending"): "not_supported",
            ("pending", "inconclusive"): "pending",
            ("inconclusive", "inconclusive"): "inconclusive",
        }
        for verdicts, expected in cases.items():
            with self.subTest(verdicts=verdicts):
                self.assertEqual(discussion.hypothesis_status(list(verdicts)), expected)


if __name__ == "__main__":
    unittest.main()
