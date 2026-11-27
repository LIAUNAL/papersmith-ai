"""The board counts the current protocol's findings only (board-follows-iteration S3, S4).

A workspace shaped like Paper_EEIA: a proof of concept answered protocol v12
(``implementations/pi5rc/pi5rc``) and the full experiments answer v23
(``implementations/pi5rc-v18/pi5rc``), whose positional discussion H14 tests
E14, the experiment proposal hypothesis H11 names in the latest sky overlay
(r21). The novelty overview, the manuscript graph's findings and the Concept
Map statuses (``GET /api/model/findings``) count only the v23 product, list the
v12 one as superseded, and show its findings under the proposal ids.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from skills._core.command_center import manuscript_graph, server
from skills._core.results import novelty_gate

REPO = Path(__file__).resolve().parents[1]
STATIC = REPO / "skills" / "_core" / "command_center" / "static"
V12 = "experiments/experiments-pi5rc-v12.md"
V23 = "experiments/experiments-pi5rc-v23.md"

PROTOCOL_V23 = """# Protocol v23

## Experiment [exp:E1] — Gain

- **Hypothesis:** The model beats the baseline.

## Experiment [exp:E2] — Second gain

- **Hypothesis:** It also beats it at night.

## Experiment [exp:E10] — Two sides

- **Hypothesis:** Both sides hold.

## Experiment [exp:E14] — Transfer

