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

from tests.remote_fakes import (  # noqa: F401
    JOBFOLDER, REMOTE_CLI, REPOSITORY_ROOT, SERVICE, PreflightCase, _git, _load_or_reuse,
)

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

    # -- F1: a symbolic link is never followed out of the mount or the clone --

    def test_a_link_inside_a_carried_tree_is_never_followed(self) -> None:
        """A file link and a directory link under a declared path in the
        mount point outside it: both are skipped with a stated reason, the
        regular files beside them are restored, and nothing outside the
        working directory is read into it or written."""
        with tempfile.TemporaryDirectory() as tmp:
            outside = Path(tmp) / "outside"
            _write(outside / "secret.txt", "secret")
            _write(outside / "tree/deep.txt", "deep secret")
            mount = Path(tmp) / "mount"
            runs = mount / "clone" / PRODUCT / "Results/e2/runs"
            _write(runs / "u1.json", "done-u1")
            (runs / "leak.json").symlink_to(outside / "secret.txt")
            (runs / "leakdir").symlink_to(outside / "tree", target_is_directory=True)
            outside_before = _tree(outside)
            base = Path(tmp) / "work"
            base.mkdir()
            _, log = self._invoke(base, self._config(mount), lambda seen: None)
            self.assertEqual(_tree(base), {
                f"clone/{PRODUCT}/Results/e2/runs/u1.json": "done-u1",
            })
            self.assertEqual([p for p in base.rglob("*") if p.is_symlink()], [])
            self.assertEqual(_tree(outside), outside_before)
            self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()),
                             ["mount", "outside", "work"])
            self.assertEqual(log, (
                f"[carry] skipped clone/{PRODUCT}/Results/e2/runs/leakdir from 'w1/k': "
                "a symbolic link in the mount is never followed\n"
                f"[carry] skipped clone/{PRODUCT}/Results/e2/runs/leak.json from 'w1/k': "
                "a symbolic link in the mount is never followed\n"
                f"[carry] restored Results/e2/runs from 'w1/k' into clone/{PRODUCT}/"
                "Results/e2/runs\n"))

    def test_a_declared_path_that_is_a_link_in_the_mount_is_skipped(self) -> None:
        for linked in (f"clone/{PRODUCT}/Results/e2/runs", f"clone/{PRODUCT}/Results",
                       "Results/e2/runs"):
            with self.subTest(linked=linked), tempfile.TemporaryDirectory() as tmp:
                outside = Path(tmp) / "outside"
                _write(outside / "e2/runs/u1.json", "foreign")
                _write(outside / "u1.json", "foreign")
                outside_before = _tree(outside)
                mount = Path(tmp) / "mount"
                link = mount / linked
                link.parent.mkdir(parents=True)
                link.symlink_to(outside, target_is_directory=True)
                base = Path(tmp) / "work"
                base.mkdir()
                _, log = self._invoke(base, self._config(mount), lambda seen: None)
                self.assertEqual(_tree(base), {})
                self.assertEqual(_tree(outside), outside_before)
                self.assertEqual(log, (
                    f"[carry] skipped carry path Results/e2/runs from 'w1/k': {linked} "
                    "is a symbolic link in the mount; it is never followed\n"
                    f"[carry] Results/e2/runs was not restored from {mount}; it starts "
                    "fresh\n"))

    def test_a_destination_link_in_the_clone_is_never_written_through(self) -> None:
        """The working directory already holds a link where a carried path
        lands (a cloned repository can): nothing is written through it."""
        for linked in (f"clone/{PRODUCT}/Results/e2/runs", f"clone/{PRODUCT}/Results",
                       f"clone/{PRODUCT}/Results/e2/runs/u1.json"):
            with self.subTest(linked=linked), tempfile.TemporaryDirectory() as tmp:
                outside = Path(tmp) / "outside"
                outside.mkdir()
                (outside / "u1.json").write_text("theirs", encoding="utf-8")
                mount = Path(tmp) / "mount"
                _write(mount / "clone" / PRODUCT / "Results/e2/runs/u1.json", "done-u1")
                base = Path(tmp) / "work"
                link = base / linked
                link.parent.mkdir(parents=True)
                link.symlink_to(outside / "u1.json" if linked.endswith(".json") else outside,
                                target_is_directory=not linked.endswith(".json"))
                _, log = self._invoke(base, self._config(mount), lambda seen: None)
                self.assertEqual(_tree(outside), {"u1.json": "theirs"})
                self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()),
                                 ["mount", "outside", "work"])
                # A linked directory refuses its whole tree; a linked file, itself.
                refused = (f"clone/{PRODUCT}/Results/e2/runs/u1.json"
                           if linked.endswith(".json") else f"clone/{PRODUCT}/Results/e2/runs")
                self.assertEqual(log, (
                    f"[carry] skipped {refused} from 'w1/k': its destination resolves "
                    "outside the working directory\n"
                    f"[carry] Results/e2/runs was not restored from {mount}; it starts "
                    "fresh\n"))

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



