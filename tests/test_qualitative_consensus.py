"""Consensus rounds and MICMAC of the qualitative-participatory line (paper-type-lines S8; T8-Q2, K4, K5).

The operator registers the panel by anonymised codes, records the consensus
rule against the approved study protocol, and records each round's response
file, bound by sha256; the core computes agreement per item from those files
(G-ROUNDS) and MICMAC from the operator's influence matrix. The assistant
never enters or edits a rating, and no output ever carries a comment.

Expected numbers are computed by hand in the docstrings, never by the module under test.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CLI = REPO / "skills" / "_core" / "qualitative" / "consensus_cli.py"
STUDY_CLI = REPO / "skills" / "_core" / "empirical" / "study_cli.py"
sys.path.insert(0, str(REPO))

MARKER = "<!-- proposal-workspace:artifact:v1 -->\n"
SECRET = "ZEBRA-QUOKKA-7731"  # a recognizable comment token that must never leave the response file
PANEL = ("P01", "P02", "P03", "P04")
# Round 1 (scale 1-5, agree from 4, threshold 75):
#   I1: 5 4 4 2 -> 3 of 4 = 75 % (consensus); sorted 2 4 4 5: median 4, q1 h = 0.75 -> 3.5, q3 h = 2.25 -> 4.25.
#   I2: 1 2 4 3 -> 1 of 4 = 25 %; sorted 1 2 3 4: median 2.5, q1 1.75, q3 3.25, IQR 1.5.
ROUND_1 = ["P01,I1,5,", f"P02,I1,4,{SECRET} first", "P03,I1,4,", "P04,I1,2,",
           "P01,I2,1,", "P02,I2,2,", f"P03,I2,4,\"{SECRET}, quoted\"", "P04,I2,3,"]
# Round 2: I2 only: 4 4 5 3 -> 3 of 4 = 75 % (consensus); sorted 3 4 4 5: median 4, q1 3.75, q3 4.25, IQR 0.5.
# Change from round 1: +50 points, median +1.5, IQR -1.
ROUND_2 = ["P01,I2,4,", "P02,I2,4,", "P03,I2,5,", f"P04,I2,3,{SECRET} again"]
MATRIX = ["x,A,B,C,D", "A,0,P,3,1", "B,2,0,3,1", "C,0,1,0,0", "D,0,1,0,0"]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Workspace(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="qualitative-consensus-")
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.outputs: list[str] = []

    def run_cli(self, *args: str, cli: Path = CLI) -> tuple[int, dict]:
        proc = subprocess.run([sys.executable, str(cli), *args, "--root", str(self.root)],
                              capture_output=True, text=True, cwd=str(REPO))
        self.outputs.append(proc.stdout + proc.stderr)
        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1, f"one JSON object expected, got {proc.stdout!r} / {proc.stderr!r}")
        return proc.returncode, json.loads(lines[0])

    def ok(self, *args: str) -> dict:
        code, out = self.run_cli(*args)
        self.assertEqual((code, out["ok"]), (0, True), out)
        return out

    def refused(self, error: str, *args: str) -> dict:
        code, out = self.run_cli(*args)
        self.assertEqual((code, out["ok"], out.get("error")), (1, False, error), out)
        self.assertTrue(out["message"])
        return out

    def write(self, relative: str, text: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def protocol(self, version: int = 1, body: str = "Delphi protocol") -> None:
        self.write(f"protocol/study-protocol-delphi-v{version:02d}.md", MARKER + body + "\n")

    def approve(self) -> None:
        self.protocol()
        code, out = self.run_cli("protocol", "approve", "--by", "Ana Ruiz", cli=STUDY_CLI)
        self.assertEqual(code, 0, out)

    def panel(self) -> None:
        for member in PANEL:
            self.ok("panel", "add", "--member", member, "--expertise", "nurse, 10 years in primary care",
                    "--by", "Ana Ruiz")

    def plan(self, *extra: str, rounds: str = "2", threshold: str = "75") -> dict:
        return self.ok("plan", "record", "--rounds", rounds, "--threshold", threshold, "--scale", "1-5",
                       "--agree-from", "4", "--by", "Ana Ruiz", *extra)

    def responses(self, name: str, rows: list[str], header: str = "member,item,rating,comment") -> Path:
        return self.write(f"data/{name}", header + "\n" + "\n".join(rows) + "\n")

    def record_round(self, k: int, name: str, *extra: str) -> dict:
        return self.ok("round", "record", "--round", str(k), "--file", f"data/{name}", "--by", "Ana Ruiz", *extra)

    def ready(self) -> None:
        self.approve()
        self.panel()
        self.plan()


class Panel(Workspace):
    def test_members_are_anonymised_codes_with_history(self) -> None:
        out = self.ok("panel", "add", "--member", "P01", "--expertise", "agronomist", "--note", "recruited via a "
                      "cooperative", "--by", "Ana Ruiz")
        self.assertEqual(out["panel"]["size"], 1)
        data = json.loads((self.root / "study/consensus/panel.json").read_text(encoding="utf-8"))
        entry = data["history"][0]
        self.assertEqual({k: entry[k] for k in ("member", "expertise", "note", "by")},
                         {"member": "P01", "expertise": "agronomist", "note": "recruited via a cooperative",
                          "by": "Ana Ruiz"})
        self.assertTrue(entry["at"])
        self.refused("MEMBER_EXISTS", "panel", "add", "--member", "P01", "--expertise", "x", "--by", "Ana Ruiz")

    def test_names_and_emails_are_refused(self) -> None:
        self.refused("MEMBER_ID_EMAIL", "panel", "add", "--member", "ana.ruiz@uni.edu", "--expertise", "x",
                     "--by", "Ana Ruiz")
        self.refused("MEMBER_ID_INVALID", "panel", "add", "--member", "Ana Ruiz", "--expertise", "x", "--by", "Ana")
        self.refused("TEXT_HAS_EMAIL", "panel", "add", "--member", "P09", "--expertise", "write to a@b.org",
                     "--by", "Ana Ruiz")
        self.refused("FIELD_MISSING", "panel", "add", "--member", "P09", "--by", "Ana Ruiz")
        self.refused("APPROVER_MISSING", "panel", "add", "--member", "P09", "--expertise", "x")
        self.assertFalse((self.root / "study/consensus/panel.json").exists())


class Plan(Workspace):
    def test_the_plan_needs_an_approved_current_protocol(self) -> None:
        self.refused("PROTOCOL_NOT_APPROVED", "plan", "record", "--rounds", "2", "--threshold", "75", "--scale",
                     "1-5", "--agree-from", "4", "--by", "Ana Ruiz")
        self.approve()
        out = self.plan()
        lock = json.loads((self.root / "study/protocol.lock.json").read_text(encoding="utf-8"))
        self.assertEqual(out["plan"]["state"], "current")
        self.assertEqual((out["plan"]["rounds"], out["plan"]["threshold"], out["plan"]["scale"],
                          out["plan"]["agree_from"], out["plan"]["protocol_sha256"]),
                         (2, 75, {"min": 1, "max": 5}, 4, lock["sha256"]))
        self.write("protocol/study-protocol-delphi-v01.md", MARKER + "edited\n")
        self.refused("PROTOCOL_CHANGED", "plan", "record", "--rounds", "3", "--threshold", "75", "--scale", "1-5",
                     "--agree-from", "4", "--by", "Ana Ruiz", "--reason", "x")

    def test_invalid_rules_are_refused(self) -> None:
        self.approve()
        base = {"--rounds": "2", "--threshold": "75", "--scale": "1-5", "--agree-from": "4"}
        for flag, value, code in (("--rounds", "0", "ROUNDS_INVALID"), ("--rounds", "two", "ROUNDS_INVALID"),
                                  ("--threshold", "0", "THRESHOLD_INVALID"), ("--threshold", "101", "THRESHOLD_INVALID"),
                                  ("--threshold", "nan", "THRESHOLD_INVALID"), ("--scale", "5-1", "SCALE_INVALID"),
                                  ("--scale", "1to5", "SCALE_INVALID"), ("--agree-from", "6", "AGREE_FROM_INVALID"),
                                  ("--agree-from", "1", "AGREE_FROM_INVALID")):
            with self.subTest(flag=flag, value=value):
                args = dict(base, **{flag: value})
                self.refused(code, "plan", "record", *[x for pair in args.items() for x in pair], "--by", "Ana Ruiz")

    def test_a_changed_plan_states_why_and_an_identical_one_is_refused(self) -> None:
        self.approve()
        self.plan()
        self.refused("REASON_MISSING", "plan", "record", "--rounds", "3", "--threshold", "75", "--scale", "1-5",
                     "--agree-from", "4", "--by", "Ana Ruiz")
        self.refused("RECORD_UNCHANGED", "plan", "record", "--rounds", "2", "--threshold", "75", "--scale", "1-5",
                     "--agree-from", "4", "--by", "Ana Ruiz", "--reason", "same")
        out = self.plan("--reason", "a third round agreed with the panel", rounds="3")
        self.assertEqual((out["plan"]["rounds"], out["plan"]["changes"]), (3, 1))


class Rounds(Workspace):
    def test_round_status_computes_agreement_from_the_files(self) -> None:
        self.ready()
        one = self.responses("round1.csv", ROUND_1)
        before = one.read_bytes()
        out = self.record_round(1, "round1.csv")
        self.assertEqual(one.read_bytes(), before, "the core never writes a response file")
        data = json.loads((self.root / "study/consensus/rounds.json").read_text(encoding="utf-8"))
        entry = data["history"][0]
        self.assertEqual((entry["round"], entry["file"], entry["sha256"], entry["responses"], entry["items"],
                          entry["responders"], entry["comments"]), (1, "data/round1.csv", sha256(one), 8, 2, 4, 2))
        self.assertEqual(out["round"]["state"], "current")
        self.responses("round2.csv", ROUND_2)
        self.record_round(2, "round2.csv")
        status = self.ok("round", "status")
        self.assertIn("type 7", status["quantile_method"])
        r1, r2 = status["rounds"]
        self.assertEqual(r1["items"][0], {"item": "I1", "n": 4, "agree": 3, "agreement_percent": 75, "median": 4,
                                          "q1": 3.5, "q3": 4.25, "iqr": 0.75, "consensus": True, "change": None})
        self.assertEqual(r1["items"][1], {"item": "I2", "n": 4, "agree": 1, "agreement_percent": 25, "median": 2.5,
                                          "q1": 1.75, "q3": 3.25, "iqr": 1.5, "consensus": False, "change": None})
        self.assertEqual(r2["items"], [{"item": "I2", "n": 4, "agree": 3, "agreement_percent": 75, "median": 4,
                                        "q1": 3.75, "q3": 4.25, "iqr": 0.5, "consensus": True,
                                        "change": {"previous_round": 1, "agreement_percent": 50, "median": 1.5,
                                                   "iqr": -1, "consensus_previous": False}}])
        self.assertEqual((r1["consensus_items"], r2["consensus_items"]), (1, 1))
        self.assertTrue(status["gate"]["passed"])
        only = self.ok("round", "status", "--round", "2")
        self.assertEqual([r["round"] for r in only["rounds"]], [2])
        self.refused("ROUND_NOT_RECORDED", "round", "status", "--round", "3")

    def test_round_refusals(self) -> None:
        self.approve()
        self.responses("round1.csv", ROUND_1)
        self.refused("PLAN_ABSENT", "round", "record", "--round", "1", "--file", "data/round1.csv", "--by", "Ana")
        self.plan()
        self.refused("PANEL_ABSENT", "round", "record", "--round", "1", "--file", "data/round1.csv", "--by", "Ana")
        self.panel()
        self.responses("unknown.csv", ["P01,I1,5,", "P99,I1,4,"])
        self.refused("MEMBER_UNKNOWN", "round", "record", "--round", "1", "--file", "data/unknown.csv", "--by", "Ana")
        self.responses("scale.csv", ["P01,I1,6,"])
        self.refused("RATING_OUT_OF_SCALE", "round", "record", "--round", "1", "--file", "data/scale.csv",
                     "--by", "Ana")
        self.responses("text.csv", ["P01,I1,4.5,"])
        self.refused("RATING_INVALID", "round", "record", "--round", "1", "--file", "data/text.csv", "--by", "Ana")
        self.responses("dup.csv", ["P01,I1,4,", "P01,I1,5,"])
        self.refused("RESPONSE_DUPLICATE", "round", "record", "--round", "1", "--file", "data/dup.csv", "--by", "Ana")
        self.responses("header.csv", ["P01,I1,4"], header="panelist,item,score")
        self.refused("CSV_INVALID", "round", "record", "--round", "1", "--file", "data/header.csv", "--by", "Ana")
        self.responses("noitem.csv", ["P01,,4,"])
        self.refused("ITEM_MISSING", "round", "record", "--round", "1", "--file", "data/noitem.csv", "--by", "Ana")
        self.refused("FILE_ABSENT", "round", "record", "--round", "1", "--file", "data/none.csv", "--by", "Ana")
        self.refused("ROUND_INVALID", "round", "record", "--round", "0", "--file", "data/round1.csv", "--by", "Ana")
        self.refused("ROUND_OUT_OF_ORDER", "round", "record", "--round", "2", "--file", "data/round1.csv",
                     "--by", "Ana")
        self.refused("ROUND_BEYOND_PLAN", "round", "record", "--round", "3", "--file", "data/round1.csv",
                     "--by", "Ana")
        self.refused("APPROVER_MISSING", "round", "record", "--round", "1", "--file", "data/round1.csv")
        self.assertFalse((self.root / "study/consensus/rounds.json").exists())
        self.record_round(1, "round1.csv")
        self.refused("RECORD_UNCHANGED", "round", "record", "--round", "1", "--file", "data/round1.csv",
                     "--by", "Ana", "--reason", "again")
        self.responses("round1b.csv", ROUND_1[:-1])
        self.refused("REASON_MISSING", "round", "record", "--round", "1", "--file", "data/round1b.csv", "--by", "Ana")
        out = self.record_round(1, "round1b.csv", "--reason", "P04 withdrew item I2 before the deadline")
        self.assertEqual(out["round"]["responses"], 7)

    def test_a_round_is_stale_when_its_file_changes(self) -> None:
        self.ready()
        one = self.responses("round1.csv", ROUND_1)
        self.record_round(1, "round1.csv")
        one.write_text(one.read_text(encoding="utf-8").replace("P04,I1,2", "P04,I1,5"), encoding="utf-8")
        r1 = self.ok("round", "status")["rounds"][0]
        self.assertEqual((r1["state"], r1["reasons"], r1["items"]), ("stale", ["file-changed"], None))
        one.unlink()
        r1 = self.ok("round", "status")["rounds"][0]
        self.assertEqual(r1["reasons"], ["file-missing"])

    def test_a_changed_plan_makes_its_rounds_stale(self) -> None:
        self.ready()
        self.responses("round1.csv", ROUND_1)
        self.record_round(1, "round1.csv")
        self.plan("--reason", "threshold agreed at 80", threshold="80")
        r1 = self.ok("round", "status")["rounds"][0]
        self.assertEqual((r1["state"], r1["reasons"]), ("stale", ["plan-changed"]))
        # The results stay those of the plan the round was recorded against: I1's 75 % reaches 75, not 80.
        self.assertEqual(r1["items"][0]["consensus"], True)
        self.assertEqual(r1["items"][1]["consensus"], False)
        out = self.record_round(1, "round1.csv", "--reason", "recorded against the new plan")
        self.assertEqual(out["round"]["state"], "current")
        self.assertEqual(out["round"]["items"][0]["consensus"], False)

    def test_a_protocol_amendment_makes_the_plan_and_rounds_stale(self) -> None:
        self.ready()
        self.responses("round1.csv", ROUND_1)
        self.record_round(1, "round1.csv")
        self.protocol(version=2, body="amended Delphi protocol")
        self.refused("PROTOCOL_CHANGED", "round", "record", "--round", "2", "--file", "data/round1.csv",
                     "--by", "Ana")
        code, _ = self.run_cli("protocol", "amend", "--by", "Ana Ruiz", "--reason", "a third round", cli=STUDY_CLI)
        self.assertEqual(code, 0)
        status = self.ok("round", "status")
        self.assertEqual((status["plan"]["state"], status["plan"]["reasons"]), ("stale", ["protocol-amended"]))
        self.assertEqual(status["rounds"][0]["reasons"], ["plan-stale"])
        self.assertFalse(status["gate"]["passed"])
        self.refused("PLAN_STALE", "round", "record", "--round", "2", "--file", "data/round1.csv", "--by", "Ana")
        self.plan("--reason", "recorded against the amended protocol")
        self.assertEqual(self.ok("round", "status")["plan"]["state"], "current")

    def test_rounds_left_without_their_plan_are_flagged_not_absent(self) -> None:
        """A plan file removed after rounds were recorded leaves orphaned rounds: G-ROUNDS is
        corrupt with a warning, never 'absent' as if nothing were owed."""
        from skills._core.qualitative import consensus
        self.ready()
        self.responses("round1.csv", ROUND_1)
        self.record_round(1, "round1.csv")
        (self.root / "study" / "consensus" / "plan.json").unlink()
        state = consensus.rounds_state(self.root)
        self.assertEqual((state["state"], state["passed"]), ("corrupt", False))
        self.assertIn("ROUNDS_WITHOUT_PLAN", [w["code"] for w in state["warnings"]])

    def test_g_rounds_needs_every_planned_round_current(self) -> None:
        from skills._core.qualitative import consensus
        self.assertEqual(consensus.rounds_state(self.root)["state"], "absent")
        self.ready()
        self.responses("round1.csv", ROUND_1)
        self.record_round(1, "round1.csv")
        state = consensus.rounds_state(self.root)
        self.assertEqual((state["gate"], state["state"], state["passed"], state["missing"]),
                         ("G-ROUNDS", "open", False, [2]))
        self.responses("round2.csv", ROUND_2)
        self.record_round(2, "round2.csv")
        state = consensus.rounds_state(self.root)
        self.assertEqual((state["state"], state["passed"], state["missing"]), ("passed", True, []))
        self.assertEqual([(r["round"], r["state"], r["consensus_items"]) for r in state["rounds"]],
                         [(1, "current", 1), (2, "current", 1)])
        self.write("data/round2.csv", "member,item,rating\nP01,I2,1\n")
        state = consensus.rounds_state(self.root)
        self.assertEqual((state["state"], state["passed"]), ("open", False))
        self.assertEqual(state["stale"], [{"round": 2, "reasons": ["file-changed"]}])


class Comments(Workspace):
    def test_no_output_or_record_carries_a_comment(self) -> None:
        from skills._core.qualitative import consensus
        self.ready()
        self.responses("round1.csv", ROUND_1)
        self.record_round(1, "round1.csv")
        self.responses("round2.csv", ROUND_2)
        self.record_round(2, "round2.csv")
        self.ok("round", "status")
        self.ok("round", "status", "--round", "2")
        self.ok("status")
        self.responses("bad.csv", [f"P01,I1,{SECRET},", f"{SECRET},I1,4,"])
        self.refused("RATING_INVALID", "round", "record", "--round", "2", "--file", "data/bad.csv", "--by", "Ana",
                     "--reason", "x")
        self.responses("bad2.csv", [f"{SECRET},I1,4,"])
        self.refused("MEMBER_UNKNOWN", "round", "record", "--round", "2", "--file", "data/bad2.csv", "--by", "Ana",
                     "--reason", "x")
        self.write("data/bad3.csv", f"P01,I1,4,{SECRET}\n")
        self.refused("CSV_INVALID", "round", "record", "--round", "2", "--file", "data/bad3.csv", "--by", "Ana",
                     "--reason", "x")
        for output in self.outputs:
            self.assertNotIn(SECRET, output)
            self.assertNotIn("ZEBRA", output)
        for path in (self.root / "study").rglob("*.json"):
            self.assertNotIn(SECRET, path.read_text(encoding="utf-8"), path)
        self.assertNotIn(SECRET, json.dumps(consensus.consensus_status(self.root)))


class Confinement(Workspace):
    def test_paths_outside_the_workspace_are_refused(self) -> None:
        self.ready()
        outside_dir = tempfile.TemporaryDirectory(prefix="qualitative-outside-")
        self.addCleanup(outside_dir.cleanup)
        outside = Path(outside_dir.name) / "round1.csv"
        outside.write_text("member,item,rating\nP01,I1,4\n", encoding="utf-8")
        inside = self.responses("round1.csv", ROUND_1)
        (self.root / "data/link.csv").symlink_to(outside)
        for given in (str(outside), str(inside), f"../{Path(outside_dir.name).name}/round1.csv", "data/link.csv"):
            with self.subTest(given=given):
                self.refused("PATH_OUTSIDE_WORKSPACE", "round", "record", "--round", "1", "--file", given,
                             "--by", "Ana")
        for given in (str(outside), "data/link.csv"):
            with self.subTest(micmac=given):
                self.refused("PATH_OUTSIDE_WORKSPACE", "micmac", "compute", "--file", given, "--by", "Ana")

    def test_a_record_folder_linked_out_of_the_workspace_is_refused(self) -> None:
        outside_dir = tempfile.TemporaryDirectory(prefix="qualitative-outside-")
        self.addCleanup(outside_dir.cleanup)
        (self.root / "study").mkdir()
        (self.root / "study/consensus").symlink_to(outside_dir.name, target_is_directory=True)
        self.refused("PATH_OUTSIDE_WORKSPACE", "panel", "add", "--member", "P01", "--expertise", "x", "--by", "Ana")
        self.assertEqual(list(Path(outside_dir.name).iterdir()), [])

    def test_a_stored_path_leaving_the_workspace_is_never_followed(self) -> None:
        from skills._core.qualitative import consensus
        self.ready()
        self.responses("round1.csv", ROUND_1)
        self.record_round(1, "round1.csv")
        path = self.root / "study/consensus/rounds.json"
        for stored in ("../../etc/passwd", "/etc/passwd", "data/\x00x.csv"):
            with self.subTest(stored=stored):
                data = json.loads(path.read_text(encoding="utf-8"))
                data["history"][0]["file"] = stored
                path.write_text(json.dumps(data), encoding="utf-8")
                r1 = consensus.round_results(self.root)["rounds"][0]
                self.assertEqual(r1["reasons"][0], "file-outside" if "\x00" not in stored else "file-missing")
                self.assertIsNone(r1["items"])


class Micmac(Workspace):
    def test_compute_binds_the_matrix_and_goes_stale_when_it_changes(self) -> None:
        """The hand-computed 4x4 of test_qualitative_consensus_stats (P counted as 4): direct sums
        A 8/2, B 6/6, C 1/6, D 1/2; stable at k = 3 with A 104/32, B 80/80, C 20/84, D 20/28."""
        matrix = self.write("data/matrix.csv", "\n".join(MATRIX) + "\n")
        out = self.ok("micmac", "compute", "--file", "data/matrix.csv", "--by", "Ana Ruiz")
        result = out["micmac"]
        self.assertEqual((result["state"], result["file"], result["sha256"], result["p_value"], result["p_entries"],
                          result["power"], result["stable"]),
                         ("current", "data/matrix.csv", sha256(matrix), 4, 1, 3, True))
        self.assertEqual([(v["name"], v["influence"], v["dependence"], v["quadrant"])
                          for v in result["direct"]["variables"]],
                         [("A", 8, 2, "influential"), ("B", 6, 6, "relay"), ("C", 1, 6, "dependent"),
                          ("D", 1, 2, "autonomous")])
        self.assertEqual([(v["influence"], v["dependence"]) for v in result["indirect"]["variables"]],
                         [(104, 32), (80, 80), (20, 84), (20, 28)])
        self.refused("RECORD_UNCHANGED", "micmac", "compute", "--file", "data/matrix.csv", "--by", "Ana Ruiz")
        fixed = self.ok("micmac", "compute", "--file", "data/matrix.csv", "--power", "2", "--p-value", "3",
                        "--by", "Ana Ruiz")["micmac"]
        self.assertEqual((fixed["power"], fixed["power_mode"], fixed["stable"], fixed["p_value"]),
                         (2, "fixed", False, 3))
        self.assertEqual(fixed["direct"]["variables"][0]["influence"], 7)  # 3 + 3 + 1 with P = 3
        self.assertEqual(self.ok("micmac", "status")["micmac"]["state"], "current")
        matrix.write_text(matrix.read_text(encoding="utf-8").replace("D,0,1,0,0", "D,1,1,0,0"), encoding="utf-8")
        state = self.ok("micmac", "status")["micmac"]
        self.assertEqual((state["state"], state["reasons"]), ("stale", ["file-changed"]))

    def test_matrix_refusals(self) -> None:
        cases = {"MATRIX_ENTRY_INVALID": ["x,A,B", "A,0,5", "B,1,0"],
                 "DIAGONAL_NONZERO": ["x,A,B", "A,1,2", "B,1,0"],
                 "MATRIX_NOT_SQUARE": ["x,A,B", "A,0,2", "B,1,0", "C,1,1"],
                 "MATRIX_NAMES_MISMATCH": ["x,A,B", "B,0,2", "A,1,0"],
                 "MATRIX_INVALID": ["x,A", "A,0"]}
        for code, rows in cases.items():
            with self.subTest(code=code):
                self.write("data/m.csv", "\n".join(rows) + "\n")
                self.refused(code, "micmac", "compute", "--file", "data/m.csv", "--by", "Ana")
        self.write("data/m.csv", "\n".join(MATRIX) + "\n")
        for power in ("1", "11", "x"):
            self.refused("POWER_INVALID", "micmac", "compute", "--file", "data/m.csv", "--power", power, "--by", "Ana")
        self.refused("P_VALUE_INVALID", "micmac", "compute", "--file", "data/m.csv", "--p-value", "-1", "--by", "Ana")
        self.refused("APPROVER_MISSING", "micmac", "compute", "--file", "data/m.csv")
        self.assertFalse((self.root / "study/consensus/micmac.json").exists())


class Readers(Workspace):
    def test_readers_never_raise_on_corrupt_records(self) -> None:
        from skills._core.qualitative import consensus
        self.ready()
        self.responses("round1.csv", ROUND_1)
        self.record_round(1, "round1.csv")
        self.write("data/matrix.csv", "\n".join(MATRIX) + "\n")
        self.ok("micmac", "compute", "--file", "data/matrix.csv", "--by", "Ana")
        for name in ("panel", "plan", "rounds", "micmac"):
            for garbage in ("{not json", json.dumps({"history": [{"round": "x", "file": 3}]}),
                            json.dumps({"history": "x"}), json.dumps([1])):
                with self.subTest(record=name, garbage=garbage):
                    path = self.root / f"study/consensus/{name}.json"
                    original = path.read_text(encoding="utf-8")
                    path.write_text(garbage, encoding="utf-8")
                    status = consensus.consensus_status(self.root)
                    self.assertTrue(status["warnings"])
                    consensus.rounds_state(self.root)
                    consensus.micmac_state(self.root)
                    consensus.round_results(self.root)
                    self.ok("status")
                    path.write_text(original, encoding="utf-8")
        self.assertEqual(consensus.micmac_state(self.root)["state"], "current")
        self.assertEqual(consensus.micmac_state(Path(self.root) / "nowhere")["state"], "absent")

    def test_status_reports_everything_and_usage_errors_exit_2(self) -> None:
        self.ready()
        status = self.ok("status")
        self.assertEqual((status["panel"]["size"], status["plan"]["state"], status["rounds"]["state"],
                          status["micmac"]["state"]), (4, "current", "open", "absent"))
        self.assertEqual(self.ok("round", "--root", str(self.root), "status")["gate"]["gate"], "G-ROUNDS")
        code, out = self.run_cli("panel", "remove")
        self.assertEqual((code, out["error"]), (2, "USAGE"))
        code, out = self.run_cli("round", "status", "--file", "x")
        self.assertEqual((code, out["error"]), (2, "USAGE"))


if __name__ == "__main__":
    unittest.main()
