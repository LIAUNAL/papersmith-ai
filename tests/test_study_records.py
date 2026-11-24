"""Operator records of an empirical study (paper-type-lines S7, T7-U2, decisions D5 and D6).

The operator approves a published study-protocol revision (gate
G-STUDY-PROTOCOL, `study/protocol.lock.json`, bound to the sha256 of its
bytes) and amends the lock when a newer revision replaces it; the ethics
approval (`study/ethics.json`) and the trial or study registration
(`study/registration.json`) are recorded beside it, each bound to the lock's
hash, so an amendment marks them stale (a warning, never a refusal).
Every test goes through `study_cli.py`, as an operator or an agent would; the
last ones import the side-effect-free readers later units call."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CLI = REPO / "skills" / "_core" / "empirical" / "study_cli.py"
MARKER = "<!-- proposal-workspace:artifact:v1 -->\n"

ETHICS = ("--committee", "Hospital Ethics Board", "--code", "CEI-2026-041", "--date", "2026-03-02",
          "--consent", "written informed consent")
REGISTRY = ("--registry", "ClinicalTrials.gov", "--id", "NCT07000001", "--date", "2026-04-01")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class StudyWorkspace(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="study-records-")
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def run_cli(self, *args: str) -> tuple[int, dict]:
        proc = subprocess.run([sys.executable, str(CLI), *args, "--root", str(self.root)],
                              capture_output=True, text=True, cwd=str(REPO))
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

    def revision(self, version: int, slug: str = "walking", body: str = "", managed: bool = True) -> Path:
        path = self.root / "protocol" / f"study-protocol-{slug}-v{version:02d}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        text = f"# Walking trial protocol v{version}\n\n**Primary outcome:** O1 -- systolic BP; time point: 12 weeks\n{body}"
        path.write_text((MARKER if managed else "") + text, encoding="utf-8")
        return path

    def lock(self) -> dict:
        return json.loads((self.root / "study" / "protocol.lock.json").read_text(encoding="utf-8"))

    def record(self, name: str) -> dict:
        return json.loads((self.root / "study" / f"{name}.json").read_text(encoding="utf-8"))

    def approved(self, version: int = 1) -> Path:
        path = self.revision(version)
        self.ok("protocol", "approve", "--by", "Ana Ruiz")
        return path

    def amended(self) -> Path:
        newer = self.revision(2, body="\nAmended eligibility.\n")
        self.ok("protocol", "amend", "--by", "Ana Ruiz", "--reason", "widened the age range")
        return newer


class ProtocolLockTests(StudyWorkspace):
    def test_status_before_any_approval_is_absent(self) -> None:
        out = self.ok("protocol", "status")
        self.assertEqual(out["protocol"]["state"], "absent")
        self.assertFalse((self.root / "study").exists())

    def test_approve_defaults_to_the_latest_managed_revision_and_pins_its_hash(self) -> None:
        self.revision(1)
        latest = self.revision(2)
        out = self.ok("protocol", "approve", "--by", "  Ana Ruiz ")
        lock = self.lock()
        self.assertEqual(lock["gate"], "G-STUDY-PROTOCOL")
        self.assertEqual(lock["revision"], "protocol/study-protocol-walking-v02.md")
        self.assertEqual(lock["sha256"], sha256(latest))
        self.assertEqual(lock["approved_by"], "Ana Ruiz")
        self.assertRegex(lock["approved_at"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
        self.assertEqual(lock["amendments"], [])
        self.assertEqual(out["approval"], lock)
        self.assertEqual(self.ok("protocol", "status")["protocol"]["state"], "current")

    def test_approve_an_explicit_revision(self) -> None:
        first = self.revision(1)
        self.revision(2)
        self.ok("protocol", "approve", "--by", "Ana Ruiz", "--revision", "protocol/study-protocol-walking-v01.md")
        self.assertEqual((self.lock()["revision"], self.lock()["sha256"]),
                         ("protocol/study-protocol-walking-v01.md", sha256(first)))
        state = self.ok("protocol", "status")["protocol"]
        self.assertEqual((state["state"], state["reasons"]), ("changed", ["newer-revision"]))

    def test_the_operator_is_required(self) -> None:
        self.revision(1)
        self.refused("APPROVER_MISSING", "protocol", "approve")
        self.refused("APPROVER_MISSING", "protocol", "approve", "--by", "   ")
        self.assertFalse((self.root / "study" / "protocol.lock.json").exists())

    def test_approve_refuses_without_a_revision_an_unmanaged_one_or_one_outside_protocol(self) -> None:
        self.refused("PROTOCOL_ABSENT", "protocol", "approve", "--by", "Ana Ruiz")
        self.revision(1, managed=False)
        self.refused("PROTOCOL_ABSENT", "protocol", "approve", "--by", "Ana Ruiz")
        self.refused("REVISION_NOT_MANAGED", "protocol", "approve", "--by", "Ana Ruiz",
                     "--revision", "protocol/study-protocol-walking-v01.md")
        self.refused("REVISION_ABSENT", "protocol", "approve", "--by", "Ana Ruiz",
                     "--revision", "protocol/study-protocol-walking-v07.md")
        (self.root / "notes.md").write_text(MARKER + "x", encoding="utf-8")
        self.refused("REVISION_INVALID", "protocol", "approve", "--by", "Ana Ruiz", "--revision", "notes.md")
        self.refused("REVISION_INVALID", "protocol", "approve", "--by", "Ana Ruiz",
                     "--revision", "protocol/../notes.md")
        self.assertFalse((self.root / "study").exists())

    def test_two_lineages_at_the_same_latest_version_are_ambiguous(self) -> None:
        self.revision(1, slug="walking")
        self.revision(1, slug="cycling")
        self.refused("REVISION_AMBIGUOUS", "protocol", "approve", "--by", "Ana Ruiz")
        self.ok("protocol", "approve", "--by", "Ana Ruiz", "--revision", "protocol/study-protocol-cycling-v01.md")

    def test_a_second_approval_is_refused(self) -> None:
        self.approved()
        self.refused("PROTOCOL_ALREADY_APPROVED", "protocol", "approve", "--by", "Ana Ruiz")

    def test_status_reports_an_edited_or_missing_locked_revision_as_changed(self) -> None:
        path = self.approved()
        path.write_text(path.read_text(encoding="utf-8") + "edited by hand\n", encoding="utf-8")
        state = self.ok("protocol", "status")["protocol"]
        self.assertEqual((state["state"], state["reasons"]), ("changed", ["revision-edited"]))
        path.unlink()
        state = self.ok("protocol", "status")["protocol"]
        self.assertEqual((state["state"], state["reasons"]), ("changed", ["revision-missing"]))

    def test_amend_moves_the_lock_to_the_newer_revision_and_keeps_the_history(self) -> None:
        first = self.approved()
        before = self.lock()
        newer = self.amended()
        lock = self.lock()
        self.assertEqual((lock["revision"], lock["sha256"]), ("protocol/study-protocol-walking-v02.md", sha256(newer)))
        self.assertEqual((lock["approved_by"], lock["approved_at"]), (before["approved_by"], before["approved_at"]))
        [amendment] = lock["amendments"]
        self.assertEqual({key: amendment[key] for key in ("by", "reason", "from_revision", "from_sha256", "revision",
                                                           "sha256")},
                         {"by": "Ana Ruiz", "reason": "widened the age range",
                          "from_revision": "protocol/study-protocol-walking-v01.md", "from_sha256": sha256(first),
                          "revision": "protocol/study-protocol-walking-v02.md", "sha256": sha256(newer)})
        self.assertIn("at", amendment)
        state = self.ok("protocol", "status")["protocol"]
        self.assertEqual((state["state"], state["amendments"]), ("current", 1))

    def test_amend_refusals(self) -> None:
        self.revision(1)
        self.refused("PROTOCOL_NOT_APPROVED", "protocol", "amend", "--by", "Ana Ruiz", "--reason", "x")
        self.ok("protocol", "approve", "--by", "Ana Ruiz")
        self.refused("APPROVER_MISSING", "protocol", "amend", "--reason", "x")
        self.refused("AMENDMENT_REASON_MISSING", "protocol", "amend", "--by", "Ana Ruiz")
        self.refused("PROTOCOL_UNCHANGED", "protocol", "amend", "--by", "Ana Ruiz", "--reason", "x")
        self.revision(2)
        self.ok("protocol", "amend", "--by", "Ana Ruiz", "--reason", "new outcome window")
        self.refused("REVISION_OLDER", "protocol", "amend", "--by", "Ana Ruiz", "--reason", "back",
                     "--revision", "protocol/study-protocol-walking-v01.md")
        self.assertEqual(len(self.lock()["amendments"]), 1)

    def test_amend_moves_the_lock_to_a_newer_revision_with_identical_bytes(self) -> None:
        first = self.approved()
        newer = first.with_name("study-protocol-walking-v02.md")
        newer.write_bytes(first.read_bytes())
        self.assertEqual(self.ok("protocol", "status")["protocol"]["reasons"], ["newer-revision"])
        out = self.ok("protocol", "amend", "--by", "Ana Ruiz", "--reason", "republished without changes")
        self.assertEqual(out["approval"]["revision"], "protocol/study-protocol-walking-v02.md")
        self.assertEqual(self.lock()["amendments"][-1]["from_revision"], "protocol/study-protocol-walking-v01.md")
        self.assertEqual(self.ok("protocol", "status")["protocol"]["state"], "current")
        self.refused("PROTOCOL_UNCHANGED", "protocol", "amend", "--by", "Ana Ruiz", "--reason", "again")

    def test_amend_records_a_hand_edit_of_the_locked_revision(self) -> None:
        path = self.approved()
        path.write_text(path.read_text(encoding="utf-8") + "typo fixed\n", encoding="utf-8")
        self.ok("protocol", "amend", "--by", "Ana Ruiz", "--reason", "typo in the eligibility")
        self.assertEqual(self.lock()["sha256"], sha256(path))
        self.assertEqual(self.ok("protocol", "status")["protocol"]["state"], "current")

    def test_a_corrupt_lock_is_reported_and_refused(self) -> None:
        self.approved()
        (self.root / "study" / "protocol.lock.json").write_text("{not json", encoding="utf-8")
        self.assertEqual(self.ok("protocol", "status")["protocol"]["state"], "corrupt")
        self.refused("PROTOCOL_LOCK_CORRUPT", "protocol", "amend", "--by", "Ana Ruiz", "--reason", "x")
        self.refused("PROTOCOL_LOCK_CORRUPT", "ethics", "record", "--by", "Ana Ruiz", *ETHICS)
        (self.root / "study" / "protocol.lock.json").write_text('{"revision": 3}', encoding="utf-8")
        self.refused("PROTOCOL_LOCK_CORRUPT", "protocol", "amend", "--by", "Ana Ruiz", "--reason", "x")

    def test_a_usage_error_is_typed(self) -> None:
        exit_code, out = self.run_cli("protocol", "sign")
        self.assertEqual((exit_code, out["ok"], out["error"]), (2, False, "USAGE"))


class EthicsTests(StudyWorkspace):
    def test_ethics_is_refused_before_the_protocol_is_approved_or_while_it_changed(self) -> None:
        self.revision(1)
        self.refused("PROTOCOL_NOT_APPROVED", "ethics", "record", "--by", "Ana Ruiz", *ETHICS)
        self.ok("protocol", "approve", "--by", "Ana Ruiz")
        self.revision(2)
        self.refused("PROTOCOL_CHANGED", "ethics", "record", "--by", "Ana Ruiz", *ETHICS)
        self.assertFalse((self.root / "study" / "ethics.json").exists())

    def agree(self, type_id: str, variant: str | None) -> None:
        path = self.root / ".papersmith" / "paper_type.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"agreed": type_id, "agreed_variant": variant}), encoding="utf-8")

    def test_an_experience_report_without_a_protocol_may_record_why_no_ethics_applies(self) -> None:
        """K5: an experience report keeps the protocol optional, so with no protocol at all it
        records a not-applicable ethics statement unbound to a lock; once a protocol is
        approved that record is no longer current and is recorded again against it."""
        self.agree("qualitative-participatory", "experience-report")
        self.refused("PROTOCOL_NOT_APPROVED", "ethics", "record", "--by", "Ana Ruiz", *ETHICS)
        out = self.ok("ethics", "record", "--by", "Ana Ruiz", "--not-applicable", "--reason",
                      "the report describes a course; no participant data")
        [entry] = self.record("ethics")["history"]
        self.assertEqual((entry["status"], entry["protocol_revision"], entry["protocol_sha256"]),
                         ("not-applicable", None, None))
        self.assertTrue(out["ethics"]["current"])
        self.approved()
        self.assertFalse(self.ok("status")["ethics"]["current"])

    def test_the_unbound_statement_is_current_only_for_its_own_case(self) -> None:
        """Only an experience report's not-applicable ethics statement may be unbound: a draft
        revision or a change of variant makes it stale, and an unbound registration or a
        hand-edited approved ethics entry never reads as current."""
        self.agree("qualitative-participatory", "experience-report")
        self.ok("ethics", "record", "--by", "Ana Ruiz", "--not-applicable", "--reason", "no participant data")
        self.assertTrue(self.ok("status")["ethics"]["current"])
        self.agree("qualitative-participatory", "qualitative-mixed")
        self.assertFalse(self.ok("status")["ethics"]["current"])
        self.agree("qualitative-participatory", "experience-report")
        self.revision(1)
        self.assertFalse(self.ok("status")["ethics"]["current"])
        (self.root / "protocol" / "study-protocol-walking-v01.md").unlink()
        path = self.root / "study" / "ethics.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["history"][-1]["status"] = "approved"
        path.write_text(json.dumps(data), encoding="utf-8")
        self.assertFalse(self.ok("status")["ethics"]["current"])
        registration = self.root / "study" / "registration.json"
        registration.write_text(json.dumps({"schema": 1, "history": [
            {"by": "Ana Ruiz", "at": "2026-01-01T00:00:00Z", "status": "not-applicable", "reason": "none",
             "protocol_revision": None, "protocol_sha256": None}]}), encoding="utf-8")
        self.assertFalse(self.ok("status")["registration"]["current"])

    def test_only_an_experience_report_without_any_protocol_skips_the_lock(self) -> None:
        not_applicable = ("--not-applicable", "--reason", "no participants")
        for type_id, variant in (("qualitative-participatory", "qualitative-mixed"),
                                 ("qualitative-participatory", None), ("observational-measurement", None)):
            with self.subTest(variant=variant, type_id=type_id):
                self.agree(type_id, variant)
                self.refused("PROTOCOL_NOT_APPROVED", "ethics", "record", "--by", "Ana Ruiz", *not_applicable)
        self.agree("qualitative-participatory", "experience-report")
        self.revision(1)  # a protocol exists, not yet approved: it is approved first
        self.refused("PROTOCOL_NOT_APPROVED", "ethics", "record", "--by", "Ana Ruiz", *not_applicable)
        self.assertFalse((self.root / "study" / "ethics.json").exists())

    def test_ethics_approval_is_bound_to_the_lock(self) -> None:
        self.approved()
        out = self.ok("ethics", "record", "--by", "Ana Ruiz", *ETHICS)
        [entry] = self.record("ethics")["history"]
        self.assertEqual({key: entry[key] for key in ("by", "status", "committee", "code", "date", "consent",
                                                       "protocol_revision", "protocol_sha256")},
                         {"by": "Ana Ruiz", "status": "approved", "committee": "Hospital Ethics Board",
                          "code": "CEI-2026-041", "date": "2026-03-02", "consent": "written informed consent",
                          "protocol_revision": "protocol/study-protocol-walking-v01.md",
                          "protocol_sha256": self.lock()["sha256"]})
        self.assertTrue(out["ethics"]["current"])
        self.assertEqual(out["ethics"]["warnings"], [])

    def test_ethics_refusals(self) -> None:
        self.approved()
        self.refused("APPROVER_MISSING", "ethics", "record", *ETHICS)
        self.refused("FIELD_MISSING", "ethics", "record", "--by", "Ana Ruiz", *ETHICS[:6])
        self.refused("FIELDS_CONFLICT", "ethics", "record", "--by", "Ana Ruiz", *ETHICS, "--not-applicable",
                     "--reason", "no human participants")
        self.refused("REASON_MISSING", "ethics", "record", "--by", "Ana Ruiz", "--not-applicable")
        self.refused("DATE_INVALID", "ethics", "record", "--by", "Ana Ruiz", *ETHICS[:5], "2026-02-30",
                     *ETHICS[6:])
        self.refused("DATE_INVALID", "ethics", "record", "--by", "Ana Ruiz", *ETHICS[:5], "02/03/2026",
                     *ETHICS[6:])
        self.refused("TEXT_INVALID", "ethics", "record", "--by", "Ana Ruiz", "--committee", "Board\x07",
                     *ETHICS[2:])
        self.assertFalse((self.root / "study" / "ethics.json").exists())
        self.ok("ethics", "record", "--by", "Ana Ruiz", *ETHICS)
        self.refused("RECORD_UNCHANGED", "ethics", "record", "--by", "Luis Pardo", *ETHICS)

    def test_not_applicable_needs_a_reason_and_is_recorded(self) -> None:
        self.approved()
        out = self.ok("ethics", "record", "--by", "Ana Ruiz", "--not-applicable", "--reason",
                      "bench calibration with no human or animal participants")
        [entry] = self.record("ethics")["history"]
        self.assertEqual((entry["status"], entry["reason"]),
                         ("not-applicable", "bench calibration with no human or animal participants"))
        self.assertNotIn("committee", entry)
        self.assertEqual(out["ethics"]["status"], "not-applicable")

    def test_an_amendment_marks_ethics_stale_as_a_warning_until_recorded_again(self) -> None:
        self.approved()
        self.ok("ethics", "record", "--by", "Ana Ruiz", *ETHICS)
        self.amended()
        out = self.ok("status")
        self.assertFalse(out["ethics"]["current"])
        self.assertIn("ETHICS_STALE", [warning["code"] for warning in out["warnings"]])
        self.ok("ethics", "record", "--by", "Ana Ruiz", *ETHICS[:3], "CEI-2026-041-A1", *ETHICS[4:])
        out = self.ok("status")
        self.assertTrue(out["ethics"]["current"])
        self.assertNotIn("ETHICS_STALE", [warning["code"] for warning in out["warnings"]])
        self.assertEqual(len(self.record("ethics")["history"]), 2)

    def test_the_same_approval_rebound_after_an_amendment_is_not_unchanged(self) -> None:
        self.approved()
        self.ok("ethics", "record", "--by", "Ana Ruiz", *ETHICS)
        self.amended()
        self.ok("ethics", "record", "--by", "Ana Ruiz", *ETHICS)
        self.assertEqual(self.record("ethics")["history"][-1]["protocol_sha256"], self.lock()["sha256"])


class RegistrationTests(StudyWorkspace):
    def test_registration_is_refused_before_the_protocol_is_approved(self) -> None:
        self.revision(1)
        self.refused("PROTOCOL_NOT_APPROVED", "registration", "record", "--by", "Ana Ruiz", *REGISTRY)

    def test_prospective_registration_is_bound_to_the_lock(self) -> None:
        self.approved()
        out = self.ok("registration", "record", "--by", "Ana Ruiz", *REGISTRY, "--first-enrolment", "2026-05-10")
        [entry] = self.record("registration")["history"]
        self.assertEqual({key: entry[key] for key in ("status", "registry", "id", "date", "first_enrolment",
                                                       "retrospective", "protocol_sha256")},
                         {"status": "registered", "registry": "ClinicalTrials.gov", "id": "NCT07000001",
                          "date": "2026-04-01", "first_enrolment": "2026-05-10", "retrospective": False,
                          "protocol_sha256": self.lock()["sha256"]})
        self.assertEqual(out["registration"]["warnings"], [])

    def test_a_registration_after_the_first_enrolment_is_retrospective(self) -> None:
        self.approved()
        out = self.ok("registration", "record", "--by", "Ana Ruiz", *REGISTRY, "--first-enrolment", "2026-03-15")
        self.assertTrue(self.record("registration")["history"][0]["retrospective"])
        self.assertIn("REGISTRATION_RETROSPECTIVE", [w["code"] for w in out["registration"]["warnings"]])
        self.assertIn("REGISTRATION_RETROSPECTIVE", [w["code"] for w in self.ok("status")["warnings"]])

    def test_registered_on_the_day_of_first_enrolment_is_prospective(self) -> None:
        self.approved()
        self.ok("registration", "record", "--by", "Ana Ruiz", *REGISTRY, "--first-enrolment", "2026-04-01")
        self.assertFalse(self.record("registration")["history"][0]["retrospective"])

    def test_without_a_first_enrolment_date_the_timing_is_unknown(self) -> None:
        self.approved()
        out = self.ok("registration", "record", "--by", "Ana Ruiz", *REGISTRY)
        entry = self.record("registration")["history"][0]
        self.assertEqual((entry["first_enrolment"], entry["retrospective"]), (None, None))
        self.assertIn("FIRST_ENROLMENT_UNKNOWN", [w["code"] for w in out["registration"]["warnings"]])

    def test_registration_refusals(self) -> None:
        self.approved()
        self.refused("APPROVER_MISSING", "registration", "record", *REGISTRY)
        self.refused("FIELD_MISSING", "registration", "record", "--by", "Ana Ruiz", *REGISTRY[:4])
        self.refused("FIELDS_CONFLICT", "registration", "record", "--by", "Ana Ruiz", "--not-applicable",
                     "--reason", "x", "--first-enrolment", "2026-03-01")
        self.refused("REASON_MISSING", "registration", "record", "--by", "Ana Ruiz", "--not-applicable")
        self.refused("DATE_INVALID", "registration", "record", "--by", "Ana Ruiz", *REGISTRY,
                     "--first-enrolment", "2026-13-01")
        self.assertFalse((self.root / "study" / "registration.json").exists())
        self.ok("registration", "record", "--by", "Ana Ruiz", *REGISTRY)
        self.refused("RECORD_UNCHANGED", "registration", "record", "--by", "Ana Ruiz", *REGISTRY)

    def test_not_applicable_registration(self) -> None:
        self.approved()
        self.ok("registration", "record", "--by", "Ana Ruiz", "--not-applicable", "--reason",
                "cross-sectional survey; no registry applies")
        entry = self.record("registration")["history"][0]
        self.assertEqual((entry["status"], entry["reason"], entry["retrospective"]),
                         ("not-applicable", "cross-sectional survey; no registry applies", None))
        self.assertEqual(self.ok("status")["registration"]["warnings"], [])

    def test_an_amendment_marks_the_registration_stale(self) -> None:
        self.approved()
        self.ok("registration", "record", "--by", "Ana Ruiz", *REGISTRY, "--first-enrolment", "2026-05-10")
        self.amended()
        out = self.ok("status")
        self.assertFalse(out["registration"]["current"])
        self.assertIn("REGISTRATION_STALE", [w["code"] for w in out["warnings"]])


class StatusTests(StudyWorkspace):
    def test_status_summarises_the_three_records(self) -> None:
        out = self.ok("status")
        self.assertEqual((out["protocol"]["state"], out["ethics"], out["registration"]), ("absent", None, None))
        self.assertEqual([w["code"] for w in out["warnings"]], ["PROTOCOL_NOT_APPROVED"])
        self.approved()
        codes = [w["code"] for w in self.ok("status")["warnings"]]
        self.assertEqual(codes, ["ETHICS_ABSENT", "REGISTRATION_ABSENT"])
        self.ok("ethics", "record", "--by", "Ana Ruiz", *ETHICS)
        self.ok("registration", "record", "--by", "Ana Ruiz", *REGISTRY, "--first-enrolment", "2026-05-10")
        out = self.ok("status")
        self.assertEqual(out["warnings"], [])
        self.assertTrue(out["ethics"]["current"] and out["registration"]["current"])
        self.revision(2)
        self.assertIn("PROTOCOL_CHANGED", [w["code"] for w in self.ok("status")["warnings"]])

    def test_a_corrupt_record_is_reported_not_raised(self) -> None:
        self.approved()
        (self.root / "study" / "ethics.json").write_text("[]", encoding="utf-8")
        out = self.ok("status")
        self.assertEqual(out["ethics"]["state"], "corrupt")
        self.assertIn("ETHICS_CORRUPT", [w["code"] for w in out["warnings"]])
        self.refused("ETHICS_CORRUPT", "ethics", "record", "--by", "Ana Ruiz", *ETHICS)


class ImportableReadersTests(StudyWorkspace):
    def setUp(self) -> None:
        super().setUp()
        if str(REPO) not in sys.path:
            sys.path.insert(0, str(REPO))
        from skills._core.empirical import records
        self.records = records

    def tree(self) -> list[tuple[str, bytes]]:
        return sorted((str(p.relative_to(self.root)), p.read_bytes() if p.is_file() else b"")
                      for p in self.root.rglob("*"))

    def test_the_readers_match_the_cli_and_write_nothing(self) -> None:
        self.assertEqual(self.records.protocol_state(self.root)["state"], "absent")
        self.assertIsNone(self.records.gate_state(self.root, "ethics"))
        self.approved()
        self.ok("ethics", "record", "--by", "Ana Ruiz", *ETHICS)
        self.amended()
        before = self.tree()
        status = self.ok("status")
        self.assertEqual(self.records.protocol_state(self.root), status["protocol"])
        self.assertEqual(self.records.gate_state(self.root, "ethics"), status["ethics"])
        self.assertIsNone(self.records.gate_state(self.root, "registration"))
        self.assertEqual(self.records.study_status(self.root), {k: v for k, v in status.items() if k != "ok"})
        self.assertEqual(self.tree(), before)
        with self.assertRaises(ValueError):
            self.records.gate_state(self.root, "consent")


if __name__ == "__main__":
    unittest.main()
