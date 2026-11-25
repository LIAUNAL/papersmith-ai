"""Capability-roster drift: the MCP surface stays deliberate, never partial."""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

from papersmith.cli import build_parser
from papersmith.mcp import registry
from papersmith.mcp.server import catalog

REPO_ROOT = Path(__file__).resolve().parents[1]
PAPER_CLI = REPO_ROOT / "skills" / "paper-writing" / "scripts" / "paper_cli.py"
SKILL_SCRIPTS = REPO_ROOT / "skills" / "paper-writing" / "scripts"
sys.path.insert(0, str(SKILL_SCRIPTS))
import paper_cli  # noqa: E402


def _paper_cli_commands() -> tuple[str, ...]:
    tree = ast.parse(PAPER_CLI.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            getattr(target, "id", None) == "COMMANDS" for target in node.targets
        ):
            return tuple(ast.literal_eval(node.value))
    raise AssertionError("paper_cli.COMMANDS was not found")


def _cli_commands() -> tuple[str, ...]:
    parser = build_parser()
    action = next(
        candidate
        for candidate in parser._actions
        if isinstance(candidate, argparse._SubParsersAction)
    )
    return tuple(action.choices)


def _paper_cli_subparser(tokens: tuple[str, ...]) -> argparse.ArgumentParser:
    """Walk `paper_cli.build_parser()`'s nested `_SubParsersAction`s down a
    verb-token path — the same walk `_cli_commands()` uses at one level,
    carried through `bib build` / `mark revisions` / `mark class`."""
    parser = paper_cli.build_parser()
    for token in tokens:
        action = next(
            candidate
            for candidate in parser._actions
            if isinstance(candidate, argparse._SubParsersAction)
        )
        parser = action.choices[token]
    return parser


def _paper_build_plan(spec: registry.ToolSpec) -> tuple[tuple[str, ...], tuple[registry.Flag, ...]]:
    """The exact verb tokens and `Flag` tuple the tool's builder ships with.

    `_paper_builder(verb, flags)` captures both in its closure; the two
    module-level builders (`_build_readiness`, `_build_full_text`) close
    over nothing and read `_READINESS_FLAGS`/`_FULL_TEXT_FLAGS` globals,
    resolved here by identity against the registry surface they live in.
    """
    closure = spec.build.__closure__
    if closure:
        cells = [cell.cell_contents for cell in closure]
        tokens = next(
            value for value in cells
            if isinstance(value, tuple) and all(isinstance(item, str) for item in value)
        )
        flags = next(
            value for value in cells
            if isinstance(value, tuple) and all(isinstance(item, registry.Flag) for item in value)
        )
        return tokens, flags
    if spec.build is registry._build_readiness:
        return ("readiness",), registry._READINESS_FLAGS
    if spec.build is registry._build_full_text:
        return ("full_text",), registry._FULL_TEXT_FLAGS
    raise AssertionError(f"cannot derive the build plan for {spec.name}")


#: CLI-only option strings the paper subparsers accept but the MCP surface
#: deliberately does not spell, per tool name. The parity test pins exactly
#: this named difference rather than weakening to a subset check, so a flag
#: rename on either side still fails the suite. There is no registry-only
#: option in the other direction.
_PAPER_CLI_ONLY_FLAGS: dict[str, frozenset[str]] = {
    # `observe` omits the optional disk-truth reconciliation half of the CLI.
    "papersmith.paper_observe": frozenset({"--experiments", "--flow", "--implementation", "--proposals", "--protocol"}),
    # `declare` withholds the decline-with-condition surface and the
    # --sections override.
    "papersmith.paper_declare": frozenset({"--condition", "--decline", "--reason", "--sections"}),
    "papersmith.paper_bib_build": frozenset({"--guidance"}),
    "papersmith.paper_write": frozenset({"--grounding"}),
    "papersmith.paper_validate": frozenset({"--min-sources"}),
}


def test_registry_labels_match_the_real_paper_cli_roster() -> None:
    assert registry.PAPER_VERBS == _paper_cli_commands()


def test_registry_labels_match_the_real_cli_roster() -> None:
    assert set(registry.CLI_COMMANDS) == set(_cli_commands())


def test_every_paper_verb_has_a_disposition() -> None:
    assert set(registry.PAPER_DISPOSITIONS) == set(registry.PAPER_VERBS)


def test_every_cli_command_has_a_disposition() -> None:
    assert set(registry.CLI_DISPOSITIONS) == set(registry.CLI_COMMANDS)


def test_dispositions_use_only_the_declared_vocabulary() -> None:
    allowed = {"exposed", "deferred", "out"}
    assert set(registry.PAPER_DISPOSITIONS.values()) <= allowed
    assert set(registry.CLI_DISPOSITIONS.values()) <= allowed


