#!/usr/bin/env python3
"""The Colab VM-side executor — everything after `launch.py` spawned it.

Runs INSIDE the session's working directory (`/content/.psmith/<session>`
in production; its own resolved directory everywhere else, which is what
lets the forge suite execute it without a VM). It reads the uploaded
`run-config.json` and `runner.ipynb`, executes the notebook with
`nbclient`, and writes the three files the session protocol is built on:

- `runner.executed.ipynb` — the executed notebook, written on the failure
  path too, because a notebook that died halfway is the only record of
  where it died (`runner_invoke.py`'s own doctrine, applied one level up);
- `files.json` — the manifest `fetch()` downloads, kept current DURING
  the run too (every `MANIFEST_REFRESH_SECONDS`, written atomically), so
  a session killed or reclaimed before `status.json` still lists what it
  had already written, and `fetch()` returns it as incomplete: the runner's
  working-directory capture (every regular file under this directory,
  minus the protocol's own names and minus `clone/.git`). Never a
  candidate scan, and never the pinned clone's VCS metadata: this is the
  landed capture rule of the parent plan's D12 (judged fix S2-J1, with
  the `.git` fold-in S2-J12);
- `status.json` — LAST, and outside every other try/finally: its presence
  is the run's only completion signal (`exitCode` 0 or non-zero, never
  absent for a run that reached this process).

A crash before `status.json` leaves the run `running` to a poll, which is
exactly what it is: the evidence that completion happened is missing, not
negative, so nothing here ever invents one early.

Nothing here names the service, reads a credential, or knows the CLI
exists: this file's whole world is one directory on one VM. The S3
credential material lives in this same boundary and nowhere else: a
staged `git-askpass.sh` is made executable here (chmod 0o700 — the upload
is a measured byte-copy and asserts no mode), both it and its token file
are deleted best-effort after the execution attempt, BEFORE the manifest
walk, and both names are excluded from the manifest at the top level as
the fallback that covers a failed deletion or a notebook that never
started.
"""
from __future__ import annotations

import json
import os
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

CONFIG_FILENAME = "run-config.json"
NOTEBOOK_FILENAME = "runner.ipynb"
EXECUTED_NOTEBOOK_FILENAME = "runner.executed.ipynb"
FILES_FILENAME = "files.json"
# The manifest is written here first and renamed over `files.json`, so a
# reader never sees a half-written list.
FILES_TMP_FILENAME = "files.json.tmp"
STATUS_FILENAME = "status.json"
STDOUT_LOG_FILENAME = "stdout.log"
LAUNCH_FILENAME = "launch.json"
EXECUTOR_FILENAME = "executor.py"
CLONE_DIRNAME = "clone"
VCS_DIRNAME = ".git"
DEFAULT_KERNEL_NAME = "python3"

# The credential material a credentialed submission stages beside this
# executor (S3): an askpass script and the token file it reads. The names
# are declared in THREE files by convention — the backend adapter (the
# uploader and the fetch-time refusal), this file (chmod, deletion,
# exclusion) and `assets/runner_bootstrap.py` (the clone's own use and
# deletion) — deliberately not shared by import: nothing above the seam
# may name the service, and the asset files are byte-copies, never
# importers of each other.
REPO_CREDENTIAL_ASKPASS_FILENAME = "git-askpass.sh"
REPO_CREDENTIAL_TOKEN_FILENAME = "git-askpass-token"

# The material files this executor deletes after the run and never lists.
# Deletion is best-effort (a failure is recorded in `status.json`, never
# fatal); this exclusion is the fallback that makes residue un-listable
# even when the deletion fails, and it is also what covers `nbclient`
# failing to start at all (cell 0 never ran, so nothing deleted anything).
CREDENTIAL_MATERIAL_FILENAMES = frozenset(
    {REPO_CREDENTIAL_ASKPASS_FILENAME, REPO_CREDENTIAL_TOKEN_FILENAME}
)

