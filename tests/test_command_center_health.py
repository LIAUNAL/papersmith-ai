"""The wiring inspector reports what it can measure, and never guesses healthy."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from skills._core.command_center import health_inspector


def _skill(root: Path, name: str) -> None:
    directory = root / "skills" / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "SKILL.md").write_text(f"# {name}\n", encoding="utf-8")


def _agent(root: Path, name: str, *, skill: str, tools: str = "Read, Glob") -> None:
    directory = root / ".claude" / "agents"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{name}.md").write_text(
        "---\n"
        f"name: {name}\n"
        f"tools: {tools}\n"
        "stretch: write\n"
        "---\n\n"
        f"Skill: `.claude/skills/{skill}/SKILL.md`. Load it and follow it.\n",
        encoding="utf-8",
    )


class WiringInspectorTests(unittest.TestCase):
    def new_workspace(self) -> Path:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        root = Path(holder.name).resolve()
        return root

    def test_skill_manifests_report_missing_manifests(self) -> None:
        """Every skill directory is reported, and `core` means it ships a front door.

        This used to assert that a skill absent from the workspace was still
        reported as MISSING-and-core, which was the old hardcoded roster showing
        through. The roster is derived now, so what is not installed is not
        described. The signal that mattered survives one level down: a skill
        directory with no `SKILL.md` is still MISSING, and a workspace with no
        `skills/` at all raises a warning rather than an empty, healthy silence.
        """
        root = self.new_workspace()
        _skill(root, "paper-writing")
        (root / "skills" / "figure-review").mkdir(parents=True)  # no SKILL.md
        self._stub_cli(root, "paper-writing", "scripts/paper_cli.py")
        rows = health_inspector.skill_manifests(root)

        by_name = {row["name"]: row for row in rows}
        assert by_name["paper-writing"]["state"] == "WIRED"
        assert by_name["paper-writing"]["core"] is True
        assert by_name["figure-review"]["state"] == "MISSING"
        assert by_name["figure-review"]["core"] is False

    def test_agent_integrity_flags_an_unbound_tool(self) -> None:
        root = self.new_workspace()
        _skill(root, "paper-writing")
        _agent(root, "redactor", skill="paper-writing")
        _agent(root, "diagram-author", skill="paper-writing", tools="Read, Telepathy")

        rows = {row["name"]: row for row in health_inspector.agent_integrity(root)}

        assert rows["redactor"]["state"] == "WIRED"
        assert rows["diagram-author"]["state"] == "TOOL_UNBOUND"
        assert rows["diagram-author"]["unbound_tools"] == ["Telepathy"]

    def test_a_missing_required_agent_is_reported(self) -> None:
        root = self.new_workspace()
        _skill(root, "paper-writing")
        rows = {row["name"]: row for row in health_inspector.agent_integrity(root)}

        for required in health_inspector.REQUIRED_AGENTS:
            assert rows[Path(required).stem]["state"] == "MISSING"

    def test_agent_referencing_an_absent_skill_is_not_wired(self) -> None:
        root = self.new_workspace()
        _agent(root, "redactor", skill="paper-writing")

        rows = {row["name"]: row for row in health_inspector.agent_integrity(root)}

        assert rows["redactor"]["state"] == "MISSING"

    def test_structural_drift_detects_a_missing_harness(self) -> None:
        root = self.new_workspace()
        state, detail = health_inspector._structural_drift(root, "claude")

        assert state == "UNKNOWN"
        assert ".claude/" in detail

    def test_structural_drift_detects_command_parity_break(self) -> None:
        root = self.new_workspace()
        _skill(root, "paper-writing")
        claude = root / ".claude"
        (claude / "commands").mkdir(parents=True)
        (claude / "skills").mkdir()
        # skills/ has paper-writing but .claude/commands/ lists nothing.
        state, detail = health_inspector._structural_drift(root, "claude")

        assert state == "DRIFT_DETECTED"
        assert "paper-writing" in detail

    def test_structural_drift_accepts_a_consistent_projection(self) -> None:
        root = self.new_workspace()
        _skill(root, "paper-writing")
        for tool in ("claude", "opencode"):
            prefix = root / f".{tool}"
            (prefix / "commands").mkdir(parents=True)
            (prefix / "skills").mkdir()
            (prefix / "commands" / "paper-writing.md").write_text("x", encoding="utf-8")
        state, detail = health_inspector._structural_drift(root, "claude")

        assert state == "IN_SYNC", detail

    def _stub_cli(self, root: Path, skill: str, relative: str) -> None:
        script = root / "skills" / skill / relative
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text("import sys\nprint('usage')\nsys.exit(0)\n", encoding="utf-8")

    def _link_skills(self, root: Path, relpath: str) -> None:
        link = root / relpath
        link.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(os.path.relpath(root / "skills", link.parent), link)

    def _wire_all_harnesses(self, root: Path, names: list[str]) -> None:
        """Claude/OpenCode commands, Pi prompts, Antigravity's two skills links and no commands."""
        for harness in (".claude/commands", ".opencode/commands", ".pi/prompts"):
            (root / harness).mkdir(parents=True)
            for name in names:
                (root / harness / f"{name}.md").write_text("x", encoding="utf-8")
        for relpath in (".claude/skills", ".opencode/skills", ".pi/skills",
                        ".agents/skills"):
            self._link_skills(root, relpath)
        # Projected agents and the generated plugin/extension, wherever the
        # matrix says a tool has them (source agents are `.claude/agents`).
        for tool in ("opencode", "pi", "antigravity"):
            (root / health_inspector.agent_dir(tool)).mkdir(parents=True)
            (root / health_inspector.agent_dir(tool) / "redactor.md").write_text("x", encoding="utf-8")
        for tool in ("opencode", "pi"):
            plugin = root / health_inspector.plugin_file(tool)
            plugin.parent.mkdir(parents=True)
            plugin.write_text("x", encoding="utf-8")

    def test_structural_drift_reports_a_missing_agents_skills_link_for_antigravity(self) -> None:
        root = self.new_workspace()
        _skill(root, "paper-writing")
        (root / ".agents").mkdir()
        state, detail = health_inspector._structural_drift(root, "antigravity")

        assert state == "DRIFT_DETECTED"
        assert ".agents/skills" in detail

        self._link_skills(root, ".agents/skills")
        state, detail = health_inspector._structural_drift(root, "antigravity")
        assert state == "IN_SYNC", detail

    def test_structural_drift_expects_pi_prompts_not_commands(self) -> None:
        root = self.new_workspace()
        _skill(root, "paper-writing")
        self._link_skills(root, ".pi/skills")
        state, detail = health_inspector._structural_drift(root, "pi")
        assert state == "DRIFT_DETECTED"
        assert ".pi/prompts" in detail

        (root / ".pi" / "prompts").mkdir()
        (root / ".pi" / "prompts" / "paper-writing.md").write_text("x", encoding="utf-8")
        (root / ".pi" / "extensions").mkdir()
        (root / ".pi" / "extensions" / "refuse-offpath-push.js").write_text("x", encoding="utf-8")
        state, detail = health_inspector._structural_drift(root, "pi")
        assert state == "IN_SYNC", detail

    def _wired_structurally(self, root: Path, tool: str) -> None:
        """A structurally complete projection for ``tool`` (links, commands,
        agents, plugin) with one skill and one source agent."""
        _skill(root, "paper-writing")
        _agent(root, "redactor", skill="paper-writing")
        for relpath in health_inspector.required_skill_links(tool):
            self._link_skills(root, relpath)
        commands = health_inspector.COMMAND_DIRS.get(tool)
        if commands:
            target = root / health_inspector.HARNESSES[tool] / commands
            target.mkdir(parents=True, exist_ok=True)
            (target / "paper-writing.md").write_text("x", encoding="utf-8")
        agents = health_inspector.agent_dir(tool)
        if agents and tool != "claude":
            (root / agents).mkdir(parents=True, exist_ok=True)
            (root / agents / "redactor.md").write_text("x", encoding="utf-8")
        plugin = health_inspector.plugin_file(tool)
        if plugin:
            (root / plugin).parent.mkdir(parents=True, exist_ok=True)
            (root / plugin).write_text("x", encoding="utf-8")

    def test_structural_drift_requires_projected_agents_and_plugins(self) -> None:
        for tool in ("opencode", "pi", "antigravity", "claude"):
            with self.subTest(tool=tool):
                root = self.new_workspace()
                self._wired_structurally(root, tool)
                state, detail = health_inspector._structural_drift(root, tool)
                assert state == "IN_SYNC", detail
                agents = health_inspector.agent_dir(tool)
                if agents and tool != "claude":
                    (root / agents / "redactor.md").unlink()
                    state, detail = health_inspector._structural_drift(root, tool)
                    assert state == "DRIFT_DETECTED" and agents in detail, detail
                    (root / agents / "redactor.md").write_text("x", encoding="utf-8")
                plugin = health_inspector.plugin_file(tool)
                if plugin:
                    (root / plugin).unlink()
                    state, detail = health_inspector._structural_drift(root, tool)
                    assert state == "DRIFT_DETECTED" and plugin in detail, detail

    def test_structural_drift_ignores_agents_when_no_source_agents_exist(self) -> None:
        root = self.new_workspace()
        _skill(root, "paper-writing")
        self._link_skills(root, ".agents/skills")
        state, detail = health_inspector._structural_drift(root, "antigravity")
        assert state == "IN_SYNC", detail

    def test_harness_sync_does_not_penalise_a_tool_the_workspace_never_enabled(self) -> None:
        root = self.new_workspace()
        _skill(root, "paper-writing")
        (root / ".papersmith").mkdir()
        (root / ".papersmith" / "config.json").write_text(
            '{"active_tools": ["claude"]}', encoding="utf-8")
        (root / ".claude" / "commands").mkdir(parents=True)
        (root / ".claude" / "commands" / "paper-writing.md").write_text("x", encoding="utf-8")
        self._link_skills(root, ".claude/skills")

        sync = health_inspector.harness_sync(root)

        assert [row["tool"] for row in sync["harnesses"]] == ["claude"]
        assert sync["harnesses"][0]["state"] == "IN_SYNC", sync
        assert sync["state"] == "IN_SYNC"

    def test_harness_sync_covers_every_tool_without_a_workspace_config(self) -> None:
        root = self.new_workspace()
        sync = health_inspector.harness_sync(root)
        assert [row["tool"] for row in sync["harnesses"]] == list(health_inspector.HARNESSES)

    def test_full_payload_shape_on_a_fully_wired_workspace(self) -> None:
        root = self.new_workspace()
        # The roster is derived from the repository's own inventory, so this
        # workspace is stubbed with exactly what the repository ships a front
        # door for -- no restated list to drift from it.
        roster = health_inspector.front_door_skills(Path(__file__).resolve().parent.parent)
        core = [name for name, _ in roster]
        for name in core:
            _skill(root, name)
        for name, relative in roster:
            self._stub_cli(root, name, relative)
        for required in health_inspector.REQUIRED_AGENTS:
            _agent(root, Path(required).stem, skill="paper-writing")
        self._wire_all_harnesses(root, core)

        health = health_inspector.get_wiring_health(root)

        assert set(health) == {
            "generated_at", "summary", "harness_sync", "skills",
            "cli_entrypoints", "agents", "environment", "matrix",
        }
        assert health["summary"]["components_total"] == health["summary"]["components_healthy"], (
            health["summary"], health["harness_sync"], health["cli_entrypoints"]
        )
        assert health["summary"]["state"] == "HEALTHY"
        assert all(row["state"] == "WIRED" for row in health["cli_entrypoints"])
        assert all(row["state"] == "WIRED" for row in health["agents"])
        assert all(row["state"] == "IN_SYNC" for row in health["harness_sync"]["harnesses"])
        assert health["matrix"]

    def test_environment_reports_missing_packages_as_tool_missing(self) -> None:
        root = self.new_workspace()
        environment = health_inspector.environment_health(root)

        names = {row["name"] for row in environment["packages"]}
        assert names == set(health_inspector.REQUIRED_PACKAGES)
        assert all(row["state"] in ("WIRED", "TOOL_MISSING") for row in environment["packages"])
        assert environment["python"]["state"] == "WIRED"

    def test_the_repository_itself_reports_every_skill_wired(self) -> None:
        repository = Path(__file__).resolve().parent.parent
        rows = health_inspector.skill_manifests(repository)

        core = {row["name"]: row["state"] for row in rows if row["core"]}
        assert core, "the repository must expose its core skills"
        assert all(state == "WIRED" for state in core.values())
        # Derived, so the roster is whatever ships a front door today. The five
        # this repository used to hardcode were a subset of the seven it has.
        assert set(core) == {
            name for name, _ in health_inspector.front_door_skills(repository)
        }


class CliEntrypointConcurrencyTests(unittest.TestCase):
    def test_front_doors_are_probed_concurrently_in_roster_order(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        root = Path(holder.name).resolve()
        names = ["alpha", "beta", "gamma", "delta"]
        for name in names:
            scripts = root / "skills" / name / "scripts"
            scripts.mkdir(parents=True)
            (scripts / f"{name}_cli.py").write_text(
                "import time\ntime.sleep(0.6)\nprint('usage')\n", encoding="utf-8")
        import time
        started = time.monotonic()
        rows = health_inspector.cli_entrypoints(root)
        elapsed = time.monotonic() - started
        self.assertEqual([row["skill"] for row in rows], sorted(names))
        self.assertTrue(all(row["state"] == "WIRED" for row in rows))
        self.assertLess(elapsed, 0.6 * len(names) * 0.75)
