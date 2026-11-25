"""The Study tab's allocation section (paper-type-lines S8, T8-B5, decision J2).

An `experiment-intervention` workspace answers an `allocation` section of
`GET /api/study`: the operator's allocation record (gate G-ALLOCATION) read
only through the side-effect-free `records.allocation_state` -- its state
(absent, current, stale, corrupt), method, block size, strata, concealment,
who recorded it and when, the list's path, row count and short sha256, the
protocol revision it is bound to, and the stale reasons. The allocation list
itself is the operator's and stays concealed: no value of it ever reaches the
view. A corrupt record turns the section into its corrupt state, never a
failed `/api/study`. A workspace of another line shows the section only once an
allocation record exists. Every record is written by the real `study_cli.py`.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from skills._core.command_center import server, study_view
from skills._core.empirical import records
from tests.test_study_view import STUDY, cli, lock, revision, workspace, write

KIND = "experiment-intervention"
#: Recognizable values of the operator's allocation list: none may reach the view.
TOKENS = ("ZEBRA-ARM-7731", "QUOKKA-ARM-4402", "P-0193")
SEQUENCE = "participant,arm\nP-0193,ZEBRA-ARM-7731\nP-0194,QUOKKA-ARM-4402\nP-0195,ZEBRA-ARM-7731\n"
LIST = "allocation/sequence.csv"
CONCEALMENT = "Sealed <opaque> envelopes held by the pharmacy"


def allocate(root: Path, *extra: str, method: str = "stratified") -> None:
    if not (root / LIST).exists():
        write(root, LIST, SEQUENCE)
    args = ["allocation", "record", "--by", "Ana Ruiz", "--file", LIST, "--method", method,
            "--concealment", CONCEALMENT]
    if method == "stratified":
        args += ["--block-size", "4", "--strata", "site, sex"]
    cli(STUDY, root, *args, *extra)


class AllocationCase(unittest.TestCase):
    def get(self, root: Path, route: str = "/api/study") -> dict:
        response = TestClient(server.create_app(root)).get(route)
        self.assertEqual(response.status_code, 200, response.text)
        text = response.text
        for token in TOKENS:
            self.assertNotIn(token, text, "the allocation sequence leaked into the view")
        return response.json()

    def section(self, view: dict) -> dict:
        self.assertIn("allocation", view)
        self.assertTrue(view["allocation"]["available"], view["allocation"])
        return view["allocation"]

    def recorded(self) -> Path:
        root = workspace(self, KIND)
        lock(root)
        allocate(root)
        return root


class SectionTests(AllocationCase):
    def test_an_intervention_workspace_answers_the_section_even_absent(self) -> None:
        view = self.get(workspace(self, KIND))
        self.assertEqual(view["paper_kind"], KIND)
        self.assertEqual(view["warnings"], [])
        self.assertEqual(self.section(view), {"available": True, "gate": "G-ALLOCATION", "state": "absent",
                                              "path": "study/allocation.json"})
        for name in study_view.SECTIONS:
            self.assertIn(name, view)

    def test_the_record_and_its_current_state(self) -> None:
        root = self.recorded()
        section = self.section(self.get(root))
        self.assertTrue(section.pop("at"))
        digest = records.sha256(root / LIST)
        self.assertEqual(section, {
            "available": True, "gate": "G-ALLOCATION", "state": "current", "path": "study/allocation.json",
            "current": True, "reasons": [], "method": "stratified", "block_size": 4, "strata": "site, sex",
            "concealment": CONCEALMENT, "note": None, "by": "Ana Ruiz", "file": LIST, "rows": 4,
            "sha256": digest[:12], "protocol_revision": "protocol/study-protocol-walking-v01.md", "records": 1,
            "warnings": []})

    def test_a_note_and_a_second_record(self) -> None:
        root = self.recorded()
        allocate(root, "--note", "Pharmacy <holds> the key", method="simple")
        section = self.section(self.get(root))
        self.assertEqual((section["method"], section["block_size"], section["strata"], section["note"],
                          section["records"]), ("simple", None, None, "Pharmacy <holds> the key", 2))

    def test_a_changed_list_makes_it_stale(self) -> None:
        root = self.recorded()
        write(root, LIST, SEQUENCE + "P-0196,QUOKKA-ARM-4402\n")
        section = self.section(self.get(root))
        self.assertEqual((section["state"], section["current"], section["reasons"]),
                         ("stale", False, ["file-changed"]))
        self.assertEqual([w["code"] for w in section["warnings"]], ["ALLOCATION_STALE"])

    def test_a_removed_list_makes_it_stale(self) -> None:
        root = self.recorded()
        (root / LIST).unlink()
        self.assertEqual(self.section(self.get(root))["reasons"], ["file-missing"])

    def test_an_unreadable_list_makes_it_stale(self) -> None:
        root = self.recorded()

        real = records.sha256

        def unreadable(path):
            if Path(path).name == "sequence.csv":
                raise OSError("permission denied")
            return real(path)

        with mock.patch.object(records, "sha256", unreadable):
            self.assertEqual(self.section(self.get(root))["reasons"], ["file-unreadable"])

    def test_an_amendment_makes_it_stale(self) -> None:
        root = self.recorded()
        revision(root, 2, "\nAmended eligibility.\n")
        cli(STUDY, root, "protocol", "amend", "--by", "Ana Ruiz", "--reason", "widened the age range")
        section = self.section(self.get(root))
        self.assertEqual((section["state"], section["reasons"], section["protocol_revision"]),
                         ("stale", ["protocol-amended"], "protocol/study-protocol-walking-v01.md"))

    def test_an_unamended_protocol_change_makes_it_stale(self) -> None:
        root = self.recorded()
        revision(root, 2)
        self.assertEqual(self.section(self.get(root))["reasons"], ["protocol-changed"])

    def test_a_corrupt_record_never_breaks_the_view(self) -> None:
        root = workspace(self, KIND)
        write(root, "study/allocation.json", "{not json")
        view = self.get(root)
        section = self.section(view)
        self.assertEqual((section["state"], section["code"]), ("corrupt", "ALLOCATION_CORRUPT"))
        self.assertTrue(section["message"])
        self.assertTrue(view["protocol"]["available"])
        self.assertTrue(view["ethics"]["available"])

    def test_the_state_is_read_through_allocation_state(self) -> None:
        root = self.recorded()
        calls = []

        def spy(where):
            calls.append(Path(where))
            return {"state": "stale", "current": False, "reasons": ["file-missing"], "method": "block",
                    "block_size": 6, "file": "x.csv", "sha256": "f" * 64, "records": 3}

        with mock.patch.object(records, "allocation_state", spy):
            section = self.section(self.get(root))
        self.assertEqual(calls, [root])
        self.assertEqual((section["state"], section["method"], section["block_size"], section["sha256"],
                          section["records"]), ("stale", "block", 6, "ffffffffffff", 3))

    def test_the_list_is_never_opened_by_the_view(self) -> None:
        root = self.recorded()
        opened = []
        real = Path.read_bytes

        def watch(path):
            if path.name == "sequence.csv":
                opened.append(path)
            return real(path)

        with mock.patch.object(records, "allocation_state", lambda where: {"state": "absent"}), \
                mock.patch.object(Path, "read_bytes", watch):
            self.section(self.get(root))
        self.assertEqual(opened, [])

    def test_another_line_shows_the_section_only_with_a_record(self) -> None:
        root = workspace(self)
        lock(root)
        self.assertNotIn("allocation", self.get(root))
        allocate(root)
        self.assertEqual(self.section(self.get(root))["state"], "current")

    def test_an_absent_reader_turns_the_section_unavailable(self) -> None:
        root = workspace(self, KIND)
        real = study_view._module

        def without_records(name):
            return (None, "records did not load") if name == "records" else real(name)

        with mock.patch.object(study_view, "_module", without_records):
            view = TestClient(server.create_app(root)).get("/api/study").json()
        self.assertEqual((view["allocation"]["available"], view["allocation"]["code"]),
                         (False, study_view.MODULE_UNAVAILABLE))

    def test_the_view_carries_no_server_label_to_translate(self) -> None:
        root = self.recorded()
        self.assertEqual(self.get(root, "/api/study?lang=es"), self.get(root))

    def test_the_view_holds_no_sequence_value_in_any_state(self) -> None:
        root = self.recorded()
        write(root, LIST, SEQUENCE + "P-0197,ZEBRA-ARM-7731\n")
        blob = json.dumps(self.get(root))
        for token in TOKENS:
            self.assertNotIn(token, blob)

    def test_the_section_belongs_to_the_intervention_line(self) -> None:
        self.assertEqual(study_view.ALLOCATION_KINDS, (KIND,))
        self.assertIn(KIND, study_view.EMPIRICAL_KINDS)


if __name__ == "__main__":
    unittest.main()
