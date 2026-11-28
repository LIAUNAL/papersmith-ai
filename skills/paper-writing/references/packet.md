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

**The AI-use record (`ai_usage`).** The packet of
`back-matter.bm-ai-use-declaration`, and of
`experimental-setup.es-training-details` (which holds the Methods sentence),
carries one more key, `ai_usage`, built read-only by
`paper_ai_usage.build` when the packet resolves a paper: `pipeline` (per
phase, from `command_center.ai_history.build_ai_usage`: the agent roles, the
harnesses whose chat sessions worked on it, and the counts of sessions,
commands, operator follow-ups, approvals, agent replies, revisions,
decisions and errors; `model` is always `null`, the operator supplies tool
versions), `drafted` (every written block, drafted by `redactor` and audited
by `contract-auditor`, with its write attempts and whether it has an
evidence ledger), `tools`, `code_or_experiments_by_agents` and
`methods_sentence_required` (true when the proof-of-concept and experiments
phase shows agent sessions), and `venues` (each selected venue's publisher
family and where it places the AI-use declaration and funding:
`paper_venue.back_matter_placement`). An unreadable source degrades to
`{"status": "unavailable"}`; the key never refuses, and every other block's
packet keeps its previous keys. The declaration states what the record shows
(`sections/10-back-matter.md`, "AI-use declaration").

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