- **Hypothesis:** It transfers.
"""

SKY = {
    "system": {"id": "proposal", "title": "r21", "planets": [
        {"id": "p-problem", "slot": "problem", "orbit": 1, "label": "Load is unexplained", "detail": "d"}]},
    "links": [],
    "pillars": [{"id": "P1", "label": "Physics prior", "detail": "Sky detail."},
                {"id": "P3", "label": "Transfer across buildings"}],
    "hypotheses": [
        {"id": "H1", "statement": "Gain over the baseline.", "pillar": "P1", "experiments": ["E1", "E2"]},
        {"id": "H7a", "statement": "First side.", "pillar": "P1", "experiments": ["E10"]},
        {"id": "H7b", "statement": "Second side.", "pillar": "P1", "experiments": ["E10"]},
        {"id": "H11", "statement": "Transfer holds.", "pillar": "P3", "experiments": ["E14"]},
    ],
}

AFFINITY = {name: {"score": 90 if name == "Concept & Feasibility" else 10, "why": "w"}
            for name in ("General", "Theory", "Use-Inspired", "Concept & Feasibility", "Negative Results")}


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _hyp(hid: str, exp: str, verdict: str, proposal: list[str] | None = None, observed: str = "") -> dict:
    item = {"id": hid, "experiment": exp, "statement": f"{hid} statement", "verdict": verdict,
            "observed": observed}
    if proposal is not None:
        item["proposal_hypotheses"] = proposal
    return item


def _discussion(stage: str, protocol: str | None, hypotheses: list[dict], **extra) -> dict:
    data = {"schema": 1, "stage": stage, "summary": f"{stage} summary.",
            "hypotheses": hypotheses,
            "novelty": {"claim": f"{stage} claim", "verdict": "justified" if stage == "full" else "pending"},
            "limitations": [f"{stage} limitation"], **extra}
    if protocol is not None:
        data["protocol"] = protocol
    return data


class _Workspace(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.root = Path(holder.name).resolve()
        _write(self.root / "experiments" / "experiments-pi5rc-v12.md", "## Experiment [exp:E3] — old\n")
        _write(self.root / "experiments" / "experiments-pi5rc-v23.md", PROTOCOL_V23)
        _write(self.root / "proposals" / "research-concept-pi5rc-r21.md", "# r21\n")
        _write(self.root / "proposals" / "research-concept-pi5rc-r21.sky.json", json.dumps(SKY))
        self.poc = self.product("pi5rc", "AGREED.md", _discussion("poc", V12, [
            _hyp("H1", "E3", "supported"), _hyp("H2a", "E3", "not_supported"), _hyp("H5", "E7", "supported")],
            contribution_type={"type": "Concept & Feasibility", "why": "Pilot.", "affinity": AFFINITY}))
        self.full = self.product("pi5rc-v18", "Experimental_AGREED.md", _discussion("full", V23, [
            _hyp("H1", "E1", "supported", ["H1"], "MAE 0.31"),
            _hyp("H2", "E2", "not_supported", ["H1"]),
            _hyp("H13", "E10", "partially_supported", ["H7a", "H7b"]),
            _hyp("H14", "E14", "supported", ["H11"], "R2 0.88"),
            _hyp("H15", "E15", "pending")]))

    def product(self, repo: str, holder: str, data: dict) -> Path:
        folder = self.root / "implementations" / repo / "pi5rc"
        _write(folder / holder, "agreed\n")
        _write(folder / "Results" / "discussion.json", json.dumps(data))
        return folder

    def rewrite(self, folder: Path, **changes) -> None:
        path = folder / "Results" / "discussion.json"
        data = json.loads(path.read_text("utf-8"))
        data.update(changes)
        for key in [k for k, v in changes.items() if v is None]:
            del data[key]
        path.write_text(json.dumps(data), encoding="utf-8")


class NoveltyOverviewTests(_Workspace):
    def test_only_the_latest_protocol_counts_and_the_old_one_is_superseded(self) -> None:
        overview = novelty_gate.get_novelty_overview(self.root)
        self.assertEqual(overview["protocol"], {"current": V23, "version": 23})
        self.assertEqual([(d["product"], d["stage"]) for d in overview["discussions"]], [("pi5rc", "full")])
        self.assertEqual([(s["repo"], s["stage"], s["protocol"], s["version"]) for s in overview["superseded"]],
                         [("pi5rc", "poc", V12, 12)])
        self.assertEqual({h["stage"] for h in overview["hypotheses"]}, {"full"})
        self.assertEqual([c["stage"] for c in overview["novelty_claims"]], ["full"])
        self.assertEqual([l["text"] for l in overview["limitations"]], ["full limitation"])

    def test_hypotheses_are_listed_under_the_proposal_ids(self) -> None:
        rows = [(h["id"], h["discussion_id"], h["unmapped"])
                for h in novelty_gate.get_novelty_overview(self.root)["hypotheses"]]
        self.assertEqual(rows, [("H1", "H1", False), ("H1", "H2", False), ("H7a", "H13", False),
                                ("H7b", "H13", False), ("H11", "H14", False), ("H15", "H15", True)])

    def test_a_superseded_type_is_shown_stale_until_the_current_one_is_judged(self) -> None:
        kind = novelty_gate.get_novelty_overview(self.root)["contribution_type"]
        self.assertEqual((kind["type"], kind["product"], kind["stage"], kind["stale"]),
                         ("Concept & Feasibility", "pi5rc", "poc", True))
        self.rewrite(self.full, contribution_type={"type": "General", "why": "H11 holds."},
                     contribution_type_protocol=V12)
        kind = novelty_gate.get_novelty_overview(self.root)["contribution_type"]
        self.assertEqual((kind["type"], kind["stage"], kind["stale"], kind["judged_protocol"]),
                         ("General", "full", True, V12))
        self.rewrite(self.full, contribution_type_protocol=V23)
        kind = novelty_gate.get_novelty_overview(self.root)["contribution_type"]
        self.assertEqual((kind["type"], kind["stale"]), ("General", False))
        self.rewrite(self.full, contribution_type_protocol=None)
        self.assertFalse(novelty_gate.get_novelty_overview(self.root)["contribution_type"]["stale"])

    def test_a_discussion_without_a_protocol_is_not_current(self) -> None:
        self.rewrite(self.full, protocol=None)
        overview = novelty_gate.get_novelty_overview(self.root)
        self.assertEqual(overview["discussions"], [])
        self.assertEqual(sorted(s["protocol"] for s in overview["superseded"]), ["", V12])

    def test_without_a_published_protocol_every_product_counts(self) -> None:
        shutil.rmtree(self.root / "experiments")
        overview = novelty_gate.get_novelty_overview(self.root)
        self.assertEqual(sorted(d["stage"] for d in overview["discussions"]), ["full", "poc"])
        self.assertEqual(overview["superseded"], [])
        self.assertEqual(overview["protocol"], {"current": "", "version": None})


class ManuscriptFindingsTests(_Workspace):
    def findings(self, graph: dict) -> dict[str, dict]:
        return {n["id"]: n for n in graph["nodes"] if n["type"] == "finding"}

    def test_findings_follow_the_latest_protocol_under_proposal_ids(self) -> None:
        graph = manuscript_graph.build_graph(self.root)
        found = self.findings(graph)
        self.assertEqual(sorted(found), ["finding:H1", "finding:H11", "finding:H15", "finding:H7a",
                                         "finding:H7b", "finding:novelty"])
        self.assertEqual((found["finding:H11"]["verdict"], found["finding:H11"]["discussion_ids"],
                          found["finding:H11"]["unmapped"]), ("supported", ["H14"], False))
        self.assertEqual(found["finding:H11"]["source"]["path"],
                         "implementations/pi5rc-v18/pi5rc/Results/discussion.json")
        self.assertIn("R2 0.88", found["finding:H11"]["detail"])
        self.assertTrue(found["finding:H15"]["unmapped"])
        # H1 is tested by E1 (supported) and E2 (not supported): one finding, combined.
        self.assertEqual((found["finding:H1"]["verdict"], found["finding:H1"]["experiments"]),
                         ("partially_supported", ["E1", "E2"]))
        self.assertEqual(found["finding:novelty"]["source"]["path"],
                         "implementations/pi5rc-v18/pi5rc/Results/discussion.json")
        edges = {(e["from"], e["to"], e["rel"]) for e in graph["edges"]}
        self.assertIn(("experiment:E14", "finding:H11", "yields"), edges)
        self.assertIn(("experiment:E10", "finding:H7a", "yields"), edges)
        self.assertIn(("experiment:E10", "finding:H7b", "yields"), edges)
        self.assertEqual(graph["protocol"], V23)
        self.assertEqual([(s["product"], s["protocol"]) for s in graph["superseded"]],
                         [("implementations/pi5rc/pi5rc", V12)])

    def test_the_old_protocol_never_merges_into_the_current_findings(self) -> None:
        found = self.findings(manuscript_graph.build_graph(self.root))
        self.assertNotIn("finding:H2a", found)
        self.assertNotIn("finding:H5", found)
        self.assertNotIn("pi5rc/pi5rc/Results", " ".join(n["source"]["path"] for n in found.values()
                                                       if "pi5rc-v18" not in n["source"]["path"]))

    def test_with_only_old_products_the_findings_say_what_is_missing(self) -> None:
        shutil.rmtree(self.full)
        graph = manuscript_graph.build_graph(self.root)
        finding = [n for n in graph["nodes"] if n["type"] == "finding"]
        self.assertEqual(len(finding), 1)
        self.assertEqual(finding[0]["status"]["state"], "missing")
        self.assertIn(f"current protocol {V23}", finding[0]["status"]["reason"])

    def test_pillar_identity_comes_from_the_revision_and_the_spec_only_enriches(self) -> None:
        _write(self.root / ".papersmith" / "model_spec.json", json.dumps({"novelty": {
            "pillars": [{"id": "P1", "name": "Stale name", "summary": "Spec summary."},
                        {"id": "P2", "name": "Retired pillar", "summary": "Dropped by r21."}],
            "hypotheses": [{"id": "H11", "title": "Transfer", "statement": "Old wording."}]}}))
        graph = manuscript_graph.build_graph(self.root)
        pillars = {n["id"]: n for n in graph["nodes"] if n["type"] == "pillar"}
        self.assertEqual(sorted(pillars), ["pillar:P1", "pillar:P3"])
        self.assertEqual((pillars["pillar:P1"]["label"], pillars["pillar:P1"]["detail"]),
                         ("Physics prior", "Spec summary."))
        self.assertEqual(pillars["pillar:P3"]["label"], "Transfer across buildings")
        hyp = next(n for n in graph["nodes"] if n["id"] == "hypothesis:H11")
        self.assertEqual((hyp["label"], hyp["title"]), ("Transfer holds.", "Transfer"))


class ModelFindingsRouteTests(_Workspace):
    def test_the_route_serves_the_current_statuses(self) -> None:
        client = TestClient(server.create_app(self.root, history_store=None))
        body = client.get("/api/model/findings").json()
        self.assertEqual((body["protocol"], body["version"]), (V23, 23))
        statuses = {k: v["status"] for k, v in body["statuses"].items()}
        self.assertEqual(statuses, {"H1": "partially_supported", "H7a": "partially_supported",
                                    "H7b": "partially_supported", "H11": "supported", "H15": "pending"})
        self.assertEqual(body["statuses"]["H11"]["experiments"], ["E14"])
        self.assertTrue(body["statuses"]["H15"]["unmapped"])
        self.assertEqual([s["product"] for s in body["superseded"]], ["implementations/pi5rc/pi5rc"])


def _node(script: str, stdin: str) -> str:
    return subprocess.run(["node", "-e", script], input=stdin, capture_output=True, text=True,
                          cwd=tempfile.gettempdir(), check=True).stdout


def _preamble(lang: str) -> str:
    return (
        "const fs=require('fs');const els={};global.fetch=undefined;"
        f"global.localStorage={{getItem:()=>{json.dumps(lang)},setItem(){{}}}};"
        "global.window={localStorage:global.localStorage,location:{href:'http://x/',origin:'http://x',hash:''},"
        "addEventListener(){}};"
        "global.CustomEvent=function(n,o){this.type=n;this.detail=o&&o.detail;};"
        "global.document={readyState:'complete',documentElement:{},addEventListener(){},dispatchEvent(){},"
        "querySelectorAll:()=>[],getElementById:(id)=>(els[id]=els[id]||{innerHTML:'',hidden:false})};"
        "for (const f of ['i18n/en.js','i18n/es.js','i18n.js','contribution-affinity.js'])"
        f"  eval(fs.readFileSync({json.dumps(str(STATIC))}+'/'+f,'utf8'));"
    )


SPEC = {"novelty": {"hypotheses": [
    {"id": "H11", "title": "Transfer", "statement": "Transfer holds.", "status": "Supported in v18 (MAE 0.4)"},
    {"id": "H7a", "title": "Side", "statement": "First side."},
    {"id": "H20", "title": "New", "statement": "Not tested yet."}]},
    "contribution_type": {"type": "Theory", "why": "A bound."}}


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class ConceptMapStatusTests(_Workspace):
    def render(self, spec: dict, findings: dict | None, lang: str = "en") -> dict:
        script = (_preamble(lang)
                  + f"eval(fs.readFileSync({json.dumps(str(STATIC / 'model-panel.js'))},'utf8'));"
                  + "const input=JSON.parse(fs.readFileSync(0,'utf8'));"
                  + "window.renderModelModules(input.spec);"
                  + "if (input.findings) window.renderModelFindings(input.findings);"
                  + "console.log(JSON.stringify({hyp:els.modelHypothesisGrid.innerHTML,"
                  + "ct:els.modelContributionType.innerHTML,pillars:els.modelPillarGrid.innerHTML}));")
        return json.loads(_node(script, json.dumps({"spec": spec, "findings": findings})))

    def findings(self) -> dict:
        return TestClient(server.create_app(self.root, history_store=None)).get("/api/model/findings").json()

    def test_the_status_comes_from_the_current_findings(self) -> None:
        html = self.render(SPEC, self.findings())["hyp"]
        cards = html.split('class="model-hypothesis-card"')[1:]
        self.assertIn("supported (current protocol v23)", cards[0])
        self.assertIn('data-finding-status="supported"', cards[0])
        self.assertIn("partially supported (current protocol v23)", cards[1])
        self.assertIn("pending (current protocol v23)", cards[2])
        # The spec's prose status is kept as a detail, never as the badge.
        self.assertIn("Status noted in the spec:</em> Supported in v18 (MAE 0.4)", cards[0])
        self.assertNotIn('<span class="badge">Supported in v18', html)

    def test_the_status_is_translated(self) -> None:
        html = self.render(SPEC, self.findings(), "es")["hyp"]
        self.assertIn("respaldada (protocolo vigente v23)", html)
        self.assertIn("pendiente (protocolo vigente v23)", html)

    def test_a_stale_contribution_type_carries_a_badge(self) -> None:
        self.assertNotIn("data-contribution-stale", self.render(SPEC, None)["ct"])
        stale = self.render({**SPEC, "contribution_type_stale": True}, None)["ct"]
        self.assertIn('data-contribution-stale="true"', stale)
        self.assertIn(">stale<", stale)

    def test_a_spec_synced_from_an_older_revision_says_so(self) -> None:
        self.assertNotIn("data-spec-stale", self.render(SPEC, None)["pillars"])
        stale = {**SPEC, "stale": True, "source_revision": "r18", "latest_revision": "r21"}
        self.assertIn("synced from r18, older than the latest revision r21", self.render(stale, None)["pillars"])
        self.assertIn("desde r18, anterior a la última revisión r21", self.render(stale, None, "es")["pillars"])


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class NoveltyPanelSupersededTests(_Workspace):
    def render(self, overview: dict, lang: str = "en") -> str:
        script = (_preamble(lang)
                  + f"eval(fs.readFileSync({json.dumps(str(STATIC / 'novelty-panel.js'))},'utf8'));"
                  + "window.NoveltyPanel.render(JSON.parse(fs.readFileSync(0,'utf8')));"
                  + "console.log(els.noveltyRoot.innerHTML);")
        return _node(script, json.dumps(overview))

    def test_superseded_products_are_shown_apart(self) -> None:
        html = self.render(novelty_gate.get_novelty_overview(self.root))
        self.assertIn('id="noveltySuperseded"', html)
        section = html.split('id="noveltySuperseded"', 1)[1].split("</section>", 1)[0]
        self.assertIn("Superseded products", section)
        self.assertIn(V12, section)
        self.assertIn(V23, section)
        matrix = html.split('data-fold="novelty:hypotheses"', 1)[1].split("</section>", 1)[0]
        self.assertNotIn("H2a", matrix)
        self.assertIn("discussion H14", matrix)
        self.assertIn('data-unmapped="true"', matrix)
        self.assertIn('data-contribution-stale="true"', html)
        es = self.render(novelty_gate.get_novelty_overview(self.root), "es")
        self.assertIn("Productos reemplazados", es)

    def test_no_superseded_section_when_every_product_is_current(self) -> None:
        shutil.rmtree(self.poc)
        self.assertNotIn('id="noveltySuperseded"', self.render(novelty_gate.get_novelty_overview(self.root)))


if __name__ == "__main__":
    unittest.main()


class DerivedProposalIdsTests(_Workspace):
    """A discussion written before ``proposal_hypotheses`` existed is shown under the
    current proposal ids, derived on read from the sky's experiments, and is not rewritten."""

    def test_a_discussion_without_the_field_maps_through_the_sky(self) -> None:
        from skills._core.results.discussion import current_findings
        path = self.full / "Results" / "discussion.json"
        data = json.loads(path.read_text("utf-8"))
        for hypothesis in data["hypotheses"]:
            hypothesis.pop("proposal_hypotheses", None)
        path.write_text(json.dumps(data), encoding="utf-8")
        before = path.read_bytes()
        statuses = current_findings(self.root)["statuses"]
        self.assertIn("H11", statuses)
        self.assertFalse(statuses["H11"]["unmapped"])
        self.assertIn("H7a", statuses)
        self.assertIn("H7b", statuses)
        self.assertNotIn("H14", statuses)
        self.assertEqual(path.read_bytes(), before)

