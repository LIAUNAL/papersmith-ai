"""A failed operation's rollback never destroys the ledger (#80).

`require_clean_worktree` admits exactly one kind of dirt: this skill's own
`.implementation/` bookkeeping, untracked or modified. The rollback after a
failed mutation (`apply`, `materialize --stage`, `adopt --apply`) ran
`git reset --hard` and `git clean -fd`, which deleted an untracked ledger and
reverted a modified one: the record of the very session that hit the
failure. Every other pre-existing change is refused before mutation, so the
rollback owns everything else it removes.

Runs `impl.main` in-process against a temporary workspace
(`impl_guards.WORKSPACE` patched), never the checkout's `implementations/`.
"""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

FORGE = Path(__file__).resolve().parents[1]
ENGINE = FORGE / "skills/_core/implementation/engine/implementation_engine.py"
sys.path.insert(0, str(ENGINE.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from domain_profile import seeded_profile  # noqa: E402  (path set above)
with seeded_profile(FORGE / "skills/proposal-implementation/impl_profile.py"):
    import implementation_engine as impl  # noqa: E402  (path set above)
import impl_guards  # noqa: E402

LEDGER_BYTES = b'{"kind": "position", "note": "operator session"}\n'


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          capture_output=True, text=True).stdout


class RollbackOwnershipTests(unittest.TestCase):

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="rollback-")).resolve()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        workspace = self.root / "implementations"
        workspace.mkdir()
        patcher = unittest.mock.patch.object(impl_guards, "WORKSPACE", workspace)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.target = workspace / "Box"
        self.target.mkdir()
        _git(self.target, "init", "-q")
        _git(self.target, "config", "user.email", "test@example.invalid")
        _git(self.target, "config", "user.name", "test")
        (self.target / "README.md").write_text("# Box\n", encoding="utf-8")
        (self.target / ".gitignore").write_text("scratch.log\n", encoding="utf-8")
        _git(self.target, "add", "-A")
        _git(self.target, "commit", "-q", "-m", "initial")
        self.head = _git(self.target, "rev-parse", "HEAD").strip()
        # An ignored operator file: `clean -fd` never reached it, and the
        # rollback must keep it that way.
        (self.target / "scratch.log").write_text("operator notes\n", encoding="utf-8")
        self.ledger = self.target / "Method" / ".implementation" / "position.jsonl"

    def main(self, argv: list[str]) -> tuple[int, dict]:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = impl.main(argv)
        return code, json.loads(buf.getvalue())

    def plan(self) -> Path:
        code, plan = self.main(["plan", "--target", str(self.target), "--name", "Method"])
        self.assertEqual(code, 0, plan)
        path = self.root / "plan.json"
        path.write_text(json.dumps(plan), encoding="utf-8")
        return path

    def failing_migrate(self, target: Path, current: dict) -> None:
        """A migration that writes, stages and then fails, the way a real
        `git mv` or reference rewrite fails halfway."""
        (target / "Method" / "Notebooks").mkdir(parents=True, exist_ok=True)
        (target / "Method" / "Notebooks" / ".gitkeep").touch()
        (target / "README.md").write_text("# half-migrated\n", encoding="utf-8")
        _git(target, "add", "-A")
        raise RuntimeError("migration failed halfway")

    def apply_failing(self) -> tuple[int, dict]:
        plan = self.plan()
        with unittest.mock.patch.object(impl, "migrate", self.failing_migrate):
            return self.main(["apply", "--target", str(self.target), "--name", "Method",
                              "--plan", str(plan)])

    def assert_operation_rolled_back(self, code: int, payload: dict) -> None:
        self.assertEqual((code, payload["code"]), (2, "APPLY_ABORTED"), payload)
        self.assertEqual(_git(self.target, "rev-parse", "HEAD").strip(), self.head)
        self.assertEqual((self.target / "README.md").read_text(encoding="utf-8"), "# Box\n")
        self.assertFalse((self.target / "Method" / "Notebooks").exists())
        self.assertEqual((self.target / "scratch.log").read_text(encoding="utf-8"),
                         "operator notes\n")

    def test_failed_operation_preserves_untracked_ledger(self):
        # The guard admits an untracked ledger once its product folder holds
        # tracked files (porcelain then names `Method/.implementation/`, not
        # a collapsed `Method/`), which is the ordinary state after `apply`.
        (self.target / "Method" / "Data").mkdir(parents=True)
        (self.target / "Method" / "Data" / ".gitkeep").touch()
        _git(self.target, "add", "-A")
        _git(self.target, "commit", "-q", "-m", "product folder")
        self.head = _git(self.target, "rev-parse", "HEAD").strip()
        self.ledger.parent.mkdir(parents=True)
        self.ledger.write_bytes(LEDGER_BYTES)
        self.assert_operation_rolled_back(*self.apply_failing())
        self.assertEqual(self.ledger.read_bytes(), LEDGER_BYTES)
        self.assertEqual(_git(self.target, "status", "--porcelain"),
                         "?? Method/.implementation/\n")

    def test_failed_operation_preserves_a_modified_tracked_ledger(self):
        self.ledger.parent.mkdir(parents=True)
        self.ledger.write_bytes(LEDGER_BYTES)
        _git(self.target, "add", "-A")
        _git(self.target, "commit", "-q", "-m", "ledger")
        self.head = _git(self.target, "rev-parse", "HEAD").strip()
        appended = LEDGER_BYTES + b'{"kind": "step", "note": "not yet committed"}\n'
        self.ledger.write_bytes(appended)
        self.assert_operation_rolled_back(*self.apply_failing())
        self.assertEqual(self.ledger.read_bytes(), appended)

    def test_rollback_cleans_only_operation_owned_artifacts(self):
        self.assert_operation_rolled_back(*self.apply_failing())
        self.assertEqual(_git(self.target, "status", "--porcelain"), "")

    def test_failed_operation_preserves_operator_tracked_edits(self):
        """Operator work outside the ledger refuses before any mutation."""
        plan = self.plan()
        (self.target / "README.md").write_text("# operator edit\n", encoding="utf-8")
        (self.target / "sentinel.txt").write_text("untracked operator file\n",
                                                  encoding="utf-8")
        migrate = unittest.mock.Mock()
        with unittest.mock.patch.object(impl, "migrate", migrate):
            code, payload = self.main(["apply", "--target", str(self.target),
                                       "--name", "Method", "--plan", str(plan)])
        self.assertEqual((code, payload["code"]), (2, "DIRTY_WORKTREE"))
        migrate.assert_not_called()
        self.assertEqual((self.target / "README.md").read_text(encoding="utf-8"),
                         "# operator edit\n")
        self.assertEqual((self.target / "sentinel.txt").read_text(encoding="utf-8"),
                         "untracked operator file\n")


if __name__ == "__main__":
    unittest.main()
