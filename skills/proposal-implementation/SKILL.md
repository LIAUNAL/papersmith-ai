---
name: proposal-implementation
description: "Trigger: turn the latest managed mathematical proposal into working Python, scaffold or reorganize a target repository, or verify an existing implementation's layout and revision fidelity. Isolated venv, keyless, fail-closed."
---

# Proposal Implementation

Turn the current managed revision (`research-concept-rNN.md`) into Python that
runs, in a target repository, and then prove it: smoke, invariants, synthetic
data. Text is not the deliverable — code with a traceable link back to the
mathematics is.

## What this skill has not written down

**The ledger is ignored whole, and that is the decision.** `.implementation/` is a
required `.gitignore` entry, so nothing under it reaches a clone. It holds two
different things: a `gate` event is a launch authorization, and since `discuss`
and `settle` landed the same file also carries the deliberation -- what was
asked, what was answered, and what was placed into the record because of it.

An earlier version of this section argued that the second half deserved to
travel and that a future version should split the ledger in two. **Settled by
the operator on 2026-09-14: it does not travel, and the ledger is not split.**
`.implementation/` is what the forge needs to do its own work; somebody reading
this repository wants the implementation, not the transcript of how it was
agreed. The reasoning behind the agreements already travels, in the paper.

This is recorded here rather than left silent because the previous wording
argued the opposite convincingly enough that a reader with no memory of that
decision would have implemented the split. Do not re-raise it as an open gap.

## Non-negotiable isolation

Every run works inside `implementations/<repo>/` and uses **that repository's own
`.venv`**. Never the forge's virtualenv, never system Python for target code.
`implementations/` is gitignored; the CLI refuses any target outside it, and refuses to
create a venv from a forge interpreter.

### Executing a notebook needs `PATH`, not just the right `python`

```bash
cd implementations/<repo>
PATH="$PWD/.venv/bin:$PATH" .venv/bin/python -m jupyter nbconvert \
  --to notebook --execute --inplace <Name>/Notebooks/<notebook>.ipynb
```

The `PATH` prefix is the whole point of that line, and dropping it is the
obvious mistake. A notebook does not name an interpreter; it names a
**kernelspec**, and a kernelspec is resolved when the kernel starts. The
ordinary `python3` kernelspec's `argv` begins with a bare `"python"` — no
absolute path — so the kernel launches whatever `python` is first on `PATH` at
that moment. Which interpreter launched `jupyter` has nothing to do with it.
So `.venv/bin/python -m jupyter nbconvert --execute` reads as isolated and is
not: the cells run under whatever the shell would have run, commonly a system
Python several minor versions back.

It fails as badly as it can: measured on a real target, a suite passing 297/297
standalone produced fifteen failures inside the notebook, and **not one line of
the failure text named an interpreter**. The reader is handed fifteen defects
that do not exist.

`verify` reports the fact rather than leaving it to prose: `validation.notebooks`
carries `interpreterVersion` (the target venv's own, read from `pyvenv.cfg`) and
per notebook `executedBy` with `interpreterMatch`, plus `foreignInterpreter`
naming every executed notebook that ran under something else. `interpreterMatch:
null` means unmeasured — no venv to compare against, or a notebook whose
metadata records no version — never a pass. It reports and never gates: a
foreign interpreter is not a wrong number, it is a reason to distrust the
numbers, and folding the two into one status destroys the distinction.

## The objective flow

**Why this skill was invoked, and where it has to arrive.** Declared here and in
`OBJECTIVE_FLOW`, held equal by a test, and deliberately independent of anything
on disk. Every other reading answers *where am I* by measuring products; this
answers *what is this for*, which no product implies.

It exists for the moment something breaks. A session that hits an error, an
interruption or a gap consults it, locates itself, resolves what blocks, and
rejoins — rather than improvising forward, which is what an agent does when a
blocker detaches it from the purpose. Every refusal this engine raises carries
it, at the single place they all reach a reader, so it is never further away
than the thing that stopped you.

**It is not the agreements and does not replace them.** What the mathematics
says lives in the managed revision; what was settled about a repository lives in
its own declared holder, `AGREED.md` (`PROFILE["holder"]["filename"]` in this
skill's own `impl_profile.py` -- a name this skill declares for itself, not an
engine default). A sibling skill sharing the engine declares its own holder
(`Experimental_AGREED.md`); each skill sets the other's declared holder aside
instead of reading it as an undeclared checklist, so both coexist under one
`<Name>/`. This says only what the skill is for.

**Purpose:** carry the agreed formulation as far as complete runs that can be
reported — not a green verification, not a passing rehearsal.

| Stage | Establishes | Behind you when |
| --- | --- | --- |
| `standing` | A repository to write the mathematics into: isolated under `implementations/` with an interpreter of its own, laid out the way this skill expects, the kit's destinations materialized, and the map from mathematical object to module approved | `structure` reports no scaffold gaps and `__implementation__` carries the revision and premises the map was approved with — which is what `materialize --stage objects` refuses without |
| `fidelity` | The code says what the bound revision says, and every claim carries an invariant with a test | `fidelity` is clean and the target's own suite is green under its own interpreter |
| `audit` | What the formulation gets wrong, established over the declared sweep, each remedy ruled admissible before it is measured and validated after | `audit` is no longer `incomplete` |
| `declaration` | What the experiment compares, over which statistical unit, by which metric, and what it produces | the benchmark declaration is answered rather than sitting at its scaffolded empty value |
| `rehearsal` | The declared flow runs end to end with its own notebooks, and the document a person reads agrees with the run | the pilot is complete and `report` is `ok` |
| `full-scale` | Every step routed to where it was decided to run, and executed there at the scale the protocol declares | this is the arrival; it is behind nobody |

**Arrival:** complete runs at the declared scale, local or remote as each step declares, with the record they leave.

**Four stops are a person's, not defects to repair.** Two of them stand in the
first stage and a session that starts from nothing meets them before anything
else: **authorizing that code be written at all**, which nothing below that gate
may start without, and **approving the map** from mathematical object to module
with the revision and premises recorded beside it. The other two stand at the
end: **publishing the commit** a worker would clone, and **authorizing a
launch**. An agent that reads any of them as a blocker will stall on it or take
it, and the last is how quota gets spent by somebody who was not asked.

That the first two exist is what makes this north cover a repository with
nothing in it. Its stages used to begin at `fidelity` — "the code says what the
revision says" — which presumes code, so a session invoked on a bare repository
read a north whose first stage assumed something that did not exist yet. A north
has to read the same on an empty repository as on one mid-campaign.

The conditions above are written to be READ, not computed. A stage derived from
products would make the purpose depend on the products, which is the one
dependency this exists without: it has to read the same on a repository with
nothing in it as on one mid-campaign.


## What this skill delegates, and to whom

Three stretches of this flow are mechanical from end to end — they carry out
decisions already taken and take none of their own — and each runs in an agent
of its own rather than in the conversation. What moves is EXECUTION, never
doctrine: every rule stays here, and each agent's first instruction is to load
this file.

A stretch begins after one of the operator's gates and ends before the next.
That boundary is the whole design: an agent that started mid-decision would
take it, which is the failure this shape exists to prevent.

| Stretch | Delegated to | Begins after | Ends before | Measure this before delegating |
| --- | --- | --- | --- | --- |
| Build | this skill delegates to the `implementation-build` agent | the object-to-module map is approved | the operator decides what to do with the findings | `verify` — `__implementation__` carries `revision` and `premises`, which is what `materialize --stage objects` refuses without |
| Walk | this skill delegates to the `implementation-walk` agent | each step's placement is decided | the launch the operator must authorize | `verify` — `undeclaredPlacement` is empty, so every step says where it runs |
| Replicate | this skill delegates to the `paper-replicator` agent | code was authorized, the repository is standing, and the referenced comparison or baseline paper is ingested under `guidance/` | the operator decides whether the adopted or replicated method is faithful enough to serve | `guidance/` holds the paper's Markdown with its equations as LaTeX; the agent searches for published code itself and records the search |

**The last column is what stops a wasted delegation.** Each agent also refuses
from inside when it finds itself before its own start — that is the backstop,
not the rule. Discovering it there costs a whole round trip to learn something
measurable before leaving, and the orchestrator that delegated has to be able to
tell "it could not start" from "it started and failed".

**On a harness with no Task-tool delegation** (no sub-agent mechanism is
documented today for pi, OpenCode, or Antigravity — see the workspace's own
`.pi/APPEND_SYSTEM.md`, `OPENCODE.md` and `.agents/AGENTS.md`):
run whichever stretch, Build, Walk or Replicate, in-process, as one step, in the same
order, holding to the same measure-before-delegating gate before starting.
The tool boundary each agent would have enforced differs by row —
`implementation-build`'s grant (`Read, Write, Edit, Bash, Glob, Grep`),
`paper-replicator`'s (the same plus `WebSearch, WebFetch` for its code search) versus `implementation-walk`'s (`Read, Bash, Glob, Grep`, with no
`Write`/`Edit`) — and either becomes the orchestrator's own discipline to
hold for whichever stretch is running, not a structural guarantee: treat
any action that would have needed a scoped-out tool as a stop, not a
workaround.

### Bringing in a comparison method: published code first, replication second

Every method the proposal compares against or builds on goes through the
Replicate row above, and the agent's first act is a recorded search for the
paper's published code. When code exists and its license allows reuse, the
agent adopts it pinned to a commit and audits it: each equation and stated
hyperparameter is matched to the line that implements it (`match`,
`deviation`, `unspecified`), the repository's own tests run, and the same
invariant tests and toy-set smoke run as a replication follow. Only when no
usable code exists does it reimplement the method from the paper, because every
choice the paper leaves unstated becomes a choice somebody made here.

For a replication, ingest first. The agent reads the paper as `paper-ingestion` leaves it under
`guidance/` (equations as LaTeX), plus the two or three cited papers the method
depends on when they are ingested too, and refuses on a bare PDF. It then plans
(modules, data shapes, configuration), analyses each equation into a function
with its shapes and assumptions, writes the code into the target's existing
layout, and verifies it with invariant tests (shapes, gradients, known cases)
and a short smoke run on the proof of concept's toy set before any GPU run.

Its product is code plus `REPLICATION.md`: the code search and the route
taken, then a correspondence table where every hyperparameter and architecture
choice cites the paper's section or equation or is marked `unspecified` with the
default chosen and why, and, for adopted code, what the code does and its
verdict. Read the `unspecified`
rows before trusting the replication: they are where it can differ from the
paper without anything failing. The agent reports no number it did not produce
and launches nothing remote.

It runs as a subagent of the active session (Claude Code, OpenCode or Pi) on
that session's own model: no API key, no external LLM service.

### `remote-execution` is driven, not delegated to

An agent of its own was considered and rejected, and the reasoning is kept
because the case for it was good and somebody will make it again.

**What argued for one.** It is the only thing in this forge that spends money,
and a boundary around what spends is the most valuable boundary there is. Its
doctrine is large, and carrying it in a walk agent's head is the context bloat
this whole shape exists to reduce. And its tools could be cut to `Read` and
`Bash`, making "it never edits the target" structural rather than doctrinal.

**What decided against.** The walk stretch does not need that doctrine — it
drives `remote_cli`, and that CLI refuses precisely and carries its own north in
every refusal, so what the walk needs is to run commands and read what comes
back. A second agent would be a hop that buys nothing it does not already have.

And the quota argument does not survive inspection: **the boundary that stops a
campaign is the launch gate, not an agent.** The walk stretch ends there by
construction and has no path to submitting one. Putting an agent in front of a
gate that already holds adds a door beside an open wall.

**What would change this.** If a stretch ever needed to run remote acts *past*
the launch gate — polling, fetching, reconciling a campaign already out — that
stretch has a different end and a different risk, and the case for its own agent
would have to be made again from there.

**Nothing here forces a delegation.** Running a stretch in the conversation is
legitimate and is what happens when the operator wants to watch it. What the
declaration buys is that the boundary is written down: a stretch that could have
been delegated is one whose ends somebody had to name.

## When a delegated agent cannot be spawned

Each stretch this skill delegates is defined in full by its own agent file:
`.claude/agents/implementation-build.md`,
`.claude/agents/implementation-walk.md`,
`.claude/agents/paper-replicator.md`. When an agent cannot be spawned — the
harness has no sub-agent mechanism, the agent is not registered in this
session, or the spawn itself fails — perform the stretch inline: read that
agent's definition file and follow it as written, from the beginning it states
to the end it states, holding any gate this skill sets before the stretch, and
returning the report shape it specifies. Its `tools:` line still bounds the
stretch: an act that would need a tool outside that list is a stop, not a
workaround. Say in the reply that the stretch ran inline and why the agent
could not be spawned.

## Activation Contract

Activate when the user asks to implement, code, scaffold, reorganize or verify
the implementation of the managed proposal. Do not activate for edits to the
proposal itself — that is `proposal-deliberation`.

## Hard Rules

- **Reply in the language the user is writing in.** Every artifact stays English --
  code, comments, commit messages, reports, every file written. The conversation
  does not. This rule is stated here, first, because it is broken by drift rather
  than by decision: this file is two thousand lines of English procedure, and
  reading it is not an instruction to speak it. It is also restated under `## How a
  gate is asked`, where it reads as being about gate questions; it is not. It
  governs every reply.
- Bind to the revision `proposal-deliberation`'s `STATUS` reports as `latest`. Never
  guess the base and never read `proposals/` by hand.
- Never write implementation code before the user approves the mapping from
  mathematical object to module.
- Dirty target worktree → stop and report. Never mutate an unclean repository.
- Migration is `git mv` in its own separate commit, before any new code.
- Never flatten an organized subtree. A product folder with the right shape and
  the wrong name is one rename, not one move per file.
- A migration is not finished until the references move with it. Moves break
  paths exactly as renames do. Present `referenceUpdates` alongside the moves
  and never apply one without the other.
- Rewrite only what is unambiguous; report the rest. A path the skill cannot
  remap safely belongs in `staleReferences`, not in a guessed substitution.
- Clone with `GIT_LFS_SKIP_SMUDGE=1` **and** persist the skip in the clone's
  local config. Pointers are enough to reorganize; the env var only covers the
  clone, so any later checkout or reset re-downloads gigabytes and burns the
  LFS quota.
- **And then say which files are placeholders, and what they would cost.** `env`
  reports them right after the clone — precisely when a repository full of pointers
  looks complete — and `verify` repeats it on every later pass, because the one thing
  worse than not knowing is forgetting. Each pointer states the real file's size, so
  the report carries a total rather than a warning. Treat every one as missing
  material: nothing in the flow reads them, no test or notebook is written against
  them, and a failure to load one is reported as an absent file rather than a corrupt
  one, because the error it actually raises names the file format and never the
  reason.
- **There is no free route, and saying otherwise is worse than the cost.** Every
  download counts against the repository owner's bandwidth — the command, the web
  interface's download button, even a source archive that happens to contain those
  objects. Clicking download in a browser costs exactly what fetching them costs.
  Report that plainly whenever the subject comes up, because the belief that the
  browser is free is the one that gets a month's allowance spent by accident.
  **Fetching is the user's decision and is never taken for them**: the command is
  printed, never run.
- **Before spending it, say where the material might come from instead.** `probe`
  already reads how the repository gets hold of what it works on — a download, a
  clone, an archive, a mounted directory. Material the repository fetches by itself
  costs nothing, and anything training produced can be produced again. A quota is
  spent only on what genuinely exists nowhere else.
- Every test of the implementation lives in the target repository and nowhere
  else. The forge's own `tests/` cover the forge's tooling — the deliberation
  engine, the ingestion helpers — and never the materialized proposal. Deleting
  the target deletes its tests, and the next implementation starts without any:
  that is the intended consequence, not an accident.
- `tests/*.py` is the source of truth and is fail-closed. The notebook is the
  executed report, never the only place a claim is checked.
- A green result means something only when red was reachable. Two ways it is
  not: an assertion that cannot fail — never compare an expression with itself,
  in an assert or in the counter feeding one, and never assert a constant — and
  a remedy test that measures its own proposal without ever exercising the
  declared formulation it corrects. `verify` reports them as
  `trivialAssertions` and `remediesWithoutControl`.
- Every remedy test carries both poles: the remedy satisfies the criterion AND
  the declared formulation fails it. One pole alone cannot distinguish an
  improvement from a measurement that would have passed anything.
- When probing a guard adversarially, assert that the fixture actually changed
  before believing the result. A negative test whose mutation silently failed
  reports success while testing nothing.
- Check that a thing works, not that it is there. A notebook that exists but was
  never run is a claim, not a report; `verify` reads its `execution_count` and
  its error outputs and says `stale`, `errored` or `executed`.
- `verify` reads; it never executes a test. It proves the code *says* what it
  should — the revision it is bound to, an invariant declared for every claim, a
  matching test for every invariant, no assertion that cannot fail. Only running
  the suite proves the code *does* it. Never treat a clean `verify` as a green
  repository, and never compare, benchmark or publish from one that was not run.
- Every module under `src/<Name>/` declares `__provenance__`; every id in its
  `invariants` has a matching `test_<id>`. No provenance, no merge. The one
  exception is the kit's own seal, `src/<Package>/report_digest.py`: it
  implements no claim, so `verify` does not list it under `missingProvenance`
  while its bytes are still the kit's (today's kit source, or the bytes the
  scaffold receipt recorded writing). A modified copy is read like any other
  module and reported. Never stamp a provenance on it.
- Never fabricate mathematics. A test whose claim is not traceable to the
  proposal does not belong in the suite.
- **A sentence ages without anything failing.** Every other check here reads a
  declaration or a file; the docstrings and comments that say what the code does
  are read by nobody, so a rename leaves the old symbol named in the paragraph
  beside it and a new revision leaves the old one in a heading that still says
  which revision was verified. `verify` reports `prose` with the two that can be
  settled without interpreting anyone: `staleRevisions`, a managed revision named
  in prose that is not the current one — the pattern derived from the revision
  handed in, never from a naming convention this skill would have to know — and
  `unresolvedSymbols`, a token shaped like a symbol that resolves to nothing under
  `src/`. In a checklist holder (this skill's and every sibling skill's declared
  filename) neither check reads what the engine wrote: the position block's
  opener and closer lines, the `` `test_<id>` `` witness token `settle` puts at the
  end of an agreement line, and the append-only `## Reversed` section. An
  agreement's own text and every other line of the holder are still read.

  **Both are reported and neither drifts a status.** A historical mention is
  legitimate and common: *"the bound r16 adopted"* is a fact about when, not a
  claim gone stale. A configuration key quoted like a symbol is not a defect
  either. Telling those apart is a reading, and a check that guessed would spend
  its credibility on the wrong ones — so it hands over the list and the reader
  judges.

  What neither can do is judge a claim about behaviour. *"Nothing here is
  modified"* ages exactly the same way and would need an assertion parsed out of a
  sentence, in whichever language its author wrote it. That one is caught by
  reading, and saying so is better than a check that pretends otherwise.
- **Never assert an absence you did not go looking for.** "There is no bootstrap",
  "that cannot be obtained", "the prior work has no data layer" are claims about the
  whole repository, and a reading that stopped at one file cannot support any of them.
  Before saying something is missing, look where it would live — and if the answer
  still is nothing, say where you looked, so the user can point at the place you did
  not. A plausible reason invented to explain what you failed to find is worse than
  saying you did not find it: it sounds like a finding and gets acted on like one.
- Audit the mathematics, not the code. A finding is an ill-formed term, a claim
  stated more strongly than the construction supports, a missing complement, or
  a constant that does not hold up.
- No finding without a remedy, and no remedy without validation. Both are
  measured over the same randomized sweep of 200 configurations.
- Classify every finding. `theorem` demands the full sweep; `tendency` must
  declare its measured rate and must never be asserted as a law.
- Rule on admissibility BEFORE measuring efficacy, never after. Run `admit`
  first: every equation a remedy cites must exist in the revision, and every
  symbol it relies on must be declared in `uses` and present there. Measuring a
  remedy that fails this produces numbers that read as evidence and lend the
  sweep's rigour to something that should never have reached the bench. The
  remedy suite refuses to run without the ruling.
- Notation the remedy would add goes in `introduces`. A non-empty `introduces`
  is admissible but makes the audit `needs-deliberation` — never `ok`. Adding
  notation is the deliberation's decision, not this skill's.
- Remedies live in `tests/`, never in `src/`. Establishing that a correction is
  sound is not the same as adopting it.
- This skill proposes; `proposal-deliberation` decides and publishes. Never
  write to `proposals/`. `handoff` hands the open findings over sized by their
  reach into the document: a remedy touching one equation, adding no notation
  and cited nowhere else settles inline; anything wider comes back as a prompt
  for a session of its own, because a change with implications deserves
  unhurried deliberation rather than a decision taken in passing.
- A remedy settles inline only if the finding declares `remedy_block`: the
  corrected equation written out, with the same `\tag{n}`. Prose is not a
  correction. Without it the reach may be local but the handoff still defers —
  writing the mathematics is the work, and nothing here paraphrases a
  description into a document. `verify` lists these under
  `audit.localRemediesNotWritten` so the omission is a decision, not a silence.
- A defect that lives in the prose rather than in a numbered equation (an
  overstated sentence, a term used before it is defined) is still a finding:
  declare `"remedy_in_prose": True` with `remedy_equations` left empty and no
  `remedy_block`. There is no `\tag{n}` to substitute at, so `verify` never
  lists it under `localRemediesNotWritten`, it never settles inline, and
  `handoff` defers it as `prose-remedy` to a deliberation session of its own,
  where the new wording is decided. It still owes `uses`, `adoption`, its
  `test_finding_<id>` and its `test_remedy_<id>`; `admit` rules it
  inadmissible if it also names remedy equations, or if the flag is anything
  but `True`. Without the flag an empty `remedy_equations` reads as before
  (`remedy-locus-missing`) and fails the kit's `test_audit.py`.
