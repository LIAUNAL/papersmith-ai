# Exploration: caztor-mvp

Caztor is a local-first web LaTeX compiler/editor. This file records the exploration behind the first change. The condensed copy lives in Engram under `sdd/caztor-mvp/explore`.

## Current state

- Greenfield repository: no application code and no commits.
- Node.js v26.8.2 with npm. pnpm and bun are not installed.
- `tectonic` 0.17.0 is the only LaTeX engine. pdflatex, xelatex, lualatex, latexmk, bibtex and biber are missing.
- `opencode` 1.19.0 and `claude` 2.1.296 are installed. `codex` is not installed.
- Platform: Linux on WSL2.
- The tectonic bundle is already cached under `~/.cache/Tectonic`. Packages not yet cached still need network access (inference).

Flag claims below come from official documentation, not from running the installed binaries. Items marked UNVERIFIED were not confirmed.

## Confirmed product decisions

- Four resizable vertical panes, left to right: file tree, LaTeX editor, PDF preview, chatbot.
- The chatbot is separate from the LaTeX editor. The user can edit LaTeX at any time while chatting.
- The chat has a designed UI consistent with the page, not a terminal look. The active provider's CLI logo is shown at the top of the chat panel.
- The chat is backed by the user's local CLIs. The provider is selectable: `opencode`, `claude`, `codex`.
- One agent definition `.md` per provider, describing its strengths and specialized in academic paper writing.
- Compilation runs locally. The structure must allow a later deployment to Cloudflare or similar.

## 1. Prism and Overleaf

Prism facts come from secondary sources (InfoQ, Gigazine, reviews); the OpenAI pages returned 403.

- Prism is a free, browser-only LaTeX workspace built on the acquired Crixet, with a GPT model that sees the whole project.
- It offers citation management with Zotero sync, equation conversion, automatic error checking and real-time collaboration.
- Criticism centers on low-quality AI-generated scientific text.

Adopt: whole-project context for the assistant, accept/undo semantics for AI edits, automatic error checking, citation-aware behavior, AI as optional.

Avoid: the merged code and chat area, cloud lock-in, collaboration scope, fabricated citations.

Overleaf conventions to match: file tree on the left, Recompile button, errors in red and warnings in orange in a log panel, a "stop on first error" toggle, SyncTeX jumps in both directions, draft mode.

## 2. Compile pipeline with tectonic

Source: https://tectonic-typesetting.github.io/book/latest/v2cli/compile.html

Recommended invocation, with cwd set to the project root:

```
tectonic -X compile <main.tex> --outdir <project>/.caztor/build --synctex --keep-logs --untrusted
```

- `--untrusted` disables all known-insecure features. `-Z shell-escape` is never passed.
- `--only-cached` gives an optional offline mode.
- `-Z continue-on-errors` maps to Overleaf's "keep going" behavior.
- Spawn with an argv array and `shell: false`, an environment allowlist, a timeout that kills the process group, and capped output capture.
- One compile at a time per project; debounced requests are coalesced.
- Output goes only under `.caztor/build`.

