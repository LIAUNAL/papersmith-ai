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
