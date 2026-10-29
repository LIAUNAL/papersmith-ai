"""paper_graph: corpus assembly, the flat id namespace, `after` edge
resolution, the derived writing order.

Pure functions over parsed `ContractHeader` records once `assemble_corpus`
has read `sections_dir` (design.md, `Internal layering`: "pure functions
over parsed records — the half a later phase reuses whole"). Ordering comes
entirely from `position`, declaration order inside `blocks`, and transcribed
`after` edges — never from a filename. Files are read in sorted-name order
only so a run is reproducible; the name itself never enters any sort key.
"""
from __future__ import annotations

import heapq
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paper_contract  # noqa: E402
import paper_declarations  # noqa: E402
import paper_guidance  # noqa: E402
import paper_verify  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_core" / "implementation"))
from impl_refusals import Refused  # noqa: E402

#: Orchestrator-settled deviation from design.md's rejected "enumerate seven
#: targets" option and from the spec's literal "resolve against the
#: skeleton fact" wording (recorded in `specs/section-contract/spec.md`'s
#: Implementation note and in tasks.md's own Notes / Deviations).
#: `skeleton` occurs exactly once across all ten shipped contracts and
#: names no body-section list anywhere, so the literal resolution has
#: nothing to read. `title-and-keywords`'s own sentence ("Every keyword
#: appears in the body") is honoured by COMPUTING "the body" instead of
#: enumerating it: every section whose `position` is strictly between
#: `abstract`'s and `back-matter`'s (positions 3-9 in the shipped corpus) —
#: looked up by section id, never a hardcoded integer or a filename.
_KEYWORD_BODY_HOLDER_SECTION = "title-and-keywords"
_KEYWORD_BODY_LOWER_ANCHOR = "abstract"
_KEYWORD_BODY_UPPER_ANCHOR = "back-matter"

#: `contract-input-partition` spec, `Requirement: Two-Heading Partition`.
#: Exact heading lines every contract's prose body must carry — checked by
#: `_verify_input_partition` below, never by a filename or a header field.
_EXTERNAL_INPUTS_HEADING = "### External inputs"
_INTERNAL_CHAIN_HEADING = "### Internal chain"

#: `internal-chain-edges` spec / `contract-input-partition` spec,
#: `Requirement: Internal-Chain Rows Name Qualified Block Ids`. A normalized
#: row's own cell OPENS with a backticked qualified id (design.md, D1: "The
#: reader consumes the leading backticked token and never reads the
#: gloss") — this is the only thing `_chain_row_id` below reads.
_CHAIN_ROW_ANCHOR_RE = re.compile(r"`([^`]+)`")
_CHAIN_ROW_SEPARATOR_RE = re.compile(r"^[-:\s]+$")

#: tasks.md 4.8b-4.8i: the PROSE -> HEADER direction no other check covers.
#: `_UNIT_PARENT_RE` matches the numbered-block heading convention six of
#: ten contracts use (`01`, `02`, `05`, `06`, `07`, `08`); the other four
#: name blocks by content (`## Funding`, `## The closing`, `## Keywords`)
#: and never match this pattern at all — the per-section gate tasks.md
#: 4.8i asks for falls out of the pattern itself, never a second flag.
#: `_UNIT_CHILD_RE` matches a `###` sub-heading naming a sub-unit
#: (`Paragraph 4a`, never `### What is cited here`, which carries no unit
#: word and is correctly ignored).
_UNIT_PARENT_RE = re.compile(r"^#{2}\s+(?:Block|Slot|Subsection)\s+(\d+)\b")
_UNIT_CHILD_RE = re.compile(r"^#{3}\s+(?:Paragraph|Block|Slot|Subsection|Part)\s+(\d+[A-Za-z]*)\b")
_ANY_TOP_HEADING_RE = re.compile(r"^#{1,2}\s")

#: A section's own ids carry the heading's number only when the ids
#: THEMSELVES are numbered (`block-1`, `slot-1`, `block-4a`) rather than
#: named by content (`mm-dataset`, `es-assessment`, `rw-closing`).
#: Measured: `01`, `02` and `05` all use the `## Slot|Subsection|Block N`
#: HEADING convention with content-named ids — a numbered heading there is
#: a human ordinal label, not a claim about a specific id, and the
#: parent-heading correspondence `_verify_block_subunits` checks only means
#: something where the ids themselves carry the number (`06`, `07`, `08`).
#: This is the precise gate 4.8i's own heading-pattern criterion widens
#: into once measured against the real corpus — a heading-pattern gate
#: alone would misfire `BLOCK_SUBUNIT_UNDECLARED` on `01`'s own
#: `## Slot 1 — The dataset` (id `mm-dataset`, no numeric suffix at all).
_NUMERIC_ID_SUFFIX_RE = re.compile(r"-\d+[A-Za-z]*$")


@dataclass(frozen=True)
class BlockRecord:
    """One block, corpus-qualified. `qualified_id` is `<section>.<block id>`
    joined with `.` — the shape `main.tex` block ids take
    (design.md, `Block ids are section-qualified for global uniqueness`)."""

    section: str
    block_id: str
    qualified_id: str
    block_index: int
    position: int
    requires_facts: tuple
    requires_declarations: tuple
    citations: str
    optional: bool
    #: `fact-production` spec, `Requirement: produces_facts Field Grammar`
    #: (design.md, Decision B) — defaulted so every existing construction
    #: site (this file's own `assemble_corpus` loop AND
    #: `tests/test_paper_decisions.py`'s own direct `BlockRecord(...)`
    #: fixture) stays green without passing it.
    produces_facts: tuple = ()
    #: `source-section-binding` spec (`the-requirement-names-the-section-
    #: that-feeds-it`, design.md Interfaces): every `(fact_id, lineage,
    #: section_title)` triple a `requires_facts` entry's `document` half
    #: declares, derived via `paper_contract.requirement_documents` — never
    #: independently listed. Defaulted to `()`, the same precedent
    #: `produces_facts` sets, so every existing construction site stays
    #: green. Inert at U1/U2: populated from the parsed header, resolved
    #: against real disk only by `_verify_source_section_bindings` (U2).
    source_bindings: tuple = ()


@dataclass(frozen=True)
class Corpus:
    """`sections`: section id -> `ContractHeader`. `blocks`: qualified id ->
    `BlockRecord`. `order_by_section`: section id -> qualified ids in
    declaration order (the order each header's own `blocks` list states)."""

    sections: dict
    blocks: dict
    order_by_section: dict
    #: `source-section-binding` spec, `Requirement: An Unmeasured Root Is
    #: Reported, Never Silently Passed`; design.md Decision B. Every
    #: distinct `SourceRoot.name` in `paper_declarations.FACT_SOURCE_ROOT
    #: .values()`, each mapped to `paper_declarations.source_root_status`'s
    #: own report — "the guard is off for this root" is always on screen,
    #: echoed by every corpus-reading verb wired against it. A
    #: `REPOSITORY`-kind root always reports `unmeasured`, by kind, per
    #: `paper_declarations.source_root_status`'s own U2b correctness
    #: repair. Defaulted to `{}`, the same precedent
    #: `produces_facts`/`source_bindings` set, so every existing direct
    #: `Corpus(...)` construction site stays green.
    source_roots: dict = field(default_factory=dict)
    #: (U3b correctness repair, `the-requirement-names-the-section-that-
    #: feeds-it`) The read-time counterpart `source_roots` already
    #: established for an unmeasured root, extended to an unbound binding:
    #: every bindable `requires_facts` entry whose own source root is
    #: MEASURED but carries no `document` half yet, reported here rather
    #: than raised. Keyed by qualified block id -> `{fact_id: {"state":
    #: "undecided", "root": root_name}}`; a fully-bound block never
    #: appears here at all (a bound fact is already visible via
    #: `BlockRecord.source_bindings`), the same parsimony a per-block
    #: report can afford that `source_roots`'s own unconditional
    #: per-root report cannot. `SECTION_BINDING_ABSENT` (`source-section-
    #: binding` spec) turns an entry surviving here into a refusal ONLY
    #: when `assemble_corpus` is called with `enforce_bindings=True` --
    #: `write`'s own gate, and nowhere else (`writing-orchestration`
    #: spec, `Requirement: Section Binding Resolution Gates write`).
    #: Defaulted to `{}`, the same precedent `source_roots` sets.
    undecided_bindings: dict = field(default_factory=dict)


