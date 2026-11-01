"""The manuscript layer of the SOTA atlas: which pool systems the paper cites.

``skills/_core/command_center/atlas_manuscript.py`` derives
``sota-pool/atlas.manuscript.json`` from ``sota-pool/atlas.json``,
``sota-pool/candidates.json``, ``paper/main.tex``, ``paper/refs.bib`` and the
per-block evidence stores, and never modifies ``atlas.json``. These tests run
on a copy of ``tests/fixtures/atlas_manuscript/`` and go through the module's
public functions, its command line, ``smith atlas cited`` and the dashboard
route.
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
from skills._core.command_center import atlas_manuscript, server

REPO = Path(__file__).resolve().parent.parent
FIXTURE = REPO / "tests" / "fixtures" / "atlas_manuscript"
COMMAND_CENTER = REPO / "skills" / "_core" / "command_center"


def _routes(app) -> dict:
    return {(r.path, tuple(sorted(getattr(r, "methods", None) or ()))): r.endpoint
            for r in app.routes if hasattr(r, "path") and hasattr(r, "endpoint")}


def _route(app, path: str, method: str):
    for (route_path, methods), endpoint in _routes(app).items():
        if route_path == path and method in methods:
            return endpoint
    raise AssertionError(f"no {method} {path} route")


class _Workspace(unittest.TestCase):
    def workspace(self) -> Path:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        root = Path(holder.name).resolve() / "ws"
        shutil.copytree(FIXTURE, root)
        return root


class CitedSystemsTests(_Workspace):
    def test_each_system_is_marked_cited_or_not_with_its_blocks_and_claims(self) -> None:
        root = self.workspace()
        joined = atlas_manuscript.cited_systems(root)
        by_id = {s["id"]: s for s in joined["systems"]}
        self.assertEqual(list(by_id), ["sys-a", "sys-b", "sys-c"])
        self.assertTrue(by_id["sys-a"]["cited"])
        self.assertEqual(by_id["sys-a"]["cite_keys"], ["alpha2024"])
        self.assertEqual(by_id["sys-a"]["blocks"], ["intro", "methods"])
        self.assertEqual(by_id["sys-a"]["claims"], [
            {"block": "intro", "cite_key": "alpha2024", "claim": "Attention pooling is common.",
             "verdict": "insufficient"},
            {"block": "methods", "cite_key": "alpha2024", "claim": "Attention weights each instance.",
             "verdict": "holds"},
        ])
        self.assertEqual(by_id["sys-b"]["cite_keys"], ["beta2023"])
        self.assertEqual(by_id["sys-b"]["blocks"], ["intro"])
        # delta2021 has evidence against sys-c, but the text never cites it.
        self.assertFalse(by_id["sys-c"]["cited"])
        self.assertEqual((by_id["sys-c"]["cite_keys"], by_id["sys-c"]["blocks"],
                          by_id["sys-c"]["claims"]), ([], [], []))
        self.assertEqual(joined["cite_source"], "main.tex")

    def test_a_cited_paper_absent_from_the_pool_is_an_extra_system(self) -> None:
        root = self.workspace()
        extra = atlas_manuscript.cited_systems(root)["extra_systems"]
        self.assertEqual(extra, [{
            "cite_key": "gamma2022", "identifier": "10.9999/extra", "resolver": "crossref",
            "title": "A Study Outside the Pool", "blocks": ["intro"],
            "claims": [{"block": "intro", "cite_key": "gamma2022", "claim": "A newer study agrees.",
                        "verdict": "holds"}],
        }])

    def test_without_main_tex_the_bibliography_names_the_cited_keys(self) -> None:
        root = self.workspace()
        (root / "paper" / "main.tex").unlink()
        joined = atlas_manuscript.cited_systems(root)
        self.assertEqual(joined["cite_source"], "refs.bib")
        self.assertEqual([s["id"] for s in joined["systems"] if s["cited"]], ["sys-a", "sys-b"])


class LayerTests(_Workspace):
    def test_build_writes_the_layer_and_leaves_atlas_json_byte_identical(self) -> None:
        root = self.workspace()
        atlas_json = root / "sota-pool" / "atlas.json"
        before = atlas_json.read_bytes()
        result = atlas_manuscript.write_layer(root)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["path"], "sota-pool/atlas.manuscript.json")
        self.assertEqual(atlas_json.read_bytes(), before)
        layer = json.loads((root / "sota-pool" / "atlas.manuscript.json").read_text("utf-8"))
        self.assertEqual(layer["schema"], atlas_manuscript.SCHEMA)
        self.assertEqual(layer["summary"], {
            "systems_total": 3, "cited_systems": 2, "uncited_systems": ["sys-c"],
            "extra_cited": 1, "cited_keys": 3,
        })
        self.assertEqual(result["summary"], layer["summary"])
        self.assertEqual(sorted(layer["generated_from"]),
                         ["atlas.json", "candidates.json", "evidence", "main.tex", "refs.bib"])
        self.assertTrue(all(isinstance(v, str) and len(v) == 64
                            for v in layer["generated_from"].values()))

    def test_a_rebuild_on_unchanged_inputs_is_byte_identical(self) -> None:
        root = self.workspace()
        atlas_manuscript.write_layer(root)
        first = (root / "sota-pool" / "atlas.manuscript.json").read_bytes()
        atlas_manuscript.write_layer(root)
        self.assertEqual((root / "sota-pool" / "atlas.manuscript.json").read_bytes(), first)

    def test_read_layer_reports_staleness_when_an_input_changes(self) -> None:
        root = self.workspace()
        self.assertEqual(atlas_manuscript.read_layer(root)["status"], "absent")
        atlas_manuscript.write_layer(root)
        fresh = atlas_manuscript.read_layer(root)
        self.assertEqual((fresh["status"], fresh["stale"]), ("ok", False))
        self.assertEqual(fresh["layer"]["summary"]["cited_systems"], 2)
        refs = root / "paper" / "refs.bib"
        refs.write_text(refs.read_text("utf-8") + "\n", encoding="utf-8")
        self.assertEqual(atlas_manuscript.read_layer(root)["stale"], True)

    def test_no_atlas_means_no_layer_is_written(self) -> None:
        root = self.workspace()
        (root / "sota-pool" / "atlas.json").unlink()
        result = atlas_manuscript.write_layer(root)
        self.assertEqual((result["ok"], result["status"]), (False, "absent"))
        self.assertFalse((root / "sota-pool" / "atlas.manuscript.json").exists())

    def test_refresh_turns_a_builder_error_into_a_warning(self) -> None:
        root = self.workspace()
        (root / "sota-pool" / "atlas.json").write_text("{not json", encoding="utf-8")
        result = atlas_manuscript.refresh(root)
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "error")
        self.assertIn("warning", result)
        self.assertFalse((root / "sota-pool" / "atlas.manuscript.json").exists())

    def test_refresh_is_silent_without_an_atlas(self) -> None:
        root = self.workspace()
        shutil.rmtree(root / "sota-pool")
        self.assertIsNone(atlas_manuscript.refresh(root))


class CommandLineTests(_Workspace):
    def test_module_entry_point_writes_and_reports_json(self) -> None:
        root = self.workspace()
        proc = subprocess.run(
            [sys.executable, "-B", "-m", "skills._core.command_center.atlas_manuscript",
             "--root", str(root), "--json"],
            cwd=str(REPO), capture_output=True, text=True, timeout=60, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(json.loads(proc.stdout)["ok"])
        self.assertTrue((root / "sota-pool" / "atlas.manuscript.json").is_file())

    def run_smith(self, *argv: str) -> tuple[int, str, str]:
        args = build_parser("smith").parse_args(list(argv))
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = args.handler(args)
        return code, out.getvalue(), err.getvalue()

    def _with_kit(self, root: Path) -> None:
        center = root / "skills" / "_core" / "command_center"
        center.mkdir(parents=True)
        for name in ("__init__.py", "atlas_manuscript.py"):
            shutil.copy(COMMAND_CENTER / name, center / name)
        shutil.copytree(REPO / "skills" / "paper-writing" / "scripts",
                        root / "skills" / "paper-writing" / "scripts",
                        ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(REPO / "skills" / "_core" / "implementation",
                        root / "skills" / "_core" / "implementation",
                        ignore=shutil.ignore_patterns("__pycache__"))

    def test_smith_atlas_cited_writes_the_layer(self) -> None:
        root = self.workspace()
        self._with_kit(root)
        code, out, _err = self.run_smith("atlas", "cited", str(root))
        self.assertEqual(code, 0, out)
        self.assertIn("2/3 systems cited", out)
        self.assertTrue((root / "sota-pool" / "atlas.manuscript.json").is_file())

    def test_smith_atlas_cited_fails_closed_without_an_atlas(self) -> None:
        root = self.workspace()
        self._with_kit(root)
        (root / "sota-pool" / "atlas.json").unlink()
        code, _out, err = self.run_smith("atlas", "cited", "--json", str(root))
        self.assertEqual(code, 1)
        self.assertIn("atlas.json", err + _out)


class RouteTests(_Workspace):
    def test_get_api_atlas_manuscript_returns_the_layer(self) -> None:
        root = self.workspace()
        app = server.create_app(root, history_store=None)
        endpoint = _route(app, "/api/atlas/manuscript", "GET")
        absent = json.loads(bytes(endpoint().body))
        self.assertEqual(absent["status"], "absent")
        atlas_manuscript.write_layer(root)
        body = json.loads(bytes(endpoint().body))
        self.assertEqual((body["status"], body["stale"]), ("ok", False))
        self.assertEqual(body["layer"]["summary"]["uncited_systems"], ["sys-c"])


if __name__ == "__main__":
    unittest.main()
