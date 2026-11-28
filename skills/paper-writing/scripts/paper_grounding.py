"""paper_grounding: per-sentence support reconciliation for a transposition
block against its own bound source section's bytes (`transposition-
grounding` spec; `design.md`, "The block asserts only what its section
carries").

A fourth sibling in `write_block`'s judge chain, shaped on `paper_audit.py`'s
own account-versus-real-bytes reconciliation (`:56-101`), never extending it
(design.md D5). An agent proposes a per-sentence support verdict; this module
re-derives both the subject sentences (from the draft's own segmented
bindings) and the section bytes (from the block's own resolved bound
sections) and reconciles the account against those re-derived values, never
trusting either from the account's own copy. `supported` is the verdict that
lets a sentence reach substitution, so `supported` is the one this module
requires to be grounded (D1) -- the inversion of `contract-audit`'s own
asymmetry, where the *blocking* verdict is the one required to cite a span.

Public surface:

    subjects_for(bindings, source_sections) -> list[Binding]
    reconcile_support(subjects, account, source_sections, *, block_id) -> list[dict]
        (raises GROUNDING_ACCOUNT_ABSENT, GROUNDING_SENTENCE_UNKNOWN,
         GROUNDING_VERDICT_MISSING, then SECTION_UNSUPPORTED_CLAIM naming
         every unsupported sentence)
    judge_support(subjects, account, source_sections, *, block_id) -> list[dict]
        (the same reconciliation, unsupported verdicts returned, not refused)
    refuse_unsupported(reconciled, *, block_id) -> None  (raises SECTION_UNSUPPORTED_CLAIM)
    source_grounding_report(subjects, reconciled) -> dict
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_core" / "implementation"))
from impl_refusals import Refused  # noqa: E402


def _body_of(section: dict) -> str:
    """One bound section's text WITHOUT its own heading line.

    `paper_source_span.resolve_bound_sections` slices from the heading's own
    first byte -- `paper_guidance.segment_markdown` sets `byte_start` at the
    `#` rather than beneath it -- so `section["text"]` opens with the heading
    itself. For the verbatim check that is correct and must not change: pasting
    a source's heading into a draft IS copying it, and `SOURCE_SECTION_
    VERBATIM` should see it.

    For grounding it is wrong, and the difference is the whole point of this
    guard. A `supported` verdict citing only the section's TITLE -- no body
    text at all -- was byte-present in the full slice and therefore survived,
    licensing a sentence the section's body never supports. A title says what a
    section is about; it does not assert anything, so it cannot ground a claim.

    Fixed HERE rather than in `paper_source_span`, deliberately. That slicer is
    shared with the already-shipped verbatim check, which wants the heading
    included. Two checks wanting different things from the same bytes is not a
    reason to change the bytes -- it is a reason for each to derive what it
    needs. The same "sibling, never extension" rule this module already follows
    toward `check_source_section_verbatim`.

    A section whose text carries no newline at all is treated as heading-only
    and yields an empty body: nothing in it can ground anything, which is the
    safe direction.
    """
    text = section.get("text", "")
    if not text.startswith("#"):
        return text
    newline = text.find("\n")
    return "" if newline == -1 else text[newline + 1:]


def subjects_for(bindings: list, source_sections: tuple) -> list:
    """The subject set: the intersection of two independently produced sets
    -- the draft's own segmented bindings and the block's resolved bound
    sections -- computed fresh on every call (`transposition-grounding`
    spec, `Requirement: The Subject Set Is An Intersection Derived From
    Bytes, Never A List`; design.md D3). No block id, section title,
    document filename, or lineage literal decides membership -- only
    `Binding.kind == "fact"` and `Binding.ref` matching a `source_sections`
    entry's own `"fact"` key."""
    bound_facts = {section["fact"] for section in source_sections}
    return [binding for binding in bindings if binding.kind == "fact" and binding.ref in bound_facts]


def reconcile_support(subjects: list, account: dict | None, source_sections: tuple, *, block_id: str) -> list:
    """`_reconcile` below, then `SECTION_UNSUPPORTED_CLAIM` naming every
    `unsupported` sentence when the account holds any (`refuse_unsupported`).
    The account is reconciled in full before the claim refusal, so an
    incomplete account refuses its own code first."""
    reconciled = _reconcile(subjects, account, source_sections, block_id=block_id)
    refuse_unsupported(reconciled, block_id=block_id)
    return reconciled


def _reconcile(subjects: list, account: dict | None, source_sections: tuple, *, block_id: str) -> list:
    """Reconciles an agent's per-sentence support account against subjects
    and section bytes re-derived independently, in both directions
    (`transposition-grounding` spec, `Requirement: The Account Is
    Reconciled...`; design.md D1/D7).

    `account` is never trusted about its own sentence list or its own copy
    of a section's text -- every byte compared here comes from
    `source_sections`' own `"text"` field, the same bytes
    `resolve_bound_sections` sliced from disk.

    Scoped to subjects' own facts alone (design.md Scope; `transposition-
    grounding` spec, `Requirement: A Sibling Check, Never An Extension...`):
    an account entry whose `"fact"` names something no subject cares about
    (an `evidence:` id, a non-bound fact, an `argument`-mode block's own
    facts) is simply irrelevant here and never inspected -- ignored, never
    `GROUNDING_SENTENCE_UNKNOWN`.

    Raises `GROUNDING_ACCOUNT_ABSENT` (subjects exist, `account is None`),
    `GROUNDING_SENTENCE_UNKNOWN` (a relevant entry's sentence matches no
    subject), `GROUNDING_VERDICT_MISSING` (a subject has no relevant
    entry); an `unsupported` verdict is kept, never raised here --
    `reconcile_support` refuses `SECTION_UNSUPPORTED_CLAIM` once the whole
    account is reconciled, naming every one. A `supported` verdict whose span is empty, or not byte-
    present in that fact's own bound section text, downgrades to
    `undecidable` with the span cleared (D1's inversion of `contract-
    audit`'s own asymmetry) -- this is the one check this whole change
    exists to make load-bearing, so it is proven by mutation (tasks.md
    3.3), never merely asserted.
    """
    if not subjects:
        return []
    if account is None:
        raise Refused(
            "GROUNDING_ACCOUNT_ABSENT",
            f"{block_id}: {len(subjects)} subject sentence(s) and no grounding account was "
            "supplied; run `write --grounding <path>` with the section-grounding-auditor "
            "agent's own account",
        )

    subject_facts = {subject.ref for subject in subjects}
    subject_sentences = {subject.sentence for subject in subjects}
    entries = account.get("support", [])
    relevant_entries = [entry for entry in entries if entry.get("fact") in subject_facts]

    by_sentence: dict[str, dict] = {}
    for entry in relevant_entries:
        if entry["sentence"] not in subject_sentences:
            raise Refused(
                "GROUNDING_SENTENCE_UNKNOWN",
                f"{block_id}: grounding account names a sentence no subject carries: "
                f"{entry['sentence']!r}",
            )
        by_sentence[entry["sentence"]] = entry

    sections_by_fact: dict[str, list] = {}
    for section in source_sections:
        sections_by_fact.setdefault(section["fact"], []).append(section)

    reconciled = []
    for subject in subjects:
        entry = by_sentence.get(subject.sentence)
        if entry is None:
            raise Refused(
                "GROUNDING_VERDICT_MISSING",
                f"{block_id}: subject sentence has no grounding-account verdict: "
                f"{subject.sentence!r}",
            )
        own_sections = sections_by_fact[subject.ref]
        verdict = entry["verdict"]
        span = entry.get("span") or ""
        downgraded = False

        if verdict == "supported":
            byte_present_own = bool(span) and any(span in _body_of(section) for section in own_sections)
            if not byte_present_own:
                verdict = "undecidable"
                span = ""
                downgraded = True

        first = own_sections[0]
        reconciled.append({
            "sentence": subject.sentence,
            "fact": subject.ref,
            "lineage": first["lineage"],
            "title": first["title"],
            "verdict": verdict,
            "span": span,
            "downgraded": downgraded,
        })
    return reconciled


def judge_support(subjects: list, account: dict | None, source_sections: tuple, *, block_id: str) -> list:
    """`reconcile_support` without its final `SECTION_UNSUPPORTED_CLAIM`:
    every subject's reconciled verdict, `unsupported` ones included, so a
    caller can hand the whole account to a re-draft. Still refuses every
    incomplete-account code. Never a pass: `write` only ever substitutes
    after `reconcile_support`, which refuses on any `unsupported`."""
    return _reconcile(subjects, account, source_sections, block_id=block_id)


def refuse_unsupported(reconciled: list, *, block_id: str) -> None:
    """Refuses `SECTION_UNSUPPORTED_CLAIM` naming EVERY `unsupported`
    sentence of the account, never only the first, so the one re-draft
    answers all of them at once."""
    unsupported = []
    for entry in reconciled:
        verdict = entry["verdict"]
        if verdict == "unsupported":
            unsupported.append(entry)
    if not unsupported:
        return
    claims = "; ".join(
        f"fact {entry['fact']!r} (lineage {entry['lineage']!r}, section {entry['title']!r}): "
        f"{entry['sentence']!r}"
        for entry in unsupported
    )
    raise Refused(
        "SECTION_UNSUPPORTED_CLAIM",
        f"{block_id}: {len(unsupported)} of {len(reconciled)} subject sentence(s) claim something "
        f"their bound section never states: {claims}",
    )


def source_grounding_report(subjects: list, reconciled: list) -> dict:
    """Mirrors `source_fidelity_report`/`style_channel_report`'s shipped
    shape (design.md D8): `decided` (verdict resolved `supported`),
    `undecidable` (agent-returned only) and `downgraded` (reconciliation-
    produced only) as SEPARATE counts -- an honest abstention and a
    downgraded, unfounded `supported` must stay distinguishable from the
    envelope alone (`transposition-grounding` spec, `Requirement:
    Undecidable Never Blocks Alone...`). `status` is `"measured"` only when
    `decided > 0`, else `"unmeasured"` with the true `subjects` count --
    the two `unmeasured` cases (no subjects at all vs. subjects with none
    decided) are distinguished by that count alone, never a third status
    value."""
    if not subjects:
        return {"status": "unmeasured", "subjects": 0}
    decided = sum(1 for entry in reconciled if entry["verdict"] == "supported")
    downgraded = sum(1 for entry in reconciled if entry["downgraded"])
    undecidable = sum(
        1 for entry in reconciled if entry["verdict"] == "undecidable" and not entry["downgraded"]
    )
    return {
        "status": "measured" if decided > 0 else "unmeasured",
        "subjects": len(subjects),
        "decided": decided,
        "undecidable": undecidable,
        "downgraded": downgraded,
    }
