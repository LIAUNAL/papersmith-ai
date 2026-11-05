"""Every idea of the proposal and of the protocol is justified by the SOTA pool.

`.papersmith/citations.json` gives each pillar, hypothesis, concept-map layer,
numbered equation and experiment 2 to 5 pool references with a reason. A step of
Phase 4 reads the proposal's ideas before the NeurIPS judge; the experiments'
citations hold the implementation actions, G-EXP-POC and Phase 5. The panels
show each idea's citations beside it, and `citations_cli.py check` says what is
owed. Validity means pool membership and a stated reason, not that the reference
truly supports the idea."""

from __future__ import annotations

import contextlib
import io
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from skills._core.command_center import experiments_view, math_view, phase_steps, server
from skills._core.results import citations, citations_cli, novelty_cli, novelty_gate
from tests.test_flow_gating_phase4 import EQUATION, POOL, _Workspace as _Phase4, _write, cite_everything, render
from tests.test_flow_gating_phase5 import render_panel
from tests.test_neurips_judge_gate import TYPED
from tests.test_phase5_review import MARKER, _Status

STATIC = Path(server.__file__).resolve().parent / "static"
A, B = POOL[0]["identifier"], POOL[1]["identifier"]
GOOD = [{"id": A, "why": "It states the bound."}, {"id": B, "why": "It measures the gap."}]
PROTOCOL = MARKER + "# Protocol\n\n## Experiment [exp:E1] — First\n\n## Experiment [exp:E2] — Second\n"


def _pool(root: Path, *extra: dict) -> None:
    _write(root / "sota-pool" / "candidates.json", json.dumps({"candidates": [*POOL, *extra]}))


def _file(root: Path, ideas: dict) -> None:
    _write(root / ".papersmith" / "citations.json", json.dumps({"schema": 1, "ideas": ideas}))


class _Ideas(_Phase4):
    """A workspace with one idea of each proposal kind and a pool of references."""

    def setUp(self) -> None:
        super().setUp()
        _pool(self.root)

    def ideas(self, **extra) -> None:
        spec = {"novelty": {"problem_statement": "Gap.", "pillars": [{"id": "P1", "name": "Pillar"}],
                            "hypotheses": [{"id": "H1", "statement": "It improves."}]},
                "conceptual_map": {"layers": [{"name": "Signal"}]}, **extra}
        _write(self.root / ".papersmith" / "model_spec.json", json.dumps(spec))
        self.revision(EQUATION)

    def problems(self, entries) -> list[str]:
        """What the contract says about the citations of ``pillar:P1``."""
        self.ideas()
        _file(self.root, {"pillar:P1": entries})
        state = citations.state(self.root)
        return next(i for i in state["ideas"] if i["key"] == "pillar:P1")["problems"]


