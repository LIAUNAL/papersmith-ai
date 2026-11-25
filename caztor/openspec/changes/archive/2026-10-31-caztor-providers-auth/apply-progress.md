# Apply Progress: caztor-providers-auth

Mode: Strict TDD (`npx vitest run`). Store: hybrid. Delivery: exception-ok, feature-branch-chain, local branches only.

Branch chain: `feature/caztor-providers-auth` -> `feat/providers-auth-s1-foundation` -> `feat/providers-auth-s2-env-turn-routes` -> s3 -> s4 (S5 only 5.1; 5.2-5.4 wait for go-ahead; S6 not started).

Deviation (all slices): tests live under `packages/*/test/` (the vitest include globs and repo convention), not `src/` as tasks.md paths say.

## Completed

### S1 Foundation (branch `feat/providers-auth-s1-foundation`, base `feature/caztor-providers-auth`)

- [x] 1.1 RED `packages/core/test/redact.test.ts` (9 tests failed before implementation)
- [x] 1.2 GREEN `packages/core/src/redact.ts`
- [x] 1.3 RED `packages/core/test/auth.test.ts` (29 failed before implementation)
- [x] 1.4 GREEN `packages/core/src/auth.ts`, `ports.ts`
- [x] 1.5 RED `packages/adapters-local/test/credential-store.test.ts` (suite failed to import)
- [x] 1.6 GREEN `credential-store.ts`, `infra.ts` (`FsStats.uid`, `mkdir` mode), `node-infra.ts`, fake FS
- [x] 1.7 RED+GREEN `state-store.test.ts` (5 failing x2 implementations, then green)

| Work Unit Evidence | Value |
|---|---|
| Focused test | `npx vitest run packages/core packages/adapters-local/test/credential-store.test.ts packages/adapters-local/test/state-store.test.ts` green |
| Runtime harness | N/A: no runtime path yet |
| Rollback | revert the two S1 commits |

### S2 Env, turn, routes (branch `feat/providers-auth-s2-env-turn-routes`, base S1)

- [x] 2.1 RED runner env tests for claude, codex, opencode (29 failed before implementation, plus 3 for echoed keys)
- [x] 2.2 GREEN per-turn env builders, `providers/stored-key.ts`, runners read the key on demand
- [x] 2.3 RED `test/providers/drive.test.ts` (6 failed)
- [x] 2.4 GREEN `drive` `secrets` option (tap lines, stderr window with split-key handling, every event string)
- [x] 2.5 RED `packages/core/test/turn-service-auth.test.ts` (11 failed)
- [x] 2.6 GREEN turn service: `api_key_missing`, `mode_unsupported`, `authMode` in request and session record
- [x] 2.7 RED `apps/server-local/test/routes/{credentials,provider-auth}.test.ts`, `server-auth.test.ts` (15 + 13 failed)
- [x] 2.8 GREEN `packages/api/src/routes/credentials.ts`, `providers.ts` (auth block, `PUT auth-mode`), `apps/server-local/src/server.ts` wiring
- [x] 2.9 characterization tests: isolation flags, trust gate and violation abort are identical in api mode (pass without production change, as the task expects "unchanged")

| Work Unit Evidence | Value |
|---|---|
| Focused test | `npx vitest run packages/adapters-local/test/providers packages/core apps/server-local` green |
| Runtime harness | `apps/server-local/test/server-auth.test.ts`: real server, scripted `claude`, temporary `XDG_CONFIG_HOME`; stores a planted fake key over HTTP, runs a turn in api mode where the CLI echoes the key on stdout and stderr, and scans the turn stream, history, provider list, error bodies, headers and every project file: key found only in `credentials.json` |
| Rollback | revert the S2 commits (restores the old env passthrough: an exported `ANTHROPIC_API_KEY` reaches Claude again; note in release) |

Deviations S2:
- Route tests are in `apps/server-local/test/routes/` (where the existing route tests live), not `packages/api/src/routes/*.test.ts`.
- Existing assertions changed because behavior changed on purpose: env expectations of the three runners (exported keys no longer pass), session record now includes `authMode`, runner request includes `authMode`, provider list items include `auth`.
- `ProviderStatus.auth` is built by the providers route (`apiReady`, `storeProblem`, `login: "unknown"`, `loginHint`), not by the runner.
- Login hints (`loginHintOf`) live in core `auth.ts`; opencode command to be confirmed by task 5.1.

### S3 Web (branch `feat/providers-auth-s3-web`, base S2)

- [x] 3.1 RED `apps/web/src/chat/ChatPanel.auth.test.tsx` (21 failed before implementation), controller and client tests
- [x] 3.2 GREEN `AuthModeToggle`, `KeyForm`, `LoginHint`, `AuthPanel`, header/ErrorCard/MessageList wiring, `ApiClient` `setAuthMode/saveCredential/deleteCredential`, fake API
- also: `auth.slot`/`slotProblem` added to the provider list (server) because the browser cannot derive the opencode vendor slot; `providers.ts` (web) is unchanged in S3 (hints come from the server, `loginHintOf` in core).

