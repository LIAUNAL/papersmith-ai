"""Standalone generator wrappers and drift detection."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
import warnings
from pathlib import Path

import yaml

from papersmith.core import init as init_module
from papersmith.core import manifest
from papersmith.errors import UserError
from papersmith.generators import (
    ALL_TOOLS,
    check_generated,
    collect_agents,
    collect_antigravity_agents,
    collect_commands,
    collect_opencode_agents,
    collect_pi_agents,
    context_for_workspace,
    derive_command_description,
    render_files,
    workspace_tools,
    yaml_double_quote,
    _translate_agent_for_antigravity,
    _translate_agent_for_opencode,
    _translate_agent_for_pi,
)
from papersmith.kit import resolve_and_validate


ROOT = Path(__file__).resolve().parents[1]

#: The fifteen command-bearing skills, in the deterministic order
#: ``collect_commands`` sorts them into. Pinned literally so a new or renamed
#: top-level skill has to be acknowledged here.
COMMAND_NAMES = (
    "datasets",
    "experiment-diagrams",
    "experimental-deliberation",
    "experimental-implementation",
    "figure-review",
    "hyperparameter-search",
    "kaggle-accounts",
    "math-tutor",
    "paper-ingestion",
    "paper-writing",
    "plausibility",
    "proposal-deliberation",
    "proposal-implementation",
    "remote-execution",
    "remote-parallelism",
    "skill-audit",
    "upgrade-project",
)

#: The twenty-five agent definitions, in the deterministic order
#: ``collect_pi_agents`` sorts them into. Pinned literally so a new or renamed
#: agent has to be acknowledged here -- and in the `.pi/agents/` projection
#: the Pi harness discovers.
AGENT_NAMES = (
    "audit-report",
    "contract-auditor",
    "dataset-curator",
    "dataset-scout",
    "deliberation-publish",
    "diagram-author",
    "experimental-publish",
    "experimental-validation",
    "experiments-build",
    "experiments-reviewer",
    "experiments-walk",
    "figure-auditor",
    "implementation-build",
    "implementation-walk",
    "insumos-observer",
    "math-tutor",
    "novelty-screener",
    "paper-ingestion",
    "paper-replicator",
    "paper-reviewer",
    "redactor",
    "section-grounding-auditor",
    "sota-grapher",
    "sota-scout",
    "style-sampler",
)


def _workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "paper"
    init_module.initialize(workspace, run_npm=False, run_env=False)
    return workspace


def _skill_description(workspace: Path, name: str) -> str:
    """Read a skill's ``description`` front-matter value independently of the
    generator's own parser, so the assertion is a cross-check, not a tautology."""
    lines = (workspace / "skills" / name / "SKILL.md").read_text(encoding="utf-8").splitlines()
    assert lines[0].strip() == "---"
    front: list[str] = []
    for line in lines[1:]:
        if line.strip() == "---":
            break
        front.append(line)
    return yaml.safe_load("\n".join(front))["description"]


