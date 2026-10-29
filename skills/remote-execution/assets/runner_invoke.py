#!/usr/bin/env python3
"""Cell 1 of the generated runner notebook — copied byte for byte.

Runs whichever of the two shapes the selected block declares.

- A CALLABLE block (`module` / `function` / `kwargs`) resolves through
  `importlib` and is called.
- A NOTEBOOK block (`notebook`) is read out of the clone, executed in a
  kernel with the clone's `src` on its `PYTHONPATH`, and written back
  executed into the runner's own working directory, which is what makes
  its outputs part of what a fetch returns.

Both stay reachable, deliberately. The notebook shape exists so that what
a worker runs can be the notebook a pilot validated, rather than a second
implementation of it whose agreement nothing checks. The callable shape
stays because a worker asked to settle one question is legitimately a
function call, and some entries cannot be named by a `module`/`function`
contract at all. `block_kind()` decides between them and refuses a block
that declares neither or both — never a default, because on this side of
the wire every default costs the same quota as the right answer.

The `smoke` variant is selected the same way for both shapes, when
`run_config["mode"] == "smoke"`. Cell 0
(`runner_bootstrap.py`) has already sparse-cloned the pinned commit and
put its `src/` on `sys.path` before this cell ever runs — `SystemExit`
there means this cell never runs at all — so the module named here
resolves from that same clone, never from anywhere this cell reaches on
its own initiative.

Importable and independently testable the same way `runner_bootstrap.py`
is: nothing runs at import time, and the orchestrating call sits behind
`if __name__ == "__main__":`, letting the forge suite drive
`select_block()`, `resolve_callable()` and `invoke()` directly against
fake `run-config.json` payloads.

No service name occurs anywhere in this file, and none may be added
later either.

Run with any Python 3.10+ (stdlib-only):
    python3 -m unittest tests.test_remote_execution
"""
from __future__ import annotations

import importlib
import json
import os
import shutil
import time
from pathlib import Path
from typing import Any, Callable, Mapping


class InvokeError(Exception):
    """A refusal: the selected `run`/`smoke` block, its declared module,
    or its declared function could not be resolved.
    """


CONFIG_FILENAME = "run-config.json"

# `runner_bootstrap.py` clones into `<base>/clone`, and this cell has to
# find the same directory to reach a declared notebook inside it. The two
# assets have no import between them — they are two cells of one notebook,
# each copied byte for byte — so this constant MIRRORS that one rather
# than importing it, exactly the way each file already holds its own
# subprocess-environment allowlist. A forge test binds the two spellings
# together; a divergence is a defect the suite catches, never a runtime
# surprise.
CLONE_DIRNAME = "clone"

# What an executed notebook is written back as, beside `run-config.json`
# and `bootstrap.json` in the runner's own working directory. A prefix and
# not an in-place overwrite: the clone is the pinned input and stays the
# pinned input, and the fetched artifact then carries both the notebook
# that was sent and the outputs it produced.
EXECUTED_NOTEBOOK_PREFIX = "executed-"

DEFAULT_KERNEL_NAME = "python3"

SRC_DIRNAME = "src"

# The handoff this cell owes the kernel it starts, beside the `PYTHONPATH`
# it already sets. Two names, forge-owned and deliberately generic — they
# are the contract between a runner and the notebook it starts, never a
# name borrowed from one repository — and mirrored, byte for byte, by
# `assets/notebook_repo_root.py`, the cell on the reading side. A forge
# test binds the two spellings together the way one already binds
# `CLONE_DIRNAME` to cell 0's.
#
# Why both, and never just the root: a directory handed over is still a
# directory nobody proved. The commit travels beside it so the reading
# cell can check the checkout it was pointed at rather than trust it, and
# a job that runs the wrong commit RUNS — it returns numbers shaped
# exactly like the right ones.
CLONE_ROOT_ENV = "FORGE_CLONE_ROOT"
CLONE_COMMIT_ENV = "FORGE_CLONE_COMMIT"

