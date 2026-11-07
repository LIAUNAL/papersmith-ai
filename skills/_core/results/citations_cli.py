#!/usr/bin/env python3
"""CLI over the SOTA citations contract (``citations.py``).

Usage:
    citations_cli.py check [--root <dir>]
    citations_cli.py rank [--root <dir>] [--sjr <csv>]

Prints one JSON object. ``check``: every idea cited and both concept trees whole
gives ``{"ok": true, ...}`` and exit 0. An idea owes citations or a tree owes a
node: ``{"ok": false, "error": "SOTA_CITATIONS_OWED", "owed": [{"key",
"problems"}], "trees": [...], ...}`` and exit 1. It writes nothing.

``rank`` writes ``sota-pool/journal-ranks.json``: for each pool reference with a
DOI, its Crossref work type, ISSNs and issued year, and its quartile in the SJR
table (``--sjr``, else the newest CSV imported with ``journal_cli.py sjr-import``).
A reference without a DOI is skipped, and one Crossref does not answer is
reported as unresolved: neither gets a rank, so neither passes the journal rule.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

try:
    from . import citations
except ImportError:
    import citations  # type: ignore


CROSSREF_WORKS = "https://api.crossref.org/works/"
CROSSREF_TIMEOUT = 15


def _emit(data: dict, code: int = 0) -> int:
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return code


def _check(root: Path) -> int:
    if not root.is_dir():
        return _emit({"ok": False, "error": "ROOT_ABSENT", "message": f"{root} is not a directory"}, 1)
    state = citations.state(root)
    owed = [{"key": idea["key"], "problems": idea["problems"]} for idea in state["ideas"] if idea["owed"]]
    summary = {"ideas": len(state["ideas"]), "cited": len(state["ideas"]) - len(owed), "stages": state["stages"],
               "file_problems": state["file_problems"], "owed": owed, "trees": state["trees"]}
    if not owed and not state["trees"]:
        return _emit({"ok": True, **summary})
    message = (f"{len(owed)} idea(s) owe {citations.MIN_CITATIONS} to {citations.MAX_CITATIONS} SOTA citations "
               f"in {citations.CITATIONS_REL}; {len(state['trees'])} concept tree finding(s)")
    return _emit({"ok": False, "error": "SOTA_CITATIONS_OWED", "message": message, **summary}, 1)


def _crossref(doi: str) -> dict[str, Any] | None:
    """A DOI's work type, ISSNs and issued year, ``None`` when Crossref does not answer."""
    request = urllib.request.Request(CROSSREF_WORKS + urllib.parse.quote(doi, safe=""),
                                     headers={"User-Agent": "papersmith-ai"})
    try:
        with urllib.request.urlopen(request, timeout=CROSSREF_TIMEOUT) as response:
            message = json.load(response)["message"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    parts = (message.get("issued") or {}).get("date-parts") or [[None]]
    return {"type": message.get("type"), "issn": message.get("ISSN") or [], "year": parts[0][0]}


def _journal_cli() -> Any:
    """The journal-finder CLI, whose SJR reader this command shares."""
    path = Path(__file__).resolve().parents[2] / "journal-finder" / "scripts" / "journal_cli.py"
    spec = importlib.util.spec_from_file_location("papersmith_journal_cli", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.")
    with os.fdopen(handle, "w", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
    os.replace(temp, path)


def _rank(root: Path, sjr: str | None) -> int:
    if not root.is_dir():
        return _emit({"ok": False, "error": "ROOT_ABSENT", "message": f"{root} is not a directory"}, 1)
    journal = _journal_cli()
    cached = None if sjr else journal.latest_cached_sjr()
    table_path = Path(sjr) if sjr else (cached[0] if cached else None)
    if table_path is None:
        return _emit({"ok": False, "error": "SJR_TABLE_ABSENT",
                      "message": f"no SJR table: download the CSV from {journal.SJR_DOWNLOAD_URL} and "
                                 "run journal_cli.py sjr-import --file <csv>, or pass --sjr <csv>"}, 1)
    try:
        table = journal.read_sjr(table_path)
    except journal.Refusal as exc:
        return _emit({"ok": False, "error": "SJR_TABLE_INVALID", "message": str(exc)}, 1)
    root = root.expanduser().resolve()
    sjr_year = journal.year_from_name(table_path.name)
    ranks: dict[str, dict[str, Any]] = {}
    skipped: list[str] = []
    unresolved: list[str] = []
    for identity, record in citations._pool(root).items():
        identifier = record["identifier"]
        if not identity.startswith("doi:"):
            skipped.append(identifier)
            continue
        work = _crossref(identity.removeprefix("doi:"))
        if work is None:
            unresolved.append(identifier)
            continue
        hit = table.lookup(work["issn"]) or {}
        quartile = hit.get("quartile")
        ranks[identifier] = {"work_type": work["type"], "issn": work["issn"], "year": work["year"],
                             "quartile": quartile, "quartile_source": "sjr" if quartile else "unknown",
                             "sjr_year": sjr_year}
    _write_atomic(root / citations.RANKS_REL, {"schema": citations.SCHEMA, "ranks": ranks})
    return _emit({"ok": True, "ranked": len(ranks), "skipped": skipped, "unresolved": unresolved,
                  "written": citations.RANKS_REL})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="citations_cli.py", description="SOTA citations of each idea")
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="Say which ideas still owe their citations")
    check.add_argument("--root", default=".", help="Workspace root (default: current dir)")
    rank = sub.add_parser("rank", help="Record each pool reference's work type and SJR quartile")
    rank.add_argument("--root", default=".", help="Workspace root (default: current dir)")
    rank.add_argument("--sjr", help="SJR CSV (default: the newest imported table)")
    args = parser.parse_args(argv)
    return _rank(Path(args.root), args.sjr) if args.command == "rank" else _check(Path(args.root))


if __name__ == "__main__":
    raise SystemExit(main())
