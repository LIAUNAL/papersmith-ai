#!/usr/bin/env python3
"""paper_cli.py — front door for the `paper-writing` skill.

Standard library only, keyless, offline, fail-closed — the shape of
`implementation_cli.py` and `remote_cli.py`. One JSON object on stdout per
invocation. Exit 0 means the command ran; exit 2 means a guard refused
before touching disk.

Wires twenty-five verbs: `scaffold`, `open`, `status`, `substitute` (from
`only-the-block-changes`; `substitute` grew an optional `--contract <path>`
in Slice C1 of `the-paper-carries-its-own-decisions`, recording provenance
without changing what bytes get written); `contract`, `readiness`, `order`
(from `the-contract-is-data-not-code` — the section-contract reader);
`declare`, `observe`, `plan` (from `the-paper-carries-its-own-decisions`,
Slices B and C2 — `observe` validates an `insumos-observer` report against
the observable-fact schema before a human runs `declare` against it);
`bind` (from `the-requirement-names-the-section-that-feeds-it`, U3e ruling
— the verb that RECORDS a `source-section-binding`, in `paper/`, never
`sections/*.md`: the answer to `SECTION_BINDING_ABSENT` a person gives BY
USING THE SKILL, never by a hand edit or an agent reading conversation
prose; `--reopen` clears an already-recorded (block, fact) pair);
`resolve`, `full_text`, `bib build`, `validate` (from `no-claim-without-a-
source-that-holds-it`, WU1/WU2/WU3, and `the-pdf-arrives-or-the-operator-
is-told` for `full_text` — `resolve` is the one path that makes this CLI
not offline end to end, keyless and behind a role `papersmith.yaml` can
empty; `full_text` fills the sibling `full-text` role the same way,
fetching an already-resolved record's own PDF from its cached metadata's
measured `full_text_url` and placing it loose under `guidance/<section-
id>/` for `paper-ingestion` to find; `bib build` rebuilds `refs.bib` whole
from cached resolved metadata only; `validate` is the single gate deciding
verdict, placement and the bounded search-round budget before any block
reaches disk, now counting each claim's DISTINCT source papers against a
configurable minimum (`paper_validate.DEFAULT_MIN_SOURCES_PER_CLAIM`,
`the-pdf-arrives-or-the-operator-is-told`, item 2), never bare record
count); `write` (from `the-
writer-may-assert-only-what-it-was-given` — a judge, never an invoker: it
reconciles an already-shuttled redactor draft and contract-auditor account
against one block's real contract, evidence set and mode, and either
substitutes the block or reports why not, with exactly one bounded
re-draft); `render`, `place` (from `a-diagram-that-compiles-or-says-why` —
a diagram that compiles standalone or says why, the repair-budget ledger,
and the data-figure boundary); `verify` (from `the-couplings-hold-or-they-
do-not` — a read-only report over five cross-section couplings, citation
integrity and contract currency; resolves the corpus's own optional-block
ids and threads them into `paper_verify.run`, so an unopened `optional:
true` block excuses a coupling as `unmeasured` rather than failing it); and
`phases`, `skeleton`, `packet` (from `the-phases-are-derived-not-
remembered` — `phases` reports each Kahn wave's own readiness basis and
gates `write` against it, `PHASE_NOT_READY`; `skeleton` infers Related Work
/ dataset-placement decisions straight from disk and opens every
non-excluded block id in derived order, once, never re-asking,
`SKELETON_ANSWER_REQUIRED`/`SKELETON_ALREADY_DECIDED`; `packet` assembles
one block's own contract prose plus, per `style-reference` guidance folder,
a heading OUTLINE only — offsets, never inlined span text — ahead of
`write`'s draft stage); and `reuse`, `exhaustion` (from
`a-leftover-paper-is-offered-before-it-is-lost` — two read-only reports
over the ingested-papers lifecycle: `reuse` names, for one block's own
still-open claims, which already-ingested `evidence`-classed papers carry
no verdict yet; `exhaustion` is the corpus-wide report of which papers now
carry a `does-not-hold` against every open claim in the whole corpus —
`paper_lifecycle.py` does every real read; this file only resolves paths
and threads `--min-sources` through. Neither verb ever deletes anything —
the operator deletes by hand, per the operator's own ruling). Left
extensible on purpose; nothing here assumes it is the last verb this file
will ever grow.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paper_block  # noqa: E402
import paper_scaffold  # noqa: E402
import paper_vocabulary  # noqa: E402
import paper_contract  # noqa: E402
import paper_graph  # noqa: E402
import paper_readiness  # noqa: E402
import paper_region  # noqa: E402,F401 -- registered for the roster derivation
import paper_guidance  # noqa: E402
import paper_declarations  # noqa: E402
import paper_marker  # noqa: E402,F401 -- the-skill-writes-the-declaration-it-demands, S2: the shared seal `paper_declarations.declare_revisions`/`read_revisions_marker` both call; raises no `Refused` of its own (design.md Decision B), imported here so `ModuleCompletenessTests` sees it and the roster derivation's whole-module scan covers it (contributing nothing, since it raises nothing)
import paper_provenance  # noqa: E402,F401 -- for the roster derivation; substitute's own --contract wiring calls paper_block, which calls this module in turn
import paper_objective  # noqa: E402,F401 -- this skill's own declared north (tests/test_agents.py); raises no Refused of its own
import paper_evidence  # noqa: E402 -- no-claim-without-a-source-that-holds-it, WU1: the claim<->source record
import paper_resolve  # noqa: E402 -- no-claim-without-a-source-that-holds-it, WU1: the urllib resolution client
import paper_bib  # noqa: E402 -- no-claim-without-a-source-that-holds-it, WU2: refs.bib from cached metadata
import paper_validate  # noqa: E402 -- no-claim-without-a-source-that-holds-it, WU3: verdicts, placement, the bounded loop
import paper_bindings  # noqa: E402 -- the-writer-may-assert-only-what-it-was-given, WU1: binding map reconciliation/resolution/typing/mode
import paper_audit  # noqa: E402 -- the-writer-may-assert-only-what-it-was-given, WU1: verbatim Disqualifiers reconciliation
import paper_write  # noqa: E402 -- the-writer-may-assert-only-what-it-was-given, WU1: the write pipeline and its attempt ledger
import paper_source_span  # noqa: E402 -- the-tripwire-reaches-the-section-that-feeds-it, WU1: a block's own bound-section bytes, resolved from the write gate's own corpus
import paper_grounding  # noqa: E402 -- the-block-asserts-only-what-its-section-carries: per-sentence support reconciliation against the bound section's own bytes; for the roster derivation
import paper_style  # noqa: E402,F401 -- the-writer-may-assert-only-what-it-was-given, WU2: style-reference resolution and R; for the roster derivation
import paper_leak  # noqa: E402,F401 -- the-writer-may-assert-only-what-it-was-given, WU2: register/overlap proof and the eight-token tripwire; for the roster derivation
import paper_latex  # noqa: E402,F401 -- a-diagram-that-compiles-or-says-why: the sole subprocess seam (latexmk), invocation, log parse, verdict; for the roster derivation
import paper_figure  # noqa: E402 -- a-diagram-that-compiles-or-says-why: source/manifest layout, stop A, the compile pipeline, the repair-budget ledger; `render`/`place` verbs
import paper_obligation  # noqa: E402,F401 -- a-diagram-that-compiles-or-says-why: components/separation/caption/mandatory checks over the contract's `figure:` declaration; imported ahead of any verb calling it directly (the same shape `paper_region.py`/`paper_guidance.py` already established) so its refusals are reachable the moment the import lands
import paper_tikz  # noqa: E402,F401 -- a-diagram-that-compiles-or-says-why: the pure TikZ optimization transforms (`figure optimize`); imported ahead of its verb wiring, the same shape `paper_region.py`/`paper_guidance.py`/`paper_obligation.py` already established, and required the moment the module exists (`ModuleCompletenessTests`)
import paper_figure_audit  # noqa: E402,F401 -- a-diagram-that-compiles-or-says-why: the figure-prose semantic auditor (`figure audit`, and `verify`'s eighth check through `paper_coupling_evidence.gather`); imported ahead of its verb wiring for the same `ModuleCompletenessTests` reason
import paper_coupling_evidence  # noqa: E402 -- the-couplings-hold-or-they-do-not: every disk read `verify` needs (named to avoid colliding with `paper_evidence.py`, WU1's own claim<->source module)
import paper_verify  # noqa: E402 -- the-couplings-hold-or-they-do-not: the seven pure coupling checks and the report they assemble; raises no `Refused` of its own (every refusal a `verify` run can report is `DECLARATION_RECORD_ABSENT`, from `paper_coupling_evidence.py`)
import paper_couplings  # noqa: E402 -- the-skill-stops-trusting-memory, item 4: the producer `paper/couplings.json` never had; `couplings` verb
import paper_full_text  # noqa: E402 -- the-pdf-arrives-or-the-operator-is-told: fills the full-text role; `full_text` verb
import paper_lifecycle  # noqa: E402 -- a-leftover-paper-is-offered-before-it-is-lost: the reuse and exhaustion reports over the ingested-papers lifecycle; `reuse`/`exhaustion` verbs; raises no `Refused` of its own
import paper_separation  # noqa: E402 -- the-whole-cut-is-argued-before-any-section-is-claimed, U1: the pure claimable-section/score-cut core; wired to the `separate` verb in U2 (`compute_separation`/`cmd_separate` below); raises no `Refused` of its own

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_core" / "implementation"))
from impl_refusals import Refused  # noqa: E402

#: This script's own absolute path, resolved once — printed by no command
#: yet, kept for the same reason `implementation_cli.py`'s `CLI_PATH` is:
#: whatever prints a runnable command later reaches for this rather than a
#: bare relative name.
CLI_PATH = Path(__file__).resolve()

#: The floor this skill's own scripts need, MEASURED rather than picked:
#: every one of the 31 shipped `paper_*.py` modules (and the shared
#: `impl_refusals.py` under `_core/implementation/`) opens with `from
#: __future__ import annotations` (PEP 563, 3.7+) -- the highest-versioned
#: feature any of them uses. Scanned for and found nowhere in this skill's
#: own scripts: the walrus operator, `match`/`case`, a PEP 604 `X | Y`
#: outside an annotation, the dict-union `|` operator, `str.removeprefix`/
#: `removesuffix`, `pathlib.Path.is_relative_to`. A future change that adds
#: any of those moves this number; nothing here should be read as a
#: forecast of what this skill will always need. This is the same
#: `SKILL_PYTHON_FLOOR` shape `implementation_engine.py` already carries
#: for its own layout templates, applied here to this skill's own
#: interpreter instead of a target's.
SKILL_PYTHON_FLOOR: tuple[int, int] = (3, 7)


def _require_supported_python() -> None:
    """Refuses by name instead of a bare traceback naming a module the
    caller never asked about -- exactly the gap this skill shipped with no
    declared floor at all until now. A pre-3.7 interpreter cannot even
    PARSE this file to reach this call (`from __future__ import
    annotations` is itself the 3.7+ syntax feature that makes every other
    module's annotations safe to write), so this comparison can only ever
    be exercised by an interpreter capable enough to load the file but
    told, at runtime, that it is older (`PythonFloorGuardTests`,
    `tests/test_paper_writing.py` -- there is no other way to prove the
    comparison itself without an old interpreter actually installed). It
    still earns its place: it is the one enforcement point a later change
    that raises the real floor with a runtime-only stdlib addition (an
    `AttributeError`, never a `SyntaxError`) reaches for, instead of
    leaving the gap this item closed to reopen silently.
    """
    current = sys.version_info[:2]
    if current < SKILL_PYTHON_FLOOR:
        raise Refused(
            "PYTHON_VERSION_UNSUPPORTED",
            f"this skill needs Python {SKILL_PYTHON_FLOOR[0]}.{SKILL_PYTHON_FLOOR[1]}+; "
            f"the running interpreter is {current[0]}.{current[1]}",
        )


#: The two classes every refusal below is sorted into, matching
#: `implementation_cli.py`'s own vocabulary: can the caller clear this by
#: changing the invocation alone (`INVOCATION_DEFECT`), or does clearing it
#: require acting on the repository (`WORK_STATE`)?
INVOCATION_DEFECT = "invocation-defect"
WORK_STATE = "work-state"

#: Every refusal code reachable from a command below, classified. Derived
#: against and held to `reachable_paper_refusal_codes()`
#: (`tests/test_paper_writing.py`) in both directions: nothing reachable is
#: unclassified, and nothing classified here is unreachable. Never a code
#: this file merely documents — every entry is a code some command really
#: raises, directly or through a module this file imports
#: (`paper_block.py`, `paper_scaffold.py`, `paper_vocabulary.py`,
#: `paper_contract.py`, `paper_graph.py`, `paper_region.py`,
#: `paper_guidance.py`; `paper_readiness.py` raises none of its own) --
#: or through `main()`'s own front door, ahead of every command
#: (`_require_supported_python`, above), which is why `main` sits beside
#: every `cmd_*` verb as a root `reachable_paper_refusal_codes()` walks.
#: `paper_region.py` and `paper_guidance.py` are imported ahead of their own
#: verb wiring (`the-paper-carries-its-own-decisions`, Slice A) -- their
#: refusals are reachable the moment the import lands, so they are
#: classified here immediately rather than left dangling until `declare`/
#: `plan` exist.
REFUSAL_CLASSIFICATION: dict[str, str] = {
    # --- main's own front door, ahead of every verb ---------------------
    "PYTHON_VERSION_UNSUPPORTED": WORK_STATE,
    # --- scaffold ------------------------------------------------------
    "PAPER_OUTSIDE_REPOSITORY": INVOCATION_DEFECT,
    "PAPER_NOT_A_DIRECTORY": WORK_STATE,
    "SCAFFOLD_ENTRY_WRONG_TYPE": WORK_STATE,
    # --- shared block resolution (open, status, substitute) ------------
    "PAPER_ABSENT": WORK_STATE,
    "TEX_UNDECODABLE": WORK_STATE,
    "BLOCK_ID_MALFORMED": INVOCATION_DEFECT,
    # --- marker grammar --------------------------------------------------
    "MARKER_MALFORMED": WORK_STATE,
    "BLOCK_DUPLICATED": WORK_STATE,
    "BLOCK_UNPAIRED": WORK_STATE,
    "BLOCK_NESTED": WORK_STATE,
    # --- open ------------------------------------------------------------
    "ANCHOR_ABSENT": INVOCATION_DEFECT,
    "OPEN_POSITION_REQUIRED": INVOCATION_DEFECT,
    "OPEN_POSITION_CONFLICT": INVOCATION_DEFECT,
    # --- substitute --------------------------------------------------------
    "BLOCK_ABSENT": WORK_STATE,
    "BLOCK_HAND_EDITED": WORK_STATE,
    "CONTENT_CARRIES_MARKER": INVOCATION_DEFECT,
    "NOTHING_TO_ADOPT": INVOCATION_DEFECT,
    "SUBSTITUTE_MODE_REQUIRED": INVOCATION_DEFECT,
    "ADOPT_BODY_CONFLICT": INVOCATION_DEFECT,
    "SUBSTITUTION_NOT_LOCAL": WORK_STATE,
    "TEX_MOVED": WORK_STATE,
    # --- closed vocabularies (paper_vocabulary.py) ----------------------
    "UNKNOWN_FACT": WORK_STATE,
    "UNKNOWN_DECLARATION": WORK_STATE,
    "UNKNOWN_CITATIONS_REGIME": WORK_STATE,
    # --- header schema (paper_contract.py; `install_header` -- and its own
    # HEADER_PRESENT/BODY_MUTATED -- deleted in the zero-production-caller
    # corrective: its one-shot migration already ran and nothing promises
    # an ongoing "create a new section contract" workflow) ----------------
    "MALFORMED_HEADER": WORK_STATE,
    "SECTIONS_OUTSIDE_REPOSITORY": INVOCATION_DEFECT,
    #: K4 corrective: `resolve_sections_dir` now also refuses when the
    #: resolved path does not exist as a directory, reusing the exact code
    #: `UNMEASURED_REASONS` (`paper_verify.py`) and `_blocks_by_fact`
    #: (`paper_coupling_evidence.py`) already use to name "the corpus
    #: itself could not be read" — never a second code for the same
    #: condition.
    "SECTION_CONTRACTS_UNREADABLE": WORK_STATE,
    #: The caller named a section or a block the corpus does not declare.
    #: Both replace a CRASH rather than adding a new prohibition: `packet`,
    #: `write` and `place` each composed `sections_dir / f"{section}.md"`
    #: (a `FileNotFoundError` for every shipped contract, since all ten are
    #: `NN-<section>.md`) and each then did a bare `next(...)` over the
    #: header's blocks (a `StopIteration` for an unknown id). Neither
    #: exception carries a literal code, so the roster could not see the
    #: gap: it was not an unclassified refusal, it was no refusal at all.
    "SECTION_UNKNOWN": INVOCATION_DEFECT,
    "BLOCK_UNDECLARED": INVOCATION_DEFECT,
    # --- corpus assembly and order (paper_graph.py) -----------------------
    "ID_COLLISION": WORK_STATE,
    "ORDER_CYCLE": WORK_STATE,
    # --- the-phases-are-derived-not-remembered, unit 1: the two-heading
    # partition every contract's prose must carry (paper_graph.py,
    # `_verify_input_partition`, called from `assemble_corpus`) ------------
    "INPUT_PARTITION_ABSENT": WORK_STATE,
    # --- the-phases-are-derived-not-remembered, unit 4: every `### Internal
    # chain` row transcribes to a real, backed `after` edge
    # (paper_graph.py, `_verify_internal_chain`) ---------------------------
    "CHAIN_ROW_UNRESOLVED": WORK_STATE,
    "CHAIN_ROW_UNBACKED": WORK_STATE,
    # --- the-phases-are-derived-not-remembered, unit 4 (tasks 4.8b-4.8i):
    # the PROSE -> HEADER direction no other check covers -- a numbered
    # heading (parent or `###` child) naming a sub-unit the front matter
    # never declared, or naming several without an explicit grouping
    # (paper_graph.py, `_verify_block_subunits`) ---------------------------
    "BLOCK_SUBUNIT_UNDECLARED": WORK_STATE,
    "UNIT_HEADING_AMBIGUOUS": WORK_STATE,
    # --- the-phases-are-derived-not-remembered, unit 6: `readiness` gains a
    # basis (design.md D3) and `phases` owns "what can I write now" (this
    # file, `cmd_readiness`/`cmd_phases`) -----------------------------------
    "READINESS_BASIS_REQUIRED": INVOCATION_DEFECT,
    "PHASE_NOT_READY": WORK_STATE,
    # --- the-phases-are-derived-not-remembered, unit 7: `skeleton`'s two
    # blocking questions, asked exactly once, and the disk-inferred
    # dataset-placement conflict (design.md D4; this file's `cmd_skeleton`,
    # `paper_declarations.infer_dataset_placement`) -----------------------
    "SKELETON_ANSWER_REQUIRED": INVOCATION_DEFECT,
    "SKELETON_ALREADY_DECIDED": WORK_STATE,
    "DATASET_PLACEMENT_CONFLICT": WORK_STATE,
    # --- the-skill-stops-trusting-memory, item 1: dataset placement is
    # derived from the corpus's own `requires_facts`/`optional` shape,
    # never a literal id pair (paper_declarations.
    # dataset_placement_candidates) -------------------------------------
    "DATASET_PLACEMENT_CANDIDATE_ABSENT": WORK_STATE,
    "DATASET_PLACEMENT_CANDIDATE_AMBIGUOUS": WORK_STATE,
    # --- region grammar (paper_region.py) -- twins of Phase 1's marker
    # codes, reachable ahead of their own verb wiring because paper_cli.py
    # imports paper_region.py at module level (Slice A, `the-paper-carries-
    # its-own-decisions`) -----------------------------------------------
    "REGION_MALFORMED": WORK_STATE,
    "REGION_DUPLICATED": WORK_STATE,
    "REGION_UNPAIRED": WORK_STATE,
    # --- guidance registry (paper_guidance.py) -- same reason -----------
    "GUIDANCE_OUTSIDE_REPOSITORY": INVOCATION_DEFECT,
    "UNKNOWN_GUIDANCE_CLASS": WORK_STATE,
    "MALFORMED_GUIDANCE_MARKER": WORK_STATE,
    # --- the-skill-stops-trusting-memory, item 2/3: the guidance registry's
    # own classification gates `validate --source-md` for the first time
    # (paper_cli._guard_source_md_classification) ---------------------------
    "SOURCE_STYLE_REFERENCE": WORK_STATE,
    "SOURCE_NOT_EVIDENCE": WORK_STATE,
    # --- the-phases-are-derived-not-remembered, unit 8: `packet`'s own
    # outline assembly over ingested guidance markdown (paper_guidance.
    # read_markdown_outline) -- reachable the instant that raise site
    # exists, `paper_guidance.py` already being an ahead-of-its-own-verb
    # import (design.md D5) --------------------------------------------
    "GUIDANCE_MARKDOWN_UNREADABLE": WORK_STATE,
    # --- declare (paper_declarations.py; UNKNOWN_FACT/UNKNOWN_DECLARATION
    # already classified above -- reused verbatim, never a second code for
    # the same condition, design.md's own decision) ---------------------
    "DECLARATION_FIXED": WORK_STATE,
    "DECLARATIONS_HAND_EDITED": WORK_STATE,
    # --- declare's own mode selection (this file; the same shape
    # SUBSTITUTE_MODE_REQUIRED/ADOPT_BODY_CONFLICT and
    # OPEN_POSITION_REQUIRED/OPEN_POSITION_CONFLICT already establish for
    # `substitute`/`open` -- not named in design.md's refusal table, which
    # only enumerates the region/vocabulary-level codes, so this is a
    # deliberate small extension of an existing convention) --------------
    "DECLARE_MODE_REQUIRED": INVOCATION_DEFECT,
    "DECLARE_MODE_CONFLICT": INVOCATION_DEFECT,
    "DECLARE_VALUE_REQUIRED": INVOCATION_DEFECT,
    "DECLINE_REASON_REQUIRED": INVOCATION_DEFECT,
    "CONDITION_REQUIRED": INVOCATION_DEFECT,
    "CONDITION_MALFORMED": WORK_STATE,
    "UNKNOWN_CONDITION_TYPE": WORK_STATE,
    # --- substitute --contract (paper_block.py's own new step; provenance
    # write itself is paper_provenance.py) -------------------------------
    "CONTRACT_UNREADABLE": WORK_STATE,
    "PROVENANCE_HAND_EDITED": WORK_STATE,
    # --- observation report validation (paper_declarations.py, wired to a
    # real caller via cmd_observe; formerly reachable only through the
    # whole-module scan, with no cmd_* root calling it -- closed by
    # wiring `observe`, the shuttle verb for `insumos-observer`'s report) -
    "NOT_AN_OBSERVABLE_FACT": INVOCATION_DEFECT,
    "EVIDENCE_CONFLATED": INVOCATION_DEFECT,
    # --- observe's own file/JSON read (this file; same shape
    # CONTRACT_UNREADABLE already establishes for a shuttled file) --------
    "OBSERVATION_REPORT_UNREADABLE": WORK_STATE,
    # --- the-skill-stops-trusting-memory, item 5: observe reconciles the
    # agent's own report against a real disk measurement this process takes
    # itself (paper_declarations.source_available/reconcile_observation_
    # report), gitignore-blind by construction -- never the agent's word
    # alone -------------------------------------------------------------
    "OBSERVATION_DISK_CONFLICT": WORK_STATE,
    # --- verdict vocabulary (paper_vocabulary.py; no-claim-without-a-
    # source-that-holds-it Phase 1) --------------------------------------
    "UNKNOWN_VERDICT": WORK_STATE,
    # --- the claim<->source record and its span (paper_evidence.py; WU1) -
    "SPAN_NOT_IN_SOURCE": WORK_STATE,
    "VERDICT_SPAN_REQUIRED": WORK_STATE,
    # --- the urllib resolution client (paper_resolve.py; WU1) -----------
    "PAPERSMITH_CONFIG_UNREADABLE": WORK_STATE,
    "UNKNOWN_ROLE": INVOCATION_DEFECT,
    "DISCOVERY_UNAVAILABLE": WORK_STATE,
    "RESOLVER_ROLE_EMPTY": WORK_STATE,
    "RESOLVER_UNREACHABLE": WORK_STATE,
    "IDENTIFIER_UNRESOLVED": WORK_STATE,
    # --- the-pdf-arrives-or-the-operator-is-told: fills the full-text role
    # (paper_full_text.py) -- `RESOLVER_ROLE_EMPTY`/`RESOLVER_UNREACHABLE`/
    # `IDENTIFIER_UNRESOLVED` above are reused verbatim, never a second code
    # for the same condition ---------------------------------------------
    "METADATA_NOT_CACHED": WORK_STATE,
    "FULL_TEXT_URL_ABSENT": WORK_STATE,
    "FULL_TEXT_NOT_A_PDF": WORK_STATE,
    "CITE_KEY_MALFORMED": INVOCATION_DEFECT,
    "FULL_TEXT_FILE_PRESENT": WORK_STATE,
    # --- the bibliography that cannot be typed (paper_bib.py; WU2) ------
    "ENTRY_UNSOURCED": WORK_STATE,
    "CITE_WITHOUT_ENTRY": WORK_STATE,
    "ENTRY_WITHOUT_CITE": WORK_STATE,
    # --- no-citation-before-its-paper-is-ingested, item 2: resolved is not
    # ingested (paper_bib._require_ingested) -------------------------------
    "ENTRY_NOT_INGESTED": WORK_STATE,
    # --- no-citation-before-its-paper-is-ingested, item 3: `write`'s own
    # citation-readiness gate (this file, `_guard_section_citations_ready`) -
    "CITATION_FOLDER_ABSENT": WORK_STATE,
    "CITATION_NOT_INGESTED": WORK_STATE,
    "CITATION_FOLDER_UNCLASSIFIED": WORK_STATE,
    # --- the validator and the bounded loop (paper_validate.py; WU3) -----
    "EVIDENCE_EXHAUSTED": WORK_STATE,
    "CITATION_MULTI_CLAIM_SENTENCE": WORK_STATE,
    "CITATION_NOUN_PHRASE": WORK_STATE,
    "CITATION_NOT_AT_SENTENCE_END": WORK_STATE,
    "CITATION_DETACHED_FROM_OBJECT": WORK_STATE,
    "CITATION_UNDER_NONE_REGIME": WORK_STATE,
    "CONTRACT_HEADER_ABSENT": WORK_STATE,
    # --- validate's own mode selection (this file; the same shape as
    # SUBSTITUTE_MODE_REQUIRED/DECLARE_MODE_REQUIRED) --------------------
    "VALIDATE_VERDICT_REQUIRED": INVOCATION_DEFECT,
    # --- mode widening (paper_vocabulary.py/paper_contract.py; the-writer-
    # may-assert-only-what-it-was-given, section-contract delta) ----------
    "UNKNOWN_MODE": WORK_STATE,
    # --- the binding map: reconciliation, resolution, structural typing,
    # mode admissibility (paper_bindings.py; WU1) -------------------------
    "UNBOUND_SENTENCE": WORK_STATE,
    "BINDING_ORPHANED": WORK_STATE,
    "EVIDENCE_ID_UNKNOWN": WORK_STATE,
    "FACT_NOT_LICENSED": WORK_STATE,
    "STRUCTURAL_CARRIES_CLAIM": WORK_STATE,
    "MODE_VIOLATION": WORK_STATE,
    # --- the contract audit: verbatim Disqualifiers, verdict reconciliation
    # (paper_audit.py; WU1) ------------------------------------------------
    "DISQUALIFIERS_ABSENT": WORK_STATE,
    "VERDICT_MISSING": WORK_STATE,
    "VERDICT_BULLET_UNKNOWN": WORK_STATE,
    # --- the write pipeline: readiness/gate and exhaustion (paper_write.py;
    # WU1) ------------------------------------------------------------------
    "MODE_ABSENT": WORK_STATE,
    "EVIDENCE_SET_REQUIRED": WORK_STATE,
    "AUDIT_EXHAUSTED": WORK_STATE,
    "DRAFT_UNREADABLE": INVOCATION_DEFECT,
    "AUDIT_UNREADABLE": INVOCATION_DEFECT,
    # --- the eight-token tripwire (paper_leak.py; WU2) ---------------------
    "STYLE_OVERLAP": WORK_STATE,
    # --- a-diagram-that-compiles-or-says-why: `render`/`place`, the sole
    # subprocess seam (paper_latex.py), source/manifest layout and the
    # repair ledger (paper_figure.py), and the obligation checks
    # (paper_obligation.py, imported ahead of any verb calling it directly
    # -- reachable the moment the import lands, the same shape
    # paper_region.py/paper_guidance.py already established). Twelve codes
    # from `authored-diagram`/`diagram-obligation`, plus two this skill's
    # own design introduces for behaviour the spec described without
    # naming a code (`LATEX_LOG_ABSENT`, `LATEX_OUTCOME_UNEXPLAINED`) -----
    "DIAGRAM_SOURCE_ABSENT": WORK_STATE,
    "LATEX_TOOLCHAIN_ABSENT": WORK_STATE,
    "LATEX_PACKAGE_ABSENT": WORK_STATE,
    "REPAIR_BUDGET_SPENT": WORK_STATE,
    "DIAGRAM_PLOTS_DATA": WORK_STATE,
    "MALFORMED_FIGURE_OBLIGATION": WORK_STATE,
    "COMPONENT_MISMATCH": WORK_STATE,
    # `components_from`'s Components Check is derived, never operator-
    # supplied (corrective amendment, `_resolve_expected_components`) -----
    "COMPONENTS_FACT_UNRESOLVED": WORK_STATE,
    "COMPONENTS_FACT_NOT_A_LIST": WORK_STATE,
    "MANIFEST_SOURCE_MISMATCH": WORK_STATE,
    "EXCLUDED_COMPONENT": WORK_STATE,
    "SHARED_COMPONENT": WORK_STATE,
    "CAPTION_INCOMPLETE": WORK_STATE,
    "MANDATORY_DIAGRAM_ABSENT": WORK_STATE,
    "LATEX_LOG_ABSENT": WORK_STATE,
    "LATEX_OUTCOME_UNEXPLAINED": WORK_STATE,
    # --- the-couplings-hold-or-they-do-not: verify's own declaration
    # record (`paper_coupling_evidence.py`; imported ahead of `verify`'s
    # own wiring, same shape as `paper_region.py`/`paper_obligation.py`
    # above). Every other tier of inability `verify` reports (an absent
    # provenance region, an undeclared block, an unreadable section
    # corpus) is an `unmeasured_reason` string in the report payload, never
    # a `Refused` -- only the whole-record-absent tier refuses the run -----
    "DECLARATION_RECORD_ABSENT": WORK_STATE,
    # --- the-skill-stops-trusting-memory, item 4: `couplings` is the
    # producer `paper/couplings.json` never had (paper_couplings.py) -------
    "COUPLINGS_INPUT_UNREADABLE": INVOCATION_DEFECT,
    "COUPLINGS_RECORD_MALFORMED": WORK_STATE,
    # --- a-fact-is-declared-or-it-is-produced, unit 1: `produces_facts`
    # joins the header grammar (`paper_contract.py`) and three assemble-
    # time checks land in `paper_graph.py` -- self-reference, route
    # exclusivity against the declarable route
    # (`paper_declarations.OBSERVABLE_FACTS ∪ STRUCTURAL_FACTS`), and
    # duplicate-producer (corroborated pairs an existing
    # coupling-verification check names, e.g. `gap` / Coupling 3, are
    # legal; every other duplicate still refuses). Unit 2 adds
    # `FACT_PRODUCER_ABSENT` (consumption-relative totality: a fact some
    # block requires resolves via `FACT_SOURCE_ROOT` or a producer, else
    # refuses) and `PRODUCER_CHAIN_ABSENT` (every one of a fact's
    # producer(s) must reach the consumer in the `after`-edge graph). Unit
    # 3 adds `PRODUCED_FACT_UNDECLARABLE`: `declare --fact`/`--decline`
    # targeting a fact whose producer is a block refuses, enforced in
    # `paper_declarations.set_fact`/`decline_fact` themselves --------------
    "FACT_SELF_REQUIRED": WORK_STATE,
    "FACT_ROUTE_AMBIGUOUS": WORK_STATE,
    "FACT_PRODUCER_DUPLICATE": WORK_STATE,
    "FACT_PRODUCER_ABSENT": WORK_STATE,
    "PRODUCER_CHAIN_ABSENT": WORK_STATE,
    "PRODUCED_FACT_UNDECLARABLE": WORK_STATE,
    # --- the-requirement-names-the-section-that-feeds-it, U1+U2: the
    # `document: {lineage, section}` half of a `requires_facts` entry
    # (`paper_contract.py`'s own grammar widening adds no new code --
    # `MALFORMED_HEADER` is reused verbatim) and its resolution against
    # real disk, wired into `assemble_corpus` (`paper_graph.py`'s new
    # `_verify_source_section_bindings`) and the marker reader it calls
    # (`paper_declarations.read_revisions_marker`/`resolve_lineage`).
    "MALFORMED_SOURCE_MARKER": WORK_STATE,
    "SOURCE_REVISIONS_UNDECLARED": WORK_STATE,
    "SOURCE_LINEAGE_UNRESOLVED": WORK_STATE,
    "SECTION_NOT_IN_SOURCE": WORK_STATE,
    "SECTION_TITLE_AMBIGUOUS": WORK_STATE,
    # --- the-requirement-names-the-section-that-feeds-it, U3: the obligation
    # itself -- a bindable fact whose own source root is MEASURED but carries
    # no `document` half. Reaches `write` through the same corpus assembly
    # every other code above reaches it through (`_resolve_write_gate` calls
    # `paper_graph.assemble_corpus` unconditionally); never reachable only
    # from the read-only `phases` verb -----------------------------------
    "SECTION_BINDING_ABSENT": WORK_STATE,
    # --- the-requirement-names-the-section-that-feeds-it, U2c: the owner's
    # ruling that `dataset` is sourced from the ingested EVIDENCE document
    # under `guidance/`, never from `proposals/`'s mathematics lineage. A
    # third `SourceRootKind`, `INGESTED` (`paper_declarations.py`), resolves
    # its own root by DERIVING which `guidance/` folder is classed
    # `'evidence'` (`paper_guidance.read_registry`, reused). More than one
    # such folder is a NEW ambiguity `SOURCE_LINEAGE_UNRESOLVED` does not
    # cover -- that code names a lineage's own candidates under an already-
    # identified root, never which root to use in the first place -----------
    "EVIDENCE_ROOT_AMBIGUOUS": WORK_STATE,
    # --- the-skill-writes-the-declaration-it-demands, S2: `mark revisions`
    # (`paper_declarations.declare_revisions`) -- the verb that WRITES a
    # source root's own revisions marker, validated against disk at the
    # moment of writing, and the seal-mismatch code its own reader
    # (`read_revisions_marker`) now raises (design.md Decisions A/C/F) -----
    "SOURCE_ROOT_UNDECLARABLE": WORK_STATE,
    "SOURCE_DECLARATION_UNMATCHED": WORK_STATE,
    "SOURCE_DECLARATION_HAND_EDITED": WORK_STATE,
    # --- the-skill-writes-the-declaration-it-demands, S3: `mark class`
    # (`paper_guidance.declare_class`) -- the verb that WRITES a guidance/
    # folder's own class marker, validated against disk at the moment of
    # writing, and the seal-mismatch code its own reader (`_classify`) now
    # raises (design.md Decisions A/C/F, guidance half) -----------------
    "GUIDANCE_FOLDER_ABSENT": WORK_STATE,
    "GUIDANCE_DECLARATION_HAND_EDITED": WORK_STATE,
    # --- the-requirement-names-the-section-that-feeds-it, U3e ruling: the
    # verb that RECORDS a binding (`bind`, `paper_declarations.bind_
    # section`/`reopen_binding`) -- the answer to `SECTION_BINDING_ABSENT`
    # a person gives BY USING THE SKILL, never by hand-editing
    # `sections/*.md` or by an agent reading conversation prose -- and the
    # conflict the corpus's own merge of a header-declared binding against
    # a RECORDED one can find (`paper_graph._reconcile_source_bindings`) --
    "BINDING_SECTIONS_REQUIRED": INVOCATION_DEFECT,
    "BINDING_LINEAGE_REQUIRED": INVOCATION_DEFECT,
    "BINDING_FACT_NOT_BINDABLE": WORK_STATE,
    "SOURCE_BINDING_CONFLICT": WORK_STATE,
    # --- the-whole-cut-is-argued-before-any-section-is-claimed, U2:
    # `separate`, the whole-cut reviewer shaped on `observe` -- reads an
    # agent-authored proposal (`_read_separation_proposal`'s own shape stage,
    # this file), resolves every title through the SAME existence/ambiguity
    # path `bind` already uses (`paper_graph.resolve_section_index`, extracted
    # from `_verify_source_section_bindings`), derives the claimable section
    # set from the document's own structure (`paper_separation.
    # claimable_sections`), and scores the cut's orphan/overlap/gap defects
    # (`paper_separation.score_cut`) -- never records a binding under any
    # outcome. `UNKNOWN_FACT`/`BINDING_FACT_NOT_BINDABLE`/`SECTION_NOT_IN_
    # SOURCE`/`SECTION_TITLE_AMBIGUOUS` above are reused verbatim, never a
    # second code for the same condition -----------------------------------
    "SEPARATION_REPORT_UNREADABLE": WORK_STATE,
    "SEPARATION_SECTION_UNCLAIMABLE": WORK_STATE,
    "SEPARATION_SECTION_OVERLAP": WORK_STATE,
    "SEPARATION_SECTION_ORPHANED": WORK_STATE,
    "SEPARATION_NOTATION_GAP": WORK_STATE,
    # --- the-whole-cut-is-argued-before-any-section-is-claimed, U3/U4: round
    # persistence (`paper_declarations.record_separation_round`/`read_
    # separation_rounds`, a fourth `declarations`-region record kind) and the
    # concession check (`_check_separation_concession`, recomputed from disk,
    # never trusting a stored score) -----------------------------------------
    "SEPARATION_ROUND_ABSENT": WORK_STATE,
    "SEPARATION_CONCESSION_REGRESSED": WORK_STATE,
    # --- the-whole-cut-is-argued-before-any-section-is-claimed, U6 (owner
    # amendment, design.md Decision I): `bind`'s own precondition -- for a
    # measured, document-rooted fact, no settled `separate` round licenses
    # this exact `(block, fact)` claim with this exact title set against the
    # document resolved and digested right now (`paper_declarations.
    # settled_round_licensing`, enforced inside `bind_section` itself) -----
    "BINDING_UNARGUED": WORK_STATE,
    # --- the-tripwire-reaches-the-section-that-feeds-it, WU2: a
    # transposition-mode block's draft pasting a run from its own bound
    # source section beyond a self-calibrated threshold
    # (`paper_leak.check_source_section_verbatim`, wired into `write_block`
    # after the style tripwire and before `substitute`) ------------------
    "SOURCE_SECTION_VERBATIM": WORK_STATE,
    # --- the-block-asserts-only-what-its-section-carries: a fourth sibling
    # in `write_block`'s judge chain, `paper_grounding.reconcile_support`
    # (wired after the verbatim check above and before `substitute`) --
    # per-sentence support reconciliation against a bound section's own
    # bytes. Every subject sentence must have a grounded `supported`
    # verdict to reach `substitute`; the permissive verdict carries the
    # burden of proof (design.md D1), which is why an absent account and a
    # missing verdict are both WORK_STATE, never merely an invocation flag
    # ----------------------------------------------------------------------
    "GROUNDING_ACCOUNT_ABSENT": WORK_STATE,
    "GROUNDING_SENTENCE_UNKNOWN": WORK_STATE,
    "GROUNDING_VERDICT_MISSING": WORK_STATE,
    "SECTION_UNSUPPORTED_CLAIM": WORK_STATE,
}


def cmd_scaffold(args: argparse.Namespace) -> dict:
    paper_dir = paper_scaffold.resolve_paper_dir(args.paper)
    return paper_scaffold.scaffold(paper_dir)


def cmd_status(args: argparse.Namespace) -> dict:
    paper_dir = paper_scaffold.resolve_paper_dir(args.paper)
    return paper_block.read_status(paper_dir)


def cmd_open(args: argparse.Namespace) -> dict:
    paper_dir = paper_scaffold.resolve_paper_dir(args.paper)
    positions_given = [flag for flag in ("after", "at_end") if getattr(args, flag, None)]
    if not positions_given:
        raise Refused(
            "OPEN_POSITION_REQUIRED",
            "--after <id> or --at-end is required.",
        )
    if len(positions_given) > 1:
        raise Refused(
            "OPEN_POSITION_CONFLICT",
            "--after and --at-end were given together; exactly one position is required.",
        )
    return paper_block.open_block(paper_dir, args.block, after=args.after, at_end=bool(args.at_end))


def cmd_substitute(args: argparse.Namespace) -> dict:
    paper_dir = paper_scaffold.resolve_paper_dir(args.paper)
    modes_given = [flag for flag in ("body", "adopt") if getattr(args, flag, None)]
    if not modes_given:
        raise Refused(
            "SUBSTITUTE_MODE_REQUIRED",
            "--body <path|-> or --adopt is required.",
        )
    if len(modes_given) > 1:
        raise Refused(
            "ADOPT_BODY_CONFLICT",
            "--body and --adopt were given together; --adopt takes no body.",
        )
    contract = Path(args.contract) if args.contract else None
    if args.adopt:
        return paper_block.substitute(paper_dir, args.block, adopt=True, contract=contract)
    raw = sys.stdin.buffer.read() if args.body == "-" else Path(args.body).read_bytes()
    return paper_block.substitute(paper_dir, args.block, new_body=raw, contract=contract)


def cmd_contract(args: argparse.Namespace) -> dict:
    if args.file:
        header, _body = paper_contract.parse(Path(args.file).read_bytes())
        return {
            "section": header.section,
            "position": header.position,
            "after": header.after,
            "blocks": header.blocks,
        }
    sections_dir = paper_contract.resolve_sections_dir(args.sections)
    corpus = paper_graph.assemble_corpus(sections_dir)
    edge_set = paper_graph.collect_edges(corpus)
    return {
        "sections": sorted(corpus.sections),
        "blocks": sorted(corpus.blocks),
        "danglingEdges": sorted(set(edge_set.dangling)),
    }


def _produced_satisfied_facts(produced_by: dict, opened_blocks: set) -> set:
    """A produced fact counts satisfied exactly when EVERY one of its
    producer blocks is a member of `opened_blocks` (`fact-production` spec,
    `Requirement: Produced-Fact Satisfaction Derived From the Producer's
    Written Status` — the same 'opened is written' rule the wave gate
    already uses). A fact with zero producers (nothing in this corpus
    produces it — legal when nothing requires it either, design.md
    Decision D) never counts satisfied by this route."""
    return {
        fact for fact, producer_ids in produced_by.items()
        if producer_ids and all(producer_id in opened_blocks for producer_id in producer_ids)
    }


def _resolve_produced_by(sections_dir: Path, fact_id: str) -> tuple:
    """`declare`'s own corpus-derived lookup (tasks.md, Unit 3, 3.4): the
    tuple of qualified producer ids `fact_id` resolves to, or `()` when the
    corpus cannot even be assembled (mirrors `paper_coupling_evidence.
    _blocks_by_fact`'s own defensive `try/except Refused` fallback — a
    `declare` call against an unassemblable corpus degrades to the
    pre-existing declarable-route behaviour rather than refusing on an
    unrelated corpus defect)."""
    try:
        corpus = paper_graph.assemble_corpus(sections_dir)
    except Refused:
        return ()
    return paper_graph.producers_by_fact(corpus).get(fact_id, ())


def compute_readiness_report(
    sections_dir: Path,
    *,
    paper_dir: Path | None = None,
    flag_facts: frozenset = frozenset(),
    flag_declarations: frozenset = frozenset(),
) -> dict:
    """The basis dispatch `readiness` reports, kept separate from `cmd_
    readiness`'s own `--paper`/`--sections` string resolution -- the same
    separation `compute_plan` already keeps from `cmd_plan`
    (`the-phases-are-derived-not-remembered`, design.md D3, tasks.md 6.4).

    `paper_dir` given -> basis `"declaration-backed"`: satisfied sets are
    read from the `declarations` region (`paper_declarations.read_
    satisfied`), merged with `flag_facts`/`flag_declarations` on top (any
    flag-given id not already recorded on disk is reported separately,
    under `"supposed"` -- design.md D3's own "each labelled `source:
    supposed`"), and `opened_blocks` is resolved from `main.tex` (`paper_
    block.read_status`) so `not-applicable` can fire for an optional,
    unopened block. This closes the regression where `cmd_readiness` never
    opened `main.tex`, so its answer never changed after `declare`.

    `paper_dir` omitted, with at least one flag given -> the hypothetical
    what-if preserved exactly as it behaved before this unit, basis
    `"supposed-only"`.

    Neither given -> refuses `READINESS_BASIS_REQUIRED`: the stale-number
    path (computing an answer from flags alone while silently ignoring an
    existing `declarations` region) is removed, never defaulted.

    `produced_by` (`a-fact-is-declared-or-it-is-produced`, `fact-production`
    spec, `Requirement: Produced-Fact Satisfaction Derived From the
    Producer's Written Status`) is resolved from the SAME assembled
    `corpus` via `paper_graph.producers_by_fact`, in both branches. A
    produced fact is NEVER read from `declared_facts` (the `declarations`
    region carve-out, `paper-declarations` spec) — its satisfaction is
    derived exclusively from whether every one of its producer blocks is
    opened in `main.tex`. `blocked_on_produced` is threaded into every
    block's own report unconditionally, so a hypothetical `--fact` call
    still names the producer of anything still missing.
    """
    corpus = paper_graph.assemble_corpus(sections_dir)
    produced_by = paper_graph.producers_by_fact(corpus)
    produced_fact_ids = set(produced_by)
    flag_facts = set(flag_facts)
    flag_declarations = set(flag_declarations)

    if paper_dir is not None:
        declared_facts, declared_declarations = paper_declarations.read_satisfied(paper_dir)
        declined_facts = paper_declarations.read_declined(paper_dir)
        opened_blocks = {block["id"] for block in paper_block.read_status(paper_dir)["blocks"]}
        produced_satisfied = _produced_satisfied_facts(produced_by, opened_blocks)
        satisfied_facts = (declared_facts - produced_fact_ids) | flag_facts | produced_satisfied
        satisfied_declarations = declared_declarations | flag_declarations
        basis = "declaration-backed"
    elif flag_facts or flag_declarations:
        declared_facts = set()
        declared_declarations = set()
        declined_facts = {}
        opened_blocks = None
        satisfied_facts = flag_facts
        satisfied_declarations = flag_declarations
        basis = "supposed-only"
    else:
        raise Refused(
            "READINESS_BASIS_REQUIRED",
            "readiness needs either --paper <dir> (reads the declarations region) "
            "or at least one --fact/--declaration flag (a hypothetical what-if); "
            "a bare call with neither has no basis to compute an answer from.",
        )

    report = paper_readiness.compute_readiness(
        corpus,
        satisfied_facts=satisfied_facts,
        satisfied_declarations=satisfied_declarations,
        opened_blocks=opened_blocks,
        basis=basis,
        declined_facts=declined_facts,
        produced_by=produced_by,
    )
    result = {"basis": basis, "blocks": report}
    if basis == "declaration-backed":
        supposed = sorted((flag_facts | flag_declarations) - (declared_facts | declared_declarations))
        if supposed:
            result["supposed"] = supposed
    return result


def cmd_readiness(args: argparse.Namespace) -> dict:
    sections_dir = paper_contract.resolve_sections_dir(args.sections)
    paper_dir = paper_scaffold.resolve_paper_dir(args.paper) if args.paper else None
    return compute_readiness_report(
        sections_dir,
        paper_dir=paper_dir,
        flag_facts=frozenset(args.fact or []),
        flag_declarations=frozenset(args.declaration or []),
    )


def cmd_order(args: argparse.Namespace) -> dict:
    sections_dir = paper_contract.resolve_sections_dir(args.sections)
    corpus = paper_graph.assemble_corpus(sections_dir)
    edge_set = paper_graph.collect_edges(corpus)
    order = paper_graph.derive_order(corpus, edge_set)
    return {"order": order, "danglingEdges": sorted(set(edge_set.dangling))}


def _skeleton_excluded_ids(corpus, *, related_work: bool, dataset_in: str) -> set:
    """The block ids `skeleton` leaves unopened for the given answers
    (design.md D4; tasks.md 7.8): every `related-work` block when Related
    Work is "no", and every dataset-placement candidate
    (`paper_declarations.dataset_placement_candidates`) NOT sitting in the
    chosen section. Every other block id is opened unconditionally.

    Derives which candidate belongs to which section from the corpus
    itself -- never a literal `mm-dataset`/`es-dataset` id pair (the
    `a-fact-source-nobody-checks` corrective: those two ids used to be
    hardcoded here, via `paper_declarations.MM_DATASET_ID`/`ES_DATASET_ID`,
    a violation of this skill's own "block ids are shape only" invariant).
    """
    excluded: set = set()
    if not related_work:
        excluded |= set(corpus.order_by_section.get("related-work", ()))
    candidates = paper_declarations.dataset_placement_candidates(corpus)
    chosen_section = (
        "materials-and-methods" if dataset_in == "materials" else "experimental-setup"
    )
    excluded |= {qid for section, qid in candidates.items() if section != chosen_section}
    return excluded


def build_skeleton(
    paper_dir: Path, sections_dir: Path, *, related_work: str | None, dataset_in: str | None,
) -> dict:
    """`skeleton`'s own logic, taking `paper_dir`/`sections_dir` directly —
    the same separation `compute_phases`/`compute_readiness_report` keep
    from their own `cmd_*` wrappers — so a test can inject both without
    going through argparse's own resolution (design.md D4;
    `specs/skeleton-startup/spec.md`).

    Asks nothing itself — the orchestrator asks the two blocking questions
    exactly once — and opens every non-excluded block id through `paper_
    block.open_block` alone, in `derive_order` order: never a new writer,
    so the byte-identity invariant `open_block` already carries is
    untouched (tasks.md 7.13, Threat Matrix "Write amplification into
    `main.tex`").

    Refuses `SKELETON_ANSWER_REQUIRED` (invocation-defect) when either
    `related_work` or `dataset_in` is `None`. Once any corpus block is
    already opened, both decisions are re-derived straight from disk
    (`paper_declarations.infer_skeleton_decisions` — never a stored flag,
    design.md D4) and compared against the given answers: a contradiction
    refuses `SKELETON_ALREADY_DECIDED` (work-state) naming both what disk
    already records and what was requested. Already-opened ids are skipped
    — idempotent, never re-opened, never re-asked.
    """
    if related_work is None or dataset_in is None:
        missing = [
            flag for flag, value in (
                ("--related-work", related_work), ("--dataset-in", dataset_in),
            )
            if value is None
        ]
        raise Refused(
            "SKELETON_ANSWER_REQUIRED",
            "skeleton needs both --related-work yes|no and --dataset-in "
            f"materials|experimental-setup; missing {missing}",
        )

    corpus = paper_graph.assemble_corpus(sections_dir)

    related_work_flag = related_work == "yes"
    requested_placement = (
        "materials-and-methods" if dataset_in == "materials" else "experimental-setup"
    )

    status = paper_block.read_status(paper_dir)
    opened_ids = {block["id"] for block in status["blocks"]}

    if opened_ids:
        decided = paper_declarations.infer_skeleton_decisions(paper_dir, corpus)
        dataset_mismatch = (
            decided["datasetPlacement"] != "undecided"
            and decided["datasetPlacement"] != requested_placement
        )
        if decided["relatedWork"] != related_work_flag or dataset_mismatch:
            raise Refused(
                "SKELETON_ALREADY_DECIDED",
                f"disk already records relatedWork={decided['relatedWork']!r}, "
                f"datasetPlacement={decided['datasetPlacement']!r}; the given flags "
                f"(relatedWork={related_work_flag!r}, datasetPlacement={requested_placement!r}) "
                "contradict it",
            )

    excluded = _skeleton_excluded_ids(corpus, related_work=related_work_flag, dataset_in=dataset_in)
    edge_set = paper_graph.collect_edges(corpus)
    order = paper_graph.derive_order(corpus, edge_set)

    opened = []
    for qualified_id in order:
        if qualified_id in excluded or qualified_id in opened_ids:
            continue
        paper_block.open_block(paper_dir, qualified_id, at_end=True)
        opened_ids.add(qualified_id)
        opened.append(qualified_id)

    return {
        "relatedWork": related_work_flag,
        "datasetPlacement": requested_placement,
        "opened": opened,
    }


def cmd_skeleton(args: argparse.Namespace) -> dict:
    paper_dir = paper_scaffold.resolve_paper_dir(args.paper)
    sections_dir = paper_contract.resolve_sections_dir(args.sections)
    return build_skeleton(
        paper_dir, sections_dir, related_work=args.related_work, dataset_in=args.dataset_in,
    )


def cmd_declare(args: argparse.Namespace) -> dict:
    paper_dir = paper_scaffold.resolve_paper_dir(args.paper)
    sections_dir = paper_contract.resolve_sections_dir(args.sections)
    modes_given = [
        flag for flag in ("declaration", "fact", "reopen", "decline") if getattr(args, flag, None)
    ]
    if not modes_given:
        raise Refused(
            "DECLARE_MODE_REQUIRED",
            "exactly one of --declaration <id>, --fact <id>, --reopen <id>, --decline <id> is required.",
        )
    if len(modes_given) > 1:
        raise Refused(
            "DECLARE_MODE_CONFLICT",
            f"{modes_given} were given together; exactly one mode is required.",
        )
    if args.reopen:
        return paper_declarations.reopen(paper_dir, args.reopen)
    if args.decline:
        condition = None
        if args.condition is not None:
            try:
                condition = json.loads(args.condition)
            except json.JSONDecodeError as exc:
                raise Refused("CONDITION_MALFORMED", f"--condition is not valid JSON: {exc.msg}")
        produced_by = _resolve_produced_by(sections_dir, args.decline)
        return paper_declarations.decline_fact(
            paper_dir, args.decline, args.reason, condition, produced_by=produced_by,
        )
    if args.value is None:
        raise Refused(
            "DECLARE_VALUE_REQUIRED",
            "--declaration/--fact requires --value <the recorded value or resolution>.",
        )
    if args.declaration:
        return paper_declarations.set_declaration(paper_dir, args.declaration, args.value)
    produced_by = _resolve_produced_by(sections_dir, args.fact)
    return paper_declarations.set_fact(paper_dir, args.fact, args.value, produced_by=produced_by)


def cmd_bind(args: argparse.Namespace) -> dict:
    """`bind`: the CLI front door for `source-section-binding`'s own
    recording verb -- the one place a genuinely undecided binding
    (`SECTION_BINDING_ABSENT`, raised only at `write`'s own gate) gets
    answered by an operator USING the skill, never by hand-editing
    `sections/*.md` (which ships with the forge and must stay byte-
    identical to `main`) and never by an agent reading conversation prose
    (`the-requirement-names-the-section-that-feeds-it`, U3e ruling,
    design.md Decision J). `--reopen` clears an already-recorded (block,
    fact) pair's fixed state instead of recording one (`paper_
    declarations.reopen_binding`) -- deliberately unguarded by the owner
    amendment below, since withdrawing a claim never creates one. Every
    other invocation records (`paper_declarations.bind_section`), which
    itself refuses `UNKNOWN_FACT`, `BINDING_FACT_NOT_BINDABLE`,
    `BINDING_LINEAGE_REQUIRED`, `BINDING_SECTIONS_REQUIRED`,
    `DECLARATION_FIXED` and, for a measured root, `BINDING_UNARGUED`
    (`the-whole-cut-is-argued-before-any-section-is-claimed`, design.md
    Decision I) — all enforced in that module, not duplicated here.

    `--sections` (the owner amendment's own addition, same default/help
    text every sibling subcommand carries) resolves `sections_dir`, whose
    PARENT is `source_base` — the identical `resolved_base = source_base
    or sections_dir.parent` derivation `paper_graph.assemble_corpus` uses,
    so `bind`'s own precondition resolves a `PROSE`-kind root under the
    SAME directory `separate`/`write` already resolve it under.
    """
    paper_dir = paper_scaffold.resolve_paper_dir(args.paper)
    if args.reopen:
        return paper_declarations.reopen_binding(paper_dir, args.block, args.fact)
    sections_dir = paper_contract.resolve_sections_dir(args.sections)
    return paper_declarations.bind_section(
        paper_dir, args.block, args.fact, args.lineage, tuple(args.section or ()),
        source_base=sections_dir.parent,
    )


def cmd_mark_revisions(args: argparse.Namespace) -> dict:
    """`mark revisions`: the CLI front door for `paper_declarations.
    declare_revisions` (design.md Decision D/F; `specs/source-declaration-
    authoring/spec.md`, `Requirement: A Source Root's Revision Rule Is
    Recorded And Validated Against Disk By Using The Skill`) -- the answer
    to `SOURCE_REVISIONS_UNDECLARED` a person gives BY USING THE SKILL,
    never by hand-editing `<root>/.paper-writing.json` with a file-writing
    tool.

    `--root` is matched against `declare_revisions`'s own derived
    declarable-root map; no operator string is ever joined onto a path
    (design.md Decision D). The source base is `paper_dir.parent`, the
    IDENTICAL derivation `compute_plan`'s own `sourceRoots` and
    `_binding_separation_report` already use -- never a second convention
    for where a root resolves from."""
    paper_dir = paper_scaffold.resolve_paper_dir(args.paper)
    return paper_declarations.declare_revisions(
        paper_dir.parent, args.root, args.revision_prefix, args.ordinal_digits,
        sealed=not args.unsealed,
    )


def cmd_mark_class(args: argparse.Namespace) -> dict:
    """`mark class`: the CLI front door for `paper_guidance.declare_class`
    (design.md Decision D/F, guidance half; `specs/guidance-registry/
    spec.md`) -- the answer to an unclassified `guidance/<folder>` a person
    gives BY USING THE SKILL, never by hand-editing
    `guidance/<folder>/.paper-writing.json` with a file-writing tool.

    `--folder` is matched against `declare_class`'s own derived folder
    enumeration; no operator string is ever joined onto a path (design.md
    Decision D)."""
    guidance_dir = paper_guidance.resolve_guidance_dir(args.guidance)
    return paper_guidance.declare_class(
        guidance_dir, args.folder, args.class_value, sealed=not args.unsealed,
    )


def cmd_mark(args: argparse.Namespace) -> dict:
    """`mark`: one root with two modes, `revisions` and `class` (design.md
    Decision D: same subject, same root, the `bib build` two-level nesting
    precedent). `mark_command` is `required=True` with `revisions` and
    `class` its only registered choices, so this dispatch is exhaustive as
    written."""
    if args.mark_command == "class":
        return cmd_mark_class(args)
    return cmd_mark_revisions(args)


#: `_read_separation_proposal`'s own closed key-set grammar (design.md,
#: Interfaces / Contracts) -- the marker's own closed-grammar discipline,
#: reused: `lineage`/`assignments` required, `concedes_to_round` optional,
#: nothing else admitted.
_SEPARATION_TOP_KEYS = frozenset({"lineage", "assignments", "concedes_to_round"})
_SEPARATION_REQUIRED_TOP_KEYS = frozenset({"lineage", "assignments"})
_SEPARATION_ASSIGNMENT_KEYS = frozenset({"block", "fact", "sections"})


def _read_separation_proposal(proposal_path: Path) -> dict:
    """`separate --proposal <path>`'s own shape stage (design.md, Interfaces
    / Contracts; `source-separation-review` spec, `Requirement: The
    Proposal File Has One Validated Shape`) -- the same shuttle-file read
    `compute_observation` keeps, widened with this verb's own grammar.

    Refuses `SEPARATION_REPORT_UNREADABLE` (work-state) for every shape
    violation named by the spec: unreadable, non-UTF-8, non-JSON,
    non-object, a wrong/unknown top-level key, a missing required key, a
    wrong-shaped assignment, `sections` not a list of unique non-empty
    strings, a duplicate `(block, fact)` pair across assignments, or the
    named facts resolving through more than one source root
    (`_resolve_separation_root` below). Every OTHER stage this file wires
    (per-title resolution, claimability, scoring, precedence) runs only
    once this function returns cleanly.

    Returns `{"lineage": str, "assignments": [{"block", "fact",
    "sections": tuple}, ...], "concedes_to_round": int|None, "root":
    paper_declarations.SourceRoot}` -- `root` is derived here, once, so no
    later stage re-derives it from the raw facts a second time.
    """
    try:
        raw = proposal_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise Refused("SEPARATION_REPORT_UNREADABLE", f"{proposal_path}: {exc}")
    try:
        report = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise Refused("SEPARATION_REPORT_UNREADABLE", f"{proposal_path}: invalid JSON: {exc.msg}")
    if not isinstance(report, dict):
        raise Refused("SEPARATION_REPORT_UNREADABLE", f"{proposal_path}: must be a JSON object")

    unknown_keys = set(report) - _SEPARATION_TOP_KEYS
    if unknown_keys:
        raise Refused(
            "SEPARATION_REPORT_UNREADABLE",
            f"{proposal_path}: unknown top-level key(s) {sorted(unknown_keys)}",
        )
    missing_keys = _SEPARATION_REQUIRED_TOP_KEYS - set(report)
    if missing_keys:
        raise Refused(
            "SEPARATION_REPORT_UNREADABLE",
            f"{proposal_path}: missing required key(s) {sorted(missing_keys)}",
        )

    lineage = report["lineage"]
    if not isinstance(lineage, str) or not lineage:
        raise Refused(
            "SEPARATION_REPORT_UNREADABLE", f"{proposal_path}: 'lineage' must be a non-empty string",
        )

    concedes_to_round = report.get("concedes_to_round")
    if concedes_to_round is not None and (
        isinstance(concedes_to_round, bool) or not isinstance(concedes_to_round, int)
    ):
        raise Refused(
            "SEPARATION_REPORT_UNREADABLE",
            f"{proposal_path}: 'concedes_to_round' must be an integer",
        )

    raw_assignments = report["assignments"]
    if not isinstance(raw_assignments, list) or not raw_assignments:
        raise Refused(
            "SEPARATION_REPORT_UNREADABLE",
            f"{proposal_path}: 'assignments' must be a non-empty list",
        )

    assignments = []
    seen_pairs = set()
    fact_ids = []
    for entry in raw_assignments:
        if not isinstance(entry, dict) or set(entry) != _SEPARATION_ASSIGNMENT_KEYS:
            raise Refused(
                "SEPARATION_REPORT_UNREADABLE",
                f"{proposal_path}: each assignment must carry exactly "
                f"{sorted(_SEPARATION_ASSIGNMENT_KEYS)}, got {entry!r}",
            )
        block, fact, sections = entry["block"], entry["fact"], entry["sections"]
        if not isinstance(block, str) or not block:
            raise Refused(
                "SEPARATION_REPORT_UNREADABLE", f"{proposal_path}: 'block' must be a non-empty string",
            )
        if not isinstance(fact, str) or not fact:
            raise Refused(
                "SEPARATION_REPORT_UNREADABLE", f"{proposal_path}: 'fact' must be a non-empty string",
            )
        if (
            not isinstance(sections, list) or not sections
            or not all(isinstance(title, str) and title for title in sections)
            or len(set(sections)) != len(sections)
        ):
            raise Refused(
                "SEPARATION_REPORT_UNREADABLE",
                f"{proposal_path}: 'sections' must be a list of unique non-empty strings, "
                f"got {sections!r}",
            )
        pair = (block, fact)
        if pair in seen_pairs:
            raise Refused(
                "SEPARATION_REPORT_UNREADABLE",
                f"{proposal_path}: duplicate assignment for (block, fact) = {pair!r}",
            )
        seen_pairs.add(pair)
        fact_ids.append(fact)
        assignments.append({"block": block, "fact": fact, "sections": tuple(sections)})

    root = _resolve_separation_root(proposal_path, fact_ids)
    return {
        "lineage": lineage, "assignments": assignments,
        "concedes_to_round": concedes_to_round, "root": root,
    }


def _resolve_separation_root(proposal_path: Path, fact_ids: list) -> object:
    """The facts named across the whole proposal MUST resolve through
    EXACTLY one source root (`source-separation-review` spec). Refuses
    `UNKNOWN_FACT`/`BINDING_FACT_NOT_BINDABLE` verbatim
    (`paper_vocabulary.validate_fact`/`paper_declarations.
    is_bindable_fact`, reused, never a second code for the same
    condition) for an individual bad fact id, and
    `SEPARATION_REPORT_UNREADABLE` naming every distinct root name found
    when more than one is named -- a file spanning two roots is not one
    document's cut at all, so it fails the FILE's own contract rather than
    earning a code of its own (design.md, Interfaces / Contracts)."""
    roots = {}
    for fact_id in fact_ids:
        paper_vocabulary.validate_fact(fact_id)
        if not paper_declarations.is_bindable_fact(fact_id):
            raise Refused(
                "BINDING_FACT_NOT_BINDABLE",
                f"{fact_id!r} is not a key of FACT_SOURCE_ROOT; it has no document-rooted "
                "source to bind at all",
            )
        source_root = paper_declarations.FACT_SOURCE_ROOT[fact_id]
        roots[source_root.name] = source_root
    if len(roots) > 1:
        raise Refused(
            "SEPARATION_REPORT_UNREADABLE",
            f"{proposal_path}: assignments resolve through more than one source root: "
            f"{sorted(roots)}",
        )
    return next(iter(roots.values()))


def _bind_invocation(entry: dict, lineage: str) -> str:
    """The exact `bind` invocation a settled (score-0) cut's own assignment
    answers -- named in the payload, never recorded (design.md, Decision
    G: `separate` never calls `bind`)."""
    section_flags = " ".join(f"--section {title!r}" for title in entry["sections"])
    return f"bind --block {entry['block']} --fact {entry['fact']} --lineage {lineage} {section_flags}"


def _separation_structural_detail(result: dict) -> str:
    """Every instance of every present class, plus all four counted
    totals -- built once so a raise from `_raise_separation_refusal` names
    everything `paper_separation.score_cut` counted, never merely the
    first defect (design.md Decision E; task 2.12's own separately-
    checkable property)."""
    orphan_count = len(result["orphan"])
    overlap_count = sum(item["count"] for item in result["overlap"])
    gap_count = len(result["gap"])
    parts = [f"total={result['total']} (orphan={orphan_count}, overlap={overlap_count}, gap={gap_count})"]
    if result["overlap"]:
        parts.append(
            "overlap: " + "; ".join(
                f"{item['title']!r} claimed by {list(item['blocks'])!r}"
                for item in result["overlap"]
            )
        )
    if result["orphan"]:
        parts.append(f"orphan: {result['orphan']!r}")
    if result["gap"]:
        parts.append(
            "gap: " + "; ".join(
                f"{item['block']!r} skips {item['title']!r}" for item in result["gap"]
            )
        )
    return " | ".join(parts)


def _raise_separation_refusal(result: dict, recorded_round_id: str) -> None:
    """Fixed precedence `overlap -> orphan -> gap` (design.md Decision E):
    exactly ONE code, chosen by whichever class is present first in that
    order, with a detail naming every instance of every class present
    PLUS the id of the round `record_separation_round` just recorded
    (task 3.9: recording happens before this refusal, and the refusal
    names it)."""
    detail = _separation_structural_detail(result) + f" | recorded round: {recorded_round_id!r}"
    if result["overlap"]:
        raise Refused("SEPARATION_SECTION_OVERLAP", detail)
    if result["orphan"]:
        raise Refused("SEPARATION_SECTION_ORPHANED", detail)
    raise Refused("SEPARATION_NOTATION_GAP", detail)


def _claims_by_block(assignments, corpus) -> tuple:
    """Anchor every assignment against the corpus's OWN `requires_facts`
    (design.md, Technical Approach, step 5): an assignment for a `(block,
    fact)` pair that is not a real `requires_facts` entry is unanchored --
    reported, never deleted or invented, and it contributes nothing to
    coverage. Shared between the current cut's own scoring and the
    concession check's recompute of a PRIOR round's assignments
    (`_check_separation_concession` below), so both go through the
    identical anchoring rule rather than two copies that could drift."""
    claims_by_block: dict = {}
    unanchored = []
    for entry in assignments:
        block, fact = entry["block"], entry["fact"]
        record = corpus.blocks.get(block)
        if record is None or fact not in record.requires_facts:
            unanchored.append({"block": block, "fact": fact})
            continue
        claims_by_block.setdefault(block, [])
        claims_by_block[block].extend(entry["sections"])
    return claims_by_block, unanchored


def _find_separation_round(paper_dir: Path, root_name: str, lineage: str, revision: str, round_number: int):
    for entry in paper_declarations.read_separation_rounds(paper_dir, root_name, lineage, revision):
        if entry["round"] == round_number:
            return entry
    return None


def _check_separation_concession(
    paper_dir: Path, root_name: str, lineage: str, revision: str, concedes_to_round,
    result: dict, claimable: dict, corpus,
) -> None:
    """design.md Decision E/`source-separation-review` spec, `Requirement:
    A Concession Is Verified By Recomputing Both Cuts From Disk, Before
    The Structural Refusal`: BOTH totals are recomputed here, from disk,
    every time -- the conceding cut's own `result` (already computed by
    the caller) and the conceded round's own `assignments`, read back and
    re-scored through the SAME `_claims_by_block`/`score_cut` path, never
    trusting either round's stored `score` field. Ties are not a
    regression: an EQUAL total is accepted.

    Called BEFORE the structural refusal (`compute_separation`'s own
    ordering, task 4.3/4.4): reversed, `SEPARATION_CONCESSION_REGRESSED`
    would be a refusal that could never fire, since only a score-0 cut
    would ever reach it."""
    if concedes_to_round is None:
        return
    conceded_round = _find_separation_round(paper_dir, root_name, lineage, revision, concedes_to_round)
    if conceded_round is None:
        raise Refused(
            "SEPARATION_ROUND_ABSENT",
            f"concedes_to_round={concedes_to_round} names no recorded round for "
            f"(root={root_name!r}, lineage={lineage!r}, revision={revision!r})",
        )
    conceded_claims, _unanchored = _claims_by_block(conceded_round["assignments"], corpus)
    conceded_result = paper_separation.score_cut(claimable["titles"], conceded_claims)
    if result["total"] > conceded_result["total"]:
        raise Refused(
            "SEPARATION_CONCESSION_REGRESSED",
            f"the conceding cut scores {result['total']}, worse than round "
            f"{concedes_to_round}'s recomputed score {conceded_result['total']} (both recomputed "
            f"from disk, never from a stored score field)",
        )


def compute_separation(
    proposal_path: Path, *, sections_dir: Path, paper_dir: Path, source_base: Path | None = None,
) -> dict:
    """`separate`'s own logic on already-resolved paths (design.md,
    Interfaces / Contracts) -- the same separation `compute_observation`
    keeps from `cmd_observe`.

    The fixed pipeline (design.md, Technical Approach): (1) shape
    (`_read_separation_proposal`, above); (2) assemble the real corpus
    (`enforce_bindings=False`, so an undecided binding elsewhere never
    blocks this read-only verb) and reuse its OWN `source_roots` for
    `paper_graph.resolve_section_index` -- one corpus assembly, not two,
    since `Corpus.source_roots` already carries everything that function
    needs (a deliberate refinement over assembling the corpus a second
    time just to recompute the identical dict); (3) derive the claimable
    set (`paper_separation.claimable_sections`) -- an UNMEASURED claimable
    set refuses `SEPARATION_SECTION_UNCLAIMABLE` immediately, before any
    per-title check, because there is no structure to resolve a title
    against at all; (4) per-title existence/ambiguity
    (`SECTION_NOT_IN_SOURCE`/`SECTION_TITLE_AMBIGUOUS`, the SAME checks
    `bind` already uses) then claimability
    (`SEPARATION_SECTION_UNCLAIMABLE`) for every named title, before any
    scoring runs; (5) anchor every assignment against the corpus's own
    `requires_facts` (unanchored ones are reported, never deleted or
    invented, and clear no orphan) and score (`paper_separation.
    score_cut`); (6) `concedes_to_round`, when given, is verified BEFORE
    anything is recorded (`_check_separation_concession`,
    `SEPARATION_ROUND_ABSENT`/`SEPARATION_CONCESSION_REGRESSED`); (7)
    EVERY structurally-valid round records now, whatever its score
    (`paper_declarations.record_separation_round`, U3) -- Decision F/G:
    `separate` writes ONLY `kind="separation"`, never a `binding`, under
    any outcome; (8) a score-0 cut returns naming the exact `bind`
    invocation for every assignment, and any nonzero total raises the ONE
    structural refusal fixed precedence names, naming the round just
    recorded (`_raise_separation_refusal`).
    """
    proposal = _read_separation_proposal(proposal_path)
    lineage = proposal["lineage"]
    assignments = proposal["assignments"]
    root = proposal["root"]
    concedes_to_round = proposal["concedes_to_round"]

    corpus = paper_graph.assemble_corpus(sections_dir, source_base=source_base, paper_dir=paper_dir)
    status = corpus.source_roots.get(root.name)
    if status is None or status["state"] != "document-rooted":
        raise Refused(
            "SEPARATION_SECTION_UNCLAIMABLE",
            f"{root.name!r} is not document-rooted; lineage {lineage!r} has no document to "
            f"measure a cut against ({(status or {}).get('reason')})",
        )
    revision_path, counts, outline = paper_graph.resolve_section_index(
        corpus.source_roots, root, lineage,
    )
    claimable = paper_separation.claimable_sections(outline)
    if claimable["state"] == "unmeasured":
        raise Refused(
            "SEPARATION_SECTION_UNCLAIMABLE",
            f"lineage {lineage!r}'s claimable set is unmeasured ({claimable['reason']})",
        )
    claimable_titles = set(claimable["titles"])

    for entry in assignments:
        block = entry["block"]
        for title in entry["sections"]:
            count = counts.get(title, 0)
            if count == 0:
                raise Refused(
                    "SECTION_NOT_IN_SOURCE",
                    f"{block}: section {title!r} is not a heading in the resolved revision "
                    f"(lineage {lineage!r})",
                )
            if count > 1:
                raise Refused(
                    "SECTION_TITLE_AMBIGUOUS",
                    f"{block}: section {title!r} matches {count} headings (lineage {lineage!r})",
                )
            if title not in claimable_titles:
                raise Refused(
                    "SEPARATION_SECTION_UNCLAIMABLE",
                    f"{block}: section {title!r} is not in the claimable set "
                    f"{claimable['titles']!r}",
                )

    claims_by_block, unanchored = _claims_by_block(assignments, corpus)
    result = paper_separation.score_cut(claimable["titles"], claims_by_block)

    revision = revision_path.name
    document_digest = hashlib.sha256(revision_path.read_bytes()).hexdigest()

    _check_separation_concession(
        paper_dir, root.name, lineage, revision, concedes_to_round, result, claimable, corpus,
    )
    recorded_round = paper_declarations.record_separation_round(
        paper_dir, root.name, lineage, revision, document_digest, assignments, result["total"],
    )
    if result["total"] == 0:
        return {
            "total": 0, "unanchored": unanchored,
            "bind_invocations": [_bind_invocation(entry, lineage) for entry in assignments],
            "round": recorded_round["round"], "round_id": recorded_round["id"],
        }
    _raise_separation_refusal(result, recorded_round["id"])


def cmd_separate(args: argparse.Namespace) -> dict:
    paper_dir = paper_scaffold.resolve_paper_dir(args.paper)
    sections_dir = paper_contract.resolve_sections_dir(args.sections)
    proposal_path = _resolve_repo_path(args.proposal)
    return compute_separation(proposal_path, sections_dir=sections_dir, paper_dir=paper_dir)


def compute_observation(
    report_path: Path, *,
    proposals_dir: Path | None = None, experiments_dir: Path | None = None,
    implementation_dir: Path | None = None,
) -> dict:
    """`observe`'s own logic, taking already-resolved paths directly — the
    same separation `compute_plan`/`compute_readiness_report`/`build_
    skeleton` keep from their own `cmd_*` wrappers, so a test can inject
    every root without going through argparse's own defaulting.

    Validates an already-produced `insumos-observer` report against the
    observable-fact schema and the `implementation`/`results`
    evidence-conflation guard, THEN reconciles it against a real disk
    measurement THIS process takes itself
    (`paper_declarations.source_available`, gitignore-blind by construction
    — `the-skill-stops-trusting-memory`, item 5) for every root given.
    Read-only: never calls `declare`, never writes anything, regardless of
    outcome.

    Refuses `OBSERVATION_DISK_CONFLICT` (work-state) when the report claims
    a fact UNSATISFIED with no evidence while that fact's own source root
    is measurably non-empty right now (`paper_declarations.
    reconcile_observation_report`) — a disagreement is named, never
    averaged into a report that simply trusts the agent's word. A root not
    given here (most commonly `implementation_dir`, which has no fixed
    default) is never measured and never reconciled against — this refuses
    only what it can actually prove wrong, never what it merely suspects.
    """
    try:
        raw = report_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise Refused("OBSERVATION_REPORT_UNREADABLE", f"{report_path}: {exc}")
    try:
        report = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise Refused("OBSERVATION_REPORT_UNREADABLE", f"{report_path}: invalid JSON: {exc.msg}")
    if not isinstance(report, dict):
        raise Refused("OBSERVATION_REPORT_UNREADABLE", f"{report_path}: must be a JSON object")
    paper_declarations.validate_observation_report(report)

    measured = {}
    for name, root in (
        ("proposals", proposals_dir), ("experiments", experiments_dir),
        ("implementation", implementation_dir),
    ):
        if root is not None:
            measured[name] = paper_declarations.source_available(root)

    disagreements = paper_declarations.reconcile_observation_report(report, measured)
    if disagreements:
        raise Refused(
            "OBSERVATION_DISK_CONFLICT",
            f"the report disagrees with what this process measured on disk: {disagreements}",
        )

    satisfied = sorted(
        fact for fact, entry in report.items() if isinstance(entry, dict) and entry.get("satisfied")
    )
    return {
        "validated": True, "facts": sorted(report.keys()), "satisfied": satisfied,
        "measured": measured,
    }


def cmd_observe(args: argparse.Namespace) -> dict:
    """`observe`: the CLI front door for `compute_observation` — resolves
    `--report` (required) and `--proposals`/`--experiments`/
    `--implementation` (each optional, none defaulted) against the real
    repository root before delegating.

    None of the three roots defaults to this repository's own top-level
    folder: `proposals/`/`experiments/` are long-lived, ongoing project
    directories in this repository's own real layout, routinely non-empty
    for reasons unrelated to any one paper's current facts, so silently
    defaulting to them would reconcile against content that says nothing
    about THIS observation and misfire (measured against this very
    repository, 2026-09-18: both are non-empty right now). Reconciliation
    only ever fires for a root the caller explicitly names, matching
    `--implementation`'s own always-optional treatment.
    """
    report_path = _resolve_repo_path(args.report)
    proposals_dir = _resolve_repo_path(args.proposals) if args.proposals else None
    experiments_dir = _resolve_repo_path(args.experiments) if args.experiments else None
    implementation_dir = _resolve_repo_path(args.implementation) if args.implementation else None
    return compute_observation(
        report_path, proposals_dir=proposals_dir, experiments_dir=experiments_dir,
        implementation_dir=implementation_dir,
    )


def cmd_resolve(args: argparse.Namespace) -> dict:
    """`resolve`: one identifier through one connector, cached by its own
    digest. Under `paper/.paper-writing/metadata/` by default, where `bib`
    and `full_text` read it; under `--cache-dir` instead for a caller that is
    not writing a paper (the plausibility agents pass their own pool), so
    confirming a reference never starts a `paper/` tree. Both locations are
    resolved, and refused if outside the repository, before any request."""
    if args.cache_dir is not None:
        cache_dir = _resolve_repo_path(args.cache_dir)
        paper_dir = None
    else:
        paper_dir = paper_scaffold.resolve_paper_dir(args.paper)
    config = paper_resolve.load_config()
    result = paper_resolve.resolve_identifier(
        args.identifier, resolver=args.resolver, role=args.role, config=config,
    )
    if paper_dir is None:
        paper_resolve.cache_metadata_in(cache_dir, result)
    else:
        paper_resolve.cache_metadata(paper_dir, result)
    return result


def cmd_full_text(args: argparse.Namespace) -> dict:
    paper_dir = paper_scaffold.resolve_paper_dir(args.paper)
    guidance_dir = paper_guidance.resolve_guidance_dir(args.guidance)
    config = paper_resolve.load_config()
    return paper_full_text.fetch_full_text(
        paper_dir, guidance_dir, section_id=args.section, metadata_digest=args.metadata_digest,
        cite_key=args.cite_key, config=config,
    )


def cmd_bib(args: argparse.Namespace) -> dict:
    paper_dir = paper_scaffold.resolve_paper_dir(args.paper)
    guidance_dir = paper_guidance.resolve_guidance_dir(args.guidance)
    if args.bib_command == "refresh":
        return paper_bib.refresh_metadata(
            paper_dir, args.cite_key, args.metadata_digest, guidance_dir=guidance_dir,
            resolver=args.resolver,
        )
    # The evidence store is append-only, so a citation dropped from the text
    # keeps its records. The bibliography follows the text: only cited keys
    # are written, each still required to carry sourced, ingested evidence.
    tex_path = paper_block.resolve_main_tex(paper_dir)
    tex_bytes = tex_path.read_bytes()
    cited = paper_bib.cited_keys(tex_bytes)
    records = [r for r in paper_evidence.read_all_records(paper_dir) if r.get("cite_key") in cited]
    result = paper_bib.build_refs_bib(paper_dir, records, guidance_dir=guidance_dir)
    reciprocal = paper_bib.check_reciprocal(
        tex_bytes, (paper_dir / "refs.bib").read_bytes(),
    )
    return {**result, "reciprocal": reciprocal}


def _round_for_new_record(existing_records: list[dict]) -> int:
    return max((record.get("round", 0) for record in existing_records), default=0) + 1


def _guard_source_md_classification(source_md: Path, guidance_dir: Path) -> None:
    """`the-skill-stops-trusting-memory`, item 2/3: `guidance/`'s per-folder
    classification (`paper_guidance.CLASSES`) is enforced here for the
    first time -- `plan` only ever echoed it back before this.

    Refuses `SOURCE_STYLE_REFERENCE` (work-state) when `source_md` resolves
    inside a folder the registry classes `style-reference`: that class
    feeds STYLE only, never content, and a quote lifted from one is not
    evidence no matter how well it locates (`style-channel` spec). Refuses
    `SOURCE_NOT_EVIDENCE` (work-state) when `source_md` resolves inside a
    guidance folder classed anything else (`unclassified`, or a future
    class outside `{"style-reference", "evidence"}`) -- `evidence` is the
    one class this gate accepts, its own real consequence rather than a
    label with nothing wired to it. A `source_md` that does not resolve
    under `guidance_dir` at all (`classify_source_md` returns `None`) is
    outside this gate's business and is never refused here.
    """
    source_class = paper_guidance.classify_source_md(source_md, guidance_dir)
    if source_class is None:
        return
    if source_class == "style-reference":
        raise Refused(
            "SOURCE_STYLE_REFERENCE",
            f"{source_md} resolves inside a guidance folder classed 'style-reference'; "
            "style-reference feeds style only, never a quote submitted as evidence",
        )
    if source_class != "evidence":
        raise Refused(
            "SOURCE_NOT_EVIDENCE",
            f"{source_md} resolves inside a guidance folder classed {source_class!r}, "
            "not 'evidence'; classify the folder before quoting it as evidence",
        )


def _build_evidence_record(
    args: argparse.Namespace, round_number: int, guidance_dir: Path,
) -> paper_evidence.EvidenceRecord:
    if args.quote and args.source_md:
        source_md_path = Path(args.source_md)
        _guard_source_md_classification(source_md_path, guidance_dir)
        span = paper_evidence.EvidenceSpan.locate(source_md_path, args.quote)
        if args.verdict == "holds":
            verdict = paper_evidence.Verdict.holds(span)
        elif args.verdict == "does-not-hold":
            verdict = paper_evidence.Verdict.does_not_hold(span)
        else:
            raise Refused(
                "VALIDATE_VERDICT_REQUIRED",
                "a located --quote/--source-md requires --verdict holds|does-not-hold",
            )
    else:
        verdict = paper_evidence.Verdict.insufficient(args.reason or "no --quote/--source-md given")
    return paper_evidence.EvidenceRecord.from_verdict(
        block_id=args.block, regime=_resolve_regime(args, "none"), claim=args.claim,
        cite_key=args.cite_key or "", identifier=args.identifier or "",
        resolver=args.resolver or "", metadata_digest=args.metadata_digest or "",
        verdict=verdict, round=round_number,
    )


def _resolve_regime(args: argparse.Namespace, fallback: str | None) -> str | None:
    """`--regime` wins when given explicitly; otherwise, when `--section-md`
    names an already-headered `sections/*.md` fixture, the regime is READ
    from that file's own contract for `--block` (`paper_validate.
    read_citations_regime` — real caller, not only the unit tests that
    exercise it directly). `fallback` (a `--sentence` JSON's own embedded
    `"regime"`, if any) is used only when neither of the above is given.
    """
    if args.regime:
        return args.regime
    if args.section_md:
        return paper_validate.read_citations_regime(Path(args.section_md), args.block)
    return fallback


def cmd_validate(args: argparse.Namespace) -> dict:
    paper_dir = paper_scaffold.resolve_paper_dir(args.paper)

    if args.sentence:
        sentence_obj = json.loads(Path(args.sentence).read_text(encoding="utf-8"))
        citations = tuple(
            paper_validate.Citation(
                text=entry["text"], position=entry["position"],
                attached_to_object=bool(entry.get("attached_to_object", False)),
                is_noun_phrase=bool(entry.get("is_noun_phrase", False)),
            )
            for entry in sentence_obj.get("citations", [])
        )
        sentence = paper_validate.Sentence(text=sentence_obj["text"], citations=citations)
        regime = _resolve_regime(args, sentence_obj.get("regime"))
        paper_validate.validate_placement(regime, sentence)

    if args.claim:
        existing = paper_evidence.read_records(paper_dir, args.block)
        round_number = args.round if args.round is not None else _round_for_new_record(existing)
        guidance_dir = paper_guidance.resolve_guidance_dir(args.guidance)
        record = _build_evidence_record(args, round_number, guidance_dir)
        paper_evidence.append_record(paper_dir, record, guidance_dir=guidance_dir)

    records = paper_evidence.read_records(paper_dir, args.block)
    claims = sorted({record["claim"] for record in records})
    body = None
    if args.body is not None:
        body = sys.stdin.buffer.read() if args.body == "-" else Path(args.body).read_bytes()
    explicit_min_sources = getattr(args, "min_sources", None)
    min_sources = (
        explicit_min_sources if explicit_min_sources is not None
        else paper_validate.DEFAULT_MIN_SOURCES_PER_CLAIM
    )
    return paper_validate.finalize_block(
        paper_dir, args.block, claims, records, body, min_sources=min_sources,
    )


def _compute_provenance_report(
    main_tex_bytes: bytes, status: dict, declarations_body: dict, corpus: "paper_graph.Corpus | None",
) -> list:
    """The `current`/`drifted`/`unprovenanced` per-block state, extracted
    from `compute_plan` (`the-phases-are-derived-not-remembered`, tasks.md
    6.9) so `phases` reads the SAME computation `plan` already proved end
    to end (`ReopenInvalidatesProvenanceEndToEndTests`), never a second one
    that could drift from it. Byte-identical to `compute_plan`'s own
    pre-extraction body; `corpus` is `None` exactly when `compute_plan`'s
    own `sections_dir` is omitted, preserving its two pre-existing callers
    that never built a section corpus.
    """
    provenance_record = paper_region.read_region(main_tex_bytes, "provenance")
    provenance_entries = (
        provenance_record["body"]["records"] if provenance_record is not None else []
    )

    # The generation, per block id, above which that block's own recorded
    # provenance generation is stale -- 0 (never stale) unless some record
    # this block's contract names was touched at a strictly later
    # generation. Computed once, up front, from every declarations record
    # in one pass over `affected_blocks`, rather than re-deriving the
    # corpus per block below.
    stale_since_generation: dict[str, int] = {}
    if corpus is not None:
        for declaration_entry in declarations_body["records"]:
            record_generation = declaration_entry.get("generation", 0)
            if record_generation <= 0:
                continue
            for affected_id in paper_declarations.affected_blocks(
                corpus, declaration_entry["id"]
            ):
                if record_generation > stale_since_generation.get(affected_id, 0):
                    stale_since_generation[affected_id] = record_generation

    report = []
    for block in status["blocks"]:
        block_id = block["id"]
        entry = next((e for e in provenance_entries if e["block"] == block_id), None)
        if entry is None:
            report.append({"block": block_id, "state": "unprovenanced"})
            continue
        digest_drifted = paper_provenance.drift(main_tex_bytes, block_id, Path(entry["contract"]))
        generation_drifted = stale_since_generation.get(block_id, 0) > entry.get("generation", 0)
        report.append({
            "block": block_id,
            "state": "drifted" if (digest_drifted or generation_drifted) else "current",
        })
    return report


def compute_plan(paper_dir: Path, *, guidance_dir: Path, sections_dir: Path | None = None) -> dict:
    """The pure aggregation `plan` reports: every `guidance/` folder's
    `{"class": ..., "declaration": ...}` (widened from a bare class string
    -- design.md Decision I; `declaration` is `paper_guidance.
    declaration_state`'s own `'undeclared'`|`'declared-unsealed'`|
    `'declared-sealed'` vocabulary, tasks.md 5.15 -- the SAME vocabulary
    `sourceRoots` uses below, never a second, 2-value spelling of the same
    concept); the whole `declarations` region body (fill and fixed state,
    per record); every written block's provenance state — `current`,
    `drifted`, or `unprovenanced`; and, since this unit, `sourceRoots`: one
    entry per distinct `paper_declarations.FACT_SOURCE_ROOT` root naming
    its `state`/`documents`/`reason` (`paper_declarations.
    source_root_status`) plus its `declaration` (`paper_declarations.
    declaration_state`) (design.md, `plan Aggregates Registry, Declarations,
    and Provenance`; `specs/source-declaration-authoring/spec.md`,
    `Requirement: The Position Report Names Every Declarable Root's And
    Every Guidance Folder's Declaration State`).

    Never writes — `read_registry`, `read_region` and `status` are all
    read-only, and `drift` only compares digests. Takes `paper_dir` and
    `guidance_dir` directly (not `--paper`/`--guidance` strings) so a test
    can inject both without going through argparse's own resolution, the
    same separation `paper_readiness.compute_readiness` already keeps from
    its own `cmd_readiness` wrapper.

    `sections_dir` (corrective batch, `the-paper-carries-its-own-decisions`
    verify FAIL, CRITICAL): reopening a fact/declaration a written block
    depends on used to leave `plan` reporting that block `current` forever
    — `paper_declarations.affected_blocks`, the pure function the spec's
    own "Reopening Invalidates Exactly the Blocks That Named It"
    requirement names as the reopen scan, had exactly one caller in the
    whole repository: its own isolated test. Optional and defaulted to
    `None` so the two pre-existing `PlanTests` that never built a section
    corpus keep passing unchanged; every real invocation (`cmd_plan` below)
    always resolves and passes one. When given, a block is ALSO reported
    `drifted` (never a new state name — `plan`'s three-state vocabulary is
    unchanged) when `affected_blocks(corpus, id)` names it for some
    declarations-region record whose own `generation` — bumped by both
    `declare` and `--reopen` — is newer than the generation this block's
    provenance was written against. This is a strict superset of "reopened
    since": a reopen-then-redeclare with a new value also invalidates a
    dependent block's provenance, correctly, since the block was written
    against a value that no longer holds; `plan` never rewrites `main.tex`
    or either region under any of this, unchanged from before.
    """
    # `guidance`'s own declaration state uses the IDENTICAL four-value
    # vocabulary `sourceRoots` uses below -- `paper_guidance.
    # declaration_state` (tasks.md 5.15), never a second, 2-value
    # "undeclared"/"declared" spelling of the same concept
    # (`specs/source-declaration-authoring/spec.md`, `Requirement: The
    # Position Report Names Every Declarable Root's And Every Guidance
    # Folder's Declaration State`).
    guidance_report = {
        folder: {
            "class": klass,
            "declaration": paper_guidance.declaration_state(guidance_dir / folder),
        }
        for folder, klass in paper_guidance.read_registry(guidance_dir).items()
    }

    tex_path = paper_block.resolve_main_tex(paper_dir)
    main_tex_bytes = tex_path.read_bytes()

    declarations_record = paper_region.read_region(main_tex_bytes, "declarations")
    declarations_body = (
        declarations_record["body"] if declarations_record is not None
        else {"generation": 0, "records": []}
    )

    status = paper_block.status(main_tex_bytes)
    corpus = paper_graph.assemble_corpus(sections_dir) if sections_dir is not None else None
    provenance_report = _compute_provenance_report(main_tex_bytes, status, declarations_body, corpus)

    # `specs/source-declaration-authoring/spec.md`, `Requirement: The
    # Position Report Names Every Declarable Root's And Every Guidance
    # Folder's Declaration State` (design.md Decision I): one entry per
    # DISTINCT root in `FACT_SOURCE_ROOT`, the same source base
    # `_binding_separation_report` already uses (`paper_dir.parent`), never
    # `sections_dir` -- `plan` should not need one for a fact about the
    # corpus. This corrects the archived predecessor's false-ticked
    # `tasks.md` item 2.14 ("echoed by every corpus-reading verb"),
    # measured false by running `plan`/`phases`/`contract` and finding none
    # of the three render `Corpus.source_roots` at all.
    source_base = paper_dir.parent
    source_roots_report = {}
    for root in sorted(set(paper_declarations.FACT_SOURCE_ROOT.values()), key=lambda r: r.name):
        root_status = paper_declarations.source_root_status(source_base, root)
        source_roots_report[root.name] = {
            "state": root_status["state"],
            "documents": root_status["documents"],
            "reason": root_status["reason"],
            "declaration": paper_declarations.declaration_state(root_status, root),
        }

    result = {
        "guidance": guidance_report,
        "declarations": declarations_body,
        "provenance": provenance_report,
        "sourceRoots": source_roots_report,
    }
    if corpus is not None:
        # item 1 (`no-citation-before-its-paper-is-ingested`): every
        # section-shaped guidance folder's own citation status, additive to
        # `guidance` above -- `corpus.sections` is the parsed corpus's own
        # set of section ids, never a hand-listed tuple.
        result["sectionGuidance"] = paper_guidance.section_citation_folders(
            guidance_dir, corpus.sections,
        )
    return result


def cmd_plan(args: argparse.Namespace) -> dict:
    paper_dir = paper_scaffold.resolve_paper_dir(args.paper)
    guidance_dir = paper_guidance.resolve_guidance_dir(args.guidance)
    sections_dir = paper_contract.resolve_sections_dir(args.sections)
    return compute_plan(paper_dir, guidance_dir=guidance_dir, sections_dir=sections_dir)


def _unwritten_required_blocks(corpus, wave: list, opened_blocks: set) -> list:
    """Non-optional blocks in `wave` that are not yet opened -- unit 3's
    absence semantics: an unopened `optional` block never blocks a wave
    (tasks.md 6b.2). Extracted out of `compute_phases`'s own gate loop
    (unit 6) so `cmd_write`'s write-path gate (unit 6b) shares the exact
    same definition of "written" rather than a second one that could
    drift from it.
    """
    return sorted(
        qualified_id for qualified_id in wave
        if not corpus.blocks[qualified_id].optional and qualified_id not in opened_blocks
    )


def _refuse_on_incomplete_waves(
    waves: list, corpus, opened_blocks: set, up_to_index: int, *, blocked_label: str,
) -> None:
    """Raises `PHASE_NOT_READY` naming the first still-incomplete wave
    among `waves[:up_to_index]` and its unwritten non-optional blocks.
    `blocked_label` names what is being gated -- a phase number for
    `compute_phases`'s own `--phase N`, a qualified block id for
    `cmd_write`'s write-path gate -- in the refusal detail. ONE gate
    computation (tasks.md 6b.1's own instruction: "do not write a second
    one"), two callers below.
    """
    for index, wave in enumerate(waves[:up_to_index]):
        unwritten = _unwritten_required_blocks(corpus, wave, opened_blocks)
        if unwritten:
            raise Refused(
                "PHASE_NOT_READY",
                f"wave {index + 1} is not complete ({unwritten} still unwritten); "
                f"{blocked_label} cannot proceed until every wave before it is complete",
            )


def _resolve_write_gate(paper_dir: Path, sections_dir: Path, qualified_id: str) -> "paper_graph.Corpus":
    """`cmd_write`'s own phase gate (tasks.md 6b.1-6b.2; `specs/writing-
    phases/spec.md`, `Requirement: Phase N Is Gated On Phase N-1`, whose
    own scenarios name `write` -- the verb unit 6 left unwired). Runs
    BEFORE any draft/audit file is opened, before `paper_write.write_
    block`'s own attempt ledger is touched, and before any byte reaches
    `main.tex` -- a block must never burn a judge-cycle attempt on a
    refusal that has nothing to do with its draft.

    Returns the `Corpus` it already assembles with `enforce_bindings=True`
    (design.md, Decision E; `transposition-fidelity` spec's own
    prerequisite plumbing). The archived predecessor that shipped this
    gate's own File Changes row already claimed it "returns the corpus so
    `cmd_write` reports it" -- the claim shipped, the return value did
    not, until this change: `cmd_write` needs this corpus back to resolve
    a block's own bound sections (`paper_source_span.resolve_bound_
    sections`), never a second, independent assembly of the same corpus.
    Returned on every path, including the early `return` below, since a
    `qualified_id` outside every wave is still a real block `cmd_write`'s
    own downstream lookup goes on to resolve.

    Resolves `qualified_id`'s own Kahn wave via `paper_graph.derive_
    waves` and calls `_refuse_on_incomplete_waves`, the SAME gate
    computation `compute_phases`'s own `--phase N` refusal uses -- so
    `phases` and `write` can never disagree about what "not ready" means
    (Unit 6's own Notes flagged exactly this drift; this closes it).

    A `qualified_id` the corpus's own waves do not contain (a typo'd
    `--section`/`--block`, or a block the section header does not
    declare) is left to `cmd_write`'s existing downstream lookup to
    refuse on its own terms -- this gate only ever narrows what CAN
    proceed, it never invents a refusal for a condition it was not asked
    to police.

    `enforce_bindings=True` (U3b correctness repair, design.md Decision
    H): this is the ONLY `assemble_corpus` call in the whole skill that
    passes it. Every read-only verb assembles the SAME corpus with the
    default `False` and reports an unbound bindable entry as
    `Corpus.undecided_bindings` rather than refusing -- drafting a block
    without knowing which section feeds it is the one moment an
    undecided binding must become `SECTION_BINDING_ABSENT` instead of a
    report, so only `write`'s own gate ever turns it into one.

    `enforce_for_block=qualified_id` (U4 correctness repair, design.md:
    "the block this `write` call names, nothing else"): scopes that
    refusal to the block THIS call is actually about to draft. A sibling
    block elsewhere in the corpus carrying its own undecided binding --
    optional, unopened, or simply not yet reached -- stays visible in
    `Corpus.undecided_bindings` but no longer blocks writing a block that
    never named it. `qualified_id` is already resolved above this
    function's own call site (`cmd_write`), so this thread-through adds
    no new resolution, only narrows which entry can raise.
    """
    corpus = paper_graph.assemble_corpus(
        sections_dir, paper_dir=paper_dir, enforce_bindings=True, enforce_for_block=qualified_id,
    )
    edge_set = paper_graph.collect_edges(corpus)
    waves = paper_graph.derive_waves(corpus, edge_set)

    wave_index = next((index for index, wave in enumerate(waves) if qualified_id in wave), None)
    if wave_index is None:
        return corpus

    tex_path = paper_block.resolve_main_tex(paper_dir)
    status = paper_block.status(tex_path.read_bytes())
    opened_blocks = {block["id"] for block in status["blocks"]}

    _refuse_on_incomplete_waves(
        waves, corpus, opened_blocks, wave_index,
        blocked_label=f"{qualified_id!r} (wave {wave_index + 1})",
    )
    return corpus


def _write_gate_state(corpus, guidance_dir: Path, qualified_id: str) -> dict:
    """What `write` would refuse for ONE block, computed WITHOUT refusing --
    the read-time half `the-requirement-names-the-section-that-feeds-it`'s
    design.md (section H) chose and only half-delivered.

    That decision table's chosen option reads: "Report an undecided binding
    at read-time (`Corpus.undecided_bindings`, mirroring `source_roots`'s
    own `unmeasured` report), refuse only when `write` assembles its own
    corpus". The refusing half shipped (`enforce_bindings=True`, the single
    `_resolve_write_gate` call site). The REPORTING half was built as a
    `Corpus` field and wired to no output at all: `source_roots`, the twin
    that sentence names, reaches the operator through `plan`'s own
    `sourceRoots`; `undecided_bindings` reached nothing. This is the wire.

    Both halves REUSE the gates `write` itself runs -- never a second
    implementation that could drift from them. The binding half reads the
    same `corpus.undecided_bindings` `_verify_source_section_bindings`
    raises from; the citation half reads the same
    `paper_guidance.section_citation_status` `_guard_section_citations_
    ready` raises from, and applies the same `regime == "none"` exemption.

    Reports, never raises: a block whose gates are all clear is
    `{"state": "clear", "blockers": []}`; otherwise `{"state": "blocked",
    "blockers": [{"code": ..., "detail": ...}, ...]}` naming EVERY blocker
    found, not merely the first. `write` itself still raises one refusal
    per call, in its own fixed order -- this report is what lets an
    operator see all of them before spending a redactor and a
    contract-auditor run on a block `write` will refuse.
    """
    blockers: list = []

    facts = corpus.undecided_bindings.get(qualified_id) or {}
    for fact_id in sorted(facts):
        info = facts[fact_id]
        blockers.append({
            "code": "SECTION_BINDING_ABSENT",
            "detail": f"{fact_id!r} is bindable and its source root "
                      f"{info['root']!r} is measured, but carries no binding",
        })

    record = corpus.blocks.get(qualified_id)
    # The SAME literal `_guard_section_citations_ready` tests (`regime ==
    # "none"`); `paper_vocabulary` exposes the regime TUPLE, never a
    # per-regime constant, so matching the sibling gate verbatim is what
    # keeps the two from drifting.
    if record is not None and record.citations != "none":
        status = paper_guidance.section_citation_status(guidance_dir, record.section)
        if not status["exists"]:
            blockers.append({
                "code": "CITATION_FOLDER_ABSENT",
                "detail": f"guidance/{record.section}/ does not exist yet",
            })
        elif status["pending_pdfs"]:
            blockers.append({
                "code": "CITATION_NOT_INGESTED",
                "detail": f"guidance/{record.section}/ still holds un-ingested "
                          f"PDF(s) {status['pending_pdfs']}",
            })
        elif status["classification"] == "unclassified":
            blockers.append({
                "code": "CITATION_FOLDER_UNCLASSIFIED",
                "detail": f"guidance/{record.section}/ carries no "
                          ".paper-writing.json marker",
            })

    return {"state": "blocked" if blockers else "clear", "blockers": blockers}


def compute_phases(
    paper_dir: Path, sections_dir: Path, *, phase: int | None = None,
    guidance_dir: Path | None = None,
) -> dict:
    """`phases`: the read-only "what can I write now" report `readiness`
    alone never answered -- `compute_readiness` had exactly one caller
    (`cmd_readiness`) before this unit (design.md D3). Takes `paper_dir`/
    `sections_dir` directly, the same separation `compute_plan` keeps from
    `cmd_plan`.

    Waves come from `paper_graph.derive_waves`; per-block readiness from
    `paper_readiness.compute_readiness` under basis `"declaration-backed"`;
    `opened` from `paper_block.status`; provenance state from the SAME
    computation `plan` already proved end to end
    (`_compute_provenance_report`, extracted from `compute_plan` this unit
    -- never a second one that could drift from it). The top-level
    `"declared"` key echoes exactly the two sets `paper_declarations.read_
    satisfied` returned -- direct, auditable proof that a `declare` write
    is seen, never inferred only from a block's own `missing_facts`
    shrinking.

    Open Question 2 (design.md), resolved here: an `unprovenanced` block
    still counts as WRITTEN for the wave gate below -- the gate reads
    `opened` (bare `main.tex` block presence) alone, never provenance
    state. Provenance currency (`drifted`/`unprovenanced`) is attached per
    block purely for the operator's own visibility and stays `plan`'s
    separately-reported concern; conflating it with wave-gating would
    block writing on a documentation gap, not a missing dependency
    (tasks.md 6.2).

    `phase` given -> refuses `PHASE_NOT_READY`, before any output is built,
    naming the first still-incomplete wave among waves `1..phase-1` and its
    unwritten non-optional blocks (via the shared `_refuse_on_incomplete_
    waves`, unit 6b: `cmd_write`'s own write-path gate below calls the
    identical function, so this read-only report and the real write path
    can never disagree about what "not ready" means); only waves `1..phase`
    are then reported. `phase` omitted -> every wave is reported -- the
    full plan the operator approves once, before writing starts
    (`specs/writing-phases/spec.md`, `Requirement: The Operator Approves
    The Phase Plan Before Writing Starts`; unit 9 wires this report into
    `SKILL.md`'s own approval prose).
    """
    corpus = paper_graph.assemble_corpus(sections_dir, paper_dir=paper_dir)
    edge_set = paper_graph.collect_edges(corpus)
    waves = paper_graph.derive_waves(corpus, edge_set)
    if guidance_dir is None:
        guidance_dir = paper_guidance.resolve_guidance_dir(None)

    tex_path = paper_block.resolve_main_tex(paper_dir)
    main_tex_bytes = tex_path.read_bytes()
    status = paper_block.status(main_tex_bytes)
    opened_blocks = {block["id"] for block in status["blocks"]}

    declarations_record = paper_region.read_region(main_tex_bytes, "declarations")
    declarations_body = (
        declarations_record["body"] if declarations_record is not None
        else {"generation": 0, "records": []}
    )
    provenance_report = _compute_provenance_report(main_tex_bytes, status, declarations_body, corpus)
    provenance_by_block = {entry["block"]: entry["state"] for entry in provenance_report}

    declared_facts, declared_declarations = paper_declarations.read_satisfied(paper_dir)
    declined_facts = paper_declarations.read_declined(paper_dir)
    produced_by = paper_graph.producers_by_fact(corpus)
    produced_satisfied = _produced_satisfied_facts(produced_by, opened_blocks)
    satisfied_facts = (declared_facts - set(produced_by)) | produced_satisfied
    readiness_report = paper_readiness.compute_readiness(
        corpus, satisfied_facts=satisfied_facts, satisfied_declarations=declared_declarations,
        opened_blocks=opened_blocks, basis="declaration-backed", declined_facts=declined_facts,
        produced_by=produced_by,
    )
    readiness_by_block = {entry["block"]: entry for entry in readiness_report}

    if phase is not None:
        _refuse_on_incomplete_waves(
            waves, corpus, opened_blocks, phase - 1, blocked_label=f"phase {phase}",
        )

    selected_waves = waves if phase is None else waves[:phase]

    wave_reports = []
    previous_complete = True
    for index, wave in enumerate(selected_waves):
        wave_complete = not _unwritten_required_blocks(corpus, wave, opened_blocks)
        if not previous_complete:
            wave_status = "gated"
        elif wave_complete:
            wave_status = "complete"
        else:
            wave_status = "open"
        wave_reports.append({
            "wave": index + 1,
            "status": wave_status,
            "blocks": [
                {
                    "block": qualified_id,
                    "status": readiness_by_block[qualified_id]["status"],
                    "missing_facts": readiness_by_block[qualified_id]["missing_facts"],
                    "missing_declarations": readiness_by_block[qualified_id]["missing_declarations"],
                    "declined_facts": readiness_by_block[qualified_id].get("declined_facts", []),
                    "stale_declines": readiness_by_block[qualified_id].get("stale_declines", []),
                    "blocked_on_produced": readiness_by_block[qualified_id].get(
                        "blocked_on_produced", []
                    ),
                    "optional": readiness_by_block[qualified_id]["optional"],
                    "opened": qualified_id in opened_blocks,
                    "provenance": provenance_by_block.get(qualified_id),
                    "write_gates": _write_gate_state(corpus, guidance_dir, qualified_id),
                }
                for qualified_id in wave
            ],
        })
        previous_complete = previous_complete and wave_complete

    return {
        "declared": {
            "facts": sorted(declared_facts),
            "declarations": sorted(declared_declarations),
        },
        "waves": wave_reports,
    }


def cmd_phases(args: argparse.Namespace) -> dict:
    paper_dir = paper_scaffold.resolve_paper_dir(args.paper)
    sections_dir = paper_contract.resolve_sections_dir(args.sections)
    guidance_dir = paper_guidance.resolve_guidance_dir(args.guidance)
    return compute_phases(
        paper_dir, sections_dir, phase=args.phase, guidance_dir=guidance_dir,
    )


def _resolve_repo_path(raw: str) -> Path:
    """Resolves a caller-supplied `--draft`/`--audit`/`--transcript` operand
    against the real repository root, reusing `paper_scaffold.FORGE_ROOT`
    containment and its `PAPER_OUTSIDE_REPOSITORY` refusal (`design.md`,
    Threat Matrix: Path containment) — never a second, freshly-invented code
    for the same condition."""
    root = paper_scaffold.FORGE_ROOT.resolve()
    target = Path(raw).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise Refused(
            "PAPER_OUTSIDE_REPOSITORY", f"{target} does not resolve inside the repository root {root}"
        )
    return target


def _declared_block(header, section: str, block_id: str) -> dict:
    """One block of a parsed header, by id -- or `BLOCK_UNDECLARED`.

    All three verbs that resolve a single `(section, block)` pair --
    `packet`, `write` and `place` -- reached for it with a bare
    `next(b for b in header.blocks if b["id"] == args.block)`, which raises
    `StopIteration` for an id the header does not declare. That is a crash,
    not this skill's refusal envelope, and it is invisible to the refusal
    roster besides: the roster is a static scan for literal codes, and a
    `StopIteration` carries none.

    One helper rather than three copies, for the reason the three copies
    themselves demonstrate: the identical defect sat in all of them, and
    repairing one would have left the class open.

    Names the ids the section DOES declare, so a typo is answerable from
    the refusal without opening the contract.
    """
    for block in header.blocks:
        if block["id"] == block_id:
            return block
    raise Refused(
        "BLOCK_UNDECLARED",
        f"section {section!r} declares no block {block_id!r}; "
        f"declared blocks are {[b['id'] for b in header.blocks]}",
    )


def _resolve_packet_source_sections(
    sections_dir: Path, header, block: dict, qualified_id: str, *, corpus, paper_dir,
) -> tuple:
    """`the-redactor-receives-the-section-it-must-transpose`, design.md
    D1/D2/D5: the block's own bound source sections, plus the sibling
    `source_sections_state` naming which of the closed four-value
    vocabulary applies (`resolved`, `unbound`, `unmeasured`, `not-
    applicable`). Mode is resolved from the header `assemble_packet`
    already parsed -- no extra disk read. Never assembles a corpus it was
    handed (`corpus is not None` skips assembly entirely); never derives a
    paper root it was not given (`paper_dir is None` skips assembly
    entirely too, rather than letting `paper_graph.assemble_corpus`
    silently derive `sections_dir.parent / "paper"` on this function's
    behalf).
    """
    mode_obj = paper_contract.resolve_mode(header, block)
    mode = mode_obj["value"] if mode_obj is not None else None
    header_triples = paper_contract.requirement_documents(block["requires_facts"])

    if mode is None:
        return (), {
            "state": "unmeasured",
            "reason": (
                f"{qualified_id}: no mode resolves at section or block level; declare one "
                "before its bound sections can be resolved"
            ),
            "unresolved": [
                {"fact": fact, "lineage": lineage, "title": title}
                for fact, lineage, title in header_triples
            ],
        }
    if mode != paper_vocabulary.MODE_TRANSPOSITION:
        return (), {
            "state": "not-applicable",
            "reason": (
                f"{qualified_id}: mode is {mode!r}, not {paper_vocabulary.MODE_TRANSPOSITION!r}; "
                "source sections are only resolved for a transposition-mode block"
            ),
            "unresolved": [],
        }

    if corpus is None:
        # Corpus-wide refusal contamination on `packet` is accepted, see
        # `design.md` D2 and `redactor-packet` spec scenario "An unrelated
        # section's defect blocks a transposition block's packet" -- the
        # tests, not this comment, are the enforcement.
        if paper_dir is None:
            if not header_triples:
                return (), {
                    "state": "unbound",
                    "reason": f"{qualified_id}: names no (fact, lineage, title) binding at all; nothing to resolve",
                    "unresolved": [],
                }
            return (), {
                "state": "unmeasured",
                "reason": (
                    f"{qualified_id}: no paper root supplied; pass --paper <dir> (or "
                    "ensure paper/main.tex is reachable) so its bound sections can be "
                    "resolved"
                ),
                "unresolved": [
                    {"fact": fact, "lineage": lineage, "title": title}
                    for fact, lineage, title in header_triples
                ],
            }
        corpus = paper_graph.assemble_corpus(sections_dir, paper_dir=paper_dir)

    record = corpus.blocks[qualified_id]
    declared_triples = record.source_bindings
    if not declared_triples:
        return (), {
            "state": "unbound",
            "reason": f"{qualified_id}: names no (fact, lineage, title) binding at all; nothing to resolve",
            "unresolved": [],
        }

    resolved_sections = paper_source_span.resolve_bound_sections(corpus, qualified_id)
    resolved_keys = {(entry["fact"], entry["lineage"], entry["title"]) for entry in resolved_sections}
    unresolved = [
        {"fact": fact, "lineage": lineage, "title": title}
        for fact, lineage, title in declared_triples
        if (fact, lineage, title) not in resolved_keys
    ]
    if unresolved:
        return resolved_sections, {
            "state": "unmeasured",
            "reason": (
                f"{qualified_id}: {len(unresolved)} bound-section triple(s) did not resolve -- "
                "run 'bind', populate the source root, or check the title -- see 'unresolved'"
            ),
            "unresolved": unresolved,
        }
    return resolved_sections, {"state": "resolved", "reason": None, "unresolved": []}


def assemble_packet(
    sections_dir: Path, guidance_dir: Path, section: str, block_id: str,
    *, corpus=None, paper_dir: Path | None = None,
) -> dict:
    """The redactor packet (`redactor-packet` spec; design.md Decision D5):
    one block's own section contract prose, verbatim, plus -- per `style-
    reference`-classed `guidance/` root -- every ingested paper's heading
    OUTLINE (`paper_guidance.read_markdown_outline`: `{title, level,
    byte_start, byte_end}`, never the span text itself); plus, for a
    `transposition`-mode block only, the block's own bound source
    sections (`the-redactor-receives-the-section-it-must-transpose`,
    design.md D1/D2/D4/D5). Read-only: never opens a reference `.md` for
    anything beyond computing its own outline, and never writes anything
    under any input, including every refusal path (tasks.md 8.14).

    This is the structural half of the leak guard the operator raised
    twice: the packet is physically incapable of carrying reference
    prose, because outlines are all it ever carries (design.md: "Rejected
    alternative -- the packet inlines each extracted section's text --
    puts an unaudited copy of reference prose in a file the redactor can
    read without ever passing residency verification or the eight-token
    tripwire"). The style-sampler agent reads this outline, picks the
    heading it judges equivalent, reads THAT span itself from the real
    file, and reports it; `paper_style.resolve_style_set` residency-
    verifies that account into `R` exactly as before -- this function
    never resolves a span and never calls `resolve_style_set` itself, so
    there is exactly one resolution path, not a second one this function
    could drift from (tasks.md 8.9).

    A `style-reference` root with no ingested papers under it (`paper_
    guidance.ingested_papers`), and a root the registry classes anything
    other than `style-reference`, both contribute nothing to `references`
    -- never a refusal (`redactor-packet` spec, `Scenario: A reference
    with no equivalent block contributes nothing` is the sampler's own
    later degrade; this is the same "contributes nothing, never refuses"
    shape one step earlier, over roots rather than resolved spans).

    Returns, additionally (`the-redactor-receives-the-section-it-must-
    transpose`, design.md Interfaces):
        "source_sections": [ {fact, lineage, title, path,
                              byte_start, byte_end, text}, ... ]
        "source_sections_state": {
            "state": "resolved" | "unbound" | "unmeasured" | "not-applicable",
            "reason": str | None,
            "unresolved": [ {fact, lineage, title}, ... ],
        }
    Never assembles a corpus it was handed; never derives a paper root it
    was not given.
    """
    # The header's own `section` field is what names a section, never the
    # filename (`paper_contract.resolve_section_path`). Composing
    # `sections_dir / f"{section}.md"` here opened none of the shipped
    # contracts -- all ten are `NN-<section>.md` -- so this verb died with a
    # traceback and exit 1 on every real block instead of refusing.
    section_path = paper_contract.resolve_section_path(sections_dir, section)
    header, body = paper_contract.parse(section_path.read_bytes())
    block = _declared_block(header, section, block_id)
    qualified_id = f"{section}.{block_id}"

    registry = paper_guidance.read_registry(guidance_dir)
    style_roots = sorted(name for name, cls in registry.items() if cls == "style-reference")
    ingested = paper_guidance.ingested_papers(guidance_dir)

    references = []
    for root in style_roots:
        for paper in ingested.get(root, []):
            outline = paper_guidance.read_markdown_outline(Path(paper["markdown"]))
            references.append({
                "root": root,
                "folder": paper["folder"],
                "markdown": paper["markdown"],
                **outline,
            })

    source_sections, source_sections_state = _resolve_packet_source_sections(
        sections_dir, header, block, qualified_id, corpus=corpus, paper_dir=paper_dir,
    )

    return {
        "block": block_id,
        "section": section,
        "contract": body.decode("utf-8"),
        "references": references,
        "source_sections": source_sections,
        "source_sections_state": source_sections_state,
    }


def cmd_packet(args: argparse.Namespace) -> dict:
    """`packet`: the CLI's own front door onto `assemble_packet` (tasks.md
    8.6) -- read-only, so an operator/orchestrator session can shuttle a
    block's contract prose plus every reference paper's heading outline
    to the redactor and style-sampler agents by hand without risking
    dropping one of the channels ("Why this verb exists at all": no
    script in this skill may import `subprocess`, so the skill can never
    invoke either agent itself). `--paper` (`the-redactor-receives-the-
    section-it-must-transpose`, design.md D1 category C) resolves through
    the SAME `paper_scaffold.resolve_paper_dir` boundary `write`/`place`
    already enforce, so a transposition-mode block's own bound sections
    can be resolved against a real paper root -- the one refusal `packet`
    newly reaches on every invocation, `PAPER_OUTSIDE_REPOSITORY`, is an
    invocation defect, never a state of the world (D1)."""
    sections_dir = paper_contract.resolve_sections_dir(args.sections)
    guidance_dir = paper_guidance.resolve_guidance_dir(args.guidance)
    paper_dir = paper_scaffold.resolve_paper_dir(args.paper)
    return assemble_packet(sections_dir, guidance_dir, args.section, args.block, paper_dir=paper_dir)


def _guard_section_citations_ready(guidance_dir: Path, section_id: str, regime: str) -> None:
    """`no-citation-before-its-paper-is-ingested`, item 3: `write` refuses
    while a citing block's own section citation folder
    (`guidance/<section-id>/`) is not fully ready -- downloaded, ingested,
    and classified (`paper_guidance.section_citation_status`). A `none`-
    regime block cites nothing and is never gated here
    (`paper_vocabulary.CITATIONS_REGIMES`; a `none`-regime block has no
    citations to gate no matter what `guidance/<section-id>/` looks like).

    Checked in this fixed order, one refusal per call -- the same shape
    `_guard_source_md_classification` already uses for `validate
    --source-md`: the folder must exist at all (`CITATION_FOLDER_ABSENT`);
    every PDF already placed in it must be ingested
    (`CITATION_NOT_INGESTED`, naming every pending PDF by name); and the
    folder itself must carry a real classification
    (`CITATION_FOLDER_UNCLASSIFIED`) -- `plan`'s own `guidance`/
    `sectionGuidance` registries enforced here as a real gate on `write`'s
    own citing path for the first time, rather than a label nothing
    consequences until `validate --source-md` sees one real quote.
    """
    if regime == "none":
        return
    status = paper_guidance.section_citation_status(guidance_dir, section_id)
    if not status["exists"]:
        raise Refused(
            "CITATION_FOLDER_ABSENT",
            f"guidance/{section_id}/ does not exist yet; download this section's cited PDFs there "
            f"so the paper-ingestion skill can turn them into evidence before {section_id} is drafted",
        )
    if status["pending_pdfs"]:
        raise Refused(
            "CITATION_NOT_INGESTED",
            f"guidance/{section_id}/ still holds un-ingested PDF(s) {status['pending_pdfs']}; "
            "run the paper-ingestion skill over this folder before writing a citing block",
        )
    if status["classification"] == "unclassified":
        raise Refused(
            "CITATION_FOLDER_UNCLASSIFIED",
            f"guidance/{section_id}/ carries no .paper-writing.json marker; classify it "
            '(e.g. {"class": "evidence"}) before writing a citing block',
        )


MAX_ENVELOPE_BYTES = 10 * 1024 * 1024  # 10 MB


def _strip_markdown_fences(text: str) -> str:
    """Normalize model output that wrapped JSON in markdown code fences."""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 2 and lines[-1].strip() == "```":
            return "\n".join(lines[1:-1]).strip()
    return stripped


def _load_draft_envelope(draft_path: Path) -> dict:
    """Validate draft envelope before indexing fields (Issue #71)."""
    try:
        if draft_path.stat().st_size > MAX_ENVELOPE_BYTES:
            raise Refused("DRAFT_UNREADABLE", f"{draft_path}: exceeds maximum envelope size")
        raw_text = draft_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise Refused("DRAFT_UNREADABLE", f"{draft_path}: {exc}")
    try:
        data = json.loads(_strip_markdown_fences(raw_text))
    except json.JSONDecodeError as exc:
        raise Refused("DRAFT_UNREADABLE", f"{draft_path}: invalid JSON: {exc.msg}")
    if not isinstance(data, dict):
        raise Refused("DRAFT_UNREADABLE", f"{draft_path}: must be a JSON object")
    if "latex" not in data or not isinstance(data["latex"], str):
        raise Refused("DRAFT_UNREADABLE", f"{draft_path}: missing or non-string 'latex'")
    if "bindings" not in data or not isinstance(data["bindings"], list):
        raise Refused("DRAFT_UNREADABLE", f"{draft_path}: missing or non-list 'bindings'")
    return data


def _load_audit_envelope(audit_path: Path) -> dict:
    """Validate audit account envelope before indexing fields (Issue #71)."""
    try:
        if audit_path.stat().st_size > MAX_ENVELOPE_BYTES:
            raise Refused("AUDIT_UNREADABLE", f"{audit_path}: exceeds maximum envelope size")
        raw_text = audit_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise Refused("AUDIT_UNREADABLE", f"{audit_path}: {exc}")
    try:
        data = json.loads(_strip_markdown_fences(raw_text))
    except json.JSONDecodeError as exc:
        raise Refused("AUDIT_UNREADABLE", f"{audit_path}: invalid JSON: {exc.msg}")
    if not isinstance(data, dict):
        raise Refused("AUDIT_UNREADABLE", f"{audit_path}: must be a JSON object")
    if "verdicts" not in data or not isinstance(data["verdicts"], list):
        raise Refused("AUDIT_UNREADABLE", f"{audit_path}: missing or non-list 'verdicts'")
    return data


def cmd_write(args: argparse.Namespace) -> dict:
    """`write`: reconciles an already-shuttled redactor draft and
    contract-auditor account against one block's real contract, evidence
    set and mode, and either substitutes the block or reports why not
    (`writing-orchestration` spec). Never drafts, never audits, never
    spawns anything (`design.md`, Decision D2) — `--draft`/`--audit` are
    JSON envelopes an agent already produced; `--transcript`, when given,
    is only containment-checked and recorded, never parsed for judgment.
    `--style`, when given, is the style-sampler's JSON account; it is
    residency-verified and recorded as `R` here, then the eight-token
    tripwire (`paper_leak.check_tripwire`) runs against the styled draft
    inside `write_block` before `substitute`, never only importable and
    unreachable (`style-leak-detection` spec, `Requirement: The
    Eight-Token Tripwire`).

    Before any of that -- before `--draft`/`--audit` are even read off
    disk -- `_resolve_write_gate` refuses `PHASE_NOT_READY` when this
    block's own wave has an earlier, still-incomplete wave (tasks.md
    6b.1-6b.5; `specs/writing-phases/spec.md`, `Requirement: Phase N Is
    Gated On Phase N-1`). Unit 6 wired this refusal onto the read-only
    `phases` verb alone; `cmd_write` never consulted `derive_waves`, so a
    later wave could be written before an earlier one existed. This gate
    closes that gap: it runs before `write_block`'s own attempt ledger is
    touched and before any byte reaches `main.tex`, so a block never
    burns a judge-cycle attempt on a refusal unrelated to its draft.

    Immediately after that gate -- still before `--draft`/`--audit` are
    read, and before `assemble_packet` even runs -- `_guard_section_
    citations_ready` refuses when this block's own section citation folder
    (`guidance/<section-id>/`) is not fully ready: downloaded, ingested,
    classified (`no-citation-before-its-paper-is-ingested`, item 3). A
    `none`-regime block cites nothing and is never gated by this.

    Then `assemble_packet` runs for this exact block (`writing-
    orchestration` spec, `Requirement: Packet Assembly Precedes Draft`).
    Its own return value is not otherwise consumed here (the redactor's
    draft and the style-sampler's account both already reached `write`
    through their own established channels, `--draft`/`--style`); running
    it is the gate: a `style-reference` root whose ingested markdown
    cannot be read refuses `GUIDANCE_MARKDOWN_UNREADABLE` here, before the
    draft/audit stage is ever reached, rather than surfacing only later
    and possibly after a judge-cycle attempt was already spent.
    """
    paper_dir = paper_scaffold.resolve_paper_dir(args.paper)
    sections_dir = paper_contract.resolve_sections_dir(args.sections)
    qualified_id = f"{args.section}.{args.block}"
    corpus = _resolve_write_gate(paper_dir, sections_dir, qualified_id)

    guidance_dir = paper_guidance.resolve_guidance_dir(args.guidance)

    section_path = paper_contract.resolve_section_path(sections_dir, args.section)
    header, body = paper_contract.parse(section_path.read_bytes())
    block = _declared_block(header, args.section, args.block)

    _guard_section_citations_ready(guidance_dir, header.section, block["citations"])

    # `the-redactor-receives-the-section-it-must-transpose`, design.md D2:
    # this corpus is already assembled above (`_resolve_write_gate`, with
    # `paper_dir` already resolved too) -- passed straight through so
    # `assemble_packet` never assembles a SECOND corpus against a
    # possibly-different derived root.
    assemble_packet(
        sections_dir, guidance_dir, args.section, args.block, corpus=corpus, paper_dir=paper_dir,
    )

    draft_path = _resolve_repo_path(args.draft)
    audit_path = _resolve_repo_path(args.audit)
    if args.transcript:
        _resolve_repo_path(args.transcript)

    draft = _load_draft_envelope(draft_path)
    audit_account = _load_audit_envelope(audit_path)

    # `the-block-asserts-only-what-its-section-carries`, design.md D7:
    # `--grounding` stays `default=None` -- requiring it would break every
    # `argument`-mode and non-transposition invocation. `grounding_account`
    # stays `None` when omitted; `GROUNDING_ACCOUNT_ABSENT` is `paper_
    # grounding`'s own to raise, never a flag check here.
    grounding_account = None
    if args.grounding:
        grounding_path = _resolve_repo_path(args.grounding)
        grounding_account = json.loads(grounding_path.read_text(encoding="utf-8"))

    mode_obj = paper_contract.resolve_mode(header, block)
    mode = mode_obj["value"] if mode_obj is not None else None

    evidence_set = ()
    if args.evidence:
        evidence_set = tuple(json.loads(Path(args.evidence).read_text(encoding="utf-8")))

    style_set = ()
    if args.style:
        proposals = json.loads(Path(args.style).read_text(encoding="utf-8"))
        recorded, _no_equivalent = paper_style.resolve_style_set(guidance_dir, proposals)
        style_set = tuple(recorded)

    contract = paper_write.BlockContract(
        # The id `skeleton`/`open` actually wrote into `main.tex` is the
        # QUALIFIED one (`<section>.<block>`, what `status` lists), and
        # `block_id` is what reaches `paper_block.substitute` at the end of
        # `write_block`. Passing `args.block` bare refused `BLOCK_ABSENT`
        # against every block of a real manuscript -- the gate above already
        # resolves `qualified_id`, so the substitution uses it too.
        block_id=qualified_id,
        contract_prose=body.decode("utf-8"),
        contract_source=str(section_path),
        citations_regime=block["citations"],
        mode=mode,
        requires_facts=paper_contract.requirement_values(block["requires_facts"]),
        evidence_set=evidence_set,
        style_set=style_set,
        source_sections=paper_source_span.resolve_bound_sections(corpus, qualified_id),
    )
    return paper_write.write_block(
        paper_dir, contract, draft, audit_account, grounding_account=grounding_account,
    )


def cmd_render(args: argparse.Namespace) -> dict:
    """`render`: compiles `paper/Figures/<id>.tex` standalone, exactly once
    per call (`authored-diagram` spec, `Requirement: Standalone Compile`).
    `--latexmk-path` is injectable ONLY for tests (`paper_latex.compile`'s
    own `path` kwarg); omitted, `shutil.which` searches the real `PATH`.

    `--acknowledge-reset` takes the OTHER branch entirely: the explicit
    operator acknowledgement that clears a spent ledger (`authored-diagram`
    spec, `Scenario: Acknowledgement clears the ledger`) — never combined
    with a compile in the same call, so a reset is always its own,
    unambiguous act.
    """
    paper_dir = paper_scaffold.resolve_paper_dir(args.paper)
    if args.acknowledge_reset:
        paths = paper_figure.figure_paths(paper_dir, args.figure_id)
        return paper_figure.acknowledge_reset(paths, args.figure_id)

    result = paper_figure.render(paper_dir, args.figure_id, path=args.latexmk_path)
    if args.section and args.block:
        result["obligations"] = _check_obligations(paper_dir, args)
    return result


def _resolve_expected_components(paper_dir: Path, sections_dir: Path, fact_id: str) -> list:
    """Derives the Components Check's expected list from `components_from`'s
    named fact — never an operator-supplied CLI flag (corrective amendment,
    `a-diagram-that-compiles-or-says-why`'s own verify FAIL:
    `--expected-components` let a wrong list be supplied for a block whose
    diagram was never that one fact's own list, silently inverting the
    check; removed rather than left reachable).

    `a-fact-is-declared-or-it-is-produced` (design.md, Decision A / `fact-
    production` spec, `Requirement: A Produced Fact's Value Is Its
    Producer's Own Rendered Text`): when `fact_id` resolves to one or more
    corpus producers (`paper_graph.producers_by_fact`), the expected list is
    read from the producer's OWN rendered `main.tex` body — never a second,
    separately-declared copy — through `paper_verify.item_lines`'s `\\item`
    extraction (the exact slice `paper_coupling_evidence.gather` already
    builds for `check_gap`; `check_contribution_list` and `paper_declarations
    .read_fact` are both bypassed for a produced fact). The deterministic
    first (lowest qualified id) producer is used when more than one exists
    — no live corpus consumer resolves a corroborated pair's value this way
    today (design.md: 'no live consumer resolves gap's text this way
    today'). When the corpus cannot even be assembled (`Refused`), this
    falls back to the pre-existing declared-fact route below — mirroring
    `paper_coupling_evidence._blocks_by_fact`'s own defensive fallback,
    since a minimal/synthetic `sections_dir` never declares a producer at
    all and must keep behaving exactly as it did before this fact had a
    produced-class route.

    For every other fact (or when no producer resolves), reads through
    `paper_declarations.read_fact` — the SAME `declarations` region
    `declare --fact` writes.

    Refuses `COMPONENTS_FACT_UNRESOLVED` (work-state) when the fact was
    never declared (or, for a produced fact, its producer is not yet
    written). Refuses `COMPONENTS_FACT_NOT_A_LIST` (work-state) when the
    resolved value does not parse as a JSON array of strings (declared
    route) or yields no `\\item` lines (produced route) — the resolved
    value for a fact a `figure:` object names via `components_from` MUST be
    exactly that list, in the order the diagram must show it when
    `ordered: true`.
    """
    try:
        corpus = paper_graph.assemble_corpus(sections_dir)
    except Refused:
        corpus = None
    producer_ids = paper_graph.producers_by_fact(corpus).get(fact_id, ()) if corpus is not None else ()
    if producer_ids:
        producer_id = sorted(producer_ids)[0]
        tex_path = paper_block.resolve_main_tex(paper_dir)
        main_tex_bytes = tex_path.read_bytes()
        parsed_blocks = paper_block.parse(main_tex_bytes)
        if producer_id not in parsed_blocks.pairs:
            raise Refused(
                "COMPONENTS_FACT_UNRESOLVED",
                f"figure.components_from names {fact_id!r}, produced by {producer_id!r}, "
                "which has not been written yet — open and substitute it first",
            )
        begin, end = parsed_blocks.pairs[producer_id]
        body = main_tex_bytes[begin["end"]:end["start"]]
        items = paper_verify.item_lines(body)
        if not items:
            raise Refused(
                "COMPONENTS_FACT_NOT_A_LIST",
                f"{fact_id!r}'s producer {producer_id!r} yields no \\item lines to resolve as a list",
            )
        return items

    resolution = paper_declarations.read_fact(paper_dir, fact_id)
    if resolution is None:
        raise Refused(
            "COMPONENTS_FACT_UNRESOLVED",
            f"figure.components_from names {fact_id!r}, which has not been declared — "
            f"run `declare --fact {fact_id} --value '[\"...\"]'` first",
        )
    try:
        parsed = json.loads(resolution)
    except json.JSONDecodeError as exc:
        raise Refused(
            "COMPONENTS_FACT_NOT_A_LIST",
            f"{fact_id!r}'s declared resolution is not valid JSON: {exc}",
        )
    if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
        raise Refused(
            "COMPONENTS_FACT_NOT_A_LIST",
            f"{fact_id!r}'s declared resolution must be a JSON array of strings, got {parsed!r}",
        )
    return parsed


def _check_obligations(paper_dir: Path, args: argparse.Namespace) -> dict:
    """Optional, real caller of `paper_obligation.py`'s checks — run only
    when `--section`/`--block` are given alongside `render`
    (`diagram-obligation` spec: obligations are read off the contract's own
    `figure:` declaration, never known).

    The Components Check runs ONLY when the block's `figure.components_from`
    names a fact — `_parse_figure` made this subkey optional precisely
    because it is a claim that one fact's own value IS the diagram's full
    expected component list, and that claim only holds when the diagram
    truly is one fact's own list by contract (section 01: the methods
    diagram's components are the contribution list). For a block whose
    diagram is a composite crossing over several categories of content
    (section 02's closing diagram: data, methods, axes, metrics,
    qualitative instruments, the repetition unit), no single fact is that
    list — such a block declares NO `components_from` at all, and no
    Components Check runs for it; `check_excluded`/`check_caption`/
    `check_mandatory`/separation still do.

    Also checks separation against every SIBLING `<other_id>.diagram.json`
    already under `paper/Figures/` — the cross-diagram intersection
    `check_shared_components` exists for, with no second CLI argument
    needed: every other diagram this figure could collide with is already
    on disk.
    """
    sections_dir = paper_contract.resolve_sections_dir(args.sections)
    section_path = paper_contract.resolve_section_path(sections_dir, args.section)
    header, _body = paper_contract.parse(section_path.read_bytes())
    block = _declared_block(header, args.section, args.block)
    figure = block["figure"]
    if figure is None:
        return {"checked": False, "reason": f"{args.block!r} declares no figure: obligation"}

    paths = paper_figure.figure_paths(paper_dir, args.figure_id)
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    manifest_components = manifest.get("components", [])

    if figure["components_from"] is not None:
        expected = _resolve_expected_components(paper_dir, sections_dir, figure["components_from"])
        paper_obligation.check_components(figure, manifest_components, expected)
    paper_obligation.check_excluded(figure, manifest_components)
    paper_obligation.check_caption(
        figure, manifest_components, manifest.get("encodings", []), manifest.get("caption", ""),
    )
    paper_obligation.check_mandatory(figure, paths["pdf"].is_file(), args.block, manifest_components)

    sibling_components = {args.figure_id: manifest_components}
    for sibling_manifest_path in sorted(paths["tex"].parent.glob("*.diagram.json")):
        sibling_id = sibling_manifest_path.name[: -len(".diagram.json")]
        if sibling_id == args.figure_id:
            continue
        sibling_manifest = json.loads(sibling_manifest_path.read_text(encoding="utf-8"))
        sibling_components[sibling_id] = sibling_manifest.get("components", [])
    paper_obligation.check_shared_components(sibling_components)

    return {"checked": True}


def _resolve_optional_block_ids(sections_dir: Path) -> frozenset:
    """The raw (unqualified) block ids `paper_verify.run` treats as
    `optional`, derived from the same corpus `cmd_verify` already reads
    through `paper_coupling_evidence.gather` (`paper_graph.assemble_corpus`)
    -- never a second, independently-maintained classification.

    `paper_verify.py` cannot resolve this itself: its own AST-enforced
    import allowlist (`tests/test_paper_writing.py`,
    `_PAPER_VERIFY_ALLOWED_IMPORTS = {"re"}`) forbids it from ever reading
    `sections_dir`, by design (`the-couplings-hold-or-they-do-not`'s own
    diskless-checks guarantee). Work Unit 3 built and proved
    `optional_block_ids` end to end but left this exact resolution
    unwired, naming `paper_cli.py`/`cmd_verify` as the one place that
    already holds `sections_dir` and calls `paper_verify.run` (tasks.md,
    Work Unit 9b) -- this is that resolution, one level up from the module
    that cannot perform it.

    An unreadable corpus resolves to an empty set: `gather`'s own
    `_blocks_by_fact` already reports `SECTION_CONTRACTS_UNREADABLE` for
    every fact in that case, so this helper never needs to raise a second
    time for the same condition -- an empty `optional_block_ids` changes no
    check's verdict beyond what `SECTION_CONTRACTS_UNREADABLE` already
    reports.
    """
    try:
        corpus = paper_graph.assemble_corpus(sections_dir)
    except Refused:
        return frozenset()
    return frozenset(record.block_id for record in corpus.blocks.values() if record.optional)


def cmd_couplings(args: argparse.Namespace) -> dict:
    """`couplings`: the producer `verify` never had
    (`the-skill-stops-trusting-memory`, item 4). Reads a JSON object from
    `--file <path|->`, validates its shape
    (`paper_couplings.validate_couplings_shape`), and writes it WHOLE and
    atomically to `paper/couplings.json` -- the same "rebuild, never
    append" shape `bib build` already uses for its own sibling untracked
    file.

    Refuses `COUPLINGS_INPUT_UNREADABLE` (invocation-defect) when `--file`
    cannot be read or does not parse as JSON. Refuses `COUPLINGS_RECORD_
    MALFORMED` (work-state) when it parses but does not carry the shape
    `verify`'s own checks read (`paper_couplings.validate_couplings_shape`)
    -- checked BEFORE a single byte is written, so a malformed record never
    reaches disk half-applied.
    """
    paper_dir = paper_scaffold.resolve_paper_dir(args.paper)
    if args.file == "-":
        raw = sys.stdin.read()
        source = "<stdin>"
    else:
        file_path = _resolve_repo_path(args.file)
        try:
            raw = file_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise Refused("COUPLINGS_INPUT_UNREADABLE", f"{file_path}: {exc}")
        source = str(file_path)
    try:
        record = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise Refused("COUPLINGS_INPUT_UNREADABLE", f"{source}: invalid JSON: {exc.msg}")
    return paper_couplings.write_couplings(paper_dir, record)


def cmd_verify(args: argparse.Namespace) -> dict:
    """`verify`: a pure, read-only report over the five cross-section
    couplings, citation integrity, and contract currency
    (`coupling-verification`/`citation-integrity`/`contract-currency`
    specs). Never writes a byte, under any input, including a refusal
    (`block-substitution` spec, `Requirement: verify Verb Is Registered
    And Read-Only`) -- `paper_coupling_evidence.gather` performs every
    disk read this needs; `paper_verify.run` is pure over the result.

    `optional_block_ids` (`_resolve_optional_block_ids`, tasks.md Work Unit
    9b) is resolved from the same `sections_dir` corpus and threaded
    through, so an unopened `optional: true` block excuses the couplings
    that depend on it alone as `unmeasured`/`OPTIONAL_BLOCK_ABSENT` rather
    than reporting a false `fail` or `BLOCK_NOT_DECLARED`.
    """
    paper_dir = paper_scaffold.resolve_paper_dir(args.paper)
    sections_dir = paper_contract.resolve_sections_dir(args.sections)
    evidence = paper_coupling_evidence.gather(paper_dir, sections_dir)
    optional_block_ids = _resolve_optional_block_ids(sections_dir)
    return paper_verify.run(evidence, optional_block_ids=optional_block_ids)


def cmd_reuse(args: argparse.Namespace) -> dict:
    """`reuse`: `SKILL.md` capability A, read-only. For `--block`'s own
    open claims, names which already-ingested, `evidence`-classed papers
    carry no verdict yet for each one -- what stops the operator
    re-downloading a paper already on disk (`paper_lifecycle.reuse_report`,
    which does every real read; this wrapper only resolves `--paper`/
    `--guidance` and threads `--min-sources` through, the same shape
    `cmd_validate` already uses for `min_sources`)."""
    paper_dir = paper_scaffold.resolve_paper_dir(args.paper)
    guidance_dir = paper_guidance.resolve_guidance_dir(args.guidance)
    min_sources = (
        args.min_sources if args.min_sources is not None
        else paper_validate.DEFAULT_MIN_SOURCES_PER_CLAIM
    )
    return paper_lifecycle.reuse_report(paper_dir, guidance_dir, args.block, min_sources=min_sources)


def cmd_exhaustion(args: argparse.Namespace) -> dict:
    """`exhaustion`: `SKILL.md` capability B, read-only and corpus-wide --
    never scoped to one section, since a paper ingested under any
    `evidence`-classed root is already citable from any block
    (`paper_lifecycle.exhaustion_report`). Lists the exhausted set and,
    for every other paper, the corpus-wide open claims it still carries no
    verdict for. Builds NO deletion of any kind -- the operator deletes by
    hand, per the operator's own 2026-09-19 ruling."""
    paper_dir = paper_scaffold.resolve_paper_dir(args.paper)
    guidance_dir = paper_guidance.resolve_guidance_dir(args.guidance)
    min_sources = (
        args.min_sources if args.min_sources is not None
        else paper_validate.DEFAULT_MIN_SOURCES_PER_CLAIM
    )
    return paper_lifecycle.exhaustion_report(paper_dir, guidance_dir, min_sources=min_sources)


def cmd_place(args: argparse.Namespace) -> dict:
    """`place`: places an already-measured figure's PDF — compiles nothing,
    requires provenance naming the run (`authored-diagram` spec,
    `Requirement: Data-Figure Boundary`)."""
    paper_dir = paper_scaffold.resolve_paper_dir(args.paper)
    return paper_figure.place_figure(
        paper_dir, args.figure_id, Path(args.pdf), Path(args.provenance),
    )


def cmd_figure(args: argparse.Namespace) -> dict:
    """`figure`: one nested namespace over the two halves of this skill's
    diagram capability — `optimize` (rewrite a source, compile-validated)
    and `audit` (compare a source against the prose that describes it).

    Nested the way `bib build` already is. `render`/`place` stay top-level:
    moving them would break every call site and every document that names
    them, for no gain.
    """
    if args.figure_command == "optimize":
        return _cmd_figure_optimize(args)
    return _cmd_figure_audit(args)


def _cmd_figure_optimize(args: argparse.Namespace) -> dict:
    """`--figure-id` is the guarded path: the manifest is read from this
    skill's own layout, so the always-run cross-check has something to check
    against. `--file` alone is a DRY RUN by construction — it has no
    manifest, so it prints the candidate and writes nothing. `--file` with
    `--in-place`/`--output` still runs stop A and the compile; it simply has
    no manifest to cross-check, which is a different fact from skipping it.
    """
    if args.file:
        if not args.in_place and not args.output:
            return paper_figure.render_optimized_text(
                Path(args.file), strip_comments=args.strip_comments,
            )
        return paper_figure.optimize_source(
            Path(args.file),
            output=Path(args.output) if args.output else None,
            strip_comments=args.strip_comments,
            compile_candidate=not args.no_compile,
            path=args.latexmk_path,
        )

    paper_dir = paper_scaffold.resolve_paper_dir(args.paper)
    return paper_figure.optimize_figure(
        paper_dir, args.figure_id,
        strip_comments=args.strip_comments,
        compile_candidate=not args.no_compile,
        output=Path(args.output) if args.output else None,
        path=args.latexmk_path,
    )


def _cmd_figure_audit(args: argparse.Namespace) -> dict:
    """`figure audit`: the findings are a verdict, never a refusal — a
    failing audit is a successful call (`status: ok`, `verdict: fail`), the
    same way `render` treats an ordinary repairable compile failure as the
    loop's ordinary cost. Only an unreadable invocation refuses, and it
    reuses `SECTION_UNKNOWN` (a `--section` stem), `SECTION_CONTRACTS_
    UNREADABLE`/`DIAGRAM_SOURCE_ABSENT` rather than inventing a code for a
    condition the repo already names.
    """
    sections_dir = paper_contract.resolve_sections_dir(args.sections)
    section_path = paper_contract.resolve_section_path(sections_dir, args.section)
    header, body = paper_contract.parse(section_path.read_bytes())

    paper_dir = None
    scratch_dir = None
    if args.figure_id:
        paper_dir = paper_scaffold.resolve_paper_dir(args.paper)
        paths = paper_figure.figure_paths(paper_dir, args.figure_id)
        tex_path, manifest_path, scratch_dir = paths["tex"], paths["manifest"], paths["scratch"]
    else:
        if not args.manifest:
            raise Refused("DIAGRAM_SOURCE_ABSENT", "--file requires --manifest")
        tex_path, manifest_path = Path(args.file), Path(args.manifest)

    if not tex_path.is_file() or not manifest_path.is_file():
        raise Refused(
            "DIAGRAM_SOURCE_ABSENT",
            f"{tex_path} and {manifest_path} must both exist to audit a figure",
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        # A manifest that cannot be read or parsed is the same refusal the
        # absent-pair check above already makes: DIAGRAM_SOURCE_ABSENT is
        # the code the repo already names for "this call cannot audit from
        # these sources", never a new code for a condition it already
        # names. The parallel gather in
        # `paper_coupling_evidence._figure_semantics` guards these same
        # reads with the same exception set.
        raise Refused(
            "DIAGRAM_SOURCE_ABSENT",
            f"{manifest_path} is not a readable diagram manifest",
        )

    contract_figure = None
    expected_components = None
    if args.block:
        block = next((entry for entry in header.blocks if entry["id"] == args.block), None)
        if block is None:
            raise Refused(
                "BLOCK_ABSENT", f"{args.block!r} is not a block of {args.section!r}",
            )
        contract_figure = block["figure"]
        if contract_figure is not None and contract_figure.get("components_from") is not None:
            # An unresolved fact is `unmeasured`, not a refusal: the audit's
            # own third value exists so "could not check" never reads as
            # "checked and clean".
            try:
                expected_components = _resolve_expected_components(
                    paper_dir or paper_scaffold.resolve_paper_dir(args.paper),
                    sections_dir,
                    contract_figure["components_from"],
                )
            except Refused:
                expected_components = None

    try:
        tex_text = tex_path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        # Same reuse as the manifest read above: an undecodable figure source
        # refuses with the code the repo already names for "this call cannot
        # audit from these sources".
        raise Refused(
            "DIAGRAM_SOURCE_ABSENT",
            f"{tex_path} is not a readable figure source",
        )

    visual = None
    if args.visual_report:
        # `_resolve_repo_path` (Decision 5, design.md): the same
        # containment guard `--draft`/`--audit`/`--transcript` already
        # reuse, never a second, freshly-invented code for the same
        # condition. An absent or unparseable report reuses `DIAGRAM_
        # SOURCE_ABSENT` -- the code this function already raises twice
        # above for "this call cannot audit from these sources" -- rather
        # than inventing a third code for a fourth unreadable source.
        visual_report_path = _resolve_repo_path(args.visual_report)
        try:
            visual = json.loads(visual_report_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            raise Refused(
                "DIAGRAM_SOURCE_ABSENT",
                f"{visual_report_path} is not a readable visual report",
            )

    report = paper_figure_audit.audit_semantics(
        tex=tex_text,
        manifest=manifest,
        section_text=body.decode("utf-8", errors="replace"),
        contract_figure=contract_figure,
        expected_components=expected_components,
        visual=visual,
    )
    report["figureId"] = args.figure_id or tex_path.stem
    report["evidence"]["section"] = f"{args.section}.md"
    if scratch_dir is not None:
        scratch_dir.mkdir(parents=True, exist_ok=True)
        (scratch_dir / "figure_audit.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8",
        )
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="paper_cli.py")
    sub = parser.add_subparsers(dest="command", required=True)

    p_scaffold = sub.add_parser("scaffold", help="create/re-enter paper/ idempotently")
    p_scaffold.add_argument(
        "--paper", default=None,
        help="override paper/ location; must resolve inside the repository root",
    )

    p_status = sub.add_parser("status", help="report the block table, read-only")
    p_status.add_argument(
        "--paper", default=None,
        help="override paper/ location; must resolve inside the repository root",
    )

    p_open = sub.add_parser("open", help="insert an empty block pair, never content")
    p_open.add_argument(
        "--paper", default=None,
        help="override paper/ location; must resolve inside the repository root",
    )
    p_open.add_argument("--block", required=True, help="block id to open")
    p_open.add_argument("--after", default=None, help="insert immediately after this block's end marker")
    p_open.add_argument("--at-end", action="store_true", help="insert at the end of the document")

    p_substitute = sub.add_parser("substitute", help="replace one block's body, or adopt a hand edit")
    p_substitute.add_argument(
        "--paper", default=None,
        help="override paper/ location; must resolve inside the repository root",
    )
    p_substitute.add_argument("--block", required=True, help="block id to substitute")
    p_substitute.add_argument("--body", default=None, help="path to the new body, or - for stdin")
    p_substitute.add_argument(
        "--adopt", action="store_true",
        help="accept the on-disk body as the new baseline; rewrites the digest, never the body",
    )
    p_substitute.add_argument(
        "--contract", default=None,
        help="record this substitution's provenance against this contract file's current digest",
    )

    p_contract = sub.add_parser(
        "contract", help="validate the section corpus, or show one file's parsed header",
    )
    p_contract.add_argument(
        "--sections", default=None,
        help="override sections/ location; must resolve inside the repository root",
    )
    p_contract.add_argument(
        "--file", default=None,
        help="show this one file's parsed header instead of validating the whole corpus",
    )

    p_readiness = sub.add_parser(
        "readiness", help="per-block writable/blocked given satisfied facts and declarations",
    )
    p_readiness.add_argument(
        "--paper", default=None,
        help="override paper/ location; must resolve inside the repository root -- reads the "
        "declarations region for its satisfied sets (basis \"declaration-backed\")",
    )
    p_readiness.add_argument(
        "--sections", default=None,
        help="override sections/ location; must resolve inside the repository root",
    )
    p_readiness.add_argument(
        "--fact", action="append", default=None,
        help="a satisfied fact id; repeatable -- a hypothetical addition when --paper is "
        "given, or the whole basis (\"supposed-only\") when it is not",
    )
    p_readiness.add_argument(
        "--declaration", action="append", default=None,
        help="a satisfied declaration id; repeatable, same basis rules as --fact",
    )

    p_phases = sub.add_parser(
        "phases",
        help="read-only: what can I write now -- waves with per-block readiness, opened, provenance",
    )
    p_phases.add_argument(
        "--paper", default=None,
        help="override paper/ location; must resolve inside the repository root",
    )
    p_phases.add_argument(
        "--sections", default=None,
        help="override sections/ location; must resolve inside the repository root",
    )
    p_phases.add_argument(
        "--guidance", default=None,
        help="override guidance/ location; must resolve inside the repository root",
    )
    p_phases.add_argument(
        "--phase", type=int, default=None,
        help="report only waves 1..N; refuses PHASE_NOT_READY if any wave before N is "
        "incomplete. Omitted: report every wave, the full plan awaiting approval",
    )

    p_skeleton = sub.add_parser(
        "skeleton",
        help="open every section/block id the two structural answers imply, empty, via open_block only",
    )
    p_skeleton.add_argument(
        "--paper", default=None,
        help="override paper/ location; must resolve inside the repository root",
    )
    p_skeleton.add_argument(
        "--sections", default=None,
        help="override sections/ location; must resolve inside the repository root",
    )
    p_skeleton.add_argument(
        "--related-work", default=None, choices=("yes", "no"),
        help="whether the manuscript carries a dedicated Related Work section; asked once",
    )
    p_skeleton.add_argument(
        "--dataset-in", default=None, choices=("materials", "experimental-setup"),
        help="where the dataset is described; asked once",
    )

    p_order = sub.add_parser("order", help="derive the writing order from the block graph")
    p_order.add_argument(
        "--sections", default=None,
        help="override sections/ location; must resolve inside the repository root",
    )

    p_declare = sub.add_parser(
        "declare",
        help="record a declaration or fact resolution, or reopen a fixed one",
    )
    p_declare.add_argument(
        "--paper", default=None,
        help="override paper/ location; must resolve inside the repository root",
    )
    p_declare.add_argument(
        "--sections", default=None,
        help="override sections/ location; must resolve inside the repository root -- "
             "resolves whether --fact/--decline names a produced fact",
    )
    p_declare.add_argument("--declaration", default=None, help="a declaration id to record")
    p_declare.add_argument("--fact", default=None, help="a fact id to record a resolution for")
    p_declare.add_argument("--reopen", default=None, help="an id to clear the fixed state of")
    p_declare.add_argument(
        "--value", default=None,
        help="the value (--declaration) or resolution (--fact) to record",
    )
    p_declare.add_argument(
        "--decline", default=None,
        help="a fact id to record as declined -- the operator has decided it does not enter the paper for now",
    )
    p_declare.add_argument(
        "--reason", default=None,
        help="mandatory with --decline: why this fact is declined",
    )
    p_declare.add_argument(
        "--condition", default=None,
        help=(
            "mandatory with --decline: a JSON object naming a disk condition the "
            "skill re-checks on every later read, e.g. "
            '\'{"type": "directory-empty-except", "path": "experiments", "ignore": [".gitkeep"]}\''
        ),
    )

    p_bind = sub.add_parser(
        "bind",
        help="record which section(s) of a source document feed one block's own bindable "
             "requirement, or reopen a previously recorded binding",
    )
    p_bind.add_argument(
        "--paper", default=None,
        help="override paper/ location; must resolve inside the repository root",
    )
    p_bind.add_argument(
        "--sections", default=None,
        help="override sections/ location; must resolve inside the repository root",
    )
    p_bind.add_argument(
        "--block", required=True,
        help="the qualified block id (<section>.<block>) the binding belongs to",
    )
    p_bind.add_argument("--fact", required=True, help="the bindable fact id this binding answers")
    p_bind.add_argument(
        "--lineage", default=None, help="the source document's lineage (required unless --reopen)",
    )
    p_bind.add_argument(
        "--section", action="append", default=None,
        help="a section title the named lineage's current revision must carry; repeatable for "
             "a binding fed by more than one section (required unless --reopen)",
    )
    p_bind.add_argument(
        "--reopen", action="store_true",
        help="clear this exact (--block, --fact) binding's fixed state instead of recording one",
    )

    p_mark = sub.add_parser(
        "mark",
        help="record a per-directory .paper-writing.json marker, validated against disk at "
             "write time -- the answer to SOURCE_REVISIONS_UNDECLARED and an unclassified "
             "guidance/ folder, by using the skill, never a hand edit",
    )
    mark_sub = p_mark.add_subparsers(dest="mark_command", required=True)
    p_mark_revisions = mark_sub.add_parser(
        "revisions",
        help="record <root>/.paper-writing.json's own revisions grammar, validated against "
             "the *.md files actually there right now",
    )
    p_mark_revisions.add_argument(
        "--paper", default=None,
        help="override paper/ location (its PARENT is the source base --root resolves "
             "under, the same derivation compute_plan's own sourceRoots uses); must resolve "
             "inside the repository root",
    )
    p_mark_revisions.add_argument(
        "--root", required=True,
        help="a PROSE-kind key of FACT_SOURCE_ROOT to declare -- derived, never a literal list",
    )
    p_mark_revisions.add_argument(
        "--revision-prefix", required=True, dest="revision_prefix",
        help="the revision ordinal's own literal prefix, e.g. 'r'",
    )
    p_mark_revisions.add_argument(
        "--ordinal-digits", required=True, type=int, dest="ordinal_digits",
        help="the minimum ordinal digit width this root's revisions carry",
    )
    p_mark_revisions.add_argument(
        "--unsealed", action="store_true",
        help="write the pre-seal grammar (no seal_sha256 key) -- the documented rollback "
             "path (design.md Decision K), run once per declared root before reverting; "
             "never a routine choice",
    )
    p_mark_class = mark_sub.add_parser(
        "class",
        help="record guidance/<folder>/.paper-writing.json's own class grammar, validated "
             "against the folders actually there right now",
    )
    p_mark_class.add_argument(
        "--folder", required=True,
        help="a directory name directly under guidance/ to classify -- matched against a "
             "derived enumeration, never a literal list",
    )
    p_mark_class.add_argument(
        "--class", required=True, dest="class_value",
        help="one of paper_guidance.CLASSES ('style-reference', 'evidence')",
    )
    p_mark_class.add_argument(
        "--guidance", default=None,
        help="override guidance/ location; must resolve inside the repository root",
    )
    p_mark_class.add_argument(
        "--unsealed", action="store_true",
        help="write the pre-seal grammar (no seal_sha256 key) -- the documented rollback "
             "path (design.md Decision K), run once per declared folder before reverting; "
             "never a routine choice",
    )

    p_separate = sub.add_parser(
        "separate",
        help="score a proposed whole-cut assignment of source sections to blocks against the "
             "document's own structure and refuse on any defect -- never records a binding "
             "under any outcome",
    )
    p_separate.add_argument(
        "--paper", default=None,
        help="override paper/ location; must resolve inside the repository root",
    )
    p_separate.add_argument(
        "--sections", default=None,
        help="override sections/ location; must resolve inside the repository root",
    )
    p_separate.add_argument(
        "--proposal", required=True,
        help="path to the proposal JSON file naming the whole cut; must resolve inside the "
             "repository root",
    )

    p_observe = sub.add_parser(
        "observe",
        help="validate an insumos-observer report against the observable-fact schema, then "
             "reconcile it against a real disk measurement this process takes itself, read-only",
    )
    p_observe.add_argument(
        "--report", required=True,
        help="path to the insumos-observer JSON report to validate; must resolve inside the repository root",
    )
    p_observe.add_argument(
        "--proposals", default=None,
        help="proposals/ location, for the disk-truth reconciliation; no default -- omit to "
             "skip reconciling formulation/dataset against disk; must resolve inside the "
             "repository root",
    )
    p_observe.add_argument(
        "--experiments", default=None,
        help="experiments/ location, for the disk-truth reconciliation; no default -- omit to "
             "skip reconciling experimental-design against disk; must resolve inside the "
             "repository root",
    )
    p_observe.add_argument(
        "--implementation", default=None,
        help="the target implementation repository's own path, for the disk-truth "
             "reconciliation; no default -- omit to skip reconciling implementation/results "
             "against disk; must resolve inside the repository root",
    )

    p_resolve = sub.add_parser(
        "resolve",
        help="resolve one identifier's metadata through a named connector, keyless",
    )
    resolve_cache = p_resolve.add_mutually_exclusive_group()
    resolve_cache.add_argument(
        "--paper", default=None,
        help="override paper/ location; must resolve inside the repository root",
    )
    resolve_cache.add_argument(
        "--cache-dir", default=None,
        help="cache the resolution as <dir>/<metadata_digest>.json instead of under "
             "paper/, for a caller that is not writing a paper; must resolve inside "
             "the repository root",
    )
    p_resolve.add_argument("--identifier", required=True, help="DOI or arXiv id to resolve")
    p_resolve.add_argument(
        "--resolver", required=True, choices=paper_resolve.RESOLVERS,
        help="which connector to resolve through",
    )
    p_resolve.add_argument(
        "--role", default="resolution", choices=paper_resolve.ROLES,
        help="which papersmith.yaml connector role this call is validated against",
    )

    p_full_text = sub.add_parser(
        "full_text",
        help="fetch one already-resolved identifier's own PDF, keyless, from its cached "
             "metadata's measured full_text_url, and place it loose under guidance/<section>/",
    )
    p_full_text.add_argument(
        "--paper", default=None,
        help="override paper/ location (where --metadata-digest's cache lives); "
             "must resolve inside the repository root",
    )
    p_full_text.add_argument(
        "--guidance", default=None,
        help="override guidance/ location; must resolve inside the repository root",
    )
    p_full_text.add_argument(
        "--section", required=True,
        help="the guidance/<section-id>/ this PDF lands loose inside",
    )
    p_full_text.add_argument(
        "--metadata-digest", required=True,
        help="the digest of an already-cached `resolve` result to fetch this record's PDF for",
    )
    p_full_text.add_argument(
        "--cite-key", required=True,
        help="the \\cite{} key this PDF supports; becomes the output filename's stem",
    )

    p_bib = sub.add_parser("bib", help="paper/refs.bib management -- never hand-typed")
    bib_sub = p_bib.add_subparsers(dest="bib_command", required=True)
    p_bib_build = bib_sub.add_parser(
        "build", help="rebuild refs.bib whole, sorted, from cached resolved metadata only",
    )
    p_bib_build.add_argument(
        "--paper", default=None,
        help="override paper/ location; must resolve inside the repository root",
    )
    p_bib_build.add_argument(
        "--guidance", default=None,
        help="override guidance/ location; must resolve inside the repository root",
    )
    p_bib_refresh = bib_sub.add_parser(
        "refresh",
        help="relink one citation's existing evidence to fresher cached metadata of the SAME work: "
             "appends a copy of the record bib build reads, changing only resolver and "
             "metadata_digest; never re-judges the source, never creates evidence",
    )
    p_bib_refresh.add_argument(
        "--paper", default=None,
        help="override paper/ location; must resolve inside the repository root",
    )
    p_bib_refresh.add_argument(
        "--guidance", default=None,
        help="override guidance/ location; must resolve inside the repository root",
    )
    p_bib_refresh.add_argument(
        "--cite-key", required=True, help="the \\cite{} key whose current evidence record is relinked",
    )
    p_bib_refresh.add_argument(
        "--metadata-digest", required=True,
        help="digest of an already-cached `resolve` result for the same DOI/arXiv id",
    )
    p_bib_refresh.add_argument(
        "--resolver", default=None, choices=paper_resolve.RESOLVERS,
        help="optional; must equal the cached metadata's own resolver, which is used when omitted",
    )

    p_validate = sub.add_parser(
        "validate",
        help="the single gate: submit one judged verdict, check round-bounded satisfaction, write on success",
    )
    p_validate.add_argument(
        "--paper", default=None,
        help="override paper/ location; must resolve inside the repository root",
    )
    p_validate.add_argument("--block", required=True, help="block id this evidence/write targets")
    p_validate.add_argument("--claim", default=None, help="claim text this call submits evidence for")
    p_validate.add_argument("--quote", default=None, help="the verbatim quote to locate in --source-md")
    p_validate.add_argument("--source-md", default=None, help="the ingested .md the quote is located in")
    p_validate.add_argument(
        "--verdict", default=None, choices=("holds", "does-not-hold"),
        help="the agent's own judgment for a located --quote; omit --quote/--source-md for insufficient",
    )
    p_validate.add_argument("--reason", default=None, help="why the record is insufficient")
    p_validate.add_argument("--cite-key", default=None, help="the \\cite{} key this record supports")
    p_validate.add_argument("--identifier", default=None, help="the resolved DOI/arXiv id")
    p_validate.add_argument("--resolver", default=None, help="which connector resolved --identifier")
    p_validate.add_argument("--metadata-digest", default=None, help="the cached resolution's own digest")
    p_validate.add_argument("--regime", default=None, choices=paper_vocabulary.CITATIONS_REGIMES)
    p_validate.add_argument(
        "--section-md", default=None,
        help="an already-headered sections/*.md path to read --block's citations regime from",
    )
    p_validate.add_argument("--round", type=int, default=None, help="override the auto-derived round number")
    p_validate.add_argument(
        "--min-sources", type=int, default=None,
        help="override the minimum DISTINCT source papers required per claim "
             "(default: paper_validate.DEFAULT_MIN_SOURCES_PER_CLAIM)",
    )
    p_validate.add_argument(
        "--guidance", default=None,
        help="override guidance/ location; must resolve inside the repository root",
    )
    p_validate.add_argument("--body", default=None, help="path to the candidate body, or - for stdin")
    p_validate.add_argument(
        "--sentence", default=None,
        help="path to a JSON {text, regime, citations:[...]} object; checked before any evidence step",
    )

    p_plan = sub.add_parser(
        "plan", help="read-only: guidance classes, declaration/fact fill state, provenance state",
    )
    p_plan.add_argument(
        "--paper", default=None,
        help="override paper/ location; must resolve inside the repository root",
    )
    p_plan.add_argument(
        "--guidance", default=None,
        help="override guidance/ location; must resolve inside the repository root",
    )
    p_plan.add_argument(
        "--sections", default=None,
        help="override sections/ location; must resolve inside the repository root",
    )

    p_write = sub.add_parser(
        "write",
        help="judge an already-drafted, already-audited block: reconcile, then substitute or report why not",
    )
    p_write.add_argument(
        "--paper", default=None,
        help="override paper/ location; must resolve inside the repository root",
    )
    p_write.add_argument(
        "--sections", default=None,
        help="override sections/ location; must resolve inside the repository root",
    )
    p_write.add_argument("--section", required=True, help="the section id this block's contract declares in its own header (e.g. 'introduction'), never the sections/*.md filename stem ('06-introduction') -- a stem refuses SECTION_UNKNOWN")
    p_write.add_argument("--block", required=True, help="block id to write")
    p_write.add_argument(
        "--draft", required=True,
        help="path to the redactor's JSON envelope: {latex, bindings}; must resolve inside the repository root",
    )
    p_write.add_argument(
        "--audit", required=True,
        help="path to the contract-auditor's JSON envelope: {verdicts}; must resolve inside the repository root",
    )
    p_write.add_argument(
        "--evidence", default=None,
        help="path to a JSON array of {id, regime, ...} evidence records this block may bind against",
    )
    p_write.add_argument(
        "--style", default=None,
        help="path to a JSON array of the style-sampler's {reference, source_md, span} proposals; "
             "residency-verified and recorded as R before the tripwire runs against the styled draft",
    )
    p_write.add_argument(
        "--guidance", default=None,
        help="override guidance/ location; must resolve inside the repository root",
    )
    p_write.add_argument(
        "--transcript", default=None,
        help="path to a recorded agent transcript; containment-checked, never parsed for judgment",
    )
    p_write.add_argument(
        "--grounding", default=None,
        help="path to the section-grounding-auditor's JSON envelope: "
             "{support: [{sentence, fact, verdict, span}, ...]}; must resolve inside the "
             "repository root",
    )

    p_render = sub.add_parser(
        "render", help="compile one diagram id standalone, exactly once, via latexmk",
    )
    p_render.add_argument(
        "--paper", default=None,
        help="override paper/ location; must resolve inside the repository root",
    )
    p_render.add_argument("--figure-id", required=True, help="the diagram id under paper/Figures/")
    p_render.add_argument(
        "--latexmk-path", default=None,
        help="test-only: override the PATH shutil.which searches for latexmk",
    )
    p_render.add_argument(
        "--acknowledge-reset", action="store_true",
        help="explicit operator acknowledgement: clears this id's spent repair-budget ledger, compiles nothing",
    )
    p_render.add_argument(
        "--section", default=None,
        help="run obligation checks after compiling: the section id this block's contract declares in its own header (e.g. 'introduction'), never the sections/*.md filename stem ('06-introduction') -- a stem refuses SECTION_UNKNOWN",
    )
    p_render.add_argument(
        "--block", default=None, help="the block id whose figure: obligation to check after compiling",
    )
    p_render.add_argument(
        "--sections", default=None,
        help="override sections/ location; must resolve inside the repository root",
    )

    p_couplings = sub.add_parser(
        "couplings",
        help="validate and write paper/couplings.json whole -- the producer verify's own "
             "declaration record never had",
    )
    p_couplings.add_argument(
        "--paper", default=None,
        help="override paper/ location; must resolve inside the repository root",
    )
    p_couplings.add_argument(
        "--file", required=True,
        help="path to the JSON couplings record to validate and write, or - for stdin; "
             "a file path must resolve inside the repository root",
    )

    p_verify = sub.add_parser(
        "verify",
        help="read-only report over the couplings, citation integrity and contract currency",
    )
    p_verify.add_argument(
        "--paper", default=None,
        help="override paper/ location; must resolve inside the repository root",
    )
    p_verify.add_argument(
        "--sections", default=None,
        help="override sections/ location; must resolve inside the repository root",
    )

    p_place = sub.add_parser(
        "place", help="place an already-measured figure's PDF; compiles nothing, needs provenance",
    )
    p_place.add_argument(
        "--paper", default=None,
        help="override paper/ location; must resolve inside the repository root",
    )
    p_place.add_argument("--figure-id", required=True, help="the diagram id under paper/Figures/")
    p_place.add_argument("--pdf", required=True, help="path to the already-produced PDF")
    p_place.add_argument(
        "--provenance", required=True,
        help="path to a JSON record naming the run this figure was measured from",
    )

    p_figure = sub.add_parser(
        "figure", help="optimize a diagram's TikZ source, or audit it against the prose",
    )
    figure_sub = p_figure.add_subparsers(dest="figure_command", required=True)

    p_figure_optimize = figure_sub.add_parser(
        "optimize",
        help="compact and compile-validate one TikZ source: prune provably-unused libraries, "
             "add detected-missing ones, factor repeated styles into one \\tikzset",
    )
    p_figure_optimize.add_argument(
        "--paper", default=None,
        help="override paper/ location; must resolve inside the repository root",
    )
    figure_source = p_figure_optimize.add_mutually_exclusive_group(required=True)
    figure_source.add_argument(
        "--figure-id",
        help="the diagram id under paper/Figures/; reads its manifest and writes back in place",
    )
    figure_source.add_argument(
        "--file",
        help="a .tex path; alone it is a dry run that prints the candidate and writes nothing",
    )
    figure_destination = p_figure_optimize.add_mutually_exclusive_group()
    figure_destination.add_argument(
        "--output", default=None, help="write the optimized source here instead of in place",
    )
    figure_destination.add_argument(
        "--in-place", action="store_true", help="write back over the source (the default for --figure-id)",
    )
    p_figure_optimize.add_argument(
        "--strip-comments", action="store_true",
        help="drop comment text; %% node: markers and %%! directives are always preserved",
    )
    p_figure_optimize.add_argument(
        "--no-compile", action="store_true",
        help="skip compile-validation (unsafe: stop A and the manifest cross-check still run)",
    )
    p_figure_optimize.add_argument(
        "--latexmk-path", default=None,
        help="test-only: override the PATH shutil.which searches for latexmk",
    )

    p_figure_audit = figure_sub.add_parser(
        "audit",
        help="verify a diagram's declared components against its section's prose "
             "(pass | fail | unmeasured; a content finding is never a refusal)",
    )
    p_figure_audit.add_argument(
        "--paper", default=None,
        help="override paper/ location; must resolve inside the repository root",
    )
    p_figure_audit.add_argument(
        "--sections", default=None,
        help="override sections/ location; must resolve inside the repository root",
    )
    figure_audit_source = p_figure_audit.add_mutually_exclusive_group(required=True)
    figure_audit_source.add_argument("--figure-id", help="the diagram id under paper/Figures/")
    figure_audit_source.add_argument("--file", help="a .tex path; requires --manifest")
    p_figure_audit.add_argument(
        "--manifest", default=None, help="the <id>.diagram.json to compare against; required with --file",
    )
    p_figure_audit.add_argument("--section", required=True, help="the section id this block's contract declares in its own header (e.g. 'introduction'), never the sections/*.md filename stem ('06-introduction') -- a stem refuses SECTION_UNKNOWN")
    p_figure_audit.add_argument(
        "--block", default=None,
        help="the block whose figure: obligation this diagram answers (optional; without it the "
             "audit reports unmeasured rather than guessing a binding)",
    )
    p_figure_audit.add_argument(
        "--visual-report", default=None,
        help="path to a figure-review `visual-report.json` (from `figure-review measure`); "
             "an already-computed, plain-data dict passed straight to "
             "audit_semantics(visual=...) -- this call never reads Figures/ or spawns a "
             "rasterizer to produce it itself",
    )
    p_packet = sub.add_parser(
        "packet",
        help="read-only: this block's own contract prose plus every style-reference "
             "paper's heading outline (offsets only, never reference prose), plus -- for a "
             "transposition-mode block -- its own bound source sections",
    )
    p_packet.add_argument("--section", required=True, help="the section id this block's contract declares in its own header (e.g. 'introduction'), never the sections/*.md filename stem ('06-introduction') -- a stem refuses SECTION_UNKNOWN")
    p_packet.add_argument("--block", required=True, help="block id to assemble the packet for")
    p_packet.add_argument(
        "--sections", default=None,
        help="override sections/ location; must resolve inside the repository root",
    )
    p_packet.add_argument(
        "--guidance", default=None,
        help="override guidance/ location; must resolve inside the repository root",
    )
    p_packet.add_argument(
        "--paper", default=None,
        help="override paper/ location; must resolve inside the repository root",
    )

    p_reuse = sub.add_parser(
        "reuse",
        help="read-only: for one block's open claims, which already-ingested, "
             "evidence-classed papers carry no verdict yet",
    )
    p_reuse.add_argument(
        "--paper", default=None,
        help="override paper/ location; must resolve inside the repository root",
    )
    p_reuse.add_argument(
        "--guidance", default=None,
        help="override guidance/ location; must resolve inside the repository root",
    )
    p_reuse.add_argument("--block", required=True, help="the block id whose open claims to report")
    p_reuse.add_argument(
        "--min-sources", type=int, default=None, dest="min_sources",
        help="distinct holds sources a claim needs before it is no longer open "
             "(default paper_validate.DEFAULT_MIN_SOURCES_PER_CLAIM)",
    )

    p_exhaustion = sub.add_parser(
        "exhaustion",
        help="read-only, corpus-wide: every evidence-classed ingested paper's exhaustion "
             "state -- lists only, never deletes",
    )
    p_exhaustion.add_argument(
        "--paper", default=None,
        help="override paper/ location; must resolve inside the repository root",
    )
    p_exhaustion.add_argument(
        "--guidance", default=None,
        help="override guidance/ location; must resolve inside the repository root",
    )
    p_exhaustion.add_argument(
        "--min-sources", type=int, default=None, dest="min_sources",
        help="distinct holds sources a claim needs before it is no longer open "
             "(default paper_validate.DEFAULT_MIN_SOURCES_PER_CLAIM)",
    )

    return parser


COMMANDS = (
    "scaffold", "status", "open", "substitute", "contract", "readiness", "phases", "skeleton", "order",
    "declare", "bind", "mark", "separate", "observe", "plan", "resolve", "full_text", "bib", "validate",
    "write", "render", "place", "couplings", "verify", "figure", "packet", "reuse", "exhaustion",
)
_COMMANDS = {
    "scaffold": cmd_scaffold,
    "status": cmd_status,
    "open": cmd_open,
    "substitute": cmd_substitute,
    "contract": cmd_contract,
    "readiness": cmd_readiness,
    "phases": cmd_phases,
    "skeleton": cmd_skeleton,
    "order": cmd_order,
    "declare": cmd_declare,
    "bind": cmd_bind,
    "mark": cmd_mark,
    "separate": cmd_separate,
    "observe": cmd_observe,
    "plan": cmd_plan,
    "resolve": cmd_resolve,
    "full_text": cmd_full_text,
    "bib": cmd_bib,
    "validate": cmd_validate,
    "write": cmd_write,
    "render": cmd_render,
    "place": cmd_place,
    "couplings": cmd_couplings,
    "verify": cmd_verify,
    "figure": cmd_figure,
    "packet": cmd_packet,
    "reuse": cmd_reuse,
    "exhaustion": cmd_exhaustion,
}


def main(argv: list[str] | None = None) -> int:
    try:
        _require_supported_python()
        parser = build_parser()
        args = parser.parse_args(argv)
        result = _COMMANDS[args.command](args)
    except Refused as exc:
        print(json.dumps({"status": "refused", "code": exc.code, "detail": exc.detail}))
        return 2
    print(json.dumps({"status": "ok", "command": args.command, **result}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
