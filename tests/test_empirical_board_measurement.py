"""The empirical board's hardware and lab-simulation tables (paper-type-lines S8, T8-B1, F2, F3, F8).

A `hardware` workspace shows the twelve steps of
`src/papersmith/templates/paper-flow-hardware.md.tpl` with the gates G-SPEC
(the study protocol lock), G-CALIBRATION (every instrument the registered data
uses calibrated and not past due today, every registered quantity with a
current uncertainty budget) and G-AGREEMENT (a current agreement analysis); the
ethics, registration and participant-flow gates join only when the operator
declares a validation with people. A `lab-simulation` workspace shows the
eleven steps of `paper-flow-lab-simulation.md.tpl` with G-STUDY-PROTOCOL and
G-CALIBRATION. Every record is written through the real CLIs (`measure_cli.py`,
`study_cli.py`, `flow_cli.py`, `paper_type_cli.py`, `paper_cli.py`); the board
only reads them.
"""

from __future__ import annotations

import json
import re
import shlex
import shutil
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from papersmith.core.init import initialize
from skills._core.command_center import empirical_board, lines, localize, server
from tests import test_empirical_board as base

REPO, TABS = base.REPO, base.TABS

HARDWARE, LAB = "hardware", "lab-simulation"
HW_STEPS = ["harness", "plausibility_hardware", "specifications", "design_files", "build", "calibration",
            "agreement", "field_validation", "open_files", "writing", "paper", "reporting_hardware"]
LAB_STEPS = ["harness", "plausibility_lab", "sample_model", "lab_protocol", "observables", "known_values",
             "uncertainty", "open_data", "writing", "paper", "reporting_lab"]
HW_GATES = ["G-SPEC", "G-CALIBRATION", "G-AGREEMENT", "G1", "G2", "G3", "G4"]
HW_PEOPLE_GATES = ["G-SPEC", "G-CALIBRATION", "G-AGREEMENT", "G-ETHICS", "G-REGISTRATION", "G-FLOW",
                   "G1", "G2", "G3", "G4"]
LAB_GATES = ["G-STUDY-PROTOCOL", "G-CALIBRATION", "G1", "G2", "G3", "G4"]
MEASURE = "skills/_core/measurement/measure_cli.py"
PAPER_TYPE = "skills/_core/paper_types/paper_type_cli.py"
LENGTHS = "replicate,length\nr1,7.1183\nr2,7.1297\nr3,7.1241\nr4,7.1209\n"
DEVICE = "pair,value\np1,51.04\np2,52.45\np3,49.88\np4,50.66\n"
REFERENCE = "pair,value\np1,51.11\np2,52.34\np3,50.00\np4,50.72\n"
IDEA = ("A low-cost load cell for field force measurement, validated against a reference device. "
        "We build it, budget its uncertainty and test its agreement with a laboratory dynamometer.")

_TEMPLATES: dict[str, Path] = {}


def _template(kind: str) -> Path:
    if kind not in _TEMPLATES:
        ws = Path(tempfile.mkdtemp(prefix="b1-template-")) / "ws"
        initialize(ws, tools=("claude",), run_npm=False, run_env=False, kind=kind)
        _TEMPLATES[kind] = ws
    return _TEMPLATES[kind]


def tearDownModule() -> None:  # noqa: N802 - unittest hook
    for ws in _TEMPLATES.values():
        shutil.rmtree(ws.parent, ignore_errors=True)