def _compute_undecided_bindings(blocks: dict, source_roots: dict) -> dict:
    """Pure derivation of `Corpus.undecided_bindings` (U3b), computed
    BEFORE `Corpus` is constructed: a frozen dataclass has nowhere to
    gain this after the fact, so this runs from the same `blocks` dict
    and the same `source_roots` dict `assemble_corpus` is about to hand
    the constructor, one statement below.

    Iterates blocks and their own `requires_facts` in the SAME order
    `_verify_source_section_bindings`'s old unconditional obligation loop
    used, so the first entry `enforce_bindings=True` raises on on any
    given call is exactly the same entry that loop would have raised on
    first -- moving the obligation off assembly-time changes WHEN it can
    fire, never WHICH entry it names first.
    """
    undecided: dict = {}
    for qualified_id, record in blocks.items():
        bound_fact_ids = {fact_id for fact_id, _lineage, _title in record.source_bindings}
        for fact_id in record.requires_facts:
            root = paper_declarations.FACT_SOURCE_ROOT.get(fact_id)
            if root is None:
                continue
            status = source_roots.get(root.name)
            if status is None or status["state"] == "unmeasured":
                continue
            if fact_id not in bound_fact_ids:
                undecided.setdefault(qualified_id, {})[fact_id] = {
                    "state": "undecided",
                    "root": root.name,
                }
    return undecided


def _reconcile_source_bindings(
    qualified_id: str, header_triples: tuple, recorded_by_fact: dict,
) -> tuple:
    """Merges a block's header-declared bindings (`paper_contract.
    requirement_documents`) with bindings RECORDED via `bind`
    (`paper_declarations.read_bindings`), per fact id — `the-requirement-
    names-the-section-that-feeds-it`, U3e ruling (design.md Decision J):
    "the corpus reads bindings from `paper/`, not from the contract" no
    longer means the header half is removed (U1's own shape stays valid,
    and its tests hold it); it means `paper/`'s own recorded bindings are
    now a SECOND, equally authoritative source this function reconciles
    against the first, never a fallback consulted only when the header is
    silent.

    A fact bound by only ONE source (header alone, or `paper/` alone)
    contributes exactly that source's triples, unchanged. A fact bound by
    BOTH must name the identical lineage and the identical section-title
    SET, or this refuses `SOURCE_BINDING_CONFLICT` naming the block, the
    fact, and both sides verbatim — a disagreement between two sources
    claiming to answer the SAME question is a conflict to resolve, never
    a precedence puzzle to silently pick a winner from.
    """
    by_fact: dict = {}
    for fact_id, lineage, title in header_triples:
        by_fact.setdefault(fact_id, []).append((lineage, title))

    result = list(header_triples)
    for fact_id, info in sorted(recorded_by_fact.items()):
        recorded_titles = [(info["lineage"], title) for title in info["sections"]]
        if fact_id in by_fact:
            if sorted(by_fact[fact_id]) != sorted(recorded_titles):
                raise Refused(
                    "SOURCE_BINDING_CONFLICT",
                    f"{qualified_id}: {fact_id!r} is bound in the contract header as "
                    f"{by_fact[fact_id]!r} and recorded via 'bind' as {recorded_titles!r} "
                    "-- these must agree exactly",
                )
            continue  # the header already contributed identical triples
        result.extend((fact_id, lineage, title) for lineage, title in recorded_titles)
    return tuple(result)


def assemble_corpus(
    sections_dir: Path, *, source_base: Path | None = None, paper_dir: Path | None = None,
    enforce_bindings: bool = False, enforce_for_block: str | None = None,
) -> Corpus:
    """Parse every `*.md` under `sections_dir`, sorted by filename for
    reproducibility only. Refuses `ID_COLLISION` (work-state) when a raw
    block id equals any section id anywhere in the corpus — the one flat
    namespace design.md's `one flat id namespace; after admits section and
    block ids` decision requires.

    Also verifies every transcribed `after` edge's own `source.quote`
    against `source.file`'s prose body (`_verify_after_transcription`) —
    the half of the transcription discipline `paper_contract.parse` cannot
    check by itself, because `source.file` may name a DIFFERENT contract
    than the one declaring the edge (the shipped `abstract` -> `conclusions`
    edge is sourced in `sections/07-conclusions.md`, not its own
    `08-abstract.md`). Every file this function reads is already read
    exactly once, in the loop below — this adds no second disk pass.

    Also verifies every `### Internal chain` row transcribes to a real,
    backed `after` edge (`_verify_internal_chain`) and that no prose
    heading announces a sub-unit the header never declared
    (`_verify_block_subunits`) — `section_bodies` (section id -> its own
    body) is built in the SAME loop as `bodies`, from the same read,
    keyed by `header.section` rather than a filename.

    `source_base` (`source-section-binding` spec; design.md Decision C):
    the directory each `PROSE`-kind `paper_declarations.FACT_SOURCE_ROOT`
    root (`proposals/`, `experiments/`, ...) is resolved under; a
    `REPOSITORY`-kind root never resolves under it at all. `None` derives
    `sections_dir.parent` — the real repository root under this skill's
    shipped layout. Every root's `document-rooted`/`unmeasured` status is
    computed once here (`Corpus.source_roots`) and then consumed by
    `_verify_source_section_bindings` below, which resolves and checks
    every `document`-bound `requires_facts` entry the parsed corpus names.

    `enforce_bindings` (U3b correctness repair, design.md Decision H):
    `False` (default) — a bindable, measured, unbound entry is reported
    in `Corpus.undecided_bindings`, never raised; every read-only verb
    keeps working on a corpus that still carries an undecided binding.
    `True` — the SAME condition can raise `SECTION_BINDING_ABSENT`, scoped
    by `enforce_for_block` below. Only `paper_cli._resolve_write_gate`
    (`write`'s own first statement) ever passes `True`: drafting a block
    without knowing which section feeds it is the one moment an undecided
    binding would otherwise force an invented answer, so only that moment
    refuses.

    `enforce_for_block` (U4 correctness repair, design.md: "the block this
    `write` call names, nothing else"): the qualified id `write` is
    actually about to draft. `None` (default) — every existing direct
    caller of `enforce_bindings=True` — raises on the FIRST entry
    `Corpus.undecided_bindings` names, corpus-wide, unchanged from before
    this parameter existed. A qualified id — `_resolve_write_gate`'s own
    call — raises ONLY if THAT block's own entry survives in
    `Corpus.undecided_bindings`; a sibling block's undecided binding stays
    a report, never a refusal for a block that never named it. This is
    the same argument `source-section-binding`'s own rationale already
    makes per block ("drafting a block without knowing which section
    feeds it is the one moment an undecided binding would otherwise force
    an invented answer"): that argument reaches the block being drafted,
    never its siblings — a block requiring no bindable fact at all cannot
    invent an answer for one, so it must not be gated on a sibling's
    unresolved binding. This does NOT consult `BlockRecord.optional`: an
    optional block that IS the one being written is still gated in full.

    `paper_dir` (U3e ruling, `the-requirement-names-the-section-that-
    feeds-it`, design.md Decision J): where `paper_declarations.
    read_bindings` looks for bindings RECORDED via `bind` — `None`
    derives `resolved_base / "paper"`, this skill's own shipped default
    layout (`<repo>/paper`), the SAME convention every existing test
    fixture already follows (`self.paper_dir = self.forge_root /
    "paper"`). Read once, before the block loop, and merged per block
    with that block's own header-declared bindings by
    `_reconcile_source_bindings` — never a second, independent source of
    truth `BlockRecord.source_bindings` could silently drift from.
    """
    sections: dict = {}
    bodies: dict = {}
    section_bodies: dict = {}
    for path in sorted(sections_dir.glob("*.md")):
        data = path.read_bytes()
        header, body = paper_contract.parse(data)
        sections[header.section] = header
        bodies[f"{sections_dir.name}/{path.name}"] = body
        section_bodies[header.section] = body

    resolved_base = source_base if source_base is not None else sections_dir.parent
    resolved_paper_dir = paper_dir if paper_dir is not None else resolved_base / "paper"
    recorded_bindings = paper_declarations.read_bindings(resolved_paper_dir)

    section_ids = set(sections)
    blocks: dict = {}
    order_by_section: dict = {}
    for section_id, header in sections.items():
        order_by_section[section_id] = []
        for index, raw_block in enumerate(header.blocks):
            block_id = raw_block["id"]
            if block_id in section_ids:
                raise Refused(
                    "ID_COLLISION",
                    f"block id {block_id!r} in section {section_id!r} collides with a section id",
                )
            qualified_id = f"{section_id}.{block_id}"
            header_bindings = paper_contract.requirement_documents(raw_block["requires_facts"])
            source_bindings = _reconcile_source_bindings(
                qualified_id, header_bindings, recorded_bindings.get(qualified_id, {}),
            )
            blocks[qualified_id] = BlockRecord(
                section=section_id,
                block_id=block_id,
                qualified_id=qualified_id,
                block_index=index,
                position=header.position,
                requires_facts=paper_contract.requirement_values(raw_block["requires_facts"]),
                requires_declarations=paper_contract.requirement_values(
                    raw_block["requires_declarations"]
                ),
                citations=raw_block["citations"],
                optional=raw_block["optional"],
                produces_facts=paper_contract.requirement_values(raw_block["produces_facts"]),
                source_bindings=source_bindings,
            )
            order_by_section[section_id].append(qualified_id)

    source_roots = {
        root.name: paper_declarations.source_root_status(resolved_base, root)
        for root in sorted(set(paper_declarations.FACT_SOURCE_ROOT.values()), key=lambda r: r.name)
    }
    undecided_bindings = _compute_undecided_bindings(blocks, source_roots)

    corpus = Corpus(
        sections=sections, blocks=blocks, order_by_section=order_by_section,
        source_roots=source_roots, undecided_bindings=undecided_bindings,
    )
    _verify_input_partition(corpus, bodies)
    _verify_after_transcription(corpus, bodies)
    _verify_requirement_transcription(corpus, bodies)
    _verify_internal_chain(corpus, bodies)
    _verify_block_subunits(corpus, section_bodies)
    _verify_source_section_bindings(
        corpus, enforce_bindings=enforce_bindings, enforce_for_block=enforce_for_block,
    )
    declarations = _produces_facts_declarations(corpus)
    _verify_route_exclusivity(declarations)
    _verify_producer_duplication(declarations)
    _verify_self_reference(corpus)
    _verify_fact_totality(corpus, declarations)
    _verify_producer_reachability(corpus, declarations)
    _verify_producer_chain_rows(corpus, declarations, section_bodies)
    return corpus


