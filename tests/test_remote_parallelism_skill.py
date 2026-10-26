"""The `remote-parallelism` skill: whether a proof of concept or an experiment
campaign is worth spreading over several remote GPU accounts, and the
reproducibility checklist a split has to satisfy before any job is generated.

Every verb is driven through `parallelism_cli.run(argv, today=...)`, the same
entry point `main()` uses, with the date injected so a recorded assessment has
a name a test can predict. Nothing here opens a socket or spawns a client: the
skill decides from measured numbers and never places or launches anything.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "remote-parallelism"
CLI_PATH = SKILL / "scripts" / "parallelism_cli.py"
AGENTS = ROOT / ".claude" / "agents"
TODAY = "2026-10-25"


def load_cli():
    spec = importlib.util.spec_from_file_location("parallelism_cli_under_test", CLI_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


CLI = load_cli()


class Run:
    """One CLI invocation: exit code, stdout, stderr, parsed JSON of each."""

    def __init__(self, argv: list[str], today: str = TODAY) -> None:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            self.code = CLI.run(argv, today=today)
        self.out, self.err = out.getvalue(), err.getvalue()
        self.json = json.loads(self.out) if self.out.strip()[:1] in "{[" and self.out.strip() else None
        self.error = json.loads(self.err) if self.err.strip().startswith("{") else None


def assess_argv(units=40, unit_minutes=30, owners=3, sessions=1, limit=12,
                quota=30, setup=10, *extra) -> list[str]:
    return ["assess", "--units", str(units), "--unit-minutes", str(unit_minutes),
            "--owners", str(owners), "--sessions-per-account", str(sessions),
            "--session-limit-hours", str(limit), "--quota-hours", str(quota),
            "--setup-minutes", str(setup), *extra]


class Base(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.root = Path(holder.name).resolve()

    def assess(self, *args, **kwargs) -> Run:
        return Run(["--root", str(self.root), *assess_argv(*args, **kwargs)])


# ------------------------------------------------------------- verdict math
class VerdictTests(Base):
    def test_a_large_campaign_over_three_accounts_parallelizes(self) -> None:
        run = self.assess()
        self.assertEqual(run.code, 0, run.err)
        result = run.json
        # One account, one session: 23 units fit a 720-minute session after a
        # 10-minute setup (10 + 23*30 = 700), so 40 units need two sessions:
        # 700 + (10 + 17*30) = 1220 minutes.
        self.assertEqual(result["serialMinutes"], 1220)
        # Three accounts: 14/13/13 units, the longest 10 + 14*30 = 430.
        self.assertEqual(result["parallelMinutes"], 430)
        self.assertEqual(result["speedup"], round(1220 / 430, 2))
        self.assertEqual(result["savedMinutes"], 790)
        self.assertEqual(result["accountsUsed"], 3)
        self.assertEqual([a["units"] for a in result["perAccount"]], [14, 13, 13])
        self.assertEqual([a["gpuHours"] for a in result["perAccount"]],
                         [round(430 / 60, 2), round(400 / 60, 2), round(400 / 60, 2)])
        self.assertTrue(result["quotaOk"])
        self.assertEqual(result["verdict"], "parallelize")
        self.assertTrue(result["reasons"])

    def test_a_small_saving_stays_on_one_account(self) -> None:
        # 4 units of 5 minutes: 30 minutes on one account, 20 over three.
        # Speed-up 1.5 meets its threshold, but 10 saved minutes do not.
        run = self.assess(units=4, unit_minutes=5)
        self.assertEqual(run.code, 0, run.err)
        self.assertEqual(run.json["serialMinutes"], 30)
        self.assertEqual(run.json["parallelMinutes"], 20)
        self.assertEqual(run.json["verdict"], "single-account")
        self.assertTrue(any("30" in reason for reason in run.json["reasons"]))

    def test_one_account_available_never_parallelizes(self) -> None:
        run = self.assess(owners=1)
        self.assertEqual(run.code, 0, run.err)
        self.assertEqual(run.json["verdict"], "single-account")
        self.assertEqual(run.json["speedup"], 1.0)

    def test_thresholds_are_stated_in_the_output(self) -> None:
        run = self.assess()
        self.assertEqual(run.json["thresholds"],
                         {"minSpeedup": 1.5, "minSavedMinutes": 30,
                          "noAccountOverQuota": True})

    def test_a_unit_longer_than_one_session_must_be_split_first(self) -> None:
        run = self.assess(unit_minutes=800)
        self.assertEqual(run.code, 0, run.err)
        self.assertEqual(run.json["verdict"], "split-first")
        self.assertIn("unitsOverSessionLimit", run.json)
        self.assertTrue(any("axis" in reason for reason in run.json["reasons"]))

    def test_setup_counts_against_the_session_limit(self) -> None:
        # 715 minutes of work fit 720 alone, not with a 10-minute setup.
        run = self.assess(unit_minutes=715, setup=10)
        self.assertEqual(run.json["verdict"], "split-first")

    def test_quota_overflow_refuses_to_parallelize(self) -> None:
        run = self.assess(units=40, unit_minutes=60, owners=2, quota=5, setup=0)
        self.assertEqual(run.code, 0, run.err)
        self.assertFalse(run.json["quotaOk"])
        self.assertEqual(run.json["verdict"], "single-account")
        self.assertTrue(any("quota" in reason for reason in run.json["reasons"]))
        over = [a for a in run.json["perAccount"] if a["overQuota"]]
        self.assertEqual(len(over), 2)

    def test_concurrent_sessions_per_account_are_counted(self) -> None:
        # Two sessions on one account already halve the campaign, so the
        # single-account baseline uses both of them.
        run = self.assess(owners=1, sessions=2)
        self.assertEqual(run.json["singleAccountMinutes"], 610)
        self.assertEqual(run.json["serialMinutes"], 1220)

    def test_the_output_is_deterministic(self) -> None:
        first, second = self.assess(), self.assess()
        self.assertEqual(first.out, second.out)


class UnitsFileTests(Base):
    def write_units(self, units) -> Path:
        path = self.root / "units.json"
        path.write_text(json.dumps(units), encoding="utf-8")
        return path

    def test_seeds_derive_from_the_unit_id_and_not_the_order(self) -> None:
        ids = [f"seed-{i}" for i in range(6)]
        path = self.write_units(ids)
        first = self.assess(6, 30, 3, 1, 12, 30, 10, "--units-file", str(path)).json
        path = self.write_units(list(reversed(ids)))
        second = self.assess(6, 30, 3, 1, 12, 30, 10, "--units-file", str(path)).json
        self.assertEqual(first["unitSeeds"], second["unitSeeds"])
        for unit in ids:
            expected = int(hashlib.sha256(unit.encode("utf-8")).hexdigest()[:8], 16) % (2 ** 31)
            self.assertEqual(first["unitSeeds"][unit], expected)

    def test_per_unit_minutes_name_the_unit_over_the_limit(self) -> None:
        path = self.write_units([{"id": "fold-0", "minutes": 30},
                                 {"id": "fold-1", "minutes": 900}])
        run = Run(["--root", str(self.root), "assess", "--units-file", str(path),
                   "--unit-minutes", "30", "--owners", "2", "--sessions-per-account", "1",
                   "--session-limit-hours", "12", "--quota-hours", "30",
                   "--setup-minutes", "10"])
        self.assertEqual(run.code, 0, run.err)
        self.assertEqual(run.json["verdict"], "split-first")
        self.assertEqual(run.json["unitsOverSessionLimit"], ["fold-1"])

    def test_a_count_that_disagrees_with_the_file_is_refused(self) -> None:
        path = self.write_units(["a", "b"])
        run = self.assess(5, 30, 3, 1, 12, 30, 10, "--units-file", str(path))
        self.assertEqual(run.code, 2)
        self.assertEqual(run.error["error"], "units-mismatch")

    def test_duplicate_unit_ids_are_refused(self) -> None:
        path = self.write_units(["a", "a"])
        run = self.assess(2, 30, 3, 1, 12, 30, 10, "--units-file", str(path))
        self.assertEqual(run.error["error"], "duplicate-unit")

    def test_a_malformed_units_file_is_refused(self) -> None:
        path = self.root / "units.json"
        path.write_text("{not json", encoding="utf-8")
        run = self.assess(2, 30, 3, 1, 12, 30, 10, "--units-file", str(path))
        self.assertEqual(run.error["error"], "units-file-invalid")

    def test_a_missing_units_file_is_refused(self) -> None:
        run = self.assess(2, 30, 3, 1, 12, 30, 10, "--units-file", str(self.root / "no.json"))
        self.assertEqual(run.error["error"], "units-file-missing")


class RefusalTests(Base):
    def test_a_missing_measurement_is_refused_never_guessed(self) -> None:
        run = Run(["--root", str(self.root), "assess", "--units", "4"])
        self.assertEqual(run.code, 2)
        self.assertEqual(run.error["error"], "missing-input")
        self.assertIn("--unit-minutes", run.error["message"])
        self.assertIn("objective", run.error)

    def test_a_non_positive_measurement_is_refused(self) -> None:
        run = self.assess(unit_minutes=0)
        self.assertEqual(run.error["error"], "bad-argument")
        run = self.assess(owners="two")
        self.assertEqual(run.error["error"], "bad-argument")

    def test_splitting_by_arm_is_refused(self) -> None:
        for axis in ("arm", "comparison"):
            run = self.assess(40, 30, 3, 1, 12, 30, 10, "--axis", axis)
            self.assertEqual(run.code, 2)
            self.assertEqual(run.error["error"], "axis-is-comparison")
        ok = self.assess(40, 30, 3, 1, 12, 30, 10, "--axis", "seed")
        self.assertEqual(ok.code, 0, ok.err)
        self.assertEqual(ok.json["inputs"]["axis"], "seed")


# ------------------------------------------------------------- team policy
class TeamPolicyTests(Base):
    """Parallelism counts distinct owners; free Colab never joins a split;
    services do not mix inside one campaign by default."""

    def test_accounts_beyond_one_per_owner_never_add_parallelism(self) -> None:
        run = self.assess(40, 30, 1, 1, 12, 30, 10, "--accounts", "3")
        self.assertEqual(run.code, 0, run.err)
        self.assertEqual(run.json["verdict"], "single-account")
        self.assertEqual(run.json["inputs"]["owners"], 1)
        self.assertEqual(run.json["inputs"]["accounts"], 3)
        self.assertEqual(run.json["accountsUsed"], 1)
        self.assertTrue(any("one per owner" in reason for reason in run.json["reasons"]))
        # Same campaign with three distinct owners does parallelize.
        self.assertEqual(self.assess(40, 30, 3, 1, 12, 30, 10, "--accounts", "3").json["verdict"],
                         "parallelize")

    def test_accounts_without_owners_is_refused(self) -> None:
        run = Run(["--root", str(self.root), "assess", "--units", "40", "--unit-minutes", "30",
                   "--accounts", "3", "--sessions-per-account", "1", "--session-limit-hours", "12",
                   "--quota-hours", "30", "--setup-minutes", "10"])
        self.assertEqual(run.code, 2)
        self.assertEqual(run.error["error"], "missing-input")
        self.assertIn("--owners", run.error["message"])

    def test_fewer_accounts_than_owners_is_refused(self) -> None:
        run = self.assess(40, 30, 3, 1, 12, 30, 10, "--accounts", "2")
        self.assertEqual(run.error["error"], "bad-argument")

    def test_free_colab_owners_are_excluded_from_a_split(self) -> None:
        run = self.assess(40, 30, 3, 1, 12, 30, 10, "--service", "colab", "--tiers", "pro,free,payg")
        self.assertEqual(run.code, 0, run.err)
        self.assertEqual(run.json["inputs"]["service"], ["colab"])
        self.assertEqual(run.json["eligibleOwners"], 2)
        self.assertEqual(run.json["excludedOwners"], [{"owner": 2, "tier": "free"}])
        self.assertEqual(len(run.json["perAccount"]), 2)
        self.assertEqual(run.json["verdict"], "parallelize")
        self.assertTrue(any("running distributed computing workers" in reason
                            and "https://research.google.com/colaboratory/faq.html" in reason
                            for reason in run.json["reasons"]))

    def test_only_free_colab_owners_never_parallelize(self) -> None:
        run = self.assess(40, 30, 3, 1, 12, 30, 10, "--service", "colab", "--tiers", "free,free,free")
        self.assertEqual(run.code, 0, run.err)
        self.assertEqual(run.json["verdict"], "single-account")
        self.assertEqual(run.json["eligibleOwners"], 0)
        self.assertTrue(any("running distributed computing workers" in reason
                            for reason in run.json["reasons"]))

    def test_colab_needs_one_known_tier_per_owner(self) -> None:
        self.assertEqual(self.assess(40, 30, 3, 1, 12, 30, 10, "--service", "colab").error["error"],
                         "missing-input")
        self.assertEqual(self.assess(40, 30, 3, 1, 12, 30, 10, "--service", "colab",
                                     "--tiers", "pro,pro").error["error"], "bad-argument")
        self.assertEqual(self.assess(40, 30, 2, 1, 12, 30, 10, "--service", "colab",
                                     "--tiers", "pro,gold").error["error"], "bad-argument")

    def test_tiers_without_colab_are_refused(self) -> None:
        run = self.assess(40, 30, 2, 1, 12, 30, 10, "--service", "other", "--tiers", "pro,pro")
        self.assertEqual(run.error["error"], "bad-argument")

    def test_a_non_colab_service_keeps_the_one_per_person_rule(self) -> None:
        run = self.assess(40, 30, 3, 1, 12, 30, 10, "--service", "other")
        self.assertEqual(run.code, 0, run.err)
        self.assertEqual(run.json["verdict"], "parallelize")
        self.assertEqual(run.json["eligibleOwners"], 3)

    def test_mixing_services_is_refused_by_default(self) -> None:
        run = self.assess(40, 30, 3, 1, 12, 30, 10, "--service", "other,colab", "--tiers", "pro")
        self.assertEqual(run.code, 0, run.err)
        self.assertEqual(run.json["verdict"], "do-not-mix")
        self.assertTrue(any("identical" in reason for reason in run.json["reasons"]))
        self.assertIsNone(run.json["parallelMinutes"])

    def test_mixing_with_declared_identical_stamps_is_assessed(self) -> None:
        run = self.assess(40, 30, 3, 1, 12, 30, 10, "--service", "other,colab", "--tiers", "free",
                          "--stamps-identical")
        self.assertEqual(run.code, 0, run.err)
        self.assertEqual(run.json["eligibleOwners"], 2)
        self.assertEqual(run.json["verdict"], "parallelize")
        self.assertTrue(any("verify --shards" in reason for reason in run.json["reasons"]))

    def test_the_script_names_no_service_on_the_vocabulary_floor(self) -> None:
        self.assertNotIn("kaggle", CLI_PATH.read_text(encoding="utf-8").lower())


# ------------------------------------------------------------- checklist
class ChecklistTests(Base):
    def test_the_checklist_holds_every_reproducibility_rule(self) -> None:
        run = Run(["checklist"])
        self.assertEqual(run.code, 0, run.err)
        ids = [item["id"] for item in run.json["checklist"]]
        for expected in ("axis-not-arm", "seed-from-unit-id", "pin-commit",
                         "pin-environment", "pin-accelerator", "stamp-environment",
                         "deterministic-flags", "same-dataset-version",
                         "rehearse-each-account", "no-pooled-timing",
                         "one-account-per-person", "one-service-per-campaign",
                         "launch-is-the-operator-s"):
            self.assertIn(expected, ids)
        text = json.dumps(run.json)
        for fragment in ("torch.manual_seed", "torch.use_deterministic_algorithms(True)",
                         "CUBLAS_WORKSPACE_CONFIG=:4096:8", "cudnn.benchmark=False",
                         "machine_shape", "identicalAcrossShards", "never by arm"):
            self.assertIn(fragment, text)

    def test_the_stamp_fields_pin_the_accelerator_and_the_code(self) -> None:
        run = Run(["stamp-fields"])
        self.assertEqual(run.code, 0, run.err)
        fields = run.json["identicalAcrossShards"]
        for field in ("python", "torch", "cuda", "cudnn", "accelerator", "commit",
                      "requirementsDigest", "dataChecksum", "dataPreparationVersion"):
            self.assertIn(field, fields)
        self.assertEqual(fields, list(CLI.STAMP_FIELDS))

    def test_assess_carries_the_same_checklist(self) -> None:
        assessed = self.assess().json
        self.assertEqual(assessed["reproducibilityChecklist"], Run(["checklist"]).json["checklist"])
        self.assertEqual(assessed["stampFields"], list(CLI.STAMP_FIELDS))


# ------------------------------------------------------------- --record
class RecordTests(Base):
    def test_record_writes_inside_the_named_tree(self) -> None:
        tree = self.root / "experiments"
        tree.mkdir()
        run = self.assess(40, 30, 3, 1, 12, 30, 10, "--record", "experiments")
        self.assertEqual(run.code, 0, run.err)
        written = tree / ".remote-parallelism" / f"assessment-{TODAY}.json"
        self.assertTrue(written.is_file())
        saved = json.loads(written.read_text(encoding="utf-8"))
        self.assertEqual(saved["verdict"], "parallelize")
        self.assertEqual(run.json["recorded"], "experiments/.remote-parallelism/"
                                               f"assessment-{TODAY}.json")

    def test_a_second_record_on_the_same_day_never_overwrites(self) -> None:
        (self.root / "experiments").mkdir()
        self.assess(40, 30, 3, 1, 12, 30, 10, "--record", "experiments")
        run = self.assess(4, 5, 3, 1, 12, 30, 10, "--record", "experiments")
        self.assertTrue(run.json["recorded"].endswith(f"assessment-{TODAY}-2.json"))

    def test_record_outside_the_workspace_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as other:
            run = self.assess(40, 30, 3, 1, 12, 30, 10, "--record", other)
        self.assertEqual(run.error["error"], "record-outside-workspace")
        run = self.assess(40, 30, 3, 1, 12, 30, 10, "--record", "../")
        self.assertEqual(run.error["error"], "record-outside-workspace")

    def test_a_symlink_escape_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as other:
            os.symlink(other, self.root / "escape")
            run = self.assess(40, 30, 3, 1, 12, 30, 10, "--record", "escape")
            self.assertEqual(run.error["error"], "record-outside-workspace")
            self.assertFalse(any(Path(other).iterdir()))

    def test_a_symlinked_record_folder_is_refused(self) -> None:
        tree = self.root / "experiments"
        tree.mkdir()
        with tempfile.TemporaryDirectory() as other:
            os.symlink(other, tree / ".remote-parallelism")
            run = self.assess(40, 30, 3, 1, 12, 30, 10, "--record", "experiments")
            self.assertEqual(run.error["error"], "record-outside-workspace")

    def test_a_missing_tree_is_refused(self) -> None:
        run = self.assess(40, 30, 3, 1, 12, 30, 10, "--record", "nowhere")
        self.assertEqual(run.error["error"], "record-missing")


class MainTests(unittest.TestCase):
    def test_the_script_runs_as_a_process(self) -> None:
        proc = subprocess.run([sys.executable, str(CLI_PATH), *assess_argv()],
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["verdict"], "parallelize")

    def test_a_refusal_exits_two_with_json_on_stderr(self) -> None:
        proc = subprocess.run([sys.executable, str(CLI_PATH), "assess"],
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(json.loads(proc.stderr)["error"], "missing-input")


# ------------------------------------------------------------- estimate
def timing_record(**overrides) -> dict:
    """A timing probe's record: two arms measured locally, one on a remote host."""
    record = {
        "schema": 1,
        "measurements": [
            {"measuredAt": "2026-10-25T10:00:00Z", "host": "local", "device": "cpu",
             "arm": "a", "unit": "epoch", "secondsPerUnit": 10.0, "unitsMeasured": 1,
             "setupSeconds": 30.0},
            {"measuredAt": "2026-10-25T10:05:00+00:00", "host": "local", "device": "cpu",
             "arm": "a", "unit": "epoch", "secondsPerUnit": 14.0, "unitsMeasured": 1},
            {"measuredAt": "2026-10-25T10:10:00", "host": "local", "device": "cpu",
             "arm": "b", "unit": "epoch", "secondsPerUnit": 20.0, "unitsMeasured": 1},
            {"measuredAt": "2026-10-25T11:00:00Z", "host": "svc:alice", "device": "cuda:A100",
             "arm": "a", "unit": "epoch", "secondsPerUnit": 2.0, "unitsMeasured": 3},
        ],
        "scales": {"poc": {"arms": 2, "folds": 2, "seeds": 1, "epochs": 5},
                   "full": {"arms": 2, "folds": 5, "seeds": 3, "epochs": 50}},
    }
    record.update(overrides)
    return record


