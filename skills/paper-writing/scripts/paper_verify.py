"""paper_verify: eight pure checks over a `paper_coupling_evidence.Evidence`,
and the report they assemble into (`the-couplings-hold-or-they-do-not`).

Every function below is a pure function of an already-built `Evidence`
object — no `Path`, no `open`, no disk read anywhere in this module
(`tests/test_paper_writing.py`, `ReadOnlyTests`'s AST lock holds this file
to exactly that). `skill-audit`'s shape throughout: derive both sides where
a side can be derived, publish the provenance of every side that cannot,
report, never repair.

`CHECKS` is one closed roster (contribution-list, chain, gap, artefacts,
future-work, citations, contract-currency, figure-semantics, language,
references); `language` reads a scan the caller hands in (`run(..., language=)`)
and `references` the sidecar's records (`run(..., references=)`); `run()` is
held to producing
exactly one report object per member, in both directions
(`ReportShapeTests`). `UNMEASURED_REASONS` is a second closed roster; every
member is proven reachable by a fixture elsewhere in the suite.

Verdict vocabulary is `pass` | `fail` | `unmeasured` — deliberately NOT
`paper_vocabulary.VERDICTS` (`holds`/`does-not-hold`/`insufficient`), which
belongs to a different domain entirely (WU1's claim<->source citation
verdicts). Reusing that vocabulary here would conflate two unrelated
judgments that happen to both be three-valued; `specs/coupling-
verification/spec.md`'s own `Requirement: Verdict Vocabulary And
Classification Field` names `pass|fail|unmeasured` explicitly, and this
module follows the spec's normative wording over design.md's one
illustrative JSON snippet (which used `holds|fails` loosely) — noted as a
documentation inconsistency in this change's own apply report, not silently
carried forward into a second live vocabulary.

Public surface:

    CHECKS               -> the seven check ids, in report order
    UNMEASURED_REASONS   -> every reason a check can report `unmeasured` for
    item_lines(body: bytes) -> list[str]  -- every `\\item ...` line's text,
                             stripped, in document order (`a-fact-is-
                             declared-or-it-is-produced`: shared by
                             `check_gap`'s own front extraction and
                             `paper_cli._resolve_expected_components`'s
                             produced-fact route)
    STRUCTURE_CHECKS     -> structural checks reported apart, under `structure`
    check_back_matter_order(evidence) -> dict -- declarations before the
                             references, appendices after them
    run(evidence) -> dict  {"checks": [...], "clean": bool,
                             "holds": int, "fails": int, "unmeasured": int,
                             "structure": [...]}
"""
from __future__ import annotations

import re

CHECKS: tuple[str, ...] = (
    "contribution-list",
    "chain",
    "gap",
    "artefacts",
    "future-work",
    "citations",
    "contract-currency",
    "figure-semantics",
    "language",
    "references",
)

#: Every reason a check's `unmeasured_reason` may carry. Closed: a check
#: returning a reason outside this tuple is a programming error in this
#: module, caught by `_entry`'s own assertion rather than shipped silently.
#:
#: `OPTIONAL_BLOCK_ABSENT` (`optional-block-semantics` spec, `Requirement:
#: Verify Excuses An Unopened Optional Block`) needs no `paper_cli.
#: REFUSAL_CLASSIFICATION` entry and moves no roster count: it is an
#: `UNMEASURED_REASONS` member, not a `Refused` exception -- the two
#: rosters are independent (this module's own docstring), and only the
#: `Refused` one is bidirectionally derived by `reachable_paper_refusal_
#: codes()` (tasks.md, Work Unit 3, 3.8).
UNMEASURED_REASONS: tuple[str, ...] = (
    "SECTION_CONTRACTS_UNREADABLE",
    "NO_BLOCK_REQUIRES_FACT",
    "BLOCK_NOT_DECLARED",
    "ASSISTED_READING_REQUIRED",
    "CONTRACT_RECORD_ABSENT",
    # `figure-semantics`'s own two reasons. `NO_FIGURE_DECLARED` is "the
    # paper declares no figure at all, so there is nothing to compare";
    # `FIGURE_SEMANTICS_UNMEASURED` is "a figure exists but the audit could
    # not reach a verdict" — kept distinct because they are different facts
    # about the paper, and folding either into the other would hide which.
    "NO_FIGURE_DECLARED",
    "FIGURE_SEMANTICS_UNMEASURED",
    "OPTIONAL_BLOCK_ABSENT",
    # `back-matter-order`'s own reason: `main.tex` carries no bibliography
    # command yet, so there is no reference list to place the back matter
    # against -- reported, never read as a correct order.
    "NO_BIBLIOGRAPHY",
    # `language`'s own reason: the caller handed `run()` no language scan
    # (`cmd_verify` always does; a direct `run(evidence)` does not).
    "LANGUAGE_NOT_SCANNED",
    # `chain`'s own reason: no block requiring the problem statement carries
    # a role-labeled line (`Problem:` ... `Evidence:`), so there is no chain
    # to compare -- the labeled form is optional prose, never required.
    "CHAIN_ROLES_ABSENT",
)

#: The structural checks `run()` reports under its own `structure` key,
#: apart from the closed `CHECKS` roster of couplings (whose count and
#: arithmetic stay exactly what `ReportShapeTests` pins).
STRUCTURE_CHECKS: tuple[str, ...] = ("back-matter-order", "own-paragraph", "appendix-length")

_VERDICTS = ("pass", "fail", "unmeasured")
#: Restated from `paper_bib.REFERENCE_STATUSES`: this module imports only `re`.
_REFERENCE_STATUSES = ("resolved", "not_found", "unreachable")

