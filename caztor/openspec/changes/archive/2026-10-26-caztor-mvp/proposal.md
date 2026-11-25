# Proposal: Caztor MVP

## Intent

Build Caztor, a local-first browser LaTeX editor whose separate chat panel drives the user's own terminal CLIs. Greenfield. Success: edit, compile, preview and agent-assisted revision with whole-turn undo, all on this machine.

## Scope

### In Scope
- Four resizable panes: file tree, CodeMirror editor, PDF preview, chat.
- tectonic compile (only engine installed): stderr plus `.log` diagnostics, BibTeX.
- Chat through `claude`, `opencode`, `codex`: selector, logo, per-provider model setting.
- One academic-writing agent `.md` per provider, provisioned into the project.
- Direct-to-disk agent edits: pre-turn snapshot, changed-files list, whole-turn undo.
- Loopback security and the ports/adapters seam.

### Out of Scope
SyncTeX jumping, biblatex/biber, cloud deployment and adapters, collaboration, accounts, Zotero, git integration.

## Capabilities

### New Capabilities
- `workspace-layout`: four-pane shell, persisted sizes.
- `project-files`: tree, CRUD, path containment, hash-checked saves.
- `latex-editor`: highlighting, autosave, external-change handling.
- `latex-compile`: tectonic runs, diagnostics, stop-on-error toggle, biblatex notice.
- `pdf-preview`: reload keeping scroll; log panel with click-to-line.
- `agent-chat`: designed chat UI, streaming, tool cards, Stop, session continuity.
- `agent-providers`: CLI detection, normalized events, model setting, error surfacing.
- `agent-definitions`: per-provider files and provisioning.
- `turn-snapshots`: snapshot, changed files, undo.
- `local-server-security`: loopback, Host/Origin allowlist, launch token.

### Modified Capabilities
None.

## Approach

`packages/core` owns `CompilerPort`, `ProjectStorePort`, `AgentRunnerPort` and a snapshot port. `packages/adapters-local` spawns binaries; `apps/server-local` (Hono, SSE) and `apps/web` (React, Vite) consume ports only, so a later `apps/worker` swaps adapters.

Ordered slices, one PR each, within 400 changed lines:

| # | Slice | Verified by |
|---|-------|-------------|
| 1 | Workspace scaffold, Vitest, enable strict TDD | `npx vitest run` |
| 2 | Core ports, local project store | containment tests |
| 3 | Server security, file API | request tests |
| 4 | Layout, file tree | component tests |
| 5 | Editor, hash-checked autosave | conflict tests |
| 6 | Compile adapter, diagnostics parser | spike fixtures |
| 7 | PDF preview, log panel | component tests |
| 8 | Turn snapshots, undo | restore tests |
| 9 | Event model, claude adapter | captured stream fixtures |
| 10 | opencode adapter, model setting | captured fixtures |
| 11 | codex adapter, "not installed" state | documented-shape fixtures |
| 12 | Agent files, provisioning | marker-block tests |
| 13 | Chat UI | component tests |

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `packages/core`, `packages/adapters-local` | New | Ports, adapters |
| `apps/server-local`, `apps/web` | New | Server, UI |
| `agents/*.md` | New | Agent sources |
| `openspec/config.yaml` | Modified | `strict_tdd: true` after slice 1 |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| `--untrusted` does not contain file reads | High | Design decision required: OS sandbox or documented accepted risk |
| User-global CLI config loads every turn (about 25k tokens, USD 0.22) | High | Design decides isolation flags |
| `continue-on-errors` exits 0 | Med | Derive status from `error:` lines |
| opencode default model fails headless | Med | Model setting; surface `error` events |
| codex untested locally | High | Fixtures; feature detection |
| Agent and user edit concurrently | Med | Hash-checked saves; snapshots |

## Rollback Plan

Each slice reverts as one PR; no migrations exist. In user projects Caztor writes only `.caztor/`, provisioned agent files and a marked `AGENTS.md` block; deleting them restores the project. Agent edits revert through whole-turn undo.

## Dependencies

- tectonic 0.17.0; network for uncached packages.
- `claude` 2.1.296, `opencode` 1.19.0; `codex` absent.

## Success Criteria

- [ ] A BibTeX paper compiles and previews; errors link to file and line.
- [ ] A claude or opencode turn streams, lists changed files and undoes fully.
- [ ] codex shows "not installed" without failing.
- [ ] Core imports no Node process APIs.
- [ ] Every slice merges under 400 lines with tests passing.