class MeasurementBoardCase(base.BoardCase):
    kind = HARDWARE

    def workspace(self, kind: str | None = None) -> Path:
        holder = tempfile.TemporaryDirectory(prefix="b1-case-", ignore_cleanup_errors=True)
        self.addCleanup(holder.cleanup)
        root = Path(holder.name) / "ws"
        shutil.copytree(_template(kind or self.kind), root, symlinks=True)
        return root

    def measure(self, root: Path, *args: str, ok: bool = True) -> dict:
        return self.run_cli(root, MEASURE, *args, "--root", str(root), ok=ok)

    @staticmethod
    def write(root: Path, rel: str, text: str) -> None:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def instrument(self, root: Path, ident: str, *, unit: str = "mm", calibrated: str = "2026-01-10",
                   due: str = "2099-01-10", reason: str | None = None) -> None:
        self.measure(root, "instrument", "add", "--id", ident, "--model", "Mitutoyo 500", "--serial", f"S-{ident}",
                     "--resolution", f"0.01 {unit}", "--calibration-certificate", "CERT-9", "--calibrated",
                     calibrated, "--due", due, "--by", "Ana Ruiz", *(("--reason", reason) if reason else ()))

    def lengths(self, root: Path) -> None:
        self.write(root, "data/length.csv", LENGTHS)
        self.measure(root, "data", "register", "--file", "data/length.csv", "--quantity", "length", "--unit", "mm",
                     "--instrument", "caliper-1", "--replicate-column", "replicate", "--by", "Ana Ruiz")

    def budget(self, root: Path, *extra: str) -> None:
        self.measure(root, "uncertainty", "compute", "--quantity", "length", *extra)

    def calibrated(self, root: Path) -> None:
        """One calibrated caliper, four registered length replicates and their budget."""
        self.instrument(root, "caliper-1")
        self.lengths(root)
        self.budget(root)

    def paired(self, root: Path) -> None:
        """Device and reference readings registered (each under its own condition, so each has a budget)."""
        self.instrument(root, "device-1", unit="N")
        self.instrument(root, "ref-1", unit="N")
        self.write(root, "data/device.csv", DEVICE)
        self.write(root, "data/reference.csv", REFERENCE)
        for name, ident in (("device", "device-1"), ("reference", "ref-1")):
            self.measure(root, "data", "register", "--file", f"data/{name}.csv", "--quantity", "force", "--unit",
                         "N", "--instrument", ident, "--value-column", "value", "--condition", f"role={name}",
                         "--by", "Ana Ruiz")
            self.measure(root, "uncertainty", "compute", "--quantity", "force", "--condition", f"role={name}")

    def agreement(self, root: Path) -> None:
        self.measure(root, "agreement", "compute", "--device-file", "data/device.csv", "--reference-file",
                     "data/reference.csv", "--pair-column", "pair")

    def approved(self, root: Path) -> None:
        self.revision(root, 1)
        self.study(root, "protocol", "approve", "--by", "Ana Ruiz")

    def bench_only(self, root: Path) -> None:
        for gate in ("ethics", "registration"):
            self.study(root, gate, "record", "--by", "Ana Ruiz", "--not-applicable", "--reason",
                       "bench-only validation, no person takes part")

    def declare_repository(self, root: Path) -> None:
        tex = root / "paper" / "main.tex"
        if not tex.is_file():
            self.write(root, "paper/main.tex", "\\documentclass{article}\n\\begin{document}\n\\end{document}\n")
        self.run_cli(root, "skills/paper-writing/scripts/paper_cli.py", "declare", "--declaration", "repository-url",
                     "--value", "https://doi.org/10.5281/zenodo.1234")

    def agree(self, root: Path, type_id: str, variant: str | None = None) -> None:
        self.write(root, "idea.txt", IDEA)
        self.run_cli(root, PAPER_TYPE, "accept", "--root", str(root), "--by", "Ana Ruiz", "--idea-file",
                     str(root / "idea.txt"))
        self.run_cli(root, PAPER_TYPE, "agree", "--root", str(root), "--type", type_id,
                     *(("--variant", variant) if variant else ()), "--by", "Ana Ruiz")

    def gate_ids(self, status: dict) -> list[str]:
        return [g["id"] for g in status["gates"]]


# --------------------------------------------------------------------------- hardware


