"""One TeX and rasterizer search order for every caller.

`smith doctor` (CLI interpreter), `experiment-diagrams` (stdlib-only script)
and the dashboard (workspace interpreter) cannot share one import, so each
restates the fallback directories. These tests fail when the copies drift,
and check that each search looks at PATH first and then the newest TeX Live
year first. Every file they create lives under a temporary directory.
"""
from __future__ import annotations

import ast
import importlib.util
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
CANONICAL = REPO / "skills" / "_core" / "command_center" / "toolchain.py"
COPIES = (
    REPO / "src" / "papersmith" / "core" / "doctor.py",
    REPO / "skills" / "experiment-diagrams" / "scripts" / "diagram_cli.py",
)
EXPECTED = (
    "/Library/TeX/texbin",
    "/opt/homebrew/bin",
    "/usr/local/bin",
    "/usr/local/texlive/*/bin/*",
    "/opt/texlive/*/bin/*",
    "~/texlive/*/bin/*",
)


def _constant(path: Path, name: str = "TOOL_FALLBACK_DIRS"):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
            value = node.value
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
            value = node.value
        if any(isinstance(t, ast.Name) and t.id == name for t in targets):
            return ast.literal_eval(value)
    raise AssertionError(f"{path.name} does not define {name}")


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _tool(directory: Path, name: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)
    return path


class FallbackListsAgree(unittest.TestCase):
    def test_every_copy_matches_the_canonical_list(self) -> None:
        canonical = _constant(CANONICAL)
        self.assertEqual(tuple(canonical), EXPECTED)
        for copy in COPIES:
            with self.subTest(copy=copy.name):
                self.assertEqual(tuple(_constant(copy)), tuple(canonical))

    def test_diagram_cli_uses_one_list_for_engines_and_rasterizers(self) -> None:
        cli = _load(COPIES[1], "diagram_cli_for_toolchain_test")
        self.assertEqual(cli.TEX_FALLBACK_DIRS, cli.TOOL_FALLBACK_DIRS)
        self.assertEqual(cli.RASTER_FALLBACK_DIRS, cli.TOOL_FALLBACK_DIRS)


class SearchOrder(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.old = _tool(self.tmp / "texlive" / "2024" / "bin" / "x86_64-linux", "pdflatex")
        self.new = _tool(self.tmp / "texlive" / "2025" / "bin" / "x86_64-linux", "pdflatex")
        self.pattern = (str(self.tmp / "texlive" / "*" / "bin" / "*"),)
        self.on_path = _tool(self.tmp / "onpath", "pdflatex")

    def test_canonical_search_prefers_path_then_newest_year(self) -> None:
        from skills._core.command_center import toolchain

        self.assertEqual(toolchain.find_tool("pdflatex", path=str(self.on_path.parent),
                                             fallback_dirs=self.pattern), str(self.on_path))
        self.assertEqual(toolchain.find_tool("pdflatex", path="", fallback_dirs=self.pattern),
                         str(self.new))
        self.assertIsNone(toolchain.find_tool("nope", path="", fallback_dirs=self.pattern))

    def test_doctor_search_prefers_newest_year(self) -> None:
        from papersmith.core import doctor

        self.assertEqual(doctor.find_tool("pdflatex", which=lambda _n: None,
                                          extra_dirs=self.pattern), str(self.new))

    def test_diagram_cli_search_prefers_newest_year(self) -> None:
        cli = _load(COPIES[1], "diagram_cli_for_toolchain_order")
        with mock.patch.object(cli, "TEX_FALLBACK_DIRS", self.pattern):
            self.assertEqual(cli.find_tex_engine(path=""), ("pdflatex", str(self.new)))


class DashboardUsesTheSearch(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_compile_paper_finds_tex_outside_path(self) -> None:
        from skills._core.command_center import server, toolchain

        texbin = self.tmp / "texlive" / "2025" / "bin" / "x86_64-linux"
        pdflatex = _tool(texbin, "pdflatex")
        bibtex = _tool(texbin, "bibtex")
        (self.tmp / "ws" / "paper").mkdir(parents=True)
        calls = []

        def fake_run(argv, **kwargs):
            calls.append((argv, kwargs["env"]["PATH"]))
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

        with mock.patch.dict(os.environ, {"PATH": str(self.tmp / "empty")}), \
                mock.patch.object(toolchain, "TOOL_FALLBACK_DIRS",
                                  (str(self.tmp / "texlive" / "*" / "bin" / "*"),)), \
                mock.patch.object(server.subprocess, "run", fake_run):
            payload, status = server._compile_paper(self.tmp / "ws")
        self.assertEqual(status, 200, payload)
        self.assertEqual([argv[0] for argv, _ in calls],
                         [str(pdflatex), str(bibtex), str(pdflatex), str(pdflatex)])
        self.assertTrue(calls[0][1].split(os.pathsep)[0] == str(texbin))

    def test_compile_paper_keeps_tools_found_on_path(self) -> None:
        from skills._core.command_center import server

        onpath = self.tmp / "onpath"
        pdflatex = _tool(onpath, "pdflatex")
        bibtex = _tool(onpath, "bibtex")
        (self.tmp / "ws" / "paper").mkdir(parents=True)
        calls = []

        def fake_run(argv, **kwargs):
            calls.append(argv)
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

        with mock.patch.dict(os.environ, {"PATH": str(onpath)}), \
                mock.patch.object(server.subprocess, "run", fake_run):
            _payload, status = server._compile_paper(self.tmp / "ws")
        self.assertEqual(status, 200)
        self.assertEqual([argv[0] for argv in calls],
                         [str(pdflatex), str(bibtex), str(pdflatex), str(pdflatex)])
        self.assertEqual(calls[1][1:], ["main"])

    def test_health_inspector_reports_every_tex_tool_through_the_search(self) -> None:
        from skills._core.command_center import health_inspector, toolchain

        texbin = self.tmp / "texlive" / "2025" / "bin" / "x86_64-linux"
        lualatex = _tool(texbin, "lualatex")
        latexmk = _tool(texbin, "latexmk")
        with mock.patch.dict(os.environ, {"PATH": str(self.tmp / "empty")}), \
                mock.patch.object(toolchain, "TOOL_FALLBACK_DIRS",
                                  (str(self.tmp / "texlive" / "*" / "bin" / "*"),)):
            latex = health_inspector.environment_health(self.tmp)["latex"]
        self.assertEqual(latex["state"], "WIRED")
        self.assertEqual(latex["engine"], str(lualatex))
        self.assertEqual(latex["tools"], {"pdflatex": None, "xelatex": None,
                                          "lualatex": str(lualatex), "latexmk": str(latexmk)})


if __name__ == "__main__":
    unittest.main()
