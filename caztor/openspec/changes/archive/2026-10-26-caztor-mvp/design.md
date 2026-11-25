# Design: Caztor MVP

Revision 2 (2026-10-11): reconciled with the ten capability specs, three confirmed user decisions and the phase-contract validator findings. Spec vocabulary is used throughout.

Evidence tags: **[O]** observed in the local spike, **[D]** documented (research claim id), **[V]** unverified, to verify in the first task of the owning slice (fallback given). Where spike and documentation differ, the spike wins.

Size note: the phase skill asks for under 800 words. This design exceeds it on purpose because the launch request requires exact signatures, argv and twelve decisions.

## Technical Approach

Ports and adapters over npm workspaces. `packages/core` holds pure TypeScript (domain types, ports, coordinators, reducers) and compiles without Node types. `packages/api` is a runtime-agnostic Hono app factory that receives ports. `packages/adapters-local` implements the ports by spawning binaries and touching the disk through three injected infrastructure interfaces (`ProcessSpawner`, `Clock`, `FileSystem`). `apps/server-local` wires adapters into the app and binds loopback. `apps/web` is a static React app. One process is spawned per compile and per chat turn. A chat turn is wrapped by a core `TurnService`: provision, snapshot, run, diff, attribute, optional undo.

```
apps/web ──HTTP/SSE──> packages/api ──ports──> packages/core
                            ^                       ^
apps/server-local ──wires── packages/adapters-local ┘ (tectonic, claude, opencode, codex, fs)
```

## Architecture Decisions

### D1. Stack and workspace

| Concern | Choice | Rejected | Rationale |
|---|---|---|---|
| Workspace | npm workspaces: `packages/{core,api,adapters-local}`, `apps/{server-local,web}`, `agents/` | pnpm, single package | npm is the only manager installed; package boundaries enforce the port seam |
| Language | TypeScript strict, ESM, `erasableSyntaxOnly`, `.ts` import specifiers | CommonJS, enums | Lets Node run sources directly |
| Server run | `node apps/server-local/src/main.ts` using Node 26 type stripping **[V]**; fallback `tsx` dev dependency | Build step with `tsc` output | No build for the server |
| HTTP | Hono; `@hono/node-server` locally | Express, Fastify | Same app object runs on Workers |
| New package `packages/api` | Route and middleware factory `createApp(deps, security)` | Routes inside `apps/server-local` (proposal) | A future `apps/worker` imports it unchanged |
| Frontend | React, Vite, plain CSS with custom-property tokens | Next.js, Tailwind | Static output; fewest dependencies |
| Editor | CodeMirror 6; `StreamLanguage` + `stex` legacy mode for `.tex .sty .cls`; an in-repo `StreamLanguage` BibTeX tokenizer for `.bib` (entry types, keys, fields, strings, comments); `@codemirror/merge` | Monaco; a third-party BibTeX package | Size and bundling; no maintained BibTeX mode was identified |
| PDF | `pdfjs-dist` pinned exactly; bytes fetched by the API client and passed as `data` | Browser viewer in an `<iframe>` | Token header can be sent; scroll and zoom are controlled |
| Panes | `react-resizable-panels` | Custom splitter | Resize and persistence built in |
| Tests | Vitest projects (node, jsdom), Testing Library | Jest | Shares Vite config |
| Serving | Production: server serves `apps/web/dist` same-origin. Dev: Vite proxies `/api` (`changeOrigin: true`) | Separate origins with CORS | No CORS surface |
| Launch | `npm start -- <projectDir>`; one project per process; default port 4317, next free port if busy | Multi-project server | One containment root |

Layout: the pane order is fixed as file tree, editor, PDF preview, chat (not reorderable). Defaults 15/35/30/20 percent. Minimum widths 160, 280, 280 and 300 px, converted to percentages on container resize if the library accepts only percentages **[V]**. Sizes persist in `localStorage` through a validating storage wrapper: a saved layout that is unreadable, not four numbers, or below a minimum is discarded and defaults apply without an error.

Cloudflare portability:

| Runs unchanged | Replaced by another adapter |
|---|---|
| `packages/core`; `packages/api` (Hono, Web APIs only); `apps/web` (Pages) | `adapters-local` → cloud adapters: R2/Durable Object project store, state and snapshots; container-hosted tectonic compiler; API-based agent runner (terminal CLIs are local-only) |
| SSE framing, event unions, reducers | `apps/server-local` → `apps/worker`; local security middleware → account auth |

### D2. Ports

See Interfaces: `ProjectStorePort`, `CompilerPort`, `AgentRunnerPort`, `SnapshotPort`, `ProvisionerPort`, `StatePort`. Core `tsconfig` uses `lib: ["ES2023","WebWorker"]` and `types: []`, so `process`, `fs` and `Buffer` do not typecheck; a test also scans `packages/core/src` and `packages/api/src` for `node:` and builtin imports.

### D3. Compile pipeline

