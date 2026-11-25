"""The Study tab's data (paper-type-lines S8, T8-O5, decision E10).

`GET /api/study` answers, for an empirical workspace (an observational-measurement
one here), one JSON object with a section per panel: the protocol and its lock,
the ethics and registration records, the operator's own data (data-use
statement, dictionary summary, QC and de-identification, never a PII value),
the analysis log and the participant flow, plus the reporting guideline of the
agreed variant. Every section is read through the shared modules' own readers
(`skills/_core/empirical`, `participant_flow`, `checklists`, `datasets_cli.py`),
and a malformed or absent record turns only its section unavailable, never the
response into a 500. `GET /api/study/checklist` runs the variant's checklist on
demand only. An experimental or review workspace answers 409 on both routes.
Every record below is written through the real CLIs.
"""

from __future__ import annotations

import inspect
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

import tests.test_experimental_line_characterization as characterization
from papersmith.core import init as init_module
from skills._core.command_center import server, study_view
from skills._core.paper_types import registry
from tests.test_analysis_log import FIELDS, MARKER

REPO = Path(__file__).resolve().parents[1]
PAGE = (REPO / "skills/_core/command_center/static/index.html").read_text(encoding="utf-8")
EMPIRICAL = REPO / "skills" / "_core" / "empirical"
STUDY = EMPIRICAL / "study_cli.py"
ANALYSIS = EMPIRICAL / "analysis_cli.py"
FLOW = REPO / "skills" / "_core" / "participant_flow" / "flow_cli.py"
PAPER_TYPE = REPO / "skills" / "_core" / "paper_types" / "paper_type_cli.py"
KIND = "observational-measurement"
SECTIONS = ("protocol", "ethics", "registration", "data", "analysis", "flow", "reporting")
#: A participant's name in the operator's data: it must never reach the view.
PII_VALUE = "Ana Zuluaga"
CSV = f"id,name,age,group\n1,{PII_VALUE},34,a\n2,Luis Gomez,41,b\n3,Eva Diaz,205,a\n"
ANALYSIS_SCRIPT = "import sys\nprint('ok')\nsys.exit(int(sys.argv[1]) if len(sys.argv) > 1 else 0)\n"
STROBE = {
    "schema": 1, "template": "strobe",
    "stages": {
        "potentially_eligible": {"n": 500},
        "examined": {"n": 450, "excluded": [{"reason": "Could not be contacted", "n": 50}]},
        "eligible": {"n": 400, "excluded": [{"reason": "Did not meet the criteria", "n": 50}]},
        "included": {"n": 350, "excluded": [{"reason": "Declined <to> take part", "n": 50}]},
        "followed": {"n": 330, "excluded": [{"reason": "Lost to follow-up", "n": 20}]},
        "analysed": {"n": 320, "excluded": [{"reason": "Missing exposure data", "n": 10}]},
    },
}


def workspace(case: unittest.TestCase, kind: str = KIND) -> Path:
    holder = tempfile.TemporaryDirectory(prefix="study-view-", ignore_cleanup_errors=True)
    case.addCleanup(holder.cleanup)
    root = Path(holder.name).resolve() / "ws"
    init_module.initialize(root, tools=("claude",), run_npm=False, run_env=False, kind=kind)
    return root


def cli(script: Path, root: Path, *args: str, root_first: bool = False, ok: bool = True) -> dict:
    """One CLI call as the operator or an agent makes it; one JSON object out."""
    argv = list(args)
    if root_first:
        argv = ["--root", str(root), *argv]
    else:
        split = argv.index("--") if "--" in argv else len(argv)
        argv[split:split] = ["--root", str(root)]
    done = subprocess.run([sys.executable, str(script), *argv], capture_output=True, text=True, cwd=str(REPO),
                          timeout=120)
    payload = json.loads(done.stdout) if done.stdout.strip() else {}  # datasets_cli prints indented JSON
    if ok:
        assert done.returncode == 0, (script.name, args, done.stdout, done.stderr)
    return payload


def write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def revision(root: Path, version: int, extra: str = "") -> None:
    write(root, f"protocol/study-protocol-walking-v{version:02d}.md",
          MARKER + f"# Walking study v{version}\n" + FIELDS + extra)


def lock(root: Path) -> None:
    revision(root, 1)
    cli(STUDY, root, "protocol", "approve", "--by", "Ana Ruiz")


