"""Datasets as declared job inputs (remote-preflight S2), every remote step's
job generated in one call (S3), and the two T1 follow-ups: a callable job's
runner hands over the clone root and commit (F1), and the service driver's
import refusal names the workspace env interpreter (F2).

Every test drives the public CLI (`remote_cli.main([...])`) or the runner
asset's own `invoke()`, against a throwaway git target and the in-process
test backends `tests/test_remote_preflight.py` registers. No test reaches a
network: the reachability probe is patched.

Run with: python3 -m pytest -q tests/test_remote_generate_jobs.py
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from tests.test_remote_preflight import (  # noqa: E402
    ADAPTER,
    JOBFOLDER,
    PLAIN,
    REMOTE_CLI,
    SCRIPTS,
    SERVICE,
    PreflightCase,
    _git,
    _PreflightBackend,
    _unreachable,
)

ASSETS = SCRIPTS.parent / "assets"
HOSTED = "preflight-hosted"


class _HostedBackend(_PreflightBackend):
    """Attaches inputs from one named dataset host, and its image already
    provides one of the target's pinned requirements."""

    INPUT_DATASETS_HOST = "elsewhere"
    PROVIDED_REQUIREMENTS = ("torch",)


ADAPTER.register(HOSTED, _HostedBackend)
ADAPTER.register_metadata(HOSTED, lambda rc: ("fake-metadata.json", json.dumps({"ok": True})))
ADAPTER.register_default_accelerator(HOSTED, lambda: ("cuda", ("sm_75",)))

PREP_SHA = "a" * 64


def _cli(argv: list[str]) -> tuple[int, dict, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = REMOTE_CLI.main(argv)
    payload = json.loads(out.getvalue()) if out.getvalue().strip() else {}
    return code, payload, err.getvalue()


class _Case(PreflightCase):
    def registry(self, *entries: dict) -> None:
        folder = self.workspace / "datasets"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "registry.json").write_text(json.dumps(list(entries)), encoding="utf-8")
        for entry in entries:
            if entry.get("preparation"):
                (folder / entry["slug"]).mkdir(exist_ok=True)
                (folder / entry["slug"] / "splits.json").write_text('{"folds": 5}\n',
                                                                     encoding="utf-8")

    @staticmethod
    def entry(slug: str, *, url: str = "", remote: dict | None = None,
              prepared: bool = True, decision: str = "allowed") -> dict:
        return {
            "slug": slug, "role": "full", "title": slug,
            "source": {"kind": "external", "url": url, "retrieved": "2026-10-28"},
            "license": {"source_name": "CC0", "decision": decision, "host_license": "CC0-1.0"},
            "files": [f"datasets/{slug}/data.csv"], "qc": None, "remote": remote,
            "preparation": ({"manifest": f"datasets/{slug}/PREPARATION.md",
                             "splits": f"datasets/{slug}/splits.json", "version": 2,
                             "sha256": PREP_SHA} if prepared else None),
        }

    def generate_job(self, *extra: str, service: str = SERVICE) -> tuple[int, dict, str]:
        return _cli(["generate-job", "--target", str(self.target), "--service", service,
                     "--job-name", "job-a", "--product", "P",
                     "--repo-url", "https://example.invalid/private.git", "--repo-ref", "main",
                     "--clone-path", "src/pkg", "--run-module", "pkg.mod",
                     "--run-function", "run", "--code-bundle",
                     "--workspace", str(self.workspace), *extra])


