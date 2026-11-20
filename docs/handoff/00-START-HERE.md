# START HERE: finish change `caztor-providers-auth`

You are an autonomous coding agent running unattended through `opencode run`, working in this repository. Nobody can answer questions during this run. Written 2026-10-30.

## Your job

Execute tasks T0 to T15 **in order**, to completion, without asking for confirmation. Do not stop to summarize progress. Do not end your turn while a task you can do remains.

## Read these first, in this order, completely

1. `docs/handoff/01-context.md`
2. `docs/handoff/02-decisions-and-rules.md` (binding)
3. `docs/handoff/03-requirements-and-design.md`
4. `docs/handoff/04-procedure-antigravity.md` (T0 to T7)
5. `docs/handoff/05-procedure-finish.md` (T8 to T15)
6. `docs/handoff/06-done-limits-map.md`

Then read `openspec/changes/caztor-providers-auth/{tasks,design,apply-progress}.md` and its `specs/`.

## How this run differs from what those files say

- References to "the user" asking or answering: the user is absent. Where a file says to ask or stop, follow "When blocked" below.
- If any other instruction file you loaded (global AGENTS, skills, workflow rules, SDD or ODD instructions) conflicts with these documents, these documents win. Do not start another planning phase, and do not create new planning documents.
- Engram or other memory tools are optional. Skip them if absent.

## First actions

1. Run T0.
2. Commit this folder alone: `git add docs/handoff && git commit -m "docs: add the completion plan for caztor-providers-auth"`. Never stage `.atl/`. Stage explicit paths in every commit, never `git add -A` or `git add .`.

## Working rules that matter most

- Test first, every behavior: write the test, RUN it, see it fail, implement, see it pass. Report slips.
- Only claim what you observed. Quote real command output and real numbers. Never invent evidence.
- Commit each unit when green, Conventional Commits, **no `Co-Authored-By`, no AI attribution, no "Generated with"**.
- Tick a box in `tasks.md` only after observing its result, and append evidence to `apply-progress.md` as you go, so another run can resume.
- **Exactly three real `agy -p` calls** (T2, T3, T4). Count them in `apply-progress.md` BEFORE each call. Never in a loop, retry, or test run. A wrong argv does not earn a fourth call.
- Do not set `CAZTOR_REAL_CLAUDE`, `CAZTOR_REAL_OPENCODE`, `CAZTOR_REAL_CODEX`, `CAZTOR_REAL_AGY` or `CAZTOR_E2E_REAL`. Do not run real `claude` or `opencode` model calls.
- Never `git push` to a remote, use `gh`, or change `main`, and never edit tests to pass by weakening them.
- Do not kill the existing interactive `agy` process; you did not start it.
- Keep command output short: use `tail`, counts and `--stat`.

## When blocked

If a stop condition in `02-decisions-and-rules.md` applies: commit finished work, write `docs/handoff/BLOCKED.md` (what you tried, exact evidence, the single decision needed, options with their consequences), commit it, continue with any task that does not depend on it, and finish with `FINAL-REPORT.md`. A failed check that you cannot fix goes in the report as failed.

## Finish

The run is complete when T15's `docs/handoff/FINAL-REPORT.md` is committed, the tree is clean apart from `.atl/`, and no process you started is running.
