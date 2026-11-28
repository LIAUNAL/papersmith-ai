---
name: paper-writing
description: "Trigger: build or re-enter the paper/ tree: scaffold, record declarations, write one named block of main.tex, resolve citations and refs.bib, verify, compile diagrams, review, adapt to a venue or translate. Fail-closed CLI (paper_cli.py)."
---

# Paper Writing

**Scope.** Create or re-enter the paper/ tree; write one named block of paper/main.tex without touching another byte; read what sections/*.md declares about itself; see which writing phase is unlocked and open the section/block skeleton once; assemble a block's redactor packet (contract prose, reference heading outlines, bound source sections); record or reopen a declaration or fact and see the paper's plan; resolve a citation against Asta/OpenAlex/Crossref/arXiv and rebuild refs.bib; validate a citation's verdict and placement; judge a drafted, audited block against its evidence and contract; compile a standalone diagram and prove it against the contract's figure: obligation; check the cross-section couplings, citation integrity and contract currency; or adapt the manuscript to a chosen journal (venue select, requirements, acquire, diff, plan, approve, build under paper/venues/<slug>/, never touching the canonical main.tex). Stdlib-only, keyless by default, fail-closed CLI (paper_cli.py).

`paper/main.tex` is edited one named block at a time, byte-for-byte. A block
is delimited by two LaTeX-comment marker lines carrying its id and a sha256
digest of its own body; this engine never rewrites a byte outside the block
it was asked to change, and proves that on every call rather than assuming
it — before a single byte reaches disk. The one documented exception is the
document frame: `skeleton --frame` writes the preamble, `\begin{document}`,
the section headings, the bibliography lines and `\end{document}` around the
blocks of a frameless file, once, moving blocks whole and proving that every
block keeps its body and digest.

## What this skill ships today

Thirty-four verbs, wired into one front door (`scripts/paper_cli.py`):
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
exhaustion state -- lists only, never deletes), `figure optimize`/`figure provenance`/`figure audit` (the TikZ optimizer, the manifest's script-and-data record, and the figure-prose semantic auditor), and the `venue` group
(`select`, `requirements`, `acquire`, `diff`, `plan`, `approve`, `build`, `status`, `list` -- adapting the
manuscript to a chosen journal under `paper/venues/<slug>/`; "Venue adaptation" in `references/venue.md`), and
`reorder` (moves canonical back-matter blocks into the order `verify`'s
`back-matter-order` check expects; "Putting back matter in order" in `references/verify.md`),
`bib` (`refs.bib` management, never hand-typed), `ai_audit` and `humanize`
(the writing-style measure and the invariant-preserving revision of one
block), `translate` (`plan`, `store`, `build`, `audit`, `status`: the
fidelity-gated Spanish translation under `paper/translations/<lang>/`) and
`review` (records one round of the `paper-reviewer`'s final review in
`.papersmith/paper_review.json`). To the
substitution engine, block ids
stay opaque strings — shape only (`[A-Za-z0-9._-]+`), no meaning. The
contract reader is what says which ids exist, what each requires, and where
in the document they belong, entirely over in `sections/*.md`.
`declare`/`plan` are what records the operator-supplied declarations and
fact resolutions those requirements name, and reports where the paper
stands against all of it in one read-only call — see "The paper's own
decisions" in `references/declarations.md`.

**This CLI is no longer offline end to end.** `resolve` is the one path
that reaches the network — stdlib `urllib` only, keyless by default, against
Ai2's Asta, OpenAlex, Crossref and arXiv, behind a `papersmith.yaml` role the
operator can empty. The operator's own Asta and OpenAlex keys (saved in smith
ui's Doctor → API keys, or with `smith keys set`) are read from their per-user
store, sent only to their own service, and never written anywhere. Every other
verb remains exactly as offline as before; `resolve` refuses by name
(`RESOLVER_UNREACHABLE`, `RESOLVER_REFUSED`, `DISCOVERY_UNAVAILABLE`,
`RESOLVER_ROLE_EMPTY`) rather than silently returning an empty result.
`resolve --references` is the one exception to that refusal: it records an
unreachable key as `unreachable` in its sidecar, so offline work carries on, and
only an emptied role refuses.

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

**Keep the digest you read.** The `digest` `status` lists for a block is its
base: pass it back as `--expect-digest <sha256>` to `substitute`, `write` or
`humanize --apply`, and the write refuses `BLOCK_CHANGED_SINCE_READ`,
writing nothing, when another session wrote that block after you read it.
Without the flag nothing is compared, exactly as before; with it, a stale
copy can never silently replace newer prose.

## The four verbs

| Verb | What it does | Refuses |
| --- | --- | --- |
| `scaffold` | Creates `paper/main.tex` (empty), `paper/refs.bib`, `paper/Figures/`, `paper/.gitkeep` if absent. Idempotent — a second run never touches an existing byte, hand edits included. The document frame is written by `skeleton --frame`, not here | `PAPER_OUTSIDE_REPOSITORY`, `PAPER_NOT_A_DIRECTORY`, `SCAFFOLD_ENTRY_WRONG_TYPE` |
| `status` | Read-only block table: id, digest, byte region, per block | `PAPER_ABSENT`, `TEX_UNDECODABLE`, `MARKER_MALFORMED`, `BLOCK_DUPLICATED`, `BLOCK_UNPAIRED`, `BLOCK_NESTED` |
| `open --block <id> (--after <id> \| --at-end)` | Installs an EMPTY begin/end pair at the named position. Never writes content — the first write to a new block is always `open` then `substitute` | adds `BLOCK_DUPLICATED`, `ANCHOR_ABSENT`, `OPEN_POSITION_REQUIRED`, `OPEN_POSITION_CONFLICT` |
| `substitute --block <id> (--body <path\|-> \| --adopt) [--expect-digest <sha256>]` | Replaces one block's body, or (`--adopt`) accepts the on-disk body as the new baseline without changing it. `--expect-digest` is the block digest `status` listed when you read it; the write refuses when the block's recorded digest has moved since | adds `BLOCK_ABSENT`, `BLOCK_HAND_EDITED`, `BLOCK_CHANGED_SINCE_READ`, `CONTENT_CARRIES_MARKER`, `NOTHING_TO_ADOPT`, `SUBSTITUTE_MODE_REQUIRED`, `ADOPT_BODY_CONFLICT`, `SUBSTITUTION_NOT_LOCAL`, `TEX_MOVED` |

Every JSON reply carries `"status": "ok"` (exit 0) or `"status": "refused",
"code": "<CODE>", "detail": "<why>"` (exit 2). A successful `substitute`
always adds `"rendering": "unproven"` — this engine has no LaTeX toolchain
and makes no claim the document compiles or that the change looks right on
the page. That is a separate, unbuilt capability.

**There is no `--force`.** Nothing here ever discards a human's on-disk text
in favor of an incoming body. The only exit from a hand-edited block is
`--adopt`, which re-baselines the digest and leaves the body untouched.

Section reference: `references/drafting-standards.md`. Read it before drafting, auditing or reviewing any block: the presentation mode, the author metadata, and the Introduction and Related Work structure.

## When a delegated agent cannot be spawned

Each stretch this skill delegates is defined in full by its own agent file:
`.claude/agents/ai-auditor.md`, `.claude/agents/contract-auditor.md`, `.claude/agents/diagram-author.md`,
`.claude/agents/figure-auditor.md`, `.claude/agents/figure-visual-reviewer.md`,
`.claude/agents/insumos-observer.md`,
`.claude/agents/paper-reviewer.md`, `.claude/agents/redactor.md`, `.claude/agents/section-grounding-auditor.md`,
`.claude/agents/style-sampler.md`, `.claude/agents/translation-style-reviewer.md`, `.claude/agents/translator.md`,
`.claude/agents/venue-adapter.md`. When an agent cannot be spawned — the
harness has no sub-agent mechanism, the agent is not registered in this
session, or the spawn itself fails — perform the stretch inline: read that
agent's definition file and follow it as written, from the beginning it states
to the end it states, holding any gate this skill sets before the stretch, and
returning the report shape it specifies. Its `tools:` line still bounds the
stretch: an act that would need a tool outside that list is a stop, not a
workaround. Say in the reply that the stretch ran inline and why the agent
could not be spawned.

An auditor run inline (`ai-auditor`, `contract-auditor`, `section-grounding-auditor`,
`figure-auditor`, `figure-visual-reviewer`, `paper-reviewer`, `venue-adapter`) is not independent of the session that drafted what it
judges. The verbs still reconcile its account against the real bytes, but say
in the reply that the audit was not separated from the draft.

## Decision Gates

| Situation | Action |
| --- | --- |
| `status` reports `BLOCK_HAND_EDITED` | Read the on-disk body before deciding. `--adopt` accepts it as the new baseline; a plain `substitute` still refuses until you do |
| `open` refuses `ANCHOR_ABSENT` | The named `--after <id>` has no pair yet — `status` first, then either open that id or pick `--at-end` |
| `open` refuses `OPEN_POSITION_REQUIRED` / `OPEN_POSITION_CONFLICT` | Exactly one of `--after <id>` / `--at-end` is required, never zero, never both |
| `substitute` refuses `SUBSTITUTE_MODE_REQUIRED` / `ADOPT_BODY_CONFLICT` | Exactly one of `--body <path\|->` / `--adopt`, never zero, never both |
| `substitute` refuses `CONTENT_CARRIES_MARKER` | The replacement body itself contains a line starting `%% paper-writing block` — strip it, this grammar cannot nest |
| `substitute`/`open` refuses `SUBSTITUTION_NOT_LOCAL` | The in-memory candidate would have changed a byte outside the target block; nothing was written. This should never fire from ordinary use — report it as a defect if it does |
| `substitute`, `write` or `humanize --apply` refuses `BLOCK_CHANGED_SINCE_READ` | Another write landed on that block after you read it; the detail names both digests. Run `status`, read the current body, rebuild the replacement on it and pass the new digest. Never drop `--expect-digest` to force the write |
| `substitute`/`open` refuses `TEX_MOVED` | Something else wrote to `main.tex` between this call's read and its write. Re-run the command against the current file — never retry blind against stale offsets |
| Any command refuses `PAPER_ABSENT` | Run `scaffold` first |

## Where each section lives, and who reads it

This file is the core: what ships, how every read starts, the four verbs,
the delegation fallback, the Decision Gates and the refusal roster. Every
other section lives, word for word, in one file under `references/`, and a
`Section reference:` line stands where it stood and says when to read it.
Read a reference when its line's condition holds, not the whole set before
starting. A delegated agent reads this core's "Every read starts the same
way" and "The four verbs" (the JSON reply every verb returns) and then only
the slices its row below names; hand it those paths with its inputs.

| Agent | The stretch | Measure before delegating | Slices it reads |
| --- | --- | --- | --- |
| `redactor` | `write`'s shuttle procedure delegates to the `redactor` agent for one block's draft | **Measure this before delegating (redactor/contract-auditor)**, in `references/write.md` | `references/drafting-standards.md`, `references/packet.md`, `references/written-in-english.md`, `references/write.md`, `references/figure-rules.md` |
| `contract-auditor` | `write`'s shuttle procedure delegates to the `contract-auditor` agent for the draft's verdict envelope | **Measure this before delegating (redactor/contract-auditor)**, in `references/write.md` | `references/drafting-standards.md`, `references/section-contract.md`, `references/write.md` |
| `section-grounding-auditor` | a `transposition`-mode draft delegates to the `section-grounding-auditor` agent | **Measure this before delegating (section-grounding-auditor)**, in `references/write.md` | `references/packet.md`, `references/write.md` |
| `ai-auditor` | the style audit delegates to the `ai-auditor` agent | No **Measure this before delegating** paragraph is written for this stretch; the agent's own "You begin" line is its start | `references/prose-pass.md` |
| `style-sampler` | the style channel delegates to the `style-sampler` agent per `style-reference` folder | **Measure this before delegating (style-sampler)**, in `references/write.md` | `references/packet.md`, `references/write.md` |
| `insumos-observer` | observing the observable facts delegates to the `insumos-observer` agent | No **Measure this before delegating** paragraph is written for this stretch; the agent's own "You begin" line is its start | `references/declarations.md`, `references/observe.md` |
| `translator` | the translation delegates to the `translator` agent, one block or fragment at a time | **Measure this before delegating (translator/translation-style-reviewer)**, in `references/translate.md` | `references/translate.md` |
| `translation-style-reviewer` | the translation review delegates to the `translation-style-reviewer` agent | **Measure this before delegating (translator/translation-style-reviewer)**, in `references/translate.md` | `references/translate.md` |
| `diagram-author` | drafting a diagram delegates to the `diagram-author` agent | **Measure this before delegating (diagram-author)**, in `references/diagram-author-gate.md` | `references/render.md`, `references/figure-rules.md`, `references/figure-obligations.md`, `references/diagram-author-gate.md`; its own guides `skills/paper-writing/references/contribution-diagram.md`, `skills/paper-writing/references/data-acquisition-diagram.md` and `skills/paper-writing/references/pictograms.tex` |
| `figure-auditor` | auditing a diagram against its own prose delegates to the `figure-auditor` agent | **Measure this before delegating (figure-auditor)**, in `references/figure-obligations.md` | `references/render.md`, `references/figure-obligations.md`; the visual checklist is `skills/figure-review/SKILL.md` |
| `figure-visual-reviewer` | judging a rendered diagram by eye delegates to the `figure-visual-reviewer` agent | **Measure this before delegating (figure-visual-reviewer)**, in `references/figure-obligations.md` | `references/render.md`, `references/figure-obligations.md` |
| `venue-adapter` | the venue stretch delegates to the `venue-adapter` agent | **Measure this before delegating (venue-adapter)**, in `references/venue.md` | `references/venue.md` |
| `paper-reviewer` | reviewing the whole paper delegates to the `paper-reviewer` agent | **Measure this before delegating (paper-reviewer)**, in `references/paper-review.md` | `references/paper-review.md` |

Section reference: `references/safety-net.md`. Read it before any write: what protects `paper/` without git, why I/O is binary, and what a block id may be.

Section reference: `references/section-contract.md`. Read it before reading a contract with `contract`, `readiness`, `order` or `phases`, and before judging a block against its contract.

Section reference: `references/skeleton.md`. Read it before opening the section and block structure with `skeleton`.

Section reference: `references/declarations.md`. Read it before `declare` or `plan`, or before observing or recording a fact a contract requires.

Section reference: `references/mark.md`. Read it before recording a source root's revision rule or a `guidance/` folder's class with `mark`.

Section reference: `references/resolve.md`. Read it before resolving a citation, building `refs.bib`, or validating a citation's verdict and placement.

Section reference: `references/observe.md`. Read it before delegating the observation of the observable facts or running `observe`.

Section reference: `references/packet.md`. Read it before assembling a block's redactor packet with `packet`.

Section reference: `references/separate-bind.md`. Read it before arguing the cut with `separate` or recording a binding with `bind`.

Section reference: `references/written-in-english.md`. Read it before drafting, revising or translating any prose of the paper.

Section reference: `references/prose-pass.md`. Read it before `ai_audit` or `humanize`.

Section reference: `references/write.md`. Read it before running `write` or delegating a draft, its contract audit, its grounding audit or a style sample.

Section reference: `references/render.md`. Read it before `render`, `place` or any `figure` verb.

Section reference: `references/figure-rules.md`. Read it before drafting a block that presents comparisons, distributions, results or a caption.

Section reference: `references/figure-obligations.md`. Read it before placing a figure, checking a `figure:` obligation, or delegating a diagram's audit or visual review.

Section reference: `references/paper-review.md`. Read it before delegating the whole-paper review or recording a round with `review`.

Section reference: `references/diagram-author-gate.md`. Read it before delegating a diagram's drafting.

Section reference: `references/verify.md`. Read it before `verify` or `reorder`.

Section reference: `references/lifecycle.md`. Read it before `reuse` or `exhaustion`.

Section reference: `references/venue.md`. Read it before any `venue` verb or delegating the venue stretch.

Section reference: `references/translate.md`. Read it before any `translate` verb or delegating the translation or its review.

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
