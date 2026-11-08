"""A cited SOTA reference opens on the 3D constellation.

Every citation the panels show is a button. Clicking it opens the Graph
Atlas, asks the atlas page to centre and highlight the reference's system, and
shows a card with what the constellation knows about it: its topic, problem,
application, family, novelty, contributions, results and conclusions. A
reference the constellation does not draw still shows its pool record."""

from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from skills._core.command_center import atlas_reference, server
from tests.test_sota_citations import PANELS, cite_everything, render_panels  # noqa: F401

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests" / "fixtures" / "atlas_manuscript"
STATIC = Path(server.__file__).resolve().parent / "static"
PAGE = (STATIC / "index.html").read_text(encoding="utf-8")


def workspace(test: unittest.TestCase) -> Path:
    root = Path(tempfile.mkdtemp())
    test.addCleanup(shutil.rmtree, root, True)
    shutil.copytree(FIXTURE / "sota-pool", root / "sota-pool")
    atlas = json.loads((root / "sota-pool" / "atlas.json").read_text(encoding="utf-8"))
    atlas["systems"][0]["planets"] += [
        {"id": "prob", "slot": "problem", "label": "Pooling loses rare events", "detail": "Mean pooling hides spikes.",
         "evidence": {"origin": "arXiv:2401.00001"}},
        {"id": "nov", "slot": "novelty", "label": "Learned attention pooling", "detail": "",
         "evidence": {"origin": "arXiv:2401.00001"}},
        {"id": "ta", "slot": "topic_app", "label": "EEG screening", "detail": "",
         "evidence": {"origin": "arXiv:2401.00001"}},
    ]
    (root / "sota-pool" / "atlas.json").write_text(json.dumps(atlas), encoding="utf-8")
    return root


class ReferenceTests(unittest.TestCase):
    def test_a_cited_reference_resolves_to_its_system_and_slots(self) -> None:
        found = atlas_reference.reference(workspace(self), "arXiv:2401.00001")
        self.assertEqual(found["record"]["title"], "Attention pooling")
        self.assertEqual(found["system"]["id"], "sys-a")
        self.assertEqual(found["system"]["key"], "sys-a.sun")
        self.assertEqual(found["system"]["slots"]["problem"],
                         [{"label": "Pooling loses rare events", "detail": "Mean pooling hides spikes."}])
        self.assertEqual(found["system"]["slots"]["novelty"][0]["label"], "Learned attention pooling")
        self.assertEqual(found["system"]["slots"]["topic_app"][0]["label"], "EEG screening")

    def test_an_identifier_matches_whatever_form_the_atlas_wrote(self) -> None:
        root = workspace(self)
        for ident in ("10.1000/B", "https://doi.org/10.1000/b", "doi:10.1000/b"):
            with self.subTest(ident=ident):
                self.assertEqual(atlas_reference.reference(root, ident)["system"]["id"], "sys-b")

    def test_a_reference_the_constellation_does_not_draw_keeps_its_pool_record(self) -> None:
        root = workspace(self)
        path = root / "sota-pool" / "candidates.json"
        pool = json.loads(path.read_text(encoding="utf-8"))
        listed = pool["candidates"] if isinstance(pool, dict) else pool
        listed.append({"identifier": "10.1000/d", "title": "Unseen method", "year": 2025})
        path.write_text(json.dumps(pool), encoding="utf-8")
        found = atlas_reference.reference(root, "10.1000/D")
        self.assertIsNone(found["system"])
        self.assertEqual((found["record"]["title"], found["record"]["year"]), ("Unseen method", 2025))

    def test_a_workspace_without_an_atlas_answers_without_failing(self) -> None:
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, True)
        self.assertEqual(atlas_reference.reference(root, "10.1000/x"),
                         {"id": "10.1000/x", "record": {}, "system": None})

    def test_the_route_answers_and_refuses_a_missing_id(self) -> None:
        client = TestClient(server.create_app(workspace(self), history_store=None))
        body = client.get("/api/atlas/reference", params={"id": "arXiv:2401.00001"}).json()
        self.assertEqual(body["system"]["id"], "sys-a")
        self.assertEqual(client.get("/api/atlas/reference").status_code, 400)


class AtlasPageTests(unittest.TestCase):
    def page(self) -> str:
        spec = importlib.util.spec_from_file_location(
            "render_atlas_for_reference", REPO / "skills" / "plausibility" / "scripts" / "render_atlas.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        atlas = json.loads((FIXTURE / "sota-pool" / "atlas.json").read_text(encoding="utf-8"))
        return module.render(atlas)

    def test_the_atlas_focuses_a_known_key_and_says_so(self) -> None:
        page = self.page()
        self.assertIn("data.command === 'focus'", page)
        self.assertIn("PLANETS.has(data.key)", page)
        self.assertIn("type: 'atlas-focused'", page)


class DashboardTests(unittest.TestCase):
    def test_every_citation_is_a_button_to_the_constellation(self) -> None:
        script = (STATIC / "citations.js").read_text(encoding="utf-8")
        self.assertIn('class="cite-link" data-atlas-ref="${esc(c.id)}"', script)

    def test_the_page_loads_the_reference_card_and_its_runtime(self) -> None:
        self.assertRegex(PAGE, r'<script src="\./atlas-reference\.js\?v=[0-9.]+"></script>')
        self.assertIn('id="atlasReferenceCard"', PAGE)
        runtime = (STATIC / "atlas-reference.js").read_text(encoding="utf-8")
        for needle in ("/api/atlas/reference", "command: 'focus'", "'atlas-focused'", "navigateTab('atlas')",
                       "switchGraph('atlas')"):
            with self.subTest(needle=needle):
                self.assertIn(needle, runtime)


if __name__ == "__main__":
    unittest.main()
