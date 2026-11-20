# Tasks: Caztor MVP

Source: design revision 2 (31 slices, order kept). Slices 17, 24 and 28 are split (a/b), giving 34 branches. Estimates are additions + deletions, fixtures excluded.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | about 11,000 total (range 10,000-13,000); per slice 150-540 |
| 400-line budget risk | High (31 slices at or near the budget; 3 estimated above it) |
| Chained PRs recommended | Yes |
| Suggested split | One local branch per slice (changed 2026-10-12: no further a/b/c splitting) |
| Delivery strategy | exception-ok (changed 2026-10-12: one branch per slice, `size:exception` accepted, the 400-line cap no longer applies) |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

Delivery decision of 2026-10-12: from batch E on, every slice is ONE branch created from the previous slice's branch, with small conventional commits inside it (one work unit with its tests per commit) and `size:exception` accepted. The slice splits below were proposed under the earlier 400-line cap and are superseded: slices 17, 24 and 28 stay single branches (`caztor/s17-compile-ui`, `caztor/s24-provider-chat-routes`, `caztor/s28-chat-header-results`) unless the user says otherwise.

Above 400 (earlier split proposal, superseded): slice 17 (440) into 17a toolbar and 17b preview; slice 24 (450) into 24a providers routes and 24b chat routes plus transcript; slice 28 (540) into 28a header/logos/selectors and 28b summary/undo/errors/notices.
Near the limit (about 390-400), with a pre-agreed split point if the real count exceeds 400: 4, 8, 10, 15, 16, 19, 23, 26, 27, 29.

### Branching and delivery (local only, no remote, no push, no gh)

- Branch names `caztor/sNN-<name>` (split: `sNNa`, `sNNb`). Tracker: `feature/caztor-mvp`, created from `main` after the baseline commit.
- Intended PR base: slice 1 targets `feature/caztor-mvp`; each later slice targets the previous slice branch. Only the tracker merges to `main`.
- Commit by work unit, tests with code, conventional commits, no AI attribution. A slice branch is created from the previous slice branch.
- Per-slice rollback boundary: revert the slice branch (its files only). Every slice leaves `npx vitest run` and `npx tsc -b` green.
- Tasks marked TOKEN SPEND call a real CLI and cost tokens; keep to one minimal call. Default `npx vitest run` spawns no real binary.

## Phase 0: Baseline (before slice 1)

- [x] 0.1 On `main` create `.gitignore` (`node_modules`, `dist`, `.caztor`, `openspec/changes/caztor-mvp/spike-raw/`) and make the initial commit with `.gitignore`, `openspec/` and `.atl/` (`chore: add repository baseline`).
- [x] 0.2 Create tracker `feature/caztor-mvp` from `main`, then branch `caztor/s01-scaffold` from it.

## Phase 1: Foundation (slices 1-8)

### Slice 1 - Scaffold (`caztor/s01-scaffold`, base `feature/caztor-mvp`, ~150) covers: testing enablement
- [x] 1.1 Create root `package.json` (npm workspaces, `test` script), `tsconfig.base.json` (strict, ESM, `erasableSyntaxOnly`) and `vitest.config.ts` (node and jsdom projects).
- [x] 1.2 Add empty workspaces `packages/{core,api,adapters-local}`, `apps/{server-local,web}` with `package.json` and `tsconfig.json` (core: `lib ES2023,WebWorker`, `types: []`).
- [x] 1.3 RED: `packages/core/test/import-guard.test.ts` fails on a `node:` import planted in a temp fixture; GREEN: scan `packages/core/src` and `packages/api/src` for `node:` and builtin imports.
- [x] 1.4 Flip `strict_tdd` and `rules.apply.tdd` to `true` in `openspec/config.yaml`; set `testing.status` to installed.
- Verify: `npx vitest run`; `npx tsc -b`.