| Work Unit Evidence | Value |
|---|---|
| Focused test | `npx vitest run apps/web` 623 passed |
| Runtime harness | `node e2e/chat.mjs` (scripted providers, temporary `XDG_CONFIG_HOME`): toggle starts on account, API marked not configured, selecting it asks for a key, masked empty field, fake key saved shows set + last four and the page never contains the key, field emptied, switch to API, delete, back; ALL CHECKS PASSED. Screenshots read in light and dark |
| Rollback | revert the S3 commits (web only plus the slot fields in the provider list) |

Deviations / slips S3:
- TDD slip: the `auth.slot` server change and the three `ApiClient` methods were implemented before their tests had been run red. The server test was then verified red by reverting the change; the client test was not (it passed on first run).
- `ProviderInfo.auth` is optional in the web type so older listings and the many existing test fixtures stay valid; the UI renders the panel only when it is present.
- The `e2e/chat.mjs` provider-count check was scoped to the "Provider" radio group, since the toggle adds radios inside the same header.

### S4 Definition, reservation, gate (branch `feat/providers-auth-s4-definition`, base S3)

- [x] 4.1 RED `agents/agents.test.ts` extended to four files (suite failed: antigravity.md missing)
- [x] 4.2 GREEN `agents/antigravity.md`; `.agents/` added to the shared section of all four (byte-identical, tests pass)
- [x] 4.3 RED+GREEN `agent-definition.ts` bracketed list, `provisioner.ts` (create/skip/remove tests `test/provisioner/antigravity.test.ts`), `agent-targets.ts`, `antigravity` id in `PROVIDER_IDS`, `loginHintOf`, account-only modes, web `PROVIDER_META` with `logo: null`
- [x] 4.4 RED+GREEN `paths.ts` (`.agents` in `RESERVED_ROOTS`), `snapshot-store.ts` exclusion; store/watch/snapshot tests extended (28 failed before)
- [x] 4.5 RED+GREEN `scanAntigravityProjectConfig`, `antigravityDefinitionProblem` (8 failed before)

| Work Unit Evidence | Value |
|---|---|
| Focused test | `npx vitest run agents/agents.test.ts packages/core packages/adapters-local` green; full suite 2865 passed |
| Runtime harness | scratch script (outside repo): real provisioner on a real temp project writes only `.agents/agents/caztor.md` (+ `.caztor/guides`), tools list parsed, definition check null, gate null |
| Rollback | revert the S4 commits (provider list returns to three providers) |

Deviations S4: the `antigravity` id reaches the provider list (as unavailable, "not available yet") from S4 as the design says; existing list expectations were updated to four. Nothing runs Antigravity yet (S5).

### Task 5.1 Free checks (no model call; run in temporary folders; no credential file or environment value read or printed)

- [x] 5.1 Done. `agy` 1.4.7 at `~/.local/bin/agy`; `codex` is not installed on this machine; `claude` and `opencode` are.

`agy --version` -> `1.4.7`. `agy --help` (flags, Go style, no value placeholders): `-p/--print` ("Run a single prompt non-interactively and print the response"), `--prompt` (alias), `--output-format text|json|stream-json`, `--input-format text|stream-json` (stream-json reads one NDJSON message per line from stdin, needs `--output-format stream-json`), `--mode accept-edits|auto|plan`, `--agent`, `--conversation <ID>`, `-c/--continue`, `--model`, `--effort`, `--add-dir`, `--project`, `--new-project`, `--log-file`, `--print-timeout`, `--disable-slash-commands`, `--sandbox`, `--dangerously-skip-permissions` (never used), `--json-schema`. Subcommands: `agent`/`agents`, `models`, `mcp`, `plugin(s)`, `changelog`, `update`, `install`, `remote-control`, `mic-serve`, `help`.
`agy models` -> 6 lines, tab separated `id<TAB>Display name` (for example `gemini-3.8-flash-high<TAB>Gemini 3.8 Flash (High)`, `claude-sonnet-4-6`, `gpt-oss-120b-medium`), preceded by a "Fetching available models..." line (stdout). Ids have no `provider/` form. Worked with no project and no extra environment.
`agy agents` -> empty output, both in an empty folder and in a scratch project holding the provisioned `.agents/agents/caztor.md`. `agy mcp list` and `agy plugin list` -> one line each (nothing configured here).
Binary strings (read-only) show `.agents/agents/`, `.agents/hooks.json`, `.agents/skills/`, `.agents/skills.json`, `.agents/rules/*.md`, `.agents/workflows/*.md`, `.agents/plugins/`: the trust gate over everything in `.agents/` matches the folder's real contents. The changelog says project custom agents in `.agents/agents/` are found "under execution with --agent, in headless (-p / --prompt) runs", which supports the definition path and `--agent caztor`.
`~/.gemini` exists on this machine; `~/.agents` and `~/.config/agy` do not (existence only).
`claude --help`: `claude auth login|logout|status` exist (`claude auth status` is a free login check, not run because it may print account data); `opencode providers login|list|logout` confirmed (`providers` has alias `auth`), so the opencode hint is right.