# The same citation vocabulary as `paper_bib.CITE_COMMANDS` (#81). This module
# may import nothing beyond its allowlist, so the tuple is restated here and
# `tests/test_paper_argv_boundaries.py` holds the two equal.
CITE_COMMANDS = ("cite", "citep", "citet", "citealp", "citealt", "citeauthor", "citeyear")
_CITE_RE = re.compile(
    rb"\\(?:" + "|".join(sorted(CITE_COMMANDS, key=len, reverse=True)).encode("ascii") + rb")\*?"
    rb"(?:\s*\[[^\]]*\]){0,2}\s*\{([^}]*)\}"
)
_BIB_ENTRY_RE = re.compile(rb"@[A-Za-z]+\{\s*([^,\s]+)\s*,")
_ITEM_RE = re.compile(r"^\\item (.*)$", re.MULTILINE)
_CLOSING_RE = re.compile(r"^Closing: (.*)$", re.MULTILINE)
_CHAIN_ROLES: tuple[str, ...] = ("Problem", "Contribution", "Property", "Instrument", "Evidence")
_CHAIN_ROLE_RE = {
    role: re.compile(rf"^{role}: (.*)$".encode("ascii"), re.MULTILINE) for role in _CHAIN_ROLES
}


def _entry(check: str, *, classification: str, verdict: str, sides: list,
           evidence: dict, limits: list, unmeasured_reason: str | None) -> dict:
    if verdict not in _VERDICTS:
        raise AssertionError(f"{verdict!r} is not one of {_VERDICTS}")
    if verdict == "unmeasured":
        if unmeasured_reason not in UNMEASURED_REASONS:
            raise AssertionError(f"{unmeasured_reason!r} is not a declared unmeasured reason")
    elif unmeasured_reason is not None:
        raise AssertionError("unmeasured_reason set on a non-unmeasured verdict")

    limits = list(limits)
    if sides and all(side["source"] == "declared" for side in sides):
        if "TWO_DECLARED_SIDES" not in limits:
            limits.append("TWO_DECLARED_SIDES")

    return {
        "check": check,
        "classification": classification,
        "verdict": verdict,
        "sides": sides,
        "evidence": evidence,
        "limits": limits,
        "unmeasured_reason": unmeasured_reason,
    }


def _unmeasured(check: str, classification: str, reason: str, *, evidence: dict | None = None) -> dict:
    return _entry(
        check, classification=classification, verdict="unmeasured",
        sides=[], evidence=evidence or {}, limits=[], unmeasured_reason=reason,
    )


def _optional_block_absence_reason(evidence, block_ids, optional_block_ids) -> str | None:
    """`OPTIONAL_BLOCK_ABSENT` fires only when `block_ids` is non-empty and
    EVERY one of them is both a member of `optional_block_ids` (declared
    `optional: true` in its section contract) AND absent from `main.tex`
    (not a key of `evidence.block_bodies` -- `paper_coupling_evidence.
    gather`'s own docstring: that dict is sliced only for ids `paper_block.
    parse` actually found opened). Membership, never a falsy-body check --
    an opened block substituted with genuinely empty content is still
    opened, and must be checked exactly like any other opened block
    (`optional-block-semantics` spec, `Requirement: Verify Excuses An
    Unopened Optional Block`: "excuses non-existence, never abandonment
    once opened").

    `optional_block_ids` is a caller-supplied set of RAW (unqualified)
    block ids -- the same vocabulary `block_ids` and `evidence.block_bodies`
    already speak. Every check function below defaults it to an empty
    `frozenset()`, so calling a check with no knowledge of which blocks are
    optional (today's only real caller, `run()`'s own default) never
    triggers this branch -- behaviour is unchanged until a caller resolves
    the corpus's own `BlockRecord.optional` flags and passes them in. That
    resolution needs `paper_graph.assemble_corpus`, which this checked-
    disk-never module cannot call itself (`_PAPER_VERIFY_ALLOWED_IMPORTS`);
    threading it from the corpus into a real caller is deferred work this
    unit's own notes name explicitly (tasks.md, Work Unit 3)."""
    if not block_ids:
        return None
    if all(
        block_id in optional_block_ids and block_id not in evidence.block_bodies
        for block_id in block_ids
    ):
        return "OPTIONAL_BLOCK_ABSENT"
    return None


def _cite_keys(body: bytes) -> set:
    keys = set()
    for match in _CITE_RE.finditer(body):
        for raw in match.group(1).split(b","):
            key = raw.strip()
            if key:
                keys.add(key.decode("utf-8", errors="replace"))
    return keys


def _bib_keys(body: bytes) -> set:
    return {match.group(1).decode("utf-8", errors="replace") for match in _BIB_ENTRY_RE.finditer(body)}


def _first_occurrence_order(body: bytes, names: list) -> list:
    text = body.decode("utf-8", errors="replace")
    positions = []
    for name in names:
        idx = text.find(name)
        if idx != -1:
            positions.append((idx, name))
    positions.sort(key=lambda pair: pair[0])
    return [name for _, name in positions]


def _parse_chain_roles(body: bytes) -> dict:
    roles = {}
    for role, pattern in _CHAIN_ROLE_RE.items():
        match = pattern.search(body)
        roles[role.lower()] = match.group(1).decode("utf-8", errors="replace") if match else ""
    return roles


def item_lines(body: bytes) -> list[str]:
    """Public promotion of the `\\item` extraction `_gap_shape` used
    privately before this — `a-fact-is-declared-or-it-is-produced`,
    design.md Decision A: `paper_cli._resolve_expected_components`'s
    produced-fact route and `check_gap`'s own front extraction share this
    ONE definition, never a second parser. Every `\\item ...` line's text,
    stripped, in document order. Allowlist stays `{"re"}`; this reads only
    the bytes it is given, never disk (`ReadOnlyTests`)."""
    text = body.decode("utf-8", errors="replace")
    return [match.group(1).strip() for match in _ITEM_RE.finditer(text)]


def _gap_shape(body: bytes) -> dict:
    text = body.decode("utf-8", errors="replace")
    items = item_lines(body)
    closing_match = _CLOSING_RE.search(text)
    closing = closing_match.group(1).strip() if closing_match else None
    offset = closing_match.start(1) if closing_match else None
    return {"front": items, "closing": closing, "closing_offset": offset}


