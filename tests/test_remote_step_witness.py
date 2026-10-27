"""An `@step` item whose step runs remotely is measured from the
remote-execution record, never from a local `step` run.

Field evidence: a ladder item `@step <job>` stayed unticked after its job
ran remotely and `fetch` returned its result, because `position` only
credited a `kind: "step"` event that `step` writes when it runs locally.
These tests pin the rule end to end, through `position` (a refresh):

- a remote step is ticked when the MAIN ledger
  (`<Name>/.remote-execution/ledger.jsonl`) holds a current `returned` for
  its job and the result ran at the job folder's current pin;
- it is not ticked with only a `submitted`, with only a rehearsal record in
  `smoke.jsonl`, with a result the source has moved past, or with a result
  that ran at a pin the job folder has since moved past;
- a local `@step` item is measured exactly as before.

Fixtures mirror `tests/test_launch_plan.py` (duplicated per that file's own
convention, not imported).
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

FORGE = Path(__file__).resolve().parents[1]
CLI = FORGE / "skills/proposal-implementation/scripts/implementation_cli.py"
ENGINE = FORGE / "skills/_core/implementation/engine/implementation_engine.py"
sys.path.insert(0, str(ENGINE.parent))
from domain_profile import seeded_profile  # noqa: E402  (path set above)
with seeded_profile(FORGE / "skills/proposal-implementation/impl_profile.py"):
    import implementation_engine as impl  # noqa: E402  (path set above)
import impl_position  # noqa: E402  (on sys.path through the engine's own import)

REVISION = "r1.md"
REVISION_TEXT = "## 1\ntexto\n"
REVISION_SHA256 = hashlib.sha256(REVISION_TEXT.encode("utf-8")).hexdigest()

#: `job1` declares no placement: it is linked to the job folder of the same
#: name by its operand alone. `big_run` is linked by `placement: remote` and
#: `job: job1`. `prep` is local.
STEPS = {
    "prep": {"module": "Method.steps", "function": "prep", "placement": "local"},
    "job1": {"module": "Method.steps", "function": "run"},
    "big_run": {"module": "Method.steps", "function": "run",
                "placement": "remote", "job": "job1", "service": "svc"},
}

ENTRYPOINT = "tools/svc/job1/runner.ipynb"
SUBMISSION = "svc:w1/job1-0001"


class RemoteStepWitnessTests(unittest.TestCase):

    def setUp(self):
        self.env = dict(os.environ)
        self.env["GIT_AUTHOR_NAME"] = self.env["GIT_COMMITTER_NAME"] = "remote-step-tests"
        self.env["GIT_AUTHOR_EMAIL"] = self.env["GIT_COMMITTER_EMAIL"] = "remote-step@example.invalid"
        self.proposals = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.proposals, ignore_errors=True)
        (self.proposals / REVISION).write_text(REVISION_TEXT, encoding="utf-8")
        self.box = (FORGE / "implementations"
                    / f"_e2e_remote_step_{os.getpid()}_{id(self)}")
        self.addCleanup(shutil.rmtree, self.box, ignore_errors=True)
        self.box.mkdir(parents=True)
        self._git("init", "-q", str(self.box), cwd=FORGE)
        (self.box / "src" / "Method").mkdir(parents=True)
        (self.box / "src" / "Method" / "__init__.py").write_text(
            f"__steps__ = {STEPS!r}\n", encoding="utf-8")
        (self.box / "src" / "Method_Benchmark").mkdir(parents=True)
        (self.box / "src" / "Method_Benchmark" / "__init__.py").write_text("", encoding="utf-8")
        (self.box / "Method").mkdir(parents=True)
        (self.box / "tests").mkdir(parents=True)
        self.commit = self._commit("initial")
        self._write_job_folder(self.commit)

    # --- fixture helpers -------------------------------------------------

    def _git(self, *args, cwd=None):
        return subprocess.run(["git", *args], cwd=cwd or self.box, env=self.env,
                              check=True, capture_output=True, text=True).stdout.strip()

    def _commit(self, message):
        self._git("add", "-A")
        self._git("commit", "-q", "-m", message)
        return self._git("rev-parse", "HEAD")

    def _write_job_folder(self, commit):
        job_dir = self.box / "tools" / "svc" / "job1"
        job_dir.mkdir(parents=True, exist_ok=True)
        run_config = {
            "schemaVersion": 1, "product": "Method", "service": "svc",
            "jobName": "job1", "commit": commit,
            "repo": {"url": "https://example.invalid/repo.git", "ref": "main"},
            "clonePaths": ["src/Method"],
            "run": {"module": "Method.module", "function": "run", "kwargs": {}},
            "runnerTemplate": [
                {"path": "assets/runner_bootstrap.py", "sha256": "0" * 64},
                {"path": "assets/runner_invoke.py", "sha256": "0" * 64},
            ],
        }
        (job_dir / "run-config.json").write_text(json.dumps(run_config), encoding="utf-8")

    def _live_digest(self):
        return impl.source_digest(self.box, impl.package_name("Method"))

    def _append(self, ledger, event):
        path = self.box / "Method" / ".remote-execution" / ledger
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event) + "\n")

    def _submitted(self, ledger="ledger.jsonl", digest=None):
        self._append(ledger, {
            "kind": "submitted", "ts": "2026-10-27T00:00:00Z",
            "entrypoint": ENTRYPOINT, "sourceDigest": digest or self._live_digest(),
            "submissionId": SUBMISSION, "worker": "svc:w1",
            "requestedCapacity": 1, "grantedCapacity": 1})

    def _returned(self, ledger="ledger.jsonl", ran_at=None):
        """A `returned` event, and the artifact `fetch` materialized for it:
        the runner's own `bootstrap.json`, naming the commit it cloned."""
        artifact = self.box / "Method" / ".remote-execution" / "returned" / "job1-0001"
        artifact.mkdir(parents=True, exist_ok=True)
        (artifact / "bootstrap.json").write_text(
            json.dumps({"commit": ran_at or self.commit}), encoding="utf-8")
        self._append(ledger, {
            "kind": "returned", "ts": "2026-10-27T01:00:00Z",
            "submissionId": SUBMISSION, "artifactPath": str(artifact),
            "observedConcurrency": 1})

    def _write_agreed(self, items):
        header = {"revision": REVISION, "revisionSha256": REVISION_SHA256,
                  "derivedAt": "2026-10-27T00:00:00Z", "session": "s1",
                  "target": "final"}
        rendered = [{"ordinal": i + 1, "mark": " ", "text": text,
                     "witness": {"kind": "step", "operand": operand}}
                    for i, (text, operand) in enumerate(items)]
        (self.box / "Method" / "AGREED.md").write_text(
            impl_position.render(header, rendered), encoding="utf-8")

    def _local_step_event(self, step, outcome="returned"):
        path = self.box / "Method" / ".implementation" / "position.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "kind": "step", "step": step, "outcome": outcome,
                "suiteDigest": impl.suite_digest(self.box),
                "at": "2026-10-27T00:00:00Z"}) + "\n")

    def _position(self):
        """`position` (a refresh): returns `{operand: (derived, mark)}`."""
        env = dict(os.environ)
        env.pop("IMPLEMENTATION_DOMAIN_PROFILE", None)
        env["IMPLEMENTATION_PROPOSALS"] = str(self.proposals)
        proc = subprocess.run(
            [sys.executable, str(CLI), "position", "--target", str(self.box),
             "--name", "Method", "--revision", REVISION, "--session", "s1"],
            capture_output=True, text=True, cwd=FORGE, env=env)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        block = impl_position.locate_block((self.box / "Method" / "AGREED.md").read_bytes())
        marks = {item["witness"]["operand"]: item["mark"]
                 for item in impl_position.parse_items(block["body"])}
        derived = {entry["witness"]["operand"]: entry["derived"]
                   for entry in payload["sequence"]}
        return {operand: (derived[operand], marks[operand]) for operand in marks}, payload

    def _reason(self, operand):
        """The `reason` `position_state` reports for an unmeasured item, read
        over the same `stepVerdicts` every evidence builder hands it."""
        state = impl.position_state(
            self.box, "Method", {"stepVerdicts": impl._step_verdicts(self.box, "Method")},
            None, None, impl._document_extra_sources(None))
        return {e["witness"]["operand"]: e["reason"] for e in state["unmeasured"]}[operand]

    # --- the rule ----------------------------------------------------------

    def test_a_remote_step_is_ticked_when_the_main_ledger_holds_a_current_returned(self):
        self._write_agreed([("Prepare.", "prep"), ("Run the job remotely.", "job1")])
        self._submitted()
        self._returned()
        state, _ = self._position()
        self.assertEqual(state["job1"], (True, "x"))

    def test_a_step_linked_by_its_declared_remote_job_is_ticked_too(self):
        self._write_agreed([("The big run.", "big_run")])
        self._submitted()
        self._returned()
        state, _ = self._position()
        self.assertEqual(state["big_run"], (True, "x"))

    def test_a_submission_still_out_does_not_tick_it(self):
        self._write_agreed([("Run the job remotely.", "job1")])
        self._submitted()
        state, _ = self._position()
        self.assertEqual(state["job1"], (None, " "))
        self.assertIn("runs remotely as job 'job1'", self._reason("job1"))
        self.assertIn("pending", self._reason("job1"))

    def test_a_rehearsal_record_alone_does_not_tick_it(self):
        self._write_agreed([("Run the job remotely.", "job1")])
        self._submitted(ledger="smoke.jsonl")
        self._returned(ledger="smoke.jsonl")
        state, _ = self._position()
        self.assertEqual(state["job1"], (None, " "))

    def test_a_result_the_source_has_moved_past_does_not_tick_it(self):
        self._write_agreed([("Run the job remotely.", "job1")])
        self._submitted(digest="0" * 64)
        self._returned()
        state, _ = self._position()
        self.assertEqual(state["job1"], (None, " "))

    def test_a_result_from_a_pin_the_job_has_moved_past_does_not_tick_it(self):
        self._write_agreed([("Run the job remotely.", "job1")])
        self._submitted()
        self._returned(ran_at=self.commit)
        (self.box / "NOTES.txt").write_text("later\n", encoding="utf-8")
        repinned = self._commit("later work")
        self._write_job_folder(repinned)
        state, _ = self._position()
        self.assertEqual(state["job1"], (None, " "))
        self.assertIn(repinned, self._reason("job1"))

    def test_a_local_step_run_does_not_tick_a_remote_step(self):
        self._write_agreed([("Run the job remotely.", "job1")])
        self._local_step_event("job1")
        state, _ = self._position()
        self.assertEqual(state["job1"], (None, " "))

    def test_a_local_step_is_measured_from_its_local_run_as_before(self):
        self._write_agreed([("Prepare.", "prep"), ("Run the job remotely.", "job1")])
        self._local_step_event("prep")
        state, _ = self._position()
        self.assertEqual(state["prep"], (True, "x"))


if __name__ == "__main__":
    unittest.main()
