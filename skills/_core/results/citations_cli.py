#!/usr/bin/env python3
"""CLI over the SOTA citations contract (``citations.py``).

Usage:
    citations_cli.py check [--root <dir>]
    citations_cli.py rank [--root <dir>] [--sjr <csv>]
    citations_cli.py lab --id <pool id> --lab <name> --evidence <url> [--root <dir>]

Prints one JSON object. ``check``: every idea cited and both concept trees whole
gives ``{"ok": true, ...}`` and exit 0. An idea owes citations or a tree owes a
node: ``{"ok": false, "error": "SOTA_CITATIONS_OWED", "owed": [{"key",
"problems"}], "trees": [...], ...}`` and exit 1. It writes nothing.

``rank`` writes ``sota-pool/journal-ranks.json``: for each pool reference with a
DOI, its Crossref work type, ISSNs and issued year, and its quartile in the SJR
table (``--sjr``, else the newest CSV imported with ``journal_cli.py sjr-import``).
A preprint is looked up in OpenAlex for an author of an accepted lab, and one of
no accepted lab is reported as skipped. A reference that does not answer is
reported as unresolved and keeps the rank it had, so an outage never erases earlier
ranks; a reference that never had a rank does not pass the journal rule.

``lab`` records the operator's confirmation that a pool preprint comes from an
accepted lab, for the papers whose affiliations OpenAlex lacks. Only the operator
decides it, with a link that shows the affiliation; ``rank`` keeps it.
"""

from __future__ import annotations

import argparse
import http.client
import importlib.util
import json
import os
import re
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
HTTP_TIMEOUT = 15
OPENALEX_WORKS = "https://api.openalex.org/works/doi:10.48550/arxiv."


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
               f"in {citations.CITATIONS_REL}")
    if state["trees"]:
        message += f"; {len(state['trees'])} concept tree finding(s)"
    return _emit({"ok": False, "error": "SOTA_CITATIONS_OWED", "message": message, **summary}, 1)


def _routes(root: Path) -> int:
    """Which ideas each pool reference is cited for, with the quote each takes."""
    if not root.is_dir():
        return _emit({"ok": False, "error": "ROOT_ABSENT", "message": f"{root} is not a directory"}, 1)
    found = citations.state(root)["routes"]
    return _emit({"ok": True, "routes": found, "uncited": [route["id"] for route in found if not route["ideas"]]})


def _crossref(doi: str) -> dict[str, Any] | None:
    """A DOI's work type, ISSNs and issued year, ``None`` when Crossref does not answer."""
    request = urllib.request.Request(CROSSREF_WORKS + urllib.parse.quote(doi, safe=""),
                                     headers={"User-Agent": "papersmith-ai"})
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
            message = json.load(response)["message"]
        parts = (message.get("issued") or {}).get("date-parts") or [[None]]
        return {"type": message.get("type"), "issn": message.get("ISSN") or [], "year": parts[0][0]}
    except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError, http.client.HTTPException):
        return None


def _openalex_institutions(arxiv_id: str) -> dict[str, Any] | None:
    """The ROR ids of a preprint's authors and its year, ``None`` when OpenAlex does not answer."""
    url = OPENALEX_WORKS + urllib.parse.quote(arxiv_id, safe="") + "?select=publication_year,authorships"
    request = urllib.request.Request(url, headers={"User-Agent": "papersmith-ai"})
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
            work = json.load(response)
        rors = [(item.get("ror") or "").rsplit("/", 1)[-1] for author in work.get("authorships") or []
                for item in author.get("institutions") or []]
        return {"rors": rors, "year": work.get("publication_year")}
    except (OSError, ValueError, KeyError, TypeError, AttributeError, http.client.HTTPException):
        return None


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
    previous = citations._ranks(root)
    ranks: dict[str, dict[str, Any]] = {}
    skipped: list[str] = []
    unresolved: list[str] = []
    ranked = 0
    for identity, record in citations._pool(root).items():
        identifier = record["identifier"]
        known = previous.get(identity)
        if known and known.get("lab_source") == "operator":
            ranks[identifier] = known
            ranked += 1
            continue
        if identity.startswith("arxiv:"):
            found = _openalex_institutions(re.sub(r"v\d+$", "", identity.removeprefix("arxiv:")))
            if found is None:
                unresolved.append(identifier)
                if known:
                    ranks[identifier] = known
                continue
            lab = next((citations.ACCEPTED_LABS[ror] for ror in found["rors"] if ror in citations.ACCEPTED_LABS), None)
            ranks[identifier] = {"work_type": "preprint", "quartile": None, "quartile_source": "unknown",
                                 "year": found["year"], "lab": lab, "lab_source": "openalex" if lab else None}
            if lab:
                ranked += 1
            else:
                skipped.append(identifier)
            continue
        if not identity.startswith("doi:"):
            skipped.append(identifier)
            continue
        work = _crossref(identity.removeprefix("doi:"))
        if work is None:
            unresolved.append(identifier)
            if known:
                ranks[identifier] = known
            continue
        hit = table.lookup(work["issn"]) or {}
        quartile = hit.get("quartile")
        ranks[identifier] = {"work_type": work["type"], "issn": work["issn"], "year": work["year"],
                             "quartile": quartile, "quartile_source": "sjr" if quartile else "unknown",
                             "sjr_year": sjr_year}
        ranked += 1
    _write_atomic(root / citations.RANKS_REL, {"schema": citations.SCHEMA, "ranks": ranks})
    return _emit({"ok": True, "ranked": ranked, "skipped": skipped, "unresolved": unresolved,
                  "written": citations.RANKS_REL})


