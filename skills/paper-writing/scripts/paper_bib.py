"""paper_bib: `paper/refs.bib` built exclusively from cached, resolved
metadata, so "never hand-typed" is a checked property rather than a claim
(`no-claim-without-a-source-that-holds-it`, `sourced-bibliography` spec).

`entry_from_record` is the SOLE entry producer -- no function or CLI flag
anywhere in this skill accepts caller-composed entry text. Handing this
module a finished entry would replace a human typing with a model typing
and degrade "never hand-typed" from a checked property to a claim
(`design.md`, Decision 4).

`no-citation-before-its-paper-is-ingested` (item 2) adds a second, stricter
requirement on top of "resolved": a citation's cached metadata may not
reach `refs.bib` until the paper it cites has actually been ingested.
Resolution and ingestion are two independent facts about the same
citation -- a DOI can resolve against OpenAlex/Crossref while the PDF
itself still sits unread on someone's desk -- so `entry_from_record` checks
both, never conflating "the metadata is real" with "the source is here to
be quoted from".

The match between a resolved record and an ingested paper is NEVER a guess
from `identifier`/`resolver` against a folder name: a resolved DOI or
arXiv id and a `guidance/<root>/<paper>/` folder name have no free
correspondence, and pairing them by string similarity risks silently
citing the WRONG paper's metadata against the RIGHT paper's ingested text
(`design.md`; the launch context's own warning). Instead this module reuses
the one link that is already exact: `record["source_md"]`, the literal path
`paper_evidence.EvidenceSpan.locate` verified a real quote against when the
evidence record was built (`validate --quote ... --source-md ...`). A
record whose evidence span was never located against any ingested file
(`source_md` empty -- `verdict == "insufficient"`, or a hand-built record)
carries no such link and refuses; a `source_md` that does not resolve to
`guidance/<root>/<paper>/<paper>.md` -- the exact two-level shape
`paper_guidance.ingested_papers` walks -- refuses the same way, because
that shape IS what "ingested" means in this skill (`paper-ingestion`
SKILL.md). No second, independent classifier is introduced.

Public surface:

    entry_from_record(paper_dir, record, *, guidance_dir) -> dict
        (raises ENTRY_UNSOURCED / ENTRY_NOT_INGESTED)
    build_refs_bib(paper_dir, records, *, guidance_dir) -> dict
        (rebuilds refs.bib whole, sorted)
    source_identity(identifier, resolver) -> tuple[str, str] | None
    refresh_metadata(paper_dir, cite_key, metadata_digest, *, guidance_dir, resolver=None) -> dict
        (relinks existing evidence to fresher metadata of the same work)
    cited_keys(main_tex_bytes)           -> set[str]
    entry_keys(refs_bib_bytes)           -> set[str]
    check_reciprocal(main_tex_bytes, refs_bib_bytes) -> dict (raises CITE_WITHOUT_ENTRY / ENTRY_WITHOUT_CITE)
    parse_bib(text) / plain_text(value)  -- the one tolerant reader, shared with the command center
    title_key(value) / bib_identifiers(entry) / identity_fields(entry)
    resolve_references(paper_dir, main_tex_bytes, refs_bib_bytes, *, config, role, force) -> dict
        (the sidecar of `resolve --references`; every request goes through paper_resolve)
    read_references(paper_dir)           -> dict
"""
from __future__ import annotations

import http.client
import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paper_block  # noqa: E402 -- the atomic write of the reference sidecar
import paper_evidence  # noqa: E402
import paper_guidance  # noqa: E402 -- no-citation-before-its-paper-is-ingested, item 2: the ingestion check
import paper_resolve  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_core" / "implementation"))
from impl_refusals import Refused  # noqa: E402

