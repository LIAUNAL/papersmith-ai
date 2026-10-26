"""Where the dashboard looks for TeX engines and PDF rasterizers.

The search is PATH first, then :data:`TOOL_FALLBACK_DIRS` (each glob pattern
sorted newest TeX Live year first), so a distribution installed outside PATH
is still found on macOS, Linux and Windows under WSL. Stdlib only.

Two other places restate the same list because they cannot import this
module: ``src/papersmith/core/doctor.py`` (the CLI's own interpreter) and
``skills/experiment-diagrams/scripts/diagram_cli.py`` (a standalone script).
``tests/test_toolchain_search.py`` fails when the copies drift.
"""

from __future__ import annotations

import glob
import os
import shutil
from pathlib import Path

#: Fallback directories after PATH, for TeX engines and rasterizers alike:
#: MacTeX's symlink farm, Homebrew (Apple silicon, then Intel and Linux
#: local installs) and TeX Live's per-year, per-platform trees.
TOOL_FALLBACK_DIRS: tuple[str, ...] = (
    "/Library/TeX/texbin",
    "/opt/homebrew/bin",
    "/usr/local/bin",
    "/usr/local/texlive/*/bin/*",
    "/opt/texlive/*/bin/*",
    "~/texlive/*/bin/*",
)


def find_tool(name: str, *, path: str | None = None,
              fallback_dirs: tuple[str, ...] | None = None) -> str | None:
    """The absolute path of ``name``: on ``path`` (default: PATH), else in a
    fallback directory (newest TeX Live year first), else None."""
    found = shutil.which(name, path=path)
    if found:
        return str(Path(found).absolute())
    dirs = TOOL_FALLBACK_DIRS if fallback_dirs is None else fallback_dirs
    for pattern in dirs:
        for directory in sorted(glob.glob(os.path.expanduser(pattern)), reverse=True):
            for candidate in (name, f"{name}.exe"):
                tool = Path(directory) / candidate
                if tool.is_file() and os.access(tool, os.X_OK):
                    return str(tool)
    return None
