"""paper_vocabulary: the three closed vocabularies a section contract's
header may draw from, and nothing else.

No I/O, no state — pure tuples plus a validator per tuple. A consumer that
only needs the vocabulary (a later phase, or a roster derivation) imports
this module alone and drags in no reader, no disk access
(design.md, `Internal layering`).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_core" / "implementation"))
from impl_refusals import Refused  # noqa: E402

#: `requires_facts` entries a block may declare — `specs/section-contract`,
#: `Requirement: Closed Fact Vocabulary`. Ten ids, exactly as spelled there.
FACTS: tuple[str, ...] = (
    "formulation",
    "contributions",
    "problem-statement",
    "gap",
    "dataset",
    "experimental-design",
    "implementation",
    "results",
    "limitations",
    "skeleton",
)

#: `requires_declarations` entries a block may declare — operator-supplied
#: inputs derived from no fact. `specs/section-contract`,
#: `Requirement: Closed Declaration Vocabulary`.
DECLARATIONS: tuple[str, ...] = (
    "author-roles",
    "grant-title",
    "grant-code",
    "repository-url",
    "keyword-bounds",
    "classification-line",
    # The ethics committee's approval (committee, code, date) and the consent
    # route, or "Not applicable." for public data -- copied from the approval
    # record like a grant code, never derived from a fact. Read by the
    # back-matter ethics and informed-consent blocks.
    "ethics-approval",
)

#: A block's `citations` value — exactly one of these three.
#: `specs/section-contract`, `Requirement: Closed Citations Regime`.
CITATIONS_REGIMES: tuple[str, ...] = ("discovery", "resolution", "none")

#: A citation verdict — exactly one of these three.
#: `no-claim-without-a-source-that-holds-it`, `citation-validation` spec,
#: `Requirement: Three Verdicts, insufficient Is Not Lenient`. `insufficient`
#: is not a soft `holds`: it fails the citation and consumes a search-round
#: iteration exactly as `does-not-hold` does, everywhere this vocabulary is
#: consumed.
VERDICTS: tuple[str, ...] = ("holds", "does-not-hold", "insufficient")

#: A block or section's drafting `mode` — exactly one of these two, named
#: once here so no string literal for a mode needs to be spelled again
#: anywhere else (`transposition-fidelity` spec, `Requirement: Only A
#: Transposition-Mode Block Is Checked, Mode Derived From The Contract On
#: Disk, Never Listed`; `design.md`, Decision D). `transposition` admits
#: only `fact`/`structural`/`resolution`-class evidence bindings; `argument`
#: additionally admits `discovery`-class evidence (`evidence-bound-drafting`
#: spec, `Requirement: Mode-Admissible Bindings`).
MODE_TRANSPOSITION: str = "transposition"
MODE_ARGUMENT: str = "argument"

#: `the-writer-may-assert-only-what-it-was-given`, `section-contract` spec,
#: `Requirement: Closed Mode Vocabulary And Transcription`.
MODES: tuple[str, ...] = (MODE_TRANSPOSITION, MODE_ARGUMENT)

#: The closed list `paper_bindings.py`'s structural typing (D3) checks a
#: `structural` sentence against — any of these words, case-folded, makes
#: the sentence carry a comparison rather than pure structure. Not
#: exhaustive of English comparatives; exhaustive of what this skill treats
#: as a claim-bearing comparative (`design.md`, Decision D3).
COMPARATIVES: tuple[str, ...] = (
    "more", "less", "greater", "fewer", "higher", "lower", "better", "worse",
    "larger", "smaller", "faster", "slower", "stronger", "weaker", "superior",
    "inferior", "outperforms", "underperforms", "exceeds", "surpasses",
    "improves", "degrades",
)

#: The closed list `paper_bindings.py`'s structural typing (D3) checks a
#: `structural` sentence's numeral detection against, alongside a bare
#: digit. Closed rather than an unfalsifiable heuristic, matching
#: `design.md`'s own rejection of proper-noun heuristics for the sibling
#: check.
NUMBER_WORDS: tuple[str, ...] = (
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten", "eleven", "twelve", "dozen", "several", "many", "few",
    "both", "half", "first", "second", "third", "fourth", "fifth",
)


#: A decline's `condition` — the disk state that justifies it, re-evaluated
#: on every read. Closed like every other vocabulary here. One type today:
#: "does the named path (resolved relative to paper_dir's own parent
#: directory) currently hold nothing beyond an ignorable allowlist" —
#: general enough for any fact whose decline rests on "no real content
#: exists yet at path X" (an empty experiments/ tree, an uncloned target
#: repo, absent run outputs, ...).
CONDITION_TYPES: tuple[str, ...] = ("directory-empty-except",)


def validate_condition_type(value) -> None:
    """Refuses `UNKNOWN_CONDITION_TYPE` (work-state) when `value` is not
    one of the declared condition types."""
    if value not in CONDITION_TYPES:
        raise Refused(
            "UNKNOWN_CONDITION_TYPE",
            f"{value!r} is not one of the declared condition types {CONDITION_TYPES}",
        )


def validate_fact(fact_id: str) -> None:
    """Refuses `UNKNOWN_FACT` (work-state) when `fact_id` is not one of the
    ten declared facts."""
    if fact_id not in FACTS:
        raise Refused("UNKNOWN_FACT", f"{fact_id!r} is not one of the declared facts {FACTS}")


def validate_declaration(declaration_id: str) -> None:
    """Refuses `UNKNOWN_DECLARATION` (work-state) when `declaration_id` is
    not one of the seven declared declarations."""
    if declaration_id not in DECLARATIONS:
        raise Refused(
            "UNKNOWN_DECLARATION",
            f"{declaration_id!r} is not one of the declared declarations {DECLARATIONS}",
        )


def validate_citations(value: str) -> None:
    """Refuses `UNKNOWN_CITATIONS_REGIME` (work-state) when `value` is not
    one of `discovery`, `resolution`, `none`."""
    if value not in CITATIONS_REGIMES:
        raise Refused(
            "UNKNOWN_CITATIONS_REGIME",
            f"{value!r} is not one of the declared citations regimes {CITATIONS_REGIMES}",
        )


def validate_verdict(value: str) -> None:
    """Refuses `UNKNOWN_VERDICT` (work-state) when `value` is not one of
    `holds`, `does-not-hold`, `insufficient`."""
    if value not in VERDICTS:
        raise Refused(
            "UNKNOWN_VERDICT",
            f"{value!r} is not one of the declared verdicts {VERDICTS}",
        )


def validate_mode(value: str) -> None:
    """Refuses `UNKNOWN_MODE` (work-state) when `value` is not one of
    `transposition`, `argument`."""
    if value not in MODES:
        raise Refused("UNKNOWN_MODE", f"{value!r} is not one of the declared modes {MODES}")
