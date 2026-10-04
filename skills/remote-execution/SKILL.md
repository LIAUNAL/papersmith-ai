---
name: remote-execution
description: "Trigger: durable record of what a repository has submitted to a remote worker, what came back, and how much to submit at once: the append-only ledger and the fold that derives per-entrypoint state, the capacity clamp and worker auto-selection, the `remote_cli` front door (`submit` with its path guard, `status`, `poll`, `fetch`, `reconcile`, `distribute`, `generate-job`, `smoke`, `record`, `readiness`), the backend-agnostic adapter seam (ABC, frozen shapes, registry), and one shipped backend -- `adapters/kaggle.py`, the only file here allowed to name a service, shelling out to `adapters/kaggle_driver.py`, the only one allowed to import the pinned `kagglesdk` client. Credentials travel as a `CredentialHandle(worker_id, token_path)`, read at one expression in that one file; readiness is derived from `smoke.jsonl` evidence, never a human assertion and never a clock. Stdlib-only except that one named driver script."
---

# Remote Execution

A submission to a remote worker is a fact once it happens, and this skill's
job is to make sure that fact survives being written, to derive current
state from the record rather than store it separately, and to decide how
much work a worker is asked to take on at once without either side of that
decision asserting the other's fact. One concrete adapter ships today —
`adapters/kaggle.py`, the only file here allowed to name a service, shelling
out to `adapters/kaggle_driver.py`, the only one allowed to import the
client — alongside the CLI a user would invoke directly (`submit`, `status`,
`poll`, `fetch`, `reconcile`). This skill's own suite reaches neither: it
exercises both the adapter and a `FakeAdapter` against fakes, never the
network, so a defect that only a live account can produce is invisible to a
green run here and has to be found by using it. One was, on 2026-09-24 —
see the capacity op's bullet under "What this skill cannot see".

## The objective flow

**Why this skill was invoked, and where it has to arrive.** Declared here and in
`OBJECTIVE_FLOW`, held equal by a test, and independent of any ledger, job folder
or result on disk. `status` answers *where am I* by folding what happened; this
answers *what is this for*, which nothing on disk implies.

It exists for the moment something breaks. A session that hits an error, an
interruption or a gap consults it, locates itself, resolves what blocks, and
rejoins. Every refusal this CLI raises carries it — which required creating the
single place they all reach a reader, because there were fourteen and nothing
could hold them to agreeing.

**Purpose:** carry work a repository declared to a worker and bring its result
back verified — not accepted, not running, back and current.

| Stage | Establishes | Behind you when |
| --- | --- | --- |
| `reachable` | A job folder pinned to a commit the declared remote can actually serve, which is what a worker clones | `generate-job` wrote the folder — it proves the pin against the remote before writing a byte, so a folder that exists is a pin that was published |
| `wire` | That this worker, at this pin, carries current — paid in minutes rather than in the hours a campaign costs | `readiness` says ready, from a verdict derived from a rehearsal's own evidence and never asserted |
| `authorized` | A launch bound to this exact commit, entrypoint and unit list, with a token minted for it and consumed once | a `gate` record matches; a bound fact that moved makes it stale, which is not the same as time passing |
| `sent` | The submission is out and the ledger knows it, so no second one answers a question already being answered | the ledger holds it with a terminal state |
| `returned` | The result is on disk, current, and not quarantined | this is the arrival; it is behind nobody |

**Arrival:** the result on disk and verified as the current one, which is the only thing anybody can read a number out of.

**`reconcile` is not a stage and never advances one.** It is the way back when
the ledger and the service stop agreeing — `drift`, or a ledger line that could
not be read at all — and it returns to `sent`. Said explicitly because without
it `drift` reads as having lost the work rather than as a detour.

**Two stops are a person's, not defects to repair:** publishing the commit a
worker would clone, which `generate-job` refuses without and names precisely,
and authorizing the launch itself.

**Arrival is the result back and verified, never the submission accepted.** That
distinction is the whole point: a submission the service took is a receipt, and
a receipt is not a measurement. Between the two sit a poll, a fetch, and a
quarantine that refuses a result which is not current.


## What this skill cannot see

**It does not know how much time budget a worker has left, and it has no way
to find out.** The adapter seam exposes `capacity` -- how many submissions may
run at once -- and `list_active`. Neither is a time budget. `distribute` plans
in concurrency slots, so its answer is "how many can run simultaneously",
never "how many hours remain this week".

**The capacity op's per-ref handling is written, and it lives in
`kaggle_driver.py`, not `adapters/kaggle.py`.** `reconcile` makes exactly one
remote call, `adapter.list_active(worker)`, which reaches a zero-argument
capacity op (`kaggle_driver.py::cmd_capacity`) that enumerates this worker's
kernels with one `list_kernels` call and then issues one status request per
ref. `adapters/kaggle.py` never talks to the service directly; it only
consumes that op's JSON result, so the loop this bullet is about was always
INSIDE the driver, never inside the adapter.

MEASURED, not assumed, against the live service on 2026-09-24, across all 9
accounts configured on this repository at the time: `list_kernels` itself
succeeded on every single one of the 9. Two distinct per-ref failure shapes
explained 7 of the 9 looking unreachable before this was fixed:

- HTTP 404 from `get_kernel_session_status` — 17 refs across 6 accounts
  (per-account spreads ranging from 1-of-13 to 9-of-20; the accounts
  themselves are deliberately not named here — this file ships in the kit
  to other people's workspaces, and `AccountVocabularyLeakTests` refuses
  any skill source that names a stored account of the machine it is read
  on. The counts are the evidence; the identities are not). A 404 on that
  endpoint
  means no session exists for that kernel — a reading that rests on the
  ordinary meaning of a 404 on a session-status resource, NOT on ever
  having observed a genuinely `queued` or `running` kernel answer
  differently: no account had one in flight at probe time, every resolved
  status was `COMPLETE`, `ERROR` or `CANCEL_ACKNOWLEDGED`. Say that
  plainly; do not overstate it into a claim this measurement never made.
- `ValueError` from `ref.split("/", 1)` — one of the nine accounts enumerated
  an entry with `ref == ''` and `title == '[Private Notebook]'`;
  `''.split("/", 1)` yields `['']`, which cannot fill the two-target
  unpack, and raised before any request was attempted. The 2 healthy
  accounts simply had zero unresolved refs.

A hypothesis TESTED AND REFUTED against that same measurement: the
per-kernel `current_version_number` field does NOT discriminate a
resolvable ref from an unresolvable one — every enumerated kernel reported
`0`, resolved and unresolved alike. Do not gate anything on it and do not
retry citing it as evidence either way.

Before the fix, NEITHER shape was caught: `cmd_capacity` had no per-ref
exception handling at all, so either one propagated straight out of it and
turned a successful enumeration into a driver-level refusal, which
`adapters/kaggle.py`'s `_parse_capacity_result` then stamped `"(list_kernels
failed structurally)"` — the enumeration had succeeded, one downstream
per-ref call had not, and the operator was told the service was
unreachable. `cmd_capacity` now guards a ref before using it (one with no
`/` is recorded unresolved without an attempt) and wraps the status call
itself so any exception it raises makes that one ref unresolved without
interrupting the refs around it, returning `{"kernels": [...], "unresolved":
[{"ref", "reason", "detail"}, ...]}` and exiting 0 whenever `list_kernels`
itself succeeded. `reason` is one of three facts: `session_absent` (404 —
definitive, no session exists), `unaddressable_ref` (never asked), or
`status_lookup_failed` (timeout/429/5xx — genuinely unknown).
`adapters/kaggle.py::list_active()` counts a ref confirmed
`queued`/`running` OR left `status_lookup_failed` as active (undercounting
an unknown ref would oversubscribe a worker). `session_absent` and
`unaddressable_ref` are real evidence of NOT in flight, so an all-404
account is ordinary and idle and returns `[]`; the fail-closed raise fires
only when nothing resolved and no definitive evidence exists either.

**Any plan that reasons in weekly hours takes that number from the operator.**
Ask; do not assume, and never read one out of this repository.

