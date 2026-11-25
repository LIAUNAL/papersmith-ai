```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:3552b2853167ebd1ada6deb8051e0e6cf9dbed9fc742ae4f1cacf0a65aec7b87
verdict: pass_with_warnings
blockers: 0
critical_findings: 0
requirements: 72/72
scenarios: 124/124
test_command: npx vitest run
test_exit_code: 0
test_output_hash: sha256:ddc29a9807d2d111cbdfa0520f798979825c00171f667c8d7c0547237e073c79
build_command: npx tsc -b
build_exit_code: 0
build_output_hash: sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
```

## Verification Report

**Change**: caztor-mvp
**Version**: N/A (10 capability specs, design revision 2)
**Mode**: Strict TDD
**Tip verified**: branch `caztor/s31b-project-cli-config` (8950c11), clean working tree

### Completeness
| Metric | Value |
|--------|-------|
| Tasks total | 89 |
| Tasks complete | 89 |
| Tasks incomplete | 0 |
| Requirements (heading count) | 72 |
| Scenarios (heading count) | 124 |

### Build & Tests Execution
**Build**: PASSED
```text
npx tsc -b  -> exit 0, no output
npm run build -w @caztor/web -> built (bundle size warning only)
```

**Tests**: PASSED, 2349 passed / 0 failed / 29 skipped (138 files passed, 6 skipped)
```text
npx vitest run -> exit 0
CAZTOR_REAL_BIN=1 npx vitest run packages/adapters-local -> exit 0, 1178 passed, 9 skipped (51 files passed, 4 skipped); real tectonic, bubblewrap and file system
Browser (real server, real tectonic, headless Chromium): e2e/dialog.mjs 7 PASS; e2e/compile.mjs 29 PASS, ALL CHECKS PASSED; e2e/chat.mjs 30 PASS, ALL CHECKS PASSED
```
The 29 skipped tests are opt-in real-CLI tests (Claude, opencode, Codex, token-spending) that this phase was told not to run. No server or tectonic process remained and port 4317 was free afterwards.

**Coverage**: not available (no coverage tool installed; config says planned). Skipped, not a failure.

### TDD Compliance
| Check | Result | Details |
|-------|--------|---------|
| TDD evidence reported | PASS | Tables for every batch A-M in apply-progress.md |
| All tasks have tests | PASS | Config-only/verification tasks (1.1, 1.2, 1.4, 3.1, 7.1, 9.2) are marked structural with a stated reason |
| RED confirmed (test files exist) | PASS | All cited test files exist in the 144-file test set |
| GREEN confirmed | PASS | Whole suite passes on execution (2349/2349 non-skipped) |
| Triangulation | PASS | Most rows list multiple distinct cases |
| Safety net for modified files | PASS | Modified-file rows carry a passing baseline count |
| Disclosed slips | WARNING | See W5 |

### Spec Compliance Matrix (by requirement; scenario evidence in the same row)
Result key: C = all scenarios covered by a passing test, P = partial.

