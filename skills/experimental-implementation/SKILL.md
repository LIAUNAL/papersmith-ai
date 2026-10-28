---
name: experimental-implementation
description: "Trigger: turn the latest experiments protocol into working Python against a target repository, run its declared measurements, and verify an existing implementation's layout and revision fidelity against both the experiments protocol and the mathematical proposal it answers to. Isolated venv, keyless, fail-closed. The second host on the shared implementation engine (change `the-second-skill-the-seam-was-for`, slice A; change `the-second-document-verified-on-its-own-terms`, slice C) -- two declared documents, each verified on its own claim vocabulary, zero engine bytes."
---

# Experimental Implementation

Turn the current experiments revision (`experiments/experiments-<slug>-vNN.md`)
into Python that runs, in a target repository, and prove it: complete runs whose
own record agrees with what the protocol says.

## Scope: two documents, each verified on its own terms

This skill is the SECOND host built on the shared implementation engine
(`_core/implementation/engine/implementation_engine.py`) -- the same engine
`proposal-implementation` already serves, changed by **zero bytes** to add this
domain. Everything here is a profile
(`skills/experimental-implementation/impl_profile.py`), a byte-identical
launcher copy, this doctrine, two agents, and this skill's own sealed corpus.

**Two declared documents, each with its own claim vocabulary.** `documents[0]`
is `experiments/`, label `experiments` -- the experiments document this skill
originally verified alone (change `the-second-skill-the-seam-was-for`, slice
A). `documents[1]` is `proposals/`, label `proposal` -- the mathematical
proposal this protocol answers to, added by change
`the-second-document-verified-on-its-own-terms` (slice C). Document 0 declares
no per-document overlay and keeps resolving from the top-level scalars below,
byte-identical to slice A; document 1 declares its own complete overlay (all
five leaves: `claim_key`, `locus_key`, `remedy_locus_key`, `notation_keys`,
`citation_pattern`), matching `proposal-implementation`'s own established
`equations` vocabulary for this domain -- never inheriting document 0's
`experiments` vocabulary by omission.

`verify`'s `fidelity.fidelityByDocument` now reports one independent status per
document, each derived from that document's own claim-key module scope: a
module implementing document 0's claims can drift while document 1 stays
clean, and the reverse. A finding may name either or both documents
(`"document": "experiments"`, `"document": ["experiments", "proposal"]`, ...);
each named document's citations are matched against that document's OWN
`citation_pattern`, never a pattern shared across both. Cross-document
agreement (a single verdict combining both documents) and a successor composer
remain follow-on changes (B, D), not built here.

## This domain's own claim vocabulary

Where `proposal-implementation` reads `equations`/`ecuación`/`formulation` at
its own single document, this skill reads its own words for document 0, and
`proposal-implementation`'s own `equations` vocabulary again for document 1
(declared as document 1's own overlay, not inherited):

| Profile leaf | Document 0 (`experiments`) | Document 1 (`proposal`) |
| --- | --- | --- |
| `claim_key` / `locus_key` | `experiments` | `equations` |
| `remedy_locus_key` | `remedy_experiments` | `remedy_equations` |
| `notation_keys.locus` / `.remedyLocus` / `.unknown` | `experiments` / `remedyExperiments` / `unknownExperiments` | `equations` / `remedyEquations` / `unknownEquations` |
| `citation_pattern` | `(Exp. <id>)` / `(Experiment. <id>)` from the shared convention, plus the legacy digit forms `Exps?`/`Experiment`/`Experimentos?` | `Ecs?`/`Eq`/`Ecuaciones?` syntax |
| `documents[N].directory` / `.label` | `experiments/` / `experiments` | `proposals/` / `proposal` |

The top-level `vocabulary.*` leaves below stay document 0's own -- they are
resolver-tier subject words, not per-document claim vocabulary:

| Profile leaf | This domain's value |
| --- | --- |
| `vocabulary.subject_singular` / `_plural` | `experiment` / `experiments` |
| `vocabulary.subject_singular_es` / `_plural_es` | `experimento` / `experimentos` |
| `vocabulary.subject_collective` / `_collective_es` | `experimentation` / `experimentación` |
| `vocabulary.artifact_noun` | `protocol` |

A module's own `__provenance__` declares a non-empty list under whichever
document's claim key it implements (`"experiments"` for document 0,
`"equations"` for document 1) -- a module may declare both -- and every
invariant listed there needs a matching test under `tests/`, exactly as the
sibling's own doctrine requires for its own claim key.

