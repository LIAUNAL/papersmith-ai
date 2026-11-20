#!/usr/bin/env python3
"""Assemble the packaged Caztor at ``src/papersmith/_caztor`` from ``caztor/``.

Caztor, the LaTeX editor of the dashboard's PDF tab, is a Node.js application
kept in ``caztor/``. An install from PyPI has no checkout, so the wheel carries
what Caztor needs at run time, laid out as in the repository: its server built
into one file (``apps/server-local/dist/main.mjs``), its built web app, its
agent definitions, its guides and its licenses. Running it needs ``node`` only;
no ``npm install`` on the user's machine.

Building needs ``npm``: it installs ``caztor/``'s dependencies when they are
absent, builds the web app and bundles the server. Without ``npm`` it keeps an
existing ``_caztor`` and otherwise skips with a warning, unless ``--require``
is given (the publishing workflow), which makes any failure fatal.

Stdlib only.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CAZTOR = ROOT / "caztor"
TARGET = ROOT / "src" / "papersmith" / "_caztor"

#: The run-time files, relative to ``caztor/``: a folder is copied whole.
SERVER_BUNDLE = Path("apps") / "server-local" / "dist" / "main.mjs"
WEB_APP = Path("apps") / "web" / "dist"
SHIPPED = (SERVER_BUNDLE, WEB_APP, Path("LICENSES"), Path("NOTICE.md"), Path("README.md"))
#: Folders whose Markdown is shipped, and nothing else (their tests stay behind).
MARKDOWN_ONLY = (Path("agents"), Path("guides"))


def _npm(*args: str) -> None:
    subprocess.run(["npm", "--prefix", str(CAZTOR), *args], check=True,
                   stdout=subprocess.DEVNULL)


def build() -> None:
    """Install when needed, build the web app and bundle the server, in ``caztor/``."""
    if not (CAZTOR / "node_modules").is_dir():
        _npm("ci")
    _npm("run", "build", "-w", "@caztor/web")
    _npm("run", "build:server")


def assemble() -> None:
    """Copy the run-time files into ``_caztor``, replacing what was there."""
    for relpath in (*SHIPPED, *MARKDOWN_ONLY):
        if not (CAZTOR / relpath).exists():
            raise SystemExit(f"caztor/{relpath} is missing; nothing was packaged")
    if TARGET.exists():
        shutil.rmtree(TARGET)
    for relpath in SHIPPED:
        source, dest = CAZTOR / relpath, TARGET / relpath
        dest.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, dest)
        else:
            shutil.copy2(source, dest)
    for folder in MARKDOWN_ONLY:
        (TARGET / folder).mkdir(parents=True)
        for source in sorted((CAZTOR / folder).glob("*.md")):
            shutil.copy2(source, TARGET / folder / source.name)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--require", action="store_true",
                        help="fail instead of skipping when Caztor cannot be built")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)
    say = (lambda _message: None) if args.quiet else print

    def skip(reason: str) -> int:
        if args.require:
            print(f"build-caztor: {reason}", file=sys.stderr)
            return 1
        kept = " The existing package is kept." if TARGET.is_dir() else ""
        print(f"build-caztor: skipped, {reason}.{kept} The PDF tab falls back to "
              "its read-only viewer without Caztor.", file=sys.stderr)
        return 0

    if not (CAZTOR / "package.json").is_file():
        return skip("there is no caztor/ folder here")
    if shutil.which("npm") is None or shutil.which("node") is None:
        return skip("node and npm are needed to build Caztor")
    try:
        build()
    except (OSError, subprocess.CalledProcessError) as exc:
        return skip(f"building Caztor failed ({exc})")
    assemble()
    say(f"caztor: {sum(1 for p in TARGET.rglob('*') if p.is_file())} files -> {TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