def _shipped_changelog_section(changelog: str) -> str:
    """The section of the release that shipped session chains, pinned by its
    own heading so a later `## Unreleased` does not move it."""
    return changelog.split("\n## 0.39.0\n", 1)[1].split("\n## ", 1)[0]


class CarryLayoutDocTests(unittest.TestCase):
    def test_the_skill_states_the_resolution_rule(self) -> None:
        skill = (REPOSITORY_ROOT / "skills/remote-execution/SKILL.md").read_text(
            encoding="utf-8")
        self.assertIn("clone/<product>/<path>", skill)
        self.assertIn("into the working directory", skill)
        changelog = (REPOSITORY_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        shipped = _shipped_changelog_section(changelog)
        self.assertIn("clone/<product>/<path>", shipped)



# ---------------------------------------------------------------------------
# S1: the deadline rehearsal in preflight
# ---------------------------------------------------------------------------

#: Appended to the fake target's `pkg/mod.py`: a smoke that runs the units
#: `FORGE_RUN_UNITS` hands it, skips the ones whose record is already on disk,
#: and stops at `FORGE_SESSION_DEADLINE` leaving `partial.json`. Its kwargs
#: select the defects the deadline rehearsal must catch.
CHAIN_SOURCE = """

def smoke_chain(**kwargs):
    units = json.loads(os.environ.get("FORGE_RUN_UNITS", '["solo"]'))
    deadline = float(os.environ.get("FORGE_SESSION_DEADLINE", "inf"))
    if kwargs.get("layout", "product") == "product":
        root = Path(os.environ["FORGE_CLONE_ROOT"]) / "P"
    else:
        root = Path(".")
    runs = root / kwargs.get("records", "Results/runs")
    runs.mkdir(parents=True, exist_ok=True)
    todo = [u for u in units if not (runs / (u + ".json")).is_file()]
    ran = []
    for index, unit in enumerate(todo):
        if not kwargs.get("ignore") and time.time() >= deadline:
            left = todo[index:]
            if kwargs.get("ids") == "renamed":
                left = ["unit-" + u for u in left]
            marker = Path(kwargs.get("marker", "partial.json"))
            if kwargs.get("marker") == "in-carry":
                marker = runs / "partial.json"
            marker.write_text(json.dumps({"remaining": left}), encoding="utf-8")
            break
        time.sleep(float(kwargs.get("unitSeconds", 0)))
        (runs / (unit + ".json")).write_text("done-" + unit, encoding="utf-8")
        ran.append(unit)
    else:
        if kwargs.get("markEmpty"):
            Path("partial.json").write_text(json.dumps({"remaining": []}), encoding="utf-8")
    Path("ran.json").write_text(json.dumps({
        "units": units, "ran": ran, "seenDone": [u for u in units if u not in todo],
        "mode": os.environ.get("FORGE_RUN_MODE"),
    }), encoding="utf-8")
    Path("shard.json").write_text(json.dumps({"evidence": {"commit": _commit()}}),
                                  encoding="utf-8")
"""

UNIT_ARGS = ("--unit", "u1", "--unit", "u2", "--unit", "u3")
#: Longer than the rehearsal's deadline window, so a target that honours the
#: deadline finishes at most one unit before it stops.
UNIT_SECONDS = 1.1


class DeadlineRehearsalCase(PreflightCase):
    def setUp(self) -> None:
        super().setUp()
        module = self.target / "src" / "pkg" / "mod.py"
        module.write_text(module.read_text(encoding="utf-8") + CHAIN_SOURCE, encoding="utf-8")
        _git(self.target, "add", "-A")
        _git(self.target, "commit", "-q", "-m", "chain smoke")
        self.commit = _git(self.target, "rev-parse", "HEAD")

    def chain_job(self, carry=("Results/runs",), **smoke_kwargs) -> Path:
        return self.generate(smoke="smoke_chain", carry_paths=list(carry) or None,
                             smoke_kwargs={"unitSeconds": UNIT_SECONDS, **smoke_kwargs})

    def timing(self, seconds_per_epoch: float) -> None:
        path = self.target / "P" / "Results" / "timing.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "schema": 1,
            "measurements": [{"measuredAt": "2026-10-28T00:00:00Z", "host": f"{SERVICE}:w1",
                              "device": "cuda:GPU-X", "arm": "a", "unit": "epoch",
                              "secondsPerUnit": seconds_per_epoch, "unitsMeasured": 1}],
            "scales": {"poc": {"arms": 1, "folds": 1, "seeds": 1, "epochs": 1},
                       "full": {"arms": 2, "folds": 5, "seeds": 1, "epochs": 10}},
        }), encoding="utf-8")

    def target_files(self) -> dict[str, bytes]:
        return {p.relative_to(self.target).as_posix(): p.read_bytes()
                for p in sorted(self.target.rglob("*"))
                if p.is_file() and ".git" not in p.relative_to(self.target).parts}

    @staticmethod
    def kept_session(keep: Path, index: int) -> Path:
        return keep / "deadline" / f"session-{index}"


