"""Which references the paper cites that the SOTA constellation does not draw.

The proposal cites pool references (.papersmith/citations.json); a reference a
later journal pass added to the pool can be cited before any system draws it.
The manuscript cites refs.bib entries; one with no system is drawn only as a
placeholder of the "Manuscript Citations" family, built from its BibTeX entry
without an abstract. `smith atlas coverage` lists both, so the flow can resolve
their abstracts, add them to the pool and draw them with the sota-grapher."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from skills._core.command_center import atlas_coverage, atlas_reference, server

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests" / "fixtures" / "atlas_manuscript"


def workspace(test: unittest.TestCase, *, complete: bool = False) -> Path:
    root = Path(tempfile.mkdtemp())
    test.addCleanup(shutil.rmtree, root, True)
    shutil.copytree(FIXTURE / "sota-pool", root / "sota-pool")
    pool_path = root / "sota-pool" / "candidates.json"
    pool = json.loads(pool_path.read_text(encoding="utf-8"))
    listed = pool["candidates"] if isinstance(pool, dict) else pool
    listed.append({"identifier": "10.1000/d", "title": "Unseen method", "year": 2025})
    pool_path.write_text(json.dumps(pool), encoding="utf-8")
    (root / ".papersmith").mkdir()
    cited = ["arXiv:2401.00001"] if complete else ["arXiv:2401.00001", "10.1000/D"]
    (root / ".papersmith" / "citations.json").write_text(json.dumps(
        {"schema": 1, "ideas": {"pillar:C1": [{"id": i, "why": "w"} for i in cited]}}), encoding="utf-8")
    extra = [] if complete else [
        {"cite_key": "kin2025", "identifier": "10.1000/d", "title": "Unseen method"},
        {"cite_key": "far2020", "identifier": None, "title": "A paper the pool never saw"}]
    (root / "sota-pool" / "atlas.manuscript.json").write_text(json.dumps(
        {"schema": "papersmith.atlas-manuscript/v1", "systems": [], "extra_systems": extra,
         "summary": {"extra_cited": len(extra)}}), encoding="utf-8")
    return root


class CoverageTests(unittest.TestCase):
    def test_it_lists_what_the_proposal_and_the_manuscript_leave_out(self) -> None:
        found = atlas_coverage.coverage(workspace(self))
        self.assertFalse(found["complete"])
        self.assertEqual(found["proposal"], {"cited": 2, "undrawn": ["10.1000/D"]})
        self.assertEqual(found["manuscript"]["placeholders"], [
            {"cite_key": "kin2025", "identifier": "10.1000/d", "title": "Unseen method", "in_pool": True},
            {"cite_key": "far2020", "identifier": "", "title": "A paper the pool never saw", "in_pool": False}])

    def test_a_drawn_paper_is_complete(self) -> None:
        found = atlas_coverage.coverage(workspace(self, complete=True))
        self.assertTrue(found["complete"])
        self.assertEqual((found["proposal"]["undrawn"], found["manuscript"]["placeholders"]), ([], []))

    def test_a_workspace_without_a_constellation_is_not_complete(self) -> None:
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, True)
        found = atlas_coverage.coverage(root)
        self.assertEqual((found["complete"], found["atlas"]), (False, False))

    def test_the_cli_reports_and_exits_one_until_complete(self) -> None:
        for complete, code in ((False, 1), (True, 0)):
            with self.subTest(complete=complete):
                done = subprocess.run([sys.executable, "-m", "skills._core.command_center.atlas_coverage",
                                       "--root", str(workspace(self, complete=complete))],
                                      capture_output=True, text=True, cwd=REPO)
                self.assertEqual(done.returncode, code, done.stderr)
                self.assertEqual(json.loads(done.stdout)["complete"], complete)

    def test_the_route_answers(self) -> None:
        client = TestClient(server.create_app(workspace(self), history_store=None))
        self.assertEqual(client.get("/api/atlas/coverage").json()["proposal"]["undrawn"], ["10.1000/D"])


class PlaceholderReferenceTests(unittest.TestCase):
    def test_a_citation_drawn_as_a_placeholder_still_opens_on_the_sky(self) -> None:
        root = workspace(self)
        merged = json.loads((root / "sota-pool" / "atlas.json").read_text(encoding="utf-8"))
        merged["systems"].append({"id": "far2020", "title": "A paper the pool never saw", "planets": [
            {"id": "sun", "slot": "sun", "label": "far2020 (2020)", "detail": "",
             "evidence": {"origin": "10.9999/far"}}]})
        (root / "sota-pool" / "atlas.with-manuscript.json").write_text(json.dumps(merged), encoding="utf-8")
        self.assertEqual(atlas_reference.reference(root, "10.9999/FAR")["system"]["key"], "far2020.sun")


class FlowTests(unittest.TestCase):
    def test_the_grapher_rebuilds_through_smith_so_manuscript_citations_stay_drawn(self) -> None:
        agent = (REPO / ".claude" / "agents" / "sota-grapher.md").read_text(encoding="utf-8")
        self.assertIn("smith atlas build .", agent)
        self.assertIn("smith atlas coverage .", agent)

    def test_each_phase_that_adds_a_reference_checks_the_constellation(self) -> None:
        for path in ("skills/proposal-deliberation/SKILL.md", "skills/experimental-deliberation/SKILL.md",
                     "skills/paper-writing/SKILL.md", "skills/plausibility/SKILL.md", "CLAUDE.md"):
            with self.subTest(path=path):
                self.assertIn("smith atlas coverage", (REPO / path).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