| Capability / Requirement | Evidence (passing tests) | Result |
|---|---|---|
| workspace-layout / Four-pane arrangement | layout/Workspace.test.tsx, app/App.test.tsx | C |
| workspace-layout / Resizable panes | layout/Workspace.test.tsx, layout/panes.test.ts (160/280/280/300 minimums) | C |
| workspace-layout / Persisted sizes | layout/storage.test.ts, panes.test.ts (corrupt shapes), Workspace.test.tsx | C |
| workspace-layout / Independent panes | editor/EditorPane.test.tsx "stays editable whatever else is running" (no test with a live turn) | P |
| project-files / File tree | files/FileTree.test.tsx, tree.test.ts | C |
| project-files / File operations | FileTree.create/delete/upload.test.tsx, routes/files-structure.test.ts, project-store-write.test.ts | C |
| project-files / Path containment | project-store.test.ts, project-store-hardening.test.ts, routes/files.test.ts | C |
| project-files / Hash-checked saves | project-store-write.test.ts, routes/files.test.ts, editor/session.test.ts | C |
| project-files / Reserved paths | project-store-agents-md.test.ts, FileTree.test.tsx, server-agents-md.test.ts | C |
| latex-editor / Syntax highlighting | editor/languages.test.ts, bibtex.test.ts | C |
| latex-editor / Autosave | editor/session.test.ts, EditorPane.test.tsx | C |
| latex-editor / External change to a clean buffer | editor/session.external.test.ts, CodeEditor.test.tsx | C |
| latex-editor / External change to a dirty buffer | session.resolve.test.ts, EditorPane.conflict.test.tsx | C |
| latex-editor / Undo restores open buffers | session.external.test.ts, routes/chat.test.ts (undo then reload) | C |
| latex-compile / Local compile | tectonic/compiler.test.ts, real-tectonic.test.ts (real run) | C |
| latex-compile / Status from diagnostics | tectonic/status.test.ts, compiler.test.ts | C |
| latex-compile / Stop-on-error toggle | compiler.test.ts, CompileOptions.test.tsx, routes/compile.test.ts | C |
| latex-compile / Diagnostics | diagnostics.test.ts, log-parser.test.ts | C |
| latex-compile / First-run state | compile-state.test.ts, CompileToolbar.test.tsx, status.test.ts (offline) | C |
| latex-compile / BibTeX and biblatex | biblatex-scan.test.ts, compiler.test.ts, real-tectonic.test.ts | C |
| latex-compile / Shell escape disabled | command.test.ts, real-tectonic.test.ts (\\write18) | C |
| latex-compile / Single run and cancel | core/compile-coordinator.test.ts, routes/compile.test.ts | C |
| latex-compile / Time limit | tectonic/compiler-limits.test.ts, real-sandbox.test.ts | C |
| latex-compile / Auto-compile | compile/auto-compile.test.ts, App.test.tsx | C |
| latex-compile / Outside-project read diagnostic | compiler.test.ts, real-tectonic.test.ts | C |
| latex-compile / Sandboxed compile | sandbox.test.ts, compiler-sandbox.test.ts, server-sandbox.test.ts, real-sandbox.test.ts (real bubblewrap) | C |
| pdf-preview / PDF display | preview/PdfPreview.test.tsx, PdfViewer.test.tsx, e2e/compile.mjs | C |
| pdf-preview / Reload keeps position | PdfViewer.test.tsx, prefs.test.ts, layout.test.ts | C |
| pdf-preview / Empty and failed states | PdfPreview.test.tsx, preview-state.test.ts | C |
| pdf-preview / Log panel with click-to-line | compile/LogPanel.test.tsx, EditorPane.test.tsx (jump), App.test.tsx | C |
| agent-chat / Designed message UI | chat/MessageList.test.tsx, markdown.test.tsx | C |
| agent-chat / Provider header | ProviderLogo/Select.test.tsx, provider-logos-notice.test.ts (asset origin, checksums) | C |
| agent-chat / Streaming at any granularity | core/chat-reducer.test.ts, MessageList.test.tsx | C |
| agent-chat / Tool activity cards | ToolActivityCard.test.tsx, MessageList.test.tsx | C |
| agent-chat / Stop | ChatPanel.test.tsx, routes/chat.test.ts, runner tests | C |
| agent-chat / Session continuity | controller.test.ts, ChatPanel.test.tsx, routes/chat.test.ts | C |
| agent-chat / Readable errors and busy state | ErrorCard.test.tsx, ChatPanel.test.tsx, controller.test.ts | C |
| agent-chat / Changed-files summary | TurnSummary.test.tsx, routes/chat.test.ts | C |
| agent-chat / Chat history | chat-history.test.ts, controller.test.ts, chat-client.test.ts | C |
| agent-providers / Provider detection | routes/providers.test.ts, server-codex.test.ts, ProviderUnavailable.test.tsx | C |
| agent-providers / Provider selection | ProviderSelect.test.tsx, routes/providers.test.ts | C |
| agent-providers / Normalized events | claude, opencode, codex mapper.test.ts; core/ports.test.ts (no single cross-provider equivalence test) | P |
| agent-providers / Per-provider model setting | core/model.test.ts, ModelSelect.test.tsx, opencode/runner.test.ts | C |
| agent-providers / Error surfacing | mapper and runner tests (auth, abrupt exit, malformed_output) | C |
| agent-providers / Isolation from global configuration | claude/runner.test.ts (tiers I1-I3), opencode/runner.test.ts, real-config.test.ts (real opencode, free) | C |
| agent-providers / Isolation violation | claude and opencode runner.test.ts (isolation_failed) | C |
| agent-providers / Project CLI configuration | providers/project-config.test.ts, runner gates, routes/providers.test.ts, ChatPanel.test.tsx | C (Claude real CLI not observed, see W2) |
| agent-providers / Codex command execution | ChatPanel.test.tsx, codex/runner.test.ts | C (fixtures from documentation, see W1) |
| agent-providers / Safe process launch | node-infra.test.ts (real spawn, shell false), command.test.ts, runners (stdin prompt) | C |
| agent-definitions / One definition per provider | agents/agents.test.ts | C |
| agent-definitions / Behavioral prohibitions | agents/agents.test.ts | C |
| agent-definitions / Provisioning | provisioner/native.test.ts | C |
| agent-definitions / User-modified definition | native.test.ts, routes/chat.test.ts (replace) | C |
| agent-definitions / Definition change resets the conversation | routes/chat.test.ts, chat-client.test.ts | C |
| agent-definitions / Marked block preservation | provisioner/agents-md.test.ts, agents-md-safety.test.ts | C |
| agent-definitions / Removable | provisioner/remove.test.ts | C |
| turn-snapshots / Pre-turn snapshot | snapshot/capture.test.ts, routes/chat.test.ts (snapshot_failed) | C |
| turn-snapshots / Changed-files list | snapshot/diff.test.ts, TurnSummary.test.tsx | C |
| turn-snapshots / Whole-turn undo | snapshot/restore.test.ts, routes/chat.test.ts | C |
| turn-snapshots / Undo protects later user edits | restore.test.ts (strict, skip, force, safety snapshot), UndoConflictDialog.test.tsx | C |
| turn-snapshots / Snapshot scope and retention | capture.test.ts (exclusions), prune.test.ts | C |
| turn-snapshots / Undo order | snapshot/restore-order.test.ts, routes/chat.test.ts (not_latest) | C |
| turn-snapshots / User edits during a turn | diff.test.ts (mixed), project-store-user-writes.test.ts, routes/chat.test.ts (recorder race) | C |
| turn-snapshots / Snapshot limits | snapshot/limits.test.ts | C |
| turn-snapshots / Revert note | core/turn-service.test.ts, routes/chat.test.ts | C |
| turn-snapshots / Interrupted turns | turn-service.test.ts, TurnSummary.test.tsx, ChatPanel.test.tsx | C |
| local-server-security / Loopback bind | server-local/test/server.test.ts | C |
| local-server-security / Host and Origin allowlists | api/test/security.test.ts, security-scope.test.ts | C |
| local-server-security / Launch token | api/test/token.test.ts, security.test.ts, server.test.ts; no test that a token from a prior launch is rejected after a restart | P |
| local-server-security / Path containment | project-store.test.ts, routes/files.test.ts, static.test.ts | C |
| local-server-security / No shell spawning | node-infra.test.ts, command.test.ts, import-guard.test.ts | C |
| local-server-security / Disclosed limits | DisclosureNotice.test.tsx, App.test.tsx, routes/session.test.ts | C |