class EstimateTests(Base):
    def write(self, record, name: str = "timing.json") -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record) if not isinstance(record, str) else record, encoding="utf-8")
        return path

    def estimate(self, *extra, record=None) -> Run:
        path = self.write(timing_record() if record is None else record)
        return Run(["--root", str(self.root), "estimate", "--timing", str(path), *extra])

    def refused(self, run: Run, code: str) -> None:
        self.assertEqual(run.code, 2, run.out)
        self.assertEqual(run.error["error"], code, run.err)
        self.assertIn("objective", run.error)

    def test_the_local_estimate_follows_the_one_formula(self) -> None:
        run = self.estimate()
        self.assertEqual(run.code, 0, run.err)
        poc = run.json["estimates"]["poc"]["local"]
        # mean of per-arm means: a -> (10 + 14) / 2 = 12, b -> 20, so 16 s/epoch;
        # 16 x 5 epochs x 2 folds x 1 seed x 2 arms = 320, plus setup 30 x 2 folds x 1 seed = 60.
        self.assertEqual(poc["seconds"], 380)
        self.assertEqual(poc["low"], 304)
        self.assertEqual(poc["high"], 456)
        self.assertEqual(poc["measurements"], 3)
        self.assertEqual(poc["device"], "cpu")
        self.assertEqual(poc["perArm"], {"a": 12, "b": 20})
        self.assertIn("±20%, single-probe extrapolation", poc["formula"])
        full = run.json["estimates"]["full"]["local"]
        # 16 x 50 x 5 x 3 x 2 = 24000, plus 30 x 5 x 3 = 450.
        self.assertEqual((full["seconds"], full["low"], full["high"]), (24450, 19560, 29340))
        self.assertIs(run.json["launchAuthorization"], False)

    def test_the_placement_rules_are_stated(self) -> None:
        run = self.estimate()
        self.assertEqual(run.json["placementRules"],
                         {"localLimitSeconds": 1200, "pocBudgetSeconds": 18000, "bound": "high"})

    def test_a_stage_within_twenty_minutes_locally_stays_local(self) -> None:
        placement = self.estimate().json["placement"]["poc"]
        # local high 456 s <= 1200 s
        self.assertEqual((placement["where"], placement["host"]), ("local", "local"))
        self.assertEqual(placement["pocBudget"], "within")

    def test_a_stage_over_twenty_minutes_locally_goes_to_the_fastest_measured_cloud_host(self) -> None:
        placement = self.estimate().json["placement"]["full"]
        # local high 29340 s > 1200 s; svc:alice high 3600 s
        self.assertEqual((placement["where"], placement["host"]), ("cloud", "svc:alice"))
        self.assertIn("20 minutes", placement["reason"])
        self.assertNotIn("pocBudget", placement)

    def test_over_twenty_minutes_with_no_cloud_measurement_asks_for_a_cloud_probe(self) -> None:
        record = timing_record()
        record["measurements"] = [m for m in record["measurements"] if m["host"] == "local"]
        record["scales"]["poc"]["epochs"] = 50
        placement = self.estimate(record=record).json["placement"]["poc"]
        # local high 16 x 50 x 2 x 1 x 2 = 3200 + 60 = 3260 s x 1.2 > 1200 s
        self.assertEqual((placement["where"], placement["host"]), ("cloud", None))
        self.assertEqual(placement["pocBudget"], "unmeasured")
        self.assertIn("timing probe on a cloud host", placement["reason"])

    def test_a_proof_of_concept_over_five_hours_on_its_host_exceeds_the_budget(self) -> None:
        record = timing_record()
        record["scales"]["poc"]["epochs"] = 2000
        run = self.estimate(record=record)
        self.assertEqual(run.code, 0, run.err)
        placement = run.json["placement"]["poc"]
        # svc:alice: 2 x 2000 x 2 x 1 x 2 = 16000 s, high 19200 s > 18000 s
        self.assertEqual((placement["where"], placement["host"]), ("cloud", "svc:alice"))
        self.assertEqual(placement["pocBudget"], "exceeds")
        self.assertIn("reduce", placement["reason"])

    def test_local_unmeasured_places_nothing(self) -> None:
        record = timing_record()
        record["measurements"] = [m for m in record["measurements"] if m["host"] != "local"]
        placement = self.estimate(record=record).json["placement"]["full"]
        self.assertIsNone(placement["where"])
        self.assertIn("local timing probe", placement["reason"])

    def test_the_mean_is_taken_per_arm_not_over_all_measurements(self) -> None:
        run = self.estimate("--stage", "poc")
        # An overall mean would read (10 + 14 + 20) / 3 = 14.67 s/epoch.
        self.assertEqual(run.json["estimates"]["poc"]["local"]["secondsPerUnit"], 16)

    def test_setup_is_zero_when_no_measurement_records_it(self) -> None:
        run = self.estimate("--stage", "poc")
        remote = run.json["estimates"]["poc"]["svc:alice"]
        # 2 s/epoch x 5 x 2 x 1 x 2 = 40, no setup recorded.
        self.assertEqual((remote["seconds"], remote["low"], remote["high"]), (40, 32, 48))
        self.assertEqual(remote["setupSeconds"], 0)
        self.assertEqual(remote["device"], "cuda:A100")

    def test_a_remote_host_without_measurements_reads_unmeasured(self) -> None:
        run = self.estimate("--host", "other:bob")
        self.assertEqual(run.code, 0, run.err)
        for stage in ("poc", "full"):
            self.assertEqual(run.json["estimates"][stage]["other:bob"], "unmeasured")
            # never estimated from local timings scaled by a guessed factor
            self.assertNotEqual(run.json["estimates"][stage]["local"], "unmeasured")

    def test_local_reads_unmeasured_when_only_a_remote_host_was_timed(self) -> None:
        record = timing_record()
        record["measurements"] = [m for m in record["measurements"] if m["host"] != "local"]
        run = self.estimate(record=record)
        self.assertEqual(run.code, 0, run.err)
        self.assertEqual(run.json["estimates"]["full"]["local"], "unmeasured")
        self.assertIsInstance(run.json["estimates"]["full"]["svc:alice"], dict)

    def test_one_stage_reports_only_that_stage(self) -> None:
        run = self.estimate("--stage", "full")
        self.assertEqual(sorted(run.json["estimates"]), ["full"])

    def test_the_json_flag_is_accepted(self) -> None:
        self.assertEqual(self.estimate("--json").code, 0)

    def test_missing_timing_is_refused(self) -> None:
        self.refused(Run(["--root", str(self.root), "estimate"]), "missing-input")

    def test_a_timing_file_that_does_not_exist_is_refused(self) -> None:
        self.refused(Run(["--root", str(self.root), "estimate", "--timing",
                          str(self.root / "nope.json")]), "timing-missing")

    def test_a_bad_stage_is_refused(self) -> None:
        self.refused(self.estimate("--stage", "pilot"), "bad-argument")

    def test_a_bad_host_slug_is_refused(self) -> None:
        self.refused(self.estimate("--host", "Not A Host"), "bad-argument")

    def test_malformed_records_are_refused(self) -> None:
        def measurement(**change):
            record = timing_record()
            record["measurements"][0].update(change)
            return record

        def without(key):
            record = timing_record()
            del record["measurements"][0][key]
            return record

        cases = {
            "not json": "{nope",
            "not an object": [],
            "schema 2": timing_record(schema=2),
            "schema as text": timing_record(schema="1"),
            "no measurements": timing_record(measurements=[]),
            "unknown key": timing_record(extra=True),
            "bad unit": measurement(unit="step"),
            "zero seconds": measurement(secondsPerUnit=0),
            "negative seconds": measurement(secondsPerUnit=-1.0),
            "boolean seconds": measurement(secondsPerUnit=True),
            "fractional units": measurement(unitsMeasured=1.5),
            "negative setup": measurement(setupSeconds=-5),
            "bad host": measurement(host="Some Host"),
            "bad device": measurement(device="gpu"),
            "empty cuda name": measurement(device="cuda:"),
            "bad date": measurement(measuredAt="yesterday"),
            "empty arm": measurement(arm=""),
            "missing arm": without("arm"),
            "unknown measurement key": measurement(note="x"),
            "scales without full": timing_record(scales={"poc": {"arms": 1, "folds": 1, "seeds": 1, "epochs": 1}}),
            "zero epochs": timing_record(scales={"poc": {"arms": 1, "folds": 1, "seeds": 1, "epochs": 0},
                                                 "full": {"arms": 1, "folds": 1, "seeds": 1, "epochs": 1}}),
            "missing folds": timing_record(scales={"poc": {"arms": 1, "seeds": 1, "epochs": 1},
                                                   "full": {"arms": 1, "folds": 1, "seeds": 1, "epochs": 1}}),
        }
        for label, record in cases.items():
            with self.subTest(label):
                self.refused(self.estimate(record=record), "timing-invalid")

    def test_one_host_on_two_devices_is_never_pooled(self) -> None:
        record = timing_record()
        record["measurements"][2]["device"] = "mps"
        self.refused(self.estimate(record=record), "mixed-devices")

    def test_record_writes_the_estimate_inside_the_workspace(self) -> None:
        tree = self.root / "Product"
        tree.mkdir()
        path = self.write(timing_record(), "Product/Results/timing.json")
        run = Run(["--root", str(self.root), "estimate", "--timing", str(path), "--record", "Product"])
        self.assertEqual(run.code, 0, run.err)
        self.assertEqual(run.json["recorded"], f"Product/.remote-parallelism/estimate-{TODAY}.json")
        saved = json.loads((self.root / run.json["recorded"]).read_text(encoding="utf-8"))
        self.assertEqual(saved["estimates"], run.json["estimates"])
        again = Run(["--root", str(self.root), "estimate", "--timing", str(path), "--record", "Product"])
        self.assertEqual(again.json["recorded"], f"Product/.remote-parallelism/estimate-{TODAY}-2.json")

    def test_record_refuses_a_timing_file_outside_the_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as other:
            outside = Path(other) / "timing.json"
            outside.write_text(json.dumps(timing_record()), encoding="utf-8")
            (self.root / "Product").mkdir()
            run = Run(["--root", str(self.root), "estimate", "--timing", str(outside),
                       "--record", "Product"])
            self.refused(run, "timing-outside-workspace")
            link = self.root / "link.json"
            os.symlink(outside, link)
            run = Run(["--root", str(self.root), "estimate", "--timing", str(link),
                       "--record", "Product"])
            self.refused(run, "timing-outside-workspace")
            self.assertFalse((self.root / "Product" / ".remote-parallelism").exists())

    def test_without_record_a_timing_file_anywhere_is_read(self) -> None:
        with tempfile.TemporaryDirectory() as other:
            outside = Path(other) / "timing.json"
            outside.write_text(json.dumps(timing_record()), encoding="utf-8")
            run = Run(["--root", str(self.root), "estimate", "--timing", str(outside)])
            self.assertEqual(run.code, 0, run.err)


