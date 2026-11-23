"""`verify` diffs a study's manuscript against its locked protocol (paper-type-lines S7, T7-U9, D9).

S7: "manuscript diffed against the protocol (guards against p-hacking,
HARKing, outcome switching)". D9: a primary-outcome switch fails verify unless
an amendment declares it; other differences are advisory coherence warnings.

The manuscript's primary outcome is the one its `outcomes` fact names by
protocol id (`primary: O1`); the protocol is the revision pinned by
`study/protocol.lock.json`, read by the study protocol's parser; the analysis
log is `analysis/log.jsonl`. The checks ride under the report's own `study`
key, present only in a workspace with a study protocol, so an applied-AI or a
review paper verifies exactly as before. Driven through the real
`paper_cli.py`, `study_cli.py` and `analysis_cli.py`; the paper CLI refuses
papers outside the repository, so each fixture lives under `.scratch/`.
"""
from __future__ import annotations

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

SCRIPTS = FORGE_ROOT / "skills" / "paper-writing" / "scripts"
EMPIRICAL = FORGE_ROOT / "skills" / "_core" / "empirical"
MARKER = "<!-- proposal-workspace:artifact:v1 -->\n"
STUDY_CHECKS = ["primary-outcome-switch", "exploratory-as-confirmatory", "outcome-not-in-protocol",
                "protocol-outcome-not-analysed"]
PLAN = """
**Primary model:** ANCOVA on arm, adjusted for baseline

**Covariates:** none

**Missing data:** multiple imputation

**Multiplicity:** not applicable
"""
V1 = ("**Primary outcome:** O1 -- HbA1c (%); time point: 12 weeks\n\n"
      "**Secondary outcome:** O2 -- body weight (kg); time point: 12 weeks\n")
V2 = ("**Primary outcome:** O2 -- body weight (kg); time point: 12 weeks\n\n"
      "**Secondary outcome:** O1 -- HbA1c (%); time point: 12 weeks\n")