class ContractTests(_Ideas):
    def test_two_to_five_citations_with_a_reason_are_valid(self) -> None:
        extra = [{"identifier": f"10.1000/x{i}", "title": "X"} for i in range(3)]
        _pool(self.root, *extra)
        five = GOOD + [{"id": e["identifier"], "why": "Same task."} for e in extra]
        self.assertEqual(self.problems(GOOD), [])
        self.assertEqual(self.problems(five), [])

    def test_one_citation_refuses(self) -> None:
        self.assertEqual(self.problems(GOOD[:1]), ["pillar:P1: 1 citation(s), needs 2 to 5"])

    def test_six_citations_refuse(self) -> None:
        extra = [{"identifier": f"10.1000/y{i}", "title": "Y"} for i in range(4)]
        _pool(self.root, *extra)
        six = GOOD + [{"id": e["identifier"], "why": "Same task."} for e in extra]
        self.assertEqual(self.problems(six), ["pillar:P1: 6 citation(s), needs 2 to 5"])

    def test_a_duplicate_id_refuses_even_when_spelled_differently(self) -> None:
        twice = [{"id": B, "why": "One."}, {"id": B.removeprefix("arXiv:"), "why": "Two."}]
        self.assertEqual(self.problems(twice), [f"pillar:P1: duplicate id {B.removeprefix('arXiv:')!r}"])

    def test_an_id_outside_the_pool_refuses(self) -> None:
        found = self.problems([GOOD[0], {"id": "10.9999/absent", "why": "Not scouted."}])
        self.assertEqual(found, ["pillar:P1: '10.9999/absent' is not in sota-pool/candidates.json"])

    def test_the_arxiv_prefix_and_the_doi_case_normalize(self) -> None:
        spelled = [{"id": "https://doi.org/" + A.upper(), "why": "Same work."},
                   {"id": B.removeprefix("arXiv:"), "why": "Same work."}]
        self.assertEqual(self.problems(spelled), [])
        self.assertEqual(citations.normalize("arXiv:2008.08605"), citations.normalize("2008.08605"))
        self.assertEqual(citations.normalize("DOI:10.1000/AbC"), citations.normalize("10.1000/abc"))

    def test_an_arxiv_version_is_not_the_same_work(self) -> None:
        self.assertNotEqual(citations.normalize("2401.00001v2"), citations.normalize("2401.00001"))

    def test_a_blank_why_refuses(self) -> None:
        self.assertEqual(self.problems([GOOD[0], {"id": B, "why": "   "}]), ["pillar:P1: entry 2 has no why"])

    def test_a_why_over_three_hundred_characters_refuses(self) -> None:
        self.assertEqual(self.problems([GOOD[0], {"id": B, "why": "x" * 301}]),
                         ["pillar:P1: entry 2 why is longer than 300 characters"])

    def test_an_idea_absent_from_the_file_owes_citations(self) -> None:
        self.ideas()
        _file(self.root, {})
        state = citations.state(self.root)
        self.assertEqual(state["stages"]["proposal"]["owed"],
                         ["pillar:P1", "hypothesis:H1", "layer:Signal", "equation:1"])

    def test_an_extra_key_is_ignored(self) -> None:
        self.ideas()
        cite_everything(self.root)
        path = self.root / ".papersmith" / "citations.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["ideas"]["pillar:GONE"] = "not even a list"
        path.write_text(json.dumps(data), encoding="utf-8")
        state = citations.state(self.root)
        self.assertEqual(state["stages"]["proposal"]["owed"], [])
        self.assertNotIn("pillar:GONE", [i["key"] for i in state["ideas"]])

    def test_a_workspace_without_ideas_owes_nothing(self) -> None:
        state = citations.state(self.root)
        self.assertEqual(state["ideas"], [])
        self.assertEqual(state["stages"]["proposal"], {"ideas": 0, "cited": 0, "owed": []})
        self.assertEqual(state["stages"]["experiments"], {"ideas": 0, "cited": 0, "owed": []})

    def test_a_broken_file_owes_every_idea_and_never_raises(self) -> None:
        self.ideas()
        for body in ("{not json", '{"schema": 2, "ideas": {}}', '{"schema": 1, "ideas": []}', "[]"):
            with self.subTest(body=body):
                _write(self.root / ".papersmith" / "citations.json", body)
                state = citations.state(self.root)
                self.assertEqual(len(state["stages"]["proposal"]["owed"]), 4)
                self.assertTrue(state["file_problems"])

    def test_a_missing_or_broken_pool_cites_nothing(self) -> None:
        self.ideas()
        cite_everything(self.root)
        for body in (None, "{broken", '["a list"]'):
            with self.subTest(body=body):
                path = self.root / "sota-pool" / "candidates.json"
                path.unlink(missing_ok=True)
                if body is not None:
                    path.write_text(body, encoding="utf-8")
                self.assertEqual(len(citations.state(self.root)["stages"]["proposal"]["owed"]), 4)

    def test_a_citation_carries_the_pool_title_and_year(self) -> None:
        self.ideas()
        _file(self.root, {"pillar:P1": GOOD})
        idea = citations.state(self.root)["ideas"][0]
        self.assertEqual(idea["citations"][0], {"id": A, "why": GOOD[0]["why"], "title": POOL[0]["title"],
                                                "year": POOL[0]["year"], "authors": POOL[0]["authors"],
                                                "venue": POOL[0]["venue"]})