#: The citation commands `cited_keys` reads -- the declared vocabulary, not
#: arbitrary TeX: each command may carry a `*` and up to two `[...]`
#: optional arguments (`\\citep[see][ch.~2]{key}`) before one `{...}` of
#: comma-separated keys. Deliberately unsupported: `\\nocite` (it lists
#: entries without citing them), capitalised `\\Citet`-style variants,
#: biblatex commands, and keys split across a nested brace group.
CITE_COMMANDS = ("cite", "citep", "citet", "citealp", "citealt", "citeauthor", "citeyear")
_CITE_RE = re.compile(
    r"\\(?:" + "|".join(sorted(CITE_COMMANDS, key=len, reverse=True)) + r")\*?"
    r"(?:\s*\[[^\]]*\]){0,2}\s*\{([^}]*)\}"
)
_BIB_ENTRY_RE = re.compile(r"@\w+\{([^,]+),")
_DOI_PREFIXES = ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "http://dx.doi.org/", "doi:")
_ARXIV_PREFIX_RE = re.compile(r"^(?:https?://(?:www\.)?arxiv\.org/(?:abs|pdf)/|arxiv:)", re.IGNORECASE)
#: The sidecar `resolve --references` writes and `verify` and the dashboard
#: read. It sits apart from `refs.bib` because `bib build` rewrites that file.
REFERENCES_SCHEMA = "papersmith.references/v1"
REFERENCE_STATUSES = ("resolved", "not_found", "unreachable")
#: Consecutive keys that reached nothing before the rest stop asking: an
#: offline run costs a few timeouts, not two per cited paper.
_UNREACHABLE_STREAK = 3

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
# Space inside the braces belongs to the accent; space after an unbraced
# letter is the word break of the text, so neither regex may consume it.
_ACCENT_BASE = r"(?:\\([ij])(?![A-Za-z])|([A-Za-z]))"
_SYMBOL_ACCENT_RE = re.compile(
    r"\\(['`^\"~=.])(?:\s*\{\s*" + _ACCENT_BASE + r"\s*\}|\s*" + _ACCENT_BASE + ")")
_LETTER_ACCENT_RE = re.compile(
    r"\\([uvHckr])(?:\s*\{\s*" + _ACCENT_BASE + r"\s*\}|\s+" + _ACCENT_BASE + ")")
_LETTER_RE = re.compile(r"\\(ss|ae|AE|oe|OE|aa|AA|o|O|l|L|i|j)(?![A-Za-z])\s*(?:\{\})?")
_ESCAPED_RE = re.compile(r"\\([&%_#$])")
_COMMAND_RE = re.compile(r"\\[a-zA-Z]+\*?\s*(?:\[[^\]]*\])?")
_YEAR_RE = re.compile(r"\b(\d{4})\b")
# An arXiv id named inside free text: "arXiv preprint arXiv:1905.13311".
_ARXIV_IN_TEXT_RE = re.compile(
    r"arxiv\s*:\s*(\d{4}\.\d{4,5}(?:v\d+)?|[a-z-]+(?:\.[a-z]{2})?/\d{7}(?:v\d+)?)", re.IGNORECASE)
_ARXIV_ID_RE = re.compile(r"^(?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[a-z]{2})?/\d{7})(?:v\d+)?$", re.IGNORECASE)


# --- reading a bibliography ---------------------------------------------
#
# The one tolerant reader: whole entries on one line, multi-line values,
# quotes, parentheses, any field case and `@string` macros, as exporters
# really write them. `atlas_manuscript` and `paper_explorer` both read through
# it, and `atlas_manuscript` is loaded by path, which is why it lives here.

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
    value = value.replace("\0", "")  # NUL delimits the held math spans below
    math: list[str] = []

    def hold(match: re.Match) -> str:
        math.append(match.group(1))
        return f"\0{len(math) - 1}\0"

    text = _MATH_RE.sub(hold, value)
    for accent_re in (_SYMBOL_ACCENT_RE, _LETTER_ACCENT_RE):
        text = accent_re.sub(
            lambda m: _accent(m.group(1), m.group(2) or m.group(4), m.group(3) or m.group(5)), text)
    text = _LETTER_RE.sub(lambda m: _LETTERS[m.group(1)], text)
    text = _ESCAPED_RE.sub(r"\1", text)
    text = _COMMAND_RE.sub("", text)
    text = text.replace("---", "—").replace("--", "–").replace("``", "“").replace("''", "”")
    text = text.replace("~", " ").replace("{", "").replace("}", "").replace("\\", "")
    text = re.sub(r"\0(\d+)\0", lambda m: math[int(m.group(1))], text)
    return unicodedata.normalize("NFC", " ".join(text.split()))


