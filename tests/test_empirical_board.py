"""The command center's board for the empirical lines (paper-type-lines S8, T8-O4, E5, E8).

An observational-measurement workspace (`smith init --kind
observational-measurement`) shows the ten steps of its flow
(`src/papersmith/templates/paper-flow-observational-measurement.md.tpl`), each
read from the study's records on disk, with the gates G-STUDY-PROTOCOL,
G-ETHICS, G-REGISTRATION, G-DATA-QC and G-FLOW. Every record here is written
through the real CLIs (`study_cli.py`, `datasets_cli.py`, `analysis_cli.py`,
`flow_cli.py`, `paper_type_cli.py`), as an operator would; the board only
reads them and never passes a gate on the operator's behalf. The experimental
and review boards are pinned by their own tests.
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from papersmith.core.init import initialize
from skills._core.command_center import empirical_board, lines, localize, server

REPO = Path(__file__).resolve().parents[1]
KIND = "observational-measurement"
PAGE = (REPO / "skills/_core/command_center/static/index.html").read_text(encoding="utf-8")
TABS = set(re.findall(r"onclick=\"navigateTab\('([a-z]+)'\)\"", PAGE))
STEPS = ["harness", "plausibility_type", "study_protocol", "ethics_registration", "data", "analysis",
         "participant_flow", "writing", "paper", "reporting_audit"]
GATES = ["G-STUDY-PROTOCOL", "G-ETHICS", "G-REGISTRATION", "G-DATA-QC", "G-FLOW", "G1", "G2", "G3", "G4"]
MARKER = "<!-- proposal-workspace:artifact:v1 -->\n"
FIELDS = """
**Research question:** Do wildfire smoke episodes raise asthma admissions?

**Primary outcome:** O1 -- weekly asthma admissions; time point: 2 weeks after an episode

**Secondary outcome:** O2 -- emergency visits; time point: 2 weeks

**Primary model:** Poisson regression of weekly admissions on smoke exposure

**Covariates:** none

**Missing data:** complete cases