### Slice 2 - Core types (split: `caztor/s02a-core-ports` base s01, `caztor/s02b-core-paths-hash` base s02a; real counts 329 and 151) covers: project-files Path containment, Reserved paths; agent-providers Normalized events
- [x] 2.1 RED `paths.test.ts` (empty, absolute, backslash, NUL, control, `..` (read-only), leading `-` such as `-Z shell-escape.tex`, over 1024, reserved prefixes return `hidden`); GREEN `packages/core/src/paths.ts` `parseRelPath`.
- [x] 2.2 RED `hash.test.ts` (known vector, `sha256:<hex>`); GREEN `hash.ts` over `crypto.subtle`.
- [x] 2.3 Add `ports.ts` with all six ports, `Result`, event unions, `ProjectState`; type-level test file proves the shapes compile.
- Verify: `npx vitest run packages/core`.

### Slice 3 - Infra (split: `caztor/s03a-infra-clock-spawner` base s02b, `caztor/s03b-memory-fs`, `caztor/s03c-node-infra`; real counts 394, 273, 341; then `caztor/s03d-fake-parity`, 294, aligns the fakes with Node) covers: local-server-security No shell spawning
- [x] 3.1 Add `infra.ts` interfaces (`ProcessSpawner`, `Clock`, `FileSystem`, `CommandWrapper`).
- [x] 3.2 RED fake self-tests (scripted chunks incl. split UTF-8, fake clock timers, in-memory FileSystem); GREEN `test/fakes/*.ts`.
- [x] 3.3 RED: `node-infra` spawn test asserts `shell:false`, `detached`, env allowlist only; GREEN `node-infra.ts`.
- Verify: `npx vitest run packages/adapters-local`; harness: spawn `node -e ""` through `node-infra`.

### Slice 4 - Project store (split: `caztor/s04a-fs-sandbox` base s03d, `caztor/s04b-store-containment`, `caztor/s04c-store-writes`, `caztor/s04d-store-structure`; real counts 127, 357, 236, 166) covers: project-files File tree, File operations, Path containment, Hash-checked saves, Reserved paths; security Path containment
- [x] 4.1 RED temp-dir contract suite: `../x` (read-only), `/etc/passwd` (read-only), NUL, symlink to outside, symlinked parent, upload into reserved path, non-regular file; GREEN `project-store.ts` real-path check.
- [x] 4.2 RED list, read (hash), write with `expect` hash/null/`any` (409 `conflict`), atomic write, mkdir, rename, recursive remove; GREEN same file.
- [x] 4.3 RED: reserved paths (`.caztor/`, `.claude/`, `.opencode/`, `.git/`, `node_modules/`) return `hidden`; `AGENTS.md` hidden only when createdByCaztor; GREEN.
- Verify: `npx vitest run packages/adapters-local/test/project-store`.

### Slice 5 - State store (`caztor/s05-state-store`, base s04d, real 292) covers: supports persistence in agent-providers, latex-compile, security
- [x] 5.1 RED: missing and corrupt `state.json` yield defaults; update is atomic; GREEN `state-store.ts`.
- Verify: `npx vitest run packages/adapters-local/test/state`.

### Slice 6 - API factory and security (split: `caztor/s06a-api-security` base s05, `caztor/s06b-token-headers`; real counts 381 and 140) covers: security Host and Origin allowlists, Launch token
- [x] 6.1 RED middleware matrix via `app.request()`: wrong Host, foreign Origin, missing/stale token on GET and write, `text/plain` POST, preflight, body limits (2 MB, 20 MB upload), no CORS headers; GREEN `packages/api/src/{app,security}.ts`.
- [x] 6.2 RED: constant-time token compare, token ignored from env without `CAZTOR_DEV=1`; GREEN.
- [x] 6.3 RED: CSP and `nosniff` headers on static responses; GREEN.
- Verify: `npx vitest run packages/api`.

### Slice 7 - Server main (split: `caztor/s07a-static-token` base s06b, `caztor/s07b-server-main` base s07a; real counts 243 and 312; the [V] check passed, no `tsx` needed) covers: security Loopback bind, Launch token
- [x] 7.1 [V] Verify Node 26 type stripping across workspaces by running `node apps/server-local/src/main.ts`; fallback add `tsx`.
- [x] 7.2 RED: bind address is `127.0.0.1` and port fallback; `<meta name="caztor-token">` placeholder replaced in fixture HTML; GREEN `main.ts`.
- Verify: `npx vitest run apps/server-local`; harness: `npm start -- <tmpdir>` then `curl` without token returns 401.

