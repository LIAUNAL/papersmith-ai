#!/usr/bin/env python3
"""CLI over the SOTA citations contract (``citations.py``).

Usage:
    citations_cli.py check [--root <dir>]

Prints one JSON object. Every idea cited: ``{"ok": true, ...}`` and exit 0. An
idea owes citations: ``{"ok": false, "error": "SOTA_CITATIONS_OWED", "owed":
[{"key", "problems"}], ...}`` and exit 1. It writes nothing.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from . import citations
except ImportError:
    import citations  # type: ignore


def _emit(data: dict, code: int = 0) -> int:
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return code


def _check(root: Path) -> int:
    if not root.is_dir():
        return _emit({"ok": False, "error": "ROOT_ABSENT", "message": f"{root} is not a directory"}, 1)
    state = citations.state(root)
    owed = [{"key": idea["key"], "problems": idea["problems"]} for idea in state["ideas"] if idea["owed"]]
    summary = {"ideas": len(state["ideas"]), "cited": len(state["ideas"]) - len(owed), "stages": state["stages"],
               "file_problems": state["file_problems"], "owed": owed}
    if not owed:
        return _emit({"ok": True, **summary})
    message = (f"{len(owed)} idea(s) owe {citations.MIN_CITATIONS} to {citations.MAX_CITATIONS} SOTA citations "
               f"in {citations.CITATIONS_REL}")
    return _emit({"ok": False, "error": "SOTA_CITATIONS_OWED", "message": message, **summary}, 1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="citations_cli.py", description="SOTA citations of each idea")
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="Say which ideas still owe their citations")
    check.add_argument("--root", default=".", help="Workspace root (default: current dir)")
    args = parser.parse_args(argv)
    return _check(Path(args.root))


if __name__ == "__main__":
    raise SystemExit(main())