# ------------------------------------------------------------- doctrine
def _table_rows(doc: str, heading: str) -> list[list[str]]:
    """The cells of the first Markdown table after `heading`."""
    start = doc.index(heading)
    rows, seen = [], False
    for line in doc[start:].splitlines()[1:]:
        if line.startswith("|"):
            seen = True
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if set("".join(cells)) <= set("-: "):
                continue
            rows.append(cells)
        elif seen:
            break
    return rows[1:]


class DoctrineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.doc = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.flat = " ".join(self.doc.split())

    def test_frontmatter_names_the_skill_and_its_trigger(self) -> None:
        self.assertTrue(self.doc.startswith("---\nname: remote-parallelism\n"))
        header = self.doc.split("---", 2)[1]
        match = re.search(r'^description: "(.+)"$', header, re.MULTILINE)
        self.assertIsNotNone(match)
        self.assertTrue(match.group(1).startswith("Trigger: decide whether a proof of concept "
                                                  "or an experiment campaign is worth spreading "
                                                  "over several remote GPU accounts"))

    def test_the_objective_flow_table_equals_the_code(self) -> None:
        rows = _table_rows(self.doc, "## The objective flow")
        declared = [[f"`{s['stage']}`", s["establishes"], s["behindWhen"]]
                    for s in CLI.OBJECTIVE_FLOW["stages"]]
        self.assertEqual(rows, declared)
        self.assertEqual([s["stage"] for s in CLI.OBJECTIVE_FLOW["stages"]],
                         ["measured", "assessed", "planned"])
        self.assertIn(f"**Arrival:** {CLI.OBJECTIVE_FLOW['arrival']}.", self.flat)

    def test_the_error_code_table_equals_the_code(self) -> None:
        rows = _table_rows(self.doc, "### Error codes")
        documented = [row[0].strip("`") for row in rows]
        self.assertEqual(documented, list(CLI.ERROR_CODES))
        source = CLI_PATH.read_text(encoding="utf-8")
        raised = set(re.findall(r'Refusal\(\s*"([a-z-]+)"', source))
        self.assertEqual(raised, set(CLI.ERROR_CODES))

    def test_every_verb_is_documented(self) -> None:
        for verb in CLI.VERBS:
            self.assertIn(f"| `{verb}` |", self.doc)

    def test_the_doctrine_reuses_placement_and_keeps_the_launch_gate(self) -> None:
        for fragment in ("`distribute`", "`generate-job`", "`readiness`", "`submit`",
                         "identicalAcrossShards", "machine_shape", "never by arm",
                         "torch.use_deterministic_algorithms(True)",
                         "CUBLAS_WORKSPACE_CONFIG=:4096:8",
                         "never launch authorization", "terms",
                         "one account per person per service", "distinct owners",
                         "https://research.google.com/colaboratory/faq.html",
                         "running distributed computing workers", "`--owners`"):
            self.assertIn(fragment, self.flat, fragment)

    def test_the_doctrine_says_how_to_estimate_before_scaling(self) -> None:
        self.assertIn("## Estimate before you scale", self.doc)
        for fragment in ("Results/timing.json", "one epoch of one fold per arm",
                         "own interpreter", "`scales`", "approved protocol", "declared pilot",
                         "±20%, single-probe extrapolation", "`unmeasured`",
                         "measured rehearsal on that host", "before the pilot",
                         "before the full run", "never launch authorization"):
            self.assertIn(fragment, self.flat, fragment)

    def test_the_skill_delegates_to_no_agent(self) -> None:
        self.assertNotIn("delegates to the `", self.doc)
        self.assertNotIn("## When a delegated agent cannot be spawned", self.doc)

    def test_the_cli_is_stdlib_only(self) -> None:
        allowed = set(sys.stdlib_module_names) | {"__future__"}
        text = CLI_PATH.read_text(encoding="utf-8")
        for name in re.findall(r"^\s*(?:from|import)\s+([A-Za-z_]\w*)", text, re.MULTILINE):
            self.assertIn(name, allowed, name)


# ------------------------------------------------------------- agents
class AgentReferenceTests(unittest.TestCase):
    #: Each agent's binding -- its FIRST skills/<x>/SKILL.md reference --
    #: which this skill must never displace.
    BINDINGS = {
        "implementation-walk": "proposal-implementation",
        "experiments-walk": "experimental-implementation",
        "experiments-build": "experimental-implementation",
        "experiments-reviewer": "experimental-implementation",
        "paper-replicator": "proposal-implementation",
    }

    def test_every_poc_and_experiment_agent_loads_this_skill(self) -> None:
        for agent, binding in self.BINDINGS.items():
            with self.subTest(agent=agent):
                body = (AGENTS / f"{agent}.md").read_text(encoding="utf-8")
                named = re.findall(r"skills/([\w-]+)/SKILL\.md", body)
                self.assertEqual(named[0], binding)
                self.assertIn("remote-parallelism", named[1:])
                flat = " ".join(body.split())
                self.assertIn("`assess`", flat)
                self.assertIn("never launch authorization", flat)


if __name__ == "__main__":
    unittest.main()
