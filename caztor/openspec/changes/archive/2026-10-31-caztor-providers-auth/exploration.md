# Exploration: caztor-providers-auth

The full exploration is in Engram under `sdd/caztor-providers-auth/explore`. This file keeps the facts, options and recommendations that later phases depend on.

## Request (2026-10-26)

The user wants to choose, per provider, between an account (subscription login) and an API key; to use their subscriptions with Claude, Antigravity and ChatGPT while keeping the API option open; and to use the writing guides of the papersmith project for Caztor's agents.

## Current state

- `PROVIDER_IDS = ["claude","opencode","codex"]` in `packages/core/src/ports.ts`; `AGENT_TARGETS` in `packages/core/src/agent-targets.ts`.
- Each runner builds its child environment from an explicit allowlist (`packages/adapters-local/src/providers/*/runner.ts`). There is no auth-mode concept.
- Claude Code documents that in `-p` mode `ANTHROPIC_API_KEY` is always used when present and outranks the subscription login (https://code.claude.com/docs/en/authentication). Today Caztor passes it through, so a user with a key exported and a Pro/Max login is billed on the API without being told.
- `agents/{claude,opencode,codex}.md` share a byte-identical shared section (enforced by `agents/agents.test.ts`); its academic-style part is six short bullets.

## 1. papersmith writing guides

Source: `/home/andres/papersmith-ai` (https://github.com/Daprosero/papersmith-ai), Apache-2.0, no NOTICE file. `sections/01..10-*.md` (about 2,700 lines) give, per section: extent, function, internal sequence, what does not belong, cross-section coherence rules, citation placement and a disqualifier checklist.

- Usable in Caztor: function, sequence, extent, exclusions, disqualifiers, citation, acronym and count conventions, section ordering rationale.
- Leave out: the JSON front matter, input and fact-chain tables, binding maps, evidence sets, transposition mode, and references to papersmith's forge, experiments, Kaggle, deliberation, OpenSpec contracts and CLI; the pipeline agents (`redactor`, `style-sampler`, `contract-auditor`, ...).
- Genre risk: the guides assume an applied-research article.

Shipping options:

| Option | Summary | Verdict |
|---|---|---|
| A | Inline everything in each definition | Too large (exceeds Codex's 32 KiB, high cost per turn) |
| B | Compact shared core in the definition plus condensed per-section guides provisioned to `.caztor/guides/` with an `INDEX.md`, read on demand | Recommended |
| C | Caztor injects the relevant guide by detecting the section | High effort, heuristic |
| D | Visible `guides/` folder in the user's project | Intrusive |

Apache-2.0 obligations: ship a copy of the license, keep any attribution notices, mark each derived file as modified (condensed, front matter removed), add a NOTICE.md entry with source URL, license, commit and nature of changes.

## 2. Antigravity (`agy` 1.4.4)

Sources: `agy --help`; `~/.gemini/antigravity-cli/builtin/skills/antigravity_guide/references/cli.md`; https://antigravity.google/docs/cli/reference, https://antigravity.google/docs/cli/headless, https://antigravity.google/docs/subagents, https://antigravity.google/docs/settings?tab=cli.

- Headless: `-p`, `--output-format stream-json` with documented events `init` (cwd, tools, permission mode, model, agent), `step_update` (`step_type` user_input, agent_response, tool, checkpoint; `state` ACTIVE or DONE) and `result` (conversation id, status, response, error, usage).
- Continuation: `--conversation <id>`.
- Agent definition: `.agents/agents/<name>.md` with `name`, `description`, `tools` (array of Antigravity tool names such as `view_file`, `replace_file_content`, `write_to_file`, `list_dir`, `find_by_name`, `grep_search`), `commandExecutionPolicy`, `model`. No inline-definition flag.
- Permissions: `--mode accept-edits|auto|plan`; tool permission policy only in the user settings file.
- Isolation gap: global settings, skills, agents and MCP under `~/.gemini/` load; no documented flag or variable relocates or disables them; credentials are in the OS keyring. Only partial isolation is possible without experiments.
- Auth: Google account sign-in by default; API key only through `modelProvider: "gemini"` and `GEMINI_API_KEY` in the global settings file.
- Models from `agy models`: gemini-3.8-flash (high, medium, low), claude-sonnet-4-6, claude-opus-4-6-thinking, gpt-oss-120b-medium.
- Unverified: tool-step payloads, auth error shape, delta granularity, whether `init.tools` lists names, behavior of a disallowed tool headless, an official logo source.

## 3. Account versus API per provider

| Provider | Account | API key | Control |
|---|---|---|---|
| Claude Code | Pro/Max login or `CLAUDE_CODE_OAUTH_TOKEN` | `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN` | Strip API variables in account mode; pass only the key in API mode |
| opencode | ChatGPT Plus/Pro OAuth (verified) | Per-vendor key variables | Model prefix selects the vendor; pass only that vendor's key |
| Codex | `codex login` (documentation only) | `OPENAI_API_KEY` or `CODEX_API_KEY` (unconfirmed) | Separate `CODEX_HOME` per mode |
| Antigravity | Google account in keyring | Global settings only | Account only in this change |

API through the CLIs reuses runners, isolation and snapshots. A direct HTTP API adapter (own tool loop behind `AgentRunnerPort`) is high effort and a separate change.

Key protection: never sent to the browser (write-only routes, show set or not set), never logged (redact taps, diagnostics, history, error details), never passed to another provider, stored outside the project (for example `~/.config/caztor/credentials.json`, 0600 in a 0700 folder, symlink-checked) or read only from the server environment.

## 4. ChatGPT subscription

opencode with the ChatGPT OAuth login works and is verified. Codex is not installed and its adapter is documentation-only. Recommendation: opencode is the supported ChatGPT-subscription route; Codex stays optional until installed and verified.

## 5. Impact

- Core: fourth provider id and agent target `.agents/agents/caztor.md`; `AuthMode = "account" | "api"`; `ProjectState.authModes`; provider status per mode; session records may need the mode.
- Adapters: `providers/antigravity/{runner,mapper}.ts`; env builders take the mode and a secrets source; an Antigravity front-matter branch in `agent-definition.ts`; credential store; guides provisioner; `.agents/` project-config scan; `.agents/` and `.caztor/guides/` reserved in the file API.
- API: provider status with modes, set mode, write-only credential set and clear.
- Web: fourth provider in the selector, account or API toggle, masked key form, login hints, Antigravity model list, logo or text fallback.
- Agents: `agents/antigravity.md`; tests extended to four files.
- Specs: `agent-providers`, `agent-definitions`, `agent-chat`, `local-server-security`.

## Recommendations

1. Guides: option B, advisory, with full Apache-2.0 attribution, as a separate change.
2. Antigravity: fourth provider, account auth only, weaker isolation tier with a visible notice, built against recorded fixtures.
3. Auth modes: explicit per-provider mode through the CLIs; keys from a write-only user-level store, passed per provider and mode. Claude account mode strips API key variables.
4. Direct API adapter: a later change.
5. ChatGPT: opencode as the supported route.

## Open product decisions

1. One change or two (guides separate).
2. Where API keys live (server environment only, a 0600 file under the user's config folder, or the OS keyring).
3. Direct API adapter now, later or never.
4. Antigravity isolation level (accept partial isolation with a notice, require an experiment first, or defer).
5. How prescriptive the guides are (advisory, strong default, or a per-project switch).
