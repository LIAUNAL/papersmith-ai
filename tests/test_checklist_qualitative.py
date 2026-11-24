"""SRQR, COREQ and ACCORD data for the checklist engine (paper-type-lines S8,
T8-C4; decision K1 of L112 and D11-D13 of L46).

The qualitative-participatory line reports a qualitative or mixed study against
SRQR (or COREQ for interview and focus-group studies) and a consensus or
foresight study against ACCORD. Each file keeps the guideline's numbering (ACCORD's
section codes T1 ... O3 become 1-35, each topic starting with its code), stores
only paraphrased topics and our own questions, and decides nothing
deterministically: every item ends at ``needs-judgment`` at best.
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

# The line's contracts do not exist yet (T8-L6 creates them); T8-L6 switches this to derive the ids from them.
LINE_SECTION_IDS = {"title-and-keywords", "abstract", "introduction", "methods", "results", "discussion",
                    "limitations", "conclusions", "back-matter"}

#: SRQR's six sections and the items each holds, in order.
SRQR_SECTIONS = (("Title and abstract", 2), ("Introduction", 2), ("Methods", 11), ("Results", 2),
                 ("Discussion", 2), ("Other", 2))
#: COREQ's three domains.
COREQ_SECTIONS = (("Domain 1: Research team and reflexivity", 8), ("Domain 2: Study design", 15),
                  ("Domain 3: Analysis and findings", 9))
#: ACCORD's sections (methods split by its sub-headings).
ACCORD_SECTIONS = (("Title", 1), ("Introduction", 3), ("Methods: registration", 1),
                   ("Methods: steering committee and panel", 4), ("Methods: preparatory research", 3),
                   ("Methods: assessing consensus", 11), ("Methods: participation", 2), ("Results", 5),
                   ("Discussion", 2), ("Other information", 3))
ACCORD_CODES = (["T1"] + [f"I{n}" for n in range(1, 4)] + [f"M{n}" for n in range(1, 22)]
                + [f"R{n}" for n in range(1, 6)] + ["D1", "D2"] + [f"O{n}" for n in range(1, 4)])

GUIDELINES = {
    "srqr": {"count": 21, "sections": SRQR_SECTIONS},
    "coreq": {"count": 32, "sections": COREQ_SECTIONS},
    "accord": {"count": 35, "sections": ACCORD_SECTIONS},
}


def run_cli(*argv: str) -> tuple[int, dict]:
    completed = subprocess.run([sys.executable, str(CLI), *argv], capture_output=True, text=True, timeout=300)
    return completed.returncode, json.loads(completed.stdout)


def targets_of(gid: str) -> dict[int, list[str]]:
    return {e["number"]: e["targets"]["default"] for e in engine.load_guideline(gid)["items"]}


class QualitativeGuidelineDataTests(unittest.TestCase):
    def test_the_files_validate_with_their_item_counts_numbered_in_order(self):
        listed = {entry["id"]: entry for entry in engine.list_guidelines()}
        for gid, spec in GUIDELINES.items():
            with self.subTest(gid):
                data = engine.load_guideline(gid)
                self.assertEqual(engine.validate_guideline(data, expected_id=gid), [])
                self.assertEqual(sum(n for _, n in spec["sections"]), spec["count"])
                self.assertEqual(data["item_count"], spec["count"])
                self.assertEqual([e["number"] for e in data["items"]], list(range(1, spec["count"] + 1)))
                self.assertEqual(listed[gid]["items"], spec["count"])
                self.assertEqual(data["lines"], ["qualitative-participatory"])

    def test_items_follow_the_guidelines_sections_in_order(self):
        for gid, spec in GUIDELINES.items():
            with self.subTest(gid):
                data = engine.load_guideline(gid)
                expected = [name for name, n in spec["sections"] for _ in range(n)]
                self.assertEqual([e["section"] for e in data["items"]], expected)

    def test_accord_topics_start_with_the_checklist_codes(self):
        topics = [e["topic"] for e in engine.load_guideline("accord")["items"]]
        self.assertEqual([t.split(" ", 1)[0] for t in topics], ACCORD_CODES)

    def test_sources_name_the_publications_and_their_dois(self):
        srqr = engine.load_guideline("srqr")
        self.assertEqual(srqr["url"], "https://doi.org/10.1097/ACM.0000000000000388")
        for part in ("O'Brien BC", "Cook DA", "Acad Med 2014;89(9):1245-1251"):
            self.assertIn(part, srqr["citation"])
        coreq = engine.load_guideline("coreq")
        self.assertEqual(coreq["url"], "https://doi.org/10.1093/intqhc/mzm042")
        for part in ("Tong A", "Craig J", "Int J Qual Health Care 2007;19(6):349-357", "interviews and focus groups"):
            self.assertIn(part, coreq["citation"])
        accord = engine.load_guideline("accord")
        self.assertEqual(accord["url"], "https://doi.org/10.1371/journal.pmed.1004326")
        for part in ("Gattrell WT", "PLoS Med 2024;21(1):e1004326", "Delphi"):
            self.assertIn(part, accord["citation"])

    def test_every_item_is_a_question_with_no_deterministic_rule(self):
        for gid in GUIDELINES:
            for entry in engine.load_guideline(gid)["items"]:
                with self.subTest(gid=gid, item=entry["number"]):
                    self.assertTrue(entry.get("question", "").strip().endswith("?"))
                    self.assertEqual(entry.get("evidence", []), [])

    def test_targets_are_only_the_line_section_ids(self):
        for gid in GUIDELINES:
            for entry in engine.load_guideline(gid)["items"]:
                with self.subTest(gid=gid, item=entry["number"]):
                    self.assertEqual(set(entry["targets"]), {"default"})
                    self.assertTrue(entry["targets"]["default"])
                    self.assertLessEqual(set(entry["targets"]["default"]), LINE_SECTION_IDS)

    def test_reflexivity_and_ethics_go_to_methods_funding_and_conflicts_to_back_matter(self):
        srqr = targets_of("srqr")
        self.assertEqual(srqr[1], ["title-and-keywords"])
        self.assertEqual(srqr[2], ["abstract"])
        self.assertTrue(all(srqr[n] == ["methods"] for n in range(5, 16)))
        self.assertEqual(srqr[19], ["limitations"])
        self.assertEqual(srqr[20], ["back-matter"])
        self.assertEqual(srqr[21], ["back-matter"])
        coreq = targets_of("coreq")
        self.assertTrue(all(coreq[n] == ["methods"] for n in range(1, 9)))
        self.assertTrue(all("methods" in coreq[n] for n in range(9, 24)))
        self.assertEqual(coreq[29], ["results"])
        accord = targets_of("accord")
        self.assertEqual(accord[1], ["title-and-keywords"])
        self.assertTrue(all("methods" in accord[n] for n in range(5, 26)))
        self.assertIn("limitations", accord[31])
        self.assertEqual(accord[34], ["back-matter"])
        self.assertEqual(accord[35], ["back-matter"])

    def test_no_item_is_satisfied_even_when_every_target_is_written(self):
        for gid, spec in GUIDELINES.items():
            with self.subTest(gid):
                data = engine.load_guideline(gid)
                blocks = {f"{t}.b-text": "Some reported text." for e in data["items"] for t in e["targets"]["default"]}
                sections: dict = {}
                for block_id in blocks:
                    section, _, block = block_id.partition(".")
                    sections.setdefault(section, set()).add(block)
                state = engine.WorkspaceState(root=ROOT, line="qualitative-participatory", paper_available=True,
                                              blocks=blocks, declarations=set(), sections=sections)
                result = engine.evaluate(data, state)
                self.assertEqual(result["summary"]["satisfied"], [])
                self.assertEqual(result["summary"]["missing"], [])
                self.assertEqual(result["summary"]["needs-judgment"], list(range(1, spec["count"] + 1)))

    def test_the_readme_lists_the_three_among_the_shipped_guidelines(self):
        text = README.read_text(encoding="utf-8")
        self.assertIn("| `srqr` | SRQR", text)
        self.assertIn("| `coreq` | COREQ", text)
        self.assertIn("| `accord` | ACCORD", text)


class QualitativeGuidelineWorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._holder = tempfile.TemporaryDirectory(prefix="checklist-qualitative-ws-")
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
