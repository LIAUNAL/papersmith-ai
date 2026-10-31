"""The dashboard's journal finder and venue endpoints.

`GET /api/journals`, `POST /api/journals/search`, `POST /api/journals/sjr` drive
`skills/journal-finder/scripts/journal_cli.py` (a stub script stands in for the
search, which would reach the network; the real CLI serves `status` and
`sjr-import`). The `/api/venues` family wraps `paper_venue` on the scratch
repositories `tests.test_paper_venue.VenueCase` builds, and the venue compile
runs the same pdflatex/bibtex sequence as the canonical one with the toolchain
mocked.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from skills._core.command_center import server
from tests.test_paper_venue import PLAN_TEXT, VenueCase, canonical_tex, sha, tree_state

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "tests" / "fixtures" / "command_center_journals"
SJR_FIXTURE = REPO / "tests" / "fixtures" / "journal_finder" / "scimagojr-2019.csv"
STUB = FIXTURES / "stub_journal_cli.py"
SAME = {"Origin": "http://testserver"}
OTHER = {"Origin": "http://evil.example"}


class JournalCase(unittest.TestCase):
    """A scratch workspace, an isolated SJR cache and a client."""

    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.tmp = Path(holder.name).resolve()
        self.root = self.tmp / "ws"
        (self.root / "paper").mkdir(parents=True)
        self.sjr_dir = self.tmp / "sjr"
        patcher = mock.patch.dict(os.environ, {"PAPERSMITH_SJR_DIR": str(self.sjr_dir)})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = TestClient(server.create_app(self.root))
        self.argv_log = self.tmp / "argv.log"

    def candidates(self) -> Path:
        target = self.root / "paper" / "journal-candidates.json"
        target.write_bytes((FIXTURES / "journal-candidates.json").read_bytes())
        return target

    def stub(self, response: dict | str, exit_code: int = 0, sleep: float = 0.0) -> None:
        """Point the dashboard at the stub CLI, which answers `response`."""
        path = self.tmp / "response.json"
        path.write_text(response if isinstance(response, str) else json.dumps(response), encoding="utf-8")
        patches = [
            mock.patch.object(server, "JOURNAL_CLI", STUB),
            mock.patch.dict(os.environ, {
                "STUB_JOURNAL_RESPONSE": str(path), "STUB_JOURNAL_EXIT": str(exit_code),
                "STUB_JOURNAL_ARGV": str(self.argv_log), "STUB_JOURNAL_SLEEP": str(sleep)}),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def calls(self) -> list[list[str]]:
        if not self.argv_log.is_file():
            return []
        return [json.loads(line) for line in self.argv_log.read_text(encoding="utf-8").splitlines()]


# --------------------------------------------------------------------------
# GET /api/journals
# --------------------------------------------------------------------------
class JournalsStateTests(JournalCase):
    def test_an_empty_workspace_answers_no_candidates_and_no_sjr(self) -> None:
        body = self.client.get("/api/journals").json()
        self.assertTrue(body["ok"])
        self.assertIsNone(body["candidates"])
        self.assertIsNone(body["sjr"])
        self.assertEqual(body["sjr_download_url"], "https://www.scimagojr.com/journalrank.php")
        self.assertFalse(body["notes_md"])

    def test_the_candidates_file_is_returned_with_every_field(self) -> None:
        self.candidates()
        body = self.client.get("/api/journals").json()
        names = [c["display_name"] for c in body["candidates"]["candidates"]]
        self.assertEqual(names, ["Open Signal Processing", "Cited Only Journal", "Obscure Quarterly",
                                 "Neural Fixtures Letters", "Biomedical Fixture Reports"])
        flagged = body["candidates"]["candidates"][3]
        self.assertEqual(flagged["fit"]["cited_in_paper"], 0.5)
        self.assertEqual(flagged["flags"], ["no-application-evidence"])
        self.assertEqual(flagged["facets"]["gate"], 0.5)
        calls = body["candidates"]["api_calls"]
        self.assertEqual((calls["made"], calls["cached"]), (26, 0))
        self.assertEqual(calls["budget"]["state"], "ok")

    def test_the_sjr_state_comes_from_the_imported_file(self) -> None:
        code = subprocess.run([sys.executable, str(server.JOURNAL_CLI), "sjr-import", "--file",
                               str(SJR_FIXTURE)], capture_output=True, text=True, check=False)
        self.assertEqual(code.returncode, 0, code.stdout)
        body = self.client.get("/api/journals").json()
        self.assertEqual(body["sjr"]["year"], 2019)
        self.assertTrue(body["sjr"]["file"].endswith("scimagojr-2019.csv"))

    def test_the_agents_notes_file_is_flagged_when_present(self) -> None:
        (self.root / "paper" / "journal-candidates.md").write_text("# notes\n", encoding="utf-8")
        self.assertTrue(self.client.get("/api/journals").json()["notes_md"])

    def test_an_unreadable_candidates_file_is_reported_not_raised(self) -> None:
        (self.root / "paper" / "journal-candidates.json").write_text("{not json", encoding="utf-8")
        response = self.client.get("/api/journals")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIsNone(body["candidates"])
        self.assertEqual(body["candidates_error"]["code"], "CANDIDATES_UNREADABLE")

    def test_an_oversized_candidates_file_is_not_read(self) -> None:
        (self.root / "paper" / "journal-candidates.json").write_text("{}", encoding="utf-8")
        with mock.patch.object(server, "JOURNALS_FILE_MAX_BYTES", 1):
            body = self.client.get("/api/journals").json()
        self.assertIsNone(body["candidates"])
        self.assertEqual(body["candidates_error"]["code"], "CANDIDATES_UNREADABLE")

    def test_a_candidates_symlink_out_of_the_workspace_is_not_followed(self) -> None:
        outside = self.tmp / "outside.json"
        outside.write_text(json.dumps({"candidates": [{"display_name": "Leak"}]}), encoding="utf-8")
        (self.root / "paper" / "journal-candidates.json").symlink_to(outside)
        body = self.client.get("/api/journals").json()
        self.assertIsNone(body["candidates"])


# --------------------------------------------------------------------------
# POST /api/journals/search
# --------------------------------------------------------------------------
SEARCH_OK = {"ok": True, "out": "paper/journal-candidates.json", "candidates": [], "quartiles": ["Q1", "Q2"]}


class JournalSearchTests(JournalCase):
    def post(self, body, headers=SAME):
        return self.client.post("/api/journals/search", json=body, headers=headers)

    def test_a_cross_origin_post_is_refused_and_nothing_runs(self) -> None:
        self.stub(SEARCH_OK)
        self.assertEqual(self.post({"quartiles": "Q1"}, OTHER).status_code, 403)
        self.assertEqual(self.calls(), [])

    def test_an_invalid_range_is_422_without_running_the_cli(self) -> None:
        self.stub(SEARCH_OK)
        for quartiles in ("Q3-Q1", "Q5", "", "Q1-", "Q1-Q2-Q3", 7, None, "Q1,Q2"):
            with self.subTest(quartiles=quartiles):
                response = self.post({"quartiles": quartiles})
                self.assertEqual(response.status_code, 422)
                body = response.json()
                self.assertFalse(body["ok"])
                self.assertEqual(body["error"], "QUARTILE_RANGE_INVALID")
        self.assertEqual(self.calls(), [])

    def test_invalid_filters_are_422(self) -> None:
        self.stub(SEARCH_OK)
        for patch in ({"limit": 0}, {"limit": 51}, {"limit": "x"}, {"max_apc": -1}, {"max_apc": "lots"},
                      {"max_review_days": 0}, {"max_review_days": 1.5}, {"oa_only": "yes"}, {"no_cache": "yes"}, {"no_cache": 1}):
            with self.subTest(patch=patch):
                response = self.post({"quartiles": "Q1", **patch})
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json()["error"], "FILTER_INVALID")
        self.assertEqual(self.calls(), [])

    def test_a_body_that_is_not_an_object_is_422(self) -> None:
        self.stub(SEARCH_OK)
        response = self.client.post("/api/journals/search", content=b"[1]", headers=SAME)
        self.assertEqual(response.status_code, 422)
        response = self.client.post("/api/journals/search", content=b"not json", headers=SAME)
        self.assertEqual(response.status_code, 422)

    def test_a_valid_search_passes_the_filters_and_returns_the_cli_json(self) -> None:
        self.stub(SEARCH_OK)
        response = self.post({"quartiles": "q1-q2", "oa_only": True, "max_apc": 2000,
                              "max_review_days": 180, "limit": 10})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), SEARCH_OK)
        (argv,) = self.calls()
        self.assertEqual(argv, ["search", "--workspace", str(self.root), "--quartiles", "Q1-Q2",
                                "--oa-only", "--max-apc", "2000", "--max-review-days", "180",
                                "--limit", "10"])

    def test_force_refresh_passes_no_cache_through(self) -> None:
        self.stub(SEARCH_OK)
        self.assertEqual(self.post({"quartiles": "Q1", "no_cache": True, "limit": 5}).status_code, 200)
        self.assertEqual(self.post({"quartiles": "Q1", "no_cache": False}).status_code, 200)
        forced, plain = self.calls()
        self.assertEqual(forced, ["search", "--workspace", str(self.root), "--quartiles", "Q1",
                                  "--limit", "5", "--no-cache"])
        self.assertNotIn("--no-cache", plain)

    def test_optional_filters_are_left_out_when_absent(self) -> None:
        self.stub(SEARCH_OK)
        self.assertEqual(self.post({"quartiles": "Q3"}).status_code, 200)
        (argv,) = self.calls()
        self.assertEqual(argv, ["search", "--workspace", str(self.root), "--quartiles", "Q3"])

    def test_a_cli_refusal_keeps_its_shape_and_maps_to_a_status(self) -> None:
        for code, status in (("PAPER_ABSENT", 409), ("NETWORK_UNAVAILABLE", 502),
                             ("QUARTILE_RANGE_INVALID", 422), ("WORKSPACE_ABSENT", 404)):
            with self.subTest(code=code):
                self.stub({"ok": False, "error": code, "message": f"{code} happened"}, exit_code=2)
                response = self.post({"quartiles": "Q1"})
                self.assertEqual(response.status_code, status)
                self.assertEqual(response.json(), {"ok": False, "error": code, "message": f"{code} happened"})

    def test_a_cli_that_prints_no_json_is_a_typed_502(self) -> None:
        self.stub("Traceback (most recent call last)", exit_code=1)
        response = self.post({"quartiles": "Q1"})
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["error"], "JOURNAL_CLI_FAILED")

    def test_the_deadline_is_enforced_with_a_504(self) -> None:
        self.stub(SEARCH_OK, sleep=5)
        with mock.patch.object(server, "JOURNAL_SEARCH_TIMEOUT_SECONDS", 0.5):
            started = time.monotonic()
            response = self.post({"quartiles": "Q1"})
        self.assertLess(time.monotonic() - started, 4)
        self.assertEqual(response.status_code, 504)
        self.assertEqual(response.json()["error"], "TIMEOUT")

    def test_a_second_search_while_one_runs_is_409(self) -> None:
        self.stub(SEARCH_OK)
        self.assertTrue(server._JOURNAL_LOCK.acquire(blocking=False))
        try:
            response = self.post({"quartiles": "Q1"})
        finally:
            server._JOURNAL_LOCK.release()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "SEARCH_RUNNING")
        self.assertEqual(self.calls(), [])

    def test_a_slow_search_does_not_block_the_event_loop(self) -> None:
        self.stub(SEARCH_OK, sleep=1.5)
        with TestClient(server.create_app(self.root)) as client:
            result = {}

            def search() -> None:
                result["status"] = client.post("/api/journals/search", json={"quartiles": "Q1"},
                                               headers=SAME).status_code

            worker = threading.Thread(target=search)
            worker.start()
            time.sleep(0.4)
            started = time.monotonic()
            self.assertEqual(client.get("/api/pdf/annotations").status_code, 200)
            self.assertLess(time.monotonic() - started, 1.0)
            worker.join(10)
        self.assertEqual(result["status"], 200)

    def test_the_lock_is_released_after_a_failure(self) -> None:
        self.stub({"ok": False, "error": "PAPER_ABSENT", "message": "x"}, exit_code=2)
        self.post({"quartiles": "Q1"})
        self.assertTrue(server._JOURNAL_LOCK.acquire(blocking=False))
        server._JOURNAL_LOCK.release()


# --------------------------------------------------------------------------
# POST /api/journals/sjr
# --------------------------------------------------------------------------
class SjrUploadTests(JournalCase):
    def upload(self, data: bytes, query: str = "?name=scimagojr-2019.csv", headers=SAME):
        return self.client.post("/api/journals/sjr" + query, content=data, headers=headers)

    def test_a_cross_origin_upload_is_refused(self) -> None:
        self.assertEqual(self.upload(SJR_FIXTURE.read_bytes(), headers=OTHER).status_code, 403)
        self.assertFalse(self.sjr_dir.exists())

    def test_a_valid_csv_is_imported_through_the_cli(self) -> None:
        response = self.upload(SJR_FIXTURE.read_bytes())
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual((body["rows"], body["year"]), (5, 2019))
        self.assertEqual((self.sjr_dir / "scimagojr-2019.csv").read_bytes(), SJR_FIXTURE.read_bytes())

    def test_the_year_query_overrides_an_unhelpful_name(self) -> None:
        response = self.upload(SJR_FIXTURE.read_bytes(), "?name=download.csv&year=2020")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["year"], 2020)
        self.assertTrue((self.sjr_dir / "scimagojr-2020.csv").is_file())

    def test_a_name_without_a_year_is_the_clis_refusal(self) -> None:
        response = self.upload(SJR_FIXTURE.read_bytes(), "?name=download.csv")
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"], "SJR_FILE_INVALID")
        self.assertFalse(self.sjr_dir.exists())

    def test_a_file_that_is_not_an_sjr_csv_is_422_and_stores_nothing(self) -> None:
        response = self.upload(b"a,b,c\n1,2,3\n")
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"], "SJR_FILE_INVALID")
        self.assertFalse(self.sjr_dir.exists() and any(self.sjr_dir.iterdir()))

    def test_an_empty_body_is_422(self) -> None:
        response = self.upload(b"")
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"], "SJR_FILE_INVALID")

    def test_the_size_cap_answers_413_and_stores_nothing(self) -> None:
        with mock.patch.object(server, "SJR_UPLOAD_MAX_BYTES", 256):
            response = self.upload(SJR_FIXTURE.read_bytes())
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json()["error"], "FILE_TOO_LARGE")
        self.assertFalse(self.sjr_dir.exists() and any(self.sjr_dir.iterdir()))

    def test_a_bad_year_is_422(self) -> None:
        for year in ("abc", "1900", "9999"):
            with self.subTest(year=year):
                response = self.upload(SJR_FIXTURE.read_bytes(), f"?name=x.csv&year={year}")
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json()["error"], "FILTER_INVALID")

    def test_a_hostile_file_name_cannot_write_outside_the_cache(self) -> None:
        before = tree_state(self.tmp)
        response = self.upload(SJR_FIXTURE.read_bytes(), "?name=../../escape/scimagojr-2018.csv")
        self.assertEqual(response.status_code, 200, response.text)
        added = set(tree_state(self.tmp)) - set(before)
        self.assertEqual(added, {"sjr/scimagojr-2018.csv"})


# --------------------------------------------------------------------------
# venues
# --------------------------------------------------------------------------
class VenueEndpointCase(VenueCase):
    """A venue scratch repository served by the dashboard app."""

    def setUp(self) -> None:
        super().setUp()
        self.client = TestClient(server.create_app(self.root))

    def post(self, path: str, body=None, headers=SAME):
        return self.client.post(path, json=body if body is not None else {}, headers=headers)

    def planned(self, **canonical) -> str:
        """An audited venue with a stored plan; returns the plan hash."""
        self.write_canonical(canonical_tex(**canonical))
        self.audited()
        return self.ok("plan", "--slug", "eswa", "--file", str(self.write_plan(PLAN_TEXT)))["plan_sha256"]


class VenueReadTests(VenueEndpointCase):
    def test_the_list_is_empty_without_venues(self) -> None:
        body = self.client.get("/api/venues").json()
        self.assertEqual(body, {"ok": True, "venues": []})

    def test_the_list_summarises_the_state_machine(self) -> None:
        self.selected()
        (venue,) = self.client.get("/api/venues").json()["venues"]
        self.assertEqual((venue["slug"], venue["state"]), ("eswa", "selected"))
        self.assertEqual(venue["journal"], "Expert Systems with Applications")

    def test_the_list_without_a_paper_directory_is_empty_not_an_error(self) -> None:
        (self.paper / "main.tex").unlink()
        self.paper.rename(self.root / "paper-gone")
        response = self.client.get("/api/venues")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["venues"], [])

    def test_the_detail_carries_status_audit_plan_and_approval(self) -> None:
        digest = self.planned(abstract_words=260)
        body = self.client.get("/api/venues/eswa").json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["status"]["state"], "planned")
        self.assertEqual(body["venue"]["journal"]["name"], "Expert Systems with Applications")
        self.assertIn("over-limit:abstract_words", [f["id"] for f in body["audit"]["findings"]])
        self.assertEqual(body["plan"]["sha256"], digest)
        self.assertEqual(body["plan"]["text"], PLAN_TEXT)
        self.assertIsNone(body["approval"])
        self.assertEqual(body["requirements"]["guidelines_urls"][0].split("/")[2], "www.sciencedirect.com")
        self.assertFalse(body["pdf"])

    def test_the_plan_hash_is_that_of_the_bytes_on_disk(self) -> None:
        self.planned(abstract_words=260)
        body = self.client.get("/api/venues/eswa").json()
        self.assertEqual(body["plan"]["sha256"],
                         hashlib.sha256((self.venue_dir() / "plan.md").read_bytes()).hexdigest())

    def test_an_early_venue_has_null_parts_not_errors(self) -> None:
        self.selected()
        body = self.client.get("/api/venues/eswa").json()
        self.assertEqual(body["status"]["state"], "selected")
        for part in ("audit", "plan", "approval", "requirements", "template", "build"):
            self.assertIsNone(body[part], part)

    def test_a_malformed_or_traversing_slug_is_400(self) -> None:
        for slug in ("%2E%2E", "Bad_Slug", "%2e%2e", "a" * 80, "-lead", "UPPER", "x.y"):
            with self.subTest(slug=slug):
                response = self.client.get(f"/api/venues/{slug}")
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()["code"], "VENUE_SLUG_INVALID")

    def test_an_unknown_venue_is_404(self) -> None:
        response = self.client.get("/api/venues/ghost")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "VENUE_ABSENT")

    def test_a_symlinked_venue_directory_is_not_followed(self) -> None:
        outside = self.root / "elsewhere"
        outside.mkdir()
        (outside / "venue.json").write_text(json.dumps({"journal": {"name": "Leak"}}), encoding="utf-8")
        (self.paper / "venues").mkdir(exist_ok=True)
        (self.paper / "venues" / "leak").symlink_to(outside)
        self.assertEqual(self.client.get("/api/venues/leak").status_code, 404)
        self.assertEqual(self.client.get("/api/venues").json()["venues"], [])

    def test_an_oversized_plan_is_not_read(self) -> None:
        self.planned(abstract_words=260)
        with mock.patch.object(server, "VENUE_TEXT_MAX_BYTES", 8):
            body = self.client.get("/api/venues/eswa").json()
        self.assertTrue(body["ok"])
        self.assertIsNone(body["plan"])
        self.assertEqual(body["plan_error"]["code"], "FILE_TOO_LARGE")


class VenueSelectTests(VenueEndpointCase):
    def test_cross_origin_is_403(self) -> None:
        self.candidates()
        self.assertEqual(self.post("/api/venues/select", {"candidate": "S1001"}, OTHER).status_code, 403)
        self.assertFalse((self.paper / "venues").exists())

    def test_a_candidate_becomes_a_venue_with_a_derived_slug(self) -> None:
        self.candidates()
        response = self.post("/api/venues/select", {"candidate": "https://openalex.org/S1001"})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["slug"], "expert-systems-with-applications")
        record = json.loads((self.venue_dir("expert-systems-with-applications") / "venue.json").read_text())
        self.assertEqual(record["quartile"], "Q1")
        self.assertEqual(record["via"], "candidate")

    def test_an_explicit_valid_slug_is_used(self) -> None:
        self.candidates()
        response = self.post("/api/venues/select", {"candidate": "S1001", "slug": "eswa"})
        self.assertEqual(response.json()["slug"], "eswa")
        self.assertTrue((self.venue_dir() / "venue.json").is_file())

    def test_selecting_the_same_journal_twice_is_409(self) -> None:
        self.candidates()
        self.post("/api/venues/select", {"candidate": "S1001"})
        response = self.post("/api/venues/select", {"candidate": "S1001"})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "VENUE_EXISTS")

    def test_refusals_keep_their_code_and_write_nothing(self) -> None:
        cases = (
            ({"candidate": "S9999", "slug": "eswa"}, 404, "CANDIDATE_UNKNOWN", True),
            ({"candidate": "S1001", "slug": "Bad Slug"}, 400, "VENUE_SLUG_INVALID", True),
            ({"candidate": "S1001", "slug": "../escape"}, 400, "VENUE_SLUG_INVALID", True),
            ({}, 422, "SELECT_MODE_REQUIRED", True),
            ({"candidate": "S1001", "journal": "X", "issn": "1234-5678", "slug": "eswa"}, 422,
             "SELECT_MODE_CONFLICT", True),
            ({"journal": "Some Journal", "issn": "bad", "slug": "eswa"}, 422, "ISSN_INVALID", True),
        )
        self.candidates()
        before = tree_state(self.root)
        for body, status, code, _ in cases:
            with self.subTest(body=body):
                response = self.post("/api/venues/select", body)
                self.assertEqual(response.status_code, status, response.text)
                self.assertEqual(response.json()["code"], code)
                self.assertFalse(response.json()["ok"])
        self.assertEqual(tree_state(self.root), before)

    def test_without_a_candidates_file_the_refusal_is_409(self) -> None:
        response = self.post("/api/venues/select", {"candidate": "S1001", "slug": "eswa"})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "CANDIDATES_ABSENT")

    def test_a_manual_journal_needs_a_slug_or_derives_one_from_its_name(self) -> None:
        response = self.post("/api/venues/select", {"journal": "Some Journal!", "issn": "1234-5678"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["slug"], "some-journal")

    def test_a_name_that_slugifies_to_nothing_falls_back_to_the_candidate_id(self) -> None:
        self.candidates()
        data = json.loads((self.paper / "journal-candidates.json").read_text())
        data["candidates"][0]["display_name"] = "!!!"
        (self.paper / "journal-candidates.json").write_text(json.dumps(data), encoding="utf-8")
        response = self.post("/api/venues/select", {"candidate": "S1001"})
        self.assertEqual(response.json()["slug"], "venue-s1001")


class VenueApproveTests(VenueEndpointCase):
    def approve(self, slug: str, statement: str, digest: str, headers=SAME):
        return self.post(f"/api/venues/{slug}/approve", {"statement": statement, "plan_sha256": digest}, headers)

    def test_a_cross_origin_approval_is_403_and_records_nothing(self) -> None:
        digest = self.planned(abstract_words=260)
        self.assertEqual(self.approve("eswa", "ok", digest, OTHER).status_code, 403)
        self.assertFalse((self.venue_dir() / "approval.json").exists())

    def test_a_request_without_an_origin_header_is_refused_too(self) -> None:
        digest = self.planned(abstract_words=260)
        response = self.client.post("/api/venues/eswa/approve",
                                    json={"statement": "ok", "plan_sha256": digest})
        self.assertEqual(response.status_code, 403)
        self.assertFalse((self.venue_dir() / "approval.json").exists())

    def test_the_approval_is_recorded_via_the_dashboard(self) -> None:
        digest = self.planned(abstract_words=260)
        response = self.approve("eswa", "I read the plan and agree.", digest)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["via"], "dashboard")
        record = json.loads((self.venue_dir() / "approval.json").read_text())
        self.assertEqual(record["via"], "dashboard")
        self.assertEqual(record["statement"], "I read the plan and agree.")
        self.assertEqual(record["plan_sha256"], digest)
        detail = self.client.get("/api/venues/eswa").json()
        self.assertEqual(detail["status"]["state"], "approved")
        self.assertTrue(detail["approval"]["valid"])

    def test_a_wrong_hash_is_409_and_an_empty_statement_422(self) -> None:
        digest = self.planned(abstract_words=260)
        wrong = self.approve("eswa", "ok", "0" * 64)
        self.assertEqual(wrong.status_code, 409)
        self.assertEqual(wrong.json()["code"], "PLAN_HASH_MISMATCH")
        empty = self.approve("eswa", "   ", digest)
        self.assertEqual(empty.status_code, 422)
        self.assertEqual(empty.json()["code"], "STATEMENT_EMPTY")
        self.assertFalse((self.venue_dir() / "approval.json").exists())

    def test_a_plan_changed_after_the_operator_read_it_is_refused(self) -> None:
        digest = self.planned(abstract_words=260)
        self.ok("plan", "--slug", "eswa", "--file", str(self.write_plan(PLAN_TEXT + "- [over-limit:abstract_words] again\n")))
        response = self.approve("eswa", "ok", digest)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "PLAN_HASH_MISMATCH")

    def test_a_non_string_body_is_422(self) -> None:
        self.planned(abstract_words=260)
        response = self.post("/api/venues/eswa/approve", {"statement": 5, "plan_sha256": ["x"]})
        self.assertEqual(response.status_code, 422)

    def test_no_plan_is_409(self) -> None:
        self.write_canonical(canonical_tex(abstract_words=260))
        self.audited()
        response = self.approve("eswa", "ok", "0" * 64)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "PLAN_ABSENT")

    def test_slug_traversal_is_refused_before_anything_runs(self) -> None:
        for slug in ("%2E%2E", "Bad_Slug", "%2e%2e"):
            with self.subTest(slug=slug):
                self.assertEqual(self.approve(slug, "ok", "0" * 64).status_code, 400)

    def test_an_unknown_venue_is_404(self) -> None:
        self.assertEqual(self.approve("ghost", "ok", "0" * 64).status_code, 404)


class VenueBuildAndCompileTests(VenueEndpointCase):
    def built(self) -> str:
        digest = self.planned(abstract_words=260)
        self.ok("approve", "--slug", "eswa", "--statement", "ok", "--plan-sha256", digest)
        return digest

    def fake_tex(self, calls: list, write_pdf: bool = True):
        def fake_run(argv, **kwargs):
            calls.append((argv, kwargs))
            if write_pdf and argv[0] == "pdflatex":
                (Path(kwargs["cwd"]) / "main.pdf").write_bytes(b"%PDF-1.4 venue build")
            return subprocess.CompletedProcess(argv, 0, stdout="This is pdfTeX", stderr="")
        return fake_run

    # -- build ----------------------------------------------------------------
    def test_a_cross_origin_build_is_403(self) -> None:
        self.built()
        self.assertEqual(self.post("/api/venues/eswa/build", None, OTHER).status_code, 403)
        self.assertFalse((self.venue_dir() / "main.tex").exists())

    def test_build_refuses_without_an_approved_plan(self) -> None:
        self.planned(abstract_words=260)
        response = self.post("/api/venues/eswa/build")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "PLAN_NOT_APPROVED")
        self.assertFalse((self.venue_dir() / "main.tex").exists())

    def test_build_writes_the_venue_file_and_leaves_the_canonical_text_alone(self) -> None:
        self.built()
        canonical = sha(self.paper / "main.tex")
        response = self.post("/api/venues/eswa/build")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["output"], "paper/venues/eswa/main.tex")
        self.assertEqual(body["compile_env"], {"TEXINPUTS": "./template//:", "BSTINPUTS": "./template//:"})
        self.assertTrue((self.venue_dir() / "main.tex").is_file())
        self.assertEqual(sha(self.paper / "main.tex"), canonical)

    def test_build_is_409_while_a_compilation_holds_the_paper_lock(self) -> None:
        self.built()
        self.assertTrue(server._PAPER_LOCK.acquire(blocking=False))
        try:
            response = self.post("/api/venues/eswa/build")
        finally:
            server._PAPER_LOCK.release()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "PAPER_BUSY")

    # -- compile --------------------------------------------------------------
    def compile(self, query: str = "?venue=eswa", headers=SAME):
        return self.client.post("/api/paper/compile" + query, headers=headers)

    def test_a_cross_origin_compile_is_403(self) -> None:
        self.assertEqual(self.compile(headers=OTHER).status_code, 403)

    def test_compile_of_an_unbuilt_venue_is_409(self) -> None:
        self.planned(abstract_words=260)
        response = self.compile()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "VENUE_NOT_BUILT")

    def test_compile_of_an_unknown_venue_is_404_and_a_bad_slug_400(self) -> None:
        self.assertEqual(self.compile("?venue=ghost").status_code, 404)
        for slug in ("..", "Bad_Slug", "a/b", "%2e%2e"):
            with self.subTest(slug=slug):
                self.assertEqual(self.compile(f"?venue={slug}").status_code, 400)

    def test_the_venue_compile_runs_the_same_sequence_in_the_venue_directory(self) -> None:
        self.built()
        self.assertEqual(self.post("/api/venues/eswa/build").status_code, 200)
        calls: list = []
        with mock.patch.object(server.subprocess, "run", self.fake_tex(calls)):
            response = self.compile()
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["outputs"], ["paper/venues/eswa/main.pdf"])
        self.assertEqual([argv[0] for argv, _ in calls], ["pdflatex", "bibtex", "pdflatex", "pdflatex"])
        self.assertEqual(calls[0][0], ["pdflatex", "-interaction=nonstopmode", "main.tex"])
        self.assertEqual(calls[1][0], ["bibtex", "main"])
        for _, kwargs in calls:
            self.assertEqual(Path(kwargs["cwd"]), self.venue_dir())
            self.assertEqual(kwargs["env"]["TEXINPUTS"], "./template//:")
            self.assertEqual(kwargs["env"]["BSTINPUTS"], "./template//:")
        self.assertEqual((self.venue_dir() / "main.pdf").read_bytes(), b"%PDF-1.4 venue build")
        self.assertFalse((self.paper / "main.pdf").exists())

    def test_a_template_free_venue_gets_no_extra_environment(self) -> None:
        self.built()
        self.post("/api/venues/eswa/build")
        (self.venue_dir() / "template.json").write_text(json.dumps({"kind": "texlive", "class": "elsarticle"}))
        calls: list = []
        with mock.patch.dict(os.environ):
            os.environ.pop("TEXINPUTS", None)
            os.environ.pop("BSTINPUTS", None)
            with mock.patch.object(server.subprocess, "run", self.fake_tex(calls)):
                self.assertEqual(self.compile().status_code, 200)
        for _, kwargs in calls:
            self.assertNotIn("TEXINPUTS", kwargs["env"])

    def test_only_the_tex_search_variables_are_taken_from_the_environment_report(self) -> None:
        report = {"TEXINPUTS": "./template//:", "BSTINPUTS": "./template//:", "PATH": "/evil",
                  "LD_PRELOAD": "/evil.so", "TEXINPUTS2": "x", "BSTINPUTS_": 3}
        self.assertEqual(server._tex_environment(report),
                         {"TEXINPUTS": "./template//:", "BSTINPUTS": "./template//:"})
        self.assertEqual(server._tex_environment({"TEXINPUTS": 5, "BSTINPUTS": "a\0b"}), {})
        self.assertEqual(server._tex_environment(None), {})

    def test_a_timeout_is_a_504_and_the_lock_is_released(self) -> None:
        self.built()
        self.post("/api/venues/eswa/build")

        def slow(argv, **kwargs):
            raise subprocess.TimeoutExpired(argv, 1)

        with mock.patch.object(server.subprocess, "run", slow):
            response = self.compile()
        self.assertEqual(response.status_code, 504)
        self.assertTrue(server._PAPER_LOCK.acquire(blocking=False))
        server._PAPER_LOCK.release()

    def test_a_missing_toolchain_is_a_typed_error_not_a_crash(self) -> None:
        self.built()
        self.post("/api/venues/eswa/build")

        def missing(argv, **kwargs):
            raise FileNotFoundError(argv[0])

        with mock.patch.object(server.subprocess, "run", missing):
            response = self.compile()
        self.assertEqual(response.status_code, 500)
        self.assertFalse(response.json()["ok"])
        self.assertIn("pdflatex", response.json()["error"])

    def test_compile_is_409_while_the_paper_lock_is_held(self) -> None:
        self.built()
        self.post("/api/venues/eswa/build")
        self.assertTrue(server._PAPER_LOCK.acquire(blocking=False))
        try:
            response = self.compile()
        finally:
            server._PAPER_LOCK.release()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "PAPER_BUSY")

    def test_without_a_venue_the_canonical_paper_is_compiled(self) -> None:
        with mock.patch.object(server, "_compile_paper", return_value=({"ok": True, "outputs": ["paper/main.pdf"]}, 200)) as canonical:
            response = self.compile("")
        self.assertEqual(response.status_code, 200)
        canonical.assert_called_once()
        self.assertEqual(response.json()["outputs"], ["paper/main.pdf"])

    # -- the venue PDF --------------------------------------------------------
    def test_the_venue_pdf_is_served_with_an_etag_and_the_canonical_one_is_untouched(self) -> None:
        self.selected()
        (self.paper / "main.pdf").write_bytes(b"%PDF-1.4 canonical")
        (self.venue_dir() / "main.pdf").write_bytes(b"%PDF-1.4 venue")
        venue = self.client.get("/api/pdf?venue=eswa")
        self.assertEqual(venue.status_code, 200)
        self.assertEqual(venue.content, b"%PDF-1.4 venue")
        self.assertEqual(venue.headers["content-type"], "application/pdf")
        self.assertEqual(self.client.get("/api/pdf").content, b"%PDF-1.4 canonical")
        revalidated = self.client.get("/api/pdf?venue=eswa", headers={"If-None-Match": venue.headers["etag"]})
        self.assertEqual(revalidated.status_code, 304)

    def test_the_venue_pdf_refuses_bad_slugs_and_missing_files(self) -> None:
        self.selected()
        self.assertEqual(self.client.get("/api/pdf?venue=eswa").status_code, 404)
        self.assertEqual(self.client.get("/api/pdf?venue=ghost").status_code, 404)
        for slug in ("..", "Bad_Slug", "a/b", "%2e%2e%2f"):
            with self.subTest(slug=slug):
                self.assertEqual(self.client.get(f"/api/pdf?venue={slug}").status_code, 400)

    def test_a_symlinked_venue_pdf_out_of_the_workspace_is_not_served(self) -> None:
        self.selected()
        with tempfile.TemporaryDirectory() as elsewhere:
            target = Path(elsewhere) / "main.pdf"
            target.write_bytes(b"%PDF-1.4 elsewhere")
            (self.venue_dir() / "main.pdf").symlink_to(target)
            self.assertEqual(self.client.get("/api/pdf?venue=eswa").status_code, 404)



# --------------------------------------------------------------------------
# the panel under node
# --------------------------------------------------------------------------
STATIC = REPO / "skills" / "_core" / "command_center" / "static"
PAGE = (STATIC / "index.html").read_text(encoding="utf-8")
PANEL = STATIC / "journals-panel.js"

#: Every tag the panel may write; anything else in its output is an injection.
ALLOWED_TAGS = {"div", "span", "strong", "a", "table", "thead", "tbody", "tr", "th", "td", "details", "summary",
                "ul", "li", "button", "label", "select", "option", "input", "code", "pre", "h4", "h5",
                "section", "textarea", "p", "em"}

PRELUDE = """
const fs = require('fs');
const store = {};
global.window = global;
global.localStorage = { getItem: (k) => store[k] ?? null, setItem: (k, v) => { store[k] = v; } };
global.CustomEvent = class { constructor(type, init) { this.type = type; this.detail = init && init.detail; } };
const docListeners = {};
const host = { innerHTML: '', listeners: {}, addEventListener(type, fn) { this.listeners[type] = fn; } };
global.document = { readyState: 'complete', documentElement: { lang: 'xx' }, querySelectorAll: () => [],
  addEventListener(type, fn) { docListeners[type] = fn; }, dispatchEvent() {}, getElementById: (id) => (id === 'journalsPanel' ? host : null) };
