#!/usr/bin/env python3
"""Generate a forge-owned, service-blind job folder for a target repository.

`generate_job()` is the whole of `generate-job` (driven by `remote_cli.py`,
which loads this module the same sibling way it loads `ledger.py`,
`packer.py` and `adapter.py`). It builds `<target>/tools/<service>/
<job-name>/`: `runner.ipynb`, `run-config.json`, and one adapter-supplied
metadata file — writing the metadata file's bytes and filename opaquely, as
returned by `ADAPTER.resolve_metadata(service)`, without ever learning what
either one means (see `adapter.py`'s own docstring on that registry).

`--target` is resolved first, and every path this module touches —
`resolve_destination()`'s containment check, the `.partial/` build
directory, the final rename — is derived from that resolved value, never
from the raw argument. Generation refuses when the derived destination is
not a directory inside the resolved target, which is what stands between a
crafted `--service`/`--job-name` (`../../etc`, say) and a write outside the
target repository entirely.

`verify_pin_preconditions()` runs next, before `resolve_clone_paths()` or
any write. It is the ONE home for every condition a pin must satisfy
before anything irreversible happens, and the only thing either decision
point calls — `generate-job` here, and `remote_cli.py`'s `submit` — with
exactly one word different between them: the `decision` that appears in
the refusal. Conditions run in `PIN_CONDITIONS` order, cheapest first,
and the first failure raises. Two call sites and the pin conditions
could otherwise drift in order, or omit one on one side, with nothing
in the code to say so.

The `clean-worktree` condition is `git status --porcelain` over the
declared clone paths, and `git diff` would be the wrong instrument rather
than a slower one: `diff` enumerates changes to TRACKED content, so an
untracked path is outside its domain by construction. That is the exact
case this condition exists to catch, because `resolve_clone_paths()`
below walks the WORKING TREE: a brand-new module that was never `git
add`ed passes the import walk and is simply absent from the commit the
runner clones, and the job dies in the kernel with `ModuleNotFoundError`
after quota is spent. Nothing here stages, commits, stashes or fetches on
the operator's behalf, and there is deliberately no flag that accepts a
dirty tree.

The `pin-published` condition is `_verify_commit_reachable()`, before
any write: `--commit` proving out with `git cat-file -e` only shows the pin
exists in the LOCAL checkout that ran `generate-job` — it says nothing
about whether the declared `--repo-url` can actually serve it, which is
what a runner needs when it clones that remote and checks out the
pin inside the kernel. `git ls-remote <repo-url> <commit>` cannot answer
this for a bare commit SHA (`ls-remote` matches ref *names*; a 40-hex pin
that is not literally a branch/tag name comes back empty with exit 0
either way), so this uses the accurate equivalent instead: `git fetch
--dry-run --depth 1 <repo-url> <commit>`, which the remote's own
upload-pack either serves or refuses with "not our ref".

That fetch is issued from a scratch repository made for it and thrown
away after — never from the target. Every sentence above was true of the
first version of this check and it still could not fire, because it asked
from inside the target: a repository holding the pin answers the `want`
out of its own object store without the remote's upload-pack being
consulted at all, and the repository the operator just committed in
always holds the pin. The depth matches the runner's own fetch
(`assets/runner_bootstrap.py:169`); `--dry-run` suppresses ref updates
but NOT object transfer, so a probe run in the target would also deposit
the remote's whole shallow tree there on every generation — 12.8 MiB of
it, measured, for the repository this skill targets.

Fails closed exactly like `computedNotDeclared`, never a warning, and
closed on an unanswerable network failure too: an unresolved DNS lookup
cannot confirm reachability any more than it can deny it, and generation
is local and free to re-run, so "cannot determine" refuses exactly like
"confirmed absent" rather than risking a silent pass on the one path this
check exists to close.

`resolve_clone_paths()` is the AST-based, transitive dependency check:
declared `clonePaths` are cross-checked against what the declared entry
modules (`run.module`, plus `run.smoke.module` when present) actually
import, transitively, before a job folder is ever written. A real import
missing from `clonePaths` (`computedNotDeclared`) always refuses
generation; an import this walk cannot resolve with confidence (a
non-literal `importlib.import_module(...)` call, any `__import__(...)`
call, a `sys.path` mutation, an unparsable file, or an import that looks
like this repository's own code but does not resolve to a file on disk)
also refuses, unless `--accept-unresolved` is passed — which records the
uncertainty in `run-config.json`'s `unresolvedImports` instead of silently
guessing. See `resolve_clone_paths()`'s own docstring for the full rule.

Run with any Python 3.10+ (stdlib-only):
    python3 -m unittest tests.test_remote_execution
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, Sequence


def _load_adapter_seam():
    """Path-import `adapter.py`, one directory up from this file, reusing an
    already-loaded copy under `remote_execution_adapter` when one exists —
    the same `sys.modules`-reuse idiom every other sibling loader in this
    skill uses, for the same reason: a second, separately exec'd copy would
    define a second, distinct `Adapter`/`CredentialHandle` with the same
    name.
    """
    module_name = "remote_execution_adapter"
    if module_name in sys.modules:
        return sys.modules[module_name]
    import importlib.util

    script = Path(__file__).resolve().parent / "adapter.py"
    spec = importlib.util.spec_from_file_location(module_name, script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


ADAPTER = _load_adapter_seam()


class JobFolderError(Exception):
    """Generation refused before writing anything a later step couldn't undo."""


class GitTimeoutError(JobFolderError):
    """A git subprocess `_run_git()` invoked expired its own timeout budget
    before finishing — a DISTINCT subclass of `JobFolderError`, never the
    same generic instance a non-zero exit or an `OSError` raises (Finding 4
    case A). `except JobFolderError` still catches this — it IS one, so
    nothing that only asks "did generation refuse" changes — but a caller
    that needs to say WHY, like `_verify_commit_reachable()`'s own
    refusal, can now tell "the question could not be finished asking"
    apart from "the remote answered no". Sharing one message between the
    two once let a slow-but-otherwise-successful fetch get reported as
    though the remote had refused the commit outright — a true
    measurement (the transfer exceeded the budget) producing a false
    conclusion (the commit must be unpublished) — which is the exact
    misdiagnosis this distinction exists to end.
    """


TOOLS_DIRNAME = "tools"
RUN_CONFIG_FILENAME = "run-config.json"
RUNNER_FILENAME = "runner.ipynb"
PARTIAL_SUFFIX = ".partial"
STALE_SUFFIX_PREFIX = ".stale-"
RUN_CONFIG_SCHEMA_VERSION = 1

# `scripts/jobfolder.py` -> `scripts/` -> `remote-execution/` -> `assets/`.
# Holds the two runner assets' real, byte-for-byte-copied content;
# referenced here so every caller — this module's own `generate_job()`,
# `remote_cli.py`'s CLI wiring, and each test fixture alike — points at the
# exact same two paths.
ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
DEFAULT_BOOTSTRAP_ASSET = ASSETS_DIR / "runner_bootstrap.py"
DEFAULT_INVOKE_ASSET = ASSETS_DIR / "runner_invoke.py"

REQUIRED_RUN_CONFIG_FIELDS = (
    "schemaVersion", "product", "service", "jobName", "commit", "repo",
    "clonePaths", "run", "runnerTemplate",
)

# A pin is an object name, never a name that resolves to one. Lowercase
# hex, 40 characters (sha1) or 64 (sha256) — the two full object-name
# widths git writes; nothing shorter, because an abbreviated name is
# ambiguous by construction, and nothing uppercase, because git never
# writes one and accepting it would make two spellings of the same pin
# compare unequal in `readiness`'s `latest.commit == run_config["commit"]`
# binding.
#
# This is not a cosmetic tightening. `--commit main` satisfied every
# other guard in this module: the reachability probe succeeds because
# `main` really is a ref the remote can serve, `_staleness_for()`'s
# `cat-file -e main^{commit}` succeeds because `main` really does resolve
# locally, and the staleness diff compares `main` against `HEAD`, which
# is usually the same commit. The job folder then records the string
# `"main"` as the code that produced a number, and the runner checks out
# whatever `main` points at on the day it runs. A pin that moves,
# recorded as if it were immutable, with every downstream check agreeing.
COMMIT_PATTERN = re.compile(r"\A(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")


def resolve_target(target: str | Path) -> Path:
    """Resolve `--target` to an absolute path and refuse anything that is
    not an existing directory — the very first thing `generate_job()` does,
    before any other check.
    """
    resolved = Path(target).resolve()
    if not resolved.is_dir():
        raise JobFolderError(
            f"--target {resolved} does not resolve to an existing directory"
        )
    return resolved


def resolve_destination(target: Path, service: str, job_name: str) -> Path:
    """Derive `<target>/tools/<service>/<job-name>/`, resolved, and refuse
    it outright when the resolved result does not stay under `target` —
    the one check that stands between a crafted `service`/`job_name`
    containing `..` and a write landing outside the target repository.
    """
    destination = (target / TOOLS_DIRNAME / service / job_name).resolve()
    try:
        destination.relative_to(target)
    except ValueError:
        raise JobFolderError(
            f"refusing destination {destination}: it does not stay under "
            f"resolved target {target} at all"
        ) from None
    return destination


def validate_clone_paths(
    clone_paths: Sequence[str], target: Path | None = None
) -> tuple[str, ...]:
    """Structural validation — empty is refused; an absolute path or one
    containing `..` is refused. When `target` is given, each path is also
    resolved against it and refused if that resolution escapes `target` —
    the symlink-escape case a purely textual check cannot see (a clone path
    whose name is safe in text but whose real, resolved location leaves the
    target directory through a symlink).

    This is the SAME validator every caller uses — `build_run_config()` at
    generation time (structural only, no `target` yet resolved), and
    `resolve_clone_paths()` again once `target` is known — never a second,
    parallel validator for the symlink case.
    """
    if not clone_paths:
        raise JobFolderError("clonePaths must not be empty")
    validated = []
    for raw in clone_paths:
        candidate = Path(raw)
        if candidate.is_absolute():
            raise JobFolderError(f"refusing absolute clone path {raw!r}")
        if ".." in candidate.parts:
            raise JobFolderError(f"refusing clone path {raw!r}: contains '..'")
        if target is not None:
            # `.resolve()` on both sides: macOS resolves `/var` through
            # `/private/var`, so an unresolved `target` (e.g. straight out
            # of `tempfile.TemporaryDirectory()`) would otherwise never
            # compare equal to a fully-resolved clone path candidate.
            resolved_target = target.resolve()
            resolved = (resolved_target / candidate).resolve()
            try:
                resolved.relative_to(resolved_target)
            except ValueError:
                raise JobFolderError(
                    f"refusing clone path {raw!r}: resolves to {resolved}, "
                    f"outside target {resolved_target} (symlink escape)"
                ) from None
        validated.append(candidate.as_posix())
    return tuple(validated)


def validate_carry_paths(carry_paths: Sequence[str]) -> tuple[str, ...]:
    """The paths, relative to the product folder, whose contents a
    continuation of this job needs carried from the session before it
    (kernel-carry S1): checkpoints, per-unit records, studies. Each must be
    a non-empty relative path with no `..`, the same structural rule
    `validate_clone_paths()` holds, because the runner copies each one
    into its own working directory and a path that escapes it would write
    somewhere nothing fetches. An empty sequence is valid and means the
    job declares none.
    """
    validated = []
    for raw in carry_paths:
        if not isinstance(raw, str) or not raw.strip():
            raise JobFolderError(f"refusing carry path {raw!r}: must be a non-empty string")
        candidate = Path(raw)
        if candidate.is_absolute():
            raise JobFolderError(f"refusing absolute carry path {raw!r}")
        if ".." in candidate.parts:
            raise JobFolderError(f"refusing carry path {raw!r}: contains '..'")
        validated.append(candidate.as_posix())
    return tuple(validated)


def with_entry_notebooks(
    clone_paths: Sequence[str], notebooks: Sequence[str]
) -> list[str]:
    """The declared clone paths plus every entry notebook no declared path
    already covers, appended as a clone path of its own (S1).

    The notebook a job runs is the only notebook it needs. Declaring its
    whole folder made every notebook beside it part of the pin, so an
    unrelated notebook re-run and committed staled the job (`pin-is-head`)
    and forced the smoke and the launch chain again. A declared path is
    never dropped or narrowed: a declared folder that covers the notebook
    is kept exactly as declared, and nothing is appended.

    A file clone path is delivered by `git sparse-checkout set` in both
    modes: non-cone matches the file itself, and cone mode (the default
    since git 2.37) includes every file directly inside the notebook's
    parent directories — siblings arrive too, read from the same pinned
    commit, but only the declared notebook enters staleness.
    """
    result = list(clone_paths)
    for raw in notebooks:
        notebook = validate_notebook_path(raw, where="generation's run block")
        if not _covered_by_declared(notebook, result):
            result.append(notebook)
    return result


def _module_to_relpath(dotted: str, source: Path) -> Path | None:
    """Resolve a dotted module name to the `.py` file it names under
    `source` (`<target>/src`) — a package's `__init__.py` when the dotted
    name is itself a package, else a plain module file. `None` when neither
    exists.
    """
    parts = dotted.split(".")
    package_init = source.joinpath(*parts) / "__init__.py"
    plain_module = source.joinpath(*parts[:-1], parts[-1] + ".py")
    if package_init.is_file():
        return package_init
    if plain_module.is_file():
        return plain_module
    return None


def _classify_import(
    dotted: str, source: Path, *, is_entry: bool
) -> tuple[str, str | None, Path | None]:
    """Classify one dotted import name against `source` (`<target>/src`).

    `("internal", clone_path, file)` — this repository's own code;
    `clone_path` is the granularity-rule top-level clone path (`src/A` for
    a package, `src/A.py` for a true top-level module) it belongs under,
    and `file` feeds the transitive walk.

    `("unresolved", None, None)` — looks like this repository's own code
    (an entry module, or a top-level segment that exists under `source`)
    but the dotted path itself does not resolve to a file on disk.

    `("external", None, None)` — filtered: the top-level segment names
    nothing under `source` at all, so this is not this repository's own
    code and never becomes a clone path or an uncertainty. An entry module
    is deliberately never given this exemption — its own absence on disk
    is exactly the "resolves to nothing" uncertainty, not something to
    skip quietly, since an entry module is by definition meant to be this
    repository's own code.
    """
    top = dotted.split(".", 1)[0]
    top_dir = source / top
    top_file = source / f"{top}.py"
    looks_internal = top_dir.is_dir() or top_file.is_file()
    if not looks_internal:
        return ("unresolved" if is_entry else "external"), None, None
    clone_path = f"src/{top}" if top_dir.is_dir() else f"src/{top}.py"
    file = _module_to_relpath(dotted, source)
    if file is None:
        return "unresolved", None, None
    return "internal", clone_path, file


def _is_dunder_import_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "__import__"
    )


def _is_import_module_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Attribute) and func.attr == "import_module":
        return True
    return isinstance(func, ast.Name) and func.id == "import_module"


def _literal_import_module_argument(node: ast.Call) -> str | None:
    if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
        return node.args[0].value
    return None


def _is_sys_path_target(expr: ast.AST) -> bool:
    return (
        isinstance(expr, ast.Attribute)
        and expr.attr == "path"
        and isinstance(expr.value, ast.Name)
        and expr.value.id == "sys"
    )


def _is_sys_path_mutation(node: ast.AST) -> bool:
    """`sys.path.append/insert/extend/remove/pop(...)`, `sys.path = ...`,
    `sys.path[...] = ...`, or `sys.path += ...` — any mutation of
    `sys.path`, which can change what a later import in the same file
    resolves to and makes this walk's own resolution uncertain.
    """
    if isinstance(node, ast.Call):
        func = node.func
        return (
            isinstance(func, ast.Attribute)
            and func.attr in ("append", "insert", "extend", "remove", "pop")
            and _is_sys_path_target(func.value)
        )
    if isinstance(node, ast.Assign):
        return any(_is_sys_path_target(t) for t in node.targets)
    if isinstance(node, ast.AugAssign):
        return _is_sys_path_target(node.target)
    return False


# ---------------------------------------------------------------------------
# Undeclared-read detection (Unit 1, same-file) — reuses the AST tree
# resolve_clone_paths() already parses for import classification; no new
# file traversal.
# ---------------------------------------------------------------------------


def _shadowed_names(tree: ast.Module) -> set[str]:
    """Every name bound anywhere in a non-module scope — a function or
    lambda parameter, or an assignment/`for`/`with`/comprehension/`except`
    target inside a function or class body. Any such name must never
    resolve through `_fold_module_constants()`'s table, even at a module
    scope occurrence of the same spelling, because a read call site using
    that name cannot be told apart from the local it might actually name
    without full scope resolution — which this walk deliberately does not
    do. Conservative by construction: over-collecting only pushes more
    cases into `unresolvedReads`, never the reverse.
    """
    shadowed: set[str] = set()

    def add_target(target: ast.AST) -> None:
        if isinstance(target, ast.Name):
            shadowed.add(target.id)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for elt in target.elts:
                add_target(elt)
        elif isinstance(target, ast.Starred):
            add_target(target.value)

    def add_args(args: ast.arguments) -> None:
        for arg in list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs):
            shadowed.add(arg.arg)
        if args.vararg:
            shadowed.add(args.vararg.arg)
        if args.kwarg:
            shadowed.add(args.kwarg.arg)

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            add_args(node.args)
            body = node.body if isinstance(node.body, list) else [node.body]
            for stmt in body:
                for sub in ast.walk(stmt):
                    if isinstance(sub, ast.Assign):
                        for t in sub.targets:
                            add_target(t)
                    elif isinstance(sub, (ast.AugAssign, ast.AnnAssign)):
                        add_target(sub.target)
                    elif isinstance(sub, (ast.For, ast.AsyncFor)):
                        add_target(sub.target)
                    elif isinstance(sub, (ast.With, ast.AsyncWith)):
                        for item in sub.items:
                            if item.optional_vars is not None:
                                add_target(item.optional_vars)
                    elif isinstance(sub, ast.comprehension):
                        add_target(sub.target)
                    elif isinstance(sub, ast.ExceptHandler) and sub.name:
                        shadowed.add(sub.name)
    return shadowed


# ---------------------------------------------------------------------------
# Cross-module attribute resolution (Unit 2) — `module.CONSTANT` reads
# (`config.<RECORD>.read_text()`, read from a target's own harness). Chosen as
# LAZY-FOLD-ON-DEMAND, not two-pass: `_classify_import()` (already reused
# unchanged) resolves a dotted module name to a file purely from the
# filesystem, independent of anything the walk's own queue has visited —
# there is no notion of "not visited yet" to be order-dependent about. This
# is what makes lazy resolution correct regardless of whether the reading
# file or the defining file is scanned first by `resolve_clone_paths()`'s
# queue (Phase 7's named risk, test `test_cross_module_read_resolves_
# regardless_of_visit_order`). `cache`, keyed by resolved file, memoizes
# each sibling file's constant table so a repeatedly-read constant is
# folded once per `resolve_clone_paths()` call, not once per reference.
# ---------------------------------------------------------------------------


