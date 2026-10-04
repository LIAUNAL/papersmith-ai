---
name: paper-writing
description: "Trigger: create or re-enter the paper/ tree; write one named block of paper/main.tex without touching another byte; read what sections/*.md declares about itself; see which writing phase is unlocked and which blocks gate the next; open the section/block skeleton once; assemble a block's redactor packet (contract prose, reference heading outlines, never reference prose, plus its bound source sections in transposition mode); record or reopen a declaration or fact resolution and see the paper's plan; resolve a citation against OpenAlex/Crossref/arXiv and rebuild refs.bib; validate a citation's verdict and placement before writing a block; judge a drafted, audited block against its own evidence and contract; compile a standalone diagram and prove it against the contract's figure: obligation; or check the cross-section couplings (contribution list, chain, the gap, diagram disjointness, future-work/limitations), citation integrity and contract currency. Stdlib-only, keyless, fail-closed CLI (paper_cli.py)."
---

# Paper Writing

`paper/main.tex` is edited one named block at a time, byte-for-byte. A block
is delimited by two LaTeX-comment marker lines carrying its id and a sha256
digest of its own body; this engine never rewrites a byte outside the block
it was asked to change, and proves that on every call rather than assuming
it — before a single byte reaches disk.

## What this skill ships today

Twenty-eight verbs, wired into one front door (`scripts/paper_cli.py`):
`scaffold`, `status`, `open`, `substitute` (the block-substitution engine),
`contract`, `readiness`, `order` (the section contract reader —
`the-contract-is-data-not-code`), `phases` (the read-only "what can I write
now" wave report), `skeleton` (opens the empty section/block structure once,
from two structural decisions inferred off disk on every later call —
`the-phases-are-derived-not-remembered`), `declare`, `bind`/`separate` (the
source-section binding loop — a document-rooted binding is recorded only
after a whole-cut argument settles at zero: `source-section-binding`,
`source-separation-review`), `mark` (records and seals a source root's
revision rule or a `guidance/` folder's class, validated against disk at
write time — the answer to `SOURCE_REVISIONS_UNDECLARED` and an
unclassified `guidance/` folder, by using the skill, never a hand edit:
`the-skill-writes-the-declaration-it-demands`), `observe` (validates an
`insumos-observer` report against the observable-fact schema before a human
runs `declare` against it), `plan` (the paper's own decisions —
`the-paper-carries-its-own-decisions`), `resolve`,
`bib build`, `validate` (citation resolution, a sourced bibliography, and
the verdict/placement gate — `no-claim-without-a-source-that-holds-it`),
`write` (evidence-bound drafting, contract audit and the style-leak proof —
`the-writer-may-assert-only-what-it-was-given`), `render`/`place` (a
diagram that compiles or says why, the repair-budget ledger, and the
data-figure boundary — `a-diagram-that-compiles-or-says-why`), `verify`
(read-only coupling verification, citation integrity and contract currency —
`the-couplings-hold-or-they-do-not`), and `packet` (the redactor's own
context: a block's contract prose plus reference heading outlines, never
reference prose — `the-phases-are-derived-not-remembered`), `couplings` (validates and
writes `paper/couplings.json` whole -- the producer declaration record
`verify` never had), `full_text` (fetches one already-resolved
identifier's own PDF, keyless, from its cached metadata's measured
full-text URL, and places it loose under `guidance/<section>/`), `reuse`
(read-only: for one block's open claims, which already-ingested,
evidence-classed papers carry no verdict yet), and `exhaustion`
(read-only, corpus-wide: every evidence-classed ingested paper's
exhaustion state -- lists only, never deletes), and `figure optimize`/`figure audit` (the TikZ optimizer and the figure-prose semantic auditor). To the
substitution engine, block ids
stay opaque strings — shape only (`[A-Za-z0-9._-]+`), no meaning. The
contract reader is what says which ids exist, what each requires, and where
in the document they belong, entirely over in `sections/*.md`.
`declare`/`plan` are what records the operator-supplied declarations and
fact resolutions those requirements name, and reports where the paper
stands against all of it in one read-only call — see "The paper's own
decisions" below.

**This CLI is no longer offline end to end.** `resolve` is the one path
that reaches the network — keyless, stdlib `urllib` only, against OpenAlex,
Crossref and arXiv, behind a `papersmith.yaml` role the operator can empty.
Every other verb remains exactly as offline as before; `resolve` refuses by
name (`RESOLVER_UNREACHABLE`, `DISCOVERY_UNAVAILABLE`, `RESOLVER_ROLE_EMPTY`)
rather than silently returning an empty result.

**Not shipped yet, on purpose.** Deriving a writing order and substituting a
block by id are two capabilities that exist side by side and are not yet
wired together: `order`'s output (a sequence of `<section>.<block>` ids) is
not fed into `open`/`substitute` automatically, and nothing here assembles
`paper/main.tex` from `sections/` on its own. Do not invent that wiring, and
do not read its absence as a bug — it is a later phase.

## Every read starts the same way

Run `status` before touching anything. It lists every block's id, digest and
byte region, and writes nothing:

```bash
.venv/bin/python skills/paper-writing/scripts/paper_cli.py status
```

(Every verb accepts `--paper <dir>` to override the default `paper/` at the
repository root; omit it and the default is used.)

## The four verbs

| Verb | What it does | Refuses |
| --- | --- | --- |
| `scaffold` | Creates `paper/main.tex`, `paper/refs.bib`, `paper/Figures/`, `paper/.gitkeep` if absent. Idempotent — a second run never touches an existing byte, hand edits included | `PAPER_OUTSIDE_REPOSITORY`, `PAPER_NOT_A_DIRECTORY`, `SCAFFOLD_ENTRY_WRONG_TYPE` |
| `status` | Read-only block table: id, digest, byte region, per block | `PAPER_ABSENT`, `TEX_UNDECODABLE`, `MARKER_MALFORMED`, `BLOCK_DUPLICATED`, `BLOCK_UNPAIRED`, `BLOCK_NESTED` |
| `open --block <id> (--after <id> \| --at-end)` | Installs an EMPTY begin/end pair at the named position. Never writes content — the first write to a new block is always `open` then `substitute` | adds `BLOCK_DUPLICATED`, `ANCHOR_ABSENT`, `OPEN_POSITION_REQUIRED`, `OPEN_POSITION_CONFLICT` |
| `substitute --block <id> (--body <path\|-> \| --adopt)` | Replaces one block's body, or (`--adopt`) accepts the on-disk body as the new baseline without changing it | adds `BLOCK_ABSENT`, `BLOCK_HAND_EDITED`, `CONTENT_CARRIES_MARKER`, `NOTHING_TO_ADOPT`, `SUBSTITUTE_MODE_REQUIRED`, `ADOPT_BODY_CONFLICT`, `SUBSTITUTION_NOT_LOCAL`, `TEX_MOVED` |

Every JSON reply carries `"status": "ok"` (exit 0) or `"status": "refused",
"code": "<CODE>", "detail": "<why>"` (exit 2). A successful `substitute`
always adds `"rendering": "unproven"` — this engine has no LaTeX toolchain
and makes no claim the document compiles or that the change looks right on
the page. That is a separate, unbuilt capability.

**There is no `--force`.** Nothing here ever discards a human's on-disk text
in favor of an incoming body. The only exit from a hand-edited block is
`--adopt`, which re-baselines the digest and leaves the body untouched.

## Decision Gates

| Situation | Action |
| --- | --- |
| `status` reports `BLOCK_HAND_EDITED` | Read the on-disk body before deciding. `--adopt` accepts it as the new baseline; a plain `substitute` still refuses until you do |
| `open` refuses `ANCHOR_ABSENT` | The named `--after <id>` has no pair yet — `status` first, then either open that id or pick `--at-end` |
| `open` refuses `OPEN_POSITION_REQUIRED` / `OPEN_POSITION_CONFLICT` | Exactly one of `--after <id>` / `--at-end` is required, never zero, never both |
| `substitute` refuses `SUBSTITUTE_MODE_REQUIRED` / `ADOPT_BODY_CONFLICT` | Exactly one of `--body <path\|->` / `--adopt`, never zero, never both |
| `substitute` refuses `CONTENT_CARRIES_MARKER` | The replacement body itself contains a line starting `%% paper-writing block` — strip it, this grammar cannot nest |
| `substitute`/`open` refuses `SUBSTITUTION_NOT_LOCAL` | The in-memory candidate would have changed a byte outside the target block; nothing was written. This should never fire from ordinary use — report it as a defect if it does |
| `substitute`/`open` refuses `TEX_MOVED` | Something else wrote to `main.tex` between this call's read and its write. Re-run the command against the current file — never retry blind against stale offsets |
| Any command refuses `PAPER_ABSENT` | Run `scaffold` first |

## The safety net has no git behind it — three layers, read for what each alone catches

`paper/*` is gitignored except `.gitkeep` (`paper-scaffold` writes it), the
same policy this repository already applies to `proposals/` and
`experiments/`. `main.tex` is never tracked, so nothing below assumes a
commit history could recover a bad write — none exists.

1. **The byte-identity invariant**, checked on candidate bytes in memory
   before any write. Primary and load-bearing, not a supplement to a deeper
   history that does not exist — the only layer with no depth limit,
   because refusing to write has no "how many steps back" question. Proven
   by an executed mutation harness (`tests/test_paper_writing.py`,
   `MutationProofTests`), not asserted: a real subprocess patches the
   engine's own source, purges any cached bytecode, and confirms the
   corresponding guard test goes red.
2. **Same-directory temp file + `os.replace`**. Catches an interrupted
   process only: `main.tex` is always fully the pre-write or fully the
   post-write content, never torn. Says nothing about whether the
   post-write content is correct.
3. **A one-deep pre-image** at `paper/.paper-writing/main.tex.prev`. The
   only recovery path once bytes have reached disk — the one case layer 1
   cannot reach, because layer 1 only rejects a region-boundary violation,
   never a correctly-scoped write whose content nobody actually wanted.
   Recovers exactly the state immediately before the most recent write. A
   second successful write overwrites it; anything earlier than one step
   back has no recovery path anywhere in this system.

`BLOCK_HAND_EDITED` sits beside these three, not inside them: it protects a
human's on-disk text from being silently overwritten, which is a different
property from "the write stayed inside its own region."

**Declared gap, narrowed.** The marker digest covers block bodies and, as of
`the-paper-carries-its-own-decisions`, the `declarations`/`provenance`
region bodies too — a hand edit to either region's own bytes refuses
(`DECLARATIONS_HAND_EDITED` / `PROVENANCE_HAND_EDITED`) rather than passing
silently. What remains outside every digest is ordinary prose: text that is
neither inside a block nor inside a region. A hand edit there is still
invisible to every layer above — `status` cannot see it and neither can the
byte-identity invariant, since both compare against the pre-image read in
the same call and carry that edit forward silently. That prose belongs to
the human; this engine never claims it.

## Binary I/O only

Every read and write of `main.tex` is binary, end to end. A universal-
newlines text-mode open would silently flatten every CRLF pair in the file
to LF outside the block being touched — exactly the corruption the
byte-identity invariant exists to catch, and a fixture with real CRLF bytes
(`tests/test_paper_writing.py`, `CRLFTests`) proves it round-trips
untouched.

## What "shape only" means for block ids

`[A-Za-z0-9._-]+`, nothing else. The block-substitution engine (`open`,
`status`, `substitute`) never validates an id against a list of what should
exist, never derives ordering, and never opens anything under `sections/`
itself — that reasoning is entirely the contract reader's, described below,
and the two sides only agree on the shape class, never on meaning. A later
change may join ids with `.` or `-` and the substitution engine needs zero
changes; a `/`-joined id would need a one-character widening of the shape
class there, and nothing more.

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