class IdeaKindTests(_Ideas):
    def keys(self) -> list[str]:
        return [i["key"] for i in citations.state(self.root)["ideas"]]

    def test_pillars_and_hypotheses_come_from_the_specification(self) -> None:
        self.ideas()
        self.assertIn("pillar:P1", self.keys())
        self.assertIn("hypothesis:H1", self.keys())

    def test_an_idea_without_an_id_takes_its_position(self) -> None:
        self.spec(pillars=[{"name": "A"}, {"name": "B"}], hypotheses=[{"statement": "H"}])
        self.assertEqual(self.keys(), ["pillar:P1", "pillar:P2", "hypothesis:H1"])

    def test_the_latest_overlay_is_the_fallback(self) -> None:
        sky = {"pillars": [{"id": "S1", "label": "Pillar"}], "hypotheses": [{"id": "SH", "statement": "H"}]}
        self.revision("# Old\n", 1, sky={"pillars": [{"id": "OLD", "label": "Gone"}]})
        self.revision("# New\n", 2, sky=sky)
        self.assertEqual(self.keys(), ["pillar:S1", "hypothesis:SH"])

    def test_layers_come_from_either_map(self) -> None:
        for field in ("concept_map", "conceptual_map"):
            with self.subTest(field=field):
                _write(self.root / ".papersmith" / "model_spec.json",
                       json.dumps({field: {"layers": [{"name": "Signal"}, {"layer": "Model"}]}}))
                self.assertEqual(self.keys(), ["layer:Signal", "layer:Model"])

    def test_equations_are_the_tagged_blocks_math_view_counts(self) -> None:
        text = ("$$\nx\n\\tag{1}\n$$\n\n$$\nuntagged\n$$\n\n```\n$$\nfenced\n\\tag{9}\n$$\n```\n\n"
                "$$\ny\n\\tag{2a}\n$$\n\n$$\nnever closed\n\\tag{3}\n")
        self.revision(text)
        self.assertEqual(self.keys(), ["equation:1", "equation:2a"])
        self.assertEqual(len(self.keys()), math_view.tagged_equation_count(text))

    def test_equations_are_read_from_the_latest_revision_only(self) -> None:
        self.revision("$$\nold\n\\tag{7}\n$$\n", 1)
        self.revision("$$\nnew\n\\tag{8}\n$$\n", 2)
        self.assertEqual(self.keys(), ["equation:8"])

    def test_experiments_are_the_headings_the_experiments_tab_parses(self) -> None:
        _write(self.root / "experiments" / "experiments-eeg-v01.md", MARKER + "## Experiment [exp:OLD] — Gone\n")
        _write(self.root / "experiments" / "experiments-eeg-v02.md", PROTOCOL)
        self.assertEqual(self.keys(), ["experiment:E1", "experiment:E2"])
        view = experiments_view.get_experiments_view(self.root)
        self.assertEqual([e["id"] for e in view["protocol"]["experiments"]], ["E1", "E2"])


class StepTests(_Ideas):
    def test_the_step_sits_between_the_mathematics_and_the_judge(self) -> None:
        self.assertEqual(phase_steps.STEP_IDS, ("problem_pillars", "hypotheses", "mathematics",
                                                "sota_citations", "neurips_review"))
        steps = self.steps()
        self.assertEqual(steps["sota_citations"]["requires"], "mathematics")
        self.assertEqual(steps["neurips_review"]["requires"], "sota_citations")
        self.assertEqual(steps["sota_citations"]["status"], "LOCKED")

    def test_it_opens_after_the_mathematics_and_holds_the_judge(self) -> None:
        self.ideas(contribution_type=TYPED)
        steps = self.steps()
        self.assertEqual(steps["sota_citations"]["status"], "ACTIVE")
        self.assertEqual(steps["sota_citations"]["evidence"]["ideas"], 4)
        self.assertEqual(steps["sota_citations"]["evidence"]["cited"], 0)
        self.assertEqual(steps["neurips_review"]["status"], "LOCKED")

    def test_it_passes_when_every_proposal_idea_is_cited(self) -> None:
        self.ideas(contribution_type=TYPED)
        cite_everything(self.root)
        steps = self.steps()
        self.assertEqual(steps["sota_citations"]["status"], "PASS")
        self.assertEqual(steps["sota_citations"]["evidence"]["cited"], 4)
        self.assertEqual(steps["neurips_review"]["status"], "PASS")

    def test_an_uncited_experiment_does_not_hold_the_proposal_step(self) -> None:
        self.ideas()
        cite_everything(self.root)
        _write(self.root / "experiments" / "experiments-eeg-v01.md", PROTOCOL)
        self.assertEqual(self.steps()["sota_citations"]["status"], "PASS")

    def test_phase_five_stays_locked_without_the_step(self) -> None:
        self.ideas(contribution_type=TYPED)
        fases = {f["stage_id"]: f for f in self.status()["fases"]}
        self.assertEqual(fases["proposal"]["status"], "ACTIVE")
        self.assertFalse(fases["poc_experiments"]["unlocked"])
        self.assertEqual(fases["poc_experiments"]["blocked_by"], "Fase 4")
        cite_everything(self.root)
        fases = {f["stage_id"]: f for f in self.status()["fases"]}
        self.assertEqual(fases["proposal"]["status"], "PASS")
        self.assertTrue(fases["poc_experiments"]["unlocked"])

    def test_the_phase_card_lists_the_step(self) -> None:
        self.ideas()
        sub = {s["id"]: s for s in self.fase4()["subfases"]}
        self.assertEqual((sub["4.7"]["name"], sub["4.7"]["status"]), ("Step 4: SOTA citations", "PENDING"))
        self.assertEqual((sub["4.8"]["name"], sub["4.8"]["status"]), ("Step 5: NeurIPS judge", "LOCKED"))

    def test_the_route_answers_read_only(self) -> None:
        self.ideas()
        _file(self.root, {"pillar:P1": GOOD})
        before = sorted(p.as_posix() for p in self.root.rglob("*"))
        body = TestClient(server.create_app(self.root, history_store=None)).get("/api/citations").json()
        self.assertEqual(body["stages"]["proposal"]["cited"], 1)
        self.assertEqual(body["ideas"][0]["citations"][1]["title"], POOL[1]["title"])
        self.assertEqual(sorted(p.as_posix() for p in self.root.rglob("*")), before)


