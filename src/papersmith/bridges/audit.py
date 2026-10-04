"""Workspace structural audit and generator-drift checks."""

from __future__ import annotations

from pathlib import Path

from ..core import manifest
from ..core.exit_codes import DRIFT_ERROR, SUCCESS
from ..errors import UserError
from ..core import fs
from ..generators import (
    ALL_TOOLS,
    TOOL_OUTPUTS,
    check_generated,
    context_for_workspace,
    workspace_tools,
)
from ..kit import resolve_and_validate
from .python import emit_result, run_script

#: Static entrypoints that postdate ``TOOL_OUTPUTS``. Kept beside the check so
#: the surplus scan covers a runtime's whole static surface.
#:
#: ``.pi/settings.json`` is deliberately here and not in ``TOOL_OUTPUTS``:
#: ``TOOL_OUTPUTS`` is the *managed* static surface, and this file is seeded
#: (``generators.SEED_OUTPUTS``: once by ``init``, and by ``upgrade`` into a
#: workspace that predates it) and then owned by the operator, so a workspace
#: that later stops declaring ``pi`` still gets its leftover reported as surplus
#: rather than silently ignored.
_EXTRA_STATIC = {
    "opencode": ("opencode.json", ".opencode/plugins/refuse-offpath-push.js"),
    "pi": (".pi/settings.json",),
}


def _surplus_static_files(root: Path, active: tuple[str, ...]) -> list[str]:
    """Static entrypoints owned by runtimes this workspace does not declare.

    A workspace created with a wider tool set keeps those files: they are
    ``reported`` here and never deleted. Dynamic outputs such as
    ``.claude/commands/`` are deliberately excluded — a never-baselined command
    file is user data, and a baselined one is handled by ``upgrade``'s orphan
    rule.
    """
    found: list[str] = []
    for tool in ALL_TOOLS:
        if tool in active:
            continue
        for relpath in (*TOOL_OUTPUTS.get(tool, ()), *_EXTRA_STATIC.get(tool, ())):
            if fs.is_regular_file(root / relpath):
                found.append(relpath)
    return sorted(set(found))


def execute(workspace: str | Path, *, check_drift: bool = False) -> int:
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
    if not check_drift:
        return SUCCESS
    # ``context_for_workspace`` raises on an absent/corrupt config, so a
    # workspace that reaches the resolver below always has a valid one.
    context = context_for_workspace(root)
    active = workspace_tools(root)
    drift = check_generated(root, context, active)
    stored = manifest.load_manifest(root)
    if stored is None:
        raise UserError(f"not a papersmith workspace: missing {root / '.papersmith/manifest.json'}")
    kit_root = resolve_and_validate()
    current = manifest.workspace_framework_files(root, kit_root)
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
    parser.set_defaults(handler=run_cli)


def run_cli(args) -> int:
    return execute(args.directory, check_drift=args.check_drift)
