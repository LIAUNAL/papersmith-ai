"""remote-parallelism: per-service account limits in `assess` and the
read-only `schedule` verb that places a project's remote steps on services
and their units on that service's accounts (spec S5).

Each test pins one rule; services are named generically except where a
fixture mirrors the operator's own setup.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "remote-parallelism"
CLI_PATH = SKILL / "scripts" / "parallelism_cli.py"
TODAY = "2026-10-27"


def load_cli():
    spec = importlib.util.spec_from_file_location("parallelism_cli_schedule_under_test", CLI_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


CLI = load_cli()


class Run:
    def __init__(self, argv: list[str]) -> None:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            self.code = CLI.run(argv, today=TODAY)
        self.out, self.err = out.getvalue(), err.getvalue()
        self.json = json.loads(self.out) if self.out.strip().startswith("{") else None
        self.error = json.loads(self.err) if self.err.strip().startswith("{") else None


UNIFORM = ["--units", "40", "--unit-minutes", "30", "--owners", "3", "--sessions-per-account", "1",
           "--session-limit-hours", "12", "--quota-hours", "30", "--setup-minutes", "10"]

#: The keys `assess` printed before per-service limits existed.
UNIFORM_KEYS = {"inputs", "thresholds", "serialMinutes", "singleAccountMinutes", "parallelMinutes",
                "speedup", "savedMinutes", "accountsUsed", "recommendedAccounts", "perAccount",
                "quotaOk", "unitsOverSessionLimit", "eligibleOwners", "excludedOwners", "verdict",
                "reasons", "reproducibilityChecklist", "stampFields", "launchAuthorization"}


class Base(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.root = Path(holder.name).resolve()

    def run_cli(self, *argv: str) -> Run:
        return Run(["--root", str(self.root), *argv])

    def refused(self, run: Run, code: str) -> None:
        self.assertEqual(run.code, 2, run.out)
        self.assertEqual(run.error["error"], code, run.err)
        self.assertIn("objective", run.error)


# ------------------------------------------------------------- assess
class PerServiceAssessTests(Base):
    def assess_accounts(self, *accounts: str, units="40", minutes="30", setup="10", extra=()) -> Run:
        argv = ["assess", "--units", units, "--unit-minutes", minutes, "--setup-minutes", setup]
        for account in accounts:
            argv += ["--account", account]
        return self.run_cli(*argv, *extra)

    def test_identical_per_service_limits_reproduce_the_uniform_numbers(self) -> None:
        uniform = self.run_cli("assess", *UNIFORM).json
        accounts = self.assess_accounts("ana:svc:1:12:30", "ben:svc:1:12:30", "cy:svc:1:12:30").json
        for key in ("serialMinutes", "singleAccountMinutes", "parallelMinutes", "speedup",
                    "savedMinutes", "verdict", "quotaOk"):
            self.assertEqual(accounts[key], uniform[key], key)
        self.assertEqual([a["units"] for a in accounts["perAccount"]], [14, 13, 13])
        self.assertEqual([a["owner"] for a in accounts["perAccount"]], ["ana", "ben", "cy"])

    def test_per_account_quota_changes_the_verdict(self) -> None:
        # 40 one-hour units over two accounts: 20 GPU hours each.
        low = self.assess_accounts("ana:svc:1:24:5", "ben:svc:1:24:5", minutes="60", setup="0")
        high = self.assess_accounts("ana:svc:1:24:100", "ben:svc:1:24:100", minutes="60", setup="0")
        self.assertEqual(low.code, 0, low.err)
        self.assertEqual(low.json["verdict"], "single-account")
        self.assertFalse(low.json["quotaOk"])
        self.assertEqual(high.json["verdict"], "parallelize")
        self.assertTrue(high.json["quotaOk"])

    def test_per_account_sessions_change_the_makespan(self) -> None:
        one = self.assess_accounts("ana:svc:1:12:100", "ben:svc:1:12:100").json
        two = self.assess_accounts("ana:svc:2:12:100", "ben:svc:1:12:100").json
        self.assertLess(two["parallelMinutes"], one["parallelMinutes"])
        self.assertEqual(two["perAccount"][0]["sessions"], 2)

    def test_a_short_session_limit_keeps_long_units_off_that_account(self) -> None:
        # 400-minute units fit a 12-hour session, not a 6-hour one.
        run = self.assess_accounts("ana:svc:1:12:100", "ben:svc:1:6:100", units="4", minutes="400")
        self.assertEqual(run.code, 0, run.err)
        self.assertEqual([a["units"] for a in run.json["perAccount"]], [4, 0])

    def test_a_free_colab_account_is_excluded_from_per_service_limits(self) -> None:
        run = self.assess_accounts("ana:colab:1:12:30:pro", "ben:colab:1:12:30:free",
                                   "cy:colab:1:12:30:payg")
        self.assertEqual(run.code, 0, run.err)
        self.assertEqual(run.json["eligibleOwners"], 2)
        self.assertEqual(run.json["excludedOwners"], [{"owner": "ben", "tier": "free"}])
        self.assertTrue(any("running distributed computing workers" in r for r in run.json["reasons"]))

    def test_mixed_services_from_accounts_are_not_mixed(self) -> None:
        run = self.assess_accounts("ana:one:1:12:30", "ben:two:1:12:30")
        self.assertEqual(run.json["verdict"], "do-not-mix")
        filtered = self.assess_accounts("ana:one:1:12:30", "ben:two:1:12:30", "cy:two:1:12:30",
                                        extra=("--service", "two"))
        self.assertEqual([a["owner"] for a in filtered.json["perAccount"]], ["ben", "cy"])

    def test_an_accounts_file_is_read_like_the_flags(self) -> None:
        path = self.root / "accounts.json"
        path.write_text(json.dumps([
            {"owner": "ana", "service": "svc", "sessions": 1, "sessionHours": 12, "quotaHours": 30},
            {"owner": "ben", "service": "svc", "sessions": 1, "sessionHours": 12, "quotaHours": 30},
            {"owner": "cy", "service": "svc", "sessions": 1, "sessionHours": 12, "quotaHours": 30}]),
            encoding="utf-8")
        flags = self.assess_accounts("ana:svc:1:12:30", "ben:svc:1:12:30", "cy:svc:1:12:30").json
        from_file = self.run_cli("assess", "--units", "40", "--unit-minutes", "30",
                                 "--setup-minutes", "10", "--accounts-file", str(path)).json
        self.assertEqual(from_file["perAccount"], flags["perAccount"])
        self.assertEqual(from_file["verdict"], flags["verdict"])

    def test_per_service_limits_refuse_the_uniform_limit_flags(self) -> None:
        run = self.assess_accounts("ana:svc:1:12:30", extra=("--quota-hours", "30"))
        self.refused(run, "bad-argument")
        self.refused(self.assess_accounts("ana:svc:one:12:30"), "accounts-invalid")
        self.refused(self.assess_accounts("ana:colab:1:12:30"), "accounts-invalid")
        self.refused(self.run_cli("assess", "--units", "4", "--unit-minutes", "30",
                                  "--setup-minutes", "0", "--accounts-file",
                                  str(self.root / "none.json")), "accounts-file-missing")

    def test_uniform_flags_keep_their_output_exactly(self) -> None:
        run = self.run_cli("assess", *UNIFORM)
        self.assertEqual(run.code, 0, run.err)
        self.assertEqual(set(run.json), UNIFORM_KEYS)
        self.assertEqual(set(run.json["perAccount"][0]), {"account", "units", "gpuHours", "overQuota"})
        self.assertEqual(run.json["perAccount"][0]["account"], 1)
        self.assertEqual(run.json["inputs"]["sessionsPerAccount"], 1)
        self.assertEqual(run.json["parallelMinutes"], 430)


# ------------------------------------------------------------- schedule
def account(owner, service, sessions, hours, quota, tier=None) -> dict:
    item = {"owner": owner, "service": service, "sessions": sessions, "sessionHours": hours,
            "quotaHours": quota}
    if tier is not None:
        item["tier"] = tier
    return item


def step(step_id, units, minutes, services=None, requires=(), setup=10, **extra) -> dict:
    item = {"id": step_id, "units": units, "unitMinutes": minutes,
            "services": services or sorted(minutes), "requires": list(requires),
            "setupMinutes": setup}
    item.update(extra)
    return item


class ScheduleTests(Base):
    def plan(self, steps, accounts, **extra) -> Path:
        path = self.root / "plan.json"
        path.write_text(json.dumps({"schema": 1, "steps": steps, "accounts": accounts, **extra}),
                        encoding="utf-8")
        return path

    def schedule(self, steps, accounts, *argv, **extra) -> Run:
        return self.run_cli("schedule", "--plan", str(self.plan(steps, accounts, **extra)), *argv)

    def operator_setup(self) -> tuple[list, list]:
        steps = [step("hpo", 25, {"colab": 40, "kaggle": 60}),
                 step("e1", 25, {"colab": 20, "kaggle": 30}, requires=["hpo"]),
                 step("e2", 25, {"colab": 20, "kaggle": 30}, requires=["hpo"]),
                 step("e3", 25, {"colab": 20, "kaggle": 30}, requires=["hpo"])]
        accounts = [account("ana", "colab", 1, 24, None, "pro"),
                    account("ana", "kaggle", 2, 12, 30), account("ben", "kaggle", 2, 12, 30)]
        return steps, accounts

    def test_a_step_starts_only_after_the_steps_it_requires(self) -> None:
        steps, accounts = self.operator_setup()
        run = self.schedule(steps, accounts)
        self.assertEqual(run.code, 0, run.err)
        by_id = {item["id"]: item for item in run.json["steps"]}
        for name in ("e1", "e2", "e3"):
            self.assertGreaterEqual(by_id[name]["startMinutes"], by_id["hpo"]["endMinutes"])
        self.assertFalse(run.json["launchAuthorization"])

    def test_a_campaign_is_never_split_across_services(self) -> None:
        steps, accounts = self.operator_setup()
        run = self.schedule(steps, accounts)
        for item in run.json["steps"]:
            services = {share["service"] for share in item["shares"] if share["units"]}
            self.assertEqual(len(services), 1, item)
            self.assertEqual(item["services"], sorted(services))
        checks = {check["id"]: check for check in run.json["doctrineChecks"]}
        self.assertTrue(checks["one-service-per-campaign"]["held"])

    def test_declared_identical_stamps_allow_one_campaign_on_two_services(self) -> None:
        steps = [step("big", 40, {"one": 30, "two": 30}, stampsIdentical=True)]
        accounts = [account("ana", "one", 1, 24, 100), account("ben", "two", 1, 24, 100)]
        run = self.schedule(steps, accounts)
        self.assertEqual(run.json["steps"][0]["services"], ["one", "two"])
        self.assertTrue(any("verify --shards" in r for r in run.json["reasons"]))

    def test_both_slots_of_a_two_session_account_are_used(self) -> None:
        run = self.schedule([step("s", 4, {"svc": 60}, setup=0)], [account("ana", "svc", 2, 12, 30)])
        self.assertEqual(run.code, 0, run.err)
        share = run.json["steps"][0]["shares"][0]
        self.assertEqual(share["units"], 4)
        self.assertEqual(share["slotsUsed"], 2)
        self.assertEqual(run.json["makespanMinutes"], 120)
        self.assertEqual(run.json["serialMinutes"], 240)

    def test_a_quota_overrun_is_flagged(self) -> None:
        run = self.schedule([step("s", 10, {"svc": 60}, setup=0)], [account("ana", "svc", 1, 24, 5)])
        self.assertEqual(run.code, 0, run.err)
        quota = run.json["quota"][0]
        self.assertEqual(quota["gpuHours"], 10)
        self.assertTrue(quota["overQuota"])
        self.assertFalse(run.json["quotaOk"])
        self.assertTrue(any("quota" in r for r in run.json["reasons"]))

    def test_an_unknown_quota_is_reported_unchecked(self) -> None:
        run = self.schedule([step("s", 2, {"colab": 60})], [account("ana", "colab", 1, 24, None, "pro")])
        self.assertIsNone(run.json["quota"][0]["overQuota"])
        self.assertTrue(any("unknown" in r for r in run.json["reasons"]))

    def test_a_free_colab_owner_is_excluded(self) -> None:
        steps = [step("s", 10, {"colab": 30})]
        run = self.schedule(steps, [account("ana", "colab", 1, 24, 50, "free"),
                                    account("ben", "colab", 1, 24, 50, "pro")])
        self.assertEqual(run.code, 0, run.err)
        self.assertEqual(run.json["excludedAccounts"], [{"account": "colab:ana", "tier": "free"}])
        owners = {share["account"] for share in run.json["steps"][0]["shares"]}
        self.assertEqual(owners, {"colab:ben"})
        only_free = self.schedule(steps, [account("ana", "colab", 1, 24, 50, "free")])
        self.refused(only_free, "no-eligible-account")

    def test_the_output_is_deterministic(self) -> None:
        steps, accounts = self.operator_setup()
        self.assertEqual(self.schedule(steps, accounts).out, self.schedule(steps, accounts).out)

    def test_the_makespan_never_exceeds_the_serial_one(self) -> None:
        steps, accounts = self.operator_setup()
        result = self.schedule(steps, accounts).json
        self.assertLessEqual(result["makespanMinutes"], result["serialMinutes"])
        self.assertGreaterEqual(result["speedup"], 1)
        # Independent steps on different services overlap.
        by_id = {item["id"]: item for item in result["steps"]}
        windows = sorted((by_id[n]["startMinutes"], by_id[n]["endMinutes"]) for n in ("e1", "e2", "e3"))
        self.assertLess(windows[1][0], windows[0][1])

    def test_unit_durations_come_from_a_timing_record_per_service(self) -> None:
        timing = {"schema": 1,
                  "measurements": [{"measuredAt": "2026-10-25T10:00:00Z", "host": "svc:ana",
                                    "device": "cuda:T4", "arm": "a", "unit": "epoch",
                                    "secondsPerUnit": 6.0, "unitsMeasured": 1}],
                  "scales": {"poc": {"arms": 1, "folds": 1, "seeds": 1, "epochs": 1},
                             "full": {"arms": 1, "folds": 5, "seeds": 1, "epochs": 100}}}
        (self.root / "timing.json").write_text(json.dumps(timing), encoding="utf-8")
        item = step("s", 5, {}, services=["svc"], setup=0,
                    timing={"svc": {"path": "timing.json", "host": "svc:ana", "stage": "full"}})
        run = self.schedule([item], [account("ana", "svc", 1, 24, 50)])
        self.assertEqual(run.code, 0, run.err)
        # 6 s x 100 epochs x 5 folds = 3000 s, upper bound +20% = 3600 s over 5 units: 12 min each.
        self.assertEqual(run.json["steps"][0]["unitMinutes"], {"svc": 12})
        other = dict(item, timing={"svc": {"path": "timing.json", "host": "svc:ben", "stage": "full"}})
        self.refused(self.schedule([other], [account("ana", "svc", 1, 24, 50)]), "plan-invalid")

    def test_the_documented_worked_example_matches_the_cli(self) -> None:
        steps = [step("hpo_search", 25, {"colab": 40, "kaggle": 60}, setup={"colab": 8, "kaggle": 10})]
        steps += [step(name, 25, {"colab": 20, "kaggle": 30}, requires=["hpo_search"],
                       setup={"colab": 8, "kaggle": 10}) for name in ("e1_run", "e2_run", "e3_run")]
        accounts = [account("amalvarezme", "colab", 1, 24, "unknown", "pro"),
                    account("amalvarezme", "kaggle", 2, 12, 30), account("teammate", "kaggle", 2, 12, 30)]
        result = self.schedule(steps, accounts).json
        doc = " ".join((SKILL / "SKILL.md").read_text(encoding="utf-8").split())
        self.assertIn("## Planning a project's remote steps", (SKILL / "SKILL.md").read_text(encoding="utf-8"))
        self.assertIn(f"Makespan {result['makespanMinutes']} minutes", doc)
        self.assertIn(f"against {result['serialMinutes']} serial", doc)
        self.assertIn(f"speed-up {result['speedup']}", doc)
        for item in result["steps"]:
            row = (f"| `{item['id']}` | {item['services'][0]} | "
                   f"{item['startMinutes']} → {item['endMinutes']} |")
            self.assertIn(row, doc)

    def test_malformed_plans_are_refused(self) -> None:
        accounts = [account("ana", "svc", 1, 24, 50)]
        self.refused(self.run_cli("schedule"), "missing-input")
        self.refused(self.run_cli("schedule", "--plan", str(self.root / "none.json")), "plan-missing")
        self.refused(self.schedule([step("a", 2, {"svc": 5}, requires=["zz"])], accounts), "plan-invalid")
        self.refused(self.schedule([step("a", 2, {"svc": 5}, requires=["b"]),
                                    step("b", 2, {"svc": 5}, requires=["a"])], accounts), "plan-invalid")
        self.refused(self.schedule([step("a", 2, {"svc": 5}, axis="arm")], accounts), "axis-is-comparison")
        self.refused(self.schedule([step("a", 2, {"svc": 5000})], accounts), "unit-over-session-limit")
        self.refused(self.schedule([step("a", 2, {"svc": 5}, setup=None)], accounts), "missing-input")


if __name__ == "__main__":
    unittest.main()
