"""`verify` reports deterministic, advisory coherence checks (#180, #183).

Each rule has one positive and one negative fixture under
`tests/fixtures/paper_coherence/`, appended to the coupling paper of
`tests/test_paper_writing.py` and checked through the real `paper_cli.py
verify`. Every coherence check is a warning: it never changes `clean` or the
coupling counts, and `verify` keeps exiting 0.
"""
from __future__ import annotations

import ast
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

FORGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_paper_writing import CLI, _build_coupling_paper  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "paper_coherence"
SCRIPTS = FORGE_ROOT / "skills" / "paper-writing" / "scripts"

#: rule -> (what the positive fixture's first finding must hold)
EXPECTED = {
    "caption-results": ("values", ["accuracy ... 0.91"]),
    "caption-interpretation": ("verbs", ["shows"]),
    "caption-duplicates": ("overlap", 1.0),
    "caption-identifiers": ("tokens", ["subject-v300", "r0h0", "K1"]),
    "overclaiming": ("words", ["solves", "always"]),
    "claims-findings": ("key_terms", ["adaptive", "caching", "footprint", "lowers", "memory",
                                      "streaming", "workloads"]),
    "not-performed": ("phrases", ["We did not", "excluded"]),
    "symbol-redefinition": ("meaning", "cache eviction threshold"),
    "naming-consistency": ("variant", "adaptive caching"),
}


class CoherenceVerifyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fresh()

    def fresh(self) -> None:
        (FORGE_ROOT / ".scratch").mkdir(exist_ok=True)
        self.root = Path(tempfile.mkdtemp(prefix=".paper-coherence-", dir=FORGE_ROOT / ".scratch"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.paper_dir = self.root / "paper"
        self.sections_dir = self.root / "sections"
        _build_coupling_paper(self.paper_dir, self.sections_dir)
        self.tex = self.paper_dir / "main.tex"

    def verify(self) -> tuple[int, dict]:
        proc = subprocess.run(
            [sys.executable, str(CLI), "verify", "--paper", str(self.paper_dir),
             "--sections", str(self.sections_dir)], capture_output=True, text=True, timeout=120)
        return proc.returncode, json.loads(proc.stdout)

    def append(self, fixture: str) -> None:
        text = self.tex.read_text(encoding="utf-8")
        extra = (FIXTURES / fixture).read_text(encoding="utf-8")
        if "\\end{document}" in text:
            text = text.replace("\\end{document}", extra + "\\end{document}", 1)
        else:
            text += "\n" + extra
        self.tex.write_text(text, encoding="utf-8")

    def coherence(self, report: dict) -> dict:
        return {entry["check"]: entry for entry in report["coherence"]}

    def _rule(self, rule: str) -> None:
        field, expected = EXPECTED[rule]
        with self.subTest(fixture="positive"):
            self.append(f"{rule}-positive.tex")
            code, report = self.verify()
            self.assertEqual(code, 0)
            entry = self.coherence(report)[rule]
            self.assertEqual((entry["verdict"], entry["severity"]), ("warn", "warning"))
            self.assertTrue(entry["findings"], entry)
            self.assertEqual(entry["findings"][0][field], expected)
        with self.subTest(fixture="negative"):
            self.fresh()
            self.append(f"{rule}-negative.tex")
            code, report = self.verify()
            self.assertEqual(code, 0)
            entry = self.coherence(report)[rule]
            self.assertEqual((entry["verdict"], entry["findings"]), ("pass", []), entry)

    # S1 (#180)
    def test_caption_result_values_are_flagged_and_key_values_are_not(self) -> None:
        self._rule("caption-results")

    def test_caption_interpretive_verbs_are_flagged(self) -> None:
        self._rule("caption-interpretation")

    def test_caption_sentence_repeating_the_body_is_flagged(self) -> None:
        self._rule("caption-duplicates")

    def test_caption_identifier_tokens_are_flagged_and_units_refs_panels_are_not(self) -> None:
        self._rule("caption-identifiers")

    # S5 (#183)
    def test_overclaiming_words_in_the_introduction_are_flagged(self) -> None:
        self._rule("overclaiming")

    def test_a_claim_without_a_matching_result_is_flagged(self) -> None:
        self._rule("claims-findings")

    def test_not_performed_work_is_flagged_outside_the_limitations(self) -> None:
        self._rule("not-performed")

    def test_a_methods_symbol_redefined_later_is_flagged(self) -> None:
        self._rule("symbol-redefinition")

    def test_a_variant_of_a_declared_name_is_flagged(self) -> None:
        self._rule("naming-consistency")
        self.fresh()
        self.append("naming-consistency-positive.tex")
        _, report = self.verify()
        variants = {f["variant"] for f in self.coherence(report)["naming-consistency"]["findings"]}
        self.assertEqual(variants, {"adaptive caching", "Bounded Retries"})

    def test_existing_paper_verifies_with_the_same_exit_code_and_counts(self) -> None:
        code, before = self.verify()
        self.assertEqual(code, 0)
        self.assertEqual([e["check"] for e in before["coherence"]],
                         ["caption-results", "caption-interpretation", "caption-duplicates",
                          "caption-identifiers", "overclaiming", "claims-findings",
                          "not-performed", "symbol-redefinition", "naming-consistency"])
        self.assertNotIn("warn", {e["verdict"] for e in before["coherence"]})
        for fixture in ("caption-results-positive.tex", "overclaiming-positive.tex",
                        "naming-consistency-positive.tex"):
            self.append(fixture)
        code, after = self.verify()
        self.assertEqual(code, 0)
        self.assertIn("warn", {e["verdict"] for e in after["coherence"]})
        keys = ("clean", "holds", "fails", "unmeasured")
        self.assertEqual({k: after[k] for k in keys}, {k: before[k] for k in keys})


class CoherencePurityTests(unittest.TestCase):
    def test_paper_verify_registers_the_same_roster(self) -> None:
        sys.path.insert(0, str(SCRIPTS))
        import paper_coherence
        import paper_verify
        self.assertEqual(paper_verify.COHERENCE_CHECKS, paper_coherence.COHERENCE_CHECKS)

    def test_paper_coherence_imports_only_re(self) -> None:
        tree = ast.parse((SCRIPTS / "paper_coherence.py").read_text(encoding="utf-8"))
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports |= {alias.name for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                imports.add(node.module or "")
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                self.assertNotIn(node.func.id, {"open", "__import__", "exec", "eval"})
        self.assertEqual(imports, {"re", "__future__"})


if __name__ == "__main__":
    unittest.main()
