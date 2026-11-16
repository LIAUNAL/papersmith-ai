"""paper_block: marker grammar, locate, substitute, invariant.

Delimits, locates, replaces and refuses over named blocks inside a
`main.tex`-shaped file, byte-for-byte. Block ids are opaque here — shape
only (`[A-Za-z0-9._-]+`), no semantics; their grammar and ordering belong to
a sibling change. All I/O is binary end to end: universal-newlines text mode
would rewrite every CRLF in the file and break the byte-identity invariant
silently, which is exactly the failure this module exists to prevent.

Public surface, disk-touching functions first (the ones `paper_cli.py` wires
directly):

    read_status(paper_dir)   -> dict              (resolves main.tex, hands
                                                     its bytes to status())
    open_block(paper_dir, block_id, ...) -> dict   (impure; end to end)
    substitute(paper_dir, block_id, ...) -> dict   (impure; end to end)

And the pure engine underneath, reusable without touching disk:

    parse(data)              -> ParsedDocument   (raises TEX_UNDECODABLE,
                                                    MARKER_MALFORMED,
                                                    BLOCK_UNPAIRED,
                                                    BLOCK_DUPLICATED,
                                                    BLOCK_NESTED)
    project(data)             -> bytes            (independent re-derivation:
                                                     re-parses from scratch and
                                                     strips every block region)
    status(data)              -> dict              (read-only block table)
    resolve_main_tex(paper_dir) -> Path            (raises PAPER_ABSENT,
                                                      PAPER_NOT_A_DIRECTORY)
    validate_block_id(id)     -> None              (raises BLOCK_ID_MALFORMED)
    build_candidate(...)      -> (bytes, bytes)     (pure; the in-memory half
                                                       of substitute's 9-step
                                                       algorithm)
    build_open_candidate(...) -> bytes              (pure; the in-memory half
                                                       of open)
    identity_invariant(...)   -> None               (raises SUBSTITUTION_NOT_LOCAL)
    check_expected_digest(...) -> None              (raises BLOCK_CHANGED_SINCE_READ)
    check_base_digest(paper_dir, block_id, expected) -> None (disk-reading
                                                       twin of the above)
    commit_candidate(...)     -> None               (CAS, pre-image, atomic
                                                       replace; raises TEX_MOVED)
"""
from __future__ import annotations

import hashlib
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paper_region  # noqa: E402
import paper_provenance  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_core" / "implementation"))
from impl_refusals import Refused  # noqa: E402

#: The exact prefix every marker-shaped line starts with. A line matching
#: this prefix that does not match the full grammar below refuses
#: `MARKER_MALFORMED` rather than being silently treated as prose — a marker
#: typo is exactly the case this check exists to catch, not to swallow.
MARKER_PREFIX = b"%% paper-writing block"

_ID = rb"[A-Za-z0-9._-]+"
_HEX64 = rb"[0-9a-f]{64}"
_BEGIN_RE = re.compile(rb"^%% paper-writing block (?P<id>" + _ID + rb") begin sha256=(?P<digest>" + _HEX64 + rb")$")
_END_RE = re.compile(rb"^%% paper-writing block (?P<id>" + _ID + rb") end$")

#: Text-mode twin of `_ID`, for validating a caller-supplied `--block <id>`
#: before it is used to look anything up. Shape only, per this module's own
#: docstring — a sibling change owns meaning.
_BLOCK_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def validate_block_id(block_id: str) -> None:
    """Refuses `BLOCK_ID_MALFORMED` (invocation-defect) when `block_id` does
    not match the shape grammar `[A-Za-z0-9._-]+`. The caller can clear this
    by changing the invocation alone, which is what makes it invocation
    rather than work-state.
    """
    if not _BLOCK_ID_RE.match(block_id):
        raise Refused(
            "BLOCK_ID_MALFORMED",
            f"{block_id!r} does not match the required shape [A-Za-z0-9._-]+",
        )


def _check_decodable(data: bytes) -> None:
    """Refuses `TEX_UNDECODABLE` (work-state) when `data` cannot be decoded
    to locate marker lines (design step 2). Binary I/O is used end to end for
    every read and write (`Binary I/O Only`) — this check never re-encodes
    `data` or uses the decoded text for anything; it exists only to catch a
    file whose bytes are not even valid UTF-8, which cannot be reasoned about
    as LaTeX source carrying ASCII marker lines at all.
    """
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise Refused(
            "TEX_UNDECODABLE",
            f"main.tex bytes cannot be decoded to locate marker lines: {exc}",
        )


