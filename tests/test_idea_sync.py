"""The ideas follow the latest proposal revision (``idea_sync.py``).

The latest revision's sky overlay gives the identity of the pillars, hypotheses
and problem tree; ``.papersmith/model_spec.json`` keeps their enrichment. The
sync writes that into the specification, retires what the revision dropped,
reports what changed, and every reader (``/api/model``, the Phase 4 steps, the
SOTA citations) shows the same precedence. "Update board" runs it.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from skills._core.command_center import board_refresh, idea_sync, model_spec, phase_steps
from skills._core.results import citations

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "skills" / "_core" / "command_center" / "idea_sync.py"
SPEC = ".papersmith/model_spec.json"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def sky(pillars: list[tuple[str, str]], hypotheses: list[tuple[str, str, str, list[str]]],
        tree: dict | None = None) -> dict:
    """An overlay: ``(id, label)`` pillars and ``(id, statement, pillar, experiments)`` hypotheses."""
    planets = [{"id": "p", "slot": "problem", "label": "The gap"}] + [
        {"id": f"c{n}", "slot": "contribution", "label": f"C{n}"} for n in range(1, 4)]
    found = {"system": {"id": "proposal", "title": "T", "planets": planets}, "links": [],
             "pillars": [{"id": i, "label": label, "detail": f"Detail of {i}."} for i, label in pillars],
             "hypotheses": [{"id": i, "statement": s, "pillar": p, "experiments": e}
                            for i, s, p, e in hypotheses]}
    if tree is not None:
        found["problem_tree"] = tree
    return found


class _Workspace(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.root = Path(holder.name).resolve() / "ws"
        self.root.mkdir()

    def revision(self, n: int, overlay: dict | None) -> None:
        name = f"research-concept-eeg-r{n:02d}"
        _write(self.root / "proposals" / f"{name}.md", "# Proposal\n")
        if overlay is not None:
            _write(self.root / "proposals" / f"{name}.sky.json", json.dumps(overlay))

    def spec(self, spec: dict, indent: int | None = 2) -> None:
        _write(self.root / SPEC, json.dumps(spec, indent=indent, ensure_ascii=False) + "\n")

    def read(self) -> dict:
        return json.loads((self.root / SPEC).read_text(encoding="utf-8"))

    def raw(self) -> str:
        return (self.root / SPEC).read_text(encoding="utf-8")


BASE_SPEC = {
    "title": "Paper",
    "novelty": {
        "problem_statement": "The gap.",
        "pillars": [{"id": "P1", "name": "Pillar one", "badge": "CORE", "summary": "Kept summary."},
                    {"id": "P2", "name": "Pillar two", "summary": "Second."}],
        "hypotheses": [{"id": "H1", "title": "First", "statement": "H1 holds.", "pillars": ["P1"],
                        "status": "Supported (v3)", "evidence": "E1 gain."},
                       {"id": "H2", "title": "Second", "statement": "H2 holds.", "pillars": ["P2"],
                        "status": "Open"},
                       {"id": "H3", "title": "Third", "statement": "H3 holds.", "pillars": ["P2"],
                        "status": "Refuted"}],
    },
    "contribution_type": {"type": "Theory", "why": "Because."},
}

CURRENT = sky([("P1", "Pillar one"), ("P2", "Pillar two, renamed")],
              [("H1", "H1 holds.", "P1", ["E1"]), ("H2", "H2 holds, restated.", "P1", ["E2"]),
               ("H4", "H4 is new.", "P2", ["E3"])])


class SyncTests(_Workspace):
    def setUp(self) -> None:
        super().setUp()
        self.spec(BASE_SPEC)
        self.revision(1, sky([("P1", "Pillar one"), ("P2", "Pillar two")],
                             [("H1", "H1 holds.", "P1", []), ("H2", "H2 holds.", "P2", []),
                              ("H3", "H3 holds.", "P2", [])]))
        self.revision(2, CURRENT)

    def test_the_report_names_what_was_added_pruned_changed_and_unchanged(self) -> None:
        result = idea_sync.sync(self.root)
        self.assertEqual(result["state"], "synced")
        self.assertTrue(result["ok"])
        self.assertTrue(result["written"])
        self.assertEqual(result["revision"], "r02")
        self.assertIsNone(result["previous_revision"])
        self.assertEqual(result["added"], ["hypothesis:H4"])
        self.assertEqual(result["pruned"], ["hypothesis:H3"])
        self.assertEqual(result["changed"], [{"id": "pillar:P2", "fields": ["name"]},
                                             {"id": "hypothesis:H1", "fields": ["experiments"]},
                                             {"id": "hypothesis:H2", "fields": ["statement", "pillars", "experiments"]}])
        self.assertEqual(result["unchanged"], ["pillar:P1"])
        self.assertEqual(result["kept"], ["problem_tree"])

    def test_the_active_lists_follow_the_revision_in_its_order(self) -> None:
        idea_sync.sync(self.root)
        novelty = self.read()["novelty"]
        self.assertEqual([p["id"] for p in novelty["pillars"]], ["P1", "P2"])
        self.assertEqual(novelty["pillars"][1]["name"], "Pillar two, renamed")
        self.assertEqual([h["id"] for h in novelty["hypotheses"]], ["H1", "H2", "H4"])
        self.assertEqual(novelty["hypotheses"][1]["statement"], "H2 holds, restated.")
        self.assertEqual(novelty["hypotheses"][1]["pillars"], ["P1"])
        self.assertEqual(novelty["hypotheses"][2]["experiments"], ["E3"])
        self.assertEqual(novelty["source_revision"], "r02")

    def test_a_dropped_id_is_retired_with_the_last_revision_that_held_it(self) -> None:
        idea_sync.sync(self.root)
        retired = self.read()["novelty"]["retired"]
        self.assertEqual(list(retired), ["hypotheses"])
        self.assertEqual(retired["hypotheses"], [{**BASE_SPEC["novelty"]["hypotheses"][2], "last_revision": "r01"}])

    def test_without_an_older_overlay_the_previous_source_revision_is_the_last(self) -> None:
        (self.root / "proposals" / "research-concept-eeg-r01.sky.json").unlink()
        self.spec({**BASE_SPEC, "novelty": {**BASE_SPEC["novelty"], "source_revision": "r01"}})
        idea_sync.sync(self.root)
        self.assertEqual(self.read()["novelty"]["retired"]["hypotheses"][0]["last_revision"], "r01")

    def test_the_enrichment_of_a_surviving_id_is_kept(self) -> None:
        idea_sync.sync(self.root)
        novelty = self.read()["novelty"]
        self.assertEqual(novelty["pillars"][0], {"id": "P1", "name": "Pillar one", "badge": "CORE",
                                                 "summary": "Kept summary."})
        h1 = novelty["hypotheses"][0]
        self.assertEqual((h1["title"], h1["status"], h1["evidence"]), ("First", "Supported (v3)", "E1 gain."))
        self.assertEqual(novelty["hypotheses"][2], {"id": "H4", "statement": "H4 is new.", "pillars": ["P2"],
                                                    "experiments": ["E3"]})
        self.assertEqual(self.read()["contribution_type"], BASE_SPEC["contribution_type"])

    def test_a_second_run_changes_nothing(self) -> None:
        idea_sync.sync(self.root)
        before = self.raw()
        again = idea_sync.sync(self.root)
        self.assertEqual(again["state"], "unchanged")
        self.assertFalse(again["written"])
        self.assertEqual((again["added"], again["pruned"], again["changed"]), ([], [], []))
        self.assertEqual(again["previous_revision"], "r02")
        self.assertEqual(self.raw(), before)

    def test_a_dry_run_reports_and_writes_nothing(self) -> None:
        before = self.raw()
        result = idea_sync.sync(self.root, dry_run=True)
        self.assertEqual(result["state"], "synced")
        self.assertTrue(result["dry_run"])
        self.assertFalse(result["written"])
        self.assertEqual(result["pruned"], ["hypothesis:H3"])
        self.assertEqual(self.raw(), before)

    def test_the_file_keeps_its_indent_and_key_order(self) -> None:
        idea_sync.sync(self.root)
        text = self.raw()
        self.assertTrue(text.startswith('{\n  "title": "Paper",\n  "novelty": {\n    "problem_statement"'))
        self.assertTrue(text.endswith("}\n"))
        self.assertEqual(list(self.read()), ["title", "novelty", "contribution_type"])
        self.assertEqual(list(self.read()["novelty"]["hypotheses"][0])[:3], ["id", "title", "statement"])

    def test_an_id_that_comes_back_takes_its_enrichment_back(self) -> None:
        idea_sync.sync(self.root)
        self.revision(3, sky([("P1", "Pillar one"), ("P2", "Pillar two, renamed")],
                             [("H1", "H1 holds.", "P1", ["E1"]), ("H3", "H3 holds.", "P2", [])]))
        result = idea_sync.sync(self.root)
        self.assertEqual(result["added"], ["hypothesis:H3"])
        novelty = self.read()["novelty"]
        h3 = next(h for h in novelty["hypotheses"] if h["id"] == "H3")
        self.assertEqual(h3["status"], "Refuted")
        self.assertNotIn("last_revision", h3)
        self.assertEqual(sorted(h["id"] for h in novelty["retired"]["hypotheses"]), ["H2", "H4"])

    def test_the_problem_tree_follows_an_overlay_that_carries_one(self) -> None:
        tree = {"central": {"text": "Degraded accuracy."},
                "causes": [{"id": "DC1", "text": "Noisy data."}, {"id": "DC3", "text": "Short records."}],
                "effects": [{"id": "EF1", "text": "Unreliable output.", "caused_by": ["DC1", "DC3"]}]}
        self.spec({**BASE_SPEC, "novelty": {**BASE_SPEC["novelty"], "problem_tree": {
            "central": {"text": "Old problem.", "note": "kept"},
            "causes": [{"id": "DC1", "text": "Noisy data.", "why": "kept"}, {"id": "DC2", "text": "Gone."}],
            "effects": [{"id": "EF1", "text": "Unreliable output.", "caused_by": ["DC1"]}]}}})
        self.revision(2, {**CURRENT, "problem_tree": tree})
        result = idea_sync.sync(self.root)
        novelty = self.read()["novelty"]
        self.assertEqual(novelty["problem_tree"]["central"], {"text": "Degraded accuracy.", "note": "kept"})
        self.assertEqual(novelty["problem_statement"], "Degraded accuracy.")
        self.assertEqual(novelty["problem_tree"]["causes"],
                         [{"id": "DC1", "text": "Noisy data.", "why": "kept"}, {"id": "DC3", "text": "Short records."}])
        self.assertEqual([c["id"] for c in novelty["retired"]["causes"]], ["DC2"])
        self.assertIn({"id": "problem:central", "fields": ["text"]}, result["changed"])
        self.assertIn({"id": "effect:EF1", "fields": ["caused_by"]}, result["changed"])
        self.assertIn("cause:DC3", result["added"])
        self.assertIn("cause:DC2", result["pruned"])


class NothingToSyncTests(_Workspace):
    def test_without_a_specification_nothing_is_written(self) -> None:
        self.revision(1, CURRENT)
        result = idea_sync.sync(self.root)
        self.assertEqual((result["state"], result["written"]), ("skipped", False))
        self.assertFalse((self.root / SPEC).exists())

    def test_without_an_overlay_nothing_is_written(self) -> None:
        self.spec(BASE_SPEC)
        before = self.raw()
        for overlay in (None, {"system": {"id": "proposal", "planets": []}}):
            with self.subTest(overlay=overlay):
                self.revision(1, overlay)
                result = idea_sync.sync(self.root)
                self.assertEqual(result["state"], "skipped")
                self.assertEqual(self.raw(), before)

    def test_without_a_revision_nothing_is_written(self) -> None:
        self.spec(BASE_SPEC)
        self.assertEqual(idea_sync.sync(self.root)["state"], "skipped")

    def test_a_refused_overlay_fails_and_writes_nothing(self) -> None:
        self.spec(BASE_SPEC)
        before = self.raw()
        self.revision(1, {"pillars": [{"id": "P1", "label": "x"}], "hypotheses": [{"id": "H1", "statement": "s"}]})
        result = idea_sync.sync(self.root)
        self.assertEqual((result["state"], result["ok"]), ("failed", False))
        self.assertIn("HYPOTHESIS_MALFORMED", result["detail"])
        self.assertEqual(self.raw(), before)


class PrecedenceTests(_Workspace):
    """The latest revision gives identity, the specification enrichment, at every reader."""

    def setUp(self) -> None:
        super().setUp()
        self.spec(BASE_SPEC)
        self.revision(2, CURRENT)

    def test_the_model_endpoint_shows_the_revision_ideas_with_their_enrichment(self) -> None:
        spec = model_spec.get_model_specification(self.root)
        novelty = spec["novelty"]
        self.assertEqual([h["id"] for h in novelty["hypotheses"]], ["H1", "H2", "H4"])
        self.assertEqual(novelty["pillars"][1]["name"], "Pillar two, renamed")
        self.assertEqual(novelty["hypotheses"][0]["status"], "Supported (v3)")
        self.assertEqual([h["id"] for h in novelty["retired"]["hypotheses"]], ["H3"])
        self.assertEqual(self.raw(), json.dumps(BASE_SPEC, indent=2, ensure_ascii=False) + "\n")

    def test_a_specification_never_synced_is_stale(self) -> None:
        spec = model_spec.get_model_specification(self.root)
        self.assertEqual((spec["stale"], spec["source_revision"], spec["latest_revision"]), (True, None, "r02"))

    def test_a_specification_synced_from_an_older_revision_is_stale(self) -> None:
        idea_sync.sync(self.root)
        self.assertNotIn("stale", model_spec.get_model_specification(self.root))
        self.revision(3, CURRENT)
        spec = model_spec.get_model_specification(self.root)
        self.assertEqual((spec["stale"], spec["source_revision"], spec["latest_revision"]), (True, "r02", "r03"))

    def test_the_phase_steps_count_the_revision_ideas(self) -> None:
        evidence = {s["id"]: s["evidence"] for s in phase_steps.proposal_steps(self.root)}
        self.assertEqual(evidence["hypotheses"]["hypotheses"], 3)
        self.assertEqual(evidence["hypotheses"]["source"], "proposals/research-concept-eeg-r02.sky.json")
        self.assertEqual(evidence["problem_pillars"]["source"], "proposals/research-concept-eeg-r02.sky.json")

    def test_the_citations_ask_for_the_revision_ideas(self) -> None:
        keys = [i["key"] for i in citations.state(self.root)["ideas"]]
        self.assertEqual([k for k in keys if k.startswith(("pillar:", "hypothesis:"))],
                         ["pillar:P1", "pillar:P2", "hypothesis:H1", "hypothesis:H2", "hypothesis:H4"])

    def test_without_an_overlay_the_specification_stands(self) -> None:
        (self.root / "proposals" / "research-concept-eeg-r02.sky.json").unlink()
        keys = [i["key"] for i in citations.state(self.root)["ideas"]]
        self.assertIn("hypothesis:H3", keys)
        self.assertEqual(len(model_spec.get_model_specification(self.root)["novelty"]["hypotheses"]), 3)


class ContributionTypeFreshnessTests(_Workspace):
    def test_a_type_recorded_for_an_older_revision_is_stale(self) -> None:
        self.spec({**BASE_SPEC, "contribution_type_revision": "r01"})
        self.revision(2, CURRENT)
        idea_sync.sync(self.root)
        self.assertTrue(model_spec.get_model_specification(self.root)["contribution_type_stale"])

    def test_a_type_recorded_for_the_latest_revision_is_current(self) -> None:
        self.spec({**BASE_SPEC, "contribution_type_revision": "r02"})
        self.revision(2, CURRENT)
        self.assertFalse(idea_sync.sync(self.root)["contribution_type_stale"])
        self.assertNotIn("contribution_type_stale", model_spec.get_model_specification(self.root))

    def test_a_type_without_a_basis_is_stale_only_once_synced(self) -> None:
        self.spec(BASE_SPEC)
        self.revision(2, CURRENT)
        self.assertNotIn("contribution_type_stale", model_spec.get_model_specification(self.root))
        self.assertTrue(idea_sync.sync(self.root)["contribution_type_stale"])
        self.assertTrue(model_spec.get_model_specification(self.root)["contribution_type_stale"])


class BoardRefreshTests(_Workspace):
    def test_update_board_syncs_the_ideas_and_reports_it(self) -> None:
        self.spec(BASE_SPEC)
        self.revision(2, CURRENT)
        artifacts = board_refresh.refresh_artifacts(self.root)
        ideas = next(a for a in artifacts if a["id"] == "ideas")
        self.assertEqual(ideas["state"], "ok")
        self.assertEqual(ideas["report"]["pruned"], ["hypothesis:H3"])
        summary = board_refresh.summarize({"fases": [], "gates": []}, artifacts)
        self.assertEqual(summary["ideas"]["added"], ["hypothesis:H4"])
        self.assertEqual(summary["ideas"]["revision"], "r02")
        self.assertEqual(self.read()["novelty"]["source_revision"], "r02")

    def test_the_summary_has_no_ideas_without_a_refresh(self) -> None:
        self.assertIsNone(board_refresh.summarize({"fases": [], "gates": []})["ideas"])


class PaperEEIAShapeTests(_Workspace):
    """Ids already match the latest revision, but the statuses cite older
    protocols, one pillar name and one hypothesis's pillar differ, and the
    hypotheses link their pillar through ``pillar``."""

    def test_the_sync_fixes_names_and_links_and_keeps_the_statuses(self) -> None:
        pillars = [("pillar-1", "Pillar 1: data"), ("pillar-2", "Pillar 2: physics"),
                   ("pillar-3", "Pillar 3: frequency reading, where the coherence decides")]
        hypotheses = [("H1", "Balance beats a free head.", "pillar-2", ["E1", "E2", "E3"]),
                      ("H6", "Coherence decides the reading.", "pillar-3", ["E9"]),
                      ("H8", "Exploratory band effect.", "pillar-3", ["E11"])]
        spec = {"title": "EEIA", "trl": "proposal r18", "novelty": {
            "problem_statement": "Degraded hourly forecast accuracy.",
            "pillars": [{"id": i, "name": label, "badge": "B", "color": "#fff", "summary": "s", "details": "d"}
                        for i, label in pillars[:2]]
            + [{"id": "pillar-3", "name": "Pillar 3: frequency reading of where the thermal response is identifiable",
                "badge": "FREQUENCY", "color": "#ef4444", "summary": "s", "details": "d"}],
            "hypotheses": [{"id": "H1", "title": "t1", "pillar": "pillar-2", "statement": hypotheses[0][1],
                            "status": "Not supported on measured data in the declared v17 runs", "evidence": "E3.a"},
                           {"id": "H6", "title": "t6", "pillar": "pillar-3", "statement": hypotheses[1][1],
                            "status": "Supported (v19)", "evidence": "E9"},
                           {"id": "H8", "title": "t8", "pillar": "pillar-2", "statement": hypotheses[2][1],
                            "status": "Open (v18)", "evidence": ""}]},
            "contribution_type": {"type": "Use-Inspired", "why": "r18 keeps the claim."}}
        self.spec(spec)
        self.revision(21, sky(pillars, hypotheses))
        result = idea_sync.sync(self.root)
        self.assertEqual(result["added"], [])
        self.assertEqual(result["pruned"], [])
        self.assertIn({"id": "pillar:pillar-3", "fields": ["name"]}, result["changed"])
        self.assertIn({"id": "hypothesis:H8", "fields": ["pillars", "experiments"]}, result["changed"])
        self.assertTrue(result["contribution_type_stale"])
        novelty = self.read()["novelty"]
        self.assertEqual(novelty["pillars"][2]["name"], pillars[2][1])
        self.assertEqual(novelty["pillars"][2]["badge"], "FREQUENCY")
        h8 = novelty["hypotheses"][2]
        self.assertEqual((h8["pillar"], h8["pillars"], h8["status"]), ("pillar-3", ["pillar-3"], "Open (v18)"))
        self.assertEqual(novelty["hypotheses"][0]["status"],
                         "Not supported on measured data in the declared v17 runs")
        self.assertNotIn("retired", novelty)
        self.assertEqual(idea_sync.sync(self.root)["state"], "unchanged")


class CommandLineTests(_Workspace):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(SCRIPT), "--root", str(self.root), *args],
                              capture_output=True, text=True, timeout=60, check=False)

    def test_the_cli_dry_run_prints_the_report_and_writes_nothing(self) -> None:
        self.spec(BASE_SPEC)
        self.revision(2, CURRENT)
        before = self.raw()
        done = self.run_cli("--dry-run", "--json")
        self.assertEqual(done.returncode, 0, done.stderr)
        report = json.loads(done.stdout)
        self.assertEqual((report["state"], report["written"]), ("synced", False))
        self.assertEqual(self.raw(), before)

    def test_the_cli_syncs(self) -> None:
        self.spec(BASE_SPEC)
        self.revision(2, CURRENT)
        done = self.run_cli()
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("IDEAS_SYNCED: r02", done.stdout)
        self.assertIn("pruned: hypothesis:H3", done.stdout)
        self.assertEqual(self.read()["novelty"]["source_revision"], "r02")

    def test_a_refused_overlay_exits_1(self) -> None:
        self.spec(BASE_SPEC)
        self.revision(1, {"pillars": [{"id": "P1"}]})
        done = self.run_cli()
        self.assertEqual(done.returncode, 1)
        self.assertIn("IDEAS_FAILED", done.stdout)


if __name__ == "__main__":
    unittest.main()
