"""orphan_sweep: removes fixture directories a killed test run left behind.

Several suites materialize their fixtures inside the live repository rather
than a temp dir, because the code under test resolves its workspace from
`FORGE_ROOT` and offers no override for it. Those suites do clean up after
themselves -- but `addCleanup` never runs when the process is killed, and a
session limit, a timeout or a cancelled agent all kill it. What survives is a
`_<name>_<pid>` directory that the next run reads as real, producing failures
whose message points at the wrong defect entirely.

Three guards make this safe to run while other processes are using the
same checkout, which is how this repository is actually worked:

- **Owned only (#60).** `implementations/` is also where an operator keeps
  real implementation repositories, and those are old and untracked too. An
  entry under the forge is swept only when its name carries the pid of a
  test process that recorded itself in the run registry (`register_run`,
  called by `tests/conftest.py` and by `sweep_and_report`), that pid is no
  longer alive, and the run started before the entry was last written. No
  registry (no git directory) means nothing is swept. Symlinks are never
  swept. The registry lives in the checkout's git directory, outside every
  swept root and outside the shipped tree.

- **Untracked only.** Anything git tracks is left alone, whatever its name.
  `skills/_core/` is 66 tracked files behind a leading underscore; a
  name-pattern sweep without this guard would delete the shared core.
- **Old only.** A sibling process's fixture is seconds or minutes old. The
  age floor distinguishes an orphan whose owner is dead from a directory
  someone is writing to right now.

No guard is an optimization. Dropping any one turns this from a cleanup
into a way to lose work.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

FORGE_ROOT = Path(__file__).resolve().parents[1]

#: Where suites are known to materialize fixtures inside the live repository.
#: Directories only -- a root absent from disk is skipped, not an error.
SWEEP_ROOTS: tuple[Path, ...] = (
    FORGE_ROOT / "implementations",
    *(FORGE_ROOT / "skills").glob("*/scripts"),
)

#: An orphan's owner is dead; a sibling's fixture is live. One hour is far
#: above any single test's lifetime and far below the gap between sessions.
MIN_AGE_SECONDS = 3600

#: A run recorded longer ago than this no longer licenses a sweep: pids are
#: reused, and an orphan that old has been seen (and kept) many times over.
RUN_TTL_SECONDS = 30 * 24 * 3600

REGISTRY_NAME = "papersmith-test-runs"


def registry_path() -> Path | None:
    """`<git dir>/papersmith-test-runs`, or None outside a git checkout."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--absolute-git-dir"],
            cwd=FORGE_ROOT, capture_output=True, text=True)
    except OSError:
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return Path(result.stdout.strip()) / REGISTRY_NAME


def register_run() -> None:
    """Records this process as a test run that may make fixtures in the live
    tree: one appended `<pid> <start time>` line. Best effort -- an
    unrecorded run only means its orphans are never swept."""
    registry = registry_path()
    if registry is None:
        return
    try:
        with registry.open("a", encoding="utf-8") as handle:
            handle.write(f"{os.getpid()} {time.time():.0f}\n")
    except OSError:
        pass


def prune_registry(now: float) -> None:
    """Rewrites the registry keeping only runs inside `RUN_TTL_SECONDS`, so the
    append-only file stays bounded. Atomic (`os.replace`); a line another
    worker appends between the read and the replace is lost, which only means
    that run's orphans are never swept -- the safe direction."""
    registry = registry_path()
    if registry is None:
        return
    try:
        lines = registry.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    kept = []
    for line in lines:
        try:
            pid, started = line.split()
            int(pid)
            if now - float(started) <= RUN_TTL_SECONDS:
                kept.append(line)
        except ValueError:
            continue
    if len(kept) == len(lines):
        return
    scratch = registry.with_name(f"{registry.name}.{os.getpid()}.tmp")
    try:
        scratch.write_text("".join(f"{line}\n" for line in kept), encoding="utf-8")
        os.replace(scratch, registry)
    except OSError:
        scratch.unlink(missing_ok=True)


