"""COSMIN Reporting Guideline 2.0 data for the checklist engine (paper-type-lines S8, T8-O6;
decisions E6 of L66 and D11-D13 of L46).

The measurement-instrument variant of the observational-measurement line reports
against COSMIN. The data file keeps the guideline's 68 items (31 general, 37
specific to a measurement property) in its own order, stores only identifiers,
paraphrased topics and our own questions, and decides nothing deterministically:
every item ends at ``needs-judgment`` at best.
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

#: COSMIN Reporting Guideline 2.0 item identifiers, in the guideline's order
#: (Table 1 general items, then Table 2 measurement-property-specific items).
GENERAL = (["T1"] + [f"A{n}" for n in range(1, 6)] + [f"I{n}" for n in range(1, 5)]
           + [f"GM{n}" for n in range(1, 10)] + [f"GR{n}" for n in range(1, 5)]
           + [f"DC{n}" for n in range(1, 8)] + ["O1"])
SPECIFIC = ([f"CV{n}" for n in range(1, 7)] + [f"SV{n}" for n in range(1, 4)] + [f"IC{n}" for n in range(1, 3)]
            + [f"CCV{n}" for n in range(1, 5)] + [f"R{n}" for n in range(1, 7)] + [f"ME{n}" for n in range(1, 7)]
            + [f"CriV{n}" for n in range(1, 4)] + [f"ConV{n}" for n in range(1, 4)]
            + [f"Resp{n}" for n in range(1, 5)])
IDENTIFIERS = GENERAL + SPECIFIC
GENERIC_SECTIONS = {"title-and-keywords", "abstract", "introduction", "methods", "results", "discussion",
                    "limitations", "conclusions", "back-matter"}


def run_cli(*argv: str) -> tuple[int, dict]:
    completed = subprocess.run([sys.executable, str(CLI), *argv], capture_output=True, text=True, timeout=300)
    return completed.returncode, json.loads(completed.stdout)


class CosminDataTests(unittest.TestCase):
    def setUp(self):
        self.data = engine.load_guideline("cosmin")

    def test_the_file_validates_with_68_items_numbered_in_order(self):
        self.assertEqual(engine.validate_guideline(self.data, expected_id="cosmin"), [])
        self.assertEqual((len(GENERAL), len(SPECIFIC)), (31, 37))
        self.assertEqual(self.data["item_count"], 68)
        self.assertEqual([entry["number"] for entry in self.data["items"]], list(range(1, 69)))
        listed = {entry["id"]: entry for entry in engine.list_guidelines()}
        self.assertEqual(listed["cosmin"]["items"], 68)

    def test_each_item_carries_its_cosmin_identifier_in_the_guidelines_order(self):
        prefixes = [entry["topic"].split(" ", 1)[0] for entry in self.data["items"]]
        self.assertEqual(prefixes, IDENTIFIERS)

    def test_the_source_is_version_2_0_with_its_doi(self):
        self.assertEqual(self.data["url"], "https://doi.org/10.1007/s11136-025-03950-x")
        self.assertIn("2.0", self.data["version"])
        self.assertIn("Qual Life Res 2025;34:1901-11", self.data["citation"])
        # The superseded version 1.0 is named so a reader citing it is not misled.
        self.assertIn("10.1007/s11136-021-02822-4", self.data["citation"])

    def test_every_item_is_a_question_with_no_deterministic_rule(self):
        for entry in self.data["items"]:
            self.assertTrue(entry.get("question", "").strip(), entry["number"])
            self.assertEqual(entry.get("evidence", []), [], entry["number"])

    def test_specific_items_say_they_apply_only_when_that_property_is_studied(self):
        for entry in self.data["items"][len(GENERAL):]:
            self.assertTrue(entry["question"].startswith("If the study evaluates "), entry["number"])

    def test_targets_are_generic_section_names_for_every_line(self):
        for entry in self.data["items"]:
            self.assertEqual(set(entry["targets"]), {"default"}, entry["number"])
            for target in entry["targets"]["default"]:
                self.assertIn(target.split(".")[0], GENERIC_SECTIONS, entry["number"])
        by_id = dict(zip(IDENTIFIERS, self.data["items"]))
        self.assertEqual(by_id["T1"]["targets"]["default"], ["title-and-keywords"])
        self.assertEqual(by_id["DC3"]["targets"]["default"], ["limitations"])
        self.assertEqual(by_id["DC7"]["targets"]["default"], ["conclusions"])
        self.assertEqual(by_id["O1"]["targets"]["default"], ["back-matter.bm-conflicts-of-interest"])
        self.assertEqual(by_id["CV1"]["targets"]["default"], ["methods"])
        self.assertEqual(by_id["Resp4"]["targets"]["default"], ["results"])

    def test_no_item_is_satisfied_even_when_every_target_is_written(self):
        blocks = {}
        for entry in self.data["items"]:
            for target in entry["targets"]["default"]:
                section, _, block = target.partition(".")
                blocks[f"{section}.{block or 'b-text'}"] = "Some reported text."
        sections: dict = {}
        for block_id in blocks:
            section, _, block = block_id.partition(".")
            sections.setdefault(section, set()).add(block)
        state = engine.WorkspaceState(root=ROOT, line="observational-measurement", paper_available=True,
                                      blocks=blocks, declarations=set(), sections=sections)
        result = engine.evaluate(self.data, state)
        self.assertEqual(result["summary"]["satisfied"], [])
        self.assertEqual(result["summary"]["missing"], [])
        self.assertEqual(result["summary"]["needs-judgment"], list(range(1, 69)))

    def test_the_readme_lists_cosmin_among_the_shipped_guidelines(self):
        text = README.read_text(encoding="utf-8")
        self.assertIn("| `cosmin` | COSMIN Reporting Guideline 2.0", text)
        self.assertIn("| 68 |", text)


class CosminWorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._holder = tempfile.TemporaryDirectory(prefix="checklist-cosmin-ws-")
        cls.ws = Path(cls._holder.name).resolve() / "ws"
        init_module.initialize(cls.ws, tools=("claude",), run_npm=False, run_env=False)

    @classmethod
    def tearDownClass(cls):
        cls._holder.cleanup()

    def test_check_on_a_fresh_workspace_reports_every_item_missing_and_none_satisfied(self):
        code, payload = run_cli("check", "--guideline", "cosmin", "--root", str(self.ws), "--json")
        self.assertEqual(code, 0, payload)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["guideline"]["id"], "cosmin")
        self.assertEqual(len(payload["items"]), 68)
        self.assertEqual(payload["summary"]["satisfied"], [])
        self.assertEqual(payload["summary"]["needs-judgment"], [])
        self.assertEqual(payload["summary"]["missing"], list(range(1, 69)))
        for entry in payload["items"]:
            self.assertTrue(entry["question"], entry["item"])
            self.assertTrue(all(m.startswith("text:") for m in entry["missing"]), entry)

    def test_show_prints_the_guideline(self):
        code, payload = run_cli("show", "cosmin")
        self.assertEqual(code, 0, payload)
        self.assertEqual(payload.get("id", payload.get("guideline", {}).get("id")), "cosmin")


if __name__ == "__main__":
    unittest.main()
