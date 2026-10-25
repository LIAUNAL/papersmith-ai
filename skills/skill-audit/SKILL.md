---
name: skill-audit
description: "Trigger: audit a skill, a CLI, or any subject that enumerates a closed set — accepted operations, subcommands, error codes, shipped assets — for the gap between what the running code accepts and what its own documentation claims. Derives both halves rather than reading either: the code side by driving the subject as a real process and taking the roster out of its own refusal message, the documented side by parsing a table. Reports; never repairs. Refuses outright without a shell, because an audit that cannot execute cannot adjudicate. Stdlib-only, no venv, no network except through `structure`'s opt-in `driver` step."
---

# Skill Audit

This skill looks for one defect: a closed set that is stated by hand in more
places than it is derived, so the statements drift from the running code and
from each other. Every roster restated by hand is a roster that eventually
loses one. The audit finds them by deriving both halves and comparing, and then
it **stops** — the report is the deliverable, and the repair belongs to whoever
owns the subject.


## What this skill delegates, and to whom

The audit itself is one stretch, and it runs in an agent of its own rather than
in the conversation that asked for it.

| Stretch | Delegated to | Begins after | Ends at | Measure this before delegating |
| --- | --- | --- | --- | --- |
| Report | this skill delegates to the `audit-report` agent | a subject is named | the report | the subject can be driven as a real process, and a shell exists — an audit that cannot execute cannot adjudicate |

**Not for comfort — for the result to mean anything.** This stretch derives two
halves separately: what the code accepts, taken from the subject's own refusal,
and what the documentation claims, parsed from its table. A context that already
carries the subject has seen one of the two before deriving it, which is the
same failure as a fixture written and read by one hand.

What moves is execution, never doctrine: every rule stays here, and the agent's
first instruction is to load this file. And what the agent may do is narrower
than what this skill describes — it has no `Edit` at all, so **reports; never
repairs** stops being a sentence and becomes a fact about what it can reach.

## When a delegated agent cannot be spawned

The stretch this skill delegates is defined in full by its agent file:
`.claude/agents/audit-report.md`. When that agent cannot be spawned — the
harness has no sub-agent mechanism, the agent is not registered in this
session, or the spawn itself fails — perform the stretch inline: read the
definition file and follow it as written, from the beginning it states to the
end it states, holding any gate this skill sets before the stretch, and returning the
report shape it specifies. Its `tools:` line still bounds the stretch: an act
that would need a tool outside that list is a stop, not a workaround. Say in
the reply that the stretch ran inline and why the agent could not be spawned.

## Activation

The audit needs to run things. Without a shell it must **refuse**.

If the `Bash` tool is unavailable, say so, name `Bash` as the missing
capability, and stop. Emit **no report**, **no finding**, **no candidate**, and
no partial verdict. Do not fall back to reading the subject's source and
describing it: reading is what produces a document full of claims marked
`read-only` with nothing `CONFIRMED by execution` anywhere, and a document like
that reads as an audit while carrying none of an audit's authority. This skill
does not degrade to reading; it refuses.

The refusal is the correct output, not a failure of the audit. An audit whose
every claim is a candidate has told the user nothing they could not have read
themselves.

## Scope, and who chooses it

**A subject whose own name carries a floor word cannot have its probe declared
here, and therefore cannot ship one at all.** This doctrine may not spell those
words -- `test_no_floor_word_appears_in_the_skill_itself` holds that -- and the
shipped-files table below must stay complete. A probe file named after such a
subject cannot satisfy both at once: naming it in the table breaks the floor,
and omitting it breaks the table.

One such subject has already been audited and returned a finding. The finding
stands; the instrument does not ship. Recorded here rather than resolved,
because every obvious remedy costs something real -- renaming a probe hides
which subject it drives, exempting the table stops it being a closed set, and
exempting the floor for filenames is a hole shaped exactly like the one the
floor exists to close. Deferred on purpose, not overlooked: exactly one
subject is affected, the finding is already measured and written, and choosing
an exception under the pressure of a single case is how exceptions get made
that nobody can take back. **The trigger is a second subject whose name carries
a floor word** -- decide it then, with two cases in hand and evidence of which
cost actually bites.

**This is the audit's own defect class, in its own doctrine.** A closed set that
cannot be completely stated is what every `no-closed-roster` finding names, and
here the obstruction is a rule this skill wrote for itself.

A subject larger than one closed surface is not audited in one pass. Propose a
slicing — one closed surface per slice, each nameable in a line — and **ask**,
through the interactive question facility. Never type a question into a reply
and continue as though it had been answered; a question nobody was asked has an
assumed answer, and an assumed answer is exactly what this skill exists to find
in other people's documents.

If the facility is unavailable, carry the assumption **explicitly**, in the
report's own words, as an assumption rather than as a decision.

## The moves

Every move is a way of getting a fact that reading cannot give you. Move by
move, in order; the numbering is the order.

| Move | Ships as | Lock |
| --- | --- | --- |
| 0. Enumerate a closed surface from both sides, and never begin by reviewing a diff | `roster` | `tests/test_skill_audit.py` |
| 1. Build the expected artifact from the documentation alone, then diff it against the producer's output | `structure` | `tests/test_skill_audit.py` |
| 2. Drive the subject as it exists on disk, never only a fixture built from the same document | `roster` | `tests/test_skill_audit.py` |
| 3. Fake every external boundary and assert on what crossed it, never dial it | `doctrine` | `tests/test_skill_audit.py` |
| 4. Read an installed dependency as text; importing a service client authenticates it | `doctrine` | `tests/test_skill_audit.py` |
| 5. Probe live only with consent, read-only, and scope the result to the environment | `doctrine` | `tests/test_skill_audit.py` |
| 6. Invert every lock the audit leans on, and watch it fire | `inversion` | `tests/test_skill_audit.py` |
| 7. Compare per-harness test counts before and after; a count that did not rise is a finding | `doctrine` | `tests/test_skill_audit.py` |
| 8. Drive the whole documented flow in order, against one real shared box, and name the first step that breaks its own declared expectation | `walkthrough` | `tests/test_skill_audit.py` |
| 9. Compare two supplied readings of one prose surface by mechanical diff, and never let the comparison close | `reading-diff` | `tests/test_skill_audit.py` |
| 10. Vary a declared input a result claims to depend on, and ask whether the declared output moves | `sensitivity` | `tests/test_skill_audit.py` |
| 11. Per reported state, whether a mechanical exit exists and whether it is published, and drive it for real if so | `exits` | `tests/test_skill_audit.py` |
| 12. Per declared check, whether its own claim of completeness is backed by a derivation or by something bounded wearing a derivation's clothes | `enumeration-reach` | `tests/test_skill_audit.py` |
| Read every artifact's opening paragraphs against its own frontmatter and its own shipped files | `doctrine` | no lock — irreducibly textual, and carried anyway |

The last row has no code and no lock, and says so. Prose contradicting prose
inside a single file cannot be mechanized, and dropping the row to make the
table tidy would be the same defect this skill exists to find.

Move 7's mechanism — a `counts` subcommand reading `Ran N tests` and `# pass N`
— is **deferred** to the follow-up change `the-manifest-that-proves-containment`
along with `manifest`. Until it lands, move 7 is carried out by running each
harness by hand and reading the figures, and this row names `doctrine` rather
than a subcommand that does not exist.

### Move 0, in detail

Enumerate the closed set from the running code and from the documentation, as
two independent derivations, before forming any opinion about either. Treat
every enumeration produced by reading as a **candidate** until something
executes. Move 0 also compares any unhedged numeral in the subject's prose
against the enumeration that immediately follows it.