def literal_text(value: Any) -> str:
    """An identifier or URL: braces and escapes go, every other byte stays."""
    if not isinstance(value, str):
        return ""
    return "".join(_ESCAPED_RE.sub(r"\1", value).replace("{", "").replace("}", "").split())


def identity_fields(entry: dict[str, str]) -> dict[str, str]:
    """The shape ``atlas_manuscript``'s identity helpers read."""
    fields = {name: literal_text(entry.get(name)) for name in ("doi", "eprint", "archiveprefix", "url")}
    fields.update({name: plain_text(entry.get(name)) for name in ("journal", "note", "howpublished")})
    return fields


def title_key(value: object) -> str:
    """A title reduced to its lower-cased words: LaTeX commands, braces,
    accents, punctuation and one leading article dropped."""
    if not isinstance(value, str):
        return ""
    text = re.sub(r"\\[a-zA-Z]+\s*|\\.|[{}]", "", value)
    text = "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))
    words = re.findall(r"[a-z0-9]+", text.casefold())
    if len(words) > 1 and words[0] in ("a", "an", "the"):
        words = words[1:]
    return " ".join(words)


def bib_identifiers(entry: dict[str, str]) -> list[tuple[str, str]]:
    """`(identifier, resolver)` pairs a bib entry names, DOI first."""
    found: list[tuple[str, str]] = []
    if entry.get("doi"):
        found.append((entry["doi"], "crossref"))
    eprint = entry.get("eprint", "")
    prefix = entry.get("archiveprefix", "").lower()
    if eprint and (prefix == "arxiv" or (not prefix and _ARXIV_ID_RE.match(eprint))):
        found.append((eprint, "arxiv"))
    for field in ("journal", "note", "howpublished", "url"):
        for match in _ARXIV_IN_TEXT_RE.finditer(entry.get(field, "")):
            found.append((match.group(1), "arxiv"))
    return found


def _require_ingested(record: dict, guidance_dir: Path) -> None:
    """item 2's own gate: `record["source_md"]` must be the real, still-
    present path of an ingested paper (`guidance/<root>/<paper>/<paper>.md`)
    -- never a guess from `identifier`/`resolver`, see the module
    docstring. Refuses `ENTRY_NOT_INGESTED` (work-state) when the record
    carries no located evidence span at all, when that span's own source
    does not sit under `guidance_dir`, or when it does not match the
    ingested-paper shape `paper_guidance.ingested_papers` itself walks.
    """
    cite_key = record.get("cite_key") or "<unknown>"
    source_md = record.get("source_md") or ""
    if not source_md:
        raise Refused(
            "ENTRY_NOT_INGESTED",
            f"{cite_key!r}: this record carries no located evidence span in an ingested paper -- "
            "run `validate --claim ... --quote ... --source-md guidance/<section>/<paper>/<paper>.md "
            f"--verdict holds --cite-key {cite_key}` against an ingested paper before it can reach refs.bib",
        )
    if not paper_guidance.is_ingested_source(source_md, guidance_dir):
        raise Refused(
            "ENTRY_NOT_INGESTED",
            f"{cite_key!r}: {source_md!r} is not an ingested paper under {guidance_dir} "
            "(guidance/<root>/<paper>/<paper>.md) -- place the cited PDF under guidance/<section>/ "
            "and run the paper-ingestion skill over it first",
        )