class HardwareStepsTests(MeasurementBoardCase):
    def test_the_board_shows_the_twelve_steps_of_the_flow(self) -> None:
        self.assertTrue(lines.registered(HARDWARE))
        status = self.status(self.workspace())
        self.assertEqual(status["paper_kind"], HARDWARE)
        self.assertNotIn("board_notice", status)
        self.assertEqual([f["stage_id"] for f in status["fases"]], HW_STEPS)
        self.assertEqual(self.gate_ids(status), HW_GATES)
        for gate in HW_GATES[:3]:
            with self.subTest(gate=gate):
                self.assertEqual(self.gate(status, gate)["status"], "PENDING")
                self.assertEqual(self.gate(status, gate)["reviewer"], "operator")
        self.assertEqual(self.gate(status, "G-SPEC")["phase"], "Fase 3")
        self.assertEqual(self.gate(status, "G-CALIBRATION")["phase"], "Fase 6")
        self.assertEqual(self.gate(status, "G-AGREEMENT")["phase"], "Fase 7")
        self.assertEqual(self.phase(status, "specifications")["name"], "Phase 3: Requirements & Specifications (G-SPEC)")
        for stage in HW_STEPS:
            with self.subTest(stage=stage):
                phase = self.phase(status, stage)
                self.assertTrue(phase["actions"])
                self.assertTrue(phase["evidence"])
                self.assertTrue(phase["subfases"])

    def test_the_steps_follow_the_flow_template(self) -> None:
        flow = (REPO / "src/papersmith/templates/paper-flow-hardware.md.tpl").read_text(encoding="utf-8")
        self.assertEqual(len(re.findall(r"^\s*(\d+)\. \*\*", flow, re.M)), len(HW_STEPS))
        self.assertEqual(list(empirical_board.LINE_TABLES[HARDWARE].steps), HW_STEPS)

    def test_the_flow_diagram_is_the_line_s_own(self) -> None:
        self.assertEqual(lines.board(HARDWARE).flow_html, "papersmith-hardware-flow.html")
        self.assertEqual(TestClient(server.create_app(self.workspace())).get("/api/flow").status_code, 200)

    def test_the_agreed_hardware_type_passes_step_two(self) -> None:
        root = self.workspace()
        self.agree(root, HARDWARE)
        step = self.phase(self.status(root), "plausibility_hardware")
        self.assertEqual(step["status"], "PASS", step["detail"])
        self.assertIn("Paper type hardware agreed by Ana Ruiz", step["detail"])


