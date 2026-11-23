"""HardwareX and GUM-reporting data for the checklist engine (paper-type-lines S8, T8-C1;
decision F4 of L78 and D11-D13 of L46).

The hardware line reports against the HardwareX article template; the
lab-simulation line (and hardware's calibration) against the GUM's guidance on
reporting an uncertainty (JCGM 100:2008, clause 7). Both data files store only
paraphrased topics, our own questions, the source URL and citation, and decide
nothing deterministically: every item ends at ``needs-judgment`` at best.
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
README = ROOT / "skills" / "_core" / "checklists" / "README.md"

#: The hardware line's contract names, one per HardwareX article section.
HARDWARE_SECTIONS = {"title-and-keywords", "abstract", "specifications-table", "hardware-in-context",
                     "hardware-description", "design-files", "bill-of-materials", "build-instructions",
                     "operation-instructions", "validation-characterization", "back-matter"}
IMRAD = {"abstract", "methods", "results", "discussion"}

#: HardwareX template order: front matter, specifications table, sections 1-7, closing statements.
HARDWAREX_ORDER = (["title-and-keywords", "abstract", "title-and-keywords"] + ["specifications-table"] * 5
                   + ["hardware-in-context"] + ["hardware-description"] * 2 + ["design-files"] * 4
                   + ["bill-of-materials"] * 2 + ["build-instructions"] * 4 + ["operation-instructions"] * 2
                   + ["validation-characterization"] * 3 + ["back-matter"] * 5)
#: GUM clause 7 identifiers, in the clause's order.
GUM_CLAUSES = ["7.1.2", "7.1.4a", "7.1.4b", "7.1.4c", "7.1.4d", "7.2.1a", "7.2.1b", "7.2.1c", "7.2.1",
               "7.2.2", "7.2.3d", "7.2.3e", "7.2.5", "7.2.6", "7.2.7a", "7.2.7b", "7.2.7c", "7.2.7d"]


def run_cli(*argv: str) -> tuple[int, dict]:
    completed = subprocess.run([sys.executable, str(CLI), *argv], capture_output=True, text=True, timeout=300)
    return completed.returncode, json.loads(completed.stdout)


def all_targets_written(data: dict, line: str) -> engine.WorkspaceState:
    blocks = {}
    for entry in data["items"]:
        for target in entry["targets"]["default"]:
            section, _, block = target.partition(".")
            blocks[f"{section}.{block or 'b-text'}"] = "Some reported text."
    sections: dict = {}
    for block_id in blocks:
        section, _, block = block_id.partition(".")
        sections.setdefault(section, set()).add(block)
    return engine.WorkspaceState(root=ROOT, line=line, paper_available=True, blocks=blocks,
                                 declarations=set(), sections=sections)


class SharedDataRules:
    gid = ""
    count = 0
    line = ""
    allowed = set()

    def setUp(self):
        self.data = engine.load_guideline(self.gid)

    def test_the_file_validates_with_its_item_count_numbered_in_order(self):
        self.assertEqual(engine.validate_guideline(self.data, expected_id=self.gid), [])
        self.assertEqual(self.data["item_count"], self.count)
        self.assertEqual([entry["number"] for entry in self.data["items"]], list(range(1, self.count + 1)))
        listed = {entry["id"]: entry for entry in engine.list_guidelines()}
        self.assertEqual(listed[self.gid]["items"], self.count)
        self.assertIn(self.line, self.data["lines"])

    def test_every_item_is_a_question_with_no_deterministic_rule(self):
        for entry in self.data["items"]:
            self.assertTrue(entry.get("question", "").strip(), entry["number"])
            self.assertEqual(entry.get("evidence", []), [], entry["number"])
            self.assertFalse({"text", "description", "wording"} & set(entry), entry["number"])

    def test_targets_are_default_targets_on_the_lines_section_names(self):
        for entry in self.data["items"]:
            self.assertEqual(set(entry["targets"]), {"default"}, entry["number"])
            for target in entry["targets"]["default"]:
                self.assertIn(target, self.allowed, entry["number"])

    def test_no_item_is_satisfied_even_when_every_target_is_written(self):
        result = engine.evaluate(self.data, all_targets_written(self.data, self.line))
        self.assertEqual(result["summary"]["satisfied"], [])
        self.assertEqual(result["summary"]["missing"], [])
        self.assertEqual(result["summary"]["needs-judgment"], list(range(1, self.count + 1)))


class HardwareXDataTests(SharedDataRules, unittest.TestCase):
    gid, count, line, allowed = "hardwarex", 31, "hardware", HARDWARE_SECTIONS

    def test_items_follow_the_template_sections_in_order(self):
        self.assertEqual([entry["targets"]["default"][0] for entry in self.data["items"]], HARDWAREX_ORDER)
        # Every HardwareX section the hardware line declares is covered by at least one item.
        self.assertEqual({entry["targets"]["default"][0] for entry in self.data["items"]}, HARDWARE_SECTIONS)

    def test_the_source_is_the_hardwarex_template_version_2(self):
        self.assertIn("2", self.data["version"])
        self.assertIn("HardwareX", self.data["name"])
        self.assertIn("June 2021", self.data["citation"])
        self.assertIn("10.5281/zenodo.5078227", self.data["citation"])

    def test_ethics_items_say_they_apply_only_when_relevant(self):
        ethics = [e for e in self.data["items"] if e["section"] == "Ethics statements"]
        self.assertEqual(len(ethics), 1)
        self.assertTrue(ethics[0]["question"].startswith("If the work involved "))


class GumReportingDataTests(SharedDataRules, unittest.TestCase):
    gid, count, line, allowed = "gum-reporting", 18, "lab-simulation", IMRAD

    def test_each_item_carries_its_gum_clause_in_order(self):
        prefixes = [entry["topic"].split(" ", 1)[0] for entry in self.data["items"]]
        self.assertEqual(prefixes, GUM_CLAUSES)

    def test_the_source_is_jcgm_100_2008_clause_7(self):
        self.assertIn("JCGM 100:2008", self.data["name"])
        self.assertTrue(self.data["url"].startswith("https://www.bipm.org/"))
        self.assertIn("clause 7", self.data["citation"])
        self.assertIn("hardware", self.data["lines"])

    def test_the_reported_result_is_checked_in_the_abstract_and_results(self):
        by_clause = dict(zip(GUM_CLAUSES, self.data["items"]))
        self.assertEqual(by_clause["7.2.1b"]["targets"]["default"], ["abstract", "results"])
        self.assertEqual(by_clause["7.2.1a"]["targets"]["default"], ["methods"])
        self.assertEqual(by_clause["7.2.7a"]["targets"]["default"], ["methods"])
        self.assertTrue(by_clause["7.2.5"]["question"].startswith("If "))


class ReadmeTests(unittest.TestCase):
    def test_the_readme_lists_both_among_the_shipped_guidelines(self):
        text = README.read_text(encoding="utf-8")
        self.assertIn("| `hardwarex` | HardwareX hardware article template", text)
        self.assertIn("| `gum-reporting` | GUM (JCGM 100:2008) clause 7", text)


class MeasurementWorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._holder = tempfile.TemporaryDirectory(prefix="checklist-measurement-ws-")
        cls.ws = Path(cls._holder.name).resolve() / "ws"
        init_module.initialize(cls.ws, tools=("claude",), run_npm=False, run_env=False)

    @classmethod
    def tearDownClass(cls):
        cls._holder.cleanup()

    def assert_nothing_satisfied(self, gid: str, count: int):
        code, payload = run_cli("check", "--guideline", gid, "--root", str(self.ws), "--json")
        self.assertEqual(code, 0, payload)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["guideline"]["id"], gid)
        self.assertEqual(len(payload["items"]), count)
        self.assertEqual(payload["summary"]["satisfied"], [])
        self.assertEqual(payload["summary"]["needs-judgment"], [])
        self.assertEqual(payload["summary"]["missing"], list(range(1, count + 1)))
        for entry in payload["items"]:
            self.assertTrue(entry["question"], entry["item"])
            self.assertTrue(entry["missing"], entry["item"])
            self.assertTrue(all(m.startswith("text:") for m in entry["missing"]), entry)

    def test_hardwarex_on_a_fresh_workspace_satisfies_nothing(self):
        self.assert_nothing_satisfied("hardwarex", 31)

    def test_gum_reporting_on_a_fresh_workspace_satisfies_nothing(self):
        self.assert_nothing_satisfied("gum-reporting", 18)

    def test_show_prints_each_guideline(self):
        for gid, count in (("hardwarex", 31), ("gum-reporting", 18)):
            code, payload = run_cli("show", gid)
            self.assertEqual((code, payload["ok"], len(payload["guideline"]["items"])), (0, True, count))


if __name__ == "__main__":
    unittest.main()
