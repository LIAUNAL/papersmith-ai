---
name: remote-execution
description: "Trigger: durable record of what a repository has submitted to a remote worker, what came back, and how much to submit at once: the append-only ledger and the fold that derives per-entrypoint state, the capacity clamp and worker auto-selection, the `remote_cli` front door (`submit` with its path guard, `status`, `poll`, `fetch`, `reconcile`, `distribute`, `remaining`, `generate-job`, `smoke`, `record`, `readiness`, `preflight`, `generate-jobs`), the backend-agnostic adapter seam (ABC, frozen shapes, registry), and one shipped backend -- `adapters/kaggle.py`, the only file here allowed to name a service, shelling out to `adapters/kaggle_driver.py`, the only one allowed to import the pinned `kagglesdk` client. Credentials travel as a `CredentialHandle(worker_id, token_path)`, read at one expression in that one file; readiness is derived from `smoke.jsonl` evidence, never a human assertion and never a clock. Stdlib-only except that one named driver script."
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
  truncation rules this schema fixes (see below). The fold keys each
  submission by `lane_key()`: `(entrypoint, worker)`, or `(entrypoint,
  "<worker>#slot<n>")` for a campaign's slot `n >= 2` on that worker, so
  two concurrent slots of one campaign are two independent "latest" facts
  that neither supersede nor quarantine each other. `pending_for(worker)`
  counts every lane whose event names that worker.
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
    actually issues it. **One `adapter.submit()` and one ledger event per
    granted slot** (S1, parallel campaigns): `packer.slot_shares()` splits
    each assignment's units round-robin into `min(granted, len(units))`
    shares, and each share is its own job (`run_config["units"]` = that
    share), its own submission id and its own `submitted` event — a worker
    granted two slots (Kaggle's cap) runs two jobs side by side instead of
    one job running its units in sequence. Slot 1 is shaped exactly as a
    one-slot worker's single job always was; slots `n >= 2` add
    `run_config["slot"] = n` (the adapter gives each its own remote
    identity — Kaggle suffixes the kernel title/slug `-slot-<n>`) and a
    `slot` field on the event (its own ledger lane). `poll`, `fetch`,
    `status` and `reconcile` work per submission id unchanged. A backend
    that answers two slots with the same id is refused
    `DUPLICATE_SUBMISSION_ID` before the repeat is recorded. A worker
    granted one slot behaves exactly as before. An assignment a healthy account was granted but
    had no units left to receive (`packer.Assignment`'s own documented
    "had room, didn't need it" case) submits nothing and reports
    `submissionId: null` — capacity with nothing to spend is never turned
    into a fabricated job. The result mirrors `packer.Distribution` field
    for field: `assignments[]` (worker, its whole `Plan`, its units,
    `submissionId` — slot 1's — and `submissions[]`, one `{slot, units,
    submissionId}` per slot), `unplaced[]` (units that did not fit, by identity),
    and `skipped[]` (`worker -> Skip.reason`, unprefixed) — an excluded
    account is always named with its reason, never silently dropped.
    Single-unit `submit` (no `--unit` at all) is untouched: today's
    `select()`/`plan()` path, byte-identical.
  - **Diagram validation, every launch**: when the resolved product holds
    `AGREED.md` (proof of concept) or `Experimental_AGREED.md` (full
    experiments), `submit` — `--smoke` included — refuses
    `DIAGRAM_NOT_VALIDATED` until the operator has validated that kind's
    experiment diagram -- in the dashboard's Experimentos tab ("Validar
    diagrama") or by approving it explicitly in the agent chat, which runs
    `experiment-diagrams validate` with the operator's words -- naming each open kind and its state (`absent`, `pending`,
    `stale`). It runs before the consent gate, so a refusal costs nothing. A
    product with neither marker is not gated. See `skills/experiment-diagrams`.
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

    **Readiness per assigned worker, campaign only** (S2, parallel
    campaigns): because a campaign `gate` record binds no worker, a
    non-rehearsal campaign `submit` checks, once `packer.distribute()` has
    named the accounts and before the first `adapter.submit()`, that every
    worker assigned units reads ready on `readiness` (its own passing
    rehearsal at the job's current pin). Otherwise it refuses
    `CAMPAIGN_WORKERS_NOT_READY`, naming every worker that still needs a
    rehearsal; nothing is submitted. A worker granted capacity but no
    units needs none. The consent token is unchanged (pin, entrypoint,
    ordered units — never workers): readiness is a recorded fact checked
    here, not something the token could bind. A single send keeps its
    current check (its `gate` record names its worker); `--smoke` and the
    legacy no-job-folder shape are exempt, as they are from the gate.

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

  **Team accounts: only owner-mapped Kaggle accounts are workers.** When
  `<workspace>/.papersmith/team.json` maps at least one owner to a Kaggle
  username (`accounts.kaggle.username`), `workers()` returns only the
  accounts kaggle-accounts lists whose username an owner maps — one per
  owner. Every other listed account stays in kaggle-accounts but is never
  a worker, and `submit` to it refuses before any credential is asked for:
  it is "not mapped to a team owner: one account per person — Kaggle
  staff: 'the one account per person applies to all Kaggle site use'"
  (https://www.kaggle.com/discussions/general/192527, verified
  2026-10-25). Registering a second account under a different email does
  not make it a different person's account. An owner whose mapped
  username kaggle-accounts does not list is reported as not validated and
  yields no worker until that account is taken in and validated.
  `KaggleAdapter.team_report()` returns all three lists (`workers`,
  `excluded` with each reason, `not_validated`), and the declared capacity
  counts mapped workers only. The adapter reads two fields per member
  (`owner`, `accounts.kaggle.username`) and nothing else; it refuses a
  registry that is not schema 1, an owner listed twice, and the same
  username under two owners. With no registry, or one mapping no Kaggle
  account, every listed account is a worker exactly as before.

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
| 11 | `fetch-origin` | A per-file download sends the stored credential only to a Kaggle origin (`api.kaggle.com`, `www.kaggle.com`, `kaggle.com`, over https); any other host, a signed storage URL included, gets a bare GET, and a redirect that leaves Kaggle drops the credential for every later hop | `kaggle_driver.py`'s `_fetch_file()` | `test_fetch_sends_the_bearer_credential_only_to_kaggle_origins` |

  Rows 8-10 are new to the child-driver topology; rows 1-7 hold verbatim
  under it — the sink is still `_env_for()`, only what reads the value on
  the other end changed (the `kaggle` CLI's `authenticate()` before this
  change, `kagglesdk`'s own `_try_fill_auth()` now). Row 11 retires the
  defensive choice `fetch` used to make for the per-file download URLs
  `list_kernel_session_output` returns: it sent this session's Bearer
  credential to whatever host a URL named, and a URL in a response is no
  authority to send a credential there. Those downloads also follow
  redirects by hand (https only, at most five), give every hop a 10 s
  connect and 60 s read timeout, and stream to disk under one 20 GiB
  budget per fetch. The output listing is paged: `fetch` follows
  `next_page_token` to the last page, and refuses a repeated token or more
  than 1000 pages. Whether Kaggle's own file URLs need the credential at
  all is still unrehearsed against a live account; a rehearsal runs only
  on the user's explicit permission.

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

  **The run notebook is cloned on its own.** `generate-job` appends every
  `--run-notebook`/`--smoke-notebook` that no declared `--clone-path`
  covers to `clonePaths` as the notebook FILE itself
  (`jobfolder.with_entry_notebooks()`), so the notebook needs no
  `--clone-path` and only it enters the pin's staleness check. Declaring
  the whole folder instead (`--clone-path <Name>/Notebooks`) still works
  and is kept exactly as declared, but it makes EVERY notebook in that
  folder part of the pin: re-running and committing an unrelated notebook
  there (a report, say) stales the job (`pin-is-head`) and sends it back
  through smoke, proposal, offer and gate. A declared path is never
  dropped or narrowed. `git sparse-checkout set` delivers a file path in
  both modes (cone mode, the default since git 2.37, also brings the
  notebook's sibling files at the same pinned commit; they never enter
  staleness).
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
| 4 | `declared-notebook-reachable` | Every notebook the run block declares (`run.notebook`, `run.smoke.notebook`) is covered by a declared clone path (generation adds an uncovered notebook as its own clone path) AND exists at the pin — `git cat-file -e <pin>:<notebook>`. Nothing imports a notebook, so the import cross-check has no representative for it and `sparse-checkout` reports nothing for a path its patterns do not cover. A job declaring no notebook passes through untouched. | `generate-job`, `submit` | Every notebook no clone path covers, every notebook absent at the pin, and the remedy for each |
| 5 | `pin-published` | The declared remote can serve the pin — `git fetch --dry-run --depth 1` from a scratch repository. Credentialless that probe is anonymous; with `--repo-credential` it authenticates through the staged askpass material (see the Colab environment block) and an SSH-shaped `--repo-url` refuses by name. `generate-job` refuses any SSH `--repo-url` before this probe, credential or not. Skipped, and only this condition, for a job that carries a code bundle (`--code-bundle`): its runner never clones. | `generate-job`, `submit` | The commit, the remote URL, the missing push addressed to `--repo-ref`, and git's own message |

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
     `--repo-url` (scp-shaped `git@host:o/r.git`, `ssh://`, `git+ssh://`,
     `ssh+git://`) is refused by `generate-job` before any git call, naming
     the rule and the `https://` alternative: the runner's clone has no SSH
     agent and no key, so no job generated from it could clone. `submit`
     still probes an older job folder's SSH remote like any other and, if
     it fails, the refusal says the probe was unauthenticated so the
     failure is not misread as a local accident. With
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
    A CALLABLE job is handed the same two names (remote-preflight F1),
    applied to the runner's own environment around the call and restored
    after it, whenever its run-config carries the pin, so a callable smoke
    on a code-bundle worker reads its commit from `FORGE_CLONE_COMMIT`
    exactly as a notebook does.
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

  **The kit's notebook bootstrap cell is recognised, nothing looser.** A
  notebook code cell byte-identical to `assets/notebook_repo_root.py`
  (exact text match against the shipped asset, never a heuristic) is
  blanked to the same number of empty lines before the notebook is
  parsed, so its `.git`/`HEAD`/loose and packed ref reads — the kit's own
  proof of the pinned commit — never become `unresolvedReads`, and every
  other cell keeps its line numbers. After that cell, the one
  `sys.path.insert(0, str(ROOT / "src"))` is not an uncertain import:
  `src/` is the clone's own source root. It stays uncertain when it sits
  before the cell, when anything in the notebook rebinds `ROOT`, or when
  the cell was edited by a single byte. Any other `sys.path` mutation and
  any other uncertain read is flagged exactly as before, so a kit notebook
  generates without `--accept-unresolved`/`--accept-unresolved-reads`
  while every other notebook still needs them.

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

