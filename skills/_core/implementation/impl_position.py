from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

from impl_refusals import Refused

#: The section's delimiters. Both are HTML comments — neither starts with
#: `[-*]`, so `BULLET_LINE`/`AGREEMENT_LINE` (implementation_cli.py:153,159)
#: never mistake either DELIMITER for a checklist item. That claim covers
#: only these two lines. The block's own sequence items, `- [ ] N. ...`
#: (`ITEM_LINE`, below), are exactly `AGREEMENT_LINE`'s shape and WERE
#: counted as ordinary agreements — measured on a minimal fixture (2 real
#: bullets plus a 3-item block reporting `open: 5`, not 2) before this was
#: caught. The position section can sit inside a hand-curated AGREED.md
#: without inflating `agreements_state`'s counts only because
#: `implementation_cli.py`'s `_agreement_scan_text` excises the block's
#: whole byte span — start of this opener through the end of the closer —
#: before either `agreements_state` or `_agreement_collides` scans a line.
#: A claim about a delimiter is not a claim about what sits between them,
#: and leaving this docstring unchanged beside a fixed mechanism is how the
#: next reader re-introduces the bug it once masked.
BLOCK_CLOSE = b"<!-- /position -->"

#: A loose opener, used only to COUNT how many blocks exist in the document.
#: Counting has to survive a header that is itself malformed in some other
#: way — undercounting here would let a second, broken block hide behind the
#: first one's well-formed refusal instead of raising its own.
_BLOCK_OPEN_MARKER = rb"<!--\s*position\b"

#: The one true opener: every header field, in this exact order. A match
#: whose start does not coincide with `_BLOCK_OPEN_MARKER`'s only hit means
#: the opener exists but its header does not parse — a malformed artifact,
#: not an absent one.
#:
#: `target` is new in the level-grammar revision (PR10, `the-position-
#: nobody-holds`): the ordered rung this pass is aiming at, in the target's
#: own vocabulary (see `derive`'s docstring). A block written by the prior,
#: boolean-only grammar carries no `target=` field, so its header no longer
#: matches this pattern at all — **refused, not migrated, not silently
#: reinterpreted**. That is the deliberate choice: a bare byte-shift of an
#: old block's marks onto a new tick meaning ("reached this pass's rung")
#: would be asserting a rung nobody ever measured. The refusal is the same
#: `POSITION_BLOCK_MALFORMED` class the opener already raised for any other
#: unparsable header, and `position --reconcile --target-level <level>`
#: (implementation_cli.py) is the migration path: a fresh header, sequence
#: items preserved by witness identity, ticks re-derived from scratch under
#: the new grammar.
#: The optional trailing group (Cut 3, `a-revision-is-two-documents`, D3):
#: a compact, whitespace-free carrier for every document beyond document 0.
#: `revision=`/`sha256=` keep meaning document 0, exactly as they always
#: have; this group is appended AFTER `target=`, never reordering or
#: reshaping a field already on disk. `\S+` alone (matching
#: `_encode_extra_documents`'s own base64 alphabet, which contains no
#: whitespace) is what lets this group carry an arbitrary number of
#: `{label, revision, revisionSha256}` entries without inventing a
#: delimiter that might collide with a label or revision name.
_BLOCK_OPEN_RE = re.compile(
    rb"<!--\s*position\s+revision=(?P<revision>\S+)\s+"
    rb"sha256=(?P<sha256>[0-9a-f]{64})\s+derivedAt=(?P<derivedAt>\S+)\s+"
    rb"session=(?P<session>\S+)\s+target=(?P<target>\S+)"
    rb"(?:\s+documents=(?P<documents>\S+))?\s*-->"
)

#: The exact opener the grammar's first revision wrote, kept only so
#: `locate_block(..., allow_legacy=True)` can tell "an old block, migratable"
#: apart from "a document neither grammar recognizes". Never matched unless
#: the caller opts in: `cmd_position` is the one place migration happens, and
#: `verify`/`probe`/`position_state`'s read side never passes `allow_legacy`,
#: so an unmigrated block still exits 2 for them exactly as documented.
_LEGACY_BLOCK_OPEN_RE = re.compile(
    rb"<!--\s*position\s+revision=(?P<revision>\S+)\s+"
    rb"sha256=(?P<sha256>[0-9a-f]{64})\s+derivedAt=(?P<derivedAt>\S+)\s+"
    rb"session=(?P<session>\S+)\s*-->"
)

def require_session_token(session: str) -> str:
    """The `session=` field as `locate_block` reads it back: one non-empty
    ASCII token with no whitespace. Checked before `position` writes, so a
    `--session` the header cannot carry is refused (#67) instead of leaving a
    block that every later read refuses as malformed."""
    if not session or not session.isascii() or any(c.isspace() for c in session):
        raise Refused(
            "POSITION_SESSION_INVALID",
            f"--session {session!r} cannot be written into the position "
            "block's header, which carries it as one ASCII token without "
            "whitespace; pass an id such as `2026-10-12-a`.")
    return session


#: A sequence item line: `- [x] 1. <prose ending in a witness token>`. Modeled
#: on `AGREEMENT_LINE` (implementation_cli.py:149), with an ordinal added: the
#: sequence's numbering is part of what a human reads and is kept as its own
#: field so a renumbered sequence never has to touch the item's prose.
ITEM_LINE = re.compile(r"^\s*-\s*\[(?P<mark>[ xX])\]\s*(?P<ordinal>\d+)\.\s*(?P<text>.+)$")

#: The four evidence classes named by the domain — forge words, identical for
#: every target and learned from none of them. See `_record_scale`'s
#: docstring (implementation_cli.py:309-341) for why the forge recognizes no
#: target's vocabulary; this is the same discipline one level up.
WITNESS_KINDS = frozenset({"record", "notebook", "rehearsal", "shard", "step"})

#: The `WITNESS_KINDS` a bare `--about <kind>` (implementation_cli.py's
#: `_resolve_discuss_about`) MUST NOT accept without an operand.
#:
#: Measured, not assumed: `--about notebook` with no operand built a
#: witness whose `operand` is `None`; `_agreement_collides` (whose first
#: line is `if not operand: return []`) then short-circuits to `[]` on that
#: falsy operand before it ever globs a file. The caller believes a
#: collision scan ran; nothing ran — and a fixture whose agreement text
#: does not happen to name the operand returns `[]` too, for an entirely
#: legitimate reason, so the two cases are indistinguishable without this
#: refusal.
#:
#: `record` is deliberately excluded: it names the search contract's own
#: declared record, one fact per target rather than a per-artifact operand,
#: so it is the one `WITNESS_KINDS` member legitimately operand-less — the
#: same reading `_derive_record`'s own two-state check gives it.
OPERAND_REQUIRED_KINDS = frozenset({"notebook", "rehearsal", "shard", "step"})

#: Every witness-shaped token on a line, used only to COUNT them. Exactly one
#: is required per item; a prose sentence that happens to mention another
#: backticked `@word` is exactly the false positive `BULLET_LINE` already had
#: to guard against one file over, so the count — not a bare search — is what
#: decides malformed. `(?::level)?` mirrors `WITNESS_RE`'s own optional
#: leveled marker so a marked token is still counted as exactly one.
_WITNESS_TOKEN_RE = re.compile(r"`@[a-z]+(?::level)?(?: [^`]+)?`")

