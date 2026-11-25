"""The empirical board's experiment-intervention table (paper-type-lines S8, T8-B5, decisions J2-J4).

An `experiment-intervention` workspace shows the eleven steps of
`src/papersmith/templates/paper-flow-experiment-intervention.md.tpl` with the
gates G-STUDY-PROTOCOL, G-REGISTRATION, G-ETHICS, G-ALLOCATION, G-DATA-QC and
G-FLOW. The agreed variant (`.papersmith/paper_type.json`) decides two of them:
a trial with people (`human-trial`) needs a current, prospective registration
(ICMJE) and a signed-off participant flow; a field experiment passes with any
current registration and keeps the flow optional. With no variant agreed the
board applies the human-trial rules, the stricter case, and says so. Every
record is written through the real CLIs (`study_cli.py`, `datasets_cli.py`,
`flow_cli.py`, `analysis_cli.py`, `paper_type_cli.py`); the board only reads
them and never shows the allocation list's content.
"""

from __future__ import annotations

import json
import re
import shlex
import shutil
import tempfile
import unittest
from pathlib import Path

from papersmith.core.init import initialize
from skills._core.command_center import empirical_board, lines, localize
from tests import test_empirical_board as base

REPO, TABS = base.REPO, base.TABS

KIND = "experiment-intervention"
STEPS = ["harness", "plausibility_intervention", "protocol_registration", "ethics_consent", "allocation",
         "intervention_followup", "prespecified_analysis", "flow_units", "writing", "paper",
         "reporting_intervention"]
GATES = ["G-STUDY-PROTOCOL", "G-REGISTRATION", "G-ETHICS", "G-ALLOCATION", "G-DATA-QC", "G-FLOW",
         "G1", "G2", "G3", "G4"]
PAPER_TYPE = "skills/_core/paper_types/paper_type_cli.py"
IDEA = ("We run a randomised controlled trial in two schools: a control group and an intervention group "
        "receive a reading programme. The primary outcome is the reading score after twelve weeks.")
#: The operator's allocation list: tokens that must never reach the board.
ALLOCATION_LIST = "unit,arm\nP-7731,Programme-Zeta\nP-7732,Control-Omega\n"
SECRET_TOKENS = ("P-7731", "Programme-Zeta", "Control-Omega")
NO_VARIANT = "No variant agreed yet, treated as a trial with people (the stricter case)"

_TEMPLATES: dict[str, Path] = {}


def _template() -> Path:
    if "ws" not in _TEMPLATES:
        ws = Path(tempfile.mkdtemp(prefix="b5-template-")) / "ws"
        initialize(ws, tools=("claude",), run_npm=False, run_env=False, kind=KIND)
        _TEMPLATES["ws"] = ws
    return _TEMPLATES["ws"]


def tearDownModule() -> None:  # noqa: N802 - unittest hook
    for ws in _TEMPLATES.values():
        shutil.rmtree(ws.parent, ignore_errors=True)