def gates(root: Path) -> None:
    cli(STUDY, root, "ethics", "record", "--by", "Ana Ruiz", "--committee", "Ethics Board <UN>", "--code", "EB-12",
        "--date", "2026-01-10", "--consent", "written")
    cli(STUDY, root, "registration", "record", "--by", "Ana Ruiz", "--registry", "OSF", "--id", "osf.io/abc",
        "--date", "2026-03-01", "--first-enrolment", "2026-02-01")


def datasets(root: Path) -> Path:
    data = write(root, "data/cohort.csv", CSV)
    script = root / "skills" / "datasets" / "scripts" / "datasets_cli.py"
    cli(script, root, "own", "--slug", "cohort", "--by", "Ana Ruiz", "--statement", "Consented <use> only",
        root_first=True)
    cli(script, root, "dictionary", "init", "--slug", "cohort", "--file", "data/cohort.csv", root_first=True)
    dictionary = root / "datasets" / "cohort" / "dictionary.json"
    document = json.loads(dictionary.read_text(encoding="utf-8"))
    for column in document["columns"]:
        if column["name"] == "age":
            column["range"] = {"min": 0, "max": 120}
            column["unit"] = "years"
            column["description"] = "Age at enrolment"
    dictionary.write_text(json.dumps(document, indent=2), encoding="utf-8")
    cli(script, root, "qc", "--slug", "cohort", "--file", "data/cohort.csv", root_first=True)
    cli(script, root, "deidentify", "--slug", "cohort", "--by", "Ana Ruiz", "--statement", "Names replaced by ids",
        root_first=True)
    return data


def analyses(root: Path) -> None:
    write(root, "analysis.py", ANALYSIS_SCRIPT)
    cli(ANALYSIS, root, "run", "--outcome", "O1", "--plan", "primary-model", "--input", "data/cohort.csv",
        "--", sys.executable, "analysis.py")
    cli(ANALYSIS, root, "run", "--outcome", "O9", "--note", "post hoc look", "--", sys.executable, "analysis.py", "1")


def flow(root: Path) -> None:
    cli(FLOW, root, "template", "strobe", "--write")
    write(root, "study/flow.json", json.dumps(STROBE))
    cli(FLOW, root, "render")
    cli(FLOW, root, "signoff", "--by", "Ana Ruiz")


def agree(root: Path, variant: str = "observational", type_id: str = KIND) -> None:
    idea = write(root, "idea.txt", "A cross-sectional survey of walking habits and blood glucose in adults.\n"
                                   "We measure HbA1c in a cohort and relate it to daily steps.\n")
    cli(PAPER_TYPE, root, "accept", "--by", "Ana Ruiz", "--idea-file", str(idea))
    cli(PAPER_TYPE, root, "agree", "--type", type_id, "--variant", variant, "--by", "Ana Ruiz")


def build_study(root: Path) -> None:
    """A study half way: protocol locked, ethics and registration recorded, own
    data registered and checked, two analyses logged, the flow signed and the
    observational variant agreed."""
    lock(root)
    gates(root)
    datasets(root)
    analyses(root)
    flow(root)
    agree(root)


class StudyViewCase(unittest.TestCase):
    def client(self, root: Path) -> TestClient:
        return TestClient(server.create_app(root))

    def get(self, root: Path, route: str = "/api/study", lang: str = "") -> dict:
        response = self.client(root).get(route + (f"?lang={lang}" if lang else ""))
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def section(self, view: dict, name: str) -> dict:
        part = view[name]
        self.assertTrue(part["available"], part)
        return part


class ContractTests(StudyViewCase):
    def test_an_empty_study_workspace_answers_every_section(self) -> None:
        view = self.get(workspace(self))
        self.assertEqual(view["paper_kind"], KIND)
        self.assertEqual(view["warnings"], [])
        self.assertNotIn("checklist", view)
        self.assertEqual(self.section(view, "protocol")["state"], "absent")
        self.assertIsNone(self.section(view, "protocol")["latest_revision"])
        self.assertFalse(self.section(view, "ethics")["recorded"])
        self.assertFalse(self.section(view, "registration")["recorded"])
        self.assertEqual(self.section(view, "data")["own"], [])
        self.assertEqual(self.section(view, "analysis")["log"]["state"], "absent")
        self.assertEqual(self.section(view, "analysis")["entries"], [])
        self.assertEqual(self.section(view, "flow")["state"], "absent")
        self.assertIsNone(self.section(view, "reporting")["guideline"])

    def test_the_view_carries_no_server_label_to_translate(self) -> None:
        root = workspace(self)
        build_study(root)
        self.assertEqual(self.get(root, lang="es"), self.get(root))