#: The one true witness: backticked, anchored to end-of-line so item prose is
#: never scanned for a stray `@`. An operand may carry slashes and dots
#: (`some/dir/thing.ipynb`) without needing its own escaping, because the
#: backtick is the only character the grammar treats as a delimiter. The example
#: is deliberately not a real layout name: this module is caller-agnostic, and a
#: comment naming one of the caller's own directories teaches the next reader
#: that the core knows a layout it must always be handed.
#:
#: `:level` (PR10) is the grammar's way for a single item to opt INTO the
#: ordered ladder. **Omitted, an item is two-state** — satisfied or not, with
#: nothing in between — exactly the grammar's first revision, unchanged, so
#: every block written before PR10's ordered-level revision keeps meaning
#: exactly what it always meant once migrated onto the new header (see
#: `_BLOCK_OPEN_RE`'s docstring for why the header itself still refuses an
#: unmigrated block). Two-state is the default because that is what a
#: witness already meant before this revision; a step earns a rung by saying
#: so, explicitly, right where a reader already looks — never inferred from
#: its kind, because two targets may both write a `@notebook` witness and
#: mean different things by it (one step reads a record tied to a rung,
#: another is a local check that only ever holds or does not). The forge
#: does not decide which a kind means; the artifact declares it.
WITNESS_RE = re.compile(
    r"`@(?P<kind>[a-z]+)(?P<leveled>:level)?(?: (?P<operand>[^`]+))?`\s*$")


def _encode_extra_documents(entries: list[dict]) -> bytes:
    """The header's `documents=` group value, for every document beyond
    document 0 (Cut 3, D3): canonical, separator-free JSON, base64-encoded
    -- the base64 alphabet carries no whitespace, so this always satisfies
    `\\S+` regardless of what a label or revision name itself contains.
    """
    payload = json.dumps(entries, separators=(",", ":"), sort_keys=True)
    return base64.urlsafe_b64encode(payload.encode("utf-8"))


def _decode_extra_documents(raw: bytes) -> list[dict]:
    """The inverse of `_encode_extra_documents`. Raises `ValueError` (bad
    base64) or a `json.JSONDecodeError` (bad JSON) on a corrupt group --
    both are caught by `locate_block`'s own caller and folded into the
    identical `POSITION_BLOCK_MALFORMED` class every other opener parse
    failure already raises."""
    return json.loads(base64.urlsafe_b64decode(raw).decode("utf-8"))


def locate_block(data: bytes, allow_legacy: bool = False) -> dict | None:
    """Find the position block's byte span in `data`, or say there is none.

    `None` is `absent` — a target whose flow never reached a gate has nothing
    to locate, and that is a state, not a search that failed (the same
    doctrine `agreements_state` states for a repository with no checklist at
    all). More than one opener is never resolved by picking the first: a
    delimiter this module owns appearing twice is an ambiguous document, the
    stricter rule adopted from `proposal-workspace.ts:2488-2501` over the
    first-occurrence rule `lifecycle-service.ts:24-35` uses for text the tool
    does not own.

    `allow_legacy=True` (PR10) additionally recognizes the exact header the
    grammar's first revision wrote (no `target=` field) and returns it with
    `"target": None, "legacy": True` instead of refusing — the one admission
    that makes migration reachable at all: `cmd_position` has to be able to
    *see* an old block before it can rewrite it. Every other caller (`verify`,
    `probe`, `position_state`'s read side) passes the default `False` and
    keeps refusing an unmigrated block exactly as documented — reading was
    never where migration was promised to happen, only `position` was.
    """
    markers = [m.start() for m in re.finditer(_BLOCK_OPEN_MARKER, data)]
    if not markers:
        return None
    if len(markers) > 1:
        raise Refused(
            "POSITION_BLOCK_NOT_UNIQUE",
            f"{len(markers)} `<!-- position ... -->` openers found in one "
            "document; a delimiter this module owns must occur exactly once.")

    header = _BLOCK_OPEN_RE.match(data, markers[0])
    legacy = False
    if header is None and allow_legacy:
        header = _LEGACY_BLOCK_OPEN_RE.match(data, markers[0])
        legacy = header is not None
    if header is None:
        raise Refused(
            "POSITION_BLOCK_MALFORMED",
            "the `<!-- position ... -->` opener does not carry revision, "
            "sha256, derivedAt, session and target in that order. A block "
            "written by the prior boolean-only grammar has no `target=` "
            "field and is refused here, not silently reinterpreted -- see "
            "`_BLOCK_OPEN_RE`'s docstring for the migration path.")
    close = data.find(BLOCK_CLOSE, header.end())
    if close == -1:
        raise Refused(
            "POSITION_BLOCK_MALFORMED",
            "no matching `<!-- /position -->` closer was found for the opener.")

    # Cut 3 (D3): `None` when the group did not match at all (a legacy
    # header, or a document-0-only header written before this cut) --
    # never confused with an empty list, which is what an EMPTY-but-present
    # group would decode to. `_LEGACY_BLOCK_OPEN_RE` names no `documents`
    # group at all, so `header.group("documents")` below would raise
    # `IndexError` on a legacy match; `legacy` is checked first for exactly
    # that reason.
    documents = None
    if not legacy:
        documents_raw = header.group("documents")
        if documents_raw is not None:
            try:
                documents = _decode_extra_documents(documents_raw)
            except (ValueError, UnicodeDecodeError) as exc:
                raise Refused(
                    "POSITION_BLOCK_MALFORMED",
                    "the `<!-- position ... -->` opener's `documents=` "
                    f"group does not decode as this grammar's compact "
                    f"per-document encoding: {exc}") from exc

    return {
        "start": header.start(),
        "end": close + len(BLOCK_CLOSE),
        "body": data[header.end():close].decode("utf-8"),
        "revision": header.group("revision").decode("ascii"),
        "revisionSha256": header.group("sha256").decode("ascii"),
        "derivedAt": header.group("derivedAt").decode("ascii"),
        "session": header.group("session").decode("ascii"),
        "target": None if legacy else header.group("target").decode("ascii"),
        "legacy": legacy,
        "documents": documents,
    }


#: A checklist item's own opening shape -- `-`/`*`, optional spacing, then
#: `[`. Mirrors `AGREEMENT_LINE`'s own start (implementation_cli.py:153)
#: without importing it: this module names no caller, so the shape is
#: restated here rather than reached for across the boundary.
_CHECKLIST_ITEM_START_RE = re.compile(r"^[-*]\s*\[")

#: An ATX heading of any level -- the generic boundary `locate_headings`'s
#: own prose-skip stops at when a section that opened with prose turns out
#: to carry no checklist item at all. Deliberately not anchored to the
#: caller's own `heading` argument: the NEXT heading, whatever its own
#: text, is what marks "this section is over", the same way a reader's eye
#: would stop looking.
_ANY_ATX_HEADING_RE = re.compile(r"^#{1,6}(\s|$)")


def _block_lines(decoded: list[str]) -> set[int]:
    """The line indexes a position block occupies, opener through closer.

    Read line by line from the block's own two markers, never through
    `locate_block`: a placement only needs to know which lines are not its
    own to enter, and must not refuse because a block elsewhere is malformed
    -- that is `position`'s and `verify`'s finding to report.
    """
    inside: set[int] = set()
    opener = re.compile(_BLOCK_OPEN_MARKER.decode("ascii"))
    closer = BLOCK_CLOSE.decode("ascii")
    open_at = None
    for index, line in enumerate(decoded):
        if open_at is None and opener.match(line):
            open_at = index
        if open_at is not None:
            inside.add(index)
            if closer in line:
                open_at = None
    return inside