def _describe_binding_absent(corpus: Corpus, qualified_id: str, fact_id: str, info: dict) -> str:
    """`SECTION_BINDING_ABSENT`'s own detail text (U3e ruling, `the-
    requirement-names-the-section-that-feeds-it`: "the refusal IS the
    question"). Names the block, the fact, the root, and — read from disk
    at this exact moment, via `paper_declarations.describe_binding_
    candidates` — every lineage that root currently carries, its own
    resolved current revision (or, for an INGESTED root, its own paper),
    and the section titles that revision actually holds right now, so a
    person can answer the refusal without opening anything. Also spells
    the exact `bind` invocation that answers it, naming this refusal's own
    block and fact — never a generic "run bind" pointer.
    """
    root = paper_declarations.FACT_SOURCE_ROOT[fact_id]
    status = corpus.source_roots[info["root"]]
    candidates = paper_declarations.describe_binding_candidates(status, root)
    detail = (
        f"{qualified_id}: {fact_id!r} is bindable and its source root {info['root']!r} is "
        f"measured, but carries no binding. Record one with `bind --block {qualified_id} "
        f"--fact {fact_id} --lineage <lineage> --section <title> [--section <title> ...]`."
    )
    if not candidates:
        return detail + f" No document was found on disk under {info['root']!r} yet."
    parts = [
        f"{lineage!r} (current: {candidate['revision']}, sections: {candidate['sections']!r})"
        for lineage, candidate in sorted(candidates.items())
    ]
    return detail + " Candidates on disk right now: " + "; ".join(parts) + "."


def resolve_section_index(source_roots: dict, root, lineage: str) -> tuple:
    """The shipped marker -> lineage -> `segment_markdown` chain,
    EXTRACTED from `_verify_source_section_bindings`'s own inline
    resolution below, so a second caller (`paper_cli.cmd_separate`,
    `the-whole-cut-is-argued-before-any-section-is-claimed`, design.md
    Decision H) reaches it instead of duplicating it -- and so a sibling
    change's own dependency can import the byte-offset OUTLINE this now
    returns, never a `{title: count}` memo alone (design.md, "Leave the
    sibling reachable").

    `source_roots` is `Corpus.source_roots` (or an identically-shaped
    dict): `root.name -> {"state", "path", ...}`
    (`paper_declarations.source_root_status`'s own return shape). `root`
    is a `paper_declarations.FACT_SOURCE_ROOT` value; its `.kind` decides
    whether resolution runs the PROSE/REPOSITORY marker-driven branch
    (`read_revisions_marker` + `resolve_lineage`) or the INGESTED identity
    branch (`resolve_ingested_document`) -- unchanged from the inline
    version this replaces.

    Returns `(revision_path, counts, outline)`: `counts` is the SAME
    `{title: int}` memo the existing verifier below consumes (a zero
    count is `SECTION_NOT_IN_SOURCE`, above one is
    `SECTION_TITLE_AMBIGUOUS`); `outline` is `paper_guidance.
    segment_markdown`'s own return shape -- `{"headings": [{"title",
    "level", "byte_start", "byte_end"}, ...]}` -- the byte-offset shape
    `paper_separation.claimable_sections` and the sibling change both
    need, never re-derived from `counts` alone.

    The caller is responsible for skipping an `unmeasured` root before
    calling this (unchanged): this function assumes `root.name` already
    resolves to a document-rooted status.
    """
    status = source_roots[root.name]
    if root.kind is paper_declarations.SourceRootKind.INGESTED:
        revision_path = paper_declarations.resolve_ingested_document(status.get("paths", [status["path"]]), lineage)
    else:
        marker = paper_declarations.read_revisions_marker(status["path"])
        if marker is None:
            raise Refused(
                "SOURCE_REVISIONS_UNDECLARED",
                paper_declarations.source_revisions_undeclared_detail(status, root),
            )
        revision_path = paper_declarations.resolve_lineage(status["path"], lineage, marker)
    body = revision_path.read_text(encoding="utf-8")
    outline = paper_guidance.segment_markdown(body)
    counts: dict = {}
    for heading in outline["headings"]:
        counts[heading["title"]] = counts.get(heading["title"], 0) + 1
    return revision_path, counts, outline


