"""The papers a manuscript cites, as one searchable list.

``cited_papers(root)`` answers ``GET /api/atlas/cited-papers``. It is a pure
read of what the workspace already holds, and every input is optional, so it
works at any phase of any paper:

* ``paper/main.tex``: which keys are cited (``paper_bib.cited_keys``, the same
  definition the manuscript graph uses), in which sections and how often;
* ``paper/refs.bib``: the metadata. ``parse_bib`` reads what exporters really
  write (whole entries on one line, multi-line values, quotes, parentheses,
  any field case, ``@string`` macros), which ``atlas_manuscript._bib_fields``
  does not need to;
* ``sota-pool/candidates.json``: fills the gaps of a paper it holds, joined by
  identifier and then by a title only one candidate carries; the bib wins;
* ``paper/.paper-writing/evidence/``: the claims each paper supports;
* ``.papersmith/citations.json``: the ideas each paper justifies;
* ``atlas_manuscript.cited_systems``: the id of the paper's node in the
  manuscript graph.

A manuscript whose ``\\cite`` commands ``paper_bib`` does not recognize yields
no key; then, as without a ``main.tex``, the bibliography's entries are listed
and ``cite_source`` says so. Nothing is invented: an absent value stays absent,
and a cited key with no bib entry stays in the list with ``has_entry`` false.
An unreadable input is a ``warnings`` item (``{"code", "detail"}``), never an
exception. Only ``http`` and ``https`` links are offered, because a bib entry's
``url`` is free text the dashboard renders.

Stdlib only, plus the workspace's ``paper_bib`` and ``paper_evidence`` through
``atlas_manuscript``.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, urlsplit

from . import atlas_manuscript

SCHEMA = "papersmith.cited-papers/v1"
CITATIONS_REL = ".papersmith/citations.json"
ABSTRACT_MAX = 4000
CLAIM_MAX = 600

_ENTRY_RE = re.compile(r"@\s*([A-Za-z]+)\s*([{(])")
_FIELD_RE = re.compile(r"[\s,]*([^\s=,{}()\"#]+)\s*=\s*")
_BARE_RE = re.compile(r"[^\s,#{}()\"]+")
_NEXT_ENTRY_RE = re.compile(r"\n\s*@\s*[A-Za-z]+\s*[{(]")
_NON_ENTRIES = {"comment", "preamble"}

_ACCENTS = {"'": "\u0301", "`": "\u0300", "^": "\u0302", '"': "\u0308", "~": "\u0303",
            "=": "\u0304", ".": "\u0307", "u": "\u0306", "v": "\u030c", "H": "\u030b",
            "c": "\u0327", "k": "\u0328", "r": "\u030a"}
_LETTERS = {"ss": "ß", "ae": "æ", "AE": "Æ", "oe": "œ", "OE": "Œ", "aa": "å", "AA": "Å",
            "o": "ø", "O": "Ø", "l": "ł", "L": "Ł", "i": "ı", "j": "ȷ"}
_MATH_RE = re.compile(r"(?<!\\)\$([^$]*)\$")
_SYMBOL_ACCENT_RE = re.compile(r"\\(['`^\"~=.])\s*\{?\s*(?:\\([ij])(?![A-Za-z])|([A-Za-z]))\s*\}?")
_LETTER_ACCENT_RE = re.compile(
    r"\\([uvHckr])(?:\s*\{\s*(?:\\([ij])(?![A-Za-z])|([A-Za-z]))\s*\}|\s+(?:\\([ij])(?![A-Za-z])|([A-Za-z])))")
_LETTER_RE = re.compile(r"\\(ss|ae|AE|oe|OE|aa|AA|o|O|l|L|i|j)(?![A-Za-z])\s*(?:\{\})?")
_ESCAPED_RE = re.compile(r"\\([&%_#$])")
_COMMAND_RE = re.compile(r"\\[a-zA-Z]+\*?\s*(?:\[[^\]]*\])?")
_SECTION = r"\\section\*?\s*\{((?:[^{}]|\{[^{}]*\})*)\}"
_COMMENT_RE = re.compile(r"(?<!\\)%.*")
_YEAR_RE = re.compile(r"\b(\d{4})\b")


# --------------------------------------------------------------------------
# BibTeX
# --------------------------------------------------------------------------
def _balanced_end(text: str, start: int) -> int:
    """Index of the delimiter closing the one at ``start``, or -1."""
    opening = text[start]
    closing = "}" if opening == "{" else ")"
    depth, index = 0, start
    while index < len(text):
        char = text[index]
        if char == "\\":
            index += 2
            continue
        if char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return -1


def _quoted_end(text: str, start: int) -> int:
    depth, index = 0, start + 1
    while index < len(text):
        char = text[index]
        if char == "\\":
            index += 2
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        elif char == '"' and depth == 0:
            return index
        index += 1
    return -1


def _value(body: str, pos: int, macros: dict[str, str]) -> tuple[str | None, int]:
    """One field value, ``#`` concatenation included, and where it ended."""
    parts: list[str] = []
    while True:
        while pos < len(body) and body[pos].isspace():
            pos += 1
        char = body[pos] if pos < len(body) else ""
        if char == "{" or char == '"':
            end = _balanced_end(body, pos) if char == "{" else _quoted_end(body, pos)
            if end < 0:
                return None, len(body)
            parts.append(body[pos + 1:end])
            pos = end + 1
        else:
            bare = _BARE_RE.match(body, pos)
            if bare is None:
                return None, len(body)
            parts.append(macros.get(bare.group(0).lower(), bare.group(0)))
            pos = bare.end()
        while pos < len(body) and body[pos].isspace():
            pos += 1
        if pos >= len(body) or body[pos] != "#":
            return "".join(parts), pos
        pos += 1


