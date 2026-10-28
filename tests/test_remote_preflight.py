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
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPOSITORY_ROOT / "skills/remote-execution/scripts"


def _load_or_reuse(module_name: str, script: Path):
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(module_name, script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


LEDGER = _load_or_reuse("remote_execution_ledger", SCRIPTS / "ledger.py")
ADAPTER = _load_or_reuse("remote_execution_adapter", SCRIPTS / "adapter.py")
REMOTE_CLI = _load_or_reuse("remote_execution_cli", SCRIPTS / "remote_cli.py")
JOBFOLDER = sys.modules["remote_execution_jobfolder"]

SERVICE = "preflight-carrier"
PLAIN = "preflight-plain"


class _Calls:
    submitted: list = []


class _PreflightBackend(ADAPTER.Adapter):
    """A kernel-style test backend: carries code bundles and input
    datasets, declares a session limit and every preflight hook."""

    CODE_BUNDLE_MAX_BYTES = 1_000_000
    INPUT_DATASETS_ROOT = "/inputs"
    interpreter = {"ok": True, "evidence": "the driver imports under this interpreter"}
    accounts = {"w1": {"ok": True, "evidence": "w1 authenticates"}}
    accelerator = {"name": "GPU-X", "architectures": ["sm_75"], "problem": None}

    @classmethod
    def session_limit_seconds(cls, machine_shape=None):
        return 2 * 3600

    def workers(self):
        return [ADAPTER.Worker(id=w, capacity=1) for w in sorted(self.accounts)]

    def submit(self, job):  # pragma: no cover - preflight must never call it
        _Calls.submitted.append(job)
        raise AssertionError("preflight submitted a job")

    def poll(self, submission_id):
        raise AssertionError("preflight polled")

    def fetch(self, submission_id, into):
        raise AssertionError("preflight fetched")

    def cancel(self, submission_id):
        raise AssertionError("preflight cancelled")

    def list_active(self, worker):
        return []

    def interpreter_check(self):
        return dict(self.interpreter)

    def account_check(self, worker):
        return dict(self.accounts.get(worker) or {"ok": False, "evidence": f"{worker} unknown",
                                                  "fix": "register it"})

    def accelerator_request(self, run_config):
        return dict(self.accelerator)


class _PlainBackend(_PreflightBackend):
    """No code bundle, no input attachment, no repo credential."""

    CODE_BUNDLE_MAX_BYTES = None
    INPUT_DATASETS_ROOT = None


for _name, _cls in ((SERVICE, _PreflightBackend), (PLAIN, _PlainBackend)):
    ADAPTER.register(_name, _cls)
    ADAPTER.register_metadata(_name, lambda rc: ("fake-metadata.json", json.dumps({"ok": True})))
    ADAPTER.register_default_accelerator(_name, lambda: ("cuda", ("sm_75",)))


MODULE_SOURCE = '''\
import json
import os
import subprocess
import time
from pathlib import Path


def run(**kwargs):
    return 1


def _commit():
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"],
                             cwd=Path(__file__).resolve().parent,
                             capture_output=True, text=True)
    except OSError:
        out = None
    if out is not None and out.returncode == 0 and out.stdout.strip():
        return out.stdout.strip()
    return os.environ.get("FORGE_CLONE_COMMIT")


def smoke_stamps(**kwargs):
    evidence = {"commit": _commit()}
    if os.environ.get("FORGE_RUN_MODE") == "smoke":
        evidence["mode"] = "smoke"
    Path("shard.json").write_text(json.dumps({
        "evidence": evidence,
        "seen": {"cwd": os.getcwd(), "kwargs": kwargs,
                 "cloneRoot": os.environ.get("FORGE_CLONE_ROOT"),
                 "inputs": os.environ.get("FORGE_INPUT_DATASETS")},
    }), encoding="utf-8")
    return evidence


def smoke_silent(**kwargs):
    return 1


def smoke_sleeps(**kwargs):
    time.sleep(float(kwargs.get("seconds", 30)))
'''


def _git(cwd: Path, *args: str) -> str:
    env = dict(os.environ)
    env["GIT_AUTHOR_NAME"] = env["GIT_COMMITTER_NAME"] = "preflight-tests"
    env["GIT_AUTHOR_EMAIL"] = env["GIT_COMMITTER_EMAIL"] = "preflight@example.invalid"
    return subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True,
                          text=True, check=True).stdout.strip()


