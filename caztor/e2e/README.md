# Browser checks (opt-in)

Real-browser checks that jsdom cannot do. They are not part of `npx vitest run`.

Requirements: the web app built (`npm run build -w @caztor/web`) and Playwright with a Chromium installed somewhere on
the machine. Point `CAZTOR_PLAYWRIGHT` at its `index.mjs` (or the package folder); add `LD_LIBRARY_PATH` if the
browser needs libraries from a non-standard place.

```sh
CAZTOR_PLAYWRIGHT=/path/to/node_modules/playwright/index.mjs node e2e/dialog.mjs
```

- `collaborators.mjs`: sharing on loopback under the public name `localhost:<port>`, with a throwaway configuration folder: the host link, invite previews that sign no one in, an invite link opened from another site and its access key typed on the sign-in page (wrong first, then right), the collaborator's own page token and view, the key on a second browser, the dialog's expiry display, revoking one key and revoking the person.
- `dialog.mjs`: Tab, Shift+Tab and focus after a confirmed delete.
- `compile.mjs`: compile, cancel, zoom and scroll kept across a recompile, auto-compile, the out-of-date mark, persisted switches and the watcher after the app's own save (uses the real tectonic with a cached bundle; screenshots go to `$CAZTOR_E2E_OUT`).
- `chat.mjs`: the chat against the real server with scripted fake providers (no tokens): streaming, tool cards, changed files, undo with each of the three choices, stop, an error card, an unavailable provider, the other provider, history after a reload and the logo text fallback. Screenshots of the full app with a finished turn (light and dark) go to `$CAZTOR_E2E_OUT`. With `CAZTOR_E2E_REAL=1` it makes exactly two real Claude Code turns instead (one edit, then undo) and spends tokens. With `CAZTOR_E2E_PROVIDER=opencode CAZTOR_E2E_MODEL=<provider/model>` the real turns are opencode's (an edit and a continuation of the session, then undo; `CAZTOR_E2E_TURNS=1` makes only the edit). `CAZTOR_E2E_ARGV_LOG=<file>` records every spawn (argv and variable names).