class HardwareGateTests(MeasurementBoardCase):
    def test_g_spec_is_the_protocol_lock_absent_current_and_stale(self) -> None:
        root = self.workspace()
        self.assertEqual(self.phase(self.status(root), "specifications")["status"], "PENDING")
        self.revision(root, 1)
        step = self.phase(self.status(root), "specifications")
        self.assertEqual(step["status"], "ACTIVE")
        self.assertIn("G-SPEC", step["detail"])
        self.study(root, "protocol", "approve", "--by", "Ana Ruiz")
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-SPEC")["status"], "PASS")
        self.assertEqual(self.phase(status, "specifications")["status"], "PASS")
        self.assertIn("Ana Ruiz", self.phase(status, "specifications")["detail"])
        self.revision(root, 1, extra="\nEdited after the signature.\n")
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-SPEC")["status"], "ACTIVE")
        self.assertIn("amendment", self.phase(status, "specifications")["detail"])

    def test_g_calibration_absent_current_and_stale(self) -> None:
        root = self.workspace()
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-CALIBRATION")["status"], "PENDING")
        self.assertIn("No instrument recorded yet", self.phase(status, "calibration")["detail"])
        self.instrument(root, "caliper-1")
        self.lengths(root)
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-CALIBRATION")["status"], "ACTIVE")
        self.assertIn("No current uncertainty budget for length", self.phase(status, "calibration")["detail"])
        self.budget(root)
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-CALIBRATION")["status"], "PASS",
                         self.phase(status, "calibration")["detail"])
        self.assertEqual(self.phase(status, "calibration")["status"], "PASS")
        # A registered data file changes: its budget is stale.
        self.write(root, "data/length.csv", LENGTHS + "r5,7.1222\n")
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-CALIBRATION")["status"], "ACTIVE")
        detail = self.phase(status, "calibration")["detail"]
        self.assertIn("The uncertainty budget of length is stale", detail)
        self.assertIn("input-changed", detail)

    def test_a_past_due_calibration_holds_the_gate(self) -> None:
        root = self.workspace()
        self.instrument(root, "caliper-1", calibrated="2020-01-10", due="2021-01-10")
        self.lengths(root)
        # The operator's override computes the budget; the instrument stays past due today.
        self.budget(root, "--allow-past-due", "--by", "Ana Ruiz", "--reason", "readings checked against a gauge block")
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-CALIBRATION")["status"], "ACTIVE")
        self.assertIn("Instrument caliper-1 is past its calibration due date (2021-01-10)",
                      self.phase(status, "calibration")["detail"])
        self.instrument(root, "caliper-1", calibrated="2026-02-01", due="2099-02-01", reason="recalibrated")
        status = self.status(root)
        # The new calibration changes the instrument record the budget used: recompute it.
        self.assertIn("instrument-changed", self.phase(status, "calibration")["detail"])
        self.budget(root)
        self.assertEqual(self.gate(self.status(root), "G-CALIBRATION")["status"], "PASS")

    def test_g_agreement_absent_current_and_stale(self) -> None:
        root = self.workspace()
        self.assertEqual(self.gate(self.status(root), "G-AGREEMENT")["status"], "PENDING")
        self.paired(root)
        self.agreement(root)
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-AGREEMENT")["status"], "PASS")
        step = self.phase(status, "agreement")
        self.assertEqual(step["status"], "PASS")
        self.assertIn("data/device.csv with data/reference.csv current (4 pairs)", step["detail"])
        self.write(root, "data/device.csv", DEVICE + "p5,50.10\n")
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-AGREEMENT")["status"], "ACTIVE")
        self.assertIn("device-changed", self.phase(status, "agreement")["detail"])

    def test_design_files_read_the_repository_url_declaration(self) -> None:
        root = self.workspace()
        step = self.phase(self.status(root), "design_files")
        self.assertEqual(step["status"], "PENDING")
        self.assertIn("repository-url", step["detail"])
        self.declare_repository(root)
        status = self.status(root)
        self.assertEqual(self.phase(status, "design_files")["status"], "PASS")
        self.assertIn("https://doi.org/10.5281/zenodo.1234", self.phase(status, "design_files")["detail"])
        self.assertEqual(self.phase(status, "open_files")["subfases"][1]["status"], "PASS")

    def test_build_and_open_files_read_the_registered_raw_files(self) -> None:
        root = self.workspace()
        status = self.status(root)
        self.assertEqual(self.phase(status, "build")["status"], "PENDING")
        self.assertEqual(self.phase(status, "open_files")["status"], "PENDING")
        self.instrument(root, "caliper-1")
        self.lengths(root)
        status = self.status(root)
        self.assertEqual(self.phase(status, "build")["status"], "PASS")
        self.assertEqual(self.phase(status, "open_files")["status"], "PASS")
        self.write(root, "data/length.csv", LENGTHS + "r5,7.1222\n")
        step = self.phase(self.status(root), "open_files")
        self.assertEqual(step["status"], "ACTIVE")
        self.assertIn("data/length.csv changed since its registration", step["detail"])


class FieldValidationTests(MeasurementBoardCase):
    def test_no_validation_declared_yet(self) -> None:
        root = self.workspace()
        self.approved(root)
        status = self.status(root)
        step = self.phase(status, "field_validation")
        self.assertEqual(step["status"], "PENDING")
        self.assertIn("No validation declared yet", step["detail"])
        self.assertEqual(self.gate_ids(status), HW_GATES)

    def test_a_bench_only_validation_passes_without_the_people_gates(self) -> None:
        root = self.workspace()
        self.approved(root)
        self.bench_only(root)
        status = self.status(root)
        step = self.phase(status, "field_validation")
        self.assertEqual(step["status"], "PASS", step["detail"])
        self.assertIn("Bench-only validation", step["detail"])
        self.assertEqual(self.gate_ids(status), HW_GATES)

    def test_a_validation_with_people_brings_the_ethics_registration_and_flow_gates(self) -> None:
        root = self.workspace()
        self.approved(root)
        self.study(root, "ethics", "record", "--by", "Ana Ruiz", "--committee", "University IRB", "--code",
                   "IRB-7", "--date", "2026-02-10", "--consent", "written consent of each user")
        status = self.status(root)
        self.assertEqual(self.gate_ids(status), HW_PEOPLE_GATES)
        self.assertEqual(self.gate(status, "G-ETHICS")["status"], "PASS")
        self.assertEqual(self.gate(status, "G-ETHICS")["phase"], "Fase 8")
        self.assertEqual(self.gate(status, "G-FLOW")["status"], "PENDING")
        step = self.phase(status, "field_validation")
        self.assertEqual(step["status"], "ACTIVE")
        self.assertIn("1 of 3 operator records current", step["detail"])
        self.study(root, "registration", "record", "--by", "Ana Ruiz", "--not-applicable", "--reason",
                   "usability study, no registry applies")
        self.flow(root, "template", "strobe", "--write")
        flow = json.loads((root / "study" / "flow.json").read_text(encoding="utf-8"))
        for stage in flow["stages"].values():
            stage["n"] = 12
        (root / "study" / "flow.json").write_text(json.dumps(flow), encoding="utf-8")
        self.flow(root, "render")
        self.flow(root, "signoff", "--by", "Ana Ruiz")
        step = self.phase(self.status(root), "field_validation")
        self.assertEqual(step["status"], "PASS", step["detail"])


