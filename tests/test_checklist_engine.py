"""The checklist engine (paper-type-lines S7, T7-U4; decisions D11-D13).

A reporting guideline is a data file under ``skills/_core/checklists/guidelines/``;
the engine evaluates a workspace into per-item results ``satisfied`` |
``missing`` | ``needs-judgment``, each with the evidence it used. PRISMA 2020
is ported from ``review_cli.py``'s presence-only ``CHECKLIST`` and must agree
with ``review_cli.py checklist`` item by item on the same workspace.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from papersmith.core import init as init_module
from skills._core.checklists import engine

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "skills" / "_core" / "checklists" / "checklist_cli.py"
GUIDELINES = ROOT / "skills" / "_core" / "checklists" / "guidelines"


def new_tmp(case: unittest.TestCase) -> Path:
    holder = tempfile.TemporaryDirectory(prefix="checklist-engine-")
    case.addCleanup(holder.cleanup)
    return Path(holder.name).resolve()


def run_cli(*argv: str, cwd: Path | None = None) -> tuple[int, dict]:
    completed = subprocess.run([sys.executable, str(CLI), *argv], capture_output=True, text=True,
                               timeout=300, cwd=cwd)
    return completed.returncode, json.loads(completed.stdout)


def guideline(*items: dict, **overrides) -> dict:
    data = {"schema": 1, "id": "test-guideline", "name": "Test guideline", "version": "1",
            "url": "https://example.org/guideline", "citation": "Example, 2026",
            "item_count": len(items), "items": list(items)}
    data.update(overrides)
    return data


def item(number: int = 1, *, targets=None, evidence=(), question: str | None = "Is it reported?") -> dict:
    entry = {"number": number, "section": "Methods", "topic": f"Topic {number}",
             "targets": targets if targets is not None else {"default": ["methods.m-a"]},
             "evidence": list(evidence)}
    if question is not None:
        entry["question"] = question
    return entry


def state(root: Path, *, blocks: dict | None = None, declarations=(), sections=None, line="experimental",
          available: bool = True) -> engine.WorkspaceState:
    blocks = blocks if blocks is not None else {}
    if sections is None:
        sections = {}
        for block_id in blocks:
            section, _, block = block_id.partition(".")
            sections.setdefault(section, set()).add(block)
    return engine.WorkspaceState(root=root, line=line, paper_available=available, blocks=dict(blocks),
                                 declarations=set(declarations), sections=sections)


def one(result: dict) -> dict:
    (only,) = result["items"]
    return only


# --------------------------------------------------------------------------- data files


class GuidelineDataTests(unittest.TestCase):
    def test_every_shipped_guideline_validates_with_its_documented_item_count(self):
        counts = {"prisma-2020": 27, "strobe": 22, "stard-2015": 30}
        listed = {entry["id"]: entry for entry in engine.list_guidelines()}
        self.assertEqual(set(listed), set(counts))
        for gid, count in counts.items():
            data = engine.load_guideline(gid)
            self.assertEqual(engine.validate_guideline(data, expected_id=gid), [])
            self.assertEqual(len(data["items"]), count, gid)
            self.assertEqual([i["number"] for i in data["items"]], list(range(1, count + 1)), gid)
            self.assertEqual(listed[gid]["items"], count)
            self.assertTrue(data["url"].startswith("https://"), gid)

    def test_the_data_stores_short_paraphrased_topics_never_item_text(self):
        for path in GUIDELINES.glob("*.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            for entry in data["items"]:
                self.assertLessEqual(len(entry["topic"]), engine.TOPIC_MAX, (path.name, entry["number"]))
                self.assertLessEqual(len(entry.get("question", "")), engine.QUESTION_MAX,
                                     (path.name, entry["number"]))
                self.assertFalse({"text", "description", "wording"} & set(entry), (path.name, entry["number"]))

    def test_the_prisma_port_carries_review_clis_topics_targets_and_records(self):
        sys.path.insert(0, str(ROOT / "skills" / "systematic-review" / "scripts"))
        try:
            import review_cli
        finally:
            sys.path.pop(0)
        data = engine.load_guideline("prisma-2020")
        self.assertEqual(data["url"], review_cli.PRISMA_URL)
        for (number, topic, targets, _record), entry in zip(review_cli.CHECKLIST, data["items"]):
            self.assertEqual((entry["number"], entry["topic"]), (number, topic))
            self.assertEqual(entry["targets"], {"review": list(targets)})

    def test_strobe_and_stard_point_at_generic_section_names(self):
        generic = {"title-and-keywords", "abstract", "introduction", "methods", "results", "discussion",
                   "back-matter"}
        for gid in ("strobe", "stard-2015"):
            for entry in engine.load_guideline(gid)["items"]:
                self.assertEqual(set(entry["targets"]), {"default"}, (gid, entry["number"]))
                for target in entry["targets"]["default"]:
                    self.assertIn(target.split(".")[0], generic, (gid, entry["number"]))

    def test_validation_names_each_problem(self):
        bad = guideline(item(1, question=None), item(1), item(3, evidence=[{"kind": "telepathy"}]))
        bad["items"][2]["topic"] = "x" * (engine.TOPIC_MAX + 1)
        bad["items"].append(item(4, evidence=[{"kind": "file", "path": "/etc/passwd"}]))
        bad["items"].append(item(5, evidence=[{"kind": "file", "path": "../outside"}]))
        bad["items"].append(item(6, evidence=[{"kind": "command", "script": "bin/x.py", "argv": [],
                                               "expect": {"ok": True}}]))
        problems = "\n".join(engine.validate_guideline(bad, expected_id="other-id"))
        for fragment in ("id 'test-guideline' does not match", "item_count 3 but 6 items",
                         "item 1: neither a content rule nor a question", "number 1 repeats",
                         "unknown rule kind 'telepathy'", "topic is longer than", "'/etc/passwd' is not a relative",
                         "'../outside' is not a relative", "script must be a .py file under skills/"):
            self.assertIn(fragment, problems)

    def test_an_invalid_data_file_is_refused_when_loaded(self):
        tmp = new_tmp(self)
        (tmp / "broken.json").write_text(json.dumps(guideline(item(1, question=None))), encoding="utf-8")
        with self.assertRaises(engine.ChecklistRefusal) as caught:
            engine.load_guideline("broken", directory=tmp)
        self.assertEqual(caught.exception.code, "GUIDELINE_INVALID")
        with self.assertRaises(engine.ChecklistRefusal) as caught:
            engine.load_guideline("absent", directory=tmp)
        self.assertEqual(caught.exception.code, "GUIDELINE_UNKNOWN")
        with self.assertRaises(engine.ChecklistRefusal) as caught:
            engine.load_guideline("../broken", directory=tmp)
        self.assertEqual(caught.exception.code, "GUIDELINE_UNKNOWN")


# --------------------------------------------------------------------------- predicates


class PredicateTests(unittest.TestCase):
    def setUp(self):
        self.root = new_tmp(self)

    def evaluate(self, entry: dict, workspace: engine.WorkspaceState) -> dict:
        return one(engine.evaluate(guideline(entry), workspace))

    def test_text_targets_written_empty_and_unresolved(self):
        written = state(self.root, blocks={"methods.m-a": "We enrolled adults.\n"})
        self.assertEqual(self.evaluate(item(), written)["presence"], "satisfied")
        empty = self.evaluate(item(), state(self.root, blocks={"methods.m-a": ""}))
        self.assertEqual((empty["status"], empty["missing"]), ("missing", ["text:methods.m-a"]))
        section = self.evaluate(item(targets={"default": ["methods"]}), written)
        self.assertEqual(section["presence"], "satisfied")
        unresolved = self.evaluate(item(targets={"default": ["methods"]}),
                                   state(self.root, blocks={}, sections={"materials-and-methods": {"mm-a"}}))
        self.assertEqual(unresolved["status"], "missing")
        detail = unresolved["evidence"][0]["detail"]
        self.assertIn("no section 'methods'", detail)
        self.assertIn("materials-and-methods", detail)
        declared = self.evaluate(item(), state(self.root, blocks={}, sections={"methods": {"m-a"}}))
        self.assertIn("not written yet", declared["evidence"][0]["detail"])

    def test_targets_follow_the_workspace_line(self):
        entry = item(targets={"review": ["methods.m-a"]})
        review = self.evaluate(entry, state(self.root, blocks={"methods.m-a": "x"}, line="review"))
        self.assertEqual(review["presence"], "satisfied")
        other = self.evaluate(entry, state(self.root, blocks={"methods.m-a": "x"}, line="experimental"))
        self.assertEqual(other["status"], "missing")
        self.assertIn("no target for the 'experimental' line", other["evidence"][0]["detail"])

    def test_file_record_and_record_field_values(self):
        ws = state(self.root, blocks={"methods.m-a": "x"})
        rules = [{"kind": "file", "path": "review/lock.json"},
                 {"kind": "record", "path": "review/rows.jsonl"},
                 {"kind": "record", "path": "review/rows.jsonl", "field": "stage", "values": ["ta", "ft"]},
                 {"kind": "record", "path": "review/doc.json", "pointer": "objective"}]
        result = self.evaluate(item(evidence=rules), ws)
        self.assertEqual(result["status"], "missing")
        self.assertEqual(result["missing"], ["file:review/lock.json", "record:review/rows.jsonl",
                                             "record:review/rows.jsonl[stage=ta,ft]", "record:review/doc.json#objective"])
        (self.root / "review").mkdir()
        (self.root / "review" / "lock.json").write_text("", encoding="utf-8")
        (self.root / "review" / "rows.jsonl").write_text('{"stage": "ta"}\n', encoding="utf-8")
        (self.root / "review" / "doc.json").write_text('{"objective": ""}', encoding="utf-8")
        result = self.evaluate(item(evidence=rules), ws)
        self.assertEqual(result["missing"], ["record:review/rows.jsonl[stage=ta,ft]", "record:review/doc.json#objective"])
        (self.root / "review" / "rows.jsonl").write_text('{"stage": "ta"}\n{"stage": "ft"}\n', encoding="utf-8")
        (self.root / "review" / "doc.json").write_text('{"objective": "Map the field."}', encoding="utf-8")
        result = self.evaluate(item(evidence=rules), ws)
        self.assertEqual((result["presence"], result["status"]), ("satisfied", "needs-judgment"))

    def test_a_corrupt_record_fails_its_rule_with_the_reason(self):
        (self.root / "rows.jsonl").write_text("{not json\n", encoding="utf-8")
        result = self.evaluate(item(evidence=[{"kind": "record", "path": "rows.jsonl"}]),
                               state(self.root, blocks={"methods.m-a": "x"}))
        self.assertEqual(result["status"], "missing")
        self.assertIn("line 1 is not JSON", result["evidence"][1]["detail"])

    def test_declaration(self):
        entry = item(evidence=[{"kind": "declaration", "name": "ethics-approval"}])
        absent = self.evaluate(entry, state(self.root, blocks={"methods.m-a": "x"}))
        self.assertEqual(absent["missing"], ["declaration:ethics-approval"])
        present = self.evaluate(entry, state(self.root, blocks={"methods.m-a": "x"}, declarations={"ethics-approval"}))
        self.assertEqual(present["presence"], "satisfied")

    def test_command_reuses_a_skill_validator_and_compares_its_answer(self):
        script = self.root / "skills" / "x" / "check.py"
        script.parent.mkdir(parents=True)
        script.write_text("import json, sys\nprint(json.dumps({'ok': sys.argv[2] == 'good', 'root': sys.argv[1]}))\n",
                          encoding="utf-8")
        ws = state(self.root, blocks={"methods.m-a": "x"})

        def rule(arg):
            return {"kind": "command", "script": "skills/x/check.py", "argv": ["{root}", arg], "expect": {"ok": True}}

        self.assertEqual(self.evaluate(item(evidence=[rule("good")]), ws)["presence"], "satisfied")
        bad = self.evaluate(item(evidence=[rule("bad")]), ws)
        self.assertEqual(bad["missing"], ["command:skills/x/check.py"])
        self.assertIn("'ok' is False", bad["evidence"][1]["detail"])
        absent = self.evaluate(item(evidence=[{**rule("good"), "script": "skills/x/absent.py"}]), ws)
        self.assertIn("does not exist", absent["evidence"][1]["detail"])

    def test_number_in_a_block_equals_a_record_value(self):
        (self.root / "prisma.json").write_text(json.dumps({"included": {"studies": 1234}}), encoding="utf-8")
        rule = {"kind": "number", "path": "prisma.json", "pointer": "included.studies"}
        entry = item(evidence=[rule], question=None)
        agrees = self.evaluate(entry, state(self.root, blocks={"methods.m-a": "We included 1{,}234 studies (n = 1,234)."}))
        self.assertEqual(agrees["status"], "satisfied")
        self.assertEqual(agrees["evidence"][1]["value"], 1234)
        disagrees = self.evaluate(entry, state(self.root, blocks={"methods.m-a": "We included 1,233 studies."}))
        self.assertEqual(disagrees["status"], "missing")
        self.assertEqual(disagrees["presence"], "satisfied")
        self.assertIn("1234", disagrees["evidence"][1]["detail"])
        self.assertEqual(disagrees["missing"], ["number:prisma.json#included.studies"])
        no_record = self.evaluate(item(evidence=[{**rule, "pointer": "included.reports"}], question=None),
                                  state(self.root, blocks={"methods.m-a": "1234"}))
        self.assertEqual(no_record["status"], "missing")
        self.assertIn("not a number", no_record["evidence"][1]["detail"])

    def test_term_present_in_a_block_folds_case_accents_and_dashes(self):
        entry = item(evidence=[{"kind": "term", "any": ["case-control", "cohort"], "in": ["title-and-keywords"]}],
                     targets={"default": ["title-and-keywords"]}, question=None)
        hit = self.evaluate(entry, state(self.root, blocks={"title-and-keywords.title": "A Case--Control study"}))
        self.assertEqual(hit["status"], "satisfied")
        self.assertEqual(hit["evidence"][1]["matched"], "case-control")
        miss = self.evaluate(entry, state(self.root, blocks={"title-and-keywords.title": "A cohortative essay"}))
        self.assertEqual((miss["status"], miss["missing"]), ("missing", ["term:case-control|cohort"]))

    def test_needs_judgment_is_never_auto_satisfied(self):
        (self.root / "n.json").write_text('{"n": 3}', encoding="utf-8")
        entry = item(evidence=[{"kind": "term", "any": ["cohort"]},
                               {"kind": "number", "path": "n.json", "pointer": "n"}],
                     question="Are the follow-up methods described?")
        result = self.evaluate(entry, state(self.root, blocks={"methods.m-a": "A cohort of 3 sites."}))
        self.assertEqual(result["status"], "needs-judgment")
        self.assertEqual(result["question"], "Are the follow-up methods described?")
        self.assertTrue(all(e["ok"] for e in result["evidence"]))

    def test_an_unscaffolded_paper_reports_every_target_unwritten(self):
        result = self.evaluate(item(), state(self.root, blocks={}, sections={}, available=False))
        self.assertEqual(result["missing"], ["text:methods.m-a"])
        self.assertIn("paper/main.tex is not scaffolded", result["evidence"][0]["detail"])


# --------------------------------------------------------------------------- workspaces


class ReviewWorkspaceCase(unittest.TestCase):
    """One review workspace per class; the parity test walks it through states."""

    @classmethod
    def setUpClass(cls):
        cls._holder = tempfile.TemporaryDirectory(prefix="checklist-engine-ws-")
        cls.ws = Path(cls._holder.name).resolve() / "ws"
        init_module.initialize(cls.ws, tools=("claude",), run_npm=False, run_env=False, kind="review")
        cls.paper = cls.ws / "skills" / "paper-writing" / "scripts" / "paper_cli.py"
        cls.review = cls.ws / "skills" / "systematic-review" / "scripts" / "review_cli.py"

    @classmethod
    def tearDownClass(cls):
        cls._holder.cleanup()

    def run_ws(self, cli: Path, *argv: str) -> dict:
        completed = subprocess.run([sys.executable, str(cli), *argv], cwd=self.ws, capture_output=True,
                                   text=True, timeout=300)
        return json.loads(completed.stdout)

    def write_block(self, block: str, text: str) -> None:
        self.run_ws(self.paper, "open", "--block", block, "--at-end")
        body = self.ws.parent / "body.tex"
        body.write_text(text, encoding="utf-8")
        result = self.run_ws(self.paper, "substitute", "--block", block, "--body", str(body))
        self.assertEqual(result.get("status"), "ok", result)

    def assert_parity(self) -> dict:
        reference = self.run_ws(self.review, "checklist")
        result = engine.check("prisma-2020", self.ws)
        self.assertEqual(len(result["items"]), 27)
        for expected, got in zip(reference["items"], result["items"]):
            self.assertEqual(got["item"], expected["item"])
            self.assertEqual(got["presence"], "satisfied" if expected["status"] == "satisfied" else "missing",
                             (expected, got))
            self.assertEqual([m for m in got["missing"] if m.startswith(("text:", "declaration:"))],
                             [m for m in expected["missing"] if m.startswith(("text:", "declaration:"))],
                             (expected, got))
            # The record verdict on its own, so a record rule is pinned even while its text is unwritten.
            record_owed = any(m.startswith("record:") for m in expected["missing"])
            rules_owed = any(not e["ok"] for e in got["evidence"] if e["rule"] in ("file", "record", "command"))
            self.assertEqual(rules_owed, record_owed, (expected, got))
            if expected["status"] == "satisfied":
                self.assertNotEqual(got["status"], "missing", got)
        return result


class PrismaParityTests(ReviewWorkspaceCase):
    def test_presence_verdicts_equal_review_cli_checklist_through_the_review(self):
        # 1. Nothing written, no record: every item owes.
        fresh = self.assert_parity()
        self.assertEqual(fresh["summary"]["missing"], list(range(1, 28)))
        self.assertTrue(fresh["notes"])

        # 2. Scaffolded, a few blocks written, the protocol approved, records on file.
        self.assertEqual(self.run_ws(self.paper, "scaffold")["status"], "ok")
        self.assert_parity()
        sys.path.insert(0, str(ROOT / "tests"))
        try:
            from test_systematic_review import PROTOCOL
        finally:
            sys.path.pop(0)
        review = self.ws / "review"
        review.mkdir(exist_ok=True)
        (review / "protocol.json").write_text(json.dumps(PROTOCOL), encoding="utf-8")
        self.assertTrue(self.run_ws(self.review, "protocol", "approve", "--by", "Operator")["ok"])
        (review / "searches.jsonl").write_text('{"id": "S1"}\n', encoding="utf-8")
        (review / "screening.jsonl").write_text('{"stage": "ta"}\n', encoding="utf-8")
        self.write_block("title-and-keywords.title", "Graph neural networks in drug discovery: a systematic review\n")
        self.write_block("methods.m-eligibility", "Studies were eligible when they evaluated a GNN on molecules.\n")
        self.write_block("results.r-study-selection",
                         "The searches identified 4 records; after screening, 1 study was included.\n")
        middle = self.assert_parity()
        by_item = {entry["item"]: entry for entry in middle["items"]}
        self.assertEqual(by_item[1]["status"], "satisfied")  # term "systematic review" in the title
        self.assertEqual(by_item[5]["status"], "needs-judgment")  # present; its content needs a reader
        self.assertEqual(by_item[8]["status"], "missing")  # screening has no full-text stage yet

        # 3. Both screening stages, the flow on file, the registration declared.
        (review / "screening.jsonl").write_text('{"stage": "ta"}\n{"stage": "ft"}\n', encoding="utf-8")
        (review / "prisma.json").write_text(json.dumps({"identification": {"records": 4},
                                                        "screening": {"records_screened": 3},
                                                        "included": {"studies": 1}}), encoding="utf-8")
        figures = self.ws / "paper" / "Figures"
        figures.mkdir(parents=True, exist_ok=True)
        (figures / "prisma-flow.svg").write_text("<svg/>", encoding="utf-8")
        self.run_ws(self.paper, "declare", "--declaration", "review-registration", "--value", "OSF 10.17605/OSF.IO/ABCDE")
        late = self.assert_parity()
        by_item = {entry["item"]: entry for entry in late["items"]}
        self.assertEqual(by_item[16]["presence"], "satisfied")
        numbers = [e for e in by_item[16]["evidence"] if e["rule"] == "number"]
        self.assertEqual([(e["value"], e["ok"]) for e in numbers], [(4, True), (1, True)])
        self.assertEqual(by_item[16]["status"], "needs-judgment")
        self.assertEqual(by_item[24]["missing"], ["text:methods.m-protocol-registration"])


class CliTests(ReviewWorkspaceCase):
    def test_list_and_show(self):
        code, listing = run_cli("list")
        self.assertEqual(code, 0)
        self.assertEqual({(g["id"], g["items"]) for g in listing["guidelines"]},
                         {("prisma-2020", 27), ("strobe", 22), ("stard-2015", 30)})
        code, shown = run_cli("show", "strobe")
        self.assertEqual((code, shown["ok"], len(shown["guideline"]["items"])), (0, True, 22))

    def test_typed_refusals(self):
        code, payload = run_cli("show", "consort-1900")
        self.assertEqual((code, payload["error"]), (2, "GUIDELINE_UNKNOWN"))
        code, payload = run_cli("check", "--guideline", "consort-1900", "--root", str(self.ws), "--json")
        self.assertEqual((code, payload["error"]), (2, "GUIDELINE_UNKNOWN"))
        code, payload = run_cli("check", "--guideline", "strobe", "--root", str(new_tmp(self)), "--json")
        self.assertEqual((code, payload["error"]), (2, "NOT_A_WORKSPACE"))
        code, payload = run_cli("check", "--root", str(self.ws))
        self.assertEqual((code, payload["error"]), (2, "USAGE"))
        code, payload = run_cli("frobnicate")
        self.assertEqual((code, payload["error"]), (2, "USAGE"))

    def test_check_prints_one_json_object_and_reports_unresolved_targets(self):
        code, payload = run_cli("check", "--guideline", "stard-2015", "--root", str(self.ws), "--json")
        self.assertEqual(code, 0, payload)
        self.assertEqual((payload["ok"], payload["guideline"]["id"], payload["line"]), (True, "stard-2015", "review"))
        self.assertEqual(len(payload["items"]), 30)
        self.assertEqual(sorted(payload["summary"]["missing"] + payload["summary"]["needs-judgment"]
                                + payload["summary"]["satisfied"]), list(range(1, 31)))
        self.assertEqual(payload["summary"]["satisfied"], [])
        details = [e["detail"] for entry in payload["items"] for e in entry["evidence"] if not e["ok"]]
        self.assertTrue(details)

    def test_check_without_json_prints_a_readable_table(self):
        completed = subprocess.run([sys.executable, str(CLI), "check", "--guideline", "prisma-2020",
                                    "--root", str(self.ws)], capture_output=True, text=True, timeout=300)
        self.assertEqual(completed.returncode, 0, completed.stdout)
        self.assertIn("PRISMA 2020", completed.stdout)
        self.assertIn(" 1  ", completed.stdout)


class ExperimentalWorkspaceTests(unittest.TestCase):
    def test_strobe_on_a_workspace_without_its_sections_says_which_are_unresolved(self):
        ws = new_tmp(self) / "ws"
        init_module.initialize(ws, tools=("claude",), run_npm=False, run_env=False)
        paper = ws / "skills" / "paper-writing" / "scripts" / "paper_cli.py"
        subprocess.run([sys.executable, str(paper), "scaffold"], cwd=ws, capture_output=True, timeout=300)
        result = engine.check("strobe", ws)
        self.assertEqual(result["line"], "experimental")
        methods = next(entry for entry in result["items"] if entry["item"] == 4)
        self.assertEqual(methods["status"], "missing")
        self.assertIn("no section 'methods'", methods["evidence"][0]["detail"])
        intro = next(entry for entry in result["items"] if entry["item"] == 2)
        self.assertIn("not written yet", intro["evidence"][0]["detail"])


if __name__ == "__main__":
    unittest.main()