def _fields(body: str, macros: dict[str, str]) -> dict[str, str]:
    fields: dict[str, str] = {}
    pos = 0
    while True:
        match = _FIELD_RE.match(body, pos)
        if match is None:
            return fields
        value, pos = _value(body, match.end(), macros)
        if value is None:
            return fields
        fields.setdefault(match.group(1).lower(), value)


def parse_bib(text: str) -> dict[str, dict[str, str]]:
    """``{cite_key: {field: raw value, "_type": entry type}}``, field names
    lower-cased, the first of two entries with one key kept. An unterminated
    entry ends where the next one starts."""
    entries: dict[str, dict[str, str]] = {}
    macros: dict[str, str] = {}
    pos = 0
    while True:
        head = _ENTRY_RE.search(text, pos)
        if head is None:
            return entries
        kind, start = head.group(1).lower(), head.end() - 1
        end = _balanced_end(text, start)
        if end < 0:
            following = _NEXT_ENTRY_RE.search(text, start)
            end = following.start() if following else len(text)
        body, pos = text[start + 1:end], end + 1
        if kind in _NON_ENTRIES:
            continue
        if kind == "string":
            macros.update(_fields(body, macros))
            continue
        key, comma, rest = body.partition(",")
        key = key.strip()
        if key and comma:
            entries.setdefault(key, {**_fields(rest, macros), "_type": kind})


def _accent(mark: str, dotless: str | None, letter: str | None) -> str:
    base = dotless or letter or ""
    return unicodedata.normalize("NFC", base + _ACCENTS[mark])


def plain_text(value: Any) -> str:
    """A BibTeX value as readable text. Accents and symbols become Unicode, and
    formatting commands and protective braces go. A math span loses only its
    dollars, because its commands have no plain form."""
    if not isinstance(value, str):
        return ""
    math: list[str] = []

    def hold(match: re.Match) -> str:
        math.append(match.group(1))
        return f"\0{len(math) - 1}\0"

    text = _MATH_RE.sub(hold, value)
    text = _SYMBOL_ACCENT_RE.sub(lambda m: _accent(m.group(1), m.group(2), m.group(3)), text)
    text = _LETTER_ACCENT_RE.sub(
        lambda m: _accent(m.group(1), m.group(2) or m.group(4), m.group(3) or m.group(5)), text)
    text = _LETTER_RE.sub(lambda m: _LETTERS[m.group(1)], text)
    text = _ESCAPED_RE.sub(r"\1", text)
    text = _COMMAND_RE.sub("", text)
    text = text.replace("---", "—").replace("--", "–").replace("``", "“").replace("''", "”")
    text = text.replace("~", " ").replace("{", "").replace("}", "").replace("\\", "")
    text = re.sub(r"\0(\d+)\0", lambda m: math[int(m.group(1))], text)
    return unicodedata.normalize("NFC", " ".join(text.split()))


def _literal(value: Any) -> str:
    """An identifier or URL: braces and escapes go, every other byte stays."""
    if not isinstance(value, str):
        return ""
    return "".join(_ESCAPED_RE.sub(r"\1", value).replace("{", "").replace("}", "").split())


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


