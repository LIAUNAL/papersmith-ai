"""paper_resolve: stdlib-only `urllib` client for citation resolution and
metadata retrieval against Ai2's Asta, OpenAlex, Crossref and arXiv. Keyless
by default -- OpenAlex's documented "polite pool" identity is a `mailto`
contact, sourced from `papersmith.yaml`'s `paper_writing.contact`, never a
secret and never hardcoded (`literature-search`, Requirement: Resolution Runs
Through the CLI Over Stdlib `urllib`). Two connectors MAY carry the
operator's own per-user key, read only through `_key()` from the store
`smith keys` and the dashboard write (`skills/_core/api_keys.py`), never from
a workspace file, and never written to a result, a cache, a refusal or
stdout: OpenAlex's `api_key` (a larger budget) and Asta's `x-api-key` (Asta
is asked at all only with its key). At most one retry, fixed 1s, only on
transport error / 429 / 5xx, never on 404 (`design.md`, Decision 3).

Asta (the Semantic Scholar corpus) is reached over MCP streamable HTTP through
the same `OPENER` (`skills/_core/literature/asta_protocol.py` holds the wire
format): one `tools/call` per lookup, its event stream read under a TOTAL
deadline because its keep-alive pings reset any per-read timeout. Only the
identifier lookup (`get_paper`) and the exact-title lookup
(`search_paper_by_title`) are called -- never an open topic search, never a
snippet, never the model-written `tldr`.

This is also the one path that makes `paper-writing`'s CLI **not** offline
end to end (`proposal.md`, Approach) -- every call sits behind a role
`papersmith.yaml` can empty, and an unreachable endpoint is a named refusal,
never a silent empty result.

Public surface:

    OPENER                                    -- module-level urllib seam
    load_config(path=None)                    -> dict
    connectors_for_role(config, role)         -> list[str]
    require_role_connectors(config, role)     -> list[str]  (raises RESOLVER_ROLE_EMPTY / DISCOVERY_UNAVAILABLE)
    active_connectors(config, role)           -> list[str]  (drops a keyed connector without its key)
    identifier_kind(identifier)               -> ("doi" | "arxiv", value) | None
    chain_for(kind, connectors)               -> list[str]
    resolve_identifier(identifier, *, resolver, role, config) -> dict
    resolve_chain(identifier, *, role, config) -> (dict, list[dict])
    search_title(title, *, role, config, connector="openalex") -> list[dict]
    pause()                                   -- the wait before each request of a batch
    fetch_bytes(url, *, config)                -> bytes
    cache_metadata(paper_dir, result)         -> dict
    cache_metadata_in(directory, result)      -> dict
    read_cached_metadata(paper_dir, digest)   -> dict | None
"""
from __future__ import annotations

import hashlib
import http.client
import importlib.util
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
#: OpenAlex and Crossref resolve a DOI, arXiv resolves its own id space,
#: Semantic Scholar (Graph API, keyless public pool) resolves either a DOI
#: or an arXiv id with cross-source external ids, and Asta (Ai2's MCP server
#: over the same corpus, asked only with the operator's key) resolves both
#: and an exact title -- together they cover every identifier `resolve`
#: accepts today. Widening this set is a module change made when a new
#: identifier scheme needs a client, never a per-paper decision
#: (`proposal.md`, Approach).
RESOLVERS: tuple[str, ...] = ("openalex", "crossref", "arxiv", "semantic-scholar", "asta")

#: What each connector CAN do -- never which one a role uses: the order of
#: `papersmith.yaml`'s role lists decides that (`literature-search`,
#: Requirement: Connector Roles Are Configuration, Never Code).
#:
#: A connector that needs the operator's key to be asked at all. Without its
#: key it is skipped, so a role that names it behaves exactly like the same
#: role without it. Asta answers identifier lookups keyless but stalls every
#: search, and Ai2's terms tie its use to a requested key.
KEY_REQUIRED: tuple[str, ...] = ("asta",)
#: A connector that never carries an abstract: asked after every one that can.
ABSTRACTLESS: tuple[str, ...] = ("crossref",)
#: The identifier kinds each connector resolves.
_RESOLVES: dict[str, tuple[str, ...]] = {
    "doi": ("asta", "openalex", "semantic-scholar", "crossref"),
    "arxiv": ("asta", "arxiv", "semantic-scholar"),
    "title": ("asta", "openalex"),
}
#: `resolve --resolver auto`: the role's active connectors in its own order.
AUTO = "auto"
#: The Semantic Scholar fields a record is built from. Never `tldr` (a model
#: wrote it) and never `openAccessPdf` (Asta stays out of the full-text role:
#: a PDF link is measured from a resolver that fetched it, never assumed).
ASTA_PAPER_FIELDS = "title,year,externalIds,venue,publicationVenue,journal,authors,abstract"