This is stated first because getting it wrong is not hypothetical. A comment
in `adapters/kaggle.py` once recorded one rehearsal's cost as `75s of a
21600s/week (6h) per-account quota`. No constant held that figure, no code
read it, no test covered it -- an aside wearing the shape of a documented
service property. Two sessions built arithmetic on it and produced a two-week
schedule for work that fits in an afternoon; the operator's real figure was
four to five times larger.

**The tell was available the whole time.** Before believing a number that
governs spending, look for the constant that holds it, the code that reads it,
and the test that covers it. A number nothing enforces is a sentence, not a
limit.

## Current Scope

Three modules exist so far, each service-blind and stdlib-only:

- `scripts/ledger.py` — `append(path, event)` appends one JSON-encoded event
  as a single line to `<target>/<Name>/.remote-execution/ledger.jsonl`. The
  file is opened `O_APPEND`; a line, once written, is never rewritten or
  deleted (see below for why an append can be trusted at all).
  `fold(lines, live_digest)` derives current per-entrypoint state from that
  log — `pending | returned | errored`, whether a pending submission is
  `staleInFlight`, and which `returned` results are `fromStaleSubmission` —
  the currency rule that tells a fresh result from a stale one.
  `submitted_event(...)`, `returned_event(...)`, `errored_event(...)` build
  the three event kinds this ledger records, with the field names and
  truncation rules this schema fixes (see below).
- `scripts/adapter.py` — the `Adapter` ABC every backend-specific module
  must satisfy in full (exactly six operations), the frozen data shapes
  that cross the seam (`Worker`, `Job`, `Submission`, `Status`, `Fetched`),
  and a name-to-class registry a caller can select a backend by without
  importing it directly. `Job.run_config` is an opaque
  `Mapping[str, object]` — normalized in `__post_init__` to a
  `MappingProxyType` over a private copy, so mutating it (or mutating the
  caller's own original dict afterward) is structurally refused. The
  packer and the ledger never read or branch on a key inside it; an empty
  `run_config` is the legacy shape every existing caller uses, a non-empty
  one is what a generated job carries. A second, separate registry,
  `register_metadata`/`resolve_metadata`, maps a name to a
  `fn(run_config) -> (filename, text)` callable — kept off the ABC
  entirely so a backend needing a service-specific metadata file (an
  accelerator request, say) never forces every other backend to grow a
  method it does not need. `adapters/kaggle.py` is the one concrete
  backend this skill ships; its own test suite also stands a `FakeAdapter`
  in for a second one, to prove the seam generalizes.
- `scripts/packer.py` — `plan(...)` clamps a repository's declared
  per-worker request to the cap the adapter states through `workers()`,
  deducting what is already committed (from the ledger's fold, refined by
  `list_active()` when the adapter answers). The clamp is never a silent
  minimum: `plan()` returns `requested`, `cap`, `inFlight` and `granted` as
  four separate numbers, plus `inFlightSource` recording whether `inFlight`
  came from the live service or fell back to the ledger. `plan()` never
  swallows `ADAPTER.WorkerUnauthorized` — every OTHER `list_active()`
  failure still degrades to the ledger count, but a refused credential is
  a decision-bearing fact, not a mere unreachable one, and propagates.
  `select(...)` picks a worker for a caller who names none: it walks
  `adapter.workers()` in declared order and returns the first one whose
  `plan()` both answered from the live service (`inFlightSource ==
  "list_active"`, never a ledger fallback — a worker this call could not
  actually confirm is never counted healthy) and still has capacity
  granted; naming no healthy worker at all is a refusal listing every
  account tried and the remedy, never a silent pass or an arbitrary pick.
  `distribute(...)` reads the same clamp across EVERY worker at once,
  never a fourth kind of number invented for it: it calls `plan()` for
  each one (through the same private triage step `select()` uses, so the
  two never drift onto two different health rules), sums whatever every
  healthy account actually grants into one `places` total, and spreads a
  caller's own work units across that total round-robin, ragged rows and
  all — a unit left over when the total runs out is named in `unplaced`
  by identity, never silently dropped or folded into a boolean. A `unit`
  is an opaque `str` end to end: `distribute()` inspects nothing about
  its contents, sorts nothing, splits nothing, and the CLI surface below
  never imposes a separator on one either — `--unit` is repeatable
  precisely so a unit containing its own comma, slash, or space still
  survives untouched from the command line through to `assignments`.
- `scripts/remote_cli.py` — the CLI front door: the submission and status
  commands (`submit`, `status`, `poll`, `fetch`, `reconcile`), the
  read-only `distribute`, and `generate-job`, `smoke record` and
  `readiness` (see "Smoke" below).
  - `submit`'s `--worker` is OPTIONAL: naming one keeps today's behavior
    exactly (an unhealthy named account refuses, never silently reroutes
    — switching accounts on a caller's behalf would spend a different
    account's quota than the one asked for); omitting it hands the choice
    to `packer.select()` above. `reconcile`, `smoke record` and
    `readiness` keep `--worker` REQUIRED — each already names one
    account's own local state (its ledger, its evidence, its capacity),
    never a fresh submission decision, so there is no fork for automatic
    selection to remove there.
  - `submit` guards the entrypoint, resolves the product via
    `product_for()` (the SAME function `status`, `fetch` and `reconcile`
    call — never an inline `parts[0]` derivation of its own), computes a
    fresh `source_digest()`, calls `packer.plan()` (a named worker) or
    `packer.select()` (none named), hands the job to a registered
    adapter's `submit()`, and appends the resulting `submitted`
    event to the ledger — in that order. A job-folder submission whose
    product cannot be resolved (no `--product`, no `product` declared in
    its own `run-config.json`) is refused right there, before the digest,
    the plan or the adapter ever run — never silently recorded under
    `tools`. `--product` is `submit`'s own CLI flag reaching `product_for`'s
    `explicit` argument, its highest-priority resolution step; `status`,
    `fetch` and `reconcile` do not yet expose an equivalent flag, since each
    reads an already-generated job folder whose own `run-config.json`
    already declares its product. The `entrypoint` field a `submitted`
    event records is the resolved entrypoint's path relative to the
    resolved product directory for the legacy shape (`Notebooks/a.ipynb`);
    for the job-folder shape, whose product directory is never an ancestor
    of the entrypoint at all, it falls back to the path relative to
    `target` instead (`tools/<service>/<job-name>/runner.ipynb`) — both
    stay unique per submission, and neither pretends a containment
    relationship the job-folder shape does not have. `guard_entrypoint()` is
    the ONLY place in this whole
    skill that holds an opinion about what KIND of file may run remotely:
    `Path.resolve()` first, then refuse anything whose resolved path does
    not match one of exactly two admitted shapes and end `.ipynb`:
    `<target>/<Name>/Notebooks/**.ipynb` (the legacy shape) or
    `<target>/tools/<service>/<job-name>/*.ipynb` (the job-folder shape,
    exactly four path components past `target` — not "at least four").
    `TOOLS_DIRNAME` ("tools") is a forge-layout constant, never a service
    name, and it is excluded from this module's own no-service source
    scan for exactly that reason. Everything below the guard
    (`Job.entrypoint`, the ledger's `entrypoint` field, the fold's indices)
    stays deliberately blind to that question; widening this one guard,
    not reworking any of those, is how a future non-notebook workload
    becomes admissible. One narrower case gets its own message before
    either shape's generic refusal (Finding 4 case B): a path that IS the
    job-folder DIRECTORY itself (exactly three components past `target`,
    first `TOOLS_DIRNAME`, actually holding both `run-config.json` and
    `runner.ipynb`) is one level above the answer, not a path in the
    wrong location — the generic "does not stay under ... nor under ..."
    message read like a location problem and sent the caller to
    regenerate a job that was already sound. The dedicated message says a
    file was expected, not a directory, and names exactly where the
    notebook is. `--smoke` sets `run_config["mode"] = "smoke"` on
    the `Job` handed to the adapter, and routes the resulting `submitted`
    event to `smoke.jsonl` instead of `ledger.jsonl` (see "Smoke" below) —
    both together, never one without the other.
  - `submit --unit` (repeatable, the exact same flag `distribute` declares)
    switches into CAMPAIGN mode (Finding 2; Decisions 6, 7): `--worker` is
    refused together with it (campaign mode spreads itself; there is no
    single named account for `--worker` to select), and
    `packer.distribute()` replaces `packer.select()`/`packer.plan()`
    entirely — the guarantee is EVERY healthy account, never the first
    one. `cmd_distribute`'s own read-only report used to be the only
    consumer of that spread; `submit --unit` is the write path that
    actually issues it. One `adapter.submit()` and one ledger event per
    `packer.Distribution` assignment — never one per unit, since a
    worker's whole assigned unit list travels inside that ONE job's opaque
    `run_config["units"]`. An assignment a healthy account was granted but
    had no units left to receive (`packer.Assignment`'s own documented
    "had room, didn't need it" case) submits nothing and reports
    `submissionId: null` — capacity with nothing to spend is never turned
    into a fabricated job. The result mirrors `packer.Distribution` field
    for field: `assignments[]` (worker, its whole `Plan`, its units, its
    submission id), `unplaced[]` (units that did not fit, by identity),
    and `skipped[]` (`worker -> Skip.reason`, unprefixed) — an excluded
    account is always named with its reason, never silently dropped.
    Single-unit `submit` (no `--unit` at all) is untouched: today's
    `select()`/`plan()` path, byte-identical.
  - **Consent gate, every launch** (Finding 3; Decisions 4, 5 — corrected
    in a later pass): `submit` refuses without an explicit `--consent
    <token>` — the "nothing is launched without explicit permission"
    rule, held until now only in agent instructions where a fresh session
    invoking `submit` would meet nothing that asks.

    **This gate is unconditional, not a campaign-only case.** The first
    pass gated campaign mode (`--unit`) alone, which left a plain `submit
    --target X --entrypoint Y --backend Z` — and equally `submit --smoke`
    — reaching the adapter with nobody asked: a single rehearsal, not a
    campaign, is the exact launch the complaint that produced this gate
    named. The fix is not a second case bolted onto the first; it is the
    same check, called unconditionally: nothing reaches
    `packer.select()`/`packer.plan()`/`packer.distribute()`, and
    therefore never `adapter.submit()`, without a token that matches what
    is being sent. Campaign mode is scoped **per campaign, not per
    shard**: one approval, carried by one invocation, covers every unit
    that invocation submits — thirty shards, one prompt. A single send is
    scoped **per launch**: one approval per `submit` invocation. A CLI
    cannot prompt on its own, so the gate refuses by default and is
    released by a token, deliberately never a `--yes` boolean: a boolean
    satisfies "not persisted" on paper and reproduces this exact defect
    the moment it lands in a wrapper script.

    The token is **derived**, not issued: `sha256(pin commit, relative
    entrypoint, ordered unit list)`, computed by
    `campaign_consent_token()` — ONE function, ONE shape, for both modes.
    An empty ordered unit list is a legitimate input for a single send,
    never a reason to invent a second derivation. For a campaign,
    `distribute` mints and prints it (in `consentToken`) ahead of time —
    already read-only, already computing the spread, already handing it
    to nobody, so printing the token adds no new write. **A single send
    has no equivalent minting command** — there is no `distribute` for
    one entrypoint — so `submit` itself mints the expected token and
    prints it **inside its own refusal** on the first, consent-less call.
    That is safe only because the refusing call never gets past the
    gate: no plan, no adapter call, no ledger line — nothing was
    launched by the run that named the token, so the printed token can
    never BE the approval it names, only something a second, deliberate
    invocation that passes it back into `--consent` can be. The worker is
    never part of what either token binds: with no `--worker`, the
    account is chosen by `packer.select()` AFTER consent would be given,
    so binding it would make the token unmintable in advance; with
    `--worker` named, the account is the caller's own explicit,
    already-honest choice.

    It expires **by construction**, not by policy: a pin that moves, an
    entrypoint that changes, or a unit added, removed or reordered all
    change the payload and therefore the digest, so a stale or
    cross-launch token simply stops matching — there is no separate
    staleness check to remember to run. Live worker health is
    deliberately NOT bound into the token: a flapping account would
    otherwise revoke an approval that was legitimately given.

    Three things make non-persistence structural, not merely asserted:
    consent is read **only from parsed argv** (never a config key, an
    environment variable, or a ledger line); a whole-tree hash snapshot
    across two invocations proves nothing under `target` records it; and
    a token minted for a different pin, entrypoint, or unit set refuses —
    including a single-send token minted for one entrypoint, which does
    not authorize submitting a different one.

    **The honest limit, stated rather than implied: no gate can prove a
    human was present at the keyboard.** It proves only that the launch
    was deliberate (a token had to be minted first, by a caller who
    already knew the exact pin and entrypoint), bound (to exactly that
    launch), and unstored (nothing here ever carries it forward to a
    later invocation).
  - **Launch authorization, a SECOND and INDEPENDENT precondition**
    (design §4, `the-position-nobody-holds`): the consent gate above
    refuses correctly, but its own single-send refusal safely PRINTS the
    token it needs — safe only because `campaign_consent_token()` is a
    sha256 over this invocation's OWN public argv, so any caller who can
    run `submit` can already compute it. That is not a flaw in the token;
    it is what a public digest can never be — an authorization. Editing
    that payload to add readiness or a justification would not close the
    gap, it would only give the printed refusal one more field to echo
    back, and it repeats the exact defect class already recorded above
    (F2: a real field left out of the digest once let three different
    accounts mint an identical token).

    `_verify_launch_authorization()` reads a DIFFERENT record instead: a
    `gate` transition, written by `implementation_cli gate` — a separate
    command, run beforehand, by a separate invocation — into
    `<target>/<product>/.implementation/position.jsonl`
    (`proposal-implementation`'s own append-only ledger, folded through
    `_core/implementation/impl_position.py`, never re-derived here). A
    non-rehearsal `submit` now refuses unless the newest `gate` event
    matches this invocation's own pin, relative entrypoint, ordered unit
    list and named worker (or its absence), and carries a non-blank
    justification.

    **Readiness is the un-forgeable half.** `gate` only ever appends its
    record after `readiness` (above) reads `True` for that job at its
    CURRENT pin — a fact only a real rehearsal, actually run and recorded,
    can produce; no caller can type it into existence. **Justification is
    legible, not verified** — `gate` requires one be present, but nothing
    here checks who wrote it or whether a human read it. What this DOES
    make true, honestly: the approval is a distinct recorded act, and
    re-running the identical refused `submit` invocation, any number of
    times, never substitutes for it.

    Scoped deliberately, not universally: a rehearsal (`--smoke`) is
    exempt — gating it would deadlock the very mechanism that makes
    readiness measurable. The legacy `<Name>/Notebooks/**.ipynb` shape is
    exempt — it has no job folder, so nothing ever promised a runner a
    commit and no `@rehearsal` witness could ever name one. Both exemptions
    are structural: readiness cannot exist before a rehearsal has run, and
    a shape with no job folder has nothing for `gate` to bind to.

    **Campaign mode (`--unit`) is NOT exempt** — a design revision on top
    of what shipped first (`the-position-nobody-holds` PR8). The original
    reasoning here claimed `gate`'s own CLI took no `--unit` flag, so a
    campaign launch could never be matched by any `gate` record; requiring
    one would make it permanently unauthorizable rather than an adoption
    cost. That premise was wrong, and the consequence inverted this whole
    mechanism's purpose: the single send ended up gated and the campaign —
    the full-scale, multi-worker, hours-long launch this change exists to
    gate in the first place — did not. `gate` now takes the identical
    repeatable `--unit` `distribute`/`submit` already declare, and binds
    the SAME three facts `campaign_consent_token()` binds for consent: pin,
    relative entrypoint, and the exact ordered unit list, computed from the
    caller's own argv before `packer.distribute()` ever runs — never the
    per-worker assignment `distribute()` computes later, which
    `_verify_launch_authorization()` never sees at all. A campaign
    authorization's `worker` field is always `None`, matching what a
    campaign `submit` invocation's own binding always is (`cmd_submit`'s
    own `--worker`/`--unit` mutual exclusivity, mirrored by `cmd_gate`'s
    own refusal on the same conflict).

    Fail-closed for everything else, on purpose: a job-folder product with
    no `.implementation/position.jsonl` at all refuses exactly like one
    with events but no match — the one-time adoption cost this accepts
    rather than reproduce today's hole for every target that never adopts
    the position mechanism. The refusal names the exact `gate` invocation
    that pays it.
  - `status` folds the ledger and reports per-entrypoint state, what is
    `staleInFlight`, what is quarantined, and `unreadableLines`. It accepts
    no `adapter` parameter at all — a structural fact, not a convention —
    so it reports and never resolves anything.
  - `poll` asks the adapter for one submission's status and refuses a
    `Status.state` outside the seam's own five-value vocabulary itself,
    rather than trusting every adapter to have gone through
    `ADAPTER.Status.__post_init__`'s own validation.
  - `fetch` materializes into `<dest>.partial/` and renames into place only
    on `Fetched.complete == True`; only a completed rename appends a
    `returned` event, so a crash mid-fetch leaves the submission `pending`
    — retryable, never a false `returned`. `LEDGER.currency_verdict()` (the
    same rule `fold()` itself uses) is evaluated before the rename: a
    `fromStaleSubmission` result overrides the caller's requested `dest`
    entirely and is fetched into
    `<target>/<Name>/.remote-execution/quarantine/<submissionId>/` instead
    — structurally outside `Results/shards/`, so it is parked and
    auditable, never merged. `fetch --smoke` computes its own destination
    the same way, into `<target>/<Name>/.remote-execution/rehearsal/
    <submissionId>/` — `--dest` is refused (not merely unused) under
    `--smoke`, and a real fetch with no `--dest` is refused symmetrically;
    both directions closed by one pure-argv pairing check, above every
    filesystem call. Every `returned` event also carries
    `observedConcurrency`: `LedgerState.pending_for(worker)` read from the
    ledger state at the top of the call, so a service throttling below the
    packer's own grant becomes a visible, different number instead of an
    assumed one.
  - `reconcile` compares `adapter.list_active(worker)` against the ledger's
    own pending set for that worker, in both directions, and only ever
    reports the difference. An id the service has that the ledger lacks is
    `orphanRemote` — reported, never auto-cancelled and never auto-adopted,
    because adopting would fabricate a `submitted` line with no digest, and
    the digest is the entire basis a later result is judged current by. A
    `pending` ledger submission the service no longer lists is
    `orphanLocal` — reported, and `--resolve` (human-invoked only, default
    `False`) is the one path that appends `errored(reason="not-found-at-service")`
    for it.

    **Its one remote call degrades rather than crashing, and says which
    happened.** `adapter.list_active()` failing — unreachable, refusing,
    timing out — returns `remote: {"status": "unavailable", "reason": …}`
    with both orphan tuples empty and `--resolve` appending nothing at all,
    instead of killing the one command an operator runs precisely because
    something has already gone wrong. The empty tuples alone would have
    said the OPPOSITE of the truth — `orphanLocal: []` from a service that
    answered is the strongest all-clear this command can give — so the
    status field carries the difference and the payload's emptiness never
    does, exactly as `packer.plan()` reports `in_flight_source` rather than
    a bare number, and as `prior_work_state()` reports `recordStatus` so an
    unreadable record cannot pass for a clean one. A service that answered
    reports `remote: {"status": "read", "reason": null}`.
    `WorkerUnauthorized` is the one `list_active()` failure that still
    refuses, re-raised untouched: a revoked credential is a
    decision-bearing fact, and `plan()` re-raises it out of the identical
    call for the same reason. Everything outside that single call — an
    absent `--target`, an unresolved product, an unreadable ledger — still
    refuses exactly as before, because none of it ever reached the service.
  - `product_for(target, entrypoint, explicit=None, *, command=None)` resolves
    which product's ledger an entrypoint belongs to — explicit, never guessed.
    Replaces the narrower `name_for()`: an explicit `--product` wins over
    everything; else, for the job-folder shape, the `product` field
    declared in that job's own `run-config.json` (read beside the
    entrypoint, if present); else, for the legacy shape, `<Name>` — the
    first path component past `target`, exactly as `name_for()` always
    derived it; else the call is refused, never silently mapped to a
    guess. Whatever step resolves a product, it must name an existing
    directory directly under `target` and must not be `TOOLS_DIRNAME`
    itself. `status`, `fetch`'s quarantine path and `reconcile`'s ledger
    selection all call this SAME function, so none of them can grow a
    second copy that quietly disagrees with another.

    **Refusal messages are parser-derived, never hand-written prose.**
    `command` names the calling subcommand (`submit`, `status`,
    `distribute`, `fetch`, `reconcile`), and the unresolved-product refusal
    names `--product` as a remedy only when `command`'s OWN
    `_build_parser()` subparser actually declares that flag — checked at
    the call, never assumed. Only `submit` (and `generate-job`, which
    never calls this function) declares `--product`; `status`,
    `distribute`, `fetch` and `reconcile` do not, so their refusal never
    cites it. A remedy the caller cannot perform is worse than a refusal
    that names nothing: it costs them the attempt.
- `scripts/adapters/kaggle.py` — the ONE file below the adapter seam allowed
  to name a service. `workers()` reports usernames from kaggle-accounts' own
  sanctioned `list --json` command (run as a subprocess; this module never
  opens kaggle-accounts' own credential file itself, directly or otherwise),
  each stamped with this service's own documented per-worker allowance
  (`KAGGLE_WORKER_CAPACITY`, a module constant, explicitly not a universal
  one). `submit`/`poll`/`fetch`/`cancel`/`list_active` shell out to
  `adapters/kaggle_driver.py` — the ONLY file in this skill permitted to
  import `kagglesdk`, invoked as a child process the same way this adapter
  used to invoke the `kaggle` CLI directly: `shell=False`, list argv, an
  env built from an allowlist (`PATH` plus, when a credential is involved,
  `KAGGLE_API_TOKEN`), and an explicit timeout on every call; a non-zero
  exit or an expired timeout is a refusal (`KaggleAdapterError`), never a
  fabricated `Status`, `Submission` or `Fetched`.

  **`fetch()` owns its own time budget, `KAGGLE_FETCH_TIMEOUT_SECONDS`
  (1800s) — a SEPARATE constant from `SUBPROCESS_TIMEOUT_SECONDS` (120s),
  never the same one reused.** This is the same finding as
  `jobfolder.py`'s `PIN_PUBLISHED_TIMEOUT_SECONDS` above, in a second
  place. The 120s constant times the control plane — worker listing, the
  submit push, `poll`, `capacity` — where every call is a small request the
  service answers immediately and failing fast is exactly right. `fetch()`
  is the one call that moves bulk bytes, and its SIZE IS DECIDED BY THE
  REMOTE JOB, not by anything this process can see beforehand; measured
  link throughput against this service varies by more than an order of
  magnitude (2.1 MB/s in one measurement, 0.06 MB/s in another). Under the
  shared budget that combination does not merely fail slowly, it
  MISDIAGNOSES: a 256 MB artifact from a completed 75-minute GPU run was
  killed at 120s and read as a broken fetch, exactly as the pin probe's
  slow run once read as an unpublished commit. 1800s is generous at the
  slow end of that range and still BOUNDED — a hung child must still die.
  The refusal names whichever budget actually expired, never the other, or
  the message sends the reader hunting for a limit that was not enforced.
  Both are constructor parameters (`timeout=`, `fetch_timeout=`) so a test
  can inject small values.

  `poll()` translates the
  driver's own reported `KernelWorkerStatus` member name into the seam's
  five-value vocabulary and never passes it through; the raw name goes in
  `Status.detail` only. `CredentialHandle(worker_id, token_path)` is
  the only credential type this adapter accepts, exposes no read method, and
  is consumed at exactly one expression in the whole skill: `_env_for()`
  reads the file that path names and puts its stripped CONTENT on
  `KAGGLE_API_TOKEN` for one child process — the driver's own.

  **The credential travels by value, and that is a trade, not a wording
  change.** The installed client's `_try_fill_auth()` reads
  `KAGGLE_API_TOKEN` and hands it straight to `BearerAuth(api_token)` — by
  value, with no path check of any kind — so a path in that variable becomes
  the literal text of an `Authorization: Bearer` header and authenticates
  nothing. The legacy `KAGGLE_CONFIG_DIR`/`kaggle.json` shape is not an
  escape from that either: it routes an access token (`KGAT...`, the shape
  this skill's credential store issues) through a Basic-auth path it was
  never meant for, and Kaggle answers 401 for every account regardless of
  validity. There is no by-path option left to prefer, so the by-path
  invariant this skill used to claim is spent. What replaces it is narrower,
  structural, and each row below is held to a test rather than to a reader's
  memory.

| # | id | Guarantee | Enforced by | Proven by |
|---|---|---|---|---|
| 1 | `by-value` | `KAGGLE_API_TOKEN` carries the token file's stripped content, never its path — the only shape the installed client authenticates | `_env_for()` | `test_the_env_value_is_the_files_stripped_content_and_never_its_path` |
| 2 | `stripped` | The newline `kaggle-accounts`' `materialize` writes never reaches the header; a newline inside a bearer header is a malformed header, not a credential | `_env_for()` | `test_the_newline_materialize_writes_never_reaches_the_header` |
| 3 | `single-reader` | No module above the adapter touches `token_path` at all, so a credential value has no route into any of them | `_env_for()`, and the absence of the attribute everywhere else | `test_no_module_above_the_adapter_can_reach_the_credential_file` |
| 4 | `fails-closed` | A credential file that cannot be read is a refusal naming the path, never a request sent without one | `_env_for()` | `test_a_credential_file_that_cannot_be_read_is_a_refusal` |
| 5 | `no-empty-bearer` | A credential file holding nothing once stripped is a refusal naming the worker — never an empty bearer header | `_env_for()` | `test_an_empty_credential_file_is_refused_rather_than_sent_as_a_bare_bearer` |
| 6 | `per-process` | Two concurrent submissions for two workers carry two distinct, uncrossed credentials: one fresh env dict per `subprocess.run`, never a shared or process-wide one | `_env_for()`, `_run()` | `test_two_concurrent_submissions_carry_two_distinct_uncrossed_credentials` |
| 7 | `really-concurrent` | The isolation above is proven under genuine overlap, not against two runs that merely happened in sequence | the falsifier's own fake `kaggle`, which records when it started and finished | `test_the_two_submissions_genuinely_overlapped_in_time` |
| 8 | `reached` | Every interception point this driver topology adds — the OUTER double (`kaggle_driver.py` faked on `PATH`) and the INNER double (a recording `requests` transport mounted on the driver's own client session) — asserts a non-zero recorded-call count before any assertion about content; a bypassed double fails rather than passing silently | `_run()`'s subprocess boundary (outer); the driver's own mounted transport in its test fixtures (inner) | `test_outer_interception_reached_count` |
| 9 | `no-sdk-above-the-driver` | `adapters/kaggle.py` names `kagglesdk` nowhere at all — text AND AST, so a live `import` and a docstring mention are both caught, not a reader's promise | `adapters/kaggle.py`'s own source (the absence of the name) | `test_driver_names_kagglesdk_nowhere_in_adapter` |
| 10 | `wire-bearer` | The prepared outbound request carries `Authorization: Bearer <the token's stripped value>`, observed below `BearerAuth.__call__` and above the socket — never a Basic header, anywhere on this path | `kaggle_driver.py`'s `_build_client()` plus the recording `requests` transport mounted on it in its own tests | `test_wire_bearer_header_carries_token_value` |

  Rows 8-10 are new to the child-driver topology; rows 1-7 hold verbatim
  under it — the sink is still `_env_for()`, only what reads the value on
  the other end changed (the `kaggle` CLI's `authenticate()` before this
  change, `kagglesdk`'s own `_try_fill_auth()` now). `fetch`'s per-file
  download URLs (`list_kernel_session_output`) are a known open question,
  not a row: whether they need this session's own Bearer credential or
  answer to an anonymous GET is settled only by a live rehearsal, not run
  by this change. `cmd_fetch` attaches the defensive choice (the same
  already-authenticated session `poll`/`submit` use) rather than guessing,
  and that choice stays **`unverified-by-rehearsal`** until a rehearsal,
  run only on the user's explicit permission, settles it either way.

  `REQUEST_GPU = True` and `KAGGLE_MACHINE_SHAPE = "NvidiaTeslaT4"` are
  declared here, and here alone in this whole skill — a request, not a
  receipt; what a submission actually ran on is a fact the service states
  at poll/fetch time in `Status.detail`, never assumed from either constant.
  **A named accelerator now reaches every push.** The retired
  `kaggle==1.7.4.5` client could not express one at all: its
  `kernels_push()` read only `enable_gpu`/`enable_tpu`, built its request
  field by field, and the string `machine_shape` occurred nowhere in that
  package, so a `machine_shape` key silently reached nobody and every push
  this skill made before this change ran wherever the service's own
  default draw landed. `kagglesdk` (the current dependency) maps
  `machine_shape` straight onto `ApiSaveKernelRequest`, and
  `kaggle_driver.py`'s own `_METADATA_PASSTHROUGH_KEYS` now carries it
  through. PROVEN LIVE, 2026-08-24: a kernel pushed with
  `machine_shape: "NvidiaTeslaT4"` reached a Tesla T4 and completed, where
  five earlier bare-`enable_gpu` submissions all failed on a drawn P100.
  Which GPU a session receives remains the service's own choice, reported
  like every other fact this skill refuses to guess at — a named request is
  not a guaranteed receipt. `assemble_metadata`
  writes that request, and every other worker-independent field a push
  needs, into a `kernel-metadata.json` template: `machine_shape` (the named
  request), `enable_gpu: true` (kept alongside it, not in place of it — the
  service documents it DEPRECATED in favor of `machine_shape` but a reader
  unfamiliar with the newer field still expects to see it),
  `enable_internet: true` (the generated runner clones over git inside the
  kernel, and Kaggle disables internet by default), `language`,
  `kernel_type`, `is_private`, and a `title` derived from the job's own
  name. `id` (`<owner>/<kernel-slug>`) and `code_file` are written BLANK —
  no worker is assigned at `generate-job` time, and the same job folder
  pushed to five different accounts needs five different `id` values, so a
  static file written once cannot hold it. `assemble_metadata` is
  registered under `ADAPTER.register_metadata("kaggle", ...)`, the second
  registry `adapter.py` exposes. `KaggleAdapter.submit()` refuses, before
  ever shelling out to `kernels push`, when `job.run_config` is non-empty
  (a generated job) and `kernel-metadata.json` is absent beside the
  entrypoint — an empty `run_config` is the legacy shape and is never
  checked, which is what keeps the credential-sentinel test's legacy-shaped
  `cmd_submit` call passing unchanged. When the metadata file IS present,
  `submit()` completes it — filling in `id` from `job.worker` and the
  entrypoint's own slug, and `code_file` from the entrypoint's own
  basename — inside a STAGED COPY of the job folder in a temp directory,
  and pushes that copy; the versioned `kernel-metadata.json` inside the
  job folder itself is only ever read, never rewritten, so a second push
  to a second worker starts from the same pristine template. This
  completion is driven by the metadata file's own presence, not by
  `run_config`: `cmd_submit` only ever sets `run_config["mode"] = "smoke"`
  for a smoke run, so an ordinary (non-smoke) job-folder submission
  reaches `submit()` with an EMPTY `run_config`, same as the legacy shape
  — the metadata file's presence is what distinguishes them. `cancel()`
  refuses explicitly: Kaggle's own CLI documents no single-kernel cancel
  operation, and this adapter does not guess at an unofficial one.

Every `remote_cli` command a user would invoke (`submit`, `status`, `poll`,
`fetch`, `reconcile`) exists today. `submit`/`poll`/`fetch`/`reconcile` are
exercised in this skill's own test suite against both a `FakeAdapter` and
`adapters/kaggle.py` (the latter only ever against a fake `kaggle`
executable — no test in this suite reaches the network or a real account).

- `scripts/jobfolder.py` — `generate-job`, driven through `remote_cli.py`
  the same way every other command is: `remote_cli.py` loads it as a
  sibling module (`JOBFOLDER = _load_sibling(...)`) and its CLI parser gains
  a `generate-job` subcommand. `generate_job()` builds
  `<target>/tools/<service>/<job-name>/` — `run-config.json`,
  `runner.ipynb`, and one adapter-supplied metadata file — from
  target-supplied values (`--service`, `--job-name`, `--product`,
  an optional `--commit`, `--repo-url`/`--repo-ref`, `--clone-path` repeated,
  `--run-module`/`--run-function`/`--run-kwargs`, an optional
  `--smoke-module`/`--smoke-function`/`--smoke-kwargs`, and an optional
  repeatable `--smoke-required-evidence` — see "Smoke" below for what that
  last one is for) plus one adapter
  registry call: `ADAPTER.resolve_metadata(service)(run_config)` returns an
  opaque `(filename, text)` pair this module writes without ever learning
  what either means — the same registry `adapters/kaggle.py` already
  registers `assemble_metadata` under (see above). `--target` is resolved
  first, and `resolve_destination()` derives the job folder's path from
  that resolved value and refuses outright when the result does not stay
  under `target` — the guard against a crafted `--service`/`--job-name`
  (`../../etc`, say) writing outside the target repository. `run-config.json`
  is written first inside a `<job>.partial/` staging directory, then
  `runner.ipynb`, then the metadata file, and only a fully-written
  `.partial/` is ever renamed into place with `os.replace` — a half-written
  job folder cannot exist. Regeneration (`--regenerate`) replaces an
  existing job folder the same way, via a double-rename (existing folder
  aside under a fresh unused name, new folder into place, aside folder
  removed only after that second rename actually succeeds) so `destination`
  is always either the old folder or the new one, never neither and never a
  mix. A leftover `<job>.partial/` from a previous failed generation is
  reported and refused, never read as a job folder. `run-config.json`'s
  schema is validated both when `generate_job()` builds one and by a
  standalone `validate_run_config()` any future reader can call again;
  `clonePaths` is validated structurally at generation (non-empty, no
  absolute path, no `..`) by `validate_clone_paths()`.

  **A run declares one of two shapes, and a notebook is one of them.**
  `run` (and `run.smoke`) is a UNION: either a `module`/`function` pair or
  a `notebook` path, never both and never neither. `jobfolder.
  run_block_kind()` is the single judge, and it is re-run on every READ,
  so a job folder that acquired a shapeless or double-shaped block any
  other way — hand-edited, written by an older generator, copied between
  machines — is refused at `submit`, the decision point that spends the
  quota. Declared at the CLI as `--run-notebook`/`--smoke-notebook`
  (`--run-module` therefore lost `required=True`; the refusal for
  declaring no shape at all moved into `run_block_kind()`, where both
  shapes are visible and argparse's own error could not have named the
  second one).

  **Why the notebook shape exists.** A callable that documents itself as
  *"exactly what the pilot notebook's own cells run"* is an assertion
  nothing checks, and it has already drifted: the notebook gained a
  second pass, the callable did not, and what a pilot validated stopped
  being what a worker would run while the docstring still claimed it was.
  A job that names the notebook itself cannot drift from it. **The
  callable shape stays reachable**, deliberately — a worker asked to
  settle one question is legitimately a function call, and some entries
  cannot be named by a `module`/`function` contract at all. This adds a
  way to send a notebook; it removes nothing.

  **A notebook is an entry to the import cross-check too.** Nothing
  imports a notebook, so `resolve_clone_paths()`'s module queue can never
  reach one; `entry_notebooks` seeds it by path instead, parsing the
  notebook's code cells (`notebook_code_source()`, which drops `%` magic
  and `!` shell lines — a named transformation, not a silent tolerance:
  `%run other.ipynb` reaches nobody) and walking every import they make
  through the identical machinery a module's imports go through. Without
  it, a notebook importing a package no `--clone-path` declares generated
  cleanly, pushed, and died in the kernel with `ModuleNotFoundError`
  after the quota was spent — the failure the module-side cross-check was
  built to close, left open on the one entry the pilot actually
  validated. A notebook never becomes a `computed` clone path of its own:
  it is not a module and maps to no package directory, and whether it is
  DELIVERED is the `declared-notebook-reachable` condition's question,
  asked of the pin.
  `runnerTemplate` records each runner asset's path and sha256 as inert
  provenance — deliberately not a drift check; adding one would be a second
  staleness condition, out of bounds for this skill (see design #744
  section 2).

  **The pin conditions.** Before any of that — before clone paths are
  even resolved, before a byte is written, before any quota is spent — the
  pin goes through every condition in the table below. They live in ONE function,
  `jobfolder.verify_pin_preconditions()`, and both decision points call it
  and nothing else: `generate-job`, which writes a job folder, and
  `submit`, which spends remote quota. One word differs between the two
  calls — the one that appears in the refusal. The order below is the
  contract, and it is cheapest-first: the local, instant questions come
  before the one that reaches a network. The first failure refuses; nothing is
  written, nothing is submitted, no ledger event is appended.

| # | id | Condition | Enforced at | Refusal names |
|---|---|---|---|---|
| 1 | `clean-worktree` | The working tree is clean over the declared clone paths — `git status --porcelain`, so an untracked file counts and an ignored one does not. Not a repository, or no commits, refuses too. | `generate-job`, `submit` | Every offending path, and `git add`/`git commit`/`git restore` as the remedy |
| 2 | `pin-is-head` | The pin is HEAD, or nothing changed between the pin and HEAD under the declared clone paths. `unknown` refuses as firmly as `drift`. | `generate-job`, `submit` | The changed clone paths, the pin and HEAD, and git's own message |
| 3 | `declared-paths-exist` | Every declared clone path exists at the pin — `git cat-file -e <pin>:<path>`, asked of the pin and never of the working tree. `sparse-checkout` accepts a path the tree does not contain and fetches nothing for it, silently. | `generate-job`, `submit` | Every absent path, and that the remedy is committing them and pinning the commit that carries them |
| 4 | `declared-notebook-reachable` | Every notebook the run block declares (`run.notebook`, `run.smoke.notebook`) is covered by a declared clone path AND exists at the pin — `git cat-file -e <pin>:<notebook>`. Nothing imports a notebook, so the import cross-check has no representative for it and `sparse-checkout` reports nothing for a path its patterns do not cover. A job declaring no notebook passes through untouched. | `generate-job`, `submit` | Every notebook no clone path covers, every notebook absent at the pin, and the remedy for each |
| 5 | `pin-published` | The declared remote can serve the pin — `git fetch --dry-run --depth 1` from a scratch repository. Credentialless that probe is anonymous; with `--repo-credential` it authenticates through the staged askpass material (see the Colab environment block) and an SSH-shaped `--repo-url` refuses by name. | `generate-job`, `submit` | The commit, the remote URL, the missing push addressed to `--repo-ref`, and git's own message |

  **Why the `clean-worktree` condition exists, and why it is `status` and not `diff`.**
  `resolve_clone_paths()` walks the WORKING TREE. Without this condition
  generation validated bytes the runner would never receive: a brand-new
  `run_search.py` that was never `git add`ed satisfied the import walk
  happily and was simply absent from the commit the runner clones, and the
  job died in the kernel with `ModuleNotFoundError` after quota was spent.
  `git diff` cannot catch that — it enumerates changes to *tracked*
  content, so an untracked path is outside its domain by construction. The
  pathspec is what keeps generation possible at all, since `generate-job`
  writes its own untracked output under `<target>/tools/`.

  **Why the `pin-is-head` condition refuses here and only reports at `read()`.** It is
  the same verdict, from the same one computation
  (`jobfolder._staleness_for()`), consumed two ways on purpose: it
  **refuses at a decision point** and **only reports** at `read()`.
  Reading is an observation — refusing there would make a drifted job
  folder unreadable, which is the one state where reading it matters most,
  and `status`, `fetch` and `reconcile` would lose the ability to say what
  is wrong. Refusing belongs where something irreversible is about to
  happen. For a long time only the reporting half existed, and a job
  folder pinned to code that had already moved on was generated, submitted
  and run with the drift printed beside the submission id like weather.

  **`--commit` is optional, and defaults to HEAD.** Omit it and the pin is
  the target's HEAD; stdout reports the commit and `commitSource:
  default-head`, so you can see what was pinned without opening the job
  folder. That source is stdout only — it describes how you typed an
  argument, not a fact about the job, and `run-config.json` records facts
  about the job. The default is safe only because of the `clean-worktree`
  and `pin-is-head` conditions: HEAD is the code that was validated
  precisely because the tree is
  clean over the clone paths and the pin is that commit. It is resolved
  locally, with `git rev-parse HEAD`, and never from the remote — the
  remote's tip was measured to be older than the entrypoint the operator
  needed, so a remote-derived default would pin code older than yours,
  pass every local check and die in the kernel after quota is spent. An
  explicit `--commit` is never substituted, discovered or overridden, and
  meets every pin condition the same way.

  **No escape hatch.** There is deliberately no dirty-tree escape hatch:
  no flag accepts a dirty tree, a drifted pin or an unpublished commit,
  and none will be added.
  Every refusal names the exact commands you can run and stops there: the
  tool never commits or pushes on your behalf, and never stages, stashes,
  resets or fetches into your repository either. A commit message is a
  human artifact, and an automatic commit poisons the very history later
  used to say which code produced which number.

  **The reachability probe** — the `pin-published` condition in detail. `generate-job`
  refuses a `--commit` the declared
  `--repo-url` cannot serve. `git cat-file -e` proves only that the pin
  exists in the checkout you are standing in, which is never in doubt and
  is not the question; the runner clones a *remote* and checks the pin out
  inside the kernel, so an unpushed pin fails there, after quota is spent.
  `git ls-remote <url> <sha>` cannot answer it either — `ls-remote` matches
  ref *names*, so a bare 40-hex pin comes back empty with exit 0 whether or
  not the remote has it. What answers it is `git fetch --dry-run --depth 1
  <url> <sha>`, whose exit code is the remote's own upload-pack either
  serving the commit or refusing it with `not our ref`.

  Three properties of that probe are load-bearing, and each was learned by
  getting it wrong first:

  1. **It runs in a scratch repository, thrown away afterwards — never in
     your repository.** A repository that already holds the pin answers the
     request from its own object store without contacting the remote at
     all, and the repository you ran `generate-job` from always holds the
     pin you just committed. The first version of this check asked from
     there and therefore passed for every pin anyone could write.
  2. **`--depth 1`, matching what `assets/runner_bootstrap.py` fetches.**
     The probe is only meaningful if it is the runner's own operation.
     `--dry-run` suppresses ref updates but not object transfer, so a
     full-depth probe would pull unbounded history on every generation —
     and running any depth inside your repository would leave those objects
     there (12.8 MiB per generation, measured against this project's own
     remote).
  3. **It is unauthenticated by default — and, with `--repo-credential`,
     it authenticates exactly because the runner will.** Credentialless,
     the child's environment is built from an allowlist that admits
     `PATH`, proxy configuration and the trust store, and admits no
     credential helper, no agent socket and no `HOME`;
     `runner_bootstrap.py` clones with no credential step either, so a
     probe that authenticated would pass jobs whose runner can never
     clone the repository — the same defect one layer up. An SSH
     `--repo-url` is not refused on sight; it is probed like any other
     and, if it fails, the refusal says the probe was unauthenticated so
     the failure is not misread as a local accident. With
     `--repo-credential`, the amendment S3 adds: the credential is
     staged for the RUNNER too (uploaded beside the executor, used by
     `clone_repo()`'s clone) and both transports are pinned to
     `https://` — with a credential, only `https://` remotes are
     admissible, an SSH-shaped remote refuses by name, and every other
     scheme refuses naming the rule. The credential value itself rides
     `_run_git()`'s `extra_env`, a per-call channel separate from the
     allowlist above, which this route never widens.
  4. **It owns its own time budget, `PIN_PUBLISHED_TIMEOUT_SECONDS` (240s)
     — a SEPARATE constant from `GIT_TIMEOUT_SECONDS` (120s), never the
     same one reused (Finding 4 case A).** That local budget times the two
     nearly-instant, purely-local calls elsewhere in this module
     (`rev-parse`, `cat-file -e`); this probe is the one call that
     transfers real bytes over the network, and measured against the live
     remote this skill targets, 12.4 MiB on a slow link took 209s once and
     27s on an identical re-run of the SAME commit. A shared 120s budget
     once made the verdict track the LINK, not the pin: the slower run
     reported the commit as "not pushed" from transfer time alone — a true
     measurement producing a false conclusion. 240s (~1.15x the measured
     worst case) is picked from that measurement, not invented.

  The refusal names the commit, the remote, the missing push addressed to
  `--repo-ref`, and carries git's own message. Failure to create or
  initialise the scratch repository refuses on that same path: a question
  that cannot be asked is never reported as a clean answer. Nothing is
  written into your repository by the probe — no ref, no `FETCH_HEAD`, no
  object — and the tool never commits or pushes on your behalf.

  **The refusal also states how much the recommended push would carry,
  when that can be known from your own clone's cache — never from the
  network.** Once the probe above has already failed for any reason
  other than its own timeout, a second, purely local reader asks one
  further question: how far is the pin beyond the last state *your
  clone* recorded for the declared remote? It reads only `git config`,
  `git rev-parse` and `git rev-list --count` against your own
  repository — never `ls-remote`, never a fetch, no bytes moved and no
  connection opened — and it owns its own small time budget,
  `PIN_WEIGHT_TIMEOUT_SECONDS`, a THIRD constant distinct from both
  `GIT_TIMEOUT_SECONDS` and `PIN_PUBLISHED_TIMEOUT_SECONDS`. The refusal
  this produces takes exactly one of two shapes:

  - **Measured** — your clone has a remote-tracking ref
    (`refs/remotes/<name>/<branch>`) whose configured URL is an exact,
    byte-for-byte match of the declared `--repo-url`. The refusal then
    states the exact commit count between that cached ref and the pin,
    and still names the push-and-pin remedy. That count is exact about
    your clone's cached record of the last fetch — it is **not** a live
    read of the remote, so it makes no claim about the remote's actual
    state right now, and no claim about how much remains to be pushed.
  - **Unmeasurable** — anything less than an exact URL match (a
    different scheme, a trailing `.git`, an SSH form naming the same
    host as an HTTPS form, two remotes sharing one URL, no matching
    remote at all, or a matching remote with no tracking ref yet)
    resolves to unmeasurable, on purpose: this tool never normalises or
    guesses at a URL match, because a number anchored on the wrong
    remote would look measured and would not be. The refusal states what
    is known and prescribes no remedy from a measurement that was never
    taken.

  **A timeout is refused through its own, separate message, never folded
  into the one above.** `_run_git()` raises `GitTimeoutError` (a distinct
  `JobFolderError` subclass) for an expired timeout; `_verify_commit_reachable()`
  catches it in its own branch and says the question could not be finished
  asking, which is NOT the same fact as the remote answering no — the two
  must never share a message, or a slow-but-published pin reads exactly
  like an unpublished one.

- `assets/runner_bootstrap.py` (cell 0) and `assets/runner_invoke.py`
  (cell 1) now hold their REAL content — copied byte-for-byte into every
  generated `runner.ipynb`, with zero interpolation, by `jobfolder.py`'s
  `build_notebook()` exactly as before. Both files are importable modules:
  nothing runs at import time, and the one orchestrating call in each
  (`bootstrap()`, `invoke()`) sits behind `if __name__ == "__main__":` —
  the state a notebook cell's own top-level code runs in, and what lets
  the forge test suite (`RunnerBootstrapTests`, `RunnerInvokeTests`)
  import each file under its own module name and drive every function
  directly against fake `run-config.json` payloads, with no notebook and
  no real clone involved for most of them.
  - `runner_bootstrap.py`'s `bootstrap()` runs, in order: read and
    validate `run-config.json` (`load_run_config`); sparse-clone the
    pinned commit (`clone_repo`, entirely through `_run_git()` — the one
    composition point for every git call: `shell=False`, list argv, a
    PATH-only env allowlist, an explicit timeout, non-zero exit is a
    refusal); put the clone's `src/` on `sys.path`
    (`add_clone_to_path`); import every declared entry module (the
    normal `run.module` and, when present, `run.smoke.module`) and
    assert each one's `__file__` resolves under that same clone
    (`verify_imports_under_clone` — the "pip-installed copy" refusal);
    detect hardware (`detect_hardware` — `torch` not importable IS
    "hardware missing", with no silent CPU fallback; it also captures
    `archList` and `capability`, described below); write
    `bootstrap.json`; then run the notebook-executor gate
    (`check_notebook_executor`) and the accelerator gate
    (`check_accelerator`). Any refusal along that path raises `SystemExit`
    on the spot, before cell 1 ever gets a chance to run.
  - **The notebook shape, on the worker.** When `run-config.json`
    declares a notebook, cell 0 adds two things and cell 1 adds one.
    `verify_notebooks_under_clone()` is the notebook's counterpart to the
    "pip-installed copy" refusal: a notebook cannot be imported, so the
    equivalent proof is that the file is where the pinned sparse checkout
    should have put it — `git sparse-checkout` reports NOTHING for a path
    its patterns do not cover, so that absence is silent by construction.
    `check_notebook_executor()` then PROBES rather than assumes: this
    cell installs only what the target declared in `environment.install`,
    nothing in this skill can know what a worker image ships, so
    `nbformat`, `nbclient` and `jupyter_client` are imported and the
    notebook's own declared kernel is resolved against an installed
    kernelspec — and a refusal names that same declaration as the remedy.
    The kernelspec half is not hypothetical: a notebook with no
    resolvable kernel made the service's own runner refuse before a
    single cell executed, discovered only after a real push with the
    quota already gone. Both gates run AFTER `bootstrap.json` is
    written, for the reason the accelerator gate already does — a refusal
    whose evidence was never written is unreadable no matter how early it
    fires.
  - `runner_invoke.py` executes the notebook out of the clone and writes
    it back EXECUTED to `<working dir>/executed-<name>.ipynb`. That
    destination is the whole of "the outputs come back": a fetch
    materializes the files the worker left in its working directory,
    which is already how `bootstrap.json` returns, so nothing in the
    ledger, the adapter seam or `fetch` changes at all. It is written on
    the failure path too — a notebook that died halfway is the only
    record of WHERE it died, and losing it means paying the quota again
    to find out. The kernel is started with the clone's own `src` first
    on `PYTHONPATH` (`kernel_python_path()`): cell 0's
    `sys.path.insert()` belongs to the RUNNER process, and the kernel is
    a separate process that inherits none of it, so without this a
    notebook importing the target's own package dies with
    `ModuleNotFoundError` on a worker whose clone is sitting right there.
  - **The handoff, and the third asset that reads it.** The kernel is
    started with `kernel_environment()`'s three variables, and that
    function is the ONE place any of them is decided: `PYTHONPATH` as
    above, plus `FORGE_CLONE_ROOT` (the clone directory) and
    `FORGE_CLONE_COMMIT` (the pinned commit). The names are forge-owned
    and deliberately generic — this is the contract between a runner and
    the notebook it starts, never a name borrowed from one repository.
    `assets/notebook_repo_root.py` is the reading side: the FIRST code
    cell of every notebook a job may run, owned here and copied byte for
    byte into `proposal-implementation`'s kit, where a forge test binds
    the two copies. It answers one question — where is the repository this
    notebook runs against — and every later cell reads what it binds.
    Measured, and the reason both halves exist: these notebooks locate
    their repository two directories above the working directory, which is
    right on a person's own machine and wrong here, because the kernel's
    working directory is the RUNNER's own and the clone sits one level
    inside it. Two directories up then names a directory that EXISTS on
    any worker — the insert succeeds, the wrong tree goes on the path, and
    the run dies later with a missing module naming a package, never the
    wrong root.
    - **Both variables, or neither.** Absent means LOCAL and the cell
      behaves exactly as it always has, checking nothing. One present
      without the other REFUSES: that is an environment somebody built and
      got half right, which is the one case a fallback cannot tell apart
      from a laptop. Cell 1 refuses the same shape from the other side — a
      notebook run with no pin to hand over never starts a kernel at all.
    - **The commit is checked, not trusted.** A root handed over is still
      a directory nobody proved, so the cell reads the checkout's own
      `HEAD` (out of `.git` directly — no subprocess, so no git binary has
      to be on a worker's PATH and no checker of these notebooks has cause
      to skip the cell every later cell depends on) and refuses a
      mismatch. This is the path that spends metered quota and a job that
      runs the wrong commit RUNS: it returns numbers shaped exactly like
      the right ones. The runner clones and the notebook receives,
      deliberately — a notebook that cloned would be a SECOND place
      deciding which commit runs, outside the one function that checks the
      pin before anything irreversible happens.

  **Accelerator contract: declare an architecture list, compare against
  what is installed, refuse only after the evidence is on disk.** A real
  rehearsal died inside the kernel with no kernel image available for its
  device: the torch build installed in the runner's image simply did not
  ship kernels for the architecture the assigned card carried, and that
  failure was invisible for days because no earlier check ever asked
  whether the build and the card actually agreed. Two decisions close
  that gap:

  - **Declare architecture, not a device name.** `run-config.json` may
    carry an additive `accelerator: {kind, architectures[]}`, written by
    `jobfolder.build_run_config()` only when a caller supplies both
    `accelerator_kind` and `accelerator_architectures` — this module
    names those two fields and never a value; the values are whatever
    the caller declares. A device name answers *is this the card I
    named* and breaks in both directions on a card whose name varies
    (a single unit versus a paired one, say); an architecture list
    answers *can this build run here*, which is the question a mismatch
    actually turns on. Omitted entirely, no `accelerator` block is
    written and a job behaves exactly as it did before this field
    existed — additive, `schemaVersion` stays 1.
  - **A job may also declare its own local-sufficiency budget.**
    `generate-job --local-budget-seconds N` writes `run-config.json`'s
    additive `localBudget: {seconds: N}` block, in the identical
    conditional-block site the `accelerator` block above already uses —
    written only when the flag is passed, silence otherwise, never a
    forge-invented default of zero. `the-pilot-decides-the-remote-
    strategy`'s `classify_remote_necessity` (`_core/implementation/
    impl_execution_strategy.py`) compares this declared seconds figure
    against the pilot-projected cost to decide whether a job needs a
    remote worker at all; a job with no `accelerator` and no
    `--local-budget-seconds` classifies `optional` — the recorded facts
    do not decide, and `proposal-implementation`'s `gate` then requires
    an explicit `--elect` naming it, on every gate call.
  - **The from-zero gap, closed (session addition): a job generated with
    no caller-declared accelerator at all is not left unprotected
    anymore.** `generate-job` exposes `--accelerator-kind`/
    `--accelerator-architecture` (repeatable) as an OVERRIDE only; a
    caller who gives neither gets `jobfolder.generate_job()`'s own
    fallback instead of a silent omission: `ADAPTER.resolve_default_accelerator(service)`,
    a THIRD registry beside `register`/`register_metadata`, the same
    shape and the same reason — service knowledge (which architecture a
    backend is expected to hand out) never becomes a forge-invented
    value, and a backend that registers no default leaves generation
    exactly as it always was, no block written. `adapters/kaggle.py`
    registers its own, beside `KAGGLE_WORKER_CAPACITY`, in the identical
    honest framing: observed against real rehearsals (both a `sm_60` and
    a `sm_75` card seen for the same request), not a law, and expected to
    be revised as the service's own hardware pool changes.
    `--environment-requirement` (repeatable)/`--environment-index-url`
    carry no such default — an install is TARGET knowledge (which
    packages one specific repository needs), so `generate-job` only ever
    forwards what a caller explicitly declares, never a registry, never
    a guess.
  - **Compare against the INSTALLED build, and refuse only after
    `bootstrap.json` is written.** `detect_hardware()` now also captures
    `environment.archList` (`torch.cuda.get_arch_list()` — the
    architectures the installed torch build actually ships kernels for)
    and `environment.capability` (the arriving device's own capability,
    from `torch.cuda.get_device_capability()`, formatted the same way
    `archList` names its own entries). `check_accelerator()` then makes
    two assertions, in this order: (1) the arriving `capability` must
    appear in the installed `archList` — the physics check, which needs
    no declaration at all and runs whenever a capability was detected;
    (2) any declared `accelerator.architectures` must be covered by that
    same installed `archList` — this is how a dual-architecture build
    gets VERIFIED rather than assumed. Either failing raises
    `AcceleratorError` (a `BootstrapError` subclass, converted to
    `SystemExit` the same way as every other refusal). Cell 1 already
    cannot run after cell 0's own `SystemExit`, so "before training" is
    structural regardless of ordering; what the ordering decides is
    whether the refusal is READABLE. `check_accelerator()` runs strictly
    after `write_bootstrap_output()`, never before, so `bootstrap.json`
    already carries the arriving device, the torch build, and the
    installed arch list the verdict was computed from by the time the
    refusal fires — a refusal whose evidence was never written is
    unreadable no matter how early it fires.
  - `runner_invoke.py`'s `invoke()` selects the normal `run` block or its
    `smoke` variant (when `run_config["mode"] == "smoke"`, the mode a
    later slice's `submit --smoke` sets) via `select_block()`, resolves
    `module`/`function` through `importlib` via `resolve_callable()`, and
    calls it with its declared `kwargs`.
  - Both files gained their own `*_module_names_no_service` guard, in the
    same family as `jobfolder.py`'s, `adapter.py`'s, `remote_cli.py`'s
    and `credentials.py`'s — eight in total across this skill now.

  `resolve_clone_paths(target, entry_modules, declared_clone_paths)` now
  holds real content, wired into `generate_job()`. It reuses
  `implementation_cli.py`'s `prior_work_state()` idiom exactly for the walk
  itself (`ast.parse` + `ast.walk` over `ast.Import`/`ast.ImportFrom`,
  inspecting only `node.module`/`alias.name`, with no relative-import
  resolution and no per-name submodule disambiguation) — walked
  transitively, over every module the declared entry modules (`run.module`,
  plus `run.smoke.module` when present) reach, instead of over one fixed
  file set. The granularity rule: a resolved import maps to its top-level
  package directory under `src/`, never to a single file (`src/A/B/C.py`
  => clone path `src/A`; a true top-level module `src/A.py` => clone path
  `src/A.py`). An import that is not this repository's own code (its
  top-level segment names nothing under `<target>/src` at all) is filtered
  and never becomes a clone path or an uncertainty.

  It returns `{declared, computed, computedNotDeclared, unresolved}`.
  `computedNotDeclared` non-empty always refuses generation, naming every
  missing path — never a warning, since this is exactly the sibling-import
  bug that broke a real run. `unresolved` names every uncertain case: a
  non-literal `importlib.import_module(...)` call, any `__import__(...)`
  call, a `sys.path` mutation, an unparsable file, or an import that looks
  like this repository's own code but does not resolve to a file on disk —
  a non-empty result also refuses generation unless `--accept-unresolved`
  is passed, which writes the uncertainty verbatim into `run-config.json`'s
  `unresolvedImports` instead of guessing, converting a silence into a
  recorded, reportable decision. `--accept-unresolved` never bypasses a
  `computedNotDeclared` refusal — only `unresolved`.

  **Undeclared-read detection (Unit 1, same-file).** The field incident this
  exists to catch: a job declared its imports correctly and still failed,
  because a module-level `Path` constant chain it never imported anything
  about was READ from at runtime — a resume record, a cached result file —
  and nothing checked whether that resolved path was covered by a declared
  clone path at all. `resolve_clone_paths()` now reuses the SAME parsed
  `ast.Module` tree its import walk already holds for every transitively-
  reached file (no new file traversal) and reads two more node families off
  it: module-level `ast.Assign` (`_fold_module_constants()`, building a
  constant -> `Path` table per file, each constant folded on top of the ones
  already folded above it in the same file) and `ast.Call`/`ast.Attribute`
  (`_scan_read_call_sites()`, classifying every call site against a closed
  read/write/neutral roster).

  The returned dict gains three keys (the corrective batch below added the
  third): `computedReadsNotDeclared` (a folded, target-contained read whose
  resolved path is not covered by a declared clone path — `Path.
  is_relative_to`, never exact-match-only, since a data file legitimately
  nests under a declared directory rather than naming it exactly, AND
  which nothing in the same walked file set writes — see the
  reclassification below), `producedReadsNotDeclared` (the SAME
  containment/coverage test, but the resolved path IS also targeted by a
  WRITE call site somewhere in the same walked file set), and
  `unresolvedReads` (a read call site whose path could not be folded, or a
  folded, target-contained path used in a call this walk cannot classify).
  All three are always present, even empty — never absent.
  `computedReadsNotDeclared` non-empty always refuses generation
  unconditionally, exactly like `computedNotDeclared` — never a warning.
  `producedReadsNotDeclared` non-empty refuses generation unless the
  caller passes **`--accept-produced-reads`**. `unresolvedReads` non-empty
  refuses generation unless the caller passes
  **`--accept-unresolved-reads`**. All three accept-flags
  (`--accept-unresolved`, `--accept-unresolved-reads`,
  `--accept-produced-reads`) are SEPARATE — passing one never waives
  another's refusal. The severity asymmetry that makes these separate
  flags rather than one shared flag: an accepted uncertain IMPORT dies
  loudly in the kernel minutes later (`_refuse_absent_clone_paths`); an
  accepted uncertain READ is reported by nobody — the field incident ran
  green. A shared flag would let the loud hatch cover the quiet ones.
  Each acceptance is recorded verbatim in `run-config.json`
  (`unresolvedReads`, `acceptedProducedReads`), mirroring
  `unresolvedImports`'s own omit-when-empty convention exactly — a job
  folder generated before a field existed simply omits it, and
  `validate_run_config()` checks required fields with no key allowlist, so
  an existing job folder stays a valid, readable job folder regardless.
  There is no declared `reads` field: `_refuse_absent_clone_paths` already
  verifies every declared path at the pin, data file or module alike, so
  only the INFERENCE side was missing.

  **The generation-deadlock CRITICAL, and why `producedReadsNotDeclared`
  exists.** A job whose own purpose is to PRODUCE a file it also reads
  back (a resumable record, exactly the real target's
  `config.<RECORD>` shape: written by `search_record()`'s own run,
  read back by a later one) could not be generated at all under Unit 1 +
  Unit 2 alone: leaving the read undeclared refused unconditionally via
  `computedReadsNotDeclared` (no hatch); declaring it as the file or its
  parent directory instead refused via `_refuse_absent_clone_paths` (no
  tree object at the pin, since the file has never yet been produced).
  Declaring refused; not declaring refused; no third option existed for a
  job's first-ever run. The fix is RECLASSIFICATION using the write
  signal, not suppression: `_scan_read_call_sites()` also collects every
  folded, target-contained path targeted by a WRITE call site anywhere in
  the same walked file set. An undeclared read whose resolved path is
  ALSO written somewhere in that same walk moves from
  `computedReadsNotDeclared` into `producedReadsNotDeclared` — still a
  refusal by default, but now with an escape hatch
  (`--accept-produced-reads`) that lets the job be generated WITHOUT
  declaring the not-yet-existent file, because an undeclared clone path is
  never checked against the pin by `_refuse_absent_clone_paths` at all.
  The operator is still told and still decides — nothing disappears
  silently. This is deliberately NOT the exclusion proposed and REJECTED
  below (Decision 5): that one would have silently dropped the read from
  candidacy entirely, with no refusal and no record, based only on the
  mkdir-then-write shape. Reclassification with a recorded acceptance
  keeps the operator in the loop; silent exclusion would not have.

  Containment FILTERS, it never accuses: a path outside `target`
  (`.resolve()` + `relative_to`) is dropped entirely — not a candidate and
  not an uncertainty — the same `external` posture `_classify_import()`
  gives a non-local import, and the same absolute-path refusal
  `validate_clone_paths()` already applies to a declared clone path. This
  containment drop applies only to a folded MODULE-LEVEL constant: an
  absolute path bound to a module-level constant and never re-assigned is
  dropped silently, never proposed and never a refusal. It does NOT apply
  the same way to a read whose absolute path is built through a LOCAL
  variable — `_fold_module_constants()` never folds locals by design, so
  that shape does not reach the containment test at all; it instead lands
  in `unresolvedReads` (refuses by default, `--accept-unresolved-reads`
  available) via the read-shaped-method-name fallback. The real target's
  own battery probe (`harness.py:167-169`,
  `online = Path("/sys/class/power_supply/AC/online")` then
  `online.read_text()`) is exactly this LOCAL-variable case — it refuses
  by default and takes the hatch, it is never silently dropped by
  containment. (A prior revision of this doctrine and its covering test
  claimed the two shapes were equivalent "regardless of which name holds
  the Path" — measured false; corrected here and in the test that used to
  make that claim.) A write call site (`.write_text`/`.write_bytes`/a
  write-mode `.open`/`.mkdir`/`.touch`/`.unlink`/`.rename`) is never a
  READ candidate — the roster IS that exclusion, and there is deliberately
  NO separate "run-produced output" exclusion layered on top of THAT
  roster (Decision 5, unchanged): a write call site collected for
  `producedReadsNotDeclared` (above) is a completely different mechanism
  — it never removes a read from candidacy, it only moves an already-
  surfaced, already-refusing candidate into the hatch-bearing bucket. That
  exclusion was proposed and REJECTED on measurement: a real target's own
  resume-artifact record is built under a directory the same run also
  `mkdir`s and writes on a later invocation — the same walked file set
  both writes AND reads that constant, so excluding "a path the run
  creates" from candidacy entirely would have suppressed the exact read
  this detector exists to catch, with no record and no refusal at all.
  Under Unit 1 alone that resume-artifact read was cross-module (the
  constant is folded in a DIFFERENT file than the one calling
  `.read_text()` on it) and therefore unfoldable, landing in
  `unresolvedReads` — refusing by default, never silently excused, but
  only via the weakest of the (then two, now three) refusal paths. Unit 2
  resolves exactly this cross-module shape, so that same read now folds
  fully; the corrective batch above is what then keeps that fully-folded
  read generation-reachable at all, by moving it to
  `producedReadsNotDeclared` (write-backed) instead of leaving it in the
  hatch-less `computedReadsNotDeclared`.

  The admitted grammar `_fold_path_expr()` folds is CLOSED and documented,
  never implied complete: `Path(__file__)` and `.resolve()`/`.parent`
  chains off it; `Path(__file__).resolve().parents[N]` with `N` a
  non-negative int literal; `Path("<string literal>")`; a bare `Name`
  already folded earlier in the same file's table; `BinOp(Div)` with a
  string-literal right operand, chained (`X / "a" / "b"`); and
  `.joinpath("a", "b", ...)` with every argument a string literal.
  Everything outside this roster returns `None` from `_fold_path_expr()`,
  never a guess, and is documented here as the same list the helper's own
  docstring carries: f-strings, `%`/`+`/`str.format` string building,
  `os.path.join(...)`, `os.environ[...]`, `sys.argv[...]`,
  `.with_name(...)`/`.with_suffix(...)`/`.stem`/`.glob(...)`, `Path(x)` for
  any `x` other than `__file__` or a string literal, a ternary
  (`ast.IfExp`), `AugAssign`, a tuple-unpack assignment target, and
  `.parents[N]` with a non-literal index. A name assigned twice at module
  level is dropped from the table entirely, never last-wins. A name bound
  ANYWHERE in a non-module scope (a function/lambda parameter, or a local
  assignment/`for`/`with`/comprehension/`except` target) is never folded
  through the table at all, even at its module-scope occurrence of the
  same spelling — a shadowed name lands in `unresolvedReads`, never
  silently resolved to a module constant it happens to share a spelling
  with. An evaluator whose limits are undocumented is a detector that
  implies completeness.

  **The limitation, measured — not a proof about every target.** This check
  finds a read whose path folds from module-level constants. It does not
  find a read of a pinned repository input whose path is built from a
  runtime parameter. Measured on one target: every runtime-parameterized
  path there was a run-produced output, so at that instance the
  unresolvable class and the defect class did not overlap. That is one
  target, not a proof about all targets. Do not inherit a scarier caveat
  than this. All five of one real target's `shard_paths()` consumers are
  write-first: `write_shard_stamp` writes; `seal_shard_stamp` reads back
  what it just wrote; `_partial_path` takes the static branch;
  `<search_entrypoint>` reads a resume artifact a prior run of the same shard
  wrote (this one becomes an `unresolvedReads` entry, not a silent miss);
  `campaign`/`smoke` `mkdir` then open for writing.

  **Cross-module attribute reads (Unit 2).** `sibling.CONSTANT.read_text()`
  — a constant folded in a DIFFERENT file than the one doing the read
  (the real, cited target's own `search_record()` reading
  `config.<RECORD>.read_text()`, the constant folded in `config.py`
  rather than the file calling it) — now resolves too. Chosen as
  LAZY-FOLD-ON-DEMAND, not two-pass: `_resolve_module_constant()` reuses
  `_classify_import()` UNCHANGED (the same function import classification
  already calls) to turn the local name an import bound (`_import_alias_
  map()`) into a sibling file, purely from the filesystem — independent of
  whether the main walk's own queue has visited that sibling yet. This is
  what makes resolution correct regardless of visit order: an entry
  module is always scanned for its own read call sites before its
  transitively-imported siblings are ever popped off the queue, so a
  same-file-only, visit-order-dependent design would have missed exactly
  the shape this Unit exists to catch. A per-`resolve_clone_paths()`-call
  cache memoizes each sibling file's folded table by resolved file path,
  so a repeatedly-referenced constant is folded once, not once per
  reference, and doubles as a cycle guard for a circular cross-module
  reference (an edge case no cited target exhibits). A module that does
  not resolve to this repository's own code (`_classify_import()`'s
  `"unresolved"` or `"external"` postures, unchanged) folds to `None`
  exactly like any other unfoldable receiver — the read call site still
  reaches `unresolvedReads` by its own read-shaped method name, never
  silently dropped.

  `validate_clone_paths()` gained an optional `target` argument: when
  given, each clone path is also resolved against it and refused if that
  resolution escapes `target` (the symlink-escape case a purely textual
  check cannot see). This is the SAME validator every caller uses —
  `build_run_config()` at generation time (structural only), and
  `resolve_clone_paths()` again once `target` is known — never a second,
  parallel validator for the symlink case.

  Decision this slice inherited from `cmd_submit`'s own `--product`
  migration (T6b) and did not change: `status`, `fetch` and `reconcile`
  still expose no `--product` flag, only `submit` does. Each of those three
  commands reads an already-generated job folder whose own
  `run-config.json` already declares its product (`product_for()`'s step
  2), so an explicit override is not load-bearing there the way it is for
  `submit`, which can be asked to record a submission for a job folder with
  no declared product at all. `generate-job` itself needs no `--product`
  resolution step either — it writes the declared `product` value straight
  into `run-config.json`, it never has to resolve one from a path the way
  `product_for()` does. Since that gap between "declares the flag" and
  "does not" is real and intentional, `product_for()`'s refusal message
  is derived from `_build_parser()` per calling subcommand (Finding 4 case
  C) rather than naming `--product` unconditionally — a `status` refusal
  used to point a caller at a flag `status` itself refuses to parse.

  `jobfolder.read(job_dir) -> JobFolder` is now the ONE reader. There is
  no `is_stale()` a caller can forget: `JobFolder.staleness` is computed
  INSIDE `read()`, before it ever constructs one, so reading a job folder
  without getting a staleness verdict alongside it is not something this
  module's API can express at all. `JobFolder` carries `path`, `run_config`
  (re-validated on every read through the same `validate_run_config()`
  `generate_job()` already calls, never a second copy) and `staleness`.

  There is exactly ONE staleness condition, always computed, never
  skippable:

  ```
  head    = git rev-parse HEAD                      # detached HEAD unchanged
  exists  = git cat-file -e <pinned>^{commit}
  changed = git diff --name-only <pinned> HEAD -- <clonePaths…>
  ```

  The pathspec (`-- <clonePaths…>`) does the intersection with the
  declared clone paths itself — deliberately: there is no second,
  independent prefix-matching implementation anywhere in this module that
  could drift from `implementation_cli.py`'s own `prior_work_state.reached()`.
  Verdict is `drift` iff `changed` is non-empty, and it is NEVER a
  refusal — staleness informs, it does not block; two non-gating layers
  already cover it (reported at submit and at `generate-job`'s own CLI
  output, `fromStaleSubmission` on `fetch`). `run-config.json`'s
  `runnerTemplate` provenance is deliberately NOT part of this condition —
  see the note on it above; adding a template-drift check would be a
  SECOND staleness condition, which is out of scope by design.

  `unknown`, with a reason, whenever the question cannot be answered at
  all: no git history, not a repository, or an absent pinned commit —
  reusing `implementation_cli.py`'s own `prior_work_state()`
  `recordStatus: "unavailable"` → `unknown` discipline, never letting an
  unanswerable record pass for a clean one. `unknown` is never rendered as
  `fresh`: absence of evidence is not evidence of freshness, and the two
  are separate branches in `_staleness_for()`, neither one falling back to
  the other.

  `clonePaths` is validated again inside `read()`, through the SAME
  `validate_clone_paths()` `generate_job()` already calls at generation
  time (including its optional `target` argument for the symlink-escape
  check) — never a second, parallel validator. The target a staleness
  check runs `git` against is derived structurally from `job_dir` itself
  (`<target>/tools/<service>/<job-name>/`, exactly as
  `resolve_destination()` builds it), not accepted as a second argument.

  `read()` has its own `_run_git()` — a SEPARATE single composition point
  from `assets/runner_bootstrap.py`'s own `_run_git()` (the two modules
  share no import), with the exact same discipline: `shell=False`, list
  argv, a `PATH`-only env allowlist, an explicit timeout, and `cwd` always
  the caller's already-resolved target — never `git -C` applied to a raw,
  unresolved argument. A pinned commit carrying shell metacharacters
  reaches this argv as one element and is never evaluated by a shell.

  Every job-folder-touching command that exists today routes through
  `read()` and reports its `staleness` alongside whatever else it already
  reports: `generate-job`'s own CLI output, `submit`, `status`, `fetch`
  (both its early "not complete yet" return and its final one), and
  `reconcile`. `remote_cli._job_folder_staleness()` is the one place that
  decides WHETHER a given entrypoint has a job folder to route through at
  all — `None` for the legacy shape (no job folder exists) and for a
  `run-config.json` `read()` cannot make sense of, the same tolerant
  "falls through cleanly" rule `product_for()`'s own narrower run-config
  lookup already applies one step up, so an already-tolerant command never
  became stricter just because staleness reporting was added beside it.
  `poll` is deliberately NOT routed: it receives only `--submission-id`
  and must not learn the worker or the job, so it has no job folder to
  route through in the first place. `readiness` (see below) now routes
  through this same `read()` too, never a second staleness computation of
  its own. Probe's own `remoteExecution` fact does not exist yet (a later
  slice builds it); once it does, it will route through `read()` the same
  way.

## The commands

`remote_cli.py` accepts exactly nine top-level subcommands; this table is the
closed roster `skill-audit`'s `roster` move derives against, driving the CLI
with a nonce it cannot accept and reading the accepted set out of its own
refusal.

| Command | What it does |
| --- | --- |
| `submit` | submit one notebook to a registered backend's worker |
| `status` | report the fold for one product's ledger; resolves nothing |
| `distribute` | report how opaque work units would spread across every healthy worker account right now; issues no work and records nothing |
| `poll` | ask the adapter for one submission's status |
| `fetch` | materialize one submission's result, quarantining it when it is not current |
| `reconcile` | compare the ledger against the adapter's `list_active()` in both directions |
| `generate-job` | generate a forge-owned job folder at `<target>/tools/<service>/<job-name>/` |
| `smoke` | smoke-run bookkeeping: recording a rehearsal's evidence-derived verdict |
| `readiness` | state whether a job is ready for a full submission on a worker; reports only, issues no submission |

## Smoke — a readiness gate, evidence-derived

A smoke run is a rehearsal, not a submission whose result feeds any report.

| Smoke subcommand | What it records |
| --- | --- |
| `record` | a `smokeResult` event: pass/fail derived from `shard_io.completeness()`, never a human assertion |

**A distinct file, not a fourth ledger `kind`.**
`<target>/<product>/.remote-execution/smoke.jsonl` lives beside
`ledger.jsonl`, appended through the exact same `ledger.append()` — but a
different FILE, load-bearing not stylistic. A fourth `kind` inside
`ledger.jsonl` was rejected: `fold()` indexes `latest[entrypoint]`, so a
smoke submission recorded there would become that entrypoint's latest
`submitted` event and silently reclassify a real, still-pending full run
as superseded. `fold()` never reads `smoke.jsonl`, so that is structurally
impossible. `smoke.jsonl` carries two kinds with no such conflict, since
nothing folds it that way: the ordinary `submitted` event a smoke
SUBMISSION writes, and a `smokeResult` event `smoke record` writes.

**`submit --smoke` stays explicit and human-invoked.** It sets
`run_config["mode"] = "smoke"` on the `Job` — opaque to `packer.py`/
`ledger.py` like every other `run_config` key — and routes the resulting
`submitted` event to `smoke.jsonl` instead of `ledger.jsonl`.
`assets/runner_invoke.py`'s `select_block()` already branches on that mode
to pick the declared `run.smoke` block over the normal `run` block.

**The verdict is not a human assertion.** `remote_cli.py smoke record
--job-dir <dir> --from-artifact <path> --worker <worker>` reads the
artifact (a fetched `shard.json`) and passes iff
`shard_io.completeness(stamp, required)` — the SAME predicate T10's
`merge()` uses — reports it complete. Smoke pass ≡ *the evidence stamp is
complete, at this commit, on this worker*. The `required` list reaches
`smoke record` WITHOUT this forge naming a field of its own: it travels
through `run-config.json`'s `run.smoke.requiredEvidence`, declared by the
TARGET at `generate-job` time via the repeatable
`--smoke-required-evidence` flag — carried, never interpreted, the same
way `run.module`/`clonePaths` already are (confirmed by
`test_remote_cli_source_names_no_evidence_field_of_its_own`). Declaring
that list without a smoke block is refused at generation time. `smoke
record` routes through `jobfolder.read()`, and — unlike
`_job_folder_staleness()` — does NOT swallow a `JobFolderError`: this
command has no legacy-shape fallback to fall through to.

**Readiness, and no clock.** `remote_cli.py readiness --job-dir <dir>
--worker <worker>` reports whether a job is ready for its full submission
on that worker — issues no submission, offers no menu, the same
"reports and resolves nothing" discipline `status` already holds
structurally (no `adapter` parameter in either signature). It binds three
facts on the LATEST `smokeResult` record for this job (append order, last
line wins): `result == "pass"`, `commit` equal to the job's CURRENT
pinned commit, `worker` equal to the worker asked about. Nothing here
reads a timestamp — a record's usefulness expires the moment the job
re-pins to a different commit or the worker changes, never after elapsed
time.

`probe` states the fact and submits nothing — `readiness` still reports
only and still issues nothing: its own signature takes no `adapter`
parameter, exactly as before. What changed (design §4,
`the-position-nobody-holds`): a non-rehearsal `submit` now READS this same
three-fact bind — through `gate`'s own recorded transition, never through
`readiness` directly — so a job whose `smokeReady` is not `True` cannot be
gated, and an ungated job cannot be submitted at full scale. `piloted` (a
`proposal-implementation` concept) remains untouched and still implies
nothing.

This is narrower than it may first read, and the distinction is
load-bearing: `probe`'s own ECHO of `smokeReady` still gates nothing —
that row above is unedited, and reading it is still purely informational.
What now gates is `readiness`'s underlying THREE-FACT MEASUREMENT, reached
only through a separately-recorded `gate` transition — permitting the
rehearsal to unlock authorization is not the same as branching on the
reported fact itself.

## Why append, not a status record

A lost append is detectable — the file is simply shorter than expected, or a
line is malformed. A lost in-place mutation of a "current status" record is
not: the write either lands or it silently doesn't, and there is no earlier
version left to compare against. So this ledger only ever grows. Resubmitting
something appends a new `submitted` line; it never erases the one it
supersedes.

## Why an append can be trusted

Four things, held together, and the first two are enforced in code, not by
convention:

- The return value of `os.write()` is checked against the byte count of the
  event about to be written, and a mismatch raises. A write can legitimately
  return short, and a short write is exactly what tears a JSONL line — a
  torn line is a lost submission, which is the one outcome this ledger
  exists to make impossible. This check is the actual defence, not the mere
  existence of an append call.
- Every event is capped at 4096 bytes before it is ever written. The
  fields in this schema — a path, a 64-hex digest, an opaque id, a worker
  name, a timestamp, an already-truncated failure reason — have no business
  producing a line anywhere near that size; exceeding it means something
  that should have been truncated was not. This number is a sanity bound on
  this schema, not `PIPE_BUF`: `PIPE_BUF` governs pipes and FIFOs, not
  regular files, and its value is platform-specific anyway (512 on darwin,
  4096 on Linux) — the wrong number, from the wrong object, and on this
  platform from the wrong operating system.
- `O_APPEND` on a regular, local file makes seek-to-end-and-write atomic as a
  unit with respect to other appenders, so two concurrent writers cannot
  interleave into the same region. `append()` writes through a raw fd
  (`os.open`/`os.write`), never Python's buffered `open(path, "a")`, because a
  buffered file object may split one logical write across syscalls and
  reintroduce exactly the interleaving `O_APPEND` exists to prevent.
- The ledger lives on a local filesystem only. NFS does not honor `O_APPEND`
  atomicity; the ledger is expected to live inside the target's own git
  checkout, which is a local clone.

## Event kinds

| event | fields |
|---|---|
| `submitted` | `ts`, `entrypoint`, `sourceDigest`, `submissionId`, `worker`, `requestedCapacity`, `grantedCapacity` |
| `returned` | `ts`, `submissionId`, `artifactPath`, `observedConcurrency` |
| `errored` | `ts`, `submissionId`, `reason` (truncated to 512 chars) |

`entrypoint` is the field name for the thing executed remotely — not
`notebook`. This schema and the adapter seam (`scripts/adapter.py`) both use
the same name for it, and neither carries a format opinion about what it
points to; that policy question belongs to the CLI that submits, not to
this record.

This table is `ledger.jsonl`'s own vocabulary — the one `fold()` indexes
by `latest[entrypoint]`. `smoke.jsonl` is a physically separate file (see
"Smoke" above) and carries its own, unrelated vocabulary:

| event | fields |
|---|---|
| `submitted` | the same shape as above — written by `submit --smoke` |
| `smokeResult` | `ts`, `jobName`, `result` (`"pass"`/`"fail"`), `commit`, `worker`, `missing` — written by `smoke record` |

## Environment

**This skill's own Python is stdlib-only except one named driver script.**
The prior sentence here claimed a floor this section no longer defends and a
packaged-client absence this driver script disproves; both are retired
outright, not softened into a paraphrase that would leave the same claim in
different words. Every module here — the ledger, the adapter seam, the packer, `remote_cli.py`,
`jobfolder.py`, the runner assets — imports nothing beyond the standard
library. The one exception is `adapters/kaggle_driver.py`: it imports
`kagglesdk`, this repository's own `requirements.txt` pins at
`kagglesdk==0.1.37` (see the credential-transport table above) — a
STANDALONE distribution since 2025-07-11, not vendored inside the `kaggle`
CLI; that claim
was true of the retired `kaggle==1.7.4.5` and does not carry forward — and
it is the ONLY file in this skill permitted to import it. Nothing
else in this skill needs it: the ledger, the packer, the seam and every
command that only reads them run with no packaged client installed at all.
But `submit`, `poll`, `fetch` and `smoke` all end at that one driver script,
so on an interpreter that cannot import `kagglesdk` they cannot start.
`kagglesdk==0.1.37` itself declares `Requires-Python: >=3.11`.

**No enforced minimum Python version in THIS skill's own code — the
driver's own selftest gates, never a version number.** This skill declares
no `python_requires` and holds no version floor anywhere in its own code;
what actually gates is `kaggle_driver.py selftest`, run against the exact
interpreter that will invoke it (`sys.executable`, inherited from the
calling adapter process). It reports whether `kagglesdk` imports under
that interpreter and, if it does not, refuses by name — the interpreter
path and the exact install command — rather than asserting a version
nothing checks (`test_driver_selftest_imports_kagglesdk`). Measured on
this machine: `kagglesdk==0.1.37` is installed and importable under this
forge's own `.venv` (Python 3.12.13); it requires >=3.11 as its own
declared floor, which is a fact about the DEPENDENCY, not a floor this
skill's code enforces on its own — whichever interpreter a given machine
actually resolves `sys.executable` to is the one the selftest must pass
under, empirically, never a version this skill's own code promises in
advance.

Check pip's own note about where it put the driver's dependency: if that
directory is not on the resolving interpreter's import path, the package is
installed and still unreachable, which reads exactly like not having
installed it. A backend that cannot be found refuses by name and says this —
see `KaggleAdapter._run` and `kaggle_driver.py`'s own import-time refusal —
rather than surfacing a raw traceback and leaving a reader to guess.

**The Colab backend (`adapters/colab.py`).** Installed as the service's own
headless CLI, pinned exactly:

```
uv tool install --force --python 3.14 google-colab-cli --with "jupyter-kernel-client<1"
```

The pin is not decorative: `google-colab-cli` 0.6.0 with
`jupyter-kernel-client` 1.x crashes every `exec` (`AttributeError: module
'jupyter_kernel_client' has no attribute 'KernelClient'`; upstream #94), so
the working combination is 0.6.0 with the 0.x client that a bare dependency
resolution does not pick. The adapter shells out to `colab` on `PATH` by
default; a non-default location can be supplied as `colab_executable` when
constructing `ColabAdapter` directly.

Authentication is the CLI's own oauth2 consent ritual — run any `colab`
command once in a terminal and approve it — and the adapter never reads
`~/.config/colab-cli/token.json`: the CLI's own child process resolves it
from the `HOME` the adapter forwards, and no module above the seam learns a
path to it.

Sessions are expensive and idle-reclaimed, so release is part of the flow,
not housekeeping: `fetch` stops a session only AFTER the manifest has
landed AND the run is terminal; the adapter spawns the CLI's own keep-alive
(best-effort) to hold a session through a long run; a released or expired
session is simply gone, and the operator's own `colab stop -s <name>` is
the manual exit. When you are done with a session, stop it — an abandoned
one burns the account's capacity until the service reclaims it.

**Never read, copy or print `~/.config/colab-cli/sessions.json`.** It
carries a live per-session access token beside each session record
(measured in spike S0), which makes it credential-grade: every session fact
this skill uses comes from the CLI's own stdout instead.

**Private repositories: `--repo-credential` (both `submit` and
`generate-job`).** It names a token file; only backends that declare
`REPO_CREDENTIAL_CARRIER` accept it (the Colab adapter does), and with it
only `https://` remotes are admissible — an SSH-shaped remote refuses by
name, because the runner's clone has no SSH agent and no key, and every
other scheme refuses naming the rule. The reachability probe authenticates
through the same staged material the runner's clone uses, so a pass means
the RUNNER can clone. The bytes are read at exactly one expression per
site, never appear on argv, in `run-config.json`, in the job folder or in
the ledger, and the staged material is deleted on the VM after the run.

A second backend brings its own answer to this section: nothing above the
adapter seam knows a service exists, so nothing above it knows what a service
needs.

## Ledger data location

Code is forge-owned and lives here, inside the skill. Data is target-owned:
`<target>/<Name>/.remote-execution/ledger.jsonl`, inside the target's own git
checkout, alongside the repository whose submissions it records.

## Smoke data location

`<target>/<product>/.remote-execution/smoke.jsonl` — the SAME directory
`ledger.jsonl` lives in, product-scoped exactly like it, but a distinct
file (see "Smoke" above for why that separation is load-bearing, not
stylistic).

## Quarantine location

`<target>/<Name>/.remote-execution/quarantine/<submissionId>/` — a
`fromStaleSubmission` result's fetch destination, structurally outside
`Results/shards/`. This is what makes the non-merging structural rather than
procedural: the tree a shard reader enumerates never contains this path, so
there is nothing a filter could forget to apply.