| Item | Decision |
|---|---|
| argv | `tectonic -X compile <main> --outdir .caztor/build/out --keep-logs --untrusted` **[O]**; cwd = project root; adapter creates the outdir. `--synctex` is **not passed**: SyncTeX is out of scope and its output was never observed (the flag was only seen to be accepted) |
| Environment | Allowlist: `PATH HOME LANG LC_ALL TMPDIR XDG_CACHE_HOME` and proxy variables; adds `TECTONIC_UNTRUSTED_MODE=1` **[D C2.3]**. `-Z shell-escape` is never passed |
| Error mode | Stop-on-error off (default): add `-Z continue-on-errors`; exit 0 and a PDF even with errors **[O]**. On: no flag; exit 1 and no PDF **[O]**. Rejected: always halting, because one typo would blank the preview. The toggle persists in project state |
| Artifacts | Tectonic writes only to `build/out/`. When a run produces a PDF the adapter atomically promotes it to `build/preview.pdf` and bumps `rev`; the log is copied to `build/last-compile.log`. A run without a PDF keeps the previous preview, which the UI marks out of date |
| Errors | stderr lines `^error: (.+):(\d+): (.*)$` **[O]**. Wrapper lines `error: something bad happened inside XeTeX; its output follows:` and `error: the XeTeX engine had an unrecoverable error` **[O]** are dropped when a located error exists; the transcript between `=====` rules **[O]** is skipped; `caused by:` lines become detail; any other `error:` line is a file-less error |
| Warnings | stderr `warning:` lines (the "errors were issued ... but were ignored" marker is consumed) plus `.log` `LaTeX Warning:` / `Package X Warning:` with `on input line N` **[O: only in the log]**; wrapped lines rejoined; file resolved by a best-effort open-file stack, otherwise no jump action |
| Status (spec terms) | Never from the exit code alone: `cancelled` or `timed-out` if killed; `failed` if this run produced no PDF; `failed-with-errors` if a PDF exists and at least one error was reported; else `success` (warnings allowed). Non-zero exit with no parsed error yields one synthetic error with the stderr tail |
| Offline first run | If the run fails with no located TeX error and stderr matches download-failure patterns (fixture recorded offline, no tokens) **[V]**, a `caztor` error reads "Could not download LaTeX support files. The first compile needs a network connection." with the raw text as detail. Fallback if patterns are unreliable: attach that hint to any failure that occurs during the `downloading` phase |
| biblatex | Core pre-scan of project `.tex` for `biblatex` or `\addbibresource` adds a notice: biber is unsupported, use BibTeX |
| Phases | `note: downloading` → `downloading` (UI: "Preparing: downloading support files", distinct from compiling) **[O]**; `note: Running TeX` and `note: Rerunning TeX because` → `typesetting` **[O]**; `note: Running BibTeX on` → `bibliography` **[O]**; `note: Running xdvipdfmx` and `note: Writing` → `finalizing` **[O]**. Unknown notes are ignored |
| Time limit and kill | 180 s wall clock, extended to 600 s once `downloading` is seen. Spawn `detached`, kill the process group: SIGTERM, then SIGKILL after 2 s. stderr capped at 2 MB, lines at 4 KB |
| Single run, queue, cancel | Core `CompileCoordinator`: one running compile per project. A request made while one runs is queued as the single follow-up (a newer request replaces the queued one) and the UI says "queued". **Cancel**: the toolbar's Compile button becomes Cancel while running; `POST /api/compile/cancel` aborts the running compile (status `cancelled`) and clears the queued one |
| Auto-compile | Optional, on by default: 1.5 s after a successful save |
| PDF serving | `GET /api/compile/pdf?rev=`, `application/pdf`, `no-store`, token required |

Preview: scroll position (page and offset within the page) and zoom are kept in component state across a reload of the document and stored in `localStorage` per project. With no PDF, an empty state invites the user to compile.

### D4. Tectonic read containment (confirmed by the user)

`--untrusted` blocks shell-escape only; `\input` of absolute and `../` paths succeeds **[O]**.

| Option | Tradeoff | Decision |
|---|---|---|
| Mandatory bubblewrap | Real containment; user namespaces may be blocked on other machines | Rejected: the MVP must not depend on it |
| Accepted risk, disclosed | Always works; a document can embed any file the user can read into the local PDF and log | **Baseline (confirmed)** |
| Opt-in sandbox behind feature detection | Containment where available; the bind profile is untested | **Last slice**, off by default |

Mitigations needing no tool: shell-escape off; tectonic's `accessing absolute path` warning **[O]** and any log-opened file resolving outside the project become a prominent "reads a file outside the project" diagnostic (best effort; `../` gives no engine warning, and `\openin` and graphics are not covered).

Limits that the disclosure states plainly (no claim of "no exfiltration path"): the agent can read what the engine wrote into the PDF or log; anything an agent reads is sent to the model provider; Claude's `Read` is confined to the project only if `--restricted` works as documented; Codex runs with `--sandbox workspace-write` and can execute commands.

Disclosure (spec "Disclosed limits"): a first-use notice when the app opens, acknowledged once per project and stored in project state, plus a README security section. Text: "Caztor runs the LaTeX engine and the selected AI CLI as your user. Compiling can read any file you can read (shell escape stays disabled). Agents use file tools, their reads may not be confined to the project, what they read is sent to the model provider, and Codex can run commands inside its own sandbox. Open only projects you trust."

Sandbox slice: `bwrap` is present on this machine at `/usr/bin/bwrap` **[O]**, but a startup probe still runs a trivial `bwrap` command; only if it succeeds does the setting "Sandboxed compile (experimental)" appear. It wraps the same argv through a `CommandWrapper` (project read-only, `build/` and the tectonic cache writable, network shared) **[V]**; a sandbox start failure is reported with an offer to disable it.

### D5. Isolation from user-global CLI configuration (confirmed product behavior)

The chat agent runs isolated: no user hooks, no MCP servers, no global `CLAUDE.md`, file read and edit tools only. The user accepted that personal tools are unavailable to the agent and that opencode isolation may hide custom providers. Observed cost without isolation: about 25k tokens and USD 0.22 for a one-word Claude turn **[O]**.

| Provider | Setting | Evidence | Fallback |
|---|---|---|---|
| claude | Agent `tools: Read, Edit, Write, Glob, Grep` | **[O]** `system/init.tools` matched exactly | n/a |
| claude | `--tools Read,Edit,Write,Glob,Grep --disallowedTools "mcp__*"` | **[D C4.12]**, **[V]** | Drop; rely on agent frontmatter |
| claude | `--restricted` | **[D C4.16]**, **[V]** | Drop; the disclosure already says reads are not confined |
| claude | `--strict-mcp-config` with no MCP config | Not in research claims, **[V]** | Drop; `mcp__*` denial remains |
| claude | **Tier I1 (preferred, the product behavior)**: no on-disk setting sources (`--setting-sources`, exact empty syntax **[V]**, not in research claims) plus the agent inline through `--agents <json>` **[D C4.14]** built from the provisioned file | **[V]** | Tier I2: `--setting-sources project` with the file agent (agent loading **[O]**); if the project has `.claude/settings*.json` or `.mcp.json`, a one-time confirmation that its hooks and servers will run. Tier I3: observed argv only, with a persistent notice that isolation is unavailable and cost is higher |
| claude | `--bare` | Rejected: skips OAuth and keychain credentials (exploration section 3) and project agents **[D C4.14]** | n/a |
| opencode | Agent `mode: primary`, `permission: {edit: allow, bash: deny, webfetch: deny, external_directory: deny}` | **[O]** | n/a |
| opencode | Additional keys: allow `read glob grep list`; deny `websearch task skill question` | **[D C7.4]**, **[V]** | Keep only the observed four keys |
| opencode | `XDG_CONFIG_HOME=<project>/.caztor/opencode-xdg` to skip global config, plugins and MCP | Not in research claims, **[V]**; hides custom providers (accepted) | No override; a notice explains that global plugins load |
| codex | `--ignore-user-config` | **[D C6.5]**, untestable | Omit |

