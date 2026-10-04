"""Workspace initialization tests against the real repository kit."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from papersmith.cli import main
from papersmith.core import config, init as init_module, manifest
from papersmith.kit import resolve_and_validate
from papersmith.errors import UserError
from papersmith.yamllite import loads


class InitTests(unittest.TestCase):
    def new_tmp(self) -> Path:
        """Scratch directory, resolved -- see BridgesTests.new_tmp for why."""
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        return Path(holder.name).resolve()

    def test_initialize_creates_the_workspace_contract(self) -> None:
        tmp_path = self.new_tmp()
        workspace = tmp_path / "sparse-ae"
        result = init_module.initialize(
            workspace,
            title="Sparse Autoencoder Audit",
            topic="mechanistic interpretability",
            tools=("claude", "opencode", "pi", "antigravity"),
            remote="kaggle",
            run_npm=False,
        )

        assert result["name"] == "sparse-ae"
        # Derived, not restated. This read `== "0.1.0"` and passed for more
        # than a thousand commits because the version never moved; the first
        # real bump broke it, which is what a copied literal always does
        # eventually. What the test means is that init records the version
        # the kit carries, so it asks the kit.
        assert result["version"] == manifest.kit_version(resolve_and_validate())
        assert result["default_target"] == "kaggle-gpu-pool"
        for relpath in (
            ".papersmith/version",
            ".papersmith/manifest.json",
            ".papersmith/config.json",
            ".papersmith/runs_ledger.jsonl",
            ".claude/agents/paper-ingestion.md",
            "skills/paper-ingestion/SKILL.md",
            "skills/proposal-deliberation/cli.mjs",
            "skills/kaggle-accounts/store/.gitignore",
            "scripts/setup-harnesses.sh",
            "sections/01-materials-and-methods.md",
            "guidance/paper-guide",
            "guidance/reference-papers",
            "guidance/data-paper",
            "proposals",
            "paper",
            "experiments",
            "implementations",
            "kaggle-inbox",
            "papersmith.yaml",
            "package.json",
            "README.md",
            "CLAUDE.md",
            "OPENCODE.md",
            ".pi/APPEND_SYSTEM.md",
            ".pi/settings.json",
            ".pi/gentle-ai/persona.json",
            ".antigravity/rules.md",
            ".gitignore",
        ):
            assert (workspace / relpath).exists(), relpath

        # The old nested proposals/ shape and the journal/DECISIONS.md pair are
        # both gone: this repository's own layout is flat and keeps no journal.
        assert not (workspace / "proposals/drafts").exists()
        assert not (workspace / "proposals/deliberated").exists()
        assert not (workspace / "proposals/receipts").exists()
        assert not (workspace / "journal").exists()
        assert not (workspace / "DECISIONS.md").exists()
        assert (workspace / "proposals/.gitkeep").exists()

        # Credentials are never copied from the kit store.
        assert not (workspace / "skills/kaggle-accounts/store/accounts.json").exists()
        assert "paper-ingestion" in (workspace / "CLAUDE.md").read_text(encoding="utf-8")
        assert "mechanistic interpretability" in (workspace / "OPENCODE.md").read_text(encoding="utf-8")
        assert json.loads((workspace / ".pi/gentle-ai/persona.json").read_text()) == {"mode": "gentleman"}

        yaml = config.load_papersmith_yaml(workspace)
        assert yaml["name"] == "sparse-ae"
        assert yaml["title"] == "Sparse Autoencoder Audit"
        assert yaml["topic"] == "mechanistic interpretability"
        assert yaml["paper_ingestion"]["mode"] == "fast"
        assert yaml["compute_targets"]["default"] == "kaggle-gpu-pool"
        assert set(yaml["execution_profiles"]) == {
            "smoke_and_invariants", "sweep_training", "benchmark_evaluation"
        }

        cfg = config.load_workspace_config(workspace)
        assert cfg["project_name"] == "sparse-ae"
        assert cfg["active_tools"] == ["claude", "opencode", "pi", "antigravity"]
        assert cfg["execution_engine"]["active_compute_target"] == "kaggle-gpu-pool"

        stored_manifest = json.loads((workspace / ".papersmith/manifest.json").read_text())
        assert stored_manifest["kind"] == "workspace"
        assert stored_manifest["version"] == manifest.kit_version(resolve_and_validate())
        expected = manifest.workspace_framework_files(workspace, Path(__file__).parents[1])
        assert stored_manifest["files"] == expected

    def test_remote_selects_the_declared_default_target(self) -> None:
        tmp_path = self.new_tmp()
        for remote, target in [
            ("local", "local-workstation"),
            ("kaggle", "kaggle-gpu-pool"),
            ("slurm", "slurm-cluster"),
        ]:
            with self.subTest(remote=remote):
                workspace = tmp_path / remote
                init_module.initialize(workspace, remote=remote, run_npm=False)
                data = config.load_papersmith_yaml(workspace)
                assert data["compute_targets"]["default"] == target
                cfg = config.load_workspace_config(workspace)
                assert cfg["execution_engine"]["active_compute_target"] == target

    def test_pi_settings_seed_is_conditional_on_the_declared_tool_set(self) -> None:
        """The seed is written only when ``pi`` is declared, and preserved once written.

        ``.pi/settings.json`` is the one thing that lets Pi discover the
        canonical ``skills/`` tree; a workspace that never declares ``pi`` must
        not carry it, so a later audit has nothing to call surplus.
        """
        tmp_path = self.new_tmp()
        without_pi = tmp_path / "without-pi"
        init_module.initialize(without_pi, tools=("claude",), run_npm=False)
        assert not (without_pi / ".pi/settings.json").exists()

        with_pi = tmp_path / "with-pi"
        init_module.initialize(with_pi, tools=("claude", "pi"), run_npm=False)
        rendered = json.loads((with_pi / ".pi/settings.json").read_text(encoding="utf-8"))
        assert rendered == {"skills": ["../skills"]}

    def test_initialize_rejects_unknown_tools(self) -> None:
        tmp_path = self.new_tmp()
        with self.assertRaisesRegex(UserError, "unsupported runtime"):
            init_module.initialize(tmp_path / "paper", tools=("claude", "wat"), run_npm=False)

    def test_initialize_rejects_nonempty_destination(self) -> None:
        tmp_path = self.new_tmp()
        workspace = tmp_path / "paper"
        workspace.mkdir()
        (workspace / "notes.md").write_text("keep")
        with self.assertRaisesRegex(UserError, "must be empty"):
            init_module.initialize(workspace, run_npm=False)

    def test_cli_init_routes_flags_and_prints_summary(self) -> None:
        tmp_path = self.new_tmp()
        workspace = tmp_path / "cli-paper"
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            assert main([
                "init", str(workspace), "--title", "CLI Paper", "--topic", "testing",
                "--tools", "claude,pi", "--remote", "local", "--no-npm",
            ]) == 0
        output = buffer.getvalue()
        assert "Initialized papersmith workspace" in output
        assert config.load_workspace_config(workspace)["active_tools"] == ["claude", "pi"]

    def test_generated_yaml_is_parseable_without_third_party_yaml(self) -> None:
        tmp_path = self.new_tmp()
        workspace = tmp_path / "paper"
        init_module.initialize(workspace, run_npm=False)
        parsed = loads((workspace / "papersmith.yaml").read_text(encoding="utf-8"))
        assert parsed["execution_profiles"]["sweep_training"]["sharding"]["values"] == [
            42, 1337, 2026, 9999
        ]
