"""Figure provenance (#181 item 5, daprosero-backlog S3): "The figure
manifest records the generating script and its data inputs inside the
repository, and `render`/`audit` refuse or warn when they are missing."

Exercised through `paper_cli.py` as real subprocesses. `figure provenance`
writes the manifest's `provenance` key (repository-relative paths, one
sha256 each); `render` and `figure audit` report `provenanceWarnings` and
never refuse on them. Fixtures live under the git-ignored `.scratch/`.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

FORGE_ROOT = Path(__file__).resolve().parents[1]
CLI = FORGE_ROOT / "skills" / "paper-writing" / "scripts" / "paper_cli.py"
sys.path.insert(0, str(FORGE_ROOT / "tests"))
from test_paper_figure import _install_stub_latexmk  # noqa: E402

_SECTION = (
    b"---\n" + json.dumps({
        "section": "demo", "position": 1,
        "blocks": [{
            "id": "b1", "requires_facts": [], "requires_declarations": [],
            "citations": "none",
        }],
    }).encode("utf-8") + b"\n---\nThe box feeds the model.\n"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FigureProvenanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = FORGE_ROOT / ".scratch" / f"figure-provenance-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.paper_dir = self.root / "paper"
        self.figures = self.paper_dir / "Figures"
        self.figures.mkdir(parents=True)
        (self.figures / "diagP.tex").write_text("% node: box\n", encoding="utf-8")
        self.manifest = self.figures / "diagP.diagram.json"
        self.manifest.write_text(json.dumps({"components": ["box"]}), encoding="utf-8")
        self.script = self.root / "scripts" / "plot_diag.py"
        self.script.parent.mkdir()
        self.script.write_text("print('plot')\n", encoding="utf-8")
        self.data = self.root / "data" / "coords.csv"
        self.data.parent.mkdir()
        self.data.write_text("x,y\n1,2\n", encoding="utf-8")
        self.sections = self.root / "sections"
        self.sections.mkdir()
        (self.sections / "demo.md").write_bytes(_SECTION)
        self.bin_dir = Path(self._tmp.name) / "bin"
        _install_stub_latexmk(self.bin_dir)

    def _run(self, *args: str) -> tuple[int, dict]:
        env = dict(os.environ, STUB_MODE="success")
        proc = subprocess.run(
            [sys.executable, str(CLI), *args], capture_output=True, text=True, timeout=60, env=env,
        )
        return proc.returncode, json.loads(proc.stdout)

    def _rel(self, path: Path) -> str:
        return path.relative_to(FORGE_ROOT).as_posix()

    def _record(self, *extra: str) -> tuple[int, dict]:
        return self._run(
            "figure", "provenance", "--paper", str(self.paper_dir), "--figure-id", "diagP",
            "--script", str(self.script), "--input", str(self.data), *extra,
        )

    def _render(self) -> tuple[int, dict]:
        return self._run(
            "render", "--paper", str(self.paper_dir), "--figure-id", "diagP",
            "--latexmk-path", str(self.bin_dir),
        )

    def _audit(self) -> tuple[int, dict]:
        return self._run(
            "figure", "audit", "--paper", str(self.paper_dir), "--figure-id", "diagP",
            "--section", "demo", "--sections", str(self.sections),
        )

    def _codes(self, payload: dict) -> list:
        return [(w["code"], w["role"]) for w in payload["provenanceWarnings"]]

    # -- recording --------------------------------------------------------

    def test_provenance_records_repository_relative_paths_with_digests(self) -> None:
        code, payload = self._record()
        self.assertEqual(code, 0, payload)
        expected = {
            "script": {"path": self._rel(self.script), "sha256": _sha256(self.script)},
            "inputs": [{"path": self._rel(self.data), "sha256": _sha256(self.data)}],
        }
        self.assertEqual(payload["provenance"], expected)
        on_disk = json.loads(self.manifest.read_text(encoding="utf-8"))
        self.assertEqual(on_disk, {"components": ["box"], "provenance": expected})

    def test_provenance_refuses_a_path_outside_the_repository_and_writes_nothing(self) -> None:
        before = self.manifest.read_bytes()
        outside = Path(self._tmp.name) / "outside.py"
        outside.write_text("x\n", encoding="utf-8")
        code, payload = self._run(
            "figure", "provenance", "--paper", str(self.paper_dir), "--figure-id", "diagP",
            "--script", str(outside),
        )
        self.assertEqual(code, 2, payload)
        self.assertEqual(payload["code"], "PAPER_OUTSIDE_REPOSITORY")
        self.assertEqual(self.manifest.read_bytes(), before)

    def test_provenance_refuses_a_missing_input_and_writes_nothing(self) -> None:
        before = self.manifest.read_bytes()
        code, payload = self._run(
            "figure", "provenance", "--paper", str(self.paper_dir), "--figure-id", "diagP",
            "--script", str(self.script), "--input", str(self.root / "data" / "gone.csv"),
        )
        self.assertEqual(code, 2, payload)
        self.assertEqual(payload["code"], "TARGET_UNREADABLE")
        self.assertEqual(self.manifest.read_bytes(), before)

    # -- render -----------------------------------------------------------

    def test_a_manifest_without_provenance_still_renders_and_warns(self) -> None:
        before = self.manifest.read_bytes()
        code, payload = self._render()
        self.assertEqual(code, 0, payload)
        self.assertEqual(payload["verdict"], "success")
        self.assertEqual(
            self._codes(payload),
            [("FIGURE_PROVENANCE_UNRECORDED", "script"), ("FIGURE_PROVENANCE_UNRECORDED", "inputs")],
        )
        self.assertEqual(self.manifest.read_bytes(), before)

    def test_recorded_provenance_renders_without_warnings(self) -> None:
        self._record()
        code, payload = self._render()
        self.assertEqual(code, 0, payload)
        self.assertEqual(payload["verdict"], "success")
        self.assertEqual(payload["provenanceWarnings"], [])

    def test_a_changed_input_warns_on_render(self) -> None:
        self._record()
        self.data.write_text("x,y\n1,3\n", encoding="utf-8")
        code, payload = self._render()
        self.assertEqual(code, 0, payload)
        self.assertEqual(self._codes(payload), [("FIGURE_PROVENANCE_CHANGED", "input")])
        self.assertEqual(payload["provenanceWarnings"][0]["path"], self._rel(self.data))

    def test_a_deleted_script_warns_on_render(self) -> None:
        self._record()
        self.script.unlink()
        code, payload = self._render()
        self.assertEqual(code, 0, payload)
        self.assertEqual(payload["verdict"], "success")
        self.assertEqual(self._codes(payload), [("FIGURE_PROVENANCE_MISSING", "script")])

    def test_a_path_outside_the_repository_warns_on_render(self) -> None:
        manifest = {
            "components": ["box"],
            "provenance": {
                "script": {"path": "../elsewhere/plot.py", "sha256": "0" * 64},
                "inputs": [{"path": "/tmp/coords.csv", "sha256": "0" * 64}],
            },
        }
        self.manifest.write_text(json.dumps(manifest), encoding="utf-8")
        code, payload = self._render()
        self.assertEqual(code, 0, payload)
        self.assertEqual(
            self._codes(payload),
            [("FIGURE_PROVENANCE_OUTSIDE_REPOSITORY", "script"),
             ("FIGURE_PROVENANCE_OUTSIDE_REPOSITORY", "input")],
        )

    # -- audit ------------------------------------------------------------

    def test_a_manifest_without_provenance_still_audits_and_warns(self) -> None:
        before = self.manifest.read_bytes()
        code, payload = self._audit()
        self.assertEqual(code, 0, payload)
        self.assertEqual(payload["status"], "ok")
        self.assertIn(payload["verdict"], {"pass", "fail", "unmeasured"})
        self.assertEqual(
            self._codes(payload),
            [("FIGURE_PROVENANCE_UNRECORDED", "script"), ("FIGURE_PROVENANCE_UNRECORDED", "inputs")],
        )
        self.assertEqual(self.manifest.read_bytes(), before)

    def test_audit_verdict_is_unchanged_by_provenance(self) -> None:
        _, legacy = self._audit()
        self._record()
        self.data.write_text("changed\n", encoding="utf-8")
        code, payload = self._audit()
        self.assertEqual(code, 0, payload)
        self.assertEqual(payload["verdict"], legacy["verdict"])
        self.assertEqual(self._codes(payload), [("FIGURE_PROVENANCE_CHANGED", "input")])


if __name__ == "__main__":
    unittest.main()
