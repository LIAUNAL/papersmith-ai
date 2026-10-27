"""The launch ladder, checked before a job is generated rather than at the
launch (S2), and `launch-plan`, the read-only command that says what is
still missing before a job launches (S3).

Field evidence (QMLEEG E5, `odd/tasks/poc-launch-smoothing.md` L3): a remote
step had no `@rehearsal <job>` item, so `offer` never published a `launch`;
earlier ladder items were ticked but unbacked, so `gate` refused
`POSITION_UNBACKED`; and `gate` refused `GATE_PROPOSAL_UNKNOWN` twice. Each
was discovered one refusal at a time, at the launch. These tests pin that
the same facts are reported up front, by `verify`, `position --reconcile`
and `launch-plan`, and that `launch-plan` reports them in the order the
acts would raise them, writing nothing.

Fixtures mirror `ProposalAndElectionGateTests` in
`tests/test_proposal_implementation.py` (duplicated per that file's own
convention, not imported).
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

FORGE = Path(__file__).resolve().parents[1]
CLI = FORGE / "skills/proposal-implementation/scripts/implementation_cli.py"
EXPERIMENTS_CLI = FORGE / "skills/experimental-implementation/scripts/implementation_cli.py"
ENGINE = FORGE / "skills/_core/implementation/engine/implementation_engine.py"
sys.path.insert(0, str(ENGINE.parent))
from domain_profile import seeded_profile  # noqa: E402  (path set above)
with seeded_profile(FORGE / "skills/proposal-implementation/impl_profile.py"):
    import implementation_engine as impl  # noqa: E402  (path set above)
import impl_position  # noqa: E402  (on sys.path through the engine's own import)

REVISION = "r1.md"
REVISION_TEXT = "## 1\ntexto\n"
REVISION_SHA256 = hashlib.sha256(REVISION_TEXT.encode("utf-8")).hexdigest()

#: The steps every fixture ladder's `@step` items name. `job1` declares no
#: placement on purpose: it is linked to the job folder of the same name by
#: its operand alone, the fallback `--reconcile` keeps.
STEPS = {
    "prep": {"module": "Method.steps", "function": "prep", "placement": "local"},
    "job1": {"module": "Method.steps", "function": "run"},
    "report": {"module": "Method.steps", "function": "report", "placement": "local"},
}


def _tree_digest(root: Path) -> dict:
    """Every file under `root` (outside `.git`) mapped to its bytes' digest."""
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file() and ".git" not in path.relative_to(root).parts
    }


