"""Initialize an independent paper workspace from the resolved kit."""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Sequence

from .. import __version__
from ..errors import SourceError, UserError
from ..generators import (
    ALL_TOOLS,
    UNSYNCHRONIZED,
    apply_generated,
    context_for_workspace,
    merge_managed,
    MCP_CONFIG_FILES,
    ensure_mcp_servers,
    seed_pi_settings,
)
from ..kit import resolve_and_validate_origin
from ..render import render_package_template
from ..schema import REMOTE_CHOICES, REMOTE_TARGETS, validate_tools
from . import kaggle_mcp
from . import config, fs
from . import manifest, progress, provenance, wiring

DEFAULT_AGENT_MODELS = {
    "paper-ingestion": "sonnet",
    "proposal-deliberator": "opus",
    "math-auditor": "opus",
    "code-materializer": "sonnet",
    "remote-orchestrator": "haiku",
}

#: How long the environment step may take. Generous on purpose: provisioning
#: resolves and downloads a micromamba environment, which is minutes on a warm
#: cache and considerably longer on a cold one. A tighter bound would report a
#: slow network as a provisioning defect.
PROVISION_TIMEOUT = 3600

#: How long ``npm install`` may take. It installs two devDependencies from a
#: warm cache in seconds; the bound exists for a registry that never answers,
#: so that the step is named and the run continues rather than hanging.
NPM_TIMEOUT = 180


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
        "guidance/paper-guide",
        "guidance/reference-papers",
        "guidance/data-paper",
        "proposals",
        "implementations",
        "kaggle-inbox",
        "paper",
        "experiments",
        # The plausibility flow's graph pool: `candidates.json` from
        # `sota-scout`, `atlas.json` from `sota-grapher`, and the `atlas.html`
        # rendered from it. It was the one drop-zone the topology never
        # scaffolded, so unlike every sibling above it did not travel through
        # git as an empty folder and this framework's own root `.gitignore`
        # named a `sota-pool/.gitkeep` that nothing created.
        "sota-pool",
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
        "sota-pool/.gitkeep",
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
    # ``.mcp.json`` registers only the servers papersmith manages -- banco-lia,
    # kaggle and colab (see
    # ``generators.ensure_mcp_servers``). The papersmith server itself is never
    # written there (success criterion #6, tests/test_mcp_no_mcp_json.py): a
    # workspace that wants it wired asks for the snippet --
    # ``smith mcp print-config --workspace <path>`` prints it and writes
    # nothing -- and the operator pastes it wherever their harness reads it.
    _write_text(root, "package.json", render_package_template("package.json.tpl", context))


def _run_npm_install(root: Path, report: progress.Reporter | None = None) -> str | None:
    report = report or progress.Reporter()
    npm = shutil.which("npm")
    if npm is None:
        return "npm was not found; deliberate requires npm install for jiti/typebox"
    try:
        code, tail = progress.run_streaming(
            [npm, "install", "--no-audit", "--no-fund", "--prefix", str(root)],
            cwd=root, report=report, timeout=NPM_TIMEOUT)
    except (OSError, progress.ChildTimedOut) as exc:
        return f"npm install could not complete: {exc}"
    if code:
        detail = tail.strip().splitlines()
        return f"npm install failed: {detail[-1] if detail else 'unknown error'}"
    return None


def _run_env_install(root: Path, report: progress.Reporter | None = None) -> str | None:
    """Provision the workspace's Python environment through its own script.

    Fail-soft and reported in ``warnings``, exactly like ``_run_npm_install``: a
    workspace whose provisioning cannot complete is still a workspace.

    **This is the step that makes ``smith ui`` work after init.** Without
    it the dashboard's backend has no interpreter that can import it: the CLI's
    own interpreter is a ``pipx`` venv with no runtime dependencies, and the
    environment ``scripts/setup_env.py`` builds is the one thing that carries
    them. It is deliberately the same script an operator can run by hand, so
    there is one provisioning path rather than two.

    The cost is real and stated rather than discovered: this downloads a
    micromamba environment, so ``init`` is no longer offline-fast unless it is
    given ``--no-env``.
    """
    script = root / "scripts" / "setup_env.py"
    report = report or progress.Reporter()
    if not script.is_file():
        return ("scripts/setup_env.py is not present, so the workspace has no "
                "environment to run the command center; run `smith upgrade`")
    interpreter = shutil.which("python3") or sys.executable
    try:
        code, tail = progress.run_streaming(
            [interpreter, str(script), "install"],
            cwd=root, report=report, timeout=PROVISION_TIMEOUT)
    except (OSError, progress.ChildTimedOut) as exc:
        return f"environment provisioning could not complete: {exc}"
    if code:
        detail = tail.strip().splitlines()
        return ("environment provisioning failed: "
                f"{detail[-1] if detail else 'unknown error'}; run "
                f"`python3 scripts/setup_env.py install` in {root}")
    return None