class HardwareLockTests(MeasurementBoardCase):
    def test_the_phase_gates_of_the_line(self) -> None:
        board = lines.board(HARDWARE)
        self.assertEqual(dict(board.phase_gates), {"agreement": "G-CALIBRATION", "writing": "G-AGREEMENT"})
        self.assertEqual(board.transversal, "reporting_hardware")
        self.assertIn("calibration", board.ungated)

    def test_agreement_waits_for_the_calibration(self) -> None:
        root = self.workspace()
        agreement = self.phase(self.status(root), "agreement")
        self.assertFalse(agreement["unlocked"])
        compute = next(a for a in agreement["actions"] if "agreement compute" in a.get("command", ""))
        self.assertTrue(compute["locked"])
        self.assertEqual(compute["requires"], "G-CALIBRATION")
        self.calibrated(root)
        agreement = self.phase(self.status(root), "agreement")
        self.assertTrue(agreement["unlocked"], agreement["blocked_by"])
        compute = next(a for a in agreement["actions"] if "agreement compute" in a.get("command", ""))
        self.assertFalse(compute["locked"])

    def test_writing_waits_for_the_agreement(self) -> None:
        root = self.workspace()
        self.calibrated(root)
        self.paired(root)
        writing = self.phase(self.status(root), "writing")
        self.assertFalse(writing["unlocked"])
        self.assertEqual(writing["blocked_by"], "G-AGREEMENT")
        self.agreement(root)
        writing = self.phase(self.status(root), "writing")
        self.assertTrue(writing["unlocked"], writing["blocked_by"])


# --------------------------------------------------------------------------- lab-simulation