#: The connector roles `papersmith.yaml`'s `paper_writing.roles` maps.
#: `discovery` is read by this module only to validate configuration --
#: the actual discovery search never runs here, it runs through the agent's
#: MCP (`literature-search`, Requirement: Discovery Runs Through the Agent's
#: MCP).
ROLES: tuple[str, ...] = ("discovery", "resolution", "full-text")

_RETRY_DELAY_SECONDS = 1
_TIMEOUT_SECONDS = 10
#: Asta pings every 15 s while a call is pending, so a read waits longer than
#: that, and the TOTAL deadline is what bounds a call.
_ASTA_READ_TIMEOUT_SECONDS = 20
_ASTA_LOOKUP_DEADLINE_SECONDS = 30
_ASTA_TITLE_DEADLINE_SECONDS = 60
_ASTA_MIN_INTERVAL_SECONDS = 1.0
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


class _KeyRefused(Exception):
    """The endpoint refused the operator's configured key (401/403)."""


# --- the operator's keys and the Asta wire format ------------------------

def _core_module(name: str, relative: str):
    """A `skills/_core` module, loaded by path once (this skill ships alone)."""
    module = sys.modules.get(name)
    if module is None:
        source = Path(__file__).resolve().parents[2] / "_core" / relative
        spec = importlib.util.spec_from_file_location(name, source)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load {source}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(name, None)
            raise
    return module


def _key(connector: str) -> str | None:
    """The operator's key for `connector` (`smith keys`, the dashboard's API
    keys panel, or its exported variable), or `None`. Never raises."""
    try:
        return _core_module("papersmith_api_keys", "api_keys.py").read(connector)
    except Exception:  # noqa: BLE001 - no usable key behaves as no key
        return None


def _asta():
    return _core_module("papersmith_asta_protocol", "literature/asta_protocol.py")


_API_KEY_PARAM_RE = re.compile(r"(api_key=)[^&\s]+")


def _redact(text: str) -> str:
    """`text` with any key a URL or an answer could carry masked."""
    text = _API_KEY_PARAM_RE.sub(r"\1<redacted>", str(text))
    for connector in KEY_REQUIRED + ("openalex",):
        value = _key(connector)
        if value:
            text = text.replace(value, "<redacted>")
    return text


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


def _key_missing(connector: str) -> bool:
    return connector in KEY_REQUIRED and not _key(connector)


def _needs_key(connector: str) -> str:
    return (f"{connector!r} is asked only with its key, which is not set: save it in the dashboard "
            f"(Doctor -> API keys) or run `smith keys set {connector}`")


def active_connectors(config: dict, role: str) -> list:
    """The role's connectors in order, without a keyed one whose key is not
    set: a role naming Asta behaves, without the Asta key, exactly like the
    same role without it. Refuses as `require_role_connectors` does when the
    role is empty, and the same way when every connector it names is keyless."""
    connectors = require_role_connectors(config, role)
    active = [name for name in connectors if not _key_missing(name)]
    if active:
        return active
    if role == "discovery":
        raise Refused("DISCOVERY_UNAVAILABLE", "every discovery connector needs a key that is not set: "
                      + "; ".join(_needs_key(name) for name in connectors))
    raise Refused("RESOLVER_ROLE_EMPTY", f"every connector of the {role!r} role needs a key that is not "
                  "set: " + "; ".join(_needs_key(name) for name in connectors))


