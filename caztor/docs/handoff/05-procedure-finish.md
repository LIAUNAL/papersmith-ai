# Procedure part 2: T8 to T15 (logo, docs, checks, verification, archive, report)

### T8. Logo (task 6.2)

Candidates in order: an icon inside the `agy` install; an official asset from https://antigravity.google. Ship byte for byte in `apps/web/src/assets/providers/`, with a `NOTICE.md` row (source URL, retrieval date, SHA-256, non-affiliation), and no script, event handler, external reference or `foreignObject`. The test `apps/server-local/test/provider-logos-notice.test.ts` covers checksums. If no official asset is found, keep `logo: null` and record that decision in `NOTICE.md`. Never draw one.

### T9. Compact auth panel

Follow-up from S3: the panel adds about 100 px to the chat header in a narrow pane. Make it compact or collapsible once the provider is configured, in light and dark. If the notice plus panel crowd the chat at 1366 x 768, fix it here.

### T10. Docs (tasks 6.1, 6.3)

On `feat/providers-auth-s6-docs`.

- `README.md`: auth modes; key storage path and permissions; Antigravity and its partial isolation; subscription routes (Claude Code, Antigravity, ChatGPT through opencode, whose accepted models vary: `openai/gpt-5.5` was rejected in October, `openai/gpt-5.6-terra` worked); release note that an exported `ANTHROPIC_API_KEY` no longer reaches Claude in account mode, and that opencode account mode ignores exported vendor keys; `CAZTOR_REAL_AGY`. Verify each command and variable against the code.
- `proposal.md`: rollback text `credentials` to `credentials.json`.
- Tick tasks, complete the traceability check in `tasks.md` (task 6.4).

### T11. Full checks

```sh
export XDG_CONFIG_HOME=$(mktemp -d)
npx vitest run
npx tsc -b
CAZTOR_REAL_BIN=1 npx vitest run packages/adapters-local
npm run build -w @caztor/web
export LD_LIBRARY_PATH=$HOME/.cache/caztor-tools/libs/root/usr/lib/x86_64-linux-gnu
export CAZTOR_PLAYWRIGHT=$HOME/.cache/caztor-tools/node_modules/playwright/index.mjs
export CAZTOR_E2E_OUT=$(mktemp -d)
node e2e/dialog.mjs; node e2e/compile.mjs; node e2e/chat.mjs
```

Do not set `CAZTOR_REAL_CLAUDE`, `CAZTOR_REAL_OPENCODE`, `CAZTOR_REAL_CODEX`, `CAZTOR_E2E_REAL` or `CAZTOR_REAL_AGY`: they spend the user's quota. Extend `e2e/chat.mjs` with Antigravity cases (scripted stub): notice, logo or fallback, unavailable state. Take screenshots with Antigravity selected in light and dark at 1440 x 900 and 1366 x 768, read them. Expect no console errors or CSP violations. CSP: `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; worker-src 'self' blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'`.

The test `project-store-watch` "finds changes that no event announced" failed once under load before being reworked. If it recurs, report it; do not ignore it.

### T12. Independent verification

**Required: this change touches credentials and sandbox guards (high-risk item 2), and S1 to S4 have never been independently verified.** Run one verifier through your `task` tool with the `general` subagent, in fresh context; if no subagent is available, do the review yourself, and state in the report that independent verification is still pending. Give it the whole of `specs/`, `design.md` and `tasks.md`, baseline `bb6814e`, working in its own worktree at `/home/andres/CaozCompilator-worktrees/verify-auth` (not under `/tmp`), removed afterwards. No real provider call. Past verifiers found defects unit tests missed, so make it adversarial, and at minimum have it try:

| Area | Probes |
|---|---|
| Credential store | Wrong mode, foreign owner, symlinked file and folder, corrupt file not overwritten, concurrent writes, interrupted write leaves no partial file or temp |
| Read-back | Every route, HEAD and GET variants, error bodies, history, event stream, `state.json`, snapshots, process argv (`/proc/<pid>/cmdline`) never contain a planted key |
| Redaction | Key split across stream chunks: the design accepts a brief live exposure in text deltas only; confirm history and final text are clean, and report whether that acceptance still holds |
| Cross-provider | Claude key never reaches opencode or Codex; opencode only gets the vendor of the model; `api` to `account` switch stops passing the key; exported keys ignored in account mode, using wrapper scripts that record the environment |
| Sessions | Mode change starts a new conversation with a notice; old records read as `account`; opencode data folder split between modes |
| Routes | Token, Host, Origin, content type, body size; hostile slots such as `../x`, `opencode:../../x`, `__proto__` |
| Antigravity | Stub-driven guard, `.agents/` symlinks and scan bounds, hostile ids and models, hung process, trust invalidation |
| UI | Key field emptied on success and failure; key absent from DOM, storage and URL; notice always shown |

Corrections: one batch fixing every blocker, one recheck limited to those blockers, written as regression tests. Anything still open goes to the user as one **Needs your decision** result.

Save the result as `openspec/changes/caztor-providers-auth/verify-report.md`, with a matrix of the 25 requirements and 63 scenarios (full, partial, missing) and the test numbers observed.

### T13. Native review

Run `gentle-ai review assess --cwd . --agent opencode --base-ref bb6814e --committed-only --json` once and record the result in `apply-progress.md`. Do NOT start a native review: consent belongs to the user, who is not present. List it as pending in `FINAL-REPORT.md`.

### T14. Archive

The archive tooling is gone, so do it by hand:

1. Requires no unticked tasks and no open critical finding.
2. Merge deltas into `openspec/specs/`: `provider-auth` copied whole. For `agent-providers`, `agent-definitions`, `agent-chat`, `local-server-security`, `project-files`: ADDED appended, MODIFIED replaces the block with the same name, whole block with all scenarios.
3. Verify each delta requirement appears exactly once, and every unrelated requirement is byte-identical to `git show HEAD:openspec/specs/<domain>/spec.md`. Files stay 0644.
4. `git mv openspec/changes/caztor-providers-auth openspec/changes/archive/<today>-caztor-providers-auth`.
5. Commit `docs(sdd): archive caztor-providers-auth and merge its specs`. Check `git status --ignored` so nothing git-ignored became staged. Leave `docs/handoff/` in place.

### T15. Report, do not merge

Do NOT touch `main`. Merging is the user's decision. Write `docs/handoff/FINAL-REPORT.md`: verified outcome, test numbers, real `agy` calls with results, every skipped or pending check, deviations, TDD slips, branch tips, and the line `Risk: item 2 (credentials and guards)`. Commit it, leave the tree clean, and end.
