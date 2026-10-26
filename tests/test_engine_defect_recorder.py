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
  typo in operator input became a persistent forge defect; and a `--session`
  the position header cannot carry (whitespace, non-ASCII, empty) was written
  into it on a refresh, leaving a block no later command could read.

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


class InvalidSessionIsARefusalTests(_Workspace):
    """#67: `position` stamps `--session` into the block's header, whose
    grammar reads it back as one ASCII token. A value it cannot carry is
    refused before anything is written, so the header stays readable and the
    next valid command still runs."""

    INVALID = ("two words", "caf\u00e9", "")

    def setUp(self):
        super().setUp()
        self.target = self.repo(self.workspace)
        for directory in ("src/Method", "src/Method_Benchmark", "tests", "Method"):
            (self.target / directory).mkdir(parents=True, exist_ok=True)
        (self.target / "src/Method/__init__.py").write_text("", encoding="utf-8")
        (self.target / "src/Method_Benchmark/__init__.py").write_text("", encoding="utf-8")
        proposals = self.root / "proposals"
        proposals.mkdir()
        (proposals / "r1.md").write_text("## 1\ntext\n", encoding="utf-8")
        patcher = unittest.mock.patch.dict(
            os.environ, {"IMPLEMENTATION_PROPOSALS": str(proposals)})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.holder = self.target / "Method" / "AGREED.md"
        self.ledger = self.target / "Method" / ".implementation" / "position.jsonl"

    def position(self, session: str, install: bool = False,
                 *extra: str) -> tuple[int, dict]:
        argv = ["position", "--target", str(self.target), "--name", "Method",
                "--revision", "r1.md", "--session", session, *extra]
        if not install:
            return self.main(argv)
        sequence = json.dumps([{"text": "Rehearse the job.",
                                "witness": {"kind": "rehearsal", "operand": "job1"}}])
        with unittest.mock.patch("sys.stdin", io.StringIO(sequence)):
            return self.main(argv + ["--sequence", "-", "--target-level", "local"])

    def header_session(self) -> str:
        return impl_position.locate_block(self.holder.read_bytes())["session"]

    def test_invalid_session_preserves_readable_header(self):
        self.assertEqual(self.position("s1", install=True)[0], 0)
        # A new notebook gives `--reconcile` an item to append, so the call
        # rewrites the header rather than reporting it unchanged.
        notebook = self.target / "Method" / "Notebooks" / "a.ipynb"
        notebook.parent.mkdir()
        notebook.write_text("{}\n", encoding="utf-8")
        before = self.holder.read_bytes()
        events = impl_position.read_events(self.ledger)
        for session in self.INVALID:
            with self.subTest(session=session):
                exit_code, payload = self.position(session, False, "--reconcile")
                self.assertEqual(exit_code, 2)
                self.assertEqual(payload["status"], "refused")
                self.assertEqual(payload["code"], "POSITION_SESSION_INVALID")
                self.assertEqual(self.holder.read_bytes(), before)
                self.assertEqual(impl_position.read_events(self.ledger), events)
                self.assertEqual(self.header_session(), "s1")
        exit_code, payload = self.position("s2", False, "--reconcile")
        self.assertEqual((exit_code, payload["status"]), (0, "written"), payload)
        self.assertEqual(self.header_session(), "s2")

    def test_an_invalid_session_on_install_writes_no_holder(self):
        for session in self.INVALID:
            with self.subTest(session=session):
                exit_code, payload = self.position(session, install=True)
                self.assertEqual((exit_code, payload["code"]),
                                 (2, "POSITION_SESSION_INVALID"))
                self.assertFalse(self.holder.exists())
                self.assertFalse(self.ledger.exists())
        self.assertEqual(self.position("s1", install=True)[0], 0)
        self.assertEqual(self.header_session(), "s1")

    def test_a_shell_safe_session_is_still_stamped_verbatim(self):
        exit_code, payload = self.position("2026-10-12-a", install=True)
        self.assertEqual(exit_code, 0, payload)
        self.assertEqual(self.header_session(), "2026-10-12-a")
        self.assertEqual(impl_position.read_events(self.ledger)[-1]["session"],
                         "2026-10-12-a")


if __name__ == "__main__":
    unittest.main()
