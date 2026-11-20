# Design: Caztor Writing Guides

## Technical Approach

Exploration option B. A pure, tested transform distills papersmith `sections/*.md` (commit `1f09516`) into committed files under `guides/`. Core gains `GuideSourcePort` and a fallback combinator. A built-in adapter reads `guides/`. The provisioner writes the guides to `.caztor/guides/` with the same hash rules as definitions, for every provider. The shared section of `agents/*.md` gains a compact advisory core and a read-only exception. Specs: `writing-guides`, `agent-definitions`, `turn-snapshots`.

## Architecture Decisions

| # | Topic | Choice | Rejected alternative and tradeoff |
|---|---|---|---|
| 1 | Distillation | `distillGuide(text, sourcePath, commit)` in `packages/adapters-local/src/guides/distill.ts` (pure strings, no Node imports). It strips the JSON front matter and only the pipeline input subsections in `STRIPPED_HEADINGS` (`### External inputs`, `### Internal chain`, `### Structural decisions`, which hold the input tables and block-id references). It keeps generic advice, including `### What is writable before measuring`, `### The loop that must be closed by hand` (the results rule), the lead prose of each `## Inputs*` section, and `## Nothing is decided here`. It removes id suffixes such as `(`block-4a`, ...)` from headings, prepends the notice and an advisory note (word counts and extents are typical ranges for a research article; the genre note covers theses, reports and reviews), appends a fixed `## Shared conventions` section, and throws on any leftover `PIPELINE_TERMS` match. `scripts/distill-guides.ts <papersmith-dir>` writes the output. The future papersmith source calls the same function at runtime. | Hand-edited copies: free condensation, but not reproducible, they drift, and a runtime source could not apply them. Core placement: the transform is specific to an external format, so it belongs in an adapter. |
| 2 | Layout | `guides/NN-*.md`, `guides/INDEX.md` (generated), `guides/SOURCE.json` (repo URL, commit, and per file: source path, source SHA-256, `stripped` headings, `kept` headings), `LICENSES/Apache-2.0.txt` (verbatim; the built-in source serves it as `LICENSE-papersmith-ai.txt`, so the provisioned set is ten guides, `INDEX.md` and the license, twelve files, all hash-tracked), `NOTICE.md` section "Writing guides" (URL, license, commit, nature of the changes). | Guides inside `agents/`: this breaks the "exactly one definition per provider" test. |
| 3 | Core | New `## Section guides` heading after `## Academic style`, ASCII, at most 3 KiB. It states the advisory rule (the request, the document's structure and the venue template win), says when to read (`.caztor/guides/INDEX.md`, then only the one relevant guide), gives a one-line function per section, lists coherence invariants, gives a genre note (theses, reports, reviews map functions, not headings), and says that guides never license content the user did not provide. The editing rule reads exactly: "Inside `.caztor/` you may only read `.caztor/build/last-compile.log` and the files in `.caztor/guides/`. Do not change them, and do not read, create, modify or delete anything else inside `.caztor/`." Budget: each definition under 16 KiB, because the user's own `AGENTS.md` text shares Codex's 32 KiB. | Inlining the guides: over 32 KiB, and a high cost per turn. |
| 4 | Port and provisioning | `ensure(provider)` provisions the definition, then the guide set, under the existing lock and before the snapshot. Per file it applies the native rules: absent means create, equal means unchanged, a known older hash means update, anything else is `skipped_user_modified`, and `replace` overwrites. For a skipped guide, turn-service shows: "The writing guide `<name>` was changed, so Caztor kept the changed version. Replace it to restore Caztor's guide." The notice keeps the `replace_definition` action, and definitions keep their current wording. `guardedFolder` refuses links. Tracking uses `state.provisioned[".caztor/guides/<name>"]`. A tracked file that is no longer in the set is deleted when its hash still matches. A guide failure never fails the turn: it yields an `unavailable` outcome with a `detail`. `remove(provider)` deletes the guides with matching hashes, and the empty folder, once no `AGENT_TARGETS` entry stays tracked. | A separate guide provisioner port: a second turn-service call and duplicated guards. A fatal guide error: an advisory feature would block writing. |
| 5 | Runtime read exception | No runtime change. Reads inside the project are already allowed: the Claude `Read` tool, opencode (`external_directory` only covers paths outside the project), the Codex `workspace-write` sandbox, and Antigravity `view_file`. The exception lives in the provider-agnostic shared text. Hash tracking detects writes. | Path-scoped deny rules (`--disallowedTools Edit(...)`, opencode per-path `edit`): unverified flags and a parser change; deferred. |
| 6 | Snapshots | Already excluded through `EXCLUDED_AT_ROOT` `.caztor`. Add a regression test only. | A guide-specific exclusion: redundant. |
| 7 | Reset | The definition hash changes once. `chooseSession` (`turn-service.ts:203`) emits "New conversation started because the agent definition changed." Guides are outside the hash, so updating them does not reset. | Hashing guides into the definition: a reset on every guide update. |

## Data Flow

    guides/ ─→ BuiltInGuideSource ─┐
    (later) PapersmithSource ──────┴→ withFallback ─→ Provisioner.ensure ─→ .caztor/guides/ + state.json
                                                          └→ outcomes ─→ turn-service notices

## Interfaces / Contracts

```ts
// packages/core/src/ports.ts
export interface GuideDocument { name: string; bytes: Uint8Array } // "INDEX.md" | "LICENSE-papersmith-ai.txt" | /^\d\d-[a-z-]+\.md$/
export interface GuideSourcePort { load(): Promise<Result<readonly GuideDocument[], { message: string }>> }
// ProvisionOutcome.status gains "unavailable"; ProvisionOutcome gains detail?: string
// agent-targets.ts: GUIDES_DIR = ".caztor/guides"; isGuideName(name)
// guide-source.ts: withFallback(primary, fallback): GuideSourcePort
```

The provisioner validates every name against `isGuideName` and requires `INDEX.md` before it writes anything.

## File Changes

| File | Action |
|---|---|
| `packages/adapters-local/src/guides/{distill,built-in-source}.ts` | Create |
| `scripts/distill-guides.ts`, `guides/*`, `guides/guides.test.ts`, `LICENSES/Apache-2.0.txt` | Create |
| `NOTICE.md`, `vitest.config.ts` (include `guides/**`) | Modify |
| `packages/core/src/{ports,agent-targets,turn-service,index}.ts`, `guide-source.ts` | Modify / Create |
| `packages/adapters-local/src/{provisioner,index}.ts`, `apps/server-local/src/agents.ts` | Modify |
| `agents/{claude,opencode,codex}.md`, `agents/agents.test.ts` | Modify |

## Slices and Testing Strategy (strict TDD, `npx vitest run`)

| Slice | Content | RED tests first |
|---|---|---|
| 1 Content | Transform, script, guides, attribution | Unit tests of `distill` fixtures: front matter and stripped sections removed, heading suffix cleaned, throws naming the file and line, deterministic. `guides.test.ts` checks: ten guides plus `INDEX.md`; headings equal `SOURCE.json` `kept`; `stripped` contains only `STRIPPED_HEADINGS`; the introduction keeps "What is writable before measuring" and the results rule; notice with path and `1f09516`; advisory, typical-range and genre wording; `**Extent**`, `## Disqualifiers` and `## Shared conventions` present; no `PIPELINE_TERMS`; license and `NOTICE.md` present; an opt-in byte-for-byte rebuild when `CAZTOR_PAPERSMITH_DIR` is set. |
| 2 Port and provisioning | Port, fallback, built-in source, provisioner, wiring | `withFallback` with fakes; a fake source replaces the built-in one; the provisioner suite on `implementations` (real file system included) covers all twelve files including the license, the guide-specific skipped notice, create, idempotence, tampered, deleted, user-authored, link refusal, replace, stale removal, removal after the last provider, `unavailable` without failing the turn, and invalid names refused; tree hiding; snapshot regression. |
| 3 Definitions | Core and exception in all three files | `agents.test.ts`: shared section byte-identical; contains `## Section guides` and `.caztor/guides/INDEX.md`; each file under 16 KiB and 32 KiB; the exact `.caztor/` rule sentence is present, and the only `.caztor/` paths are `build/last-compile.log` and `guides/`; a turn-service test for a single reset. |

Slice 3 follows slice 2, so a definition never points to guides that do not exist. Slice 1 exceeds 400 lines because of generated content (the size exception was accepted).

## Threat Matrix

N/A: no routing, shell, subprocess, VCS automation or executable-file boundary. The provisioner writes stay under the existing guarded writer.

## Migration / Rollout

No migration. The first turn after the upgrade resets once and provisions the guides.

## Open Questions

None. Resolved by the orchestrator: the license is provisioned; the generic introduction advice is kept; article-based numbers are presented as typical ranges; the compile log and `.caztor/guides/` are the only readable `.caztor/` paths.