#: Root files almost every existing repository already has. Import keeps the
#: repository's ``README.md`` (the scaffold's is only a stub, and the workspace
#: owns it after init anyway) and merges the managed block into its
#: ``.gitignore`` (see ``generators.merge_managed``) instead of refusing.
IMPORT_KEPT = frozenset({"README.md"})
IMPORT_MERGED = frozenset({".gitignore"})
#: Harness MCP files an existing repository may already have. Import keeps
#: them and ``initialize`` then adds the banco-lia entry to each.
IMPORT_MCP_KEPT = frozenset(MCP_CONFIG_FILES.values())


def _import_staged(root: Path, staged: Path) -> None:
    """Merge a complete scaffold without replacing any existing path.

    Check the complete tree before writing; exclusive creates still guard against
    collisions appearing between preflight and copy. Roll back only paths this
    operation created if a copy fails (never remove a pre-existing path).
    The root files in :data:`IMPORT_KEPT` and :data:`IMPORT_MERGED` are the
    exception: an existing one is kept, or merged after every copy succeeded.
    """
    def adopted(relpath: Path, names: frozenset[str]) -> bool:
        dest = root / relpath
        return (len(relpath.parts) == 1 and relpath.name in names
                and fs.is_regular_file(dest) and not dest.is_symlink())

    directories = sorted((p for p in staged.rglob("*") if p.is_dir() and not p.is_symlink()),
                         key=lambda p: (len(p.relative_to(staged).parts), str(p)))
    entries = sorted((p for p in staged.rglob("*") if not p.is_dir() or p.is_symlink()),
                     key=str)
    merged = [p for p in entries if adopted(p.relative_to(staged), IMPORT_MERGED)]
    entries = [p for p in entries if p not in merged
               and not adopted(p.relative_to(staged), IMPORT_KEPT)
               and not (p.relative_to(staged).as_posix() in IMPORT_MCP_KEPT
                        and fs.is_regular_file(root / p.relative_to(staged))
                        and not (root / p.relative_to(staged)).is_symlink())]
    for source in merged:
        dest = root / source.relative_to(staged)
        if merge_managed(dest.name, source.read_text(encoding="utf-8"),
                         dest.read_bytes()) is None:
            raise UserError(f"import collision: {dest} has malformed papersmith markers "
                            "or is not UTF-8")
    for source in directories:
        dest = root / source.relative_to(staged)
        if dest.is_symlink() or (dest.exists() and not dest.is_dir()):
            raise UserError(f"import collision: {dest}")
    for source in entries:
        dest = root / source.relative_to(staged)
        if dest.exists() or dest.is_symlink():
            raise UserError(f"import collision: {dest}")

    # Do not address a destination child by its pathname after preflight: a
    # swapped ancestor symlink could otherwise redirect even an exclusive open
    # outside the workspace. Each lookup is relative to an open directory fd,
    # and O_NOFOLLOW refuses swaps at every component.
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise UserError("safe import requires directory-fd and no-follow filesystem support")
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW

    @contextlib.contextmanager
    def parent_fd(root_fd: int, relpath: Path):
        with contextlib.ExitStack() as stack:
            current = root_fd
            for part in relpath.parts[:-1]:
                child = os.open(part, directory_flags, dir_fd=current)
                stack.callback(os.close, child)
                current = child
            yield current

    def require_parent_unchanged(root_fd: int, rel: Path, fd: int) -> None:
        with parent_fd(root_fd, rel) as current:
            expected, actual = os.fstat(fd), os.fstat(current)
            if (expected.st_dev, expected.st_ino) != (actual.st_dev, actual.st_ino):
                raise UserError(f"destination parent changed during import: {root / rel.parent}")

    created: list[tuple[Path, tuple[int, int], bool]] = []
    try:
        # If the root path itself changed while staging, refuse rather than
        # opening an unrelated directory before anchoring the descriptor.
        identity = root.stat()
        with contextlib.ExitStack() as root_stack:
            root_fd = os.open(root, directory_flags)
            root_stack.callback(os.close, root_fd)
            actual = os.fstat(root_fd)
            if (actual.st_dev, actual.st_ino) != (identity.st_dev, identity.st_ino):
                raise UserError("destination changed during import")
            try:
                for source in directories:
                    rel = source.relative_to(staged)
                    with parent_fd(root_fd, rel) as fd:
                        try:
                            os.mkdir(rel.name, dir_fd=fd)
                        except FileExistsError:
                            # Must be a real directory, never a symlink.
                            child = os.open(rel.name, directory_flags, dir_fd=fd)
                            os.close(child)
                        else:
                            stat = os.stat(rel.name, dir_fd=fd, follow_symlinks=False)
                            created.append((rel, (stat.st_dev, stat.st_ino), True))
                for source in entries:
                    rel = source.relative_to(staged)
                    with parent_fd(root_fd, rel) as fd:
                        if source.is_symlink():
                            os.symlink(os.readlink(source), rel.name, dir_fd=fd)
                            stat = os.stat(rel.name, dir_fd=fd, follow_symlinks=False)
                            created.append((rel, (stat.st_dev, stat.st_ino), False))
                        elif source.is_file():
                            with source.open("rb") as inp:
                                with os.fdopen(os.open(rel.name, os.O_WRONLY | os.O_CREAT |
                                                       os.O_EXCL | os.O_NOFOLLOW, 0o666,
                                                       dir_fd=fd), "wb") as out:
                                    stat = os.fstat(out.fileno())
                                    created.append((rel, (stat.st_dev, stat.st_ino), False))
                                    shutil.copyfileobj(inp, out)
                        else:
                            raise UserError(f"unsupported staged entry: {source}")
                        require_parent_unchanged(root_fd, rel, fd)
                for source in merged:
                    _merge_root_file(root_fd, source)
            except (OSError, UserError) as exc:
                for rel, inode, is_directory in reversed(created):
                    try:
                        with parent_fd(root_fd, rel) as fd:
                            stat = os.stat(rel.name, dir_fd=fd, follow_symlinks=False)
                            if (stat.st_dev, stat.st_ino) == inode:
                                if is_directory:
                                    os.rmdir(rel.name, dir_fd=fd)
                                else:
                                    os.unlink(rel.name, dir_fd=fd)
                    except OSError:
                        pass  # changed parent or concurrent occupant: leave it untouched
                raise UserError(f"import failed; newly created paths rolled back where possible: {exc}") from exc
    except OSError as exc:
        raise UserError(f"safe import unavailable: {exc}") from exc