def entry_from_record(paper_dir: Path, record: dict, *, guidance_dir: Path) -> dict:
    """The sole `refs.bib` entry producer. Reads the cached metadata blob
    keyed by `record['metadata_digest']` (`paper_resolve.read_cached_metadata`)
    and requires the cache's OWN recorded digest to agree with the lookup
    key -- a self-consistency check, not a network call, so this refuses
    correctly with the `OPENER` never installed.

    Refuses `ENTRY_UNSOURCED` (work-state) when `record` carries no
    `resolver`/`metadata_digest` at all (a hand-composed entry, or one from
    an `insufficient` verdict, never has both), when no cached blob exists
    for that digest, or when the cached blob's own digest field does not
    match the key it was looked up by. Refuses `ENTRY_NOT_INGESTED`
    (work-state), checked only once resolution itself is proven, when the
    paper this citation names has not actually been ingested yet
    (`_require_ingested` above; `no-citation-before-its-paper-is-ingested`,
    item 2) -- resolved and ingested are two independent facts, and this is
    the sole gate that requires both before a byte reaches `refs.bib`.
    """
    cite_key = record.get("cite_key") or "<unknown>"
    digest = record.get("metadata_digest") or ""
    resolver = record.get("resolver") or ""
    if not digest or not resolver:
        raise Refused(
            "ENTRY_UNSOURCED",
            f"{cite_key!r}: no resolver/metadata_digest recorded -- this entry was never resolved",
        )
    cached = paper_resolve.read_cached_metadata(paper_dir, digest)
    if cached is None:
        raise Refused(
            "ENTRY_UNSOURCED", f"{cite_key!r}: no cached metadata found for digest {digest!r}"
        )
    if cached.get("metadata_digest") != digest:
        raise Refused(
            "ENTRY_UNSOURCED",
            f"{cite_key!r}: the cached blob's own digest does not match the digest it was looked up by",
        )
    _require_ingested(record, guidance_dir)
    return {
        "cite_key": cite_key,
        "title": cached.get("title"),
        "doi": cached.get("doi"),
        "year": cached.get("year"),
        # An entry with no author is one bibtex cannot even sort ("to sort,
        # need author or key") and no venue will accept. Both are carried
        # through from the cached blob when the connector captured them, and
        # stay absent when it did not -- never invented here.
        "authors": cached.get("authors") or [],
        "venue": cached.get("venue"),
        "resolver": resolver,
        "metadata_digest": digest,
    }


def _latex_escape(value: str) -> str:
    """Escape LaTeX-special bytes `_entry_text` below emits verbatim from
    connector-captured metadata: backslash FIRST (every other replacement
    below adds one, so escaping it later would double-escape those), then
    `&`, `%`, `$`, `#`, `_`. `{`/`}` are deliberately left UNESCAPED --
    they are BibTeX-structural (they delimit the field value itself), and
    escaping them would break brace matching, not protect anything.
    """
    text = value.replace("\\", r"\textbackslash{}")
    for char in ("&", "%", "$", "#", "_"):
        text = text.replace(char, f"\\{char}")
    return text


def _entry_text(entry: dict) -> str:
    # `@article` only when a venue was actually captured: the `plain` style
    # prints `journal` for an article and ignores it on a `@misc`, so an
    # entry with no venue stays `@misc` rather than rendering as an article
    # with a blank journal.
    kind = "article" if entry.get("venue") else "misc"
    lines = [f"@{kind}{{{entry['cite_key']},"]
    # `author`, `title` and `journal` share the identical exposure to raw,
    # unescaped connector text; all three are escaped here.
    if entry.get("authors"):
        authors = " and ".join(_latex_escape(a) for a in entry["authors"])
        lines.append(f"  author = {{{authors}}},")
    if entry.get("title"):
        lines.append(f"  title = {{{_latex_escape(entry['title'])}}},")
    if entry.get("venue"):
        lines.append(f"  journal = {{{_latex_escape(entry['venue'])}}},")
    if entry.get("doi"):
        lines.append(f"  doi = {{{entry['doi']}}},")
    if entry.get("year") is not None:
        lines.append(f"  year = {{{entry['year']}}},")
    lines.append("}")
    # Provenance rides ABOVE the entry as a BibTeX comment, never inside it as
    # a `note` field. A `note` PRINTS: the `plain` style rendered every
    # reference as "... resolver=openalex; metadata_digest=6f98..." in the
    # compiled bibliography -- and the bare `_` of `metadata_digest` is a
    # math-mode character, so the emitted `.bbl` raised "Missing $ inserted"
    # and a single-pass compile then resolved every \ref to `??` and every
    # \cite to `[?]`. BibTeX ignores bytes between entries, so a leading `%`
    # line keeps the provenance readable in the file and out of the page.
    # Nothing reads this back: `parse_bib` skips bytes between entries, and
    # `_BIB_ENTRY_RE` matches cite keys alone.
    comment = f"% resolver={entry['resolver']}; metadata_digest={entry['metadata_digest']}"
    return comment + "\n" + "\n".join(lines) + "\n"


