"""The math panel's data: real LaTeX from the workspace, a novelty card, and a
proof that every equation the panel shows compiles with the vendored KaTeX."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from skills._core.command_center import math_view, server

STATIC = Path(server.__file__).resolve().parent / "static"
KATEX = STATIC / "vendor" / "katex" / "katex.min.js"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

PROPOSAL_R01 = """# Research concept r01

## 1. Problem

The old revision.

$$
x = 1 \\tag{1}
$$
"""

PROPOSAL_R02 = """# Research concept r02

## 2. Formulation

We encode each EEG epoch $x_t$ into a quantum state.

$$
\\lvert \\psi(x) \\rangle = U_{\\phi}(x) \\lvert 0 \\rangle^{\\otimes n} \\tag{1}
$$

The feature map embeds the signal in Hilbert space. It is then measured.

### 2.1 Kernel

$$
k(x, x') = \\lvert \\langle \\psi(x) \\mid \\psi(x') \\rangle \\rvert^{2} \\tag{2}
$$

The fidelity kernel compares two epochs (Ec. 1).
"""

SKY = {
    "system": {"id": "proposal", "title": "Quantum kernels for EEG", "planets": [
        {"id": "sun", "slot": "sun", "label": "Quantum kernels for EEG"},
        {"id": "nov", "slot": "novelty", "label": "Fidelity kernel on EEG epochs",
         "detail": "A quantum feature map separates epochs a classical kernel cannot."},
        {"id": "prob", "slot": "problem", "label": "Non-linear EEG separability",
         "detail": "Classical kernels saturate on short noisy epochs."},
        {"id": "c1", "slot": "contribution", "label": "Data re-uploading map"},
        {"id": "c2", "slot": "contribution", "label": "Shot-noise aware training"},
        {"id": "c3", "slot": "contribution", "label": "Benchmark on BCI-IV 2a"},
    ]},
    "links": [],
}


def compile_with_katex(latex: list[str]) -> list[str]:
    """Errors KaTeX raises for each string (strict, throwOnError)."""
    script = (
        "const vm=require('vm'),fs=require('fs');const c={};vm.createContext(c);"
        f"vm.runInContext(fs.readFileSync({json.dumps(str(KATEX))},'utf8'),c);"
        "const out=[];for(const t of JSON.parse(fs.readFileSync(0,'utf8'))){"
        "try{c.katex.renderToString(t,{displayMode:true,throwOnError:true,strict:'error'});}"
        "catch(e){out.push(t+' :: '+e.message);}}console.log(JSON.stringify(out));"
    )
    done = subprocess.run(["node", "-e", script], input=json.dumps(latex), capture_output=True,
                          text=True, cwd=tempfile.gettempdir(), check=True)
    return json.loads(done.stdout)


class _Workspace(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.root = Path(holder.name).resolve()
        (self.root / "papersmith.yaml").write_text("title: QMLEEG\ntopic: Quantum ML for EEG\n",
                                                   encoding="utf-8")


class ProposalTests(_Workspace):
    def write_proposals(self) -> None:
        proposals = self.root / "proposals"
        proposals.mkdir()
        (proposals / "research-concept-qml-r01.md").write_text(PROPOSAL_R01, encoding="utf-8")
        (proposals / "research-concept-qml-r02.md").write_text(PROPOSAL_R02, encoding="utf-8")
        (proposals / "research-concept-qml-r02.sky.json").write_text(json.dumps(SKY), encoding="utf-8")

    def test_the_latest_revision_supplies_tagged_equations_with_their_context(self) -> None:
        self.write_proposals()
        view = math_view.build(self.root)
        self.assertEqual(view["source"], "proposal:proposals/research-concept-qml-r02.md")
        self.assertEqual([e["tag"] for e in view["equations"]], ["1", "2"])
        first, second = view["equations"]
        self.assertEqual(first["heading"], "2. Formulation")
        self.assertEqual(first["latex"],
                         "\\lvert \\psi(x) \\rangle = U_{\\phi}(x) \\lvert 0 \\rangle^{\\otimes n}")
        self.assertEqual(first["connection"], "The feature map embeds the signal in Hilbert space.")
        self.assertEqual(second["heading"], "2.1 Kernel")
        self.assertEqual(second["connection"], "The fidelity kernel compares two epochs (Ec. 1).")
        self.assertEqual(compile_with_katex([e["latex"] for e in view["equations"]]), [])

    def test_the_sky_overlay_fills_the_novelty_card(self) -> None:
        self.write_proposals()
        card = math_view.build(self.root)["novelty"]
        self.assertEqual(card["central_idea"], "Quantum kernels for EEG")
        self.assertEqual(card["novelty"], "Fidelity kernel on EEG epochs")
        self.assertEqual(card["novelty_detail"],
                         "A quantum feature map separates epochs a classical kernel cannot.")
        self.assertEqual(card["problem"], "Non-linear EEG separability")
        self.assertEqual(card["contributions"], ["Data re-uploading map", "Shot-noise aware training",
                                                 "Benchmark on BCI-IV 2a"])
        self.assertEqual(card["key_equation"]["tag"], "1")

    def test_a_revision_without_an_overlay_takes_its_novelty_from_the_concept_map(self) -> None:
        self.write_proposals()
        (self.root / "proposals" / "research-concept-qml-r02.sky.json").unlink()
        (self.root / ".papersmith").mkdir()
        (self.root / ".papersmith" / "model_spec.json").write_text(json.dumps({
            "title": "Spec title",
            "novelty": {"problem_tree": {"central": {"text": "Degraded accuracy on short epochs"}},
                        "pillars": [{"name": "Fidelity kernel", "summary": "Detail one."},
                                    {"name": "Re-uploading map"}, {"name": "Shot-noise training"}]},
        }), encoding="utf-8")
        card = math_view.build(self.root)["novelty"]
        self.assertEqual(card["central_idea"], "QMLEEG")
        self.assertEqual((card["novelty"], card["novelty_detail"]), ("Fidelity kernel", "Detail one."))
        self.assertEqual(card["problem"], "Degraded accuracy on short epochs")
        self.assertEqual(card["contributions"], ["Re-uploading map", "Shot-noise training"])

    def test_the_overlay_wins_over_the_concept_map(self) -> None:
        self.write_proposals()
        (self.root / ".papersmith").mkdir()
        (self.root / ".papersmith" / "model_spec.json").write_text(json.dumps({
            "novelty": {"pillars": [{"name": "Other"}, {"name": "Another"}]}}), encoding="utf-8")
        card = math_view.build(self.root)["novelty"]
        self.assertEqual(card["novelty"], "Fidelity kernel on EEG epochs")
        self.assertEqual(card["contributions"][0], "Data re-uploading map")

    def test_maths_inside_a_code_block_is_not_an_equation(self) -> None:
        text = "## A\n\n```latex\n$$\n\\begin{bad\n$$\n```\n\n$$\ny = 2 \\tag{3}\n$$\n"
        found = math_view.equations_from_markdown(text)
        self.assertEqual([(e["latex"], e["tag"]) for e in found], [("y = 2", "3")])

    def test_a_proposal_symlinked_outside_the_workspace_is_not_read(self) -> None:
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        secret = Path(outside.name) / "research-concept-x-r09.md"
        secret.write_text("## S\n\n$$\nsecret = 1\n$$\n", encoding="utf-8")
        (self.root / "proposals").mkdir()
        (self.root / "proposals" / "research-concept-x-r09.md").symlink_to(secret)
        self.assertEqual(math_view.build(self.root)["equations"], [])

        self.assertEqual(math_view.build(self.root)["source"], "none")

    def test_an_invalid_model_spec_is_not_named_as_the_source(self) -> None:
        (self.root / ".papersmith").mkdir()
        (self.root / ".papersmith" / "model_spec.json").write_text("{not json", encoding="utf-8")
        self.assertEqual(math_view.build(self.root)["source"], "none")

    def test_a_display_block_without_a_closing_fence_is_skipped(self) -> None:
        (self.root / "proposals").mkdir()
        (self.root / "proposals" / "research-concept-x-r01.md").write_text(
            "## A\n\n$$\nx = 1\n", encoding="utf-8")
        self.assertEqual(math_view.build(self.root)["equations"], [])


class ModelSpecTests(_Workspace):
    def test_a_model_spec_file_is_normalised(self) -> None:
        (self.root / ".papersmith").mkdir()
        (self.root / ".papersmith" / "model_spec.json").write_text(json.dumps({
            "title": "Hand-written spec",
            "novelty": {"problem_statement": "P", "pillars": [{"name": "N1", "summary": "S1"}]},
            "mathematical_model": {"core_equations": [
                {"id": "e1", "number": "(1)", "name": "Loss", "latex": "L = \\sum_i \\ell_i",
                 "description": "Total loss. Second sentence.",
                 "variables": [{"sym": "ell_i", "desc": "per-sample loss"}]}]},
        }), encoding="utf-8")
        view = math_view.build(self.root)
        self.assertEqual(view["source"], "model_spec:.papersmith/model_spec.json")
        eq = view["equations"][0]
        self.assertEqual((eq["heading"], eq["latex"], eq["tag"]), ("Loss", "L = \\sum_i \\ell_i", "1"))
        self.assertEqual(eq["connection"], "Total loss.")
        self.assertEqual(eq["variables"], [{"symbol": "ell_i", "meaning": "per-sample loss"}])
        self.assertEqual(view["novelty"]["problem"], "P")


class FallbackTests(_Workspace):
    def test_a_project_spec_supplies_its_latex_and_every_equation_compiles(self) -> None:
        (self.root / ".papersmith").mkdir()
        shutil.copy(FIXTURES / "moneeg" / "model_spec.json", self.root / ".papersmith" / "model_spec.json")
        view = math_view.build(self.root)
        self.assertEqual(view["source"], "model_spec:.papersmith/model_spec.json")
        self.assertGreaterEqual(len(view["equations"]), 6)
        self.assertEqual(compile_with_katex([e["latex"] for e in view["equations"]]), [])

    def test_a_folder_named_like_an_old_project_gets_nothing_from_it(self) -> None:
        target = self.root.parent / f"{self.root.name}-moneeg"
        shutil.copytree(self.root, target)
        self.addCleanup(shutil.rmtree, target, True)
        view = math_view.build(target)
        self.assertEqual((view["source"], view["equations"]), ("none", []))

    def test_an_empty_workspace_says_so(self) -> None:
        view = math_view.build(self.root)
        self.assertEqual(view["source"], "none")
        self.assertEqual(view["equations"], [])
        self.assertEqual(view["novelty"]["central_idea"], "QMLEEG")
        self.assertIn("Quantum ML for EEG", view["lema"])

    def test_the_route_serves_the_view(self) -> None:
        app = server.create_app(self.root, history_store=None)
        endpoint = next(r.endpoint for r in app.routes if getattr(r, "path", None) == "/api/model/math")
        body = json.loads(bytes(endpoint().body))
        self.assertEqual(body["source"], "none")


class VendoredKatexTests(unittest.TestCase):
    def test_katex_ships_with_its_fonts_and_license(self) -> None:
        vendor = STATIC / "vendor" / "katex"
        for name in ("katex.min.js", "katex.min.css", "LICENSE"):
            self.assertTrue((vendor / name).is_file(), name)
        self.assertTrue(any((vendor / "fonts").glob("KaTeX_Main-Regular.woff2")))


if __name__ == "__main__":
    unittest.main()