class ProtocolTests(StudyViewCase):
    def test_the_lock_the_latest_revision_and_the_amendments(self) -> None:
        root = workspace(self)
        lock(root)
        protocol = self.section(self.get(root), "protocol")
        self.assertEqual(protocol["state"], "current")
        self.assertEqual(protocol["revision"], "protocol/study-protocol-walking-v01.md")
        self.assertEqual(protocol["latest_revision"], "protocol/study-protocol-walking-v01.md")
        self.assertEqual((protocol["approved_by"], protocol["amendments"]), ("Ana Ruiz", []))
        revision(root, 2, "\nAdded a sensitivity analysis.\n")
        changed = self.section(self.get(root), "protocol")
        self.assertEqual((changed["state"], changed["reasons"]), ("changed", ["newer-revision"]))
        self.assertEqual(changed["latest_revision"], "protocol/study-protocol-walking-v02.md")
        cli(STUDY, root, "protocol", "amend", "--by", "Ana Ruiz", "--reason", "Sensitivity <analysis> added")
        amended = self.section(self.get(root), "protocol")
        self.assertEqual((amended["state"], amended["revision"]), ("current", "protocol/study-protocol-walking-v02.md"))
        self.assertEqual([(a["by"], a["reason"], a["revision"]) for a in amended["amendments"]],
                         [("Ana Ruiz", "Sensitivity <analysis> added", "protocol/study-protocol-walking-v02.md")])

    def test_a_corrupt_lock_is_stated_and_the_rest_still_answers(self) -> None:
        root = workspace(self)
        build_study(root)
        write(root, "study/protocol.lock.json", "{")
        view = self.get(root)
        protocol = self.section(view, "protocol")
        self.assertEqual(protocol["state"], "corrupt")
        self.assertIn("protocol.lock.json", protocol["message"])
        for name in ("data", "analysis", "flow", "reporting"):
            with self.subTest(section=name):
                self.assertTrue(view[name]["available"], view[name])


class EthicsAndRegistrationTests(StudyViewCase):
    def test_recorded_current_and_the_retrospective_flag(self) -> None:
        root = workspace(self)
        lock(root)
        gates(root)
        view = self.get(root)
        ethics = self.section(view, "ethics")
        self.assertTrue(ethics["recorded"] and ethics["current"])
        self.assertEqual((ethics["status"], ethics["committee"], ethics["code"], ethics["consent"], ethics["by"]),
                         ("approved", "Ethics Board <UN>", "EB-12", "written", "Ana Ruiz"))
        registration = self.section(view, "registration")
        self.assertEqual((registration["status"], registration["registry"], registration["id"]),
                         ("registered", "OSF", "osf.io/abc"))
        self.assertTrue(registration["retrospective"])
        self.assertIn("REGISTRATION_RETROSPECTIVE", [w["code"] for w in registration["warnings"]])

    def test_an_amendment_makes_both_stale(self) -> None:
        root = workspace(self)
        lock(root)
        gates(root)
        revision(root, 2)
        cli(STUDY, root, "protocol", "amend", "--by", "Ana Ruiz", "--reason", "New version")
        view = self.get(root)
        for gate in ("ethics", "registration"):
            with self.subTest(gate=gate):
                part = self.section(view, gate)
                self.assertFalse(part["current"])
                self.assertIn(f"{gate.upper()}_STALE", [w["code"] for w in part["warnings"]])

    def test_not_applicable_states_its_reason(self) -> None:
        root = workspace(self)
        lock(root)
        cli(STUDY, root, "ethics", "record", "--by", "Ana Ruiz", "--not-applicable", "--reason", "Public data only")
        ethics = self.section(self.get(root), "ethics")
        self.assertEqual((ethics["status"], ethics["reason"]), ("not-applicable", "Public data only"))

    def test_a_corrupt_record_turns_only_its_section_unavailable(self) -> None:
        root = workspace(self)
        lock(root)
        gates(root)
        write(root, "study/ethics.json", "[")
        view = self.get(root)
        self.assertEqual((view["ethics"]["available"], view["ethics"]["code"]), (False, "ETHICS_CORRUPT"))
        self.assertTrue(view["registration"]["available"])
        self.assertTrue(view["protocol"]["available"])


