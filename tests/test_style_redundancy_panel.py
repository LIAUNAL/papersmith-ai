"""The PDF viewer's style-and-redundancy panel.

`POST /api/pdf/ai-audit` with an empty payload audits the whole manuscript.
Beside its existing keys it returns what the panel draws: one 0-100 score
(0 clear, 100 needs revision) averaging the style and flow scores, a
breakdown per section (blocks grouped by the contract that declares them, in
contract order) and the passages that raise the score most, each with the
block it sits in. It reads writing quality only and never claims to estimate
AI detection.
"""
from __future__ import annotations

import re
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "skills" / "paper-writing" / "scripts"))
sys.path.insert(0, str(REPO))
import paper_ai_metrics  # noqa: E402
from skills._core.command_center import server  # noqa: E402

PAGE = (REPO / "skills" / "_core" / "command_center" / "static" / "index.html").read_text(encoding="utf-8")
EN = (REPO / "skills" / "_core" / "command_center" / "static" / "i18n" / "en.js").read_text(encoding="utf-8")

METHODS = ("Furthermore, the model is trained on the data. Moreover, the model is trained on the data. "
           "Additionally, the model is trained on the data. It is worth noting that the data are noisy.")
SETUP = "We split subjects into five folds and report balanced accuracy with a Friedman test."


def contract(block_ids: list[str]) -> str:
    blocks = ",\n".join(f'    {{"id": "{b}"}}' for b in block_ids)
    return f'```json\n{{\n  "blocks": [\n{blocks}\n  ]\n}}\n```\n\n# Contract\n'


def block(block_id: str, body: str) -> str:
    return (f"%% paper-writing block {block_id} begin sha256=0\n{body}\n"
            f"%% paper-writing block {block_id} end\n")


class ManuscriptPanelPayloadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "sections").mkdir()
        (root / "paper").mkdir()
        (root / "sections" / "01-materials-and-methods.md").write_text(contract(["mm-a"]), encoding="utf-8")
        (root / "sections" / "02-experimental-setup.md").write_text(contract(["es-a"]), encoding="utf-8")
        (root / "paper" / "main.tex").write_text(
            "\\begin{document}\n" + block("experimental-setup.es-a", SETUP) + block("mm-a", METHODS)
            + "\\end{document}\n",
            encoding="utf-8")
        self.data = TestClient(server.create_app(root)).post("/api/pdf/ai-audit", json={}).json()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_the_score_is_a_0_to_100_mean_of_style_and_flow(self) -> None:
        text = "\n\n".join([SETUP, METHODS])
        style = paper_ai_metrics.analyze_style(text)["style_score"]
        flow = paper_ai_metrics.analyze_flow(text)["flow_score"]
        self.assertEqual(self.data["score"], round(100 * (style + flow) / 2))
        self.assertTrue(0 <= self.data["score"] <= 100)
        self.assertIn(self.data["score_verdict"], ("clear", "uneven", "needs_revision"))

    def test_sections_follow_contract_order_with_their_blocks(self) -> None:
        sections = self.data["sections"]
        self.assertEqual([s["section"] for s in sections], ["Materials and methods", "Experimental setup"])
        self.assertEqual(sections[0]["blocks"], ["mm-a"])
        self.assertEqual(sections[1]["blocks"], ["experimental-setup.es-a"])  # a prefixed block id
        for entry in sections:
            self.assertTrue(0 <= entry["score"] <= 100)
        self.assertGreater(sections[0]["score"], sections[1]["score"])

    def test_findings_quote_a_span_and_name_its_block(self) -> None:
        findings = self.data["findings"]
        self.assertTrue(findings)
        self.assertLessEqual(len(findings), 12)
        for finding in findings:
            self.assertEqual(set(finding), {"block", "section", "category", "span", "sentence"})
        hit = next(f for f in findings if f["block"] == "mm-a")
        self.assertIn(hit["sentence"], METHODS)  # the whole sentence, to find it in the PDF
        self.assertEqual(hit["section"], "Materials and methods")

    def test_existing_keys_are_kept(self) -> None:
        for key in ("scope", "blocks_analyzed", "style_score", "style_verdict", "composite_score",
                    "blocks", "burstiness", "cliches", "lexical_diversity", "disclosure_notice"):
            with self.subTest(key=key):
                self.assertIn(key, self.data)
        self.assertIn("flow_score", self.data["blocks"]["mm-a"])


class PanelMarkupTests(unittest.TestCase):
    def test_the_toolbar_button_opens_the_panel(self) -> None:
        self.assertIn('id="btnAuditAi" onclick="openStyleRedundancyPanel()"', PAGE)
        self.assertIn("function renderStyleRedundancy(", PAGE)
        self.assertNotIn("alert(`${msg}", PAGE)

    def test_the_panel_never_claims_ai_detection(self) -> None:
        keys = re.findall(r'"(styleRedundancy\.[A-Za-z]+)": "([^"]*)"', EN)
        self.assertGreaterEqual(len(keys), 8)
        for key, text in keys:
            with self.subTest(key=key):
                self.assertNotRegex(text.lower(), r"detect|ai risk|probability")


if __name__ == "__main__":
    unittest.main()
