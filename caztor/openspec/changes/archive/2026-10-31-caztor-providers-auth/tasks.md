# Tasks: Caztor Providers Auth

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 2800-3800 (code, tests, fixtures, docs) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | S1 → S2 → S3 → S4 → S5 → S6 (one local branch each) |
| Delivery strategy | exception-ok (size exception accepted; each slice stays one branch, not split further) |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

Tracker `feature/caztor-providers-auth` (from `bb6814e`). Local branches only; S1 base = tracker, Sn base = S(n-1). Conventional commits, no AI attribution. Strict TDD: RED test first. Tests use a temporary config home; the store file `credentials.json` under the user config dir (runtime path) is written only by shipped code.

### Suggested Work Units

| Unit | Goal | Base | Focused test | Runtime harness | Rollback |
|------|------|------|--------------|-----------------|----------|
| S1 | Types, store, redaction, state | tracker | `npx vitest run packages/core packages/adapters-local/src/credential-store` | N/A: no runtime path yet | revert S1 |
| S2 | Env, turn, routes | S1 | `npx vitest run packages/adapters-local/src/providers packages/api` | fake-runner server request | revert S2 (restores API-key override; note in release) |
| S3 | Web toggle, key form, hints | S2 | `npx vitest run apps/web` | browser check of toggle | revert S3 |
| S4 | Definition, reservation, gate | S3 | `npx vitest run agents packages/adapters-local/src` | provision into scratch project | revert S4 |
| S5 | Antigravity runner | S4 | `npx vitest run packages/adapters-local/src/providers/antigravity` | free `agy` checks, then R1-R3 | revert S5 |
| S6 | Docs, NOTICE, traceability | S5 | `npx vitest run` | N/A: docs | revert S6 |

## Phase 1: S1 Foundation

- [x] 1.1 RED `packages/core/src/redact.test.ts`: secrets under 8 chars skipped, mask `[redacted]`, nested event strings. (PA5)
- [x] 1.2 GREEN `packages/core/src/redact.ts` `redactSecrets`.
- [x] 1.3 RED `packages/core/src/auth.test.ts`: slot names `claude`, `codex`, `opencode:<vendor>`, mode default `account`. (PA1, PA6)
- [x] 1.4 GREEN `packages/core/src/auth.ts` and `ports.ts`: `AuthMode`, slots, `CredentialStorePort`, `CredentialReaderPort`, `TurnRequest.authMode`.
- [x] 1.5 RED `packages/adapters-local/src/credential-store.test.ts` (fake FS, temp config home): 0700/0600 create, group/other bits refused, wrong uid, linked dir/file, corrupt file never overwritten, temp cleanup, last4 only for keys of 12+ chars. (PA3, PA4)
- [x] 1.6 GREEN `packages/adapters-local/src/credential-store.ts`, `infra.ts` (`FsStats.uid`).
- [x] 1.7 RED+GREEN `packages/adapters-local/src/state-store.ts` tests: `authModes` sanitize, missing = `account`. (PA1)

## Phase 2: S2 Env, turn, routes

- [x] 2.1 RED runner tests for claude, opencode, codex: env per mode (exported keys stripped), vendor variable only, unknown vendor refused, separate `opencode-data-api` folder, key absent from argv. (AP1, PA6)
- [x] 2.2 GREEN `packages/adapters-local/src/providers/{claude,opencode,codex}/runner.ts`: per-turn env, on-demand `read(slot)`.
- [x] 2.3 RED `drive.test.ts`: key scrubbed from tap lines, stderr tail, event fields, history. (PA5)
- [x] 2.4 GREEN `providers/drive.ts` secrets param.
- [x] 2.5 RED `packages/core/src/turn-service.test.ts`: `api_key_missing` refusal, session `authMode` mismatch starts new conversation with notice. (PA2, PA1)
- [x] 2.6 GREEN `packages/core/src/turn-service.ts`, `session` record.
- [x] 2.7 RED `packages/api/src/routes/{providers,credentials}.test.ts`: 409/400 codes, echo `{slot,set,last4?}`, no GET, `no-store`, token/Origin/content-type. (PA4, LS1, PA2)
- [x] 2.8 GREEN routes plus `apps/server-local/src/server.ts` wiring.
- [x] 2.9 RED+GREEN `providers/project-config.ts` unchanged-isolation tests. (AP6, AP7, AP8)