class DeadlineRehearsalPassTests(DeadlineRehearsalCase):
    def test_a_target_that_stops_and_resumes_passes(self) -> None:
        job = self.chain_job()
        before = self.target_files()
        keep = self.root / "kept"
        code, payload, err = self.preflight(job, *UNIT_ARGS, "--keep-rehearsal", str(keep))
        row = self.row(payload, "deadline-rehearsal")
        self.assertEqual(row["status"], "pass", row)
        self.assertEqual(code, 0, (payload, err))
        remaining = row["details"]["remaining"]
        self.assertTrue(set(remaining) <= {"u1", "u2", "u3"} and remaining, row)
        self.assertEqual(row["details"]["units"], ["u1", "u2", "u3"])
        self.assertEqual(row["details"]["carried"], ["clone/P/Results/runs"])
        self.assertIn("partial.json", row["evidence"])
        # Session 1 ran under the runner with every unit and stopped early.
        first = json.loads((self.kept_session(keep, 1) / "ran.json").read_text())
        self.assertEqual(first["units"], ["u1", "u2", "u3"])
        self.assertEqual(first["mode"], "smoke")
        self.assertEqual(first["ran"] + remaining, ["u1", "u2", "u3"])
        # Session 2 got only the remaining ids, found the rest done under the
        # same product path, and ran only what was left.
        second = json.loads((self.kept_session(keep, 2) / "ran.json").read_text())
        self.assertEqual(second["units"], remaining)
        self.assertEqual(second["ran"], remaining)
        self.assertEqual(second["seenDone"], [])
        self.assertEqual(
            sorted(p.name for p in (self.kept_session(keep, 2) / "clone/P/Results/runs")
                   .iterdir()), ["u1.json", "u2.json", "u3.json"])
        self.assertFalse((self.kept_session(keep, 2) / "partial.json").exists())
        self.assertEqual(self.target_files(), before, "preflight writes nothing in the target")

    def test_a_working_directory_layout_also_resumes(self) -> None:
        job = self.chain_job(layout="working")
        _, payload, _ = self.preflight(job, *UNIT_ARGS)
        row = self.row(payload, "deadline-rehearsal")
        self.assertEqual(row["status"], "pass", row)
        self.assertEqual(row["details"]["carried"], ["Results/runs"])

    def test_carry_with_a_passing_rehearsal_lets_a_long_unit_pass_session_fit(self) -> None:
        self.timing(120.0)  # 100 epochs x 120 s = 200 min > 80% of 2 h
        job = self.chain_job()
        _, payload, _ = self.preflight(job, *UNIT_ARGS)
        deadline = self.row(payload, "deadline-rehearsal")
        self.assertEqual(deadline["status"], "pass")
        self.assertFalse(deadline["details"]["kept"])
        self.assertFalse(Path(deadline["details"]["scratch"]).exists())
        row = self.row(payload, "session-fit")
        self.assertEqual(row["status"], "pass", row)
        self.assertIn("deadline rehearsal", row["evidence"])


