from __future__ import annotations

import sys
from pathlib import Path
from impl_gitops import git
from impl_layout import FORGE_ROOT, WORKSPACE
from impl_refusals import Refused


#: The directory this skill appends its own ledger to, relative to a product
#: root. Named here rather than imported from the position module because this
#: guard must not depend on the thing it is excusing.
LEDGER_DIRECTORY = ".implementation"


def _is_own_bookkeeping(porcelain_line: str) -> bool:
    """Whether one `git status --porcelain` line is this skill's own ledger.

    The guard exists so the skill never mutates a repository carrying somebody
    else's uncommitted work. Its own append-only ledger is not somebody else's
    work, and counting it produced a measured deadlock: every ledger-appending
    command (`position`, `discuss`, `gate`, `close`, `step`) leaves the tree
    dirty, so the next clean-requiring command (`plan`, `apply`, `step`)
    refuses. Measured on a scratch target -- one step ran, the second returned
    `DIRTY_WORKTREE` with `M <product>/.implementation/position.jsonl` as the
    only entry, and three ran back to back once that path was excluded.

    This excuses the path, never the question of whether the ledger belongs in
    the index at all. That is a separate decision, and this guard behaves the
    same either way -- which is the point: a repository that ignores its ledger
    and one that commits it must not disagree about whether a step may run.

    Porcelain paths are repository-relative. A rename carries two of them
    (`old -> new`) and both are checked, because a half-matched rename is not
    this skill's own bookkeeping.
    """
    payload = porcelain_line[3:] if len(porcelain_line) > 3 else ""
    sides = payload.split(" -> ") if " -> " in payload else [payload]
    return bool(sides) and all(
        LEDGER_DIRECTORY in Path(side.strip().strip('"')).parts
        for side in sides if side.strip())


def own_bookkeeping_snapshot(target: Path) -> dict[str, bytes | None]:
    """The bytes of every dirty path `require_clean_worktree` excuses.

    The guard admits exactly this dirt and refuses every other change, so it
    is the one pre-existing state a rollback after a failed mutation could
    destroy: `git reset --hard` reverts a modified ledger and deletes one the
    operation staged, and `git clean -fd` deletes an untracked one. Keyed by
    repository-relative path; `None` marks a ledger file deleted in the
    working tree. Listed file by file (`--untracked-files=all`), so an
    untracked `.implementation/` directory yields its files.
    """
    entries = git(target, "status", "--porcelain", "-z",
                  "--untracked-files=all").split("\0")
    kept: dict[str, bytes | None] = {}
    index = 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if len(entry) < 4:
            continue
        paths = [entry[3:]]
        if entry[0] in "RC":            # `-z` puts a rename's source next
            paths.append(entries[index])
            index += 1
        for rel in paths:
            if LEDGER_DIRECTORY not in Path(rel).parts:
                continue
            full = target / rel
            kept[rel] = full.read_bytes() if full.is_file() else None
    return kept


def require_clean_worktree(target: Path) -> None:
    dirty = [line for line in git(target, "status", "--porcelain").splitlines()
             if line.strip() and not _is_own_bookkeeping(line)]
    if dirty:
        raise Refused(
            "DIRTY_WORKTREE",
            "The target working tree has uncommitted or untracked changes. "
            "Commit or stash them first; this skill never mutates a dirty repository.",
        )


def resolve_target(raw: str) -> Path:
    target = Path(raw).expanduser().resolve()
    try:
        target.relative_to(WORKSPACE.resolve())
    except ValueError:
        raise Refused(
            "OUTSIDE_WORKSPACE",
            f"Target must live under {WORKSPACE}. Clone the repository there first — "
            "the forge's own environment is never a workspace for generated code.",
        )
    if not (target / ".git").exists():
        raise Refused("NOT_A_GIT_REPO", f"{target} is not a git repository.")
    return target


def require_non_forge_interpreter() -> None:
    prefix = Path(sys.prefix).resolve()
    try:
        prefix.relative_to((FORGE_ROOT / "skills").resolve())
    except ValueError:
        return
    raise Refused(
        "FORGE_INTERPRETER",
        "This process is running inside one of the forge's own virtualenvs. "
        "Re-run with a system interpreter so the target venv never inherits it.",
    )
