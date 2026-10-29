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