A guarded vocabulary is a closed set too, so its **reach** is Move 0's
subject as well, via `roster`'s optional `guardReach` recipe block. For every
member the block's own driven `producer` derives, `identifier_variants`
derives that member's plural, underscore-joined, and case-joined forms --
never a claim about correct English pluralisation, only a probe for shapes a
word-boundary matcher can measurably fail to reach, since `_` is itself a
word character in that pattern language. The guard is then driven for real
with each form, never matched against a recipe-declared pattern compiled
with `re`, which would be a hand-copy of the subject's own source living
beside it, free to drift. A control runs first: the bare guarded member
itself MUST be reached, or the finding is `kind=guard-never-fires` once, not
one `kind=guard-unreachable-variant` per identifier form. A subject exposing
no driveable guard for a declared `guardReach` block is `kind=no-driveable-
guard`, the `no-closed-roster` idiom reused verbatim -- reported, never a
silently empty roster.

The same drive answers a second, narrower question: whether the guard's
verdict is measuring identity or content. Substitute the guarded member with
a neutral token nothing could collide with and drive the guard again; if it
now passes, the guard's verdict moved when the identifier moved and the
content did not, and the result is `identity-measured`. If it still refuses,
the probe could not determine that, and the result is `not-determined` --
`IDENTITY_MEASURED` is a closed two-value roster with no third value ever
meaning "the content is specific," because that would be a reading, not a
measurement. Every such payload also carries the `READING_DIFF_LIMIT`
sentence, regardless of verdict: a rename-insensitive guard proves its own
matcher tests identity, and proves nothing whatever about whether the
content behind it is still specific.

### Move 1, in detail

Construct what the documentation says the producer should emit, from the
documentation alone, and diff it against what the producer actually emits. This
is the only move that catches the document and the producer drifting apart while
each stays internally consistent. It is only sound under the conditions below.

`structure`'s `fromZero` side now drives a real external `claude -p` process
through a `driver` step. The three tests that exercise this for real
(`FrozenPayloadTests.test_structure_payload_carries_frozen`,
`StructureSelfProbeTests.test_the_shipped_recipe_drives_a_real_external_process`
and
`NothingWasRepairedTests.test_a_structure_run_leaves_the_subject_and_its_ground_untouched`)
default to skipped and opt in only with `SKILL_AUDIT_LIVE_DRIVER=1`. Before
any change to `run_box_step`, `BOX_STEP_KINDS`, `DRIVER_ENV_ALLOWLIST`, or the
shipped recipe's `driver` step, run
`SKILL_AUDIT_LIVE_DRIVER=1 .venv/bin/python -m unittest tests.test_skill_audit.FrozenPayloadTests.test_structure_payload_carries_frozen tests.test_skill_audit.StructureSelfProbeTests.test_the_shipped_recipe_drives_a_real_external_process tests.test_skill_audit.NothingWasRepairedTests.test_a_structure_run_leaves_the_subject_and_its_ground_untouched`
so the change is proven against the real driver mechanism, not only against
its default-skipped shadow.

The gate is not a convenience. `subprocess.run`'s own timeout reaches the
agent it started and nothing the agent started in turn: those children are
reparented and keep working long after the driver step has been recorded as
timed out. They work inside `implementations/`, which is also where this
suite's own throwaway boxes live and what several of its assertions compare
before against after. An ungated site therefore does not merely cost time --
it injects a nondeterministic writer into the directory the rest of the suite
is measuring, and the failures land on whichever unrelated test is running
when it writes.

### The constructed child environment

`constructed_child_env` is the one place a driver-kind child environment is
built, shared by `run_box_step`'s `driver` step-kind and
`run_sensitivity_drive`'s producer drive. `PYTHONDONTWRITEBYTECODE=1` is
injected into every such environment **unconditionally** -- never inherited
from the parent process, and never satisfiable by declaring it in a
recipe's `env` list. The name stays out of `DRIVER_ENV_ALLOWLIST` **on
purpose**: a recipe naming it explicitly is refused `Unprobeable`,
deliberately, not an oversight. Widening the allowlist to admit it would
turn the purge into a value a recipe could opt out of, and a same-size
mutation could then execute a cached `.pyc` again -- the exact trap this
paragraph exists to keep shut.

### Move 6, in detail

Invert every lock the audit leans on, and watch it fire, through the
`inversion` subcommand. The mutation sweep is bounded, not exhaustive: a
**guarded fact** is the `(file, line, literal)` triple a named test asserts
on, sourced **only** from the invoking probe recipe's own declared
`mutations` block -- never listed by hand, and never derived from the
subject's own lock roster in v1. Facts the sweep did not reach are named in
`## Unchecked`, never silently dropped.

The observing run each guarded fact declares is driven once, unmutated,
before the first byte is touched: a subject whose observing run is already
red is refused `Unprobeable` `kind=baseline-not-green`, with no file mutated
and no finding emitted -- against an already-red suite, every guarded fact
would report `fires`, having proven nothing.

One subprocess test-run per guarded fact, serial, each restored before the
next. **Hard cap: eight guarded facts per run**, plus this subcommand's own
`--timeout`, applied to each observing run; overflow lands in `##
Unchecked`. A wall-clock budget was considered and rejected: it would make a
report's contents depend on the machine that produced it, so two runs of the
same audit on different machines could disagree about what was checked --
the same class of defect as "green by accident of the machine." A count cap
is deterministic and travels with the report.

Restore discipline, inherited from the table below: `sha256` before, write
the mutation, run, apply the **inverse patch**, re-`sha256`, assert equality.
Never `git checkout --`. A restore that does not reproduce the digest halts
the sweep as `Unprobeable` -- a damaged tree is an inability to look, and the
sweep must not keep mutating. Invert the effect the guard asserts, not the
comparison around it: flipping `==` to `!=` only changes which subset is
excluded and yields a different wrong answer, never the absence of the fact.

A guarded fact whose mutation leaves the suite green is **not** simply an
obsolete guard: condition 2 proves the bytes moved, and nothing proves
behaviour moved along with them. The cause may equally be an **equivalent
mutant** (the bytes changed, the behaviour did not) or a **degenerate
fixture** (the fixture's own correct answer already equals the mutant's
output) -- both measured defects from the source session, not hypothetical.
Every such finding is adjudicated `not adjudicable`, sitting under `##
Not adjudicable` with the rest of that verdict's findings, and its own
remedy is a three-way verdict, never build-or-delete: `- Remedy: delete`
when the guarded fact no longer exists; `- Remedy: update` when the fact
exists but moved, or the test measures it wrongly; `- Remedy: undecided:
<reason>` when the split itself cannot be made, and that reason MUST name
one of `obsolete guard`, `equivalent mutant`, or `degenerate fixture`, or
state that none could be determined -- defaulting to `obsolete guard`
when the cause is undistinguished is the exact overclaim this paragraph
now refuses. **v1 ships no delete-versus-update classifier.** A prior
draft of this doctrine named `check_citations.py`'s `symbols_in`/
`repo_symbols` as the precedent for deciding that split by AST existence-
checking; that tool **does not exist in this repository**, so v1 cannot
reuse it and does not imitate it either. Every v1 not-adjudicable finding
therefore carries `- Remedy: undecided: <reason>` only -- `delete` and
`update` remain in the validator's own accepted vocabulary, for a
human-authored report, but v1's own emitter never produces either until a
later change ships that classifier. **The auditor still never deletes a
test.** It reports, in the three rosters at the top of `## Not adjudicable`,
and the finding still gets its own `## Repair units` row with a
changed-line forecast, so the next change picks it up as a work item.

Every Move-6 finding, whatever its verdict, also carries `- Reachability:
fires: <what this does not prove>` or `- Reachability: silent: <what this
does not prove>`. A red mutation proves the guarded fact's lock **fires**;
it never proves every consumer of that fact was exercised, which needs
Move 0's own enumeration over every field a producer emits, not a single
substitution. Stating reachability rather than coverage is what keeps a
passing inversion sweep from being read as a stronger claim than it is.

