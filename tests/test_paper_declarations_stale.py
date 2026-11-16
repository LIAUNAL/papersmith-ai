"""A declared fact warns when the source it was read from changed since.

Issue #184 item 7: "Facts declared with `declare` do not propagate: an
earlier dataset or experimental-design declaration can stay stale after the
protocol changes, without any warning." `set_fact` (what `declare --fact`
calls) now records the digest of the source root(s) the fact is read from,
and `read_stale_facts` names every fixed fact whose source no longer matches.
Records written before this change carry no basis and are never reported.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

FORGE_ROOT = Path(__file__).resolve().parents[1]
SKILL_SCRIPTS = FORGE_ROOT / "skills" / "paper-writing" / "scripts"
sys.path.insert(0, str(SKILL_SCRIPTS))
import paper_block  # noqa: E402
import paper_declarations  # noqa: E402
import paper_region  # noqa: E402
import paper_scaffold  # noqa: E402

PROTOCOL = "experiments/experiments-demo-v01.md"


class StaleFactTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.paper_dir = self.base / "paper"
        paper_scaffold.scaffold(self.paper_dir)
        self._write(PROTOCOL, "# Protocol\n\n## Experiment [exp:E1]\n\n- **Dataset:** CHB-MIT\n")

    def _write(self, rel: str, text: str) -> None:
        path = self.base / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _records(self) -> list:
        tex = paper_block.resolve_main_tex(self.paper_dir).read_bytes()
        return paper_region.read_region(tex, "declarations")["body"]["records"]

    def test_the_declared_fact_records_the_digest_of_its_source(self) -> None:
        result = paper_declarations.set_fact(self.paper_dir, "experimental-design", "5-fold CV")
        self.assertEqual(result["resolution"], "5-fold CV")
        record = next(r for r in self._records() if r["id"] == "experimental-design")
        self.assertEqual(sorted(record["basis"]), ["experiments"])
        self.assertRegex(record["basis"]["experiments"], r"^[0-9a-f]{64}$")

    def test_an_unchanged_protocol_reports_nothing(self) -> None:
        paper_declarations.set_fact(self.paper_dir, "experimental-design", "5-fold CV")
        self.assertEqual(paper_declarations.read_stale_facts(self.paper_dir), {})

    def test_a_changed_protocol_makes_the_design_and_the_dataset_stale(self) -> None:
        paper_declarations.set_fact(self.paper_dir, "experimental-design", "5-fold CV")
        paper_declarations.set_fact(self.paper_dir, "dataset", "CHB-MIT")
        paper_declarations.set_fact(self.paper_dir, "formulation", "kernel")
        self._write("experiments/experiments-demo-v02.md", "# Protocol v2\n\n- **Dataset:** TUH\n")
        stale = paper_declarations.read_stale_facts(self.paper_dir)
        self.assertEqual(sorted(stale), ["dataset", "experimental-design"])
        self.assertEqual(stale["experimental-design"]["roots"], ["experiments"])
        self.assertIn("experiments", stale["dataset"]["roots"])
        detail = stale["experimental-design"]["detail"]
        self.assertIn("experimental-design", detail)
        self.assertIn("experiments/", detail)
        self.assertIn("--reopen", detail)

    def test_an_edited_protocol_file_is_a_change_too(self) -> None:
        paper_declarations.set_fact(self.paper_dir, "experimental-design", "5-fold CV")
        self._write(PROTOCOL, "# Protocol\n\nLeave-one-subject-out.\n")
        self.assertIn("experimental-design", paper_declarations.read_stale_facts(self.paper_dir))

    def test_reopening_and_redeclaring_clears_the_warning(self) -> None:
        paper_declarations.set_fact(self.paper_dir, "experimental-design", "5-fold CV")
        self._write(PROTOCOL, "# Protocol\n\nLeave-one-subject-out.\n")
        paper_declarations.reopen(self.paper_dir, "experimental-design")
        self.assertEqual(paper_declarations.read_stale_facts(self.paper_dir), {})
        paper_declarations.set_fact(self.paper_dir, "experimental-design", "LOSO")
        self.assertEqual(paper_declarations.read_stale_facts(self.paper_dir), {})

    def test_a_record_without_a_basis_is_never_reported_and_never_rewritten(self) -> None:
        """A fact recorded before this change has no `basis`: nothing to
        compare, so no warning, and reading never rewrites the region."""
        paper_declarations.set_fact(self.paper_dir, "experimental-design", "5-fold CV")
        tex_path = paper_block.resolve_main_tex(self.paper_dir)
        pre = tex_path.read_bytes()
        record = paper_region.read_region(pre, "declarations")
        body = record["body"]
        for entry in body["records"]:
            entry.pop("basis", None)
        region_bytes, _ = paper_region.build_region_bytes("declarations", body)
        legacy = paper_region.replace_or_append(
            pre, "declarations", region_bytes,
            {"begin_start": record["begin_start"], "end_end": record["end_end"]},
        )
        tex_path.write_bytes(legacy)
        self._write(PROTOCOL, "# Protocol\n\nLeave-one-subject-out.\n")
        self.assertEqual(paper_declarations.read_stale_facts(self.paper_dir), {})
        self.assertEqual(tex_path.read_bytes(), legacy)

    def test_a_declaration_and_a_repository_fact_carry_no_basis(self) -> None:
        paper_declarations.set_declaration(self.paper_dir, "grant-code", "Hermes 1")
        paper_declarations.set_fact(self.paper_dir, "results", "table 2")
        for record in self._records():
            self.assertNotIn("basis", record, record)


if __name__ == "__main__":
    unittest.main()
