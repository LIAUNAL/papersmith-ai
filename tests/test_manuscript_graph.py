"""The manuscript summary graph (closing-sections-and-manuscript-graphs S6).

``skills/_core/command_center/manuscript_graph.py`` writes
``.papersmith/manuscript_graph.json``: typed nodes (topic, problem, pillar,
hypothesis, sota, base_concept, novelty_concept, experiment, finding,
conclusion) and typed edges, read from the artifacts each phase already
writes. A missing source becomes a ``missing`` node naming the phase that
fills it; nothing is invented. These tests run on a copy of
``tests/fixtures/manuscript_graph/`` and go through the module's public
functions, its command line, ``smith atlas summary`` and the dashboard routes.
"""

from __future__ import annotations

import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from papersmith.cli import build_parser
from skills._core.command_center import manuscript_graph, server

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests" / "fixtures" / "manuscript_graph"
NODE_TYPES = ("topic", "problem", "pillar", "hypothesis", "sota", "base_concept",
              "novelty_concept", "experiment", "finding", "conclusion")


def _route(app, path: str, method: str):
    for route in app.routes:
        if getattr(route, "path", None) == path and method in (getattr(route, "methods", None) or ()):
            return route.endpoint
    raise AssertionError(f"no {method} {path} route")


class _Workspace(unittest.TestCase):
    def workspace(self) -> Path:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        root = Path(holder.name).resolve() / "ws"
        shutil.copytree(FIXTURE, root)
        return root

    def empty_workspace(self) -> Path:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        root = Path(holder.name).resolve() / "ws"
        root.mkdir()
        return root

    @staticmethod
    def nodes(graph: dict, kind: str) -> list[dict]:
        return [n for n in graph["nodes"] if n["type"] == kind]

    @staticmethod
    def edge_set(graph: dict) -> set[tuple[str, str, str]]:
        return {(e["from"], e["to"], e["rel"]) for e in graph["edges"]}