### Move 8, in detail

Every earlier move probes one closed surface in isolation. This one drives the
documented flow itself, step by step, against a real shared box, and asks
whether each step's own declared expectation still holds once it actually
runs. A step matching its own expectation is `passed`, whatever its exit code
— a documented refusal is a pass. The first step whose observation
contradicts what it declared is the stall, named by its index; every gate at
or after that index is `unreached`, and the report carries it under
`## Unchecked`, never under clean. A step declaring no expectation at all is
refused before it runs: a gate that asserts nothing is not a gate.

A step that reports success is not a step that produced. `walkthrough` takes
a digest of the shared **box** -- never the subject -- before and after each
driven step, and grades what actually changed against that one step's own
declarations: a step not declared `readOnly` that leaves the box
byte-identical is reported as having produced nothing, whatever it exited; a
step declaring `roots` is measured against them, and a change wholly or
partly outside its declared `roots` is reported as writing into a tree it
does not own; a step declared `readOnly` is exempt outright. The digest
covers the box, not the subject, because every step already runs with its
`cwd` inside the box -- digesting the subject would fire on every step of
every correct flow. Separately, and independently of any one step's own
grading, the subject tree is digested once before the whole flow and once
after: `walkthrough` never writes into the subject at all, so any change
there halts the sweep `Unprobeable kind=step-escaped-the-box` -- an
inability to look, never a finding, the same reach `structure`'s own
from-zero build already had and `walkthrough` did not.

### Move 9, in detail

Every earlier move derives at least one side of a comparison from a real
process or a real table. This one takes both sides as given -- two supplied
readings of one prose surface -- and asks only whether they agree, never
whether either is right. Two readers agreeing proves the prose has **one
reading**, never that it is closed, and `comparison` stays the literal
`not-run` for a surface compared this way, permanently. Four independent
barriers hold this: an AST lock proving the subcommand never calls
`doctrine_side`, `probe_code_side`, or `finish`; a structural lock proving
`closed_seen` is assigned `True` at exactly one site, inside `run_roster`,
fed only by a `doctrine_side` status; the literal `not-run` comparison, held
as a constant rather than a computed value; and a behavioural lock proving a
reading naming more than a real code side never yields an `unregistered`
key at all. A supplied reading may propose a candidate for a later gate; it
may never itself close a comparison.

### Move 10, in detail

Every earlier move asks whether a documented set and a running set agree.
This one asks a different question of a single reported value: was it
computed, or was it typed in? Materialize the subject into a copy -- `##
Frozen` pins the real subject's digest for the whole report, so the real
subject is never touched -- then remove one declared input at a time from
that copy, re-drive the subject's own declared producer, and re-read the
declared results site. A declared value that never moves across every
input it was checked against, up to a bounded cap, is `not adjudicable`:
a fact with no computation traceable to it. The candidate `(output,
input)` pairs are never listed by hand; they come from the subject's own
declared results table, the same `declared` site grammar `structure`
already uses.

An inverted control runs first, exactly as it does before the real
ignorant drive: every declared input is removed **at once**, and the
producer is proven to notice -- either by refusing, or by the declared
values changing from what the freshly-copied box already held before
anything ran. Without that proof, the sweep stalls rather than accusing a
producer it never reached: it cannot tell "never read the box" from
"every value is typed in", and guessing would make those two
indistinguishable forever. Only once the control passes does a per-input
`unchanged` cell mean anything.

The baseline drive, with every declared input present, must then exit
`0`. A producer that refuses even with its box intact passes the control
and fills every cell with `producer-refused`, so the sweep stalls
(`kind=sensitivity-baseline-refused`) rather than report a matrix measured
against values the producer never computed.

**Hard cap: four declared inputs varied per run**, sorted-first-four for
determinism -- overflow lands in `## Unchecked`, naming the total. A count
cap, never a wall-clock budget, for the same reason Move 6's own cap is
one: a time budget would make a report's contents depend on the machine
that produced it. Restore discipline is inherited from Move 6 verbatim:
`sha256` before, remove, drive, write the exact bytes back, `sha256`
again, assert equality -- never `git checkout --`, which has no target
here at all, since the copy is not tracked by git.

### Move 11, in detail

The ten earlier moves all ask whether the subject is correct. None asks
whether the subject lets its operator out. Measured on a sibling skill: of
51 reported keys naming a state a human must act on, eight had a mechanical
exit and none published it -- getting out of one required reading the
skill's own documentation, finding a payload's shape by grepping its test
suite, and rebuilding an input by hand.

Per state a recipe declares: a state the recipe or subject marks a human
judgement is `judgement`, reported and never a finding -- publishing a
command for a judgement would be worse than the silence. A state with no
such declaration is searched, through the recipe's own declared `site` and
`extract`, for a published act; none found is `unstated`, a finding,
reported with the driveable range that was searched. The audit does not
guess at an unpublished exit's identity: locating one would mean searching
the subject's surface for an act that would clear a named state, and any
name-similarity heuristic is a guess this skill refuses everywhere else.

A found act passes an admission gate before any process starts: split into
a list of strings, refused if that split is empty; refused if it carries a
shell metacharacter (`;`, `|`, `&`, `$`, `>`, `<`, a backtick, or a
newline), because this tool never sets `shell=True` and passing one through
literally would misreport a shell command as broken; and its `argv[0]`
resolved under `--subject`, under `--repo-root`, or named in the recipe's
own declared interpreter allowlist -- the `DRIVER_ENV_ALLOWLIST` precedent,
applied to an operator-authored act. Anything else is
`published-but-unparseable`.

An admitted act then runs for real, inside `materialize_subject_copy`'s own
copy so an exit that repairs repairs only that copy, through
`constructed_child_env` for its environment and this subcommand's own
`--timeout`. **`published-and-ran` deliberately does not read the act's own
exit code** -- the requirement is that the act can be reached, not that it
succeeds; an act that runs and refuses has been published and can be run,
and judging whether its refusal was correct is a different question this
probe does not ask. A missing binary is `published-but-not-executable`; a
hang is `published-but-timed-out`.

The real subject is digested before and after the whole sweep, exactly like
every other box-owning move: a change reaching it is
`Unprobeable kind=exit-escaped-the-box`, the sweep halts, and `erase_box`
still runs in a `finally`.

### Move 12, in detail

Move 0 enumerates a closed surface from both sides and is correct to do so.
This asks a narrower question of one side alone: for a check the subject
declares complete over a set, is its own iteration source *derived* from
the subject, or *bounded* -- a literal collection, a single module's
namespace, or a subset filtered before the assertion runs. Measured, four
times in one session: an enumerator of refusal codes walking one
function-name prefix inside one file, invisible to 42 codes raised
elsewhere; a check documented as "enumerated from the signature" that
skipped any function without a particular parameter; a helper collecting
"the notebooks the steps run" by matching any string literal with that
suffix, so a mutation replacing the call while leaving the literal survived
it; and a check hand-listing four names that lagged reality by two.

`probe_code_side`'s whole argument is that no source of the subject is
parsed, so the subject may be written in any language. Move 12 does the
opposite on purpose, on a **check's own source**, never the subject's, and
so cannot live inside `roster` without forking a second code-side
derivation there -- `ast` is the one new stdlib import this move admits, and
`enumeration-reach` is its own subcommand for exactly that reason. A
check's own name and docstring are its stated claim, read and reported
verbatim; the tool never adjudicates whether that claim is universal, only
what the check's own iteration source actually is. A check whose site does
not end `.py`, or whose source does not parse as Python, is
`unreachable-for-this-language`, never guessed at.

