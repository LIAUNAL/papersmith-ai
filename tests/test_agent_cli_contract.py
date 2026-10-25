"""The paper-ingestion agent names only what the executable CLI accepts (#70).

The agent is shipped in every workspace and projected into every harness, so a
flag it names that `extract_pdf.py` does not define sends the model to a command
that fails. The flags are read from the script's own `--help`, not listed here.
"""
from __future__ import annotations

import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENT = ROOT / ".claude" / "agents" / "paper-ingestion.md"
SKILL = ROOT / "skills" / "paper-ingestion" / "SKILL.md"
SCRIPT = ROOT / "skills" / "paper-ingestion" / "scripts" / "extract_pdf.py"
FLAG = re.compile(r"(?<![\w-])--[a-z][a-z0-9-]*")


def cli_flags() -> set[str]:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        capture_output=True, text=True, timeout=60, cwd=ROOT,
    )
    assert result.returncode == 0, result.stderr
    return set(FLAG.findall(result.stdout))


class PaperIngestionAgentContractTest(unittest.TestCase):
    def test_every_flag_the_agent_names_exists_in_the_cli(self) -> None:
        named = set(FLAG.findall(AGENT.read_text(encoding="utf-8")))
        known = cli_flags()
        self.assertIn("--list", known, "the --help parse found no flags at all")
        self.assertEqual(sorted(named - known), [],
                         "the agent names flags extract_pdf.py does not define")

    def test_agent_names_no_manifest_version_the_skill_does_not_declare(self) -> None:
        skill = SKILL.read_text(encoding="utf-8")
        named = set(re.findall(r"[Mm]anifest v\d+(?:\.\d+)*",
                               AGENT.read_text(encoding="utf-8")))
        self.assertEqual(sorted(v for v in named if v not in skill), [])


if __name__ == "__main__":
    unittest.main()
