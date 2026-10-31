"""POST /api/phase/run runs a stage's commands off the event loop, bounds
every TeX run by a timeout, and lets one paper job write paper/ at a time."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from skills._core.command_center import server


class Req:
    def __init__(self, body):
        self.body = body
        self.headers = {}  # a same-origin guard reads it; no Origin header, as from curl

    async def json(self):
        return self.body


class Recorder:
    """An inert subprocess.run: records argv, kwargs and the calling thread."""

    def __init__(self, fail_on: str | None = None):
        self.calls: list[tuple[list[str], dict, bool]] = []
        self.fail_on = fail_on

    def __call__(self, argv, **kwargs):
        self.calls.append((list(argv), kwargs, threading.current_thread() is threading.main_thread()))
        if self.fail_on and argv[0] == self.fail_on:
            raise subprocess.TimeoutExpired(argv, kwargs.get("timeout"))
        return subprocess.CompletedProcess(argv, 0, stdout="ok", stderr="")


class PhaseRunHandlerTests(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.root = Path(holder.name).resolve() / "paper-ws"
        (self.root / "paper").mkdir(parents=True)
        (self.root / "paper" / "main.tex").write_text("\\documentclass{article}\n", encoding="utf-8")
        self.endpoint = next(r.endpoint for r in server.create_app(self.root, history_store=None).routes
                             if getattr(r, "path", None) == "/api/phase/run")

    def run_phase(self, phase_id: str, stub) -> tuple[int, dict]:
        with mock.patch.object(server.subprocess, "run", stub):
            response = asyncio.run(self.endpoint(Req({"phase_id": phase_id})))
        return response.status_code, json.loads(bytes(response.body))

    def test_compile_reaches_pdflatex_with_the_inherited_path(self) -> None:
        stub = Recorder()
        with mock.patch.dict("os.environ", {"PATH": "/usr/bin:/bin"}):
            status, body = self.run_phase("Fase 10", stub)
        self.assertEqual(status, 200, body)
        self.assertTrue(body["ok"])
        self.assertEqual([c[0][0] for c in stub.calls], ["pdflatex", "bibtex", "pdflatex", "pdflatex"])
        self.assertEqual(stub.calls[0][0], ["pdflatex", "-interaction=nonstopmode", "main.tex"])
        self.assertEqual(stub.calls[0][1]["cwd"], str(self.root / "paper"))
        # The inherited PATH is kept, after any TeX directory the search found
        # (none on a runner without TeX, MacTeX or TeX Live elsewhere).
        self.assertEqual(stub.calls[0][1]["env"]["PATH"].split(os.pathsep)[-2:], ["/usr/bin", "/bin"])
        self.assertEqual(body["outputs"], ["paper/main.pdf"])

    def test_every_tex_run_has_a_timeout(self) -> None:
        stub = Recorder()
        self.run_phase("Fase 10", stub)
        self.assertEqual(len(stub.calls), 4)
        for argv, kwargs, _ in stub.calls:
            with self.subTest(argv=argv):
                self.assertIsInstance(kwargs.get("timeout"), (int, float))

    def test_a_tex_run_that_times_out_fails_the_check(self) -> None:
        stub = Recorder(fail_on="bibtex")
        status, body = self.run_phase("Fase 10", stub)
        self.assertEqual(status, 504)
        self.assertFalse(body["ok"])
        self.assertIn("bibtex", body["error"])
        self.assertEqual([c[0][0] for c in stub.calls], ["pdflatex", "bibtex"])

    def test_stage_commands_run_off_the_event_loop(self) -> None:
        script = self.root / "scripts" / "build_manuscript.py"
        script.parent.mkdir()
        script.write_text("print('built')\n", encoding="utf-8")
        for phase_id in ("Fase 10", "Fase 8"):
            stub = Recorder()
            status, body = self.run_phase(phase_id, stub)
            with self.subTest(phase=phase_id):
                self.assertEqual(status, 200, body)
                self.assertTrue(stub.calls)
                self.assertFalse(any(on_main for _, _, on_main in stub.calls))

    def test_the_writing_stage_still_runs_its_build_script(self) -> None:
        script = self.root / "scripts" / "build_manuscript.py"
        script.parent.mkdir()
        script.write_text("print('built')\n", encoding="utf-8")
        stub = Recorder()
        status, body = self.run_phase("Fase 8", stub)
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertIn("build_manuscript.py ended with code 0", body["message"])
        self.assertEqual(stub.calls[0][0][1], str(script))
        self.assertEqual(stub.calls[0][1]["timeout"], 20)

    def test_a_second_paper_job_is_refused_while_one_runs(self) -> None:
        started, release = threading.Event(), threading.Event()

        def slow(argv, **kwargs):
            started.set()
            release.wait(5)
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

        async def both():
            first = asyncio.create_task(self.endpoint(Req({"phase_id": "Fase 10"})))
            await asyncio.to_thread(started.wait, 5)
            try:
                second = await self.endpoint(Req({"phase_id": "Fase 10"}))
            finally:
                release.set()
            return await first, second

        with mock.patch.object(server.subprocess, "run", slow):
            first, second = asyncio.run(both())
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 409)
        self.assertFalse(json.loads(bytes(second.body))["ok"])


if __name__ == "__main__":
    unittest.main()
