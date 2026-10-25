# Proposal Deliberation — examples and help

See [SKILL.md](../SKILL.md) for the full tutor-role conditioning and workflow discipline. This page is worked examples only: checking `STATUS` before deciding a base, creating the first managed version, resolving a locus, building `resolvedDecisions`, and the preview → accept → publish cycle. Every call below is a real, verified invocation of `node skills/proposal-deliberation/cli.mjs` — none of it requires `ANTHROPIC_API_KEY` or any model configuration.

## Checking `STATUS` before deciding a base

Before running the decision tree in [SKILL.md's "Resolving the base version"](../SKILL.md#resolving-the-base-version), call `STATUS` — read-only, keyless, no model call:

```bash
node skills/proposal-deliberation/cli.mjs '{ "operation": "STATUS" }'
```

Against a `proposals/` directory holding a managed `r01`/`r02` pair, one managed-looking-but-unmarked `r03` (missing the `<!-- proposal-workspace:artifact:v1 -->` marker, so it does NOT count as managed), and an unrelated `initial-idea.md`:

```json
{
  "status": "ok",
  "operation": "STATUS",
  "managedRevisions": [
    { "filename": "research-concept-r01.md", "lineage": "ROOT", "revisionNumber": 1, "isLatest": false },
    { "filename": "research-concept-r02.md", "lineage": "ROOT", "revisionNumber": 2, "isLatest": true }
  ],
  "latest": "research-concept-r02.md",
  "multipleActive": false,
  "candidates": [],
  "nonManagedFiles": ["initial-idea.md", "research-concept-r03.md"]
}
```

Pass `sourceFilename` to classify one candidate base against that same inventory in the same call:

```bash
node skills/proposal-deliberation/cli.mjs '{ "operation": "STATUS", "sourceFilename": "research-concept-r01.md" }'
```

```json
{ "...": "same fields as above, plus:", "sourceClassification": "OLDER_MANAGED", "newerRevisionNumbers": [2] }
```

```bash
node skills/proposal-deliberation/cli.mjs '{ "operation": "STATUS", "sourceFilename": "initial-idea.md" }'
```

```json
{ "...": "same fields as above, plus:", "sourceClassification": "UNMANAGED" }
```

`sourceClassification` is one of `LATEST`, `OLDER_MANAGED` (with `newerRevisionNumbers`), `UNMANAGED`, or `NOT_FOUND` (the filename is not present in `proposals/` at all, or it is not a real basename). Never mutating: no `proposals/` file is ever created, moved, or changed by a `STATUS` call — a confirmed backup move (SKILL.md's decision tree) is something *you* do afterward with a plain file move, never the engine. `STATUS` also answers on a project that has **no `proposals/` directory yet** — the exact pre-creation state `CREATE_INITIAL_REVISION` exists for — with the same empty inventory (`latest: null`, empty `managedRevisions`/`nonManagedFiles`), so the "run `STATUS` first" step never has a chicken-and-egg failure. A `proposals/` that exists but cannot be read still fails closed with an error instead of reporting "empty."

## Creating the first managed version

When no managed proposal exists yet, call the engine with `operation: CREATE_INITIAL_REVISION` and the idea as `instruction`:

```bash
node skills/proposal-deliberation/cli.mjs '{
  "operation": "CREATE_INITIAL_REVISION",
  "instruction": "Distribution-free calibration under covariate shift. A paper proposing a calibration test for conformal prediction sets when the covariates shift."
}'
```

This is explicit and user-triggered only: it never runs automatically, and it is rejected outright when a managed proposal already exists (it never overwrites or duplicates one). The engine loads the project's `guidance/paper-guide` directory once and composes v1 from that guide content plus the supplied idea — title, section heading, and filename slug are all derived from the idea, never a fixed generic skeleton: the title is the first sentence and the section heading the second, each with its terminal `.`, `!` or `?` dropped (punctuation inside a sentence is kept) and capped at 200 characters, and the slug is the title lowercased and hyphenated. The whole idea is then written verbatim as the section body, so those two sentences appear twice on purpose: the headings are labels, and the body is the only place the full text survives. An idea with no second sentence is refused with `INITIAL_IDEA_SINGLE_SENTENCE`. A successful call returns the created filename, revision, and document hash as completion evidence. Before writing, the composed v1 runs the same structural pre-publish validation every successor's accept turn runs over the whole document (size and reserved bytes, well-formed display blocks, standalone ATX headings); a failure is refused with `INITIAL_REVISION_CANDIDATE_VALIDATION_FAILED`, `nextAction: "repair_candidate_markdown"`, and a message naming the rule and the offending line. A heading marker inside a backtick code span is text and passes.

### The source window

`CREATE_INITIAL_REVISION` pastes the declared sources into v1, but reads at most **4000 bytes across all of them** by default, in declaration order (this skill declares one source, `guidance/paper-guide`); inside each source, `<folder>/<folder>.md` files come first and flat `*.md` files second, in name order. The document that crosses the limit is cut at it and the ones after it are not read at all. Every result that composed a document — `created`, the dry run's `preview`, and a canonical-form or validation refusal — carries the report, and a warning whenever something was cut or left out. Driven on the experiments skill, whose sources are a data paper and `proposals/` (this skill reports the same shape for its paper guide):

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

A guide that holds the engine's reserved markers (a managed revision copied into `guidance/paper-guide/`, say) is read with them neutralised: each reserved marker comment line is removed, any other occurrence of a reserved marker name becomes plain text, NUL bytes are dropped, and the document's `sourceWindow` entry carries `reservedMarkersRemoved: <count>`. v1 never carries another document's markers.

### Dry run first: see v1 before it exists

A successful `CREATE_INITIAL_REVISION` takes a project-wide creation lock (`.proposal-deliberation/locks/initial-revision.lock`) and leaves it in place for good: it is the guard that keeps two concurrent creations from both winning, so after one success every further attempt is refused `MANAGED_PROPOSAL_ALREADY_EXISTS`. The engine never removes that lock. To see what v1 would be before committing to it, add `--dry-run` (or `"dryRun": true` in the request):

```bash
node skills/proposal-deliberation/cli.mjs --dry-run '{
  "operation": "CREATE_INITIAL_REVISION",
  "instruction": "Distribution-free calibration under covariate shift. A paper proposing a calibration test for conformal prediction sets when the covariates shift."
}'
```

The dry run runs every check the real call runs — required sources, an existing managed revision, the single-sentence refusal, the canonical form, the pre-publish validation — and composes the document, then stops before the lock and the write. It answers `status: "preview"`, `dryRun: true`, `mutations: 0`, the would-be `targetFilename` and `targetRevision`, `canonicalMetadata`, the composed `markdown` (without the artifact marker) and `instructionBudget`; nothing under `proposals/` or `.proposal-deliberation/` is created. Sending the same request without the flag then writes exactly that markdown. If the creation lock is already present, the dry run answers the refusal the real call would meet (`MANAGED_PROPOSAL_ALREADY_EXISTS`, naming the lock) and leaves the lock untouched. `dryRun` applies only to `CREATE_INITIAL_REVISION`; on any other operation it is refused `DRY_RUN_UNSUPPORTED` and nothing runs (`CREATE_SUCCESSOR` already previews without it; `STATUS` and `RESOLVE_TARGET` never write and ignore the flag).

## Adopting an existing document as v1

When the user chooses to adopt an unmanaged file already in `proposals/` as the first revision (decision tree branch 3), let the engine do it:

```bash
node skills/proposal-deliberation/cli.mjs '{
  "operation": "ADOPT_INITIAL_REVISION",
  "instruction": "Adopt the existing draft as the first revision.",
  "sourceFilename": "my-draft.md"
}'
```

It runs the same gate a created v1 meets (the canonical form, then the pre-publish validation) over the file's own bytes, and then publishes them through the creation path itself: the single-winner creation lock, an exclusive write under `research-concept-<slug of the first "# " title, else of the file name>-r01.md`, the committed derived state and the receipt. The receipt is the one a created v1 gets (`"operation": "CREATE_INITIAL_REVISION"`) plus `"adoptedFrom": "my-draft.md"`. Driven against a `my-draft.md` titled `# Calibrated sampling under drift` (proposal skill shown; `authority` omitted):

```json
{
  "operation": "ADOPT_INITIAL_REVISION",
  "sourceFilename": "my-draft.md",
  "status": "adopted",
  "mode": "rename",
  "targetFilename": "research-concept-calibrated-sampling-under-drift-r01.md",
  "targetRevision": "r01",
  "mutations": 1,
  "manifestStatus": "COMMITTED",
  "auditStatus": "PASS",
  "nextAction": "move_adopted_source_to_backup",
  "sourceLeftInPlace": true
}
```

The engine never moves or deletes a file in `proposals/`, so `my-draft.md` is still there, byte-identical: move it to a backup after the user confirms, as the decision tree's backups paragraph describes. Refusals, each with nothing written: `ADOPTION_SOURCE_INVALID` (not one `.md` file directly inside `proposals/`), `MANAGED_PROPOSAL_ALREADY_EXISTS` (a managed revision or the creation lock already exists), `INITIAL_REVISION_CANONICAL_FORM_VIOLATION` / `INITIAL_REVISION_CANDIDATE_VALIDATION_FAILED` (the document breaks the gate; repair it and retry). `--dry-run` answers `status: "preview"` with the would-be `targetFilename` and writes nothing.

**Recording an old hand-adopted v1.** A first revision adopted by hand (marker prepended, file renamed) has no state and no receipt, and the consistency audit reports `MISSING_MANIFEST` for it. It keeps reading exactly as before — nothing invalidates it. To give it its record, send the same operation with `sourceFilename` set to that revision: `mode: "record"`, its bytes untouched, after the same gate, with the state and the receipt (`adoptedFrom` names the revision itself) written and no lock taken; the audit then passes. A revision that already has a receipt is refused `ADOPTION_ALREADY_RECORDED` and never re-recorded, and a managed revision past the first is refused `ADOPTION_SOURCE_NOT_INITIAL`.

## Open one `--serve` process for the whole deliberation

The engine host's own cold start (jiti compiling its TS sources) is paid once per spawned process. A single version already needs at least three calls — resolve, preview, accept — so start ONE persistent process and keep it open for the whole deliberation instead of spawning a fresh `cli.mjs` invocation per call:

```bash
node skills/proposal-deliberation/cli.mjs --serve
```

Every example below is a JSON line sent to that same process's stdin, in order.

## Resolving a locus before deciding

Before you can build a `resolvedDecisions` entry, you need the engine's own resolved entry ID for the locus you intend to touch. Send a `RESOLVE_TARGET` line to the `--serve` process above — this is read-only, makes no model call, and needs no `ANTHROPIC_API_KEY`. It uses the exact same resolver (`loadDocumentState` → `resolveSuccessorTarget` → `ambiguityGate`) `orchestrator.ts` calls internally for `CREATE_SUCCESSOR`, so the returned `entryId` is guaranteed to match what `CREATE_SUCCESSOR` itself would resolve for the identical `sourceFilename`/query:

```json
{ "operation": "RESOLVE_TARGET", "sourceFilename": "research-concept-r05.md", "query": "Assumptions stationarity" }
```

Write the query as **distinctive words from the target heading**, not as a sentence describing it. The resolver scores a heading by how many query words are words of its heading line, so only the rare words help. A query word matches a heading only when it equals one of the heading's own words, never part of one: `O1` matches `### O1. Objective` and not `### O10. Scope`, and `entropy` still reaches `Cross-entropy` because each part of a hyphenated word counts. A heading whose words are exactly the query's (ignoring its section label and stopwords) outranks one that merely contains them, so `Alignment loss` names `## Alignment loss`, not `## Alignment loss weighting`. Drop punctuation (the query is truncated at the first `,;:.`), drop the section number, and keep accents exactly as the heading spells them — matching is accent-sensitive. Stopwords are filtered out for you.

**Naming an outer section.** Open the query with the heading's level marks and only headings of that level are considered: `## Data` names the whole `## Data` section, subsections included, even when `### Synthetic data` carries the same word, which is how a line directly under `## Data` (a `**Dataset:**` label, say) becomes editable. A level-marked query is read as the heading spelled out, so its label and punctuation are harmless: `## 4. Baselines: comparison table` is a valid selector. Without level marks every level is considered, and a match nested inside another is no longer collapsed to the innermost section: a tie blocks and lists both.

```json
{ "operation": "RESOLVE_TARGET", "sourceFilename": "research-concept-r05.md", "query": "## Data" }
```


```json
{ "status": "resolved", "operation": "RESOLVE_TARGET", "entryId": "…", "blocked": false, "question": null }
```

- If `blocked` is `false`, `entryId` is the real value to use as `targetEntryId`/`anchorEntryId`/`sourceEntryIds`/`destinationAnchorId` in your decision.
- If `blocked` is `true`, the query matched more than one candidate — `question` lists them and names the terms that matched all of them, and `candidates` carries each one's `entryId`, `headingLevel` and `headingPath`. A candidate reads as its level marks and its real heading path (`### Methods › Setup`), so two sections with the same title, or a section and the subsection inside it, are told apart. **Remove those terms; never add more.** Extra words match more headings, so "narrowing" a blocked query widens it. Never guess between the listed candidates.
- If the reason is `SUCCESSOR_TARGET_NOT_FOUND`, no heading line matched — you described the section's content instead of its title. Name the heading. A successor locus is never resolved from body text, so a near-miss can never silently hand you the wrong section.

Do this once per independent locus in the batch you are about to apply. To resolve several loci in one call, send `queries` (an array of `{ "query": "..." }`) instead of `query`:

```json
{ "operation": "RESOLVE_TARGET", "sourceFilename": "research-concept-r05.md", "queries": [{ "query": "Assumptions stationarity" }, { "query": "Main convergence theorem" }] }
```

```json
{ "status": "resolved", "operation": "RESOLVE_TARGET", "results": [{ "query": "Assumptions stationarity", "entryId": "…", "blocked": false, "question": null }, { "query": "Main convergence theorem", "entryId": "…", "blocked": false, "question": null }] }
```

## Building `resolvedDecisions` and applying

### Replace (the common case: rewrite a paragraph, definition, or block)

```bash
node skills/proposal-deliberation/cli.mjs '{
  "operation": "CREATE_SUCCESSOR",
  "sourceFilename": "research-concept-r05.md",
  "instruction": "Tighten the definition of stationarity to require strict, not weak, stationarity.",
  "selectedEntryId": "Assumptions stationarity",
  "resolvedDecisions": [
    { "kind": "replace", "targetEntryId": "<entryId from the resolve step>", "replacementText": "A process is strictly stationary when its full joint distribution is shift-invariant..." }
  ]
}'
```

### Insert

```json
{
  "operation": "CREATE_SUCCESSOR",
  "sourceFilename": "research-concept-r05.md",
  "instruction": "Add a remark after the main theorem clarifying the role of the boundedness assumption.",
  "selectedEntryId": "Main convergence theorem",
  "resolvedDecisions": [
    { "kind": "insert", "anchorEntryId": "<entryId>", "position": "after", "content": "**Remark.** Boundedness is used only to control the tail of the empirical process; ..." }
  ]
}
```

### Delete

```json
{
  "operation": "CREATE_SUCCESSOR",
  "sourceFilename": "research-concept-r05.md",
  "instruction": "Remove the sentence claiming the method has no computational overhead — it is unsupported.",
  "selectedEntryId": "Limitations",
  "resolvedDecisions": [
    { "kind": "delete", "targetEntryId": "<entryId>", "instructionEvidence": "Remove the sentence claiming the method has no computational overhead.", "reason": "unsupported claim" }
  ]
}
```

Deleting a document's **first** section is allowed: the artifact marker line that opens every managed revision is a block boundary of its own, so the next heading may follow it directly. Anywhere else, a removal that would leave two blocks one line break apart is refused as `successor-markdown-block-safety`.

### Move (literal — content carried byte-for-byte)

```json
{
  "operation": "CREATE_SUCCESSOR",
  "sourceFilename": "research-concept-r05.md",
  "instruction": "Move the paragraph beginning \"We next impose compactness\" from the motivation section to immediately before the assumptions list.",
  "selectedEntryId": "Assumptions compactness",
  "resolvedDecisions": [
    {
      "kind": "move",
      "sourceEntryIds": ["<source entryId>"],
      "destinationAnchorId": "<destination entryId>",
      "position": "before",
      "moveMode": "LITERAL",
      "removeSource": true,
      "cleanupLevel": "NONE"
    }
  ]
}
```

### Copy (adaptive — content reworded to fit its new context)

An `ADAPTIVE` relocation requires you to supply the reworded text yourself in `transformedContent` — the engine never invents it, and neither should you without a stated basis:

```json
{
  "operation": "CREATE_SUCCESSOR",
  "sourceFilename": "research-concept-r05.md",
  "instruction": "Copy the notation convention for logarithms from the notation section to the start of the appendix, adapting it to refer back to the notation section.",
  "selectedEntryId": "Notation conventions",
  "resolvedDecisions": [
    {
      "kind": "copy",
      "sourceEntryIds": ["<source entryId>"],
      "destinationAnchorId": "<appendix start entryId>",
      "position": "inside_start",
      "moveMode": "ADAPTIVE",
      "removeSource": false,
      "cleanupLevel": "NONE",
      "transformedContent": "As established in the notation section, all logarithms are natural unless noted otherwise."
    }
  ]
}
```

### Multiple independent loci in one version

Use `selectedEntryIds` (plural) instead of `selectedEntryId`, one query per entry, and supply one decision per resolved locus:

```json
{
  "operation": "CREATE_SUCCESSOR",
  "sourceFilename": "research-concept-r05.md",
  "instruction": "Tighten stationarity and add the boundedness remark in the same version.",
  "selectedEntryIds": ["Assumptions stationarity", "Main convergence theorem"],
  "resolvedDecisions": [
    { "kind": "replace", "targetEntryId": "<entryId 1>", "replacementText": "..." },
    { "kind": "insert", "anchorEntryId": "<entryId 2>", "position": "after", "content": "..." }
  ]
}
```

A batch that mixes in-place kinds (`replace`/`insert`/`delete`) with a relocation (`move`/`copy`) still completes in a single accept call, but publishes as two versions — see SKILL.md's "One version per homogeneous batch."

## Preview, then accept

Every `CREATE_SUCCESSOR` call above only previews. A real run looks like:

```json
{
  "operation": "CREATE_SUCCESSOR",
  "modelCalls": 1,
  "plannerCalls": 1,
  "tutorCalls": 0,
  "reviewerCalls": 0,
  "mutations": 0,
  "status": "awaiting_acceptance",
  "targetFilename": "research-concept-r06.md",
  "acceptanceToken": "…",
  "patchCount": 1,
  "manifestStatus": "NOT_PUBLISHED",
  "nextAction": "accept_successor",
  "instructionBudget": { "limit": 65536, "used": 81, "remaining": 65455 }
}
```

`instructionBudget` is how much of the 65,536-character `instruction` cap this request used (here the 81-character instruction of the replace example above); an instruction over the cap is refused on every operation with `INSTRUCTION_TOO_LONG` and nothing is written. The first revision's `created` result carries the same object for its idea.

(`modelCalls`/`plannerCalls` are always `1` here as a bookkeeping artifact of routing through the ambient-supplied planner — no network or model call is made. `tutorCalls`/`reviewerCalls` are always `0`: those roles are yours, in-conversation, not the engine's.)

The preview also carries a `mathDelta` naming every mathematical atom that existed before and is gone after — display equations, inline math, `\tag` values, LaTeX macros, `(Ec. N)` citations:

```json
"mathDelta": { "lost": [{ "id": "display:2a32c3fe", "kind": "display", "text": "x_{t+1}=A x_t" }], "added": [] }
```

Publishing requires echoing every lost id in `acknowledgedMathRemovals`; leave one out and the accept answers `MATH_REMOVALS_NOT_ACKNOWLEDGED` and writes nothing. Editing an equation counts as removing its previous form. Say out loud to the user what is leaving the document before you acknowledge it.

When the successor would still name a companion artifact of ANOTHER revision — a file named after a revision with a suffix other than `.md`, such as the graph rendered for the source — the preview, the published result and the receipt carry `staleCompanionReferences` (absent when there is none):

```json
"staleCompanionReferences": [
  { "reference": "research-concept-r05.graph.html", "revision": "research-concept-r05.md", "inherited": true }
]
```

`inherited: true` means the source carried the same reference outside your locus; `false` means your own replacement wrote it. The engine never rewrites the line and never renders the picture: either replace the line inside this successor with the successor's own reference, as a decision like any other, or publish with the flag and say so. See [the graph](../SKILL.md#the-graph-the-proposal-inside-the-sota-sky).

To publish, reuse the SAME `--serve` session opened at the top of this page — send the resolve line, then the preview line, then an accept line with `acceptSuccessor: true`, the returned `acceptanceToken`, and any `acknowledgedMathRemovals`, all over the same stdin:

```json
{"operation":"RESOLVE_TARGET","sourceFilename":"research-concept-r05.md","query":"..."}
{"operation":"CREATE_SUCCESSOR","sourceFilename":"research-concept-r05.md","instruction":"...","selectedEntryId":"...","resolvedDecisions":[{"kind":"replace","targetEntryId":"<entryId from the resolve line>","replacementText":"..."}]}
{"operation":"CREATE_SUCCESSOR","sourceFilename":"research-concept-r05.md","instruction":"...","selectedEntryId":"...","resolvedDecisions":[{"kind":"replace","targetEntryId":"<entryId from the resolve line>","replacementText":"..."}],"acceptSuccessor":true,"successorAcceptanceToken":"<the acceptanceToken from the preview line>","acknowledgedMathRemovals":["<every mathDelta.lost[].id from the preview line>"]}
```

To record why the change was made and who decided it, append `"rationale":"<why>","decider":"human"` (or `"agent"`) to the accept line; the successor's receipt then carries both beside its `instructionHash`:

```json
{ "instructionHash": "…", "rationale": "The old definition admitted weakly stationary processes the theorem does not cover.", "decider": "human", "…": "…" }
```

Both fields are optional, and a receipt without them validates exactly as before. A blank or over-2000-character `rationale`, or a `decider` other than `agent`/`human`, is refused `DECISION_RECORD_INVALID`; either field on another operation is refused `DECISION_RECORD_UNSUPPORTED`.

The final line returns `status: "published"`, the new filename, `receiptId`, `manifestStatus: "COMMITTED"`, and `auditStatus`/`selfAuditStatus: "PASS"`. The acceptance token is single-use and lives only in that `--serve` process's memory — a preview from one process cannot be accepted by another invocation of `cli.mjs`. Keeping resolve, preview, and accept on the same stdin also means the engine's cold start is paid once for all three, not three times.

## Rejections are the safety net, not a bug

If your resolution or decision was wrong, the engine rejects it instead of silently doing something else:

- `WRONG_TARGET_ENTRY_ID` — re-resolve the locus (previous section) and rebuild the decision; do not reuse a stale or guessed ID.
- `ALTERED_REPLACEMENT_TEXT` — for an exact byte-preserving edit, copy the original block into `replacementText` unchanged.
- `NO_MATCHING_DECISION` / `AMBIGUOUS_MATCHING_DECISIONS` — every resolved locus in the request needs exactly one decision claiming it.
- `DECISIONS_OUTSIDE_SELECTION` — a single `selectedEntryId` was sent with decisions for other sections too (listed in `outsideSelection`); those would have been dropped, so nothing is previewed. Send one query per section in `selectedEntryIds`.
- `SOURCE_EQUALS_DESTINATION` / `HIERARCHY_CYCLE_DESTINATION_DESCENDANT` / `NO_OP_PLAN` — the described relocation or replacement is structurally impossible; go back to the user rather than forcing a shape that would satisfy validation without satisfying the request.

## The operations this host accepts

`STATUS`, `RESOLVE_TARGET`, `CREATE_INITIAL_REVISION`, `ADOPT_INITIAL_REVISION`, `CREATE_SUCCESSOR`, `WITHDRAW_REVISION`,
`RESTORE_WITHDRAWN_REVISION`, `CHAT_DELIBERATION`, `CLOSE_DELIBERATION`, `MAINTENANCE`. Anything
else is refused by name with `UNKNOWN_OPERATION` rather than routed as something else.

Three of them are accepted but outside this skill's flow, and the distinction matters when reading
a response:

- `CHAT_DELIBERATION` / `CLOSE_DELIBERATION` hand a deliberation turn to the engine. SKILL.md tells
  you to hold the thread yourself instead, so you never open one. Their state is in memory only —
  nothing is written, nothing survives the process, and no conversation can reach another.
- `MAINTENANCE` answers `delegation_permitted` for external upkeep work. It carries no authority
  over the proposal (`documentAuthority: "FORBIDDEN"`) and mutates nothing.

`tests/proposal-deliberation-cli-operation-surface.test.mjs` pins this list. Adding or removing an
operation is a public change and must edit that test too.

## Managed revision lifecycle

To withdraw an eligible managed revision:

```bash
node skills/proposal-deliberation/cli.mjs '{
  "operation": "WITHDRAW_REVISION",
  "sourceFilename": "research-concept-r05.md",
  "withdrawalReason": "superseded by a cleaner formulation"
}'
```

Omit `withdrawalOperationId` — the engine generates and returns it along with the audited backup location. To restore:

```bash
node skills/proposal-deliberation/cli.mjs '{
  "operation": "RESTORE_WITHDRAWN_REVISION",
  "sourceFilename": "research-concept-r05.md"
}'
```

If more than one withdrawn record shares that filename, the engine asks for the exact `withdrawalOperationId` instead of guessing. Withdrawal and restore bypass target resolution, `resolvedDecisions`, and all planning — they are deterministic file operations with an audited recovery copy, unaffected by the ambient-model rewrite.

## Reading the result

Before telling the user an edit is complete, check the returned `status`, `manifestStatus`, `auditStatus`, `selfAuditStatus`, and `recoveryStatus`. Anything other than `published` / `COMMITTED` / `PASS` / `PASS` / `not_required` means the operation is not done — follow only the recovery or clarification the engine itself reports; never invent a revision or replay a request blindly.