def _first_bullet_insertion(
        decoded: list[str], offsets: list[int], total: int, heading_index: int) -> int:
    """The insertion offset for one located heading occurrence at
    `heading_index`: directly after the section's LAST checklist item, so a
    section reads in the order its items were settled (`cross-skill-
    consistency`, B4). Nothing already in the section moves: a holder
    written newest first by an earlier release keeps every line where it
    is, and the new item follows them.

    A position block's lines are never the section's items: the block is
    `position`'s, and an item spliced into it stops the block parsing
    (`POSITION_ITEM_MALFORMED`, X6). A section whose only checklist lines
    sit inside the block -- the holder `position` has just created --
    receives its first item directly after the block's closing line.

    The section ends at the next ATX heading of any level, or at the end of
    the document. A section with no checklist item and no block falls back
    to its own first non-blank line, or `total` when nothing follows the
    heading (unchanged from before this function existed). Fenced regions
    are skipped throughout.
    """
    count = len(decoded)
    block = _block_lines(decoded)
    last_item = None
    block_close = None
    fenced = False
    first_content = None
    cursor = heading_index + 1
    while cursor < count:
        line = decoded[cursor]
        if cursor in block:
            if first_content is None:
                first_content = cursor
            if BLOCK_CLOSE.decode("ascii") in line:
                block_close = cursor
            cursor += 1
            continue
        if line.startswith("```") or line.startswith("~~~"):
            fenced = not fenced
            if first_content is None:
                first_content = cursor
            cursor += 1
            continue
        if fenced:
            cursor += 1
            continue
        if line == "":
            cursor += 1
            continue
        if _ANY_ATX_HEADING_RE.match(line):
            break
        if first_content is None:
            first_content = cursor
        if _CHECKLIST_ITEM_START_RE.match(line):
            last_item = cursor
        cursor += 1
    anchor = last_item if last_item is not None else block_close
    if anchor is not None:
        return offsets[anchor + 1] if anchor + 1 < count else total
    if first_content is None:
        # Nothing but blank lines before the next heading (or the end):
        # the first non-blank line is that heading itself, or nothing.
        probe = heading_index + 1
        while probe < count and decoded[probe] == "":
            probe += 1
        return offsets[probe] if probe < count else total
    return offsets[first_content]


def locate_headings(data: bytes, heading: str) -> list[dict]:
    """Every zero-width insertion span for `heading`'s exact occurrences in
    `data`, one entry per hit, never a refusal.

    `heading` is matched by exact equality against a line's own stripped
    text, hash marks included -- `--under "## Ladder"` matches only a line
    that reads exactly `## Ladder`, never one that merely contains it.
    Measured on the real holder this module's own `BLOCK_CLOSE` docstring
    already cites: `## Figures — phase 1` and `## Figures — phase 2` both
    contain `## Figures`, so a substring rule already picks the wrong one
    of two on that document alone.

    A fenced region -- a line beginning, after leading whitespace, with
    three backticks or three tildes -- toggles exclusion for every line
    between its open and its matching close. Extra hits elsewhere in the
    document only widen the caller's own ambiguity count, which is safe; a
    fenced heading as the ONLY hit is the one way a placement would land
    inside a fenced block instead of the document's own prose, so it is
    excluded here rather than merely left for the caller to notice too
    late.

    Each returned span is `{"start": p, "end": p}` -- zero-width by
    construction. A section that opens directly with a checklist item
    lands at that item's own first byte; a section with no checklist item
    at all lands at the first byte of its first non-blank line, or
    `len(data)` when nothing follows the heading -- both unchanged from
    this function's first revision. **A section that opens with a
    paragraph of prose before its first checklist item lands at that
    item, past the prose, not ahead of it** -- see
    `_first_bullet_insertion`'s own docstring for the measurement that
    made this necessary: a rule that only ever skipped blank lines
    wedged an inserted bullet between a heading and the prose introducing
    it, on 2 of a real document's own 17 `## ` sections. A blank separator
    line is never itself counted as the insertion point, in any of the
    three shapes. Composing a returned span with `splice` (where
    `start == end`) inserts one new line without replacing anything that
    was already there.

    Returns a list rather than raising, deliberately unlike `locate_block`,
    which owns a document-wide delimiter and refuses on more than one
    opener. A heading belongs to the caller's own vocabulary, not this
    module's, so "none found" and "found more than once" are read off this
    list's own length by whoever asked, and only that caller names what
    each count means. This module stays ignorant of that caller's own
    refusal vocabulary entirely -- the same separation `WITNESS_KINDS`
    already keeps one level up, where a kind is named but never a code.
    """
    heading = heading.strip()
    parts = data.split(b"\n")
    count = len(parts)
    # `data.split(b"\n")` drops every newline byte it split on; put back
    # exactly one per line except the true final one, so summing lengths
    # reconstructs `data`'s own byte offsets rather than a re-decoded guess.
    lines = [parts[i] + (b"\n" if i < count - 1 else b"") for i in range(count)]

    offsets: list[int] = []
    running = 0
    for line in lines:
        offsets.append(running)
        running += len(line)
    total = running
    decoded = [line.decode("utf-8").strip() for line in lines]

    spans: list[dict] = []
    fenced = False
    for i, stripped in enumerate(decoded):
        if stripped.startswith("```") or stripped.startswith("~~~"):
            fenced = not fenced
            continue
        if fenced or stripped != heading:
            continue
        insertion = _first_bullet_insertion(decoded, offsets, total, i)
        spans.append({"start": insertion, "end": insertion})
    return spans


def parse_items(body: str) -> list[dict]:
    """Every sequence item in a located block's body, witness resolved.

    Raises rather than reports: this section is entirely tool-owned, so a
    line that does not parse, an item without exactly one witness, or a
    witness naming a kind this module does not recognize are all the same
    class `MALFORMED_FINDINGS` already is for `read_findings`
    (implementation_cli.py:2151) — a broken artifact, not a not-yet-ready
    target. `main()`'s existing `except Refused` turns this into exit 2 from
    any command that reads a position block, `verify`/`probe` included, with
    no extra wiring at either call site.
    """
    items: list[dict] = []
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = ITEM_LINE.match(line)
        if not match:
            raise Refused(
                "POSITION_ITEM_MALFORMED",
                f"line in the position block does not parse as a sequence "
                f"item: {line!r}")
        ordinal = int(match.group("ordinal"))
        mark = "x" if match.group("mark") in "xX" else " "
        text = match.group("text")

        tokens = _WITNESS_TOKEN_RE.findall(text)
        witness_match = WITNESS_RE.search(text)
        if len(tokens) != 1 or witness_match is None:
            raise Refused(
                "POSITION_ITEM_WITHOUT_WITNESS",
                f"item {ordinal} must carry exactly one witness token "
                f"anchored to end of line; found {len(tokens)}: {text!r}")

        kind = witness_match.group("kind")
        if kind not in WITNESS_KINDS:
            raise Refused(
                "POSITION_WITNESS_UNKNOWN_KIND",
                f"item {ordinal} names unknown witness kind {kind!r}; "
                f"expected one of {sorted(WITNESS_KINDS)}")

        items.append({
            "ordinal": ordinal,
            "mark": mark,
            "text": text[:witness_match.start()].rstrip(),
            "witness": {
                "kind": kind,
                "operand": witness_match.group("operand"),
                # See `WITNESS_RE`'s docstring: a per-item declaration, not a
                # per-kind one. Absent the `:level` marker, an item is
                # two-state (the default, unchanged from the grammar's first
                # revision); marked, `derive` reports which declared rung it
                # reaches instead of a bare pass/fail.
                "twostate": witness_match.group("leveled") is None,
            },
        })
    return items


