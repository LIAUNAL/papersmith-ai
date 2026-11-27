"""Placed figures measured against every built venue's layout (spec S2 of
`odd/tasks/venue-figures-and-content-tracking.md`).

`place` measures a figure against the canonical `paper/main.tex` layout and
refuses below 0.70 x its body size. A venue build (`venue build`) can use a
different body size and text width: the Elsevier fixture builds an
`elsarticle` preprint at 12 pt (text width 390 pt) from a 10 pt article
(345 pt). Here:

- `venue build` measures every figure the venue manuscript includes against
  the venue's own layout, and reports a figure below the venue floor (or
  wider than the venue text) as a finding in its output and in build.json,
  with the remedy; the build does not fail on it;
- `place` keeps its canonical gate and adds `venueWarnings`, one entry per
  built venue the figure fails, never a refusal;
- with no built venue, `place` prints exactly what it printed before.

Every case goes through the public verbs (`paper_cli.main`). The figure is
the `compliant` plot fixture of `test_paper_place.py` (7.5 pt ticks on a
~337 pt-wide figure), compiled at test time with `pdflatex`; the venue
scaffold is `test_paper_venue.py`'s. At 0.93\\textwidth its ticks print at
~7.15 pt in the 10 pt canonical paper (floor 7.0 pt) and at ~8.0 pt in the
12 pt venue (floor 8.4 pt); at full width they pass both.
"""
from __future__ import annotations

import json
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_paper_place import NO_PDFLATEX, PDFLATEX, _Compiled  # noqa: E402
from test_paper_venue import VenueCase, canonical_tex  # noqa: E402

COMPILED = _Compiled()

PLACE_KEYS = ["command", "figureId", "pdf", "provenance", "status"]
ALL_DECLARATIONS = ("author-contributions", "funding", "data-availability", "conflicts")


def tearDownModule() -> None:  # noqa: N802 (unittest hook)
    COMPILED.cleanup()


@unittest.skipUnless(PDFLATEX, NO_PDFLATEX)
class VenueFigurePrintSizeCase(VenueCase):
    def setUp(self) -> None:
        super().setUp()
        self.write_contracts(abstract_extent="**Extent** 200–240 words")
        (self.root / "sources").mkdir()

    # -- figures ---------------------------------------------------------------
    def provenance(self, **extra) -> Path:
        path = self.root / "sources" / f"provenance-{len(list((self.root / 'sources').iterdir()))}.json"
        path.write_text(json.dumps({"run": "campaign-7", **extra}), encoding="utf-8")
        return path

    def place(self, figure_id: str, **provenance) -> tuple:
        return self.run_cli(
            "place", "--paper", str(self.paper), "--figure-id", figure_id,
            "--pdf", str(COMPILED.pdf("compliant")), "--provenance", str(self.provenance(**provenance)),
        )

    def diagram(self, figure_id: str) -> None:
        figures = self.paper / "Figures"
        figures.mkdir(exist_ok=True)
        shutil.copy(COMPILED.pdf("compliant"), figures / f"{figure_id}.pdf")
        (figures / f"{figure_id}.tex").write_text("% diagram source\n", encoding="utf-8")
        (figures / f"{figure_id}.diagram.json").write_text(
            json.dumps({"figureId": figure_id, "widthFraction": 0.93}), encoding="utf-8")

    # -- venue -----------------------------------------------------------------
    def build(self, *includes: str) -> dict:
        """Build the Elsevier venue from a canonical manuscript whose results
        include `includes` (each `(width option, target)`)."""
        extra = "".join(f"\\includegraphics[{option}]{{{target}}}\n" for option, target in includes)
        self.write_canonical(canonical_tex(related=True, declarations=ALL_DECLARATIONS, results_extra=extra))
        self.audited(extras=[])
        return self.ok("build", "--slug", "eswa")

    def build_record(self) -> dict:
        return json.loads((self.venue_dir() / "build.json").read_text(encoding="utf-8"))


