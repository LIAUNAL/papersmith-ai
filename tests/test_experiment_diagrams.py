"""experiment-diagrams: the PoC and full-experiments diagrams, driven through
`skills/experiment-diagrams/scripts/diagram_cli.py`.

Every test builds its own product folder under a temporary directory and never
writes into this checkout. A test that needs a real TeX toolchain and a
rasterizer is skipped when the machine lacks them (CI may have no TeX).
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
CLI = REPO / "skills" / "experiment-diagrams" / "scripts" / "diagram_cli.py"

PROPOSAL = "research-concept-sample-r02.md"
EXPERIMENTS = "experiments-sample-v03.md"

AGREED = f"""# Agreed

## Ladder

<!-- position revision={PROPOSAL} sha256=00 derivedAt=2026-10-26T00:00:00Z -->
- [x] 1. Time one epoch of fold 0 per arm (timing probe). `@step time_probe`
- [x] 2. Train the three arms on fold 0 of the toy set (pilot). `@step poc_train`
- [ ] 3. Render convergence and subject-level pilot tables. `@step poc_report`
<!-- /position -->
"""

EXPERIMENTAL_AGREED = f"""# Agreed

## Ladder

<!-- position revision={EXPERIMENTS} sha256=00 derivedAt=2026-10-26T00:00:00Z -->
- [ ] 1. Run the full grid of every arm. `@step full_run`
- [ ] 2. Report the significance table and figures. `@step full_report`
<!-- /position -->
"""

PROPOSAL_TEXT = """# Hybrid re-uploading classifier for EEG

## Exploring quantum data re-uploading circuits to classify ADHD from EEG
"""

EXPERIMENTS_TEXT = """# Hybrid re-uploading classifier for EEG

## Experimental Protocol and Empirical Validation Plan

## Experiment [exp:E1] — Hybrid classification and Fourier expressivity

## Experiment [exp:E2] — Entanglement topology ablation

## Experiment [exp:E3] — Re-uploading depth and barren plateaus
"""


def _tex_available() -> bool:
    return any(shutil.which(t) for t in ("latexmk", "lualatex", "pdflatex"))


def _raster_available() -> bool:
    return any(shutil.which(t) for t in ("pdftoppm", "pdftocairo", "gs", "sips"))


def _load_cli():
    spec = importlib.util.spec_from_file_location("diagram_cli_under_test", CLI)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Workspace:
    """A forge-shaped tree: `implementations/<repo>/<Name>/` plus the
    `proposals/` and `experiments/` the approval markers name."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.target = root / "implementations" / "sample-repo"
        self.product = self.target / "Sample"
        self.product.mkdir(parents=True)
        (root / "proposals").mkdir()
        (root / "experiments").mkdir()
        (root / "proposals" / PROPOSAL).write_text(PROPOSAL_TEXT, encoding="utf-8")
        (root / "experiments" / EXPERIMENTS).write_text(EXPERIMENTS_TEXT, encoding="utf-8")

    def approve(self, kind: str) -> None:
        if kind == "poc":
            (self.product / "AGREED.md").write_text(AGREED, encoding="utf-8")
        else:
            (self.product / "Experimental_AGREED.md").write_text(EXPERIMENTAL_AGREED, encoding="utf-8")


def run_cli(*args: str, env: dict | None = None) -> tuple[int, dict]:
    proc = subprocess.run(
        [sys.executable, str(CLI), *args],
        capture_output=True, text=True, timeout=300, env=env,
    )
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:  # pragma: no cover - diagnostic
        raise AssertionError(f"stdout is not one JSON object: {proc.stdout!r} {proc.stderr!r}") from exc
    return proc.returncode, payload