def test_the_server_host_is_declared_out_not_exposed() -> None:
    assert registry.CLI_DISPOSITIONS["mcp"] == "out"
    assert not any(spec.verb == "mcp" for spec in registry.TOOLS)


def test_exposed_paper_tools_are_exactly_the_exposed_dispositions() -> None:
    exposed_tools = {spec.verb for spec in registry.TOOLS if spec.surface == "paper"}
    exposed_declared = {
        verb for verb, state in registry.PAPER_DISPOSITIONS.items() if state == "exposed"
    }
    assert exposed_tools == exposed_declared


def test_every_tool_name_is_namespaced_and_unique() -> None:
    names = [spec.name for spec in registry.TOOLS]
    assert len(names) == len(set(names))
    assert all(name.startswith("papersmith.") for name in names)


def test_every_input_schema_is_a_closed_object() -> None:
    for spec in registry.TOOLS:
        schema = spec.input_schema
        assert schema["type"] == "object", spec.name
        assert schema["additionalProperties"] is False, spec.name
        for required in schema.get("required", []):
            assert required in schema["properties"], spec.name


def test_every_tool_declares_all_four_annotation_hints() -> None:
    for spec in registry.TOOLS:
        for hint in ("readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint"):
            assert isinstance(spec.annotations[hint], bool), (spec.name, hint)


def test_read_only_and_destructive_are_never_both_true() -> None:
    for spec in registry.TOOLS:
        if spec.annotations["readOnlyHint"]:
            assert spec.annotations["destructiveHint"] is False, spec.name


def test_target_check_is_open_world_despite_being_read_only() -> None:
    spec = registry.TOOLS_BY_NAME["papersmith.target_check"]
    assert spec.annotations["readOnlyHint"] is True
    assert spec.annotations["openWorldHint"] is True


def test_paper_validate_is_exposed_but_never_read_only() -> None:
    # C1: `validate` appends evidence and can substitute the block body.
    spec = registry.TOOLS_BY_NAME["papersmith.paper_validate"]
    assert spec.annotations["readOnlyHint"] is False
    assert spec.annotations["destructiveHint"] is True
    assert registry.PAPER_DISPOSITIONS["validate"] == "exposed"


def test_paper_observe_is_exposed_read_only() -> None:
    spec = registry.TOOLS_BY_NAME["papersmith.paper_observe"]
    assert spec.annotations["readOnlyHint"] is True
    assert registry.PAPER_DISPOSITIONS["observe"] == "exposed"


def test_only_resolve_and_render_remain_deferred() -> None:
    deferred = {
        verb for verb, state in registry.PAPER_DISPOSITIONS.items() if state == "deferred"
    }
    # `resolve` reaches the network and caches metadata; `render` shells out to
    # latexmk. Both are named, never silently dropped.
    assert deferred == {"resolve", "render"}


def test_no_deferred_cli_command_remains() -> None:
    assert not [
        command
        for command, state in registry.CLI_DISPOSITIONS.items()
        if state == "deferred"
    ]
    assert registry.CLI_DISPOSITIONS["mcp"] == "out"


def test_catalog_tools_match_the_registry_order() -> None:
    assert [tool["name"] for tool in catalog()["tools"]] == [
        spec.name for spec in registry.TOOLS
    ]


def test_paper_tool_flags_match_the_cli_subparsers() -> None:
    """Flag-level parity between every paper `ToolSpec` and the real parser.

    The verb-name and disposition tests pin the roster, but nothing pinned
    the FLAGS a tool's builder spells against the option strings the CLI
    subparser accepts — so a rename on either side used to stay green while
    breaking the MCP tool at runtime. Every paper tool's flags must be
    exactly its subparser's option strings, no more and no less, with the
    sole sanctioned difference the CLI-only options withheld by name in
    `_PAPER_CLI_ONLY_FLAGS`.

    `spec.verb` is not enough to reach the subparser (both `bib build` and
    `mark revisions`/`mark class` nest), so the walk uses the verb tokens
    the tool's builder actually ships with.
    """
    for spec in (spec for spec in registry.TOOLS if spec.surface == "paper"):
        tokens, flags = _paper_build_plan(spec)
        subparser = _paper_cli_subparser(tokens)
        spelled = {flag.flag for flag in flags}
        accepted = {
            option
            for action in subparser._actions
            if not isinstance(action, (argparse._SubParsersAction, argparse._HelpAction))
            for option in action.option_strings
        }
        forgiven = _PAPER_CLI_ONLY_FLAGS.get(spec.name, frozenset())
        assert not (spelled - accepted), (
            f"{spec.name} spells flags its subparser does not accept: "
            f"{sorted(spelled - accepted)}"
        )
        assert accepted - spelled == forgiven, (
            f"{spec.name} subparser accepts options the tool does not spell "
            f"(beyond the named exceptions): {sorted(accepted - spelled - forgiven)}"
        )