def _import_alias_map(tree: ast.Module) -> dict[str, str]:
    """Local name -> dotted module name, for every `ast.Import`/
    `ast.ImportFrom` reachable anywhere in `tree` (scope is irrelevant here,
    same as the read call sites this feeds — Task 8.1: only rebinding of
    the name itself in a non-module scope disqualifies folding, and that is
    `_shadowed_names()`'s job, not this map's).

    `import pkg.sub as alias` -> `{"alias": "pkg.sub"}`; bare `import pkg`
    -> `{"pkg": "pkg"}` (the bound name is always the first dotted
    segment when no `asname` is given). `from pkg import name` -> `{"name":
    "pkg.name"}`, mirroring a real cited target's own `from <package>
    import bags, config, report_digest, wiring` shape (a sibling-module
    import, not a package attribute) — `name` here is a SUBMODULE, exactly
    what this resolution needs; `from pkg import *` is skipped, same
    posture as the import-classification walk gives a star import (never
    enqueued).
    """
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                local = alias.asname or alias.name.split(".", 1)[0]
                aliases[local] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                if alias.name == "*":
                    continue
                local = alias.asname or alias.name
                aliases[local] = f"{node.module}.{alias.name}"
    return aliases


def _resolve_module_constant(
    dotted_module: str,
    attr: str,
    source: Path,
    cache: dict[Path, dict[str, Path] | None],
) -> Path | None:
    """Resolve `dotted_module.attr` by classifying `dotted_module` through
    `_classify_import()` (the SAME function import classification already
    uses, unchanged) and, only when it names this repository's own code
    (`kind == "internal"`), folding that sibling file's own module-level
    constants and looking up `attr` in the result.

    A module that does not resolve (`"unresolved"`, e.g. it looks like this
    repository's own package but the specific submodule file does not
    exist) or is not this repository's own code (`"external"`) returns
    `None` — never a guess, and never silence: the caller (`_fold_path_expr`,
    then `_scan_read_call_sites`) treats a `None` receiver as unfoldable,
    which becomes an `unresolvedReads` entry for a read-shaped call, same as
    any other unfoldable receiver.

    `cache` memoizes by resolved file, and doubles as a cycle guard: a file
    is marked `None` (in progress) the instant its own fold begins, so a
    constant chain that circularly cross-references back to a file already
    being folded resolves that one hop to `None` instead of recursing
    forever — an edge case no cited target exhibits, guarded defensively.
    """
    kind, _clone_path, file = _classify_import(dotted_module, source, is_entry=False)
    if kind != "internal" or file is None:
        return None
    if file in cache:
        table = cache[file]
        return None if table is None else table.get(attr)
    cache[file] = None  # in progress: guards against a circular reference
    try:
        text = file.read_text(encoding="utf-8")
        sibling_tree = ast.parse(text)
    except (OSError, UnicodeDecodeError, SyntaxError):
        cache[file] = {}
        return None
    table = _fold_module_constants(sibling_tree, file, source=source, cache=cache)
    cache[file] = table
    return table.get(attr)


def _fold_module_constants(
    tree: ast.Module,
    file: Path,
    *,
    source: Path | None = None,
    cache: dict[Path, dict[str, Path] | None] | None = None,
) -> dict[str, Path]:
    """Scan module-level assignments only (`tree.body`, never a nested
    function or class body) and fold each single-name target's right-hand
    side through `_fold_path_expr()`, building each constant on top of the
    ones already folded above it in the same file — exactly the real shape
    this exists to catch (`REPOSITORY` -> `PRODUCT` -> `RESULTS` ->
    `RECORD`, each one a `Name` lookup into the constants already folded).

    Both `ast.Assign` (`NAME = value`) and `ast.AnnAssign` (`NAME: type =
    value`) count. An annotation changes nothing about what a constant is
    worth, and reading only the first form silently dropped an annotated
    link out of the middle of a chain: every constant built on top of it
    then failed to fold too, and the reads through them left the path table
    entirely — reported as unresolved, or not reported at all. A bare
    `NAME: type` with no value (`node.value is None`) binds nothing and is
    skipped; it is not a name assigned twice either, since it was never
    assigned once.

    A name assigned twice at module level is dropped from the table
    entirely, never last-wins: a second assignment means the first fold
    cannot be trusted as the name's one true value. A name bound anywhere
    in a non-module scope (`_shadowed_names()`) is never added at all, for
    the same reason — see that function's docstring.

    `source`/`cache`, when given (Unit 2), enable a right-hand side that is
    itself a cross-module attribute (`module.CONSTANT`) to resolve via
    `_resolve_module_constant()` — `imports` (`_import_alias_map()`) is
    always computed fresh from THIS `tree`, never passed in, since it is
    intrinsic to the file being folded, not to the caller.
    """
    shadowed = _shadowed_names(tree)
    imports = _import_alias_map(tree)
    table: dict[str, Path] = {}
    assigned_twice: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
                continue
            name = node.targets[0].id
            value = node.value
        elif isinstance(node, ast.AnnAssign):
            # An `ast.AnnAssign` has exactly one target by construction, so
            # the single-`Name` discipline above reduces to the `isinstance`
            # half of it -- no count to check, nothing relaxed.
            if node.value is None or not isinstance(node.target, ast.Name):
                continue
            name = node.target.id
            value = node.value
        else:
            continue
        if name in assigned_twice:
            continue
        if name in table:
            del table[name]
            assigned_twice.add(name)
            continue
        if name in shadowed:
            continue
        folded = _fold_path_expr(
            value, table, file, imports=imports, source=source, cache=cache
        )
        if folded is not None:
            table[name] = folded
    return table


def _fold_path_expr(
    node: ast.AST,
    table: dict[str, Path],
    file: Path,
    *,
    imports: dict[str, str] | None = None,
    source: Path | None = None,
    cache: dict[Path, dict[str, Path] | None] | None = None,
) -> Path | None:
    """Fold one AST expression into a concrete `Path`, admitting only a
    closed grammar (design decision 3):

    - `Path(__file__)`, and `.resolve()` / `.parent` chains off it
    - `Path(__file__).resolve().parents[N]`, `N` a non-negative int literal
    - `Path("<string literal>")`
    - a bare `Name` already present in `table`
    - `BinOp(Div)` with a string-literal right operand, chained
      (`X / "a" / "b"`)
    - `.joinpath("a", "b", ...)` with every argument a string literal
    - (Unit 2) `module.CONSTANT`, an `ast.Attribute` whose receiver is a
      bare `Name` bound by an import (`imports`) to another module in this
      repository — resolved via `_resolve_module_constant()`, ONLY when
      `imports`/`source`/`cache` are all supplied by the caller

    Everything else returns `None`, never a guess — this is the CLOSED,
    documented grammar (see `SKILL.md`'s undeclared-read-detection
    doctrine for the same list, kept in sync by hand): f-strings,
    `%`/`+`/`str.format` string building, `os.path.join(...)`,
    `os.environ[...]`, `sys.argv[...]`, `.with_name(...)`/
    `.with_suffix(...)`/`.stem`/`.glob(...)`, `Path(x)` for any `x` other
    than `__file__` or a string literal, a ternary (`ast.IfExp`),
    `AugAssign`, a tuple-unpack assignment target, `.parents[N]` with a
    non-literal index, and an attribute access whose receiver is not a
    known imported module. An evaluator whose limits are undocumented is a
    detector that implies completeness — everything outside this roster
    becomes an `unresolvedReads` entry instead, carrying the file, line,
    and `ast.unparse()` of the expression.
    """
    if isinstance(node, ast.Name):
        return table.get(node.id)

    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "Path":
        if len(node.args) == 1 and not node.keywords:
            arg = node.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                return Path(arg.value)
            if isinstance(arg, ast.Name) and arg.id == "__file__":
                return file
        return None

    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        if node.func.attr == "resolve" and not node.args and not node.keywords:
            base = _fold_path_expr(
                node.func.value, table, file, imports=imports, source=source, cache=cache
            )
            return base.resolve() if base is not None else None
        if (
            node.func.attr == "joinpath"
            and node.args
            and not node.keywords
            and all(isinstance(a, ast.Constant) and isinstance(a.value, str) for a in node.args)
        ):
            base = _fold_path_expr(
                node.func.value, table, file, imports=imports, source=source, cache=cache
            )
            if base is None:
                return None
            for arg in node.args:
                base = base / arg.value
            return base
        return None

    if isinstance(node, ast.Attribute) and node.attr == "parent":
        base = _fold_path_expr(
            node.value, table, file, imports=imports, source=source, cache=cache
        )
        return base.parent if base is not None else None

    if (
        isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "parents"
    ):
        index = node.slice
        if not (isinstance(index, ast.Constant) and isinstance(index.value, int)
                and not isinstance(index.value, bool) and index.value >= 0):
            return None
        base = _fold_path_expr(
            node.value.value, table, file, imports=imports, source=source, cache=cache
        )
        if base is None:
            return None
        parents = list(base.parents)
        if index.value >= len(parents):
            return None
        return parents[index.value]

    if (
        isinstance(node, ast.BinOp)
        and isinstance(node.op, ast.Div)
        and isinstance(node.right, ast.Constant)
        and isinstance(node.right.value, str)
    ):
        base = _fold_path_expr(
            node.left, table, file, imports=imports, source=source, cache=cache
        )
        return (base / node.right.value) if base is not None else None

    if (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and imports is not None
        and source is not None
        and cache is not None
        and node.value.id in imports
    ):
        return _resolve_module_constant(imports[node.value.id], node.attr, source, cache)

    return None


def _read_candidate(folded: Path, resolved_target: Path) -> Path | None:
    """Containment FILTERS, it never accuses (design decision 4): `folded`
    is resolved and tested against `resolved_target`. Outside the target,
    it is dropped entirely — not a candidate and not an uncertainty, the
    same posture `_classify_import()`'s `external` branch gives an import
    that names nothing under `<target>/src`, and the same absolute-path
    refusal `validate_clone_paths()` already applies to a declared clone
    path. A battery probe like `/sys/class/power_supply/AC/online` is
    exactly this case: real, resolvable, and none of this repository's
    business.
    """
    resolved = folded.resolve()
    try:
        resolved.relative_to(resolved_target)
    except ValueError:
        return None
    return resolved


# The read/write/neutral call-site roster (design decision 6). `open`
# (both the builtin and the `Path.open()` method) is handled separately
# below since its read/write verdict depends on its own `mode` argument,
# not on its method name alone.
_READ_METHODS = frozenset({"read_text", "read_bytes"})
_WRITE_METHODS = frozenset({
    "write_text", "write_bytes", "mkdir", "touch", "unlink", "rename",
})
_NEUTRAL_METHODS = frozenset({
    "exists", "is_file", "is_dir", "parent", "parents", "name", "stem",
    "suffix", "resolve", "as_posix", "with_name", "with_suffix",
})
_WRITE_MODE_CHARS = frozenset({"w", "a", "x", "+"})


def _mode_is_write(mode_node: ast.AST | None) -> bool:
    """`None` (mode omitted) and any non-literal mode are both treated as
    NOT a write — never guessed towards silence. A literal mode is a
    write only when it contains one of `w`/`a`/`x`/`+`.
    """
    if isinstance(mode_node, ast.Constant) and isinstance(mode_node.value, str):
        return any(ch in mode_node.value for ch in _WRITE_MODE_CHARS)
    return False


def _keyword_value(keywords: list, name: str) -> ast.AST | None:
    for kw in keywords:
        if kw.arg == name:
            return kw.value
    return None


def _unresolved_entry(file: Path, node: ast.AST, why: str) -> str:
    try:
        expr = ast.unparse(node)
    except Exception:
        expr = "<unparsable expression>"
    line = getattr(node, "lineno", "?")
    return f"{file}:{line}: {expr} — {why}"


def _scan_read_call_sites(
    tree: ast.Module,
    table: dict[str, Path],
    file: Path,
    resolved_target: Path,
    *,
    source: Path | None = None,
    cache: dict[Path, dict[str, Path] | None] | None = None,
) -> tuple[set[Path], list[str], set[Path]]:
    """Walk every `ast.Call` in `tree` once, classifying each one against
    the read/write/neutral roster (design decision 6). `source`/`cache`
    (Unit 2), when given, let a receiver such as `config.<RECORD>`
    fold through `_fold_path_expr()`'s cross-module branch — `imports`
    (`_import_alias_map()`) is computed fresh from THIS `tree`, same
    reasoning as `_fold_module_constants()`.

    - the call is itself part of `_fold_path_expr()`'s own grammar
      (`Path(...)`, `.resolve()`, `.joinpath(...)`) -> pure path
      construction, never an I/O action, skipped;
    - an `Attribute` call whose receiver folds to a contained path:
      `.read_text`/`.read_bytes`/a non-write `.open(...)` -> a read
      candidate; a WRITE method (`.write_text`/`.write_bytes`/a
      write-mode `.open(...)`/`.mkdir`/`.touch`/`.unlink`/`.rename`) ->
      also a WRITE candidate (corrective batch addition — see below); a
      neutral method -> silent; anything else -> `unresolvedReads`
      ("anything else on a folded, contained path" is never silence);
    - an `Attribute` call whose receiver does NOT fold, but whose method
      name is unmistakably read-shaped (`.read_text`/`.read_bytes`/a
      non-write `.open(...)`) -> `unresolvedReads` (the f-string case);
    - the builtin `open(path, mode=...)` -> the same read/write verdict,
      by its first positional argument instead of a receiver (a write
      mode is a WRITE candidate the same way);
    - the builtin `str(path)` -> silent (the one bare-call NEUTRAL roster
      member; every other bare call is scanned below instead);
    - any other call (a folded, contained path passed as a bare argument
      into a call this walk cannot otherwise classify, e.g.
      `some_loader(RECORD)`, `pd.read_csv(DATA)`) -> `unresolvedReads`.

    Returns `(read_candidates, unresolved, write_candidates)`:
    `read_candidates`/`write_candidates` are resolved, target-relative
    `Path`s; `unresolved` is a list of `"<file>:<line>: <expr> — <why>"`
    strings.

    `write_candidates` (corrective batch, closing the generation-deadlock
    CRITICAL): collected for exactly one reason — `resolve_clone_paths()`
    uses it to tell "a read of a file nothing in this walk ever produces"
    (a genuinely missing declared input, still refused unconditionally
    via `computedReadsNotDeclared`) apart from "a read of a file THIS SAME
    walked file set also writes" (a produced-file candidate — see
    `producedReadsNotDeclared` on `resolve_clone_paths()`). This is
    RECLASSIFICATION using the write signal, never silent exclusion: a
    write call site was already never a read candidate (Decision 5,
    unchanged); collecting it here additionally does not remove or
    silence anything on its own — `resolve_clone_paths()` still surfaces
    every produced-file candidate, and `generate_job()` still refuses it
    by default, only through a different, hatch-bearing bucket.
    """
    imports = _import_alias_map(tree)
    read_candidates: set[Path] = set()
    unresolved: list[str] = []
    write_candidates: set[Path] = set()

    def fold(expr: ast.AST) -> Path | None:
        return _fold_path_expr(
            expr, table, file, imports=imports, source=source, cache=cache
        )

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if fold(node) is not None:
            continue  # pure path construction, not an I/O action

        if isinstance(node.func, ast.Attribute):
            method = node.func.attr
            receiver = fold(node.func.value)
            if receiver is not None:
                contained = _read_candidate(receiver, resolved_target)
                if contained is None:
                    continue  # outside target: dropped, never flagged
                if method == "open":
                    mode_node = _keyword_value(node.keywords, "mode")
                    if mode_node is None and node.args:
                        mode_node = node.args[0]
                    if _mode_is_write(mode_node):
                        write_candidates.add(contained)
                    else:
                        read_candidates.add(contained)
                elif method in _READ_METHODS:
                    read_candidates.add(contained)
                elif method in _WRITE_METHODS:
                    write_candidates.add(contained)
                elif method in _NEUTRAL_METHODS:
                    pass
                else:
                    unresolved.append(_unresolved_entry(
                        file, node,
                        "unclassified call on a folded, target-contained path",
                    ))
                continue
            # Receiver did not fold. Still flag an unmistakably
            # read-shaped call by its own method name — the path could
            # not be resolved, but the call site's own shape says "read".
            is_read_shaped = method in _READ_METHODS
            if method == "open":
                mode_node = _keyword_value(node.keywords, "mode")
                if mode_node is None and node.args:
                    mode_node = node.args[0]
                is_read_shaped = not _mode_is_write(mode_node)
            if is_read_shaped:
                unresolved.append(_unresolved_entry(
                    file, node, "read call on a path that could not be resolved",
                ))
                continue
            # Not a recognized read shape either — fall through to the
            # generic bare-argument scan below, in case a folded,
            # contained path was passed as an argument instead.

        elif isinstance(node.func, ast.Name) and node.func.id == "open" and node.args:
            path_arg = node.args[0]
            mode_node = _keyword_value(node.keywords, "mode")
            if mode_node is None and len(node.args) >= 2:
                mode_node = node.args[1]
            folded = fold(path_arg)
            if folded is not None:
                contained = _read_candidate(folded, resolved_target)
                if contained is None:
                    continue  # outside target: dropped, never flagged
                if _mode_is_write(mode_node):
                    write_candidates.add(contained)
                else:
                    read_candidates.add(contained)
                continue
            if not _mode_is_write(mode_node):
                unresolved.append(_unresolved_entry(
                    file, node, "open() call on a path that could not be resolved",
                ))
            continue

        elif (
            isinstance(node.func, ast.Name)
            and node.func.id == "str"
            and len(node.args) == 1
            and not node.keywords
        ):
            # `str()` is the one bare-call NEUTRAL roster member (design
            # decision 6) — a folded path passed to it is never a read,
            # never an uncertainty, unlike every other bare call.
            continue

        # Generic fallback: any folded, target-contained path passed as a
        # bare argument into a call this walk cannot otherwise classify —
        # the library-loader shape (`some_loader(RECORD)`,
        # `pd.read_csv(DATA)`). Never silence.
        for arg in node.args:
            folded = fold(arg)
            if folded is None:
                continue
            contained = _read_candidate(folded, resolved_target)
            if contained is None:
                continue
            unresolved.append(_unresolved_entry(
                file, node,
                "a folded, target-contained path passed as a bare argument "
                "into an unclassified call",
            ))
            break

    return read_candidates, unresolved, write_candidates