def _merge_root_file(root_fd: int, source: Path) -> None:
    """Rewrite one root file as the merge of its bytes and ``source``.

    Read through the anchored root descriptor without following a link, and
    replace it with a sibling written exclusively, so a failure leaves the
    repository's own file as it was.
    """
    name = source.name
    with os.fdopen(os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=root_fd), "rb") as inp:
        existing = inp.read()
    content = merge_managed(name, source.read_text(encoding="utf-8"), existing)
    if content is None:
        raise UserError(f"import collision: {name} changed during import")
    temporary = f".{name}.papersmith-import"
    try:
        with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                               os.O_NOFOLLOW, 0o666, dir_fd=root_fd), "w",
                       encoding="utf-8", newline="") as out:
            out.write(content)
        os.replace(temporary, name, src_dir_fd=root_fd, dst_dir_fd=root_fd)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temporary, dir_fd=root_fd)
        raise


def initialize(destination: str | Path, *, title: str = "Untitled Paper",
               tools: Sequence[str] = ALL_TOOLS, topic: str = "unspecified",
               remote: str = "kaggle", run_npm: bool = True,
               run_env: bool = False,
               report: progress.Reporter | None = None,
               allow_dirty_kit: bool = False,
               import_existing: bool = False) -> dict:
    """Create a workspace and return a machine-readable operation summary.

    ``report`` is where the bar, the child's log and the estimate go. It
    defaults to a reporter that writes nothing, because the callers that are
    not a terminal -- the MCP server, which spawns this CLI and reads its
    stdout, and the test suite -- have to keep the bytes they always got.
    """
    report = report or progress.Reporter()
    tools = validate_tools(list(tools))
    if remote not in REMOTE_CHOICES:
        raise UserError(f"remote must be one of {', '.join(REMOTE_CHOICES)}")
    if not isinstance(title, str) or not title.strip():
        raise UserError("title must be a non-empty string")
    if not isinstance(topic, str) or not topic.strip():
        raise UserError("topic must be a non-empty string")

    # Decided before the destination is created: a kit carrying uncommitted
    # edits (or one whose git state cannot be read) refuses here, while nothing
    # has been written, unless the caller allowed it explicitly.
    kit_root, kit_origin = resolve_and_validate_origin()
    kit_source = provenance.describe(kit_root, kit_origin)
    allowed_dirty = provenance.require_admissible(kit_source, verb="init",
                                                  allow_dirty=allow_dirty_kit)

    root = Path(destination).expanduser().resolve()
    if fs.exists(root):
        if not fs.is_dir(root):
            raise UserError(f"destination is not a directory: {root}")
        try:
            populated = any(root.iterdir())
        except OSError as exc:
            raise UserError(f"destination is not readable: {root}: {exc}") from None
        if populated:
            if not import_existing:
                raise UserError(f"destination must be empty: {root} (use --import-existing "
                                "to add papersmith to an existing folder)")
            # Build a complete scaffold off-target before touching user content.
            # Provisioning happens only after the collision-free merge, so a
            # rejected import never invokes npm or the environment installer.
            with tempfile.TemporaryDirectory(prefix="papersmith-init-") as holder:
                staged = Path(holder) / root.name
                result = initialize(
                    staged, title=title, tools=tools, topic=topic, remote=remote,
                    run_npm=False, run_env=False, report=report,
                    allow_dirty_kit=allow_dirty_kit)
                _import_staged(root, staged)
            ensure_mcp_servers(root, tools, warnings=result["warnings"])
            result["workspace"] = str(root)
            result["name"] = root.name
            if run_npm:
                warning = _run_npm_install(root, report)
                if warning:
                    result["warnings"].append(warning)
            if run_env:
                warning = _run_env_install(root, report)
                if warning:
                    result["warnings"].append(warning)
            return result
    else:
        root.mkdir(parents=True, exist_ok=True)

    # The plan excludes the steps this run was told to skip, so the bar counts
    # the work that will actually happen. Two of these are a package install and
    # an environment download, so the priors are a first guess that the run
    # replaces with the pace it measures.
    plan = [
        progress.Step("kit", "copying the kit", 1.5),
        progress.Step("harness", "linking the harness skills", 0.3),
        progress.Step("workspace", "writing the workspace files", 0.4),
        progress.Step("generated", "projecting the harness surface", 0.6),
    ]
    if run_npm:
        plan.append(progress.Step("npm", "running npm install", 45.0))
    if run_env:
        plan.append(progress.Step("environment",
                                  "provisioning the Python environment", 300.0))
    plan.append(progress.Step("manifest", "validating and writing the baseline", 0.6))
    report.plan(plan)

    with report.step("kit"):
        version = manifest.kit_version(kit_root) or __version__
        target = REMOTE_TARGETS[remote]
        name = root.name
        _create_topology(root)
        copied = _copy_kit(root, kit_root)
    # A wired harness `skills` symlink is reported like every other kit file.
    # A path that could not be linked (no symlink privilege, read-only mount,
    # ELOOP) or that real content already occupies is surfaced as a warning
    # below; init still succeeds and `upgrade` repairs it once the cause is
    # fixed. Files are never copied in place of a link.
    with report.step("harness"):
        link_report = manifest.link_harness_skills_report(root, tools=tools)
        copied.extend(link_report.linked)

    with report.step("workspace"):
        _write_workspace_seed(root, name=name, title=title.strip(), topic=topic.strip(),
                              target=target, version=version, tools=tools)
        if "pi" in tools:
            seed_pi_settings(root)
        mcp_warnings: list[str] = []
        ensure_mcp_servers(root, tools, warnings=mcp_warnings)
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
    with report.step("generated"):
        context = context_for_workspace(root)
        generated = apply_generated(root, context, tools, skipped=unsynchronized)
    warnings: list[str] = manifest.link_warnings(link_report) + mcp_warnings
    if run_npm:
        with report.step("npm"):
            warning = _run_npm_install(root, report)
        if warning:
            warnings.append(warning)
    if run_env:
        with report.step("environment"):
            warning = _run_env_install(root, report)
        if warning:
            warnings.append(warning)

    # Validate the generated documents before making the manifest authoritative.
    with report.step("manifest"):
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
        source_record, written = provenance.write_record(root, kit_source,
                                                         allowed_dirty=allowed_dirty)
        if not written:
            warnings.append(f"could not write {provenance.KIT_SOURCE_RECORD}; "
                            "`status` will report this workspace's kit source as unknown")
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
        "kit_source": source_record,
        "wiring": wiring.summarize(root, tools, link_report, unsynchronized),
    }