class DataTests(StudyViewCase):
    def test_own_data_statement_dictionary_qc_and_deidentification(self) -> None:
        root = workspace(self)
        datasets(root)
        data = self.section(self.get(root), "data")
        self.assertEqual(len(data["own"]), 1)
        entry = data["own"][0]
        self.assertEqual((entry["slug"], entry["role"]), ("cohort", "own"))
        self.assertEqual((entry["data_use"]["statement"], entry["data_use"]["by"]), ("Consented <use> only", "Ana Ruiz"))
        dictionary = entry["dictionary"]
        self.assertEqual((dictionary["state"], dictionary["path"]), ("valid", "datasets/cohort/dictionary.json"))
        self.assertEqual(dictionary["pii"], ["name"])
        self.assertEqual([c["name"] for c in dictionary["columns"]], ["id", "name", "age", "group"])
        self.assertEqual(entry["qc"]["status"], "warn")
        checks = {(c["check"], c["column"]): c for c in entry["qc"]["domain_checks"]}
        self.assertEqual(checks[("out-of-range", "age")]["count"], 1)
        self.assertIn(("pii-column", "name"), checks)
        self.assertTrue(all("values" not in c for c in entry["qc"]["domain_checks"]))
        self.assertTrue(entry["deidentification"]["recorded"])
        self.assertTrue(entry["deidentification"]["current"])
        self.assertEqual(entry["deidentification"]["columns"], ["name"])

    def test_no_pii_value_ever_reaches_the_view(self) -> None:
        root = workspace(self)
        build_study(root)
        text = self.client(root).get("/api/study").text
        for value in (PII_VALUE, "Luis Gomez", "Eva Diaz"):
            with self.subTest(value=value):
                self.assertNotIn(value, text)

    def test_a_changed_file_makes_the_deidentification_stale(self) -> None:
        root = workspace(self)
        data = datasets(root)
        data.write_text(CSV + "4,New Person,50,b\n", encoding="utf-8")
        entry = self.section(self.get(root), "data")["own"][0]
        self.assertFalse(entry["deidentification"]["current"])
        self.assertIn("changed since the de-identification", entry["deidentification"]["problem"])

    def test_a_corrupt_registry_turns_only_its_section_unavailable(self) -> None:
        root = workspace(self)
        build_study(root)
        write(root, "datasets/registry.json", "{not json")
        view = self.get(root)
        self.assertFalse(view["data"]["available"])
        self.assertTrue(view["data"]["code"])
        for name in ("protocol", "ethics", "analysis", "flow"):
            with self.subTest(section=name):
                self.assertTrue(view[name]["available"], view[name])

    def test_a_broken_workspace_datasets_cli_is_named(self) -> None:
        root = workspace(self)
        datasets(root)
        script = root / "skills" / "datasets" / "scripts" / "datasets_cli.py"
        script.write_text("def broken(:\n", encoding="utf-8")
        view = self.get(root)
        self.assertTrue(any("SyntaxError" in w and str(script) in w for w in view["warnings"]), view["warnings"])
        self.assertEqual(self.section(view, "data")["own"][0]["slug"], "cohort")


class AnalysisTests(StudyViewCase):
    def test_entries_with_label_outcome_plan_and_exit_code(self) -> None:
        root = workspace(self)
        lock(root)
        datasets(root)
        analyses(root)
        part = self.section(self.get(root), "analysis")
        self.assertEqual(part["log"]["state"], "ok")
        rows = [(e["id"], e["outcome"], e["plan"], e["label"], e["exit_code"]) for e in part["entries"]]
        self.assertEqual(rows, [("A0002", "O1", "primary-model", "confirmatory", 0),
                                ("A0004", "O9", None, "exploratory", 1)])
        self.assertEqual(part["entries"][1]["label_reason"]["code"], "outcome-not-in-protocol")
        self.assertEqual(part["entries"][1]["note"], "post hoc look")
        self.assertEqual(part["labels"], {"confirmatory": 1, "exploratory": 1})
        self.assertEqual(part["failed_runs"], ["A0004"])
        self.assertEqual((part["interrupted_runs"], part["repairs"]), ([], 0))
        self.assertIn("OUTCOME_NOT_IN_PROTOCOL", [w["code"] for w in part["warnings"]])

    def test_a_torn_log_is_stated_and_its_repair_counted(self) -> None:
        root = workspace(self)
        lock(root)
        datasets(root)
        analyses(root)
        with open(root / "analysis" / "log.jsonl", "ab") as stream:
            stream.write(b'{"seq": 5, "label": "confi')
        torn = self.section(self.get(root), "analysis")
        self.assertEqual(torn["log"]["state"], "torn")
        self.assertIn("ANALYSIS_LOG_TORN", [w["code"] for w in torn["warnings"]])
        cli(ANALYSIS, root, "repair", "--by", "Ana Ruiz")
        repaired = self.section(self.get(root), "analysis")
        self.assertEqual((repaired["log"]["state"], repaired["repairs"]), ("ok", 1))
        self.assertEqual(len(repaired["entries"]), 2)