# ---------------------------------------------------------------- S2: datasets
class DatasetInputTests(_Case):
    def test_a_public_origin_becomes_an_input_dataset_with_its_preparation_checks(self) -> None:
        self.registry(self.entry(
            "adhd", url="https://www.kaggle.com/datasets/danizo/eeg-dataset-for-adhd"))
        code, payload, err = self.generate_job("--dataset", "adhd")
        self.assertEqual(code, 0, err)
        config = json.loads((Path(payload["jobFolder"]) / "run-config.json").read_text())
        self.assertEqual(config["inputDatasets"], ["danizo/eeg-dataset-for-adhd"])
        check = config["datasetChecks"]["danizo/eeg-dataset-for-adhd"]
        self.assertEqual(check["slug"], "adhd")
        self.assertEqual(check["sha256"], PREP_SHA)
        self.assertEqual(check["file"], "data.csv")
        self.assertEqual(check["preparationVersion"], 2)
        self.assertEqual(len(check["splitsSha256"]), 64)
        self.assertEqual(payload["inputDatasets"], ["danizo/eeg-dataset-for-adhd"])

    def test_a_public_published_remote_wins_over_the_origin(self) -> None:
        self.registry(self.entry(
            "adhd", url="https://www.kaggle.com/datasets/danizo/eeg-dataset-for-adhd",
            remote={"ref": "lab/adhd", "visibility": "public", "version": 1}))
        code, payload, err = self.generate_job("--dataset", "adhd")
        self.assertEqual(code, 0, err)
        config = json.loads((Path(payload["jobFolder"]) / "run-config.json").read_text())
        self.assertEqual(config["inputDatasets"], ["lab/adhd"])
        self.assertEqual(config["datasetChecks"]["lab/adhd"]["source"], "published")

    def test_an_unpublished_source_refuses_naming_publish_with_consent(self) -> None:
        self.registry(self.entry("eeg", url="https://example.invalid/eeg.zip"))
        code, _, err = self.generate_job("--dataset", "eeg")
        self.assertEqual(code, 1)
        self.assertIn("DATASET_NOT_PUBLISHED", err)
        self.assertIn("/datasets publish --slug eeg", err)
        self.assertIn("--consent eeg", err)
        self.assertFalse((self.target / "tools" / SERVICE / "job-a").exists())

    def test_a_private_remote_refuses(self) -> None:
        self.registry(self.entry("eeg", remote={"ref": "lab/eeg", "visibility": "private",
                                                "version": 1}))
        code, _, err = self.generate_job("--dataset", "eeg")
        self.assertEqual(code, 1)
        self.assertIn("DATASET_NOT_PUBLIC", err)
        self.assertIn("lab/eeg", err)

    def test_an_unprepared_dataset_refuses(self) -> None:
        self.registry(self.entry(
            "adhd", url="https://www.kaggle.com/datasets/danizo/eeg-dataset-for-adhd",
            prepared=False))
        code, _, err = self.generate_job("--dataset", "adhd")
        self.assertEqual(code, 1)
        self.assertIn("DATASET_NOT_PREPARED", err)
        self.assertIn("prepare", err)

    def test_an_unknown_slug_refuses(self) -> None:
        self.registry()
        code, _, err = self.generate_job("--dataset", "nope")
        self.assertEqual(code, 1)
        self.assertIn("DATASET_UNKNOWN", err)

    def test_a_host_the_service_cannot_attach_refuses(self) -> None:
        self.registry(self.entry(
            "adhd", url="https://www.kaggle.com/datasets/danizo/eeg-dataset-for-adhd"))
        code, _, err = self.generate_job("--dataset", "adhd", service=HOSTED)
        self.assertEqual(code, 1)
        self.assertIn("DATASET_HOST_NOT_ATTACHABLE", err)

    def test_generation_never_uploads(self) -> None:
        self.registry(self.entry(
            "adhd", url="https://www.kaggle.com/datasets/danizo/eeg-dataset-for-adhd"))
        with unittest.mock.patch("subprocess.run", wraps=subprocess.run) as ran:
            code, _, err = self.generate_job("--dataset", "adhd")
        self.assertEqual(code, 0, err)
        for call in ran.call_args_list:
            argv = call.args[0] if call.args else call.kwargs.get("args")
            self.assertEqual(argv[0], "git", argv)

    def test_without_dataset_generate_job_is_unchanged(self) -> None:
        code, payload, err = self.generate_job()
        self.assertEqual(code, 0, err)
        config = json.loads((Path(payload["jobFolder"]) / "run-config.json").read_text())
        self.assertNotIn("inputDatasets", config)
        self.assertNotIn("datasetChecks", config)
        self.assertNotIn("inputDatasets", payload)

    def test_the_explicit_input_dataset_flag_still_works_beside_dataset(self) -> None:
        self.registry(self.entry(
            "adhd", url="https://www.kaggle.com/datasets/danizo/eeg-dataset-for-adhd"))
        code, payload, err = self.generate_job("--dataset", "adhd",
                                               "--input-dataset", "other/set")
        self.assertEqual(code, 0, err)
        config = json.loads((Path(payload["jobFolder"]) / "run-config.json").read_text())
        self.assertEqual(config["inputDatasets"], ["other/set", "danizo/eeg-dataset-for-adhd"])
        self.assertEqual(set(config["datasetChecks"]), {"danizo/eeg-dataset-for-adhd"})

    def test_the_runner_exports_the_dataset_checks(self) -> None:
        invoke = _load_invoke()
        seen = {}
        config = {"commit": "c" * 40, "run": {"module": "m", "function": "f"},
                  "datasetChecks": {"o/s": {"sha256": PREP_SHA}}}
        module = type(sys)("m")
        module.f = lambda: seen.update(
            checks=os.environ.get("FORGE_DATASET_CHECKS"))
        invoke.invoke(config, import_module=lambda name: module, base_dir=self.root)
        self.assertEqual(json.loads(seen["checks"]), {"o/s": {"sha256": PREP_SHA}})
        self.assertNotIn("FORGE_DATASET_CHECKS", os.environ)