_DOI_URL_RE = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:)", re.IGNORECASE)
_DOI_RE = re.compile(r"^10\.\d+(?:\.\d+)*/\S+$")
_ARXIV_PREFIX_RE = re.compile(r"^(?:https?://(?:www\.)?arxiv\.org/(?:abs|pdf)/|arxiv:)", re.IGNORECASE)
_ARXIV_ID_RE = re.compile(r"^(?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[a-z]{2})?/\d{7})(?:v\d+)?$", re.IGNORECASE)


def identifier_kind(identifier: str) -> tuple[str, str] | None:
    """`("doi", bare doi)`, `("arxiv", bare id)` or `None` for anything else.

    A DOI loses a `https://doi.org/`-style or `doi:` prefix; an arXiv id its
    `arXiv:` prefix or `arxiv.org/abs|pdf/` URL and a trailing `.pdf`.
    """
    text = (identifier or "").strip()
    bare = _DOI_URL_RE.sub("", text)
    if _DOI_RE.match(bare):
        return ("doi", bare)
    bare = _ARXIV_PREFIX_RE.sub("", text)
    if bare.lower().endswith(".pdf"):
        bare = bare[:-4]
    if _ARXIV_ID_RE.match(bare):
        return ("arxiv", bare)
    return None


def chain_for(kind: str, connectors: list) -> list:
    """The connectors of a role that resolve an identifier of `kind`, in the
    role's own order, with the ones that never carry an abstract last."""
    able = [name for name in connectors if name in _RESOLVES.get(kind, ())]
    return [name for name in able if name not in ABSTRACTLESS] + [name for name in able if name in ABSTRACTLESS]


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
                raise _NoSuchWork(f"{_redact(url)}: 404")
            if exc.code == 429 or 500 <= exc.code < 600:
                last_error = exc
                if attempts < 2:
                    time.sleep(_RETRY_DELAY_SECONDS)
                    continue
                raise _Unreachable(f"{_redact(url)}: HTTP {exc.code} after {attempts} attempt(s)")
            if exc.code in (401, 403) and "api_key=" in url:
                # The operator's key, not the work: never reported as a missing paper.
                raise _KeyRefused(f"{_redact(url)}: HTTP {exc.code}: the configured key was refused; "
                                  "check it in the dashboard (Doctor -> API keys) or with `smith keys status`")
            raise _NoSuchWork(f"{_redact(url)}: HTTP {exc.code}")
        except urllib.error.URLError as exc:
            last_error = exc
            if attempts < 2:
                time.sleep(_RETRY_DELAY_SECONDS)
                continue
            raise _Unreachable(f"{_redact(url)}: {exc.reason} after {attempts} attempt(s)")
    raise _Unreachable(f"{_redact(url)}: unreachable after {attempts} attempt(s): {last_error}")


def _openalex_params(config: dict) -> dict:
    """`mailto` from configuration and, only when the operator configured
    one, their OpenAlex key: the one place a key enters an OpenAlex request."""
    params = {}
    contact = _contact(config)
    if contact:
        params["mailto"] = contact
    key = _key("openalex")
    if key:
        params["api_key"] = key
    return params