def build_refs_bib(paper_dir: Path, records: list[dict], *, guidance_dir: Path,
                   cited: set[str] = frozenset()) -> dict:
    """Rebuilds `paper/refs.bib` WHOLE, sorted by cite key -- never appended
    in place (`design.md`, Decision 4). One entry per distinct `cite_key`
    among `records` (last-write-wins per key, oldest to newest). Every
    entry is checked via `entry_from_record` BEFORE a single byte is
    written, so one unsourced OR un-ingested record refuses the whole
    rebuild rather than leaving a partially-written file behind.

    A key of `cited` that the existing file holds and `records` does not
    would be lost by the rewrite, so it refuses `ENTRY_UNSOURCED` first and
    the file stays byte for byte. An entry nobody cites still leaves.
    """
    by_key: dict[str, dict] = {}
    for record in records:
        cite_key = record.get("cite_key")
        if cite_key:
            by_key[cite_key] = record
    refs_path = paper_dir / "refs.bib"
    existing = refs_path.read_bytes() if refs_path.is_file() else b""
    lost = sorted((set(cited) & set(parse_bib(existing.decode("utf-8", errors="replace")))) - set(by_key))
    if lost:
        raise Refused(
            "ENTRY_UNSOURCED",
            f"refs.bib was left untouched: rebuilding it would drop the cited entries {lost}, which "
            "have no evidence record -- `bib build` writes only what `validate` recorded, so validate "
            "each key against an ingested paper first",
        )
    entries = [
        entry_from_record(paper_dir, by_key[key], guidance_dir=guidance_dir) for key in sorted(by_key)
    ]
    text = "".join(_entry_text(entry) for entry in entries)
    refs_path.write_text(text, encoding="utf-8")
    return {"path": str(refs_path), "entries": [entry["cite_key"] for entry in entries]}


def source_identity(identifier: str, resolver: str) -> tuple[str, str] | None:
    """The one normalized `(kind, value)` a resolved identifier names, or
    `None` when it names none: a DOI (`openalex`/`crossref`) loses only a
    `https://doi.org/`-style or `doi:` prefix and its case, which DOIs never
    carry meaning in; an arXiv id loses only its `arXiv:` prefix or
    `arxiv.org/abs|pdf/` URL and a trailing `.pdf`. An arXiv VERSION is
    kept: `2401.00001v2` and `2401.00001` are not proven to be the same
    text, so they never compare equal here, and a DOI never equals an arXiv
    id even when it is arXiv's own `10.48550/arXiv.*` DOI.
    """
    text = (identifier or "").strip()
    if not text or resolver not in paper_resolve.RESOLVERS:
        return None
    if resolver == "arxiv":
        bare = _ARXIV_PREFIX_RE.sub("", text)
        if bare.lower().endswith(".pdf"):
            bare = bare[:-4]
        return ("arxiv", bare.lower())
    lowered = text.lower()
    for prefix in _DOI_PREFIXES:
        if lowered.startswith(prefix):
            lowered = lowered[len(prefix):]
            break
    return ("doi", lowered)


def _cache_identity(cached: dict) -> tuple[str, str] | None:
    """A cached blob's identity; a DOI-resolver blob whose own `doi` field
    names a different work than its `identifier` contradicts itself and
    identifies nothing."""
    identity = source_identity(cached.get("identifier") or "", cached.get("resolver") or "")
    doi = cached.get("doi")
    if identity is not None and identity[0] == "doi" and doi:
        if source_identity(doi, cached["resolver"]) != identity:
            return None
    return identity


def _identity_text(identity: tuple[str, str] | None) -> str:
    return "unidentifiable" if identity is None else f"{identity[0]}:{identity[1]}"


