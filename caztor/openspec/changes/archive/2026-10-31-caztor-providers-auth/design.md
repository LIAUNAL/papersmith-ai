# Design: Caztor Providers Auth

## Technical Approach

Core gains pure auth types and ports; adapters own the credential file, env builders and the Antigravity runner. Runners build the child env per turn (not at construction), read the key on demand just before spawning, and register it with a redactor inside `drive`. Specs: `provider-auth`, `agent-providers`, `agent-definitions`, `agent-chat`, `local-server-security`, `project-files`.

## Architecture Decisions

| # | Topic | Choice | Rejected | Rationale |
|---|---|---|---|---|
| 1 | Mode state | `ProjectState.authModes: Partial<Record<ProviderId, AuthMode>>`; missing = `account`. `SessionRecord.authMode` (missing parses as `account`); a mismatch starts a new conversation with notice "New conversation started because the sign-in method changed." | Global mode; resuming across modes | Mode is a project choice; follows the existing agentHash/isolation pattern; old sessions keep resuming |
| 2 | Status | `ProviderStatus.auth = { mode, modes, keys: {slot,set,last4?}[], login: "signed_in"\|"signed_out"\|"unknown", loginHint }` | Model call to test login | No paid calls; `unknown` unless a free documented command exists (free checks F5) |
| 3 | Store | `${XDG_CONFIG_HOME:-$HOME/.config}/caztor/credentials.json`, `{"version":1,"keys":{slot:value}}`; dir 0700, file 0600, owner = process uid, `lstat` on both (no links); write = exclusive temp 0600 + rename; existing dir/file with group/other bits is refused (no silent chmod); corrupt file: status `corrupt`, read/set/clear refuse, never overwritten | OS keyring; server-env only; auto-repair | Confirmed decision; corrupt-file rule from spec |
| 4 | Slots | `claude`, `codex`, `opencode:<vendor>`; vendor = model prefix | Vendor-shared slots | Spec cross-vendor scenario; the direct API adapter adds its own slots |
| 5 | Key lifetime | `CredentialReaderPort.read(slot)` called inside `runTurn` only; value lives in a local and the spawn env | Runner field; `TurnRequest` field | Nothing serializable holds it; core never sees a key |
| 6 | Redaction | `redactSecrets(text, secrets)` (core, pure; secrets >= 8 chars; mask `[redacted]`); `drive` gets `secrets` and scrubs tap lines, stderr tail, and every string field of emitted events; credential routes use fixed messages | Redacting in the turn service | Provider output is the only echo source; history persists redacted events |
| 7 | Antigravity guard | Allowed: `view_file`, `list_dir`, `find_by_name`, `grep_search`, `replace_file_content`, `write_to_file`. Superseded by real evidence (`docs/handoff/BLOCKED.md`): `init.tools` is ignored because it always lists about 60 tools; only tool steps are judged. Original text: `init.tools` outside set: abort before acting. `init` without a usable tool list: per-step guard only; a tool step with no recognizable name aborts (fail closed); `dropEventsOnViolation` | Trusting the definition | Global config can add tools; spec requires abort |
| 8 | Trust gate | Any file under `<root>/.agents/` except `.agents/agents/caztor.md` is a finding (bounded scan, fingerprinted as today); a modified `caztor.md` with tools outside the set or `commandExecutionPolicy` not `off` gives a `replace_definition` warning | Parsing Antigravity file kinds | No documented list of executable kinds; fail closed |
| 9 | `.agents/` | Add to `RESERVED_ROOTS` and `EXCLUDED_AT_ROOT` | Hiding only `.agents/agents/` | Confirmed: snapshots already skip any path failing `parseRelPath` (`snapshot-store.ts:177`); explicit listing documents it |
| 10 | Logo | Candidates, in order: icon shipped inside the `agy` install, `https://antigravity.google` favicon/brand asset; byte-for-byte with SHA-256 in `NOTICE.md`; else `logo: null` (text "Antigravity") | Drawing one | Same policy as Codex |

## Child Environment

