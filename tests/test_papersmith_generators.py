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
    collect_commands,
    context_for_workspace,
    derive_command_description,
    render_files,
    workspace_tools,
    yaml_double_quote,
)
from papersmith.kit import resolve_and_validate


ROOT = Path(__file__).resolve().parents[1]

#: The ten command-bearing skills, in the deterministic order
#: ``collect_commands`` sorts them into. Pinned literally so a new or renamed
#: top-level skill has to be acknowledged here.
COMMAND_NAMES = (
    "experimental-deliberation",
    "experimental-implementation",
    "figure-review",
    "kaggle-accounts",
    "paper-ingestion",
    "paper-writing",
    "proposal-deliberation",
    "proposal-implementation",
    "remote-execution",
    "skill-audit",
)


def _workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "paper"
    init_module.initialize(workspace, run_npm=False)
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
            ".antigravity/rules.md",
            "opencode.json",
            ".opencode/plugins/refuse-offpath-push.js",
        }
        expected |= {f".opencode/commands/{name}.md" for name in COMMAND_NAMES}
        expected |= {f".claude/commands/{name}.md" for name in COMMAND_NAMES}
        assert set(render_files(workspace, tools=ALL_TOOLS)) == expected
        # Pi's entrypoint is a system-prompt append it actually reads; the old
        # ``PI.md`` name was never a context-file candidate. The settings file
        # is seeded once by ``init`` (see the conditional-seed test in
        # ``test_papersmith_init``), not rendered, so it is asserted here as a
        # workspace file, not via ``render_files``.
        assert (workspace / ".pi/APPEND_SYSTEM.md").is_file()
        assert (workspace / ".pi/settings.json").is_file()
        assert not (workspace / "PI.md").exists()
        agents = collect_agents(workspace)
        assert any(agent["name"] == "paper-ingestion" for agent in agents)

    def test_command_derivation_is_scoped_to_the_command_tools(self) -> None:
        workspace = _workspace(self.new_tmp())
        opencode = render_files(workspace, tools=("opencode",))
        assert sum(1 for path in opencode if path.startswith(".opencode/commands/")) == 10
        assert ".claude/commands/paper-ingestion.md" not in opencode
        claude = render_files(workspace, tools=("claude",))
        assert sum(1 for path in claude if path.startswith(".claude/commands/")) == 10
        assert ".opencode/commands/paper-ingestion.md" not in claude
        assert not any(
            path.startswith(".opencode/commands/")
            for path in render_files(workspace, tools=("pi",))
        )
        assert not any(
            path.startswith(".opencode/commands/")
            for path in render_files(workspace, tools=("antigravity",))
        )

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

    def test_pi_generator_repairs_every_output(self) -> None:
        workspace = _workspace(self.new_tmp())
        (workspace / ".pi/APPEND_SYSTEM.md").write_text("drift", encoding="utf-8")
        (workspace / ".pi/gentle-ai/persona.json").write_text("{}", encoding="utf-8")
        command = [sys.executable, str(ROOT / "scripts/gen-pi.py"), "--root", str(workspace)]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        assert '"mode": "gentleman"' in (workspace / ".pi/gentle-ai/persona.json").read_text()
        assert "drift" not in (workspace / ".pi/APPEND_SYSTEM.md").read_text()

    def test_antigravity_check_is_exit_three_on_missing_output(self) -> None:
        workspace = _workspace(self.new_tmp())
        (workspace / ".antigravity/rules.md").unlink()
        command = [
            sys.executable, str(ROOT / "scripts/gen-antigravity.py"),
            "--root", str(workspace), "--check",
        ]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        assert result.returncode == 3
        assert ".antigravity/rules.md" in result.stdout


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
        init_module.initialize(workspace, tools=("claude", "pi"), run_npm=False)
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
        init_module.initialize(workspace, tools=("claude",), run_npm=False)
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