# Two more forge-owned names, composed for the same reason and by the same
# kind of function as the two above, but carrying a different kind of fact.
# `run_config["mode"]` and `run_config["units"]` are written by the packer
# and by `remote_cli.py`'s `--smoke` flag PER WORKER SLICE
# (`remote_cli.py:1260-1261`): one job can fan out into several
# submissions, and each submission gets its own units and its own mode.
# A CALLABLE block's `kwargs`, by contrast, is written once, at job
# generation, and is therefore IDENTICAL for every worker that shares the
# job. Neither shape has anywhere else for a per-submission fact to travel
# — a notebook's kernel is a separate process that inherits only what this
# file's environment composition hands it, and a callable's kwargs are
# fixed before any worker exists — so the environment is the one channel
# either shape has for "which units am I" or "am I the smoke variant".
#
# `units` is JSON-encoded rather than joined on a delimiter: a delimiter
# invites exactly the ambiguity this handoff cannot afford (a unit name
# that happens to contain it, or what an empty run between two delimiters
# is supposed to mean), while JSON already round-trips a list of strings
# without this file inventing its own escaping rule. The absent-vs-empty
# distinction is carried by WHETHER THE KEY EXISTS, never by its value: a
# `run_config` that never mentions `units` leaves `FORGE_RUN_UNITS` unset
# entirely, so `os.environ.get(UNITS_ENV)` reads `None` for "no units were
# declared", while a `run_config` that declares an empty list still sets
# the variable, to the JSON text `"[]"` — present, parseable, and meaning
# "units were declared, and there are zero of them". Collapsing those two
# into the same unset-key reading would make a legitimately empty campaign
# indistinguishable from a config that never mentioned units at all.
MODE_ENV = "FORGE_RUN_MODE"
UNITS_ENV = "FORGE_RUN_UNITS"

# The session deadline handed to the target, in epoch seconds: the moment
# by which it must have stopped starting new units or trials, written a
# checkpoint, and exited cleanly. `submit` copies the backend's declared
# continuous session limit into `run_config["sessionLimitSeconds"]`
# (`Adapter.session_limit_seconds()`); this cell turns it into
#
#     deadline = session start + limit - max(10% of limit, 30 min)
#
# where "session start" is the moment this cell composes the environment.
# The margin covers what ran before it (cell 0's clone and install), the
# checkpoint write itself, and the upload of the outputs. A run_config with
# no `sessionLimitSeconds` exports no deadline at all, exactly as before
# this name existed -- an unknown limit is never turned into a number.
SESSION_DEADLINE_ENV = "FORGE_SESSION_DEADLINE"
SESSION_LIMIT_KEY = "sessionLimitSeconds"
SESSION_MARGIN_FRACTION = 0.10
SESSION_MARGIN_MIN_SECONDS = 1800

# The carry-over of a continuation (kernel-carry S3). `generate-job
# --carry-path` declares, in `run_config["carryPaths"]`, the paths relative
# to the product folder whose contents a continuation needs; `submit` adds
# `run_config["carry"]`, one `{"submissionId", "ref", "mount"}` row per
# earlier submission whose output the backend mounted for this job. Before
# the entrypoint runs, `restore_carry()` copies each declared path from each
# mount into this cell's working directory -- the folder whose files come
# back as the result -- so the target finds its checkpoints where it wrote
# them and needs no code of its own to resume. `FORGE_CARRY_IN` names the
# mounts that were present (joined with `os.pathsep`), for a target that
# wants to read the earlier output directly. A missing mount or path is
# written to the run log and the unit starts fresh; it is never fatal.
CARRY_IN_ENV = "FORGE_CARRY_IN"
CARRY_PATHS_KEY = "carryPaths"
CARRY_KEY = "carry"
CARRY_LOG_PREFIX = "[carry]"