`remote_cli.py` accepts exactly twelve top-level subcommands; this table is the
closed roster `skill-audit`'s `roster` move derives against, driving the CLI
with a nonce it cannot accept and reading the accepted set out of its own
refusal.

| Command | What it does |
| --- | --- |
| `submit` | submit one notebook to a registered backend's worker |
| `status` | report the fold for one product's ledger; resolves nothing |
| `distribute` | report how opaque work units would spread across every healthy worker account right now, with each worker's per-slot `shares`; issues no work and records nothing |
| `remaining` | report which declared units have no complete result yet (`complete`, `inFlight`, `unknown` with its `refetch` commands, `remaining`, in the declared order), the list the next campaign sends; asks no backend and records nothing |
| `poll` | ask the adapter for one submission's status |
| `fetch` | materialize one submission's result, quarantining it when it is not current; an incomplete result is kept under `partial/` and, when the run is over (`failed`/`unknown`), recorded `errored` naming it |
| `reconcile` | compare the ledger against the adapter's `list_active()` in both directions |
| `generate-job` | generate a forge-owned job folder at `<target>/tools/<service>/<job-name>/` |
| `generate-jobs` | generate every remote step's job folder in one call from the product's declared `__steps__` (and a `schedule` output), deriving service, run, clone paths, code bundle, requirements, carry paths and `--dataset` inputs; prints one row per job and the single `preflight` command to run next |
| `smoke` | smoke-run bookkeeping: recording a rehearsal's evidence-derived verdict |
| `readiness` | state whether a job is ready for a full submission on a worker, from that worker's own latest rehearsal; reports only, issues no submission |
| `preflight` | check a generated job locally before its first remote rehearsal, one `pass`/`warn`/`fail` row per check with its evidence and fix, including a local rehearsal of its smoke; exits non-zero on any `fail`, never submits |

## Refusal codes

Refusals that carry a stable code print it first in the message, so a caller
can branch on it without parsing prose.

| Code | Raised by | Meaning |
| --- | --- | --- |
| `DIAGRAM_NOT_VALIDATED` | `submit` (every mode) | the product holds an approval whose experiment diagram the operator has not validated |
| `CAMPAIGN_WORKERS_NOT_READY` | campaign `submit` (`--unit`, not `--smoke`) | a worker the distribution assigns units to has no passing rehearsal of its own at the current pin; the message names every such worker |
| `DUPLICATE_SUBMISSION_ID` | campaign `submit` | the backend answered two slots of one campaign with the same submission id; the repeat is not recorded |
| `LEDGER_EVENT_TOO_LARGE` | campaign `submit` | a slot's share of units would make its `submitted` event exceed the ledger's 4096-byte line; checked for every slot before the first submission, so nothing is sent |
| `CODE_BUNDLE_NOT_CARRIED` | `generate-job --code-bundle` | the service's adapter does not declare `CODE_BUNDLE_MAX_BYTES`, so it cannot ship a code bundle; refused before any git call |
| `CODE_BUNDLE_TOO_LARGE` | `generate-job --code-bundle` | the compressed bundle exceeds the service's `CODE_BUNDLE_MAX_BYTES`; the message names both sizes and nothing is written |
| `CODE_BUNDLE_UNSAFE_ENTRY` | `generate-job --code-bundle`, the runner | an archive entry is absolute, carries `..`, is a link or special file, or lies outside the declared clone paths |
| `CODE_BUNDLE_MISMATCH` | `submit`, the backend's push, the runner | the job folder's `code-bundle.tar.gz` is absent, does not hash to `codeBundle.sha256`, or (at `submit`) holds files that differ from the pin's; nothing is pushed or unpacked |
| `CODE_BUNDLE_WITH_REPO_CREDENTIAL` | `generate-job` | `--code-bundle` and `--repo-credential` were both given; a bundled job never clones, so the credential would be ignored. Refused before anything is read or written |
| `WORKSPACE_WITHOUT_DATASET` | `generate-job --workspace` | `--workspace` was given without `--dataset`; it only chooses which registry `--dataset` reads, so alone it would change nothing |
| `DATASET_UNKNOWN` | `generate-job --dataset`, `generate-jobs --dataset` | the slug is not in the workspace's `datasets/registry.json` |
| `DATASET_LICENSE_NOT_ALLOWED` | `generate-job --dataset`, `generate-jobs --dataset` | the dataset's license decision is missing or refused; run `/datasets license` first |
| `DATASET_NOT_PREPARED` | `generate-job --dataset`, `generate-jobs --dataset` | the dataset has no official preparation (`/datasets prepare`), so there is no sha256 to record |
| `DATASET_NOT_PUBLIC` | `generate-job --dataset`, `generate-jobs --dataset` | the dataset is published privately and its source names no public dataset page; the fix names `/datasets publish ... --public` with the operator's consent. Nothing is uploaded |
| `DATASET_NOT_PUBLISHED` | `generate-job --dataset`, `generate-jobs --dataset` | the dataset is not published and its source names no public dataset page a worker can attach; the fix names `/datasets publish` with the operator's consent. Nothing is uploaded |
| `DATASET_HOST_NOT_ATTACHABLE` | `generate-job --dataset`, `generate-jobs --dataset` | the dataset resolves to a host other than the one the service's adapter attaches from (`INPUT_DATASETS_HOST`) |
| `DATASETS_SKILL_MISSING` | `generate-job --dataset`, `generate-jobs --dataset` | the workspace has no `skills/datasets/scripts/datasets_cli.py` beside this skill, so the registry cannot be resolved; the fix names `smith upgrade` |
| `STEPS_UNREADABLE` | `generate-jobs` | the product's `src/<Package>/__init__.py` or `config.py` does not parse, or the `__steps__` it assigns is not a literal the reader can evaluate without running the target's code |
| `SCHEDULE_UNREADABLE` | `generate-jobs --from-schedule` | the file is not readable JSON, holds no `steps` list, or a step has no `id` or names no `services` |
| `SCHEDULE_IS_A_PLAN` | `generate-jobs --from-schedule` | the file is the schedule's input plan (it carries `schema` and no `makespanMinutes`), whose `services` are only the allowed ones; the fix names `parallelism_cli.py schedule --plan <file>` and passing its output instead |
| `CARRY_WORKER_MISMATCH` | campaign `submit` (a job declaring `--carry-path`) | a continuation unit's earlier output was produced on another worker than the one it is placed on; an earlier output carries only within its own account. The message names that worker and `--no-carry`; checked for every slot before the first submission, so nothing is sent |

