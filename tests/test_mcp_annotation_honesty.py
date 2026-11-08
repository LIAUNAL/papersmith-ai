"""Success criterion #4: read-only means read-only, mutation-proven.

The first test proves the guard is load-bearing: it would catch a tool that is
annotated read-only and still writes. The second runs every read-only tool over
a real workspace and requires the tree to come back byte-identical.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from mcp_series import (
    build_workspace,
    call_many,
    scaffold_paper,
    tool_call,
    tree_hash,
)

from papersmith.mcp.registry import TOOLS

READ_ONLY = tuple(spec.name for spec in TOOLS if spec.annotations["readOnlyHint"])


@pytest.fixture(scope="module")
def workspace(tmp_path_factory) -> Path:
    ws = build_workspace(tmp_path_factory.mktemp("mcp-annotation-honesty"))
    scaffold_paper(ws)
    return ws


def test_the_tree_hash_guard_detects_a_mutation(workspace: Path) -> None:
    before = tree_hash(workspace)
    probe = workspace / "annotation-honesty-probe.txt"
    probe.write_text("x", encoding="utf-8")
    try:
        assert tree_hash(workspace) != before
    finally:
        probe.unlink()
    assert tree_hash(workspace) == before


def _files(root: Path) -> dict[str, str]:
    return {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(root.rglob("*")) if path.is_file()
            and "__pycache__" not in path.parts and path.suffix not in (".pyc", ".pyo")}


def test_every_read_only_tool_leaves_the_workspace_byte_identical(workspace: Path) -> None:
    assert READ_ONLY
    changed = []
    for index, name in enumerate(READ_ONLY):
        before = _files(workspace)
        call_many(workspace, [tool_call(name, request_id=index)])
        after = _files(workspace)
        paths = sorted(path for path in set(before) | set(after) if before.get(path) != after.get(path))
        if paths:
            changed.append(f"{name}: {', '.join(paths[:10])}")
    assert changed == [], "read-only tools changed the workspace: " + "; ".join(changed)