def _carry_relative(raw: Any) -> Path | None:
    """A declared carry path as a safe relative `Path`, or `None` when it
    is not one (absolute, `..`, empty, not a string)."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    candidate = Path(raw)
    if candidate.is_absolute() or ".." in candidate.parts or not candidate.parts:
        return None
    return candidate


def restore_carry(run_config: Mapping[str, Any], base_dir: str | Path | None = None) -> str | None:
    """Copy each declared carry path from each mounted earlier output into
    the working directory, and return the `FORGE_CARRY_IN` value (`None`
    when nothing was mounted, or when this job carries nothing).

    Never raises for a missing mount, a missing path or a malformed row:
    each is printed as one `[carry]` line to the run log and skipped, so
    the unit starts fresh from whatever is not there. A run_config with no
    `carry` rows prints nothing and copies nothing -- the job runs exactly
    as it did before this existed.
    """
    rows = run_config.get(CARRY_KEY) or []
    if not isinstance(rows, list) or not rows:
        return None
    declared = run_config.get(CARRY_PATHS_KEY) or []
    if not isinstance(declared, list):
        declared = []
    base = Path(base_dir) if base_dir is not None else Path.cwd()
    present: list[str] = []
    for row in rows:
        mount_text = row.get("mount") if isinstance(row, Mapping) else None
        ref = row.get("ref") if isinstance(row, Mapping) else None
        if not isinstance(mount_text, str) or not mount_text:
            print(f"{CARRY_LOG_PREFIX} skipped a carry row with no mount: {row!r}", flush=True)
            continue
        mount = Path(mount_text)
        if not mount.is_dir():
            print(f"{CARRY_LOG_PREFIX} mount {mount} of {ref!r} is absent; "
                  "the unit starts fresh", flush=True)
            continue
        present.append(str(mount))
        for raw in declared:
            relative = _carry_relative(raw)
            if relative is None:
                print(f"{CARRY_LOG_PREFIX} skipped carry path {raw!r}: not a "
                      "relative path inside the product folder", flush=True)
                continue
            source = mount / relative
            destination = base / relative
            if source.is_dir():
                shutil.copytree(source, destination, dirs_exist_ok=True)
            elif source.is_file():
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
            else:
                print(f"{CARRY_LOG_PREFIX} {raw} is missing from {mount}; it starts "
                      "fresh", flush=True)
                continue
            print(f"{CARRY_LOG_PREFIX} restored {raw} from {ref!r}", flush=True)
    return os.pathsep.join(present) if present else None

# The public datasets a job reads (kernel-input-datasets S3). `generate-job
# --input-dataset` declares them in `run_config["inputDatasets"]` as
# `<owner>/<slug>`; `submit` adds `run_config["inputRoot"]` only for a
# backend that attaches them to the push. Before the entrypoint runs,
# `discover_input_datasets()` searches that root for each ref's slug -- the
# sub-path below the root is the service's, never hard-coded here -- and
# `FORGE_INPUT_DATASETS` carries a JSON object mapping every declared ref to
# the directory found, or to null when the backend attached nothing or no
# directory was found, so the target downloads that dataset itself. A job
# declaring no inputs exports nothing and prints nothing.
INPUT_DATASETS_ENV = "FORGE_INPUT_DATASETS"

# `FORGE_DATASET_CHECKS` carries `run_config["datasetChecks"]` as JSON when
# the job declares one (remote-preflight S2: `generate-job --dataset`): per
# input ref, the workspace preparation's sha256 values, so the target can
# verify the data it reads is the data the preparation was made from.
DATASET_CHECKS_ENV = "FORGE_DATASET_CHECKS"
INPUT_DATASETS_KEY = "inputDatasets"
INPUT_ROOT_KEY = "inputRoot"
INPUT_LOG_PREFIX = "[inputs]"
# How many directory levels below the root the search descends, and how
# many directories it opens at most: enough for `<root>/<slug>`,
# `<root>/<owner>/<slug>` and `<root>/<kind>/<owner>/<slug>`, without
# walking the contents of a large dataset.
INPUT_SEARCH_DEPTH = 4
INPUT_SEARCH_MAX_DIRS = 20000


def _input_ref_parts(raw: Any) -> tuple[str, str] | None:
    """`(owner, slug)` for a well-formed `<owner>/<slug>` ref, else `None`."""
    if not isinstance(raw, str):
        return None
    owner, sep, slug = raw.partition("/")
    if not sep or not owner or not slug or "/" in slug:
        return None
    for part in (owner, slug):
        if part.startswith(".") or not all(ch.isalnum() or ch in "-_" for ch in part):
            return None
    return owner, slug


def _find_input_mount(root: Path, owner: str, slug: str) -> Path | None:
    """The directory named `slug` under `root`, at most
    `INPUT_SEARCH_DEPTH` levels down: one whose parent is named `owner`
    first, then the shallowest, then the first in sorted order. `None`
    when there is none. Never descends into a match."""
    candidates: list[tuple[int, int, str]] = []
    frontier = [root]
    opened = 0
    for depth in range(1, INPUT_SEARCH_DEPTH + 1):
        following: list[Path] = []
        for directory in frontier:
            if opened >= INPUT_SEARCH_MAX_DIRS:
                break
            opened += 1
            try:
                children = sorted(child for child in directory.iterdir() if child.is_dir())
            except OSError:
                continue
            for child in children:
                if child.name == slug:
                    owned = 0 if child.parent.name == owner else 1
                    candidates.append((owned, depth, str(child)))
                else:
                    following.append(child)
        frontier = following
        if not frontier:
            break
    if not candidates:
        return None
    return Path(min(candidates)[2])


def discover_input_datasets(run_config: Mapping[str, Any]) -> str | None:
    """The `FORGE_INPUT_DATASETS` value for this job, or `None` when it
    declares no input datasets (nothing is exported, nothing printed).

    Never raises: a malformed ref is logged and left out, an absent root
    or an unfound slug maps the ref to null and is logged, so the target
    falls back to downloading."""
    refs = run_config.get(INPUT_DATASETS_KEY)
    if not isinstance(refs, list) or not refs:
        return None
    root_text = run_config.get(INPUT_ROOT_KEY)
    root = Path(root_text) if isinstance(root_text, str) and root_text else None
    found: dict[str, str | None] = {}
    for raw in refs:
        parts = _input_ref_parts(raw)
        if parts is None:
            print(f"{INPUT_LOG_PREFIX} skipped input dataset {raw!r}: not "
                  "<owner>/<slug>", flush=True)
            continue
        mount = _find_input_mount(root, *parts) if root is not None and root.is_dir() else None
        if mount is not None:
            found[raw] = str(mount)
            print(f"{INPUT_LOG_PREFIX} {raw} is mounted at {mount}", flush=True)
        else:
            found[raw] = None
            reason = ("the service attached no inputs" if root is None
                      else f"no directory named {parts[1]!r} under {root}")
            print(f"{INPUT_LOG_PREFIX} {raw} not attached ({reason}); the "
                  "target downloads it", flush=True)
    return json.dumps(found, sort_keys=True)


def session_deadline(limit_seconds: Any, *, started: float) -> int:
    """`started + limit - max(limit * SESSION_MARGIN_FRACTION,
    SESSION_MARGIN_MIN_SECONDS)`, as whole epoch seconds.

    A limit that is not a positive integer is refused, not ignored: it is
    written by `submit` from a backend's declared constant, so anything
    else is a defect, and a deadline silently dropped is hours of compute
    a session limit can still take away.
    """
    if isinstance(limit_seconds, bool) or not isinstance(limit_seconds, int) or limit_seconds <= 0:
        raise InvokeError(
            f"run-config.json's {SESSION_LIMIT_KEY!r} must be a positive integer "
            f"number of seconds, got {limit_seconds!r}"
        )
    margin = max(limit_seconds * SESSION_MARGIN_FRACTION, SESSION_MARGIN_MIN_SECONDS)
    return int(started + limit_seconds - margin)


def kernel_python_path(clone_root: str | Path, existing: str | None) -> str:
    """`PYTHONPATH` for the kernel a notebook executes in — the clone's own
    `src`, ahead of whatever was already there.

    Cell 0's `sys.path.insert(0, <clone>/src)` puts the pinned code on the
    path of the RUNNER process, and a notebook executes in a SEPARATE
    kernel process that inherits none of it. Without this, a notebook
    whose first cell imports the target's own package dies with
    `ModuleNotFoundError` on a worker whose clone is sitting right there
    — the pinned code delivered, and unreachable.

    Prepended rather than replacing: an existing `PYTHONPATH` belongs to
    the worker's own image and this has no business discarding it. The
    clone goes first for the same reason cell 0 inserts at position 0 —
    a copy of the same package installed elsewhere must never win against
    the commit this job pinned.
    """
    clone_src = str((Path(clone_root) / SRC_DIRNAME).resolve())
    if existing:
        return clone_src + os.pathsep + existing
    return clone_src


def submission_environment(
    mode: Any = None,
    units: list[str] | None = None,
    session_deadline: int | None = None,
    carry_in: str | None = None,
    input_datasets: str | None = None,
    dataset_checks: str | None = None,
) -> dict:
    """Compose `FORGE_RUN_MODE` and `FORGE_RUN_UNITS` — the two
    per-submission facts described beside `MODE_ENV`/`UNITS_ENV` above —
    on their own, apart from `kernel_environment()`.

    Kept separate rather than folded silently into `kernel_environment()`
    because the CALLABLE branch of `invoke()` has no clone and no
    `PYTHONPATH` to compose: it runs in the runner's own process, on the
    `sys.path` `runner_bootstrap.py` already prepared, never in a kernel
    subprocess. Forcing a `clone_root`/`commit` pair onto a caller that has
    neither would trade one kind of accidental default for another.
    `kernel_environment()` still ends up composing both of these names for
    the notebook branch — it calls this function and merges the result in
    — so this remains the one function that decides what either name is
    worth; a divergence between what a kernel sees and what a callable
    sees could never come from two encodings disagreeing with each other.

    Absent `mode` (`None`): no `FORGE_RUN_MODE` key at all, never an empty
    string standing in for it — a reader doing `os.environ.get(MODE_ENV)`
    must see `None` for "no mode declared", not a present-but-empty value
    a careless truthiness check could confuse with "declared and false".
    Absent `units` (`None`, meaning `run_config` never mentioned the key):
    no `FORGE_RUN_UNITS` key either. A DECLARED empty list still sets it,
    to the JSON text `"[]"`, because only a present key can tell a reader
    that zero units is what was decided, rather than what is missing.

    Absent `session_deadline` (`None`, no declared session limit): no
    `FORGE_SESSION_DEADLINE` key either; present, it is the epoch-seconds
    integer `session_deadline()` computed.
    """
    result: dict[str, str] = {}
    if mode is not None:
        result[MODE_ENV] = str(mode)
    if units is not None:
        result[UNITS_ENV] = json.dumps(list(units))
    if session_deadline is not None:
        result[SESSION_DEADLINE_ENV] = str(int(session_deadline))
    if carry_in:
        result[CARRY_IN_ENV] = str(carry_in)
    if input_datasets:
        result[INPUT_DATASETS_ENV] = str(input_datasets)
    if dataset_checks:
        result[DATASET_CHECKS_ENV] = str(dataset_checks)
    return result


def kernel_environment(
    clone_root: str | Path,
    commit: str,
    existing: Mapping[str, str] | None = None,
    *,
    mode: Any = None,
    units: list[str] | None = None,
    session_deadline: int | None = None,
    carry_in: str | None = None,
    input_datasets: str | None = None,
    dataset_checks: str | None = None,
) -> dict:
    """Everything the kernel receives from this cell, composed in one place.

    Three variables always, and up to two more when this submission
    declares them: the `PYTHONPATH` that makes the pinned code importable,
    the two that tell the notebook WHERE the pinned code is and WHICH
    commit it is, and `FORGE_RUN_MODE`/`FORGE_RUN_UNITS` — composed by
    `submission_environment()` and merged in here — that tell it which
    per-submission slice it is running. This function is the only thing
    that decides any of them; a second place that exported one of the
    first three would be a second place deciding which tree a notebook
    runs against, and the whole reason that handoff exists is that a
    notebook left to work it out resolves a directory that exists on any
    worker and fails much later, naming a package rather than a root. The
    same discipline applies to the newer two: `select_block()` already
    reads `mode` off `run_config` to choose a block, so a second place
    that re-derived `FORGE_RUN_MODE` from something other than that exact
    value would be a second place a kernel's view of "which run is this"
    could disagree with the runner's own.

    `existing` is the environment being extended, so `PYTHONPATH` is
    prepended to rather than replaced; every forge-owned name, old or new,
    is set outright, because the only thing that could already be carrying
    one is an earlier runner, and this submission's own value is the one
    that counts. `mode`/`units` default to `None`, so a caller that never
    passes either gets exactly the three names this function has always
    produced — see `submission_environment()` for the absent/empty
    distinction that governs what either becomes when it is passed.
    """
    existing = {} if existing is None else existing
    composed = {
        "PYTHONPATH": kernel_python_path(clone_root, existing.get("PYTHONPATH")),
        CLONE_ROOT_ENV: str(Path(clone_root).resolve()),
        CLONE_COMMIT_ENV: str(commit),
    }
    composed.update(submission_environment(mode, units, session_deadline, carry_in,
                                           input_datasets, dataset_checks))
    return composed


def block_kind(block: Mapping[str, Any]) -> str:
    """Which of the two shapes a selected block declares — `"callable"`
    (a `module`/`function` pair) or `"notebook"` (a `notebook` path) —
    refusing anything that is neither and anything that is both.

    The mirror of `jobfolder.run_block_kind()`, held here on its own for
    the reason every guard in these two assets is: this cell runs against
    whatever `run-config.json` the kernel was actually handed, not against
    the one a generator validated. A block that declares neither shape is
    refused rather than defaulted, and a block that declares both is
    refused rather than resolved by precedence — a silent precedence rule
    would decide, on the worker, which of two disagreeing declarations the
    operator paid for.
    """
    if not isinstance(block, Mapping):
        raise InvokeError(f"selected block {block!r} is not an object")
    notebook = block.get("notebook")
    module = block.get("module")
    function = block.get("function")
    if notebook is not None and (module is not None or function is not None):
        raise InvokeError(
            f"selected block declares BOTH a notebook ({notebook!r}) and a "
            f"module/function pair ({module!r}/{function!r}); a block "
            "declares exactly one of the two"
        )
    if notebook is not None:
        if not isinstance(notebook, str) or not notebook.strip():
            raise InvokeError(
                f"selected block declares notebook {notebook!r}: a notebook "
                "path must be a non-empty string"
            )
        return "notebook"
    if module and function:
        return "callable"
    raise InvokeError(
        f"selected block {dict(block)!r} declares neither a "
        "'module'/'function' pair nor a 'notebook'"
    )


def select_block(run_config: Mapping[str, Any]) -> Mapping[str, Any]:
    """The normal `run` block, or its `smoke` variant when
    `run_config["mode"] == "smoke"` — T11 sets that mode; this is the
    branch it selects.
    """
    run_block = run_config.get("run", {})
    if run_config.get("mode") == "smoke":
        smoke = run_block.get("smoke")
        if not smoke:
            raise InvokeError(
                "run_config declares mode 'smoke' but its 'run' block "
                "carries no 'smoke' entry"
            )
        return smoke
    return run_block


def resolve_callable(
    block: Mapping[str, Any],
    *,
    import_module: Callable[[str], Any] = importlib.import_module,
) -> Callable[..., Any]:
    """Resolve `block["module"]`/`block["function"]` through `importlib`,
    refusing a missing module, a missing attribute, or a non-callable
    attribute — never guessing at any of the three.
    """
    module_name = block.get("module")
    function_name = block.get("function")
    if not module_name or not function_name:
        raise InvokeError(
            f"block {dict(block)!r} is missing a 'module' or a 'function'"
        )
    try:
        module = import_module(module_name)
    except ImportError as exc:
        raise InvokeError(f"could not import {module_name!r}: {exc}") from exc
    try:
        func = getattr(module, function_name)
    except AttributeError as exc:
        raise InvokeError(
            f"{module_name!r} has no attribute {function_name!r}"
        ) from exc
    if not callable(func):
        raise InvokeError(f"{module_name}.{function_name} is not callable")
    return func


def _default_notebook_client(notebook: Any, *, kernel_name: str, cwd: Path) -> Any:
    """The real executor, built only when a notebook run actually reaches
    it — never at import time, so the forge suite can drive every other
    function in this file on a machine that has no kernel at all.

    `nbclient` is what executes; `resources.metadata.path` is the working
    directory it starts the kernel in. That directory is the RUNNER's own
    working directory and deliberately not the notebook's location inside
    the clone: a notebook writing a relative path is writing an output,
    and an output written inside the clone is an output the fetch never
    sees. The clone is the pinned input; the working directory is what
    comes back.
    """
    from nbclient import NotebookClient

    return NotebookClient(
        notebook,
        kernel_name=kernel_name,
        resources={"metadata": {"path": str(cwd)}},
    )


def execute_notebook(
    block: Mapping[str, Any],
    base_dir: str | Path | None = None,
    *,
    commit: Any = None,
    mode: Any = None,
    units: list[str] | None = None,
    session_deadline: int | None = None,
    carry_in: str | None = None,
    input_datasets: str | None = None,
    dataset_checks: str | None = None,
    client_factory: Callable[..., Any] = _default_notebook_client,
) -> dict:
    """Execute the declared notebook — the notebook half of cell 1.

    The notebook is read from the CLONE (`<base>/clone/<notebook>`, the
    pinned bytes cell 0 fetched), executed with the kernel it names, and
    written back — outputs and all — to `<base>/executed-<name>.ipynb`,
    the runner's own working directory. That destination is the whole of
    "the outputs come back": the fetch materializes the files the worker
    left in its working directory, which is already how `bootstrap.json`
    returns, so an executed notebook written there needs nothing added
    anywhere else in this skill to arrive.

    The kernel is started with `kernel_environment()`'s variables: the
    clone's `src` first on `PYTHONPATH`, the clone's directory and the
    pinned commit under the two forge-owned names the notebook's own first
    cell reads, and — when this submission declares either —
    `FORGE_RUN_MODE`/`FORGE_RUN_UNITS` under the two names
    `submission_environment()` composes. That handoff is why `commit`,
    `mode` and `units` are all parameters of this function: they come from
    `run-config.json` by way of `invoke()`, and `commit` is the only thing
    that lets the notebook check the checkout it is pointed at instead of
    trusting it, while `mode`/`units` are the only channel this particular
    submission's own facts have for reaching a notebook at all — a
    notebook's own cells are the pinned bytes cell 0 fetched, identical for
    every worker that runs the same clone, so a per-submission fact has
    nowhere to live but the environment its kernel starts in.

    Four things this refuses rather than works around:

    - a run with no commit to hand over. This is the metered path; a
      notebook started without the pin is a notebook that has to work the
      repository out for itself, and the answer it works out is a
      directory that exists on any worker. Refused BEFORE the kernel
      starts, because a job that runs the wrong commit works;
    - a notebook path that escapes the clone, or is not a file inside it
      (cell 0 already proves this for a declared notebook, and this cell
      proves it again because it is the cell that opens the file);
    - a missing `nbformat`/`nbclient` — an `ImportError` becomes an
      `InvokeError` naming `environment.install` as the remedy, the same
      remedy cell 0's own executor gate names;
    - an execution that raises — the partially-executed notebook is
      written to the same destination BEFORE the failure is re-raised, so
      the fetched artifact carries the traceback in the cell that
      produced it instead of nothing at all.

    `client_factory` exists only so the forge suite can drive this
    function without a kernel; the default is the real one.
    """
    if not isinstance(commit, str) or not commit.strip():
        raise InvokeError(
            f"cannot start a notebook kernel: the pinned commit is {commit!r}, "
            f"so neither {CLONE_ROOT_ENV} nor {CLONE_COMMIT_ENV} can be handed "
            "over as a pair. Half a handoff is refused on the reading side too; "
            "a notebook left to locate the repository on its own resolves a "
            "directory that exists on any worker and fails much later, naming a "
            "package rather than a root"
        )
    base = Path(base_dir) if base_dir is not None else Path.cwd()
    name = block["notebook"]
    clone_root = (base / CLONE_DIRNAME).resolve()
    notebook_path = (clone_root / name).resolve()
    try:
        notebook_path.relative_to(clone_root)
    except ValueError:
        raise InvokeError(
            f"declared notebook {name!r} resolves to {notebook_path}, outside "
            f"the clone at {clone_root}"
        ) from None
    if not notebook_path.is_file():
        raise InvokeError(
            f"declared notebook {name!r} is not at {notebook_path}; the "
            "sparse checkout delivered nothing for it"
        )
    try:
        import nbformat
    except ImportError as exc:
        raise InvokeError(
            "cannot execute a notebook: 'nbformat' is not importable in this "
            "runtime. Declare it in run-config.json's environment.install "
            f"(--environment-requirement): {exc}"
        ) from exc

    notebook = nbformat.read(str(notebook_path), as_version=4)
    kernelspec = (notebook.get("metadata") or {}).get("kernelspec") or {}
    kernel_name = str(kernelspec.get("name") or DEFAULT_KERNEL_NAME)
    executed_path = base / f"{EXECUTED_NOTEBOOK_PREFIX}{notebook_path.name}"

    try:
        client = client_factory(notebook, kernel_name=kernel_name, cwd=base)
    except ImportError as exc:
        raise InvokeError(
            "cannot execute a notebook: 'nbclient' is not importable in this "
            "runtime. Declare it in run-config.json's environment.install "
            f"(--environment-requirement): {exc}"
        ) from exc

    handoff = kernel_environment(clone_root, commit, os.environ,
                                 mode=mode, units=units,
                                 session_deadline=session_deadline,
                                 carry_in=carry_in,
                                 input_datasets=input_datasets,
                                 dataset_checks=dataset_checks)
    saved = {variable: os.environ.get(variable) for variable in handoff}
    os.environ.update(handoff)
    try:
        client.execute()
    finally:
        for variable, previous in saved.items():
            if previous is None:
                os.environ.pop(variable, None)
            else:
                os.environ[variable] = previous
        # Written on the failure path too, and that is the point: a
        # notebook that died halfway is the only record of WHERE it died,
        # and losing it means paying the quota again to find out.
        nbformat.write(notebook, str(executed_path))

    return {
        "notebook": name,
        "kernel": kernel_name,
        "executed": str(executed_path),
        "cells": len(notebook.get("cells") or []),
    }


def invoke(
    run_config: Mapping[str, Any],
    *,
    import_module: Callable[[str], Any] = importlib.import_module,
    base_dir: str | Path | None = None,
    client_factory: Callable[..., Any] = _default_notebook_client,
) -> Any:
    """The whole of cell 1: select the block, decide which of the two
    shapes it declares, and run that one.

    A callable block resolves through `importlib` and is called with its
    declared kwargs, exactly as it always was. A notebook block is
    executed from the clone and written back executed. `block_kind()`
    decides, and it refuses a block that is neither or both — this
    function has no default branch, because the only default available
    costs the same quota as the right answer.

    `run_config["commit"]`, `run_config["mode"]` and `run_config["units"]`
    are all read here and handed down rather than looked up again lower:
    this is where the config is, and re-reading any of the three somewhere
    else would be a second place that decides which commit, which mode, or
    which units a submission runs against. Read with `.get()` and never
    `[...]` — a missing pin becomes `execute_notebook()`'s own refusal,
    which says what could not be handed over, instead of a `KeyError` that
    says only that a dictionary was missing a key; a missing mode or units
    is simply absent, and `submission_environment()` is what turns that
    absence into no environment variable at all rather than a refusal,
    because unlike the pin, neither one is required for either shape to
    run.

    The notebook branch hands `mode`/`units` down through
    `execute_notebook()`'s own parameters, which compose them into the
    kernel's environment the same way `commit` already is. The CALLABLE
    branch has no kernel and no `execute_notebook()` to hand them through,
    so it composes `submission_environment()` directly and applies it to
    `os.environ` around the call, restoring it afterward with the exact
    idiom `execute_notebook()` already uses for its own handoff — save
    whatever each variable held before, update, run, then put every saved
    value back (or remove the variable if there was nothing to restore).
    The reason the callable branch needs this at all: `block["kwargs"]` is
    written once, at job generation, and is therefore IDENTICAL for every
    worker a job fans out to, while `mode` and `units` are written once per
    SUBMISSION by the packer and the CLI (`remote_cli.py:1260-1261`). A
    callable that needs to know which units it was handed, or whether it
    is running the smoke variant, cannot learn either from `kwargs` no
    matter how the job was generated — the environment is the only channel
    either shape has for a fact that varies per submission rather than per
    job.
    """
    block = select_block(run_config)
    mode = run_config.get("mode")
    units = run_config.get("units")
    deadline = None
    if run_config.get(SESSION_LIMIT_KEY) is not None:
        deadline = session_deadline(run_config[SESSION_LIMIT_KEY], started=time.time())
    kind = block_kind(block)
    # Restored before the entrypoint, whichever shape it is, so the target
    # resumes from checkpoints already on disk (kernel-carry S3).
    carry_in = restore_carry(run_config, base_dir)
    # Where the declared input datasets are mounted (kernel-input-datasets S3).
    input_datasets = discover_input_datasets(run_config)
    checks = run_config.get("datasetChecks")
    dataset_checks = json.dumps(checks, sort_keys=True) if checks else None
    if kind == "notebook":
        return execute_notebook(block, base_dir,
                                commit=run_config.get("commit"),
                                mode=mode, units=units,
                                session_deadline=deadline,
                                carry_in=carry_in,
                                input_datasets=input_datasets,
                                dataset_checks=dataset_checks,
                                client_factory=client_factory)
    func = resolve_callable(block, import_module=import_module)
    kwargs = dict(block.get("kwargs") or {})
    handoff = submission_environment(mode, units, deadline, carry_in, input_datasets,
                                     dataset_checks)
    # remote-preflight F1: a callable job is handed the clone root and the
    # pinned commit under the same two names a notebook kernel receives, so
    # a target that stamps its commit on a code-bundle worker (no git
    # metadata beyond `.git/HEAD`) reads it from `FORGE_CLONE_COMMIT` there
    # too. Exported only when the pin is present: unlike the notebook
    # branch, a callable needs neither to run, so a missing pin is not a
    # refusal here.
    commit = run_config.get("commit")
    if isinstance(commit, str) and commit.strip():
        base = Path(base_dir) if base_dir is not None else Path.cwd()
        handoff[CLONE_ROOT_ENV] = str((base / CLONE_DIRNAME).resolve())
        handoff[CLONE_COMMIT_ENV] = commit
    saved = {variable: os.environ.get(variable) for variable in handoff}
    os.environ.update(handoff)
    try:
        return func(**kwargs)
    finally:
        for variable, previous in saved.items():
            if previous is None:
                os.environ.pop(variable, None)
            else:
                os.environ[variable] = previous


def _load_run_config(base_dir: str | Path | None = None) -> dict:
    base = Path(base_dir) if base_dir is not None else Path.cwd()
    path = base / CONFIG_FILENAME
    if not path.is_file():
        raise InvokeError(f"{path} does not exist")
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    invoke(_load_run_config())
