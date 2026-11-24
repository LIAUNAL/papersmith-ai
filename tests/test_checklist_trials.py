"""CONSORT 2025 and ARRIVE 2.0 data for the checklist engine (paper-type-lines S8,
T8-C3; decision J1 of L100 and D11-D13 of L46).

The experiment-intervention line reports a human trial against CONSORT 2025 and a
field experiment against ARRIVE 2.0 (no formal checklist exists for crop or plot
trials, L11: those answer ARRIVE's design and analysis items where they apply).
Both files keep the guideline's numbering with sub-items folded into their
numbered item, store only paraphrased topics and our own questions, and decide
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

#: The experiment-intervention line's IMRaD contract ids plus back matter.
ALLOWED_TARGETS = {"title-and-keywords", "abstract", "introduction", "methods", "results", "discussion",
                   "limitations", "conclusions", "back-matter"}

#: CONSORT 2025's six checklist sections and the items each holds, in order.
CONSORT_SECTIONS = (("Title and abstract", 1), ("Open science", 4), ("Introduction", 2), ("Methods", 14),
                    ("Results", 7), ("Discussion", 2))
#: ARRIVE 2.0's two sets.
ARRIVE_SECTIONS = (("Essential 10", 10), ("Recommended Set", 11))

GUIDELINES = {
    "consort-2025": {"count": 30, "sections": CONSORT_SECTIONS},
    "arrive-2": {"count": 21, "sections": ARRIVE_SECTIONS},
}


def run_cli(*argv: str) -> tuple[int, dict]:
    completed = subprocess.run([sys.executable, str(CLI), *argv], capture_output=True, text=True, timeout=300)
    return completed.returncode, json.loads(completed.stdout)


class TrialGuidelineDataTests(unittest.TestCase):
    def test_both_files_validate_with_their_item_counts_numbered_in_order(self):
        listed = {entry["id"]: entry for entry in engine.list_guidelines()}
        for gid, spec in GUIDELINES.items():
            with self.subTest(gid):
                data = engine.load_guideline(gid)
                self.assertEqual(engine.validate_guideline(data, expected_id=gid), [])
                self.assertEqual(sum(n for _, n in spec["sections"]), spec["count"])
                self.assertEqual(data["item_count"], spec["count"])
                self.assertEqual([e["number"] for e in data["items"]], list(range(1, spec["count"] + 1)))
                self.assertEqual(listed[gid]["items"], spec["count"])
                self.assertEqual(data["lines"], ["experiment-intervention"])

    def test_items_follow_the_guidelines_sections_in_order(self):
        for gid, spec in GUIDELINES.items():
            with self.subTest(gid):
                data = engine.load_guideline(gid)
                expected = [name for name, n in spec["sections"] for _ in range(n)]
                self.assertEqual([e["section"] for e in data["items"]], expected)

    def test_sources_name_the_publications_and_their_dois(self):
        consort = engine.load_guideline("consort-2025")
        self.assertEqual(consort["url"], "https://doi.org/10.1136/bmj-2024-081123")
        for venue in ("BMJ 2025;389:e081123", "JAMA", "Lancet", "Nat Med", "PLOS Med", "Hopewell S"):
            self.assertIn(venue, consort["citation"])
        arrive = engine.load_guideline("arrive-2")
        self.assertEqual(arrive["url"], "https://doi.org/10.1371/journal.pbio.3000410")
        self.assertIn("PLoS Biol 2020;18(7):e3000410", arrive["citation"])
        self.assertIn("Percie du Sert N", arrive["citation"])
        self.assertIn("field experiment", arrive["citation"])

    def test_every_item_is_a_question_with_no_deterministic_rule(self):
        for gid in GUIDELINES:
            for entry in engine.load_guideline(gid)["items"]:
                with self.subTest(gid=gid, item=entry["number"]):
                    self.assertTrue(entry.get("question", "").strip().endswith("?"))
                    self.assertEqual(entry.get("evidence", []), [])

    def test_targets_are_only_the_line_contract_ids(self):
        for gid in GUIDELINES:
            for entry in engine.load_guideline(gid)["items"]:
                with self.subTest(gid=gid, item=entry["number"]):
                    self.assertEqual(set(entry["targets"]), {"default"})
                    self.assertTrue(entry["targets"]["default"])
                    self.assertTrue(set(entry["targets"]["default"]) <= ALLOWED_TARGETS)

    def test_consort_places_open_science_in_methods_and_back_matter(self):
        items = {e["number"]: e["targets"]["default"] for e in engine.load_guideline("consort-2025")["items"]}
        self.assertEqual(items[1], ["title-and-keywords", "abstract"])
        self.assertEqual(items[2], ["methods", "back-matter"])
        self.assertEqual(items[3], ["methods", "back-matter"])
        self.assertEqual(items[4], ["back-matter"])
        self.assertEqual(items[5], ["back-matter"])
        self.assertTrue(all(items[n] == ["methods"] for n in range(8, 22)))
        self.assertTrue(all(items[n] == ["results"] for n in range(22, 29)))
        self.assertEqual(items[30], ["limitations"])

    def test_arrive_essential_ten_report_design_methods_and_results(self):
        items = {e["number"]: e["targets"]["default"] for e in engine.load_guideline("arrive-2")["items"]}
        self.assertTrue(all("methods" in items[n] for n in range(1, 10)))
        self.assertEqual(items[10], ["results"])
        self.assertEqual(items[11], ["abstract"])
        self.assertIn("limitations", items[17])
        self.assertEqual(items[20], ["back-matter"])

    def test_no_item_is_satisfied_even_when_every_target_is_written(self):
        for gid, spec in GUIDELINES.items():
            with self.subTest(gid):
                data = engine.load_guideline(gid)
                blocks = {f"{t}.b-text": "Some reported text." for e in data["items"] for t in e["targets"]["default"]}
                sections: dict = {}
                for block_id in blocks:
                    section, _, block = block_id.partition(".")
                    sections.setdefault(section, set()).add(block)
                state = engine.WorkspaceState(root=ROOT, line="experiment-intervention", paper_available=True,
                                              blocks=blocks, declarations=set(), sections=sections)
                result = engine.evaluate(data, state)
                self.assertEqual(result["summary"]["satisfied"], [])
                self.assertEqual(result["summary"]["missing"], [])
                self.assertEqual(result["summary"]["needs-judgment"], list(range(1, spec["count"] + 1)))

    def test_the_readme_lists_both_among_the_shipped_guidelines(self):
        text = README.read_text(encoding="utf-8")
        self.assertIn("| `consort-2025` | CONSORT 2025", text)
        self.assertIn("| `arrive-2` | ARRIVE 2.0", text)


class TrialGuidelineWorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._holder = tempfile.TemporaryDirectory(prefix="checklist-trials-ws-")
        cls.ws = Path(cls._holder.name).resolve() / "ws"
        init_module.initialize(cls.ws, tools=("claude",), run_npm=False, run_env=False)

    @classmethod
    def tearDownClass(cls):
        cls._holder.cleanup()

    def test_check_on_a_fresh_workspace_reports_every_item_missing_and_none_satisfied(self):
        for gid, spec in GUIDELINES.items():
            with self.subTest(gid):
                code, payload = run_cli("check", "--guideline", gid, "--root", str(self.ws), "--json")
                self.assertEqual(code, 0, payload)
                self.assertTrue(payload["ok"])
                self.assertEqual(payload["guideline"]["id"], gid)
                self.assertEqual(len(payload["items"]), spec["count"])
                self.assertEqual(payload["summary"]["satisfied"], [])
                self.assertEqual(payload["summary"]["needs-judgment"], [])
                self.assertEqual(payload["summary"]["missing"], list(range(1, spec["count"] + 1)))
                for entry in payload["items"]:
                    self.assertTrue(entry["question"], entry["item"])
                    self.assertTrue(all(m.startswith("text:") for m in entry["missing"]), entry)

    def test_show_prints_each_guideline(self):
        for gid in GUIDELINES:
            code, payload = run_cli("show", gid)
            self.assertEqual(code, 0, payload)
            self.assertEqual(payload["guideline"]["id"], gid)


if __name__ == "__main__":
    unittest.main()