class DiagramCliTests(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory(prefix="experiment-diagrams-")
        self.addCleanup(holder.cleanup)
        self.ws = _Workspace(Path(holder.name))

    def derive(self, kind: str) -> tuple[int, dict]:
        return run_cli("derive", "--target", str(self.ws.target), "--name", "Sample", "--kind", kind)

    # -- derive -----------------------------------------------------------------

    def test_derive_refuses_approval_absent_without_the_marker(self) -> None:
        for kind in ("poc", "experiments"):
            code, payload = self.derive(kind)
            self.assertNotEqual(code, 0)
            self.assertEqual(payload["error"], "APPROVAL_ABSENT")
            self.assertFalse((self.ws.product / "diagrams" / f"{kind}.json").exists())

    def test_derive_writes_a_valid_spec_with_the_marker(self) -> None:
        for kind in ("poc", "experiments"):
            self.ws.approve(kind)
            code, payload = self.derive(kind)
            self.assertEqual(code, 0, payload)
            spec_path = self.ws.product / "diagrams" / f"{kind}.json"
            self.assertTrue(spec_path.is_file())
            self.assertEqual(Path(payload["spec"]).resolve(), spec_path.resolve())
            spec = json.loads(spec_path.read_text(encoding="utf-8"))
            self.assertEqual(spec["kind"], kind)
            self.assertTrue(spec["claim"].strip())
            focal = [n for n in spec["nodes"] if n["role"] == "focal"]
            self.assertEqual(len(focal), 1)
            self.assertEqual(spec["focal"], focal[0]["id"])
            self.assertEqual(_load_cli().validate_spec(spec), [])

    def test_derive_reads_the_evidence_the_marker_names(self) -> None:
        self.ws.approve("poc")
        self.ws.approve("experiments")
        self.derive("poc")
        self.derive("experiments")
        poc = (self.ws.product / "diagrams" / "poc.json").read_text(encoding="utf-8")
        experiments = (self.ws.product / "diagrams" / "experiments.json").read_text(encoding="utf-8")
        self.assertIn("pilot", poc.lower())
        self.assertIn(PROPOSAL, poc)
        self.assertIn("Entanglement topology ablation", experiments)
        self.assertIn(EXPERIMENTS, experiments)

    def test_derive_keeps_an_existing_spec(self) -> None:
        self.ws.approve("poc")
        self.derive("poc")
        spec_path = self.ws.product / "diagrams" / "poc.json"
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        spec["claim"] = "An edited claim the designer wrote."
        spec_path.write_text(json.dumps(spec), encoding="utf-8")
        code, payload = self.derive("poc")
        self.assertEqual(code, 0, payload)
        self.assertFalse(payload["written"])
        self.assertIn("An edited claim", spec_path.read_text(encoding="utf-8"))

    # -- render -----------------------------------------------------------------

    def _spec(self, kind: str = "poc") -> Path:
        self.ws.approve(kind)
        self.derive(kind)
        return self.ws.product / "diagrams" / f"{kind}.json"

    def test_render_refuses_spec_invalid_naming_the_field(self) -> None:
        spec_path = self._spec()
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        spec["edges"][0]["semantics"] = "teleport"
        spec_path.write_text(json.dumps(spec), encoding="utf-8")
        code, payload = run_cli("render", "--spec", str(spec_path))
        self.assertNotEqual(code, 0)
        self.assertEqual(payload["error"], "SPEC_INVALID")
        self.assertIn("edges[0].semantics", payload["message"])
        self.assertFalse((spec_path.parent / "poc.tex").exists())

    def test_render_refuses_a_spec_without_a_claim(self) -> None:
        spec_path = self._spec()
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        spec["claim"] = "  "
        spec_path.write_text(json.dumps(spec), encoding="utf-8")
        code, payload = run_cli("render", "--spec", str(spec_path))
        self.assertNotEqual(code, 0)
        self.assertEqual(payload["error"], "SPEC_INVALID")
        self.assertIn("claim", payload["message"])

    def test_render_refuses_a_missing_spec_file(self) -> None:
        code, payload = run_cli("render", "--spec", str(self.ws.product / "diagrams" / "poc.json"))
        self.assertNotEqual(code, 0)
        self.assertEqual(payload["error"], "SPEC_INVALID")

    def test_render_without_tex_refuses_and_leaves_the_tex(self) -> None:
        spec_path = self._spec()
        cli = _load_cli()
        out = io.StringIO()
        with mock.patch.dict(os.environ, {"PATH": ""}), \
                mock.patch.object(cli, "TEX_FALLBACK_DIRS", ()), \
                contextlib.redirect_stdout(out):
            code = cli.main(["render", "--spec", str(spec_path)])
        payload = json.loads(out.getvalue())
        self.assertNotEqual(code, 0)
        self.assertEqual(payload["error"], "TEX_TOOLCHAIN_ABSENT")
        tex = spec_path.parent / "poc.tex"
        self.assertTrue(tex.is_file())
        self.assertEqual(Path(payload["tex"]).resolve(), tex.resolve())
        self.assertFalse((spec_path.parent / "poc.pdf").exists())

    def test_tex_discovery_finds_nothing_on_an_empty_path(self) -> None:
        cli = _load_cli()
        with mock.patch.object(cli, "TEX_FALLBACK_DIRS", ()):
            self.assertIsNone(cli.find_tex_engine(path=""))
        with mock.patch.object(cli, "RASTER_FALLBACK_DIRS", ()):
            self.assertIsNone(cli.find_rasterizer(path=""))

    def test_tex_discovery_searches_the_fallback_dirs(self) -> None:
        cli = _load_cli()
        with tempfile.TemporaryDirectory() as bindir:
            tool = Path(bindir) / "pdflatex"
            tool.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            tool.chmod(0o755)
            with mock.patch.object(cli, "TEX_FALLBACK_DIRS", (bindir,)):
                found = cli.find_tex_engine(path="")
        self.assertIsNotNone(found)
        self.assertEqual(found[0], "pdflatex")

    def test_render_writes_the_tex_library_and_palette(self) -> None:
        spec_path = self._spec("experiments")
        run_cli("render", "--spec", str(spec_path))
        tex = (spec_path.parent / "experiments.tex").read_text(encoding="utf-8")
        self.assertIn("\\documentclass", tex)
        self.assertIn("standalone", tex)
        self.assertIn("\\tikzset", tex)
        for name, hexcode in (("psCanvas", "F7F3E8"), ("psInk", "20252B"), ("psCool", "4F7CAC"),
                              ("psWarm", "E09F3E"), ("psAlert", "D96855")):
            self.assertIn(f"\\definecolor{{{name}}}{{HTML}}{{{hexcode}}}", tex)
        for style in ("ps operator", "ps state", "ps focal", "ps evidence", "ps context",
                      "ps primary", "ps secondary", "ps supervision", "ps feedback"):
            self.assertIn(style, tex)

    @unittest.skipUnless(_tex_available() and _raster_available(),
                         "needs a TeX engine and a rasterizer on PATH")
    def test_render_compiles_pdf_and_png(self) -> None:
        for kind in ("poc", "experiments"):
            spec_path = self._spec(kind)
            code, payload = run_cli("render", "--spec", str(spec_path))
            self.assertEqual(code, 0, payload)
            pdf = spec_path.parent / f"{kind}.pdf"
            png = spec_path.parent / f"{kind}.png"
            self.assertTrue(pdf.is_file() and pdf.read_bytes().startswith(b"%PDF"))
            self.assertTrue(png.is_file() and png.read_bytes().startswith(b"\x89PNG"))
            self.assertEqual(Path(payload["png"]).resolve(), png.resolve())

    # -- status -----------------------------------------------------------------

    def test_status_reports_each_kind(self) -> None:
        code, payload = run_cli("status", "--target", str(self.ws.target), "--name", "Sample")
        self.assertEqual(code, 0, payload)
        for kind in ("poc", "experiments"):
            entry = payload["kinds"][kind]
            for field in ("approved", "spec", "tex", "pdf", "png"):
                self.assertIs(entry[field], False, (kind, field))
        self.ws.approve("poc")
        self.derive("poc")
        code, payload = run_cli("status", "--target", str(self.ws.target), "--name", "Sample")
        self.assertEqual(code, 0, payload)
        self.assertTrue(payload["kinds"]["poc"]["approved"])
        self.assertTrue(payload["kinds"]["poc"]["spec"])
        self.assertFalse(payload["kinds"]["poc"]["tex"])
        self.assertFalse(payload["kinds"]["experiments"]["approved"])
        self.assertFalse(payload["kinds"]["experiments"]["spec"])

    def test_status_refuses_an_absent_product(self) -> None:
        code, payload = run_cli("status", "--target", str(self.ws.target), "--name", "Nobody")
        self.assertNotEqual(code, 0)
        self.assertEqual(payload["error"], "PRODUCT_ABSENT")


class SkillDoctrineTests(unittest.TestCase):
    def test_skill_attributes_sivia_and_names_the_four_roles(self) -> None:
        text = (REPO / "skills" / "experiment-diagrams" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("github.com/exsinger-hub/Sivia", text)
        for role in ("Designer", "Drawer", "Reviewer", "Corrector", "grayscale"):
            self.assertIn(role, text)

    def test_the_implementation_flows_call_the_diagram_step(self) -> None:
        poc = (REPO / "skills" / "proposal-implementation" / "SKILL.md").read_text(encoding="utf-8")
        full = (REPO / "skills" / "experimental-implementation" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("/experiment-diagrams poc", poc)
        self.assertIn("/experiment-diagrams experiments", full)


if __name__ == "__main__":
    unittest.main()