class TrialBoardCase(base.BoardCase):
    def workspace(self) -> Path:
        holder = tempfile.TemporaryDirectory(prefix="b5-case-", ignore_cleanup_errors=True)
        self.addCleanup(holder.cleanup)
        root = Path(holder.name) / "ws"
        shutil.copytree(_template(), root, symlinks=True)
        return root

    @staticmethod
    def write(root: Path, rel: str, text: str) -> None:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def agree(self, root: Path, variant: str | None) -> None:
        self.write(root, "idea.txt", IDEA)
        self.run_cli(root, PAPER_TYPE, "accept", "--root", str(root), "--by", "Ana Ruiz", "--idea-file",
                     str(root / "idea.txt"))
        extra = ("--variant", variant) if variant else ()
        self.run_cli(root, PAPER_TYPE, "agree", "--root", str(root), "--type", KIND, *extra, "--by", "Ana Ruiz")

    def registered(self, root: Path, *, date: str = "2026-01-05", first: str | None = "2026-01-10") -> None:
        extra = ("--first-enrolment", first) if first else ()
        self.study(root, "registration", "record", "--by", "Ana Ruiz", "--registry", "ISRCTN", "--id",
                   "ISRCTN12345678", "--date", date, *extra)

    def ethics(self, root: Path) -> None:
        self.study(root, "ethics", "record", "--by", "Ana Ruiz", "--committee", "School Board IRB", "--code",
                   "IRB-77", "--date", "2026-01-02", "--consent", "written parental consent")

    def allocated(self, root: Path) -> None:
        self.write(root, "allocation/list.csv", ALLOCATION_LIST)
        self.study(root, "allocation", "record", "--by", "Ana Ruiz", "--file", "allocation/list.csv", "--method",
                   "block", "--block-size", "4", "--concealment", "sealed opaque envelopes")

    def trial_flow(self, root: Path, *, sign: bool = True) -> None:
        self.flow(root, "template", "consort-2025", "--arm", "Control", "--arm", "Programme", "--write")
        path = root / "study" / "flow.json"
        flow = json.loads(path.read_text(encoding="utf-8"))
        stages = flow["stages"]
        stages["assessed"]["n"] = 120
        stages["randomised"]["n"] = 100
        for item, n in zip(stages["randomised"]["excluded"], (10, 6, 4)):
            item["n"] = n
        for stage in ("allocated", "follow_up", "analysed"):
            for arm in ("Control", "Programme"):
                stages[stage]["branches"][arm]["n"] = 50
        path.write_text(json.dumps(flow), encoding="utf-8")
        self.flow(root, "check")
        if sign:
            self.flow(root, "render")
            self.flow(root, "signoff", "--by", "Ana Ruiz")

    def trial(self, root: Path) -> None:
        """Every record of a prospectively registered human trial."""
        self.agree(root, "human-trial")
        self.approved(root)
        self.registered(root)
        self.ethics(root)
        self.allocated(root)
        self.own_data(root)
        self.analysed(root)
        self.trial_flow(root)


# --------------------------------------------------------------------------- steps


class StepsTests(TrialBoardCase):
    def test_the_board_shows_the_eleven_steps_of_the_flow(self) -> None:
        self.assertTrue(lines.registered(KIND))
        status = self.status(self.workspace())
        self.assertEqual(status["paper_kind"], KIND)
        self.assertNotIn("board_notice", status)
        self.assertEqual([f["stage_id"] for f in status["fases"]], STEPS)
        self.assertEqual([g["id"] for g in status["gates"]], GATES)
        phases = {g["id"]: g["phase"] for g in status["gates"]}
        self.assertEqual([phases[g] for g in GATES[:6]], ["Fase 3", "Fase 3", "Fase 4", "Fase 5", "Fase 6", "Fase 8"])
        for gate in GATES[:6]:
            with self.subTest(gate=gate):
                self.assertEqual(self.gate(status, gate)["reviewer"], "operator")
                self.assertNotEqual(self.gate(status, gate)["status"], "PASS")
        self.assertEqual(self.phase(status, "allocation")["name"],
                         "Phase 5: Allocation, Blocks & Sample Size (G-ALLOCATION)")
        for stage in STEPS:
            with self.subTest(stage=stage):
                phase = self.phase(status, stage)
                self.assertTrue(phase["actions"])
                self.assertTrue(phase["evidence"])
                self.assertTrue(phase["subfases"])

    def test_the_steps_follow_the_flow_template(self) -> None:
        flow = (REPO / "src/papersmith/templates/paper-flow-experiment-intervention.md.tpl").read_text(encoding="utf-8")
        self.assertEqual(len(re.findall(r"^\s*(\d+)\. \*\*", flow, re.M)), len(STEPS))
        self.assertEqual(list(empirical_board.LINE_TABLES[KIND].steps), STEPS)
        self.assertEqual(lines.board(KIND).flow_html, "papersmith-flow.html")

    def test_the_agreed_variant_passes_step_two(self) -> None:
        root = self.workspace()
        self.agree(root, "field-experiment")
        step = self.phase(self.status(root), "plausibility_intervention")
        self.assertEqual(step["status"], "PASS", step["detail"])
        self.assertIn("Paper type experiment-intervention (field-experiment) agreed by Ana Ruiz", step["detail"])

    def test_the_protocol_step_holds_the_protocol_and_the_registration(self) -> None:
        root = self.workspace()
        self.agree(root, "human-trial")
        self.revision(root, 1)
        step = self.phase(self.status(root), "protocol_registration")
        self.assertEqual(step["status"], "ACTIVE")
        self.assertIn("G-STUDY-PROTOCOL", step["detail"])
        self.study(root, "protocol", "approve", "--by", "Ana Ruiz")
        step = self.phase(self.status(root), "protocol_registration")
        self.assertEqual(step["status"], "ACTIVE")
        self.assertIn("No registration record yet", step["detail"])
        self.registered(root)
        step = self.phase(self.status(root), "protocol_registration")
        self.assertEqual(step["status"], "PASS", step["detail"])
        self.assertEqual([s["name"] for s in step["subfases"]],
                         ["Protocol revisions (protocol/study-protocol-*.md)", "Operator approval (G-STUDY-PROTOCOL)",
                          "Registration (G-REGISTRATION, operator)"])

    def test_the_intervention_and_analysis_steps_read_the_shared_records(self) -> None:
        root = self.workspace()
        self.approved(root)
        self.own_data(root)
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-DATA-QC")["status"], "PASS")
        self.assertEqual(self.phase(status, "intervention_followup")["status"], "PASS")
        self.analysed(root)
        step = self.phase(self.status(root), "prespecified_analysis")
        self.assertEqual(step["status"], "PASS", step["detail"])
        self.assertIn("1 confirmatory", step["detail"])