class BuildGraphTests(_Workspace):
    def test_every_node_type_is_present_from_its_source(self) -> None:
        graph = manuscript_graph.build_graph(self.workspace())
        self.assertEqual(graph["schema"], manuscript_graph.SCHEMA)
        for kind in NODE_TYPES:
            present = [n for n in self.nodes(graph, kind) if n["status"]["state"] == "present"]
            self.assertTrue(present, kind)
        for node in graph["nodes"]:
            self.assertEqual(set(node) >= {"id", "type", "label", "detail", "source", "paper_blocks",
                                           "status"}, True, node)
        topic = self.nodes(graph, "topic")[0]
        self.assertEqual(topic["label"], "Calibrated pooling for multiple-instance learning")
        self.assertEqual(topic["source"]["path"], "papersmith.yaml")
        self.assertIn("Whole-slide pathology", topic["detail"])
        problem = self.nodes(graph, "problem")[0]
        self.assertEqual(problem["label"], "Attention pooling assigns uncalibrated instance weights.")
        self.assertEqual(problem["source"], {"path": "paper/main.tex",
                                             "locator": "declarations: fact problem-statement"})
        pillars = self.nodes(graph, "pillar")
        self.assertEqual([p["label"] for p in pillars], ["Calibrated attention", "Graph prior"])
        self.assertEqual(pillars[0]["source"]["path"], "proposals/research-concept-pool-r01.sky.json")

    def test_every_edge_type_links_the_expected_nodes(self) -> None:
        graph = manuscript_graph.build_graph(self.workspace())
        edges = self.edge_set(graph)
        expected = {
            ("topic", "problem", "frames"),
            ("problem", "pillar:P1", "decomposes_into"),
            ("problem", "pillar:P2", "decomposes_into"),
            ("pillar:P1", "hypothesis:H1", "predicts"),
            ("sota:sys-a", "pillar:P1", "extends"),
            ("base_concept:eq:mean", "novelty_concept:eq:calibrated", "builds_on"),
            ("novelty_concept:contribution:calibrated attention", "hypothesis:H1", "tested_by"),
            ("hypothesis:H1", "experiment:e1", "tested_in"),
            ("hypothesis:exp-e2", "experiment:e2", "tested_in"),
            ("experiment:e1", "finding:H1", "yields"),
            ("experiment:e2", "finding:H2", "yields"),
            ("finding:H1", "conclusion:conclusions.concl-block-2", "summarized_in"),
        }
        self.assertEqual(expected - edges, set())
        # sys-b has no sky link: it is cited inside mm-proposal, so it reaches the
        # novelty concepts of that block as `cited_by`.
        self.assertIn(("sota:sys-b", "novelty_concept:eq:calibrated", "cited_by"), edges)
        # sys-c is linked by the sky but never cited: no node, no edge.
        self.assertNotIn("sota:sys-c", {n["id"] for n in graph["nodes"]})
        ids = {n["id"] for n in graph["nodes"]}
        for edge in graph["edges"]:
            self.assertIn(edge["from"], ids)
            self.assertIn(edge["to"], ids)

    def test_base_and_novelty_math_split_by_paper_block(self) -> None:
        graph = manuscript_graph.build_graph(self.workspace())
        base = [n for n in self.nodes(graph, "base_concept") if n.get("concept_kind") == "equation"]
        novelty = [n for n in self.nodes(graph, "novelty_concept") if n.get("concept_kind") == "equation"]
        self.assertEqual([n["label"] for n in base], ["eq:mean"])
        self.assertEqual(base[0]["paper_blocks"], ["materials-and-methods.mm-borrowed-machinery"])
        self.assertIn("\\frac{1}{n}", base[0]["detail"])
        self.assertEqual([n["label"] for n in novelty], ["eq:calibrated"])
        self.assertEqual(novelty[0]["paper_blocks"], ["materials-and-methods.mm-proposal"])
        contributions = [n["label"] for n in self.nodes(graph, "novelty_concept")
                         if n.get("concept_kind") == "contribution"]
        self.assertEqual(contributions, ["calibrated attention", "graph prior"])

    def test_an_empty_proposal_block_falls_back_to_the_proposal_equations(self) -> None:
        root = self.workspace()
        tex = root / "paper" / "main.tex"
        text = tex.read_text("utf-8")
        start = text.index("%% paper-writing block materials-and-methods.mm-proposal begin")
        start = text.index("\n", start) + 1
        end = text.index("%% paper-writing block materials-and-methods.mm-proposal end")
        tex.write_text(text[:start] + text[end:], encoding="utf-8")
        graph = manuscript_graph.build_graph(root)
        novelty = [n for n in self.nodes(graph, "novelty_concept") if n.get("concept_kind") == "equation"]
        self.assertEqual([n["source"]["path"] for n in novelty],
                         ["proposals/research-concept-pool-r01.md"] * 2)
        self.assertEqual([n["label"] for n in novelty], ["(1) Borrowed machinery", "(2) Proposal"])

    def test_findings_carry_the_discussion_verdicts(self) -> None:
        graph = manuscript_graph.build_graph(self.workspace())
        findings = {n["id"]: n for n in self.nodes(graph, "finding")}
        self.assertEqual((findings["finding:H1"]["verdict"], findings["finding:H1"]["outcome"]),
                         ("supported", "supported"))
        self.assertEqual((findings["finding:H2"]["verdict"], findings["finding:H2"]["outcome"]),
                         ("not_supported", "refuted"))
        self.assertEqual(findings["finding:novelty"]["outcome"], "supported")
        self.assertEqual(findings["finding:H1"]["source"]["path"],
                         "implementations/repo/Pool/Results/discussion.json")
        self.assertIn("AUC 0.91", findings["finding:H1"]["detail"])
        yields = {e["to"]: e.get("verdict") for e in graph["edges"] if e["rel"] == "yields"}
        self.assertEqual(yields["finding:H2"], "refuted")

    def test_conclusions_are_one_first_sentence_per_block(self) -> None:
        graph = manuscript_graph.build_graph(self.workspace())
        conclusions = self.nodes(graph, "conclusion")
        self.assertEqual([c["label"] for c in conclusions], [
            "We proposed calibrated set pooling.",
            "Calibrated attention reached an AUC of 0.91 on the toy set.",
        ])
        self.assertEqual(conclusions[1]["paper_blocks"], ["conclusions.concl-block-2"])

    def test_sota_nodes_are_the_cited_systems_only(self) -> None:
        graph = manuscript_graph.build_graph(self.workspace())
        sota = {n["id"]: n for n in self.nodes(graph, "sota")}
        self.assertEqual(sorted(sota), ["sota:sys-a", "sota:sys-b"])
        self.assertEqual(sota["sota:sys-a"]["paper_blocks"], ["materials-and-methods.mm-proposal"])

    def test_the_build_is_deterministic_and_carries_input_digests(self) -> None:
        root = self.workspace()
        first = manuscript_graph.build_graph(root)
        self.assertEqual(first, manuscript_graph.build_graph(root))
        self.assertIn("paper/main.tex", first["generated_from"])
        self.assertIn("proposals/research-concept-pool-r01.sky.json", first["generated_from"])


