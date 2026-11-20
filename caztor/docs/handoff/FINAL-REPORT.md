# Final Report: caztor-providers-auth

## Outcome

The plan is complete on `feat/providers-auth-s6-docs`, apart from the pending items below. Caztor has account and API sign-in modes, a credential store and a fourth provider, Antigravity. `main` is untouched at `bb6814e`.

Who did what: GPT-5.6 Terra handled T0, T1, T8 and the S1-S4 verification until its usage limit. Gemini 3.8 Flash wrote the first mapper, runner and fixtures until its quota ran out. Claude fixed them and finished T6 to T15.

## Observed checks

| Check | Result |
|---|---|
| `npx vitest run` | 2927 passed, 33 skipped, 0 failed |
| `npx tsc -b` | exit 0 |
| `CAZTOR_REAL_BIN=1 npx vitest run packages/adapters-local` | 1458 passed, 11 skipped, before the final hardening commit |
| `npm run build -w @caztor/web` | passed |
| `e2e/dialog.mjs`, `e2e/compile.mjs`, `e2e/chat.mjs` | exit 0, including Antigravity cases and no console or CSP errors |
| Independent S5 verification | No blocker; 6 advisories, 5 fixed with regression tests |

## Real `agy` calls

Agy 1.4.12 with `gemini-3.8-flash-medium`, recorded in `docs/handoff/BLOCKED.md`.

| Call | Result |
|---|---|
| First R1 attempt | Exit 2 on argv form, before any model request |
| R1 edit | Exit 0; the file was edited |
| R2 shell | Exit 0; no shell step, the model declined |
| R3 continuation | Exit 0; same conversation |

The Gemini work session also spent the account's quota, separately from these calls. Its reset was reported as about 121 hours from 2026-10-31.

## Pending and not verified

- **Native review:** assessment reports high risk and review due. Not started, because consent is the user's.
- **Merge to `main`:** the user's decision.
- **Real Antigravity turn through Caztor:** never run. The runner was tested with recorded and synthetic streams, because the quota is spent. `CAZTOR_REAL_AGY_TURNS=1` runs one when quota returns.
- **Unobserved `agy` behavior:** auth failure, a real disallowed tool step and malformed output use synthetic fixtures. The quota error shape is real.
- **`commandExecutionPolicy: off`:** enforcement by the CLI is unproven. The guard may stop a tool only after it started, and the UI says so.
- **Scenario matrix:** an independent pass over all 63 scenarios found 51 covered, 11 partial and 1 that needs a real `agy` run (not signed in). Tests were then added for 10 of the partial ones. Open: Isolated run, which needs a real binary with a planted global hook, and Not signed in.
- **Login state:** learned from account-mode turns and kept in memory, so it is `unknown` after each server start and the hint shows until a turn completes.
- **Redaction of `agy` output:** covers Caztor's stored keys and key-like values (16 or more characters, no spaces, not a path) of environment variables whose names end like a secret. A token `agy` holds by itself is not known to Caztor, so it would not be hidden.
- **Guard allowlist of step types:** only five non-tool types pass: `agent_response`, `user_input`, `system_message` and `error_message`, seen in 324 real steps, and `checkpoint`, which no capture has shown. A new type from a future `agy` stops the turn until it is added.
- **Guard false positive:** an `agent_response` step with `tool_name: null` stops the turn by mistake. It fails closed, and no real capture has shown it.
- **Redaction names:** variables such as `GEMINI_API_KEYS`, `GITHUB_TOKEN_2` or `SECRET_KEY_BASE` are not masked, because the name must end like a secret. `agy` does not receive them, so it would have to find them itself. A long ordinary word under a matching name is still masked.
- **Provider refresh:** when two refreshes overlap, such as saving a key and then deleting one, the newer answer is dropped and the panel stays stale until the next refresh. `load()` has no such guard.
- **Other guard gaps:** an `agent_response` step with `toolName` or `tool_calls`, and an unknown top-level `tool_call` event, are not refused. No capture has shown them.
- **Last output line:** a fatal or final last line does not stop a child that stays alive after closing its output, and `tap` skips that line.
- **Redaction gaps:** a key split across `text_delta` chunks is not masked in those chunks, a key holding `"` stays visible in `tap`, and `probe` error detail in `detect()` is not redacted.
- **Screenshots:** two Antigravity views were read after the notice was shortened (1366 light, 1440 dark); the other 21 captures were not.
- **Cosmetic:** Antigravity answers contain `file://` links with absolute paths.

## Deviations and TDD slips

- `--print-timeout 180s` was dropped: the other runners have no such limit and it would cut long edits.
- Design decision 7 changed: `init.tools` is ignored, because it always lists about 60 tools.
- A definition with a problem now refuses the turn and offers replacement, stricter than the earlier warning.
- `mode_unsupported` was added to `TURN_ERROR_CODES`.
- Server wiring was written before `server-antigravity.test.ts`, so its RED was not observed. T8 logo code also preceded its assertion.
- The first archive commit `690bba9` holds an incomplete spec merge, because a failed script did not stop the commit. `79b217d` completes it from the base specs, with checks. Squash them if preferred.

## Branch tips

`feat/providers-auth-s6-docs` holds everything; `feat/providers-auth-s5-antigravity` stops at `8c97965`.

Risk: item 2 (credentials and guards)
