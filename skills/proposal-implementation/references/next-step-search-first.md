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