def _verify_source_section_bindings(
    corpus: Corpus, *, enforce_bindings: bool = False, enforce_for_block: str | None = None,
) -> None:
    """`source-section-binding` spec — every check a `document`-bound
    `requires_facts` entry (`BlockRecord.source_bindings`) is held to,
    against real disk. Inert for every entry with no `document` half (U1),
    and inert for every root `corpus.source_roots` reports `unmeasured`
    (design.md Decision B: an unmeasured root is reported, never a
    refusal) — resolution only ever runs against a `document-rooted` root.

    For each `(root, lineage)` pair the corpus's bindings actually name,
    under a document-rooted root, resolution branches on the root's OWN
    `kind` (design.md, `SourceRootKind`):

    1a. `PROSE`/`REPOSITORY` roots (a `REPOSITORY` root is never
        document-rooted, so it never reaches this branch in practice):
        `paper_declarations.read_revisions_marker` — `None` (absent
        marker) refuses `SOURCE_REVISIONS_UNDECLARED` naming the root; a
        malformed marker propagates `MALFORMED_SOURCE_MARKER` from the
        reader itself. `paper_declarations.resolve_lineage` then refuses
        `SOURCE_LINEAGE_UNRESOLVED` on zero or tied candidates.
    1b. `INGESTED` roots (U2c ruling): an ingested paper is not a
        revisioned lineage, so there is no marker to read at all —
        `paper_declarations.resolve_ingested_document` resolves the
        lineage by IDENTITY, refusing the SAME `SOURCE_LINEAGE_UNRESOLVED`
        on zero or more-than-one matching ingested document.
    2. The resolved document is segmented once (`paper_guidance.
       segment_markdown`) into a `{title: count}` memo, keyed by
       `(root, lineage)` — one file read per distinct pair for the WHOLE
       corpus (design.md Decision E), never one per binding. Every binding
       naming that pair is then a dict lookup: a zero count refuses
       `SECTION_NOT_IN_SOURCE`, a count above one refuses
       `SECTION_TITLE_AMBIGUOUS`, both naming the owning block and the
       title.

    0. (U3b correctness repair, `the-requirement-names-the-section-that-
       feeds-it` — U3's own unconditional version of this step forced an
       agent to INVENT two bindings rather than leave the corpus
       assemblable at all, which the owner ruled worse than the defect it
       fixed) `Corpus.undecided_bindings` already names every bindable,
       measured, unbound entry (`_compute_undecided_bindings`, run before
       this function, before `Corpus` even exists). `enforce_bindings=False`
       (every read-only verb's own default) leaves that report as a
       report: this step raises NOTHING for it. `enforce_bindings=True`
       (`write`'s own gate, and ONLY `write`'s) can turn a surviving entry
       into `SECTION_BINDING_ABSENT`, naming the owning block and the fact
       id — SCOPED by `enforce_for_block` (U4 correctness repair): `None`
       raises on the first entry `Corpus.undecided_bindings` names, in the
       SAME block order the old unconditional obligation loop used,
       corpus-wide — the shape every existing direct `enforce_bindings=True`
       caller still gets. A qualified id (`_resolve_write_gate`'s own
       call) raises ONLY when THAT block's own entry survives; a sibling
       block's undecided binding is left standing in the report, never
       raised for a block that does not name it — the per-block rationale
       above ("drafting a block without knowing which section feeds it is
       the one moment an undecided binding would otherwise force an
       invented answer") only ever reached the block being drafted, never
       its 46 siblings, and a block with no bindable fact at all cannot
       invent an answer for one. Either way the obligation stays
       UNCONDITIONAL for the block actually being enforced against, and
       still never consults `BlockRecord.optional`: an optional block that
       IS the one being written is still gated in full.
    """
    if enforce_bindings:
        if enforce_for_block is not None:
            facts = corpus.undecided_bindings.get(enforce_for_block)
            if facts:
                fact_id, info = next(iter(facts.items()))
                raise Refused(
                    "SECTION_BINDING_ABSENT",
                    _describe_binding_absent(corpus, enforce_for_block, fact_id, info),
                )
        else:
            for qualified_id, facts in corpus.undecided_bindings.items():
                fact_id, info = next(iter(facts.items()))
                raise Refused(
                    "SECTION_BINDING_ABSENT",
                    _describe_binding_absent(corpus, qualified_id, fact_id, info),
                )

    memo: dict = {}
    for qualified_id, record in corpus.blocks.items():
        for fact_id, lineage, section_title in record.source_bindings:
            root = paper_declarations.FACT_SOURCE_ROOT.get(fact_id)
            if root is None:
                continue
            status = corpus.source_roots.get(root.name)
            if status is None or status["state"] == "unmeasured":
                continue

            memo_key = (root.name, lineage)
            if memo_key not in memo:
                memo[memo_key] = resolve_section_index(corpus.source_roots, root, lineage)

            revision_path, counts, _outline = memo[memo_key]
            count = counts.get(section_title, 0)
            if count == 0:
                raise Refused(
                    "SECTION_NOT_IN_SOURCE",
                    f"{qualified_id}: section {section_title!r} is not a heading in "
                    f"{revision_path.name} (lineage {lineage!r})",
                )
            if count > 1:
                raise Refused(
                    "SECTION_TITLE_AMBIGUOUS",
                    f"{qualified_id}: section {section_title!r} matches {count} headings in "
                    f"{revision_path.name} (lineage {lineage!r})",
                )


def _verify_input_partition(corpus: Corpus, bodies: dict) -> None:
    """`contract-input-partition` spec, `Requirement: Two-Heading
    Partition`. Refuses `INPUT_PARTITION_ABSENT` (work-state) naming
    whichever of `### External inputs` / `### Internal chain` is missing
    from a contract's own prose body — reads the SAME `bodies` dict
    `_verify_after_transcription` already holds, so this costs zero extra
    disk passes. `corpus` is accepted for the same signature shape as its
    sibling `_verify_internal_chain` (design.md, Interfaces / Contracts);
    the check itself is purely a body-text scan, no corpus data needed.

    `### Internal chain` is checked first: when a flat, unpartitioned
    contract carries neither heading, naming the internal-chain gap is the
    more actionable report, since that is the half this change exists to
    make explicit and machine-addressable (`specs/contract-input-
    partition/spec.md`'s own "flat, unpartitioned contract" scenario)."""
    for file_key, body in bodies.items():
        text = body.decode("utf-8")
        for heading in (_INTERNAL_CHAIN_HEADING, _EXTERNAL_INPUTS_HEADING):
            if not re.search(rf"(?m)^{re.escape(heading)}\s*$", text):
                raise Refused(
                    "INPUT_PARTITION_ABSENT",
                    f"{file_key}: missing {heading!r} heading in the contract's prose body",
                )


def _verify_after_transcription(corpus: Corpus, bodies: dict) -> None:
    """Enforces, for every transcribed `after` entry whose OWN `target`
    resolves to something real in this corpus (`_resolve_target` below —
    reused rather than re-derived), the same transcription discipline
    `paper_contract.parse` already enforces for `mode`: the entry's
    `source.quote` must be a literal (whitespace-collapsed, markdown-
    emphasis-stripped) substring of `source.file`'s own prose body —
    `paper_contract.quote_in_body`, the one shared check, never a second
    copy of it.

    Skipped for a DANGLING target on purpose: `design.md`'s own "An
    absent after target is reported, never refused" already treats a
    dangling target as a legitimate, reportable state (deleting a
    contract mid-edit is explicitly in scope) — refusing on the quote of
    an edge that already names nothing would conflate two independent
    failures under one refusal. Every shipped `after` edge resolves, so
    this narrowing costs the real corpus nothing.
    """
    for section_id, header in corpus.sections.items():
        entries = list(header.after)
        for raw_block in header.blocks:
            entries += raw_block["after"]

        for entry in entries:
            if _resolve_target(corpus, entry["target"]) is None:
                continue
            source = entry["source"]
            body = bodies.get(source["file"])
            if body is None or not paper_contract.quote_in_body(body, source["quote"]):
                raise Refused(
                    "SPAN_NOT_IN_SOURCE",
                    f"{section_id}: after-edge quote {source['quote']!r} not found verbatim "
                    f"(whitespace-collapsed, markdown-emphasis-stripped) in "
                    f"{source['file']}'s prose body",
                )


