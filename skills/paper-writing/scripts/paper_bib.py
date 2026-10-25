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
    cited_keys(main_tex_bytes)           -> set[str]
    entry_keys(refs_bib_bytes)           -> set[str]
    check_reciprocal(main_tex_bytes, refs_bib_bytes) -> dict (raises CITE_WITHOUT_ENTRY / ENTRY_WITHOUT_CITE)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
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
