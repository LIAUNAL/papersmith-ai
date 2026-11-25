"""Caztor's own agent definition is not a smith agent.

Caztor writes `.claude/agents/caztor.md`, `.opencode/agents/caztor.md` and
`.agents/agents/caztor.md` into the workspace itself, and promises never to
write `.pi/` (caztor/README.md). smith projects every other
`.claude/agents/*.md` into the other harnesses, so it must leave this one alone:
`smith upgrade` neither overwrites Caztor's copies nor creates
`.pi/agents/caztor.md`, and `doctor` does not list it among smith's agents.
"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from papersmith.core import doctor
from papersmith.core import init as init_module
from papersmith.core import upgrade as upgrade_module
from papersmith.generators import ALL_TOOLS, check_generated, render_files

CLAUDE_COPY = (
    "---\nname: caztor\ndescription: Caztor academic writing instructions\n"
    "tools: Read, Edit\n---\n\nCaztor's own instructions.\n"
)
OPENCODE_COPY = "---\ndescription: Caztor academic writing instructions\nmode: primary\n---\n\nCaztor (opencode).\n"
ANTIGRAVITY_COPY = "---\nname: caztor\ndescription: Caztor academic writing instructions\n---\n\nCaztor (Antigravity).\n"


def _upgrade(workspace: Path) -> dict:
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return upgrade_module.upgrade(workspace, allow_dirty_kit=True)


class CaztorAgentProjectionTests(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.workspace = Path(holder.name).resolve() / "paper"
        init_module.initialize(self.workspace, run_npm=False, run_env=False)
        self.copies = {
            ".claude/agents/caztor.md": CLAUDE_COPY,
            ".opencode/agents/caztor.md": OPENCODE_COPY,
            ".agents/agents/caztor.md": ANTIGRAVITY_COPY,
        }
        for relpath, text in self.copies.items():
            (self.workspace / relpath).write_text(text, encoding="utf-8")

    def assert_caztor_copies_untouched(self) -> None:
        for relpath, text in self.copies.items():
            self.assertEqual((self.workspace / relpath).read_text(encoding="utf-8"), text, relpath)
        self.assertFalse((self.workspace / ".pi" / "agents" / "caztor.md").exists())

    def test_render_projects_the_other_agents_but_not_caztor(self) -> None:
        rendered = render_files(self.workspace, tools=ALL_TOOLS, warnings=[])
        for directory in (".pi/agents", ".opencode/agents", ".agents/agents"):
            self.assertNotIn(f"{directory}/caztor.md", rendered)
            self.assertIn(f"{directory}/redactor.md", rendered)
        self.assertNotIn("`caztor`", rendered["CLAUDE.md"])
        self.assertIn("`redactor`", rendered["CLAUDE.md"])

    def test_upgrade_leaves_caztor_copies_alone_and_writes_no_pi_copy(self) -> None:
        _upgrade(self.workspace)
        self.assert_caztor_copies_untouched()
        for directory in (".pi/agents", ".opencode/agents", ".agents/agents"):
            self.assertTrue((self.workspace / directory / "redactor.md").is_file(), directory)
        self.assertEqual([path for path in check_generated(self.workspace, tools=ALL_TOOLS)
                          if path.endswith("agents/caztor.md")], [])
        stored = json.loads((self.workspace / ".papersmith" / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual([path for path in stored["files"] if path.endswith("agents/caztor.md")], [])

    def test_upgrade_after_an_older_release_projected_caztor_keeps_caztor_copies(self) -> None:
        # An older smith projected caztor.md and baselined its copies; the orphan
        # sweep removes smith's own `.pi/` copy but never Caztor's files.
        path = self.workspace / ".papersmith" / "manifest.json"
        stored = json.loads(path.read_text(encoding="utf-8"))
        for relpath in (".pi/agents/caztor.md", ".opencode/agents/caztor.md", ".agents/agents/caztor.md"):
            stored["files"][relpath] = "0" * 64
        path.write_text(json.dumps(stored), encoding="utf-8")
        (self.workspace / ".pi" / "agents" / "caztor.md").write_text("projected by smith\n", encoding="utf-8")
        _upgrade(self.workspace)
        self.assert_caztor_copies_untouched()

    def test_doctor_does_not_list_caztor_as_a_smith_agent(self) -> None:
        backend = {
            "wiring": {"agents": [
                {"name": "redactor", "path": ".claude/agents/redactor.md", "state": "WIRED", "detail": "ok"},
                {"name": "caztor", "path": ".claude/agents/caztor.md", "state": "WIRED", "detail": "ok"},
            ]},
            "packages": [], "phases": [],
        }
        report = doctor.build_report(self.workspace, backend=backend)
        agents = [row["item"] for row in report["rows"] if row["area"] == "agents"]
        self.assertIn("redactor", agents)
        self.assertNotIn("caztor", agents)


if __name__ == "__main__":
    unittest.main()
