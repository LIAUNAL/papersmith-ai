"""paper_coupling_evidence: every disk read `verify` needs, isolated here
and nowhere else (`the-couplings-hold-or-they-do-not`, design.md, `skill-
local modules, an evidence seam, no _core/`).

Named `paper_coupling_evidence` rather than the proposal's own
`paper_evidence` because that name is already taken by
`no-claim-without-a-source-that-holds-it`'s claim<->source record module —
a real, landed, unrelated capability this change must not collide with
(measured on disk before naming this file).

This module reads bytes; it never checks them. Every check `paper_verify.py`
runs is a pure function of the `Evidence` object built here, so the AST
read-only lock (`tests/test_paper_writing.py`, `ReadOnlyTests`) can hold this
module to "reads only" and `paper_verify.py` to "touches disk never" as two
separate, independently provable claims.

`verify` reads its own declaration record from `paper/couplings.json` —
read-only, untracked like `main.tex` itself, and never the `declarations`
region `paper_declarations.py` owns (that region's payload shape is a
different capability's decision, not this one's — design.md, `one record,
one grammar, and this change writes none of it`). The `provenance` region
IS the same one `the-paper-carries-its-own-decisions` already writes at
`substitute --contract` time; this module only ever reads it, through
`paper_provenance.read_provenance`/`paper_provenance.drift` — never a second
implementation of the same digest comparison.

Public surface:

    Evidence                         -> the dataclass every check reads,
                                         including `producers_by_fact`
                                         (`a-fact-is-declared-or-it-is-
                                         produced`: `check_gap` alone reads
                                         it; `blocks_by_fact` is untouched)
    gather(paper_dir, sections_dir) -> Evidence   (raises
                                                     DECLARATION_RECORD_ABSENT)
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paper_block  # noqa: E402
import paper_contract  # noqa: E402
import paper_figure_audit  # noqa: E402 -- one-way: this module MAY import the auditor; the auditor MUST NOT import this one or `paper_verify` (`paper_verify.py` is AST-locked to `re` and could not anyway)
import paper_graph  # noqa: E402
import paper_provenance  # noqa: E402
import paper_vocabulary  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_core" / "implementation"))
from impl_refusals import Refused  # noqa: E402

#: The declaration record's own filename, sibling to `main.tex`/`refs.bib`
#: under `paper/` — untracked (`paper/*` is gitignored except `.gitkeep`),
#: read-only to this module, and written by nobody this change depends on
#: (design.md, `one record, one grammar, and this change writes none of
#: it`).
COUPLINGS_RECORD_NAME = "couplings.json"


@dataclass(frozen=True)
class Evidence:
    """Everything a check needs, already read. A check never touches
    `paper_dir`/`sections_dir` itself — those two fields exist on this
    object only so `paper_verify.run`'s report can name where evidence came
    from, never so a check can re-open a file `gather()` already read.

    `blocks_by_fact`: fact id -> `(block_ids, unmeasured_reason)`, for every
    fact in `paper_vocabulary.FACTS` — `block_ids` is empty and
    `unmeasured_reason` is set whenever the derivation could not produce a
    real block set (`SECTION_CONTRACTS_UNREADABLE` when the corpus itself
    could not be read at all, `NO_BLOCK_REQUIRES_FACT` when it could be read
    and simply names no block for that fact). Derived once here, through
    `paper_contract.parse` by way of `paper_graph.assemble_corpus` — never a
    record-declared fallback (design.md, `which blocks a check reads is
    derived, not hardcoded, and has exactly one source`).

    `block_bodies`: block id -> that block's body bytes, under the id its
    markers carry and, for a section-qualified marker, under its raw id too,
    sliced from `main_tex_bytes` via `paper_block.parse` — the one place
    this module calls the block grammar's own parser, so `paper_verify.py`
    never has to (design.md, `verify never parses a marker: it calls
    paper_block.parse and slices bodies from the same bytes`).

    `contract_drift`: block id -> `bool | None`, for every block the
    `provenance` region names — `True` stale, `False` current, `None` when
    the recorded contract file itself could not be re-read. Computed via
    `paper_provenance.drift`, which this module is the only caller of, so
    `paper_verify.py`'s check B never opens a contract file itself.

    `producers_by_fact`: fact id -> `(producer_block_ids, unmeasured_
    reason)`, the PRODUCER counterpart to `blocks_by_fact` above
    (`a-fact-is-declared-or-it-is-produced`, design.md Decision F) —
    `producer_block_ids` are raw (unqualified) ids naming every block whose
    `produces_facts` names that fact, same `SECTION_CONTRACTS_UNREADABLE`
    fallback shape as `blocks_by_fact`. `check_gap` alone reads this field;
    `blocks_by_fact` itself is untouched, so `check_chain`'s own
    `zip(block_ids, links)` alignment is never at risk.
    """

    paper_dir: Path
    sections_dir: Path
    main_tex_bytes: bytes
    refs_bib_bytes: bytes
    record: dict = field(default_factory=dict)
    provenance: dict | None = None
    contract_drift: dict = field(default_factory=dict)
    block_bodies: dict = field(default_factory=dict)
    blocks_by_fact: dict = field(default_factory=dict)
    #: The eighth check's whole input: `paper_figure_audit.audit_semantics`'s
    #: already-computed report, one entry per figure under `paper/Figures/`,
    #: or `None` when the paper declares no figure at all. A `dict`, never
    #: `Path`-typed — the read lock (`tests/test_paper_writing.py`,
    #: `ReadOnlyTests`) forbids `paper_verify.py` touching any `Path`-typed
    #: field, and this field exists so that module can read a verdict without
    #: parsing anything itself.
    figure_semantics: dict | None = None
    producers_by_fact: dict = field(default_factory=dict)


def _read_declaration_record(paper_dir: Path) -> dict:
    """Refuses `DECLARATION_RECORD_ABSENT` (work-state) when
    `paper/couplings.json` does not exist, cannot be parsed as JSON, or
    parses to something carrying no `blocks` entry at all — an empty
    record conveys nothing about any coupling, so it is exactly as absent
    as a missing file (`coupling-verification` spec, `Requirement:
    Declaration Record Presence Gates The Run`; M6).
    """
    path = paper_dir / COUPLINGS_RECORD_NAME
    if not path.is_file():
        raise Refused(
            "DECLARATION_RECORD_ABSENT",
            f"{path} does not exist; verify has nothing declared to read",
        )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise Refused(
            "DECLARATION_RECORD_ABSENT", f"{path}: unreadable as a declaration record: {exc}"
        )
    if not isinstance(raw, dict) or not raw.get("blocks"):
        raise Refused(
            "DECLARATION_RECORD_ABSENT", f"{path}: carries no declared blocks"
        )
    return raw


def _blocks_by_fact(sections_dir: Path) -> dict:
    """Every fact in `paper_vocabulary.FACTS` mapped to the raw block ids
    whose `requires_facts` names it, in corpus order. `SECTION_CONTRACTS_
    UNREADABLE` when the corpus cannot be assembled at all (an absent
    `sections_dir`, or any file under it refusing `paper_contract.parse` —
    headerless included, `MALFORMED_HEADER` among them); `NO_BLOCK_REQUIRES_
    FACT` when the corpus reads fine and simply names no block for a given
    fact (design.md, `An empty derived set is unmeasured ... never zero
    comparisons reported as agreement`).
    """
    try:
        corpus = paper_graph.assemble_corpus(sections_dir)
    except Refused:
        corpus = None
    if corpus is None or not corpus.blocks:
        return {fact: ((), "SECTION_CONTRACTS_UNREADABLE") for fact in paper_vocabulary.FACTS}

    by_fact: dict = {fact: [] for fact in paper_vocabulary.FACTS}
    for qualified_id in sorted(corpus.blocks):
        record = corpus.blocks[qualified_id]
        for fact in record.requires_facts:
            if fact in by_fact:
                by_fact[fact].append(record.block_id)
    return {
        fact: (tuple(block_ids), None) if block_ids else ((), "NO_BLOCK_REQUIRES_FACT")
        for fact, block_ids in by_fact.items()
    }


def _producers_by_fact(sections_dir: Path) -> dict:
    """Every fact in `paper_vocabulary.FACTS` mapped to the raw block ids
    whose `produces_facts` names it, in corpus order — the PRODUCER
    counterpart to `_blocks_by_fact` above (`a-fact-is-declared-or-it-is-
    produced`, `fact-production` spec). Deliberately its OWN
    `assemble_corpus` call rather than sharing state with `_blocks_by_fact`
    — this module's read-only contract is provable independently of that
    sibling function's own shape, and the two never need to agree on
    anything beyond which corpus they each re-derive from.

    Scans only BLOCK-level `produces_facts` (`corpus.blocks`), mirroring
    `_blocks_by_fact`'s own scope (`requires_facts` has no section-level
    counterpart at all) — the real corpus's two `gap` producers, `related-
    work.rw-closing` and `introduction.block-3`, are both block-level, and
    no live check needs a section-level producer id today.

    `SECTION_CONTRACTS_UNREADABLE` when the corpus cannot be assembled at
    all, the same fallback `_blocks_by_fact` uses. Unlike `_blocks_by_fact`,
    a fact named by zero producers is reported as `((), None)` rather than a
    distinct reason — `check_gap`'s own `len(block_ids) != 2` gate already
    reports an empty or wrong-count producer set as `BLOCK_NOT_DECLARED`,
    so a second reason string for the same "wrong count" condition would
    only duplicate that gate, never add a distinct one.
    """
    try:
        corpus = paper_graph.assemble_corpus(sections_dir)
    except Refused:
        corpus = None
    if corpus is None or not corpus.blocks:
        return {fact: ((), "SECTION_CONTRACTS_UNREADABLE") for fact in paper_vocabulary.FACTS}

    by_fact: dict = {fact: [] for fact in paper_vocabulary.FACTS}
    for qualified_id in sorted(corpus.blocks):
        record = corpus.blocks[qualified_id]
        for fact in record.produces_facts:
            if fact in by_fact:
                by_fact[fact].append(record.block_id)
    return {fact: (tuple(block_ids), None) for fact, block_ids in by_fact.items()}


def _compute_contract_drift(main_tex_bytes: bytes, provenance: dict | None) -> dict:
    if provenance is None:
        return {}
    result: dict = {}
    for entry in provenance["body"]["records"]:
        contract_path = Path(entry["contract"])
        try:
            result[entry["block"]] = paper_provenance.drift(
                main_tex_bytes, entry["block"], contract_path
            )
        except OSError:
            result[entry["block"]] = None
    return result


def manuscript_prose(paper_dir: Path, section_ids) -> str:
    """The manuscript bodies of every block belonging to `section_ids`.

    A block's id in `paper/main.tex` is section-qualified
    (`<section>.<block-id>`, `paper_graph`'s `qualified_id`), so a section's
    blocks are the ones whose marker id starts with `<section>.`. Only the
    bytes BETWEEN a block's begin and end markers are returned — the marker
    lines themselves carry a digest, never prose.

    **Why this exists:** a section contract (`sections/*.md`) is the plan for
    a section, not its prose. A paper-specific component such as "Circular
    Data Re-Uploading (CDRU)" is named in the manuscript block that realises
    the section (often as a `\\subsection` title) and never in the contract,
    so a figure audit that only reads the contract reports it as an
    unmatched node however faithfully the manuscript names it.

    **Absence is not a refusal:** a `main.tex` that is missing, unreadable
    or whose markers do not parse yields the empty string, so the caller
    compares against the contract text alone — exactly what it did before
    this read existed. The marker-grammar refusals belong to `gather()`
    (which reads `main.tex` for every other check) and to `block status`;
    this auxiliary read must not add a second place that raises them.
    """
    prefixes = tuple(f"{section_id}." for section_id in section_ids)
    if not prefixes:
        return ""
    try:
        data = (paper_dir / "main.tex").read_bytes()
        parsed = paper_block.parse(data)
    except (Refused, OSError):
        return ""
    chunks: list = []
    for block_id in parsed.order:
        if not block_id.startswith(prefixes):
            continue
        begin, end = parsed.pairs[block_id]
        chunks.append(data[begin["end"]:end["start"]].decode("utf-8", errors="replace"))
    return "\n".join(chunks)


def _figure_prose(paper_dir: Path, sections_dir: Path) -> str:
    """The prose of every section that declares at least one `figure:`
    obligation: its contract body plus its manuscript blocks.

    **Why this is coarse, and why that is stated rather than hidden:**
    binding a figure id to a section is not declared anywhere — the
    contract's `figure:` object carries no id, and `paper_contract` refuses
    unknown keys there (`MALFORMED_FIGURE_OBLIGATION`) — so the aggregate
    check compares a figure's declared components against the prose of the
    sections that carry figures at all. The standalone `figure audit` verb,
    which takes `--section` explicitly, is the precise path; this one is
    deliberately wider and says so instead of inventing a binding nobody
    declared.

    **Contract text plus manuscript text:** the contract body alone never
    names a paper-specific component (see `manuscript_prose`), so each
    figure-bearing section's blocks in `paper_dir/main.tex` join the union.
    The contract text stays in it, so nothing that matched before stops
    matching; an absent or unparseable `main.tex` leaves the contract text
    alone, the previous behaviour.
    """
    if not sections_dir.is_dir():
        return ""
    chunks: list = []
    section_ids: list = []
    for path in sorted(sections_dir.glob("*.md")):
        try:
            header, body = paper_contract.parse(path.read_bytes())
        except (Refused, OSError):
            continue
        if any(block.get("figure") is not None for block in header.blocks):
            chunks.append(body.decode("utf-8", errors="replace"))
            section_ids.append(header.section)
    manuscript = manuscript_prose(paper_dir, section_ids)
    if manuscript:
        chunks.append(manuscript)
    return "\n".join(chunks)


def _figure_semantics(paper_dir: Path, sections_dir: Path) -> dict | None:
    """Run `paper_figure_audit.audit_semantics` over every figure with a
    manifest, and aggregate. Two structurally distinct "no report" cases:

    - `None` — no `Figures/` directory, or no `*.diagram.json` inside it:
      the paper declares no figure at all, a fact the eighth check reports
      as `NO_FIGURE_DECLARED` rather than as a vacuous pass.
    - an unmeasured aggregate (`verdict: "unmeasured"`, empty `figures`) —
      manifests DO exist but every one was skipped by the guards below (its
      `<id>.tex` is missing, its JSON is malformed/undecodable/unreadable,
      or it is not a dict): a figure is declared and the audit could not
      reach a verdict, which the eighth check reports as
      `FIGURE_SEMANTICS_UNMEASURED`. The two facts stay distinct
      (`paper_verify.UNMEASURED_REASONS` documents why).
    """
    figures_dir = paper_dir / "Figures"
    if not figures_dir.is_dir():
        return None
    manifests = sorted(figures_dir.glob("*.diagram.json"))
    if not manifests:
        return None

    prose = _figure_prose(paper_dir, sections_dir)
    reports: dict = {}
    for manifest_path in manifests:
        figure_id = manifest_path.name[: -len(".diagram.json")]
        tex_path = figures_dir / f"{figure_id}.tex"
        if not tex_path.is_file():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            continue
        if not isinstance(manifest, dict):
            continue
        reports[figure_id] = paper_figure_audit.audit_semantics(
            tex=tex_path.read_text(encoding="utf-8", errors="replace"),
            manifest=manifest,
            section_text=prose,
            contract_figure=None,
        )
    if not reports:
        # Manifests existed but the guards skipped every one: this is
        # `FIGURE_SEMANTICS_UNMEASURED` (a figure exists, no verdict was
        # reached), never `NO_FIGURE_DECLARED` (no figure at all).
        return {"verdict": "unmeasured", "figures": reports}

    verdicts = {report["verdict"] for report in reports.values()}
    if "fail" in verdicts:
        verdict = "fail"
    elif "unmeasured" in verdicts:
        verdict = "unmeasured"
    else:
        verdict = "pass"
    return {"verdict": verdict, "figures": reports}


def gather(paper_dir: Path, sections_dir: Path) -> Evidence:
    """The one function every disk read `verify` performs funnels through.

    Order: resolve and read `main.tex` (reusing `paper_block.resolve_
    main_tex`'s own `PAPER_ABSENT`/`PAPER_NOT_A_DIRECTORY`, and letting
    `paper_block.parse` raise its own marker-grammar refusals unchanged —
    never a second implementation of either); read `refs.bib` if present,
    empty bytes otherwise (`refs.bib` is scaffolded empty and citation check
    A treats "no entries" as zero, not as an error); read the declaration
    record (`DECLARATION_RECORD_ABSENT`, M6); read the `provenance` region
    if present; derive the per-fact block sets from `sections_dir`.
    """
    tex_path = paper_block.resolve_main_tex(paper_dir)
    main_tex_bytes = tex_path.read_bytes()

    refs_bib_path = paper_dir / "refs.bib"
    refs_bib_bytes = refs_bib_path.read_bytes() if refs_bib_path.is_file() else b""

    record = _read_declaration_record(paper_dir)
    provenance = paper_provenance.read_provenance(main_tex_bytes)
    contract_drift = _compute_contract_drift(main_tex_bytes, provenance)

    parsed = paper_block.parse(main_tex_bytes)
    block_bodies = {
        block_id: main_tex_bytes[begin["end"]:end["start"]]
        for block_id, (begin, end) in parsed.pairs.items()
    }
    # A manuscript `paper_cli` writes names each block `<section>.<id>` in its
    # markers, while the contracts, `couplings.json` and every check speak the
    # raw id. Alias each qualified body under its raw id too, unless two
    # sections share that raw id (then only the qualified keys stay).
    raw_ids: dict = {}
    for block_id in block_bodies:
        if "." in block_id:
            raw_ids.setdefault(block_id.split(".", 1)[1], []).append(block_id)
    for raw, qualified in raw_ids.items():
        if len(qualified) == 1 and raw not in block_bodies:
            block_bodies[raw] = block_bodies[qualified[0]]

    blocks_by_fact = _blocks_by_fact(sections_dir)
    figure_semantics = _figure_semantics(paper_dir, sections_dir)
    producers_by_fact = _producers_by_fact(sections_dir)

    return Evidence(
        paper_dir=paper_dir,
        sections_dir=sections_dir,
        main_tex_bytes=main_tex_bytes,
        refs_bib_bytes=refs_bib_bytes,
        record=record,
        provenance=provenance,
        contract_drift=contract_drift,
        block_bodies=block_bodies,
        blocks_by_fact=blocks_by_fact,
        figure_semantics=figure_semantics,
        producers_by_fact=producers_by_fact,
    )
