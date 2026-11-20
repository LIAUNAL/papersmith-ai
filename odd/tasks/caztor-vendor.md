Bring Caztor's source into papersmith-ai so the pull request needs one repository.
Branch: papersmith-ai `pr/caztor-embed` (worktree ~/papersmith-ai-worktrees/pr-caztor-embed). Delivery: single-pr (user-chosen squash import). Runners: pytest (smith), vitest + tsc (caztor/).

## Specs

- S1. "para el pr debemos incluir y dejar todo en papersmith, porque resultarìa incomodo tener que bajar 2 repos": Caztor's source lives inside papersmith-ai under `caztor/`, and smith ui runs that copy without a second checkout.
- S2. History answered "Un solo commit (Recomendado)": Caztor enters as one squashed `git subtree` commit; its full history stays in CaozCompilator.
- S3. Assumption: one setup command installs Caztor's dependencies and builds its web app; the docs and the dashboard's unavailable message name it.
- S4. "hay que hacer que se instale al tiempo con papersmith, y que ahora al actualizarlo tambien aparezca": installing papersmith-ai (`pipx install`, `pip install`) brings Caztor, and updating it (`pipx upgrade`) brings the matching Caztor, with only `node` (and `tectonic` to compile) on the machine, no `npm install`.
- S5. Answered "asi me parece bien" to: the wheel stays as it is, and the first time the PDF tab opens smith downloads what is missing (tectonic, and node when Node 26 is absent) from their official releases, checked against a pinned SHA-256, kept in `~/.cache/papersmith/tools/`.

## Tasks

- [x] T1 [S1, S2] Import CaozCompilator `feat/smith-embed` as `caztor/` with `git subtree add --squash`. Route: inline. Commit: c6426a3d, 03a30882.
- [x] T2 [S1, S3] Sidecar locator: `CAZTOR_HOME`, else the `caztor/` folder of the papersmith checkout smith runs from; messages name the setup command. Tests. Route: inline. Commit: c2d18dbc, 6f5c5be2 (smith ui sets CAZTOR_HOME: the dashboard runs in the workspace env, which lacks papersmith).
- [x] T3 [S3] `npm run setup:caztor`, part of `npm run setup`; docs; CI job running Caztor's suite. Route: inline. Commit: c2d18dbc.
- [x] T4 Consolidation: full suites, kit rebuild, workspace upgrade, live check. Route: inline.
- [x] T5 [S4] Caztor builds its server into one file, `apps/server-local/dist/main.mjs`, that finds its web app, agents and guides from there. Route: inline.
- [x] T6 [S4] The wheel carries `papersmith/_caztor/` (server bundle, web app, agents, guides, licenses), built by `scripts/build-caztor.py` in publishing; smith ui runs the checkout's caztor/ when set up, else the packaged one. Route: inline.
- [x] T7 [S5] `caztor_tools.py`: PATH first (node >= 26), else the pinned release for the platform, SHA-256 checked, only the executable kept; the sidecar puts the programs' folders first on Caztor's PATH; the PDF tab says it is preparing. Route: inline. Risk: item 2 (downloads and runs executables), item 5 (dependencies).

## Log

- L1 (2026-11-20) "no, para el pr debemos incluir y dejar todo en papersmith, porque resultarìa incomodo tener que bajar 2 repos."
- L2 (2026-11-20) History answered "Un solo commit (Recomendado)". Caztor: 636 tracked files, ~78k lines, 312 commits; source branch `feat/smith-embed` at 505cbdc.
- L3 (2026-11-20) Verification: `npm run setup:caztor` installs and builds inside caztor/ (node_modules and dist stay ignored); Caztor 3546 tests green, tsc clean; smith Node 843/843; smith pytest -n 8 twice: 10521 passed with 43 failed + 8 errors, then 29 failed, different tests each run (test_paper_decisions, test_remote_execution, test_paper_contract, test_mcp_*); every one passes serially on this branch and on the base d1cc4292, so it is parallel-run flakiness, not this change.
- L4 (2026-11-20) Live: ~/papersmith-ai local/integration fast-forwarded to 6f5c5be2, `npm run setup:caztor` there, kit rebuilt, workspace upgraded (local fix 773f939 restored again), `smith ui` restarted; POST /api/caztor starts /home/andres/papersmith-ai/caztor on 4318; tutor switches render. CaozCompilator no longer runs.
- L5 (2026-11-20) "ya terminó? pero, hay que hacer que se instale al tiempo con papersmith, y que ahora al actualizarlo tambien aparezca". Users install with pipx (wheel), where caztor/ is absent. Caztor\'s server reads only three paths from its own location (web dist, agents/, guides/ + LICENSES); its runtime dependencies are hono and @hono/node-server, so a bundled server plus the built web app runs on node alone.
- L6 (2026-11-20) Verification: the bundle (`npm run build:server`, rolldown, 0.6 MB) runs from a copy with no node_modules and compiles a document; a wheel built with `pip wheel` (11 MB, 31 `_caztor/` files) installed into a clean venv resolves `ui.bundled_caztor()` to site-packages/papersmith/_caztor and the sidecar starts it and serves the page. Caztor 3546 tests green, tsc clean; caztor/publishing/doctor tests 51 passed (artifact tests skip without `python -m build`).
- L7 (2026-11-20) "y no puedes incluir ahi node y tecnonic de una vez? que tan pesado pasa a ser?" Measured: tectonic 24 MB (8 MB compressed); Node 26 ~120 MB (~40-45 MB compressed, official figures). Recommended download-on-first-use over per-platform wheels; answered "asi me parece bien".
- L8 (2026-11-20) Verification: real Node 26.13.1 and Tectonic 0.17.0 for linux-x64 fetched in 12 s, checksums matched, both run; the fetched tectonic compiles a document in 1.3 s with an existing TeX cache; the wheel-installed Caztor started by the sidecar with PATH=/usr/bin:/bin runs on the fetched node. A first compile on an empty HOME waits on Tectonic's own TeX package download (~25 KB/s from its server here), outside this change.
