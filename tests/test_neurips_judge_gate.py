"""The NeurIPS judge is a step the flow cannot skip.

The paper-reviewer's contribution type is step 4 of Phase 4, so Phase 5 stays
locked until the proposal carries one. A proof of concept or a full experiment
with a complete discussion and no type refuses its approval, in the dashboard
and in `smith novelty`. Each panel offers the button that launches the judge
right where its verdict appears."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from skills._core.command_center import phase_steps, server
from skills._core.results import novelty_cli, novelty_gate
from tests.test_flow_gating_phase4 import EQUATION, _Workspace as _Phase4, _write, render
from tests.test_phase5_review import _Status, _write_discussion

STATIC = Path(server.__file__).resolve().parent / "static"
TYPED = {"type": "Theory", "why": "The core is a bound."}


class _Proposal(_Phase4):
    def ready(self, **extra) -> None:
        spec = {"novelty": {"problem_statement": "Gap.", "pillars": [{"name": "P1"}],
                            "hypotheses": [{"statement": "H1"}]}, **extra}
        _write(self.root / ".papersmith" / "model_spec.json", json.dumps(spec))
        self.revision(EQUATION)


class ProposalStepTests(_Proposal):
    def test_the_judge_is_the_fourth_step_and_needs_the_mathematics(self) -> None:
        steps = phase_steps.proposal_steps(self.root)
        self.assertEqual(steps[-1]["id"], "neurips_review")
        self.assertEqual((steps[-1]["status"], steps[-1]["requires"]), ("LOCKED", "mathematics"))

    def test_it_opens_after_the_mathematics_and_passes_with_a_valid_type(self) -> None:
        self.ready()
        self.assertEqual(self.steps()["neurips_review"]["status"], "ACTIVE")
        self.ready(contribution_type={"type": "Survey", "why": "x"})
        self.assertEqual(self.steps()["neurips_review"]["status"], "ACTIVE")
        self.ready(contribution_type=TYPED)
        step = self.steps()["neurips_review"]
        self.assertEqual((step["status"], step["evidence"]["type"]), ("PASS", "Theory"))

    def test_phase_four_waits_for_the_judge_and_phase_five_with_it(self) -> None:
        self.ready()
        fases = {f["stage_id"]: f for f in self.status()["fases"]}
        self.assertEqual(fases["proposal"]["status"], "ACTIVE")
        self.assertFalse(fases["poc_experiments"]["unlocked"])
        self.assertEqual(fases["poc_experiments"]["blocked_by"], "Fase 4")
        self.ready(contribution_type=TYPED)
        fases = {f["stage_id"]: f for f in self.status()["fases"]}
        self.assertEqual(fases["proposal"]["status"], "PASS")
        self.assertTrue(fases["poc_experiments"]["unlocked"])

    def test_the_phase_card_lists_the_judge_as_a_sub_phase(self) -> None:
        self.ready()
        sub = {s["id"]: s for s in self.fase4()["subfases"]}
        self.assertEqual(sub["4.7"]["status"], "PENDING")


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class ConceptMapButtonTests(_Proposal):
    def test_the_step_button_types_the_judge_command(self) -> None:
        self.ready()
        result = render(phase_steps.proposal_steps(self.root), clicks=["neurips_review"])
        self.assertEqual(len(result["calls"]), 1)
        text, run, kind = result["calls"][0]
        self.assertTrue(text.startswith("/proposal-deliberation "))
        self.assertIn("paper-reviewer", text)
        self.assertIn("contribution_type", text)
        self.assertEqual((run, kind), (False, "slash"))

    def test_a_locked_judge_sends_nothing_and_says_what_it_requires(self) -> None:
        result = render(phase_steps.proposal_steps(self.root), clicks=["neurips_review"])
        self.assertEqual(result["calls"], [])
        self.assertIn("Requires: Mathematics", result["html"])
        button = re.search(r'<button[^>]*data-model-step="neurips_review"[^>]*>', result["html"]).group(0)
        self.assertIn("disabled", button)

    def test_the_verdict_card_carries_the_button_where_the_type_appears(self) -> None:
        self.ready()
        script = (
            "const fs=require('fs');const els={};const ls={};"
            "global.localStorage={getItem:()=>'en',setItem(){}};"
            "global.window={localStorage:global.localStorage};"
            "global.fetch=undefined;"
            "global.document={getElementById:(i)=>(els[i]=els[i]||{innerHTML:'',hidden:false}),"
            "querySelectorAll:()=>[],addEventListener(){}};"
            f"for (const f of ['i18n/en.js','i18n/es.js','i18n.js','model-panel.js'])"
            f" eval(fs.readFileSync({json.dumps(str(STATIC))}+'/'+f,'utf8'));"
            "const steps=JSON.parse(fs.readFileSync(0,'utf8'));"
            "window.renderModelModules({title:'x'});window.renderModelSteps(steps);"
            "console.log(els.modelContributionType.innerHTML);")
        html = subprocess.run(["node", "-e", script], input=json.dumps(phase_steps.proposal_steps(self.root)),
                              capture_output=True, text=True, cwd=tempfile.gettempdir(), check=True).stdout
        button = re.search(r'<button[^>]*data-model-step="neurips_review"[^>]*>', html).group(0)
        self.assertNotIn("disabled", button)


class _Stages(_Status):
    def poc(self, typed: bool = False) -> Path:
        product = self.product("Poc", "AGREED.md", discussion="complete")
        self.set_type(product, TYPED if typed else None)
        return product

    def full(self, typed: bool = False) -> Path:
        product = self.product("Full", "Experimental_AGREED.md", discussion="complete")
        self.set_type(product, TYPED if typed else None)
        return product

    @staticmethod
    def set_type(product: Path, kind: dict | str | None) -> None:
        path = product / "Results" / "discussion.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data.pop("contribution_type", None)
        if kind:
            data["contribution_type"] = kind
        path.write_text(json.dumps(data), encoding="utf-8")


class ApprovalTests(_Stages):
    def test_a_poc_approval_refuses_until_the_judge_ran_and_records_nothing(self) -> None:
        product = self.poc()
        with self.assertRaises(novelty_gate.NoveltyRefusal) as ctx:
            novelty_gate.record_decision(self.root, "approve", stage="poc")
        self.assertEqual(ctx.exception.code, "NEURIPS_JUDGE_OWED")
        self.assertIn("Poc", ctx.exception.message)
        self.assertEqual(novelty_gate.read_gate(self.root)["poc"]["status"], "pending")
        self.set_type(product, TYPED)
        record = novelty_gate.record_decision(self.root, "approve", stage="poc")
        self.assertEqual(record["poc"]["status"], "approved")

    def test_a_full_approval_refuses_until_the_judge_ran(self) -> None:
        product = self.full()
        with self.assertRaises(novelty_gate.NoveltyRefusal) as ctx:
            novelty_gate.record_decision(self.root, "approve")
        self.assertEqual(ctx.exception.code, "NEURIPS_JUDGE_OWED")
        self.assertEqual(novelty_gate.read_gate(self.root)["status"], "pending")
        self.set_type(product, TYPED)
        self.assertEqual(novelty_gate.record_decision(self.root, "approve")["status"], "approved")

    def test_a_malformed_type_does_not_skip_the_judge(self) -> None:
        for kind in ({"type": "Survey", "why": "x"}, {"type": "Theory", "why": " "}, "Theory"):
            with self.subTest(kind=kind):
                product = self.full()
                self.set_type(product, kind)
                self.assertEqual(novelty_gate.judge_state(self.root)["full"]["owed"], ["Full"])
                with self.assertRaises(novelty_gate.NoveltyRefusal) as ctx:
                    novelty_gate.record_decision(self.root, "approve")
                self.assertEqual(ctx.exception.code, "NEURIPS_JUDGE_OWED")

    def test_an_iteration_never_needs_the_judge(self) -> None:
        self.poc()
        self.full()
        self.assertEqual(novelty_gate.record_decision(self.root, "iterate", stage="poc")["poc"]["status"],
                         "iterating")
        self.assertEqual(novelty_gate.record_decision(self.root, "iterate_experiments")["status"],
                         "iterating_experiments")

    def test_the_cli_and_the_route_refuse_alike(self) -> None:
        self.poc()
        self.assertEqual(novelty_cli.main(["approve", "--root", str(self.root), "--gate", "poc"]), 1)
        res = TestClient(self.app).post("/api/novelty/decision", json={"action": "approve", "stage": "poc"})
        self.assertEqual((res.status_code, res.json()["error"]), (422, "NEURIPS_JUDGE_OWED"))

    def test_the_overview_says_what_each_stage_owes(self) -> None:
        self.poc()
        self.full(typed=True)
        judge = novelty_gate.get_novelty_overview(self.root)["judge"]
        self.assertEqual(judge["poc"], {"complete": 1, "owed": ["Poc"]})
        self.assertEqual(judge["full"], {"complete": 1, "owed": []})


NOVELTY = """
const fs = require('fs');
const els = {}; const calls = [];
global.localStorage = { getItem: () => 'en', setItem() {} };
global.window = { localStorage: global.localStorage, location: { hash: '' }, addEventListener() {},
  sendToCli: (text, run, opts) => { calls.push([text, run, opts && opts.kind]); return true; } };
