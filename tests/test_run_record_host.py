"""Run records name the host they ran on (#186).

Every record a run leaves -- the runner's `bootstrap.json` environment, the
kit's `shard.json` stamp and bounded-benchmark summary, and the timing probe's
`Results/timing.json` -- carries a `runtime` block: the host label, the
hardware model (machine, CPU model, core count, GPU model), the installed
library versions and the thread settings. The keys each record already had are
unchanged. `parallelism_cli.py estimate` and `plan`, which pool a candidate's
timing rows, flag (never refuse) a pool whose rows came from more than one host
or under differing thread settings.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "remote-parallelism" / "scripts"
KIT_NB = ROOT / "skills" / "proposal-implementation" / "assets" / "kit" / "nb"
RUNNER = ROOT / "skills" / "remote-execution" / "assets" / "runner_bootstrap.py"

RUNTIME_KEYS = ["hardware", "host", "hostSource", "libraries", "threads"]
THREAD_KEYS = ["MKL_NUM_THREADS", "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "torch"]
HARDWARE_KEYS = ["cpu", "cpuCount", "gpu", "machine"]


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# Shared with the probe's own suite: spawned workers unpickle `timing_probe` by
# module name, so a second load under that name would break them.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_timing_probe import PROBE  # noqa: E402
CLI = load("parallelism_cli_run_record_host", SCRIPTS / "parallelism_cli.py")
BOOTSTRAP = load("runner_bootstrap_run_record_host", RUNNER)
STAMP = load("remote_stamp_run_record_host", KIT_NB / "remote_stamp.py")

LABELLED = {"MVIA_TIMING_HOST": "colab:alice", "OMP_NUM_THREADS": "4",
            "MKL_NUM_THREADS": "2", "OPENBLAS_NUM_THREADS": "1"}
SCALES = {"poc": {"arms": 1, "folds": 1, "seeds": 1, "epochs": 1},
          "full": {"arms": 1, "folds": 2, "seeds": 2, "epochs": 2}}


def fake_torch(*, cuda: bool, threads: int = 3):
    return SimpleNamespace(
        __version__="9.9.9",
        get_num_threads=lambda: threads,
        cuda=SimpleNamespace(is_available=lambda: cuda, get_device_name=lambda i: "FakeGPU",
                             get_device_capability=lambda i=0: (7, 5),
                             get_arch_list=lambda: ["sm_75"]),
    )


class RuntimeShape:
    def assert_runtime(self, runtime: dict, *, host: str, gpu, torch_threads) -> None:
        self.assertEqual(sorted(runtime), RUNTIME_KEYS)
        self.assertEqual(runtime["host"], host)
        self.assertEqual(runtime["hostSource"], "MVIA_TIMING_HOST")
        self.assertEqual(sorted(runtime["hardware"]), HARDWARE_KEYS)
        self.assertEqual(runtime["hardware"]["gpu"], gpu)
        self.assertEqual(runtime["hardware"]["cpuCount"], os.cpu_count())
        self.assertTrue(runtime["hardware"]["machine"])
        self.assertIn("python", runtime["libraries"])
        self.assertEqual(sorted(runtime["threads"]), THREAD_KEYS)
        self.assertEqual(runtime["threads"]["torch"], torch_threads)
        self.assertEqual((runtime["threads"]["OMP_NUM_THREADS"], runtime["threads"]["MKL_NUM_THREADS"],
                          runtime["threads"]["OPENBLAS_NUM_THREADS"]), ("4", "2", "1"))
        text = json.dumps(runtime)
        self.assertNotIn(str(Path.home()), text)


class BootstrapRecordTests(RuntimeShape, unittest.TestCase):
    def test_the_bootstrap_environment_names_host_hardware_libraries_and_threads(self) -> None:
        with mock.patch.dict(os.environ, LABELLED):
            environment = BOOTSTRAP.detect_hardware(import_module=lambda name: fake_torch(cuda=True))
        self.assert_runtime(environment["runtime"], host="colab:alice", gpu="FakeGPU", torch_threads=3)
        self.assertEqual(environment["runtime"]["libraries"]["torch"], "9.9.9")

    def test_the_existing_bootstrap_environment_keys_are_unchanged(self) -> None:
        environment = BOOTSTRAP.detect_hardware(import_module=lambda name: fake_torch(cuda=False))
        self.assertEqual(sorted(set(environment) - {"runtime"}), ["archList", "capability", "device", "torch"])
        self.assertEqual(environment["device"], {"kind": "cpu", "name": "cpu"})
        self.assertEqual(environment["torch"], "9.9.9")
        self.assertIsNone(environment["runtime"]["hardware"]["gpu"])

    def test_without_a_label_the_host_is_the_machine_node_name(self) -> None:
        saved = os.environ.pop("MVIA_TIMING_HOST", None)
        try:
            runtime = BOOTSTRAP.detect_hardware(import_module=lambda name: fake_torch(cuda=False))["runtime"]
        finally:
            if saved is not None:
                os.environ["MVIA_TIMING_HOST"] = saved
        self.assertEqual(runtime["hostSource"], "platform.node")
        self.assertEqual(runtime["host"], __import__("platform").node() or None)


class ShardStampTests(RuntimeShape, unittest.TestCase):
    def test_the_shard_stamp_carries_the_runtime_beside_its_existing_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repository = Path(tmp) / "repo"
            (repository / "src" / "nb").mkdir(parents=True)
            (repository / "src" / "nb" / "method.py").write_text("X = 1\n", encoding="utf-8")
            out = Path(tmp) / "out"
            with mock.patch.dict(os.environ, dict(LABELLED, FORGE_RUN_MODE="smoke",
                                                  FORGE_CLONE_COMMIT="a" * 40)):
                path = STAMP.write_shard({"units": 1}, out, device="cpu", repository=repository)
            shard = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(sorted(shard), ["environment", "evidence", "mode", "runs", "runtime"])
        self.assertEqual(sorted(shard["environment"]), ["device"])
        self.assertEqual(sorted(shard["evidence"]), ["commit", "sourcesDigest"])
        self.assertEqual(shard["runtime"]["host"], "colab:alice")
        self.assertEqual(sorted(shard["runtime"]), RUNTIME_KEYS)
        self.assertEqual(sorted(shard["runtime"]["threads"]), THREAD_KEYS)
        self.assertEqual(shard["runtime"]["threads"]["OMP_NUM_THREADS"], "4")


class BenchmarkSummaryTests(RuntimeShape, unittest.TestCase):
    def test_the_benchmark_environment_carries_the_runtime_beside_its_existing_keys(self) -> None:
        sys.path.insert(0, str(KIT_NB))
        try:
            benchmark = load("benchmark_run_record_host", KIT_NB / "benchmark.py")
        finally:
            sys.path.remove(str(KIT_NB))
        benchmark.refuse_foreign_interpreter = lambda: None
        with mock.patch.dict(os.environ, LABELLED):
            where = benchmark.environment()
        self.assertEqual(sorted(set(where) - {"runtime"}),
                         ["hostedRuntime", "interpreter", "platform", "python", "repository", "selfHosted",
                          "torch"])
        import torch
        self.assert_runtime(where["runtime"], host="colab:alice",
                            gpu=torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
                            torch_threads=torch.get_num_threads())
        self.assertEqual(where["runtime"]["libraries"]["torch"], torch.__version__)


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def epoch_of(clock: Clock, seconds: float):
    def epoch(settings, wrap):
        for _ in wrap([1]):
            pass
        clock.now += seconds
    return epoch


HOST = {"cpuCount": 8, "ramGB": 16.0, "mps": False, "cuda": False}


class TimingProbeRecordTests(unittest.TestCase):
    def setUp(self) -> None:
        self._box = tempfile.TemporaryDirectory()
        self.addCleanup(self._box.cleanup)
        self.path = Path(self._box.name) / "Exp" / "Results" / "timing.json"
        self.path.parent.mkdir(parents=True)

    def sweep(self, label: str, omp: str = "4") -> dict:
        clock = Clock()
        with mock.patch.dict(os.environ, dict(LABELLED, MVIA_TIMING_HOST=label, OMP_NUM_THREADS=omp)):
            return PROBE.sweep(epoch_of(clock, 2.0), arm="a", candidates=["local-cpu-1"], cap_seconds=1000,
                               clock=clock, info=HOST)

    def test_each_row_names_its_host_label_and_thread_settings(self) -> None:
        result = self.sweep("machine-a")
        row = result["rows"][0]
        self.assertEqual(row["hostLabel"], "machine-a")
        self.assertEqual(sorted(row["threadSettings"]), THREAD_KEYS)
        self.assertEqual(row["threadSettings"]["OMP_NUM_THREADS"], "4")
        expected = row["threads"] if "torch" in sys.modules else None
        self.assertEqual(row["threadSettings"]["torch"], expected)
        self.assertEqual(result["hosts"], {"local": HOST})
        self.assertEqual(sorted(result["runtimes"]["machine-a"]), RUNTIME_KEYS)

    def test_the_written_record_keeps_every_runtime_and_loads(self) -> None:
        PROBE.write_record(self.path, self.sweep("machine-a"), scales=SCALES)
        PROBE.write_record(self.path, self.sweep("machine-b"))
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(sorted(data["runtimes"]), ["machine-a", "machine-b"])
        self.assertEqual(sorted(data), ["hosts", "measurements", "runtimes", "scales", "schema"])
        self.assertEqual(CLI.load_timing(self.path, "timing.json")["schema"], 2)

    def cli(self, *argv: str) -> dict:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = CLI.run(["--root", self._box.name, *argv], today="2026-11-16")
        self.assertEqual(code, 0)
        return json.loads(out.getvalue())

    def test_estimate_and_plan_flag_a_pool_that_spans_two_hosts(self) -> None:
        PROBE.write_record(self.path, self.sweep("machine-a"), scales=SCALES)
        PROBE.write_record(self.path, self.sweep("machine-b"))
        for verb in ("estimate", "plan"):
            result = self.cli(verb, "--timing", str(self.path))
            warnings = result["runtimeWarnings"]
            self.assertEqual([(w["candidate"], w["kind"]) for w in warnings], [("local-cpu-1", "cross-host")], verb)
            self.assertEqual(warnings[0]["hosts"], ["machine-a", "machine-b"])
            self.assertIn("more than one host", warnings[0]["message"])

    def test_estimate_flags_a_pool_under_differing_thread_settings(self) -> None:
        PROBE.write_record(self.path, self.sweep("machine-a", omp="4"), scales=SCALES)
        PROBE.write_record(self.path, self.sweep("machine-a", omp="8"))
        result = self.cli("estimate", "--timing", str(self.path))
        self.assertEqual([w["kind"] for w in result["runtimeWarnings"]], ["thread-settings"])

    def test_one_host_one_thread_setting_raises_no_warning(self) -> None:
        PROBE.write_record(self.path, self.sweep("machine-a"), scales=SCALES)
        PROBE.write_record(self.path, self.sweep("machine-a"))
        for verb in ("estimate", "plan"):
            self.assertNotIn("runtimeWarnings", self.cli(verb, "--timing", str(self.path)), verb)

    def test_a_record_without_runtime_fields_loads_and_estimates_as_before(self) -> None:
        record = {"schema": 2, "hosts": {"local": HOST}, "scales": SCALES, "measurements": [
            {"measuredAt": "2026-10-25T10:00:00Z", "host": "local", "candidate": "local-cpu-1", "device": "cpu",
             "arm": "a", "unit": "epoch", "secondsPerUnit": 2.0, "unitsMeasured": 1, "processes": 1}]}
        self.path.write_text(json.dumps(record), encoding="utf-8")
        result = self.cli("estimate", "--timing", str(self.path))
        self.assertNotIn("runtimeWarnings", result)
        self.assertEqual(result["estimates"]["poc"]["local"]["secondsPerUnit"], 2)


if __name__ == "__main__":
    unittest.main()