def register(subparsers) -> None:
    parser = subparsers.add_parser("init", help="initialize a standalone paper workspace")
    parser.add_argument(
        "directory", metavar="<dir>", nargs="?", default=".",
        help="where to create the workspace (default: the current directory)")
    parser.add_argument("--title", default="Untitled Paper")
    parser.add_argument(
        "--tools",
        default=",".join(ALL_TOOLS),
        help="comma-separated runtimes (claude, opencode, pi, antigravity/agy)",
    )
    parser.add_argument("--topic", default="unspecified")
    parser.add_argument("--remote", choices=REMOTE_CHOICES, default="kaggle")
    parser.add_argument("--import-existing", action="store_true",
                        help=("initialize a nonempty directory without overwriting existing files: keep its "
                              "README.md, merge papersmith's block into its .gitignore, and "
                              "refuse any other collision"))
    parser.add_argument("--no-npm", action="store_true", help="skip the best-effort npm install")
    parser.add_argument(
        "--with-env", action="store_true",
        help=("provision the workspace's micromamba Python environment during init "
              "(warning: multi-gigabyte download); by default, provisioning is deferred "
              "until experimental runs or ingestion"))
    parser.add_argument(
        "--no-env", action="store_true",
        help="skip provisioning this workspace's Python environment (default)")
    parser.add_argument(
        "--allow-dirty-kit", action="store_true",
        help=("initialize even when the kit source has uncommitted changes under its "
              "shipped paths, or its git state cannot be determined; the workspace "
              "records that it was built from such a kit"))
    parser.set_defaults(handler=run_cli)
    progress_flags = parser.add_mutually_exclusive_group()
    progress_flags.add_argument(
        "--progress", action="store_true",
        help=("stream a plain progress log with an ETA; a terminal already gets "
              "the bar, and a pipe stays silent unless this is asked for"))
    progress_flags.add_argument(
        "--no-progress", action="store_true",
        help="never draw progress, even on a terminal")


