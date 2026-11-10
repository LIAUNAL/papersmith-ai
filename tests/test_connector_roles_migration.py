"""`smith upgrade` names Ai2's Asta in an existing workspace's roles, once.

`papersmith.yaml` belongs to the workspace and `upgrade` never rewrites it, so
a workspace made before this release keeps `resolution: openalex, crossref,
arxiv` forever unless a migration reaches it. Naming `asta` there changes
nothing until its key is set (a keyed connector without its key is skipped);
with the key, Asta is asked first. The migration edits only the block lists
the template seeded, keeps every other byte, and never overrules an operator
who removed `asta` afterwards.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from papersmith import yamllite
from papersmith.core import fs, init as init_module, migrations as migrations_module
from papersmith.core.migrations import AstaConnectorRoles

SKILL_SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "paper-writing" / "scripts"
sys.path.insert(0, str(SKILL_SCRIPTS))
import paper_resolve  # noqa: E402

OLD = """# workspace config
version: 1
paper_writing:
  contact: ""
  roles:
    discovery: []
    resolution:
      - openalex
      - crossref
      - arxiv
    full-text:
      - openalex
      - arxiv
# trailing comment kept
"""


class AstaConnectorRolesTests(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.root = Path(holder.name).resolve()
        (self.root / ".papersmith").mkdir()

    def write(self, text: str, *, newline: str = "\n") -> Path:
        path = self.root / "papersmith.yaml"
        path.write_bytes(text.replace("\n", newline).encode("utf-8"))
        return path

    def roles(self) -> dict:
        text = (self.root / "papersmith.yaml").read_bytes().decode("utf-8")
        return yamllite.loads(text.replace("\r\n", "\n"))["paper_writing"]["roles"]

    def test_the_seeded_lists_gain_asta_first_and_nothing_else_moves(self) -> None:
        self.write(OLD)
        migration = AstaConnectorRoles()

        assert len(migration.plan(self.root)) == 2
        done, failures = migration.apply(self.root)

        assert failures == [] and len(done) == 2
        text = (self.root / "papersmith.yaml").read_text(encoding="utf-8")
        assert text == OLD.replace("    discovery: []\n", "    discovery:\n      - asta\n").replace(
            "    resolution:\n", "    resolution:\n      - asta\n")
        assert self.roles() == {"discovery": ["asta"], "resolution": ["asta", "openalex", "crossref", "arxiv"],
                                "full-text": ["openalex", "arxiv"]}
        # The skill's own reader agrees with the orchestrator's.
        parsed = paper_resolve.parse_yaml_subset(text)
        assert parsed["paper_writing"]["roles"]["resolution"][0] == "asta"

    def test_crlf_line_endings_survive(self) -> None:
        self.write(OLD, newline="\r\n")
        AstaConnectorRoles().apply(self.root)
        raw = (self.root / "papersmith.yaml").read_bytes()
        assert b"\r\n      - asta\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b"")

    def test_it_runs_once_and_never_overrules_a_later_removal(self) -> None:
        self.write(OLD)
        migration = AstaConnectorRoles()
        migration.apply(self.root)
        assert migration.plan(self.root) == []
        self.write(OLD)  # the operator took asta out again
        assert migration.plan(self.root) == []

    def test_a_customized_list_is_left_exactly_as_written_and_reported_once(self) -> None:
        custom = OLD.replace("      - crossref\n", "")
        path = self.write(custom)
        migration = AstaConnectorRoles()

        planned = migration.plan(self.root)
        done, failures = migration.apply(self.root)

        assert any("by hand" in action for action in planned)
        assert failures == []
        assert any("customized" in line for line in done)
        assert path.read_text(encoding="utf-8").count("- asta") == 1  # discovery only
        assert migration.plan(self.root) == []

    def test_a_list_that_already_names_asta_is_left_alone(self) -> None:
        path = self.write(OLD.replace("    resolution:\n", "    resolution:\n      - asta\n")
                          .replace("    discovery: []\n", "    discovery:\n      - asta\n"))
        before = path.read_bytes()
        assert AstaConnectorRoles().plan(self.root) == []
        assert path.read_bytes() == before

    def test_no_config_or_no_roles_block_plans_nothing(self) -> None:
        assert AstaConnectorRoles().plan(self.root) == []
        self.write("version: 1\npaper_writing:\n  contact: \"\"\n")
        assert AstaConnectorRoles().plan(self.root) == []

    def test_a_write_that_fails_is_a_returned_failure(self) -> None:
        path = self.write(OLD)
        with mock.patch.object(fs, "replace_bytes", return_value=False):
            done, failures = AstaConnectorRoles().apply(self.root)
        assert done == [] and len(failures) == 1
        assert path.read_text(encoding="utf-8") == OLD
        assert not (self.root / ".papersmith" / "connector-roles.json").exists()

    def test_it_ships_as_convergence_and_a_fresh_workspace_needs_nothing(self) -> None:
        shipped = [m for m in migrations_module.REGISTRY if isinstance(m, AstaConnectorRoles)]
        assert len(shipped) == 1 and shipped[0].applies_from is None
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        workspace = Path(holder.name).resolve() / "paper"
        init_module.initialize(workspace, run_npm=False, run_env=False)
        assert AstaConnectorRoles().plan(workspace) == []


class ReplaceBytesTests(unittest.TestCase):
    def test_an_atomic_replace_keeps_the_mode_and_never_raises(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        path = Path(holder.name) / "file.txt"
        path.write_text("old", encoding="utf-8")
        path.chmod(0o640)
        assert fs.replace_bytes(path, b"new\r\n") is True
        assert path.read_bytes() == b"new\r\n"
        assert (path.stat().st_mode & 0o777) == 0o640
        assert fs.replace_bytes(Path(holder.name) / "missing-dir" / "x", b"y") is False


if __name__ == "__main__":
    unittest.main()