def check_contribution_list(evidence, *, optional_block_ids: frozenset = frozenset()) -> dict:
    """Coupling 1 (`coupling-verification` spec, `Requirement: Coupling 1
    — Contribution List Identity`). Declared: `record["facts"]
    ["contributions"]`, ordered. Derived, per block requiring the
    `contributions` fact: the order each declared name FIRST occurs in that
    block's own bytes. A name absent from a block's bytes fails the
    declared-name literal-presence limit distinctly from an order mismatch
    (`Requirement: Declared-Name Literal Presence Limit`) — both are
    reported, either alone flips the verdict to `fail`.

    Only a block that **enumerates** the contributions is held to the list:
    one whose bytes name at least one declared contribution literally. A
    block that requires the fact but names none of them (a title, an
    abstract's background, a related-work synthesis) only reads it, and is
    listed under `reading_blocks` instead of failing. A block naming some
    but not all of them still fails, and so does a paper in which no block
    enumerates the list at all.

    `optional_block_ids`: see `_optional_block_absence_reason`. Checked
    before `BLOCK_NOT_DECLARED` — a block absent because the paper never
    took that optional branch is a more precise explanation than "not
    declared", not a competing one.
    """
    block_ids, reason = evidence.blocks_by_fact.get("contributions", ((), "SECTION_CONTRACTS_UNREADABLE"))
    if reason is not None:
        return _unmeasured("contribution-list", "mechanical", reason)
    optional_reason = _optional_block_absence_reason(evidence, block_ids, optional_block_ids)
    if optional_reason is not None:
        return _unmeasured("contribution-list", "mechanical", optional_reason)

    declared_blocks = evidence.record.get("blocks", {})
    undeclared = [bid for bid in block_ids if bid not in declared_blocks]
    declared = evidence.record.get("facts", {}).get("contributions") or []
    if undeclared or not declared:
        return _unmeasured("contribution-list", "mechanical", "BLOCK_NOT_DECLARED",
                            evidence={"undeclared_blocks": undeclared})

    sides = [{"name": "facts.contributions", "source": "declared", "origin": "couplings.json"}]
    per_block_order = {}
    mismatched = []
    absent_from_bytes = []
    enumerating = []
    reading = []
    for block_id in block_ids:
        body = evidence.block_bodies.get(block_id, b"")
        order = _first_occurrence_order(body, list(declared))
        per_block_order[block_id] = order
        sides.append({
            "name": f"{block_id}:first-occurrence-order", "source": "derived",
            "origin": "main.tex block bytes",
        })
        if not order:
            reading.append(block_id)
            continue
        enumerating.append(block_id)
        for name in declared:
            if name not in order:
                absent_from_bytes.append({"block": block_id, "name": name})
        if order != list(declared):
            mismatched.append(block_id)

    verdict = "fail" if (mismatched or absent_from_bytes or not enumerating) else "pass"
    return _entry(
        "contribution-list", classification="mechanical", verdict=verdict, sides=sides,
        evidence={
            "declared": list(declared), "per_block_order": per_block_order,
            "mismatched_blocks": mismatched, "absent_from_bytes": absent_from_bytes,
            "enumerating_blocks": enumerating, "reading_blocks": reading,
        },
        limits=["ORDER_FROM_FIRST_OCCURRENCE"], unmeasured_reason=None,
    )


def check_chain(evidence, *, optional_block_ids: frozenset = frozenset()) -> dict:
    """Coupling 2 (`Requirement: Coupling 2 — Chain Word Identity`).
    Declared: one word per link (`record["chain"]["links"][i]["word"]`).
    Derived, per block requiring the `problem-statement` fact: the literal
    text found at each of the chain's five role-labeled lines
    (`Problem:`/`Contribution:`/`Property:`/`Instrument:`/`Evidence:`).
    Fails when the declared word is not literally present at every role
    (identity, never synonymy — M2), or when it is not itself a member of
    the declared contribution set (set closure against coupling 1's own
    declared list).

    The role-labeled form is optional prose: when no block requiring the
    fact carries any of the five labels, there is no chain to read and the
    check reports `unmeasured` with `CHAIN_ROLES_ABSENT` rather than failing
    every link. One label anywhere is enough to hold the whole chain to it.

    `optional_block_ids`: see `_optional_block_absence_reason`.
    """
    block_ids, reason = evidence.blocks_by_fact.get("problem-statement", ((), "SECTION_CONTRACTS_UNREADABLE"))
    if reason is not None:
        return _unmeasured("chain", "mechanical", reason)
    optional_reason = _optional_block_absence_reason(evidence, block_ids, optional_block_ids)
    if optional_reason is not None:
        return _unmeasured("chain", "mechanical", optional_reason)

    declared_blocks = evidence.record.get("blocks", {})
    undeclared = [bid for bid in block_ids if bid not in declared_blocks]
    links = evidence.record.get("chain", {}).get("links") or []
    if undeclared or not links:
        return _unmeasured("chain", "mechanical", "BLOCK_NOT_DECLARED",
                            evidence={"undeclared_blocks": undeclared})

    if not any(any(_parse_chain_roles(evidence.block_bodies.get(block_id, b"")).values())
               for block_id in block_ids):
        return _unmeasured("chain", "mechanical", "CHAIN_ROLES_ABSENT")

    declared_contributions = set(evidence.record.get("facts", {}).get("contributions") or [])
    sides = [{"name": "chain.links", "source": "declared", "origin": "couplings.json"}]
    per_link = []
    failed = False
    for block_id, link in zip(block_ids, links):
        body = evidence.block_bodies.get(block_id, b"")
        roles = _parse_chain_roles(body)
        sides.append({"name": f"{block_id}:roles", "source": "derived", "origin": "main.tex block bytes"})
        word = link.get("word", "")
        role_present = {role: (word in text) for role, text in roles.items()}
        closure_ok = word in declared_contributions
        link_ok = all(role_present.values()) and closure_ok
        if not link_ok:
            failed = True
        per_link.append({
            "block": block_id, "word": word, "roles_present": role_present, "closure": closure_ok,
        })

    verdict = "fail" if failed else "pass"
    return _entry(
        "chain", classification="mechanical", verdict=verdict, sides=sides,
        evidence={"links": per_link}, limits=["LITERAL_IDENTITY_ONLY"], unmeasured_reason=None,
    )