class MissingSourcesTests(_Workspace):
    def test_an_empty_workspace_yields_one_missing_node_per_type(self) -> None:
        graph = manuscript_graph.build_graph(self.empty_workspace())
        for kind in NODE_TYPES:
            nodes = self.nodes(graph, kind)
            self.assertEqual(len(nodes), 1, kind)
            status = nodes[0]["status"]
            self.assertEqual(status["state"], "missing", kind)
            self.assertTrue(status["reason"], kind)
            self.assertTrue(status["phase"], kind)
        self.assertEqual(graph["edges"], [])
        self.assertEqual(graph["summary"]["missing"], list(NODE_TYPES))

    def test_old_sky_files_without_pillars_fall_back_to_the_model_spec(self) -> None:
        root = self.workspace()
        sky_path = root / "proposals" / "research-concept-pool-r01.sky.json"
        sky = json.loads(sky_path.read_text("utf-8"))
        del sky["pillars"], sky["hypotheses"]
        sky_path.write_text(json.dumps(sky), encoding="utf-8")
        graph = manuscript_graph.build_graph(root)
        pillar = self.nodes(graph, "pillar")
        self.assertEqual(pillar[0]["status"]["state"], "missing")
        self.assertIn("proposal-deliberation", pillar[0]["status"]["phase"])
        (root / ".papersmith").mkdir()
        (root / ".papersmith" / "model_spec.json").write_text(json.dumps(
            {"novelty": {"pillars": [{"name": "Spec pillar", "summary": "From the spec."}]}}),
            encoding="utf-8")
        graph = manuscript_graph.build_graph(root)
        pillar = self.nodes(graph, "pillar")
        self.assertEqual([p["label"] for p in pillar], ["Spec pillar"])
        self.assertEqual(pillar[0]["source"]["path"], ".papersmith/model_spec.json")
        # Without sky hypotheses, each protocol experiment brings its own.
        self.assertIn(("hypothesis:exp-e1", "experiment:e1", "tested_in"), self.edge_set(graph))

    def test_a_malformed_pillar_list_is_missing_with_the_refusal(self) -> None:
        root = self.workspace()
        sky_path = root / "proposals" / "research-concept-pool-r01.sky.json"
        sky = json.loads(sky_path.read_text("utf-8"))
        sky["hypotheses"][0]["pillar"] = "P9"
        sky_path.write_text(json.dumps(sky), encoding="utf-8")
        pillar = self.nodes(manuscript_graph.build_graph(root), "pillar")
        self.assertEqual(pillar[0]["status"]["state"], "missing")
        self.assertIn("HYPOTHESIS_PILLAR_UNKNOWN", pillar[0]["status"]["reason"])

    def test_without_the_paper_the_problem_comes_from_the_sky(self) -> None:
        root = self.workspace()
        shutil.rmtree(root / "paper")
        graph = manuscript_graph.build_graph(root)
        problem = self.nodes(graph, "problem")[0]
        self.assertEqual(problem["label"], "Attention weights are uncalibrated")
        self.assertEqual(problem["source"]["locator"], "planet p-problem (slot problem)")
        for kind in ("base_concept", "sota"):
            self.assertEqual(self.nodes(graph, kind)[0]["status"]["state"], "missing", kind)

    def test_an_unparsable_main_tex_degrades_instead_of_raising(self) -> None:
        root = self.workspace()
        (root / "paper" / "main.tex").write_text(
            "%% paper-writing block x begin sha256=zz\n", encoding="utf-8")
        graph = manuscript_graph.build_graph(root)
        base = self.nodes(graph, "base_concept")[0]
        self.assertEqual(base["status"]["state"], "missing")
        self.assertIn("MARKER_MALFORMED", base["status"]["reason"])
        # No conclusion block can be read: the discussion summary stands in.
        conclusion = self.nodes(graph, "conclusion")[0]
        self.assertEqual((conclusion["label"], conclusion["source"]["path"]),
                         ("Calibrated attention helps on the toy set.",
                          "implementations/repo/Pool/Results/discussion.json"))


