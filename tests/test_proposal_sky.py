"""The proposal's own sky: the SOTA constellation rebuilt with stage 3 in it.

`merge_proposal_sky.py` is held to the whole chain, not to its own output
text: the merged atlas must keep every SOTA system and link it was handed, must
pass `check_atlas.py` -- the constellation's single authority -- and must render
through `render_atlas.py` as one self-contained sky that names itself as the
proposal's. Its refusals are held to the overlay's own contract: three to five
contribution concepts, and a link that lands only on a planet that exists.

Stdlib only.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MERGER = REPO / "skills" / "proposal-deliberation" / "scripts" / "merge_proposal_sky.py"
CHECKER = REPO / "skills" / "plausibility" / "scripts" / "check_atlas.py"
RENDERER = REPO / "skills" / "plausibility" / "scripts" / "render_atlas.py"
DATA_OPEN = '<script type="application/json" id="atlas-data">'

ORBITS = {"sun": 0, "topic_app": 1, "topic_ai": 1, "problem": 1, "application": 1,
          "family": 2, "novelty": 1, "contribution": 1, "result": 3, "conclusion": 3}
BASE_SLOTS = ["sun", "topic_app", "topic_ai", "problem", "application", "novelty",
              "result", "conclusion"]


def planet(pid, slot="result", **over):
    doc = {"id": pid, "slot": slot, "orbit": ORBITS[slot], "label": f"L{pid}",
           "detail": f"D{pid}", "provenance": "stated",
           "evidence": {"origin": "https://example.test/p", "quote": "q",
                        "retrieved": "2026-09-30"}}
    doc.update(over)
    return doc


def system(sid, fam):
    nodes = [planet(f"{sid}-{slot}", slot) for slot in BASE_SLOTS]
    nodes.append(planet(f"{sid}-family", "family", label=fam))
    return {"id": sid, "title": f"T{sid}", "planets": nodes}


SOTA_LINK = {"from_system": "a", "from": "a-result", "to_system": "b",
             "to": "b-result", "rel": "extends"}


def atlas():
    return {"systems": [system("a", "F1"), system("b", "F2"), system("c", "F3")],
            "links": [dict(SOTA_LINK)]}


def overlay(contributions=3, links=None, sid="proposal", family="F2", **over):
    nodes = [planet(f"{sid}-{slot}", slot) for slot in BASE_SLOTS]
    nodes += [planet(f"{sid}-contrib-{i}", "contribution") for i in range(contributions)]
    nodes.append(planet(f"{sid}-family", "family", label=family))
    doc = {"system": {"id": sid, "title": "Research concept r01", "planets": nodes},
           "links": links if links is not None else [
               {"from": f"{sid}-novelty", "to_system": "a", "to": "a-result", "rel": "extends"},
               {"from": f"{sid}-problem", "to_system": "b", "to": "b-result", "rel": "addresses"},
               {"from": f"{sid}-contrib-0", "to_system": "c", "to": "c-result", "rel": "about"},
           ]}
    doc.update(over)
    return doc


class MergeProposalSkyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="proposal-sky-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))
        self.atlas_path = self.tmp / "atlas.json"
        self.overlay_path = self.tmp / "r01.sky.json"
        self.merged_path = self.tmp / "atlas.with-proposal.json"
        self.atlas_path.write_text(json.dumps(atlas()), encoding="utf-8")
        self.overlay_path.write_text(json.dumps(overlay()), encoding="utf-8")

    def run_script(self, script, *args):
        proc = subprocess.run([sys.executable, str(script), *args],
                              capture_output=True, text=True, cwd=self.tmp)
        return proc.returncode, proc.stdout + proc.stderr

    def merge(self, *extra):
        return self.run_script(MERGER, str(self.atlas_path), str(self.overlay_path),
                               "--out", str(self.merged_path), *extra)

    def test_the_sota_side_arrives_untouched_and_in_its_own_order(self):
        code, out = self.merge()
        self.assertEqual(code, 0, out)
        before, after = atlas(), json.loads(self.merged_path.read_text(encoding="utf-8"))
        self.assertEqual([s["id"] for s in after["systems"]],
                         [s["id"] for s in before["systems"]] + ["proposal"])
        self.assertEqual(after["systems"][:3], before["systems"])
        self.assertEqual(after["links"][0], SOTA_LINK)

    def test_the_overlays_link_carries_the_proposal_as_its_source(self):
        """`from_system` is absent from the overlay on purpose; the written link
        must still be a complete one, or the checker refuses it as an endpoint
        without a system."""
        code, out = self.merge()
        self.assertEqual(code, 0, out)
        merged = json.loads(self.merged_path.read_text(encoding="utf-8"))
        written = [l for l in merged["links"] if l.get("from_system") == "proposal"]
        self.assertEqual(len(written), 3)
        self.assertEqual(
            sorted((l["from"], l["to_system"], l["to"], l["rel"]) for l in written),
            [("proposal-contrib-0", "c", "c-result", "about"),
             ("proposal-novelty", "a", "a-result", "extends"),
             ("proposal-problem", "b", "b-result", "addresses")])

    def test_the_merged_sky_passes_the_constellations_own_checker(self):
        """The chain is the contract: a merge that produces an atlas the
        checker refuses has not produced a sky."""
        code, out = self.merge()
        self.assertEqual(code, 0, out)
        code, out = self.run_script(CHECKER, str(self.merged_path))
        self.assertEqual(code, 0, out)
        self.assertIn("ATLAS_WELL_FORMED: 4 systems", out)

    def test_the_merged_sky_renders_as_the_proposals_own_page(self):
        code, out = self.merge()
        self.assertEqual(code, 0, out)
        page_path = self.tmp / "r01.graph.html"
        title = "Propuesta r01 — sobre el cielo SOTA"
        code, out = self.run_script(RENDERER, str(self.merged_path),
                                    "--out", str(page_path), "--title", title)
        self.assertEqual(code, 0, out)
        page = page_path.read_text(encoding="utf-8")
        self.assertIn(f"<title>{title}</title>", page)
        self.assertEqual(page.count(DATA_OPEN), 1)
        start = page.index(DATA_OPEN) + len(DATA_OPEN)
        scene = json.loads(page[start:page.index("</script>", start)])
        self.assertEqual(scene["atlas"]["systems"][-1]["id"], "proposal")
        self.assertIn("proposal.proposal-novelty", scene["positions"])
        self.assertEqual(len(scene["positions"]),
                         sum(len(s["planets"]) for s in scene["atlas"]["systems"]))
        self.assertTrue(any(e["inter"] for e in scene["edges"]),
                        "a proposal link into another system must be drawn as one")

    def test_two_contributions_are_refused_by_the_overlays_own_contract(self):
        self.overlay_path.write_text(json.dumps(overlay(contributions=2)), encoding="utf-8")
        code, out = self.merge()
        self.assertEqual(code, 1, out)
        self.assertIn("OVERLAY_CONTRIBUTIONS_OUTSIDE_3_5", out)

    def test_six_contributions_are_refused_by_the_overlays_own_contract(self):
        self.overlay_path.write_text(json.dumps(overlay(contributions=6)), encoding="utf-8")
        code, out = self.merge()
        self.assertEqual(code, 1, out)
        self.assertIn("OVERLAY_CONTRIBUTIONS_OUTSIDE_3_5", out)

    def test_five_contributions_are_admitted(self):
        self.overlay_path.write_text(json.dumps(overlay(contributions=5)), encoding="utf-8")
        code, out = self.merge()
        self.assertEqual(code, 0, out)

    def test_a_link_landing_on_no_planet_is_refused_by_name(self):
        links = [{"from": "proposal-novelty", "to_system": "a",
                  "to": "a-no-such-planet", "rel": "extends"}]
        self.overlay_path.write_text(json.dumps(overlay(links=links)), encoding="utf-8")
        code, out = self.merge()
        self.assertEqual(code, 1, out)
        self.assertIn("LINK_TARGET_UNKNOWN: a.a-no-such-planet", out)
        self.assertFalse(self.merged_path.exists(), "nothing is written when the merge refuses")

    def test_a_link_leaving_the_overlay_only_planets_is_refused_by_name(self):
        links = [{"from": "no-such-concept", "to_system": "a",
                  "to": "a-result", "rel": "extends"}]
        self.overlay_path.write_text(json.dumps(overlay(links=links)), encoding="utf-8")
        code, out = self.merge()
        self.assertEqual(code, 1, out)
        self.assertIn("LINK_SOURCE_UNKNOWN: proposal.no-such-concept", out)

    def test_a_system_id_already_in_the_constellation_is_refused(self):
        self.overlay_path.write_text(json.dumps(overlay(sid="a")), encoding="utf-8")
        code, out = self.merge()
        self.assertEqual(code, 1, out)
        self.assertIn("SYSTEM_ID_TAKEN: a", out)

    def test_an_overlay_that_is_not_json_is_unjudged_not_refused(self):
        self.overlay_path.write_text("{not json", encoding="utf-8")
        code, out = self.merge()
        self.assertEqual(code, 2, out)
        self.assertIn("OVERLAY_NOT_JSON", out)

    def test_a_proposal_family_outside_the_pool_budget_is_the_checkers_call(self):
        """The merger does not restate the constellation's family bound. A five
        family pool is the widest the checker admits, so a proposal that opens a
        sixth neighborhood merges fine and is refused by the one authority that
        owns that number -- named, and after the merge, not instead of it."""
        seven = {"systems": [system(f"s{i}", f"F{i}") for i in range(1, 8)], "links": []}
        self.atlas_path.write_text(json.dumps(seven), encoding="utf-8")
        self.overlay_path.write_text(json.dumps(overlay(family="F8", links=[])),
                                     encoding="utf-8")
        code, out = self.merge()
        self.assertEqual(code, 0, out)
        self.assertTrue(self.merged_path.is_file())
        code, out = self.run_script(CHECKER, str(self.merged_path))
        self.assertEqual(code, 1, out)
        self.assertIn("POOL_FAMILIES_OUTSIDE_3_7", out)


if __name__ == "__main__":
    unittest.main()
