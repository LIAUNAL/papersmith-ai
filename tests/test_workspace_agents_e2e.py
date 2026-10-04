"""From-scratch agent series: every subagent definition, inside the workspace.

Layer purpose. ``test_agents.py`` holds the deep two-way binding contract for
the repository's own copies; this module proves the *shipped* copies — the
``.claude/agents`` tree every ``papersmith init`` workspace carries — arrive
whole, parse, resolve the skill each stretch loads, and reach every harness
routing document. An agent that only exists in the repository is not a shipped
subagent.

Read-only: nothing here launches a model or mutates a workspace.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import unittest
from pathlib import Path

from papersmith.generators import check_generated

from workspace_series import REPO_ROOT, make_workspace, new_tmp

ROUTING_DOCS = ("CLAUDE.md", "OPENCODE.md", ".pi/APPEND_SYSTEM.md", ".antigravity/rules.md")
SKILL_BINDING = re.compile(r"skills/([\w-]+)/SKILL\.md")


def frontmatter(path: Path) -> dict[str, str]:
    """Parse the single-line key/value frontmatter an agent definition carries."""
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines and lines[0].strip() == "---", f"{path} has no frontmatter"
    metadata: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" in line:
            key, value = line.split(":", 1)
            value = value.strip()
            if value[:1] in {"'", '"'}:
                value = ast.literal_eval(value)
            metadata[key.strip()] = value
    return metadata


def agent_files(workspace: Path) -> list[Path]:
    return sorted((workspace / ".claude" / "agents").glob("*.md"))


class AgentShippingTests(unittest.TestCase):

    def test_every_repository_agent_ships_in_the_workspace(self) -> None:
        workspace = make_workspace(new_tmp(self))
        repo = {path.name for path in (REPO_ROOT / ".claude/agents").glob("*.md")}
        shipped = {path.name for path in agent_files(workspace)}
        self.assertTrue(repo, "the repository must define agents")
        self.assertEqual(shipped, repo, "the workspace must ship the whole agent tree")

    def test_every_shipped_agent_matches_its_recorded_bytes(self) -> None:
        workspace = make_workspace(new_tmp(self))
        manifest = json.loads(
            (workspace / ".papersmith" / "manifest.json").read_text(encoding="utf-8"))
        for path in agent_files(workspace):
            relpath = path.relative_to(workspace).as_posix()
            with self.subTest(agent=path.name):
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                self.assertEqual(manifest["files"].get(relpath), digest,
                                 f"{relpath} does not match the workspace manifest")


class AgentContractTests(unittest.TestCase):

    def test_every_agent_parses_and_names_itself(self) -> None:
        workspace = make_workspace(new_tmp(self))
        for path in agent_files(workspace):
            with self.subTest(agent=path.name):
                metadata = frontmatter(path)
                self.assertEqual(metadata.get("name"), path.stem)
                self.assertTrue(metadata.get("description", "").strip(),
                                "an agent without a description opens every session blind")
                self.assertTrue(metadata.get("tools", "").strip(),
                                "an agent must declare the tools it may use")

    def test_every_agent_skill_binding_resolves_in_the_workspace(self) -> None:
        workspace = make_workspace(new_tmp(self))
        for path in agent_files(workspace):
            with self.subTest(agent=path.name):
                named = SKILL_BINDING.findall(path.read_text(encoding="utf-8"))
                self.assertTrue(named, f"{path.name} names no skill to load")
                for skill in named:
                    self.assertTrue(
                        (workspace / "skills" / skill / "SKILL.md").is_file(),
                        f"{path.name} names {skill}, which the workspace does not ship",
                    )


class AgentRoutingTests(unittest.TestCase):

    def test_every_routing_doc_lists_every_agent_verbatim(self) -> None:
        workspace = make_workspace(new_tmp(self))
        metadata = {path.stem: frontmatter(path) for path in agent_files(workspace)}
        for doc_name in ROUTING_DOCS:
            text = (workspace / doc_name).read_text(encoding="utf-8")
            self.assertIn("skills/", text, f"{doc_name} must route to the skill tree")
            for stem, fields in metadata.items():
                with self.subTest(doc=doc_name, agent=stem):
                    self.assertIn(f"- `{fields['name']}`", text)
                    self.assertIn(fields["description"], text)

    def test_generated_projections_are_clean_and_tamper_evident(self) -> None:
        workspace = make_workspace(new_tmp(self))
        self.assertEqual(check_generated(workspace), [],
                         "a fresh workspace must carry no generator drift")
        pi = workspace / ".pi/APPEND_SYSTEM.md"
        pi.write_text("drift\n", encoding="utf-8")
        self.assertIn(".pi/APPEND_SYSTEM.md", check_generated(workspace))

    def test_agent_tree_is_declared_the_single_source_of_truth(self) -> None:
        workspace = make_workspace(new_tmp(self))
        claude = (workspace / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn(".claude/agents/", claude)
        self.assertIn("single source of truth", claude)

    def test_generated_routing_docs_document_their_command_surface(self) -> None:
        workspace = make_workspace(new_tmp(self))
        opencode = (workspace / "OPENCODE.md").read_text(encoding="utf-8")
        self.assertIn(".opencode/commands/", opencode)
        self.assertIn("refuse-offpath-push.js", opencode)
        claude = (workspace / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn(".claude/commands/", claude)
        pi = (workspace / ".pi/APPEND_SYSTEM.md").read_text(encoding="utf-8")
        # Pi routes skills through the settings file and exposes them natively
        # as ``/skill:<name>``; it therefore documents no command directory it
        # does not have.
        self.assertIn(".pi/settings.json", pi)
        self.assertIn("/skill:", pi)
        self.assertIn("no command files are generated", pi)
        antigravity = (workspace / ".antigravity/rules.md").read_text(encoding="utf-8")
        self.assertIn("no generated slash commands", antigravity)