**Envelope note**: the validator requires completed equal to total for a passing verdict, so the envelope counts the 3 partial scenarios as accepted with warning (W3, W4); the true split is below.

**Compliance summary**: 69/72 requirements and 121/124 scenarios fully covered by a passing test; 3 requirements (3 scenarios) partial; 0 missing; 0 failing. The scenario-to-test mapping was built from test titles, the apply-progress evidence tables and spot reads, then confirmed by the green runs above.

### Correctness (Static Evidence)
All 72 requirements have implementing code in the five workspaces (core, api, adapters-local, server-local, web) plus agents/. No requirement lacks an implementation.

### Coherence (Design)
| Decision | Followed? | Notes |
|---|---|---|
| Hexagonal split (core pure, adapters, api, apps) | Yes | core/test/import-guard.test.ts enforces no Node imports in core |
| Loopback, Host/Origin, per-launch token on every API call | Yes | security tests + runtime check |
| Argv-array spawns, no shell | Yes | node-infra real spawn |
| Tectonic argv/env | Deviation, documented | `./main.tex`, env allowlist without LANG/LC_ALL, notes on stdout (merged streams) |
| Provider env by explicit names, not prefixes | Deviation, documented | Safer than the design |
| Claude MCP connected -> notice | Deviation, documented | Turn is aborted instead (stricter) |
| Compile Button in preview pane header | Deviation, documented | Cosmetic |
| Rescan after turn and undo | Open | Periodic 30 s/5 s rescan exists; confirm wiring (see S2) |
| Logos in assets with NOTICE | Deviation | NOTICE.md at repo root by user request; checksums tested |