# The files the PROTOCOL itself owns in the working directory. Subtracted
# from the manifest by name at the TOP level only: a file carrying one of
# these names further down the tree is a product of the run, not a
# protocol payload, and stays in the capture.
PROTOCOL_FILENAMES = frozenset(
    {
        EXECUTOR_FILENAME,
        LAUNCH_FILENAME,
        CONFIG_FILENAME,
        NOTEBOOK_FILENAME,
        STATUS_FILENAME,
        FILES_FILENAME,
        FILES_TMP_FILENAME,
        STDOUT_LOG_FILENAME,
    }
)

# How often the running manifest is rewritten while the notebook executes.
# A session the service stops (its continuous limit, or an idle reclaim)
# returns at most this much less than it wrote; the cost is one directory
# walk per interval.
MANIFEST_REFRESH_SECONDS = 60

# This executor's OWN ceiling for one notebook execution — deliberately
# not the CLI's helper budget (`--timeout`'s 600 s class is for short
# in-kernel helpers, never for the payload run this skill exists for): a
# ceiling that kills a real run records a failure the run never had.
# Three hours sits well above the observed run lengths this skill has
# paid for (a 75-minute GPU run is on record) and below Colab's own
# session ceiling.
NOTEBOOK_TIMEOUT_SECONDS = 10800

# The whole allowlist of ERROR TEXT kept in `status.json`. Bounded so a
# runaway traceback cannot turn the completion signal into a multi-MB
# file every poll has to read past.
ERROR_MAX_CHARS = 2000


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def execute_notebook(base: Path) -> None:
    """Execute `runner.ipynb` with its own declared kernel, with the
    kernel's working directory set to `base` — the runner's working
    directory, and deliberately not the notebook's location: a relative
    write is an output, and outputs must land where `fetch()` looks.

    The executed notebook is written in a `finally`, so a run that dies
    halfway still comes back with the cell that killed it. `nbformat`
    and `nbclient` are imported HERE, never at module import: importing
    the module (the forge suite does) must not require a kernel
    installation, and a missing one surfaces as this run's failure with
    the traceback in `status.json["error"]`, not as an import-time crash
    of the whole executor.

    `client_factory`-style injection is deliberately absent: the suite
    drives this function's caller (`run`) with this function replaced,
    which is the same seam one level up.
    """
    import nbformat
    from nbclient import NotebookClient

    notebook_path = base / NOTEBOOK_FILENAME
    notebook = nbformat.read(str(notebook_path), as_version=4)
    kernelspec = (notebook.get("metadata") or {}).get("kernelspec") or {}
    kernel_name = str(kernelspec.get("name") or DEFAULT_KERNEL_NAME)
    client = NotebookClient(
        notebook,
        timeout=NOTEBOOK_TIMEOUT_SECONDS,
        kernel_name=kernel_name,
        resources={"metadata": {"path": str(base)}},
    )
    try:
        client.execute()
    finally:
        nbformat.write(notebook, str(base / EXECUTED_NOTEBOOK_FILENAME))


def manifest_entries(base: Path) -> list[str]:
    """The `files.json` allowlist: every regular file the run left in its
    working directory, minus the protocol's own names and minus the
    pinned clone's VCS metadata, sorted POSIX-relative.

    Two prunes, each a deliberate rule rather than a heuristic:

    - a TOP-LEVEL name in `PROTOCOL_FILENAMES` is protocol, not product;
    - a TOP-LEVEL name in `CREDENTIAL_MATERIAL_FILENAMES` (S3) is the
      staged askpass material — normally already deleted by the time this
      runs, and excluded here so a residue from a failed deletion (or a
      notebook that never started) can never be listed either;
    - anything under `clone/.git/` is the pinned input's VCS metadata —
      thousands of files that are not produced artifacts and that a
      per-file download would pay for one call at a time.

    Symlinks are skipped, never followed and never listed: a link's
    target is somebody else's file, possibly outside this directory, and
    a manifest that can point outside the session is a manifest that can
    fetch a file this run never made.
    """
    entries: list[str] = []
    for path in base.rglob("*"):
        if path.is_symlink():
            continue
        if not path.is_file():
            continue
        relative = path.relative_to(base)
        parts = relative.parts
        if len(parts) == 1 and (
            parts[0] in PROTOCOL_FILENAMES
            or parts[0] in CREDENTIAL_MATERIAL_FILENAMES
        ):
            continue
        if len(parts) >= 2 and parts[0] == CLONE_DIRNAME and parts[1] == VCS_DIRNAME:
            continue
        entries.append(relative.as_posix())
    return sorted(entries)


