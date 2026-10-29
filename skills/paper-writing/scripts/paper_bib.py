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
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
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
    # Nothing reads this back: `_BIB_ENTRY_RE` is the only reader of
    # `refs.bib` and it matches cite keys alone.
    comment = f"% resolver={entry['resolver']}; metadata_digest={entry['metadata_digest']}"
    return comment + "\n" + "\n".join(lines) + "\n"


def build_refs_bib(paper_dir: Path, records: list[dict], *, guidance_dir: Path) -> dict:
    """Rebuilds `paper/refs.bib` WHOLE, sorted by cite key -- never appended
    in place (`design.md`, Decision 4). One entry per distinct `cite_key`
    among `records` (last-write-wins per key, oldest to newest). Every
    entry is checked via `entry_from_record` BEFORE a single byte is
    written, so one unsourced OR un-ingested record refuses the whole
    rebuild rather than leaving a partially-written file behind.
    """
    by_key: dict[str, dict] = {}
    for record in records:
        cite_key = record.get("cite_key")
        if cite_key:
            by_key[cite_key] = record
    entries = [
        entry_from_record(paper_dir, by_key[key], guidance_dir=guidance_dir) for key in sorted(by_key)
    ]
    text = "".join(_entry_text(entry) for entry in entries)
    refs_path = paper_dir / "refs.bib"
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