class GeneratorsTests(unittest.TestCase):
    def new_tmp(self) -> Path:
        """Scratch directory, resolved -- see BridgesTests.new_tmp for why."""
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        return Path(holder.name).resolve()

    def test_generators_are_clean_after_init(self) -> None:
        workspace = _workspace(self.new_tmp())
        assert check_generated(workspace, tools=ALL_TOOLS) == []
        assert collect_commands(workspace, warnings=[]) == [
            {
                "name": name,
                "description": derive_command_description(_skill_description(workspace, name)),
            }
            for name in COMMAND_NAMES
        ]
        expected = {
            ".gitignore",
            "CLAUDE.md",
            "OPENCODE.md",
            ".pi/APPEND_SYSTEM.md",
            ".pi/gentle-ai/persona.json",
            ".agents/AGENTS.md",
            "opencode.json",
            ".opencode/plugins/refuse-offpath-push.js",
            ".pi/extensions/refuse-offpath-push.js",
        }
        expected |= {f".opencode/commands/{name}.md" for name in COMMAND_NAMES}
        expected |= {f".claude/commands/{name}.md" for name in COMMAND_NAMES}
        expected |= {f".pi/prompts/{name}.md" for name in COMMAND_NAMES}
        expected |= {f".pi/agents/{name}.md" for name in AGENT_NAMES}
        expected |= {f".opencode/agents/{name}.md" for name in AGENT_NAMES}
        expected |= {f".agents/agents/{name}.md" for name in AGENT_NAMES}
        assert set(render_files(workspace, tools=ALL_TOOLS)) == expected
        agents = collect_agents(workspace)
        assert any(agent["name"] == "paper-ingestion" for agent in agents)

    def test_command_derivation_is_scoped_to_the_command_tools(self) -> None:
        workspace = _workspace(self.new_tmp())
        # Counted off COMMAND_NAMES rather than restated as a literal: the
        # tuple above is the pin a new skill has to be acknowledged in, and a
        # second copy of its length is just a second place to forget.
        expected = len(COMMAND_NAMES)
        opencode = render_files(workspace, tools=("opencode",))
        assert sum(1 for path in opencode if path.startswith(".opencode/commands/")) == expected
        assert ".claude/commands/paper-ingestion.md" not in opencode
        claude = render_files(workspace, tools=("claude",))
        assert sum(1 for path in claude if path.startswith(".claude/commands/")) == expected
        assert ".opencode/commands/paper-ingestion.md" not in claude
        pi = render_files(workspace, tools=("pi",))
        assert sum(1 for path in pi if path.startswith(".pi/prompts/")) == expected
        assert ".pi/prompts/paper-ingestion.md" in pi
        assert not any(path.startswith((".opencode/commands/", ".claude/commands/")) for path in pi)
        # Antigravity reads the skills link and gets no command files of its own.
        antigravity = render_files(workspace, tools=("antigravity",))
        assert not any("/commands/" in path or "/prompts/" in path for path in antigravity)
        assert not any(path.startswith(".pi/prompts/") for path in (*opencode, *claude))

    def test_command_body_consumes_arguments_and_derives_description(self) -> None:
        workspace = _workspace(self.new_tmp())
        rendered = render_files(workspace, tools=("opencode",))[".opencode/commands/paper-ingestion.md"]
        head, _, body = rendered.partition("\n---\n")
        assert head.startswith("---\n")
        assert "description: " in head
        assert "$ARGUMENTS" in body
        assert "skills/paper-ingestion/SKILL.md" in body
        assert yaml_double_quote(
            derive_command_description(_skill_description(workspace, "paper-ingestion"))
        ) in head

    def test_pi_agent_projection_is_scoped_to_pi(self) -> None:
        workspace = _workspace(self.new_tmp())
        assert [agent["name"] for agent in collect_pi_agents(workspace, warnings=[])] == list(AGENT_NAMES)
        pi = render_files(workspace, tools=("pi",))
        assert sum(1 for path in pi if path.startswith(".pi/agents/")) == 25
        assert ".pi/agents/sota-scout.md" in pi
        assert not any(
            path.startswith(".pi/agents/")
            for path in render_files(workspace, tools=("claude",))
        )
        assert not any(
            path.startswith(".pi/agents/")
            for path in render_files(workspace, tools=("opencode",))
        )

    def test_opencode_agent_projection_is_scoped_to_opencode(self) -> None:
        workspace = _workspace(self.new_tmp())
        assert [a["name"] for a in collect_opencode_agents(workspace, warnings=[])] == list(AGENT_NAMES)
        opencode = render_files(workspace, tools=("opencode",))
        assert sum(1 for path in opencode if path.startswith(".opencode/agents/")) == 25
        assert ".opencode/agents/sota-scout.md" in opencode
        for tool in ("claude", "pi", "antigravity"):
            assert not any(
                path.startswith(".opencode/agents/")
                for path in render_files(workspace, tools=(tool,))
            ), tool

    def test_opencode_agent_translation_emits_permission_not_tools(self) -> None:
        workspace = _workspace(self.new_tmp())
        by_name = {a["name"]: a["text"] for a in collect_opencode_agents(workspace, warnings=[])}
        scout = by_name["sota-scout"]
        head, _, body = scout.partition("\n---\n")
        meta = yaml.safe_load(head.removeprefix("---\n"))
        assert set(meta) == {"description", "mode", "permission"}
        assert meta["mode"] == "subagent"
        assert meta["permission"]["websearch"] == "allow"
        assert meta["permission"]["webfetch"] == "allow"
        assert meta["permission"]["bash"] == "allow"
        assert meta["permission"]["edit"] == "allow"  # Write is granted to sota-scout
        assert ".claude/" not in scout
        assert "skills/plausibility/SKILL.md" in body

    def test_opencode_read_only_agents_get_no_edit_or_bash(self) -> None:
        workspace = _workspace(self.new_tmp())
        by_name = {a["name"]: a["text"] for a in collect_opencode_agents(workspace, warnings=[])}
        # redactor is declared `tools: Read, Glob, Grep` in the source.
        meta = yaml.safe_load(by_name["redactor"].split("\n---\n")[0].removeprefix("---\n"))
        permission = meta["permission"]
        assert permission["read"] == "allow"
        assert permission["glob"] == "allow" and permission["grep"] == "allow"
        for key in ("edit", "bash", "webfetch", "websearch", "task"):
            assert permission[key] == "deny", key

    def test_opencode_translation_maps_each_tool_least_privilege(self) -> None:
        def perms(tools: str) -> tuple[dict, list[str]]:
            source = f"---\nname: a\ndescription: d\ntools: {tools}\n---\nbody\n"
            entry, reason, notes = _translate_agent_for_opencode(source)
            assert reason is None and entry is not None
            head = entry["text"].split("\n---\n")[0].removeprefix("---\n")
            return yaml.safe_load(head)["permission"], notes

        permission, notes = perms("Read")
        assert permission["read"] == "allow" and notes == []
        assert {k for k, v in permission.items() if v == "allow"} == {"read"}
        permission, _ = perms("Edit")
        assert {k for k, v in permission.items() if v == "allow"} == {"edit"}
        permission, _ = perms("Write")
        assert {k for k, v in permission.items() if v == "allow"} == {"edit"}
        permission, _ = perms("Bash")
        assert {k for k, v in permission.items() if v == "allow"} == {"bash"}
        permission, _ = perms("WebFetch, WebSearch")
        assert {k for k, v in permission.items() if v == "allow"} == {"webfetch", "websearch"}
        permission, _ = perms("Glob")
        assert {k for k, v in permission.items() if v == "allow"} == {"glob", "list"}

    def test_opencode_unknown_tool_is_not_granted_and_warns(self) -> None:
        source = "---\nname: a\ndescription: d\ntools: Read, NotebookEdit\n---\nbody\n"
        entry, reason, notes = _translate_agent_for_opencode(source)
        assert reason is None and entry is not None
        assert any("NotebookEdit" in note for note in notes)
        head = entry["text"].split("\n---\n")[0].removeprefix("---\n")
        permission = yaml.safe_load(head)["permission"]
        assert {k for k, v in permission.items() if v == "allow"} == {"read"}
        assert "tools:" not in head and "notebookedit" not in head.lower()

    def test_opencode_unknown_tool_warning_reaches_the_sink(self) -> None:
        workspace = _workspace(self.new_tmp())
        path = workspace / ".claude" / "agents" / "extra.md"
        path.write_text("---\nname: extra\ndescription: d\ntools: Read, Mystery\n---\nb\n",
                        encoding="utf-8")
        sink: list[str] = []
        names = [a["name"] for a in collect_opencode_agents(workspace, warnings=sink)]
        assert "extra" in names
        assert any("extra" in w and "Mystery" in w for w in sink), sink

    def test_opencode_agent_projection_skips_unusable_definitions(self) -> None:
        workspace = _workspace(self.new_tmp())
        agents = workspace / ".claude" / "agents"
        (agents / "broken.md").write_text("no frontmatter\n", encoding="utf-8")
        (agents / "unclosed.md").write_text("---\nname: unclosed\n", encoding="utf-8")
        (agents / "nameless.md").write_text("---\ndescription: d\n---\nb\n", encoding="utf-8")
        (agents / "undescribed.md").write_text("---\nname: undescribed\n---\nb\n", encoding="utf-8")
        (agents / "unsafe.md").write_text("---\nname: ../evil\ndescription: d\n---\nb\n",
                                          encoding="utf-8")
        (agents / "binary.md").write_bytes(b"\xff\xfe\x00bad")
        (agents / "dir.md").mkdir()
        sink: list[str] = []
        names = [a["name"] for a in collect_opencode_agents(workspace, warnings=sink)]
        assert len(names) == 25
        for stem in ("broken", "unclosed", "nameless", "undescribed", "unsafe", "binary", "dir"):
            assert any(f"'{stem}'" in w for w in sink), (stem, sink)

    def test_opencode_agents_drift_and_regeneration(self) -> None:
        from papersmith.generators import apply_generated
        workspace = _workspace(self.new_tmp())
        target = workspace / ".opencode" / "agents" / "redactor.md"
        assert target.is_file()
        target.write_text("drift\n", encoding="utf-8")
        assert ".opencode/agents/redactor.md" in check_generated(workspace, tools=ALL_TOOLS)
        assert ".opencode/agents/redactor.md" in apply_generated(workspace, tools=ALL_TOOLS)
        assert check_generated(workspace, tools=ALL_TOOLS) == []

    def test_pi_extension_relay_is_scoped_to_pi_and_drift_checked(self) -> None:
        workspace = _workspace(self.new_tmp())
        relpath = ".pi/extensions/refuse-offpath-push.js"
        assert relpath in render_files(workspace, tools=("pi",))
        for tool in ("claude", "opencode", "antigravity"):
            assert relpath not in render_files(workspace, tools=(tool,)), tool
        text = render_files(workspace, tools=("pi",))[relpath]
        assert 'pi.on("tool_call"' in text
        assert "block: true" in text
        assert "refuse_offpath_push.py" in text
        assert "_load_push_surfaces" in text
        from papersmith.generators import apply_generated
        target = workspace / relpath
        assert target.is_file()
        target.write_text("drift\n", encoding="utf-8")
        assert relpath in check_generated(workspace, tools=ALL_TOOLS)
        assert relpath in apply_generated(workspace, tools=ALL_TOOLS)
        assert check_generated(workspace, tools=ALL_TOOLS) == []

    def test_antigravity_agent_projection_is_scoped_to_antigravity(self) -> None:
        workspace = _workspace(self.new_tmp())
        assert [a["name"] for a in collect_antigravity_agents(workspace, warnings=[])] == list(AGENT_NAMES)
        rendered = render_files(workspace, tools=("antigravity",))
        assert sum(1 for path in rendered if path.startswith(".agents/agents/")) == 25
        assert ".agents/agents/sota-scout.md" in rendered
        for tool in ("claude", "pi", "opencode"):
            assert not any(
                path.startswith(".agents/agents/")
                for path in render_files(workspace, tools=(tool,))
            ), tool

    def test_antigravity_agent_translation_shape(self) -> None:
        workspace = _workspace(self.new_tmp())
        by_name = {a["name"]: a["text"] for a in collect_antigravity_agents(workspace, warnings=[])}
        scout = by_name["sota-scout"]
        head, _, body = scout.partition("\n---\n")
        meta = yaml.safe_load(head.removeprefix("---\n"))
        assert set(meta) == {"name", "description", "tools", "commandExecutionPolicy"}
        assert "model" not in meta  # omitted: documented default is inherit
        assert meta["name"] == "sota-scout"
        assert {"search_web", "read_url_content", "run_command", "write_to_file"} <= set(meta["tools"])
        assert meta["commandExecutionPolicy"] == "sandbox"
        assert ".claude/" not in scout
        assert "skills/plausibility/SKILL.md" in body

    def test_antigravity_read_only_agents_get_no_edit_shell_or_off_policy(self) -> None:
        workspace = _workspace(self.new_tmp())
        by_name = {a["name"]: a["text"] for a in collect_antigravity_agents(workspace, warnings=[])}
        # redactor is declared `tools: Read, Glob, Grep` in the source.
        meta = yaml.safe_load(by_name["redactor"].split("\n---\n")[0].removeprefix("---\n"))
        assert set(meta["tools"]) == {"view_file", "find_by_name", "list_dir", "grep_search"}
        assert meta["commandExecutionPolicy"] == "off"

    def test_antigravity_translation_maps_each_tool_least_privilege(self) -> None:
        def tools(value: str) -> tuple[set[str], list[str]]:
            source = f"---\nname: a\ndescription: d\ntools: {value}\n---\nbody\n"
            entry, reason, notes = _translate_agent_for_antigravity(source)
            assert reason is None and entry is not None
            head = entry["text"].split("\n---\n")[0].removeprefix("---\n")
            return set(yaml.safe_load(head)["tools"]), notes

        assert tools("Read")[0] == {"view_file"}
        assert tools("Glob")[0] == {"find_by_name", "list_dir"}
        assert tools("Grep")[0] == {"grep_search"}
        assert tools("Write")[0] == {"write_to_file"}
        assert tools("Edit")[0] == {"replace_file_content", "multi_replace_file_content"}
        assert tools("Bash")[0] == {"run_command"}
        assert tools("WebSearch")[0] == {"search_web"}
        assert tools("WebFetch")[0] == {"read_url_content"}

    def test_antigravity_unknown_tool_is_not_granted_and_warns(self) -> None:
        source = "---\nname: a\ndescription: d\ntools: Read, NotebookEdit\n---\nbody\n"
        entry, reason, notes = _translate_agent_for_antigravity(source)
        assert reason is None and entry is not None
        assert any("NotebookEdit" in note for note in notes)
        head = entry["text"].split("\n---\n")[0].removeprefix("---\n")
        assert yaml.safe_load(head)["tools"] == ["view_file"]
        assert "notebookedit" not in head.lower()

    def test_antigravity_source_without_tools_line_grants_nothing(self) -> None:
        entry, reason, _ = _translate_agent_for_antigravity(
            "---\nname: a\ndescription: d\n---\nbody\n")
        assert reason is None and entry is not None
        meta = yaml.safe_load(entry["text"].split("\n---\n")[0].removeprefix("---\n"))
        assert "tools" not in meta  # documented default is the empty list
        assert meta["commandExecutionPolicy"] == "off"

    def test_antigravity_unknown_tool_warning_reaches_the_sink(self) -> None:
        workspace = _workspace(self.new_tmp())
        path = workspace / ".claude" / "agents" / "extra.md"
        path.write_text("---\nname: extra\ndescription: d\ntools: Read, Mystery\n---\nb\n",
                        encoding="utf-8")
        sink: list[str] = []
        names = [a["name"] for a in collect_antigravity_agents(workspace, warnings=sink)]
        assert "extra" in names
        assert any("extra" in w and "Mystery" in w for w in sink), sink

    def test_antigravity_agent_projection_skips_unusable_definitions(self) -> None:
        workspace = _workspace(self.new_tmp())
        agents = workspace / ".claude" / "agents"
        (agents / "broken.md").write_text("no frontmatter\n", encoding="utf-8")
        (agents / "unclosed.md").write_text("---\nname: unclosed\n", encoding="utf-8")
        (agents / "nameless.md").write_text("---\ndescription: d\n---\nb\n", encoding="utf-8")
        (agents / "undescribed.md").write_text("---\nname: undescribed\n---\nb\n", encoding="utf-8")
        (agents / "unsafe.md").write_text("---\nname: ../evil\ndescription: d\n---\nb\n",
                                          encoding="utf-8")
        (agents / "binary.md").write_bytes(b"\xff\xfe\x00bad")
        (agents / "dir.md").mkdir()
        sink: list[str] = []
        names = [a["name"] for a in collect_antigravity_agents(workspace, warnings=sink)]
        assert len(names) == 25
        for stem in ("broken", "unclosed", "nameless", "undescribed", "unsafe", "binary", "dir"):
            assert any(f"'{stem}'" in w for w in sink), (stem, sink)

    def test_antigravity_agents_drift_and_regeneration(self) -> None:
        from papersmith.generators import apply_generated
        workspace = _workspace(self.new_tmp())
        target = workspace / ".agents" / "agents" / "redactor.md"
        assert target.is_file()
        target.write_text("drift\n", encoding="utf-8")
        assert ".agents/agents/redactor.md" in check_generated(workspace, tools=ALL_TOOLS)
        assert ".agents/agents/redactor.md" in apply_generated(workspace, tools=ALL_TOOLS)
        assert check_generated(workspace, tools=ALL_TOOLS) == []

    def test_pi_agent_translation_maps_tools_and_skill_paths(self) -> None:
        workspace = _workspace(self.new_tmp())
        by_name = {agent["name"]: agent["text"] for agent in collect_pi_agents(workspace, warnings=[])}
        scout = by_name["sota-scout"]
        head, _, body = scout.partition("\n---\n")
        assert head.startswith("---\n")
        assert "name: sota-scout" in head
        assert "WebSearch" not in head and "WebFetch" not in head
        # pi-web-access supplies these names; the projection only declares tools,
        # and does not install the extension or change Pi's tool settings.
        assert "mcp" not in head and "websearch" not in head and "webfetch" not in head
        assert "  - web_search" in head and "  - fetch_content" in head
        assert "- read" in head and "- bash" in head
        assert ".claude/" not in scout
        assert "skills/plausibility/SKILL.md" in body
        # Domain metadata the skills read travels untouched.
        assert "description: " in head

    def test_pi_web_tools_map_to_pi_web_access_without_warnings(self) -> None:
        workspace = _workspace(self.new_tmp())
        sink: list[str] = []
        by_name = {a["name"]: a["text"] for a in collect_pi_agents(workspace, warnings=sink)}
        for name in ("sota-scout", "experimental-validation", "novelty-screener"):
            head = by_name[name].partition("\n---\n")[0]
            tools = yaml.safe_load(head.removeprefix("---\n"))["tools"]
            assert "web_search" in tools and "fetch_content" in tools, name
            assert not any(f"agent '{name}'" in w and "Web" in w for w in sink), sink

    def test_pi_unknown_non_web_tools_still_pass_through_lowercased(self) -> None:
        workspace = _workspace(self.new_tmp())
        path = workspace / ".claude" / "agents" / "custom.md"
        path.write_text(
            "---\nname: custom\ndescription: x\ntools: Read, NotebookEdit, WebSearch\n---\nbody\n",
            encoding="utf-8",
        )
        sink: list[str] = []
        by_name = {a["name"]: a["text"] for a in collect_pi_agents(workspace, warnings=sink)}
        head = by_name["custom"].partition("\n---\n")[0]
        assert "  - read\n  - notebookedit\n  - web_search" in head
        assert not any("NotebookEdit" in w or "WebSearch" in w for w in sink), sink

    def test_pi_legacy_tool_mapping_remains_unchanged(self) -> None:
        source = ("---\nname: legacy\ndescription: x\n"
                  "tools: Read, Glob, Grep, Write, Edit, Bash, WebFetch\n---\nbody\n")
        entry, reason, notes = _translate_agent_for_pi(source)
        assert reason is None and entry is not None and notes == []
        head = entry["text"].partition("\n---\n")[0]
        assert yaml.safe_load(head.removeprefix("---\n"))["tools"] == [
            "read", "find", "grep", "write", "edit", "bash", "fetch_content",
        ]

    def test_a_model_line_stays_in_the_claude_projection(self) -> None:
        """`.claude/agents` is copied, not rendered, so a source's `model:` line
        is already the Claude projection. No other harness here has a cited
        per-agent model mechanism, so each translator writes no model at all,
        whether the source names one or omits it."""
        named = ("---\nname: light\ndescription: d\ntools: Read, Glob, Grep\n"
                 "model: sonnet\n---\nbody\n")
        omitted = "---\nname: inherit\ndescription: d\ntools: Read, Glob, Grep\n---\nbody\n"
        for translate in (_translate_agent_for_pi, _translate_agent_for_opencode,
                          _translate_agent_for_antigravity):
            for source in (named, omitted):
                with self.subTest(translator=translate.__name__, source=source):
                    entry, reason, _ = translate(source)
                    assert reason is None and entry is not None
                    head = entry["text"].split("\n---\n")[0].removeprefix("---\n")
                    meta = yaml.safe_load(head)
                    assert "model" not in meta and "tier" not in meta, head
                    assert entry["text"].endswith("---\nbody\n")

    def test_the_pi_translator_drops_only_a_top_level_model_line(self) -> None:
        """A nested key that happens to be called `model` belongs to its parent
        mapping and survives; only the agent's own top-level `model:` goes."""
        source = ("---\nname: nested\ndescription: d\ntools: Read\nmodel: sonnet\n"
                  "metadata:\n  model: kept\n---\nbody\n")
        entry, reason, _ = _translate_agent_for_pi(source)
        assert reason is None and entry is not None
        meta = yaml.safe_load(entry["text"].split("\n---\n")[0].removeprefix("---\n"))
        assert "model" not in meta
        assert meta["metadata"] == {"model": "kept"}

    def test_the_claude_projection_carries_the_source_model_line_verbatim(self) -> None:
        workspace = _workspace(self.new_tmp())
        for name, expected in (("math-tutor", ["model: sonnet"]), ("sota-scout", [])):
            with self.subTest(agent=name):
                header = (workspace / ".claude" / "agents" / f"{name}.md").read_text(
                    encoding="utf-8").split("---\n", 2)[1]
                assert [line for line in header.splitlines()
                        if line.startswith("model:")] == expected

    def test_pi_agent_projection_skips_malformed_definitions(self) -> None:
        workspace = _workspace(self.new_tmp())
        (workspace / ".claude" / "agents" / "broken.md").write_text("no frontmatter\n", encoding="utf-8")
        sink: list[str] = []
        names = [agent["name"] for agent in collect_pi_agents(workspace, warnings=sink)]
        assert "broken" not in names
        assert any("broken" in warning for warning in sink), sink
        assert len(names) == 25

    def test_unsupported_runtime_generator_still_raises(self) -> None:
        workspace = _workspace(self.new_tmp())
        with self.assertRaisesRegex(UserError, "unsupported runtime generator"):
            render_files(workspace, tools=("nope",))

    def test_opencode_check_reports_drift_without_mutating(self) -> None:
        workspace = _workspace(self.new_tmp())
        output = workspace / "OPENCODE.md"
        original = output.read_bytes()
        output.write_bytes(b"drift\n")
        command = [sys.executable, str(ROOT / "scripts/gen-opencode.py"), "--root", str(workspace), "--check"]
        checked = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        assert checked.returncode == 3
        assert "OPENCODE.md" in checked.stdout
        assert output.read_bytes() == b"drift\n"

        generated = subprocess.run(command[:-1], cwd=ROOT, capture_output=True, text=True)
        assert generated.returncode == 0, generated.stderr
        assert output.read_bytes() == original

    def test_pi_generator_repairs_both_outputs(self) -> None:
        workspace = _workspace(self.new_tmp())
        (workspace / ".pi/APPEND_SYSTEM.md").write_text("tampered-body-7f3c", encoding="utf-8")
        (workspace / ".pi/gentle-ai/persona.json").write_text("{}", encoding="utf-8")
        command = [sys.executable, str(ROOT / "scripts/gen-pi.py"), "--root", str(workspace)]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        assert '"mode": "gentleman"' in (workspace / ".pi/gentle-ai/persona.json").read_text()
        assert "tampered-body-7f3c" not in (workspace / ".pi/APPEND_SYSTEM.md").read_text()

    def test_antigravity_check_is_exit_three_on_missing_output(self) -> None:
        workspace = _workspace(self.new_tmp())
        (workspace / ".agents/AGENTS.md").unlink()
        command = [
            sys.executable, str(ROOT / "scripts/gen-antigravity.py"),
            "--root", str(workspace), "--check",
        ]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        assert result.returncode == 3
        assert ".agents/AGENTS.md" in result.stdout


