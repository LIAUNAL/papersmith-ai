"""Subprocess bridge contracts and deliberation action aliases."""

from __future__ import annotations

import argparse
import ast
import contextlib
import io
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from papersmith.bridges import deliberation, implementation, node, python as python_bridge
from papersmith.core.exit_codes import EXECUTION_ERROR, SUCCESS, USER_ERROR, map_child_rc
from papersmith.errors import ExecutionError, UserError


ROOT = Path(__file__).resolve().parents[1]


ENGINE = ROOT / "skills/_core/implementation/engine/implementation_engine.py"


def _engine_commands() -> set[str]:
    """The engine's own `COMMANDS` keys, read from its source (the one
    conditional `**{...}` entry included), never listed here."""
    tree = ast.parse(ENGINE.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "COMMANDS"):
            for sub in ast.walk(node.value):
                if isinstance(sub, ast.Dict):
                    names.update(k.value for k in sub.keys
                                 if isinstance(k, ast.Constant))
    return names


def _implementation_args(**overrides):
    values = {
        "action": "materialize",
        "target": "implementations/paper",
        "name": "Paper",
        "plan": "plan.json",
        "finding": None,
        "entry_text": None,
        "python": None,
        "shards": None,
        "revision": None,
        "extra": [],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _deliberation_args(**overrides):
    values = {
        "request": None,
        "request_file": None,
        "action": "status",
        "instruction": None,
        "revision": None,
        "query": [],
        "selected_entry_id": [],
        "decisions": None,
        "accept": False,
        "acceptance_token": None,
        "withdrawal_operation_id": None,
        "withdrawal_reason": None,
        "prior_conclusion": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class BridgesTests(unittest.TestCase):
    def new_tmp(self) -> Path:
        """A scratch directory, RESOLVED.

        `python.run_script()` resolves the workspace it is given, because
        the path it builds is compared against the workspace elsewhere. On
        macOS `tempfile` hands out a path under `/var`, which is a symlink
        to `/private/var`, so an unresolved fixture and the production
        code's own answer are two spellings of one directory that compare
        unequal — and the test failed on a platform detail while the code
        under it was correct. Resolving here, rather than at each
        assertion, keeps that from being rediscovered per assertion.
        """
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        return Path(holder.name).resolve()

    def patch(self, target, attribute, value):
        patcher = mock.patch.object(target, attribute, value)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_child_exit_code_mapping(self) -> None:
        for child, expected in [(0, SUCCESS), (2, USER_ERROR), (1, EXECUTION_ERROR), (7, EXECUTION_ERROR)]:
            with self.subTest(child=child):
                assert map_child_rc(child) == expected

    def test_interpreter_falls_back_then_selects_project_micromamba(self) -> None:
        tmp_path = self.new_tmp()
        assert python_bridge.interpreter_for(tmp_path, prefer_micromamba=True)[0] != str(
            tmp_path / ".micromamba" / "bin" / "micromamba"
        )
        mamba = tmp_path / ".micromamba/bin/micromamba"
        mamba.parent.mkdir(parents=True)
        mamba.write_text("binary", encoding="utf-8")
        (tmp_path / ".micromamba/envs/papersmith").mkdir(parents=True)
        assert python_bridge.interpreter_for(tmp_path, prefer_micromamba=True) == [
            str(mamba), "run", "-n", "papersmith", "python"
        ]

    def test_run_script_forwards_list_argv_and_environment(self) -> None:
        tmp_path = self.new_tmp()
        script = tmp_path / "script.py"
        script.write_text("", encoding="utf-8")
        captured: dict[str, object] = {}

        def fake_run(command, **kwargs):
            captured["command"] = command
            captured["kwargs"] = kwargs
            return subprocess.CompletedProcess(command, 0, "ok", "")

        self.patch(python_bridge.subprocess, "run", fake_run)
        result = python_bridge.run_script(tmp_path, script, ["--flag", "value"], env={"PAPER": "1"})
        assert result.returncode == 0
        assert captured["command"][-3:] == [str(script), "--flag", "value"]
        assert captured["kwargs"]["env"]["PAPER"] == "1"
        assert captured["kwargs"]["cwd"] == tmp_path

    def test_missing_script_is_a_source_error(self) -> None:
        tmp_path = self.new_tmp()
        with self.assertRaisesRegex(Exception, "missing skill script"):
            python_bridge.run_script(tmp_path, "missing.py")

    def test_implementation_aliases_map_to_real_commands(self) -> None:
        command, args = implementation.command_args(_implementation_args())
        assert command == "apply"
        assert args == ["--target", "implementations/paper", "--name", "Paper", "--plan", "plan.json"]
        command, args = implementation.command_args(_implementation_args(action="benchmark", plan=None))
        assert command == "probe"
        assert "--target" in args and "--name" in args

    def test_implementation_validates_required_fields(self) -> None:
        with self.assertRaisesRegex(UserError, "requires --target"):
            implementation.command_args(_implementation_args(target=None))
        with self.assertRaisesRegex(UserError, "requires --plan"):
            implementation.command_args(_implementation_args(plan=None))

    def test_bridged_commands_are_engine_commands(self) -> None:
        engine = _engine_commands()
        self.assertTrue(engine)
        self.assertLessEqual(implementation.REAL_COMMANDS, engine)

    def test_unsupported_action_names_the_bridge_and_the_direct_route(self) -> None:
        with self.assertRaises(UserError) as caught:
            implementation.command_args(_implementation_args(action="position"))
        message = str(caught.exception)
        for command in implementation.REAL_COMMANDS:
            self.assertIn(command, message)
        self.assertIn("skills/proposal-implementation/scripts/implementation_cli.py position",
                      message)

    def test_materialize_alias_still_runs_apply_and_says_which_command_it_is(self) -> None:
        tmp_path = self.new_tmp()
        captured: dict[str, object] = {}

        def fake_run(root, script, argv):
            captured["argv"] = argv
            return subprocess.CompletedProcess(argv, 0, "", "")

        self.patch(implementation, "run_script", fake_run)
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            rc = implementation.execute(tmp_path, _implementation_args(action="materialize"))
        assert rc == SUCCESS
        assert captured["argv"][0] == "apply"
        note = stderr.getvalue()
        self.assertIn("--action apply", note)
        self.assertIn("materialize --stage", note)
        self.assertIn("implementation_cli.py", note)

        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            implementation.execute(tmp_path, _implementation_args(action="apply"))
        assert stderr.getvalue() == ""

    def test_readme_names_every_engine_command_the_bridge_does_not_run(self) -> None:
        # The CLI reference moved out of the README into docs/cli.md (#79).
        readme = (ROOT / "docs" / "cli.md").read_text(encoding="utf-8")
        start = readme.index("### `smith implement [<dir>]`")
        section = readme[start:readme.index("\n### ", start + 1)]
        for command in sorted(_engine_commands() - implementation.REAL_COMMANDS):
            self.assertIn(f"`{command}`", section)

    def test_deliberation_alias_request_shapes(self) -> None:
        assert deliberation.build_request(_deliberation_args(action="status")) == {"operation": "STATUS"}
        assert deliberation.build_request(_deliberation_args(
            action="init", instruction="A proposal idea"
        )) == {"operation": "CREATE_INITIAL_REVISION", "instruction": "A proposal idea"}
        assert deliberation.build_request(_deliberation_args(
            action="plan", revision="research-concept-r01.md", query=["Assumptions stationarity"]
        )) == {
            "operation": "RESOLVE_TARGET",
            "sourceFilename": "research-concept-r01.md",
            "query": "Assumptions stationarity",
        }
        assert deliberation.build_request(_deliberation_args(
            action="audit", instruction="audit this"
        )) == {"operation": "MAINTENANCE", "instruction": "audit this"}

    def test_raw_deliberation_request_is_not_reshaped(self) -> None:
        request = {"operation": "STATUS", "sourceFilename": "note.md"}
        args = _deliberation_args(request='{"operation":"STATUS","sourceFilename":"note.md"}', action=None)
        assert deliberation.build_request(args) == request

    def test_adopt_alias_names_the_source_it_adopts(self) -> None:
        expected = {"operation": "ADOPT_INITIAL_REVISION", "sourceFilename": "my-draft.md",
                    "instruction": "Adopt the draft."}
        for action in ("adopt", "ADOPT_INITIAL_REVISION"):
            with self.subTest(action=action):
                assert deliberation.build_request(_deliberation_args(
                    action=action, revision="my-draft.md", instruction="Adopt the draft.")) == expected

    def test_adopt_without_a_source_is_refused_before_the_engine(self) -> None:
        with self.assertRaisesRegex(UserError, "--revision is required for deliberate action adopt"):
            deliberation.build_request(_deliberation_args(action="adopt", instruction="Adopt the draft."))
        with self.assertRaisesRegex(UserError, "--instruction is required for deliberate action adopt"):
            deliberation.build_request(_deliberation_args(action="adopt", revision="my-draft.md"))

    def test_every_engine_operation_is_reachable_by_action(self) -> None:
        """The operation enum is read from the engine's own schema, never listed
        here, so an operation added to the engine without a bridge route fails."""
        source = (ROOT / "skills/_core/deliberation/engine/proposal-workspace.ts").read_text(encoding="utf-8")
        start = source.index("operation:Type.Optional(StringEnum([")
        listed = source[start:source.index("]", start)]
        operations = set(re.findall(r"'([A-Z_]+)'", listed))
        self.assertIn("ADOPT_INITIAL_REVISION", operations)
        self.assertEqual(operations - deliberation.REAL_OPERATIONS, set())

    @unittest.skipIf(
        shutil.which("node") is None or not (ROOT / "node_modules/jiti").is_dir(),
        reason="Node.js and jiti are required for the keyless engine smoke check",
    )
    def test_adopt_action_runs_the_engine_operation_end_to_end(self) -> None:
        root = self.new_tmp()
        (root / "skills").symlink_to(ROOT / "skills")
        (root / "node_modules").symlink_to(ROOT / "node_modules")
        (root / "proposals").mkdir()
        draft = "# Sampling under drift\n\n## Setting\n\nA sampler with bounded drift.\n"
        (root / "proposals" / "my-draft.md").write_text(draft, encoding="utf-8")
        args = _deliberation_args(action="adopt", revision="my-draft.md",
                                  instruction="Adopt the draft as v1.", serve=False)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = deliberation.execute(root, args)
        response = json.loads(out.getvalue())
        self.assertEqual(code, SUCCESS, out.getvalue())
        self.assertEqual(response["operation"], "ADOPT_INITIAL_REVISION")
        self.assertEqual(response["status"], "adopted")
        written = root / "proposals" / response["targetFilename"]
        self.assertTrue(written.is_file())
        self.assertEqual((root / "proposals" / "my-draft.md").read_text(encoding="utf-8"), draft)

    def test_deliberation_requires_instruction_for_mutating_alias(self) -> None:
        with self.assertRaisesRegex(UserError, "--instruction is required"):
            deliberation.build_request(_deliberation_args(action="init"))

    def test_node_missing_is_user_error(self) -> None:
        self.patch(node, "node_binary", lambda: None)
        with self.assertRaisesRegex(UserError, "node is required"):
            node.ensure_node_engine(self.new_tmp())

    @unittest.skipIf(
        shutil.which("node") is None or not (ROOT / "node_modules/jiti").is_dir(),
        reason="Node.js and jiti are required for the keyless engine smoke check",
    )
    def test_deliberation_status_uses_one_json_lines_engine(self) -> None:
        responses = node.call_engine(ROOT, [{"operation": "STATUS"}], timeout=60)
        assert len(responses) == 1
        assert responses[0]["status"] == "ok"
        assert responses[0]["operation"] == "STATUS"