class VenueBuildMeasuresFiguresTests(VenueFigurePrintSizeCase):
    def test_a_figure_that_passes_canonical_but_not_the_12pt_venue_is_a_build_finding(self) -> None:
        code, placed = self.place("result", printedWidthFraction=0.93)
        self.assertEqual(code, 0, placed)
        self.assertEqual(sorted(placed), PLACE_KEYS, "no venue built yet: place output is unchanged")

        payload = self.build(("width=0.93\\textwidth", "Figures/result.pdf"))
        report = payload["figure_print"]
        self.assertEqual(report["layout"]["bodyPt"], 12.0)
        self.assertEqual(report["layout"]["textWidthPt"], 390.0)
        self.assertEqual(len(report["findings"]), 1, report)
        finding = report["findings"][0]
        self.assertEqual(finding["slug"], "eswa")
        self.assertEqual(finding["figure"], "paper/Figures/result.pdf")
        self.assertEqual(finding["kind"], "placed")
        self.assertEqual(finding["issues"], ["below-print-floor"])
        self.assertEqual(finding["minPrintedPt"], 8.4)
        self.assertLess(finding["smallestPrintedPt"], 8.4)
        self.assertIn("12 pt", finding["remedy"])
        self.assertIn("390", finding["remedy"])
        self.assertIn("8.4 pt", finding["remedy"])
        self.assertEqual(self.build_record()["figure_print"], report, "build.json carries the same report")

    def test_a_rendered_diagram_the_venue_includes_is_measured_too(self) -> None:
        self.diagram("pipeline")
        report = self.build(("width=0.93\\textwidth", "Figures/pipeline"))["figure_print"]
        self.assertEqual([(f["figure"], f["kind"], f["issues"]) for f in report["findings"]],
                         [("paper/Figures/pipeline.pdf", "diagram", ["below-print-floor"])])
        self.assertIn("diagram", report["findings"][0]["remedy"])

    def test_a_figure_wider_than_the_venue_text_is_a_finding(self) -> None:
        self.assertEqual(self.place("wide", printedWidthFraction=1.0)[0], 0)
        report = self.build(("width=420pt", "Figures/wide.pdf"))["figure_print"]
        self.assertEqual([(f["figure"], f["issues"]) for f in report["findings"]],
                         [("paper/Figures/wide.pdf", ["wider-than-text"])])
        self.assertIn("390", report["findings"][0]["remedy"])

    def test_a_figure_that_passes_both_layouts_has_no_finding(self) -> None:
        self.assertEqual(self.place("result", printedWidthFraction=1.0)[0], 0)
        report = self.build(("width=\\textwidth", "Figures/result.pdf"))["figure_print"]
        self.assertEqual(report["findings"], [])
        self.assertEqual([(m["figure"], m["verdict"]) for m in report["measured"]],
                         [("paper/Figures/result.pdf", "pass")])
        self.assertEqual(self.build_record()["figure_print"]["findings"], [])


class PlaceWarnsPerBuiltVenueTests(VenueFigurePrintSizeCase):
    def test_place_warns_for_a_built_venue_the_figure_fails_and_still_places_it(self) -> None:
        self.build()
        code, payload = self.place("result", printedWidthFraction=0.93)
        self.assertEqual(code, 0, payload)
        self.assertEqual(payload["status"], "ok")
        self.assertTrue((self.paper / "Figures" / "result.pdf").is_file(), "a warning never refuses")
        self.assertEqual([(w["slug"], w["issues"]) for w in payload["venueWarnings"]],
                         [("eswa", ["below-print-floor"])])
        self.assertIn("12 pt", payload["venueWarnings"][0]["remedy"])

    def test_a_figure_that_passes_every_built_venue_has_no_warning(self) -> None:
        self.build()
        code, payload = self.place("result", printedWidthFraction=1.0)
        self.assertEqual(code, 0, payload)
        self.assertEqual(payload["venueWarnings"], [])

    def test_the_canonical_gate_still_refuses_with_a_built_venue(self) -> None:
        self.build()
        code, payload = self.place("result", printedWidthFraction=0.5)
        self.assertEqual(code, 2, payload)
        self.assertEqual(payload["code"], "FIGURE_TEXT_BELOW_PRINT_FLOOR")

    def test_no_built_venue_means_no_warning_and_the_same_output(self) -> None:
        self.selected()  # a venue that was never built does not count
        code, payload = self.place("result", printedWidthFraction=0.93)
        self.assertEqual(code, 0, payload)
        self.assertEqual(sorted(payload), PLACE_KEYS)


if __name__ == "__main__":
    unittest.main()