class FlowTests(StudyViewCase):
    def test_valid_rendered_signed_with_the_counts(self) -> None:
        root = workspace(self)
        flow(root)
        part = self.section(self.get(root), "flow")
        self.assertEqual((part["state"], part["template"], part["figure"]["state"]), ("valid", "strobe", "current"))
        self.assertEqual(part["figure"]["path"], "paper/Figures/participant-flow.svg")
        self.assertTrue(part["figure"]["exists"])
        self.assertTrue(part["signoff"]["current"])
        self.assertEqual(part["signoff"]["by"], "Ana Ruiz")
        stages = {stage["id"]: stage for stage in part["stages"]}
        self.assertEqual([s["id"] for s in part["stages"]],
                         ["potentially_eligible", "examined", "eligible", "included", "followed", "analysed"])
        self.assertEqual(stages["included"]["n"], 350)
        self.assertEqual(stages["included"]["groups"][0]["items"], [{"label": "Declined <to> take part", "n": 50}])

    def test_invalid_counts_list_their_problems_and_unsign_the_flow(self) -> None:
        root = workspace(self)
        flow(root)
        broken = json.loads(json.dumps(STROBE))
        broken["stages"]["eligible"]["n"] = 999
        write(root, "study/flow.json", json.dumps(broken))
        part = self.section(self.get(root), "flow")
        self.assertEqual(part["state"], "invalid")
        self.assertTrue(part["problems"])
        self.assertTrue(all(p.get("code") for p in part["problems"]))
        self.assertEqual(part["stages"], [])
        self.assertFalse(part["signoff"]["current"])

    def test_a_corrupt_sign_off_record_turns_only_its_section_unavailable(self) -> None:
        root = workspace(self)
        build_study(root)
        write(root, "study/flow-signoffs.json", "[")
        view = self.get(root)
        self.assertEqual((view["flow"]["available"], view["flow"]["code"]), (False, "SIGNOFFS_CORRUPT"))
        self.assertTrue(view["analysis"]["available"])


class ModuleTests(StudyViewCase):
    def test_a_missing_shared_module_says_why_in_its_sections(self) -> None:
        root = workspace(self)
        original = dict(study_view.MODULES)
        study_view.MODULES["records"] = "empirical.no_such_module"
        self.addCleanup(study_view.MODULES.update, original)
        view = self.get(root)
        for name in ("protocol", "ethics", "registration"):
            with self.subTest(section=name):
                self.assertEqual((view[name]["available"], view[name]["code"]), (False, study_view.MODULE_UNAVAILABLE))
        self.assertTrue(any("records" in w for w in view["warnings"]), view["warnings"])
        self.assertTrue(view["flow"]["available"])