class _Fixture(unittest.TestCase):

    def _proposals(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        (root / REVISION).write_text(REVISION_TEXT, encoding="utf-8")
        return root

    def _box(self, steps: dict | None = STEPS):
        self._box_count = getattr(self, "_box_count", 0) + 1
        box = (FORGE / "implementations"
               / f"_e2e_launch_plan_{os.getpid()}_{id(self)}_{self._box_count}")
        self.addCleanup(shutil.rmtree, box, ignore_errors=True)
        box.mkdir(parents=True)
        env = dict(os.environ)
        env["GIT_AUTHOR_NAME"] = env["GIT_COMMITTER_NAME"] = "launch-plan-tests"
        env["GIT_AUTHOR_EMAIL"] = env["GIT_COMMITTER_EMAIL"] = "launch-plan@example.invalid"
        subprocess.run(["git", "init", "-q", str(box)], check=True, capture_output=True)
        (box / "src" / "Method").mkdir(parents=True)
        init = "" if steps is None else f"__steps__ = {steps!r}\n"
        (box / "src" / "Method" / "__init__.py").write_text(init, encoding="utf-8")
        (box / "src" / "Method_Benchmark").mkdir(parents=True)
        (box / "src" / "Method_Benchmark" / "__init__.py").write_text("", encoding="utf-8")
        (box / "Method").mkdir(parents=True)
        (box / "tests").mkdir(parents=True)
        subprocess.run(["git", "add", "-A"], cwd=box, env=env, check=True,
                       capture_output=True)
        subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=box, env=env,
                       check=True, capture_output=True)
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=box, env=env,
                                check=True, capture_output=True, text=True).stdout.strip()
        return box, commit

    def _write_job_folder(self, box, commit, *, service="svc", job_name="job1"):
        job_dir = box / "tools" / service / job_name
        job_dir.mkdir(parents=True, exist_ok=True)
        run_config = {
            "schemaVersion": 1, "product": "Method", "service": service,
            "jobName": job_name, "commit": commit,
            "repo": {"url": "https://example.invalid/repo.git", "ref": "main"},
            "clonePaths": ["src/Method"],
            "run": {"module": "Method.module", "function": "run", "kwargs": {}},
            "runnerTemplate": [
                {"path": "assets/runner_bootstrap.py", "sha256": "0" * 64},
                {"path": "assets/runner_invoke.py", "sha256": "0" * 64},
            ],
        }
        (job_dir / "run-config.json").write_text(json.dumps(run_config), encoding="utf-8")
        return job_dir

    def _write_smoke_pass(self, box, *, job_name="job1", commit, worker="w1"):
        smoke_path = box / "Method" / ".remote-execution" / "smoke.jsonl"
        smoke_path.parent.mkdir(parents=True, exist_ok=True)
        event = {"kind": "smokeResult", "ts": "2026-08-27T00:00:00Z",
                 "jobName": job_name, "result": "pass", "commit": commit,
                 "worker": worker, "missing": []}
        with smoke_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event) + "\n")

    def _write_agreed(self, box, items):
        """`items`: `(mark, text, kind, operand)` tuples, in ladder order."""
        header = {"revision": REVISION, "revisionSha256": REVISION_SHA256,
                  "derivedAt": "2026-08-27T00:00:00Z", "session": "s1",
                  "target": "final"}
        rendered = [{"ordinal": i + 1, "mark": mark, "text": text,
                     "witness": {"kind": kind, "operand": operand}}
                    for i, (mark, text, kind, operand) in enumerate(items)]
        (box / "Method" / "AGREED.md").write_text(
            impl_position.render(header, rendered), encoding="utf-8")

    def _sequence(self, box):
        block = impl_position.locate_block((box / "Method" / "AGREED.md").read_bytes())
        return [(item["witness"]["kind"], item["witness"]["operand"], item["text"])
                for item in impl_position.parse_items(block["body"])]

    def run_cli(self, *args, proposals=None, cli=CLI):
        env = dict(os.environ)
        env.pop("IMPLEMENTATION_DOMAIN_PROFILE", None)
        if proposals is not None:
            env["IMPLEMENTATION_PROPOSALS"] = str(proposals)
        return subprocess.run([sys.executable, str(cli), *args],
                              capture_output=True, text=True, cwd=FORGE, env=env)

    def _register_capacity(self):
        rcli = impl._load_remote_execution_cli()
        rcli.ADAPTER.register_declared_capacity("svc", lambda: (1, 1))

    def _propose(self, box, *, jobs=("job1",)):
        return impl.cmd_propose(argparse.Namespace(
            target=str(box), name="Method", session="s1", jobs=list(jobs),
            workers=["w1"], depends_on=None, rationale="Campaign for the fixture."))

    def _launch_plan(self, box, proposals, *, job="job1", worker="w1"):
        self._register_capacity()
        args = argparse.Namespace(
            command="launch-plan", target=str(box), name="Method",
            revision=REVISION, job=job, worker=worker, session=None)
        with unittest.mock.patch.dict(
                os.environ, {"IMPLEMENTATION_PROPOSALS": str(proposals)}):
            return impl.cmd_launch_plan(args)

    def _validate_diagram(self, box):
        """The operator's dashboard act, done the way the dashboard does it."""
        product = box / "Method"
        (product / "diagrams").mkdir(parents=True, exist_ok=True)
        (product / "diagrams" / "poc.png").write_bytes(b"\x89PNG fixture")
        impl._load_remote_execution_cli()._diagram_cli().write_validation(product, "poc")

    @staticmethod
    def _acts(result):
        return {act["act"]: act for act in result["acts"]}


