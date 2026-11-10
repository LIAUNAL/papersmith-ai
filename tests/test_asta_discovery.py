"""Ai2's Asta as an agent discovery connector, registered for every harness.

`init` and `upgrade` register the `asta` MCP server in each declared harness's
file with the key only by reference (`ASTA_API_KEY`); only `sota-scout` may
reach it as a subagent, and only where the harness's grant fails safe; the
scout searches it only when the key is loaded in its session. Nothing it
generates (a `tldr`, a snippet) ever becomes an abstract.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

from papersmith import generators
from papersmith.cli import build_parser
from papersmith.core import init as init_module, upgrade as upgrade_module
from skills._core.command_center import health_inspector, terminal

ROOT = Path(__file__).resolve().parents[1]
AGENTS = ROOT / ".claude" / "agents"


def _load(name: str, relative: str):
    module = sys.modules.get(name)
    if module is None:
        spec = importlib.util.spec_from_file_location(name, ROOT / "skills" / "_core" / relative)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return module


CLAUDE_ENTRY = {"type": "http", "url": "https://asta-tools.allen.ai/mcp/v1",
                "headers": {"x-api-key": "${ASTA_API_KEY:-}"}, "timeout": 60000}
BRIDGED_ENTRY = {"command": "npx", "args": ["-y", "mcp-remote@0.14.3", "https://asta-tools.allen.ai/mcp/v1",
                                            "--header", "x-api-key:${ASTA_API_KEY}"]}
OPENCODE_ENTRY = {"type": "remote", "url": "https://asta-tools.allen.ai/mcp/v1",
                  "headers": {"x-api-key": "{env:ASTA_API_KEY}"}, "enabled": True}


class RegistrationTests(unittest.TestCase):
    def workspace(self) -> Path:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        root = Path(holder.name).resolve() / "paper"
        init_module.initialize(root, run_npm=False, run_env=False,
                               tools=["claude", "opencode", "pi", "antigravity"])
        return root

    def servers(self, root: Path, relpath: str, key: str = "mcpServers") -> dict:
        return json.loads((root / relpath).read_text(encoding="utf-8"))[key]

    def test_init_registers_asta_in_every_declared_harness_with_the_key_by_reference(self) -> None:
        root = self.workspace()
        self.assertEqual(self.servers(root, ".mcp.json")["asta"], CLAUDE_ENTRY)
        self.assertEqual(self.servers(root, ".pi/mcp.json")["asta"], BRIDGED_ENTRY)
        self.assertEqual(self.servers(root, ".agents/mcp_config.json")["asta"], BRIDGED_ENTRY)
        self.assertEqual(self.servers(root, "opencode.json", "mcp")["asta"], OPENCODE_ENTRY)
        for relpath in (".mcp.json", ".pi/mcp.json", ".agents/mcp_config.json", "opencode.json"):
            text = (root / relpath).read_text(encoding="utf-8")
            self.assertNotRegex(text, r"x-api-key[\"']?\s*:\s*[\"'][A-Za-z0-9]{16,}", relpath)

    def test_the_managed_roster_is_one_list_in_every_harness(self) -> None:
        self.assertEqual(generators.MANAGED_MCP_SERVERS, ("banco-lia", "kaggle", "colab", "asta"))
        for tool in generators.MCP_CONFIG_FILES:
            self.assertEqual(tuple(generators._mcp_entries(tool)), generators.MANAGED_MCP_SERVERS)
        root = self.workspace()
        self.assertEqual(tuple(self.servers(root, "opencode.json", "mcp")), generators.MANAGED_MCP_SERVERS)

    def test_upgrade_puts_asta_back_and_keeps_the_workspaces_own_servers(self) -> None:
        root = self.workspace()
        path = root / ".mcp.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        del data["mcpServers"]["asta"]
        data["mcpServers"]["mine"] = {"command": "my-server"}
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

        upgrade_module.upgrade(root, allow_dirty_kit=True)

        servers = self.servers(root, ".mcp.json")
        self.assertEqual(servers["asta"], CLAUDE_ENTRY)
        self.assertEqual(servers["mine"], {"command": "my-server"})

    def test_a_malformed_file_is_reported_naming_every_managed_server(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        root = Path(holder.name)
        (root / ".mcp.json").write_text("[]", encoding="utf-8")
        warnings: list[str] = []
        generators.ensure_mcp_servers(root, ["claude"], warnings=warnings)
        self.assertIn("banco-lia, kaggle, colab and asta", warnings[0])

    def test_the_forge_registers_asta_exactly_like_every_workspace(self) -> None:
        forge = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))
        self.assertEqual(forge["mcpServers"]["asta"], generators._asta_entry("claude"))
        self.assertIn("ASTA_API_KEY", forge["//"])

    def test_one_name_and_one_url_across_the_cli_the_skills_and_the_dashboard(self) -> None:
        api_keys = _load("papersmith_api_keys", "api_keys.py")
        protocol = _load("papersmith_asta_protocol", "literature/asta_protocol.py")
        self.assertEqual(generators.ASTA_MCP_URL, protocol.ENDPOINT)
        self.assertEqual(generators.ASTA_KEY_ENV, api_keys.PROVIDERS["asta"]["env"])
        self.assertEqual(generators.ASTA_KEY_HEADER, protocol.KEY_HEADER)
        self.assertEqual(terminal.ASTA_MCP_SERVER, generators.ASTA_MCP_SERVER)
        self.assertIn(".mcp.json", terminal.asta_mcp_status(self.workspace())["registered"])


def _agent(tools: str) -> str:
    return f"---\nname: probe\ndescription: \"probe\"\ntools: {tools}\n---\n\n# Probe\n"


class ProjectionTests(unittest.TestCase):
    def test_opencode_allows_the_granted_server_and_denies_it_elsewhere(self) -> None:
        granted, _reason, notes = generators._translate_agent_for_opencode(_agent("Read, mcp__asta__*"))
        self.assertIn('  "asta_*": allow', granted["text"])
        self.assertEqual(notes, [])
        other, _reason, _notes = generators._translate_agent_for_opencode(_agent("Read"))
        self.assertIn('  "asta_*": deny', other["text"])

    def test_pi_and_antigravity_carry_no_managed_grant_and_say_nothing(self) -> None:
        yaml, notes = generators._pi_tools_line("Read, mcp__asta__*")
        self.assertEqual(yaml, "tools:\n  - read")
        self.assertEqual(notes, [])
        entry, _reason, notes = generators._translate_agent_for_antigravity(_agent("Read, mcp__asta__*"))
        self.assertNotIn("asta", entry["text"])
        self.assertEqual(notes, [])

    def test_an_unmanaged_server_grant_is_still_refused_by_name(self) -> None:
        _entry, _reason, notes = generators._translate_agent_for_opencode(_agent("Read, mcp__mystery__*"))
        self.assertTrue(any("mcp__mystery__*" in note for note in notes), notes)

    def test_the_inspector_binds_a_managed_server_grant_only(self) -> None:
        self.assertTrue(health_inspector._tool_bound("mcp__asta__*"))
        self.assertFalse(health_inspector._tool_bound("mcp__mystery__*"))
        self.assertFalse(health_inspector._tool_bound("mcp__asta__get_paper"))
        self.assertEqual(health_inspector._FALLBACK_GRANTABLE_MCP_SERVERS, generators.GRANTABLE_MCP_SERVERS)
        self.assertLessEqual(set(generators.GRANTABLE_MCP_SERVERS), set(generators.MANAGED_MCP_SERVERS))


class AgentProseTests(unittest.TestCase):
    def frontmatter_tools(self, name: str) -> list[str]:
        text = (AGENTS / f"{name}.md").read_text(encoding="utf-8")
        line = next(line for line in text.split("---", 2)[1].splitlines() if line.startswith("tools:"))
        return [token.strip() for token in line.split(":", 1)[1].split(",")]

    def test_only_the_scout_holds_the_asta_grant(self) -> None:
        holders = [path.stem for path in sorted(AGENTS.glob("*.md"))
                   if "mcp__asta__*" in path.read_text(encoding="utf-8").split("---", 2)[1]]
        self.assertEqual(holders, ["sota-scout"])
        self.assertIn("mcp__asta__*", self.frontmatter_tools("sota-scout"))

    def test_the_scout_searches_asta_only_with_its_key_loaded(self) -> None:
        text = (AGENTS / "sota-scout.md").read_text(encoding="utf-8")
        for fragment in ("smith keys status asta --json", '"configured": true', '"source": "env"',
                         "call no Asta tool", "`tldr`", "neither is ever an abstract", "Never print, echo or pass the key"):
            self.assertIn(fragment, text, fragment)
        spans = [span for span in re.findall(r"`([^`]*)`", text, flags=re.S) if "paper_cli.py resolve" in span]
        self.assertEqual(len(spans), 1)

    def test_the_gate_command_parses(self) -> None:
        args = build_parser().parse_args(["keys", "status", "asta", "--json"])
        self.assertEqual((args.provider, args.as_json), ("asta", True))

    def test_every_keyed_discovery_connector_is_granted_to_the_scout(self) -> None:
        template = (ROOT / "src" / "papersmith" / "templates" / "papersmith.yaml.tpl").read_text(encoding="utf-8")
        block = template.split("    discovery:", 1)[1].split("    resolution:", 1)[0]
        connectors = re.findall(r"- (\S+)", block)
        tools = self.frontmatter_tools("sota-scout")
        for connector in connectors:
            if connector in generators.GRANTABLE_MCP_SERVERS:
                self.assertIn(f"mcp__{connector}__*", tools)

    def test_the_screener_never_grades_on_generated_text(self) -> None:
        text = (AGENTS / "novelty-screener.md").read_text(encoding="utf-8")
        self.assertIn("never\ngrades a claim", text)
        self.assertNotIn("mcp__asta", text)


if __name__ == "__main__":
    unittest.main()
