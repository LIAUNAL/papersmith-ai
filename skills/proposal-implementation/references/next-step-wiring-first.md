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