class DeadlineRehearsalFailTests(DeadlineRehearsalCase):
    def test_a_target_that_ignores_the_deadline_fails_both_rows(self) -> None:
        self.timing(120.0)
        job = self.chain_job(ignore=True)
        code, payload, _ = self.preflight(job, *UNIT_ARGS)
        row = self.row(payload, "deadline-rehearsal")
        self.assertEqual(row["status"], "fail")
        self.assertIn("no partial.json", row["evidence"])
        self.assertIn("FORGE_SESSION_DEADLINE", row["fix"])
        fit = self.row(payload, "session-fit")
        self.assertEqual(fit["status"], "fail")
        self.assertIn("deadline rehearsal", fit["evidence"])
        self.assertNotEqual(code, 0)

    def test_marker_ids_that_are_not_the_submitted_units_fail(self) -> None:
        job = self.chain_job(ids="renamed")
        _, payload, _ = self.preflight(job, *UNIT_ARGS)
        row = self.row(payload, "deadline-rehearsal")
        self.assertEqual(row["status"], "fail")
        self.assertIn("unit-u", row["evidence"])
        self.assertIn("equal the submitted unit strings", row["fix"])

    def test_a_marker_inside_a_carry_path_fails(self) -> None:
        job = self.chain_job(marker="in-carry")
        _, payload, _ = self.preflight(job, *UNIT_ARGS)
        row = self.row(payload, "deadline-rehearsal")
        self.assertEqual(row["status"], "fail")
        self.assertIn("inside the declared carry path", row["evidence"])

    def test_records_outside_every_carry_path_fail(self) -> None:
        job = self.chain_job(carry=("checkpoints",))
        _, payload, _ = self.preflight(job, *UNIT_ARGS)
        row = self.row(payload, "deadline-rehearsal")
        self.assertEqual(row["status"], "fail")
        self.assertIn("checkpoints", row["evidence"])
        self.assertIn("start fresh", row["evidence"])

    def test_a_session_over_its_budget_fails_and_leaves_no_scratch(self) -> None:
        local = REMOTE_CLI._load_sibling("remote_execution_local_rehearsal",
                                         "local_rehearsal.py")
        job = self.chain_job(ignore=True, unitSeconds=5)
        run_config = json.loads((job / "run-config.json").read_text())
        result = local.deadline_rehearse(
            job_dir=job, target=self.target, run_config=run_config,
            interpreter=Path(sys.executable), units=["u1", "u2", "u3"],
            partial_marker=REMOTE_CLI.SHARD_IO.partial_marker, timeout=2)
        self.assertEqual(result["status"], "fail")
        self.assertIn("did not stop", result["evidence"])
        self.assertFalse(result["details"]["kept"])
        self.assertFalse(Path(result["details"]["scratch"]).exists())