def _unreachable(*args, **kwargs):
    raise JOBFOLDER.JobFolderError("the declared remote could not serve the pin (private)")


class PreflightCase(unittest.TestCase):
    def setUp(self) -> None:
        box = tempfile.TemporaryDirectory()
        self.addCleanup(box.cleanup)
        self.root = Path(box.name)
        self.target = self.root / "repo"
        (self.target / "src" / "pkg").mkdir(parents=True)
        (self.target / "src" / "pkg" / "__init__.py").write_text("", encoding="utf-8")
        (self.target / "src" / "pkg" / "mod.py").write_text(MODULE_SOURCE, encoding="utf-8")
        (self.target / "P").mkdir()
        (self.target / "P" / "README.md").write_text("product\n", encoding="utf-8")
        _git(self.target, "init", "-q")
        _git(self.target, "add", "-A")
        _git(self.target, "commit", "-q", "-m", "initial")
        self.commit = _git(self.target, "rev-parse", "HEAD")
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        # Generation's reachability probe is private by default here.
        patcher = unittest.mock.patch.object(
            JOBFOLDER, "_verify_commit_reachable", side_effect=_unreachable)
        self.probe = patcher.start()
        self.addCleanup(patcher.stop)
        _Calls.submitted = []
        for cls in (_PreflightBackend, _PlainBackend):
            self.addCleanup(setattr, cls, "accounts", dict(cls.accounts))
            self.addCleanup(setattr, cls, "interpreter", dict(cls.interpreter))
            self.addCleanup(setattr, cls, "accelerator", dict(cls.accelerator))

    def generate(self, *, service: str = SERVICE, smoke: str = "smoke_stamps",
                 code_bundle: bool = True, required=("evidence.commit",), **extra) -> Path:
        kwargs = dict(
            target=self.target, service=service, job_name="job-a", product="P",
            commit=self.commit, repo_url="https://example.invalid/private.git",
            repo_ref="main", clone_paths=["src/pkg"], run_module="pkg.mod",
            run_function="run", smoke_module="pkg.mod", smoke_function=smoke,
            smoke_required_evidence=list(required) or None, code_bundle=code_bundle,
        )
        kwargs.update(extra)
        return JOBFOLDER.generate_job(**kwargs)

    def preflight(self, job_dir: Path, *extra: str, interpreter: bool = True) -> tuple[int, dict, str]:
        argv = ["preflight", "--target", str(self.target),
                "--entrypoint", str(job_dir / "runner.ipynb"),
                "--workspace", str(self.workspace)]
        if interpreter:
            argv += ["--interpreter", sys.executable]
        argv += list(extra)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = REMOTE_CLI.main(argv)
        payload = json.loads(out.getvalue()) if out.getvalue().strip() else {}
        return code, payload, err.getvalue()

    @staticmethod
    def rows(payload: dict, check: str) -> list[dict]:
        return [row for row in payload["checks"] if row["check"] == check]

    def row(self, payload: dict, check: str) -> dict:
        found = self.rows(payload, check)
        self.assertEqual(len(found), 1, (check, payload))
        return found[0]


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

    def test_carry_paths_admit_a_long_unit(self) -> None:
        self._timing(120.0)
        job = self.generate(carry_paths=["checkpoints"])
        _, payload, _ = self.preflight(job, "--skip-rehearsal")
        row = self.row(payload, "session-fit")
        self.assertEqual(row["status"], "pass")
        self.assertIn("carry", row["evidence"])


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