class LabTests(MeasurementBoardCase):
    kind = LAB

    def test_the_board_shows_the_eleven_steps_of_the_flow(self) -> None:
        self.assertTrue(lines.registered(LAB))
        status = self.status(self.workspace())
        self.assertEqual(status["paper_kind"], LAB)
        self.assertNotIn("board_notice", status)
        self.assertEqual([f["stage_id"] for f in status["fases"]], LAB_STEPS)
        self.assertEqual(self.gate_ids(status), LAB_GATES)
        self.assertEqual(self.gate(status, "G-STUDY-PROTOCOL")["phase"], "Fase 4")
        self.assertEqual(self.gate(status, "G-CALIBRATION")["phase"], "Fase 7")
        flow = (REPO / "src/papersmith/templates/paper-flow-lab-simulation.md.tpl").read_text(encoding="utf-8")
        self.assertEqual(len(re.findall(r"^\s*(\d+)\. \*\*", flow, re.M)), len(LAB_STEPS))
        for stage in LAB_STEPS:
            with self.subTest(stage=stage):
                phase = self.phase(status, stage)
                self.assertTrue(phase["actions"])
                self.assertTrue(phase["evidence"])
                self.assertTrue(phase["subfases"])
        self.assertEqual(TestClient(server.create_app(self.workspace())).get("/api/flow").status_code, 200)

    def test_the_steps_read_the_protocol_the_data_the_calibration_and_the_budgets(self) -> None:
        root = self.workspace()
        status = self.status(root)
        for stage in ("sample_model", "lab_protocol", "observables", "known_values", "uncertainty"):
            self.assertEqual(self.phase(status, stage)["status"], "PENDING", stage)
        self.revision(root, 1)
        self.assertEqual(self.phase(self.status(root), "sample_model")["status"], "PASS")
        self.study(root, "protocol", "approve", "--by", "Ana Ruiz")
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-STUDY-PROTOCOL")["status"], "PASS")
        self.assertEqual(self.phase(status, "lab_protocol")["status"], "PASS")
        self.instrument(root, "caliper-1")
        self.lengths(root)
        status = self.status(root)
        self.assertEqual(self.phase(status, "observables")["status"], "PASS")
        self.assertEqual(self.phase(status, "known_values")["status"], "PASS",
                         self.phase(status, "known_values")["detail"])
        self.assertEqual(self.gate(status, "G-CALIBRATION")["status"], "ACTIVE")
        self.assertEqual(self.phase(status, "uncertainty")["status"], "ACTIVE")
        self.budget(root)
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-CALIBRATION")["status"], "PASS")
        self.assertEqual(self.phase(status, "uncertainty")["status"], "PASS",
                         self.phase(status, "uncertainty")["detail"])
        self.write(root, "data/length.csv", LENGTHS + "r5,7.1222\n")
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-CALIBRATION")["status"], "ACTIVE")
        self.assertEqual(self.phase(status, "observables")["status"], "ACTIVE")

    def test_a_past_due_instrument_holds_the_known_values_step(self) -> None:
        root = self.workspace()
        self.instrument(root, "caliper-1", calibrated="2020-01-10", due="2021-01-10")
        self.lengths(root)
        step = self.phase(self.status(root), "known_values")
        self.assertEqual(step["status"], "ACTIVE")
        self.assertIn("past its calibration due date", step["detail"])

    def test_the_locks_of_the_line(self) -> None:
        board = lines.board(LAB)
        self.assertEqual(dict(board.phase_gates), {"writing": "G-CALIBRATION"})
        self.assertEqual(board.transversal, "reporting_lab")
        root = self.workspace()
        self.approved(root)
        self.instrument(root, "caliper-1", calibrated="2020-01-10", due="2021-01-10")
        self.lengths(root)
        # The analysis (uncertainty) step waits for the calibration against known values.
        uncertainty = self.phase(self.status(root), "uncertainty")
        self.assertFalse(uncertainty["unlocked"])
        self.assertEqual(uncertainty["blocked_by"], "Fase 6")
        self.instrument(root, "caliper-1", calibrated="2026-02-01", due="2099-02-01", reason="recalibrated")
        status = self.status(root)
        self.assertTrue(self.phase(status, "uncertainty")["unlocked"])
        # The writing waits for current budgets.
        writing = self.phase(status, "writing")
        self.assertFalse(writing["unlocked"])
        self.assertEqual(writing["blocked_by"], "G-CALIBRATION")
        self.budget(root)
        writing = self.phase(self.status(root), "writing")
        self.assertTrue(writing["unlocked"], writing["blocked_by"])


# --------------------------------------------------------------------------- checklists


class ChecklistTests(MeasurementBoardCase):
    def checklists(self, root: Path, stage: str) -> list[dict]:
        return self.phase(self.status(root), stage)["subfases"]

    def test_hardware_names_hardwarex_from_the_family_and_gum_reporting(self) -> None:
        root = self.workspace()
        subs = self.checklists(root, "reporting_hardware")
        self.assertEqual(subs[0]["name"], "Reporting checklist")
        self.assertIn("No paper type agreed yet", subs[0]["detail"])
        self.assertEqual(subs[1]["name"], "Reporting checklist (gum-reporting)")
        self.agree(root, HARDWARE)
        self.assertEqual(empirical_board.agreed_type(root)["checklist"], "hardwarex")
        subs = self.checklists(root, "reporting_hardware")
        self.assertEqual(subs[0]["name"], "Reporting checklist (hardwarex)")
        self.assertIn("--guideline hardwarex", subs[0]["detail"])
        self.assertIn("HardwareX", subs[0]["detail"])
        self.assertEqual(subs[1]["name"], "Reporting checklist (gum-reporting)")
        self.assertIn("--guideline gum-reporting", subs[1]["detail"])
        self.assertEqual(subs[2]["name"], "Workspace audit (smith audit .)")

    def test_lab_simulation_names_the_variants_gum_reporting(self) -> None:
        root = self.workspace(LAB)
        self.assertIn("No variant agreed yet", self.checklists(root, "reporting_lab")[0]["detail"])
        self.agree(root, LAB, "materials")
        subs = self.checklists(root, "reporting_lab")
        self.assertEqual(subs[0]["name"], "Reporting checklist (gum-reporting)")
        self.assertEqual([s["name"] for s in subs][1:], ["Workspace audit (smith audit .)"])


