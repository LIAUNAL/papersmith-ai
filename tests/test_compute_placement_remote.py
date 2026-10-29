"""Remote honesty (compute-placement S5).

- `generate-job` without the new flag writes byte-identical job files: the
  default GPU stays for compatibility (pinned against
  `fixtures/compute_placement/generate_job_default.json`, recorded before the
  change, with only the pin and the code bundle's digest normalized).
- `--accelerator-kind cpu` writes a CPU-only job on a service that declares
  one, and is refused, naming the service, everywhere else.
- `preflight`'s `accelerator` row says a default GPU is a default, not a
  measured choice, and points to `plan`; `session-fit` reads the job's own
  candidate rows of a schema 2 record.

Run with: python3 -m pytest -q tests/test_compute_placement_remote.py
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
import unittest.mock
from pathlib import Path

from tests.remote_fakes import JOBFOLDER, REMOTE_CLI, SERVICE, PreflightCase

GOLDEN = Path(__file__).resolve().parent / "fixtures" / "compute_placement" / "generate_job_default.json"


def _cli(argv: list[str]) -> tuple[int, dict, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = REMOTE_CLI.main(argv)
    payload = json.loads(out.getvalue()) if out.getvalue().strip() else {}
    return code, payload, err.getvalue()


class _Case(PreflightCase):
    def generate_cli(self, service: str, *extra: str, job: str = "job-a") -> tuple[int, dict, str]:
        argv = ["generate-job", "--target", str(self.target), "--service", service, "--job-name", job,
                "--product", "P", "--repo-url", "https://example.invalid/private.git", "--repo-ref", "main",
                "--clone-path", "src/pkg", "--run-module", "pkg.mod", "--run-function", "run", *extra]
        if service == "kaggle":
            return _cli(argv + ["--code-bundle"])
        with unittest.mock.patch.object(JOBFOLDER, "_verify_commit_reachable", return_value=None):
            return _cli(argv)

    def files(self, payload: dict) -> dict:
        folder = Path(payload["jobFolder"])
        found = {}
        for name in ("run-config.json", "kernel-metadata.json"):
            if (folder / name).is_file():
                text = (folder / name).read_text(encoding="utf-8").replace(self.commit, "<commit>")
                if name == "run-config.json" and "codeBundle" in json.loads(text):
                    bundle = json.loads(text)["codeBundle"]
                    text = text.replace(bundle["sha256"], "<bundle-sha256>").replace(
                        f'"bytes": {bundle["bytes"]}', '"bytes": "<bundle-bytes>"')
                found[name] = text
        return found


def default_job_files(case: _Case) -> dict:
    files = {}
    for service in ("kaggle", "colab"):
        code, payload, err = case.generate_cli(service, job=f"job-{service}")
        case.assertEqual(code, 0, err)
        files[service] = case.files(payload)
    return files


class DefaultJobUnchangedTests(_Case):
    def test_generate_job_without_the_new_flag_writes_the_same_bytes(self) -> None:
        golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
        self.assertEqual(default_job_files(self), golden)


# A test service that, like the real ones, declares a CPU-only session.
from tests.remote_fakes import ADAPTER, _PreflightBackend  # noqa: E402

CPU_SERVICE = "preflight-cpu"


class _CpuCapableBackend(_PreflightBackend):
    def accelerator_request(self, run_config):
        declared = run_config.get("accelerator") or {}
        if declared.get("kind") == "cpu":
            return {"name": "cpu", "architectures": [], "problem": None}
        return dict(self.accelerator)


ADAPTER.register(CPU_SERVICE, _CpuCapableBackend)
ADAPTER.register_metadata(CPU_SERVICE, lambda rc: ("fake-metadata.json", json.dumps({"ok": True})))
ADAPTER.register_default_accelerator(CPU_SERVICE, lambda: ("cuda", ("sm_75",)))
ADAPTER.register_cpu_only(CPU_SERVICE)


class CpuOnlyJobTests(_Case):
    def config(self, payload: dict) -> dict:
        return json.loads((Path(payload["jobFolder"]) / "run-config.json").read_text(encoding="utf-8"))

    def test_kaggle_writes_a_cpu_only_job_that_requests_no_gpu(self) -> None:
        code, payload, err = self.generate_cli("kaggle", "--accelerator-kind", "cpu")
        self.assertEqual(code, 0, err)
        config = self.config(payload)
        self.assertEqual(config["accelerator"], {"kind": "cpu", "architectures": []})
        metadata = json.loads((Path(payload["jobFolder"]) / "kernel-metadata.json").read_text())
        self.assertIs(metadata["enable_gpu"], False)
        self.assertNotIn("machine_shape", metadata)
        kaggle = ADAPTER.resolve("kaggle")
        module = sys.modules[kaggle.__module__]
        # submit() never adds the default card to a template that asks for no GPU.
        self.assertEqual(module.staged_machine_shape(dict(metadata)), metadata)
        self.assertEqual(module.staged_machine_shape({"enable_gpu": True})["machine_shape"], "NvidiaTeslaT4")
        self.assertEqual(object.__new__(kaggle).accelerator_request(config)["name"], "cpu")

    def test_colab_writes_a_cpu_only_job_that_asks_for_no_gpu_variant(self) -> None:
        code, payload, err = self.generate_cli("colab", "--accelerator-kind", "cpu")
        self.assertEqual(code, 0, err)
        config = self.config(payload)
        self.assertEqual(config["accelerator"], {"kind": "cpu", "architectures": []})
        colab = ADAPTER.resolve("colab")
        adapter = object.__new__(colab)
        self.assertIsNone(adapter._accelerator_variant(config["accelerator"]))
        self.assertEqual(adapter.accelerator_request(config)["name"], "cpu")

    def test_a_service_without_a_cpu_only_session_refuses_it_by_name(self) -> None:
        code, _, err = _cli(["generate-job", "--target", str(self.target), "--service", SERVICE,
                             "--job-name", "job-a", "--product", "P",
                             "--repo-url", "https://example.invalid/private.git", "--repo-ref", "main",
                             "--clone-path", "src/pkg", "--run-module", "pkg.mod", "--run-function", "run",
                             "--code-bundle", "--accelerator-kind", "cpu"])
        self.assertNotEqual(code, 0)
        self.assertIn(SERVICE, err)
        self.assertIn("CPU-only", err)

    def test_a_cpu_only_job_declares_no_architecture(self) -> None:
        code, _, err = self.generate_cli("kaggle", "--accelerator-kind", "cpu",
                                         "--accelerator-architecture", "sm_75")
        self.assertNotEqual(code, 0)
        self.assertIn("architecture", err)


class PreflightHonestyTests(_Case):
    def test_a_default_gpu_is_named_a_default_not_a_measured_choice(self) -> None:
        job = self.generate()
        _, payload, _ = self.preflight(job, "--skip-rehearsal")
        row = self.row(payload, "accelerator")
        self.assertEqual(row["status"], "warn")
        self.assertIn("a default, not a measured choice", row["evidence"])
        self.assertIn("plan", row["fix"])
        self.assertIn("--accelerator-kind cpu", row["fix"])

    def test_a_cpu_only_job_says_so(self) -> None:
        job = self.generate(service=CPU_SERVICE, accelerator_kind="cpu")
        _, payload, _ = self.preflight(job, "--skip-rehearsal")
        row = self.row(payload, "accelerator")
        self.assertEqual(row["status"], "pass")
        self.assertIn("CPU-only", row["evidence"])

    def timing(self) -> None:
        def item(candidate: str, device: str, seconds: float) -> dict:
            return {"measuredAt": "2026-10-29T00:00:00Z", "host": f"{CPU_SERVICE}:w1", "candidate": candidate,
                    "device": device, "arm": "a", "unit": "epoch", "secondsPerUnit": seconds,
                    "unitsMeasured": 1}

        path = self.target / "P" / "Results" / "timing.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({
            "schema": 2, "hosts": {},
            "measurements": [item(f"{CPU_SERVICE}:w1/GPU-X", "cuda:GPU-X", 6.0),
                             item(f"{CPU_SERVICE}:w1/cpu", "cpu", 120.0)],
            "scales": {"poc": {"arms": 1, "folds": 1, "seeds": 1, "epochs": 1},
                       "full": {"arms": 2, "folds": 5, "seeds": 1, "epochs": 10}}}), encoding="utf-8")

    def test_session_fit_reads_the_job_s_own_candidate_rows(self) -> None:
        self.timing()
        gpu = self.generate(service=CPU_SERVICE)
        row = self.row(self.preflight(gpu, "--skip-rehearsal")[1], "session-fit")
        self.assertEqual(row["status"], "pass", row)
        self.assertIn(f"{CPU_SERVICE}:w1/GPU-X", row["evidence"])
        cpu = self.generate(service=CPU_SERVICE, accelerator_kind="cpu", job_name="job-cpu")
        row = self.row(self.preflight(cpu, "--skip-rehearsal")[1], "session-fit")
        self.assertEqual(row["status"], "fail", row)
        self.assertIn(f"{CPU_SERVICE}:w1/cpu", row["evidence"])
        named = self.row(self.preflight(cpu, "--skip-rehearsal", "--candidate",
                                        f"{CPU_SERVICE}:w1/GPU-X")[1], "session-fit")
        self.assertEqual(named["status"], "warn", named)
        self.assertIn("CPU-only", named["evidence"])
