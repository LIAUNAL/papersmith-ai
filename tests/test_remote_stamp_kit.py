"""The scaffold ships remote readiness by default (poc-launch-smoothing, S4).

Every new target gets two kit files from `materialize --stage scaffold`:

- `src/<Package>/remote_stamp.py`, whose `write_shard` writes the `shard.json`
  a remote smoke is recorded from -- only under the runner (`FORGE_RUN_MODE`),
  carrying the commit, the source digest and the device;
- `tests/test_remote_readiness.py`, which tests that stamp and carries a
  device-mix guard plus a placeholder test the target wires to its forward.

These tests examine a target scaffolded by `scripts/materialize.py`, the
forge's harness over the identical destination list the engine writes.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

FORGE = Path(__file__).resolve().parents[1]
SKILL = FORGE / "skills" / "proposal-implementation"
MATERIALIZE = SKILL / "scripts" / "materialize.py"
KIT = SKILL / "assets" / "kit"

sys.path.insert(0, str(FORGE / "skills" / "_core" / "implementation" / "engine"))
from domain_profile import seeded_profile  # noqa: E402  (path set above)
# Seeded for the import only, never left in `os.environ`: a profile variable
# that outlives this module steers every later launcher in the same worker.
with seeded_profile(SKILL / "impl_profile.py"):
    import implementation_engine as impl  # noqa: E402

NAME = "Example-Method"
PACKAGE = "Example_Method"
STAMP = f"src/{PACKAGE}/remote_stamp.py"
READINESS = "tests/test_remote_readiness.py"

#: The scaffold destinations as they stood before S4, in order. Their
#: materialized bytes must not move.
PRE_S4_DESTINATIONS = [
    f"src/{PACKAGE}/__init__.py",
    f"src/{PACKAGE}/report_digest.py",
    "tests/test_smoke.py",
    "tests/findings.py", "tests/conftest.py", "tests/sweep.py",
    "tests/admissibility.py",
    "tests/test_audit.py", "tests/test_remedies.py",
    f"{NAME}/Notebooks/verification.ipynb",
]


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True,
        text=True,
        env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
             "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"},
    ).stdout.strip()


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ScaffoldedTarget(unittest.TestCase):
    """One freshly materialized, committed target per test class."""

    @classmethod
    def setUpClass(cls):
        cls._box = tempfile.TemporaryDirectory()
        cls.root = Path(cls._box.name) / "target"
        cls.root.mkdir()
        _git(cls.root, "init", "-q")
        subprocess.run([sys.executable, str(MATERIALIZE), str(cls.root), NAME, "7"],
                       check=True, capture_output=True, text=True)
        _git(cls.root, "add", "-A")
        _git(cls.root, "commit", "-q", "-m", "scaffold")

    @classmethod
    def tearDownClass(cls):
        cls._box.cleanup()


class ScaffoldShipsRemoteReadinessTests(ScaffoldedTarget):
    def test_scaffold_destinations_name_both_files(self):
        destinations = impl.scaffold_destinations(NAME)
        self.assertIn(STAMP, destinations)
        self.assertIn(READINESS, destinations)
        self.assertEqual(impl.scaffold_kit_source(STAMP, NAME),
                         KIT / "nb" / "remote_stamp.py")
        self.assertEqual(impl.scaffold_kit_source(READINESS, NAME),
                         KIT / "tests" / "test_remote_readiness.py")

    def test_materialize_writes_both_files_into_a_fresh_target(self):
        self.assertTrue((self.root / STAMP).is_file())
        readiness = (self.root / READINESS).read_text(encoding="utf-8")
        self.assertNotIn("{{", readiness)
        self.assertIn(f'"{PACKAGE}"', readiness)

    def test_the_stamp_owes_no_provenance(self):
        self.assertIn(STAMP, impl.kit_owned_package_files(NAME))

    def test_existing_kit_destinations_are_unchanged(self):
        destinations = impl.scaffold_destinations(NAME)
        self.assertEqual(
            [d for d in destinations if d not in (STAMP, READINESS)],
            PRE_S4_DESTINATIONS)
        for destination in PRE_S4_DESTINATIONS[1:]:
            source = impl.scaffold_kit_source(destination, NAME)
            expected = impl.scaffold_substitute_body(
                source.read_text(encoding="utf-8"), NAME, "7")
            self.assertEqual(
                (self.root / destination).read_text(encoding="utf-8"), expected,
                destination)
        self.assertEqual(
            (self.root / PRE_S4_DESTINATIONS[0]).read_text(),
            impl.authored_package_init(NAME))


class WriteShardTests(ScaffoldedTarget):
    def setUp(self):
        sys.path.insert(0, str(self.root / "src"))
        self.addCleanup(sys.path.remove, str(self.root / "src"))
        for name in [m for m in sys.modules if m.startswith(PACKAGE)]:
            del sys.modules[name]
        import importlib
        self.stamp = importlib.import_module(f"{PACKAGE}.remote_stamp")
        self.out = Path(tempfile.mkdtemp())
        saved = os.environ.pop("FORGE_RUN_MODE", None)
        if saved is not None:
            self.addCleanup(os.environ.__setitem__, "FORGE_RUN_MODE", saved)

    def tearDown(self):
        os.environ.pop("FORGE_RUN_MODE", None)

    def test_writes_nothing_without_the_run_mode(self):
        self.assertIsNone(self.stamp.write_shard({"units": 1}, self.out))
        self.assertEqual(list(self.out.iterdir()), [])

    def test_writes_into_the_working_directory_by_default(self):
        os.environ["FORGE_RUN_MODE"] = "smoke"
        before = Path.cwd()
        os.chdir(self.out)
        try:
            path = self.stamp.write_shard({"units": 1})
        finally:
            os.chdir(before)
        self.assertEqual(path.resolve(), (self.out / "shard.json").resolve())

    def test_carries_the_declared_fields_under_the_run_mode(self):
        os.environ["FORGE_RUN_MODE"] = "smoke"
        path = self.stamp.write_shard({"units": 1}, self.out, device="cpu")
        self.assertEqual(path, self.out / "shard.json")
        shard = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(shard["mode"], "smoke")
        self.assertEqual(shard["runs"], {"units": 1})
        commit = shard["evidence"]["commit"]
        self.assertRegex(commit, r"^[0-9a-f]{40}$")
        self.assertEqual(commit, _git(self.root, "rev-parse", "HEAD"))
        digest = _load(self.root / "src" / PACKAGE / "report_digest.py",
                       "seal_under_test").source_digest(self.root, PACKAGE)
        self.assertEqual(shard["evidence"]["sourcesDigest"], digest)
        self.assertEqual(shard["environment"]["device"]["kind"], "cpu")
        self.assertTrue(shard["environment"]["device"]["name"])

    def test_meets_the_smoke_record_required_evidence(self):
        os.environ["FORGE_RUN_MODE"] = "smoke"
        shard = json.loads(self.stamp.write_shard({}, self.out).read_text())
        shard_io = _load(FORGE / "skills" / "remote-execution" / "scripts"
                         / "shard_io.py", "shard_io_under_test")
        report = shard_io.completeness(
            shard, ["evidence.commit", "environment.device.kind"])
        self.assertEqual(report.get("missing"), [], report)


class CodeBundleWorkerTests(ScaffoldedTarget):
    """remote-preflight S4/L7: a code-bundle worker holds only `.git/HEAD`,
    so `git rev-parse` fails there and the stamp reads the commit the runner
    exports instead; and the scaffold's smoke template stamps by itself."""

    def setUp(self):
        sys.path.insert(0, str(self.root / "src"))
        self.addCleanup(sys.path.remove, str(self.root / "src"))
        for name in [m for m in sys.modules if m.startswith(PACKAGE)]:
            del sys.modules[name]
        import importlib
        self.stamp = importlib.import_module(f"{PACKAGE}.remote_stamp")
        self.out = Path(tempfile.mkdtemp())
        self.bundled = Path(tempfile.mkdtemp())
        (self.bundled / ".git").mkdir()
        (self.bundled / ".git" / "HEAD").write_text("f" * 40 + "\n", encoding="utf-8")
        self.saved = {k: os.environ.pop(k, None) for k in ("FORGE_RUN_MODE", "FORGE_CLONE_COMMIT")}

    def tearDown(self):
        for key, value in self.saved.items():
            os.environ.pop(key, None)
            if value is not None:
                os.environ[key] = value

    def test_commit_falls_back_to_the_runner_commit_when_git_fails(self):
        os.environ["FORGE_CLONE_COMMIT"] = "a" * 40
        self.assertEqual(self.stamp.commit(self.bundled), "a" * 40)

    def test_git_still_wins_where_it_answers(self):
        os.environ["FORGE_CLONE_COMMIT"] = "a" * 40
        self.assertEqual(self.stamp.commit(self.root), _git(self.root, "rev-parse", "HEAD"))

    def test_no_git_and_no_runner_commit_is_none(self):
        self.assertIsNone(self.stamp.commit(self.bundled))

    def test_the_stamped_smoke_template_writes_shard_json(self):
        @self.stamp.stamped
        def smoke(scale=1):
            return {"scale": scale}

        os.environ["FORGE_RUN_MODE"] = "smoke"
        before = Path.cwd()
        os.chdir(self.out)
        try:
            self.assertEqual(smoke(scale=2), {"scale": 2})
        finally:
            os.chdir(before)
        shard = json.loads((self.out / "shard.json").read_text(encoding="utf-8"))
        self.assertEqual(shard["runs"], {"scale": 2})
        self.assertEqual(shard["mode"], "smoke")

    def test_the_stamped_template_writes_nothing_outside_the_runner(self):
        smoke = self.stamp.stamped(lambda: {"x": 1})
        before = Path.cwd()
        os.chdir(self.out)
        try:
            smoke()
        finally:
            os.chdir(before)
        self.assertFalse((self.out / "shard.json").exists())