**Multiplicity:** not applicable
"""
DATA = "patient_name,age,admissions\nAna,34,2\nLuis,51,1\n"
IDEA = ("Hospital admissions for asthma rise after wildfire smoke episodes. We hold five years of weekly "
        "admissions and air-quality records from the regional hospital network.")

_TEMPLATE: dict[str, Path] = {}


def _template() -> Path:
    """One initialized observational-measurement workspace, copied by each test."""
    if "ws" not in _TEMPLATE:
        ws = Path(tempfile.mkdtemp(prefix="o4-template-")) / "ws"
        initialize(ws, tools=("claude",), run_npm=False, run_env=False, kind=KIND)
        _TEMPLATE["ws"] = ws
    return _TEMPLATE["ws"]


def tearDownModule() -> None:  # noqa: N802 - unittest hook
    for ws in _TEMPLATE.values():
        shutil.rmtree(ws.parent, ignore_errors=True)


class BoardCase(unittest.TestCase):
    def workspace(self) -> Path:
        holder = tempfile.TemporaryDirectory(prefix="o4-case-", ignore_cleanup_errors=True)
        self.addCleanup(holder.cleanup)
        root = Path(holder.name) / "ws"
        shutil.copytree(_template(), root, symlinks=True)
        return root

    def status(self, root: Path, lang: str = "") -> dict:
        response = TestClient(server.create_app(root)).get("/api/status" + (f"?lang={lang}" if lang else ""))
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def run_cli(self, root: Path, script: str, *args: str, ok: bool = True) -> dict:
        proc = subprocess.run([sys.executable, str(root / script), *args], capture_output=True, text=True,
                              cwd=str(root), timeout=120)
        text = proc.stdout.strip() or proc.stderr.strip()
        payload = json.loads(text)
        if ok:
            self.assertEqual(proc.returncode, 0, text)
        return payload

    def study(self, root: Path, *args: str) -> dict:
        return self.run_cli(root, "skills/_core/empirical/study_cli.py", *args, "--root", str(root))

    def datasets(self, root: Path, *args: str) -> dict:
        return self.run_cli(root, "skills/datasets/scripts/datasets_cli.py", "--root", str(root), *args)

    def flow(self, root: Path, *args: str) -> dict:
        return self.run_cli(root, "skills/_core/participant_flow/flow_cli.py", *args, "--root", str(root))

    def analysis(self, root: Path, *args: str) -> dict:
        return self.run_cli(root, "skills/_core/empirical/analysis_cli.py", *args, "--root", str(root))

    @staticmethod
    def phase(status: dict, stage: str) -> dict:
        return next(f for f in status["fases"] if f["stage_id"] == stage)

    @staticmethod
    def gate(status: dict, gate_id: str) -> dict:
        return next(g for g in status["gates"] if g["id"] == gate_id)

    # ----- the operator's records, through the CLIs

    @staticmethod
    def revision(root: Path, version: int, extra: str = "") -> None:
        path = root / "protocol" / f"study-protocol-smoke-v{version:02d}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(MARKER + f"# Smoke and asthma v{version}\n" + FIELDS + extra, encoding="utf-8")

    def approved(self, root: Path) -> None:
        self.revision(root, 1)
        self.study(root, "protocol", "approve", "--by", "Ana Ruiz")

    def recorded(self, root: Path) -> None:
        self.study(root, "ethics", "record", "--by", "Ana Ruiz", "--committee", "Hospital IRB", "--code", "IRB-12",
                   "--date", "2026-01-10", "--consent", "waived for records")
        self.study(root, "registration", "record", "--by", "Ana Ruiz", "--not-applicable", "--reason",
                   "retrospective records study, no registry applies")

    def own_data(self, root: Path, *, deidentify: bool = True) -> None:
        (root / "data").mkdir(exist_ok=True)
        (root / "data" / "cohort.csv").write_text(DATA, encoding="utf-8")
        self.datasets(root, "own", "--slug", "cohort", "--by", "Ana Ruiz", "--statement", "research use only")
        self.datasets(root, "dictionary", "init", "--slug", "cohort", "--file", "data/cohort.csv")
        self.datasets(root, "qc", "--slug", "cohort", "--file", "data/cohort.csv")
        if deidentify:
            self.datasets(root, "deidentify", "--slug", "cohort", "--by", "Ana Ruiz", "--statement",
                          "names replaced by study codes")

    def analysed(self, root: Path) -> None:
        (root / "results").mkdir(exist_ok=True)
        (root / "results" / "o1.csv").write_text("beta,0.4\n", encoding="utf-8")
        self.analysis(root, "record", "--outcome", "O1", "--by", "Ana Ruiz", "--tool", "SPSS",
                      "--input", "data/cohort.csv", "--output", "results/o1.csv")

    def flow_counts(self, root: Path, analysed: int = 118) -> None:
        path = root / "study" / "flow.json"
        if not path.is_file():
            self.flow(root, "template", "strobe", "--write")
        flow = json.loads(path.read_text(encoding="utf-8"))
        for stage in flow["stages"].values():
            stage["n"] = 120
        flow["stages"]["analysed"].update(n=analysed, excluded=[{"reason": "missing outcome", "n": 120 - analysed}])
        path.write_text(json.dumps(flow), encoding="utf-8")

    def signed_flow(self, root: Path) -> None:
        self.flow_counts(root)
        self.flow(root, "render")
        self.flow(root, "signoff", "--by", "Ana Ruiz")

    def full_study(self, root: Path) -> None:
        self.approved(root)
        self.recorded(root)
        self.own_data(root)
        self.analysed(root)
        self.signed_flow(root)

    def spanish_gaps(self, status: dict) -> list[str]:
        """Board labels with no Spanish entry. The workspace's own words stay
        as written: the contracts' opening sentences and block questions, the
        artifacts' file names and what the operator typed into a record."""
        own = {s["principles"] for s in status["sections"]}
        own |= {b["question"] for s in status["sections"] for b in s["canonical_blocks"]}
        own |= {a["name"] for a in status["artifacts"]}
        fields = localize.DISPLAY_FIELDS["/api/status"]
        return sorted({text for text in localize.display_strings(status, fields)
                       if text not in own and localize.lookup(text) is None})


