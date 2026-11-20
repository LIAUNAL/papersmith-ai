# Definition of done, known limits, backlog, file map

## 9. Definition of done

- [ ] All of `tasks.md` ticked with observed evidence
- [ ] Antigravity selectable and one real turn observed: edit lands, listed, undone exactly
- [ ] Guard observed against what `agy` really emits, or the weaker guarantee reported to the user
- [ ] Notice always visible; logo or recorded fallback
- [ ] Full checks in T11 green, with numbers recorded
- [ ] Independent verification with no open blocker; verify report committed
- [ ] Specs merged and change archived
- [ ] README and NOTICE accurate
- [ ] No real key in any test, log, fixture or commit; no attribution in any commit: `git log bb6814e..HEAD --format='%b' | grep -iE 'co-authored|generated with'` is empty
- [ ] No orphan process; temporary folders removed
- [ ] User decided on `main`

## 11. Known limits to keep disclosed

Codex never ran against a real CLI and has no project-config gate. `claude -p` still writes session transcripts under `~/.claude/projects`, and the model sees the signed-in email through Claude Code's own metadata. Claude with a project `.mcp.json` under the isolation flags was never observed on the real CLI; a trust gate covers it. opencode installs about 62 MB of plugin packages per project. The PDF preview has no text layer and no WebAssembly decoders, so text is not selectable and JPX, JBIG2 or CMap-dependent PDFs may render wrongly. The read-only rule for `.caztor/guides` is instruction plus hash tracking, not enforcement. Tectonic reads are not confined unless the opt-in sandbox is on.

## 12. Backlog, not part of this work

- Guide source backed by a local papersmith checkout, toward Caztor as a papersmith extension. `GuideSourcePort` and `distillGuide` are ready for it.
- Direct HTTP API adapter, reusing the credential store and auth modes.
- Cloudflare deployment: `apps/worker`, Container or WASM compile, API-based agent. The terminal-backed chat stays local-only.
- Install and verify Codex. Run `CAZTOR_REAL_BIN=1 CAZTOR_REAL_CODEX=1` first.
- `claude auth status` as a free login check to replace `login: "unknown"`. It may print account data; handle that.
- Tests: token rotation across restart; editor during a live turn; cross-provider event equivalence; every guide covering each "Complete set" topic; automated e2e for guide provisioning.
- Forced rescan after turn and undo (design D9 of the MVP), unconfirmed.
- A coverage tool, a linter, and code splitting (web bundle above 600 kB).
- Git config isolation in `guides/distill-script.test.ts`.
- `~/texlive` exists on this machine and was never examined. The first request asked to use the local LaTeX compilers; only `tectonic` was on PATH. Multi-engine support is unbuilt. **Unverified** whether it is a usable TeX Live.
- A LICENSE for Caztor itself: the user's choice, compatible with the Apache-2.0 guides. Review vendor brand guidelines before publishing.

## 13. Where things are

| What | Where |
|---|---|
| This change | `openspec/changes/caztor-providers-auth/{proposal,design,tasks,apply-progress,exploration}.md`, `specs/` |
| Archived changes | `openspec/changes/archive/` (MVP and writing guides, with verify reports) |
| Current specs | `openspec/specs/` |
| Provider adapters | `packages/adapters-local/src/providers/` |
| Agent definitions | `agents/`, tests in `agents/agents.test.ts`, provisioner in `packages/adapters-local/src/provisioner.ts` |
| Credentials | `packages/adapters-local/src/credential-store.ts`, `packages/core/src/{auth,redact}.ts`, `packages/api/src/routes/credentials.ts` |
| Chat UI | `apps/web/src/chat/` |
| Browser tooling | `~/.cache/caztor-tools` (Playwright, Chromium libraries), scripts in `e2e/`, see `e2e/README.md` |
| Engram topics (project `caozcompilator`) | `sdd/caztor-providers-auth/{request,state,explore,proposal,spec,design,tasks,apply-progress}`, `sdd/caztor-mvp/*`, `sdd/caztor-writing-guides/*`. These records predate the tooling change; the repository wins when they disagree |
