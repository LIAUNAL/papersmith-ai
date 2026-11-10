"""`verify` reports whether every cited key has a reference record.

Coverage, never abstract presence: a key `resolve --references` could not
resolve passes with a visible note, so offline work is never blocked; only a
key with no record fails. Reuses the coupling fixture of
`tests/test_paper_writing.py` through the real `paper_cli.py`.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import types
import unittest
import uuid
from pathlib import Path

FORGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_paper_writing import CLI, _build_coupling_paper  # noqa: E402
sys.path.insert(0, str(FORGE_ROOT / "skills" / "paper-writing" / "scripts"))
import paper_verify  # noqa: E402


class VerifyReferencesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = FORGE_ROOT / ".scratch" / f".paper-verify-references-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.paper_dir = self.root / "paper"
        self.sections_dir = self.root / "sections"
        _build_coupling_paper(self.paper_dir, self.sections_dir)
        self.sidecar = self.paper_dir / ".paper-writing" / "references.json"
        self.tex = self.paper_dir / "main.tex"

    def verify(self) -> dict:
        proc = subprocess.run(
            [sys.executable, str(CLI), "verify", "--paper", str(self.paper_dir),
             "--sections", str(self.sections_dir)], capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return json.loads(proc.stdout)

    def entry(self, report: dict) -> dict:
        return {e["check"]: e for e in report["checks"]}["references"]

    def cite(self, *keys: str) -> None:
        self.cited = set(keys) | self.existing()
        self.tex.write_bytes(self.tex.read_bytes() + ("\n% \\cite{" + ",".join(keys) + "}\n").encode())

    def existing(self) -> set[str]:
        return set(self.entry(self.verify())["evidence"]["cited"])

    def write(self, **statuses: str) -> None:
        self.sidecar.parent.mkdir(parents=True, exist_ok=True)
        records = {key: {"status": status, "abstract": "A" if status == "resolved" else None}
                   for key, status in statuses.items()}
        records.update({key: {"status": "resolved", "abstract": "A"} for key in self.cited - set(records)})
        self.sidecar.write_text(json.dumps({"references": records}), encoding="utf-8")

    def test_a_key_with_no_record_fails_and_names_itself(self) -> None:
        self.cite("alpha2020")
        entry = self.entry(self.verify())
        self.assertEqual(entry["verdict"], "fail")
        self.assertIn("alpha2020", entry["evidence"]["missing"])

    def test_every_key_with_a_record_passes(self) -> None:
        self.cite("alpha2020")
        self.write(alpha2020="resolved")
        entry = self.entry(self.verify())
        self.assertEqual((entry["verdict"], entry["evidence"]["missing"]), ("pass", []))
        self.assertEqual(entry["limits"], [])

    def test_not_found_and_unreachable_pass_with_a_visible_note(self) -> None:
        self.cite("alpha2020", "beta2021")
        self.write(alpha2020="not_found", beta2021="unreachable")
        entry = self.entry(self.verify())
        self.assertEqual(entry["verdict"], "pass")
        self.assertEqual(entry["evidence"]["not_found"], ["alpha2020"])
        self.assertEqual(entry["evidence"]["unreachable"], ["beta2021"])
        self.assertTrue(entry["limits"])

    def test_a_bad_sidecar_covers_nothing_and_never_refuses(self) -> None:
        self.cite("alpha2020")
        self.sidecar.parent.mkdir(parents=True, exist_ok=True)
        self.sidecar.write_text("{not json", encoding="utf-8")
        self.assertEqual(self.entry(self.verify())["verdict"], "fail")

    def test_verify_writes_no_sidecar(self) -> None:
        self.verify()
        self.assertFalse(self.sidecar.exists())


class RemediationTests(unittest.TestCase):
    def check(self, records: dict | None) -> dict:
        evidence = types.SimpleNamespace(main_tex_bytes=b"\\cite{a}")
        return paper_verify.check_references(evidence, references=records)

    def test_a_missing_record_says_what_to_run(self) -> None:
        report = self.check({})
        self.assertEqual(report["verdict"], "fail")
        self.assertTrue(any("resolve --references" in line for line in report["limits"]))

    def test_a_resolved_paper_without_an_abstract_is_a_visible_note_and_passes(self) -> None:
        report = self.check({"a": {"status": "resolved", "abstract": None}})
        self.assertEqual(report["verdict"], "pass")
        self.assertTrue(any("abstract" in line for line in report["limits"]))


class NoCitationsTests(unittest.TestCase):
    def test_an_asta_resolved_key_earns_an_acknowledgement_note_not_a_failure(self) -> None:
        evidence = types.SimpleNamespace(main_tex_bytes=b"See \\cite{a,b}.\n")
        records = {"a": {"status": "resolved", "resolver": "asta", "abstract": "A"},
                   "b": {"status": "resolved", "resolver": "openalex", "abstract": "B"}}
        entry = paper_verify.check_references(evidence, references=records)
        self.assertEqual(entry["verdict"], "pass")
        self.assertEqual(entry["evidence"]["via_asta"], ["a"])
        self.assertTrue(any("Ai2's Asta" in line and "acknowledge" in line for line in entry["limits"]),
                        entry["limits"])
        without = paper_verify.check_references(evidence, references={**records, "a": records["b"]})
        self.assertEqual(without["verdict"], "pass")
        self.assertFalse(any("Asta" in line for line in without["limits"]))

    def test_a_workspace_with_no_citations_passes(self) -> None:
        sys.path.insert(0, str(FORGE_ROOT / "skills" / "paper-writing" / "scripts"))
        import types

        import paper_verify

        evidence = types.SimpleNamespace(main_tex_bytes=b"No citations here.\n")
        entry = paper_verify.check_references(evidence, references={})
        self.assertEqual((entry["verdict"], entry["evidence"]["cited"]), ("pass", []))


if __name__ == "__main__":
    unittest.main()
