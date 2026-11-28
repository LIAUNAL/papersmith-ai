## The prose pass: what it may not touch

An already-written block can be edited for **prose** — vocabulary, phrasing,
sentence rhythm, the connective between two sentences. That pass is **opt-in**: it
runs when the operator asks for it, on a block that already exists, and never as
part of `write`.

**The list it may not touch.** Citations and their identifiers, every number and
statistic, the methodology as stated, and the technical terms a block's contract
names. A pass that changes one of those has not improved the prose; it has broken
the block's binding to its evidence. That is a **failure, not a warning** — the
same class of damage `UNBOUND_SENTENCE` and `SPAN_NOT_IN_SOURCE` exist to catch,
and a draft that survives those two audits by accident has still damaged the
artifact.

**It never writes to `main.tex` itself.** Its output goes through `open` and
`substitute` like any other body, so the engine's own proof — that not one byte
outside the target block moved — still holds for it. A pass with its own
file-writing path would sit outside every guarantee this skill makes.

**It runs as a checklist with nothing installed.** The untouchable list above, plus
the three audits `write` already sequences. An operator-wired prose-editing connector
is an accelerator inside that contract, never a prerequisite for it: a skill that
stops working because a third-party server is absent has made the operator's
environment part of its contract.

**Style audit and style revision.** An already-written block can be measured for
writing quality — cadence (sentence-length $CV$; a monotone cadence reads flat),
overused academic phrasing (a closed catalog of words and formulaic patterns), and
lexical diversity — via `paper_cli.py ai_audit`, which reports a `style_score`
(0 clear, 1 needs revision) and a `style_verdict` (`clear`, `uneven`,
`needs_revision`). `paper_cli.py humanize` checks a revised draft of one block:
it refuses `F5_INVARIANT_VIOLATION` when a citation, number, statistic, or display
equation changed, and with `--apply` it substitutes the block only when the draft
meets `--style-target` (default 0.20) unless `--force`, refusing
`TARGET_SCORE_UNMET` otherwise. The audit delegates to the `ai-auditor` agent.
Pass `--expect-digest <sha256>`, the block digest `status` listed when the
revision started: `humanize` refuses `BLOCK_CHANGED_SINCE_READ` before judging
a draft written against a block that has changed since. `--draft` must sit
inside the repository (`PAPER_OUTSIDE_REPOSITORY`, whose detail says so); a
scratch draft kept elsewhere goes in inline with `--replacement "$(cat <path>)"`.

**Flow and redundancy.** Every style report also carries a `flow` key
(`flow_score`, `flow_verdict` in the same three bands, and `findings`, each
naming its sentence, its paragraph and the quoted span; `thresholds` states
every limit). It measures stock connectors (the same one opening two
sentences within five, more than a quarter of the sentences opening with
one, synthesis openers such as *Overall* or *Taken together* repeated),
sentence openings (consecutive repeats, one dominant opening, *This/These +
noun* in series), *because*, *where* and *, which* density (the *where*
that follows an equation and defines its symbols is exempt), repeated
five-word phrases across paragraphs and near-duplicate sentences, and
template phrasing (*It is worth noting*, *plays a crucial role*, *In this
context*, *serves as*, *This highlights*). `ai_audit --all` reports it over
the whole manuscript, where cross-block repetition shows, and per block.
`humanize` returns `flow_findings` and `revision_guidance`, and `--apply`
also refuses `TARGET_SCORE_UNMET` while `flow_verdict` is `needs_revision`
(unless `--force`). The guidance rebuilds each transition from the logical
relation (contrast, cause, consequence, elaboration, example) instead of
swapping one stock connector for another, drops a connector the sentence
order already carries, and cuts repetition — always under the F5 gate.

These are readability checks, never an AI detector: no step aims to make
machine-assisted prose pass as human-written, and a passing style score does not
change the obligation to declare AI use (every report carries that
`disclosure_notice`). The old keys `composite_score`, `verdict`, `target_score`,
and `meets_target`, and the `--target-score` flag, remain as deprecated aliases
for one release.

**It reports what it changed**, block by block, so the operator reads the diff it
produced instead of being asked to trust it.