## Before the first rehearsal

Run `preflight` on every generated job before the operator is asked to
authorize its first rehearsal, and again after any re-pin. It never submits;
it reaches a service only through the existing read-only probes (the
anonymous reachability probe `generate-job` already runs, the adapter's own
interpreter and account probes). A `--repo-credential` token is read only
through the generator's single read site, inside that probe, exactly as
`generate-job` reads it; preflight itself opens no credential file.

```
python3 scripts/remote_cli.py preflight --target <repo> \
    --entrypoint <repo>/tools/<service>/<job-name>/runner.ipynb \
    [--worker <id>]... [--expect-accelerator <name|sm_*>] \
    [--timing <Results/timing.json>] [--candidate <host>:<owner>/<machine>] \
    [--stage poc|full] [--units N] [--unit <id>]... [--deadline-block smoke|run] \
    [--local-smoke-kwargs '<json>'] [--local-timeout SECONDS] \
    [--skip-rehearsal] [--keep-rehearsal <new dir>] [--interpreter <python>] \
    [--repo-credential <token file>] [--workspace <workspace>]
```

`--entrypoint` is repeatable: given more than one (the command
`generate-jobs` prints), it prints `{jobs: [one report per job], summary}`
with the summed counts and one `ok`; given one, the report below, unchanged.
`--workspace` names the workspace whose env interpreter, dataset registry,
team registry and account credentials are checked (default: the workspace
this skill is installed in), so a CLI run from another checkout checks the
accounts that workspace actually holds.

It prints one JSON object: `checks`, one row per check as
`{check, status, evidence, fix}` (`status` is `pass`, `warn` or `fail`; an
`account` row also carries `worker`, the rehearsal row `details` with its
duration), and `summary` with the counts and `ok`. It exits 0 only when no
row fails. Run it under the workspace env interpreter, the one `submit` uses.

| Check | Fails (or warns) when | Fix it names |
| --- | --- | --- |
| `pin` | the job's clone paths moved since its pin (`staleness` not `fresh`) | commit, then `generate-job --regenerate` |
| `diagrams` | an approval (`AGREED.md`, `Experimental_AGREED.md`) owes an experiment diagram that is not `validated`; `submit` would refuse `DIAGRAM_NOT_VALIDATED` | the dashboard's "Validar diagrama", or `diagram_cli.py validate` on the operator's explicit approval in the chat |
| `interpreter` | the service's driver is not usable under the interpreter running this command | the workspace env interpreter, `<workspace>/.micromamba/envs/papersmith/bin/python`, when it exists |
| `code-reachability` | the job carries no code bundle and the runner could not clone the pin anonymously (nor with `--repo-credential` on a service that carries one) | `--repo-credential` on a carrier; `generate-job --code-bundle --regenerate` on a service that ships bundles |
| `inputs` | warns: a service that attaches inputs, a job declaring no `--input-dataset`, and a workspace `datasets/registry.json` naming a remote source | `generate-job --dataset <slug> --regenerate`, or `--input-dataset <owner>/<slug>` |
| `local-rehearsal` | the job's smoke, run locally under runner conditions, raises, overruns `--local-timeout`, leaves no `shard.json`, or leaves one missing a `requiredEvidence` path | the target's smoke stamps (`remote_stamp.write_shard`, `@remote_stamp.stamped`); `--local-smoke-kwargs` for a cheaper local scale |
| `account` | fails when the worker's account does not authenticate or is not signed in; warns when it has no passing rehearsal of its own at this pin | validate or sign in the account; `submit --smoke --worker <id>` once authorized |
| `accelerator` | fails when the machine the job will request is not the one `--expect-accelerator` names, or lacks the job's declared architecture; warns when it is the service default and no expectation was given, saying the GPU is a default, not a measured choice; passes a CPU-only job (`--accelerator-kind cpu`) and says so | compare candidates with `remote-parallelism plan`, then regenerate with `--accelerator-kind cpu` or `--accelerator-kind`/`--accelerator-architecture`, or confirm with `--expect-accelerator` |
| `deadline-rehearsal` | present only for a job that declares carry paths or whose unit or whole-session estimate exceeds the usable session. Fails when the job's smoke (or `--deadline-block run`), run locally under a deadline that has already arrived, overruns `--local-timeout`, raises, leaves no `partial.json`, leaves one whose ids are not among the `--unit` ids, leaves it inside a carry path, leaves none of its declared carry paths, or when the second session, handed only the remaining ids with those paths restored, does not finish them; warns when skipped (`--skip-rehearsal`, no `--unit`, or a failed local rehearsal) | read `FORGE_SESSION_DEADLINE` before each unit, epoch or trial, checkpoint into a carry path, write `partial.json` with the `FORGE_RUN_UNITS` ids and exit 0; `--unit <id>` per unit |
| `session-fit` | fails when one unit's upper-bound estimate (the timing record's measurements on this service; on a schema 2 record, the `--candidate` named, or else the slowest candidate of this service on the job's own kind of machine, CPU-only or accelerator, at its fastest measured setting) exceeds the usable session (`remote-parallelism`'s 80% margin) and the job declares no carry paths, or declares them and the deadline rehearsal failed; warns when the deadline rehearsal was skipped (quoting why), when it ran but never stopped early (quoting its evidence), and when unmeasured. Declared carry paths alone never pass a unit that spans sessions | more units, or `generate-job --carry-path` and a passing deadline rehearsal |

The local rehearsal materializes the job's code with the runner's own
functions in a fresh scratch directory outside the target: unpacked from
`code-bundle.tar.gz` when the job carries one (so only `.git/HEAD`, never git
history), sparse-cloned at the pin from the target otherwise. It runs the
smoke block through the runner's own `invoke()` with `mode` `smoke`, under the
target's `.venv` interpreter (`--interpreter` overrides it). The child
inherits only `PATH`, `HOME`, `LANG`, `LC_ALL`, `TMPDIR` and `SYSTEMROOT`
(those set here), and gets the clone's `src` on `PYTHONPATH`,
`FORGE_CLONE_ROOT`, `FORGE_CLONE_COMMIT` and what `invoke()` exports itself
(`FORGE_RUN_MODE`, `FORGE_INPUT_DATASETS` with every declared input
unattached, `FORGE_SESSION_DEADLINE`). The `shard.json` it leaves is judged by
the same `shard_io.completeness()` `smoke record` uses. The scratch directory
is removed afterwards, passing or failing, and an unexpected error during the
rehearsal is a `fail` row carrying the error, never a traceback.
`--keep-rehearsal <new dir>` keeps the scratch directory there to read; the
path must not exist yet and must lie outside the target, and either refusal
happens before anything is written.

