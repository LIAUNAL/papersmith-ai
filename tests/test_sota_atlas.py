"""The constellation bound, held executable: check_atlas.py's verdicts and
render_atlas.py's single-file HTML.

Every refusal the checker can name is produced here from an atlas built
for it, never read out of the script's prose. The renderer is held to
one 3D sky (a deterministic scene in a JSON data island drawn by the
vendored three.js viewer inlined verbatim), deterministic bytes, drawn
cross-links, and output that opens with no network.

Stdlib only.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent / "skills" / "plausibility" / "scripts"
CHECKER = SKILL / "check_atlas.py"
RENDERER = SKILL / "render_atlas.py"
BUNDLE = SKILL.parent / "assets" / "atlas3d.bundle.js"
DATA_OPEN = '<script type="application/json" id="atlas-data">'


def scene_of(page):
    """The data island the viewer draws: the scene, parsed back as JSON."""
    start = page.index(DATA_OPEN) + len(DATA_OPEN)
    return json.loads(page[start:page.index("</script>", start)])

ORBITS = {"sun": 0, "branch": 1, "topic_app": 1, "topic_ai": 1,
          "problem": 1, "application": 1, "family": 2, "novelty": 1,
          "contribution": 1, "result": 3, "conclusion": 3}
BASE_SLOTS = ["sun", "topic_app", "topic_ai", "problem", "application",
              "novelty", "result", "conclusion"]


def planet(pid, slot="result", **over):
    doc = {"id": pid, "slot": slot, "orbit": ORBITS[slot], "label": f"L{pid}",
           "detail": f"D{pid}", "provenance": "stated",
           "evidence": {"origin": "https://example.test/p", "quote": "q",
                        "retrieved": "2026-09-30"}}
    doc.update(over)
    return doc


def system(sid, fam):
    """One system with exactly one family planet: the group it belongs to."""
    nodes = [planet(f"{sid}-{slot}", slot) for slot in BASE_SLOTS]
    nodes.append(planet(f"{sid}-family", "family", label=fam))
    return {"id": sid, "title": f"T{sid}", "planets": nodes}


def atlas(systems=None, links=None):
    if systems is None:
        systems = [system("a", "F1"), system("b", "F2"), system("c", "F3")]
    return {"systems": systems, "links": links if links is not None else []}


class CheckAtlasTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="sota-atlas-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))

    def run_checker(self, payload, name="atlas.json"):
        target = self.tmp / name
        target.write_text(payload if isinstance(payload, str) else json.dumps(payload),
                          encoding="utf-8")
        proc = subprocess.run([sys.executable, str(CHECKER), str(target)],
                              capture_output=True, text=True, cwd=self.tmp)
        return proc.returncode, proc.stdout + proc.stderr

    def test_green_constellation_with_intra_and_family_links_passes(self):
        links = [{"from_system": "a", "from": "a-family", "to_system": "b",
                  "to": "b-family", "rel": "shares-family-with"},
                 {"from_system": "a", "from": "a-sun", "to_system": "a",
                  "to": "a-problem", "rel": "about"}]
        code, out = self.run_checker(atlas(links=links))
        self.assertEqual(code, 0, out)
        self.assertIn("ATLAS_WELL_FORMED", out)

    def test_family_link_on_non_family_is_named(self):
        links = [{"from_system": "a", "from": "a-topic_app", "to_system": "b",
                  "to": "b-family", "rel": "shares-family-with"}]
        code, out = self.run_checker(atlas(links=links))
        self.assertEqual(code, 1, out)
        self.assertIn("SHARED_FAMILY_LINK_ON_NON_FAMILY", out)

    def test_cross_family_bridge_passes(self):
        links = [{"from_system": "a", "from": "a-family", "to_system": "b",
                  "to": "b-family", "rel": "contradicts"}]
        code, out = self.run_checker(atlas(links=links))
        self.assertEqual(code, 0, out)
        self.assertIn("ATLAS_WELL_FORMED", out)

    def test_twenty_first_planet_exceeds_the_ceiling(self):
        systems = [system("a", "F1"), system("b", "F2"), system("c", "F3")]
        systems[0]["planets"].extend(planet(f"x{i}") for i in range(12))
        code, out = self.run_checker(atlas(systems=systems))
        self.assertEqual(code, 1, out)
        self.assertIn("PLANET_BUDGET_EXCEEDED", out)

    def test_second_family_planet_breaks_membership(self):
        systems = [system("a", "F1"), system("b", "F2"), system("c", "F3")]
        systems[0]["planets"].append(
            planet("a-family-2", "family", orbit=2, label="F2"))
        code, out = self.run_checker(atlas(systems=systems))
        self.assertEqual(code, 1, out)
        self.assertIn("SLOT_COUNT_OUTSIDE_ROW", out)

    def test_pool_with_one_family_is_no_constellation(self):
        systems = [system("a", "F1"), system("b", "F1")]
        code, out = self.run_checker(atlas(systems=systems))
        self.assertEqual(code, 1, out)
        self.assertIn("POOL_FAMILIES_OUTSIDE_3_5", out)

    def test_pool_with_six_families_is_no_constellation(self):
        systems = [system(f"s{i}", f"F{i}") for i in range(6)]
        code, out = self.run_checker(atlas(systems=systems))
        self.assertEqual(code, 1, out)
        self.assertIn("POOL_FAMILIES_OUTSIDE_3_5", out)

    def test_link_to_no_planet_is_named(self):
        links = [{"from_system": "a", "from": "a-sun", "to_system": "b",
                  "to": "ghost", "rel": "contradicts"}]
        code, out = self.run_checker(atlas(links=links))
        self.assertEqual(code, 1, out)
        self.assertIn("LINK_ENDPOINT_WITHOUT_PLANET", out)

    def test_link_to_no_system_is_named(self):
        links = [{"from_system": "a", "from": "a-sun", "to_system": "ghost",
                  "to": "a-topic_app", "rel": "about"}]
        code, out = self.run_checker(atlas(links=links))
        self.assertEqual(code, 1, out)
        self.assertIn("LINK_SYSTEM_WITHOUT_SYSTEM", out)

    def test_undated_evidence_is_named(self):
        systems = [system("a", "F1"), system("b", "F2"), system("c", "F3")]
        systems[0]["planets"][0]["evidence"]["retrieved"] = "someday"
        code, out = self.run_checker(atlas(systems=systems))
        self.assertEqual(code, 1, out)
        self.assertIn("EVIDENCE_RETRIEVED_UNDATED", out)

    def test_non_json_is_unjudged_not_refused(self):
        code, out = self.run_checker("{not json")
        self.assertEqual(code, 2, out)
        self.assertIn("ATLAS_NOT_JSON", out)

    def test_optional_contributions_are_admitted_up_to_five(self):
        """A proposal carries three to five concepts that hint at its novelty
        and the issues it could resolve. A paper carries none, which is why the
        row's floor is zero: the slot is optional for every system, so the SOTA
        side of the same atlas keeps the shape it always had."""
        nodes = system("a", "F1")["planets"] + [
            planet(f"a-contrib-{i}", "contribution") for i in range(5)]
        payload = atlas(systems=[{**system("a", "F1"), "planets": nodes},
                                 system("b", "F2"), system("c", "F3")])
        code, out = self.run_checker(payload)
        self.assertEqual(code, 0, out)

    def test_a_sixth_contribution_is_refused(self):
        """Five is the widest the proposal contract names; a sixth concept is
        a different claim and belongs in a revision of its own."""
        nodes = system("a", "F1")["planets"] + [
            planet(f"a-contrib-{i}", "contribution") for i in range(6)]
        payload = atlas(systems=[{**system("a", "F1"), "planets": nodes},
                                 system("b", "F2"), system("c", "F3")])
        code, out = self.run_checker(payload)
        self.assertEqual(code, 1, out)
        self.assertIn("SLOT_COUNT_OUTSIDE_ROW", out)


class QuoteFidelityTests(unittest.TestCase):
    """E6: `--pool` holds every quote to the abstract its origin names.

    Without it the checker certifies shape only, so a paraphrase or an
    invented sentence dressed as a quote ran green. With `--pool
    sota-pool/candidates.json` every planet's `evidence.origin` must name a
    pool candidate (its `identifier`, `source_url` or `url`) and its `quote`
    must be a verbatim substring of that candidate's `abstract`. Whitespace
    runs are layout, not authorship, so they compare collapsed; nothing else
    is normalized.
    """

    ABSTRACT = ("We study sparse codes.\n  Our method   recovers the dictionary "
                "under mild assumptions. Results hold on three benchmarks.")

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="sota-fidelity-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))

    def grounded_atlas(self, quote="Our method recovers the dictionary"):
        systems = [system("a", "F1"), system("b", "F2"), system("c", "F3")]
        for sys_ in systems:
            for node in sys_["planets"]:
                node["evidence"] = {"origin": f"arXiv:{sys_['id']}", "quote": quote,
                                    "retrieved": "2026-09-30"}
        return atlas(systems=systems)

    def pool(self, abstracts=None):
        abstracts = abstracts or {}
        return [{"identifier": f"arXiv:{sid}", "resolver": "arxiv",
                 "source_url": f"https://arxiv.example/abs/{sid}",
                 "abstract": abstracts.get(sid, self.ABSTRACT)}
                for sid in ("a", "b", "c")]

    def run_checker(self, atlas_doc, pool_doc=None, *extra):
        target = self.tmp / "atlas.json"
        target.write_text(json.dumps(atlas_doc), encoding="utf-8")
        argv = [sys.executable, str(CHECKER), str(target)]
        if pool_doc is not None:
            pool_path = self.tmp / "candidates.json"
            pool_path.write_text(pool_doc if isinstance(pool_doc, str) else json.dumps(pool_doc),
                                 encoding="utf-8")
            argv += ["--pool", str(pool_path)]
        proc = subprocess.run(argv + list(extra), capture_output=True, text=True, cwd=self.tmp)
        return proc.returncode, proc.stdout + proc.stderr

    def test_a_verbatim_quote_passes(self):
        code, out = self.run_checker(self.grounded_atlas(), self.pool())
        self.assertEqual(code, 0, out)
        self.assertIn("every quote verbatim", out)

    def test_a_paraphrase_fails(self):
        code, out = self.run_checker(self.grounded_atlas("Our approach recovers the dictionary"),
                                     self.pool())
        self.assertEqual(code, 1, out)
        self.assertIn("EVIDENCE_QUOTE_NOT_IN_ABSTRACT", out)

    def test_whitespace_is_layout_but_case_is_not(self):
        code, out = self.run_checker(self.grounded_atlas("sparse codes. Our method"), self.pool())
        self.assertEqual(code, 0, out)
        code, out = self.run_checker(self.grounded_atlas("our method recovers"), self.pool())
        self.assertEqual(code, 1, out)

    def test_the_source_url_names_the_candidate_too(self):
        doc = self.grounded_atlas()
        for sys_ in doc["systems"]:
            for node in sys_["planets"]:
                node["evidence"]["origin"] = f"https://arxiv.example/abs/{sys_['id']}"
        code, out = self.run_checker(doc, self.pool())
        self.assertEqual(code, 0, out)

    def test_an_origin_outside_the_pool_fails(self):
        doc = self.grounded_atlas()
        doc["systems"][0]["planets"][0]["evidence"]["origin"] = "https://elsewhere.example/x"
        code, out = self.run_checker(doc, self.pool())
        self.assertEqual(code, 1, out)
        self.assertIn("EVIDENCE_ORIGIN_NOT_IN_POOL", out)

    def test_a_candidate_without_an_abstract_cannot_be_quoted(self):
        pool = self.pool()
        pool[1]["abstract"] = None
        code, out = self.run_checker(self.grounded_atlas(), pool)
        self.assertEqual(code, 1, out)
        self.assertIn("EVIDENCE_ABSTRACT_MISSING", out)

    def test_a_pool_wrapped_in_an_object_reads_the_same(self):
        code, out = self.run_checker(self.grounded_atlas(), {"candidates": self.pool()})
        self.assertEqual(code, 0, out)

    def test_an_unreadable_pool_judges_nothing(self):
        code, out = self.run_checker(self.grounded_atlas(), "{not json")
        self.assertEqual(code, 2, out)
        self.assertIn("POOL_NOT_JSON", out)
        code, out = self.run_checker(self.grounded_atlas(), {"candidates": "x"})
        self.assertEqual(code, 2, out)
        self.assertIn("POOL_MALFORMED", out)

    def test_without_the_pool_the_check_stays_shape_only(self):
        code, out = self.run_checker(self.grounded_atlas("Our approach recovers the dictionary"))
        self.assertEqual(code, 0, out)
        self.assertNotIn("quote verbatim", out)


class GrapherAgentChecksQuotesTests(unittest.TestCase):
    """The agent that draws the atlas runs the checker WITH the pool, so the
    quote-fidelity guard runs inside its own repair loop, not only when an
    operator remembers the flag. Every agent definition (canonical and every
    projection) that runs the checker on the pool's atlas is read."""

    ROOT = Path(__file__).resolve().parent.parent
    PROJECTIONS = (".claude/agents", ".agents/agents", ".opencode/agents", ".pi/agents")

    def test_every_checker_run_on_the_atlas_carries_the_pool(self):
        runs = []
        for folder in self.PROJECTIONS:
            for agent in sorted((self.ROOT / folder).glob("*.md")):
                for line in agent.read_text(encoding="utf-8").splitlines():
                    if "check_atlas.py sota-pool/atlas.json" in line:
                        runs.append((f"{folder}/{agent.name}", line.strip()))
        self.assertTrue(runs, "no agent runs the atlas checker")
        for where, line in runs:
            with self.subTest(agent=where):
                self.assertIn("--pool sota-pool/candidates.json", line)


class RenderAtlasTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="sota-render-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))
        self.atlas_path = self.tmp / "atlas.json"
        self.atlas_path.write_text(json.dumps(atlas()), encoding="utf-8")
        self.out_path = self.tmp / "atlas.html"

    def run_renderer(self, *args):
        proc = subprocess.run([sys.executable, str(RENDERER), *args],
                              capture_output=True, text=True, cwd=self.tmp)
        return proc.returncode, proc.stdout + proc.stderr

    def test_green_atlas_renders_one_self_contained_sky(self):
        links = [{"from_system": "a", "from": "a-family", "to_system": "b",
                  "to": "b-family", "rel": "shares-family-with"}]
        self.atlas_path.write_text(json.dumps(atlas(links=links)), encoding="utf-8")
        code, out = self.run_renderer(str(self.atlas_path), "--out", str(self.out_path))
        self.assertEqual(code, 0, out)
        self.assertIn("ATLAS_RENDERED", out)
        page = self.out_path.read_text(encoding="utf-8")
        self.assertNotIn("<svg", page)
        self.assertEqual(page.count('id="sky"'), 1)
        self.assertEqual(page.count(DATA_OPEN), 1)
        scene = scene_of(page)
        self.assertEqual(sorted(s["title"] for s in scene["atlas"]["systems"]),
                         ["Ta", "Tb", "Tc"])
        inter = [e for e in scene["edges"] if e["inter"]]
        self.assertEqual([(e["from"], e["to"]) for e in inter],
                         [("a.a-family", "b.b-family")])
        self.assertIn('rellegend', page)
        self.assertIn('id="zoomin"', page)
        self.assertIn('id="zoomout"', page)
        self.assertIn('id="zoomreset"', page)
        self.assertIn('famchips', page)
        self.assertNotIn('famfilter', page)
        self.assertIn('id="overlay"', page)
        self.assertIn('openModal', page)
        self.assertIn('AtlasViewer.mount', page)
        self.assertNotIn("<script src", page)
        self.assertNotIn("<link ", page)
        self.assertNotIn("@import", page)

    def test_default_title_is_the_sota_constellations_own_words(self):
        """A second caller must not change the first one's artifact: the
        default is the sentence this page always carried."""
        code, out = self.run_renderer(str(self.atlas_path), "--out", str(self.out_path))
        self.assertEqual(code, 0, out)
        page = self.out_path.read_text(encoding="utf-8")
        self.assertIn("<title>SOTA constellation</title>", page)
        self.assertIn("<h1>SOTA constellation — one sky</h1>", page)

    def test_a_named_sky_says_its_own_name_in_both_places(self):
        """A caller rendering another domain's sky names it. The tab title and
        the heading both follow, so the page cannot contradict its own tab."""
        named = "Propuesta r01 — sobre el cielo SOTA"
        code, out = self.run_renderer(str(self.atlas_path), "--out", str(self.out_path),
                                      "--title", named)
        self.assertEqual(code, 0, out)
        page = self.out_path.read_text(encoding="utf-8")
        self.assertIn(f"<title>{named}</title>", page)
        self.assertIn(f"<h1>{named}</h1>", page)
        self.assertNotIn("SOTA constellation — one sky", page)

    def test_a_name_carrying_markup_is_escaped(self):
        """The name is text, not markup: a proposal title with an angle bracket
        must not become a tag in the artifact."""
        code, out = self.run_renderer(str(self.atlas_path), "--out", str(self.out_path),
                                      "--title", "<img src=x onerror=alert(1)>")
        self.assertEqual(code, 0, out)
        page = self.out_path.read_text(encoding="utf-8")
        self.assertNotIn("<img src=x", page)
        self.assertIn("&lt;img src=x", page)

    def test_vendored_viewer_is_inlined_verbatim(self):
        code, out = self.run_renderer(str(self.atlas_path), "--out", str(self.out_path))
        self.assertEqual(code, 0, out)
        bundle = BUNDLE.read_text(encoding="utf-8")
        self.assertNotIn("</script", bundle.lower())
        self.assertIn("AtlasViewer", bundle)
        self.assertIn(bundle, self.out_path.read_text(encoding="utf-8"))

    def test_every_planet_has_a_point_in_three_dimensions(self):
        code, out = self.run_renderer(str(self.atlas_path), "--out", str(self.out_path))
        self.assertEqual(code, 0, out)
        scene = scene_of(self.out_path.read_text(encoding="utf-8"))
        keys = {f"{s['id']}.{p['id']}" for s in atlas()["systems"] for p in s["planets"]}
        self.assertEqual(set(scene["positions"]), keys)
        points = list(scene["positions"].values())
        self.assertTrue(all(len(p) == 3 for p in points))
        self.assertGreater(len({p[2] for p in points}), 1, "the sky must not be flat")
        for sid, frame in scene["frames"].items():
            self.assertEqual(set(frame), {"center", "u", "v"}, sid)

    def test_same_atlas_draws_the_same_sky(self):
        first = self.tmp / "first.html"
        second = self.tmp / "second.html"
        self.run_renderer(str(self.atlas_path), "--out", str(first))
        self.run_renderer(str(self.atlas_path), "--out", str(second))
        self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_red_shape_is_not_drawn(self):
        self.atlas_path.write_text(json.dumps({"systems": []}), encoding="utf-8")
        code, out = self.run_renderer(str(self.atlas_path), "--out", str(self.out_path))
        self.assertEqual(code, 1, out)
        self.assertFalse(self.out_path.exists())

    def test_shared_family_name_draws_its_tie(self):
        payload = {"systems": [system("a", "F"), system("b", "F")], "links": []}
        target = self.tmp / "ties.json"
        target.write_text(json.dumps(payload), encoding="utf-8")
        out_path = self.tmp / "ties.html"
        code, out = self.run_renderer(str(target), "--out", str(out_path))
        self.assertEqual(code, 0, out)
        ties = scene_of(out_path.read_text(encoding="utf-8"))["ties"]
        self.assertEqual(ties, [{"family": "F", "from": "a.a-family", "to": "b.b-family"}])

    def test_missing_operand_is_usage(self):
        code, _ = self.run_renderer()
        self.assertEqual(code, 2)

    def test_systems_keep_clear_of_each_other_on_one_plane(self):
        import importlib.util
        import math
        spec = importlib.util.spec_from_file_location("render_atlas", str(RENDERER))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        systems = [{"id": f"s{i:02d}", "planets": []} for i in range(25)]
        pts = list(module._system_centers(systems).values())
        nearest = min(math.dist(a, b) for i, a in enumerate(pts) for b in pts[i + 1:])
        self.assertGreaterEqual(nearest, 600)

    def test_families_land_in_distinct_neighborhoods(self):
        import importlib.util
        import math
        spec = importlib.util.spec_from_file_location("render_atlas", str(RENDERER))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        owned = ([system(f"a{i}", "F1") for i in range(3)]
                 + [system(f"b{i}", "F2") for i in range(3)])
        centers = module._system_centers(owned)
        groups: dict[str, list[tuple[float, float]]] = {}
        for sid, point in centers.items():
            fam = "F1" if sid.startswith("a") else "F2"
            groups.setdefault(fam, []).append(point)
        centroids = {fam: (sum(p[0] for p in pts) / len(pts),
                           sum(p[1] for p in pts) / len(pts))
                     for fam, pts in groups.items()}
        self.assertGreater(math.dist(centroids["F1"], centroids["F2"]), 3000)