def _openalex_url(doi: str, config: dict) -> str:
    base = f"https://api.openalex.org/works/https://doi.org/{urllib.parse.quote(doi, safe='/:;()._-')}"
    params = _openalex_params(config)
    if params:
        return base + "?" + urllib.parse.urlencode(params)
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
    passes DOIs to OpenAlex and Crossref, and a bare arXiv id (what a role's
    chain passes once `identifier_kind` stripped its prefix) as an arXiv id.
    A batch still owes its `_REQUEST_PAUSE_SECONDS` between requests, like
    every other connector.
    """
    bare = identifier.strip()
    if bare[:6].lower() == "arxiv:":
        prefixed = "ARXIV:" + bare[6:].strip()
    elif bare[:4].lower() == "doi:":
        prefixed = "DOI:" + bare[4:].strip()
    elif _ARXIV_ID_RE.match(bare):
        prefixed = "ARXIV:" + bare
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


#: Markup a source printed is never stripped into a "quote" it never printed.
_MARKUP_RE = re.compile(r"</?(?:jats:[\w-]+|mml:[\w-]+|p|i|b|em|strong|sub|sup|sc|scp|italic|bold|br|span|div)"
                        r"\b[^<>]*>", re.IGNORECASE)
_asta_last_call = [0.0]


def _asta_call(tool: str, arguments: dict, *, config: dict, deadline_seconds: float) -> list:
    """One Asta tool call through `OPENER`: the text parts of its answer.

    Raises `_NoSuchWork` (the corpus holds no such paper), `_KeyRefused` (the
    key was refused) or `_Unreachable` (anything else, after at most one
    retry, and never past `deadline_seconds` of wall time). No message carries
    the key."""
    protocol = _asta()
    key = _key("asta")
    url, body, headers = protocol.request(tool, arguments, key=key)
    headers = {"User-Agent": _user_agent(config), **headers}
    until = time.monotonic() + deadline_seconds
    attempts = 0
    while True:
        attempts += 1
        if until - time.monotonic() <= 0:
            raise _Unreachable(f"asta {tool}: no answer within {deadline_seconds:g} s")
        wait = _ASTA_MIN_INTERVAL_SECONDS - (time.monotonic() - _asta_last_call[0])
        if wait > 0:
            time.sleep(wait)
        _asta_last_call[0] = time.monotonic()
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        retryable = True
        try:
            remaining = max(0.1, until - time.monotonic())
            with OPENER.open(request, timeout=min(_ASTA_READ_TIMEOUT_SECONDS, remaining)) as response:
                message = protocol.read_message(response.readline, deadline=until)
            return protocol.tool_texts(message)
        except protocol.AstaError as exc:
            detail = protocol.redact(exc.detail, key)
            if exc.kind == protocol.NOT_FOUND:
                raise _NoSuchWork(f"asta {tool}: {detail}")
            if exc.kind == protocol.REFUSED:
                raise _KeyRefused(f"asta {tool}: {detail}: the configured Asta key was refused; check it "
                                  "in the dashboard (Doctor -> API keys) or with `smith keys status asta`")
            reason = detail
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise _KeyRefused(f"asta {tool}: HTTP {exc.code}: the configured Asta key was refused")
            reason = f"HTTP {exc.code}"
            retryable = exc.code == 429 or 500 <= exc.code < 600
        except (urllib.error.URLError, OSError, http.client.HTTPException, ValueError) as exc:
            reason = protocol.redact(f"{type(exc).__name__}: {getattr(exc, 'reason', exc)}", key)
        if not retryable or attempts >= 2 or until - time.monotonic() <= _RETRY_DELAY_SECONDS:
            raise _Unreachable(f"asta {tool}: {reason} after {attempts} attempt(s)")
        time.sleep(_RETRY_DELAY_SECONDS)


def _parse_asta(paper: dict) -> dict:
    """A Semantic Scholar paper object in `resolve_identifier`'s shape.

    `abstract` is the paper's own `abstract` only, whitespace-collapsed: never
    the model-written `tldr`, and `None` when it carries markup, the same rule
    Crossref's JATS gets. `full_text_url` is always `None`: Asta stays out of
    the full-text role."""
    authors = []
    for author in paper.get("authors") or []:
        name = author.get("name") if isinstance(author, dict) else None
        if isinstance(name, str) and name.strip():
            authors.append(name.strip())
    journal = paper.get("journal") if isinstance(paper.get("journal"), dict) else {}
    publication_venue = paper.get("publicationVenue") if isinstance(paper.get("publicationVenue"), dict) else {}
    venue = journal.get("name") or publication_venue.get("name") or paper.get("venue") or None
    external = paper.get("externalIds") if isinstance(paper.get("externalIds"), dict) else {}
    abstract = paper.get("abstract")
    if isinstance(abstract, str):
        abstract = " ".join(abstract.split()) or None
        if abstract and _MARKUP_RE.search(abstract):
            abstract = None
    else:
        abstract = None
    return {
        "title": paper.get("title"), "doi": external.get("DOI"), "year": paper.get("year"),
        "full_text_url": None, "authors": authors, "venue": venue, "abstract": abstract,
    }


def _resolve_asta(identifier: str, config: dict) -> tuple[bytes, dict]:
    """`(raw, metadata)`: `raw` is the tool's JSON text, never the event
    stream around it, so two answers differing only in pings digest alike."""
    kind = identifier_kind(identifier)
    if kind is None:
        raise _NoSuchWork(f"asta: {identifier!r} is neither a DOI nor an arXiv id")
    texts = _asta_call("get_paper", {"paper_id": _asta().paper_id(*kind), "fields": ASTA_PAPER_FIELDS},
                       config=config, deadline_seconds=_ASTA_LOOKUP_DEADLINE_SECONDS)
    payload = next((text for text in texts if text.strip()), None)
    if payload is None:
        raise _Unreachable("asta get_paper: the answer carried no paper")
    try:
        paper = json.loads(payload)
    except ValueError:
        raise _Unreachable("asta get_paper: the answer is not JSON")
    if not isinstance(paper, dict):
        raise _Unreachable("asta get_paper: the answer is not a paper object")
    return payload.encode("utf-8"), _parse_asta(paper)


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
    no configured connectors, does not include `resolver`, or `resolver`
    needs a key that is not set, `RESOLVER_UNREACHABLE` (exit 2) when the
    transport never answers after one retry, `RESOLVER_REFUSED` when the
    service refuses the operator's configured key, and `IDENTIFIER_UNRESOLVED`
    when the endpoint answers but names no matching work (`literature-search`,
    Requirement: Unreachable Connectors Refuse By Name).
    """
    connectors = require_role_connectors(config, role)
    if resolver not in connectors or resolver not in RESOLVERS:
        raise Refused(
            "RESOLVER_ROLE_EMPTY",
            f"{resolver!r} is not a connector configured for role {role!r} ({connectors})",
        )
    if _key_missing(resolver):
        raise Refused("RESOLVER_ROLE_EMPTY", _needs_key(resolver))
    try:
        if resolver == "asta":
            raw, metadata = _resolve_asta(identifier, config)
        else:
            url, parser = _ENDPOINT_BUILDERS[resolver](identifier, config)
            raw = _get(url, config=config)
            metadata = parser(raw)
    except _Unreachable as exc:
        raise Refused("RESOLVER_UNREACHABLE", str(exc))
    except _NoSuchWork as exc:
        raise Refused("IDENTIFIER_UNRESOLVED", str(exc))
    except _KeyRefused as exc:
        raise Refused("RESOLVER_REFUSED", str(exc))
    digest = hashlib.sha256(raw).hexdigest()
    return {
        "identifier": identifier,
        "resolver": resolver,
        "metadata_digest": digest,
        **metadata,
    }