**The deadline rehearsal** (`deadline_rehearse()` in
`scripts/local_rehearsal.py`) proves, before any remote hour, that a chain of
sessions resumes. It runs in its own scratch directory outside the target
(`<--keep-rehearsal>/deadline/` when kept), with the same runner functions,
interpreter and environment as the local rehearsal, two sessions in a row:

1. Session 1 gets the `--unit` ids as `FORGE_RUN_UNITS` and a session limit
   whose `FORGE_SESSION_DEADLINE`, by the runner's own formula, arrives one
   second after the runner starts. It must exit 0, leave a `partial.json`
   (`{"remaining": [<unit id strings>]}`, read by `shard_io.partial_marker`
   exactly as `remaining` reads it) whose ids are among the `--unit` ids and
   which lies outside every carry path, and leave at least one declared
   carry path where `restore_carry()` looks (`clone/<product>/<path>` or
   `<path>`).
2. Session 2 gets only the remaining ids, a `carry` row whose mount is
   session 1's directory (restored by the runner's own `restore_carry()`),
   and the service's own limit; it must exit 0 and leave no `partial.json`.

Each session has `--local-timeout` seconds. The rehearsal needs the unit ids
the job's `submit --unit` will send, because a marker's ids must equal the
submitted unit strings: `remaining` and the carry evidence intersect them
with each `submitted` event's `units`, and a `submit` without `--unit`
records no share at all, so a run cut at its limit is never listed as
remaining. `FORGE_RUN_MODE` is set only for a smoke (`run_config["mode"]`),
so a target must write `partial.json` whatever that variable says.

The rehearsal is not a sandbox. It runs the target's smoke on this machine
with the real `HOME`, so a smoke that downloads reaches the network and
writes its caches (under `HOME`) exactly as it would anywhere else; what it
withholds is the workspace, not the network.

Every rule below was learned from a remote round that a local check would
have saved:

1. Validate every approved experiment diagram before generating the jobs:
   `submit --smoke` refuses `DIAGRAM_NOT_VALIDATED` only at launch.
2. Run `remote_cli` under the workspace env interpreter. A system interpreter
   without the pinned service driver refuses at `submit`, and the driver's
   refusal names that interpreter (never a `pip install --user` into
   whichever one ran it).
3. A private repository needs a way in: a repository credential on a service
   that carries one, the code bundle on a service that ships bundles. A
   bundled worker has only `.git/HEAD`.
4. A job on a service whose non-interactive sessions cannot download a dataset
   declares every public dataset it reads with `--input-dataset`; the target
   still downloads when `FORGE_INPUT_DATASETS` maps it to null.
5. The smoke writes `shard.json` into its working directory carrying every
   `--smoke-required-evidence` path, including a smoke that only measures
   timing.
6. Read the commit with `git rev-parse HEAD`, falling back to
   `FORGE_CLONE_COMMIT` when git cannot answer (a code-bundle worker); the
   scaffold's `remote_stamp.py` does.
7. Register each person's own account and take its credential in before any
   rehearsal; every account needs its own rehearsal at the current pin.
8. Name the accelerator the plan expects (`--expect-accelerator`) and generate
   with `--accelerator-*` when it is not the service default, or with
   `--accelerator-kind cpu` when `remote-parallelism plan` recommends a
   CPU-only session; the service's GPU default is never the measured choice.
9. The workspace's `datasets/` folder is not in the target: a remote run
   reaches its data through a declared input or a download the target checks
   by sha256, never through a workspace path. `generate-job --dataset <slug>`
   declares it from the registry and records the preparation's sha256 values
   (`FORGE_DATASET_CHECKS`).
10. Several remote steps: `generate-jobs` writes every job in one call (code
    bundle, requirements, carry paths and inputs derived), then run the one
    `preflight` it prints.
11. Every fix after a rehearsal moves the pin, which means regenerated jobs and
    re-minted consent tokens: fix what `preflight` reports first.
12. A run longer than one session rehearses its deadline here first:
    `preflight --unit <id> ...` with the job's own unit ids. A target that
    ignores `FORGE_SESSION_DEADLINE`, writes no `partial.json`, writes ids that
    are not its units, or checkpoints outside its carry paths loses the
    session's hours remotely and is caught here in seconds.

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

**The smoke writes the stamp; nothing else does.** The runner never
writes `shard.json`: the target's smoke does, into its own working
directory, which is the folder `fetch --smoke` returns. A callable smoke
runs with `FORGE_RUN_MODE` set (the runner exports it around the call),
so writing the stamp only when that variable is present keeps local runs
clean. Put in it what proves the rehearsal ran the code you think on the
hardware you think — typically the commit (`git rev-parse HEAD` of the
clone), a digest of the sources, and the device kind and name — and
declare those paths with `--smoke-required-evidence`. `generate-job`
reports a `warnings` entry when a smoke block declares none, because
`completeness(stamp, [])` passes on any JSON at all. `smoke record
--from-artifact` takes either the `shard.json` itself or the fetched
rehearsal folder, and a folder with no stamp is refused with what the
smoke must write.

**Readiness, and no clock.** `remote_cli.py readiness --job-dir <dir>
--worker <worker>` reports whether a job is ready for its full submission
on that worker — issues no submission, offers no menu, the same
"reports and resolves nothing" discipline `status` already holds
structurally (no `adapter` parameter in either signature). It binds three
facts on the LATEST `smokeResult` record for this job ON THIS WORKER
(append order, last line wins): `result == "pass"`, `commit` equal to the
job's CURRENT pinned commit, `worker` equal to the worker asked about.
Readiness is per worker: a later rehearsal on another account never
revokes this one's, so several accounts can be ready for one campaign at
once — which campaign `submit` requires (`CAMPAIGN_WORKERS_NOT_READY`).
`latest_smoke_event(path, job)` without a worker still returns the job's
latest record on any worker. Nothing here
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
| `submitted` | `ts`, `entrypoint`, `sourceDigest`, `submissionId`, `worker`, `requestedCapacity`, `grantedCapacity`, `slot` only for a campaign's slot 2 and up on one worker, `units` (that submission's share) only for a campaign submission, and `carriedFrom` (`[{"submissionId", "ref"}]`, the earlier submissions whose output it was handed) only for a continuation that carried one |
| `returned` | `ts`, `submissionId`, `artifactPath`, `observedConcurrency` |
| `errored` | `ts`, `submissionId`, `reason` (truncated to 512 chars), and, when `fetch` recorded a run that ended without a complete result, `artifactPath` (where its bytes are kept, never a results tree) and `runState` (`failed` or `unknown`) |

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
uv tool install --force --python 3.14 "google-colab-cli==0.6.0" --with "jupyter-kernel-client<1"
```

The pin is not decorative: `google-colab-cli` 0.6.0 with
`jupyter-kernel-client` 1.x crashes every `exec` (`AttributeError: module
'jupyter_kernel_client' has no attribute 'KernelClient'`; upstream #94), so
the working combination is 0.6.0 with the 0.x client that a bare dependency
resolution does not pick. The adapter shells out to `colab` on `PATH` by
default; a non-default location can be supplied as `colab_executable` when
constructing `ColabAdapter` directly.

`google-colab-cli` 0.7.5 is **untested live** and the pin stays at 0.6.0.
Read from 0.7.5's own `--help` and installed source (never authenticated):
it depends on `jupyter-kernel-client==0.9.0` and resolves either kernel
client class name, so #94 looks fixed there; the `sessions` line gained a
`Shape:` field, which the adapter's line parser still reads; `new`,
`exec`, `upload`, `download`, `install`, `status` and `stop` keep the flags
the adapter passes. But 0.7.5 no longer ships the hidden `keep-alive`
command the adapter spawns (0.6.0 does), so on 0.7.5 that best-effort
keep-alive would silently do nothing and a long run could be idle-reclaimed.
Moving the pin waits for a live rehearsal that settles that.

Authentication is the CLI's own oauth2 copy-paste ritual, and the adapter
never reads the token file the CLI writes: the CLI's own child process
resolves it from the `HOME` the adapter forwards, and no module above the
seam learns a path to it. Measured in the CLI's source (0.6.0 and 0.7.5
alike): the token lives at `~/.config/colab-cli/token.json`, resolved from
`HOME` when the CLI starts, and the global `--config PATH` flag names the
session state FILE (`sessions.json`) only — it never moves the token. No
OAuth client file is needed: the CLI ships Google's public installed-app
client (`colab_cli/oauth_config.json`) and uses it whenever
`~/.colab-cli-oauth-config.json` does not exist; its copy-paste redirect
is registered to that client, so substituting your own client would break
the flow (`redirect_uri_mismatch`, per the CLI's own `auth.py`).

**Team accounts: one worker per owner.** When
`<workspace>/.papersmith/team.json` declares Colab accounts, the adapter
exposes one worker per owner, `colab:<owner>`, and runs every child for
that worker with `HOME=<configDir>` (the owner's own state directory)
plus `--config <configDir>/.config/colab-cli/sessions.json` — still only
`PATH` and `HOME` are forwarded. It reads three fields per member
(`owner`, `accounts.colab.tier`, `accounts.colab.configDir`), checks that
the directory exists with mode 0700, and never opens anything inside it.
It refuses a registry that is not schema 1, an owner listed twice, an
unknown tier, a relative `configDir`, and the same `configDir` under two
owners. With no registry (or one declaring no Colab account) the single
`colab` worker on the operator's own `HOME` is unchanged. Each owner signs
in once, on their own Google account, in a terminal:

```
mkdir -p -m 700 ~/.config/papersmith/colab/<owner>
HOME=~/.config/papersmith/colab/<owner> colab \
  --config ~/.config/papersmith/colab/<owner>/.config/colab-cli/sessions.json sessions
