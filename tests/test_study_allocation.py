"""The allocation record of an intervention study (paper-type-lines S8, T8-A1, decisions J2 and J3 of L100).

The operator generates the allocation sequence with their own tool or service
and records it with `study_cli.py allocation record`: the CLI binds the file's
sha256 and row count and the protocol lock's sha256 in `study/allocation.json`
(gate G-ALLOCATION). It never reads out, prints or alters the sequence: every
test below writes a sequence of recognizable tokens and checks that no output
and no record carries one. Changing or removing the file, or amending the
protocol, makes the record stale. J3: the registration reader already exposes
`retrospective`, so a board can tell a prospective registration apart.
Every test goes through `study_cli.py`; the last ones import the readers."""

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
CLI = REPO / "skills" / "_core" / "empirical" / "study_cli.py"
MARKER = "<!-- proposal-workspace:artifact:v1 -->\n"
TOKENS = ("ZEBRA-ARM-QX17", "OKAPI-ARM-QX42")
SEQUENCE = "id,arm\n" + "".join(f"P{n:03d},{TOKENS[n % 2]}\n" for n in range(1, 13))
CONCEALMENT = ("--concealment", "central web service; arms revealed only after enrolment")
REGISTRY = ("--registry", "ClinicalTrials.gov", "--id", "NCT07000001", "--date", "2026-04-01")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class AllocationWorkspace(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="study-allocation-")
        self.base = Path(self._tmp.name)
        self.root = self.base / "workspace"
        self.root.mkdir()
        self.addCleanup(self._tmp.cleanup)
        self.outputs: list[str] = []

    def tearDown(self) -> None:
        for text in self.outputs:
            for token in TOKENS:
                self.assertNotIn(token, text, "the allocation sequence leaked into an output")
        record = self.root / "study" / "allocation.json"
        if record.exists():
            for token in TOKENS:
                self.assertNotIn(token, record.read_text(encoding="utf-8"))

    def run_cli(self, *args: str) -> tuple[int, dict]:
        proc = subprocess.run([sys.executable, str(CLI), *args, "--root", str(self.root)],
                              capture_output=True, text=True, cwd=str(REPO))
        self.outputs += [proc.stdout, proc.stderr]
        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1, f"one JSON object expected, got {proc.stdout!r} / {proc.stderr!r}")
        return proc.returncode, json.loads(lines[0])

    def refused(self, code: str, *args: str) -> dict:
        exit_code, out = self.run_cli(*args)
        self.assertEqual((exit_code, out["ok"], out.get("error")), (1, False, code), out)
        self.assertTrue(out["message"])
        return out

    def ok(self, *args: str) -> dict:
        exit_code, out = self.run_cli(*args)
        self.assertEqual((exit_code, out["ok"]), (0, True), out)
        return out

    def revision(self, version: int, body: str = "") -> Path:
        path = self.root / "protocol" / f"study-protocol-walking-v{version:02d}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(MARKER + f"# Walking trial protocol v{version}\n\n**Primary outcome:** O1 -- BP\n{body}",
                        encoding="utf-8")
        return path

    def approved(self) -> Path:
        path = self.revision(1)
        self.ok("protocol", "approve", "--by", "Ana Ruiz")
        return path

    def amended(self) -> None:
        self.revision(2, body="\nAmended eligibility.\n")
        self.ok("protocol", "amend", "--by", "Ana Ruiz", "--reason", "widened the age range")

    def sequence(self, text: str = SEQUENCE, name: str = "allocation/sequence.csv") -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def record_args(self, *extra: str, file: str = "allocation/sequence.csv") -> tuple[str, ...]:
        return ("allocation", "record", "--file", file, "--method", "simple", *CONCEALMENT, *extra)

    def allocation(self) -> dict:
        return json.loads((self.root / "study" / "allocation.json").read_text(encoding="utf-8"))

    def lock(self) -> dict:
        return json.loads((self.root / "study" / "protocol.lock.json").read_text(encoding="utf-8"))


