"""The Study tab's deposit section (paper-type-lines S8, T8-B4, decision H6).

A `data-resource` workspace answers a `deposit` section of `GET /api/study`:
every dataset of the resource (each registry entry but a toy set) with its
deposit record (repository, identifier and scheme, licence, landing page,
version, date, who recorded it) and whether it is current or stale, with the
reasons, read only through `datasets_cli.deposit_state` (never re-parsed). A
workspace of another line shows the section only once a deposit is recorded.
The reporting section names `datasheets` through `registry.checklist_for`.
Every record is written by the real `datasets_cli.py`.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from skills._core.command_center import server, study_view
from tests.test_study_view import PAPER_TYPE, cli, workspace, write

KIND = "data-resource"
DOI = "10.5281/zenodo.7654321"
CSV = "id,score\n1,3\n2,5\n"


def datasets_cli(root: Path) -> Path:
    return root / "skills" / "datasets" / "scripts" / "datasets_cli.py"


def own(root: Path, slug: str = "notes") -> None:
    write(root, f"data/{slug}.csv", CSV)
    cli(datasets_cli(root), root, "own", "--slug", slug, "--by", "Ana Ruiz", "--statement", "Open <research> use",
        root_first=True)
    cli(datasets_cli(root), root, "qc", "--slug", slug, "--file", f"data/{slug}.csv", root_first=True)


def deposit(root: Path, slug: str = "notes", *extra: str) -> None:
    cli(datasets_cli(root), root, "deposit", "--slug", slug, "--repository", "Zenodo <EU>", "--identifier", DOI,
        "--license", "CC-BY-4.0", "--by", "Ana Ruiz", *extra, root_first=True)


class DepositCase(unittest.TestCase):
    def get(self, root: Path, route: str = "/api/study") -> dict:
        response = TestClient(server.create_app(root)).get(route)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def section(self, view: dict) -> dict:
        self.assertIn("deposit", view)
        self.assertTrue(view["deposit"]["available"], view["deposit"])
        return view["deposit"]


class SectionTests(DepositCase):
    def test_a_data_resource_workspace_answers_the_section_even_empty(self) -> None:
        view = self.get(workspace(self, KIND))
        self.assertEqual(view["paper_kind"], KIND)
        self.assertEqual(view["warnings"], [])
        self.assertEqual(self.section(view)["datasets"], [])
        for name in study_view.SECTIONS:
            self.assertIn(name, view)
        self.assertNotIn("instruments", view)

    def test_the_deposit_record_and_its_state(self) -> None:
        root = workspace(self, KIND)
        own(root)
        deposit(root, "notes", "--url", "https://zenodo.org/records/7654321", "--version", "v1", "--date",
                "2026-11-20")
        rows = self.section(self.get(root))["datasets"]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual({key: row[key] for key in ("slug", "role", "recorded", "current", "stale")},
                         {"slug": "notes", "role": "own", "recorded": True, "current": True, "stale": []})
        self.assertEqual({key: row[key] for key in ("repository", "identifier", "scheme", "license", "url",
                                                    "version", "date", "by")},
                         {"repository": "Zenodo <EU>", "identifier": DOI, "scheme": "doi", "license": "CC-BY-4.0",
                          "url": "https://zenodo.org/records/7654321", "version": "v1", "date": "2026-11-20",
                          "by": "Ana Ruiz"})
        self.assertTrue(row["recorded_on"])
        self.assertEqual(row["files"], ["data/notes.csv"])
        self.assertEqual(row["revisions"], 0)
        deposit(root, "notes", "--version", "v2")
        self.assertEqual(self.section(self.get(root))["datasets"][0]["revisions"], 1)

    def test_a_changed_file_makes_the_deposit_stale_and_says_why(self) -> None:
        root = workspace(self, KIND)
        own(root)
        deposit(root)
        write(root, "data/notes.csv", CSV + "3,4\n")
        row = self.section(self.get(root))["datasets"][0]
        self.assertEqual((row["recorded"], row["current"]), (True, False))
        self.assertEqual(row["stale"], [{"reason": "file-changed", "file": "data/notes.csv"}])

    def test_a_dataset_without_a_deposit_and_a_toy_set(self) -> None:
        root = workspace(self, KIND)
        own(root)
        cli(datasets_cli(root), root, "license", "--slug", "toy", "--source-license", "CC0 1.0", "--role", "toy",
            root_first=True)
        rows = self.section(self.get(root))["datasets"]
        self.assertEqual([row["slug"] for row in rows], ["notes"])
        self.assertEqual((rows[0]["recorded"], rows[0]["current"], rows[0]["repository"]), (False, False, None))

    def test_the_state_is_read_through_deposit_state(self) -> None:
        root = workspace(self, KIND)
        own(root)
        deposit(root)
        module, _why = study_view.load_datasets_cli(root)
        calls = []

        def spy(where, entry):
            calls.append(entry["slug"] if isinstance(entry, dict) else entry)
            return {"recorded": True, "current": False, "stale": [{"reason": "file-missing", "file": "x.csv"}],
                    "deposit": {"repository": "Spy", "identifier": "10.1/spy", "scheme": "doi"}}

        with mock.patch.object(module, "deposit_state", spy):
            row = self.section(self.get(root))["datasets"][0]
        self.assertEqual(calls, ["notes"])
        self.assertEqual((row["repository"], row["identifier"], row["current"]), ("Spy", "10.1/spy", False))
        self.assertEqual(row["stale"], [{"reason": "file-missing", "file": "x.csv"}])

    def test_another_line_shows_the_section_only_with_a_deposit(self) -> None:
        root = workspace(self)
        own(root)
        self.assertNotIn("deposit", self.get(root))
        deposit(root)
        self.assertTrue(self.section(self.get(root))["datasets"][0]["current"])

    def test_an_unreadable_registry_turns_the_section_unavailable(self) -> None:
        root = workspace(self, KIND)
        write(root, "datasets/registry.json", "{not json")
        view = self.get(root)
        self.assertFalse(view["deposit"]["available"])
        self.assertTrue(view["protocol"]["available"])

    def test_the_view_carries_no_server_label_to_translate(self) -> None:
        root = workspace(self, KIND)
        own(root)
        deposit(root)
        self.assertEqual(self.get(root, "/api/study?lang=es"), self.get(root))


class ReportingTests(DepositCase):
    def test_the_type_names_datasheets(self) -> None:
        root = workspace(self, KIND)
        idea = write(root, "idea.txt", "We release a corpus of annotated clinical notes for triage.\n"
                                       "We collected, documented and deposited the notes.\n")
        cli(PAPER_TYPE, root, "accept", "--by", "Ana Ruiz", "--idea-file", str(idea))
        cli(PAPER_TYPE, root, "agree", "--type", KIND, "--by", "Ana Ruiz")
        reporting = self.get(root)["reporting"]
        self.assertEqual((reporting["type"], reporting["variant"], reporting["guideline"], reporting["code"]),
                         (KIND, None, "datasheets", None))
        self.assertNotIn("additional_guidelines", reporting)
        checklist = self.get(root, "/api/study/checklist")
        self.assertEqual((checklist["guideline"]["id"], len(checklist["items"])), ("datasheets", 50))

    def test_the_deposit_section_belongs_to_the_data_resource_line(self) -> None:
        self.assertEqual(study_view.DEPOSIT_KINDS, (KIND,))
        self.assertIn(KIND, study_view.EMPIRICAL_KINDS)


if __name__ == "__main__":
    unittest.main()
