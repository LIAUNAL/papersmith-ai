"""`smith doctor`: one table of project health rows for a workspace.

Every row is ``{area, item, state, detail}`` with ``state`` one of
``ok | warn | fail | absent``; the summary carries the worst state. A missing
tool is a row, never an exception, and a ``fail`` row makes the command exit
with ``EXECUTION_ERROR``.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from papersmith.cli import main
from papersmith.core import doctor
from papersmith.core import init as init_module
from papersmith.core.exit_codes import EXECUTION_ERROR, SUCCESS

STATES = {"ok", "warn", "fail", "absent"}


def _fake_backend(*, skill_state: str = "WIRED", phases=None) -> dict:
    """A backend payload shaped like ``doctor_view.backend_payload``."""
    return {
        "interpreter": "/usr/bin/python3",
        "python": {"version": "3.12.4", "ok": True},
        "packages": [
            {"name": "numpy", "module": "numpy", "present": True, "version": "2.0.0", "required": True},
            {"name": "docling", "module": "docling", "present": False, "version": None, "required": False},
        ],
        "wiring": {
            "harness_sync": {"state": "IN_SYNC", "harnesses": [
                {"tool": "claude", "prefix": ".claude", "state": "IN_SYNC", "detail": "ok"}]},
            "skills": [{"name": "paper-writing", "path": "skills/paper-writing/SKILL.md",
                        "state": skill_state, "core": True, "bytes": 10}],
            "cli_entrypoints": [],
            "agents": [{"name": "redactor", "path": ".claude/agents/redactor.md",
                        "state": "WIRED", "detail": "ok"}],
        },
        "phases": phases if phases is not None else [
            {"id": "Fase 1", "name": "Fase 1: Entorno", "status": "PASS", "detail": "listo"},
            {"id": "Fase 2", "name": "Fase 2: SOTA", "status": "PENDING", "detail": "pendiente"},
        ],
        "phases_error": None,
    }


def _capture(argv: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


class DoctorTests(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.tmp = Path(holder.name).resolve()
        self.workspace = self.tmp / "doctor-paper"
        init_module.initialize(self.workspace, run_npm=False, run_env=False)

    def test_cli_json_has_summary_rows_and_every_area(self) -> None:
        # The real backend: a subprocess of the workspace interpreter.
        code, out, _ = _capture(["doctor", str(self.workspace), "--json"])
        payload = json.loads(out)
        self.assertEqual(set(payload), {"summary", "rows"})
        self.assertIn(payload["summary"]["state"], STATES)
        for row in payload["rows"]:
            self.assertEqual(set(row), {"area", "item", "state", "detail"})
            self.assertIn(row["state"], STATES)
        areas = {row["area"] for row in payload["rows"]}
        self.assertEqual(areas, set(doctor.AREAS))
        items = {(row["area"], row["item"]) for row in payload["rows"]}
        for item in ("installed CLI", "kit", "workspace", "drift"):
            self.assertIn(("framework", item), items)
        for tool in ("git", "node", "micromamba", "latexmk", "lualatex", "pdflatex",
                     "pdftoppm", "pdftocairo", "gs", "sips"):
            self.assertIn(("tools", tool), items)
        self.assertIn(("skills", "paper-writing"), items)
        self.assertIn(("agents", "redactor"), items)
        self.assertTrue(any(area == "flows" and item.startswith("Phase 1:") for area, item in items))
        self.assertEqual(code, EXECUTION_ERROR if payload["summary"]["state"] == "fail" else SUCCESS)

    def test_a_missing_tool_is_a_row_not_an_exception(self) -> None:
        with mock.patch.object(doctor, "find_tool", lambda *a, **k: None):
            report = doctor.build_report(self.workspace, backend=_fake_backend())
        tools = {row["item"]: row for row in report["rows"] if row["area"] == "tools"}
        for name in ("git", "latexmk", "lualatex", "pdflatex", "pdftoppm", "gs", "sips"):
            self.assertIn(tools[name]["state"], {"warn", "absent"}, name)
        self.assertEqual(tools["TeX engine"]["state"], "warn")
        self.assertEqual(tools["rasterizer"]["state"], "warn")
        self.assertNotEqual(report["summary"]["state"], "fail")

    def test_tex_is_found_in_a_known_texlive_dir_when_path_misses_it(self) -> None:
        bindir = self.tmp / "texlive" / "2026" / "bin" / "x86_64-linux"
        bindir.mkdir(parents=True)
        engine = bindir / "lualatex"
        engine.write_text("#!/bin/sh\n", encoding="utf-8")
        engine.chmod(engine.stat().st_mode | stat.S_IXUSR)
        found = doctor.find_tool("lualatex", which=lambda _name: None,
                                 extra_dirs=(str(self.tmp / "texlive" / "*" / "bin" / "*"),))
        self.assertEqual(Path(found), engine)
        self.assertIsNone(doctor.find_tool("nope", which=lambda _name: None,
                                           extra_dirs=(str(self.tmp / "texlive" / "*" / "bin" / "*"),)))

    def test_summary_is_the_worst_state(self) -> None:
        self.assertEqual(doctor.worst(["ok", "absent", "warn"]), "warn")
        self.assertEqual(doctor.worst(["ok", "fail", "warn"]), "fail")
        self.assertEqual(doctor.worst([]), "ok")
        report = doctor.build_report(self.workspace, backend=_fake_backend(skill_state="MISSING"))
        skill = next(r for r in report["rows"] if r["area"] == "skills" and r["item"] == "paper-writing")
        self.assertEqual(skill["state"], "fail")
        self.assertEqual(report["summary"]["state"], "fail")
        self.assertEqual(report["summary"]["state"], doctor.worst(r["state"] for r in report["rows"]))

    def test_phases_map_to_states(self) -> None:
        report = doctor.build_report(self.workspace, backend=_fake_backend(phases=[
            {"name": "Fase 1: A", "status": "PASS", "detail": "x"},
            {"name": "Fase 2: B", "status": "PENDING", "detail": "y"},
            {"name": "Fase 3: C", "status": "BLOCKED", "detail": "z"},
        ]))
        flows = {r["item"]: r["state"] for r in report["rows"] if r["area"] == "flows"}
        self.assertEqual(flows, {"Fase 1: A": "ok", "Fase 2: B": "absent", "Fase 3: C": "warn"})

    def test_a_fail_row_exits_with_execution_error_and_prints_a_table(self) -> None:
        with mock.patch.object(doctor, "load_backend",
                               lambda root: (_fake_backend(skill_state="MISSING"), None)):
            code, out, _ = _capture(["doctor", str(self.workspace)])
        self.assertEqual(code, EXECUTION_ERROR)
        self.assertIn("AREA", out)
        self.assertIn("paper-writing", out)
        self.assertIn("Summary: FAIL", out)

    def test_a_healthy_report_exits_zero(self) -> None:
        with mock.patch.object(doctor, "load_backend", lambda root: (_fake_backend(), None)), \
                mock.patch.object(doctor, "find_tool", lambda *a, **k: "/usr/bin/tool"):
            code, out, _ = _capture(["doctor", str(self.workspace), "--json"])
        self.assertEqual(code, SUCCESS, out)
        self.assertNotEqual(json.loads(out)["summary"]["state"], "fail")

    def test_an_unavailable_backend_degrades_to_warn_rows(self) -> None:
        with mock.patch.object(doctor, "load_backend", lambda root: (None, "no interpreter")):
            code, out, _ = _capture(["doctor", str(self.workspace), "--json"])
        payload = json.loads(out)
        backend_rows = [r for r in payload["rows"] if r["area"] in {"packages", "skills", "agents", "flows"}]
        self.assertTrue(backend_rows)
        self.assertTrue(all(r["state"] == "warn" for r in backend_rows))
        self.assertTrue(any("no interpreter" in r["detail"] for r in backend_rows))
        self.assertEqual(code, SUCCESS)

    def test_outside_a_workspace_is_a_user_error(self) -> None:
        code, _, err = _capture(["doctor", str(self.tmp)])
        self.assertEqual(code, 1)
        self.assertIn("not a papersmith workspace", err)

    def test_the_command_is_documented(self) -> None:
        docs = (Path(__file__).resolve().parents[1] / "docs" / "cli.md").read_text(encoding="utf-8")
        self.assertIn("### `smith doctor [<dir>]`", docs)
        self.assertIn("| `doctor` |", docs)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
