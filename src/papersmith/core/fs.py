"""Total filesystem predicates for every framework-managed path.

A managed path is data a user can damage, and the framework's contract is to
report a damaged workspace rather than block on it or die inside it. Two
distinct hazards are therefore folded into ``False`` here:

* ``Path.is_file``, ``Path.is_dir`` and ``Path.exists`` re-raise every errno but
  ENOENT/ENOTDIR/EBADF/ELOOP, so an unsearchable parent (EACCES) escapes. On
  CPython 3.11-3.13 — which the declared ``requires-python`` covers — that
  includes the plain ``is_file`` this framework used to call directly. CPython
  3.14 changed which errnos ``_ignore_error`` swallows, so the same call returns
  ``False`` there: the guard is load-bearing on 3.11-3.13 and invisible on 3.14.
* A non-regular but *openable* path — a FIFO, or a symlink to a character
  device — makes the subsequent ``open(2)`` block forever or read without bound.
  A guarded read is not enough on its own; the regularity gate has to come
  first.

This module is deliberately dependency-free. ``core.config`` needs the same gate
``generators`` uses, and ``generators`` imports ``core.config``, so the guard
has to live below both of them.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path


def is_regular_file(path: Path) -> bool:
    """True when ``path`` is a regular file the framework may open.

    This is the gate every managed-path read must pass before it opens a file.
    """
    try:
        return path.is_file()
    except OSError:
        return False


def is_dir(path: Path) -> bool:
    """``Path.is_dir`` treating an unstatable path as absent."""
    try:
        return path.is_dir()
    except OSError:
        return False


def exists(path: Path) -> bool:
    """True when anything at all occupies ``path``.

    ``Path.exists`` follows symlinks — a dangling one reports ``False`` — and
    re-raises EACCES. This must not raise, and must not be fooled by a dangling
    link, or a write would land on the link's target instead of being reported.
    """
    try:
        path.lstat()
    except OSError:
        return False
    return True


def can_be_written(path: Path) -> bool:
    """True when writing ``path`` would create or replace a regular file.

    An existing non-regular path — directory, FIFO, socket, device, dangling
    symlink — is refused: ``open`` on a FIFO never returns, and clobbering a
    directory raises only after the caller has already mutated other files.
    """
    return not (exists(path) and not is_regular_file(path))


def read_text(path: Path, *, encoding: str = "utf-8") -> str | None:
    """Read a managed path as text, or ``None`` when it cannot be read.

    ``None`` covers absent, unstatable, non-regular (a FIFO would block) and
    undecodable alike: every caller treats "nothing readable here" the same way,
    so a damaged file degrades to a reported absence instead of an exception.
    """
    if not is_regular_file(path):
        return None
    try:
        return path.read_text(encoding=encoding)
    except (OSError, UnicodeDecodeError):
        return None


def write_text(path: Path, text: str, *, encoding: str = "utf-8") -> bool:
    """Write ``text`` to a managed path, or report that it could not be done.

    Returns ``False`` when the path is occupied by something other than a
    regular file, or when the write itself fails — a read-only parent, a full
    disk. The caller reports the path; nothing here raises.
    """
    if not can_be_written(path):
        return False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding=encoding)
    except OSError:
        return False
    return True


def replace_bytes(path: Path, data: bytes) -> bool:
    """Replace an existing regular file's bytes atomically, keeping its mode.

    For a file that belongs to the workspace (``papersmith.yaml``): a crash
    mid-write leaves either the old bytes or the new ones, never a truncated
    config, and nothing is decoded, so line endings stay as given. Returns
    ``False`` instead of raising when the path is not a regular file or the
    write fails.
    """
    if not is_regular_file(path):
        return False
    try:
        mode = path.stat().st_mode & 0o7777
        handle, temporary = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    except OSError:
        return False
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    except OSError:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        return False
    return True


def copy_file(source: Path, destination: Path) -> bool:
    """Copy ``source`` over ``destination``, or report that it could not be done.

    ``shutil.copyfile`` opens the destination for writing, so a FIFO there would
    block forever and a directory would raise. Returns ``False`` instead, so a
    damaged destination is reported rather than hanging the run.
    """
    if not can_be_written(destination):
        return False
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    except OSError:
        return False
    return True
