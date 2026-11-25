"""Datasheets for Datasets data for the checklist engine (paper-type-lines S8, T8-C2;
decision H1 of L90 and D11-D13 of L46).

The data-resource line reports against the question set of Datasheets for
Datasets (Gebru et al., Commun. ACM 2021). The paper lists its questions as
unnumbered bullets in seven sections; the data file keeps one item per question
in the paper's order, leaves out each section's closing "any other comments"
bullet, stores only paraphrased topics and our own questions, and decides
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

#: The paper's seven sections and how many questions each holds (its closing
#: "any other comments" bullet excluded), in the paper's order.
SECTIONS = (("Motivation", 3), ("Composition", 15), ("Collection process", 11),
            ("Preprocessing/cleaning/labeling", 3), ("Uses", 5), ("Distribution", 6), ("Maintenance", 7))
COUNT = sum(n for _, n in SECTIONS)
#: The data-resource line's contract ids (a Scientific Data descriptor) plus back matter.
ALLOWED_TARGETS = {"title-and-keywords", "abstract", "background-summary", "methods", "data-records",
                   "technical-validation", "usage-notes", "code-availability", "back-matter"}


def run_cli(*argv: str) -> tuple[int, dict]:
    completed = subprocess.run([sys.executable, str(CLI), *argv], capture_output=True, text=True, timeout=300)
    return completed.returncode, json.loads(completed.stdout)


class DatasheetsDataTests(unittest.TestCase):
    def setUp(self):
        self.data = engine.load_guideline("datasheets")

    def test_the_file_validates_with_50_items_numbered_in_order(self):
        self.assertEqual(engine.validate_guideline(self.data, expected_id="datasheets"), [])
        self.assertEqual(COUNT, 50)
        self.assertEqual(self.data["item_count"], COUNT)
        self.assertEqual([entry["number"] for entry in self.data["items"]], list(range(1, COUNT + 1)))
        listed = {entry["id"]: entry for entry in engine.list_guidelines()}
        self.assertEqual(listed["datasheets"]["items"], COUNT)
        self.assertEqual(self.data["lines"], ["data-resource"])

    def test_items_follow_the_papers_seven_sections_in_order(self):
        expected = [name for name, n in SECTIONS for _ in range(n)]
        self.assertEqual([entry["section"] for entry in self.data["items"]], expected)
        for entry in self.data["items"]:
            self.assertTrue(entry["topic"].startswith(entry["section"].split("/")[0] + ": "), entry["number"])

    def test_the_source_is_the_2021_cacm_paper_with_its_doi_and_arxiv_id(self):
        self.assertEqual(self.data["url"], "https://doi.org/10.1145/3458723")
        self.assertIn("Commun ACM 2021;64(12):86-92", self.data["citation"])
        self.assertIn("arXiv:1803.09010", self.data["citation"])

    def test_every_item_is_a_question_with_no_deterministic_rule(self):
        for entry in self.data["items"]:
            self.assertTrue(entry.get("question", "").strip().endswith("?"), entry["number"])
            self.assertEqual(entry.get("evidence", []), [], entry["number"])
            self.assertNotIn("other comments", entry["topic"].lower(), entry["number"])

    def test_targets_are_only_the_data_resource_contract_ids(self):
        for entry in self.data["items"]:
            self.assertEqual(set(entry["targets"]), {"default"}, entry["number"])
            self.assertTrue(entry["targets"]["default"], entry["number"])
            for target in entry["targets"]["default"]:
                self.assertIn(target, ALLOWED_TARGETS, entry["number"])
        first = {}
        for entry in self.data["items"]:
            first.setdefault(entry["section"], entry["targets"]["default"][0])
        self.assertEqual(first, {"Motivation": "background-summary", "Composition": "data-records",
                                 "Collection process": "methods", "Preprocessing/cleaning/labeling": "methods",
                                 "Uses": "usage-notes", "Distribution": "data-records",
                                 "Maintenance": "usage-notes"})
        licence = [e for e in self.data["items"] if e["section"] == "Distribution" and "licen" in e["topic"].lower()]
        self.assertEqual(len(licence), 1)
        self.assertIn("back-matter", licence[0]["targets"]["default"])

    def test_no_item_is_satisfied_even_when_every_target_is_written(self):
        blocks = {}
        for entry in self.data["items"]:
            for target in entry["targets"]["default"]:
                blocks[f"{target}.b-text"] = "Some reported text."
        sections: dict = {}
        for block_id in blocks:
            section, _, block = block_id.partition(".")
            sections.setdefault(section, set()).add(block)
        state = engine.WorkspaceState(root=ROOT, line="data-resource", paper_available=True,
                                      blocks=blocks, declarations=set(), sections=sections)
        result = engine.evaluate(self.data, state)
        self.assertEqual(result["summary"]["satisfied"], [])
        self.assertEqual(result["summary"]["missing"], [])
        self.assertEqual(result["summary"]["needs-judgment"], list(range(1, COUNT + 1)))

    def test_the_readme_lists_datasheets_among_the_shipped_guidelines(self):
        text = README.read_text(encoding="utf-8")
        self.assertIn("| `datasheets` | Datasheets for Datasets", text)
        self.assertIn("| 50 |", text)


class DatasheetsWorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._holder = tempfile.TemporaryDirectory(prefix="checklist-datasheets-ws-")
        cls.ws = Path(cls._holder.name).resolve() / "ws"
        init_module.initialize(cls.ws, tools=("claude",), run_npm=False, run_env=False)

    @classmethod
    def tearDownClass(cls):
        cls._holder.cleanup()

    def test_check_on_a_fresh_workspace_reports_every_item_missing_and_none_satisfied(self):
        code, payload = run_cli("check", "--guideline", "datasheets", "--root", str(self.ws), "--json")
        self.assertEqual(code, 0, payload)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["guideline"]["id"], "datasheets")
        self.assertEqual(len(payload["items"]), COUNT)
        self.assertEqual(payload["summary"]["satisfied"], [])
        self.assertEqual(payload["summary"]["needs-judgment"], [])
        self.assertEqual(payload["summary"]["missing"], list(range(1, COUNT + 1)))
        for entry in payload["items"]:
            self.assertTrue(entry["question"], entry["item"])
            self.assertTrue(all(m.startswith("text:") for m in entry["missing"]), entry)

    def test_show_prints_the_guideline(self):
        code, payload = run_cli("show", "datasheets")
        self.assertEqual(code, 0, payload)
        self.assertEqual(payload["guideline"]["id"], "datasheets")


if __name__ == "__main__":
    unittest.main()
