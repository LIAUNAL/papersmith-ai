"""`scripts/setup-harnesses.sh` replaces only what it manages (#63).

The script projects the canonical `skills/` tree into each harness as a relative
symlink. A path at a harness location that is not a symlink is user-owned
content: the script must leave it intact and say so, not `rm -rf` it.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "setup-harnesses.sh"
HARNESS_LINKS = (".claude/skills", ".pi/skills", ".opencode/skills", ".agents/skills")


class SetupHarnessesTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "scripts").mkdir()
        shutil.copy2(SCRIPT, self.root / "scripts" / "setup-harnesses.sh")
        (self.root / "skills" / "demo").mkdir(parents=True)
        (self.root / "skills" / "demo" / "SKILL.md").write_text("---\nname: demo\n---\n")

    def run_setup(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(self.root / "scripts" / "setup-harnesses.sh")],
            cwd=self.root, capture_output=True, text=True, timeout=60,
        )

    def assert_managed_link(self, relpath: str) -> None:
        link = self.root / relpath
        self.assertTrue(link.is_symlink(), f"{relpath} must be a symlink")
        self.assertEqual(os.readlink(link), os.path.relpath(self.root / "skills", link.parent))
        self.assertTrue((link / "demo" / "SKILL.md").is_file(), relpath)

    def test_user_owned_skill_directory_is_preserved_and_reported(self) -> None:
        own = self.root / ".claude" / "skills" / "my-skill" / "SKILL.md"
        own.parent.mkdir(parents=True)
        own.write_text("mine\n")

        result = self.run_setup()

        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(".claude/skills", result.stderr)
        self.assertIn("not a symlink", result.stderr)
        self.assertEqual(own.read_text(), "mine\n", "user-owned content must survive setup")
        self.assertFalse((self.root / ".claude" / "skills").is_symlink())
        for relpath in HARNESS_LINKS[1:]:
            self.assert_managed_link(relpath)

    def test_user_owned_file_at_harness_path_is_preserved(self) -> None:
        own = self.root / ".pi" / "skills"
        own.parent.mkdir(parents=True)
        own.write_text("notes\n")

        result = self.run_setup()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(".pi/skills", result.stderr)
        self.assertEqual(own.read_text(), "notes\n")

    def test_existing_managed_link_is_replaced(self) -> None:
        stale = self.root / ".opencode" / "skills"
        stale.parent.mkdir(parents=True)
        stale.symlink_to("/nonexistent/old-checkout/skills")

        result = self.run_setup()

        self.assertEqual(result.returncode, 0, result.stderr)
        for relpath in HARNESS_LINKS:
            self.assert_managed_link(relpath)

    def test_repeated_setup_converges(self) -> None:
        first = self.run_setup()
        second = self.run_setup()

        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(first.stdout, second.stdout)
        for relpath in HARNESS_LINKS:
            self.assert_managed_link(relpath)
            self.assertFalse((self.root / relpath / "skills").exists(), "no nested link")


if __name__ == "__main__":
    unittest.main()