Bibliography: tectonic handles BibTeX and reruns itself. biblatex with biber is effectively unsupported (tectonic issue #893) and biber is not installed. The MVP supports BibTeX and shows a clear diagnostic when `biblatex` or `\addbibresource` is detected.

Error parsing: no documented tectonic-specific format (UNVERIFIED). Parse the kept `.log`: lines starting with `! ` are errors, followed by `l.<N>` context. Fall back to stderr `error:` and `warning:` lines.

SyncTeX: `--synctex` produces `*.synctex.gz`, but no maintained JavaScript parser was found. Jumping is deferred; the flag stays on and the artifact path stays stable.

UNVERIFIED: whether `\input{/etc/hostname}` or `\openin` can read outside the project under `--untrusted`.

## 3. Driving the provider CLIs headlessly

One process is spawned per turn, with the project root as working directory.

### claude

Sources: https://code.claude.com/docs/en/cli-reference, https://code.claude.com/docs/en/headless

- `-p` with `--output-format stream-json --verbose --include-partial-messages` for token deltas.
- Text deltas: `stream_event` → `content_block_delta` → `text_delta`. The last line is a `result` message. `session_id` appears in `system/init` and `result`.
- Continuity: `--resume <id>`, `--session-id <uuid>`.
- Agent injection: `--agent <name>` adopts a subagent file's prompt, tools and model. The `--agent` plus `-p` combination is not shown explicitly in the docs (verify in the spike). `--append-system-prompt-file` is the fallback.
- Permissions: `--permission-mode`, `--allowedTools`, `--disallowedTools`, `--tools`, `--max-turns`.
- `--bare` skips OAuth and keychain credentials, so it must not be used for subscription users.
- Without `--bare`, `-p` runs the project's `.claude/settings.json` hooks and `.mcp.json` servers with no trust dialog. This must be documented.
- System-prompt flags are recorded on the first request of a conversation and are not reapplied on `--resume`.
- SIGINT ends the turn cleanly.

### opencode

Sources: https://opencode.ai/docs/cli/, https://opencode.ai/docs/agents/, https://opencode.ai/docs/permissions/, https://opencode.ai/docs/server/

- `opencode run` with `--format json`, `-s/--session <id>`, `--agent`, `-m provider/model`, `--dir`, `--auto`.
- Event stream (third-party source, UNVERIFIED): JSONL with `step_start`, `text`, `tool_use`, `step_finish`, `error`; every event carries `sessionID`. `text` appears to be whole parts, not token deltas.
- Agent files: Markdown in `.opencode/agents/`; the filename is the agent name. Frontmatter: `description` (required), `mode`, `model`, `permission` (`edit`, `bash`, `webfetch`, `task`). The body is the system prompt.
- `external_directory` defaults to `ask` and must be denied explicitly.
- `opencode serve` (HTTP plus SSE) is a possible later optimization.
- UNVERIFIED: whether `--` is honored before the prompt.

### codex

Sources: https://learn.chatgpt.com/docs/non-interactive-mode, https://learn.chatgpt.com/docs/agent-configuration/agents-md

- `codex exec "<prompt>"`, or `-` to read the prompt from stdin; `--json` for JSONL; `-C/--cd <path>`; `-s/--sandbox read-only|workspace-write|danger-full-access`; `--skip-git-repo-check`.
- Continuity: `codex exec resume <SESSION_ID> ["prompt"]`.
- Events: `thread.started` (with `thread_id`), `turn.started|completed|failed`, `item.started|completed`, `error`.
- Instructions: `AGENTS.md` is discovered from the project root. Custom agents are TOML with no documented headless selector, so the Markdown route for codex is `AGENTS.md`.
- The binary is not installed: the adapter can only be built against fixtures.

### Chat transport options

| Approach | Pros | Cons | Effort |
|---|---|---|---|
| A. Spawn per turn, parse JSONL, SSE to the browser (recommended) | Uniform across the three CLIs; stateless server; simple Stop; native session resume | Startup cost per turn | Low to medium |
| B. Long-lived processes | Lower latency | Providers diverge; lifecycle and leak risk | High |
| C. Vendor SDKs | Typed events | The user asked for the terminal CLIs; per-vendor lock-in | Medium |

Recommendation: an `AgentProvider` interface that yields normalized events (`session`, `text_delta`, `text`, `tool_start`, `tool_end`, `file_changed`, `error`, `done`), feature detection at startup so a missing CLI shows a "not installed" state, and `{project, provider} → sessionId` persisted in `.caztor/state.json`.

## 4. Agent definition files

Canonical sources live in the Caztor repository at `agents/claude.md`, `agents/opencode.md` and `agents/codex.md`. A provisioning step writes them into the open project.

| Provider | Target path | Native format | Selection |
|---|---|---|---|
| claude | `.claude/agents/caztor.md` | Subagent frontmatter | `--agent caztor` |
| opencode | `.opencode/agents/caztor.md` | Agent frontmatter | `--agent caztor` |
| codex | `AGENTS.md` in the project root | Plain Markdown | Automatic through cwd |

- Generated content sits inside a managed marker block. A user-authored `AGENTS.md` is never overwritten outside that block.
- Provisioned paths are hidden from the file tree.
- Each agent file requires minimal scoped edits, preserves existing macros and labels, forbids fabricated citations, forbids shell commands, and reads `.caztor/build/last-compile.log` for compile feedback.

## 5. Frontend stack

| Concern | Recommendation | Deciding tradeoff |
|---|---|---|
| Framework and build | React, TypeScript, Vite; Vitest for tests | Largest ecosystem for panels, CodeMirror and PDF.js |
| Editor | CodeMirror 6 | Smaller and modular, with a merge view for agent diffs; Monaco is heavier and awkward to bundle |
| LaTeX mode | `StreamLanguage` with `stex` from `@codemirror/legacy-modes` | The community `lang-tex` package had bundling problems |
| PDF | `pdfjs-dist` used directly, version pinned | Control over reload without flicker and scroll retention |
| Split panes | `react-resizable-panels` | Layout persistence comes built in |

Provider logos are third-party trademarks: use official brand assets under their guidelines, with a text fallback.

## 6. Cloud portability

- Cloudflare Workers cannot spawn processes; `child_process` is a non-functional stub.
- Cloud compile options: a Cloudflare Container running the same tectonic (recommended eventually, same engine as local), a browser WASM TeX engine (different engine, maintenance risk), or an external compile service.
- The terminal-backed chat is local-only. A cloud substitute would be an API-based agent adapter with defined file tools.
- Hono runs on Node now and on Workers later.

Recommended seam: core logic depends only on ports.

- `CompilerPort.compile(projectRef, opts) → { pdfRef, diagnostics[], logRef }`
- `ProjectStorePort` (list, read, write, rename, delete, watch)
- `AgentRunnerPort.runTurn(...) → AsyncIterable<AgentEvent>`

Layout: npm workspaces with `packages/core`, `packages/adapters-local`, `apps/web` and `apps/server-local`. A future `apps/worker` swaps the adapters. Chat events use SSE.

## 7. Security

- Listen on `127.0.0.1` only.
- Validate `Host` and `Origin` against a fixed server-side allowlist to defeat DNS rebinding.
- Require a random per-launch token header and `Content-Type: application/json` on state-changing requests. Use SSE through `fetch` so the header can be sent. No permissive CORS.
- Path containment: resolve against one project root, reject absolute paths, `..` and NUL bytes, use `realpath`, refuse escaping symlinks, cap sizes, write atomically. Never serve `.caztor/` or provisioned agent files through the file API, except the PDF artifact.
- Commands: `spawn` with an argv array and `shell: false`, binaries from a fixed set, prompts through stdin or after `--`, timeouts with process-group kill, environment allowlist.
- Agent blast radius: shell and network tools denied by default, cwd scoped to the project, LaTeX and bibliography text treated as untrusted input.

## 8. Editor and agent concurrency

- The editor buffer is authoritative, with debounced autosave and a hash per file on the server.
- External changes hot-reload a clean buffer and open a merge view on a dirty one.
- Saves use an optimistic concurrency check and are rejected on hash mismatch.

## MVP scope

In scope:

1. Four-pane resizable layout with persisted sizes.
2. File tree with create, rename, delete and open for text files.
3. CodeMirror 6 LaTeX editor with highlighting and autosave.
4. Compile through tectonic (button and debounced auto-compile), PDF preview that keeps scroll on reload, log panel with click-to-line.
5. Chat panel with provider selector, provider logo, streamed messages, tool activity cards, Stop and per-project session continuity.
6. Three provider adapters and three agent files. Codex is built against fixtures and degrades gracefully when not installed.
7. Loopback security as described above.
8. The ports and adapters seam.

Out of scope: SyncTeX jumping, real-time collaboration, accounts, cloud deployment and cloud adapters, biblatex with biber, Zotero, git integration, templates, multi-engine selection, WASM TeX, an in-browser terminal.

## Open product decision

How agent edits reach the files: applied directly to disk with a pre-turn snapshot and undo, or proposed as diffs that the user approves one by one.

## Spike items

- Capture tectonic's real error and warning output for parser fixtures.
- Test the `\input` absolute-path escape under `--untrusted`.
- Confirm `claude -p --agent` works headlessly.
- Confirm the `opencode run --format json` event shapes on 1.19.0.
- Confirm that opencode honors `--` before the prompt.

## Risks

- Tectonic error format and escape behavior are unverified until the spike.
- The codex adapter cannot be tested locally and may drift from reality.
- opencode streaming is coarser than claude's token deltas.
- Concurrent edits by the user and the agent can lose work without hash-checked saves.
- Indirect prompt injection through document content.
- `claude -p` runs project hooks and MCP servers without a trust dialog.
- biblatex and biber documents will not compile.
- The cloud path is unproven; the seam is a mitigation, not a guarantee.
- Provider logos are trademarks.
- CLI flags change quickly: pin minimum versions and feature-detect at startup.