@dataclass(frozen=True)
class ParsedDocument:
    """The result of one `parse()` call: every marker found, paired by id,
    plus the order the ids' pairs appear in. `pairs[id]` is
    `(begin_marker, end_marker)`; each marker is a dict with byte offsets
    into the SAME `data` this was parsed from — never reusable against a
    different buffer.
    """

    markers: list[dict]
    pairs: dict[str, tuple[dict, dict]]
    order: list[str]


def _iter_lines(data: bytes):
    """Yield `(start, end, content)` for each line in `data`.

    `end` includes the line's own terminator (so `data[start:end]` is the
    complete line, bytes and all); `content` excludes it. Recognizes only
    `\\n` and `\\r\\n` — this format's lines are LaTeX source, not arbitrary
    text, and `bytes.splitlines()` would also split on `\\v`/`\\f`/`\\x1c`-
    `\\x1e`, none of which this grammar has any business reacting to.
    """
    start = 0
    length = len(data)
    while start < length:
        nl = data.find(b"\n", start)
        if nl == -1:
            end = length
            content_end = length
        else:
            end = nl + 1
            content_end = nl - 1 if (nl > start and data[nl - 1:nl] == b"\r") else nl
        yield start, end, data[start:content_end]
        start = end


def scan_markers(data: bytes) -> list[dict]:
    """Find every marker-prefixed line in `data`. Raises `MARKER_MALFORMED`
    (naming the offending line) for a line that starts with the marker
    prefix but does not match the exact begin/end grammar.
    """
    markers: list[dict] = []
    for line_no, (start, end, content) in enumerate(_iter_lines(data), start=1):
        if not content.startswith(MARKER_PREFIX):
            continue
        m = _BEGIN_RE.match(content)
        if m:
            markers.append({
                "kind": "begin",
                "id": m.group("id").decode("ascii"),
                "digest": m.group("digest").decode("ascii"),
                "start": start,
                "end": end,
                "digest_start": start + m.start("digest"),
                "digest_end": start + m.end("digest"),
                "line": line_no,
            })
            continue
        m = _END_RE.match(content)
        if m:
            markers.append({
                "kind": "end",
                "id": m.group("id").decode("ascii"),
                "start": start,
                "end": end,
                "line": line_no,
            })
            continue
        raise Refused(
            "MARKER_MALFORMED",
            f"line {line_no} matches the marker prefix but not its grammar: {content!r}",
        )
    return markers


def pair_markers(markers: list[dict]) -> tuple[dict[str, tuple[dict, dict]], list[str]]:
    """Pair begin/end markers in document order.

    Refuses `BLOCK_DUPLICATED` when two begins (or two ends) share one id,
    `BLOCK_NESTED` when a begin appears before its predecessor's matching
    end, and `BLOCK_UNPAIRED` when a begin has no matching end or an end has
    no matching open begin.
    """
    pairs: dict[str, tuple[dict, dict]] = {}
    order: list[str] = []
    began_ids: set[str] = set()
    ended_ids: set[str] = set()
    open_marker: dict | None = None

    for marker in markers:
        if marker["kind"] == "begin":
            if marker["id"] in began_ids:
                raise Refused(
                    "BLOCK_DUPLICATED",
                    f"id {marker['id']!r}: a second begin marker at line {marker['line']}",
                )
            if open_marker is not None:
                raise Refused(
                    "BLOCK_NESTED",
                    f"begin for {marker['id']!r} at line {marker['line']} appears before "
                    f"{open_marker['id']!r}'s matching end",
                )
            began_ids.add(marker["id"])
            open_marker = marker
        else:
            if marker["id"] in ended_ids:
                raise Refused(
                    "BLOCK_DUPLICATED",
                    f"id {marker['id']!r}: a second end marker at line {marker['line']}",
                )
            if open_marker is None or open_marker["id"] != marker["id"]:
                raise Refused(
                    "BLOCK_UNPAIRED",
                    f"end marker for {marker['id']!r} at line {marker['line']} has no matching open begin",
                )
            ended_ids.add(marker["id"])
            pairs[marker["id"]] = (open_marker, marker)
            order.append(marker["id"])
            open_marker = None

    if open_marker is not None:
        raise Refused(
            "BLOCK_UNPAIRED",
            f"begin marker for {open_marker['id']!r} at line {open_marker['line']} has no matching end",
        )

    return pairs, order


