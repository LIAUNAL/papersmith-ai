"""The Experiments tab's local-environment table: bounded, offline, cached.

``local_env.local_environment(root)`` reports the workspace micromamba env and
each implementation target's ``.venv``: whether the interpreter is present, its
Python version, the libraries the target declares (``pyproject.toml`` and
``requirements*.txt``, names only) with their installed versions, and the
device torch sees. One subprocess per interpreter runs one fixed inline script;
nothing from the target is ever executed. The interpreters here are fake
executable scripts that print fixed JSON and record how they were called.
"""

from __future__ import annotations

import json
import os
import shlex
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from skills._core.command_center import local_env, terminal


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _fake_python(path: Path, payload: dict | None, log: Path, *, sleep: float = 0.0) -> Path:
    """An executable that appends one line per call to ``log`` and prints ``payload``."""
    body = ["#!/bin/sh", f'echo call >> "{log}"']
    if sleep:
        body.append(f"exec sleep {sleep}")
    if payload is not None:
        body.append(f"printf '%s\\n' {shlex.quote(json.dumps(payload))}")
    else:
        body.append("echo 'not json'")
    exe = _write(path, "\n".join(body) + "\n")
    exe.chmod(0o755)
    return exe


class _Env(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.tmp = Path(holder.name).resolve()
        self.root = self.tmp / "ws"
        self.root.mkdir()
        self.log = self.tmp / "calls.log"
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        patcher = mock.patch.dict(os.environ, {"PATH": str(self.bin)})
        patcher.start()
        self.addCleanup(patcher.stop)
        dirs = mock.patch.object(terminal, "TOOL_DIRS", ())
        dirs.start()
        self.addCleanup(dirs.stop)
        local_env.clear_cache()
        self.addCleanup(local_env.clear_cache)

    def target(self, repo: str = "repo") -> Path:
        target = self.root / "implementations" / repo
        _write(target / "pyproject.toml",
               '[project]\nname = "demo"\ndependencies = [\n  "torch>=2.0",\n'
               '  "numpy[extra] ; python_version>\'3.8\'",\n  "Scikit_Learn==1.5",\n]\n')
        _write(target / "requirements.txt",
               "# comment\npennylane>=0.36\n-r other.txt\n-e .\nnumpy\n\n--index-url https://x\n")
        _write(target / "requirements-dev.txt", "pytest\n")
        return target

    def calls(self) -> list[str]:
        return self.log.read_text(encoding="utf-8").splitlines() if self.log.exists() else []


class RequirementTests(_Env):
    def test_names_come_from_pyproject_and_requirements_files_only(self) -> None:
        target = self.target()
        names = local_env.required_libraries(target)
        self.assertEqual(names["names"], ["numpy", "pennylane", "pytest", "scikit-learn", "torch"])
        self.assertEqual(names["sources"], ["pyproject.toml", "requirements-dev.txt", "requirements.txt"])

    def test_a_malformed_pyproject_never_raises(self) -> None:
        target = self.root / "implementations" / "bad"
        _write(target / "pyproject.toml", "[project\nnot toml")
        _write(target / "requirements.txt", "numpy\n")
        names = local_env.required_libraries(target)
        self.assertEqual(names["names"], ["numpy"])


class EnvironmentTests(_Env):
    def test_workspace_env_and_micromamba_are_reported(self) -> None:
        _fake_python(self.root / ".micromamba/envs/papersmith/bin/python",
                     {"python": "3.12.4", "installed": {}, "device": None}, self.log)
        _fake_python(self.bin / "micromamba", {}, self.tmp / "mm.log")
        env = local_env.local_environment(self.root)
        workspace = env["workspace"]
        self.assertTrue(workspace["present"])
        self.assertEqual(workspace["python"], "3.12.4")
        self.assertEqual(workspace["state"], "ready")
        self.assertEqual(workspace["path"], ".micromamba/envs/papersmith/bin/python")
        self.assertTrue(workspace["micromamba"])
        self.assertEqual(env["targets"], [])

    def test_absent_interpreters_are_reported_missing_without_a_subprocess(self) -> None:
        self.target()
        env = local_env.local_environment(self.root)
        self.assertFalse(env["workspace"]["present"])
        self.assertEqual(env["workspace"]["state"], "missing")
        self.assertIsNone(env["workspace"]["micromamba"])
        [target] = env["targets"]
        self.assertEqual(target["repo"], "repo")
        self.assertFalse(target["present"])
        self.assertEqual(target["state"], "missing")
        self.assertEqual(target["required"], ["numpy", "pennylane", "pytest", "scikit-learn", "torch"])
        self.assertEqual(self.calls(), [])

    def test_installed_versions_missing_libraries_and_device(self) -> None:
        target = self.target()
        _fake_python(target / ".venv/bin/python", {
            "python": "3.11.9",
            "installed": {"numpy": "2.1.0", "pennylane": "0.38.0", "pytest": None,
                          "scikit-learn": "1.5.0", "torch": "2.4.1"},
            "device": {"cuda": False, "mps": True}}, self.log)
        [row] = local_env.local_environment(self.root)["targets"]
        self.assertTrue(row["present"])
        self.assertEqual(row["python"], "3.11.9")
        self.assertEqual(row["state"], "incomplete")
        self.assertEqual(row["missing"], ["pytest"])
        self.assertIn({"name": "torch", "version": "2.4.1"}, row["libraries"])
        self.assertEqual(row["device"], "mps")
        self.assertEqual(row["path"], "implementations/repo/.venv/bin/python")

    def test_all_installed_with_cuda_is_ready(self) -> None:
        target = self.target()
        _fake_python(target / ".venv/bin/python", {
            "python": "3.11.9",
            "installed": {n: "1.0" for n in ("numpy", "pennylane", "pytest", "scikit-learn", "torch")},
            "device": {"cuda": True, "cuda_name": "<b>GPU</b>", "mps": False}}, self.log)
        [row] = local_env.local_environment(self.root)["targets"]
        self.assertEqual(row["state"], "ready")
        self.assertEqual(row["missing"], [])
        self.assertEqual(row["device"], "cuda:<b>GPU</b>")

    def test_no_torch_means_no_device_claim(self) -> None:
        target = self.root / "implementations" / "plain"
        _write(target / "requirements.txt", "numpy\n")
        _fake_python(target / ".venv/bin/python",
                     {"python": "3.11.9", "installed": {"numpy": "2.0"}, "device": None}, self.log)
        [row] = local_env.local_environment(self.root)["targets"]
        self.assertEqual(row["state"], "ready")
        self.assertIsNone(row["device"])

    def test_a_timeout_or_garbage_is_unverified(self) -> None:
        target = self.target()
        _fake_python(target / ".venv/bin/python", None, self.log)
        [row] = local_env.local_environment(self.root)["targets"]
        self.assertEqual(row["state"], "unverified")
        self.assertEqual(row["device"], "unverified")
        local_env.clear_cache()
        _fake_python(target / ".venv/bin/python", {"python": "3.11"}, self.log, sleep=3)
        with mock.patch.object(local_env, "PROBE_TIMEOUT", 0.3):
            started = time.monotonic()
            [row] = local_env.local_environment(self.root)["targets"]
        self.assertLess(time.monotonic() - started, 2.5)
        self.assertEqual(row["state"], "unverified")
        self.assertIn("unverified", row["detail"])

    def test_the_probe_is_cached_and_reprobed_when_the_interpreter_changes(self) -> None:
        target = self.target()
        exe = _fake_python(target / ".venv/bin/python",
                           {"python": "3.11.9", "installed": {}, "device": None}, self.log)
        local_env.local_environment(self.root)
        local_env.local_environment(self.root)
        self.assertEqual(len(self.calls()), 1)
        stamp = exe.stat().st_mtime + 10
        os.utime(exe, (stamp, stamp))
        local_env.local_environment(self.root)
        self.assertEqual(len(self.calls()), 2)
        # Past the TTL the cached answer is served at once and one background
        # probe replaces it.
        with mock.patch.object(local_env.time, "monotonic", return_value=time.monotonic() + 400):
            [row] = local_env.local_environment(self.root)["targets"]
            self.assertEqual(row["python"], "3.11.9")
            deadline = time.time() + 5
            while len(self.calls()) < 3 and time.time() < deadline:
                time.sleep(0.05)
        self.assertEqual(len(self.calls()), 3)

    def test_an_expired_probe_never_blocks_the_request(self) -> None:
        target = self.target()
        exe = _fake_python(target / ".venv/bin/python",
                           {"python": "3.11.9", "installed": {}, "device": None}, self.log)
        local_env.local_environment(self.root)
        stamp = exe.stat().st_mtime
        # The interpreter turns slow, under the same identity (same mtime).
        _fake_python(exe, None, self.log, sleep=1)
        os.utime(exe, (stamp, stamp))
        with mock.patch.object(local_env.time, "monotonic", return_value=time.monotonic() + 400):
            started = time.monotonic()
            [row] = local_env.local_environment(self.root)["targets"]
            elapsed = time.monotonic() - started
        self.assertLess(elapsed, 0.5)
        self.assertEqual(row["python"], "3.11.9")

    def test_only_the_fixed_inline_script_runs_isolated_outside_the_target(self) -> None:
        target = self.target()
        marker = self.tmp / "target-code-ran"
        _write(target / "sitecustomize.py", f"open({str(marker)!r}, 'w').write('x')\n")
        _write(target / "setup.py", f"open({str(marker)!r}, 'w').write('x')\n")
        _fake_python(target / ".venv/bin/python",
                     {"python": "3.11.9", "installed": {}, "device": None}, self.log)
        with mock.patch.object(local_env.subprocess, "run", wraps=local_env.subprocess.run) as run:
            local_env.local_environment(self.root)
        self.assertEqual(run.call_count, 1)
        argv = run.call_args.args[0]
        self.assertEqual(argv[1:4], ["-I", "-c", local_env.PROBE_SCRIPT])
        self.assertEqual(json.loads(argv[4]), ["numpy", "pennylane", "pytest", "scikit-learn", "torch"])
        self.assertEqual(argv[5], "1")
        cwd = Path(run.call_args.kwargs["cwd"]).resolve()
        self.assertNotIn(self.root, (cwd, *cwd.parents))
        self.assertEqual(run.call_args.kwargs["timeout"], local_env.PROBE_TIMEOUT)
        self.assertFalse(marker.exists())

    def test_the_real_probe_script_reads_metadata_in_this_interpreter(self) -> None:
        import subprocess
        import sys
        done = subprocess.run([sys.executable, "-I", "-c", local_env.PROBE_SCRIPT,
                               json.dumps(["pip", "surely-not-installed-xyz"]), "0"],
                              capture_output=True, text=True, timeout=30, check=True)
        out = json.loads(done.stdout)
        self.assertIsNone(out["installed"]["surely-not-installed-xyz"])
        self.assertIsNone(out["device"])
        self.assertTrue(out["python"].startswith(f"{sys.version_info.major}."))

    def test_never_raises_on_an_unreadable_root(self) -> None:
        env = local_env.local_environment(self.tmp / "does-not-exist")
        self.assertEqual(env["targets"], [])
        self.assertEqual(env["workspace"]["state"], "missing")


if __name__ == "__main__":
    unittest.main()