def _derive_record(evidence: dict) -> tuple[bool | None, str]:
    """`@record` (two-state, the default) ticks against `search_state()`'s own `recordFound`/`scaleSatisfied`.

    `evidence["search"]` is that function's return, verbatim.
    `evidence["requiredScale"]` is the caller's own `declared_required_scale(search)`
    — computed once by the caller rather than re-derived here, so this stays a
    plain dict reader and never learns `search_state`'s internal shape.

    **Arrival alone is not evidence that a record reports on the code
    running now.** A record is a file left behind by whatever ran; nothing
    about its presence says which code produced it -- the same gap
    `_derive_shard`'s own docstring names for a shard, one level up.
    `evidence["search"]["recordCurrent"]` is `search_state()`'s own answer,
    computed the identical way `_shards_current` computes one for a shard:
    `None` when the target never declared `search.currentWhen` (nothing to
    check, so a found record is trusted on arrival alone, exactly as before
    this key existed); `True`/`False` once it did, comparing the record's
    own stamp against the digest of the code as it stands.

    **A stale record reads `None` (unmeasured), never `False`.** The record
    exists -- `recordFound` already said so -- we simply cannot say it
    speaks for this code; that is a different fact from "nothing has run
    yet", the identical distinction `_derive_shard`'s `shardsCurrent`
    doctrine already draws for an arrived-but-not-current shard. Only
    `recordFound is False` is ever a definite `False` here: currency
    answers a question about a record that was found, never about one that
    was not.
    """
    search = evidence.get("search")
    if not isinstance(search, dict) or "recordFound" not in search:
        return None, "search.recordFound"
    found = search.get("recordFound")
    if found is None:
        return None, "search.recordFound"
    if found is False:
        return False, "search.recordFound"
    current = search.get("recordCurrent")
    if current is False:
        return None, "search.recordCurrent"
    suffix = "" if current is None else "+recordCurrent"
    if evidence.get("requiredScale"):
        return search.get("scaleSatisfied") is True, "search.scaleSatisfied" + suffix
    return True, "search.recordFound" + suffix


def _derive_notebook(evidence: dict, operand: str | None) -> tuple[bool | None, str]:
    """`@notebook <path>` (two-state, the default) ticks against `notebooks_state()`'s per-report state.

    `operand` is matched against `report["notebook"]` both exactly and by
    suffix (`.../<operand>`), because `notebooks_state` stamps a path relative
    to the target while the witness names only the tail relative to the
    product — the same pair the design's grammar table declares. Neither
    directory is named here: the caller owns its layout and hands it in, and a
    core that spelled one out would be holding a fact it is supposed to receive.
    """
    measured_by = f"notebooks.reports[{operand}].sourcesMatch"
    notebooks = evidence.get("notebooks")
    if not operand or not isinstance(notebooks, dict):
        return None, measured_by
    report = next(
        (r for r in notebooks.get("reports", [])
         if r.get("notebook") == operand
         or r.get("notebook", "").endswith(f"/{operand}")),
        None)
    if report is None:
        return None, measured_by
    return (report.get("status") == "executed"
            and report.get("sourcesMatch") is True), measured_by


def _derive_rehearsal(evidence: dict, operand: str | None) -> tuple[bool | None, str]:
    """`@rehearsal <jobName>` (two-state, the default) ticks against `remote_execution_jobs_state()["smokeReady"]`.

    The un-forgeable half of the whole change (design §4.3): `smokeReady` is
    only ever `True` once a rehearsal actually ran and was recorded at the
    job's current pin, so a hand-edited mark can never make this branch agree
    with a rehearsal that did not happen.
    """
    measured_by = f"remoteExecution.smokeReady[{operand}]"
    smoke_ready = evidence.get("smokeReady")
    if not operand or not isinstance(smoke_ready, dict) or operand not in smoke_ready:
        return None, measured_by
    return smoke_ready.get(operand) is True, measured_by


def _derive_shard(evidence: dict, operand: str | None) -> tuple[bool | None, str]:
    """`@shard <id>` (two-state, the default) ticks against `verify --shards`'s `shardsArrived`.

    `evidence["shardsArrived"]` is `None` whenever this invocation resolved
    neither an explicit override nor a declared shard location for this run
    (a bare `verify` with no `--shards` and no `distribution.shardsRoot`
    declared, most commonly) — and `None` here means `unmeasured`, never
    `False`: the shard may well have arrived, this invocation simply was
    never told where to look.

    **Arrival alone is not evidence that a shard reports on the code running
    now.** A shard folder is a file left behind by whatever ran; nothing about
    its presence says which code produced it, and reading a rung off it is the
    same unbacked attribution `_derive_notebook_level` already refuses ("we
    have not looked with current eyes"). `evidence["shardsCurrent"]` is the
    subset of arrived shards whose own stamp says otherwise — measured by the
    caller, which is the only layer that knows both the stamp field a target
    declared and the digest of the code as it stands. An arrived shard that is
    NOT in that subset reads `None` (unmeasured), never `False`: the shard
    exists, we simply cannot say it speaks for this code.

    **`shardsCurrent is None` restores the behaviour that predates it, exactly.**
    A target that never declared which stamp field carries its code identity
    has said nothing this could check, and inventing a field name on its behalf
    is the one thing the forge must not do — so arrival alone decides, as it
    always did, and no target that never opted in changes verdict.
    """
    arrived = evidence.get("shardsArrived")
    current = evidence.get("shardsCurrent")
    measured_by = ("distribution.shardsArrived" if current is None
                   else "distribution.shardsArrived+shardsCurrent")
    if not operand or arrived is None:
        return None, measured_by
    if operand not in arrived:
        return False, measured_by
    if current is not None and operand not in current:
        return None, measured_by
    return True, measured_by


def _derive_step(evidence: dict, operand: str | None) -> tuple[bool | None, str]:
    """`@step <name>` (two-state, the default) ticks against
    `evidence["stepVerdicts"][operand]`, a plain dict reader with no ladder
    of its own -- design "A Leveled Step Refuses, Never Derives Silently":
    a step reports satisfied/not, never a graduated rung.

    `evidence["stepVerdicts"]` is the caller's already-resolved tri-state per
    step name (`_step_verdicts`, `implementation_cli.py`): `True` once the
    latest `kind: "step"` ledger event for this name recorded `outcome:
    "returned"` under a current `suite_digest`; `False` once it recorded
    `outcome: "raised"` under a current digest; `None` for every other case
    -- no event, a stale digest, or a pre-change event carrying no digest at
    all (spec "The Ledger Carries Currency, Old Events Read Safely"). This
    function itself never compares digests, never reads the ledger, never
    walks a filesystem: that math belongs to its one caller, the identical
    layering `_derive_shard`'s own docstring states for `shardsCurrent`.

    The dict's own value is returned untouched -- `verdicts.get(operand)`,
    never `is True`/`is False` collapsed -- so a recorded `False` (the suite
    actually raised) reads as the definite `False` it is, never folded into
    the same `None` an operand that never ran would produce. Only a missing
    key, a missing dict, or a missing operand short-circuit to `None`.
    """
    measured_by = f"stepVerdicts[{operand}]"
    verdicts = evidence.get("stepVerdicts")
    if not operand or not isinstance(verdicts, dict) or operand not in verdicts:
        return None, measured_by
    return verdicts.get(operand), measured_by


_DERIVERS = {
    "notebook": _derive_notebook,
    "rehearsal": _derive_rehearsal,
    "shard": _derive_shard,
    "step": _derive_step,
}


def level_index(levels: list[str], level: str | None) -> int | None:
    """`level`'s position on the declared ladder, or `None` off it (unknown
    or `level is None`).

    This is the whole of what the forge knows about a ladder: an ordered
    list, and how to compare two positions in it. The names on that list are
    entirely the target's own vocabulary — this module holds none of its
    own, the same discipline `WITNESS_KINDS` already keeps for evidence
    classes one level up. A repository with a three-rung remote-execution
    ladder and one with none at all (`levels == []`) both run this same
    arithmetic; only the list differs.
    """
    if level is None:
        return None
    try:
        return levels.index(level)
    except ValueError:
        return None