The tier is a constant chosen after verification, not probed at runtime. Whatever the flags do, the Claude adapter asserts on `system/init`: a tool outside the allowlist aborts the turn with `isolation_failed`; non-empty `mcp_servers` produces a notice. Codex is the exception to "file tools only": no documented flag disables command execution, so the limit is disclosed.

### D6. Provider adapters

All adapters: fixed binary names resolved once to absolute paths, argv arrays, `shell: false`, cwd = project root, environment allowlist plus provider prefixes (`ANTHROPIC_ CLAUDE_`, `OPENCODE_ OPENAI_`, `CODEX_`), `NO_COLOR=1`, prompt on stdin (never in argv), ANSI stripped, lines over 1 MB dropped. Unrecognized event types and single unparseable lines are ignored; a stream that ends without a terminal event, or 20 consecutive unparseable lines, ends the turn with `malformed_output`. Exactly one `done`, last.

| | claude | opencode | codex (fixtures only) |
|---|---|---|---|
| argv | `claude -p --output-format stream-json --verbose --include-partial-messages --agent caztor --permission-mode acceptEdits` **[O]** + D5 flags + `[--model m] [--resume id]` | `opencode run --format json --agent caztor -m <provider/model> --dir <project> [-s id]` **[O]** | `codex exec --json --sandbox workspace-write --skip-git-repo-check --ignore-user-config -` **[D C6.1-C6.5]** + `[-m m]` (not in research claims, **[V]**; fallback: omit and disable the Codex model selector). `-C` is not used: the spawn cwd is the project root |
| Prompt | stdin **[O]** | stdin **[O]**; fallback `-- <prompt>` **[O]** | stdin **[D C6.3]** |
| Session | `session_id` from `system/init` **[O]**; reuse `--resume` **[D C4.9, V]** | top-level `sessionID`; reuse `-s` **[O]** | `thread.started.thread_id`; `codex exec resume <id>` **[D C6.4, V]** |
| Text | `text_delta` → `text_delta`; completed `assistant` text block → `text` | `text` event → one whole `text` (no simulated streaming) | `item.completed` agent message → `text` |
| Tools | `content_block_start` tool_use → `tool_start`; `input_json_delta` accumulated, on block stop → `tool_update` with path; `user` tool_result → `tool_end` | `tool_use` (already finished) → `tool_start` then `tool_end`; `state.status` error → `failed` | `item.started` → `tool_start`; `item.completed` → `tool_end`; accepts `type` and legacy `item_type` |
| Ignored | hooks, status, thinking, signature, rate limit, unknown | `step_start`, unknown | reasoning, plan, unknown |
| End | `result`: `is_error` → `error`; else `done` with cost; `permission_denials` → notice | `step_finish` accumulates usage; exit 0 → `done` | `turn.completed` → `done`; `turn.failed`/`error` → `error` |
| Errors | Exit without `result` → `provider_error` with stderr tail | `error` event with exit 1 **[O]**: 401/403 → `auth` or `model_unavailable`, 429 → `rate_limited`; message from `error.data.message` | Mapped by documented shape |
| Model | Optional; CLI default | **Required**: without one the turn is not started and the user is asked to set a model **[O: free tier fails headless]**; list from `opencode models` **[V]**, fallback free text | Optional |
| Detect | `<bin> --version`, 5 s limit; missing binary → unavailable, "not installed"; older than the tested version → warning. Cached; manual re-check |

Stop: abort → SIGINT to the process group (documented in exploration, **[V]**), SIGTERM after 3 s, SIGKILL after 2 s more. The turn ends **cancelled** (`done{reason:"cancelled"}`); the snapshot diff still runs. One active turn per project: a second send is rejected with 409 and the composer is disabled while a turn runs.

Persistence (`StatePort`, `.caztor/state.json`): selected provider per project, per-provider model, per-provider session record `{sessionId, agentHash, isolation}`. Because Claude records the agent on the first request and does not reapply it on `--resume` **[D C4.3, C4.4]**, a session is resumed only when the stored `agentHash` and `isolation` equal the current ones; otherwise a new session starts and the chat shows "New conversation started because the agent definition changed". The rule applies to all providers.

### D7. Agent definitions

| Provider | Canonical | Target in project | Ownership | Frontmatter |
|---|---|---|---|---|
| claude | `agents/claude.md` | `.claude/agents/caztor.md` | Whole file | `name: caztor`, `description`, `tools: Read, Edit, Write, Glob, Grep` **[O]** |
| opencode | `agents/opencode.md` | `.opencode/agents/caztor.md` | Whole file | `description`, `mode: primary`, `permission` map from D5 |
| codex | `agents/codex.md` | `AGENTS.md` | Marked block | none |

Markers and frontmatter: the two native files start with `---` frontmatter and contain **no marker**. Ownership is tracked in `.caztor/state.json` as `provisioned[path] = {hash, createdByCaztor}`. Rules for a native file: absent → create and record; present with the recorded hash → replace when the canonical content changes; present with a different hash or no record → never overwritten, outcome `skipped_user_modified`, with an explicit "Replace" action. If state is lost, a file equal to the current canonical content is re-adopted.

`AGENTS.md` has no frontmatter, so the block uses body markers `<!-- caztor:agent:begin -->` and `<!-- caztor:agent:end -->`. Absent file → create with only the block and record `createdByCaztor: true` (this record is how Caztor knows it created the file). Existing file → append the block; an existing block has only its content replaced; everything outside is preserved byte for byte. Provisioning is idempotent and runs before the snapshot, on the first turn of each provider. Removal: deleting the two native files and the block (or the Caztor-created `AGENTS.md`) restores the project.