class WriteReadRefreshTests(_Workspace):
    def test_write_then_read_reports_fresh_then_stale(self) -> None:
        root = self.workspace()
        result = manuscript_graph.write_graph(root)
        self.assertEqual((result["ok"], result["status"], result["path"]),
                         (True, "written", ".papersmith/manuscript_graph.json"))
        stored = json.loads((root / ".papersmith" / "manuscript_graph.json").read_text("utf-8"))
        self.assertEqual(stored, manuscript_graph.build_graph(root))
        self.assertEqual(manuscript_graph.read_graph(root)["stale"], False)
        (root / "paper" / "main.tex").write_text("changed\n", encoding="utf-8")
        read = manuscript_graph.read_graph(root)
        self.assertEqual((read["status"], read["stale"]), ("ok", True))

    def test_read_without_a_file_is_absent(self) -> None:
        self.assertEqual(manuscript_graph.read_graph(self.workspace()),
                         {"status": "absent", "stale": None, "graph": None})

    def test_refresh_is_silent_outside_a_workspace_and_warns_on_error(self) -> None:
        self.assertIsNone(manuscript_graph.refresh(self.empty_workspace()))
        root = self.workspace()
        (root / ".papersmith").write_text("not a directory", encoding="utf-8")
        result = manuscript_graph.refresh(root)
        self.assertEqual((result["ok"], result["status"]), (False, "error"))
        self.assertIn("manuscript graph not rebuilt", result["warning"])

    def test_module_entry_point_writes_and_reports_json(self) -> None:
        root = self.workspace()
        proc = subprocess.run(
            [sys.executable, "-B", "-m", "skills._core.command_center.manuscript_graph",
             "--root", str(root), "--json"], cwd=str(REPO), capture_output=True, text=True,
            timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["status"], "written")


class SmithAtlasSummaryTests(_Workspace):
    def run_smith(self, *argv: str) -> tuple[int, str, str]:
        args = build_parser("smith").parse_args(list(argv))
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = args.handler(args)
        return code, out.getvalue(), err.getvalue()

    def kit_workspace(self) -> Path:
        root = self.workspace()
        shutil.copytree(REPO / "skills", root / "skills",
                        ignore=shutil.ignore_patterns("__pycache__", "node_modules"))
        return root

    def test_smith_atlas_summary_writes_the_graph(self) -> None:
        root = self.kit_workspace()
        code, out, _err = self.run_smith("atlas", "summary", str(root))
        self.assertEqual(code, 0)
        self.assertIn(".papersmith/manuscript_graph.json", out)
        self.assertTrue((root / ".papersmith" / "manuscript_graph.json").is_file())

    def test_smith_atlas_summary_needs_the_kit(self) -> None:
        from papersmith.errors import UserError
        with self.assertRaises(UserError):
            self.run_smith("atlas", "summary", str(self.workspace()))


class RouteTests(_Workspace):
    def test_get_returns_the_stored_graph_with_its_stale_flag(self) -> None:
        root = self.workspace()
        app = server.create_app(root, history_store=None)
        absent = json.loads(_route(app, "/api/atlas/manuscript-graph", "GET")().body)
        self.assertEqual(absent["status"], "absent")
        manuscript_graph.write_graph(root)
        body = json.loads(_route(app, "/api/atlas/manuscript-graph", "GET")().body)
        self.assertEqual((body["status"], body["stale"]), ("ok", False))
        self.assertEqual(body["graph"]["schema"], manuscript_graph.SCHEMA)

    def test_the_view_is_offline_html_with_every_column_and_missing_marks(self) -> None:
        app = server.create_app(self.empty_workspace(), history_store=None)
        response = _route(app, "/api/atlas/manuscript-graph/view", "GET")(lang="en")
        html = response.body.decode("utf-8")
        self.assertTrue(response.media_type.startswith("text/html"))
        self.assertNotIn("https://", html)
        self.assertNotIn("<script src", html)
        for label in ("Topic", "Problem and pillars", "Hypotheses", "Main SOTA",
                      "Base and novelty math", "Experiments", "Findings", "Conclusions"):
            self.assertIn(label, html)
        self.assertIn('class="node node--missing"', html)
        # Labels stay English in the server; each carries the dashboard key that
        # translates it (static/i18n/en.js and es.js hold every one).
        spanish = _route(app, "/api/atlas/manuscript-graph/view", "GET")(lang="es").body.decode()
        self.assertIn('<html lang="es">', spanish)
        catalogues = {lang: (REPO / "skills" / "_core" / "command_center" / "static" / "i18n"
                             / f"{lang}.js").read_text("utf-8") for lang in ("en", "es")}
        import re
        keys = set(re.findall(r'data-i18n="([^"]+)"', spanish))
        self.assertIn("atlas.summaryView.finding", keys)
        for key in keys:
            for lang, text in catalogues.items():
                self.assertIn(f'"{key}"', text, (lang, key))
        self.assertIn('"atlas.summaryView.finding": "Hallazgos"', catalogues["es"])

    def test_the_view_escapes_workspace_text(self) -> None:
        root = self.workspace()
        (root / "papersmith.yaml").write_text("topic: <script>alert(1)</script>\n", encoding="utf-8")
        app = server.create_app(root, history_store=None)
        html = _route(app, "/api/atlas/manuscript-graph/view", "GET")(lang="en").body.decode()
        self.assertNotIn("<script>alert(1)", html)


if __name__ == "__main__":
    unittest.main()
