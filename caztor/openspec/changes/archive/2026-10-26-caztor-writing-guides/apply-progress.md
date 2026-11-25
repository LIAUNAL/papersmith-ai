# Apply progress: caztor-writing-guides

Mode: Strict TDD (`npx vitest run`). Delivery: exception-ok, feature-branch-chain, local branches only.
Source commit used: papersmith-ai `1f09516` (HEAD of `/home/andres/papersmith-ai` confirmed `1f09516`; sources are read with `git show 1f09516:...`).

## Slice 1: Content (branch `feature/caztor-writing-guides-s1-content`, base `feature/caztor-writing-guides`) - DONE

Commits: `1da2080` distiller, set builder, script; `5b49670` guides, license, NOTICE.

| Task | Test file | RED | GREEN | Notes |
|---|---|---|---|---|
| 1.1/1.2 | `packages/adapters-local/test/guides/distill.test.ts` | module missing, then 1 assertion mismatch on the error text | 20/20 | triangulated with rewrites, comments, id suffixes, Inputs rename |
| 1.2 (set) | `packages/adapters-local/test/guides/build-set.test.ts` | module missing; index "title selects among them" failed before edit | 10/10 | |
| 1.3 | `guides/distill-script.test.ts` | module missing | 4/4 | temporary git repository fixture |
| 1.4 | `guides/guides.test.ts` (license) | n/a | cmp identical to source `LICENSE` | |
| 1.5/1.6 | `guides/guides.test.ts` | guides directory moved away: ENOENT | 114/114, with `CAZTOR_PAPERSMITH_DIR` too | slip below |
| 1.7 | `guides/guides.test.ts` (NOTICE) | failed: no "Writing guides" section | green after edit | |

TDD slips: (1) I ran the script and generated `guides/` before writing `guides/guides.test.ts` (the generated output was needed to see which source vocabulary leaked); RED for 1.5 was therefore demonstrated afterwards by removing a guide. (2) The `guides/**` include in `vitest.config.ts` was added together with the first test, not with 1.5.

Work Unit Evidence (slice 1):
- Focused: `npx vitest run guides packages/adapters-local/test/guides` all green.
- Runtime: `node scripts/distill-guides.ts /home/andres/papersmith-ai` then `git diff --exit-code guides LICENSES` exit 0.
- Rollback: `guides/`, `scripts/`, `LICENSES/`, `NOTICE.md` section, `packages/adapters-local/{src,test}/guides`, `vitest.config.ts`/`tsconfig.json` entries.

## Slice 2: Port and provisioning (branch `feature/caztor-writing-guides-s2-provisioning`, base `feature/caztor-writing-guides-s1-content`) - DONE

Commits: `1680260` port, names, `withFallback`; `e105cbd` built-in source and provisioner; turn-service notices commit; `ccd9680` server wiring.

| Task | Test file | RED | GREEN |
|---|---|---|---|
| 2.1/2.2 | `packages/core/test/guide-source.test.ts` | module missing | 20 tests (names, `guideSetProblem`, `withFallback`, `isGuideTarget`) |
| 2.3 | `packages/adapters-local/test/guides/built-in-source.test.ts` | module missing | 11, memory and real fs plus the repository's own guides |
| 2.4/2.5 | `packages/adapters-local/test/provisioner/guides.test.ts` | 17 failed on both file systems | 34 pass; safety net 132/132 before and after extracting `syncFile` |
| 2.5 (state) | `packages/adapters-local/test/state-store.test.ts` | the state store dropped `.caztor/guides/*` records | green after `isGuideTarget` |
| 2.6 | `packages/adapters-local/test/provisioner/remove-guides.test.ts` | removal code already existed; RED shown by disabling it (10 of 12 failed) | 12 |
| 2.7 | `packages/core/test/turn-service.test.ts` | 3 failed | 64 |
| 2.8 | `apps/server-local/test/routes/chat-guides.test.ts` | 7 failed | 7 pass |
| 2.9 | `packages/adapters-local/test/snapshot/diff.test.ts` | regression only: `.caztor` was already excluded, so no RED possible | green |

TDD slips: (1) `removeGuides` was written together with `ensureGuides` (2.5) before its test (2.6); RED was shown afterwards by disabling the function. (2) 2.9 is a regression test and passed on first run, as the design predicted.
Deviation: the state store dropped provisioned keys that are neither agent targets nor valid project paths, so `isGuideTarget` was added to core and used in `state-store.ts` (not in the design). `/api/chat/definition/replace` now lists the twelve guide outcomes too; one existing assertion in `apps/server-local/test/routes/chat.test.ts` was updated for that (the first outcome is still the definition's `updated`).
Work Unit Evidence (slice 2): focused `npx vitest run packages apps/server-local` green; runtime: `chat-guides.test.ts` and the provisioner suite run the real file system (twelve files, `state.json` records, hidden from `/api/files`, absent from `files_changed`); rollback: core/adapters/server edits listed in the commits.

## Slice 3: Definitions (branch `feature/caztor-writing-guides-s3-definitions`, base `feature/caztor-writing-guides-s2-provisioning`) - DONE

Commit: `feat(agents): add the advisory writing guide core and the read exception for the guides` (agents, tests, README).

| Task | Test file | RED | GREEN |
|---|---|---|---|
| 3.1/3.3 | `agents/agents.test.ts` | 13 failed (core section, exact `.caztor/` rule, allowed paths) | 138 pass; core 2092 bytes plus heading (limit 3072); definitions 9.1 to 9.5 KiB (limit 16 KiB) |
| 3.2 | `packages/core/test/turn-service.test.ts` | regression only: the reset behaviour already existed, so no RED was possible | 66 pass (single reset; guide-only updates do not reset) |
| 3.4 | README "Writing guides" section, layout row, opt-in rebuild row; NOTICE already complete from 1.7 | n/a | n/a |

Final verification (all on the slice 3 branch, `CAZTOR_*` as listed in the assignment): `npx vitest run` 2567 passed / 31 skipped; `CAZTOR_REAL_BIN=1 npx vitest run packages/adapters-local` 1272 passed / 9 skipped; `CAZTOR_PAPERSMITH_DIR=/home/andres/papersmith-ai npx vitest run` 2569 passed / 29 skipped (byte-for-byte rebuild included); `npx tsc -b` clean; `npm run build -w @caztor/web` ok; `e2e/dialog.mjs`, `e2e/compile.mjs`, `e2e/chat.mjs` all PASS; real server (`node e2e/chat-server.ts`, scripted fake runner, temp project): one turn wrote the twelve guide files, `state.json` tracks 12 guide records, `/api/files` lists only `main.tex`, `GET /api/files/content?path=.caztor/guides/INDEX.md` is 403, and `files_changed` lists only `main.tex`. The server process was stopped by PID.
