"""`parallelism_cli.py plan`: the fastest affordable placement, by measurement.

Over every measured candidate -- local CPU with N processes, a local
accelerator, each account's machine, CPU-only remote -- `plan` packs a stage's
units (one fold x seed pair, every arm on the same machine) onto the
candidate's slots with its own setup, session limits and quota, and keeps the
smallest makespan upper bound. A GPU wins only when it was measured faster;
an unmeasured candidate is listed with what would measure it and is never
extrapolated from another host. When loading dominates an epoch, the plan
advises a cached representation and rewrites nothing.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_compute_placement import ROOT, TODAY, Workspace, dru_like, row, schema1_record, schema2_record  # noqa: E402
from test_timing_probe import PROBE  # noqa: E402

PROBE_PATH = "skills/remote-parallelism/scripts/timing_probe.py"

PAID = ["--account", "ana:colab:1:12:unknown:pro"]
POC = {"poc": {"arms": 2, "folds": 4, "seeds": 2, "epochs": 2},
       "full": {"arms": 2, "folds": 5, "seeds": 3, "epochs": 30}}


def launch_bound() -> dict:
    """Eight local CPU processes at 12 s/epoch each against a T4 at 8 s/epoch:
    per epoch the GPU is faster, but its 420 s setup and its single slot lose."""
    return schema2_record([
        row("local-cpu-1", 69.5, threads=8),
        row("local-cpu-8", 12.0, threads=1, setupSeconds=5.0),
        row("colab:ana/T4", 8.0, setupSeconds=420.0, batchSize=32),
        row("colab:ben/T4", 8.0, setupSeconds=420.0, batchSize=32),
    ], scales=POC)


class PlanTests(Workspace):
    def plan(self, record, *extra) -> dict:
        status, out, err = self.cli("plan", "--timing", self.write(record), *extra)
        self.assertEqual(status, 0, err)
        self.assertFalse(out["launchAuthorization"])
        return out

    def test_a_gpu_measured_faster_wins_when_the_local_cpu_exceeds_twenty_minutes(self) -> None:
        out = self.plan(dru_like(), "--stage", "full", *PAID, "--account", "ben:colab:1:12:unknown:pro")
        full = out["plans"]["full"]
        best = full["recommended"]
        self.assertEqual((best["option"], best["device"]), ("colab:ana/T4", "cuda:Tesla T4"))
        self.assertEqual(best["settings"], {"batchSize": 32, "numWorkers": 2})
        # 15 units of (8.0 + 8.2) / 2 s x 2 arms x 30 epochs = 486 s each, on one session, + 420 s setup.
        self.assertEqual(best["makespanSeconds"]["seconds"], 7710)
        self.assertEqual(best["accounts"], ["colab:ana"])
        lost = {item["option"]: item["reason"] for item in full["lost"]}
        self.assertIn("20 minutes", lost["local-cpu-1"])
        unmeasured = {item["candidate"]: item["measureWith"] for item in full["unmeasured"]}
        self.assertIn("colab:ben", unmeasured)
        self.assertIn("colab:ana/cpu", unmeasured)
        self.assertIn("--accelerator-kind cpu", unmeasured["colab:ana/cpu"])
        self.assertIn("local-mps", unmeasured)
        self.assertIn("timing_probe.py", unmeasured["local-mps"])
        # Ben's account is never planned from Ana's T4 timing.
        self.assertNotIn("colab:ben/T4", {item["option"] for item in full["options"]})

    def test_many_cpu_processes_beat_one_launch_bound_gpu_on_makespan(self) -> None:
        out = self.plan(launch_bound(), "--stage", "poc", *PAID, "--account", "ben:colab:1:12:unknown:pro")
        poc = out["plans"]["poc"]
        best = poc["recommended"]
        self.assertEqual((best["option"], best["device"], best["processes"]), ("local-cpu-8", "cpu", 8))
        # 8 units of 12 s x 2 arms x 2 epochs = 48 s, one per process, + 5 s setup.
        self.assertEqual(best["makespanSeconds"], {"seconds": 53, "low": 42.4, "high": 63.6})
        self.assertEqual(best["acceleratorHours"], 0)
        options = {item["option"]: item for item in poc["options"]}
        # One T4: 8 x 32 s + 420 s; both T4 accounts: 4 x 32 s + 420 s.
        self.assertEqual(options["colab:ana/T4"]["makespanSeconds"]["seconds"], 676)
        split = options["colab/T4 x2"]
        self.assertEqual((split["kind"], split["makespanSeconds"]["seconds"]), ("split", 548))
        self.assertEqual(split["status"], "split-not-worth")
        lost = {item["option"]: item["reason"] for item in poc["lost"]}
        self.assertIn("slower", lost["colab:ana/T4"])
        self.assertIn("speed-up", lost["colab/T4 x2"])
        self.assertEqual(poc["pocBudget"], "within")

    def test_a_gpu_never_wins_a_tie(self) -> None:
        record = schema2_record([row("local-cpu-1", 10.0), row("local-mps", 10.0)], scales=POC)
        best = self.plan(record, "--stage", "poc")["plans"]["poc"]["recommended"]
        self.assertEqual(best["option"], "local-cpu-1")
        self.assertIn("no accelerator was measured faster", best["reason"])

    def test_a_split_over_owners_measured_on_their_own_rows_is_recommended_when_worth_it(self) -> None:
        # The local CPU is measured too: an accelerator split wins only over a measured CPU.
        record = schema2_record([row("local-cpu-1", 69.5),
                                 row("colab:ana/T4", 8.0, setupSeconds=420.0),
                                 row("colab:ben/T4", 9.0, setupSeconds=420.0),
                                 row("colab:cy/T4", 8.0, setupSeconds=420.0)])
        out = self.plan(record, "--stage", "full", *PAID, "--account", "ben:colab:1:12:unknown:pro",
                        "--account", "cy:colab:1:12:unknown:free")
        full = out["plans"]["full"]
        best = full["recommended"]
        self.assertEqual((best["option"], best["kind"]), ("colab/T4 x2", "split"))
        self.assertEqual(best["accounts"], ["colab:ana", "colab:ben"])
        self.assertEqual(sum(item["units"] for item in best["perAccount"]), 15)
        self.assertIn("speed-up", best["reason"])
        self.assertEqual(out["excludedAccounts"], [{"account": "colab:cy", "tier": "free"}])
        lost = {item["option"]: item["reason"] for item in full["lost"]}
        self.assertIn("free", lost["colab:cy/T4"])

    def test_loading_that_dominates_an_epoch_brings_cached_representation_advice(self) -> None:
        record = schema2_record([row("local-cpu-4", 40.0, loadSeconds=30.0, computeSeconds=10.0),
                                 row("local-cpu-1", 60.0, loadSeconds=10.0, computeSeconds=50.0)], scales=POC)
        timing = self.write(record)
        before = sorted(path.name for path in self.root.rglob("*"))
        status, out, err = self.cli("plan", "--timing", timing, "--stage", "poc")
        self.assertEqual(status, 0, err)
        self.assertEqual(sorted(path.name for path in self.root.rglob("*")), before)
        (advice,) = out["representationAdvice"]
        self.assertEqual((advice["candidate"], advice["loadShare"], advice["threshold"]), ("local-cpu-4", 0.75, 0.4))
        self.assertFalse(advice["rewritesData"])
        for form in ("float32", ".npy memmap", "precomputed windows"):
            self.assertIn(form, advice["advice"])
        self.assertEqual(out["plans"]["poc"]["recommended"]["representationAdvice"], advice["advice"])

    def test_measured_cached_rows_are_compared_with_raw(self) -> None:
        record = schema2_record([row("local-cpu-4", 40.0, dataSource="raw", loadSeconds=30.0, computeSeconds=10.0),
                                 row("local-cpu-4", 14.0, dataSource="cached", loadSeconds=4.0,
                                     computeSeconds=10.0)], scales=POC)
        out = self.plan(record, "--stage", "poc")
        self.assertEqual(out["plans"]["poc"]["recommended"]["settings"], {"dataSource": "cached"})
        self.assertEqual(out["representationAdvice"], [])
        self.assertEqual(out["dataSourceComparisons"],
                         [{"candidate": "local-cpu-4", "rawSecondsPerUnit": 40, "cachedSecondsPerUnit": 14}])

    def test_nothing_measured_recommends_nothing(self) -> None:
        record = schema2_record([row("colab:ana/T4", 8.0)])
        out = self.plan(record, "--stage", "full")
        full = out["plans"]["full"]
        self.assertIsNone(full["recommended"])
        lost = {item["option"]: item["reason"] for item in full["lost"]}
        self.assertIn("--account", lost["colab:ana/T4"])
        self.assertIn("local-cpu-1", {item["candidate"] for item in full["unmeasured"]})

    def test_a_schema_1_record_plans_by_host(self) -> None:
        out = self.plan(schema1_record(), "--stage", "poc", *PAID)
        options = {item["option"]: item for item in out["plans"]["poc"]["options"]}
        self.assertEqual(sorted(options), ["colab:ana", "local"])
        # Local: 2 units of 70.25 s x 2 arms x 5 epochs + 12 s setup = 1417 s, over 20 minutes at +20%.
        self.assertEqual(options["local"]["status"], "over-local-limit")
        self.assertEqual(out["plans"]["poc"]["recommended"]["option"], "colab:ana")

    def test_record_writes_the_plan_inside_the_workspace(self) -> None:
        (self.root / "Product").mkdir()
        out = self.plan(launch_bound(), *PAID, "--record", "Product")
        self.assertEqual(out["recorded"], f"Product/.remote-parallelism/plan-{TODAY}.json")
        saved = json.loads((self.root / out["recorded"]).read_text(encoding="utf-8"))
        self.assertEqual(saved["plans"], out["plans"])

    def test_the_documented_worked_example_matches_the_cli(self) -> None:
        poc = self.plan(launch_bound(), "--stage", "poc", *PAID,
                        "--account", "ben:colab:1:12:unknown:pro")["plans"]["poc"]
        options = {item["option"]: item for item in poc["options"]}
        doc = " ".join((ROOT / "skills/remote-parallelism/SKILL.md").read_text(encoding="utf-8").split())
        self.assertIn("## Plan the placement before you run", doc)
        best = poc["recommended"]["makespanSeconds"]
        self.assertIn(f"recommends `{poc['recommended']['option']}`: makespan {best['seconds']} s "
                      f"(upper bound {best['high']} s), against "
                      f"{options['colab:ana/T4']['makespanSeconds']['seconds']} s for one GPU account and "
                      f"{options['colab/T4 x2']['makespanSeconds']['seconds']} s for the two-account split, "
                      f"whose speed-up {options['colab/T4 x2']['speedup']} is below", doc)

    def test_a_gpu_beats_a_measured_cpu_and_says_which_one(self) -> None:
        out = self.plan(dru_like(), "--stage", "full", *PAID)
        full = out["plans"]["full"]
        self.assertEqual(full["status"], "recommended")
        self.assertEqual(full["recommended"]["option"], "colab:ana/T4")
        self.assertEqual(full["measureFirst"], [])
        self.assertNotIn("provisional", full)
        # The only measured CPU is over the local limit, so the reason names it and
        # what it lost on, never "every eligible CPU candidate".
        self.assertEqual(full["reason"], full["recommended"]["reason"])
        self.assertEqual(full["reason"],
                         "colab:ana/T4 has the smallest measured makespan upper bound (9252 s); an accelerator "
                         "wins because it was measured faster than local-cpu-1, over-local-limit: 8.1 s per "
                         "epoch against 70 s, makespan upper bound 9252 s against 75600 s")
        self.assertNotIn("every eligible CPU", json.dumps(out))


    def test_refusals(self) -> None:
        status, _, err = self.cli("plan")
        self.assertEqual((status, err["error"]), (2, "missing-input"))
        status, _, err = self.cli("plan", "--timing", self.write(dru_like()), "--stage", "pilot")
        self.assertEqual((status, err["error"]), (2, "bad-argument"))
        status, _, err = self.cli("plan", "--timing", self.write(dru_like()), "--candidate", "laptop")
        self.assertEqual((status, err["error"]), (2, "bad-argument"))


class GpuIsNeverTheDefaultTests(Workspace):
    """An accelerator is recommended only when it beat a measured CPU candidate.
    Otherwise the plan names no device and asks for the CPU measurement first."""

    def plan(self, record, *extra) -> tuple[dict, str]:
        timing = self.write(record)
        before = (self.root / timing).read_bytes()
        status, out, err = self.cli("plan", "--timing", timing, *extra)
        self.assertEqual((status, err), (0, None))
        self.assertFalse(out["launchAuthorization"])
        self.assertEqual((self.root / timing).read_bytes(), before)
        return out, timing

    def assertNeedsMeasurement(self, stage_plan: dict, provisional: str) -> None:
        self.assertIsNone(stage_plan["recommended"])
        self.assertEqual(stage_plan["status"], "needs-measurement")
        self.assertEqual(stage_plan["provisional"]["option"], provisional)
        self.assertNotEqual(stage_plan["provisional"]["device"], "cpu")
        self.assertNotIn("measured faster than every eligible CPU", json.dumps(stage_plan))
        with self.assertRaises(PROBE.ProbeRefusal):
            PROBE.device_from_plan({"plans": {"stage": stage_plan}}, "stage")

    def test_no_cpu_measured_at_all_recommends_no_accelerator(self) -> None:
        record = schema2_record([row("colab:ana/T4", 8.0, setupSeconds=420.0)])
        out, timing = self.plan(record, "--stage", "full", *PAID)
        full = out["plans"]["full"]
        self.assertNeedsMeasurement(full, "colab:ana/T4")
        self.assertEqual(full["reason"],
                         "no firm recommendation: colab:ana/T4 has the smallest measured makespan upper bound "
                         "(9144 s), but no CPU candidate was measured, so an accelerator is never chosen by "
                         "default; measure local-cpu-1, colab:ana/cpu first, then plan again")
        self.assertEqual(full["provisional"]["reason"], full["reason"])
        self.assertEqual(full["measureFirst"], [
            {"candidate": "local-cpu-1",
             "measureWith": f"run {PROBE_PATH} on the target's interpreter with --candidates local-cpu-1",
             "command": (f"<target>/.venv/bin/python {PROBE_PATH} --path <target>/src --entry "
                         f"<package>.<module>:<function> --arm <arm id> --out {timing} "
                         "--candidates local-cpu-1")},
            {"candidate": "colab:ana/cpu",
             "measureWith": ("a rehearsal on colab:ana that runs the timing probe there (generate-job "
                             "--accelerator-kind cpu, submit --smoke, fetch --smoke) and appends its own row"),
             "command": (f"python {PROBE_PATH} --path <target>/src --entry <package>.<module>:<function> "
                         f"--arm <arm id> --out {timing} --host colab:ana --candidates colab:ana/cpu")},
        ])
        # Every measureFirst row is also listed under unmeasured.
        unmeasured = {item["candidate"] for item in full["unmeasured"]}
        self.assertLessEqual({item["candidate"] for item in full["measureFirst"]}, unmeasured)
        self.assertEqual([item["option"] for item in full["lost"]], [])

    def test_a_faster_cpu_over_the_local_limit_sends_the_remote_cpu_to_be_measured(self) -> None:
        # local-cpu-1 at 6 s/epoch beats the T4's 8 s/epoch but needs 15 x 360 s locally (over 20
        # minutes); the account's CPU-only machine is unmeasured.
        record = schema2_record([row("local-cpu-1", 6.0), row("colab:ana/T4", 8.0, setupSeconds=420.0)])
        out, timing = self.plan(record, "--stage", "full", *PAID)
        full = out["plans"]["full"]
        self.assertNeedsMeasurement(full, "colab:ana/T4")
        self.assertEqual(full["reason"],
                         "no firm recommendation: colab:ana/T4 has the smallest measured makespan upper bound "
                         "(9144 s), but it beat no measured CPU candidate (local-cpu-1, over-local-limit: 8 s "
                         "per epoch against 6 s, makespan upper bound 9144 s against 6480 s), so an accelerator "
                         "is never chosen by default; measure colab:ana/cpu first, then plan again")
        self.assertEqual([item["candidate"] for item in full["measureFirst"]], ["colab:ana/cpu"])
        self.assertIn("--host colab:ana --candidates colab:ana/cpu", full["measureFirst"][0]["command"])
        lost = {item["option"]: item["reason"] for item in full["lost"]}
        self.assertIn("20 minutes", lost["local-cpu-1"])
        self.assertNotIn("colab:ana/T4", lost)

    def test_an_accelerator_that_beat_a_cpu_over_the_limit_on_makespan_is_firm(self) -> None:
        # The CPU is faster per epoch but pays a 1000 s setup: 150 x 6 s + 1000 s locally, over 20
        # minutes, against 150 x 6.5 s on the local accelerator.
        record = schema2_record([row("local-cpu-1", 6.0, setupSeconds=1000.0), row("local-mps", 6.5)],
                                scales={"poc": POC["poc"], "full": {"arms": 1, "folds": 1, "seeds": 1,
                                                                    "epochs": 150}})
        out, _ = self.plan(record, "--stage", "full")
        full = out["plans"]["full"]
        self.assertEqual((full["status"], full["recommended"]["option"]), ("recommended", "local-mps"))
        self.assertEqual(full["measureFirst"], [])
        self.assertNotIn("provisional", full)
        self.assertIn("measured faster than local-cpu-1, over-local-limit: 6.5 s per epoch against 6 s, "
                      "makespan upper bound 1170 s against 2280 s", full["reason"])

    def test_nothing_eligible_is_its_own_status(self) -> None:
        record = schema2_record([row("colab:ana/T4", 8.0)])
        full = self.plan(record, "--stage", "full")[0]["plans"]["full"]
        self.assertEqual((full["status"], full["recommended"], full["measureFirst"]), ("no-eligible", None, []))
        self.assertNotIn("provisional", full)

    def test_poc_budget_reads_unmeasured_without_a_firm_pick(self) -> None:
        record = schema2_record([row("local-mps", 1.0)], scales=POC)
        out, _ = self.plan(record, "--stage", "poc")
        poc = out["plans"]["poc"]
        self.assertNeedsMeasurement(poc, "local-mps")
        self.assertEqual(poc["pocBudget"], "unmeasured")
        self.assertEqual([item["candidate"] for item in poc["measureFirst"]], ["local-cpu-1"])


if __name__ == "__main__":
    unittest.main()