def _registered_runs(now: float) -> dict[int, list[float]] | None:
    """pid -> start times of recent registered runs; None without a registry."""
    registry = registry_path()
    if registry is None:
        return None
    runs: dict[int, list[float]] = {}
    try:
        lines = registry.read_text(encoding="utf-8").splitlines()
    except OSError:
        return runs
    for line in lines:
        try:
            pid, started = line.split()
            pid_n, started_t = int(pid), float(started)
        except ValueError:
            continue
        if now - started_t <= RUN_TTL_SECONDS:
            runs.setdefault(pid_n, []).append(started_t)
    return runs


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:          # exists, owned by someone else
        return True
    return True


def _owned_by_a_dead_run(path: Path, runs: dict[int, list[float]],
                         mtime: float) -> bool:
    """True when `path`'s name carries the pid of a registered, now-dead
    test run that started before `path` was last written."""
    for token in path.name.split(".")[0].split("_"):
        if not token.isdigit():
            continue
        pid = int(token)
        if any(started <= mtime for started in runs.get(pid, ())) \
                and not _alive(pid):
            return True
    return False


def _is_untracked(path: Path) -> bool:
    """True when git knows nothing about `path`. Anything tracked is never
    swept -- this is what keeps `skills/_core/` and every other
    legitimately underscore-prefixed tracked path out of reach."""
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", str(path)],
        cwd=FORGE_ROOT, capture_output=True, text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        return False
    # A directory holding tracked children is itself tracked, for our purposes.
    listed = subprocess.run(
        ["git", "ls-files", "--", str(path)],
        cwd=FORGE_ROOT, capture_output=True, text=True,
    )
    return not listed.stdout.strip()


def _age_seconds(path: Path, now: float) -> float:
    return now - path.lstat().st_mtime


def _inside_forge(root: Path) -> bool:
    try:
        root.resolve().relative_to(Path(FORGE_ROOT).resolve())
    except ValueError:
        return False
    return True


def sweep(roots: tuple[Path, ...] = SWEEP_ROOTS,
          min_age_seconds: float = MIN_AGE_SECONDS,
          now: float | None = None) -> list[str]:
    """Removes untracked `_`-prefixed entries older than `min_age_seconds`
    under each of `roots`; under the forge, only those a dead registered
    test run owns (#60). A root outside the forge is a test's own tempdir
    and needs no ownership proof. Returns the paths removed, relative to the
    forge root, so a caller can report what it cleaned rather than doing it
    silently."""
    now = time.time() if now is None else now
    removed: list[str] = []
    runs = None
    for root in roots:
        if not root.is_dir():
            continue
        needs_owner = _inside_forge(root)
        if needs_owner:
            runs = _registered_runs(now) if runs is None else runs
            if not runs:
                continue
        for child in sorted(root.glob("_*")):
            if child.name.startswith("__"):      # __pycache__ and friends
                continue
            if child.is_symlink():               # never swept, never followed
                continue
            if not _is_untracked(child):
                continue
            # A sibling's own cleanup may remove its fixture between the
            # listing above and this check; gone is not an orphan, and
            # raising here would error every test of the calling file.
            try:
                age = _age_seconds(child, now)
            except FileNotFoundError:
                continue
            if age < min_age_seconds:
                continue
            if needs_owner and not _owned_by_a_dead_run(child, runs, now - age):
                continue
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)
            try:
                removed.append(str(child.relative_to(FORGE_ROOT)))
            except ValueError:
                # A root outside the forge (a test's own tempdir). Report the
                # absolute path rather than failing the sweep over cosmetics.
                removed.append(str(child))
    return removed


def sweep_and_report() -> None:
    """`setUpModule` entry point: sweeps, and says what it removed. Silence
    means nothing was left behind, which is the normal case."""
    if os.environ.get("FORGE_SKIP_ORPHAN_SWEEP"):
        return
    register_run()
    prune_registry(time.time())
    for path in sweep():
        print(f"orphan_sweep: removed {path} (left by a killed run)")