def _identity_fields(entry: dict[str, str]) -> dict[str, str]:
    """The shape ``atlas_manuscript``'s identity helpers read."""
    fields = {name: _literal(entry.get(name)) for name in ("doi", "eprint", "archiveprefix", "url")}
    fields.update({name: plain_text(entry.get(name)) for name in ("journal", "note", "howpublished")})
    return fields


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


def _citations_in_order(paper_bib: Any, tex: bytes | None) -> tuple[dict[str, dict[str, int]], list[str]]:
    """``({key: {section: count}}, keys in first-citation order)``. Citations
    before the first ``\\section`` count under an empty section title."""
    counts: dict[str, dict[str, int]] = {}
    order: list[str] = []
    if tex is None:
        return counts, order
    text = _COMMENT_RE.sub("", tex.decode("utf-8", errors="replace"))
    section = ""
    for match in re.finditer(f"{_SECTION}|{paper_bib._CITE_RE.pattern}", text):
        if match.group(2) is None:
            section = plain_text(match.group(1))
            continue
        for key in (k.strip() for k in match.group(2).split(",")):
            if not key:
                continue
            if key not in counts:
                order.append(key)
            sections = counts.setdefault(key, {})
            sections[section] = sections.get(section, 0) + 1
    return counts, order


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
    bib = parse_bib(refs.decode("utf-8", errors="replace")) if refs else {}
    cited = paper_bib.cited_keys(tex) if tex else set()
    source = "main.tex" if cited else ("refs.bib" if bib else ("main.tex" if tex is not None else "none"))
    if not cited:
        cited = set(bib)

    candidates = attempt("pool", lambda: _pool(root), [])
    nodes = attempt("graph", lambda: _graph_nodes(root, paper_dir), {})
    ideas = attempt("ideas", lambda: _idea_entries(root), [])
    records = attempt("evidence", lambda: paper_evidence.read_all_records(paper) if paper.is_dir() else [], [])
    claims: dict[str, list[dict]] = {}
    for record in records:
        if isinstance(record, dict) and record.get("cite_key") in cited:
            claims.setdefault(record["cite_key"], []).append(record)

    counts, order = _citations_in_order(paper_bib, tex)
    ranked = order + sorted(cited - set(order))
    papers = [_paper(paper_bib, key, bib.get(key), claims.get(key, []), counts.get(key, {}), candidates,
                     ideas, nodes.get(key), position) for position, key in enumerate(k for k in ranked if k in cited)]
    return _answer(source, papers, warnings)


def _pool(root: Path) -> list[dict]:
    raw = atlas_manuscript._read(root / "sota-pool" / "candidates.json")
    return atlas_manuscript._candidate_list(json.loads(raw.decode("utf-8"))) if raw else []


def _paper(paper_bib: Any, key: str, entry: dict[str, str] | None, records: list[dict],
           sections: dict[str, int], candidates: list[dict], ideas: list[tuple[str, str, str]],
           node_id: str | None, position: int) -> dict[str, Any]:
    fields = _identity_fields(entry or {})
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
    pool_year = pool.get("year")
    return {
        "key": key,
        "has_entry": entry is not None,
        "type": bib.get("_type"),
        "title": title or (str(pool["title"]) if pool.get("title") else None),
        "authors": _authors(bib.get("author") or bib.get("editor")) or _candidate_authors(candidate),
        "year": year.group(1) if year else (str(pool_year) if pool_year else None),
        "venue": venue or (str(pool["venue"]) if pool.get("venue") else None),
        "abstract": _clip(plain_text(bib.get("abstract")) or str(pool.get("abstract") or ""), ABSTRACT_MAX) or None,
        "keywords": _keywords(bib.get("keywords")),
        "link": _link(fields, candidate),
        "family": str(pool["family"]) if pool.get("family") else None,
        "in_pool": candidate is not None,
        "order": position,
        "cites": sum(sections.values()),
        "sections": [{"title": title_, "count": count} for title_, count in sections.items()],
        "claims": [{"block": c["block"], "claim": _clip(c["claim"], CLAIM_MAX), "verdict": c["verdict"]}
                   for c in atlas_manuscript._claims(records)],
        "ideas": [{"idea": idea, "why": why} for idea, reference, why in ideas
                  if keys & atlas_manuscript._keys(paper_bib, reference, "crossref" if reference.startswith("10.") else None)],
        "node_id": node_id,
    }


def _answer(source: str, papers: list[dict], warnings: list[dict]) -> dict[str, Any]:
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
        "warnings": warnings,
    }
