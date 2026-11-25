"""The analysis log of an empirical study (paper-type-lines S7, T7-U9, decisions D7 and D8).

S7: "analysis log of every analysis run, exploratory analyses labelled". D7: a
run that maps to no analysis-plan entry of the locked protocol is exploratory,
and neither the agent nor the operator can relabel it without a protocol
amendment. D8: `analysis run -- <cmd>` hashes the script and inputs before
running; `analysis record --by` is the operator's attested entry for a GUI
tool. Every test goes through `analysis_cli.py` and `study_cli.py`, as an
operator or an agent would; the protocol's outcomes are read by the study
protocol's own parser under node.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ANALYSIS = REPO / "skills" / "_core" / "empirical" / "analysis_cli.py"
STUDY = REPO / "skills" / "_core" / "empirical" / "study_cli.py"
MARKER = "<!-- proposal-workspace:artifact:v1 -->\n"
LOG = "analysis/log.jsonl"
FIELDS = """
**Research question:** Does a walking programme lower HbA1c?

**Primary outcome:** O1 -- HbA1c (%); time point: 12 weeks

**Secondary outcome:** O2 -- body weight (kg); time point: 12 weeks

**Primary model:** ANCOVA of the 12-week HbA1c on arm, adjusted for baseline

**Covariates:** none

**Missing data:** multiple imputation under missing at random