```

The CLI prints an authorization URL; the owner opens it, approves, and
pastes back the code Google shows. `--auth adc` (Application Default
Credentials) also resolves from `HOME`, so it isolates per owner the same
way.

The team rule, enforced at the adapter: one account per person, and a
`free` account is never a worker of a split campaign. The Colab FAQ
(https://research.google.com/colaboratory/faq.html, verified 2026-10-25)
disallows "using multiple accounts to work around access or resource usage
restrictions" on every managed runtime and, on free runtimes without a
positive compute-unit balance, "running distributed computing workers". So
a submission carrying campaign `units` on a free worker refuses by name,
citing that rule, before any CLI call; a single send (interactive work or
a proof-of-concept pilot) on a free worker is allowed; a campaign whose
units land on `pro`, `payg` or `enterprise` workers is allowed.
`workers()` lists free accounts first, so a campaign that would place a
unit on one refuses at its first assignment, before any paid account has
launched. `ColabAdapter.campaign_refusal(worker)` returns that reason (or
`None`) without a subprocess, for a planner that wants to exclude rather
than refuse. The declared capacity counts distinct owners on paid tiers.

GPU variants by tier: `colab new --gpu` accepts `T4`, `L4`, `G4`, `A100`
and `H100` (0.7.5 help). Expect `T4` on a free account and `L4`, `A100`
or `H100` on paid compute; the FAQ itself names no models — free access to
GPUs "is heavily restricted", premium GPUs come with a paid plan "subject
to availability", and the types "vary over time". The adapter maps only
`sm_75 → T4`, `sm_80 → A100`, `sm_90 → H100` (`COLAB_ACCELERATOR_VARIANTS`).

**A Colab job asks for a GPU by default.** The adapter registers its own
default accelerator, `cuda` with `sm_75` (`COLAB_ACCELERATOR_KIND`,
`COLAB_ACCELERATOR_ARCHITECTURES`), the same way the Kaggle adapter does, so
`generate-job` with no `--accelerator-*` flags writes that block and `submit`
passes `--gpu T4`. Before this, a from-zero Colab job carried no block, got no
`--gpu`, and ran on a CPU runtime without a word. Because the block is
declared, the VM-side `check_accelerator()` refuses a runtime that arrives
without CUDA (its arch list is empty), so the smoke fails and `readiness` stays
`false` instead of counting a CPU rehearsal as ready. Pass
`--accelerator-kind cuda --accelerator-architecture sm_80` (or `sm_90`) to ask
a paid account for an A100 (or H100).

**CPU-only jobs.** The GPU default stays for compatibility, and it is a
default, not a measured choice: `remote-parallelism plan` decides from the
timing record whether a CPU-only session, a GPU, or the local machine runs a
stage. When it recommends a CPU-only remote session, `generate-job
--accelerator-kind cpu` (no `--accelerator-architecture`) writes the block
`{"kind": "cpu", "architectures": []}`: Colab's `new` then gets no `--gpu`, and
Kaggle's `kernel-metadata.json` carries `enable_gpu: false` and no
`machine_shape`, which `submit` leaves as read. A service whose adapter does
not declare a CPU-only session (`ADAPTER.register_cpu_only`) refuses the flag
at generation, naming the service. A generation without the flag writes
byte-identical files.

Sessions are expensive and idle-reclaimed, so release is part of the flow,
not housekeeping: `fetch` stops a session only AFTER the manifest has
landed AND the run is terminal; the adapter spawns the CLI's own keep-alive
(best-effort) to hold a session through a long run; a released or expired
session is simply gone, and the operator's own `colab stop -s <name>` is
the manual exit. When you are done with a session, stop it — an abandoned
one burns the account's capacity until the service reclaims it.

**Fetch as soon as the run is terminal.** The keep-alive holds a session
through the run, not after it: once the executor exits, the session idles
and the service reclaims it, taking every result with it (`poll` then
answers `unknown`, `session not found`). Whoever waits on a Colab run fetches
in the same loop that sees `complete`, never later.

What of this rule the code holds, and what it does not: releasing the session
after completion is verified in code, since `fetch` stops it only after every
manifest file is local and only when `status.json` exists
(`test_colab_fetch_stops_session_only_after_terminal_status`, and the
round-trip test's download-before-stop order). Unverified: nothing fetches on
its own when a run turns terminal, so a prompt fetch rests on whoever polls,
and the delay after which the service reclaims an idle session was never
measured.

**The manifest is kept current during the run.** The executor rewrites
`files.json` every `MANIFEST_REFRESH_SECONDS` (60 s) while the notebook
executes, atomically (`files.json.tmp`, then a rename), so a fetch of a
session still running, or one whose process died before `status.json`,
downloads every file already written and reports it `complete=False`.
Fetching periodically during a long run is what saves a reclaimed one:
each such fetch keeps a snapshot under `partial/`, and a later fetch that
finds the session gone records the last snapshot (see "Sessions,
checkpoints and resume").

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
Credential or not, `generate-job` refuses an SSH `--repo-url` (the
runner cannot clone over SSH): declare `https://`, or a local path for a
local rehearsal. A credential is never embedded in `--repo-url` itself: a URL carrying a
user, password or token before `@` (a bare SSH login such as
`git@host:o/r.git` excepted) is refused before any git call or write, and
a job folder whose `run-config.json` carries one is refused on every read,
without the refusal echoing the URL.