def write_manifest(base: Path) -> None:
    """Write `files.json` atomically: the list goes to `FILES_TMP_FILENAME`
    and is renamed over the manifest, so a poll or fetch reading it mid-run
    reads either the previous list or the new one, never half of one."""
    tmp = base / FILES_TMP_FILENAME
    _write_json(tmp, manifest_entries(base))
    os.replace(tmp, base / FILES_FILENAME)


def _refresh_manifest(base: Path, stop: threading.Event) -> None:
    """The running manifest: rewritten every `MANIFEST_REFRESH_SECONDS`
    until `stop` is set. A failed refresh is skipped, never fatal -- the
    final manifest after the run is the one `run()` checks."""
    while not stop.wait(MANIFEST_REFRESH_SECONDS):
        try:
            write_manifest(base)
        except Exception:  # noqa: BLE001 - the run must not die of a refresh
            continue


def _ensure_askpass_mode(base: Path) -> None:
    """S3/D6: re-establish the askpass script's executable bit before the
    notebook runs.

    The upload is a measured byte-copy and asserts no mode, so the bit is
    re-established here rather than assumed. A chmod failure raises, and
    `run()` catches it on the same boundary as the notebook — so the run
    fails with a clear `status.json["error"]` BEFORE any notebook starts,
    rather than letting the clone die later on a non-executable askpass.
    """
    askpass = base / REPO_CREDENTIAL_ASKPASS_FILENAME
    if askpass.is_file():
        os.chmod(askpass, 0o700)


def _delete_credential_material(path: Path) -> None:
    """The single unlink site for the staged material, so a test can
    inject one deletion failure without patching `Path.unlink` globally.
    """
    path.unlink(missing_ok=True)


def _remove_credential_material(base: Path, errors: list[str]) -> None:
    """Best-effort deletion of the staged material, after the execution
    attempt — success or failure — and BEFORE the manifest walk (S3/D6).

    Both names are attempted (`missing_ok` covers a credentialless run,
    where neither was ever staged). A failed unlink is appended to the
    caller's error list, which lands in `status.json["error"]`, and is
    never fatal: the clone's own outcome must not be masked, and the
    manifest exclusion is what bounds the residue either way.
    """
    for name in sorted(CREDENTIAL_MATERIAL_FILENAMES):
        try:
            _delete_credential_material(base / name)
        except OSError as exc:
            errors.append(
                f"credential cleanup: {name}: {type(exc).__name__}: {exc}"
            )


def run(base: Path) -> int:
    """Execute, then always write the manifest and, last of all, the
    completion signal. The return value is the exit code `status.json`
    carries; the CALLER (`__main__` below) uses it only as its own exit
    code, and the adapter's poll reads `status.json`, never this
    process's exit status — a detached child's exit status is not
    observable to anybody who was not waiting on it, and the CLI process
    that spawned us is long gone.
    """
    errors: list[str] = []
    exit_code = 0
    stop = threading.Event()
    refresher = threading.Thread(
        target=_refresh_manifest, args=(base, stop), daemon=True
    )
    refresher.start()
    try:
        _ensure_askpass_mode(base)
        execute_notebook(base)
    except BaseException as exc:  # noqa: BLE001 - the signal must survive any failure
        exit_code = 1
        errors.append(f"{type(exc).__name__}: {exc}")
    finally:
        stop.set()
        refresher.join()

    # S3/D6's deletion point: after the attempt, before the manifest. The
    # manifest walk below runs AFTER this so a successful deletion is
    # reflected, and excludes both names anyway so a failed one is not.
    _remove_credential_material(base, errors)

    try:
        write_manifest(base)
    except BaseException as exc:  # noqa: BLE001 - status.json must still land
        errors.append(f"manifest: {type(exc).__name__}: {exc}")

    status: dict[str, object] = {"exitCode": exit_code, "finishedAt": _utc_now()}
    if errors:
        status["error"] = " | ".join(errors)[:ERROR_MAX_CHARS]
    _write_json(base / STATUS_FILENAME, status)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(run(Path(__file__).resolve().parent))