class StepsTests(BoardCase):
    def test_the_board_shows_the_ten_steps_of_the_line(self) -> None:
        self.assertTrue(lines.registered(KIND))
        status = self.status(self.workspace())
        self.assertEqual(status["paper_kind"], KIND)
        self.assertNotIn("board_notice", status)
        self.assertEqual([f["stage_id"] for f in status["fases"]], STEPS)
        self.assertEqual([f["id"] for f in status["fases"]], [f"Fase {n}" for n in range(1, 11)])
        self.assertEqual(self.phase(status, "study_protocol")["name"], "Phase 3: Study Protocol (G-STUDY-PROTOCOL)")
        self.assertEqual([g["id"] for g in status["gates"]], GATES)
        for gate in GATES[:5]:
            with self.subTest(gate=gate):
                self.assertEqual(self.gate(status, gate)["status"], "PENDING")
                self.assertEqual(self.gate(status, gate)["reviewer"], "operator")
        self.assertEqual(self.gate(status, "G-DATA-QC")["phase"], "Fase 5")
        for stage in STEPS:
            with self.subTest(stage=stage):
                phase = self.phase(status, stage)
                self.assertTrue(phase["actions"])
                self.assertTrue(phase["evidence"])
                self.assertTrue(phase["subfases"])

    def test_the_steps_follow_the_flow_template(self) -> None:
        flow = (REPO / "src/papersmith/templates/paper-flow-observational-measurement.md.tpl").read_text(encoding="utf-8")
        numbered = re.findall(r"^\s*(\d+)\. \*\*", flow, re.M)
        self.assertEqual(numbered, [str(n) for n in range(1, 11)])
        table = empirical_board.LINE_TABLES[KIND]
        self.assertEqual(list(table.steps), STEPS)

    def test_plausibility_and_the_agreed_type_pass_step_two(self) -> None:
        root = self.workspace()
        self.assertEqual(self.phase(self.status(root), "plausibility_type")["status"], "PENDING")
        idea = root / "idea.txt"
        idea.write_text(IDEA, encoding="utf-8")
        cli = "skills/_core/paper_types/paper_type_cli.py"
        self.run_cli(root, cli, "accept", "--root", str(root), "--by", "Ana Ruiz", "--idea-file", str(idea))
        step = self.phase(self.status(root), "plausibility_type")
        self.assertEqual(step["status"], "ACTIVE")
        self.run_cli(root, cli, "agree", "--root", str(root), "--type", KIND, "--variant", "observational",
                     "--by", "Ana Ruiz")
        step = self.phase(self.status(root), "plausibility_type")
        self.assertEqual(step["status"], "PASS", step["detail"])
        self.assertIn("observational", step["detail"])
        self.assertTrue(self.phase(self.status(root), "study_protocol")["unlocked"])