class DeviceGuardTests(ScaffoldedTarget):
    def setUp(self):
        try:
            import torch
        except ImportError:  # pragma: no cover - the forge env ships torch
            self.skipTest("torch is not installed")
        self.torch = torch
        sys.path.insert(0, str(self.root / "src"))
        self.addCleanup(sys.path.remove, str(self.root / "src"))
        self.readiness = _load(self.root / READINESS, "readiness_under_test")

    def test_refuses_an_einsum_that_mixes_devices(self):
        torch = self.torch

        def leaky_forward(x):
            weights = torch.ones(3)  # allocated on CPU, not on x's device
            return torch.einsum("bi,i->b", x, weights)

        x = torch.ones(2, 3, device="meta")
        with self.assertRaisesRegex(AssertionError, "einsum"):
            with self.readiness.single_device():
                leaky_forward(x)

    def test_refuses_a_matmul_that_mixes_devices(self):
        torch = self.torch
        x = torch.ones(2, 3, device="meta")
        with self.assertRaisesRegex(AssertionError, "matmul"):
            with self.readiness.single_device():
                x @ torch.ones(3, 1)
        with self.assertRaisesRegex(AssertionError, "matmul"):
            with self.readiness.single_device():
                torch.matmul(x, torch.ones(3, 1))

    def test_passes_a_forward_that_stays_on_its_input_device(self):
        torch = self.torch

        def forward(x):
            weights = torch.ones(3, device=x.device)
            return torch.einsum("bi,i->b", x, weights) + (x @ weights[:, None])[:, 0]

        x = torch.ones(2, 3, device="meta")
        with self.readiness.single_device():
            out = forward(x)
        self.assertEqual(out.device.type, "meta")
        self.assertIs(torch.einsum, self.readiness._ORIGINAL_EINSUM)


class TemplateRunsInTheTargetTests(ScaffoldedTarget):
    def _pytest(self, *prelude: str):
        code = "; ".join([*prelude, "import sys, pytest",
                          f"sys.exit(pytest.main(['-q', '-rs', '-p', 'no:cacheprovider', '{READINESS}']))"])
        env = {k: v for k, v in os.environ.items() if k != "FORGE_RUN_MODE"}
        return subprocess.run([sys.executable, "-c", code], cwd=self.root,
                              capture_output=True, text=True, env=env)

    def test_template_passes_and_names_the_unwired_forward(self):
        run = self._pytest()
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn("FORWARD", run.stdout)
        self.assertRegex(run.stdout, r"\d+ passed")

    def test_template_skips_cleanly_without_torch(self):
        run = self._pytest("import sys", "sys.modules['torch'] = None")
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn("torch", run.stdout)
        self.assertRegex(run.stdout, r"\d+ skipped")
        self.assertNotRegex(run.stdout, r"\d+ (failed|error)")

    def test_template_holds_no_trivial_assertion(self):
        self.assertEqual(
            [hit for hit in impl.trivial_assertions(self.root / "tests")
             if hit.startswith(Path(READINESS).name)], [])


if __name__ == "__main__":
    unittest.main()
