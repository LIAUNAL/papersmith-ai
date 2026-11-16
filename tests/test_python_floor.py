"""Every skill CLI refuses an interpreter older than the package floor by name (#184 item 5).

The package requires Python 3.11 (`pyproject.toml`), but skills are often run with the system `python3`.
Before this guard a 3.9 interpreter crashed with a bare TypeError or SyntaxError naming a module the caller
never asked about. Each `*_cli.py` entry point now checks the version before importing anything else and
answers `{"ok": false, "error": "PYTHON_VERSION_UNSUPPORTED", ...}` with exit code 2.
"""
from __future__ import annotations

import ast
import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

FORGE_ROOT = Path(__file__).resolve().parents[1]
FLOOR_LINE = "if _floor_sys.version_info < (3, 11):"


def cli_entries() -> list[Path]:
    return sorted(p for p in (FORGE_ROOT / "skills").rglob("*_cli.py")
                  if "/assets/" not in p.as_posix() and "__pycache__" not in p.parts)


def package_floor() -> tuple[int, int]:
    text = (FORGE_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    major, minor = re.search(r'requires-python\s*=\s*">=(\d+)\.(\d+)"', text).groups()
    return int(major), int(minor)


def old_interpreter() -> str | None:
    """A system interpreter below the floor, when this machine has one (macOS ships 3.9)."""
    for candidate in ("/usr/bin/python3", shutil.which("python3.9"), shutil.which("python3.10")):
        if not candidate or not Path(candidate).exists():
            continue
        probe = subprocess.run([candidate, "-c", "import sys; print(sys.version_info[:2] < (3, 11))"],
                               capture_output=True, text=True)
        if probe.stdout.strip() == "True":
            return candidate
    return None


class PythonFloorTests(unittest.TestCase):
    def test_the_guard_names_the_package_floor(self) -> None:
        self.assertEqual(package_floor(), (3, 11))
        self.assertIn(f"< {package_floor()}:", FLOOR_LINE)

    def test_every_cli_checks_the_floor_before_any_other_import(self) -> None:
        entries = cli_entries()
        self.assertGreater(len(entries), 10)
        for path in entries:
            with self.subTest(cli=str(path.relative_to(FORGE_ROOT))):
                source = path.read_text(encoding="utf-8")
                self.assertIn(FLOOR_LINE, source)
                tree = ast.parse(source)
                imports = [node for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))
                           and not (isinstance(node, ast.ImportFrom) and node.module == "__future__")]
                guard = next(node for node in tree.body if isinstance(node, ast.If)
                             and FLOOR_LINE.strip(":") in ast.get_source_segment(source, node))
                self.assertEqual(ast.unparse(imports[0]), "import sys as _floor_sys")
                self.assertLess(imports[0].lineno, guard.lineno)
                self.assertTrue(all(node.lineno > guard.lineno for node in imports[1:]),
                                "an import runs before the floor is checked")

    def test_an_old_interpreter_is_refused_by_name(self) -> None:
        interpreter = old_interpreter()
        if interpreter is None:
            self.skipTest("no interpreter below 3.11 on this machine")
        for path in cli_entries():
            with self.subTest(cli=str(path.relative_to(FORGE_ROOT))):
                done = subprocess.run([interpreter, str(path), "--help"], capture_output=True, text=True,
                                      timeout=60, cwd=FORGE_ROOT)
                self.assertEqual(done.returncode, 2, done.stderr[-400:])
                # Each CLI answers on its own refusal channel: stdout, or stderr for datasets_cli.
                answer = json.loads(done.stdout or done.stderr)
                self.assertEqual(answer["error"], "PYTHON_VERSION_UNSUPPORTED")
                self.assertFalse(answer["ok"])
                self.assertIn("3.11", answer["message"])
                self.assertNotIn("Traceback", done.stdout + done.stderr)


if __name__ == "__main__":
    unittest.main()