const calls = []; const sent = []; const pdf = [];
global.__routes = [];
global.fetch = async (url, init) => {
  const method = (init && init.method) || 'GET';
  calls.push({ url, method, body: init && init.body });
  const route = global.__routes.find((r) => r[0] === method && url.startsWith(r[1]));
  const reply = route ? route[2] : { status: 404, body: {} };
  return { ok: reply.status < 400, status: reply.status, json: async () => reply.body };
};
global.sendToCli = async (text, run, options) => { sent.push({ text, run, options }); return true; };
global.setPdfVenue = (slug) => pdf.push(slug);
%(files)s
window.i18n.setLanguage(%(lang)s);
const P = window.JournalsPanel;
P.mount();
const out = (value) => console.log(JSON.stringify(value));
const el = (attrs, extra) => Object.assign({ disabled: false, getAttribute: (n) => (n in attrs ? attrs[n] : null),
  closest(selector) { const name = selector.slice(1, -1); return name in attrs ? this : null; } }, extra || {});
const click = async (attrs) => { await host.listeners.click({ target: el(attrs) }); await new Promise((r) => setTimeout(r, 0)); };
const field = async (attrs, extra, type) => { await host.listeners[type || 'input']({ target: el(attrs, extra) }); await new Promise((r) => setTimeout(r, 0)); };
"""


@unittest.skipUnless(shutil.which("node"), "node is required to run the panel")
class PanelRenderTests(unittest.TestCase):
    def node(self, body: str, lang: str = "es"):
        files = "".join(f"eval(fs.readFileSync({json.dumps(str(path))}, 'utf8'));"
                        for path in (STATIC / "i18n" / "en.js", STATIC / "i18n" / "es.js", STATIC / "i18n.js", PANEL))
        script = (PRELUDE % {"files": files, "lang": json.dumps(lang)} + "(async () => {" + body
                  + "})().catch((error) => { console.error(error); process.exit(1); });")
        done = subprocess.run(["node", "-e", script], capture_output=True, text=True, cwd=tempfile.gettempdir(),
                              check=False)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout.strip().splitlines()[-1])

    def candidates_js(self) -> str:
        return "const doc = " + (FIXTURES / "journal-candidates.json").read_text(encoding="utf-8") + ";"

    def assert_only_known_markup(self, html: str) -> None:
        tags = set(re.findall(r"</?([a-zA-Z][a-zA-Z0-9]*)", html))
        self.assertLessEqual(tags, ALLOWED_TAGS, f"unexpected tags: {tags - ALLOWED_TAGS}")
        for href in re.findall(r'href="([^"]*)"', html):
            self.assertRegex(href, r"^(https?://|/api/)", href)

    # -- results --------------------------------------------------------------
    def test_the_results_render_in_spanish_with_every_column(self) -> None:
        html = self.node(self.candidates_js() + """
          out(P.resultsHtml({ journals: { candidates: doc, notes_md: true, sjr: { file: '/x/scimagojr-2019.csv', year: 2019 } },
                              sort: 'fit', busy: {} }));""")
        for expected in (
            "Open Signal Processing", "Neural Fixtures Letters", "Elegir esta revista", "Aproximado con OpenAlex",
            "sin datos públicos", "15 sem (RIC 9.6–20.4) · n=6", "5 sem (RIC 3.2–6.8) · n=6", "<strong>0.57</strong>",
            "trabajos similares 0.60", "citadas en el artículo 0.50", "afinidad temática 0.58",
            "ISSN 3333-3333", "SJR 2.345 · 2019", "percentil 60.0", "Acceso abierto", "DOAJ", "APC 1500 USD",
            "APC desconocido", ">pubmed<", ">crossref<", "Revista", "Cuartil",
            "https://doi.org/10.3333/osp.1", "https://neural-fixtures.example/",
            "Abrir paper/journal-candidates.md", "excluidas", "Artificial Intelligence (Q1), Software (Q2)",
        ):
            self.assertIn(expected, html)
        self.assertIn('rel="noopener noreferrer"', html)
        self.assert_only_known_markup(html)

    def test_facet_hits_the_gate_and_the_flag_badge_use_the_cli_names(self) -> None:
        html = self.node(self.candidates_js() + """
          const row = (name) => {
            const one = { ...doc, candidates: doc.candidates.filter((c) => c.display_name === name) };
            return P.resultsHtml({ journals: { candidates: one }, sort: 'fit', busy: {} });
          };
          out({ gated: row('Neural Fixtures Letters'), plain: row('Open Signal Processing') });""")
        gated, plain = html["gated"], html["plain"]
        self.assertIn("método 5 · aplicación 0", gated)
        self.assertIn("afinidad temática de la aplicación 0", gated)
        self.assertIn("compuerta ×0.5", gated)
        self.assertIn('<span class="badge badge--warn">Sin evidencia de aplicación</span>', gated)
        self.assertIn("método 3 · aplicación 3", plain)
        self.assertNotIn("compuerta", plain)
        self.assertNotIn("Sin evidencia de aplicación", plain)

    def test_the_scoring_formula_line_comes_from_query_scoring(self) -> None:
        es, off, dropped = self.node(self.candidates_js() + """
          const view = (patch) => P.resultsHtml({ journals: { candidates: { ...doc, query: { ...doc.query, scoring: { ...doc.query.scoring, ...patch } } } },
                                                 sort: 'fit', busy: {} });
          out([view({}),
               view({ facet_gate: { applies: false, factor: 0.5, rule: 'x' } }),
               view({ active: ['similar_works', 'cited_in_paper'] })]);""")
        self.assertIn("Fórmula de ajuste: fit_score = 0.45 * similar_works + 0.3 * cited_in_paper + 0.25 * topic_overlap", es)
        self.assertIn("Compuerta de aplicación: ×0.5 sin evidencia de aplicación", es)
        self.assertNotIn("Componentes sin señal", es)
        self.assertIn("Compuerta de aplicación inactiva", off)
        self.assertIn("Componentes sin señal, fuera de la fórmula: topic_overlap", dropped)

    def test_the_same_results_render_in_english(self) -> None:
        html = self.node(self.candidates_js() + """
          out(P.resultsHtml({ journals: { candidates: doc }, sort: 'fit', busy: {} }));""", lang="en")
        for expected in ("Choose this journal", "OpenAlex proxy (approximate)", "no public data",
                         "15 wk (IQR 9.6–20.4) · n=6", "API calls: 26 made, 0 cached",
                         "Fit formula: fit_score = 0.45 * similar_works", "method 5 · application 0",
                         "application gate ×0.5", "OpenAlex 15/0 · Crossref 5/0 · PubMed 6/0",
                         "OpenAlex budget: USD 0.05 left of 0.1"):
            self.assertIn(expected, html)
        self.assertNotIn("Elegir", html)

    def test_rows_tolerate_the_absence_of_the_newer_fields(self) -> None:
        html = self.node("""
          const doc = { candidates: [{ display_name: 'Bare', openalex_id: 'S9' }, { id: 'S8' }, {}], quartiles: 'Q1-Q2' };
          out(P.resultsHtml({ journals: { candidates: doc }, sort: 'fit', busy: {} }));""")
        self.assertIn("Bare", html)
        self.assertEqual(html.count("Elegir esta revista"), 3)
        self.assert_only_known_markup(html)

    def test_no_file_and_an_unreadable_file_have_their_own_messages(self) -> None:
        empty, broken = self.node("""
          out([P.resultsHtml({ journals: { candidates: null }, sort: 'fit', busy: {} }),
               P.resultsHtml({ journals: { candidates: null, candidates_error: { code: 'X', message: '<b>bad</b>' } }, sort: 'fit', busy: {} })]);""")
        self.assertIn("Todavía no hay búsqueda", empty)
        self.assertIn("&lt;b&gt;bad&lt;/b&gt;", broken)

    def test_sorting_by_review_time_puts_journals_without_data_last(self) -> None:
        order = self.node(self.candidates_js() + """
          doc.candidates.reverse();
          const names = (sort) => { const html = P.resultsHtml({ journals: { candidates: doc }, sort, busy: {} });
            return [...html.matchAll(/<strong>([^<]*)<\\/strong>/g)].map((m) => m[1]).filter((n) => /[a-z]/.test(n)); };
          out([names('fit'), names('review'), names('hindex')]);""")
        self.assertEqual(order[0], ["Open Signal Processing", "Cited Only Journal", "Obscure Quarterly",
                                    "Neural Fixtures Letters", "Biomedical Fixture Reports"])
        self.assertEqual(order[1], ["Neural Fixtures Letters", "Open Signal Processing", "Cited Only Journal",
                                    "Obscure Quarterly", "Biomedical Fixture Reports"])
        self.assertEqual(order[2], ["Neural Fixtures Letters", "Open Signal Processing", "Cited Only Journal",
                                    "Biomedical Fixture Reports", "Obscure Quarterly"])

    def test_the_api_calls_line_shows_made_cached_per_service_and_the_budget(self) -> None:
        ok, exhausted, unknown, cache_off, absent = self.node(self.candidates_js() + """
          const view = (calls) => P.resultsHtml({ journals: { candidates: { ...doc, api_calls: calls } }, sort: 'fit', busy: {} });
          const base = doc.api_calls;
          out([view(base),
               view({ ...base, budget: { state: 'exhausted', remaining_usd: 0, limit_usd: 0.1, retry_after_seconds: 3600 } }),
               view({ ...base, budget: { state: 'unknown', remaining_usd: null, limit_usd: null, retry_after_seconds: null } }),
               view({ ...base, cache: { enabled: false, dir: '/x' } }),
               view(undefined)]);""")
        self.assertIn("Llamadas a las APIs: 26 hechas, 0 en caché", ok)
        self.assertIn("OpenAlex 15/0 · Crossref 5/0 · PubMed 6/0", ok)
        self.assertIn("Presupuesto de OpenAlex: quedan USD 0.05 de 0.1", ok)
        self.assertIn("badge--ok", ok)
        self.assertNotIn("agotado", ok)
        self.assertIn("Presupuesto de OpenAlex agotado (reintentar en 3600 s)", exhausted)
        self.assertIn("OPENALEX_API_KEY", exhausted)
        self.assertIn("badge--bad", exhausted)
        self.assertIn("Presupuesto de OpenAlex: sin datos", unknown)
        self.assertNotIn("agotado", unknown)
        self.assertIn("Caché desactivada", cache_off)
        self.assertNotIn("Llamadas a las APIs", absent)
        self.assertNotIn("Presupuesto", absent)

    # -- escaping -------------------------------------------------------------
    def test_hostile_values_never_become_markup(self) -> None:
        html = self.node("""
          const evil = '<script>alert(1)</script><img src=x onerror=alert(2)>"' + "'";
          const doc = { candidates: [{
            display_name: evil, openalex_id: evil, publisher: evil, issn_l: evil, homepage_url: 'javascript:alert(3)',
            quartile: evil, quartile_source: 'sjr', sjr: { value: evil, year: evil }, review_time: { source: evil, median_days: 70, n: evil },
            fit_score: 0.5, fit: { similar_works: evil }, facets: { method: evil, application: evil, application_topic_overlap: evil, gate: evil },
            flags: [evil], similar_works: [{ title: evil, year: evil, doi: evil }, { title: 'ok', doi: 'https://doi.org/10.1/a"b' }],
            h_index: evil, is_oa: true, apc_usd: evil }],
            api_calls: { made: evil, cached: evil, by_service: { [evil]: { made: evil, cached: evil } },
                         cache: { enabled: evil }, budget: { state: evil, remaining_usd: evil, limit_usd: evil, retry_after_seconds: evil } },
            query: { title: evil, scoring: { formula: evil, active: [evil], facet_gate: { applies: true, factor: evil } } },
            notes: [evil], quartiles: [evil], generated_at: evil, excluded_count: evil };
          out(P.resultsHtml({ journals: { candidates: doc, candidates_error: { message: evil } }, sort: 'fit', busy: {} }));""")
        self.assertNotIn("<script", html)
        self.assertNotIn("<img", html)
        self.assertNotIn('javascript:', html.replace("&quot;", '"').split('href="')[1] if 'href="' in html else "")
        self.assert_only_known_markup(html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)

    def test_the_fixture_with_hostile_works_stays_inert(self) -> None:
        html = self.node(self.candidates_js() + """
          out(P.resultsHtml({ journals: { candidates: doc }, sort: 'fit', busy: {} }));""")
        self.assertNotIn("<img", html)
        self.assertNotIn("<script", html)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", html)
        self.assertIn("%3Cscript%3E", html)

    # -- the form -------------------------------------------------------------
    def test_the_form_and_the_sjr_line_render_in_spanish(self) -> None:
        form, sjr_none, sjr_file = self.node("""
          const base = { form: { from: 'Q2', to: 'Q3', oaOnly: true, maxApc: '1500', maxReview: '', limit: '15' }, busy: {}, sort: 'fit', sjrYear: '' };
          out([P.formHtml(base),
               P.sjrHtml({ ...base, journals: { sjr: null, sjr_download_url: 'https://www.scimagojr.com/journalrank.php' } }),
               P.sjrHtml({ ...base, journals: { sjr: { file: '/home/u/.cache/scimagojr-2025.csv', year: 2025 } } })]);""")
        for expected in ("Desde el cuartil", "Hasta el cuartil", "Solo acceso abierto", "APC máximo (USD)",
                         "Revisión máxima (días)", "Buscar revistas", "Analizar con agente", "Ordenar por",
                         "Forzar actualización"):
            self.assertIn(expected, form)
        self.assertIn('<option value="Q2" selected>', form)
        self.assertIn('data-jp-field="oaOnly" checked', form)
        self.assertIn('data-jp-field="noCache">', form)
        self.assertNotIn('data-jp-field="noCache" checked', form)
        self.assertIn('value="1500"', form)
        self.assertIn("Sin archivo SJR", sjr_none)
        self.assertIn('href="https://www.scimagojr.com/journalrank.php"', sjr_none)
        self.assertIn("Subir CSV de SJR", sjr_none)
        self.assertIn("Archivo SJR: scimagojr-2025.csv (año 2025)", sjr_file)
        self.assertNotIn("/home/u", sjr_file)

    def test_a_reversed_range_is_flagged_and_the_search_does_not_run(self) -> None:
        result = self.node("""
          window.JournalsPanel.state.form.from = 'Q3'; window.JournalsPanel.state.form.to = 'Q1';
          const html = P.formHtml(P.state);
          await click({ 'data-jp-action': 'search' });
          out({ html, calls: calls.length });""")
        self.assertIn("no puede ir después", result["html"])
        self.assertEqual(result["calls"], 0)

    def test_the_agent_command_and_the_search_body_follow_the_form(self) -> None:
        result = self.node("""
          const f = (patch) => ({ from: 'Q1', to: 'Q2', oaOnly: false, maxApc: '', maxReview: '', limit: '', ...patch });
          out({ plain: P.agentCommand(f({})), single: P.agentCommand(f({ to: 'Q1' })),
                full: P.agentCommand(f({ oaOnly: true, maxApc: '2000', maxReview: '180', limit: '10' })),
                junk: P.agentCommand(f({ maxApc: '-5', maxReview: 'x', limit: '99' })),
                body: P.searchBody(f({ oaOnly: true, maxApc: '2000', maxReview: '180', limit: '10' })),
                bare: P.searchBody(f({ from: 'Q3', to: 'Q4' })),
                forced: P.searchBody(f({ noCache: true })), forcedCommand: P.agentCommand(f({ noCache: true })) });""")
        self.assertEqual(result["plain"], "/journal-finder Q1-Q2")
        self.assertEqual(result["single"], "/journal-finder Q1")
        self.assertEqual(result["full"], "/journal-finder Q1-Q2 --oa-only --max-apc 2000 --max-review-days 180 --limit 10")
        self.assertEqual(result["junk"], "/journal-finder Q1-Q2")
        self.assertEqual(result["body"], {"quartiles": "Q1-Q2", "oa_only": True, "max_apc": 2000,
                                          "max_review_days": 180, "limit": 10})
        self.assertEqual(result["bare"], {"quartiles": "Q3-Q4", "oa_only": False})
        self.assertEqual(result["forced"], {"quartiles": "Q1-Q2", "oa_only": False, "no_cache": True})
        # The skill's usage has no --no-cache flag, so the agent command never carries it.
        self.assertEqual(result["forcedCommand"], "/journal-finder Q1-Q2")

    # -- the venue card -------------------------------------------------------
    VENUE_JS = """
      const evil = '<script>alert(1)</script>';
      const detail = {
        ok: true, slug: 'eswa', pdf: true,
        status: { slug: 'eswa', state: 'planned', blockers: 1, audit_stale: false, build_stale: false,
          steps: ['selected','requirements','template','audited','planned','approved','built','compiled']
            .map((step, i) => ({ step, done: i < 5 && step !== 'approved' })) },
        venue: { journal: { name: 'Expert Systems <b>with</b> Applications', homepage_url: 'https://example.org/j' }, quartile: 'Q1' },
        requirements: { guidelines_urls: ['https://example.org/guide', 'javascript:alert(1)'] },
        template: { kind: 'texlive', class: 'elsarticle' },
        audit: { findings: [
          { id: 'over-limit:abstract_words', severity: 'blocker', message: 'abstract <i>too long</i>', blocks: ['abstract.slot-1'],
            smith: { words: 260 }, venue: { quote: evil, url: 'https://example.org/guide', max: 250 }, resolved_by: 'text-change' },
          { id: 'extra-section:x', severity: 'minor', message: 'm', smith: {}, venue: { quote: null, url: 'javascript:alert(2)' },
            resolved_by: 'operator-decision' },
          { id: 'reference-style-mismatch:reference-style', severity: 'major', message: 'm', smith: { bst: 'ieeetr' },
            venue: { quote: 'Use elsarticle-num', url: 'https://example.org/bst', bst: 'elsarticle-num' }, resolved_by: 'build' }] },
        plan: { text: '# Plan\\n- [over-limit:abstract_words] ' + evil, sha256: 'a'.repeat(64) },
        approval: null };
      const base = { venues: [{ slug: 'eswa', journal: 'Expert Systems' }, { slug: 'other', journal: 'Other' }], slug: 'eswa',
        detail, pdfView: 'canonical', busy: {}, statement: 'I <b>agree</b>', note: '', form: {} };
    """

    def test_the_venue_card_renders_state_audit_plan_and_actions_in_spanish(self) -> None:
        html = self.node(self.VENUE_JS + "out(P.venueHtml(base));")
        for expected in (
            "elegida", "requisitos", "plantilla", "auditada", "construida", "compilada", "Siguiente:",
            "Leer el plan y aprobarlo, o pedir cambios.", "Hallazgos de la auditoría", "bloqueante", "mayor", "menor",
            "cambio de texto", "decisión del operador", "construcción de la revista", "fuente",
            "Plan de ajuste", "Aprobar plan", "Pedir cambios", "Analizar plantilla con agente",
            "Aplicar plan con agente", "Construir y compilar versión de la revista", "PDF canónico", "PDF de la revista",
            "Tu aprobación, con tus propias palabras", "Cambios que quieres en el plan", "Normas para autores",
            "Plantilla: texlive elsarticle", "over-limit:abstract_words", 'data-jp-sha="' + "a" * 64 + '"',
            "words:", "max:", "Use elsarticle-num", "https://example.org/guide",
        ):
            self.assertIn(expected, html)
        self.assertIn("I &lt;b&gt;agree&lt;/b&gt;", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertNotIn("<script", html)
        self.assertNotIn("javascript:", html)
        self.assert_only_known_markup(html)

    def test_apply_needs_an_approval_bound_to_the_current_plan(self) -> None:
        pending, approved, stale = self.node(self.VENUE_JS + """
          const apply = (d) => P.venueHtml({ ...base, detail: d });
          out([apply(detail),
               apply({ ...detail, approval: { valid: true, via: 'dashboard', approved_at: '2026-10-31T10:00:00+00:00', statement: 'ok <b>go</b>' } }),
               apply({ ...detail, approval: { valid: false, plan_sha256: 'b'.repeat(64) } })]);""")
        self.assertRegex(pending, r'data-jp-action="venue-apply"[^>]*disabled')
        self.assertNotRegex(approved, r'data-jp-action="venue-apply"[^>]*disabled')
        self.assertIn("Aprobado vía dashboard el 2026-10-31T10:00:00+00:00: “ok &lt;b&gt;go&lt;/b&gt;”", approved)
        self.assertNotIn('data-jp-action="approve"', approved)
        self.assertIn("aprobación de un plan anterior", stale)
        self.assertIn('data-jp-action="approve"', stale)

    def test_the_next_action_follows_the_state_machine(self) -> None:
        result = self.node("""
          const steps = (upto, skip) => ['selected','requirements','template','audited','planned','approved','built','compiled']
            .map((step, i) => ({ step, done: i < upto && step !== skip }));
          out({ fresh: P.nextAction({ steps: steps(1) }), noTemplate: P.nextAction({ steps: steps(2) }),
                noAudit: P.nextAction({ steps: steps(3) }),
                stale: P.nextAction({ steps: steps(4), audit_stale: true, blockers: 0 }),
                needPlan: P.nextAction({ steps: steps(4), blockers: 2 }),
                needApproval: P.nextAction({ steps: steps(5), blockers: 2 }),
                cleanBuild: P.nextAction({ steps: steps(4), blockers: 0 }),
                approvedBuild: P.nextAction({ steps: steps(6), blockers: 2 }),
                rebuild: P.nextAction({ steps: steps(7), blockers: 0, build_stale: true }),
                compile: P.nextAction({ steps: steps(7), blockers: 0 }),
                done: P.nextAction({ steps: steps(8), blockers: 0 }) });""")
        self.assertEqual(result, {
            "fresh": "analyze", "noTemplate": "analyze", "noAudit": "analyze", "stale": "analyze",
            "needPlan": "plan", "needApproval": "approve", "cleanBuild": "build", "approvedBuild": "build",
            "rebuild": "rebuild", "compile": "compile", "done": "done"})

    def test_no_venue_and_a_clean_audit_have_their_own_texts(self) -> None:
        none, clean = self.node("""
          out([P.venueHtml({ venues: [], busy: {} }), P.auditHtml({ findings: [] })]);""")
        self.assertIn("Todavía no hay revista elegida", none)
        self.assertIn("Sin hallazgos", clean)

    # -- behaviour ------------------------------------------------------------
    def test_search_posts_the_filters_then_reloads_the_candidates(self) -> None:
        result = self.node(self.candidates_js() + """
          __routes.push(['POST', '/api/journals/search', { status: 200, body: { ok: true, candidates: [1, 2, 3] } }]);
          __routes.push(['GET', '/api/journals', { status: 200, body: { ok: true, candidates: doc, sjr: null } }]);
          const s = P.state; s.form = { from: 'Q1', to: 'Q2', oaOnly: true, maxApc: '', maxReview: '', limit: '5' };
          await click({ 'data-jp-action': 'search' });
          out({ calls: calls.map((c) => [c.method, c.url, c.body]), message: s.message, html: host.innerHTML.slice(0, 400),
                names: s.journals.candidates.candidates.length });""")
        self.assertEqual(result["calls"][0], ["POST", "/api/journals/search",
                                              json.dumps({"quartiles": "Q1-Q2", "oa_only": True, "limit": 5}, separators=(",", ":"))])
        self.assertEqual(result["calls"][1][:2], ["GET", "/api/journals"])
        self.assertEqual(result["message"], {"kind": "ok", "text": "Búsqueda terminada: 3 revistas."})
        self.assertEqual(result["names"], 5)

    def test_a_failed_search_shows_the_code_and_message_escaped(self) -> None:
        result = self.node("""
          __routes.push(['POST', '/api/journals/search', { status: 502, body: { ok: false, error: 'NETWORK_UNAVAILABLE', message: '<b>down</b>' } }]);
          await click({ 'data-jp-action': 'search' });
          out({ html: host.innerHTML, busy: P.state.busy.search });""")
        self.assertIn("La búsqueda falló: NETWORK_UNAVAILABLE: &lt;b&gt;down&lt;/b&gt;", result["html"])
        self.assertFalse(result["busy"])

    def test_force_refresh_sends_no_cache_and_the_checkbox_is_remembered(self) -> None:
        result = self.node("""
          __routes.push(['POST', '/api/journals/search', { status: 200, body: { ok: true, candidates: [] } }]);
          __routes.push(['GET', '/api/journals', { status: 200, body: { ok: true, candidates: null, sjr: null } }]);
          await field({ 'data-jp-field': 'noCache' }, { checked: true }, 'change');
          const formHtml = P.formHtml(P.state);
          await click({ 'data-jp-action': 'search' });
          out({ body: JSON.parse(calls.find((c) => c.method === 'POST').body), formHtml });""")
        self.assertEqual(result["body"], {"quartiles": "Q1-Q2", "oa_only": False, "limit": 15, "no_cache": True})
        self.assertIn('data-jp-field="noCache" checked', result["formHtml"])

    def test_a_spent_openalex_quota_reaches_the_operator_with_the_key_name(self) -> None:
        html = self.node("""
          const message = 'OpenAlex could not be reached: HTTP 429; set OPENALEX_API_KEY (a free key has its own daily budget) or wait for the reset';
          __routes.push(['POST', '/api/journals/search', { status: 502, body: { ok: false, error: 'NETWORK_UNAVAILABLE', message } }]);
          await click({ 'data-jp-action': 'search' });
          out(host.innerHTML);""")
        self.assertIn("La búsqueda falló: NETWORK_UNAVAILABLE: OpenAlex could not be reached", html)
        self.assertIn("OPENALEX_API_KEY", html)

    def test_analyze_with_agent_sends_the_slash_command_to_the_console(self) -> None:
        sent = self.node("""
          P.state.form = { from: 'Q1', to: 'Q2', oaOnly: true, maxApc: '2000', maxReview: '180', limit: '10' };
          await click({ 'data-jp-action': 'analyze' });
          out(sent);""")
        self.assertEqual(sent, [{"text": "/journal-finder Q1-Q2 --oa-only --max-apc 2000 --max-review-days 180 --limit 10",
                                 "run": True, "options": {"kind": "slash"}}])

    def test_the_sjr_upload_posts_the_raw_file_with_its_name_and_year(self) -> None:
        result = self.node("""
          __routes.push(['POST', '/api/journals/sjr', { status: 200, body: { ok: true, rows: 31000, year: 2024 } }]);
          __routes.push(['GET', '/api/journals', { status: 200, body: { ok: true, candidates: null, sjr: { file: '/c/scimagojr-2024.csv', year: 2024 } } }]);
          await field({ 'data-jp-field': 'sjrYear' }, { value: '2024' });
          const file = { name: 'scimagojr 2024.csv' };
          await field({ 'data-jp-field': 'sjrFile' }, { files: [file] }, 'change');
          out({ post: calls.find((c) => c.method === 'POST'), same: calls.find((c) => c.method === 'POST').body === file,
                message: P.state.sjrMessage });""")
        self.assertEqual(result["post"]["url"], "/api/journals/sjr?name=scimagojr%202024.csv&year=2024")
        self.assertTrue(result["same"])
        self.assertEqual(result["message"]["text"], "Archivo SJR importado: 31000 revistas, año 2024.")

    def test_choosing_a_journal_selects_the_venue_and_opens_its_card(self) -> None:
        result = self.node(self.VENUE_JS + """
          __routes.push(['POST', '/api/venues/select', { status: 200, body: { ok: true, slug: 'eswa', journal: 'Expert Systems', via: 'candidate' } }]);
          __routes.push(['GET', '/api/venues/eswa', { status: 200, body: detail }]);
          __routes.push(['GET', '/api/venues', { status: 200, body: { ok: true, venues: base.venues } }]);
          await click({ 'data-jp-action': 'select', 'data-jp-id': 'https://openalex.org/S1001' });
          out({ calls: calls.map((c) => [c.method, c.url, c.body]), slug: P.state.slug, html: host.innerHTML.includes('Aprobar plan') });""")
        self.assertEqual(result["calls"][0], ["POST", "/api/venues/select", json.dumps({"candidate": "https://openalex.org/S1001"}, separators=(",", ":"))])
        self.assertEqual(result["slug"], "eswa")
        self.assertTrue(result["html"])

    def test_a_failed_selection_is_reported_with_the_refusal_code(self) -> None:
        message = self.node("""
          __routes.push(['POST', '/api/venues/select', { status: 404, body: { ok: false, code: 'CANDIDATE_UNKNOWN', detail: 'no candidate' } }]);
          await click({ 'data-jp-action': 'select', 'data-jp-id': 'S9' });
          out(P.state.message);""")
        self.assertEqual(message["kind"], "bad")
        self.assertIn("CANDIDATE_UNKNOWN: no candidate", message["text"])

    def test_the_agent_buttons_name_the_slug_and_the_venue_adapter_steps(self) -> None:
        sent = self.node(self.VENUE_JS + """
          Object.assign(P.state, { venues: base.venues, slug: 'eswa', detail });
          await click({ 'data-jp-action': 'venue-analyze' });
          await click({ 'data-jp-action': 'venue-apply', 'data-jp-sha': 'a'.repeat(64) });
          out(sent);""")
        analyze, apply = sent
        self.assertTrue(analyze["run"] and analyze["options"] == {"kind": "slash"})
        for needle in ('"eswa"', "venue-adapter", "venue requirements", "venue acquire", "venue diff", "venue plan",
                       "requirements.json", "quote and url", "never submit"):
            self.assertIn(needle, analyze["text"].replace("Never submit", "never submit").replace("Never edit", "never edit"))
        self.assertNotIn("\n", analyze["text"])
        for needle in ('"eswa"', "paper/venues/eswa/plan.md", "a" * 64, "write loop", "redactor", "contract-auditor",
                       "venue diff --slug eswa"):
            self.assertIn(needle, apply["text"])
        self.assertNotIn("\n", apply["text"])
        self.assertTrue(analyze["text"].startswith("/paper-writing") and apply["text"].startswith("/paper-writing"))

    def test_request_changes_sends_the_note_and_needs_one(self) -> None:
        result = self.node(self.VENUE_JS + """
          Object.assign(P.state, { venues: base.venues, slug: 'eswa', detail });
          await click({ 'data-jp-action': 'changes' });
          const before = sent.length;
          await field({ 'data-jp-field': 'note' }, { value: 'Keep the abstract.\\nMove methods up.' });
          await click({ 'data-jp-action': 'changes' });
          out({ before, sent, note: P.state.note });""")
        self.assertEqual(result["before"], 0)
        (message,) = result["sent"]
        self.assertIn('"eswa"', message["text"])
        self.assertIn("Keep the abstract. Move methods up.", message["text"])
        self.assertIn("venue plan --slug eswa", message["text"])
        self.assertNotIn("\n", message["text"])
        self.assertEqual(result["note"], "")

    def test_approve_posts_the_statement_with_the_plan_hash_and_needs_words(self) -> None:
        result = self.node(self.VENUE_JS + """
          Object.assign(P.state, { venues: base.venues, slug: 'eswa', detail, statement: '' });
          __routes.push(['POST', '/api/venues/eswa/approve', { status: 200, body: { ok: true, via: 'dashboard' } }]);
          __routes.push(['GET', '/api/venues/eswa', { status: 200, body: detail }]);
          __routes.push(['GET', '/api/venues', { status: 200, body: { ok: true, venues: base.venues } }]);
          await click({ 'data-jp-action': 'approve', 'data-jp-sha': 'a'.repeat(64) });
          const empty = calls.filter((c) => c.method === 'POST').length;
          await field({ 'data-jp-field': 'statement' }, { value: 'I read it and agree.' });
          await click({ 'data-jp-action': 'approve', 'data-jp-sha': 'a'.repeat(64) });
          out({ empty, posts: calls.filter((c) => c.method === 'POST').map((c) => [c.url, JSON.parse(c.body)]) });""")
        self.assertEqual(result["empty"], 0)
        self.assertEqual(result["posts"], [["/api/venues/eswa/approve",
                                            {"statement": "I read it and agree.", "plan_sha256": "a" * 64}]])

    def test_a_refused_approval_shows_the_code(self) -> None:
        message = self.node(self.VENUE_JS + """
          Object.assign(P.state, { venues: base.venues, slug: 'eswa', detail, statement: 'ok' });
          __routes.push(['POST', '/api/venues/eswa/approve', { status: 409, body: { ok: false, code: 'PLAN_HASH_MISMATCH', detail: 'changed' } }]);
          __routes.push(['GET', '/api/venues', { status: 200, body: { ok: true, venues: base.venues } }]);
          await click({ 'data-jp-action': 'approve', 'data-jp-sha': 'a'.repeat(64) });
          out(P.state.message);""")
        self.assertEqual(message["kind"], "bad")
        self.assertIn("PLAN_HASH_MISMATCH: changed", message["text"])

    def test_build_and_compile_run_in_order_and_switch_to_the_venue_pdf(self) -> None:
        result = self.node(self.VENUE_JS + """
          Object.assign(P.state, { venues: base.venues, slug: 'eswa', detail });
          __routes.push(['POST', '/api/venues/eswa/build', { status: 200, body: { ok: true, compile_env: {} } }]);
          __routes.push(['POST', '/api/paper/compile', { status: 200, body: { ok: true, message: 'paper/venues/eswa/main.pdf compiled (4 pages).' } }]);
          __routes.push(['GET', '/api/venues/eswa', { status: 200, body: { ...detail, pdf: true } }]);
          __routes.push(['GET', '/api/venues', { status: 200, body: { ok: true, venues: base.venues } }]);
          await click({ 'data-jp-action': 'build' });
          out({ posts: calls.filter((c) => c.method === 'POST').map((c) => c.url), pdf, view: P.state.pdfView,
                message: P.state.message });""")
        self.assertEqual(result["posts"], ["/api/venues/eswa/build", "/api/paper/compile?venue=eswa"])
        self.assertEqual(result["pdf"], ["eswa"])
        self.assertEqual(result["view"], "venue")
        self.assertIn("4 pages", result["message"]["text"])

    def test_a_refused_build_does_not_compile(self) -> None:
        result = self.node(self.VENUE_JS + """
          Object.assign(P.state, { venues: base.venues, slug: 'eswa', detail });
          __routes.push(['POST', '/api/venues/eswa/build', { status: 409, body: { ok: false, code: 'PLAN_NOT_APPROVED', detail: 'no approved plan' } }]);
          __routes.push(['GET', '/api/venues/eswa', { status: 200, body: detail }]);
          __routes.push(['GET', '/api/venues', { status: 200, body: { ok: true, venues: base.venues } }]);
          await click({ 'data-jp-action': 'build' });
          out({ posts: calls.filter((c) => c.method === 'POST').map((c) => c.url), message: P.state.message, pdf });""")
        self.assertEqual(result["posts"], ["/api/venues/eswa/build"])
        self.assertIn("PLAN_NOT_APPROVED: no approved plan", result["message"]["text"])
        self.assertEqual(result["pdf"], [])

    def test_the_pdf_toggle_switches_the_viewer_and_the_venue_option_needs_a_pdf(self) -> None:
        result = self.node(self.VENUE_JS + """
          Object.assign(P.state, { venues: base.venues, slug: 'eswa', detail });
          await click({ 'data-jp-action': 'pdf', 'data-jp-view': 'venue' });
          const afterVenue = [...pdf];
          await click({ 'data-jp-action': 'pdf', 'data-jp-view': 'canonical' });
          out({ afterVenue, pdf, without: P.venueHtml({ ...base, detail: { ...detail, pdf: false } }) });""")
        self.assertEqual(result["afterVenue"], ["eswa"])
        self.assertEqual(result["pdf"], ["eswa", None])
        self.assertRegex(result["without"], r'data-jp-view="venue"[^>]*disabled')

    def test_changing_the_language_redraws_the_panel(self) -> None:
        before, after = self.node("""
          const before = host.innerHTML;
          window.i18n.setLanguage('en');
          docListeners.languagechange();
          out([before, host.innerHTML]);""")
        self.assertIn("Buscar revistas", before)
        self.assertIn("Search journals", after)
        self.assertNotIn("Buscar revistas", after)

    # -- the page -------------------------------------------------------------
    def test_the_page_mounts_the_panel_between_the_banner_and_the_top_bar(self) -> None:
        banner = PAGE.index('id="linkPdfDirect"')
        mount = PAGE.index('id="journalsPanel"')
        topbar = PAGE.index('<div class="pdf-viewer-topbar">')
        self.assertLess(banner, mount)
        self.assertLess(mount, topbar)
        self.assertIn('<script src="./journals-panel.js?v=0.46.0"></script>', PAGE)

    def test_the_pdf_viewer_follows_the_venue_toggle(self) -> None:
        self.assertIn("window.setPdfVenue = setPdfVenue;", PAGE)
        self.assertIn("&venue=${encodeURIComponent(pdfVenueSlug)}", PAGE)
        self.assertIn("pdfUrl(`v=${forceReload ? (lastPdfToken || Date.now()) : 'doc'}`)", PAGE)
        # The canonical viewer lines other tests pin stay as they were.
        self.assertIn("native.src = `/api/pdf?v=${token}`;", PAGE)


if __name__ == "__main__":
    unittest.main()