def parse(data: bytes) -> ParsedDocument:
    """Scan and pair in one call — the shape every other function in this
    module builds on."""
    _check_decodable(data)
    markers = scan_markers(data)
    pairs, order = pair_markers(markers)
    return ParsedDocument(markers=markers, pairs=pairs, order=order)


def project(data: bytes) -> bytes:
    """Re-parse `data` from scratch and return everything OUTSIDE every
    block region, concatenated in document order.

    This is the independent half of the byte-identity invariant: it is a
    different computation from `prefix + new + suffix`, the substitution's
    own construction, which is what lets the invariant actually go red when
    a region boundary is wrong (see `identity_invariant`).
    """
    parsed = parse(data)
    regions = sorted((begin["start"], end["end"]) for begin, end in parsed.pairs.values())
    out = bytearray()
    cursor = 0
    for start, end in regions:
        out += data[cursor:start]
        cursor = end
    out += data[cursor:]
    return bytes(out)


def status(data: bytes) -> dict:
    """Read-only block table: every parsed id, its digest and its byte
    region. Never writes.
    """
    parsed = parse(data)
    blocks = []
    for block_id in parsed.order:
        begin, end = parsed.pairs[block_id]
        blocks.append({
            "id": block_id,
            "digest": begin["digest"],
            "region": [begin["start"], end["end"]],
        })
    return {"blocks": blocks}


def _ensure_trailing_newline(body: bytes) -> bytes:
    """A non-empty body must end with its own newline so the end marker that
    follows starts its own line — otherwise the end marker would not be a
    line at all, and a later `parse()` would not recognize it. This adds
    exactly the one byte needed for that, never a blank line: a blank line
    is an *empty* line, and appending a single trailing newline to non-empty
    content is not one.
    """
    if body and not body.endswith(b"\n"):
        return body + b"\n"
    return body


def _rewrite_begin_digest(pre: bytes, begin: dict, new_digest: str) -> bytes:
    """The begin marker's line, with only its digest field replaced.

    `sha256=` digests are always 64 lowercase hex characters, so this never
    changes the line's length — no byte offset outside the digest field
    itself moves, in this line or any other.
    """
    new_digest_bytes = new_digest.encode("ascii")
    assert len(new_digest_bytes) == 64
    return (
        pre[begin["start"]:begin["digest_start"]]
        + new_digest_bytes
        + pre[begin["digest_end"]:begin["end"]]
    )


def check_expected_digest(block_id: str, begin: dict, expected_digest: str | None) -> None:
    """The compare-and-swap on a block's base (#185): refuses
    `BLOCK_CHANGED_SINCE_READ` when the digest the block's begin marker
    records now differs from `expected_digest`, the one the caller read
    (the `digest` `status` lists). `None` checks nothing, so every caller
    that never passes a base keeps its previous behaviour exactly.

    The recorded digest is the one shape compared: it is what `status`
    reports, what `substitute` rewrites on every write and what `--adopt`
    re-baselines, so any write another session made since the read moves
    it. A hand edit that left the marker alone is `BLOCK_HAND_EDITED`'s
    business, not this check's.
    """
    if expected_digest is None:
        return
    if begin["digest"] != expected_digest.lower():
        raise Refused(
            "BLOCK_CHANGED_SINCE_READ",
            f"{block_id!r}: read at sha256={expected_digest.lower()}, now records "
            f"sha256={begin['digest']}; another write landed since it was read. Run status, "
            "read the current body and rebuild the replacement on it",
        )


def check_base_digest(paper_dir: Path, block_id: str, expected_digest: str | None) -> None:
    """`check_expected_digest` against `<paper_dir>/main.tex` as it is now,
    for a verb that wants to refuse a stale base before any of its own work
    (`write`, before its gates spend an attempt). Writes nothing.
    Refuses `BLOCK_ABSENT` when `block_id` has no pair.
    """
    if expected_digest is None:
        return
    validate_block_id(block_id)
    parsed = parse(resolve_main_tex(paper_dir).read_bytes())
    if block_id not in parsed.pairs:
        raise Refused("BLOCK_ABSENT", f"no block named {block_id!r}")
    check_expected_digest(block_id, parsed.pairs[block_id][0], expected_digest)