**A check that says it derives and enumerates by hand is worse than no
check**, because nobody looks at it again -- the whole finding, and the
reason a derived enumeration is reported plainly, never escalated: it is
not a finding, it is the check working as documented.

## The stages

A differential audit against a second subject runs in six stages, cheapest
first. Each is a row in a table, never a numbered heading -- the same reason
move numbering lives in the moves table rather than in headings of its own.
Stage 2 is not itself differential: it demands the subject be driven from
ignorance whenever anything is reachable to drive, and every report --
differential or not -- carries all six stage rows.

| Stage | Models | Demands |
| --- | --- | --- |
| 0. Freeze the subject | 0 | `frozen` |
| 1. Decide by tool | 0 | `undecidable` |
| 2. Drive from ignorance | 1 | `user-drive` |
| 3. Two blind readings, over that list only | 2 | `reading-diff` |
| 4. Differential drive, one box with the skill and one without | 2 | `drives` |
| 5. Partition the two transcripts | 1 | `found-by` |

Six model runs, total, and only if every stage after the first three
actually runs -- one for stage 2's drive from ignorance, two for stage 3's
blind readings, two for stage 4's differential drive, one for stage 5's
partition -- stated here, before any of them is launched.

Each `Demands` cell holds a `REPORT_SHAPE` key, not prose, held to "The shape
of a report" table below in both directions by
`ReportSchemaSelfDescriptionTests`. A stage is conditional exactly because
this table names it: `## Stage outcomes` records it `ran` or
`skipped: <reason>`, mirroring `## Move outcomes` exactly, and only a `ran`
row demands the artifact its own `Demands` cell names -- a `skipped` row
demands nothing. A zero-model audit, stages 0 and 1 `ran` and stages 2
through 5 all `skipped`, is a valid report on its own terms, never a partial
one -- **except stage 2**, whose skip is accepted under exactly one reason,
below.

One cross-section rule ties `## Undecidable` back to `## Move outcomes`: an
entry claiming `- Rung: probe` must name a move whose own row there reads
`ran`. Declaring a probe was the answer and then skipping the move it names
is refused, structurally.

### `### Demanded, not scaffolded`: an operator's declaration, never a proof

Stage 2 drives the subject from ignorance and measures that the drive ran.
It does not measure whether everything the subject **reads** from its own
target during that drive is **demanded** when the target is built from
nothing -- a from-zero scaffold silently missing a declaration the subject
reads is invisible to every other move. `## User drive`'s
`### Demanded, not scaffolded` subsection states this by hand: per
declaration the subject reads from its target, the declaration itself,
where it belongs, and the consequence of its absence. `(none)` is the
explicit way to say there was nothing to demand; a bare heading is refused
the same as an absent one, exactly like `### Declared, not proven` already
is.

This is the structural half only, and stays one on purpose. The stronger,
derived form -- scaffold into an empty box, drive the subject against that
box, and collect what it refuses for -- is out of reach for the same reason
`structure`'s own from-zero driver already states in this file:
`subprocess.run()` is this tool's only authority over an external driver,
and it holds none over what happens on either side of that call. That
stronger form is recorded here as **the scaffolded-refusal drive**, deferred
rather than built, and rather than smuggled into a recipe that cannot
express it.

### An artefact is judged by what it shows, and by what nobody named

Only a real drive produces artefacts, so this attaches to stage 2's own
from-zero build, not to a static check. `structure`'s optional
`artefactKinds` recipe block names a kind by its `glob`; per declared
member of that kind, the payload reports `produced`, `produced-but-empty`
(a file the build wrote carrying zero bytes -- existence is not the
measurement), `absent` (the build never wrote it at all), `carries-no-match`
(the kind declares a `contentPattern` and the produced content does not
match it), or `content-not-declared` (no pattern is declared, so the
content is never assumed full). Separately, and sharing the same
`tree_digest(from_zero_root, exclude)` enumeration: every on-disk member of
that kind the declared roster never names at all, reported as `unnamed`
whether or not the list is empty -- a flow validates only what it names, so
an artefact nobody named is otherwise never checked at all, and the report
would still read complete.

### The binding ruling: an audit never reports without driving

Stage 2 accepts exactly one skip reason:

    - Stage: 2: skipped: no reachable surface (stage 1)

accepted only when stage 1's row reads `ran` and `## Undecidable` is
**non-empty** with every entry's `- Kind:` reading `no-closed-roster`. An
empty `## Undecidable` section is not the same claim as a section full of
`no-closed-roster` entries: a cleanly-decided surface never enters that
section at all, so its presence there is exactly what distinguishes "nothing
was reachable" from "nobody looked." Any other stage 2 skip reason --
including a genuinely empty `## Undecidable` -- is rejected as
`driver-required`: an audit never reports on a subject without driving it,
and the zero-model path is never a caller's shortcut to assert. "Optional"
applies only to stages 3 through 5, after a successful drive, never to
stage 2 itself.

A stage-3/4/5 row MAY read `skipped: offered, declined` -- available, the
operator chose not to take it -- distinguishable at a glance from any other
`skipped: <reason>` text, which always means "could not run." That text is
legal only once stage 2 itself reads `ran` and `## User drive`'s own
`- Outcome:` reads `agree`: equivalence reached is what makes the question
worth asking in the first place. Without that agreement, no question was
asked, and `check-report` rejects the `offered, declined` text wherever it
appears on 3 through 5 -- stage 2's own row may never carry it at all.

Stages 3 through 5 carry no lock over the one fact that would matter most:
whether the two readers, or the two drives, were actually blind, isolated,
and out of contact with each other. `check-report` can enforce that an
artifact exists and has the shape this table names. It cannot enforce that
the process which produced it never let the two sides talk, because this
tool only ever calls `subprocess.run()` and holds no authority over what
happens on either side of that call. A stage row in this table, like the
moves table's own textual row, is an operator's declaration -- never a
proof.

## The from-zero comparison and its soundness conditions

A from-zero comparison that quietly consults the producer proves nothing, and
proves it convincingly. All of these hold or the comparison's result is not read.