def _verify_requirement_transcription(corpus: Corpus, bodies: dict) -> None:
    """Enforces, for every `requires_facts` / `requires_declarations`
    entry, the same transcription discipline `_verify_after_transcription`
    enforces for `after` edges: the entry's `source.quote` must be a
    literal (whitespace-collapsed, markdown-emphasis-stripped) substring of
    `source.file`'s own prose body — `paper_contract.quote_in_body`, the
    one shared check, never a second copy of it (`requirement-transcription`
    spec, `Requirement: Transcribed Requirement Entries Only`).

    U3 (design.md D3) makes `source` unconditionally required at the shape
    layer (`paper_contract._normalize_requirement_entry`), so every entry
    reaching this function always carries one — unlike `after`'s own
    dangling-target case, there is no legitimate reason to skip an entry
    here. Reads the SAME `bodies` dict its siblings already hold — zero
    extra disk passes.

    `a-fact-is-declared-or-it-is-produced` (`fact-production` spec,
    `Requirement: Transcribed produces_facts Entries Only`; design.md,
    Decision B) widens the block-level tuple with `produces_facts` — the
    entry shape is byte-identical to `requires_facts`, so no second check
    is written, only one more field name walked. The section-level half
    (`header.produces_facts`) is walked SEPARATELY, the same way
    `paper_contract._verify_mode_transcription` already walks `header.mode`
    apart from block-level `mode` entries — `requires_facts` /
    `requires_declarations` have no section-level counterpart, so only
    `produces_facts` needs this extra loop.
    """
    for section_id, header in corpus.sections.items():
        for entry in header.produces_facts:
            source = entry["source"]
            body = bodies.get(source["file"])
            if body is None or not paper_contract.quote_in_body(body, source["quote"]):
                raise Refused(
                    "SPAN_NOT_IN_SOURCE",
                    f"{section_id}: produces_facts quote {source['quote']!r} for "
                    f"{entry['value']!r} not found verbatim (whitespace-collapsed, "
                    f"markdown-emphasis-stripped) in {source['file']}'s prose body",
                )
        for raw_block in header.blocks:
            block_id = raw_block["id"]
            for field in ("requires_facts", "requires_declarations", "produces_facts"):
                for entry in raw_block[field]:
                    source = entry["source"]
                    body = bodies.get(source["file"])
                    if body is None or not paper_contract.quote_in_body(body, source["quote"]):
                        raise Refused(
                            "SPAN_NOT_IN_SOURCE",
                            f"{section_id}.{block_id}: {field} quote {source['quote']!r} for "
                            f"{entry['value']!r} not found verbatim (whitespace-collapsed, "
                            f"markdown-emphasis-stripped) in {source['file']}'s prose body",
                        )


def _produces_facts_declarations(corpus: Corpus) -> list:
    """Every `(fact_id, producer_qualified_id)` pair a `produces_facts`
    entry declares, section- and block-level alike — the producer id is the
    qualified SECTION id for a section-level entry, the qualified BLOCK id
    for a block-level one. Shared by `_verify_route_exclusivity` and
    `_verify_producer_duplication` below so both read the same scan
    (`fact-production` spec, `Requirement: produces_facts Field Grammar` /
    `Requirement: Every Producer Is Either Sole Or Corroborated`)."""
    declarations: list = []
    for section_id, header in corpus.sections.items():
        for entry in header.produces_facts:
            declarations.append((entry["value"], section_id))
        for raw_block in header.blocks:
            qualified_id = f"{section_id}.{raw_block['id']}"
            for entry in raw_block["produces_facts"]:
                declarations.append((entry["value"], qualified_id))
    return declarations


#: `fact-production` spec, `Requirement: Every Producer Is Either Sole Or
#: Corroborated`: the facts declarable through `paper_declarations` (never
#: written by a block) — a `produces_facts` entry naming one of these is a
#: route conflict, not a legitimate production claim.
_DECLARABLE_ROUTE_FACTS = frozenset(
    paper_declarations.OBSERVABLE_FACTS
) | frozenset(paper_declarations.STRUCTURAL_FACTS)


def _verify_route_exclusivity(declarations: list) -> None:
    """Refuses `FACT_ROUTE_AMBIGUOUS` (work-state) naming the producer and
    the fact, when a `produces_facts` entry names a fact that only
    resolves through the declarable route (`paper_declarations.
    OBSERVABLE_FACTS ∪ STRUCTURAL_FACTS`) — design.md, Refusal Codes #4."""
    for fact_id, producer_id in declarations:
        if fact_id in _DECLARABLE_ROUTE_FACTS:
            raise Refused(
                "FACT_ROUTE_AMBIGUOUS",
                f"{producer_id}: 'produces_facts' names {fact_id!r}, which is only "
                f"ever declared or structurally resolved, never produced by a block",
            )


def _verify_producer_duplication(declarations: list) -> None:
    """Refuses `FACT_PRODUCER_DUPLICATE` (work-state) naming the fact and
    every competing producer, for a fact named by two or more blocks'
    `produces_facts` — UNLESS it is named by EXACTLY two, and an existing
    coupling-verification check names that fact (`paper_verify.CHECKS`,
    e.g. `gap` / Coupling 3): corroboration is checked structurally, by
    asking the real, existing coupling roster, never by a hand-listed
    exception list of fact ids here (`fact-production` spec, `Requirement:
    Every Producer Is Either Sole Or Corroborated`; design.md, Decision F)."""
    producers_by_fact = _producers_by_fact(declarations)
    for fact_id, producer_ids in producers_by_fact.items():
        if len(producer_ids) < 2:
            continue
        if len(producer_ids) == 2 and fact_id in paper_verify.CHECKS:
            continue
        raise Refused(
            "FACT_PRODUCER_DUPLICATE",
            f"{fact_id!r} is produced by {sorted(producer_ids)!r}",
        )


def _verify_self_reference(corpus: Corpus) -> None:
    """Refuses `FACT_SELF_REQUIRED` (work-state) naming the block and the
    fact, when a block's `produces_facts` and `requires_facts` name the
    same fact id (`fact-production` spec, `Requirement: A Block MUST NOT
    Require What It Produces`)."""
    for qualified_id, record in corpus.blocks.items():
        overlap = set(record.requires_facts) & set(record.produces_facts)
        if overlap:
            fact_id = sorted(overlap)[0]
            raise Refused(
                "FACT_SELF_REQUIRED",
                f"{qualified_id}: requires and produces {fact_id!r}",
            )


def _producers_by_fact(declarations: list) -> dict:
    """`fact_id -> [producer_id, ...]`, the same grouping
    `_verify_producer_duplication` derives inline — factored out so
    `_verify_fact_totality` and `_verify_producer_reachability` share one
    derivation rather than each re-scanning `declarations` its own way."""
    producers_by_fact: dict = {}
    for fact_id, producer_id in declarations:
        producers_by_fact.setdefault(fact_id, []).append(producer_id)
    return producers_by_fact