# --------------------------------------------------------------- S3: all jobs
STEPS_SOURCE = '''\
__steps__ = {
    "compute": {
        "module": "pkg.mod", "function": "run", "advances": 1, "reads": [],
        "produces": ["Results/compute", "Notebooks/compute.ipynb"],
        "placement": "remote", "job": "compute", "service": "%(carrier)s",
    },
    "train": {
        "module": "pkg.mod", "function": "run", "advances": 2,
        "reads": ["Results/compute"], "produces": ["Results/train"],
        "placement": "remote", "job": "train", "service": "%(hosted)s",
    },
    "render": {
        "module": "pkg.mod", "function": "run", "advances": 3,
        "produces": ["Notebooks/render.ipynb"], "placement": "local",
    },
}
'''


class GenerateJobsTests(_Case):
    def setUp(self) -> None:
        super().setUp()
        (self.target / "src" / "P").mkdir()
        (self.target / "src" / "P" / "__init__.py").write_text(
            STEPS_SOURCE % {"carrier": SERVICE, "hosted": HOSTED}, encoding="utf-8")
        (self.target / "P" / "Notebooks").mkdir()
        (self.target / "P" / "Notebooks" / "compute.ipynb").write_text(json.dumps({
            "cells": [{"cell_type": "code", "metadata": {}, "execution_count": None,
                       "outputs": [], "source": ["import pkg.mod\n"]}],
            "metadata": {}, "nbformat": 4, "nbformat_minor": 5}), encoding="utf-8")
        (self.target / "requirements.txt").write_text(
            "# pinned\nnumpy==1.26.4\ntorch==2.3.0\n-r other.txt\n", encoding="utf-8")
        _git(self.target, "remote", "add", "origin", "https://example.invalid/private.git")
        _git(self.target, "add", "-A")
        _git(self.target, "commit", "-q", "-m", "declare steps")
        self.commit = _git(self.target, "rev-parse", "HEAD")

    def generate_jobs(self, *extra: str) -> tuple[int, dict, str]:
        return _cli(["generate-jobs", "--target", str(self.target), "--product", "P",
                     "--workspace", str(self.workspace),
                     "--smoke-module", "pkg.mod", "--smoke-function", "smoke_stamps",
                     "--smoke-required-evidence", "evidence.commit", *extra])

    def job_config(self, service: str, job: str) -> dict:
        path = self.target / "tools" / service / job / "run-config.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def test_every_remote_step_gets_a_job_and_local_steps_none(self) -> None:
        code, payload, err = self.generate_jobs()
        self.assertEqual(code, 0, (payload, err))
        rows = {row["step"]: row for row in payload["jobs"]}
        self.assertEqual(set(rows), {"compute", "train"})
        self.assertEqual(rows["compute"]["service"], SERVICE)
        self.assertEqual(rows["train"]["service"], HOSTED)
        for row in rows.values():
            self.assertEqual(row["status"], "generated", row)
        self.assertEqual([item["step"] for item in payload["skipped"]], ["render"])
        self.assertEqual(self.job_config(SERVICE, "compute")["commit"], self.commit)

    def test_an_unreachable_repository_gets_a_code_bundle(self) -> None:
        _, payload, _ = self.generate_jobs()
        row = next(row for row in payload["jobs"] if row["step"] == "compute")
        self.assertTrue(row["codeBundle"])
        self.assertIn("codeBundle", self.job_config(SERVICE, "compute"))

    def test_a_reachable_repository_is_cloned(self) -> None:
        self.probe.side_effect = None
        _, payload, _ = self.generate_jobs()
        row = next(row for row in payload["jobs"] if row["step"] == "compute")
        self.assertFalse(row["codeBundle"])
        self.assertNotIn("codeBundle", self.job_config(SERVICE, "compute"))

    def test_an_unreachable_repository_without_bundles_refuses_that_job_only(self) -> None:
        schedule = self.root / "schedule.json"
        schedule.write_text(json.dumps({"steps": [{"id": "compute", "services": [PLAIN]}],
                                        "makespanMinutes": 10}), encoding="utf-8")
        code, payload, _ = self.generate_jobs("--from-schedule", str(schedule))
        self.assertEqual(code, 1)
        rows = {row["step"]: row for row in payload["jobs"]}
        self.assertEqual(rows["compute"]["status"], "refused")
        self.assertTrue(rows["compute"]["error"])
        self.assertEqual(rows["train"]["status"], "generated")

    def test_requirements_are_the_pins_minus_what_the_service_provides(self) -> None:
        self.generate_jobs()
        carrier = self.job_config(SERVICE, "compute")["environment"]["install"]["requirements"]
        hosted = self.job_config(HOSTED, "train")["environment"]["install"]["requirements"]
        self.assertEqual(carrier, ["numpy==1.26.4", "torch==2.3.0"])
        self.assertEqual(hosted, ["numpy==1.26.4"])

    def test_carry_paths_come_from_produces_without_notebooks(self) -> None:
        self.generate_jobs()
        self.assertEqual(self.job_config(SERVICE, "compute")["carryPaths"], ["Results/compute"])
        self.assertEqual(self.job_config(HOSTED, "train")["carryPaths"], ["Results/train"])

    def test_the_schedule_chooses_the_service(self) -> None:
        self.probe.side_effect = None
        schedule = self.root / "schedule.json"
        schedule.write_text(json.dumps({"steps": [{"id": "compute", "services": [PLAIN]}],
                                        "makespanMinutes": 10}), encoding="utf-8")
        code, payload, err = self.generate_jobs("--from-schedule", str(schedule))
        self.assertEqual(code, 0, (payload, err))
        rows = {row["step"]: row for row in payload["jobs"]}
        self.assertEqual(rows["compute"]["service"], PLAIN)
        self.assertTrue((self.target / "tools" / PLAIN / "compute" / "run-config.json").is_file())
        self.assertFalse((self.target / "tools" / SERVICE / "compute").exists())

    def test_a_schedule_naming_an_undeclared_step_refuses(self) -> None:
        schedule = self.root / "schedule.json"
        schedule.write_text(json.dumps({"steps": [{"id": "ghost", "services": [PLAIN]}],
                                        "makespanMinutes": 10}), encoding="utf-8")
        code, _, err = self.generate_jobs("--from-schedule", str(schedule))
        self.assertEqual(code, 1)
        self.assertIn("ghost", err)

    def test_the_schedule_input_plan_is_refused_with_the_fix(self) -> None:
        plan = self.root / "plan.json"
        plan.write_text(json.dumps({"schema": 1, "steps": [{"id": "compute", "units": 2,
                                                            "services": [PLAIN]}]}),
                        encoding="utf-8")
        code, _, err = self.generate_jobs("--from-schedule", str(plan))
        self.assertEqual(code, 1)
        self.assertIn("schedule --plan", err)

    def test_datasets_are_declared_on_every_job(self) -> None:
        self.registry(self.entry(
            "adhd", url="https://www.kaggle.com/datasets/danizo/eeg-dataset-for-adhd"))
        code, payload, err = self.generate_jobs("--dataset", "adhd")
        # The hosted service attaches another host's inputs only.
        rows = {row["step"]: row for row in payload["jobs"]}
        self.assertEqual(rows["compute"]["inputDatasets"], ["danizo/eeg-dataset-for-adhd"])
        self.assertEqual(rows["train"]["status"], "refused")
        self.assertIn("DATASET_HOST_NOT_ATTACHABLE", rows["train"]["error"])

    def test_the_next_command_is_one_preflight_over_every_job(self) -> None:
        _, payload, _ = self.generate_jobs()
        nxt = payload["next"]
        self.assertIn(" preflight ", nxt)
        self.assertEqual(nxt.count("--entrypoint"), 2)
        for row in payload["jobs"]:
            self.assertIn(str(Path(row["jobFolder"]) / "runner.ipynb"), nxt)

    def test_one_preflight_checks_every_job_it_is_given(self) -> None:
        _, payload, _ = self.generate_jobs()
        entrypoints = [str(Path(row["jobFolder"]) / "runner.ipynb") for row in payload["jobs"]]
        argv = ["preflight", "--target", str(self.target), "--workspace", str(self.workspace),
                "--skip-rehearsal"]
        for entry in entrypoints:
            argv += ["--entrypoint", entry]
        code, report, err = _cli(argv)
        self.assertEqual(len(report["jobs"]), 2, (report, err))
        self.assertEqual({job["jobFolder"] for job in report["jobs"]},
                         {str(Path(e).parent) for e in entrypoints})
        self.assertIn("ok", report["summary"])
        self.assertEqual(code, 0 if report["summary"]["ok"] else 1)

    def test_a_target_declaring_no_remote_step_refuses(self) -> None:
        (self.target / "src" / "P" / "__init__.py").write_text("__steps__ = {}\n",
                                                               encoding="utf-8")
        _git(self.target, "commit", "-qam", "no steps")
        code, _, err = self.generate_jobs()
        self.assertEqual(code, 1)
        self.assertIn("no remote step", err)

    def test_generate_jobs_is_a_top_level_subcommand(self) -> None:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
            REMOTE_CLI.main(["generate-jobs", "--help"])
        for flag in ("--from-schedule", "--dataset", "--product"):
            self.assertIn(flag, out.getvalue())