def highest_rung(kind: str, levels: list[str]) -> int | None:
    """The highest index on `levels` a leveled witness of this kind could
    EVER derive, whatever runs next -- `None` for a kind that carries no
    ladder at all, and for an empty ladder, which has no index to name.

    A bound is not a measurement: it is what the evidence CLASS can prove
    at its very best. `smokeReady` is two-valued, so a `@rehearsal` that
    passed proves the floor plus one and nothing further -- reaching past
    that is `@record`'s or `@shard`'s evidence to speak to. Every other
    leveled kind can reach the top: an arrived, current shard is full-scale
    evidence in its own right, and a record that meets its own declared
    scale was asked nothing further.

    **The derivers read this rather than restating it.**
    `_derive_rehearsal_level` and `_derive_shard_level` below return
    `levels[highest_rung(...)]` on their own best branch, so the bound
    and the derivation are one expression and not two that can drift. That
    matters because a report is built on this: a bound that claimed less
    than a deriver actually reaches would tell a repository its ladder can
    never be climbed when it can.

    A kind absent from the table answers `None` and contributes no bound.
    `"step"` is the one such kind today and is unreachable here anyway:
    `_resolve_deriver` refuses `@step:level` outright
    (`POSITION_WITNESS_NOT_LEVELABLE`) before anything can ask it for a rung.
    """
    if not levels:
        return None
    if kind == "rehearsal":
        return min(1, len(levels) - 1)
    if kind in ("notebook", "shard", "record"):
        return len(levels) - 1
    return None


def attainable_rung(items: list[dict], levels: list[str]) -> str | None:
    """The highest rung this sequence could EVER attain, on evidence nobody
    has measured yet -- `attained_level`'s own question asked about the
    future instead of the present.

    `attained_level` is the highest rung at which every leveled item grades
    satisfied NOW; this is the highest rung at which every leveled item
    COULD grade satisfied, taking each one's evidence class at its best
    (`highest_rung`). The minimum, because attainment is whole-sequence:
    one item that can never pass rung N holds the whole sequence below it,
    exactly as it does in `attained_level`.

    **A sequence with no leveled item can attain the whole ladder**, vacuously
    and deliberately: with nothing that could fail to reach a rung, every
    rung is reachable by aiming at it. This is a bound on the future, so it
    does not contradict `attained_level`, which answers what is reached now
    and bounds such a sequence by its aim.

    Pure: no I/O, no evidence read at all. It answers a question about the
    grammar and the ladder, never about what has run.
    """
    if not levels:
        return None
    caps = [bound for bound in
            (highest_rung(item["witness"]["kind"], levels) for item in items
             if not item["witness"].get("twostate", True))
            if bound is not None]
    return levels[min(caps)] if caps else levels[-1]


def _record_scale_level(
        record: dict | None, required_scale: dict | None, levels: list[str], *,
        measured_by: str) -> tuple[str | None, str]:
    """The rung a record's own scale reaches, composed from exactly the two
    facts `search_state()` (or `named_records_state()`, one level over) already
    computes — `recordFound` and, when a scale is declared, `scaleSatisfied` —
    never a new measurement.

    This is the mechanism behind PR10's motivating defect: a record found on
    disk but short of the declared scale (sixty runs beside a declared
    eighteen hundred) used to satisfy the same boolean `@record` witness a
    full record did. Composed as a rung instead, it reads as the *second*
    rung on a ladder with room for one, not the top — visible on the item
    itself, not something a reader has to already remember to doubt.

    - not found → the floor rung: nothing has run yet.
    - found, and either no scale is declared or the declared scale is met →
      the top rung: nothing further was asked of this record.
    - found, short of a declared scale → one rung under the top when the
      ladder has room for that distinction (three rungs or more); the floor
      otherwise — a two-rung ladder has nowhere honest to place "something
      ran, but not enough of it" except "not yet there".
    - `scaleSatisfied` itself unmeasured (a scale is declared but nothing
      could check it) → unmeasured, not guessed at.

    **`record`, `required_scale` and `measured_by` are three explicit
    bindings, one arithmetic body** (design D2): `derive`'s own bare
    `@record:level` branch feeds this `evidence["search"]`/
    `evidence["requiredScale"]`, `_derive_notebook_level` feeds it the
    identical pair, and `_derive_record_level` feeds it one
    `evidence["records"][name]` entry and that entry's own `requiredScale` —
    the same arithmetic, never a second one drifting beside it. `measured_by`
    carries no default and is never computed internally: every branch below
    returns it unchanged, so a caller that names the wrong string reports the
    wrong provenance for a correctly-derived rung — a caller-visible mistake,
    not a silent one.
    """
    if not levels:
        return None, measured_by
    if not isinstance(record, dict) or "recordFound" not in record:
        return None, measured_by
    found = record.get("recordFound")
    if found is None:
        return None, measured_by
    if found is False:
        return levels[0], measured_by
    if not required_scale or record.get("scaleSatisfied") is True:
        return levels[-1], measured_by
    if record.get("scaleSatisfied") is False:
        return levels[max(0, len(levels) - 2)], measured_by
    return None, measured_by


def _derive_notebook_level(
        evidence: dict, operand: str | None, levels: list[str]) -> tuple[str | None, str]:
    """`@notebook <path>` (leveled): the rung the record behind this report
    reaches — but only once the report itself is honestly current.

    A notebook that has not run, or whose sources no longer match, cannot
    attribute a rung to anything it printed: unmeasured, not the floor,
    because the fact is "we have not looked with current eyes", not "we
    looked and it has not started" — the distinction `derive`'s own
    docstring keeps for the same reason one level up. Once the report is
    current, its rung is the record's own (`_record_scale_level`): a report
    is only ever as trustworthy about scale as the record it read.
    """
    measured_by = f"notebooks.reports[{operand}].sourcesMatch+search.scaleSatisfied"
    notebooks = evidence.get("notebooks")
    if not operand or not isinstance(notebooks, dict):
        return None, measured_by
    report = next(
        (r for r in notebooks.get("reports", [])
         if r.get("notebook") == operand
         or r.get("notebook", "").endswith(f"/{operand}")),
        None)
    if report is None:
        return None, measured_by
    if not (report.get("status") == "executed" and report.get("sourcesMatch") is True):
        return None, measured_by
    # `measured_by` is threaded through rather than discarded (`_`): the
    # returned string is this same fixed value on every path
    # `_record_scale_level` can take, so sourcing it from the call rather
    # than reassigning it locally is what makes a swap between this
    # binding's own string and `derive`'s own bare-record one an observable
    # mutation — see `_record_scale_level`'s own docstring.
    level, measured_by = _record_scale_level(
        evidence.get("search"), evidence.get("requiredScale"), levels,
        measured_by=measured_by)
    return level, measured_by


def _derive_rehearsal_level(
        evidence: dict, operand: str | None, levels: list[str]) -> tuple[str | None, str]:
    """`@rehearsal <jobName>` (leveled): `smokeReady` is itself a two-valued
    fact (a rehearsal ran and passed, or it did not), so it can only ever
    place a job at the floor rung or the one just above it — reaching
    further than that is `@record`'s or `@shard`'s evidence to speak to, a
    rehearsal never claims full scale on its own.
    """
    measured_by = f"remoteExecution.smokeReady[{operand}]"
    if not levels:
        return None, measured_by
    smoke_ready = evidence.get("smokeReady")
    if not operand or not isinstance(smoke_ready, dict) or operand not in smoke_ready:
        return None, measured_by
    if smoke_ready.get(operand) is True:
        # `highest_rung`, never a second `min(1, ...)` written beside it:
        # `unreachable_ladder_state` (`implementation_cli.py`) reports a
        # ladder no launch can ever reach BECAUSE of this bound, and a copy
        # of the arithmetic is how the report and the derivation come to
        # disagree about what a rehearsal proves.
        return levels[highest_rung("rehearsal", levels)], measured_by
    return levels[0], measured_by