# --------------------------------------------------------------------------- G-REGISTRATION


class RegistrationTests(TrialBoardCase):
    def registration(self, root: Path) -> dict:
        status = self.status(root)
        sub = next(s for s in self.phase(status, "protocol_registration")["subfases"]
                   if s["name"] == "Registration (G-REGISTRATION, operator)")
        gate = self.gate(status, "G-REGISTRATION")
        self.assertEqual(gate["status"], sub["status"])
        return sub

    def test_a_prospective_registration_passes_a_trial_with_people(self) -> None:
        root = self.workspace()
        self.agree(root, "human-trial")
        self.approved(root)
        self.registered(root)
        sub = self.registration(root)
        self.assertEqual(sub["status"], "PASS", sub["detail"])
        self.assertIn("on or before the first enrolment on 2026-01-10 (prospective)", sub["detail"])
        self.assertNotIn(NO_VARIANT, sub["detail"])

    def test_a_retrospective_registration_fails_a_trial_with_people(self) -> None:
        root = self.workspace()
        self.agree(root, "human-trial")
        self.approved(root)
        self.registered(root, date="2026-02-01")
        sub = self.registration(root)
        self.assertEqual(sub["status"], "FAIL")
        self.assertIn("Retrospective registration", sub["detail"])
        self.assertIn("on 2026-02-01, after the first enrolment on 2026-01-10", sub["detail"])
        self.assertIn("ICMJE requires a trial with people to be registered on or before its first enrolment",
                      sub["detail"])
        self.assertIn("the paper states it as retrospective", sub["detail"])

    def test_an_unknown_prospectivity_fails_a_trial_with_people(self) -> None:
        root = self.workspace()
        self.agree(root, "human-trial")
        self.approved(root)
        self.registered(root, first=None)
        sub = self.registration(root)
        self.assertEqual(sub["status"], "FAIL")
        self.assertIn("no first-enrolment date recorded", sub["detail"])
        self.assertIn("--first-enrolment", sub["detail"])

    def test_a_not_applicable_registration_fails_a_trial_with_people(self) -> None:
        root = self.workspace()
        self.agree(root, "human-trial")
        self.approved(root)
        self.study(root, "registration", "record", "--by", "Ana Ruiz", "--not-applicable", "--reason", "pilot")
        sub = self.registration(root)
        self.assertEqual(sub["status"], "FAIL")
        self.assertIn("A trial with people must be registered", sub["detail"])

    def test_an_absent_or_stale_registration_keeps_the_shared_behaviour(self) -> None:
        root = self.workspace()
        self.agree(root, "human-trial")
        self.approved(root)
        sub = self.registration(root)
        self.assertEqual(sub["status"], "PENDING")
        self.assertIn("No registration record yet (study_cli.py registration record)", sub["detail"])
        self.registered(root)
        self.revision(root, 2)
        self.study(root, "protocol", "amend", "--by", "Ana Ruiz", "--reason", "a second school")
        sub = self.registration(root)
        self.assertEqual(sub["status"], "ACTIVE")
        self.assertIn("Stale: the registration record covers an earlier protocol lock", sub["detail"])

    def test_with_no_variant_the_board_applies_the_trial_rules_and_says_so(self) -> None:
        root = self.workspace()
        self.approved(root)
        self.registered(root, date="2026-02-01")
        sub = self.registration(root)
        self.assertEqual(sub["status"], "FAIL")
        self.assertIn("ICMJE", sub["detail"])
        self.assertIn(NO_VARIANT, sub["detail"])
        self.registered(root)
        sub = self.registration(root)
        self.assertEqual(sub["status"], "PASS")
        self.assertIn(NO_VARIANT, sub["detail"])

    def test_a_type_agreed_without_variant_is_treated_as_a_trial(self) -> None:
        root = self.workspace()
        self.agree(root, None)
        self.approved(root)
        self.registered(root, date="2026-02-01")
        sub = self.registration(root)
        self.assertEqual(sub["status"], "FAIL")
        self.assertIn(NO_VARIANT, sub["detail"])

    def test_a_field_experiment_passes_with_any_current_registration(self) -> None:
        root = self.workspace()
        self.agree(root, "field-experiment")
        self.approved(root)
        sub = self.registration(root)
        self.assertEqual(sub["status"], "PENDING")
        self.assertIn("No registration record yet", sub["detail"])
        self.registered(root, date="2026-02-01")
        sub = self.registration(root)
        self.assertEqual(sub["status"], "PASS", sub["detail"])
        self.assertNotIn("ICMJE", sub["detail"])
        self.registered(root, first=None)
        self.assertEqual(self.registration(root)["status"], "PASS")
        self.study(root, "registration", "record", "--by", "Ana Ruiz", "--not-applicable", "--reason",
                   "plot trial, no registry applies")
        sub = self.registration(root)
        self.assertEqual(sub["status"], "PASS")
        self.assertIn("Not applicable, recorded by Ana Ruiz", sub["detail"])