class _Experiments(_Status):
    def setUp(self) -> None:
        super().setUp()
        _pool(self.root)
        _write(self.root / "experiments" / "experiments-eeg-v01.md", PROTOCOL)

    def cite(self) -> None:
        cite_everything(self.root)

    def poc(self) -> Path:
        product = self.product("Poc", "AGREED.md", discussion="complete")
        path = product / "Results" / "discussion.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        path.write_text(json.dumps({**data, "contribution_type": TYPED}), encoding="utf-8")
        return product

    def full(self) -> Path:
        product = self.product("Full", "Experimental_AGREED.md", discussion="complete")
        path = product / "Results" / "discussion.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        path.write_text(json.dumps({**data, "contribution_type": TYPED}), encoding="utf-8")
        return product

    def actions(self) -> list[dict]:
        wanted = ("/proposal-implementation", "/experimental-implementation")
        return [a for a in self.fase5()["actions"] if a.get("slash") in wanted]


class ExperimentLockTests(_Experiments):
    def test_uncited_experiments_lock_the_implementation_actions(self) -> None:
        found = self.actions()
        self.assertEqual(len(found), 3)
        self.assertTrue(all(a["locked"] for a in found))
        self.assertEqual({a["requires"] for a in found if a["slash"] == "/proposal-implementation"},
                         {"G-SOTA-CITATIONS"})

    def test_citations_unlock_the_proof_of_concept_but_not_the_full_run(self) -> None:
        self.cite()
        found = {a["label"]: a for a in self.actions()}
        self.assertFalse(found["Implement the proof of concept"]["locked"])
        self.assertFalse(found["Replication of comparison methods"]["locked"])
        full = found["Implement and measure the experiments"]
        self.assertEqual((full["locked"], full["requires"]), (True, "G-EXP-POC"))

    def test_the_full_action_names_the_citations_once_the_poc_is_verified(self) -> None:
        self.poc()
        self.cite()
        novelty_gate.record_decision(self.root, "approve", stage="poc")
        _file(self.root, {})
        full = next(a for a in self.actions() if a["slash"] == "/experimental-implementation")
        self.assertEqual((full["locked"], full["requires"]), (True, "G-SOTA-CITATIONS"))
        self.cite()
        self.assertFalse(next(a for a in self.actions() if a["slash"] == "/experimental-implementation")["locked"])

    def test_a_workspace_without_experiments_keeps_its_actions_open(self) -> None:
        (self.root / "experiments" / "experiments-eeg-v01.md").write_text(MARKER + "# E\n", encoding="utf-8")
        found = {a["label"]: a["locked"] for a in self.actions()}
        self.assertFalse(found["Implement the proof of concept"])

    def test_phase_five_cannot_pass_while_an_experiment_is_uncited(self) -> None:
        self.poc()
        self.full()
        self.cite()
        novelty_gate.record_decision(self.root, "approve", stage="poc")
        self.assertEqual(self.fase5()["status"], "PASS")
        _file(self.root, {})
        fase = self.fase5()
        self.assertEqual(fase["status"], "ACTIVE")
        self.assertLess(fase["progress"], 1.0)
        self.assertIn("experiments with SOTA citations: 0 of 2", fase["detail"])
        self.assertEqual(self.sub("SOTA citations of the experiments")["status"], "PENDING")

    def test_the_flow_says_what_the_experiments_owe(self) -> None:
        flow = TestClient(self.app).get("/api/experiments").json()["flow"]
        self.assertEqual(flow["citations"], {"ideas": 2, "cited": 0, "owed": 2})