def _derive_shard_level(
        evidence: dict, operand: str | None, levels: list[str]) -> tuple[str | None, str]:
    """`@shard <id>` (leveled): an arrived shard that reports on the code
    running now is full-scale evidence in its own right, so it places its
    item at the top rung; one that has not arrived, at the floor — both
    definite, because `shardsArrived` being present at all (not `None`)
    means this invocation was told to look.

    A shard that arrived but is not `evidence["shardsCurrent"]` reads
    `None` (unmeasured), never the floor, for the identical reason
    `_derive_notebook_level` gives: the fact is "we have not looked with
    current eyes", not "it has not started". And `shardsCurrent is None`
    — the target declared no way to tell — leaves arrival alone deciding,
    exactly as it did before that key existed. See `_derive_shard`'s own
    docstring for both halves in full.
    """
    arrived = evidence.get("shardsArrived")
    current = evidence.get("shardsCurrent")
    measured_by = ("distribution.shardsArrived" if current is None
                   else "distribution.shardsArrived+shardsCurrent")
    if not levels:
        return None, measured_by
    if not operand or arrived is None:
        return None, measured_by
    if operand not in arrived:
        return levels[0], measured_by
    if current is not None and operand not in current:
        return None, measured_by
    # Read from the same table `_derive_rehearsal_level` reads its own bound
    # from, for the same reason: one expression, never two.
    return levels[highest_rung("shard", levels)], measured_by


def _derive_record_level(
        evidence: dict, operand: str | None, levels: list[str]) -> tuple[str | None, str]:
    """`@record:level <name>` (leveled): the rung the NAMED entry's own
    found/scale state reaches, routed through the identical
    `_record_scale_level` arithmetic the `search` block's own bare
    `@record:level` already uses (design D2) — never a second one.

    `evidence["records"]` is `named_records_state()`'s own shape:
    `{name: {recordFound, recordCurrent, scaleSatisfied, requiredScale}}`.
    **A `name` absent from a declared `__records__` derives `None`
    (unmeasured), never `False`** — `POSITION_RECORD_UNKNOWN` already
    refuses this state before `position` ever writes a mark from it (see
    `cmd_position`); `verify`/`probe`, which never refuse, read the identical
    absence as "nothing to check", the same doctrine an unlisted `@notebook`
    path or `@rehearsal` job already reads one level over.
    """
    measured_by = f"records[{operand}].recordFound+scaleSatisfied"
    records = evidence.get("records")
    if not operand or not isinstance(records, dict) or operand not in records:
        return None, measured_by
    entry = records[operand]
    if not isinstance(entry, dict):
        return None, measured_by
    return _record_scale_level(
        entry, entry.get("requiredScale"), levels, measured_by=measured_by)


_LEVEL_DERIVERS = {
    "notebook": _derive_notebook_level,
    "rehearsal": _derive_rehearsal_level,
    "shard": _derive_shard_level,
}


def _resolve_deriver(table: dict, table_name: str, kind: str, item: dict):
    """The one place either lookup table (`_DERIVERS`, `_LEVEL_DERIVERS`) is
    read by kind, replacing two bare subscripts that each raised an uncaught
    `KeyError` for a kind the table does not carry -- design "The guard
    lives at the lookup, not as a fourth special case".

    A kind present in `WITNESS_KINDS` but absent from `_LEVEL_DERIVERS`
    (`"step"`, by design: a step reports satisfied/not, never a rung) is
    reachable from real markdown -- `@step:level <name>` parses cleanly,
    `parse_items` validates only that the *kind* is known, never that this
    particular kind carries a ladder. A kind absent from `_DERIVERS` is not
    reachable the same way today (every `WITNESS_KINDS` member besides
    `record`, special-cased above this call, has a `_DERIVERS` entry); this
    guard exists there anyway so a *future* kind added to `WITNESS_KINDS`
    without a two-state deriver fails the identical classified way rather
    than a bare `KeyError` one layer up.

    `POSITION_WITNESS_NOT_LEVELABLE` is deliberately not rostered in
    `GATING_REFUSALS` (`implementation_cli.py`): `raised_refusal_codes`
    scans `cmd_*` subtrees only, and this raise sits in `_core/`, one layer
    below any `cmd_*` body -- the same non-rostered class `parse_items`'s own
    `POSITION_ITEM_MALFORMED`/`POSITION_WITNESS_UNKNOWN_KIND` already belong
    to.

    `item` is read only through `.get("ordinal")`, never a bare subscript:
    `cmd_discuss`'s own synthetic probe item (`implementation_cli.py`, built
    to measure a bare `--about <kind>` before any sequence item exists)
    carries no `"ordinal"` key at all -- measured after a first version of
    this guard read `item["ordinal"]` unconditionally and crashed every
    `discuss --about <operand-required kind> <operand>` call with an
    uncaught `KeyError`, even on the successful path where the deriver was
    found and this guard never had anything to report.
    """
    deriver = table.get(kind)
    if deriver is None:
        raise Refused(
            "POSITION_WITNESS_NOT_LEVELABLE",
            f"item {item.get('ordinal', '?')} names witness kind {kind!r}, "
            f"which has no {table_name} deriver; kinds that do: "
            f"{sorted(table)}")
    return deriver


