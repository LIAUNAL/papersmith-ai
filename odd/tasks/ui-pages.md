# Read-only dashboard on GitHub Pages (/ui-github)

Objective: any workspace can publish a static, read-only snapshot of its dashboard to GitHub Pages with `/ui-github`, for viewing only: no server, no terminal, no agent, no phase execution.
Branch: feat/ui-pages (worktree ../papersmith-ai-worktrees/ui-pages). Delivery: ask-on-risk. Test runner: pytest (`.micromamba/envs/papersmith/bin/python -m pytest`) and Playwright (`cd ui; PYTHONPATH=../src:.. npx playwright test --project=shipped`).

## Specs

- S1 "explora si podemos desplegar el tablero ui de cada paper en githubpages solo para fines de visualizacion, sin cli agente sctivo no posibilidad de ejecucion de fases, solo para visualizar."
- S2 "planea la opcion, implementa para que sea posible y desplegarse mediante comando /ui-github"
- S3 "verifica, actualiza, comit mergea push release, actualiza qmleegv2 y despliega el tablero en githubpages como prueba"
- S4 (design decision, privacy) A Pages site is public even for a private repository on GitHub Pro: the snapshot carries no AI conversations, team accounts or emails, credential status, absolute paths or the operator's PDF annotations; only an allow-list of workspace files is copied.

- S5 "ajusta para que el historial de ia tambien se pueda llevar a github pages, pero sin revelar correos, nombres, claves, tokens o cualqier cosa que pueda vulnerar seguridad, y el comando debe traer una bandera para indicar si quiere o no desplegar la pagina con historial de ia, por defecto debe estar en true" — supersedes S4's exclusion of AI conversations: they are included by default, scrubbed; a flag turns them off.

## Design

- `smith ui export --static <dir>` builds the snapshot: the shipped `static/` assets, plus every read-only GET the dashboard makes, answered in-process by `create_app(root, history_store=None, enable_terminal=False)` with the AI-archive sync patched out (`/api/status` via `app.state.status_payload`), for `en` and `es`, written as files and indexed in `snapshot/manifest.json` (request key → file, content type). Dynamic parameters are enumerated from the snapshot's own answers (citation ids, venue slugs, QA pages, artifact paths). Excluded: `/api/ai-history*`, tutor and terminal routes, `/api/doctor`; scrubbed: absolute root and home paths, team/accounts/credential fields of `/api/experiments`.
- A shim (`static/snapshot.js`, loaded right after `i18n.js` only in the export) maps every `/api/...` fetch, iframe/img/link URL and `pdfUrl()` to the snapshot file, answers non-GET with 403 `STATIC_SNAPSHOT`, makes `sendToCli` and phase runs no-ops, hides execution controls (`body.ps-static`) and shows a "read-only snapshot of <date>" banner. All URLs become relative so the site works under `/<repo>/`.
- `smith ui pages [dir]` publishes the export to the `gh-pages` branch of the workspace's `origin` (orphan commit, force-pushed), enables Pages from that branch with `gh api` when needed and prints the URL. The `ui-github` skill (slash command `/ui-github`) runs export then publish, after the operator confirms the public URL.

## Tasks

- [x] T1 [S1, S4, S5] static export + shim + read-only UI + masked AI history, with tests — delegated (context backstop) — 2d369aa1, b953c522
- [x] T2 [S2, S5] `smith ui --publish-pages` + `ui-github` skill + docs, with tests — delegated (context backstop) — dc0126dc
- [x] T3 [S3] verify, commit, merge, push, release; upgrade qmleegV2; deploy its dashboard — inline (0.68.0, qmleegV2 upgraded, Pages live)

## Log

- L1 (2026-11-08) "ahora, explora si podemos desplegar el tablero ui de cada paper en githubpages solo para fines de visualizacion, sin cli agente sctivo no posibilidad de ejecucion de fases, solo para visualizar. planea la opcion, implementa para que sea posible y desplegarse mediante comando /ui-github , verifica, actualiza, comit mergea push release, actualiza qmleegv2 y despliega el tablero en githubpages como prueba"
- L2 Evidence: amalvarezme is on GitHub Pro, so Pages works from the private qmleegV2 repo, but the site is public. The dashboard map (explorer): one fetch hook in i18n.js; root-absolute /api URLs; iframes, img, links and PDF.js bypass fetch; server-side es translation of several JSON routes and three HTML views; /api/status and /api/ai-history write (archive sync); /api/artifact serves any file; existing `--export-static` copies assets only.
- L3 (2026-11-08) "pon el repo de qmleegV2 publico, pero manten las restricciones de seguridsd para no exponer correos, chats, tokens etc" — operator chose "Purgar y publicar": .papersmith/ai-history purged from qmleegV2 history with git filter-repo and gitignored (kept on disk), the corresponding-author email redacted from old blobs, history rescanned (no emails or tokens), force-pushed, repo public. Backup ~/Documents/qmleegV2-before-public-2026-11-08.tar.gz.
- L4 (2026-11-08) "ajusta para que el historial de ia tambien se pueda llevar a github pages, pero sin revelar correos, nombres, claves, tokens o cualqier cosa que pueda vulnerar seguridad, y el comando debe traer una bandera para indicar si quiere o no desplegar la pagina con historial de ia, por defecto debe estar en true"
- L5 T1 done: `smith ui --export-snapshot <dir> [--snapshot-lang en,es] [--ai-history|--no-ai-history]` (AI history on by default, masked by ai_archive.redact_public); shipped Playwright 64 passed; qmleegV2 trial export 28 MB, 0 hits for author names, emails, home paths or tokens; guidance/ excluded; novelty viewer write turned off during export. Operator decision (2026-11-08) on the PDF: "Incluir el PDF" — paper/main.pdf and figures are published as they are.
- L6 T2 done: `smith ui [dir] --publish-pages [--pages-branch gh-pages] [--pages-remote origin] [--yes] [--no-ai-history]`; orphan commit built with a temporary GIT_INDEX_FILE and force-pushed; Pages enabled with gh api (404 → POST, other source → PUT); 15 publish tests; dry run against a local bare repo published 305 files.
- L7 T3 done: #169 merged (CI fix 0d10dfe2: no project/platform names in kit code), 0.68.0 released (GitHub + PyPI), installed; qmleegV2 upgraded and pushed; `smith ui --publish-pages --yes` pushed gh-pages 9e3cc3c1c0fa, site https://amalvarezme.github.io/qmleegV2/ serves 200 with data (r04, 34-page PDF); scan of the published branch: no real emails, names, tokens or home paths (only template third.author@ addresses and the bare KGAT_ prefix in help text).