class ReconcileInsertsRehearsalBeforeRemoteStepTests(_Fixture):
    """S2(a): `position --reconcile` places a missing `@rehearsal <job>`
    immediately before the ladder item that runs that job remotely."""

    def _reconcile(self, box, proposals):
        return self.run_cli("position", "--target", str(box), "--name", "Method",
                            "--revision", REVISION, "--session", "s1",
                            "--reconcile", proposals=proposals)

    def test_reconcile_inserts_the_rehearsal_before_the_step_with_the_same_operand(self):
        box, commit = self._box()
        self._write_job_folder(box, commit)
        self._write_agreed(box, [
            (" ", "Prepare the data.", "step", "prep"),
            (" ", "Run the job remotely.", "step", "job1"),
            (" ", "Report.", "step", "report"),
        ])
        proc = self._reconcile(box, self._proposals())
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(self._sequence(box), [
            ("step", "prep", "Prepare the data."),
            ("rehearsal", "job1", impl.POSITION_PLACEHOLDER_TEXT),
            ("step", "job1", "Run the job remotely."),
            ("step", "report", "Report."),
        ])

    def test_reconcile_inserts_before_the_step_whose_declared_remote_job_it_is(self):
        """A step id that differs from its job folder's name, linked only by
        `__steps__[id]["job"]` with `placement: remote`."""
        box, commit = self._box(steps={**STEPS,
            "big_run": {"module": "Method.steps", "function": "run",
                        "placement": "remote", "job": "job1", "service": "svc"}})
        self._write_job_folder(box, commit)
        self._write_agreed(box, [
            (" ", "Prepare.", "step", "prep"),
            (" ", "The big run.", "step", "big_run"),
        ])
        proc = self._reconcile(box, self._proposals())
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual([k for k, _, _ in self._sequence(box)],
                         ["step", "rehearsal", "step"])
        self.assertEqual(self._sequence(box)[1][1], "job1")

    def test_reconcile_appends_the_rehearsal_when_no_step_runs_the_job(self):
        box, commit = self._box()
        self._write_job_folder(box, commit)
        self._write_agreed(box, [
            (" ", "Prepare the data.", "step", "prep"),
            (" ", "Report.", "step", "report"),
        ])
        proc = self._reconcile(box, self._proposals())
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(self._sequence(box), [
            ("step", "prep", "Prepare the data."),
            ("step", "report", "Report."),
            ("rehearsal", "job1", impl.POSITION_PLACEHOLDER_TEXT),
        ])

    def test_reconcile_without_remote_steps_or_jobs_is_unchanged(self):
        """Previous behaviour: a ladder with no job folder and no remote step
        reconciles to exactly what it held, byte for byte."""
        box, _ = self._box()
        self._write_agreed(box, [
            (" ", "Prepare the data.", "step", "prep"),
            (" ", "Report.", "step", "report"),
        ])
        before = (box / "Method" / "AGREED.md").read_bytes()
        proc = self._reconcile(box, self._proposals())
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual((box / "Method" / "AGREED.md").read_bytes(), before)


class VerifyReportsTheLaunchLadderTests(_Fixture):
    """S2(a)+(b): `verify` names a job whose ladder lacks `@rehearsal <job>`,
    with the ordinal it belongs before, and the ticked-but-unbacked items."""

    def _verify(self, box, proposals):
        proc = self.run_cli("verify", "--target", str(box), "--name", "Method",
                            "--revision", REVISION, proposals=proposals)
        self.assertIn(proc.returncode, (0, 1), proc.stdout + proc.stderr)
        return json.loads(proc.stdout)

    def test_verify_reports_the_missing_rehearsal_witness_and_unbacked_items(self):
        box, commit = self._box()
        self._write_job_folder(box, commit)
        self._write_agreed(box, [
            ("x", "Prepare the data.", "step", "prep"),
            (" ", "Run the job remotely.", "step", "job1"),
        ])
        result = self._verify(box, self._proposals())
        ladder = result["launchLadder"]
        self.assertEqual(ladder["rehearsalWitnessMissing"],
                         [{"job": "job1", "step": "job1", "beforeOrdinal": 2}])
        self.assertEqual(ladder["unbackedOrdinals"], [1])
        self.assertIn("--reconcile", ladder["resolve"])

    def test_verify_omits_the_key_when_the_ladder_is_complete(self):
        box, commit = self._box()
        self._write_job_folder(box, commit)
        self._write_agreed(box, [
            (" ", "Rehearse.", "rehearsal", "job1"),
            (" ", "Run the job remotely.", "step", "job1"),
        ])
        result = self._verify(box, self._proposals())
        self.assertNotIn("launchLadder", result)