def producers_by_fact(corpus: Corpus) -> dict:
    """Public counterpart to `_producers_by_fact`, for a caller outside this
    module that already holds an assembled `Corpus` and needs `fact_id ->
    (qualified_producer_id, ...)` without re-deriving the scan itself —
    `a-fact-is-declared-or-it-is-produced`, tasks.md Unit 3: `paper_
    readiness`/`paper_cli` resolve `produced_by` for `readiness`/`phases`/
    `declare`/the Components Check through this one function, the same
    derivation `_verify_producer_duplication`/`_verify_fact_totality`/
    `_verify_producer_reachability` already share above. Every id here is
    QUALIFIED (`<section>.<block>`, or a bare section id for a section-level
    `produces_facts` entry) — the same vocabulary `corpus.blocks` and
    `opened_blocks` (qualified block ids opened in `main.tex`) already
    speak. `paper_coupling_evidence.py`'s OWN `producers_by_fact` is a
    separate, RAW-id derivation for `evidence.block_bodies`'s own
    vocabulary — never this function, so `check_chain`'s `zip(block_ids,
    links)` alignment is never at risk of a qualified/raw id mismatch."""
    raw = _producers_by_fact(_produces_facts_declarations(corpus))
    return {fact_id: tuple(ids) for fact_id, ids in raw.items()}


def _verify_fact_totality(corpus: Corpus, declarations: list) -> None:
    """Refuses `FACT_PRODUCER_ABSENT` (work-state) naming a fact some block
    REQUIRES (`requires_facts`, excluding the structural `skeleton` fact,
    resolved by the existing skeleton-startup mechanism) that resolves
    through neither `paper_declarations.FACT_SOURCE_ROOT` (the five
    observable facts, always externally available) nor any block's
    `produces_facts` (`fact-production` spec, `Requirement: Every Producer
    Is Either Sole Or Corroborated`; design.md, Decision D:
    'Totality is relative to consumption'). A produced-class fact that no
    block requires needs no producer — it is simply absent from this paper,
    legally; an unconditional (never-required) totality invariant is
    precisely what broke every raw-header fixture in the previous change."""
    producers_by_fact = _producers_by_fact(declarations)
    required_facts = {
        fact_id for record in corpus.blocks.values() for fact_id in record.requires_facts
    }
    for fact_id in sorted(required_facts):
        if fact_id in paper_declarations.STRUCTURAL_FACTS:
            continue
        if fact_id in paper_declarations.FACT_SOURCE_ROOT:
            continue
        if fact_id in producers_by_fact:
            continue
        raise Refused(
            "FACT_PRODUCER_ABSENT",
            f"{fact_id!r} is required but has no producer: absent from "
            f"FACT_SOURCE_ROOT and named by no block's produces_facts",
        )


def _verify_producer_reachability(corpus: Corpus, declarations: list) -> None:
    """Refuses `PRODUCER_CHAIN_ABSENT` (work-state) naming the consumer, the
    fact, and the producer, when a block requiring a produced-class fact is
    not reachable, in the `after`-edge block graph (`collect_edges` /
    `_build_graph` — the SAME graph `derive_order`/`derive_waves` consume),
    from every one of that fact's producer block(s) (`internal-chain-edges`
    spec / `contract-input-partition` spec; design.md, Decision C: refuse
    unless the producer reaches every consumer, never a derived edge and
    never a required DIRECT edge — a cycle can only ever come from the
    hand-written corpus, and an indirect, transitively-backed chain is
    legal). `gap`'s corroborated pair (design.md, Decision F) means BOTH
    producers must reach a `gap` consumer — satisfaction requires every
    producer opened (Decision E), so the writing order must guarantee both
    precede it."""
    producers_by_fact = _producers_by_fact(declarations)
    if not producers_by_fact:
        return
    successors, _indegree = _build_graph(corpus, collect_edges(corpus))
    for qualified_id, record in corpus.blocks.items():
        for fact_id in record.requires_facts:
            producer_ids = producers_by_fact.get(fact_id)
            if not producer_ids:
                continue
            for producer_id in producer_ids:
                if producer_id == qualified_id:
                    continue  # FACT_SELF_REQUIRED already refuses this shape
                if not _reaches(successors, producer_id, qualified_id):
                    raise Refused(
                        "PRODUCER_CHAIN_ABSENT",
                        f"{qualified_id}: requires {fact_id!r}, produced by "
                        f"{producer_id!r}, but {producer_id!r} does not reach "
                        f"{qualified_id!r} in the writing order",
                    )


def _reaches(successors: dict, source: str, target: str) -> bool:
    """Iterative, cycle-tolerant DFS (a visited set, never unbounded
    recursion) over `successors` — `True` when `target` is reachable from
    `source`, `False` when `source` names no node in the graph at all (a
    section-level producer id, never measured in the shipped corpus, whose
    every block would need to be checked individually instead)."""
    if source not in successors:
        return False
    visited = {source}
    stack = [source]
    while stack:
        node = stack.pop()
        for successor in successors.get(node, ()):
            if successor == target:
                return True
            if successor not in visited:
                visited.add(successor)
                stack.append(successor)
    return False


def _verify_producer_chain_rows(corpus: Corpus, declarations: list, section_bodies: dict) -> None:
    """`contract-input-partition` spec, `Requirement: A Produced-Fact
    Dependency Is An Internal-Chain Row`. `_verify_producer_reachability`
    above proves the producer reaches the consumer somewhere in the
    `after`-edge graph, transitively or not (Decision C); this is its
    mirror in the DOCUMENTATION direction, the same way `_verify_internal_
    chain` (ROW -> edge) and this function (EDGE -> row) are mirrors of
    each other rather than one check re-derived twice: a reachable producer
    is not enough on its own — the consumer's OWN `### Internal chain`
    table, in its OWN section's prose body, must carry a row whose
    dependency cell resolves to that exact producer's qualified id. Refuses
    `PRODUCER_CHAIN_ABSENT` (work-state, the SAME code the reachability
    check raises — both are two ways the identical guarantee, 'the reader
    can find in prose why this producer must precede this consumer', can be
    missing) naming the consumer, the fact, and the producer.

    Reads `section_bodies` (section id -> its own body, the same dict
    `_verify_block_subunits` already holds from `assemble_corpus`'s single
    read loop) rather than the file-keyed `bodies` dict `_verify_internal_
    chain` reads — a row lives in the CONSUMER's own section file, and
    `record.section` is a semantic section id, not a filename, so this
    reuses the one dict that is already keyed the way this lookup needs,
    costing zero extra disk passes.
    """
    producers_by_fact = _producers_by_fact(declarations)
    if not producers_by_fact:
        return
    rows_by_section: dict = {}
    for section_id, body in section_bodies.items():
        pairs = set()
        for holder_cell, dependency_cell in _internal_chain_rows(body.decode("utf-8")):
            holder_id = _chain_row_id(holder_cell)
            dependency_id = _chain_row_id(dependency_cell)
            if holder_id is not None and dependency_id is not None:
                pairs.add((holder_id, dependency_id))
        rows_by_section[section_id] = pairs

    for qualified_id, record in corpus.blocks.items():
        for fact_id in record.requires_facts:
            producer_ids = producers_by_fact.get(fact_id)
            if not producer_ids:
                continue
            for producer_id in producer_ids:
                if producer_id == qualified_id:
                    continue  # FACT_SELF_REQUIRED already refuses this shape
                pairs = rows_by_section.get(record.section, set())
                if (qualified_id, producer_id) not in pairs:
                    raise Refused(
                        "PRODUCER_CHAIN_ABSENT",
                        f"{qualified_id}: requires {fact_id!r}, produced by "
                        f"{producer_id!r}, but no '### Internal chain' row in "
                        f"{record.section!r} names {producer_id!r} as a dependency",
                    )


