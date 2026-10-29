### `nextStep: "validate"` — run the acid test: the method alone, against its own claim

Reached one of two ways, and its own PUBLISHED TEXT differs by which (design
D13, D19-D21, D23a-D23c — a branching sentence under the one rung name, the
`declare-first`/`build-first` precedent).

**Reached from an absent benchmark package** once the comparison has been
declined and this second question is still open (`probe`'s four-way branch,
all within the one last-among-the-overrides position): unanswered comparison
→ `benchmark`; comparison declined, acid test open → `validate` (the OFFER TO
RUN, described below); both declined → `declined`, naming both dates; either
decision reopened or freshly answered `"yes"`, nothing yet built →
[`build-first`](#nextstep-build-first--a-standing-decision-was-accepted-and-nothing-is-built-yet)).

**Reached from `already-benchmarked`** (Unit 6b, D23a) once a comparison has
already run AND completed, WITH more than the method's own single arm
declared, and this transition's own bucket is unanswered — a REPORTING
STATE, never an offer to run, and covered in its own subsection below
("Two transitions, and they are not symmetric").

**What it is, and what it is not.** The target's own apparatus, the same one
`benchmark` above uses, with a single arm: the method alone, on real data, at
small scale — no rival, no winner. The question is not "which wins" but "does
the method do what the proposal said it would do". It is **not more
verification** — the invariant tests already prove the formulas in the
abstract, with no data — and it is **not a comparison** — there is no rival
arm and nothing here decides a winner.

**The yardstick's form is already written; its calibration is asked.**
`__implementation__["premises"]` states the prediction, the statistical unit,
the metric and the direction — the shape of a single-arm pass/fail criterion.
It does not state a threshold, and with one arm there is nothing to be better
than. The draft's `needs` asks the person for the reference figure the
declared `revision` reports, and names that revision — the engine never
parses a number out of prose (`report_state`'s own `proseNumbers` finding
treats exactly that as a defect).

**`placement` is its own section in the draft, and it decides nothing.** A
`__steps__` entry with no `placement` blocks the walk
(`PLACEMENT_UNDECLARED_CONSEQUENCE`), so the draft names `local` and `remote`
with each one's own consequence and picks neither. Within that section a
`job` folder name is already proposed, derived mechanically from the step's
own name — costing the person nothing to accept — but `service` is asked,
never guessed: this skill may read a service name to walk a directory and
must reduce it to a count before returning anything, and it cannot discover
one either, since adapters register lazily. Any accelerator, environment, or
budget knob the remote path accepts is named as available and answered by
the person, never pre-selected. An empty `__levels__` does not rule out a
remote placement — the two are independent declarations; an empty ladder
only changes the walk's grading from by-rung to walked/not-walked.

**The published question states cost's shape, never its magnitude.** It says
that this is a real run that spends machine time, that a local run occupies
this machine for its duration, that a remote run spends metered quota on a
service account, that the scale on offer is the small one and a larger
campaign is a separate decision, and that declining later costs nothing to
unwind. It states no duration, no quota figure and no service name — the
forge cannot know any of those, and this repository already lived through a
forge-invented weekly-quota figure that sat in a comment nothing read and did
not match reality.

**A remote acid-test step reaches a worker through the unmodified
`remote-execution` path.** Nothing here is new machinery: `flow_acts` is
already generic over any declared step's `placement`/`job`/`service`, and
`resolve_clone_paths()` already cross-checks declared clone paths against
what the declared entry modules actually import — a single arm simply needs
fewer of them, through the identical check every other step uses. The job
folder lands at `tools/<service>/<job-name>/` — `remote-execution`'s own
output root, outside all three `materialize` stage lists — and carries the
notebook already chosen for the run via `--run-notebook`, never a second
implementation of it.

**What it may write to, and the one thing it may never create.** Accepting
the acid test **must never create `src/<Package>_Benchmark/`** and must
never write any harness-stage destination — not the benchmark declaration,
not its entry module, not its verdict module, not its harness notebook. A
single-arm run of the method against its own declared prediction is not a
benchmark, and naming it one would reintroduce this skill's own defect
wearing the opposite mask. This holds identically whether placement is local
or remote: a generated job folder is not a back door around it, because
`tools/` sits outside every `materialize` stage list even in principle. What
it MAY write to: the method's own package declaration (a `__steps__`,
`__records__` and/or `__levels__` entry, re-sealed with `materialize
--authored`), the method's own modules and tests, `<Name>/Notebooks/`, a
record under the product folder at a path that does not borrow the
comparison's name (never `.../Results/Benchmark/...`), and — when placement
is remote — its own job folder under `tools/`. Every other package under
`src/` stays read-only to it.

