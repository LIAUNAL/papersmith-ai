"""`generate-jobs` options (odd/tasks/generate-jobs-options.md, T1, S1-S5):
per-job smoke kwargs, extra carry paths, input datasets, and step selection,
so a campaign never falls back to regenerating its jobs one by one.

Every option is pinned the same way: the job `generate-jobs` writes is
byte-identical to the one `generate-job` writes with the equivalent flags
(the second call regenerates the same folder, and every file is compared).
Without the new options, the output is pinned against a golden captured from
v0.38.0 before any of this existed.

Every test drives the public CLI (`remote_cli.main([...])`) against a
throwaway git target and the in-process test backends; no test reaches a
network: the reachability probe is patched.

Run with: python3 -m pytest -q tests/test_generate_jobs_options.py
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
import unittest
from pathlib import Path

from tests import test_remote_generate_jobs as base
from tests.remote_fakes import PLAIN, REMOTE_CLI, SERVICE, _git

HOSTED = base.HOSTED
REPO_URL = "https://example.invalid/private.git"
_cli = base._cli

# e1 declares its own smoke kwargs and an extra carry path, e2 declares
# nothing new, e5 declares its whole smoke and runs on a service that neither
# carries code bundles nor attaches inputs.
STEPS_SOURCE = '''\
__steps__ = {
    "e1": {
        "module": "pkg.mod", "function": "run", "advances": 1, "reads": [],
        "produces": ["Results/e1"], "placement": "remote", "job": "e1",
        "service": "%(carrier)s",
        "smoke": {"kwargs": {"steps": ["e1"]}}, "carry": ["Results/checkpoints"],
    },
    "e2": {
        "module": "pkg.mod", "function": "run", "advances": 2, "reads": ["Results/e1"],
        "produces": ["Results/e2"], "placement": "remote", "job": "e2",
        "service": "%(carrier)s",
    },
    "e5": {
        "module": "pkg.mod", "function": "run", "advances": 3,
        "produces": ["Results/e5"], "placement": "remote", "job": "e5",
        "service": "%(plain)s",
        "smoke": {"module": "pkg.mod", "function": "smoke_stamps",
                  "kwargs": {"steps": ["e5"]}, "requiredEvidence": ["evidence.commit"]},
    },
    "render": {
        "module": "pkg.mod", "function": "run", "advances": 4,
        "produces": ["Notebooks/render.ipynb"], "placement": "local",
    },
}
'''

PIN = "numpy==1.26.4"
GLOBAL_SMOKE = ("--smoke-module", "pkg.mod", "--smoke-function", "smoke_stamps",
                "--smoke-required-evidence", "evidence.commit")


def _snapshot(root: Path) -> dict[str, bytes]:
    """Every file under `root`, by relative path, as bytes."""
    if not root.exists():
        return {}
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in sorted(root.rglob("*")) if p.is_file()}


class _OptionsCase(base._Case):
    def setUp(self) -> None:
        super().setUp()
        self.write_steps(STEPS_SOURCE % {"carrier": SERVICE, "plain": PLAIN})
        (self.target / "requirements.txt").write_text(PIN + "\n", encoding="utf-8")
        _git(self.target, "remote", "add", "origin", REPO_URL)
        self.commit_all("declare steps")
        self.branch = _git(self.target, "rev-parse", "--abbrev-ref", "HEAD")

    def write_steps(self, source: str) -> None:
        (self.target / "src" / "P").mkdir(exist_ok=True)
        (self.target / "src" / "P" / "__init__.py").write_text(source, encoding="utf-8")

    def commit_all(self, message: str) -> None:
        _git(self.target, "add", "-A")
        _git(self.target, "commit", "-q", "-m", message)
        self.commit = _git(self.target, "rev-parse", "HEAD")

    def generate_jobs(self, *extra: str) -> tuple[int, dict, str]:
        return _cli(["generate-jobs", "--target", str(self.target), "--product", "P", *extra])

    def folder(self, service: str, job: str) -> Path:
        return self.target / "tools" / service / job

    def config(self, service: str, job: str) -> dict:
        return json.loads((self.folder(service, job) / "run-config.json").read_text("utf-8"))

    def row(self, payload: dict, step: str) -> dict:
        rows = [row for row in payload["jobs"] if row["step"] == step]
        self.assertEqual(len(rows), 1, payload)
        return rows[0]

    def assert_generate_job_writes_the_same(self, service: str, job: str, *flags: str,
                                            bundle: bool = True) -> None:
        """Regenerate `tools/<service>/<job>` with `generate-job` and the
        flags equivalent to what `generate-jobs` derived: every byte holds."""
        written = _snapshot(self.folder(service, job))
        self.assertIn("run-config.json", written)
        code, _, err = _cli([
            "generate-job", "--target", str(self.target), "--service", service,
            "--job-name", job, "--product", "P", "--commit", self.commit,
            "--repo-url", REPO_URL, "--repo-ref", self.branch, "--regenerate",
            "--clone-path", "src/pkg", "--run-module", "pkg.mod", "--run-function", "run",
            "--environment-requirement", PIN, *(["--code-bundle"] if bundle else []),
            *flags])
        self.assertEqual(code, 0, err)
        regenerated = _snapshot(self.folder(service, job))
        self.assertEqual(sorted(regenerated), sorted(written))
        for name in written:
            self.assertEqual(regenerated[name], written[name], name)


# ------------------------------------------------------- S1: smoke per job
class SmokePerJobTests(_OptionsCase):
    def test_a_steps_own_smoke_kwargs_beat_the_global_ones(self) -> None:
        code, payload, err = self.generate_jobs(*GLOBAL_SMOKE, "--smoke-kwargs",
                                                '{"fast": true}', "--only", "e1",
                                                "--only", "e2")
        self.assertEqual(code, 0, (payload, err))
        self.assertEqual(self.config(SERVICE, "e1")["run"]["smoke"]["kwargs"],
                         {"steps": ["e1"]})
        self.assertEqual(self.config(SERVICE, "e2")["run"]["smoke"]["kwargs"], {"fast": True})
        self.assert_generate_job_writes_the_same(
            SERVICE, "e1", *GLOBAL_SMOKE, "--smoke-kwargs", '{"steps": ["e1"]}',
            "--carry-path", "Results/e1", "--carry-path", "Results/checkpoints")
        self.assert_generate_job_writes_the_same(
            SERVICE, "e2", *GLOBAL_SMOKE, "--smoke-kwargs", '{"fast": true}',
            "--carry-path", "Results/e2")

    def test_smoke_kwargs_for_wins_over_the_steps_declaration(self) -> None:
        code, payload, err = self.generate_jobs(
            *GLOBAL_SMOKE, "--only", "e1", "--only", "e2",
            "--smoke-kwargs-for", "e1", '{"steps": ["e1"], "n": 1}',
            "--smoke-kwargs-for", "e2", '{"steps": ["e2"]}')
        self.assertEqual(code, 0, (payload, err))
        self.assertEqual(self.config(SERVICE, "e1")["run"]["smoke"]["kwargs"],
                         {"steps": ["e1"], "n": 1})
        self.assertEqual(self.config(SERVICE, "e2")["run"]["smoke"]["kwargs"],
                         {"steps": ["e2"]})
        self.assert_generate_job_writes_the_same(
            SERVICE, "e1", *GLOBAL_SMOKE, "--smoke-kwargs", '{"steps": ["e1"], "n": 1}',
            "--carry-path", "Results/e1", "--carry-path", "Results/checkpoints")
        self.assert_generate_job_writes_the_same(
            SERVICE, "e2", *GLOBAL_SMOKE, "--smoke-kwargs", '{"steps": ["e2"]}',
            "--carry-path", "Results/e2")

    def test_a_step_may_declare_its_whole_smoke(self) -> None:
        self.probe.side_effect = None  # e5's service carries no code bundle
        code, payload, err = self.generate_jobs("--only", "e5")
        self.assertEqual(code, 0, (payload, err))
        self.assertEqual(self.config(PLAIN, "e5")["run"]["smoke"],
                         {"module": "pkg.mod", "function": "smoke_stamps",
                          "kwargs": {"steps": ["e5"]},
                          "requiredEvidence": ["evidence.commit"]})
        self.assert_generate_job_writes_the_same(
            PLAIN, "e5", *GLOBAL_SMOKE, "--smoke-kwargs", '{"steps": ["e5"]}',
            "--carry-path", "Results/e5", bundle=False)

    def test_smoke_kwargs_for_must_be_a_json_object(self) -> None:
        for value in ('{"steps": ', "[1]"):
            code, _, err = self.generate_jobs(*GLOBAL_SMOKE, "--smoke-kwargs-for", "e1", value)
            self.assertEqual(code, 1, value)
            self.assertIn("--smoke-kwargs-for e1", err)
            self.assertFalse((self.target / "tools").exists())

    def test_smoke_kwargs_for_one_step_twice_refuses(self) -> None:
        code, _, err = self.generate_jobs(*GLOBAL_SMOKE, "--smoke-kwargs-for", "e1", "{}",
                                          "--smoke-kwargs-for", "e1", '{"n": 1}')
        self.assertEqual(code, 1)
        self.assertIn("--smoke-kwargs-for e1", err)
        self.assertFalse((self.target / "tools").exists())

    def test_a_malformed_smoke_declaration_refuses_that_job_only(self) -> None:
        self.write_steps((STEPS_SOURCE % {"carrier": SERVICE, "plain": PLAIN}).replace(
            '"smoke": {"kwargs": {"steps": ["e1"]}}', '"smoke": {"kwargs": ["e1"]}'))
        self.commit_all("malformed smoke")
        code, payload, _ = self.generate_jobs(*GLOBAL_SMOKE, "--only", "e1", "--only", "e2")
        self.assertEqual(code, 1)
        self.assertEqual(self.row(payload, "e1")["status"], "refused")
        self.assertIn("STEP_DECLARATION_MALFORMED", self.row(payload, "e1")["error"])
        self.assertEqual(self.row(payload, "e2")["status"], "generated")
        self.assertFalse(self.folder(SERVICE, "e1").exists())


# ---------------------------------------------------- S2: extra carry paths
class CarryPathTests(_OptionsCase):
    def test_declared_and_flagged_carry_paths_follow_the_produces_ones(self) -> None:
        code, payload, err = self.generate_jobs(
            *GLOBAL_SMOKE, "--only", "e1", "--carry-path-for", "e1", "Results/studies",
            "--carry-path-for", "e1", "Results/checkpoints")
        self.assertEqual(code, 0, (payload, err))
        carry = ["Results/e1", "Results/checkpoints", "Results/studies"]
        self.assertEqual(self.config(SERVICE, "e1")["carryPaths"], carry)
        self.assertEqual(self.row(payload, "e1")["carryPaths"], carry)
        self.assert_generate_job_writes_the_same(
            SERVICE, "e1", *GLOBAL_SMOKE, "--smoke-kwargs", '{"steps": ["e1"]}',
            *[arg for path in carry for arg in ("--carry-path", path)])

    def test_a_carry_path_is_validated_as_generate_job_validates_it(self) -> None:
        code, payload, _ = self.generate_jobs(*GLOBAL_SMOKE, "--only", "e2",
                                              "--carry-path-for", "e2", "../outside")
        self.assertEqual(code, 1)
        row = self.row(payload, "e2")
        self.assertEqual(row["status"], "refused")
        self.assertFalse(self.folder(SERVICE, "e2").exists())
        _, _, err = _cli(["generate-job", "--target", str(self.target), "--service", SERVICE,
                          "--job-name", "e2", "--product", "P", "--repo-url", REPO_URL,
                          "--repo-ref", self.branch, "--clone-path", "src/pkg",
                          "--run-module", "pkg.mod", "--run-function", "run",
                          "--code-bundle", "--carry-path", "Results/e2",
                          "--carry-path", "../outside"])
        self.assertIn(row["error"], err)

    def test_a_malformed_carry_declaration_refuses_that_job_only(self) -> None:
        self.write_steps((STEPS_SOURCE % {"carrier": SERVICE, "plain": PLAIN}).replace(
            '"carry": ["Results/checkpoints"]', '"carry": "Results/checkpoints"'))
        self.commit_all("malformed carry")
        code, payload, _ = self.generate_jobs(*GLOBAL_SMOKE, "--only", "e1")
        self.assertEqual(code, 1)
        self.assertIn("STEP_DECLARATION_MALFORMED", self.row(payload, "e1")["error"])


# ------------------------------------------------------ S3: input datasets
class InputDatasetTests(_OptionsCase):
    def setUp(self) -> None:
        super().setUp()
        self.probe.side_effect = None  # reachable: e5's service needs a clone

    def test_input_dataset_reaches_every_job_of_a_service_that_attaches(self) -> None:
        code, payload, err = self.generate_jobs(
            *GLOBAL_SMOKE, "--input-dataset", "lab/eeg", "--input-dataset", "lab/labels",
            "--input-dataset-for", "e1", "lab/extra", "--input-dataset-for", "e5", "lab/e5")
        self.assertEqual(code, 0, (payload, err))
        self.assertEqual(self.config(SERVICE, "e1")["inputDatasets"],
                         ["lab/eeg", "lab/labels", "lab/extra"])
        self.assertEqual(self.config(SERVICE, "e2")["inputDatasets"], ["lab/eeg", "lab/labels"])
        # e5's service attaches nothing: only what was named for it.
        self.assertEqual(self.config(PLAIN, "e5")["inputDatasets"], ["lab/e5"])
        self.assertEqual(self.row(payload, "e5")["inputDatasets"], ["lab/e5"])
        for service, job in ((SERVICE, "e1"), (SERVICE, "e2"), (PLAIN, "e5")):
            self.assertNotIn("datasetChecks", self.config(service, job))
        self.assert_generate_job_writes_the_same(
            SERVICE, "e1", *GLOBAL_SMOKE, "--smoke-kwargs", '{"steps": ["e1"]}',
            "--carry-path", "Results/e1", "--carry-path", "Results/checkpoints",
            "--input-dataset", "lab/eeg", "--input-dataset", "lab/labels",
            "--input-dataset", "lab/extra", bundle=False)
        self.assert_generate_job_writes_the_same(
            PLAIN, "e5", *GLOBAL_SMOKE, "--smoke-kwargs", '{"steps": ["e5"]}',
            "--carry-path", "Results/e5", "--input-dataset", "lab/e5", bundle=False)

    def test_a_service_that_attaches_nothing_gets_no_global_input(self) -> None:
        code, payload, err = self.generate_jobs(*GLOBAL_SMOKE, "--only", "e5",
                                                "--input-dataset", "lab/eeg")
        self.assertEqual(code, 0, (payload, err))
        self.assertNotIn("inputDatasets", self.config(PLAIN, "e5"))
        self.assertEqual(self.row(payload, "e5")["inputDatasets"], [])

    def test_a_ref_named_globally_and_per_step_is_declared_once(self) -> None:
        code, payload, err = self.generate_jobs(*GLOBAL_SMOKE, "--only", "e2",
                                                "--input-dataset", "lab/eeg",
                                                "--input-dataset-for", "e2", "lab/eeg")
        self.assertEqual(code, 0, (payload, err))
        self.assertEqual(self.config(SERVICE, "e2")["inputDatasets"], ["lab/eeg"])

    def test_input_dataset_beside_dataset_keeps_the_explicit_refs_first(self) -> None:
        self.registry(self.entry(
            "adhd", url="https://www.kaggle.com/datasets/danizo/eeg-dataset-for-adhd"))
        code, payload, err = self.generate_jobs(
            *GLOBAL_SMOKE, "--only", "e2", "--workspace", str(self.workspace),
            "--dataset", "adhd", "--input-dataset", "other/set")
        self.assertEqual(code, 0, (payload, err))
        config = self.config(SERVICE, "e2")
        self.assertEqual(config["inputDatasets"], ["other/set", "danizo/eeg-dataset-for-adhd"])
        self.assertEqual(set(config["datasetChecks"]), {"danizo/eeg-dataset-for-adhd"})
        self.assert_generate_job_writes_the_same(
            SERVICE, "e2", *GLOBAL_SMOKE, "--carry-path", "Results/e2",
            "--workspace", str(self.workspace), "--dataset", "adhd",
            "--input-dataset", "other/set", bundle=False)

    def test_a_malformed_ref_refuses_as_generate_job_refuses_it(self) -> None:
        code, payload, _ = self.generate_jobs(*GLOBAL_SMOKE, "--only", "e2",
                                              "--input-dataset-for", "e2", "not a ref")
        self.assertEqual(code, 1)
        row = self.row(payload, "e2")
        self.assertEqual(row["status"], "refused")
        self.assertFalse(self.folder(SERVICE, "e2").exists())
        _, _, err = _cli(["generate-job", "--target", str(self.target), "--service", SERVICE,
                          "--job-name", "e2", "--product", "P", "--repo-url", REPO_URL,
                          "--repo-ref", self.branch, "--clone-path", "src/pkg",
                          "--run-module", "pkg.mod", "--run-function", "run",
                          "--input-dataset", "not a ref"])
        self.assertIn(row["error"], err)


# --------------------------------------------------------------- S4: selection
class SelectionTests(_OptionsCase):
    def test_skip_leaves_a_finished_job_untouched(self) -> None:
        self.probe.side_effect = None
        code, payload, err = self.generate_jobs(*GLOBAL_SMOKE)
        self.assertEqual(code, 0, (payload, err))
        finished = _snapshot(self.folder(PLAIN, "e5"))
        (self.target / "README.md").write_text("moved pin\n", encoding="utf-8")
        self.commit_all("move the pin")
        code, payload, err = self.generate_jobs(*GLOBAL_SMOKE, "--regenerate", "--skip", "e5")
        self.assertEqual(code, 0, (payload, err))
        self.assertEqual({row["step"] for row in payload["jobs"]}, {"e1", "e2"})
        self.assertEqual(self.config(SERVICE, "e1")["commit"], self.commit)
        self.assertEqual(_snapshot(self.folder(PLAIN, "e5")), finished)
        self.assertIn({"step": "e5", "reason": "excluded by --skip"}, payload["skipped"])
        self.assertIn({"step": "render", "reason": "placement 'local'"}, payload["skipped"])
        self.assertEqual(payload["next"].count("--entrypoint"), 2)

    def test_only_generates_just_the_named_steps(self) -> None:
        code, payload, err = self.generate_jobs(*GLOBAL_SMOKE, "--only", "e2")
        self.assertEqual(code, 0, (payload, err))
        self.assertEqual([row["step"] for row in payload["jobs"]], ["e2"])
        self.assertEqual(payload["skipped"], [
            {"step": "e1", "reason": "not named by --only"},
            {"step": "e5", "reason": "not named by --only"},
            {"step": "render", "reason": "placement 'local'"}])
        self.assertFalse(self.folder(SERVICE, "e1").exists())
        self.assert_generate_job_writes_the_same(
            SERVICE, "e2", *GLOBAL_SMOKE, "--carry-path", "Results/e2")

    def test_a_schedule_naming_a_skipped_step_is_not_refused(self) -> None:
        schedule = self.root / "schedule.json"
        schedule.write_text(json.dumps({"steps": [
            {"id": "e1", "services": [SERVICE]}, {"id": "e2", "services": [SERVICE]},
            {"id": "e5", "services": [PLAIN]}], "makespanMinutes": 10}), encoding="utf-8")
        code, payload, err = self.generate_jobs(*GLOBAL_SMOKE, "--from-schedule", str(schedule),
                                                "--skip", "e5")
        self.assertEqual(code, 0, (payload, err))
        self.assertEqual({row["step"] for row in payload["jobs"]}, {"e1", "e2"})
        self.assertIn({"step": "e5", "reason": "excluded by --skip"}, payload["skipped"])
        self.assertFalse(self.folder(PLAIN, "e5").exists())
        before = _snapshot(self.target / "tools")
        code, payload, err = self.generate_jobs(*GLOBAL_SMOKE, "--regenerate",
                                                "--from-schedule", str(schedule),
                                                "--only", "ghost")
        self.assertEqual(code, 1)
        self.assertIn("STEP_UNKNOWN", err)
        self.assertEqual(_snapshot(self.target / "tools"), before)

    def assert_refused_before_writing(self, *extra: str, says: str) -> None:
        before = _snapshot(self.target / "tools")
        code, payload, err = self.generate_jobs(*GLOBAL_SMOKE, "--regenerate", *extra)
        self.assertEqual(code, 1, (extra, payload))
        self.assertEqual(payload, {}, extra)
        self.assertIn(says, err, extra)
        self.assertEqual(_snapshot(self.target / "tools"), before, extra)

    def test_an_unknown_step_is_refused_before_anything_is_written(self) -> None:
        for extra in (("--only", "ghost"), ("--skip", "ghost"),
                      ("--smoke-kwargs-for", "ghost", "{}"),
                      ("--carry-path-for", "ghost", "Results/x"),
                      ("--input-dataset-for", "ghost", "lab/x")):
            self.assert_refused_before_writing(*extra, says="STEP_UNKNOWN")
            self.assertFalse((self.target / "tools").exists(), extra)

    def test_an_unknown_step_leaves_existing_jobs_unchanged(self) -> None:
        code, _, err = self.generate_jobs(*GLOBAL_SMOKE, "--only", "e2")
        self.assertEqual(code, 0, err)
        (self.target / "README.md").write_text("moved pin\n", encoding="utf-8")
        self.commit_all("move the pin")
        for extra in (("--only", "e2", "--only", "ghost"),
                      ("--skip", "ghost"), ("--carry-path-for", "ghost", "Results/x")):
            self.assert_refused_before_writing(*extra, says="STEP_UNKNOWN")

    def test_a_local_step_is_not_a_step_to_select(self) -> None:
        self.assert_refused_before_writing("--only", "render", says="placement 'local'")
        self.assertFalse((self.target / "tools").exists())

    def test_only_and_skip_naming_the_same_step_refuses(self) -> None:
        self.assert_refused_before_writing("--only", "e1", "--skip", "e1",
                                           says="STEP_SELECTION_CONFLICT")
        self.assertFalse((self.target / "tools").exists())

    def test_a_value_for_a_step_left_out_refuses(self) -> None:
        self.assert_refused_before_writing("--skip", "e1", "--carry-path-for", "e1", "R/x",
                                           says="STEP_SELECTION_CONFLICT")
        self.assert_refused_before_writing("--only", "e2", "--smoke-kwargs-for", "e1", "{}",
                                           says="STEP_SELECTION_CONFLICT")

    def test_a_selection_that_leaves_nothing_refuses(self) -> None:
        self.assert_refused_before_writing("--skip", "e1", "--skip", "e2", "--skip", "e5",
                                           says="STEP_SELECTION_CONFLICT")
        self.assertFalse((self.target / "tools").exists())


# ----------------------------------------- S5: no new option, no new output
#: Captured from v0.38.0 (`origin/main` 1392aed0) before any option existed,
#: over `tests/test_remote_generate_jobs.py`'s own fixture. Hashes that move
#: with the pin or with an asset are placeholders: the byte-identity tests
#: below hold those bytes against `generate-job` instead.
GOLDEN_CONFIGS = {
    "compute": {
        "accelerator": {"architectures": ["sm_75"], "kind": "cuda"},
        "carryPaths": ["Results/compute"],
        "clonePaths": ["src/pkg", "P/Notebooks/compute.ipynb"],
        "codeBundle": {"bytes": "<BYTES>", "file": "code-bundle.tar.gz", "format": "tar.gz",
                       "sha256": "<SHA256>"},
        "commit": "<COMMIT>",
        "environment": {"install": {"requirements": ["numpy==1.26.4", "torch==2.3.0"]}},
        "jobName": "compute", "product": "P",
        "repo": {"ref": "<BRANCH>", "url": REPO_URL},
        "run": {"notebook": "P/Notebooks/compute.ipynb",
                "smoke": {"function": "smoke_stamps", "kwargs": {}, "module": "pkg.mod",
                          "requiredEvidence": ["evidence.commit"]}},
        "runnerTemplate": [{"path": "assets/runner_bootstrap.py", "sha256": "<SHA256>"},
                           {"path": "assets/runner_invoke.py", "sha256": "<SHA256>"}],
        "schemaVersion": 1, "service": SERVICE,
    },
    "train": {
        "accelerator": {"architectures": ["sm_75"], "kind": "cuda"},
        "carryPaths": ["Results/train"],
        "clonePaths": ["src/pkg"],
        "codeBundle": {"bytes": "<BYTES>", "file": "code-bundle.tar.gz", "format": "tar.gz",
                       "sha256": "<SHA256>"},
        "commit": "<COMMIT>",
        "environment": {"install": {"requirements": ["numpy==1.26.4"]}},
        "jobName": "train", "product": "P",
        "repo": {"ref": "<BRANCH>", "url": REPO_URL},
        "run": {"function": "run", "kwargs": {}, "module": "pkg.mod",
                "smoke": {"function": "smoke_stamps", "kwargs": {}, "module": "pkg.mod",
                          "requiredEvidence": ["evidence.commit"]}},
        "runnerTemplate": [{"path": "assets/runner_bootstrap.py", "sha256": "<SHA256>"},
                           {"path": "assets/runner_invoke.py", "sha256": "<SHA256>"}],
        "schemaVersion": 1, "service": HOSTED,
    },
}
GOLDEN_FILES = ["code-bundle.tar.gz", "fake-metadata.json", "run-config.json", "runner.ipynb"]
GOLDEN_PAYLOAD = {
    "commit": "<COMMIT>",
    "jobs": [
        {"carryPaths": ["Results/compute"], "codeBundle": True,
         "environmentRequirements": ["numpy==1.26.4", "torch==2.3.0"], "inputDatasets": [],
         "job": "compute", "jobFolder": f"<TARGET>/tools/{SERVICE}/compute",
         "service": SERVICE, "status": "generated", "step": "compute"},
        {"carryPaths": ["Results/train"], "codeBundle": True,
         "environmentRequirements": ["numpy==1.26.4"], "inputDatasets": [],
         "job": "train", "jobFolder": f"<TARGET>/tools/{HOSTED}/train",
         "service": HOSTED, "status": "generated", "step": "train"},
    ],
    "next": ("<PYTHON> <CLI> preflight --target <TARGET> --workspace <WORKSPACE>"
             f" --entrypoint <TARGET>/tools/{SERVICE}/compute/runner.ipynb"
             f" --entrypoint <TARGET>/tools/{HOSTED}/train/runner.ipynb"),
    "product": "P",
    "skipped": [{"reason": "placement 'local'", "step": "render"}],
    "summary": {"generated": 2, "refused": 0},
    "target": "<TARGET>",
}


class WithoutOptionsTests(base._Case):
    """The v0.38.0 fixture of `test_remote_generate_jobs.py`, unchanged."""

    def setUp(self) -> None:
        super().setUp()
        (self.target / "src" / "P").mkdir()
        (self.target / "src" / "P" / "__init__.py").write_text(
            base.STEPS_SOURCE % {"carrier": SERVICE, "hosted": HOSTED}, encoding="utf-8")
        (self.target / "P" / "Notebooks").mkdir()
        (self.target / "P" / "Notebooks" / "compute.ipynb").write_text(json.dumps({
            "cells": [{"cell_type": "code", "metadata": {}, "execution_count": None,
                       "outputs": [], "source": ["import pkg.mod\n"]}],
            "metadata": {}, "nbformat": 4, "nbformat_minor": 5}), encoding="utf-8")
        (self.target / "requirements.txt").write_text(
            "# pinned\nnumpy==1.26.4\ntorch==2.3.0\n-r other.txt\n", encoding="utf-8")
        _git(self.target, "remote", "add", "origin", REPO_URL)
        _git(self.target, "add", "-A")
        _git(self.target, "commit", "-q", "-m", "declare steps")
        self.commit = _git(self.target, "rev-parse", "HEAD")
        self.branch = _git(self.target, "rev-parse", "--abbrev-ref", "HEAD")

    def generate_jobs(self) -> tuple[int, dict, str]:
        return _cli(["generate-jobs", "--target", str(self.target), "--product", "P",
                     "--workspace", str(self.workspace), *GLOBAL_SMOKE])

    def normalized(self, text: str) -> str:
        for real, placeholder in (
                (str(Path(REMOTE_CLI.__file__).resolve()), "<CLI>"),
                (str(Path(sys.executable)), "<PYTHON>"),
                (str(self.workspace.resolve()), "<WORKSPACE>"),
                (str(self.target.resolve()), "<TARGET>"),
                (self.commit, "<COMMIT>")):
            text = text.replace(real, placeholder)
        return text

    def test_the_output_is_v0_38_0s(self) -> None:
        code, payload, err = self.generate_jobs()
        self.assertEqual(code, 0, (payload, err))
        self.assertEqual(json.loads(self.normalized(json.dumps(payload))), GOLDEN_PAYLOAD)
        for row in payload["jobs"]:
            folder = Path(row["jobFolder"])
            self.assertEqual(sorted(_snapshot(folder)), GOLDEN_FILES)
            config = json.loads(self.normalized((folder / "run-config.json").read_text()))
            config["codeBundle"].update(bytes="<BYTES>", sha256="<SHA256>")
            for asset in config["runnerTemplate"]:
                asset["sha256"] = "<SHA256>"
            config["repo"]["ref"] = config["repo"]["ref"].replace(self.branch, "<BRANCH>")
            self.assertEqual(config, GOLDEN_CONFIGS[row["step"]], row["step"])

    def test_every_job_is_what_generate_job_writes(self) -> None:
        code, payload, err = self.generate_jobs()
        self.assertEqual(code, 0, (payload, err))
        for step, service, run, requirements in (
                ("compute", SERVICE, ("--run-notebook", "P/Notebooks/compute.ipynb"),
                 ("numpy==1.26.4", "torch==2.3.0")),
                ("train", HOSTED, ("--run-module", "pkg.mod", "--run-function", "run"),
                 ("numpy==1.26.4",))):
            folder = self.target / "tools" / service / step
            written = _snapshot(folder)
            code, _, err = _cli([
                "generate-job", "--target", str(self.target), "--service", service,
                "--job-name", step, "--product", "P", "--commit", self.commit,
                "--repo-url", REPO_URL, "--repo-ref", self.branch, "--regenerate",
                "--clone-path", "src/pkg", *run, *GLOBAL_SMOKE, "--code-bundle",
                "--carry-path", f"Results/{step}",
                *[arg for pin in requirements for arg in ("--environment-requirement", pin)]])
            self.assertEqual(code, 0, err)
            self.assertEqual(_snapshot(folder), written, step)


class HelpTests(unittest.TestCase):
    def test_generate_jobs_names_every_new_option(self) -> None:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
            REMOTE_CLI.main(["generate-jobs", "--help"])
        for flag in ("--smoke-kwargs-for", "--carry-path-for", "--input-dataset",
                     "--input-dataset-for", "--only", "--skip"):
            self.assertIn(flag, out.getvalue())


if __name__ == "__main__":
    unittest.main()
