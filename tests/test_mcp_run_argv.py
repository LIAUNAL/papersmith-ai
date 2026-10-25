"""#59: positional arguments reach the child as positionals, and an omitted
`dry_run` produces the safe `--dry-run` argv the consent guard assumes.

Driven through the real server over stdio (`mcp_series`), so the assertion is
on what the child CLI actually parsed, not on an in-process plan. Before the
fix `papersmith.run {"profile": P}` spawned `run profile P` (the child read
the profile as `profile` and `P` as the workspace directory), an omitted
`dry_run` passed the guard as planning-only yet sent no `--dry-run`, and
`papersmith.remote` spawned `remote operation <op>`, which the child rejects.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcp_series import build_workspace, call_many, tool_call

from papersmith.mcp import registry

PROFILE = "smoke_and_invariants"


@pytest.fixture(scope="module")
def workspace(tmp_path_factory) -> Path:
    return build_workspace(tmp_path_factory.mktemp("mcp-run-argv"))


def _call(workspace: Path, name: str, arguments: dict) -> dict:
    return call_many(workspace, [tool_call(name, arguments)])[0]["result"]


def _jobs(result: dict) -> list[dict]:
    assert result["isError"] is False, result
    return json.loads(result["content"][0]["text"])["jobs"]


def test_run_profile_is_a_positional_and_omitted_dry_run_plans_only(workspace: Path) -> None:
    jobs = _jobs(_call(workspace, "papersmith.run", {"profile": PROFILE}))
    assert jobs and all(job["profile"] == PROFILE for job in jobs)
    assert all(job["dry_run"] is True for job in jobs)


def test_run_with_explicit_dry_run_true_plans_only(workspace: Path) -> None:
    jobs = _jobs(_call(workspace, "papersmith.run", {"profile": PROFILE, "dry_run": True}))
    assert all(job["profile"] == PROFILE and job["dry_run"] is True for job in jobs)


def test_an_option_like_profile_is_read_as_a_profile_name(workspace: Path) -> None:
    result = _call(workspace, "papersmith.run", {"profile": "--help"})
    text = result["content"][0]["text"]
    assert result["isError"] is True
    assert "usage:" not in text
    assert "--help" in text


def test_remote_operation_is_a_positional(workspace: Path) -> None:
    result = _call(workspace, "papersmith.remote", {"operation": "status"})
    text = result["content"][0]["text"]
    assert "invalid choice" not in text, text


def test_the_dry_run_default_is_one_declared_value() -> None:
    spec = registry.TOOLS_BY_NAME["papersmith.run"]
    assert spec.input_schema["properties"]["dry_run"]["default"] is True
    plan = spec.build({"profile": PROFILE}, Path("/ws"))
    assert plan.tokens == ("run", "--dry-run", "--", PROFILE)
    plan = spec.build({"profile": PROFILE, "dry_run": False, "consent": "t"}, Path("/ws"))
    assert plan.tokens == ("run", "--consent", "t", "--", PROFILE)


def test_extra_tokens_follow_the_workspace_directory_slot() -> None:
    spec = registry.TOOLS_BY_NAME["papersmith.implement"]
    plan = spec.build({"action": "status", "extra": ["--json", "x"]}, Path("/ws"))
    assert plan.tokens == ("implement", "--action", "status", "--", ".", "--json", "x")