### Slice 8 - Session and file routes (split: `caztor/s08a-session-routes` base s07b, `caztor/s08b-files-read`, `caztor/s08c-files-write`, `caztor/s08d-files-structure`, `caztor/s08e-events-sse`; real counts 322, 262, 185, 268, 229) covers: project-files File tree, File operations, Hash-checked saves, Reserved paths
- [x] 8.1 RED request tests: `GET /api/session`, `PATCH /api/settings`; GREEN `routes/session.ts`.
- [x] 8.2 RED: files list/read/PUT 409, create collision 409, rename, recursive delete, upload (octet-stream, 20 MB, 409 on existing, reserved path rejected); GREEN `routes/files.ts`.
- [x] 8.3 RED: `/api/events` (read-only) SSE framing, `id`, heartbeat with fake clock; GREEN `sse.ts`.
- Verify: `npx vitest run packages/api`.

## Phase 2: Web shell and editing (slices 9-12)

### Slice 9 - Web shell (`caztor/s09-web-shell`, base s08, ~380) covers: workspace-layout all four; security Disclosed limits (notice)
- [x] 9.1 Add Vite/React config, API client reading the token `<meta>`, token CSS tokens file.
- [x] 9.2 [V] Check `react-resizable-panels` pixel minimums; apply percentage conversion if needed. Result: v4.14.4 takes numeric `minSize` as pixels, so no conversion is needed; saved layouts are validated in percent against the pixel minimums for the measured width.
- [x] 9.3 RED: pane order, defaults 15/35/30/20, minimums, persisted sizes, corrupt layout discarded, panes independent; GREEN `layout/`.
- [x] 9.4 RED: first-use disclosure shown once per project and acknowledged via settings; GREEN.
- Verify: `npx vitest run apps/web`; harness: `npm run build -w apps/web`.

### Slice 10 - File tree (`caztor/s10-file-tree`, base s09, ~390) covers: project-files File tree, File operations
- [x] 10.1 RED: tree render, open file, hidden entries absent, binary shown as binary; GREEN `files/`.
- [x] 10.2 RED: create, rename, delete with confirmation, folders, upload, collision message; GREEN.
- Verify: `npx vitest run apps/web/src/files`.

### Fix slice 10h (`caztor/s10h-ui-store-fixes`, base `caztor/s10g-events-refresh`, real 410): verifier findings on batch D
- [x] 10h.1 Temp file created owner-only (`writeFile` `mode` option on the fake and Node file systems, contract test); dialog focus and inert background; saved layout validated by shape only; HTML-looking file name test; vacuous Workspace test removed.

### Slice 11 - Editor (`caztor/s11-editor`, base `caztor/s10h-ui-store-fixes`, real about 1,700) covers: latex-editor Syntax highlighting, Autosave
- [x] 11.1 RED: BibTeX tokenizer (entry types, keys, fields, strings, comments); GREEN in-repo `StreamLanguage`.
- [x] 11.2 RED: buffer states saved/saving/dirty/conflict/error, 800 ms autosave with `baseHash`, 409 and failure keep dirty; GREEN `editor/` behind a thin CodeMirror wrapper.
- Verify: `npx vitest run apps/web/src/editor`.

### Slice 12 - External changes (`caztor/s12-editor-conflicts`, base `caztor/s11-editor`, ~360) covers: latex-editor clean/dirty external change, Undo restores open buffers
- [x] 12.1 RED: event hash equal to base ignored; clean buffer reloads keeping cursor and scroll; GREEN.
- [x] 12.2 RED: dirty buffer banner (Keep mine, Load disk, Copy, Compare), autosave paused until resolved; GREEN with `@codemirror/merge`.
- [x] 12.3 [V] Check recursive watcher behavior on this filesystem; add forced rescan fallback test. Result: recursive `fs.watch` reports nested files and new folders on ext4 and tmpfs here; the 9p `/mnt/c` (read-only) mount was not tested; the 5 s periodic rescan and `store.rescan()` cover a silent watcher.
- Verify: `npx vitest run apps/web/src/editor`.