def build_candidate(
    pre: bytes,
    parsed: ParsedDocument,
    block_id: str,
    new_body: bytes | None,
    adopt: bool,
    expected_digest: str | None = None,
) -> tuple[bytes, bytes]:
    """The in-memory half of the substitution algorithm (design steps 1–6).

    Pure: takes the pre-write bytes and the already-parsed document, returns
    `(candidate_bytes, written_body)`. Never touches disk.

    Refuses `BLOCK_ABSENT` when `block_id` has no pair. In substitute mode
    (`adopt=False`): refuses `BLOCK_HAND_EDITED` naming both digests when
    the on-disk body no longer matches the recorded one, then
    `CONTENT_CARRIES_MARKER` when the caller's replacement body contains a
    marker-shaped line — matching design step order (hand-edit check before
    content check). In adopt mode (`adopt=True`): refuses `NOTHING_TO_ADOPT`
    when the on-disk body already matches the recorded digest; otherwise
    rewrites the digest to match the on-disk body and leaves that body
    untouched. With `expected_digest`, either mode then refuses
    `BLOCK_CHANGED_SINCE_READ` when the recorded digest is no longer the one
    the caller read (`check_expected_digest`), after the mode's own first
    check so every earlier refusal keeps its order.
    """
    if block_id not in parsed.pairs:
        raise Refused("BLOCK_ABSENT", f"no block named {block_id!r}")

    begin, end = parsed.pairs[block_id]
    on_disk_body = pre[begin["end"]:end["start"]]
    on_disk_digest = hashlib.sha256(on_disk_body).hexdigest()

    if adopt:
        if on_disk_digest == begin["digest"]:
            raise Refused(
                "NOTHING_TO_ADOPT",
                f"{block_id!r}: on-disk digest already matches the recorded sha256={begin['digest']}",
            )
        check_expected_digest(block_id, begin, expected_digest)
        written_body = on_disk_body
        written_digest = on_disk_digest
    else:
        if on_disk_digest != begin["digest"]:
            raise Refused(
                "BLOCK_HAND_EDITED",
                f"{block_id!r}: expected sha256={begin['digest']}, found sha256={on_disk_digest}",
            )
        check_expected_digest(block_id, begin, expected_digest)
        assert new_body is not None
        for _, _, content in _iter_lines(new_body):
            if content.startswith(MARKER_PREFIX):
                raise Refused(
                    "CONTENT_CARRIES_MARKER",
                    f"replacement body for {block_id!r} contains a marker-shaped line: {content!r}",
                )
        written_body = _ensure_trailing_newline(new_body)
        written_digest = hashlib.sha256(written_body).hexdigest()

    new_begin_line = _rewrite_begin_digest(pre, begin, written_digest)
    candidate = pre[:begin["start"]] + new_begin_line + written_body + pre[end["start"]:]
    return candidate, written_body


def identity_invariant(pre: bytes, candidate: bytes) -> None:
    """Refuses `SUBSTITUTION_NOT_LOCAL` when `candidate` would change any
    byte outside the target block's own region — checked on candidate bytes
    in memory, before any write reaches disk. This is layer 1 of the safety
    net and the only layer with no depth limit: refusing to write has no
    "how many steps back" question.

    Both sides are re-derived independently via `project()`, which re-parses
    from scratch; comparing `prefix + new + suffix` against itself here
    would prove nothing, since that IS the construction being checked.
    """
    if project(candidate) != project(pre):
        raise Refused(
            "SUBSTITUTION_NOT_LOCAL",
            "the candidate would change bytes outside the target block's region",
        )


def _atomic_replace(path: Path, data: bytes) -> None:
    """Write `data` to `path` via a same-directory temp file + `os.replace`,
    so a process interrupted mid-write never leaves `path` torn: it is
    always fully the pre-write or fully the post-write content.
    """
    directory = path.parent
    directory.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(directory), prefix=path.name + ".")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def _pre_image_path(paper_dir: Path) -> Path:
    return paper_dir / ".paper-writing" / "main.tex.prev"