#: What a chain step may answer instead of a record, and still go on.
_CHAIN_FAILURES = ("IDENTIFIER_UNRESOLVED", "RESOLVER_UNREACHABLE", "RESOLVER_REFUSED")


def resolve_chain(identifier: str, *, role: str, config: dict) -> tuple[dict, list]:
    """`resolve --resolver auto`: the role's active connectors that resolve
    this identifier's kind, in the role's order (abstractless ones last).

    Returns `(record, attempts)`. The record is the first, in that order,
    that carries an abstract, else the first that found the work -- always
    whole from ONE connector, never fields merged from two, so its `resolver`
    and `metadata_digest` name what was actually fetched. `attempts` lists
    each connector asked and what it answered. When none found the work it
    refuses by the strongest common reason."""
    kind = identifier_kind(identifier)
    if kind is None:
        raise Refused("IDENTIFIER_UNRESOLVED",
                      f"{identifier!r} is neither a DOI nor an arXiv id; name one connector with --resolver")
    connectors = active_connectors(config, role)
    chain = chain_for(kind[0], connectors)
    if not chain:
        raise Refused("RESOLVER_ROLE_EMPTY", f"no active connector of role {role!r} resolves a {kind[0]} "
                      f"({connectors})")
    attempts: list = []
    first = None
    for name in chain:
        if first is not None and name in ABSTRACTLESS:
            continue  # it could only repeat a record that has no abstract
        try:
            record = resolve_identifier(kind[1], resolver=name, role=role, config=config)
        except Refused as exc:
            if exc.code not in _CHAIN_FAILURES:
                raise
            attempts.append({"resolver": name, "outcome": exc.code, "detail": str(exc.detail)[:300]})
            continue
        attempts.append({"resolver": name, "outcome": "abstract" if record.get("abstract") else "no_abstract"})
        if record.get("abstract"):
            return record, attempts
        first = first or record
    if first is not None:
        return first, attempts
    outcomes = {attempt["outcome"] for attempt in attempts}
    summary = "; ".join(f"{a['resolver']}: {a['outcome']}" for a in attempts)
    if outcomes == {"RESOLVER_REFUSED"}:
        raise Refused("RESOLVER_REFUSED", f"every connector asked refused its key ({summary})")
    if outcomes <= {"RESOLVER_UNREACHABLE", "RESOLVER_REFUSED"}:
        raise Refused("RESOLVER_UNREACHABLE", f"no connector of the chain answered ({summary})")
    raise Refused("IDENTIFIER_UNRESOLVED", f"no connector of the chain holds this work ({summary})")


