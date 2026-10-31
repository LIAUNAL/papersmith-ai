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
        self.assertEqual(names, ["Expert Systems with Applications", "Journal Without Optional Fields"])
        first = body["candidates"]["candidates"][0]
        self.assertEqual(first["fit"]["cited_in_paper"], 0.5)
        self.assertEqual(first["flags"], ["no-application-evidence"])
        self.assertEqual(body["candidates"]["api_calls"], {"made": 42, "cached": 7})

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
                      {"max_review_days": 0}, {"max_review_days": 1.5}, {"oa_only": "yes"}):
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


if __name__ == "__main__":
    unittest.main()
