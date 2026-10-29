"""remote-parallelism and session chains (odd/tasks/session-chains.md S3, S4).

S3 -- quota weeks: `schedule` and `plan` add the wait for the next weekly
quota reset when an account's assigned hours exceed its quota, read from the
account data `assess`/`schedule` already take (`quotaHours`), and report how
many quota weeks the work spans. A unit chained over several sessions stays
on its account, so it waits for that account's reset rather than moving.

S4 -- `plan` costs a resumable chain (`--resumable --checkpoint-minutes M`)
instead of dropping an over-margin candidate as `split-first`; each chained
session pays the setup again.

Services are named generically: the quota is data, never a service's name.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_compute_placement import CLI, Workspace, row, schema2_record  # noqa: E402

WEEK = 7 * 24 * 60


def account(owner, service, sessions, hours, quota) -> dict:
    return {"owner": owner, "service": service, "sessions": sessions, "sessionHours": hours,
            "quotaHours": quota}


def step(step_id, units, minutes, setup=0, **extra) -> dict:
    return {"id": step_id, "units": units, "unitMinutes": {"svc": minutes}, "services": ["svc"],
            "setupMinutes": setup, **extra}


class ScheduleQuotaWeekTests(Workspace):
    def schedule(self, steps, accounts) -> dict:
        (self.root / "plan.json").write_text(json.dumps({"schema": 1, "steps": steps,
                                                         "accounts": accounts}), encoding="utf-8")
        status, out, err = self.cli("schedule", "--plan", "plan.json")
        self.assertEqual(status, 0, err)
        return out

    def test_an_account_over_its_weekly_quota_waits_for_the_reset(self) -> None:
        # Ten one-hour units, one session, a 5-hour weekly quota: five now,
        # five after the reset.
        out = self.schedule([step("s", 10, 60)], [account("ana", "svc", 1, 24, 5)])
        self.assertEqual(out["makespanMinutes"], WEEK + 300)
        self.assertEqual(out["quotaWeeks"], 2)
        (quota,) = out["quota"]
        self.assertEqual(quota["gpuHours"], 10)
        self.assertTrue(quota["overQuota"])
        self.assertEqual(quota["quotaWeeks"], 2)
        self.assertEqual(quota["quotaWaitMinutes"], WEEK - 300)
        self.assertFalse(out["quotaOk"])
        self.assertTrue(any("waits" in r and "quota" in r and "svc:ana" in r for r in out["reasons"]),
                        out["reasons"])

    def test_an_account_with_quota_left_takes_the_work_instead_of_waiting(self) -> None:
        out = self.schedule([step("s", 12, 60)],
                            [account("ana", "svc", 1, 24, 5), account("ben", "svc", 1, 24, 100)])
        units = {share["account"]: share["units"] for share in out["steps"][0]["shares"]}
        self.assertEqual(units, {"svc:ana": 5, "svc:ben": 7})
        self.assertEqual(out["makespanMinutes"], 420)
        self.assertEqual(out["quotaWeeks"], 1)
        self.assertEqual([item["quotaWaitMinutes"] for item in out["quota"]], [0, 0])
        self.assertEqual([item["quotaWeeks"] for item in out["quota"]], [1, 1])
        self.assertTrue(out["quotaOk"])

    def test_a_chained_unit_waits_on_its_own_account(self) -> None:
        # 900 minutes of work, 12-hour sessions (576 usable) with a 10-minute
        # setup: two chained sessions of 576 and 344 minutes. The second does
        # not fit what is left of a 10-hour quota, so it waits for that
        # account's reset; the chain's checkpoints never move to the other.
        out = self.schedule([step("long", 1, 900, setup=10, resumable=True, checkpointMinutes=60)],
                            [account("ana", "svc", 1, 12, 10), account("ben", "svc", 1, 12, 10)])
        (share,) = out["steps"][0]["shares"]
        self.assertEqual((share["account"], share["units"], share["sessions"]), ("svc:ana", 1, 2))
        self.assertEqual(out["makespanMinutes"], WEEK + 344)
        by_account = {item["account"]: item for item in out["quota"]}
        self.assertEqual(by_account["svc:ana"]["quotaWaitMinutes"], WEEK - 576)
        self.assertEqual(by_account["svc:ana"]["quotaWeeks"], 2)
        self.assertEqual(by_account["svc:ben"]["units"], 0)
        self.assertEqual(by_account["svc:ben"]["quotaWeeks"], 0)

    def test_an_unknown_quota_never_waits(self) -> None:
        out = self.schedule([step("s", 10, 60)], [account("ana", "svc", 1, 24, None)])
        self.assertEqual(out["makespanMinutes"], 600)
        (quota,) = out["quota"]
        self.assertIsNone(quota["quotaWeeks"])
        self.assertEqual(quota["quotaWaitMinutes"], 0)
        self.assertEqual(out["quotaWeeks"], 1)


#: One remote candidate on a generic service, two-hour sessions (96 usable
#: minutes = 5760 s): a unit of 60 epochs x 100 s = 6000 s (7200 s at the
#: upper bound) plus a 300 s setup does not fit one session.
LONG_UNIT = {"poc": {"arms": 1, "folds": 1, "seeds": 1, "epochs": 1},
             "full": {"arms": 1, "folds": 1, "seeds": 1, "epochs": 60}}


class PlanChainTests(Workspace):
    def plan(self, record, *extra) -> dict:
        status, out, err = self.cli("plan", "--timing", self.write(record), "--stage", "full", *extra)
        self.assertEqual(status, 0, err)
        return out

    @staticmethod
    def option(out: dict, name: str) -> dict:
        return next(item for item in out["plans"]["full"]["options"] if item["option"] == name)

    def long_unit(self) -> dict:
        return schema2_record([row("svc:ana/T4", 100.0, setupSeconds=300.0)], scales=LONG_UNIT)

    def test_an_over_margin_candidate_is_split_first_without_resumable(self) -> None:
        out = self.plan(self.long_unit(), "--account", "ana:svc:1:2:100")
        option = self.option(out, "svc:ana/T4")
        self.assertEqual(option["status"], "split-first")
        self.assertIn("--resumable", option["reason"])

    def test_a_resumable_candidate_is_costed_as_a_chain(self) -> None:
        out = self.plan(self.long_unit(), "--account", "ana:svc:1:2:100",
                        "--resumable", "--checkpoint-minutes", "10")
        option = self.option(out, "svc:ana/T4")
        self.assertEqual(option["status"], "eligible", option)
        # ceil(7200 / (5760 - 300)) = 2 sessions, each paying the 300 s setup.
        self.assertEqual(option["sessionsPerUnit"], 2)
        self.assertTrue(option["resumable"])
        self.assertEqual(option["checkpointMinutes"], 10)
        self.assertEqual(option["makespanSeconds"]["seconds"], 6000 + 2 * 300)
        self.assertTrue(out["rules"]["resumable"])

    def test_a_checkpoint_longer_than_a_session_s_work_stays_split_first(self) -> None:
        out = self.plan(self.long_unit(), "--account", "ana:svc:1:2:100",
                        "--resumable", "--checkpoint-minutes", "95")
        option = self.option(out, "svc:ana/T4")
        self.assertEqual(option["status"], "split-first")
        self.assertIn("checkpoint", option["reason"])

    def test_resumable_and_checkpoint_minutes_come_together(self) -> None:
        record = self.write(self.long_unit())
        status, _, err = self.cli("plan", "--timing", record, "--resumable")
        self.assertEqual((status, err["error"]), (2, "missing-input"))
        status, _, err = self.cli("plan", "--timing", record, "--checkpoint-minutes", "10")
        self.assertEqual((status, err["error"]), (2, "bad-argument"))
        status, _, err = self.cli("plan", "--timing", record, "--resumable", "--checkpoint-minutes", "0")
        self.assertEqual((status, err["error"]), (2, "bad-argument"))

    def test_an_account_over_its_quota_waits_in_the_plan_too(self) -> None:
        # Five 30-minute units on one session with a 2-hour weekly quota:
        # four now, the fifth after the reset.
        scales = {"poc": LONG_UNIT["poc"], "full": {"arms": 1, "folds": 5, "seeds": 1, "epochs": 30}}
        record = schema2_record([row("svc:ana/T4", 60.0)], scales=scales)
        out = self.plan(record, "--account", "ana:svc:1:12:2")
        option = self.option(out, "svc:ana/T4")
        self.assertEqual(option["status"], "eligible", option)
        self.assertEqual(option["makespanSeconds"]["seconds"], WEEK * 60 + 1800)
        self.assertEqual(option["quotaWeeks"], 2)
        (per,) = option["perAccount"]
        self.assertTrue(per["overQuota"])
        self.assertEqual(per["quotaWeeks"], 2)
        self.assertEqual(per["quotaWaitSeconds"], WEEK * 60 - 4 * 1800)
        self.assertIn("reset", option["quotaNote"])


class QuotaWeekDocTests(unittest.TestCase):
    def test_the_skill_documents_quota_weeks_and_resumable_plans(self) -> None:
        skill = (Path(CLI.__file__).resolve().parents[1] / "SKILL.md").read_text(encoding="utf-8")
        for needle in ("quotaWeeks", "quotaWaitMinutes", "--resumable --checkpoint-minutes",
                       "sessionsPerUnit"):
            self.assertIn(needle, skill)
        self.assertEqual(CLI.QUOTA_WEEK_MINUTES, WEEK)


if __name__ == "__main__":
    unittest.main()
