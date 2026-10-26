"""Shell scripts keep LF endings on every platform.

A clone made by Windows git (``core.autocrlf=true``) into ``/mnt/c`` would
otherwise check ``setup-harnesses.sh`` out with CRLF, and bash under WSL
fails on the ``\\r``. ``.gitattributes`` pins LF; these tests read the
checkout and never write to it.
"""
from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True,
                          text=True, check=True).stdout


@unittest.skipUnless(shutil.which("git") and (REPO / ".git").exists(), "needs a git checkout")
class LineEndingTests(unittest.TestCase):
    def test_the_attributes_file_pins_lf_for_shell_scripts(self) -> None:
        self.assertTrue((REPO / ".gitattributes").is_file())
        out = _git("check-attr", "text", "eol", "--", "scripts/example.sh", "any/file.py")
        self.assertIn("scripts/example.sh: eol: lf", out)
        self.assertIn("any/file.py: eol: lf", out)
        self.assertNotIn("scripts/example.sh: text: unset", out)

    def test_binary_assets_are_not_text(self) -> None:
        out = _git("check-attr", "text", "--", "a.png", "a.pdf", "a.woff2", "a.bcmap")
        for name in ("a.png", "a.pdf", "a.woff2", "a.bcmap"):
            self.assertIn(f"{name}: text: unset", out)

    def test_every_tracked_shell_script_has_lf_endings(self) -> None:
        scripts = [line for line in _git("ls-files", "-z", "--", "*.sh").split("\0") if line]
        self.assertTrue(scripts, "the repository ships shell scripts")
        crlf = [name for name in scripts
                if (REPO / name).is_file() and b"\r\n" in (REPO / name).read_bytes()]
        self.assertEqual(crlf, [])


if __name__ == "__main__":
    unittest.main()
