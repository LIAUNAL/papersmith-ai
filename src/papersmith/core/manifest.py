"""Workspace and kit manifests: SHA-256 tracking, filtering, preservation.

Two manifests exist:

* ``kit-manifest.json`` at the kit root — hashes of every framework file the
  kit ships (written by ``scripts/build-kit.py``; computed on the fly when a
  development checkout has none).
* ``<workspace>/.papersmith/manifest.json`` — hashes of every
  framework-managed file as it exists in that workspace, plus the workspace
  version and update timestamp.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from ..errors import UserError
from ..generators import MANAGED_BLOCK_FILES, managed_view, render_files, workspace_tools
from . import fs

MANIFEST_SCHEMA = 1

#: The workspace version marker. It is neither a kit file nor a rendered output,
#: so it is named once here and included in :func:`synchronized_paths`
#: explicitly.
VERSION_MARKER = ".papersmith/version"

# The kit's top-level entries a workspace copies at init and re-syncs on
# upgrade. Everything else a workspace holds is either generated (rendered
# entrypoint docs) or preserved research state.
#
# ``guidance/paper-guide`` is deliberately absent: its real content is
# third-party reference PDFs, and this repository's own ``.gitignore``
# (``guidance/*/*``) keeps them out of git on purpose. ``walk_kit_files``
# walks the filesystem, not git, so listing that directory here would bundle
# whatever a maintainer's checkout happens to hold into every shipped kit. The
# folder still reaches a fresh workspace empty, via ``_create_topology``'s
# ``.gitkeep``.
#
# ``sections`` travels WITH content: the ten ``sections/*.md`` files are
# generic writing contracts, not this paper's own research, so a workspace
# needs the same bytes this repository ships — like ``skills``, not like
# ``guidance/paper-guide``.
KIT_ENTRIES = (
    "skills",
    "sections",
    "sections-review",
    ".claude/agents",
    "scripts/setup_env.py",
    "scripts/setup-harnesses.sh",
    "requirements.txt",
)

# Paths ``upgrade`` must never overwrite or delete. ``papersmith.yaml`` and
# ``package.json`` are seeded once at init (see ``init._write_workspace_seed``),
# like Pi's ``.pi/settings.json`` (see ``generators.seed_pi_settings``),
# and then belong to the user like ``README.md`` does; the rest is research
# state the user produces under the topology ``init`` scaffolds.
PRESERVE_PATTERNS = (
    "guidance/**",
    "proposals/**",
    "paper/**",
    "experiments/**",
    "implementations/**",
    "kaggle-inbox/**",
    "review/**",
    "papersmith.yaml",
    "package.json",
    "README.md",
    ".pi/settings.json",
    ".mcp.json",
    ".pi/mcp.json",
    ".agents/mcp_config.json",
    ".env*",
)

_SKIP_DIRS = {".venv", "node_modules", "__pycache__", ".pytest_cache", ".micromamba", ".git"}
_SKIP_SUFFIXES = (".pyc", ".pyo")
_KEEP_HIDDEN = {".gitignore", ".gitkeep"}
_STORE_DIR = "skills/kaggle-accounts/store"


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def is_preserved(relpath: str) -> bool:
    """True when ``upgrade`` must never overwrite or delete the path."""
    posix = relpath.replace("\\", "/")
    name = posix.rsplit("/", 1)[-1]
    for pattern in PRESERVE_PATTERNS:
        if pattern.endswith("/**"):
            prefix = pattern[:-3]
            if posix == prefix or posix.startswith(prefix + "/"):
                return True
        elif pattern.endswith("*") and pattern.startswith("."):
            if name.startswith(pattern[:-1]):
                return True
        elif posix == pattern:
            return True
    return False


def should_skip_file(path: Path) -> bool:
    name = path.name
    if name.startswith(".") and name not in _KEEP_HIDDEN:
        return True
    return path.suffix in _SKIP_SUFFIXES


def should_skip_dir(path: Path) -> bool:
    return path.name in _SKIP_DIRS


def _walk_dir(root: Path, kit_root: Path, files: dict[str, str]) -> None:
    try:
        children = sorted(root.iterdir())
    except OSError:
        return
    for child in children:
        if fs.is_dir(child):
            if should_skip_dir(child):
                continue
            if child.relative_to(kit_root).as_posix() == _STORE_DIR:
                # The credential store ships only its protective .gitignore —
                # a stored token committed is a token burned.
                store = []
                try:
                    store = sorted(child.iterdir())
                except OSError:
                    pass
                for entry in store:
                    if fs.is_regular_file(entry) and entry.name == ".gitignore":
                        files[entry.relative_to(kit_root).as_posix()] = sha256_file(entry)
                continue
            _walk_dir(child, kit_root, files)
            continue
        # A non-regular entry is not a framework file, and hashing one would
        # block forever on a FIFO rather than report the damaged kit source.
        if should_skip_file(child) or not fs.is_regular_file(child):
            continue
        files[child.relative_to(kit_root).as_posix()] = sha256_file(child)


def walk_kit_files(kit_root: Path) -> dict[str, str]:
    """relpath -> sha256 for every file the kit ships, filtered."""
    files: dict[str, str] = {}
    for entry in KIT_ENTRIES:
        path = kit_root / entry
        if not fs.exists(path):
            continue
        if fs.is_regular_file(path):
            files[entry] = sha256_file(path)
        else:
            _walk_dir(path, kit_root, files)
    return files


#: Harness directories that read the workspace's skills through a projected
#: symlink to the canonical ``skills/`` tree — the same shape
#: ``scripts/setup-harnesses.sh`` creates for this repository's own checkout
#: (see that script; it targets the identical four paths). A generated
#: workspace needs this wired at ``init`` time, not left for the operator to
#: reproduce by hand with a separate setup step.
#:
#: Each entry is an explicit ``(tool, relpath)`` pair: the owning tool is never
#: derived from the path, because a harness may read its skills from a
#: directory that does not carry its name (Antigravity documents
#: ``.agents/skills``).
HARNESS_SKILL_LINKS: tuple[tuple[str, str], ...] = (
    ("claude", ".claude/skills"),
    ("pi", ".pi/skills"),
    ("opencode", ".opencode/skills"),
    ("antigravity", ".agents/skills"),
)


@dataclass(frozen=True)
class LinkReport:
    """Outcome of one :func:`link_harness_skills_report` pass, by relpath.

    ``linked`` holds the links this call created or repaired; a link that was
    already correct appears in no bucket. ``failed`` holds paths where creating
    the link raised :class:`OSError` (no symlink privilege, read-only mount,
    unwritable parent). ``blocked`` holds paths occupied by real, non-symlink
    content that this call refuses to touch.
    """

    linked: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    blocked: list[str] = field(default_factory=list)


def link_harness_skills_report(root: Path, tools: Sequence[str] | None = None) -> LinkReport:
    """Create or repair the relative ``skills`` symlink for each selected harness.

    Mirrors ``scripts/setup-harnesses.sh``: relative (so the workspace stays
    relocatable) and idempotent (re-running converges to the same layout — a
    stale symlink with the wrong target is replaced, never nested into). A
    path already holding real, non-symlinked content is left untouched, never
    deleted, and reported as ``blocked``. A path whose link could not be
    created is reported as ``failed``. Files are never copied as a fallback:
    the canonical ``skills/`` tree stays the single copy. ``tools`` narrows
    which harnesses are linked; ``None`` links all of them.
    """
    report = LinkReport()
    canonical = root / "skills"
    if not fs.is_dir(canonical):
        return report
    for tool, relpath in HARNESS_SKILL_LINKS:
        if tools is not None and tool not in tools:
            continue
        target = root / relpath
        want = os.path.relpath(canonical, target.parent)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.is_symlink():
                if os.readlink(target) == want:
                    continue
            elif target.exists():
                report.blocked.append(relpath)
                continue
            # Build the replacement next to `target` and rename it into
            # place atomically, so a failed create never leaves `target`
            # deleted with nothing put back (os.replace(2) has no such gap;
            # unlink-then-symlink_to does).
            tmp = target.with_name(target.name + ".papersmith-tmp")
            tmp.unlink(missing_ok=True)
            tmp.symlink_to(want)
            tmp.replace(target)
        except OSError:
            report.failed.append(relpath)
            continue
        report.linked.append(relpath)
    return report


def link_harness_skills(root: Path, tools: Sequence[str] | None = None) -> list[str]:
    """Return only the relpaths :func:`link_harness_skills_report` linked.

    Kept for callers that only need the created or repaired paths; those that
    must tell an operator about failures use the report variant.
    """
    return link_harness_skills_report(root, tools).linked


def link_warnings(report: LinkReport) -> list[str]:
    """One operator-facing warning per failed or blocked link path."""
    warnings = [
        f"harness skills link '{relpath}' could not be created; skills are not "
        "linked there (re-run `smith upgrade` once the cause is fixed)"
        for relpath in report.failed
    ]
    warnings.extend(
        f"harness skills link '{relpath}' not linked: real content occupies the "
        "path and was left untouched (move it aside to wire the link)"
        for relpath in report.blocked
    )
    return warnings


def copy_kit_file(kit_root: Path, relpath: str, dest_root: Path,
                  dest_relpath: str | None = None) -> bool:
    """Copy one kit file into a workspace, or report that it could not be done.

    ``dest_relpath`` is where the file lands when the paper line serves it at
    another path (:func:`kit_layout`); it defaults to ``relpath``.

    ``shutil.copyfile`` opens the destination for writing, so a FIFO there would
    block forever and a directory would raise — after earlier paths in the same
    run have already been synchronized. Returns False instead.
    """
    return fs.copy_file(kit_root / relpath, dest_root / (dest_relpath or relpath))


def load_manifest(workspace: Path) -> dict | None:
    path = workspace / ".papersmith" / "manifest.json"
    if not fs.is_regular_file(path):
        if fs.exists(path):
            raise UserError(f"corrupted manifest {path}: not a readable regular file")
        return None
    text = fs.read_text(path)
    if text is None:
        raise UserError(f"corrupted manifest {path}: unreadable or not valid UTF-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise UserError(f"corrupted manifest {path}: {exc}") from None
    if not isinstance(data, dict) or data.get("kind") != "workspace":
        raise UserError(f"corrupted manifest {path}: missing workspace envelope")
    if data.get("schema") != MANIFEST_SCHEMA or not isinstance(data.get("version"), str):
        raise UserError(f"corrupted manifest {path}: unsupported schema or version")
    files = data.get("files")
    if not isinstance(files, dict) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in files.items()
    ):
        raise UserError(f"corrupted manifest {path}: files must be a string-to-string map")
    return data


def write_manifest(dest_root: Path, version: str, files: dict[str, str], *, kind: str,
                   build: dict | None = None) -> None:
    """Write a workspace or kit manifest.

    ``build`` (kit manifests only) carries the build provenance -- ``commit``
    and ``dirty`` of the tree the kit was copied from -- that
    :mod:`papersmith.core.provenance` reads back for a bundled kit.
    """
    payload = {
        "schema": MANIFEST_SCHEMA,
        "kind": kind,
        "version": version,
        "files": dict(sorted(files.items())),
    }
    if build is not None:
        if kind != "kit":
            raise ValueError("build provenance belongs to a kit manifest only")
        payload.update({"commit": build.get("commit"), "dirty": build.get("dirty")})
    if kind == "workspace":
        payload["updated_at"] = _timestamp()
        path = dest_root / ".papersmith" / "manifest.json"
    elif kind == "kit":
        payload["generated_at"] = _timestamp()
        path = dest_root / "kit-manifest.json"
    else:
        raise ValueError(f"unknown manifest kind {kind!r}")
    if not fs.write_text(path, json.dumps(payload, indent=2) + "\n"):
        raise UserError(f"could not write {path}")


def load_kit_manifest(kit_root: Path) -> dict | None:
    path = kit_root / "kit-manifest.json"
    if not fs.is_regular_file(path):
        if fs.exists(path):
            raise UserError(f"corrupted kit manifest {path}: not a readable regular file")
        return None
    text = fs.read_text(path)
    if text is None:
        raise UserError(f"corrupted kit manifest {path}: unreadable or not valid UTF-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise UserError(f"corrupted kit manifest {path}: {exc}") from None
    if not isinstance(data, dict) or data.get("kind") != "kit":
        raise UserError(f"corrupted kit manifest {path}: missing kit envelope")
    if data.get("schema") != MANIFEST_SCHEMA or not isinstance(data.get("version"), str):
        raise UserError(f"corrupted kit manifest {path}: unsupported schema or version")
    return data


def kit_files(kit_root: Path) -> dict[str, str]:
    """relpath -> sha256 for the kit's framework files.

    A bundled kit answers from its manifest; a development checkout has none
    and is hashed live so ``upgrade`` always tracks the latest dev state.
    """
    cached = load_kit_manifest(kit_root)
    if cached is not None:
        files = cached.get("files")
        if isinstance(files, dict) and all(isinstance(v, str) for v in files.values()):
            return dict(files)
        raise UserError(f"corrupted kit manifest at {kit_root}: bad files map")
    return walk_kit_files(kit_root)


#: The paper lines a workspace can follow. ``experimental`` is the original
#: line and the default of every workspace that records no kind.
PAPER_KINDS = ("experimental", "review")
DEFAULT_PAPER_KIND = "experimental"

#: Kit paths that belong to the review line only. An experimental workspace
#: never receives them, so its files stay exactly what they were before the
#: review line existed.
REVIEW_ONLY_PREFIXES = ("sections-review/", "skills/systematic-review/")
_REVIEW_SECTIONS = "sections-review/"
_SECTIONS = "sections/"
#: Experimental section contracts the review line keeps as they are: the
#: back matter is the same accountability surface for both lines.
REVIEW_SHARED_SECTIONS = ("sections/10-back-matter.md",)


def paper_kind(workspace: Path) -> str:
    """The paper line a workspace follows, from ``.papersmith/config.json``.

    A workspace without the key (every workspace made before the review line,
    and every experimental one) is experimental. An unknown value refuses,
    because copying the wrong line's files into a workspace is not repairable
    by a later run.
    """
    text = fs.read_text(workspace / ".papersmith" / "config.json")
    if text is None:
        return DEFAULT_PAPER_KIND
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return DEFAULT_PAPER_KIND
    kind = data.get("paper_kind", DEFAULT_PAPER_KIND) if isinstance(data, dict) else DEFAULT_PAPER_KIND
    if kind not in PAPER_KINDS:
        raise UserError(f"unknown paper_kind {kind!r} in {workspace / '.papersmith' / 'config.json'}; "
                        f"expected one of {', '.join(PAPER_KINDS)}")
    return kind


def kit_layout(kit_root: Path, kind: str = DEFAULT_PAPER_KIND) -> dict[str, str]:
    """Workspace relpath -> kit relpath for the files a ``kind`` workspace gets.

    The experimental line maps every kit file onto itself except the
    review-only ones. The review line drops the experimental section contracts
    (but the shared back matter) and serves ``sections-review/<file>`` at
    ``sections/<file>``, so every consumer that globs ``sections/*.md`` reads
    the review contracts unchanged.
    """
    if kind not in PAPER_KINDS:
        raise UserError(f"paper kind must be one of {', '.join(PAPER_KINDS)}")
    layout: dict[str, str] = {}
    for relpath in kit_files(kit_root):
        if kind == "experimental":
            if not relpath.startswith(REVIEW_ONLY_PREFIXES):
                layout[relpath] = relpath
        elif relpath.startswith(_REVIEW_SECTIONS):
            layout[_SECTIONS + relpath[len(_REVIEW_SECTIONS):]] = relpath
        elif not relpath.startswith(_SECTIONS) or relpath in REVIEW_SHARED_SECTIONS:
            layout[relpath] = relpath
    return layout


def kit_version(kit_root: Path) -> str:
    cached = load_kit_manifest(kit_root)
    if cached is not None and isinstance(cached.get("version"), str):
        return cached["version"]
    pkg = kit_root / "package.json"
    text = fs.read_text(pkg)
    if text is not None:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict) and isinstance(data.get("version"), str):
            return data["version"]
    return "0.0.0"


def sha256_if_readable(path: Path) -> str | None:
    """``sha256_file`` for a path that may be absent or unreadable.

    A framework-managed file can be missing, permission-denied, or otherwise
    unstatable. The manifest records what it can actually read rather than
    aborting its caller: ``status`` and ``audit`` must report a damaged
    workspace, not die on one.
    """
    if not fs.is_regular_file(path):
        return None
    try:
        return sha256_file(path)
    except OSError:
        return None


def _managed_digest(path: Path, relpath: str) -> str | None:
    if not fs.is_regular_file(path):
        return None
    try:
        view = managed_view(relpath, path.read_bytes())
    except OSError:
        return None
    # Unverifiable (malformed markers): omitted, so the baseline writer records
    # it as unsynchronized and ``status`` keeps reporting it.
    return None if view is None else hashlib.sha256(view).hexdigest()


def synchronized_paths(workspace: Path, kit_root: Path, context: dict | None = None,
                       tools: list[str] | tuple[str, ...] | None = None) -> set[str]:
    """Every path a run is responsible for *delivering* into a workspace.

    This is the set a baseline writer must sweep: :func:`workspace_framework_files`
    records a hash for each of these, but silently omits any it cannot read, and a
    path absent from both the live and the stored map is invisible to ``status`` —
    which is how a damaged path turns into a false "no drift".

    **Preserved paths are excluded.** ``guidance/**``, ``README.md``,
    ``papersmith.yaml`` and friends are the user's by contract
    (:func:`is_preserved`); a run never delivers them, so it must not demand them.
    Marking one because the user deleted it — or because a newer kit added a file
    the workspace predates — would record drift that no ``upgrade`` can ever
    clear, since ``upgrade`` skips preserved paths on every run.

    Kept here, beside the manifest it describes, so the components cannot drift
    from what :func:`workspace_framework_files` actually records.
    """
    deliverable = {relpath for relpath in kit_layout(kit_root, paper_kind(workspace))
                   if not is_preserved(relpath)}
    rendered = render_files(workspace, context, tools or workspace_tools(workspace))
    return deliverable | set(rendered) | {VERSION_MARKER}


def workspace_framework_files(workspace: Path, kit_root: Path,
                              context: dict | None = None, *,
                              notes: list[str] | None = None) -> dict[str, str]:
    """Current hashes of every framework-managed file in a workspace.

    The rendered contribution derives from :func:`generators.render_files` — the
    single path authority — instead of a second, hand-maintained path list. The
    stored baseline, ``status`` and ``audit`` therefore all see the same set,
    dynamic per-skill command files included, and cannot drift apart.

    ``context`` is optional so the existing two-argument callers keep working: a
    caller that already built one may pass it, and it is derived here otherwise.

    A path this cannot read is **omitted**, not marked — see
    :func:`synchronized_paths` for why the baseline writer has to account for
    that.

    ``notes`` collects the projection notes rendering produces (a Claude tool
    a runtime has no counterpart for, a skipped definition). Without it they
    are emitted as one ``UserWarning``, as before; the read-only ``status`` and
    ``audit`` pass a list so they report them only when asked.
    """
    files: dict[str, str] = {}
    for relpath in kit_layout(kit_root, paper_kind(workspace)):
        digest = sha256_if_readable(workspace / relpath)
        if digest is not None:
            files[relpath] = digest
    rendered = render_files(workspace, context, workspace_tools(workspace), warnings=notes)
    for relpath in rendered:
        if relpath in MANAGED_BLOCK_FILES:
            # Only the block is the framework's; lines the workspace added
            # outside it are not drift (``generators.managed_view``).
            digest = _managed_digest(workspace / relpath, relpath)
        else:
            digest = sha256_if_readable(workspace / relpath)
        if digest is not None:
            files[relpath] = digest
    version_digest = sha256_if_readable(workspace / VERSION_MARKER)
    if version_digest is not None:
        files[VERSION_MARKER] = version_digest
    return files