def _confirm_lab(root: Path, identifier: str, lab: str, evidence: str) -> int:
    """Record the operator's confirmation of a preprint's lab."""
    if not root.is_dir():
        return _emit({"ok": False, "error": "ROOT_ABSENT", "message": f"{root} is not a directory"}, 1)
    root = root.expanduser().resolve()
    accepted = sorted(set(citations.ACCEPTED_LABS.values()))
    if lab not in accepted:
        return _emit({"ok": False, "error": "LAB_NOT_ACCEPTED", "message": f"{lab!r} is not one of {accepted}"}, 1)
    if not evidence.strip():
        return _emit({"ok": False, "error": "EVIDENCE_REQUIRED", "message": "--evidence must link the affiliation"}, 1)
    identity = citations.normalize(identifier)
    record = citations._pool(root).get(identity)
    if record is None:
        return _emit({"ok": False, "error": "NOT_IN_POOL", "message": f"{identifier!r} is not in {citations.POOL_REL}"}, 1)
    if not identity.startswith("arxiv:"):
        return _emit({"ok": False, "error": "NOT_A_PREPRINT",
                      "message": f"{identifier!r} has a DOI: its journal rank decides, not a lab"}, 1)
    if citations._year(record.get("year")) is None:
        return _emit({"ok": False, "error": "YEAR_UNKNOWN", "message": f"{identifier!r} has no year in the pool"}, 1)
    path = root / citations.RANKS_REL
    data = citations._json(path, root, citations.MAX_POOL_BYTES) if path.exists() else {"ranks": {}}
    ranks = data.get("ranks") if isinstance(data, dict) else None
    if not isinstance(ranks, dict):
        return _emit({"ok": False, "error": "RANKS_UNREADABLE", "message": f"{citations.RANKS_REL} cannot be read"}, 1)
    ranks[record["identifier"]] = {"work_type": "preprint", "quartile": None, "quartile_source": "unknown",
                                   "year": record.get("year"), "lab": lab, "lab_source": "operator",
                                   "evidence": evidence.strip()}
    _write_atomic(root / citations.RANKS_REL, {"schema": citations.SCHEMA, "ranks": ranks})
    return _emit({"ok": True, "id": record["identifier"], "lab": lab, "written": citations.RANKS_REL})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="citations_cli.py", description="SOTA citations of each idea")
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="Say which ideas still owe their citations")
    check.add_argument("--root", default=".", help="Workspace root (default: current dir)")
    routes = sub.add_parser("routes", help="List the ideas each pool reference is cited for, and the uncited ones")
    routes.add_argument("--root", default=".", help="Workspace root (default: current dir)")
    rank = sub.add_parser("rank", help="Record each pool reference's work type and SJR quartile")
    rank.add_argument("--root", default=".", help="Workspace root (default: current dir)")
    rank.add_argument("--sjr", help="SJR CSV (default: the newest imported table)")
    lab = sub.add_parser("lab", help="Record the operator's confirmation of a preprint's lab")
    lab.add_argument("--root", default=".", help="Workspace root (default: current dir)")
    lab.add_argument("--id", required=True, help="Pool identifier of the preprint")
    lab.add_argument("--lab", required=True, help="An accepted lab, as citations.ACCEPTED_LABS names it")
    lab.add_argument("--evidence", required=True, help="Link that shows the affiliation")
    args = parser.parse_args(argv)
    if args.command == "lab":
        return _confirm_lab(Path(args.root), args.id, args.lab, args.evidence)
    if args.command == "routes":
        return _routes(Path(args.root))
    return _rank(Path(args.root), args.sjr) if args.command == "rank" else _check(Path(args.root))


if __name__ == "__main__":
    raise SystemExit(main())