def refresh_metadata(
    paper_dir: Path, cite_key: str, metadata_digest: str, *, guidance_dir: Path,
    resolver: str | None = None,
) -> dict:
    """`bib refresh`: relinks the record `build_refs_bib` would read for
    `cite_key` (last-write-wins over `paper_evidence.read_all_records`) to
    the cached metadata keyed by `metadata_digest`, by appending a copy of
    that record that differs ONLY in `resolver` and `metadata_digest`.

    This is a metadata relink, never a support judgment: the claim, quote,
    span, verdict, round and block are copied byte for byte, so the source's
    `guidance/` classification is deliberately not re-judged here -- it was
    judged when the span was located, and `validate` keeps refusing any NEW
    quote from a non-evidence folder. Accordingly it can only relink what
    already exists: refuses `ENTRY_UNSOURCED` when no record carries
    `cite_key`, `ENTRY_NOT_INGESTED` when that record has no located,
    verdict-bearing span or its source is no longer an ingested paper, and
    `ENTRY_UNSOURCED` when either cache is missing or not filed under its
    own digest, when `--resolver` disagrees with the new cache, when the
    record and both caches do not name the same `source_identity`, or when
    an appended copy would not supersede the record. Every check runs
    before the one write; `append_record` is called without `guidance_dir`,
    so no evidence manifest is touched. Refreshing to the digest already
    recorded writes nothing and reports `refreshed: false`.
    """
    winner = None
    for record in paper_evidence.read_all_records(paper_dir):
        if record.get("cite_key") == cite_key:
            winner = record
    if winner is None:
        raise Refused(
            "ENTRY_UNSOURCED",
            f"{cite_key!r}: no evidence record carries this cite key -- "
            "refresh relinks existing evidence and never creates any",
        )
    if (winner.get("verdict") not in ("holds", "does-not-hold") or not winner.get("source_md")
            or not winner.get("quote") or not winner.get("locator")
            or set(winner) != set(paper_evidence.EvidenceRecord.__dataclass_fields__)):
        raise Refused(
            "ENTRY_NOT_INGESTED",
            f"{cite_key!r}: its current evidence record carries no located, verdict-bearing span -- "
            "refresh relinks existing located evidence only and never creates any",
        )
    # The current link must itself be sound: cached, self-consistent and
    # still ingested -- the same gate `bib build` applies to it.
    entry_from_record(paper_dir, winner, guidance_dir=guidance_dir)
    current = paper_resolve.read_cached_metadata(paper_dir, winner["metadata_digest"])
    fresh = paper_resolve.read_cached_metadata(paper_dir, metadata_digest)
    if fresh is None:
        raise Refused(
            "ENTRY_UNSOURCED", f"{cite_key!r}: no cached metadata found for digest {metadata_digest!r}"
        )
    if fresh.get("metadata_digest") != metadata_digest:
        raise Refused(
            "ENTRY_UNSOURCED",
            f"{cite_key!r}: the cached blob's own digest does not match the digest it was looked up by",
        )
    fresh_resolver = fresh.get("resolver")
    if resolver is not None and resolver != fresh_resolver:
        raise Refused(
            "ENTRY_UNSOURCED",
            f"{cite_key!r}: --resolver {resolver!r} does not match the cached metadata's "
            f"resolver {fresh_resolver!r}",
        )
    identities = (
        source_identity(winner.get("identifier") or "", winner["resolver"]),
        _cache_identity(current),
        _cache_identity(fresh),
    )
    if identities[0] is None or len(set(identities)) != 1:
        raise Refused(
            "ENTRY_UNSOURCED",
            f"{cite_key!r}: cached metadata {metadata_digest!r} does not identify the same work as its "
            f"evidence record (record {_identity_text(identities[0])}, current "
            f"{_identity_text(identities[1])}, new {_identity_text(identities[2])})",
        )
    block_id = winner["block_id"]
    # `read_all_records` walks the stores in sorted filename order, so the
    # copy supersedes the record only if that record ends its own block's
    # store and no store sorted after it carries the key.
    stores = sorted(paper_evidence._store_path(paper_dir, block_id).parent.glob("*.jsonl"))
    holding = [
        path.stem for path in stores
        if any(r.get("cite_key") == cite_key for r in paper_evidence.read_records(paper_dir, path.stem))
    ]
    own_store = [r for r in paper_evidence.read_records(paper_dir, block_id) if r.get("cite_key") == cite_key]
    if holding[-1:] != [block_id] or own_store[-1:] != [winner]:
        raise Refused(
            "ENTRY_UNSOURCED",
            f"{cite_key!r}: its current evidence record is not the last line of its own block's store "
            f"{block_id!r} -- an appended copy would not supersede it",
        )
    result = {
        "cite_key": cite_key, "refreshed": False, "block": block_id,
        "path": str(paper_evidence._store_path(paper_dir, block_id)), "resolver": fresh_resolver,
        "metadata_digest": metadata_digest, "previous_metadata_digest": winner["metadata_digest"],
        "year": fresh.get("year"),
    }
    if (winner["resolver"], winner["metadata_digest"]) == (fresh_resolver, metadata_digest):
        return result
    relinked = paper_evidence.EvidenceRecord(
        **{**winner, "resolver": fresh_resolver, "metadata_digest": metadata_digest}
    )
    paper_evidence.append_record(paper_dir, relinked)
    return {**result, "refreshed": True}