class GateTests(BoardCase):
    def test_the_protocol_gate_absent_current_and_stale(self) -> None:
        root = self.workspace()
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-STUDY-PROTOCOL")["status"], "PENDING")
        self.assertEqual(self.phase(status, "study_protocol")["status"], "PENDING")
        self.revision(root, 1)
        self.assertEqual(self.phase(self.status(root), "study_protocol")["status"], "ACTIVE")
        self.study(root, "protocol", "approve", "--by", "Ana Ruiz")
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-STUDY-PROTOCOL")["status"], "PASS")
        self.assertEqual(self.phase(status, "study_protocol")["status"], "PASS")
        self.assertIn("Ana Ruiz", self.phase(status, "study_protocol")["detail"])
        self.revision(root, 1, extra="\nEdited after the approval.\n")
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-STUDY-PROTOCOL")["status"], "ACTIVE")
        self.assertIn("amendment", self.phase(status, "study_protocol")["detail"])
        self.study(root, "protocol", "amend", "--by", "Ana Ruiz", "--reason", "typo in the design")
        self.assertEqual(self.gate(self.status(root), "G-STUDY-PROTOCOL")["status"], "PASS")

    def test_ethics_and_registration_absent_current_and_stale(self) -> None:
        root = self.workspace()
        self.approved(root)
        status = self.status(root)
        self.assertEqual([self.gate(status, g)["status"] for g in ("G-ETHICS", "G-REGISTRATION")],
                         ["PENDING", "PENDING"])
        self.recorded(root)
        status = self.status(root)
        # A not-applicable registration passes like a recorded one.
        self.assertEqual([self.gate(status, g)["status"] for g in ("G-ETHICS", "G-REGISTRATION")], ["PASS", "PASS"])
        step = self.phase(status, "ethics_registration")
        self.assertEqual(step["status"], "PASS")
        self.assertIn("Not applicable", step["subfases"][1]["detail"])
        self.assertIn("Hospital IRB", step["subfases"][0]["detail"])
        self.revision(root, 2)
        self.study(root, "protocol", "amend", "--by", "Ana Ruiz", "--reason", "second outcome window")
        status = self.status(root)
        self.assertEqual([self.gate(status, g)["status"] for g in ("G-ETHICS", "G-REGISTRATION")],
                         ["ACTIVE", "ACTIVE"])
        self.assertIn("Stale", self.phase(status, "ethics_registration")["subfases"][0]["detail"])

    def test_the_data_qc_gate_is_read_from_the_evidence(self) -> None:
        root = self.workspace()
        self.assertEqual(self.gate(self.status(root), "G-DATA-QC")["status"], "PENDING")
        self.own_data(root, deidentify=False)
        status = self.status(root)
        # The dictionary flags patient_name as personal data: not de-identified yet.
        self.assertEqual(self.gate(status, "G-DATA-QC")["status"], "ACTIVE")
        self.assertIn("personal data not de-identified", self.phase(status, "data")["detail"])
        self.datasets(root, "deidentify", "--slug", "cohort", "--by", "Ana Ruiz", "--statement", "names coded")
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-DATA-QC")["status"], "PASS", self.phase(status, "data")["detail"])
        self.assertEqual(self.phase(status, "data")["status"], "PASS")
        # The data changes after its QC: stale.
        (root / "data" / "cohort.csv").write_text(DATA + "Eva,29,3\n", encoding="utf-8")
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-DATA-QC")["status"], "ACTIVE")
        self.assertIn("data file changed", self.phase(status, "data")["detail"])
        self.datasets(root, "qc", "--slug", "cohort", "--file", "data/cohort.csv")
        self.datasets(root, "deidentify", "--slug", "cohort", "--by", "Ana Ruiz", "--statement", "names coded")
        self.assertEqual(self.gate(self.status(root), "G-DATA-QC")["status"], "PASS")
        # The dictionary changes after the QC: stale too.
        dictionary = root / "datasets" / "cohort" / "dictionary.json"
        document = json.loads(dictionary.read_text(encoding="utf-8"))
        document["columns"][1]["description"] = "age at admission"
        dictionary.write_text(json.dumps(document), encoding="utf-8")
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-DATA-QC")["status"], "ACTIVE")
        self.assertIn("current data dictionary", self.phase(status, "data")["detail"])

    def test_a_failed_quality_check_fails_the_gate(self) -> None:
        root = self.workspace()
        self.own_data(root)
        dictionary = root / "datasets" / "cohort" / "dictionary.json"
        document = json.loads(dictionary.read_text(encoding="utf-8"))
        document["columns"].append({"name": "smoke_days", "type": "integer", "unit": "", "range": None,
                                    "levels": None, "missing_codes": [], "description": "", "pii": False})
        dictionary.write_text(json.dumps(document), encoding="utf-8")
        self.datasets(root, "qc", "--slug", "cohort", "--file", "data/cohort.csv")
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-DATA-QC")["status"], "FAIL")
        self.assertIn("quality check failed", self.phase(status, "data")["detail"])

    def test_the_flow_gate_absent_current_and_stale(self) -> None:
        root = self.workspace()
        self.assertEqual(self.gate(self.status(root), "G-FLOW")["status"], "PENDING")
        self.flow_counts(root)
        self.flow(root, "render")
        step = self.phase(self.status(root), "participant_flow")
        self.assertEqual(step["status"], "ACTIVE")
        self.assertIn("awaiting the operator's sign-off", step["detail"])
        self.flow(root, "signoff", "--by", "Ana Ruiz")
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-FLOW")["status"], "PASS")
        self.assertEqual(self.phase(status, "participant_flow")["status"], "PASS")
        self.flow_counts(root, analysed=117)
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-FLOW")["status"], "ACTIVE")
        self.assertIn("draw the flow figure again", self.phase(status, "participant_flow")["detail"])

    def test_the_analysis_step_reads_the_log(self) -> None:
        root = self.workspace()
        self.assertEqual(self.phase(self.status(root), "analysis")["status"], "PENDING")
        self.approved(root)
        self.own_data(root)
        self.analysed(root)
        step = self.phase(self.status(root), "analysis")
        self.assertEqual(step["status"], "PASS", step["detail"])
        self.assertIn("1 confirmatory", step["detail"])

    def test_the_board_never_writes_a_record(self) -> None:
        root = self.workspace()
        self.full_study(root)
        watched = ["study", "protocol", "analysis", "datasets", ".papersmith/paper_type.json"]

        def snapshot() -> dict:
            out = {}
            for rel in watched:
                base = root / rel
                paths = [base] if base.is_file() else sorted(p for p in base.rglob("*") if p.is_file())
                out.update({p.relative_to(root).as_posix(): p.read_bytes() for p in paths})
            return out

        before = snapshot()
        self.status(root)
        self.status(root, "es")
        self.assertEqual(snapshot(), before)