**Private repositories without a credential: `generate-job --code-bundle`.**
A service whose runner cannot be handed a repository credential at all ships
the code instead: its adapter class declares the optional capability
`CODE_BUNDLE_MAX_BYTES` (the Kaggle adapter does, 786,432 bytes — a
conservative bound, since the service documents no size limit for a pushed
notebook's source; 768 KiB of gzip is about 1 MiB of base64 in the cell).
With `--code-bundle`, generation takes the declared clone paths (plus the
run/smoke notebook) from the pinned COMMIT with `git archive` — never the
working tree, so an untracked or ignored file such as a token never enters
it — gzips them with a fixed mtime (the same pin always yields the same
bytes), writes `code-bundle.tar.gz` beside `run-config.json` and records
`codeBundle: {file, format, sha256, bytes}` there. The remote is never asked:
no published-tip default and no `pin-published` probe, while every local
condition (clean worktree, pin is HEAD, declared paths exist) still refuses
as always; no credential is read, and `--repo-credential` together with
`--code-bundle` refuses `CODE_BUNDLE_WITH_REPO_CREDENTIAL` before anything is
read or written. `submit` checks the file against the recorded sha256 and
rebuilds the bundle from the pin, comparing their files, before anything is
uploaded; the backend writes its bytes into the pushed notebook, and the
runner verifies the sha256 again and unpacks into the same clone directory
instead of cloning, refusing an entry that is absolute, carries `..`, lies
inside a `.git` directory, is a link or special file, or lies outside the
declared clone paths. It then writes `<clone>/.git/HEAD` holding the pinned
commit, the shape a detached clone leaves, so a notebook's repository-root
cell proves the root at `FORGE_CLONE_COMMIT` exactly as for a clone (and
still refuses any other commit). `bootstrap.json` and the run record the same
pinned `commit` as a cloned job, so smoke and readiness verdicts read identically,
and the job goes stale exactly when a cloned one would (a clone path changed
after the pin). Without `--code-bundle` nothing changes. A bundle honors the
commit's own `.gitattributes` `export-ignore`/`export-subst` under a clone
path. Refusals: `CODE_BUNDLE_NOT_CARRIED`, `CODE_BUNDLE_TOO_LARGE`,
`CODE_BUNDLE_UNSAFE_ENTRY`, `CODE_BUNDLE_MISMATCH`,
`CODE_BUNDLE_WITH_REPO_CREDENTIAL` (see "Refusal codes").

A second backend brings its own answer to this section: nothing above the
adapter seam knows a service exists, so nothing above it knows what a service
needs.

## The session-chain rule

Every service stops a session after a continuous run time it publishes, and
some also reclaim a session they judge idle. Whatever the session had not
written out by then is lost, together with the hours it cost. A run longer
than one session is therefore planned, checked and executed as a chain of
sessions that checkpoint and resume. The rule, for every agent that plans,
builds or launches a remote run:

1. **Estimate against the session margin.** Compare the stage's upper-bound
   estimate (`remote-parallelism` `estimate` and `plan` over
   `Results/timing.json`) with 80% of the account's session limit, per unit
   and for the whole session. A unit (a fold, a seed, a trial batch) that
   fits is one session. One that does not is split along the declared axis
   (never by arm) or declared resumable and planned as a chain of sessions
   on the same account, each paying the setup again (`plan --resumable
   --checkpoint-minutes`, `"resumable": true` in a `schedule` plan). Never
   plan a unit that only finishes if the session is never interrupted.
2. **Checkpoint every epoch or trial** into a path the job declares with
   `generate-job --carry-path`, relative to the product folder; under the
   runner the target writes it at `clone/<product>/<path>` below
   `FORGE_CLONE_ROOT`.
3. **Stop at the deadline.** Read `FORGE_SESSION_DEADLINE` (epoch seconds)
   before starting each unit, epoch or trial; when the next one may not
   finish before it, write the checkpoint and the results so far, write
   `partial.json` in the working directory as `{"remaining": [<unit ids>]}`
   naming the units it did not finish, and exit 0. The ids are strings equal
   to the units it was sent, read from `FORGE_RUN_UNITS`: `remaining` and
   the carry evidence intersect them with the submitted share, so any other
   id is dropped. A `partial.json` without that list means none of the
   share's units is finished. Write the marker whatever `FORGE_RUN_MODE`
   says: the runner sets that variable only for a smoke.
4. **Send a chain as a campaign**, `submit --unit <id>` per unit. A plain
   `submit` records no share, so a session cut at its limit is never listed
   as remaining; `submit` reports `carry: no-share` and a `carryWarning`.
5. **Rehearse the deadline before the first remote rehearsal.** `preflight
   --unit <id> ...` runs the `deadline-rehearsal` row (see "Before the first rehearsal"):
   locally, under a deadline that has already arrived, the job must stop with
   a valid `partial.json` and its carry paths, and a second session handed
   only the remaining ids, with those paths restored, must finish them.
   `session-fit` fails when it fails and warns when it was skipped; declared
   carry paths alone never pass a unit that spans sessions.
6. **Fetch promptly, then resubmit only the remaining units.** Fetch as soon
   as a run is terminal, and periodically during a long one, so a reclaimed
   session still leaves its last snapshot on this side. `remaining` names the
   units left; pass its list unchanged to `distribute` and then `submit`,
   which carries the declared paths to the continuation on the same account
   (`carry: attached`, `carry: uploaded`, or `carry: unsupported`; see
   below).
7. **Count quota weeks.** An account whose assigned hours exceed its weekly
   quota waits for the reset: `remote-parallelism` `schedule` and `plan` put
   the wait in the makespan and report `quotaWeeks`, and a chain waits on its
   own account rather than moving to one that cannot read its checkpoints.

## Sessions, checkpoints and resume

How each part of the session-chain rule above is carried out.

**Declared limits.** Each adapter declares its service's limit through
`Adapter.session_limit_seconds(machine_shape=None)` -- a classmethod, not a
seventh abstract operation, whose default is `None` (unknown). Kaggle:
`KAGGLE_SESSION_LIMIT_SECONDS`, 12 h for a GPU session. Colab:
`COLAB_PRO_SESSION_LIMIT_SECONDS`, 24 h for a Pro session, with idle reclaim
possibly much earlier. Both are the services' published limits at the time
of writing and must be re-checked against their documentation before a plan
leans on them.

**The deadline.** For a job folder, `submit` copies the declared limit into
the job's `run_config["sessionLimitSeconds"]` (nothing at all when the
adapter declares none, so such a job is unchanged), and the runner
(`assets/runner_invoke.py`) exports, to a callable and to a notebook kernel
alike,

    FORGE_SESSION_DEADLINE = session start + limit - max(10% of limit, 30 min)

in epoch seconds (`SESSION_MARGIN_FRACTION`, `SESSION_MARGIN_MIN_SECONDS`).
The margin covers the setup before the runner's cell, the checkpoint write
and the upload of the outputs. A target uses it like this:

```python
import json, os, time
from pathlib import Path

deadline = float(os.environ.get("FORGE_SESSION_DEADLINE", "inf"))
for index, unit in enumerate(units_to_run):    # skip the ones already done
    if time.time() + estimated_seconds(unit) > deadline:
        save_checkpoint()                      # what a new session resumes from
        unfinished = units_to_run[index:]      # this unit and every one after it
        Path("partial.json").write_text(json.dumps({"remaining": unfinished}))
        break                                  # exit 0: the outputs still come back
    run_and_record(unit)                       # one runs.jsonl record per unit
```

**Honest states.** A fetch that comes back without a complete result never
records `returned`. Its bytes are moved out of `.partial/` into
`<target>/<Name>/.remote-execution/partial/<submissionId>/<UTC stamp>/` --
kept, never overwritten, never deleted, and never offered a results path.
The run's own state (`poll`) decides the rest: `failed` (a Kaggle `ERROR`,
which includes a session that hit its limit) or `unknown` (a session the
service no longer reports, as after a reclaim) appends an `errored` event
naming the kept path (`artifactPath`, `runState`); a run still going appends
nothing, and the ledger stays `pending`. When the backend cannot reach the
run at all and an earlier fetch kept a snapshot, the snapshot is what gets
recorded. Kaggle's `fetch` reads the session status before the output
listing and reports `complete=False` for anything but `COMPLETE`. The
ordinary incomplete path therefore never leaves a `.partial/` behind; one
left by a killed fetch still refuses, naming the command that clears it.

