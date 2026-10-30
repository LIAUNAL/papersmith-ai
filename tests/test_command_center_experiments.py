"""The experiments panel: its read-only view, its route, its tab and its renderer.

The view (``experiments_view.get_experiments_view``) reads the latest
experiments protocol and every product folder under ``implementations/`` and
never raises on what it finds there. The route and ``/api/artifact`` are
exercised through their ASGI endpoints; the renderer runs under node.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from skills._core.command_center import experiments_view, server

STATIC = Path(server.__file__).resolve().parent / "static"
PAGE = (STATIC / "index.html").read_text(encoding="utf-8")
SCRIPT_PATH = STATIC / "experiments-panel.js"

PROTOCOL = """<!-- proposal-workspace:artifact:v1 -->
# A Title

**Validation scheme:** Stratified 5-fold CV with 5 seeds, Wilcoxon signed-rank (p < 0.05)

## Experiment [exp:E1] — Hybrid Classification

- **Hypothesis:** The hybrid model beats the baseline.
- **Success criterion:** Balanced accuracy at least 0.85.
- **Priority:** core
- **Estimated Cost:** 12 GPU hours.

### Expected Report: Experiment E1

| Model Variant | Balanced Acc | F1 |
| :--- | :--- | :--- |
| Hybrid DRU | | |
| Linear | | |

## Experiment [exp:E2] — Ablation

- **Hypothesis:** Entanglement helps.
- **Priority:** ablation

### Expected Report: Experiment E2