# --------------------------------------------------------------------------- G-ETHICS, G-ALLOCATION


class EthicsAndAllocationTests(TrialBoardCase):
    def test_the_ethics_gate_is_the_shared_record(self) -> None:
        root = self.workspace()
        self.approved(root)
        self.assertEqual(self.gate(self.status(root), "G-ETHICS")["status"], "PENDING")
        self.ethics(root)
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-ETHICS")["status"], "PASS")
        step = self.phase(status, "ethics_consent")
        self.assertEqual(step["status"], "PASS", step["detail"])
        self.assertIn("Approved by School Board IRB (IRB-77)", step["detail"])

    def test_the_allocation_gate_absent_current_and_stale(self) -> None:
        root = self.workspace()
        self.approved(root)
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-ALLOCATION")["status"], "PENDING")
        self.assertIn("No allocation record yet (study_cli.py allocation record)",
                      self.phase(status, "allocation")["detail"])
        self.allocated(root)
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-ALLOCATION")["status"], "PASS")
        step = self.phase(status, "allocation")
        self.assertEqual(step["status"], "PASS", step["detail"])
        self.assertIn("Allocation recorded by Ana Ruiz: method block, 3 row(s); concealment: sealed opaque envelopes",
                      step["detail"])
        # The list changed: stale with its reason.
        self.write(root, "allocation/list.csv", ALLOCATION_LIST + "P-7733,Control-Omega\n")
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-ALLOCATION")["status"], "ACTIVE")
        self.assertIn("Stale (the allocation list changed since it was recorded)",
                      self.phase(status, "allocation")["detail"])
        # An amendment and a removed list: every reason is shown.
        self.revision(root, 2)
        self.study(root, "protocol", "amend", "--by", "Ana Ruiz", "--reason", "a third school")
        (root / "allocation" / "list.csv").unlink()
        detail = self.phase(self.status(root), "allocation")["detail"]
        self.assertIn("Stale (the allocation list is missing; the protocol was amended since it was recorded)",
                      detail)

    def test_a_corrupt_allocation_record_fails(self) -> None:
        root = self.workspace()
        self.write(root, "study/allocation.json", "{not json")
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-ALLOCATION")["status"], "FAIL")
        self.assertIn("The allocation record is unreadable", self.phase(status, "allocation")["detail"])

    def test_the_board_never_shows_the_allocation_list(self) -> None:
        root = self.workspace()
        self.trial(root)
        for lang in ("", "es"):
            text = json.dumps(self.status(root, lang))
            for token in SECRET_TOKENS:
                with self.subTest(lang=lang, token=token):
                    self.assertNotIn(token, text)