class ApprovalTests(_Experiments):
    def test_the_poc_approval_refuses_and_records_nothing(self) -> None:
        self.poc()
        before = (self.root / ".papersmith" / "novelty_gate.json").exists()
        with self.assertRaises(novelty_gate.NoveltyRefusal) as ctx:
            novelty_gate.record_decision(self.root, "approve", stage="poc")
        self.assertEqual(ctx.exception.code, "SOTA_CITATIONS_OWED")
        self.assertIn("experiment:E1", ctx.exception.message)
        self.assertEqual(novelty_gate.read_gate(self.root)["poc"]["status"], "pending")
        self.assertEqual((self.root / ".papersmith" / "novelty_gate.json").exists(), before)

    def test_the_poc_approval_passes_with_every_experiment_cited(self) -> None:
        self.poc()
        self.cite()
        record = novelty_gate.record_decision(self.root, "approve", stage="poc")
        self.assertEqual(record["poc"]["status"], "approved")

    def test_smith_novelty_approve_refuses_with_its_code(self) -> None:
        self.poc()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = novelty_cli.main(["approve", "--root", str(self.root), "--gate", "poc"])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out.getvalue())["error"], "SOTA_CITATIONS_OWED")
        self.assertEqual(novelty_gate.read_gate(self.root)["poc"]["status"], "pending")

    def test_the_route_refuses_alike(self) -> None:
        self.poc()
        res = TestClient(self.app).post("/api/novelty/decision", json={"action": "approve", "stage": "poc"})
        self.assertEqual((res.status_code, res.json()["error"]), (422, "SOTA_CITATIONS_OWED"))
        self.assertEqual(novelty_gate.read_gate(self.root)["poc"]["status"], "pending")

    def test_an_iteration_never_needs_the_citations(self) -> None:
        self.poc()
        record = novelty_gate.record_decision(self.root, "iterate", stage="poc")
        self.assertEqual(record["poc"]["status"], "iterating")

    def test_the_judge_still_refuses_first(self) -> None:
        product = self.poc()
        path = product / "Results" / "discussion.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data.pop("contribution_type")
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(novelty_gate.NoveltyRefusal) as ctx:
            novelty_gate.record_decision(self.root, "approve", stage="poc")
        self.assertEqual(ctx.exception.code, "NEURIPS_JUDGE_OWED")