def derive(items: list[dict], evidence: dict) -> list[dict]:
    """The measured verdict for every item's witness, and nothing else.

    **A level, not a bool (PR10) — except where an item declared itself
    two-state.** Per item, `derived` is:

    - for a two-state item (no `:level` marker, the default): `True`/`False`
      when the evidence class actually
      answers, `None` ("unmeasured") when it does not — unchanged from the
      grammar's first revision, because a two-state item has no rung to be
      assigned and never has one invented for it.
    - for a leveled item (the default): one of `evidence["levels"]`'s own
      names when the evidence resolves to a rung, `None` when it does not.
      **A leveled item is never assigned `False`; only `None` or one of the
      declared names.** `None` is never folded into the floor rung: "we did
      not look" and "it has not started" stay two different facts, the same
      rule `_record_scale` already keeps by returning `{}` rather than
      guessing.

    `unbacked` is the one asymmetry a blank box and a ticked box do not
    share. `disagrees` compares a mark against a measurement, so it is
    necessarily silent when there is no measurement — an `x` over an
    unmeasured witness contradicts nothing, because nothing was said. But
    the two marks are not equally honest there: a blank box over an
    unmeasured witness claims nothing and is exactly right to; a ticked one
    asserts a step was reached while the only thing that could confirm it
    was never looked at. Without this key those two items are byte-identical
    in every report the position produces, so the assertion nobody measured
    reads as the settled fact everybody did. `unbacked` is that, and only
    that: `satisfied is None and mark == "x"`. It is deliberately NOT folded
    into `disagrees` — a disagreement names a measurement that says
    otherwise, and there is none here to name.

    `satisfied` is the tick-worthy verdict every caller writing a mark
    should read, never `derived` directly: for a two-state item it is
    `derived` itself; for a leveled item it is whether `derived`'s rung is
    at or above `evidence["targetLevel"]` — the pass this call is deriving
    against — computed via `level_index` and `None` whenever either side is
    `None` or unknown. `disagrees` compares `satisfied` against the item's
    existing mark, not `derived`, so a two-state item and a leveled item are
    graded by the identical rule once `satisfied` exists.

    Pure: no I/O. `evidence` is a plain dict of already-computed states plus
    the declared ladder (`evidence["levels"]`, absent or `[]` for a target
    that names none) and this pass's own target (`evidence["targetLevel"]`),
    so two callers (`verify`, `probe`) hand this the same shape and get the
    same answer without either one importing the other's read path.
    """
    levels = evidence.get("levels") or []
    target_level = evidence.get("targetLevel")
    results = []
    for item in items:
        witness = item["witness"]
        kind, operand = witness["kind"], witness["operand"]
        # Two-state is the default when a hand-built item dict carries no
        # `twostate` key at all (`.get(..., True)`, not `.get(...)`), the
        # same default `WITNESS_RE`'s docstring states for the markdown
        # grammar itself -- a caller that never opted into levels keeps
        # getting exactly the boolean derivation it always got.
        twostate = witness.get("twostate", True)
        if twostate:
            if kind == "record":
                derived, measured_by = _derive_record(evidence)
            else:
                deriver = _resolve_deriver(_DERIVERS, "two-state", kind, item)
                derived, measured_by = deriver(evidence, operand)
            satisfied = derived
        else:
            if kind == "record":
                # A named operand routes through the addressed entry
                # (design D2/D4); an unnamed one (bare `@record:level`, the
                # grammar that predates `__records__` entirely) keeps the
                # search block's own byte-identical fallthrough — "existing
                # instances keep working" (spec).
                if operand:
                    derived, measured_by = _derive_record_level(evidence, operand, levels)
                else:
                    derived, measured_by = _record_scale_level(
                        evidence.get("search"), evidence.get("requiredScale"), levels,
                        measured_by="search.recordFound+scaleSatisfied")
            else:
                deriver = _resolve_deriver(_LEVEL_DERIVERS, "leveled", kind, item)
                derived, measured_by = deriver(evidence, operand, levels)
            # `derived is None` must short-circuit straight to `satisfied =
            # None`: an `and`-chain that starts `derived_index is not None`
            # collapses to the bool `False` the moment that first condition
            # is `False`, which would silently turn "unmeasured" into a
            # definite "not satisfied" -- exactly the collapse this whole
            # revision exists to keep from happening.
            if derived is None:
                satisfied = None
            else:
                derived_index = level_index(levels, derived)
                target_index = level_index(levels, target_level)
                satisfied = (None if derived_index is None or target_index is None
                            else derived_index >= target_index)
        disagrees = satisfied is not None and satisfied != (item["mark"] == "x")
        # See the docstring: a tick over a witness nothing measured is an
        # assertion, and it has to be told apart from the blank box beside
        # it, which asserts nothing and is honest for it.
        unbacked = satisfied is None and item["mark"] == "x"
        results.append({
            "derived": derived,
            "twostate": twostate,
            "satisfied": satisfied,
            "measuredBy": measured_by,
            "disagrees": disagrees,
            "unbacked": unbacked,
        })
    return results


def attained_level(items: list[dict], evidence: dict) -> str | None:
    """Which rung the evidence currently REACHES, or `None` when it reaches
    none: **the highest rung at which every leveled item grades `satisfied`.**

    A header's `target=` states what a pass AIMS at, and an aim is legitimately
    one rung above what has been reached — that is how a pass climbs at all.
    Attainment is the other fact, and until this function existed the grammar
    carried no way to say it: a reader could see the aim on every payload and
    had to trip a refusal to learn whether anything backed it. Two meanings on
    one field is how a recorded rung that outlived its evidence came to switch
    off the very rule that should have caught it.

    **Defined against `derive`, never beside it.** Each candidate rung is put
    back through `derive` with that rung as `targetLevel`, so "attained at R"
    means exactly what "satisfied at R" already means for every witness kind —
    including the ones added after this was written. The alternative, taking
    the minimum `level_index(derived)` across the items, is the same number
    today and a second arithmetic to keep in step forever.

    Three boundaries, each a decision:

    - **`None` is not the floor.** A leveled item nobody measured grades
      `satisfied is None`, which is not `True`, so it holds attainment below
      every rung — including the first. "We did not look" and "it has not
      started" stay two different facts here exactly as they do in `derive`.
    - **Two-state items never participate.** They are graded without the ladder
      and read identically at every rung, so they carry no information about
      which one was reached. Folding them in would make this whole-sequence
      completeness under another name.
    - **A sequence with no leveled item attains the rung it aims at, never
      more** (`cross-skill-consistency`, B8). Nothing in it measured a scale,
      so no rung above the aim was shown reached; before 0.14.0 this answered
      the ladder's top vacuously, so a pilot-aimed two-state sequence read as
      full-scale with no full-scale run behind it. The aim is
      `evidence["targetLevel"]`; with no aim on the ladder the answer is
      `None`. Sealing stays as unconstrained as before: the rung-skip rule
      compares an aim with this answer, which is that same aim.

    `evidence["levels"]` is the ladder, read from the same key `derive` reads
    it from, so the two can never disagree about which ladder is in play. No
    ladder (`[]`, or the key absent) means no rung name to answer with, and the
    answer is `None`.

    Pure: no I/O, and `evidence` is copied per candidate rather than mutated,
    so a caller's own `targetLevel` survives the call untouched and never
    reaches the grading of a leveled item — attainment is a property of the
    evidence, never of the pass that happens to be reading it. The aim is read
    only as the bound of a sequence with nothing leveled in it.
    """
    levels = evidence.get("levels") or []
    if not any(not item["witness"].get("twostate", True) for item in items):
        aim = evidence.get("targetLevel")
        return aim if aim in levels else None
    # Top down: the first rung that grades attained is the highest one, and
    # `satisfied` is monotone down the ladder (`derived_index >= target_index`),
    # so there is never a lower rung that fails beneath a higher one that
    # passed.
    for level in reversed(levels):
        graded = derive(items, {**evidence, "targetLevel": level})
        if all(result["satisfied"] is True for result in graded
               if not result["twostate"]):
            return level
    return None


def render(header: dict, items: list[dict]) -> str:
    """The block's complete markdown text, opener through closer.

    The inverse of `locate_block` + `parse_items`: splicing this back in is
    how a refresh or an install writes. Item order, marks and text are the
    caller's; this only lays out the fixed grammar around them, so a caller
    that wants marks left untouched for an unmeasured witness passes items
    whose `mark` it never changed.

    `header.get("documents")` (Cut 3, D3): the trailing `documents=` group
    is emitted only when this key is present AND non-empty -- absent or
    empty, the opener's bytes are IDENTICAL to this function's pre-Cut-3
    output, byte for byte. `revision`/`revisionSha256` keep meaning
    document 0 regardless.
    """
    documents = header.get("documents")
    documents_field = (
        f" documents={_encode_extra_documents(documents).decode('ascii')}"
        if documents else "")
    lines = [
        f"<!-- position revision={header['revision']} "
        f"sha256={header['revisionSha256']} derivedAt={header['derivedAt']} "
        f"session={header['session']} target={header['target']}"
        f"{documents_field} -->"
    ]
    for item in items:
        witness = item["witness"]
        operand = witness.get("operand")
        suffix = "" if witness.get("twostate", True) else ":level"
        token = (f"`@{witness['kind']}{suffix} {operand}`" if operand
                else f"`@{witness['kind']}{suffix}`")
        lines.append(f"- [{item['mark']}] {item['ordinal']}. {item['text']} {token}")
    lines.append("<!-- /position -->")
    return "\n".join(lines) + "\n"