**Remaining units.** Every campaign `submitted` event records its share
(`units`). `remaining --target <t> --entrypoint <e> --unit <u> ...` pairs
each submission with the terminal event that settled it, in append order
(so an id the service reused for a later resubmission never erases what an
earlier one returned), and counts a unit complete when a submission at the
current source digest carrying it was `returned` -- with two exceptions. A
result `fetch` sent to `.remote-execution/quarantine/` (a
`fromStaleSubmission` verdict) completes nothing. A returned result holding
a `partial.json` (the run stopped early and exited 0) completes only the
units of its share that the marker's `remaining` list does not name; a
marker without that list, or one that does not parse, completes none. With
`--unit-field <dotted.path>` -- the field of the target's `runs.jsonl`
records that names a unit -- the per-unit records inside a kept partial
result, or inside a returned one with a `partial.json`, count too: a unit
with its own record is complete even when a marker lists it. A returned
result whose recorded `artifactPath` is no longer a directory on disk
completes nothing: its units are reported as `unknown` and stay in
`remaining`, and `refetch` names, per submission, the exact `remote_cli
fetch ... --dest <artifactPath> --backend <service>` that brings it back
(run it before resending them, or you pay for those hours again); it is
never continuation evidence either. Units of a submission still unsettled are reported as
`inFlight` and are not resent. `remaining` keeps the declared order, which is
the order the consent token binds, so its list goes to `distribute` and
`submit` unchanged (`unitArgs` spells it as `--unit` flags).

**Carry-over, automatic for declared paths.** A job declares what a
continuation needs with `generate-job --carry-path <path>` (repeatable;
relative to the product folder, e.g. `Results/e1/runs`,
`Results/checkpoints`, `hpo/studies`), recorded as `carryPaths` in
`run-config.json`. A job that declares none behaves exactly as before. For
one that does, a campaign `submit` finds, for each unit it sends, the
earlier submission of the same entrypoint that left it to be continued --
the evidence `remaining` reads: a settled submission at the current source
digest whose returned result holds a `partial.json` listing it (or listing
nothing), or whose `errored` event names bytes kept under
`.remote-execution/partial/`. Then:

1. **Same account only.** `distribute` (and `submit`, which distributes the
   same way) places such a unit on the worker that produced its earlier
   output when that worker is in the pool; when that worker has no place
   left the unit stays `unplaced` for a later campaign. A unit whose worker
   is not in the pool refuses `CARRY_WORKER_MISMATCH`, naming that worker;
   `submit --no-carry` starts it fresh instead (`carry: fresh`). Carrying a
   private kernel's output across two accounts was never verified.
2. **Automatic attach.** The share's job gets `run_config["carry"]`, one
   `{"submissionId", "ref", "mount"}` row per earlier submission, from the
   adapter's optional `carry_source(submission_id)` (not a seventh abstract
   operation). Kaggle answers the submission id itself as the kernel ref
   and adds it to the pushed `kernel-metadata.json`'s `kernel_sources`, so
   the earlier kernel's output is mounted at
   `/kaggle/input/notebooks/<owner>/<slug>/` (verified on a live account on
   2026-10-27). The `submitted` event records `carriedFrom`, and the
   submission's row in `submit`'s output reports `carry: attached` with the
   same `carriedFrom`.
3. **Restore before the entrypoint.** The runner (`restore_carry()` in
   `assets/runner_invoke.py`) copies each declared carry path from each
   mount back to where the earlier session wrote it, before the callable or
   notebook starts, so the target resumes from the checkpoints already on
   disk with no code of its own. A mount mirrors the earlier session's
   working directory (the folder whose files come back), and a declared
   path is looked up there in two layouts, each restored in place: the
   product layout `clone/<product>/<path>`, which is where a target that
   binds its root to `FORGE_CLONE_ROOT` (`<cwd>/clone`) writes its product
   folder, restored to `<cwd>/clone/<product>/<path>`; and the working
   layout `<path>`, where a job writing relative to its working directory
   (every job before the product layout) left it, restored
   into the working directory. Both are restored when both exist; nothing is moved between
   them, nothing outside a declared path is copied, and the mount is only
   read. `<product>` is `run-config.json`'s `product`, joined only when it
   is one folder name. A symbolic link in the mount is never followed: a
   declared path that is one, or sits under one, is skipped (`[carry]
   skipped carry path <path> from <ref>: <link> is a symbolic link in the
   mount; it is never followed`), and a link inside a carried tree is not
   copied. A file is written only where its resolved destination stays
   inside the working directory, so a link already in the clone never
   carries a write out of it (`its destination resolves outside the working
   directory`). Each restore is one `[carry] restored <path> from
   <ref> into <where>` line in the run log. The runner then exports the
   present mounts as `FORGE_CARRY_IN` (joined with `os.pathsep`). A missing
   mount or path is one `[carry]` line in the run log, and the unit starts
   fresh; it is never fatal.
4. **Services without kernel inputs upload the fetched output.** A backend
   whose jobs cannot mount another job's output, but which can put local
   files into the session it starts, declares the optional class attribute
   `CARRY_UPLOAD` (not a seventh operation). Colab does: its CLI's `upload`
   writes one local file into a running session (a contents-API `PUT`; the
   parent directory must exist). For such a backend the share's job gets
   one `{"submissionId", "ref", "upload"}` row per earlier submission,
   `upload` naming the local directory `fetch` left (the returned result
   holding the `partial.json`, or the kept bytes under
   `.remote-execution/partial/`); the row reports `carry: uploaded` and
   `carriedFrom` as above, and the ledger never records the local path.
   Before the launch, the Colab adapter creates
   `<root>/<session>.carry/<k>/` (beside the session directory, so the
   manifest never fetches carried inputs back), uploads every regular file
   under a declared carry path in either layout (`clone/<product>/<path>`
   and `<path>`) and nothing else -- a declared path the runner would
   refuse (empty, `.`, absolute, `..`) is skipped, so no row uploads the
   whole fetched output -- and hands the runner the same row with
   `mount` in place of `upload`, which `restore_carry()` reads as above. A
   source that is not a directory refuses before any CLI call; a failed
   upload stops the session before the launch. A backend that can neither
   mount nor upload reports `carry: unsupported` and carries nothing;
   upload the checkpoint into the new session yourself.

A single send (no `--unit`) and the legacy shape carry nothing. A single
send of a job that declares carry paths is still sent, but its output
reports `carry: no-share` and a `carryWarning`: it records no share, so if
its session is cut at the limit `remaining` lists none of its units and no
continuation carries its checkpoints. Send a chain as `submit --unit <id>`.

**No push replaces an output a continuation reads.** `submit` hands every
job of a job declaring carry paths -- every share of a campaign, a single
send, a rehearsal -- `run_config["carryProtected"]`: the ref of every
submission whose output a unit still waits to continue from, read from the
main ledger whether or not this invocation sends that unit. Kaggle never
pushes to a protected ref, nor to one the job itself carries from: the push
goes to the first alternate kernel not protected, deterministically
`<slug>-carry`, then `<slug>-carry-2`, ... (`CARRY_ALTERNATE_SUFFIX`,
`kernel_ref()` in `adapters/kaggle.py`). So a fresh share never overwrites
the kernel another share of its campaign mounts, two continuations never
push each other's source, a later fresh-only campaign leaves a pending
continuation's source intact, and a kernel never names itself in
`kernel_sources` (never verified live). A carry path that names the product
folder itself (`.`) is refused like one that escapes it.