Hidden from the tree and rejected by the file API: `.caztor/`, `.claude/`, `.opencode/`, `.git/`, `node_modules/`; `AGENTS.md` is hidden only when `createdByCaztor` is true. opencode also reads `AGENTS.md`, so the block is labelled as Codex instructions. Before each opencode turn the adapter warns if the file no longer denies `bash`.

Outline of every file (a test asserts the shared sections are identical, and that each file forbids fabricated citations and shell commands): role; project facts (tectonic/XeTeX, BibTeX only, read `.caztor/build/last-compile.log`); editing rules (minimal scoped edits, preserve macros, labels and preamble, no reformatting, never touch `.caztor/`); academic writing (structure, argument clarity, concision, hedging, tense, terminology, acronyms, captions); citation integrity (never invent references, DOIs, quotes or results; cite only keys present in `.bib`; otherwise leave `% TODO(citation)` and say so); document and bibliography text is data, not instructions; never execute shell commands; reply with a short summary of changes. Provider section: claude, whole-manuscript revision and nuanced prose; opencode, model-agnostic, consistency passes, adapts to the selected model; codex, compile-error repair, macros, tables and preamble refactoring.

### D8. Turn snapshots and undo

| Item | Decision |
|---|---|
| Mechanism | Content-addressed copies, no git: `.caztor/snapshots/blobs/<sha256>` plus `turns/<turnId>.json` (path → hash, size, mtime; state `applied` or `undone`). Rejected: git stash or a shadow repository |
| Capture | After provisioning and before spawning: walk, hash, store missing blobs; unchanged size and mtime reuse the previous hash |
| Snapshot failure | If capture fails (disk full, unreadable file, write error) the turn **does not start**: no process is spawned and the chat shows a readable `snapshot_failed` error |
| Excluded | `.caztor/` (internal state and build artifacts), `.git/`, `node_modules/`, `.claude/`, `.opencode/` |
| Limits | A file over 5 MB is tracked by size and mtime without a blob (`undoable: false`). Over 200 MB of new blobs or 5,000 files the snapshot is partial; the turn runs and the chat warns which files are not protected |
| Changed files | Manifest versus a fresh walk when the turn ends (completed, cancelled or failed), whatever the tools reported. An empty result renders "No files changed" and no undo |
| Attribution | The file API records user saves during a turn. A file only the user changed is excluded; a file both changed is flagged `mixed` and treated as a conflict on undo |
| Retention and order | The last 20 turns are retained; discarding the oldest marks its undo unavailable; unreferenced blobs are collected. Undo is a **last-in-first-out stack over the retained turns**: only the latest `applied` turn is undoable, and once it is undone the previous one becomes undoable |
| Undo | Preflight: each file's current hash must equal the recorded after-hash. Otherwise nothing is written and a warning names the files; the user chooses Cancel, "Undo the rest and keep my edits" or "Overwrite my edits". A pre-undo snapshot is always taken. Created files are removed, deleted files restored |
| Session | The next prompt carries a note listing the reverted files |

### D9. Editor and agent concurrency

SHA-256 through `crypto.subtle`, formatted `sha256:<hex>`. Each buffer keeps `baseHash` and a state: saved, saving, dirty, conflict, error. Autosave (800 ms idle) sends `baseHash`; a mismatch returns 409 with the current hash; any other failure keeps the buffer dirty and shows the error state. External changes arrive on `/api/events` from a best-effort recursive watcher plus a forced rescan after every turn and undo. Event hash equal to `baseHash`: ignore. Clean buffer: reload, keep cursor and scroll (this also covers undo). Dirty buffer: banner with "Keep mine", "Load disk version", "Copy my text" and "Compare" (merge view); autosave pauses until resolved. The editor is never locked by chat state.

### D10. HTTP API and streaming

| Method and path | Purpose |
|---|---|
| `GET /api/session`, `PATCH /api/settings` | Project, engine, sandbox availability, settings (stop-on-error, auto-compile, sandbox, main file, disclosure acknowledged) |
| `GET /api/files` | Tree of files and folders |
| `GET` / `PUT /api/files/content?path=` | Read (hash returned); write `{content, baseHash}` → 200 or 409 |
| `POST /api/files` | Create `{path, kind: "file" or "dir"}`; 409 with a readable message on a name collision |
| `POST /api/files/rename`, `DELETE /api/files?path=` | Rename or delete a file or folder (folder delete is recursive after UI confirmation) |
| `POST /api/files/upload?path=` | Raw body, `Content-Type: application/octet-stream`, up to 20 MB, 409 if the name exists |
| `GET /api/events` | SSE: `file_changed`, compile events |
| `POST /api/compile`, `POST /api/compile/cancel` | Start or queue (202 `{compileId, queued}`); cancel |
| `GET /api/compile/status`, `/pdf?rev=`, `/log` | Last result and artifacts |
| `GET /api/providers`, `POST /api/providers/recheck` | Detection |
| `PUT /api/providers/selected`, `PUT /api/providers/:id/model` | Persisted provider and model |
| `POST /api/chat/turns` | Response body is the turn's SSE stream |
| `POST /api/chat/turns/:id/stop`, `/undo` | Stop; undo `{mode: strict, skip_conflicts, force}` |
| `GET /api/chat/history?provider=`, `POST /api/chat/sessions/reset` | Transcript from `.caztor/chat/<provider>.jsonl`; new chat |

SSE: `id: <seq>`, `event: <type>`, `data: <json>`, comment heartbeat every 15 s, read with `fetch` so the token header is sent. Chat event names are the `TurnEvent` types; compile event names are `compile.started`, `compile.phase`, `compile.finished`. A dropped chat connection does not stop the turn.

Security middleware, in order: bind `127.0.0.1` only; `Host` must be `127.0.0.1:<port>` or `localhost:<port>`; `Origin`, when present, must be in the fixed allowlist and is required on non-GET; every `/api/*` request, reads included, requires `X-Caztor-Token`; non-GET requires `Content-Type: application/json`, except the upload route which requires `application/octet-stream`; no CORS headers and preflight refused; body limit 2 MB (20 MB for upload).

