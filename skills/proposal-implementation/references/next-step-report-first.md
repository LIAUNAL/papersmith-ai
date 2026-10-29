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
