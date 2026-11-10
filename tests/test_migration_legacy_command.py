"""`smith upgrade` repoints MCP servers that still launch the removed `papersmith`.

From 0.2.0 to 0.18.x `smith mcp print-config` printed, and docs/mcp.md told
operators to paste, ``"command": "papersmith"``. The console script that name
ran is gone, so a pasted entry would fail to start with nothing in the
workspace saying why. Those three MCP files belong to the workspace
(``PRESERVE_PATTERNS``) and ``ensure_mcp_servers`` keeps every server it does
not manage, so only a migration can reach them: it rewrites the one field and
leaves every other server, key and argument as the operator wrote it.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from papersmith.core import fs, init as init_module, migrations as migrations_module
from papersmith.core import upgrade as upgrade_module
from papersmith.core.migrations import RetireLegacyCommand
from papersmith.generators import MCP_CONFIG_FILES

LEGACY = {"command": "papersmith", "args": ["mcp", "serve", "--workspace", "/srv/paper"]}
OTHER = {"command": "uvx", "args": ["some-server"]}


class RetireLegacyCommandTests(unittest.TestCase):
    def new_workspace(self) -> Path:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        root = Path(holder.name).resolve()
        (root / ".papersmith").mkdir(parents=True)
        return root

    def write(self, workspace: Path, relpath: str, data: object) -> Path:
        path = workspace / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        text = data if isinstance(data, str) else json.dumps(data, indent=2) + "\n"
        path.write_text(text, encoding="utf-8")
        return path

    def read(self, workspace: Path, relpath: str) -> dict:
        return json.loads((workspace / relpath).read_text(encoding="utf-8"))

    def test_every_harness_file_gets_its_legacy_server_repointed(self) -> None:
        workspace = self.new_workspace()
        for relpath in MCP_CONFIG_FILES.values():
            self.write(workspace, relpath,
                       {"mcpServers": {"papersmith": dict(LEGACY), "other": dict(OTHER)},
                        "theirs": {"kept": True}})
        migration = RetireLegacyCommand()

        planned = migration.plan(workspace)
        done, failures = migration.apply(workspace)

        assert failures == []
        assert len(planned) == len(MCP_CONFIG_FILES) == len(done)
        for relpath in MCP_CONFIG_FILES.values():
            assert any(relpath in action for action in planned), planned
            data = self.read(workspace, relpath)
            assert data["mcpServers"]["papersmith"] == {**LEGACY, "command": "smith"}
            assert data["mcpServers"]["other"] == OTHER
            assert data["theirs"] == {"kept": True}

    def test_a_renamed_server_that_launches_the_old_command_is_repointed_too(self) -> None:
        """The key was the operator's to rename; the binary it runs is what broke."""
        workspace = self.new_workspace()
        self.write(workspace, ".mcp.json", {"mcpServers": {"paper-tools": dict(LEGACY)}})

        RetireLegacyCommand().apply(workspace)

        assert self.read(workspace, ".mcp.json")["mcpServers"]["paper-tools"]["command"] == "smith"

    def test_a_converged_workspace_plans_nothing(self) -> None:
        workspace = self.new_workspace()
        assert RetireLegacyCommand().plan(workspace) == []
        self.write(workspace, ".mcp.json",
                   {"mcpServers": {"papersmith": {**LEGACY, "command": "smith"}, "other": OTHER}})
        assert RetireLegacyCommand().plan(workspace) == []

    def test_applying_twice_changes_nothing_the_second_time(self) -> None:
        workspace = self.new_workspace()
        path = self.write(workspace, ".mcp.json", {"mcpServers": {"papersmith": dict(LEGACY)}})
        migration = RetireLegacyCommand()

        migration.apply(workspace)
        once = path.read_bytes()

        assert migration.plan(workspace) == []
        assert path.read_bytes() == once

    def test_an_explicit_path_is_left_as_the_operator_wrote_it(self) -> None:
        """Only the bare name the old docs printed is known to mean the removed
        script; a path may be the operator's own wrapper."""
        workspace = self.new_workspace()
        path = self.write(workspace, ".mcp.json",
                          {"mcpServers": {"papersmith": {**LEGACY,
                                                         "command": "/opt/tools/papersmith"}}})
        before = path.read_bytes()

        assert RetireLegacyCommand().plan(workspace) == []
        assert path.read_bytes() == before

    def test_a_file_that_is_not_a_json_object_is_left_untouched_and_never_raises(self) -> None:
        workspace = self.new_workspace()
        broken = self.write(workspace, ".mcp.json", '{"mcpServers": {"papersmith": ')
        listed = self.write(workspace, ".pi/mcp.json", ["papersmith"])
        no_servers = self.write(workspace, ".agents/mcp_config.json", {"mcpServers": ["papersmith"]})
        before = {path: path.read_bytes() for path in (broken, listed, no_servers)}
        migration = RetireLegacyCommand()

        assert migration.plan(workspace) == []
        assert migration.apply(workspace) == ([], [])
        assert {path: path.read_bytes() for path in before} == before

    def test_a_write_that_fails_is_a_returned_failure_not_an_exception(self) -> None:
        workspace = self.new_workspace()
        self.write(workspace, ".mcp.json", {"mcpServers": {"papersmith": dict(LEGACY)}})

        with mock.patch.object(fs, "write_text", return_value=False):
            done, failures = RetireLegacyCommand().apply(workspace)

        assert done == []
        assert len(failures) == 1 and ".mcp.json" in failures[0]

    def test_it_ships_as_a_convergence_migration(self) -> None:
        """A gated migration can never both pass the registry rule and run
        (tests/test_papersmith_migrations.py); this one asks the files instead."""
        shipped = [entry for entry in migrations_module.REGISTRY
                   if isinstance(entry, RetireLegacyCommand)]
        assert len(shipped) == 1
        assert shipped[0].applies_from is None
        assert shipped[0].id == "mcp-legacy-papersmith-command"


class UpgradeRepointsTheLegacyCommandTests(unittest.TestCase):
    def workspace(self) -> Path:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        root = Path(holder.name).resolve() / "paper"
        init_module.initialize(root, run_npm=False, run_env=False)
        return root

    def test_a_fresh_workspace_has_nothing_to_repoint(self) -> None:
        assert RetireLegacyCommand().plan(self.workspace()) == []

    def test_smith_upgrade_repairs_an_entry_pasted_from_an_old_release(self) -> None:
        workspace = self.workspace()
        path = workspace / ".mcp.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["mcpServers"]["papersmith"] = dict(LEGACY)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

        result = upgrade_module.upgrade(workspace)

        servers = json.loads(path.read_text(encoding="utf-8"))["mcpServers"]
        assert servers["papersmith"] == {**LEGACY, "command": "smith"}
        applied = {entry["id"]: entry for entry in result["migrations"]["applied"]}
        assert applied["mcp-legacy-papersmith-command"]["failures"] == []


if __name__ == "__main__":
    unittest.main()