def _internal_chain_rows(text: str) -> list:
    """Every data row of a contract's own `### Internal chain` markdown
    table, as `(holder_cell, dependency_cell)` raw text pairs — bounded by
    the next `##`/`###` heading, or EOF when none follows. A contract
    reporting no internal dependencies (`04`/`07`'s own checkable "None —
    ..." prose, no table at all) yields an empty list: nothing for
    `_verify_internal_chain` to check for that file, matching the
    genuinely-empty case `contract-input-partition` already accepts."""
    match = re.search(rf"(?m)^{re.escape(_INTERNAL_CHAIN_HEADING)}\s*$", text)
    if match is None:
        return []
    section_text = text[match.end():]
    next_heading = re.search(r"(?m)^#{2,3}\s", section_text)
    if next_heading is not None:
        section_text = section_text[:next_heading.start()]

    rows = []
    for line in section_text.splitlines():
        line = line.strip()
        if not (line.startswith("|") and line.endswith("|")):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) != 2:
            continue
        holder_cell, dependency_cell = cells
        if holder_cell == "Block" and dependency_cell == "Depends on":
            continue  # the table's own header row
        if _CHAIN_ROW_SEPARATOR_RE.match(holder_cell):
            continue  # the `|---|---|` separator row
        rows.append((holder_cell, dependency_cell))
    return rows


def _chain_row_id(cell: str) -> str | None:
    """A row cell's own LEADING backticked token — `_resolve_target`'s
    exact input shape — or `None` when the cell opens on prose instead
    (design.md, D1: "The reader consumes the leading backticked token and
    never reads the gloss")."""
    match = _CHAIN_ROW_ANCHOR_RE.match(cell)
    return match.group(1) if match else None


def _verify_internal_chain(corpus: Corpus, bodies: dict) -> None:
    """`internal-chain-edges` spec, both Requirements; `contract-input-
    partition` spec, `Requirement: Internal-Chain Rows Name Qualified Block
    Ids`. Reads the SAME `bodies` dict `_verify_after_transcription`
    already holds — zero extra disk passes (design.md, Data Flow).

    For every `### Internal chain` row: refuses `CHAIN_ROW_UNRESOLVED`
    (naming the row's own text) when either cell's leading backticked
    token is missing or is not a key of `corpus.blocks`; refuses
    `CHAIN_ROW_UNBACKED` (naming the holder and the dependency) when both
    resolve but no `after` edge backs `(dependency, holder)` in the block
    graph. Reuses `collect_edges` for the live edge set — never a second,
    independent edge derivation that could disagree with the one `order`/
    `readiness`/`derive_waves` actually consume.
    """
    edge_pairs = {(before, after) for before, after, _source in collect_edges(corpus).edges}
    for file_key, body in bodies.items():
        text = body.decode("utf-8")
        for holder_cell, dependency_cell in _internal_chain_rows(text):
            row_text = f"{holder_cell} | {dependency_cell}"
            holder_id = _chain_row_id(holder_cell)
            dependency_id = _chain_row_id(dependency_cell)
            if holder_id is None or holder_id not in corpus.blocks:
                raise Refused(
                    "CHAIN_ROW_UNRESOLVED",
                    f"{file_key}: {row_text!r} names no qualified block id for its subject",
                )
            if dependency_id is None or dependency_id not in corpus.blocks:
                raise Refused(
                    "CHAIN_ROW_UNRESOLVED",
                    f"{file_key}: {row_text!r} names no qualified block id for its dependency",
                )
            if (dependency_id, holder_id) not in edge_pairs:
                raise Refused(
                    "CHAIN_ROW_UNBACKED",
                    f"{file_key}: {holder_id} depends on {dependency_id}, but no "
                    f"'after' edge backs that pair",
                )


def _numbered_block_ids(corpus: Corpus, section_id: str, number: str) -> list:
    """Every declared id in `section_id` whose own local suffix — after the
    last `-` — starts with `number` (`block-4a` and `block-4b` both match
    `number='4'`; `block-1` matches `number='1'` and nothing else does).
    The correspondence a numbered `##`/`###` heading makes with the
    header's OWN declared ids — read from `corpus`, never assumed from the
    heading text alone."""
    matches = []
    for qualified_id in corpus.order_by_section[section_id]:
        suffix = qualified_id.rsplit("-", 1)[-1]
        if re.match(rf"^{re.escape(number)}[A-Za-z]*$", suffix):
            matches.append(qualified_id)
    return matches


def _section_uses_numbered_ids(corpus: Corpus, section_id: str) -> bool:
    """Whether `section_id`'s own declared ids are themselves numbered
    (see `_NUMERIC_ID_SUFFIX_RE`'s own comment for the measured reason
    `01`, `02` and `05` are excluded here even though all three use the
    `## Slot|Subsection|Block N` HEADING convention)."""
    return any(_NUMERIC_ID_SUFFIX_RE.search(qid) for qid in corpus.order_by_section[section_id])


def _verify_block_subunits(corpus: Corpus, section_bodies: dict) -> None:
    """tasks.md, 4.8b-4.8i: the PROSE -> HEADER direction no other check
    covers. Every other refusal this change ships checks TABLE -> GRAPH (a
    chain row naming a block); this is the sibling direction — a heading
    announcing a sub-unit, or claiming a single numbered unit, that the
    front matter does not back with exactly the declared id(s) it implies.

    Scoped BY CONSTRUCTION to sections whose own ids are themselves
    numbered (`_section_uses_numbered_ids`) — `01`, `02`, `05` (numbered
    HEADINGS, content-named ids) and `03`, `04`, `09`, `10` (content-named
    headings too) never enter either branch below; no second per-section
    flag, the gate is measured directly off the declared ids.

    Refuses `BLOCK_SUBUNIT_UNDECLARED` when a numbered heading (parent or
    child) resolves to ZERO declared ids under loose suffix matching (a
    number no id anywhere carries at all), and the new
    `UNIT_HEADING_AMBIGUOUS` when a PARENT heading resolves to MORE THAN
    ONE id — the exact residue `06`'s own block-4 split left behind before
    4.8g's fix, `## Block 4` matching both `block-4a` and `block-4b` under
    loose suffix matching with no children to disambiguate it — UNLESS its
    own heading text already names every one of them in backticks: an
    explicit grouping, not an accident.
    """
    for section_id, body in section_bodies.items():
        if not _section_uses_numbered_ids(corpus, section_id):
            continue
        text = body.decode("utf-8")
        current_parent = None
        for line in text.splitlines():
            parent_match = _UNIT_PARENT_RE.match(line)
            if parent_match:
                number = parent_match.group(1)
                matches = _numbered_block_ids(corpus, section_id, number)
                if not matches:
                    raise Refused(
                        "BLOCK_SUBUNIT_UNDECLARED",
                        f"{section_id}: heading {line.strip()!r} names no declared block id",
                    )
                if len(matches) > 1:
                    local_ids = [qid.split(".", 1)[1] for qid in matches]
                    if not all(f"`{local_id}`" in line for local_id in local_ids):
                        raise Refused(
                            "UNIT_HEADING_AMBIGUOUS",
                            f"{section_id}: heading {line.strip()!r} resolves to "
                            f"{sorted(matches)!r} — name every one in the heading "
                            f"itself to declare it an explicit grouping",
                        )
                current_parent = line
                continue
            if _ANY_TOP_HEADING_RE.match(line):
                current_parent = None
                continue
            child_match = _UNIT_CHILD_RE.match(line)
            if child_match and current_parent is not None:
                identifier = child_match.group(1)
                matches = _numbered_block_ids(corpus, section_id, identifier)
                if not matches:
                    raise Refused(
                        "BLOCK_SUBUNIT_UNDECLARED",
                        f"{section_id}: heading {line.strip()!r} (under "
                        f"{current_parent.strip()!r}) names no declared block id",
                    )


def _resolve_target(corpus: Corpus, target_id: str) -> list | None:
    """A transcribed `after`'s `target` names a section (expands to every
    block of it, in declaration order) or a block (already section-
    qualified: a single-element list). `None` when it resolves to neither —
    the caller records it as a dangling edge rather than refusing
    (design.md, `An absent after target is reported, never refused`)."""
    if target_id in corpus.sections:
        return list(corpus.order_by_section[target_id])
    if target_id in corpus.blocks:
        return [target_id]
    return None