global.CustomEvent = function () {};
global.document = { readyState: 'complete', documentElement: {}, addEventListener() {}, dispatchEvent() {},
  querySelectorAll: () => [], getElementById: (id) => (els[id] = els[id] || { innerHTML: '', hidden: false }) };
for (const f of ['i18n/en.js', 'i18n/es.js', 'i18n.js', 'novelty-panel.js'])
  eval(fs.readFileSync(process.argv[1] + '/' + f, 'utf8'));
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
window.NoveltyPanel.render(input.overview);
for (const stage of input.clicks) window.launchNoveltyJudge(stage);
console.log(JSON.stringify({ html: els.noveltyRoot.innerHTML, calls }));
"""


def render_novelty(overview: dict, clicks: list[str] | None = None) -> dict:
    out = subprocess.run(["node", "-e", NOVELTY, str(STATIC)],
                         input=json.dumps({"overview": overview, "clicks": clicks or []}),
                         capture_output=True, text=True, cwd=tempfile.gettempdir(), check=True)
    return json.loads(out.stdout)


def _button(html: str, needle: str) -> str:
    return next(b for b in re.findall(r"<button[^>]*>", html) if needle in b)


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class NoveltyButtonTests(_Stages):
    def overview(self) -> dict:
        return novelty_gate.get_novelty_overview(self.root)

    def test_a_stage_that_owes_the_judge_offers_it_and_locks_its_approval(self) -> None:
        self.poc()
        result = render_novelty(self.overview(), clicks=["poc"])
        card = result["html"][result["html"].index('id="noveltyContributionType"'):]
        self.assertIn("launchNoveltyJudge('poc')", card)
        self.assertIn("disabled", _button(result["html"], "sendNoveltyDecision('approve', 'poc')"))
        self.assertEqual(len(result["calls"]), 1)
        text, run, kind = result["calls"][0]
        self.assertTrue(text.startswith("/proposal-implementation "))
        self.assertIn("paper-reviewer", text)
        self.assertEqual((run, kind), (False, "slash"))

    def test_the_full_stage_launches_from_the_experiment_skill(self) -> None:
        self.full()
        result = render_novelty(self.overview(), clicks=["full"])
        self.assertTrue(result["calls"][0][0].startswith("/experimental-implementation "))
        self.assertIn("disabled", _button(result["html"], "sendNoveltyDecision('approve')"))

    def test_a_judged_stage_keeps_its_approval_open(self) -> None:
        self.poc(typed=True)
        html = render_novelty(self.overview())["html"]
        self.assertNotIn("disabled", _button(html, "sendNoveltyDecision('approve', 'poc')"))

    def test_without_a_complete_discussion_nothing_is_sent(self) -> None:
        result = render_novelty({"hypotheses": [], "discussions": [], "limitations": []}, clicks=["poc", "full"])
        self.assertEqual(result["calls"], [])
        self.assertIn("disabled", _button(result["html"], "data-novelty-judge"))


class CatalogueTests(unittest.TestCase):
    def test_both_catalogues_carry_the_judge_keys(self) -> None:
        for name in ("en.js", "es.js"):
            text = (STATIC / "i18n" / name).read_text(encoding="utf-8")
            for key in ("modelSteps.neuripsReview", "modelSteps.judge", "modelSteps.judgeAgain",
                        "modelSteps.evidence.neuripsReview", "modelSteps.evidence.neuripsOwed",
                        "novelty.judge.launchPoc", "novelty.judge.launchFull", "novelty.judge.againPoc",
                        "novelty.judge.againFull", "novelty.judge.owed", "novelty.judge.needsDiscussion",
                        "novelty.judge.approvalLocked"):
                with self.subTest(file=name, key=key):
                    self.assertIn(f'"{key}":', text)


if __name__ == "__main__":
    unittest.main()
