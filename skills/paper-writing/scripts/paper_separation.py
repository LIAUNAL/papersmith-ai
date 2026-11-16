"""paper_separation: the pure core of the whole-cut review, design.md
Decisions B and D.

Two functions, no I/O, no CLI wiring, no persistence, no corpus assembly --
a caller resolves an outline and an anchored claim map first, and this
module answers two questions about them: which sections a block may claim
at all, and how badly a proposed cut breaks the document's own structure.

Public surface:

    claimable_sections(outline)              -> {"state", "level", "titles", "reason"}
    score_cut(claimable, claims_by_block)    -> {"orphan", "overlap", "gap", "total"}
"""
from __future__ import annotations


def claimable_sections(outline: dict) -> dict:
    """Decision B: eliminate root spans to a fixed point, then take every
    remaining heading at the shallowest remaining level, ordered by
    `byte_start`.

    `outline` is `paper_guidance.segment_markdown`'s own return shape --
    `{"headings": [...]}`, each heading carrying `{title, level,
    byte_start, byte_end}`, or `{"headings": [], "reason": "NO_HEADINGS"}`
    for a document with no ATX heading at all.

    A heading `H` is a root span iff every OTHER remaining heading's
    `byte_start` lies strictly inside `[H.byte_start, H.byte_end)` -- it
    contains all of them, so it partitions nothing. A lone remaining
    heading is never eliminated, though: "every other remaining heading"
    is an empty set, so it is vacuously a root span, and dropping it would
    leave a single-section document (an ingested dataset page) with no
    claimable section at all, a source no block could ever bind (issue
    #184 item 6). The last section standing is the whole document's one
    claimable section; a title wrapping two or more sections is still
    eliminated, as before.

    No heading-level literal governs this computation anywhere: the only
    comparison against a level is against `shallowest`, itself derived
    from whatever remains after elimination -- never a hardcoded bound. A
    document nested one level deeper, or one level shallower, needs no
    edit here.

    Returns `{"state": "measured"|"unmeasured", "level": int|None,
    "titles": tuple, "reason": str|None}`. `state` is `"unmeasured"` when
    the document carries no heading at all, or when elimination leaves
    nothing behind -- reporting a claimable set and exiting 0 in either
    case would let a cut pass because nothing was actually measured.
    """
    headings = outline.get("headings") or []
    if not headings:
        reason = outline.get("reason", "NO_HEADINGS")
        return {"state": "unmeasured", "level": None, "titles": (), "reason": reason}

    remaining = _eliminate_root_spans(headings)
    if not remaining:
        return {"state": "unmeasured", "level": None, "titles": (), "reason": "ALL_ROOT_SPANS"}

    shallowest = min(heading["level"] for heading in remaining)
    claimable = sorted(
        (heading for heading in remaining if heading["level"] == shallowest),
        key=lambda heading: heading["byte_start"],
    )
    return {
        "state": "measured",
        "level": shallowest,
        "titles": tuple(heading["title"] for heading in claimable),
        "reason": None,
    }


def _eliminate_root_spans(headings: list) -> list:
    """One iteration drops every heading that is a root span AGAINST the
    snapshot the iteration started from, then repeats against what is
    left -- the fixed point Decision B names. Identity (`id`), not value
    equality, decides membership in the removal set, so two headings that
    happen to carry identical title/level/byte-range text (impossible in
    practice, since two headings cannot start at the same byte offset)
    could never be confused for one another regardless."""
    remaining = list(headings)
    while remaining:
        root_span_ids = {
            id(heading)
            for heading in remaining
            if all(
                heading["byte_start"] < other["byte_start"] < heading["byte_end"]
                for other in remaining
                if other is not heading
            )
        }
        if not root_span_ids or len(root_span_ids) == len(remaining):
            # Nothing to drop, or dropping would empty the set: only a lone
            # heading is a root span of itself, and it is the one section left.
            return remaining
        remaining = [heading for heading in remaining if id(heading) not in root_span_ids]
    return remaining


def score_cut(claimable: tuple, claims_by_block: dict) -> dict:
    """Decision D, defined once. `claimable` is the ordered claimable set
    (`claimable_sections(...)["titles"]`); `claims_by_block` maps each
    block id to the titles it claims -- already anchored by the caller,
    since this function has no corpus to check anything against. A title
    named in `claims_by_block` that is not itself in `claimable` (an
    unanchored assignment's title, or one resolved outside the claimable
    set entirely) is silently excluded from every count below: it clears
    no orphan and can create neither an overlap nor a gap.

    - **orphan**: every claimable title no block's claims name at all.
    - **overlap**: per title, `k - 1` where `k` is the number of DISTINCT
      blocks claiming it (0 when claimed by 0 or 1 block). Two blocks on
      one title cost 1; three cost 2 -- ambiguous at k >= 3 in the
      proposal's own telling; this is the ruling.
    - **gap**: per block, every claimable title strictly between that
      block's own minimum and maximum claimed title (by document order)
      that the block itself does not claim. A block claiming zero or one
      title can never contribute a gap.
    - **total**: `orphan + overlap + gap`. Lower is better; equal totals
      are not a regression, because nothing else is ranked.

    Returns `{"orphan": [title, ...], "overlap": [{"title", "blocks",
    "count"}, ...], "gap": [{"block", "title"}, ...], "total": int}` --
    every list names instances, so a refusal built from this can name
    every defect rather than the first.
    """
    index = {title: position for position, title in enumerate(claimable)}
    claimants: dict = {title: [] for title in claimable}
    for block, titles in claims_by_block.items():
        for title in titles:
            if title in claimants:
                claimants[title].append(block)

    orphan = [title for title in claimable if not claimants[title]]

    overlap = []
    overlap_total = 0
    for title in claimable:
        blocks = claimants[title]
        k = len(blocks)
        if k > 1:
            count = k - 1
            overlap.append({"title": title, "blocks": tuple(sorted(blocks)), "count": count})
            overlap_total += count

    gap = []
    for block, titles in claims_by_block.items():
        claimed_indices = sorted(index[title] for title in titles if title in index)
        if len(claimed_indices) < 2:
            continue
        lo = claimed_indices[0]
        hi = claimed_indices[-1]
        claimed_set = set(claimed_indices)
        for position in range(lo + 1, hi):
            if position not in claimed_set:
                gap.append({"block": block, "title": claimable[position]})

    total = len(orphan) + overlap_total + len(gap)
    return {"orphan": orphan, "overlap": overlap, "gap": gap, "total": total}
