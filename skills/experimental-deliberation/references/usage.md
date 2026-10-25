# Experimental Deliberation — examples and help

See [SKILL.md](../SKILL.md) for the tutor-role conditioning, the canonical form, and the discipline around external validation. This page is worked examples only: checking `STATUS`, creating v1, resolving a locus, building `resolvedDecisions`, and the preview → accept → publish cycle.

Every request below is sent through this skill's own launcher, which is what supplies the domain profile:

```bash
node skills/experimental-deliberation/cli.mjs
```

None of it requires `ANTHROPIC_API_KEY` or any model configuration — no call on this path reaches a network or a model. The response shapes shown are the ones the engine's own public projection emits; treat field names as exact and field values as illustrative.

## Checking `STATUS` before deciding a base

Read-only, keyless, no model call. Run it before reading a source, loading a document, or touching anything in `experiments/`:

```bash
node skills/experimental-deliberation/cli.mjs '{ "operation": "STATUS" }'
```

Against an `experiments/` directory holding a managed `v01`/`v02` pair, one managed-looking-but-unmarked `v03` (missing the artifact marker, so it does **not** count as managed), and an unrelated `draft-plan.md`:

```json
{
  "status": "ok",
  "operation": "STATUS",
  "managedRevisions": [
    { "filename": "experiments-domain-shift-baseline-sweep-v01.md", "lineage": "domain-shift-baseline-sweep", "revisionNumber": 1, "isLatest": false },
    { "filename": "experiments-domain-shift-baseline-sweep-v02.md", "lineage": "domain-shift-baseline-sweep", "revisionNumber": 2, "isLatest": true }
  ],
  "latest": "experiments-domain-shift-baseline-sweep-v02.md",
  "multipleActive": false,
  "candidates": [],
  "nonManagedFiles": ["draft-plan.md", "experiments-domain-shift-baseline-sweep-v03.md"]
}
```

Pass `sourceFilename` to classify one candidate base in the same call:

```bash
node skills/experimental-deliberation/cli.mjs '{ "operation": "STATUS", "sourceFilename": "experiments-domain-shift-baseline-sweep-v01.md" }'
```

```json
{ "...": "same fields as above, plus:", "sourceClassification": "OLDER_MANAGED", "newerRevisionNumbers": [2] }
```

`sourceClassification` is one of `LATEST`, `OLDER_MANAGED` (with `newerRevisionNumbers`), `UNMANAGED`, or `NOT_FOUND`. `STATUS` never mutates: no file in `experiments/` is created, moved or changed by it. A confirmed backup move is something *you* do afterwards with a plain file move. `STATUS` also answers on a project with no `experiments/` directory yet — the exact pre-creation state `CREATE_INITIAL_REVISION` exists for — with an empty inventory. A directory that exists but cannot be read fails closed with an error instead of reporting "empty."

## Creating the first managed version

Only when `STATUS` reports zero managed revisions. Both required sources must exist on disk first:

```
guidance/data-paper/<paper-name>/<paper-name>.md    (required)
proposals/                                          (required — at least one document)
guidance/paper-guide/<name>/<name>.md               (optional)
```