| Provider | account | api |
|---|---|---|
| Claude | base + `CLAUDE_CODE_OAUTH_TOKEN`, `CLAUDE_CONFIG_DIR`; strip `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL` | base + `CLAUDE_CONFIG_DIR` + `ANTHROPIC_API_KEY`=stored; server-env Anthropic vars and OAuth token never passed |
| opencode | base, no vendor key or base-URL vars (an exported key cannot override the OAuth login) | base + only the vendor's variable (`openai`→`OPENAI_API_KEY`, `anthropic`→`ANTHROPIC_API_KEY`, `google`→`GOOGLE_GENERATIVE_AI_API_KEY`, `openrouter`, `groq`, `xai`, `mistral`, `deepseek`, `opencode`→`OPENCODE_API_KEY`); `XDG_DATA_HOME=<root>/.caztor/opencode-data-api` (0700, link-checked) so `auth.json` logins cannot win; unknown vendor refused |
| Codex (docs only) | base + `CODEX_HOME`; strip `CODEX_API_KEY`, `OPENAI_API_KEY`, `OPENAI_BASE_URL` | base + `CODEX_HOME` + `CODEX_API_KEY`=stored |
| Antigravity | base + `XDG_RUNTIME_DIR`, `DBUS_SESSION_BUS_ADDRESS` (keyring); no `GEMINI_*`/`GOOGLE_*` | refused (`mode_unsupported`) |

Base = existing `PATH, HOME, locale, TMPDIR, proxies, certificates`, `NO_COLOR=1`.

## Antigravity Adapter

- argv: `agy -p --output-format stream-json --mode accept-edits --agent caztor [--model M] [--conversation ID]`, no shell, prompt on stdin (F1 confirms; fallback `-p -- <prompt>` only if stdin is unsupported). Isolation tier `P1`.
- Mapper: `init` → guard input; `step_update` `agent_response` ACTIVE → `text_delta`, DONE → `text`; `tool` ACTIVE → `tool_start` (kind: view_file read, list/find/grep search, replace edit, write write), DONE → `tool_end`; `user_input`/`checkpoint` ignored; `result` → `session` (conversation id, regex-checked), `usage`, `done`; error result with auth shape → `auth` + login hint.
- Detection: `agy --version`, then `agy models` (30 s cache), both in a `mkdtemp` cwd; models parsed by line regex.
- Stop: shared `drive` escalation and `forceStop` on the process group.
- Notice, every turn and in the header: "Antigravity runs with partial isolation: your global Antigravity settings, skills, agents and MCP servers in ~/.gemini/ may load, and Caztor cannot turn them off. Caztor allows only file reading and editing tools and stops the turn if another tool appears."
- Definition `agents/antigravity.md`: `name: caztor`, `description`, `tools: [view_file, list_dir, find_by_name, grep_search, replace_file_content, write_to_file]` (one-line flow list), `commandExecutionPolicy: off`, `model: inherit`. `parseAgentFile` branch splits the bracketed list. Shared section byte-identical across four; it gains `.agents/` among folders to leave alone; guides are provisioned unchanged.

## Data Flow

    web toggle/key form ──→ api routes ──→ CredentialStore (~/.config/caztor)
                                  └────→ StatePort.authModes
    turn start ─→ TurnService (mode, key set?) ─→ runner.runTurn(authMode)
                    runner: reader.read(slot) ─→ buildEnv(mode,key) ─→ drive(secrets) ─→ redacted events

## File Changes