**No push replaces a kernel still running.** The protected set also holds
the ref of every submission of the same entrypoint that is still in flight
(submitted, never settled) in the main ledger -- and in `smoke.jsonl` for a
rehearsal -- at any source digest, for every job folder, including one that
declares no carry paths. A second campaign started while the first still
runs therefore goes to `<slug>-carry` (or the next free alternate) instead
of re-pushing the running kernel. When nothing is in flight and nothing is
pending, no `carryProtected` key is written and the job is byte-identical
to before; when something is, that key is the only addition. The legacy
shape (no job folder) is unchanged.

## Every job at once

`generate-jobs` generates one job folder per remote step a product declares,
in one call, deriving each from what the target and the workspace already say
(remote-preflight S3). The single `generate-job` is unchanged.

```
python3 scripts/remote_cli.py generate-jobs --target <repo> --product <Name> \
    [--from-schedule <schedule output.json>] [--dataset <slug>]... \
    [--smoke-module M --smoke-function F] [--smoke-kwargs '<json>'] \
    [--smoke-required-evidence <path>]... [--repo-url URL] [--repo-ref REF] \
    [--repo-credential <token file>] [--regenerate] [--workspace <dir>] \
    [--accept-unresolved] [--accept-unresolved-reads] [--accept-produced-reads]
```

The three `--accept-*` flags mean what they mean for `generate-job`, applied to
every job, so a refusal relayed in a job's row names a flag this command takes.

- **Steps**: every `__steps__` entry (`src/<Package>/__init__.py`, else
  `config.py`, read with `ast`) with `placement: "remote"`; other steps are
  listed under `skipped`.
- **Service and job folder**: the step's `service` and `job`. With
  `--from-schedule` (a remote-parallelism `schedule` OUTPUT), a step it names
  runs on the service(s) it chose, one job per service; a schedule naming an
  undeclared step refuses, and the schedule's input plan is refused naming
  `schedule --plan`.
- **Run and clone paths**: the step's notebook among its `produces`
  (`Notebooks/...ipynb`) as `--run-notebook`, else its `module`/`function`;
  clone paths are the ones the generator's own import/read walk computes for
  those entries. The smoke options apply to every job.
- **Code bundle**: when the pin is not anonymously reachable and the service's
  adapter declares `CODE_BUNDLE_MAX_BYTES`. On a repository-credential
  carrier, `--repo-credential` is passed instead.
- **Environment requirements**: the target's `requirements.txt` (or
  `pyproject.toml` `[project].dependencies`), minus the distributions the
  adapter's optional `PROVIDED_REQUIREMENTS` says its image provides (none
  declared: every pin is installed).
- **Carry paths**: the step's `produces` roots that are not notebooks.
- **Inputs**: `--dataset`, as for `generate-job` below.

It prints `{jobs, skipped, summary, next}`: one row per job (`step`,
`service`, `job`, `status` `generated` or `refused` with its `error`, and for a
generated one `jobFolder`, `codeBundle`, `inputDatasets`, `carryPaths`,
`environmentRequirements`), and `next`, the one `preflight` command over every
generated job. One refused job never stops the others; the exit status is 0
only when none was refused.

## Job inputs

### From the workspace registry

`generate-job --dataset <slug>` (repeatable; also on `generate-jobs`) resolves
the slug in the workspace's `datasets/registry.json` (`--workspace` overrides
which workspace) through the datasets skill's own `job_input()`. Its ref is
the published remote when that is public, else the public dataset page its
source URL names on a dataset host that recognizes it. The ref is declared as
an input dataset (after any explicit `--input-dataset`), and the official
preparation's sha256 values -- the prepared data file's and `splits.json`'s --
are recorded as `datasetChecks` in `run-config.json`. The runner exports them
as `FORGE_DATASET_CHECKS` (a JSON object keyed by ref), so the target verifies
the data it reads is the data the preparation was made from. Nothing is
uploaded: an unpublished or private dataset refuses `DATASET_NOT_PUBLISHED` /
`DATASET_NOT_PUBLIC` naming `/datasets publish` with the operator's consent,
an unprepared one `DATASET_NOT_PREPARED`, and one served by a host the
service does not attach from (`Adapter.INPUT_DATASETS_HOST`)
`DATASET_HOST_NOT_ATTACHABLE`. Without `--dataset`, nothing changes.

### Declared by ref

A job that reads a public dataset declares it with `generate-job
--input-dataset <owner>/<slug>` (repeatable), recorded as `inputDatasets` in
`run-config.json`. Each ref is exactly `<owner>/<slug>`, each part letters,
digits, `-` or `_`, and appears once; a malformed or repeated ref refuses at
generation, before anything is written, and on every read of
`run-config.json` (`validate_input_datasets()` in `scripts/jobfolder.py`), so
a hand-edited one refuses at `submit` before anything is sent. A job that
declares none is byte-identical to before: no `inputDatasets` key, nothing
added at submit, nothing exported.

A pushed kernel is a non-interactive session: it cannot attach a dataset at
run time (Kaggle refused `kagglehub.dataset_download(...)` inside one with
`New Datasets cannot be attached in non-interactive sessions`), so the
dataset must be named in the push itself.

1. **Optional capability, not a seventh operation.** A backend that attaches
   declared inputs to the push sets `Adapter.INPUT_DATASETS_ROOT` to the
   directory its jobs find them mounted under, read-only; the ABC keeps its
   six abstract operations. `submit` (single send, campaign and rehearsal
   alike) hands that root to the job as `run_config["inputRoot"]` and reports
   `inputs: attached` (the single-send output's `inputs` key, the campaign
   output's top-level `inputs`). A backend that leaves it `None` (Colab)
   reports `inputs: unsupported` and adds nothing.
2. **Kaggle names them in the push.** `adapters/kaggle.py` adds each
   declared ref to the pushed `kernel-metadata.json`'s `dataset_sources`
   (`INPUT_DATASETS_ROOT = "/kaggle/input"`), and `adapters/kaggle_driver.py`
   maps that key through its closed metadata table onto the save-kernel
   request's `dataset_data_sources` (kagglesdk 0.1.37), as it maps
   `kernel_sources` onto `kernel_data_sources`.
3. **The runner says where they are.** Before the callable or notebook
   starts, `discover_input_datasets()` in `assets/runner_invoke.py` searches
   `inputRoot` (at most four levels down, never inside a match) for a
   directory named after each ref's slug, preferring one whose parent is
   named after its owner -- the sub-path below the root is the service's and
   is never hard-coded, since the carried kernel output appeared under a
   `notebooks/<owner>/<slug>/` segment nobody predicted. It exports
   `FORGE_INPUT_DATASETS`: a JSON object mapping every declared ref to the
   directory found, or to `null` when the backend attached nothing or no
   directory was found. Each ref is one `[inputs]` line in the run log; it
   is never fatal. The target reads the mounted directory when there is
   one and falls back to downloading the dataset only when the value is
   `null`.

## Ledger data location

Code is forge-owned and lives here, inside the skill. Data is target-owned:
`<target>/<Name>/.remote-execution/ledger.jsonl`, inside the target's own git
checkout, alongside the repository whose submissions it records.

## Smoke data location

`<target>/<product>/.remote-execution/smoke.jsonl` — the SAME directory
`ledger.jsonl` lives in, product-scoped exactly like it, but a distinct
file (see "Smoke" above for why that separation is load-bearing, not
stylistic).

## Kept partial results location

`<target>/<Name>/.remote-execution/partial/<submissionId>/<UTC stamp>/` --
what `fetch` brought back from a run without a complete result, one
directory per fetch. Outside `Results/shards/` for the same reason as
quarantine below.

## Quarantine location

`<target>/<Name>/.remote-execution/quarantine/<submissionId>/` — a
`fromStaleSubmission` result's fetch destination, structurally outside
`Results/shards/`. This is what makes the non-merging structural rather than
procedural: the tree a shard reader enumerates never contains this path, so
there is nothing a filter could forget to apply.