class RecordTests(AllocationWorkspace):
    def test_recording_binds_the_file_and_the_lock_without_touching_the_sequence(self) -> None:
        self.approved()
        path = self.sequence()
        before = path.read_bytes()
        out = self.ok(*self.record_args("--by", "Ana Ruiz", "--note", "list from the trial statistician"))
        self.assertEqual(out["path"], "study/allocation.json")
        self.assertEqual(path.read_bytes(), before)
        data = self.allocation()
        self.assertEqual(data["schema"], 1)
        self.assertEqual(len(data["history"]), 1)
        entry = data["history"][0]
        self.assertEqual({key: entry[key] for key in entry if key != "at"},
                         {"by": "Ana Ruiz", "file": "allocation/sequence.csv", "sha256": sha256(path), "rows": 13,
                          "method": "simple", "block_size": None, "strata": None,
                          "concealment": "central web service; arms revealed only after enrolment",
                          "note": "list from the trial statistician",
                          "protocol_revision": "protocol/study-protocol-walking-v01.md",
                          "protocol_sha256": self.lock()["sha256"]})
        self.assertTrue(entry["at"].endswith("Z"))
        state = out["allocation"]
        self.assertEqual((state["state"], state["current"], state["reasons"], state["records"], state["warnings"]),
                         ("current", True, [], 1, []))

    def test_block_and_stratified_methods_keep_their_details(self) -> None:
        self.approved()
        self.sequence()
        self.ok("allocation", "record", "--file", "allocation/sequence.csv", "--method", "block", "--block-size",
                "4", *CONCEALMENT, "--by", "Ana Ruiz")
        self.assertEqual((self.allocation()["history"][-1]["method"], self.allocation()["history"][-1]["block_size"]),
                         ("block", 4))
        self.ok("allocation", "record", "--file", "allocation/sequence.csv", "--method", "stratified", "--strata",
                "site; age band", *CONCEALMENT, "--by", "Ana Ruiz")
        entry = self.allocation()["history"][-1]
        self.assertEqual((entry["method"], entry["strata"], entry["block_size"]), ("stratified", "site; age band", None))
        self.assertEqual(len(self.allocation()["history"]), 2)

    def test_an_absolute_path_inside_the_workspace_is_stored_relative(self) -> None:
        self.approved()
        path = self.sequence()
        self.ok(*self.record_args("--by", "Ana Ruiz", file=str(path)))
        self.assertEqual(self.allocation()["history"][0]["file"], "allocation/sequence.csv")