Because [v1 is checked, not exempt](../SKILL.md#creating-v1-checked-by-the-same-gate-as-every-successor), the idea text itself must already carry both of this domain's declared labels, `**Dataset:** …` and `**Validation scheme:** …`, and **each on its own line**: both rules match at line start, so folding a declaration into the middle of a sentence does not satisfy them.

```bash
node skills/experimental-deliberation/cli.mjs '{
  "operation": "CREATE_INITIAL_REVISION",
  "instruction": "Domain shift baseline sweep. Testing whether the proposed adaptation term improves held-out accuracy under domain shift without target labels. Claim C1: the method needs no target labels. Claim C2: the gain survives a reduced labelled budget.\n\n**Dataset:** domain-shift-benchmark (standard train/validation/test split as distributed).\n\n**Validation scheme:** paired Wilcoxon signed-rank test, 5 seeds, 3 repetitions per seed."
}'
```

Driven verbatim (2026-10-12), against a fixture carrying both required sources:

```json
{
  "status": "created",
  "operation": "CREATE_INITIAL_REVISION",
  "targetFilename": "experiments-domain-shift-baseline-sweep-v01.md",
  "targetRevision": "v01",
  "targetSha256": "2a4f6a8bcacbed91bb374cca99636e1af4cb66a4cd7e28c567e8da4620cb9211",
  "canonicalMetadata": { "schemaVersion": 1, "title": "Domain shift baseline sweep", "sectionHeading": "Testing whether the proposed adaptation term improves held-out accuracy under domain shift without target labels" },
  "mutations": 1,
  "receiptId": "experiments-domain-shift-baseline-sweep-v01.md:v01",
  "manifestStatus": "NOT_TRACKED",
  "nextAction": null,
  "instructionBudget": { "limit": 65536, "used": 425, "remaining": 65111 }
}
```

Two things to read carefully in that response. The **filename slug is derived from the first sentence of your idea** — the title and section heading come from the idea text too, never from a fixed skeleton — so write that first sentence as the lineage name you want; a short, standalone first sentence (`"Domain shift baseline sweep."`) is what produced the clean `domain-shift-baseline-sweep` slug above. The derivation is fixed: the title is the first sentence and the section heading the second, each with its terminal `.`, `!` or `?` dropped (punctuation inside the sentence is kept), both capped at 200 characters; the whole idea is then written verbatim as the section body, so the two sentences appear twice on purpose — the headings are labels, the body is the only place your full text survives. And `targetRevision` reports **`v01`, the same label the filename carries** — `artifact.revisionLabel(1)`, read from this domain's own profile, never a hardcoded `r01`: the filename is the authority and the label agrees with it.

If a required source directory is absent:

```json
{
  "status": "blocked",
  "operation": "CREATE_INITIAL_REVISION",
  "nextAction": "supply_required_source",
  "blockers": [{ "code": "REQUIRED_SOURCE_MISSING", "message": "Required source \"guidance/data-paper\" is missing; CREATE_INITIAL_REVISION cannot proceed without it." }]
}
```

If a managed revision already exists, it blocks with `MANAGED_PROPOSAL_ALREADY_EXISTS` — it never overwrites or duplicates one.

### Dry run first: see v1 before it exists

A successful `CREATE_INITIAL_REVISION` takes a project-wide creation lock (`.experimental-deliberation/locks/initial-revision.lock`) and leaves it in place for good: it is the guard that keeps two concurrent creations from both winning, so after one success every further attempt is refused `MANAGED_PROPOSAL_ALREADY_EXISTS`. The engine never removes that lock. To see what v1 would be before committing to it, add `--dry-run` (or `"dryRun": true` in the request):

```bash
node skills/experimental-deliberation/cli.mjs --dry-run '{
  "operation": "CREATE_INITIAL_REVISION",
  "instruction": "Domain shift baseline sweep. Testing whether the proposed adaptation term improves held-out accuracy under domain shift without target labels.\n\n**Dataset:** domain-shift-benchmark (standard train/validation/test split as distributed).\n\n**Validation scheme:** paired Wilcoxon signed-rank test, 5 seeds, 3 repetitions per seed."
}'
```

The dry run runs every check the real call runs — required sources, an existing managed revision, the single-sentence refusal, the canonical form, the pre-publish validation — and composes the document, then stops before the lock and the write. It answers `status: "preview"`, `dryRun: true`, `mutations: 0`, the would-be `targetFilename` and `targetRevision`, `canonicalMetadata`, the composed `markdown` (without the artifact marker) and `instructionBudget`; nothing under `experiments/` or `.experimental-deliberation/` is created. Sending the same request without the flag then writes exactly that markdown. If the creation lock is already present, the dry run answers the refusal the real call would meet (`MANAGED_PROPOSAL_ALREADY_EXISTS`, naming the lock) and leaves the lock untouched. `dryRun` applies only to `CREATE_INITIAL_REVISION`; on any other operation it is refused `DRY_RUN_UNSUPPORTED` and nothing runs (`CREATE_SUCCESSOR` already previews without it; `STATUS` and `RESOLVE_TARGET` never write and ignore the flag).

### The source window

`CREATE_INITIAL_REVISION` pastes the declared sources into v1, but reads at most **4000 bytes across all of them** by default, in declaration order (the data paper, then `proposals/`, then the paper guide); inside each source, `<folder>/<folder>.md` files come first and flat `*.md` files second, in name order. The document that crosses the limit is cut at it and the ones after it are not read at all. Every result that composed a document — `created`, the dry run's `preview`, and a canonical-form or validation refusal — carries the report, and a warning whenever something was cut or left out. Driven with a 6,001-byte data paper and one proposal file:

```json
"sourceWindow": {
  "limitBytes": 4000,
  "loadedBytes": 4000,
  "sources": [
    { "path": "guidance/data-paper/benchmark/benchmark.md", "bytes": 6001, "loadedBytes": 4000, "status": "truncated" },
    { "path": "proposals/research-concept-shared-code-r02.md", "bytes": 44, "loadedBytes": 0, "status": "not-loaded" }
  ]
},
"warnings": [{ "code": "SOURCE_WINDOW_TRUNCATED", "message": "The first revision reads at most 4000 bytes across its declared sources, in declaration order; cut at the window: guidance/data-paper/benchmark/benchmark.md (4000 of 6001 bytes); not read at all: proposals/research-concept-shared-code-r02.md. Pass sourceWindowBytes (up to 262144) to widen it for this creation, shorten the sources, or carry what matters in the idea text." }]
```

Add `"sourceWindowBytes": <1..262144>` to the request to widen the window for that one creation (every loaded byte is pasted into v1, which then has to pass the same validation). A value outside that range, or not an integer, is refused `SOURCE_WINDOW_INVALID`; the field on any other operation is refused `SOURCE_WINDOW_UNSUPPORTED`. Combine it with `--dry-run` to read the report before anything is written.

### v1 is checked before it is written

**v1 is checked, not exempt.** Source fragments are pasted in verbatim under a `## Reference Sources` heading (this profile's `sourceReferenceHeading`), one `### <path>` per fragment — but `CREATE_INITIAL_REVISION` runs the composed candidate through the identical `violations()` gate `CREATE_SUCCESSOR` runs, before any write (see [SKILL.md](../SKILL.md#creating-v1-checked-by-the-same-gate-as-every-successor)). If a pasted fragment carries a filled report-table cell, or a URL with no verification tag, v1 is refused outright:

```json
{
  "status": "blocked",
  "blockers": [{ "code": "INITIAL_REVISION_CANONICAL_FORM_VIOLATION", "message": "…: url-without-verification-marker -- https://example.org/untagged-source must be followed by [pending-verification] or [verified: YYYY-MM-DD]; an unmarked URL claims a search that left no trace" }]
}
```

The same holds for the structural pre-publish validation every successor's accept turn runs over the whole document. A source fragment with a heading fused into prose (`The log marks its boundary with ## Results inline.`) is refused with `INITIAL_REVISION_CANDIDATE_VALIDATION_FAILED`, `nextAction: "repair_candidate_markdown"`, and a message naming `atx-heading-standalone` and the offending line; the same sentence with the marker in a code span (`` `## Results` ``) publishes.

Driven for real: a source fragment containing one bare URL and nothing else wrong never becomes a file on disk. So there is nothing to repair in v1 for either of those two conditions *after* creation — a v1 that exists already satisfies them, exactly as any successor does; asking the reader to check for a violation that would have blocked the write is asking them to repair a file that cannot exist. What is still worth a read once v1 is created is what the gate does **not** check: whether a pasted source fragment says what you meant it to, and whether the idea text you sent is the document you actually want to build on.

### A v1 created before 0.14.0 that carries copied markers

Before 0.14.0, v1 pasted each proposal revision verbatim, including its reserved artifact marker line, so a v1 from that release can hold copies of the marker inside `## Reference Sources`. Its bytes are never rewritten. A successor that keeps the copies is refused at preview:

```json
{ "status": "blocked", "message": "CANDIDATE_VALIDATION_FAILED", "nextAction": "repair_candidate",
  "blockers": [{ "code": "successor-copied-artifact-marker", "message": "the candidate still carries 2 copied artifact marker lines inherited from its source, under \"## Reference Sources > ### proposals/…-r01.md\", \"# … > ## … > ### proposals/…-r02.md\": … In this successor, also replace each section named above (RESOLVE_TARGET it, then a replace decision whose content is the section without the marker lines); …" }] }
```

The pasted proposal brought its own `# ` heading, so the copies can sit in more than one section. Resolve each section the message names, and send one replace decision per section (`selectedEntryIds`, one query per section) whose `replacementText` is that section without the marker line. Your other edits can go in the same successor. Once that successor is published it holds no copies, and every later successor reads it normally. A replacement that writes a marker back is refused `successor-patch-limit`.

## Adopting an existing document as v1

When the user chooses to adopt an unmanaged file already in `experiments/` as the first revision (decision tree branch 3), let the engine do it:

```bash
node skills/experimental-deliberation/cli.mjs '{
  "operation": "ADOPT_INITIAL_REVISION",
  "instruction": "Adopt the existing draft as the first revision.",
  "sourceFilename": "my-draft.md"
}'
```

It runs the same gate a created v1 meets (the canonical form, then the pre-publish validation) over the file's own bytes, and then publishes them through the creation path itself: the single-winner creation lock, an exclusive write under `experiments-<slug of the first "# " title, else of the file name>-v01.md`, the committed derived state and the receipt. The receipt is the one a created v1 gets (`"operation": "CREATE_INITIAL_REVISION"`) plus `"adoptedFrom": "my-draft.md"`. Driven against a `my-draft.md` titled `# Domain shift baseline sweep` and carrying both declarations (`authority` and the audit fields omitted):

```json
{
  "operation": "ADOPT_INITIAL_REVISION",
  "sourceFilename": "my-draft.md",
  "status": "adopted",
  "mode": "rename",
  "targetFilename": "experiments-domain-shift-baseline-sweep-v01.md",
  "targetRevision": "v01",
  "mutations": 1,
  "manifestStatus": "COMMITTED",
  "auditStatus": "PASS",
  "nextAction": "move_adopted_source_to_backup",
  "sourceLeftInPlace": true
}
```

The engine never moves or deletes a file in `experiments/`, so `my-draft.md` is still there, byte-identical: move it to a backup after the user confirms, as the decision tree's backups paragraph describes. Refusals, each with nothing written: `ADOPTION_SOURCE_INVALID` (not one `.md` file directly inside `experiments/`), `MANAGED_PROPOSAL_ALREADY_EXISTS` (a managed revision or the creation lock already exists), `INITIAL_REVISION_CANONICAL_FORM_VIOLATION` / `INITIAL_REVISION_CANDIDATE_VALIDATION_FAILED` (the document breaks the gate; repair it and retry). `--dry-run` answers `status: "preview"` with the would-be `targetFilename` and writes nothing.

**Recording an old hand-adopted v1.** A first revision adopted by hand (marker prepended, file renamed) has no state and no receipt, and the consistency audit reports `MISSING_MANIFEST` for it. It keeps reading exactly as before — nothing invalidates it. To give it its record, send the same operation with `sourceFilename` set to that revision: `mode: "record"`, its bytes untouched, after the same gate, with the state and the receipt (`adoptedFrom` names the revision itself) written and no lock taken; the audit then passes. A revision that already has a receipt is refused `ADOPTION_ALREADY_RECORDED` and never re-recorded, and a managed revision past the first is refused `ADOPTION_SOURCE_NOT_INITIAL`.

## Open one `--serve` process for the whole deliberation

The acceptance token lives only in that process's memory, and the host's cold start is paid once per process. Resolve, preview and accept are three calls; send all three — and every later version's calls — down the same stdin:

```bash
node skills/experimental-deliberation/cli.mjs --serve
```

Every example below is one JSON line to that process.

## Resolving a locus before deciding

```json
{ "operation": "RESOLVE_TARGET", "sourceFilename": "experiments-domain-shift-baseline-sweep-v02.md", "query": "Baselines comparison" }
```

```json
{ "status": "resolved", "operation": "RESOLVE_TARGET", "entryId": "…", "blocked": false, "question": null }
```

Write the query as **distinctive words from the target heading**, not a sentence describing it. The resolver scores a heading by how many query words are words of its heading line, so only rare words help. A query word matches a heading only when it equals one of the heading's own words, never part of one: `O1` matches `### O1. Objective` and not `### O10. Scope`, and `entropy` still reaches `Cross-entropy` because each part of a hyphenated word counts. A heading whose words are exactly the query's (ignoring its section label and stopwords) outranks one that merely contains them, so `Alignment loss` names `## Alignment loss`, not `## Alignment loss weighting`. Drop punctuation (the query truncates at the first `,;:.`), drop the section number, keep accents exactly as the heading spells them.

- ✅ `"Baselines comparison"`
- ✅ `"## 4. Baselines: comparison table"` — level marks first: the heading spelled out, label and punctuation included
- ❌ `"Section 4. Baselines: comparison table"` — after a section noun, punctuation truncates it to `"4"`

**Naming an outer section.** Open the query with the heading's level marks and only headings of that level are considered: `## Data` names the whole `## Data` section, subsections included, even when `### Synthetic data` carries the same word, which is how a line directly under `## Data` (a `**Dataset:**` label, say) becomes editable. A level-marked query is read as the heading spelled out, so its label and punctuation are harmless: `## 4. Baselines: comparison table` is a valid selector. Without level marks every level is considered, and a match nested inside another is no longer collapsed to the innermost section: a tie blocks and lists both.

If `blocked` is `true`, the query matched more than one candidate — **remove the terms the question names, never add more**. When a query is blocked, `question` and `candidates` list every candidate with its level marks and its real heading path (`### Methods › Setup`); name the one you meant by its own heading words, or by level marks for the outer one. The blocked result also carries `candidates`, one `{ entryId, headingLevel, headingPath, score }` per candidate. Adding words to "narrow" a query widens it. If the reason is `SUCCESSOR_TARGET_NOT_FOUND`, no heading matched: you described the section's content instead of its title.

An experiment whose heading carries its own `[exp:E1]` declaration resolves from a query of just `E1` (measured), so keep the declaration in the heading rather than in the body. `experimental-implementation` reads the same convention (`skills/_core/conventions/experiments.json`) and locates an experiment only by such a heading, its block running to the next heading of the same or a higher level; one heading per experiment is all either skill needs (no wrapping `## N`).

Several loci in one call:

```json
{ "operation": "RESOLVE_TARGET", "sourceFilename": "experiments-domain-shift-baseline-sweep-v02.md", "queries": [{ "query": "Baselines comparison" }, { "query": "Experiment E1 protocol" }] }
```

```json
{ "status": "resolved", "operation": "RESOLVE_TARGET", "results": [{ "query": "Baselines comparison", "entryId": "…", "blocked": false, "question": null }, { "query": "Experiment E1 protocol", "entryId": "…", "blocked": false, "question": null }] }
```

## What a well-formed experiment block looks like

This is the shape to put in `replacementText`. It satisfies every canonical-form rule: empty report cells, a declared parameters table, a tagged URL, a baseline row carrying both a repository and a venue year, a criterion under its bold label, and a declared identifier a claim can cite.

```markdown
## Experiment [exp:E1] — labelled-budget sweep

Sustains claim C1 [tests:E1]: the method needs no target labels.

**Hypothesis.** Held-out accuracy of the adapted arm does not fall below the source-only arm as the labelled budget shrinks.

**Variables.** Independent: labelled examples per class (k). Dependent: held-out accuracy, macro-F1. Controlled: architecture, optimiser, seed set.

**Data and splits.** The benchmark's own train/validation/test partition, unchanged.

**Protocol.** Five seeds per cell; paired comparison against the source-only arm on the same seeds; Wilcoxon signed-rank at alpha = 0.05.

- **Success criterion:** the adapted arm's mean held-out accuracy is not lower than the source-only arm's at every value of k, with the paired test not rejecting equality.

**Priority.** Core. **Estimated cost.** 30 runs, roughly 6 GPU-hours.

| Parameter | Value |
| --- | --- |
| Learning rate | 3e-4 |
| Batch size | 128 |

### Expected report

| Arm | k=1 | k=5 | k=20 |
| --- | --- | --- | --- |
| Source only |  |  |  |
| Adapted |  |  |  |

![Held-out accuracy against labelled examples per class](figures/accuracy-vs-k.png)

### Baselines

| Baseline | Repository | Venue |
| --- | --- | --- |
| Alpha-Net | [repository](https://example.org/alpha-net) [pending-verification] | ICML 2015 |
| Beta-Net | https://example.org/beta-net [verified: 2026-09-08] | NeurIPS 2019 |
```

Three things to notice, each of which is a rule and not a style choice:

- The report table's body cells are **empty**, and its first header cell is `Arm`, so the fabricated-value rule applies to every column past the first.
- The baselines table's first header cell is **`Baseline`**, which exempts its cells from that rule as a reference. Spell it that way when you want the exemption; do not when you do not.
- The settings table's first header cell is **`Parameter`**, which declares it a parameters table: values the plan fixes now, not results, so its numbers are allowed. `Parameters`, `Hyperparameter` and `Hyperparameters` declare the same (case-insensitively, the whole cell). Nothing else does: a first header cell like `Parameter count`, or a `Parameter` column further right, leaves the table an ordinary report table under the rule.
- Both URLs are tagged, one per style. `[verified: 2026-09-08]` says a search on that date reached it; `[pending-verification]` says nobody has.

The block is canonical in form, not a model of statistical design: an exact paired Wilcoxon over five seeds can never reach p < 0.05 (its smallest two-sided p is 0.0625), and the protocol names no correction, effect size or confidence interval. Choose the test from the experiment's type with [Choosing the significance test by experiment type](../SKILL.md#choosing-the-significance-test-by-experiment-type), and declare the convergence curves and the significance table among the expected outputs.

## Building `resolvedDecisions` and applying

Every `CREATE_SUCCESSOR` preview needs `changeSummary`, or it is blocked with `CHANGE_SUMMARY_REQUIRED`.

### Replace (the common case)

```json
{
  "operation": "CREATE_SUCCESSOR",
  "sourceFilename": "experiments-domain-shift-baseline-sweep-v02.md",
  "instruction": "Add the missing venue year to the Beta-Net baseline row and tag its repository URL.",
  "selectedEntryId": "Baselines comparison",
  "changeSummary": {
    "what": "Completed the Beta-Net baseline row with its venue year and a verification tag.",
    "why": "A baseline without a venue year and a checkable repository is not a comparison a reviewer can follow."
  },
  "resolvedDecisions": [
    { "kind": "replace", "targetEntryId": "<entryId from the resolve step>", "replacementText": "| Baseline | Repository | Venue |\n| --- | --- | --- |\n| Alpha-Net | [repository](https://example.org/alpha-net) [verified: 2026-09-08] | ICML 2015 |\n| Beta-Net | [repository](https://example.org/beta-net) [verified: 2026-09-08] | NeurIPS 2019 |\n\n" }
  ]
}
```

### Insert

```json
{
  "operation": "CREATE_SUCCESSOR",
  "sourceFilename": "experiments-domain-shift-baseline-sweep-v02.md",
  "instruction": "Add an ablation experiment removing the adaptation term, after the main experiment.",
  "selectedEntryId": "Experiment E1 labelled budget sweep",
  "changeSummary": {
    "what": "Added ablation experiment E2, removing the adaptation term.",
    "why": "Claim C1 attributes the gain to that term, and nothing currently isolates it."
  },
  "resolvedDecisions": [
    { "kind": "insert", "anchorEntryId": "<entryId>", "position": "after", "content": "## Experiment [exp:E2] — adaptation term ablation\n\nSustains claim C1 [tests:E2] …\n\n" }
  ]
}
```

### Delete

```json
{
  "operation": "CREATE_SUCCESSOR",
  "sourceFilename": "experiments-domain-shift-baseline-sweep-v02.md",
  "instruction": "Remove the sentence claiming the adapted arm outperforms every published baseline — nothing has been run.",
  "selectedEntryId": "Motivation",
  "changeSummary": {
    "what": "Removed an asserted outcome from the motivation section.",
    "why": "This document plans work that has not happened; an asserted result is a fabricated one."
  },
  "resolvedDecisions": [
    { "kind": "delete", "targetEntryId": "<entryId>", "instructionEvidence": "Remove the sentence claiming the adapted arm outperforms every published baseline.", "reason": "asserted outcome in a plan" }
  ]
}
```

Deleting a document's **first** section is allowed: the artifact marker line that opens every managed revision is a block boundary of its own, so the next heading may follow it directly. Anywhere else, a removal that would leave two blocks one line break apart is refused as `successor-markdown-block-safety`.

### Move (literal) and copy (adaptive)

```json
{
  "kind": "move",
  "sourceEntryIds": ["<source entryId>"],
  "destinationAnchorId": "<destination entryId>",
  "position": "before",
  "moveMode": "LITERAL",
  "removeSource": true,
  "cleanupLevel": "NONE"
}
```

A `LITERAL` relocation carries the content byte-for-byte (omit `transformedContent`). An `ADAPTIVE` one requires you to supply the reworded text yourself in `transformedContent` — the engine never invents it, and neither should you without a stated basis.

### Several loci in one version

Use `selectedEntryIds` (plural), one query per entry, and one decision per resolved locus:

```json
{
  "operation": "CREATE_SUCCESSOR",
  "sourceFilename": "experiments-domain-shift-baseline-sweep-v02.md",
  "instruction": "Tighten E1's success criterion and complete the baselines table in the same version.",
  "selectedEntryIds": ["Experiment E1 labelled budget sweep", "Baselines comparison"],
  "changeSummary": { "what": "…", "why": "…" },
  "resolvedDecisions": [
    { "kind": "replace", "targetEntryId": "<entryId 1>", "replacementText": "…" },
    { "kind": "replace", "targetEntryId": "<entryId 2>", "replacementText": "…" }
  ]
}
```

## Preview, then accept

Every `CREATE_SUCCESSOR` above only previews:

```json
{
  "operation": "CREATE_SUCCESSOR",
  "status": "awaiting_acceptance",
  "sourceFilename": "experiments-domain-shift-baseline-sweep-v02.md",
  "targetFilename": "experiments-domain-shift-baseline-sweep-v03.md",
  "acceptanceToken": "…",
  "patchCount": 2,
  "modelCalls": 1,
  "plannerCalls": 1,
  "tutorCalls": 0,
  "reviewerCalls": 0,
  "mutations": 0,
  "manifestStatus": "NOT_PUBLISHED",
  "nextAction": "accept_successor",
  "instructionBudget": { "limit": 65536, "used": 83, "remaining": 65453 },
  "preservationDelta": { "lost": [], "added": [] },
  "mathDelta": { "lost": [], "added": [] }
}
```

`instructionBudget` is how much of the 65,536-character `instruction` cap this request used (here the 83-character instruction of the replace example above); an instruction over the cap is refused on every operation with `INSTRUCTION_TOO_LONG` and nothing is written. `CREATE_INITIAL_REVISION`'s result carries the same object for the idea.

`patchCount` is **2** for a one-decision batch, and that is not a mistake: on an all-`replace` batch the engine appends its own edit over the `## Changes` block from your `changeSummary`. `modelCalls`/`plannerCalls` are always `1` as a bookkeeping artifact of routing through the ambient-supplied planner — no network or model call is made. `tutorCalls`/`reviewerCalls` are always `0`: those roles are yours, in this conversation.

`mathDelta` is a permanent legacy alias for the identical `preservationDelta` object; read either. A version that drops something looks like this:

```json
"preservationDelta": {
  "lost": [
    { "id": "url:https://example.org/beta-net", "kind": "url", "text": "https://example.org/beta-net" },
    { "id": "baseline:3f2a19c4", "kind": "baseline", "text": "Beta-Net" }
  ],
  "added": []
}
```

Say out loud to the user what is leaving the document before you acknowledge it. Then publish by resending the identical request with the acceptance fields appended:

```
{"operation":"RESOLVE_TARGET","sourceFilename":"experiments-domain-shift-baseline-sweep-v02.md","query":"Baselines comparison"}
{"operation":"CREATE_SUCCESSOR","sourceFilename":"experiments-domain-shift-baseline-sweep-v02.md","instruction":"…","selectedEntryId":"Baselines comparison","changeSummary":{"what":"…","why":"…"},"resolvedDecisions":[{"kind":"replace","targetEntryId":"<entryId>","replacementText":"…"}]}
{"operation":"CREATE_SUCCESSOR","sourceFilename":"experiments-domain-shift-baseline-sweep-v02.md","instruction":"…","selectedEntryId":"Baselines comparison","changeSummary":{"what":"…","why":"…"},"resolvedDecisions":[{"kind":"replace","targetEntryId":"<entryId>","replacementText":"…"}],"acceptSuccessor":true,"successorAcceptanceToken":"<from the preview line>","acknowledgedRemovals":["url:https://example.org/beta-net","baseline:3f2a19c4"]}
```

Leave a lost id out and the accept answers `MATH_REMOVALS_NOT_ACKNOWLEDGED` and writes nothing. (`acknowledgedMathRemovals` is accepted as an equivalent field name; the two are merged into one set.)

To record why the change was made and who decided it, append `"rationale":"<why>","decider":"human"` (or `"agent"`) to the accept line; the successor's receipt then carries both beside its `instructionHash`, for example `"rationale": "Beta-Net's venue year was missing and its URL untagged.", "decider": "human"`. Both are optional, and a receipt without them validates exactly as before. A blank or over-2000-character `rationale`, or a `decider` other than `agent`/`human`, is refused `DECISION_RECORD_INVALID`; either field on another operation is refused `DECISION_RECORD_UNSUPPORTED`.

When the successor would still name a file named after ANOTHER revision with a suffix other than `.md` (an artifact rendered for the previous version, inherited outside your locus), the preview, the published result and the receipt carry `staleCompanionReferences`, one `{ "reference", "revision", "inherited" }` per reference, absent when there is none. The engine never rewrites that line or regenerates the artifact: replace the line inside this successor as an ordinary decision, or publish with the flag and say so.

The acceptance token is single-use and lives only in that `--serve` process's memory: a preview from one process cannot be accepted by another invocation.

### Resolved: the accept turn publishes in this domain

A successful publish returns `status: "published"`, the new filename, `targetSha256`, `receiptId`, `manifestStatus: "COMMITTED"`, and `auditStatus`/`selfAuditStatus: "PASS"`. **This domain reaches that.** Driving the full `resolve → preview → accept` cycle above against a real project (2026-09-13), on a v01 created exactly as shown earlier in this page, produced:

```json
{"status":"resolved","operation":"RESOLVE_TARGET","entryId":"composite:72:0cd72369d4fa6c88","blocked":false,"question":null,"text":"## Testing whether the proposed adaptation term improves held-out accuracy under domain shift without target labels.\n\n…"}
{"operation":"CREATE_SUCCESSOR","sourceFilename":"experiments-domain-shift-baseline-sweep-v01.md","status":"awaiting_acceptance","targetFilename":"experiments-domain-shift-baseline-sweep-v02.md","acceptanceToken":"l6k6lEbqwNH9Ghqb5IKWdBa47_mXmyBpOw457pbh25U","patchCount":2,"manifestStatus":"NOT_PUBLISHED","nextAction":"accept_successor"}
{"operation":"CREATE_SUCCESSOR","sourceFilename":"experiments-domain-shift-baseline-sweep-v01.md","status":"published","targetFilename":"experiments-domain-shift-baseline-sweep-v02.md","targetSha256":"f6f79c273001ca9657f51c322bacfc8fc480e6cd453efcac31d27cec7e12292c","receiptId":"experiments-domain-shift-baseline-sweep-v02.md:v02","manifestStatus":"COMMITTED","auditStatus":"PASS","selfAuditStatus":"PASS","nextAction":null}
```

(`entryId` and `acceptanceToken` are session-specific, like every other illustrative field on this page; `status`, `manifestStatus`, `auditStatus` and `selfAuditStatus` are not.)

The successor stood on disk beside its source. An earlier diagnosis of this path, on 2026-09-08, reported `INVALID_TARGET_REVISION` and blamed a hardcoded `-r(\d+)\.md$` in the shared core. Re-measured, that cause is not in the source and never described this code: `nextSuccessorTarget`, `parseManagedRevision` and `strictRevisionLabel` all read the revision pattern from this domain's own profile (`DOMAIN.artifact.revisionPattern`, `"v"`), so a `…-v0N.md` successor parses and validates exactly as an `…-r0N.md` one would in the mathematical sibling. See [SKILL.md](../SKILL.md#resolved-the-accept-turn-publishes-in-this-domain) for the full re-measurement.

Everything up to and including the write is real and worth running: resolution, patch compilation, candidate validation, the canonical-form rules, `preservationDelta`, the source-authority detection, and the publish itself all execute exactly as documented above. Still, read `status`, `manifestStatus`, `auditStatus` and `selfAuditStatus` before telling the user an edit landed — anything other than `published` / `COMMITTED` / `PASS` / `PASS` means it did not.

## When the candidate breaks the canonical form

A candidate violating any canonical-form rule fails validation, and the accept turn answers:

```json
{ "status": "blocked", "category": "recovery", "message": "CANDIDATE_VALIDATION_FAILED", "patchCount": 0, "nextAction": "inspect_error" }
```

**The public response does not name which canonical-form rule failed.** The projection that builds it keeps `status`, `category` and `message` and drops the validation detail. (A refusal from the accept turn's own pre-publish validation, such as `successor-markdown-block-safety` or `successor-copied-artifact-marker`, is named instead: `nextAction: "repair_candidate"` and one blocker with the rule's code, message and repair step.) So the message is where to start, not where to finish — go back to the bytes you wrote and check them against the rules, in this order:

1. Every external URL followed immediately by `[pending-verification]` or `[verified: YYYY-MM-DD]` — including URLs inside table cells and Markdown link targets.
2. Every report-table body cell past column one free of digits.
3. Every baselines-table body row carrying a repository URL and a four-digit venue year, with the year coming from the venue and not from a verification tag.
4. Every `[tests:X]` / `(Exp. X)` citation resolving to an `[exp:X]` this document declares, and no identifier declared twice.
5. Well-formed Markdown: complete blocks, blank-line separation preserved at block boundaries, and every ATX heading on its own line (a `## ` inside a backtick code span is text and passes).

The preview runs the same pre-publish validation the accept turn runs, so a candidate the accept turn would refuse is refused at the preview with this same message, and no acceptance token is issued for it.

The same projection applies to a source-authority block:

```json
{ "status": "blocked", "category": "recovery", "message": "SOURCE_AUTHORITY_CONFLICT" }
```

That fires when a line asserts an achieved result. The right fix is almost always to rewrite the sentence as planned work, not to acknowledge it. When the sentence genuinely quotes somebody else's published result, echo the conflict ids in `acknowledgedSourceConflicts` on the accept turn — and tell the user which sentence and whose result it is before you do.

## Rejections are the safety net, not a bug

- `CHANGE_SUMMARY_REQUIRED` — the preview turn carried no `changeSummary`.
- `WRONG_TARGET_ENTRY_ID` — re-resolve the locus and rebuild the decision; never reuse a stale or guessed ID.
- `ALTERED_REPLACEMENT_TEXT` — for an exact byte-preserving edit, copy the original block unchanged.
- `NO_MATCHING_DECISION` / `AMBIGUOUS_MATCHING_DECISIONS` — every resolved locus needs exactly one decision claiming it.
- `DECISIONS_OUTSIDE_SELECTION` — a single `selectedEntryId` was sent with decisions for other sections too (listed in `outsideSelection`); those would have been dropped, so nothing is previewed. Send one query per section in `selectedEntryIds`.
- `OVERLAPPING_PATCHES` — two edits over one span. On an all-`replace` batch the engine appends its own edit over the `## Changes` block, so do not also target that block yourself.
- `SOURCE_EQUALS_DESTINATION` / `HIERARCHY_CYCLE_DESTINATION_DESCENDANT` / `NO_OP_PLAN` — the relocation or replacement described is structurally impossible. Go back to the user rather than forcing a shape that satisfies validation without satisfying the request.
- `MULTIPLE_ACTIVE_REVISIONS` — a tied latest across lineages. Ask for the exact `sourceFilename`.

## The operations this host accepts

`STATUS`, `RESOLVE_TARGET`, `CREATE_INITIAL_REVISION`, `ADOPT_INITIAL_REVISION`, `CREATE_SUCCESSOR`, `WITHDRAW_REVISION`, `RESTORE_WITHDRAWN_REVISION`, `CHAT_DELIBERATION`, `CLOSE_DELIBERATION`, `MAINTENANCE`. Anything else is refused by name with `UNKNOWN_OPERATION` rather than routed as something else.

Three are accepted but outside this skill's flow:

- `CHAT_DELIBERATION` / `CLOSE_DELIBERATION` hand a deliberation turn to the engine. SKILL.md tells you to hold the thread yourself, so you never open one. Their state is in memory only — nothing is written, nothing survives the process.
- `MAINTENANCE` answers `delegation_permitted` for external upkeep work. It carries no authority over the document and mutates nothing.

Every operation except `STATUS` and `RESOLVE_TARGET` requires a non-empty `instruction` string, or the host rejects the envelope with `INSTRUCTION_REQUIRED`.

## Managed revision lifecycle

```bash
node skills/experimental-deliberation/cli.mjs '{
  "operation": "WITHDRAW_REVISION",
  "instruction": "Withdraw the superseded plan.",
  "sourceFilename": "experiments-domain-shift-baseline-sweep-v03.md",
  "withdrawalReason": "superseded after the protocol search was redone"
}'
```

Omit `withdrawalOperationId` — the engine generates and returns it with the audited backup location. The **base revision cannot be withdrawn**: aiming this at `…-v01.md` answers `blocked` with the warning `BASE_REVISION_WITHDRAWAL_BLOCKED` and changes nothing (measured). To restore:

```bash
node skills/experimental-deliberation/cli.mjs '{
  "operation": "RESTORE_WITHDRAWN_REVISION",
  "instruction": "Restore the withdrawn plan.",
  "sourceFilename": "experiments-domain-shift-baseline-sweep-v03.md"
}'
```

If more than one withdrawn record shares that filename, the engine asks for the exact `withdrawalOperationId` instead of guessing. Withdrawal and restore bypass target resolution, `resolvedDecisions` and all planning — they are deterministic file operations with an audited recovery copy.

## Reading the result

Before telling the user an edit is complete, check `status`, `manifestStatus`, `auditStatus`, `selfAuditStatus` and `recoveryStatus`. Anything other than `published` / `COMMITTED` / `PASS` / `PASS` / `not_required` means the operation is not done. Follow only the recovery the engine itself reports; never invent a revision or replay a request blindly.