class CliTests(_Ideas):
    def run_cli(self, *args: str) -> tuple[int, dict]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = citations_cli.main(list(args))
        return code, json.loads(out.getvalue())

    def test_check_prints_what_is_owed_and_exits_non_zero(self) -> None:
        self.ideas()
        _file(self.root, {"pillar:P1": GOOD[:1]})
        code, body = self.run_cli("check", "--root", str(self.root))
        self.assertEqual(code, 1)
        self.assertEqual((body["ok"], body["error"]), (False, "SOTA_CITATIONS_OWED"))
        self.assertEqual((body["ideas"], body["cited"]), (4, 0))
        self.assertEqual(body["owed"][0], {"key": "pillar:P1", "problems": ["pillar:P1: 1 citation(s), needs 2 to 5"]})
        self.assertEqual([o["key"] for o in body["owed"]],
                         ["pillar:P1", "hypothesis:H1", "layer:Signal", "equation:1"])

    def test_check_passes_with_every_idea_cited(self) -> None:
        self.ideas()
        cite_everything(self.root)
        code, body = self.run_cli("check", "--root", str(self.root))
        self.assertEqual(code, 0)
        self.assertEqual((body["ok"], body["cited"], body["owed"]), (True, 4, []))

    def test_check_covers_the_experiments_too(self) -> None:
        self.ideas()
        cite_everything(self.root)
        _write(self.root / "experiments" / "experiments-eeg-v01.md", PROTOCOL)
        code, body = self.run_cli("check", "--root", str(self.root))
        self.assertEqual(code, 1)
        self.assertEqual([o["key"] for o in body["owed"]], ["experiment:E1", "experiment:E2"])

    def test_a_missing_root_refuses(self) -> None:
        code, body = self.run_cli("check", "--root", str(self.root / "absent"))
        self.assertEqual((code, body["error"]), (1, "ROOT_ABSENT"))

    def test_the_script_runs_by_path_and_writes_nothing(self) -> None:
        self.ideas()
        script = Path(citations_cli.__file__).resolve()
        done = subprocess.run(["python3", str(script), "check", "--root", "."], cwd=self.root,
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 1, done.stderr)
        self.assertEqual(json.loads(done.stdout)["error"], "SOTA_CITATIONS_OWED")
        self.assertFalse((self.root / ".papersmith" / "citations.json").exists())


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class ButtonTests(_Ideas):
    def test_the_step_button_types_the_command(self) -> None:
        self.ideas()
        result = render(phase_steps.proposal_steps(self.root), clicks=["sota_citations"])
        self.assertEqual(len(result["calls"]), 1)
        text, run, kind = result["calls"][0]
        self.assertTrue(text.startswith("/proposal-deliberation "))
        self.assertIn(".papersmith/citations.json", text)
        self.assertIn("citations_cli.py check", text)
        self.assertEqual((run, kind), (False, "slash"))

    def test_a_locked_step_sends_nothing_and_says_what_it_requires(self) -> None:
        for lang, reason in (("en", "Requires: Mathematics"), ("es", "Requiere: Matemática")):
            with self.subTest(lang=lang):
                result = render(phase_steps.proposal_steps(self.root), lang, clicks=["sota_citations"])
                self.assertEqual(result["calls"], [])
                self.assertIn(reason, result["html"])
                button = re.search(r'<button[^>]*data-model-step="sota_citations"[^>]*>', result["html"]).group(0)
                self.assertIn("disabled", button)

    def test_the_judge_now_waits_for_the_citations(self) -> None:
        self.ideas()
        result = render(phase_steps.proposal_steps(self.root), clicks=["neurips_review"])
        self.assertEqual(result["calls"], [])
        self.assertIn("Requires: SOTA citations", result["html"])


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class ExperimentsButtonTests(_Experiments):
    def view(self) -> dict:
        return TestClient(self.app).get("/api/experiments").json()

    @staticmethod
    def button(html: str, step: str) -> str:
        return re.search(rf'<button[^>]*data-exp-step="{step}"[^>]*>', html).group(0)

    def test_the_tab_types_the_deliberation_command(self) -> None:
        result = render_panel("experiments", self.view(), clicks=[["data-exp-step", "cite"]])
        self.assertNotIn("disabled", self.button(result["html"], "cite"))
        self.assertEqual(len(result["calls"]), 1)
        _, text, run, kind = result["calls"][0]
        self.assertTrue(text.startswith("/experimental-deliberation "))
        self.assertIn(".papersmith/citations.json", text)
        self.assertEqual((run, kind), (False, "slash"))

    def test_uncited_experiments_lock_both_implementation_buttons(self) -> None:
        for lang, reason in (("en", "Requires every experiment cited"), ("es", "Requiere citar cada experimento")):
            with self.subTest(lang=lang):
                result = render_panel("experiments", self.view(), lang,
                                      clicks=[["data-exp-step", "poc"], ["data-exp-step", "full"]])
                self.assertEqual(result["calls"], [])
                self.assertIn("disabled", self.button(result["html"], "poc"))
                self.assertIn("disabled", self.button(result["html"], "full"))
                self.assertIn(reason, result["html"])

    def test_cited_experiments_open_the_proof_of_concept(self) -> None:
        self.cite()
        result = render_panel("experiments", self.view(), clicks=[["data-exp-step", "poc"]])
        self.assertNotIn("disabled", self.button(result["html"], "poc"))
        self.assertTrue(result["calls"][0][1].startswith("/proposal-implementation "))

    def test_a_workspace_without_experiments_cannot_launch_the_step(self) -> None:
        (self.root / "experiments" / "experiments-eeg-v01.md").write_text(MARKER + "# E\n", encoding="utf-8")
        result = render_panel("experiments", self.view(), clicks=[["data-exp-step", "cite"]])
        self.assertEqual(result["calls"], [])
        self.assertIn("disabled", self.button(result["html"], "cite"))
        self.assertIn("Requires a protocol with experiments", result["html"])


