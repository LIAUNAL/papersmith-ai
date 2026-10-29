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