## Phase 3: S3 Web

- [x] 3.1 RED `apps/web/src/chat/*.test.tsx`: toggle, not-configured state, field emptied on success and failure, login hints per provider. (AC1, AC2, AC3, PA7)
- [x] 3.2 GREEN `AuthModeToggle`, `KeyForm`, `LoginHint`, `providers.ts`.

## Phase 4: S4 Definition, reservation, gate

- [x] 4.1 RED `agents/agents.test.ts`: four definitions, byte-identical shared section with `.agents/`, guide core. (AD1, AD2, AD3)
- [x] 4.2 GREEN `agents/antigravity.md`; update `agents/{claude,opencode,codex}.md` shared section.
- [x] 4.3 RED+GREEN `agent-definition.ts` bracketed tools list, `provisioner.ts` create/skip/remove, `agent-targets.ts`. (AD1, AD2)
- [x] 4.4 RED+GREEN `paths.ts`, `snapshot-store.ts`: `.agents/` reserved and excluded. (PF1)
- [x] 4.5 RED+GREEN trust gate: any `.agents/` file except `caztor.md` is a finding; modified `caztor.md` warns. (AP3, AD1)

## Phase 5: S5 Antigravity runner

- [x] 5.1 Free checks only: `agy --help`, `--version`, `models`, `agents`; `claude --help`, `opencode --help` login commands; repeated against 1.4.11.
- [x] 5.2 REQUIRES ORCHESTRATOR GO-AHEAD (TOKEN SPEND): R1 real `agy -p` fixture turn; sanitize into fixtures.
- [x] 5.3 REQUIRES ORCHESTRATOR GO-AHEAD (TOKEN SPEND): R2 real `agy -p` asking for `ls`; record shell-tool behavior.
- [x] 5.4 REQUIRES ORCHESTRATOR GO-AHEAD (TOKEN SPEND): R3 real `agy -p --conversation` using R1 id.
- [x] 5.5 RED `providers/antigravity/mapper.test.ts` and `runner.test.ts`: mapping, init and step guard, hostile id/model argv, notice, stop, detection, continuation, `mode_unsupported` for API. (AP2, AP3, AP4, AP5, AC4)
- [x] 5.6 GREEN `providers/antigravity/{mapper,runner}.ts`; add `antigravity` id, `logo: null` fallback, header. (AP2, AC5)
- [x] 5.7 Wire fourth runner in `apps/server-local/src/server.ts`.

## Phase 6: S6 Docs

- [x] 6.1 `README.md`: auth modes, key storage, Antigravity, release note on `ANTHROPIC_API_KEY`.
- [x] 6.2 `NOTICE.md`: Antigravity logo row with SHA-256, or text-fallback decision.
- [x] 6.3 `openspec/changes/caztor-providers-auth/proposal.md`: rollback text `credentials` → `credentials.json`.
- [x] 6.4 Traceability check below; full `npx vitest run`.

## Traceability

PA1 1.3,1.7,2.5 | PA2 2.5,2.7 | PA3 1.5 | PA4 1.5,2.7 | PA5 1.1,2.3 | PA6 1.3,2.1 | PA7 3.1 | AP1 2.1 | AP2 5.5 | AP3 4.5,5.5 | AP4 5.5 | AP5 5.5 | AP6-8 2.9 | AD1-3 4.1-4.3 | AC1-3 3.1 | AC4 5.5 | AC5 5.6 | LS1 2.7 | PF1 4.4. Uncovered: none.