PANELS = r"""
const fs = require('fs');
const els = {}; const ls = {}; let repaints = 0;
const [dir, lang] = process.argv.slice(1);
global.localStorage = { getItem: (k) => (k === 'papersmith-lang' ? lang : null), setItem() {} };
global.window = { localStorage: global.localStorage, location: { hash: '' }, addEventListener() {} };
const el = (id) => (els[id] = els[id] || { id, innerHTML: '', textContent: '', hidden: false, dataset: {},
  querySelectorAll: () => [], addEventListener() {}, classList: { add() {}, remove() {}, toggle() {} } });
global.document = { documentElement: { dataset: {} }, readyState: 'complete', querySelectorAll: () => [],
  getElementById: el, addEventListener: (k, f) => { (ls[k] = ls[k] || []).push(f); } };
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const answer = (body) => ({ ok: true, status: 200, json: async () => body });
global.fetch = async (url) => {
  if (url.startsWith('/api/citations')) return answer(input.citations);
  if (url.startsWith('/api/model/math')) return answer(input.math);
  if (url.startsWith('/api/experiments')) return answer(input.experiments);
  if (url.startsWith('/api/model/steps')) return answer({ steps: [] });
  return { ok: false, status: 404, json: async () => ({}) };
};
for (const f of ['i18n/en.js', 'i18n/es.js', 'i18n.js', 'citations.js', 'math-panel.js', 'model-panel.js', 'experiments-panel.js'])
  eval(fs.readFileSync(dir + '/' + f, 'utf8'));
(async () => {
  window.renderModelModules(input.spec);
  await window.refreshMathPanel();
  await window.refreshExperimentsPanel();
  await window.Citations.load();
  await new Promise((r) => setTimeout(r, 0));
  console.log(JSON.stringify({
    pillars: el('modelPillarGrid').innerHTML, hypotheses: el('modelHypothesisGrid').innerHTML,
    layers: el('modelConceptLayers').innerHTML, equations: el('mathStack').innerHTML,
    experiments: el('experimentsRoot').innerHTML,
  }));
})();
"""


def render_panels(payload: dict, lang: str = "en") -> dict:
    out = subprocess.run(["node", "-e", PANELS, str(STATIC), lang], input=json.dumps(payload),
                         capture_output=True, text=True, cwd=tempfile.gettempdir(), check=True)
    return json.loads(out.stdout)


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class PanelTests(_Ideas):
    HOSTILE = "<img src=x onerror=alert(1)>"

    def payload(self) -> dict:
        client = TestClient(server.create_app(self.root, history_store=None))
        return {"citations": client.get("/api/citations").json(), "spec": client.get("/api/model").json(),
                "math": client.get("/api/model/math").json(), "experiments": client.get("/api/experiments").json()}

    def all_ideas(self) -> None:
        self.ideas()
        _write(self.root / "experiments" / "experiments-eeg-v01.md", PROTOCOL)

    def test_each_panel_shows_title_year_and_why_beside_the_idea(self) -> None:
        self.all_ideas()
        cite_everything(self.root)
        result = render_panels(self.payload())
        for panel in ("pillars", "hypotheses", "layers", "equations", "experiments"):
            with self.subTest(panel=panel):
                self.assertIn(POOL[0]["title"], result[panel])
                self.assertIn(str(POOL[0]["year"]), result[panel])
                self.assertIn("Cited for the test.", result[panel])
                self.assertIn("SOTA citations", result[panel])

    def test_spanish_names_the_block(self) -> None:
        self.all_ideas()
        cite_everything(self.root)
        result = render_panels(self.payload(), "es")
        for panel in ("pillars", "hypotheses", "layers", "equations", "experiments"):
            with self.subTest(panel=panel):
                self.assertIn("Citas del SOTA", result[panel])

    def test_an_idea_that_owes_citations_is_marked(self) -> None:
        self.all_ideas()
        for lang, mark in (("en", "Owes 2 to 5 SOTA citations"), ("es", "Debe de 2 a 5 citas del SOTA")):
            result = render_panels(self.payload(), lang)
            for panel in ("pillars", "hypotheses", "layers", "equations", "experiments"):
                with self.subTest(lang=lang, panel=panel):
                    self.assertIn(mark, result[panel])

    def test_every_value_is_escaped(self) -> None:
        self.all_ideas()
        _pool(self.root, {"identifier": "10.1000/evil", "title": self.HOSTILE, "year": self.HOSTILE})
        cite_everything(self.root)
        path = self.root / ".papersmith" / "citations.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        hostile = [{"id": "10.1000/evil", "why": self.HOSTILE}, {"id": A, "why": self.HOSTILE}]
        data["ideas"] = {key: hostile for key in data["ideas"]}
        path.write_text(json.dumps(data), encoding="utf-8")
        result = render_panels(self.payload())
        for panel in ("pillars", "hypotheses", "layers", "equations", "experiments"):
            with self.subTest(panel=panel):
                self.assertIn("&lt;img", result[panel])
                self.assertNotIn("<img", result[panel])


