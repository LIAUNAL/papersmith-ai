"""Phase 5 (proof of concept and experiments), reviewed end to end.

The phase passes from evidence on disk, never from a file name: a published
managed experiments revision, a proof of concept and a full experiment that
each close with a complete ``Results/discussion.json``. Each sub-phase carries its own evidence, the gate
names a reviewer that exists, the remote rehearsal and the operator's launch
are their own steps, the Kaggle host counts one validated account per team
owner, the help box states the verbs in the order they run, and run-option
labels state one unit per range.
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from skills._core.command_center import phase_actions, remote_services, run_options, server

REPO = Path(__file__).resolve().parents[1]
PANEL = REPO / "skills/_core/command_center/static/experiments-panel.js"
MARKER = "<!-- proposal-workspace:artifact:v1 -->\n"
KAGGLE = remote_services.RUN_HOSTS[1]


def _write(path: Path, text: str = "ok\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _discussion(stage: str, verdict: str = "supported") -> dict:
    """A minimal discussion that cites only the evidence ``_write_discussion`` lays down."""
    return {
        "schema": 1, "stage": stage, "protocol": "experiments/experiments-eeg-v01.md",
        "generated_at": "2026-10-30T00:00:00Z",
        "summary": "The hybrid model beats the linear baseline.",
        "discussion_type": ["comparative"],
        "metrics": [{"name": "balanced_accuracy", "role": "primary", "why": "Classes are imbalanced.",
                     "source": "Results/figures/acc.png"}],
        "hypotheses": [{"id": "H1", "experiment": "E1", "statement": "The hybrid model beats the baseline.",
                        "metric": "balanced_accuracy", "test": "Wilcoxon signed-rank",
                        "criterion": "At least 0.85", "observed": "0.87",
                        "evidence": ["significance:hybrid vs linear", "Results/figures/acc.png"],
                        "verdict": verdict, "rationale": "The criterion is met."}],
        "novelty": {"claim": "Hybrid encoding is new.", "verdict": "justified",
                    "evidence": ["significance:hybrid vs linear"], "rationale": "It beats the baseline."},
        "qualitative_not_applicable": "No interpretable component in this stage.",
        "limitations": [], "next_steps": [],
    }


def _write_discussion(folder: Path, stage: str, verdict: str = "supported") -> None:
    """The discussion plus the evidence files it cites (a figure and a significance file)."""
    _write(folder / "Results" / "figures" / "acc.png")
    _write(folder / "Results" / "significance.json",
           json.dumps([{"comparison": "hybrid vs linear", "p_value": 0.01}]))
    _write(folder / "Results" / "discussion.json", json.dumps(_discussion(stage, verdict)))


def _help_source() -> str:
    en_js = REPO / "skills/_core/command_center/static/i18n/en.js"
    return en_js.read_text(encoding="utf-8")


class _Status(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.root = Path(holder.name).resolve() / "ws"
        self.root.mkdir()
        self.app = server.create_app(self.root, history_store=None)

    def status(self) -> dict:
        route = next(r.endpoint for r in self.app.routes if getattr(r, "path", None) == "/api/status")
        return json.loads(bytes(route().body))

    def fase5(self) -> dict:
        return next(f for f in self.status()["fases"] if f["stage_id"] == "poc_experiments")

    def sub(self, prefix: str) -> dict:
        return next(s for s in self.fase5()["subfases"] if s["name"].startswith(prefix))

    def protocol(self, marked: bool = True) -> None:
        _write(self.root / "experiments" / "experiments-eeg-v01.md", (MARKER if marked else "") + "# E\n")

    def product(self, name: str, marker: str, results: bool = True, discussion: str | None = None) -> Path:
        """A product folder; ``discussion`` is ``None`` (a bare ``Results/``), ``"draft"`` or ``"complete"``."""
        folder = self.root / "implementations" / "repo" / name
        _write(folder / marker)
        if results:
            (folder / "Results").mkdir(parents=True, exist_ok=True)
        if discussion:
            stage = "full" if marker == "Experimental_AGREED.md" else "poc"
            _write_discussion(folder, stage, "supported" if discussion == "complete" else "pending")
        return folder

    def report(self, folder: Path, body: object, name: str = "reviewer_report.json") -> None:
        _write(folder / "Results" / name, json.dumps(body))


class Phase5StatusFromEvidenceTests(_Status):
    def test_nothing_on_disk_is_pending(self) -> None:
        self.assertEqual(self.fase5()["status"], "PENDING")

    def test_a_file_name_containing_poc_is_not_evidence(self) -> None:
        _write(self.root / "experiments" / "poc-notes.md")
        _write(self.root / "experiments" / "validation-plan.md")
        self.assertNotEqual(self.fase5()["status"], "PASS")

    def test_a_published_revision_alone_is_active(self) -> None:
        self.protocol()
        self.assertEqual(self.fase5()["status"], "ACTIVE")

    def test_an_unmarked_revision_is_not_published(self) -> None:
        self.protocol(marked=False)
        self.product("Poc", "AGREED.md")
        self.product("Full", "Experimental_AGREED.md")
        self.assertEqual(self.fase5()["status"], "ACTIVE")

    def test_revision_poc_and_full_discussions_pass(self) -> None:
        self.protocol()
        self.product("Poc", "AGREED.md", discussion="complete")
        self.product("Full", "Experimental_AGREED.md", discussion="complete")
        fase = self.fase5()
        self.assertEqual((fase["status"], fase["progress"]), ("PASS", 1.0))

    def test_bare_results_folders_no_longer_pass_the_phase(self) -> None:
        self.protocol()
        self.product("Poc", "AGREED.md")
        self.product("Full", "Experimental_AGREED.md")
        fase = self.fase5()
        self.assertEqual(fase["status"], "ACTIVE")
        self.assertAlmostEqual(fase["progress"], 0.333, places=3)

    def test_a_product_without_results_does_not_count(self) -> None:
        self.protocol()
        self.product("Poc", "AGREED.md", discussion="complete")
        self.product("Full", "Experimental_AGREED.md", results=False)
        self.assertEqual(self.fase5()["status"], "ACTIVE")

    def test_the_phase_detail_counts_discussed_products(self) -> None:
        self.protocol()
        self.product("Poc", "AGREED.md", discussion="complete")
        self.product("Poc2", "AGREED.md")
        detail = self.fase5()["detail"]
        self.assertIn("1 of 2", detail)
        self.assertIn("discussion", detail)

    def test_each_sub_phase_reads_its_own_evidence(self) -> None:
        self.protocol()
        self.assertEqual(self.sub("Stage published")["status"], "PASS")
        self.assertEqual(self.sub("Data:")["status"], "PENDING")
        _write(self.root / "datasets" / "registry.json", json.dumps([{"slug": "toy", "role": "toy"}]))
        self.assertEqual(self.sub("Data:")["status"], "PASS")
        self.assertEqual(self.sub("Replication")["status"], "PENDING")
        _write(self.root / "implementations" / "repo" / "Baseline" / "REPLICATION.md")
        self.assertEqual(self.sub("Replication")["status"], "PASS")
        self.assertEqual(self.sub("Proof of concept")["status"], "PENDING")
        poc = self.product("Poc", "AGREED.md", discussion="complete")
        self.assertEqual(self.sub("Proof of concept")["status"], "PASS")
        self.assertEqual(self.sub("Estimate the time")["status"], "PENDING")
        _write(poc / "Results" / "timing.json", "{}")
        self.assertEqual(self.sub("Estimate the time")["status"], "PASS")
        self.assertEqual(self.sub("Full experiments")["status"], "PENDING")
        self.product("Full", "Experimental_AGREED.md", discussion="complete")
        self.assertEqual(self.sub("Full experiments")["status"], "PASS")
        self.assertEqual(self.sub("Remote rehearsal")["status"], "PENDING")
        _write(poc / ".remote-execution" / "ledger.jsonl", '{"kind": "submitted"}\n')
        self.assertEqual(self.sub("Remote rehearsal")["status"], "PASS")

    def test_the_reviewer_sub_phase_reads_the_reviewer_report(self) -> None:
        self.protocol()
        poc = self.product("Poc", "AGREED.md", discussion="complete")
        review = self.sub("Code review")
        self.assertEqual(review["status"], "PENDING")
        self.assertNotIn("leaves no file", review["detail"])
        self.assertIn("Results/reviewer_report.json", review["detail"])
        self.report(poc, {"status": "open", "summary": {"blockers": 2, "blockers_resolved": 1}})
        self.assertEqual(self.sub("Code review")["status"], "ACTIVE")
        self.report(poc, {"status": "resolved"})
        self.assertEqual(self.sub("Code review")["status"], "PASS")

    def test_a_report_with_every_blocker_resolved_passes(self) -> None:
        folder = self.product("Full", "Experimental_AGREED.md")
        self.report(folder, {"summary": {"blockers": 3, "blockers_resolved": 3}}, "reviewer-report.json")
        self.assertEqual(self.sub("Code review")["status"], "PASS")

    def test_a_report_that_is_not_an_object_is_no_report(self) -> None:
        folder = self.product("Poc", "AGREED.md")
        self.report(folder, ["resolved"])
        self.assertEqual(self.sub("Code review")["status"], "PENDING")
        _write(folder / "Results" / "reviewer_report.json", "{not json")
        self.assertEqual(self.sub("Code review")["status"], "PENDING")


class Phase5DiscussionGatesTests(_Status):
    DETAIL_PIECES = ("complete Results/discussion.json", "hypothesis verdicts",
                     "python skills/_core/results/discussion_cli.py check --product")

    def test_a_bare_results_folder_is_active_not_pass(self) -> None:
        self.product("Poc", "AGREED.md")
        sub = self.sub("Proof of concept")
        self.assertEqual(sub["status"], "ACTIVE")
        self.assertIn("0 of 1", sub["detail"])

    def test_a_draft_discussion_is_active(self) -> None:
        self.product("Poc", "AGREED.md", discussion="draft")
        self.assertEqual(self.sub("Proof of concept")["status"], "ACTIVE")

    def test_an_invalid_discussion_is_active(self) -> None:
        folder = self.product("Poc", "AGREED.md")
        _write(folder / "Results" / "discussion.json", json.dumps({"schema": 1}))
        self.assertEqual(self.sub("Proof of concept")["status"], "ACTIVE")
        _write(folder / "Results" / "discussion.json", "{broken")
        self.assertEqual(self.sub("Proof of concept")["status"], "ACTIVE")

    def test_a_complete_discussion_passes_and_states_the_counts(self) -> None:
        self.product("Poc", "AGREED.md", discussion="complete")
        self.product("Poc2", "AGREED.md", discussion="draft")
        sub = self.sub("Proof of concept")
        self.assertEqual(sub["status"], "PASS")
        self.assertIn("1 of 2", sub["detail"])
        for piece in self.DETAIL_PIECES:
            with self.subTest(piece=piece):
                self.assertIn(piece, sub["detail"])
        self.assertIn("AGREED.md", sub["detail"])

    def test_without_a_poc_the_sub_phase_is_pending(self) -> None:
        self.assertEqual(self.sub("Proof of concept")["status"], "PENDING")

    def test_the_full_stage_follows_the_same_rule(self) -> None:
        self.assertEqual(self.sub("Full experiments")["status"], "PENDING")
        folder = self.product("Full", "Experimental_AGREED.md")
        self.assertEqual(self.sub("Full experiments")["status"], "ACTIVE")
        _write_discussion(folder, "full", "pending")
        self.assertEqual(self.sub("Full experiments")["status"], "ACTIVE")
        _write_discussion(folder, "full")
        sub = self.sub("Full experiments")
        self.assertEqual(sub["status"], "PASS")
        self.assertIn("1 of 1", sub["detail"])
        self.assertIn("Experimental_AGREED.md", sub["detail"])

    def test_a_full_discussion_without_a_significance_test_is_not_complete(self) -> None:
        folder = self.product("Full", "Experimental_AGREED.md")
        _write_discussion(folder, "full")
        (folder / "Results" / "significance.json").unlink()
        self.assertEqual(self.sub("Full experiments")["status"], "ACTIVE")

    def test_a_poc_discussion_does_not_pass_the_full_sub_phase(self) -> None:
        self.product("Poc", "AGREED.md", discussion="complete")
        self.assertEqual(self.sub("Full experiments")["status"], "PENDING")

    def test_the_evidence_counts_discussed_drafts_and_reviews(self) -> None:
        poc = self.product("Poc", "AGREED.md", discussion="complete")
        self.product("Poc2", "AGREED.md", discussion="draft")
        self.product("Poc3", "AGREED.md")
        full = self.product("Full", "Experimental_AGREED.md", discussion="complete")
        self.report(poc, {"status": "resolved"})
        self.report(full, {"status": "open"})
        evidence = server._phase5_evidence(self.root)
        self.assertEqual((evidence["poc"], evidence["poc_discussed"], evidence["poc_discussion_drafts"]), (3, 1, 1))
        self.assertEqual((evidence["full"], evidence["full_discussed"], evidence["full_discussion_drafts"]), (1, 1, 0))
        self.assertEqual((evidence["reviewed"], evidence["review_reports"]), (1, 2))

    def test_the_gate_criteria_name_verdicts_tests_novelty_and_the_discussion(self) -> None:
        gate = next(g for g in self.status()["gates"] if g["id"] == "G-EXP-POC")
        criteria = gate["criteria"].lower()
        for needle in ("hypothesis", "novelty", "qualitative", "discussion", "reproducibility",
                       "baseline", "success criteria"):
            with self.subTest(needle=needle):
                self.assertIn(needle, criteria)

    def test_the_gate_follows_the_phase(self) -> None:
        self.protocol()
        self.product("Poc", "AGREED.md")
        self.product("Full", "Experimental_AGREED.md")
        gate = next(g for g in self.status()["gates"] if g["id"] == "G-EXP-POC")
        self.assertEqual(gate["status"], "ACTIVE")


class Phase5NamesAndOrderTests(_Status):
    def test_the_gate_names_a_reviewer_that_exists(self) -> None:
        gate = next(g for g in self.status()["gates"] if g["id"] == "G-EXP-POC")
        self.assertEqual(gate["reviewer"], "experiments-reviewer")
        self.assertTrue((REPO / ".claude" / "agents" / "experiments-reviewer.md").is_file())

    def test_the_phase_name_matches_its_label_and_names_agents(self) -> None:
        fase = self.fase5()
        self.assertEqual(fase["name"], f"Phase 5: {phase_actions.PHASE_LABELS['poc_experiments']}")
        for agent in re.split(r"[^a-z-]+", fase["agent"]):
            if agent:
                with self.subTest(agent=agent):
                    self.assertTrue((REPO / ".claude" / "agents" / f"{agent}.md").is_file())

    def test_sub_phases_follow_the_one_order(self) -> None:
        subs = self.fase5()["subfases"]
        self.assertEqual([s["id"] for s in subs], [f"5.{i}" for i in range(1, len(subs) + 1)])
        names = [s["name"] for s in subs]
        order = ["Stage published", "Data:", "Replication", "Proof of concept", "Estimate the time",
                 "Full experiments", "Code review (experiments-reviewer) before the rehearsal",
                 "Remote rehearsal and launch authorization (operator)"]
        found = [next(i for i, n in enumerate(names) if n.startswith(p)) for p in order]
        self.assertEqual(found, sorted(found))
        estimate = subs[found[4]]["detail"]
        self.assertIn("before the pilot and again before the full run", estimate.lower())
        rehearsal = subs[found[7]]["detail"]
        verbs = ["generate-job", "submit --smoke", "fetch --smoke", "readiness", "gate", "submit ", "status",
                 "fetch"]
        positions = []
        start = 0
        for verb in verbs:
            start = rehearsal.index(verb, start)
            positions.append(start)
        self.assertEqual(positions, sorted(positions))

    def test_phase_actions_follow_the_same_order(self) -> None:
        actions = phase_actions.ACTIONS["poc_experiments"]["actions"]
        keys = [a.get("slash") or a["label"] for a in actions]
        order = ["/experimental-deliberation", "/datasets", "Replication of comparison methods",
                 "Implement the proof of concept", "Estimate the time and choose where to run",
                 "/hyperparameter-search", "Implement and measure the experiments", "/remote-parallelism", "/kaggle-accounts", "/remote-execution"]
        index = []
        for key in order:
            index.append(next(i for i, a in enumerate(actions)
                              if a.get("slash") == key or a["label"] == key))
        self.assertEqual(index, sorted(index), keys)

    def test_parallelism_and_accounts_actions_and_the_team_rule(self) -> None:
        actions = phase_actions.ACTIONS["poc_experiments"]["actions"]
        parallel = next(a for a in actions if a.get("slash") == "/remote-parallelism")
        guide = " ".join(parallel["guide"])
        self.assertIn("estimate", guide)
        self.assertIn("assess", guide)
        self.assertIn("--owners", guide)
        accounts = next(a for a in actions if a.get("slash") == "/kaggle-accounts")
        self.assertIn("validate", accounts["prefix"] + " ".join(accounts["guide"]))
        everything = json.dumps(actions, ensure_ascii=False)
        self.assertTrue("one account per person and service" in everything or "una cuenta por persona y servicio" in everything)
        self.assertIn("smith team add", everything)
        self.assertIn("--attest", everything)


class KaggleReadinessCountsOwnersTests(unittest.TestCase):
    def services(self, members: list[dict], stored: int) -> dict:
        rows = [{"id": "token", "state": "active"}, {"id": "cli", "state": "active"},
                {"id": "accounts", "state": "active" if stored else "inactive", "count": stored}]
        return {"rows": rows, "team": {"present": bool(members), "problem": None, "members": members}}

    def test_only_owners_with_a_validated_account_count(self) -> None:
        members = [{"owner": "ana", "kaggle_username": "ana-k", "kaggle_validated": True},
                   {"owner": "beto", "kaggle_username": "beto-k", "kaggle_validated": True},
                   {"owner": "caro", "kaggle_username": "caro-k", "kaggle_validated": False},
                   {"owner": "dani", "kaggle_username": None, "kaggle_validated": None}]
        out = remote_services.remote_host_readiness(self.services(members, stored=5), "poc")[KAGGLE]
        self.assertTrue(out["available"])
        self.assertTrue("2 propietario(s) con cuenta validada" in out["reason"] or "2 owner(s) with a validated account" in out["reason"])

    def test_a_registry_whose_owners_have_no_validated_account_is_unavailable(self) -> None:
        members = [{"owner": "ana", "kaggle_username": "ana-k", "kaggle_validated": False}]
        out = remote_services.remote_host_readiness(self.services(members, stored=3), "poc")[KAGGLE]
        self.assertFalse(out["available"])
        self.assertTrue("0 propietario(s) con cuenta validada" in out["reason"] or "0 owner(s) with a validated account" in out["reason"])

    def test_without_a_registry_the_stored_accounts_count(self) -> None:
        out = remote_services.remote_host_readiness(self.services([], stored=3), "poc")[KAGGLE]
        self.assertTrue(out["available"])
        self.assertTrue("3 cuenta(s)" in out["reason"] or "3 stored worker account(s)" in out["reason"])


class HelpBoxTests(unittest.TestCase):
    def test_remote_verbs_are_in_the_order_they_run(self) -> None:
        source = _help_source()
        for section in re.findall(r"generate-job</code>.*?</li>", source, re.S):
            verbs = ["generate-job", "submit --smoke", "fetch --smoke", "readiness", "gate",
                     "<code>submit</code>", "status", "poll", "<code>fetch</code>"]
            positions = []
            start = 0
            for verb in verbs:
                with self.subTest(section=section[:40], verb=verb):
                    start = section.index(verb, start)
                    positions.append(start)
        self.assertGreaterEqual(len(re.findall(r"generate-job</code>.*?</li>", source, re.S)), 2)
        self.assertNotIn("<code>readiness</code> → <code>smoke</code>", source)

    def test_credentials_limits_options_and_team_rule_are_honest(self) -> None:
        source = _help_source()
        self.assertIn("access_token", source)
        self.assertIn("KGAT", source)
        self.assertIn("kaggle-inbox/", source)
        self.assertNotIn("9 h", source)
        self.assertIn("get_accelerator_quota", source)
        for needle in ("Local", ".venv", "micromamba", "Results/timing.json", "experiments-reviewer",
                       "smith team add", "https://www.kaggle.com/discussions/general/192527",
                       "applies to all Kaggle site use"):
            with self.subTest(needle=needle):
                self.assertIn(needle, source)
        for needle in ("qubits", "PennyLane"):
            self.assertNotIn(needle, source)

    def test_the_yaml_template_says_its_compute_fields_are_local(self) -> None:
        text = (REPO / "src/papersmith/templates/papersmith.yaml.tpl").read_text(encoding="utf-8")
        self.assertIn("max_timeout_hours: 9", text)
        self.assertIn("local cap", text)
        self.assertIn("machine_shape", text)


class RunOptionLabelTests(unittest.TestCase):
    def test_a_range_states_one_unit(self) -> None:
        self.assertEqual(run_options.range_label(82, 120), "82 s – 120 s")
        self.assertEqual(run_options.range_label(84, 120), "84 s – 120 s")
        self.assertTrue(run_options.range_label(90, 126) in ("1.5 min – 2.1 min", "1,5 min – 2,1 min"))
        self.assertTrue(run_options.range_label(2 * 3600, 3 * 3600) in ("2.0 h – 3.0 h", "2,0 h – 3,0 h"))

    def test_recommendations_carry_no_nested_parentheses(self) -> None:
        timing = run_options.parse_timing({
            "schema": 1,
            "measurements": [{"host": f"{KAGGLE}:ana", "unit": "epoch", "secondsPerUnit": 1.0}],
            "scales": {"poc": {"arms": 1, "folds": 1, "seeds": 1, "epochs": 100},
                       "full": {"arms": 1, "folds": 1, "seeds": 1, "epochs": 100}}})
        timing["file"] = "implementations/r/P/Results/timing.json"
        rows = [{"id": "token", "state": "active"}, {"id": "cli", "state": "active"},
                {"id": "accounts", "state": "active", "count": 1}, {"id": "colab_cli", "state": "active"}]
        view = {"products": [{"kind": "poc", "timing": timing}],
                "remote_services": {"rows": rows, "team": {"problem": None, "members": [
                    {"owner": "ana", "colab_tier": "pro", "colab_config_present": True}]}},
                "local_environment": {"workspace": {"present": True}, "targets": []}}
        options = run_options.run_options(Path("."), view)
        for stage, rec in options["recommendations"].items():
            depth, deepest = 0, 0
            for char in rec["text"]:
                depth += char == "("
                deepest = max(deepest, depth)
                depth -= char == ")"
            with self.subTest(stage=stage, text=rec["text"]):
                self.assertLessEqual(deepest, 1)
        measured = next(r for r in options["rows"] if r["estimate"])
        self.assertEqual(measured["estimate_label"], "80 s – 120 s ±20%")


@unittest.skipUnless(shutil.which("node"), "node is required to run the panel renderer")
class RunOptionsTableRendersTests(unittest.TestCase):
    TIMING = {"schema": 1,
              "measurements": [{"host": "local", "unit": "epoch", "secondsPerUnit": 2.0, "arm": "A"},
                               {"host": f"{KAGGLE}:ana", "unit": "epoch", "secondsPerUnit": 1.0, "arm": "A",
                                "setupSeconds": 30.0}],
              "scales": {"poc": {"arms": 1, "folds": 2, "seeds": 1, "epochs": 5},
                         "full": {"arms": 2, "folds": 5, "seeds": 3, "epochs": 50}}}

    def render(self, view: dict) -> str:
        i18n_js = PANEL.parent / "i18n.js"
        en_js = PANEL.parent / "i18n" / "en.js"
        es_js = PANEL.parent / "i18n" / "es.js"
        script = (
            "const fs=require('fs');"
            "global.window={localStorage:{getItem:()=>'es',setItem:()=>{}}};"
            "global.document={addEventListener(){},querySelectorAll:()=>[]};"
            f"eval(fs.readFileSync({json.dumps(str(en_js))},'utf8'));"
            f"eval(fs.readFileSync({json.dumps(str(es_js))},'utf8'));"
            f"eval(fs.readFileSync({json.dumps(str(i18n_js))},'utf8'));"
            f"eval(fs.readFileSync({json.dumps(str(PANEL))},'utf8'));"
            "console.log(window.ExperimentsPanel.runOptions(JSON.parse(fs.readFileSync(0,'utf8'))));"
        )
        return subprocess.run(["node", "-e", script], input=json.dumps(view), capture_output=True,
                              text=True, cwd=tempfile.gettempdir(), check=True).stdout

    def view(self, timing: dict | None) -> dict:
        products = []
        if timing is not None:
            parsed = run_options.parse_timing(timing)
            parsed["file"] = "implementations/r/P/Results/timing.json"
            products = [{"kind": "poc", "timing": parsed}]
        rows = [{"id": "token", "state": "active"}, {"id": "cli", "state": "active"},
                {"id": "accounts", "state": "active", "count": 1}, {"id": "colab_cli", "state": "active"}]
        return {"products": products,
                "remote_services": {"rows": rows, "team": {"problem": None, "members": [
                    {"owner": "ana", "colab_tier": "pro", "colab_config_present": True}]}},
                "local_environment": {"workspace": {"present": True}, "targets": []}}

    def test_every_stage_and_host_renders_with_and_without_timing(self) -> None:
        for timing in (self.TIMING, None):
            options = run_options.run_options(Path("."), self.view(timing))
            self.assertEqual({(r["stage"], r["host"]) for r in options["rows"]},
                             {(s, h) for s in run_options.STAGES for h in remote_services.RUN_HOSTS})
            out = self.render(options)
            with self.subTest(timing=bool(timing)):
                for label in ("Proof of concept", "Full experiment", "Local", "Kaggle", "Colab"):
                    self.assertIn(label, out)
                self.assertTrue("Recomendación" in out or "Recommendation" in out)
                if timing:
                    self.assertIn("±20%", out)
                    self.assertTrue("sin medir" in out or "unmeasured" in out)
                else:
                    self.assertIn("Results/timing.json", out)


if __name__ == "__main__":
    unittest.main()


class RejectedRegistryReadinessTests(unittest.TestCase):
    def test_a_registry_the_backend_refuses_never_reads_ready(self) -> None:
        import json, tempfile
        from skills._core.command_center import remote_services
        cases = {
            "duplicate username": {"schema": 1, "members": [
                {"owner": "ana", "accounts": {"kaggle": {"username": "same"}}},
                {"owner": "ben", "accounts": {"kaggle": {"username": "SAME"}}}]},
            "duplicate owner": {"schema": 1, "members": [
                {"owner": "ana", "accounts": {"kaggle": {"username": "a"}}},
                {"owner": "ana", "accounts": {"kaggle": {"username": "b"}}}]},
            "bad slug": {"schema": 1, "members": [{"owner": "Ana Bad", "accounts": {}}]},
            "wrong schema": {"schema": 2, "members": []},
        }
        for label, registry in cases.items():
            with self.subTest(label), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / ".papersmith").mkdir()
                (root / ".papersmith" / "team.json").write_text(json.dumps(registry), encoding="utf-8")
                team = remote_services.team_members(root)
                self.assertIn(team["problem"], ("rejected", "invalid"), label)
