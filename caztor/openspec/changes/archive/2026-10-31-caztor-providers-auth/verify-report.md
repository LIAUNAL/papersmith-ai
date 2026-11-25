# Verification Report: Caztor Providers Auth

## Current verdict (2026-10-31)

No open critical blocker. S5 was verified by a fresh subagent against the specs and the real `agy` captures, using 57 throwaway probes and no real provider call. It found no blocker and 6 advisories. Fixed with regression tests: guard fail-open on unclear tool steps (A1, A2), symlinked or extra-key definitions (A3, A4), and the sign-in panel folding over a store problem (A6). Open advisory: Antigravity error output reaches the error detail unredacted, since it has no secrets to redact (A5).

Latest suite: 2927 passed, 33 skipped; `npx tsc -b` exit 0. Browser checks `dialog`, `compile` and `chat` passed before the last two small commits and were not repeated after them unless the final report says so.

Limits: the 25-requirement, 63-scenario matrix was not completed scenario by scenario. S1 to S4 rely on the earlier verification below, which was run by a subagent of the GPT-5.6 Terra session. Its probes of the credential store and read-back were not repeated here.

## Earlier verification (superseded on S5)

## Scope

Independent T12 verification compared this branch with `bb6814e`, using the change's specs, design, and tasks. No real provider call, credential file, or project file was modified.

## Evidence

| Check | Observed result |
|---|---|
| S1-S4 focused verification | 375 passed |
| Full suite | 2865 passed, 31 skipped |
| Typecheck | exit 0 |
| Antigravity provider tests | unavailable: `packages/adapters-local/test/providers/antigravity` has no test files |

## Requirement Matrix

| Area | Status | Evidence |
|---|---|---|
| Credential store, routes, redaction, auth-mode sessions | full for independently inspected S1-S4 behavior | verifier found no concrete blocker; focused suite 375 passed |
| Provider auth and environment routing | full for independently inspected S1-S4 behavior | verifier found no concrete blocker |
| Antigravity provider, isolation, guard, detection, continuation | missing | no runner, mapper, server wiring, or test directory exists |
| Antigravity permanent notice and turn integration | missing | no S5 implementation exists |
| Antigravity logo/header | partial | official logo and focused header/notice tests pass; runner remains missing |
| Archive traceability | missing | tasks 5.2-5.7, 6.1, and 6.4 remain unticked |

## Blocker

`apps/server-local/src/server.ts` wires only opencode, Codex, and Claude. There is no `packages/adapters-local/src/providers/antigravity/` runner or mapper. The independent verifier confirmed that this prevents detection, guarded execution, trust-gated turn startup, continuation, and the permanent partial-isolation notice.

The source blocker is recorded in `docs/handoff/BLOCKED.md`: the sole R1 invocation exited 2 because `-p` consumed `--output-format` as its prompt. Under the fixed three-call budget, a replacement R1 requires user authorization.

## Result

Verification is incomplete with one open critical blocker. No correction batch was possible without inventing the real stream contract or exceeding the authorized-call rule.