def check_gap(evidence, *, optional_block_ids: frozenset = frozenset()) -> dict:
    """Coupling 3 (`Requirement: Coupling 3 — The Gap Is Assisted`). Both
    sides are derived, sliced from the two `gap`-fact blocks' own bytes;
    nothing is declared. Mechanical sub-checks (both closings present,
    fronts equal, front counts equal) are published as named booleans; the
    "same thing at different depths" reading is never computed. The check's
    own top-level verdict is unconditionally `unmeasured`,
    `ASSISTED_READING_REQUIRED` — `holds`/`pass` is structurally absent from
    this check's own vocabulary (design.md, `the assisted payload publishes
    evidence, and its only verdict is unmeasured`): no mechanical
    sub-result, however clean, ever promotes it.

    `optional_block_ids`: see `_optional_block_absence_reason`. Checked
    ahead of the `len(block_ids) != 2` gate — even the "wrong number of gap
    blocks" reading is less precise than "the gap's optional half was never
    opened" when that is what actually happened.

    `a-fact-is-declared-or-it-is-produced` (design.md, Decision F): the pair
    is derived from `evidence.producers_by_fact` — the two blocks that
    PRODUCE `gap` (`related-work.rw-closing`, `introduction.block-3`) —
    never from the sibling consumer-scan mapping every OTHER check in this
    module still reads (every block that merely `requires_facts: [gap]`,
    which today also includes `experimental-setup.es-assessment` for an
    unrelated reason). Widening that sibling mapping instead of adding this
    separate one would silently misalign `check_chain`'s own
    `zip(block_ids, links)` (design.md: "a separate mapping was the only
    non-corrupting route").
    """
    block_ids, reason = evidence.producers_by_fact.get("gap", ((), "SECTION_CONTRACTS_UNREADABLE"))
    if reason is not None:
        return _unmeasured("gap", "assisted", reason)
    optional_reason = _optional_block_absence_reason(evidence, block_ids, optional_block_ids)
    if optional_reason is not None:
        return _unmeasured("gap", "assisted", optional_reason)
    if len(block_ids) != 2:
        return _unmeasured(
            "gap", "assisted", "BLOCK_NOT_DECLARED", evidence={"block_ids": list(block_ids)},
        )

    first_id, second_id = block_ids
    first_shape = _gap_shape(evidence.block_bodies.get(first_id, b""))
    second_shape = _gap_shape(evidence.block_bodies.get(second_id, b""))

    both_closings_present = first_shape["closing"] is not None and second_shape["closing"] is not None
    fronts_equal = first_shape["front"] == second_shape["front"]
    front_counts_equal = len(first_shape["front"]) == len(second_shape["front"])

    sides = [
        {"name": f"{first_id}:closing", "source": "derived", "origin": "main.tex block bytes"},
        {"name": f"{second_id}:closing", "source": "derived", "origin": "main.tex block bytes"},
        {"name": f"{first_id}:front", "source": "derived", "origin": "main.tex block bytes"},
        {"name": f"{second_id}:front", "source": "derived", "origin": "main.tex block bytes"},
    ]
    return _entry(
        "gap", classification="assisted", verdict="unmeasured", sides=sides,
        evidence={
            "closings": {first_id: first_shape["closing"], second_id: second_shape["closing"]},
            "closing_offsets": {
                first_id: first_shape["closing_offset"], second_id: second_shape["closing_offset"],
            },
            "fronts": {first_id: first_shape["front"], second_id: second_shape["front"]},
            "mechanical": {
                "both_closings_present": both_closings_present,
                "fronts_equal": fronts_equal,
                "front_counts_equal": front_counts_equal,
            },
            "depth_reading": "unmeasured",
        },
        limits=[], unmeasured_reason="ASSISTED_READING_REQUIRED",
    )


def check_artefacts(evidence, *, optional_block_ids: frozenset = frozenset()) -> dict:
    """Coupling 4 (`Requirement: Coupling 4 — Diagram Cell Disjointness`).
    Declared: `record["artefacts"]["setup_cells"]` / `["results_
    artefacts"]`. The methods-diagram side is never separately declared —
    it IS coupling 1's own declared contribution set, reused
    (design.md: "the list check 1 already bound to the document, never
    declared twice"). Fails on a results cell absent from the declared
    setup cells (M4a), or a non-empty intersection between the setup cells
    and the contribution set (M4b).

    `optional_block_ids`: threaded through to `check_contribution_list`,
    whose own `OPTIONAL_BLOCK_ABSENT` reason (if any) is what this check
    reports too, via the same "unmeasured passes through" path
    `BLOCK_NOT_DECLARED` already used before this change.
    """
    contribution_check = check_contribution_list(evidence, optional_block_ids=optional_block_ids)
    if contribution_check["verdict"] == "unmeasured":
        return _unmeasured("artefacts", "mechanical", contribution_check["unmeasured_reason"])

    artefacts = evidence.record.get("artefacts")
    if not artefacts:
        return _unmeasured("artefacts", "mechanical", "BLOCK_NOT_DECLARED")

    setup_cells = list(artefacts.get("setup_cells") or [])
    results_artefacts = list(artefacts.get("results_artefacts") or [])
    methods_cells = set(evidence.record.get("facts", {}).get("contributions") or [])

    undeclared_results = sorted(set(results_artefacts) - set(setup_cells))
    shared_with_methods = sorted(set(setup_cells) & methods_cells)

    verdict = "fail" if (undeclared_results or shared_with_methods) else "pass"
    return _entry(
        "artefacts", classification="mechanical", verdict=verdict,
        sides=[
            {"name": "artefacts.setup_cells", "source": "declared", "origin": "couplings.json"},
            {"name": "artefacts.results_artefacts", "source": "declared", "origin": "couplings.json"},
            {
                "name": "methods-diagram (== contribution-list)", "source": "derived",
                "origin": "check contribution-list",
            },
        ],
        evidence={
            "setup_cells": setup_cells, "results_artefacts": results_artefacts,
            "undeclared_results": undeclared_results, "shared_with_methods": shared_with_methods,
        },
        limits=[], unmeasured_reason=None,
    )