class _Workspace(unittest.TestCase):
    def setUp(self) -> None:
        (FORGE_ROOT / ".scratch").mkdir(exist_ok=True)
        self.root = Path(tempfile.mkdtemp(prefix=".paper-protocol-switch-", dir=FORGE_ROOT / ".scratch"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.paper_dir = self.root / "paper"
        self.sections_dir = self.root / "sections"
        _build_coupling_paper(self.paper_dir, self.sections_dir)
        self.baseline_code, self.baseline = self.verify()

    def write(self, rel: str, text: str) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def run_json(self, *argv: str) -> tuple[int, dict]:
        proc = subprocess.run([sys.executable, *argv], capture_output=True, text=True, timeout=120)
        return proc.returncode, json.loads(proc.stdout)

    def verify(self) -> tuple[int, dict]:
        return self.run_json(str(CLI), "verify", "--paper", str(self.paper_dir), "--sections", str(self.sections_dir))

    def declare_outcomes(self, value: str) -> None:
        code, out = self.run_json(str(CLI), "declare", "--paper", str(self.paper_dir), "--sections",
                                  str(self.sections_dir), "--fact", "outcomes", "--value", value)
        self.assertEqual(code, 0, out)

    def reopen_outcomes(self) -> None:
        code, out = self.run_json(str(CLI), "declare", "--paper", str(self.paper_dir), "--sections",
                                  str(self.sections_dir), "--reopen", "outcomes")
        self.assertEqual(code, 0, out)

    def study(self, *args: str) -> dict:
        code, out = self.run_json(str(EMPIRICAL / "study_cli.py"), *args, "--root", str(self.root))
        self.assertEqual(code, 0, out)
        return out

    def log(self, outcome: str) -> dict:
        self.write("analysis/out.csv", f"{outcome},0.4\n")
        code, out = self.run_json(str(EMPIRICAL / "analysis_cli.py"), "record", "--by", "Ana Ruiz", "--tool", "SPSS",
                                  "--outcome", outcome, "--output", "analysis/out.csv", "--root", str(self.root))
        self.assertEqual(code, 0, out)
        return out["entry"]

    def revision(self, version: int, outcomes: str) -> None:
        self.write(f"protocol/study-protocol-walking-v{version:02d}.md",
                   MARKER + f"# Walking trial v{version}\n\n**Research question:** Does walking lower HbA1c?\n\n"
                   + outcomes + PLAN)

    def locked(self, outcomes: str = V1) -> None:
        self.revision(1, outcomes)
        self.study("protocol", "approve", "--by", "Ana Ruiz")

    def results(self, sentence: str) -> None:
        tex = self.paper_dir / "main.tex"
        text = tex.read_text(encoding="utf-8")
        tex.write_text(text.replace("\\end{document}", f"\\section{{Results}}\n{sentence}\n\\end{{document}}", 1)
                       if "\\end{document}" in text else text + f"\n\\section{{Results}}\n{sentence}\n",
                       encoding="utf-8")

    def study_entries(self) -> dict:
        code, report = self.verify()
        self.assertEqual(code, self.baseline_code, report)
        self.assertEqual([entry["check"] for entry in report["study"]], STUDY_CHECKS)
        self.report = report
        return {entry["check"]: entry for entry in report["study"]}


class NoStudyTests(_Workspace):
    def test_an_experimental_paper_gets_no_study_entry(self) -> None:
        self.assertNotIn("study", self.baseline)
        self.declare_outcomes("primary: O2 body weight")
        code, report = self.verify()
        self.assertNotIn("study", report)
        self.assertEqual(code, self.baseline_code)
        self.assertEqual(report["clean"], self.baseline["clean"])

    def test_a_review_workspace_gets_no_study_entry(self) -> None:
        self.write("papersmith.yaml", "paper_kind: review\n")
        self.write("review/protocol.json", json.dumps({"question": "q", "outcomes": ["O1"]}))
        self.write("review/protocol.lock.json", json.dumps({"sha256": "0" * 64}))
        code, report = self.verify()
        self.assertNotIn("study", report)
        self.assertEqual((code, report["clean"], report["coherence"]),
                         (self.baseline_code, self.baseline["clean"], self.baseline["coherence"]))


class PrimaryOutcomeSwitchTests(_Workspace):
    def test_the_locked_primary_outcome_passes(self) -> None:
        self.locked()
        self.declare_outcomes("primary: O1 HbA1c at 12 weeks; secondary: O2")
        entry = self.study_entries()["primary-outcome-switch"]
        self.assertEqual((entry["verdict"], entry["severity"]), ("pass", "error"))
        self.assertEqual((entry["evidence"]["manuscript"], entry["evidence"]["locked"]), ("O1", "O1"))
        self.assertEqual(self.report["clean"], self.baseline["clean"])

    def test_a_switched_primary_outcome_fails_verify(self) -> None:
        self.locked()
        self.declare_outcomes("Primary outcome O2 (body weight); secondary O1")
        entry = self.study_entries()["primary-outcome-switch"]
        self.assertEqual(entry["verdict"], "fail")
        self.assertEqual((entry["findings"][0]["manuscript"], entry["findings"][0]["locked"]), ("O2", "O1"))
        self.assertIn("no amendment declares the switch", entry["findings"][0]["message"])
        self.assertIs(self.report["clean"], False)
        for key in ("holds", "fails", "unmeasured"):
            self.assertEqual(self.report[key], self.baseline[key])

    def test_an_amendment_that_declares_the_switch_exempts_it(self) -> None:
        self.locked()
        self.revision(2, V2)
        self.study("protocol", "amend", "--by", "Ana Ruiz", "--reason", "HbA1c assay withdrawn")
        self.declare_outcomes("primary: O2 body weight; secondary: O1")
        entry = self.study_entries()["primary-outcome-switch"]
        self.assertEqual(entry["verdict"], "pass")
        self.assertEqual(entry["evidence"]["approved"], "O1")
        switch = entry["evidence"]["declared_switches"][0]
        self.assertEqual((switch["amendment"], switch["from"], switch["to"], switch["reason"]),
                         (1, "O1", "O2", "HbA1c assay withdrawn"))
        self.assertEqual(self.report["clean"], self.baseline["clean"])

    def test_a_manuscript_left_on_the_pre_amendment_primary_fails(self) -> None:
        self.locked()
        self.revision(2, V2)
        self.study("protocol", "amend", "--by", "Ana Ruiz", "--reason", "HbA1c assay withdrawn")
        self.declare_outcomes("primary: O1")
        entry = self.study_entries()["primary-outcome-switch"]
        self.assertEqual(entry["verdict"], "fail")
        self.assertIn("before amendment 1", entry["findings"][0]["message"])

    def test_an_unamended_newer_revision_does_not_declare_a_switch(self) -> None:
        self.locked()
        self.revision(2, V2)
        self.declare_outcomes("primary: O2")
        self.assertEqual(self.study_entries()["primary-outcome-switch"]["verdict"], "fail")

    def test_unlocked_or_undeclared_is_unmeasured_and_does_not_fail(self) -> None:
        self.revision(1, V1)
        self.declare_outcomes("primary: O2")
        entry = self.study_entries()["primary-outcome-switch"]
        self.assertEqual((entry["verdict"], entry["unmeasured_reason"]), ("unmeasured", "PROTOCOL_NOT_LOCKED"))
        self.assertEqual(self.report["clean"], self.baseline["clean"])
        self.study("protocol", "approve", "--by", "Ana Ruiz")
        self.reopen_outcomes()
        entry = self.study_entries()["primary-outcome-switch"]
        self.assertEqual((entry["verdict"], entry["unmeasured_reason"]), ("unmeasured", "OUTCOMES_FACT_UNDECLARED"))
        self.declare_outcomes("the outcomes of the protocol")
        entry = self.study_entries()["primary-outcome-switch"]
        self.assertEqual((entry["verdict"], entry["unmeasured_reason"]), ("unmeasured", "PRIMARY_OUTCOME_UNNAMED"))


class AdvisoryTests(_Workspace):
    def test_a_results_sentence_on_an_exploratory_only_outcome_is_flagged(self) -> None:
        self.locked()
        self.declare_outcomes("primary: O1")
        self.log("O3")
        self.results("Walking lowered waist circumference by 2 cm (Outcome O3).")
        entry = self.study_entries()["exploratory-as-confirmatory"]
        self.assertEqual((entry["verdict"], entry["severity"]), ("warn", "warning"))
        self.assertEqual(entry["findings"][0]["outcome"], "O3")
        self.assertEqual(self.report["clean"], self.baseline["clean"])

    def test_a_results_sentence_that_says_exploratory_is_not_flagged(self) -> None:
        self.locked()
        self.declare_outcomes("primary: O1")
        self.log("O3")
        self.results("In an exploratory analysis, walking lowered waist circumference (Outcome O3).")
        self.assertEqual(self.study_entries()["exploratory-as-confirmatory"]["verdict"], "pass")

    def test_outcomes_outside_the_protocol_and_protocol_outcomes_left_unanalysed_are_flagged(self) -> None:
        self.locked()
        self.declare_outcomes("primary: O1")
        self.log("O1")
        self.log("O3")
        entries = self.study_entries()
        self.assertEqual(entries["outcome-not-in-protocol"]["verdict"], "warn")
        self.assertEqual(entries["outcome-not-in-protocol"]["findings"], [{"outcome": "O3", "exploratory": 1}])
        self.assertEqual(entries["protocol-outcome-not-analysed"]["findings"], [{"outcome": "O2"}])
        self.log("O2")
        self.assertEqual(self.study_entries()["protocol-outcome-not-analysed"]["verdict"], "pass")
        self.assertEqual(self.report["clean"], self.baseline["clean"])


class RosterTests(unittest.TestCase):
    def test_paper_verify_registers_the_same_study_roster(self) -> None:
        sys.path.insert(0, str(SCRIPTS))
        import paper_coherence
        import paper_verify
        self.assertEqual(list(paper_verify.STUDY_CHECKS), STUDY_CHECKS)
        self.assertEqual(paper_verify.STUDY_CHECKS, paper_coherence.STUDY_CHECKS)

    def test_no_study_leaves_the_report_unchanged_and_a_failed_switch_makes_it_unclean(self) -> None:
        sys.path.insert(0, str(SCRIPTS))
        import paper_coherence
        import paper_verify
        report = {"clean": True, "holds": 1}
        self.assertIs(paper_verify.attach_study(report, paper_coherence.run_study_guarded(b"", None, None)), report)
        entries = paper_coherence.run_study_guarded(b"", None, {"protocol": "not a dict"})
        self.assertEqual([e["unmeasured_reason"] for e in entries], ["CHECK_FAILED"] * 4)
        self.assertIs(paper_verify.attach_study(report, entries)["clean"], True)


if __name__ == "__main__":
    unittest.main()
