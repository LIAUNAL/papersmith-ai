"""Kit-root resolution.

The kit is the framework's copy-on-init asset tree (skills, agent definitions,
paper-guide, provisioning scripts). Resolution order:

1. ``PAPERSMITH_KIT_ROOT`` environment variable — the explicit override.
2. A papersmith-ai development checkout on disk (a directory holding
   ``skills/``, ``scripts/setup_env.py``, and ``CLAUDE.md``) found above the
   installed package — this is how ``smith`` run from a checkout tracks
   live edits without reinstalling.
3. The ``_kit/`` snapshot bundled inside the installed package.

A resolved root must contain ``skills/``; otherwise the caller gets
SOURCE_ERROR (exit 2), because a kitless install cannot initialize or upgrade
a workspace.
"""

from __future__ import annotations

import os
from pathlib import Path

from .core import fs
from .errors import SourceError

KIT_DIR_NAME = "_kit"


def resolve_kit_root(start_file: str | Path | None = None) -> Path:
    """Resolve the kit root for an install located at ``start_file``.

    ``start_file`` defaults to this module's ``__file__``; tests pass an
    explicit path so resolution does not depend on the test machine's layout.
    """
    return resolve_kit_origin(start_file)[0]


def resolve_kit_origin(start_file: str | Path | None = None) -> tuple[Path, str]:
    """The kit root and the branch that found it: ``override``, ``checkout``
    or ``bundled`` -- the ``source`` a workspace's kit-source record names."""
    start = Path(start_file).resolve() if start_file else Path(__file__).resolve()
    env = os.environ.get("PAPERSMITH_KIT_ROOT")
    if env:
        return Path(env).expanduser().resolve(), "override"
    dev = _dev_checkout(start)
    if dev is not None:
        return dev, "checkout"
    return start.parent / KIT_DIR_NAME, "bundled"


def _dev_checkout(start_file: Path) -> Path | None:
    pkg_dir = start_file.parent  # .../src/papersmith (or site-packages/papersmith)
    src_or_site = pkg_dir.parent
    for candidate in (src_or_site.parent, *src_or_site.parents[1:4]):
        if _looks_like_checkout(candidate):
            return candidate
    return None


def _looks_like_checkout(root: Path) -> bool:
    return (
        fs.is_dir(root / "skills")
        and fs.is_regular_file(root / "scripts" / "setup_env.py")
        and fs.is_regular_file(root / "CLAUDE.md")
    )


def validate_kit_root(root: Path) -> Path:
    if not fs.is_dir(root / "skills"):
        raise SourceError(
            f"kit root {root} has no skills/ directory — point PAPERSMITH_KIT_ROOT "
            "at a papersmith-ai checkout or reinstall the package"
        )
    return root


def resolve_and_validate(start_file: str | Path | None = None) -> Path:
    return validate_kit_root(resolve_kit_root(start_file))


def resolve_and_validate_origin(start_file: str | Path | None = None) -> tuple[Path, str]:
    root, source = resolve_kit_origin(start_file)
    return validate_kit_root(root), source
