"""hyperparameter-search reads the timing probe's schema 2 record.

The timing probe (`skills/remote-parallelism/scripts/timing_probe.py`) appends
its rows to `<Name>/Results/timing.json` and upgrades a schema 1 record to
schema 2 in place, so `hpo_cli.py plan --timing` must read schema 2 or the
search cannot be estimated once the probe has run. On schema 2 the estimate
and the `mixed-devices` refusal are keyed by candidate: one host may hold CPU
and accelerator rows, each estimated from its own rows and never pooled.

Schema 1 is pinned: the digests below are the normalized stdout and stderr of
the CLI over the same records, recorded before schema 2 was read.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_hyperparameter_search_skill import CLI, CLI_PATH, valid_plan  # noqa: E402
from test_timing_probe import PROBE, Clock, fake_epoch  # noqa: E402

SCALES = {"poc": {"arms": 2, "folds": 1, "seeds": 1, "epochs": 1},
          "full": {"arms": 2, "folds": 5, "seeds": 3, "epochs": 10}}
EMPTY = hashlib.sha256(b"").hexdigest()
#: (exit code, sha256 of stdout, sha256 of stderr), the temporary root replaced by <ROOT>.
SCHEMA1_PINS = {
    "estimate": (0, "918c79c1a04a87758e38d4e29715ea3bcb8f26faf0eb90f9c835ef2d7b5cbc19", EMPTY),
    "mixed": (2, EMPTY, "4276f45ff0f035392914e8acf047994d906264dc7bd9811ee9f6e8a09a6b9a95"),
    "badrow": (2, EMPTY, "025d2f3a94c7295f30ea50873d8c90c0198e7dbe30080b48571a163e18db89d6"),
}


def measurement(seconds: float, host: str = "local", device: str = "cpu", arm: str = "proposed",
                **extra) -> dict:
    item = {"measuredAt": "2026-10-25T10:00:00Z", "host": host, "device": device, "arm": arm,
            "unit": "epoch", "secondsPerUnit": seconds, "unitsMeasured": 1}
    item.update(extra)
    return item


def schema2(measurements: list[dict]) -> dict:
    return {"schema": 2, "hosts": {"local": {"cpuCount": 8, "ramGB": 16.0, "mps": True, "cuda": False}},
            "measurements": measurements, "scales": SCALES}


class Schema2Tests(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.root = Path(holder.name).resolve()
        (self.root / "Method" / "hpo").mkdir(parents=True)
        (self.root / "Method" / "Results").mkdir()
        self.plan_path = self.root / "Method" / "hpo" / "plan.json"
        self.plan_path.write_text(json.dumps(valid_plan()), encoding="utf-8")
        self.timing = self.root / "Method" / "Results" / "timing.json"

    def run_plan(self, *extra: str) -> tuple[int, str, str]:
        proc = subprocess.run([sys.executable, str(CLI_PATH), "plan", "--file", str(self.plan_path),
                               "--timing", str(self.timing), *extra],
                              capture_output=True, text=True, timeout=120)
        root = str(self.root)
        return proc.returncode, proc.stdout.replace(root, "<ROOT>"), proc.stderr.replace(root, "<ROOT>")

    def test_a_record_the_probe_upgraded_is_read(self) -> None:
        self.timing.write_text(json.dumps({"schema": 1, "scales": SCALES,
                                           "measurements": [measurement(2.0), measurement(4.0, arm="baseline-a")]}),
                               encoding="utf-8")
        clock = Clock()
        result = PROBE.sweep(fake_epoch(clock, {32: 1.0}), arm="proposed", candidates=["local-cpu-1", "local-mps"],
                             grid={"batchSize": [32]}, cap_seconds=1000, clock=clock,
                             info={"cpuCount": 8, "ramGB": 16.0, "mps": True, "cuda": False},
                             now=lambda: "2026-10-29T10:00:00Z")
        PROBE.write_record(self.timing, result)
        self.assertEqual(json.loads(self.timing.read_text(encoding="utf-8"))["schema"], 2)
        before = self.timing.read_bytes()
        code, out, err = self.run_plan()
        self.assertEqual((code, err), (0, ""))
        estimate = json.loads(out)["estimate"]
        # The upgraded schema 1 rows stay one host-keyed candidate; each probe row is its own.
        self.assertEqual(sorted(estimate), ["local", "local-cpu-1", "local-mps"])
        self.assertEqual((estimate["local"]["seconds"], estimate["local"]["device"]), (6000, "cpu"))
        for name, device in (("local-cpu-1", "cpu"), ("local-mps", "mps")):
            with self.subTest(name):
                # 20 trials x 2 arms x 5 folds x 10 epochs x 4 s (two 1 s loads + two 1 s computes).
                self.assertEqual({key: estimate[name][key] for key in
                                  ("seconds", "low", "high", "secondsPerUnit", "measurements", "device",
                                   "candidate", "host")},
                                 {"seconds": 8000, "low": 6400, "high": 9600, "secondsPerUnit": 4,
                                  "measurements": 1, "device": device, "candidate": name, "host": "local"})
        self.assertEqual(self.timing.read_bytes(), before)

    def test_one_host_with_cpu_and_mps_candidates_is_accepted_and_never_pooled(self) -> None:
        self.timing.write_text(json.dumps(schema2([
            measurement(2.0, candidate="local-cpu-4", processes=4, batchSize=32),
            measurement(3.0, candidate="local-cpu-4", processes=4, batchSize=128),
            measurement(1.0, device="mps", candidate="local-mps", batchSize=32),
            measurement(8.0, host="gpu:alice", device="cuda:T4", candidate="gpu:alice/T4"),
        ])), encoding="utf-8")
        code, out, err = self.run_plan("--host", "gpu:bob")
        self.assertEqual((code, err), (0, ""))
        estimate = json.loads(out)["estimate"]
        self.assertEqual(sorted(estimate), ["gpu:alice/T4", "gpu:bob", "local-cpu-4", "local-mps"])
        # A candidate's sweep is read at its fastest measured setting: settings are never pooled.
        self.assertEqual((estimate["local-cpu-4"]["secondsPerUnit"], estimate["local-cpu-4"]["settings"]),
                         (2, {"batchSize": 32}))
        self.assertEqual(estimate["local-cpu-4"]["seconds"], 4000)
        self.assertEqual((estimate["local-mps"]["seconds"], estimate["local-mps"]["device"]), (2000, "mps"))
        self.assertEqual((estimate["gpu:alice/T4"]["host"], estimate["gpu:alice/T4"]["seconds"]),
                         ("gpu:alice", 16000))
        self.assertEqual(estimate["gpu:bob"], "unmeasured")
        self.assertIn("fastest measured setting", json.loads(out)["range"])

    def test_one_candidate_on_two_devices_is_refused(self) -> None:
        self.timing.write_text(json.dumps(schema2([
            measurement(2.0, candidate="gpu:alice/T4", host="gpu:alice", device="cuda:T4"),
            measurement(2.0, candidate="gpu:alice/T4", host="gpu:alice", device="cuda:L4"),
        ])), encoding="utf-8")
        code, out, err = self.run_plan()
        self.assertEqual((code, out), (2, ""))
        error = json.loads(err)
        self.assertEqual(error["error"], "mixed-devices")
        self.assertEqual(error["message"], "candidate gpu:alice/T4 was timed on cuda:L4, cuda:T4: timing is never "
                                           "pooled across machines; keep one device per candidate")
        self.assertEqual(error["objective"], CLI.OBJECTIVE_FLOW)

    def test_a_malformed_schema_2_record_is_refused_as_invalid(self) -> None:
        self.timing.write_text(json.dumps(schema2([
            measurement(2.0, host="gpu:alice", candidate="local-cpu-1")])), encoding="utf-8")
        code, out, err = self.run_plan()
        self.assertEqual((code, out), (2, ""))
        error = json.loads(err)
        self.assertEqual(error["error"], "timing-invalid")
        self.assertIn("candidate local-cpu-1 runs on local, not on gpu:alice", error["message"])

    def test_schema_1_outputs_are_unchanged(self) -> None:
        records = {
            "estimate": ([measurement(2.0), measurement(4.0, arm="baseline-a"),
                          measurement(8.0, host="gpu:alice", device="cuda:T4")], ["--host", "gpu:bob"]),
            "mixed": ([measurement(2.0), measurement(3.0, device="mps")], []),
            "badrow": ([dict(measurement(2.0), unit="step")], []),
        }
        for name, (measurements, extra) in records.items():
            with self.subTest(name):
                self.timing.write_text(json.dumps({"schema": 1, "measurements": measurements, "scales": SCALES}),
                                       encoding="utf-8")
                code, out, err = self.run_plan(*extra)
                self.assertEqual((code, hashlib.sha256(out.encode()).hexdigest(),
                                  hashlib.sha256(err.encode()).hexdigest()), SCHEMA1_PINS[name], out + err)


if __name__ == "__main__":
    unittest.main()