| File | Action |
|---|---|
| `packages/core/src/{ports,auth,redact}.ts` | Modify/Create: `AuthMode`, slots, `CredentialStorePort`, `CredentialReaderPort`, `redactSecrets`, `TurnRequest.authMode`, `antigravity` id |
| `packages/core/src/{agent-targets,paths,turn-service}.ts` | Modify: target, reserved root, refusal `api_key_missing`, session mode |
| `packages/adapters-local/src/credential-store.ts`, `infra.ts` (`FsStats.uid`) | Create/Modify |
| `packages/adapters-local/src/providers/{claude,opencode,codex}/runner.ts`, `drive.ts` | Modify |
| `packages/adapters-local/src/providers/antigravity/{runner,mapper}.ts` | Create |
| `packages/adapters-local/src/{agent-definition,provisioner,state-store,snapshot-store}.ts`, `providers/project-config.ts` | Modify |
| `packages/api/src/routes/{providers,credentials}.ts` | Modify/Create |
| `apps/server-local/src/server.ts` | Modify: store + reader wiring, fourth runner |
| `apps/web/src/chat/{providers.ts,AuthModeToggle,KeyForm,LoginHint}` | Modify/Create |
| `agents/antigravity.md`, `agents/agents.test.ts`, `NOTICE.md`, `README.md` | Create/Modify |

## Interfaces / Contracts

- `PUT /api/providers/:id/auth-mode {mode}` → 409 `api_key_missing`, 400 `mode_unsupported`.
- `PUT /api/credentials/:slot {key}` (1..512 printable ASCII, no whitespace) and `DELETE /api/credentials/:slot` → `{slot,set,last4?}` only; `last4` only for keys >= 12 chars; `Cache-Control: no-store`; no GET of a value. Existing gate already enforces Host, Origin, token, JSON content type and body size.
- Login hints: Claude "run `claude`, then `/login`"; opencode `opencode providers login` (F5 confirms name); Codex `codex login`; Antigravity "run `agy` and follow the sign-in prompts".

## Testing Strategy

Slices S1–S5 are kept. Adjustments: S1 also carries the core types and `authModes` state; S2 carries the turn-service refusal and session mode; the `antigravity` provider id lands in S4 (with `logo: null` in the web table), so S1–S3 stay three-provider.

| Slice | Tests (RED first, `npx vitest run`) |
|---|---|
| S1 types, store, redaction | Fake FS: 0700/0600 creation, wrong mode, uid, link dir/file, corrupt, atomic temp cleanup; redaction table; state sanitize |
| S2 env, turn, routes | Env table per provider/mode (exported key stripped), vendor isolation, key absent from events/history/errors, session mode reset, route echo/token/content-type/Origin |
| S3 web | Toggle, not-configured state, field emptied on success and failure, hints |
| S4 definition, reservation, gate | Four definitions, byte-identical shared section, parser branch, provisioner create/skip/remove, `.agents/` hidden, gate inert/executable |
| S5 runner | Sanitized fixtures: mapping, guard (init and step), notice, stop, detection, continuation |

Real CLI: free F1 `agy --help`, F2 `agy --version`, F3 `agy models` under the built env (keyring reachable), F4 `agy agents` in a scratch project, F5 `claude --help`/`opencode --help`/`agy --help` for login-status commands. Then, each only with the orchestrator's go-ahead: R1 read-and-edit turn (records `init`, step and `result` payloads), R2 prompt asking to run `ls` (records whether a shell tool is listed, attempted or refused), R3 `--conversation` with R1's id. Fixtures: paths → `<root>`, ids → fixed fakes, account data removed; raw output never committed.

## Threat Matrix

| Boundary | Applicability |
|---|---|
| Documentation-like paths | N/A: no file classification by name |
| Git repository selection, commit, push, PR | N/A: no VCS automation |

Subprocess boundary (applicable, project rows): no shell; IDs regex-checked before argv; model leading dash refused; prompt on stdin; keys only in env, never argv. RED tests: argv for hostile session id/model, env per mode, key not in argv.

## Migration / Rollout

No data migration: missing `authModes`/`authMode` read as `account`. Release note: Claude account mode now ignores an exported `ANTHROPIC_API_KEY`.

## Open Questions

- [ ] If `init.tools` always lists every built-in tool, Antigravity is unusable under decision 7 (known after R1).
- [ ] Whether `agy` has `--agent` and reads stdin (F1); whether a project `.gemini/` folder is loaded.
- [ ] Split `text_delta` chunks can show a key briefly before the redacted `text` replaces them.