# --------------------------------------------------------------------------- G-FLOW


class FlowTests(TrialBoardCase):
    def test_a_trial_with_people_needs_the_signed_flow(self) -> None:
        root = self.workspace()
        self.agree(root, "human-trial")
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-FLOW")["status"], "PENDING")
        self.assertEqual(self.phase(status, "flow_units")["status"], "PENDING")
        self.trial_flow(root, sign=False)
        self.assertEqual(self.gate(self.status(root), "G-FLOW")["status"], "PENDING")
        self.flow(root, "render")
        self.flow(root, "signoff", "--by", "Ana Ruiz")
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-FLOW")["status"], "PASS")
        self.assertEqual(self.phase(status, "flow_units")["status"], "PASS")

    def test_a_field_experiment_keeps_the_flow_optional(self) -> None:
        root = self.workspace()
        self.agree(root, "field-experiment")
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-FLOW")["status"], "PASS")
        step = self.phase(status, "flow_units")
        self.assertEqual(step["status"], "PASS", step["detail"])
        self.assertIn("Optional for a field experiment (not blocking)", step["detail"])
        self.assertIn("experimental units", step["detail"])
        # A flow kept but not signed off is shown as it is, and still never blocks.
        self.trial_flow(root, sign=False)
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-FLOW")["status"], "PASS")
        sub = next(s for s in self.phase(status, "flow_units")["subfases"] if "G-FLOW" in s["name"])
        self.assertIn("Optional for a field experiment (not blocking): Not signed off yet", sub["detail"])

    def test_with_no_variant_the_flow_is_required_and_says_so(self) -> None:
        root = self.workspace()
        status = self.status(root)
        self.assertEqual(self.gate(status, "G-FLOW")["status"], "PENDING")
        sub = next(s for s in self.phase(status, "flow_units")["subfases"] if "G-FLOW" in s["name"])
        self.assertIn(NO_VARIANT, sub["detail"])


# --------------------------------------------------------------------------- locks


