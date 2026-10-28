#!/usr/bin/env python3
"""The capacity clamp: what a repository asks for, clamped to what a worker allows.

The settled rule this module exists to enforce, and enforce in exactly one
place: the adapter states the cap, the repository states the request, and
this module — never either of those two — does the clamping. Neither side
is trusted to know the other's fact. How many jobs a worker will run at
once is a fact about the service, so it is read here only through
`adapter.workers()`, never accepted as a parameter from a caller and never
hardcoded. How many the repository WANTS to use of that is the repository's
own declared intent, handed in as `requested` by whoever calls `plan()` —
this module never guesses it and never defaults it.

`plan()` reports `requested`, `cap`, `inFlight` and `granted` as four
separate numbers on purpose. A clamp collapsed down to `granted` alone is
indistinguishable from an unclamped grant that merely happens to equal the
same number — a caller asking for five and receiving two because the
service caps at two looks identical, from `granted` alone, to a caller
asking for exactly two and receiving it. Those are different facts to know
before spending an afternoon waiting on a service, and this module keeps
them different by never collapsing them into one number in the first place.

Three functions read that one clamp at three different scopes, never a
fourth kind of number invented for any of them. `plan()` answers for ONE
named worker — a fact about that worker alone. `select()` walks every
worker `adapter.workers()` reports, in that same declared order, and
returns the first one whose health can be established and that still has
room; it stops at the first healthy account, a one-account probe.
`distribute()` walks every worker too, but never stops early: it reads
`plan()` for each one, sums what every healthy account actually grants
into one total, and spreads a caller's own opaque work units across that
total round-robin. One worker's clamp — `select()`'s whole concern — is
one case among many `distribute()` reads the exact same way, never a
special one it treats differently.

Depends only on `adapter.py`'s ABC (`plan()` requires a real `Adapter`
instance, checked structurally, not merely documented) and `ledger.py`'s
`fold()` (to learn what is already in flight before granting more). Names
no backend and holds no service-specific knowledge; nothing below this
module's own two dependencies is ever imported.

Run with any Python 3.10+ (stdlib-only):
    python3 -m unittest tests.test_remote_execution
"""
from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence


def _load_sibling(module_name: str, filename: str):
    """Path-import a sibling module from this same directory, reusing an
    already-loaded copy under `module_name` when one exists.

    This skill's scripts are not a package — there is no `__init__.py`, on
    purpose, so the skill stays runnable with a bare `python3` and no
    install step — so a cross-module dependency inside it goes by file
    path, the same technique `tests/test_remote_execution.py` already uses
    for every module in this skill.

    The reuse check is not an optimization; it is a correctness requirement.
    `ledger.py`'s `LedgerState` and `adapter.py`'s `Worker`/`Adapter` are
    dataclasses and an ABC. Two separately exec'd copies of the same source
    file produce two DISTINCT class objects with the same name — an
    `isinstance` check made against one copy would silently fail against an
    instance built by the other, even though the source is byte-identical.
    Checking `sys.modules` first, and only loading fresh when nothing is
    there yet, is what keeps this module and whatever already loaded its
    dependencies talking about the same classes.
    """
    if module_name in sys.modules:
        return sys.modules[module_name]
    script = Path(__file__).resolve().parent / filename
    spec = importlib.util.spec_from_file_location(module_name, script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


LEDGER = _load_sibling("remote_execution_ledger", "ledger.py")
ADAPTER = _load_sibling("remote_execution_adapter", "adapter.py")


class PackerError(Exception):
    """A plan could not be computed from what the adapter and ledger state."""


@dataclass(frozen=True)
class Plan:
    """One capacity decision for one named worker, with the clamp kept
    visible — the single case `select()` returns the first healthy
    instance of, and the same case `distribute()` computes for every
    worker in a whole set and then sums, never a second, richer shape
    invented for either caller.

    Every field here is a distinct fact; none is derivable from another
    without also knowing at least one more:

    - `requested` — what the repository's own config declared it wants.
    - `cap` — what `adapter.workers()` states this worker allows, read
      fresh at plan time, never cached across calls and never hardcoded.
    - `in_flight` — how much of that cap is already committed, per
      `in_flight_source` below.
    - `granted` — `max(0, min(requested, cap) - in_flight)`. Never negative:
      a worker already at or over its cap grants zero, not a negative
      number that would otherwise have to be clamped again downstream.
    - `in_flight_source` — `"list_active"` when the adapter answered and
      that live count was used, `"ledger"` when it did not (or raised) and
      the ledger's own fold supplied the count instead. This is what keeps
      a live-refined `in_flight` from being reported with the same
      confidence as a fallback estimate that merely carries the same value.
    """

    worker: str
    requested: int
    cap: int
    in_flight: int
    granted: int
    in_flight_source: str


@dataclass(frozen=True)
class Assignment:
    """One worker's slice of a `distribute()` call: the WHOLE `Plan` that
    granted these places, never a copied-out `granted` number alone. The
    same doctrine `Plan` itself enforces one arity up — collapsing this
    down to a bare integer would make a clamped grant indistinguishable
    from an unclamped one, exactly the confusion `Plan`'s four separate
    fields exist to prevent.

    `units` holds this worker's assigned identities, in the order they were
    handed to `distribute()`. A worker that was granted capacity but had no
    units left to receive still appears here, with `units=()` — "had room,
    didn't need it" is a different fact than "had no room", so it is never
    folded into `skipped`.
    """

    plan: Plan
    units: tuple[str, ...]


@dataclass(frozen=True)
class Skip:
    """One worker `distribute()` granted zero places to, and why —
    `reason` is triage's own message, unprefixed by the worker id `worker`
    already carries.
    """

    worker: str
    reason: str


@dataclass(frozen=True)
class Distribution:
    """The result of one `distribute()` call. Four separate facts, on
    purpose, the same way `Plan` refuses to collapse its own four fields
    into one: `units` (what was handed in), `places` (total granted
    capacity), `assignments` (who got what), and `unplaced` (what did not
    fit, by identity). There is deliberately no `complete: bool` field —
    a boolean is exactly the collapse this module exists to refuse;
    `unplaced` already carries the fact, richer than a flag ever could.

    Two invariants hold for every `Distribution` this module returns:
    every unit in `units` appears exactly once across `assignments` and
    `unplaced` combined (conservation — nothing vanishes), and the set of
    workers named across `assignments` and `skipped` equals
    `adapter.workers()` exactly (no account disappears silently).
    """

    units: tuple[str, ...]
    places: int
    assignments: tuple[Assignment, ...]
    unplaced: tuple[str, ...]
    skipped: tuple[Skip, ...]


def plan(
    *,
    adapter: "ADAPTER.Adapter",
    worker_id: str,
    requested: int,
    ledger_lines: Iterable[str],
    live_digest: str | Callable[[], str],
) -> Plan:
    """Clamp `requested` concurrent jobs on `worker_id` to what the adapter
    and the ledger together say is actually available right now.

    `adapter` must be a real `Adapter` instance — checked structurally here,
    the same discipline `adapter.py`'s own ABC uses to refuse an incomplete
    subclass, rather than trusting a caller to have passed the right shape
    of object. `cap` is discovered through `adapter.workers()` and no other
    route: this module accepts no `cap` or `capacity` parameter from its
    caller, because the cap is not this module's fact, or the caller's, to
    assert — it is the adapter's alone.

    `in_flight` starts as `fold(ledger_lines, live_digest).pending_for(worker_id)`
    — every entrypoint whose latest submission to this worker has neither
    returned nor errored yet. `adapter.list_active(worker_id)` then refines
    that count when the adapter answers, because the ledger only ever
    reflects what THIS repository last recorded submitting, while
    `list_active()` reflects what the service itself currently considers
    active. When `list_active()` raises — the service unreachable, refusing,
    or timing out — this function falls back to the ledger-derived count
    rather than propagating the failure, but it says so through
    `Plan.in_flight_source` rather than reporting a bare number with no
    indication of where it came from.
    """
    if not isinstance(adapter, ADAPTER.Adapter):
        raise PackerError(
            f"{adapter!r} is not an Adapter instance; capacity is discovered "
            "through the adapter seam only, never accepted some other way"
        )

    workers_by_id = {worker.id: worker for worker in adapter.workers()}
    if worker_id not in workers_by_id:
        raise PackerError(f"adapter reports no worker named {worker_id!r}")
    cap = workers_by_id[worker_id].capacity

    state = LEDGER.fold(ledger_lines, live_digest)
    in_flight = state.pending_for(worker_id)
    in_flight_source = "ledger"

    try:
        in_flight = len(adapter.list_active(worker_id))
        in_flight_source = "list_active"
    except ADAPTER.WorkerUnauthorized:
        # NOT swallowed: a revoked or otherwise unauthorized credential is
        # a decision-bearing fact, never a mere "service unreachable" one.
        # Folding it into the ledger fallback below would make a revoked
        # account report exactly like a healthy one whose live count
        # merely could not be confirmed — the one confusion this
        # exception exists to make structurally impossible. Every OTHER
        # exception below still degrades to the ledger, unchanged.
        raise
    except Exception:
        # Unreachable, refusing, or timed out: the ledger-derived count
        # computed above is already in `in_flight` and stays there. This is
        # a refusal to trust a number the service could not actually
        # confirm, not a fabricated "it must still be running" guess.
        pass

    granted = max(0, min(requested, cap) - in_flight)

    return Plan(
        worker=worker_id,
        requested=requested,
        cap=cap,
        in_flight=in_flight,
        granted=granted,
        in_flight_source=in_flight_source,
    )


def _triage(
    *,
    adapter: "ADAPTER.Adapter",
    worker: "ADAPTER.Worker",
    requested: int,
    ledger_lines: Iterable[str],
    live_digest: str | Callable[[], str],
) -> tuple[Plan | None, str | None]:
    """Decide whether ONE worker counts as healthy-and-grantable, the exact
    per-worker branch `select()` used to inline in its own loop. Returns
    `(plan, None)` when it does, `(None, reason)` when it does not — never
    both, never neither. `reason` is the same three exact messages
    `select()` has always produced, unprefixed by `worker.id` (a caller
    that already has the worker identity separately, like `distribute()`'s
    `Skip`, does not need it repeated inside the message itself).

    A private helper, not a shared body: `select()` calls this once per
    worker and returns on the FIRST healthy one — a one-account live probe.
    `distribute()` calls this once per worker too, but never stops early —
    an N-account probe. Rewriting `select()` as
    `distribute(units=(x,))[0]` would turn its one-account probe into an
    N-account one against a live service, which is why the two share this
    triage step and nothing more.
    """
    try:
        candidate = plan(
            adapter=adapter,
            worker_id=worker.id,
            requested=requested,
            ledger_lines=ledger_lines,
            live_digest=live_digest,
        )
    except ADAPTER.WorkerUnauthorized as exc:
        return None, f"unauthorized ({exc})"

    if candidate.in_flight_source != "list_active":
        return None, (
            "live capacity evidence unavailable (service "
            "unreachable or refusing) — not counted healthy"
        )

    if candidate.granted < 1:
        return None, (
            f"no capacity granted right now "
            f"(cap={candidate.cap}, in_flight={candidate.in_flight})"
        )

    return candidate, None


def select(
    *,
    adapter: "ADAPTER.Adapter",
    requested: int,
    ledger_lines: Iterable[str],
    live_digest: str | Callable[[], str],
) -> Plan:
    """Choose a worker with no caller-supplied name, walking
    `adapter.workers()` in the DECLARED order (the accounts CLI's own
    stable order — this module invents no ordering of its own) and
    returning the first one whose health can be established and that has
    at least one slot to grant.

    A worker counts as HEALTHY for this purpose only when BOTH of these
    hold, distinguished by the exact two fields `plan()` already reports
    rather than by a second, separate health probe this function would
    otherwise have to invent:

    - `plan()` did not raise `ADAPTER.WorkerUnauthorized` — the backend's
      own distinct signal that this worker's credential is refused, never
      swallowed here or in `plan()` itself.
    - `plan().in_flight_source == "list_active"` — the adapter's live
      capacity read genuinely succeeded for this worker. A `plan()` that
      fell back to `"ledger"` answers a real question for a caller who
      already committed to one named worker, but it answers a WEAKER one
      than automatic selection is allowed to accept: `plan()` cannot tell
      "unreachable right now" apart from "revoked" on its own, and
      counting an unconfirmed worker healthy here would let a merely
      slow or flaky service look exactly like a genuinely healthy one —
      the same confusion `WorkerUnauthorized` exists to prevent, on the
      other side of the same fact.

    A healthy worker with `granted < 1` (every slot already spent) is
    skipped too, but for a different, unremarkable reason: it has nothing
    to grant right now, not that it is unwell.

    No worker healthy and grantable is an honest terminal state, never a
    silent pass and never an arbitrary pick: the refusal names every
    worker this call actually tried and the reason each one was skipped,
    plus the remedy — restore at least one account's credential, or wait
    for the service to become reachable, before retrying with no
    `--worker` named at all.
    """
    if not isinstance(adapter, ADAPTER.Adapter):
        raise PackerError(
            f"{adapter!r} is not an Adapter instance; capacity is discovered "
            "through the adapter seam only, never accepted some other way"
        )

    workers = adapter.workers()
    if not workers:
        raise PackerError(
            "adapter reports no workers at all; automatic selection has "
            "nothing to choose among"
        )

    reasons: list[str] = []
    for worker in workers:
        candidate, reason = _triage(
            adapter=adapter,
            worker=worker,
            requested=requested,
            ledger_lines=ledger_lines,
            live_digest=live_digest,
        )
        if candidate is None:
            reasons.append(f"{worker.id}: {reason}")
            continue

        return candidate

    raise PackerError(
        "automatic selection found no healthy worker with capacity among "
        f"{[worker.id for worker in workers]}; restore at least one "
        "account's credential, or wait for the service to become "
        f"reachable, before retrying with no --worker named: {'; '.join(reasons)}"
    )


def _round_robin_sequence(plans: list[Plan]) -> list[str]:
    """Ragged round-robin over already-granted `Plan`s, in the order they
    were handed in (which is `adapter.workers()`'s own declared order,
    filtered to `granted >= 1` — `distribute()` invents no ordering of its
    own). For `r = 0, 1, 2, ...`, every worker with `granted(w) > r` gets
    one more slot in this round; the round-robin stops the instant a round
    adds nothing, which is exactly what makes ragged rows (`w1(2), w2(1),
    w3(2)`) terminate at the right length (5, not 6) instead of looping
    forever. Deterministic because `plans` is never re-sorted and neither a
    `dict` nor a `set` participates in the walk.
    """
    order_ids = [candidate.worker for candidate in plans]
    granted_by_id = {candidate.worker: candidate.granted for candidate in plans}
    sequence: list[str] = []
    round_index = 0
    while True:
        round_ids = [worker_id for worker_id in order_ids if granted_by_id[worker_id] > round_index]
        if not round_ids:
            break
        sequence.extend(round_ids)
        round_index += 1
    return sequence


def slot_shares(assignment: Assignment) -> tuple[tuple[str, ...], ...]:
    """Split one worker's assigned units into one share per concurrent slot
    it was granted: `k = min(granted, len(units))` shares, share `j` holding
    `units[j::k]` -- round-robin by slot, in the order `distribute()` handed
    them out. Each share becomes its OWN submission (S1, parallel
    campaigns): a worker granted two slots runs two jobs side by side
    instead of one job running every unit in sequence.

    A worker granted one slot gets exactly one share holding every unit it
    was given -- today's one-job-per-worker shape, unchanged. No units (the
    "had room, didn't need it" case) is no share at all: capacity with
    nothing to spend never becomes a fabricated job. Pure: reads nothing
    but the `Assignment` it is handed.
    """
    units = tuple(assignment.units)
    if not units:
        return ()
    slots = max(1, min(assignment.plan.granted, len(units)))
    return tuple(units[index::slots] for index in range(slots))


def distribute(
    *,
    adapter: "ADAPTER.Adapter",
    units: Sequence[str],
    ledger_lines: Iterable[str],
    live_digest: str | Callable[[], str],
    affinity: Mapping[str, str] | None = None,
) -> Distribution:
    """Aggregate capacity across EVERY worker `adapter.workers()` reports,
    and assign opaque `units` to it round-robin, ragged rows and all.

    Where `select()` answers "give me ONE worker with capacity" and stops
    at the first healthy account, `distribute()` answers a different
    question: "spread ALL of these units across every account that has
    room". It never invents an ordering of its own — worker order comes
    from `adapter.workers()`, unit order from the caller — and it inspects
    nothing about a unit beyond "an opaque `str`"; what a unit MEANS is the
    caller's knowledge, never this module's.

    No `requested` parameter: every worker is asked `requested=len(units)`
    and `plan()` (via `_triage()`) does the clamping, exactly once per
    worker. Pre-slicing `len(units) // len(workers)` before asking is
    REJECTED — three units over five workers would floor to a zero-sized
    ask at every worker and distribute nothing at all, the same collapse
    `requested=0` would cause here too; asking each worker for the FULL
    `len(units)` and letting the clamp do its job is what lets a small
    campaign still spread across several accounts with one open place each.

    `adapter.workers()` reporting no workers at all reuses `select()`'s own
    first refusal, unchanged — an adapter with nothing to distribute across
    is not this function's fact to soften into an empty result. Duplicate
    unit identifiers refuse by name AND position instead: `unplaced` and
    `assignments` both report by identity, and a repeated identity would
    make "which one is unplaced" unanswerable, besides quietly submitting
    the same unit twice under two different accounts.

    Health is read exactly once, only through `_triage()` — the same two
    fields `plan()` already reports, never a second, separate health probe
    and never a worker's own declared cap read directly here. A worker
    `_triage()` could not confirm live contributes zero places and is
    named in `skipped` by
    identity; a revoked worker is skipped the same way, its
    `WorkerUnauthorized` never propagating out of this function. Nothing
    computed here is persisted: no ledger line is appended, and no
    already-computed assignment is ever revisited by a later call to this
    same function — a unit left `unplaced` becomes assignable again only on
    a SUBSEQUENT `distribute()` call, once the ledger reflects whatever
    changed.

    `affinity` (kernel-carry S4) maps a unit to the one worker it must run
    on -- a continuation whose earlier output can only be carried within
    the account that produced it. A pinned unit whose worker is among the
    granted ones takes one of that worker's places first; when that worker
    has no place left the unit stays `unplaced` (it waits for a later
    campaign rather than starting on an account that cannot carry its
    output). A pinned unit whose worker is not in the pool at all is placed
    like any other, and `submit` decides about it. Every other unit fills
    the remaining places in the same round-robin order as before. `None`
    or an empty mapping is byte-identical to the placement without it.
    """
    if not isinstance(adapter, ADAPTER.Adapter):
        raise PackerError(
            f"{adapter!r} is not an Adapter instance; capacity is discovered "
            "through the adapter seam only, never accepted some other way"
        )

    workers = adapter.workers()
    if not workers:
        raise PackerError(
            "adapter reports no workers at all; automatic selection has "
            "nothing to choose among"
        )

    units = tuple(units)

    positions_by_unit: dict[str, list[int]] = {}
    for index, unit in enumerate(units):
        positions_by_unit.setdefault(unit, []).append(index)
    duplicates = {
        unit: positions for unit, positions in positions_by_unit.items() if len(positions) > 1
    }
    if duplicates:
        detail = "; ".join(
            f"{unit!r} at positions {positions}" for unit, positions in duplicates.items()
        )
        raise PackerError(
            "duplicate unit identifiers refuse to distribute — placing both "
            f"would double-submit the same work under two accounts: {detail}"
        )

    requested = len(units)
    granted_plans: list[Plan] = []
    skipped: list[Skip] = []
    # A campaign is placed only on workers the adapter says may take part
    # in one. `campaign_refusal` is an optional adapter hook (a worker on a
    # tier whose terms forbid distributed workers, say): an ineligible
    # worker is skipped by name, before any live probe, so the units go to
    # the eligible ones instead of the whole campaign being refused later.
    campaign_refusal = getattr(adapter, "campaign_refusal", None)
    for worker in workers:
        if callable(campaign_refusal):
            refusal = campaign_refusal(worker.id)
            if refusal:
                skipped.append(Skip(worker=worker.id, reason=f"not a campaign worker: {refusal}"))
                continue
        candidate, reason = _triage(
            adapter=adapter,
            worker=worker,
            requested=requested,
            ledger_lines=ledger_lines,
            live_digest=live_digest,
        )
        if candidate is None:
            skipped.append(Skip(worker=worker.id, reason=reason))
            continue
        granted_plans.append(candidate)

    places = sum(candidate.granted for candidate in granted_plans)
    sequence = _round_robin_sequence(granted_plans)
    assigned_count = min(len(units), len(sequence))

    units_by_worker: dict[str, list[str]] = {candidate.worker: [] for candidate in granted_plans}
    if not affinity:
        for index in range(assigned_count):
            units_by_worker[sequence[index]].append(units[index])
        unplaced = units[assigned_count:]
    else:
        open_places = list(sequence)
        placed: dict[str, str] = {}
        waiting: set[str] = set()
        for unit in units:
            pinned = affinity.get(unit)
            if pinned is None or pinned not in units_by_worker:
                continue
            if pinned in open_places:
                open_places.remove(pinned)
                placed[unit] = pinned
            else:
                waiting.add(unit)
        free = iter(open_places)
        for unit in units:
            if unit in placed or unit in waiting:
                continue
            worker_id = next(free, None)
            if worker_id is None:
                break
            placed[unit] = worker_id
        for unit in units:
            if unit in placed:
                units_by_worker[placed[unit]].append(unit)
        unplaced = tuple(unit for unit in units if unit not in placed)

    assignments = tuple(
        Assignment(plan=candidate, units=tuple(units_by_worker[candidate.worker]))
        for candidate in granted_plans
    )

    return Distribution(
        units=units,
        places=places,
        assignments=assignments,
        unplaced=unplaced,
        skipped=tuple(skipped),
    )
