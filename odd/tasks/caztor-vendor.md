Bring Caztor's source into papersmith-ai so the pull request needs one repository.
Branch: papersmith-ai `pr/caztor-embed` (worktree ~/papersmith-ai-worktrees/pr-caztor-embed). Delivery: single-pr (user-chosen squash import). Runners: pytest (smith), vitest + tsc (caztor/).

## Specs

- S1. "para el pr debemos incluir y dejar todo en papersmith, porque resultarìa incomodo tener que bajar 2 repos": Caztor's source lives inside papersmith-ai under `caztor/`, and smith ui runs that copy without a second checkout.
- S2. History answered "Un solo commit (Recomendado)": Caztor enters as one squashed `git subtree` commit; its full history stays in CaozCompilator.
- S3. Assumption: one setup command installs Caztor's dependencies and builds its web app; the docs and the dashboard's unavailable message name it.

## Tasks

- [x] T1 [S1, S2] Import CaozCompilator `feat/smith-embed` as `caztor/` with `git subtree add --squash`. Route: inline. Commit: c6426a3d, 03a30882.
- [x] T2 [S1, S3] Sidecar locator: `CAZTOR_HOME`, else the `caztor/` folder of the papersmith checkout smith runs from; messages name the setup command. Tests. Route: inline. Commit: c2d18dbc, 6f5c5be2 (smith ui sets CAZTOR_HOME: the dashboard runs in the workspace env, which lacks papersmith).
- [x] T3 [S3] `npm run setup:caztor`, part of `npm run setup`; docs; CI job running Caztor's suite. Route: inline. Commit: c2d18dbc.
- [x] T4 Consolidation: full suites, kit rebuild, workspace upgrade, live check. Route: inline.

## Log

- L1 (2026-11-20) "no, para el pr debemos incluir y dejar todo en papersmith, porque resultarìa incomodo tener que bajar 2 repos."
- L2 (2026-11-20) History answered "Un solo commit (Recomendado)". Caztor: 636 tracked files, ~78k lines, 312 commits; source branch `feat/smith-embed` at 505cbdc.
- L3 (2026-11-20) Verification: `npm run setup:caztor` installs and builds inside caztor/ (node_modules and dist stay ignored); Caztor 3546 tests green, tsc clean; smith Node 843/843; smith pytest -n 8 twice: 10521 passed with 43 failed + 8 errors, then 29 failed, different tests each run (test_paper_decisions, test_remote_execution, test_paper_contract, test_mcp_*); every one passes serially on this branch and on the base d1cc4292, so it is parallel-run flakiness, not this change.
- L4 (2026-11-20) Live: ~/papersmith-ai local/integration fast-forwarded to 6f5c5be2, `npm run setup:caztor` there, kit rebuilt, workspace upgraded (local fix 773f939 restored again), `smith ui` restarted; POST /api/caztor starts /home/andres/papersmith-ai/caztor on 4318; tutor switches render. CaozCompilator no longer runs.