class LockTests(TrialBoardCase):
    def test_the_phase_gates_of_the_line(self) -> None:
        board = lines.board(KIND)
        self.assertEqual(dict(board.phase_gates), {"prespecified_analysis": "G-DATA-QC", "writing": "G-FLOW"})
        self.assertEqual(board.transversal, "reporting_intervention")
        analysis = board.actions["prespecified_analysis"]["actions"]
        locked = [a for a in analysis if a.get("requires_all")]
        self.assertEqual(len(locked), 2)
        for action in locked:
            self.assertEqual(action["requires_all"], ["G-STUDY-PROTOCOL", "G-ETHICS", "G-REGISTRATION",
                                                      "G-ALLOCATION", "G-DATA-QC"])

    def test_writing_waits_for_the_flow_of_a_trial_with_people(self) -> None:
        root = self.workspace()
        self.agree(root, "human-trial")
        self.approved(root)
        self.own_data(root)
        self.analysed(root)
        writing = self.phase(self.status(root), "writing")
        self.assertFalse(writing["unlocked"])
        self.assertEqual(writing["blocked_by"], "Fase 8")
        self.trial_flow(root)
        writing = self.phase(self.status(root), "writing")
        self.assertTrue(writing["unlocked"], writing["blocked_by"])

    def test_writing_of_a_field_experiment_does_not_wait_for_a_flow(self) -> None:
        root = self.workspace()
        self.agree(root, "field-experiment")
        self.approved(root)
        self.own_data(root)
        self.analysed(root)
        writing = self.phase(self.status(root), "writing")
        self.assertTrue(writing["unlocked"], writing["blocked_by"])

    def test_the_analysis_waits_for_the_allocation(self) -> None:
        root = self.workspace()
        self.agree(root, "human-trial")
        self.approved(root)
        self.registered(root)
        self.ethics(root)
        self.own_data(root)
        actions = self.phase(self.status(root), "prespecified_analysis")["actions"]
        locked = [a for a in actions if a.get("locked") is not None]
        self.assertTrue(locked)
        for action in locked:
            self.assertTrue(action["locked"])
            self.assertEqual(action["requires"], "G-ALLOCATION")
        self.allocated(root)
        actions = self.phase(self.status(root), "prespecified_analysis")["actions"]
        self.assertFalse(any(a.get("locked") for a in actions))


# --------------------------------------------------------------------------- checklist, read-only, cards, Spanish


class ChecklistTests(TrialBoardCase):
    def test_the_variant_chooses_the_checklist(self) -> None:
        for variant, guideline, items in (("human-trial", "consort-2025", 30), ("field-experiment", "arrive-2", 21)):
            with self.subTest(variant=variant):
                root = self.workspace()
                sub = self.phase(self.status(root), "reporting_intervention")["subfases"][0]
                self.assertIn("No variant agreed yet", sub["detail"])
                self.agree(root, variant)
                sub = self.phase(self.status(root), "reporting_intervention")["subfases"][0]
                self.assertEqual(sub["name"], f"Reporting checklist ({guideline})")
                self.assertIn(f"{items} items", sub["detail"])


class ReadOnlyAndCardTests(TrialBoardCase):
    def test_the_board_never_writes_a_record(self) -> None:
        root = self.workspace()
        self.trial(root)
        watched = ["study", "protocol", "analysis", "datasets", "data", "allocation", "paper",
                   ".papersmith/paper_type.json"]

        def snapshot() -> dict:
            out = {}
            for rel in watched:
                folder = root / rel
                paths = [folder] if folder.is_file() else sorted(p for p in folder.rglob("*") if p.is_file())
                out.update({p.relative_to(root).as_posix(): p.read_bytes() for p in paths})
            return out

        before = snapshot()
        self.assertIn("study/allocation.json", before)
        self.assertIn("study/registration.json", before)
        self.status(root)
        self.status(root, "es")
        self.assertEqual(snapshot(), before)

    def test_a_full_trial_passes_every_operator_gate(self) -> None:
        root = self.workspace()
        self.trial(root)
        status = self.status(root)
        for gate in GATES[:6]:
            with self.subTest(gate=gate):
                self.assertEqual(self.gate(status, gate)["status"], "PASS")
        self.assertTrue(self.phase(status, "writing")["unlocked"])

    def test_every_card_runs_a_real_command(self) -> None:
        root = self.workspace()
        clis = {
            "python skills/_core/empirical/study_cli.py": "skills/_core/empirical/study_cli.py",
            "python skills/_core/empirical/analysis_cli.py": "skills/_core/empirical/analysis_cli.py",
            "python skills/_core/participant_flow/flow_cli.py": "skills/_core/participant_flow/flow_cli.py",
            "python skills/datasets/scripts/datasets_cli.py": "skills/datasets/scripts/datasets_cli.py",
            "python skills/_core/checklists/checklist_cli.py": "skills/_core/checklists/checklist_cli.py",
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
                    if a["kind"] == "command" and re.search(r" (approve|amend|record|own|deidentify|signoff) ",
                                                            a["command"] + " ")]
        self.assertGreaterEqual(len(commands), 9)
        for command in commands:
            with self.subTest(command=command):
                self.assertRegex(command, r'--by "<operator name>"')