class LockTests(BoardCase):
    def test_analysis_waits_for_the_protocol_the_records_and_the_data_qc(self) -> None:
        root = self.workspace()
        actions = [a for a in self.phase(self.status(root), "analysis")["actions"] if a.get("locked") is not None]
        self.assertEqual(len(actions), 2)
        for action in actions:
            self.assertTrue(action["locked"])
            self.assertEqual(action["requires"], "G-STUDY-PROTOCOL")
        self.approved(root)
        self.recorded(root)
        locked = [a for a in self.phase(self.status(root), "analysis")["actions"] if a.get("locked")]
        self.assertEqual({a["requires"] for a in locked}, {"G-DATA-QC"})
        self.own_data(root)
        status = self.status(root)
        self.assertFalse(any(a.get("locked") for a in self.phase(status, "analysis")["actions"]))
        self.assertIsNone(self.phase(status, "analysis")["blocked_by"])

    def test_writing_waits_for_the_flow_signoff(self) -> None:
        root = self.workspace()
        self.approved(root)
        self.recorded(root)
        self.own_data(root)
        self.analysed(root)
        self.flow_counts(root)
        self.flow(root, "render")
        writing = self.phase(self.status(root), "writing")
        self.assertFalse(writing["unlocked"])
        self.assertEqual(writing["blocked_by"], "Fase 7")
        self.flow(root, "signoff", "--by", "Ana Ruiz")
        writing = self.phase(self.status(root), "writing")
        self.assertTrue(writing["unlocked"], writing["blocked_by"])

    def test_the_phase_gates_of_the_line(self) -> None:
        board = lines.board(KIND)
        self.assertEqual(dict(board.phase_gates), {"analysis": "G-DATA-QC", "writing": "G-FLOW"})
        self.assertEqual(board.transversal, "reporting_audit")


class ChecklistTests(BoardCase):
    def checklist(self, root: Path) -> dict:
        return self.phase(self.status(root), "reporting_audit")["subfases"][0]

    def agree(self, root: Path, variant: str) -> None:
        idea = root / "idea.txt"
        idea.write_text(IDEA, encoding="utf-8")
        cli = "skills/_core/paper_types/paper_type_cli.py"
        self.run_cli(root, cli, "accept", "--root", str(root), "--by", "Ana Ruiz", "--idea-file", str(idea))
        self.run_cli(root, cli, "agree", "--root", str(root), "--type", KIND, "--variant", variant, "--by", "Ana Ruiz")

    def test_the_checklist_names_the_agreed_variants_guideline(self) -> None:
        root = self.workspace()
        self.assertIn("No variant agreed yet", self.checklist(root)["detail"])
        self.agree(root, "diagnostic-validation")
        sub = self.checklist(root)
        self.assertEqual(sub["name"], "Reporting checklist (stard-2015)")
        self.assertEqual(sub["status"], "PENDING")
        self.assertIn("--guideline stard-2015", sub["detail"])
        self.assertIn("STARD 2015", sub["detail"])

    def test_a_variant_without_checklist_data_says_so(self) -> None:
        root = self.workspace()
        self.agree(root, "measurement-instrument")
        real = empirical_board.paper_types.get

        def without_checklist(type_id: str, path=None) -> dict:
            item = json.loads(json.dumps(real(type_id, path)))
            for variant in item.get("variants") or []:
                variant["checklist"] = None
            return item

        with mock.patch.object(empirical_board.paper_types, "get", without_checklist):
            sub = self.checklist(root)
            self.assertEqual(sub["name"], "Reporting checklist")
            self.assertIn("No checklist data yet for the measurement-instrument variant", sub["detail"])
            self.assertEqual(self.spanish_gaps(self.status(root)), [])


