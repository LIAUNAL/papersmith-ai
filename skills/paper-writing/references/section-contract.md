## Reading the section contract

Four more verbs, from `the-contract-is-data-not-code` and
`the-phases-are-derived-not-remembered`: `contract`, `readiness`, `order`,
`phases`. Each `sections/*.md` file now opens with a `---`-fenced JSON
header — `section`, `position`, optional `after`, and a `blocks` list, each
block declaring `id`, `requires_facts`, `requires_declarations`,
`citations`, `optional`, and optionally `produces_facts` (see "A fact is
declared, or it is produced" below).

**The prose body is no longer merely read by a human.** Every contract's
prose now carries a `### External inputs` / `### Internal chain` partition
(a third, `### Structural decisions`, holds whatever names no block at
all); `contract` refuses `INPUT_PARTITION_ABSENT` when either required
heading is missing. Each `### Internal chain` row leads with a backticked
qualified id (`` `<section>.<block-id>` ``) naming a dependency, and that
dependency must be backed by a real `after` edge whose own quote is
literally present in the prose — a row naming an unresolvable id refuses
`CHAIN_ROW_UNRESOLVED`, a resolvable id with no backing edge refuses
`CHAIN_ROW_UNBACKED`. A `###`-level sub-unit heading (`Paragraph`, `Block`,
`Slot`, `Subsection`, `Part`, followed by an identifier) that resolves to
zero declared ids refuses `BLOCK_SUBUNIT_UNDECLARED`; one that resolves to
more than one refuses `UNIT_HEADING_AMBIGUOUS`. All four are wired into
`assemble_corpus`, so every verb that reads the corpus (`contract`, `order`,
`readiness`, `phases`, `plan`, `verify`, `write`) is gated by them.

| Verb | What it does | Refuses |
| --- | --- | --- |
| `contract [--file <path>]` | Validates the whole `sections/` corpus (flat id namespace, every `after` target resolved or reported dangling, the prose partition and its chain rows, and every `produces_facts` declaration — see "A fact is declared, or it is produced" below), or shows one file's parsed header with `--file` | `MALFORMED_HEADER`, `UNKNOWN_FACT`, `UNKNOWN_DECLARATION`, `UNKNOWN_CITATIONS_REGIME`, `ID_COLLISION`, `SECTIONS_OUTSIDE_REPOSITORY`, `INPUT_PARTITION_ABSENT`, `CHAIN_ROW_UNRESOLVED`, `CHAIN_ROW_UNBACKED`, `BLOCK_SUBUNIT_UNDECLARED`, `UNIT_HEADING_AMBIGUOUS`, `FACT_SELF_REQUIRED`, `FACT_ROUTE_AMBIGUOUS`, `FACT_PRODUCER_DUPLICATE`, `FACT_PRODUCER_ABSENT`, `PRODUCER_CHAIN_ABSENT` |
| `readiness (--paper <dir> \| --fact <id>... \| --declaration <id>...)` | Per-block `writable`/`blocked`/`not-applicable`, naming every still-missing fact and declaration separately; a still-missing PRODUCED fact also carries `blocked_on_produced` naming it and every one of its producer blocks. `--paper <dir>` reads the `declarations` region for basis `declaration-backed` (any flag also given is reported separately under `supposed`); at least one bare `--fact`/`--declaration` flag with no `--paper` is basis `supposed-only`, an explicit hypothetical what-if | adds `READINESS_BASIS_REQUIRED` |
| `order` | Derives the writing order from the block graph — `position`, declared block order, and every transcribed `after` edge; never the filename | adds `ORDER_CYCLE` |
| `phases [--phase N]` | Read-only "what can I write now": Kahn-wave decomposition of the block graph, each block's own readiness (basis `declaration-backed`, including `blocked_on_produced`), `opened` and provenance state, and the facts/declarations already on record. `--phase N` reports only waves `1..N` | adds `PHASE_NOT_READY` |

`--sections <dir>` overrides the default `sections/` at the repository root
on all four (`--paper <dir>` on `readiness`/`phases` overrides `paper/` the
same way), the same shape `--paper` already has elsewhere.

**`readiness` alone is not "what can I write now."** A bare `readiness`
call with neither `--paper` nor a flag has no basis to compute an answer
from and refuses `READINESS_BASIS_REQUIRED` rather than silently reporting
a stale, flags-only number — the exact defect that once let `readiness`'s
answer never change after a `declare`, because it never opened `main.tex`
at all. `phases` is the read-only report that actually answers "what can I
write now": it resolves readiness from disk itself, orders it into waves,
and gates a requested `--phase N` on every earlier wave being complete.
Over the shipped corpus (47 blocks) `phases` reports **nine** waves shaped
**21 / 3 / 6 / 10 / 2 / 2 / 1 / 1 / 1** — measured directly (`paper_cli.py
phases`, dated 2026-09-21), not copied from an earlier count: the shape
moved from **eight** waves, **22 / 7 / 11 / 2 / 2 / 1 / 1 / 1**, when
`the-methods-section-produces-the-contributions` moved `contributions`'
sole producer from `introduction.block-4b` to
`materials-and-methods.mm-proposal`, pulling the methods section's
`mm-proposal` block (and everything after it in the graph) earlier.

**The three closed vocabularies** a header may draw from: fifteen
`requires_facts` ids (`formulation`, `contributions`, `problem-statement`,
`gap`, `dataset`, `experimental-design`, `implementation`, `results`,
`limitations`, `skeleton`, and the study facts `protocol`, `sample`,
`outcomes`, `analysis-plan`, `participant-flow`), nine
`requires_declarations` ids (`author-roles`, `grant-title`, `grant-code`,
`repository-url`, `keyword-bounds`, `classification-line`, `ethics-approval`,
`review-registration`, `study-registration`), and three `citations` regimes (`discovery`,
`resolution`, `none`). A value outside any of the three refuses
immediately — this is deliberately closed, not a convention.

### A fact is declared, or it is produced

Every one of the fifteen `requires_facts` ids resolves through exactly one
of two routes, never both: the ten OBSERVABLE facts (`dataset`,
`experimental-design`, `implementation`, `results`, `formulation`, and the
study facts `protocol`, `sample`, `outcomes`, `analysis-plan`,
`participant-flow`) and the
structural `skeleton` fact stay `declare`-only, resolved from an operator
measurement or the skeleton-startup mechanism; the remaining four —
`contributions`, `problem-statement`, `gap`, `limitations` — are PRODUCED:
some block's own `produces_facts` header entry names them, and satisfaction
is read from that producer block's own written status in `main.tex`, never
from a `declare` call or the `declarations` region. `gap` is the one
corroborated exception with two legal producers at once (`related-work.rw-
closing` and `introduction.block-3` — a coupling-verification check
verifies they agree); every other fact resolves to exactly one producer or
refuses `FACT_PRODUCER_DUPLICATE`.

A `produces_facts` entry is the same rich `{value, source: {file, quote}}`
shape `requires_facts` already uses. A block whose `produces_facts` and
`requires_facts` name the same fact refuses `FACT_SELF_REQUIRED`; a
`produces_facts` entry naming a fact that only resolves through `declare`
(one of the ten observable facts, or `skeleton`) refuses
`FACT_ROUTE_AMBIGUOUS`; a required fact resolving to no producer anywhere
and absent from the declarable route refuses `FACT_PRODUCER_ABSENT`; and a
block requiring a produced fact whose own `### Internal chain` table
carries no row naming that fact's producer refuses `PRODUCER_CHAIN_ABSENT`
— the same code `order`'s own graph-reachability check raises when the
producer never reaches the consumer at all. `readiness`/`phases` both gain
a `blocked_on_produced` entry (alongside `declined_facts`/`stale_declines`)
naming the still-missing fact and every one of its producers, so a
`blocked` report tells the operator to WRITE the producer, never to
`declare` it; `declare` itself refuses `PRODUCED_FACT_UNDECLARABLE` on any
attempt to declare a produced fact directly.

**The block graph is authoritative; `position` is rendering order, not
writing order.** Two edges are transcribed in the shipped contracts' own
headers (`abstract` after `conclusions`, `introduction`'s `block-3` after
`related-work`), each carrying the exact sentence that states it. A third,
`title-and-keywords` after every section between `abstract` and
`back-matter`, is computed from `position` rather than enumerated — see
`specs/section-contract/spec.md`'s implementation note in
`openspec/changes/the-contract-is-data-not-code/` for why.

**Nothing here writes to `paper/main.tex`.** `order`'s output is a sequence
of block ids (`<section>.<block>`, e.g. `introduction.block-3`) under its
own `order` key, alongside `danglingEdges` — the same shape `open`/
`substitute` accept as `--block`. `order`'s own sequence and `phases`'s
wave-flattened sequence are NOT the same ordering in general (a
multi-frontier graph makes `order`'s min-heap interleave across waves where
`phases` groups by wave); do not assert them equal — `derive_waves` and
`derive_order` are two distinct read paths over the same graph, on purpose.
Wiring the two together (open every block in derived order, substitute each
as it's written) is a later capability, not this one.

**`optional`, read verbatim off the header, changes an observable outcome
in three places, never in `order`'s own sequence.** `contract`'s parsed
header echoes it per block; `readiness` reports `not-applicable` (instead
of `writable`/`blocked`) for an optional, unopened block under
`declaration-backed` basis; `verify` reports `unmeasured`, reason
`OPTIONAL_BLOCK_ABSENT`, for a coupling whose derived block set is entirely
optional-and-unopened. `order`'s own graph derivation reads no block's
`optional` flag at all — an optional block is ordered exactly like any
other.

### Decision Gates (contract, readiness, order, phases)

| Situation | Action |
| --- | --- |
| `contract` reports `danglingEdges` | An `after` target names an id absent from the corpus — not a defect on its own (deleting a contract is in scope), but confirm it is intentional before trusting `order`'s result |
| `order` refuses `ORDER_CYCLE` | Two or more blocks' `after` edges disagree about who comes first; the refusal names every block in the cycle — fix one of the transcribed sentences, it is never resolved by re-running |
| `readiness` reports a block `blocked` with an empty `missing_facts` | The block is waiting on a declaration only (an operator-supplied input like `repository-url`), not on any measurement |
| `readiness` refuses `READINESS_BASIS_REQUIRED` | Give `--paper <dir>` to read the real declarations region, or at least one `--fact`/`--declaration` flag for an explicit hypothetical — a bare call has no basis to answer from |
| `declare --decline <fact-id> --reason <text> --condition <json>` records a fact as DECLINED | The operator has decided this fact does not enter the paper for now (e.g. no experimental protocol exists yet) — distinct from "not yet measured". The `--condition` is re-evaluated fresh from disk on every `readiness`/`phases` call: while it holds, a block whose only missing facts are declined ones reports `declined`, naming the fact and reason; once it lapses, that block reports `blocked` again with `stale_declines` naming the fact, reason, condition and what changed — the skill never auto-unblocks on a lapse, it only surfaces it. A block missing even one live (non-declined) fact, one whose decline has lapsed, or any declaration at all, still reports `blocked` — a decline never masks a real gap. `--reopen <fact-id>` clears a decline exactly like a resolution, and a decline/resolve conflict on the same id refuses `DECLARATION_FIXED` in both directions (declining an already-resolved fact, or resolving an already-declined one) |
| A header refuses `UNKNOWN_FACT` / `UNKNOWN_DECLARATION` / `UNKNOWN_CITATIONS_REGIME` | The file declares a value outside the closed vocabulary — fix the header, the vocabularies are not extended by editing the reader |
| `contract` refuses `INPUT_PARTITION_ABSENT` | The prose body is missing `### External inputs` or `### Internal chain` — add the missing heading, present but empty if the section truly has none |
| `contract` refuses `CHAIN_ROW_UNRESOLVED` | An `### Internal chain` row does not lead with a resolvable, backticked `<section>.<block-id>` — fix the row's leading token |
| `contract` refuses `CHAIN_ROW_UNBACKED` | The row names a real block id, but no `after` edge backs that exact dependency — add the edge with a literal quote from the same prose |
| `contract` refuses `BLOCK_SUBUNIT_UNDECLARED` | A `###` sub-unit heading (`Paragraph`/`Block`/`Slot`/`Subsection`/`Part` + identifier) resolves to zero declared ids — either declare the missing id or fix the heading |
| `contract` refuses `UNIT_HEADING_AMBIGUOUS` | A `##` unit heading resolves to more than one declared id with no explicit grouping — name every resolved id in the heading itself |
| `phases` refuses `PHASE_NOT_READY` when `--phase N` is given | An earlier wave still has an unwritten, non-`optional` block — the refusal names it; open/substitute it (or every such block) before asking for a later phase |
| `write` refuses `PHASE_NOT_READY` | The target block's own wave has an earlier, still-incomplete wave — this fires before any draft/audit byte is read and before an attempt is spent; resolve the same way `phases` names |