@dataclass
class EdgeSet:
    """`edges`: `(before_qualified_id, after_qualified_id, source)` triples
    -- `before` must be written first. `source` is the transcribing
    `{"file", "quote"}` dict, or `None` for the position-derived edge.
    `dangling`: every `after` target that resolved to nothing."""

    edges: list
    dangling: list


def collect_edges(corpus: Corpus) -> EdgeSet:
    """Every transcribed `after` edge, section- and block-level, plus the
    one position-derived edge (module docstring). This is the FULL edge
    list the topological sort consumes; a caller wanting only the literal,
    header-declared cross-section subset filters this same list by
    holder-section-vs-target-section, never hand-listing it."""
    edges: list = []
    dangling: list = []

    for section_id, header in corpus.sections.items():
        holder_blocks = corpus.order_by_section[section_id]

        for entry in header.after:
            targets = _resolve_target(corpus, entry["target"])
            if targets is None:
                dangling.append(entry["target"])
                continue
            for target_qualified in targets:
                for holder_qualified in holder_blocks:
                    edges.append((target_qualified, holder_qualified, entry["source"]))

        for raw_block, holder_qualified in zip(header.blocks, holder_blocks):
            for entry in raw_block["after"]:
                targets = _resolve_target(corpus, entry["target"])
                if targets is None:
                    dangling.append(entry["target"])
                    continue
                for target_qualified in targets:
                    edges.append((target_qualified, holder_qualified, entry["source"]))

    edges.extend(_position_derived_edges(corpus))

    return EdgeSet(edges=edges, dangling=dangling)


def _position_derived_edges(corpus: Corpus) -> list:
    """See module docstring / `_KEYWORD_BODY_*` constants."""
    if (_KEYWORD_BODY_HOLDER_SECTION not in corpus.sections
            or _KEYWORD_BODY_LOWER_ANCHOR not in corpus.sections
            or _KEYWORD_BODY_UPPER_ANCHOR not in corpus.sections):
        return []

    lower = corpus.sections[_KEYWORD_BODY_LOWER_ANCHOR].position
    upper = corpus.sections[_KEYWORD_BODY_UPPER_ANCHOR].position
    holder_blocks = corpus.order_by_section[_KEYWORD_BODY_HOLDER_SECTION]

    edges = []
    for section_id, header in corpus.sections.items():
        if section_id == _KEYWORD_BODY_HOLDER_SECTION:
            continue
        if lower < header.position < upper:
            for target_qualified in corpus.order_by_section[section_id]:
                for holder_qualified in holder_blocks:
                    edges.append((target_qualified, holder_qualified, None))
    return edges


def _sort_key(corpus: Corpus, qualified_id: str) -> tuple:
    """`(section.position, block_index_within_section, block_id)` — every
    component read from the header, none from dict iteration, `os.listdir`
    or the filename (design.md, `The sort, and how ties are broken`)."""
    record = corpus.blocks[qualified_id]
    return (record.position, record.block_index, qualified_id)


def _build_graph(corpus: Corpus, edge_set: EdgeSet) -> tuple:
    """`(successors, indegree)` — the adjacency shape both `derive_order`
    (one flattened total order) and `derive_waves` (the same graph's
    successive Kahn frontiers, thrown away by `derive_order`'s own min-heap
    today) sort over. `successors[qid]` lists ids that must be written
    after `qid`; `indegree[qid]` counts unmet `after` dependencies. Pure —
    no mutation of `corpus` or `edge_set`, no disk read."""
    successors: dict = {qid: [] for qid in corpus.blocks}
    indegree: dict = {qid: 0 for qid in corpus.blocks}
    for before, after, _source in edge_set.edges:
        successors[before].append(after)
        indegree[after] += 1
    return successors, indegree


def derive_order(corpus: Corpus, edge_set: EdgeSet) -> list:
    """Kahn's algorithm over the block graph, min-heap tie-broken by
    `_sort_key`. Refuses `ORDER_CYCLE` (work-state), naming the
    participating blocks, when Kahn terminates with nodes remaining — a
    minimal cycle extracted by DFS over the residual subgraph.
    """
    successors, indegree = _build_graph(corpus, edge_set)

    heap = [(_sort_key(corpus, qid), qid) for qid, degree in indegree.items() if degree == 0]
    heapq.heapify(heap)

    remaining_indegree = dict(indegree)
    order: list = []
    while heap:
        _key, qid = heapq.heappop(heap)
        order.append(qid)
        for successor in successors[qid]:
            remaining_indegree[successor] -= 1
            if remaining_indegree[successor] == 0:
                heapq.heappush(heap, (_sort_key(corpus, successor), successor))

    if len(order) != len(corpus.blocks):
        remaining = set(corpus.blocks) - set(order)
        cycle = _extract_minimal_cycle(remaining, successors)
        raise Refused("ORDER_CYCLE", f"a cycle among blocks: {' -> '.join(cycle)}")

    return order


def _extract_minimal_cycle(remaining: set, successors: dict) -> list:
    """DFS over the residual subgraph (`remaining` nodes only) for one
    cycle, reported as an ordered id list. Deterministic: nodes are tried
    in sorted order, so a given residual subgraph always reports the same
    cycle."""
    visiting: set = set()
    visited: set = set()
    path: list = []

    def dfs(node: str):
        visiting.add(node)
        path.append(node)
        for successor in successors[node]:
            if successor not in remaining:
                continue
            if successor in visiting:
                start = path.index(successor)
                return path[start:] + [successor]
            if successor not in visited:
                found = dfs(successor)
                if found is not None:
                    return found
        visiting.discard(node)
        visited.add(node)
        path.pop()
        return None

    for start_node in sorted(remaining):
        if start_node in visited:
            continue
        found = dfs(start_node)
        if found is not None:
            return found
    return sorted(remaining)


def derive_waves(corpus: Corpus, edge_set: EdgeSet) -> list:
    """The same block graph `derive_order` flattens, reported instead as
    waves 1..N — every wave the full set of blocks whose in-degree in the
    residual graph reaches zero at that Kahn round, tie-broken WITHIN a
    wave the same way `derive_order` tie-breaks (`_sort_key`). Reuses
    `_build_graph` (design.md D2) — no second graph construction, no
    second sort key. Refuses `ORDER_CYCLE`, the identical detail string
    `derive_order` raises via the same `_extract_minimal_cycle`, when
    nodes remain unassigned once the frontier is exhausted.

    `derive_order`'s own min-heap holds ready nodes from SEVERAL frontiers
    at once (a node from wave 2 can out-rank, by `_sort_key`, a still-
    unpopped node from wave 1), so its flattened sequence legitimately
    interleaves waves. Flattening THIS function's waves is therefore never
    asserted equal to `derive_order`'s sequence — only that both name the
    same node set, and that every edge crosses a wave boundary
    (design.md D2, invariants 1/2/5; `specs/writing-phases/spec.md`).
    """
    successors, indegree = _build_graph(corpus, edge_set)

    remaining_indegree = dict(indegree)
    frontier = sorted(
        (qid for qid, degree in remaining_indegree.items() if degree == 0),
        key=lambda qid: _sort_key(corpus, qid),
    )

    waves: list = []
    written = 0
    while frontier:
        waves.append(frontier)
        written += len(frontier)
        next_frontier: list = []
        for qid in frontier:
            for successor in successors[qid]:
                remaining_indegree[successor] -= 1
                if remaining_indegree[successor] == 0:
                    next_frontier.append(successor)
        frontier = sorted(next_frontier, key=lambda qid: _sort_key(corpus, qid))

    if written != len(corpus.blocks):
        remaining = set(corpus.blocks) - {qid for wave in waves for qid in wave}
        cycle = _extract_minimal_cycle(remaining, successors)
        raise Refused("ORDER_CYCLE", f"a cycle among blocks: {' -> '.join(cycle)}")

    return waves