def cited_keys(main_tex_bytes: bytes) -> set[str]:
    text = main_tex_bytes.decode("utf-8", errors="replace")
    keys: set[str] = set()
    for match in _CITE_RE.finditer(text):
        for key in match.group(1).split(","):
            key = key.strip()
            if key:
                keys.add(key)
    return keys


def entry_keys(refs_bib_bytes: bytes) -> set[str]:
    text = refs_bib_bytes.decode("utf-8", errors="replace")
    return {match.group(1).strip() for match in _BIB_ENTRY_RE.finditer(text)}


def check_reciprocal(main_tex_bytes: bytes, refs_bib_bytes: bytes) -> dict:
    """`sourced-bibliography`, Requirement: Reciprocal Citation/Entry
    Checks. Each direction fires independently: a `\\cite{}` with no
    matching entry refuses `CITE_WITHOUT_ENTRY` naming every missing key,
    checked first; an entry never cited refuses `ENTRY_WITHOUT_CITE` naming
    every unused key, checked only once the first direction is clean -- so
    a fixture exercising only one direction never sees the other's code."""
    cited = cited_keys(main_tex_bytes)
    entries = entry_keys(refs_bib_bytes)
    missing_entries = sorted(cited - entries)
    if missing_entries:
        raise Refused(
            "CITE_WITHOUT_ENTRY", f"cited but no matching refs.bib entry: {missing_entries}"
        )
    unused_entries = sorted(entries - cited)
    if unused_entries:
        raise Refused("ENTRY_WITHOUT_CITE", f"refs.bib entries never cited: {unused_entries}")
    return {"cited": sorted(cited), "entries": sorted(entries)}


# --- reference metadata for every cited key -----------------------------

def references_path(paper_dir: Path) -> Path:
    return paper_dir / ".paper-writing" / "references.json"


def read_references(paper_dir: Path) -> dict[str, dict]:
    """`{cite_key: record}` of the sidecar, empty when there is none. Raises
    `ValueError` for one that is not the document `resolve --references`
    writes; each caller decides what that means to it."""
    path = references_path(paper_dir)
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    records = data.get("references") if isinstance(data, dict) else None
    if not isinstance(records, dict):
        raise ValueError(f"{path.name} holds no `references` mapping")
    return {key: record for key, record in records.items() if isinstance(record, dict)}


def _reference_link(result: dict) -> str | None:
    """A DOI's or arXiv id's page, else the OpenAlex work a search found."""
    identifier = result.get("identifier") or ""
    if result.get("resolver") == "arxiv":
        return f"https://arxiv.org/abs/{quote(identifier, safe='/.-')}"
    doi = source_identity(result.get("doi") or identifier, "crossref")
    if doi is not None and doi[1].startswith("10."):
        return f"https://doi.org/{quote(doi[1], safe='/:;()._-')}"
    return identifier if identifier.startswith("https://") else None


def _reference_record(status: str, retrieved: str, identifier: str | None, result: dict | None) -> dict:
    found = result or {}
    return {
        "status": status,
        "resolver": found.get("resolver"),
        "identifier": found.get("identifier", identifier),
        "title": found.get("title"),
        "abstract": found.get("abstract"),
        "year": found.get("year"),
        "venue": found.get("venue"),
        "link": _reference_link(found) if result else None,
        "digest": found.get("metadata_digest"),
        "retrieved": retrieved,
    }


def _ask(call) -> tuple[object, bool]:
    """`(answer, failed)` of one paced request. An endpoint that names no such
    work answers `None`; one that never answers, or answers something
    unreadable, reports `failed` so the key can be retried."""
    paper_resolve.pause()
    try:
        return call(), False
    except Refused as exc:
        if exc.code == "IDENTIFIER_UNRESOLVED":
            return None, False
        if exc.code == "RESOLVER_UNREACHABLE":
            return None, True
        raise
    except (OSError, ValueError, SyntaxError, http.client.HTTPException):
        return None, True


