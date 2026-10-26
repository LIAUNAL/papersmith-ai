"""Read-only tools answer, and a skill refusal keeps its own name."""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_series import build_workspace, call_many, scaffold_paper, tool_call

READ_ONLY_OK = (
    "papersmith.workspace_status",
    "papersmith.workspace_audit",
    "papersmith.workspace_doctor",
    "papersmith.target_list",
    "papersmith.target_check",
    "papersmith.paper_status",
    "papersmith.paper_contract",
    "papersmith.paper_readiness",
    "papersmith.paper_order",
    "papersmith.paper_plan",
)


@pytest.fixture(scope="module")
def workspace(tmp_path_factory) -> Path:
    ws = build_workspace(tmp_path_factory.mktemp("mcp-tools"))
    scaffold_paper(ws)
    return ws


def test_read_only_tools_all_answer_without_error(workspace: Path) -> None:
    responses = call_many(
        workspace, [tool_call(name, request_id=index) for index, name in enumerate(READ_ONLY_OK)]
    )
    for name, response in zip(READ_ONLY_OK, responses):
        result = response["result"]
        assert result["isError"] is False, (name, result)
        assert result["resultType"] == "complete"
        assert result["content"][0]["type"] == "text"
        assert result["content"][0]["text"].strip()


def test_status_tool_returns_structured_content(workspace: Path) -> None:
    responses = call_many(workspace, [tool_call("papersmith.workspace_status")])
    structured = responses[0]["result"]["structuredContent"]
    assert "workspace" in structured
    assert "framework" in structured


def test_paper_tools_return_the_cli_json_envelope(workspace: Path) -> None:
    responses = call_many(workspace, [tool_call("papersmith.paper_status")])
    assert responses[0]["result"]["structuredContent"]["status"] == "ok"


def test_a_skill_refusal_keeps_its_verbatim_code(workspace: Path) -> None:
    responses = call_many(workspace, [tool_call("papersmith.paper_verify")])
    result = responses[0]["result"]
    assert result["isError"] is True
    assert result["structuredContent"]["code"] == "DECLARATION_RECORD_ABSENT"
    assert result["structuredContent"]["mapped"] == "USER_ERROR"
    assert "SOURCE_ERROR" not in result["content"][0]["text"]


def test_unknown_tool_is_a_protocol_error(workspace: Path) -> None:
    responses = call_many(workspace, [tool_call("papersmith.absent")])
    assert responses[0]["error"]["code"] == -32602
    assert responses[0]["error"]["data"]["code"] == "UNKNOWN_TOOL"


def test_missing_required_argument_is_refused_before_spawning(workspace: Path) -> None:
    responses = call_many(workspace, [tool_call("papersmith.target_set", {})])
    result = responses[0]["result"]
    assert result["isError"] is True
    assert result["structuredContent"]["code"] == "MISSING_ARGUMENT"


def test_unknown_argument_is_refused_before_spawning(workspace: Path) -> None:
    responses = call_many(
        workspace, [tool_call("papersmith.workspace_status", {"nonsense": True})]
    )
    result = responses[0]["result"]
    assert result["isError"] is True
    assert result["structuredContent"]["code"] == "UNKNOWN_ARGUMENT"


def test_absent_arguments_object_defaults_to_empty(workspace: Path) -> None:
    message = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "papersmith.workspace_status"},
    }
    responses = call_many(workspace, [message])
    assert responses[0]["result"]["isError"] is False