def pause() -> None:
    """The wait a batch owes before each request (`_REQUEST_PAUSE_SECONDS`)."""
    time.sleep(_REQUEST_PAUSE_SECONDS)


def search_title(title: str, *, role: str, config: dict, connector: str = "openalex") -> list[dict]:
    """The works `connector` (OpenAlex or Asta) ranks for `title`, each in
    `resolve_identifier`'s shape, its digest taken over that one work. A
    ranking is no identification: the caller accepts a work only by its own
    title. Refuses as `resolve_identifier` does, and answers `[]` for nothing
    found.
    """
    connectors = require_role_connectors(config, role)
    if connector not in connectors or connector not in _RESOLVES["title"]:
        raise Refused(
            "RESOLVER_ROLE_EMPTY", f"{connector!r} is not a connector configured for role {role!r} ({connectors})",
        )
    if _key_missing(connector):
        raise Refused("RESOLVER_ROLE_EMPTY", _needs_key(connector))
    if connector == "asta":
        return _asta_titles(title, config)
    query = {"search": title, "per-page": _TITLE_SEARCH_RESULTS, **_openalex_params(config)}
    url = "https://api.openalex.org/works?" + urllib.parse.urlencode(query)
    try:
        raw = _get(url, config=config)
    except _Unreachable as exc:
        raise Refused("RESOLVER_UNREACHABLE", f"title search: {exc}")
    except _NoSuchWork:
        return []
    except _KeyRefused as exc:
        raise Refused("RESOLVER_REFUSED", f"title search: {exc}")
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


def _asta_titles(title: str, config: dict) -> list[dict]:
    """Asta's exact-title lookup, each paper in `resolve_identifier`'s shape,
    named by its DOI, else its arXiv id, else its Semantic Scholar page."""
    protocol = _asta()
    try:
        texts = _asta_call("search_paper_by_title", {"title": title, "fields": ASTA_PAPER_FIELDS + ",url"},
                           config=config, deadline_seconds=_ASTA_TITLE_DEADLINE_SECONDS)
        papers = protocol.papers(texts)
    except _Unreachable as exc:
        raise Refused("RESOLVER_UNREACHABLE", f"title search: {exc}")
    except _NoSuchWork:
        return []
    except _KeyRefused as exc:
        raise Refused("RESOLVER_REFUSED", f"title search: {exc}")
    except protocol.AstaError as exc:
        raise Refused("RESOLVER_UNREACHABLE", f"title search: asta: {exc.detail}")
    works = []
    for paper in papers:
        metadata = _parse_asta(paper)
        external = paper.get("externalIds") if isinstance(paper.get("externalIds"), dict) else {}
        page = paper.get("url") or (f"https://www.semanticscholar.org/paper/{paper['paperId']}"
                                    if paper.get("paperId") else None)
        identifier = metadata.get("doi") or (f"arXiv:{external['ArXiv']}" if external.get("ArXiv") else page)
        if not identifier:
            continue
        encoded = json.dumps(paper, sort_keys=True).encode("utf-8")
        works.append({"identifier": identifier, "resolver": "asta",
                      "metadata_digest": hashlib.sha256(encoded).hexdigest(), **metadata})
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