class CommandDerivationTests(unittest.TestCase):
    """``collect_commands`` is fail-soft: user state never hard-fails generation."""

    def new_tmp(self) -> Path:
        """Scratch directory, resolved -- see BridgesTests.new_tmp for why."""
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        return Path(holder.name).resolve()

    def _broken(self, workspace: Path, name: str, text: str) -> None:
        directory = workspace / "skills" / name
        directory.mkdir()
        (directory / "SKILL.md").write_text(text, encoding="utf-8")

    def test_clean_workspace_yields_every_skill_and_no_warning(self) -> None:
        workspace = _workspace(self.new_tmp())
        sink: list[str] = []
        assert [item["name"] for item in collect_commands(workspace, warnings=sink)] == list(COMMAND_NAMES)
        assert sink == []

    def test_underscore_shelf_and_nested_files_are_skipped_silently(self) -> None:
        workspace = _workspace(self.new_tmp())
        assert (workspace / "skills" / "_core").is_dir()
        nested = workspace / "skills" / "paper-ingestion" / "nested"
        nested.mkdir()
        (nested / "SKILL.md").write_text("---\nname: nested\ndescription: 'Trigger: x.'\n---\n", encoding="utf-8")
        sink: list[str] = []
        assert [item["name"] for item in collect_commands(workspace, warnings=sink)] == list(COMMAND_NAMES)
        assert sink == []

    def test_missing_skill_file_is_skipped_with_a_warning(self) -> None:
        workspace = _workspace(self.new_tmp())
        (workspace / "skills" / "ghost").mkdir()
        sink: list[str] = []
        assert [item["name"] for item in collect_commands(workspace, warnings=sink)] == list(COMMAND_NAMES)
        assert sink == ["skipping skill 'ghost': missing SKILL.md"]

    def test_malformed_frontmatter_is_skipped_never_raised(self) -> None:
        workspace = _workspace(self.new_tmp())
        self._broken(workspace, "broken", "# no front matter at all\n")
        sink: list[str] = []
        assert [item["name"] for item in collect_commands(workspace, warnings=sink)] == list(COMMAND_NAMES)
        assert sink == ["skipping skill 'broken': malformed front matter"]

    def test_mismatched_name_is_skipped(self) -> None:
        workspace = _workspace(self.new_tmp())
        self._broken(workspace, "mismatched", '---\nname: other\ndescription: "Trigger: x."\n---\n')
        sink: list[str] = []
        collect_commands(workspace, warnings=sink)
        assert sink == [
            "skipping skill 'mismatched': name 'other' does not match directory 'mismatched'"
        ]

    def test_missing_description_is_skipped(self) -> None:
        workspace = _workspace(self.new_tmp())
        self._broken(workspace, "undescribed", "---\nname: undescribed\n---\n")
        sink: list[str] = []
        collect_commands(workspace, warnings=sink)
        assert sink == ["skipping skill 'undescribed': missing description"]

    def test_manifest_declared_name_is_used_not_the_directory(self) -> None:
        workspace = _workspace(self.new_tmp())
        source = (workspace / "skills" / "paper-ingestion" / "SKILL.md").read_text(encoding="utf-8")
        assert "name: paper-ingestion" in source

    def test_no_sink_emits_exactly_one_aggregated_warning(self) -> None:
        workspace = _workspace(self.new_tmp())
        (workspace / "skills" / "ghost").mkdir()
        self._broken(workspace, "broken", "# nope\n")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            collect_commands(workspace)
        # One warning, not one per skip: Python's default filter dedupes by
        # (module, line), and every skip is emitted from the same line.
        assert len(caught) == 1
        message = str(caught[0].message)
        assert "skipping skill 'ghost': missing SKILL.md" in message
        assert "skipping skill 'broken': malformed front matter" in message

    def test_derive_command_description_takes_the_first_sentence(self) -> None:
        assert derive_command_description("Trigger: do a thing. Then do more.") == "Trigger: do a thing."
        assert derive_command_description("no boundary here") == "no boundary here"
        assert derive_command_description("  spaced\tout.\nmore ") == "spaced out."
        assert derive_command_description("Ends with a question? Yes.") == "Ends with a question?"

    def test_yaml_double_quote_round_trips_every_skill_description(self) -> None:
        workspace = _workspace(self.new_tmp())
        for name in COMMAND_NAMES:
            derived = derive_command_description(_skill_description(workspace, name))
            quoted = yaml_double_quote(derived)
            assert yaml.safe_load(f"description: {quoted}\n")["description"] == derived

    def test_yaml_double_quote_escapes_quotes_and_backslashes(self) -> None:
        assert yaml.safe_load("value: " + yaml_double_quote('a "b" c'))["value"] == 'a "b" c'
        assert yaml.safe_load("value: " + yaml_double_quote("a\\b"))["value"] == "a\\b"