class ModuleLoadingTests(BoardCase):
    def test_a_broken_workspace_module_falls_back_visibly(self) -> None:
        root = self.workspace()
        self.approved(root)
        broken = root / "skills" / "_core" / "empirical" / "records.py"
        broken.write_text("def broken(:\n", encoding="utf-8")
        status = self.status(root)
        step = self.phase(status, "study_protocol")
        self.assertEqual(step["status"], "PASS")
        self.assertIn("the workspace's records.py did not load (SyntaxError", step["detail"])
        self.assertIn(str(broken), step["detail"])
        self.assertNotIn("did not load", self.phase(status, "writing")["detail"])
        self.assertEqual(self.spanish_gaps(status), [])
        self.assertNotIn("did not load", self.phase(self.status(root, "es"), "study_protocol")["detail"])

    def test_without_the_modules_the_board_still_answers(self) -> None:
        root = self.workspace()
        shutil.rmtree(root / "skills" / "_core" / "empirical")
        with mock.patch.object(empirical_board, "DASHBOARD_SKILLS", root / "absent"):
            status = self.status(root)
        self.assertEqual([f["stage_id"] for f in status["fases"]], STEPS)
        self.assertIn("records.py is not available", self.phase(status, "study_protocol")["detail"])
        self.assertEqual(self.gate(status, "G-STUDY-PROTOCOL")["status"], "PENDING")
        self.assertEqual(self.spanish_gaps(status), [])


class CardTests(BoardCase):
    def test_every_card_runs_a_real_command(self) -> None:
        root = self.workspace()
        clis = {
            "python skills/_core/empirical/study_cli.py": "skills/_core/empirical/study_cli.py",
            "python skills/_core/empirical/analysis_cli.py": "skills/_core/empirical/analysis_cli.py",
            "python skills/_core/participant_flow/flow_cli.py": "skills/_core/participant_flow/flow_cli.py",
            "python skills/datasets/scripts/datasets_cli.py": "skills/datasets/scripts/datasets_cli.py",
            "python skills/_core/checklists/checklist_cli.py": "skills/_core/checklists/checklist_cli.py",
        }
        smith_verbs = {"status", "audit"}
        board = lines.board(KIND)
        for stage in board.stages:
            for action in board.actions[stage]["actions"]:
                with self.subTest(stage=stage, action=action["label"]):
                    if action["kind"] == "prompt":
                        self.assertTrue(action["guide"])
                        name = action["slash"].lstrip("/")
                        self.assertTrue((root / ".claude" / "commands" / f"{name}.md").is_file(), name)
                    elif action["kind"] == "redirect":
                        self.assertIn(action["tab"], TABS)
                    else:
                        words = shlex.split(action["command"])
                        if words[0] == "smith":
                            self.assertIn(words[1], smith_verbs)
                            continue
                        prefix = " ".join(words[:2])
                        self.assertIn(prefix, clis)
                        self.assertEqual(self._parse(root / clis[prefix], words[2:]), "parsed", action["command"])
        self.assertEqual(set(board.actions), set(board.stages))
        self.assertEqual(set(board.evidence), set(board.stages))

    @staticmethod
    def _parse(script: Path, argv: list[str]) -> str:
        """Whether the CLI's own parser accepts ``argv`` (stopped right after parsing)."""

        class Parsed(BaseException):
            pass

        original = argparse.ArgumentParser.parse_args

        def spy(self, args=None, namespace=None):
            original(self, args, namespace)
            raise Parsed

        spec = importlib.util.spec_from_file_location(f"o4_cli_{script.stem}", script)
        module = importlib.util.module_from_spec(spec)
        saved = list(sys.path)
        # A workspace CLI imports `skills` from its own (temporary) root; drop
        # what it imported so later tests never resolve `skills` there.
        modules = set(sys.modules)
        try:
            spec.loader.exec_module(module)
            entry = getattr(module, "run", None) if script.name == "datasets_cli.py" else module.main
            with mock.patch.object(argparse.ArgumentParser, "parse_args", spy), \
                    contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                entry(argv)
        except Parsed:
            return "parsed"
        except SystemExit as exc:
            return f"refused ({exc.code})"
        finally:
            sys.path[:] = saved
            for name in set(sys.modules) - modules:
                if name == "skills" or name.startswith("skills."):
                    del sys.modules[name]
        return "not parsed"

    def test_every_operator_record_names_the_operator(self) -> None:
        board = lines.board(KIND)
        commands = [a["command"] for stage in board.stages for a in board.actions[stage]["actions"]
                    if a["kind"] == "command" and re.search(r" (approve|amend|record|own|deidentify|signoff) ",
                                                            a["command"])]
        self.assertEqual(len(commands), 10)
        for command in commands:
            self.assertRegex(command, r'--by "<operator name>"')

    def test_a_phase_check_answers_with_its_step(self) -> None:
        root = self.workspace()
        client = TestClient(server.create_app(root))
        body = client.post("/api/phase/run", json={"phase_id": "Fase 3"}).json()
        self.assertEqual(body["stage"], "study_protocol")
        self.assertIn("Phase 3: it runs from its card", body["message"])
        self.assertEqual(client.post("/api/phase/run", json={"phase_id": "Fase 11"}).status_code, 422)
        self.assertEqual(lines.board(KIND).stage_for("analysis"), "analysis")
        self.assertEqual(client.get("/api/flow").status_code, 200)
        agents = client.get("/api/agents").json()
        self.assertEqual(agents.get("paper_kind"), KIND)