Contradictions or open points against the design (decide before 5.5/5.6):
1. Prompt on stdin: the changelog shows `-p "/usage"`, so `-p` takes the prompt as an argument. Whether `-p` reads the prompt from stdin could not be checked without a model call. The design's fallback (`-p -- <prompt>`) may be the real form; argv would then carry the prompt (still no shell). `--input-format stream-json` is a documented stdin route (NDJSON), needing `--output-format stream-json`.
2. `agy models` lines are `id<TAB>name`, not `provider/model`; the detection regex must take the first column.
3. Print-mode errors: the changelog says a failed headless run exits with code 3 and prints an `AGY_ERROR` line; the mapper/auth detection should key on that as well as on the `result` error event.
4. `agy agents` lists nothing for a provisioned definition: either it only lists global agents or the definition is not recognised until trusted. Check in R1 (needs go-ahead) that `--agent caztor` finds it.
5. Stream event names (`init`, `step_update`, `result`) are not documented in `--help` or the changelog; only R1 can confirm them.
6. Free login check available for Claude (`claude auth status`): a follow-up could replace `login: "unknown"`.

### T1 repeat free checks (2026-10-31, no model call)

- [x] Repeated `agy --version`, `--help`, `models`, `agents`, and `changelog` from temporary working directories. `agy --version` is now `1.4.11`; `agents` remains empty; `models` still emits `Fetching available models...` followed by six `id<TAB>Display name` rows.
- [x] Prompt delivery is settled before R1: `--input-format stream-json` explicitly reads NDJSON from stdin and requires `--output-format stream-json`. The 1.1.1 changelog says `-p` no longer reads stdin when its prompt is passed as a flag, so the runner must use the documented stream-json stdin form rather than place user text in argv.
- [x] `--agent`, `--conversation`, `--mode`, and `--dangerously-skip-permissions` remain present. The changelog records stable `init`, `step_update`, and `result` stream events, and an `init` fix for advertising unavailable tools.
- [x] New `--settings` accepts session-only JSON settings or a path and is never persisted. It is not an isolation or global-configuration relocation flag, so it does not change the partial-isolation design.
- [x] No new flag isolates or relocates global configuration. No credential path or value was read.

### T2 R1 real edit turn (2026-10-31)

- Call budget before invocation: 1 of exactly 3 authorized real `agy -p` calls. R1 is invoked once only with stream-json stdin.
- Result: exit `2`, no stdout events, no edit. `agy` reported: `-p took "--output-format" as its prompt, so the intended prompt was left as an argument and ignored. Attach the prompt to the flag (-p='your prompt') and move --output-format elsewhere on the command line.` The source file remained `The cat sat on the mat.`
- This consumed the invocation under the fixed three-call budget: a wrong argv does not authorize a fourth call. No R2 or R3 call was made. The required R1 stream schema, tool guard behavior, and continuation id therefore remain unobserved; raw captures remain outside the repository.

### T8 and T10 independent documentation work

- [x] 6.2: shipped the official unmodified `https://antigravity.google/favicon.svg` as `apps/web/src/assets/providers/antigravity.svg`. SHA-256: `de7911c3d206a3d2fe3d5b4e76e84b185c581d7a259406f64db247b5b824f02e`; notice updated. Focused logo and header tests: 26 passed.
- [x] 6.3: corrected the proposal rollback path to `~/.config/caztor/credentials.json`.
- [ ] 6.1 and 6.4 remain blocked by the absent S5 runner and its real-CLI evidence. The README cannot accurately document `CAZTOR_REAL_AGY` until that opt-in test exists.

### T11 full checks

- [x] `XDG_CONFIG_HOME=$(mktemp -d) npx vitest run`: 159 passed files, 6 skipped; 2865 passed tests, 31 skipped; duration 13.19 s.
- [x] `npx tsc -b`: exit 0.
- [ ] The opt-in binary check, web build, browser e2e extension, and screenshots were not run: Antigravity's runner and its scripted-stub integration cases do not exist after the T2 blocker.

### T13 native review assessment

- [x] `gentle-ai review assess --cwd . --agent opencode --base-ref bb6814e --committed-only --json`: risk `high`, 105 changed paths, 5376 changed lines, review due for `high_risk`. No native review was started because candidate consent belongs to the absent user.