def resolve_main_tex(paper_dir: Path) -> Path:
    """Resolve `<paper_dir>/main.tex` for a block operation — `open`,
    `status`, `substitute` — none of which ever create `paper/` themselves;
    only `scaffold` does that.

    Refuses `PAPER_ABSENT` (work-state) when `paper_dir` or `main.tex` under
    it does not exist, and `PAPER_NOT_A_DIRECTORY` (work-state) when
    `paper_dir` exists as a non-directory.
    """
    if not paper_dir.exists():
        raise Refused("PAPER_ABSENT", f"{paper_dir} does not exist; run scaffold first")
    if not paper_dir.is_dir():
        raise Refused("PAPER_NOT_A_DIRECTORY", f"{paper_dir} exists and is not a directory")
    tex_path = paper_dir / "main.tex"
    if not tex_path.is_file():
        raise Refused("PAPER_ABSENT", f"{tex_path} does not exist; run scaffold first")
    return tex_path


def read_status(paper_dir: Path) -> dict:
    """The disk-reading wrapper that makes the pure `status()` a CLI verb:
    resolves `main.tex`, reads it, hands the bytes to `status()`. Never
    writes — `status()` itself never has, and this adds no write either.
    """
    tex_path = resolve_main_tex(paper_dir)
    return status(tex_path.read_bytes())


def commit_candidate(paper_dir: Path, tex_path: Path, pre: bytes, candidate: bytes) -> None:
    """Steps 8–9 of `substitute` for any verb that built a whole-file
    candidate from `pre`: refuses `TEX_MOVED` when `main.tex` changed since
    `pre` was read, then writes the one-deep pre-image and atomically
    replaces `main.tex`. The caller has already run `identity_invariant`.
    """
    if hashlib.sha256(tex_path.read_bytes()).hexdigest() != hashlib.sha256(pre).hexdigest():
        raise Refused(
            "TEX_MOVED",
            "main.tex changed on disk between this call's read and its write",
        )
    _atomic_replace(_pre_image_path(paper_dir), pre)
    _atomic_replace(tex_path, candidate)


def substitute(
    paper_dir: Path,
    block_id: str,
    *,
    new_body: bytes | None = None,
    adopt: bool = False,
    contract: Path | None = None,
    expected_digest: str | None = None,
    clock=paper_region.default_clock,
) -> dict:
    """The full algorithm against `<paper_dir>/main.tex`, 9 steps plus one
    optional 10th.

    1–2. Read `main.tex` binary; digest it.
    3.   Scan and pair every marker (`MARKER_MALFORMED`, `BLOCK_UNPAIRED`,
         `BLOCK_DUPLICATED`, `BLOCK_NESTED`, `BLOCK_ABSENT`).
    4–6. `build_candidate` — hand-edit check, the optional base-digest
         check (`expected_digest`, `BLOCK_CHANGED_SINCE_READ`), marker-in-
         body check, build.
    7.   `identity_invariant` on the candidate, in memory
         (`SUBSTITUTION_NOT_LOCAL`).
    8.   Re-read `main.tex`; compare against the digest from step 2 — a
         compare-and-swap precondition (`TEX_MOVED`) guarding against a
         second session's edit landing between this call's read and write.
    8b.  If `contract` was given, prove it is readable NOW, before any byte
         reaches disk (`CONTRACT_UNREADABLE`, `the-paper-carries-its-own-
         decisions`'s own step, inserted here rather than at the top so
         every PRE-EXISTING refusal above still fires in exactly the same
         order it always has — this never reorders or suppresses one of
         them, block-substitution's own additive-refusal requirement).
    9.   Write the one-deep pre-image, THEN atomically replace `main.tex`.
         Step 8 precedes step 9 so a stale pre-image is never written; a
         crash between the two writes leaves the pre-image identical to
         `main.tex`, which is harmless.
    10.  If `contract` was given, record its provenance
         (`paper_provenance.record_write`) — the block body written in
         step 9 is IDENTICAL whether or not `contract` is supplied; only
         the `provenance` region differs (`PROVENANCE_HAND_EDITED` may
         still refuse here, after the block itself is already written —
         the block write and the provenance write are not one atomic
         transaction, matching design.md's own "written body is unchanged"
         acceptance criterion, which says nothing about provenance being
         all-or-nothing with it).
    """
    validate_block_id(block_id)
    tex_path = resolve_main_tex(paper_dir)
    pre = tex_path.read_bytes()
    pre_digest = hashlib.sha256(pre).hexdigest()

    parsed = parse(pre)
    candidate, written_body = build_candidate(
        pre, parsed, block_id, new_body, adopt, expected_digest=expected_digest,
    )
    identity_invariant(pre, candidate)

    current = tex_path.read_bytes()
    if hashlib.sha256(current).hexdigest() != pre_digest:
        raise Refused(
            "TEX_MOVED",
            "main.tex changed on disk between this call's read and its write",
        )

    if contract is not None:
        try:
            contract.read_bytes()
        except OSError as exc:
            raise Refused("CONTRACT_UNREADABLE", f"{contract}: {exc}")

    _atomic_replace(_pre_image_path(paper_dir), pre)
    _atomic_replace(tex_path, candidate)

    if contract is not None:
        paper_provenance.record_write(tex_path, block_id, contract, clock=clock)

    return {
        "block": block_id,
        "digest": hashlib.sha256(written_body).hexdigest(),
        "rendering": "unproven",
    }


