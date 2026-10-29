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
