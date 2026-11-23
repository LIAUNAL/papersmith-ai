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
TEMPLATES = REPO / "src" / "papersmith" / "templates"
PLANNED_CATALOGUE = (
    "applied-ai", "review", "observational-measurement", "experiment-intervention", "qualitative-participatory",
    "hardware", "lab-simulation", "data-resource",
)
VARIANTS = {
    "observational-measurement": ["observational", "diagnostic-validation", "measurement-instrument"],
    "experiment-intervention": ["human-trial", "field-experiment"],
    "qualitative-participatory": ["qualitative-mixed", "consensus-foresight", "experience-report"],
    "lab-simulation": ["materials", "modelling-simulation"],
}


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


def missing_flow_templates(document: dict) -> list[str]:
    """The variant ``flow_template`` names with no file in the package's templates."""
    named = [v["flow_template"] for t in document["types"] for v in t.get("variants", [])
             if v.get("flow_template") is not None]
    return [name for name in named if not (TEMPLATES / name).is_file()]


class ShippedCatalogueTests(unittest.TestCase):
    def test_it_holds_the_planned_catalogue_in_order(self) -> None:
        self.assertEqual(tuple(t["id"] for t in registry.load()), PLANNED_CATALOGUE)

    def test_the_available_types_are_the_existing_paper_kinds(self) -> None:
        available = {t["id"]: t["line"] for t in registry.available()}
        self.assertEqual(available, {"applied-ai": "experimental", "review": "review",
                                     "observational-measurement": "observational-measurement",
                                     "hardware": "hardware", "lab-simulation": "lab-simulation"})
        self.assertEqual(set(available.values()), set(manifest.PAPER_KINDS))
        self.assertEqual(registry.by_line(manifest.DEFAULT_PAPER_KIND)["id"], "applied-ai")

    def test_every_type_is_complete_and_concise(self) -> None:
        for item in registry.load():
            with self.subTest(type=item["id"]):
                self.assertLessEqual(len(item["summary"]), registry.MAX_SUMMARY)
                self.assertTrue(item["stages"])
                self.assertTrue(registry.all_signals(item))
                for guideline in item["guidelines"]:
                    self.assertTrue(guideline["url"].startswith("https://"))

    def test_the_families_group_their_variants(self) -> None:
        found = {t["id"]: [v["id"] for v in t.get("variants", [])] for t in registry.load() if t.get("variants")}
        self.assertEqual(found, VARIANTS)
        for item in registry.load():
            with self.subTest(type=item["id"]):
                self.assertTrue(registry.all_signals(item))

    def test_every_variant_flow_template_is_a_shipped_template(self) -> None:
        # The registry ships to workspaces and checks only the name pattern;
        # the repository is where the template files can be seen.
        self.assertEqual(missing_flow_templates(json.loads(registry.CATALOGUE.read_text(encoding="utf-8"))), [])

    def test_a_missing_flow_template_is_caught(self) -> None:
        document = json.loads(registry.CATALOGUE.read_text(encoding="utf-8"))
        variants = next(t for t in document["types"] if t.get("variants"))["variants"]
        variants[0]["flow_template"] = "paper-flow-no-such-line.md.tpl"
        variants[1]["flow_template"] = "paper-flow-review.md.tpl"
        registry.validate(document)
        self.assertEqual(missing_flow_templates(document), ["paper-flow-no-such-line.md.tpl"])

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
        self.refuses([entry(signals=["survey", "survey"])], "repeat")

    def test_variants_are_validated(self) -> None:
        variant = {"id": "cohort", "name": "Cohort", "summary": "A cohort.", "guidelines": [], "signals": ["cohort"]}
        family = entry(signals=[], variants=[variant])
        self.assertEqual(registry.validate({"version": 2, "types": [family]})[0]["variants"][0]["id"], "cohort")
        self.refuses([entry(signals=[], variants=[{**variant, "signals": []}])], "signals")
        self.refuses([entry(signals=[], variants=[{**variant, "id": "Bad"}])], "variant id")
        self.refuses([entry(signals=["cohort"], variants=[variant])], "repeat")
        self.refuses([entry(id="observational", signals=[], variants=[{**variant, "id": "observational"}])], "duplicate")
        other = entry(id="other", signals=["cohort"])
        self.refuses([entry(signals=[], variants=[variant]), other], "also a signal")

    def test_guideline_urls_must_be_https(self) -> None:
        self.refuses([entry(guidelines=[{"name": "X", "url": "http://example.org"}])], "https")

    def test_the_document_shape_is_checked(self) -> None:
        with self.assertRaises(registry.RegistryError):
            registry.validate({"types": "nope"})


class SignalDiscriminationTests(unittest.TestCase):
    def test_no_signal_is_shared_by_two_types(self) -> None:
        # A shared signal scores two types alike and tells the advisor nothing (T2).
        owners: dict[str, list[str]] = {}
        for item in registry.load():
            for signal in registry.all_signals(item):
                owners.setdefault(signal, []).append(item["id"])
        self.assertEqual({s: ids for s, ids in owners.items() if len(ids) > 1}, {})


class CliTests(unittest.TestCase):
    def test_list_prints_the_catalogue(self) -> None:
        done = subprocess.run([sys.executable, "-m", "skills._core.paper_types.registry", "list"],
                              cwd=REPO, capture_output=True, text=True, check=False)
        self.assertEqual(done.returncode, 0, done.stderr)
        payload = json.loads(done.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual([t["id"] for t in payload["types"]], list(PLANNED_CATALOGUE))

    def test_usage_and_a_broken_catalogue_are_typed_refusals(self) -> None:
        import contextlib, io, tempfile
        from unittest import mock
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(registry.main(["nope"]), 2)
        self.assertEqual(json.loads(out.getvalue())["error"], "USAGE")
        with tempfile.TemporaryDirectory() as tmp:
            broken = Path(tmp) / "paper_types.json"
            broken.write_text("{not json", encoding="utf-8")
            out = io.StringIO()
            with mock.patch.object(registry, "CATALOGUE", broken), contextlib.redirect_stdout(out):
                self.assertEqual(registry.main(["list"]), 1)
        self.assertEqual(json.loads(out.getvalue())["error"], "CATALOGUE_INVALID")


if __name__ == "__main__":
    unittest.main()