def splice(data: bytes, new_block: bytes, block: dict | None) -> bytes:
    """The document's complete new bytes, with only the located span replaced.

    Pure: slicing and concatenation on `bytes`, never `re.sub` or
    `str.replace`. Both interpret characters in a replacement argument —
    `re.sub` treats a leading backslash in the replacement as an escape
    (`\\t`, `\\g<0>`...) — and `AGREED.md` already carries `\\tag{}` and other
    backslash sequences the design cites (lines 197-261 of a real target).
    Slicing at the exact located offsets sidesteps replacement-string
    semantics entirely: `new_block`'s bytes are only ever concatenated, never
    interpreted.

    `block is None` means the document holds no position section yet: the new
    block is appended, preceded by exactly enough blank line(s) to separate it
    from whatever the document already ends with, and everything before that
    point — the file's other 90 hand-curated items, its `Reversed` section —
    is untouched down to the byte.
    """
    if block is None:
        if not data or data.endswith(b"\n\n"):
            return data + new_block
        if data.endswith(b"\n"):
            return data + b"\n" + new_block
        return data + b"\n\n" + new_block
    return data[:block["start"]] + new_block + data[block["end"]:]


def digest_bytes(data: bytes) -> str:
    """The sha256 hex digest of `data`, pure and side-effect-free.

    The one primitive a pre-image capture and `write_spliced`'s own
    re-check both need, so the two sides of a comparison call the
    identical function rather than each computing a hash its own way and
    risking a mismatch that means nothing about the bytes themselves.
    """
    return hashlib.sha256(data).hexdigest()


#: The digest a `defect` declaration or check reads for a path with no
#: regular file at it. A fixed non-hex string, never `None`: `append_event`
#: writes exactly the keys a dict carries (`json.dumps(event, sort_keys=True)`),
#: so a key that was never written and a key written as JSON `null` both
#: collapse to `None` under `event.get("fileSha256")` — this repository has
#: already been bitten by that class (`_derive_record`'s `"recordFound" not
#: in search` check, `_derive_shard`'s `shardsCurrent is None` doctrine).
#: Choosing a string instead of `None` keeps the field's type uniform —
#: always a string when the key is present — so "the key is missing" and
#: "the file is absent" separate cleanly at `.get()` with nothing to
#: remember. `"absent"` cannot collide with a real digest for two
#: independent reasons: a sha256 hex digest is exactly 64 characters, and
#: its alphabet is `[0-9a-f]` — `"absent"` is 6 characters and contains `s`,
#: `n`, `t`. Nothing ever parses this field; it is an opaque equality token
#: with one distinguished value, compared only by `==` against another
#: token from this identical producer.
ABSENT_FILE_DIGEST = "absent"


def current_file_digest(path: Path) -> str:
    """The one producer both a `defect` declaration and a later check call.

    `digest_bytes(path.read_bytes())` for a regular file, `ABSENT_FILE_DIGEST`
    for anything else (absent, a directory, a socket, ...). This is the ONLY
    place absence is tested as a branch anywhere in the mechanism — every
    caller, including `open_defects` below, treats absence as a VALUE this
    function returns, never as a condition of its own to test. That is what
    keeps clearing (see `open_defects`) a single uniform comparison rather
    than a special case that would clear a never-existing path on its first
    check (design decision 1's own bypass, design decision 3's closure of it).
    """
    if path.is_file():
        return digest_bytes(path.read_bytes())
    return ABSENT_FILE_DIGEST


def write_spliced(path: Path, data: bytes, *, expect_digest: str) -> None:
    """Write `data` to `path` by temp file + `os.replace`, same directory --
    but only once `path`'s CURRENT bytes still digest to `expect_digest`.

    `expect_digest` is the pre-image's own digest, captured by the caller
    at the exact read that located whatever offsets `data` was spliced
    against (design decision 2, compare-and-swap on the holder document).
    Keyword-only and carries no default, the identical loud-omission shape
    `impl_availability.launch_available`'s own required argument keeps: a
    caller that forgets to pass one fails the call itself, rather than
    quietly writing over bytes nobody re-checked.

    Re-reads `path` (or treats an absent one as `digest_bytes(b"")`)
    immediately before writing anything at all. On a mismatch, raises
    `Refused("POSITION_HOLDER_MOVED", ...)` and writes nothing -- not even
    a temp file -- so the on-disk bytes are untouched down to the last
    one. A mismatch means the document changed between the read that
    located a section's offsets and this write; the offsets computed
    against the earlier read are never applied to bytes they were not
    actually located against.

    Same-directory temp file so the eventual replace is one filesystem
    rename rather than a cross-device copy, and so a crash mid-write never
    leaves the original truncated: the old file stays exactly as it was
    until the new one is fully written and renamed over it.
    """
    current = path.read_bytes() if path.exists() else b""
    if digest_bytes(current) != expect_digest:
        raise Refused(
            "POSITION_HOLDER_MOVED",
            f"{path} changed between the read that located its section and "
            "this write; refusing rather than splicing offsets computed "
            "against bytes that are no longer there. Measure the section "
            "again and retry -- never assume the earlier read still holds.")
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def read_events(path: Path) -> list[dict]:
    """Every event `.implementation/position.jsonl` holds, oldest first.

    Modeled on the remote-execution ledger's own fold
    (`_load_remote_execution_ledger`, implementation_cli.py:4826-4844): an
    absent file is zero events, not an error, because a target that never
    reached a gate has nothing appended yet. A line that fails to parse is
    skipped rather than raising — the ledger this mirrors already treats a
    corrupt line as silently absent evidence rather than a reason to refuse
    every read that follows it.
    """
    if not path.exists():
        return []
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def append_event(path: Path, event: dict) -> None:
    """Append one JSON line to `.implementation/position.jsonl`, creating it.

    Append-only, on purpose: `remote-execution/SKILL.md`'s own rationale for
    its ledger ("Why append, not a status record") applies unchanged here — a
    lost append is detectable (the newest `gate` a caller expects is simply
    missing), and a lost in-place mutation is not.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True))
        handle.write("\n")


def open_defects(events: list[dict], forge_root: Path) -> list[dict]:
    """Every currently-open `defect` declaration, latest-wins per file.

    `forge_root` is an explicit argument, never imported (`impl_guards`'
    own doctrine, restated for this module in design decision 8): this
    module stays ignorant of the caller's own layout, and one derivation
    serves both a refusal guard and a diagnostic report, so the two can
    never disagree about what "open" means.

    Clearing is ONE uniform comparison — `current_file_digest(path) !=
    recorded` — with no existence branch anywhere in this function. Absence
    enters only as a VALUE `current_file_digest` returns for the recorded
    file, never as a condition this function evaluates for itself; see that
    function's own docstring for why the difference is load-bearing.

    Two checks run before the comparison, both independent of file
    existence:

    - a `kind: "defect"` event with no `fileSha256` key at all (`.get()`
      reads `None`) is treated as OPEN unconditionally — fail closed, per
      design decision 2. It can only be hand-written or truncated; its own
      exit is a fresh `defect` declaration for the same file, which
      supersedes it under latest-wins and then clears by editing.
    - a stored `file` that does not resolve under `forge_root/skills`
      is rejected outright — the containment invariant `cmd_defect`
      enforces at declaration is re-verified for free on this read side, so
      a hand-written ledger line can never point this checker outside the
      forge tree it is allowed to name.

    Latest-wins: `events` is oldest-first (`read_events`'s own contract), so
    a later `kind: "defect"` event for the same `file` simply overwrites an
    earlier one in the fold below — the newest declaration is always the one
    compared.
    """
    forge_root = forge_root.resolve()
    skills_root = forge_root / "skills"
    latest: dict[str, dict] = {}
    for event in events:
        if event.get("kind") != "defect":
            continue
        file_field = event.get("file")
        if not isinstance(file_field, str):
            continue
        resolved = (forge_root / file_field).resolve()
        try:
            resolved.relative_to(skills_root)
        except ValueError:
            continue
        latest[file_field] = event

    still_open = []
    for file_field, event in latest.items():
        recorded = event.get("fileSha256")
        if recorded is None:
            still_open.append(event)
            continue
        if current_file_digest(forge_root / file_field) == recorded:
            still_open.append(event)
    return still_open