## Phase 3: Compile (slices 13-18)

### Slice 13 - Compile parsing I (`caztor/s13-compile-parse`, base s12, ~380) covers: latex-compile Status from diagnostics, Diagnostics, First-run state, BibTeX and biblatex
- [x] 13.1 Derive sanitized fixtures from `spike-raw/tectonic-err.log` and `tectonic-bib.log`; test fails if a fixture holds the home path.
- [x] 13.2 RED: stderr `error: file:line:` extraction, wrapper lines dropped, transcript skipped, `caused by:`, file-less error; GREEN `tectonic/diagnostics.ts`.
- [x] 13.3 RED: status derivation (cancelled, timed-out, failed, failed-with-errors, success), synthetic error with stderr tail; GREEN.
- [x] 13.4 Record offline-first-run fixture locally (no tokens) [V]; RED/GREEN mapping and `downloading`-phase fallback.
- [x] 13.5 RED/GREEN `biblatex-scan.ts` notice.
- Verify: `npx vitest run packages/adapters-local/test/tectonic packages/core`.

### Slice 14 - Compile parsing II (`caztor/s14-log-parser`, base s13, ~340) covers: latex-compile Diagnostics, Outside-project read diagnostic
- [x] 14.1 RED: `.log` `LaTeX Warning` or `Package X Warning` with `on input line N`, wrapped lines rejoined, stderr marker consumed; GREEN `log-parser.ts`.
- [x] 14.2 RED: open-file stack resolves file, else no jump; `accessing absolute path` warning becomes the outside-project diagnostic; GREEN.
- Verify: `npx vitest run packages/adapters-local/test/tectonic`.

### Slice 15 - Tectonic adapter (`caztor/s15-tectonic-adapter`, base s14, ~390) covers: latex-compile Local compile, Stop-on-error, Shell escape disabled, Time limit; security No shell spawning
- [x] 15.1 RED: argv equals `tectonic -X compile <main> --outdir .caztor/build/out --keep-logs --untrusted` (+`-Z continue-on-errors` when stop-on-error is off); never `--synctex`, never shell-escape; main named `-Z shell-escape.tex` rejected.
- [x] 15.2 RED: env allowlist plus `TECTONIC_UNTRUSTED_MODE=1`; GREEN `compiler.ts`.
- [x] 15.3 RED: phase mapping from notes, atomic PDF promotion and `rev` bump, previous preview kept when no PDF; GREEN.
- [x] 15.4 RED (fake clock): 180 s limit extended to 600 s on `downloading`, SIGTERM then SIGKILL after 2 s, stderr 2 MB / line 4 KB caps; GREEN.
- Verify: `npx vitest run packages/adapters-local/test/tectonic`; harness (opt-in, no tokens): `CAZTOR_REAL_BIN=1 npx vitest run` real tectonic compile.

### Slice 16 - Coordinator and compile routes (`caztor/s16-compile-routes`, base s15, ~390) covers: latex-compile Local compile, Single run and cancel
- [x] 16.1 RED (fake ports/clock): one run per project, newer request replaces queued follow-up, cancel aborts and clears queue; GREEN `compile-coordinator.ts`.
- [x] 16.2 RED: `POST /api/compile` 202 `{compileId, queued}`, cancel, status, `/pdf?rev=` (read-only) (`no-store`, token), `/log` (read-only), SSE `compile.*`; GREEN `routes/compile.ts`.
- Verify: `npx vitest run packages/core packages/api`.

### Slice 17a - Compile toolbar (merged into one branch `caztor/s17-compile-ui` with 17b, user decision; `caztor/s17a-compile-toolbar`, base s16, ~230) covers: latex-compile Stop-on-error, Single run and cancel, Auto-compile, First-run state
- [x] 17a.1 RED: Compile becomes Cancel while running, "queued" label, stop-on-error toggle persists, auto-compile 1.5 s after successful save, "Preparing: downloading support files"; GREEN `compile/`.
- Verify: `npx vitest run apps/web/src/compile`.