class GenerateJobsVocabularyTests(unittest.TestCase):
    def test_the_plan_module_names_no_service(self) -> None:
        source = (SCRIPTS / "job_plan.py").read_text(encoding="utf-8").lower()
        for leaked in ("kaggle", "colab", "t4", "a100"):
            self.assertNotIn(leaked, source, leaked)

    def test_the_abc_still_keeps_six_operations(self) -> None:
        self.assertEqual(len(ADAPTER.Adapter.__abstractmethods__), 6)


# ------------------------------------------------------- F1: callable handoff
def _load_invoke():
    name = "remote_generate_jobs_runner_invoke"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ASSETS / "runner_invoke.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class CallableHandoffTests(unittest.TestCase):
    def test_a_callable_job_sees_the_clone_root_and_commit(self) -> None:
        invoke = _load_invoke()
        with tempfile.TemporaryDirectory() as box:
            base = Path(box)
            (base / "clone").mkdir()
            seen = {}
            module = type(sys)("m")
            module.f = lambda: seen.update(root=os.environ.get("FORGE_CLONE_ROOT"),
                                           commit=os.environ.get("FORGE_CLONE_COMMIT"))
            config = {"commit": "d" * 40, "run": {"module": "m", "function": "f"}}
            invoke.invoke(config, import_module=lambda name: module, base_dir=base)
            self.assertEqual(seen["commit"], "d" * 40)
            self.assertEqual(seen["root"], str((base / "clone").resolve()))
            self.assertNotEqual(os.environ.get("FORGE_CLONE_COMMIT"), "d" * 40)

    def test_a_callable_job_without_a_pin_still_runs(self) -> None:
        invoke = _load_invoke()
        module = type(sys)("m")
        module.f = lambda: os.environ.get("FORGE_CLONE_COMMIT")
        result = invoke.invoke({"run": {"module": "m", "function": "f"}},
                               import_module=lambda name: module)
        self.assertIsNone(result)