class CatalogueTests(unittest.TestCase):
    def test_both_catalogues_carry_the_keys(self) -> None:
        for name in ("en.js", "es.js"):
            text = (STATIC / "i18n" / name).read_text(encoding="utf-8")
            for key in ("citations.title", "citations.owed", "modelSteps.sotaCitations", "modelSteps.cite",
                        "modelSteps.citeAgain", "modelSteps.evidence.sotaCitations", "exp.flow.cite",
                        "exp.flow.citeBody", "exp.flow.citeButton", "exp.flow.requiresProtocol",
                        "exp.flow.requiresCitations"):
                with self.subTest(file=name, key=key):
                    self.assertIn(f'"{key}":', text)

    def test_the_script_loads_before_the_panels_with_their_token(self) -> None:
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        token = re.search(r'math-panel\.js\?v=([^"]+)"', html).group(1)
        self.assertIn(f'./citations.js?v={token}"', html)
        self.assertLess(html.index("./citations.js"), html.index("./math-panel.js"))


class FlowTextTests(unittest.TestCase):
    def test_the_skills_state_the_rule(self) -> None:
        repo = Path(server.__file__).resolve().parents[3]
        for skill in ("proposal-deliberation", "experimental-deliberation"):
            text = (repo / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")
            with self.subTest(skill=skill):
                self.assertIn(".papersmith/citations.json", text)
                self.assertIn("citations_cli.py check --root .", text)


class ApprovalButtonTests(unittest.TestCase):
    def test_the_poc_approval_is_disabled_while_an_experiment_owes_citations(self) -> None:
        script = (
            "const fs=require('fs');const els={};"
            "global.localStorage={getItem:()=>'en',setItem(){}};"
            "global.window={localStorage:global.localStorage,location:{hash:''},addEventListener(){}};"
            "global.CustomEvent=function(){};"
            "global.document={readyState:'complete',documentElement:{},addEventListener(){},dispatchEvent(){},"
            "querySelectorAll:()=>[],getElementById:(i)=>(els[i]=els[i]||{innerHTML:'',hidden:false})};"
            "for (const f of ['i18n/en.js','i18n/es.js','i18n.js','novelty-panel.js'])"
            " eval(fs.readFileSync(process.argv[1]+'/'+f,'utf8'));"
            "window.NoveltyPanel.render(JSON.parse(fs.readFileSync(0,'utf8')));"
            "console.log(els.noveltyRoot.innerHTML);")
        static = Path(server.__file__).resolve().parent / "static"

        def page(owed: list[str]) -> str:
            overview = {"hypotheses": [], "discussions": [], "limitations": [],
                        "poc_verification": {"discussed": 1, "decision": {"status": "pending"}},
                        "judge": {}, "experiment_citations_owed": owed}
            return subprocess.run(["node", "-e", script, str(static)], input=json.dumps(overview),
                                  capture_output=True, text=True, cwd=tempfile.gettempdir(), check=True).stdout

        def button(html: str) -> str:
            return next(b for b in re.findall(r"<button[^>]*>", html)
                        if "sendNoveltyDecision('approve', 'poc')" in b)

        owing = page(["experiment:E1"])
        self.assertIn("disabled", button(owing))
        self.assertIn("2 to 5 SOTA citations", owing)
        self.assertNotIn("disabled", button(page([])))


if __name__ == "__main__":
    unittest.main()