### Slice 17b - PDF preview (merged into `caztor/s17-compile-ui`; `caztor/s17b-pdf-preview`, base s17a, ~210) covers: pdf-preview PDF display, Reload keeps position, Empty and failed states
- [x] 17b.1 RED: renders pdf.js via mocked wrapper using fetched bytes, zoom, scroll page+offset kept across reload and in `localStorage` per project, empty state, out-of-date mark; GREEN `preview/` (`pdfjs-dist` pinned).
- Verify: `npx vitest run apps/web/src/preview`.

### Slice 18 - Log panel (`caztor/s18-log-panel`, base `caztor/s17-compile-ui` (17a and 17b merged), ~200) covers: pdf-preview Log panel with click-to-line
- [x] 18.1 RED: diagnostics list, click opens file at line, no-jump entries inert, raw log view; GREEN.
- Verify: `npx vitest run apps/web/src/compile`.

## Phase 4: Snapshots, agents, turns (slices 19-24)

### Slice 19 - Snapshot capture (`caztor/s19-snapshot-capture`, base s18, ~390) covers: turn-snapshots Pre-turn snapshot, Changed-files list, Snapshot scope and retention, Snapshot limits
- [x] 19.1 RED: capture hashes and reuses unchanged size+mtime, excluded dirs skipped, capture failure returns error; GREEN `snapshot-store.ts`.
- [x] 19.2 RED: >5 MB tracked without blob (`undoable:false`), 200 MB / 5,000 files partial with `unprotected`; GREEN.
- [x] 19.3 RED: diff created/modified/deleted, `userOnly` excluded, `mixed` flag, empty list; prune keeps 20 and collects blobs; GREEN.
- Verify: `npx vitest run packages/adapters-local/test/snapshot`.

### Slice 20 - Snapshot restore (`caztor/s20-snapshot-restore`, base s19, ~350) covers: turn-snapshots Whole-turn undo, Undo protects later user edits, Undo order
- [x] 20.1 RED: LIFO (`not_latest`, `already_undone`, `discarded`); GREEN `restore`.
- [x] 20.2 RED: preflight conflict writes nothing; `skip_conflicts`, `force`; pre-undo snapshot; created removed, deleted restored; GREEN.
- Verify: `npx vitest run packages/adapters-local/test/snapshot`.

### Slice 21 - Agent files (`caztor/s21-agent-files`, base s20, ~300) covers: agent-definitions One definition per provider, Behavioral prohibitions
- [x] 21.1 RED `agents/agents.test.ts`: shared sections identical across the three files; each forbids invented citations and shell commands; document text is data; GREEN `agents/{claude,opencode,codex}.md` with required frontmatter.
- Verify: `npx vitest run agents`.

### Slice 22 - Provisioner (`caztor/s22-provisioner`, base s21, ~380) covers: agent-definitions Provisioning, User-modified definition, Marked block preservation, Removable
- [x] 22.1 RED: absent creates and records; recorded hash replaces on change; differing hash or no record yields `skipped_user_modified`; explicit replace; state loss re-adopts equal file; GREEN `provisioner.ts`.
- [x] 22.2 RED: `AGENTS.md` block create/append/replace, bytes outside preserved, idempotent, createdByCaztor removal; GREEN.
- Verify: `npx vitest run packages/adapters-local/test/provisioner`.

### Fix slice 22b (`caztor/s22b-compile-hardening`, base `caztor/s22-provisioner`, real 794): verifier findings on batch G
- [x] 22b.1 Watcher re-arms after the project folder is replaced (folder identity), sub-folder watch failures degrade the watcher; compile log bounded (stat first, tail parsed, copy and served log capped with a marker, UI shows the last 200,000 characters); biblatex-without-biber error explained; engine unavailable reason on `/api/session` and in the UI; `compile.queued` / `compile.dequeued` events; cascade errors after a missing file dropped, `! LaTeX Error:` prefix stripped, paragraph boxes attributed to their first line.

