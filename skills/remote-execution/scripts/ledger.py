#!/usr/bin/env python3
"""Append-only ledger for forge-owned remote execution.

A submission to a remote worker is a fact once it happens, and facts are not
edited — only added to. This module owns the append path — appending one
JSON-encoded event to `<target>/<Name>/.remote-execution/ledger.jsonl`, one
line per event, opened `O_APPEND`, never rewritten and never deleted — and
the fold: deriving "what is the current state of this entrypoint" from that
log, including the currency rule that tells a fresh result from a stale one.
No mutable "current status" record is ever stored; every answer `fold()`
gives is recomputed from the log each time it is called.

Ledger CODE is forge-owned. Ledger DATA lives inside the target's own git
checkout, because it is a per-repository record of what that repository
submitted, not something the forge should hold on anyone's behalf.

Why an append is trustworthy at all rests on four things held together, and
only two of them are this module's job:

- `O_APPEND` on a regular, local file makes seek-to-end-and-write atomic as a
  unit with respect to other appenders, so two concurrent writers cannot
  interleave into the same region. That guarantee is unconditional; it does
  not depend on any buffer-size constant, `PIPE_BUF` included.
- The return value of `os.write()` is checked against the byte count, and a
  mismatch raises. A write CAN legitimately return short, and a short write
  is exactly what tears a JSONL line. This check is the actual defence
  against that, not the append call's mere existence.
- No `io` buffering: `open(path, "a")` may split one logical write across
  syscalls, which would reintroduce the interleaving `O_APPEND` exists to
  prevent. `append()` here always goes through `os.open`/`os.write` on a raw
  fd, one `os.write()` per event.
- Local filesystem only — NFS does not honor `O_APPEND` atomicity. That is a
  precondition stated in `SKILL.md`, not something this module can enforce.

Run with any Python 3.10+ (stdlib-only):
    python3 -m unittest tests.test_remote_execution
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Mapping

# A ledger event has no business being large: the fields are a path, a
# 64-hex digest, an opaque id, a worker name and a timestamp — ~300 B
# observed — plus an errored.reason already truncated below. Exceeding this
# means a field that should have been truncated was not, so raising is the
# correct response.
#
# This is a sanity bound on OUR OWN schema, and deliberately NOT `PIPE_BUF`.
# `PIPE_BUF` governs atomicity of writes to pipes and FIFOs, and says nothing
# about regular files — which is what this ledger is. Its value is also
# platform-specific: 512 on darwin (`os.pathconf('/tmp', 'PC_PIPE_BUF')`),
# 4096 on Linux. Re-deriving this cap from it would be a number borrowed
# from the wrong object, and on this platform, from the wrong operating
# system.
MAX_EVENT_BYTES = 4096

# Unlike every other field in this schema, `errored.reason` has no natural
# size limit at the call site — an exception's full text, a service's raw
# error body. It is truncated here, at construction, so a runaway reason can
# never be what pushes an otherwise routine failure record over the
# line-level cap above.
MAX_REASON_CHARS = 512


class LedgerError(Exception):
    """An append could not be trusted to have landed as a whole event."""


# Written into a ledger directory the moment `_ensure_local_state_dir()`
# first creates it — see that function's docstring for why every byte
# under such a directory is excluded, not only the ledger files.
_LOCAL_STATE_GITIGNORE = (
    "# Written by ledger.py::append() the moment this directory was first\n"
    "# created. Everything under here — fetched artifacts and ledger files\n"
    "# alike — is this repository's own local remote-execution\n"
    "# bookkeeping: reproducible or per-machine, never something a fresh\n"
    "# clone needs. A manual .gitignore edit in one target's checkout does\n"
    "# not help the next one; this file exists so no target needs that\n"
    "# edit at all.\n"
    "*\n"
)


def _ensure_local_state_dir(directory: Path) -> None:
    """Create `directory` if missing, and make sure it carries its own
    `.gitignore` from the moment it exists.

    This directory (`<target>/<product>/.remote-execution/`) is created
    afresh for every target/product pair this module is ever pointed at.
    A human fixing one existing target's root `.gitignore` by hand fixes
    exactly that one repository and leaves the next target with the same
    untracked-66-MB defect. Writing the ignore file HERE, at the one
    place this module creates the directory, is what closes the gap for
    every target, not just the one already caught.

    Deliberately a proactive WRITE, not the harder refusal
    `kaggle-accounts`' `accounts_cli.assert_ignored()` uses before storing
    a credential: that function's entire protection model IS the ignore
    rule, and its failure mode (a leaked token) is irreversible. A ledger
    event is not a credential — an unignored ledger file is a
    history-hygiene annoyance, cleanable after the fact with `git rm
    --cached`, never a secret leak. That asymmetry is why this writes the
    file instead of blocking the caller who did nothing wrong.
    """
    directory.mkdir(parents=True, exist_ok=True)
    gitignore_path = directory / ".gitignore"
    if not gitignore_path.exists():
        gitignore_path.write_text(_LOCAL_STATE_GITIGNORE, encoding="utf-8")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def submitted_event(
    *,
    entrypoint: str | Path,
    source_digest: str,
    submission_id: str,
    worker: str,
    requested_capacity: int,
    granted_capacity: int,
    ts: str | None = None,
    slot: int | None = None,
) -> dict:
    """Build a `submitted` event.

    `slot` is the concurrent slot of `worker` this submission occupies when
    one campaign sends several submissions of the same entrypoint to the
    same worker (S1, parallel campaigns). Slot 1 -- and every submission
    that is not one of several -- carries no `slot` field at all, so such
    an event is byte-identical to one written before slots existed. A
    `slot` of 2 or more puts the submission in its own lane of the fold
    (`lane_key()`), so it neither supersedes nor is superseded by slot 1.

    `entrypoint` — not `notebook` — is the field name for the thing executed
    remotely. The dataclass and adapter seam that will carry this same value
    around (a later task) name it the same way: this schema and that seam
    agree on one vocabulary for "the thing that runs", and neither one
    smuggles in a format opinion about it.
    """
    event: dict = {
        "kind": "submitted",
        "ts": ts or _now(),
        "entrypoint": str(entrypoint),
        "sourceDigest": source_digest,
        "submissionId": submission_id,
        "worker": worker,
        "requestedCapacity": requested_capacity,
        "grantedCapacity": granted_capacity,
    }
    if slot is not None and slot != 1:
        event["slot"] = slot
    return event


SLOT_LANE_SEPARATOR = "#slot"


def lane_key(submission: Mapping[str, object]) -> tuple[str, str]:
    """The `(entrypoint, lane)` key a `submitted` event is folded under.

    The lane is the worker itself for every event without a `slot` field
    (and for slot 1): exactly the `(entrypoint, worker)` key every reader
    already indexes. A submission in slot `n >= 2` of a worker gets the
    lane `<worker>#slot<n>`: two concurrent submissions of one entrypoint
    to one worker are two independent "latest" facts, never one superseding
    the other -- the same reason `latest` was keyed by worker at all.
    `pending_for()` counts a worker's lanes by the event's own `worker`
    field, never by parsing this key.
    """
    entrypoint = str(submission["entrypoint"])
    worker = str(submission["worker"])
    slot = submission.get("slot")
    if slot is None or slot == 1:
        return (entrypoint, worker)
    return (entrypoint, f"{worker}{SLOT_LANE_SEPARATOR}{slot}")


def returned_event(
    *,
    submission_id: str,
    artifact_path: str | Path,
    observed_concurrency: int,
    ts: str | None = None,
) -> dict:
    """Build a `returned` event."""
    return {
        "kind": "returned",
        "ts": ts or _now(),
        "submissionId": submission_id,
        "artifactPath": str(artifact_path),
        "observedConcurrency": observed_concurrency,
    }


def errored_event(*, submission_id: str, reason: str, ts: str | None = None) -> dict:
    """Build an `errored` event, with `reason` truncated to 512 chars."""
    return {
        "kind": "errored",
        "ts": ts or _now(),
        "submissionId": submission_id,
        "reason": reason[:MAX_REASON_CHARS],
    }


def append(path: str | Path, event: Mapping[str, object]) -> None:
    """Append one event as a single JSON line, or raise without recording it.

    Serialization and the size check both happen before any filesystem call,
    so a rejected event never creates the ledger file or its parent
    directory. Once the write is attempted, a short write is the one failure
    this function cannot undo: the partial bytes it already put on disk stay
    there. The caller must treat the event as unrecorded and must not retry
    blindly onto the same fd — the tail left behind is a corrupted line, and
    handling that is the next fold's job (a later module), not a repair
    attempted here.
    """
    line = json.dumps(event, sort_keys=True) + "\n"
    payload = line.encode("utf-8")

    if len(payload) > MAX_EVENT_BYTES:
        raise LedgerError(
            f"event is {len(payload)} bytes, over the {MAX_EVENT_BYTES}-byte "
            "sanity cap for this schema; a field that should have been "
            "truncated was not"
        )

    path = Path(path)
    _ensure_local_state_dir(path.parent)

    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        written = os.write(fd, payload)
    finally:
        os.close(fd)

    if written != len(payload):
        # A large write CAN legitimately return short, and a short write is
        # exactly what tears a JSONL line. A torn line is a lost submission,
        # which is the one outcome this ledger exists to make impossible, so
        # this fails loudly rather than trusting os.write() to have done the
        # whole job silently.
        raise LedgerError(
            f"short write on append: wrote {written} of {len(payload)} "
            f"bytes to {path}; treat this event as unrecorded"
        )


# --------------------------------------------------------------------------
# The fold: deriving current state from the append-only log.
# --------------------------------------------------------------------------

_TERMINAL_KINDS = ("returned", "errored")


@dataclass(frozen=True)
class EntrypointState:
    """Where one entrypoint stands after folding the log.

    `state` reflects only the entrypoint's LATEST submission's own terminal
    event (or the absence of one) — a `returned` event that belongs to a
    SUPERSEDED submission never promotes this to "returned". That event is
    instead reported through `LedgerState.from_stale_submission` and
    quarantined; it never touches what this entrypoint's current picture
    says.
    """

    state: str  # "pending" | "returned" | "errored"
    stale_in_flight: bool


@dataclass
class LedgerState:
    """The result of folding a ledger's lines. Derived, not stored.

    Nothing here is a fact on its own — every field is recomputed from the
    log each time `fold()` runs. A mutable "current status" record is
    exactly what this ledger's append-only design exists to avoid: a lost
    append is detectable (the reader can count lines against what it
    expects), a lost in-place mutation is not.
    """

    by_id: dict[str, dict]
    latest: dict[tuple[str, str], dict]
    entrypoints: dict[tuple[str, str], EntrypointState]
    verdicts: dict[str, str]
    unreadable_lines: int

    @property
    def stale_in_flight(self) -> tuple[str, ...]:
        """Entrypoints with a pending submission the source has moved past.

        Named by ENTRYPOINT alone, deduplicated — an entrypoint counts as
        stale-in-flight if ANY of its workers is, even though `entrypoints`
        itself is now keyed by `(entrypoint, worker)` (Decision 6). JSON has
        no tuple key, `stale_in_flight` is consumed as a flat name list by
        every existing caller, and nesting this one too would be a second
        breaking shape change buying nothing over the first.

        Reported, never acted on — see `fold()`'s note on why this function
        never calls `cancel()`.
        """
        return tuple(
            sorted(
                {
                    entrypoint
                    for (entrypoint, _worker), state in self.entrypoints.items()
                    if state.stale_in_flight
                }
            )
        )

    @property
    def from_stale_submission(self) -> tuple[str, ...]:
        """Entrypoints with at least one quarantined, never-merged result."""
        stale_entrypoints = {
            self.by_id[submission_id]["entrypoint"]
            for submission_id, verdict in self.verdicts.items()
            if verdict == "fromStaleSubmission" and submission_id in self.by_id
        }
        return tuple(sorted(stale_entrypoints))

    def pending_for(self, worker: str) -> int:
        """Count entrypoints whose LATEST submission targets `worker` and is
        still pending.

        This is what the packer's capacity clamp (a later module) treats as
        concurrent work already committed to `worker` before granting any
        more. Only an entrypoint's latest submission FOR THIS WORKER is
        ever considered — `self.latest` is keyed by `(entrypoint, worker)`
        (Decision 6), so a resubmission by a DIFFERENT worker to the same
        entrypoint can never shadow or double-count this one's own latest
        submission, and an older, superseded submission from this same
        worker can never be double-counted either: it stopped being what
        this `(entrypoint, worker)` pair's state answers for the moment a
        newer submission from the SAME worker superseded it. A worker's
        slot lanes (`lane_key()`) each count once: two concurrent slots of
        one campaign are two submissions in flight on that worker.
        """
        return sum(
            1
            for key, submission in self.latest.items()
            if submission.get("worker") == worker
            and self.entrypoints[key].state == "pending"
        )


def fold(lines: Iterable[str], live_digest: str | Callable[[], str]) -> LedgerState:
    """Derive current per-entrypoint state from the append-only log.

    Append order IS the total order this function honors, full stop. `ts` is
    a field carried on every event for a human reading the raw file, and it
    is NEVER used to order or compare events here: two machines submitting
    to the same ledger can disagree about the time, and sorting by a value
    one of them wrote would reorder events the filesystem's `O_APPEND`
    already ordered correctly. `lines` is trusted to already be in that
    order — the order the caller read them off disk — and this function
    does not second-guess it.

    `live_digest` is the source digest to judge recorded submissions
    against, taken as data rather than computed in here. This module stays
    stdlib-only and target-blind on purpose: the dependency direction for
    this whole skill is `remote_cli -> packer -> ledger -> adapter`, one
    way, and the actual `source_digest()` lives in proposal-implementation's
    own module, which is the one that knows what a target's source tree is.
    Importing it from here would point that arrow the wrong way for no
    benefit `fold()` itself needs. A caller that already knows how to
    compute a fresh digest passes a string; if computing one is not free, it
    passes a zero-argument callable instead, and this function pays for it
    at most once per call — not once per event or per entrypoint.

    Two passes over `lines`, not one. The first resolves `by_id` and
    `latest` — facts about the WHOLE log. The second computes each
    `returned` event's verdict against those resolved facts. A single
    forward pass would get this wrong: a result that looked current the
    moment it arrived can become `fromStaleSubmission` the instant a LATER
    resubmission lands, even though the log line itself never changes. Since
    `fold()` is a batch computation that can run long after every event in
    the log has landed, "latest" has to mean latest across the whole log,
    not "latest as of wherever this loop has read so far".
    """
    live = live_digest() if callable(live_digest) else live_digest

    by_id: dict[str, dict] = {}
    latest: dict[str, dict] = {}
    latest_position: dict[tuple[str, str], int] = {}
    terminal_by_id: dict[str, tuple[int, dict]] = {}
    # Position travels with each `returned` event too (mirrors
    # `terminal_by_id`, Part B): the verdicts loop below needs it for the
    # same reason the entrypoints-settle loop does — see that loop's verdict
    # override for why.
    returned_events: list[tuple[int, dict]] = []
    unreadable_lines = 0

    for position, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not line:
            continue

        try:
            event = json.loads(line)
            if not isinstance(event, dict) or "kind" not in event:
                raise ValueError("not a ledger event")
        except (json.JSONDecodeError, ValueError):
            # A corrupted or truncated line is exactly what a short write
            # (see append()) or a process killed mid-append leaves behind.
            # It is skipped and counted here, never repaired and never
            # rewritten: repairing it would mean inventing a fact this
            # ledger never actually recorded, and rewriting the file is the
            # one operation the append-only design exists to rule out.
            unreadable_lines += 1
            continue

        kind = event.get("kind")
        if kind == "submitted":
            # Last-write-wins by submissionId is intentional, not a defect
            # (Part C1): on an identity-stable backend `by_id[id]` means
            # "the most recent submission under this id", which models a
            # mutable remote object (a Kaggle kernel gets overwritten in
            # place by each resubmission) rather than one execution per id.
            # `cmd_fetch` fetches BY id, and the service's current output
            # belongs to its newest run under that id — so resolving to the
            # last record read is correct here; append position (Part B)
            # is what the fold's ENTRYPOINT-keyed state needs instead, and
            # is threaded separately via `latest_position`.
            by_id[event["submissionId"]] = event
            # Overwritten every time a submitted event for this EXACT
            # (entrypoint, worker) pair is seen, in the order this loop
            # sees them — append order, not `ts`. The last write wins, same
            # as it would for any other last-one-in-wins index over an
            # ordered log. Keyed by the pair, not the entrypoint alone
            # (Decision 6): five accounts submitting the same entrypoint
            # are five independent "latest" facts, one per worker, not one
            # fact where the fourth and fifth submissions read as
            # superseding the first three.
            latest_key = lane_key(event)
            latest[latest_key] = event
            latest_position[latest_key] = position
        elif kind in _TERMINAL_KINDS:
            # Position travels WITH the event in one tuple so the two can
            # never diverge (Part B): an identity-stable backend (Kaggle)
            # mints the SAME submissionId across repeated submissions of
            # one (entrypoint, worker) pair, so a terminal event recorded
            # here can belong to an EARLIER submission than the one
            # `latest` now holds for that pair. The entrypoints-settle loop
            # below compares this position against `latest_position` to
            # tell "settles the latest submission" apart from "stale
            # terminal from a submission that was since superseded".
            terminal_by_id[event["submissionId"]] = (position, event)
            if kind == "returned":
                returned_events.append((position, event))
        # Any other kind parses cleanly and is simply one this fold does not
        # act on yet — forward-compatible, not corrupted.

    verdicts: dict[str, str] = {}
    for position, event in returned_events:
        submission = by_id.get(event["submissionId"])
        if submission is None:
            # A returned event naming a submission this log never recorded
            # is a reconciliation concern (a later task's territory, not
            # this fold's) — the line parsed cleanly, so it is not counted
            # as unreadable. It simply contributes no verdict.
            continue
        verdict = currency_verdict(submission, latest, live)
        if verdict == "current":
            # currency_verdict()'s id-equality half is structurally inert on
            # an identity-stable backend (Part C2): `submission` came from
            # `by_id`, which is last-write-wins (Part C1), so `submission`
            # is already the SAME record `latest[key]` holds and the id
            # comparison inside currency_verdict can never disagree with
            # itself. That half's guarding duty — catching a `returned`
            # event that settles an EARLIER submission than the one now on
            # record — relocates here: THIS event's own append position,
            # compared against the latest `submitted` position recorded for
            # its (entrypoint, worker) pair, is the fact that still tells
            # "settles the latest submission" apart from "stale result from
            # a submission since superseded". Applying it only when
            # currency_verdict already said "current" leaves a digest-moved
            # verdict (the OTHER, backend-independent half) untouched — this
            # is an additional check, not a replacement for that one.
            key = lane_key(submission)
            if position < latest_position[key]:
                verdict = "fromStaleSubmission"
        verdicts[event["submissionId"]] = verdict

    entrypoints: dict[tuple[str, str], EntrypointState] = {}
    for key, submission in latest.items():
        entry = terminal_by_id.get(submission["submissionId"])
        # A terminal event whose append position precedes this pair's
        # latest `submitted` event settled an EARLIER submission that has
        # since been superseded — it never gets to promote this entrypoint
        # out of "pending", even though `terminal_by_id` is keyed by the
        # (colliding) submissionId alone. Without this check, an
        # identity-stable backend's stale terminal would misread as
        # settling the resubmission it precedes.
        if entry is None or entry[0] < latest_position[key]:
            state = "pending"
        elif entry[1]["kind"] == "returned":
            state = "returned"
        else:
            state = "errored"

        # staleInFlight is orthogonal to state on purpose: it only ever
        # applies to a submission still waiting on a result. A submission
        # that already returned or errored is a settled fact, not an
        # in-flight one, however stale the source has since become.
        stale_in_flight = state == "pending" and submission["sourceDigest"] != live

        entrypoints[key] = EntrypointState(
            state=state, stale_in_flight=stale_in_flight
        )

    return LedgerState(
        by_id=by_id,
        latest=latest,
        entrypoints=entrypoints,
        verdicts=verdicts,
        unreadable_lines=unreadable_lines,
    )


def currency_verdict(
    submission: Mapping[str, object], latest: Mapping[tuple[str, str], dict], live: str
) -> str:
    """The currency rule a `returned` event's submission is judged by.

    Public — not just `fold()`'s own internal helper — because `fetch()`
    (a later module) has to classify a submission's currency BEFORE a
    `returned` event exists to fold over: the quarantine-vs-normal
    placement decision has to be made at materialize time, from the same
    rule, not a second reimplementation of it that could quietly drift from
    this one.

    Both halves below are load-bearing, but not for every backend equally
    (Part C2) — each covers a different class:

    - `superseded` (id-equality) catches a resubmission at an UNCHANGED
      digest — a retry after a service failure, where the source never
      moved but an older submission id is no longer the one that matters.
      Digest-equality alone would miss this: the old submission's recorded
      digest still equals the live one, so a digest-only check would call
      its result current. This half is load-bearing for a FRESH-ID-PER-CALL
      backend (every `submit()` mints a new, distinct id) — proved
      reachable by `test_resubmission_at_unchanged_digest_still_marks_
      earlier_result_stale`. On an IDENTITY-STABLE backend (Kaggle-shaped:
      the same `(worker, entrypoint)` always mints the same id), this half
      is structurally INERT: `by_id[id]` and `latest[(entrypoint, worker)]`
      resolve to the SAME record once ids repeat, so `latest_for_key !=
      submission` can never be true — pinned by
      `test_retry_at_unchanged_digest_under_a_stable_id_reads_current`. Its
      guarding duty does not vanish there; it relocates to `fold()`'s
      append-position checks — BOTH of them, not just one: the
      `entrypoints`-settle loop (Part B) protects `pending_for()`/the
      packer clamp, and a SEPARATE positional check in the verdicts loop
      (immediately after this function is called, guarding only its
      `"current"` answers) protects `LedgerState.verdicts` and
      `from_stale_submission` — the field `remote_cli.py` surfaces
      directly as the CLI's `"quarantined"` output. An earlier version of
      this docstring named only the `entrypoints` relocation; that
      understated the claim; verify report `sdd/the-id-that-repeats-
      by-construction/verify-report` (engram #1134) traced the gap to a
      consumer this docstring had not accounted for. Both relocations are
      proved by the SAME test,
      `test_positional_guard_catches_what_id_equality_
      would_catch_on_a_fresh_id_backend`, which asserts on
      `entrypoints`, `verdicts`, AND `from_stale_submission` together.
    - `sourceMoved` (digest-equality) catches the opposite: the same
      submission is still the latest one on record — no resubmission
      happened — yet the source has moved again since it was submitted.
      Id-equality alone would miss this: the id still matches the latest
      one, so an id-only check would call this result current too. This
      half is load-bearing for BOTH backend classes: it is orthogonal to
      how ids are minted.

    `latest` is keyed by `(entrypoint, worker)` (Decision 6): this reads
    only the SAME worker's own latest submission for this entrypoint, so a
    different worker's resubmission of the same entrypoint can never mark
    this one superseded. A caller passing an old, entrypoint-only-keyed
    `latest` dict fails CLOSED here, not open: `.get()` on a mismatched key
    shape finds nothing, `latest_for_key` is `None`, and the submission is
    over-quarantined as superseded rather than falsely admitted as current.

    Either check alone lets a superseded result read as current, which is
    the one defect class this whole ledger exists to prevent. A submission
    this log never recorded (a defensive case that should not arise given
    `submission` always comes from `by_id`) is treated as superseded rather
    than current — this rule fails closed, not open.
    """
    latest_for_key = latest.get(lane_key(submission))
    superseded = (
        latest_for_key is None
        or latest_for_key["submissionId"] != submission["submissionId"]
    )
    source_moved = submission["sourceDigest"] != live
    current = not superseded and not source_moved
    return "current" if current else "fromStaleSubmission"
