# Apply progress: caztor-mvp

Batches A (slices 1-3), B (fake-parity fix, slices 4-6), C (slices 7-8), D (hardening fix slice, slices 9-10), E (UI fix slice, slices 11-12) and F (slices 13-16, the compile pipeline on the server) are complete. Cumulative tasks done: 0.1-0.2, 1.1-1.4, 2.1-2.3, 3.1-3.3, 4.1-4.3, 5.1, 6.1-6.3, 7.1-7.2, 8.1-8.3, 9.1-9.4, 10.1-10.2, 10h.1, 11.1-11.2, 12.1-12.3, 13.1-13.5, 14.1-14.2, 15.1-15.4, 16.1-16.2.

Mode: Strict TDD (Vitest 5, `npx vitest run`; typecheck `npx tsc -b`). Delivery: auto-chain until batch D; from batch E (user decision of 2026-10-12) `exception-ok`: ONE branch per slice with `size:exception` accepted, `feature-branch-chain`, local branches only.

## Batch A (slices 1-3): complete

Tasks 0.1-0.2, 1.1-1.4, 2.1-2.3, 3.1-3.3 are marked `[x]` in tasks.md.

Branch chain (each from the previous): `feature/caztor-mvp` > `caztor/s01-scaffold` > `caztor/s02a-core-ports` > `caztor/s02b-core-paths-hash` > `caztor/s03a-infra-clock-spawner` > `caztor/s03b-memory-fs` > `caztor/s03c-node-infra`.

Splits (slice diff would have exceeded 400 changed lines): slice 2 into 2a (ports, 329) and 2b (paths and hash, 151); slice 3 into 3a (infra interfaces, fake clock, fake spawner, 394), 3b (in-memory file system fake, 273) and 3c (Node infra, 341).

### TDD Cycle Evidence

| Task | Test file | Layer | Safety net | RED | GREEN | Triangulate | Refactor |
|---|---|---|---|---|---|---|---|
| 1.3 | `packages/core/test/import-guard.test.ts` | Unit + repo scan | N/A (new) | module missing | 5/5 | node:, bare builtins, dynamic import, require, clean imports | none needed |
| 2.3 | `packages/core/test/ports.test.ts` | Unit + type-level | N/A (new) | module missing | 6/6, tsc green | exhaustive event switch, port signatures | none needed |
| 2.1 | `packages/core/test/paths.test.ts` | Unit | N/A (new) | module missing | 36/36 | accepted, invalid_path, outside_root, hidden tables | none needed |
| 2.2 | `packages/core/test/hash.test.ts` | Unit | N/A (new) | module missing | 4/4 | empty, abc, binary vectors, inequality | none needed |
| 3.2 | `packages/adapters-local/test/fakes/*.test.ts` | Unit | N/A (new) | modules missing | 19/19 | clock ordering/cancel/nesting, spawner chunks/split UTF-8/signals, fs codes/symlinks | none needed |
| 3.3 | `packages/adapters-local/test/node-infra.test.ts` | Unit + opt-in process harness | N/A (new) | module missing | 12 pass, 3 opt-in pass | options, env, stdin, exit, kill, fs, clock | none needed |
| 1.1, 1.2, 3.1 | n/a | Structural | N/A | n/a | tsc green | skipped: config/type-only | n/a |
| 1.4 | n/a | Structural | N/A | n/a | n/a | skipped: config flip | n/a |

### Work Unit Evidence

| Slice | Focused test | Runtime harness | Rollback boundary |
|---|---|---|---|
| 1 | `npx vitest run`: 5 passed | N/A: no runtime boundary | revert `caztor/s01-scaffold` |
| 2a, 2b | `npx vitest run packages/core`: 51 passed | N/A: pure code | revert each branch |
| 3a-3c | `npx vitest run packages/adapters-local`: 34 passed | `CAZTOR_REAL_BIN=1 npx vitest run packages/adapters-local`: real `node -e ""` spawn, env isolation, group kill passed | revert each branch |

### Deviations

- Slices 2 and 3 split (see above); no pre-agreed split point existed in tasks.md.
- Task 2.3 was done before 2.1 because `parseRelPath` depends on `RelPath` and `StoreError`.
- `ports.ts` also exports runtime constants `PROVIDER_IDS` and `TURN_ERROR_CODES` so the port test has a runtime RED.
- `FileSystem` shape was not specified in the design; defined in `infra.ts` (readFile, writeFile with `exclusive`, mkdir, readdir, stat, lstat, realpath, rename, rm, copyFile).
- `ChildHandle.exit` rejects when the process cannot start (ENOENT).
- TypeScript 7.0.2 and Vitest 5.0.3 (latest at install time); each package has `src/index.ts` so `tsc -b` has inputs.

## Batch B (fake-parity fix, slices 4, 5, 6): complete

Tasks 4.1-4.3, 5.1 and 6.1-6.3 are marked `[x]` in tasks.md, whose branch names now match the real ones.

Branch chain (each from the previous, starting at `caztor/s03c-node-infra`): `caztor/s03d-fake-parity` > `caztor/s04a-fs-sandbox` > `caztor/s04b-store-containment` > `caztor/s04c-store-writes` > `caztor/s04d-store-structure` > `caztor/s05-state-store` > `caztor/s06a-api-security` > `caztor/s06b-token-headers`.

Real changed lines (additions plus deletions, `package-lock.json` excluded): s03d 294, s04a 127, s04b 357, s04c 236, s04d 166, s05 292, s06a 381, s06b 140 (plus this docs commit).

Splits: slice 4 (about 760 real lines) into 4a sandbox, 4b containment and reads, 4c atomic writes, 4d folders, rename and remove; slice 6 (about 520) into 6a gates and 6b token and headers.

### TDD Cycle Evidence (batch B)

| Task | Test file | Layer | Safety net | RED | GREEN | Triangulate | Refactor |
|---|---|---|---|---|---|---|---|
| fix 1-3 (fs parity) | `adapters-local/test/contract/fs-contract.test.ts` | Contract, fake and real fs | 82 passed | 4 failed on the fake | 43 passed | `..`, links before `..`, exclusive vs dangling link, rename onto dir/file | recursive `mkdir` rewritten as a resolver |
| fix 4-6 (spawner) | `adapters-local/test/node-infra.test.ts`, `fakes/fake-spawner.test.ts` | Unit + default real ENOENT/NUL | 43 passed | 3 failed | 48 passed, tsc green | sync throw, NUL, missing binary, exit vs close | typed `ChildProcessWithoutNullStreams` |
| 4.1, 4.3 | `adapters-local/test/project-store.test.ts` | Contract, fake and real fs | N/A (new) | module missing | 44 passed | traversal, absolute, NUL, escaping file/parent links, dangling, reserved link, non-regular, AGENTS.md both ways | error-code helpers |
| 4.2 write | `adapters-local/test/project-store-write.test.ts` | Contract, fake and real fs | 44 passed | 48 failed | 48 passed | null/hash/any, stale, vanished, binary, reserved, escape, dangling, inner link, atomic failure, 20 MB | stat handling simplified |
| 4.2 structure | same file | Contract | 28 passed | 20 failed | 48 passed | collision, missing, reserved, escaping, into itself, link moved, recursive vs not | none needed |
| 5.1 | `adapters-local/test/state-store.test.ts` | Contract, fake and real fs | N/A (new) | module missing | 24 passed | missing, 5 corrupt shapes, field-level repair, merge, concurrent, atomic failure, escaping `.caztor` | none needed |
| 6.1 | `api/test/security.test.ts` | Request matrix (`app.request`) | N/A (new) | module missing | 31 passed | one violating request per rule plus a positive control | none needed |
| 6.2 | `api/test/token.test.ts` | Unit | 31 passed | module missing | 8 passed | equal, prefix, empty, multi-byte, dev/prod env | middleware uses `timingSafeEqual` |
| 6.3 | `api/test/security.test.ts` | Request matrix | 31 passed | 3 failed | 42 passed | static, API and rejection responses | none needed |

### Work Unit Evidence (batch B)

| Slice | Focused test | Runtime harness | Rollback boundary |
|---|---|---|---|
| s03d | `npx vitest run packages/adapters-local`: 48 passed | `CAZTOR_REAL_BIN=1 npx vitest run packages/adapters-local`: 169 passed at end of batch | revert `caztor/s03d-fake-parity` |
| s04a-s04d | `npx vitest run packages/adapters-local/test/project-store*`: 92 passed | same suite runs against a real temporary directory | revert each branch |
| s05 | `npx vitest run packages/adapters-local/test/state-store.test.ts`: 24 passed | real temporary directory | revert `caztor/s05-state-store` |
| s06a, s06b | `npx vitest run packages/api`: 42 passed | `app.request()` over the real Hono app | revert each branch |

Full runs at each branch tip: s03d 99 passed, s04a 101, s04b 145, s04c 173, s04d 193, s05 217, s06a 248, s06b 259; 3 opt-in skipped; `npx tsc -b` exit 0 on all.

### Deviations (batch B)

- Slice 4 and slice 6 split (see above); the original slice 4 estimate of 390 was wrong by about two times because the shared fake and real sandbox and the real-path resolver were not counted.
- `ProjectStore` (adapter) omits `watch`; the watcher belongs to slice 12 task 12.3. It adds `readText` (UTF-8, 2 MB) beside `read`, which returns raw bytes for any regular file so undo and snapshots keep working.
- `FileEntry` is unchanged: binary and oversized files are listed, and `readText` refuses them with `not_text` or `too_large`.
- The tree lists only regular files and folders. Symbolic links and special files are omitted from the listing and never descended into.
- A dangling symbolic link is refused as `outside_root` because its target cannot be proven to stay inside the project.
- A non-empty folder removed without `recursive` returns `invalid_path` because `StoreError` has no dedicated code.
- Temporary files use the prefix `.caztor-tmp-` and are never listed.
- `@caztor/core` now has `exports` and `@caztor/adapters-local` depends on it (first cross-package import).
- State defaults chosen from the latex-compile spec: continue past errors (stop-on-error off), auto-compile on.
- `DELETE` requires `Content-Type: application/json` even without a body, as the design states for every non-GET; the web client must send it.
- `createApp(deps, security)` takes an empty `ApiDeps` for now; routes arrive in slice 8.
- Hono 4.13.13 installed (current stable at install time).

## Batch C (slices 7, 8): complete

Tasks 7.1-7.2 and 8.1-8.3 are marked `[x]` in tasks.md.

Branch chain (each from the previous, starting at `caztor/s06b-token-headers`): `caztor/s07a-static-token` > `caztor/s07b-server-main` > `caztor/s08a-session-routes` > `caztor/s08b-files-read` > `caztor/s08c-files-write` > `caztor/s08d-files-structure` > `caztor/s08e-events-sse`.

Real changed lines (additions plus deletions, `package-lock.json`, `openspec/` and the HTML fixture excluded): s07a 243, s07b 312, s08a 322, s08b 262, s08c 185, s08d 268, s08e 229 (plus this docs commit).

Splits: slice 7 (555 real lines) into 7a static serving and token injection, 7b bind, fallback and main; slice 8 (about 1,270 real lines) into 8a session and settings, 8b file tree and text read, 8c hash-checked save and create, 8d rename, delete and upload, 8e events stream.

[V] 7.1: Node v26.8.2 runs `node apps/server-local/src/main.ts` with type stripping across the workspace packages (the symlinked packages resolve to real paths outside `node_modules`, where stripping applies). Each package needed an `exports` entry pointing at `src/index.ts`. The `tsx` fallback was NOT needed.

### TDD Cycle Evidence (batch C)

| Task | Test file | Layer | Safety net | RED | GREEN | Triangulate | Refactor |
|---|---|---|---|---|---|---|---|
| 7.2 token injection | `server-local/test/html.test.ts` | Unit | N/A (new) | module missing | 4 passed | placeholder, none, attribute escaping, `$&` pattern | none needed |
| 7.2 static | `server-local/test/static.test.ts` | Request tests over a fixture web root | N/A (new) | module missing; then 1 failed (no-store) | 15 passed | index, assets, headers, Host gate, 7 traversal and malformed paths, unbuilt app, `/api/*` not a page | none needed |
| 7.2 bind and start | `server-local/test/server.test.ts` | Unit with an injected listen | N/A (new) | module missing | 11 passed | default port, fallback, loopback on every attempt, other error, attempt limit, token source, Host after fallback, API mount | none needed |
| 7.2 cli | `server-local/test/cli.test.ts` | Unit | N/A (new) | module missing | 6 passed | argument, `--`, four usage errors | none needed |
| 8.1 | `server-local/test/routes/session.test.ts` | Request tests, real stores | 294 passed | 14 of 19 failed | 19 passed | token and Host rejection, defaults, probes, 10 invalid patches | none needed |
| 8.2 errors | `api/test/store-errors.test.ts` | Unit | N/A (new) | module missing; then 8 failed (test expectation) | 11 passed | every code, conflict with and without hash | test assertion corrected |
| 8.2 read | `server-local/test/routes/files.test.ts` | Request tests, real project store | 314 passed | 30 of 36 failed | 36 passed | list, text, 6 error paths, symlink escape, binary, 2 MB | none needed |
| 8.2 write, create | same file | Request tests | 338 passed | 5 failed after route, hash helper was async | 61 passed | stale, null base, deleted, reserved, 5 bad bodies, collision, missing parent | `exists` (not `conflict`) expected for a null base on an existing file |
| 8.2 rename, delete, upload | `server-local/test/routes/files-structure.test.ts` | Request tests | 361 passed | 22 of 29 failed | 29 passed | collision, reserved, recursive on and off, 20 MB and 20 MB + 1, content types | gate tests moved to the security middleware alone |
| 8.3 | `api/test/sse.test.ts` | Unit and stream reads with a fake clock | 390 passed | module missing | 9 passed | framing, newline escaping, name injection, ids, fan-out, heartbeat at 14,999 and 15,000 ms, disconnect cleanup | none needed |
| 7.1 | n/a | Runtime check | N/A | n/a | node ran across packages | skipped: verification task, not code | n/a |