**Nothing materializes up front.** Asking the question creates nothing;
answering it and opening a discussion creates nothing; only agreeing a
specific run materializes what that run needs — the identical discipline
`benchmark` above and D15b state for the comparison offer.

**Answering is entirely inside this skill and this session.** Nothing here
hands off to another skill: acceptance is discussed with the same
discuss/agreement machinery this skill already uses for its other offers.

**Boundary, named rather than built.** `generate_job` accepts
environment-provisioning input (`environment_requirements`,
`environment_index_url`), and at least one already-scaffolded target
carries its own top-level `__environment__` literal of exactly that shape,
unread by anything in this skill (see
`implementation-comparison-deferral`'s migration requirement, which
carries it forward rather than dropping it). Wiring that literal through
as the remote acid test's environment input is almost certainly what it
was meant for, and this is where that wiring would eventually live. **It
is not built here** — that is a reader for a literal this change
deliberately leaves without one, named so the next person finds it rather
than rediscovers it.

**Two transitions, and they are not symmetric (Unit 6b, design D22/D23).**
Somebody who already has one of the two — a run acid test, or a run
comparison — can want the other. The two directions are not the same
operation, and neither is automatic: both are discussed first, the
identical `discuss --decision yes|no` gate every other decision surface on
this ladder already uses.

- **Test → comparison ADDS.** A rival arm answers a different question —
  "which wins" rather than "does it do what it said" — and gaining that
  answer does not retract the one already given. The mechanism is D19's
  token and *nothing else*: re-answer the comparison bucket with
  `decision: "yes"` and the ladder reports
  [`build-first`](#nextstep-build-first--a-standing-decision-was-accepted-and-nothing-is-built-yet)
  exactly as it would for a fresh acceptance — no separate transition
  surface exists, because two mechanisms this skill already ships already
  compose it. The acid test's own record is never deleted, overwritten, or
  re-run by building the comparison.

- **Comparison → test REMOVES NOTHING.** A completed comparison already runs
  the method on the same data an acid test would use, so the acid-test
  question is already measured inside the comparison's own record — no new
  run is required. Reached from `already-benchmarked`, `validate` publishes
  a REPORTING state, never an offer to run (see above): it names that the
  answer already lives in the comparison's own record and the arm that is
  the method, and asks whether to stop asking the comparison's own
  question about the rival separately. No `validation` draft rides beside
  this publication — proposing a run here would spend machine time
  relearning what the repository already knows, this change's own defect
  class wearing a third mask.

  **Accepting undeclares the rival arm and deletes nothing (D23c).** The
  transition is a hand edit to the benchmark declaration's own `arms`
  block — removing the rival's entry, keeping the method's own — re-sealed
  with `materialize --authored` (D10's own precedent; no new CLI verb).
  This engine performs no such edit itself: `materialize --authored` only
  re-seals a receipt over bytes already on disk, the identical restraint
  every hand-edited declaration in this skill already keeps. Once
  undeclared, the rival is invisible to every arms-based reader
  (`unreachedModules`, the wiring crossing, `probe`'s own ladder) going
  forward — that is what "stop asking" means. **Never touched by either
  direction**: `<Name>/Results/…`, every executed notebook and its stamp,
  and every ledger event. "Ceasing to ask about something" and "erasing
  it" are different operations; this capability performs only the first,
  because the forge may not assume recoverability — a target's own git
  history is *that target's* measured property, never a guarantee this
  engine can check before acting on it.