| Scheme | F1 |
| :--- | :--- |
| Ring | |
"""


def _routes(app) -> dict:
    return {
        route.path: route.endpoint
        for route in app.routes
        if hasattr(route, "path") and hasattr(route, "endpoint")
    }


def _json(response) -> dict:
    return json.loads(bytes(response.body).decode("utf-8"))


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class Workspace:
    """A temporary workspace with a protocol, a PoC and a full product."""

    def __init__(self, test: unittest.TestCase) -> None:
        holder = tempfile.TemporaryDirectory()
        test.addCleanup(holder.cleanup)
        outside = tempfile.TemporaryDirectory()
        test.addCleanup(outside.cleanup)
        self.root = Path(holder.name).resolve()
        self.outside = Path(outside.name).resolve()
        root = self.root
        _write(root / "experiments" / "experiments-demo-v01.md", "# old\n")
        _write(root / "experiments" / "experiments-demo-v02.md", PROTOCOL)

        poc = root / "implementations" / "repo" / "PocModel"
        _write(poc / "AGREED.md", "agreed\n")
        history = [{"epoch": i, "loss": 1.0 / (i + 1), "val_loss": 1.2 / (i + 1)} for i in range(1200)]
        _write(poc / "Results" / "history.json", json.dumps(history))
        _write(poc / "Results" / "figures" / "curve.svg", "<svg xmlns='http://www.w3.org/2000/svg'/>")
        _write(poc / "Results" / "figures" / "fig.png", "png")
        _write(poc / "Results" / "summary.json", json.dumps({"best": {"acc": 0.9, "loss": 0.1}, "seed": 42}))
        _write(poc / "Results" / "broken.json", "{not json")
        _write(poc / "Results" / "significance-broken.json", "{also not json")
        ledger = [
            {"kind": "submitted", "ts": "2026-10-01T00:00:00Z", "entrypoint": "Notebooks/train.py",
             "submissionId": "s1", "worker": "acct-a"},
            {"kind": "returned", "ts": "2026-10-01T01:00:00Z", "submissionId": "s1",
             "artifactPath": "out"},
            {"kind": "submitted", "ts": "2026-10-02T00:00:00Z", "entrypoint": "Notebooks/eval.py",
             "submissionId": "s2", "worker": "acct-b"},
        ]
        _write(poc / ".remote-execution" / "ledger.jsonl",
               "\n".join(json.dumps(e) for e in ledger) + "\nnot-json\n")

        full = root / "implementations" / "repo" / "FullModel"
        _write(full / "Experimental_AGREED.md", "agreed\n")
        rows = ["epoch,loss,acc,seed,model"]
        for model in ("hybrid", "linear"):
            for seed in (1, 2):
                for epoch in range(5):
                    rows.append(f"{epoch},{1.0 / (epoch + 1)},{0.5 + epoch * 0.1},{seed},{model}")
        _write(full / "Results" / "history.csv", "\n".join(rows) + "\n")
        _write(full / "Results" / "shards" / "a" / "history.jsonl",
               "\n".join(json.dumps({"step": s, "loss": 2.0 - s * 0.1}) for s in range(10)) + "\n")
        _write(full / "Results" / "tables" / "metrics.csv", "model,acc\nhybrid,0.9\nlinear,0.8\n")
        _write(full / "Results" / "tables" / "metrics.md",
               "| model | f1 |\n| --- | --- |\n| hybrid | 0.88 |\n")
        _write(full / "Results" / "significance.json", json.dumps([
            {"comparison": "hybrid vs linear", "test": "wilcoxon", "statistic": 0.0, "p_value": 0.031,
             "p_adjusted": 0.031, "correction": "holm", "effect_size": 0.8,
             "effect_size_name": "rank-biserial", "ci_low": 0.02, "ci_high": 0.12, "n": 25,
             "alpha": 0.05},
        ]))
        _write(full / "Results" / "figures" / "cm.pdf", "%PDF-1.4")
        _write(full / "Results" / "panel.json", json.dumps({"pinned": ["Results/figures/cm.pdf",
                                                                        "../../../../escape.txt"]}))
        # A symlink escaping the workspace is never read nor listed.
        secret = _write(self.outside / "history.json", json.dumps([{"epoch": 0, "loss": 9.0}]))
        os.symlink(secret, full / "Results" / "history-escape.json")
        os.symlink(self.outside, full / "Results" / "figures" / "linked")
        _write(self.outside / "leak.png", "png")


class ViewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ws = Workspace(self)
        self.view = experiments_view.get_experiments_view(self.ws.root)
        self.products = {p["name"]: p for p in self.view["products"]}

    def test_protocol_comes_from_the_latest_revision(self) -> None:
        protocol = self.view["protocol"]
        self.assertEqual(protocol["file"], "experiments/experiments-demo-v02.md")
        self.assertEqual(protocol["revision"], 2)
        self.assertIn("Wilcoxon", protocol["validation_scheme"])
        e1, e2 = protocol["experiments"]
        self.assertEqual((e1["id"], e1["title"], e1["priority"]), ("E1", "Hybrid Classification", "core"))
        self.assertEqual(e1["hypothesis"], "The hybrid model beats the baseline.")
        self.assertEqual(e1["success_criterion"], "Balanced accuracy at least 0.85.")
        self.assertEqual(e1["cost"], "12 GPU hours.")
        report = e1["expected_reports"][0]
        self.assertEqual(report["headers"], ["Model Variant", "Balanced Acc", "F1"])
        self.assertEqual(report["rows"][0], ["Hybrid DRU", "", ""])
        self.assertEqual(e2["id"], "E2")
        self.assertEqual(e2["expected_reports"][0]["rows"], [["Ring", ""]])

    def test_products_are_classified_by_their_agreement_file(self) -> None:
        self.assertEqual(self.products["PocModel"]["kind"], "poc")
        self.assertEqual(self.products["FullModel"]["kind"], "full")
        self.assertEqual(self.products["PocModel"]["path"], "implementations/repo/PocModel")

    def test_convergence_series_are_parsed_and_downsampled(self) -> None:
        conv = self.products["PocModel"]["convergence"]
        self.assertEqual(len(conv), 1)
        self.assertEqual(conv[0]["x_key"], "epoch")
        names = sorted(s["name"] for s in conv[0]["series"])
        self.assertEqual(names, ["loss", "val_loss"])
        for series in conv[0]["series"]:
            self.assertLessEqual(len(series["points"]), experiments_view.MAX_POINTS)
            self.assertEqual(series["points"][0][0], 0)
            self.assertEqual(series["points"][-1][0], 1199)

    def test_grouped_csv_and_shard_histories(self) -> None:
        conv = {c["file"].rsplit("/", 1)[-1]: c for c in self.products["FullModel"]["convergence"]}
        self.assertIn("history.csv", conv)
        self.assertIn("history.jsonl", conv)
        groups = {(s["name"], s["group"]) for s in conv["history.csv"]["series"]}
        self.assertIn(("loss", "model=hybrid, seed=1"), groups)
        self.assertIn(("acc", "model=linear, seed=2"), groups)
        self.assertEqual(len(groups), 8)
        self.assertEqual(conv["history.jsonl"]["x_key"], "step")

    def test_figures_tables_significance_and_pinned(self) -> None:
        full = self.products["FullModel"]
        self.assertEqual(full["figures"], ["implementations/repo/FullModel/Results/figures/cm.pdf"])
        tables = {t["path"].rsplit("/", 1)[-1]: t for t in full["tables"]}
        self.assertEqual(tables["metrics.csv"]["headers"], ["model", "acc"])
        self.assertEqual(tables["metrics.csv"]["rows"], [["hybrid", "0.9"], ["linear", "0.8"]])
        self.assertEqual(tables["metrics.md"]["rows"], [["hybrid", "0.88"]])
        self.assertEqual(full["significance"][0]["test"], "wilcoxon")
        self.assertAlmostEqual(full["significance"][0]["p_adjusted"], 0.031)
        self.assertEqual(full["pinned"], ["implementations/repo/FullModel/Results/figures/cm.pdf"])
        poc = self.products["PocModel"]
        summary = [t for t in poc["tables"] if t["path"].endswith("summary.json")][0]
        self.assertIn(["best.acc", "0.9"], summary["rows"])
        self.assertEqual(sorted(p.rsplit("/", 1)[-1] for p in poc["figures"]), ["curve.svg", "fig.png"])

    def test_malformed_files_become_warnings(self) -> None:
        text = "\n".join(self.view["warnings"])
        self.assertIn("significance-broken.json", text)
        poc_text = "\n".join(self.products["PocModel"]["warnings"])
        self.assertIn("significance-broken.json", poc_text)

    def test_symlinks_escaping_the_workspace_are_ignored(self) -> None:
        payload = json.dumps(self.view)
        self.assertNotIn("history-escape", json.dumps(self.products["FullModel"]["convergence"]))
        self.assertNotIn("leak.png", payload)
        self.assertNotIn(str(self.ws.outside), payload)
        self.assertNotIn("escape.txt", json.dumps(self.products["FullModel"]["pinned"]))

    def test_runs_are_folded_from_the_ledger(self) -> None:
        runs = self.products["PocModel"]["runs"]
        self.assertEqual(runs["count"], 2)
        self.assertEqual(runs["by_state"], {"returned": 1, "submitted": 1})
        self.assertEqual(runs["latest"][0]["entrypoint"], "Notebooks/eval.py")
        self.assertEqual(self.products["FullModel"]["runs"]["count"], 0)

    def test_an_empty_workspace_is_a_valid_view(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        view = experiments_view.get_experiments_view(holder.name)
        self.assertIsNone(view["protocol"])
        self.assertEqual(view["products"], [])
        self.assertIn("remote_accounts", view)


REGISTRY = [
    {"slug": "toy-eeg", "role": "toy", "title": "Toy eeg set (toy-eeg)",
     "source": {"kind": "synthetic", "url": "", "retrieved": "2026-10-24"},
     "license": {"source_name": "generated", "decision": "allowed", "host_license": "CC0-1.0"},
     "files": ["datasets/toy-eeg/toy-eeg.csv"], "qc": {"status": "pass", "report": "datasets/toy-eeg/qc.json"},
     "preparation": {"manifest": "datasets/toy-eeg/PREPARATION.md", "version": 2},
     "remote": {"ref": "someone/toy-eeg", "visibility": "private", "version": 1}},
    {"slug": "bci-iv", "role": "full", "title": "<script>alert(1)</script>",
     "source": {"kind": "external", "url": "https://example.org", "retrieved": "2026-10-24"},
     "license": {"source_name": "CC BY-NC 4.0", "decision": "refused", "host_license": "CC-BY-NC-4.0"},
     "files": [], "qc": None, "preparation": None, "remote": None},
]


class PerExperimentResultsTests(unittest.TestCase):
    """A product that keeps one folder per experiment under ``Results/``.

    Figures and tables live in ``Results/<experiment>/figures`` and
    ``Results/<experiment>/tables``, a summary in ``Results/<experiment>/summary.json``,
    and hundreds of run records under ``Results/<experiment>/runs/`` that the panel
    never shows.
    """

    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.root = Path(holder.name).resolve()
        self.product = self.root / "implementations" / "repo" / "Deep"
        results = self.product / "Results"
        (self.product / "Experimental_AGREED.md").parent.mkdir(parents=True)
        (self.product / "Experimental_AGREED.md").write_text("# Agreed\n", encoding="utf-8")
        for experiment in ("e1", "e2"):
            runs = results / experiment / "runs" / "arm"
            runs.mkdir(parents=True)
            for i in range(150):
                (runs / f"s{i}.json").write_text("{}", encoding="utf-8")
        for experiment in ("e1", "e2"):
            (results / experiment / "figures").mkdir(parents=True)
            (results / experiment / "figures" / f"{experiment}-convergence.png").write_bytes(b"\x89PNG")
            (results / experiment / "tables").mkdir(parents=True)
            (results / experiment / "tables" / f"{experiment}.md").write_text(
                "| arm | acc |\n|---|---|\n| dru | 0.9 |\n", encoding="utf-8")
            (results / experiment / "summary.json").write_text(json.dumps({"met": True}), encoding="utf-8")
        (results / "figures").mkdir()
        (results / "figures" / "top.png").write_bytes(b"\x89PNG")

    def product_view(self) -> dict:
        view = experiments_view.get_experiments_view(self.root)
        return next(p for p in view["products"] if p["name"] == "Deep")

    def test_figures_and_tables_inside_an_experiment_folder_are_shown(self) -> None:
        product = self.product_view()
        base = "implementations/repo/Deep/Results/"
        self.assertIn(base + "e1/figures/e1-convergence.png", product["figures"])
        self.assertIn(base + "e2/figures/e2-convergence.png", product["figures"])
        self.assertIn(base + "figures/top.png", product["figures"])
        paths = [t["path"] for t in product["tables"]]
        for experiment in ("e1", "e2"):
            self.assertIn(base + f"{experiment}/tables/{experiment}.md", paths)
            self.assertIn(base + f"{experiment}/summary.json", paths)

    def test_run_records_do_not_use_up_the_file_cap(self) -> None:
        product = self.product_view()
        self.assertIn("implementations/repo/Deep/Results/e2/figures/e2-convergence.png", product["figures"])
        self.assertFalse(any("only the first" in w for w in product["warnings"]), product["warnings"])

    def test_the_walk_itself_stays_bounded(self) -> None:
        original = experiments_view.MAX_SCANNED_FILES
        experiments_view.MAX_SCANNED_FILES = 50
        self.addCleanup(setattr, experiments_view, "MAX_SCANNED_FILES", original)
        product = self.product_view()
        self.assertTrue(any("files were visited" in w for w in product["warnings"]), product["warnings"])

    def test_a_deeper_summary_is_not_read_as_a_table(self) -> None:
        archived = self.product / "Results" / "e1" / "v05"
        archived.mkdir()
        (archived / "summary.json").write_text(json.dumps({"old": 1}), encoding="utf-8")
        paths = [t["path"] for t in self.product_view()["tables"]]
        self.assertNotIn("implementations/repo/Deep/Results/e1/v05/summary.json", paths)


class DatasetsViewTests(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.root = Path(holder.name).resolve()

    def test_registry_summary_is_read(self) -> None:
        _write(self.root / "datasets" / "registry.json", json.dumps(REGISTRY))
        _write(self.root / "datasets" / "search-2026-10-24.json", "{}")
        view = experiments_view.get_experiments_view(self.root)
        datasets = view["datasets"]
        self.assertEqual(datasets["registry"], "datasets/registry.json")
        self.assertEqual(datasets["searches"], ["datasets/search-2026-10-24.json"])
        items = {item["slug"]: item for item in datasets["items"]}
        self.assertEqual(list(items), ["bci-iv", "toy-eeg"])
        toy = items["toy-eeg"]
        self.assertEqual(toy, {"slug": "toy-eeg", "role": "toy", "title": "Toy eeg set (toy-eeg)",
                               "license": "allowed", "host_license": "CC0-1.0", "qc": "pass",
                               "prepared": True, "preparation_version": 2,
                               "remote_ref": "someone/toy-eeg", "visibility": "private",
                               "remote_version": 1})
        self.assertIsNone(items["bci-iv"]["qc"])
        self.assertIsNone(items["bci-iv"]["remote_ref"])

    def test_absent_or_malformed_registry_never_raises(self) -> None:
        view = experiments_view.get_experiments_view(self.root)
        self.assertEqual(view["datasets"]["items"], [])
        self.assertIsNone(view["datasets"]["registry"])
        _write(self.root / "datasets" / "registry.json", "{not json")
        view = experiments_view.get_experiments_view(self.root)
        self.assertEqual(view["datasets"]["items"], [])
        self.assertTrue(any("registry.json" in w for w in view["warnings"]))
        _write(self.root / "datasets" / "registry.json", json.dumps([{"no": "slug"}, "junk", REGISTRY[0]]))
        view = experiments_view.get_experiments_view(self.root)
        self.assertEqual([item["slug"] for item in view["datasets"]["items"]], ["toy-eeg"])

    def test_a_symlinked_registry_escaping_the_workspace_is_not_read(self) -> None:
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        secret = _write(Path(outside.name) / "registry.json", json.dumps(REGISTRY))
        (self.root / "datasets").mkdir()
        os.symlink(secret, self.root / "datasets" / "registry.json")
        view = experiments_view.get_experiments_view(self.root)
        self.assertEqual(view["datasets"]["items"], [])


class RouteTests(unittest.TestCase):
    def test_route_returns_the_view_and_artifact_serves_svg_and_csv(self) -> None:
        ws = Workspace(self)
        routes = _routes(server.create_app(ws.root))
        payload = _json(routes["/api/experiments"]())
        self.assertEqual(len(payload["products"]), 2)
        svg = routes["/api/artifact"](path="implementations/repo/PocModel/Results/figures/curve.svg")
        self.assertEqual(svg.media_type, "image/svg+xml")
        csv = routes["/api/artifact"](path="implementations/repo/FullModel/Results/tables/metrics.csv")
        self.assertTrue(csv.media_type.startswith("text/plain"))  # unchanged: CSV stays readable in a tab


class PageTests(unittest.TestCase):
    def test_the_tab_sits_between_model_and_sections(self) -> None:
        modelo = PAGE.index("navigateTab('modelo')")
        experiments = PAGE.index("navigateTab('experiments')")
        sections = PAGE.index("navigateTab('sections')")
        self.assertLess(modelo, experiments)
        self.assertLess(experiments, sections)
        self.assertLess(PAGE.index('id="pane-experiments"'), PAGE.index('id="pane-sections"'))

    def test_the_script_is_loaded_and_the_tab_refreshes_it(self) -> None:
        self.assertIn('<script src="./experiments-panel.js?v=', PAGE)
        start = PAGE.index("function navigateTab(tabId)")
        body = PAGE[start:PAGE.index("function filterModelView")]
        self.assertIn("tabId === 'experiments'", body)
        self.assertIn("window.refreshExperimentsPanel?.()", body)
        self.assertIn("'experiments'", PAGE[PAGE.index("// Hash routing on load"):])


def _hpo_summary(study: str, **over) -> dict:
    arm, _, fold = study.partition("-fold")
    summary = {
        "schema": 1, "study": study, "arm": arm, "fold": int(fold) if fold else None,
        "objective": {"metric": "val_balanced_accuracy", "direction": "maximize"},
        "sampler": {"name": "TPESampler", "seed": 42}, "pruner": "MedianPruner",
        "nTrials": 40, "complete": 31, "pruned": 8, "failed": 1, "bestValue": 0.8125,
        "bestParams": {"lr": 0.001, "layers": 3},
        "space": [{"name": "lr", "kind": "float", "low": 1e-4, "high": 1e-1, "log": True}],
        "importance": {"evaluator": "fanova", "seed": 7, "values": {"lr": 0.72, "layers": 0.28}},
        "importanceCheck": {"evaluator": "ped-anova", "values": {"lr": 0.6, "layers": 0.4}},
        "contourParams": ["lr", "layers"],
        "figures": {"contour": "contour.png", "importance": "importance.png", "history": "history.png"},
        "optunaVersion": "5.0.0", "generatedAt": "2026-10-25T00:00:00Z",
    }
    summary.update(over)
    return summary


class HpoViewTests(unittest.TestCase):
    """``Results/hpo/<study>/summary.json`` (schema 1) becomes ``product["hpo"]``."""

    def setUp(self) -> None:
        self.ws = Workspace(self)
        self.full = self.ws.root / "implementations" / "repo" / "FullModel"
        self.hpo = self.full / "Results" / "hpo"
        study = self.hpo / "hybrid-fold1"
        _write(study / "summary.json", json.dumps(_hpo_summary("hybrid-fold1")))
        for name in ("contour.png", "importance.png", "history.png"):
            _write(study / name, "png")
        _write(self.hpo / "linear-fold1" / "summary.json", json.dumps(_hpo_summary(
            "linear-fold1", complete=1, pruned=0, failed=0, bestValue=0.5,
            figures={"contour": None, "importance": None, "history": "history.png"},
            notes=["contour: fewer than two complete trials"])))
        _write(self.hpo / "linear-fold1" / "history.png", "png")
        _write(self.hpo / "broken-fold1" / "summary.json", "{not json")
        _write(self.hpo / "old-fold1" / "summary.json", json.dumps(_hpo_summary("old-fold1", schema=2)))
        # A summary whose study folder links outside the workspace is never read.
        outside = self.ws.outside / "esc-fold1"
        _write(outside / "summary.json", json.dumps(_hpo_summary("esc-fold1")))
        os.symlink(self.ws.outside / "esc-fold1" / "summary.json", self.hpo / "esc-summary-link.json")
        _write(self.hpo / "leaky-fold1" / "summary.json", json.dumps(_hpo_summary(
            "leaky-fold1", figures={"contour": "../../../../../../../escape.png", "importance": "/etc/x.png",
                                     "history": None})))
        os.symlink(outside / "summary.json", self.hpo / "leaky-fold1" / "linked.json")
        (self.hpo / "linked-fold1").mkdir()
        os.symlink(outside / "summary.json", self.hpo / "linked-fold1" / "summary.json")
        self.view = experiments_view.get_experiments_view(self.ws.root)
        self.product = next(p for p in self.view["products"] if p["name"] == "FullModel")
        self.studies = {h["study"]: h for h in self.product["hpo"]}

    def test_summaries_are_read_with_workspace_relative_figures(self) -> None:
        entry = self.studies["hybrid-fold1"]
        base = "implementations/repo/FullModel/Results/hpo/hybrid-fold1"
        self.assertEqual(entry["figures"], {"contour": f"{base}/contour.png",
                                            "importance": f"{base}/importance.png",
                                            "history": f"{base}/history.png"})
        self.assertEqual((entry["arm"], entry["fold"]), ("hybrid", 1))
        self.assertEqual((entry["nTrials"], entry["complete"], entry["pruned"], entry["failed"]),
                         (40, 31, 8, 1))
        self.assertEqual(entry["bestValue"], 0.8125)
        self.assertEqual(entry["bestParams"], {"lr": 0.001, "layers": 3})
        self.assertEqual(entry["objective"], {"metric": "val_balanced_accuracy", "direction": "maximize"})
        self.assertEqual(entry["importance"], {"evaluator": "fanova", "values": {"lr": 0.72, "layers": 0.28}})
        self.assertEqual(entry["importanceCheck"]["evaluator"], "ped-anova")
        self.assertEqual(entry["contourParams"], ["lr", "layers"])
        self.assertEqual(entry["file"], f"{base}/summary.json")
        self.assertEqual(entry["notes"], [])

    def test_hpo_figures_are_not_repeated_in_the_generic_lists(self) -> None:
        payload = json.dumps(self.product["figures"]) + json.dumps(self.product["tables"]) \
            + json.dumps(self.product["convergence"])
        self.assertNotIn("Results/hpo", payload)

    def test_a_null_figure_keeps_its_notes(self) -> None:
        entry = self.studies["linear-fold1"]
        self.assertIsNone(entry["figures"]["contour"])
        self.assertIsNone(entry["figures"]["importance"])
        self.assertTrue(entry["figures"]["history"].endswith("hpo/linear-fold1/history.png"))
        self.assertEqual(entry["notes"], ["contour: fewer than two complete trials"])

    def test_malformed_or_other_schema_summaries_become_warnings(self) -> None:
        self.assertNotIn("broken-fold1", self.studies)
        self.assertNotIn("old-fold1", self.studies)
        text = "\n".join(self.product["warnings"])
        self.assertIn("broken-fold1/summary.json: malformed JSON", text)
        self.assertIn("old-fold1/summary.json: not a schema-1 hyperparameter summary", text)

    def test_links_escaping_the_workspace_are_ignored(self) -> None:
        self.assertNotIn("esc-fold1", self.studies)
        self.assertNotIn("linked-fold1", self.studies)
        leaky = self.studies["leaky-fold1"]
        self.assertEqual(leaky["figures"], {"contour": None, "importance": None, "history": None})
        payload = json.dumps(self.view)
        self.assertNotIn(str(self.ws.outside), payload)
        self.assertNotIn("escape.png", payload)

    def test_the_number_of_studies_is_capped(self) -> None:
        for k in range(experiments_view.MAX_HPO_STUDIES + 3):
            _write(self.hpo / f"arm{k:03d}-fold1" / "summary.json",
                   json.dumps(_hpo_summary(f"arm{k:03d}-fold1")))
        view = experiments_view.get_experiments_view(self.ws.root)
        product = next(p for p in view["products"] if p["name"] == "FullModel")
        self.assertEqual(len(product["hpo"]), experiments_view.MAX_HPO_STUDIES)
        self.assertIn(f"capped at {experiments_view.MAX_HPO_STUDIES}", "\n".join(product["warnings"]))

    def test_a_product_without_a_search_has_an_empty_list(self) -> None:
        poc = next(p for p in self.view["products"] if p["name"] == "PocModel")
        self.assertEqual(poc["hpo"], [])


@unittest.skipUnless(shutil.which("node"), "node is required to run the panel renderer")
class RenderTests(unittest.TestCase):
    def render(self, view: dict) -> str:
        i18n_js = SCRIPT_PATH.parent / "i18n.js"
        en_js = SCRIPT_PATH.parent / "i18n" / "en.js"
        es_js = SCRIPT_PATH.parent / "i18n" / "es.js"
        script = (
            "const fs=require('fs');"
            "global.window={localStorage:{getItem:()=>'es',setItem:()=>{}}};"
            "global.document={addEventListener(){},querySelectorAll:()=>[]};"
            f"eval(fs.readFileSync({json.dumps(str(en_js))},'utf8'));"
            f"eval(fs.readFileSync({json.dumps(str(es_js))},'utf8'));"
            f"eval(fs.readFileSync({json.dumps(str(i18n_js))},'utf8'));"
            f"eval(fs.readFileSync({json.dumps(str(SCRIPT_PATH))},'utf8'));"
            "console.log(window.ExperimentsPanel.render(JSON.parse(fs.readFileSync(0,'utf8'))));"
        )
        return subprocess.run(["node", "-e", script], input=json.dumps(view), capture_output=True,
                              text=True, cwd=tempfile.gettempdir(), check=True).stdout

    def test_renders_help_charts_sections_and_escapes(self) -> None:
        ws = Workspace(self)
        view = experiments_view.get_experiments_view(ws.root)
        view["products"][0]["name"] = "<img src=x onerror=alert(1)>"
        out = self.render(view)
        self.assertIn("Ayuda: lanzar y monitorear en Kaggle (CLI o MCP)", out)
        self.assertIn("<details", out)
        self.assertIn("<svg", out)
        self.assertIn("<polyline", out)
        self.assertIn("Prueba de concepto", out)
        self.assertIn("Experimentos completos", out)
        self.assertIn("NvidiaTeslaT4", out)
        self.assertIn("remote_cli.py", out)
        self.assertIn("https://www.kaggle.com/mcp", out)
        self.assertIn("/api/artifact?path=", out)
        self.assertIn("wilcoxon", out)
        self.assertIn("pendiente", out.lower())
        self.assertNotIn("<img src=x", out)

    def test_renders_the_datasets_section_with_badges_and_escapes(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        _write(Path(holder.name) / "datasets" / "registry.json", json.dumps(REGISTRY))
        view = experiments_view.get_experiments_view(holder.name)
        out = self.render(view)
        self.assertIn("Datasets (toy y completos)", out)
        self.assertIn("toy-eeg", out)
        self.assertIn("someone/toy-eeg", out)
        self.assertIn("privado", out)
        self.assertIn("badge--ok", out)
        self.assertIn("rechazada", out)
        self.assertNotIn("<script>alert(1)</script>", out)
        self.assertIn("&lt;script&gt;", out)

    def test_datasets_empty_state_names_the_verbs(self) -> None:
        out = self.render({"protocol": None, "products": [], "warnings": [], "remote_accounts": {},
                           "datasets": {"items": [], "registry": None, "searches": []}})
        self.assertIn("Datasets (toy y completos)", out)
        self.assertIn("/datasets synth", out)
        self.assertIn("/datasets search", out)

    def test_renders_the_hyperparameter_search_section_and_escapes(self) -> None:
        ws = Workspace(self)
        study = ws.root / "implementations" / "repo" / "FullModel" / "Results" / "hpo" / "hybrid-fold1"
        _write(study / "summary.json", json.dumps(_hpo_summary(
            "hybrid-fold1", bestParams={"<b>lr</b>": "<script>alert(1)</script>"},
            figures={"contour": None, "importance": "importance.png", "history": "history.png"},
            notes=["contour: <i>one parameter</i>"])))
        for name in ("importance.png", "history.png"):
            _write(study / name, "png")
        out = self.render(experiments_view.get_experiments_view(ws.root))
        self.assertIn("Búsqueda de hiperparámetros (Optuna)", out)
        self.assertEqual(out.count("Búsqueda de hiperparámetros (Optuna)</h4>"), 1)
        self.assertIn("hybrid-fold1", out)
        self.assertIn("31 / 8", out)
        self.assertIn("val_balanced_accuracy", out)
        self.assertIn("maximizar", out)
        self.assertIn("fANOVA", out)
        self.assertIn("exp-hpo-bar", out)
        self.assertIn("hpo%2Fhybrid-fold1%2Fimportance.png", out)
        self.assertIn("hpo%2Fhybrid-fold1%2Fhistory.png", out)
        self.assertIn("contour: &lt;i&gt;one parameter&lt;/i&gt;", out)
        self.assertNotIn("<script>alert(1)</script>", out)
        self.assertNotIn("<b>lr</b>", out)
        self.assertIn("/hyperparameter-search plan|report|status", out)

    def test_the_search_section_is_absent_without_studies(self) -> None:
        out = self.render(experiments_view.get_experiments_view(Workspace(self).root))
        self.assertNotIn("Búsqueda de hiperparámetros (Optuna)</h4>", out)

    def test_empty_view_names_what_produces_the_charts(self) -> None:
        out = self.render({"protocol": None, "products": [], "warnings": [], "remote_accounts": {}})
        self.assertIn("Results/history", out)
        self.assertIn("Ayuda: lanzar y monitorear en Kaggle (CLI o MCP)", out)

    def test_execution_monitor_parses_ladder_and_computes_eta(self) -> None:
        ws = Workspace(self)
        full_dir = ws.root / "implementations" / "repo" / "FullModel"
        ladder = """# Agreed