# ------------------------------------------------ F2: driver import refusal
class DriverImportRefusalTests(unittest.TestCase):
    def test_the_refusal_names_the_workspace_env_interpreter(self) -> None:
        with tempfile.TemporaryDirectory() as box:
            workspace = Path(box)
            adapters = workspace / "skills" / "remote-execution" / "scripts" / "adapters"
            adapters.mkdir(parents=True)
            shutil.copy2(SCRIPTS / "adapters" / "kaggle_driver.py", adapters)
            env_python = workspace / ".micromamba" / "envs" / "papersmith" / "bin" / "python"
            env_python.parent.mkdir(parents=True)
            env_python.write_text("#!/bin/sh\n", encoding="utf-8")
            # `-S`: no site-packages, so the pinned client is not importable.
            ran = subprocess.run([sys.executable, "-S", "-I", str(adapters / "kaggle_driver.py"),
                                  "selftest"], capture_output=True, text=True)
            payload = json.loads(ran.stdout)
            self.assertEqual(ran.returncode, 1)
            self.assertIn("not importable", payload["error"])
            self.assertIn(str(env_python), payload["error"])
            self.assertNotIn("--user", payload["error"])


# ------------------------------------- F3: preflight honors --workspace
class WorkspaceAccountsTests(unittest.TestCase):
    """The account check reads the team registry and credential store of the
    workspace preflight was told to check, not of the checkout the CLI file
    happens to live in."""

    def setUp(self) -> None:
        box = tempfile.TemporaryDirectory()
        self.addCleanup(box.cleanup)
        self.workspace = Path(box.name)
        from tests.test_remote_preflight_adapters import COLAB, FAKE_ACCOUNTS, KAGGLE
        self.kaggle, self.colab = KAGGLE, COLAB
        scripts = self.workspace / "skills" / "kaggle-accounts" / "scripts"
        scripts.mkdir(parents=True)
        self.log = self.workspace / "accounts.log"
        (scripts / "accounts_cli.py").write_text(FAKE_ACCOUNTS.format(log=str(self.log)),
                                                 encoding="utf-8")
        signed = self.workspace / "ana-state"
        (signed / ".config" / "colab-cli").mkdir(parents=True)
        (signed / ".config" / "colab-cli" / "token.json").write_text("{}", encoding="utf-8")
        (self.workspace / ".papersmith").mkdir()
        (self.workspace / ".papersmith" / "team.json").write_text(json.dumps({
            "schema": 1, "members": [{"owner": "ana", "accounts": {
                "colab": {"tier": "pro", "configDir": str(signed)}}}]}), encoding="utf-8")

    def test_the_first_service_reads_the_workspace_accounts(self) -> None:
        result = self.kaggle.KaggleAdapter(workspace=self.workspace).account_check("acct-a")
        self.assertTrue(result["ok"], result)
        self.assertIn("validate", self.log.read_text())

    def test_the_second_service_reads_the_workspace_team(self) -> None:
        result = self.colab.ColabAdapter(workspace=self.workspace).account_check("colab:ana")
        self.assertTrue(result["ok"], result)

    def test_preflight_constructs_the_adapter_for_its_workspace(self) -> None:
        seen = []

        class _Recording(_PreflightBackend):
            def __init__(self, workspace=None):
                seen.append(workspace)

        ADAPTER.register("preflight-recording", _Recording)
        ADAPTER.register_metadata("preflight-recording",
                                  lambda rc: ("fake-metadata.json", json.dumps({"ok": True})))
        case = _Case("run")
        case.setUp()
        try:
            job = case.generate(service="preflight-recording")
            _cli(["preflight", "--target", str(case.target), "--entrypoint",
                  str(job / "runner.ipynb"), "--workspace", str(self.workspace),
                  "--skip-rehearsal"])
        finally:
            case.doCleanups()
        self.assertEqual(seen[-1], self.workspace.resolve())


if __name__ == "__main__":
    unittest.main()