### Work Unit Evidence (batch C)

| Slice | Focused test | Runtime harness | Rollback boundary |
|---|---|---|---|
| s07a, s07b | `npx vitest run apps/server-local`: 35 passed | real server on a temporary project (below) | revert each branch |
| s08a-s08e | `npx vitest run apps/server-local/test/routes packages/api`: routes use a real temporary project folder | same real server run | revert each branch |

Full runs at each branch tip: s07a 278 passed, s07b 294, s08a 314, s08b 338, s08c 361, s08d 390, s08e 399; 3 opt-in skipped; `npx tsc -b` exit 0 on all.

Runtime harness (end of batch): `CAZTOR_DEV=1 CAZTOR_TOKEN=... node apps/server-local/src/main.ts <empty temp dir>` bound `127.0.0.1:4317` (checked with `ss -ltn`); `curl` without the token to `/api/session` returned 401, with the token 200, `/api/files` 200, a foreign `Host` 403, `DELETE` without a JSON content type 415, `/api/events` 200; the process was stopped and the port was released.

### Deviations (batch C)

- Slice 7 and slice 8 split (see above); the original estimates of 200 and 390 were low by about 2.8 and 3.2 times.
- `apps/web/dist` does not exist yet, so the real server answers `/` with 404 until slice 9; token injection is tested against a fixture. The runtime check used the development token (`CAZTOR_DEV=1`) because the production token is only delivered through the page.
- Each package got `exports` pointing at `src/index.ts`, and `@caztor/adapters-local` now has a real public index (it was `export {}`). `@hono/node-server` 2.1.4 was added to `apps/server-local`.
- `ApiDeps` is `{ projectName, store, state, events, clock, engine?, sandbox? }`. `engine` and `sandbox` are optional probes and are reported unavailable until the compiler (slice 15) and sandbox (slice 31) are wired.
- `ProjectStore` has no code for "folder not empty"; `DELETE /api/files` without `recursive=true` returns 409 `not_empty` when the store answers `invalid_path` for a folder, and recursive deletion is requested with `?recursive=true`.
- A `PUT /api/files/content` with `baseHash: null` on an existing file returns 409 `exists` (the store's code for "must not exist"), not `conflict`; a stale hash returns `conflict` with `currentHash`.
- Route tests live in `apps/server-local/test/routes` and use the real project and state stores over a real temporary folder, because `packages/api` cannot import the Node adapters; `packages/api/test/support.ts` now tests the security middleware alone (the real upload route would shadow a probe at the same path).
- `index.html` is served with `Cache-Control: no-store`; static assets are served by `apps/server-local/src/static.ts` behind the same Host check and security headers.
- `main.ts` resolves the project folder from `INIT_CWD` when run through `npm start`. The `start` script is `node apps/server-local/src/main.ts`.
- `Last-Event-ID` resume is not implemented (the design does not require it); ids are a per-process sequence.
- The `AGENTS.md` created-by-Caztor flag is not wired into the store yet (the provisioner arrives in slice 22), so any `AGENTS.md` is listed for now.

## Batch D (hardening fix slice, slices 9, 10): complete

Tasks 9.1-9.4 and 10.1-10.2 are marked `[x]` in tasks.md. Slice 11 was not started.

Branch chain (each from the previous, starting at `caztor/s08e-events-sse`): `caztor/s08f-gate-scope` > `caztor/s08g-fs-mode` > `caztor/s08h-state-hardening` > `caztor/s08i-store-hardening` > `caztor/s09a-web-scaffold` > `caztor/s09b-api-client` > `caztor/s09c-layout-model` > `caztor/s09d-workspace` > `caztor/s09e-disclosure` > `caztor/s09f-app-shell` > `caztor/s10a-tree-model` > `caztor/s10b-tree-render` > `caztor/s10c-open-files` > `caztor/s10d-create` > `caztor/s10e-rename` > `caztor/s10f-delete` > `caztor/s10g-events-refresh`.

Real changed lines (additions plus deletions, `package-lock.json` and `openspec/` excluded): s08f 133, s08g 98, s08h 56, s08i 353, s09a 356, s09b 273, s09c 213, s09d 294, s09e 350, s09f 220, s10a 133, s10b 343, s10c 167, s10d 286, s10e 248, s10f 337, s10g 386 (plus this docs commit).

Splits: the nine-fold slice 9 estimate (~380) became six branches (a scaffold and tokens, b API client, c layout model, d workspace, e dialog and notice, f app shell) at about 1,700 real lines; slice 10 (~390) became seven branches (a model, b render, c open, d create, e rename, f delete and upload, g events) at about 1,650. The estimates were low by about 4.4 and 4.2 times, mostly tests (about 45 percent) and CSS.

### Hardening fix items (verifier findings on batch B)

1. Lost updates: a per-path keyed mutex (sorted acquisition) serializes the check and the replace in `write`, and `rename` locks source and destination; concurrent tests on the fake and the real file system.
2. Parent swap: `realpath` of the parent after the temporary write and before the rename, abort and remove the temporary file on a mismatch; injected-wrapper tests swap before and after the temporary write. Residual window recorded in the design threat matrix.
3. Mode bits: `FsStats.mode` and `FileSystem.chmod` (fake and Node in parity, fs contract tests); `write` applies the old mode to the temporary file.
4. State load: `load()` catches a failing `.caztor` inspection (ELOOP, EACCES) and returns the defaults; `update()` still throws.
5. State keys: `provisioned` keys must pass `parseRelPath`, others are dropped.
6. Gate scope: token, content-type and body gates cover `/api` and `/api/*`; any method other than GET and HEAD outside the API gets 405 before a handler.
7. Empty token: `securityMiddleware` (and so `createApp`) throws below 16 characters.
8. Temp prefix: a path with any segment starting `.caztor-tmp-` is refused as `hidden` by `locate` on every operation.
9. Unbounded reads: `read` checks `stat` size against 20 MB, `write` hashes only when a hash is expected and refuses a larger existing file with `too_large`; `expect null` and `any` never read the old file.
10. Negative tests: uppercase Host, trailing-dot Host, token in the query string, security headers on 404 and 500.

### TDD Cycle Evidence (batch D)

| Task | Test file | Layer | Safety net | RED | GREEN | Triangulate | Refactor |
|---|---|---|---|---|---|---|---|
| fix 6, 7, 10 | `api/test/security-scope.test.ts` | Request matrix | 399 passed | 8 failed | 416 passed | `/api`, lookalike `/apiary`, four methods outside, short and empty tokens, boundary 16 | none needed |
| fix 3 | `adapters-local/test/contract/fs-contract.test.ts`, `project-store-write.test.ts` | Contract, fake and real fs | 416 passed | 6 failed | 422 passed | chmod, link following, rename keeps mode, 0755 and 0600 | none needed |
| fix 4, 5 | `adapters-local/test/state-store.test.ts` | Contract | 422 passed | 6 failed | 428 passed | self link, EACCES, valid and 6 invalid keys | none needed |
| fix 1, 2, 8, 9 | `adapters-local/test/project-store-hardening.test.ts` | Contract, fake and real fs | 428 passed | 27 failed | 462 passed | same-hash, create-only, different files, after failure, rename, swap before and after, 4 prefix paths, 3 large-file cases | write split into `replaceFile` |
| 9.1 | `web/src/api/token.test.ts`, `client.test.ts` | Unit with a fake fetch | N/A (new) | modules missing | 15 passed | meta variants, headers on GET, JSON, DELETE, upload, error shapes | none needed |
| 9.3 | `web/src/layout/panes.test.ts`, `storage.test.ts`, `Workspace.test.tsx` | Unit and jsdom component | N/A (new) | modules missing; 3 component fixes (jsdom widths, focus) | 36 passed | 11 invalid shapes, minimum per width, blocked storage, restore, corrupt, keyboard resize | none needed |
| 9.4 | `web/src/disclosure/DisclosureNotice.test.tsx`, `app/App.test.tsx` | jsdom component | N/A (new) | modules missing | 12 passed | shown or not, once per project, failure keeps it open, Escape ignored | none needed |
| 10.1 | `web/src/files/tree.test.ts`, `FileTree.test.tsx` | Unit and jsdom component | N/A (new) | modules missing | 36 passed | sorting, nesting, reserved, binary, large, learned binary, errors | `classifyFile` takes a plain path and size |
| 10.2 create, rename | `FileTree.create.test.tsx`, `FileTree.test.tsx` | jsdom component | 95 passed | modules missing | 107 passed | collision, folder context, invalid names, Escape, folder rename, create then rename | tests anchored to row names |
| 10.2 delete, upload | `FileTree.delete.test.tsx`, `FileTree.upload.test.tsx` | jsdom component | 107 passed | modules missing | 124 passed | file and folder, cancel, Escape, failure, 20 MB boundary, collision, partial selection | none needed |
| 10 events | `web/src/api/sse-parser.test.ts`, `events.test.ts`, `FileTree.events.test.tsx` | Unit, stream reads, jsdom | 124 passed | modules missing | 146 passed | every chunk cut, CRLF split, reconnect backoff, resume, burst merge, unsubscribe | CR handling rewritten with a skip flag |
| 9.2 | n/a | Runtime check | N/A | n/a | pixel minimums supported | skipped: verification task | n/a |

### Work Unit Evidence (batch D)

| Slice | Focused test | Runtime harness | Rollback boundary |
|---|---|---|---|
| s08f-s08i | `npx vitest run packages/api packages/adapters-local apps/server-local` | `CAZTOR_REAL_BIN=1 npx vitest run packages/adapters-local`: 215 passed | revert each branch |
| s09a-s09f | `npx vitest run apps/web`: 51 passed at s09d, 61 at s09f | `npm run build -w @caztor/web` and the real server (below) | revert each branch |
| s10a-s10g | `npx vitest run apps/web/src/files`: 56 passed at s10f, `apps/web` 146 at s10g | same | revert each branch |

Full runs at each branch tip: s08f 416 passed, s08g 422, s08h 428, s08i 462, s09a 469, s09b 477, s09c 503, s09d 513, s09e 518, s09f 523, s10a 537, s10b 544, s10c 549, s10d 557, s10e 569, s10f 586, s10g 608; 3 opt-in skipped; `npx tsc -b` exit 0 on all.

Runtime harness (end of batch, tip `caztor/s10g-events-refresh`): `npm run build -w @caztor/web` produced `dist/index.html`, one JS and one CSS asset; `node apps/server-local/src/main.ts <temp dir with main.tex>` served `GET /` 200 `text/html` with the token meta tag populated (64 characters, placeholder absent), the JS 200 `text/javascript`, the CSS 200 `text/css`, `GET /api/files` with the token 200 listing `main.tex`, without the token 401, `POST /` 405, `GET /api/events` 200 (held open until `curl -m 2` stopped it), and the CSP header present; the server was killed and port 4317 was free afterwards. There is no browser here: the rendered layout and styles were NOT visually verified.

### Deviations (batch D)

- Slices 9 and 10 split into 13 branches (see above); the original estimates were low by about 4 times.
- Design D1 names Vite/React and `react-resizable-panels`; installed versions are react and react-dom 19.3.0, vite 8.3.4, @vitejs/plugin-react 6.1.2, react-resizable-panels 4.14.4, @testing-library/react 16.3.3, user-event 14.6.7, jest-dom 7.0.1. All work with Vitest 5 and TypeScript 7. The panes library v4 takes numeric minimums as pixels, so the percentage conversion in D1 is unnecessary; saved layouts are validated in percent against the pixel minimums for the measured window width (1,440 px when unknown).
- A saved layout is discarded when a pane is below its pixel minimum for the current width, so the 15/35/30/20 defaults themselves fall below the chat minimum on windows narrower than 1,500 px; the library clamps them on first layout.
- The file tree asks for confirmation before deleting a file as well as a folder (the spec requires it for folders only).
- Folder delete from the UI always sends `recursive=true` after confirmation; the 409 `not_empty` path is only reachable by other clients.
- New files, folders and uploads go into the folder last clicked in the tree (the project root otherwise); names with `/` or `\` are refused in the form.
- The tree learns that a file is not text from the server (`not_text`, `too_large`) when the extension and size do not already say so; extension list is in `files/tree.ts`.
- Selecting a text file reads it and shows a short summary in the editor pane; the editor itself arrives in slice 11.
- `vite.config.ts` and `index.html` are not type-checked by `tsc -b` (the web tsconfig covers `src`); the build proves them.
- The fake API and jsdom limits: jsdom does no layout, so the pane library treats a pointer click near a divider as a drag; component tests that type into a box focus it by script.
- `apps/web/tsconfig.json` emits declarations to `dist-types` (git-ignored) so `dist` belongs to Vite.


## Batch E (UI fix slice, slice 11 Editor, slice 12 External changes): complete

Tasks 10h.1, 11.1-11.2 and 12.1-12.3 are marked `[x]` in tasks.md, whose forecast table now records the one-branch-per-slice decision.

Branch chain (each from the previous, starting at `caztor/s10g-events-refresh`): `caztor/s10h-ui-store-fixes` > `caztor/s11-editor` > `caztor/s12-editor-conflicts`. Under the new delivery decision each slice is one branch with small work-unit commits.

Real changed lines (additions plus deletions, `package-lock.json` and `openspec/` excluded): s10h 410, s11 1,706, s12 1,914. All three are `size:exception`.

### Fix slice items (verifier findings on batch D)

1. Temp file mode: `FileSystem.writeFile` takes `mode` (creation only, like `open(2)`); the fake and the Node file system agree; `replaceFile` creates the temporary file with `0o600` when it replaces an existing file and then applies the original mode before the rename; the fs contract suite and the store write suite assert the mode passed and the mode observed right after creation.
2. Dialog: the rest of the page is made `inert` while a dialog is open and restored on close (only what the dialog changed); a `focusin` listener, a `blur` check and a `MutationObserver` on `disabled` keep focus inside; the panel is focusable (`tabIndex -1`) as the last resort; on close focus returns to the trigger, or when it was removed to the pane that held it (`data-focus-home` on `PaneShell`).
3. Layout: `parseLayout(value)` checks only the shape, pane ids, finite positive sizes and a total near 100; the width parameter and `REFERENCE_WIDTH` are gone; the pane library clamps to pixel minimums.
4. A file named `<img src=x onerror=alert(1)>.tex` is rendered as text in the tree (test added; React already escaped it, so it passed on first run as a regression test); the vacuous Workspace typing test was removed and replaced by a real editor test in slice 11.

### TDD Cycle Evidence (batch E)

| Task | Test file | Layer | Safety net | RED | GREEN | Triangulate | Refactor |
|---|---|---|---|---|---|---|---|
| fix 1 | `adapters-local/test/contract/fs-contract.test.ts`, `project-store-write.test.ts` | Contract, fake and real fs | 212 passed | 4 failed | 216 passed | new file, existing file keeps bits, exclusive, 0600 and 0644 originals | test wrapper made a `Proxy` (spreading a class instance lost its methods) |
| fix 2 | `web/src/components/Dialog.test.tsx` | jsdom component | 154 passed | 4 failed of 8 | 8 passed | inert set and restored, already-inert region kept, Tab and Shift+Tab wrap, blur retention, focus escape, return to trigger, return to pane | none needed |
| fix 3 | `layout/panes.test.ts`, `storage.test.ts`, `Workspace.test.tsx` | Unit and jsdom | 154 passed | 3 failed | 155 passed | small pane kept, zero pane rejected, narrow window keeps saved layout | removed width parameter |
| fix 4 | `files/FileTree.test.tsx` | jsdom component | 155 passed | 1 failed (assertion on `innerHTML` was wrong: attribute text) | 12 passed | `img` absent, no `onerror` attribute | none needed |
| 11.1 | `editor/bibtex.test.ts`, `languages.test.ts` | Unit (tokenizer driven by `StringStream`, highlight classes via `highlightTree`) | N/A (new) | modules missing | 22 passed | entry types, parentheses, nested braces, escaped quotes, multi-line values, macros and `#`, `@string`, `@comment`, `@preamble`, recovery, stray characters, extension table | none needed |
| 11.2 api | `api/client.test.ts` | Unit with a fake fetch | 8 passed | 2 failed | 10 passed | PUT with hash and with null, 409 with `currentHash` | none needed |
| 11.2 session | `editor/session.test.ts` | Unit with fake timers | N/A (new) | module missing | 20 passed | debounce reset, 799 ms boundary, saving state, edit during save, edit back to saved, 409, failure and retry, per-file buffers, rename, forget, subscription, dispose | none needed |
| 11.2 view | `CodeEditor.test.tsx`, `EditorPane.test.tsx`, `diff.test.ts`, `App.test.tsx` | jsdom component (CodeMirror runs in jsdom with two `Range` stubs in the test setup) | 180 passed | modules missing | 693 passed at slice end | typing reports whole text, external text not reported as an edit, cursor kept before and after the change, scroll, per-file cursor, save shortcut, error and retry, conflict status, rename, delete, unsaved-changes guard | none needed |
| 12.1, 12.2 session | `editor/session.external.test.ts`, `session.resolve.test.ts` | Unit with fake timers | 693 passed | 16 failed (external); resolve tests were written after the implementation and checked by mutation (see deviations) | 50 passed | own echo, stale event, burst, reconnect, deleted, identical text, conflict refresh, keep mine, load disk, copy names, failures | none needed |
| 12.2 view | `EditorPane.conflict.test.tsx`, `App.test.tsx` | jsdom component | 267 passed | 8 failed | 269 passed | banner, four actions, copy note, comparison with both texts, deletion, problem message | `comparing` reset when the conflict ends |
| 12.3 infra | `fakes/fake-watcher.test.ts`, `node-infra.test.ts` | Unit, plus opt-in real events | 17 passed | 1 failed | 20 passed, opt-in 21 | fake counts and failure to start; real nested event and no event after close | none needed |
| 12.3 store | `project-store-watch.test.ts` | Contract, fake and real file system, fake watcher and clock | 270 passed | 46 failed | 270 passed | lifecycle, debounce, burst, unchanged event, new and deleted, folder moved in and removed, store write, temp and reserved paths, `AGENTS.md`, links, rescan, periodic rescan, failed start, watcher error, failing listener | `null` event path handled as a full scan |
| 12.3 server | `server-local/test/server-watch.test.ts` | Request tests with a manual watcher | 121 passed | 3 failed | 124 passed | event stream receives `file_changed`, watcher closed with the server, started once | watch starts after the app is built |

### Work Unit Evidence (batch E)

| Slice | Focused test | Runtime harness | Rollback boundary |
|---|---|---|---|
| s10h | `npx vitest run`: 622 passed, 3 skipped | none beyond the real fs contract suite | revert `caztor/s10h-ui-store-fixes` |
| s11 | `npx vitest run apps/web/src/editor`: 106 passed at the end | real server and headless Chromium: file opens, highlighted in light and dark, `.bib` highlighted, selection visible | revert `caztor/s11-editor` |
| s12 | `npx vitest run packages/adapters-local apps/server-local apps/web/src/editor` | real server and headless Chromium end to end (below) | revert `caztor/s12-editor-conflicts` |

Full runs at each branch tip: s10h 622 passed, s11 693, s12 788; 3 to 4 opt-in skipped; `npx tsc -b` exit 0 on all. `CAZTOR_REAL_BIN=1 npx vitest run packages/adapters-local`: 270 passed, 0 skipped.

End-to-end (tip `caztor/s12-editor-conflicts`): `npm run build -w @caztor/web`, `node apps/server-local/src/main.ts <temp project>`, headless Chromium. Typing in `main.tex` showed "Unsaved changes", then "Saved" after the idle period, and the file on disk contained the text. Writing the file from outside reloaded the clean buffer with the cursor unchanged; a long file kept its scroll position (3026 px before and after). Typing then writing from outside within the idle period raised the conflict banner, kept the disk version on disk and the user's text in the editor, Compare showed both versions, and Load disk version replaced the text. The browser console showed one `409` resource error, which is the rejected save; the server process was stopped afterwards and port 4317 was free.

### Deviations (batch E)

- The 12.2 resolution tests were written after the implementation of `keepMine`, `takeDisk` and `saveCopy` (they were added in the same step as the 12.1 session code). I checked them by mutation instead: removing the base-hash update made 4 fail and removing the name-collision retry made 1 fail. The `diff.ts` helper was also written with its test in one step; the missing-module RED was observed afterwards by moving the file away.
- The 400-line cap no longer applies (user decision); slices 17, 24 and 28 stay single branches in tasks.md.
- Design D9 says `Copy my text`; the banner button reads "Save a copy" (writes `<name>-copy.<ext>` next to the file, then `-copy-2`, and so on).
- Design D9 says the watcher is best effort plus a forced rescan after every turn and undo. `ProjectStore.rescan()` exists and a 5 s periodic rescan runs while anyone watches; wiring the rescan after turns and undo belongs to slices 23 and 24.
- Two event streams are open (the file tree and the editor session each call `subscribeEvents`). The hub supports it; a shared stream is a later cleanup.
- A buffer based on a deleted file has `baseHash: null`, and "Keep mine" then creates the file again through the same hash-checked route.
- Not verified: the `/mnt/c` (9p) mount for the recursive watcher; keyboard focus rings and the merge view in the dark theme were not inspected; the bundle is 590 kB (CodeMirror plus React), which Vite warns about; no code splitting was done.
- Dependencies installed (npm, current stable): `@codemirror/state` 6.7.6, `@codemirror/view` 6.43.14, `@codemirror/commands` 6.11.1, `@codemirror/language` 6.13.1, `@codemirror/legacy-modes` 6.5.5, `@lezer/highlight` 1.2.5, `@codemirror/merge` 6.12.2.
- `FakeApi` changed: it now keeps per-file hashes that survive a rename, supports `writeFile` with 409 `conflict` and `exists`, `changeOnDisk` and `removeFromDisk`; the one test that expected `sha256:fake` was updated.


## Batch F (slices 13 Compile parsing I, 14 Compile parsing II, 15 Tectonic adapter, 16 Coordinator and compile routes): complete

Tasks 13.1-13.5, 14.1-14.2, 15.1-15.4 and 16.1-16.2 are marked `[x]` in tasks.md.

Branch chain (each from the previous, starting at `caztor/s12-editor-conflicts`): `caztor/s13-compile-parse` > `caztor/s14-log-parser` > `caztor/s15-tectonic-adapter` > `caztor/s16-compile-routes`. One branch per slice, small work-unit commits, `size:exception` accepted.

Real changed lines (additions plus deletions, `package-lock.json` and `openspec/` excluded): s13 992 (585 without the recorded fixtures), s14 306, s15 1,413, s16 982. All except s14 are `size:exception`.

### TDD Cycle Evidence (batch F)

| Task | Test file | Layer | Safety net | RED | GREEN | Triangulate | Refactor |
|---|---|---|---|---|---|---|---|
| 13.1 | `adapters-local/test/tectonic/fixtures.test.ts` | Unit (fixture scan) | N/A (new) | scan failed on a planted fixture holding the home path (observed, then removed) | 3 passed | home, tmp, user name, empty file | none needed |
| 13.2 | `tectonic/diagnostics.test.ts` | Unit on recorded fixtures | N/A (new) | module missing | 12 passed | repeated errors listed once, `ch/one` resolved to `.tex`, wrapper and transcript dropped, file-less error, colons in message, unresolved file, notes only, located and file-less warnings, markers consumed | none needed |
| 13.3 | `tectonic/status.test.ts` | Unit | 12 passed | 10 failed (export missing) | 25 passed | success, failed-with-errors (exit 0), failed (halt), cancelled, timed-out, synthetic error for exit 101, for exit 1 with PDF, for exit 0 without PDF, none when a located error exists, tail bounds | none needed |
| 13.4 | `tectonic/status.test.ts` | Unit on the recorded offline fixture | 25 passed | 3 failed | 30 passed | recorded offline text, other texts (dns, refused, timed out), fallback by downloading phase, no hint without network signs, no hint for a located error | none needed |
| 13.5 | `core/test/biblatex-scan.test.ts` | Unit | N/A (new) | 7 failed (function missing) | 7 passed | `\usepackage`, package list, `\RequirePackage`, `\addbibresource`, comments vs escaped `%`, BibTeX project, `backend=bibtex`, lookalike package name | none needed |
| 14.1 | `tectonic/log-parser.test.ts` | Unit on recorded logs | N/A (new) | module missing | 9 passed | undefined reference and citation, summary and TeX errors skipped, Package and Class warnings with file stack, 79-column rejoin, unresolved file, no line, repeated warning, none | wrapped-line join loop fixed (RED showed the bug) |
| 14.2 | `tectonic/log-parser.test.ts`, `diagnostics.test.ts` | Unit | 9 passed | 7 failed | 15 + 13 passed | engine warning, `../` from the log only, one file named once, two files, inside spellings ignored, prefix-sharing sibling folder | none needed |
| 15.1, 15.2 | `tectonic/command.test.ts` | Unit | N/A (new) | module missing | 10 passed | both modes, no `--synctex` or shell escape in either, `./` prefix, five unsafe main names, allowlist, secrets dropped, untrusted forced, unset skipped | none needed |
| 15 reader | `tectonic/line-reader.test.ts` | Unit | N/A (new) | module missing | 13 passed | split lines, split UTF-8, CRLF, 4 KB cut in one chunk and across chunks, nine note mappings, unknown notes | none needed |
| 15.3, 15.4 | `tectonic/compiler.test.ts`, `compiler-preview.test.ts`, `compiler-limits.test.ts` | Unit with fake spawner, fake clock and in-memory fs | N/A (new) | module missing | 33 passed | argv/cwd/env, stop-on-error flag, unsafe main, ENOENT to engine-missing, phases once and split chunks, success, failed-with-errors, failed with stale PDF and old preview, offline, biblatex, outside reads, copy then rename, rev bump, last good preview, 180 s, 179.999 s, 600 s, late download, SIGKILL after 2 s, cancel, pre-aborted, first cause wins, 4 KB line cap, 2 MB cap, probe | one racy test rewritten to wait on events instead of timers |
| 15 stdout split | `tectonic/line-reader.test.ts`, `compiler.test.ts` | Unit | 102 passed | 5 failed | 107 passed | notes on stdout with errors on stderr, download seen on stdout extends the limit, merged order inside a stream, a failing stream | none needed |
| 15 fake | `fakes/fake-spawner.test.ts` | Unit | 9 passed | see deviations | 11 passed | later output, no child spawned | none needed |
| 15 real | `tectonic/real-tectonic.test.ts` (opt-in) | Real binary | N/A | exposed the stdout/stderr split | 7 passed | version, BibTeX with `\input`, errors with and without halting, undefined reference, `\write18`, outside read, cancel | none needed |
| 16.1 | `core/test/compile-coordinator.test.ts` | Unit with a controlled compiler | N/A (new) | 13 failed | 13 passed | first run at once, one follow-up replaced twice, order started/finished/started, restart after idle, cancel with queue, cancel when idle, cancel without result, request after cancel, phases forwarded, throwing compiler, no result, unsubscribe and failing listener, shutdown | `endedWith` helper |
| 16.2 | `server-local/test/routes/compile.test.ts` | Request tests, real store and state, controlled compiler | N/A (new route module) | 20 failed of 23 | 23 passed | 202 and ids, persisted toggle and main file, empty body, named main, overlapping requests, four unsafe mains, bad JSON, missing/ambiguous main, single top-level `.tex`, engine missing 503, no compiler 503, token and content type, cancel, status, pdf headers, no PDF 404, traversal queries, log, SSE events | none needed |
| 16 wiring | `server-local/test/server-compile.test.ts` | Request tests with a scripted spawner | existing server tests green | 3 failed of 4 | 4 passed | engine available with version, missing engine, cwd/argv/env without secrets, close cancels a running compile | none needed |

### Work Unit Evidence (batch F)

| Slice | Focused test | Runtime harness | Rollback boundary |
|---|---|---|---|
| s13 | `npx vitest run packages/adapters-local/test/tectonic packages/core`: all passed | N/A: pure parsers over recorded output | revert `caztor/s13-compile-parse` |
| s14 | `npx vitest run packages/adapters-local/test/tectonic`: 46 passed | N/A: pure parsers over recorded output | revert `caztor/s14-log-parser` |
| s15 | `npx vitest run packages/adapters-local/test/tectonic`: 107 passed, 7 opt-in skipped | `CAZTOR_REAL_BIN=1 npx vitest run packages/adapters-local/test/tectonic/real`: 7 passed with real tectonic 0.17.0 | revert `caztor/s15-tectonic-adapter` |
| s16 | `npx vitest run packages/core packages/api apps/server-local`: passed | real server plus `curl` (below) | revert `caztor/s16-compile-routes` |

Full runs at each branch tip: s13 825 passed + 4 skipped, s14 841 + 4, s15 904 + 11, s16 944 + 11; `npx tsc -b` exit 0 on all. `CAZTOR_REAL_BIN=1 npx vitest run packages/adapters-local` at s16: 386 passed, 0 skipped.

End-to-end (tip `caztor/s16-compile-routes`): `node apps/server-local/src/main.ts <temp project>`, token read from the served page, `curl` against the API.

| Scenario | Observed |
|---|---|
| (a) `main.tex` with BibTeX and one `\input`, toggle off | status `success`, no diagnostics; preview route 200, `application/pdf`, `cache-control: no-store`, `x-content-type-options: nosniff`, bytes start with `%PDF` (sha256 prefix `b0a9c776`) |
| (b) `bad.tex` (two undefined control sequences), stop-on-first-error ON | status `failed`, `pdfRev` null, one error `bad.tex:4 Undefined control sequence` with detail `halted on potentially-recoverable error as specified`; preview still served and identical to (a) (`b0a9c776`) |
| (b) `bad.tex`, toggle OFF | status `failed-with-errors`, errors `bad.tex:4` and `bad.tex:6`, new preview promoted (`acd3f26b`, `%PDF`) |
| (c) `ref.tex` (undefined reference) | status `success`, warning `ref.tex:3 Reference \`nolabel' on page 1 undefined`, source `log`; `/api/compile/log` served the kept log |
| Cancel | `slow.tex` (spin loop) started, a second request queued (`queued: true`), `POST /api/compile/cancel` returned `{cancelled: true}`; status `cancelled`, nothing queued, no `tectonic` process left (checked with `pgrep -x`) |
| Events | the open `/api/events` stream received 5 `compile.started`, 11 `compile.phase`, 5 `compile.finished` and no `file_changed` for the build folder |
| Gates | preview without token 401; `?rev=../../../../etc/passwd` returned 200 with the preview only |
| Shutdown | server stopped by PID (`kill <pid>`), process gone, port 4317 free, no `tectonic` left |

### Deviations (batch F)

- **Streams (observed, contradicts the task statement)**: with tectonic 0.17.0 and stdout and stderr as separate pipes, the `note:` lines go to STDOUT and only `warning:`, `error:` and `caused by:` go to stderr (shell redirection of both into one file hides this). The opt-in real test exposed it. The adapter reads both streams as one line sequence (`mergedLines`); the design's "phases from stderr" is therefore "phases from either stream". Fixtures were recorded with both streams merged, which is how the parsers read them.
- **Argv**: the main file is passed as `./path` (the design allows `after --` or `./`), because `--` must come after all options and tectonic then rejects options placed after the input. Argv order is the design's: `-X compile ./main.tex --outdir .caztor/build/out --keep-logs --untrusted [-Z continue-on-errors]`.
- **Environment allowlist (final)**: `PATH HOME XDG_CACHE_HOME TECTONIC_CACHE_DIR TMPDIR HTTP_PROXY HTTPS_PROXY ALL_PROXY NO_PROXY http_proxy https_proxy all_proxy no_proxy`, plus `TECTONIC_UNTRUSTED_MODE=1` (forced). `LANG` and `LC_ALL` from the design were dropped: with `env -i PATH=...` alone tectonic compiled from the existing cache (it falls back to the passwd entry for the home), so neither `HOME` nor a locale is strictly needed; `HOME`, `XDG_CACHE_HOME` and `TECTONIC_CACHE_DIR` stay because they locate the cache on other machines. `TECTONIC_CACHE_DIR` was verified to be honored (an empty one forced a download attempt).
- **Output folder**: the adapter removes and recreates `.caztor/build/out` before every run (tectonic exits with "output directory does not exist" otherwise, and a PDF left by an earlier run must not count as this run's output).
- **Compile id**: `CompileRequest` is unchanged. The coordinator mints the id at request time (so `202 {compileId, queued}` is immediate for queued requests too) and re-tags the adapter's events; the adapter's own `started` id is ignored. A queued request that is replaced never emits anything.
- **Status of a failed run**: `failed` (halted, no PDF) keeps `logAvailable: true` when the engine wrote a log, so the log route serves the failed run's log.
- **Offline detection** matches the recorded text (`this bundle isn't cached, and we couldn't get it from the internet ... error sending request`, exit 101, a Rust panic on stderr) plus dns, refused, reset and timed-out texts, and falls back to any failure with no located error while `downloading` was seen.
- **biblatex**: the notice is a `warning` (not an error), so a project that uses biblatex with biber can still be `success`; `biblatex` with `backend=bibtex` raises nothing because BibTeX can run it.
- **Outside-project reads** are reported once per resolved absolute path, as a `warning` with `file: null` and the absolute path in the message, from the engine's absolute-path warning (dropped from the generic stderr warnings) and from `../` or absolute names the log shows opening. Absolute paths inside the root are ignored.
- **Overfull boxes**: tectonic prints them as `warning: file:line: Overfull \hbox ...` on stderr (file named without extension, for example `sections/body`); they are listed as located warnings, with the resolver adding `.tex`.
- **Compile route extras**: `POST /api/compile` accepts an empty body, `{}` or `{ "main": "..." }`; without one it uses the project's `mainFile`, then `main.tex`, then the only top-level `.tex` file (409 `no_main_file` otherwise). Stop-on-first-error always comes from the saved project setting. `503 engine_unavailable` was added to the error statuses. `GET /api/compile/pdf` ignores its query completely (the revision is only a cache key); `GET /api/compile/log` returns `text/plain`.
- **Server wiring** (slice 16): `startServer` takes an optional `spawner`; the engine environment is built from the server's `env` option; `close()` cancels a running compile and waits for the process group to end before closing the listener. The session route's `engine` probe spawns `tectonic --version` on each call (5 s limit).
- **Strict TDD slips, disclosed**: (1) the `FakeSpawner.pushStderr/pushStdout` test and implementation were written in one step, so no RED was observed for that fake helper (it is test support, and the compiler tests that use it were RED first); (2) the fixture scan RED was observed by planting a bad fixture, not by writing the test before the fixtures.
- Task 13.1 says to derive fixtures from `spike-raw/tectonic-*.log`; the stderr fixtures were recorded fresh with the real binary (the `.log` and `.blg` fixtures are fresh recordings of the same document types too), and all paths were replaced with `/work` or relative names. The offline fixture was recorded with a dead proxy and an empty cache.
- Not done / not verified: the `downloading` phase was observed from a real first-run recording (252 lines, trimmed in the fixture) but the 600 s extension was only tested with the fake clock; sandboxed compile is slice 31; preview rev is a clock-based number, so after a server restart the existing preview is served but the UI learns its revision only after the next compile.



## Batch G (fix slice s16b, slice 17 compile UI, slice 18 log panel): complete

Branch chain: `caztor/s16-compile-routes` > `caztor/s16b-dialog-watcher-fixes` > `caztor/s17-compile-ui` > `caztor/s18-log-panel`. One branch per slice, `size:exception` accepted.

### s16b (`caztor/s16b-dialog-watcher-fixes`): complete, real changed lines 669 (633 added, 36 removed)

1. Dialog Tab trap: `onBlur` ignores a blur whose related target is inside the panel and re-checks on the next animation frame instead of a microtask; jsdom test simulates the gap (blur, microtask, then focus); `e2e/dialog.mjs` fails on the old code (Tab stayed on Cancel) and passes now.
2. Focus after a confirmed delete: after closing, a short-lived `MutationObserver` (2 s, stops on the first focus move, click or key) moves focus to the pane when the browser dropped it on the body.
3. Watcher blind spot: `nodeDirectoryWatcher` now opens one non-recursive `fs.watch` per folder (added when a folder appears, closed when it goes; reserved top-level folders and links skipped). Reproduced first with an opt-in real fs test (failed on the recursive watch). Rescan: 30 s while the event watcher is open and healthy, 5 s while it is missing or failed (a failed watcher is reopened on the next backstop pass). Chosen because a rescan cost about 1.6 s per 5,000 files and the watcher now reports in-place writes reliably.
4. Watched root deleted and recreated: a scan that fails closes the watcher; the next backstop pass (5 s) reopens it on the new folder and reports files that appeared or vanished.
5. Added tests: keepMine/takeDisk when the disk re-read fails, keepMine after typing during the conflict, saveCopy with all 50 names taken, saveCopy outside a conflict, low-surrogate branch (mutation-checked) and a seeded round-trip property test. These cover existing code, so they passed on first run (no RED possible); the diff ones were checked by mutation.
6. One shared SSE stream: `subscribeEvents` opens one connection with the first subscriber and closes it with the last (RED: 2 of 4 new tests failed).

Verification at tip: `npx vitest run`: 962 passed, 13 skipped; `npx tsc -b`: exit 0; `CAZTOR_REAL_BIN=1 npx vitest run packages/adapters-local/test/node-infra.test.ts`: 23 passed.

### s17 (`caztor/s17-compile-ui`, base `caztor/s16b-dialog-watcher-fixes`, slices 17a and 17b merged): complete, real changed lines 2,872 (2,837 added, 35 removed), `size:exception`

Done: tasks 17a.1 and 17b.1.

- Server: `GET /api/compile/status` adds `pdfAvailable` (answers the "preview exists after a restart" note; the UI loads the preview without a compile).
- Web API client and fake: `startCompile`, `cancelCompile`, `getCompileStatus`, `readPdf(rev)` (bytes fetched with the token header), `readLog`; the fake has a hand-driven compile (`fake.compile.phase/finish`).
- `compile/`: pure `compileReducer` (events, status, queued, first-run phase labels), `CompileController`, `startAutoCompile` (1.5 s debounce after a successful save, `EditorSession.onSaved`), `CompileToolbar` (Compile becomes Cancel, status line, engine missing), `CompileOptions` (stop-on-first-error and auto-compile, saved through the settings route, undone on failure).
- `preview/`: pure `layout.ts` (page boxes, visible window, anchors page+fraction, zoom steps, fit width, canvas ratio), `prefs.ts` (per-project zoom and anchor in `localStorage`, validated), `preview-state.ts` (shown/wanted revision, out-of-date mark), `PdfViewer` (lazy canvases, off-screen draw then swap so a reload never blanks, scroll and zoom kept), `PdfPreview`, `PreviewPane`, and `engine-pdfjs.ts` (PDF.js behind the `PdfEngine` seam). The toolbar sits in the preview pane header (design D3 says "the toolbar's Compile button"; the pane header is where Overleaf puts it); the switches and zoom controls are rows inside the pane.
- Dependency: `pdfjs-dist` 6.4.299 pinned exactly (npm current stable). The worker is a Vite `?url` asset served same-origin (`pdf.worker.min` 1.26 MB, own file); the library is a lazy chunk (430 kB). PDF.js options: `useWasm: false` (WebAssembly would need `'wasm-unsafe-eval'`); scripting off (default). No CSP change. Not bundled: CMaps, standard font data, wasm decoders (jbig2, openjpeg, qcms), the text layer. LaTeX output embeds its fonts; a PDF that needs a CJK CMap, a non-embedded standard font or JPX/JBIG2 images may not render correctly (not tested). No text selection in the preview (no text layer).
- Deviation from the PDF.js 5 documentation: v6 removed `isEvalSupported`; no option is needed.

Verification at tip: `npx vitest run`: 1,085 passed, 13 skipped; `npx tsc -b`: exit 0. Real browser (`e2e/compile.mjs`, real server, real tectonic): all checks passed (see the end-of-batch section).

### s18 (`caztor/s18-log-panel`, base `caztor/s17-compile-ui`): complete, real changed lines 785 (775 added, 10 removed), `size:exception`

Done: task 18.1. `EditorSession.reveal` + `jump` in the snapshot, `CodeEditor` `reveal` prop (cursor to the start of the 1-based line, clamped, applied once per request id, editor focused), `LogPanel` (counts, errors red and warnings orange from tokens `--color-danger` and the new `--color-warning`, entries with file and line are buttons, entries without either are plain rows, detail text, raw log on request and re-read after the next compile, auto-opens on errors, folds), wired into `PreviewPane`; `App.openAt` opens the file (a buffer already open keeps its unsaved text), then moves the cursor. The log panel group has `role="group"` (not a region) so the pane count stays four. A diagnostic with a file but no line has no jump (spec: "no file or line"). The biblatex notice and the outside-project warning arrive as readable messages from the server and are shown as is.

Verification at tip: `npx vitest run`: 1,116 passed, 13 skipped; `npx tsc -b`: exit 0.

### TDD Cycle Evidence (batch G)

| Task | Test file | Layer | Safety net | RED | GREEN | Triangulate | Refactor |
|---|---|---|---|---|---|---|---|
| s16b-1 dialog Tab | `components/Dialog.test.tsx`, `e2e/dialog.mjs` | jsdom + real Chromium | 8/8 | 1 failed (jsdom gap simulation); real browser failed on the old code (Tab stayed on Cancel) | 10 passed; browser 7 PASS | blur-gap case, disabled-control refocus, focus escape | none |
| s16b-2 focus after delete | same | jsdom + real Chromium | 9/9 | 1 failed | 10 passed | trigger removed in the same batch and later | none |
| s16b-3 watcher | `adapters-local/test/node-infra.test.ts` (opt-in), `project-store-watch.test.ts` | real fs + unit | 21 passed | real: in-place write after rename not seen; unit: rescan interval tests failed | 23 passed, 379 passed | both files, nested folder, new folders, removed folders, reserved folder, healthy vs failed watcher intervals | none |
| s16b-4 root recreated | `project-store-watch.test.ts` | unit (fake watcher, memory and node fs) | 44 passed | failed | passed | files vanish and appear, watcher count and starts | none |
| s16b-5 missing tests | `session.resolve.test.ts`, `diff.test.ts` | unit | 114 | n/a: cover existing code (passed first; low-surrogate branch checked by mutation: 2 failed) | 114 passed | 50 names, no conflict, failing re-read then recovery, seeded round trip (2,000 cases) | none |
| s16b-6 one SSE stream | `api/events.test.ts` | unit | 7 passed | 2 failed of 4 | 9 passed | one connection, close with last, reopen, failing subscriber | none |
| s17 status hint | `server-local/test/routes/compile.test.ts` | request | 22 passed | 2 failed | 24 passed | with and without a preview | none |
| s17 client | `api/client.test.ts` | unit fake fetch | 10 passed | 5 failed | 15 passed | start, queued, 503, cancel, status, PDF bytes with token, log, 404 | `request` split into `send` |
| s17 compile state | `compile/compile-state.test.ts`, `controller.test.ts`, `auto-compile.test.ts` | unit | N/A (new) | module missing (run for auto-compile; the other two files were written with the module in one step) | 14 + 8 + 6 passed | events, queue, cancel, late answers, status, labels, debounce, off, engine missing, stop | none |
| s17 toolbar and switches | `CompileToolbar.test.tsx`, `CompileOptions.test.tsx` | jsdom | N/A (new) | modules missing | 6 + 5 passed | idle, running, first run, queued, outcomes, engine missing; defaults, persist, failure rollback | none |
| s17 preview logic | `preview/layout.test.ts`, `prefs.test.ts`, `preview-state.test.ts` | unit | N/A (new) | module missing (layout run; others in one step) | 18 + 16 + 13 passed | boxes, window, anchors, zoom, fit, ratio; validation; revision tracking | none |
| s17 viewer and pane | `PdfViewer.test.tsx`, `PdfPreview.test.tsx` | jsdom with a fake engine | N/A (new) | module missing | 11 + 10 passed (one expectation corrected: only two of three pages are inside the window) | lazy window, drop, anchors, no flicker, stale draw, zoom steps, persistence, failure states | none |
| s17 wiring | `app/App.test.tsx` | jsdom | 405 | 4 failed | 410 | button, cancel, preview after restart, engine missing, auto-compile on and off | App split into `App` and `Project` |
| s18 editor reveal | `CodeEditor.test.tsx`, `session.test.ts`, `EditorPane.test.tsx` | jsdom | 111 | 4 + 2 + 2 failed | 125 passed | line, new id, same id, clamps, other file | none |
| s18 log panel | `compile/LogPanel.test.tsx`, `app/App.test.tsx` | jsdom | 405 | module missing; 3 App tests failed | 19 + 3 passed | counts, singular, severity, detail, no-location entries, notices, jump, failed open, raw log, folding | role changed to `group` after an existing four-pane test failed |

### Work Unit Evidence (batch G)

| Slice | Focused test | Runtime harness | Rollback boundary |
|---|---|---|---|
| s16b | `npx vitest run`: 962 passed, 13 skipped | `node e2e/dialog.mjs` (real Chromium): 7 PASS; `CAZTOR_REAL_BIN=1` node-infra: 23 passed | revert `caztor/s16b-dialog-watcher-fixes` |
| s17 | `npx vitest run apps/web/src/compile apps/web/src/preview`: all passed; full: 1,085 passed | `node e2e/compile.mjs` (real server, real tectonic, real Chromium) | revert `caztor/s17-compile-ui` |
| s18 | `npx vitest run apps/web/src/compile`: all passed; full: 1,116 passed | same script, now with the log panel and both themes | revert `caztor/s18-log-panel` |

End of batch: `CAZTOR_REAL_BIN=1 npx vitest run packages/adapters-local`: 392 passed (21 files); `npm run build -w @caztor/web`: built (index 636 kB, PDF.js chunk 430 kB, worker 1.26 MB, still a size warning); `node e2e/dialog.mjs` and `node e2e/compile.mjs`: all PASS, no console errors or CSP violations. No server or tectonic process left, port 4317 free.

### Deviations and limits (batch G)

- Strict TDD slips, disclosed: for some new modules the test and implementation files were written in the same step (the missing-module RED was inferred, not executed): `controller`, `compile-state`, `prefs`, `preview-state`, `PdfViewer` modules. The s17 status route test pair was reverted to confirm RED afterwards (2 failed).
- Design D3 says "the toolbar's Compile button": placed in the preview pane header.
- The rescan period is now 30 s while the event watcher is open and healthy, 5 s otherwise.
- Not verified: very large PDFs (50 pages tested in jsdom only through the window logic; the real run had 8 pages), `/mnt/c` 9p watcher, high device pixel ratios, PDFs needing CMaps, standard fonts, JPX or JBIG2 images, a text layer (none exists), first-run download state in a real browser (observed only through tests), a real offline run.

## Batch H (slices 19 to 22): in progress

### s19 (`caztor/s19-snapshot-capture`, base `caztor/s18-log-panel`): complete, `size:exception`

Done: tasks 19.1, 19.2, 19.3 and the `e2e/compile.mjs` flakiness fix (first commit).

- `e2e/compile.mjs`: a page-side `MutationObserver` counts runs (a run is the button turning into Cancel) and the script waits for that durable count and for the resulting status, instead of polling for the transient button. Three consecutive runs: 29 PASS each, exit 0.
- Refactor (approval tests: the 379 existing adapter tests): `keyed-lock.ts` and `containment.ts` extracted from the project store; the store behaves as before.
- Project store: `userWrites` recorder (`user-writes.ts`, hashes before and after each change made through the store while a turn runs, folders expanded to files), `write(..., { mode })`, `remove(..., { expect })` (conditional on the content hash).
- Snapshot store (`snapshot-store.ts`, `snapshot-manifest.ts`): content-addressed blobs `.caztor/snapshots/blobs/<hex>`, `turns/<id>.json` manifests (validated on read), capture with size+mtime hash reuse (not trusted within 2 s of the previous capture), limits (5 MB file, 200 MB new content, 5,000 files; injected for tests), diff with user attribution, `undoable()`, `prune()` with blob collection.

### s20 (`caztor/s20-snapshot-restore`, base `caztor/s19-snapshot-capture`): complete, `size:exception`

Done: tasks 20.1, 20.2. `restore(turnId, mode)` in `snapshot-store.ts`: LIFO over turns that are `applied` and not known to be empty (`not_latest`, `already_undone`, `discarded`; a tampered manifest counts as discarded); preflight against the recorded after-state (hash and mode, or size+time+mode for a file too large to hash) with the three choices (`strict` writes nothing and returns `conflict`; `skip_conflicts`; `force`); a file both the user and the agent changed (`mixed`) is always a conflict; blob copies are verified by hash before any write; a safety snapshot goes to `.caztor/snapshots/safety/<turnId>.json` (not on the stack, kept by `prune`) before the first write; writes go through the project store (hash-checked, per-path lock, mode set), created files are removed with a hash check and the folders the turn added are removed with them. `RestoreResult` got a `failed` variant and `diff` takes `userWrites` (see deviations).

### s21 (`caztor/s21-agent-files`, base `caztor/s20-snapshot-restore`): complete

Done: task 21.1. `agents/{claude,opencode,codex}.md` (7.1 to 7.5 KB each, plain ASCII), `agents/agents.test.ts` (38 tests, picked up by the existing `agents/**/*.test.ts` include) and `agents/tsconfig.json` (typechecks the test). Each file is `[frontmatter] + title + "## Provider characteristics" + "## Role ..."`; everything from `## Role` to the end is byte-identical across the three files (tested), so the shared section is edited in three places and the test catches drift. Frontmatter: claude `name`, `description`, `tools: Read, Edit, Write, Glob, Grep`; opencode `description`, `mode: primary`, `permission` with the four observed keys; codex none. The extra opencode permission keys (D5, marked [V]) are left for slice 29.3.

### s22 (`caztor/s22-provisioner`, base `caztor/s21-agent-files`): complete, `size:exception`

Done: tasks 22.1, 22.2. `provisioner.ts` (`ensure`, `remove`), `agent-definition.ts`, `agents-dir.ts` (`defaultAgentsDir()` from `import.meta.url`, independent of the working directory). Native files carry no marker; ownership by hash in `state.json`; a definition that is a link, or a `.claude`/`.opencode`/`agents` folder that is a link (even inside the project), is refused; a user-modified or unrecorded file is `skipped_user_modified` until `ensure(provider, { replace: true })`; a file equal to the shipped one is re-adopted. `AGENTS.md`: marked block, bytes outside preserved, visible file written through the store with the hash read (a user save in between is not lost), `createdByCaztor` flips to false when the user adds text. Fixes found on the way: `state.json` sanitizing dropped the native record paths (reserved folders), now allowed by name (`isAgentTarget` in core). Wiring: store rejects file operations on a Caztor-created `AGENTS.md` (`hidden`), the snapshot skips it, `server.ts` passes the state flag to the store (tree, API, watcher).

### TDD Cycle Evidence (batch H)

| Task | Test file | Layer | Safety net | RED | GREEN | Triangulate | Refactor |
|---|---|---|---|---|---|---|---|
| e2e fix | `e2e/compile.mjs` | real Chromium | n/a | n/a (flaky; verified by 3 runs) | 3 x 29 PASS | 3 runs | none |
| refactor lock/containment | existing adapter tests | unit | 379 | n/a (approval tests) | 379 | n/a | extracted |
| user writes, mode, conditional remove | `user-writes.test.ts`, `project-store-user-writes.test.ts` | unit, memory + real fs | 379 | module missing; 12 failed | 396 passed | save/create/delete/folders/any/stale | none |
| 19.1 capture | `snapshot/capture.test.ts` | unit, memory + real fs | N/A | module missing (run) | 34 passed | reuse, racy (mutation checked), exclusions, failures, ids, link, concurrency | none |
| 19.2 limits | `snapshot/limits.test.ts` | same | N/A | SLIP: limit code was written with 19.1; RED shown by mutation (6 failed with limits disabled) | 12 passed | size, count, bytes, new-only bytes | none |
| 19.3 diff, prune, undoable | `snapshot/diff.test.ts`, `prune.test.ts` | same | 46 | 36 failed (methods missing) | 84 passed | mutation checked | none |
| manifest parsing | `snapshot/manifest.test.ts` | unit | n/a | SLIP: tests written after the parser; passed first run | 27 passed | tamper cases | none |
| 20.1 LIFO | `snapshot/restore-order.test.ts` | same | 84 | 12 failed (restore missing) | 12 passed | LIFO, twice, discarded, empty, concurrent | none |
| 20.2 conflicts, safety | `snapshot/restore.test.ts` | same | 12 | 34 failed | 179 passed; 4 mutations caught | strict/skip/force, mixed, race, tamper, links | none |
| 21.1 agent files | `agents/agents.test.ts` | unit | N/A | file missing (run) | 38 passed | | none |
| state paths | `state-store.test.ts` | unit | 30 | 4 failed | 34 passed | | none |
| 22.1 native | `provisioner/native.test.ts` | unit, memory + real fs | N/A | module missing (run) | 40 passed | | none |
| `defaultAgentsDir` | `provisioner/agents-dir.test.ts` | unit | n/a | SLIP: test after code | 2 passed | cwd independence | none |
| 22.2 block | `provisioner/agents-md.test.ts` | unit | 40 | 30 failed | 76 passed | | redundant agent variable removed |
| removal | `provisioner/remove.test.ts` | unit | 76 | 24 failed | 100 passed | | none |
| AGENTS.md hidden | `project-store-agents-md.test.ts`, `snapshot/capture.test.ts`, `server-agents-md.test.ts` | unit, server | 685 | 2 + 2 + 1 failed | all passed | | none |

### Work Unit Evidence (batch H)

| Slice | Focused test | Runtime harness | Rollback boundary |
|---|---|---|---|
| s19 | `npx vitest run packages/adapters-local/test/snapshot`: 84 passed at tip | real-fs exercise (below) | revert `caztor/s19-snapshot-capture` |
| s20 | same, 179 passed (memory and real fs) | same | revert `caztor/s20-snapshot-restore` |
| s21 | `npx vitest run agents`: 38 passed | n/a (text files) | revert `caztor/s21-agent-files` |
| s22 | `npx vitest run packages/adapters-local/test/provisioner`: 100 passed | same | revert `caztor/s22-provisioner` |

Real-fs exercise (throwaway script, not committed): provision claude, capture, modify/create/delete/chmod, list 4 files, undo, tree (hash:mode) identical; then a user edit after the turn with the three choices (cancel writes nothing and names `a.tex`; keep edits restores the rest; overwrite restores everything); safety snapshot present. All PASS.

### Deviations (batch H)

- `SnapshotPort.diff(turnId, userWrites)` takes `ReadonlyMap<RelPath, UserWrite>` (hash before first and after last user change), not `ReadonlySet`: a set cannot tell "user only" from "both" (design says mixed is flagged). `RestoreResult` gained `{ status: "failed", message }` (safety snapshot failure). `ProjectStore.write` takes `{ mode }`, `remove` takes `{ expect }`.
- `partial` in `capture` means "some file is unprotected" (oversize files included).
- A turn with an empty change list is skipped on the undo stack; `prune(20)` must be called by the turn service after `capture` (slice 23); the safety snapshot is not on the stack and is not pruned.
- Safety snapshots obey the same limits, so a file over 5 MB overwritten by a forced undo is not protected.
- Removing a block from a file without a final newline leaves one added newline. Reuse by size+mtime is not trusted within 2 s of the capture.
- Opencode permission keys beyond the four observed are left for 29.3. Shared agent text is kept equal by test, not generated.
- The provisioner is not wired into the server yet (slice 23/24); only the `AGENTS.md` flag is.
- Strict TDD slips: see the table (limits code ahead of tests; manifest and `defaultAgentsDir` tests after the code).


## Batch I (fix slice 22b, slices 23 and 24): in progress

### s22b (`caztor/s22b-compile-hardening`, base `caztor/s22-provisioner`): code complete, `size:exception`

Seven fix commits, each test-first (RED observed by running before the implementation: watch replaced folder, node-infra root replaced and sub-folder errors, log bounds, available() reasons, session reason, App reason, biber, diagnostics, coordinator queue events, reducer, log-text). Items: (1) `FsStats.id` and `WatchHost.rootId`: the backstop reopens the watcher when the folder identity changed; the Node watcher reports an error when the root is replaced or a sub-folder watch fails or cannot be opened (ENOENT ignored); (2) `FileSystem.readRange`, `tectonic/log-bounds.ts` (parse the whole log up to 8 MB else the last 4 MB with a warning; copy and serve head 256 KiB + marker + tail 768 KiB), UI `log-text.ts` shows at most 200,000 characters; (3) `explainBiberFailure`; (4) `reason` on the engine probe, `/api/session` and `PreviewPane`; (5) `queued` / `dequeued` coordinator events published as `compile.queued` / `compile.dequeued`; (6) cascade, prefix and paragraph-line rules in `diagnostics.ts`. Verification: `npx vitest run` 1497 passed, 14 skipped; `npx tsc -b` 0; `node e2e/compile.mjs` ALL CHECKS PASSED (real server, tectonic, Chromium).
Deviations: with only the tail of a huge log parsed, warnings lose their file (open-file stack) and read "... on input line N"; an unrecognised `--version` output now makes the engine unavailable (was available without version).

### s24 (`caztor/s24-chat-routes`, base `caztor/s23-turn-service`; 24a and 24b merged by user decision): complete, `size:exception`

Done: tasks 24a.1 and 24b.1. Commits: chat history adapter (`chat-history.ts`, `.caztor/chat/<provider>.jsonl`, 200 turns / 1 MiB, damaged lines skipped, long texts shortened), `parseModel` in core (regex `^[A-Za-z0-9._:/-]+$`, no leading dash, 200 chars, empty clears), provider routes (`GET /api/providers`, `POST /api/providers/recheck`, `PUT /api/providers/selected`, `PUT /api/providers/:id/model`; detection cached until a re-check; providers without an adapter are listed unavailable), chat routes (`POST /api/chat/turns` answers with the turn's SSE stream and `x-caztor-turn-id`; `GET /api/chat/turns/current` and `/:id/events` resume with `Last-Event-ID` or `?after=`; `/:id/stop`; `/:id/undo` with strict, skip_conflicts, force and 409 bodies; `/definition/replace`; `/history`; `/sessions/reset`), server wiring (`apps/server-local/src/agents.ts` `createAgentServices`; `startServer` takes `runners` and `agentsDir`; the project store gets the user-write log; close stops a running turn). Test support: `apps/server-local/test/support/fake-runner.ts` (scripted events, really writes files), `routes/chat-support.ts`.

| Task | Test file | Layer | Safety net | RED | GREEN | Triangulate | Refactor |
|---|---|---|---|---|---|---|---|
| history adapter | `adapters-local/test/chat-history.test.ts` | unit, memory + real fs | N/A | module missing (run) | 16 passed | order, clear, limits, size, shortening, damaged lines, concurrency | none |
| model validation | `core/test/model.test.ts` | unit | N/A | 19 failed (not exported yet; SLIP: module written in the same step as the test) | 19 passed | accept, dash, characters, trim/clear, type, length | none |
| 24a.1 providers | `server-local/test/routes/providers.test.ts` | request, real stores | N/A | support module missing (run) | 24 passed | token gate x4, list, reasons, cache, recheck, unwired, throwing detect, select, model | none |
| 24b.1 chat | `server-local/test/routes/chat.test.ts` | request, real stores, fake runner | N/A | routes missing (run: failed/hung) | 47 passed after fixing two test-helper bugs | gate x8, stream, order, refusals, busy, snapshot_failed, errors, user edits, stop, drop and resume, undo modes, note, sessions, definition, history | none |
| wiring | `server-local/test/server-chat.test.ts` | server | 228 | SLIP: `server.ts` wired before the test; test passed first run | 2 passed | event stream, shutdown | none |

Work Unit Evidence (s24): focused `npx vitest run apps/server-local packages/api`; runtime harness: throwaway script composing the real server over TCP with the fake runner (13 checks PASS, see batch summary); rollback: revert `caztor/s24-chat-routes`.

### Deviations (batch I)

- Design D10 lists `POST /api/chat/turns/:id/stop` and `/undo` only; added `GET /api/chat/turns/current`, `GET /api/chat/turns/:id/events` (resubscribe), `POST /api/chat/definition/replace`. `ChatHistoryPort` and `TurnService` are new core contracts; the notice event gained an optional `action`.
- Provisioning outcome `skipped_user_modified` is reported as a notice with `action: "replace_definition"`.
- The revert note lives in memory only (lost on a restart). The transcript stores compacted events per turn, not the raw stream.
- No real provider adapter yet, so by default every provider is listed unavailable; real adapters arrive in slices 25 to 30.
- The `turn_started` event is not sent when the snapshot fails (the stream is `error`, `done`).


## Batch J (fix slice s24b, slices 25 and 26): complete

### s24b (`caztor/s24b-snapshot-agent-fixes`, base `caztor/s24-chat-routes`): code complete, `size:exception` (about 1,940 changed lines)

Ten commits, each test-first (RED observed by running before the implementation unless noted). Batch H verifier items: (1) undo never writes or removes through a link (a file, or a folder above it, that is a link is skipped and reported); (2) safety snapshots keep the newest 5 and blob collection includes them and drops `*.tmp`; (3) names the disk cannot open (replacement character, lstat ENOENT) are skipped by `store.list()` and the snapshot walk and reported as not protected; (4) the reuse key is size, mtime, ctime and object id, and the hash is not trusted within 2 s of the capture for either time; (5) empty folders: `dirsAfter` is recorded by the diff, undo recreates removed folders and removes added empty ones, and a folder-only turn is on the undo stack; (6) `AGENTS.md`: a block between the markers is replaced only when its body hash is the recorded one (or replace is asked), removal is byte-exact (a file without final newline gets a block without final newline), and the file is hidden only while it holds exactly the recorded block (`agents-md.ts`, `createAgentsMdVisibility`); (7) restored modes masked to 0o777, duplicate change paths and duplicate folders reject the manifest, `diff`, `undoable`, `prune` return `Result` and `restore` returns `failed` when `.caztor/snapshots` is a link, the history route reports `undoProblem` and the undo route answers 409 `undo_failed`; (8) agent text: class and package rule now asks for request or confirmation and to propose first, the managed block and definition files are protected while the user's own `AGENTS.md` text may be edited on request, the Codex development note and non-actionable statements were dropped.
Batch I verifier items: (1) chat history refuses a link for `.caztor`, `.caztor/chat` or the file (load returns nothing, append is refused, the turn shows a warning notice); (2) the user-write recorder keeps running until the diff is done and the diff is repeated when a save landed meanwhile (RED shown against the old turn service at server level); (3) a runner that ignores stop is cut off after 5 s (`STOP_GRACE_MS`): notice, `done: cancelled`, `forceStop()` on the adapter; (4) runner events are validated (`validateAgentEvent`), invalid ones dropped with one warning notice; (5) the replay buffer is bounded by count and bytes with delta joining, and single events are truncated; (6) stored turns are capped at 1000 events and 256 KiB per line, the history read is capped at 1 MiB; (7) the watcher is reopened and the project scanned at once after a watcher error.
Slips: the history route (`undoProblem`) and `forceStop`/validation code were written in the same step as their tests for two items; the `done` cleanup regression (`iterator.return()`) was found by the full suite. Deviations: `SnapshotPort.diff/undoable/prune` now return `Result`; `ChatHistoryPort` unchanged; invalid runner events become a notice, not an error.
Verification at the tip: `npx vitest run` 1793 passed, 14 skipped; `npx tsc -b` 0.

### s25 (`caztor/s25-claude-mapper`, base `caztor/s24b-snapshot-agent-fixes`): complete, `size:exception`

`providers/claude/mapper.ts` (`createClaudeMapper`: `feed(line)` returns events, the `system/init` facts and a `fatal` flag; `finish()` closes a stream that ended without a result), sanitized fixtures in `test/providers/claude/fixtures/` (generated from the raw capture: paths, ids, signatures, hooks, rate-limit data and MCP names replaced; a test fails on `/home/`, `claude-1000`, `andres`, `codegraph`, `context7`, `engram`). Variants: auth error, rate limit, permission denial, isolation violation, cancelled, resume. Thinking and signatures are never emitted; unknown types are ignored; lines over 1 MB are dropped; 20 unparseable lines in a row end the turn with `malformed_output`; tool inputs are collected up to 256 KiB per call; paths outside the project give no hint.
RED: module missing (run), 52 tests green on the first implementation run (the tests were written against the fixtures first). Verification: `npx vitest run` 1845 passed; `npx tsc -b` 0.

### s26 (`caztor/s26-claude-runner`, base s25): complete, `size:exception`

`providers/claude/runner.ts`, `providers/resolve-binary.ts`, `providers/lines.ts`; wired in `apps/server-local/src/server.ts` (default `runners` is the Claude runner; opencode and codex stay unavailable). Tier I1 argv (verified): `-p --output-format stream-json --verbose --include-partial-messages --permission-mode acceptEdits --setting-sources "" --strict-mcp-config --disable-slash-commands --tools Read,Edit,Write,Glob,Grep --agents <json> --agent caztor [--model m] [--resume id]`; prompt on stdin; `--bare` and `--restricted` are not used. Environment: PATH, HOME, locale, TMPDIR, proxy and certificate variables, `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL`, `CLAUDE_CODE_OAUTH_TOKEN`, `CLAUDE_CONFIG_DIR`, plus `NO_COLOR=1` and `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1` (the last is documented but not verified). Isolation is asserted on `system/init`: a tool outside the five or any MCP server (I1, I2) aborts with `isolation_failed`. Stop: SIGINT, SIGTERM after 3 s, SIGKILL 2 s later; `forceStop()` is SIGKILL of the group. Detection: `claude --version`, 5 s limit, warning below 2.1.296.
Real CLI (3 calls, all on a temporary project): init showed tools exactly Read, Edit, Write, Glob, Grep, `mcp_servers` `[]`, `slash_commands` `[]`, `skills` `[]`, agents only caztor and built-ins, plugins only built-ins, 0 hook lines; the first request used 6,096 context tokens (25k without isolation) and the model answered "No" to a question about the global CLAUDE.md; the edit landed; resume by session id kept the same session and its edit landed. Costs: turn 1 USD 0.0319, resume turn about USD 0.0038, repeat of turn 1 USD 0.0095 (default model sonnet-5-5).
Deviations: the design lists the `ANTHROPIC_`/`CLAUDE_` prefixes; they would pass the variables of a parent Claude Code session (seen in the first real run), so explicit names are passed. The tasks say a connected MCP server gives a notice; the user's requirement and the runner abort the turn instead (tier I3 only warns). Tier I2 blocks with `isolation_failed` and a message while project Claude config exists and `projectClaudeConfigConfirmed` is false; the confirmation UI is not built yet.


## Batch K (slices 27 and 28, plus verifier items): complete, `size:exception`

Chain: `caztor/s26-claude-runner` > `caztor/s27-chat-core` > `caztor/s28-chat-header-results` (28a and 28b merged) > `caztor/s28b-recorder-race`. Local branches only.

### s27 (`caztor/s27-chat-core`, base s26): tasks 27.1, 27.2

Core `chat-reducer.ts` (`chatReducer`, `turnFromRecord`; state has a timeline of turns and notes, `lastSeq` so a replay after a reconnect never duplicates text, whole `text` replaces deltas). Web `apps/web/src/chat/`: own Markdown reader (`markdown.ts` produces plain data, no HTML, links only http/https/mailto, images shown as text, no library added), `Markdown`, `MessageList` (log region, polite, `aria-busy` while streaming, follows output only while the reader is at the end), `ToolActivityCard`, `Composer` (Enter sends, Shift+Enter new line, Send disabled and Stop while busy, Stop returns focus), `ChatController` (external store; send, stop, resubscribe with `Last-Event-ID` and backoff, history, refreshes the undoable turn), `ChatPanel`; API client `streamTurn` (SSE over `fetch`, `onOpen`), `listProviders`, `chatHistory`, `stopTurn`; fake API chat section; App wiring (chat is its own pane, editor stays editable).

### s28 (`caztor/s28-chat-header-results`, base s27): tasks 28a.1, 28a.2, 28b.1

Logos: `claude.svg`, `opencode-logo-light.svg`, `opencode-logo-dark.svg` in `apps/web/src/assets/providers/`, byte for byte from the vendors (see `NOTICE.md`: source URL, retrieval date 2026-10-25, SHA-256, terms). Codex: no official logo could be obtained (openai/codex repo has none, developers.openai.com only the site logo, openai.com/brand is behind a bot challenge); nothing was drawn, the chat shows "Codex" as text. `ProviderLogo` (picture with a dark variant, text only when missing or on load error), `ProviderSelect` (radio group of logos, arrows, unavailable ones selectable with their reason), `ModelSelect` (list or text box, server's rejection shown), `ProviderUnavailable` with Check again, `ProviderHeader`, New chat with confirmation, auto-choice of the first installed provider (claude first) when the project has none, `TurnSummary` (changed files open in the editor, "No files changed", Undo only on the undoable turn, Undone, mixed and not-covered flags), `UndoConflictDialog` (Cancel, undo the rest and keep my edits, overwrite), `ErrorCard` (plain title, action, collapsed detail), `NoticeBanner` (Replace definition with confirmation), "Stopped" mark. Verifier items A1 (a non-empty `skipped` list is a partial undo: warning that names the files and why, never shown as success, not marked Undone) and A2 (tools without an end are closed as `interrupted` when `done` arrives, when the connection is lost, and for stored turns). `e2e/chat.mjs` and `e2e/chat-server.ts` (scripted providers; `CAZTOR_E2E_REAL=1` makes the two real-Claude steps).

### s28b-recorder-race (`caztor/s28b-recorder-race`, base s28): items 3 to 6

3. `UserWriteRecorder.inflight()`; `UserWriteLog.end()` is async and waits for saves, renames and removals in flight; the store hashes the bytes before the rename and registers the write before it; `UserWriteRecording.end()` in core is async. Tests: store-level (rename held between rename and record, end must wait, memory and node fs) and server-level (real HTTP routes, held rename, file is `mixed`, strict undo answers 409, skip_conflicts keeps the user's save). 4. `SnapshotPort.notCovered()`, `files_changed.notCovered`, shown in `TurnSummary`. 5. `mapper.oversize()` and `splitter.dropped()`: one warning per turn. 6. State error "The .caztor folder is a link, ..."; the turn error is "Caztor could not prepare the project for the assistant: ..."; history refusals name `.caztor`, `.caztor/chat`, `.caztor/chat/<provider>.jsonl`.

### TDD cycle evidence (batch K)

| Unit | Test file | RED | GREEN | Notes |
|---|---|---|---|---|
| chatReducer | `core/test/chat-reducer.test.ts` | 24 failed (module missing, run) | 23 passed (one test dropped with the unneeded `replay_begin`) | tools-left-open tests added in s28, RED 5 failed |
| Markdown | `web/src/chat/markdown.test.tsx` | no tests (module missing, run) | 10 passed | |
| API client chat | `web/src/api/chat-client.test.ts` | SLIP: client code written before its test | 6 passed; later additions RED first (onOpen, provider calls, undo) | |
| ChatController | `chat/controller.test.ts` | module missing (run); later groups RED (6, 7, 2 failed) | 25 passed | |
| components | ToolActivityCard, Composer, MessageList, ChatPanel, ProviderLogo/Select/Header, ModelSelect, ProviderUnavailable, TurnSummary, UndoConflictDialog, ErrorCard, NoticeBanner tests | modules missing (run) | all passed; one fix for a name polluted by a hidden note | |
| recorder race | store-level and `server-local/test/routes/chat.test.ts` | store: 4 failed; server: 3 failed with the old code | passed | |
| notCovered, oversize, state messages | hardening, turn-service, mapper, runner, state-store, chat-history tests | 3, 3, 7 failed | passed | |

Slips: the API client code was written before its test (test added immediately, passed); the first commit of 28a moved a Node-only test after `tsc` failed (amended); one commit message ("test(e2e)") also carries the small auto-choice change in `controller.ts` because it was found by the browser check; two commits were made with a `tsc` error in a test file and amended at once.

### Verification and deviations

`npx vitest run` 2076 passed, 15 skipped (one unrelated timing test, `project-store-watch` "finds changes that no event announced", failed once under load and passed on re-run); `npx tsc -b` 0; `npm run build -w @caztor/web` ok; `e2e/dialog.mjs`, `e2e/compile.mjs`, `e2e/chat.mjs` all pass. Real Claude Code: 1 turn (edit, USD 0.0080018) and an undo (no model call).
Deviations: logos are in `NOTICE.md` at the repository root (user request) and not under `assets/providers/` (design); a running turn found after a reload has no user message (the server does not expose the prompt of a running turn); a provider is chosen automatically when the project has none; default pane widths are unchanged (chat 20 %).


## Batch L (slices 29 and 30, plus two UI fixes): complete, `size:exception`

Chain: `caztor/s28b-recorder-race` > `caztor/s29-opencode-adapter` > `caztor/s30-codex-adapter`. Local branches only.

### s29 (`caztor/s29-opencode-adapter`, base s28b): tasks 29.1 to 29.4 done, code complete

Commits: UI fixes (status dot no longer over the label; an unchosen provider is shown as selected and saved only when the user sends or chooses), `opencode/mapper.ts` with sanitized fixtures, shared process lifecycle `providers/drive.ts` (the Claude runner now uses it), `opencode/runner.ts`, `note` and `supportsModel` on `ProviderStatus` through the API and the chat header, server wiring, opt-in real test, e2e real opencode mode.

- argv: `opencode run --format json --agent caztor --pure -m <provider/model> --dir <root> [-s <ses_id>]`, prompt on stdin, `shell: false`, cwd the project root. The model is required (`model_required`, no spawn) and must be `provider/model`; an option-like value is refused.
- Isolation tier I1: `XDG_CONFIG_HOME=<root>/.caztor/opencode-xdg` (verified: `opencode agent list` and `opencode models` show no user agents, plugins, MCP or custom providers; the login in `~/.local/share/opencode/auth.json` stays usable), `--pure`, `OPENCODE_DISABLE_CLAUDE_CODE`, `OPENCODE_DISABLE_EXTERNAL_SKILLS`, `OPENCODE_DISABLE_AUTOUPDATE`, `NO_COLOR`. Environment allowlist with explicit names only (no `OPENCODE_CONFIG*`).
- Tool check on every finished call: outside the allowed set (read, edit, write, apply_patch, multiedit, patch, glob, grep, list, todowrite, todoread, invalid) aborts with `isolation_failed`; a refused built-in (for example `bash` with status error) shows as a failed tool and the turn goes on; an unknown name (a plugin or MCP tool) aborts at any status.
- Detection: `opencode --version` (5 s), `opencode --pure models` with an empty config folder for the model list, and `opencode models` with the user's own config to find providers isolation hides; those are reported as `note` ("... not available here: ollama"). The list is kept 30 s because every turn detects first.
- Error mapping from the real captures: free tier 403 and a rejected model 400 become `model_unavailable` with "choose another model"; 401 and `ProviderAuthError` become `auth`; 429 `rate_limited`.

Real opencode (2 `opencode run` calls in total, temporary project, through `e2e/chat.mjs` with the real server and browser): call 1, `-m openai/gpt-5.5`: rejected by the provider ("The 'gpt-5.5' model is not supported when using Codex with a ChatGPT account"), 0 tokens, shown in the chat as "The model is not available" with the choose-another-model text. The opencode database shows gpt-5.5 worked on 2026-10-12 and the same message appears for it now, so the account gating changed; call 2, `-m openai/gpt-5.6-terra` (the user's most recent ChatGPT model, a deviation from the requested model): one edit turn, edit landed, changed files listed, undo restored the original, 13,591 input and 150 output tokens, cost 0 (ChatGPT subscription). The model answered that it has no engram tool and no bash tool. The continuation (`-s`) was not run for real (call budget); it is covered by the fake spawner and by a stub `opencode` run through the same e2e.

### TDD cycle evidence (batch L, s29)

| Unit | Test file | RED | GREEN | Notes |
|---|---|---|---|---|
| controller auto-select | `web/src/chat/controller.test.ts` | 3 failed | 31 passed | shown, not saved; saved on send or on an explicit pick; kept after model and re-check |
| opencode mapper | `adapters-local/test/providers/opencode/mapper.test.ts` | no tests (module missing, run) | 54 passed | fixture scan rejects home path, user name, `claude-1000`, `engram`, raw session ids |
| shared drive refactor | existing Claude runner tests | n/a (approval: 98 passed before and after) | 98 passed | |
| opencode runner | `.../opencode/runner.test.ts` | no tests (module missing, run) | 63 passed | 3 test-side slips fixed (scripts without exit or step) |
| provider note and no-model | `server-local/test/routes/providers.test.ts`, `ChatPanel.test.tsx` | 1 and 2 failed | passed | |
| server wiring | `server-local/test/server-opencode.test.ts` | 4 failed | 4 passed | |

Slips: the status-dot CSS fix has no unit test (visual; checked with screenshots); the route code for `note` and `supportsModel` was written right after its RED test.

Also on s29: the model listing gets 15 s (not 5 s) after a status line of the note went missing twice on a busy machine (a RED test first).

### s30 (`caztor/s30-codex-adapter`, base s29): tasks 30.1, 30.2 done, code complete

Commits: `codex/mapper.ts` with documentation-derived fixtures (`documented-*.jsonl` plus a README that says none is a capture), `codex/runner.ts` and server wiring, the OpenAI mark as the Codex logo with its `NOTICE.md` row, the opt-in real check, e2e checks.

- argv (from research C6.1-C6.5, unverified: no `codex` binary): `codex exec --json --sandbox workspace-write --skip-git-repo-check --ignore-user-config [resume <id>] -`, prompt on stdin, cwd the project root, no `-C`. `AGENTS.md` is the instruction source (the provisioner's block). Environment allowlist with explicit names (`CODEX_HOME`, `CODEX_API_KEY`, `OPENAI_API_KEY`, `OPENAI_BASE_URL`), never the `CODEX_` prefix.
- Model: the `-m` flag is not in the documentation the adapter was written from, so per the design's fallback no model is passed and `ProviderStatus.supportsModel: false` hides the model selector (the API and the chat carry the new optional field).
- Mapper: `type` or legacy `item_type`, `assistant_message` as a message, command executions, file changes, web searches and MCP calls as tools, reasoning and plans ignored, `turn.completed` usage, `turn.failed` and `error` events (an error followed by a completed turn stays a warning notice), 401 text becomes a sign-in error.
- Detection: `codex --version`; missing binary is "Codex is not installed: the codex command was not found on the PATH."; the chat shows it unavailable with that reason.
- Disclosure: a note in the provider header, always shown while Codex is selected (also when unavailable): "Codex can run commands on this computer inside its own sandbox, which limits where it can write. Caztor cannot turn this off."
- Logo (user decision of 2026-10-26): `apps/web/src/assets/providers/codex.svg` is `https://developers.openai.com/favicon.svg` byte for byte (the OpenAI blossom on a blue disc, one file for both color schemes; SHA-256 `8e1b976b...e58` in `NOTICE.md`, with the note that it is the OpenAI company mark used to identify Codex). The site header logo `/OpenAI_Developers.svg` is the black words "OpenAI Developers" (inverted by a style rule in dark mode, no separate dark file), so it was not used. The text fallback stays for a load failure.

### TDD cycle evidence (batch L, s30)

| Unit | Test file | RED | GREEN | Notes |
|---|---|---|---|---|
| codex mapper | `adapters-local/test/providers/codex/mapper.test.ts` | no tests (module missing, run) | 37 passed | one expectation order fixed in the test (notice after the text) |
| codex runner | `.../codex/runner.test.ts` | no tests (module missing, run) | 32 passed | |
| server wiring | `server-local/test/server-codex.test.ts` | 4 failed | 4 passed | |
| logo and NOTICE | `ProviderLogo.test.tsx`, `provider-logos-notice.test.ts` | 3 failed | passed | |
| listing timeout (s29) | `opencode/runner.test.ts` | 1 failed | passed | |

Slips: none in the order of test and code for s30. The e2e run found one race caused by the first UI fix (the log region appears after the shown provider is saved), fixed in the script by waiting for the region.

### Verification and deviations (batch L)

`npx vitest run` 2281 passed, 19 skipped (final run in the report); `npx tsc -b` 0; `CAZTOR_REAL_BIN=1 npx vitest run packages/adapters-local` passes; `npm run build -w @caztor/web` ok; `e2e/dialog.mjs`, `e2e/compile.mjs`, `e2e/chat.mjs` pass with no console errors or CSP violations.
Deviations: the design lists the `OPENCODE_`/`OPENAI_`/`CODEX_` prefixes for the environment; explicit names are used (a prefix would pass `OPENCODE_CONFIG*`, which isolation must keep out). The tasks ask for the model list from `opencode models` as optional: it is used, kept 30 s. The real continuation with `-s` was not run for real (2-call cap, call 1 rejected by the provider). The UI fix commit and the s29 refactor commit (`providers/drive.ts`, the Claude runner now uses it) are outside the literal task text.


## Batch M, slice 31 (`caztor/s31-sandbox-readme`, base s30): tasks 31.1 and 31.2 done, `size:exception`

- `packages/adapters-local/src/sandbox.ts`: `createSandbox` (probe = `ldd` of the engine, then `tectonic --version` inside `bwrap` with the real profile; a success is remembered), `buildSandboxedSpec` (argv array, `shell: false`: `--unshare-all --share-net --die-with-parent`, `/usr` and the system trees read-only, a few `/etc` files, the engine and its `ldd` libraries read-only, the project read-only with `.caztor/build` and the cache writable, private `/tmp`, nothing else of `$HOME`), `parseLddPaths`, `sandboxStartFailure` (lines starting `bwrap:`).
- Core `CompileRequest.sandboxed?`; the compile route sends the persisted `sandboxedCompile`; the compiler wraps the spec for such requests and reports a start failure ("The sandbox could not start. Turn off "Sandboxed compile" in the compile options ...") whether the wrapper cannot be built or bwrap fails after launch. Server wires the probe into `GET /api/session` (`sandbox`). Web: the checkbox "Sandboxed compile (experimental)" shows only when available (or when already on, so it can be turned off, with the reason).
- Finding: tectonic 0.17.0 keeps its cache in `~/.cache/tectonic` (lowercase; `Tectonic` was the older name). Binding only `Tectonic` made every sandboxed run regenerate the format. The cache folders are `TECTONIC_CACHE_DIR`, else `$XDG_CACHE_HOME` or `~/.cache` + `tectonic`, plus `Tectonic` when it exists.
- README.md written and verified (fresh clone: `npm install`, `npm run build -w @caztor/web`, `npm start -- <folder>` print the address, the page and `/api/session` answer).

### TDD cycle evidence (batch M, s31)

| Unit | Test file | RED | GREEN |
|---|---|---|---|
| sandbox profile, ldd, probe | `adapters-local/test/sandbox.test.ts` | module missing (run) | 15 passed |
| compiler sandbox integration | `adapters-local/test/tectonic/compiler-sandbox.test.ts` | 4 failed | 5 passed |
| server wiring | `server-local/test/server-sandbox.test.ts` | 3 failed | 3 passed |
| web option | `web/src/compile/CompileOptions.test.tsx` | 2 failed | 8 passed |
| real binaries (opt-in) | `adapters-local/test/tectonic/real-sandbox.test.ts` | written with the code | 6 passed (see below) |

Slips: the real-binary file was written after the sandbox code (it needs the code to run); its two first failures were test-side (the PDF id normalisation, the cache folder layout). Two existing expectations changed for the new field (`sandboxed: false` in `server-local/test/routes/compile.test.ts`, the port signature in `core/test/ports.test.ts`).

Real checks (`CAZTOR_REAL_BIN=1`): BibTeX multi-file project sandboxed = unsandboxed PDF (dates and ids stripped); `\input` of an absolute home path and of `../neighbour` succeed unsandboxed and fail sandboxed with no PDF; first run with an empty `TECTONIC_CACHE_DIR` downloads inside the sandbox and succeeds; cancel and the (scaled) time limit leave no process mentioning the project (checked through `/proc`).

## Batch M, addendum (`caztor/s31b-project-cli-config`, base s31): fixes from the independent verification of batch L, `size:exception`

1. **Project-borne code (CRITICAL)**: both runners now refuse a turn with `isolation_failed` (text ends with the action "Trust this project's CLI configuration") while the project carries configuration that runs programs and the user has not trusted the exact files. `scanClaudeProjectConfig` (`.mcp.json`, `.claude/settings.json`, `.claude/settings.local.json`; every tier, because `claude --help` documents `--setting-sources` and `--strict-mcp-config` but only a model call would show their effect) and `scanOpencodeProjectConfig` (`opencode.json[c]` in the project and its parents up to the repository root, `.opencode/opencode.json[c]`, non-empty `.opencode/{plugins,plugin,tools,tool,commands,command}/`; a config file with only display keys is not flagged; an unreadable one is). Trust is stored per provider as a fingerprint (`ProjectState.projectCliConfigTrusted`, replaces `projectClaudeConfigConfirmed`) and stops counting when a file changes. API: `projectConfig {files, confirmed, fingerprint}` in `GET /api/providers`; `POST /api/providers/:id/project-config/trust {fingerprint}` (409 `project_config_changed` when the files changed since shown, 409 `no_project_config`). Chat: notice, "Review project configuration" button, composer closed, dialog with Cancel first and focused.
   - opencode `detect()`: `--version` and `--pure models` in a fresh `mkdtemp` folder (0700, new `FileSystem.mkdtemp`) used as cwd and as `XDG_CONFIG_HOME`, removed afterwards. The second, non-isolated `opencode models` call and its "hidden providers" note are gone.
   - Real, free checks with the planted project (marker files): plain `opencode models` in the project runs the plugin (control); `--pure models` runs neither plugin nor MCP; `opencode --pure debug agent caztor` runs neither; `opencode mcp list` runs both (not used by Caztor). Observed but not applied: `OPENCODE_DISABLE_PROJECT_CONFIG=1` stops project MCP and plugins, but it also hides the project agent file Caztor provisions, so it would need an inline agent.
2. **`.caztor/opencode-xdg`**: created by Caztor with mode 0700 before spawning; the turn is refused when it or `.caztor` is a symbolic link; `.caztor` and `.opencode` are already reserved roots (hidden from the tree, file API and watcher) and excluded from snapshots at the root. README notes the ~62 MB plugin package.
3. **Flaky test** `project-store-watch.test.ts`: the helper waited a fixed 15 ms for the baseline scan. It now awaits `store.rescan()`, which queues behind the baseline. With the pause set to 0 the old helper failed 13 tests, the new one passes.
4. README: providers, project configuration gate, disclosed limits updated.

### TDD cycle evidence (addendum)

| Unit | Test file | RED | GREEN |
|---|---|---|---|
| scan + JSONC | `adapters-local/test/providers/project-config.test.ts` | module missing (run) | 13 passed |
| `FileSystem.mkdtemp` | `node-infra.test.ts`, `fakes/memory-fs.test.ts` | 2 failed | passed |
| state field | `state-store.test.ts` | 2 failed | passed |
| claude gate | `providers/claude/runner.test.ts` | 5 failed | 44 passed |
| opencode gate, config home, detection | `providers/opencode/runner.test.ts` | 13 failed | 73 passed |
| API trust route | `server-local/test/routes/providers.test.ts` | 6 failed | 33 passed |
| web dialog | `web/src/chat/ChatPanel.test.tsx` | 4 failed | 27 passed |
| planted project, real opencode (opt-in) | `providers/opencode/real-config.test.ts` | written with the code | 4 passed |
| flaky watch test | `project-store-watch.test.ts` | 13 failed with `pause(0)` | 56 passed |

Slips: `server-opencode.test.ts` (the end-to-end trust test) was edited in the same step as the API fingerprint field, so its RED was not run on its own; the real-config test needs the code so it was written together with it. Existing expectations changed on purpose: opencode detection (one listing, no note), `server-opencode` (two spawns), compile route request now carries `sandboxed`.
Also in this batch: the real-sandbox PDF comparison was time-dependent (dates sit in compressed object streams); it now inflates streams, strips dates and ids, and has a negative control.
