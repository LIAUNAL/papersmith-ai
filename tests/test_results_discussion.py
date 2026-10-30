"""The results-discussion contract: ``skills/_core/results/discussion.py`` and its CLI.

Both files are loaded by file path (the folder has no package ``__init__``),
the way the dashboard and the gating will import them. The CLI runs as a
subprocess so exit codes, stdout shape and "nothing written on refusal" are
observed exactly as an agent sees them.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RESULTS_DIR = Path(__file__).resolve().parents[1] / "skills" / "_core" / "results"
CLI = RESULTS_DIR / "discussion_cli.py"


def _load(filename: str, name: str):
    spec = importlib.util.spec_from_file_location(name, RESULTS_DIR / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


discussion = _load("discussion.py", "results_discussion_under_test")

PROTOCOL = """<!-- proposal-workspace:artifact:v1 -->
# A Title

**Validation scheme:** Stratified 5-fold CV

## Experiment [exp:E1] — Hybrid Classification

- **Hypothesis:** The hybrid model beats the baseline, with `p < 0.05`.
- **Success criterion:** Balanced accuracy at least 0.85.
- **Priority:** core

### Expected Report: Experiment E1

- **Hypothesis:** must be ignored inside an expected report

| Model | F1 |
| :--- | :--- |
| Hybrid | |

## Experiment [exp:E2] — Ablation

- **Hypothesis:** Entanglement helps.
- **Priority:** ablation

## Notes

