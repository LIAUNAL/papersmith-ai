# Tasks: Caztor Writing Guides

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 2200-3000 (slice 1 about 1800-2400, generated content) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | Slice 1 -> Slice 2 -> Slice 3 |
| Delivery strategy | exception-ok (size exception accepted; one local branch per slice) |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Base | Focused test | Runtime harness | Rollback |
|------|------|------|--------------|-----------------|----------|
| 1 | Content: distiller, guides, attribution | `feature/caztor-writing-guides` | `npx vitest run guides packages/adapters-local/src/guides` | `npx tsx scripts/distill-guides.ts /home/andres/papersmith-ai` (read-only) then `git diff --exit-code guides` | `guides/`, `scripts/`, `LICENSES/`, `NOTICE.md` |
| 2 | Port, fallback, provisioning, wiring | slice 1 branch | `npx vitest run packages` | Provision a temp project through the real file system; check twelve files and `state.json` | core/adapters/server edits |
| 3 | Definitions core and read exception | slice 2 branch | `npx vitest run agents` | Compare shared section across the three files | `agents/*` |

## Slice 1: Content

- [x] 1.1 RED: `packages/adapters-local/test/guides/distill.test.ts` (moved from `src/`: the repository keeps tests in `test/`) fixtures: front matter and stripped sections removed, heading suffix cleaned, throws naming file and line, deterministic.
- [x] 1.2 GREEN: `packages/adapters-local/src/guides/distill.ts` (`distillGuide`, `STRIPPED_HEADINGS`, `PIPELINE_TERMS`, notice, advisory note, `## Shared conventions`).
- [x] 1.3 Create `scripts/distill-guides.ts` reading `/home/andres/papersmith-ai` (read-only) at `1f09516`; writes `guides/NN-*.md`, `INDEX.md`, `SOURCE.json`.
- [x] 1.4 Copy Apache-2.0 verbatim to `LICENSES/Apache-2.0.txt` from `/home/andres/papersmith-ai` (read-only).
- [x] 1.5 RED: `guides/guides.test.ts` plus `guides/distill-script.test.ts` and `packages/adapters-local/test/guides/build-set.test.ts` (ten guides plus index, kept/stripped vs `SOURCE.json`, introduction advice, notice, advisory/typical-range/genre wording, `**Extent**`, `## Disqualifiers`, no pipeline terms, license, opt-in rebuild via `CAZTOR_PAPERSMITH_DIR`); add `guides/**` to `vitest.config.ts`.
- [x] 1.6 GREEN: run the script, commit generated `guides/*`.
- [x] 1.7 Add "Writing guides" section to `NOTICE.md` (URL, license, commit, changes); test asserts it.

## Slice 2: Port and provisioning

- [x] 2.1 RED: `packages/core/src/guide-source.test.ts` for `withFallback` with fakes (primary ok, primary fails, both fail).
- [x] 2.2 GREEN: `GuideSourcePort`, `GuideDocument`, `unavailable` status and `detail` in `packages/core/src/ports.ts`; `GUIDES_DIR`, `isGuideName` in `agent-targets.ts`; create `guide-source.ts`; export in `index.ts`.
- [x] 2.3 RED then GREEN: `packages/adapters-local/src/guides/built-in-source.ts` serves `guides/` plus `LICENSE-papersmith-ai.txt`; missing folder gives error.
- [x] 2.4 RED: provisioner suite in `packages/adapters-local/src/provisioner.test.ts`: twelve files, create, idempotence, tampered guide and license, deleted, user-authored, replace, link refusal, invalid names, missing `INDEX.md`, stale removal, `unavailable` without failing the turn.
- [x] 2.5 GREEN: extend `ensure` in `packages/adapters-local/src/provisioner.ts` (hash rules, `state.provisioned[".caztor/guides/<name>"]`).
- [x] 2.6 RED then GREEN: `remove` deletes matching guides, keeps modified, drops empty folder after last provider.
- [x] 2.7 RED then GREEN: `packages/core/src/turn-service.ts` shows guide-specific skipped notice, keeps `replace_definition`; test with fake source.
- [x] 2.8 Wire the source in `apps/server-local/src/agents.ts` and `packages/adapters-local/src/index.ts`.
- [x] 2.9 RED regression test: snapshot excludes `.caztor/guides`; tree hiding.

## Slice 3: Definitions

- [x] 3.1 RED: `agents/agents.test.ts`: shared section byte-identical, `## Section guides`, `.caztor/guides/INDEX.md`, sizes under 16 KiB, exact `.caztor/` rule, only allowed `.caztor/` paths.
- [x] 3.2 RED: turn-service test for a single reset on definition change.
- [x] 3.3 GREEN: edit `agents/claude.md`, `agents/opencode.md`, `agents/codex.md` (core after `## Academic style`, at most 3 KiB; editing rule).
- [x] 3.4 Update `README.md` (guides, source, license) and `NOTICE.md`.

## Traceability

| Requirement | Tasks |
|---|---|
| Guide content; Advisory stance | 1.1-1.6 |
| Guide source port | 2.1-2.3, 2.8 |
| Provisioning; Tampered/deleted/user-authored; Removal | 2.4-2.7 |
| Apache-2.0 attribution | 1.4, 1.5, 1.7, 3.4 |
| Writing guide core; Guide read exception; Size bound | 3.1, 3.3 |
| Agent provisioning; Removable | 2.4-2.6 |
| Definition change resets | 3.2 |
| Snapshot scope | 2.9 |
