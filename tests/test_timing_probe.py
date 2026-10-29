"""The timing probe: a bounded sweep that measures candidates and never picks one.

`skills/remote-parallelism/scripts/timing_probe.py` is run by the target's own
interpreter against the target's epoch function. For each candidate (local CPU
with N processes, a local accelerator, a remote machine when it runs there) it
times one epoch per setting of batch size, loader workers, pin memory,
prefetch, threads, dtype and data source, splits each epoch into time spent
waiting on data and time computing, stops a candidate's sweep at its time cap,
and writes schema 2 rows into `<Name>/Results/timing.json` and nowhere else.
It names no device as the default: the device comes from `plan`'s measured
recommendation, or there is no choice.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "remote-parallelism" / "scripts"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "compute_placement"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# Importable by its own name: spawned workers unpickle the probe's epoch timer by module.
sys.path.insert(0, str(SCRIPTS))
PROBE = load("timing_probe", SCRIPTS / "timing_probe.py")
CLI = load("parallelism_cli_probe_test", SCRIPTS / "parallelism_cli.py")
HOST = {"cpuCount": 8, "ramGB": 16.0, "mps": False, "cuda": False}
SCALES = {"poc": {"arms": 2, "folds": 2, "seeds": 1, "epochs": 2},
          "full": {"arms": 2, "folds": 5, "seeds": 3, "epochs": 30}}


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def fake_epoch(clock: Clock, load_per_batch: dict, compute: float = 1.0):
    """Two batches; waiting on data costs `load_per_batch[batchSize]` each."""
    def epoch(settings: dict, wrap) -> None:
        def batches():
            for index in range(2):
                clock.now += load_per_batch[settings["batchSize"]]
                yield index

        for _ in wrap(batches()):
            clock.now += compute
    return epoch


class SweepTests(unittest.TestCase):
    def sweep(self, epoch, clock, **kwargs):
        options = {"arm": "a", "candidates": ["local-cpu-1"], "grid": {"batchSize": [32, 128]},
                   "cap_seconds": 1000, "clock": clock, "info": HOST,
                   "now": lambda: "2026-10-29T10:00:00Z"}
        options.update(kwargs)
        return PROBE.sweep(epoch, **options)

    def test_each_setting_is_one_row_with_load_split_from_compute(self) -> None:
        clock = Clock()
        result = self.sweep(fake_epoch(clock, {32: 4.0, 128: 1.0}), clock)
        self.assertEqual(result["skipped"], [])
        rows = result["rows"]
        self.assertEqual([row["batchSize"] for row in rows], [32, 128])
        first = rows[0]
        self.assertEqual({key: first[key] for key in ("host", "candidate", "device", "arm", "unit",
                                                      "processes", "unitsMeasured")},
                         {"host": "local", "candidate": "local-cpu-1", "device": "cpu", "arm": "a",
                          "unit": "epoch", "processes": 1, "unitsMeasured": 1})
        self.assertEqual((first["secondsPerUnit"], first["loadSeconds"], first["computeSeconds"]),
                         (10.0, 8.0, 2.0))
        self.assertEqual((rows[1]["secondsPerUnit"], rows[1]["loadSeconds"]), (4.0, 2.0))
        self.assertEqual(result["hosts"], {"local": HOST})

    def test_a_candidate_stops_at_its_time_cap_and_says_what_it_skipped(self) -> None:
        clock = Clock()
        result = self.sweep(fake_epoch(clock, {32: 4.0, 64: 2.0, 128: 1.0}), clock, cap_seconds=5,
                            candidates=["local-cpu-1", "local-mps"],
                            info=dict(HOST, mps=True), grid={"batchSize": [32, 64, 128]})
        # The cap is per candidate, and the first setting always runs: one
        # epoch is the smallest measurement there is.
        self.assertEqual([(row["candidate"], row["batchSize"]) for row in result["rows"]],
                         [("local-cpu-1", 32), ("local-mps", 32)])
        skipped = {(item["candidate"], item["settings"].get("batchSize")): item["reason"]
                   for item in result["skipped"]}
        self.assertEqual(sorted(skipped), [("local-cpu-1", 64), ("local-cpu-1", 128),
                                           ("local-mps", 64), ("local-mps", 128)])
        self.assertIn("time cap of 5 s", skipped[("local-cpu-1", 64)])

    def test_an_accelerator_the_machine_lacks_is_skipped_never_run_on_cpu(self) -> None:
        clock = Clock()
        result = self.sweep(fake_epoch(clock, {32: 1.0}), clock, candidates=["local-mps", "local-cpu-1"],
                            grid={"batchSize": [32]})
        self.assertEqual([row["candidate"] for row in result["rows"]], ["local-cpu-1"])
        self.assertEqual(result["skipped"][0]["candidate"], "local-mps")
        self.assertIn("no mps", result["skipped"][0]["reason"])

    def test_cpu_is_always_a_candidate_and_accelerators_only_when_present(self) -> None:
        self.assertEqual(PROBE.local_candidates(HOST), ["local-cpu-1", "local-cpu-4"])
        with_mps = PROBE.local_candidates(dict(HOST, mps=True, cpuCount=2))
        self.assertEqual(with_mps, ["local-cpu-1", "local-mps"])
        info = PROBE.host_info()
        self.assertEqual(sorted(info), ["cpuCount", "cuda", "mps", "ramGB"])
        self.assertIsInstance(info["mps"], bool)
        self.assertIsInstance(info["cuda"], bool)

    def test_a_sub_50_microsecond_epoch_is_recorded_at_the_floor_never_as_zero(self) -> None:
        clock = Clock()

        def tiny(settings: dict, wrap) -> None:
            for _ in wrap(range(1)):
                clock.now += 0.00003

        (row,) = self.sweep(tiny, clock, grid={})["rows"]
        self.assertEqual((row["secondsPerUnit"], row["loadSeconds"], row["computeSeconds"]), (0.0001, 0.0, 0.0))
        # The row is a valid measurement: a positive secondsPerUnit.
        record = {"schema": 2, "hosts": {"local": HOST}, "measurements": [row], "scales": SCALES}
        with tempfile.TemporaryDirectory() as holder:
            path = Path(holder) / "timing.json"
            path.write_text(json.dumps(record), encoding="utf-8")
            self.assertEqual(CLI.load_timing(path, "timing.json")["measurements"][0]["secondsPerUnit"], 0.0001)

    def test_candidates_that_disagree_with_the_host_are_refused_before_anything_runs(self) -> None:
        ran = []
        for host, candidates in (("kaggle:zoe", ["local-cpu-1"]), ("kaggle:zoe", ["kaggle:zoe/T4", "local-mps"]),
                                 ("kaggle:zoe", ["colab:zoe/T4"]), ("local", ["kaggle:zoe/cpu"])):
            with self.subTest(host=host, candidates=candidates):
                with self.assertRaises(PROBE.ProbeRefusal) as caught:
                    self.sweep(lambda settings, wrap: ran.append(settings), Clock(), host=host,
                               candidates=candidates)
                self.assertIn(f"--host {host}", str(caught.exception))
        self.assertEqual(ran, [])

    def test_several_processes_are_timed_concurrently(self) -> None:
        sys.path.insert(0, str(FIXTURES))
        self.addCleanup(sys.path.remove, str(FIXTURES))
        epochs = load("epochs", FIXTURES / "epochs.py")
        result = PROBE.sweep(epochs.sleepy_epoch, arm="a", candidates=["local-cpu-2"],
                             grid={"batchSize": [16]}, cap_seconds=60, info=HOST)
        self.assertEqual(result["skipped"], [])
        (row,) = result["rows"]
        self.assertEqual((row["candidate"], row["processes"], row["threads"]), ("local-cpu-2", 2, 4))
        self.assertGreaterEqual(row["secondsPerUnit"], 0.07)
        self.assertGreater(row["loadSeconds"], 0)
        self.assertGreater(row["computeSeconds"], 0)


class RecordTests(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.root = Path(holder.name).resolve()
        self.results = self.root / "Product" / "Results"
        self.results.mkdir(parents=True)
        self.path = self.results / "timing.json"

    def rows(self) -> dict:
        clock = Clock()
        return PROBE.sweep(fake_epoch(clock, {32: 4.0, 128: 1.0}), arm="a", candidates=["local-cpu-1"],
                           grid={"batchSize": [32, 128]}, cap_seconds=1000, clock=clock, info=HOST)

    def test_the_written_record_is_schema_2_and_estimates_the_fastest_setting(self) -> None:
        result = self.rows()
        PROBE.write_record(self.path, result, scales=SCALES)
        self.assertEqual(sorted(p.name for p in self.results.iterdir()), ["timing.json"])
        data = CLI.load_timing(self.path, "timing.json")
        self.assertEqual(data["schema"], 2)
        self.assertEqual(data["hosts"], {"local": HOST})
        estimate = CLI.candidate_estimate(data["measurements"], data["scales"]["poc"])
        self.assertEqual((estimate["secondsPerUnit"], estimate["settings"]["batchSize"]), (4, 128))

    def test_a_schema_1_record_is_upgraded_and_keeps_its_rows(self) -> None:
        old = {"schema": 1, "scales": SCALES, "measurements": [
            {"measuredAt": "2026-10-25T10:00:00Z", "host": "local", "device": "cpu", "arm": "a",
             "unit": "epoch", "secondsPerUnit": 69.5, "unitsMeasured": 1}]}
        self.path.write_text(json.dumps(old), encoding="utf-8")
        PROBE.write_record(self.path, self.rows())
        data = CLI.load_timing(self.path, "timing.json")
        self.assertEqual(data["schema"], 2)
        self.assertEqual(data["measurements"][0], old["measurements"][0])
        self.assertEqual(len(data["measurements"]), 3)
        self.assertEqual(data["scales"], SCALES)

    def test_it_writes_only_a_results_timing_file_and_never_guesses_scales(self) -> None:
        for wrong in (self.root / "Product" / "timing.json", self.results / "other.json"):
            with self.subTest(wrong.name), self.assertRaises(PROBE.ProbeRefusal):
                PROBE.write_record(wrong, self.rows(), scales=SCALES)
            self.assertFalse(wrong.exists())
        with self.assertRaises(PROBE.ProbeRefusal) as caught:
            PROBE.write_record(self.path, self.rows())
        self.assertIn("scales", str(caught.exception))
        self.assertFalse(self.path.exists())

    def test_the_device_comes_from_the_plan_or_there_is_no_choice(self) -> None:
        for plan in (None, {}, {"plans": {"poc": {"recommended": None}}}):
            with self.subTest(plan=plan), self.assertRaises(PROBE.ProbeRefusal):
                PROBE.device_from_plan(plan, "poc")
        plan = {"plans": {"poc": {"recommended": {"candidate": "local-cpu-4", "device": "cpu"}}}}
        self.assertEqual(PROBE.device_from_plan(plan, "poc"), "cpu")

    def test_the_command_line_runs_the_target_entry_point(self) -> None:
        self.path.write_text(json.dumps({"schema": 1, "scales": SCALES, "measurements": [
            {"measuredAt": "2026-10-25T10:00:00Z", "host": "local", "device": "cpu", "arm": "a",
             "unit": "epoch", "secondsPerUnit": 69.5, "unitsMeasured": 1}]}), encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "timing_probe.py"), "--path", str(FIXTURES),
             "--entry", "epochs:sleepy_epoch", "--arm", "b", "--candidates", "local-cpu-1",
             "--batch-sizes", "8,16", "--cap-seconds", "30", "--out", str(self.path)],
            capture_output=True, text=True, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        summary = json.loads(proc.stdout)
        self.assertEqual(summary["rows"], 2)
        data = CLI.load_timing(self.path, "timing.json")
        self.assertEqual([row.get("batchSize") for row in data["measurements"]], [None, 8, 16])

    def test_the_command_line_refuses_local_candidates_on_a_remote_host_and_writes_nothing(self) -> None:
        self.path.write_text(json.dumps({"schema": 1, "scales": SCALES, "measurements": [
            {"measuredAt": "2026-10-25T10:00:00Z", "host": "local", "device": "cpu", "arm": "a",
             "unit": "epoch", "secondsPerUnit": 69.5, "unitsMeasured": 1}]}), encoding="utf-8")
        before = self.path.read_bytes()
        for extra in (["--candidates", "local-cpu-1,local-cpu-4"], []):
            with self.subTest(extra=extra):
                proc = subprocess.run(
                    [sys.executable, str(SCRIPTS / "timing_probe.py"), "--path", str(FIXTURES),
                     "--entry", "epochs:sleepy_epoch", "--arm", "b", "--host", "kaggle:zoe", *extra,
                     "--out", str(self.path)],
                    capture_output=True, text=True, timeout=120)
                self.assertEqual((proc.returncode, proc.stdout), (2, ""))
                error = json.loads(proc.stderr)
                self.assertEqual(error["error"], "probe-refused")
                self.assertIn("local-cpu-1", error["message"])
                self.assertIn("--host kaggle:zoe", error["message"])
                self.assertEqual(self.path.read_bytes(), before)
                self.assertEqual(sorted(p.name for p in self.results.iterdir()), ["timing.json"])


if __name__ == "__main__":
    unittest.main()