class GroupLayoutAndBridgeTests(unittest.TestCase):
    """The group layout ("Group layout") and the dashboard bridge are
    additions: the default sky the Python renderer precomputes stays the same
    bytes, and the page only gains one button and a postMessage contract."""

    # sha256 of json.dumps(_scene(atlas)) for FIXED_ATLAS, taken before the
    # group layout existed: the default layout must not move.
    SCENE_SHA = "29b6a5f8249dc9158d33a35e5e91c83281dc07989f28a894276f45f86420bb87"
    LAYOUT_SHA = "5f426e9544d6bb8bfd087f4264af8007bdc9302b222c5ddb71adbd57e3fba3f5"

    @staticmethod
    def fixed_atlas():
        links = [{"from_system": "a", "from": "a-family", "to_system": "b",
                  "to": "b-family", "rel": "shares-family-with"}]
        return atlas(systems=[system("a", "F1"), system("b", "F2"), system("c", "F1")],
                     links=links)

    @staticmethod
    def module():
        import importlib.util
        spec = importlib.util.spec_from_file_location("render_atlas", str(RENDERER))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def page(self):
        return self.module().render(self.fixed_atlas())

    def page_script(self):
        page = self.page()
        bundle = BUNDLE.read_text(encoding="utf-8")
        return page[page.index(bundle) + len(bundle):]

    def test_default_scene_is_byte_identical_to_the_precomputed_sky(self):
        import hashlib
        scene = self.module()._scene(self.fixed_atlas())
        self.assertEqual(hashlib.sha256(json.dumps(scene).encode()).hexdigest(),
                         self.SCENE_SHA)
        layout = {"positions": scene["positions"], "frames": scene["frames"]}
        self.assertEqual(hashlib.sha256(json.dumps(layout).encode()).hexdigest(),
                         self.LAYOUT_SHA)
        island = scene_of(self.page())
        self.assertEqual(island["positions"], scene["positions"])
        self.assertEqual(island["frames"], scene["frames"])
        self.assertEqual(self.page(), self.page())

    def test_page_has_the_group_layout_button_beside_the_zoom_buttons(self):
        page = self.page()
        self.assertIn('<button id="grouplayout">Group layout</button>', page)
        toolbar = page[page.index('<div id="toolbar">'):]
        toolbar = toolbar[:toolbar.index("</div>")]
        for button in ('id="zoomin"', 'id="zoomout"', 'id="zoomreset"', 'id="grouplayout"'):
            self.assertIn(button, toolbar)
        script = self.page_script()
        self.assertIn("getElementById('grouplayout')", script)
        self.assertIn("setLayout", script)

    def test_page_listens_to_atlas_commands_from_its_parent_only(self):
        script = self.page_script()
        self.assertIn("addEventListener('message'", script)
        self.assertIn("event.source === window.parent", script)
        self.assertIn("'atlas-command'", script)
        for command in ("'group-layout'", "'sky-layout'", "'toggle-layout'", "'reset'"):
            self.assertIn(command, script)

    def test_page_reports_layout_and_planet_selection_to_its_parent(self):
        script = self.page_script()
        self.assertIn("type: 'atlas-layout'", script)
        self.assertIn("type: 'atlas-planet-selected'", script)
        self.assertIn("window.parent !== window", script)
        self.assertIn("postMessage(", script)

    def test_page_offers_the_2d_constellation_when_the_3d_sky_should_not_run(self):
        """No WebGL, a software renderer, a small machine or a slow first few
        seconds open the 2D constellation, and the viewer can switch by hand."""
        page = self.page()
        toolbar = page[page.index('<div id="toolbar">'):]
        toolbar = toolbar[:toolbar.index("</div>")]
        for button in ('id="viewmode"', 'id="names"', 'id="autorotate"', 'id="spinleft"',
                       'id="spinright"', 'id="tiltup"', 'id="tiltdown"'):
            self.assertIn(button, toolbar)
        self.assertIn('<div id="gpunote" role="status" hidden></div>', page)
        script = self.page_script()
        for needle in ("failIfMajorPerformanceCaveat", "WEBGL_debug_renderer_info",
                       "navigator.deviceMemory", "navigator.hardwareConcurrency",
                       "get('view')", "const FlatViewer", "function watchFrameRate",
                       "'view-2d'", "'view-3d'"):
            self.assertIn(needle, script)

    def test_page_stops_drawing_while_nobody_can_see_it(self):
        script = self.page_script()
        self.assertIn("addEventListener('visibilitychange'", script)
        self.assertIn("'pause': () => { dashboardPaused = true; applyVisibility(); }", script)
        self.assertIn("'resume': () => { dashboardPaused = false; applyVisibility(); }", script)

    def test_bundle_draws_no_system_label_sprites_and_exposes_the_page_handle(self):
        source = (BUNDLE.parent / "atlas3d" / "viewer.js").read_text(encoding="utf-8")
        self.assertNotIn("labelSprite(String(system.title", source)
        self.assertIn("Math.min(Math.max(window.devicePixelRatio || 1, 1), 2)", source)
        bundle = BUNDLE.read_text(encoding="utf-8")
        for method in ("dispose(", "project(", "rotating(", "spin(", "tilt(", "refresh("):
            self.assertIn(method, bundle)

    def test_bundle_exposes_the_layout_switch(self):
        bundle = BUNDLE.read_text(encoding="utf-8")
        self.assertIn("setLayout", bundle)
        self.assertIn("'groups'".replace("'", '"'), bundle)
        self.assertNotIn("</script", bundle.lower())


if __name__ == "__main__":
    unittest.main()