**Multiplicity:** not applicable
"""
SCRIPT = "import pathlib, sys\nprint('analysed')\npathlib.Path('out.csv').write_text('beta,0.4\\n')\nsys.exit(int(sys.argv[1]) if len(sys.argv) > 1 else 0)\n"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class AnalysisWorkspace(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="analysis-log-")
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.write("analysis.py", SCRIPT)
        self.write("data/cohort.csv", "id,hba1c\n1,7.1\n")

    def write(self, rel: str, text: str) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def cli(self, script: Path, *args: str, env: dict | None = None) -> tuple[int, dict]:
        argv = list(args)
        split = argv.index("--") if "--" in argv else len(argv)
        argv[split:split] = ["--root", str(self.root)]
        proc = subprocess.run([sys.executable, str(script), *argv], capture_output=True, text=True,
                              cwd=str(REPO), env=env, timeout=120)
        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1, f"one JSON object expected, got {proc.stdout!r} / {proc.stderr!r}")
        return proc.returncode, json.loads(lines[0])

    def ok(self, *args: str, env: dict | None = None) -> dict:
        code, out = self.cli(ANALYSIS, *args, env=env)
        self.assertEqual((code, out["ok"]), (0, True), out)
        return out

    def refused(self, error: str, *args: str, exit_code: int = 1, env: dict | None = None) -> dict:
        code, out = self.cli(ANALYSIS, *args, env=env)
        self.assertEqual((code, out["ok"], out.get("error")), (exit_code, False, error), out)
        self.assertTrue(out["message"])
        return out

    def study(self, *args: str) -> dict:
        code, out = self.cli(STUDY, *args)
        self.assertEqual((code, out["ok"]), (0, True), out)
        return out

    def revision(self, version: int, extra: str = "") -> Path:
        return self.write(f"protocol/study-protocol-walking-v{version:02d}.md",
                          MARKER + f"# Walking trial v{version}\n" + FIELDS + extra)

    def lock(self) -> None:
        self.revision(1)
        self.study("protocol", "approve", "--by", "Ana Ruiz")

    def run_analysis(self, outcome: str, *extra: str, args: tuple = ()) -> dict:
        return self.ok("run", "--outcome", outcome, "--input", "data/cohort.csv", "--output", "out.csv", *extra,
                       "--", sys.executable, "analysis.py", *args)["entry"]

    def log_lines(self) -> list[dict]:
        return [json.loads(line) for line in (self.root / LOG).read_text(encoding="utf-8").splitlines()]


class LabelTests(AnalysisWorkspace):
    def test_a_run_before_any_lock_is_exploratory(self) -> None:
        self.revision(1)
        entry = self.run_analysis("O1")
        self.assertEqual(entry["label"], "exploratory")
        self.assertEqual(entry["label_reason"]["code"], "no-protocol-lock")
        self.assertEqual(entry["protocol"]["state"], "absent")
        self.assertIsNone(entry["protocol"]["sha256"])

    def test_a_planned_outcome_under_a_current_lock_is_confirmatory(self) -> None:
        self.lock()
        entry = self.run_analysis("O1")
        lock = json.loads((self.root / "study" / "protocol.lock.json").read_text(encoding="utf-8"))
        self.assertEqual((entry["label"], entry["label_reason"]["code"]), ("confirmatory", "in-locked-protocol"))
        self.assertEqual(entry["protocol"], {"state": "current", "revision": lock["revision"],
                                             "sha256": lock["sha256"], "amendments": 0})
        self.assertEqual(self.run_analysis("O2")["label"], "confirmatory")

    def test_an_unplanned_outcome_is_exploratory(self) -> None:
        self.lock()
        entry = self.run_analysis("O3")
        self.assertEqual((entry["label"], entry["label_reason"]["code"]), ("exploratory", "outcome-not-in-protocol"))

    def test_no_flag_sets_the_label(self) -> None:
        self.lock()
        for flag in (("--label", "confirmatory"), ("--confirmatory",), ("--lab", "confirmatory")):
            self.refused("USAGE", "run", "--outcome", "O3", *flag, "--", sys.executable, "analysis.py", exit_code=2)
            self.refused("USAGE", "record", "--by", "Ana Ruiz", "--tool", "SPSS", "--outcome", "O3",
                         "--output", "data/cohort.csv", *flag, exit_code=2)
        self.assertFalse((self.root / LOG).exists())
        self.assertEqual(self.run_analysis("O3")["label"], "exploratory")

    def test_only_an_amendment_that_adds_the_outcome_makes_a_later_run_confirmatory(self) -> None:
        self.lock()
        first = self.run_analysis("O3")
        self.revision(2, "\n**Secondary outcome:** O3 -- waist circumference (cm); time point: 12 weeks\n")
        changed = self.run_analysis("O3")
        self.assertEqual((changed["label"], changed["label_reason"]["code"]), ("exploratory", "protocol-changed"))
        self.study("protocol", "amend", "--by", "Ana Ruiz", "--reason", "added waist circumference")
        later = self.run_analysis("O3")
        self.assertEqual((later["label"], later["protocol"]["amendments"]), ("confirmatory", 1))
        runs = [e for e in self.log_lines() if e["kind"] == "run"]  # each run-started entry carries the same label
        self.assertEqual([e["label"] for e in runs], ["exploratory", "exploratory", "confirmatory"])
        self.assertEqual([e["label"] for e in self.log_lines() if e["kind"] == "run-started"],
                         ["exploratory", "exploratory", "confirmatory"])
        self.assertEqual(runs[0], first)
        codes = [w["code"] for w in self.ok("status")["warnings"]]
        self.assertIn("OUTCOME_ADDED_AFTER_ANALYSIS", codes)

    def test_a_plan_entry_must_be_one_the_protocol_plans(self) -> None:
        self.lock()
        self.assertEqual(self.run_analysis("O1", "--plan", "missing-data")["label"], "confirmatory")
        self.assertEqual(self.run_analysis("O1", "--plan", "primary-model")["label"], "confirmatory")
        entry = self.run_analysis("O2", "--plan", "primary-model")
        self.assertEqual((entry["label"], entry["label_reason"]["code"]),
                         ("exploratory", "primary-model-not-for-outcome"))
        entry = self.run_analysis("O1", "--plan", "covariates")  # the protocol declares `none`
        self.assertEqual((entry["label"], entry["label_reason"]["code"]), ("exploratory", "plan-entry-not-in-protocol"))
        self.refused("PLAN_ENTRY_INVALID", "run", "--outcome", "O1", "--plan", "subgroup", "--",
                     sys.executable, "analysis.py")

    def test_without_node_a_locked_study_refuses_and_an_unlocked_one_still_logs(self) -> None:
        env = dict(os.environ, PATH=str(self.root / "no-bin"))
        self.revision(1)
        entry = self.ok("run", "--outcome", "O1", "--", sys.executable, "analysis.py", env=env)["entry"]
        self.assertEqual(entry["label"], "exploratory")
        self.study("protocol", "approve", "--by", "Ana Ruiz")
        self.refused("PROTOCOL_PARSER_UNAVAILABLE", "run", "--outcome", "O1", "--", sys.executable, "analysis.py",
                     env=env)
        self.assertEqual([e["kind"] for e in self.log_lines()], ["run-started", "run"])  # the first run only


class HashTests(AnalysisWorkspace):
    def test_a_run_hashes_script_inputs_streams_outputs_and_records_the_exit(self) -> None:
        entry = self.run_analysis("O1", args=("3",))
        self.assertEqual(entry["script"], {"path": "analysis.py", "sha256": sha256(SCRIPT.encode())})
        self.assertEqual(entry["inputs"], [{"path": "data/cohort.csv", "dataset": None,
                                            "sha256": sha256((self.root / "data/cohort.csv").read_bytes())}])
        self.assertEqual(entry["outputs"], [{"path": "out.csv", "sha256": sha256(b"beta,0.4\n")}])
        self.assertEqual((entry["kind"], entry["attested"], entry["exit_code"]), ("run", False, 3))
        self.assertGreaterEqual(entry["duration_s"], 0)
        self.assertEqual(entry["stdout_sha256"], sha256(b"analysed\n"))
        self.assertEqual((self.root / "analysis/streams" / entry["stdout_sha256"]).read_bytes(), b"analysed\n")
        self.assertEqual(entry["command"][1:], ["analysis.py", "3"])
        self.assertEqual(self.ok("status")["failed_runs"], [entry["id"]])

    def test_the_script_is_found_or_named(self) -> None:
        self.write("other.R", "x <- 1\n")
        entry = self.ok("run", "--outcome", "O1", "--script", "other.R", "--", sys.executable, "analysis.py")["entry"]
        self.assertEqual(entry["script"]["path"], "other.R")
        self.refused("SCRIPT_NOT_FOUND", "run", "--outcome", "O1", "--", sys.executable, "-c", "print(1)")
        self.refused("INPUT_ABSENT", "run", "--outcome", "O1", "--input", "data/none.csv", "--",
                     sys.executable, "analysis.py")
        self.refused("PATH_OUTSIDE_WORKSPACE", "run", "--outcome", "O1", "--input", "/etc/hostname", "--",
                     sys.executable, "analysis.py")
        self.refused("USAGE", "run", "--outcome", "O1", exit_code=2)
        self.refused("OUTCOME_INVALID", "run", "--outcome", "O 1", "--", sys.executable, "analysis.py")

    def test_a_registered_dataset_input_carries_its_qc_hash(self) -> None:
        digest = sha256((self.root / "data/cohort.csv").read_bytes())
        self.write("datasets/registry.json", json.dumps([{"slug": "cohort", "files": ["data/cohort.csv"]}]))
        self.write("datasets/cohort/qc.json", json.dumps({"file": "data/cohort.csv", "sha256": digest,
                                                          "status": "pass",
                                                          "dictionary": {"sha256": "d" * 64}}))
        dataset = self.run_analysis("O1")["inputs"][0]["dataset"]
        self.assertEqual(dataset, {"slug": "cohort", "qc_sha256": digest, "qc_status": "pass",
                                   "dictionary_sha256": "d" * 64, "matches_qc": True})
        self.write("data/cohort.csv", "id,hba1c\n1,9.9\n")
        self.assertFalse(self.run_analysis("O1")["inputs"][0]["dataset"]["matches_qc"])


class AppendOnlyTests(AnalysisWorkspace):
    def test_entries_are_chained(self) -> None:
        # A wrapped run writes two entries: `run-started` before the command, `run` after it.
        self.run_analysis("O1")
        self.run_analysis("O2")
        raw = (self.root / LOG).read_bytes().split(b"\n")
        lines = self.log_lines()
        self.assertEqual([(e["seq"], e["id"], e["kind"]) for e in lines],
                         [(1, "A0001", "run-started"), (2, "A0002", "run"), (3, "A0003", "run-started"),
                          (4, "A0004", "run")])
        self.assertEqual([e["prev"] for e in lines], [None] + [sha256(line) for line in raw[:3]])
        self.assertEqual((lines[1]["started"], lines[3]["started"]), ("A0001", "A0003"))

    def test_a_corrupt_line_refuses_every_append_before_anything_runs(self) -> None:
        self.run_analysis("O1")
        log = self.root / LOG
        log.write_text(log.read_text(encoding="utf-8") + "{not json\n", encoding="utf-8")
        (self.root / "out.csv").unlink()
        self.refused("ANALYSIS_LOG_CORRUPT", "run", "--outcome", "O1", "--output", "out.csv", "--",
                     sys.executable, "analysis.py")
        self.assertFalse((self.root / "out.csv").exists())
        self.refused("ANALYSIS_LOG_CORRUPT", "record", "--by", "Ana Ruiz", "--tool", "SPSS", "--outcome", "O1",
                     "--output", "data/cohort.csv")
        status = self.ok("status")
        self.assertEqual(status["log"]["state"], "corrupt")
        self.assertIn("ANALYSIS_LOG_CORRUPT", [w["code"] for w in status["warnings"]])

    def test_relabelling_an_entry_by_hand_breaks_the_chain(self) -> None:
        self.run_analysis("O3")
        self.run_analysis("O3")
        log = self.root / LOG
        lines = log.read_text(encoding="utf-8").splitlines()
        edited = json.loads(lines[0])
        edited["label"] = "confirmatory"
        log.write_text("\n".join([json.dumps(edited, sort_keys=True)] + lines[1:]) + "\n", encoding="utf-8")
        self.refused("ANALYSIS_LOG_CORRUPT", "run", "--outcome", "O1", "--", sys.executable, "analysis.py")


class RunTraceTests(AnalysisWorkspace):
    BREAKER = ("import pathlib\n"
               "log = pathlib.Path('analysis/log.jsonl')\n"
               "log.write_bytes(log.read_bytes() + b'{broken\\n')\n"
               "pathlib.Path('out.csv').write_text('beta,0.9\\n')\n")

    def test_a_run_is_logged_before_its_command_so_a_failed_append_leaves_a_trace(self) -> None:
        self.write("breaker.py", self.BREAKER)
        self.refused("ANALYSIS_LOG_CORRUPT", "run", "--outcome", "O1", "--output", "out.csv", "--",
                     sys.executable, "breaker.py")
        self.assertEqual((self.root / "out.csv").read_text(encoding="utf-8"), "beta,0.9\n")
        first = json.loads((self.root / LOG).read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual((first["kind"], first["id"], first["exit_code"]), ("run-started", "A0001", None))
        self.assertEqual(first["command"][1:], ["breaker.py"])
        self.assertEqual(first["outputs"], [{"path": "out.csv", "sha256": None}])

    def test_a_run_killed_mid_command_is_reported_as_interrupted(self) -> None:
        self.write("killer.py", "import os, signal\nos.kill(os.getppid(), signal.SIGKILL)\n")
        proc = subprocess.run([sys.executable, str(ANALYSIS), "run", "--outcome", "O1", "--root", str(self.root),
                               "--", sys.executable, "killer.py"], capture_output=True, text=True, timeout=120)
        self.assertNotEqual(proc.returncode, 0)
        status = self.ok("status")
        self.assertEqual(status["interrupted_runs"], ["A0001"])
        self.assertIn("RUN_INTERRUPTED", [w["code"] for w in status["warnings"]])
        self.assertEqual(status["labels"], {"confirmatory": 0, "exploratory": 0})
        self.run_analysis("O1")
        status = self.ok("status")
        self.assertEqual((status["interrupted_runs"], status["labels"]["exploratory"]), (["A0001"], 1))

    def test_a_command_that_cannot_start_is_refused_before_any_entry(self) -> None:
        self.refused("COMMAND_NOT_FOUND", "run", "--outcome", "O1", "--script", "analysis.py", "--",
                     "no-such-program-xyz", "analysis.py")
        self.assertFalse((self.root / LOG).exists())


class StreamsIgnoredTests(AnalysisWorkspace):
    def test_run_ignores_its_streams_in_any_workspace(self) -> None:
        self.run_analysis("O1")
        self.assertEqual((self.root / "analysis" / ".gitignore").read_text(encoding="utf-8"), "streams/\n")
        git = subprocess.run(["git", "init", "-q", str(self.root)], capture_output=True)
        if git.returncode == 0:
            check = subprocess.run(["git", "-C", str(self.root), "check-ignore", "-q",
                                    f"analysis/streams/{sha256(b'analysed' + chr(10).encode())}"])
            self.assertEqual(check.returncode, 0, "the streams are ignored by git")

    def test_a_users_analysis_gitignore_is_never_overwritten(self) -> None:
        self.write("analysis/.gitignore", "*.tmp\n")
        out = self.ok("run", "--outcome", "O1", "--", sys.executable, "analysis.py")
        self.assertEqual((self.root / "analysis" / ".gitignore").read_text(encoding="utf-8"), "*.tmp\n")
        self.assertEqual([w["code"] for w in out["warnings"]], ["STREAMS_NOT_IGNORED"])
        self.write("analysis/.gitignore", "*.tmp\nstreams/\n")
        self.assertNotIn("warnings", self.ok("run", "--outcome", "O1", "--", sys.executable, "analysis.py"))


class TornAppendTests(AnalysisWorkspace):
    TAIL = b'{"schema": 1, "seq": 3, "kind": "run-sta'

    def tear(self) -> bytes:
        self.run_analysis("O1")
        log = self.root / LOG
        before = log.read_bytes()
        log.write_bytes(before + self.TAIL)
        return before

    def test_a_torn_final_line_is_refused_with_its_own_code_and_nothing_runs(self) -> None:
        self.tear()
        (self.root / "out.csv").unlink()
        out = self.refused("ANALYSIS_LOG_TORN", "run", "--outcome", "O1", "--output", "out.csv", "--",
                           sys.executable, "analysis.py")
        self.assertIn("repair --by", out["message"])
        self.assertFalse((self.root / "out.csv").exists())
        self.refused("ANALYSIS_LOG_TORN", "record", "--by", "Ana Ruiz", "--tool", "SPSS", "--outcome", "O1",
                     "--output", "data/cohort.csv")
        status = self.ok("status")
        self.assertEqual(status["log"]["state"], "torn")
        self.assertIn("ANALYSIS_LOG_TORN", [w["code"] for w in status["warnings"]])

    def test_repair_moves_the_torn_tail_aside_records_it_and_logging_resumes(self) -> None:
        before = self.tear()
        self.refused("APPROVER_MISSING", "repair")
        out = self.ok("repair", "--by", "Ana Ruiz")
        repair = out["repair"]
        self.assertEqual((repair["by"], repair["tail_bytes"], repair["tail_sha256"]),
                         ("Ana Ruiz", len(self.TAIL), sha256(self.TAIL)))
        self.assertEqual((self.root / repair["moved_to"]).read_bytes(), self.TAIL)
        self.assertEqual((self.root / LOG).read_bytes(), before)
        recorded = [json.loads(line) for line in
                    (self.root / "analysis" / "repairs.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(recorded, [repair])
        self.assertEqual(self.ok("status")["repairs"], 1)
        self.assertEqual(self.run_analysis("O1")["seq"], 4)
        self.refused("ANALYSIS_LOG_NOT_TORN", "repair", "--by", "Ana Ruiz")

    def test_repair_never_touches_a_log_corrupt_before_its_tail(self) -> None:
        self.run_analysis("O1")
        log = self.root / LOG
        log.write_bytes(b"{edited\n" + log.read_bytes() + self.TAIL)
        damaged = log.read_bytes()
        self.refused("ANALYSIS_LOG_CORRUPT", "repair", "--by", "Ana Ruiz")
        self.assertEqual(log.read_bytes(), damaged)
        self.assertFalse((self.root / "analysis" / "repairs.jsonl").exists())

    def test_a_complete_final_line_without_its_newline_is_kept_and_the_next_append_starts_a_new_line(self) -> None:
        self.run_analysis("O1")
        log = self.root / LOG
        log.write_bytes(log.read_bytes().rstrip(b"\n"))
        self.run_analysis("O2")
        self.assertEqual([e["seq"] for e in self.log_lines()], [1, 2, 3, 4])


class AttestedRecordTests(AnalysisWorkspace):
    def test_record_is_the_operators_attested_entry(self) -> None:
        self.lock()
        self.write("spss/output.spv", "binary-ish")
        entry = self.ok("record", "--by", "Ana Ruiz", "--tool", "SPSS 29", "--outcome", "O2",
                        "--input", "data/cohort.csv", "--output", "spss/output.spv",
                        "--note", "GLM univariate, menus")["entry"]
        self.assertEqual((entry["kind"], entry["attested"], entry["by"], entry["tool"]),
                         ("record", True, "Ana Ruiz", "SPSS 29"))
        self.assertEqual(entry["label"], "confirmatory")
        self.assertEqual(entry["outputs"], [{"path": "spss/output.spv", "sha256": sha256(b"binary-ish")}])
        self.assertIsNone(entry["command"])
        self.assertEqual(self.ok("record", "--by", "Ana Ruiz", "--tool", "R GUI", "--outcome", "O9",
                                 "--output", "spss/output.spv")["entry"]["label"], "exploratory")

    def test_record_refuses_without_operator_tool_or_output(self) -> None:
        base = ("record", "--outcome", "O1", "--output", "data/cohort.csv")
        self.refused("APPROVER_MISSING", *base, "--tool", "SPSS")
        self.refused("FIELD_MISSING", *base, "--by", "Ana Ruiz")
        self.refused("OUTPUT_MISSING", "record", "--by", "Ana Ruiz", "--tool", "SPSS", "--outcome", "O1")
        self.refused("OUTPUT_ABSENT", "record", "--by", "Ana Ruiz", "--tool", "SPSS", "--outcome", "O1",
                     "--output", "nothing.spv")
        self.refused("USAGE", "record", "--by", "Ana Ruiz", "--tool", "SPSS", "--outcome", "O1",
                     "--output", "data/cohort.csv", "--", "spss", exit_code=2)
        self.assertFalse((self.root / LOG).exists())


class StatusTests(AnalysisWorkspace):
    def test_status_reports_outcomes_left_unanalysed_and_outcomes_outside_the_protocol(self) -> None:
        self.assertEqual(self.ok("status")["log"]["state"], "absent")
        self.lock()
        self.run_analysis("O1")
        self.run_analysis("O7")
        status = self.ok("status")
        self.assertEqual(status["labels"], {"confirmatory": 1, "exploratory": 1})
        self.assertEqual(status["protocol_outcomes"], {"primary": "O1", "secondary": ["O2"]})
        self.assertEqual(status["plan_entries"], ["primary-model", "missing-data"])
        warnings = {(w["code"], w.get("outcome")) for w in status["warnings"]}
        self.assertEqual(warnings, {("PROTOCOL_OUTCOME_NOT_ANALYSED", "O2"), ("OUTCOME_NOT_IN_PROTOCOL", "O7")})


if __name__ == "__main__":
    unittest.main()