- To settle one inline, drive `proposal-deliberation` with the item's
  `deliberation` payload: `RESOLVE_TARGET` with its `selectedEntryId` returns
  the entry's `text`; pipe that text into `implementation_cli.py compose
  --finding <id> --entry-text -`; send the returned `replacementText` as a
  `replace` decision to `CREATE_SUCCESSOR`. Composition substitutes inside the
  entry rather than handing back the bare block, because an entry usually holds
  more than the one equation and replacing it wholesale would delete the rest.
- Adoption is read from the published revision, never assumed. The reliable
  signal is that the text the remedy replaces is gone; if nothing recognizable
  took its place the state is `changed-unrecognized` and a human confirms.
- An adopted remedy stops being a proposal and becomes the formulation, so it
  moves: its remedy test retires, its claim lands in the invariant suite as
  `test_<becomes_invariant>`, and the module implementing it declares that
  invariant. Until it does, `audit` stays `incomplete` — leaving it in the
  remedy suite would keep reporting a defect the revision no longer has, and
  would keep its claim outside the contract every other claim is held to.
- Adoption is terminal, and every reader agrees on it. An adopted finding stays
  in `tests/findings.py` with its `test_finding_<id>` as evidence; it is never
  listed in `remediesWithoutValidation`, never counts as introducing notation,
  and `admit --revision <successor>` rules it admissible with an `adopted`
  verdict naming the revision. What it still owes is only the move above, so
  the audit reaches `ok` without deleting anything. `changed-unrecognized` is
  not adoption: `admit` keeps it inadmissible until a human confirms.
- Comparison against a baseline happens only after the implementation is faithful
  and only through `probe`, never improvised mid-implementation. It reports
  `nextStep` and that order is binding: an implementation computing with numpy
  cannot be trained at all, so the PyTorch conversion is settled before a
  comparison is discussed. See [Conversion, then benchmark](#conversion-then-benchmark).
- A result is never reported as more than the bounds it was obtained under, and a
  winner is never declared from two bare means. Both settings — the fast unit-free
  sweep and the trained run over real material — carry those bounds beside their
  numbers and grant a verdict only past the combined standard error.
- **And below a declared floor of repetitions, no verdict at all.** With one
  repetition the dispersion is zero and the threshold is zero, so the rule that
  exists to suppress noise declares a winner on every row instead. Stamp the reason
  and print the table; never suppress it, because the pilot has to run the same code
  the campaign will.
- **Every rule that governs a measurement governs every statement derived from
  it.** A number is checked and then a sentence is written about it, and the
  sentence is where the rules quietly stop being applied — the same pooling that
  would be caught in a table passes unnoticed inside the line that summarizes it.
  Whatever is computed from a measurement is bound by the measurement's rules: its
  bounds, its dispersion, its pairing, its floor. A derived statement that breaks
  one of them is worse than no statement, because it arrives with the authority of
  the measurement it contradicts.
- **Every aggregation names the axis it collapses, and collapses one.** Folding a
  second axis without saying so produces something that reads like the first:
  repetitions laid end to end read as one long run, settings averaged together read
  as one setting, instances pooled read as subjects. The failure is silent by
  construction — the output has the right shape and the wrong meaning — so the axis
  is declared where the aggregation happens, and anything that would flatten two is
  refused rather than explained afterwards.
- **Equalize what is drawn, not only what the arms touch.** Panels that differ in
  how many points they carry differ in something nobody declared, and the eye reads
  density as coverage. Two arms measured in different statistical units do not
  become comparable by being placed side by side; either the figure puts them in a
  space they both have, or it does not put them together.
- **When a figure's composition rests on a claim about the data, the code that
  draws it measures that claim.** "These two panels would show the same thing" and
  "this column is redundant" are measurements wearing the clothes of a design
  decision. Left as beliefs they are never revisited and quietly stop being true;
  measured by the drawing code, the figure adjusts itself and says why.
- **A finding is explained in the language the user is speaking**, in a neutral
  professional register. Identifiers, equation numbers, record keys and code stay
  as they are — they are a data contract. What is being handed over is a judgement
  about their mathematics, and a judgement nobody can read has not been handed over.
- The benchmark lives in its own package beside the method's, never inside it. A
  harness declares no `__provenance__` because it implements no equation, and
  stamping one on it to satisfy the check empties the check.
- **An arm calls the method's modules; it never reimplements them.** The harness
  implements no equation, so every equation it exercises comes from `src/<Package>/`
  — and the arm that writes the term inline instead has silently forked the
  formulation. The fork is invisible to everything else here: the module still
  declares its sections, the arm still declares the same ones, and the two documents
  are read separately and both come back clean. `verify` crosses that join and reports
  `unreachedModules`; `probe` answers `wiring-first` rather than offering the run.

  It goes wrong quietly and in one direction. The inline version starts as a
  defensible simplification — a stabilizer dropped, a constant folded away, a
  reduction that was equivalent at the time — and it is written down as a description
  rather than as a finding. Then the revision moves, the module moves with it, and the
  arm does not. What was a rounding difference becomes the whole term, and every
  number in the campaign was measured on mathematics the proposal no longer states.
- **The baseline is used as it is; the method is used as its proposal states.** These
  are not in tension and must not be traded against each other. Prior work is never
  edited to fit the comparison, and the new method is never held to the prior work's
  simplifications to keep the two looking alike. Where computing each side as stated
  makes something the arms share stop lining up, that is a real consequence to be
  measured and declared — never a reason to compute the method differently from its
  own formulation, because what the proposal adds is often exactly what the comparison
  exists to show, and dropping it to keep the sides symmetric deletes the result.
- **And a rule nothing verifies is a rule that quietly stops holding.** Prior work
  sits under `src/` beside the method, and every other check walked past it: not the
  structure, not the provenance, not the stamp that ties a report to its code. So it
  could be edited in any session and the next one would open a repository that says
  nothing happened. `priorWork` reports what changed, and reports it whatever the
  answer, because a check that speaks only on failure teaches nobody what it watches.

  **Report the fact, then say whether it reaches the run.** "Prior work changed" on
  its own goes red for good in a repository that legitimately evolves, and a check
  that is always red is one nobody reads. `reaching` is the half that decides
  whether anyone must act: the benchmark imports from prior work — that is what
  makes it a comparison — so a change to a module an arm imports moves what that arm
  computes and the record is stale, while a change to a training loop the benchmark
  never calls moves nothing here and may still matter to prior work's own notebooks.

  **What is there comes from the disk; only what is *recorded* comes from Git.**
  `modules` and `imported` are enumerated from the filesystem, because *does this
  exist* and *does an arm import it* are the filesystem's questions and answering
  them from the index makes an ignored-but-used module vanish — Git says nothing
  about an ignored path, so a prior-work module that runs on every call would be
  reported as absent and the whole check would come back clean. Git answers the one
  question only it can, and `recordStatus` says whether it could answer at all, so
  an unreadable record reports `unknown` and never passes for a clean one.

  `untrackedImported` is what falls out of asking both: a module present on this
  disk, imported by an arm, and outside the record. Whether it is ignored or merely
  never added is the ignore rules' business; what matters is that an arm computes
  with something nobody else receives, so the comparison cannot be reproduced from
  what was committed.

  Correcting prior work is a session of its own. This says the boundary was crossed;
  it never crosses it.

  **`priorWork` and the report's stamp will disagree, and the pairing is declared
  rather than a defect.** The stamp covers all of `src/` on purpose: it is computed
  twice, once by the notebook and once by the verification, and any rule subtler
  than a directory is a rule two implementations can drift apart on — and a stamp
  whose halves disagree protects nothing. So a change to prior work the benchmark
  never imports marks every report stale while `reaching` stays empty. Both are
  true and they answer different questions. Say the combination out loud: nothing
  an arm computes moved, the numbers still stand, and the stamp needs a re-run to
  agree with the tree. Left unsaid, somebody spends a campaign on a comment.
- Two arms differ in what they compute **and in everything they touch**. Shared
  mutable state — running statistics, caches, how much of the generator each
  consumes — is a difference nobody declared, and a rung that ignores it credits a
  term with what the exposure did.
- **Never credit a mechanism without trying to take the credit away.** When a
  difference is attributed to something, switch that something off and re-run. Two
  runs settle what an argument cannot, and they happen before the claim is written
  down, not after somebody doubts it.
- A run below the scale the protocol declares is a **pilot**, and its numbers are
  never quoted as results — not in the report, not in the summary, not in
  conversation. Only an explicit authorization releases the full run: not a clean
  verification, not a green pilot, not the agent's own conclusion that it is ready.
  Green is not permission.
- **The checklist is made of the agreements, not of the plan of work.** Every design
  decision reached in conversation becomes an item that gets ticked off. A checklist
  derived from how the agent intends to build can be completed in full while an
  agreement never reaches the code, and nothing anywhere will say so — the omission
  arrives as a silence, and silences are not read.
- **A decision already agreed is never re-decided while implementing.** When the work
  runs into something that makes it awkward — a dependency that is not installed, a
  thing easier to print than to draw, an interface that does not fit — that is not a
  detail to resolve in passing. Say it plainly: this was agreed, this is what blocks
  it, this is what I would put in its place, this is what the substitution costs. Then
  wait. A change mentioned inside a progress report reads as housekeeping and gets
  nodded through, and afterwards nobody decided it.
- **And when something agreed turns out to be missing, find out when it went missing
  before explaining why.** A reconstruction that sounds coherent is worse than "I have
  not checked yet": it lands as a finding and gets acted on like one. The rule against
  asserting an absence nobody looked for applies to the session's own history exactly
  as it applies to a repository.
- **When a rule joins two ends — something writes, something reads — the check has to
  cross the join.** Testing each side against a fixture you wrote yourself verifies
  both halves and never the connection, which is the only thing the rule was about.
  The fixture always passes: the same hand wrote it and reads it. Run the thing, then
  ask the tool what it sees.
- **Revision drift is sized by reach, not only located.** Some changes are local — an
  equation gains a stabilizer, a constant moves — and the implementation adjusts.
  Others change what the experiment *is*: what is predicted, over which statistical
  unit, what counts as correct. Those do not oblige an adjustment, they oblige a new
  protocol, and every result, checkpoint and dimension stops meaning anything rather
  than merely going stale. Never adjust the code and re-run without ruling on which of
  the two it is; a table of the old metric computed over the new formulation is
  arithmetically correct and answers a question that no longer exists.
- **Saved models are verified like everything else.** They carry the revision they
  were trained under in their manifest, so it gets read. A checkpoint from an earlier
  revision is named as such and never analysed silently beside current ones.
- **The inspection enumerates from the disk, not from the index.** *Does this exist*
  is the filesystem's question; *is this part of the record* is the ignore rules'.
  Answering both with the list of committed files makes "not added yet" mean the same
  as "deliberately excluded", and a misplaced module then gets reported after it has
  entered the history instead of before. Both sources are local: no inspection has any
  business depending on a remote, and none does.

## Target layout

```
<repo>/
├── <Name>/                    Notebooks/  Data/ (only if data exists)  Results/  Models/
├── src/<Package>/             the implementation (.py), one module per mathematical object
├── src/<Package>_Benchmark/   the harness: configuration, material, wiring, verdict
├── tests/                     smoke, invariants, synthetic, findings + audit + remedies
├── tools/ (only if needed)    launches and operates runs; implements no equation
└── pyproject.toml             isolation marker: anchors pytest/ruff to this repo
```

`<Name>` is chosen by the user. `<Package>` is its importable form: a hyphen is
legal in a directory but not in a Python identifier, so `Example-Method/` pairs with
`src/Example_Method/`. Never scaffold `src/<Name>/` when the two differ — nothing
could import it. Pre-existing code moves to its own package under `src/`, never
into `src/<Package>/`. `pyproject.toml` must carry
`[tool.pytest.ini_options]` with `pythonpath = ["src"]`: without it the suite
cannot import the package offline, and an existing file that lacks the table
counts as a gap, not as compliance.

**The benchmark is a sibling package, never a subfolder of the method's.** Two rules
already in force decide this between them, and there is exactly one place left that
satisfies both: `verify` recurses into `src/<Package>/` demanding `__provenance__`
from every module, and it counts any tracked `.py` outside `src/` and `tests/` as a
stray module. So a harness beside the notebooks breaks the structure at the first
commit, and a harness inside the method's package breaks the fidelity — unless
somebody stamps a provenance on it, which is worse than either: provenance says
"this module implements these equations", a harness implements none, and falsifying
it hollows out the one check that keeps the code tied to the mathematics.

Nothing in the benchmark package is part of the formulation. Deleting it leaves the
method intact, which is the property the name is promising.

**And `tools/` exists for the same reason, reached the same way.** A script that
wires this repository into a run — declaring which backend it hands work to,
and at what capacity — has nowhere else to go. Not the method's package: it
implements no equation, so it could only sit there by declaring a
`__provenance__` it has no right to, and that is the falsified stamp the
paragraph above refuses. Not the benchmark's package: that one trains and
measures, and declaring a backend is neither. And not untracked, because then
the configuration of a run that costs hours lives on one disk and no later
session can reproduce how it was launched. No place existed for that
declaration, and that absence is the argument for naming one. The launching
machinery itself — the part identical for every repository — has since moved
to the forge's `remote-execution` skill; the revocation note further below
records what moved and why.

**What puts anything there is a command, not a template.** `remote_cli generate-job`
writes a job folder at `tools/<service>/<job-name>/` — a `run-config.json` pinning
the commit, the clone paths and the entry point, beside the runner the service
executes. That is the exact shape the admission guard accepts, so nothing here
scaffolds a `tools/` template and nothing here invents a second one: the directory
exists because a generated job needs somewhere to live, and the generator is what
decides its contents.

It is a named place and not an amnesty. A `.py` loose at the top of the repository
is still a stray module. And nothing under `tools/` is ever asked for a
provenance, because the scan only ever recurses into `src/<Package>/` — which is
exactly what stops a launcher from being able to claim it implements anything.

## Decision Gates

| Situation | Action |
| --- | --- |
| No repository yet | Ask: create new, or clone an existing URL |
| Repository empty | Scaffold the layout directly; no migration commit |
| Layout already compliant, code present | Verification mode only |
| Layout drift | `plan` → present the map → user approves → `apply` |
| Product folder right shape, wrong name | `plan` proposes one rename; subtrees stay intact |
| Plan reports `referenceUpdates` | Show them; `apply` rewrites them in the same commit |
| `verify` reports `staleReferences` | A path points nowhere: report before writing any code |
| Plan reports `unclassified` or `conflicts` | Ask where those files belong; never guess |
| `verify` reports structure drift | Report it as its own finding, ask before fixing |
| `verify` reports stale modules | Report revision drift separately; ask before rewriting |
| `verify` reports `unreachedModules` | An arm declares mathematics it never calls: report before any run |
| `verify` reports a non-empty `structure.scaffoldGaps`/`objectGaps`/`harnessGaps` | Kit destinations this skill ships are absent from the repository. `structure.resolve` publishes one entry per gap key that names anything, each naming the exact `materialize --stage` that writes them and the exact files it would write, with a `discuss` command that runs unedited. It is a question and not the command on purpose: `--plan` is an approval a human gives, and a published command that generated its own approval would answer the gate instead of passing it; `--seed` is the number the scaffolded experiment draws from, which no skill may choose for a repository |
| `verify` reports `fidelity: "undeclared"` | The Benchmark package exists and every block of `__benchmark__` is still at its scaffolded empty value: fill the declaration before quoting any fidelity result, because nothing measured against it has been checked yet |
| `probe` reports `nextStep: "declare-first"` | The benchmark package exists (a comparison was already accepted) but every block of `__benchmark__` is still at its scaffolded empty value: report before offering a run built on a declaration that has not happened. A target with no benchmark package at all does not reach this row — see `nextStep: "benchmark"`/`"validate"`/`"declined"` below |
| `probe` reports `nextStep: "poll-first"` | A submission is already out to a remote worker with no result back yet: report before offering another run |
| `probe` reports `nextStep: "search-first"` | A declared search's record is absent from disk: the run has no chosen configuration yet, report before offering it |
| `probe` reports `nextStep: "pilot-first"` | The flow the target declared has steps that have not finished at pilot — `pilotCompleteness.incomplete` names them, ordinal-carrying and ordinal-less alike: report those, and never the declared scale, because nothing has been produced yet for anybody to read |
| `probe` reports `nextStep: "pilot-decisions"` | The flow finished at pilot and each of its steps now owes its own decision about how the full run carries it: publish the per-step questions, read `remoteExecution.necessity` beside them, and decide one step at a time. Show `report.liveFindings` first when it names anything — those decisions are taken over artefacts that carry live findings, and the acknowledgement holds this rung until it is answered |
| `probe` reports a job with `smokeReady: false` | A job folder exists that no rehearsal has ever passed on its pinned commit: read it before offering a campaign, because a rehearsal finds cheaply what the long run would find expensively |
| `probe` reports a job whose `staleness` is `drift` | The repository moved past the commit that job is pinned to: regenerate the job, or say plainly that the run measures the older code, before offering a campaign |
| `probe` reports a job in `remoteExecution.notebookPilot.unpiloted` | That job would run a notebook this pilot never opened, so the artefact about to cost machine time has not been executed and read here first: name the notebook and say so before offering a campaign. Nothing refuses it — a repository may generate a job before it pilots, or send a different notebook on purpose — but a campaign offered without saying it is a campaign offered on an untested file |
| `probe`/`verify` report `remoteExecution: "drift"` | The ledger and the service no longer agree, or a stale result arrived: run `remote_cli reconcile` before reading anything else out of that ledger. Waiting fixes nothing. The state publishes its own exit now — `remoteExecution.resolve` carries the question and a `discuss` command that runs unedited. It is a question and not the command because `reconcile` requires `--worker` and `--backend`, and this section may print neither: a worker id is a service account's username (which is why `workers` is a count) and a backend name is a service name |
| `probe`/`verify` report `remoteExecution: "unreliable"` | A line of the ledger could not be read, so nothing about what is out there is trustworthy: run `remote_cli reconcile` and report what it finds before offering a run. `remoteExecution.resolve` publishes that question with a runnable `discuss` command, for the same reason and with the same limit as the row above |
| `verify`/`probe` report `position: "stale"` | The section's header is bound to a revision whose bytes no longer match: run `position` again to rebind it before trusting any tick on it |
| `verify`/`probe` report `position.disagreements` | A recorded mark contradicts its own measured evidence: report before gating or closing anything on it, and run `position` to correct it |
| `verify`/`probe`/`position` report `position.unbacked` | A mark is ticked and nothing measured it: an assertion, not a reading, and `gate`/`close` refuse on it. **A refresh does not clear it** — `position` deliberately never rewrites a mark it could not measure, which is what makes a derived mark worth reading. The exit is a reinstall of the same sequence (`--sequence - --replace`), which installs every item blank and re-derives it in the same call, so measured marks come straight back and only the assertions go. Run `position` and paste the `resolve.command` it prints: the array that command consumes is already inside it, so it runs unedited. `verify` and `probe` report the finding and publish no command for it — a `position` write is stamped with the caller's own `--session`, and neither of those commands carries one to stamp |
| `gate` refuses `POSITION_DISAGREES` | A ticked sequence item disagrees with its own witness's measurement — the same fact the `position.disagreements` row above reports, refused here specifically because the tick is a launch's own premise. Remedy is identical: run `position` to correct it, then gate again. Never a blank, unreconciled item — that direction is honest, not a false claim, and does not refuse |
| `position` refuses `POSITION_HOLDER_MOVED` | The holder document changed between the read that located its section and this write: re-run the command that measures the section fresh, never retry blind against offsets that were computed against bytes no longer on disk |
| `gate` refuses `NOT_READY` | No passing rehearsal is on file for this job at its current pin — or, for a campaign (`--unit`), for one of the workers its `propose` record names, each of which the refusal names: rehearse it first, on every worker named — readiness cannot be asserted, only measured |
| `gate` or `launch-plan` refuses `JOB_SERVICE_AMBIGUOUS` | Folders of this job name sit under more than one service, so the job alone does not say which one: pass `--service <service>`, the `service` the step declares — never pick one by default |
| `offer` refuses `OFFER_UNANSWERED` | No `--answer` was supplied on this call — required every call, never read back from a prior one: pass `--answer yes` or `--answer no` before an action set can be published |
| `gate` refuses `GATE_AUTHORIZATION_REQUIRED`/`_UNKNOWN`/`_MISMATCH`/`_STALE`/`_CONSUMED` | `--authorization <token>` is missing, names nothing on the ledger, was minted for a different job or unit list, was minted against a pin/entrypoint/rung/revision/position status that has since moved, or already authorized one successful `gate` call: publish (or re-publish) with `offer` first, then gate with the token its `launch` action names. A stale token means a bound fact moved, never that time passed |
| `priorWork` reports `modified` | Say what changed and that correcting prior work belongs to a session of its own |
| `priorWork` reports `reaching` | The change moves what an arm computes: the record is stale, report before any run |
| `search` reports `incomplete` | A value is chosen by outcome and the search does not say enough about itself to be an experiment: report before quoting anything it chose |
| `distribution` reports `incomplete` | A run is split and does not say enough about the split to still be one run: report before merging anything |
| Target outside `implementations/`, or dirty tree | Refuse and report the guard |

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
  approved protocol (the experiments revision, once one exists) and the
  declared pilot; nothing guesses it.
- **The estimate.** `estimate --timing <Name>/Results/timing.json --record
  <Name>` gives each stage (`poc`, `full`) a range per host, from the one
  formula that verb defines. A remote host reads `unmeasured` until a
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
- **Placement by measurement, never by default.** Before the proof of
  concept or the full run is placed, run `remote-parallelism`'s timing probe
  (`skills/remote-parallelism/scripts/timing_probe.py`, under the target's own
  interpreter against its epoch function) over the candidates: the local CPU
  with one process and with several processes, any local accelerator, each
  account's machine once its own rehearsal adds the row (a CPU-only session
  included), and the batch, loader and thread settings. Then run `plan
  --timing <Name>/Results/timing.json --record <Name>` with the team's
  accounts. `plan` compares CPU against GPU and local against cloud, counts
  local processes and the parallelism of several accounts, and recommends an
  accelerator only when it was measured faster or cheaper: a GPU is never by
  default. A candidate that reads `unmeasured` is measured before it is
  chosen, never assumed. A remote CPU-only session is generated with
  `generate-job --accelerator-kind cpu`. When loading dominates an epoch, the
  plan's representation advice (a cached preprocessed form of the data) goes
  to the operator. The plan, like the estimate, is never authorization.
- **What it is.** A measurement-derived range (±20%, single-probe
  extrapolation), never a promise, and never authorization: the pilot and the
  launch stay the operator's to approve after reading it.

## Every remote unit fits one session, or resumes

A service stops a session after its continuous run limit, and whatever was not
written out by then is lost with the hours it cost. So every remote unit fits
one session within the 80% margin (`schedule` and `assess` refuse
`unit-over-session-margin` otherwise), or its step is declared resumable from a
checkpoint. The target reads `FORGE_SESSION_DEADLINE` (epoch seconds), writes
its checkpoint and starts no new unit or trial past it, then exits cleanly.
A unit that does not fit is split along the declared axis — fold, seed,
subject block, never by arm — or resumed over chained sessions on the same
account. After a cut session, run `fetch` (it keeps the partial result), then
`remaining`, and send again only the units it lists. A checkpoint reaches the
next session as follows: on a kernel service, the previous kernel's output
attached to the next kernel through `kernel_sources` and read under its input
root at `notebooks/<owner>/<slug>/` (checked on a live account on 2026-10-27).
papersmith attaches it automatically for the paths the job declares with
`generate-job --carry-path`: `submit` places the continuation on the account
that produced the checkpoint (`--no-carry` starts it fresh instead), and the
runner restores those paths before the entrypoint and exports
`FORGE_CARRY_IN`, so the target code is unchanged. On Colab nothing is carried
automatically (`carry: unsupported`); upload the checkpoint into the new
session. The details live in
`skills/remote-execution/SKILL.md`, **Sessions, checkpoints and
resume**, and `skills/remote-parallelism/SKILL.md`.

A job that reads a public dataset declares it with `generate-job
--input-dataset <owner>/<slug>` (repeatable). A pushed kernel is a
non-interactive session and cannot attach a dataset at run time, so on a
kernel service `submit` names the declared datasets in the push and reports
`inputs: attached`; a service that attaches none reports `inputs:
unsupported`. Either way the runner exports `FORGE_INPUT_DATASETS` before the
entrypoint, a JSON object mapping each ref to its mounted directory or to
null: the target reads the mounted directory when there is one and downloads
the dataset only when the value is null. The details live in
`skills/remote-execution/SKILL.md`, **Job inputs**.

## Where to start: the repository is the memory

**Every invocation begins the same way — look at `src/` before asking anything.**
Nothing about a previous session is stored anywhere; the repository itself is the
record. An implementation sitting in `src/` is the evidence that this skill already
ran here, which means the layout question was already put to the user and answered.
Whether they accepted or declined it is not worth recovering: either way it is
settled, and asking again treats a decision as if it had never been made.

That state is *read*, never *remembered*. Nothing is carried forward except facts
about the repository as it is now, so nothing can drift out of date and nothing a
past session concluded can bias this one.

Route on **existence, not on fidelity**. Whether the implementation still matches the
latest revision is a measurement, and `verify` is what makes it — asking it here
would send a repository whose code is bound to `r14` while `latest` is `r16` through a
full first pass, re-implementing from scratch something that only needs bringing up to
date. Drift is Flow B's fourth step, not a reason to start over.

- **`src/` holds no implementation at all** → first pass. Run
  [Flow A](#flow-a--first-pass).
- **`src/` holds one, whatever revision it is bound to** → run
  [Flow B](#flow-b--every-later-pass), which measures the drift and handles it.

## Flow A — first pass

1. `node skills/proposal-deliberation/cli.mjs '{ "operation": "STATUS" }'` → take `latest`.
2. **Ask for the repository URL** and clone it:
   `GIT_LFS_SKIP_SMUDGE=1 git clone <url> implementations/<repo>` (or `git init`), pin the
   LFS skip in the clone's local config (see `references/usage.md`), then `env`.
   `env` adds `.venv/` and `*.egg-info/` to the clone's `.git/info/exclude`
   first, so its own products never leave the tree dirty for `plan`.
3. Install dev dependencies with the printed target `pip`, never the forge's.
4. **Is there prior work, and does its layout already comply?** Run `plan`. If
   `status` is `compliant`, go to step 6. Otherwise present every rename, move and
   reference update with its reason, and read `reorganization`:
   `decisionCount` is what the user actually reads: every move, every rename, every
   reference rewrite. `carriedFiles` is reported alongside it and is worth saying out
   loud — "this renames one folder and sweeps thirty-seven files with it" — but it is
   not what decides the branch. Renaming a folder of two hundred files is one line to
   read and one command to undo; counting those files would measure blast radius and
   call it reviewability, forcing a separate session for a trivial change.
   - **`scale: "reviewable"`** → **[GATE]** ask whether to reorganize. On approval,
     `apply` lands renames, moves and reference updates in one commit. On refusal,
     continue without touching the layout — that refusal needs no record, because
     the next session reads the tree, not a note about it.
   - **`scale: "large"`** → **do not apply it, even if the user says yes.** A list
     this long is approved without being read, and an unread approval is not one.
     Say so, and hand the user a self-contained prompt that performs exactly this
     reorganization in a separate session. Then continue without it.
5. **Fill every scaffold gap.** Run `materialize --stage scaffold --plan <path
   to the current plan> --seed <the suite's fixed seed>`. If step 4 ran `apply`,
   run `plan` again first and pass that new plan: `apply` carried out the old
   one (its moves and `createDirs`), so the old one is `PLAN_STALE` here by
   design (`references/usage.md`, "The plan, apply and materialize lifecycle"). `plan`'s
   `scaffoldFiles` and `verify`'s `structure.scaffoldGaps` report the same
   destinations — the table below, plus the two merge anchors
   (`.gitignore`, `pyproject.toml [tool.pytest.ini_options]`) when either is
   missing — and the command writes every one of them from the kit at
   `assets/kit/`, then records what it wrote in `<Name>/.implementation/
   materialization.json` — the receipt a later hand-edit is checked against
   (`SCAFFOLD_DRIFT`), and the reason a target scaffolded before this command
   existed reads `UNRECORDED_SCAFFOLD` until an operator runs `materialize
   --adopt <path>` on each of its scaffold destinations, deliberately, one at
   a time. The agent never copies these files by hand: a target `verify`
   reports incomplete after this command runs means the command refused, not
   that a row was skipped. `scripts/materialize.py` — the forge's own
   harness, never a step of Flow A — performs this exact mapping over the
   identical list (`scaffold_destinations`), so the test suite can examine a
   freshly scaffolded target the identical way: the rows marked `authored:`
   are written rather than copied, and the `.gitignore` is merged into
   whatever the repository already has instead of written over it.
   `src/<Package>_Benchmark/__init__.py` is **not** among these destinations —
   see [`nextStep: "declare-first"`](#nextstep-declare-first--the-benchmark-package-exists-and-says-nothing-yet).

   | Gap `plan` and `verify` report | Written from |
   | --- | --- |
   | `.gitignore (.venv/, __pycache__/, .ipynb_checkpoints/)` | authored: the entries a virtualenv inside the target needs kept out of the index, plus `*.egg-info/` (never a gap on its own) |
   | `pyproject.toml [tool.pytest.ini_options] pythonpath` | `assets/pyproject.template.toml`, or the anchor appended to the existing file |
   | `src/<Package>/__init__.py` | authored: exports the target's own modules (none yet), plus `__implementation__`/`__levels__`/`__steps__`/`__records__` prefilled empty, with guidance comments, awaiting step 8/9 |
   | `src/<Package>/report_digest.py` | `assets/kit/nb/report_digest.py` |
   | `src/<Package>/remote_stamp.py` | `assets/kit/nb/remote_stamp.py` |
   | `tests/test_smoke.py` | `assets/kit/tests/test_smoke.py` |
   | `tests/findings.py` | `assets/kit/tests/findings.py` |
   | `tests/conftest.py` | `assets/kit/tests/conftest.py` |
   | `tests/sweep.py` | `assets/kit/tests/sweep.py` |
   | `tests/admissibility.py` | `assets/kit/tests/admissibility.py` |
   | `tests/test_audit.py` | `assets/kit/tests/test_audit.py` |
   | `tests/test_remedies.py` | `assets/kit/tests/test_remedies.py` |
   | `tests/test_remote_readiness.py` | `assets/kit/tests/test_remote_readiness.py` |
   | `<Name>/Notebooks/verification.ipynb` | `assets/kit/nb/verification.ipynb` |

   `conftest.py`, `sweep.py` and `admissibility.py` declare no test of their own,
   and skipping them for that reason is what breaks the scaffold: `test_audit.py`
   and `test_remedies.py` both open by importing them, so a tree without them is
   not collected at all. `admissibility.py` belongs in `tests/` specifically —
   it reads the ruling from beside itself, which is where `admit` writes it.

   **Remote readiness ships with the scaffold.** `src/<Package>/remote_stamp.py`
   writes the `shard.json` that `remote-execution`'s `smoke record` reads:
   `write_shard(summary, directory=None, *, device=None)` writes it only when
   `FORGE_RUN_MODE` is set (the runner exports it around the call it makes),
   into the working directory unless `directory` names another, carrying
   `mode`, `evidence.commit` (the repository's `HEAD`, or `FORGE_CLONE_COMMIT`
   where git cannot answer: a code-bundle worker holds only `.git/HEAD`), `evidence.sourcesDigest`
   (the `report_digest.py` seal), `environment.device` (`{kind, name}`, from
   `device` or from `torch` when it is importable) and `runs` (the summary).
   Anywhere else it writes nothing and returns `None`. The target's smoke
   callable calls it once its work is done, or is decorated with `@stamped`,
   the scaffold's smoke template, which stamps whatever the smoke returns; pair it with `generate-job
   --smoke-required-evidence evidence.commit --smoke-required-evidence
   environment.device.kind`, so the smoke records only when the stamp
   carries both. Like the seal, it proves nothing and owes no
   `__provenance__` while its bytes are the kit's. `tests/test_remote_readiness.py`
   tests that stamp and carries `single_device()`, a guard that patches
   `torch.einsum`, `torch.matmul` and `@` to refuse operands on two devices.
   Set its `FORWARD` to a callable that builds the target's inputs on the
   device it is given and runs the forward: the test then runs it on
   `torch.device("meta")`, which needs no GPU but does not on its own refuse a
   CPU tensor mixed in. Until `FORWARD` is set that test skips and says what to
   fill in, and every torch test skips when torch is not installed.

   **Both kit notebooks open with a cell this skill does not own.** Its first
   code cell binds `ROOT`, every later cell reads it, and its bytes are a copy
   of `remote-execution`'s `assets/notebook_repo_root.py` — bound by a forge
   test that goes red the moment the two differ. Do not edit it here and do not
   re-answer that question further down the notebook. The reason lives in that
   skill: locating the repository two directories above the working directory
   is right on a person's own machine and wrong on a remote worker, where the
   kernel's working directory is the runner's own, the clone sits one level
   inside it, and two directories up names a directory that exists anyway — so
   the wrong tree goes on the path and the run dies much later naming a missing
   package rather than a wrong root. The cell reads a clone directory and a
   pinned commit from the environment when a runner exported them, proves the
   checkout is at that commit, refuses a half-exported pair, and falls back to
   the local layout only when nothing at all was handed over.

   `materialize --stage scaffold` substitutes the scaffold-time `{{TOKEN}}`
   placeholders (`{{PKG}}`, `{{SEED}}`, `{{NAME}}`, and `{{REVISION}}` once it
   is known — declared, or bound by `plan --revision`) itself; the step-9
   tokens are left standing on purpose, and `--stage objects` later fills the
   revision and the module name into scaffold files still exactly as written —
   see `references/usage.md` for the full token table and when each one is
   answered.
6. **Ask for the name.** Run `name --name "<whatever they typed>"` and show both
   forms it returns — the `<Name>/` directory and the `src/<Package>/` package —
   then **[GATE]** confirm before writing anything with them.
7. **[GATE] Ask for authorization to implement.** Nothing below writes code until
   this is given.
8. Present the object → module map, **and beside it the declaration's `revision`
   and `premises`**. Wait for approval. Only then write code, and write those two
   into `src/<Package>/__init__.py`'s `__implementation__` first — the method's
   own package, not the benchmark's: these two are facts about the method, and
   `src/<Package>_Benchmark/` is the comparison's own file. If the file does not
   exist yet (a target scaffolded before this literal existed), run `materialize
   --stage scaffold` first — it never overwrites what a target already has — then
   write `__implementation__` in beside `__all__`.

   Both are asked here rather than invented, and both have their answer already.
   `revision` is **proposed** as step 1's `latest` and confirmed inside this same
   approval — proposed, because a value taken silently is a value nobody agreed
   to, and a fabricated one binds the declaration to a revision that may not
   exist. `premises` is not new work either: the protocol the gate above was
   granted on already said what kind of prediction is assumed, over which
   statistical unit, by which metric and in which direction it is judged. Those
   four answers exist; what has never happened is anybody writing them down.
   Use the field names `authored_package_init`'s own template comment names —
   `prediction`, `statisticalUnit`, `metric`, `direction` — and carry the
   answers across unchanged.

   This is the same rule `AGREED.md` already states one section down: append
   at every gate, before writing any code the gate authorized. Recording what was
   agreed is part of the gate, not a chore that follows it. `__benchmark__`'s
   five blocks — `arms`, `search`, `report`, `distribution`, `entry` — are
   **not** filled here: they are read off the work as it happens, and step 9
   onward is where that happens.

   **Migrating a target scaffolded before this relocation.** A target whose
   `src/<Package>_Benchmark/__init__.py` still binds `revision`/`premises` at
   the old home refuses `OBJECT_MAP_AT_OLD_HOME`, naming both locations, rather
   than the plain `OBJECT_MAP_NOT_APPROVED` a target that never declared at all
   gets. The remedy uses mechanisms that already exist, once, by hand:
   1. `materialize --stage scaffold --plan <approved> --seed <seed>` — writes
      only what is missing; an authored `src/<Package>/__init__.py` is never
      overwritten.
   2. Move `revision` and `premises` (as `__implementation__`) and any of
      `__levels__`/`__steps__`/`__records__` the old file declares — **and any
      other top-level literal it carries, whether this skill reads it or not**
      — from `src/<Package>_Benchmark/__init__.py` into `src/<Package>/__init__.py`
      by hand, verbatim, comments and all. Leave `__benchmark__`'s remaining
      five blocks where they already are.
   3. `materialize --authored src/<Package>/__init__.py` — re-seals the edited
      scaffold destination so `SCAFFOLD_DRIFT` clears.
   4. Delete `src/<Package>_Benchmark/report_digest.py` if one is still there —
      a second copy of a file this skill's own doctrine refuses to keep twice.
   5. Re-execute the notebooks: the seal moved, so every prior stamp is stale
      by construction. Never hand-edit a stamp.
9. **Materialize the object scaffolding, then write one module per object with
   `__provenance__`, plus its invariant tests.** Run `materialize --stage objects
   --plan <path to the approved plan> --seed <the suite's fixed seed>`. It refuses
   `OBJECT_MAP_NOT_APPROVED` until step 8's `revision`/`premises` are recorded in
   `src/<Package>/__init__.py` — this stage cannot run before that gate.

   Pass `--module <name>` to write the first row under the name the approved
   map gives the module (`src/<Package>/<name>.py`); without it the stage
   writes `module.py`, and only while the package holds no module of its own.
   Once the map's modules exist, `structure.objectGaps` no longer names
   `module.py`.

   | Written into | Written from |
   | --- | --- |
   | `src/<Package>/<module>.py` | `assets/kit/src/module.py` |
   | `tests/test_invariants.py` | `assets/kit/tests/test_invariants.py` |
   | `tests/test_synthetic.py` | `assets/kit/tests/test_synthetic.py` |

   None of the three is a scaffold gap, and step 5's table does not name them on
   purpose: their tokens — `{{MODULE}}`, `{{FUNCTION_NAME}}`, `{{INVARIANT_ID}}`,
   `{{SECTION}}`, `{{EQUATION}}`, `{{EXPECTATION}}` — are answers to the map step 8
   has just approved, and nothing could have answered them before that.
   `materialize --stage objects` writes these three from the kit with
   `{{REVISION}}`, `{{NAME}}` and `{{MODULE}}` filled in and step 9's own tokens
   still standing inside identifiers — unlike the scaffold stage, this write is
   not gated on the result parsing, because nothing could make it parse yet; a
   test file still in that state fails as one item naming its placeholders. The
   same call fills the revision and the module name into the scaffold files
   that are still byte-identical to their receipt, and re-seals them.
   The agent authors the real module and tests over this scaffolding, then declares
   each path with `materialize --authored <path>` so `verify` stops reading it as
   drift. This is also why `tests/test_smoke.py`, which the scaffold does write,
   fails until this step runs: its `MODULES` names a module that does not exist yet.
   That failure is the question being asked, not a defect to suppress.
10. Audit: sweep 200 configurations, declare each finding in `tests/findings.py`
    with its kind, status, measured rate and proposed remedy.
11. `admit --revision <latest>`: rule on admissibility before anything is
    measured. Only admitted remedies proceed. When the audit found nothing,
    `FINDINGS = []` refuses `NO_FINDINGS` until that outcome is recorded
    explicitly with `admit --revision <latest> --no-findings`; only then does
    `verify` read the audit as `ok` instead of `none`.
12. Validate every admitted remedy over the same sweep: it must resolve its
    finding and preserve the properties already established.
13. **Report the findings and say what they cost to establish.** For each one:
    what is wrong, what the remedy is, and that it was **detected over 200
    configurations and confirmed over the same 200**. A remedy presented without
    that number reads as an opinion; it is a measurement, and the user is entitled
    to know it before authorizing anything.
14. **[GATE] Ask for authorization to apply the corrections to the proposal and to
    the code.** On approval this session drives the deliberation engine itself:
    `handoff` sizes each finding, `RESOLVE_TARGET` locates the entry, `compose`
    builds the replacement, and `CREATE_SUCCESSOR` publishes the next revision.
    See `references/usage.md`. Publishing advances the user's real lineage, so it
    happens only behind this gate.
15. Run the suite with the target interpreter, then execute the notebook —
    with the target venv's `bin` prepended to `PATH`, not merely as the
    interpreter that launches jupyter. See "Executing a notebook needs
    `PATH`, not just the right `python`" under Non-negotiable isolation:
    the kernelspec resolves a bare `python` off `PATH` at kernel start, so
    the obvious invocation runs the cells under a foreign interpreter and
    says nothing about having done so.
16. **Final check.** `verify --revision <latest>` → report `structure`, `fidelity`,
    `audit` and `validation`.
    - `--revision` is optional and pins the check. Omitted, `verify` discovers the
      newest revision of the family the bench itself declares, and `fidelity`
      reports which it used under `latestRevision` with `revisionSource` naming
      how it got there — `argument`, `discovered`, or `none` when there was
      nothing to discover from. Prefer omitting it: a revision you pass is a
      revision you asserted, and asserting the one the bench is already bound to
      is how a bench built against an older revision reads as current.
    - Discovery considers only **published** revisions. A revision is published
      when the deliberation skill wrote the artifact marker as the file's first
      bytes; a draft, an export or a copy left in the same directory carries no
      marker and is passed over, because marking every module stale against a
      document nobody published is drift the tool invented. The rule is the
      marker and never a filename shape: if any candidate of the family carries
      it, `fidelity.markerOwned` is `true` and every unmarked candidate is named
      in `fidelity.nonManagedCandidates`; if none does, resolution is unchanged
      and `markerOwned` is `false`, so a hand-authored family still works. Two
      candidates that tie are listed in `fidelity.revisionTie` rather than
      decided in silence. All three are reported and none of them refuses —
      report what was passed over, and let the user say whether it matters.
    - **Not faithful** → correct the code and re-enter from step 15. **At most
      three passes.** If the third still is not faithful, stop and hand the user
      the decision, with what the three attempts established. A loop with no bound
      does not fail — it keeps trying, and nobody notices.
    - **Faithful** → **do not stop here.** Continue into Flow B step 3: the
      repository is now in exactly the state a later invocation would find, so it
      gets the same answer. Ending here would make the reply depend on how the user
      arrived rather than on what the repository holds, and would leave them to
      re-invoke just to be told what comes next. `probe` is read-only and instant;
      what it reports is a question, not work, and the gate is where they stop.
    - **Then `close`.** `close --revision <latest> --session <your-session-id>` —
      writing the position becomes a precondition of finishing, not a courtesy.
      It refuses `POSITION_ABSENT`, `POSITION_STALE` or `POSITION_DISAGREES` and
      names which one, rather than ending a session with the position still only
      in the agent's own memory. A position is owed only once the target declares
      a flow (`__levels__`, `__steps__`, `__records__`, a shard root or a job
      folder): a proposal-only target closes without one and the response says
      `positionOwed: false`. An agreement no test could ever witness (a scoping
      decision, a premise, a deferral) is closed by asking the operator whether
      it is closed and why, then `settle --done --unwitnessed --reason "<their
      reason>" --text "<line>"` — recorded as a decision under
      `agreements.witness.decided`, never counted as witnessed. Never tick one
      by hand. When the line does not exist yet, put it in first with `settle
      --under "## Ladder" --unwitnessed --reason "<why>" --text "<line>"` (no
      `--about`, no discussion), never by hand.

## How a gate is asked

**Speak the language the user is speaking.** The repository, the code, the commits and
every file written stay in English; the conversation does not. A skill that answers a
Spanish session in English has changed the subject.

**And speak plainly.** Command names, JSON fields and status codes are this skill's
plumbing, not the user's. Say what was found and what it means; name a command only
when the user has to run it themselves.

**The subject is the plan of work, not the mathematics and not the code.** When
proposing how something will be built or measured, what the user is judging is the
sequence and the friction: what gets built, in what order, what has to meet what, and
where the two sides do not fit. Not equations, not identifiers.

They wrote the code once and can no longer recite it; they deliberate the mathematics
elsewhere and do not need it restated here. A draft carrying either is asking them to
decode before they can judge, and every symbol it spends is a place they stop to
recall instead.

**Do not open with a status report.** When the verification came back clean, that is a
precondition, not news: one sentence saying the implementation matches the latest
revision and the suite passes, and move on. Listing what was checked, how many tests
ran and which fields came back green spends the reader's attention before the proposal
starts. A report is owed when something is *wrong* — then it is the whole message.

So narrate the work:

- **What will be built and in what order.** Plainly, as steps.
- **Where the two sides do not line up, and how that is resolved.** This is the part
  worth their attention: prior work and new work were built for different shapes, and
  making them meet always costs something. Say what does not fit, **propose the way
  through**, and say what that way gives up.

  A friction named without a proposed resolution is the problem handed back. The user
  cannot argue with a question — they argue with a proposal, and rejecting one is how
  they steer. Ending on "how would you like to handle this?" after correctly finding
  the hardest part is the same evasion as a menu, one level deeper: it does the
  diagnosis and stops before the prescription.
- **The experiment itself, stated as a protocol.** This is what the user is actually
  agreeing to, and it is where a draft most often goes vague. The standard is two
  things: someone else could run it and get the same thing, and the user can disagree
  with a *specific* choice rather than with a mood.

  What that takes depends entirely on the experiment, and the repository has already
  been read by the time a draft exists, so write it from what is there. Whatever the
  inputs are, say which ones and where they come from. Whatever has to be built or
  configured to run it, say which and at what size, and why that size. Whatever the
  comparison needs that the material does not already contain, say how it is
  constructed. However many times it runs, say how many and what changes between runs.
  Numbers, not adjectives.

  **Give the material its roles, and keep them disjoint.** Wherever something is fitted
  to the material, at least two roles exist — what it is fitted on and what it is
  judged on — and they must not overlap: judging on what was fitted measures how well
  it absorbed that material, and it flatters each side by a different amount, most of
  all the side that absorbs best. If anything at all is chosen by looking at outcomes,
  that choosing needs a third role of its own, or the judgement is reading a decision
  it already made. Say the proportions, say how the division is drawn, and say what
  every role is used for. **Do not carve a role you will not use** — it costs material
  and buys nothing.

  **And choose those proportions, do not inherit them.** A conventional division copied
  because it is conventional is not a decision, and it meets the letter of this rule
  while deciding nothing. The share that goes to judging follows from what the
  measurement has to resolve — the next paragraph — and the two are one thought: work
  out the difference worth detecting, work out how many units that takes, give the
  judging role at least those, and let what remains fund the rest. If the material
  cannot fund every role at that size, that is the finding, and it is said before
  anything runs rather than discovered after a scale has already been proposed.

  Say how each role is composed, not only how large it is. Whatever has to be present
  in every one of them for the comparison to be defined must be present in every one
  of them; a division drawn without regard for that produces a failure that reads as a
  defect of the method and is a defect of the division.

  **Say what the measurement can resolve, before running it.** Count the units the
  verdict will rest on and state the difference that many can separate from noise. A
  protocol whose verdict rests on too few will answer "indistinguishable" whatever
  happens, and the user pays the whole run to learn nothing. That arithmetic is
  cheaper than the run, so it happens first, and it is what decides the scale rather
  than a number that felt reasonable.

- **What is held identical across both sides.** A comparison means something only when
  one thing differs. Name everything the two share and the single thing they do not —
  whatever those turn out to be for this experiment. Without it the measurement is of
  whatever else drifted, and no result can be attributed to the difference it claims
  to be about.

  **Free choices count as part of what differs.** Any knob left open — a coefficient, a
  threshold, a stopping point — is a choice, and if one side's is tuned while the
  other's is guessed or left at whatever its author defaulted to, then the sides differ
  in two things and the claim that only one changed is false. Either both are chosen
  the same way, on the same material, by the same rule, or both are fixed at a declared
  value and the report says so. Tuning one side is the easiest way to produce a result
  that survives every other check and means nothing.

- **What it depends on that might not hold** — data that has to be present, something
  that has to download, something assumed about their setup.

Mathematics enters only when a constraint forces a decision, and then as one plain
sentence about what is required, never as an equation. A file or a function is named
only when the user will open it themselves.

**Generic in the source, concrete in the proposal.** That this skill knows nothing
about any particular field is a property of its code — no dataset, no architecture, no
method hardcoded anywhere. It is not a property of the conversation. By the time a
draft is written the repository has been read: what the prior work trains on, how it
loads it, what shape each side expects. Use it.

So the recipe is specific — in whatever terms this experiment is made of. How many
repetitions and why that many. Every proportion, ratio and threshold, named. Anything
the comparison needs that the material does not already provide, and how it gets
built. Numbers the user can disagree with, not adjectives they can only nod at.

A proposal that stays abstract to remain general has confused generality with
vagueness: generality means the *skill* works for any paper, not that its *plan* works
for none. The skill carries no assumption about what an experiment is made of; the
draft carries every detail of this one.

Two kinds of gate, and treating them alike is the mistake to avoid.

### What happens to an agreement after it is made

A gate produces agreements, and agreements are the thing this flow loses. They are
reached in conversation, they live in nobody's file, and by the time the code is
being written the only record of them is a memory that re-decides freely.

**Write them down as the checklist.** Not the steps of the build — those are the
agent's own plan, and it can finish every one of them while an agreed thing quietly
never happens. The items are what was settled: this figure, that instrument, this
proportion, that ordering. Then an agreement that never reached the code shows up as
an unticked item instead of as nothing at all.

**The checklist is a file, and `verify` reads it.** `<Name>/AGREED.md`, one
markdown item per agreement, unticked when made and ticked when the code carries it:

```markdown
- [x] the free scalar stays at its neutral and identical across arms
- [ ] the figure shows the picture inline, not the path it wrote
```

It lives inside the product folder so it travels with the work, and it is read
rather than remembered — the same rule as everything else here. `verify` reports
`agreements` beside the other statuses: `open` with the items still outstanding,
`settled`, or `absent` when the file does not exist. Absence is a state and not a
failure, because a flow that never reached a gate has nothing to record; it is
reported either way, since a check that speaks only on failure teaches nobody what
it was watching. A bullet written without a checkbox comes back as `unparsed`,
because an agreement in the wrong format is one nobody counts — the same failure
the file exists to prevent, one level down. A sibling skill's own declared
holder (`Experimental_AGREED.md`) is that skill's checklist, never this one's:
`agreements` and the position section never read it, and `agreements` lists it
under `siblingHolders` (present only when such a file exists).

**Once the proof of concept's approval in `<Name>/AGREED.md` is settled, run
`/experiment-diagrams poc`** so the operator verifies the PoC diagram beside the
product in the dashboard's Experimentos panel and validates it there, or
approves it explicitly in the conversation (then run `experiment-diagrams
validate` with the operator's words); nothing of the product is launched
remotely (`DIAGRAM_NOT_VALIDATED`) until then.

Append to it at every gate, before writing any code the gate authorized. And never
report the work done while an item is open: say which, and why it is still open.

**The append is a command, not a hand edit.** `discuss` records the question and,
once answered, the conversation itself as a fact with a ledger line; `settle` then
places exactly one `- [ ] <text>` line under a named heading — the write, performed
by the skill rather than narrated by the agent, is what "the skill binds you so
that it is placed in the contract" means in practice. `settle` refuses unless an
answered `discuss` event already names the identical thing, and refuses again on
an unnamed collision with what is already there. It never authors the sentence and
never ticks the box: both are still the agent's, or the human's, to decide — see
[Flow B step 8](#flow-b--every-later-pass) for the exact invocation.

**And when implementation collides with one, that is a gate, not a detail.** The
collision is real and worth reporting — a package missing, a rendering that is far
easier as text than as a picture, an interface that will not take the shape agreed.
What is not allowed is resolving it alone and mentioning it on the way past. Name the
agreement, name what blocks it, name the replacement and what it gives up, and wait
for a yes.

The substitution is usually the more defensible engineering choice, and that is
exactly why it slips through: it looks like tidiness rather than a decision. It was
still the user's to make.

### Decisions — offer the options

A decision has a knowable set of outcomes: reorganize or not, convert or not, run or
not. Ask it as a choice, using the runtime's interactive question UI when there is
one. An open "do you want me to reorganize?" leaves the user guessing what the
alternatives are and what each costs. The third outcome is usually the interesting
one:

| gate | the options that must be visible |
|---|---|
| reorganize | apply it · leave the layout alone · **too large: take it to its own session** |
| the name | use `<Name>`/`<Package>` as normalized · type a different one |
| implement | go ahead · stop here |
| corrections to the proposal | publish them · leave the findings open · review them one by one first |
| convert to PyTorch | convert implementation and tests · not now |
| run the benchmark | run it · not now (it downloads a dataset and uses the machine) |

- **Never offer an option the flow cannot honour.** A reorganization above the limit
  is not offered as "apply it": that answer would be refused after the user chose it.
- **State each option's cost before it is chosen**, not after. Publishing advances the
  real lineage; the benchmark occupies the machine; declining the layout leaves drift
  every later run will report. A choice made without its consequence is not a
  decision, and the authorization it produces is not one either.

### Design — a conversation, and one question at the end of it

The wiring and the object→module map are **not** decisions, and they are not
questionnaires either. They are things to work out together, and the skill already
holds what it takes to open the conversation: the provenance of each module, the
baseline's own code, what it trains on and how it loads it.

**No options, no menu, no "how do you want to handle this".** Offering approaches to
choose between returns the work to the user while holding the context that would have
answered it, and a menu is that same evasion wearing a structure. This is the
deliberation tutor's posture at a smaller scale: propose, say what you are unsure of,
listen, argue back when the answer does not hold, and keep going until it settles.

**Tell it, do not report it.** Narrate what you found and what you would do with it —
not which commands you ran, not what the JSON came back with, not a list of fields.
The user does not need the mechanics to judge the idea; the mechanics are this
skill's problem. Say what the repository turned out to contain, what that suggests,
and what still worries you.

What the conversation carries:

- **The proposal**, concrete enough to argue with. Vague is not humble: a draft too
  soft to be wrong cannot be corrected either.
- **Where each part came from** — read, inferred, or assumed. The three are not
  equally trustworthy and the user is entitled to know which is which.
- **Your own doubts, raised by you.** Not "let me know if this is right", but the
  specific thing you could not settle from the repository and why it matters. A
  proposal that hides its soft spot is asking for approval, not for review.

**Only ask when the conversation has converged.** You decide when your doubts are
answered and the design is reasonable, and you say what changed your mind. Then, one
question and only one: implement this? Not before — asking earlier turns a
deliberation into a form, which is what this section exists to prevent.

**"Correct something else first" is not a request for a menu.** When the user pushes
back without naming the piece, do not answer with a list of the parts in play for
them to pick from: that is the questionnaire returning in another shape, and it asks
them to do the locating. Go back to the part you were least sure of, say why it is
still bothering you, and open there. If you genuinely cannot tell which piece they
mean, ask that — one question, in their words, not a numbered inventory of your own
design decisions.

## Flow B — every later pass

1. Read `src/` and take `latest` from `STATUS`.
2. **Run the suite with the target interpreter, then `verify --revision <latest>`.**
   Both, and in that order — they answer different questions and neither substitutes
   for the other.

   `verify` **reads**: it checks the layout, that every module still declares the
   revision it was written against, that every invariant it names has a matching
   test, that no assertion is one that cannot fail, and that the notebook was
   actually executed. What it cannot tell you is whether any of those tests pass.
   Running the suite is what proves the code *does* what it says; `verify` proves it
   *says* what it should.

   Skipping the run is how a repository reaches a benchmark while an invariant is
   broken: every provenance intact, every id matched, `fidelity` clean, and a claim
   failing underneath. That gap is widest right after a change of backend, which
   rewrites how every number is computed while leaving every declaration untouched.

   **A module's revision binding is by name, not by content.** `verify` marks a
   module `stale` only when its own declared `revision` names a file other than
   `latest` — `__provenance__` carries a filename, never a content hash. Editing
   `latest` itself in place, while every module still names it correctly, passes
   the suite and `verify` clean: nothing this step reads compares the file's
   current bytes against anything. That edit is invisible here, not fixed here —
   it surfaces later, at `gate`/`close`, as `POSITION_STALE` (the position
   section's own header carries a `sha256` of the revision it was measured
   against, and re-checks it there): a refusal, not an overwrite. Nothing already
   recorded is touched; the old evidence stays on disk and simply stops counting
   until `position` is run again to rebind it. A green suite and a clean `verify`
   at THIS step are never proof that `latest`'s bytes are the ones any earlier
   position was measured against.
3. **Suite green and no differences** → report both, then run `probe --revision <latest>`
   before asking anything and follow its `nextStep`. See
   [Conversion, then benchmark](#conversion-then-benchmark). On `nothing-to-compare`
   or `already-benchmarked`, **ask the user what they want to do next** and invent
   no work.

   **Nothing to compare does not hide the declared flow.** A target with no
   prior-work package under `src/` (its comparison arms may live inside
   `<Package>` itself) still owes its pilot and its per-step decisions:
   `probe` answers `pilot-first` while a declared step is short at pilot, and
   `pilot-decisions` once the pilot is complete and a step is undecided, and
   only then `nothing-to-compare`.

   **`piloted` is its own state and never reads as finished.** A record whose scale
   sits below the one the protocol declares is neither absent nor done. Report it
   precisely — how many repetitions and how long it ran, what the protocol asks for,
   what the full run costs from the measured time, and what the configuration declares
   but has never exercised — and then leave the question open. Not a menu: the pilot
   exists to be the place where somebody looks, adds a test, moves a proportion, and
   runs it short again, and a list of three buttons closes exactly the door it was
   built to hold open. The decision to release the full run appears only after the user
   says there is nothing left to change.
4. **A failing test** → that is the finding, before any question about fidelity. Report
   which claim broke and stop; a red suite is not a state to compare from.
5. **Differences in fidelity** → **[GATE] ask whether the user made those changes.**

   Read `drift` before saying anything: it crosses the sections that actually differ
   between the revision a module declares and the current one with the sections that
   module declares. A module bound to an older revision whose own sections never moved
   needs re-binding, not rewriting — bookkeeping, not mathematics — and saying "nine
   modules are stale" when one equation changed tells the reader there is work and
   nothing about where. `benchmark` answers the same question for the bench: which
   arms a changed section reaches, so the experiment is re-run because something it
   depends on moved rather than because a string did.

   A section is a heading whose first token is a label: a number (`## 3. Formulation`,
   `## 3`), a dotted number (`### 3.1`), or an identifier (`### O1. Objective`), closed
   by an optional `.`, `)` or `:`. The grammar lives once, in
   `skills/_core/conventions/sections.json`. A labelled heading nested under another
   is its own section and still part of its parent, so a change inside `3.1` reports
   both `3` and `3.1`; an unlabelled heading belongs to the section around it. A
   module's `__provenance__["sections"]` names those labels exactly as the headings
   spell them. A revision whose headings carry no label yields no sections, and only
   the file-level revision drift (`staleModules`) is reported for it.
   - **They did** → the code is ahead of the proposal. Remind them to update the
     mathematics and hand them the prompt that does it. Do not edit their code to
     match an older proposal.
   - **They did not** → the code has drifted. Correct it and re-run the validations,
     bounded by the same three passes as Flow A step 16.
6. **A target declaring `__steps__` can run one of them, isolated, under its own
   venv:** `step --target <repo> --name <Name> --step <name> --session <your-session-id>`.
   This is the executor for the isolation rule stated at the top of this file
   ("Non-negotiable isolation") — a `PATH` prefixed by the target's own `.venv/bin`
   so a notebook's kernelspec resolves the right interpreter rather than a bare
   `python` off whatever launched it. Refuses `DIRTY_WORKTREE` before anything
   runs (a step mutates the target, same as `plan`/`apply`), `STEPS_UNDECLARED`/
   `STEP_UNKNOWN`/`STEP_MALFORMED` when the name does not resolve statically, and
   `STEP_MODULE_MISSING`/`STEP_FUNCTION_MISSING`/`STEP_NOT_CALLABLE`/
   `INTERPRETER_ABSENT` when it does not resolve inside the venv. Every resolved
   run — pass or fail — appends one `kind: "step"` event; it never sequences,
   never dispatches `probe`'s `nextStep`, and it neither reads nor writes a
   `gate` event.
7. **Run `offer`** once the position sequence exists: `offer --target <repo>
   --name <Name> --session <your-session-id> --revision <latest> --answer
   yes|no` on EVERY call (answering: continue the flow as it stands, or
   change the experiment contract first?) — required every time, never read
   back from a prior call. It refuses `OFFER_UNANSWERED` whenever `--answer`
   is omitted, then publishes a closed action set — one `launch` per job the
   shared availability rule already says `gate` would not refuse, plus
   `run-step` or `expand-contract` depending on the answer just supplied.
   Present it as a menu; nothing here runs on its own.
8. **Once a `discuss` question is answered, place it — do not hand-edit
   `AGREED.md`.** `settle --target <repo> --name <Name> --session
   <your-session-id> --about <ordinal|witness> --text "<what was settled>"
   --under "<exact heading>"` writes exactly one `- [ ] <text>` line,
   verbatim, after the last item under that heading (items read oldest
   first; the position block is never entered, so `--under "## Ladder"` works
   on the holder `position` creates). It refuses `SETTLE_NOT_DISCUSSED` /
   `SETTLE_DISCUSSION_UNANSWERED` unless an answered `discuss` event already
   names the identical witness, and `SETTLE_COLLIDES_UNNAMED` when the same
   thing already appears to be on record — name the item it supersedes with
   `--supersedes "<exact existing text>"` to proceed. This is the mechanical
   half of the doctrine above ("What happens to an agreement after it is
   made"): the tool never authors the sentence and never ticks the box —
   both are still yours — it only performs the write once you have decided
   what to write and confirmed it was discussed.

## Conversion, then benchmark

Run `probe --revision <latest>` and follow its `nextStep`. The order it reports is
not a preference.

**A baseline is asked about first.** Without one there is nothing to compare, and
then the backend is nobody's business: numpy is where the mathematics is proved —
no autograd, no device, no optimizer to mask a wrong formula — and for a proposal
nobody is going to train, that is where it belongs and where it can stay. Demanding a
conversion there would ask for work with no purpose and make a finished
implementation read as unfinished.

**With a baseline, the conversion comes before the comparison**, because an
implementation computing with numpy cannot be trained at all. Proposing a benchmark
first would ask the user to approve a run that cannot happen.

The verification before all of this does not care which backend it finds. It is a
static reading — the revision each module is bound to, an invariant for every claim,
a test for every invariant, no assertion that cannot fail — and the suite is run with
whatever interpreter the target has. Both work the same whether the implementation
computes with arrays or with tensors, because which one is right depends on the stage
the proposal is at, not on this skill's preference.

### The implementation declaration: `revision` and `premises`

`src/<Package>/__init__.py` carries `__implementation__` — one literal, two
blocks, `{"revision": "", "premises": {}}` — beside the target's own
`__levels__`/`__steps__`/`__records__`. These are facts about the METHOD, not
about the comparison, so they live in the method's own package rather than in
`src/<Package>_Benchmark/`, which is the comparison's own file:

    __implementation__ = {
        "revision": "r01.md",
        "premises": {
            "prediction": "a class label per subject",
            "statisticalUnit": "subject",
            "metric": "balancedAccuracy",
            "direction": "higher",
        },
    }

**`revision` and `premises` are asked by this flow, never invented.** `revision`
names the managed revision this declaration is bound to — a filename under
`proposals/`, not a value `materialize.py` or any other tool fabricates.
`premises` says what kind of prediction the protocol assumes, over which
statistical unit, by which metric and in which direction it is judged;
nothing downstream validates its content — it is written for a person
reading a drift report beside changed sections, not for a check to parse.
This is Flow A's ask for `revision` and `premises`, at step 8, above.

**One package, two skills: key `revision` by document label.** When
`experimental-implementation` works on the same target it reads the same
`src/<Package>/__init__.py`, and a single name cannot be both a proposal
revision and an experiments revision: each skill would read the other's name
as its own (`verify` then discovers nothing for that skill and reports
`fidelity: unknown`). Name one revision per document label instead; each
skill reads only its own document's label (`proposal` here, `experiments`
there) and neither goes stale because the other moved:

    __implementation__ = {
        "revision": {"proposal": "r03.md", "experiments": "experiments-<slug>-v02.md"},
        "premises": {...},
    }

A bare string keeps its old meaning (this skill's own document), so existing
targets read exactly as before and nothing rewrites them; switch to the keyed
form by hand when a second skill starts binding the package. A mapping with no
entry under this skill's label leaves its revision unanswered: with empty
`premises` the declaration is `undeclared` and its detail names the missing
label; with `premises` answered, `materialize --stage objects` refuses
`OBJECT_MAP_NOT_APPROVED` naming `revision`. Any other lineage's name is never
read here. A value under the label that is not a string makes
the declaration `undeclared`. `verify` and `probe` read the narrowed name; the
full mapping travels as `revisionByDocument` on the reader's contract.

Under the keyed form, a module whose `__provenance__` revision belongs to
another label's lineage (the same filename family as that label's mapped name,
digits aside, so an older revision of it counts too) is the other skill's to
judge: `verify` lists it in `fidelity.otherLineageModules` (`{module, label,
revision}`) and keeps it out of `staleModules`, `drift` and the headline
`fidelity.status`. Before 0.14.0 it read "bound to an older revision" and
drifted the headline of both skills on every shared target. A module of this
skill's own lineage goes stale exactly as before, and a bare string binds no
other lineage, so every module is judged here.

| Literal | Filled by | When |
| --- | --- | --- |
| `revision` | Flow A step 8 | Proposed as step 1's `latest` and confirmed inside the authorization approval, before any code that approval authorized is written |
| `premises` | Flow A step 8 | Carried across from the protocol the gate was granted on, field for field, in the same approval |

The other three declarations beside it — `__levels__`, `__steps__`,
`__records__` — are the target's own first-flow declarations, filled in as
that flow is walked, never by this skill's own object-map gate. `authored_package_init`
prefills all four empty, with guidance comments, the moment
`src/<Package>/__init__.py` is scaffolded.

### The benchmark declaration, and its five blocks

`src/<Package>_Benchmark/__init__.py` carries one literal, `__benchmark__`, and
every check downstream of it — `search`, `distribution`, `report`, the wiring
crossing behind `wiring-first`, `probe`'s whole ladder — reads that one dict
and nothing else. It is a **harness** destination, not a scaffold one: the
kit ships it with all five top-level blocks present and empty
(`assets/kit/src_benchmark/__init__.py`), but `materialize --stage harness`
writes it only once a comparison has been accepted (see
[`nextStep: "benchmark"`](#nextstep-benchmark--propose-the-wiring-then-train-both-and-measure)) —
never at scaffold time, and never for a target whose comparison was declined
or whose acid test was run instead. Before acceptance there is no file at
all; once it is materialized, what it does not yet have is anything written
into it:

    __benchmark__ = {
        "arms": {
            "baseline": {"sections": ["3.1"]},
            "proposed": {"sections": ["3.1", "3.4"]},
        },
        "search": {
            "what": "the regularization weight",
            "requiredScale": {"epochs": 20, "seeds": 3},
            "role": "validation split",
            "tieRule": "smallest value within one standard error of the best",
        },
        "report": {
            "renderers": ["tables.render"],
            "conclusions": ["tables.conclusion"],
            "figures": ["figures.curves"],
            "dimensions": {"accuracy": "higher", "seconds": "lower"},
        },
        "entry": {
            "module": "Example_Method_Benchmark.benchmark",
            "function": "run",
        },
        "distribution": {
            "axis": "seed",
            "poolable": ["accuracy"],
            "perEnvironment": [],
            "perRun": [],
            "identicalAcrossShards": ["datasetSize"],
        },
    }

Which step fills which block, so that "somebody fills it in as the work happens"
names a somebody:

| Block | Filled by | When |
| --- | --- | --- |
| `arms` | Flow B's `wiring-first` rung | Once an arm is wired and the sections it exercises are known |
| `search` | Flow B's `search-first` rung | Once a search is actually run and has a scale and a tie rule of its own |
| `report` | Flow B's `report-first` rung | Once the renderers and conclusions exist to name |
| `distribution` | Flow B's shard work | Once a run is actually split across machines |
| `entry` | Flow B's harness placement | Once the harness module exists and its own entry point is known |

Every row is the same rule: a block is written when the work it describes has
happened, and never before.

**`arms`, `search`, `report` and `distribution` are never invented.** Each is
read off the work as it happens — an arm's sections once it is wired, a
search's own scale and tie rule once one is run, a report's renderers once
they are written, a distribution's axis and partition once a run is actually
split across machines. Flow A stops at the empty container for every one of
them; filling them in is what the later steps of this skill are for.

**Emptiness means something different at the block level than inside one.** A
container that has been written into can legitimately stay empty —
`perRun: []` is a declared, measured fact about a run that never divides per
repetition, and `distribution` reports it as answered, not missing. A whole
block still at its scaffolded empty value is not that: no repository ever
means "I measured that `distribution` is empty" before a single shard has
run. `declare-first`, below, is what tells the two apart.

**`undeclared` covers a blank declaration, not only a missing one.** Both a
target with no `src/<Package>_Benchmark/` directory at all (`absent`) and one
whose `__init__.py` parses but leaves every block at its scaffolded, empty
value (`undeclared`) are read the same way by `search`, `distribution` and
`report` — as nothing yet said, not as a finished declaration that happens to
say little. `probe`'s `declare-first` is narrower than that (D4): it fires
only on `undeclared`, never on `absent` — a target with no benchmark package
at all is the ordinary pre-acceptance state and falls through to the
comparison offer or the decline pair instead, never to "declare" a file that
deliberately does not exist yet. Once any one block is answered, the
declaration is `declared`, and each block reports its own state independently
from there.

### `nextStep: "convert"` — port the implementation to PyTorch

`backend` reports which files still compute with numpy. **[GATE]** ask, then convert
the modules under `src/<Package>/` **and their tests together**. `mixed` is the state
to avoid, not a milestone: modules that train while the tests still assert over numpy
give a passing suite that measures something the trained model never touched.

The mathematics does not change — this is a change of backend, not of method — so
`verify --revision <latest>` must still report `fidelity` clean afterwards, and every
invariant test must still hold. Re-run the audit: a remedy established over the numpy
sweep has not been established over the converted one.

**Declare the backend once converted.** By default `backend` is inferred from
imports, and any file importing only numpy reads as `mixed`, including a test
helper that only seeds a generator. State the backend in
`src/<Package>/__init__.py` instead:

```python
__backend__ = "torch"   # or "numpy", "jax", "tensorflow"; None = infer from imports
```

Then the stated value decides (`backend.source: "declared"`, `backend.declared`):
`tensor` (trainable) when some file under `src/<Package>/` imports it,
`declared-unmet` when none does, `numpy` for `"numpy"`, and
`unrecognized-backend` (with `declarationError`) for any other value, which
fails closed and is never trainable. `numpyFiles`/`tensorFiles` are still
reported. The kit's `tests/conftest.py` and `tests/sweep.py` import no array
library (they seed a `random.Random` and expose `SEED`/`configuration_seed`),
so they never decide the backend; a target scaffolded before 0.14.0 keeps its
numpy-importing copies, which is exactly the case the declaration settles.

**Torch in the target venv.** PyPI's plain `torch` is the CUDA build on Linux.
`env --torch cpu` appends `--extra-index-url https://download.pytorch.org/whl/cpu
torch==<X>+cpu` to `nextCommand`, with `<X>` from `--torch-version` or the one
exact `torch==X` pin in the target's manifests (no exact release refuses
`TORCH_VERSION_REQUIRED`); `env --torch gpu` appends `torch` (or `torch==<X>`)
from the default index. Without `--torch`, `env` installs no torch.

### `nextStep: "declare-first"` — the benchmark package exists and says nothing yet

`resolve_benchmark_declaration`'s `undeclared` state is what this rung acts
on: `src/<Package>_Benchmark/__init__.py` exists — the harness stage has
already written it, which only happens once a comparison has been accepted
(see [`nextStep: "benchmark"`](#nextstep-benchmark--propose-the-wiring-then-train-both-and-measure)) —
but either nothing parses as `__benchmark__`, or one does and every block in
it is still at its scaffolded empty value (see
[The benchmark declaration, and its five blocks](#the-benchmark-declaration-and-its-five-blocks)).
`declared` — at least one block answered — does not block the run, and lets
the ladder continue to the checks below that read what was answered.

**`resolved["status"] == "absent"` — no benchmark package at all — does
*not* route here.** That is the ordinary, pre-acceptance state of every
first-flow target now that the benchmark package is no longer scaffolded: it
falls through to the comparison offer (`benchmark`) or, once that offer is
answered, to `validate`/`declined`/`build-first` instead — see
[`nextStep: "benchmark"`](#nextstep-benchmark--propose-the-wiring-then-train-both-and-measure).
Routing an absent package here would tell every such target to go and fill a
file that deliberately does not exist yet.

**Why it sits first, ahead of every other rung here, and why that is not a
preference.** `unreachedModules` — what `wiring-first` reads — is computed
from this same declaration's `arms` block, and with nothing declared that
block is always empty: `wiring-first` can never fire on its own while the
declaration itself has said nothing, so placing this rung ahead of it costs
nothing that rung would otherwise have caught. Left unguarded, a target whose
benchmark package exists and has declared nothing instead reaches
`report-first` by accident: `report` already reports its own `"undeclared"`
the moment its block has nothing in it, and that alone used to carry the run
offer straight past a target that had not started declaring anything, into a
rung whose whole premise is a document disagreeing with a run — when no
report exists yet to disagree with. `declare-first` is the honest rung for
that state, and it stands ahead of every check that is built on top of a
declaration which has not happened.

**Report it, and stop there.** Unlike `wiring-first`, this names nothing to
correct: there is no fork to point at, only empty blocks and a person who has
not yet filled `arms`, `search`, `report` and `distribution` in as the work
happens. Say what the resolver's own `detail` names: no readable literal at
all, or one that parses with nothing in it answered.

### `nextStep: "env-first"` — the declared entry module cannot be imported

`report.live` came back anything other than `ok` (and other than the absence
that means `report` itself is still undeclared, which is `declare-first`'s
state, not this one): the interpreter under `<target>/.venv` could not import
the module the benchmark declares as its own entry point. `report.liveDetail`
carries the real last line of that failure, quoted rather than paraphrased —
never a guess at what is missing.

**Why a clean `config` import is not enough evidence, and why this rung exists
at all.** `config` is pure Python; it imports fine with nothing installed. An
empty venv that had never run anything still answered `live: ok` from that
alone, which cleared the way to a run the environment could not perform. The
entry module is what actually pulls the target's runtime in, so its own
failure is the truthful verdict.

**What this rung is never for.** `env` installs packages; it writes no module
and edits no import, so a rung whose only exit is that command must never be
reached by a file being absent. Two ways it was: the constants `writtenSelections`
is derived from used to be imported from `<Package>_Benchmark.config`
unconditionally, and the kit ships no `config.py`; and the kit's own
`benchmark.py` imported `verdict` flat, which does not resolve under the dotted
`entry.module` the kit's own example declares. A repository built exactly as
step 9 prescribes hit both, in that order, and looped here. `report.constants`
now names which module the constants were read from (`config` first, then the
kit's `benchmark`), or says `absent` when there was none — a fact, never this
rung.

**Report it, and stop there.** Run `env` — its `nextCommand` lists the
target's own declared manifests beside the forge's dev requirements — install
what it prints, and probe again. There is nothing here to correct in the
repository itself: the fix is provisioning, not code.

### `nextStep: "wiring-first"` — an arm declares mathematics it never calls

**The `wiring` draft is in this payload.** It used to be guarded on
`next_step == "benchmark"` alone, and the override that sets `wiring-first` runs
before that guard — so at the one answer that names missing wiring, the draft of
how each module becomes trainable came back `null` and whoever was reading had
to compose the plan in prose. `PROBE_NEXT_STEPS` now says which answers carry
it, and both of the two that describe the wiring do.

`unreachedModules` names each module of the method that no arm reaches, directly or
through another module, while at least one arm declares its sections. Each entry
carries the equations it implements and the arms that claim them, because the section
is where it lives and the equation is what the reader acts on.

**And an empty `arms` switches the whole crossing off, silently, so
`fidelity.benchmark.note` says so.** `unreachedModules` is built FROM `arms`:
with none declared it answers `[]` on every run whatever the modules hold and
whatever the harness calls, `armsReached` answers `null`, `benchmark.status` can
never read `unfaithful`, and `wiring-first` can never be reached. `note` names
the file, counts the modules that declare sections and go uncrossed, and names
each reader that goes quiet. It is `null` the moment an arm is declared, and
`null` for a repository whose modules declare no sections at all — there is no
crossing to lose there, and `missingProvenance` already names those modules.
Reported and never demanded: one arm and nothing to compare is a legitimate
resting state, and which comparison a repository runs is not the forge's to
decide.

This blocks the run, ahead of an already-pending submission, a missing search
configuration and a report in drift, and behind only a declaration that has not
started. A wrong report describes a sound run and costs a
sentence; this costs the campaign, because every number came from an arm that was not
computing what the table says it computed.

Report it as its own finding and say when it started being material. It is almost
never a fresh mistake: the arm reimplemented the term when the inline version was
equivalent, and a later revision moved the module and left the arm behind. So name
both — the fork, and the change that turned it from a rounding difference into the
whole term. **[GATE]** then propose pointing the arm at the module and ask, because
correcting it changes what the next run measures.

Read what the correction implies before proposing it. Computing the arm as its
proposal states can change what the two arms share, and that consequence gets measured
and declared — it is never a reason to keep computing the method the prior work's way.
See the hard rule on using the baseline as it is and the method as its proposal states.

### `nextStep: "poll-first"` — a submission is already out, and its answer has not returned

A session can end with work already sent to a remote worker and no result back yet.
The next session's `probe` would otherwise say "run the benchmark" while that answer
is still in flight, inviting a duplicate submission that spends real quota answering a
question already being answered. `remoteExecution.status` already carries this —
folded once by the ledger reader and read here, never re-folded — and `"pending"` is
the one value this rung acts on: at least one entrypoint has a submission out with
nothing terminal recorded against it yet.

**Why it sits after `wiring-first` and before `search-first`, and why that order is
not a preference.** A submission that went out under broken wiring is already
answering the wrong question, and no amount of waiting fixes that — so `wiring-first`
still corrects the arm before anything asks whether to wait or to run. Once the
wiring is sound, an answer already on its way outranks a value nobody has chosen yet:
where a search's own record is absent because the search itself is what is pending,
answering `search-first` would ask the reader to resubmit exactly what is already in
flight — the duplicate this rung exists to prevent. `poll-first` catches that case;
`search-first` only fires once nothing is actually out there to check on.

**`drift` and `unreliable` are deliberately not `poll-first`.** Both are real defects
and neither is "wait for it." `drift` means a submission's source moved out from
under it while it was in flight, or a result already arrived and was quarantined
against a submission that was no longer current — the fix is `remote_cli reconcile`,
which compares the ledger against what the service says is running in both
directions, not polling a value that waiting will not resolve. `unreliable` means a
line of the log could not be read at all, so nothing about what is or is not out
there can be trusted yet — polling would be asking a question of a record that cannot
currently answer it, and the same reconciliation is what re-establishes one. Both fall through this rung unresolved, exactly as they did before it
existed; folding either into "poll" would tell the reader to wait for something a
wait cannot fix.

### The remote-execution seam — which subcommand answers which reported state

This flow reports remote-execution states and runs none of the commands that
resolve them. That is the right division — `probe` and `verify` read and never
send — but it left a reader told to wait, or told a ledger had drifted, with no
name to type. The commands belong to the forge's `remote-execution` skill; what
belongs here is which reported state routes to which one:

| Subcommand | The reported state that routes here | Applicable flags | Where the flags are documented |
| --- | --- | --- | --- |
| `submit` | None. This flow offers a campaign to a human and never sends one itself | `--backend`, `--entrypoint`, `--target` | the `remote-execution` skill |
| `status` | `remoteExecution` on any target: it folds the same ledger `probe` reports, for when you want it fresher than the last read | `--entrypoint`, `--target` | the `remote-execution` skill |
| `poll` | `nextStep: "poll-first"` — a submission is out and its answer has not come back | `--backend`, `--submission-id` | the `remote-execution` skill |
| `fetch` | A submission the ledger calls returned whose result is not on disk yet | `--backend`, `--entrypoint`, `--submission-id`, `--target` | the `remote-execution` skill |
| `reconcile` | `remoteExecution` reporting `drift` or `unreliable`: the ledger and the service disagree, or a line of the log could not be read | `--backend`, `--entrypoint`, `--target`, `--worker` | the `remote-execution` skill |
| `generate-job` | No job folder for the campaign about to be offered — `remoteExecution.jobs` empty, or naming none that matches | `--job-name`, `--product`, `--repo-ref`, `--repo-url`, `--service`, `--target` | the `remote-execution` skill |
| `generate-job` | A job folder exists and its declared pin no longer matches what the clone paths hold — `staleness` reports `drift`: regenerate (`--regenerate`) rather than offer a run against a repository that has moved | `--job-name`, `--product`, `--repo-ref`, `--repo-url`, `--service`, `--target` | the `remote-execution` skill |
| `distribute` | A campaign whose units outnumber what one account can hold at once: it reports which account each unit would go to and which ones do not fit, and sends nothing | `--backend`, `--entrypoint`, `--target`, `--unit` | the `remote-execution` skill |
| `remaining` | A campaign whose session was cut, or that came back with only part of its units: it reports which declared units have no complete result yet, the only ones the next campaign sends; it asks no backend and records nothing | `--entrypoint`, `--target`, `--unit` | the `remote-execution` skill |
| `smoke record` | `smokeReady: false` for a job that has rehearsed and whose verdict was never written down | `--from-artifact`, `--job-dir`, `--worker` | the `remote-execution` skill |
| `readiness` | `smokeReady` itself: it is the function `probe` calls to compute that fact, and asking it directly is how you see the reason | `--job-dir`, `--worker` | the `remote-execution` skill |
| `generate-jobs` | The product declares several remote steps and none (or a stale set) has a job folder: it generates every remote step's job in one call from `__steps__` (and a `schedule` output) and prints the one `preflight` to run next | `--product`, `--target` | the `remote-execution` skill |
| `preflight` | A job folder exists and no rehearsal has been asked for yet, or the job was just re-pinned: it checks locally everything a first remote rehearsal used to find, and is run before the operator is asked to authorize one | `--entrypoint`, `--target` | the `remote-execution` skill |

Column one is read by the suite against that CLI's own parser, so a subcommand
added there fails the tests until this table says which state sends a reader to
it. Column three — applicable flags — is read from the same parser, narrowed to
what each subcommand marks `required=True`: the shape a reader actually has to
match, which is exactly where `readiness` (`--job-dir`/`--worker`) stopped being
`--target`/`--entrypoint` shaped the way every neighbouring row here is, and
following the table as if it were would refuse on a usage error rather than
route anywhere. The full flag lists are still deliberately not restated: two
copies of a flag list is the drift this table exists to remove, and
`references/usage.md` shows the shape of three invocations and points at the
owning skill for the rest.

**A job folder that exists is not the same defect as one that is absent.**
`generate-job`'s first row above covers `remoteExecution.jobs` naming none —
there is nothing on disk yet. A job folder can also exist and be pinned to a
commit the repository has since moved past: `staleness` reports that as
`drift`, distinct from the absent-folder case and from `reconcile`'s ledger/
service disagreement, and it maps to the second `generate-job` row — the same
command, run with `--regenerate` against the existing folder rather than a
fresh one.

### `nextStep: "pilot-first"` — the declared flow has not finished at pilot

**The pilot is a gate, not a step.** A target may declare a flow: **every**
`__steps__` entry is one of its steps, and an `advances` ordinal says where a
step goes in the order rather than whether it counts. This rung fires while any
of those steps has not finished, and it withholds the offer of the declared
scale until they all have. It fires whether or not anything is comparable: a
target with no prior-work package under `src/` reaches it, and the next rung,
exactly as one with a baseline does.

**Every declared step, never the ordered subset**, and that is a measured
correction rather than a preference. The rung read only the entries carrying an
ordinal. On a real repository four of ten declared steps carried none: all four
were invisible to the gate, none of them had ever run, two of their notebooks
held zero executed cells — and `probe` answered `pilot-decisions`, offering the
remote worker over a flow six tenths walked. A step written into `__steps__` is
a step the target means to run. The ordinal orders the ones that claim a
position; the ordinal-less ones are reported after them, in name order, and are
owed exactly as much.

Two facts are asked of each step, and only two. It has to have **run and
returned** — the same `@step` reading the position grammar already performs, so a
run recorded against a suite that has since moved reads as unmeasured rather than
as a pass. And every notebook it owes has to be **executed against these
sources** — `status: "executed"` and `sourcesMatch: true` together, the same
`@notebook` reading. Existence proves nothing: a file copied into place and an
executed report are indistinguishable until the execution counts are read.

**How the notebooks a step owes are known, and why nothing new is declared for
it.** Nothing here reads the target's own Python to find which file a step
executes; it does not have to, and there are two links to read instead. The
first is the step's own `produces` roots — the output roots `step` already
measures a run's write scope against — where a root under `Notebooks/` is the
target naming a notebook that step renders. That half needs no ordinal, which is
exactly why an ordinal-less step can be asked the notebook question at all. The
second is unchanged: `advances` says which position item a step produces evidence
for, and the operand of the item at that ordinal is a notebook when that item's
witness names one. Both are kept, because dropping the second would lose a check
every target that declares notebook witnesses and no `produces` has today, and a
predicate standing in front of the expensive door may only ever widen. Neither is
a new declaration: a repository built from zero is asked for nothing it is not
asked for already.

**A step that declares no `produces` is unmeasurable here, never failed.** It is
named in `pilotCompleteness.unmeasurable`, beside the `note` that says what the
absence costs, and its own run still decides whether it is complete — the same
reported-never-demanded shape `verify`'s `undeclaredProduces` already uses. The
two lists ask a reader for opposite things: `incomplete` asks for a run,
`unmeasurable` asks for a declaration. Folding them together would either fail a
legitimate step for a declaration it never had to make, or — the direction that
actually costs something — let *nobody could look* pass for *nothing was wrong*.

**Whether the pilot opened a notebook at all is said per step, zero included, and
it is a report rather than a rung.** Every row carries `notebookCount`, and
`pilotCompleteness.withoutNotebook` names the steps whose set came back empty,
beside its own `withoutNotebookNote`. Nothing is refused on it: a target may
legitimately keep its computation in a library and render nothing of its own, so
such a step's verdict is exactly what it was and the flow reaches the same rung it
always did. It is reported because until it was, the fact was invisible — a step
that renders no notebook and a step whose notebook nobody opened read identically
off every other key — and that invisibility is how four declared steps in ten, and
the notebooks they own, fell out of a pilot with nobody told. The count is on every
row and not only on the zeroes, the same reason `priorWork` reports what did *not*
change: a report met for the first time on the run where it matters is a report
nobody has learnt to read. It is a different absence from `unmeasurable` — that one
is a step nobody could look at, this one a step there was nothing to open.

**And a repository built from zero is asked the question before it can run into
it.** `withoutNotebook` reports after a pilot has been paid for; the from-zero
half is `verify`'s own `undeclaredStepNotebooks`, read off the declaration alone
and answerable on a repository that has run nothing yet. It names every declared
step whose `produces` roots include none under `Notebooks/`, beside what the
absence costs, and it refuses nothing. It reads that one declaration and never
the position sequence, which is stated rather than left to be found: a step
whose notebook is witnessed only by the item at its `advances` ordinal is named
here anyway, because a sequence witness is a mark in `AGREED.md` and a
repository built from zero has not written one — a check that consulted it
would go quiet on exactly the repository it exists for. The two are separate keys and not one
widened key on purpose: they answer different questions — *this repository
opened no notebook here* and *nobody ever asked it to have one* — and folding
the demand into the report would make one key's emptiness mean both "every step
owns a notebook" and "no pilot has run".

**The pattern it asks for, stated once so the kit and the report agree.** A flow
has two kinds of step, and each owns a notebook: one that **computes** —
orchestrating the target's own library, writing data, drawing nothing — and one
that **draws**, reading what the computing step left behind and rendering
tables, figures and conclusions. Both are then executed by the pilot *as
notebooks*, which is the whole point: the artefact later handed to a worker
elsewhere is a notebook, so a pilot that exercises anything else has not tested
what gets sent. The kit ships both kinds in its own `__steps__` example.
Collapsing them into one step stays a legitimate design and nothing refuses it —
what it costs, written down so the choice is made rather than defaulted into, is
that a figure can no longer be redrawn without paying for the computation behind
it again, and that whichever half sits outside a notebook is the half the pilot
never exercised in the shape it will be sent in.

**An item whose witness is not a notebook adds nothing to its step**, and that
restraint is what keeps this rung reachable. A record must meet its own declared
scale and a campaign run short leaves no shard at all, so both are evidence only
the full run produces. Demanding either here would deadlock the flow on exactly
the evidence it is withholding permission to go and get.

**A target that declares no ordered flow reaches none of this.** `status:
"undeclared"` means the rule does not apply, and the ladder answers precisely
what it answered before this rung existed. A repository that never opted into an
ordering is not an unfinished one — and that condition is deliberately *not*
widened with the rest: it asks whether ANY entry carries an ordinal, because a
repository with no ordering at all has opted into nothing. What the widening
changes is which steps count once a flow exists.

**Why it sits after `poll-first` and before `search-first`.** A submission
already out keeps its place: an answer on its way outranks anything this
repository could be told to start, and asking again would spend real quota on a
question the first send is already answering. Everything below it is about
machine time that has not been spent yet, and the pilot comes before the scale.
`search-first` fires on "the record is absent or short", which is a true fact and
a different one: a target can have run one step of six, produced nothing anybody
can read, and satisfy that condition exactly. Measured, on a real target: one
step of six had run, six of its seven notebooks carried zero executed cells and
zero outputs, and the flow offered the full declared scale anyway. A question
that offers the expensive run at that point is an invitation to say yes.

**The published question names the steps, never a count.** `resolve` and
`toDiscuss` carry the runnable `discuss` command; the sentence names each step
still short, the same shape `POSITION_RUNG_SKIPPED`'s own detail uses when it
names the items that came up short. It asks the repair choice — do it now, or
record why it is deliberately deferred — and never the flow question, because
the flow question is the offer this rung exists to withhold.

### `nextStep: "pilot-decisions"` — every step ran, and each one owes its own decision

**What a finished pilot unlocks is not permission to launch.** The flow runs as
it stands, which proves that it runs; its notebooks run, which proves that it
shows what was agreed; and only then does the flow return to its first step and
go one step at a time, deciding for each one how the full run carries it — sent
to a worker for the steps that need one, kept local for the steps that do not.
This rung is the start of that pass, and the offer of the declared scale waits
behind it.

**One question per step, each retiring on its own.** `toDiscuss` carries the
rung's own question first — what state the flow is in, and where its outputs are
— and then one entry per step that has not been decided yet. Every entry is a
runnable `discuss` command, and `discuss` buckets by exact question text, so
answering one retires one. Nothing new records the answers: `discuss` already
does, and building a second approval surface beside it would give two places to
look for the same decision.

**Never-asked is not decided.** A step whose question nobody has asked appears in
no open bucket either, so the pass reads which texts were ANSWERED rather than
which are open. Reading the absence as agreement is silence taken for consent.

**A report in drift is named here, and holds the pass until it is
acknowledged.** These decisions are taken over the artefacts a human reads, so
a pass that stays silent about the state of those artefacts is telling the
operator the document is fine. `report.liveFindings` names the findings that are
about this code — a finding stamped `fromStaleNotebook` describes a run the
repository has already moved past and is not one — and while any of them stands
unacknowledged this rung keeps the answer, publishing the acknowledgement
BEFORE the per-step questions. Measured: on a real repository the report was in
drift with five kinds of finding about the notebooks the pilot had just
produced, and the ladder walked into this pass anyway; `report-first` sits below
it and would have said the same thing after the decisions were already taken.

It is an acknowledgement and **not a wall**. A report at pilot is legitimately in
drift — a section whose run has not happened renders an absence — and for some
findings the repair *is* the full run, so a hard gate would refuse the pass that
authorizes the run in order to fix the report the run is what fixes. The exit is
the operator's own and is the one the question already offers: repair the report
now, or record why the decisions are taken over it as it stands. Nothing new
records that answer either — `discuss` buckets it by exact text like every other
question in this pass, and a finding appearing or clearing re-opens it, because
that is a change of state and not a moving count.

**And which steps the pilot opened no notebook for is named in the same
sentence.** Naming where the outputs are and staying silent about the steps that
rendered none tells an operator they are looking at the whole flow when they are
looking at part of it — six paths named out of ten declared steps, on the
repository this was measured on — and this is the last rung before the decisions
that put a step on a remote worker, whose own artefact may be one of the notebooks
nothing ever executed. The sentence names them and the pass carries on; nothing is
refused, and a target that deliberately computes in a library reads its own design
back rather than a finding.

**Which steps need a worker is not answered here.** `remoteExecution.necessity`
classifies job folders — must-remote, local-sufficient, or optional with the
missing fact named — and a job folder is not a step: nothing declared ties one to
the other, and inventing the link would be the forge deciding a repository's own
layout for it. Read that classification beside this pass; it informs the
decisions and never makes them.

### `nextStep: "search-first"` — a declared search has not chosen anything yet

**This rung asks the flow question, and used to publish nothing.** A search is
an experiment, declared as one, with a scale of its own — so this is one of the
three answers where the standing rule applies: continue the flow toward the
declared scale, or complement the experiments first. `resolve` and `toDiscuss`
carry the runnable `discuss` command that opens it; the question names the
DECLARED scale and never the achieved one, so it stays byte-identical across
polls while the decision has not changed.

`search` carries the same reading `verify` already reports (see the hard rule on a
search being an experiment, declared as one, under
[Proving the comparison measures anything at all](#proving-the-comparison-measures-anything-at-all)).
Two fields fire this rung, sharing one remedy: `recordFound` — a search block is
declared, and its own `record` does not exist where the declaration says it lives —
and `scaleSatisfied` short of `true`. Nothing here learns what the search is
choosing — the declaration does, and this only asks the filesystem whether the
answer is there and at the scale the declaration itself requires.

**`scaleSatisfied` is a tri-state, and both non-`true` values fire this rung.**
`search_state` reads the record's own recorded scale along exactly the axis
names `requiredScale` declares, and reports `recordScale` beside it.
`scaleSatisfied: false` means the record names every declared axis and falls
short on at least one — read `recordScale` next to `requiredScale` to see which
one. `scaleSatisfied: null` means the record names none of the declared axes at
all: an unprovable precondition, not a satisfied one, the same doctrine the pin
probe already applies to a question it cannot ask. Neither advances the ladder,
and the cost is accepted rather than softened: a target whose record stays
silent about the declared axes now refuses here, where it used to pass on
`recordFound` alone.

**Why it sits after `wiring-first` and `poll-first`, and before `report-first`, and
why that order is not a preference.** `wiring-first` stays ahead because correcting a
fork changes what an arm computes, which changes what a search over that arm would
find: searching first against a forked arm would spend the search on a term the
proposal does not state, and none of that time is recoverable. `poll-first` comes
next because a submission already out may be the very search this rung would send the
reader to run again — asking a second time would spend real quota on a duplicate
rather than catch a value nobody has chosen yet, so waiting is asked about before
searching is. Once nothing is pending, `search-first` fires because a run whose
governing scalar has not been chosen does not yet have a configuration to run — worse
than a wrong report, and far cheaper to catch before any machine time is spent.
`report-first` stays last: a report in drift still describes a sound run, wrongly,
which costs a sentence rather than the campaign.

**The forecast is reported beside the declaration, never gated.** `costForecast`
projects the search's own `requiredScale` from the same measured duration
`_projected_cost` already uses for the benchmark, following the same discipline: a
projection from data, not a guess, and a stated reason rather than a silent `None`
when nothing was measured to project from. Read `aboveMeasuredScale` before saying
anything about how long the search will take — **a search declares its own scale, and
it is not the pilot's.** A pilot reporting a light scale says nothing about the
search that is about to run first under a heavier one it declared for itself; missing
that gap once is how a few minutes of pilot time gets mistaken for the cost of the
whole flow.

Read `contention` and `basis` next. A projection (`costForecast` and the benchmark's
`projectedCost` alike) scales one duration, and runs that share a machine compete for
it: one pilot on eight workers took 2.42 times its single-process projection. When the
record's `reduction` names the `parallelism` it ran at (a positive integer), the
forecast reports it, `contention: "included"`, and holds at that parallelism only.
Otherwise it reads `parallelism: null`, `contention: "unmeasured"` and a `basis`
saying it is single-process, and no contention factor is supplied, because any factor
here would be chosen rather than measured. A `parallelism` of any other shape is
echoed as `parallelismMalformed` and never read. To forecast a campaign at its planned
parallelism, run the pilot at that parallelism and record `parallelism` beside its
duration.

### `nextStep: "report-first"` — the document does not yet agree with the run

`report` carries the same reading `verify` already reports (see
[The report contract, and why `verify` reads the document too](#the-report-contract-and-why-verify-reads-the-document-too)),
and this rung acts on nothing but its `status`: anything other than `ok` blocks the
run, because a document a human reads is about to be offered and it does not yet
say what the run says.

**Why it sits last of the four that block a run, and why that is not a
preference.** A forked arm costs the campaign, because every number came from
mathematics the proposal does not state, and no repetition count repairs that. An
already-pending submission costs real quota a second time when it is offered a fresh
run instead of being waited on — quota already spent, not merely projected, which is
why it outranks a value nobody has chosen yet. A missing search value costs nothing
yet computed, because the run has no configuration to launch at all. A report in
drift is narrower than any of the three: it describes a sound run, wrongly, and
correcting a sentence costs a sentence, not the campaign — which is exactly why it
does not outrank a forked arm, an already-pending submission, or an unchosen scalar.
It still blocks, because a wrong sentence printed with the authority of thirty
repetitions behind it is worse than no sentence.

**Re-execute before judging.** A finding read off a stale notebook describes the
run that happened, not the code that is there now. Correcting it before
re-running corrects two different things at once, and the second correction is
invented — nothing behind it was re-measured. Re-run first; if the finding
survives the re-run, it is a claim about the code as it stands. If it does not,
it was never a claim about the code at all, only about a run that no longer
exists.

**What the statuses mean here.** `report`'s own status describes the document: a
report `drift` is the contract itself being violated — a number typed by hand,
one measurement rendered twice, a table with no conclusion after it — and it can
be true while every number the run produced is correct. A notebook's status
describes the evidence the report was rendered from, on its own separate ladder:
`empty` before any code cell has run, `errored` when one raised, `stale` when one
has not run at all, and `stale-sources` when every cell ran clean but against
code that has since changed underneath it. `fromStaleNotebook` on a finding is
the join between the two — it says the finding was read off a notebook that is
not `executed` against the current tree, so what it names is a property of a past
run rather than a property of the document as it stands right now.

### `nextStep: "benchmark"` — propose the wiring, then train both and measure

Only reachable once `backend.trainable` is true and a baseline exists.

`probe` returns a `wiring` draft assembled from each module's `__provenance__` and
from the baseline's own code — the modules with their sections and equations, the
baseline package, what it trains on and how it loads it.

That is raw material for you, not output for the user. **Open a conversation with it**
— see [Design — a conversation](#design--a-conversation-and-one-question-at-the-end-of-it).
Say what you found in their repository and what you would wire to what: which modules
carry the trainable terms, where the backbone's features enter, what the head predicts
over. Mark what you read, what you inferred and what you assumed, and raise whatever
you could not settle. Then work it out with them.

The harness knows how to train and measure; it cannot know what makes *this* method
trainable, and that is the one part worth the user's attention. Handing them the three
questions unanswered wastes the context this skill is already holding.

The draft's `offer` is `fromBaseline` and nothing else: the backbones, task names,
trained weights, **data entry points** and notebooks the prior work actually uses,
read from its own code. That environment is where its published results were
obtained, so it is the one a comparison means something in.

The entry points matter more than the names. A task name says what was measured; a
loader says how to measure it again, and the wiring needs the second. Notebooks
outside the proposal are read too — that is usually where the prior experiments
actually ran.

**Read `acquisition` before saying anything is unavailable.** A package can resolve a
directory it never creates; what creates it usually lives in a notebook, and a reading
that stopped at the package would conclude the material is unobtainable while the
thing that obtains it sits one file away. `acquisition` reports what was found about
how each side gets hold of what it trains on — a download, a clone, an archive, a
mounted directory. Material that is absent until something runs is not material that
cannot be had, and treating the two alike discards most of a user's experimental
ground for no reason.

**Read `foundNothingFor` before concluding anything.** The reading is a heuristic over
English word-stems and structure, so it misses a plausible variant and misses a
repository named in another language entirely. Where it reports finding nothing for a
kind, `readBy` says how it looked: put that to the user and ask them to point, rather
than telling them their baseline has no data layer. An empty list is a miss, and
presenting it as an absence would be the flow concluding something it never
established.

Nothing is suggested from a list. This is a forge for papers, not for one field: it
cannot know which models or datasets are reasonable for mathematics it has not read,
and offering a catalogue of well-known benchmarks would push both implementations
into a setting neither has been measured in. If the baseline's own environment is too
heavy to screen with, say so and let the user name a lighter one.

Write the completed wiring as `src/<Package>_Benchmark/wiring.py`, exposing
`build_new`, `build_baseline` and **`build_data`**. `build_baseline` may be `None`
when the prior work cannot run under the common reduction as it stands: that is a
`not applicable` with its reason, and the baseline is never edited to make a
comparison possible.

The harness owns training and measuring and nothing else: it names no dataset and no
architecture, because a catalogue there would dictate the experiment — the wiring
would be forced to pick whichever well-known set the baseline happens to touch, and
the reported common environment would be an intersection with that list rather than
the environment the prior results came from. `build_data` belongs to the wiring for
the same reason the builders do.

Materialize these four, fill in the reduction, and execute the notebook. Run
`materialize --stage harness --plan <path to the approved plan>` — no `--seed`: none
of the four carries a `{{SEED}}` token (`probe.ipynb` carries `{{SEEDS}}` instead,
answered later, at probe time). Unlike `objects`, this stage needs no step-8
precondition and its three `.py` destinations parse cleanly the moment they land:

| Written into | Written from |
| --- | --- |
| `src/<Package>_Benchmark/__init__.py` | `assets/kit/src_benchmark/__init__.py`, copied verbatim and never populated — see [The benchmark declaration, and its five blocks](#the-benchmark-declaration-and-its-five-blocks) |
| `src/<Package>_Benchmark/benchmark.py` | `assets/kit/nb/benchmark.py` |
| `src/<Package>_Benchmark/verdict.py` | `assets/kit/nb/verdict.py` |
| `<Name>/Notebooks/probe.ipynb` | `assets/kit/nb/probe.ipynb` |

The agent never copies these four by hand — the same `materialize` discipline step 5
and step 9 use, and `wiring.py` above stays the one bespoke-authored exception: it is
never a kit destination and this command never touches it. This is also the one and
only stage that ever writes `src/<Package>_Benchmark/` into a target at all — see
[`nextStep: "declare-first"`](#nextstep-declare-first--the-benchmark-package-exists-and-says-nothing-yet)
for why the scaffold stage no longer does.

`assets/kit/nb/` stages what the notebooks need; it does not mirror where any of it
ends up. Python that lives beside a notebook is a
stray module the moment it is committed; see [Target layout](#target-layout). The
notebook therefore addresses the harness by repository-relative path from `src/`, and
runs it from the harness's own directory so that its `verdict.py` and `wiring.py`
siblings resolve. Without
`wiring.py` the harness refuses and says what is missing. It trains each
implementation over every seed, measures accuracy, wall time, peak memory and
parameter count, and writes `<Name>/Results/Probe_results.json`.

**[GATE]** ask before running: it is quick by design, but it is still the user's
machine, and it downloads a dataset.

Execute the notebook with the target repository's own interpreter, as with the suite —
and with that venv's `bin` on `PATH`, for the reason the isolation section gives:
the kernel resolves its own interpreter off `PATH`, never off whatever launched
jupyter. `benchmark.py` refuses under any other and says which one to use — for this file that
is not a hygiene rule but the measurement itself: wall time and peak memory describe
whichever environment ran them, so a foreign interpreter produces a correct
measurement of the wrong thing and the summary would attribute it to this repository.
Where there is no interpreter of its own to compare against — a hosted runtime with no
virtualenv in the checkout — it stamps interpreter, platform and device into the
summary instead of refusing, so a table produced elsewhere is labelled as produced
elsewhere rather than attributed to this machine.

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

### `nextStep: "build-first"` — a standing decision was accepted, and nothing is built yet

Reached once either standing decision — the comparison's or the acid test's —
has been answered `decision: "yes"` and nothing has been wired or run for it
yet (design D19-D21). The decision is already made; what is owed is the
wiring, the same reading that already makes `wiring-first` a repair rather
than an offer, and this rung shares its kind.

**A decision reopens on the answer alone, never on waiting for structure to
exist.** Either standing decision may be changed after a decline by
answering the same question again through `discuss --decision yes|no` — a
closed token, refused `DISCUSS_DECISION_NOT_A_TOKEN` as anything else, the
identical discipline `offer`'s own `--answer` already keeps. Answering
`yes` reopens the decision immediately, by the strength of that answer
alone: it is never reported as declined merely because the benchmark
package or the wired acid test has not been built yet. Answering `no` again
leaves it declined. No dedicated reopening code path exists beyond reading
the token — the same "the reopening code is the absence of a branch" rule
that already governs the harness-materializing path.

**A legacy or free-text answer with no token reads as `"no"`.** Before this
capability, the only reachable meaning of an answered comparison/acid-test
bucket was "declined", so a bucket whose last event carries no `decision`
field — every decline recorded before this capability existed, and any
answer given through plain `--answer` alone — is read as `"no"`. This is a
migration rule, not an interpretation of prose: no existing ledger event is
rewritten, and nothing re-fires an offer already settled the day this
capability lands.

**One rung, a branching sentence.** The comparison's own acceptance act
(`materialize --stage harness`) and the acid test's (declaring a
`__steps__` entry — this rung must never route through the harness stage)
differ, so the published sentence names which decision was accepted rather
than describing an act generic enough to cover both falsely, and the
matching draft rides beside it: `wiring` when the comparison was accepted,
`validation` when the acid test was — never both at once.

**Placement never moved.** This is a fourth arm inside the exact same
last-among-the-overrides branch design D13 already places `benchmark`/
`validate`/`declined` in, guarded by the identical
`resolved["status"] == "absent"` condition — never a new position in the
chain. A genuinely owed repair above it (an arm nothing calls, a submission
already out, a declared search with no record, a report in drift, a
declared flow still owed at pilot) continues to outrank it exactly as it
outranks `declined` and `validate`.

### The report contract, and why `verify` reads the document too

Every other check in this skill asks whether the run was sound. None of them asks
whether the document a human reads says what the run says — and a sound run with a
report that contradicts it is worse than no report, because the contradiction
arrives with the run's authority.

So the benchmark package declares its report alongside its arms, and `verify`
checks the notebooks against that declaration. It is a declaration and not a list
of names in the skill, and that is the whole point: nothing here may learn what a
metric is called in somebody's field.

```python
"report": {
    "renderers":       ["tables.render", "tables.render_summary"],
    "conclusions":     ["tables.conclusion", "tables.conclusion_scale"],
    "conclusionEntry": "tables.conclusions",
    "objectiveEntry":  "tables.objective",
    "figures":         ["figures.curves", "figures.grid"],
    "dimensions":      {"accuracy": "higher", "seconds": "lower"},
    "components":      {"terms": ["fit", "penalty"], "share": "penaltyShare"},
    "selections":      {"SEEDS": "the pilot, a prefix of FULL_SEEDS"},
    "record":          "tables.json",
    "records":         ["Results/summary.json", "Results/Benchmark", "Results/figures"],
}
```

Every module name above is invented, and invented from exactly two: `tables` and
`figures`, the two the kit's own declaration already uses. That is a rule and not
a habit — a worked example is the one place a reader most readily mistakes an
illustration for a practice, so an example that reached into somebody's
repository for a module name would be teaching that repository's layout as
everybody's. The suite holds this example to those two names.

What that buys, and each one is a way a report goes wrong while every number
behind it is right:

- **No measurement typed into prose.** A number written by hand cannot be
  recomputed, so it survives the run that contradicts it. This is the sharpest of
  the checks: it catches a conclusion written by hand, a caption left from an
  earlier campaign, and a sentence the figure beside it already disagrees with.
- **One measurement, one place.** Two renderings of one number are two things that
  can drift apart, and the reader cannot tell which one moved. The cell that
  writes the record is exempt — the record is supposed to hold everything.
- **Framing before, conclusion after.** What is measured, why, and which direction
  wins; then a conclusion that comes from a function. A reader should not have to
  reverse-engineer the direction of a column, and a conclusion typed by hand is
  the first failure wearing a sentence.
- **Selections computed, or declared with the rule that fixed them.** A constant
  naming a subset of another constant is a choice somebody made. It is legitimate
  when the rule looks at no outcome — and that is a claim a human makes, so it is
  stated where it can be argued with rather than inferred from the shape of a list.
- **A conclusion must be able to come out different.** `conclusionEntry` is run
  over the record and over the same record with its numbers permuted; identical
  text means the conclusion is tied to nothing. This is `trivialAssertions` pointed
  at the report — a conclusion that cannot come out wrong is measuring nothing, for
  exactly the reason an assertion that cannot fail proves nothing.
- **A cell that shows nothing showed nothing.** Every check above reads the code a
  cell contains. Three failures live only in what it *emitted*, and all three
  survive every reading of the source: a measurement computed and never displayed,
  a figure that came out as a *description of a figure*, and a rendering that came
  out as a *sentence*. The second hides well —
  displaying a figure object where the runtime never registered an image formatter
  emits a line of text like `<Figure size 640x480>`. The cell ran, raised nothing,
  produced an output, and anything reading `execution_count` and the error list
  calls it green. `verify` reports these as `unrendered` and `describedNotShown`.

  The third hides best of all, and it was measured rather than argued: in one real
  report, of 57 rendered outputs 6 carried a table and 21 explained why they had
  nothing to show. Each of those cells called a declared rendering, ran clean,
  emitted markdown, states its aim and carries a conclusion — so every check above
  stays quiet and the reader is told the document is fine. `verify` reports it as
  `statedNotShown`, and it is judged by the **structure** of what the cell emitted
  — a mime the runtime rendered as something other than prose, a markdown table's
  rule, a measurement, rows of values — and never by what the words say. Matching
  sentences would write one repository's prose, in one language, into a forge that
  is not allowed to know whose repository it is, and would go quiet on the next
  one. It is reported and never refused: a rendering legitimately has nothing to
  show before the run that fills it, and what is wrong today is only that the
  absence is invisible. Named and counted, the reader judges.
- **A term's share, not just its magnitude.** A term correctly implemented and
  multiplied by something tiny produces a column of near-zeros that reads like a
  result, and the numerator alone cannot tell *the term commanded nothing* from
  *the term was scaled to nothing* — both print small. `components` names the
  terms the arms combine and the dimension carrying their share; `verify` reports
  a declared term the record never carries as `componentsNotRecorded`, and more
  than one term with no share — or no declaration at all — as
  `componentsWithoutShare`. This one was measured rather than argued: a repository
  shipped `contribution` without its denominator and every other check was green,
  and what the ratio then showed on the first run was the two families optimizing
  objectives balanced an order of magnitude apart.

  It is a declaration and not a list here for the same reason the metric names
  are: nothing in this skill may learn what a term of somebody's objective is
  called. The check asks whether each declared component is recorded, never what
  it means.
- **A conclusion that restates its table has not concluded.** `restated` crosses
  from a rendering to the sentence written about it — the one direction every other
  duplication check is blind to, because the second copy is not a rendering. It is
  answerable only from what the two cells *emitted*: the number appears in neither
  source. A conclusion may name the value it rests on; past two it has stopped
  saying what the table cannot and started saying the table again. This one was
  also measured rather than argued: five conclusions in a real report were
  enumerating their own tables, one of them twenty-one numbers deep, with every
  other check clean.
- **And neither is a record nobody declared.** Every check above fires only on
  something somebody wrote down, so the repository running an experiment nobody
  accounted for is exactly the one where they all stay quiet. `records` names what
  a run leaves under `Results/`; anything else there comes back as
  `undeclaredRecords`. What it catches is a second experiment arriving as a file —
  its own scale, its own material role, its output feeding every later run — while
  the contract describes only the first.

  Format-agnostic, deliberately: filtering to `.json` would hand a silent pass to
  every repository that records in `.csv`, `.parquet` or `.npz`, and silent is the
  failure this exists to prevent. A repository that archives figures under
  `Results/` declares the directory once, and that declaration shows in the echo,
  so opting out of file-by-file accounting is a visible decision and not a gap.

  Scoped to `Results/` and not to the whole product, because `Models/` holds one
  artefact per checkpoint by this layout's own design; reporting sixty manifests
  as undeclared would be a finding nobody reads.

  It says a file is unaccounted for. It cannot say the file is a second
  experiment — what it does is force the question, which is where somebody has to
  write down what the thing is.
- **A picture nobody declared is a contract that is short.** `undeclaredDrawings`
  names a cell that showed an image through no declared call. Without it the two
  findings above would be a courtesy rather than a net: they can only fire on a
  drawing call somebody wrote down, and the repository most likely to ship a figure
  that never rendered is exactly the one that never wrote one down — there the
  check goes silent and the report comes out clean. This was not an argument, it
  was measured: the first run of these checks against a real repository passed with
  `figures` empty and three cells drawing.

Two entries here are declarations and not lists in this skill, for the same reason
the metric names are not: `conclusionEntry`, because a check that has to guess at
signatures ends up reporting *could not exercise*, and that reads as a pass; and
`figures`, because asking whether a picture was shown must not require knowing how
anybody draws. A check that guessed at plotting libraries would go silent the
moment a repository used a different one. Declaring no drawing calls is not the
same as drawing nothing, so the echo of the contract shows the key even when it is
empty — and `undeclaredDrawings` is what makes the empty case cost something.

Two things do not need the declaration at all, because they read the *shape of the
output* instead of the code. An output the runtime could render only as plain text,
whose payload is an object's repr, is a description of the thing where the thing
belongs — no library is named to see that. It is judged per output and never per
cell: a rich rendering stores its repr *beside* itself, so a displayed Markdown
block carries `<IPython…Markdown object>` next to its `text/markdown`, and reading
the cell as a whole calls every heading in the notebook a figure that never drew.

**Every one of these is read off what a cell emitted, so on a stale notebook it
describes the run that happened and not the code that is there now.** A finding
whose notebook no longer matches the tree carries `fromStaleNotebook`. Without
it the two halves sit in one output two keys apart and nobody crosses them: the
finding says a conclusion restates its table, the notebook list says that
notebook is `stale-sources`, and the reader concludes the code is defective. It
was observed doing exactly that — a session proposed correcting a conclusion
that had already been corrected hours earlier, which risks a second, different
correction of the same thing. Re-run first; a finding that survives the re-run
is the one about the code.

`verify` reports this as `report`, beside `structure`, `fidelity`, `audit` and
`validation`. **A report in drift is reason not to offer the full run** — `probe`
answers `report-first` instead of `benchmark`. A campaign measured in hours can
otherwise print a wrong conclusion with the authority of thirty repetitions, and
correcting it afterwards costs the campaign rather than the sentence.

### Writing the report, not only checking it

A rule that exists only as a check is paid for with a campaign: the notebook is
written wrong, the grid runs, and the defect surfaces after the machine time is
spent. So the conventions below govern how the report is written, and the checks
above catch what slipped. None of them can be verified mechanically — that is why
they are here and not in the contract.

- **A figure is shown, never merely filed.** A cell that writes a picture and
  prints its path has reported a filename. The reader has to open something else
  to see what the cell claims to have produced, and a report that requires opening
  something else is not reporting. *Merely* is the whole of the rule: the archived
  copy stays, and stays vector — the notebook shows the picture inline **and** the
  cell writes the file a paper is built from. Both, and neither instead of the
  other. Nothing in `describedNotShown` or `undeclaredDrawings` reads what a cell
  wrote to disk, so keeping the archived figure can never be the reason a check
  turns red.
- **The framing is a paragraph, not a form.** What is being measured and how, what
  for, and what value would count as the good one. A reader should not have to
  reassemble the point from three bolded labels, and a template invites filling the
  slots rather than saying the thing.
- **A direction is not a target, and the target is computed.** "Higher is better"
  says which way to look and nothing about where good stops; a reader who does not
  already know the metric learns nothing from it. What they need is the landmark —
  a chance level, a bound, an agreement across runs — and that landmark is a
  number, so typing it into the prose ages exactly as a measurement typed into the
  prose does: the day a constant moves, the sentence goes on naming the old one.
  So the framing has a written half and a computed one. `objectiveEntry` is the
  package's call that states, for a dimension, the value being aimed at;
  `verify` reports a section that never states one as `unaimed`, and reports a
  package that declares no entry at all with that absence as the reason rather
  than passing it in silence.

  **What this must never become is a list of kinds of objective.** A check that
  could tell a chance level from a unit interval would have learned somebody's
  field and would go quiet in the next repository that measures something else.
  The skill asks only whether the section states its objective; what the objective
  *is* belongs to the package, exactly as the metric names do.
- **What the framing carries, the figure does not repeat.** No title restating the
  heading directly above it. No caption restating bounds the notebook already
  stated. Stating them twice is the duplication rule again, in two media.
- **Decoration appears once.** Axis labels shared by every panel collapse into one
  for the whole figure; tick labels stay at the border. But whether an axis really
  is shared is a claim about the data, so the drawing code **measures it** and
  collapses only what it found — a grid whose panels quietly differ in range, drawn
  as if they shared one, is a figure that lies in the direction of tidiness.
- **The picture qualifies, the table quantifies, and that is the order.** The
  figure shows the shape; the table that puts numbers on that shape reads better
  after it than before it.
- **The stamp is stated once, computed, and binds everything under it.** Bounds
  repeated on every table train the reader to skip them, which is the opposite of
  what they are for. The line describing a table and the stamp that bounds the run
  belong to the framing, not to the renderer's output.
- **The conclusion names who.** Not a description of the distribution — who is
  ahead, on what evidence, and plainly when the evidence does not reach far enough
  to call it. That last clause is not a hedge: below the declared floor of
  repetitions there is no verdict to give, and a conclusion that names a winner
  anyway is reading noise out loud.
- **A table reports the extreme only where the extreme is the unflattering side.**
  The best of N repetitions grows with the method's own dispersion, so printing it
  beside a mean flatters the noisiest arm — the same reason the median artefact is
  kept and never the best. A worst case is the other direction and informs.

### The record a later session reads

That summary is the record, and it is the only one. A later session reads it to learn
that a run happened, under which reduction, and against which revision — nothing is
stored outside the repository, so nothing can fall out of sync.

Three properties make it usable rather than merely present:

- **It lives where the verification looks.** A correct record at a path nobody opens
  protects nothing.
- **Its revision declares it stale by inspection**, with no bookkeeping anywhere else.
- **The readable summary beside it is generated, never written by hand.** It is emitted
  by the notebook along with the results, carrying the revision, the protocol read from
  the configuration, the arms and the numbers. Regenerated on every run, it cannot
  drift from what it describes, because it *is* what it describes. A hand-written
  summary is a second source of truth: it goes stale in silence and is believed anyway,
  which is the same failure as a notebook that exists and never ran.

The method's own package declares, in `__implementation__`, **which revision the
whole implementation is built against**, and the benchmark package declares
**which sections and equations each arm exercises**. Neither carries
`__provenance__` — the benchmark implements no equation — but without the two
together nobody can answer the question a new revision immediately raises: does
this change oblige the bench to change? Together, the drift report names the
arms a changed section reaches.

**And `__implementation__` declares its own premises beside `revision`**: what
kind of prediction the protocol assumes, over which statistical unit, by which
metric and in which direction. Those are what a change of reach destroys — a
formulation that moves from deciding a class to estimating a quantity leaves
every arm intact and every dimension meaningless. Nothing can rule on that
automatically, and nothing should try. What the tool can do is put the
premises beside what changed, so the question *is this still the same
experiment* gets asked with them in view instead of not getting asked at all.

### What has to survive the session, and what cannot be recovered later

- **Two phases, two notebooks: one trains and measures, the other loads and analyses.**
  The split is what makes a later question cheap — anything computable from weights and
  data can be added whenever it occurs to somebody. It comes with a consequence that
  has to be said out loud rather than discovered: **whatever exists only while training
  runs must be recorded now or it is gone.** Loss trajectories, per-epoch measurements,
  what a quantity did on its way to its final value — none of that can be recovered
  from a checkpoint, and re-running the campaign is the only way back.
- **A manifest with explicit indices beside every kept artefact.** Rebuilding the
  material by re-running the draw depends on every library involved producing the same
  permutation it produced the first time, which nobody promises across versions. Write
  down which inputs went where. A model that travels without its material can only be
  measured on something else.
- **The formulation's preconditions are guaranteed by the sampler.** Where the
  mathematics requires a non-empty index set, a positive trace, a class present on both
  sides, the pipeline arranges it by construction. The code that raises is right to
  raise; the mistake is letting a draw provoke it in the middle of an epoch and reading
  the crash as a defect of the method.

### A ladder, not a duel

Two complete methods measured against each other answer *which one wins* and cannot
answer *which piece did the work*. The second question is the one a paper has to
answer, and it costs almost nothing to ask at the same time: the arms differ from one
another by one thing at a time, and the pairs are written down before anything runs.

- **A floor for every statistical unit, not one floor.** The arm with its adaptation,
  correction or auxiliary term switched off — everything else identical — is what a
  gain is read against. When the two sides predict over different units, each family
  needs its own floor, or a gain cannot be separated from the representation that
  produced it.
- **One rung, one difference, and its reading declared.** Write what each pair is
  supposed to reveal next to the pair. A ladder whose rungs differ in two things is a
  table of numbers nobody can attribute.
- **Equalize what the arms *touch*, not only what they *compute*.** This is the
  expensive one. An arm that looks at data another arm never looks at is already
  different, even when it computes nothing from it: shared mutable state — the running
  statistics of a normalization layer, a cache, a moving estimate, how much of the
  random generator each arm consumes — is a channel through which arms differ without
  anyone declaring it. Enumerate that state and make every arm touch it identically,
  including the floors that have no use for it. Otherwise the rung credits the term
  with what the exposure did.
- **Equalize the unit of work per step.** Material per update and number of updates,
  fixed and declared. Two sides fed different amounts per step are being compared on
  their optimizer.

### Proving the comparison measures anything at all

A rung can read zero for two reasons that look identical on paper and are not: the
mechanism does nothing, or the mechanism was given no weight. Three habits keep them
apart, and each is cheap enough that skipping it is never the economical choice.

- **Refute a result with the smallest decisive experiment.** When a difference is
  credited to a mechanism, switch that mechanism off and see whether the difference
  survives. Two runs settle what an argument cannot, and the answer arrives before
  anything is written down. This is the audit's adversarial refuter, pointed at
  results instead of findings.
- **Report each declared component's share of the objective.** A term that is
  correctly implemented and multiplied by something tiny produces a table of exact
  zeros that reads like a result. Without the share, "it had no effect" and "it had no
  weight" are indistinguishable.
- **Calibrate the free scalars by measurement, not by inheritance.** A coefficient
  taken from prior work was calibrated for prior work's scale. Sweep it over decades
  on a single cell and find where the term begins to move the outcome, before the grid
  runs. It costs minutes and decides whether the whole campaign says anything.
- **A run split across machines is still one run, and only if it is declared as
  one.** When a campaign is too large for the machine in front of you, it gets
  divided — and the division is a choice with a wrong answer. `verify` reports
  `distribution`: the `axis` a shard is a subset of, which measurements are
  `poolable`, which are `perEnvironment`, which vary `perRun`, and what must be
  `identicalAcrossShards`.

  **The axis may be anything except a comparison.** Divide by repetition, by
  subject, by fold, by whatever a repetition is made of here — but never by arm.
  Every rung of the ladder subtracts two arms, so splitting there puts that
  subtraction across a hardware boundary, and the rung then credits a mechanism
  with what the machine did. That is the one split no care afterwards can undo,
  and it is the only one this refuses; what the axis *is* instead is the
  repository's business, and a skill that required a particular one would work
  for the repository it was written against and no other.

  **A measurement describes whichever machine produced it.** Accuracy is a
  property of the method and pools freely; wall time and peak memory are
  properties of the machine, and averaging them across two of them yields a
  number that describes neither. A measurement that varies from one run to the
  next even holding everything else fixed belongs to neither: it is `perRun`,
  and reading it one machine at a time would claim a stability across runs that
  was never measured. So every declared dimension belongs to exactly one of the
  three. In none, and it is silently dropped — a column nobody notices is gone.
  In more than one, and there are two answers to one question. Which is which
  the repository says; nothing here learns what a dimension measures.

  **Requesting hardware and receiving it are two obligations.** A service
  allocates by availability, so a shard can ask for one class and land on
  another without a word. Pin it where the launching lives, and stamp what
  arrived where the measuring lives; group cost by the stamp and never by the
  request. A stamp that cannot tell two accelerators apart is a label that lies,
  and grouping by it is worse than not grouping at all.

  **Shards agree on what they said had to agree, or the merge refuses.** Not
  averages — refuses. A different epoch count is a different experiment rather
  than different hardware, and one table drawn over both is a table nobody can
  attribute.

  **`verify --shards <dir>` is what produces that refusal**, and it is the only
  way to. Give it the directory the returned shards landed in — one
  subdirectory per shard, each holding its own `shard.json` stamp — and
  `distribution.shardsDisagree` names every `identicalAcrossShards` field the
  stamps disagree on, while `distribution.shardsArrived` lists the shards that
  were actually read. Omit the flag and both are empty, which means nothing was
  checked rather than nothing was wrong: a refusal nobody attempted reads
  exactly like a merge nobody objected to, and that is what this flag exists to
  separate.

  **Arrival is not evidence that a shard reports on the code you are running.**
  A shard folder is a file left behind by whatever ran; its presence says
  nothing about which code wrote it, and ticking a step because a directory
  exists is an attribution nobody measured. The declaration may name where a
  shard records its own code identity — `currentWhen`, an optional dotted path
  into the `shard.json` stamp, e.g. `"currentWhen": "evidence.sourcesDigest"` —
  and then a shard counts only while the value there still matches the code as
  it stands; one that arrived from code the repository has moved past reads as
  unmeasured, never as a step reached and never as a step that never started.
  Declare nothing and arrival alone decides, exactly as before. Which field
  holds that identity is the repository's to say: the forge only compares, the
  same division `identicalAcrossShards` already keeps.

  **`gate`, `close`, `discuss` and `probe` carry no `--shards` flag of their
  own, so a `@shard` witness ticked by `position --shards <dir>` used to read
  `unmeasured` at every one of them forever — permanently, since none of them
  has a flag to re-supply the evidence `position` already looked at once.**
  The declaration may name where returned shards land — `shardsRoot`, a
  sibling optional key to `currentWhen`, e.g. `"shardsRoot": "<Name>/Results/
  shards"` — and every command that reads a position section resolves that
  same directory automatically, exactly as if `--shards <dir>` had been given
  to it. A tick written from real evidence stays checkable everywhere that
  evidence is read, not only at the one command that happened to carry the
  flag. Declare nothing and a `@shard` tick still reads `unmeasured`
  everywhere, exactly as before this key existed — but `gate` and `close`
  now refuse it with `POSITION_SHARDS_UNDECLARED`, not `POSITION_UNBACKED`:
  the tick was never told where to look, which is a different, narrower fact
  than "looked, and found silent". `verify`'s own `--shards` stays
  explicit-only, deliberately: it reports over whichever directory an
  operator names, not a gate the declaration should widen on its own.

  **What refuses here and what averages is a division of labour, not an
  oversight.** This skill refuses and stops. It never averages, pools or merges
  a shard result, because a refusal is general — it needs only the fields the
  declaration marked identical — and an average is not: what may legitimately
  be pooled, and how, is the repository's own question, answered in its own
  harness with its own vocabulary. A forge that averaged would have to learn
  what a cell means, which is exactly the knowledge it may not have.

  And scale is recomputed from what came back, never from what was asked for.
  Three shards planned and two returned is a smaller campaign, not a failed one,
  and the record says which repetitions the verdict actually rests on.

  No service is named here, and none should be. Where the work goes is the
  repository's decision, declared as a backend and a capacity; the launcher
  that knows about it is general machinery, identical for every
  implementation, and now lives in the forge's `remote-execution` skill,
  with service knowledge confined to a single adapter file there.

  This revokes only half of what this rule used to say. The sentence above —
  no service is named here, and none should be — governs what the RECORD
  names, and nothing about it moved: `DISTRIBUTION_DECLARATION` and
  `distribution_state` still name none, and the leak test still holds them
  to it. What is revoked is the half that governed where the launcher's CODE
  lives. A reader who meets that placement quoted elsewhere should read it
  as retired; the sentence beside it never was.
- **And a search is an experiment, declared as one.** The moment a value is chosen
  by looking at outcomes, the thing that chose it needs everything a run needs, and
  three of those are invisible until somebody walks into them. `verify` reports
  `search`: what is being chosen, its `requiredScale`, its `role`, its `tieRule`,
  and — optional, and the one every later reading hangs off — its `record`.

  **Its own scale, declared apart from the one it is running at.** Lowering a
  search to test the pipeline cheaply writes a value found in a landscape nothing
  else trains in, and every later run consumes it without a word. Without both
  numbers the record and the configuration agree with each other and it all reads
  as finished — the same failure the pilot stamp exists to prevent, one experiment
  over.

  **Its own material role, disjoint from the verdict's.** Choosing by outcome on
  the material the verdict rests on makes the verdict report a decision it already
  made, by an amount nobody can subtract afterwards. Carve the role, and fund it
  from material the verdict does not lose — the arithmetic of what the verdict must
  resolve does not bend to make room for a search.

  **A tie rule that was written, not inherited.** `max` leaves the first element
  winning by accident, and where the objective is flat the accident is what
  chooses — which is exactly the stretch where a term is inert and every candidate
  scores the same. Write which way ties go and why.

  No tool is named here and none should be. Which search a problem wants depends on
  the problem: an adaptive sampler returns unequally sampled points, and this skill
  asks afterwards for the whole landscape to support a claim about scale, so
  recommending one would be pushing an output shape that contradicts its own
  reporting rules. What the skill asks is that whatever was used declares itself.

  Declaring a search is optional, because most repositories search nothing. What
  makes it bite is `undeclaredRecords`: a search leaves an artefact where the
  records live, so it has to be named there, and naming it is the moment somebody
  has to say what the thing is.

  The limit, stated rather than papered over: nothing here can check that the role
  is disjoint from the verdict's, because it does not know the material. It can
  only require that the role be named, which is what puts the question in front of
  whoever writes it.

### The pilot, and never launching the long run blind

A campaign that takes a day to run has to be wrong cheaply first. The pilot is not a
rehearsal of the campaign — it *is* the campaign, at a scale small enough to be wrong
in ten minutes.

**What a pilot is, said plainly, because everything below assumes it.** The pilot is
the declared flow walked with the declared notebooks, at whatever reduced scale the
target declares, so that the artefacts that will later be sent have been executed and
read first. Both halves are the definition. A run at a small scale that never opened
the notebooks is not a pilot of the thing that gets sent: it validates one path while
the artefact somebody will hand to a worker — or hand to a reader — is the other, and
nobody finds out until the expensive run comes back wrong. Measured, on a real
repository: of ten declared steps six executed a notebook and four computed by calling
the library directly, and the notebooks those four own, one of them the very file a
remote worker would have been given, were never executed by the flow at all.

- **Two knobs separate the pilot from the full run, and nothing else does.** Every
  number that defines the experiment lives in one configuration; the pilot is that
  configuration with the repetition count and the length lowered. If the pilot is a
  different program it proves nothing about the program that matters.
- **The configuration declares the scale the verdict requires, not only the scale
  running now.** Without both, a record of the pilot and the configuration agree with
  each other and everything looks finished.
- **Time one cell before committing the grid.** An estimate of the cost is cheaper
  than the cost, and it belongs as the notebook's first step rather than as a sentence
  in conversation. Report the measured figure, never the guessed one.
- **Repetitions go in the outermost loop**, so a repetition varies the material it
  draws and not merely the initialization.
- **Every change is exercised at pilot scale.** Adding an arm, adding a test, moving a
  proportion: change it, run it short, look, change it again. That cycle is what the
  pilot exists for.
- **After a revision changes, the short run comes back before the long one.** The arms
  may have moved with the mathematics, and the temptation once the code is adjusted is
  to release the whole thing.
- **Nothing releases the full run except an explicit authorization.** Not a clean
  verification, not a green pilot, not the agent concluding it is ready. Green is not
  permission.

While a run stands at pilot scale, its numbers are never quoted as results — not in
the report, not in the summary, not in conversation.

### The partition, when the comparison trains

This section is about training, so it says the ordinary thing plainly rather than
leaving it to be rediscovered: **propose a training / selection / evaluation split, by
name, in the first draft.** Whatever is fitted learns from the first; anything chosen
by looking at outcomes — a coefficient, a stopping point, a threshold — is chosen on
the second; the verdict is read only from the third. They are disjoint, and nothing
from the third is seen before the verdict.

The general rule this instantiates is in
[Design — a conversation](#design--a-conversation-and-one-question-at-the-end-of-it):
roles kept disjoint, sizes derived from what the measurement must resolve rather than
copied from convention, composition stated and not only size. Here that means: say the
proportions and where they came from, say how each part is drawn, and say what happens
to any part you would carve and not use — if nothing is chosen by looking, the middle
one is not needed and taking it costs material for nothing.

When there are two sides being compared, the split is the same for both and drawn
once. A comparison whose sides saw different material is not measuring the method.

Four things decide whether the numbers mean anything:

- **It is bounded, not shrunk.** The scale comes from what the verdict has to resolve,
  so what it answers, it answers — but it answers one question. A setting sized to
  separate a three-point gap says nothing about an advantage that only appears further
  up, and a number read without its bounds beside it will be taken for more than it
  is. Print them together, every time.
- **Speed buys repetition.** Several seeds on a small setting beat one slow run,
  because one run cannot separate a difference from its own noise. Report dispersion,
  never a bare mean.
- **The slice is stratified, not random.** The proposal requires every class to be
  present in the source collection the local correspondence uses; a random slice can
  drop one, leaving that correspondence undefined. The failure would look like a
  defect of the method and be a defect of the sampling. `benchmark.py` enforces this
  and raises rather than returning a quietly smaller slice.
- **The reduction is identical for both, and the baseline is never edited to fit it.**
  It is the user's prior work. If it cannot be driven into the common setting as it
  stands, pass `None` as its builder: the run records `not applicable` with the reason.

### One table, two settings, and a winner per row

Both settings answer the same question — where does each implementation hold — so
they share one shape and one set of rules, in `verdict.py`. The synthetic sweep is
fast and unit-free; the trained run swaps in a real model over real data. Same table,
different instrument.

Every row declares which direction wins it, and **a verdict is only granted when the
means differ by more than their combined standard error.** Anything closer is
`indistinguishable`. That threshold is the whole reason several seeds are run:
comparing two bare means always produces a winner, because every measurement differs
from every other at enough decimal places, and reporting that is reading noise out
loud. A dimension with no better direction — a parameter count — is reported and not
contested.

**And the threshold needs a floor under it, because below one it inverts.** With a
single repetition the dispersion is zero, so the combined standard error is zero, so
*every* row declares a winner from a bare difference — the rule turns into its own
opposite exactly where the protection was most needed. Declare a minimum number of
repetitions; below it, grant no verdicts, stamp the reason in the header and in the
record, and print the table anyway. Suppressing it would make the pilot a different
program from the campaign, which is the one thing the pilot may not be.

Four more things separate a table that informs from one that flatters:

- **When a claim can be satisfied by degenerating, measure the complement.** A
  distance that falls may be alignment or collapse, and the first number alone calls
  both a success. The measurement that tells them apart is reported beside it, always,
  and neither is reported alone.
- **Report the observed range and how it varies across settings, not only the mean.**
  A claim about scale — that a quantity stays bounded, that it behaves the same
  everywhere — is only a claim until its range is printed. The variation across
  settings is the sharper half: a common scale means the same quantity lands in the
  same range whichever configuration it is measuring.
- **Use paired differences when no single setting resolves anything.** Averaging raw
  values across settings folds each setting's difficulty into the dispersion and
  drowns the effect. The difference between two arms measured within the same setting
  cancels that difficulty, and agreement across settings is what carries a reading
  that no single setting could support.
- **Keep the median artefact, never the best.** Whatever is saved for later inspection
  represents the method only if it is typical. The best of thirty is an extreme of
  thirty draws, and what gets inspected afterwards describes the luckiest run.

Dimensions come from what the proposal claims to improve, not from a generic
checklist. Cost — wall time, peak memory — compares cleanly even when the two predict
on different statistical units. Accuracy needs a metric both sides can carry: the
existing probe in this lineage used a unit-free separation statistic precisely so it
could compare across units, which is worth reaching for before declaring anything
incomparable. Where no such metric exists, the row is `not applicable` with its
reason. **`not applicable` is a legitimate cell; filling it with a number is not.**

Close with the tally: where the new implementation wins, where the baseline does,
what was indistinguishable, and what could not be compared. The reader should not
have to count rows to learn the answer.

6. **Report the layout, never gate on it.** `structure` is part of the answer in
   step 2, so drift is always visible. But it does not stop the flow and it is not
   asked about again: that question belongs to the first pass, and it was answered
   there — including when the answer was "no".

## Output Contract

Report: the bound revision, the target path, the migration commit hash (if
any), the object → module map, the test result, and every verification status
`verify` returns, separately. There are twenty-four of them, and a list written
inline is a list that loses one — two of these were computed, returned and named
in no doctrine at all, so a reader met them first in the JSON:

| Status | What it reports | Gates? |
| --- | --- | --- |
| `structure` | Missing directories, stray modules, unparsable tests, stale references and scaffold gaps, plus `resolve` — one published exit per gap key that names anything, `[]` when nothing is owed | Yes — `drift` is a layout that no longer matches |
| `priorWork` | That prior work is untouched | Reported whatever it says |
| `agreements` | The state of `AGREED.md`, item by item, plus a nested `witness` dimension: `unwitnessed`/`unmeasured`/`disagrees` texts and a `summary` field ("N of M witnessed") printed on every run, including "0 of 0 witnessed"; `decided` (witness-less lines closed by `settle --done --unwitnessed`, with reason and session) and `handTicked` (witness-less lines ticked with no recorded act) appear only when non-empty and never count as witnessed | `open` items: yes — never report work done while one is `open`. `witness.disagrees`: **never here** — reported only; `close` is the sole place that refuses `AGREEMENT_DISAGREES` |
| `position` | The execution sequence's derived state, read from `<Name>/AGREED.md`'s own position section: which steps are measured done, which disagree with their disk mark, which this invocation could not measure at all | **Never** — a derived fact, reported so a human can decide about it |
| `prose` | Historical revision mentions and symbol-shaped configuration keys | Reported whatever it says; these are facts, not verdicts |
| `search` | Whether a declared search says enough about itself for its chosen value to mean anything | Yes |
| `distribution` | What a run split across shards declares, and whether the shards that arrived agree | Yes |
| `remoteExecution` | The state of the remote-execution ledger and its job folders, plus `resolve` — the published exit for `drift` and `unreliable`, `null` for every state that names no work | Yes |
| `coupling` | Which notebook cells reach into the target's internals instead of its declared surface | **Never** — a static fact, reported so somebody can decide about it |
| `fidelity` | The revision each module is bound to, provenance, untested invariants, and how the revision was resolved | Yes |
| `lfs` | Which large files are real content and which are unfetched pointers | Reported whatever it says |
| `report` | Whether the document a human reads obeys the rules the numbers already do | Yes |
| `audit` | Findings, their evidence, their remedies, admissibility and compatibility | Yes |
| `validation` | Smoke test, invariant tests, trivial assertions and every notebook of the product | Yes |
| `toDiscuss` | One directly runnable, `shlex.quote`-escaped `discuss` command per `audit.localRemediesNotWritten` finding id, asking whether its local remedy is written now or deliberately deferred (and why) | **Never** — a published action naming an already-computed undecided thing, not a verdict; publishing it lowers the friction to ask, and does not prove whoever answers is the operator (see "Neither half proves who answered," below) |
| `undeclaredOptional` | Every optional key a DECLARED `search`/`distribution` block left unanswered (`SEARCH_OPTIONAL`/`DISTRIBUTION_OPTIONAL` — `search.record`, `search.currentWhen`, `distribution.currentWhen`, `distribution.shardsRoot`), each entry naming its `section`, `field` and the exact `consequence` its absence carries — MINUS every field `undeclaredBlocking` reports, which is not optional in any sense this word carries and is named there with the steps it stops. Reported, never demanded — a target with no search, or no split run, is asked nothing here either | **Never** — an optional field left unanswered is a legitimate resting state, not a defect; this only makes the option visible and names what it costs |
| `undeclaredBlocking` | The other half of `undeclaredOptional`, and the half that key cannot honestly hold: every undeclared optional field a witness in the target's OWN declared sequence cannot be measured without, so its absence stops a declared step rather than narrowing a reading. Each entry names its `section`, `field`, the `evidence` key the field produces, `blockedBy` (each sequence item whose `measuredBy` head is that key, with its witness), `blockedSteps` (every `__steps__` entry whose `advances` ordinal sits above the earliest of them, and which `step` therefore refuses `STEP_SEQUENCE_NOT_REACHED` on every call), the `consequence` — which composes in the field's own — and an `exit`. The set is DERIVED from the sequence, never listed: a roster of load-bearing fields would go stale the first time a witness kind changed what it reads. Matching on the `measuredBy` head and never the whole string is what keeps a corroborator out — `search.currentWhen` and `distribution.currentWhen` narrow a reading and stay in `undeclaredOptional` — and what sorts the record kinds for free, since a named `@record:level <name>` is measured through its own `__records__` entry. `[]` when the target declares no ordered flow, when no unanswered field's key is named by any item, and when every such item sits at or above the furthest ordinal any step advances | **Never** — the refusal it reports ahead of is unchanged; it only says before the first step runs what `step` would otherwise say four ordinals in. Its `exit` is a **question**, never a command: the one act that clears it is an edit to the target's own benchmark declaration, and the forge authors no target declaration — so what is published is the question and the directly runnable `discuss` command that opens it |
| `undeclaredLadder` | The ordered rung ladder `__levels__` names, when it names none: the declaration, the file that would carry it, and the exact `consequence` its absence carries — `POSITION_RUNG_SKIPPED` can never fire, `position.attainedLevel` stays `null` forever, every item stays two-state because a `:level` witness is refused, and a header's `--target-level` is compared against nothing. `null` when a ladder is declared, and when the target has no benchmark package to declare one in | **Never** — a repository whose steps are all two-state needs no ladder and is not defective for having none; this only makes the option visible and names what it costs |
| `unreachableLadder` | A declared ladder the sequence beside it can never climb to the launch floor of: `levels`, `requiredLevel`, `highestAttainable`, `cappedBy`, and the consequence. Fires from four rungs up with a leveled `@rehearsal` item, which `smokeReady` bounds at the floor plus one | Never — reported so a `RUNG_NOT_ATTAINED` nothing can answer is legible before it is met |
| `undeclaredRecords` | The named records `__records__` names, when it names none: the declaration, the file that would carry it, and the exact `consequence` its absence carries — a leveled `@record:level <name>` witness can only ever derive `None` (unmeasured), and `position` refuses `POSITION_RECORD_UNKNOWN` outright before that state is ever written to a mark. `null` when at least one record is declared, and when the target has no benchmark package to declare one in | **Never** — a repository whose only leveled `@record` witness is the bare, operand-less one needs no named record and is not defective for having none; this only makes the option visible and names what it costs |
| `unfinishableFlow` | An ordered flow the target's own declared scale makes unwalkable: `requiredScale` (the scale that decides), `blockedBy` (each sequence item a run below that scale can never tick — a two-state `@record` witness, which `impl_position._derive_record` grades against `search.scaleSatisfied`), `blockedSteps` (every `__steps__` entry whose `advances` ordinal sits above the earliest of them, and which `step` therefore refuses `STEP_SEQUENCE_NOT_REACHED` on every call) and the consequence, which names the exit: a leveled `@record:level <name>` witness backed by one `__records__` entry per record the flow produces, each with its own `requiredScale`. `null` when no scale is declared, when no item is graded against one, and when no step waits behind such an item | Never — the refusal it reports ahead of is unchanged; this only says before the first step runs what `step` would otherwise say several steps in |
| `undeclaredProduces` | One entry per declared `__steps__` step that names no `produces`: the `step`, the exact `declaration` key that would carry it, the file that would carry it, and the `consequence` its absence carries — `step` snapshots the product folder before and after every run, so with no declared root it can tell neither a run that returned having written nothing from one that produced its whole output, nor a run that stayed in its own tree from one that wrote into a neighbour's. `[]` when every declared step names its roots, when the target declares no steps at all, and when it has no benchmark package to declare them in | **Never** — an absent declaration switches a reading off; it does not make the step defective, and a refusal here would grade an act whose subprocess has already run. The kit ships the key in its own `__steps__` example so a repository built from zero meets the question rather than defaulting past it |
| `undeclaredPlacement` | One entry per declared `__steps__` step that names no `placement`: the `step`, the exact `declaration` key that would carry it, and the `consequence` its absence carries — the walk cannot route that step once the flow leaves rehearsal scale. It knows the step exists, what it produces and where it sits in the order, and not whether it runs here or on a worker, so `probe`'s `flowActs` reports it `blocked` rather than choosing. A **declaration** and never a ledger read: routing gets decided in conversation, a conversation lands in `.implementation/` as free prose, and `.gitignore` excludes that directory — so a decision left there can be neither consumed nor travelled with, while the walk that acts on it runs from a clone. The ledger keeps the reason; this key carries the fact. `[]` when every declared step names one, when the target declares no steps at all, and when it has no benchmark package to declare them in | **Never** — a repository that never leaves rehearsal scale needs no placement on anything and is not defective for saying nothing. What it must not do is DEFAULT: routing an unrouted step by convention is how a run measured in days lands somewhere nobody chose. The from-zero demand is the kit's own `__steps__` example, which ships `placement` on both steps, and the `job` and `service` a remote one names |
| `undeclaredStepNotebooks` | One entry per declared `__steps__` step that names no notebook among its `produces` roots: the `step`, the exact `declaration` key that would carry it, the file that would carry it, and the `consequence` its absence carries — a pilot is the declared flow walked with the declared notebooks, `_pilot_notebooks` reads a step's notebooks off those roots and nothing else, so a step naming none is walked by calling the target's library while the notebook that would carry the same work elsewhere is never executed by the run meant to validate it. **One declaration and never the position sequence:** `_pilot_notebooks` also reaches a notebook through the item at a step's `advances` ordinal, and a step reached only that way is named here anyway — a sequence witness is a mark in `AGREED.md`, which the repository this exists for has not written yet, so consulting it would go quiet on exactly that repository. Every step that owns no notebook, INCLUDING one that declares no `produces` at all, and deliberately not subtracted from `undeclaredProduces`: `[]` here has to mean *every declared step owns a notebook*, and subtracting would let a repository whose steps all declare nothing read empty. `[]` when every declared step names one, when the target declares no steps at all, and when it has no benchmark package to declare them in | **Never** — a repository may legitimately compute in its own library and render elsewhere, and a refusal would corner an operator whose layout is exactly what they meant. It is a new key and not a widening of `pilotCompleteness.withoutNotebook` because the two answer different questions: that one is computed from a pilot's own evidence and says *this repository opened no notebook here*, this one is read off the declaration alone and says *nobody ever asked it to have one*, which is the question a repository built from zero has to meet before any run exists. The kit ships both kinds of step in its own `__steps__` example — one that computes and one that draws, each naming its own notebook |

Column one is read by the suite against `verify`'s own return, so a status added
to the command fails the tests until it has a row here. Columns two and three are
prose and are not asserted: that a row says a status never gates is a claim a
human makes, and `coupling`'s is carried by the tests that already exercise it.

One more key is not in the table because it is not always there:
`launchLadder` appears only when the position ladder still owes a launch
something — a job (a job folder, or a `placement: "remote"` step's `job`)
whose ladder names no `@rehearsal <job>` item (`rehearsalWitnessMissing`,
with the ordinal it belongs before), or ticked items nothing measured
(`unbackedOrdinals`) — so a target that never reaches a remote step reads
byte-identically. It never gates; `references/usage.md`'s *Reading `verify`*
says how to clear it, and `launch-plan` reports the same key per job.

`priorWork`, `agreements` and `prose` are reported whatever they
say: that prior work is untouched, and that nothing was left open, are facts the
reader is owed, and a check that only speaks up when something is wrong teaches
nobody what it was watching. Never report the work done while `agreements` is
`open` — name the items and say why they are still open. For each finding give
its kind, the equations it touches, its status with the measured rate, and the
remedy with the equations the remedy would change. State scope left out. Never
claim verification passed without the `verify` output and a green suite, and
never report a finding whose remedy validation did not run.

**Neither half proves who answered.** `close`'s `DISCUSSION_UNANSWERED` gate,
and the `discuss` commands `toDiscuss` above and `settle`'s
`SETTLE_COLLIDES_UNNAMED` refusal now publish, prove only that a decision
reached the record — never that the operator authored it. An agent can open
a question and answer it itself, and nothing downstream can tell. That
happened in this very session. Publishing a runnable command lowers the
friction to ask; it does not raise the bar on who is allowed to answer.

### What `probe` reports, and why none of the job facts is a gate

`probe` answers `nextStep` and reports sixteen facts around it. The ladder
that chooses `nextStep` reads most of them; the rest are read by a human
before deciding what to do with the answer, and a fact nobody was told about
is a fact nobody reads:

| Fact | What it reports | Gates? |
| --- | --- | --- |
| `objective` | Why this skill was invoked and where it has to arrive: the declared `purpose`, the ordered `stages` with what each establishes and how a reader knows it is behind them, the `arrival`, and the `humanStops` that are a person's decision rather than a defect to repair. Reported **above** every measurement beside it, and carried by every refusal this engine raises. Invariant and independent of anything on disk — every other fact here answers *where am I* by reading products; this answers *what is this for*, which no product implies. See the section **The objective flow** and `OBJECTIVE_FLOW` | **Never**, and it is never derived either: a stage computed from products would make the purpose depend on the products, which is the one dependency it exists without. It has to read the same on a repository with nothing in it as on one mid-campaign |
| `backend` | Whether the implementation can be trained at all, and what it computes with: `__backend__` in `src/<Package>/__init__.py` when stated (`source: "declared"`), import inference otherwise (`source: "imports"`) | Yes — `convert` is the answer when it cannot |
| `baselines` | The prior implementations there are to compare against | Yes — nothing to compare against outranks everything else on the ladder |
| `comparable` | Whether that list is non-empty, stated once so nobody re-derives it | Reported whatever it says |
| `coupling` | Which notebook cells reach into the target's internals instead of its declared surface | **Never** — a static fact, reported so somebody can decide about it |
| `decisions` | Two standing decisions, always both present: `comparison` (the offer to compare) and `validation` (the acid-test offer to run one arm), each `{state, at, asked, decision}` — `state` is `"answered"` once that offer's own question has been answered, `null` while it stands open; `at` and `asked` are read verbatim off that ledger event and are display-only, never a tiebreak. `decision` (D19) is `"yes"`/`"no"` once answered, read through the closed `discuss --decision` token — an answered bucket with no token reads `"no"` (D20's migration rule) — and `null` while unanswered. The engine still parses no free text: `decision` is the one closed token it reads, never the prose in `answered` | **Yes** — read to publish `validate`, `declined` and `build-first` (below); the ladder's own guard is each offer's exact question text plus this `decision` token |
| `harnessStatus` | Where the target's own declaration says its harness module is: `undeclared`, present at `path`, or `declaredMissing` naming `declaredModule` and `searchedPath`. `declaredFunction` echoes `entry.function` beside it, and `note` names what a blank one costs: nothing in this skill reads that field, but a job generated in the callable shape needs `generate-job --run-function`, and this declaration is where its value comes from | Reported whatever it says |
| `nextStep` | The one thing to do next | This is the answer, not a fact feeding it |
| `notebook` | Where the pilot notebook is, or `null` | Reported whatever it says |
| `position` | The execution sequence's derived state, read from `<Name>/AGREED.md`'s own position section. `probe` takes no `--shards`, so every `@shard` witness reports `unmeasured` here, never a false "did not arrive" | **Never** — a derived fact, reported so a human can decide about it |
| `pilotCompleteness` | Whether the flow the target declared has actually finished at pilot, step by step: `status` (`undeclared` when no `__steps__` entry carries an `advances` ordinal at all), one row per **declared** step — ordinal-carrying ones first and in that order, the rest after in name order — naming its `advances` (`null` where it declares none), whether it `ran` and returned, the `notebooks` it owes and whether all of them are executed against these sources (`notebooksCurrent`), how many the pilot opens for it (`notebookCount`, on every row and zero included), and `producesDeclared`; plus `incomplete` — the steps still short — `unmeasurable` beside it, the steps whose output nobody could look at because they declare no `produces` roots, and `withoutNotebook`, the steps the pilot walked without opening a notebook at all, each list with its own note | Yes — an unfinished flow is `pilot-first`, and a finished one whose steps have not each been decided is `pilot-decisions` |
| `walk` | Where this repository stands in its own declared flow, step by step: `status` (`undeclared`/`notStarted`/`walking`/`walked`), the declared `levels` and `topRung`, one row per declared step (`walk` — `notWalked`, `unfinished` (a `started` ledger event with no terminal partner, a run that was killed) or `walked` — plus `lastOutcome`, `lastAt`, the `rung` its position item grades at, `atTopRung`, and the output roots it `renders`), and one row per result-rendering artefact in the product tree, each inheriting the state of the step that renders it (`renderedBy`, `walk`, `rung`, `witnessed`). An artefact no declared step renders reads `outsideTheWalk` — a description of that artefact, not an accusation about it. Every input is already held: the ledger's step events, the position sequence and its rungs, and each step's own `produces` roots; **no target declaration is introduced** | **Never** — a walk report answers *where am I*, not *what is broken*. Nothing in it is a finding: a step nobody has walked is a state, a flow that has not started is where every repository begins, and reporting either as a defect would greet an operator with noise on their first clean run |
| `flowDestination` | Where this flow is GOING and every act still standing between the repository and there: the `rung` at the top of the ladder the target itself declared, the `remaining` acts to reach it in flow order, and a `note`. Reported **always**, whatever the position header aims at, because `flowActs` answers what is owed toward the rung AIMED at and a repository resting at the floor with every step reaching the floor owes nothing there — so a session reading only that concludes the work is done when the destination has not been reached. Which rung the top IS stays the target's word: a ladder whose top is a local rung has a local destination and this says so, because a forge that assumed the top meant a worker would be deciding somebody's flow for them. `rung: null` with the cost named when no ladder is declared | **Never**, and it is never acted on either — acting happens against `flowActs`, one rung at a time, because the ladder refuses a skipped rung and this would otherwise read as permission to jump. What it guarantees is narrower and is the whole point: the flow cannot look finished while it is not |
| `flowActs` | The half `walk` could not answer: what the next act is for every declared step still owed, in the flow's own order, one entry each — `run-local`, `generate-job`, `rehearse`, `launch`, or `blocked` with what is missing named. Routed by each step's own `placement` (`local`/`remote`) and, for a remote one, the `job` and `service` it declares. A step is dropped only once its own rung reaches the one the position header aims at (`position --target-level`), never once it has been walked: the ledger's step events carry no scale, so on a real repository all ten declared steps read `walked` at the floor rung and skipping on that answered *nothing is owed* for a full run that had not started. **`blocked` is a first-class answer, never a blank**: a step nobody routed is not a step with nothing to do, and routing by default is how a run measured in days lands somewhere nobody chose | **Never** — it reports what WOULD be done and issues none of it. Running any act is the caller's, and every guard each one carries stays exactly where it is; a fact that both decided and dispatched would be a launch path with no `gate` in front of it |
| `remoteExecution` | The ledger's fold, plus the job folders that exist on disk right now, plus its own `resolve` — the published exit for `drift` and `unreliable`, `null` otherwise. Distinct from the top-level `resolve`, which answers `nextStep` | Yes — a submission already out is `poll-first` |
| `report` | Whether the document a human reads agrees with the run | Yes — a document in drift is `report-first` |
| `resolve` | What to do about `nextStep`, published by the engine rather than composed by whoever reads it: `{kind: "command", command}` for a step this flow can name completely, `{kind: "question", question, command}` for a step whose next act is a decision, and `null` only for the two steps the roster declares terminal | **Never** — a published action, not a verdict; publishing it proves the decision reached the record, never that the operator took it |
| `results` | What the last pilot measured, and at what scale | Yes — below scale is `piloted`, at scale is `already-benchmarked` |
| `search` | Whether a declared search chose anything, and what a full run would cost | Yes — a record absent from disk, or its `scaleSatisfied` short of `true`, is `search-first` |
| `toDiscuss` | The question-shaped half of `resolve`, as a list: one directly runnable, `shlex.quote`-escaped `discuss` command for every `nextStep` whose next act is a decision, naming the target/name pair and — for `piloted` and `search-first` — the DECLARED (never the achieved) scale. Empty for the two terminal steps and for `env-first`, whose exit is a command nobody has to decide about | **Never** — a published action naming an already-computed undecided thing, not a verdict (see "Neither half proves who answered," above) |
| `unreachedModules` | Arms declaring mathematics they never call | Yes — that is `wiring-first` |
| `validation` | The acid-test draft, present at the one answer `PROBE_NEXT_STEPS` marks as carrying it: `validate`, the offer to run the method alone against its own declared prediction. `null` at every other answer, the identical shape `wiring` keeps. See [`nextStep: "validate"`](#nextstep-validate) | Reported whatever it says |
| `wiring` | The proposed wiring, present at the two answers `PROBE_NEXT_STEPS` marks as carrying it: `benchmark`, the offer to run, and `wiring-first`, where an arm declares mathematics it never calls. It used to be guarded on `benchmark` alone, so the one answer that named missing wiring withheld the draft of how to wire it | Reported whatever it says |

Column one is read by the suite against `probe`'s own return, exactly as the
table above is read against `verify`'s: a fact added to the command fails the
tests until it has a row here. Columns two and three are prose and are not
asserted.

**`remoteExecution` folds two sources under one key**, and a reader has to know
which one they are looking at. The ledger's own fields say what went out to a
worker and what came back. These three say what exists on disk right now:

| Job fact | What it reports | Gates? |
| --- | --- | --- |
| `jobs` | Every generated job folder found under `tools/`, each with its product, its own `staleness` verdict, and the `notebook` its run block declares (`null` for the callable shape, and for a config that could not be read at all) | **Never** — reported beside the answer, read before a campaign |
| `services` | How many services those folders are spread across, as a count | **Never** — a count, so that no service is ever named here |
| `smokeReady` | Per job, whether a rehearsal has already passed on the commit that job is pinned to | **Never** — for the reason below |

**Why neither of the two is a gate, and what would change that.** `smokeReady`
and a job's `staleness` are exactly the two facts somebody wants before paying
for a long run, and neither one can become a rung. The function computing them
answers `{"jobs": [], "services": 0, "smokeReady": {}}` for a repository with no
remote-execution CLI on disk at all — byte-identical to what it answers for a
repository that has one and has generated no job yet. "Nothing is ready" and
"none of this applies" are the same three keys, and a rung needs to tell them
apart. Branching anyway would withhold the benchmark offer from every repository
that never sends work anywhere, which is most of them.

So both are reported, and the Decision Gates table is what sends a reader to
them. If the fact ever grew a per-job link to the campaign about to be offered —
tying an unrehearsed job to *this* run rather than to the repository in general —
the difference becomes expressible and this position should be revisited.

### Is the notebook this job would run one the pilot walked?

`remoteExecution.notebookPilot` answers exactly that, and until it existed
nothing did. Both halves were already on the page: a job's run block can name a
notebook, and the worker runs that exact file out of the sparse clone at the
pinned commit; `pilotCompleteness` already knows which notebooks the declared
flow opened. Nobody compared them, so a repository could show a complete pilot
beside a job pointing at a notebook that pilot never touched, and every key read
clean.

Three answers, one shape:

| `status` | What it means |
| --- | --- |
| `piloted` | The pilot walked this exact notebook. The file about to cost machine time has been executed and read here first |
| `unpiloted` | It did not — or the job's path is not one the pilot's vocabulary can express at all, which is the same answer for the same reason: nothing here has run that file |
| `not-applicable` | This job declares the callable shape and names no notebook, so there is nothing to compare. A first-class answer, never a blank |

Every row carries `job`, `notebook`, `pilotRelative` and `status` in all three
states. A payload whose shape changes with its answer makes each reader test for
a key before reading it, and the one that forgets reads `null` and calls it
"not applicable".

**It reports and it refuses nothing.** This sits in front of the expensive
door, and a refusal there an operator cannot clear corners them at the one point
where every alternative costs money. A repository may generate a job before it
pilots, or pilot through one notebook and send another deliberately. What must
never happen is that nobody is told — so the Decision Gates row above sends a
reader to `unpiloted` before a campaign is offered, and the answer is computed on
every run rather than only on the run where it turns out to matter.

**The two vocabularies are joined, never assumed equal.** A job's
`run.notebook` is repository-relative, because the remote-execution skill
resolves it against the clone; the pilot's notebooks are product-relative. The
job's path is restated in the pilot's vocabulary segment-wise, and `pilotRelative`
reports the result so a reader can see what was actually compared. `null` there
is not a match: a path the pilot's vocabulary cannot express is not a notebook
the pilot walked.

**Nothing in `remote-execution` is read differently or changed for this.** The
notebook comes out of the same open `run-config.json` this command already reads
each job's staleness from — `run.notebook` alone, never that skill's own
`declared_notebooks()`, whose union with `run.smoke` answers a different
question and would report a rehearsal's artefact as the thing a campaign sends.

### The rehearsal is the agent's to run

The `submit` row above says this flow offers a campaign to a human and never
sends one itself. That sentence is about the campaign, and it is right about
it: a full run costs hours and real quota, and what it costs is the reason a
person authorizes it rather than reads about it afterwards.

A rehearsal is not that. It is the smallest slice that still exercises the whole wire — minutes — and
it exists precisely to find cheaply what the long run would find expensively.
Nothing here ever forbade running one. Nothing told the agent to either, so on
reaching a job that had never rehearsed the only thing left to do was ask, and
asking made the cheap check cost the same conversation as the expensive one.

**So the rehearsal is run, not offered.** When the Decision Gates row for a job
with `smokeReady: false` sends you here, on the worker the campaign would use:

| Step | Command | What it establishes |
| --- | --- | --- |
| Check it locally first | `remote_cli preflight` | everything a first remote rehearsal used to fail on is fixed: diagrams validated, the driver's interpreter, code reachability, declared inputs, the smoke run locally under runner conditions leaving a complete `shard.json`, each account, the accelerator, the session fit; every `fail` row is fixed before the rehearsal is run or offered |
| Rehearse | `remote_cli submit --smoke` | the wire carries current on this worker, at this pinned commit |
| Bring it back | `remote_cli fetch` | the shard the rehearsal wrote is on disk to be read |
| Write the verdict down | `remote_cli smoke record` | the verdict is evidence-derived, never a human's assertion |
| Read it | `remote_cli readiness` | whether that worker is ready, and when it is not, why |

Report what comes back either way. A rehearsal that fails is the cheapest
result this flow can produce, and it is worth more than a campaign that failed
for the same reason six hours later.

**Per worker, and it does not carry over.** A rehearsal binds to the worker and
the commit it ran on. A pass on one account says nothing about another, so a
campaign spread across several needs one on each. `gate --unit` holds you to it:
it refuses `NOT_READY`, naming each worker the campaign's `propose` record
lists without a passing rehearsal of its own at the job's pin.

**None of this makes `smokeReady` a gate.** It still cannot be one, for the
reason given above — the fact answers identically for a repository with no
remote-execution CLI at all — and permitting the rehearsal is not the same as
branching on the fact. What routes a reader here is the Decision Gates row,
which is prose a reader follows, not a rung the ladder computes.

### The smoke proves the pipe, the pilot proves the science

**The smoke proves the pipe. The pilot proves the science.** A rehearsal's
readiness measurement — the service accepted the submission, the kernel ran,
the shard came down carrying the agreed fields — is a different fact from a
pilot's production: the whole flow ran, and what it produced satisfies what
was agreed. Passing one MUST NOT be read as passing the other. This is why
`@step:level <name>` refuses `POSITION_WITNESS_NOT_LEVELABLE` rather than
reporting a rung: `_derive_step` reads `run_step`'s `raised`/`returned`
outcome, which is identical whether the callable ran at pilot scale or full
scale — it measures completion, never production. A step earns no rung this
way, on purpose: a witness that cannot see what its own prose claims to
describe would be worse than one that refuses to claim it at all.

## Command Roster

Two tables, and together they are the whole of `implementation_cli.py`'s
dispatch surface. The first is the write-verb half: every command that writes
into `<Name>/AGREED.md`, into `.implementation/`'s ledger, or into both, rather
than only reporting. The second is everything else the CLI accepts.

Column one of both is read against `COMMANDS`' own keys, in both directions: a
new command fails the tests until it has a row, and a row no command backs
fails them too.

**`settle`'s class is closed at five modes**, stated once here rather than
re-derived by measurement: place (the default), attach a witness
(`--attach`), remove (`--remove`), reverse (`--reverse`), and mark done
(`--done`). Two of those five are compositions of the other three, not
gaps of their own: editing an agreement's text is `--reverse` (write the
explanation and delete the line in one call) followed by a fresh
placement; moving one between sections is `--remove` (once the removal is
already explained) followed by placement under the new heading — and
re-pointing a witness is neither: it is `--attach`'s own write with one
refusal lifted, so it is spelled `--attach --replace` rather than as a
sixth mode. The composition that would reach the same end state — reverse,
place, attach, done — is not equivalent, because it destroys a tick the
agreement never lost and writes a `## Reversed` entry for something that
was never reversed. Nothing else in this file writes into `AGREED.md`'s
checklist body.

**`--session <id>`**, required by `position`, `propose`, `gate`, `offer`,
`close`, `step`, `settle`, `defect` and `walk`, is an id the caller chooses —
one per working session, reused across its writes, one shell-safe token. The
engine never mints it, and refuses it only where `position` would write it into
the block's header (`POSITION_SESSION_INVALID`: empty, non-ASCII or with
whitespace); it stamps it on every event the call appends, as attribution. `references/usage.md`,
"Session ids", has the details.

**Running these commands.** Through this skill's `scripts/implementation_cli.py`,
which sets `IMPLEMENTATION_DOMAIN_PROFILE`; a profile you set yourself must be an
absolute path (`IMPLEMENTATION_DOMAIN_PROFILE_NOT_ABSOLUTE` otherwise). The
workspace bridge `smith implement --action` reaches only `env`, `name`,
`plan`, `apply`, `admit`, `handoff`, `compose`, `probe` and `verify`, and its
`--action materialize` is a kept alias of `apply`, not of `materialize` below.

| Command | What it writes | Refuses on |
| --- | --- | --- |
| `position` | No flag: re-derives the marks of the block already in `<Name>/AGREED.md`, touching nothing else about it. `--sequence -`: installs a fresh section from stdin JSON (each entry's `witness.twostate` defaults to `true` when omitted). `--reconcile`: reconstructs the sequence from what the target already has (declared record, discovered job folders, `Notebooks/*.ipynb`, and one `@shard` per arrived shard with `--shards`), matching existing items by witness identity and adding only unmatched ones — a missing `@rehearsal <job>` is inserted immediately before the item that runs that job remotely (an `@step` named after the job, or a step declared `placement: "remote"` with that `job`), every other one appended — every discovered witness is two-state. `--shards <dir>` also measures every `@shard` witness against that directory in every write mode, not `--reconcile` alone — without it `@shard` reads `unmeasured`, never `False`. `--repair-header` (`the-holder-each-skill-declares`, design D6/D7): repairs an existing declared holder's header when it disagrees with the current profile's declared document count, dropping only a `documents=` group naming labels this profile does not read and leaving `revision`/`revisionSha256`/`derivedAt`/`session`/`target` and the block body byte-identical — or, when the evidence instead supports giving this target its own declared holder, creates that one and leaves the poisoned file untouched; ambiguous evidence writes nothing and stops with a named question. Mutually exclusive with `--sequence`/`--reconcile`/`--replace`. `--target-level <level>` names the rung this pass is aiming at (one of the target's own `__levels__`, read from the benchmark package's `__init__.py`/`config.py`); required only for a fresh header, sticky (reused) across a bare refresh. **A rung is never skipped going forward:** to seal at rung N, every leveled item must already grade as satisfied at rung N-1 — derived from the evidence as it currently stands, never from the ledger, since a target that never ran this command has no ledger and a history check would pass vacuously on exactly the repositories the rule exists to stop. The rung compared against is the one the EVIDENCE attains, never the one the header records: `target=` states what a pass aims at, legitimately one rung above what is reached, so an aim reaches at most one rung above attainment and where a pass came from is not consulted — a retreat and a re-seal assert that N-1 is reached exactly as a climb does. The first rung needs no predecessor, which is what keeps an operator whose evidence collapsed from ever being cornered; two-state items never participate; and a target that declares no `__levels__` is unaffected — nothing here ever asks one for a ladder, so `verify`'s `undeclaredLadder` reports the absence and what it costs instead. `position`'s state publishes `attainedLevel` beside `targetLevel`, so the gap between the two is readable without tripping a refusal; with no leveled witness in the sequence `attainedLevel` is the aim itself, never a rung above it. A mark means "reached the level this pass asks for" for a leveled (`:level`-marked) witness, or a plain pass/fail for a two-state (unmarked, the default) one — see `impl_position.derive`'s own docstring. Every real write appends one event to `.implementation/position.jsonl` | `REVISION_UNREADABLE`, `DOCUMENT_REVISION_UNREADABLE` (a declared document beyond document 0 has no readable revision -- no family found, ambiguous families, or a discovered name that does not read; the detail names the index, label, directory and cause), `POSITION_BLOCK_EXISTS` (install over an existing block without `--replace`), `POSITION_SEQUENCE_AND_RECONCILE`, `POSITION_REPAIR_CONFLICT` (`--repair-header` combined with `--sequence`, `--reconcile` or `--replace`), `POSITION_HOLDER_ABSENT` (narrowed, `the-holder-each-skill-declares` D9: no product folder exists to create the declared holder in — the create path still needs a folder), `HOLDER_UNDECLARED` (an existing checklist holds items under a name neither this skill nor any sibling skill sharing the engine declares; names both exits — rename it to the declared name in the target repository, or declare that name as this skill's own `PROFILE["holder"]["filename"]`. A sibling skill's own declared holder, e.g. `Experimental_AGREED.md`, is never a candidate: it is derived from each sibling `impl_profile.py`, set aside, and the declared holder is created beside it), `HOLDER_REPAIR_AMBIGUOUS` (`--repair-header` only: the evidence does not determine repair vs. giving the target its own declared holder — a declared label already carries a recorded revision, the block is legacy, or more than one file carries a block; nothing is written until a human decides), `POSITION_HOLDER_AMBIGUOUS`, `POSITION_BLOCK_NOT_UNIQUE`, `POSITION_BLOCK_MALFORMED` (also raised for a block written by the pre-level-grammar revision, which carries no `target=` field and is never silently migrated), `POSITION_ITEM_MALFORMED`, `POSITION_ITEM_WITHOUT_WITNESS`, `POSITION_WITNESS_UNKNOWN_KIND`, `POSITION_SEQUENCE_UNREADABLE`, `POSITION_SEQUENCE_EMPTY`, `POSITION_SESSION_INVALID` (`--session` is empty, non-ASCII or holds whitespace, which the header cannot carry; refused before anything is written), `POSITION_TARGET_LEVEL_REQUIRED` (a fresh header with no `--target-level` and no existing block to inherit one from), `POSITION_TARGET_LEVEL_UNKNOWN` (`--target-level` names something `__levels__` never declared), `POSITION_LEVELS_UNDECLARED` (a `:level`-marked witness exists but `__levels__` declares no ladder), `POSITION_RUNG_SKIPPED` (a seal at a rung whose predecessor on the declared ladder is not currently attained by the evidence — see below), `STEPS_UNDECLARED` (an `@step` witness exists in the sequence and the target declares no `__steps__` at all — the identical code and wording `step` itself raises for the same fact), `POSITION_STEP_UNKNOWN` (an `@step` witness names an operand absent from `__steps__`; the detail lists what the target actually declares — `parse_items` validates only the witness kind, never this string), `POSITION_RECORD_UNKNOWN` (a leveled `@record:level <name>` witness names an operand absent from `__records__`, whether it declares others or none at all), `POSITION_RECORD_MALFORMED` (that operand IS declared and its entry cannot be read: not a mapping, so the reader drops it while this refusal calls it declared, or a mapping with no `path` string, so nothing can ever be looked for — `__steps__`'s own `STEP_MALFORMED`, one literal over), `POSITION_HOLDER_MOVED` (the holder file's bytes changed between the read that located its section and the write; offsets computed against the earlier read are refused rather than spliced into bytes they were never actually located against — re-run, never retry blind), `PRODUCT_DIR_MISNAMED` (this call's `<name>/` holds none of the product categories while exactly one differently-named folder holds them, so the ledger would open a second product tree nothing else reads — refused before the first append, publishing the `plan` that names the folder) |
| `discuss` | One `discuss` event per call to `.implementation/position.jsonl` — the question, the computed collision list, and (once given) the answer. Never touches `<Name>/AGREED.md`. Never gates: an unanswered question is a reported `status`, not a refusal. The response also carries `collisionSearch`: `"performed"` when the witness names an operand the search actually ran against, `"unperformed"` for the one operand-less kind (`record`) — an empty `collides` alone would read exactly like a search that ran and found nothing | `DISCUSS_STDIN_CONFLICT` (`--question -` and `--answer -` together), `DISCUSS_EMPTY_QUESTION`, `DISCUSS_ABOUT_NOT_FOUND` (an `--about` ordinal outside the sequence), `POSITION_WITNESS_UNKNOWN_KIND` (an `--about` witness spec naming an unknown kind), `DISCUSS_ABOUT_OPERAND_REQUIRED` (a bare `--about notebook`/`rehearsal`/`shard`/`step` with no operand — the collision search this call would otherwise run cannot know what to search for, so it refuses rather than silently returning an empty result), `PRODUCT_DIR_MISNAMED` (this call's `<name>/` holds none of the product categories while exactly one differently-named folder holds them, so the ledger would open a second product tree nothing else reads — refused before the first append, publishing the `plan` that names the folder) |
| `propose` | One `proposal` event to `.implementation/position.jsonl`, scoped to a whole CAMPAIGN, never a single job: `jobs` (repeatable `--job`, at least one — the subset THIS proposal covers), `workers` (repeatable `--worker`, at least one — the accounts the campaign spreads over; `gate --unit` refuses `NOT_READY` until every one of them has its own passing rehearsal at the job's pin), `dependsOn` (repeatable `--depends-on job:dependency`), `rationale` (required, non-blank) and `campaign: {commit, jobSet}` — never argv, a live-disk snapshot of every job folder currently discovered. Multi-use by design: calling `propose` again appends a fresh event rather than editing the last one; a bound proposal is never consumed, so a single job's transient failure never forces re-proposing the whole campaign | `EMPTY_RATIONALE`, `PRODUCT_DIR_MISNAMED` (this call's `<name>/` holds none of the product categories while exactly one differently-named folder holds them, so the ledger would open a second product tree nothing else reads — refused before the first append, publishing the `plan` that names the folder) |
| `gate` | One `gate` event to `.implementation/position.jsonl`: job, worker, commit, revision, entrypoint, units, the justification and `elected` (the `--elect` list, additive), plus one `authorization-consumed` event naming the presented token. Prints no token of its own — nothing here can be minted from the caller's own argv; `--authorization <token>` (required) must instead name a token an earlier `offer` publish already minted. `--worker <account>` authorizes a single-send or rehearsal launch for exactly that account; repeatable `--unit` authorizes a CAMPAIGN launch instead, binding the exact ordered unit list a later `submit --unit ...` will carry — the same derivation `campaign_consent_token()` uses for consent — and records `worker: null`, since a campaign names no single account. The two flags are mutually exclusive. `--service <service>` selects the job folder when folders of the same job name sit under different services: a job is identified by `(service, job)`, and that folder's own readiness is the one read. A campaign is authorized only when every worker its `propose` record names has rehearsed on the job's current pin — readiness is per worker, never the latest rehearsal's worker alone. Once the authorization token itself verifies, `gate` also requires a bound campaign proposal naming this job (published by `propose`) and, when this job classifies `optional` (`classify_remote_necessity`'s own verdict — the recorded facts do not decide), a matching `--elect <job>` on this exact invocation | `EMPTY_JUSTIFICATION`, `REVISION_UNREADABLE`, `DOCUMENT_REVISION_UNREADABLE` (a declared document beyond document 0 has no readable revision), `POSITION_ABSENT`, `POSITION_STALE`, `POSITION_UNBACKED` (a sequence item is ticked and its witness was never measured — a blank box claims nothing, a ticked one asserts a step was reached, and no launch is authorized against an assertion nobody checked), `POSITION_SHARDS_UNDECLARED` (the ticked item's witness is `@shard` and nothing named where a returned shard lands — no declared `distribution.shardsRoot`, and `gate` carries no `--shards` of its own to override with; a different fact from `POSITION_UNBACKED`, since this tick was never told where to look at all), `POSITION_DISAGREES` (a sequence item is ticked but its own witness measured the opposite — never a blank, unreconciled item, only a tick that is itself a false claim), `NOT_READY` (no passing rehearsal on file at the job's current pin; for a campaign, `--unit`, also any worker the bound `propose` record names without its own passing rehearsal at that pin — the refusal names each such worker), `JOB_SERVICE_AMBIGUOUS` (folders of `--job`'s name sit under more than one service and no `--service` selects one; one folder per job name needs none), `SEQUENCE_NOT_REACHED` (an earlier item in the sequence is still open, or no item names this job at all), `GATE_WORKER_UNIT_CONFLICT` (`--worker` and `--unit` both given), `GATE_WORKER_REQUIRED` (neither given — there is no auto-select shape for `gate` to authorize), `GATE_AUTHORIZATION_REQUIRED` (`--authorization` omitted), `GATE_AUTHORIZATION_UNKNOWN` (no ledger record vouches for the token, or it no longer re-digests to its own recorded fields), `GATE_AUTHORIZATION_SUPERSEDED` (a legitimate token minted before `proposalDigest` joined the binding — diagnostic only, refused exactly as hard as `UNKNOWN`), `GATE_AUTHORIZATION_MISMATCH` (the record names a different job or unit list), `GATE_AUTHORIZATION_STALE` (a bound fact has moved since minting — never merely elapsed time), `GATE_AUTHORIZATION_CONSUMED` (the token already authorized one successful `gate` call; single-use, never reusable), `GATE_PROPOSAL_UNKNOWN` (the token names no campaign proposal this ledger still vouches for), `GATE_PROPOSAL_MISMATCH` (a genuine, current proposal exists but does not name this job), `GATE_PROPOSAL_STALE` (the proposal's own campaign identity no longer matches live disk — the pin moved, or a job folder was added or removed), `GATE_ELECTION_REQUIRED` (this job classifies `optional` and no `--elect` names it), `GATE_ELECTION_MISMATCH` (`--elect` names a different job, or names this job while it does not classify `optional`), `FORGE_DEFECT_OPEN` (an open forge defect for this target/name — checked first, before every code above), `PRODUCT_DIR_MISNAMED` (this call's `<name>/` holds none of the product categories while exactly one differently-named folder holds them, so the ledger would open a second product tree nothing else reads — refused before the first append, publishing the `plan` that names the folder) |
| `offer` | Records the flow-continuation answer (`--answer yes` or `--answer no`, a closed token) as one `offer` event to `.implementation/position.jsonl`, then publishes a closed action set: one `launch` per job the shared availability rule (`gate` reads the identical verdict) says is available, plus `run-step` when the recorded answer is `yes` or `expand-contract` when it is `no`. Every action is exactly `{id, command, establishes, binding}`; an unavailable action is omitted entirely, never disabled-with-a-reason. `expand-contract`'s own `command` publishes a `discuss --about record --question <text>` invocation, never a write — it carries no `--session` (`discuss` registers none) and, run verbatim, only appends a `discuss` event; it never touches `AGREED.md`. `--answer` is required on EVERY call — never read back from a prior `offer` event, no matter how many exist or what they contain; a supplied answer is always honored and always appends a new event. Repeatable `--unit` is the operator-declared ordered list a `launch` action binds instead of a single-send one, switching its published command to campaign form (`--unit ...`, never `--worker <account>`) — the engine never substitutes its own list. Every published `launch` action's `binding` also carries an `authorization` token: a digest minted over the engine's own re-derived binding (job, commit, entrypoint, units, rung, revision, position status), never over this call's argv alone. Minting is mint-if-absent — a fresh `kind: "authorization"` event is appended only when the ledger holds no unconsumed one already covering that exact binding, the same discipline `cmd_close`'s own `prior_close` lookup uses — so a repeat publish over unchanged state mints nothing new and republishes the same token. The published `command` string carries the minted token as `--authorization <token>`, so it is directly runnable | `OFFER_ANSWER_NOT_A_TOKEN` (`--answer` given something other than `yes`/`no`), `REVISION_UNREADABLE`, `DOCUMENT_REVISION_UNREADABLE` (a declared document beyond document 0 has no readable revision), `OFFER_UNANSWERED` (`--answer` omitted on this call — refuses identically whether the ledger holds no offer event, one, or many; checked above `resolve_target`, so it wins over `FORGE_DEFECT_OPEN` too), `FORGE_DEFECT_OPEN` (an open forge defect for this target/name — checked immediately after resolving target/name, before `REVISION_UNREADABLE`), `PRODUCT_DIR_MISNAMED` (this call's `<name>/` holds none of the product categories while exactly one differently-named folder holds them, so the ledger would open a second product tree nothing else reads — refused before the first append, publishing the `plan` that names the folder) |
| `close` | Refreshes the position (see `position`), then one `close` event to `.implementation/position.jsonl` binding session, revision and a digest of the resulting sequence. A target declaring no flow (no `__levels__`, `__steps__`, `__records__`, shard root or job folder) owes no position: it skips the refresh, binds the empty sequence and reports `positionOwed: false` | `FORGE_DEFECT_OPEN` (an open forge defect for this target/name — checked first, before `REVISION_UNREADABLE`), `REVISION_UNREADABLE`, `DOCUMENT_REVISION_UNREADABLE` (a declared document beyond document 0 has no readable revision), `POSITION_ABSENT` (no position, and the target declares a flow; the detail names what it declares), `POSITION_STALE`, `POSITION_UNBACKED` (a sequence item is ticked and its witness was never measured), `POSITION_SHARDS_UNDECLARED` (the ticked item's witness is `@shard` and nothing named where a returned shard lands — a different fact from `POSITION_UNBACKED`: never told where to look, rather than looked and found silent), `POSITION_DISAGREES` (checked against the position exactly as recorded, before the refresh) — the identical ladder `gate` calls first (`impl_availability.position_honest`), never a second refusal ladder this command writes for itself; `AGREEMENT_DISAGREES` (a separate axis, checked right after the ladder: a ticked `AGREED.md` item whose declared `test_<id>` witness is absent from a fully-parsed `tests/` — the only place this ever gates, `verify`/`probe` only ever report it); `DISCUSSION_UNANSWERED` (a third, independent axis, checked right after `AGREEMENT_DISAGREES` and before the position refresh: at least one distinct `discuss` question text — grouped by exact trimmed text, never by witness identity — has no answer as its last event in ledger order; names every open text and prints one runnable `discuss --answer` retirement command per text), `PRODUCT_DIR_MISNAMED` (this call's `<name>/` holds none of the product categories while exactly one differently-named folder holds them, so the ledger would open a second product tree nothing else reads — refused before the first append, publishing the `plan` that names the folder) |
| `step` | Runs exactly one declared `__steps__` entry as a subprocess under the target's own `.venv/bin/python`, `PATH` prefixed by that interpreter's own directory — see [Non-negotiable isolation](#non-negotiable-isolation). A PAIR of `step` events to `.implementation/position.jsonl` on every run past `INTERPRETER_ABSENT`: `outcome: "started"` the instant before the subprocess spawns, then a terminal event. The ledger's shape is therefore readable on its own — **no event at all means the command never started, a `started` with no partner means it started and was killed (partial product), a terminal event means it ran and reported** — so a step's success is read off this pair, never off an exit code or stdout. The terminal event is `refused` (carrying `refusalCode`, no digest) for the four target-side refusals, and otherwise carries name, dotted callable, interpreter, outcome, exit status, error (when raised), and `suiteDigest` (`suite_digest(target)` — `src/`, `tests/`, and five fixed environment manifests, computed fresh at write time, unconditionally regardless of outcome). This reverses "no digest field" only for a bare runner step with no self-stamping artifact of its own; a notebook still recomputes `source_digest` fresh against its own `DIGEST_MARKER` output, so a ledger-carried copy there would still be redundant. An `@step` witness in `position`'s own sequence reads this ledger's latest event per step name (latest wins) and folds `True`/`False`/`unmeasured` from it — stale digest or a pre-change event with none of its own both read as `unmeasured`, never a false `True`/`False`. **A step that runs remotely** (declared `placement: "remote"` with a `job`, or named after a job folder) is never ticked by a local `step` run: `position` ticks it once `fetch` has recorded a `returned` on the MAIN ledger (`<Name>/.remote-execution/ledger.jsonl`, never `smoke.jsonl`) for every worker's latest submission of that job, judged `current` by the remote-execution fold, and the returned `bootstrap.json` names the commit the job folder is pinned to now; a pending or errored submission, a quarantined result, or a result from an older pin reads `unmeasured`, with a `reason` naming which. The digest is deliberately not narrowed to what the step executes (its callable may run the suite or a file under `tests/`, and the engine cannot see which), so any edit under `src/` or `tests/`, a test-only one included, leaves every earlier step mark unmeasured until that step runs again: commit code and tests before the first pilot step. Each unmeasured `@step` item carries `reason` (never ran, or last run no longer counts, plus the exact `step` command) and `digestScope`. **Stated non-goal:** this witness does not distinguish a fully-executed suite from one that skipped tests — `pytest` exits 0 on skips, so `returned` grades green over a skipped suite exactly as a notebook report already does; closing assert-forgetting is not closing skip-laundering. Every successful call publishes `next`: the two runnable acts that stand between this step and the following one, so the loop is read where it is needed rather than remembered. `next[0]` is `git status --porcelain` over the target — **a step's product is committed before the next step runs**, because every step dirties the target with its own product and the next one refuses `DIRTY_WORKTREE` until it is clean; the listing is published and the commit message stays the operator's, this skill never authors one. `next[1]`, present only when the product carries a readable position block, is the exact `position` refresh bound to that block's own revision, because nothing else updates the marks an ordered next step reads. Published on every run including `raised` and `unknown` — a step that failed still left what it wrote in the tree, and a killed one left more of it. A declared six-step flow is therefore six `step` calls, five commits and five refreshes. Every successful call also publishes `wrote` — what this run changed in the product folder, split by whether the step owns it: `status` (`own`/`nothing`/`foreign`/`undeclared`), the `declared` roots, the `inside` and `outside` paths, `ignored` (always present, `[]` when clean — the subset of `inside` the repository's own ignore rules exclude, so it will never enter the repository's history even though the declaration reads satisfied), an `ignoredNote` (present only when `ignored` is non-empty), and a note. `ignored` is computed over `inside` only, never `outside` — a foreign write is already the strongest reading this skill gives for that half. `foreign` is the reading nothing else in this skill can take: a step that wrote into another step's product tree reports `outcome: "returned"`, passes every other check, and changes only a field inside a file nobody opens. The same block minus its note and its ignoredNote is written into the terminal ledger event — the paths, never the prose — so both readings are durable rather than printed once. Paths are compared by `(size, mtime)` per file — every write a filesystem records moves it — with `.implementation/` excluded for the reason the dirty-tree guard excuses it. A step naming no `produces` reports `undeclared` and is graded against nothing; `verify`'s own `undeclaredProduces` is where that is said per step. Every successful call also publishes `lastRun`: the elapsed seconds of the LAST completed run of this same step, folded from the `started`/terminal pair already on the ledger. It is a MEASUREMENT and never a budget, it costs the target no declaration at all — an `expectedMinutes` in `__steps__` would be a field this skill reads and therefore one a from-zero repository would have to be made to ship — and its limit is published rather than implied: `status: "unmeasured"` on a step nobody has run yet, which is exactly the run whose cost surprises somebody. A run that started and never reported measured nothing and is skipped, so the field agrees with the ledger's own shape. Never appends, reads or alters a `gate` event, and calls none of the remote-execution loaders — there is no call path from here to a launch | `FORGE_DEFECT_OPEN` (an open forge defect for this target/name — checked first, before `DIRTY_WORKTREE`), `DIRTY_WORKTREE` (before any subprocess spawns), `STEPS_UNDECLARED`, `STEP_UNKNOWN`, `STEP_MALFORMED` (declared entry missing `module` or `function`), `STEP_SEQUENCE_NOT_REACHED` (an earlier sequence item is still unticked — the mark read is the literal one in `AGREED.md`, which a step that just ran does not update, so the refusal publishes the exact runnable `position` refresh bound to the revision the block already names; `position` is the only writer into that section and `step` never becomes a second one), `INTERPRETER_ABSENT`, `STEP_MODULE_MISSING`, `STEP_FUNCTION_MISSING`, `STEP_NOT_CALLABLE`, `STEP_RUNNER_SILENT` (the process exited without ever writing a verdict), `PRODUCT_DIR_MISNAMED` (this call's `<name>/` holds none of the product categories while exactly one differently-named folder holds them, so the ledger would open a second product tree nothing else reads — refused before the first append, publishing the `plan` that names the folder) |
| `settle` | Places exactly one caller-authored `- [ ] <text>` line, verbatim, under a caller-named `--under <heading>` (exact match, hash marks included) in this skill's own declared holder (`the-holder-each-skill-declares` D10: every mode resolves through `holder_resolution` and writes into exactly that one resolved file — never every by-shape candidate `agreements_state` finds) — the mark written is always `[ ]`, never `[x]`. `--about` is resolved the identical way `discuss`'s own `--about` is, then matched against the ledger by witness identity `(kind, operand)`; ANY answered `discuss` event satisfies this, never newest-wins, so a later open clarifying question never erases an earlier answer. On a collision (the same `_agreement_collides` search `discuss` reports), `--supersedes <text>` must exact-match one of the computed colliding items; recorded in the one `settle` ledger event only — the document itself still needs a human-written `Reversed` paragraph to show the supersession actually happened, which this command deliberately cannot author. Optional `--witness test_<id>` — a separate identity from `--about` — is persisted verbatim as a trailing `` `test_<id>` `` token; omitted, the written line is byte-identical to the pre-witness grammar. `settle` is the ONLY command that ever writes this token: there is no `patch`/`edit` subcommand, and hand-typing one into the file is unsupported doctrine, not a technical prevention — the parser cannot and does not distinguish a skill-written token from a hand-typed one, and `verify`/`close` evaluate either exactly the same way. No `--revision`: a placement binds to no revision. **`--attach`** (design "attach, not place") switches this same command into a second mode: bind `--witness` (required in this mode) onto a line ALREADY settled, matched by its exact `--text` — the mark is never touched, a ticked item stays ticked and an open one stays open, and everything else in the holder file is byte-identical afterward. `--under`/`--about`/`--supersedes` do not apply with `--attach` and are refused if given; the discussion precondition (`SETTLE_NOT_DISCUSSED`/`SETTLE_DISCUSSION_UNANSWERED`) is skipped entirely, because a line `--attach` matches was already discussed and placed by a prior `settle` call — attaching a witness to it is not placing a new agreement (see `cmd_settle`'s own docstring for the full reasoning). This is the retrofit mechanism, not the retrofit itself: running it over every already-settled line in a target is a separate, bounded, operator-directed pass. `--attach` also takes `--replace` (`re-pointing-a-proof-is-not-retracting-a-claim`): instead of refusing `SETTLE_ALREADY_WITNESSED`, it re-points the located line's EXISTING witness onto the incoming `--witness` token — mark-blind, exactly as untouched between a ticked and an open line as plain `--attach` already is. Refused `SETTLE_NOTHING_TO_REPLACE` if the located line carries no witness at all (plain `--attach`, without `--replace`, is the create path for that) and `SETTLE_WITNESS_UNCHANGED` if the incoming token equals the one already there. Performs no read of `tests/` and no check that either witness names a real test — that gate stays exactly where it already was, at `verify`/`close`. The previous token is recorded as `replacedWitness` in both the `settle` ledger event and this call's response, beside an always-present `replace` boolean mirroring the other four mode flags. **`--remove`** (design "the eraser") switches this same command into a third mode: delete an already-settled line's own bytes outright, matched by its exact `--text`, touching no other byte in the document. Refused `SETTLE_NOT_REVERSED` unless the exact text is already quoted, bold, under a `## Reversed` heading somewhere in the same holder — deletion is refused until the document itself already explains why, and `--remove` deliberately cannot author that explanation. `--under`/`--supersedes`/`--witness` do not apply and are refused if given. **`--reverse`** (design "a reversal is one write") switches this same command into a fourth mode: write a NEW `## Reversed` entry (from `--paragraph`, required — `SETTLE_PARAGRAPH_REQUIRED` if blank or omitted, since the engine never authors the reasoning) and delete that same located line, both folded into ONE spliced write — either both land or the compare-and-swap itself refuses and neither does. Refused `SETTLE_ALREADY_REVERSED` if the text is already quoted under `## Reversed` (plain `--remove` is the reachable command for that state) and `SETTLE_HEADING_AMBIGUOUS` if the holder carries more than one `## Reversed` heading; with none, the first reversal opens `## Reversed` at the end of the file. `--under`/`--supersedes`/`--witness` do not apply and are refused if given. **`--done`** (design "the tick this class closes") switches this same command into a fifth mode: flip an already-settled line's own mark from `[ ]` to `[x]`, matched by its exact `--text` — the text, any witness token it already carries, and every other byte in the holder file are unchanged. Refused `SETTLE_NOT_WITNESSED` unless the located line already carries a `` `test_<id>` `` token: a tick asserts the work is done, and this command refuses to author that assertion for a line nobody can point a test at — bind one first with `--attach`. Refused `SETTLE_ALREADY_DONE` if the located mark is already `x`/`X`. `--under`/`--supersedes`/`--witness`/`--paragraph` do not apply with `--done` and are refused if given; the discussion precondition is skipped for the identical reason `--attach` skips it. **`--done --unwitnessed --reason <text>`** is the recorded closing act for a line no test could ever witness (a scoping decision, a premise, a deferral): the same one-byte flip, only on a line naming no witness, with the operator's reason and the session written to the ledger event and the response (`unwitnessed: true`, `reason` — both absent from every other call); `agreements.witness.decided` names it and it is never counted as witnessed (see `cmd_settle`'s own docstring for the full guard argument). **No mode un-ticks**: a mistaken tick is corrected with `--reverse` (works on a ticked line; the explanation and the ledger event stay) followed by a fresh `--under` placement. A create-path item is appended after the section's last checklist item (oldest first), never inside the position block | `FORGE_DEFECT_OPEN` (an open forge defect for this target/name — checked first, before every code below), `SETTLE_STDIN_CONFLICT` (`--text -` and `--supersedes -` together), `SETTLE_EMPTY_TEXT`, `SETTLE_ATTACH_CONFLICT` (`--attach` combined with `--under` or `--supersedes`), `SETTLE_REMOVE_CONFLICT` (`--remove` combined with `--attach`/`--under`/`--supersedes`/`--witness`), `SETTLE_REVERSE_CONFLICT` (`--reverse` combined with `--attach`/`--remove`/`--under`/`--supersedes`/`--witness`, or `--paragraph` given without `--reverse`), `SETTLE_DONE_CONFLICT` (`--done` combined with `--attach`/`--remove`/`--reverse`/`--under`/`--supersedes`/`--witness`/`--paragraph`), `SETTLE_WITNESS_REQUIRED` (`--attach` without `--witness`), `SETTLE_PARAGRAPH_REQUIRED` (`--reverse` without a non-blank `--paragraph`), `SETTLE_UNDER_REQUIRED` / `SETTLE_ABOUT_REQUIRED` (create path only, omitted without `--attach`/`--remove`/`--reverse`/`--done`; `--about` is not asked for with `--unwitnessed --reason`, the witness-less placement, which refuses `--about`/`--witness`/`--supersedes` as `SETTLE_UNWITNESSED_CONFLICT`), `SETTLE_NOT_DISCUSSED` (no `discuss` event names this witness identity at all — create path only), `SETTLE_DISCUSSION_UNANSWERED` (events exist, none `answered` — create path only), `SETTLE_HOLDER_ABSENT` (narrowed, `the-holder-each-skill-declares` D9: no product folder exists to create the declared holder in — `settle` creates that holder itself, with its declared heading scaffold, the moment the folder exists, and only together with the line it writes: a refused `settle` or `position` creates no holder), `HOLDER_UNDECLARED` (an existing checklist holds items under a name neither this skill nor any sibling skill sharing the engine declares — narrows `settle`'s write set to exactly the one resolved holder, D10; names both exits — rename the found file to the declared name in the target repository, or declare that name as this skill's own `PROFILE["holder"]["filename"]`; a sibling skill's own declared holder is never a candidate and is never offered for renaming), `SETTLE_HEADING_ABSENT` / `SETTLE_HEADING_AMBIGUOUS` (create path: the named heading occurs zero, or more than one, times across every holder — a fenced code block's own heading-shaped line never counts as an occurrence; `SETTLE_HEADING_AMBIGUOUS` also on the `--reverse` path when the holder carries more than one `## Reversed` heading), `SETTLE_TEXT_ABSENT` / `SETTLE_TEXT_AMBIGUOUS` (`--attach`/`--remove`/`--reverse`/`--done` paths: `--text` matches zero, or more than one, existing checklist line across every holder), `SETTLE_ALREADY_WITNESSED` (`--attach` path, `--replace` absent: the one located line already carries a witness token; `--attach` adds a witness, it never replaces one on its own — the detail names `--replace` as the exit), `SETTLE_REPLACE_CONFLICT` (`--replace` given without `--attach` — it modifies that mode and names nothing on its own), `SETTLE_NOTHING_TO_REPLACE` (`--attach --replace` path: the located line carries no witness at all, so there is nothing to re-point — plain `--attach` is the create path), `SETTLE_WITNESS_UNCHANGED` (`--attach --replace` path: the incoming `--witness` equals the one already on the located line, so the write would be a no-op), `SETTLE_NOT_REVERSED` (`--remove` path: the exact text is not already quoted, bold, under a `## Reversed` heading in the same holder), `SETTLE_ALREADY_REVERSED` (`--reverse` path: the exact text is already quoted under `## Reversed`; plain `--remove` is the reachable command for that state), `SETTLE_ALREADY_DONE` (`--done` path: the located line's own mark is already `x`/`X`), `SETTLE_NOT_WITNESSED` (`--done` path: the located line carries no witness token; the detail names `--unwitnessed` for a line no test could ever witness), `SETTLE_UNWITNESSED_CONFLICT` (`--unwitnessed` without `--done`, or `--reason` without `--unwitnessed`), `SETTLE_REASON_REQUIRED` (`--done --unwitnessed` without a non-blank `--reason`), `SETTLE_WITNESS_PRESENT` (`--done --unwitnessed` path: the located line names a witness — plain `--done` closes it), `SETTLE_COLLIDES_UNNAMED` (create path: a collision exists and `--supersedes` was not given; names every colliding text verbatim, never a count, and prints one runnable `discuss` command asking which one, if any, this placement supersedes), `SETTLE_SUPERSEDES_UNKNOWN` (create path: `--supersedes` names text absent from the computed collision list), `SETTLE_WITNESS_MALFORMED` (`--witness` given and not `test_[A-Za-z0-9_]+`, either path), `POSITION_HOLDER_MOVED` (reused unchanged from `position`/`close` — the holder's bytes changed between the read that located the line and the write), `PRODUCT_DIR_MISNAMED` (this call's `<name>/` holds none of the product categories while exactly one differently-named folder holds them, so the ledger would open a second product tree nothing else reads — refused before the first append, publishing the `plan` that names the folder) |
| `defect` | One `defect` event to `.implementation/position.jsonl`: the forge-relative `--file` path, its live `fileSha256` digest, `session`, `at` and, when given, `detail` (omitted entirely, never written as `null`, when not given). Declares that some file this forge itself ships is currently broken. While this stays open (see `open_defects`), `step`, `gate`, `offer`, `close`, `settle`, `apply`, `admit` and `adopt --apply` all refuse `FORGE_DEFECT_OPEN` for this exact `<target>/<name>` — see their own rows below, and `apply`/`admit` in [The rest of the surface](#the-rest-of-the-surface-and-the-roster-closed-at-twenty-one). `probe`, `verify`, `position`, `plan`, `compose`, `handoff` and `discuss` stay reachable throughout; `handoff` additionally surfaces every open defect (file, session, detail) in its report. Never gated on an already-open defect and calls no worktree guard itself: a second declaration while one is open must stay possible, and the worktree is likely dirty precisely when something is broken. Repeatable — a call over an unchanged digest appends a fresh event rather than editing or refusing. Clearing happens the moment the named file's bytes change; asserting a fix in a fresh `--detail` on unchanged bytes does not clear it. **Deleting the file after a defect was declared against it is itself a clear**, decided rather than an oversight: the recorded digest can never again match an absent file, so absence is the strongest possible digest change (`ABSENT_FILE_DIGEST`, see `impl_position.current_file_digest`) — not a hole to close. This blocks mid-flow forge repair once detected; it does not prevent the edit itself — no hook or deny rule is added. Scope is per `<target>/<name>`, never a switch that blocks every target at once: a parallel session on a different target running the identical broken code must rediscover it | `DEFECT_FILE_NOT_FORGE_OWNED` (`--file` resolves outside `FORGE_ROOT/skills` — checked before existence, so this command never reports on the existence of anything outside that tree), `DEFECT_FILE_ABSENT` (`--file` is not a regular file; a path that never existed is refused rather than recorded, since the sentinel it would otherwise carry could never clear on its own), `PRODUCT_DIR_MISNAMED` (this call's `<name>/` holds none of the product categories while exactly one differently-named folder holds them, so the ledger would open a second product tree nothing else reads — refused before the first append, publishing the `plan` that names the folder) |
| `walk` | Walks the declared flow toward the rung the position header aims at, act by act, in `advances` order. It executes the **published subcommands as subprocesses** rather than calling their functions, so every guard those carry applies exactly as it does to a person running them — nothing re-implemented, nothing bypassed; a walker that reached inside would be a second path to the same acts, and the second path is always the one missing a check. It performs `run-local` and `generate-job` and STOPS at a `rehearse` — no act here performs a rehearsal, and the doctrine below leaves it to a person — refreshes the position after each local step, and records that step's product with a **mechanical** message naming the step and nothing else (subject `walk: <step>` by default; `--commit-template '<subject with {step}>'` reshapes it, e.g. `chore(walk): {step}` for a target that enforces Conventional Commits) — `step` refuses on a dirty tree and every step dirties it, so a walk that stopped to ask for a message would not be a walk; what the work MEANS stays the operator's and none of it is pushed. It appends to no ledger itself: every write goes through `step` or `position`. **It stops at a launch and has no path to `submit` at all**. When more than one remote step is ready at once it also returns `concurrentLaunches` (see `launch-plan` below): every `launch` step whose `reads` are already produced — by steps already done or by the local steps this walk just ran — and every remote step still `waiting`, with the steps it `waitsOn` named. Each launchable step goes out through its own `launch-plan`/`propose`/`offer`/`gate`, on the service its step declares; one launchable step adds no key, and the result is the serial one | Refuses `FORGE_DEFECT_OPEN`, and `WALK_COMMIT_TEMPLATE_MALFORMED` before anything runs when `--commit-template` holds no `{step}`, any other brace, or more than one line; otherwise it does not refuse, it STOPS — at the first act it will not take (`launch`, `blocked`, or an unclassified act) or the first that refused, returning `performed` and `stoppedAt`. Stops rather than filtering and continuing, because the flow is ordered: a step that cannot run is one whose output every later step reads |
| `materialize` | Exactly one of three mutually exclusive modes. `--stage <scaffold\|objects\|harness> --plan <path> [--seed <n>]`: plan-gated (the `PLAN_MISMATCH`/`PLAN_STALE` pattern `apply` uses) and clean-worktree-required; writes the chosen stage's file destinations from the kit — `scaffold_destinations` for `scaffold` (plus its two merge anchors, `.gitignore`/`pyproject.toml`), `object_destinations` for `objects` (gated on step 8's declaration; `--seed` required), `harness_destinations` for `harness` (no `--seed` needed, gains `src/<Package>_Benchmark/__init__.py`) — and records every write in `<Name>/.implementation/materialization.json` (git-ignored), written last, atomically, after every file has landed. `--authored <path>`: releases the drift seal on one receipt-recorded destination, any of `all_kit_destinations` (the paths listed under "The sealed set" in `references/usage.md`) or a file the objects stage recorded under a `--module` name, after the agent has authored over it (a notebook's seal reads its cell types and sources, so executing `verification.ipynb` or `probe.ipynb` in place is not drift and needs no `--authored`) — no file write, no plan gate, a dirty tree is fine (precedent: `_is_own_bookkeeping`). `--adopt <path>`: records an unrecorded destination's current bytes into the receipt as `kind: "adopted"` — the degraded guarantee, spelled out in `references/usage.md`: the record names who is responsible for the bytes, never that they came from the kit | `FORGE_DEFECT_OPEN` (an open forge defect for this target/name — checked first, before every code below: `materialize --stage` writes kit destinations over the target, so it spends exactly as `apply` does), `MATERIALIZE_MODE_REQUIRED`, `MATERIALIZE_MODE_CONFLICT` (two or more of `--stage`/`--authored`/`--adopt` given together), `OUTSIDE_WORKSPACE`, `NOT_A_GIT_REPO`, `DIRTY_WORKTREE` (`--stage` only), `PLAN_REQUIRED`, `PLAN_MISMATCH`, `PLAN_STALE`, `SEED_REQUIRED` (`scaffold`/`objects` only), `OBJECT_MAP_NOT_APPROVED` (`--stage objects` before step 8's `revision`/`premises` are recorded), `OBJECT_MAP_AT_OLD_HOME` (`--stage objects` on a target scaffolded before `__implementation__` existed, whose `revision`/`premises` still sit at the pre-relocation home — see the migration procedure at step 8), `STAGE_CANNOT_ANSWER` (a scaffold-stage template still carries an unresolved `{{TOKEN}}` after substitution), `DESTINATION_CONFLICT` (a destination appeared between the set computation and the write, the whole stage refused before any byte lands), `APPLY_ABORTED` (mid-write failure; tree reset and cleaned, no receipt entry), `NOT_A_KIT_DESTINATION` (`--authored`/`--adopt` naming a path outside `all_kit_destinations`; the detail lists every accepted path), `MATERIALIZE_PATH_ABSENT` (naming a path with no bytes on disk), `NO_RECEIPT_ENTRY` (`--authored` on a path the engine never wrote — use `--adopt`), `ALREADY_RECORDED` (`--adopt` on a path the receipt already carries — use `--authored`) |
| `adopt` | Two modes mirroring `plan` → `apply`, with the human gate between them. Survey (`--source <folder> --target implementations/<repo> --name <Name>`): normalizes the name first, copies the tree (never moves it; `.git/` starts fresh), git-inits and commits the copy, detects the paper draft (zero means code-only, one is proposed as the v1 base, several refuse), runs the plan machinery over the copy, and writes `adoption-plan.json` at the target's root — source, target, name, `sourceTreeHash`, the paper candidate, the reorganization with its decision count and scale, the scaffold gaps and the adopted files. Mutates nothing else. Apply (`--apply --plan <path> [--session <id>] [--seed <n>]`): revalidates the surveyed bytes, places the draft as the managed v1 (unmanaged staging confirmed by `STATUS`, marker bytes prepended, renamed to `research-concept-r01.md`, consistency must hold), lands the `git mv` migration with its reference updates in one commit, writes the scaffold stage, records each surveyed file through the unchanged per-file adopt, and closes with the `verify` report. Prior work keeps its own package under `src/` and never lands in `src/<Package>/` | `SOURCE_NOT_FOUND` (no `--source`, or a source that is not a directory), `ADOPT_AMBIGUOUS` (several drafts could be the v1 base, `proposals/` already holds managed revisions, or the staged draft's standing is unestablished), `OUTSIDE_WORKSPACE`, `NOT_A_GIT_REPO`, `DESTINATION_CONFLICT` (the target exists, nests inside the source, or two sources clash), `PLAN_REQUIRED` (apply without `--plan`), `PLAN_MISMATCH` (a plan from another target, name, or command), `PLAN_STALE` (the copy moved since the survey), `DIRTY_WORKTREE`, `UNCLASSIFIED_FILES`, `APPLY_ABORTED`, `STAGE_CANNOT_ANSWER`, `NOT_A_KIT_DESTINATION`, `MATERIALIZE_PATH_ABSENT`, `ALREADY_RECORDED`, `INVALID_NAME`, `FORGE_DEFECT_OPEN` (checked before the apply moves anything) |

### The rest of the surface, and the roster closed at twenty-one

The table above is the write-verb half. A partial roster read as a complete one
is the failure this heading exists to prevent, and this file has already made
it once: a limitation paragraph at the top said the CLI accepted nine and
refused everything else by naming them, so the running code held a roster this
document did not. Nothing derived that nine. By the time anybody measured it
the surface had doubled and the sentence was still there, unchallenged, because
a spelled number with nothing reading it cannot go red.

`COMMANDS` binds twenty-two subcommands and dispatches nothing else. The twelve
above and the ten below are that set, stated here as closed. The ten are not
lesser commands; they are the ones whose contract is already carried at length
elsewhere — `probe` and `verify` each own a status roster of their own, and
restating those statuses here would be the second definition of one rule this
file's doctrine keeps rejecting. So for them the load-bearing column is the
third: where the detail actually lives.

| Command | What it does | Where its detail lives |
| --- | --- | --- |
| `name` | Normalizes a name as the user typed it into the directory/package pair every later command takes as `--name`, and reports it so the agent can show it before writing anything. The only command that takes no `--target`: it runs before a target exists. Refuses `NAME_EMPTY`, `NAME_HAS_NO_WORDS`, `NAME_NOT_ALPHANUMERIC` and `NAME_STARTS_WITH_DIGIT` rather than guessing a spelling | `references/usage.md`, *The name, normalized before the directory exists* |
| `env` | Adds `.venv/` and `*.egg-info/` to the clone's `.git/info/exclude` (reported as `excluded`) so its own products never dirty the tree, then builds the target's own `.venv` under `implementations/<repo>/`; `--torch cpu` or `--torch gpu` (optionally with `--torch-version X`) adds a torch build to `nextCommand` (see `nextStep: "convert"`; `TORCH_VERSION_REQUIRED` when `cpu` has no exact release), refusing an interpreter below 3.10 or below the target's own declared `python_requires`, whichever is higher — and refusing outright to run from a forge virtualenv. Reports every LFS pointer as a placeholder with the real file's size, at the one moment a repository full of pointers looks complete | `references/usage.md`, *2. The isolated environment* |
| `plan` | Reads the repository and returns the migration it would perform — `renames`, moves, `createDirs`, `referenceUpdates`, `unclassifiedFiles` — and writes nothing. The artefact the user approves; `apply` refuses anything else | `references/usage.md`, *3. Plan the migration (read-only)* |
| `apply` | Executes exactly the approved plan — and refuses anything else — as one separate `git mv` commit, all-or-nothing: the tree is verified clean first, and a mid-migration failure restores the reviewed starting point rather than leaving a half-migrated repository. A gating command — it refuses `FORGE_DEFECT_OPEN` like the write-verbs above | `references/usage.md`, *4. Apply, as one separate commit* |
| `verify` | Reports layout, revision fidelity, scaffold/object/harness drift, the audit bridge's state and every executed notebook's interpreter. Reports and never gates: its statuses are their own roster, held to `cmd_verify`'s own returns | `references/usage.md`, *5. Verify* and *Reading `verify`* |
| `admit` | Rules on each remedy's admissibility before anything is measured, and writes the verdict into the target so the remedy suite can refuse to run without it. Only the verdict travels — the proposal's text stays in the forge. Gating, and refuses `FORGE_DEFECT_OPEN` | `references/usage.md`, *`admit` — admissibility is ruled on first* |
| `compose` | Rewrites one resolved entry so a finding's remedy takes its place, substituting inside the entry rather than handing back the bare block, and using the equation's own `\tag{n}` as the identity it lands on | `references/usage.md`, *`compose` — the remedy takes the entry's place* |
| `handoff` | Hands the open findings back to the deliberation, sized by their reach: a local remedy travels as an agenda item, a structural one as a reason code and the numbers behind it, for a session of its own. This command composes no sentence for a reader: nothing hands a program the language it is being spoken to in, so it hands over what it knows — the code, the measurements, and the domain's own nouns — and the agent does the speaking. Also surfaces every open forge `defect` — file, session, detail — in its report | `references/usage.md`, *`handoff` — back to the deliberation, sized by reach* |
| `probe` | Reports what stands between this repository and a benchmark, and runs nothing. Answers `nextStep`, which is what the Decision Gates rows are written about and what a reader is sent to before every offer to run. Its reported facts are their own roster; none of them is a gate | `references/usage.md`, *Probe — what stands between this repository and a benchmark* and *Reading `probe`* |
| `launch-plan` | Lists, for one `--job` (with `--service <service>` when folders of that job name sit under more than one service, refused `JOB_SERVICE_AMBIGUOUS` otherwise), the acts still between it and its launch — `propose`, `offer`, `gate`, `submit`, in order — each with `status` (`done`/`blocked`/`next`/`pending`), the code it would raise now and the exact command to run, plus `launchLadder` when the ladder still owes the launch a `@rehearsal` witness or a measurement. Plus `concurrentLaunches` when more than one remote step can launch at once: `launchable` (each `{step, job}` whose `reads` are all produced by steps already done, or that reads nothing — independent steps, in particular steps placed on different services, launched concurrently, each through its own `propose`/`offer`/`gate`), `waiting` (each remote step whose `reads` come from a step not yet done, with that step named in `waitsOn`; a step declaring no `reads` key waits on every owed step ahead of it) and a `note`. Absent with one launchable step, so the serial plan is unchanged. Read-only: no ledger event, no token, no file. Every verdict is the act's own rule read through the same functions (`launch_available`, `_verify_gate_proposal`, `_find_authorization`, `remote_cli`'s gate-record and diagram checks). Run it before `generate-job` and before `gate` | `references/usage.md`, *`launch-plan` — what is still missing before a job launches* |

### Every refusal declares how it is cleared

The write-verb table's `Refuses on` column enumerates codes. A code is not an exit: a live
session hit `POSITION_DISAGREES`, the engine printed the code and a sentence,
and the agent driving the CLI composed the next question itself — "Do you want
me to do that now?". That is the failure this section exists to make
impossible. **The engine publishes what happens next. The agent never composes
it.**

One hundred and thirty-two distinct codes are reachable from the ten gating
commands — `apply`, `admit`, `gate`, `offer`, `close`, `step`, `settle`,
`materialize`, `position`, `agree` (`GATING_COMMANDS`). **Reachable from, not
raised inside**, and the difference cost a live session: the roster was first
built from a walk over the `cmd_*` bodies alone, which cannot see a refusal a
command reaches through a helper, so forty-two codes — `DIRTY_WORKTREE` among
them — were never classified and reached users bare. The suite derives the set
by following calls out of those bodies and out of `implementation_cli.py` into
`_core/implementation/`. `agree` joins this roster unconditionally (its own
`cmd_agree` stays a plain module-level function whether or not `COMMANDS`
registers it for a given profile), so its two codes are reachable here even
under a profile that never registers `agree` at all. Each code is classified
in `GATING_REFUSALS` by one derivable test, and the classification is a
decision somebody made rather than a shape somebody noticed:

> Can the caller clear this by changing the invocation alone, without touching
> the repository?

- **Yes — an *invocation* defect** (60 codes). The detail already names the
  flag, the token or the mutual exclusion. Nothing is published beside it: a
  `resolve` key on every refusal is the shape a reader learns to skip, and that
  is how a real one stops being read.
- **No — a *work state*** (72 codes). Somebody must act on the repository, so
  the refused payload carries `resolve`: `{kind: "command", command}` when the
  engine can name the whole exit, or `{kind: "question", question, command}`
  when the next act is a decision, where `command` is the runnable `discuss`
  invocation that opens it.

Every published command — a `resolve`, a `next` act, an `offer` action, a `toDiscuss` entry — is runnable **verbatim from any directory**: it carries the absolute path of the interpreter running this CLI and the absolute path of the CLI itself (`CLI_INVOCATION`), both `shlex.quote`d, and every embedded path is absolute. The script ships mode 644 with no execute bit, so a bare relative script name was runnable from exactly one directory and silently not from any other — a shell's `command not found` reaches a harness on stdout with exit status 0, which is a step that never ran reported as a step that did.

A `resolve` is published only when the refused **call** is itself a gating one.
The roster's reach crosses helpers that non-gating commands share — `plan` runs
the same dirty-tree guard `apply` does — and a resolution built from arguments
the refused command never carried would not run.

`POSITION_DISAGREES` resolves to re-executing the verification notebook under
the target's own venv with that venv's `bin` on `PATH` — see
[Executing a notebook needs `PATH`](#executing-a-notebook-needs-path-not-just-the-right-python)
— and then re-running `position` to rebind the mark to what was measured.

Two classifications are worth stating because a reader will argue with them.
`GATE_AUTHORIZATION_REQUIRED`'s detail *does* name a flag, and it is still a
work state: naming `--authorization` is not the same as being able to fill it,
because the token is minted only by a prior `offer` publish. And
`POSITION_ABSENT` publishes a question rather than a command — measured, not
assumed: the obvious `position --reconcile` was run and refused
`POSITION_TARGET_LEVEL_REQUIRED`, because a fresh header cannot be written
without naming the rung the pass aims at, and only the target's own `__levels__`
name the rungs.

`position` was the ninth command to join the roster, and it joined on the
criterion rather than by history: it reads the target before it writes, and two
of its refusals — `POSITION_HOLDER_AMBIGUOUS` (two files carry the block) and
`POSITION_LEVELS_UNDECLARED` (a leveled item, no ladder declared) — were work
states reaching their reader as a bare code, which is the exact defect this
roster exists to make impossible. `POSITION_RUNG_SKIPPED` joined with it.

The roster is derived-against rather than proof-read, exactly as the Output
Contract's status table is: the suite walks the gating commands' own source for
the codes they raise, so **a refusal added to a gating command fails the tests
until it has been classified.** Adding a code that publishes nothing is now a
decision with a name on it, not an omission.

### When the forge itself crashes mid-flow

Declaring a defect is not the only way one gets recorded. `main()` catches
exactly one coded exception, `Refused`, for its ordinary exit-2 report; any
OTHER exception raised while dispatching a command — a bug in this forge's
own code, not a caller mistake — is, by definition, a forge-side defect, and
is auto-appended as a `kind: "defect"` event (naming the crashing module and
its own current digest) before the original error is raised again unchanged.
No agent has to notice this and run `defect` by hand first.

This needs `<target>` and `<name>` to have a ledger path to write into at
all, so it inherits the same stated limit `defect` itself does not close:
`env` (no `--name`), `name` (no `--target`) and `compose` (nothing
layout-shaped to address) cannot be recorded against and are left exactly as
crash-prone as they already were. A crash inside one of those three still
propagates in full; it is simply never captured.

## References

- `references/usage.md` — worked invocations of every command.
- `scripts/implementation_cli.py` — every command in [Command Roster](#command-roster), and nothing outside it. Stdlib only.
- `assets/` — pyproject, module, test and notebook templates.