class RefusalTests(AllocationWorkspace):
    def test_refuses_before_the_protocol_is_approved_and_current(self) -> None:
        self.sequence()
        self.refused("PROTOCOL_NOT_APPROVED", *self.record_args("--by", "Ana Ruiz"))
        self.approved()
        self.revision(2)
        self.refused("PROTOCOL_CHANGED", *self.record_args("--by", "Ana Ruiz"))
        self.assertFalse((self.root / "study" / "allocation.json").exists())

    def test_the_operator_is_required(self) -> None:
        self.approved()
        self.sequence()
        self.refused("APPROVER_MISSING", *self.record_args())
        self.refused("APPROVER_MISSING", *self.record_args("--by", "  "))
        self.assertFalse((self.root / "study" / "allocation.json").exists())

    def test_field_refusals(self) -> None:
        self.approved()
        self.sequence()
        by = ("--by", "Ana Ruiz")
        self.refused("FIELD_MISSING", "allocation", "record", "--method", "simple", *CONCEALMENT, *by)
        self.refused("FIELD_MISSING", "allocation", "record", "--file", "allocation/sequence.csv", *CONCEALMENT, *by)
        self.refused("CONCEALMENT_MISSING", "allocation", "record", "--file", "allocation/sequence.csv",
                     "--method", "simple", *by)
        self.refused("CONCEALMENT_MISSING", "allocation", "record", "--file", "allocation/sequence.csv",
                     "--method", "simple", "--concealment", "   ", *by)
        self.refused("FIELDS_CONFLICT", *self.record_args("--block-size", "4", *by))
        # A block size goes with block and stratified allocation only.
        self.refused("FIELDS_CONFLICT", "allocation", "record", "--file", "allocation/sequence.csv", "--method",
                     "minimisation", "--strata", "site", "--block-size", "4", *CONCEALMENT, *by)
        self.refused("FIELDS_CONFLICT", *self.record_args("--strata", "site", *by))
        self.refused("FIELDS_CONFLICT", "allocation", "record", "--file", "allocation/sequence.csv", "--method",
                     "block", "--strata", "site", *CONCEALMENT, *by)
        self.refused("FIELD_MISSING", "allocation", "record", "--file", "allocation/sequence.csv", "--method",
                     "stratified", *CONCEALMENT, *by)
        self.refused("FIELD_MISSING", "allocation", "record", "--file", "allocation/sequence.csv", "--method",
                     "minimisation", *CONCEALMENT, *by)
        for size in ("0", "1", "four", "-2"):
            self.refused("BLOCK_SIZE_INVALID", "allocation", "record", "--file", "allocation/sequence.csv",
                         "--method", "block", "--block-size", size, *CONCEALMENT, *by)
        self.refused("TEXT_INVALID", *self.record_args("--note", "a\x07b", *by))
        self.assertFalse((self.root / "study" / "allocation.json").exists())

    def test_a_non_ascii_digit_block_size_is_refused(self) -> None:
        # Superscript two passes str.isdigit() but int() rejects it; Arabic-Indic four passes
        # int() but is not the ASCII whole number the record documents.
        self.approved()
        self.sequence()
        for size in ("\u00b2", "\u0664", "4\u00b2"):
            with self.subTest(size=size):
                self.refused("BLOCK_SIZE_INVALID", "allocation", "record", "--file", "allocation/sequence.csv",
                             "--method", "block", "--block-size", size, *CONCEALMENT, "--by", "Ana Ruiz")
        self.assertFalse((self.root / "study" / "allocation.json").exists())

    def test_status_takes_no_record_option(self) -> None:
        """`allocation status` reads the recorded list only: a record option is a usage error, never ignored."""
        self.approved()
        self.sequence()
        self.sequence(name="allocation/other.csv")
        self.ok(*self.record_args("--by", "Ana Ruiz"))
        for option in (("--file", "allocation/other.csv"), ("--by", "Ana Ruiz"), ("--method", "simple"),
                       ("--block-size", "4"), ("--strata", "site"), CONCEALMENT, ("--note", "x")):
            with self.subTest(option=option[0]):
                exit_code, out = self.run_cli("allocation", "status", *option)
                self.assertEqual((exit_code, out["ok"], out["error"]), (2, False, "USAGE"), out)
        self.assertEqual(self.ok("allocation", "status")["allocation"]["state"], "current")

    def test_stratified_permuted_blocks_record_their_block_size(self) -> None:
        # Stratified permuted blocks are a common trial design.
        self.approved()
        self.sequence()
        result = self.ok("allocation", "record", "--file", "allocation/sequence.csv", "--method", "stratified",
                         "--strata", "site", "--block-size", "4", *CONCEALMENT, "--by", "Ana Ruiz")
        self.assertEqual((result["allocation"]["method"], result["allocation"]["block_size"]), ("stratified", 4))

    def test_an_unknown_method_is_a_usage_error(self) -> None:
        self.approved()
        self.sequence()
        exit_code, out = self.run_cli("allocation", "record", "--file", "allocation/sequence.csv", "--method",
                                      "coin", *CONCEALMENT, "--by", "Ana Ruiz")
        self.assertEqual((exit_code, out["error"]), (2, "USAGE"))

    def test_file_refusals(self) -> None:
        self.approved()
        by = ("--by", "Ana Ruiz")
        self.refused("ALLOCATION_FILE_MISSING", *self.record_args(*by))
        (self.root / "allocation" / "folder").mkdir(parents=True)
        self.refused("ALLOCATION_FILE_MISSING", *self.record_args(*by, file="allocation/folder"))
        self.sequence("")
        self.refused("ALLOCATION_FILE_EMPTY", *self.record_args(*by))
        self.sequence("\n  \n\n")
        self.refused("ALLOCATION_FILE_EMPTY", *self.record_args(*by))
        outside = self.base / "outside.csv"
        outside.write_text(SEQUENCE, encoding="utf-8")
        self.refused("ALLOCATION_FILE_OUTSIDE", *self.record_args(*by, file="../outside.csv"))
        self.refused("ALLOCATION_FILE_OUTSIDE", *self.record_args(*by, file=str(outside)))
        link = self.root / "allocation" / "link.csv"
        os.symlink(outside, link)
        self.refused("ALLOCATION_FILE_OUTSIDE", *self.record_args(*by, file="allocation/link.csv"))
        self.assertFalse((self.root / "study" / "allocation.json").exists())

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root reads a file whatever its mode")
    def test_an_unreadable_file_is_refused(self) -> None:
        self.approved()
        path = self.sequence()
        path.chmod(0)
        self.addCleanup(path.chmod, 0o644)
        self.refused("ALLOCATION_FILE_UNREADABLE", *self.record_args("--by", "Ana Ruiz"))
        self.assertFalse((self.root / "study" / "allocation.json").exists())

    def test_an_identical_record_is_refused(self) -> None:
        self.approved()
        self.sequence()
        self.ok(*self.record_args("--by", "Ana Ruiz"))
        self.refused("RECORD_UNCHANGED", *self.record_args("--by", "Ana Ruiz"))

    def test_a_corrupt_record_is_reported_and_refused(self) -> None:
        self.approved()
        self.sequence()
        (self.root / "study" / "allocation.json").write_text("[]", encoding="utf-8")
        out = self.ok("allocation", "status")
        self.assertEqual(out["allocation"]["state"], "corrupt")
        self.assertIn("ALLOCATION_CORRUPT", [w["code"] for w in self.ok("status")["warnings"]])
        self.refused("ALLOCATION_CORRUPT", *self.record_args("--by", "Ana Ruiz"))


