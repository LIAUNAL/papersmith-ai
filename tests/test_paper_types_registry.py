"""The paper-type catalogue (paper-type-lines S2): one data file every consumer
reads -- the type advisor, the Paper type panel, plausibility and the docs.
The loader validates it, so a malformed catalogue refuses instead of drawing a
half-empty panel."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from papersmith.core import manifest
from skills._core.paper_types import registry

REPO = Path(__file__).resolve().parents[1]
PLANNED_CATALOGUE = (
    "applied-ai", "review", "observational", "intervention", "qualitative-mixed",
    "diagnostic-validation", "lab-measurement", "computational", "data-resource", "composite-index",
)


def entry(**overrides) -> dict:
    base = {
        "id": "observational", "name": "Observational study", "status": "planned", "line": None,
        "summary": "A study of a population, territory or dataset as it is.",
        "novelty": "The population or dataset studied.",
        "stages": ["Question", "Sampling", "Analysis"],
        "guidelines": [{"name": "STROBE", "url": "https://www.equator-network.org/reporting-guidelines/strobe/"}],
        "signals": ["survey", "cohort"],
    }
    return {**base, **overrides}


class ShippedCatalogueTests(unittest.TestCase):
    def test_it_holds_the_planned_catalogue_in_order(self) -> None:
        self.assertEqual(tuple(t["id"] for t in registry.load()), PLANNED_CATALOGUE)

    def test_the_available_types_are_the_existing_paper_kinds(self) -> None:
        available = {t["id"]: t["line"] for t in registry.available()}
        self.assertEqual(available, {"applied-ai": "experimental", "review": "review"})
        self.assertEqual(set(available.values()), set(manifest.PAPER_KINDS))
        self.assertEqual(registry.by_line(manifest.DEFAULT_PAPER_KIND)["id"], "applied-ai")

    def test_every_type_is_complete_and_concise(self) -> None:
        for item in registry.load():
            with self.subTest(type=item["id"]):
                self.assertLessEqual(len(item["summary"]), registry.MAX_SUMMARY)
                self.assertTrue(item["stages"])
                self.assertTrue(item["signals"])
                for guideline in item["guidelines"]:
                    self.assertTrue(guideline["url"].startswith("https://"))

    def test_get_names_an_unknown_type(self) -> None:
        self.assertEqual(registry.get("review")["line"], "review")
        with self.assertRaises(registry.RegistryError) as caught:
            registry.get("poetry")
        self.assertIn("poetry", str(caught.exception))


class ValidationTests(unittest.TestCase):
    def refuses(self, items, fragment: str) -> None:
        with self.assertRaises(registry.RegistryError) as caught:
            registry.validate({"version": 1, "types": items})
        self.assertIn(fragment, str(caught.exception))

    def test_a_valid_catalogue_passes(self) -> None:
        self.assertEqual(registry.validate({"version": 1, "types": [entry()]})[0]["id"], "observational")

    def test_duplicates_and_bad_ids_refuse(self) -> None:
        self.refuses([entry(), entry()], "duplicate")
        self.refuses([entry(id="Bad Id")], "id")

    def test_status_and_line_must_agree(self) -> None:
        self.refuses([entry(status="available", line=None)], "line")
        self.refuses([entry(status="planned", line="experimental")], "line")
        self.refuses([entry(status="maybe")], "status")

    def test_missing_fields_and_long_text_refuse(self) -> None:
        item = entry()
        del item["novelty"]
        self.refuses([item], "novelty")
        self.refuses([entry(summary="x" * (registry.MAX_SUMMARY + 1))], "summary")
        self.refuses([entry(signals=[])], "signals")
        self.refuses([entry(signals=["Survey"])], "signals")

    def test_guideline_urls_must_be_https(self) -> None:
        self.refuses([entry(guidelines=[{"name": "X", "url": "http://example.org"}])], "https")

    def test_the_document_shape_is_checked(self) -> None:
        with self.assertRaises(registry.RegistryError):
            registry.validate({"types": "nope"})


class CliTests(unittest.TestCase):
    def test_list_prints_the_catalogue(self) -> None:
        done = subprocess.run([sys.executable, "-m", "skills._core.paper_types.registry", "list"],
                              cwd=REPO, capture_output=True, text=True, check=False)
        self.assertEqual(done.returncode, 0, done.stderr)
        payload = json.loads(done.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual([t["id"] for t in payload["types"]], list(PLANNED_CATALOGUE))


if __name__ == "__main__":
    unittest.main()