### Issues Found
**CRITICAL**: None.

**WARNING**:
- W1. Codex adapter was never run against the real CLI (not installed): argv, event mapping and the sandbox claim come from documentation only; fixtures are documentation-derived. Location: packages/adapters-local/src/providers/codex/*, test/providers/codex/*. Codex has no project-configuration gate. Disclosed to the user.
- W2. Claude Code under the isolation flags with a project `.mcp.json`/settings was never observed on the real CLI; the safety rests on the per-project trust gate (providers/project-config.ts, claude/runner.ts) rather than on proven flag behavior.
- W3. Req "Launch token" scenario "Token rotates" has no test that a previous launch's token fails after a restart (only that tokens are generated randomly and ignored from the environment in production). Location: apps/server-local/test/server.test.ts.
- W4. Req "Independent panes" (editor accepts typing during a running turn) is proven only by a generic "stays editable" test, not with a live chat turn; req "Normalized events" ("Equivalent turns") has per-provider mapper tests but no cross-provider equivalence test. Locations: apps/web/src/editor/EditorPane.test.tsx:118, packages/adapters-local/test/providers/*/mapper.test.ts.
- W5. Strict TDD slips disclosed in apply-progress (tests written after or with the code): FakeSpawner helper, fixture scan, limits.ts (RED by mutation), manifest parser, defaultAgentsDir, model.ts, server-chat wiring, chat API client, controller/compile-state/prefs/preview-state/PdfViewer modules (RED inferred), real-sandbox and real-config tests, server-opencode trust test. All end covered and green; several were mutation-checked. Process finding, not a behavior gap.
- W6. The save-versus-turn-end race fix is proven only by a deterministic in-repo test; the original race was not reproduced over HTTP.
- W7. Real-CLI paths not exercised here by instruction (spend tokens): Claude, opencode (continuation `-s` never run for real), Codex, CAZTOR_E2E_REAL.

**SUGGESTION**:
- S1. No coverage tool is configured (config lists coverage as planned); consider adding @vitest/coverage-v8 and a threshold.
- S2. Design D9 asks for a forced rescan after every turn and undo; apply-progress defers wiring to slices 23/24. Confirm it is wired (periodic rescan already bounds staleness).
- S3. Disclosed limits to keep in the README: Claude Code writes its own transcripts under ~/.claude/projects and the provider includes the signed-in account email in model context; PDF preview has no text layer and no WebAssembly decoders (CSP), so text cannot be selected and JPX/JBIG2/CMap-dependent PDFs may render wrongly.
- S4. No linter is configured; web bundle is 636 kB with a chunk-size warning (code splitting not done).
- S5. The 9p `/mnt/c` recursive watcher, very large PDFs and high device pixel ratios remain unverified.

### Verdict
PASS WITH WARNINGS
0 CRITICAL, 7 WARNING, 5 SUGGESTION. All 89 tasks complete; suite and typecheck green; real tectonic, bubblewrap and Chromium checks pass. Ready to archive; the warnings are disclosed limits and two thin scenario proofs, none blocks.
