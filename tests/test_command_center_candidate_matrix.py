"""The Candidate Matrix shows the pool the plausibility phase wrote.

`/plausibility` writes `sota-pool/candidates.json` as an object -- the idea, the
families, the candidates, the excluded ones, the pool's note and what it still
owes -- and `check_atlas.py` reads either that object or a bare list. The
dashboard read only the list: `/api/candidates` answered 500 on a real pool and
the matrix stayed empty. Every reader now shares one normalizer, the matrix
shows only what the pool records (no invented date, resolver or verdict), and
the Plausibility phase links to the matrix.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from skills._core.command_center import phase_actions, server

STATIC = Path(server.__file__).resolve().parent / "static"
PAGE = (STATIC / "index.html").read_text(encoding="utf-8")
CONSOLE = (STATIC / "phase-console.js").read_text(encoding="utf-8")


def candidate(identifier: str, family: str, year: int, *, anchor: bool = False) -> dict:
    return {"identifier": identifier, "resolver": "openalex", "title": f"Paper {identifier}",
            "authors": ["A. Author"], "year": year, "venue": "Venue", "abstract": "An abstract.",
            "source_url": f"https://doi.org/{identifier}", "retrieved": "2026-10-21",
            "family": family, "family_id": "F1", "family_provenance": "grouped", "anchor": anchor}


OBJECT_POOL = {
    "idea_verbatim": "The idea.", "interpretation": "Reading.", "retrieved": "2026-10-21",
    "families": [{"id": "F1", "name": "Kernels", "provenance": "grouped", "members": ["10.1/a"]}],
    "candidates": [candidate("10.1/a", "Kernels", 2021, anchor=True),
                   candidate("10.1/b", "Networks", 2025)],
    "excluded": [{"identifier": "10.1/c", "title": "No abstract", "reason": "abstract null"}],
    "plausibility_note": "Two families are well covered.",
    "owed": ["Pool short: 2 resolved candidates, not 25."],
}


class PoolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="candidates-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        (self.root / "sota-pool").mkdir()
        self.client = TestClient(server.create_app(self.root, history_store=None))

    def write(self, pool: object) -> None:
        (self.root / "sota-pool" / "candidates.json").write_text(json.dumps(pool), encoding="utf-8")

    def test_the_plausibility_object_is_served(self) -> None:
        self.write(OBJECT_POOL)
        response = self.client.get("/api/candidates")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["count"], 2)
        self.assertEqual([c["identifier"] for c in body["candidates"]], ["10.1/a", "10.1/b"])
        self.assertEqual(body["families"], ["Kernels", "Networks"])
        self.assertEqual(body["plausibility_note"], "Two families are well covered.")
        self.assertEqual(body["owed"], ["Pool short: 2 resolved candidates, not 25."])
        self.assertEqual(body["excluded"], 1)
        self.assertEqual(body["retrieved"], "2026-10-21")

    def test_a_bare_list_is_still_served(self) -> None:
        self.write([candidate("10.1/a", "Kernels", 2021)])
        body = self.client.get("/api/candidates").json()
        self.assertEqual((body["count"], body["families"]), (1, ["Kernels"]))
        self.assertEqual(body["owed"], [])

    def test_no_pool_is_an_empty_matrix(self) -> None:
        body = self.client.get("/api/candidates").json()
        self.assertEqual((body["count"], body["candidates"], body["families"]), (0, [], []))

    def test_a_malformed_pool_says_so_without_inventing_candidates(self) -> None:
        self.write({"candidates": "not a list"})
        response = self.client.get("/api/candidates")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 0)

    def test_the_server_rendered_view_lists_the_object_pool(self) -> None:
        self.write(OBJECT_POOL)
        page = self.client.get("/api/atlas/candidates/view").text
        self.assertIn("Paper 10.1/a", page)
        self.assertIn("Networks", page)

    def test_the_phase_counts_the_object_pool(self) -> None:
        self.write(OBJECT_POOL)
        self.assertEqual(server._candidate_count(self.root), 2)


class MatrixPageTests(unittest.TestCase):
    def matrix_script(self) -> str:
        start = PAGE.index("async function loadCandidatesMatrix()")
        return PAGE[start:PAGE.index("function toggleAbstractRow", start)]

    def test_the_matrix_shows_only_what_the_pool_records(self) -> None:
        script = self.matrix_script()
        for invented in ("'2026-10-14'", "|| 'OpenAlex'", "|| 2022", "candidates.defaultPlausibility",
                         "candidates.defaultVenue"):
            with self.subTest(invented=invented):
                self.assertNotIn(invented, script)
        self.assertIn("c.retrieved", script)
        self.assertIn("c.anchor", script)

    def test_the_stats_are_computed_from_the_pool(self) -> None:
        script = self.matrix_script()
        self.assertIn("candStatWindow", script)
        self.assertIn("candStatPlausible", script)
        self.assertIn('id="candidatePoolNote"', PAGE)
        self.assertNotIn("Q1/Q2", (STATIC / "i18n" / "en.js").read_text(encoding="utf-8"))


class PhaseLinkTests(unittest.TestCase):
    def test_the_plausibility_phase_opens_the_candidate_matrix(self) -> None:
        actions = phase_actions.ACTIONS["plausibility"]["actions"]
        matrix = [a for a in actions if a["kind"] == "redirect" and a.get("section") == "papers"]
        self.assertEqual(len(matrix), 1)
        self.assertEqual(matrix[0]["tab"], "atlas")

    def test_the_console_switches_the_graph_panel_to_that_view(self) -> None:
        start = CONSOLE.index("function redirect(a)")
        body = CONSOLE[start:CONSOLE.index("\n  }\n", start)]
        self.assertIn("a.tab === 'atlas'", body)
        self.assertIn("window.switchGraph", body)


if __name__ == "__main__":
    unittest.main()