def check_future_work(evidence, *, optional_block_ids: frozenset = frozenset()) -> dict:
    """Coupling 5 (`Requirement: Coupling 5 — Future Work ⊆ Limitations`).
    Declared, both sides: `record["facts"]["limitations"]` and
    `record["future_work"]["directions"]`. Totality fails on a direction
    answering no declared limitation (M5). The shared citation key is
    checked against the union of `\\cite` keys across every block requiring
    the `limitations` fact, and against `refs.bib` — both derived.
    "Relevant subset" and "specific enough to be a paper" are published as
    `out-of-reach`, never attempted (`Requirement: Classification`).

    `optional_block_ids`: see `_optional_block_absence_reason`.
    """
    block_ids, reason = evidence.blocks_by_fact.get("limitations", ((), "SECTION_CONTRACTS_UNREADABLE"))
    if reason is not None:
        return _unmeasured("future-work", "mechanical", reason)
    optional_reason = _optional_block_absence_reason(evidence, block_ids, optional_block_ids)
    if optional_reason is not None:
        return _unmeasured("future-work", "mechanical", optional_reason)

    declared_blocks = evidence.record.get("blocks", {})
    undeclared = [bid for bid in block_ids if bid not in declared_blocks]
    future_work = evidence.record.get("future_work") or {}
    directions = future_work.get("directions") or []
    declared_limitations = evidence.record.get("facts", {}).get("limitations") or []
    if undeclared or not directions or not declared_limitations:
        return _unmeasured("future-work", "mechanical", "BLOCK_NOT_DECLARED",
                            evidence={"undeclared_blocks": undeclared})

    unanswered = [d["id"] for d in directions if d.get("limitation") not in declared_limitations]

    block_cite_keys: set = set()
    for block_id in block_ids:
        block_cite_keys |= _cite_keys(evidence.block_bodies.get(block_id, b""))
    bib_keys = _bib_keys(evidence.refs_bib_bytes)
    missing_cite = [
        d["id"] for d in directions
        if d.get("cite_key") not in block_cite_keys or d.get("cite_key") not in bib_keys
    ]

    verdict = "fail" if (unanswered or missing_cite) else "pass"
    return _entry(
        "future-work", classification="mechanical", verdict=verdict,
        sides=[
            {"name": "facts.limitations", "source": "declared", "origin": "couplings.json"},
            {"name": "future_work.directions", "source": "declared", "origin": "couplings.json"},
            {"name": "cite-keys", "source": "derived", "origin": "main.tex/refs.bib"},
        ],
        evidence={
            "declared_limitations": list(declared_limitations), "directions": list(directions),
            "unanswered": unanswered, "missing_cite": missing_cite,
            "relevance": "out-of-reach", "specificity": "out-of-reach",
        },
        limits=[], unmeasured_reason=None,
    )


def check_citations(evidence, *, optional_block_ids: frozenset = frozenset()) -> dict:
    """Check A (`citation-integrity` spec). Both sides derived from the
    document itself — no declaration anywhere. A dangling `\\cite` fails
    (M3a); an orphan `refs.bib` entry is reported, never failed (M3b) —
    exercised as two independent mutations, neither reading as proof of the
    other.

    `optional_block_ids` is accepted, unused, only for call-uniformity with
    the other six checks `run()` dispatches identically — this check's
    required evidence is never derived from `blocks_by_fact`, so no block's
    `optional` declaration can ever be relevant to it.
    """
    cite_keys = sorted(_cite_keys(evidence.main_tex_bytes))
    bib_keys = sorted(_bib_keys(evidence.refs_bib_bytes))
    dangling = sorted(set(cite_keys) - set(bib_keys))
    orphans = sorted(set(bib_keys) - set(cite_keys))
    verdict = "fail" if dangling else "pass"
    return _entry(
        "citations", classification="mechanical", verdict=verdict,
        sides=[
            {"name": "cite-keys", "source": "derived", "origin": "main.tex \\cite{...}"},
            {"name": "bib-entries", "source": "derived", "origin": "refs.bib @type{key,"},
        ],
        evidence={
            "cite_keys": cite_keys, "bib_keys": bib_keys, "dangling": dangling, "orphans": orphans,
        },
        limits=[], unmeasured_reason=None,
    )


def check_contract_currency(evidence, *, optional_block_ids: frozenset = frozenset()) -> dict:
    """Check B (`contract-currency` spec). `classification` is the literal
    two-word value the spec's own scenario states — `"out-of-reach today"`,
    distinct from the plain `"out-of-reach"` `coupling-verification`'s own
    enum otherwise uses for coupling 5's sub-parts (each spec's own literal
    wording, followed exactly).

    An absent OR empty `provenance` region reports `unmeasured`,
    `CONTRACT_RECORD_ABSENT` (M7) — never zero stale blocks, which would be
    indistinguishable from a genuinely current paper. When present, per-
    block staleness is `evidence.contract_drift`, already computed by
    `paper_coupling_evidence.gather` via `paper_provenance.drift` — this
    function never re-derives it, and never opens the contract file itself.

    `optional_block_ids` is accepted, unused, only for call-uniformity —
    this check reads `evidence.provenance`/`contract_drift`, never
    `blocks_by_fact`.
    """
    if evidence.provenance is None or not evidence.provenance["body"]["records"]:
        return _unmeasured("contract-currency", "out-of-reach today", "CONTRACT_RECORD_ABSENT")

    per_block = dict(evidence.contract_drift)
    stale = sorted(block_id for block_id, drifted in per_block.items() if drifted)
    verdict = "fail" if stale else "pass"
    return _entry(
        "contract-currency", classification="out-of-reach today", verdict=verdict,
        sides=[
            {
                "name": "provenance.records[*].contract_sha256", "source": "declared",
                "origin": "provenance region",
            },
            {
                "name": "contract file sha256", "source": "derived",
                "origin": "section contract file bytes",
            },
        ],
        evidence={"per_block_stale": per_block, "stale_blocks": stale},
        limits=[], unmeasured_reason=None,
    )


