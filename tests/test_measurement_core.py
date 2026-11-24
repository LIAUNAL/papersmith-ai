"""Measurement core shared by the hardware and lab-simulation lines (paper-type-lines S7, S8; T8-M1, decision F1).

The operator registers instruments (`study/instruments.json`) and the raw
measurement files they produced (`study/measurements.json`, bound by
sha256); the core computes from them an uncertainty budget per quantity
(JCGM 100:2008) and the agreement of a device with a reference device
(Bland-Altman, ICC(2,1)). It never writes a measured value: every test that
computes also checks that the registered files keep their bytes.

Every numeric expectation is recomputed here with explicit arithmetic or
taken from a published table, never from the module under test.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CLI = REPO / "skills" / "_core" / "measurement" / "measure_cli.py"
sys.path.insert(0, str(REPO))

READINGS = [10.01, 10.03, 9.99, 10.02, 10.00]
CALIPER = ("instrument", "add", "--id", "caliper-1", "--model", "Mitutoyo 500-196", "--serial", "SN-001",
           "--resolution", "0.01 mm", "--stated-uncertainty", "0.02 mm", "--distribution", "normal",
           "--coverage-k", "2", "--calibration-certificate", "LAB-CAL-2026-17", "--calibrated", "2026-01-10",
           "--due", "2099-01-10", "--by", "Ana Ruiz")
# Student t quantiles, two-sided 95 % (one-sided 0.975), from any standard table.
T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 10: 2.228, 20: 2.086, 30: 2.042, 40: 2.021,
        100: 1.984}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sample_sd(values: list[float]) -> float:
    mean = sum(values) / len(values)
    return math.sqrt(sum((v - mean) ** 2 for v in values) / (len(values) - 1))


class Workspace(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="measurement-core-")
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def run_cli(self, *args: str) -> tuple[int, dict]:
        proc = subprocess.run([sys.executable, str(CLI), *args, "--root", str(self.root)],
                              capture_output=True, text=True, cwd=str(REPO))
        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1, f"one JSON object expected, got {proc.stdout!r} / {proc.stderr!r}")
        return proc.returncode, json.loads(lines[0])

    def ok(self, *args: str) -> dict:
        code, out = self.run_cli(*args)
        self.assertEqual((code, out["ok"]), (0, True), out)
        return out

    def refused(self, error: str, *args: str) -> dict:
        code, out = self.run_cli(*args)
        self.assertEqual((code, out["ok"], out.get("error")), (1, False, error), out)
        self.assertTrue(out["message"])
        return out

    def csv(self, name: str, header: str, rows: list[str]) -> Path:
        path = self.root / "data" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(header + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
        return path

    def readings(self, name: str = "length.csv", values=READINGS) -> Path:
        return self.csv(name, "replicate,length", [f"r{i + 1},{v}" for i, v in enumerate(values)])

    def register(self, name: str = "length.csv", *extra: str) -> dict:
        return self.ok("data", "register", "--file", f"data/{name}", "--quantity", "length", "--unit", "mm",
                       "--instrument", "caliper-1", "--replicate-column", "replicate", "--by", "Ana Ruiz", *extra)


class StudentT(unittest.TestCase):
    def test_quantiles_match_the_table_to_three_decimals(self) -> None:
        from skills._core.measurement import stats
        for dof, expected in T975.items():
            with self.subTest(dof=dof):
                self.assertAlmostEqual(stats.t_quantile(0.975, dof), expected, places=3)
        self.assertAlmostEqual(stats.t_quantile(0.995, 4), 4.604, places=3)
        self.assertAlmostEqual(stats.t_quantile(0.95, 7), 1.895, places=3)
        self.assertAlmostEqual(stats.t_quantile(0.025, 5), -2.571, places=3)
        self.assertAlmostEqual(stats.t_quantile(0.975, None), 1.960, places=3)

    def test_gum_table_g2_at_95_45_percent(self) -> None:
        from skills._core.measurement import stats
        # JCGM 100:2008 Table G.2, p = 95.45 %.
        for dof, expected in {1: 13.97, 2: 4.53, 3: 3.31, 5: 2.65, 10: 2.28, 20: 2.13, 50: 2.05, None: 2.00}.items():
            with self.subTest(dof=dof):
                self.assertAlmostEqual(stats.t_quantile((1 + 0.9545) / 2, dof), expected, places=2)


class Agreement(unittest.TestCase):
    def test_icc_2_1_reproduces_shrout_and_fleiss_table_2(self) -> None:
        from skills._core.measurement import stats
        # Shrout & Fleiss (1979), Table 2: six targets rated by four judges; ICC(2,1) = .29.
        rows = [[9, 2, 5, 8], [6, 1, 3, 2], [8, 4, 6, 8], [7, 1, 2, 6], [10, 5, 6, 9], [6, 2, 4, 7]]
        self.assertAlmostEqual(stats.icc_2_1(rows)["value"], 0.29, places=2)


class Instruments(Workspace):
    def test_add_records_the_instrument_with_its_calibration(self) -> None:
        out = self.ok(*CALIPER)
        self.assertEqual(out["path"], "study/instruments.json")
        stored = json.loads((self.root / "study" / "instruments.json").read_text())
        entry = stored["history"][0]
        self.assertEqual(entry["id"], "caliper-1")
        self.assertEqual(entry["resolution"], {"value": 0.01, "unit": "mm"})
        self.assertEqual(entry["stated_uncertainty"],
                         {"value": 0.02, "unit": "mm", "distribution": "normal", "coverage_k": 2.0})
        self.assertEqual((entry["calibrated"], entry["due"], entry["by"]), ("2026-01-10", "2099-01-10", "Ana Ruiz"))

    def test_status_reports_current_and_past_due_on_a_date(self) -> None:
        self.ok(*CALIPER)
        before = self.ok("instrument", "status", "--on", "2099-01-10")["instruments"]
        self.assertEqual(before["instruments"][0]["calibration"], "current")
        after = self.ok("instrument", "status", "--on", "2099-01-11")["instruments"]
        self.assertEqual(after["instruments"][0]["calibration"], "past-due")
        self.assertEqual(after["past_due"], ["caliper-1"])

    def test_history_is_never_overwritten_silently(self) -> None:
        self.ok(*CALIPER)
        self.refused("RECORD_UNCHANGED", *CALIPER)
        recalibrated = [a if a != "2026-01-10" else "2026-06-01" for a in CALIPER]
        self.refused("INSTRUMENT_EXISTS", *recalibrated)
        self.ok(*recalibrated, "--reason", "recalibrated after repair")
        history = json.loads((self.root / "study" / "instruments.json").read_text())["history"]
        self.assertEqual([e["calibrated"] for e in history], ["2026-01-10", "2026-06-01"])
        self.assertEqual(history[1]["reason"], "recalibrated after repair")
        state = self.ok("instrument", "status", "--on", "2026-07-01")["instruments"]
        self.assertEqual((state["instruments"][0]["calibrated"], state["instruments"][0]["entries"]),
                         ("2026-06-01", 2))

    def test_refusals(self) -> None:
        without_by = CALIPER[:-2]
        self.refused("APPROVER_MISSING", *without_by)
        no_certificate = [a for i, a in enumerate(CALIPER) if i not in (CALIPER.index("--calibration-certificate"),
                                                                       CALIPER.index("--calibration-certificate") + 1)]
        self.refused("FIELD_MISSING", *no_certificate)
        swap = list(CALIPER)
        swap[swap.index("--due") + 1] = "2025-01-01"
        self.refused("DATE_ORDER", *swap)
        bad = list(CALIPER)
        bad[bad.index("--resolution") + 1] = "0.01"
        self.refused("MAGNITUDE_INVALID", *bad)
        rect = list(CALIPER)
        rect[rect.index("--distribution") + 1] = "rectangular"
        self.refused("FIELDS_CONFLICT", *rect)
        no_k = [a for i, a in enumerate(CALIPER) if i not in (CALIPER.index("--coverage-k"),
                                                              CALIPER.index("--coverage-k") + 1)]
        self.refused("FIELD_MISSING", *no_k)
        self.assertFalse((self.root / "study").exists())
        code, out = self.run_cli(*CALIPER[:-2], "--distribution", "triangular")
        self.assertEqual((code, out["error"]), (2, "USAGE"))


class DataRegistration(Workspace):
    def test_register_binds_the_file_by_hash(self) -> None:
        self.ok(*CALIPER)
        path = self.readings()
        out = self.register("length.csv", "--condition", "temperature=20 C")
        entry = out["registration"]
        self.assertEqual((entry["path"], entry["sha256"], entry["rows"]), ("data/length.csv", sha256(path), 5))
        self.assertEqual(entry["columns"], ["replicate", "length"])
        self.assertEqual((entry["value_column"], entry["conditions"]), ("length", {"temperature": "20 C"}))
        self.assertEqual(self.ok("data", "status")["data"]["files"][0]["state"], "current")

    def test_refusals(self) -> None:
        self.readings()
        base = ("data", "register", "--file", "data/length.csv", "--quantity", "length", "--unit", "mm",
                "--instrument", "caliper-1", "--by", "Ana Ruiz")
        self.refused("INSTRUMENT_UNKNOWN", *base)
        self.ok(*CALIPER)
        self.refused("APPROVER_MISSING", *base[:-2])
        self.refused("FILE_ABSENT", *[a if a != "data/length.csv" else "data/none.csv" for a in base])
        outside = Path(tempfile.mkdtemp(prefix="measurement-outside-"))
        self.addCleanup(lambda: (outside / "x.csv").unlink(missing_ok=True) or outside.rmdir())
        (outside / "x.csv").write_text("length\n1\n2\n")
        self.refused("PATH_OUTSIDE_WORKSPACE", *[a if a != "data/length.csv" else str(outside / "x.csv")
                                                 for a in base])
        self.refused("COLUMN_ABSENT", *base, "--value-column", "width")
        self.refused("COLUMN_ABSENT", *base, "--replicate-column", "run")
        self.csv("bad.csv", "replicate,length", ["r1,10.0", "r2,", "r3,10.1"])
        self.refused("VALUE_INVALID", *[a if a != "data/length.csv" else "data/bad.csv" for a in base])
        self.csv("dup.csv", "replicate,length", ["r1,10.0", "r1,10.1"])
        self.refused("REPLICATE_DUPLICATE", *[a if a != "data/length.csv" else "data/dup.csv" for a in base],
                     "--replicate-column", "replicate")
        self.refused("CONDITION_INVALID", *base, "--condition", "temperature")
        self.refused("QUANTITY_NAME_INVALID", *[a if a != "length" else "../length" for a in base])
        self.ok(*base)
        self.refused("RECORD_UNCHANGED", *base)
        self.refused("DATA_ALREADY_REGISTERED", *base, "--condition", "temperature=20 C")
        self.ok(*base, "--condition", "temperature=20 C", "--reason", "condition was omitted")


class UncertaintyBudget(Workspace):
    def setUp(self) -> None:
        super().setUp()
        self.ok(*CALIPER)
        self.data = self.readings()
        self.register()

    def expected(self, sensitivity_resolution: float = 1.0) -> dict:
        # JCGM 100:2008 4.2 (type A), 4.3.3 and F.2.2.1 (type B), 5.1.2 (combination), G.4.1 (nu_eff).
        n = len(READINGS)
        mean = sum(READINGS) / n
        u_a = sample_sd(READINGS) / math.sqrt(n)
        u_cal = 0.02 / 2
        u_res = 0.01 / (2 * math.sqrt(3))
        terms = [u_a, u_cal, sensitivity_resolution * u_res]
        u_c = math.sqrt(sum(t * t for t in terms))
        nu_eff = u_c ** 4 / (u_a ** 4 / (n - 1))
        return {"mean": mean, "u_a": u_a, "u_cal": u_cal, "u_res": u_res, "u_c": u_c, "nu_eff": nu_eff}

    def test_gum_worked_example_at_95_percent(self) -> None:
        out = self.ok("uncertainty", "compute", "--quantity", "length", "--level", "0.95")
        self.assertEqual(out["path"], "study/uncertainty/length.json")
        budget = out["budget"]
        hand = self.expected()
        # By hand: mean 10.01, s = sqrt(0.001/4) = 0.0158114, u_A = 0.0070711, u_c = 0.0125831.
        self.assertAlmostEqual(hand["mean"], 10.01, places=12)
        self.assertAlmostEqual(hand["u_c"], 0.0125831, places=7)
        self.assertAlmostEqual(budget["type_a"]["mean"], hand["mean"], places=12)
        self.assertAlmostEqual(budget["type_a"]["sd"], 0.0158114, places=7)
        self.assertEqual((budget["type_a"]["n"], budget["type_a"]["dof"]), (5, 4))
        components = {c["name"]: c for c in budget["components"]}
        self.assertAlmostEqual(components["repeatability"]["u"], hand["u_a"], places=12)
        self.assertAlmostEqual(components["calibration"]["u"], hand["u_cal"], places=12)
        self.assertAlmostEqual(components["resolution"]["u"], hand["u_res"], places=12)
        self.assertEqual((components["calibration"]["type"], components["calibration"]["dof"]), ("B", None))
        self.assertAlmostEqual(budget["combined_standard_uncertainty"], hand["u_c"], places=12)
        # nu_eff = 0.000158333^2 / (0.00005^2 / 4) = 40.11, truncated to 40 (GUM G.4.1 note).
        self.assertAlmostEqual(budget["effective_dof"], hand["nu_eff"], places=6)
        self.assertAlmostEqual(budget["effective_dof"], 40.11, places=2)
        self.assertEqual(budget["coverage"]["dof_used"], 40)
        self.assertEqual(budget["coverage"]["method"], "student-t")
        self.assertAlmostEqual(budget["coverage"]["k"], T975[40], places=3)
        self.assertAlmostEqual(budget["expanded_uncertainty"], T975[40] * hand["u_c"], places=4)
        self.assertEqual(budget["inputs"]["files"], [{"path": "data/length.csv", "sha256": sha256(self.data),
                                                      "rows": 5}])
        self.assertTrue(budget["inputs"]["instrument"]["entry_sha256"])
        state = self.ok("uncertainty", "status")["uncertainty"]
        self.assertEqual((state["budgets"][0]["quantity"], state["budgets"][0]["state"]), ("length", "current"))

    def test_declared_k_and_sensitivity(self) -> None:
        budget = self.ok("uncertainty", "compute", "--quantity", "length", "--coverage-k", "2",
                         "--sensitivity", "resolution=2")["budget"]
        hand = self.expected(sensitivity_resolution=2.0)
        self.assertAlmostEqual(budget["combined_standard_uncertainty"], hand["u_c"], places=12)
        self.assertEqual((budget["coverage"]["method"], budget["coverage"]["k"], budget["coverage"]["level"]),
                         ("declared", 2.0, None))
        self.assertAlmostEqual(budget["expanded_uncertainty"], 2 * hand["u_c"], places=12)
        components = {c["name"]: c for c in budget["components"]}
        self.assertEqual(components["resolution"]["sensitivity"], 2.0)
        self.assertAlmostEqual(components["resolution"]["contribution"], 2 * hand["u_res"], places=12)

    def test_rectangular_stated_uncertainty(self) -> None:
        rect = list(CALIPER)
        rect[rect.index("--distribution") + 1] = "rectangular"
        rect[rect.index("--stated-uncertainty") + 1] = "0.05 mm"
        del rect[rect.index("--coverage-k"):rect.index("--coverage-k") + 2]
        self.ok(*rect, "--reason", "manufacturer accuracy as a half-width")
        budget = self.ok("uncertainty", "compute", "--quantity", "length")["budget"]
        components = {c["name"]: c for c in budget["components"]}
        self.assertAlmostEqual(components["calibration"]["u"], 0.05 / math.sqrt(3), places=12)
        self.assertEqual(budget["coverage"]["level"], 0.95)

    def test_refusals(self) -> None:
        self.refused("DATA_ABSENT", "uncertainty", "compute", "--quantity", "mass")
        self.refused("FIELD_MISSING", "uncertainty", "compute")
        self.refused("FIELD_MISSING", "agreement", "compute", "--device-file", "data/length.csv")
        self.refused("FIELDS_CONFLICT", "uncertainty", "compute", "--quantity", "length", "--level", "0.95",
                     "--coverage-k", "2")
        self.refused("LEVEL_INVALID", "uncertainty", "compute", "--quantity", "length", "--level", "95")
        self.refused("COMPONENT_UNKNOWN", "uncertainty", "compute", "--quantity", "length",
                     "--sensitivity", "temperature=1")
        self.refused("SENSITIVITY_INVALID", "uncertainty", "compute", "--quantity", "length",
                     "--sensitivity", "resolution=x")
        self.readings("one.csv", [10.0])
        self.ok("data", "register", "--file", "data/one.csv", "--quantity", "width", "--unit", "mm",
                "--instrument", "caliper-1", "--value-column", "length", "--by", "Ana Ruiz")
        self.refused("REPLICATES_TOO_FEW", "uncertainty", "compute", "--quantity", "width")
        self.readings("inch.csv")
        self.ok("data", "register", "--file", "data/inch.csv", "--quantity", "depth", "--unit", "in",
                "--instrument", "caliper-1", "--value-column", "length", "--by", "Ana Ruiz")
        self.refused("UNIT_MISMATCH", "uncertainty", "compute", "--quantity", "depth")
        self.ok("uncertainty", "compute", "--quantity", "depth", "--sensitivity", "resolution=0.03937",
                "--sensitivity", "calibration=0.03937")
        self.readings("warm.csv")
        self.register("warm.csv", "--condition", "temperature=30 C")
        self.refused("CONDITIONS_MIXED", "uncertainty", "compute", "--quantity", "length")
        warm = self.ok("uncertainty", "compute", "--quantity", "length", "--condition", "temperature=30 C")
        self.assertEqual(warm["budget"]["conditions"], {"temperature": "30 C"})
        self.assertEqual([f["path"] for f in warm["budget"]["inputs"]["files"]], ["data/warm.csv"])

    def test_past_due_calibration_refuses_unless_the_operator_overrides(self) -> None:
        late = list(CALIPER)
        late[late.index("--calibrated") + 1] = "1999-01-01"
        late[late.index("--due") + 1] = "2000-01-01"
        self.ok(*late, "--reason", "the certificate on file is the old one")
        self.refused("CALIBRATION_PAST_DUE", "uncertainty", "compute", "--quantity", "length")
        self.refused("APPROVER_MISSING", "uncertainty", "compute", "--quantity", "length", "--allow-past-due",
                     "--reason", "drift checked against a gauge block")
        self.refused("REASON_MISSING", "uncertainty", "compute", "--quantity", "length", "--allow-past-due",
                     "--by", "Ana Ruiz")
        budget = self.ok("uncertainty", "compute", "--quantity", "length", "--allow-past-due", "--by", "Ana Ruiz",
                         "--reason", "drift checked against a gauge block")["budget"]
        self.assertEqual(budget["calibration"]["state"], "past-due")
        self.assertEqual((budget["calibration"]["override"]["by"], budget["calibration"]["override"]["reason"]),
                         ("Ana Ruiz", "drift checked against a gauge block"))

    def test_an_override_on_a_current_calibration_refuses_instead_of_being_dropped(self) -> None:
        # The operator's attestation is never silently discarded: with the
        # calibration current, --allow-past-due, --by or --reason refuse.
        for extra in (("--allow-past-due", "--by", "Ana Ruiz", "--reason", "drift checked"),
                      ("--by", "Ana Ruiz"), ("--reason", "drift checked")):
            with self.subTest(extra=extra):
                self.refused("OVERRIDE_NOT_NEEDED", "uncertainty", "compute", "--quantity", "length", *extra)
        budget = self.ok("uncertainty", "compute", "--quantity", "length")["budget"]
        self.assertIsNone(budget["calibration"]["override"])

    def test_a_changed_input_makes_the_budget_stale(self) -> None:
        self.ok("uncertainty", "compute", "--quantity", "length")
        self.data.write_text(self.data.read_text().replace("10.03", "10.04"), encoding="utf-8")
        budget = self.ok("status")["uncertainty"]["budgets"][0]
        self.assertEqual((budget["state"], budget["reasons"]), ("stale", ["input-changed"]))
        self.assertEqual(self.ok("data", "status")["data"]["files"][0]["state"], "changed")
        self.refused("DATA_CHANGED", "uncertainty", "compute", "--quantity", "length")
        self.register("length.csv", "--reason", "transcription error corrected by the operator")
        self.assertIn("input-changed", self.ok("uncertainty", "status")["uncertainty"]["budgets"][0]["reasons"])
        self.ok("uncertainty", "compute", "--quantity", "length")
        self.assertEqual(self.ok("uncertainty", "status")["uncertainty"]["budgets"][0]["state"], "current")
        self.readings("more.csv")
        self.register("more.csv")
        self.assertEqual(self.ok("uncertainty", "status")["uncertainty"]["budgets"][0]["reasons"], ["inputs-added"])
        self.ok("uncertainty", "compute", "--quantity", "length")
        recalibrated = [a if a != "2026-01-10" else "2026-06-01" for a in CALIPER]
        self.ok(*recalibrated, "--reason", "recalibrated")
        self.assertEqual(self.ok("uncertainty", "status")["uncertainty"]["budgets"][0]["reasons"],
                         ["instrument-changed"])
        self.data.unlink()
        self.assertIn("input-missing", self.ok("uncertainty", "status")["uncertainty"]["budgets"][0]["reasons"])
        warnings = {w["code"] for w in self.ok("status")["warnings"]}
        self.assertTrue({"BUDGET_STALE", "DATA_MISSING"} <= warnings, warnings)


DEVICE = [10, 12, 14, 16, 19]
REFERENCE = [11, 12, 13, 17, 17]


class DeviceAgreement(Workspace):
    def setUp(self) -> None:
        super().setUp()
        self.ok(*CALIPER)
        self.ok("instrument", "add", "--id", "ref-1", "--model", "Reference gauge", "--serial", "R-9",
                "--resolution", "0.001 mm", "--calibration-certificate", "NMI-44", "--calibrated", "2026-01-01",
                "--due", "2099-01-01", "--by", "Ana Ruiz")
        self.device = self.csv("device.csv", "sample,length", [f"s{i},{v}" for i, v in enumerate(DEVICE)]
                               + ["s9,15"])
        self.reference = self.csv("reference.csv", "sample,length", [f"s{i},{v}" for i, v in enumerate(REFERENCE)])
        for name, instrument in (("device.csv", "caliper-1"), ("reference.csv", "ref-1")):
            self.ok("data", "register", "--file", f"data/{name}", "--quantity", "length", "--unit", "mm",
                    "--instrument", instrument, "--by", "Ana Ruiz")

    def test_bland_altman_and_icc(self) -> None:
        out = self.ok("agreement", "compute", "--device-file", "data/device.csv", "--reference-file",
                      "data/reference.csv", "--pair-column", "sample")
        self.assertEqual(out["path"], "study/agreement.json")
        analysis = out["analysis"]
        n = len(DEVICE)
        diffs = [d - r for d, r in zip(DEVICE, REFERENCE)]
        bias = sum(diffs) / n                       # (-1 + 0 + 1 - 1 + 2) / 5 = 0.2
        sd = sample_sd(diffs)                       # sqrt(6.8 / 4) = 1.30384
        self.assertAlmostEqual(bias, 0.2, places=12)
        self.assertAlmostEqual(sd, math.sqrt(1.7), places=12)
        ba = analysis["bland_altman"]
        self.assertEqual((ba["n"], analysis["n"]), (5, 5))
        self.assertAlmostEqual(ba["bias"], bias, places=12)
        self.assertAlmostEqual(ba["sd_differences"], sd, places=12)
        self.assertAlmostEqual(ba["loa_lower"], bias - 1.96 * sd, places=12)
        self.assertAlmostEqual(ba["loa_upper"], bias + 1.96 * sd, places=12)
        # ICC(A,1) for two raters from the means a_i and differences d_i (an algebraic identity of the
        # two-way ANOVA form, independent of the module): MSR = 2 var(a), MSE = var(d) / 2, MSC = n dbar^2 / 2.
        means = [(d + r) / 2 for d, r in zip(DEVICE, REFERENCE)]
        var_a = sample_sd(means) ** 2
        var_d = sd ** 2
        icc = (2 * var_a - var_d / 2) / (2 * var_a + var_d / 2 + bias ** 2 - var_d / n)
        self.assertAlmostEqual(analysis["icc"]["value"], icc, places=12)
        self.assertEqual(analysis["icc"]["form"], "ICC(2,1)")
        self.assertEqual(analysis["unpaired"], {"device": ["s9"], "reference": []})
        self.assertEqual(analysis["device"]["sha256"], sha256(self.device))
        state = self.ok("agreement", "status")["agreement"]
        self.assertEqual(state["analyses"][0]["state"], "current")
        self.device.write_text(self.device.read_text().replace("s4,19", "s4,20"), encoding="utf-8")
        stale = self.ok("agreement", "status")["agreement"]["analyses"][0]
        self.assertEqual((stale["state"], stale["reasons"]), ("stale", ["device-changed"]))

    def test_refusals(self) -> None:
        base = ("agreement", "compute", "--device-file", "data/device.csv", "--reference-file", "data/reference.csv")
        self.refused("COLUMN_ABSENT", *base, "--pair-column", "subject")
        self.csv("loose.csv", "sample,length", ["s0,1", "s1,2"])
        self.refused("DATA_NOT_REGISTERED", *base[:-1], "data/loose.csv", "--pair-column", "sample")
        self.ok("data", "register", "--file", "data/loose.csv", "--quantity", "length", "--unit", "mm",
                "--instrument", "ref-1", "--by", "Ana Ruiz")
        self.refused("PAIRS_TOO_FEW", *base[:-1], "data/loose.csv", "--pair-column", "sample")
        self.csv("mass.csv", "sample,mass", [f"s{i},{v}" for i, v in enumerate(REFERENCE)])
        self.ok("data", "register", "--file", "data/mass.csv", "--quantity", "mass", "--unit", "mm",
                "--instrument", "ref-1", "--by", "Ana Ruiz")
        self.refused("QUANTITY_MISMATCH", *base[:-1], "data/mass.csv", "--pair-column", "sample")
        self.csv("twice.csv", "sample,length", ["s0,1", "s0,2", "s1,3", "s2,4"])
        self.ok("data", "register", "--file", "data/twice.csv", "--quantity", "length", "--unit", "mm",
                "--instrument", "ref-1", "--by", "Ana Ruiz")
        self.refused("PAIR_DUPLICATE", *base[:-1], "data/twice.csv", "--pair-column", "sample")
        self.refused("FIELDS_CONFLICT", *base[:-1], "data/device.csv", "--pair-column", "sample")


class NoMeasuredValueIsWritten(Workspace):
    def test_every_verb_leaves_registered_files_untouched(self) -> None:
        self.ok(*CALIPER)
        files = [self.readings(), self.csv("ref.csv", "replicate,length",
                                           [f"r{i + 1},{v + 0.01}" for i, v in enumerate(READINGS)])]
        self.register()
        self.ok("data", "register", "--file", "data/ref.csv", "--quantity", "length", "--unit", "mm",
                "--instrument", "caliper-1", "--by", "Ana Ruiz", "--condition", "pass=2")
        before = {p: (sha256(p), os.stat(p).st_mtime_ns) for p in files}
        self.ok("uncertainty", "compute", "--quantity", "length", "--condition", "pass=2")
        self.ok("agreement", "compute", "--device-file", "data/length.csv", "--reference-file", "data/ref.csv",
                "--pair-column", "replicate")
        for verb in (("status",), ("data", "status"), ("uncertainty", "status"), ("agreement", "status"),
                     ("instrument", "status")):
            self.ok(*verb)
        self.assertEqual({p: (sha256(p), os.stat(p).st_mtime_ns) for p in files}, before)
        written = sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob("*") if p.is_file())
        self.assertEqual(written, ["data/length.csv", "data/ref.csv", "study/agreement.json",
                                   "study/instruments.json", "study/measurements.json",
                                   "study/uncertainty/length.json"])


class Readers(Workspace):
    def test_readers_are_side_effect_free(self) -> None:
        from skills._core.measurement import records
        self.assertEqual(records.instruments_state(self.root), {"state": "absent"})
        self.assertEqual(records.data_state(self.root), {"state": "absent", "files": []})
        self.assertEqual(records.budget_state(self.root), {"state": "absent", "budgets": []})
        self.assertEqual(records.agreement_state(self.root), {"state": "absent", "analyses": []})
        status = records.measurement_status(self.root)
        self.assertEqual(status["warnings"], [])
        self.assertEqual(list(self.root.iterdir()), [])

    def test_a_corrupt_record_is_reported_not_raised(self) -> None:
        from skills._core.measurement import records
        (self.root / "study").mkdir()
        (self.root / "study" / "instruments.json").write_text("{not json")
        self.assertEqual(records.instruments_state(self.root)["state"], "corrupt")
        codes = {w["code"] for w in records.measurement_status(self.root)["warnings"]}
        self.assertIn("INSTRUMENTS_CORRUPT", codes)
        self.refused("INSTRUMENTS_CORRUPT", *CALIPER)


if __name__ == "__main__":
    unittest.main()
