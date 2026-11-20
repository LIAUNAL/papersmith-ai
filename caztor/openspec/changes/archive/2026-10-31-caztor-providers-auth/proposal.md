# Proposal: Caztor Providers Auth

## Intent

Users cannot choose between a subscription login and an API key per provider, and Antigravity is not a provider. **Security-relevant behavior change**: Claude Code documents that in print mode `ANTHROPIC_API_KEY` overrides the subscription login. Caztor passes it through today, so a user with a key exported is billed on the API without being told. Claude account mode will strip `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN` and `ANTHROPIC_BASE_URL`.

## Scope

### In Scope
- Explicit per-provider auth mode (`account` | `api`), chosen in the chat, persisted.
- Write-only credential store: `~/.config/caztor/` (0700, symlink-checked), file 0600; only "set / not set" and last four characters reach the browser; never logged or written to diagnostics, history or errors; passed only to its own provider and vendor.
- Child environments built per mode (Claude strip; opencode passes only the model vendor's key).
- Antigravity (`agy`) as fourth provider, account only, partial isolation with a permanent notice, definition `.agents/agents/caztor.md` (file read/edit tools only), runtime guard, trust gate over `.agents/`, shared academic section and guides, logo with `NOTICE.md` entry or text fallback.

### Out of Scope
- Direct HTTP API adapter (later; reuses auth mode and store).
- Codex account and API modes beyond documentation; opencode remains the ChatGPT-subscription route.
- Antigravity API mode; OS keyring.

## Capabilities

### New Capabilities
- `provider-auth`: auth modes, credential store, write-only exposure, redaction, per-provider key routing.

### Modified Capabilities
- `agent-providers`: fourth provider, detection per mode, env per mode, Antigravity isolation tier, guard, trust gate over `.agents/`.
- `agent-definitions`: fourth definition, shared section byte-identical across four, size bound.
- `agent-chat`: mode toggle, masked key form, login hints, partial-isolation notice, Antigravity header.
- `local-server-security`: credential routes write-only, never echoed.
- `project-files`: `.agents/` reserved.

`writing-guides` and `turn-snapshots` are unchanged (provider-agnostic provisioning; agent directories already excluded).

## Approach

Exploration recommendations 2, 3 and 5. Core gains `AuthMode` and a `CredentialStorePort`; runners receive mode plus secrets source. Antigravity runner and mapper are built against recorded `stream-json` fixtures.

### Slice plan (chained branches from `bb6814e`)

| # | Slice | Verified by |
|---|---|---|
| S1 | `AuthMode`, credential store adapter, redaction | Unit tests (permissions, symlink, redaction) |
| S2 | Env builders per mode, Claude strip, server routes | Env and route tests |
| S3 | Web toggle, key form, hints | Component tests |
| S4 | Antigravity definition, `.agents/` reservation, trust gate | Definition and file-API tests |
| S5 | Antigravity runner, mapper, guard, notice, logo | Fixture tests, real-CLI checks |

### Real-CLI verification policy
Free checks first: `agy --help`, `agy models`, `agy agents`. Then at most **three** real `agy -p` calls (fixture turn, disallowed-tool behavior, `--conversation` continuation), each requiring the orchestrator's explicit go-ahead in apply. No paid Claude or opencode calls.

## Affected Areas

| Area | Impact |
|------|--------|
| `packages/core/src/{ports,agent-targets,turn-service}.ts` | Modified |
| `packages/adapters-local/src/providers/{claude,opencode,codex}/`, `project-config.ts` | Modified |
| `packages/adapters-local/src/providers/antigravity/`, credential store | New |
| `apps/server-local/src/{server,agents}.ts`, `apps/web/src/chat/` | Modified |
| `agents/antigravity.md`, `agents/agents.test.ts`, `NOTICE.md`, `README.md` | New/Modified |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| `agy` loads `~/.gemini/` globals | High | Notice, guard, trust gate |
| Undocumented `agy` payloads | Med | Fixtures from bounded real calls |
| Key leak via logs or errors | Low | Redaction tests on every sink |
| Default mode for existing projects | Med | Decided in design |

## Rollback Plan

Revert slice branches in reverse order. Remove `.agents/agents/caztor.md` through hash-tracked removal; delete `~/.config/caztor/credentials.json` manually. Reverting S2 restores the API-key override, so say so in release notes.

## Dependencies

- `agy` 1.4.4 signed in; tectonic and codex unaffected.

## Success Criteria

- [ ] Claude account mode never passes the three variables (tested).
- [ ] No key appears in any response, log, history or diagnostic (tested).
- [ ] Antigravity runs a turn with read/edit tools only and shows the notice.
- [ ] Four definitions share a byte-identical section.