def check_figure_semantics(evidence, *, optional_block_ids: frozenset = frozenset()) -> dict:
    """Check C (`a-diagram-that-compiles-or-says-why`'s semantic half).

    Reads ONLY the already-computed `evidence.figure_semantics` dict that
    `paper_coupling_evidence.gather()` stored. It imports nothing, opens
    nothing, and touches no `Path`-typed field — the invocation moved into
    the reader precisely so this module's import allowlist could stay at
    `re` rather than being widened to admit `json` and the auditor.

    A manifest component the section prose never names is the
    phantom-component case; a `components_from` step absent from both the
    manifest and the prose is the missing-stage case. Both are `fail`. An
    audit that could not compare anything is `unmeasured`, never `pass` —
    the third value exists exactly so "could not check" is not reported as
    agreement.

    `optional_block_ids` is accepted, unused, only for call-uniformity with
    the other seven checks `run()` dispatches identically — this check's
    required evidence is `evidence.figure_semantics`, never
    `blocks_by_fact`, so no block's `optional` declaration can ever be
    relevant to it.
    """
    semantics = evidence.figure_semantics
    if semantics is None:
        return _unmeasured("figure-semantics", "mechanical", "NO_FIGURE_DECLARED")

    if semantics.get("verdict") == "unmeasured":
        return _unmeasured(
            "figure-semantics", "mechanical", "FIGURE_SEMANTICS_UNMEASURED",
            evidence={"figures": semantics.get("figures", {})},
        )

    return _entry(
        "figure-semantics", classification="mechanical",
        verdict=semantics.get("verdict", "unmeasured"),
        sides=[
            {
                "name": "figure manifest components", "source": "declared",
                "origin": "paper/Figures/<id>.diagram.json",
            },
            {"name": "section prose", "source": "derived", "origin": "sections/*.md bodies"},
        ],
        evidence={"figures": semantics.get("figures", {})},
        limits=[], unmeasured_reason=None,
    )


_BACK_MATTER_BEGIN_RE = re.compile(
    rb"^%% paper-writing block (back-matter\.[A-Za-z0-9._-]+) begin\b", re.MULTILINE
)
#: Where the reference list is typeset: a BibTeX `\bibliography{...}`, a
#: hand-written `thebibliography` environment, or biblatex's
#: `\printbibliography`. Anchored at the line start (after indentation), so
#: a commented-out command never counts.
_REFERENCES_RE = re.compile(
    rb"^[ \t]*\\(?:bibliography\{|begin\{thebibliography\}|printbibliography\b)", re.MULTILINE
)
#: The back-matter blocks that follow the references; every other
#: back-matter block is a declaration and precedes them
#: (`sections/10-back-matter.md`, "Placement follows the venue").
APPENDIX_BLOCKS: frozenset = frozenset({"back-matter.bm-appendices"})


def check_back_matter_order(evidence, *, optional_block_ids: frozenset = frozenset()) -> dict:
    """`back-matter-order` (`odd/tasks/manuscript-polish-0-54.md`, S3): back
    matter renders after the conclusions and BEFORE the references, and
    appendices AFTER them. Both sides are derived from `main.tex` itself:
    the begin marker of every `back-matter.*` block, and the first line that
    typesets the references. A declaration block beginning after that line
    fails, and so does an appendix block beginning before it. No
    bibliography at all is `unmeasured`, `NO_BIBLIOGRAPHY` -- never `pass`.

    Reports; never repairs: the canonical file is reordered by moving the
    blocks, and `venue build` always emits this order whatever the
    canonical file holds.

    `optional_block_ids` is accepted, unused, only for call-uniformity."""
    data = evidence.main_tex_bytes
    blocks = [(m.group(1).decode("ascii"), m.start()) for m in _BACK_MATTER_BEGIN_RE.finditer(data)]
    references = _REFERENCES_RE.search(data)
    if references is None:
        return _unmeasured("back-matter-order", "mechanical", "NO_BIBLIOGRAPHY",
                           evidence={"back_matter_blocks": [block_id for block_id, _ in blocks]})
    at = references.start()
    late = [block_id for block_id, start in blocks if block_id not in APPENDIX_BLOCKS and start > at]
    early = [block_id for block_id, start in blocks if block_id in APPENDIX_BLOCKS and start < at]
    return _entry(
        "back-matter-order", classification="mechanical",
        verdict="fail" if late or early else "pass",
        sides=[
            {"name": "back-matter block begin markers", "source": "derived", "origin": "main.tex"},
            {"name": "reference list", "source": "derived",
             "origin": "main.tex \\bibliography / thebibliography / \\printbibliography"},
        ],
        evidence={
            "references_line": data.count(b"\n", 0, at) + 1,
            "declarations_after_references": late,
            "appendices_before_references": early,
        },
        limits=[], unmeasured_reason=None,
    )


def check_language(evidence, *, optional_block_ids: frozenset = frozenset(),
                   language: dict | None = None) -> dict:
    """Check D (spec S4 of `odd/tasks/manuscript-polish-0-54.md`): the
    manuscript is English unless the paper declares another language, and
    carries no placeholder text.

    `language` is `paper_language.scan` over `evidence.main_tex_bytes`,
    resolved one level up in `cmd_verify` -- this module imports nothing
    beyond `re` (`ReadOnlyTests`' allowlist), the same reason
    `optional_block_ids` is resolved there. Absent, the check reports
    `unmeasured`/`LANGUAGE_NOT_SCANNED`, never a silent pass. A Spanish
    line or a placeholder marker fails; a paper declaring a non-English
    main language is judged on placeholders only.

    `optional_block_ids` is accepted, unused, only for call-uniformity.
    """
    if language is None:
        return _unmeasured("language", "mechanical", "LANGUAGE_NOT_SCANNED")
    spanish = list(language.get("spanish", []))
    placeholders = list(language.get("placeholders", []))
    return _entry(
        "language", classification="mechanical",
        verdict="fail" if spanish or placeholders else "pass",
        sides=[
            {"name": "main.tex prose", "source": "derived",
             "origin": "main.tex outside math, comments, markers and non-prose environments"},
            {"name": "manuscript language", "source": "derived",
             "origin": "babel/polyglossia main language, English when undeclared"},
        ],
        evidence={"language": language.get("language", "english"),
                  "spanish": spanish, "placeholders": placeholders},
        limits=[], unmeasured_reason=None,
    )