class ChecklistTests(StudyViewCase):
    def test_the_agreed_variant_names_the_guideline(self) -> None:
        root = workspace(self)
        agree(root)
        reporting = self.section(self.get(root), "reporting")
        self.assertEqual((reporting["type"], reporting["variant"], reporting["guideline"]),
                         (KIND, "observational", "strobe"))

    def test_the_variant_checklist_is_served_on_demand(self) -> None:
        root = workspace(self)
        build_study(root)
        checklist = self.get(root, "/api/study/checklist")
        self.assertTrue(checklist["available"])
        self.assertEqual(checklist["guideline"]["id"], "strobe")
        self.assertEqual([item["item"] for item in checklist["items"]][:3], [1, 2, 3])
        self.assertEqual(len(checklist["items"]), 22)
        self.assertFalse(checklist["paper_available"])
        self.assertTrue(set(checklist["summary"]) >= {"satisfied", "missing", "needs-judgment"})

    def test_without_an_agreed_variant_there_is_no_checklist_data_yet(self) -> None:
        root = workspace(self)
        checklist = self.get(root, "/api/study/checklist")
        self.assertTrue(checklist["available"])
        self.assertIsNone(checklist["guideline"])
        self.assertEqual(checklist["code"], study_view.NO_CHECKLIST)
        self.assertNotIn("items", checklist)

    def test_another_variant_chooses_its_own_guideline(self) -> None:
        root = workspace(self)
        agree(root, "diagnostic-validation")
        self.assertEqual(self.section(self.get(root), "reporting")["guideline"], "stard-2015")

    def test_the_panel_get_never_runs_the_checklist(self) -> None:
        root = workspace(self)
        build_study(root)
        engine = study_view._module("engine")[0]
        original = engine.check

        def refuse(*_args, **_kwargs):  # pragma: no cover - must not run
            raise AssertionError("the checklist ran inside GET /api/study")

        engine.check = refuse
        self.addCleanup(setattr, engine, "check", original)
        self.assertTrue(self.get(root)["reporting"]["available"])

    def test_the_checklist_route_runs_off_the_event_loop(self) -> None:
        source = inspect.getsource(server.create_app)
        route = source[source.index('"/api/study/checklist"'):][:700]
        self.assertIn("async def", route)
        self.assertIn("asyncio.to_thread(study_view.checklist", route)


class OtherLinesTests(StudyViewCase):
    def test_experimental_and_review_workspaces_are_refused_with_409(self) -> None:
        for kind in ("experimental", "review"):
            client = self.client(workspace(self, kind))
            for route in ("/api/study", "/api/study/checklist"):
                with self.subTest(kind=kind, route=route):
                    response = client.get(route)
                    self.assertEqual(response.status_code, 409)
                    body = response.json()
                    self.assertEqual((body["ok"], body["code"], body["paper_kind"]),
                                     (False, study_view.NOT_A_STUDY_WORKSPACE, kind))

    def test_the_experimental_status_is_unchanged(self) -> None:
        for name, lang in (("status-en.json", "en"), ("status-es.json", "es")):
            with self.subTest(golden=name):
                golden = json.loads((characterization.GOLDEN / name).read_text(encoding="utf-8"))
                self.assertEqual(characterization.undeclared(name, golden, characterization.status(lang)), [])

    def test_the_empirical_kinds_are_the_catalogue_families_beyond_the_two_first_lines(self) -> None:
        families = {item["id"] for item in registry.load()} - {"applied-ai", "review"}
        self.assertEqual(set(study_view.EMPIRICAL_KINDS), families)
        self.assertNotIn("experimental", study_view.EMPIRICAL_KINDS)


class StudyTabMarkupTests(unittest.TestCase):
    def test_the_study_tab_follows_the_pipeline_and_lists_the_empirical_kinds(self) -> None:
        buttons = re.findall(r"onclick=\"navigateTab\('([a-z]+)'\)\"", PAGE)
        self.assertEqual(buttons[:4], ["flow", "pipeline", "review", "study"])
        kinds = re.search(r"onclick=\"navigateTab\('study'\)\" data-kinds=\"([^\"]+)\"", PAGE)
        self.assertIsNotNone(kinds)
        self.assertEqual(kinds.group(1).split(), list(study_view.EMPIRICAL_KINDS))
        self.assertIn('<div id="pane-study" class="tab-pane">', PAGE)
        self.assertIn('id="studyPanel"', PAGE)
        self.assertIn('src="./study-panel.js?v=0.82.0"', PAGE)
        self.assertRegex(PAGE, r"if \(tabId === 'study'\) \{?\s*window\.refreshStudyPanel\?\.\(\)")
        self.assertIn("study: () => window.refreshStudyPanel?.()", PAGE)
        allow = re.search(r"\[('pipeline'[^\]]*)\]\.includes\(hash\)", PAGE)
        self.assertIn("'study'", allow.group(1))

    def test_the_tab_stays_hidden_under_the_first_two_lines_and_until_the_line_is_known(self) -> None:
        self.assertIn('body:not([data-paper-kind]) [data-kinds]:not([data-kinds~="experimental"]) '
                      '{ display: none !important; }', PAGE)
        self.assertIn('body[data-paper-kind="experimental"] [data-kinds]:not([data-kinds~="experimental"]), '
                      'body[data-paper-kind="review"] [data-kinds]:not([data-kinds~="review"]) '
                      '{ display: none !important; }', PAGE)


if __name__ == "__main__":
    unittest.main()