class SpanishTests(TrialBoardCase):
    def test_every_label_has_a_spanish_entry(self) -> None:
        for variant in (None, "human-trial", "field-experiment"):
            root = self.workspace()
            states = {
                "empty": lambda: None,
                "agreed": lambda: self.agree(root, variant) if variant else None,
                "revision": lambda: self.revision(root, 1),
                "approved": lambda: self.study(root, "protocol", "approve", "--by", "Ana Ruiz"),
                "unknown registration": lambda: self.registered(root, first=None),
                "retrospective": lambda: self.registered(root, date="2026-02-01"),
                "not applicable": lambda: self.study(root, "registration", "record", "--by", "Ana Ruiz",
                                                     "--not-applicable", "--reason", "pilot"),
                "prospective": lambda: self.registered(root),
                "ethics": lambda: self.ethics(root),
                "allocated": lambda: self.allocated(root),
                "data": lambda: self.own_data(root),
                "analysed": lambda: self.analysed(root),
                "unsigned flow": lambda: self.trial_flow(root, sign=False),
                "signed flow": lambda: (self.flow(root, "render"), self.flow(root, "signoff", "--by", "Ana Ruiz")),
                "stale": lambda: (self.write(root, "allocation/list.csv", ALLOCATION_LIST + "P-1,A\n"),
                                  self.revision(root, 2)),
                "amended": lambda: self.study(root, "protocol", "amend", "--by", "Ana Ruiz", "--reason", "more"),
                "list removed": lambda: (root / "allocation" / "list.csv").unlink(),
            }
            for name, step in states.items():
                step()
                with self.subTest(variant=variant, state=name):
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

    def test_the_spanish_reasons_read_as_spanish(self) -> None:
        root = self.workspace()
        self.agree(root, "human-trial")
        self.approved(root)
        self.registered(root, date="2026-02-01")
        self.allocated(root)
        self.write(root, "allocation/list.csv", ALLOCATION_LIST + "P-1,A\n")
        spanish = self.status(root, "es")
        registration = next(s for s in self.phase(spanish, "protocol_registration")["subfases"]
                            if "G-REGISTRATION" in s["name"])
        self.assertIn("ICMJE", registration["detail"])
        self.assertIn("retrospectivo", registration["detail"])
        self.assertIn("2026-02-01", registration["detail"])
        allocation = self.phase(spanish, "allocation")["detail"]
        self.assertIn("la lista de asignación cambió", allocation)
        self.assertEqual([f["stage_id"] for f in spanish["fases"]], STEPS)


class OtherBoardsTests(unittest.TestCase):
    def test_the_other_tables_keep_their_gate_definitions(self) -> None:
        for kind in ("observational-measurement", "hardware", "lab-simulation"):
            table = empirical_board.LINE_TABLES[kind]
            with self.subTest(kind=kind):
                for gate in table.gates:
                    self.assertIs(empirical_board.gate_definition(table, gate), empirical_board.GATES[gate])
        self.assertIs(empirical_board.gate_definition(empirical_board.LINE_TABLES["data-resource"], "G-DEPOSIT"),
                      empirical_board.GATES["G-DEPOSIT"])
        self.assertEqual(empirical_board.GATES["G-REGISTRATION"].step, "ethics_registration")
        self.assertEqual(empirical_board.GATES["G-FLOW"].step, "participant_flow")

    def test_the_line_defines_its_own_registration_and_flow_gates(self) -> None:
        table = empirical_board.LINE_TABLES[KIND]
        self.assertEqual(sorted(table.gate_defs), ["G-FLOW", "G-REGISTRATION"])
        for gate in ("G-STUDY-PROTOCOL", "G-ETHICS", "G-ALLOCATION", "G-DATA-QC"):
            self.assertIs(empirical_board.gate_definition(table, gate), empirical_board.GATES[gate])


if __name__ == "__main__":
    unittest.main()