def _best_title_match(title: str, year: str | None, works: list[dict]) -> dict | None:
    """The work carrying exactly `title`, normalized, or `None`: a near title
    is another paper. Among equals, the bib's year and then an abstract."""
    wanted = title_key(title)
    exact = [work for work in works if wanted and title_key(work.get("title")) == wanted]
    exact.sort(key=lambda work: (str(work.get("year")) != year, not work.get("abstract")))
    return exact[0] if exact else None


def _resolve_reference(entry: dict[str, str], *, connectors: list, role: str,
                       config: dict) -> tuple[str, dict | None]:
    """`(status, result)` for one bib entry: its identifiers through the
    configured connectors, then an OpenAlex title search while no abstract
    was found. Crossref never carries an abstract, so a DOI asks OpenAlex
    first and Crossref only for a work OpenAlex does not hold."""
    found, failed = None, False
    for identifier, resolver in bib_identifiers(identity_fields(entry)):
        identity = source_identity(identifier, resolver)
        chain = ("openalex", "crossref") if resolver == "crossref" else (resolver,)
        for name in chain:
            if identity is None or name not in connectors or (found and name == "crossref"):
                continue
            result, down = _ask(lambda: paper_resolve.resolve_identifier(
                identity[1], resolver=name, role=role, config=config))
            failed = failed or down
            if result and result.get("abstract"):
                return "resolved", result
            found = found or result
    title = plain_text(entry.get("title"))
    if title and "openalex" in connectors:
        works, down = _ask(lambda: paper_resolve.search_title(title, role=role, config=config))
        failed = failed or down
        year = _YEAR_RE.search(plain_text(entry.get("year") or entry.get("date")))
        match = _best_title_match(title, year.group(1) if year else None, works or [])
        if match and (found is None or match.get("abstract")):
            return "resolved", match
    if found:
        return "resolved", found
    return ("unreachable" if failed else "not_found"), None


def resolve_references(paper_dir: Path, main_tex_bytes: bytes, refs_bib_bytes: bytes, *,
                       config: dict, role: str = "resolution", force: bool = False) -> dict:
    """`resolve --references`: one sidecar record per cited key, every entry
    of the bibliography when the manuscript's citation commands are not ones
    `cited_keys` reads. A `resolved` record is reused unless `force`, and no
    failure replaces one; every other key is asked again. Reaching nothing is
    a recorded `unreachable`, never a refusal, so offline work carries on,
    while an emptied role refuses before any request or write.
    """
    connectors = paper_resolve.require_role_connectors(config, role)
    bib = parse_bib(refs_bib_bytes.decode("utf-8", errors="replace"))
    keys = sorted(cited_keys(main_tex_bytes) or bib)
    try:
        previous = read_references(paper_dir)
    except ValueError:
        previous = {}  # derived data: this run replaces what cannot be read
    retrieved = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    records: dict[str, dict] = {}
    reused = streak = 0
    for key in keys:
        kept = previous.get(key) if previous.get(key, {}).get("status") == "resolved" else None
        if kept is not None and not force:
            records[key] = kept
            reused += 1
            continue
        entry = bib.get(key)
        named = bib_identifiers(identity_fields(entry)) if entry else []
        if entry is None:
            status, result = "not_found", None
        elif streak >= _UNREACHABLE_STREAK:
            status, result = "unreachable", None
        else:
            status, result = _resolve_reference(entry, connectors=connectors, role=role, config=config)
            streak = streak + 1 if status == "unreachable" else 0
        if status != "resolved" and kept is not None:
            records[key] = kept
            continue
        records[key] = _reference_record(status, retrieved, named[0][0] if named else None, result)
    path = references_path(paper_dir)
    document = {"schema": REFERENCES_SCHEMA, "references": records}
    text = json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    paper_block._atomic_replace(path, text.encode("utf-8"))
    statuses = [record.get("status") for record in records.values()]
    return {
        "path": str(path),
        "references": len(records),
        "resolved": statuses.count("resolved"),
        "not_found": statuses.count("not_found"),
        "unreachable": statuses.count("unreachable"),
        "with_abstract": sum(1 for record in records.values() if record.get("abstract")),
        "reused": reused,
    }