class SectionsArtifactsTelemetryTests(BoardCase):
    def test_sections_come_from_the_lines_contracts(self) -> None:
        root = self.workspace()
        status = self.status(root)
        ids = [s["id"] for s in status["sections"]]
        self.assertEqual(ids, sorted(p.stem for p in (root / "sections").glob("*.md")))
        by_id = {s["id"]: s for s in status["sections"]}
        methods = by_id["04-methods"]
        self.assertTrue(methods["principles"].startswith("The methods transcribe the locked protocol"))
        front = json.loads((root / "sections" / "04-methods.md").read_text(encoding="utf-8").split("---")[1])
        self.assertEqual([b["id"] for b in methods["canonical_blocks"]],
                         [f"methods.{b['id']}" for b in front["blocks"]])
        roles = {b["id"]: b["role"] for b in methods["canonical_blocks"]}
        self.assertEqual(roles["methods.m-design-setting"], "Study block")
        self.assertEqual(roles["methods.m-reference-standard"],
                         "Optional study block of the diagnostic-validation variant")
        self.assertTrue(by_id["05-results"]["has_figures"])
        self.assertFalse(methods["has_figures"])
        # The shared back matter keeps its experimental metadata.
        self.assertEqual(by_id["10-back-matter"]["cross_relations"],
                         "Meets the regulatory and ethical requirements of academic publishing.")

    def test_the_study_records_are_artifacts(self) -> None:
        root = self.workspace()
        self.full_study(root)
        rows = {a["rel_path"]: a["category"] for a in self.status(root)["artifacts"]}
        self.assertEqual(rows["protocol/study-protocol-smoke-v01.md"], "Study Protocol")
        self.assertEqual(rows["study/protocol.lock.json"], "Study Records")
        self.assertEqual(rows["study/flow.json"], "Study Records")
        self.assertEqual(rows["analysis/log.jsonl"], "Analysis Log")
        self.assertEqual(rows["datasets/cohort/qc.json"], "Data Quality")
        self.assertEqual(rows["paper/Figures/participant-flow.svg"], "Participant Flow")

    def test_telemetry_has_labels_and_no_invented_numbers(self) -> None:
        root = self.workspace()
        self.full_study(root)
        status = self.status(root)
        rows = status["telemetria"]
        measured = [f for f in status["fases"] if f["status"] in ("PASS", "ACTIVE")]
        self.assertTrue(rows)
        self.assertEqual([r["fase"] for r in rows], [f["name"] for f in measured])
        for row in rows:
            with self.subTest(row=row["fase"]):
                self.assertEqual((row["tokens"], row["tool_uses"], row["duracion"]), (None, None, None))
                self.assertTrue(row["note"])
        self.assertEqual((status["totals"]["total_tokens"], status["totals"]["total_tool_uses"]), ("0", 0))


