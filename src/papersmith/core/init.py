"""Initialize an independent paper workspace from the resolved kit."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Sequence

from .. import __version__
from ..errors import SourceError, UserError
from ..generators import (
    ALL_TOOLS,
    UNSYNCHRONIZED,
    apply_generated,
    context_for_workspace,
)
from ..kit import resolve_and_validate
from ..render import render_package_template
from ..schema import REMOTE_CHOICES, REMOTE_TARGETS, validate_tools
from . import config, fs
from . import manifest

DEFAULT_AGENT_MODELS = {
    "paper-ingestion": "sonnet",
    "proposal-deliberator": "opus",
    "math-auditor": "opus",
    "code-materializer": "sonnet",
    "remote-orchestrator": "haiku",
}


def _write_text(root: Path, relpath: str, content: str) -> None:
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _create_topology(root: Path) -> None:
    # ``proposals/`` stays flat: this repository's own layout is
    # `proposals/research-concept-rNN.md` with no subfolders (see
    # `skills/proposal-deliberation/profile.ts`, which declares
    # `directory: "proposals"` with no nested stage directories), and a fresh
    # workspace must match it rather than diverge with a `drafts/deliberated/
    # receipts` shape nothing reads.
    directories = (
        ".papersmith",
        ".claude/agents",
        ".opencode",
        ".pi/gentle-ai",
        ".antigravity",
        "guidance/paper-guide",
        "guidance/reference-papers",
        "guidance/data-paper",
        "proposals",
        "implementations",
        "kaggle-inbox",
        "paper",
        "experiments",
    )
    for relpath in directories:
        (root / relpath).mkdir(parents=True, exist_ok=True)
    # Every directory a fresh workspace must ship empty gets a `.gitkeep`, so
    # the folder itself travels through Git while its contents — third-party
    # PDFs, managed revisions, run products — stay on the machine that made
    # them. `guidance/paper-guide` is listed even though the kit no longer
    # bundles its own copy (see ``manifest.KIT_ENTRIES``): the workspace still
    # needs the empty drop-zone.
    for relpath in (
        "guidance/paper-guide/.gitkeep",
        "guidance/reference-papers/.gitkeep",
        "guidance/data-paper/.gitkeep",
        "proposals/.gitkeep",
        "implementations/.gitkeep",
        "kaggle-inbox/.gitkeep",
        "paper/.gitkeep",
        "experiments/.gitkeep",
    ):
        path = root / relpath
        if not fs.exists(path):
            fs.write_text(path, "")


def _copy_kit(root: Path, kit_root: Path) -> list[str]:
    """Copy every kit file into a fresh workspace, or fail loudly.

    ``init`` builds a workspace or refuses; unlike ``upgrade`` it has no
    partially-synchronized workspace to protect, so an unwritable destination is
    an error rather than something to report and continue past.
    """
    copied: list[str] = []
    for relpath in sorted(manifest.kit_files(kit_root)):
        source = kit_root / relpath
        if not fs.is_regular_file(source):
            raise SourceError(f"kit manifest names a missing source file: {source}")
        if not manifest.copy_kit_file(kit_root, relpath, root):
            raise UserError(f"could not write {root / relpath}")
        copied.append(relpath)
    return copied


def _default_config(name: str, tools: Sequence[str], target: str, stamp: str) -> dict:
    return {
        "project_name": name,
        "active_tools": list(tools),
        "agent_models": dict(DEFAULT_AGENT_MODELS),
        "execution_engine": {
            "active_compute_target": target,
            "active_profile": "smoke_and_invariants" if target == "local-workstation" else "sweep_training",
            "accounts_store_path": "skills/kaggle-accounts/store/accounts.json",
            "ledger_path": ".papersmith/runs_ledger.jsonl",
            "auto_retry_failed_shards": True,
            "max_retries": 2,
        },
        "created_at": stamp,
        "updated_at": stamp,
    }


def _write_workspace_seed(root: Path, *, name: str, title: str, topic: str,
                          target: str, version: str, tools: Sequence[str]) -> None:
    context = {
        "name": name,
        "title": title,
        "topic": topic,
        "version": version,
        "tools": ", ".join(tools),
        "agents": "- Agent definitions are available under `.claude/agents/`.",
        "name_yaml": json.dumps(name, ensure_ascii=False),
        "title_yaml": json.dumps(title, ensure_ascii=False),
        "topic_yaml": json.dumps(topic, ensure_ascii=False),
        "default_target_yaml": json.dumps(target, ensure_ascii=False),
        "name_json": json.dumps(name, ensure_ascii=False),
    }
    _write_text(root, "papersmith.yaml", render_package_template("papersmith.yaml.tpl", context))
    _write_text(root, "README.md", render_package_template("readme.md.tpl", context))
    # No ``.mcp.json``: success criterion #6 (tests/test_mcp_no_mcp_json.py) is
    # that the framework never generates, reads or overwrites one. A workspace
    # that wants the server wired asks for the snippet instead --
    # ``papersmith mcp print-config --workspace <path>`` prints it and writes
    # nothing -- and the operator pastes it wherever their harness reads it.
    _write_text(root, "package.json", render_package_template("package.json.tpl", context))
    if "pi" in tools:
        # Pi discovers project skills through ``<cwd>/.pi/settings.json`` (its
        # project settings resolve from the ``<cwd>/.pi`` base directory), so a
        # ``"../skills"`` entry reaches the canonical tree without a symlink.
        # Seeded once rather than generated, for the same reason
        # ``papersmith.yaml`` and ``package.json`` are: it is operator-editable,
        # and ``manifest.PRESERVE_PATTERNS`` keeps ``upgrade`` from clobbering
        # those edits. The neighbouring comment explains why no ``.mcp.json``
        # is written; this one records why the Pi settings file IS.
        _write_text(root, ".pi/settings.json",
                    render_package_template("pi-settings.json.tpl", context))


def _run_npm_install(root: Path) -> str | None:
    npm = shutil.which("npm")
    if npm is None:
        return "npm was not found; deliberate requires npm install for jiti/typebox"
    try:
        result = subprocess.run(
            [npm, "install", "--no-audit", "--no-fund", "--prefix", str(root)],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=180,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"npm install could not complete: {exc}"
    if result.returncode:
        detail = (result.stderr or result.stdout or "unknown npm error").strip().splitlines()
        return f"npm install failed: {detail[-1] if detail else 'unknown error'}"
    return None


def initialize(destination: str | Path, *, title: str = "Untitled Paper",
               tools: Sequence[str] = ALL_TOOLS, topic: str = "unspecified",
               remote: str = "kaggle", run_npm: bool = True) -> dict:
    """Create a workspace and return a machine-readable operation summary."""
    tools = validate_tools(list(tools))
    if remote not in REMOTE_CHOICES:
        raise UserError(f"remote must be one of {', '.join(REMOTE_CHOICES)}")
    if not isinstance(title, str) or not title.strip():
        raise UserError("title must be a non-empty string")
    if not isinstance(topic, str) or not topic.strip():
        raise UserError("topic must be a non-empty string")

    root = Path(destination).expanduser().resolve()
    if fs.exists(root):
        if not fs.is_dir(root):
            raise UserError(f"destination is not a directory: {root}")
        try:
            populated = any(root.iterdir())
        except OSError as exc:
            raise UserError(f"destination is not readable: {root}: {exc}") from None
        if populated:
            raise UserError(f"destination must be empty: {root}")
    else:
        root.mkdir(parents=True, exist_ok=True)

    kit_root = resolve_and_validate()
    version = manifest.kit_version(kit_root) or __version__
    target = REMOTE_TARGETS[remote]
    name = root.name
    _create_topology(root)
    copied = _copy_kit(root, kit_root)
    _write_workspace_seed(root, name=name, title=title.strip(), topic=topic.strip(),
                          target=target, version=version, tools=tools)

    stamp = config.utc_timestamp()
    workspace_config = _default_config(name, tools, target, stamp)
    config.write_json(root / ".papersmith" / "config.json", workspace_config)
    # The destination is absent or empty by contract, so no damaged path can
    # occupy these yet; unlike ``upgrade`` there is nothing to gate against.
    (root / ".papersmith" / "version").write_text(version + "\n", encoding="utf-8")
    (root / ".papersmith" / "runs_ledger.jsonl").touch()

    # Render exactly the declared tool set: the payload the CLI validated and
    # stored above is the same set every later consumer resolves through
    # ``generators.workspace_tools``.
    unsynchronized: list[str] = []
    context = context_for_workspace(root)
    generated = apply_generated(root, context, tools, skipped=unsynchronized)
    warnings: list[str] = []
    if run_npm:
        warning = _run_npm_install(root)
        if warning:
            warnings.append(warning)

    # Validate the generated documents before making the manifest authoritative.
    config.load_workspace_config(root)
    config.load_papersmith_yaml(root)
    framework_files = manifest.workspace_framework_files(root, kit_root)
    for relpath in manifest.synchronized_paths(root, kit_root, context, tools):
        # Any managed path the baseline cannot hash — non-regular, never
        # written, or written but still unreadable — is recorded with a marker,
        # so ``status`` reports it as drift instead of losing it in the rewrite.
        if relpath not in framework_files:
            framework_files[relpath] = UNSYNCHRONIZED
    manifest.write_manifest(root, version, framework_files, kind="workspace")
    return {
        "workspace": str(root),
        "name": name,
        "version": version,
        "active_tools": list(tools),
        "remote": remote,
        "default_target": target,
        "copied_files": copied,
        "generated_files": generated,
        "warnings": warnings,
    }


def register(subparsers) -> None:
    parser = subparsers.add_parser("init", help="initialize a standalone paper workspace")
    parser.add_argument("directory", metavar="<dir>")
    parser.add_argument("--title", default="Untitled Paper")
    parser.add_argument("--tools", default=",".join(ALL_TOOLS), help="comma-separated runtimes")
    parser.add_argument("--topic", default="unspecified")
    parser.add_argument("--remote", choices=REMOTE_CHOICES, default="kaggle")
    parser.add_argument("--no-npm", action="store_true", help="skip the best-effort npm install")
    parser.set_defaults(handler=run_cli)


def run_cli(args) -> int:
    tools = [item.strip() for item in args.tools.split(",") if item.strip()]
    result = initialize(
        args.directory,
        title=args.title,
        tools=tools,
        topic=args.topic,
        remote=args.remote,
        run_npm=not args.no_npm,
    )
    print(f"Initialized papersmith workspace: {result['workspace']}")
    print(f"Framework version: {result['version']}; default target: {result['default_target']}")
    for warning in result["warnings"]:
        print(f"Warning: {warning}", file=__import__("sys").stderr)
    return 0