def check_references(evidence, *, optional_block_ids: frozenset = frozenset(),
                     references: dict | None = None) -> dict:
    """Coverage of `paper/.paper-writing/references.json`: every cited key has
    a record. `references` is that file's `{cite_key: record}`, read one level
    up in `cmd_verify` for the reason `check_language` gives; absent means no
    record at all. A key `resolve --references` could not resolve still has a
    record, so it passes with a note in `limits`: offline work is never
    blocked, and an abstract is never required.

    `optional_block_ids` is accepted, unused, only for call-uniformity.
    """
    records = references or {}
    cited = sorted(_cite_keys(evidence.main_tex_bytes))
    statuses = {key: records[key].get("status") for key in cited if isinstance(records.get(key), dict)}
    missing = [key for key in cited if statuses.get(key) not in _REFERENCE_STATUSES]
    not_found = [key for key in cited if statuses.get(key) == "not_found"]
    unreachable = [key for key in cited if statuses.get(key) == "unreachable"]
    without_abstract = [key for key in cited if statuses.get(key) == "resolved"
                        and not records[key].get("abstract")]
    unresolved = len(not_found) + len(unreachable)
    return _entry(
        "references", classification="mechanical", verdict="fail" if missing else "pass",
        sides=[
            {"name": "cite-keys", "source": "derived", "origin": "main.tex \\cite{...}"},
            {"name": "reference-records", "source": "derived",
             "origin": ".paper-writing/references.json, written by resolve --references"},
        ],
        evidence={"cited": cited, "missing": missing, "not_found": not_found,
                  "unreachable": unreachable, "without_abstract": without_abstract},
        limits=[f"{unresolved} cited key(s) have a record but no resolved metadata"] if unresolved else [],
        unmeasured_reason=None,
    )


#: Blocks that open a paragraph of their own: the future-work block closes the
#: conclusions as their last paragraph, and every declaration is a paragraph.
#: Their markers are comments, so a block that follows another with no blank
#: line in between would run into its last paragraph.
OWN_PARAGRAPH_BLOCKS: frozenset = frozenset({
    "conclusions.concl-block-4",
    "back-matter.bm-author-contributions", "back-matter.bm-funding",
    "back-matter.bm-data-availability", "back-matter.bm-code-availability",
    "back-matter.bm-ethics-statement", "back-matter.bm-informed-consent",
    "back-matter.bm-conflicts-of-interest", "back-matter.bm-acknowledgments",
})
_ANY_BEGIN_RE = re.compile(rb"^%% paper-writing block ([\w.-]+) begin[^\n]*\n", re.M)
_SECTIONING_LINE_RE = re.compile(rb"^\s*\\(?:part|chapter|section|subsection|subsubsection)\*?\s*[\[{]")


def _opens_paragraph(data: bytes, begin: int, body_start: int) -> bool:
    """Whether the body starting at `body_start` opens a paragraph: its own
    first line is blank, or the last non-comment line before the begin marker
    is blank, a sectioning command, or the start of the file."""
    if data[body_start:body_start + 1] == b"\n":
        return True
    before = data[:begin].split(b"\n")[:-1]
    for line in reversed(before):
        stripped = line.strip()
        if stripped.startswith(b"%"):
            continue
        return not stripped or bool(_SECTIONING_LINE_RE.match(line))
    return True


def check_own_paragraph(evidence, *, optional_block_ids: frozenset = frozenset()) -> dict:
    """`own-paragraph`: every block in `OWN_PARAGRAPH_BLOCKS` present in
    `main.tex` opens a paragraph of its own. Reports the blocks that run into
    the paragraph before them; never repairs (`write` and `humanize --apply`
    open those bodies on a blank line).

    `optional_block_ids` is accepted, unused, only for call-uniformity."""
    data = evidence.main_tex_bytes
    checked, run_on = [], []
    for match in _ANY_BEGIN_RE.finditer(data):
        block_id = match.group(1).decode("ascii")
        if block_id not in OWN_PARAGRAPH_BLOCKS:
            continue
        checked.append(block_id)
        if not _opens_paragraph(data, match.start(), match.end()):
            run_on.append(block_id)
    return _entry(
        "own-paragraph", classification="mechanical",
        verdict="fail" if run_on else "pass",
        sides=[{"name": "own-paragraph block begin markers", "source": "derived", "origin": "main.tex"}],
        evidence={"checked": checked, "run_on": run_on},
        limits=[], unmeasured_reason=None,
    )


#: One printed page of the body, in words of prose; a display equation counts
#: as `_EQUATION_WORDS` and a table row as `_ROW_WORDS`. An appendix at or
#: under one page belongs in the body section that needs it.
PAGE_WORDS = 550
_EQUATION_WORDS = 40
_ROW_WORDS = 15
_APPENDIX_BLOCK = b"back-matter.bm-appendices"
#: One whole display: an equation-like environment, `\[ … \]` or `$$ … $$`,
#: so each counts once whatever its delimiters.
_DISPLAY_RE = re.compile(rb"\\begin\{(equation|align|gather|multline|eqnarray)\*?\}.*?\\end\{\1\*?\}"
                         rb"|\\\[.*?\\\]|\$\$.*?\$\$", re.S)