def build_open_candidate(
    pre: bytes,
    parsed: ParsedDocument,
    block_id: str,
    *,
    after: str | None,
    at_end: bool,
) -> bytes:
    """The pure half of `open`: an empty begin/end pair for `block_id`,
    inserted at the position the caller named. Installs an empty pair only —
    never content; the first write to a new block is always `open` then
    `substitute`.

    Refuses `BLOCK_DUPLICATED` (work-state) if `block_id` already has a
    pair, and `ANCHOR_ABSENT` (invocation-defect) if `after` names an id
    with no pair. Ordering is the caller's business, never derived here.

    Hard rule: never inserts a blank line it was not asked for. Appending at
    the end of a file whose last byte is not already a newline adds exactly
    the one byte needed so the new marker starts its own line — the same
    discipline `_ensure_trailing_newline` applies to a substituted body —
    never a blank line, which would be two.
    """
    if block_id in parsed.pairs:
        raise Refused("BLOCK_DUPLICATED", f"id {block_id!r} already has a pair")

    if after is not None:
        if after not in parsed.pairs:
            raise Refused("ANCHOR_ABSENT", f"no block named {after!r}")
        _, anchor_end = parsed.pairs[after]
        insert_at = anchor_end["end"]
        gap = b""
    else:
        assert at_end
        insert_at = len(pre)
        gap = b"\n" if pre and not pre.endswith(b"\n") else b""

    empty_digest = hashlib.sha256(b"").hexdigest()
    pair = (
        f"%% paper-writing block {block_id} begin sha256={empty_digest}\n".encode("ascii")
        + f"%% paper-writing block {block_id} end\n".encode("ascii")
    )
    return pre[:insert_at] + gap + pair + pre[insert_at:]


def open_block(
    paper_dir: Path,
    block_id: str,
    *,
    after: str | None = None,
    at_end: bool = False,
) -> dict:
    """The disk-writing half of `open` — the exact same CAS + pre-image +
    atomic-replace shape as `substitute` (design steps 7–9). The shared
    `identity_invariant` is reused as-is, not reimplemented: a newly opened
    block's own bytes sit entirely inside its own (new) region, so
    `project()` excludes them on both sides of the write either way — an
    insertion that corrupted a byte outside every region is exactly the
    violation the shared invariant already catches.
    """
    validate_block_id(block_id)
    tex_path = resolve_main_tex(paper_dir)
    pre = tex_path.read_bytes()
    pre_digest = hashlib.sha256(pre).hexdigest()

    parsed = parse(pre)
    candidate = build_open_candidate(pre, parsed, block_id, after=after, at_end=at_end)
    identity_invariant(pre, candidate)

    current = tex_path.read_bytes()
    if hashlib.sha256(current).hexdigest() != pre_digest:
        raise Refused(
            "TEX_MOVED",
            "main.tex changed on disk between this call's read and its write",
        )

    _atomic_replace(_pre_image_path(paper_dir), pre)
    _atomic_replace(tex_path, candidate)

    return {
        "block": block_id,
        "position": f"after:{after}" if after is not None else "at-end",
    }