def _covered_by_declared(candidate: str, declared: Sequence[str]) -> bool:
    """A computed read path is covered when it EQUALS or is nested under a
    declared clone path — never exact-match-only, since a resolved data
    file (`src/A/data.json`) legitimately sits under a declared directory
    (`src/A`) rather than naming it exactly, unlike the import check's
    granularity-rule clone paths.
    """
    cand_path = Path(candidate)
    for decl in declared:
        decl_path = Path(decl)
        if cand_path == decl_path or decl_path in cand_path.parents:
            return True
    return False


def resolve_clone_paths(
    target: Path,
    entry_modules: Sequence[str],
    declared_clone_paths: Sequence[str],
    entry_notebooks: Sequence[str] = (),
) -> dict:
    """Cross-check declared `clonePaths` against what the declared entries
    actually import, transitively, before generation ever writes a job
    folder.

    An entry is a declared module (`run.module`, `run.smoke.module`) or a
    declared NOTEBOOK (`run.notebook`, `run.smoke.notebook`) — `entry_
    notebooks`, added when a job became able to run the notebook the pilot
    ran. The two are entries in exactly the same sense and are walked by
    exactly the same machinery (`absorb()` below), for a reason worth
    stating: nothing IMPORTS a notebook, so the module queue can never
    reach one, and a notebook whose own imports went unwalked would carry
    the undeclared-import failure this whole cross-check exists to close
    straight back into the kernel. What a notebook does NOT get is a
    `computed` clone path of its own — it is not a module and maps to no
    package directory; that it is delivered at all is the
    `declared-notebook-reachable` pin condition's question, asked of the
    pin.

    Reuses `implementation_cli.py`'s `prior_work_state()` idiom exactly for
    the walk itself (`ast.parse` + `ast.walk` over `ast.Import`/
    `ast.ImportFrom`, inspecting only `node.module` for `ImportFrom` and
    `alias.name` for `Import`, with no relative-import resolution) — just
    walked transitively, over every module an entry module reaches,
    instead of over one fixed file set.

    One conservative widening on top of that reused idiom, confirmed
    necessary by a real production gap: for `from A import name`, `name`
    is also tried as a candidate submodule `A.name`, and enqueued ONLY
    when that candidate resolves to an actual file on disk. Without this,
    `from A import sub` enqueues `A` alone, which resolves to
    `A/__init__.py` — never to `A/sub.py` when `sub` is a submodule FILE
    rather than an attribute `__init__.py` itself defines, so `sub.py`'s
    own imports were never walked at all. A generated job's `from
    PackageName import alpha, beta, gamma, delta` (an empty `__init__.py`)
    let `delta.py`'s own further import slip past this check undeclared,
    and a real clone failed at runtime with `ModuleNotFoundError` for
    exactly that reason. Resolving the
    candidate first, rather than enqueuing every imported name
    unconditionally, is what keeps an ordinary `from A import
    some_attribute` from becoming a spurious `unresolved` entry.

    The granularity rule (design #744 section 3): a resolved import maps
    to its top-level package directory under `src/`, never to a single
    file — `src/A/B/C.py` => clone path `src/A`; a true top-level module
    `src/A.py` => clone path `src/A.py`. An import that is not this
    repository's own code (its top-level segment names nothing under
    `<target>/src` at all) is filtered and never becomes a clone path.

    Returns `{"declared", "computed", "computedNotDeclared", "unresolved",
    "computedReadsNotDeclared", "producedReadsNotDeclared",
    "unresolvedReads"}`:
    `declared` is `declared_clone_paths` re-validated through the SAME
    `validate_clone_paths()` `generate_job()` already uses (structural,
    plus the symlink-escape check now that `target` is known) — never a
    second validator. `computedNotDeclared` names every real import missing
    from `clonePaths`; a non-empty result is always a refusal, never a
    warning. `unresolved` names every uncertain case this walk hit: a
    non-literal `importlib.import_module(...)` call, any `__import__(...)`
    call, a `sys.path` mutation, an unparsable file, or an import that
    looks like this repository's own code but does not resolve to a file
    on disk. A non-empty `unresolved` refuses generation unless the caller
    passes `--accept-unresolved`, which records it in `run-config.json`'s
    `unresolvedImports` instead of guessing.

    `computedReadsNotDeclared`, `producedReadsNotDeclared`, and
    `unresolvedReads` (Unit 1, undeclared-read detection; the corrective
    batch adds `producedReadsNotDeclared`) are built from the SAME parsed
    `tree` this walk already holds for every transitively-reached file —
    no new file traversal. `_fold_module_constants()` builds each file's
    own constant->`Path` table; `_scan_read_call_sites()` classifies every
    call site against the read/write/neutral roster, now ALSO returning
    every folded, target-contained path targeted by a WRITE call site
    anywhere in the walked file set (`write_candidates`).

    A folded, target-contained read whose resolved path is not covered by
    a declared clone path (`Path.is_relative_to`, never exact-match-only)
    is always a refusal, never a warning — but WHICH of two buckets it
    refuses through now depends on the write signal (corrective batch,
    reclassification, not suppression — see `SKILL.md`'s
    "generation-deadlock" doctrine for the full account):

    - not written anywhere in the same walked file set ->
      `computedReadsNotDeclared`: a genuinely missing declared input,
      refused UNCONDITIONALLY, no hatch, unchanged from before this
      corrective batch;
    - ALSO written somewhere in the same walked file set (the same
      resolved path appears as a WRITE call-site target, e.g.
      `RECORD.write_text(...)` beside `RECORD.read_text()`) ->
      `producedReadsNotDeclared`: a produced-file candidate — the job may
      exist to CREATE this file on its first run, so declaring it (as
      `_refuse_absent_clone_paths` would then require existing at the
      pin) is not always possible. Refused unless the caller passes
      `--accept-produced-reads`, which records the finding VERBATIM in
      `run-config.json`'s `acceptedProducedReads` — the operator is still
      told and still decides; nothing disappears silently.

    A read call site whose path could not be folded, or a folded,
    target-contained path used in a call this walk cannot classify,
    becomes an `unresolvedReads` entry instead — refused unless the
    caller passes `--accept-unresolved-reads`, a SEPARATE flag from
    `--accept-unresolved` (imports) and from `--accept-produced-reads`
    that never waives either other refusal (severity asymmetry: an
    accepted uncertain import dies loudly in the kernel minutes later; an
    accepted uncertain read is reported by nobody). A path outside
    `target` is dropped from candidacy entirely, never flagged — the same
    `external` posture `_classify_import()` gives a non-local import.
    All three new keys are always present, even when empty (never
    absent).
    """
    resolved_target = target.resolve()
    source = resolved_target / "src"
    declared = validate_clone_paths(declared_clone_paths, resolved_target)

    computed: set[str] = set()
    unresolved: list[str] = []
    computed_reads: set[str] = set()
    unresolved_reads: list[str] = []
    # Corrective batch: every folded, target-contained path targeted by a
    # WRITE call site anywhere in the walked file set — used ONLY to
    # reclassify (never to suppress) an undeclared read of the same
    # resolved path. See the docstring above and `producedReadsNotDeclared`
    # below.
    produced_paths: set[str] = set()
    # Unit 2 (cross-module resolution): memoizes each sibling file's own
    # constant table, keyed by resolved file, shared across the whole walk.
    # Populated LAZILY (on first cross-module reference, via
    # `_resolve_module_constant()`) and/or directly below as each file is
    # visited in the main walk — whichever happens first for a given file;
    # both paths compute the identical, deterministic table, so visit
    # order never changes the result (Phase 7).
    constant_cache: dict[Path, dict[str, Path] | None] = {}
    visited: set[Path] = set()
    queued: set[str] = set(entry_modules)
    queue: list[tuple[str, bool]] = [(name, True) for name in entry_modules]

    def enqueue(name: str) -> None:
        if name not in queued:
            queued.add(name)
            queue.append((name, False))

    def absorb(file: Path, tree: ast.Module, exempt=None) -> None:
        """Everything this walk learns from ONE already-parsed file:
        its own constant table, its read/write call sites, and every
        import it makes enqueued for the walk to follow.

        Extracted from the module loop below so a NOTEBOOK entry goes
        through the identical machinery rather than a second,
        notebook-shaped copy of it. A notebook reaches this function
        with a tree parsed from its own code cells
        (`notebook_code_source()`); a module reaches it with a tree
        parsed from its file. Nothing below this line can tell them
        apart, which is exactly the property that keeps a notebook's
        undeclared import from being a weaker refusal than a module's.
        """
        # Undeclared-read detection (Unit 1 same-file, Unit 2 cross-module):
        # the SAME parsed `tree`, no new file traversal. `file` is already
        # resolved (derived from `source = resolved_target / "src"`).
        # `constant_cache` overwrites any lazily-computed placeholder for
        # this file with the authoritative table — deterministic, so this
        # is idempotent regardless of which path reached `file` first.
        read_table = _fold_module_constants(tree, file, source=source, cache=constant_cache)
        constant_cache[file] = read_table
        read_candidates, read_unresolved, write_candidates = _scan_read_call_sites(
            tree, read_table, file, resolved_target, source=source, cache=constant_cache
        )
        for candidate in read_candidates:
            computed_reads.add(candidate.relative_to(resolved_target).as_posix())
        unresolved_reads.extend(read_unresolved)
        for candidate in write_candidates:
            produced_paths.add(candidate.relative_to(resolved_target).as_posix())

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                enqueue(node.module)
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    candidate = f"{node.module}.{alias.name}"
                    # `from A import sub` names `sub` only as an imported
                    # NAME on `node.module = "A"` — `enqueue("A")` alone
                    # resolves to `A/__init__.py`, never to `A/sub.py`,
                    # when `sub` is actually a submodule FILE rather than
                    # an attribute `__init__.py` itself defines. A real
                    # production gap this conservative widening closes: a
                    # generated job's `from PackageName import alpha, beta,
                    # gamma, delta` (an empty `__init__.py`) let `delta.py`'s
                    # own further imports slip past this walk entirely,
                    # undeclared, and the clone failed at runtime with
                    # `ModuleNotFoundError`.
                    # Enqueued ONLY when `candidate` resolves to an actual
                    # file on disk — an ordinary `from A import
                    # some_attribute`, where `some_attribute` is merely a
                    # name `__init__.py` defines rather than a submodule
                    # file, must never become a spurious `unresolved`
                    # entry, so this never enqueues a name that cannot be
                    # positively confirmed as a real submodule first.
                    if _module_to_relpath(candidate, source) is not None:
                        enqueue(candidate)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    enqueue(alias.name)
            elif _is_dunder_import_call(node):
                unresolved.append(f"{file}: __import__(...) call is uncertain")
            elif _is_import_module_call(node):
                literal = _literal_import_module_argument(node)
                if literal is not None:
                    enqueue(literal)
                else:
                    unresolved.append(
                        f"{file}: non-literal importlib.import_module(...) call is uncertain"
                    )
            elif _is_sys_path_mutation(node):
                if exempt is None or not exempt(node):
                    unresolved.append(f"{file}: sys.path mutation is uncertain")

    # A declared NOTEBOOK is an entry too, and the only one this walk can
    # reach by path rather than by dotted name: nothing imports a notebook,
    # so `_classify_import()` has no way to find it and the module queue
    # never would. Seeded here, before the queue runs, so every import its
    # code cells make is enqueued exactly as an entry module's are and
    # lands in `computed` — which is what makes an undeclared import inside
    # the pilot's own notebook a refusal at generation instead of a
    # `ModuleNotFoundError` inside the kernel with the quota already spent.
    #
    # Every failure here becomes an `unresolved` entry rather than an
    # exception: a notebook that is missing, unreadable, not JSON, or whose
    # code cells will not parse is an UNCERTAIN walk, and this module
    # already has one vocabulary for that. Its own existence at the pin is
    # a different question, asked by the `declared-notebook-reachable` pin
    # condition against the commit rather than against the working tree.
    for raw_notebook in entry_notebooks:
        try:
            relative = validate_notebook_path(
                raw_notebook, where="clone-path resolution"
            )
        except JobFolderError as exc:
            unresolved.append(str(exc))
            continue
        notebook_file = (resolved_target / relative).resolve()
        try:
            notebook_file.relative_to(resolved_target)
        except ValueError:
            unresolved.append(
                f"notebook {relative!r} resolves to {notebook_file}, outside "
                f"target {resolved_target} (symlink escape)"
            )
            continue
        if not notebook_file.is_file():
            unresolved.append(
                f"notebook {relative!r} does not exist under {resolved_target}"
            )
            continue
        try:
            notebook_text, bootstrap_end = _notebook_scan_source(notebook_file)
        except JobFolderError as exc:
            unresolved.append(str(exc))
            continue
        try:
            notebook_tree = ast.parse(notebook_text)
        except SyntaxError as exc:
            unresolved.append(
                f"{notebook_file}: code cells are unparsable as Python ({exc})"
            )
            continue
        if notebook_file in visited:
            continue
        visited.add(notebook_file)
        # S5: the kit bootstrap cell binds `ROOT` to the clone, so the one
        # insert of exactly `ROOT / "src"` after it is the clone's own
        # source root. Any other mutation, an insert before the cell, or a
        # notebook that rebinds `ROOT` anywhere stays uncertain.
        exempt = None
        if bootstrap_end is not None and not _binds_root(notebook_tree):
            def exempt(node: ast.AST, _after: int = bootstrap_end) -> bool:
                return (
                    getattr(node, "lineno", 0) > _after
                    and ast.dump(node) == _KIT_SRC_INSERT_DUMP
                )
        absorb(notebook_file, notebook_tree, exempt)

    while queue:
        dotted, is_entry = queue.pop(0)
        kind, clone_path, file = _classify_import(dotted, source, is_entry=is_entry)
        if kind == "external":
            continue
        if kind == "unresolved":
            unresolved.append(
                f"import {dotted!r} resolves to nothing on disk under {source}"
            )
            continue
        computed.add(clone_path)
        if file in visited:
            continue
        visited.add(file)

        try:
            text = file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            unresolved.append(f"{file}: unreadable ({exc})")
            continue
        try:
            tree = ast.parse(text)
        except SyntaxError as exc:
            unresolved.append(f"{file}: unparsable ({exc})")
            continue

        absorb(file, tree)

    uncovered_reads = [
        r for r in computed_reads if not _covered_by_declared(r, declared)
    ]
    return {
        "declared": list(declared),
        "computed": sorted(computed),
        "computedNotDeclared": sorted(computed - set(declared)),
        "unresolved": unresolved,
        "computedReadsNotDeclared": sorted(
            r for r in uncovered_reads if r not in produced_paths
        ),
        "producedReadsNotDeclared": sorted(
            r for r in uncovered_reads if r in produced_paths
        ),
        "unresolvedReads": unresolved_reads,
    }


def validate_commit_shape(commit: object, *, source: str = "the pinned commit") -> str:
    """A pin is an object name, never a name that resolves to one.

    The SAME validator both callers use — `validate_run_config()` on every
    read and every generation, and `verify_pin_preconditions()` before it
    asks any of the pin conditions — never a second, parallel copy. The
    precondition function checks it FIRST, ahead of every condition,
    because a name-shaped pin makes each of them compare a value to
    itself and answer yes: `main` really is a ref the remote can serve,
    `main^{commit}` really does resolve locally, and the staleness diff
    between `main` and `HEAD` really is empty. Every pin condition
    passing for a pin that means something different tomorrow.
    """
    if not isinstance(commit, str) or not COMMIT_PATTERN.match(commit):
        raise JobFolderError(
            f"{source} declares commit {commit!r}, which is not a "
            "commit object name: a pin must be lowercase hex, 40 or 64 "
            "characters. A branch or tag name is not a pin — it resolves to "
            "a different commit tomorrow, and the runner would check out "
            "whatever it points at then, not the code this job was "
            "validated against. Pass the output of `git rev-parse HEAD`."
        )
    return commit


NOTEBOOK_SUFFIX = ".ipynb"

# The two shapes a `run` (or `run.smoke`) block may take, and the only
# two. Named here rather than respelled at each of the four places that
# branch on them (`validate_run_config()`, `build_run_config()`,
# `generate_job()`, and `assets/runner_invoke.py`'s own mirror).
RUN_BLOCK_KINDS = ("callable", "notebook")


def validate_notebook_path(raw: object, *, where: str) -> str:
    """Structural validation for a declared notebook path — the same
    posture `validate_clone_paths()` holds for a clone path, and for the
    same reasons: the value reaches `git cat-file`, a `sparse-checkout`
    pathspec and a filesystem join, so an absolute or `..`-bearing path is
    refused before any of them sees it.

    The `.ipynb` suffix is checked here and nowhere else. It is not
    decoration: `runner_invoke.py` hands this path to a notebook reader,
    and anything else reaching that reader dies inside the kernel with a
    decode error after the quota is already spent — the exact class of
    failure every other guard in this module exists to move earlier.
    """
    if not isinstance(raw, str) or not raw.strip():
        raise JobFolderError(
            f"{where} declares notebook {raw!r}: a notebook path must be a "
            "non-empty string"
        )
    candidate = Path(raw)
    if candidate.is_absolute():
        raise JobFolderError(f"{where} refuses absolute notebook path {raw!r}")
    if ".." in candidate.parts:
        raise JobFolderError(f"{where} refuses notebook path {raw!r}: contains '..'")
    if candidate.suffix != NOTEBOOK_SUFFIX:
        raise JobFolderError(
            f"{where} refuses notebook path {raw!r}: a notebook run must name "
            f"a {NOTEBOOK_SUFFIX} file"
        )
    return candidate.as_posix()


def run_block_kind(block: object, *, where: str) -> str:
    """Which of the two shapes a `run`/`run.smoke` block declares —
    `"callable"` (a `module`/`function` pair) or `"notebook"` (a
    `notebook` path) — refusing anything that is neither and anything
    that is both.

    **A union, deliberately never a widening.** A block carrying a
    notebook BESIDE a module/function pair would be two declarations of
    the same run with nothing in the code saying which one the worker
    obeys — which is precisely the divergence this whole shape exists to
    close: a callable documenting itself as "exactly what the notebook's
    own cells run" is an assertion no guard can check, and it has already
    drifted once. Exactly one of the two, or a refusal.

    **A refusal, deliberately never a fallback.** Both directions are
    refused HERE rather than resolved by a default, because the caller
    downstream of this function spends metered quota. A block declaring
    neither shape would otherwise have to be guessed at, and every guess
    available costs the same money as the right answer.

    `where` names the block being judged (`"run"`, `"run.smoke"`) so a
    refusal about a smoke block is never read as one about the normal
    run.
    """
    if not isinstance(block, Mapping):
        raise JobFolderError(f"{where} must be a JSON object")
    notebook = block.get("notebook")
    module = block.get("module")
    function = block.get("function")
    if notebook is not None and (module is not None or function is not None):
        raise JobFolderError(
            f"{where} declares BOTH a notebook ({notebook!r}) and a "
            f"module/function pair ({module!r}/{function!r}); a block "
            "declares exactly one of the two, never both — two declarations "
            "of one run is the divergence this shape exists to prevent"
        )
    if notebook is not None:
        validate_notebook_path(notebook, where=where)
        return "notebook"
    if module and function:
        return "callable"
    raise JobFolderError(
        f"{where} declares neither a 'module'/'function' pair nor a "
        f"'notebook'; got {dict(block)!r}. A run with no declared shape is "
        "refused rather than defaulted, because the next step spends quota"
    )


