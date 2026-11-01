"""Workspace structural audit and generator-drift checks."""

from __future__ import annotations

import sys
from pathlib import Path

from ..core import manifest
from ..core import paper_qa
from ..core.exit_codes import DRIFT_ERROR, SUCCESS
from ..errors import UserError
from ..core import fs
from ..generators import (
    ALL_TOOLS,
    RETIRED_STATIC,
    TOOL_OUTPUTS,
    check_generated,
    context_for_workspace,
    workspace_tools,
)
from ..kit import resolve_and_validate
from .python import emit_result, run_script

#: Static entrypoints that postdate ``TOOL_OUTPUTS``. Kept beside the check so
#: the surplus scan covers a runtime's whole static surface.
_EXTRA_STATIC = {
    "opencode": ("opencode.json", ".opencode/plugins/refuse-offpath-push.js"),
    "pi": (".pi/extensions/refuse-offpath-push.js",),
}


def _surplus_static_files(root: Path, active: tuple[str, ...]) -> list[str]:
    """Static entrypoints on disk that this workspace's surface does not own.

    Two families qualify, and they are reported for the same reason: nothing
    regenerates them, so nothing else would ever mention them again.

    One is a runtime the workspace does not declare. A workspace created with a
    wider tool set keeps those files: they are ``reported`` here and never
    deleted. The other is a path a later release *retired*, which is reported
    for every runtime rather than only for the undeclared ones -- a workspace
    that still declares ``pi`` is exactly the one most likely to be carrying
    the retired ``PI.md``, and silence there would defeat the table.

    Dynamic outputs such as ``.claude/commands/``, ``.pi/prompts/`` and
    ``.opencode/agents/`` are deliberately excluded — a never-baselined command
    file is user data, and a baselined one is handled by ``upgrade``'s orphan
    rule.
    """
    found: list[str] = []
    for tool in ALL_TOOLS:
        for relpath in RETIRED_STATIC.get(tool, ()):
            if fs.is_regular_file(root / relpath):
                found.append(relpath)
        if tool in active:
            continue
        for relpath in (*TOOL_OUTPUTS.get(tool, ()), *_EXTRA_STATIC.get(tool, ())):
            if fs.is_regular_file(root / relpath):
                found.append(relpath)
    return sorted(set(found))


def execute(workspace: str | Path, *, check_drift: bool = False, verbose: bool = False) -> int:
    root = Path(workspace).expanduser().resolve()
    spec = root / "skills/skill-audit/references/probes/skill-audit.subcommands.json"
    if not fs.is_regular_file(spec):
        raise UserError(f"missing structural audit probe: {spec}")
    result = run_script(
        root,
        "skills/skill-audit/scripts/audit_cli.py",
        [
            "roster",
            "--subject", str(root / "skills/skill-audit"),
            "--probe-spec", str(spec),
            "--repo-root", str(root),
        ],
    )
    code = emit_result(result)
    if code != SUCCESS:
        return code
    # Read-only: the stored manuscript QA report's findings and staleness
    # (`smith paper qa`), printed only when a compiled manuscript exists. It
    # never changes the exit code.
    qa_line = paper_qa.audit_line(root)
    if qa_line is not None:
        print(qa_line)
    if not check_drift:
        return SUCCESS
    # ``context_for_workspace`` raises on an absent/corrupt config, so a
    # workspace that reaches the resolver below always has a valid one.
    context = context_for_workspace(root)
    active = workspace_tools(root)
    # Projection notes are collected, not warned: ``init``/``upgrade`` report
    # them when they write the projections, and this read only compares them.
    notes: list[str] = []
    drift = check_generated(root, context, active, warnings=notes)
    stored = manifest.load_manifest(root)
    if stored is None:
        raise UserError(f"not a papersmith workspace: missing {root / '.papersmith/manifest.json'}")
    kit_root = resolve_and_validate()
    current = manifest.workspace_framework_files(root, kit_root, notes=[])
    if verbose:
        for note in notes:
            print(f"note: {note}", file=sys.stderr)
    manifest_drift = sorted({
        path for path in set(current) | set(stored["files"])
        if current.get(path) != stored["files"].get(path)
    })
    surplus = _surplus_static_files(root, active)
    if drift or manifest_drift or surplus:
        if drift:
            print("generator drift: " + ", ".join(drift))
        if manifest_drift:
            print("manifest drift: " + ", ".join(manifest_drift))
        if surplus:
            print("surplus: " + ", ".join(surplus))
        return DRIFT_ERROR
    print("drift: clean")
    return SUCCESS


def register(subparsers) -> None:
    parser = subparsers.add_parser("audit", help="audit workspace structure and consistency")
    parser.add_argument("directory", nargs="?", default=".", metavar="<dir>")
    parser.add_argument("--check-drift", action="store_true")
    parser.add_argument("--verbose", action="store_true",
                        help="with --check-drift, also print the projection notes to stderr")
    parser.set_defaults(handler=run_cli)


def run_cli(args) -> int:
    return execute(args.directory, check_drift=args.check_drift, verbose=args.verbose)