# --------------------------------------------------------------------------- read-only, cards, Spanish


class ReadOnlyAndCardTests(MeasurementBoardCase):
    def test_the_board_never_writes_a_record(self) -> None:
        root = self.workspace()
        self.approved(root)
        self.bench_only(root)
        self.calibrated(root)
        self.paired(root)
        self.agreement(root)
        self.declare_repository(root)
        watched = ["study", "protocol", "analysis", "data", "paper/main.tex", ".papersmith/paper_type.json"]

        def snapshot() -> dict:
            out = {}
            for rel in watched:
                base = root / rel
                paths = [base] if base.is_file() else sorted(p for p in base.rglob("*") if p.is_file())
                out.update({p.relative_to(root).as_posix(): p.read_bytes() for p in paths})
            return out

        before = snapshot()
        self.assertIn("study/uncertainty/length.json", before)
        self.status(root)
        self.status(root, "es")
        self.assertEqual(snapshot(), before)

    def test_every_card_runs_a_real_command(self) -> None:
        clis = {
            "python skills/_core/empirical/study_cli.py": "skills/_core/empirical/study_cli.py",
            "python skills/_core/empirical/analysis_cli.py": "skills/_core/empirical/analysis_cli.py",
            "python skills/_core/participant_flow/flow_cli.py": "skills/_core/participant_flow/flow_cli.py",
            "python skills/_core/checklists/checklist_cli.py": "skills/_core/checklists/checklist_cli.py",
            "python skills/_core/measurement/measure_cli.py": "skills/_core/measurement/measure_cli.py",
            "python skills/paper-writing/scripts/paper_cli.py": "skills/paper-writing/scripts/paper_cli.py",
        }
        for kind in (HARDWARE, LAB):
            root = self.workspace(kind)
            board = lines.board(kind)
            for stage in board.stages:
                for action in board.actions[stage]["actions"]:
                    with self.subTest(kind=kind, stage=stage, action=action["label"]):
                        if action["kind"] == "prompt":
                            self.assertTrue(action["guide"])
                            name = action["slash"].lstrip("/")
                            self.assertTrue((root / ".claude" / "commands" / f"{name}.md").is_file(), name)
                        elif action["kind"] == "redirect":
                            self.assertIn(action["tab"], TABS)
                        else:
                            words = shlex.split(action["command"])
                            if words[0] == "smith":
                                self.assertIn(words[1], {"status", "audit"})
                                continue
                            prefix = " ".join(words[:2])
                            self.assertIn(prefix, clis)
                            self.assertEqual(base.CardTests._parse(root / clis[prefix], words[2:]), "parsed",
                                             action["command"])
            self.assertEqual(set(board.actions), set(board.stages))
            self.assertEqual(set(board.evidence), set(board.stages))

    def test_every_operator_record_names_the_operator(self) -> None:
        for kind in (HARDWARE, LAB):
            board = lines.board(kind)
            commands = [a["command"] for stage in board.stages for a in board.actions[stage]["actions"]
                        if a["kind"] == "command" and re.search(r" (approve|amend|record|signoff|add|register) ",
                                                                a["command"])]
            self.assertTrue(commands)
            for command in commands:
                with self.subTest(kind=kind, command=command):
                    self.assertRegex(command, r'--by "<operator name>"')

    def test_a_broken_workspace_measurement_module_falls_back_visibly(self) -> None:
        root = self.workspace()
        self.calibrated(root)
        broken = root / "skills" / "_core" / "measurement" / "records.py"
        broken.write_text("def broken(:\n", encoding="utf-8")
        status = self.status(root)
        step = self.phase(status, "calibration")
        self.assertEqual(step["status"], "PASS")
        self.assertIn("the workspace's records.py did not load (SyntaxError", step["detail"])
        self.assertEqual(self.spanish_gaps(status), [])


