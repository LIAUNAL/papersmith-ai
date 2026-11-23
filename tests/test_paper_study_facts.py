"""The study facts and the `study-registration` declaration (T7-U8, S7).

S7: "fact vocabulary and `FACT_SOURCE_ROOT` entries for protocol, sample,
outcomes, analysis plan, participant flow". Decision D10 (L46, accepted in
L47): a STRUCTURED fact source kind for the participant flow. Decision D6: a
new `study-registration` declaration, `review-registration` untouched.

`protocol`, `sample`, `outcomes` and `analysis-plan` are read from the study
protocol revisions `protocol/study-protocol-<slug>-vNN.md` (a PROSE root);
`participant-flow` is read from the JSON record `study/flow.json` (a
STRUCTURED root, hashed as `participant_flow.model.flow_sha256` hashes it,
timestamp keys aside). Driven through the real `paper_cli.py`; the CLI
refuses papers outside the repository, so each fixture lives under the
git-ignored `.scratch/`.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

FORGE_ROOT = Path(__file__).resolve().parents[1]
SKILL_SCRIPTS = FORGE_ROOT / "skills" / "paper-writing" / "scripts"
CLI = SKILL_SCRIPTS / "paper_cli.py"
sys.path.insert(0, str(SKILL_SCRIPTS))
import paper_declarations  # noqa: E402
import paper_vocabulary  # noqa: E402

PROTOCOL_FACTS = ("protocol", "sample", "outcomes", "analysis-plan")
STUDY_FACTS = PROTOCOL_FACTS + ("participant-flow",)
REVISION = "protocol/study-protocol-demo-v01.md"
FLOW = "study/flow.json"


def _flow_model():
    path = FORGE_ROOT / "skills" / "_core" / "participant_flow" / "model.py"
    spec = importlib.util.spec_from_file_location("_test_participant_flow_model", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _CliFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.root = FORGE_ROOT / ".scratch" / f".paper-study-facts-{os.getpid()}-{id(self)}"
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.paper_dir = self.root / "paper"
        self.sections_dir = self.root / "sections"
        self.sections_dir.mkdir(parents=True)
        self.assertEqual(self.run_cli("scaffold", "--paper", str(self.paper_dir))[0], 0)
        self.write(REVISION, "# Study protocol\n\n**Primary outcome:** O1 -- HbA1c; time point: 12 weeks\n")
        self.flow = _flow_model().empty_flow("strobe")
        self.flow["updated_at"] = "2026-11-01T00:00:00Z"
        self.write(FLOW, json.dumps(self.flow, indent=2))

    def write(self, rel: str, text: str) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def run_cli(self, *args: str):
        proc = subprocess.run([sys.executable, str(CLI), *args], capture_output=True, text=True,
                              timeout=60)
        return proc.returncode, json.loads(proc.stdout), proc.stderr

    def declare(self, *args: str) -> dict:
        code, payload, stderr = self.run_cli("declare", "--paper", str(self.paper_dir),
                                             "--sections", str(self.sections_dir), *args)
        self.assertEqual(code, 0, stderr or payload)
        return payload

    def stale(self) -> dict:
        code, payload, stderr = self.run_cli("phases", "--paper", str(self.paper_dir),
                                             "--sections", str(self.sections_dir))
        self.assertEqual(code, 0, stderr or payload)
        return payload["stale_facts"]


class StudyVocabularyTests(unittest.TestCase):
    def test_the_five_study_facts_are_observable_facts(self) -> None:
        for fact in STUDY_FACTS:
            self.assertIn(fact, paper_vocabulary.FACTS)
            self.assertIn(fact, paper_declarations.OBSERVABLE_FACTS)

    def test_the_protocol_facts_read_the_protocol_prose_root(self) -> None:
        for fact in PROTOCOL_FACTS:
            root = paper_declarations.FACT_SOURCE_ROOT[fact]
            self.assertEqual(root.name, "protocol")
            self.assertIs(root.kind, paper_declarations.SourceRootKind.PROSE)

    def test_the_participant_flow_reads_a_structured_root(self) -> None:
        root = paper_declarations.FACT_SOURCE_ROOT["participant-flow"]
        self.assertEqual(root, paper_declarations.SourceRoot(
            FLOW, paper_declarations.SourceRootKind.STRUCTURED))

    def test_the_protocol_root_is_declarable_and_the_flow_root_is_not(self) -> None:
        declarable = paper_declarations.declarable_source_roots()
        self.assertIn("protocol", declarable)
        self.assertNotIn(FLOW, declarable)

    def test_study_registration_is_a_declaration_beside_review_registration(self) -> None:
        self.assertIn("study-registration", paper_vocabulary.DECLARATIONS)
        self.assertIn("review-registration", paper_vocabulary.DECLARATIONS)
        self.assertNotIn("study-registration", paper_vocabulary.FACTS)


class StudyFactDeclarationTests(_CliFixture):
    def _records(self) -> dict:
        code, payload, stderr = self.run_cli("plan", "--paper", str(self.paper_dir),
                                             "--sections", str(self.sections_dir))
        self.assertEqual(code, 0, stderr or payload)
        return {r["id"]: r for r in payload["declarations"]["records"]}

    def test_each_protocol_fact_records_the_digest_of_the_protocol_root(self) -> None:
        for fact in PROTOCOL_FACTS:
            self.declare("--fact", fact, "--value", f"{fact} as stated in v01")
        records = self._records()
        digests = {records[fact]["basis"]["protocol"] for fact in PROTOCOL_FACTS}
        self.assertEqual(len(digests), 1)
        for fact in PROTOCOL_FACTS:
            self.assertEqual(sorted(records[fact]["basis"]), ["protocol"])
            self.assertRegex(records[fact]["basis"]["protocol"], r"^[0-9a-f]{64}$")

    def test_the_participant_flow_basis_is_the_flow_module_hash(self) -> None:
        self.declare("--fact", "participant-flow", "--value", "STROBE flow, 412 enrolled")
        basis = self._records()["participant-flow"]["basis"]
        self.assertEqual(basis, {FLOW: _flow_model().flow_sha256(self.flow)})

    def test_study_registration_is_declared_through_the_cli(self) -> None:
        value = ("ClinicalTrials.gov NCT01234567, registered 2026-01-10, "
                 "first enrolment 2026-02-01")
        payload = self.declare("--declaration", "study-registration", "--value", value)
        self.assertEqual(payload["value"], value)
        self.assertEqual(self._records()["study-registration"]["kind"], "declaration")


class StudyFactStalenessTests(_CliFixture):
    def setUp(self) -> None:
        super().setUp()
        for fact in STUDY_FACTS:
            self.declare("--fact", fact, "--value", f"{fact} v01")
        self.assertEqual(self.stale(), {})

    def test_a_new_protocol_revision_makes_the_protocol_facts_stale(self) -> None:
        self.write("protocol/study-protocol-demo-v02.md", "# Study protocol v02\n")
        stale = self.stale()
        self.assertEqual(sorted(stale), sorted(PROTOCOL_FACTS))
        for fact in PROTOCOL_FACTS:
            self.assertEqual(stale[fact]["roots"], ["protocol"])
            self.assertIn("protocol/", stale[fact]["detail"])

    def test_changed_flow_counts_make_only_the_participant_flow_stale(self) -> None:
        changed = json.loads(json.dumps(self.flow))
        changed["stages"]["potentially_eligible"]["n"] = 412
        self.write(FLOW, json.dumps(changed))
        stale = self.stale()
        self.assertEqual(sorted(stale), ["participant-flow"])
        self.assertEqual(stale["participant-flow"]["roots"], [FLOW])
        self.assertIn(f"from {FLOW},", stale["participant-flow"]["detail"])

    def test_a_timestamp_or_formatting_change_is_not_a_change(self) -> None:
        moved = dict(self.flow, updated_at="2026-11-20T09:30:00Z", entered_at="2026-11-20")
        self.write(FLOW, json.dumps(moved, sort_keys=True))
        self.assertEqual(self.stale(), {})

    def test_a_flow_file_that_is_not_json_is_still_a_change(self) -> None:
        self.write(FLOW, "{ not json")
        self.assertEqual(sorted(self.stale()), ["participant-flow"])


class StudyFlowDigestRobustnessTests(_CliFixture):
    def test_valid_json_the_flow_hash_cannot_encode_still_records_a_basis(self) -> None:
        # A lone surrogate is valid JSON (an escaped code unit) but not encodable as UTF-8,
        # and a deeply nested array exhausts the JSON parser's recursion.
        for label, text in (("lone surrogate", '{"schema": 1, "template": "strobe", "note": "\\ud800"}'),
                            ("deep nesting", "[" * 100000 + "]" * 100000),
                            ("a list", "[1, 2, 3]"), ("a number", "7")):
            with self.subTest(label):
                self.write(FLOW, text)
                self.declare("--reopen", "participant-flow")
                self.declare("--fact", "participant-flow", "--value", f"flow {label}")
                code, payload, stderr = self.run_cli("plan", "--paper", str(self.paper_dir),
                                                     "--sections", str(self.sections_dir))
                self.assertEqual(code, 0, stderr or payload)
                record = {r["id"]: r for r in payload["declarations"]["records"]}["participant-flow"]
                self.assertRegex(record["basis"].get(FLOW, ""), r"^[0-9a-f]{64}$")
                self.assertEqual(self.stale(), {})

    def test_without_the_flow_module_the_basis_falls_back_to_the_bytes(self) -> None:
        cache = list(paper_declarations._flow_model_cache)
        self.addCleanup(lambda: paper_declarations._flow_model_cache.__setitem__(slice(None), cache))
        paper_declarations._flow_model_cache[:] = [None]  # a kit without skills/_core/participant_flow
        flow = self.root / FLOW
        basis = paper_declarations.source_basis(self.root, "participant-flow")
        import hashlib
        self.assertEqual(basis, {FLOW: hashlib.sha256(flow.read_bytes()).hexdigest()})
        changed = json.loads(json.dumps(self.flow))
        changed["stages"]["potentially_eligible"]["n"] = 412
        self.write(FLOW, json.dumps(changed))
        self.assertNotEqual(paper_declarations.source_basis(self.root, "participant-flow"), basis)


class StudySourceRootTests(_CliFixture):
    def test_the_protocol_revisions_take_the_revisions_marker(self) -> None:
        code, payload, stderr = self.run_cli(
            "mark", "revisions", "--root", "protocol", "--revision-prefix", "v",
            "--ordinal-digits", "2", "--paper", str(self.paper_dir),
        )
        self.assertEqual(code, 0, stderr or payload)
        self.assertEqual(payload["matched"], ["study-protocol-demo-v01.md"])
        self.assertTrue((self.root / "protocol" / ".paper-writing.json").is_file())

    def test_the_flow_root_refuses_a_revisions_marker_naming_its_kind(self) -> None:
        code, payload, _stderr = self.run_cli(
            "mark", "revisions", "--root", FLOW, "--revision-prefix", "v",
            "--ordinal-digits", "2", "--paper", str(self.paper_dir),
        )
        self.assertNotEqual(code, 0)
        self.assertEqual(payload["code"], "SOURCE_ROOT_UNDECLARABLE")
        self.assertIn("'structured'", payload["detail"])

    def test_plan_reports_both_roots(self) -> None:
        code, payload, stderr = self.run_cli("plan", "--paper", str(self.paper_dir),
                                             "--sections", str(self.sections_dir))
        self.assertEqual(code, 0, stderr or payload)
        roots = payload["sourceRoots"]
        self.assertEqual(roots["protocol"]["state"], "document-rooted")
        self.assertEqual(roots["protocol"]["declaration"], "undeclared")
        self.assertEqual(roots[FLOW]["state"], "unmeasured")
        self.assertEqual(roots[FLOW]["declaration"], "n/a")
        self.assertIn("structured", roots[FLOW]["reason"])

    def test_observe_reconciles_the_study_roots_against_disk(self) -> None:
        report = self.root / "report.json"
        report.write_text(json.dumps({"sample": {"satisfied": False, "evidence": []}}),
                          encoding="utf-8")
        code, payload, _stderr = self.run_cli(
            "observe", "--report", str(report), "--protocol", str(self.root / "protocol"),
        )
        self.assertNotEqual(code, 0)
        self.assertEqual(payload["code"], "OBSERVATION_DISK_CONFLICT")
        report.write_text(json.dumps({"participant-flow": {"satisfied": False, "evidence": []}}),
                          encoding="utf-8")
        code, payload, _stderr = self.run_cli(
            "observe", "--report", str(report), "--flow", str(self.root / FLOW),
        )
        self.assertNotEqual(code, 0)
        self.assertEqual(payload["code"], "OBSERVATION_DISK_CONFLICT")

    def test_a_file_counts_as_available_only_for_the_structured_flow_root(self) -> None:
        # Baseline: a file passed to a directory root (--proposals, --experiments,
        # --implementation) measured unavailable, so no disagreement arises.
        report = self.root / "report.json"
        stray = self.root / "notes.txt"
        stray.write_text("not a folder\n", encoding="utf-8")
        for flag, fact in (("--proposals", "formulation"), ("--experiments", "experimental-design"),
                           ("--implementation", "implementation")):
            with self.subTest(flag):
                report.write_text(json.dumps({fact: {"satisfied": False, "evidence": []}}), encoding="utf-8")
                code, payload, stderr = self.run_cli("observe", "--report", str(report), flag, str(stray))
                self.assertNotEqual(payload.get("code"), "OBSERVATION_DISK_CONFLICT", stderr or payload)
                self.assertEqual(code, 0, stderr or payload)


if __name__ == "__main__":
    unittest.main()
