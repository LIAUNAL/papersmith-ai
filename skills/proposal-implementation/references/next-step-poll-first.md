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
