"""Where a crash is recorded, and what never counts as one (#67, #88).

`main()` records any non-`Refused` exception as a `kind: "defect"` event, and
every gated command then refuses `FORGE_DEFECT_OPEN` until it clears. Two
holes made that mechanism poison state it was never meant to touch:

- #88: the recorder built its ledger path from the raw `--target`/`--name`,
  skipping the three guards `defect` itself runs (`resolve_target`,
  `validate_name`, `require_named_product_dir`). A crash wrote ledgers outside
  the workspace, created absent targets, followed `--name ../x`, and opened
  the phantom `<name>/` tree `PRODUCT_DIR_MISNAMED` exists to prevent.
- #67: an unreadable or malformed `--plan` raised an uncaught exception, so a
  typo in operator input became a persistent forge defect.

Every scenario runs `impl.main` in-process against a workspace in a temporary
directory (`impl_guards.WORKSPACE` patched), never the checkout's
`implementations/`.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
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
import impl_position  # noqa: E402


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


class _Workspace(unittest.TestCase):
    """A temporary forge workspace the engine's guards accept."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="defect-recorder-")).resolve()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.workspace = self.root / "implementations"
        self.workspace.mkdir()
        patcher = unittest.mock.patch.object(impl_guards, "WORKSPACE", self.workspace)
        patcher.start()
        self.addCleanup(patcher.stop)

    def repo(self, parent: Path, name: str = "Box") -> Path:
        target = parent / name
        target.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(target)], check=True, capture_output=True)
        _git(target, "config", "user.email", "test@example.invalid")
        _git(target, "config", "user.name", "test")
        return target

    def main(self, argv: list[str]) -> tuple[int, dict]:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = impl.main(argv)
        return code, json.loads(buf.getvalue())

    def crash(self, target: Path | str, name: str) -> None:
        boom = unittest.mock.Mock(side_effect=RuntimeError("boom"))
        with unittest.mock.patch.dict(impl.COMMANDS, {"step": boom}):
            with self.assertRaises(RuntimeError) as raised:
                impl.main(["step", "--target", str(target), "--name", name,
                           "--session", "s1", "--step", "whatever"])
        self.assertEqual(str(raised.exception), "boom")

    def files_under(self, path: Path) -> list[str]:
        return sorted(p.relative_to(path).as_posix() for p in path.rglob("*")
                      if ".git" not in p.relative_to(path).parts)


class CrashLedgerGuardTests(_Workspace):
    """#88: the recorder derives its ledger through the gates' three guards
    and records nothing when any of them refuses."""

    def test_a_crash_with_a_target_outside_the_workspace_writes_nothing(self):
        outside = self.repo(self.root / "outside", "Demo")
        self.crash(outside, "Demo")
        self.assertFalse((outside / "Demo").exists())
        self.assertEqual(self.files_under(outside), [])

    def test_a_crash_before_the_target_exists_never_creates_it(self):
        absent = self.workspace / "Absent"
        self.crash(absent, "Demo")
        self.assertFalse(absent.exists())
        self.assertEqual(list(self.workspace.iterdir()), [])

    def test_a_crash_with_a_traversing_name_writes_nothing_beside_the_target(self):
        target = self.repo(self.workspace)
        self.crash(target, "../x")
        self.assertFalse((self.workspace / "x").exists())
        self.assertEqual(sorted(p.name for p in self.workspace.iterdir()), ["Box"])
        self.assertEqual(self.files_under(target), [])

    def test_a_crash_under_a_misnamed_product_folder_opens_no_phantom_tree(self):
        target = self.repo(self.workspace)
        notebook = target / "Other" / "Notebooks" / "a.ipynb"
        notebook.parent.mkdir(parents=True)
        notebook.write_text("{}\n", encoding="utf-8")
        _git(target, "add", "-A")
        _git(target, "commit", "-q", "-m", "product under another name")
        self.crash(target, "Method")
        self.assertFalse((target / "Method").exists())

    def test_a_real_crash_in_a_valid_target_is_still_recorded(self):
        target = self.repo(self.workspace)
        (target / "Method").mkdir()
        self.crash(target, "Method")
        ledger = target / "Method" / ".implementation" / "position.jsonl"
        events = impl_position.read_events(ledger)
        defects = [e for e in events if e.get("kind") == "defect"]
        self.assertEqual(len(defects), 1)
        self.assertEqual(defects[0]["command"], "step")
        self.assertEqual(defects[0]["detail"], "RuntimeError: boom")
        self.assertEqual(len(impl_position.open_defects(events, impl.FORGE_ROOT)), 1)


class InvalidPlanIsARefusalTests(_Workspace):
    """#67: an invalid `--plan` refuses with exit 2 and leaves no defect, so
    the next command still runs."""

    def setUp(self):
        super().setUp()
        self.target = self.repo(self.workspace)
        (self.target / "Method").mkdir()
        self.ledger = self.target / "Method" / ".implementation" / "position.jsonl"
        self.plans = Path(tempfile.mkdtemp(prefix="plans-"))
        self.addCleanup(shutil.rmtree, self.plans, ignore_errors=True)

    def apply(self, plan: Path) -> tuple[int, dict]:
        return self.main(["apply", "--target", str(self.target),
                          "--name", "Method", "--plan", str(plan)])

    def assert_refused_without_poisoning(self, plan: Path, code: str) -> None:
        exit_code, payload = self.apply(plan)
        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["status"], "refused")
        self.assertEqual(payload["code"], code)
        self.assertFalse(self.ledger.exists())
        # The next gated command reaches its own gate, not FORGE_DEFECT_OPEN.
        other = self.plans / "other.json"
        other.write_text(json.dumps({"target": "elsewhere", "name": "Method"}),
                         encoding="utf-8")
        exit_code, payload = self.apply(other)
        self.assertEqual((exit_code, payload["code"]), (2, "PLAN_MISMATCH"))

    def test_a_missing_plan_refuses_and_leaves_no_defect(self):
        self.assert_refused_without_poisoning(self.plans / "absent.json", "PLAN_STALE")

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0,
                     "root reads a mode-000 file")
    def test_an_unreadable_plan_refuses_and_leaves_no_defect(self):
        plan = self.plans / "locked.json"
        plan.write_text("{}", encoding="utf-8")
        plan.chmod(0)
        self.addCleanup(plan.chmod, 0o600)
        self.assert_refused_without_poisoning(plan, "PLAN_STALE")

    def test_a_malformed_plan_refuses_and_leaves_no_defect(self):
        plan = self.plans / "malformed.json"
        plan.write_text("{not json", encoding="utf-8")
        self.assert_refused_without_poisoning(plan, "PLAN_STALE")

    def test_a_plan_that_is_not_an_object_refuses_and_leaves_no_defect(self):
        plan = self.plans / "list.json"
        plan.write_text("[]", encoding="utf-8")
        self.assert_refused_without_poisoning(plan, "PLAN_MISMATCH")


if __name__ == "__main__":
    unittest.main()