| Condition | What it forbids |
| --- | --- |
| The documented side never references the producer | Not a call, not an import, not a borrowed constant, and not to decide which elements to build. Enforced by parsing the derivation function's syntax tree |
| The comparison's domain is declared and closed | An open domain makes the diff noise, and noise gets exempted until the comparison means nothing |
| Both directions report as sets, never as a boolean | `unregistered`, `phantom` and `duplicated` are different defects with different remedies |
| The comparison is proven reachable-red both ways | Adding to the code side fires `unregistered`; deleting a documented row fires `phantom` |
| The documented side comes from a parseable table, never from prose | The reader who writes the from-zero side has just read the artifact and will reproduce it unconsciously |
| The from-zero side never references the subject | Not the `{subject}` token, not a hand-typed absolute or repo-relative path to it. The mirror of the first row: a from-zero build that reads from the subject is not a build, it is a copy wearing one |
| A `driver` step's brief names the problem, never the shape | Never a literal file or directory the subject's own declared file table lists (or any entry's own basename), derived from that table rather than from a list held here or in the recipe. Naming the shape would dictate the driver's output and copy the producer's structure instead of letting the driver build its own; the comparison's resolution is bounded by the brief, and the brief is the operator's |

Where the subject has no such table, **"there is no closed roster here" is the
finding**, emitted as a first-class result with the range that was searched. It
is not an error, not an exception, and not a clean verdict.

A documented table counts as a roster site only if the recipe declares its scope
and quotes its heading, and the quoted heading is then checked against disk. A
table headed `## Other engine operations` is a complement set; diffing it
against the full runtime roster would emit a screenful of confident nonsense on
the auditor's very first subject.

## How the moves fail

Each of these has already cost a phase in this repository. Each is a
requirement, not a caveat.

| Failure | Requirement |
| --- | --- |
| A lock passes off its own fixture's name | Assert the needle is absent from the fixture's name and path **first**, before the assertion that looks for it |
| A fixture cannot reach the guarded branch | Establish reachability; an assertion over a branch the fixture never enters is unfalsifiable, and it passes |
| A wholesale double stands in for a process | Drive the subject as a subprocess. A double replacing a function cannot hold a claim about the process it would have run |
| A green suite is offered as evidence | Greenness is never evidence. Evidence is a named execution with a named observation |
| Containment is proven by `git status` | `git status --porcelain` over an ignored directory is empty by construction. Prove it by a before/after content manifest |
| A live request's success is claimed as a receipt | It proves the environment answered. It proves nothing about the subject's code |
| A new name is proven free by the default search | The default search honours `.gitignore`. Search with it disabled and hidden files included, or the negative is worthless |
| An inversion is undone with `git checkout --` | Restore by inverse patch and confirm by content comparison; checkout restores from the index and silently discards unrelated work |
| A remote-job rung is claimed from a full run, or from nothing at all | Drive it through that job's own `run.smoke` block (module / function / kwargs / requiredEvidence) in `run-config.json`; a job declaring none of `smoke_module`/`smoke_function` is itself a finding, service-blind, with no epoch or pilot-scale dial: a shard measured at pilot scale is not a cheaper shard, it is a different experiment |
| A "did not move" report accuses a producer never proven to read its box | Fire an inverted control first: remove every declared input at once and demand the producer notice, by refusal or by its declared values changing. A per-input `unchanged` cell means nothing until the control has passed |
| A same-size mutation reads live because it ran a cached `.pyc` | Inject `PYTHONDONTWRITEBYTECODE=1` unconditionally into every constructed child environment, at every site that builds one, through one shared helper -- never dependent on the parent process's own environment, and never satisfiable by a recipe's own declaration |

## The evidence ladder

When both halves disagree, the consumer decides, and only execution establishes
what the consumer does. Highest first:

| Rank | Evidence |
| --- | --- |
| Strongest | The installed consumer, measured by running it |
| | Two independent consumers agreeing under constraints neither can be changed for |
| | The live subject on disk, driven as a process |
| | Fixtures the audit built |
| Weakest | Prose, in either artifact |

Prose is last because both sides are claims until something executes. A
statement in any document describing what a consumer does is **never** evidence
of what that consumer does — that rule was proven twice in this repository's
own history, and it is stated here so it is not rediscovered a third time.

## Adjudication

Every finding carries exactly one adjudication, and there is no default.

| Adjudication | Means | Remedy |
| --- | --- | --- |
| `doctrine wrong` | The documentation states something the running code does not do | Correct the document |
| `artefact wrong` | The running code does something its own documentation forbids or omits | Correct the code |
| `not adjudicable` | Enumeration found no consumer at all, or Move 6 found a guarded fact whose mutation left the suite green | See below |

### Not adjudicable

`not adjudicable` is not a softer verdict; it is a different question. The
question is not which half is wrong but that **this half has no other half** — a
value declared and enumerated with nothing anywhere reading it or branching on
it. Its remedy is build-or-delete, a user decision with real cost, and that is
the structural reason report-then-fix is the correct ordering: an auditor that
repaired what it found would have to guess this one.

A guarded fact whose mutation leaves the suite green is a distinct occasion
for the same verdict, never the no-consumer case above: not the absence of a
consumer, but a lock that no longer discriminates. Move 6's own remedy names
which job follows -- delete, update, or undecided with a stated reason --
never build-or-delete.

These findings get their **own report section**, distinct from the ranked
findings, so a reader can see at a glance which findings are defects and which
are open questions about intent.

Move 10 emits `not adjudicable` only, never `artefact wrong`: distinguishing
"documented dependency, no path" from "no computation at all" would need a
hand-written roster of documented dependencies -- the exact second roster
this skill refuses everywhere else. A finding's own text states the
observation and the tested range, never a motive: an output may legitimately
be insensitive to one input over a narrower range than the one checked.

Do not apply the rule "every reported fact must be branched on". It is false by
construction: facts are deliberately reported without gating anything, and the
bar for such a value is documentation, not consumption. A value that is
computed, documented, and deliberately never branched on is **not** a finding.

## The shape of a report

`check-report` enforces this. A shape enforced only by prose is a
hand-maintained roster, which is the class this skill exists to find.

The current report shape is `skill-audit-report/1`. A report predating this
shape (no `## Report integrity` section at all) is not judged against it —
see `report-integrity` below — and this sentence is the one place the
version is stated; `REPORT_SCHEMA_VERSION` is held to it by a lock, never
restated as a second literal.

That version is **not** a compatibility escape, and this is the one place
that says so. Every item in the table below is judged against every report
carrying `## Report integrity`, including a report signed before that item
existed; the only unjudged report is one with no `## Report integrity`
section at all. So `remedy`, which arrived after the first reports were
signed, retroactively invalidates a previously-valid report whose `## Not
adjudicable` carries a `- Move: 6` finding -- `check-report` exits `1`
naming that finding, and no version bump exempts it. The remedy is to re-run
the audit and issue a new report, never to hand-edit the old one into
agreement: an audit report is a record of what was true when it was written,
and `- Self-digest:` exists to make editing one visible.

| Item | Required content | Rejected when |
| --- | --- | --- |
| `report-integrity` | `## Report integrity`, the report's first `## ` section, carrying `- Schema: skill-audit-report/N` and `- Self-digest:` — a canonical-content digest over the report's own text with that one line excluded, reusing the existing `sha256:` spelling and canonical-string-then-hash idiom `frozen_digest` already uses | Both fields absent together means the report predates this shape and is not judged (a separate outcome, never `1`); exactly one of the two present is `tampered`, never read as predating; a present digest that disagrees with recomputation is `tampered`; the section is present but is not the report's first `## ` heading |
| `supersedes` | Optional `- Supersedes: sha256:<hex>` inside `## Report integrity`, naming the OTHER report's own self-digest, never this report's own — checked with `check-report --supersedes-report <path>`, which recomputes the named companion's self-digest and compares `## Frozen`'s `- Subject:` values, never `- Digest:` (a genuine re-validation is expected to change the subject digest) | The value is not shaped `sha256:<hex>`; the value equals this report's own `- Self-digest:` (a report cannot supersede itself); the flag is supplied but the report carries no `- Supersedes:` line; the named companion is unreadable, predates, or postdates the schema, or either side's `- Subject:` is absent; the recomputed companion digest disagrees with the declared value; the two `- Subject:` values disagree |
| `ranked-findings` | Findings, ordered, each naming **both halves** at `file:line` | A finding cites a single `file:line`; that is a candidate, not a finding |
| `move-number` | The move that found each finding | A finding names no move |
| `move-outcomes` | `## Move outcomes`, one row per move named in the moves table above, each `ran` or `skipped: <reason>` | A move has no row, or a `skipped` row carries no reason |
| `evidence-marker` | Per finding, `CONFIRMED by execution` or `read-only` | A finding carries neither; there is no default, and a missing marker is never read as confirmed |
| `found-by` | Per finding, `both`, `one`, or `not-compared` | A finding carries none of the three; there is no default, and a missing marker is never read as `one` |
| `adjudication` | Per finding, one of the adjudications above | A finding carries none, or carries a value outside the table |
| `clean-section` | `## Clean, stated as results`, with the enumeration that supports each entry | An entry's only support is that a suite passed |
| `unchecked-section` | `## Unchecked`, naming what was not enumerated | A surface that was never enumerated is absent, or is reported as clean |
| `falsifier` | The observation that would overturn this report | Absent |
| `changed-line-forecast` | The size of the fix that would follow, in changed lines | Absent |
| `frozen` | `## Frozen`, naming the digest every finding's own `- Digest:` must agree with. The section also carries `- Subject:` and `- Exclude:`, neither demanded by this item -- but `- Subject:` is load-bearing beyond its own report: `supersedes` above compares it across two reports, so a report omitting it can neither supersede nor be superseded, and one whose `- Subject:` drifts silently stops being comparable to its own predecessors | A report carries no `## Frozen`, or a finding's digest disagrees with it |
| `repair-units` | `## Repair units`, a table naming each unit's findings and its own changed-line forecast, a grouping distinct from move or adjudication | A finding belongs to no unit or to more than one, or a forecast cell is not an integer |
| `disputed-severity` | `## Disputed severity`, bare heading; when non-empty, exactly two `- Position:` lines per dispute, each citing `file:line`, recorded verbatim, with no ranking | The heading is absent, or a dispute's positions are unpaired, or a position carries no citation |
| `stage-outcomes` | `## Stage outcomes`, one row per stage named in the stages table above, each `ran` or `skipped: <reason>` | A stage has no row, or a `skipped` row carries no reason |
| `undecidable` | `## Undecidable`, bare heading, demanded when stage 1 is `ran`; when non-empty, each entry names `- Kind:`, `- Rung:` (`probe` or `readers`), and, when the rung is `probe`, `- Probe: <move>` | The heading is absent while stage 1's row reads `ran`, or a `probe` rung names a move whose own `## Move outcomes` row is not `ran` |
| `user-drive` | `## User drive`, demanded when stage 2 is `ran`; the driver's `argv`, `argv[0]`'s resolved path, its `cwd`, the env names passed, any declared-but-absent env name (`envMissing`), the ignorance control gate's outcome, the box digest before and after -- `run_structure`'s own `ignorance` block, transcribed rather than narrated -- a `- Digest:` line agreeing with `## Frozen`'s, a non-empty `### Declared, not proven` subsection stating what the drive did not prove: training-data exposure, contact between drives, "genuinely ignorant" versus "was not shown the file", and that the comparison's resolution is bounded by the brief the operator wrote; and a non-empty `### Demanded, not scaffolded` subsection, per declaration the subject read from its target during the drive, naming the declaration, where it belongs, and the consequence of its absence -- `(none)` is the explicit way to say there was nothing to demand | Absent while stage 2's row reads `ran`; the `- Digest:` line is absent or disagrees with `## Frozen`; `### Declared, not proven` is absent or carries nothing, because a drive claiming to have proven everything has misread what it did; or `### Demanded, not scaffolded` is absent or carries nothing, left blank rather than stated `(none)` |
| `reading-diff` | `## Reading diff`, demanded when stage 3 is `ran` | Absent while stage 3's row reads `ran` |
| `drives` | `## Drives`, demanded when stage 4 is `ran`; no finding may attribute itself to the skill-less drive while naming the subject as its own target | Absent while stage 4's row reads `ran`, or a finding commits that category error |
| `not-adjudicable` | `## Not adjudicable`, bare heading; when non-empty, each entry names the absent half, its `- Evidence:`, and the `## Repair units` unit it belongs to; when at least one entry carries `- Move: 6`, the section opens with `- Delete:`, `- Update:`, `- Undecided:`, naming each in-scope finding by label, `(none)` for an empty bucket -- the same conditionally-required idiom `NO_CONFIRMED_DECLARATION` already uses for a line demanded only when a condition holds | The heading is absent, or a finding whose `- Adjudication:` reads `not adjudicable` sits under `## Ranked findings` instead; the three rosters are missing while a Move-6 not-adjudicable finding exists, present with no such finding, or a label is omitted, duplicated, or listed under the wrong bucket |
| `remedy` | Per finding with `- Move: 6` and `- Adjudication: not adjudicable`, `- Remedy:` one of `delete`, `update`, or `undecided: <reason>`, where an `undecided` reason names one of `obsolete guard`, `equivalent mutant`, `degenerate fixture`, or states `none determined` | The field is absent in that exact scope; carries a value outside the vocabulary; a bare `undecided` with no reason; an `undecided` reason naming none of the four; or is present on any finding outside that exact scope |
| `reachability` | Per finding with `- Move: 6`, `- Reachability: fires: <what this does not prove>` or `- Reachability: silent: <what this does not prove>` -- proves the guarded fact's lock fires (or stayed silent), never that every consumer of the fact was exercised | The field is absent on a Move-6 finding; carries a value outside `fires`/`silent`; or is present on any finding outside that exact scope |
| `computed-value-provenance` | `## Computed-value provenance`, bare heading, unconditional -- like `## Not adjudicable` and `## Disputed severity`, demanded whether or not Move 10 ran; when Move 10 ran, transcribes `sensitivity`'s own emitted payload: the producer, the control outcome, the inputs varied and the total declared, the range swept, and the full matrix -- published even when no cell crosses the finding threshold | The heading is absent |

Every `check-report` run additionally reports `"supersession"`, a closed
three-value roster: `not-claimed` when the report carries no `- Supersedes:`
line, `unverified` when a claim is present but has not been checked against a
named companion (including a claim that is itself malformed or
self-referential), or `verified` once `--supersedes-report <path>` recomputes
the named companion's own self-digest and it agrees with the declared value,
and the two reports' `- Subject:` values also agree. Never a boolean:
collapsing "nobody claimed a supersession" into "a claim exists that nobody
checked" is the exact defect this field exists to remove — an unsuperseded
report announces itself, unprompted, on every single run.

A report in which **no** finding is marked `CONFIRMED by execution` must say so
in its **first line**. A clean surface still gets the full report shape,
including a populated `## Clean, stated as results`: an empty clean section and
a surface nobody looked at must never look the same. `- Found by:` is the
independence axis and travels alongside `- Evidence:`'s obtained axis on every
finding; `## Disputed severity` demands nothing of an undisputed report, and
carries no vocabulary of its own beyond that one heading.

## The subcommands

| Subcommand | Derives | Emits |
| --- | --- | --- |
| `roster` | Code side by driving the subject as a process; documented side by parsing a table; a guarded vocabulary's reach and identity-versus-content, optionally, by driving its own declared guard | `code`, `doctrine`, `unregistered`, `phantom`, `duplicated`, `numeralMismatch`, `notes`, `guardReach` |
| `check-report` | The report shape above, from a report file | `violations` |
| `structure` | Declared side by parsing a structure table; on-disk side by walking `--subject`; from-zero side by walking a recipe-built scaffold inside an empty box; per optional declared `artefactKind`, what the from-zero build produced and which on-disk members its declared roster never names | `sides`, `outcome`, `onlyIn`, `missingFrom`, `notes`, `containment`, `artefacts` |
| `walkthrough` | An ordered recipe of steps, each run for real against one shared box, each held to its own declared expectation | `steps`, `stall`, `unreached`, `containment` |
| `reading-diff` | Two supplied readings of one prose surface, given directly rather than derived | `agreement`, `shared`, `onlyIn`, `comparison`, `candidates`, `limit`, `frozen` |
| `sensitivity` | A copy of the subject, a producer driven once per varied declared input, and the declared results site re-read after each drive | `control`, `matrix`, `notAdjudicable`, `inputsVaried`, `inputsUnchecked`, `inputsTotal`, `notes`, `containment` |
| `inversion` | The real subject in place, one guarded fact substituted at a time from the recipe's own declared `mutations` block, its declared observing run driven before and after | `baseline`, `matrix`, `factsDriven`, `factsUnchecked`, `factsTotal`, `notAdjudicable`, `observed`, `frozen`, `notes` |
| `exits` | Per state a recipe declares, a human-judgement declaration, a published act extracted from the subject's own text, or neither; an admitted act driven for real inside a copy | `exits`, `searched`, `frozen` |
| `enumeration-reach` | Per declared check, its own stated claim and its own iteration source, classified from its syntax tree | `checks`, `bounded` |

`roster` exits `0` for **any** verdict, findings included, and `2` when the
probe could not be driven or the extraction matched nothing. Inability to look
never shares an exit code with absence of findings. An extraction that matches
nothing **raises**; returning an empty set would make every documented row a
phantom finding, which is a broken probe wearing a result's clothes.

`check-report` exits `0` for a valid report, `1` for an invalid one, and `2`
when the report cannot be read.

`structure` exits `0` for **any** verdict — agreement, a two-side outcome, or
a three-way divergence — and `2` only when a side cannot be derived, when its
from-zero box is not empty and so cannot be adopted, or when the from-zero
build wrote outside its own box. None of those three is a finding; each is an
inability to look.

`walkthrough` exits `0` for **any** verdict, a stall included, a step that
produced nothing included, and a step that wrote outside its declared
`roots` included — none of those three is an inability to look. It exits `2`
only when the flow itself could not be entered: a step declaring no
expectation at all, its shared box already occupied, the very first step's
own command missing, or a driven step that changed the **subject** rather
than its own box (`kind=step-escaped-the-box`).

`reading-diff` exits `0` for **either** verdict — agreement or divergence —
and `2` only when it could not look: something other than exactly two
`--reading` flags, a reading file that cannot be read, or a reading whose
`members` list is missing or empty. It never calls `doctrine_side`,
`probe_code_side`, or `finish`, and `comparison` is always `not-run` for the
surface it names.

`sensitivity` exits `0` for **any** verdict, a `not adjudicable` finding
included, and for the degenerate "this subject declares no computed values"
result. It exits `2` only when it could not look: an occupied box, a control
that never proved the producer reads its copy, a restore that did not
reproduce its pre-variation bytes, or a drive that wrote outside its own box.
None of those four is a finding; each is an inability to look.

`inversion` exits `0` for **any** verdict, a not-adjudicable finding
included, and `2` only for an inability to look: no `mutations` block, an
absent or ambiguous guarded fact, a mutation that only flips a comparison
operator, a write that did not change the file's bytes, an observing run
that was not green before the first mutation, a restore that did not
reproduce its pre-mutation bytes, or a drive that wrote outside its
declared file. None of those seven is a finding; each is an inability to
look.

`exits` exits `0` for **any** state's outcome -- `judgement`, `unstated`,
and all five of `published-and-ran`, `published-but-not-executable`,
`published-but-unparseable`, and `published-but-timed-out` -- and `2` only
for an inability to look: no `states` block, its box already occupied, or a
published act reaching the real subject (`kind=exit-escaped-the-box`). None
of `unstated` or any admission-gate outcome is an inability to look; each is
a reported fact about the state.

`enumeration-reach` exits `0` for **any** classification, including
`unreachable-for-this-language`, and `2` only for an inability to look: no
`checks` block, a check naming no site, or a named check not found in its
own site. Nothing here mutates the subject; there is no box, no copy, and
no escape gate, because nothing here writes at all.

## The shipped files

This skill's own `structure` recipe (`references/probes/skill-audit.structure.json`)
points its declared side at this table. Rows exist because a file was added
on disk, never the reverse: a file is deleted first, and its row follows in
the same change.

| Path | Holds |
| --- | --- |
| `SKILL.md` | this doctrine |
| `scripts/audit_cli.py` | the CLI implementing every move that ships as code |
| `references/usage.md` | one worked invocation per subcommand |
| `references/example-report.md` | a report `check-report` accepts |
| `references/probes/skill-audit.subcommands.json` | the self-probe recipe for `roster` |
| `references/probes/skill-audit.structure.json` | the self-probe recipe for `structure` |
| `references/probes/skill-audit.first-run.json` | the self-probe recipe for `walkthrough` |
| `references/probes/proposal-deliberation.accepted-operations.json` | the first subject's `roster` recipe |
| `references/probes/skill-audit.reading-a.json` | the first supplied reading of the worked `reading-diff` invocation |
| `references/probes/skill-audit.reading-b.json` | the second supplied reading of the worked `reading-diff` invocation |
| `references/probes/skill-audit.sensitivity.json` | the self-probe recipe for `sensitivity` |
| `references/probes/skill-audit.self-guarded-facts.json` | the self-probe recipe for `inversion` |
| `references/probes/skill-audit.exits.json` | the self-probe recipe for `exits` |
| `references/probes/skill-audit.enumeration-reach.json` | the self-probe recipe for `enumeration-reach`, pointed at two of this file's own suite's checks |
| `references/probes/remote-execution.accepted-operations.json` | `remote-execution`'s top-level `roster` recipe — pre-existing gap, committed without this row |
| `references/probes/remote-execution.smoke-subcommands.json` | `remote-execution`'s nested `smoke record` `roster` recipe |
| `references/probes/proposal-implementation.accepted-operations.json` | `proposal-implementation`'s `roster` recipe — same finding, over 2045 lines |
| `references/probes/experimental-deliberation.accepted-operations.json` | `experimental-deliberation`'s `roster` recipe — `proposal-deliberation`'s sibling engine, previously unaudited |
| `references/probes/experimental-implementation.accepted-operations.json` | `experimental-implementation`'s `roster` recipe — `proposal-implementation`'s sibling engine, previously unaudited |
| `references/probes/kaggle-accounts.accepted-operations.json` | `kaggle-accounts`'s `roster` recipe — handles live credentials, previously unaudited |
| `references/probes/paper-writing.accepted-operations.json` | `paper-writing`'s `roster` recipe — largest, newest skill in the forge, previously unaudited |
| `references/probes/paper-ingestion.accepted-operations.json` | `paper-ingestion`'s `roster` recipe, over its flag surface rather than a subcommand (the script takes no subcommand) — previously unaudited |

`references/probes/remote-execution.accepted-operations.json` shipped one commit
before this pair of rows was added, itself undeclared here the whole time —
this table's own `structure` probe would have caught that gap the moment
anyone ran it. It is the same defect class this skill exists to catch,
committed while fixing an instance of it elsewhere in this same file: a rule
enforced at operator cadence, not on every commit, so a gap between "a file
landed" and "its row landed" can outlive one commit undetected.

## Decision Gates

| Situation | Action |
| --- | --- |
| No shell | Refuse; name `Bash`; emit no report, no finding, no candidate |
| Subject spans more than one closed surface | Propose a slicing and ask before running |
| The interactive question facility is unavailable | Carry the assumption explicitly in the report, as an assumption |
| The subject's documentation states the set only in prose | Emit `no-closed-roster` with the searched range; do not raise, do not report clean |
| The subject exposes neither a refusal message nor a parser | Emit `no derivation available for this surface`; do not pass silently |
| The extraction matched nothing | Exit `2`. Never an empty code side |
| A recipe claims a table's scope | Check the quoted heading against disk before honouring the claim |
| A set is restated by hand in more than one place | Report every restatement under `duplicated`, even when they all agree |
| A recipe's `restatementSearch` declares fewer paths than `duplicated` needs to fire | Emit `restatement-search-cannot-fire`; a search that cannot reach two matching sites must say so, not report an empty `duplicated` indistinguishable from a search that ran and found nothing |
| A finding's only evidence is prose on both sides | Mark it `read-only`, report it as a candidate, declare neither side wrong |
| Enumeration found no consumer at all | Mark it `not adjudicable`; put it in its own section; name build-or-delete |
| A finding's remedy is a single-line deletion | Report it. Make no edit |
| The report is written | Hand off. Do not proceed to repair |
| A new name is needed | Search with `.gitignore` disabled and hidden files included, before writing it |
| A lock passed on its first run | Invert it, watch it fire, restore by inverse patch, confirm by content comparison |
| A throwaway directory is needed | Put it under `implementations/_<name>` and remove it; never the system temporary directory |
| A from-zero box already holds files | Exit `2` naming the path; never adopt a non-empty box |
| Any of `structure`'s three sides normalises to zero members | Exit `2`; never hand an empty set to the comparison |
| A `structure` recipe step names an unknown `{token}` | Exit `2`; only `{repoRoot}`, `{subject}`, and `{box}` interpolate |
| A from-zero build changes the subject | Exit `2` as `build-escaped-the-box`; never reported as a finding |
| A declared cell's shape cannot be produced by a walk | Set it aside as `shape-not-walkable`; never expand it against the disk |
| A `walkthrough` step declares no expectation | Exit `2`; a gate that asserts nothing is not a gate |
| A `walkthrough` step's argv[0] is missing at index 0 | Exit `2`; the flow was never entered |
| A `walkthrough` step's argv[0] is missing after index 0 | Report it as the stall; a documented command that is not there is a fact about the flow |
| A `walkthrough` step matches its own `expect` | Report it `passed`, whatever its exit code |
| A gate is reached after a `walkthrough` stall | Report it `unreached`, under `## Unchecked`, never as clean |
| A `walkthrough` step declares `"reset": true` | Empty the shared box before running that step |
| A note's kind is absent from `ESCALATION_BUCKETS` | Fail the totality lock; every kind must classify into exactly one bucket |
| An escalatable note's recipe declares `probe: "refusal"` | Rung `probe`; propose the noted candidates as `walkthrough` gates before any reader is invoked |
| An escalatable note has no such recipe, and no readers are available | Rung `readers`; the surface stays in `## Undecidable`, honestly, never silently |
| A recipe declares `candidateGates` | Generate an inverted control gate first, then one gate per candidate; never restate the refusal pattern by hand |
| The control gate does not observe its own declared refusal | Every candidate becomes `unreached`; no candidate may be reported accepted against a channel not proven capable of refusing |
| A `candidateGates.argv` names an unknown `{token}` | Exit `2`; only `{repoRoot}`, `{subject}`, `{box}`, and `{candidate}` interpolate, and `{candidate}` only inside this block |
| A consequence kind is produced by an already-escalatable surface | Never escalate it a second time as an independent entry |
| `reading-diff` is invoked with other than exactly two `--reading` flags | Exit `2`; the comparison needs exactly two supplied readings |
| Two supplied readings agree | Report `agreement: "single-reading"`; `comparison` stays `not-run`, never `closed` |
| A stage's `## Stage outcomes` row is `ran` | Demand the artifact its own `Demands` cell in the stages table names |
| A stage's `## Stage outcomes` row is `skipped` | Demand nothing that stage's `Demands` cell names |
| An `## Undecidable` entry claims `- Rung: probe` | Its `- Probe: <move>` must name a move whose own `## Move outcomes` row is `ran` |
| A finding attributes itself to the skill-less drive and names the subject as its target | Reject it; that drive never ran the skill's own machinery and cannot make a claim with the subject as its target |
| A `sensitivity` box already holds files | Exit `2` naming the path; never adopt a non-empty box |
| The subject declares no computed values in a parseable table | Emit "this subject declares no computed values" naming the range searched; exit `2`, never a clean verdict |
| A sensitivity control drive exits `0` and the declared values do not change | Exit `2`, `kind=sensitivity-control-stalled`; every pair is `unreached` until a producer is proven to consume its box |
| A sensitivity baseline drive (every declared input present) exits nonzero | Exit `2`, `kind=sensitivity-baseline-refused`; no matrix is reported against a baseline the producer never computed. A refusal only once an input is removed stays a `producer-refused` cell, exit `0` |
| A sensitivity per-variation restore does not reproduce its pre-variation bytes | Exit `2`; the sweep halts, and the next variation is never attempted |
| A sensitivity drive writes outside its own box | Exit `2` as `build-escaped-the-box`; never reported as a finding |
| A declared value is `unchanged` for every varied input | `not adjudicable`, never `artefact wrong`; the finding states the observation and the tested range, never a motive |
| More declared inputs exist than the sensitivity cap | Vary the first four, sorted; name the rest in `## Unchecked` with the true total |
| An inversion recipe declares no `mutations` block | Exit `2`; never reported as zero guarded facts |
| An inversion guarded fact's observing run is not green before any mutation | Exit `2`, `kind=baseline-not-green`; no file is mutated and no finding is emitted |
| An inversion guarded fact's literal is absent from its declared line | Exit `2`, `kind=fact-absent`; halt before any write |
| An inversion guarded fact's literal appears more than once on its declared line | Exit `2`, `kind=fact-ambiguous`; neither occurrence is substituted |
| An inversion guarded fact's replacement only inverts a comparison operator | Exit `2`, `kind=operator-flip`; the value itself must change |
| An inversion guarded fact's write leaves the file's bytes unchanged | Exit `2`, `kind=no-op-write`; the observing run never executes |
| An inversion guarded fact's restore does not reproduce its pre-mutation bytes | Exit `2`, `kind=sensitivity-restore-failed`; the sweep halts, and the next fact is never mutated |
| An inversion drive writes outside its declared file | Exit `2` as `build-escaped-the-box`; never reported as a finding |
| More guarded facts exist than the inversion cap | Drive the first eight, sorted; name the rest individually in `## Unchecked` |
| An `exits` recipe declares no `states` block | Exit `2`; never reported as zero states |
| An `exits` box already holds files | Exit `2` naming the path; never adopt a non-empty box |
| A reported state names no published act, and declares itself a human judgement | Report `judgement`; never a finding, never a published command |
| A reported state names no published act, and declares nothing | Report `unstated`, a finding, with the driveable range that was searched |
| A published act splits empty, or carries a shell metacharacter | Report `published-but-unparseable`; never passed to `shell=True` |
| A published act's `argv[0]` resolves under neither `--subject`, `--repo-root`, nor the recipe's declared interpreters | Report `published-but-unparseable`; refused before any process starts |
| A published act's binary does not exist | Report `published-but-not-executable` |
| A published act hangs past `exits`' own `--timeout` | Report `published-but-timed-out` |
| A published act reaches the real subject | Exit `2` as `exit-escaped-the-box`; never reported as a finding |
| An `enumeration-reach` recipe declares no `checks` block | Exit `2`; never reported as zero checks |
| A declared check's site does not end `.py`, or does not parse as Python | Report `unreachable-for-this-language`; never guessed at |
| A declared check's own iteration source is computed from the subject | Report `derived`; never a finding |
| A declared check's own iteration source is a literal collection, a namespace walk, or a filtered namespace walk | Report both the check's own claim and the bounded kind, side by side |

## Handoff

The audit's terminal state is a **handoff**, never an invocation and never a
repair.

| Field | Value |
| --- | --- |
| `mutations` | `0` |
| `documentAuthority` | `FORBIDDEN` |
| `explicitHandoffRequired` | `true` |

The audit makes no edit to the subject. Not to the documentation, not to the
code, not the one-line deletion that would close a `phantom`. The wall between
reporting and repairing **is** the product: an audit that repairs is an audit
whose findings nobody reviewed.

This skill cannot invoke a spec-driven-development phase. Every `sdd-*` skill is
`disable-model-invocation: true`, `user-invocable: false`, and delegate-only, so
there is nothing here to call. What this skill can do is **be** the exploration:
it runs under a doctrine that requires a shell, and it lands its report where a
proposal phase reads. Handing the report to the user, with the repair units and
the changed-line forecast already in it, is the whole terminal state.
