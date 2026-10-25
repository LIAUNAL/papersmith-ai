"""#60: the orphan sweep removes only what a test run provably owns.

The sweep runs against the live `implementations/`, which is also where an
operator keeps real implementation repositories. Age and "git does not track
it" are true of those too, so neither can be what licenses a delete. Each
test here builds its own throwaway forge (a real git repository) and points
the sweep at it; the live checkout is never touched.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import orphan_sweep


def _dead_pid() -> int:
    """A pid that names no live process: a child that already exited."""
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    return proc.pid


class OwnershipLicensesTheSweepTests(unittest.TestCase):

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.forge = Path(tmp.name)
        subprocess.run(["git", "init", "-q"], cwd=self.forge, check=True)
        self.implementations = self.forge / "implementations"
        self.implementations.mkdir()
        patcher = mock.patch.object(orphan_sweep, "FORGE_ROOT", self.forge)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_the_registry_lives_outside_every_swept_root(self):
        registry = orphan_sweep.registry_path()
        self.assertIsNotNone(registry)
        self.assertTrue(registry.resolve().is_relative_to(
            (self.forge / ".git").resolve()))

    def _aged(self, name: str, age_seconds: float = 7200, *,
              symlink_to: Path | None = None) -> Path:
        path = self.implementations / name
        if symlink_to is not None:
            path.symlink_to(symlink_to, target_is_directory=True)
            return path
        path.mkdir()
        (path / "fixture.txt").write_text("left behind", encoding="utf-8")
        stamp = time.time() - age_seconds
        os.utime(path, (stamp, stamp))
        return path

    def _sweep(self):
        return orphan_sweep.sweep(roots=(self.implementations,),
                                  min_age_seconds=3600)

    def test_an_old_untracked_operator_repository_is_never_swept(self):
        """The reported hazard: old, untracked and `_`-prefixed is exactly
        what an operator's own repository can look like."""
        operator = self._aged("_my_paper_2024")
        subprocess.run(["git", "init", "-q"], cwd=operator, check=True)
        stamp = time.time() - 7200
        os.utime(operator, (stamp, stamp))
        removed = self._sweep()
        self.assertTrue(operator.exists(), "an operator repository was swept")
        self.assertTrue((operator / "fixture.txt").exists())
        self.assertEqual(removed, [])

    def test_an_interrupted_run_s_fixture_is_swept(self):
        """A killed run registered its pid and died; the fixture named after
        that pid is provably its own, and is removed."""
        pid = _dead_pid()
        with mock.patch.object(orphan_sweep.os, "getpid", return_value=pid), \
                mock.patch.object(orphan_sweep.time, "time",
                                  return_value=time.time() - 3 * 3600):
            orphan_sweep.register_run()
        orphan = self._aged(f"_e2e_step_killed_{pid}_1234")
        removed = self._sweep()
        self.assertFalse(orphan.exists())
        self.assertEqual(removed, [f"implementations/{orphan.name}"])

    def test_a_fixture_of_a_live_run_survives(self):
        """This very process registered itself: its fixtures are in use."""
        orphan_sweep.register_run()
        live = self._aged(f"_e2e_live_{os.getpid()}")
        self.assertEqual(self._sweep(), [])
        self.assertTrue(live.exists())

    def test_a_pid_token_no_run_registered_is_not_ownership(self):
        unregistered = self._aged(f"_e2e_step_killed_{_dead_pid()}")
        self.assertEqual(self._sweep(), [])
        self.assertTrue(unregistered.exists())

    def test_a_symlink_is_never_swept_nor_followed(self):
        pid = _dead_pid()
        with mock.patch.object(orphan_sweep.os, "getpid", return_value=pid), \
                mock.patch.object(orphan_sweep.time, "time",
                                  return_value=time.time() - 3 * 3600):
            orphan_sweep.register_run()
        elsewhere = tempfile.TemporaryDirectory()
        self.addCleanup(elsewhere.cleanup)
        (Path(elsewhere.name) / "keep.txt").write_text("x", encoding="utf-8")
        link = self._aged(f"_e2e_link_{pid}", symlink_to=Path(elsewhere.name))
        stamp = time.time() - 7200
        os.utime(link, (stamp, stamp), follow_symlinks=False)
        self.assertEqual(self._sweep(), [])
        self.assertTrue(link.is_symlink())
        self.assertTrue((Path(elsewhere.name) / "keep.txt").exists())

    def test_without_a_registry_nothing_in_the_forge_is_swept(self):
        """No git directory means no record of any run: fail closed."""
        with mock.patch.object(orphan_sweep, "registry_path", return_value=None):
            orphan = self._aged(f"_e2e_step_killed_{_dead_pid()}")
            self.assertEqual(self._sweep(), [])
            self.assertTrue(orphan.exists())


if __name__ == "__main__":
    unittest.main()


class RegistryPruningTests(unittest.TestCase):
    """Review follow-up: the append-only registry is pruned of expired runs."""

    def test_pruning_drops_expired_runs_and_keeps_recent_ones(self):
        import tempfile
        import time

        with tempfile.TemporaryDirectory() as tmp:
            registry = Path(tmp) / "papersmith-test-runs"
            now = time.time()
            old = now - orphan_sweep.RUN_TTL_SECONDS - 10
            registry.write_text(f"111 {old:.0f}\n222 {now:.0f}\nnot a line\n", encoding="utf-8")
            with mock.patch.object(orphan_sweep, "registry_path", return_value=registry):
                orphan_sweep.prune_registry(now)
            self.assertEqual(registry.read_text(encoding="utf-8"), f"222 {now:.0f}\n")
