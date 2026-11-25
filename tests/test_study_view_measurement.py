"""The Study tab's measurement sections (paper-type-lines S8, T8-B1, decision F7).

A `hardware` or `lab-simulation` workspace (and any workspace that holds
measurement records) answers four more sections of `GET /api/study`, read only
through `skills/_core/measurement/records.py`: `instruments` (model, serial,
resolution, stated uncertainty, certificate, calibrated and due dates, current
or past due today), `measurements` (each registered raw data file: path,
quantity, unit, instrument, rows, conditions, current or changed; never a
measured value), `uncertainty` (each budget per quantity and condition set: its
type A/B components, sensitivity coefficients, combined and expanded
uncertainty, effective degrees of freedom, coverage factor and level, current or
stale with the reason, a past-due override and who authorized it) and
`agreement` (device and reference, n, bias, limits of agreement, ICC(2,1),
current or stale). The reporting section reads the checklist through
`registry.checklist_for`, so a hardware workspace (no variants) names
`hardwarex`, and lists `gum-reporting` as a second guideline of the line;
`GET /api/study/checklist?guideline=<id>` runs one of the line's guidelines and
refuses any other with 400. Every record is written by the real
`measure_cli.py`.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from skills._core.command_center import server, study_view
from skills._core.measurement import records
from tests.test_study_view import PAPER_TYPE, REPO, cli, workspace, write

MEASURE = REPO / "skills" / "_core" / "measurement" / "measure_cli.py"
MEASUREMENT = ("instruments", "measurements", "uncertainty", "agreement")
#: Raw readings: none of these strings may reach the view.
LENGTHS = ("7.1183", "7.1297", "7.1241", "7.1209")
DEVICE = ("51.0371", "52.4483", "49.8829", "50.6617")
REFERENCE = ("51.1102", "52.3391", "49.9974", "50.7215")
RAW = LENGTHS + DEVICE + REFERENCE


def instrument(root: Path, ident: str, *, calibrated: str = "2026-01-10", due: str = "2099-01-10",
               unit: str = "mm") -> None:
    cli(MEASURE, root, "instrument", "add", "--id", ident, "--model", "Mitutoyo <500>", "--serial", f"S-{ident}",
        "--resolution", f"0.01 {unit}", "--calibration-certificate", "CERT <9>", "--calibrated", calibrated,
        "--due", due, "--stated-uncertainty", f"0.02 {unit}", "--distribution", "normal", "--coverage-k", "2",
        "--by", "Ana Ruiz")


def lengths(root: Path) -> Path:
    path = write(root, "data/length.csv", "replicate,length\n" + "".join(f"r{i},{v}\n" for i, v in enumerate(LENGTHS)))
    cli(MEASURE, root, "data", "register", "--file", "data/length.csv", "--quantity", "length", "--unit", "mm",
        "--instrument", "caliper-1", "--replicate-column", "replicate", "--condition", "temperature=20 C",
        "--by", "Ana Ruiz")
    return path


def agreement(root: Path) -> Path:
    instrument(root, "device-1", unit="N")
    instrument(root, "ref-1", unit="N")
    device = write(root, "data/device.csv", "pair,value\n" + "".join(f"p{i},{v}\n" for i, v in enumerate(DEVICE)))
    write(root, "data/reference.csv", "pair,value\n" + "".join(f"p{i},{v}\n" for i, v in enumerate(REFERENCE)))
    for name, ident in (("device", "device-1"), ("reference", "ref-1")):
        cli(MEASURE, root, "data", "register", "--file", f"data/{name}.csv", "--quantity", "force", "--unit", "N",
            "--instrument", ident, "--value-column", "value", "--by", "Ana Ruiz")
    cli(MEASURE, root, "agreement", "compute", "--device-file", "data/device.csv", "--reference-file",
        "data/reference.csv", "--pair-column", "pair")
    return device


def agree(root: Path, variant: str | None, type_id: str) -> None:
    idea = write(root, "idea.txt", "A low-cost load cell for field force measurement, calibrated against a "
                                   "reference device.\nWe build it, budget its uncertainty and test agreement.\n")
    cli(PAPER_TYPE, root, "accept", "--by", "Ana Ruiz", "--idea-file", str(idea))
    cli(PAPER_TYPE, root, "agree", "--type", type_id, *(("--variant", variant) if variant else ()), "--by", "Ana Ruiz")


def measurement_records(root: Path) -> None:
    """One calibrated caliper, four length replicates and their budget, and a
    device-versus-reference agreement analysis."""
    instrument(root, "caliper-1")
    lengths(root)
    cli(MEASURE, root, "uncertainty", "compute", "--quantity", "length")
    agreement(root)


class MeasurementCase(unittest.TestCase):
    def get(self, root: Path, route: str = "/api/study") -> dict:
        response = TestClient(server.create_app(root)).get(route)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def section(self, view: dict, name: str) -> dict:
        self.assertTrue(view[name]["available"], view[name])
        return view[name]


class SectionsTests(MeasurementCase):
    def test_hardware_and_lab_simulation_answer_the_four_sections_even_empty(self) -> None:
        for kind in ("hardware", "lab-simulation"):
            with self.subTest(kind=kind):
                view = self.get(workspace(self, kind))
                self.assertEqual(view["paper_kind"], kind)
                self.assertEqual(view["warnings"], [])
                for name in MEASUREMENT:
                    self.assertEqual(self.section(view, name)["state"], "absent")
                for name in study_view.SECTIONS:
                    self.assertIn(name, view)

    def test_an_observational_workspace_keeps_its_sections(self) -> None:
        view = self.get(workspace(self))
        for name in MEASUREMENT:
            self.assertNotIn(name, view)
        self.assertNotIn("additional_guidelines", view["reporting"])

    def test_measurement_records_show_wherever_they_exist(self) -> None:
        root = workspace(self)
        instrument(root, "caliper-1")
        view = self.get(root)
        self.assertEqual(self.section(view, "instruments")["state"], "recorded")
        self.assertEqual(self.section(view, "measurements")["state"], "absent")

    def test_the_record_paths_are_the_measurement_core_s(self) -> None:
        self.assertEqual(study_view.MEASUREMENT_RECORDS,
                         (records.INSTRUMENTS_PATH, records.DATA_PATH, records.UNCERTAINTY_DIR, records.AGREEMENT_PATH))

    def test_the_view_carries_no_server_label_to_translate(self) -> None:
        root = workspace(self, "hardware")
        measurement_records(root)
        self.assertEqual(self.get(root, "/api/study?lang=es"), self.get(root))


class InstrumentsTests(MeasurementCase):
    def test_every_instrument_with_its_calibration_today(self) -> None:
        root = workspace(self, "hardware")
        instrument(root, "caliper-1")
        instrument(root, "gauge-2", calibrated="2020-01-01", due="2020-12-31")
        part = self.section(self.get(root), "instruments")
        rows = {row["id"]: row for row in part["instruments"]}
        self.assertEqual(sorted(rows), ["caliper-1", "gauge-2"])
        caliper = rows["caliper-1"]
        self.assertEqual((caliper["model"], caliper["serial"], caliper["calibration_certificate"]),
                         ("Mitutoyo <500>", "S-caliper-1", "CERT <9>"))
        self.assertEqual(caliper["resolution"], {"value": 0.01, "unit": "mm"})
        self.assertEqual(caliper["stated_uncertainty"],
                         {"value": 0.02, "unit": "mm", "distribution": "normal", "coverage_k": 2.0})
        self.assertEqual((caliper["calibrated"], caliper["due"], caliper["calibration"]),
                         ("2026-01-10", "2099-01-10", "current"))
        self.assertEqual((caliper["by"], caliper["entries"]), ("Ana Ruiz", 1))
        self.assertEqual(rows["gauge-2"]["calibration"], "past-due")
        self.assertEqual(part["past_due"], ["gauge-2"])
        self.assertRegex(part["on"], r"^\d{4}-\d{2}-\d{2}$")

    def test_a_corrupt_record_turns_only_its_section_unavailable(self) -> None:
        root = workspace(self, "hardware")
        measurement_records(root)
        write(root, "study/instruments.json", "{")
        view = self.get(root)
        self.assertEqual((view["instruments"]["available"], view["instruments"]["code"]),
                         (False, "INSTRUMENTS_CORRUPT"))
        self.assertTrue(view["measurements"]["available"])
        self.assertTrue(view["protocol"]["available"])


class DataFilesTests(MeasurementCase):
    def test_registered_files_without_a_value(self) -> None:
        root = workspace(self, "hardware")
        instrument(root, "caliper-1")
        lengths(root)
        files = self.section(self.get(root), "measurements")["files"]
        self.assertEqual(len(files), 1)
        entry = files[0]
        self.assertEqual((entry["path"], entry["quantity"], entry["unit"], entry["instrument"], entry["rows"]),
                         ("data/length.csv", "length", "mm", "caliper-1", 4))
        self.assertEqual((entry["conditions"], entry["state"], entry["by"]),
                         ({"temperature": "20 C"}, "current", "Ana Ruiz"))

    def test_a_changed_file_is_stated(self) -> None:
        root = workspace(self, "hardware")
        instrument(root, "caliper-1")
        lengths(root).write_text("replicate,length\nr0,1\nr1,2\n", encoding="utf-8")
        self.assertEqual(self.section(self.get(root), "measurements")["files"][0]["state"], "changed")


class UncertaintyTests(MeasurementCase):
    def test_the_budget_its_components_and_its_result(self) -> None:
        root = workspace(self, "lab-simulation")
        instrument(root, "caliper-1")
        lengths(root)
        cli(MEASURE, root, "uncertainty", "compute", "--quantity", "length", "--sensitivity", "resolution=1.5")
        stored = json.loads((root / "study/uncertainty/length.json").read_text(encoding="utf-8"))["budgets"][0]
        part = self.section(self.get(root), "uncertainty")
        self.assertEqual(part["state"], "recorded")
        budget = part["budgets"][0]
        self.assertEqual((budget["quantity"], budget["unit"], budget["conditions"], budget["state"]),
                         ("length", "mm", {"temperature": "20 C"}, "current"))
        self.assertEqual(budget["reasons"], [])
        self.assertEqual([(c["name"], c["type"]) for c in budget["components"]],
                         [("repeatability", "A"), ("calibration", "B"), ("resolution", "B")])
        self.assertEqual([c["sensitivity"] for c in budget["components"]], [1.0, 1.0, 1.5])
        for got, kept in zip(budget["components"], stored["components"]):
            self.assertEqual((got["u"], got["dof"], got["contribution"], got["unit"], got["source"]),
                             (kept["u"], kept["dof"], kept["contribution"], kept["unit"], kept["source"]))
        self.assertEqual(budget["combined_standard_uncertainty"], stored["combined_standard_uncertainty"])
        self.assertEqual(budget["effective_dof"], stored["effective_dof"])
        self.assertEqual(budget["expanded_uncertainty"], stored["expanded_uncertainty"])
        self.assertEqual(budget["coverage"], stored["coverage"])
        self.assertEqual((budget["coverage"]["method"], budget["coverage"]["level"]), ("student-t", 0.95))
        self.assertEqual((budget["n"], budget["mean"]), (4, stored["type_a"]["mean"]))
        self.assertEqual((budget["method"], budget["calibration"]["state"], budget["calibration"]["override"]),
                         ("JCGM 100:2008 (GUM)", "current", None))

    def test_a_changed_input_makes_the_budget_stale_and_says_why(self) -> None:
        root = workspace(self, "hardware")
        measurement_records(root)
        (root / "data/length.csv").write_text("replicate,length\nr0,1\nr1,2\n", encoding="utf-8")
        budget = self.section(self.get(root), "uncertainty")["budgets"][0]
        self.assertEqual((budget["state"], budget["reasons"]), ("stale", ["input-changed"]))

    def test_a_past_due_override_names_who_authorized_it(self) -> None:
        root = workspace(self, "hardware")
        instrument(root, "caliper-1", calibrated="2020-01-01", due="2020-12-31")
        lengths(root)
        cli(MEASURE, root, "uncertainty", "compute", "--quantity", "length", "--allow-past-due", "--by", "Ana Ruiz",
            "--reason", "Checked against a <gauge> block")
        calibration = self.section(self.get(root), "uncertainty")["budgets"][0]["calibration"]
        self.assertEqual(calibration["state"], "past-due")
        self.assertEqual((calibration["override"]["by"], calibration["override"]["reason"]),
                         ("Ana Ruiz", "Checked against a <gauge> block"))

    def test_a_corrupt_budget_file_is_named_and_the_rest_answer(self) -> None:
        root = workspace(self, "hardware")
        measurement_records(root)
        write(root, "study/uncertainty/mass.json", "[")
        budgets = {b["quantity"]: b for b in self.section(self.get(root), "uncertainty")["budgets"]}
        self.assertEqual(budgets["mass"]["state"], "corrupt")
        self.assertEqual(budgets["length"]["state"], "current")


class AgreementTests(MeasurementCase):
    def test_bias_limits_and_icc_with_the_files(self) -> None:
        root = workspace(self, "hardware")
        agreement(root)
        stored = json.loads((root / "study/agreement.json").read_text(encoding="utf-8"))["analyses"][0]
        analysis = self.section(self.get(root), "agreement")["analyses"][0]
        self.assertEqual(analysis["device"], {"path": "data/device.csv", "instrument": "device-1", "value_column": "value"})
        self.assertEqual(analysis["reference"]["path"], "data/reference.csv")
        self.assertEqual((analysis["quantity"], analysis["unit"], analysis["n"], analysis["pair_column"]),
                         ("force", "N", 4, "pair"))
        self.assertEqual(analysis["bland_altman"], stored["bland_altman"])
        self.assertEqual((analysis["icc"]["form"], analysis["icc"]["value"]), ("ICC(2,1)", stored["icc"]["value"]))
        self.assertEqual((analysis["state"], analysis["reasons"]), ("current", []))

    def test_a_changed_device_file_makes_it_stale(self) -> None:
        root = workspace(self, "hardware")
        agreement(root).write_text("pair,value\np0,1\np1,2\np2,3\n", encoding="utf-8")
        analysis = self.section(self.get(root), "agreement")["analyses"][0]
        self.assertEqual((analysis["state"], analysis["reasons"]), ("stale", ["device-changed"]))


class NoRawValueTests(MeasurementCase):
    def test_no_measured_value_ever_reaches_the_view(self) -> None:
        root = workspace(self, "hardware")
        measurement_records(root)
        text = TestClient(server.create_app(root)).get("/api/study").text
        self.assertIn('"agreement"', text)
        for value in RAW:
            with self.subTest(value=value):
                self.assertNotIn(value, text)
        self.assertNotIn("unpaired", text)


class ModuleTests(MeasurementCase):
    def test_a_missing_measurement_module_says_why_in_its_sections(self) -> None:
        root = workspace(self, "hardware")
        original = study_view.MEASUREMENT_MODULE
        study_view.MEASUREMENT_MODULE = "measurement.no_such_module"
        self.addCleanup(setattr, study_view, "MEASUREMENT_MODULE", original)
        view = self.get(root)
        for name in MEASUREMENT:
            with self.subTest(section=name):
                self.assertEqual((view[name]["available"], view[name]["code"]), (False, study_view.MODULE_UNAVAILABLE))
        self.assertTrue(any("measurement.no_such_module" in w for w in view["warnings"]), view["warnings"])
        self.assertTrue(view["protocol"]["available"])


class ReportingTests(MeasurementCase):
    def test_hardware_names_hardwarex_and_gum_reporting(self) -> None:
        root = workspace(self, "hardware")
        agree(root, None, "hardware")
        reporting = self.section(self.get(root), "reporting")
        self.assertEqual((reporting["type"], reporting["variant"], reporting["guideline"], reporting["code"]),
                         ("hardware", None, "hardwarex", None))
        self.assertEqual(reporting["additional_guidelines"], ["gum-reporting"])

    def test_lab_simulation_names_gum_reporting_through_its_variant(self) -> None:
        root = workspace(self, "lab-simulation")
        agree(root, "materials", "lab-simulation")
        reporting = self.section(self.get(root), "reporting")
        self.assertEqual((reporting["variant"], reporting["guideline"]), ("materials", "gum-reporting"))
        self.assertNotIn("additional_guidelines", reporting)

    def test_lab_simulation_without_a_variant_still_names_its_line_guideline(self) -> None:
        root = workspace(self, "lab-simulation")
        agree(root, None, "lab-simulation")
        reporting = self.section(self.get(root), "reporting")
        self.assertEqual((reporting["guideline"], reporting["reason"]), (None, "variant-not-agreed"))
        self.assertEqual(reporting["additional_guidelines"], ["gum-reporting"])

    def test_the_checklist_runs_either_guideline_of_the_line(self) -> None:
        root = workspace(self, "hardware")
        agree(root, None, "hardware")
        primary = self.get(root, "/api/study/checklist")
        self.assertEqual((primary["guideline"]["id"], len(primary["items"])), ("hardwarex", 31))
        second = self.get(root, "/api/study/checklist?guideline=gum-reporting")
        self.assertEqual((second["guideline"]["id"], len(second["items"])), ("gum-reporting", 18))
        self.assertEqual(second["type"], "hardware")

    def test_a_guideline_outside_the_line_is_refused(self) -> None:
        for kind, guideline in (("hardware", "strobe"), ("observational-measurement", "gum-reporting"),
                                ("hardware", "../x")):
            with self.subTest(kind=kind, guideline=guideline):
                root = workspace(self, kind)
                response = TestClient(server.create_app(root)).get("/api/study/checklist",
                                                                   params={"guideline": guideline})
                self.assertEqual(response.status_code, 400, response.text)
                body = response.json()
                self.assertEqual((body["ok"], body["code"], body["guideline"]),
                                 (False, study_view.GUIDELINE_NOT_THIS_LINE, guideline))


if __name__ == "__main__":
    unittest.main()
