# Requirements and adapter design

## 6. Requirements still to satisfy

Authoritative text: `openspec/changes/caztor-providers-auth/specs/`. Requirements with open implementation:

| Id | Requirement (spec file) | Must hold |
|---|---|---|
| AP2 | Antigravity provider (`agent-providers`) | Selectable when installed and signed in; unavailable with a "not installed" reason otherwise, others unaffected; no login gives a refused or failed turn with a readable hint; text, tools, edits and completion normalized like other providers |
| AP3 | Antigravity partial isolation (`agent-providers`) | Only file read and edit tools requested; notice present on every turn |
| AP4 | Antigravity tool guard (`agent-providers`) | A tool outside the set, at start or mid-turn, aborts with a readable error and the process is terminated |
| AP5 | Provider detection (`agent-providers`) | Lists `opencode`, `claude`, `codex`, `antigravity`; API mode without a key shows not configured |
| AC4 | Partial-isolation notice (`agent-chat`) | Visible whenever Antigravity is active; cannot be dismissed permanently |
| AC5 | Provider header (`agent-chat`) | Logo, or name as text when unavailable; origin recorded in the notice file |

Notice text (design, fixed): "Antigravity runs with partial isolation: your global Antigravity settings, skills, agents and MCP servers in ~/.gemini/ may load, and Caztor cannot turn them off. Caztor allows only file reading and editing tools and stops the turn if another tool appears."

## 7. Design for the adapter

From `openspec/changes/caztor-providers-auth/design.md`, corrected by the free checks.

- **Argv:** `agy -p --output-format stream-json --mode accept-edits --agent caztor [--model M] [--conversation ID]`. Array form, `shell: false`, cwd the project root. Never `--dangerously-skip-permissions`.
- **Prompt delivery is unresolved.** The design says stdin; the changelog shows `-p "/usage"`, which suggests an argument. R1 settles it. If it must be an argument, use `-p -- <prompt>` or `--input-format stream-json` on stdin with `{"event":"user","message":{"content":"..."}}`, and test that a prompt beginning with `-` cannot become an option.
- **Environment:** the shared base plus `XDG_RUNTIME_DIR` and `DBUS_SESSION_BUS_ADDRESS` (keyring access); no `GEMINI_*` or `GOOGLE_*`. Follow the environment table in the design and the explicit-names pattern of the other runners; never pass prefixes.
- **API mode:** refused with `mode_unsupported`.
- **Tier name:** `P1`.
- **Mapper (documented, unverified):** `init` feeds the guard. `step_update`: `agent_response` ACTIVE to `text_delta`, DONE to `text`; `tool` ACTIVE to `tool_start` (`view_file` read; `list_dir`, `find_by_name`, `grep_search` search; `replace_file_content` edit; `write_to_file` write), DONE to `tool_end`; `user_input` and `checkpoint` ignored. `result` to `session` (regex-checked conversation id), usage, `done`. Result statuses documented: `SUCCESS|ERROR|CANCELED|INTERRUPTED|INVALID|WAITING|RUNNING`.
- **Errors:** a failed headless run reportedly exits 3 and prints an `AGY_ERROR` line (changelog). Key on that as well as on the result event. An auth-shaped failure maps to `auth` with the login hint: run `agy` and follow the sign-in prompts.
- **Guard:** allowed tools are `view_file`, `list_dir`, `find_by_name`, `grep_search`, `replace_file_content`, `write_to_file`. A listed `init.tools` entry outside the set aborts before acting. If `init` has no usable list, guard per step; a tool step with no recognizable name aborts (fail closed). Use `dropEventsOnViolation`.
- **Detection:** `agy --version`, then `agy models` (30 s cache), both in a `mkdtemp` cwd (mode 0700, removed afterwards), never the project. `agy models` prints a "Fetching available models..." line, then `id<TAB>Display name`; take the first column. Ids have no `provider/` prefix. Six were listed on 2026-10-12 to 2026-10-26: `gemini-3.8-flash-{high,medium,low}`, `claude-sonnet-4-6`, `claude-opus-4-6-thinking`, `gpt-oss-120b-medium`.
- **Trust gate:** `scanAntigravityProjectConfig` and `configRefusal` in `providers/project-config.ts`, with `projectConfigConfirmed` wired like the other runners. `antigravityDefinitionProblem` gives the `replace_definition` warning.
- **Stop:** `drive` escalation (SIGINT, SIGTERM at 3 s, SIGKILL 2 s later) and `forceStop` on the process group.
- **Reuse, do not re-implement:** `providers/drive.ts` (`drive`, `probe`, `failed`, `STOP_ESCALATION_MS`), `providers/lines.ts`, `providers/version.ts`, `providers/resolve-binary.ts`, `parseModel` in core. Copy the structure of `providers/opencode/{mapper,runner}.ts`, whose text arrives in whole parts, and `providers/claude/` for the `init` guard.
- **Wiring:** add `antigravity: createAntigravityRunner({...})` to the default `runners` in `apps/server-local/src/server.ts` (around line 119), with `projectConfigConfirmed` reading `projectCliConfigTrusted.antigravity`. Export it from `packages/adapters-local/src/index.ts`.

**Open question that can block the provider:** if `init.tools` always lists every built-in tool regardless of the definition, the guard as designed stops every turn. If R1 shows this, guard on tools actually used in step events, document the change in `design.md`, and report it to the user as a weakened guarantee. Also watch whether the definition's `tools` list and `commandExecutionPolicy: off` are honored at all, and whether `agy` hangs on a tool name it cannot map (the docs warn about this).
