"""paper_reorder: move canonical back-matter blocks into the order `verify`
expects (#184 item 4, `odd/tasks/daprosero-backlog.md` S6.4).

`verify`'s `back-matter-order` check (`paper_verify.check_back_matter_order`)
reports a declaration block (`back-matter.*`, not an appendix) that begins
after the reference list, and an appendix block (`paper_verify.
APPENDIX_BLOCKS`) that begins before it. This module owns no ordering rule
of its own: it asks that check which blocks are out of place, using the
same reference-list pattern, and moves exactly those blocks:

- a misplaced declaration goes immediately before the reference list's
  first line, after any declaration already there;
- a misplaced appendix goes immediately after the reference list's last
  line (`\\end{thebibliography}` for a hand-written list).

Moves are byte-preserving: a block's region (begin marker through end
marker, its own newline included) is cut and inserted whole, every byte
outside every block keeps its order (`paper_block.identity_invariant`), and
every block keeps its bytes. The moved candidate must pass the check before
anything is written; the write reuses `paper_block.commit_candidate` (the
same `TEX_MOVED` compare-and-swap, pre-image and atomic replace
`substitute` uses).

Refuses `REORDER_LAYOUT_AMBIGUOUS` when the layout gives no single place to
move a block to: no reference list, more than one, a reference list inside a
block, a hand-written list with no `\\end{thebibliography}`, or a block to
move whose end marker is the file's last line without a newline.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paper_block  # noqa: E402
import paper_verify  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_core" / "implementation"))
from impl_refusals import Refused  # noqa: E402

_THEBIBLIOGRAPHY_END_RE = re.compile(rb"^[ \t]*\\end\{thebibliography\}", re.MULTILINE)
#: A `\bibliographystyle{...}` line directly above the reference list belongs
#: to it: a declaration moved before the list goes above that line too.
_BIBLIOGRAPHYSTYLE_LINE_RE = re.compile(rb"[ \t]*\\bibliographystyle\{[^\n]*\n\Z")


def _order_check(data: bytes) -> dict:
    return paper_verify.check_back_matter_order(SimpleNamespace(main_tex_bytes=data))


def _line_end(data: bytes, pos: int) -> int:
    newline = data.find(b"\n", pos)
    return len(data) if newline == -1 else newline + 1


def _line_number(data: bytes, pos: int) -> int:
    return data.count(b"\n", 0, pos) + 1


def _ambiguous(detail: str) -> Refused:
    return Refused("REORDER_LAYOUT_AMBIGUOUS", detail)


def _reference_span(data: bytes, regions: dict) -> tuple[int, int]:
    """`(start, end)` of the one reference list: its first line's start and
    its last line's end. Refuses when there is not exactly one, or when
    either end sits inside a block region."""
    matches = list(paper_verify._REFERENCES_RE.finditer(data))
    if not matches:
        raise _ambiguous(
            "no reference list (\\bibliography, thebibliography or \\printbibliography) in main.tex, "
            "so there is no place to order back matter around"
        )
    if len(matches) > 1:
        lines = ", ".join(str(_line_number(data, m.start())) for m in matches)
        raise _ambiguous(f"{len(matches)} reference lists in main.tex (lines {lines}); keep one, then reorder")
    start = matches[0].start()
    list_start = start
    previous = data.rfind(b"\n", 0, max(start - 1, 0)) + 1 if start else 0
    if start and _BIBLIOGRAPHYSTYLE_LINE_RE.match(data[previous:start]):
        list_start = previous
    if b"thebibliography" in matches[0].group(0):
        closing = _THEBIBLIOGRAPHY_END_RE.search(data, start)
        if closing is None:
            raise _ambiguous(
                f"the thebibliography environment at line {_line_number(data, start)} has no "
                "\\end{thebibliography}"
            )
        end = _line_end(data, closing.start())
    else:
        end = _line_end(data, start)
    for block_id, (region_start, region_end) in regions.items():
        if region_start <= list_start < region_end or region_start < end <= region_end:
            raise _ambiguous(
                f"the reference list at line {_line_number(data, start)} sits inside block {block_id!r}; "
                "move it out of the block by hand, then reorder"
            )
    return list_start, end


def plan(data: bytes) -> dict:
    """Pure: the moves that put `data`'s back matter in the checked order
    and the candidate bytes they produce. Never touches disk."""
    parsed = paper_block.parse(data)
    regions = {
        block_id: (begin["start"], end["end"]) for block_id, (begin, end) in parsed.pairs.items()
    }
    before = _order_check(data)
    if before["verdict"] == "pass":
        return {"moves": [], "candidate": data, "verdict": "pass"}

    refs_start, refs_end = _reference_span(data, regions)
    late = before["evidence"]["declarations_after_references"]
    early = before["evidence"]["appendices_before_references"]
    moving = sorted(late + early, key=lambda block_id: regions[block_id][0])
    for block_id in moving:
        region_start, region_end = regions[block_id]
        if not data[region_start:region_end].endswith(b"\n"):
            raise _ambiguous(
                f"block {block_id!r} ends the file without a newline; moving it would join two lines"
            )

    to_before = b"".join(data[slice(*regions[b])] for b in moving if b in late)
    to_after = b"".join(data[slice(*regions[b])] for b in moving if b in early)
    events = sorted(
        [(regions[b][0], regions[b][1], b"") for b in moving]
        + [(refs_start, refs_start, to_before), (refs_end, refs_end, to_after)],
        key=lambda event: (event[0], event[1]),
    )
    out = bytearray()
    cursor = 0
    for start, end, payload in events:
        out += data[cursor:start]
        out += payload
        cursor = end
    out += data[cursor:]
    candidate = bytes(out)

    moves = [
        {
            "block": block_id,
            "from_line": _line_number(data, regions[block_id][0]),
            "to": "before-references" if block_id in late else "after-references",
        }
        for block_id in moving
    ]
    return {"moves": moves, "candidate": candidate, "verdict": _order_check(candidate)["verdict"]}


def _prove_byte_preserving(pre: bytes, candidate: bytes) -> None:
    """Every byte outside every block keeps its order, and every block keeps
    its own bytes; `SUBSTITUTION_NOT_LOCAL` otherwise (a defect, never
    ordinary use)."""
    paper_block.identity_invariant(pre, candidate)
    pre_pairs = paper_block.parse(pre).pairs
    new_pairs = paper_block.parse(candidate).pairs
    if set(pre_pairs) != set(new_pairs) or any(
        pre[pre_pairs[b][0]["start"]:pre_pairs[b][1]["end"]]
        != candidate[new_pairs[b][0]["start"]:new_pairs[b][1]["end"]]
        for b in pre_pairs
    ):
        raise Refused("SUBSTITUTION_NOT_LOCAL", "a moved block would not keep its own bytes")


def reorder(paper_dir: Path, *, apply: bool = False) -> dict:
    """Report (default) or apply the moves `plan` derives for
    `<paper_dir>/main.tex`. Already in order: no moves, nothing written, so
    a second `--apply` is a no-op."""
    tex_path = paper_block.resolve_main_tex(paper_dir)
    pre = tex_path.read_bytes()
    result = plan(pre)
    changed = bool(result["moves"])
    if changed:
        if result["verdict"] != "pass":
            raise _ambiguous(
                "moving the misplaced blocks would still not satisfy back-matter-order; reorder by hand"
            )
        _prove_byte_preserving(pre, result["candidate"])
    applied = False
    if apply and changed:
        paper_block.commit_candidate(paper_dir, tex_path, pre, result["candidate"])
        applied = True
    return {
        "moves": result["moves"],
        "changed": changed,
        "applied": applied,
        "back_matter_order": result["verdict"],
    }
