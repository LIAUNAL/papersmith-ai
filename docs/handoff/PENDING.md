# Pending tasks

The work to finish when possible. Evidence and context are in [FINAL-REPORT.md](FINAL-REPORT.md).

## Needs quota or a decision

- [ ] Run one real Antigravity turn through Caztor once the Google quota returns, around 2026-11-05. It spends quota:
      `CAZTOR_REAL_BIN=1 CAZTOR_REAL_AGY=1 CAZTOR_REAL_AGY_TURNS=1 npx vitest run packages/adapters-local`
- [ ] During that run, observe a real disallowed tool step and whether `commandExecutionPolicy: off` is enforced.
- [ ] Observe the real output of `agy` without a login, then compare it with the synthetic fixtures.
- [ ] Decide whether to run the native review. It was due for high risk and was not run before the merge to `main`.

## Pi provider

- [ ] Run one real Pi turn through Caztor once someone is signed in to Pi. It spends quota. The adapter and its fixtures come from Pi 1.4.0's documentation only (`docs/json.md`, `docs/message-types.md`); no real turn was run.
- [ ] Observe the real output of `pi --mode json` without a login and with an unknown model, then compare it with the runner tests, which assume exit 1 with "No models available" or `Model "x" not found` on stderr.
- [ ] Confirm that `--tools read,edit,write,grep,find,ls` really keeps `bash` from being declared, and that `--append-system-prompt ""` keeps a global `APPEND_SYSTEM.md` out.
- [ ] Confirm that api mode works with `PI_CODING_AGENT_DIR` pointed at the empty `.caztor/pi-agent-api` (no saved login or global settings), and that Pi writes nothing there that should not stay.

## Collaborators

- [ ] Run one real `tailscale serve --bg 4317` with `--public-name <MagicDNS name> --secure` and open an invite from another device. Only loopback with `localhost:<port>` as the public name was checked (`e2e/collaborators.mjs`); whether the proxy keeps the original `Host` was not observed (both forms are allowed).
- [x] Link previews (chat apps that fetch a pasted URL) can use up an invite. Done: an invite is now a link plus an access key; the link only opens the sign-in form (checked with repeated fetches in `e2e/collaborators.mjs`).
- [ ] No real login was completed through the browser relay, for any provider: claude, codex, opencode, Pi and agy were only started with an empty scratch home and killed after their first output (nothing was pasted or submitted). Still to observe with a real account, per provider:
  - claude: that `claude auth login --claudeai` without a terminal accepts the pasted code on stdin and exits 0, and where the login lands under `CLAUDE_CONFIG_DIR` of the private home.
  - codex: that `codex login --device-auth` exits 0 once the code is entered, inside bubblewrap with `CODEX_HOME` in the private home.
  - opencode: that the headless ChatGPT method exits 0 after the device code; and that opencode's own menu (`opencode auth login` in a terminal) can be driven with the relayed keys.
  - Pi: that the typed `/login` opens its provider menu, which providers work from a relayed terminal, and that it writes `auth.json` in `PI_CODING_AGENT_DIR` (the relay's sign of success).
  - agy: that choosing Google OAuth prints a link and reads the code from the terminal, where its token file lands without D-Bus, and that `agy models` running next to the open TUI (the relay's check) is safe and says signed in.
- [ ] A real agent turn of a collaborator inside the sandbox, with the project's `.caztor/` hidden: only `--version` and shell probes ran. Check that each CLI finds what it needs (opencode's plugin install in the person's own `opencode-xdg`, Pi's prompt file in `.caztor/agents`).
- [ ] With `--new-session`, the first SIGINT to the group ends bwrap and `--die-with-parent` kills the CLI at once, so a collaborator's turn gets no graceful stop. Killing still escalates and works; forwarding SIGINT was not changed.
- [ ] `.caztor/opencode-xdg/opencode/node_modules` (opencode's own plugin package) is kept between host turns and not verified. Collaborators can no longer write it; a package planted before this change would stay until the folder is deleted.
- [ ] Trust confirmations stored before the HMAC seal (plain fingerprints) no longer count, so each project's configuration is asked for once more.
- [ ] Browser sign-ins live with the open project: opening another project ends them.
- [ ] Sessions do not expire on their own (the cookie lasts a year); only a revoke ends them.

## PaperSmith workspaces

- [ ] Decide whether Caztor's agents get PaperSmith's MCP server (`smith mcp serve`). The runners refuse MCP on purpose, so this needs its own security review.
- [ ] Decide what to do with a workspace that has no `paper/main.tex`: only a note today, no scaffold.
- [ ] Block markers: renaming a `.tex` away and back, or deleting and recreating it, gets past the save check. So do agent writes and files the editor cannot open.
- [ ] Block markers: if PaperSmith rewrites a block while an unsaved edit is open, "keep mine" cannot be saved, because PaperSmith changes the marker's digest. "Take disk" or "save copy" work.
- [ ] Decide what to do when `paper/main.tex` is a link outside the project: no question is asked and it cannot be opened.
- [ ] Align with PaperSmith's `latexmk`/`lualatex` build. Caztor compiles with Tectonic into `.caztor/build`, not into `paper/main.pdf`.
- [ ] Hide `skills/kaggle-accounts/store` from the agents too. The file API hides it, but an agent's own tools can still reach it.
- [ ] Decide how undo snapshots should treat large workspaces. Snapshots stop at 200 MB and 5,000 files, so undo can be partial.
- [ ] Remove a remembered project from the navigator, and key preview preferences by path, because two folders with one name share them.
- [ ] Check that opening a workspace does not disturb `smith upgrade`: a turn adds `.claude/`, `.opencode/`, `.agents/` entries and an `AGENTS.md` block.

## Unproven behavior

- [ ] Prove the "Isolated run" scenario with a real binary and a planted global hook. It spends provider tokens.
- [ ] Read the other 21 browser captures.

## Guard

- [ ] Refuse an `agent_response` step with `toolName` or `tool_calls`, and an unknown top-level `tool_call` event.
- [ ] Stop the false positive on an `agent_response` step with `tool_name: null`.
- [ ] Stop a child that stays alive after a fatal or final last line, and pass that line to `tap`.
- [ ] Add any new `agy` step type seen in real runs to `NON_TOOL_STEPS` in `packages/adapters-local/src/providers/antigravity/mapper.ts`.

## Redaction

- [ ] Mask variables such as `GEMINI_API_KEYS`, `GITHUB_TOKEN_2` and `SECRET_KEY_BASE` without corrupting ordinary text.
- [ ] Mask a key split across `text_delta` chunks, and a key holding `"` in `tap`.
- [ ] Redact the `probe` error detail in `detect()`.

## Interface

- [ ] Use a per-request sequence in `refreshProviders`, so overlapping refreshes keep the newest answer.
- [ ] Guard `load()` against overwriting a newer selection.
- [ ] Remove absolute paths from the `file://` links in Antigravity answers.
- [ ] Remove the absolute key-file path from the corrupt-store refusal.

## Repository

- [ ] Decide whether to keep the `.atl/*` local changes, which are tooling files and were not committed.
- [ ] Remote push: nothing was pushed. `main` is local only.
