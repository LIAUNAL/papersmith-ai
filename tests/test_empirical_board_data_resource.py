"""The empirical board's data-resource table (paper-type-lines S8, T8-B4, decisions H3, H4).

A `data-resource` workspace shows the eleven steps of
`src/papersmith/templates/paper-flow-data-resource.md.tpl` with the gates
G-STUDY-PROTOCOL (the collection protocol's lock), G-ETHICS (an ethics record
current or not applicable, plus the right to release every registered dataset:
the own-data statement or an `allowed` licence decision), G-DATA-QC (the shared
quality gate) and G-DEPOSIT (`datasets_cli.deposit_state` current for every
registered dataset). The baselines and the deposit wait for G-DATA-QC; the
writing waits for G-DEPOSIT. Every record is written through the real CLIs
(`study_cli.py`, `datasets_cli.py`, `analysis_cli.py`, `paper_type_cli.py`); the
board only reads them.
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

KIND = "data-resource"
STEPS = ["harness", "plausibility_resource", "collection_protocol", "ethics_licence", "curation", "quality",
         "baselines", "deposit", "writing", "paper", "reporting_resource"]
GATES = ["G-STUDY-PROTOCOL", "G-ETHICS", "G-DATA-QC", "G-DEPOSIT", "G1", "G2", "G3", "G4"]
DATA = "participant_name,age,label\nAna,34,positive\nLuis,51,negative\n"
DOI = "10.5281/zenodo.7654321"
PAPER_TYPE = "skills/_core/paper_types/paper_type_cli.py"
IDEA = ("We release a corpus of annotated clinical notes for asthma triage. "
        "We collected the notes under consent and document, check and deposit them.")

_TEMPLATES: dict[str, Path] = {}


def _template() -> Path:
    if "ws" not in _TEMPLATES:
        ws = Path(tempfile.mkdtemp(prefix="b4-template-")) / "ws"
        initialize(ws, tools=("claude",), run_npm=False, run_env=False, kind=KIND)
        _TEMPLATES["ws"] = ws
    return _TEMPLATES["ws"]


def tearDownModule() -> None:  # noqa: N802 - unittest hook
    for ws in _TEMPLATES.values():
        shutil.rmtree(ws.parent, ignore_errors=True)


class ResourceBoardCase(base.BoardCase):
    def workspace(self) -> Path:
        holder = tempfile.TemporaryDirectory(prefix="b4-case-", ignore_cleanup_errors=True)
        self.addCleanup(holder.cleanup)
        root = Path(holder.name) / "ws"
        shutil.copytree(_template(), root, symlinks=True)
        return root

    @staticmethod
    def write(root: Path, rel: str, text: str) -> None:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def ethics(self, root: Path) -> None:
        self.study(root, "ethics", "record", "--by", "Ana Ruiz", "--committee", "Hospital IRB", "--code", "IRB-12",
                   "--date", "2026-01-10", "--consent", "written consent for release")

    def own(self, root: Path) -> None:
        self.write(root, "data/notes.csv", DATA)
        self.datasets(root, "own", "--slug", "notes", "--by", "Ana Ruiz", "--statement",
                      "Released for research under CC-BY-4.0")

    def dictionary(self, root: Path) -> None:
        self.datasets(root, "dictionary", "init", "--slug", "notes", "--file", "data/notes.csv")

    def checked(self, root: Path, *, deidentify: bool = True) -> None:
        self.datasets(root, "qc", "--slug", "notes", "--file", "data/notes.csv")
        if deidentify:
            self.datasets(root, "deidentify", "--slug", "notes", "--by", "Ana Ruiz", "--statement",
                          "names replaced by study codes")

    def baseline(self, root: Path) -> None:
        self.write(root, "baseline.py", "print('ok')\n")
        self.write(root, "results/baseline.csv", "accuracy,0.81\n")
        self.analysis(root, "record", "--outcome", "O1", "--by", "Ana Ruiz", "--tool", "Weka",
                      "--input", "data/notes.csv", "--output", "results/baseline.csv")

    def deposited(self, root: Path) -> None:
        self.datasets(root, "deposit", "--slug", "notes", "--repository", "Zenodo", "--identifier", DOI,
                      "--license", "CC-BY-4.0", "--by", "Ana Ruiz", "--version", "v1")

    def resource(self, root: Path) -> None:
        """Protocol locked, ethics recorded, own data documented, checked, de-identified and deposited."""
        self.approved(root)
        self.ethics(root)
        self.own(root)
        self.dictionary(root)
        self.checked(root)
        self.baseline(root)
        self.deposited(root)

    def agree(self, root: Path) -> None:
        self.write(root, "idea.txt", IDEA)
        self.run_cli(root, PAPER_TYPE, "accept", "--root", str(root), "--by", "Ana Ruiz", "--idea-file",
                     str(root / "idea.txt"))
        self.run_cli(root, PAPER_TYPE, "agree", "--root", str(root), "--type", KIND, "--by", "Ana Ruiz")


# --------------------------------------------------------------------------- steps


class StepsTests(ResourceBoardCase):
    def test_the_board_shows_the_eleven_steps_of_the_flow(self) -> None:
        self.assertTrue(lines.registered(KIND))
        status = self.status(self.workspace())
        self.assertEqual(status["paper_kind"], KIND)
        self.assertNotIn("board_notice", status)
        self.assertEqual([f["stage_id"] for f in status["fases"]], STEPS)
        self.assertEqual([g["id"] for g in status["gates"]], GATES)
        phases = {g["id"]: g["phase"] for g in status["gates"]}
        self.assertEqual([phases[g] for g in GATES[:4]], ["Fase 3", "Fase 4", "Fase 6", "Fase 8"])
        for gate in GATES[:4]:
            with self.subTest(gate=gate):
                self.assertEqual(self.gate(status, gate)["status"], "PENDING")
                self.assertEqual(self.gate(status, gate)["reviewer"], "operator")
        self.assertEqual(self.phase(status, "deposit")["name"], "Phase 8: Deposit with a Persistent Identifier (G-DEPOSIT)")
        for stage in STEPS:
            with self.subTest(stage=stage):
                phase = self.phase(status, stage)
                self.assertTrue(phase["actions"])
                self.assertTrue(phase["evidence"])
                self.assertTrue(phase["subfases"])

    def test_the_steps_follow_the_flow_template(self) -> None:
        flow = (REPO / "src/papersmith/templates/paper-flow-data-resource.md.tpl").read_text(encoding="utf-8")
        self.assertEqual(len(re.findall(r"^\s*(\d+)\. \*\*", flow, re.M)), len(STEPS))
        self.assertEqual(list(empirical_board.LINE_TABLES[KIND].steps), STEPS)
        self.assertEqual(lines.board(KIND).flow_html, f"papersmith-{KIND}-flow.html")

    def test_the_agreed_type_passes_step_two(self) -> None:
        root = self.workspace()
        self.agree(root)
        step = self.phase(self.status(root), "plausibility_resource")
        self.assertEqual(step["status"], "PASS", step["detail"])
        self.assertIn("Paper type data-resource agreed by Ana Ruiz", step["detail"])

    def test_the_curation_step_reads_the_dictionaries(self) -> None:
        root = self.workspace()
        self.assertEqual(self.phase(self.status(root), "curation")["status"], "PENDING")
        self.own(root)
        step = self.phase(self.status(root), "curation")
        self.assertEqual(step["status"], "ACTIVE")
        self.assertIn("notes: no data dictionary (datasets_cli.py dictionary init)", step["detail"])
        self.dictionary(root)
        step = self.phase(self.status(root), "curation")
        self.assertEqual(step["status"], "PASS", step["detail"])
        self.assertIn("1 dataset(s) with a valid data dictionary", step["detail"])
        (root / "datasets" / "notes" / "dictionary.json").write_text("{\"columns\": 3}", encoding="utf-8")
        step = self.phase(self.status(root), "curation")
        self.assertEqual(step["status"], "ACTIVE")
        self.assertIn("notes: the data dictionary is invalid", step["detail"])

    def test_the_baselines_step_reads_the_log(self) -> None:
        root = self.workspace()
        self.assertEqual(self.phase(self.status(root), "baselines")["status"], "PENDING")
        self.approved(root)
        self.own(root)
        self.baseline(root)
        step = self.phase(self.status(root), "baselines")
        self.assertEqual(step["status"], "PASS", step["detail"])
        self.assertIn("1 analysis entries logged", step["detail"])


# --------------------------------------------------------------------------- gates


class GateTests(ResourceBoardCase):
    def test_the_protocol_gate_absent_current_and_stale(self) -> None:
        root = self.workspace()
        self.revision(root, 1)
        step = self.phase(self.status(root), "collection_protocol")
        self.assertEqual(step["status"], "ACTIVE")
        self.assertIn("G-STUDY-PROTOCOL", step["detail"])
        self.study(root, "protocol", "approve", "--by", "Ana Ruiz")
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-STUDY-PROTOCOL")["status"], "PASS")
        self.revision(root, 1, extra="\nEdited.\n")
        self.assertEqual(self.gate(self.status(root), "G-STUDY-PROTOCOL")["status"], "ACTIVE")

    def test_the_ethics_gate_needs_the_record_and_the_right_to_release(self) -> None:
        root = self.workspace()
        self.approved(root)
        self.ethics(root)
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-ETHICS")["status"], "ACTIVE")
        step = self.phase(status, "ethics_licence")
        self.assertEqual(step["status"], "ACTIVE")
        self.assertIn("No dataset registered yet", step["detail"])
        self.own(root)
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-ETHICS")["status"], "PASS")
        step = self.phase(status, "ethics_licence")
        self.assertEqual(step["status"], "PASS", step["detail"])
        names = [s["name"] for s in step["subfases"]]
        self.assertEqual(names, ["Ethics approval and consent (G-ETHICS, operator)",
                                 "Right to release: own-data statement or allowed licence (G-ETHICS, operator)"])
        self.assertIn("notes: own data, data-use statement by Ana Ruiz", step["subfases"][1]["detail"])
        # An amendment makes the ethics record stale.
        self.revision(root, 2)
        self.study(root, "protocol", "amend", "--by", "Ana Ruiz", "--reason", "a second source")
        self.assertEqual(self.gate(self.status(root), "G-ETHICS")["status"], "ACTIVE")

    def test_not_applicable_ethics_and_an_allowed_licence_pass(self) -> None:
        root = self.workspace()
        self.approved(root)
        self.study(root, "ethics", "record", "--by", "Ana Ruiz", "--not-applicable", "--reason",
                   "public sensor records, no person takes part")
        self.datasets(root, "license", "--slug", "sensors", "--source-license", "CC BY 4.0")
        step = self.phase(self.status(root), "ethics_licence")
        self.assertEqual(step["status"], "PASS", step["detail"])
        self.assertIn("sensors: licence CC BY 4.0 allowed", step["subfases"][1]["detail"])

    def test_a_refused_or_overridden_licence_does_not_pass(self) -> None:
        root = self.workspace()
        self.approved(root)
        self.ethics(root)
        self.datasets(root, "license", "--slug", "forum", "--source-license", "CC BY-NC 4.0")
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-ETHICS")["status"], "ACTIVE")
        self.assertIn("forum: the licence was refused", self.phase(status, "ethics_licence")["detail"])
        self.datasets(root, "license", "--slug", "forum", "--source-license", "CC BY-NC 4.0", "--override",
                      "used inside the project only")
        detail = self.phase(self.status(root), "ethics_licence")["detail"]
        self.assertIn("forum: the licence was accepted by an override", detail)
        self.assertEqual(self.spanish_gaps(self.status(root)), [])

    def test_the_data_qc_gate_absent_current_and_stale(self) -> None:
        root = self.workspace()
        self.own(root)
        self.dictionary(root)
        self.assertEqual(self.gate(self.status(root), "G-DATA-QC")["status"], "ACTIVE")
        self.checked(root, deidentify=False)
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-DATA-QC")["status"], "ACTIVE")
        self.assertIn("personal data not de-identified", self.phase(status, "quality")["detail"])
        self.datasets(root, "deidentify", "--slug", "notes", "--by", "Ana Ruiz", "--statement", "names coded")
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-DATA-QC")["status"], "PASS")
        self.assertEqual(self.phase(status, "quality")["status"], "PASS")
        self.write(root, "data/notes.csv", DATA + "Eva,29,positive\n")
        self.assertEqual(self.gate(self.status(root), "G-DATA-QC")["status"], "ACTIVE")

    def test_the_deposit_gate_absent_current_and_stale(self) -> None:
        root = self.workspace()
        self.approved(root)
        self.ethics(root)
        self.own(root)
        self.dictionary(root)
        self.checked(root)
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-DEPOSIT")["status"], "PENDING")
        self.assertIn("notes: no deposit recorded yet", self.phase(status, "deposit")["detail"])
        self.deposited(root)
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-DEPOSIT")["status"], "PASS")
        step = self.phase(status, "deposit")
        self.assertEqual(step["status"], "PASS", step["detail"])
        self.assertIn(f"notes in Zenodo (doi {DOI})", step["detail"])
        # A changed data file makes the deposit stale.
        self.write(root, "data/notes.csv", DATA + "Eva,29,positive\n")
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-DEPOSIT")["status"], "ACTIVE")
        step = self.phase(status, "deposit")
        self.assertEqual(step["status"], "ACTIVE")
        self.assertIn("notes: the deposit is stale (data/notes.csv changed since the deposit)", step["detail"])

    def test_every_registered_dataset_must_be_deposited(self) -> None:
        root = self.workspace()
        self.own(root)
        self.dictionary(root)
        self.checked(root)
        self.deposited(root)
        self.datasets(root, "license", "--slug", "sensors", "--source-license", "CC0 1.0")
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-DEPOSIT")["status"], "ACTIVE")
        self.assertIn("sensors: no deposit recorded yet", self.phase(status, "deposit")["detail"])

    def test_a_toy_set_is_not_part_of_the_resource(self) -> None:
        root = self.workspace()
        self.datasets(root, "license", "--slug", "toy", "--source-license", "CC0 1.0", "--role", "toy")
        status = self.status(root)
        self.assertIn("No dataset registered yet", self.phase(status, "deposit")["detail"])
        self.assertEqual(self.gate(status, "G-DEPOSIT")["status"], "PENDING")


# --------------------------------------------------------------------------- locks


class LockTests(ResourceBoardCase):
    def test_the_phase_gates_of_the_line(self) -> None:
        board = lines.board(KIND)
        self.assertEqual(dict(board.phase_gates), {"baselines": "G-DATA-QC", "writing": "G-DEPOSIT"})
        self.assertEqual(board.transversal, "reporting_resource")
        self.assertIn("deposit", board.ungated)

    def test_baselines_and_deposit_wait_for_the_data_qc(self) -> None:
        root = self.workspace()
        status = self.status(root)
        for stage in ("baselines", "deposit"):
            with self.subTest(stage=stage):
                locked = [a for a in self.phase(status, stage)["actions"] if a.get("locked") is not None]
                self.assertTrue(locked)
                for action in locked:
                    self.assertTrue(action["locked"])
                    self.assertEqual(action["requires"], "G-DATA-QC")
        self.approved(root)
        self.ethics(root)
        self.own(root)
        self.dictionary(root)
        self.checked(root)
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-DATA-QC")["status"], "PASS")
        for stage in ("baselines", "deposit"):
            with self.subTest(stage=stage):
                self.assertFalse(any(a.get("locked") for a in self.phase(status, stage)["actions"]))
        self.assertTrue(self.phase(status, "baselines")["unlocked"], self.phase(status, "baselines")["blocked_by"])
        # The deposit does not wait for a baseline.
        self.assertEqual(self.phase(status, "baselines")["status"], "PENDING")
        self.assertTrue(self.phase(status, "deposit")["unlocked"])

    def test_writing_waits_for_the_deposit(self) -> None:
        root = self.workspace()
        self.approved(root)
        self.ethics(root)
        self.own(root)
        self.dictionary(root)
        self.checked(root)
        writing = self.phase(self.status(root), "writing")
        self.assertFalse(writing["unlocked"])
        self.assertEqual(writing["blocked_by"], "Fase 8")
        self.deposited(root)
        writing = self.phase(self.status(root), "writing")
        self.assertTrue(writing["unlocked"], writing["blocked_by"])
        self.write(root, "data/notes.csv", DATA + "Eva,29,positive\n")
        self.assertFalse(self.phase(self.status(root), "writing")["unlocked"])


# --------------------------------------------------------------------------- checklist, read-only, cards, Spanish


class ChecklistTests(ResourceBoardCase):
    def test_the_type_names_the_datasheets_checklist(self) -> None:
        root = self.workspace()
        subs = self.phase(self.status(root), "reporting_resource")["subfases"]
        self.assertEqual(subs[0]["name"], "Reporting checklist")
        self.assertIn("No paper type agreed yet", subs[0]["detail"])
        self.agree(root)
        self.assertEqual(empirical_board.agreed_type(root)["checklist"], "datasheets")
        subs = self.phase(self.status(root), "reporting_resource")["subfases"]
        self.assertEqual(subs[0]["name"], "Reporting checklist (datasheets)")
        self.assertIn("--guideline datasheets", subs[0]["detail"])
        self.assertIn("50 items", subs[0]["detail"])
        self.assertEqual([s["name"] for s in subs][1:], ["Workspace audit (smith audit .)"])


class ReadOnlyAndCardTests(ResourceBoardCase):
    def test_the_board_never_writes_a_record(self) -> None:
        root = self.workspace()
        self.resource(root)
        watched = ["study", "protocol", "analysis", "datasets", "data", ".papersmith/paper_type.json"]

        def snapshot() -> dict:
            out = {}
            for rel in watched:
                folder = root / rel
                paths = [folder] if folder.is_file() else sorted(p for p in folder.rglob("*") if p.is_file())
                out.update({p.relative_to(root).as_posix(): p.read_bytes() for p in paths})
            return out

        before = snapshot()
        self.assertIn("datasets/registry.json", before)
        self.status(root)
        self.status(root, "es")
        self.assertEqual(snapshot(), before)

    def test_every_card_runs_a_real_command(self) -> None:
        root = self.workspace()
        clis = {
            "python skills/_core/empirical/study_cli.py": "skills/_core/empirical/study_cli.py",
            "python skills/_core/empirical/analysis_cli.py": "skills/_core/empirical/analysis_cli.py",
            "python skills/datasets/scripts/datasets_cli.py": "skills/datasets/scripts/datasets_cli.py",
            "python skills/_core/checklists/checklist_cli.py": "skills/_core/checklists/checklist_cli.py",
            "python skills/paper-writing/scripts/paper_cli.py": "skills/paper-writing/scripts/paper_cli.py",
        }
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
                            self.assertIn(words[1], {"status", "audit"})
                            continue
                        prefix = " ".join(words[:2])
                        self.assertIn(prefix, clis)
                        self.assertEqual(base.CardTests._parse(root / clis[prefix], words[2:]), "parsed",
                                         action["command"])
        self.assertEqual(set(board.actions), set(board.stages))
        self.assertEqual(set(board.evidence), set(board.stages))

    def test_every_operator_record_names_the_operator(self) -> None:
        board = lines.board(KIND)
        commands = [a["command"] for stage in board.stages for a in board.actions[stage]["actions"]
                    if a["kind"] == "command" and re.search(r" (approve|amend|record|own|deidentify|deposit) ",
                                                            a["command"])]
        self.assertGreaterEqual(len(commands), 8)
        for command in commands:
            with self.subTest(command=command):
                self.assertRegex(command, r'--by "<operator name>"')


class SpanishTests(ResourceBoardCase):
    def test_every_label_has_a_spanish_entry(self) -> None:
        root = self.workspace()
        states = {
            "empty": lambda: None,
            "revision": lambda: self.revision(root, 1),
            "approved": lambda: self.study(root, "protocol", "approve", "--by", "Ana Ruiz"),
            "ethics": lambda: self.ethics(root),
            "own": lambda: self.own(root),
            "dictionary": lambda: self.dictionary(root),
            "qc owed": lambda: self.checked(root, deidentify=False),
            "checked": lambda: self.datasets(root, "deidentify", "--slug", "notes", "--by", "Ana Ruiz",
                                             "--statement", "names coded"),
            "baseline": lambda: self.baseline(root),
            "deposited": lambda: self.deposited(root),
            "agreed": lambda: self.agree(root),
            "second source": lambda: self.datasets(root, "license", "--slug", "sensors", "--source-license",
                                                   "CC BY-NC 4.0"),
            "stale": lambda: (self.revision(root, 2), self.write(root, "data/notes.csv", DATA + "Eva,29,positive\n")),
        }
        for name, step in states.items():
            step()
            with self.subTest(state=name):
                self.assertEqual(self.spanish_gaps(self.status(root)), [])

    def test_the_new_texts_have_exact_entries(self) -> None:
        catalogue = json.loads(localize.CATALOGUE.read_text(encoding="utf-8"))
        table = empirical_board.LINE_TABLES[KIND]
        for stage in table.steps:
            step = empirical_board.STEPS[stage]
            with self.subTest(stage=stage):
                self.assertIn(f"Phase {{n}}: {step.title}", catalogue)
                self.assertIn(step.label, catalogue)
                self.assertIn(step.desc, catalogue)
                for label, _ in step.evidence:
                    self.assertIn(label, catalogue)
                for action in step.actions["actions"]:
                    for text in (action["label"], action.get("desc") or action["label"], *action.get("guide", ()),
                                 *((action["placeholder"],) if action.get("placeholder") else ())):
                        self.assertIn(text, catalogue)
        for gate in table.gates:
            with self.subTest(gate=gate):
                definition = empirical_board.gate_definition(table, gate)
                self.assertIn(definition.criteria, catalogue)
        for label in lines.board(KIND).labels.values():
            self.assertIsNotNone(localize.lookup(f"Phase 4 — {label}"))

    def test_the_spanish_board_keeps_its_machine_values(self) -> None:
        root = self.workspace()
        self.resource(root)
        english, spanish = self.status(root), self.status(root, "es")
        self.assertTrue(spanish["fases"][7]["name"].startswith("Fase 8: "))
        self.assertEqual([f["stage_id"] for f in spanish["fases"]], STEPS)
        self.assertEqual([g["status"] for g in spanish["gates"]], [g["status"] for g in english["gates"]])
        self.assertIn(DOI, self.phase(spanish, "deposit")["detail"])


class OtherBoardsTests(unittest.TestCase):
    def test_the_other_tables_keep_their_gate_definitions(self) -> None:
        for kind in ("observational-measurement", "hardware", "lab-simulation"):
            table = empirical_board.LINE_TABLES[kind]
            with self.subTest(kind=kind):
                for gate in table.gates:
                    self.assertIs(empirical_board.gate_definition(table, gate), empirical_board.GATES[gate])
        self.assertEqual(empirical_board.GATES["G-ETHICS"].step, "ethics_registration")

    def test_the_server_answers_the_flow_and_a_phase_check(self) -> None:
        holder = tempfile.TemporaryDirectory(prefix="b4-other-", ignore_cleanup_errors=True)
        self.addCleanup(holder.cleanup)
        root = Path(holder.name) / "ws"
        shutil.copytree(_template(), root, symlinks=True)
        client = TestClient(server.create_app(root))
        self.assertEqual(client.get("/api/flow").status_code, 200)
        body = client.post("/api/phase/run", json={"phase_id": "Fase 8"}).json()
        self.assertEqual(body["stage"], "deposit")


if __name__ == "__main__":
    unittest.main()