class SpanishTests(BoardCase):
    def test_every_label_has_a_spanish_entry(self) -> None:
        root = self.workspace()
        states = {
            "empty": lambda: None,
            "revision": lambda: self.revision(root, 1),
            "approved": lambda: self.study(root, "protocol", "approve", "--by", "Ana Ruiz"),
            "recorded": lambda: self.recorded(root),
            "data owed": lambda: self.own_data(root, deidentify=False),
            "data": lambda: self.datasets(root, "deidentify", "--slug", "cohort", "--by", "Ana Ruiz",
                                          "--statement", "names coded"),
            "analysed": lambda: self.analysed(root),
            "flow drawn": lambda: (self.flow_counts(root), self.flow(root, "render")),
            "signed": lambda: self.flow(root, "signoff", "--by", "Ana Ruiz"),
            "stale": lambda: (self.revision(root, 2), self.flow_counts(root, analysed=117),
                              (root / "data" / "cohort.csv").write_text(DATA + "Eva,29,3\n", encoding="utf-8")),
        }
        for name, step in states.items():
            step()
            with self.subTest(state=name):
                self.assertEqual(self.spanish_gaps(self.status(root)), [])

    def test_the_spanish_board_keeps_its_machine_values(self) -> None:
        root = self.workspace()
        english, spanish = self.status(root), self.status(root, "es")
        self.assertTrue(spanish["fases"][2]["name"].startswith("Fase 3: "))
        self.assertEqual([f["stage_id"] for f in spanish["fases"]], STEPS)
        self.assertEqual([g["status"] for g in spanish["gates"]], [g["status"] for g in english["gates"]])
        self.assertEqual(spanish["paper_kind"], KIND)

    def test_the_boards_own_texts_have_entries_of_their_own(self) -> None:
        # A generic template ("{version} at {path}") would otherwise half-translate them.
        catalogue = json.loads(localize.CATALOGUE.read_text(encoding="utf-8"))
        texts = [empirical_board.TELEMETRY_NOTE, *(c for _, _, c in empirical_board._ARTIFACTS)]
        texts += [gate.criteria for gate in empirical_board.GATES.values()]
        for step in empirical_board.STEPS.values():
            texts += [step.desc, step.label, *(label for label, _ in step.evidence)]
            self.assertIn(f"Phase {{n}}: {step.title}", catalogue)
            for action in step.actions["actions"]:
                texts += [action["label"], action.get("desc") or action["label"], *action.get("guide", ())]
                if action.get("placeholder"):
                    texts.append(action["placeholder"])
        self.assertEqual(sorted({text for text in texts if text not in catalogue}), [])

    def test_the_agents_table_labels_have_spanish(self) -> None:
        for label in lines.board(KIND).labels.values():
            with self.subTest(label=label):
                self.assertIsNotNone(localize.lookup(label))
                self.assertIsNotNone(localize.lookup(f"Phase 4 — {label}"))


class OtherLinesTests(unittest.TestCase):
    def test_the_registry_registers_the_board_on_its_own(self) -> None:
        # A fresh interpreter that imports only the registry (as the server does).
        code = ("from skills._core.command_center import lines; "
                f"print(lines.registered({KIND!r}), lines.board({KIND!r}).notice)")
        env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(REPO / "src"), str(REPO)])}
        proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=str(REPO),
                              env=env, timeout=120)
        self.assertEqual(proc.stdout.strip(), "True None", proc.stderr)

    def test_the_experimental_and_review_boards_are_untouched(self) -> None:
        from skills._core.command_center import phase_actions, review_board

        self.assertIs(lines.board("experimental"), lines.EXPERIMENTAL)
        self.assertIs(lines.board("review"), lines.REVIEW)
        self.assertIs(lines.REVIEW.actions, review_board.REVIEW_ACTIONS)
        self.assertIs(lines.EXPERIMENTAL.actions, phase_actions.ACTIONS)
        self.assertEqual(sorted(lines.BOARDS), sorted(["experimental", "review", KIND, "hardware", "lab-simulation",
                                                      "data-resource", "experiment-intervention",
                                                      "qualitative-participatory"]))


if __name__ == "__main__":
    unittest.main()