Token: 32 random bytes per launch, constant-time compare. Production: generated in process, kept in memory only, never written to disk or read from the environment. Development only (`CAZTOR_DEV=1`): the dev script generates a token for that run and passes it as `CAZTOR_TOKEN` to both the server and Vite; the variable is ignored without `CAZTOR_DEV=1`. Delivery to the page: `index.html` contains `<meta name="caztor-token" content="__CAZTOR_TOKEN__">`; the server (or Vite's `transformIndexHtml` in dev) replaces the placeholder and the app reads the tag. No inline script is used.

CSP (production responses): `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; worker-src 'self' blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'`, plus `nosniff` and `no-referrer`. `'unsafe-inline'` is allowed for styles only, because CodeMirror and the pane library inject style elements; scripts stay strict. Tightening to a style nonce is **[V]** and not required.

Path containment: core `parseRelPath` rejects empty, absolute, backslash, control or NUL characters, `.`/`..` segments, a path that starts with `-` (the whole path, not each segment), and length over 1024; reserved prefixes return `hidden`. Any caller that places a project path into a process argv must pass it after `--` or prefix it with `./`, because `parseRelPath` does not reject a `-` that starts a later segment. The adapter requires the real path of the deepest existing ancestor inside the real root, refuses escaping symlinks and non-regular files, and writes atomically. The editor opens UTF-8 text up to 2 MB; other files appear in the tree as binary.

### D11. Chat UI

`ChatPanel` → `ProviderHeader` (`ProviderLogo`, name, status, `ProviderSelect`, `ModelSelect`, New chat) · `MessageList` (`UserMessage`, `AssistantMessage` with a minimal safe renderer and no raw HTML, `ToolActivityCard` with tool name, target path chip and status running/done/failed, `TurnSummary` with the changed files or "No files changed" and `UndoTurnButton` only for the undoable turn, `UndoConflictDialog`, `NoticeBanner`, `ErrorCard` with a plain title, a suggested action and collapsed raw detail) · `Composer` (Send becomes Stop; disabled while a turn runs) · `ProviderUnavailable` ("not installed", install hint, re-check). State is a pure `chatReducer(state, TurnEvent)` in core that accepts deltas and whole parts without loss, duplication or reordering. Not terminal-styled: proportional font, bubbles and cards from the shared tokens, monospace only for code and path chips, no prompt glyph, cursor or escape output.

Logos (confirmed): the MVP ships the official logos of Claude, opencode and Codex as unmodified assets in `apps/web/src/assets/providers/{claude,opencode,codex}.svg`. `ProviderLogo` shows the provider name as text only when the asset is missing or fails to load. `apps/web/src/assets/providers/NOTICE.md` records, per asset, the owner, source URL and retrieval date, and states that Caztor is not affiliated with the vendors. Each vendor's brand guidelines should be reviewed before Caztor is published. Assets must be taken from official vendor sources, never redrawn.

## Data Flow

Compile, with a queued request and a cancel:

```
Web          API            CompileCoordinator      TectonicCompiler      tectonic
 |--POST /compile-->|--request()-->|                      |                   |
 |<--202 {compileId}|              |--compile(req,signal)->|--spawn(argv)---->|
 |<==SSE compile.started===========|                       |<--stderr note:---|
 |<==SSE compile.phase downloading=|<--phase---------------|                  |
 |--POST /compile-->|--request()-->| running: store as queued follow-up       |
 |<--202 {queued}---|              |                       |<--exit code------|
 |                  |              |                       |--parse stderr + out/<job>.log
 |                  |              |                       |--promote preview.pdf, bump rev
 |<==SSE compile.finished{status,diagnostics,rev}==========|
 |--GET /compile/pdf?rev-->|--readArtifact('pdf')--------->|
 |                  |              |--start queued run ---->|--spawn---------->|
 |--POST /compile/cancel-->|--cancel()-->| abort signal --->|--kill group----->|
 |<==SSE compile.finished{status: cancelled}===============|
```

Chat turn that edits a file, then undo:

```
Web          API           TurnService      Provisioner   Snapshot    AgentRunner   CLI
 |--POST /chat/turns-->|--start()-->|--ensure(provider)->|           |             |
 |                     |            |--capture(turnId)-------------->|             |
 |                     |            |   capture fails: error snapshot_failed, done failed, no spawn
 |<==turn_started======|            |--runTurn(req,signal)------------------------>|--spawn-->|
 |<==session / text_delta / tool_start / tool_update / tool_end====================|<-JSONL---|
 |   (user autosaves another file: file API records a user write)                  |
 |<==done==============|            |<---------------------------------------------|<-exit----|
 |                     |            |--diff(turnId, userOnly)------->|
 |<==files_changed=====|            |--append transcript; rescan -> file_changed on /api/events
 |--POST /turns/:id/undo {strict}-->|--restore(turnId, strict)------>| preflight hashes
 |<--409 conflicts (user edited a.tex): warning, nothing written     |
 |--POST undo {skip_conflicts}----->|--restore---------------------->| pre-undo snapshot, write blobs
 |<--200 restored; file_changed events; previous turn becomes undoable; next prompt notes the revert
```

## Interfaces / Contracts

```ts
// packages/core/src/ports.ts — no Node imports
export type RelPath = string & { readonly __brand: "RelPath" };
export type ContentHash = `sha256:${string}`;
export type Result<T, E> = { ok: true; value: T } | { ok: false; error: E };
export type ProviderId = "claude" | "opencode" | "codex";

export interface FileEntry { path: RelPath; kind: "file" | "dir"; size: number }
export type StoreError =
  | { code: "not_found" | "invalid_path" | "outside_root" | "hidden" | "exists" | "too_large" | "not_text" | "io"; path: string }
  | { code: "conflict"; path: RelPath; currentHash: ContentHash | null };
export interface FileChange { path: RelPath; hash: ContentHash | null }

export interface ProjectStorePort {
  list(): Promise<FileEntry[]>;
  read(path: RelPath): Promise<Result<{ bytes: Uint8Array; hash: ContentHash }, StoreError>>;
  /** expect: a hash = must match; null = must not exist (create, upload); "any" = unconditional (undo only). */
  write(path: RelPath, bytes: Uint8Array, expect: ContentHash | null | "any"): Promise<Result<{ hash: ContentHash }, StoreError>>;
  mkdir(path: RelPath): Promise<Result<void, StoreError>>;
  rename(from: RelPath, to: RelPath): Promise<Result<void, StoreError>>;          // files and folders
  remove(path: RelPath, opts?: { recursive: boolean }): Promise<Result<void, StoreError>>;
  watch(onChange: (change: FileChange) => void): () => void;
}

export interface Diagnostic {
  severity: "error" | "warning"; file: RelPath | null; line: number | null;
  message: string; detail?: string; source: "stderr" | "log" | "caztor";
}
export interface CompileRequest { main: RelPath; stopOnFirstError: boolean }
export interface CompileResult {
  status: "success" | "failed-with-errors" | "failed" | "timed-out" | "cancelled" | "engine-missing";
  pdfRev: string | null; diagnostics: Diagnostic[]; durationMs: number; logAvailable: boolean;
}
export type CompileEvent =
  | { type: "started"; compileId: string }
  | { type: "phase"; phase: "downloading" | "typesetting" | "bibliography" | "finalizing" }
  | { type: "finished"; compileId: string; result: CompileResult };
export interface CompilerPort {
  available(): Promise<{ ok: boolean; version?: string }>;
  compile(req: CompileRequest, signal: AbortSignal): AsyncIterable<CompileEvent>; // abort = cancel
  readArtifact(kind: "pdf" | "log"): Promise<Uint8Array | null>;
}

export type TurnErrorCode =
  | "not_installed" | "auth" | "model_unavailable" | "model_required" | "rate_limited" | "permission_denied"
  | "isolation_failed" | "snapshot_failed" | "malformed_output" | "timeout" | "provider_error";
export type ToolKind = "read" | "edit" | "write" | "search" | "command" | "other";
export type AgentEvent =
  | { type: "session"; sessionId: string }
  | { type: "text_delta"; messageId: string; text: string }
  | { type: "text"; messageId: string; text: string }            // authoritative; replaces deltas
  | { type: "tool_start"; toolId: string; name: string; kind: ToolKind; path?: string }
  | { type: "tool_update"; toolId: string; path?: string; title?: string }
  | { type: "tool_end"; toolId: string; status: "done" | "failed"; summary?: string }
  | { type: "notice"; level: "info" | "warning"; message: string }
  | { type: "error"; code: TurnErrorCode; message: string; detail?: string }
  | { type: "done"; reason: "completed" | "cancelled" | "failed";
      usage?: { inputTokens?: number; outputTokens?: number; costUsd?: number } };

export interface ProviderStatus {
  provider: ProviderId; installed: boolean; unavailableReason?: string; version?: string;
  versionWarning?: string; models?: string[]; requiresModel: boolean;
}
export interface TurnRequest { prompt: string; sessionId: string | null; model: string | null; agent: AgentDefinition }
export interface AgentRunnerPort {
  readonly provider: ProviderId;
  readonly isolation: string;                                    // tier id, part of the session record
  detect(): Promise<ProviderStatus>;
  runTurn(req: TurnRequest, signal: AbortSignal): AsyncIterable<AgentEvent>; // exactly one "done", last
}

export interface AgentDefinition { hash: ContentHash; name: string; description: string; prompt: string; tools: string[] }
export interface ProvisionOutcome { target: string; status: "created" | "updated" | "unchanged" | "skipped_user_modified" }
export interface ProvisionerPort {
  /** Idempotent. Returns the definition actually present in the project. */
  ensure(provider: ProviderId, opts?: { replace: boolean }): Promise<Result<{ outcomes: ProvisionOutcome[]; agent: AgentDefinition }, { message: string }>>;
}

export interface ChangedFile {
  path: RelPath; change: "created" | "modified" | "deleted";
  beforeHash: ContentHash | null; afterHash: ContentHash | null; undoable: boolean; mixed: boolean;
}
export type RestoreResult =
  | { status: "restored"; files: RelPath[]; skipped: RelPath[] }
  | { status: "conflict"; conflicts: { path: RelPath; expected: ContentHash | null; actual: ContentHash | null }[] }
  | { status: "unavailable"; reason: "not_latest" | "discarded" | "already_undone" };
export interface SnapshotPort {
  capture(turnId: string): Promise<Result<{ partial: boolean; unprotected: RelPath[] }, { message: string }>>;
  diff(turnId: string, userOnly: ReadonlySet<RelPath>): Promise<ChangedFile[]>;
  undoable(): Promise<string | null>;                            // top of the LIFO stack
  restore(turnId: string, mode: "strict" | "skip_conflicts" | "force"): Promise<RestoreResult>;
  prune(keepTurns: number): Promise<string[]>;                   // discarded turn ids
}

export interface SessionRecord { sessionId: string; agentHash: ContentHash; isolation: string }
export interface ProjectState {
  selectedProvider: ProviderId | null;
  models: Partial<Record<ProviderId, string>>;
  sessions: Partial<Record<ProviderId, SessionRecord>>;
  mainFile: RelPath | null;
  stopOnFirstError: boolean; autoCompile: boolean; sandboxedCompile: boolean;
  disclosureAcknowledged: boolean; projectClaudeConfigConfirmed: boolean;
  provisioned: Record<string, { hash: ContentHash; createdByCaztor: boolean }>;
}
export interface StatePort {
  load(): Promise<ProjectState>;                                 // defaults when missing or corrupt
  update(patch: Partial<ProjectState>): Promise<ProjectState>;   // atomic write of .caztor/state.json
}

export type TurnEvent = AgentEvent
  | { type: "turn_started"; turnId: string; provider: ProviderId; snapshotPartial: boolean; unprotected: RelPath[] }
  | { type: "files_changed"; turnId: string; files: ChangedFile[] };   // empty list = "No files changed"
```

```ts
// packages/adapters-local/src/infra.ts — injected into every adapter
export interface SpawnSpec { file: string; args: readonly string[]; cwd: string; env: Readonly<Record<string, string>>; stdin?: string }
export interface ChildHandle {
  stdout: AsyncIterable<Uint8Array>; stderr: AsyncIterable<Uint8Array>;
  exit: Promise<{ code: number | null; signal: string | null }>;
  killGroup(signal: "SIGINT" | "SIGTERM" | "SIGKILL"): void;
}
export interface ProcessSpawner { spawn(spec: SpawnSpec): ChildHandle }
export interface Clock { now(): number; setTimeout(fn: () => void, ms: number): () => void }
export type CommandWrapper = (spec: SpawnSpec) => SpawnSpec; // identity, or the bubblewrap wrapper
```

`FileSystem` is the narrow subset of `node:fs/promises` used by the store, state, snapshot and provisioner adapters.

## File Changes

| File | Action | Description |
|---|---|---|
| `package.json`, `tsconfig.base.json`, `vitest.config.ts` | Create | Workspaces, strict TS, Vitest projects |
| `packages/core/src/{ports,paths,hash,compile-coordinator,turn-service,prompt,chat-reducer,biblatex-scan}.ts` | Create | Pure domain |
| `packages/api/src/{app,security,sse}.ts`, `routes/{session,files,compile,providers,chat}.ts` | Create | Hono factory |
| `packages/adapters-local/src/{infra,node-infra,project-store,state-store,snapshot-store,provisioner,sandbox}.ts` | Create | Disk and process adapters |
| `packages/adapters-local/src/tectonic/{compiler,diagnostics,log-parser}.ts` | Create | Compile adapter |
| `packages/adapters-local/src/providers/{claude,opencode,codex}/{mapper,runner}.ts` | Create | Provider adapters |
| `packages/adapters-local/test/fixtures/**` | Create | Sanitized fixtures |
| `apps/server-local/src/main.ts` | Create | Wiring, loopback bind, token, static |
| `apps/web/src/{api,layout,files,editor,compile,preview,chat}/**` | Create | UI |
| `apps/web/src/assets/providers/{claude,opencode,codex}.svg`, `NOTICE.md` | Create | Official logos and their origin |
| `agents/{claude,opencode,codex}.md` | Create | Canonical agent files |
| `README.md` | Create | Usage, security disclosures |
| `openspec/config.yaml` | Modify | `strict_tdd: true` after slice 1 |

## Testing Strategy

Strict TDD: every unit gets its failing test first. The default `npx vitest run` spawns no real binary.

| Layer | What to Test | Approach |
|---|---|---|
| Core unit | Path parsing, hashing, coordinator queue and cancel, turn service (provision order, snapshot failure, attribution, session invalidation, empty change list), prompt building, chat reducer, biblatex scan | Pure tests with fake ports and a fake clock |
| Core architecture | No Node imports in `core` and `api` | Import-scan test plus `types: []` typecheck |
| Adapter unit | Diagnostics and log parsers, status derivation, offline mapping; provider mappers | Fixtures; table tests per native event; unknown and truncated lines |
| Adapter process | argv, environment allowlist, stdin prompt, time limit, group kill, cancel and Stop escalation, exit without a terminal event | Fake `ProcessSpawner` replaying fixtures with scripted chunk boundaries (split lines, split UTF-8) and fake `Clock` |
| Adapter disk | Store (files, folders, upload, collisions), state store (corrupt file), snapshots (LIFO, retention, limits), provisioning rules | In-memory `FileSystem` fake; a small temp-directory contract suite for symlink and real-path behavior |
| API integration | Security middleware matrix, token on reads, upload content type, file routes, 409 flows, SSE framing, cancel, undo conflicts | `app.request()` with fake ports; token injection tested against a fixture HTML |
| Web component | Pane order, minimum widths, corrupt layout, disclosure notice, tree operations, editor states and conflict banner, preview scroll, zoom, empty and out-of-date states, log panel, every chat component and state, logo fallback on load error | jsdom and Testing Library; CodeMirror and pdf.js behind thin mocked wrappers; injected fake API client |
| Opt-in | Real tectonic end to end | `CAZTOR_REAL_BIN=1`, excluded by default |
| E2E | Not planned | Manual smoke checklist per slice |

Fixtures: raw spike captures are preserved, git-ignored, in `openspec/changes/caztor-mvp/spike-raw/` (`claude-turn-edit.jsonl`, `opencode-turn-edit.jsonl`, `opencode-error-free-tier.jsonl`, `opencode-error-model-rejected.jsonl`, `tectonic-err.log`, `tectonic-bib.log`). Adapter slices derive **sanitized, trimmed** fixtures from them: paths, session ids, MCP server names, signatures and account data are replaced with placeholders, and a test fails if a fixture contains the user's home path. No token spend is needed for the first Claude and opencode fixtures. Cases with no capture (Claude error, cancel and resume; isolation violation) are hand-edited variants of the captures, labelled synthetic. Missing tectonic cases (continue-on-errors, log warnings, offline) are recorded locally at no token cost. Codex fixtures are written from documented shapes and labelled as such. Fixtures do not count toward the 400-line budget.

## Threat Matrix

| Boundary | Minimum adversarial cases | Applicability | Design response | Planned RED tests |
|---|---|---|---|---|
| Documentation-like paths | `requirements.txt`, `CMakeLists.txt`, executable Markdown/MDX, `README.sh` | Applicable: provisioned agent Markdown is active instruction content, and project `.claude/settings*.json` / `.mcp.json` are executed by the CLI | Caztor never executes a project file. Agent files are written only by the provisioner under the ownership rules. Claude tier I1 loads no project settings; tier I2 requires confirmation when such files exist. Reserved paths are unreachable through the file API | Provisioner does not overwrite an unrecorded or modified native file; file API returns `hidden` for `.claude/agents/caztor.md` and `.caztor/**`; tier I2 blocks the turn until confirmation when `.mcp.json` exists |
| Git repository selection | `git -C`, relative paths, absolute paths | N/A: no git command is run; snapshots are file copies; codex receives `--skip-git-repo-check` | n/a | n/a |
| Commit state | staged, `commit -a`, empty index | N/A: no commits are created | n/a | n/a |
| Push state | tracking branch, first push, explicit refspec | N/A: no push | n/a | n/a |
| PR commands | explicit `--head`, environment prefix, composed commands | N/A: no PR automation | n/a | n/a |

Additional process boundaries introduced by this design (same propagation rule):

| Boundary | Adversarial cases | Safe behavior | Planned RED tests |
|---|---|---|---|
| Subprocess argv | Main file named `-Z shell-escape.tex`; model value `--dangerous`; prompt `; rm -rf ~` or starting with `--` | `parseRelPath` rejects a path that starts with `-`, and callers pass paths after `--` or as `./path`; model must match `^[A-Za-z0-9._:/-]+$` and not start with `-`; prompt only on stdin; no shell | One test per case asserting rejection or an unchanged argv |
| Subprocess environment | Secrets in the server environment | Only allowlisted names and provider prefixes are passed | Spawn spec contains no other variable |
| Path containment | `../x`, `/etc/passwd`, NUL, symlink to outside, symlinked parent, upload to a reserved path | Rejected before disk access or at the real-path check | One test per case, core and temp-directory suite |
| Path containment, concurrent swap (residual risk) | A parent folder replaced by a link leading out of the project between the containment check and the atomic rename | Node has no `openat`, so the race cannot be closed completely. The store re-resolves the parent with `realpath` after the temporary file is written and immediately before the rename, and aborts (removing the temporary file) when it no longer resolves to the checked location. A swap landing between that last `realpath` and the `rename` call remains possible for a local attacker with write access to the project folder; the sandbox (slice 31) is the defence in depth. Writes and renames of the same path are serialized inside the process | Injected file system wrapper that swaps the parent before the temporary write and after it; two concurrent saves on one hash |
| Local HTTP | Wrong `Host`, foreign `Origin`, missing token on a read and on a write, stale token, `text/plain` POST, preflight | 403/401/415; no CORS headers | Middleware matrix |
| Agent stream | Unknown event types, malformed JSON, oversized line, ANSI, no terminal event | Ignored or capped; `malformed_output` or `provider_error`, then `done` | Mapper and runner tests |
| Process lifetime | Hung compile or agent; Stop or cancel ignored | Group kill escalation with fake clock | Time-limit, cancel and Stop tests |
| Agent isolation | `system/init` lists `Bash` or an MCP tool | Turn aborted with `isolation_failed` | Fixture variant test |

## Migration / Rollout

No migration required. One PR per slice, chained. The proposal's 13 slices become 31 so that each stays within 400 changed lines; the previously high-risk slices (store, editor, compile, turn service, Claude adapter, chat UI) are split.

| # | Slice | Verified by | Budget risk |
|---|---|---|---|
| 1 | Workspace scaffold, Vitest projects, import guard, enable strict TDD | `npx vitest run` | Low |
| 2 | Core: paths, hash, all six ports, state and event types | Path and hash tests | Medium |
| 3 | Infra interfaces, Node implementations, fakes | Fake self-tests | Low |
| 4 | Local project store: containment, files, folders, binary writes, reserved paths | Containment tests | Medium |
| 5 | State store (`state.json`, corrupt fallback) | State tests | Low |
| 6 | `packages/api` factory, security middleware, CSP | Middleware matrix | Medium |
| 7 | Server main: loopback bind, token, static serving, `<meta>` injection | Fixture-HTML test | Low |
| 8 | Session, settings and file routes (create, folders, rename, delete, upload), `/api/events` | Request tests | Medium |
| 9 | Web shell: API client, four-pane layout (order, minimums, persistence, corrupt fallback), first-use disclosure notice | Component tests | Medium |
| 10 | File tree: open, create, rename, delete, folders, upload, collision messages | Component tests | Medium |
| 11 | Editor: CodeMirror host, LaTeX and BibTeX highlighting, autosave states | Component tests | Medium |
| 12 | Editor: external changes, conflict banner, compare view | Conflict tests | Medium |
| 13 | Compile parsing: stderr errors, wrappers, status derivation, offline mapping, biblatex scan | Fixtures | Medium |
| 14 | Compile parsing: log warnings, file stack, outside-project read diagnostic | Fixtures | Medium |
| 15 | Tectonic adapter: argv, environment, phases, time limit, group kill, artifact promotion | Fake spawner tests | Medium |
| 16 | Compile coordinator (queue, cancel), compile routes, compile SSE | Core and request tests | Medium |
| 17 | Compile toolbar (compile, cancel, queued, toggle, auto-compile, first-run state) and PDF preview (scroll, zoom, empty, out of date) | Component tests | Medium |
| 18 | Log panel with click-to-line | Component tests | Low |
| 19 | Snapshot store: capture, failure, diff, limits, retention | Snapshot tests | Medium |
| 20 | Snapshot restore: LIFO stack, conflicts, pre-undo snapshot | Restore tests | Medium |
| 21 | Agent files and shared-section test | Content tests | Medium (prose) |
| 22 | Provisioner adapter | Ownership and block tests | Medium |
| 23 | Turn service and prompt builder | Fake runner tests | Medium |
| 24 | Providers routes (list, re-check, selected, model) and chat routes (turns, stop, undo, history, reset), transcript | Request tests | Medium |
| 25 | Claude mapper and sanitized fixtures | Fixtures | Medium |
| 26 | Claude runner: argv, isolation tier, init assertion, Stop, detection | Fake spawner tests | Medium |
| 27 | Chat UI: reducer, message list, tool cards, composer and Stop | Component tests | Medium |
| 28 | Chat UI: header with logos and `NOTICE.md`, provider and model selectors, turn summary, undo and conflict dialog, unavailable and error states, notices | Component tests | Medium to high: split header from summary if needed |
| 29 | opencode adapter, model-required gate, isolation | Fixtures | Medium |
| 30 | codex adapter and "not installed" state | Documented-shape fixtures | Medium |
| 31 | Opt-in bubblewrap sandbox, README disclosures | Fake spawner tests | Low |

## Open Questions

None block the design, and no user decision is pending. To verify during implementation, each with the fallback stated above: Node type stripping across workspace packages; every **[V]** flag in D5 and D6; Claude `--resume` and Stop by SIGINT; `opencode models`; tectonic download-failure text; pixel minimums in the pane library; recursive watching on the user's filesystem; the bubblewrap profile.