class DeadlineRehearsalTriggerTests(DeadlineRehearsalCase):
    def test_skipping_the_rehearsal_warns_and_session_fit_warns(self) -> None:
        self.timing(120.0)
        job = self.chain_job()
        _, payload, _ = self.preflight(job, "--skip-rehearsal", *UNIT_ARGS)
        self.assertEqual(self.row(payload, "deadline-rehearsal")["status"], "warn")
        fit = self.row(payload, "session-fit")
        self.assertEqual(fit["status"], "warn")
        self.assertIn("the deadline rehearsal was skipped (--skip-rehearsal), so resuming "
                      "from a checkpoint is unproven", fit["evidence"])

    def test_a_rehearsal_that_never_stopped_early_is_quoted_not_called_skipped(self) -> None:
        """F3: session 1 finished every unit before its deadline, so the
        row warns; `session-fit` quotes that evidence instead of saying the
        rehearsal was skipped."""
        self.timing(120.0)
        job = self.chain_job(unitSeconds=0, markEmpty=True)
        _, payload, _ = self.preflight(job, *UNIT_ARGS)
        row = self.row(payload, "deadline-rehearsal")
        self.assertEqual(row["status"], "warn", row)
        evidence = ("session 1 finished every unit before its deadline and left an empty "
                    "partial.json; stopping early was not exercised")
        self.assertEqual(row["evidence"], evidence)
        fit = self.row(payload, "session-fit")
        self.assertEqual(fit["status"], "warn", fit)
        self.assertNotIn("skipped", fit["evidence"])
        self.assertTrue(fit["evidence"].endswith(
            "declares carry paths (Results/runs), but the deadline rehearsal did not "
            f"exercise a stop: {evidence}"), fit)
        self.assertEqual(fit["fix"], row["fix"])
        self.assertEqual(fit["fix"], "rehearse more units (--unit) or a slower "
                                     "--local-smoke-kwargs")

    def test_without_unit_ids_the_rehearsal_is_skipped_naming_the_flag(self) -> None:
        self.timing(120.0)
        job = self.chain_job()
        _, payload, _ = self.preflight(job)
        row = self.row(payload, "deadline-rehearsal")
        self.assertEqual(row["status"], "warn")
        self.assertIn("--unit", row["fix"])
        self.assertEqual(self.row(payload, "session-fit")["status"], "warn")

    def test_a_job_that_fits_one_session_and_carries_nothing_has_no_row(self) -> None:
        self.timing(1.0)  # 100 s for the whole stage
        job = self.chain_job(carry=())
        code, payload, _ = self.preflight(job, *UNIT_ARGS)
        self.assertEqual(self.rows(payload, "deadline-rehearsal"), [])
        self.assertEqual(self.row(payload, "session-fit")["status"], "pass")
        self.assertEqual(code, 0, payload)

    def test_a_session_over_the_margin_requires_it_even_when_units_fit(self) -> None:
        self.timing(120.0)  # 10 units of 20 min fit; 200 min in one session do not
        job = self.chain_job(carry=())
        _, payload, _ = self.preflight(job, "--units", "10", *UNIT_ARGS)
        self.assertEqual(self.row(payload, "deadline-rehearsal")["status"], "pass")
        self.assertEqual(self.row(payload, "session-fit")["status"], "pass")

    def test_the_preflight_parser_declares_unit_and_deadline_block(self) -> None:
        parser = REMOTE_CLI._build_parser()
        args = parser.parse_args(["preflight", "--target", "/t", "--entrypoint", "/t/a.ipynb",
                                  "--unit", "u1", "--unit", "u2"])
        self.assertEqual(args.unit_ids, ["u1", "u2"])
        self.assertEqual(args.deadline_block, "smoke")
        args = parser.parse_args(["preflight", "--target", "/t", "--entrypoint", "/t/a.ipynb",
                                  "--deadline-block", "run"])
        self.assertEqual(args.deadline_block, "run")
        self.assertIsNone(args.unit_ids)


class DeadlineRehearsalDocTests(unittest.TestCase):
    def test_the_skill_documents_the_deadline_rehearsal(self) -> None:
        skill = (REPOSITORY_ROOT / "skills/remote-execution/SKILL.md").read_text(
            encoding="utf-8")
        for needle in ("`deadline-rehearsal`", "--deadline-block", "[--unit <id>]...",
                       "warns when the deadline rehearsal was skipped", "carry: no-share",
                       "a target must write `partial.json` whatever that variable says"):
            self.assertIn(needle, skill)
        changelog = (REPOSITORY_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        shipped = _shipped_changelog_section(changelog)
        for needle in ("deadline-rehearsal", "carry: no-share", "session-fit"):
            self.assertIn(needle, shipped)



class UploadedCarryDocTests(unittest.TestCase):
    """S5: the uploaded continuation and the idle-reclaim rule, each stated
    with what verifies it."""

    def test_the_skill_documents_the_uploaded_carry_and_the_reclaim_rule(self) -> None:
        skill = (REPOSITORY_ROOT / "skills/remote-execution/SKILL.md").read_text(
            encoding="utf-8")
        for needle in ("carry: uploaded", "`CARRY_UPLOAD`", "<session>.carry/<k>/",
                       "test_colab_fetch_stops_session_only_after_terminal_status",
                       "Unverified:", "carry: unsupported"):
            self.assertIn(needle, skill)
        changelog = (REPOSITORY_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        shipped = _shipped_changelog_section(changelog)
        self.assertIn("carry: uploaded", shipped)


if __name__ == "__main__":
    unittest.main()