def declared_notebooks(run_config: Mapping[str, object]) -> list[str]:
    """Every notebook path a run configuration declares — the normal `run`
    block's, and `run.smoke`'s when that block declares one — sorted and
    deduplicated.

    One derivation, three readers: `generate_job()` (which cross-checks
    them before writing), `remote_cli.py`'s submit gate (which re-derives
    them from the job folder's OWN config rather than from a caller's
    arguments), and the pin condition both of those reach. A second
    spelling anywhere would let the decision points disagree about which
    notebooks a job promised to run, which is the drift
    `verify_pin_preconditions()` already exists to make impossible for
    every other condition.
    """
    run_block = run_config.get("run")
    if not isinstance(run_block, Mapping):
        return []
    found = []
    notebook = run_block.get("notebook")
    if isinstance(notebook, str) and notebook:
        found.append(notebook)
    smoke = run_block.get("smoke")
    if isinstance(smoke, Mapping):
        smoke_notebook = smoke.get("notebook")
        if isinstance(smoke_notebook, str) and smoke_notebook:
            found.append(smoke_notebook)
    return sorted(set(found))


def notebook_code_source(path: Path) -> str:
    """Every code cell of a notebook, concatenated into one parseable
    Python source text — what lets `resolve_clone_paths()` walk a
    notebook's imports with the SAME `ast` machinery it already walks a
    module's with, rather than a second, notebook-shaped analysis.

    Markdown and raw cells are dropped; they carry no imports. Within a
    code cell, a line whose first non-space character is `%` or `!` is
    dropped too: those are the kernel's own magic and shell escapes, not
    Python, and one of them anywhere in a real pilot notebook would make
    `ast.parse()` raise and turn every such notebook into an `unresolved`
    refusal. Dropping them costs nothing this walk needs — a magic line
    cannot carry an `import` statement — and it is a NAMED transformation
    rather than a silent tolerance: `%run other.ipynb` still reaches
    nobody, and that is stated here rather than discovered later.

    Raises `JobFolderError` when the file is not readable as a notebook;
    the caller turns that into an `unresolved` entry rather than a crash.
    """
    return "\n".join(chunk for _raw, chunk in _notebook_code_cells(path)) + "\n"


def _notebook_code_cells(path: Path) -> list[tuple[str, str]]:
    """Every code cell of a notebook as `(raw, chunk)`: `raw` is the cell's
    source exactly as stored (what `_is_kit_bootstrap_cell()` compares
    byte for byte), `chunk` is that source with `%` magic and `!` shell
    lines dropped — the piece `notebook_code_source()` joins. One reader,
    so the joined text and the per-cell view can never disagree.
    """
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise JobFolderError(f"{path}: not readable as a notebook ({exc})") from exc
    if not isinstance(payload, Mapping):
        raise JobFolderError(f"{path}: notebook does not decode to a JSON object")
    cells: list[tuple[str, str]] = []
    for cell in payload.get("cells") or []:
        if not isinstance(cell, Mapping) or cell.get("cell_type") != "code":
            continue
        source = cell.get("source")
        if isinstance(source, list):
            text = "".join(str(line) for line in source)
        elif isinstance(source, str):
            text = source
        else:
            continue
        kept = [
            line for line in text.splitlines()
            if not line.lstrip().startswith(("%", "!"))
        ]
        cells.append((text, "\n".join(kept)))
    return cells


#: The kit's notebook bootstrap cell, owned by this skill and copied byte for
#: byte as the first code cell of every kit notebook. Recognised by exact
#: text, never by a heuristic: an edited copy is scanned like any other cell.
KIT_BOOTSTRAP_CELL_ASSET = ASSETS_DIR / "notebook_repo_root.py"

#: The one `sys.path` mutation the kit cell's `ROOT` makes safe: `src/` is
#: the clone's own source root, already on the kernel's `PYTHONPATH`.
_KIT_SRC_INSERT_DUMP = ast.dump(
    ast.parse('sys.path.insert(0, str(ROOT / "src"))', mode="eval").body
)

_kit_bootstrap_text_cache: list[str | None] = []


def _kit_bootstrap_text() -> str | None:
    if not _kit_bootstrap_text_cache:
        try:
            text: str | None = KIT_BOOTSTRAP_CELL_ASSET.read_text(encoding="utf-8")
        except OSError:
            text = None
        _kit_bootstrap_text_cache.append(text)
    return _kit_bootstrap_text_cache[0]


def _is_kit_bootstrap_cell(raw: str) -> bool:
    """True only for a cell byte-identical to `assets/notebook_repo_root.py`."""
    owned = _kit_bootstrap_text()
    return owned is not None and raw == owned