_TABULAR_RE = re.compile(rb"\\begin\{(?:tabular|tabularx|longtable)\*?\}(.*?)\\end\{(?:tabular|tabularx|longtable)\*?\}", re.S)
_MATH_RE = re.compile(rb"\\begin\{(equation|align|gather|multline|eqnarray)\*?\}.*?\\end\{\1\*?\}|\\\[.*?\\\]|\$\$.*?\$\$|\$[^$]*\$", re.S)
_WORD_RE = re.compile(rb"[A-Za-z][A-Za-z'-]+")
_COMMAND_RE = re.compile(rb"\\[A-Za-z@]+\*?")


def check_appendix_length(evidence, *, optional_block_ids: frozenset = frozenset()) -> dict:
    """`appendix-length`: an appendix that prints in one page or less is not an
    appendix -- its content goes into the body section that needs it,
    Materials and Methods for a derivation or a formal detail, the
    experimental set-up for a table of settings. The extent is estimated
    from the source: prose words, plus `_EQUATION_WORDS` per display
    equation and `_ROW_WORDS` per table row, against `PAGE_WORDS`. No
    appendix, or an empty one, passes.

    `optional_block_ids` is accepted, unused, only for call-uniformity."""
    data = evidence.main_tex_bytes
    begin = re.search(rb"^%% paper-writing block " + re.escape(_APPENDIX_BLOCK) + rb" begin[^\n]*\n", data, re.M)
    end = re.search(rb"^%% paper-writing block " + re.escape(_APPENDIX_BLOCK) + rb" end", data, re.M)
    body = data[begin.end():end.start()] if begin and end and end.start() > begin.end() else b""
    body = b"\n".join(line for line in body.split(b"\n") if not line.strip().startswith(b"%"))
    tables = _TABULAR_RE.findall(body)
    rows = sum(table.count(b"\\\\") for table in tables)
    equations = len(_DISPLAY_RE.findall(body))
    prose = _COMMAND_RE.sub(b" ", _TABULAR_RE.sub(b" ", _MATH_RE.sub(b" ", body)))
    words = len(_WORD_RE.findall(prose))
    extent = words + _EQUATION_WORDS * equations + _ROW_WORDS * rows
    present = bool(words or equations or rows)
    short = present and extent <= PAGE_WORDS
    move_to = None
    if short:
        move_to = "experimental-setup" if rows and not equations else "materials-and-methods"
    return _entry(
        "appendix-length", classification="mechanical",
        verdict="fail" if short else "pass",
        sides=[{"name": "appendix block body", "source": "derived", "origin": "main.tex"},
               {"name": "one printed page", "source": "derived", "origin": f"{PAGE_WORDS} words"}],
        evidence={"present": present, "words": words, "display_equations": equations,
                  "table_rows": rows, "estimated_words": extent, "page_words": PAGE_WORDS,
                  "move_to": move_to},
        limits=["the extent is estimated from the source; the compiled PDF is the final measure"],
        unmeasured_reason=None,
    )


_STRUCTURE_FUNCTIONS = {"back-matter-order": check_back_matter_order,
                        "own-paragraph": check_own_paragraph,
                        "appendix-length": check_appendix_length}
assert set(_STRUCTURE_FUNCTIONS) == set(STRUCTURE_CHECKS), "every STRUCTURE_CHECKS member needs one function"


_CHECK_FUNCTIONS = {
    "contribution-list": check_contribution_list,
    "chain": check_chain,
    "gap": check_gap,
    "artefacts": check_artefacts,
    "future-work": check_future_work,
    "citations": check_citations,
    "contract-currency": check_contract_currency,
    "figure-semantics": check_figure_semantics,
    "language": check_language,
    "references": check_references,
}
assert set(_CHECK_FUNCTIONS) == set(CHECKS), "every CHECKS member needs exactly one function, and the reverse"


def run(evidence, *, optional_block_ids: frozenset = frozenset(), language: dict | None = None,
        references: dict | None = None) -> dict:
    """Assemble the full report: one object per `CHECKS` member, in both
    directions (`ReportShapeTests`). `holds + fails + unmeasured ==
    len(CHECKS)` always; `unmeasured` is never counted in `holds` — held by
    the arithmetic below, not by prose.

    `optional_block_ids`: raw (unqualified) block ids declared
    `optional: true` in their section contract, threaded unchanged into
    every check (`optional-block-semantics` spec). Defaults to an empty
    `frozenset()` — today's only real caller resolves no such set (deriving
    it needs `paper_graph.assemble_corpus` over the same `sections_dir`
    `gather()` already read, wiring left to whichever caller owns that
    corpus read; this module touches disk never, by its own AST lock), so
    behaviour is byte-identical to before this parameter existed until a
    caller passes real values.

    `language`: `paper_language.scan` over `main.tex`, handed only to
    `check_language` (spec S4); `None` reports that check `unmeasured`.

    `references`: the sidecar's `{cite_key: record}`, handed only to
    `check_references`; `None` is a paper with no sidecar.
    """
    inputs = {"language": {"language": language}, "references": {"references": references}}
    entries = [
        _CHECK_FUNCTIONS[check](evidence, optional_block_ids=optional_block_ids, **inputs.get(check, {}))
        for check in CHECKS
    ]
    holds = sum(1 for entry in entries if entry["verdict"] == "pass")
    fails = sum(1 for entry in entries if entry["verdict"] == "fail")
    unmeasured = sum(1 for entry in entries if entry["verdict"] == "unmeasured")
    assert holds + fails + unmeasured == len(CHECKS)
    # Structural checks sit apart from the coupling roster and its counts;
    # a manuscript is clean only when every one of them passes as well.
    structure = [_STRUCTURE_FUNCTIONS[check](evidence, optional_block_ids=optional_block_ids)
                 for check in STRUCTURE_CHECKS]
    structure_clean = all(entry["verdict"] == "pass" for entry in structure)
    return {
        "checks": entries, "clean": (fails == 0 and unmeasured == 0 and structure_clean),
        "holds": holds, "fails": fails, "unmeasured": unmeasured,
        "structure": structure,
    }