### Slice 23 - Turn service (`caztor/s23-turn-service`, base s22, ~390) covers: agent-chat Session continuity; agent-definitions Definition change resets the conversation; turn-snapshots User edits during a turn, Revert note, Interrupted turns
- [x] 23.1 RED (fake ports): provision before snapshot; snapshot failure emits `snapshot_failed`, no spawn; GREEN `turn-service.ts`.
- [x] 23.2 RED: session resumed only if `agentHash` and `isolation` match, else new session and notice; GREEN.
- [x] 23.3 RED: diff runs on completed/cancelled/failed; user-only exclusion, mixed; empty list; revert note in next prompt; GREEN `prompt.ts`.
- Verify: `npx vitest run packages/core`.

### Slice 24a - Provider routes (merged with 24b into one branch `caztor/s24-chat-routes`, user decision; `caztor/s24a-provider-routes`, base s23, ~200) covers: agent-providers Provider selection, Per-provider model setting
- [x] 24a.1 RED: list, re-check, selected, model (regex `^[A-Za-z0-9._:/-]+$`, rejects `--dangerous`); GREEN `routes/providers.ts`.
- Verify: `npx vitest run packages/api`.

### Slice 24b - Chat routes (merged into `caztor/s24-chat-routes`; `caztor/s24b-chat-routes`, base s24a, ~250) covers: agent-chat Stop, Session continuity, Readable errors and busy state, Chat history
- [x] 24b.1 RED: turns stream as SSE, second send 409, stop, undo modes with conflict 409, history from `.caztor/chat/<provider>.jsonl`, sessions reset; GREEN `routes/chat.ts`.
- Verify: `npx vitest run packages/api`.

## Phase 5: Providers and chat UI (slices 25-30)

### Slice 25 - Claude mapper (`caztor/s25-claude-mapper`, base s24b, ~350) covers: agent-providers Normalized events, Error surfacing
- [x] 25.1 Derive sanitized trimmed fixture from `spike-raw/claude-turn-edit.jsonl` (no tokens); add synthetic error, cancel, resume and isolation-violation variants.
- [x] 25.2 RED table tests per native event (deltas, whole text, tool start/update/end, result error, unknown, malformed, ANSI, oversized line); GREEN `claude/mapper.ts`.
- Verify: `npx vitest run packages/adapters-local/test/providers/claude`.

### Slice 26 - Claude runner (`caztor/s26-claude-runner`, base s25, ~390) covers: agent-providers Provider detection, Isolation from global configuration, Isolation violation, Project CLI configuration, Safe launch
- [x] 26.1 [V] Check flags free of cost with `claude --help` (`--tools`, `--setting-sources`, `--restricted`, `--strict-mcp-config`, `--agents`); one minimal TOKEN SPEND call only if help is inconclusive; apply documented tier fallback.
- [x] 26.2 RED: argv equals observed set plus verified flags; prompt only on stdin (`; rm -rf ~`, `--x` prompts); env allowlist; model `--dangerous` rejected; GREEN `claude/runner.ts`.
- [x] 26.3 RED: `system/init` with `Bash` aborts `isolation_failed`; non-empty `mcp_servers` notice; tier I2 blocks until confirmation when `.mcp.json` exists; GREEN.
- [x] 26.4 RED: Stop escalation (SIGINT, 3 s SIGTERM, 2 s SIGKILL) with fake clock; exit without `result`; 20 unparseable lines; detection (missing, old version); GREEN.
- Verify: `npx vitest run packages/adapters-local/test/providers/claude`.

### Slice 27 - Chat UI core (`caztor/s27-chat-core`, base s26, ~390) covers: agent-chat Designed message UI, Streaming at any granularity, Tool activity cards, Stop
- [x] 27.1 RED: `chatReducer` accepts deltas and whole parts without loss, duplication or reordering; GREEN `chat-reducer.ts` (core).
- [x] 27.2 RED: MessageList, safe renderer (no raw HTML), ToolActivityCard states, Composer Send/Stop and disabled while running; GREEN `chat/`.
- Verify: `npx vitest run packages/core apps/web/src/chat`.