class SpanishTests(MeasurementBoardCase):
    def test_every_hardware_label_has_a_spanish_entry(self) -> None:
        root = self.workspace()
        states = {
            "empty": lambda: None,
            "revision": lambda: self.revision(root, 1),
            "approved": lambda: self.study(root, "protocol", "approve", "--by", "Ana Ruiz"),
            "agreed": lambda: self.agree(root, HARDWARE),
            "instrument": lambda: (self.instrument(root, "caliper-1"), self.lengths(root)),
            "budget": lambda: self.budget(root),
            "paired": lambda: self.paired(root),
            "agreement": lambda: self.agreement(root),
            "people": lambda: self.study(root, "ethics", "record", "--by", "Ana Ruiz", "--committee", "IRB", "--code",
                                         "IRB-7", "--date", "2026-02-10", "--consent", "written"),
            "declared": lambda: self.declare_repository(root),
            "stale": lambda: (self.write(root, "data/length.csv", LENGTHS + "r5,7.1222\n"),
                              self.write(root, "data/device.csv", DEVICE + "p5,50.10\n"),
                              self.revision(root, 1, extra="\nEdited.\n")),
            "past due": lambda: self.instrument(root, "caliper-1", calibrated="2020-01-10", due="2021-01-10",
                                                reason="certificate re-read"),
        }
        for name, step in states.items():
            step()
            with self.subTest(state=name):
                self.assertEqual(self.spanish_gaps(self.status(root)), [])

    def test_every_lab_label_has_a_spanish_entry(self) -> None:
        root = self.workspace(LAB)
        states = {
            "empty": lambda: None,
            "revision": lambda: self.revision(root, 1),
            "approved": lambda: self.study(root, "protocol", "approve", "--by", "Ana Ruiz"),
            "bench": lambda: self.bench_only(root),
            "data": lambda: (self.instrument(root, "caliper-1"), self.lengths(root)),
            "budget": lambda: self.budget(root),
            "agreed": lambda: self.agree(root, LAB, "modelling-simulation"),
            "stale": lambda: self.write(root, "data/length.csv", LENGTHS + "r5,7.1222\n"),
        }
        for name, step in states.items():
            step()
            with self.subTest(state=name):
                self.assertEqual(self.spanish_gaps(self.status(root)), [])

    def test_the_new_texts_have_exact_entries(self) -> None:
        catalogue = json.loads(localize.CATALOGUE.read_text(encoding="utf-8"))
        for kind in (HARDWARE, LAB):
            table = empirical_board.LINE_TABLES[kind]
            for stage in table.steps:
                step = empirical_board.STEPS[stage]
                with self.subTest(kind=kind, stage=stage):
                    self.assertIn(f"Phase {{n}}: {step.title}", catalogue)
                    self.assertIn(step.label, catalogue)
                    self.assertIn(step.desc, catalogue)
            for gate in table.gates:
                self.assertIn(empirical_board.GATES[gate].criteria, catalogue)
            for label in lines.board(kind).labels.values():
                self.assertIsNotNone(localize.lookup(f"Phase 4 — {label}"))


class OtherBoardsTests(unittest.TestCase):
    def test_the_observational_table_is_unchanged(self) -> None:
        table = empirical_board.LINE_TABLES["observational-measurement"]
        self.assertEqual(table.steps, ("harness", "plausibility_type", "study_protocol", "ethics_registration",
                                       "data", "analysis", "participant_flow", "writing", "paper",
                                       "reporting_audit"))
        self.assertEqual(dict(table.phase_gates), {"analysis": "G-DATA-QC", "writing": "G-FLOW"})
        self.assertEqual(table.extra_checklists, ())
        self.assertFalse(table.conditional_gates)


if __name__ == "__main__":
    unittest.main()