## How an experiment is located: one convention, shared

`verify`'s per-section drift (`fidelity.drift[].changedSections`) speaks in
experiment ids too: an experiment heading's `[exp:<id>]` is its section label
(`documents[0].section_heading.marker` in this skill's profile), and a legacy `## N`
heading reads through the engine's shared section-label convention
(`skills/_core/conventions/sections.json`). Inside a legacy block both ids
move together (`## 1` wrapping `[exp:E1]` reports `1` and `E1`). A module's
`__provenance__["sections"]` names those ids.

`experimental-deliberation` writes the experiments document, and this skill
reads it, so both read the same convention from one file:
`skills/_core/conventions/experiments.json` (the identifier class, the
declaration marker `exp`, the citation marker `tests`, and the prose form
`(Exp. <id>)`). Edit it there, never in either skill.

- **Canonical form.** An experiment is a heading of any level carrying its
  declaration, `## Experiment [exp:E1] — labelled-budget sweep`. Its block runs
  to the next heading of the same or a higher level, so `### Protocol` under
  it belongs to it. A finding names it as `"experiments": ["E1"]`; `compose`
  replaces exactly that block.
- **Legacy forms, still read.** Before 0.14.0 this skill knew only a bare
  `## N` heading, so published revisions carry either `## N` alone or `## N`
  wrapping a `### Experiment [exp:EN]` heading. Both keep reading; no managed
  revision is rewritten. A legacy `## N` block declares `N` and every
  `[exp:<id>]` nested in it, and the two ids name the same experiment
  (`block_locator.block_aliases`): a finding citing `1` and one citing `E1`
  reach the same block, and `compose` accepts a replacement carrying both. A
  replacement carrying two separate experiments still refuses
  `AMBIGUOUS_REMEDY_TAG`.
- **Crossings into the proposal are a separate form.** `[claims:N]` cites
  the proposal's `\tag{N}` and is resolved by `agree`'s crossing check
  against the proposal, never against this document's own experiments.

## Sharing `__implementation__` with `proposal-implementation`

On a target both implementation skills work on, `src/<Package>/__init__.py`
holds one `__implementation__`, and its `revision` names one revision per
document label: `{"proposal": "r03.md", "experiments": "experiments-<slug>-v02.md"}`.
This skill reads only `experiments` (its document 0); the sibling reads only
`proposal`. A bare string still means this skill's experiments revision,
exactly as before 0.14.0. Bound to a single proposal filename, this skill's
`verify` used to look for that family under `experiments/`, find nothing and
report `fidelity: unknown`. A mapping with no `experiments` entry reads as an
unanswered revision, never as the proposal's name. The details, and the
`undeclared` cases, are in `proposal-implementation`'s SKILL.md under "The
implementation declaration".

Under the keyed form, a module bound to the proposal's lineage is the sibling's
to judge: `verify` lists it in `fidelity.otherLineageModules` and keeps it out
of `staleModules` and the headline `fidelity.status`, while
`fidelityByDocument` still judges it under `proposal`. Before 0.14.0 it read
"bound to an older revision" here, so the headline drifted while every entry of
`fidelityByDocument` read `ok`.

## `Data/` is demandable, per product folder

`documents[0]`'s own `dataset_marker` leaf (`**Dataset:**`) makes a
declared dataset demandable: when the bound experiments revision carries
a line-leading `**Dataset:** ...` declaration -- the same marker
`experimental-deliberation`'s own preservation rule already enforces on
this domain's documents -- `verify` reports `{Name}/Data` in
`missingDirs` until that folder exists, exactly as it already does for
`Notebooks/`, `Results/` and `Models/`. Presence only: which files
constitute the dataset is out of scope, matching the other three
categories.

The demand is **per product folder, never at the repository root**, for
three reasons:

1. A run binds to **one method** -- `--name` already carries that
   binding, and the data is the data that method's own experiments use.
2. The same repository's data may not apply to a **different method**
   living beside it under the same clone.
3. A later paper may move the repository to a **different area
   entirely**, whose data is not this one's.

A document declaring no dataset (`dataset_marker: None`, as `documents[1]`
-- the mathematical proposal -- always does) changes nothing: `Data/`
stays undemanded for that document, exactly as before this capability
existed.

## The Results layout the dashboard reads

Every measurement this skill instruments lands inside its own product folder,
under `Results/`, in the shape the command center's experiments panel reads.
A measurement written anywhere else runs and is never shown. Paths are
relative to the product folder `<Name>/`:

| Path | What it holds | Shape |
| --- | --- | --- |
| `Results/history*.{json,jsonl,csv}` | Convergence, per epoch or step | One record per epoch or step, carrying an `epoch` or `step` key and numeric series such as `loss`, `val_loss` or a metric; optional `seed`, `fold` and `model` columns let the panel draw mean ± sd across seeds and separate the curves. |
| `Results/figures/**` | The experiment's figures | `png`, `svg`, `jpg` or `pdf` files. |
| `Results/tables/**` | The experiment's tables | `csv`, `md` or `json` files. |
| `Results/summary.json` | The run's headline numbers | One JSON object. |
| `Results/significance*.json` | The significance table | A JSON list of objects with the keys `comparison`, `test`, `statistic`, `p_value`, `p_adjusted`, `correction`, `effect_size`, `effect_size_name`, `ci_low`, `ci_high`, `n` and `alpha`. |

The test, correction and effect size written there are the ones the bound
experiments revision declares (see `experimental-deliberation`'s **Choosing
the significance test by experiment type**); the instrumentation stage is not
closed for an experiment whose declared significance table has nowhere to
land.

The panel classifies a product folder by its checklist holder: one holding
`Experimental_AGREED.md` is a full experiment (this skill), and one holding
only `AGREED.md` is a proof of concept (`proposal-implementation`).

## The objective flow

**Why this skill was invoked, and where it has to arrive.** Declared here and in
`OBJECTIVE_FLOW`, held equal by a test, and deliberately independent of anything
on disk -- the same property `proposal-implementation`'s own north has, and for
the same reason: a session that hits an error, an interruption or a gap
consults it, locates itself, resolves what blocks, and rejoins.

**Purpose:** carry the declared experiments protocol as far as complete runs
whose own record agrees with what the protocol says -- not a green
verification, not a passing rehearsal.

| Stage | Establishes | Behind you when |
| --- | --- | --- |
| `standing` | A repository set up the way this skill expects, with an interpreter of its own and the protocol's declared steps laid out as runnable commands | `structure` reports no scaffold gaps and the protocol the run answers to is named and readable |
| `binding` | The code that runs says what the bound experiments revision says, every declared step traced to a runnable command | `fidelity` is clean against the bound experiments revision and the target's own suite is green under its own interpreter |
| `instrumentation` | Every measurement the protocol declares has a place to land -- a metric, a record, a check that can fail | every declared measurement resolves to something that can actually be run and read back |
| `rehearsal` | The declared flow runs end to end at a small scale, and the record it leaves agrees with the document a person reads | the rehearsal is complete and its own report is `ok` |
| `full-scale` | Every step routed to where it was decided to run, and executed there at the scale the protocol declares | this is the arrival; it is behind nobody |

**Arrival:** complete runs at the protocol's declared scale, with a record
checkable against the experiments revision.

**Four stops are a person's, not defects to repair:** authorizing that code be
written at all; approving the map from the protocol's declared steps to
runnable commands; publishing the commit a worker would clone; authorizing a
launch, which is hours of somebody's quota.

Before generating a job and again before `gate`, run this skill's own
`launch-plan --target <repo> --name <Name> --revision <revision> --job <job>
[--worker <account>]`. It is the shared engine's command, so it reads this
skill's own holder (`Experimental_AGREED.md`) and writes nothing: it lists
`propose`, `offer`, `gate` and `submit` in order, each with what it would
refuse now and the exact next command, and `verify` reports the same ladder
gaps under `launchLadder`. Pass `--service <service>` when folders of
the same job name sit under more than one service (a job is `(service, job)`;
`JOB_SERVICE_AMBIGUOUS` otherwise). When several remote steps read only what is
already produced -- typically arms placed on different services -- the plan and
`walk` both list them under `concurrentLaunches.launchable`, each to be
launched through its own `propose`/`offer`/`gate`, and name every step still
`waiting` with what it `waitsOn`. A campaign `gate --unit` refuses `NOT_READY`
until every worker its `propose` record names has its own passing rehearsal
at the job's pin, and names the ones that do not. `proposal-implementation`'s `references/usage.md`
(*`launch-plan` — what is still missing before a job launches*) documents its
output.

This north declares no stage nothing measures, and no `entrances` at all --
declaring an entrance nothing produces would be a claim with no producer, the
same reasoning `experimental-deliberation`'s own profile records for itself.

## What this skill delegates, and to whom

Three stretches of this flow are carried out by their own agents: two are
mechanical from end to end, and one is a read-only review between them. What moves is EXECUTION, never doctrine: every rule stays here,
and each agent's first instruction is to load this file.

| Stretch | Delegated to | Begins after | Ends at | Measure this before delegating |
| --- | --- | --- | --- | --- |
| Build | this skill delegates to the `experiments-build` agent | the object-to-map is approved | every declared measurement has a place to land (`instrumentation`) | `verify` -- the protocol's declared steps must already be traced to runnable commands |
| Review | this skill delegates to the `experiments-reviewer` agent | every declared measurement has a place to land (`instrumentation`) | a findings report on code quality, optimisation, remote GPU use and statistical tests, read by the operator before the rehearsal and the launch | `verify` -- every declared measurement resolves, so the code under review is the code that will run |
| Walk | this skill delegates to the `experiments-walk` agent | each step's placement is decided | the launch the operator must authorize | `verify` -- `undeclaredPlacement` is empty, so every step says where it runs |

Each agent also refuses from inside when it finds itself before its own start --
the backstop, not the rule.

## When a delegated agent cannot be spawned

Each stretch this skill delegates is defined in full by its own agent file:
`.claude/agents/experiments-build.md`, `.claude/agents/experiments-reviewer.md`,
`.claude/agents/experiments-walk.md`.
When an agent cannot be spawned — the harness has no sub-agent mechanism, the
agent is not registered in this session, or the spawn itself fails — perform
the stretch inline: read that agent's definition file and follow it as
written, from the beginning it states to the end it states, holding any gate this skill sets before the stretch, and returning the report shape it specifies. Its
`tools:` line still bounds the stretch: an act that would need a tool outside
that list is a stop, not a workaround. Say in the reply that the stretch ran
inline and why the agent could not be spawned.

## Estimating the processing time before the pilot and before the full run

Report the processing-time estimate to the operator before asking for a
pilot, and again before asking for a launch of the full run. It comes from
`remote-parallelism`'s `estimate` verb
(`skills/remote-parallelism/SKILL.md`, **Estimate before you scale**), read
over the timing probe's record.

- **The timing record.** A short timing probe — one epoch of one fold per
  arm, on the target's own interpreter, with the device recorded — writes
  `Results/timing.json` in the product folder `<Name>/`. `Results/` is
  declared among the step's `produces` roots, so the record is committed with
  the step's product like any other output. `scales` is copied from the
  approved experiments protocol (the bound experiments revision) and the
  declared pilot; nothing guesses it.
- **The estimate.** `estimate --timing <Name>/Results/timing.json --record
  <Name>` gives each stage (`poc`, `full`) a range per host, from the one
  formula that verb defines. A remote GPU host reads `unmeasured` until a
  measured rehearsal on that host adds its own timing; local timings never
  stand in for it.
- **Where it runs, and how long a proof of concept may take.** The same
  output carries `placement` per stage, read on each range's upper bound. A
  stage whose local estimate exceeds 20 minutes runs on a cloud host — the
  fastest one measured, or one timed first — never locally. A proof of
  concept is sized to run in at most 5 hours on the host it is placed on;
  when `placement.pocBudget` reads `exceeds`, the design is reduced (subjects,
  epochs, folds, seeds or arms) and estimated again before the pilot is asked
  for.
- **What it is.** A measurement-derived range (±20%, single-probe
  extrapolation), never a promise, and never authorization: the pilot and the
  launch stay the operator's to approve after reading it.

## The hyperparameter search step

Only when the bound experiments revision declares a Hyperparameter Search
subsection. The step sits after the proof of concept and the timing estimate,
and before the full runs: the timing probe sizes it (`plan --timing`), and it
is placed like the full runs — a step routed to a remote GPU notebook is
generated, rehearsed and launched through `remote-execution`, behind the
operator's consent. It runs through `/hyperparameter-search`
(`skills/hyperparameter-search/SKILL.md`), which validates the plan, names one
study per arm and outer fold and reports their importance and contour figures
under `Results/hpo/`. Its results are frozen per outer fold: every seed of
the full run reuses that fold's tuned values and never searches again.

## Where to start: the repository is the memory

Same routing rule as `proposal-implementation`'s own -- **read `src/`, never
remember a prior session.** An implementation already sitting there is the
whole record of what was already asked and answered; a repository with none
has not been through this skill yet.

- **`src/` holds no implementation at all** -> Flow A.
- **`src/` holds one, whatever revision it is bound to** -> Flow B, which
  measures drift against BOTH documents before deciding anything.

## Flow A -- first pass

This domain ships no `assets/kit/` (`materialize --stage scaffold` is
unavailable, above), so a target's scaffold is hand-written, not
materialized. Everything else follows the sibling's own first-pass shape,
narrowed to what this domain actually has:

1. Clone the target repository under `implementations/<repo>/`, then `env`
   to build its own venv from its own interpreter -- never the forge's.
   `env` first adds `.venv/` and `*.egg-info/` to the clone's
   `.git/info/exclude`, so neither leaves the tree dirty for a later
   clean-requiring command.
   `env --torch cpu|gpu [--torch-version X]` adds a torch build to the printed
   install (CPU: the PyTorch CPU index and an exact `+cpu` pin), and
   `__backend__` in `src/<Package>/__init__.py` states the backend `probe`
   reads instead of inferring it from imports (`proposal-implementation`'s
   SKILL.md, `nextStep: "convert"`).
2. **Ask for the name.** Run `name --name "<whatever they typed>"`, confirm
   both forms it returns, then **[GATE]** before writing anything with them.
3. **[GATE] Ask for authorization to implement.** Nothing below writes code
   before this.
4. Present the object-to-module map for **both documents** -- which module
   implements which experiment section, and which implements which
   equation the experiment answers to (`documents[0]`/`documents[1]`,
   above). Wait for approval, then write code, and give each module the
   `__provenance__` claim key it actually implements (`experiments`,
   `equations`, or both).
5. Hand off to the `experiments-build` agent once every declared
   measurement has a place to land (`instrumentation`, the objective flow
   above) -- delegated, not walked by hand.
6. Hand off to the `experiments-walk` agent once every step's placement is
   decided -- the same delegation table above names when each stretch
   begins and ends.
   `walk` commits each step's product under the subject `walk: <step>`; a
   target held to a commit convention passes `--commit-template
   'chore(walk): {step}'` (`{step}` is the one placeholder; anything else is
   refused `WALK_COMMIT_TEMPLATE_MALFORMED` before the walk starts). The
   shared engine's `walk` is documented in `proposal-implementation`'s
   `references/usage.md`.

## Flow B -- every later pass

1. Read `src/` and take the newest revision of **each** declared document
   independently -- document 0's own discovery, and document 1's own,
   never one name assumed for both (`each-document-names-its-own-revision`).
2. **Run the suite with the target interpreter, then `verify --revision
   <document 0's newest>`.** Same division as the sibling's own Flow B step
   2: running the suite proves the code *does* what it says; `verify`
   proves it *says* what it should. Neither substitutes for the other.
3. **Differences in fidelity, in EITHER document** -> **[GATE] ask whether
   the user made that document's own change** -- `fidelityByDocument`
   reports each document's status independently (above), so a drift in
   document 1 alone routes the same gate document 0's own drift always
   has, and does not wait for document 0 to also disagree. The gate itself
   is not repeated or reworded here: it is the sibling's own
   ("did the user make this change") asked against whichever document's
   own evidence disagrees.
4. **Suite green and fidelity clean in both documents** -> `agree
   --revision <document 0's newest>` (available once more than one
   document is declared, which this skill's profile always does). Names
   every citation the experiments document makes into the mathematical
   proposal that the proposal does not currently declare, and every claim
   the proposal declares that no experiment cites -- refuses once, naming
   both kinds together, never a verdict on which side should change.
   Resolve each named discrepancy in conversation (`--acknowledge <exact
   id>` clears only the ids echoed back exactly, for that one call) before
   continuing. A claim the experiments document deliberately does not test
   is declared there instead, once, with the shared convention's
   `[out-of-scope:<id>]` marker: `agree` subtracts it from `untested` on
   every later call and echoes it under `outOfScope` (see
   `references/usage.md`). Deciding that a claim is out of scope is the
   user's call, made in the experiments document through
   `experimental-deliberation`, never something to write in to make `agree`
   pass.

   - **A third kind `agree` never checks, and never will:** whether an
     experiment's declared metric or protocol actually corresponds to
     what the claim it cites asserts. Reading both documents to judge
     that is exactly the kind of question a check that tried would get
     wrong in both directions -- blocking correct work and passing broken
     work alike. It is guidance for whoever reads `agree`'s output next,
     never a condition `agree` tests: a citation can resolve cleanly by
     `agree`'s own measure while still citing the wrong claim for what it
     actually measures, and only a reader who has read both documents can
     tell.
5. Once `agree` reports no unacknowledged discrepancy, run `handoff
   --revision <document 0's newest>` to size the open findings and hand
   the local ones to the deliberation (`experimental-deliberation`) as
   agenda items. `settleInline` entries substitute through `compose`;
   everything else is a prompt for a session of its own. A finding whose
   defect lives in the protocol's prose rather than in an experiment block
   declares `"remedy_in_prose": True` with `remedy_experiments` empty and no
   `remedy_block`: it is never asked for a block and always defers, as
   `prose-remedy` (the shared engine's rule, stated in full in
   `proposal-implementation`'s own SKILL.md).
6. Once the deliberation publishes a successor revision, this skill's own
   part is done -- what remains is reaching a **test submission**, and
   `remote-execution`'s own commands answer it exactly as they do for the
   sibling: `probe`'s `nextStep` names which one, and
   [the sibling's own remote-execution seam table](../proposal-implementation/SKILL.md#the-remote-execution-seam--which-subcommand-answers-which-reported-state)
   names which subcommand answers which reported state. Nothing here
   re-documents that table or re-asks its own gate; this skill drives the
   same shared scripts (`REMOTE_EXECUTION_CLI_SCRIPT` et al., already
   `FORGE_ROOT`-derived) rather than rebuilding them.

## Entry command

```bash
skills/experimental-implementation/scripts/implementation_cli.py <command> [args...]
```

A concrete, runnable example -- this exact line runs verbatim, unedited, from
the forge's own root (`tests/test_experimental_implementation.py`'s own
published-commands test proves it):

```bash
skills/experimental-implementation/scripts/implementation_cli.py name --name Trial
```

The launcher is a byte-for-byte copy of `proposal-implementation`'s own launcher
(design.md D4): every value inside it is derived from its own location, so the
same bytes, placed under this skill's own `scripts/`, resolve to THIS
skill's own profile without a single domain-specific line. Every argument,
subcommand and exit code is the shared engine's; nothing here re-documents them.

The launcher sets `IMPLEMENTATION_DOMAIN_PROFILE` only when the environment
does not already carry it, so an explicit fixture profile wins. One inherited
value is refused instead: another skill's own `impl_profile.py` (for example
`proposal-implementation`'s, left exported by a shell or an earlier process),
under which this skill would read the other skill's documents and holder. The
launcher exits `2` with `IMPLEMENTATION_DOMAIN_PROFILE_SIBLING` before the
engine loads, naming both profiles; unset the variable and run again. The
sibling is recognized by the skill its profile declares (the skill directory of
`PROFILE["cli"]["path"]`), not by where the file sits, so a sibling's profile
from another checkout or workspace is refused too; this skill's own profile is
accepted from any tree.

A profile you set yourself (a fixture, or the engine run without this
launcher) must be an absolute path: a relative one refuses
`IMPLEMENTATION_DOMAIN_PROFILE_NOT_ABSOLUTE` before any command runs. The
commands that write the ledger take `--session <id>`, an id you choose per
working session; `proposal-implementation`'s `references/usage.md`, "Session
ids", defines it. The workspace bridge `smith implement` drives the
sibling's launcher, never this one: run this skill's commands through its own
`scripts/implementation_cli.py`.

## Which commands are not available yet, and why

This domain ships no `assets/kit/` at all (measured this session: the kit
sibling ships is ~99% general machinery, and copying ~2,000 lines to change the
~20 that are not would be the exact duplication the operator refused for the
CLI, one directory over). Consequence, stated rather than discovered:

- **`materialize --stage scaffold`** and any other stage that copies kit
  destinations reads `assets/kit/`, which this skill does not ship. A target
  scaffolded under this domain needs its object-to-module map approved and
  written by hand, or from a kit a later change adds.
- **A target the sibling scaffolded carries the sibling's seal**,
  `src/<Package>/report_digest.py`, which declares no `__provenance__`.
  `verify` here does not list it under `missingProvenance` while its bytes are
  exactly the ones the scaffold receipt's `materialized` entry recorded; a
  modified copy, an adopted one, or one with no receipt entry is reported
  like any other module. The same holds for the sibling's remote stamp,
  `src/<Package>/remote_stamp.py`, scaffolded beside it with
  `tests/test_remote_readiness.py`. A full run's remote smoke callable calls
  `write_shard(summary)` from it: under the runner (`FORGE_RUN_MODE`) it
  writes the `shard.json` `smoke record` reads, carrying `evidence.commit`,
  `evidence.sourcesDigest` and `environment.device`, and anywhere else it
  writes nothing. Pair it with `generate-job --smoke-required-evidence
  evidence.commit --smoke-required-evidence environment.device.kind`. The
  readiness test's `FORWARD` placeholder is where the target wires its own
  forward for the `meta` device-mix guard (see the sibling's step 5).

Every other published command runs exactly as `proposal-implementation`'s own
doctrine describes it, against this domain's own profile leaves instead of the
sibling's.

## The checklist holder: `Experimental_AGREED.md`

This skill declares its own checklist holder in `impl_profile.py`'s
`PROFILE["holder"]["filename"]`: `Experimental_AGREED.md`, deliberately
distinct from the sibling's own `AGREED.md` -- the two skills share the same
engine and the same per-product-folder shape, so a fixed shared name would
let one skill's write land inside the other's checklist. See
`references/usage.md` for the create-on-absent behavior, for why the
sibling's own `AGREED.md` beside it is set aside rather than refused, and for
what `position`/`settle` refuse (`HOLDER_UNDECLARED`, naming both exits) when a
checklist already exists under a name no skill sharing the engine declares.

An agreement no test could ever witness is closed by the operator's recorded
decision, `settle --done --unwitnessed --reason "<their reason>"`, never by a
hand tick; `close` owes a position only once the target declares a flow. Both
are described in `references/usage.md`.

**Once the full experiments' approval in `<Name>/Experimental_AGREED.md` is
settled, run `/experiment-diagrams experiments`** so the operator verifies the
experiments diagram beside the product in the dashboard's Experimentos panel and
validates it there; nothing of the product is launched remotely
(`DIAGRAM_NOT_VALIDATED`) until then.

## What this skill has not written down

Same as the sibling, and settled the same way: `.implementation/` is a required
`.gitignore` entry, so neither a launch authorization nor a deliberation record
reaches a clone. **Settled by the operator on 2026-09-14: that is correct and
the ledger is not split.** What the forge needs to do its own work stays home;
the reasoning behind the agreements travels in the paper. Do not re-raise it as
an open gap -- see the sibling's own section for the full wording.

## Non-negotiable isolation

Every run works inside `implementations/<repo>/` and uses that repository's own
`.venv`. Never the forge's virtualenv, never system Python for target code.
`implementations/` is gitignored; the CLI refuses any target outside it, and
refuses to create a venv from a forge interpreter -- exactly as the sibling's
own doctrine states, because this is the shared engine's own behaviour, not a
domain-specific one.

## References

- `references/usage.md` -- this skill's own checklist-holder obligations
  (declared filename, create-on-absent, write-refusal-into-an-undeclared-
  holder). This skill ships no `assets/kit/`, so the sibling's own worked
  invocations and kit-asset sections do not apply here; see
  [`proposal-implementation/references/usage.md`](../proposal-implementation/references/usage.md)
  for those.
- `scripts/implementation_cli.py` -- the byte-identical launcher copy
  (design.md D4) that resolves to this skill's own profile.