class StalenessTests(AllocationWorkspace):
    def recorded(self) -> Path:
        self.approved()
        path = self.sequence()
        self.ok(*self.record_args("--by", "Ana Ruiz"))
        return path

    def status(self) -> dict:
        return self.ok("allocation", "status")["allocation"]

    def test_absent_until_recorded_and_no_warning_for_studies_without_allocation(self) -> None:
        self.assertEqual(self.status(), {"state": "absent"})
        self.approved()
        out = self.ok("status")
        self.assertEqual(out["allocation"], {"state": "absent"})
        self.assertNotIn("ALLOCATION_ABSENT", [w["code"] for w in out["warnings"]])

    def test_a_changed_file_makes_the_record_stale(self) -> None:
        path = self.recorded()
        path.write_text(SEQUENCE.replace(TOKENS[0], TOKENS[1], 1), encoding="utf-8")
        state = self.status()
        self.assertEqual((state["state"], state["current"], state["reasons"]), ("stale", False, ["file-changed"]))
        self.assertEqual([w["code"] for w in state["warnings"]], ["ALLOCATION_STALE"])
        self.assertIn("ALLOCATION_STALE", [w["code"] for w in self.ok("status")["warnings"]])
        self.ok(*self.record_args("--by", "Ana Ruiz"))
        state = self.status()
        self.assertEqual((state["state"], state["records"]), ("current", 2))

    def test_a_removed_file_makes_the_record_stale(self) -> None:
        self.recorded().unlink()
        state = self.status()
        self.assertEqual((state["state"], state["reasons"]), ("stale", ["file-missing"]))

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root reads a file whatever its mode")
    def test_an_unreadable_file_makes_the_record_stale(self) -> None:
        path = self.recorded()
        path.chmod(0)
        self.addCleanup(path.chmod, 0o644)
        state = self.status()
        self.assertEqual((state["state"], state["reasons"]), ("stale", ["file-unreadable"]))

    def test_a_stored_path_outside_the_workspace_is_stale_and_never_hashed(self) -> None:
        """A hand-edited `file` that leaves the workspace is confined like the record command:
        an absolute path, a traversal or a link pointing out is `file-outside`, never hashed."""
        path = self.recorded()
        outside = self.base / "outside.csv"
        outside.write_text(SEQUENCE, encoding="utf-8")
        link = self.root / "allocation" / "link.csv"
        os.symlink(outside, link)
        record = self.root / "study" / "allocation.json"
        original = record.read_text(encoding="utf-8")
        hashed: list[Path] = []
        if str(REPO) not in sys.path:
            sys.path.insert(0, str(REPO))
        from skills._core.empirical import records
        real_sha256 = records.sha256

        def spy(target: Path) -> str:
            hashed.append(Path(target))
            return real_sha256(target)

        for stored in ("../outside.csv", str(outside), "allocation/link.csv",
                       "allocation/../../outside.csv"):
            with self.subTest(stored=stored):
                data = json.loads(original)
                data["history"][-1]["file"] = stored
                record.write_text(json.dumps(data), encoding="utf-8")
                state = self.status()
                self.assertEqual((state["state"], state["current"], state["reasons"]),
                                 ("stale", False, ["file-outside"]))
                self.assertEqual([w["code"] for w in state["warnings"]], ["ALLOCATION_STALE"])
                hashed.clear()
                records.sha256 = spy
                try:
                    self.assertEqual(records.allocation_state(self.root)["reasons"], ["file-outside"])
                finally:
                    records.sha256 = real_sha256
                self.assertNotIn(outside.resolve(), [target.resolve() for target in hashed])
        record.write_text(original, encoding="utf-8")
        self.assertEqual(self.status()["state"], "current")
        self.assertTrue(path.is_file())

    def test_an_amendment_makes_the_record_stale_until_recorded_again(self) -> None:
        self.recorded()
        self.amended()
        state = self.status()
        self.assertEqual((state["state"], state["reasons"]), ("stale", ["protocol-amended"]))
        self.ok(*self.record_args("--by", "Ana Ruiz"))
        state = self.status()
        self.assertEqual((state["state"], state["protocol_revision"]),
                         ("current", "protocol/study-protocol-walking-v02.md"))

    def test_an_unamended_protocol_change_makes_the_record_stale(self) -> None:
        self.recorded()
        self.revision(2)
        self.assertEqual(self.status()["reasons"], ["protocol-changed"])


