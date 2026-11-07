"""The papers a manuscript cites, as one searchable list.

``cited_papers(root)`` answers ``GET /api/atlas/cited-papers``. It is a pure
read of what the workspace already holds, and every input is optional, so it
works at any phase of any paper:

* ``paper/main.tex``: which keys are cited (``paper_bib.cited_keys`` over the
  text outside ``%`` comments, so a commented-out citation is not one), in
  which sections and how often;
* ``paper/refs.bib``: the metadata. ``paper_bib.parse_bib`` reads what exporters
  really write (whole entries on one line, multi-line values, quotes,
  parentheses, any field case, ``@string`` macros);
* ``sota-pool/candidates.json``: fills the gaps of a paper it holds, joined by
  identifier and then by a title only one candidate carries; the bib wins;
* ``paper/.paper-writing/references.json``: what ``resolve --references``
  retrieved, the last fallback for a title, year, venue, abstract or link;
* ``paper/.paper-writing/evidence/``: the claims each paper supports;
* ``.papersmith/citations.json``: the ideas each paper justifies;
* ``atlas_manuscript.cited_systems``: the id of the paper's node in the
  manuscript graph.

A manuscript whose ``\\cite`` commands ``paper_bib`` does not recognize yields
no key; then, as without a ``main.tex``, the bibliography's entries are listed
and ``cite_source`` says so. Nothing is invented: an absent value stays absent,
and a cited key with no bib entry stays in the list with ``has_entry`` false.
An unreadable input is a ``warnings`` item (``{"code", "detail"}``), never an
exception, and a paper that cannot be assembled stays listed by its key with a
``paper`` warning. Only ``http`` and ``https`` links are offered, because a bib entry's
``url`` is free text the dashboard renders.

Stdlib only, plus the workspace's ``paper_bib`` and ``paper_evidence`` through
``atlas_manuscript``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, urlsplit

from . import atlas_manuscript
from .paper_clusters import cluster_papers

SCHEMA = "papersmith.cited-papers/v1"
CITATIONS_REL = ".papersmith/citations.json"
ABSTRACT_MAX = 4000
CLAIM_MAX = 600

_SECTION = r"\\section\*?\s*\{((?:[^{}]|\{[^{}]*\})*)\}"
_COMMENT_RE = re.compile(r"(?<!\\)%.*")
_YEAR_RE = re.compile(r"\b(\d{4})\b")


# --------------------------------------------------------------------------
# BibTeX: the parser and the text cleaner are `paper_bib`'s, shared with the
# manuscript layer; these names stay so a caller of this module keeps working.
# --------------------------------------------------------------------------
def parse_bib(text: str) -> dict[str, dict[str, str]]:
    return atlas_manuscript._paper_modules()[0].parse_bib(text)


def plain_text(value: Any) -> str:
    return atlas_manuscript._paper_modules()[0].plain_text(value)


def _split_top(value: str, separator: re.Pattern) -> list[str]:
    """``value`` cut at each ``separator`` outside braces."""
    parts, depth, last, index = [], 0, 0, 0
    while index < len(value):
        char = value[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        elif depth == 0:
            match = separator.match(value, index)
            if match is not None:
                parts.append(value[last:index])
                index = last = match.end()
                continue
        index += 1
    parts.append(value[last:])
    return parts


def _authors(raw: Any) -> list[str]:
    if not isinstance(raw, str):
        return []
    names = []
    for name in _split_top(raw, re.compile(r"\s+and\s+", re.IGNORECASE)):
        pieces = [plain_text(p) for p in _split_top(name, re.compile(","))]
        if pieces == ["others"]:
            continue
        names.append(f"{pieces[1]} {pieces[0]}" if len(pieces) == 2 else ", ".join(p for p in pieces if p))
    return [n.strip() for n in names if n.strip()]


def _keywords(raw: Any) -> list[str]:
    return [k for k in (plain_text(p) for p in re.split(r"[,;]", raw))
            if k] if isinstance(raw, str) else []


# --------------------------------------------------------------------------
# joins
# --------------------------------------------------------------------------
def _web_link(value: Any) -> str | None:
    text = value.strip() if isinstance(value, str) else ""
    try:
        parts = urlsplit(text)
    except ValueError:
        return None
    return text if parts.scheme in ("http", "https") and parts.netloc else None


def _identifier_link(identifier: str, resolver: str) -> str | None:
    if resolver == "crossref":
        doi = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:)", "", identifier.strip(), flags=re.IGNORECASE)
        return f"https://doi.org/{quote(doi, safe='/:;()._-')}" if doi else None
    if resolver == "arxiv":
        return f"https://arxiv.org/abs/{quote(identifier.strip(), safe='/.-')}"
    return None


def _candidate_link(candidate: dict) -> str | None:
    for field in ("source_url", "url"):
        link = _web_link(candidate.get(field))
        if link:
            return link
    identifier, resolver = candidate.get("identifier"), candidate.get("resolver")
    if not isinstance(identifier, str):
        return None
    return (_web_link(identifier) or _identifier_link(identifier, str(resolver or ""))
            or (_identifier_link(identifier, "crossref") if identifier.lower().startswith("10.") else None))


def _link(fields: dict[str, str], candidate: dict | None) -> str | None:
    for identifier, resolver in atlas_manuscript._bib_identifiers(fields):
        link = _identifier_link(identifier, resolver)
        if link:
            return link
    return _web_link(fields.get("url")) or (_candidate_link(candidate) if candidate else None)


def _candidate_keys(paper_bib: Any, candidate: dict) -> set[str]:
    keys = atlas_manuscript._keys(paper_bib, candidate.get("identifier"), candidate.get("resolver"))
    keys |= atlas_manuscript._keys(paper_bib, candidate.get("source_url"))
    keys |= atlas_manuscript._keys(paper_bib, candidate.get("url"))
    return keys


def _match_candidate(paper_bib: Any, keys: set[str], title: str, candidates: list[dict]) -> dict | None:
    """The pool candidate a paper is: by identifier, else by a title only one holds."""
    for candidate in candidates:
        if keys & _candidate_keys(paper_bib, candidate):
            return candidate
    wanted = atlas_manuscript._title_key(title)
    owners = [c for c in candidates if wanted and atlas_manuscript._title_key(c.get("title")) == wanted]
    return owners[0] if len(owners) == 1 else None


def _candidate_authors(candidate: dict | None) -> list[str]:
    authors = (candidate or {}).get("authors")
    if isinstance(authors, str):
        return [authors.strip()] if authors.strip() else []
    return [str(a).strip() for a in authors if str(a).strip()] if isinstance(authors, list) else []


def _citations_in_order(paper_bib: Any, text: str) -> tuple[dict[str, dict[str, int]], list[str], list[list[str]]]:
    """``({key: {section: count}}, keys in first-citation order, the keys of each
    citation command)`` of a text outside comments. Citations before the first
    ``\\section`` count under an empty section title."""
    counts: dict[str, dict[str, int]] = {}
    order: list[str] = []
    cocited: list[list[str]] = []
    section = ""
    for match in re.finditer(f"{_SECTION}|{paper_bib._CITE_RE.pattern}", text):
        if match.group(2) is None:
            section = plain_text(match.group(1))
            continue
        keys = [k.strip() for k in match.group(2).split(",") if k.strip()]
        cocited.append(keys)
        for key in keys:
            if key not in counts:
                order.append(key)
            sections = counts.setdefault(key, {})
            sections[section] = sections.get(section, 0) + 1
    return counts, order, cocited


def _graph_nodes(root: Path, paper_dir: Path | str | None) -> dict[str, str]:
    """``{cite_key: manuscript graph node id}``, as ``manuscript_graph._sota`` names them."""
    joined = atlas_manuscript.cited_systems(root, paper_dir=paper_dir)
    nodes = {key: f"sota:{system['id']}" for system in joined["systems"] if system["cited"]
             for key in system["cite_keys"]}
    nodes.update({paper["cite_key"]: f"sota:cite:{paper['cite_key']}" for paper in joined["extra_systems"]})
    return nodes


def _idea_entries(root: Path) -> list[tuple[str, str, str]]:
    """``(idea, reference id, why)`` for every entry of the citations file."""
    raw = atlas_manuscript._read(root / CITATIONS_REL)
    data = json.loads(raw.decode("utf-8")) if raw else {}
    ideas = data.get("ideas") if isinstance(data, dict) else None
    if not isinstance(ideas, dict):
        return []
    return [(str(idea), str(item.get("id") or ""), str(item.get("why") or ""))
            for idea, items in sorted(ideas.items()) if isinstance(items, list)
            for item in items if isinstance(item, dict)]


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


# --------------------------------------------------------------------------
# public API
# --------------------------------------------------------------------------
def cited_papers(root: Path | str, *, paper_dir: Path | str | None = None) -> dict[str, Any]:
    """Every cited paper; see the module docstring. Never raises."""
    root = Path(root).expanduser().resolve()
    paper = atlas_manuscript._paper_dir(root, paper_dir)
    warnings: list[dict[str, str]] = []

    def attempt(code: str, read: Callable[[], Any], default: Any) -> Any:
        try:
            return read()
        except Exception as exc:  # noqa: BLE001 - one bad input never hides the rest
            warnings.append({"code": code, "detail": f"{type(exc).__name__}: {exc}"[:300]})
            return default

    modules = attempt("modules", atlas_manuscript._paper_modules, None)
    if modules is None:
        return _answer("none", [], warnings)
    paper_bib, paper_evidence = modules

    tex = attempt("manuscript", lambda: atlas_manuscript._read(paper / "main.tex"), None)
    refs = attempt("bibliography", lambda: atlas_manuscript._read(paper / "refs.bib"), None)
    bib = attempt("bibliography", lambda: parse_bib(refs.decode("utf-8", errors="replace")), {}) if refs else {}
    text = _COMMENT_RE.sub("", tex.decode("utf-8", errors="replace")) if tex else ""
    cited = paper_bib.cited_keys(text.encode("utf-8"))
    source = "main.tex" if cited else ("refs.bib" if bib else ("main.tex" if tex is not None else "none"))
    if not cited:
        cited = set(bib)

    candidates = attempt("pool", lambda: _pool(root), [])
    nodes = attempt("graph", lambda: _graph_nodes(root, paper_dir), {})
    ideas = attempt("ideas", lambda: _idea_entries(root), [])
    references = attempt("references", lambda: paper_bib.read_references(paper), {})
    records = attempt("evidence", lambda: paper_evidence.read_all_records(paper) if paper.is_dir() else [], [])
    claims: dict[str, list[dict]] = {}
    for record in records:
        key = record.get("cite_key") if isinstance(record, dict) else None
        if isinstance(key, str) and key in cited:
            claims.setdefault(key, []).append(record)

    counts, order, cocited = attempt("manuscript", lambda: _citations_in_order(paper_bib, text), ({}, [], []))
    ranked = order + sorted(cited - set(order))
    papers = []
    for position, key in enumerate(k for k in ranked if k in cited):
        entry = bib.get(key)
        papers.append(attempt(
            "paper",
            lambda: _paper(paper_bib, key, entry, claims.get(key, []), counts.get(key, {}), candidates,
                           ideas, nodes.get(key), position, references.get(key)),
            _bare_paper(key, entry, position)))
    return _answer(source, papers, warnings, cocited)


def _pool(root: Path) -> list[dict]:
    raw = atlas_manuscript._read(root / "sota-pool" / "candidates.json")
    return atlas_manuscript._candidate_list(json.loads(raw.decode("utf-8"))) if raw else []


def _paper(paper_bib: Any, key: str, entry: dict[str, str] | None, records: list[dict],
           sections: dict[str, int], candidates: list[dict], ideas: list[tuple[str, str, str]],
           node_id: str | None, position: int, reference: dict | None = None) -> dict[str, Any]:
    fields = paper_bib.identity_fields(entry or {})
    title = plain_text((entry or {}).get("title"))
    keys = atlas_manuscript._bib_keys(paper_bib, fields)
    for record in records:
        keys |= atlas_manuscript._keys(paper_bib, record.get("identifier"), record.get("resolver"))
    candidate = _match_candidate(paper_bib, keys, title, candidates)
    if candidate:
        keys |= _candidate_keys(paper_bib, candidate)
    pool = candidate or {}
    bib = entry or {}
    venue = next((plain_text(bib[f]) for f in ("journal", "journaltitle", "booktitle") if bib.get(f)), "")
    year = _YEAR_RE.search(plain_text(bib.get("year") or bib.get("date")))
    side = reference if reference and reference.get("status") == "resolved" else {}
    fallback_year = pool.get("year") or side.get("year")
    fallback_title = pool.get("title") or side.get("title")
    fallback_venue = pool.get("venue") or side.get("venue")
    fallback_abstract = pool.get("abstract") or side.get("abstract")
    return {
        **_bare_paper(key, entry, position),
        "type": bib.get("_type"),
        "title": title or (str(fallback_title) if fallback_title else None),
        "authors": _authors(bib.get("author") or bib.get("editor")) or _candidate_authors(candidate),
        "year": year.group(1) if year else (str(fallback_year) if fallback_year else None),
        "venue": venue or (str(fallback_venue) if fallback_venue else None),
        "abstract": _clip(plain_text(bib.get("abstract")) or str(fallback_abstract or ""), ABSTRACT_MAX) or None,
        "keywords": _keywords(bib.get("keywords")),
        "link": _link(fields, candidate) or _web_link(side.get("link")),
        "family": str(pool["family"]) if pool.get("family") else None,
        "in_pool": candidate is not None,
        "cites": sum(sections.values()),
        "sections": [{"title": title_, "count": count} for title_, count in sections.items()],
        "claims": [{"block": c["block"], "claim": _clip(c["claim"], CLAIM_MAX), "verdict": c["verdict"]}
                   for c in atlas_manuscript._claims(records)],
        "ideas": [{"idea": idea, "why": why} for idea, reference, why in ideas
                  if keys & atlas_manuscript._keys(paper_bib, reference, "crossref" if reference.startswith("10.") else None)],
        "node_id": node_id,
    }


def _bare_paper(key: str, entry: dict[str, str] | None, position: int) -> dict[str, Any]:
    """A paper's shape with nothing joined: all a key alone can say."""
    return {"key": key, "has_entry": entry is not None, "type": None, "title": None, "authors": [],
            "year": None, "venue": None, "abstract": None, "keywords": [], "link": None, "family": None,
            "in_pool": False, "order": position, "cites": 0, "sections": [], "claims": [], "ideas": [],
            "node_id": None}


def _answer(source: str, papers: list[dict], warnings: list[dict],
            cocited: list[list[str]] | None = None) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "cite_source": source,
        "papers": papers,
        "summary": {
            "total": len(papers),
            "in_pool": sum(1 for p in papers if p["in_pool"]),
            "with_link": sum(1 for p in papers if p["link"]),
            "with_abstract": sum(1 for p in papers if p["abstract"]),
            "missing_entries": sorted(p["key"] for p in papers if not p["has_entry"]),
        },
        "clusters": cluster_papers(papers, cocited),
        "warnings": warnings,
    }