def _binds_root(tree: ast.AST) -> bool:
    """Whether anything in `tree` (re)binds the name `ROOT`."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "ROOT" and not isinstance(
            node.ctx, ast.Load
        ):
            return True
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) \
                and node.name == "ROOT":
            return True
        if isinstance(node, (ast.Import, ast.ImportFrom)) and any(
            (alias.asname or alias.name.split(".")[0]) == "ROOT"
            for alias in node.names
        ):
            return True
        if isinstance(node, (ast.Global, ast.Nonlocal)) and "ROOT" in node.names:
            return True
    return False


def _notebook_scan_source(path: Path) -> tuple[str, int | None]:
    """The text `resolve_clone_paths()` parses for a notebook entry, and the
    last line of the first kit bootstrap cell in it (`None` without one).

    A kit bootstrap cell is replaced by as many EMPTY lines as it occupies,
    so every other cell keeps the line numbers `notebook_code_source()`
    gives it and nothing else in the scan changes: the cell's own reads
    (`.git`, `HEAD`, loose and packed refs of the runner's clone) are the
    kit's proof of the pinned commit, not inputs a clone path must carry.
    """
    pieces: list[str] = []
    line = 0
    bootstrap_end: int | None = None
    for raw, chunk in _notebook_code_cells(path):
        span = chunk.count("\n") + 1
        if _is_kit_bootstrap_cell(raw):
            chunk = "\n" * (span - 1)
            if bootstrap_end is None:
                bootstrap_end = line + span
        pieces.append(chunk)
        line += span
    return "\n".join(pieces) + "\n", bootstrap_end


def validate_run_config(run_config: Mapping[str, object]) -> None:
    """The schema check re-run on every read, not only at generation —
    `generate_job()` calls it on the very config it is about to write, so a
    caller a later slice adds to `jobfolder.read()` needs no second copy of
    this logic.

    `commit` is checked for SHAPE here rather than beside the `--commit`
    flag, and the reason is this function's own re-run-on-every-read
    property: a job folder that acquired a name-shaped pin any other way —
    hand-edited, written by an older generator, copied between machines —
    is refused when it is READ, not only when it is written. A guard that
    lived at the CLI flag would let exactly that job folder through, and a
    job folder is read at submit, status, fetch, reconcile and readiness.

    `localBudget`, like `accelerator` and `environment` before it, needs
    no explicit acceptance here: this function checks REQUIRED_RUN_CONFIG_
    FIELDS against a fixed list and never rejects a key outside it, so an
    optional, additive block is already readable the moment
    `build_run_config()` writes it — no allowlist exists to widen.
    """
    if not isinstance(run_config, Mapping):
        raise JobFolderError("run-config.json must decode to a JSON object")
    missing = [field for field in REQUIRED_RUN_CONFIG_FIELDS if field not in run_config]
    if missing:
        raise JobFolderError(f"run-config.json missing required fields: {missing}")
    if run_config.get("schemaVersion") != RUN_CONFIG_SCHEMA_VERSION:
        raise JobFolderError(
            f"run-config.json declares schemaVersion "
            f"{run_config.get('schemaVersion')!r}; this generator writes and "
            f"reads only {RUN_CONFIG_SCHEMA_VERSION}"
        )
    validate_commit_shape(run_config["commit"], source="run-config.json")
    repo = run_config["repo"]
    if isinstance(repo, Mapping):
        refuse_repo_url_credentials(repo.get("url"), where="run-config.json")
    validate_clone_paths(run_config["clonePaths"])
    run_block = run_config["run"]
    # The union check, and the whole of it — see `run_block_kind()`. It is
    # re-run on every READ for the same reason the commit-shape check is: a
    # job folder that acquired a shapeless or double-shaped `run` block any
    # other way (hand-edited, written by an older generator, copied between
    # machines) is refused when it is read, not only when it is written, and
    # a job folder is read at submit — the decision point that spends quota.
    run_block_kind(run_block, where="run-config.json's 'run' block")
    if isinstance(run_block, Mapping) and run_block.get("smoke") is not None:
        run_block_kind(
            run_block["smoke"], where="run-config.json's 'run.smoke' block"
        )
    carry_paths = run_config.get("carryPaths")
    if carry_paths is not None:
        if not isinstance(carry_paths, list):
            raise JobFolderError("run-config.json's carryPaths must be a list of carry paths")
        validate_carry_paths(carry_paths)


def _asset_sha256(path: Path) -> str:
    if not path.is_file():
        raise JobFolderError(
            f"runner asset {path} does not exist; generation refuses to build "
            "a job folder around a missing cell"
        )
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_run_config(
    *,
    product: str,
    service: str,
    job_name: str,
    commit: str,
    repo_url: str,
    repo_ref: str,
    clone_paths: Sequence[str],
    run_module: str | None = None,
    run_function: str | None = None,
    run_kwargs: Mapping[str, object] | None = None,
    run_notebook: str | None = None,
    smoke_module: str | None = None,
    smoke_function: str | None = None,
    smoke_kwargs: Mapping[str, object] | None = None,
    smoke_notebook: str | None = None,
    bootstrap_asset: Path,
    invoke_asset: Path,
    unresolved_imports: Sequence[str] | None = None,
    unresolved_reads: Sequence[str] | None = None,
    accepted_produced_reads: Sequence[str] | None = None,
    smoke_required_evidence: Sequence[str] | None = None,
    accelerator_kind: str | None = None,
    accelerator_architectures: Sequence[str] | None = None,
    environment_requirements: Sequence[str] | None = None,
    environment_index_url: str | None = None,
    local_budget_seconds: int | None = None,
    carry_paths: Sequence[str] | None = None,
) -> dict:
    """Assemble `run-config.json`'s exact shape from target-supplied values.

    `run_notebook`/`smoke_notebook` are the second of the two shapes a run
    block may take (see `run_block_kind()`): the block records
    `{"notebook": <clone-relative path>}` and NOTHING else — no `module`,
    no `function`, no `kwargs`. A notebook is not a callable, and giving
    it an empty `kwargs` would be a key that means nothing to every reader
    downstream. Given together with `run_module`/`run_function` the call
    is refused here, before `validate_run_config()` is even reached, so
    the refusal names the ARGUMENT the caller passed rather than the
    config it would have produced.

    `runnerTemplate` records each asset's path and sha256 as inert
    provenance — deliberately not a drift check (see `SKILL.md`): a second
    staleness condition is explicitly out of scope for this skill.

    `unresolved_imports`, when non-empty, is recorded verbatim as
    `unresolvedImports` — the `--accept-unresolved` escape hatch turning a
    silence into a recorded, reportable decision (design #744 section 3).

    `unresolved_reads`, when non-empty, is recorded verbatim as
    `unresolvedReads` — the SAME omit-when-empty convention as
    `unresolvedImports`, but gated by the SEPARATE `--accept-unresolved-reads`
    flag (Unit 1, undeclared-read detection). A job folder generated
    before this field existed simply omits it; `validate_run_config()`
    checks required fields with no key allowlist, so absence never
    invalidates an existing job folder.

    `accepted_produced_reads`, when non-empty, is recorded verbatim as
    `acceptedProducedReads` (corrective batch) — the SAME omit-when-empty
    convention, gated by the SEPARATE `--accept-produced-reads` flag. A
    produced-read finding is a read of a path the same walked file set
    also writes (the job may exist to CREATE it on its first run); the
    flag turns the silence into a recorded, reportable decision the same
    way `--accept-unresolved`/`--accept-unresolved-reads` already do —
    this is RECLASSIFICATION with a recorded acceptance, never a silent
    exclusion: the operator is still told, and still has to decide.

    `smoke_required_evidence`, when given, is recorded verbatim as
    `run.smoke.requiredEvidence` — the dot-separated field paths
    `shard_io.completeness()` will later walk to judge a smoke run's own
    returned stamp. This module never learns what any of those paths
    MEAN; it only carries the list from the target's own declaration (a
    repeatable `--smoke-required-evidence` CLI flag) to wherever `smoke
    record` reads it back from — the SAME "caller brings the vocabulary"
    discipline `completeness(stamp, required)` already holds in
    `shard_io.py`. Given without also declaring a smoke block, it is
    refused: a required-evidence list with no smoke run to judge is not a
    value this schema can express.

    `accelerator_kind`/`accelerator_architectures`, when given, are
    recorded verbatim as `accelerator: {kind, architectures[]}`. This
    module names only those two fields and never a value: an architecture
    list, never a device name, because a name answers *is this the card I
    named* (a device's own name string is not even stable across how many
    units share it) while an architecture list answers *can this build
    run here* — the question `runner_bootstrap.py`'s accelerator gate
    actually asks, against the torch build installed at run time. Omitted
    entirely, no `accelerator` block is written and the generated job
    behaves exactly as it did before this field existed (additive,
    `schemaVersion` stays 1). Given partially — a kind with no
    architecture list, or the reverse — is refused: neither half alone is
    a value this schema can express.

    `local_budget_seconds`, when given, is recorded verbatim as
    `localBudget: {seconds}` — the target's own declared threshold for
    whether a job's pilot-projected cost is locally tolerable, the SAME
    "declared here, compared elsewhere" discipline `accelerator` already
    holds: this module names the number and never judges it. Seconds,
    because `search_cost_forecast()` (`implementation_cli.py`) projects
    in seconds and the comparison this budget exists for is seconds
    against seconds, with no unit conversion anywhere. Omitted entirely,
    no `localBudget` block is written — silence, not a default of `0` or
    any other value, because `classify_remote_necessity()` (design D3)
    treats a target that declared nothing as a fact it does not have,
    never as a target that declared "no time at all".

    `environment_requirements`/`environment_index_url`, when given, are
    recorded verbatim as `environment: {install: {requirements[],
    indexUrl}}` (Decision 3). This module names only those two fields
    and never a package: it does not know which tensor-library build a
    target needs, only that the target declared one. `indexUrl` is
    optional within a declared install — a caller relying on pip's own
    default index declares `requirements` alone — but declaring
    `indexUrl` with no `requirements` is refused: an index with nothing
    to install is not a value this schema can express. Omitted entirely,
    no `environment` block is written and the generated job behaves
    exactly as it did before this field existed (additive, `schemaVersion`
    stays 1). Specifier-shape validation (a requirement beginning with
    `-` is refused) happens where the install actually runs —
    `runner_bootstrap.py`'s `install_environment()` — not here: this
    module only carries the target's own declared list.
    """
    validated_clone_paths = validate_clone_paths(clone_paths)
    has_smoke_block = bool((smoke_module and smoke_function) or smoke_notebook)
    if smoke_required_evidence and not has_smoke_block:
        raise JobFolderError(
            "smoke_required_evidence was given but no smoke module/function "
            "was declared; a required-evidence list with no smoke run to "
            "judge is not a value run-config.json can express"
        )
    has_accelerator = accelerator_kind is not None or accelerator_architectures is not None
    if has_accelerator and not (accelerator_kind and accelerator_architectures):
        raise JobFolderError(
            "accelerator_kind and accelerator_architectures must both be "
            "given (and non-empty), or both omitted; a kind with no "
            "architecture list, or the reverse, is not a value "
            "run-config.json can express"
        )
    has_environment_install = bool(environment_requirements)
    if environment_index_url and not has_environment_install:
        raise JobFolderError(
            "environment_index_url was given but no environment_requirements; "
            "an index URL with nothing to install is not a value "
            "run-config.json can express"
        )
    # Exactly one shape per block, and the block carries ONLY that shape's
    # own keys — a notebook block never gets an empty `kwargs`, because a
    # notebook is not called with arguments and a key that means nothing
    # is a key a later reader has to decide what to do with.
    # `run_block_kind()` inside `validate_run_config()` below refuses the
    # both-declared and neither-declared cases; these branches only decide
    # which keys get written.
    if run_notebook and (run_module or run_function):
        raise JobFolderError(
            f"run_notebook ({run_notebook!r}) was given together with "
            f"run_module/run_function ({run_module!r}/{run_function!r}); a "
            "run declares exactly one of the two shapes, never both"
        )
    if smoke_notebook and (smoke_module or smoke_function):
        raise JobFolderError(
            f"smoke_notebook ({smoke_notebook!r}) was given together with "
            f"smoke_module/smoke_function ({smoke_module!r}/"
            f"{smoke_function!r}); a smoke run declares exactly one of the "
            "two shapes, never both"
        )
    if run_notebook:
        run_block: dict = {"notebook": validate_notebook_path(run_notebook, where="run")}
    else:
        run_block = {
            "module": run_module,
            "function": run_function,
            "kwargs": dict(run_kwargs or {}),
        }
    if has_smoke_block:
        if smoke_notebook:
            smoke_block: dict = {
                "notebook": validate_notebook_path(smoke_notebook, where="run.smoke")
            }
        else:
            smoke_block = {
                "module": smoke_module,
                "function": smoke_function,
                "kwargs": dict(smoke_kwargs or {}),
            }
        if smoke_required_evidence:
            smoke_block["requiredEvidence"] = list(smoke_required_evidence)
        run_block["smoke"] = smoke_block

    run_config = {
        "schemaVersion": RUN_CONFIG_SCHEMA_VERSION,
        "product": product,
        "service": service,
        "jobName": job_name,
        "commit": commit,
        "repo": {"url": repo_url, "ref": repo_ref},
        "clonePaths": list(validated_clone_paths),
        "run": run_block,
        "runnerTemplate": [
            {"path": "assets/runner_bootstrap.py", "sha256": _asset_sha256(bootstrap_asset)},
            {"path": "assets/runner_invoke.py", "sha256": _asset_sha256(invoke_asset)},
        ],
    }
    if unresolved_imports:
        run_config["unresolvedImports"] = list(unresolved_imports)
    if unresolved_reads:
        run_config["unresolvedReads"] = list(unresolved_reads)
    if accepted_produced_reads:
        run_config["acceptedProducedReads"] = list(accepted_produced_reads)
    if has_accelerator:
        run_config["accelerator"] = {
            "kind": accelerator_kind,
            "architectures": list(accelerator_architectures),
        }
    if local_budget_seconds is not None:
        run_config["localBudget"] = {"seconds": local_budget_seconds}
    if carry_paths:
        run_config["carryPaths"] = list(validate_carry_paths(carry_paths))
    if has_environment_install:
        install_block: dict = {"requirements": list(environment_requirements)}
        if environment_index_url:
            install_block["indexUrl"] = environment_index_url
        run_config["environment"] = {"install": install_block}
    validate_run_config(run_config)
    return run_config


def _notebook_cell(source_text: str) -> dict:
    return {
        "cell_type": "code",
        "metadata": {},
        "execution_count": None,
        "outputs": [],
        "source": source_text.splitlines(keepends=True),
    }


def build_notebook(bootstrap_asset: Path, invoke_asset: Path) -> dict:
    """Two cells, copied byte for byte from the two runner assets, with
    zero interpolation — the same bytes for every job, which is exactly
    what makes `runner_bootstrap.py`/`runner_invoke.py` unit-testable as
    modules in the forge suite rather than only as embedded, per-job prose.

    `metadata.kernelspec` is not optional decoration: confirmed against a
    real remote kernel run, a notebook with no `kernelspec` at all makes
    the service's own runner (`papermill`) refuse before a single cell
    executes — `ValueError: No kernel name found in notebook and no
    override provided` — discovered only after a real push, quota
    already spent, for a notebook that was never going to run regardless
    of which target it clones. This is notebook-format correctness, true
    of every generated job unconditionally, never a fact about one target
    repository — which is exactly why it belongs here and nowhere else.
    """
    if not bootstrap_asset.is_file() or not invoke_asset.is_file():
        raise JobFolderError(
            f"runner assets are missing ({bootstrap_asset}, {invoke_asset}); "
            "generation refuses to build a job folder around a missing cell"
        )
    return {
        "cells": [
            _notebook_cell(bootstrap_asset.read_text(encoding="utf-8")),
            _notebook_cell(invoke_asset.read_text(encoding="utf-8")),
        ],
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def _rmtree(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


def generate_job(
    *,
    target: str | Path,
    service: str,
    job_name: str,
    product: str,
    commit: str | None = None,
    repo_url: str,
    repo_ref: str,
    clone_paths: Sequence[str],
    run_module: str | None = None,
    run_function: str | None = None,
    run_kwargs: Mapping[str, object] | None = None,
    run_notebook: str | None = None,
    smoke_module: str | None = None,
    smoke_function: str | None = None,
    smoke_kwargs: Mapping[str, object] | None = None,
    smoke_notebook: str | None = None,
    smoke_required_evidence: Sequence[str] | None = None,
    regenerate: bool = False,
    bootstrap_asset: str | Path | None = None,
    invoke_asset: str | Path | None = None,
    accept_unresolved: bool = False,
    accept_unresolved_reads: bool = False,
    accept_produced_reads: bool = False,
    accelerator_kind: str | None = None,
    accelerator_architectures: Sequence[str] | None = None,
    environment_requirements: Sequence[str] | None = None,
    environment_index_url: str | None = None,
    local_budget_seconds: int | None = None,
    repo_credential_path: str | Path | None = None,
    carry_paths: Sequence[str] | None = None,
) -> Path:
    """Generate one job folder, atomically, refusing to overwrite an
    existing one unless `regenerate=True`.

    A run is declared as EITHER a `run_module`/`run_function` pair or a
    `run_notebook` — exactly one, judged by `run_block_kind()` before the
    pin is even resolved. The notebook shape exists so that what a worker
    runs can be the notebook the pilot ran, rather than a second
    implementation of it asserting in a docstring that the two agree.
    Both shapes stay reachable on purpose: a worker asked to settle one
    question is legitimately a function call, and some entries cannot be
    named by a `module`/`function` contract at all.

    `commit` may be omitted, and then defaults to the target's HEAD
    through `_resolve_pin()` — one implementation shared with the CLI, so
    the two cannot disagree about what HEAD means, and a purely local one
    that reaches no remote. The default is not independent of the
    conditions below: HEAD is the code that was validated precisely
    because the `clean-worktree` condition proves the working tree holds
    the same bytes and the `pin-is-head` condition proves the pin is that
    commit. Resolution happens BEFORE
    them, and a defaulted pin then meets every condition exactly as an
    explicit one does. An explicit `commit` is never substituted,
    discovered or overridden.

    Order is fixed: resolve `target` (no other check runs against a raw,
    unresolved path); derive and validate `destination`; resolve the pin;
    put it
    through every condition in `PIN_CONDITIONS`, in that order, via the
    single shared `verify_pin_preconditions()` — which is also the only
    thing `submit` calls, so the two decision points cannot drift in
    order or in which conditions they enforce — refusing before anything
    else runs if any of them fails; resolve and cross-check
    `clone_paths` against what the declared entry modules actually import
    (`resolve_clone_paths()`), refusing before anything else is built if
    that check fails; build `run-config.json` and the
    notebook fully, in memory, before touching disk; only then check for an
    existing folder or a leftover `.partial/`. Everything from that point
    on writes into `<job>.partial/` first — `run-config.json`,
    `runner.ipynb`, and the adapter-supplied metadata file, in that order —
    and only a fully-written `.partial/` is ever renamed into place. A
    half-written job folder therefore cannot exist: either `.partial/`
    never became `destination` at all, or it did so as one atomic rename
    with everything already inside it.

    Regeneration replaces the existing folder without ever leaving
    `destination` half-old-half-new: the existing folder is renamed aside
    (an atomic rename to a fresh, guaranteed-unused name) before the new
    `.partial/` is renamed into `destination`'s place, and only removed
    once that second rename has actually succeeded. If the second rename
    itself fails, the aside copy is renamed straight back — `destination`
    is either the old job folder or the new one at every instant an
    outside observer could look, never neither and never a mix.

    `accelerator_kind`/`accelerator_architectures`, when BOTH omitted (the
    from-zero case), are resolved from `service`'s own registered default
    via `ADAPTER.resolve_default_accelerator()` — service knowledge,
    read the same way `ADAPTER.resolve_metadata()` is a few lines below,
    never a value this module invents or hardcodes itself. A caller
    supplying either half explicitly always wins outright; a service
    that registered no default (or registered none at all) leaves the
    generated job with no `accelerator` block, exactly as every job did
    before this default existed — silence, not a guess.
    `environment_requirements`/`environment_index_url` carry no such
    default: an install is TARGET knowledge (which packages a specific
    repository needs), never service knowledge, so this function only
    ever forwards what a caller explicitly declared.

    `local_budget_seconds` carries no default of any kind, unlike
    `accelerator_kind`/`accelerator_architectures` above: there is no
    service-registered fallback and no forge-invented value. Omitted, no
    `localBudget` block is written at all — see `build_run_config()`'s
    own docstring for why that silence must never become a `0`.

    `carry_paths` (kernel-carry S1), when given, is recorded as
    `carryPaths`: the paths, relative to the product folder, a
    continuation of this job restores from the session before it
    (`validate_carry_paths()`). Omitted or empty, no `carryPaths` key is
    written and `submit` carries nothing for this job, exactly as before.

    `repo_credential_path` (S3) is forwarded verbatim into that same
    condition set, where only the network-reaching `pin-published` probe
    ever reads it: with a path, generation's reachability check
    authenticates through the same askpass material a credentialed
    runner clone uses, admits `https://` remotes only, and reads the
    token at exactly one expression. Omitted (every pre-S3 caller), every
    condition behaves exactly as before.

    `service` is validated against BOTH registries together (the
    union-of-registries rule): a service known to either registry is
    legal. An adapter that registers no metadata assembler — a backend
    whose service reads no metadata file — generates a job folder holding
    exactly `run-config.json` and `runner.ipynb`; no third file is
    invented for it. A name unknown to both registries refuses here, by
    name, before anything is written.
    """
    resolved_target = resolve_target(target)
    destination = resolve_destination(resolved_target, service, job_name)
    # Before the pin is resolved: resolution may already call git with it.
    refuse_repo_url_credentials(repo_url, where="generation")
    # #56: the runner clones with no SSH agent and no key, so an SSH remote
    # is one no job generated from it could ever clone. Refused by rule here,
    # before any git call; `submit` still probes an older job folder's remote.
    if _looks_like_ssh_remote(repo_url):
        raise JobFolderError(
            "generation refuses: the declared remote is an SSH remote (scp-shaped "
            "host:path, ssh://, git+ssh:// or ssh+git://), and the runner's clone "
            "has no SSH agent and no key, so it could never clone it. Declare the "
            "repository's https:// URL (with --repo-credential for a private one), "
            "or a local path for a local rehearsal."
        )

    # The two shapes are decided HERE, before the pin is resolved and long
    # before anything is written, so a caller who declared neither shape —
    # or both — is refused by the same `run_block_kind()` that will judge
    # the written config, rather than by whichever downstream call happens
    # to trip over the gap first. `run_block_kind()` is given the block
    # this call is ABOUT to build, not one read back off disk.
    run_block_kind(
        {k: v for k, v in
         (("module", run_module), ("function", run_function),
          ("notebook", run_notebook)) if v is not None},
        where="generation's run block",
    )
    if smoke_module or smoke_function or smoke_notebook:
        run_block_kind(
            {k: v for k, v in
             (("module", smoke_module), ("function", smoke_function),
              ("notebook", smoke_notebook)) if v is not None},
            where="generation's smoke block",
        )

    entry_modules = [name for name in (run_module, smoke_module) if name]
    entry_notebooks = [nb for nb in (run_notebook, smoke_notebook) if nb]
    clone_paths = with_entry_notebooks(clone_paths, entry_notebooks)

    commit = _resolve_pin(resolved_target, commit, repo_url=repo_url,
                          repo_ref=repo_ref, clone_paths=clone_paths)
    verify_pin_preconditions(
        target=resolved_target,
        commit=commit,
        clone_paths=clone_paths,
        notebooks=entry_notebooks,
        repo_url=repo_url,
        repo_ref=repo_ref,
        decision="generation",
        # S3: the generation-time reachability probe meets the same
        # credential-conditional behavior `submit`'s gate does; `None`
        # (every pre-S3 caller) is byte-identical to today.
        repo_credential_path=repo_credential_path,
    )

    clone_resolution = resolve_clone_paths(
        resolved_target, entry_modules, clone_paths, entry_notebooks
    )
    if clone_resolution["computedNotDeclared"]:
        raise JobFolderError(
            "generation refuses: these imports resolve to clone paths not "
            "declared in --clone-path: "
            f"{clone_resolution['computedNotDeclared']}"
        )
    if clone_resolution["unresolved"] and not accept_unresolved:
        raise JobFolderError(
            "generation refuses: uncertain imports found (pass "
            "--accept-unresolved to record and proceed instead of refusing): "
            f"{clone_resolution['unresolved']}"
        )
    if clone_resolution["computedReadsNotDeclared"]:
        raise JobFolderError(
            "generation refuses: these reads resolve to paths not declared "
            "in --clone-path: "
            f"{clone_resolution['computedReadsNotDeclared']}"
        )
    if clone_resolution["producedReadsNotDeclared"] and not accept_produced_reads:
        raise JobFolderError(
            "generation refuses: these reads resolve to paths not declared "
            "in --clone-path, but the same walked file set also WRITES them "
            "— this job may exist to produce the file on its first run, so "
            "declaring it would require it to already exist at the pin "
            "(pass --accept-produced-reads to record this decision and "
            "proceed instead of refusing; this is a SEPARATE flag from "
            "--accept-unresolved-reads, which never waives this refusal): "
            f"{clone_resolution['producedReadsNotDeclared']}"
        )
    if clone_resolution["unresolvedReads"] and not accept_unresolved_reads:
        raise JobFolderError(
            "generation refuses: uncertain reads found (pass "
            "--accept-unresolved-reads to record and proceed instead of "
            "refusing; this is a SEPARATE flag from --accept-unresolved, "
            "which never waives this refusal): "
            f"{clone_resolution['unresolvedReads']}"
        )

    resolved_bootstrap = Path(bootstrap_asset) if bootstrap_asset else DEFAULT_BOOTSTRAP_ASSET
    resolved_invoke = Path(invoke_asset) if invoke_asset else DEFAULT_INVOKE_ASSET

    # From-zero gap (session addition): a caller declaring NEITHER half of
    # the accelerator pair gets the service adapter's own registered
    # default, never a value this module invents. An explicit caller value
    # (either half) always wins and skips this lookup entirely — matching
    # `build_run_config()`'s own refusal below for a half-given pair.
    if accelerator_kind is None and accelerator_architectures is None:
        default_accelerator = ADAPTER.resolve_default_accelerator(service)
        if default_accelerator is not None:
            accelerator_kind, accelerator_architectures = default_accelerator()

    run_config = build_run_config(
        product=product,
        service=service,
        job_name=job_name,
        commit=commit,
        repo_url=repo_url,
        repo_ref=repo_ref,
        clone_paths=clone_paths,
        run_module=run_module,
        run_function=run_function,
        run_kwargs=run_kwargs,
        run_notebook=run_notebook,
        smoke_module=smoke_module,
        smoke_function=smoke_function,
        smoke_kwargs=smoke_kwargs,
        smoke_notebook=smoke_notebook,
        bootstrap_asset=resolved_bootstrap,
        invoke_asset=resolved_invoke,
        unresolved_imports=clone_resolution["unresolved"] if accept_unresolved else None,
        unresolved_reads=(
            clone_resolution["unresolvedReads"] if accept_unresolved_reads else None
        ),
        accepted_produced_reads=(
            clone_resolution["producedReadsNotDeclared"]
            if accept_produced_reads else None
        ),
        smoke_required_evidence=smoke_required_evidence,
        accelerator_kind=accelerator_kind,
        accelerator_architectures=accelerator_architectures,
        environment_requirements=environment_requirements,
        environment_index_url=environment_index_url,
        local_budget_seconds=local_budget_seconds,
        carry_paths=carry_paths,
    )
    notebook = build_notebook(resolved_bootstrap, resolved_invoke)

    # The union-of-registries rule: a service is known when EITHER
    # registry knows it. An adapter that registered no metadata assembler
    # simply writes no third file; a name unknown to BOTH refuses here,
    # by name, while refusing still costs nothing — the same placement
    # every check above this line holds.
    try:
        ADAPTER.resolve(service)
        adapter_known = True
    except KeyError:
        adapter_known = False
    try:
        metadata_assembler = ADAPTER.resolve_metadata(service)
    except KeyError:
        metadata_assembler = None
    if metadata_assembler is None and not adapter_known:
        raise JobFolderError(
            f"generation refuses: no adapter and no metadata assembler is "
            f"registered under {service!r}; register the service's own module "
            "under scripts/adapters/ (reachable through the CLI's own "
            "--service side-loader) before generating a job for it"
        )
    metadata_file: tuple[str, str] | None = (
        metadata_assembler(run_config) if metadata_assembler is not None else None
    )

    if destination.is_dir() and not regenerate:
        raise JobFolderError(
            f"{destination} already exists; pass regenerate=True (or "
            "--regenerate) to replace it"
        )

    partial = destination.with_name(destination.name + PARTIAL_SUFFIX)
    if partial.exists():
        raise JobFolderError(
            f"a leftover {partial} exists from a previous failed generation; "
            "it is never read as a job folder — remove it by hand before "
            "retrying"
        )

    partial.mkdir(parents=True)
    try:
        (partial / RUN_CONFIG_FILENAME).write_text(
            json.dumps(run_config, sort_keys=True, indent=2), encoding="utf-8"
        )
        (partial / RUNNER_FILENAME).write_text(
            json.dumps(notebook, indent=1), encoding="utf-8"
        )
        if metadata_file is not None:
            metadata_name, metadata_text = metadata_file
            (partial / metadata_name).write_text(metadata_text, encoding="utf-8")
    except BaseException:
        _rmtree(partial)
        raise

    aside = None
    if destination.is_dir():
        aside = destination.with_name(destination.name + STALE_SUFFIX_PREFIX + uuid.uuid4().hex)
        os.replace(str(destination), str(aside))
    try:
        os.replace(str(partial), str(destination))
    except BaseException:
        if aside is not None:
            os.replace(str(aside), str(destination))
        raise
    if aside is not None:
        _rmtree(aside)

    return destination


# ---------------------------------------------------------------------------
# read() — the single reader, staleness computed inside it (design #744 §4)
# ---------------------------------------------------------------------------

# The whole allowlist a git subprocess's environment is built from here —
# never `os.environ` forwarded wholesale, the same restraint
# `assets/runner_bootstrap.py`'s own `_run_git()` applies to its own child
# environment. This is a SEPARATE composition point from that one: the two
# live in different modules, with no import between them, so each has to
# hold this discipline on its own rather than inherit it.
#
# `runner_bootstrap.py:70` holds exactly `("PATH",)`, and this list is
# deliberately longer — but only along one axis. Everything past `PATH`
# decides whether the probe can REACH a host: proxy configuration, and the
# trust store a corporate CA is installed into. Nothing here decides WHO
# the probe is. No `HOME` (which is the whole of git's user-configuration
# story: `~/.gitconfig` carries `credential.helper`, `url.*.insteadOf` and
# `http.*.extraHeader`), no `SSH_AUTH_SOCK`, no askpass, no token. That is
# not caution, it is the point of the check.
#
# One credential-conditional amendment (S3; D6), and it is an amendment
# to this COMMENT, never to the tuple below. Credentialless, nothing
# changes: `runner_bootstrap.py`'s clone carries no credential step
# either, so a probe that authenticated would answer a question about a
# remote THIS operator can read and report it as a question about a
# remote the RUNNER can clone — the same defect this probe exists to
# close, moved one layer up. With `--repo-credential`, both sides
# authenticate with the SAME staged credential — the backend uploads the
# askpass material beside the executor, `runner_bootstrap.py` clones with
# it — and both transports are pinned to `https://` (SD14's scheme gate
# below, SD15's re-check in the runner), so the probe's answer is again a
# fact about the runner. The credential value travels through
# `_run_git()`'s `extra_env`, a channel deliberately separate from this
# allowlist: nothing here is widened by it.
#
# Both cases of every proxy variable: curl reads the lowercase spelling,
# and a corporate environment commonly sets only that one. Admitting one
# case and not the other turns a local misconfiguration into a refusal
# wearing the message of an unpublished commit.
GIT_ENV_ALLOWLIST = (
    "PATH",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "no_proxy",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "GIT_SSL_CAINFO",
)
GIT_TIMEOUT_SECONDS = 120.0

# The URL schemes a `repo_url` may name before any git call reaches it. Every
# other `<scheme>://` makes git exec a `git-remote-<scheme>` helper, and the
# `<transport>::<address>` form (`ext::`, `fd::`) names a helper command
# outright; both are refused by `_remote_transport_admissible()`. Local and
# scp-shaped remotes carry no scheme and stay admissible.
REMOTE_URL_SCHEMES = ("https", "http", "ssh", "git", "file", "git+ssh", "ssh+git")

# The env name the probe's askpass script reads the credential VALUE from.
# The value is handed to the git child through its environment — never
# argv, never a file — so it dies with the child process. S3/D6: this
# module's constant, and the script below is the only thing that reads it.
REPO_CREDENTIAL_ENV_NAME = "PSMITH_REPO_CREDENTIAL"

# The askpass script the credential-aware probe writes into its own scratch
# `TemporaryDirectory()` (mode 0o700) and points `GIT_ASKPASS` at for the
# one fetch call. It prints the value from the environment, so no token
# file exists locally at all and the scratch directory dies with the call.
REPO_CREDENTIAL_ASKPASS_SCRIPT = """#!/bin/sh
# Answers git's credential prompts from the environment. Never a file:
# the value dies with the child. One read site for the token exists in
# this module, and this is the script it feeds.
printf '%s' "$PSMITH_REPO_CREDENTIAL"
"""

# What `_run_git()` sets itself on every call, never forwarded from this
# process. `GIT_TERMINAL_PROMPT=0` closes git's own prompt. The three
# `GIT_CONFIG_*` entries reset `credential.helper` to empty: dropping `HOME`
# drops `~/.gitconfig`, but not the SYSTEM config, and Homebrew's git ships
# one naming `osxkeychain`. Measured 2026-10-26: with no `HOME` that helper
# waited on the macOS keychain until the probe's whole 240 s budget expired,
# so a published commit refused as unconfirmable. With the helper reset,
# only the probe's own askpass (or nothing) answers a credential prompt --
# which is what "nothing here decides WHO the probe is" already required.
GIT_FIXED_ENV = {
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_CONFIG_COUNT": "1",
    "GIT_CONFIG_KEY_0": "credential.helper",
    "GIT_CONFIG_VALUE_0": "",
}

# `pin-published`'s own budget (Finding 4 case A; Decision 13a) --
# deliberately a SEPARATE constant from `GIT_TIMEOUT_SECONDS` above, never
# the same one reused. That local budget times two nearly-instant,
# purely-local calls this module makes elsewhere (`rev-parse`,
# `cat-file -e`); the pin-published probe below is the one call in this
# whole module that transfers real bytes over the network, and a shared
# budget made the verdict track the LINK, not the pin: measured against
# the live remote this skill targets, transferring 12.4 MiB on a slow
# connection took 209s once and 27s on an identical re-run of the SAME
# commit. Under the old shared 120s budget, the first, slower run
# reported the commit as "not pushed" -- a true measurement (the transfer
# really did take longer than 120s) producing a false conclusion (the
# commit was published all along), because the timeout and the
# reachability question shared one message. 240s (~1.15x the measured
# 209s worst case, rounded up) is picked from that measurement, not
# invented: headroom above the observed worst case while staying
# bounded, never merged back into the local calls' own 120s, which they
# have never needed.
PIN_PUBLISHED_TIMEOUT_SECONDS = 240.0

# `pin-published`'s LOCAL weight reader owns its own budget too --
# deliberately a THIRD, separate constant from both of the two above,
# never either one reused. Measured, not invented (Decision 5): five
# consecutive warm-cache timings each of the reader's three calls
# (`git config --local --get-regexp`, `git rev-parse --verify --quiet
# <ref>^{commit}`, `git rev-list --count <anchor>..<pin> --`), on the
# apply machine (macOS 26.5.2, Darwin 25.5.0, arm64), against this
# repository (1,131 commits) and the largest other repository already on
# that disk (48 commits). The observed max across every call and both
# repositories was ~6.2ms (`rev-parse --verify`, this repository). This
# budget governs a purely local history walk whose cost this measurement
# cannot fully sample -- a much larger repository's history on a machine
# that is not this one -- so unlike `PIN_PUBLISHED_TIMEOUT_SECONDS`'s
# ~1.15x its own measured worst case, this constant is deliberately many
# multiples above the ~6.2ms observed (5.0s is roughly 800x that
# worst case): undershooting here only produces `unmeasurable`, a
# first-class outcome documented in `SKILL.md`, never a wrong verdict --
# the opposite failure mode of the network probe's own budget. Per
# `_run_git()` call (`timeout=` reaches `subprocess.run`), so the
# reader's wall-clock worst case is three times this constant (15.0s).
PIN_WEIGHT_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True)
class JobFolder:
    """A job folder read back, staleness attached.

    There is no `is_stale()` a caller can forget: `staleness` is computed
    INSIDE `read()`, before it ever constructs one of these, so getting a
    `JobFolder` back without a staleness verdict alongside it is not
    something this module's API can express — reading a job folder
    without checking it is not expressible.
    """

    path: Path
    run_config: Mapping[str, object]
    staleness: Mapping[str, object]


def _run_git(
    args: Sequence[str],
    *,
    cwd: str | Path,
    timeout: float = GIT_TIMEOUT_SECONDS,
    extra_env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess:
    """The single composition point for every git invocation this module
    makes. `shell=False` with a list argv means a value carrying shell
    metacharacters (a pinned commit, in particular) reaches `argv` as one
    element and is never evaluated — no shell is ever invoked to interpret
    it. The environment is built from `GIT_ENV_ALLOWLIST` alone, never
    this process's own `os.environ` forwarded wholesale. `cwd` is always
    a path the caller has already resolved — never `git -C` applied to a
    raw, unresolved argument. A non-zero exit raises `JobFolderError`
    rather than being silently ignored; an expired timeout raises
    `GitTimeoutError`, a distinct subclass of the same, so a caller that
    needs to tell "the question could not be finished asking" apart from
    "the answer was no" can (Finding 4 case A) — every existing caller
    that only catches `JobFolderError` keeps catching this too.

    `extra_env` (S3) is a caller-supplied mapping merged into the child's
    environment AFTER the allowlist and `GIT_TERMINAL_PROMPT=0`. It is
    deliberate that this is a separate channel from `GIT_ENV_ALLOWLIST`:
    the allowlist is a statement about WHO the probe is (and is asserted
    to stay empty of authorization-shaped names), while `extra_env` is an
    explicit, per-call decision the caller made — the credential-aware
    probe's askpass path and value. Entries are always passed by name,
    never an `os.environ` passthrough, and the allowlist itself never
    changes. `None` (every pre-S3 caller) is byte-identical to today.

    `GIT_TERMINAL_PROMPT=0` and `stdin=DEVNULL` make "this never blocks
    waiting for a human" true rather than hopeful, and they are set HERE
    rather than at the one call site that needs them because a setting
    that has to be remembered at each call site is a setting that will
    eventually be forgotten at one. They are inert for the local
    `rev-parse`/`cat-file`/`diff` calls, which read nothing from stdin
    and ask nobody for a password. They are load-bearing for the
    reachability probe: the two are separate channels, and closing only
    one leaves the other open. `GIT_TERMINAL_PROMPT=0` closes git's own
    credential prompt over HTTPS; it says nothing to `ssh`, which reads a
    passphrase straight from the terminal. In an interactive session this
    process's stdin IS that terminal, so an SSH remote would hold the
    120-second timeout open waiting for a passphrase nobody is present to
    type, instead of refusing at once with a message an operator can act
    on.
    """
    argv = ["git", *args]
    env = {name: os.environ[name] for name in GIT_ENV_ALLOWLIST if name in os.environ}
    env.update(GIT_FIXED_ENV)
    if extra_env:
        env.update(extra_env)
    try:
        result = subprocess.run(
            argv,
            shell=False,
            cwd=str(cwd),
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise GitTimeoutError(f"git {' '.join(args)} timed out after {timeout}s") from exc
    except OSError as exc:
        raise JobFolderError(f"could not run git: {exc}") from exc
    if result.returncode != 0:
        raise JobFolderError(
            f"git {' '.join(args)} exited {result.returncode}: {result.stderr.strip()}"
        )
    return result


def _remote_transport_admissible(repo_url: str) -> bool:
    """Whether `repo_url` may reach git at all, as a remote and nothing else.

    `run-config.json` travels with a cloned repository, so its `repo_url` is
    input, not configuration this process wrote. Refused: a value beginning
    with `-` (an option, even though every call also ends options with
    `--`), the `<transport>::<address>` helper form, and any `<scheme>://`
    outside `REMOTE_URL_SCHEMES`. A local path or an scp-shaped
    `git@host:owner/repo.git` names no helper and stays admissible: this
    gate decides which transport may run, never which remote is wanted.
    """
    # The helper form is `<transport>::<address>` at the start of the URL; a
    # `::` inside an IPv6 literal (`https://[2001:db8::1]/r.git`) is not one.
    if not repo_url or repo_url.startswith("-") or re.match(r"[A-Za-z][A-Za-z0-9+.-]*::", repo_url):
        return False
    scheme = re.match(r"([A-Za-z][A-Za-z0-9+.-]*)://", repo_url)
    return scheme is None or scheme.group(1).lower() in REMOTE_URL_SCHEMES


def refuse_repo_url_credentials(repo_url: object, *, where: str) -> None:
    """Refuse a `repo_url` that embeds a credential, without echoing it (#56).

    `run-config.json` is committed and uploaded, and the URL reaches git's
    argv and refusal text, so `https://<token>@host/…` or
    `<user>:<password>@…` would leak the secret into all three. Any userinfo
    is refused, except a bare SSH login name (`git@host:o/r.git`,
    `ssh://git@host/r.git`), which names an account and carries no secret.
    Private remotes authenticate through `--repo-credential` instead.
    """
    if not isinstance(repo_url, str):
        return
    scheme, separator, rest = repo_url.partition("://")
    authority = re.split(r"[/?#]", rest if separator else repo_url, maxsplit=1)[0]
    if "@" not in authority:
        return
    userinfo = authority.rsplit("@", 1)[0]
    ssh_login = (not separator or scheme.lower() in ("ssh", "git+ssh", "ssh+git"))
    if ssh_login and ":" not in userinfo:
        return
    raise JobFolderError(
        f"{where} refuses: the declared remote embeds a credential (a user, "
        "password or token before '@'); a credential is never written to "
        "run-config.json, passed to git or printed. Declare the remote "
        "without it and pass the token file with --repo-credential."
    )


def _looks_like_ssh_remote(repo_url: str) -> bool:
    """`ssh://…` (or `git+ssh://`, `ssh+git://`), or scp-shaped `git@host:owner/repo.git`.

    Three uses (SD14, then #56):

    * refusing an SSH remote at GENERATION, before any git call (#56,
      operator decision): the runner's clone has no SSH agent and no key,
      so no job generated from an SSH remote could ever clone it;
    * enriching a refusal that has already happened — its original use,
      and the only one the credentialLESS submit-time probe has, which
      still probes an older job folder's SSH remote instead of refusing it;
    * deciding an explicit refusal BEFORE the probe's scratch repository
      exists — ONLY when a repository credential was supplied. With a
      credential, the old "not refused on sight" reasoning is void: the
      operator has declared a token path, so the runner will present one,
      and `runner_bootstrap`'s clone has no SSH agent and no key, so a
      credential cannot travel over SSH at all. In that one case an
      SSH-shaped remote is refused by name. See `_verify_commit_reachable()`.
    """
    lowered = repo_url.lower()
    if lowered.startswith(("ssh://", "git+ssh://", "ssh+git://")):
        return True
    if "://" in repo_url:
        return False
    host, separator, _ = repo_url.partition(":")
    return bool(separator) and "/" not in host


@dataclass(frozen=True)
class _CachedWeight:
    """What the local cache says the pin holds beyond the declared remote.

    `measured` is the ONLY gate. A measured zero is a real answer -- the
    cache already reaches the pin, so the probe most likely failed for a
    local reason rather than the remote refusing -- and it is a different
    fact from a read that could not be taken.
    """

    measured: bool
    commits: int = 0
    anchor_ref: str = ""
    anchor_commit: str = ""
    reason: str = ""


# One clause per `_CachedWeight.reason` code, rendered into the
# unmeasurable refusal shape. Every code the reader can produce has a
# clause here; there is no fifth outcome.
_WEIGHT_UNMEASURABLE_REASONS = {
    "no-local-repository": "no local repository was available to read it from",
    "no-exact-url-match": "no local remote is configured with exactly that URL",
    "ambiguous-url-match": (
        "more than one local remote is configured with exactly that URL, "
        "and those records can disagree"
    ),
    "anchor-unreadable": "the local record of that remote's branch could not be read",
}


def _unpushed_weight_from_cache(
    target: Path | None, commit: str, repo_url: str, repo_ref: str
) -> _CachedWeight:
    """How far `commit` sits beyond the last state this clone's cache
    recorded for `repo_url`, read entirely from state already on disk.

    Never raises. Never contacts a remote. Three local git calls at most
    (`config`, `rev-parse`, `rev-list`), each bounded by
    `PIN_WEIGHT_TIMEOUT_SECONDS`. Every internal failure -- a missing
    `target`, zero or more than one exact URL match, a missing
    remote-tracking ref, or any git invocation failure -- resolves to
    `_CachedWeight(measured=False, reason=...)` inside this function;
    nothing escapes it. A helper that can raise a second kind of refusal
    has become a guard, and this is not one (Decision 3).

    Anchor resolution (Decision 2), each step failing into unmeasurable:

    1. `git config --local --get-regexp` for every configured remote URL.
    2. Keep only entries whose value is byte-identical to `repo_url` --
       no strip, no normalisation, no case folding. Zero matches or two
       or more matches both resolve to unmeasurable: an ambiguous cache
       is an answer the operator cannot see the basis for.
    3. The anchor ref is `refs/remotes/<name>/<branch>`, `<branch>` being
       `repo_ref` with one leading `refs/heads/` removed; a `repo_ref`
       still `refs/`-prefixed after that removal has no general
       remote-tracking mirror and resolves to unmeasurable.
    """
    if target is None:
        return _CachedWeight(measured=False, reason="no-local-repository")
    try:
        try:
            listed = _run_git(
                ["config", "--local", "--get-regexp", r"^remote\..*\.url$"],
                cwd=target,
                timeout=PIN_WEIGHT_TIMEOUT_SECONDS,
            ).stdout
        except JobFolderError:
            # `git config --get-regexp` signals "no key matches" with a
            # non-zero exit and empty output -- the ordinary shape of "no
            # remotes configured", not a failure. Reading it as zero
            # matches (rather than letting it fall through to the
            # generic `anchor-unreadable` outcome below) is what makes
            # this case name the correct, specific reason.
            listed = ""
        matches = []
        for line in listed.splitlines():
            key, _, value = line.partition(" ")
            if not key.startswith("remote.") or not key.endswith(".url"):
                continue
            if value == repo_url:
                matches.append(key[len("remote."):-len(".url")])
        if not matches:
            return _CachedWeight(measured=False, reason="no-exact-url-match")
        if len(matches) > 1:
            return _CachedWeight(measured=False, reason="ambiguous-url-match")
        remote_name = matches[0]

        branch = repo_ref
        if branch.startswith("refs/heads/"):
            branch = branch[len("refs/heads/"):]
        if branch.startswith("refs/"):
            return _CachedWeight(measured=False, reason="anchor-unreadable")
        anchor_ref = f"refs/remotes/{remote_name}/{branch}"

        anchor_commit = _run_git(
            ["rev-parse", "--verify", "--quiet", f"{anchor_ref}^{{commit}}"],
            cwd=target,
            timeout=PIN_WEIGHT_TIMEOUT_SECONDS,
        ).stdout.strip()
        if not anchor_commit:
            return _CachedWeight(measured=False, reason="anchor-unreadable")

        commits = int(
            _run_git(
                ["rev-list", "--count", f"{anchor_commit}..{commit}", "--"],
                cwd=target,
                timeout=PIN_WEIGHT_TIMEOUT_SECONDS,
            ).stdout.strip()
        )
    except (JobFolderError, OSError):
        return _CachedWeight(measured=False, reason="anchor-unreadable")
    return _CachedWeight(
        measured=True,
        commits=commits,
        anchor_ref=anchor_ref,
        anchor_commit=anchor_commit,
    )


def _verify_commit_reachable(
    commit: str,
    repo_url: str,
    repo_ref: str,
    *,
    decision: str = "generation",
    repo_credential_path: str | Path | None = None,
    target: str | Path | None = None,
) -> None:
    """Confirm `commit` is actually fetchable from the declared `repo_url`
    — the exact operation a runner performs when it clones that remote and
    checks out the pin inside the kernel — before `generate_job()` ever
    writes a byte.

    **The probe runs in a scratch repository, never in the target, and
    that is the whole of this function's correctness.** A repository that
    already holds the pin is the one place on earth that cannot ask this
    question: git answers a `want` it can satisfy locally without the
    remote's `upload-pack` ever being consulted. Since generation is run
    from the repository the operator just committed in, the target always
    holds the pin, so a probe run there returned clean for every pin
    anyone could write — including one committed a second ago and never
    pushed, which is precisely and only the case this check exists for.
    So: `tempfile.TemporaryDirectory()` → `git init -q` → fetch, and the
    directory is discarded on the way out.

    Two consequences that are easy to get backwards, both measured
    against the live remote this skill targets rather than reasoned about:

    * `--dry-run` suppresses ref updates. It does NOT suppress object
      transfer. One shallow probe wrote 12.8 MiB of objects into the
      repository it ran in while writing no ref and no `FETCH_HEAD` at
      all. Running it in the target would therefore grow the operator's
      object store by the remote's whole shallow tree on every single
      generation — a second, quieter reason the scratch directory is not
      merely a way of getting the right answer.
    * `--depth 1` is what `assets/runner_bootstrap.py:169` fetches at, so
      matching it is what makes "the probe is the operation the runner
      performs" true. It also happens to defeat the local-object-store
      shortcut on its own, because a shallow fetch has to negotiate a
      boundary with the remote — but that is a git implementation detail
      two flags deep, and this function does not lean on it. The scratch
      repository makes the question structurally unanswerable from local
      state; the depth makes it the runner's question. Neither one
      substitutes for the other.
    * The fetch call passes `timeout=PIN_PUBLISHED_TIMEOUT_SECONDS`
      explicitly — a THIRD fact measured against the same live remote,
      easy to get backwards in the same way: `_run_git()`'s own default,
      `GIT_TIMEOUT_SECONDS` (120s), is what the `git init -q` call above
      still runs under, because that call is purely local and never
      needed more. The fetch transfers real bytes, and 12.4 MiB on a slow
      connection took 209s once and 27s on an identical re-run of the
      SAME commit. Sharing one budget between the two made the verdict
      track the LINK, not the pin: the slower run reported the commit as
      "not pushed" from transfer time alone. A timeout is "the question
      could not be asked", never "the answer is no", and the two must not
      share one refusal message either — see the two `except` branches
      below.

    `git cat-file -e <pinned>^{commit}` (used by `_staleness_for()` below)
    only proves the pin exists in the target's LOCAL history; it is silent
    on whether `repo_url` can serve it. `git ls-remote <repo_url>
    <commit>` cannot fill that gap either for a bare 40-hex commit SHA:
    `ls-remote` matches ref *names* against a pattern, and a commit hash
    is not a ref name unless it happens to collide with one, so it comes
    back empty with exit 0 whether or not the remote actually has the
    commit — reconfirmed against the live remote while rewriting this,
    not merely inherited from the note that first claimed it. `git fetch
    --dry-run --depth 1 <repo_url> <commit>` is the accurate equivalent:
    the remote's own upload-pack either serves the object graph reaching
    `commit` (exit 0) or refuses it with "not our ref" (non-zero) — the
    same failure a runner's own clone would hit, just paid for here
    instead of inside a kernel after quota is spent. It runs through
    `_run_git()`, the single composition point, so it inherits that
    function's `shell=False` list-argv, `GIT_ENV_ALLOWLIST`,
    `GIT_TERMINAL_PROMPT=0` and `stdin=DEVNULL` discipline rather than a
    second, parallel one — `repo_url` reaches an outside host and is
    treated as untrusted input the same way a pinned commit already is
    elsewhere in this module.

    The `git init` is inside the same `try` as the fetch, and so is the
    `TemporaryDirectory()` that precedes it. A scratch repository that
    cannot be created is an unanswerable question, and this module has
    one settled answer for those. Leaving either outside would let the
    failure surface as a bare `JobFolderError` — or, for the temporary
    directory, an unhandled `OSError`, which is a crash rather than a
    refusal — naming neither the commit nor the remote the operator has
    to act on.

    `repo_ref` is used for exactly one thing and never for a decision:
    the remedy sentence. The pin is deliberately NOT validated as
    contained in that ref — proving that needs either the ref's whole
    history (the unbounded cost `--depth 1` exists to avoid) or the
    remote's tip alone (false the moment anyone else pushes).

    Raises `JobFolderError` — refusing generation, exactly like the
    existing `computedNotDeclared` refusal, never a warning — both when
    the remote confirms it cannot serve `commit` AND when the question
    could not be asked at all (a DNS failure, a timeout, an unreachable
    host, a scratch repository that could not be made). A network
    failure cannot confirm reachability any more than it can deny it, the
    same way `_staleness_for()`'s own `unknown` verdict is never rendered
    as `fresh`. Generation is local and costs nothing to re-run once
    connectivity is back; a wrong PASS here costs spent remote-execution
    quota and a failure discovered only after the push — the exact
    expense this check exists to avoid. Git's own message (which does
    name the distinct underlying cause) is carried into the refusal
    rather than replaced with a second, coarser one.

    A timeout (`GitTimeoutError`, raised by `_run_git()` for exactly this
    case) is refused through its OWN branch, with its OWN wording, never
    folded into the same message a confirmed "not our ref" or a DNS
    failure produces (Finding 4 case A). A timeout means "the question
    could not be finished asking" — it is silent on which answer the
    remote would have given — and is a categorically different fact from
    "the remote answered no", even though both refuse generation exactly
    the same way. A shared budget once let a slow-but-successful fetch
    time out and get reported with the SAME "could not be confirmed
    reachable ... push it and pin the commit the remote actually
    received" wording a genuine refusal gets: a true measurement (the
    transfer took over 120s) producing a false conclusion (the commit
    must be unpublished), because the timeout and the refusal shared one
    message. `PIN_PUBLISHED_TIMEOUT_SECONDS` narrows how often this
    branch fires at all; this message split is what keeps it honest on
    the rarer occasion a probe still exceeds even that wider budget.

    An SSH-shaped `repo_url` gets a sentence added to that same refusal,
    not a guard of its own. The probe is unauthenticated on purpose, and
    so is the runner, so `Permission denied (publickey)` here is a real
    finding about the job rather than a local accident — but it reads
    like a local accident unless the message says so. Refusing SSH URLs
    on sight instead would be deciding remote policy on the strength of a
    colon in a string, and would refuse a working deploy-key setup.

    `repo_credential_path` (S3/D6) is the ONE credential-conditional
    behavior this function has; with `None` (every pre-S3 caller) the
    function is byte-identical to today. With a path, the scheme decides
    BEFORE the scratch repository is created:

    * only `https://` is admissible. The credential is a bearer secret
      git presents to whatever URL the remote names and to whatever
      transport that URL selects, and this skill's runner-side clone
      carries no SSH agent and no key, so a credential can never travel
      over SSH. An SSH-shaped remote is refused by name, with its own
      message — the credentialless "colon in a string" reasoning dies the
      moment the operator has declared a token path, because the runner
      will now present one. Every other scheme (`http://`, `file://`, a
      bare local path) refuses naming the HTTPS-only rule. A
      credentialless call keeps today's exact behavior, including the
      enriched-refusal sentence, because that call's premise (an
      anonymous probe standing in for an anonymous runner) is still true;
    * the token is read at exactly ONE expression — a single
      `read_text().strip()` — and handed to the fetch call's `extra_env`,
      where it dies with the child. No token file is ever written
      locally: the askpass script is mode 0o700 inside the probe's own
      scratch `TemporaryDirectory()` and prints the value from its
      environment. An unreadable path or an empty-after-strip value
      refuses naming the path, before any network call — an empty
      credential would be presented to git as an empty token, a
      configuration accident this function must never launder into a
      network question.

    `target` (Decision 4) is the operator's OWN repository -- never the
    scratch probe directory above -- and is used for exactly one further
    thing when the catch-all branch below fires: `_unpushed_weight_from_cache()`
    reads it for a purely local, no-network weight measurement. `None`
    (every call this suite made before this parameter existed) takes that
    reader's `no-local-repository` unmeasurable path without a single git
    call.
    """
    if not _remote_transport_admissible(repo_url):
        raise JobFolderError(
            f"{decision} refuses: the declared remote {repo_url!r} is not a "
            "repository URL git may fetch from as-is. A remote begins with "
            f"one of {', '.join(s + '://' for s in REMOTE_URL_SCHEMES)}, or is "
            "a local path or an scp-shaped host:path; a value beginning with "
            "'-', a '<transport>::' helper address, or any other scheme would "
            "make git run a command instead of contacting a remote."
        )
    if repo_credential_path is not None:
        if repo_url.startswith("https://"):
            try:
                # The ONE read site (D6): these bytes fuel the fetch call's
                # `extra_env` below and exist nowhere else — not on argv,
                # not in a file, not in any refusal message.
                credential_value = (
                    Path(repo_credential_path).read_text(encoding="utf-8").strip()
                )
            except OSError as exc:
                raise JobFolderError(
                    f"{decision} refuses: the repository credential at "
                    f"{repo_credential_path} could not be read: {exc}"
                ) from exc
            if not credential_value:
                raise JobFolderError(
                    f"{decision} refuses: the repository credential at "
                    f"{repo_credential_path} is empty after stripping "
                    "whitespace; refusing to hand git an empty credential"
                )
        elif _looks_like_ssh_remote(repo_url):
            raise JobFolderError(
                f"{decision} refuses: a repository credential was supplied, "
                f"and the declared remote {repo_url!r} is an SSH-shaped URL. "
                "With a credential only https:// remotes are admissible: the "
                "credential is a bearer token git presents to the URL the "
                "remote names, and the runner's own clone has no SSH agent "
                "and no key, so a credential could never travel over SSH at "
                "all. Declare the remote's https:// URL, or drop "
                "--repo-credential."
            )
        else:
            raise JobFolderError(
                f"{decision} refuses: a repository credential was supplied, "
                f"and the declared remote {repo_url!r} is not an https:// "
                "URL. With a credential, only https:// remotes are "
                "admissible: the token is a bearer secret git would "
                "otherwise present to a transport that does not encrypt it. "
                "Declare the remote's https:// URL, or drop "
                "--repo-credential."
            )
    else:
        credential_value = None

    try:
        with tempfile.TemporaryDirectory(prefix="jobfolder-probe-") as scratch:
            _run_git(["init", "-q"], cwd=scratch)
            if credential_value is None:
                _run_git(
                    ["fetch", "--dry-run", "--depth", "1", repo_url, commit],
                    cwd=scratch,
                    timeout=PIN_PUBLISHED_TIMEOUT_SECONDS,
                )
            else:
                askpass = Path(scratch) / "askpass.sh"
                askpass.write_text(REPO_CREDENTIAL_ASKPASS_SCRIPT, encoding="utf-8")
                os.chmod(askpass, 0o700)
                _run_git(
                    ["fetch", "--dry-run", "--depth", "1", repo_url, commit],
                    cwd=scratch,
                    timeout=PIN_PUBLISHED_TIMEOUT_SECONDS,
                    extra_env={
                        "GIT_ASKPASS": str(askpass),
                        REPO_CREDENTIAL_ENV_NAME: credential_value,
                    },
                )
    except GitTimeoutError as exc:
        # A timeout is refused through its OWN branch, with its OWN
        # wording (Finding 4 case A): "the question could not be finished
        # asking" is a categorically different fact from "the remote
        # answered no", even though both refuse generation the same way.
        # Sharing the message below with this case once let a
        # slow-but-successful fetch get reported as a confirmed refusal —
        # a true measurement (the transfer exceeded the budget) producing
        # a false conclusion (the commit must be unpublished).
        raise JobFolderError(
            f"{decision} refuses: could not confirm whether commit "
            f"{commit!r} is reachable on the declared remote {repo_url!r} "
            f"— the probe itself timed out before finishing: {exc}. A "
            "timeout means the question could not be finished asking, "
            "which is NOT the same as the remote saying no, and is not, "
            "by itself, evidence the commit is unpublished. Retry once "
            "the connection allows the probe to finish — a large "
            "transfer on a slow link can exceed even the "
            f"{PIN_PUBLISHED_TIMEOUT_SECONDS}s budget this probe is given."
        ) from exc
    except (JobFolderError, OSError) as exc:
        remedy = (
            f" — push it to {repo_ref!r} on {repo_url!r} and pin the "
            "commit the remote actually received"
        )
        unauthenticated = (
            " (the probe is unauthenticated on purpose, because a runner "
            "clones unauthenticated too, so an SSH remote is one no runner "
            "can clone either)"
            if _looks_like_ssh_remote(repo_url)
            else ""
        )
        base = (
            f"{decision} refuses: commit {commit!r} could not be confirmed "
            f"reachable on the declared remote {repo_url!r} — a runner "
            "would attempt and fail this same fetch inside the kernel, "
            f"after quota is already spent{unauthenticated}: {exc}"
        )
        # The local weight measurement is attempted only here, in the
        # catch-all branch — never above, where `GitTimeoutError` means
        # the question could not be finished asking at all. The reader
        # never raises; `weight.measured` alone selects the shape below
        # (never a truthiness test on `weight.commits` — a measured zero
        # is a real answer, not an absence of one; Decision 3).
        weight = _unpushed_weight_from_cache(target, commit, repo_url, repo_ref)
        if weight.measured:
            plural = "" if weight.commits == 1 else "s"
            raise JobFolderError(
                base + remedy +
                f". Measured locally, no bytes moved: the pin is "
                f"{weight.commits} commit{plural} beyond the last state this "
                f"clone recorded for that remote ({weight.anchor_ref} at "
                f"{weight.anchor_commit[:12]}, from the last fetch). That count is "
                "exact about this clone's cached record and makes no claim about "
                "the remote's state now."
            ) from exc
        raise JobFolderError(
            base +
            ". How much that push would carry could not be measured here: "
            f"{_WEIGHT_UNMEASURABLE_REASONS[weight.reason]}. Nothing is "
            "prescribed from a measurement that was not taken."
        ) from exc


# The conditions a pin has to satisfy before anything irreversible
# happens, in the order they are checked. The order IS the contract, and
# it is cheapest-first: the local, instant questions come before the one
# that reaches a network. How many of each is deliberately not written
# here: that number went stale once already, when this tuple grew in the
# middle, and it is derivable from the tuple anyway. It is a module constant rather than a sequence of
# statements so that `SKILL.md`'s doctrine table can be held to it by the
# suite — prose cannot be held to code, a table can.
PIN_CONDITIONS = ("clean-worktree", "pin-is-head", "declared-paths-exist",
                  "declared-notebook-reachable", "pin-published")


def _refuse_dirty_worktree(
    *, target: Path, clone_paths: Sequence[str], decision: str, **_unused: object
) -> None:
    """The `clean-worktree` condition — the working tree must be clean over
    the declared clone paths.

    `git status --porcelain`, never `git diff`, and the two are not
    interchangeable here. `diff` enumerates changes to TRACKED content; a
    path git does not track at all is outside its domain by construction,
    not by omission. That is the whole case this condition exists to
    catch: `resolve_clone_paths()` walks the WORKING TREE, so a brand-new
    `run_search.py` that was never `git add`ed passes the import walk
    happily and is simply absent from the commit the runner clones. The
    job then dies in the kernel with `ModuleNotFoundError`, after quota is
    already spent. Measured in a scratch repository with one modified
    tracked file and one never-added file: `diff --name-only` reports only
    the modified one; `status --porcelain` reports both.

    `git rev-parse HEAD` runs first so "not a repository" and "no commits
    yet" refuse with git's own words, rather than surfacing as a wall of
    `??` lines that names a symptom instead of the cause. Cleanliness that
    cannot be proven is not cleanliness, so both refuse.

    The `-- <clone_paths…>` pathspec is the same intersection idiom
    `_staleness_for()` already uses — no second, prefix-matching
    implementation that could drift from it — and it is also what keeps
    generation possible at all: `generate_job()` writes untracked files
    under `<target>/tools/`, so an unscoped check would forbid its own
    output on the second run.

    Nothing here stages, commits, stashes or fetches. The refusal names
    the commands and stops. A commit message is a human artifact, and an
    automatic commit poisons the exact history later used to say which
    code produced which number. There is deliberately no flag that accepts
    a dirty tree: it was rejected by name, and a refusal that advertises a
    bypass is a refusal that will be bypassed.
    """
    try:
        _run_git(["rev-parse", "HEAD"], cwd=target)
    except JobFolderError as exc:
        raise JobFolderError(
            f"{decision} refuses: {target} has no commit to compare its "
            "working tree against, so it cannot be shown to hold the same "
            "bytes the runner would clone — and cleanliness that cannot be "
            f"proven is not cleanliness: {exc}"
        ) from exc

    status = _run_git(
        ["status", "--porcelain", "--", *clone_paths], cwd=target
    )
    dirty = [line for line in status.stdout.splitlines() if line.strip()]
    if not dirty:
        return
    named = "\n  ".join(dirty)
    raise JobFolderError(
        f"{decision} refuses: the working tree is not clean over the "
        f"declared clone paths {list(clone_paths)}, so the bytes validated "
        "here are not the bytes a runner would clone — an untracked module "
        "under a clone path passes the import walk and is then absent from "
        "the commit the runner checks out, and the job dies in the kernel "
        f"after quota is spent:\n  {named}\n"
        "Commit or discard them yourself — `git add <path>` then `git "
        "commit`, or `git restore <path>` — and re-run. This tool never "
        "stages, commits, pushes or stashes on your behalf."
    )


def _refuse_stale_pin(
    *,
    target: Path,
    commit: str,
    clone_paths: Sequence[str],
    decision: str,
    **_unused: object,
) -> None:
    """The `pin-is-head` condition — the pin must be HEAD, or nothing may
    have changed between them under the declared clone paths.

    The verdict comes from `_staleness_for()` and from nowhere else. That
    function has answered exactly this question since the job folder
    existed; it simply never did anything but REPORT. Two non-gating
    layers consumed it — a line in `submit`'s return payload, and
    `fromStaleSubmission` on the way back — and neither could refuse, so a
    job folder pinned to a commit whose code had already moved on was
    generated, submitted and run, with the drift printed beside the
    submission id as though it were weather. This function is the missing
    consumer, not a second computation: a second `git diff` here could
    disagree with the read-time report, and then there would be two
    answers to one question with nothing to say which was current.

    `drift` and `unknown` both refuse, and `unknown` is never rendered as
    `fresh`. A pin absent from local history cannot be shown to be HEAD or
    equivalent to it, and this module has one settled answer for questions
    it cannot ask. `_staleness_for()`'s `reason` already embeds the
    wrapped git error, so carrying it forward is what keeps git's own
    words — and the existing substring assertion on them — intact.

    The `clean-worktree` condition is what makes this one honest.
    `_staleness_for()` compares two COMMITTED trees and is blind to
    uncommitted work by construction; it would call a pin fresh while an
    untracked module sat beside it. The `clean-worktree` and
    `pin-is-head` conditions are therefore separate and ordered, not one
    refined into the other.
    """
    staleness = _staleness_for(target, commit, clone_paths)
    status = staleness["status"]
    if status == "fresh":
        return

    if status == "unknown":
        raise JobFolderError(
            f"{decision} refuses: the staleness of pin {commit!r} against "
            f"{target}'s HEAD is unknown, and an unanswerable question is "
            "never reported as a clean answer — a pin that cannot be shown "
            "to be the code being validated is not a pin worth spending "
            f"quota on: {staleness['reason']}"
        )

    try:
        head = _run_git(["rev-parse", "HEAD"], cwd=target).stdout.strip()
    except JobFolderError:  # pragma: no cover - clean-worktree refuses first
        head = "HEAD"
    changed = "\n  ".join(staleness["changedPaths"])
    raise JobFolderError(
        f"{decision} refuses: pin {commit!r} is not the code in "
        f"{target} — HEAD is {head!r} and these declared clone paths "
        f"differ between the two:\n  {changed}\n"
        f"A runner would clone {commit!r}, so the numbers it returns would "
        "belong to code you have already moved on from. Pin HEAD instead, "
        "or check out the pin. This tool never commits, pushes or resets on "
        "your behalf."
    )


def _refuse_absent_clone_paths(
    *, target: Path, commit: str, clone_paths: Sequence[str], decision: str,
    **_unused: object,
) -> None:
    """The `declared-paths-exist` condition — every declared clone path
    must exist at the pin.

    `git sparse-checkout set` accepts a path the tree does not contain and
    checks out nothing for it, silently. So a job could declare the data file
    its run depends on, generate cleanly, push, spend the quota, and have the
    kernel refuse for the absence of a file the operator believed they had
    declared their way to — the failure this whole family of conditions exists
    to move from the kernel to here.

    Generation's existing cross-check answers a different question. It asks
    whether every import the entry modules make is covered by a declared path;
    it never asks whether a declared path is anything at all. A data path — a
    record a run reads rather than a module it imports — lives entirely in the
    second question's domain.

    Asked of the PIN and never of the working tree, because the pin is what the
    runner fetches. A file the operator can see and the pin cannot is precisely
    the case a working-tree check would wave through.

    Local, so it sits ahead of the network condition: there is no reason to ask
    a remote about a pin whose own contents already refuse.
    """
    missing = []
    for path in clone_paths:
        try:
            _run_git(["cat-file", "-e", f"{commit}:{path}"], cwd=target)
        except JobFolderError:
            missing.append(path)
    if missing:
        raise JobFolderError(
            f"{decision} refuses: these declared clone paths do not exist at "
            f"{commit!r}, so a runner's sparse checkout would fetch nothing for "
            f"them and the run would fail inside the kernel after quota is "
            f"already spent: {missing}. Commit them and pin the commit that "
            "carries them, or stop declaring them."
        )


def _refuse_unreachable_notebook(
    *, target: Path, commit: str, clone_paths: Sequence[str],
    notebooks: Sequence[str] = (), decision: str, **_unused: object,
) -> None:
    """The `declared-notebook-reachable` condition — every declared
    notebook must actually ARRIVE in the runner's checkout, which is two
    facts and not one.

    1. **Covered by a declared clone path.** `git sparse-checkout set`
       delivers what the declared paths cover and nothing else. A notebook
       sitting outside every declared path is simply absent from the
       checkout, and `run.notebook` naming it does not make it arrive —
       `clonePaths` is the only thing that does. This half cannot be
       inferred from the import cross-check either: that check asks
       whether every computed path is declared, and a notebook is never
       computed at all (nothing imports it), so a notebook has no
       representative in `computedNotDeclared` for any declaration to be
       missing from.
    2. **Present at the pin.** The same question
       `_refuse_absent_clone_paths` asks of a clone path, asked of the
       file rather than of the directory that carries it: a declared
       clone path can exist at the pin while the notebook inside it does
       not, and `sparse-checkout` reports nothing for either case.

    Both asked of the PIN and never of the working tree, for the reason
    the `declared-paths-exist` condition already gives: the pin is what
    the runner fetches, and a
    notebook the operator can see and the pin cannot is precisely the case
    a working-tree check waves through.

    Local, and therefore ahead of the network condition. A job with no
    declared notebook — every job the callable shape produces — passes
    through untouched.
    """
    uncovered = [nb for nb in notebooks if not _covered_by_declared(nb, clone_paths)]
    if uncovered:
        raise JobFolderError(
            f"{decision} refuses: these declared notebooks are not covered by "
            f"any declared clone path, so the runner's sparse checkout would "
            f"never receive them and the run would fail inside the kernel "
            f"after quota is already spent: {uncovered}. Declare a "
            f"--clone-path that contains them."
        )
    missing = []
    for notebook in notebooks:
        try:
            _run_git(["cat-file", "-e", f"{commit}:{notebook}"], cwd=target)
        except JobFolderError:
            missing.append(notebook)
    if missing:
        raise JobFolderError(
            f"{decision} refuses: these declared notebooks do not exist at "
            f"{commit!r}, so the runner would clone a checkout without them "
            f"and the run would fail inside the kernel after quota is "
            f"already spent: {missing}. Commit them and pin the commit that "
            "carries them, or stop declaring them."
        )


def _refuse_unpublished_pin(
    *,
    commit: str,
    repo_url: str,
    repo_ref: str,
    decision: str,
    repo_credential_path: str | Path | None = None,
    target: Path | None = None,
    **_unused: object,
) -> None:
    """The `pin-published` condition — the declared remote must be able
    to serve the pin.

    A thin adapter onto `_verify_commit_reachable()`, which owns the whole
    of this question and documents it at length. It exists so that every
    condition reaches `verify_pin_preconditions()` through one uniform
    keyword-only shape, and so that `PIN_CONDITIONS` maps to callables
    rather than to a chain of `if` statements a later condition could be
    inserted into out of order.

    `repo_credential_path` (S3) and `target` (Decision 4) are threaded
    explicitly here rather than absorbed by `**_unused`: this is the one
    condition either input applies to, and a parameter that rides the
    catch-all would make it silently droppable by a future signature edit
    that looks harmless.
    """
    _verify_commit_reachable(
        commit,
        repo_url,
        repo_ref,
        decision=decision,
        repo_credential_path=repo_credential_path,
        target=target,
    )


_PIN_CONDITION_CHECKS = {
    "clean-worktree": _refuse_dirty_worktree,
    "pin-is-head": _refuse_stale_pin,
    "declared-paths-exist": _refuse_absent_clone_paths,
    "declared-notebook-reachable": _refuse_unreachable_notebook,
    "pin-published": _refuse_unpublished_pin,
}


def pin_source(target: Path | str, explicit: str | None, recorded: str) -> str:
    """Which of the three ways the pin arrived, named for an operator.

    Lives here rather than in the CLI because answering it needs to know what
    HEAD is, and this module is the one place that asks git that — the same
    reason `_resolve_pin` is shared. A second `rev-parse` in the front door
    would be a second definition of HEAD, and a test forbids exactly that.

    `explicit` when the caller typed it. Otherwise the default resolved either
    to HEAD or, when HEAD was unpublished and the declared ref's published tip
    carried the same clone-path content, to that tip — different facts about
    which code will run, so different words.

    Silent when HEAD cannot be read: this is operator feedback, and a feedback
    string is never worth failing a generation that already succeeded.
    """
    if explicit:
        return "explicit"
    try:
        head = _run_git(["rev-parse", "HEAD"], cwd=Path(target)).stdout.strip()
    except JobFolderError:
        return "default"
    if not head:
        return "default"
    return "default-head" if head == recorded else "default-published-tip"


def _resolve_pin(target: Path, commit: str | None, *,
                 repo_url: str | None = None, repo_ref: str | None = None,
                 clone_paths: Sequence[str] | None = None) -> str:
    """The pin, defaulted to the target's HEAD when the caller gave none.

    One implementation, shared by the Python API and the CLI, so the two
    cannot disagree about what HEAD means. It is deliberately LOCAL — `git
    rev-parse HEAD` in the resolved target — and reaches no remote, ever.
    Measured against the live remote this skill targets before this was
    written: the remote's tip was OLDER than the entrypoint the operator
    needed, which existed only in an unpushed commit. A helpful
    remote-derived default would have pinned code older than the caller's,
    passed every local check (generation validates against the working
    tree), and died in the kernel after quota was spent — the exact
    failure class this change exists to remove, reintroduced by
    convenience.

    This default is safe only because the `clean-worktree` and
    `pin-is-head` conditions exist. HEAD is the code that was validated
    precisely when the working tree is
    clean over the clone paths and the pin is that commit. It must
    therefore never be reachable around `verify_pin_preconditions()`: the
    resolution happens before them, and every condition then runs against
    the resolved value exactly as it would against an explicit one.

    A target with no HEAD refuses here, with git's own words, rather than
    defaulting to something. There is no commit to default to.
    """
    if commit is not None:
        return commit
    try:
        head = _run_git(["rev-parse", "HEAD"], cwd=target).stdout.strip()
    except JobFolderError as exc:
        raise JobFolderError(
            f"--commit was omitted and {target} has no HEAD to default to: "
            f"{exc}"
        ) from exc
    published = _published_equivalent(target, head, repo_url, repo_ref, clone_paths)
    return published or head


def _published_equivalent(
    target: Path, head: str, repo_url: str | None, repo_ref: str | None,
    clone_paths: Sequence[str] | None,
) -> str | None:
    """The declared ref's published tip, when it delivers the same clone-path
    content as `head` — otherwise `None`, and `head` stands.

    This is not the remote-derived default the caller above refuses. That one
    pins whatever is newest on the remote and can be OLDER than the caller's
    code; this one pins a published commit only after proving, by diff, that a
    runner cloning it receives byte-identical code. When the diff is not empty
    it returns nothing and the ordinary refusal follows, unchanged.

    Written because the guard refused its own author. Generating a job folder
    writes under `tools/`; committing that moves HEAD past the remote; the next
    generation defaults to the unpublished HEAD and the `pin-published`
    condition refuses — over a commit whose entire content is the job
    folder being regenerated, and which
    the runner never clones. Measured on a live target: the blocking commit
    touched nothing but its own job folder, and its diff against the published
    commit over every declared clone path was empty.

    `ls-remote` asks for one ref by name and transfers no objects, so the cost is
    a round trip and nothing else. It is also the first reader `repo.ref` has
    ever had: the field was written into every `run-config.json` and consulted by
    nothing.

    Silent on every uncertainty. No remote declared, no ref, no clone paths, an
    unreachable network, a tip that is not an ancestor of `head` — each returns
    `None` and leaves `head` to face the conditions exactly as before. A default
    that cannot prove itself does not get to lower a guard.
    """
    if not (repo_url and repo_ref and clone_paths):
        return None
    if not _remote_transport_admissible(repo_url):
        return None
    try:
        listed = _run_git(["ls-remote", "--", repo_url, repo_ref], cwd=target).stdout
    except JobFolderError:
        return None
    tip = listed.split("\t", 1)[0].strip() if listed.strip() else ""
    if len(tip) != 40 or tip == head:
        return None
    try:
        # An ancestor, never merely a commit that happens to differ: pinning a
        # tip `head` does not descend from would silently ship a different
        # lineage rather than the same code at an earlier point on this one.
        _run_git(["merge-base", "--is-ancestor", tip, head], cwd=target)
        changed = _run_git(
            ["diff", "--name-only", tip, head, "--", *clone_paths], cwd=target
        ).stdout.strip()
    except JobFolderError:
        return None
    return None if changed else tip


def verify_pin_preconditions(
    *,
    target: str | Path,
    commit: str,
    clone_paths: Sequence[str],
    repo_url: str,
    repo_ref: str,
    decision: str,
    notebooks: Sequence[str] = (),
    repo_credential_path: str | Path | None = None,
) -> None:
    """The one home for every condition a pin must satisfy before anything
    irreversible happens, and the ONLY thing either decision point calls.

    `notebooks` defaults to empty, and that default is the whole of the
    callable shape's behavior: a job that declares no notebook meets
    exactly the conditions it met before this parameter existed. It is
    NOT a silent skip for a job that does declare one — both decision
    points derive it from the same `declared_notebooks()`, one off the
    caller's arguments and one off the job folder's own written config,
    so neither can reach `_refuse_unreachable_notebook` with an empty
    list for a job that has a notebook to check.

    A decision point is any command that writes a job folder or spends
    remote quota: `generate-job` and `submit`. Both call exactly this
    function, with exactly one word different between them — `decision`,
    which is the word that appears in the refusal. That is the whole
    reason this is a function rather than three calls at each site: six
    call sites can drift in order, or omit one condition on one side, and
    nothing in the code would say so. Here the order is a module constant
    and the omission is impossible.

    Conditions run in `PIN_CONDITIONS` order, cheapest first, and the
    first failure raises `JobFolderError`. Every refusal carries git's own
    message forward rather than replacing it with a second, coarser one —
    git's text names the distinct underlying cause, and an existing test
    asserts on a substring of it reaching the caller.

    `clone_paths` goes through the SAME `validate_clone_paths()` every
    other caller uses, with `target` supplied, before any of them is
    handed to git as a pathspec. That is not defensive duplication: it is
    what keeps the structural refusal for an absolute or `..`-bearing
    clone path identical whether it is reached here or from
    `resolve_clone_paths()` later.

    This function never writes, stages, commits, pushes, stashes or
    fetches into `target`. It asks questions and refuses.

    `repo_credential_path` (S3) exists for symmetry with the one
    condition that reads it — `pin-published` — which is also the only
    condition that ever reaches a network. It is threaded through the
    SAME uniform keyword shape every condition already receives (each
    ignores it unless it is `_refuse_unpublished_pin`), so the credential
    travels on the same path as every other input and there is exactly
    one place (`_verify_commit_reachable`) that interprets it.
    """
    validate_commit_shape(commit, source=f"{decision}")
    resolved_target = resolve_target(target)
    validated_clone_paths = validate_clone_paths(clone_paths, resolved_target)
    validated_notebooks = tuple(
        validate_notebook_path(notebook, where=decision) for notebook in notebooks
    )
    for condition in PIN_CONDITIONS:
        _PIN_CONDITION_CHECKS[condition](
            target=resolved_target,
            commit=commit,
            clone_paths=validated_clone_paths,
            notebooks=validated_notebooks,
            repo_url=repo_url,
            repo_ref=repo_ref,
            decision=decision,
            repo_credential_path=repo_credential_path,
        )


def _staleness_for(target: Path, pinned_commit: str, clone_paths: Sequence[str]) -> dict:
    """The one staleness condition (design #744 §4), always computed, never
    skippable:

        head    = git rev-parse HEAD
        exists  = git cat-file -e <pinned>^{commit}
        changed = git diff --name-only <pinned> HEAD -- <clonePaths…>

    The pathspec (`-- <clonePaths…>`) does the intersection with the
    declared clone paths — deliberately: there is no second,
    prefix-matching implementation of that intersection anywhere in this
    module that could drift from this one.

    Verdict is `drift` iff `changed` is non-empty. Never a refusal: this
    function always returns a verdict, it never raises for a stale or
    unknown result.

    The SAME verdict refuses at a decision point and only reports at
    `read()`, and that asymmetry is deliberate rather than an accident of
    where the code sits. `_refuse_stale_pin()` — the `pin-is-head`
    condition in `PIN_CONDITIONS` — calls exactly this function and
    raises on `drift` and `unknown`, so `generate-job` and `submit` both
    refuse. `read()`
    calls it and attaches the verdict. Reading is an observation: refusing
    there would make a drifted job folder unreadable, which is the one
    state in which reading it is most useful, and every reporting command
    (`status`, `fetch`, `reconcile`) would lose the ability to say what is
    wrong. Refusing belongs where something irreversible is about to
    happen; reporting belongs where someone is looking.

    For a long time only the reporting half existed. Two non-gating layers
    consumed the verdict — a line in `submit`'s return payload, and
    `fromStaleSubmission` on the way back — and neither could refuse, so a
    job folder pinned to code that had already moved on was generated,
    submitted and run with the drift printed beside the submission id as
    though it were weather. The `pin-is-head` condition is the missing
    consumer. There is still exactly one computation, which is what
    keeps the guard and the report from ever disagreeing.

    This function compares two COMMITTED trees and is blind to
    uncommitted work by construction — which is why the `clean-worktree`
    condition is a separate condition ordered before it, and not a
    refinement of this one.

    `unknown`, with a reason, whenever the question cannot be answered at
    all: no git history, not a repository, or an absent pinned commit —
    reusing `implementation_cli.py`'s own `prior_work_state()` discipline
    of never letting an unanswerable record pass for a clean one.
    `unknown` is never rendered as `fresh`: the two are separate branches
    below, neither one falls back to the other.
    """
    try:
        _run_git(["rev-parse", "HEAD"], cwd=target)
    except JobFolderError as exc:
        return {
            "status": "unknown",
            "reason": f"{target} has no git history to check staleness against: {exc}",
            "changedPaths": [],
        }

    try:
        _run_git(["cat-file", "-e", f"{pinned_commit}^{{commit}}"], cwd=target)
    except JobFolderError as exc:
        return {
            "status": "unknown",
            "reason": (
                f"pinned commit {pinned_commit!r} was not found in {target}'s "
                f"history: {exc}"
            ),
            "changedPaths": [],
        }

    diff = _run_git(
        ["diff", "--name-only", pinned_commit, "HEAD", "--", *clone_paths], cwd=target
    )
    changed = [line for line in diff.stdout.splitlines() if line]
    return {
        "status": "drift" if changed else "fresh",
        "reason": None,
        "changedPaths": changed,
    }


def smoke_warnings(run_config: dict) -> list[str]:
    """What a generated smoke block leaves unproven, reported by `generate-job`.

    `smoke record` passes iff the returned stamp carries every path in
    `run.smoke.requiredEvidence`; with none declared, any `shard.json` at all
    passes, so a rehearsal proves nothing about the commit or the device.
    """
    smoke = (run_config.get("run") or {}).get("smoke")
    if not smoke or smoke.get("requiredEvidence"):
        return []
    return ["the smoke block declares no --smoke-required-evidence, so `smoke record` "
            "passes on any shard.json; declare the stamp paths that prove the run "
            "(its commit, the device it ran on), and make the smoke write shard.json "
            "into its working directory"]


def read(job_dir: str | Path) -> JobFolder:
    """The ONLY reader. Every command that touches an already-generated
    job folder (`generate-job`'s own CLI output, `submit`, `status`,
    `fetch`, `reconcile`) routes through this one function rather than
    parsing `run-config.json` and computing staleness each its own way.

    `clonePaths` is validated again here, through the SAME
    `validate_clone_paths()` `generate_job()` already calls at generation
    time — never a second, parallel validator (design #744 §§2-4:
    "validated at generation and again on every read").

    The target a staleness check runs `git` against is derived
    structurally from `job_dir` itself (`<target>/tools/<service>/
    <job-name>/`, exactly as `resolve_destination()` builds it) rather
    than accepted as a second argument — there is exactly one path this
    reader could mean by "the repository this job belongs to".
    """
    resolved = Path(job_dir).resolve()
    if not resolved.is_dir():
        raise JobFolderError(f"{resolved} is not an existing directory")

    config_path = resolved / RUN_CONFIG_FILENAME
    if not config_path.is_file():
        raise JobFolderError(
            f"{config_path} does not exist; {resolved} is not a generated job folder"
        )
    try:
        run_config = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise JobFolderError(f"{config_path} is not valid JSON: {exc}") from exc
    validate_run_config(run_config)

    try:
        tools_dir = resolved.parents[1]
        target = resolved.parents[2]
    except IndexError:
        raise JobFolderError(
            f"{resolved} is not nested deep enough under a target to derive "
            "one"
        ) from None
    if tools_dir.name != TOOLS_DIRNAME:
        raise JobFolderError(
            f"{resolved} does not sit under <target>/{TOOLS_DIRNAME}/"
            "<service>/<job-name>/; a target cannot be derived from it"
        )

    clone_paths = validate_clone_paths(run_config["clonePaths"], target)
    staleness = _staleness_for(target, run_config["commit"], clone_paths)

    return JobFolder(
        path=resolved,
        run_config=MappingProxyType(dict(run_config)),
        staleness=MappingProxyType(staleness),
    )