### Slice 28a - Chat header (`caztor/s28a-chat-header`, base s27, ~270) covers: agent-chat Provider header; agent-providers Provider selection (UI), Provider detection (UI)
- [x] 28a.1 Add official logo SVGs from vendor sources (never redrawn) and `NOTICE.md` (owner, source URL, retrieval date, non-affiliation); URL retrieval is a manual step.
- [x] 28a.2 RED: ProviderLogo text fallback on load error, ProviderSelect, ModelSelect, New chat, ProviderUnavailable with re-check; GREEN.
- Verify: `npx vitest run apps/web/src/chat`.

### Slice 28b - Chat results (`caztor/s28b-chat-results`, base s28a, ~270) covers: agent-chat Readable errors and busy state, Changed-files summary; agent-providers Error surfacing (UI)
- [x] 28b.1 RED: TurnSummary ("No files changed", undo only on latest turn), UndoConflictDialog (Cancel, rest, overwrite), ErrorCard (title, action, collapsed detail), NoticeBanner; GREEN.
- Verify: `npx vitest run apps/web/src/chat`.

### Slice 28c - Batch J verifier fixes (`caztor/s28b-recorder-race`, base s28; added by the coordinator, not in the original plan)
- [x] 28c.1 Recorder race: ending a user-write recording waits for saves, renames and removals in flight (`inflight()`), so a save racing with `done` is attributed to the user and survives strict and skip_conflicts undo.
- [x] 28c.2 `files_changed.notCovered` lists names Caztor cannot read (not UTF-8); shown in the chat as not covered by undo.
- [x] 28c.3 One warning notice per turn when an oversized provider line is dropped (line reader and mapper).
- [x] 28c.4 A linked `.caztor` gets an accurate turn error and history notice without host paths.

### Slice 29 - opencode adapter (`caztor/s29-opencode-adapter`, base s28b, ~400) covers: agent-providers Provider detection, Per-provider model setting, Error surfacing, Isolation from global configuration, Safe launch
- [x] 29.1 Fixtures from `spike-raw/opencode-turn-edit.jsonl` and both `opencode-error-*.jsonl` (no tokens).
- [x] 29.2 RED mapper tests (text, tool_use start+end, `step_finish` usage, 401/403/429 mapping, unknown); GREEN `opencode/mapper.ts`.
- [x] 29.3 [V] Check `opencode models` and extra permission keys and `XDG_CONFIG_HOME` isolation with `--help` and local runs; one minimal TOKEN SPEND call only if needed; apply fallbacks.
- [x] 29.4 RED: model-required gate (no spawn), argv, stdin prompt, bash-deny warning; GREEN `runner.ts`.
- Verify: `npx vitest run packages/adapters-local/test/providers/opencode`.

### Slice 30 - codex adapter (`caztor/s30-codex-adapter`, base s29, ~360) covers: agent-providers Provider detection, Codex command execution, Normalized events
- [x] 30.1 Write fixtures from documented shapes, labelled documented.
- [x] 30.2 RED mapper (`type` and legacy `item_type`, `turn.failed`); GREEN; RED argv/`resume`; `-m` kept or dropped per [V] fallback; "not installed" state; GREEN.
- Verify: `npx vitest run packages/adapters-local/test/providers/codex`.

## Phase 6: Sandbox and docs (slice 31)

### Slice 31 - Sandbox and README (`caztor/s31-sandbox-readme`, base s30, ~330) covers: latex-compile Sandboxed compile; security Disclosed limits
- [x] 31.1 RED: startup probe gates the setting; wrapper binds (project read-only, build and cache writable); start failure offers disable; GREEN `sandbox.ts`.
- [x] 31.2 Write `README.md` usage and security section with the disclosure text.
- Verify: `npx vitest run`; harness: `bwrap --version` probe and one compile with sandbox on.

## Apply batches (one session each)

A: 0, 1, 2, 3 · B: 4, 5, 6 · C: 7, 8 · D: 9, 10 · E: 11, 12 · F: 13, 14 · G: 15, 16 · H: 17a, 17b, 18 · I: 19, 20 · J: 21, 22 · K: 23, 24a, 24b · L: 25, 26 · M: 27, 28a, 28b · N: 29, 30 · O: 31 and final verification.

## Requirement traceability

All 72 requirements covered; see each slice's covers line. Uncovered: none.