class LaunchPlanTests(_Fixture):
    """S3: `launch-plan` lists propose, offer, gate, submit in order, each
    with its status, the code it would raise now and the next command."""

    def test_missing_rehearsal_is_reported_first(self):
        box, commit = self._box()
        self._write_job_folder(box, commit)
        self._write_smoke_pass(box, commit=commit)
        self._write_agreed(box, [(" ", "Run the job remotely.", "step", "job1")])
        result = self._launch_plan(box, self._proposals())
        self.assertEqual([a["act"] for a in result["acts"]],
                         ["propose", "offer", "gate", "submit"])
        offer = self._acts(result)["offer"]
        self.assertEqual(offer["status"], "blocked")
        self.assertEqual(offer["code"], "SEQUENCE_NOT_REACHED")
        self.assertEqual(offer["facts"]["reason"], "no_witness")
        self.assertIn("--reconcile", offer["command"])
        self.assertEqual(result["launchLadder"]["rehearsalWitnessMissing"],
                         [{"job": "job1", "step": "job1", "beforeOrdinal": 1}])
        # The proposal waits for the ladder: proposing now would freeze a
        # pin the remaining work may still move.
        self.assertEqual(self._acts(result)["propose"]["status"], "pending")
        self.assertEqual(self._acts(result)["propose"]["code"], "GATE_PROPOSAL_UNKNOWN")
        self.assertEqual(result["next"]["act"], "offer")
        self.assertEqual(result["next"]["code"], "SEQUENCE_NOT_REACHED")

    def test_unbacked_items_are_reported(self):
        box, commit = self._box()
        self._write_job_folder(box, commit)
        self._write_smoke_pass(box, commit=commit)
        self._write_agreed(box, [
            ("x", "Prepare the data.", "step", "prep"),
            (" ", "Rehearse.", "rehearsal", "job1"),
            (" ", "Run the job remotely.", "step", "job1"),
        ])
        result = self._launch_plan(box, self._proposals())
        offer = self._acts(result)["offer"]
        self.assertEqual(offer["status"], "blocked")
        self.assertEqual(offer["code"], "POSITION_UNBACKED")
        self.assertEqual(result["launchLadder"]["unbackedOrdinals"], [1])
        self.assertEqual(self._acts(result)["gate"]["status"], "pending")

    def test_not_ready_is_reported(self):
        box, commit = self._box()
        self._write_job_folder(box, commit)
        self._write_agreed(box, [
            (" ", "Rehearse.", "rehearsal", "job1"),
            (" ", "Run the job remotely.", "step", "job1"),
        ])
        result = self._launch_plan(box, self._proposals())
        offer = self._acts(result)["offer"]
        self.assertEqual(offer["status"], "blocked")
        self.assertEqual(offer["code"], "NOT_READY")
        self.assertNotIn("launchLadder", result)

    def test_no_proposal_is_next_when_everything_else_is_in_place(self):
        box, commit = self._box()
        self._write_job_folder(box, commit)
        self._write_smoke_pass(box, commit=commit)
        self._write_agreed(box, [
            (" ", "Rehearse.", "rehearsal", "job1"),
            (" ", "Run the job remotely.", "step", "job1"),
        ])
        result = self._launch_plan(box, self._proposals())
        acts = self._acts(result)
        self.assertEqual(acts["propose"]["status"], "next")
        self.assertEqual(acts["propose"]["code"], "GATE_PROPOSAL_UNKNOWN")
        self.assertIn(" propose ", acts["propose"]["command"])
        self.assertIn("--job job1", acts["propose"]["command"])
        self.assertEqual(acts["offer"]["status"], "pending")
        self.assertIsNone(acts["offer"]["code"])
        self.assertEqual(acts["gate"]["status"], "pending")
        self.assertEqual(acts["submit"]["status"], "pending")
        self.assertEqual(result["next"]["act"], "propose")
        self.assertEqual(result["next"]["command"], acts["propose"]["command"])

    def test_offer_is_next_once_a_current_proposal_names_the_job(self):
        box, commit = self._box()
        self._write_job_folder(box, commit)
        self._write_smoke_pass(box, commit=commit)
        self._write_agreed(box, [(" ", "Rehearse.", "rehearsal", "job1")])
        self._propose(box)
        result = self._launch_plan(box, self._proposals())
        acts = self._acts(result)
        self.assertEqual(acts["propose"]["status"], "done")
        self.assertEqual(acts["offer"]["status"], "next")
        self.assertIn(" offer ", acts["offer"]["command"])
        self.assertIn("--answer yes", acts["offer"]["command"])

    def test_gate_is_next_with_the_minted_token_and_submit_after_it(self):
        box, commit = self._box()
        self._write_job_folder(box, commit)
        self._write_smoke_pass(box, commit=commit)
        self._write_agreed(box, [(" ", "Rehearse.", "rehearsal", "job1")])
        self._propose(box)
        proposals = self._proposals()
        self._register_capacity()
        with unittest.mock.patch.dict(
                os.environ, {"IMPLEMENTATION_PROPOSALS": str(proposals)}):
            offered = impl.cmd_offer(argparse.Namespace(
                target=str(box), name="Method", revision=REVISION,
                session="s1", answer="yes", units=None))
        token = next(a for a in offered["actions"]
                     if a["id"] == "launch")["binding"]["authorization"]
        result = self._launch_plan(box, proposals)
        acts = self._acts(result)
        self.assertEqual(acts["offer"]["status"], "done")
        self.assertEqual(acts["gate"]["status"], "next")
        self.assertIn(f"--authorization {token}", acts["gate"]["command"])
        self.assertIn("--worker w1", acts["gate"]["command"])
        # The fixture's facts do not decide necessity, so the plan says the
        # gate needs an election before the gate itself would refuse it.
        self.assertTrue(acts["gate"]["elect"])
        self.assertIn("--elect job1", acts["gate"]["command"])

        with unittest.mock.patch.dict(
                os.environ, {"IMPLEMENTATION_PROPOSALS": str(proposals)}):
            impl.cmd_gate(argparse.Namespace(
                target=str(box), name="Method", revision=REVISION,
                session="s1", job="job1", worker="w1", units=None,
                justification="Because it is time.", authorization=token,
                elected=["job1"]))
        self._validate_diagram(box)
        result = self._launch_plan(box, proposals)
        acts = self._acts(result)
        self.assertEqual(acts["gate"]["status"], "done")
        self.assertEqual(acts["submit"]["status"], "next")
        self.assertIn(" submit ", acts["submit"]["command"])
        self.assertIn("--consent ", acts["submit"]["command"])
        self.assertIn("--worker w1", acts["submit"]["command"])
        self.assertIn("--backend '<service>'", acts["submit"]["command"])

    def test_submit_reports_an_unvalidated_diagram(self):
        box, commit = self._box()
        self._write_job_folder(box, commit)
        self._write_smoke_pass(box, commit=commit)
        self._write_agreed(box, [(" ", "Rehearse.", "rehearsal", "job1")])
        result = self._launch_plan(box, self._proposals())
        self.assertEqual(self._acts(result)["submit"]["code"], "DIAGRAM_NOT_VALIDATED")

    def test_launch_plan_writes_nothing(self):
        box, commit = self._box()
        self._write_job_folder(box, commit)
        self._write_smoke_pass(box, commit=commit)
        self._write_agreed(box, [(" ", "Rehearse.", "rehearsal", "job1")])
        self._propose(box)
        before = _tree_digest(box)
        ledger = box / "Method" / ".implementation" / "position.jsonl"
        ledger_before = ledger.read_bytes()
        self._launch_plan(box, self._proposals())
        self.assertEqual(ledger.read_bytes(), ledger_before)
        self.assertEqual(_tree_digest(box), before)

    def test_launch_plan_runs_from_both_hosts_cli(self):
        """The command is the shared engine's, so both launchers carry it."""
        for cli in (CLI, EXPERIMENTS_CLI):
            with self.subTest(cli=cli.parent.parent.name):
                proc = self.run_cli("launch-plan", "--help", cli=cli)
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                self.assertIn("--job", proc.stdout)


if __name__ == "__main__":
    unittest.main()