**The three closed vocabularies** a header may draw from: ten
`requires_facts` ids (`formulation`, `contributions`, `problem-statement`,
`gap`, `dataset`, `experimental-design`, `implementation`, `results`,
`limitations`, `skeleton`), six `requires_declarations` ids (`author-roles`,
`grant-title`, `grant-code`, `repository-url`, `keyword-bounds`,
`classification-line`), and three `citations` regimes (`discovery`,
`resolution`, `none`). A value outside any of the three refuses
immediately — this is deliberately closed, not a convention.

### A fact is declared, or it is produced

Every one of the ten `requires_facts` ids resolves through exactly one of
two routes, never both: the five OBSERVABLE facts (`dataset`,
`experimental-design`, `implementation`, `results`, `formulation`) and the
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
(one of the five observable facts, or `skeleton`) refuses
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

## Opening the empty skeleton: `skeleton`

Before any block can be written, every section/block id the manuscript will
carry must exist, empty, in `paper/main.tex` — `skeleton` builds exactly
that, and only that: it opens each non-excluded id through the existing
`open_block` writer alone, in `derive_order` order, and writes no content.

```bash
.venv/bin/python skills/paper-writing/scripts/paper_cli.py skeleton \
    --related-work yes --dataset-in materials
```

| Verb | What it does | Refuses |
| --- | --- | --- |
| `skeleton --related-work yes\|no --dataset-in materials\|experimental-setup [--sections <dir>] [--paper <dir>]` | Opens every `sections/*.md` block id the two answers imply, empty, skipping ids already opened | `SKELETON_ANSWER_REQUIRED`, `SKELETON_ALREADY_DECIDED`, `DATASET_PLACEMENT_CONFLICT` |

**Two structural decisions, asked exactly once.** Whether the manuscript
carries a dedicated Related Work section, and whether the dataset is
described in Materials and Methods or in Experimental Setup, are answered
by `--related-work`/`--dataset-in` the first time any block is opened.
Neither flag given refuses `SKELETON_ANSWER_REQUIRED`, naming which is
missing.

**Every later call infers both decisions from disk, never from a stored
flag and never from an agent's own memory.** Once any corpus block is
already opened, `skeleton` re-derives both answers straight from the
opened block ids themselves (`paper_declarations.infer_skeleton_decisions`)
and compares them against whatever was given: a contradiction refuses
`SKELETON_ALREADY_DECIDED`, naming both what disk already records and what
was requested. Opening both `mm-dataset` and `es-dataset` at once is a
genuine conflict the inference cannot resolve one way — it refuses
`DATASET_PLACEMENT_CONFLICT` rather than silently picking a winner.
Already-opened ids are skipped, so a repeated `skeleton` call with the same
answers is idempotent.

## The paper's own decisions: declarations and provenance

Two more regions live in `main.tex` alongside its blocks, holding JSON
bodies rather than prose — `declarations` and `provenance`. Neither is
readable by Phase 1's block scanner: both markers share the `%% paper-writing
<kind>` lead-in but never the literal token `block` in slot 3, so
`MARKER_PREFIX`'s own `startswith` check skips them (proven in
`tests/test_paper_decisions.py::DisjointGrammarTests`).

`declare` records two kinds of value: a `declaration` (one of the six
operator-input ids — `author-roles`, `grant-title`, `grant-code`,
`repository-url`, `keyword-bounds`, `classification-line`) or a `fact`
resolution (one of the ten fact ids). Recording either fixes it immediately
— a further `declare` on the same id refuses `DECLARATION_FIXED` until
`--reopen <id>` clears exactly that entry.

```bash
.venv/bin/python skills/paper-writing/scripts/paper_cli.py declare \
    --declaration repository-url --value https://example.org/repo
.venv/bin/python skills/paper-writing/scripts/paper_cli.py declare \
    --reopen repository-url
```

**A fact can also be DECLINED, not just resolved.** `declare --decline
<fact-id> --reason <text> --condition <json>` records a fact the operator
has decided does not enter the paper for now — e.g. no experimental
protocol exists yet — as distinct from a fact simply not yet measured. All
three flags are mandatory together: `--reason` empty or missing refuses
`DECLINE_REASON_REQUIRED`, since an undocumented decline is
indistinguishable from an omission six months later; `--condition` missing
refuses `CONDITION_REQUIRED`; a malformed condition (not a JSON object, a
missing/wrong-typed required field, or a `path` resolving outside the
repository root) refuses `CONDITION_MALFORMED`; a `condition.type` outside
the closed vocabulary (today, only `"directory-empty-except"`) refuses
`UNKNOWN_CONDITION_TYPE`. A decline fixes the fact exactly like a
resolution does — declining an already-resolved fact, or resolving an
already-declined one, both refuse `DECLARATION_FIXED` until `--reopen
<fact-id>` clears it, the same single gate every other fixed record goes
through.

**The condition is what keeps a decline from going stale on a human's
memory.** It is re-evaluated fresh from disk on EVERY `readiness`/`phases`
call, never cached and never evaluated only once at decline time: a block
whose only missing facts are declines whose condition still holds reports
`declined`, naming the fact and its reason. Once the named condition no
longer holds — `"directory-empty-except"` means the path now contains
something beyond its own `ignore` allowlist, e.g. a real file landed in
`experiments/` — that same block reports `blocked` again, and the response
carries `stale_declines` naming the fact, its reason, its condition, and
what changed (`detail`). The skill never auto-unblocks a block just
because a lapsed condition suggests progress, and it never keeps quietly
reporting `declined` once the condition is gone either — it only surfaces
the lapse; the operator decides what happens next (declare the fact for
real, or re-decline on new grounds). A block missing even one live
(non-declined) fact, one whose decline has lapsed, or any declaration at
all, still reports `blocked` regardless of any other decline's own state —
a decline never masks a real gap.

```bash
.venv/bin/python skills/paper-writing/scripts/paper_cli.py declare \
    --decline experimental-design --reason "no protocol exists yet in experiments/" \
    --condition '{"type": "directory-empty-except", "path": "experiments", "ignore": [".gitkeep"]}'
```

| Verb | What it does | Refuses |
| --- | --- | --- |
| `declare (--declaration <id> \| --fact <id> \| --reopen <id> \| --decline <fact-id> --reason <text> --condition <json>) [--value <v>]` | Records a declaration or fact resolution, clears one id's fixed state, or declines a fact with a disk condition re-checked on every later read. A PRODUCED fact (`contributions`, `problem-statement`, `gap`, `limitations`) can never be declared or declined directly — its satisfaction comes only from writing its producer block | `DECLARE_MODE_REQUIRED`, `DECLARE_MODE_CONFLICT`, `DECLARE_VALUE_REQUIRED`, `DECLINE_REASON_REQUIRED`, `CONDITION_REQUIRED`, `CONDITION_MALFORMED`, `UNKNOWN_CONDITION_TYPE`, `UNKNOWN_DECLARATION`, `UNKNOWN_FACT`, `DECLARATION_FIXED`, `DECLARATIONS_HAND_EDITED`, `PRODUCED_FACT_UNDECLARABLE` |

`substitute` also accepts an optional `--contract <path>`: it changes no
byte of what gets written to the block, only records — in the `provenance`
region — the contract file's sha256 digest as read at that exact moment and
the declarations region's current generation. A block substituted without
`--contract` is reported `unprovenanced`, never assumed current.

```bash
.venv/bin/python skills/paper-writing/scripts/paper_cli.py substitute \
    --block intro --body body.tex --contract sections/introduction.md
```

`plan` reads all three concerns — guidance classification, declaration/fact
fill state, and provenance state (`current`, `drifted`, `unprovenanced`) —
in one call, and writes nothing anywhere:

```bash
.venv/bin/python skills/paper-writing/scripts/paper_cli.py plan
```

| Verb | What it does | Refuses |
| --- | --- | --- |
| `plan [--guidance <dir>] [--sections <dir>]` | Read-only aggregation: guidance classes plus their declaration state, source root states plus their declaration state, declaration/fact fill state, per-block provenance state | `PAPER_ABSENT`, `TEX_UNDECODABLE`, marker/region grammar codes, `GUIDANCE_OUTSIDE_REPOSITORY`, `UNKNOWN_GUIDANCE_CLASS`, `MALFORMED_GUIDANCE_MARKER`, `SOURCE_DECLARATION_HAND_EDITED`, `GUIDANCE_DECLARATION_HAND_EDITED`, `SECTIONS_OUTSIDE_REPOSITORY`, `MALFORMED_HEADER`, `ID_COLLISION` (no new codes of its own — the two `*_HAND_EDITED` codes belong to `read_revisions_marker`/`_classify`, reached here because `plan` reads through the same readers) |

**`plan` names every declarable root's and every `guidance/` folder's
declaration state, in ONE shared vocabulary — never two.** A `sourceRoots`
key carries one entry per root `FACT_SOURCE_ROOT` knows, each naming that
root's existing measurement `state`/`documents`/`reason` plus a
`declaration` value; `guidance`'s own entries widen from a bare class
string to `{"class": ..., "declaration": ...}`. Both `declaration` values
are drawn from the SAME four-value vocabulary: `"undeclared"` (no marker),
`"declared-unsealed"` (a valid marker with no seal — every marker written
before this skill could seal one, and every marker written with `mark
... --unsealed`), `"declared-sealed"` (a valid marker whose recorded seal
matches), or `"n/a"` (a `REPOSITORY`- or `INGESTED`-kind source root, which
carries no revisions rule at all — never applies to a `guidance/` folder,
since every listed one is classifiable). A worked `plan` reply, invented
names throughout:

```json
{"guidance": {"style-corpus": {"class": "style-reference", "declaration": "declared-sealed"},
              "scratch":      {"class": "unclassified",    "declaration": "undeclared"}},
 "sourceRoots": {"experiments": {"state": "document-rooted", "documents": 3,
                                 "reason": null, "declaration": "declared-sealed"},
                 "proposals":   {"state": "unmeasured", "documents": 0,
                                 "reason": "... holds no '*.md' documents",
                                 "declaration": "undeclared"}},
 "declarations": {"...": "..."}, "provenance": ["..."]}
