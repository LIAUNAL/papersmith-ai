# Research: caztor-mvp

schema: gentle-ai.sdd-research/v1
revision: 2
outcome: done
change: caztor-mvp
project: caozcompilator
date: 2026-10-11
supersedes: revision 1 (partial)
scope: Questions narrowed to what documentation and the open web can answer. Sub-questions that can only be closed by executing binaries were removed and are owned by an orchestrator-run local spike, which is not evidence of this research.

## 1. Questions
Q1. Which `tectonic -X compile` options relate to diagnostics and logs, and does the documentation describe any structured diagnostic output?
Q2. What does the documentation say `--untrusted` and `--hide` do, and does it claim any filesystem path containment?
Q3. What is the documented status of biblatex/biber support (issue #893), and which bibliography-related compile options are documented?
Q4. What do the official Claude Code docs specify for headless use: `-p`, `--agent`, `--output-format stream-json` with `--verbose`/`--include-partial-messages`, session resume semantics, tool restriction flags, and permission behavior in print mode?
Q5. What do the official opencode docs specify for `opencode run` flags, agent selection, session continuation, working directory, and permissions; and what third-party evidence exists for the JSON event schema (labelled as third-party)?
Q6. What do the official Codex docs specify for `codex exec`: JSONL event types, sandbox modes, stdin prompt, resume, AGENTS.md discovery, and Linux/WSL2 sandbox prerequisites?
Q7. What are the documented frontmatter schemas for Claude Code subagent files and opencode agent files, including tool and permission restriction?
Q8. Is there an open-source JavaScript/TypeScript SyncTeX parser, and what license header does its source carry?

## 2. Admission
Capability declaration received: schema `gentle-ai.sdd-research-capability/v1`; `documentation` GRANTED (WebFetch/WebSearch, official vendor docs and repos); `open-web` GRANTED (WebFetch/WebSearch, issue trackers, changelogs, third-party write-ups). No shell, no file read/write, no persistence, no binary execution.
Grants observed and used: WebFetch and WebSearch only. No other capability was used. Persistence is delegated to the orchestrator.

## 3. Sources
All accessed_at 2026-10-11. Class: D = documentation, W = open-web. "(3P)" = third-party.

| id | class | title | publisher | URL | excerpt |
|----|-------|-------|-----------|-----|---------|
| S1 | D | CLI reference | Anthropic | https://code.claude.com/docs/en/cli-reference | "--agent: Specify an agent for the current session (overrides the agent setting)"; "--tools: Restrict which built-in tools Claude can use. Use "" to disable all ... or tool names like "Bash,Edit,Read""; "--include-partial-messages: Include partial streaming events in output. Requires --print and --output-format stream-json" |
| S2 | D | Run Claude Code programmatically (headless) | Anthropic | https://code.claude.com/docs/en/headless | "Use --output-format stream-json with --verbose and --include-partial-messages to receive tokens as they're generated"; "The last line of the stream is a result message with the final response text, cost, and session metadata." |
| S3 | D | Create custom subagents | Anthropic | https://code.claude.com/docs/en/sub-agents | "Only name and description are required."; "Pass --agent <name> to start a session where the main thread itself takes on that subagent's tool restrictions and model" |
| S4 | D | Stream responses in real-time (Agent SDK) | Anthropic | https://code.claude.com/docs/en/agent-sdk/streaming-output | "StreamEvent messages containing raw API events"; event types message_start, content_block_start, content_block_delta, content_block_stop, message_delta, message_stop |
| S5 | D | opencode CLI (run) | opencode | https://opencode.ai/docs/cli/ | `opencode run [message..]`; "--format: Format: default (formatted) or json (raw JSON events)"; "--auto: Auto-approve permissions that are not explicitly denied." |
| S6 | D | opencode Agents | opencode | https://opencode.ai/docs/agents/ | "description (required)"; agent files in `.opencode/agents/`; "permission" with ask/allow/deny; "tools: Deprecated" |
| S7 | D | tectonic -X compile (CLI reference) | Tectonic project (book) | https://tectonic-typesetting.github.io/book/latest/v2cli/compile.html (same text on docs.rs https://docs.rs/crate/tectonic/0.17.0/source/docs/src/v2cli/compile.md) | "--untrusted: Input is untrusted -- disable all known-insecure features"; "--hide: Tell the engine that no file at <hide_path> exists, if it tries to read it"; "--keep-logs: Keep the log files generated during processing" |
| S8 | W | Biblatex fails due to version mismatch (issue #893) | tectonic-typesetting/tectonic (GitHub) | https://github.com/tectonic-typesetting/tectonic/issues/893 | "Found biblatex control file version 3.7, expected version 3.8."; status open, latest comment Apr 2025 |
| S9 | D | Non-interactive mode (codex exec) | OpenAI | https://learn.chatgpt.com/docs/non-interactive-mode (redirect from developers.openai.com/codex/noninteractive) | "When you enable --json, stdout becomes a JSON Lines (JSONL) stream"; "By default, codex exec runs in a read-only sandbox." |
| S10 | D | AGENTS.md | OpenAI | https://learn.chatgpt.com/docs/agent-configuration/agents-md (redirect from developers.openai.com/codex/guides/agents-md) | "walks down to the current working directory"; AGENTS.override.md then AGENTS.md; 32 KiB default cap |
| S11 | D | Sandboxing | OpenAI | https://learn.chatgpt.com/docs/sandboxing.md (redirect from developers.openai.com/codex/concepts/sandboxing.md) | "Install bubblewrap first"; fallback helper "requires support for unprivileged user namespace creation" |
| S12 | W (3P) | opencode stream-json cheatsheet | Little Bear Apps (Untether) | https://littlebearapps.com/help/untether/opencode-stream-json-cheatsheet/ | "Only five types reach stdout"; step_start, tool_use, text, step_finish, error; top-level sessionID |
| S13 | W | synctexjs.ts in LaTeX-Workshop | James-Yu/LaTeX-Workshop (GitHub) | https://raw.githubusercontent.com/James-Yu/LaTeX-Workshop/master/src/locate/synctex/synctexjs.ts | MIT License, "Copyright (c) 2018 Thomas Durieux", https://github.com/tdurieux/synctex-js; `export function parseSyncTex(pdfsyncBody: string): PdfSyncObject | undefined` |

Additional pages consulted but not used as validated evidence: opencode permissions page (https://opencode.ai/docs/permissions/), listed in claims C5.5 below via its fetch result; third-party search snippets (preview.nvim PR, Codex JSONL third-party references), used only as pointers.

## 4. Validated claims

### Q1 tectonic diagnostics
- C1.1 `-X compile` supports `--print` ("Print the engine's chatter during processing") and `--keep-logs` ("Keep the log files generated during processing"); `-Z continue-on-errors` keeps compiling after severe errors. [S7]
- C1.2 The `--print` description implies that without it engine output is not shown. [S7] (interpretation of the doc; see section 7)
- C1.3 The page documents no structured or machine-readable diagnostic option; the option list contains no such flag. [S7] (absence in the documented option list, not proof of absence in the binary)
- Out of scope for revision 2 (owned by the local spike): exact `error:` / `warning:` line prefixes, file:line format, and where --keep-logs writes the .log file.

### Q2 tectonic containment
- C2.1 Default compilation is "trusted" mode, where features such as shell-escape can be enabled on the command line; they are off unless requested (`-Z shell-escape`). [S7]
- C2.2 `--untrusted` ("Input is untrusted -- disable all known-insecure features") prevents those features from being enabled regardless of other settings such as `-Z shell-escape`. [S7]
- C2.3 `TECTONIC_UNTRUSTED_MODE` set to a non-empty value is equivalent to `--untrusted`; the docs note untrusted scripts could defeat it by clearing the variable. [S7]
- C2.4 `--hide <path>...` makes the engine behave as if no file exists at that path when it tries to read it. [S7]
- C2.5 The documentation describes `--untrusted` only in terms of insecure engine features such as shell escape. No document fetched states that it restricts `\input`, `\openin` or `\includegraphics` to the project directory, or that it blocks absolute paths. [S7] (absence of statement)

### Q3 tectonic bibliography
- C3.1 Issue #893 "Biblatex fails due to version mismatch" is open with no linked fix; the biber step fails when the installed biber and the bundled biblatex versions differ (error text quoted in the excerpt). [S8]
- C3.2 Reported workarounds: pin biber 2.17 (works with Tectonic 0.11.0; biber 2.18 fails), use package-manager builds, or point `-Z search-path` at a compatible system biblatex. The proposal to bundle biber (#1010) was unimplemented as of Jan 2024. Latest comment Apr 1, 2025. [S8]
- C3.3 `--pass` accepts `default`, `tex`, `bibtex_first`; `-Z min-crossrefs` is documented as equivalent to bibtex's `-min-crossrefs`. [S7]
- NOT validated: that BibTeX is handled by an in-process engine without a `bibtex` binary (the fetched sources do not state this explicitly; the `-Z min-crossrefs` flag is circumstantial). Status after Apr 2025 for tectonic 0.17.0 is unverified.

### Q4 Claude Code headless
- C4.1 `--agent <name>` is a documented CLI flag that selects an agent for the session and "overrides the agent setting"; `-p/--print` is the documented non-interactive flag. [S1, S3] No fetched page contains an example or sentence combining `--agent` with `-p` explicitly; the CLI reference notes `--bg` cannot combine with `-p` but lists no such conflict for `--agent`. [S1, S2] (the documentation does not state the combination; verifying it is owned by the orchestrator-run local spike)
- C4.2 When used as the session agent, a custom subagent's system prompt replaces the default Claude Code system prompt entirely (like `--system-prompt`); CLAUDE.md files still load; the agent's tool restrictions and model apply to the main thread. [S3]
- C4.3 The agent choice persists on resume: Claude Code restores the agent's tool restrictions and model with the conversation; if the agent no longer exists the session continues with default tools and a warning. [S3]
- C4.4 The system prompt is built once on the first request (including system prompt flag text) and recorded in the session; later requests, including after `--resume`/`--continue`, reuse it until compaction, unless `--system-prompt-snapshot off` is passed (v2.1.257+). Different system-prompt flags on a later launch take effect only after compaction or a new conversation. [S1]
- C4.5 `--output-format stream-json` emits newline-delimited JSON. With `--verbose --include-partial-messages` it also emits token-level events; `--include-partial-messages` requires `--print` and `stream-json`; the last line is a `result` message with final text, cost and session metadata. [S1, S2]
- C4.6 Text deltas are lines matching `type == "stream_event"` with `event.delta.type == "text_delta"` and text in `event.delta.text` (documented jq filter). [S2]
- C4.7 Stream events wrap raw API events: `message_start`, `content_block_start` (content_block.type text or tool_use, with name), `content_block_delta` (delta.type `text_delta` with `text`, or `input_json_delta` with `partial_json`), `content_block_stop`, `message_delta`, `message_stop`. Complete `assistant` messages arrive per finished content block; `result` is last. Stream events are for the main session only; subagent messages carry `parent_tool_use_id`. [S4, S2]
- C4.8 A cut tool call gets no `content_block_stop`; `message_stop` is still emitted (v2.1.290+). [S4]
- C4.9 The first event is `system/init` with session metadata (model, tools, MCP servers, plugins, optional `capabilities`); events carry `session_id`; `--output-format json` returns `session_id`; `session_id` resumes via `--resume <id>`; `--session-id <uuid>` sets an explicit UUID. [S2, S1]
- C4.10 `--api_retry` events: `system/api_retry` with `attempt`, `max_retries`, `retry_delay_ms`, `error_status`, `error`, `uuid`, `session_id`. [S2]
- C4.11 With stream-json, denials appear as `permission_denied` system messages and the final result lists `permission_denials` (with `--permission-prompts none`, v2.1.259+). [S2]
- C4.12 Tool restriction: `--tools` restricts the built-in tool set (`""` disables all; or names like "Read,Edit"), does not affect MCP tools (use `--disallowedTools "mcp__*"`); `--disallowedTools` bare names remove tools from context; `--allowedTools` only auto-approves and does not restrict availability. [S1]
- C4.13 Permission behavior: in `-p` a request that would prompt is denied when no permission host exists; `--permission-prompts none` denies and tells the model not to retry; `dontAsk` denies everything not pre-approved; `acceptEdits` auto-approves file writes. A run where nothing sets a permission mode takes the built-in starting mode, which can be `auto`; pass the mode explicitly. [S2, S1]
- C4.14 `--bare` skips auto-discovery of hooks, skills, commands, subagents, plugins, MCP, memory and CLAUDE.md; custom agents can be supplied with `--agents <json>` (file form requires v2.1.281+), but `--add-dir` does not load `.claude/agents/` in bare mode. [S2, S1]
- C4.15 `--max-turns` (print only) exits with an error at the limit; `--max-budget-usd` caps spend; `--no-session-persistence` disables saving. [S1]
- C4.16 `--restricted` removes command-running tools and WebFetch (unless named in `--tools`) and confines built-in file tools to the working directories (v2.1.248+). [S1]
- C4.17 Piped stdin is capped at 10MB in print mode; prompt may be piped. [S2]

### Q5 opencode headless
- C5.1 `opencode run [message..]` is the non-interactive command. Flags: `--format default|json` ("json (raw JSON events)"), `--agent`, `--session/-s`, `--continue/-c`, `--fork`, `--model/-m provider/model`, `--file/-f`, `--dir` ("Directory to run in, or path on the remote server when attaching"), `--attach`, `--port`, `--auto`, `--title`, `--variant`, `--thinking`, `--command`. [S5]
- C5.2 `--auto` is documented as "Auto-approve permissions that are not explicitly denied." [S5] The agent `permission` field takes ask/allow/deny per tool key. [S6] The documented pages (S5, S6) do not state how `ask` behaves in a plain `opencode run` without `--auto`. The statements previously taken from the opencode permissions page (https://opencode.ai/docs/permissions/) are removed from validated claims because that page has no source ID in section 3.
- C5.3 Event schema (THIRD PARTY, not official): five stdout types `step_start`, `tool_use`, `text`, `step_finish`, `error`; each has top-level `type`, `timestamp` (ms) and `sessionID` (`ses_...`) and a `part` object that repeats `sessionID`; `text` events carry the whole text in `part.text` (no deltas described) with `part.time`; `tool_use` is emitted only when the tool finishes, with `part.tool`, `part.callID`, `part.state.{status,input,output,title,metadata,time}`; permission rejections surface as `tool_use` with `state.status = "error"` and `state.error`; `step_finish` has optional `part.reason` ("stop" final, "tool-calls" continues), `cost`, `tokens`; `error` has `error.name` and `error.data.message`; `permission.asked`, `question.asked`, `session.compacted` are not emitted to stdout. [S12]
- NOT validated against official docs or source: the schema above (official repo run.ts could not be fetched), whether `--` is honored, whether the prompt can come from stdin, and what `ask` does in `run` without `--auto`. See section 7.

### Q6 codex headless
- C6.1 `codex exec --json` makes stdout a JSONL stream. Documented event types: `thread.started` (with `thread_id`), `turn.started`, `turn.completed` (with `usage`: `input_tokens`, `cached_input_tokens`, `output_tokens`, `reasoning_output_tokens`), `turn.failed`, `item.*` (`item.started`/`item.completed` with `item` having `id`, `type`, and for commands `command`/`status`; agent messages carry `text`), and `error`. Item types: agent messages, reasoning, command executions, file changes, MCP tool calls, web searches, plan updates. The page says it does not document every field. [S9]
- C6.2 Default sandbox in `codex exec` is read-only; `--sandbox workspace-write` allows edits; `--sandbox danger-full-access` for isolated environments; `--full-auto` is deprecated. The page documents sandbox settings only, not a separate approval mode for exec. [S9]
- C6.3 Prompt via stdin: omitting the prompt argument reads the prompt from stdin (`codex exec -` makes it explicit); with both, the prompt is the instruction and piped content is context. [S9]
- C6.4 Resume: `codex exec resume --last "<prompt>"` and `codex exec resume <SESSION_ID>`. [S9]
- C6.5 Codex requires running inside a Git repository unless `--skip-git-repo-check`; `--ephemeral` avoids saving session files; `-o/--output-last-message <path>` writes the final message; `--ignore-user-config`, `--ignore-rules` exist. [S9]
- C6.6 AGENTS.md discovery: global scope `~/.codex` (or `CODEX_HOME`) using `AGENTS.override.md` if non-empty, else `AGENTS.md`; project scope walks from the project root (typically Git root) down to the cwd, one file per directory, order `AGENTS.override.md`, `AGENTS.md`, then `project_doc_fallback_filenames`; files are concatenated root to cwd (closer overrides), stops at `project_doc_max_bytes` (default 32 KiB); built once per run. [S10]
- C6.7 Linux/WSL2 sandbox: install `bubblewrap` first; Codex uses the first `bwrap` on PATH, otherwise a bundled helper that requires unprivileged user-namespace support; it warns at startup if unavailable; Ubuntu 24.04 may need the `bwrap-userns-restrict` AppArmor profile or `sysctl kernel.apparmor_restrict_unprivileged_userns=0`. The page does not describe how a non-interactive run handles an action needing approval. [S11]
- NOT validated from primary source: exact per-item field names beyond the sample. Third-party references disagree on older naming (`item_type`/`assistant_message` before v0.44.0 versus `type`/`agent_message`).

### Q7 Agent file formats
- C7.1 Claude Code subagent files are Markdown with YAML frontmatter; only `name` (max 256 chars, no `:`) and `description` are required. Unknown fields are ignored without error. Optional fields: `tools`, `disallowedTools`, `model`, `permissionMode`, `maxTurns`, `skills`, `mcpServers`, `hooks`, `memory`, `background`, `omitClaudeMd`, `effort`, `isolation`, `color`, `initialPrompt`, `experimental`. [S3]
- C7.2 `tools` is an allowlist (comma-separated string or YAML list; inherits all if omitted); `disallowedTools` is a denylist applied first; a tool in both is removed; `mcp__<server>` patterns accepted; `AskUserQuestion`, `EnterPlanMode`, `ExitPlanMode`, `Workflow` are always removed from subagents. `permissionMode` values: `default`, `acceptEdits`, `auto`, `dontAsk`, `bypassPermissions`, `plan`, `manual`. `initialPrompt` auto-submits as the first user turn when the agent runs as the main session agent via `--agent`. [S3]
- C7.3 opencode agent files live in `.opencode/agents/` (project) or `~/.config/opencode/agents/` (global); file name becomes the agent name; only `description` is required; optional: `mode` (`primary|subagent|all`, default `all`), `model` (`provider/model-id`), `temperature`, `top_p`, `steps`, `disable`, `prompt`, `hidden`, `color`, `permission`, `tools` (deprecated); extra keys pass through to the provider. [S6]
- C7.4 opencode `permission` maps keys (`read`, `edit`, `glob`, `grep`, `list`, `bash`, `task`, `external_directory`, `webfetch`, `websearch`, `lsp`, `skill`, `question`, `doom_loop`) to `ask|allow|deny`; several keys also accept pattern objects; for `permission.task` the last matching rule wins. [S6]

### Q8 SyncTeX in JavaScript
- C8.1 LaTeX-Workshop contains `src/locate/synctex/synctexjs.ts` (plus `worker.ts`) exporting `parseSyncTex(pdfsyncBody: string): PdfSyncObject | undefined` and the types `Block` and `PdfSyncObject`. The file has no imports (self-contained) and carries an MIT license header, "Copyright (c) 2018 Thomas Durieux", pointing to https://github.com/tdurieux/synctex-js. [S13]
- C8.2 The parser takes an already-decompressed string body, so gunzip of `.synctex.gz` must be done by the caller (inferred from the signature). [S13]
- NOT validated: the license of the LaTeX-Workshop repository as a whole (LICENSE file could not be fetched; search snippets indicate MIT but are unverified); whether `tdurieux/synctex-js` is published on npm or maintained; a standalone npm package for SyncTeX was not found by search.

## 5. Contradictions, uncertainty and freshness
- Claude Code docs mention versions up to v2.1.295 (headless) and v2.1.290; installed is 2.1.296, so the documented behavior should apply. Features gated by version (e.g. `--permission-prompts` v2.1.259+, `--agents` file form v2.1.281+, `--forward-subagent-text` v2.1.211+) are all older than 2.1.296.
- Event flags: C4.5 states `--verbose` is part of the documented stream-json recipe; the CLI reference also requires `--print` for `--include-partial-messages`.
- opencode: official docs do not document the JSON schema; the only schema source is third party (S12) and it is flagged by search results as partly inconsistent with another third-party doc (jsr.io lists pending/running/failed tool statuses; the Untether cheatsheet says only completed, plus errors). Treat as unverified until a capture from opencode 1.19.0.
- The upstream opencode repository moved from sst/opencode; raw.githubusercontent paths for `sst/opencode` and `anomalyco/opencode` run.ts returned 404, so source-level confirmation was not obtained.
- Codex: OpenAI docs moved from developers.openai.com to learn.chatgpt.com (308 redirects). Codex is not installed on the target machine; documentation may reflect a newer CLI than any future install. Third-party sources disagree on historic field names (item_type vs type).
- tectonic: docs are 0.17.0-matched (docs.rs); issue #893 is still open at the last comment (Apr 2025); post-2025 developments were not found.
- LaTeX-Workshop search results showed last push April 2024 on one index; current activity unverified.

## 6. (merged into section 5)

## 7. Unsupported questions or sub-questions
None remain within the revised scope. Each of Q1-Q8 is answered by the validated claims in section 4, mapped to sources S1-S13. Where a document is silent, the claim records the silence as the finding:
- Q1: no structured diagnostic option is documented (C1.3).
- Q2: no path containment is claimed (C2.5).
- Q4: no document states the `--agent` plus `-p` combination explicitly (C4.1).
- Q5: the official opencode docs do not state how `ask` behaves in plain `run`, and do not document the JSON event schema.
- Q6: the Codex docs do not state how `exec` handles actions that need approval.

Out of scope: closed by local execution, not evidence of this research
- Exact tectonic stdout/stderr text for errors and warnings (prefixes, `l.NN`, file:line format).
- The location and name of files written by `--keep-logs`.
- Whether `--untrusted` restricts `\input`, `\openin` or `\includegraphics` to the project directory or blocks absolute paths.
- How BibTeX runs without an external `bibtex` binary.
- Whether `claude -p --agent` works in practice, the `result` and `system/init` field lists, and `--resume` combined with a different agent or system-prompt flags.
- The opencode 1.19.0 JSON event schema as captured, whether `--` is honored, whether the prompt can come from stdin, and how `ask` behaves in plain `run`.
- The codex field-level JSONL schema and approval behavior in `exec`. Codex is not installed.
- Current tectonic bibliography behavior after April 2025.

## 8. Product choices (non-authoritative suggestions)
- P1 For compile diagnostics, capture stderr with `--print`/`--keep-logs` and parse the TeX `.log` for `l.NN` style errors only after verifying the format on 0.17.0 (section 7); do not design the parser before that.
- P2 Do not rely on `--untrusted` for filesystem containment; treat it as shell-escape protection only until proven otherwise, and consider `--hide` plus running tectonic in a restricted cwd/outdir.
- P3 Prefer plain BibTeX (`.bib` + `\bibliography`) for the MVP; treat biblatex/biber as unsupported until #893 is resolved.
- P4 Claude: spawn `claude -p --output-format stream-json --verbose --include-partial-messages --agent <name> --tools "Read,Edit,Write" --permission-mode acceptEdits --permission-prompts none` (flags all documented in S1/S2; verify the combination at runtime); keep the session id from `system/init` or `result` for `--resume`. Consider `--setting-sources` and `--bare`-style isolation, noting `--bare` does not load project agents (use `--agents` JSON then).
- P5 opencode: use `opencode run --format json --agent <name> --dir <project> --session <id>`; define the agent with `permission` rules (deny `bash`, `webfetch`, `websearch`; allow `read`/`edit`/`glob`/`grep`/`list`) and avoid relying on `--auto` unless needed; confirm the event shape with a captured run before building the parser. Treat `text` as whole parts unless capture shows deltas.
- P6 codex: defer, or support behind a feature flag; document the WSL2 bubblewrap prerequisite and `--sandbox workspace-write`, and the Git-repo requirement (`--skip-git-repo-check`); `AGENTS.md` is the natural agent-definition surface.
- P7 For SyncTeX, adopt the MIT-licensed `synctexjs.ts` approach (with its attribution to Thomas Durieux) after confirming the repo license, plus a gunzip step; alternatively depend on tdurieux/synctex-js if it is published.
