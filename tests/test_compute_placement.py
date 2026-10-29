"""Compute placement: candidate-aware timing (schema 2) beside the schema 1
record every existing target already wrote.

Schema 1 is pinned: the same record produces byte-for-byte the `estimate`,
`assess` and `schedule` outputs it produced before schema 2 existed
(`fixtures/compute_placement/schema1_outputs.json`). Schema 2 adds a candidate
per measurement (where and how it ran: `local-cpu-4`, `local-mps`,
`<service>:<owner>/<machine>`), its loader and batch settings, and the split
of each epoch into load and compute time; the `mixed-devices` refusal is keyed
by candidate, so one host may hold CPU and accelerator rows without pooling
them.

The timing numbers are synthetic, shaped after one real case: a method that
takes 69.5 s per epoch on a local CPU and 8.0 s on a remote T4.
"""

from __future__ import annotations

import copy
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI_PATH = ROOT / "skills" / "remote-parallelism" / "scripts" / "parallelism_cli.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "compute_placement"
GOLDEN = FIXTURES / "schema1_outputs.json"
TODAY = "2026-10-29"


def load_cli():
    spec = importlib.util.spec_from_file_location("parallelism_cli_compute_placement", CLI_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


CLI = load_cli()


def run_cli(*argv: str) -> tuple[int, dict | None, dict | None]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = CLI.run(list(argv), today=TODAY)
    parse = lambda text: json.loads(text) if text.strip().startswith("{") else None  # noqa: E731
    return code, parse(out.getvalue()), parse(err.getvalue())


# ------------------------------------------------------------- fixtures
def schema1_record() -> dict:
    """A schema 1 record as today's targets write it: two arms locally, one remote host."""
    return {
        "schema": 1,
        "measurements": [
            {"measuredAt": "2026-10-25T10:00:00Z", "host": "local", "device": "cpu", "arm": "a",
             "unit": "epoch", "secondsPerUnit": 69.5, "unitsMeasured": 1, "setupSeconds": 12.0},
            {"measuredAt": "2026-10-25T10:05:00Z", "host": "local", "device": "cpu", "arm": "b",
             "unit": "epoch", "secondsPerUnit": 71.0, "unitsMeasured": 1},
            {"measuredAt": "2026-10-25T11:00:00Z", "host": "colab:ana", "device": "cuda:Tesla T4",
             "arm": "a", "unit": "epoch", "secondsPerUnit": 8.0, "unitsMeasured": 2,
             "setupSeconds": 420.0},
        ],
        "scales": {"poc": {"arms": 2, "folds": 2, "seeds": 1, "epochs": 5},
                   "full": {"arms": 2, "folds": 5, "seeds": 3, "epochs": 30}},
    }


def row(candidate: str, seconds: float, arm: str = "a", **extra) -> dict:
    """One schema 2 measurement; host and device follow from the candidate."""
    if candidate.startswith("local-"):
        host = "local"
        device = {"local-mps": "mps", "local-cuda": "cuda:RTX 4090"}.get(candidate, "cpu")
    else:
        host, machine = candidate.split("/", 1)
        device = "cpu" if machine == "cpu" else f"cuda:Tesla {machine}"
    item = {"measuredAt": "2026-10-29T10:00:00Z", "host": host, "candidate": candidate, "device": device,
            "arm": arm, "unit": "epoch", "secondsPerUnit": seconds, "unitsMeasured": 1}
    if candidate.startswith("local-cpu-"):
        item["processes"] = int(candidate.rsplit("-", 1)[1])
    item.update(extra)
    return item


LOCAL_HOST = {"cpuCount": 8, "ramGB": 16.0, "mps": True, "cuda": False}


def schema2_record(measurements: list[dict], scales: dict | None = None, hosts: dict | None = None) -> dict:
    return {"schema": 2, "hosts": {"local": dict(LOCAL_HOST)} if hosts is None else hosts,
            "measurements": measurements,
            "scales": scales or {"poc": {"arms": 2, "folds": 4, "seeds": 2, "epochs": 2},
                                 "full": {"arms": 2, "folds": 5, "seeds": 3, "epochs": 30}}}


def dru_like() -> dict:
    """69.5 s/epoch on one local CPU process, 8.0 s/epoch on a remote T4."""
    return schema2_record([
        row("local-cpu-1", 69.5, threads=8, batchSize=32, numWorkers=0),
        row("local-cpu-1", 70.5, arm="b", threads=8, batchSize=32, numWorkers=0),
        row("colab:ana/T4", 8.0, setupSeconds=420.0, batchSize=32, numWorkers=2),
        row("colab:ana/T4", 8.2, arm="b", setupSeconds=420.0, batchSize=32, numWorkers=2),
    ])


class Workspace(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.root = Path(holder.name).resolve()

    def write(self, record, name: str = "Product/Results/timing.json") -> str:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        return name

    def cli(self, *argv: str) -> tuple[int, dict | None, dict | None]:
        return run_cli("--root", str(self.root), *argv)


def schema1_outputs(root: Path) -> dict:
    """`estimate`, `assess` and `schedule` over the schema 1 record, as JSON."""
    path = root / "Product" / "Results" / "timing.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(schema1_record()), encoding="utf-8")
    (root / "plan.json").write_text(json.dumps({
        "schema": 1, "setupMinutes": 7,
        "steps": [{"id": "full", "units": 15, "services": ["colab"],
                   "timing": {"colab": {"path": "Product/Results/timing.json", "host": "colab:ana",
                                        "stage": "full"}}}],
        "accounts": [{"owner": "ana", "service": "colab", "sessions": 1, "sessionHours": 12,
                      "quotaHours": None, "tier": "pro"}]}), encoding="utf-8")
    outputs = {}
    for name, argv in {
        "estimate": ["estimate", "--timing", "Product/Results/timing.json"],
        "estimate-poc-host": ["estimate", "--timing", "Product/Results/timing.json", "--stage", "poc",
                              "--host", "kaggle:ben"],
        "assess": ["assess", "--units", "15", "--unit-minutes", "8", "--setup-minutes", "7",
                   "--account", "ana:colab:1:12:unknown:pro", "--account", "ben:colab:1:12:unknown:pro"],
        "schedule": ["schedule", "--plan", "plan.json"],
    }.items():
        code, out, err = run_cli("--root", str(root), *argv)
        outputs[name] = {"code": code, "out": out, "err": err}
    return outputs


class Schema1PinnedTests(unittest.TestCase):
    """A schema 1 record keeps loading and keeps producing today's outputs."""

    def test_estimate_assess_and_schedule_outputs_are_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as holder:
            outputs = schema1_outputs(Path(holder).resolve())
        golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
        self.assertEqual(sorted(outputs), sorted(golden))
        for name in golden:
            with self.subTest(name):
                self.assertEqual(outputs[name], golden[name])


class Schema2EstimateTests(Workspace):
    def estimate(self, record, *extra) -> tuple[int, dict | None, dict | None]:
        return self.cli("estimate", "--timing", self.write(record), *extra)

    def refused(self, record, code: str = "timing-invalid") -> str:
        status, out, err = self.estimate(record)
        self.assertEqual(status, 2, out)
        self.assertEqual(err["error"], code, err)
        return err["message"]

    def test_each_candidate_is_estimated_from_its_own_rows(self) -> None:
        status, out, err = self.estimate(dru_like())
        self.assertEqual(status, 0, err)
        full = out["candidateEstimates"]["full"]
        self.assertEqual(sorted(full), ["colab:ana/T4", "local-cpu-1"])
        # (69.5 + 70.5) / 2 = 70 s x 30 epochs x 5 folds x 3 seeds x 2 arms.
        self.assertEqual(full["local-cpu-1"]["seconds"], 63000)
        self.assertEqual(full["local-cpu-1"]["device"], "cpu")
        self.assertEqual(full["local-cpu-1"]["processes"], 1)
        self.assertEqual(full["colab:ana/T4"]["device"], "cuda:Tesla T4")
        self.assertEqual(out["estimates"]["full"]["local"]["candidate"], "local-cpu-1")
        self.assertEqual(out["estimates"]["full"]["colab:ana"]["candidate"], "colab:ana/T4")
        self.assertEqual(out["placement"]["full"]["host"], "colab:ana")

    def test_one_host_holds_cpu_and_accelerator_rows_without_pooling_them(self) -> None:
        record = schema2_record([row("local-cpu-1", 69.5), row("local-cpu-4", 30.0), row("local-mps", 20.0)])
        status, out, err = self.estimate(record)
        self.assertEqual(status, 0, err)
        poc = out["candidateEstimates"]["poc"]
        self.assertEqual({name: item["secondsPerUnit"] for name, item in poc.items()},
                         {"local-cpu-1": 69.5, "local-cpu-4": 30, "local-mps": 20})
        self.assertEqual(out["estimates"]["poc"]["local"]["candidate"], "local-mps")
        same = schema2_record([row("colab:ana/T4", 8.0), row("colab:ana/T4", 9.0, device="cuda:Tesla P100")])
        self.assertIn("candidate colab:ana/T4", self.refused(same, "mixed-devices"))

    def test_the_fastest_measured_setting_of_a_candidate_is_the_one_estimated(self) -> None:
        record = schema2_record([
            row("local-cpu-4", 40.0, batchSize=32, numWorkers=0, loadSeconds=30.0, computeSeconds=10.0),
            row("local-cpu-4", 18.0, batchSize=128, numWorkers=4, pinMemory=False, prefetch=2,
                loadSeconds=6.0, computeSeconds=12.0, dtype="float32", dataSource="cached", threads=2),
        ])
        status, out, err = self.estimate(record)
        self.assertEqual(status, 0, err)
        item = out["candidateEstimates"]["poc"]["local-cpu-4"]
        self.assertEqual(item["secondsPerUnit"], 18)
        self.assertEqual(item["settings"], {"threads": 2, "batchSize": 128, "numWorkers": 4,
                                            "pinMemory": False, "prefetch": 2, "dtype": "float32",
                                            "dataSource": "cached"})
        self.assertEqual(item["loadShare"], 0.33)
        self.assertEqual(item["settingsMeasured"], 2)

    def test_a_remote_candidate_is_never_extrapolated_from_another_host(self) -> None:
        status, out, err = self.estimate(dru_like(), "--host", "colab:ben")
        self.assertEqual(status, 0, err)
        self.assertEqual(out["estimates"]["full"]["colab:ben"], "unmeasured")
        self.assertNotIn("colab:ben/T4", out["candidateEstimates"]["full"])

    def test_malformed_schema2_records_are_refused(self) -> None:
        def with_row(**change):
            item = row("local-cpu-4", 30.0)
            item.update(change)
            return schema2_record([item])

        cases = {
            "no hosts": {key: value for key, value in schema2_record([row("local-cpu-1", 9.0)]).items()
                         if key != "hosts"},
            "schema 3": dict(schema2_record([row("local-cpu-1", 9.0)]), schema=3),
            "host info key": schema2_record([row("local-cpu-1", 9.0)], hosts={"local": {"cores": 8}}),
            "host info cpuCount": schema2_record([row("local-cpu-1", 9.0)],
                                                 hosts={"local": dict(LOCAL_HOST, cpuCount=0)}),
            "bad candidate": with_row(candidate="laptop"),
            "candidate on another host": with_row(candidate="colab:ana/T4", device="cuda:T4"),
            "local cpu on mps": with_row(device="mps"),
            "processes disagree": with_row(processes=2),
            "accelerator machine on cpu": schema2_record([row("colab:ana/T4", 8.0, device="cpu")]),
            "cpu machine on cuda": schema2_record([row("colab:ana/cpu", 8.0, device="cuda:T4")]),
            "zero threads": with_row(threads=0),
            "negative workers": with_row(numWorkers=-1),
            "pin memory text": with_row(pinMemory="yes"),
            "bad dtype": with_row(dtype="Float 32"),
            "bad data source": with_row(dataSource="disk"),
            "negative load": with_row(loadSeconds=-1.0),
            "load and compute past the epoch": with_row(loadSeconds=20.0, computeSeconds=20.0),
        }
        for label, record in cases.items():
            with self.subTest(label):
                self.refused(record)
        schema1 = schema1_record()
        schema1["measurements"][0]["candidate"] = "local-cpu-1"
        self.refused(schema1)

    def test_a_schedule_step_names_its_candidate_when_a_host_holds_several(self) -> None:
        record = schema2_record([row("colab:ana/T4", 6.0), row("colab:ana/cpu", 40.0)],
                                scales={"poc": {"arms": 1, "folds": 1, "seeds": 1, "epochs": 1},
                                        "full": {"arms": 1, "folds": 5, "seeds": 1, "epochs": 100}})
        timing = self.write(record)
        accounts = [{"owner": "ana", "service": "colab", "sessions": 1, "sessionHours": 24,
                     "quotaHours": 50, "tier": "pro"}]

        def schedule(spec: dict) -> tuple[int, dict | None, dict | None]:
            (self.root / "plan.json").write_text(json.dumps({"schema": 1, "setupMinutes": 0, "accounts": accounts,
                "steps": [{"id": "s", "units": 5, "services": ["colab"], "timing": {"colab": spec}}]}),
                encoding="utf-8")
            return self.cli("schedule", "--plan", "plan.json")

        base = {"path": timing, "host": "colab:ana", "stage": "full"}
        status, _, err = schedule(base)
        self.assertEqual((status, err["error"]), (2, "plan-invalid"))
        self.assertIn("colab:ana/T4", err["message"])
        status, out, err = schedule(dict(base, candidate="colab:ana/T4"))
        self.assertEqual(status, 0, err)
        # 6 s x 100 epochs x 5 folds = 3000 s, upper bound +20% = 3600 s over 5 units: 12 min each.
        self.assertEqual(out["steps"][0]["unitMinutes"], {"colab": 12})
        status, _, err = schedule(dict(base, candidate="colab:ben/T4"))
        self.assertEqual((status, err["error"]), (2, "plan-invalid"))


if __name__ == "__main__":
    unittest.main()