```

**Reopening a fact or declaration invalidates the blocks that named it.**
`plan` reads the `sections/` corpus (`--sections` overrides it, same shape
as the other three corpus-reading verbs) to derive, per block, whether any
fact or declaration its own contract names was declared or reopened after
that block's own provenance was written — `declare`/`--reopen` both bump
a record's own generation counter; a block whose recorded generation is
now behind is reported `drifted`, the same state name a contract-byte edit
already used. No new state, no new field on-disk carries a literal "stale"
flag — this is a derived read-time property, recomputed on every `plan`
call from `paper_declarations.affected_blocks` (the reopen-scan function)
and the generation each record was last touched at, never from write
order.

**`guidance/` classifies as `style-reference` or `evidence`, from a
per-folder marker only — never a folder's name.** A folder with no
`.paper-writing.json` reports `unclassified`, including every folder on a
fresh clone; that is designed behavior, not a fault. Both classes have a
real, wired consequence: `style-reference` feeds the style channel
(`packet`/`resolve_style_set`, below) and, since `the-skill-stops-trusting-
memory`, GATES `validate --source-md` shut (`SOURCE_STYLE_REFERENCE`);
`evidence` is the one class `validate --source-md` accepts
(`SOURCE_NOT_EVIDENCE` otherwise) — classifying a folder is no longer a
label with nothing reading it back.

**`read_registry` and the actual ingested papers live at two different
depths.** `read_registry` (above, driving `plan` and now `validate`)
enumerates exactly one level — `guidance/<category>/` — and reports each
category's own class or `unclassified`. The eight ingested papers this
skill ships sit one level further down, at
`guidance/<category>/<paper>/<paper>.md`; `ingested_papers` walks that
second level for `packet` below. `guidance/*/*` is a `.gitignore` pattern,
so `fd`/`rg` report that whole tree empty — both readers walk it with
`Path.iterdir()`, gitignore-blind by construction, never a shell call. A
category folder still unclassified on a given checkout keeps reporting
`unmeasured` through the style channel, and now refuses `SOURCE_NOT_
EVIDENCE` from `validate` — correct, and the operator's own pending
decision, not a defect.

**Two kinds of guidance folder coexist, ADDITIVELY.** A function-named
folder (`reference-papers`, `paper-guide`, `data-paper`,
…) is whatever the operator has always used it for — style references, a
general paper guide, a benchmark's own data paper — and every one of those
keeps flowing through `read_registry`/`classify_source_md` exactly as
before; nothing here deletes, moves or reclassifies any of them. A
**section citation folder** is a SECOND, independent kind: a folder whose
name equals a section id the parsed `sections/` corpus declares (from
`SECTION_ID` in a contract's own front matter — `introduction`,
`related-work`, `materials-and-methods`, … — never a hand-listed tuple,
since one went stale silently in this repository the day the skill grew
past its first three verbs). It holds exactly that section's own cited
PDFs, downloaded there for `paper-ingestion` to turn into evidence
(`no-citation-before-its-paper-is-ingested`, item 1). Nothing distinguishes
the two kinds structurally — a folder is read either way through the same
`.paper-writing.json` marker and the same `Path.iterdir()` walk
(`paper_guidance.section_citation_status`) — the ONLY thing that makes a
folder a section citation folder is its name matching a real section id;
an operator's function-named folder that happens to collide with a future
section id would simply become both at once, which is intended, not a
conflict to resolve. `plan` reports every corpus section's own citation
status under `sectionGuidance` — `{exists, classification, ingested,
pending_pdfs}` per section id — alongside `guidance`'s pre-existing
function-named-folder registry, in the same call.

**No `--adopt` exists for either region.** A hand-edited `declarations` or
`provenance` region refuses (`DECLARATIONS_HAND_EDITED` /
`PROVENANCE_HAND_EDITED`) and writes nothing — unlike a block body, a
region is a decision the machine reads back as authority, and adopting a
hand edit would launder an unreviewed change into "what was decided."

## Recording a declaration: `mark`

One verb, `mark`, with two sub-modes — `revisions` and `class` — from
`the-skill-writes-the-declaration-it-demands`. Both write the SAME per-
directory `.paper-writing.json` file name, validated against the real files
on disk at the moment of writing, sealed the same way, with the same
rollback mode. They keep disjoint key sets (`revisions` for a source root,
`class` for a `guidance/` folder) and their own kind-specific refusals —
this is one subject (a directory's own declaration), not two.

```bash
.venv/bin/python skills/paper-writing/scripts/paper_cli.py mark revisions \
    --root experiments --revision-prefix r --ordinal-digits 2
.venv/bin/python skills/paper-writing/scripts/paper_cli.py mark class \
    --folder style-corpus --class style-reference
```

| Verb | What it does | Refuses |
| --- | --- | --- |
| `mark revisions --root <name> --revision-prefix <prefix> --ordinal-digits <n> [--unsealed]` | Records `<root>/.paper-writing.json`'s `revisions` grammar, matched against `sorted(path.glob("*.md"))` at the moment of writing, sealed by default | `SOURCE_ROOT_UNDECLARABLE`, `MALFORMED_SOURCE_MARKER`, `SOURCE_DECLARATION_UNMATCHED` |
| `mark class --folder <name> --class <value> [--guidance <dir>] [--unsealed]` | Records `guidance/<folder>/.paper-writing.json`'s `class` grammar, checked against the folders actually enumerated under `guidance/` at the moment of writing, sealed by default | `GUIDANCE_FOLDER_ABSENT`, `UNKNOWN_GUIDANCE_CLASS`, `EVIDENCE_ROOT_AMBIGUOUS`, `MALFORMED_GUIDANCE_MARKER` |

**Neither verb creates the directory or folder it names, and no operator
string is ever joined onto a path.** `--root` is matched against the
derived declarable-root map and `--folder` against `sorted(guidance_dir.
iterdir())`; the write target always comes from the matched entry, never
from string concatenation. `--root` MUST name a `PROSE`-kind key of
`FACT_SOURCE_ROOT` — otherwise `SOURCE_ROOT_UNDECLARABLE`, naming every
declarable root and the rejected root's own kind. `--folder` MUST name a
directory directly under the resolved `guidance/` — otherwise
`GUIDANCE_FOLDER_ABSENT`, naming every folder that is there.

**The loop this verb closes — a refusal now names a command, not just a
wall.** Two independent gating verbs raise the refusal `mark` answers:

```
write / bind refuses SOURCE_REVISIONS_UNDECLARED
  │  names the root, the marker filename it is missing, every *.md file
  │  currently under it, and the exact `mark revisions` invocation to run
  ▼
mark revisions --root <name> --revision-prefix <prefix> --ordinal-digits <n>
  │  matches the declared prefix/width against disk RIGHT NOW; zero
  │  matches refuses SOURCE_DECLARATION_UNMATCHED instead of writing
  ▼
write / bind proceeds
```

```
validate --source-md refuses SOURCE_NOT_EVIDENCE (folder unclassified)
  ▼
mark class --folder <name> --class evidence
  ▼
validate --source-md proceeds
```

**Re-recording always succeeds — there is no `--reopen`, no `--adopt`, and
no stuck state.** Both `mark` sub-modes always write when their own
write-time validation passes, whether or not a marker already exists at
that path and whatever its existing seal says. A hand-edited marker is
cleared by running `mark` again with values matching the files actually on
disk, never by hand-editing the file — running the verb IS the only exit,
because there is no `--adopt`.

**The seal, and exactly how strong it is.** Both sub-modes write a
`seal_sha256` key by default — a digest over the declaration's own
canonical bytes (sorted-keys JSON, so the identical declaration serializes
identically across runs), excluding that key itself. The seal is verified
inside the same reader every gating verb already reaches
(`read_revisions_marker`, `_classify`) — never inside `plan` alone — so a
hand edit to a sealed marker's bytes refuses `SOURCE_DECLARATION_HAND_EDITED`
or `GUIDANCE_DECLARATION_HAND_EDITED` the next time ANY gating verb reads
it, not only when `plan` happens to be the one asking.

> This seal detects an unaware edit. It is self-consistency, not tamper-proofing: the convention has no secret, so anyone who reproduces it can edit the file and recompute a matching seal.

That is the seal's entire claim — no more. It stops a declaration from
silently drifting out of sync with a hand-typed edit nobody meant to make;
it does not stop a determined edit, because the convention that computes it
is public, reproducible, and lives in this very file.

**`--unsealed` is the rollback path, and only that.** Both sub-modes accept
`--unsealed`, which writes the declaration in the pre-seal grammar with the
`seal_sha256` key entirely absent — the exact shape an unmodified older
reader (one that predates this capability) still accepts. It is not a
weaker everyday mode: run it once per already-declared root or folder,
while the code that still understands `--unsealed` is present, immediately
before reverting past this capability — otherwise a revert would leave
every marker this skill sealed refused as malformed (`MALFORMED_SOURCE_
MARKER`/`MALFORMED_GUIDANCE_MARKER`) by the older reader, unreadable rather
than merely unsealed. `--unsealed` removes nothing a determined editor
could not already remove by hand-editing the file — it exists only to make
the rollback a command instead of a hand edit.

### Decision Gates (mark)

| Situation | Action |
| --- | --- |
| `write`/`bind` refuses `SOURCE_REVISIONS_UNDECLARED` | Run the exact `mark revisions` invocation the refusal names — it already reads the root's current `*.md` files for you |
| `mark revisions` refuses `SOURCE_ROOT_UNDECLARABLE` | `--root` names a root whose kind is not `PROSE` — pick one of the roots the refusal lists as declarable |
| `mark revisions` refuses `SOURCE_DECLARATION_UNMATCHED` | The prefix/digit-width pair matches zero `*.md` files under the root right now — the refusal lists every file it saw; fix the prefix/width or check the root |
| `validate --source-md` refuses `SOURCE_NOT_EVIDENCE` on a `guidance/` folder | Run `mark class --folder <name> --class evidence` (only if the folder truly holds evidence, never to silence the refusal) |
| `mark class` refuses `GUIDANCE_FOLDER_ABSENT` | `--folder` names a folder that does not exist directly under `guidance/` — the refusal lists every folder that is there; `mark` never creates one |
| `mark class` refuses `EVIDENCE_ROOT_AMBIGUOUS` | Another folder already carries the `evidence` class — re-mark that other folder first if this one should hold it instead |
| Either `mark` refuses `MALFORMED_SOURCE_MARKER` / `MALFORMED_GUIDANCE_MARKER` | The marker file on disk was hand-edited into an invalid shape — re-run `mark` with correct values; it always overwrites |
| `read_revisions_marker`/`_classify` refuses `SOURCE_DECLARATION_HAND_EDITED` / `GUIDANCE_DECLARATION_HAND_EDITED` | A sealed marker's bytes were hand-edited after sealing — re-run `mark` for that root/folder; there is no `--adopt` |
| About to revert past this capability | Run `mark ... --unsealed` once per already-sealed root/folder BEFORE reverting, or the older reader will refuse every sealed marker as malformed |

## No claim without a source that holds it: `resolve`

Search comes first, always — but search itself runs through the agent's own
MCP (`discovery` role, `.mcp.json`), never through this CLI. `resolve` is the
CLI-side half: given an identifier and a named connector, it fetches
metadata over stdlib `urllib`, keyless, and caches the result on disk keyed
by its own digest.

```bash
.venv/bin/python skills/paper-writing/scripts/paper_cli.py resolve \
    --identifier 10.1000/example --resolver openalex --role resolution
```

| Verb | What it does | Refuses |
| --- | --- | --- |
| `resolve --identifier <id> --resolver {openalex,crossref,arxiv} [--role <role>]` | Resolves one identifier's metadata through one named connector and caches it | `PAPERSMITH_CONFIG_UNREADABLE`, `UNKNOWN_ROLE`, `DISCOVERY_UNAVAILABLE`, `RESOLVER_ROLE_EMPTY`, `RESOLVER_UNREACHABLE`, `IDENTIFIER_UNRESOLVED` |

**Every role can be emptied in `papersmith.yaml`.** An empty `resolution`
role refuses `RESOLVER_ROLE_EMPTY` rather than silently resolving nothing;
an unreachable connector refuses `RESOLVER_UNREACHABLE` with a non-zero
exit, never a silent empty result. `contact` (a courtesy `mailto` for
OpenAlex's polite pool) is read from `papersmith.yaml`, never hardcoded, and
is never a secret — leaving it empty just means requests go out without it.

**No verdict lives in this CLI.** Whether a source's text actually supports
a claim is a judgment the agent makes by reading a located span
(`EvidenceSpan.locate`, `paper_evidence.py`) — this module only ever proves
a span is real, byte for byte; it never decides what the span means.

`bib build` rebuilds `paper/refs.bib` WHOLE, sorted, exclusively from
cached resolved metadata — never appended, never hand-typed:

```bash
.venv/bin/python skills/paper-writing/scripts/paper_cli.py bib build
```

| Verb | What it does | Refuses |
| --- | --- | --- |
| `bib build [--guidance <dir>]` | Rebuilds `refs.bib` from every block's cached, resolved AND ingested evidence records; checks both `\cite{}`/entry directions | `ENTRY_UNSOURCED`, `ENTRY_NOT_INGESTED`, `CITE_WITHOUT_ENTRY`, `ENTRY_WITHOUT_CITE` |

A hand-typed entry (no `resolver`/`metadata_digest` provenance) refuses
`ENTRY_UNSOURCED` before a single byte of `refs.bib` is rewritten — checked
entirely offline, since the provenance is either cached already or it is not.

**Resolved is not ingested.** `no-citation-before-its-paper-is-ingested`
(item 2) adds a second, independent requirement: a citation's cached
metadata may not reach `refs.bib` until the paper it cites has actually
been ingested — a DOI can resolve against OpenAlex while the PDF itself
still sits unread. `entry_from_record` checks both, and a record that
resolved but was never ingested refuses `ENTRY_NOT_INGESTED` by name,
naming the record's own cite key. **The match is never a guess**: a
resolved DOI/arXiv id and a `guidance/<root>/<paper>/` folder name have no
free correspondence, and pairing them by similarity risks silently citing
the wrong paper's metadata against the right paper's text. Instead this
reuses the one link that is already exact — `record["source_md"]`, the
literal path `EvidenceSpan.locate` verified a real quote against when
`validate --quote ... --source-md ...` built the evidence record — and
confirms that path still resolves to a real `guidance/<root>/<paper>/
<paper>.md` (`paper_guidance.is_ingested_source`, the same two-level shape
`ingested_papers` walks). A record whose evidence span was never located
(`insufficient`, or hand-built with no `source_md`) carries no such link
and refuses the same way.

`validate` is the single gate: submit one judged verdict for one claim
(the agent's own reading of a located span decides `holds` vs
`does-not-hold`; omitting `--quote`/`--source-md` records `insufficient`),
then check the block's round-bounded satisfaction, and write only when
every claim the block has evidence for holds:

```bash
.venv/bin/python skills/paper-writing/scripts/paper_cli.py validate \
    --block intro.claim --claim "the dataset holds 12000 labeled examples" \
    --quote "holds 12,000 labeled examples" --source-md guidance/06-introduction/paper1.md \
    --verdict holds --cite-key smith2024 --body body.tex
```

| Verb | What it does | Refuses |
| --- | --- | --- |
| `validate --block <id> [--claim ... --quote ... --source-md ... --verdict holds\|does-not-hold] [--body <path\|->] [--sentence <json>] [--regime <r> \| --section-md <path>] [--guidance <dir>]` | Optionally records one evidence submission, then reports `pending`/`satisfied`/`written`, or refuses on exhaustion | `SPAN_NOT_IN_SOURCE`, `VALIDATE_VERDICT_REQUIRED`, `EVIDENCE_EXHAUSTED`, `CITATION_MULTI_CLAIM_SENTENCE`, `CITATION_NOUN_PHRASE`, `CITATION_NOT_AT_SENTENCE_END`, `CITATION_DETACHED_FROM_OBJECT`, `CITATION_UNDER_NONE_REGIME`, `CONTRACT_HEADER_ABSENT`, `SOURCE_STYLE_REFERENCE`, `SOURCE_NOT_EVIDENCE` |

`--section-md <path>` reads `--block`'s `citations` regime straight from an
already-headered `sections/*.md` file, instead of typing `--regime` by
hand; an explicit `--regime` always wins when both are given.

**A `--source-md` that resolves inside a `guidance/` folder is gated by
that folder's own registry class** (`plan`'s `style-reference`/`evidence`
classification, above — never a second classifier). A folder classed
`style-reference` refuses `SOURCE_STYLE_REFERENCE`: that class feeds STYLE
only, and a quote lifted from one is not evidence no matter how well it
locates. A folder classed anything else — `unclassified` included — refuses
`SOURCE_NOT_EVIDENCE`: `evidence` is the one class this gate accepts. A
`--source-md` that does not resolve under `guidance/` at all is outside
this gate's business and is never refused here.

**Three search rounds per block, then exhaustion.** `insufficient` fails a
claim exactly as `does-not-hold` does — never a soft `holds`. On the third
round with claims still unsupported, `validate` refuses
`EVIDENCE_EXHAUSTED` naming every unsupported claim, and
`paper_block.substitute` is never reached: the write sits strictly inside
the all-satisfied branch.

**Placement dispatches on regime, never one universal rule.** Under
`discovery`, a citation must close the sentence it supports and a
noun-phrase citation is prohibited; under `resolution`, a citation attaches
to the object it credits wherever that sits, and a noun-phrase citation is
exactly what that asks for; under `none`, no citation is allowed at all.

**Observing before declaring: the `insumos-observer` agent.** For the five
facts an outside observer can check against evidence (`formulation`,
`dataset`, `experimental-design`, `implementation`, `results`), this skill
delegates to the `insumos-observer` agent — it reports satisfaction and
evidence, never a value, and never calls `declare` itself. Its JSON report
is shuttled to a file and read back through `observe`, which validates it
against the observable-fact schema before a human runs `declare` against
it — the same shuttle shape `write --draft <path>` already establishes for
the redactor's account, never trusting an agent's account unjudged.

```bash
.venv/bin/python skills/paper-writing/scripts/paper_cli.py observe \
    --report insumos-observer-report.json \
    --proposals proposals --experiments experiments \
    --implementation implementations/<target-repo>
```

| Verb | What it does | Refuses |
| --- | --- | --- |
| `observe --report <path> [--proposals <dir>] [--experiments <dir>] [--implementation <dir>]` | Read-only: validates an `insumos-observer` report against the ten observable facts and the `implementation`/`results` evidence-conflation guard, THEN reconciles it against a real disk measurement this process takes itself for every root given; writes nothing and never calls `declare` | `OBSERVATION_REPORT_UNREADABLE`, `NOT_AN_OBSERVABLE_FACT`, `EVIDENCE_CONFLATED`, `OBSERVATION_DISK_CONFLICT` |

**The skill measures source availability itself — it does not trust an
agent's word for it, and it does not trust a human's memory either.**
`--proposals`/`--experiments`/`--implementation` each name a root this
process measures directly (`Path.iterdir()`, gitignore-blind by
construction — the same mechanism `ingested_papers` already uses for
`guidance/`, never a shell call, never `fd`/`rg`, both of which honor
`.gitignore` by default and can report a genuinely populated directory
empty). Pass all three you can: when a fact's own source root
(`formulation`/`dataset` from `proposals/`, `experimental-design` from
`experiments/`, `implementation`/`results` from the target repository) is
measurably non-empty right now while the report claims that fact
UNSATISFIED with no evidence at all, `observe` refuses
`OBSERVATION_DISK_CONFLICT` naming the exact disagreement — never averaged
into a report that simply repeats the agent's claim. A root you omit is
never measured and never reconciled against; omitting `--implementation`
(no fixed default — its path varies per target) only skips reconciling
`implementation`/`results`, it never widens what the other two check.
`--proposals`/`--experiments` also have no default, deliberately: both are
long-lived, ongoing directories in this repository's own real layout,
routinely non-empty for reasons unrelated to any one paper's current
facts, so silently defaulting to them would reconcile against content that
says nothing about THIS observation.

## The redactor's own context: `packet`

Before delegating to the `redactor` agent, the orchestrating agent needs to
hand it a block's own contract prose, whatever reference material the
`style-sampler` might draw equivalent style from, and — for a
`transposition`-mode block — the block's own bound source sections
(`the-redactor-receives-the-section-it-must-transpose`) — `packet`
assembles exactly that, read-only.

```bash
.venv/bin/python skills/paper-writing/scripts/paper_cli.py packet \
    --section introduction --block block-1 --paper paper
```

| Verb | What it does | Refuses |
| --- | --- | --- |
| `packet --section <id> --block <id> [--sections <dir>] [--guidance <dir>] [--paper <dir>]` | Read-only: the block's own contract prose verbatim, a heading OUTLINE (`{title, level, byte_start, byte_end}`) per ingested paper under every `style-reference`-classed `guidance/` root, and — for a `transposition`-mode block only — its own bound source sections (`source_sections`, `{fact, lineage, title, path, byte_start, byte_end, text}`) plus a sibling `source_sections_state` | `GUIDANCE_MARKDOWN_UNREADABLE`, `PAPER_OUTSIDE_REPOSITORY`, plus (for a `transposition`-mode block, via corpus assembly) every code the `write` row's corpus-assembly column already lists — see "Corpus codes newly reachable from `packet`" below |

**The packet carries no reference prose at all — a structural leak guard,
never an instructional one.** Each `references` entry is an outline of
byte offsets into a reference paper's own markdown, never the span text
itself; a mutation that inlines span text instead of offsets is exactly
what turns this guard's own test red. The `style-sampler` agent reads this
outline, picks the heading it judges equivalent, and reads that span
itself from the real file — `packet` never resolves a span and never calls
`paper_style.resolve_style_set`, so there is exactly one resolution path
for a styled draft, not a second one this verb could drift from.

**An unclassified or empty `guidance/` tree is not a refusal.** A
`style-reference` root with no ingested papers under it, and a root the
registry classes as anything other than `style-reference`, both contribute
nothing to `references` — over the shipped corpus, where no category
folder is classified yet, `packet` against a real block returns
`references: []`; that is the honest, expected answer to "nothing has been
classified," not an error.

### `source_sections_state`: a closed four-value vocabulary, never a silent empty list

`packet` never refuses on account of a missing or unresolved bound section
— an absent or unreadable paper root, a block with no binding decided, and
a non-`transposition` block are all NAMED STATES, not refusals. `state` is
one of:

| `state` | meaning | `source_sections` | `reason` |
| --- | --- | --- | --- |
| `resolved` | every declared/recorded triple produced bytes | non-empty | `None` |
| `unbound` | the block names no `(fact, lineage, title)` triple at all — nothing to look for | `[]` | names the absence |
| `unmeasured` | a triple exists and could not be resolved — could not look; `unresolved` names each undecided triple | possibly partial | names the flag, root, or absent `mode` declaration that would answer it |
| `not-applicable` | the block's own mode is not `transposition` | `[]` | names the actual mode |

`unbound` and `unmeasured` both report an empty `source_sections`, but the
envelope is never the same: `state` alone distinguishes "this block has no
bound section" from "I could not look." An `argument`-mode block's other
three packet keys (`block`, `section`, `contract`, `references`) stay
byte-identical to a packet assembled with no `--paper` at all — the fifth
key only ever WIDENS what a `transposition`-mode block's packet carries,
never anything else.

### Corpus codes newly reachable from `packet` (`transposition`-mode blocks only)

`packet` assembles a corpus (`paper_graph.assemble_corpus`, read-only,
`enforce_bindings=False`) ONLY for a `transposition`-mode block — an
`argument`-mode or mode-less block's packet touches no corpus at all and
inherits nothing. For a `transposition`-mode block, seventeen shipped
codes become reachable from `packet` for the first time: `ID_COLLISION`,
`SOURCE_BINDING_CONFLICT`, `SOURCE_REVISIONS_UNDECLARED`,
`SECTION_NOT_IN_SOURCE`, `SECTION_TITLE_AMBIGUOUS`,
`INPUT_PARTITION_ABSENT`, `SPAN_NOT_IN_SOURCE`, `FACT_ROUTE_AMBIGUOUS`,
`FACT_PRODUCER_DUPLICATE`, `FACT_SELF_REQUIRED`, `FACT_PRODUCER_ABSENT`,
`PRODUCER_CHAIN_ABSENT`, `CHAIN_ROW_UNRESOLVED`, `CHAIN_ROW_UNBACKED`,
`BLOCK_SUBUNIT_UNDECLARED`, `UNIT_HEADING_AMBIGUOUS`, and
`DECLARATIONS_HAND_EDITED` — every one of these was already reachable from
`write`'s own corpus assembly before this capability existed; none is new
to the codebase (`design.md` category B). `PAPER_OUTSIDE_REPOSITORY` is
reachable on EVERY `packet` invocation, `transposition`-mode or not
(category C) — the one refusal `packet` gains that is an invocation
defect, never a state of the world.

**Widened blast radius, never new reachability.** `assemble_corpus` parses
every `sections/*.md` under `sections_dir`, not only the block's own file.
For a `transposition`-mode block, `MALFORMED_HEADER` and
`MALFORMED_FIGURE_OBLIGATION` can therefore be raised by an UNRELATED
section file's own defect — an accepted consequence of assembling one
corpus for the whole paper (`design.md` category D), never a defect of the
requested block's own binding. An `argument`-mode block's packet never
touches the corpus at all, so the identical unrelated defect never
surfaces for it.

## The whole cut is argued before any section is claimed: `separate` and `bind`

Two more verbs, from `source-section-binding` and `source-separation-review`.
Five `requires_facts` ids are BINDABLE — read from a real document on disk,
never declared by hand: `formulation` (a `proposals/` document),
`experimental-design` (an `experiments/` document), `dataset` (an
already-ingested paper under `guidance/`), and `implementation`/`results`
(a target code repository — always reported unmeasured for binding purposes,
because a repository is measured by RUNNING it, never read as prose for
section binding, regardless of what files it happens to contain). The first
three resolve to a real document (a `PROSE` root's current revision, or an
`INGESTED` root's own paper); a binding for either kind names which
section(s) of that document feed the block's claim.

**The refusal that starts the loop fires only at `write`.** Every read-only
verb — `contract`, `order`, `readiness`, `phases`, `plan` — tolerates a
document-rooted bindable fact with no recorded binding and reports nothing
about it. Only `write`'s own gate, immediately after its phase check, turns
the same gap into a refusal: `SECTION_BINDING_ABSENT`, naming the block, the
fact, every lineage that root currently carries on disk right now, and a
`bind` invocation to run.

**Recording that binding is a two-step loop, not the one command the first
refusal names.** Answering `SECTION_BINDING_ABSENT` with `bind` alone now
refuses a second time: for a document-rooted fact, `bind` demands a SETTLED
`separate` round that already argued this exact claim.

```
write refuses SECTION_BINDING_ABSENT
  │  names the block, the fact, and a bare `bind` invocation
  ▼
separate --proposal <path>
  │  scores the WHOLE cut against the document's own structure;
  │  refuses on any defect, naming every instance of every class present
  ▼  score 0 → the cut is SETTLED; the payload names the exact
  │  `bind` invocation for every assignment
bind --block <id> --fact <id> --lineage <lineage> --section <title> ...
  │  refuses BINDING_UNARGUED unless a settled round just named
  │  this exact (block, fact) with this exact title set
  ▼
write proceeds
```

`separate --proposal <path>` reads an agent-authored JSON file — never a
hand-edited `sections/*.md` header, which ships with the corpus and must
stay byte-identical, and never conversation prose an agent merely
paraphrases:

```json
{
  "lineage": "field-survey",
  "concedes_to_round": 1,
  "assignments": [
    {"block": "overview.block-a", "fact": "formulation",
     "sections": ["1. Background on widget metrics"]},
    {"block": "methods.block-b", "fact": "formulation",
     "sections": ["2. Alignment estimators", "3. Proposed alignment objective"]}
  ]
}
```

`lineage` and `assignments` are required; `concedes_to_round` is optional and
names the round number this cut abandons in favour of itself. Each
assignment's `sections` is a list of unique, non-empty title strings — a
bare string, an unknown top-level key, a duplicate `(block, fact)` pair
across assignments, or assignments resolving through more than one source
root all refuse `SEPARATION_REPORT_UNREADABLE` before anything is scored.

**Scoring, in one paragraph.** `separate` derives the document's own
claimable sections (every heading at the shallowest remaining level, once
any heading that wraps every other heading is eliminated — no heading-level
number is ever hardcoded), then scores the proposed cut against it:
**orphan** (a claimable title no assignment claims), **overlap** (a
claimable title two or more distinct blocks claim), **gap** (a title sitting
between two titles the same block claims, that the block itself does not
claim). A defect-free cut (total 0) is **settled**. A nonzero total raises
exactly ONE code by fixed precedence — overlap, then orphan, then gap — with
a detail naming every instance of every class present, never only the first
one found.

**Every structurally-valid round is recorded, whatever its score — settled
or not.** The record is the negotiation's own log, not a verdict: a losing
round stays readable so a later `concedes_to_round` can point back at it.
When `concedes_to_round` is given, `separate` recomputes BOTH totals from
disk — this cut's own score and the conceded round's score, from its stored
assignments, never trusting either round's stored `score` field — and
refuses `SEPARATION_CONCESSION_REGRESSED` if this cut scores strictly worse;
an equal total is accepted, never treated as a regression.

**`bind` demands that a settled round argued exactly this claim.** For a
document-rooted fact, `bind` refuses `BINDING_UNARGUED` unless a recorded
round: names the same root, lineage and document revision as resolved right
now; was scored against that document's exact bytes, digested at scoring
time (a newly published revision, or an in-place rewrite of the same
filename, both void the licence); settled at total 0; and named this exact
`(block, fact)` with this exact SET of titles — a subset or a superset of
the argued titles refuses just as a wrong block would. The refusal names
which of the four checks failed, both title sets when they disagree, and
the exact `separate --proposal <path>` invocation to run next.
`bind --reopen` is never guarded this way: withdrawing a binding never
needs an argument for the claim it is retracting.

**`separate` never records a binding, under any outcome.** A settled
(score-0) round only ever names the `bind` invocations it licenses; `bind`
remains the one place a binding becomes real, and it is still the only
verb `write`'s phase-gated corpus assembly ever reads back.

```bash
.venv/bin/python skills/paper-writing/scripts/paper_cli.py separate \
    --proposal proposal.json
.venv/bin/python skills/paper-writing/scripts/paper_cli.py bind \
    --block overview.block-a --fact formulation --lineage field-survey \
    --section "1. Background on widget metrics"
```

| Verb | What it does | Refuses |
| --- | --- | --- |
| `separate --proposal <path> [--sections <dir>] [--paper <dir>]` | Reads an already-authored whole-cut proposal, resolves every named title against the document's own structure and the assembled corpus, scores it, and records the round it just argued regardless of outcome. Never records a binding | `SEPARATION_REPORT_UNREADABLE`, `SEPARATION_SECTION_UNCLAIMABLE`, `SECTION_NOT_IN_SOURCE`, `SECTION_TITLE_AMBIGUOUS`, `SEPARATION_SECTION_OVERLAP`, `SEPARATION_SECTION_ORPHANED`, `SEPARATION_NOTATION_GAP`, `SEPARATION_ROUND_ABSENT`, `SEPARATION_CONCESSION_REGRESSED` |
| `bind --block <id> --fact <id> --lineage <lineage> --section <title> [--section <title> ...] [--sections <dir>] [--paper <dir>]` | Records which section(s) of a source document feed one block's own bindable requirement | `UNKNOWN_FACT`, `BINDING_FACT_NOT_BINDABLE`, `BINDING_LINEAGE_REQUIRED`, `BINDING_SECTIONS_REQUIRED`, `DECLARATION_FIXED`, `BINDING_UNARGUED` |
| `bind --block <id> --fact <id> --reopen` | Clears an already-recorded `(block, fact)` binding's fixed state instead of recording one — never gated by `BINDING_UNARGUED` | (none beyond `bind`'s own) |

**`--sections <dir>` here is the same corpus-directory override every other
verb carries** (default `sections/`) — it is never the list of section
titles a binding claims. That list is the repeatable `--section <title>`
(singular), a different flag entirely; do not confuse the two when reading
either command's own `--help`.

### Decision Gates (separate, bind)

| Situation | Action |
| --- | --- |
| `write` refuses `SECTION_BINDING_ABSENT` | Run `separate --proposal <path>` naming a whole cut for the missing claim's lineage, then the exact `bind` invocation the settled cut licenses |
| `separate` refuses `SEPARATION_SECTION_OVERLAP` / `SEPARATION_SECTION_ORPHANED` / `SEPARATION_NOTATION_GAP` | One code by fixed precedence overlap → orphan → gap; the detail names every instance of every class present — fix the cut and resubmit the same proposal file |
| `separate` refuses `SEPARATION_SECTION_UNCLAIMABLE` | A named title resolves to a real heading outside the claimable set (the document's own title, or a subsection), or the document's claimable set could not be measured at all — `--file`/`contract` the section, or re-check the title against the document's own headings |
| `separate` refuses `SEPARATION_ROUND_ABSENT` | `concedes_to_round` names a round with no record for this exact `(root, lineage, revision)` — check the round number and that the document revision has not moved |
| `separate` refuses `SEPARATION_CONCESSION_REGRESSED` | This cut recomputes worse than the round it concedes to; both totals are recomputed from disk, never trusted from either round's stored record — argue a cut that is at least as good |
| `bind` refuses `BINDING_UNARGUED` | No settled round licenses this exact `(block, fact)` claim, or its licence expired (a new revision or an in-place rewrite voids it) — the detail names which of the four checks failed and the exact `separate` invocation to run next |
| A binding's own fact resolves to an unmeasured root | `bind` records as it always did, no `separate` round required — the payload reports `separation: unmeasured(<reason>)`, never a silent pass over a document that was never there to argue about |

## The writer may assert only what it was given: `write`

Three channels feed one block's draft: **contract** (the block's own prose,
verbatim), **evidence** (the block's evidence set — resolved, cached
records, never invented), and **style** (whole equivalent blocks from
`style-reference`-classed `guidance/` folders — empty is valid, meaning
"no style channel at all"). Two audits check the result before it ever
reaches `main.tex`: **evidence-bound drafting**, which reconciles a binding
map against the emitted LaTeX so an unbound assertion is *detected*, never
merely instructed against; and **contract audit**, which evaluates the
contract's own `## Disqualifiers` bullets verbatim against the draft. `write`
is the judge that sequences both — **it never drafts and never audits
anything itself.**

```bash
.venv/bin/python skills/paper-writing/scripts/paper_cli.py write \
    --section materials-and-methods --block mm-proposal \
    --draft draft.json --audit audit.json --evidence evidence.json
```

| Verb | What it does | Refuses |
| --- | --- | --- |
| `write --section <id> --block <id> --draft <path> --audit <path> [--evidence <path>] [--style <path>] [--guidance <dir>] [--transcript <path>] [--grounding <path>]` | Before any draft/audit byte is read: refuses if this block's own phase wave is not yet writable, then refuses if this block's own section citation folder is not fully ready, then runs packet assembly for this block. Then reconciles the already-drafted, already-audited block against its real contract, evidence set and mode; substitutes on success, reports fired bullets on a first failure, refuses on exhaustion. `--style` records the sampler's account as `R` and runs the eight-token tripwire against the styled draft before `substitute`. For a `transposition`-mode block with at least one resolved bound section, `check_source_section_verbatim` then runs against the same draft, after the style tripwire and before `substitute`. `--grounding` records the section-grounding-auditor's account and reconciles it against every subject sentence, after the verbatim check and before `substitute` | `PHASE_NOT_READY`, `CITATION_FOLDER_ABSENT`, `CITATION_NOT_INGESTED`, `CITATION_FOLDER_UNCLASSIFIED`, `GUIDANCE_MARKDOWN_UNREADABLE`, `MODE_ABSENT`, `EVIDENCE_SET_REQUIRED`, `UNBOUND_SENTENCE`, `BINDING_ORPHANED`, `EVIDENCE_ID_UNKNOWN`, `FACT_NOT_LICENSED`, `STRUCTURAL_CARRIES_CLAIM`, `MODE_VIOLATION`, `DISQUALIFIERS_ABSENT`, `VERDICT_MISSING`, `VERDICT_BULLET_UNKNOWN`, `AUDIT_EXHAUSTED`, `SPAN_NOT_IN_SOURCE`, `STYLE_OVERLAP`, `SOURCE_SECTION_VERBATIM`, `GROUNDING_ACCOUNT_ABSENT`, `GROUNDING_SENTENCE_UNKNOWN`, `GROUNDING_VERDICT_MISSING`, `SECTION_UNSUPPORTED_CLAIM` |

**The phase gate stops the write path, it does not merely report it.**
Unit 6 wired `PHASE_NOT_READY` onto the read-only `phases` verb alone;
`write` never consulted the same wave computation, so a later wave could be
written before an earlier one existed. `write` now resolves this exact
block's own wave via the SAME gate `phases` uses and refuses
`PHASE_NOT_READY` before `--draft`/`--audit` are even read off disk and
before `write_block`'s own attempt ledger is touched — a block never burns
a judge-cycle attempt on a refusal that has nothing to do with its draft.

**Citations must be ready before a block is drafted**
(`no-citation-before-its-paper-is-ingested`, item 3). Immediately after the
phase gate, still before `--draft`/`--audit` are read, `write` reads this
block's own `citations` regime off its real contract and, for anything
other than `none`, checks its section's own citation folder
(`guidance/<section-id>/`, item 1 above): the folder must exist
(`CITATION_FOLDER_ABSENT`, naming the section id and telling the operator
to download the cited PDFs there); every PDF already placed there must be
ingested — a loose PDF still sitting directly in the folder refuses
`CITATION_NOT_INGESTED`, naming it by filename and pointing at the
`paper-ingestion` skill; and the folder itself must carry a real
classification, not `unclassified` (`CITATION_FOLDER_UNCLASSIFIED`). A
`none`-regime block cites nothing and is never gated by any of this, no
matter what `guidance/<section-id>/` looks like — a guard that blocks
every block regardless of its own contract would be as wrong as one that
blocks none. Only then does `write` run `assemble_packet` for this exact
block (`packet`'s own assembly, above) as a gate in its own right: a
`style-reference` root whose ingested markdown cannot be read refuses
`GUIDANCE_MARKDOWN_UNREADABLE` here, before the draft/audit stage is ever
reached.

### The shuttle procedure — this CLI never invokes an agent

No module under `scripts/` imports `subprocess`, `os.system`, `os.popen`,
`os.exec*`, or `multiprocessing` (an AST scan asserts it, with exactly one
named, currently-unused exception reserved for a sibling skill's own
`latexmk` integration — see `tests/test_paper_writing.py`,
`NoSubprocessScanTests`). `write` cannot run unattended, by construction:

1. The orchestrating agent (you) assembles the four redactor inputs and
   delegates to the `redactor` agent, which returns
   `{"latex": ..., "bindings": [...]}`. Write that JSON to a file.
2. The orchestrating agent also delegates to the `contract-auditor` agent
   and writes its JSON verdict envelope to a second file.
3. Run `write --draft <path> --audit <path>`. On `"status": "written"` the
   block is done. On `"status": "audit-fired"`, hand the returned `fired`
   bullets and spans back to the redactor as explicit feedback and re-draft
   **exactly once** — a third submission under the same contract/evidence/
   mode refuses `AUDIT_EXHAUSTED`.

**Measure this before delegating (redactor/contract-auditor):** confirm the
contract's own `sections/*.md` file and its evidence set are both already
readable; an agent asked to draft or audit against a source it cannot read
cannot distinguish "nothing to cite" from "cannot be checked."

The style channel follows the same shuttle shape: the orchestrating agent
delegates to the `style-sampler` agent per `style-reference`-classed
`guidance/` folder, and its verified, recorded account becomes `R` — the
only material any later overlap check may compare a styled draft against.
An all-`noEquivalent` style set reports the style channel `unmeasured`
(`paper_write.style_channel_report`), not a silent pass: an unmeasured
register/overlap check proves nothing about whether style leaked.

**Measure this before delegating (style-sampler):** confirm the guidance
registry has already classed at least one folder `style-reference`; an
agent asked to sample against a registry that classes nothing cannot
distinguish "no style channel wanted" from "nothing to sample yet."

### `mode`: how a block is licensed to argue

`sections/*.md` headers may now declare a `mode` — `transposition` or
`argument` — at section level (the default) or block level (overriding
it), transcribed from the contract's own prose exactly like an `after`
edge (`{"value": ..., "source": {"file", "quote"}}`). A header declaring
neither is schema-valid — ten of the ten shipped contracts carry `mode`
today — but `write` refuses `MODE_ABSENT` rather than assuming one for any
block it resolves to `None`.

`transposition` admits only `fact`/`structural`/`resolution`-class
evidence bindings — a block reporting an existing result. `argument`
additionally admits `discovery`-class evidence — a block making a claim
about the field. Binding a `discovery`-class record under `transposition`
refuses `MODE_VIOLATION`.

### `requires_facts` / `requires_declarations`: the requirement must name its own sentence

Every `requires_facts` / `requires_declarations` entry is now a rich
`{value, source: {file, quote}}` object — the same shape `after` and
`mode` already carry — never a bare id string. `paper_contract.parse`
enforces the shape (`value` a string in the closed vocabulary, `source` a
non-null `{file, quote}` object); `paper_graph.assemble_corpus` then
verifies `source.quote` is a literal, whitespace-collapsed, markdown-
emphasis-stripped substring of `source.file`'s own prose body (self-file
or cross-file, exactly like an `after` edge), unconditionally, on every
command that assembles the corpus. An entry whose quote cannot be found
refuses `SPAN_NOT_IN_SOURCE` naming the block and the fact or declaration
id; a bare string now refuses `MALFORMED_HEADER` at parse, before the
corpus-wide gate ever runs — the half-migrated, untranscribed state is
structurally unrepresentable, not merely detected.

`BlockRecord.requires_facts` / `.requires_declarations` stay plain tuples
of ids downstream — `paper_contract.requirement_values()` is the single
accessor deriving them, so nothing but `paper_contract.py` itself ever
subscripts a parsed block's `["requires_facts"]` / `["requires_declarations"]`
directly.

Two requirements the operator ruled spurious were removed rather than
transcribed, never merely left bare: `experimental-setup.es-assessment`'s
`dataset` (already carried by its own `after` edge to `es-dataset`) and
`title-and-keywords.keywords`'s `contributions` (already reached
transitively through the seven `introduction.*` blocks). The full
evidence and ruling live in `openspec/changes/the-requirement-names-the-
sentence-that-demands-it/unanchored-requirements.md`.

### The style-leak proof: register rises, overlap does not

Style must not carry content. Proven, not asserted, by drafting one block
three times against identical contract, evidence and mode — twice with an
empty style set (`A`, `B`) and once with the real one (`S`) — then checking
two measurements:

- **Register distance**, `d(S,{A,B})`, must exceed `d(A,B)` — the A/B
  control is a required argument to `paper_leak.register_distance_holds`,
  never optional, so the control cannot be silently dropped.
- **N-gram overlap**, `overlap(S,R) <= max(overlap(A,R), overlap(B,R))` —
  self-calibrating against whatever chance floor two unstyled drafts
  already share, with `paper_leak.relative_overlap_holds` taking no
  threshold parameter at all.

Independent of both: any shared run of **eight or more** normalized tokens
between a styled draft and a sample in `R` refuses `STYLE_OVERLAP` by name
— a tripwire, not the proof; tuning it can never move the guarantee above,
because the guarantee's own function reads no threshold. Both measurements
read `R` alone, never a reference file directly.

### The transposition-fidelity guard: a same-author threshold, self-calibrated

A `transposition`-mode block must carry its bound source section into the
paper's own style, never copy it. `paper_leak.check_source_section_verbatim`
is a SIBLING of the tripwire above — its own refusal, `SOURCE_SECTION_
VERBATIM`, reusing the same shipped `overlap_against_set`/`tripwire_spans`
primitives, never widening `check_tripwire` itself (that would compare
against a reference file read directly, exactly what `Requirement: Overlap
Reads Only The Recorded Sample Set` forbids).

The eight-token tripwire above is calibrated against an INDEPENDENT
published paper's prose, where any shared clause is already suspicious. A
bound source section is the SAME author's own earlier text about the same
work, where reusing terms, quantities and formal statements at a far higher
baseline is ordinary — so this guard self-calibrates per block, per
section, against the one text already known to be legitimate: the block's
own contract prose. `threshold = max(overlap_against_set(contract_prose,
[section]), SOURCE_RUN_BACKSTOP)`, `SOURCE_RUN_BACKSTOP = 16`, a RULING not
a measurement. There is no upper clamp on the floor: a contract that
already carries a long run from its own bound section has licensed that
run, and the inertness this creates for that block is always visible — the
floor and threshold are reported in every `write` envelope's
`sourceFidelity`, per section, whether or not the check refused, never
inferred from the absence of a refusal.

Runs inside `write_block`, after the style tripwire above and before
`substitute`, so a draft failing both checks always names `STYLE_OVERLAP`
first. Guarded on `contract.mode == paper_vocabulary.MODE_TRANSPOSITION` —
derived from the contract on disk, never a block id or a hand-maintained
list; an `argument`-mode block is out of scope this change and is never
checked, regardless of overlap.

### The transposition-grounding guard: containment, not copying

A `transposition`-mode block must assert only what its bound source section
carries. The verbatim check above judges **copying**; it stays silent about
a draft that paraphrases freely while asserting something the section never
states. `paper_grounding.reconcile_support` is a fourth sibling in `write`'s
judge chain, judging **containment** instead: a subject sentence — a
`fact:`-bound sentence whose fact also names a section the block resolves as
bound — must be supported by that section's own bytes. The orchestrating
agent also delegates to the `section-grounding-auditor` agent, which returns
one `supported`/`unsupported`/`undecidable` verdict per subject sentence,
quoting a span from the bound section for every `supported`. Write that JSON
to a file and run `write --grounding <path>`.

**Measure this before delegating (section-grounding-auditor):** confirm the
block's own bound source sections have already resolved (`packet`'s own
`source_sections`/`source_sections_state`, above); an agent asked to judge
support against a section that never resolved cannot distinguish "nothing to
ground" from "cannot be checked."

**The permissive verdict carries the burden of proof — the opposite of
`contract-audit`'s own asymmetry.** There, the *blocking* verdict (`fires`)
must quote a span. Here `supported` is what lets a sentence reach
`substitute`, so `supported` is the one `write` requires to be grounded: its
cited span must be byte-present in the re-derived text of the section
belonging to that sentence's own fact — never the account's own copy of
either. A `supported` verdict with an empty or absent span, or one grounded
only in a *different* fact's section, downgrades to `undecidable` rather
than being trusted. `unsupported` needs no span to refuse
`SECTION_UNSUPPORTED_CLAIM`, naming the block, the fact, the lineage, the
section title and the sentence — demanding a span for a claim the section
never makes would demand proof of a negative.

`undecidable` — returned directly or produced by a downgrade — never blocks
on its own; a mechanism that blocks on its own uncertainty trains the agent
to guess. But the two are counted and reported SEPARATELY in
`sourceGrounding` (`subjects`, `decided`, `undecidable`, `downgraded`), so an
honest abstention and a downgraded, unfounded `supported` stay
distinguishable from the envelope alone. `status` is `"measured"` only when
`decided > 0`, else `"unmeasured"` — reported for a block with no subjects
at all, and separately for one whose subjects are all undecidable, the two
cases distinguished by the reported `subjects` count. **Falsifier:** over ten
or more recorded real `write` runs against genuine document-rooted bindings,
if any block reaches `written` with `downgraded > 0`, or with `subjects > 0`
and `decided == 0`, this no-ratio-threshold ruling is wrong and a blocking
rule over these counts must be added.

That falsifier cannot be run today — no real `document`-rooted binding exists
on disk anywhere, which is precisely why no number was picked — so the
obligation is carried by a tripwire rather than by this paragraph.
`GroundingThresholdObligationTests` (`tests/test_paper_writing.py`) reads the
recorded bindings and passes only while there are none. The day `bind` records
one for real it goes red and names what is then owed: accumulate the runs, and
either discharge the ruling with measured counts or replace it with the
blocking rule it asks for. A document cannot notice its own precondition
changing; a test can.

An `evidence:`-bound sentence and a `structural` sentence are never subjects
— held by their own separately shipped mechanisms — and neither is any
sentence in an `argument`-mode block, the same `contract.mode` derivation
`MODE_ABSENT` and the verbatim check above both already rest on. This is a
sibling check, never an extension of the verbatim check or the style
tripwire: it takes an agent account as input and refuses on semantics,
something neither of those two functions' contracts admit. Runs inside
`write_block`, after the verbatim check above and before `substitute`, so a
draft failing both checks always names `SOURCE_SECTION_VERBATIM` first —
copying is decided before meaning.

## A diagram that compiles, or says why: `render` and `place`

Three more modules, from `a-diagram-that-compiles-or-says-why`:
`paper_latex.py` (the sole holder of `subprocess` in this skill — an AST
scan, `NoSubprocessScanTests`, holds every other script to zero),
`paper_figure.py` (source/manifest layout, stop A, the compile pipeline,
the repair-budget ledger), and `paper_obligation.py` (components,
separation, caption, mandatory — pure functions over the contract's own
`figure:` declaration, never a hardcoded section or block id).

Each diagram id resolves to `paper/Figures/<id>.tex` (standalone TikZ, one
`% node: <label>` comment per component), a sibling `<id>.diagram.json`
manifest (`components`, `encodings`, `caption`), and — once compiled —
`<id>.pdf` beside them. `main.tex` receives the figure only through the
existing `substitute` verb's `\includegraphics`; no TikZ byte ever enters
`main.tex`.

| Verb | What it does | Refuses |
| --- | --- | --- |
| `render --figure-id <id> [--paper <dir>]` | Compiles `<id>.tex` standalone via exactly one `latexmk` call, cross-checks the manifest both directions, and scans stop A before ever spawning the compiler | `DIAGRAM_SOURCE_ABSENT`, `MANIFEST_SOURCE_MISMATCH`, `DIAGRAM_PLOTS_DATA`, `LATEX_TOOLCHAIN_ABSENT`, `LATEX_LOG_ABSENT`, `LATEX_OUTCOME_UNEXPLAINED`, `LATEX_PACKAGE_ABSENT`, `REPAIR_BUDGET_SPENT` |
| `render --figure-id <id> --section <section-id> --block <id> [--sections <dir>] [--paper <dir>]` | The same compile, and then the full obligation suite (components — only when the block declares `components_from`, excludes, caption, mandatory, cross-diagram separation) against the block's own `figure:` declaration | adds `MALFORMED_FIGURE_OBLIGATION`, `COMPONENT_MISMATCH`, `COMPONENTS_FACT_UNRESOLVED`, `COMPONENTS_FACT_NOT_A_LIST`, `EXCLUDED_COMPONENT`, `SHARED_COMPONENT`, `CAPTION_INCOMPLETE`, `MANDATORY_DIAGRAM_ABSENT` |
| `render --figure-id <id> --acknowledge-reset [--paper <dir>]` | The explicit operator acknowledgement that clears a spent ledger — compiles nothing, never combined with a compile in the same call | (none beyond `render`'s own) |
| `place --figure-id <id> --pdf <path> --provenance <path> [--paper <dir>]` | Places an already-measured figure's PDF — compiles nothing, requires a provenance record naming the run that produced it | `DIAGRAM_SOURCE_ABSENT` (reused: the named artifact this call needs is absent) |
| `figure optimize --figure-id <id> [--in-place \| --output <path>] [--strip-comments] [--no-compile] [--paper <dir>]` | Rewrites one diagram's TikZ source: prunes the libraries it can **prove** unused, adds the ones it detects as missing, factors repeated option lists into one `\tikzset`, then compiles the candidate and commits it only on a `success` verdict. `background=2pt` headers, relative positioning, and `% node:` markers are preserved by construction | `DIAGRAM_SOURCE_ABSENT`, `DIAGRAM_PLOTS_DATA`, `MANIFEST_SOURCE_MISMATCH`, `LATEX_TOOLCHAIN_ABSENT`, `LATEX_PACKAGE_ABSENT`, `LATEX_OUTCOME_UNEXPLAINED` |
| `figure optimize --file <path.tex> [--strip-comments]` | Dry run: prints the optimized candidate for one source path and writes nothing (no manifest, so no cross-check applies) | `DIAGRAM_SOURCE_ABSENT` |
| `figure audit --figure-id <id> --section <id> [--block <id>] [--sections <dir>] [--paper <dir>]` | Compares the manifest's declared components — **not** every `\node{}` string — against the section prose, and the `components_from` fact's list against both. Emits `verdict` (`pass`/`fail`/`unmeasured`) plus `unmatched_nodes`, `missing_pipeline_steps`, `label_mismatches`, `warnings`, `remediation`, and writes `figure_audit.json` beside the figure's ledger | `DIAGRAM_SOURCE_ABSENT`, `SECTION_CONTRACTS_UNREADABLE`, `SECTION_UNKNOWN`, `BLOCK_ABSENT` |
| `figure audit --file <path.tex> --manifest <path.json> --section <id> [--block <id>]` | The same audit for a figure outside `paper/Figures/`; `--file` requires `--manifest` | as above |

**`figure optimize`'s two guards run even under `--no-compile`.** The manifest
cross-check and stop A are pure text checks, independent of the compiler, so
the shortcut skips the compiler and nothing else; a candidate failing either is
discarded with the original left byte-identical. A repairable compile failure
is likewise an ordinary outcome, not a refusal: the call returns `status: ok`
with `verdict: "rolled_back"` and the diagnostics. A library `optimize` cannot
recognize it never removes — it only prunes what it can prove unused.

**`figure audit`'s findings are a verdict, never a refusal.** A `fail` is a
successful call (`status: ok`, `verdict: fail`), the same way `render` treats a
repairable compile failure as the loop's ordinary cost. `unmeasured` exists so
"could not check" never reads as "checked and clean": a figure whose contract
declares no `components_from`, or a call that omits `--block`, reports
`unmeasured` rather than a vacuous pass.

**A repairable failure is an ordinary outcome, not a refusal.** `render`
returns `"status": "ok"`, `"verdict": "failure"` with the parsed
diagnostics and `attemptsUsed`/`budgetRemaining` for a compile that failed
but is still within its four-attempt budget — spending an attempt is the
loop's ordinary cost. Only the fifth attempt for an id refuses
`REPAIR_BUDGET_SPENT`, naming every distinct diagnostic and source digest
already tried; the budget survives edits between attempts (keyed to the id
alone, never reset by a new digest) and is cleared only by an explicit
operator acknowledgement (deleting the ledger file — `paper/.paper-writing/
figures/<id>/ledger.json` — **is** that acknowledgement, made explicit
rather than pretended-secure). A missing `.sty` refuses
`LATEX_PACKAGE_ABSENT` and spends nothing: redrawing cannot fix an absent
package.

**The data-figure boundary, measured, not assumed.** Stop A
(`paper_figure.scan_data_boundary`) refuses `DIAGRAM_PLOTS_DATA`
pre-compile on a plotting package, a `\begin{axis}`, an external table
read, an `\input`/`\include` escaping `paper/Figures/`, or an embedded
coordinate series over the illustrative threshold. Stop B is the compile's
own sandbox (`cwd` = `paper/Figures/`, `-outdir` = scratch, child env
carrying `openin_any=p`/`openout_any=p`/`shell_escape=f`) — **measured
against a real TeX Live 2026 install, not merely declared**: `shell_escape=f`
genuinely blocks `\write18`, but `openin_any=p` does **not** block a literal
absolute-path `\input{...}` on this engine (an explicit absolute path never
goes through kpathsea's search algorithm at all). Stop A's pre-compile
source scan is therefore the primary, load-bearing defense against that
exact vector — never something resting on the env var alone. Placing a
measured figure is `place`, entirely outside the compile path: no
`latexmk` call, no ledger, no stop-A scan.

**Obligations are read, never known.** A block's `figure:` declaration
(`ordered`, `excludes`, `caption_enumerates`, `caption_decodes`,
`mandatory` — all five required; `components_from` OPTIONAL,
`paper_contract.py`'s `_parse_figure`) is read entirely off the contract;
`paper_obligation.py`'s pure functions (`check_components`,
`check_excluded`, `check_shared_components`, `check_caption`,
`check_mandatory`) check it against a manifest, never against a hardcoded
section or block id. When `components_from` names a fact, the Components
Check's expected list is DERIVED — never operator-supplied — from that
fact's own declared resolution (`declare --fact <id> --value
'["a", "b"]'`, read back through `paper_declarations.read_fact`), refusing
`COMPONENTS_FACT_UNRESOLVED` when the fact was never declared and
`COMPONENTS_FACT_NOT_A_LIST` when its resolution does not parse as a JSON
array of strings. `components_from`'s named fact must equal the FULL
expected list by contract — section 01's methods diagram IS the
contribution list, so `components_from: contributions` alone suffices. A
block whose diagram is a composite crossing over several categories of
content, none of which alone is the full list (section 02's closing
diagram: data, methods, axes, metrics, qualitative instruments, the
repetition unit), declares NO `components_from` at all — the Components
Check simply does not run for it, honestly, rather than being wired to one
fact's partial value and silently inverting (measured directly by
`a-diagram-that-compiles-or-says-why`'s own corrective verify: the prior
`components_from: dataset` reading refused a prose-compliant diagram and
passed a degenerate one). Deleting a `figure:` key removes the whole
obligation with zero code changed. A block whose contract states the
synthesis artefact may be a diagram **or** a table (section 05's block 5)
carries no diagram obligation at all when the operator's choice leaves no
`<id>.tex` — a legal table triggers nothing.

**Drafting the diagram itself delegates to the `diagram-author` agent.**
It authors the `.tex`/`.diagram.json` pair and drives its own `render`
loop up to the repair budget, stopping at `REPAIR_BUDGET_SPENT` or an
unrecoverable refusal for the operator to resolve — it never clears a spent
ledger itself.

**Auditing a diagram against its own prose delegates to the `figure-auditor` agent.**
It runs `figure audit` and reports that JSON as the authoritative
semantic verdict, and measures whether the visual half (overlaps, legibility,
out-of-bounds text) is answerable by running `figure-review probe` and
quoting its exit — bounding those dimensions to the `figure-review` skill's
checklist when the probe resolves a rasterizer link, and reporting them
`unmeasured` quoting the probe's own refusal code when it does not — and
checks typographic parity between the figure's preamble and the paper's own
font setup. It never repairs the figure and never reports a visual verdict it
did not measure.

**Measure this before delegating (figure-auditor):** confirm the block's
`figure:` declaration is readable (`contract --file <path>`) and that the
figure's `<id>.tex` and `<id>.diagram.json` both exist; an agent asked to audit
a figure it cannot read cannot distinguish "clean" from "unreadable."

**Measure this before delegating (diagram-author):** confirm the block's
`figure:` declaration is already readable (`contract --file <path>`) and,
when it declares a `components_from` fact, that fact is already declared
as a JSON array of strings (`plan` reports it fixed; `declare --fact <id>
--value '["a", "b"]'` if not) — an agent asked to draft a diagram against
an obligation it cannot read cannot distinguish "no components yet" from
"cannot be checked."

## The couplings hold, or they do not: `verify`

Ten contracts state obligations that span two sections. A finished
`paper/main.tex` can satisfy every section alone and still be incoherent
across them — `verify` is a read-only report over seven checks: five
cross-section couplings, citation integrity, and contract currency. It
never writes a byte, under any input, including every refusal path, and it
never repairs anything it finds — `skill-audit`'s own shape, reused here.

```bash
.venv/bin/python skills/paper-writing/scripts/paper_cli.py couplings --file couplings.json
.venv/bin/python skills/paper-writing/scripts/paper_cli.py verify
```

| Verb | What it does | Refuses |
| --- | --- | --- |
| `couplings --file <path\|->` | Validates a JSON couplings record's shape and writes it WHOLE, atomically, to `paper/couplings.json` — never merged with what was there before | `COUPLINGS_INPUT_UNREADABLE`, `COUPLINGS_RECORD_MALFORMED` |
| `verify [--sections <dir>]` | Read-only report: `contribution-list`, `chain`, `gap`, `artefacts`, `future-work`, `citations`, `contract-currency`, `figure-semantics` | `DECLARATION_RECORD_ABSENT` |

**Three values, never two.** Every check's own `verdict` is `pass`, `fail`
or `unmeasured` — `unmeasured` is never folded into `pass`. Two new modules
carry this: `paper_coupling_evidence.py` (every disk read `verify`
performs — named to avoid colliding with `paper_evidence.py`, the
claim<->source evidence module `no-claim-without-a-source-that-holds-it`
already ships) and `paper_verify.py` (the eight pure checks and the report
they assemble; an AST lock and an executed before/after content manifest
both hold it, and `paper_coupling_evidence.py`, to writing nothing).

**The eighth check, `figure-semantics`, reads a dict and imports nothing.**
`paper_verify.py` is held to an import allowlist of exactly `re`, so it can
neither parse JSON nor reach the auditor. The invocation therefore lives in
`paper_coupling_evidence.gather()` — the module that already owns every disk
read — which runs `paper_figure_audit.audit_semantics` over each figure and
stores the **already-computed report dict** on `Evidence.figure_semantics`.
`paper_verify.py` maps that dict's verdict into its own closed
`pass|fail|unmeasured` vocabulary and never touches a `Path`-typed field. No
figure at all reports `unmeasured`, reason `NO_FIGURE_DECLARED`; a figure the
audit could not compare reports `unmeasured`, reason
`FIGURE_SEMANTICS_UNMEASURED`. The dependency direction is one-way:
`paper_coupling_evidence.py` may import `paper_figure_audit.py`; the auditor
may not import the reader or `paper_verify.py`.

**`verify` reads its own declaration record, `paper/couplings.json` —
read-only, untracked like `main.tex` itself.** `couplings` is its producer:
`{"blocks": {...}, "facts": {"contributions": [...], "limitations": [...]},
"chain": {"links": [{"word": ...}, ...]}, "artefacts": {"setup_cells":
[...], "results_artefacts": [...]}, "future_work": {"directions": [{"id":
..., "limitation": ..., "cite_key": ...}, ...]}}` — every field but
`blocks` optional, `paper_couplings.validate_couplings_shape` checked
BEFORE a byte is written, so a malformed shape is diagnosed at write time
rather than surfacing later as a confusing `unmeasured`. Unlike `refs.bib`
(never hand-typed, above), this content is legitimately hand-authored: the
operator's own judgment about the paper's structure, not something a
connector resolves. An entirely absent or empty record refuses
`DECLARATION_RECORD_ABSENT` for the whole run: nothing is known about any
coupling, so per-check `unmeasured` across the board would bury the fact
that nothing was checked at all. One block missing its own entry inside an
otherwise-present record is narrower — `unmeasured`, reason
`BLOCK_NOT_DECLARED`, for the couplings that depend on that block only; the
run still proceeds and every other check still reports a real verdict.
Which blocks a check reads is itself derived, never hardcoded or
record-declared: the set is every block whose contract `requires_facts`
names the relevant fact, read through `paper_contract.parse` over
`sections/*.md` headers. An unreadable or headerless corpus reports
`unmeasured`, reason `SECTION_CONTRACTS_UNREADABLE`; a fact no block
requires reports `unmeasured`, reason `NO_BLOCK_REQUIRES_FACT` — never zero
comparisons reported as agreement.

**Contract currency reads the `provenance` region `the-paper-carries-its-
own-decisions` already writes at `substitute --contract` time — `verify`
never writes it.** An absent or empty region reports check `contract-
currency` alone `unmeasured`, reason `CONTRACT_RECORD_ABSENT`, and the run
still exits `0`: every other check still reports. Editing one block's
guidance changes the whole-file contract hash and flags every block of
that section stale, not only the edited one — inherited from that region's
own accepted over-reporting tradeoff, never narrowed here.

**Coupling 3 (the gap) can never read `pass`.** Its own vocabulary is the
single value `unmeasured`, reason `ASSISTED_READING_REQUIRED` — `verify`
never guesses and never gates on "the same thing at different depths."
What it publishes instead: both blocks' closing sentences verbatim with
byte offsets, both front lists with counts, and three mechanical
sub-results (both closings present, fronts equal, front counts equal) as
named booleans — evidence a human can act on without making the reading
themselves.

### Decision Gates (verify)

| Situation | Action |
| --- | --- |
| `verify` refuses `DECLARATION_RECORD_ABSENT` | `paper/couplings.json` is missing or empty — run `couplings --file <path>` with a record naming at least `blocks`, then run `verify` again |
| `couplings` refuses `COUPLINGS_RECORD_MALFORMED` | The given record's shape does not match what `verify`'s checks read (`blocks` empty/absent, or a known field wrong-typed) — fix the record and resubmit; nothing was written |
| A check reports `unmeasured`, reason `BLOCK_NOT_DECLARED` | Only the block(s) that check depends on have no entry in the record; every other check still ran |
| A check reports `unmeasured`, reason `SECTION_CONTRACTS_UNREADABLE` | The `sections/` corpus itself could not be read — `contract`/`order` first, then re-run `verify` |
| Coupling `gap` reports `unmeasured` | This is unconditional, not a defect — read the published closings and front lists yourself; `verify` never closes this one |
| `contract-currency` reports `unmeasured`, reason `CONTRACT_RECORD_ABSENT` | No block was ever written with `--contract`; every other check still reports |

## The lifecycle: `reuse` and `exhaustion`

Operator-ruled, 2026-09-19 (`a-leftover-paper-is-offered-before-it-is-lost`):

```
downloaded -> ingested -> candidate for every claim with no record yet
                              |
                   validate -> holds          -> cited, counts toward coverage
                            -> does-not-hold  -> still a candidate for the others
                              |
        when EVERY open claim has its does-not-hold -> exhausted -> operator deletes
```

**The skill NEVER deletes on its own.** `reuse` and `exhaustion` are both
read-only reports over `paper_lifecycle.py`; the operator deletes with
their own explicit shell command. Neither verb needed `main.tex` open at
all — every read here goes through `paper_evidence.read_records`/`read_all_
records` (the JSONL store under `paper/.paper-writing/evidence/`) and
`paper_guidance`'s own registry, so neither raises a code of its own —
`PAPER_ABSENT`/`GUIDANCE_OUTSIDE_REPOSITORY`/etc. are already classified.

```bash
.venv/bin/python skills/paper-writing/scripts/paper_cli.py reuse --block intro.claim
.venv/bin/python skills/paper-writing/scripts/paper_cli.py exhaustion
```

| Verb | What it does | Refuses |
| --- | --- | --- |
| `reuse --block <id> [--paper <dir>] [--guidance <dir>] [--min-sources <n>]` | Read-only: for `--block`'s own OPEN claims (recorded, not yet `min_sources`-satisfied), names which already-ingested, `evidence`-classed papers carry no verdict yet for each one — what stops the operator re-downloading a paper already on disk | none of its own |
| `exhaustion [--paper <dir>] [--guidance <dir>] [--min-sources <n>]` | Read-only, CORPUS-WIDE: every `evidence`-classed ingested paper's exhaustion state against every open claim in the WHOLE corpus (never one section's blocks alone) — `exhausted` when a `does-not-hold` covers every one; otherwise `active`, naming every claim still without a verdict from that paper | none of its own |

**A `does-not-hold` never masks a `holds`.** A paper carrying a `holds`
verdict anywhere is reported `active`, reason `"holds"`, regardless of what
every other claim decided about it — deleting a cited paper would break
that citation. **An empty open-claim set never means "exhausted."** Nothing
tried yet is not evidence of uselessness, so a freshly-ingested, never-
tested paper reports `active`, reason `"no-open-claims"`, not vacuously
`exhausted`.

**Corpus-wide, never per section.** `exhaustion`'s open-claim set unions
every block's own evidence store (`paper_evidence.read_all_records`),
because `validate --source-md` was never section-scoped to begin with — a
paper ingested under any `evidence`-classed `guidance/` root is already
citable from any block. Evaluating "uncited" within one section's blocks
alone would propose deleting a paper another section still needs; this is
exactly the mistake the operator caught before either verb was built.

### Decision Gates (reuse, exhaustion)

| Situation | Action |
| --- | --- |
| `reuse --block <id>` reports `openClaims: []` | Either nothing has been asked about this block yet, or every claim already asked already has `min_sources` distinct `holds` sources — check `validate`'s own coverage report to tell which |
| `exhaustion` reports a paper `active`, reason `"holds"` | Never a candidate for deletion — it is cited; `remaining` is reported empty on purpose |
| `exhaustion` reports a paper `active`, reason `"no-open-claims"` | Nothing has been tried against it corpus-wide yet — not a defect, and never "exhausted" by an empty set |
| `exhaustion` reports a paper `active`, reason `"remaining-claims"` | `remaining` names every claim, corpus-wide, this paper still carries no verdict for — the operator's own next search |
| `exhaustion` lists a paper under `exhausted` | Every corpus-wide open claim already carries this paper's own `does-not-hold` — the operator deletes it by hand; this skill never does |

## Refusal roster

Every refusal is `Refused(code, detail)`, classified invocation-defect
(clear it by changing the invocation alone) or work-state (something on
disk needs a human's decision first). The roster is derived from every
module `paper_cli.py` itself imports, by walking their source
(`tests/test_paper_writing.py`, `reachable_paper_refusal_codes` — the same
shape `proposal-implementation`'s own roster derivation uses) and held to
it in both directions: nothing reachable ships unclassified, and nothing
classified here is unreachable. The module list is derived too
(`paper_cli_imported_modules`), from `paper_cli.py`'s own `import`
statements rather than a hand-listed tuple — a hand-listed tuple went stale
silently once, the day this skill grew past its first three scripts, and
every refusal in the two new modules shipped unrostered until a later
change re-derived it. Adding a `Refused` anywhere in a module `paper_cli.py`
imports, without updating `paper_cli.REFUSAL_CLASSIFICATION`, fails that
test on its own — and so does adding a module `paper_cli.py` never imports
but expecting its refusals to be reachable through the front door.