def run_cli(args) -> int:
    tools = [item.strip() for item in args.tools.split(",") if item.strip()]
    report = progress.Reporter.for_stream(
        sys.stdout,
        requested=bool(getattr(args, "progress", False)),
        suppressed=bool(getattr(args, "no_progress", False)),
    )
    run_env = bool(getattr(args, "with_env", False)) and not bool(getattr(args, "no_env", False))
    result = initialize(
        args.directory,
        title=args.title,
        tools=tools,
        topic=args.topic,
        remote=args.remote,
        run_npm=not args.no_npm,
        run_env=run_env,
        report=report,
        allow_dirty_kit=args.allow_dirty_kit,
        import_existing=args.import_existing,
    )
    report.finish()
    print(f"Initialized papersmith workspace: {result['workspace']}")
    print(f"Framework version: {result['version']}; default target: {result['default_target']}")
    print(f"Kit source: {provenance.describe_record({'recorded': True, **result['kit_source']})}")
    print("Harness wiring:")
    for line in wiring.format_summary(result["wiring"]):
        print(f"  {line}")
    for line in kaggle_mcp.summary_lines(_active_tools_of(result)):
        print(line)
    if not run_env:
        print("\nNote: Python environment provisioning was deferred for a fast init.")
        print("To provision the micromamba environment for experiments and ingestion:")
        print("  smith env install  (or python3 scripts/setup_env.py install)")
    for warning in result["warnings"]:
        print(f"Warning: {warning}", file=__import__("sys").stderr)
    return 0


def _active_tools_of(result: dict) -> list[str]:
    """The harnesses this run wired, for the offline Kaggle MCP summary."""
    wiring = result.get("wiring")
    if isinstance(wiring, dict):
        return [str(tool) for tool in wiring]
    if isinstance(wiring, list):
        return [str(item.get("tool")) for item in wiring if isinstance(item, dict) and item.get("tool")]
    return []