class RegistrationProspectiveTests(AllocationWorkspace):
    """J3: `gate_state` exposes `retrospective`; false means prospective, null means unknown."""

    def test_the_registration_reader_tells_prospective_from_retrospective(self) -> None:
        if str(REPO) not in sys.path:
            sys.path.insert(0, str(REPO))
        from skills._core.empirical import records
        self.approved()
        self.ok("registration", "record", "--by", "Ana Ruiz", *REGISTRY)
        self.assertIsNone(records.gate_state(self.root, "registration")["retrospective"])
        self.ok("registration", "record", "--by", "Ana Ruiz", *REGISTRY, "--first-enrolment", "2026-05-10")
        self.assertIs(records.gate_state(self.root, "registration")["retrospective"], False)
        self.ok("registration", "record", "--by", "Ana Ruiz", *REGISTRY, "--first-enrolment", "2026-03-10")
        self.assertIs(records.gate_state(self.root, "registration")["retrospective"], True)


class ImportableReaderTests(AllocationWorkspace):
    def setUp(self) -> None:
        super().setUp()
        if str(REPO) not in sys.path:
            sys.path.insert(0, str(REPO))
        from skills._core.empirical import records
        self.records = records

    def tree(self) -> list[tuple[str, bytes]]:
        return sorted((str(p.relative_to(self.root)), p.read_bytes() if p.is_file() else b"")
                      for p in self.root.rglob("*"))

    def test_the_reader_matches_the_cli_and_writes_nothing(self) -> None:
        self.assertEqual(self.records.allocation_state(self.root), {"state": "absent"})
        self.approved()
        path = self.sequence()
        self.ok(*self.record_args("--by", "Ana Ruiz"))
        path.write_text(SEQUENCE + "P013,ZEBRA-ARM-QX17\n", encoding="utf-8")
        before = self.tree()
        status = self.ok("status")
        state = self.records.allocation_state(self.root)
        self.assertEqual(state, self.ok("allocation", "status")["allocation"])
        self.assertEqual(state, status["allocation"])
        self.assertEqual(self.records.study_status(self.root), {k: v for k, v in status.items() if k != "ok"})
        self.assertEqual(self.tree(), before)
        self.outputs.append(json.dumps(self.records.study_status(self.root)))


if __name__ == "__main__":
    unittest.main()
