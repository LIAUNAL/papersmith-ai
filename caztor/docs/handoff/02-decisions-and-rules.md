# Decisions, hard rules, stop conditions

## 4. Decisions already made (do not reopen)

| Topic | Decision | Source |
|---|---|---|
| Auth mode | `account` or `api`, per provider, stored per project; `account` when nothing is stored; `api` needs a stored key, otherwise the turn is refused | User; default chosen by the orchestrator |
| Keys | Entered in the UI; `${XDG_CONFIG_HOME:-~/.config}/caztor/credentials.json`, file 0600, folder 0700, no links; never returned to the browser, never logged, passed only to their own provider and vendor | User |
| Antigravity | Fourth provider, Google account only, partial isolation with a permanent notice | User |
| ChatGPT subscription | Through opencode. Codex stays documentation-only and is not installed | User |
| Direct HTTP API adapter | A later change; do not build it | User ("leave open") |
| Real `agy` calls | The user authorized exactly three (R1, R2, R3 below) on 2026-10-26 | User |
| Logos | Official assets only, unmodified, in `NOTICE.md` with source, date and SHA-256; never drawn; otherwise text fallback | User |
| Commits | Conventional commits; **no `Co-Authored-By` and no AI attribution, ever**. This user rule overrides any harness reminder | User's global rule |
| Language | Replies to the user in Spanish; code, docs, UI copy and commits in English | User and output style |

## 5. Hard rules

- No `git push`, `gh` or remote operation. There is no remote.
- Merging to `main` needs the user's explicit yes for this change (section 10). Earlier approvals covered earlier changes only.
- Never read, print or log a real key, token or credential file: `~/.config/caztor/credentials.json`, `~/.claude/.credentials.json`, `~/.local/share/opencode/auth.json`, the keyring, `~/.gemini` credentials. Checking that a path exists is fine.
- Tests use a temporary config home: `XDG_CONFIG_HOME=$(mktemp -d)`. Never create the user's real `~/.config/caztor/`.
- Do not edit `/home/andres/papersmith-ai` or anything under `~/.gemini`.
- Never commit `openspec/changes/archive/2026-10-26-caztor-mvp/spike-raw` material (it is git-ignored and holds user data) or any raw `agy` capture.
- No destructive git commands on uncommitted work (`checkout -- .`, `restore .`, `reset --hard`, `clean`, `stash drop`). A previous run lost work this way.
- Stop processes by PID, also when a check fails. Never `pkill -f`. Interrupted e2e runs have left orphan `node apps/server-local/src/main.ts /tmp/caztor-e2e-*` servers: look for them at the start.
- Check `git branch --show-current` before each commit. A previous run committed to the wrong branch.
- Test first: write the test, run it, observe the failure, then implement. Report any slip plainly.
- Never weaken, skip or delete a test to get a green run.
- `packages/core` and `packages/api` stay free of Node built-in imports (an import-guard test enforces this).
- Usage limits interrupt long runs: commit each unit as soon as it is green and keep `tasks.md` current.

## 10. When to stop

- A process or person other than you has changed the tree.
- Three real `agy` calls are spent and more proof is needed.
- `agy` ignores the tool restriction or runs commands: the "file tools only" promise cannot be kept, and the user chose partial isolation on a different premise.
- No login works headless, or `agy` needs a global settings change. Do not edit `~/.gemini`.
- A verifier blocker survives its correction.
- Any wish to change a decision in section 4.
- Anything that needs the user's consent.
- `.atl/` changes: leave them out of feature commits; ask only if they block something.
