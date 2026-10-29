"""Session chains: a run longer than one continuous session checkpoints,
stops at the deadline and continues in the next session from what the first
one left (odd/tasks/session-chains.md).

S2 -- the runner's carry restore resolves each declared carry path where the
target reads and writes it. Under the runner, a target binds its repository
root to `FORGE_CLONE_ROOT` (`<cwd>/clone`) and writes `<cwd>/clone/<product>/
<path>`; a job that predates that layout wrote `<cwd>/<path>`. The earlier
session's output, mounted for the continuation, mirrors that session's
working directory, so each layout is restored to the same place it was
written, and nothing is moved between them.

Run with: python -m pytest -q tests/test_session_chains.py
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import sys
import tempfile
import types
import unittest
import unittest.mock
from pathlib import Path

from tests.remote_fakes import JOBFOLDER, REPOSITORY_ROOT, _load_or_reuse

RUNNER_INVOKE = _load_or_reuse(
    "remote_execution_runner_invoke",
    REPOSITORY_ROOT / "skills/remote-execution/assets/runner_invoke.py",
)

PRODUCT = "QM-EEG"
COMMIT = "c" * 40


def _tree(root: Path) -> dict[str, str]:
    """Every file under `root`, relative path -> content."""
    if not root.is_dir():
        return {}
    return {
        path.relative_to(root).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(root.rglob("*")) if path.is_file()
    }


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class CarryLayoutTests(unittest.TestCase):
    """S2: `restore_carry` restores the product layout and the working
    layout, each to where the earlier session wrote it."""

    def _invoke(self, base: Path, run_config: dict, target) -> tuple[dict, str]:
        """Run `invoke()` on a callable block whose function is `target`,
        handing it the environment it sees; returns (seen, run log)."""
        seen: dict = {}
        module = types.ModuleType("session_chain_probe")

        def run():
            seen["env"] = dict(os.environ)
            target(seen)

        module.run = run
        buffer = io.StringIO()
        with unittest.mock.patch.dict(sys.modules, {"session_chain_probe": module}), \
                contextlib.redirect_stdout(buffer):
            RUNNER_INVOKE.invoke(
                {**run_config, "run": {"module": "session_chain_probe", "function": "run"}},
                base_dir=base,
            )
        return seen, buffer.getvalue()

    def _config(self, mount: Path, **extra) -> dict:
        return {
            "product": PRODUCT,
            "commit": COMMIT,
            "carryPaths": ["Results/e2/runs"],
            "carry": [{"submissionId": "w1/k", "ref": "w1/k", "mount": str(mount)}],
            **extra,
        }

    def test_the_product_layout_is_restored_under_the_clone_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mount = Path(tmp) / "mount"
            _write(mount / "clone" / PRODUCT / "Results/e2/runs/u1.json", "done-u1")
            _write(mount / "clone" / PRODUCT / "Results/e2/other/x.json", "undeclared")
            _write(mount / "clone" / PRODUCT / "src/m.py", "pinned code")
            before = _tree(mount)
            base = Path(tmp) / "work"
            base.mkdir()

            def target(seen):
                root = Path(os.environ[RUNNER_INVOKE.CLONE_ROOT_ENV])
                seen["runs"] = _tree(root / PRODUCT / "Results/e2/runs")

            seen, log = self._invoke(base, self._config(mount), target)
            self.assertEqual(seen["runs"], {"u1.json": "done-u1"})
            self.assertEqual(seen["env"][RUNNER_INVOKE.CARRY_IN_ENV], str(mount))
            # Only the declared path, only in the layout it was written in.
            self.assertEqual(_tree(base), {
                f"clone/{PRODUCT}/Results/e2/runs/u1.json": "done-u1",
            })
            self.assertEqual(_tree(mount), before, "the mount is never modified")
            self.assertIn(f"restored Results/e2/runs from 'w1/k' into clone/{PRODUCT}/"
                          "Results/e2/runs", log)
            self.assertNotIn("missing", log)

    def test_the_working_layout_of_an_older_job_still_restores(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mount = Path(tmp) / "mount"
            _write(mount / "Results/e2/runs/u1.json", "done-u1")
            before = _tree(mount)
            base = Path(tmp) / "work"
            base.mkdir()

            def target(seen):
                seen["runs"] = _tree(base / "Results/e2/runs")

            seen, log = self._invoke(base, self._config(mount), target)
            self.assertEqual(seen["runs"], {"u1.json": "done-u1"})
            self.assertEqual(_tree(base), {"Results/e2/runs/u1.json": "done-u1"})
            self.assertEqual(_tree(mount), before)
            self.assertIn("restored Results/e2/runs from 'w1/k' into the working "
                          "directory", log)

    def test_a_run_config_without_a_product_restores_the_working_layout(self) -> None:
        """The pre-existing shape (no `product` key, no commit) restores
        exactly as before and logs nothing about the clone."""
        with tempfile.TemporaryDirectory() as tmp:
            mount = Path(tmp) / "mount"
            _write(mount / "Results/checkpoints/ckpt.pt", "epoch-7")
            _write(mount / "clone/X/Results/checkpoints/ckpt.pt", "never read")
            base = Path(tmp) / "work"
            base.mkdir()
            seen, log = self._invoke(base, {
                "carryPaths": ["Results/checkpoints"],
                "carry": [{"submissionId": "s", "ref": "w1/k", "mount": str(mount)}],
            }, lambda seen: None)
            self.assertEqual(_tree(base), {"Results/checkpoints/ckpt.pt": "epoch-7"})
            self.assertEqual(log, "[carry] restored Results/checkpoints from 'w1/k' "
                                  "into the working directory\n")

    def test_both_layouts_present_are_each_restored_in_place(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mount = Path(tmp) / "mount"
            _write(mount / "clone" / PRODUCT / "Results/e2/runs/u1.json", "product")
            _write(mount / "Results/e2/runs/u2.json", "working")
            base = Path(tmp) / "work"
            base.mkdir()
            _, log = self._invoke(base, self._config(mount), lambda seen: None)
            self.assertEqual(_tree(base), {
                f"clone/{PRODUCT}/Results/e2/runs/u1.json": "product",
                "Results/e2/runs/u2.json": "working",
            })
            self.assertEqual(log.count("[carry] restored"), 2)

    def test_a_path_missing_from_both_layouts_starts_fresh(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mount = Path(tmp) / "mount"
            mount.mkdir()
            base = Path(tmp) / "work"
            base.mkdir()
            seen, log = self._invoke(base, self._config(mount), lambda seen: None)
            self.assertEqual(_tree(base), {})
            self.assertEqual(seen["env"][RUNNER_INVOKE.CARRY_IN_ENV], str(mount))
            self.assertEqual(log, f"[carry] Results/e2/runs is missing from {mount}; "
                                  "it starts fresh\n")

    def test_a_product_that_is_not_one_folder_name_is_never_joined(self) -> None:
        for product in ("../escape", "a/b", "", ".", "..", 7):
            with self.subTest(product=product), tempfile.TemporaryDirectory() as tmp:
                mount = Path(tmp) / "mount"
                _write(mount / "clone/escape/Results/e2/runs/u1.json", "x")
                _write(mount / "Results/e2/runs/u2.json", "working")
                base = Path(tmp) / "work"
                base.mkdir()
                _, log = self._invoke(base, self._config(mount, product=product),
                                      lambda seen: None)
                self.assertEqual(_tree(base), {"Results/e2/runs/u2.json": "working"})
                self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()),
                                 ["mount", "work"])
                self.assertNotIn("clone/", log)

    def test_session_two_reads_the_tree_session_one_wrote(self) -> None:
        """The whole chain through the runner: session 1 finishes `u1`,
        stops at its deadline leaving `partial.json`; its working directory
        is the mount of session 2, which finds `u1` done under the same
        product path and runs only `u2`."""
        units = ["u1", "u2"]

        def target(seen):
            root = Path(os.environ[RUNNER_INVOKE.CLONE_ROOT_ENV]) / PRODUCT
            runs = root / "Results/e2/runs"
            runs.mkdir(parents=True, exist_ok=True)
            todo = [u for u in json.loads(os.environ[RUNNER_INVOKE.UNITS_ENV])
                    if not (runs / f"{u}.json").is_file()]
            seen["ran"] = todo[:1]
            for unit in todo[:1]:
                (runs / f"{unit}.json").write_text(f"done-{unit}", encoding="utf-8")
            left = todo[1:]
            if left:
                Path("partial.json").write_text(json.dumps({"remaining": left}),
                                                encoding="utf-8")

        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "session-1"
            first.mkdir()
            previous = Path.cwd()
            os.chdir(first)
            try:
                seen1, _ = self._invoke(first, {"product": PRODUCT, "commit": COMMIT,
                                                "units": units,
                                                "carryPaths": ["Results/e2/runs"]}, target)
            finally:
                os.chdir(previous)
            self.assertEqual(seen1["ran"], ["u1"])
            self.assertEqual(json.loads((first / "partial.json").read_text()),
                             {"remaining": ["u2"]})
            second = Path(tmp) / "session-2"
            second.mkdir()
            os.chdir(second)
            try:
                seen2, _ = self._invoke(second, {
                    "product": PRODUCT, "commit": COMMIT, "units": ["u2"],
                    "carryPaths": ["Results/e2/runs"],
                    "carry": [{"submissionId": "s1", "ref": "w1/k", "mount": str(first)}],
                }, target)
            finally:
                os.chdir(previous)
            self.assertEqual(seen2["ran"], ["u2"])
            self.assertEqual(_tree(second / "clone" / PRODUCT / "Results/e2/runs"),
                             {"u1.json": "done-u1", "u2.json": "done-u2"})
            self.assertFalse((second / "partial.json").exists())


class RunConfigWithoutCarryTests(unittest.TestCase):
    """A job that declares no carry is generated byte for byte as before."""

    def test_a_job_without_carry_writes_the_same_run_config_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            asset = Path(tmp) / "asset.py"
            asset.write_text("# asset\n", encoding="utf-8")
            digest = hashlib.sha256(b"# asset\n").hexdigest()
            run_config = JOBFOLDER.build_run_config(
                product="FEM-TOLLA", service="svc", job_name="job",
                commit="a" * 40, repo_url="https://example.invalid/r.git",
                repo_ref="main", clone_paths=["FEM-TOLLA/src"],
                run_module="pkg.mod", run_function="main", run_kwargs={"n": 3},
                bootstrap_asset=asset, invoke_asset=asset,
            )
        expected = (
            '{\n'
            '  "clonePaths": [\n'
            '    "FEM-TOLLA/src"\n'
            '  ],\n'
            '  "commit": "' + "a" * 40 + '",\n'
            '  "jobName": "job",\n'
            '  "product": "FEM-TOLLA",\n'
            '  "repo": {\n'
            '    "ref": "main",\n'
            '    "url": "https://example.invalid/r.git"\n'
            '  },\n'
            '  "run": {\n'
            '    "function": "main",\n'
            '    "kwargs": {\n'
            '      "n": 3\n'
            '    },\n'
            '    "module": "pkg.mod"\n'
            '  },\n'
            '  "runnerTemplate": [\n'
            '    {\n'
            '      "path": "assets/runner_bootstrap.py",\n'
            '      "sha256": "' + digest + '"\n'
            '    },\n'
            '    {\n'
            '      "path": "assets/runner_invoke.py",\n'
            '      "sha256": "' + digest + '"\n'
            '    }\n'
            '  ],\n'
            '  "schemaVersion": ' + json.dumps(JOBFOLDER.RUN_CONFIG_SCHEMA_VERSION) + ',\n'
            '  "service": "svc"\n'
            '}'
        )
        self.assertEqual(json.dumps(run_config, sort_keys=True, indent=2), expected)


class CarryLayoutDocTests(unittest.TestCase):
    def test_the_skill_states_the_resolution_rule(self) -> None:
        skill = (REPOSITORY_ROOT / "skills/remote-execution/SKILL.md").read_text(
            encoding="utf-8")
        self.assertIn("clone/<product>/<path>", skill)
        self.assertIn("into the working directory", skill)
        changelog = (REPOSITORY_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        unreleased = changelog.split("## Unreleased", 1)[1].split("\n## ", 1)[0]
        self.assertIn("clone/<product>/<path>", unreleased)


if __name__ == "__main__":
    unittest.main()