- **Hypothesis:** outside any experiment, ignored
"""


def _write(path: Path, text: str = "x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def good(stage: str = "poc") -> dict:
    """A complete, valid discussion for the ``Product`` fixture."""
    return {
        "schema": 1,
        "stage": stage,
        "protocol": "experiments/experiments-demo-v01.md",
        "generated_at": "2026-10-30T00:00:00Z",
        "summary": "The hybrid model beats the linear baseline on balanced accuracy.",
        "discussion_type": ["comparative"],
        "metrics": [{"name": "balanced_accuracy", "role": "primary",
                     "why": "Classes are imbalanced.", "source": "Results/tables/main.csv"}],
        "hypotheses": [{
            "id": "H1", "experiment": "E1", "statement": "The hybrid model beats the baseline.",
            "metric": "balanced_accuracy", "test": "Wilcoxon signed-rank",
            "criterion": "Balanced accuracy at least 0.85.", "observed": "0.87 vs 0.80",
            "evidence": ["significance:hybrid vs linear", "Results/figures/acc.png"],
            "verdict": "supported", "rationale": "The criterion is met and the test rejects the null.",
        }],
        "novelty": {"claim": "Hybrid encoding is new here.", "verdict": "justified",
                    "evidence": ["significance:hybrid vs linear"], "rationale": "Beats the baseline."},
        "qualitative": [{"title": "Saliency", "kind": "interpretability", "method": "Grad-CAM",
                         "figure": "Results/qualitative/saliency.png", "reading": "Focus on the alpha band."}],
        "limitations": ["Small sample."],
        "next_steps": ["Run the full experiment."],
    }


class Product:
    """A temporary workspace holding one approved product with some results."""

    def __init__(self, test: unittest.TestCase, holder: str = "AGREED.md") -> None:
        tmp = tempfile.TemporaryDirectory()
        test.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.folder = self.root / "implementations" / "repo" / "Demo"
        self.folder.mkdir(parents=True)
        if holder:
            _write(self.folder / holder, "approved")
        _write(self.folder / "Results" / "figures" / "acc.png")
        _write(self.folder / "Results" / "qualitative" / "saliency.png")
        _write(self.folder / "Results" / "tables" / "main.csv", "model,f1\nhybrid,0.9\n")
        _write(self.folder / "Results" / "significance.json",
               json.dumps([{"comparison": "hybrid vs linear", "p_value": 0.01}]))

    def write_discussion(self, data) -> Path:
        return _write(self.folder / "Results" / "discussion.json", json.dumps(data))

    def snapshot(self) -> dict:
        out = {}
        for path in sorted(self.root.rglob("*")):
            out[path.relative_to(self.root).as_posix()] = (
                path.read_bytes() if path.is_file() and not path.is_symlink() else None)
        return out


class CheckCase(unittest.TestCase):
    def setUp(self) -> None:
        self.product = Product(self)

    def check(self, data, product: Product | None = None) -> dict:
        return discussion.check_discussion((product or self.product).folder, data)

    def mutated(self, mutate, stage: str = "poc") -> dict:
        data = good(stage)
        mutate(data)
        return data

    def assertInvalid(self, data, *fragments: str, product: Product | None = None) -> dict:
        result = self.check(data, product)
        self.assertEqual(result["status"], "invalid", result)
        for fragment in fragments:
            self.assertTrue(any(fragment in e for e in result["errors"]), (fragment, result["errors"]))
        return result


class ConstantsTest(unittest.TestCase):
    def test_enums(self) -> None:
        self.assertEqual(tuple(discussion.STAGES), ("poc", "full"))
        self.assertEqual(set(discussion.VERDICTS),
                         {"supported", "partially_supported", "not_supported", "inconclusive", "pending"})
        self.assertEqual(set(discussion.NOVELTY_VERDICTS),
                         {"justified", "partially_justified", "not_justified", "pending"})
        self.assertEqual(set(discussion.QUALITATIVE_KINDS), {"qualitative", "interpretability", "explainability"})
        self.assertEqual(set(discussion.DISCUSSION_TYPES),
                         {"comparative", "ablation", "failure-analysis", "sensitivity",
                          "interpretability", "cost", "generalization"})


class ProductStageTest(unittest.TestCase):
    def test_holders(self) -> None:
        self.assertEqual(discussion.product_stage(Product(self).folder), "poc")
        self.assertEqual(discussion.product_stage(Product(self, "Experimental_AGREED.md").folder), "full")
        self.assertIsNone(discussion.product_stage(Product(self, "").folder))

    def test_full_wins_when_both_exist(self) -> None:
        product = Product(self, "Experimental_AGREED.md")
        _write(product.folder / "AGREED.md")
        self.assertEqual(discussion.product_stage(product.folder), "full")

    def test_missing_folder(self) -> None:
        self.assertIsNone(discussion.product_stage(Path("/nonexistent/papersmith/product")))


class ValidDiscussionTest(CheckCase):
    def test_complete(self) -> None:
        self.assertEqual(self.check(good()),
                         {"status": "complete", "errors": [], "warnings": [], "stage": "poc"})

    def test_draft_when_a_hypothesis_is_pending(self) -> None:
        def mutate(d):
            d["hypotheses"].append({"id": "H2", "statement": "Entanglement helps.", "verdict": "pending"})
        result = self.check(self.mutated(mutate))
        self.assertEqual((result["status"], result["errors"]), ("draft", []))

    def test_draft_when_novelty_is_pending(self) -> None:
        def mutate(d):
            d["novelty"] = {"claim": "x", "verdict": "pending"}
        result = self.check(self.mutated(mutate))
        self.assertEqual((result["status"], result["errors"]), ("draft", []))

    def test_inconclusive_needs_no_evidence_and_is_not_pending(self) -> None:
        def mutate(d):
            d["hypotheses"][0].update(verdict="inconclusive", evidence=[])
        result = self.check(self.mutated(mutate))
        self.assertEqual((result["status"], result["errors"]), ("complete", []))

    def test_unknown_keys_are_warnings_only(self) -> None:
        def mutate(d):
            d["extra"] = 1
            d["hypotheses"][0]["mood"] = "high"
            d["available_evidence"] = {"figures": []}
        result = self.check(self.mutated(mutate))
        self.assertEqual(result["status"], "complete")
        self.assertEqual(len(result["warnings"]), 2, result["warnings"])
        self.assertTrue(any("extra" in w for w in result["warnings"]))
        self.assertTrue(any("mood" in w for w in result["warnings"]))

    def test_qualitative_not_applicable_instead_of_entries(self) -> None:
        def mutate(d):
            del d["qualitative"]
            d["qualitative_not_applicable"] = "Tabular features, nothing to visualise."
        self.assertEqual(self.check(self.mutated(mutate))["status"], "complete")


class RuleTest(CheckCase):
    def test_schema(self) -> None:
        for bad in (2, "1", None, True):
            self.assertInvalid(self.mutated(lambda d, b=bad: d.update(schema=b)), "schema")
        self.assertInvalid(self.mutated(lambda d: d.pop("schema")), "schema")

    def test_stage_must_match_the_holder(self) -> None:
        result = self.assertInvalid(good("full"), "stage")
        self.assertEqual(result["stage"], "poc")
        self.assertInvalid(self.mutated(lambda d: d.update(stage="bogus")), "stage")
        self.assertInvalid(self.mutated(lambda d: d.pop("stage")), "stage")

    def test_product_without_holder(self) -> None:
        bare = Product(self, "")
        result = self.assertInvalid(good(), "AGREED.md", product=bare)
        self.assertIsNone(result["stage"])

    def test_summary(self) -> None:
        for bad in ("", "   ", None, 5):
            self.assertInvalid(self.mutated(lambda d, b=bad: d.update(summary=b)), "summary")
        self.assertInvalid(self.mutated(lambda d: d.pop("summary")), "summary")
        self.assertInvalid(self.mutated(lambda d: d.update(summary="x" * 2001)), "summary")
        self.assertEqual(self.check(self.mutated(lambda d: d.update(summary="x" * 2000)))["status"], "complete")

    def test_metrics(self) -> None:
        result = self.assertInvalid(self.mutated(lambda d: d.update(metrics=[])), "metrics")
        self.assertEqual(len(result["errors"]), 1)
        self.assertInvalid(self.mutated(lambda d: d.pop("metrics")), "metrics")
        self.assertInvalid(self.mutated(lambda d: d["metrics"][0].pop("name")), "metrics[0].name")
        self.assertInvalid(self.mutated(lambda d: d["metrics"][0].update(why=" ")), "metrics[0].why")
        self.assertInvalid(self.mutated(lambda d: d["metrics"].append("oops")), "metrics[1]")

    def test_metric_role_outside_the_enum_is_only_a_warning(self) -> None:
        result = self.check(self.mutated(lambda d: d["metrics"][0].update(role="tertiary")))
        self.assertEqual((result["status"], len(result["warnings"])), ("complete", 1))

    def test_hypotheses_required(self) -> None:
        self.assertInvalid(self.mutated(lambda d: d.update(hypotheses=[])), "hypotheses")
        self.assertInvalid(self.mutated(lambda d: d.pop("hypotheses")), "hypotheses")

    def test_hypothesis_id_and_statement(self) -> None:
        self.assertInvalid(self.mutated(lambda d: d["hypotheses"][0].pop("id")), "hypotheses[0].id")
        self.assertInvalid(self.mutated(lambda d: d["hypotheses"][0].update(statement="")),
                           "hypotheses[0].statement")

    def test_verdict_outside_the_enum(self) -> None:
        self.assertInvalid(self.mutated(lambda d: d["hypotheses"][0].update(verdict="maybe")),
                           "hypotheses[0].verdict")
        self.assertInvalid(self.mutated(lambda d: d["hypotheses"][0].pop("verdict")),
                           "hypotheses[0].verdict")

    def test_duplicate_ids_warn(self) -> None:
        def mutate(d):
            d["hypotheses"].append(copy.deepcopy(d["hypotheses"][0]))
        result = self.check(self.mutated(mutate))
        self.assertEqual((result["status"], len(result["warnings"])), ("complete", 1))

    def test_decided_verdicts_need_evidence(self) -> None:
        for verdict in ("supported", "partially_supported", "not_supported"):
            result = self.assertInvalid(
                self.mutated(lambda d, v=verdict: d["hypotheses"][0].update(verdict=v, evidence=[])),
                "hypotheses[0].evidence")
            self.assertEqual(len(result["errors"]), 1, result)
        self.assertInvalid(self.mutated(lambda d: d["hypotheses"][0].pop("evidence")), "hypotheses[0].evidence")

    def test_pending_needs_no_evidence(self) -> None:
        def mutate(d):
            d["hypotheses"][0].update(verdict="pending", evidence=[])
        self.assertEqual(self.check(self.mutated(mutate))["status"], "draft")

    def test_evidence_path_must_exist(self) -> None:
        self.assertInvalid(self.mutated(lambda d: d["hypotheses"][0]["evidence"].append("Results/figures/nope.png")),
                           "Results/figures/nope.png")

    def test_evidence_even_on_pending_is_validated(self) -> None:
        def mutate(d):
            d["hypotheses"][0].update(verdict="pending", evidence=["Results/nope.png"])
        self.assertInvalid(self.mutated(mutate), "Results/nope.png")

    def test_evidence_entries_must_be_strings(self) -> None:
        self.assertInvalid(self.mutated(lambda d: d["hypotheses"][0]["evidence"].append(7)),
                           "hypotheses[0].evidence[2]")
        self.assertInvalid(self.mutated(lambda d: d["hypotheses"][0].update(evidence="Results/figures/acc.png")),
                           "hypotheses[0].evidence")

    def test_evidence_absolute_path_rejected_even_if_it_exists(self) -> None:
        target = str(self.product.folder / "Results" / "figures" / "acc.png")
        self.assertInvalid(self.mutated(lambda d: d["hypotheses"][0]["evidence"].append(target)), "absolute")

    def test_evidence_dotdot_escape_rejected_even_if_it_exists(self) -> None:
        _write(self.product.root / "outside.txt")
        for escape in ("../../../outside.txt", "Results/../../../../outside.txt"):
            self.assertInvalid(self.mutated(lambda d, e=escape: d["hypotheses"][0]["evidence"].append(e)),
                               "outside the product")

    def test_dotdot_that_stays_inside_is_fine(self) -> None:
        def mutate(d):
            d["hypotheses"][0]["evidence"].append("Results/tables/../figures/acc.png")
        self.assertEqual(self.check(self.mutated(mutate))["status"], "complete")

    def test_symlink_escaping_the_product_rejected(self) -> None:
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        secret = _write(Path(outside.name) / "secret.png")
        try:
            os.symlink(secret, self.product.folder / "Results" / "figures" / "leak.png")
            os.symlink(outside.name, self.product.folder / "Results" / "linked")
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        for evidence in ("Results/figures/leak.png", "Results/linked/secret.png"):
            self.assertInvalid(self.mutated(lambda d, e=evidence: d["hypotheses"][0]["evidence"].append(e)),
                               "outside the product")
        def mutate(d):
            d["qualitative"][0]["figure"] = "Results/figures/leak.png"
        self.assertInvalid(self.mutated(mutate), "qualitative[0].figure")

    def test_symlink_staying_inside_the_product_is_fine(self) -> None:
        try:
            os.symlink(self.product.folder / "Results" / "figures" / "acc.png",
                       self.product.folder / "Results" / "figures" / "alias.png")
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        def mutate(d):
            d["hypotheses"][0]["evidence"].append("Results/figures/alias.png")
        self.assertEqual(self.check(self.mutated(mutate))["status"], "complete")

    def test_significance_must_match_a_comparison(self) -> None:
        def mutate(d):
            d["hypotheses"][0]["evidence"] = ["significance:hybrid vs ghost"]
        self.assertInvalid(self.mutated(mutate), "hybrid vs ghost")
        def empty(d):
            d["hypotheses"][0]["evidence"] = ["significance:"]
        self.assertInvalid(self.mutated(empty), "significance:")

    def test_significance_shapes_and_locations(self) -> None:
        results = self.product.folder / "Results"
        _write(results / "exp1" / "significance_extra.json",
               json.dumps({"tests": [{"comparison": "a vs b"}, "junk", 3]}))
        _write(results / "exp2" / "deep" / "significance-wrap.json",
               json.dumps({"comparisons": [{"comparison": "c vs d"}]}))
        _write(results / "significance_results.json", json.dumps({"results": [{"comparison": "e vs f"}]}))
        _write(results / "significance_single.json", json.dumps({"comparison": "g vs h"}))
        _write(results / "exp3" / "notes.json", json.dumps([{"comparison": "ignored"}]))
        _write(results / "significance_bad.json", "{not json")
        for name in ("a vs b", "c vs d", "e vs f", "g vs h"):
            def mutate(d, n=name):
                d["hypotheses"][0]["evidence"] = ["significance:" + n]
            self.assertEqual(self.check(self.mutated(mutate))["status"], "complete", name)
        def ignored(d):
            d["hypotheses"][0]["evidence"] = ["significance:ignored"]
        self.assertInvalid(self.mutated(ignored), "ignored")

    def test_significance_outside_results_or_oversized_is_ignored(self) -> None:
        _write(self.product.folder / "significance_top.json", json.dumps([{"comparison": "top level"}]))
        big = self.product.folder / "Results" / "significance_big.json"
        _write(big, json.dumps([{"comparison": "big one", "pad": "x" * (discussion.MAX_FILE_BYTES + 10)}]))
        for name in ("top level", "big one"):
            def mutate(d, n=name):
                d["hypotheses"][0]["evidence"] = ["significance:" + n]
            self.assertInvalid(self.mutated(mutate), name)

    def test_significance_file_symlinked_outside_is_ignored(self) -> None:
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        target = _write(Path(outside.name) / "s.json", json.dumps([{"comparison": "leaked"}]))
        try:
            os.symlink(target, self.product.folder / "Results" / "significance_leak.json")
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        def mutate(d):
            d["hypotheses"][0]["evidence"] = ["significance:leaked"]
        self.assertInvalid(self.mutated(mutate), "leaked")

    def test_full_stage_requires_significance_evidence_for_decided_verdicts(self) -> None:
        full = Product(self, "Experimental_AGREED.md")
        for verdict in ("supported", "partially_supported", "not_supported"):
            def mutate(d, v=verdict):
                d["hypotheses"][0].update(verdict=v, evidence=["Results/figures/acc.png"])
            result = self.assertInvalid(self.mutated(mutate, "full"), "hypotheses[0]", "significance", product=full)
            self.assertEqual((len(result["errors"]), result["stage"]), (1, "full"))

    def test_full_stage_with_significance_is_complete(self) -> None:
        full = Product(self, "Experimental_AGREED.md")
        self.assertEqual(self.check(good("full"), full),
                         {"status": "complete", "errors": [], "warnings": [], "stage": "full"})

    def test_full_stage_inconclusive_and_pending_exempt(self) -> None:
        full = Product(self, "Experimental_AGREED.md")
        def mutate(d):
            d["hypotheses"][0].update(verdict="inconclusive", evidence=[])
            d["hypotheses"].append({"id": "H2", "statement": "s", "verdict": "pending"})
        result = self.check(self.mutated(mutate, "full"), full)
        self.assertEqual((result["status"], result["errors"], result["warnings"]), ("draft", [], []))

    def test_poc_stage_without_significance_is_a_warning(self) -> None:
        def mutate(d):
            d["hypotheses"][0]["evidence"] = ["Results/figures/acc.png"]
        result = self.check(self.mutated(mutate, "poc"))
        self.assertEqual((result["status"], result["errors"]), ("complete", []))
        self.assertEqual(len(result["warnings"]), 1)
        self.assertIn("significance", result["warnings"][0])

    def test_novelty(self) -> None:
        self.assertInvalid(self.mutated(lambda d: d.pop("novelty")), "novelty")
        self.assertInvalid(self.mutated(lambda d: d.update(novelty="yes")), "novelty")
        self.assertInvalid(self.mutated(lambda d: d["novelty"].update(verdict="meh")), "novelty.verdict")
        self.assertInvalid(self.mutated(lambda d: d["novelty"].pop("verdict")), "novelty.verdict")

    def test_novelty_decided_needs_evidence(self) -> None:
        for verdict in ("justified", "partially_justified", "not_justified"):
            self.assertInvalid(self.mutated(lambda d, v=verdict: d["novelty"].update(verdict=v, evidence=[])),
                               "novelty.evidence")

    def test_novelty_evidence_is_resolved_like_hypothesis_evidence(self) -> None:
        self.assertInvalid(self.mutated(lambda d: d["novelty"].update(evidence=["significance:ghost"])), "ghost")
        self.assertInvalid(self.mutated(lambda d: d["novelty"].update(evidence=["Results/ghost.png"])),
                           "Results/ghost.png")
        self.assertInvalid(self.mutated(lambda d: d["novelty"].update(evidence=["../x"])), "novelty.evidence")

    def test_novelty_pending_needs_no_evidence(self) -> None:
        def mutate(d):
            d["novelty"] = {"claim": "c", "verdict": "pending", "evidence": []}
        self.assertEqual(self.check(self.mutated(mutate))["status"], "draft")

    def test_qualitative_or_reason_required(self) -> None:
        for patch in ({"qualitative": []}, {"qualitative": [], "qualitative_not_applicable": "  "},
                      {"qualitative": None, "qualitative_not_applicable": ""}):
            def mutate(d, p=patch):
                d.update(p)
            result = self.assertInvalid(self.mutated(mutate), "qualitative")
            self.assertEqual(len(result["errors"]), 1, result)
        self.assertInvalid(self.mutated(lambda d: d.pop("qualitative")), "qualitative")

    def test_qualitative_entry_kind_and_figure(self) -> None:
        self.assertInvalid(self.mutated(lambda d: d["qualitative"][0].update(kind="vibes")), "qualitative[0].kind")
        self.assertInvalid(self.mutated(lambda d: d["qualitative"][0].pop("kind")), "qualitative[0].kind")
        self.assertInvalid(self.mutated(lambda d: d["qualitative"][0].update(figure="Results/qualitative/no.png")),
                           "qualitative[0].figure")
        self.assertInvalid(self.mutated(lambda d: d["qualitative"][0].update(figure="")), "qualitative[0].figure")
        self.assertInvalid(self.mutated(lambda d: d["qualitative"][0].update(figure="/etc/hosts")),
                           "qualitative[0].figure")
        self.assertInvalid(self.mutated(lambda d: d["qualitative"][0].update(figure="../../../../x.png")),
                           "qualitative[0].figure")

    def test_every_error_is_reported_together(self) -> None:
        result = self.check({"schema": 9})
        self.assertEqual(result["status"], "invalid")
        for fragment in ("schema", "stage", "summary", "metrics", "hypotheses", "novelty", "qualitative"):
            self.assertTrue(any(fragment in e for e in result["errors"]), (fragment, result["errors"]))

    def test_discussion_type_outside_the_enum_is_a_warning(self) -> None:
        result = self.check(self.mutated(lambda d: d.update(discussion_type=["comparative", "gossip"])))
        self.assertEqual((result["status"], len(result["warnings"])), ("complete", 1))
        result = self.check(self.mutated(lambda d: d.update(discussion_type="comparative")))
        self.assertEqual((result["status"], len(result["warnings"])), ("complete", 1))

    def test_oversized_collections_are_an_error_not_a_crash(self) -> None:
        def mutate(d):
            d["hypotheses"] = [{"id": f"H{i}", "statement": "s", "verdict": "pending"} for i in range(5000)]
        self.assertInvalid(self.mutated(mutate), "hypotheses")


class NeverRaisesTest(CheckCase):
    def test_garbage_inputs(self) -> None:
        garbage = [None, [], "text", 3, 1.5, True, {}, [1, 2], {"schema": []}, {"hypotheses": "x"},
                   {"hypotheses": [None, 1, [], "x"], "metrics": [None], "novelty": [], "qualitative": "q"},
                   {"hypotheses": [{"id": [], "statement": {}, "verdict": [], "evidence": [[]]}]},
                   {"novelty": {"verdict": {}, "evidence": {}}, "qualitative": [None, 3]},
                   {"summary": ["a"], "metrics": {"name": "x"}}]
        for item in garbage:
            result = self.check(item)
            self.assertEqual(result["status"], "invalid", item)
            self.assertIsInstance(result["errors"], list)
            self.assertTrue(result["errors"], item)

    def test_non_json_values_and_missing_product(self) -> None:
        result = self.check({"summary": object(), "schema": 1})
        self.assertEqual(result["status"], "invalid")
        result = discussion.check_discussion(Path("/nonexistent/papersmith/product"), good())
        self.assertEqual(result["status"], "invalid")
        self.assertIsNone(result["stage"])

    def test_evidence_with_nul_bytes_and_long_paths(self) -> None:
        for evidence in ("a\x00b", "Results/" + "x" * 5000):
            result = self.check(self.mutated(lambda d, e=evidence: d["hypotheses"][0]["evidence"].append(e)))
            self.assertEqual(result["status"], "invalid")


class LoadAndCheckTest(CheckCase):
    def test_absent(self) -> None:
        result = discussion.load_and_check(self.product.folder)
        self.assertEqual(result, {"present": False, "file": "Results/discussion.json", "data": None,
                                  "status": "absent", "errors": [], "warnings": [], "stage": "poc"})

    def test_complete(self) -> None:
        self.product.write_discussion(good())
        result = discussion.load_and_check(self.product.folder)
        self.assertTrue(result["present"])
        self.assertEqual(result["file"], "Results/discussion.json")
        self.assertEqual(result["data"], good())
        self.assertEqual((result["status"], result["errors"], result["stage"]), ("complete", [], "poc"))

    def test_malformed_json(self) -> None:
        _write(self.product.folder / "Results" / "discussion.json", "{not json")
        result = discussion.load_and_check(self.product.folder)
        self.assertEqual((result["present"], result["data"], result["status"]), (True, None, "invalid"))
        self.assertEqual(len(result["errors"]), 1)
        self.assertIn("JSON", result["errors"][0])

    def test_non_object_json_and_binary(self) -> None:
        for text in ("[1, 2]", "null", '"s"'):
            _write(self.product.folder / "Results" / "discussion.json", text)
            self.assertEqual(discussion.load_and_check(self.product.folder)["status"], "invalid")
        (self.product.folder / "Results" / "discussion.json").write_bytes(b"\xff\xfe\x00bad")
        self.assertEqual(discussion.load_and_check(self.product.folder)["status"], "invalid")

    def test_oversized_file_is_not_read(self) -> None:
        _write(self.product.folder / "Results" / "discussion.json", " " * (discussion.MAX_FILE_BYTES + 1))
        result = discussion.load_and_check(self.product.folder)
        self.assertEqual((result["present"], result["data"], result["status"]), (True, None, "invalid"))
        self.assertIn("larger", result["errors"][0])

    def test_symlink_leaving_the_product_is_not_read(self) -> None:
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        target = _write(Path(outside.name) / "d.json", json.dumps(good()))
        try:
            os.symlink(target, self.product.folder / "Results" / "discussion.json")
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        result = discussion.load_and_check(self.product.folder)
        self.assertEqual((result["present"], result["data"], result["status"]), (True, None, "invalid"))


class ScaffoldTest(unittest.TestCase):
    def make(self, holder: str = "AGREED.md") -> Product:
        product = Product(self, holder)
        _write(product.root / "experiments" / "experiments-demo-v02.md", PROTOCOL)
        return product

    def test_skeleton_from_the_protocol_verbatim(self) -> None:
        product = self.make()
        data = discussion.scaffold(product.folder)
        self.assertEqual(data["schema"], 1)
        self.assertEqual(data["stage"], "poc")
        self.assertEqual(data["protocol"], "experiments/experiments-demo-v02.md")
        self.assertRegex(data["generated_at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d")
        self.assertEqual(data["summary"], "")
        self.assertEqual(data["metrics"], [])
        self.assertEqual(data["discussion_type"], [])
        self.assertEqual(data["qualitative"], [])
        self.assertEqual(data["qualitative_not_applicable"], "")
        self.assertEqual(data["limitations"], [])
        self.assertEqual(data["next_steps"], [])
        self.assertEqual(data["novelty"], {"claim": "", "verdict": "pending", "evidence": [], "rationale": ""})
        self.assertEqual(data["hypotheses"], [
            {"id": "H1", "experiment": "E1", "statement": "The hybrid model beats the baseline, with `p < 0.05`.",
             "metric": "", "test": "", "criterion": "Balanced accuracy at least 0.85.", "observed": "",
             "evidence": [], "verdict": "pending", "rationale": ""},
            {"id": "H2", "experiment": "E2", "statement": "Entanglement helps.",
             "metric": "", "test": "", "criterion": "", "observed": "",
             "evidence": [], "verdict": "pending", "rationale": ""},
        ])

    def test_full_stage(self) -> None:
        self.assertEqual(discussion.scaffold(self.make("Experimental_AGREED.md").folder)["stage"], "full")

    def test_latest_protocol_revision_is_numeric(self) -> None:
        product = self.make()
        _write(product.root / "experiments" / "experiments-demo-v10.md",
               "## Experiment [exp:Z9] — Newer\n\n- **Hypothesis:** newest\n")
        _write(product.root / "experiments" / "experiments-demo-v9.md", "## Experiment [exp:Y1] — Older\n")
        _write(product.root / "experiments" / "notes-v99.md", "## Experiment [exp:N1] — not a protocol\n")
        data = discussion.scaffold(product.folder)
        self.assertEqual(data["protocol"], "experiments/experiments-demo-v10.md")
        self.assertEqual([(h["id"], h["experiment"], h["statement"]) for h in data["hypotheses"]],
                         [("H1", "Z9", "newest")])

    def test_explicit_root(self) -> None:
        product = self.make()
        other = Product(self)
        _write(other.root / "experiments" / "experiments-o-v01.md", "## Experiment [exp:Q1] — Q\n- **Hypothesis:** h\n")
        data = discussion.scaffold(product.folder, other.root)
        self.assertEqual(data["protocol"], "experiments/experiments-o-v01.md")

    def test_without_a_protocol(self) -> None:
        product = Product(self)
        data = discussion.scaffold(product.folder)
        self.assertEqual((data["protocol"], data["hypotheses"]), ("", []))

    def test_available_evidence(self) -> None:
        product = self.make()
        results = product.folder / "Results"
        _write(results / "exp1" / "figures" / "curve.svg")
        _write(results / "exp1" / "figures" / "notes.txt")
        _write(results / "exp1" / "tables" / "t.json", "{}")
        _write(results / "summary.json", "{}")
        _write(results / "hpo" / "figures" / "skipped.png")
        _write(results / "qualitative" / "nested" / "cam.pdf")
        _write(results / "significance_a.json", json.dumps({"tests": [{"comparison": "x vs y"},
                                                                       {"comparison": "hybrid vs linear"}]}))
        evidence = discussion.scaffold(product.folder)["available_evidence"]
        self.assertEqual(evidence["figures"], ["Results/exp1/figures/curve.svg", "Results/figures/acc.png"])
        self.assertEqual(evidence["tables"],
                         ["Results/exp1/tables/t.json", "Results/summary.json", "Results/tables/main.csv"])
        self.assertEqual(evidence["qualitative"],
                         ["Results/qualitative/nested/cam.pdf", "Results/qualitative/saliency.png"])
        self.assertEqual(sorted(evidence["significance"]), ["hybrid vs linear", "x vs y"])

    def test_available_evidence_ignores_escaping_symlinks(self) -> None:
        product = self.make()
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        secret = _write(Path(outside.name) / "secret.png")
        try:
            os.symlink(secret, product.folder / "Results" / "figures" / "leak.png")
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        self.assertEqual(discussion.scaffold(product.folder)["available_evidence"]["figures"],
                         ["Results/figures/acc.png"])

    def test_scaffold_is_invalid_until_filled(self) -> None:
        product = self.make()
        product.write_discussion(discussion.scaffold(product.folder))
        result = discussion.load_and_check(product.folder)
        self.assertEqual(result["status"], "invalid")
        for fragment in ("summary", "metrics", "qualitative"):
            self.assertTrue(any(fragment in e for e in result["errors"]), (fragment, result["errors"]))
        self.assertFalse(any("schema" in e or "stage" in e for e in result["errors"]), result["errors"])
        self.assertFalse(any("available_evidence" in w for w in result["warnings"]))

    def test_scaffold_writes_nothing(self) -> None:
        product = self.make()
        before = product.snapshot()
        discussion.scaffold(product.folder)
        self.assertEqual(product.snapshot(), before)

    def test_refusals(self) -> None:
        with self.assertRaises(discussion.DiscussionRefusal) as caught:
            discussion.scaffold(Path("/nonexistent/papersmith/implementations/r/N"))
        self.assertEqual(caught.exception.code, "PRODUCT_ABSENT")
        with self.assertRaises(discussion.DiscussionRefusal) as caught:
            discussion.scaffold(Product(self, "").folder)
        self.assertEqual(caught.exception.code, "APPROVAL_ABSENT")


class CliCase(unittest.TestCase):
    def setUp(self) -> None:
        self.product = Product(self)
        _write(self.product.root / "experiments" / "experiments-demo-v01.md", PROTOCOL)

    def run_cli(self, *args: str) -> tuple[int, dict, str]:
        proc = subprocess.run([sys.executable, str(CLI), *args], capture_output=True, text=True, timeout=60)
        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1, (proc.stdout, proc.stderr))
        return proc.returncode, json.loads(lines[0]), proc.stderr

    def refusal(self, args: list[str], code: str, product: Product | None = None) -> dict:
        target = product or self.product
        before = target.snapshot()
        exit_code, out, _err = self.run_cli(*args)
        self.assertNotEqual(exit_code, 0)
        self.assertEqual(out["ok"], False)
        self.assertEqual(out["error"], code)
        self.assertIsInstance(out["message"], str)
        self.assertTrue(out["message"])
        self.assertEqual(target.snapshot(), before, "a refusal must write nothing")
        return out


class CliScaffoldTest(CliCase):
    def test_success_writes_only_the_discussion_file(self) -> None:
        shutil_results = self.product.folder / "Results"
        for path in sorted(shutil_results.rglob("*"), reverse=True):  # start without a Results/ at all
            path.unlink() if path.is_file() else path.rmdir()
        shutil_results.rmdir()
        before = self.product.snapshot()
        exit_code, out, _ = self.run_cli("scaffold", "--product", str(self.product.folder))
        self.assertEqual(exit_code, 0)
        self.assertEqual(out["ok"], True)
        self.assertEqual(out["file"], "Results/discussion.json")
        self.assertEqual(out["stage"], "poc")
        self.assertEqual(out["hypotheses"], 2)
        after = self.product.snapshot()
        added = sorted(set(after) - set(before))
        self.assertEqual(added, ["implementations/repo/Demo/Results",
                                 "implementations/repo/Demo/Results/discussion.json"])
        self.assertEqual({k: v for k, v in after.items() if k in before}, before)
        written = json.loads((self.product.folder / "Results" / "discussion.json").read_text(encoding="utf-8"))
        self.assertEqual(written["hypotheses"][0]["statement"], "The hybrid model beats the baseline, with `p < 0.05`.")
        self.assertEqual(written["hypotheses"][0]["criterion"], "Balanced accuracy at least 0.85.")
        self.assertEqual(written["protocol"], "experiments/experiments-demo-v01.md")

    def test_the_scaffold_is_reported_invalid(self) -> None:
        _exit, out, _ = self.run_cli("scaffold", "--product", str(self.product.folder))
        self.assertEqual(out["status"], "invalid")
        self.assertTrue(out["errors"])

    def test_product_absent(self) -> None:
        missing = self.product.root / "implementations" / "repo" / "Nope"
        self.refusal(["scaffold", "--product", str(missing)], "PRODUCT_ABSENT")
        self.assertFalse(missing.exists())
        file_path = self.product.folder / "AGREED.md"
        self.refusal(["scaffold", "--product", str(file_path)], "PRODUCT_ABSENT")

    def test_approval_absent(self) -> None:
        bare = Product(self, "")
        self.refusal(["scaffold", "--product", str(bare.folder)], "APPROVAL_ABSENT", bare)
        self.assertFalse((bare.folder / "Results" / "discussion.json").exists())

    def test_discussion_exists_is_never_overwritten(self) -> None:
        self.product.write_discussion(good())
        self.refusal(["scaffold", "--product", str(self.product.folder)], "DISCUSSION_EXISTS")
        self.assertEqual(json.loads((self.product.folder / "Results" / "discussion.json").read_text()), good())

    def test_dangling_symlink_counts_as_existing(self) -> None:
        try:
            os.symlink(self.product.root / "nowhere.json", self.product.folder / "Results" / "discussion.json")
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        self.refusal(["scaffold", "--product", str(self.product.folder)], "DISCUSSION_EXISTS")

    def test_results_symlink_leaving_the_product_is_refused(self) -> None:
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        bare = Product(self)
        for path in sorted((bare.folder / "Results").rglob("*"), reverse=True):
            path.unlink() if path.is_file() else path.rmdir()
        (bare.folder / "Results").rmdir()
        try:
            os.symlink(outside.name, bare.folder / "Results")
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        out = self.refusal(["scaffold", "--product", str(bare.folder)], "RESULTS_UNSAFE", bare)
        self.assertEqual(os.listdir(outside.name), [])
        self.assertIn("RESULTS_UNSAFE", out["error"])

    def test_relative_product_path(self) -> None:
        proc = subprocess.run([sys.executable, str(CLI), "scaffold", "--product", "implementations/repo/Demo"],
                              cwd=self.product.root, capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["stage"], "poc")


class CliCheckTest(CliCase):
    def test_complete_exits_zero(self) -> None:
        self.product.write_discussion(good())
        exit_code, out, _ = self.run_cli("check", "--product", str(self.product.folder))
        self.assertEqual(exit_code, 0)
        self.assertEqual(out, {"ok": True, "status": "complete", "errors": [], "warnings": [], "stage": "poc"})

    def test_draft_exits_zero(self) -> None:
        data = good()
        data["novelty"] = {"claim": "c", "verdict": "pending"}
        self.product.write_discussion(data)
        exit_code, out, _ = self.run_cli("check", "--product", str(self.product.folder))
        self.assertEqual((exit_code, out["ok"], out["status"]), (0, True, "draft"))

    def test_invalid_exits_non_zero(self) -> None:
        data = good()
        data["summary"] = ""
        self.product.write_discussion(data)
        exit_code, out, _ = self.run_cli("check", "--product", str(self.product.folder))
        self.assertNotEqual(exit_code, 0)
        self.assertEqual((out["ok"], out["status"], out["stage"]), (False, "invalid", "poc"))
        self.assertEqual(len(out["errors"]), 1)
        self.assertIn("summary", out["errors"][0])

    def test_malformed_file_is_invalid(self) -> None:
        _write(self.product.folder / "Results" / "discussion.json", "{nope")
        exit_code, out, _ = self.run_cli("check", "--product", str(self.product.folder))
        self.assertNotEqual(exit_code, 0)
        self.assertEqual((out["ok"], out["status"]), (False, "invalid"))

    def test_discussion_absent(self) -> None:
        self.refusal(["check", "--product", str(self.product.folder)], "DISCUSSION_ABSENT")

    def test_product_absent(self) -> None:
        self.refusal(["check", "--product", str(self.product.root / "nope")], "PRODUCT_ABSENT")


class CliStatusTest(CliCase):
    def test_status_mirrors_check_but_exits_zero(self) -> None:
        data = good()
        data["summary"] = ""
        self.product.write_discussion(data)
        exit_code, out, _ = self.run_cli("status", "--product", str(self.product.folder))
        self.assertEqual(exit_code, 0)
        self.assertEqual((out["ok"], out["status"]), (False, "invalid"))
        self.assertEqual(sorted(out), ["errors", "ok", "stage", "status", "warnings"])

    def test_status_complete(self) -> None:
        self.product.write_discussion(good())
        exit_code, out, _ = self.run_cli("status", "--product", str(self.product.folder))
        self.assertEqual((exit_code, out["ok"], out["status"]), (0, True, "complete"))

    def test_status_absent_is_not_a_refusal(self) -> None:
        exit_code, out, _ = self.run_cli("status", "--product", str(self.product.folder))
        self.assertEqual(exit_code, 0)
        self.assertEqual(out, {"ok": False, "status": "absent", "errors": [], "warnings": [], "stage": "poc"})

    def test_status_product_absent_still_refuses(self) -> None:
        self.refusal(["status", "--product", str(self.product.root / "nope")], "PRODUCT_ABSENT")


class CliUsageTest(CliCase):
    def test_usage_errors_are_json_on_stdout(self) -> None:
        for args in ([], ["scaffold"], ["bogus", "--product", "x"], ["check", "--product"],
                     ["check", "--product", str(self.product.folder), "--force"]):
            exit_code, out, _ = self.run_cli(*args)
            self.assertEqual(exit_code, 2, args)
            self.assertEqual((out["ok"], out["error"]), (False, "USAGE"), args)
            self.assertTrue(out["message"], args)

    def test_usage_writes_nothing(self) -> None:
        before = self.product.snapshot()
        self.run_cli("scaffold")
        self.run_cli("scaffold", "--product", str(self.product.folder), "--overwrite")
        self.assertEqual(self.product.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