## Ladder
- [x] 1. Rehearse HPO. `@rehearsal hpo_search`
- [x] 2. Run nested HPO search. `@notebook Notebooks/hpo.ipynb`
- [ ] 3. Run E1. `@step e1_run`
"""
        _write(full_dir / "Experimental_AGREED.md", ladder)
        view = experiments_view.get_experiments_view(ws.root)
        prod = next(p for p in view["products"] if p["name"] == "FullModel")
        m = prod.get("execution_monitor")
        self.assertIsNotNone(m)
        self.assertEqual(m["total_stages"], 3)
        self.assertEqual(m["completed_stages"], 2)
        self.assertEqual(m["progress_percent"], 66.7)
        self.assertIn("Run E1", m["current_stage"])
        self.assertEqual(m["stages"][2]["step"], "e1_run")
        self.assertGreater(m["remaining_seconds"], 0)
        self.assertIsNotNone(m["estimated_completion_iso"])

    def test_renders_execution_monitor_card(self) -> None:
        ws = Workspace(self)
        full_dir = ws.root / "implementations" / "repo" / "FullModel"
        ladder = """# Agreed
## Ladder
- [x] 1. Rehearse HPO. `@rehearsal hpo_search`
- [ ] 2. Run E1. `@step e1_run`
"""
        _write(full_dir / "Experimental_AGREED.md", ladder)
        out = self.render(experiments_view.get_experiments_view(ws.root))
        self.assertIn("exp-monitor-card", out)
        self.assertIn("Monitor de Ejecución", out)
        self.assertIn("Finalización estimada", out)

    def discussed(self) -> Workspace:
        ws = Workspace(self)
        poc = _discussion(summary="<script>alert(1)</script> hybrid wins",
                          discussion_type=["comparative", "cost"])
        poc["hypotheses"][0]["statement"] = "<img src=x onerror=alert(2)> beats linear"
        poc["hypotheses"].append({"id": "H2", "statement": "Only at PoC.", "verdict": "pending"})
        poc["qualitative"] = [{"title": "Saliency map", "kind": "interpretability", "method": "Grad-CAM",
                               "figure": "Results/qualitative/saliency.png", "reading": "Focus on C3."}]
        poc.pop("qualitative_not_applicable")
        _write(ws.root / "implementations" / "repo" / "PocModel" / "Results" / "qualitative" / "saliency.png", "png")
        _write(ws.root / "implementations" / "repo" / "PocModel" / "Results" / "qualitative" / "extra.png", "png")
        _put_discussion(ws, "PocModel", poc)
        full = _discussion("full")
        full["hypotheses"][0]["verdict"] = "not_supported"
        _put_discussion(ws, "FullModel", full)
        return ws

    def test_the_product_card_opens_with_the_discussion_block(self) -> None:
        out = self.render(experiments_view.get_experiments_view(self.discussed().root))
        self.assertIn("Resumen y discusión", out)
        self.assertLess(out.index("Resumen y discusión"), out.index("Convergencia"))
        for text in ("hybrid wins", "comparative", "cost", "balanced_accuracy", "wilcoxon", "&gt;= 0.85",
                     "Grad-CAM", "Focus on C3.", "Saliency map", "A new encoding.", "Small sample.",
                     "More seeds."):
            self.assertIn(text, out)
        # The two figures under Results/qualitative: the referenced one and the unreferenced one.
        self.assertIn("qualitative%2Fsaliency.png", out)
        self.assertIn("qualitative%2Fextra.png", out)
        # One artifact renders its URL twice (link and image); the referenced figure is not repeated.
        self.assertEqual(out.count("qualitative%2Fsaliency.png"), 2)
        self.assertEqual(out.count("qualitative%2Fextra.png"), 2)
        self.assertIn("significance:hybrid vs linear", out)

    def test_verdicts_and_statuses_are_badges_in_spanish(self) -> None:
        out = self.render(experiments_view.get_experiments_view(self.discussed().root))
        for label in ("soportada", "pendiente", "no soportada", "justificada"):
            self.assertIn(label, out)
        self.assertRegex(out, r'badge--ok[^>]*>[^<]*soportada')
        self.assertRegex(out, r'badge--bad[^>]*>[^<]*no soportada')
        self.assertIn("completa", out)

    def test_a_draft_and_an_invalid_status_show_their_badge_and_errors(self) -> None:
        ws = Workspace(self)
        draft = _discussion()
        draft["hypotheses"][0].update(verdict="pending", evidence=[])
        _put_discussion(ws, "PocModel", draft)
        _put_discussion(ws, "FullModel", _discussion("full", summary=""))
        out = self.render(experiments_view.get_experiments_view(ws.root))
        self.assertIn("badge--warn", out)
        self.assertIn("borrador", out)
        self.assertIn("inválida", out)
        self.assertIn("summary", out)

    def test_the_absent_discussion_names_the_scaffold_and_check_commands(self) -> None:
        out = self.render(experiments_view.get_experiments_view(Workspace(self).root))
        self.assertIn("Resumen y discusión", out)
        self.assertIn("python skills/_core/results/discussion_cli.py scaffold --product "
                      "implementations/repo/PocModel", out)
        self.assertIn("discussion_cli.py check --product implementations/repo/FullModel", out)

    def test_the_stage_comparison_follows_the_full_group(self) -> None:
        out = self.render(experiments_view.get_experiments_view(self.discussed().root))
        self.assertIn("PoC vs experimentos completos", out)
        self.assertGreater(out.index("PoC vs experimentos completos"), out.index("Experimentos completos"))
        section = out[out.index("PoC vs experimentos completos"):]
        self.assertIn("PocModel", section)
        self.assertIn("FullModel", section)
        self.assertIn("H2", section)
        plain = self.render(experiments_view.get_experiments_view(Workspace(self).root))
        self.assertNotIn("PoC vs experimentos completos", plain)

    def test_the_discussion_is_escaped(self) -> None:
        out = self.render(experiments_view.get_experiments_view(self.discussed().root))
        self.assertNotIn("<script>alert(1)</script>", out)
        self.assertNotIn("<img src=x", out)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt; hybrid wins", out)
        self.assertIn("&lt;img src=x onerror=alert(2)&gt; beats linear", out)

    def test_a_not_applicable_reason_is_shown_without_a_gallery(self) -> None:
        ws = Workspace(self)
        _put_discussion(ws, "PocModel", _discussion())
        out = self.render(experiments_view.get_experiments_view(ws.root))
        self.assertIn("No interpretability method applies.", out)

    def test_the_significance_table_gains_hypothesis_and_experiment_columns(self) -> None:
        ws = Workspace(self)
        full = ws.root / "implementations" / "repo" / "FullModel" / "Results"
        _write(full / "significance.json", json.dumps([
            {"comparison": "hybrid vs linear", "test": "wilcoxon", "p_value": 0.03,
             "hypothesis": "H1", "experiment": "E1"}]))
        with_columns = self.render(experiments_view.get_experiments_view(ws.root))
        self.assertIn("<th>Hipótesis</th><th>Experimento</th>", with_columns)
        without = self.render(experiments_view.get_experiments_view(Workspace(self).root))
        self.assertNotIn("<th>Hipótesis</th>", without)



def _discussion(stage: str = "poc", **over) -> dict:
    """A discussion that the shared check calls complete for the ``Workspace`` products."""
    evidence = (["significance:hybrid vs linear", "Results/figures/cm.pdf"] if stage == "full"
                else ["Results/figures/fig.png"])
    data = {
        "schema": 1, "stage": stage, "protocol": "experiments/experiments-demo-v02.md",
        "generated_at": "2026-10-30T00:00:00+00:00",
        "summary": "The hybrid model beats the baseline.",
        "discussion_type": ["comparative", "ablation"],
        "metrics": [{"name": "balanced_accuracy", "role": "primary", "why": "Balanced classes.",
                     "source": "Results/tables/metrics.csv"}],
        "hypotheses": [{"id": "H1", "experiment": "E1", "statement": "Hybrid beats linear.",
                        "metric": "balanced_accuracy", "test": "wilcoxon", "criterion": ">= 0.85",
                        "observed": "0.90", "evidence": list(evidence), "verdict": "supported",
                        "rationale": "The criterion is met."}],
        "novelty": {"claim": "A new encoding.", "verdict": "justified", "evidence": list(evidence),
                    "rationale": "Beats the baseline."},
        "qualitative": [],
        "qualitative_not_applicable": "No interpretability method applies.",
        "limitations": ["Small sample."], "next_steps": ["More seeds."],
    }
    data.update(over)
    return data


def _put_discussion(ws: "Workspace", product: str, data: dict) -> Path:
    path = ws.root / "implementations" / "repo" / product / "Results" / "discussion.json"
    return _write(path, json.dumps(data))


class DiscussionViewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ws = Workspace(self)

    def products(self) -> dict:
        view = experiments_view.get_experiments_view(self.ws.root)
        return {p["name"]: p for p in view["products"]}

    def test_a_product_without_a_discussion_has_none(self) -> None:
        products = self.products()
        self.assertIsNone(products["PocModel"]["discussion"])
        self.assertIsNone(products["FullModel"]["discussion"])
        self.assertEqual(experiments_view.get_experiments_view(self.ws.root)["stage_comparison"], [])

    def test_an_overlong_summary_is_invalid_and_shown_clipped(self) -> None:
        _put_discussion(self.ws, "PocModel", _discussion(summary="S" * 3000))
        d = self.products()["PocModel"]["discussion"]
        self.assertEqual((d["status"], d["errors"]), ("invalid", ["summary: longer than 2000 characters"]))
        self.assertEqual(len(d["summary"]), 2000)

    def test_a_complete_discussion_is_carried_and_linked(self) -> None:
        _put_discussion(self.ws, "PocModel", _discussion())
        d = self.products()["PocModel"]["discussion"]
        self.assertEqual(d["file"], "implementations/repo/PocModel/Results/discussion.json")
        self.assertEqual((d["status"], d["stage"], d["errors"]), ("complete", "poc", []))
        self.assertEqual(d["summary"], "The hybrid model beats the baseline.")
        self.assertEqual(d["discussion_type"], ["comparative", "ablation"])
        self.assertEqual(d["metrics"][0]["name"], "balanced_accuracy")
        h = d["hypotheses"][0]
        self.assertEqual((h["id"], h["experiment"], h["verdict"]), ("H1", "E1", "supported"))
        self.assertEqual(h["evidence"], [{"ref": "Results/figures/fig.png",
                                          "path": "implementations/repo/PocModel/Results/figures/fig.png"}])
        self.assertEqual(d["novelty"]["verdict"], "justified")
        self.assertEqual(d["novelty"]["evidence"][0]["path"],
                         "implementations/repo/PocModel/Results/figures/fig.png")
        self.assertEqual(d["qualitative"], [])
        self.assertEqual(d["qualitative_not_applicable"], "No interpretability method applies.")
        self.assertEqual((d["limitations"], d["next_steps"]), (["Small sample."], ["More seeds."]))

    def test_significance_evidence_is_text_and_not_linked(self) -> None:
        _put_discussion(self.ws, "FullModel", _discussion("full"))
        d = self.products()["FullModel"]["discussion"]
        self.assertEqual(d["status"], "complete")
        evidence = {e["ref"]: e["path"] for e in d["hypotheses"][0]["evidence"]}
        self.assertIsNone(evidence["significance:hybrid vs linear"])
        self.assertEqual(evidence["Results/figures/cm.pdf"], "implementations/repo/FullModel/Results/figures/cm.pdf")

    def test_a_draft_and_an_invalid_discussion_keep_their_status(self) -> None:
        draft = _discussion()
        draft["hypotheses"][0].update(verdict="pending", evidence=[])
        _put_discussion(self.ws, "PocModel", draft)
        _put_discussion(self.ws, "FullModel", _discussion("full", summary=""))
        products = self.products()
        self.assertEqual(products["PocModel"]["discussion"]["status"], "draft")
        invalid = products["FullModel"]["discussion"]
        self.assertEqual(invalid["status"], "invalid")
        self.assertTrue(any("summary" in e for e in invalid["errors"]))

    def test_a_malformed_discussion_is_invalid_and_never_raises(self) -> None:
        _write(self.ws.root / "implementations" / "repo" / "PocModel" / "Results" / "discussion.json", "{nope")
        d = self.products()["PocModel"]["discussion"]
        self.assertEqual(d["status"], "invalid")
        self.assertTrue(d["errors"])
        self.assertEqual(d["hypotheses"], [])

    def test_evidence_escaping_the_product_is_text_and_not_linked(self) -> None:
        # A sibling product's file is inside the workspace but outside this product.
        data = _discussion()
        data["hypotheses"][0]["evidence"] = [
            "../FullModel/Results/figures/cm.pdf", "Results/figures/fig.png", "/etc/passwd"]
        _put_discussion(self.ws, "PocModel", data)
        d = self.products()["PocModel"]["discussion"]
        self.assertEqual(d["status"], "invalid")
        links = {e["ref"]: e["path"] for e in d["hypotheses"][0]["evidence"]}
        self.assertIsNone(links["../FullModel/Results/figures/cm.pdf"])
        self.assertIsNone(links["/etc/passwd"])
        self.assertEqual(links["Results/figures/fig.png"], "implementations/repo/PocModel/Results/figures/fig.png")

    def test_a_symlink_leaving_the_product_is_not_linked(self) -> None:
        poc = self.ws.root / "implementations" / "repo" / "PocModel"
        os.symlink(self.ws.outside / "leak.png", poc / "Results" / "figures" / "leak.png")
        data = _discussion()
        data["qualitative"] = [{"title": "Leak", "kind": "qualitative", "method": "m",
                                "figure": "Results/figures/leak.png", "reading": "r"}]
        _put_discussion(self.ws, "PocModel", data)
        d = self.products()["PocModel"]["discussion"]
        self.assertIsNone(d["qualitative"][0]["figure"])
        self.assertEqual(d["qualitative"][0]["figure_ref"], "Results/figures/leak.png")

    def test_a_discussion_symlinked_outside_the_workspace_is_not_read(self) -> None:
        secret = _write(self.ws.outside / "discussion.json", json.dumps(_discussion(summary="SECRET")))
        os.symlink(secret, self.ws.root / "implementations" / "repo" / "PocModel" / "Results" / "discussion.json")
        d = self.products()["PocModel"]["discussion"]
        self.assertEqual(d["status"], "invalid")
        self.assertNotIn("SECRET", json.dumps(d))

    def test_lists_and_text_are_bounded(self) -> None:
        data = _discussion(limitations=["L" * 2000] * 100, hypotheses=[
            {"id": f"H{i}", "statement": "x" * 2000, "verdict": "pending"} for i in range(250)])
        _put_discussion(self.ws, "PocModel", data)
        d = self.products()["PocModel"]["discussion"]
        self.assertLessEqual(len(d["hypotheses"]), 200)
        self.assertLessEqual(len(d["limitations"]), 50)
        self.assertLessEqual(len(d["hypotheses"][0]["statement"]), experiments_view.TEXT_MAX)
        self.assertLessEqual(len(d["limitations"][0]), experiments_view.TEXT_MAX)
        self.assertLessEqual(len(d["errors"]), 100)

    def test_qualitative_figures_have_their_own_kind_and_list(self) -> None:
        poc = self.ws.root / "implementations" / "repo" / "PocModel" / "Results"
        _write(poc / "qualitative" / "saliency.png", "png")
        _write(poc / "E1" / "qualitative" / "cam.svg", "<svg/>")
        _write(poc / "qualitative" / "notes.md", "# not a figure")
        product = self.products()["PocModel"]
        base = "implementations/repo/PocModel/Results/"
        self.assertEqual(product["qualitative_figures"], [base + "E1/qualitative/cam.svg",
                                                          base + "qualitative/saliency.png"])
        self.assertNotIn(base + "qualitative/saliency.png", product["figures"])
        self.assertNotIn(base + "E1/qualitative/cam.svg", product["figures"])
        self.assertEqual(sorted(p.rsplit("/", 1)[-1] for p in product["figures"]), ["curve.svg", "fig.png"])
        results = poc
        self.assertEqual(experiments_view._result_kind(results, results / "qualitative" / "x.png"), "qualitative")
        self.assertEqual(experiments_view._result_kind(results, results / "figures" / "x.png"), "figure")

    def test_qualitative_figures_are_bounded(self) -> None:
        poc = self.ws.root / "implementations" / "repo" / "PocModel" / "Results" / "qualitative"
        for i in range(experiments_view.MAX_FIGURES + 10):
            _write(poc / f"q{i:03d}.png", "png")
        product = self.products()["PocModel"]
        self.assertEqual(len(product["qualitative_figures"]), experiments_view.MAX_FIGURES)

    def test_significance_rows_carry_hypothesis_and_experiment(self) -> None:
        full = self.ws.root / "implementations" / "repo" / "FullModel" / "Results"
        _write(full / "significance.json", json.dumps([
            {"comparison": "hybrid vs linear", "test": "wilcoxon", "p_value": 0.03, "hypothesis": "H1",
             "experiment": "E" + "1" * 900},
            {"comparison": "other", "test": "t", "p_value": 0.2}]))
        rows = self.products()["FullModel"]["significance"]
        self.assertEqual(rows[0]["hypothesis"], "H1")
        self.assertLessEqual(len(rows[0]["experiment"]), 200)
        self.assertIsNone(rows[1]["hypothesis"])
        self.assertIsNone(rows[1]["experiment"])

    def test_the_stage_comparison_joins_the_verdicts_by_hypothesis_id(self) -> None:
        poc = _discussion()
        poc["hypotheses"].append({"id": "H2", "statement": "Only at PoC.", "verdict": "pending"})
        full = _discussion("full")
        full["hypotheses"][0]["verdict"] = "partially_supported"
        full["hypotheses"].append({"id": "H3", "statement": "Only at full.", "verdict": "inconclusive"})
        _put_discussion(self.ws, "PocModel", poc)
        _put_discussion(self.ws, "FullModel", full)
        rows = experiments_view.get_experiments_view(self.ws.root)["stage_comparison"]
        by_id = {r["id"]: r for r in rows}
        self.assertEqual([r["id"] for r in rows], ["H1", "H2", "H3"])
        self.assertEqual(by_id["H1"]["statement"], "Hybrid beats linear.")
        self.assertEqual(by_id["H1"]["poc"], {"product": "PocModel", "verdict": "supported"})
        self.assertEqual(by_id["H1"]["full"], {"product": "FullModel", "verdict": "partially_supported"})
        self.assertIsNone(by_id["H2"]["full"])
        self.assertEqual(by_id["H2"]["poc"]["verdict"], "pending")
        self.assertIsNone(by_id["H3"]["poc"])
        self.assertEqual(by_id["H3"]["full"]["verdict"], "inconclusive")

    def test_with_several_products_of_a_kind_the_first_by_listing_wins(self) -> None:
        second = self.ws.root / "implementations" / "repo" / "AaaPoc"
        _write(second / "AGREED.md", "agreed\n")
        _write(second / "Results" / "figures" / "fig.png", "png")
        other = _discussion(summary="Other.")
        other["hypotheses"][0]["verdict"] = "not_supported"
        _write(second / "Results" / "discussion.json", json.dumps(other))
        _put_discussion(self.ws, "PocModel", _discussion())
        rows = experiments_view.get_experiments_view(self.ws.root)["stage_comparison"]
        self.assertEqual(rows[0]["poc"], {"product": "AaaPoc", "verdict": "not_supported"})

    def test_no_comparison_row_without_a_discussion_at_either_stage(self) -> None:
        _put_discussion(self.ws, "PocModel", _discussion())
        rows = experiments_view.get_experiments_view(self.ws.root)["stage_comparison"]
        self.assertEqual(rows[0]["poc"]["verdict"], "supported")
        self.assertIsNone(rows[0]["full"])


if __name__ == "__main__":
    unittest.main()
