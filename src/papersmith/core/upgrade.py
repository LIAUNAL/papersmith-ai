"""Synchronize framework-owned files into an existing workspace."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Sequence

from ..errors import SourceError, UserError
from ..generators import (
    RETIRED_STATIC,
    UNSYNCHRONIZED,
    apply_generated,
    context_for_workspace,
    read_workspace_version,
    render_files,
    PI_SETTINGS_FILE,
    ensure_mcp_servers,
    seed_pi_settings,
)
from ..kit import resolve_and_validate_origin
from ..schema import validate_tools
from . import kaggle_mcp
from . import config, fs, manifest, migrations, provenance, wiring
from .exit_codes import EXECUTION_ERROR

#: Dynamic rendered outputs — one file per discovered skill, so their membership
#: cannot be enumerated by a static list. Only paths under these prefixes that
#: were previously baselined are ever removed (see :func:`_orphaned`).
DYNAMIC_PREFIXES = (
    ".opencode/commands/", ".opencode/agents/", ".agents/agents/", ".claude/commands/", ".pi/prompts/",
    ".pi/agents/",
)


def _contained(relpath: str) -> bool:
    """True when a stored key is a plain workspace-relative path.

    The manifest is data, so anything that is not a normal relative path — an
    absolute key, a ``..`` segment, or a NUL byte — is refused before it can be
    joined and unlinked. This check is lexical and total: it cannot itself raise.
    """
    if not relpath or relpath.startswith("/") or "\x00" in relpath:
        return False
    return ".." not in relpath.split("/")


def _orphaned(root: Path, previous_managed: set[str], current_render: set[str]) -> list[str]:
    """Baselined dynamic paths that are no longer derivable.

    The exact predicate: a path qualifies only when it is in ``previous_managed``
    (the stored manifest — it was this tool's own output), it starts with a
    declared dynamic prefix, it is absent from ``current_render``, and it is a
    contained relative path inside ``root``.

    A file under those prefixes that was never baselined is deliberately
    preserved: it is not this tool's output, so deleting it would lose user data.
    Static entrypoints never match a prefix and are never removable *here*: a
    retired one is removed by :func:`_retired`, which recognises it by name in
    :data:`generators.RETIRED_STATIC` rather than by shape.

    A stored-manifest key is data, not a trusted path. It is validated lexically
    first and only then resolved, so a crafted key is refused rather than
    resolved: a symlink loop, a NUL byte or an out-of-workspace target can never
    turn ``upgrade`` into a file-deletion primitive.
    """
    anchor = root.resolve()
    eligible: list[str] = []
    for path in previous_managed:
        if not path.startswith(DYNAMIC_PREFIXES) or path in current_render:
            continue
        if not _contained(path):
            continue
        try:
            inside = (root / path).resolve().is_relative_to(anchor)
        except (OSError, ValueError, RuntimeError):
            inside = False
        if inside:
            eligible.append(path)
    return sorted(eligible)


def _retired(root: Path, previous_managed: set[str], active: Sequence[str]) -> list[str]:
    """Baselined static paths a later release retired for a declared runtime.

    The gate is narrower than :func:`_orphaned` in one direction and wider in
    another. It is narrower because a retired path is not recognised by shape —
    it is not under a dynamic prefix — but by the named
    :data:`generators.RETIRED_STATIC` table, so the set of paths ``upgrade`` may
    ever delete stays enumerable and reviewable instead of growing with any
    baselined file that stops being rendered. It is wider because a retired
    static path *is* removable, which the prefix rule refuses to every static
    entrypoint.

    Both conditions are required, and each rules out a different loss. The path
    must be in ``previous_managed``: a ``PI.md`` this tool never wrote is a
    user's file, and it survives — the boundary ``test_migration_keeps_static_
    entrypoints_and_names_them_as_surplus`` holds. The runtime that used to
    write it must still be declared: a workspace that dropped ``pi`` keeps its
    pi files and gets them reported as surplus, exactly like every other
    undeclared runtime's.
    """
    eligible: list[str] = []
    for tool in active:
        for relpath in RETIRED_STATIC.get(tool, ()):
            if relpath in previous_managed and _contained(relpath):
                eligible.append(relpath)
    return sorted(set(eligible))


def _copy_if_needed(workspace: Path, kit_root: Path, relpath: str, *, force: bool,
                    unsynchronized: list[str], kit_relpath: str | None = None) -> bool:
    """Synchronize one kit file; return whether it was written.

    A destination that cannot be written — a FIFO a copy would block on, a
    directory, an unsearchable parent — is appended to ``unsynchronized``
    instead of aborting a run that has already synchronized earlier files.
    """
    kit_relpath = kit_relpath or relpath
    source = kit_root / kit_relpath
    destination = workspace / relpath
    if not fs.is_regular_file(source):
        raise SourceError(f"kit manifest names a missing source file: {source}")
    if manifest.is_preserved(relpath):
        return False
    if not force:
        # A guarded hash, not a bare one: a regular file whose mode denies the
        # read makes ``sha256_file`` raise, and this runs inside the repair
        # command, after earlier kit files have already been written.
        current = manifest.sha256_if_readable(destination)
        if current is not None and current == manifest.sha256_if_readable(source):
            return False
    if not manifest.copy_kit_file(kit_root, kit_relpath, workspace, relpath):
        unsynchronized.append(relpath)
        return False
    return True


def _refuse_a_downgrade(root: Path, kit_version: str, *, allowed: bool) -> None:
    """Refuse to move a workspace to an older framework version.

    `upgrade` read the kit's version and WROTE it in three places, and the
    only comparison it made was an equality -- enough to decide whether to
    rewrite the version file, and nothing about order. So installing an
    older kit over a newer workspace rolled it back in silence and reported
    the older version as the new truth.

    This refuses at a decision point rather than reporting afterwards, the
    same split `remote-execution`'s pin conditions already draw and for the
    reason written there: a warning printed beside work that already
    happened reads like weather. By the time the files are copied the
    rollback IS the state.

    The escape hatch is its own argument, deliberately not `force`. `force`
    means "write even when the bytes already match", and a caller asking
    for a redundant rewrite must not receive a version rollback as part of
    the bargain -- one flag answering two unrelated questions is how an
    operator gets a behaviour they never asked for.

    A workspace with no recorded version is not a downgrade: there is
    nothing to go backwards from, and refusing a first upgrade would block
    the case this guard was never about. A recorded version that cannot be
    ordered refuses instead, because the guard's whole claim is that one
    version precedes another, and writing files under a relationship
    nobody established is the silence being removed here.
    """
    if allowed:
        return
    recorded = read_workspace_version(root, "").strip()
    if not recorded:
        return
    # Shared with the migration gate, which refuses for the same reason: see
    # ``migrations.version_order``.
    current = migrations.version_order(recorded)
    incoming = migrations.version_order(kit_version)
    if current is None or incoming is None:
        raise UserError(
            f"cannot tell whether {kit_version!r} precedes the version this "
            f"workspace records ({recorded!r}): one of them carries no "
            f"orderable number. Re-run with allow_downgrade=True "
            f"(`--allow-downgrade`) if you mean to install it anyway")
    if incoming < current:
        raise UserError(
            f"refusing to move this workspace backwards: it records "
            f"{recorded!r} and the installed kit is {kit_version!r}. "
            f"Install the newer kit, or re-run with allow_downgrade=True "
            f"(`--allow-downgrade`) if the rollback is deliberate")


def _as_pending(outcome: migrations.Outcome) -> dict:
    """One pending migration, in the single shape every caller reports."""
    return {
        "id": outcome.migration_id,
        "summary": outcome.summary,
        "actions": list(outcome.actions),
    }


def _empty_migration_report() -> dict:
    return {"ran": False, "applied": [], "satisfied": [], "undetermined": [],
            "pending": [], "failures": []}


def upgrade(workspace: str | Path = ".", *, tools: Sequence[str] | None = None,
            force: bool = False, allow_downgrade: bool = False,
            migrate: bool = True, plan_migrations: bool = False,
            allow_dirty_kit: bool = False) -> dict:
    root = Path(workspace).expanduser().resolve()
    stored = manifest.load_manifest(root)
    if stored is None:
        raise UserError(f"not a papersmith workspace: missing {root / '.papersmith/manifest.json'}")

    kit_root, kit_origin = resolve_and_validate_origin()
    # The paper line decides which kit files this workspace receives and
    # where (``manifest.kit_layout``): a review workspace keeps its review
    # section contracts and never gets the experimental ones back.
    kit_files = manifest.kit_layout(kit_root, manifest.paper_kind(root))
    version = manifest.kit_version(kit_root)
    # Read once, before this run can rewrite it: every later decision about
    # migrations asks where the workspace STARTED, not where it ended up.
    recorded = read_workspace_version(root, "").strip()

    if plan_migrations:
        # A preview that synchronized files on the way would be a preview of
        # something that already happened. Nothing below this branch runs, the
        # downgrade guard included: it refuses writes, and there are none.
        preview = migrations.plan(root, recorded=recorded, kit_version=version)
        return {
            "workspace": str(root),
            "version": version,
            "planned": True,
            "migrations": {
                **_empty_migration_report(),
                "satisfied": preview.satisfied,
                "undetermined": preview.undetermined,
                "pending": [_as_pending(entry) for entry in preview.pending],
            },
        }

    # Before a single byte is written, and never after: by the time the kit
    # files are copied the rollback is already the workspace's state. The kit
    # source guard is the same decision for the same reason: uncommitted kit
    # edits copied into a workspace are its state from then on.
    kit_source = provenance.describe(kit_root, kit_origin)
    allowed_dirty = provenance.require_admissible(kit_source, verb="upgrade",
                                                  allow_dirty=allow_dirty_kit)
    _refuse_a_downgrade(root, version, allowed=allow_downgrade)
    # Same reason, same place: a damaged migration ledger cannot be told from
    # an empty one, and discovering that after the files are synchronized
    # leaves the operator with a half-moved workspace and no record of why.
    migrations.read_applied(root)
    workspace_config = config.load_workspace_config(root)
    active_tools = validate_tools(list(tools) if tools is not None else workspace_config["active_tools"])
    changed: list[str] = []
    preserved: list[str] = []
    unsynchronized: list[str] = []

    for relpath in sorted(kit_files):
        if manifest.is_preserved(relpath):
            preserved.append(relpath)
            continue
        if _copy_if_needed(root, kit_root, relpath, force=force,
                           unsynchronized=unsynchronized, kit_relpath=kit_files[relpath]):
            changed.append(relpath)

    # Repair a missing or stale harness `skills` symlink for the active
    # tools, the same way a missing kit file is repaired above, and report
    # it the same way. Never touches real, non-symlinked content at that
    # path; a failed or blocked path is returned as a warning instead.
    link_report = manifest.link_harness_skills_report(root, tools=active_tools)
    changed.extend(link_report.linked)

    if tools is not None:
        workspace_config["active_tools"] = active_tools
    workspace_config["updated_at"] = config.utc_timestamp()
    config.write_json(root / ".papersmith" / "config.json", workspace_config)

    # Rendered files are framework-owned projections. Context is read after
    # raw agent/config files have been synchronized so the new roster appears.
    context = context_for_workspace(root)
    generated = apply_generated(root, context, active_tools, skipped=unsynchronized,
                                baseline=stored["files"])
    for relpath in generated:
        if relpath not in changed:
            changed.append(relpath)
    # Workspaces made before Pi's web tools were declared get the settings
    # file once; an existing one is the workspace's own and stays as it is.
    if "pi" in active_tools and seed_pi_settings(root):
        changed.append(PI_SETTINGS_FILE)
    # Each harness's MCP file is the workspace's own; upgrade only adds or
    # refreshes the banco-lia entry and keeps every other server.
    mcp_warnings: list[str] = []
    changed.extend(ensure_mcp_servers(root, active_tools, warnings=mcp_warnings))

    # Remove previously-baselined dynamic outputs that stopped being derivable
    # (a workspace-local skill that was removed or renamed). The baseline is the
    # stored manifest loaded at the top of this run, before this run rewrites it
    # below — reading it afterwards would compare the new baseline with itself
    # and find nothing.
    current_render = set(render_files(root, context, active_tools))
    deliverable = manifest.synchronized_paths(root, kit_root, context, active_tools)
    removed: list[str] = []
    stranded: list[str] = []
    removable = _orphaned(root, set(stored["files"]), current_render)
    for relpath in _retired(root, set(stored["files"]), active_tools):
        if relpath not in removable:
            removable.append(relpath)
    for relpath in removable:
        target = root / relpath
        if not fs.exists(target):
            # Already gone. Nothing to delete and nothing to retry: recording it
            # as stranded would re-mark it on every run, and a marker the live
            # map can never show is drift that no upgrade can ever clear.
            removed.append(relpath)
            continue
        if not fs.is_regular_file(target):
            # Present but not something this run will delete — a directory, or a
            # FIFO the user left there. Reported and retried; removing it clears
            # the report.
            stranded.append(relpath)
            continue
        try:
            target.unlink()
        except OSError:
            # A read-only parent or a refusing filesystem must not abort the run
            # after the workspace has already been synchronized; the path is
            # reported below instead, and a later run retries it.
            stranded.append(relpath)
            continue
        removed.append(relpath)

    # Artifact migrations run here and nowhere else: after the kit is
    # synchronized, because a migration may need the new release's own scripts
    # and assets (the atlas renderer is a kit file), and before the version
    # marker below, because that marker is a claim about artifacts.
    if migrate:
        report = migrations.run(root, recorded=recorded, kit_version=version)
        migration_report = {
            "ran": True,
            "applied": [{"id": outcome.migration_id, "actions": list(outcome.actions),
                         "failures": list(outcome.failures)} for outcome in report.applied],
            "satisfied": report.satisfied,
            "undetermined": report.undetermined,
            "pending": [],
            "failures": report.failures,
        }
        # Undetermined is deliberately not a blocker: nothing was attempted, so
        # nothing is half-done. A failure is, because something is.
        artifacts_reached_this_version = report.ok
    else:
        preview = migrations.plan(root, recorded=recorded, kit_version=version)
        migration_report = {
            **_empty_migration_report(),
            "satisfied": preview.satisfied,
            "undetermined": preview.undetermined,
            "pending": [_as_pending(entry) for entry in preview.pending],
        }
        artifacts_reached_this_version = not preview.pending

    # One rule, no exception: the marker moves when the migrations for this
    # version are done. `--no-migrate` is not an exemption from it — advancing
    # the marker over artifacts the operator asked this run to leave alone
    # would turn the flag into a way to record a release they never reached,
    # and `status`'s `version_match` would report the lie as agreement.
    #
    # The manifest above is the opposite case and is written unconditionally:
    # it is a claim about FILES, and the files did move. Holding it back would
    # make `status` report every synchronized file as drift and bury the one
    # fact that matters.
    #
    # The marker is a managed path like any other, so it takes the same gate on
    # both sides: reading a FIFO would block, and writing one would block too —
    # in the command whose whole job is to repair a damaged workspace.
    if artifacts_reached_this_version and read_workspace_version(root, "") != version:
        if fs.write_text(root / ".papersmith" / "version", version + "\n"):
            changed.append(".papersmith/version")
            # The routing docs state the recorded version, and they were
            # rendered above against the marker this run just moved. Left
            # alone, every upgrade across a release ended with
            # `audit --check-drift` reporting those docs as generator drift
            # until a second upgrade re-rendered them.
            skipped_again: list[str] = []
            rerendered = apply_generated(root, context_for_workspace(root), active_tools,
                                         skipped=skipped_again, baseline=stored["files"])
            changed.extend(relpath for relpath in rerendered if relpath not in changed)
            unsynchronized.extend(relpath for relpath in skipped_again
                                  if relpath not in unsynchronized)
        else:
            unsynchronized.append(".papersmith/version")

    framework_files = manifest.workspace_framework_files(root, kit_root)
    for relpath in stranded:
        # Keep an undeletable path in the baseline. It is not part of the current
        # framework set, so recording it makes ``status`` and ``audit`` report it
        # as drift and lets a later upgrade retry the removal; dropping it would
        # strand the file untracked forever.
        target = root / relpath
        framework_files[relpath] = manifest.sha256_if_readable(target) or UNSYNCHRONIZED
    for relpath in deliverable:
        # Every managed path this run was responsible for must be accounted for
        # in the baseline. ``workspace_framework_files`` omits any path it cannot
        # hash — non-regular, never written, or written but still unreadable (a
        # write-only file) — and an omission on both sides of ``status``'s
        # comparison is a false "no drift". Sweeping the whole managed universe,
        # rather than only the paths reported as unsynchronized, is what makes
        # this total: a write can succeed and still leave the path unhashable.
        if relpath not in framework_files:
            framework_files[relpath] = UNSYNCHRONIZED
    manifest.write_manifest(root, version, framework_files, kind="workspace")
    # Every upgrade rewrites the record, including the first one a workspace
    # created before 0.14.0 receives -- which is why that case needs no
    # migration: the files moved, so the record of where they came from moves.
    source_record, source_written = provenance.write_record(root, kit_source,
                                                            allowed_dirty=allowed_dirty)
    return {
        "workspace": str(root),
        "version": version,
        "planned": False,
        "kit_source": source_record,
        "kit_source_unwritten": [] if source_written else [provenance.KIT_SOURCE_RECORD],
        "migrations": migration_report,
        "recorded_version": read_workspace_version(root, "").strip(),
        "active_tools": active_tools,
        "changed_files": changed,
        "preserved_files": preserved,
        "removed": removed,
        "stranded": stranded,
        "unsynchronized": unsynchronized,
        "link_warnings": manifest.link_warnings(link_report),
        "mcp_warnings": mcp_warnings,
        "wiring": wiring.summarize(root, active_tools, link_report, unsynchronized),
    }


def register(subparsers) -> None:
    parser = subparsers.add_parser("upgrade", help="synchronize framework files in a workspace")
    parser.add_argument("directory", nargs="?", default=".", metavar="<dir>")
    parser.add_argument(
        "--tools",
        default=None,
        help="replace active runtime generators (claude, opencode, pi, antigravity/agy)",
    )
    parser.add_argument("--force", action="store_true", help="force framework-file writes")
    parser.add_argument("--allow-downgrade", action="store_true",
                        help="permit installing an older framework version")
    parser.add_argument("--allow-dirty-kit", action="store_true",
                        help="upgrade even when the kit source has uncommitted changes "
                             "under its shipped paths, or its git state cannot be "
                             "determined; the workspace records it")
    parser.add_argument("--no-migrate", dest="migrate", action="store_false",
                        help="synchronize framework files without migrating workspace "
                             "artifacts; the recorded version stays where it is")
    # Deliberately not `--dry-run`: a flag by that name on `upgrade` would
    # imply the kit copy, the projections and the orphan sweep were previewed
    # too, and they are not. One flag must not overstate its reach.
    parser.add_argument("--plan-migrations", action="store_true",
                        help="report the pending artifact migrations and exit, writing nothing")
    parser.set_defaults(handler=run_cli)


def _migration_lines(report: dict) -> list[str]:
    """The report's own lines, so a caller can tell an empty one from a section.

    A migration that failed before doing anything has actions to report: none.
    Deciding the section header from the fact that one RAN printed a label with
    nothing under it, while the line that mattered went to stderr.
    """
    lines: list[str] = []
    for entry in report["pending"]:
        lines.append(f"pending {entry['id']}: {entry['summary']}")
        lines.extend(f"  - {action}" for action in entry["actions"])
    for entry in report["applied"]:
        lines.extend(f"{entry['id']}: {action}" for action in entry["actions"])
    for identifier in report["undetermined"]:
        lines.append(f"undetermined {identifier}: this workspace records no "
                     "orderable version, so nothing places it against the "
                     "migration's gate")
    return lines


def run_cli(args) -> int:
    tools = None
    if args.tools is not None:
        tools = [item.strip() for item in args.tools.split(",") if item.strip()]
    result = upgrade(args.directory, tools=tools, force=args.force,
                     allow_downgrade=args.allow_downgrade, migrate=args.migrate,
                     plan_migrations=args.plan_migrations,
                     allow_dirty_kit=args.allow_dirty_kit)

    if result["planned"]:
        report = result["migrations"]
        print(f"Pending artifact migrations for {result['workspace']} "
              f"at framework version {result['version']}:")
        lines = _migration_lines(report)
        if not lines:
            print("  none; this workspace's artifacts already match the installed release")
        for line in lines:
            print(f"  {line}")
        print("Nothing was written.")
        return 0

    print(f"Upgraded papersmith workspace: {result['workspace']}")
    print(f"Framework version: {result['version']}; changed files: {len(result['changed_files'])}")
    print(f"Kit source: {provenance.describe_record({'recorded': True, **result['kit_source']})}")
    for relpath in result["kit_source_unwritten"]:
        print(f"Warning: could not write '{relpath}'; `status` will report the kit "
              "source as unknown")
    for relpath in result["unsynchronized"]:
        print(f"Warning: could not write '{relpath}'; it stays reported as drift")
    print("Harness wiring:")
    for line in wiring.format_summary(result["wiring"]):
        print(f"  {line}")
    for warning in result["link_warnings"] + result.get("mcp_warnings", []):
        print(f"Warning: {warning}")
    for line in kaggle_mcp.summary_lines(_active_tools_of(result)):
        print(line)

    report = result["migrations"]
    lines = _migration_lines(report)
    if lines:
        print("Artifact migrations:")
        for line in lines:
            print(f"  {line}")
    # Say which version the workspace actually records, every time the two
    # disagree. A held-back marker that nothing reports is the same silence as
    # a marker that moved without its artifacts.
    if result["recorded_version"] != result["version"]:
        print(f"Recorded version stays at {result['recorded_version'] or '(none)'}: "
              f"the artifact migrations for {result['version']} are not done. "
              "Re-run `smith upgrade` once their cause is fixed.")
    if report["failures"]:
        for failure in report["failures"]:
            print(f"Migration failed: {failure}", file=sys.stderr)
        return EXECUTION_ERROR
    return 0


def _active_tools_of(result: dict) -> list[str]:
    """The harnesses this run wired, for the offline Kaggle MCP summary."""
    wiring = result.get("wiring")
    if isinstance(wiring, dict):
        return [str(tool) for tool in wiring]
    if isinstance(wiring, list):
        return [str(item.get("tool")) for item in wiring if isinstance(item, dict) and item.get("tool")]
    return []
