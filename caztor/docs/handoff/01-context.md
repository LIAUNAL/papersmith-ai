# Context and current state

## 1. Read this first

**Remaining goal.** Finish change `caztor-providers-auth`: the Antigravity adapter, its real-CLI proof, docs, independent verification, archive, and delivery to `main`. Nothing else is in scope unless the user asks (section 12 is a backlog, not a task list).

**Why the work stopped.** The previous session hit the account's weekly usage limit immediately after creating the empty S5 branch. No code defect stopped it.

**Three things changed since the plan was written:**

1. **The SDD tooling is gone.** `gentle-ai` is now 4.3.1: `gentle-ai sdd-status` and `gentle-ai sdd-attempt` return "unknown command", and the `sdd-*` agent types and `~/.claude/skills/sdd-*` no longer exist. Do not look for them, and ignore every attempt token in older records. The attempt opened for this change can never be settled; that is expected. Do not re-plan: `openspec/changes/caztor-providers-auth/tasks.md` remains the task list and logbook.
2. **Receipt-driven development is now on by default** (`gentle-ai review mode status`). After a work-unit commit run `gentle-ai review assess` only when T13 says so. Candidate consent belongs to the user.
3. **`agy` moved from 1.4.7 to 1.4.11** since the free checks were recorded. Repeat them (task T1).

**An `agy` process may be running in this repository.** On 2026-10-30 at 16:10 an interactive `agy` (no flags, cwd `/home/andres/CaozCompilator`) was started, apparently by the user. Before writing anything:

```sh
pgrep -af '(^|/)agy( |$)'; git status --short; git log --oneline -3
```

Never kill a process you did not start. If that process has changed files or commits, stop and ask the user which work wins.

## 2. Current state

| Item | Value |
|---|---|
| Repository | `/home/andres/CaozCompilator` (git, no remote, local branches only) |
| Checked out | `feat/providers-auth-s5-antigravity` at `6d1b430`, no commits of its own yet |
| `main` | `bb6814e` (MVP plus writing guides, both archived) |
| Working tree | `.atl/skill-registry.md` and `.atl/.skill-registry.cache.json` modified by tooling (not part of this work, do not commit them with feature work) |
| Tests at `6d1b430` | `npx vitest run` 2865 passed, 31 skipped; `npx tsc -b` exit 0 (run with a temporary `XDG_CONFIG_HOME`) |
| Tasks | 5.1 and all of S1 to S4 ticked; 5.2 to 5.7 and 6.1 to 6.4 open |

Branch chain, each from the previous:

```text
main (bb6814e)
└─ feature/caztor-providers-auth (0bad862, planning artifacts)
   └─ feat/providers-auth-s1-foundation (45597ef)
      └─ feat/providers-auth-s2-env-turn-routes (99af941)
         └─ feat/providers-auth-s3-web (bd0b97d)
            └─ feat/providers-auth-s4-definition (6d1b430)
               └─ feat/providers-auth-s5-antigravity (6d1b430, work continues here)
```

Done in S1 to S4: auth types and slots, credential store, secret redaction, per-mode child environments, Claude account mode stripping API variables, credential routes, auth mode routes, web toggle and key form and login hints, `agents/antigravity.md`, the `antigravity` provider id, `.agents` reserved, `scanAntigravityProjectConfig`, `antigravityDefinitionProblem`.

Not done: anything that runs `agy`. Antigravity is listed as unavailable because no runner is wired. The permanent partial-isolation notice is not built.

## 3. Product context

Caztor is a local-first web LaTeX editor. Four vertical panes, left to right: files, LaTeX editor, PDF preview, chat. The chat is deliberately separate from the editor, has a designed non-terminal UI, and shows the active provider's logo. It drives the user's local CLIs. A long-term direction stated by the user: Caztor becomes an extension of papersmith (`/home/andres/papersmith-ai`), their research group's project, and is later deployable to Cloudflare or similar.

Read `README.md` for usage and layout: `packages/core` (ports, turn service, no Node imports), `packages/api` (Hono routes, no Node imports), `packages/adapters-local` (Node adapters), `apps/server-local`, `apps/web`, `agents/`, `guides/`, `e2e/`.

**What this change delivers, in the user's words (translated):** choose a provider by API or account; "I want to use a chat by subscription, which is what I have with you (Claude), with Antigravity, ChatGPT, but leave the API option open".
