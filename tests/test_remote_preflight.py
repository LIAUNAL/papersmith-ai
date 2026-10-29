"""`remote_cli preflight`: everything a first remote rehearsal used to catch,
caught locally in one command (remote-preflight S1).

Each test drives the public CLI (`remote_cli.main([...])`) against a
throwaway git target and a test backend that declares the optional
preflight hooks (`interpreter_check`, `account_check`,
`accelerator_request`). No test reaches a network: the anonymous
reachability probe is patched, and the local rehearsal runs the job's smoke
callable under this interpreter in a scratch directory.

Run with: python3 -m unittest tests.test_remote_preflight
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
import unittest
import unittest.mock
from pathlib import Path

from tests.remote_fakes import (  # noqa: F401
    ADAPTER, JOBFOLDER, LEDGER, MODULE_SOURCE, PLAIN, REMOTE_CLI, REPOSITORY_ROOT, SCRIPTS,
    SERVICE, PreflightCase, _Calls, _git, _PlainBackend, _PreflightBackend, _unreachable,
)


class PreflightShapeTests(PreflightCase):
    def test_a_ready_job_passes_every_check_and_exits_zero(self) -> None:
        job = self.generate()
        code, payload, err = self.preflight(job, "--expect-accelerator", "GPU-X")
        self.assertEqual(code, 0, (payload, err))
        checks = [row["check"] for row in payload["checks"]]
        for expected in ("pin", "diagrams", "interpreter", "code-reachability", "inputs",
                         "local-rehearsal", "account", "accelerator", "session-fit"):
            self.assertIn(expected, checks)
        for row in payload["checks"]:
            self.assertEqual(set(row) - {"worker", "details"},
                             {"check", "status", "evidence", "fix"}, row)
            self.assertIn(row["status"], ("pass", "warn", "fail"))
        self.assertEqual(payload["summary"]["fail"], 0)
        self.assertTrue(payload["summary"]["ok"])
        self.assertEqual(_Calls.submitted, [])

    def test_any_failing_row_exits_non_zero_with_the_report_on_stdout(self) -> None:
        job = self.generate(smoke="smoke_silent")
        code, payload, _ = self.preflight(job)
        self.assertEqual(code, 1)
        self.assertFalse(payload["summary"]["ok"])
        self.assertGreaterEqual(payload["summary"]["fail"], 1)

    def test_preflight_is_a_top_level_subcommand(self) -> None:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
            REMOTE_CLI.main(["preflight", "--help"])
        self.assertIn("--entrypoint", out.getvalue())
        self.assertIn("--local-smoke-kwargs", out.getvalue())

    def test_a_stale_pin_fails_and_names_regeneration(self) -> None:
        job = self.generate()
        (self.target / "src" / "pkg" / "mod.py").write_text(MODULE_SOURCE + "\n# moved\n",
                                                             encoding="utf-8")
        _git(self.target, "commit", "-qam", "move the pin")
        _, payload, _ = self.preflight(job, "--skip-rehearsal")
        row = self.row(payload, "pin")
        self.assertEqual(row["status"], "fail")
        self.assertIn("--regenerate", row["fix"])


class DiagramCheckTests(PreflightCase):
    def test_an_approval_with_an_unvalidated_diagram_fails_naming_both_routes(self) -> None:
        job = self.generate()
        (self.target / "P" / "AGREED.md").write_text("approved\n", encoding="utf-8")
        code, payload, _ = self.preflight(job, "--skip-rehearsal")
        row = self.row(payload, "diagrams")
        self.assertEqual(row["status"], "fail")
        self.assertIn("poc: absent", row["evidence"])
        self.assertIn("Validar diagrama", row["fix"])
        self.assertIn("validate", row["fix"])
        self.assertEqual(code, 1)

    def test_a_product_without_approvals_is_not_gated(self) -> None:
        job = self.generate()
        _, payload, _ = self.preflight(job, "--skip-rehearsal")
        self.assertEqual(self.row(payload, "diagrams")["status"], "pass")


class InterpreterCheckTests(PreflightCase):
    def test_an_unimportable_driver_fails_and_names_the_workspace_env(self) -> None:
        env_python = self.workspace / ".micromamba" / "envs" / "papersmith" / "bin" / "python"
        env_python.parent.mkdir(parents=True)
        env_python.write_text("#!/bin/sh\n", encoding="utf-8")
        _PreflightBackend.interpreter = {"ok": False, "evidence": "the driver is not importable"}
        job = self.generate()
        _, payload, _ = self.preflight(job, "--skip-rehearsal")
        row = self.row(payload, "interpreter")
        self.assertEqual(row["status"], "fail")
        self.assertIn(str(env_python), row["fix"])
        self.assertIn("not importable", row["evidence"])

    def test_a_service_without_the_hook_warns(self) -> None:
        job = self.generate()
        with unittest.mock.patch.object(_PreflightBackend, "interpreter_check", None):
            _, payload, _ = self.preflight(job, "--skip-rehearsal")
        self.assertEqual(self.row(payload, "interpreter")["status"], "warn")


class CodeReachabilityTests(PreflightCase):
    def test_a_bundled_job_passes_without_asking_the_remote(self) -> None:
        job = self.generate(code_bundle=True)
        self.probe.reset_mock()
        _, payload, _ = self.preflight(job, "--skip-rehearsal")
        self.assertEqual(self.row(payload, "code-reachability")["status"], "pass")
        self.probe.assert_not_called()

    def test_an_unreachable_cloned_job_fails_and_names_the_code_bundle(self) -> None:
        self.probe.side_effect = None
        job = self.generate(code_bundle=False)
        self.probe.side_effect = _unreachable
        _, payload, _ = self.preflight(job, "--skip-rehearsal")
        row = self.row(payload, "code-reachability")
        self.assertEqual(row["status"], "fail")
        self.assertIn("--code-bundle", row["fix"])

    def test_a_reachable_cloned_job_passes(self) -> None:
        self.probe.side_effect = None
        job = self.generate(code_bundle=False)
        _, payload, _ = self.preflight(job, "--skip-rehearsal")
        self.assertEqual(self.row(payload, "code-reachability")["status"], "pass")


class InputsCheckTests(PreflightCase):
    def _registry(self) -> None:
        (self.workspace / "datasets").mkdir()
        (self.workspace / "datasets" / "registry.json").write_text(json.dumps([
            {"slug": "eeg", "source": {"kind": "external", "url": "https://example.invalid/d/eeg"},
             "remote": None},
            {"slug": "toy", "source": {"kind": "synthetic", "url": ""}, "remote": None},
        ]), encoding="utf-8")

    def test_a_kernel_job_declaring_no_inputs_warns_when_the_registry_names_a_remote_source(self) -> None:
        self._registry()
        job = self.generate()
        _, payload, _ = self.preflight(job, "--skip-rehearsal")
        row = self.row(payload, "inputs")
        self.assertEqual(row["status"], "warn")
        self.assertIn("eeg", row["evidence"])
        self.assertNotIn("toy", row["evidence"])
        self.assertIn("--input-dataset", row["fix"])

    def test_a_declared_input_passes(self) -> None:
        self._registry()
        job = self.generate(input_datasets=["owner/eeg"])
        _, payload, _ = self.preflight(job, "--skip-rehearsal")
        row = self.row(payload, "inputs")
        self.assertEqual(row["status"], "pass")
        self.assertIn("owner/eeg", row["evidence"])


class LocalRehearsalTests(PreflightCase):
    def test_a_smoke_that_never_stamps_fails_in_seconds(self) -> None:
        job = self.generate(smoke="smoke_silent")
        _, payload, _ = self.preflight(job)
        row = self.row(payload, "local-rehearsal")
        self.assertEqual(row["status"], "fail")
        self.assertIn("shard.json", row["evidence"])
        self.assertIn("write_shard", row["fix"])
        self.assertIn("seconds", row["details"])

    def test_a_stamp_missing_required_evidence_fails_naming_it(self) -> None:
        job = self.generate(required=("evidence.commit", "evidence.device"))
        _, payload, _ = self.preflight(job)
        row = self.row(payload, "local-rehearsal")
        self.assertEqual(row["status"], "fail")
        self.assertIn("evidence.device", row["evidence"])

    def test_a_bundled_smoke_runs_like_the_worker_and_passes(self) -> None:
        job = self.generate(required=("evidence.commit", "evidence.mode"),
                            input_datasets=["owner/eeg"])
        keep = self.root / "kept"
        code, payload, err = self.preflight(job, "--keep-rehearsal", str(keep))
        row = self.row(payload, "local-rehearsal")
        self.assertEqual(row["status"], "pass", (row, err))
        shard = json.loads((keep / "session" / "shard.json").read_text(encoding="utf-8"))
        # No git beyond `.git/HEAD`: the commit came from FORGE_CLONE_COMMIT.
        self.assertEqual(shard["evidence"]["commit"], self.commit)
        self.assertFalse((keep / "session" / "clone" / ".git" / "objects").exists())
        self.assertEqual((keep / "session" / "clone" / ".git" / "HEAD")
                         .read_text(encoding="utf-8").strip(), self.commit)
        cwd = Path(shard["seen"]["cwd"]).resolve()
        self.assertNotIn(self.target.resolve(), [cwd, *cwd.parents])
        self.assertEqual(Path(shard["seen"]["cloneRoot"]).resolve(),
                         (keep / "session" / "clone").resolve())
        self.assertEqual(json.loads(shard["seen"]["inputs"]), {"owner/eeg": None})

    def test_local_smoke_kwargs_replace_the_declared_scale(self) -> None:
        job = self.generate(smoke_kwargs={"scale": "full"})
        keep = self.root / "kept"
        self.preflight(job, "--keep-rehearsal", str(keep),
                       "--local-smoke-kwargs", json.dumps({"scale": "tiny"}))
        shard = json.loads((keep / "session" / "shard.json").read_text(encoding="utf-8"))
        self.assertEqual(shard["seen"]["kwargs"], {"scale": "tiny"})

    def test_a_smoke_over_its_time_budget_fails(self) -> None:
        job = self.generate(smoke="smoke_sleeps")
        _, payload, _ = self.preflight(job, "--local-timeout", "2")
        row = self.row(payload, "local-rehearsal")
        self.assertEqual(row["status"], "fail")
        self.assertIn("2", row["evidence"])
        self.assertIn("--local-smoke-kwargs", row["fix"])

    def test_without_a_target_venv_the_rehearsal_fails_naming_it(self) -> None:
        job = self.generate()
        _, payload, _ = self.preflight(job, interpreter=False)
        row = self.row(payload, "local-rehearsal")
        self.assertEqual(row["status"], "fail")
        self.assertIn(".venv", row["evidence"])

    def test_the_target_venv_interpreter_is_used_by_default(self) -> None:
        venv_python = self.target / ".venv" / "bin" / "python"
        venv_python.parent.mkdir(parents=True)
        venv_python.symlink_to(sys.executable)
        job = self.generate()
        _, payload, _ = self.preflight(job, interpreter=False)
        row = self.row(payload, "local-rehearsal")
        self.assertEqual(row["status"], "pass", row)
        self.assertIn(str(venv_python), row["evidence"])

    def test_skip_rehearsal_warns(self) -> None:
        job = self.generate()
        _, payload, _ = self.preflight(job, "--skip-rehearsal")
        self.assertEqual(self.row(payload, "local-rehearsal")["status"], "warn")


class AccountCheckTests(PreflightCase):
    def test_a_failing_account_fails(self) -> None:
        _PreflightBackend.accounts = {"w1": {"ok": False, "evidence": "w1 rejected (401)",
                                             "fix": "validate it"}}
        job = self.generate()
        _, payload, _ = self.preflight(job, "--skip-rehearsal", "--worker", "w1")
        row = self.row(payload, "account")
        self.assertEqual(row["status"], "fail")
        self.assertEqual(row["worker"], "w1")
        self.assertIn("401", row["evidence"])

    def test_every_worker_is_checked_and_each_needs_its_own_rehearsal(self) -> None:
        _PreflightBackend.accounts = {"w1": {"ok": True, "evidence": "ok"},
                                      "w2": {"ok": True, "evidence": "ok"}}
        job = self.generate()
        artifact = self.root / "shard.json"
        artifact.write_text(json.dumps({"evidence": {"commit": self.commit}}), encoding="utf-8")
        REMOTE_CLI.cmd_smoke_record(job_dir=job, artifact_path=artifact, worker="w1")
        _, payload, _ = self.preflight(job, "--skip-rehearsal")
        rows = {row["worker"]: row for row in self.rows(payload, "account")}
        self.assertEqual(sorted(rows), ["w1", "w2"])
        self.assertEqual(rows["w1"]["status"], "pass")
        self.assertEqual(rows["w2"]["status"], "warn")
        self.assertIn("--smoke", rows["w2"]["fix"])
        self.assertIn("w2", rows["w2"]["fix"])


class AcceleratorCheckTests(PreflightCase):
    def test_the_service_default_is_named_and_warned_without_an_expectation(self) -> None:
        job = self.generate()
        _, payload, _ = self.preflight(job, "--skip-rehearsal")
        row = self.row(payload, "accelerator")
        self.assertEqual(row["status"], "warn")
        self.assertIn("GPU-X", row["evidence"])
        self.assertIn("default", row["evidence"])

    def test_a_mismatch_with_the_plan_fails(self) -> None:
        job = self.generate()
        _, payload, _ = self.preflight(job, "--skip-rehearsal", "--expect-accelerator", "A100")
        row = self.row(payload, "accelerator")
        self.assertEqual(row["status"], "fail")
        self.assertIn("A100", row["evidence"])
        self.assertIn("--accelerator-architecture", row["fix"])

    def test_an_expectation_matched_by_architecture_passes(self) -> None:
        job = self.generate()
        _, payload, _ = self.preflight(job, "--skip-rehearsal", "--expect-accelerator", "sm_75")
        self.assertEqual(self.row(payload, "accelerator")["status"], "pass")

    def test_a_request_problem_the_adapter_reports_fails(self) -> None:
        _PreflightBackend.accelerator = {"name": "GPU-X", "architectures": ["sm_75"],
                                         "problem": "the job declares sm_80"}
        job = self.generate()
        _, payload, _ = self.preflight(job, "--skip-rehearsal")
        row = self.row(payload, "accelerator")
        self.assertEqual(row["status"], "fail")
        self.assertIn("sm_80", row["evidence"])


class SessionFitTests(PreflightCase):
    def _timing(self, seconds_per_unit: float) -> Path:
        path = self.target / "P" / "Results" / "timing.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({
            "schema": 1,
            "measurements": [{"measuredAt": "2026-10-28T00:00:00Z", "host": f"{SERVICE}:w1",
                              "device": "cuda:GPU-X", "arm": "a", "unit": "epoch",
                              "secondsPerUnit": seconds_per_unit, "unitsMeasured": 1}],
            "scales": {"poc": {"arms": 1, "folds": 1, "seeds": 1, "epochs": 1},
                       "full": {"arms": 2, "folds": 5, "seeds": 1, "epochs": 10}},
        }), encoding="utf-8")
        return path

    def test_no_timing_record_warns_unmeasured(self) -> None:
        job = self.generate()
        _, payload, _ = self.preflight(job, "--skip-rehearsal")
        row = self.row(payload, "session-fit")
        self.assertEqual(row["status"], "warn")
        self.assertIn("unmeasured", row["evidence"])

    def test_a_unit_over_the_session_margin_fails(self) -> None:
        self._timing(120.0)  # 100 epochs x 120 s = 3.33 h > 80% of 2 h
        job = self.generate()
        _, payload, _ = self.preflight(job, "--skip-rehearsal")
        row = self.row(payload, "session-fit")
        self.assertEqual(row["status"], "fail")
        self.assertIn("--carry-path", row["fix"])

    def test_more_units_fit(self) -> None:
        self._timing(120.0)
        job = self.generate()
        _, payload, _ = self.preflight(job, "--skip-rehearsal", "--units", "10")
        self.assertEqual(self.row(payload, "session-fit")["status"], "pass")

    def test_carry_paths_alone_no_longer_pass_a_long_unit(self) -> None:
        """session-chains S1: declared carry paths are not proof of resuming;
        with the deadline rehearsal skipped the row warns."""
        self._timing(120.0)
        job = self.generate(carry_paths=["checkpoints"])
        _, payload, _ = self.preflight(job, "--skip-rehearsal")
        row = self.row(payload, "session-fit")
        self.assertEqual(row["status"], "warn")
        self.assertIn("carry", row["evidence"])
        self.assertIn("deadline rehearsal was skipped", row["evidence"])
        self.assertEqual(self.row(payload, "deadline-rehearsal")["status"], "warn")


class RehearsalScratchTests(PreflightCase):
    def test_a_failed_rehearsal_leaves_no_scratch_directory_behind(self) -> None:
        job = self.generate(smoke="smoke_silent")
        _, payload, _ = self.preflight(job)
        row = self.row(payload, "local-rehearsal")
        self.assertEqual(row["status"], "fail")
        # Its own scratch, not a glob of the shared temporary directory, which
        # tests running in parallel fill and empty under it.
        self.assertFalse(Path(row["details"]["scratch"]).exists())
        self.assertFalse(row["details"]["kept"])

    def test_keep_rehearsal_keeps_a_failed_one(self) -> None:
        job = self.generate(smoke="smoke_silent")
        keep = self.root / "kept-failure"
        _, payload, _ = self.preflight(job, "--keep-rehearsal", str(keep))
        self.assertEqual(self.row(payload, "local-rehearsal")["status"], "fail")
        self.assertTrue(keep.is_dir())

    def test_keep_rehearsal_inside_the_target_is_refused_before_anything_is_written(self) -> None:
        job = self.generate()
        keep = self.target / "kept-inside"
        code, payload, _ = self.preflight(job, "--keep-rehearsal", str(keep))
        row = self.row(payload, "local-rehearsal")
        self.assertNotEqual(code, 0)
        self.assertEqual(row["status"], "fail")
        self.assertIn("inside the target", row["evidence"])
        self.assertIn("--keep-rehearsal <new dir outside the target>", row["fix"])
        self.assertNotIn("smoke block", row["fix"])
        self.assertFalse(keep.exists())

    def test_an_existing_keep_directory_names_a_new_one_as_the_fix(self) -> None:
        job = self.generate()
        keep = self.root / "already"
        keep.mkdir()
        code, payload, _ = self.preflight(job, "--keep-rehearsal", str(keep))
        row = self.row(payload, "local-rehearsal")
        self.assertNotEqual(code, 0)
        self.assertEqual(row["status"], "fail")
        self.assertIn("already exists", row["evidence"])
        self.assertIn("--keep-rehearsal <new dir outside the target>", row["fix"])
        self.assertNotIn("smoke block", row["fix"])
        self.assertEqual(list(keep.iterdir()), [])

    def test_an_unexpected_error_fails_the_row_and_removes_the_scratch(self) -> None:
        local = REMOTE_CLI._load_sibling("remote_execution_local_rehearsal",
                                         "local_rehearsal.py")
        job = self.generate()
        with unittest.mock.patch.object(local, "materialize",
                                        side_effect=RuntimeError("boom")):
            code, payload, _ = self.preflight(job)
        row = self.row(payload, "local-rehearsal")
        self.assertNotEqual(code, 0)
        self.assertEqual(row["status"], "fail")
        self.assertIn("RuntimeError: boom", row["evidence"])
        self.assertIn("rerun preflight", row["fix"])
        self.assertFalse(row["details"]["kept"])
        self.assertFalse(Path(row["details"]["scratch"]).exists())

    def test_an_unexpected_error_keeps_the_scratch_when_asked(self) -> None:
        local = REMOTE_CLI._load_sibling("remote_execution_local_rehearsal",
                                         "local_rehearsal.py")
        job = self.generate()
        keep = self.root / "kept-error"
        with unittest.mock.patch.object(local, "materialize",
                                        side_effect=RuntimeError("boom")):
            code, payload, _ = self.preflight(job, "--keep-rehearsal", str(keep))
        row = self.row(payload, "local-rehearsal")
        self.assertNotEqual(code, 0)
        self.assertEqual(row["status"], "fail")
        self.assertIn("RuntimeError: boom", row["evidence"])
        self.assertTrue(row["details"]["kept"])
        self.assertTrue((keep / "session").is_dir())


class InputsFixTests(PreflightCase):
    def test_the_inputs_warning_names_the_registry_flag_too(self) -> None:
        (self.workspace / "datasets").mkdir()
        (self.workspace / "datasets" / "registry.json").write_text(json.dumps([
            {"slug": "eeg", "source": {"kind": "external", "url": "https://x.invalid/eeg"},
             "remote": None}]), encoding="utf-8")
        job = self.generate()
        _, payload, _ = self.preflight(job, "--skip-rehearsal")
        row = self.row(payload, "inputs")
        self.assertEqual(row["status"], "warn")
        self.assertIn("--dataset <slug>", row["fix"])
        self.assertIn("--input-dataset <owner>/<slug>", row["fix"])


class PreflightVocabularyTests(unittest.TestCase):
    def test_the_rehearsal_module_names_no_service(self) -> None:
        source = (SCRIPTS / "local_rehearsal.py").read_text(encoding="utf-8").lower()
        for leaked in ("kaggle", "colab", "t4", "a100"):
            self.assertNotIn(leaked, source, leaked)

    def test_the_abc_keeps_six_operations(self) -> None:
        self.assertEqual(len(ADAPTER.Adapter.__abstractmethods__), 6)
        for hook in ("interpreter_check", "account_check", "accelerator_request"):
            self.assertNotIn(hook, ADAPTER.Adapter.__abstractmethods__)


if __name__ == "__main__":
    unittest.main()