class WorkspaceToolsResolverTests(unittest.TestCase):
    """Change B: one resolver decides which runtimes a workspace declares."""

    def new_tmp(self) -> Path:
        """Scratch directory, resolved -- see BridgesTests.new_tmp for why."""
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        return Path(holder.name).resolve()

    def _warned(self, workspace: Path) -> tuple[tuple[str, ...], list]:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            resolved = workspace_tools(workspace)
        return resolved, caught

    def test_declared_tool_set_is_returned_verbatim(self) -> None:
        workspace = self.new_tmp() / "paper"
        init_module.initialize(workspace, tools=("claude", "pi"), run_npm=False, run_env=False)
        assert workspace_tools(workspace) == ("claude", "pi")

    def test_absent_config_warns_once_and_falls_back(self) -> None:
        bare = self.new_tmp() / "bare"
        bare.mkdir()
        resolved, caught = self._warned(bare)
        assert resolved == ALL_TOOLS
        assert len(caught) == 1, "the resolver emits exactly one aggregated warning"
        assert "assuming all runtimes" in str(caught[0].message)

    def test_corrupt_config_warns_once_and_falls_back(self) -> None:
        workspace = _workspace(self.new_tmp())
        (workspace / ".papersmith" / "config.json").write_text("{not json", encoding="utf-8")
        resolved, caught = self._warned(workspace)
        assert resolved == ALL_TOOLS
        assert len(caught) == 1

    def test_non_utf8_config_warns_once_and_falls_back(self) -> None:
        workspace = _workspace(self.new_tmp())
        (workspace / ".papersmith" / "config.json").write_bytes(b"\xff\xfe not utf-8")
        resolved, caught = self._warned(workspace)
        assert resolved == ALL_TOOLS
        assert len(caught) == 1

    def test_unknown_tool_falls_back_because_validation_rejects_the_config(self) -> None:
        # A syntactically valid config naming an unknown runtime is already a
        # UserError from ``validate_config_json``, so it reaches the same
        # fallback rather than a separate "unknown tool" branch.
        workspace = _workspace(self.new_tmp())
        config_path = workspace / ".papersmith" / "config.json"
        data = json.loads(config_path.read_text(encoding="utf-8"))
        data["active_tools"] = ["nope"]
        config_path.write_text(json.dumps(data), encoding="utf-8")
        resolved, caught = self._warned(workspace)
        assert resolved == ALL_TOOLS
        assert len(caught) == 1

    def test_rendered_contribution_has_no_extra_and_no_missing_path(self) -> None:
        """Criterion 2: the single-authority equality, stated exactly.

        ``workspace_framework_files`` legitimately hashes the kit's files and the
        version marker too, so the claim is the union equality rather than a bare
        ``render_files`` comparison.
        """
        workspace = self.new_tmp() / "paper"
        init_module.initialize(workspace, tools=("claude",), run_npm=False, run_env=False)
        kit_root = resolve_and_validate()
        context = context_for_workspace(workspace)
        assert (
            set(manifest.workspace_framework_files(workspace, kit_root).keys())
            == set(manifest.kit_files(kit_root).keys())
            | set(render_files(workspace, context, workspace_tools(workspace)).keys())
            | {".papersmith/version"}
        )

    def test_the_two_argument_call_still_derives_its_own_context(self) -> None:
        workspace = _workspace(self.new_tmp())
        kit_root = resolve_and_validate()
        assert (manifest.workspace_framework_files(workspace, kit_root)
                == manifest.workspace_framework_files(
                    workspace, kit_root, context_for_workspace(workspace)))
