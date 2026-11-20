# Procedure part 1: T0 to T7 (Antigravity adapter)

## 8. Procedure

Tasks are in order. Work on `feat/providers-auth-s5-antigravity` for T1 to T7, then `feat/providers-auth-s6-docs` from it.

### T0. Orient

```sh
cd /home/andres/CaozCompilator
pgrep -af '(^|/)agy( |$)'; pgrep -af 'server-local|chat-server|tectonic|chrom'
git status --short; git branch --show-current; git log --oneline -3
XDG_CONFIG_HOME=$(mktemp -d) npx vitest run 2>&1 | tail -5
npx tsc -b; echo "tsc exit=$?"
```

Expected: `6d1b430`, 2865 passed. Any other result: find out why first. Read `tasks.md`, the task 5.1 section of `apply-progress.md`, the design's Antigravity section and the two spec files. 

### T1. Repeat the free checks (no model call)

In a `mktemp -d` folder: `agy --version`, `agy --help`, `agy models`, `agy agents`, `agy changelog`. Record what changed since 1.4.7 in `apply-progress.md`, especially stdin, `--agent`, `AGY_ERROR`, tool restriction, and any new flag that isolates or relocates global configuration. A new isolation flag would change this design: tell the user. Exit: findings committed as docs.

### T2. Task 5.2, R1: real edit turn

**Budget for the whole change: exactly three real `agy -p` calls, already authorized. They use the user's Google subscription quota.** No trace of a call from the interrupted run was found, so treat all three as available and say so in `apply-progress.md`. Run each once, never in a loop or a retry, and never on a shell line that can run it twice. If a call fails because of argv form, do not spend another: record it, decide from the evidence, and stop per `02-decisions-and-rules.md` before any call beyond three.

1. `P=$(mktemp -d)`. Put `main.tex` containing `The cat sat on the mat.` in it, and copy `agents/antigravity.md` to `$P/.agents/agents/caztor.md`. Prefer the real provisioner, as it writes the exact target.
2. Record modification times under `~/.gemini` (names and times only).
3. Run with the user's real environment reduced to the runner's allowlist, recording stdout to a file outside the repository: prompt "In main.tex change the word cat to dog."
4. Record: argv, exit code, whether stdin worked, event names and fields, `init` contents, whether `--agent caztor` resolved, delta granularity, tool step payload, conversation id, usage fields, edited file, files changed outside `$P`.

Exit: findings in `apply-progress.md`, and every open question in section 7 either answered or named.

### T3. Task 5.3, R2: shell refusal

Fresh temporary project. Prompt: "Run the command ls and tell me the output." Record whether a shell tool is listed, attempted, refused, or executed, and exactly what is emitted. Plant a marker test only if safe (prompt asking for a harmless `touch` inside the temporary project is acceptable; nothing outside it). If `agy` actually ran a command despite `commandExecutionPolicy: off`, tell the user: the guard then limits damage only after the fact, and the disclosure must say so.

### T4. Task 5.4, R3: continuation

In R1's project, `--conversation <id>`, prompt "What word did you change?". Confirm the same id and that it remembers.

### T5. Sanitized fixtures

Under `packages/adapters-local/test/providers/antigravity/fixtures/`, derived from R1 and R2: paths to `<root>`, ids to fixed fakes, all account data removed; trim long payloads. Add hand-written fixtures for auth failure, disallowed tool, malformed line, and missing `result`, labelled synthetic in a `README.md`. A scan test must reject the home path, user name, the user's email, real conversation ids, and Claude-session paths, following `providers/opencode` fixture tests. Raw captures stay out of the repository.

### T6. Tasks 5.5 and 5.6: mapper and runner, test first

Write these failing tests, run them, then implement. Assert observable effects through the public interface.

**`test/providers/antigravity/mapper.test.ts`**

| Case | Expected |
|---|---|
| Real edit fixture | `session`, text, `tool_start`/`tool_end` pairs with kind and path, `done` completed; same final text however it was chunked |
| `checkpoint`, `user_input`, unknown event | Ignored, turn continues |
| Thinking or internal content, if present in the capture | Never emitted |
| `result` with error | One readable error, one `done` failed |
| Auth failure, `AGY_ERROR` line, exit code 3 | `auth` error with the login hint |
| 20 consecutive unparseable lines | `malformed_output`, consistent with the Claude mapper |
| Oversized line | Dropped with one notice per turn |
| Stream ends with no `result`, or a tool with no end | Failed, exactly one `done`, no dangling tool |
| Hostile conversation id in events | Not accepted as a session |

**`test/providers/antigravity/runner.test.ts`** (fake spawner and fake clock)

| Case | Expected |
|---|---|
| Argv | Exact array; no `--dangerously-skip-permissions`; `--model` only from `parseModel`; hostile model and id never reach argv; prompt beginning with `-` is not an option |
| Environment | Only the allowlist; a secret, `GEMINI_API_KEY`, `GOOGLE_API_KEY`, `CLAUDE_CODE_SESSION_ID` in the parent do not reach the child |
| API mode | `mode_unsupported`, nothing spawned |
| Guard at start | `init` with a shell tool aborts, process terminated, no file change from later events |
| Guard mid-turn | Disallowed tool, MCP-like name, or a tool step with no name aborts |
| Allowed tools | Turn proceeds |
| Trust gate | Unconfirmed `.agents/hooks.json` refuses with no spawn; confirmed proceeds; only `caztor.md` is inert; changed file invalidates trust |
| Notice | Emitted on every turn |
| Stop | SIGINT, SIGTERM at 3 s, SIGKILL 2 s later; `cancelled`; no process left |
| Detection | Not installed reason; `id<TAB>name` parsed with the first line skipped; run in a temporary cwd never equal to the project; temporary folder removed; 30 s cache |
| Continuation | `--conversation` only for a stored, regex-valid id; change of definition or mode starts anew, per existing `chooseSession` |
| Redaction | Planted secret absent from all output channels |

**Web tests (`apps/web/src/chat/`)**: notice visible whenever Antigravity is active and present after reload and with no dismiss-forever control; absent for other providers; account-only (no API option); model selector uses the detected list; logo or text.

Add an opt-in real test gated by `CAZTOR_REAL_BIN=1` plus `CAZTOR_REAL_AGY=1`, as the other providers have. It must not run during this work unless it counts as one of the three calls.

Then, in `agents/antigravity.md`, reconcile the provider section with what R1 to R3 proved. The shared section must stay byte-identical across the four files (`agents/agents.test.ts`).

### T7. Task 5.7: wire and prove

Wire the runner (section 7). Test in `apps/server-local/test/server-antigravity.test.ts`, modelled on `server-opencode.test.ts`, with a scripted stub `agy` on PATH: listed available with version, full turn over HTTP, changed files, undo, trust gate through the routes. Commit.

