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

**The evidence is the final, approved experiment only.** The paper describes
and discusses the experiments, models and results that ended as definitive and
approved, never the iteration that led to them. When you assemble a block's
`--evidence`, take results only from the full experiment the operator approved
(the folder with `Experimental_AGREED.md` and its complete
`Results/discussion.json`, with `G-NOVELTY` approved) and the design only from
the latest protocol revision; leave out the proof of concept, pilot and
preliminary runs, hyperparameter-search trials (`Results/hpo/`, beyond the
final configuration they chose), superseded protocol or proposal revisions and
every round of deliberation. A results or discussion block discusses only what
a figure or table of the paper shows. A limitation names a restriction of the
models and tests the paper reports, never of an intermediate test that did not
become a definitive experiment; a future-work direction answers one of those
limitations and carries a reference that supports it. `verify` flags a
sentence that narrates the iteration (`iteration-history`) and a future-work
sentence without a citation (`future-work-uncited`).

```bash
.venv/bin/python skills/paper-writing/scripts/paper_cli.py write \
    --section materials-and-methods --block mm-proposal \
    --draft draft.json --audit audit.json --evidence evidence.json
```

| Verb | What it does | Refuses |
| --- | --- | --- |
| `write --section <id> --block <id> --draft <path> --audit <path> [--evidence <path>] [--style <path>] [--guidance <dir>] [--transcript <path>] [--grounding <path>] [--expect-digest <sha256>]` | With `--expect-digest`, first refuses `BLOCK_CHANGED_SINCE_READ` when the block's recorded digest is no longer the one read, and checks it again at `substitute`. Before any draft/audit byte is read: refuses if this block's own phase wave is not yet writable, then refuses if this block's own section citation folder is not fully ready, then runs packet assembly for this block. Then reconciles the already-drafted, already-audited block against its real contract, evidence set and mode; substitutes on success, reports fired bullets on a first failure, refuses and escalates on exhaustion. `--style` records the sampler's account as `R` and runs the eight-token tripwire against the styled draft before `substitute`. For a `transposition`-mode block with at least one resolved bound section, `check_source_section_verbatim` then runs against the same draft, after the style tripwire and before `substitute`. `--grounding` records the section-grounding-auditor's account and reconciles it against every subject sentence, after the verbatim check and before `substitute` | `BLOCK_CHANGED_SINCE_READ`, `PHASE_NOT_READY`, `CITATION_FOLDER_ABSENT`, `CITATION_NOT_INGESTED`, `CITATION_FOLDER_UNCLASSIFIED`, `GUIDANCE_MARKDOWN_UNREADABLE`, `MODE_ABSENT`, `DRAFT_NOT_ENGLISH`, `DRAFT_PLACEHOLDER_TEXT`, `DRAFT_BOLD_LEAD_IN`, `DRAFT_SECTION_HEADING`, `EVIDENCE_SET_REQUIRED`, `UNBOUND_SENTENCE`, `BINDING_ORPHANED`, `EVIDENCE_ID_UNKNOWN`, `FACT_NOT_LICENSED`, `DECLARATION_NOT_LICENSED`, `STRUCTURAL_CARRIES_CLAIM`, `DECLARATION_UNDECLARED`, `DECLARATION_VALUE_ABSENT`, `DECLARATION_CARRIES_CLAIM`, `MODE_VIOLATION`, `DISQUALIFIERS_ABSENT`, `VERDICT_MISSING`, `VERDICT_BULLET_UNKNOWN`, `AUDIT_EXHAUSTED`, `SPAN_NOT_IN_SOURCE`, `STYLE_OVERLAP`, `SOURCE_SECTION_VERBATIM`, `GROUNDING_ACCOUNT_ABSENT`, `GROUNDING_SENTENCE_UNKNOWN`, `GROUNDING_VERDICT_MISSING`, `SECTION_UNSUPPORTED_CLAIM` |
| `write --section <id> --block <id> --draft <path> --precheck [--evidence <path>] [--style <path>] [--guidance <dir>] [--expect-digest <sha256>]` | Runs every deterministic check `write` runs, in its order, before any judge is spawned: the digest, phase and citation gates, packet assembly, language, lead-ins, headings, the evidence audit and binding, the disqualifier extraction, table lint, the style tripwire and the verbatim-from-source check. Reads no judge account: `--audit` and `--grounding` beside `--precheck` are invocation errors (exit 2). Writes no attempt ledger, substitutes nothing. Returns `"status": "precheck-passed"` with `attempt` (the attempt the next `write` would be), `disqualifiers` (every bullet the contract judge must rule on), `rowCount` (contract 05's measured synthesis-table finding, or `null`), `groundingSubjects` (the sentences the grounding judge must rule on; empty means no grounding judge is needed), `tableLint` and `language` | the same codes as `write` before its contract audit, plus `DISQUALIFIERS_ABSENT`, `STYLE_OVERLAP`, `SOURCE_SECTION_VERBATIM`, and `AUDIT_EXHAUSTED` when the block already escalated to the operator |

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

**A table that shrinks to fit is a warning, never a refusal.** Every `write`
envelope (`written` and `audit-fired`) carries `tableLint`
(`paper_latex.table_lint_report`): the body size read from `main.tex`
(`print_scale.body_font_pt`), the printed range (`minPrintedPt` 0.70 × body,
`maxPrintedPt` 0.90 × body), and one finding per
`\resizebox` or `adjustbox` width scaling of a tabular
(`table-scaled-to-width`), `\scalebox`/`adjustbox scale=` below 0.85
(`table-scaled-below-floor`), and `\tiny`/`\scriptsize`/`\footnotesize`/`\small`
(or `\fontsize{<pt>}`) inside a table that prints below the floor
(`table-font-below-floor`), and a size inside a table that prints above the
cap, or a table that declares no size and so prints at the body size
(`table-font-above-cap`, command `\normalsize (default)`). It warns
for the same reason an `Overfull` box is a non-blocking diagnostic: the source
cannot prove what prints (the body size may be a fallback), and the compiled
manuscript's QA measures it. Contracts 02 and 03 carry the rule
(`## Tables stay inside the text block`).

### The shuttle procedure — this CLI never invokes an agent

No module under `scripts/` imports `subprocess`, `os.system`, `os.popen`,
`os.exec*`, or `multiprocessing` (an AST scan asserts it, with exactly one
named, currently-unused exception reserved for a sibling skill's own
`latexmk` integration — see `tests/test_paper_writing.py`,
`NoSubprocessScanTests`). `write` cannot run unattended, by construction:

1. The orchestrating agent (you) runs `packet` and spawns the `redactor`
   agent (subagent name `redactor`, never a generic agent) with the packet
   for this one block. The redactor checks its draft against every
   disqualifier bullet that applies to the block before returning, reports
   which it checked, and returns `{"latex": ..., "bindings": [...]}`. Write
   that JSON to a file.
2. Run `write --draft <path> --precheck --expect-digest <sha256>` (same
   `--evidence`/`--style` as the real call), passing the block digest
   `status` listed before step 1 (record it then, every time you delegate a
   draft). Every deterministic refusal surfaces here, before any judge
   runs; it spends no attempt. Fix the draft with the redactor and precheck
   again until it passes. `precheck-passed` lists the `disqualifiers` the
   contract judge rules on and the `groundingSubjects` the grounding judge
   rules on.
3. Spawn the judges **in parallel, on the same draft**: the
   `contract-auditor` agent always, and the `section-grounding-auditor`
   agent too when `groundingSubjects` is not empty. Write each JSON
   envelope to its own file.
4. Run one `write --draft <path> --audit <path> [--grounding <path>]
   --expect-digest <sha256>`. The block is written only when every judge
   passes: the contract audit fires on no bullet and every grounding
   subject is supported or undecidable. A block another session wrote in
   the meantime refuses `BLOCK_CHANGED_SINCE_READ` before any gate runs or
   any attempt is spent. On `"status": "written"` the block is done.
5. On `"status": "audit-fired"`, or a refusal after the contract audit that
   only a re-draft answers (`STYLE_OVERLAP`, `SOURCE_SECTION_VERBATIM`,
   `SECTION_UNSUPPORTED_CLAIM`), hand ALL of it back to the redactor as
   explicit feedback: every `fired` bullet and span, and the whole
   `grounding` record — every subject sentence's verdict under `verdicts`
   and the refusal detail that names every unsupported sentence, never only
   the first (the `audit-fired` envelope carries it; after a refusal, read
   it from the ledger, `paper/.paper-writing/attempts/<block>.json`, keys
   `refusal` and `grounding`). Re-draft **exactly once**, then
   repeat steps 2 to 4 (a re-draft makes both earlier verdicts stale, so
   both judges run again).
6. When the re-draft still fires, or still refuses after the contract
   audit, `write` records the ledger's terminal `escalated` state with the
   judges' verdicts (`paper/.paper-writing/attempts/<block>.json`) and
   refuses `AUDIT_EXHAUSTED`. **Stop and ask the operator**, showing the
   fired bullets, their spans and every grounding verdict. No further
   re-draft runs, every later `write` or `--precheck` under the same
   contract, evidence set and mode refuses `AUDIT_EXHAUSTED`, and nothing
   passes automatically. A changed contract, evidence set or mode is a new
   attempt key and opens a fresh budget; only the operator decides it.

An incomplete judge account (`VERDICT_MISSING`, `VERDICT_BULLET_UNKNOWN`,
`GROUNDING_ACCOUNT_ABSENT`, `GROUNDING_SENTENCE_UNKNOWN`,
`GROUNDING_VERDICT_MISSING`) spends no attempt: ask the same judge again for
the missing verdicts, never re-draft for it.

**The contract judge rules on every bullet.** No contract marks a
disqualifier bullet as belonging to one block (a bullet such as "Block 3 in
other than two paragraphs" names its block in prose only), so `write`
extracts every bullet of the section and `VERDICT_MISSING` forces a verdict
on each. A bullet about another block is `clear` for this draft unless the
draft itself breaches it; the judge never skips it.

**Measure this before delegating (redactor/contract-auditor):** confirm the
contract's own `sections/*.md` file and its evidence set are both already
readable; an agent asked to draft or audit against a source it cannot read
cannot distinguish "nothing to cite" from "cannot be checked."

**On a harness with no Task-tool delegation** (OpenCode projects these
agents as `mode: subagent` per `OPENCODE.md`, Antigravity reads them from
`.agents/agents/` per `.agents/AGENTS.md`, and Pi reads its projection only
when the third-party `pi-subagents` package is installed per
`.pi/APPEND_SYSTEM.md`; a Pi session without that package, or any session
whose agent is not registered, has none):
run this stretch in-process, as one step, in the same order, holding to the
same measure-before-delegating gate before starting. The tool boundary the
agents would have enforced (`redactor` and `contract-auditor` cannot write
to disk) becomes the orchestrator's own discipline to hold, not a
structural guarantee — treat any action that would have needed a
scoped-out tool as a stop, not a workaround.

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

**On a harness with no Task-tool delegation** (OpenCode projects these
agents as `mode: subagent` per `OPENCODE.md`, Antigravity reads them from
`.agents/agents/` per `.agents/AGENTS.md`, and Pi reads its projection only
when the third-party `pi-subagents` package is installed per
`.pi/APPEND_SYSTEM.md`; a Pi session without that package, or any session
whose agent is not registered, has none):
run this stretch in-process, as one step, in the same order, holding to the
same measure-before-delegating gate before starting. The tool boundary the
agent would have enforced (`style-sampler` cannot write to disk) becomes
the orchestrator's own discipline to hold, not a structural guarantee —
treat any action that would have needed a scoped-out tool as a stop, not a
workaround.

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

### The binding map: four kinds

The redactor hands `write` one binding per sentence it drafted, each exactly
one of:

| Binding | The sentence carries | Licensed by |
|---|---|---|
| `evidence:<record-id>` | what that evidence record supports | the block's evidence set (`--evidence`) |
| `fact:<fact-id>` | an operator-declared or produced fact | the block's `requires_facts` |
| `declaration:<id>[,<id>...]` | the recorded value of one or more declarations, copied verbatim | the block's `requires_declarations`; `ai-usage` for the blocks whose packet carries the `ai_usage` record (`back-matter.bm-ai-use-declaration`, `experimental-setup.es-training-details`) |
| `structural` | nothing: transitions, pointers, summaries | always; no numeral, `\cite`, comparative or named object outside the contract prose |

`declaration:` exists for the blocks whose contract demands tokens no other
kind may carry: the grant code and the funder (`bm-funding`), the repository
URL, commit and access date (`bm-code-availability`,
`bm-data-availability`), the ethics approval code, and the framework release
and tool names of the AI-use declaration. Record a value with `declare
--declaration <id> --value <v>`; `packet` hands the block's recorded values
to the redactor under `declarations` (`{id: value | null}`), and the
`ai_usage` record under `ai_usage` (its `tool_names` are the printed harness
names). One sentence may name several ids (`declaration:grant-title,grant-code`
for a funding entry that names its project and its code together).

`write` judges every `declaration:` sentence against the values it names,
after `resolve_bindings` and `type_structural`, in this order:

1. every id is licensed, or it refuses `DECLARATION_NOT_LICENSED`;
2. every id has a recorded value, or it refuses `DECLARATION_UNDECLARED`
   naming the `declare` invocation that records it;
3. for every id, the sentence prints at least one component of its value
   verbatim, or it refuses `DECLARATION_VALUE_ABSENT`. The components of a
   recorded value are the whole value, each parenthetical group's text, and
   each `;`- or newline-separated part of the rest
   (`"https://x/y; commit 06faa71; checked 2026-11-13"` -> `https://x/y`,
   `commit 06faa71`, `checked 2026-11-13`); for `ai-usage` they are the
   framework's name, URL and release, the tool ids and printed names, the
   phase labels and agents, the drafting and auditing agents and the drafted
   sections (`paper_ai_usage.declarable`). The comparison reads printed
   text: accent macros (`m\'aquina`), `\url{}`/`\href{}{}`, TeX dashes and
   quotes, `~` and escaped specials are reduced on both sides, and a
   component matches only between alphanumeric boundaries;
4. outside math, every alphanumeric run holding a digit is a run of a named
   value (for `ai-usage`, its phase counts too; a recorded ISO date
   `2026-11-13` also holds `13`, `11`, `November` and `Nov`, so it may be
   printed `13 November 2026`), and every capitalised word that does not open
   the sentence or follow a `.`/`:` (a bold label such as
   `\textbf{Funding.}`) is in the contract prose or a run of a named value
   (any case), and no comparative (`better`, `outperforms`, ... as
   `structural` refuses them) appears unless a named value holds it, or it
   refuses `DECLARATION_CARRIES_CLAIM`. The contract prose never licenses a
   numeral: its example release is not this paper's release. Capitalised
   words the contract prose names are licensed as written, so a tool the
   contract lists only as an example still reads as licensed here; the
   contract-auditor's AI-usage bullet is what holds the declaration to the
   record.

`declaration:` is admitted in every mode, like `fact:` and `structural`, and
is never a grounding subject.

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

**On a harness with no Task-tool delegation** (OpenCode projects these
agents as `mode: subagent` per `OPENCODE.md`, Antigravity reads them from
`.agents/agents/` per `.agents/AGENTS.md`, and Pi reads its projection only
when the third-party `pi-subagents` package is installed per
`.pi/APPEND_SYSTEM.md`; a Pi session without that package, or any session
whose agent is not registered, has none):
run this stretch in-process, as one step, in the same order, holding to the
same measure-before-delegating gate before starting. The tool boundary the
agent would have enforced (`section-grounding-auditor` cannot write to
disk) becomes the orchestrator's own discipline to hold, not a structural
guarantee — treat any action that would have needed a scoped-out tool as a
stop, not a workaround.

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
