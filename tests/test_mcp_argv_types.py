"""#59 refinement: argument values are checked against the declared schema
before any argv exists, and `paper_contract --file` stays inside the workspace.

Driven through the real server over stdio (`mcp_series`). Before the fix the
server checked only unknown and missing names: a string `"false"` for a
boolean was truthy and became `--force`, any wrong-typed value was
stringified into argv and spawned a child, and `paper_contract`'s `file` was
handed to the child unresolved, so it read any path on the machine.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_series import build_workspace, call_many, scaffold_paper, tool_call, tree_hash

from papersmith.mcp.registry import TOOLS

SECRET = "outside-the-workspace-marker"

_WRONG = {"string": 123, "boolean": "false", "integer": "1", "array": "x"}


@pytest.fixture(scope="module")
def workspace(tmp_path_factory) -> Path:
    ws = build_workspace(tmp_path_factory.mktemp("mcp-argv-types"))
    scaffold_paper(ws)
    return ws


def _refusal(response: dict) -> dict:
    result = response["result"]
    assert result["isError"] is True, result
    return result["structuredContent"]


def test_mcp_boolean_arguments_reject_string_false(workspace: Path) -> None:
    before = tree_hash(workspace)
    responses = call_many(
        workspace, [tool_call("papersmith.workspace_upgrade", {"force": "false"})]
    )
    refusal = _refusal(responses[0])
    assert refusal["code"] == "INVALID_ARGUMENT"
    assert "force" in refusal["detail"] and "boolean" in refusal["detail"]
    assert "exit" not in refusal  # no child ran
    assert tree_hash(workspace) == before


def test_mcp_invalid_argument_types_do_not_execute(workspace: Path) -> None:
    calls = []
    for spec in TOOLS:
        properties = spec.input_schema.get("properties", {})
        if not properties:
            continue
        name, declared = next(iter(properties.items()))
        calls.append((spec.name, name, {name: _WRONG[declared["type"]]}))
    before = tree_hash(workspace)
    responses = call_many(
        workspace,
        [tool_call(tool, arguments, request_id=i + 1) for i, (tool, _, arguments) in enumerate(calls)],
    )
    for (tool, name, _), response in zip(calls, responses):
        refusal = _refusal(response)
        assert refusal["code"] == "INVALID_ARGUMENT", (tool, refusal)
        assert name in refusal["detail"], (tool, refusal)
        assert "exit" not in refusal, (tool, refusal)
    assert tree_hash(workspace) == before


def test_paper_contract_file_is_confined(workspace: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside.md"
    outside.write_text(SECRET + "\n", encoding="utf-8")
    link = workspace / "escape-link.md"
    link.symlink_to(outside)
    relative = Path("..") / ".." / outside.relative_to(outside.parents[1])
    try:
        attempts = [str(outside), str(Path("..") / relative), link.name]
        responses = call_many(
            workspace,
            [
                tool_call("papersmith.paper_contract", {"file": raw}, request_id=i + 1)
                for i, raw in enumerate(attempts)
            ],
        )
    finally:
        link.unlink()
    for raw, response in zip(attempts, responses):
        refusal = _refusal(response)
        assert refusal["code"] == "WORKSPACE_ESCAPE", (raw, refusal)
        assert "exit" not in refusal, (raw, refusal)
        assert SECRET not in response["result"]["content"][0]["text"]


def test_paper_contract_file_inside_the_workspace_still_parses(workspace: Path) -> None:
    section = sorted((workspace / "sections").glob("*.md"))[0]
    relative = section.relative_to(workspace).as_posix()
    responses = call_many(
        workspace, [tool_call("papersmith.paper_contract", {"file": relative})]
    )
    result = responses[0]["result"]
    assert result["isError"] is False, result
    assert result["structuredContent"]["section"] == "materials-and-methods"
