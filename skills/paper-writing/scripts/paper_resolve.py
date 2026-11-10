"""paper_resolve: stdlib-only `urllib` client for citation resolution and
metadata retrieval against OpenAlex, Crossref and arXiv. Keyless -- OpenAlex's
documented "polite pool" identity is a `mailto` contact, sourced from
`papersmith.yaml`'s `paper_writing.contact`, never a secret and never
hardcoded (`literature-search`, Requirement: Resolution Runs Through the CLI
Over Stdlib `urllib`). At most one retry, fixed 1s, only on transport error /
429 / 5xx, never on 404 (`design.md`, Decision 3).

This is also the one path that makes `paper-writing`'s CLI **not** offline
end to end (`proposal.md`, Approach) -- every call sits behind a role
`papersmith.yaml` can empty, and an unreachable endpoint is a named refusal,
never a silent empty result.

Public surface:

    OPENER                                    -- module-level urllib seam
    load_config(path=None)                    -> dict
    connectors_for_role(config, role)         -> list[str]
    require_role_connectors(config, role)     -> list[str]  (raises RESOLVER_ROLE_EMPTY / DISCOVERY_UNAVAILABLE)
    resolve_identifier(identifier, *, resolver, role, config) -> dict
    search_title(title, *, role, config)      -> list[dict]
    pause()                                   -- the wait before each request of a batch
    fetch_bytes(url, *, config)                -> bytes
    cache_metadata(paper_dir, result)         -> dict
    cache_metadata_in(directory, result)      -> dict
    read_cached_metadata(paper_dir, digest)   -> dict | None
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paper_scaffold  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_core" / "implementation"))
from impl_refusals import Refused  # noqa: E402

#: Test seam (`design.md`, Decision 3, "Test seam"). Every outbound request
#: goes through this exact object; a test installs an opener whose `.open()`
#: raises `urllib.error.URLError` to prove the offline refusal path with no
#: live network call -- and switching it back proves the guard is load-
#: bearing rather than merely present.
OPENER: urllib.request.OpenerDirector = urllib.request.build_opener()

#: The connectors this CLI resolves against, closed for what an
#: identifier's own scheme demands, never for what any one paper is about:
#: OpenAlex and Crossref resolve a DOI, arXiv resolves its own id space, and
#: Semantic Scholar (Graph API, keyless public pool) resolves either a DOI
#: or an arXiv id with cross-source external ids -- together they cover every
#: identifier `resolve` accepts today. Widening this set is a module change
#: made when a new identifier scheme needs a client, never a per-paper
#: decision (`proposal.md`, Approach).
RESOLVERS: tuple[str, ...] = ("openalex", "crossref", "arxiv", "semantic-scholar")

#: The connector roles `papersmith.yaml`'s `paper_writing.roles` maps.
#: `discovery` is read by this module only to validate configuration --
#: the actual discovery search never runs here, it runs through the agent's
#: MCP (`literature-search`, Requirement: Discovery Runs Through the Agent's
#: MCP).
ROLES: tuple[str, ...] = ("discovery", "resolution", "full-text")

_RETRY_DELAY_SECONDS = 1
_TIMEOUT_SECONDS = 10
#: The wait before each request of a batch: `resolve_identifier` has no rate
#: limiter of its own, and one call per cited paper must stay polite.
_REQUEST_PAUSE_SECONDS = 0.2
_TITLE_SEARCH_RESULTS = 10

_CONFIG_PATH = paper_scaffold.FORGE_ROOT / "papersmith.yaml"

_COMMENT_RE = re.compile(r"(?<!['\"])#.*$")


class _Unreachable(Exception):
    """Transport failure, or the retry budget is exhausted."""


class _NoSuchWork(Exception):
    """The endpoint answered, but names no matching work."""


# --- a minimal YAML-subset reader -------------------------------------
#
# `papersmith.yaml` stays readable by a human editor with comments, so this
# is deliberately NOT a general YAML parser (no flow style, no anchors, no
# multi-document streams) -- only what this repository's own config file
# ever uses: nested mappings, scalar strings, and block lists of scalar
# strings, indentation-delimited. `paper-writing` stays stdlib-only
# end to end (`SKILL.md`); pulling in a YAML library for one small,
# self-authored config block would cost the "no third-party dependency"
# property for the whole skill just to read six lines.

def _strip_comment(line: str) -> str:
    return _COMMENT_RE.sub("", line).rstrip()


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _scalar(text: str):
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    return text


def _parse_block(lines: list[str], start: int, indent: int):
    if start < len(lines) and lines[start].lstrip().startswith("- "):
        items = []
        i = start
        while i < len(lines) and _indent(lines[i]) == indent and lines[i].lstrip().startswith("- "):
            items.append(_scalar(lines[i].lstrip()[2:]))
            i += 1
        return items, i

    result: dict = {}
    i = start
    while i < len(lines) and _indent(lines[i]) == indent:
        line = lines[i].strip()
        if ":" not in line:
            raise ValueError(f"expected 'key: value' at: {line!r}")
        key, _, rest = line.partition(":")
        key = key.strip()
        rest = rest.strip()
        if rest == "":
            j = i + 1
            if j < len(lines) and _indent(lines[j]) > indent:
                value, i = _parse_block(lines, j, _indent(lines[j]))
            else:
                value = {}
                i = j
        elif rest == "[]":
            value = []
            i += 1
        else:
            value = _scalar(rest)
            i += 1
        result[key] = value
    return result, i


def parse_yaml_subset(text: str) -> dict:
    """Parses the constrained shape above. Raises `ValueError` on anything
    it does not recognize -- fail closed, never a partial or best-effort
    read of a config file this whole skill trusts."""
    lines = [_strip_comment(raw) for raw in text.splitlines()]
    lines = [ln for ln in lines if ln.strip() != ""]
    if not lines:
        return {}
    value, _ = _parse_block(lines, 0, 0)
    if not isinstance(value, dict):
        raise ValueError("top level of the config must be a mapping")
    return value


def load_config(path: Path | None = None) -> dict:
    """Reads and parses `papersmith.yaml` (or `path`). Refuses
    `PAPERSMITH_CONFIG_UNREADABLE` (work-state) when the file is missing,
    not valid UTF-8, or does not match the constrained shape
    `parse_yaml_subset` understands."""
    target = path if path is not None else _CONFIG_PATH
    if not target.is_file():
        raise Refused("PAPERSMITH_CONFIG_UNREADABLE", f"{target} does not exist")
    try:
        text = target.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise Refused("PAPERSMITH_CONFIG_UNREADABLE", f"{target}: not valid utf-8: {exc}")
    try:
        return parse_yaml_subset(text)
    except ValueError as exc:
        raise Refused("PAPERSMITH_CONFIG_UNREADABLE", f"{target}: {exc}")


def connectors_for_role(config: dict, role: str) -> list:
    if role not in ROLES:
        raise Refused("UNKNOWN_ROLE", f"{role!r} is not one of the declared roles {ROLES}")
    roles_cfg = (config.get("paper_writing") or {}).get("roles") or {}
    connectors = roles_cfg.get(role) or []
    return list(connectors) if isinstance(connectors, list) else [connectors]


def require_role_connectors(config: dict, role: str) -> list:
    """Refuses `DISCOVERY_UNAVAILABLE` for an empty `discovery` role, or
    `RESOLVER_ROLE_EMPTY` for an empty `resolution`/`full-text` role -- two
    different facts sharing no code, because "which role is empty" is part
    of what a caller needs to act on (`design.md`, Decision 3)."""
    connectors = connectors_for_role(config, role)
    if connectors:
        return connectors
    if role == "discovery":
        raise Refused("DISCOVERY_UNAVAILABLE", "no connector is configured for the discovery role")
    raise Refused("RESOLVER_ROLE_EMPTY", f"no connector is configured for the {role!r} role")


def _contact(config: dict) -> str:
    contact = (config.get("paper_writing") or {}).get("contact")
    return contact if isinstance(contact, str) else ""


def _user_agent(config: dict) -> str:
    contact = _contact(config)
    return f"papersmith-ai (mailto:{contact})" if contact else "papersmith-ai"


def _get(url: str, *, config: dict) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": _user_agent(config)})
    attempts = 0
    last_error: object = None
    while attempts < 2:
        attempts += 1
        try:
            with OPENER.open(request, timeout=_TIMEOUT_SECONDS) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise _NoSuchWork(f"{url}: 404")
            if exc.code == 429 or 500 <= exc.code < 600:
                last_error = exc
                if attempts < 2:
                    time.sleep(_RETRY_DELAY_SECONDS)
                    continue
                raise _Unreachable(f"{url}: HTTP {exc.code} after {attempts} attempt(s)")
            raise _NoSuchWork(f"{url}: HTTP {exc.code}")
        except urllib.error.URLError as exc:
            last_error = exc
            if attempts < 2:
                time.sleep(_RETRY_DELAY_SECONDS)
                continue
            raise _Unreachable(f"{url}: {exc.reason} after {attempts} attempt(s)")
    raise _Unreachable(f"{url}: unreachable after {attempts} attempt(s): {last_error}")


def _openalex_url(doi: str, config: dict) -> str:
    base = f"https://api.openalex.org/works/https://doi.org/{urllib.parse.quote(doi, safe='/:;()._-')}"
    contact = _contact(config)
    if contact:
        return base + "?" + urllib.parse.urlencode({"mailto": contact})
    return base


def _crossref_url(doi: str) -> str:
    return f"https://api.crossref.org/works/{urllib.parse.quote(doi, safe='')}"


def _arxiv_url(arxiv_id: str) -> str:
    # Users paste `arXiv:1512.03385`; the API's `id_list` wants the bare
    # id. Measured: with the prefix the feed comes back entry-less (706
    # bytes, no `<entry>`), without it the paper arrives. Strip one
    # case-insensitive `arxiv:` prefix plus surrounding whitespace.
    bare = arxiv_id.strip()
    if bare[:6].lower() == "arxiv:":
        bare = bare[6:].strip()
    return "http://export.arxiv.org/api/query?" + urllib.parse.urlencode({"id_list": bare})


def _semantic_scholar_url(identifier: str, config: dict) -> str:
    """The Semantic Scholar Graph API `paper` endpoint for one identifier.

    Keyless (the public shared pool -- no `mailto`, no `x-api-key`); the
    endpoint takes the identifier prefixed with its own scheme (`DOI:...`,
    `ARXIV:...`), so a bare DOI is treated as one, matching how `resolve`
    passes DOIs to OpenAlex and Crossref. A batch still owes its
    `_REQUEST_PAUSE_SECONDS` between requests, like every other connector.
    """
    bare = identifier.strip()
    if bare[:6].lower() == "arxiv:":
        prefixed = "ARXIV:" + bare[6:].strip()
    elif bare[:4].lower() == "doi:":
        prefixed = "DOI:" + bare[4:].strip()
    else:
        prefixed = "DOI:" + bare
    fields = "title,authors,year,venue,externalIds,abstract,openAccessPdf"
    return ("https://api.semanticscholar.org/graph/v1/paper/"
            + urllib.parse.quote(prefixed, safe=":")
            + "?" + urllib.parse.urlencode({"fields": fields}))


def _parse_semantic_scholar(raw: bytes) -> dict:
    """The same seven fields `_parse_openalex` answers, from the Graph API's
    paper record: `openAccessPdf.url` is a measured open version, never
    inferred (`full-text-fetch`, "Reachability is measured, never assumed")."""
    obj = json.loads(raw)
    authors = []
    for author in obj.get("authors") or []:
        name = ((author or {}).get("name") or "").strip()
        if name:
            authors.append(name)
    return {
        "title": obj.get("title"),
        "doi": (obj.get("externalIds") or {}).get("DOI"),
        "year": obj.get("year"),
        "full_text_url": (obj.get("openAccessPdf") or {}).get("url"),
        "authors": authors,
        "venue": obj.get("venue"),
        "abstract": obj.get("abstract"),
    }


def _parse_openalex(raw: bytes) -> dict:
    obj = json.loads(raw)
    # `full_text_url`: OpenAlex's own measured signal that a real open
    # version exists (`open_access.is_oa`) plus the URL it names
    # (`open_access.oa_url`) -- never inferred from the DOI or title alone.
    # A record with `is_oa: false`, or with no `open_access` object at all,
    # reports `None` here, same as a paywalled Crossref record
    # (`full-text-fetch`, "Reachability is measured, never assumed").
    open_access = obj.get("open_access") or {}
    full_text_url = open_access.get("oa_url") if open_access.get("is_oa") else None
    # `authors`/`venue`: captured because a bibliography entry without them is
    # unusable -- bibtex cannot even sort it ("to sort, need author or key"), and
    # a reference list with no author names cannot be submitted anywhere. They are
    # read off the response actually received, exactly like `full_text_url`, and
    # default to an empty list / None when the record carries none.
    authors = []
    for authorship in obj.get("authorships") or []:
        name = ((authorship.get("author") or {}).get("display_name") or "").strip()
        if name:
            authors.append(name)
    source = ((obj.get("primary_location") or {}).get("source") or {})
    venue = source.get("display_name")
    return {
        "title": obj.get("title"), "doi": obj.get("doi"), "year": obj.get("publication_year"),
        "full_text_url": full_text_url, "authors": authors, "venue": venue,
        "abstract": _deinvert_abstract(obj.get("abstract_inverted_index")),
    }


def _deinvert_abstract(index) -> str | None:
    """Rebuild OpenAlex's position-indexed abstract into reading order.

    The connector returns `{word: [positions]}`, not text. Sorting by
    position is the only faithful reconstruction; joining the dict in wire
    order would scramble the sentence. An absent, empty, or malformed index
    parses to `None`, never to a joined guess — a scout that grades against
    a scrambled abstract would cite word salad as evidence.
    """
    if not isinstance(index, dict) or not index:
        return None
    ordered = []
    for word, positions in index.items():
        if not isinstance(word, str) or not isinstance(positions, list):
            return None
        for position in positions:
            if not isinstance(position, int) or position < 0:
                return None
            ordered.append((position, word))
    if not ordered:
        return None
    ordered.sort()
    return " ".join(word for _, word in ordered)


def _crossref_year(message: dict):
    """The year of Crossref's `issued` date, else of `published`, read off
    the record actually received. Crossref spells a date as
    `{"date-parts": [[year, month?, day?]]}` and an unknown one as
    `[[null]]`; anything that is not an integer year there parses to
    `None`, never to a guess."""
    for field in ("issued", "published"):
        date = message.get(field)
        parts = date.get("date-parts") if isinstance(date, dict) else None
        first = parts[0] if isinstance(parts, list) and parts else None
        year = first[0] if isinstance(first, list) and first else None
        if isinstance(year, int) and not isinstance(year, bool):
            return year
    return None


def _arxiv_year(entry, namespace: dict):
    """The year of the entry's own `<published>` stamp (`YYYY-MM-DDT...`),
    or `None` when the entry carries no readable one."""
    published = entry.find("atom:published", namespace)
    text = (published.text or "").strip() if published is not None else ""
    return int(text[:4]) if len(text) >= 4 and text[:4].isdigit() else None


def _parse_crossref(raw: bytes) -> dict:
    obj = json.loads(raw)
    message = obj.get("message", {})
    titles = message.get("title") or []
    # `full_text_url`: deliberately always `None`. A Crossref `link` entry
    # names a URL and a `content-type`, but neither field says the link is
    # actually open to a keyless fetch -- most point at a publisher wall
    # (`full-text-fetch`, "a bare Crossref DOI usually leads to a publisher
    # wall"). Guessing "probably open" from an unverified content-type would
    # be exactly the assumption this module's whole design refuses to make;
    # a paper resolved through Crossref is always reported unobtainable by
    # this connector, never a coin flip on a link's own unverified label.
    authors = []
    for author in message.get("author") or []:
        name = " ".join(part for part in (author.get("given"), author.get("family")) if part).strip()
        if name:
            authors.append(name)
    containers = message.get("container-title") or []
    # `abstract`: deliberately always `None`. Crossref abstracts arrive as
    # publisher-supplied JATS (`<jats:p>` and friends), not plain text, and
    # stripping tags here would mint a "quote" no source ever printed — the
    # same fabrication this module refuses for reachability above. A scout
    # that needs citable prose resolves through OpenAlex or arXiv instead.
    return {
        "title": titles[0] if titles else None, "doi": message.get("DOI"),
        "year": _crossref_year(message),
        "full_text_url": None, "authors": authors,
        "venue": containers[0] if containers else None, "abstract": None,
    }


def _parse_arxiv(raw: bytes) -> dict:
    namespace = {"atom": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(raw)
    entry = root.find("atom:entry", namespace)
    if entry is None:
        raise _NoSuchWork("arXiv feed carried no <entry>")
    title_el = entry.find("atom:title", namespace)
    title = title_el.text.strip() if title_el is not None and title_el.text else None
    # `abstract`: the entry's own `<summary>`, whitespace-collapsed to one
    # line (arXiv ships it multi-line). Collapsing blank runs is layout, not
    # authorship — the words stay the feed's own, in the feed's own order.
    # Absent summary parses to `None`, never to a title restated as prose.
    summary_el = entry.find("atom:summary", namespace)
    abstract = None
    if summary_el is not None and summary_el.text:
        abstract = " ".join(summary_el.text.split()) or None
    # `full_text_url`: read directly off the entry's own `<link type=
    # "application/pdf">` -- arXiv's Atom feed reports this for every real
    # entry, so this is measured from the response actually received, never
    # constructed from the identifier alone (that would be assuming, not
    # measuring, even though arXiv is definitionally open access).
    full_text_url = None
    for link in entry.findall("atom:link", namespace):
        if link.get("type") == "application/pdf":
            full_text_url = link.get("href")
            break
    authors = []
    for author in entry.findall("atom:author", namespace):
        name_el = author.find("atom:name", namespace)
        if name_el is not None and name_el.text:
            authors.append(name_el.text.strip())
    return {"title": title, "doi": None, "year": _arxiv_year(entry, namespace),
            "full_text_url": full_text_url,
            "authors": authors, "venue": "arXiv", "abstract": abstract}


_ENDPOINT_BUILDERS = {
    "openalex": lambda identifier, config: (_openalex_url(identifier, config), _parse_openalex),
    "crossref": lambda identifier, config: (_crossref_url(identifier), _parse_crossref),
    "arxiv": lambda identifier, config: (_arxiv_url(identifier), _parse_arxiv),
    "semantic-scholar": lambda identifier, config: (_semantic_scholar_url(identifier, config), _parse_semantic_scholar),
}


def resolve_identifier(identifier: str, *, resolver: str, role: str, config: dict) -> dict:
    """Resolves one identifier through one named resolver, honoring the
    role's configured connector list.

    Refuses `DISCOVERY_UNAVAILABLE`/`RESOLVER_ROLE_EMPTY` when the role has
    no configured connectors or does not include `resolver`,
    `RESOLVER_UNREACHABLE` (exit 2) when the transport never answers after
    one retry, and `IDENTIFIER_UNRESOLVED` when the endpoint answers but
    names no matching work (`literature-search`, Requirement: Unreachable
    Connectors Refuse By Name).
    """
    connectors = require_role_connectors(config, role)
    if resolver not in connectors or resolver not in _ENDPOINT_BUILDERS:
        raise Refused(
            "RESOLVER_ROLE_EMPTY",
            f"{resolver!r} is not a connector configured for role {role!r} ({connectors})",
        )
    url, parser = _ENDPOINT_BUILDERS[resolver](identifier, config)
    try:
        raw = _get(url, config=config)
        metadata = parser(raw)
    except _Unreachable as exc:
        raise Refused("RESOLVER_UNREACHABLE", str(exc))
    except _NoSuchWork as exc:
        raise Refused("IDENTIFIER_UNRESOLVED", str(exc))
    digest = hashlib.sha256(raw).hexdigest()
    return {
        "identifier": identifier,
        "resolver": resolver,
        "metadata_digest": digest,
        **metadata,
    }


def pause() -> None:
    """The wait a batch owes before each request (`_REQUEST_PAUSE_SECONDS`)."""
    time.sleep(_REQUEST_PAUSE_SECONDS)


def search_title(title: str, *, role: str, config: dict) -> list[dict]:
    """The works OpenAlex ranks for `title`, each in `resolve_identifier`'s
    shape, its digest taken over that one work. A ranking is no identification:
    the caller accepts a work only by its own title. Refuses as
    `resolve_identifier` does, and answers `[]` for nothing found.
    """
    connectors = require_role_connectors(config, role)
    if "openalex" not in connectors:
        raise Refused(
            "RESOLVER_ROLE_EMPTY", f"'openalex' is not a connector configured for role {role!r} ({connectors})",
        )
    query = {"search": title, "per-page": _TITLE_SEARCH_RESULTS}
    if _contact(config):
        query["mailto"] = _contact(config)
    url = "https://api.openalex.org/works?" + urllib.parse.urlencode(query)
    try:
        raw = _get(url, config=config)
    except _Unreachable as exc:
        raise Refused("RESOLVER_UNREACHABLE", f"title search: {exc}")
    except _NoSuchWork:
        return []
    works = []
    for work in json.loads(raw).get("results") or []:
        encoded = json.dumps(work, sort_keys=True).encode("utf-8")
        metadata = _parse_openalex(encoded)
        doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", metadata.get("doi") or "", flags=re.IGNORECASE)
        works.append({
            "identifier": doi or work.get("id"), "resolver": "openalex",
            "metadata_digest": hashlib.sha256(encoded).hexdigest(), **metadata,
        })
    return works


def fetch_bytes(url: str, *, config: dict) -> bytes:
    """Fetches raw bytes from `url` through the exact same client
    `resolve_identifier` uses -- the module-level `OPENER` seam, its retry
    policy (one retry, fixed 1s, only transport error / 429 / 5xx), and its
    `contact` courtesy `User-Agent` -- never a second HTTP path
    (`full-text-fetch`, "Do not write a second HTTP path"). The one real
    caller is `paper_full_text.fetch_full_text`, fetching the PDF bytes a
    cached record's own `full_text_url` names.

    Raises `RESOLVER_UNREACHABLE` (exit 2) when the transport never answers
    after one retry, and `IDENTIFIER_UNRESOLVED` when the endpoint answers
    with a 404 or other non-retryable status -- the same two codes
    `resolve_identifier` already raises for its own `_get` call (worded
    distinctly here only so each call site's own mutation proof keeps a
    uniquely-anchored literal to target; both funnel through the SAME
    `_get`, never a second HTTP path).
    """
    try:
        return _get(url, config=config)
    except _Unreachable as exc:
        raise Refused("RESOLVER_UNREACHABLE", f"full-text fetch: {exc}")
    except _NoSuchWork as exc:
        raise Refused("IDENTIFIER_UNRESOLVED", f"full-text fetch: {exc}")


def metadata_dir(paper_dir: Path) -> Path:
    """Where a paper's resolutions are cached, and where `bib` and
    `full_text` look them up."""
    return paper_dir / ".paper-writing" / "metadata"


def _metadata_path(paper_dir: Path, metadata_digest: str) -> Path:
    return metadata_dir(paper_dir) / f"{metadata_digest}.json"


def cache_metadata(paper_dir: Path, result: dict) -> dict:
    """Caches a `resolve_identifier` result keyed by its own
    `metadata_digest` (`design.md`, Decision 4 -- `paper_bib.py`'s entry
    producer looks it back up by this same key)."""
    return cache_metadata_in(metadata_dir(paper_dir), result)


def cache_metadata_in(directory: Path, result: dict) -> dict:
    """The same record, keyed the same way, in a directory the caller names
    -- for a caller that is not writing a paper (`resolve --cache-dir`).
    Nothing under `paper/` reads it: `bib` and `full_text` read only
    `metadata_dir(paper_dir)`."""
    path = directory / f"{result['metadata_digest']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return {"path": str(path)}


def read_cached_metadata(paper_dir: Path, metadata_digest: str) -> dict | None:
    path = _metadata_path(paper_dir, metadata_digest)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
