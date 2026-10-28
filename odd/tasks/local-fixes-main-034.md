# Local fixes on main 0.34.0
Objective: selectively integrate missing local behavior on `e6a8c42a`; branch `integrate/local-fixes-main-034`; delivery `feature-branch-chain`, no publishing or merging authorized.
Runner: existing repository micromamba Python/pytest, `npm run test:all`, `npm run typecheck`; original checkout stays untouched.

## Specs
- S1: "si" — accepted the comparison-first proposal: "Arrancamos con la comparación, sin hacer merges, push ni borrar ramas hasta tener el diagnóstico".
- S2: "eso, sigue" — continue the proposed selective integration after the diagnosis, preserving local work. Original outcome: "si los cubren, dejar con lo que hay en main actualizado, sino acoplar a ese neuvo main y mergear y pushear". Assumption: current stage prepares and verifies integration only; merge/push remain a later decision.
- S3: "esto qcreo que es mio y no de la forja pi-web-access de .pi/settings.json: ignora o como resolvemos??" followed by "eso, sigue" — accepted excluding that settings change, keeping the new main's file unchanged.
- S4: Delivery choice: "Cadena sobre una rama de integración (recomendada)" (`feature-branch-chain`); shape selection does not authorize publishing.

## Tasks
- T1 [S2-S4] delegated, done: port remaining smoke-runtime readiness behavior from `5d81d086`, retaining upstream priority; Risk: item 5 (runtime selection); commit: this unit (identity recorded in next log update). RED: 6 failed; GREEN: 7 passed; independent verify PASS.
- T2 [S2-S4] delegated, in_progress: port same-work bibliography metadata refresh from `26d22274`, retaining upstream citation-command vocabulary; commit: pending.
- T3 [S2-S4] delegated, pending: port vocabulary/privacy guard repair from `83427a6a`, preserving upstream tests; Risk: item 2 (privacy test guards); commit: pending.
- T4 [S2-S4] delegated, pending: port multi-folder citation evidence from `adeb1e79` excluding `.pi/settings.json`, with dependent all-root vocabulary scan `506c8c00`; commit: pending.
- T5 [S2-S4] delegated, pending: port cited-only bibliography `d42620b8`, preserving upstream expanded citation parsing; commit: pending.
- T6 [S2-S4] delegated, pending: port introduction 4a prior-work citation allowance `96681cf0`, including translated contract and provenance; commit: pending.
- T7 [S1-S4] inline, pending: full suite, typecheck, per-unit assessment/review where due, original-tree/settings preservation, and integration report; commit: pending.

## Log
L1: Original user request: "antes arracnar con las tareas que tenemos pendietes, debemos hacer unas csas, haycambios en el main de la forja, la idea es mirar si esos cambios cubren los arreglos que estan la o las ramas en local, si los cubren, dejar con lo que hay en main actualizado, sino acoplar a ese neuvo main y mergear y pushear, cómo lo ves? es el orden correcto?"
L2: 2026-10-28 diagnosis: all 10 local branches form one chain ending `96681cf0`; 11 exclusive commits. Main already covers exact artifact casing `927b7d17` and mathematical Unicode `7a0cce49`; do not port those. Smoke selection is partially covered. Six other behaviors remain missing. Tracking-only commits are historical, not behavior.
L3: User: "esto qcreo que es mio y no de la forja pi-web-access de .pi/settings.json: ignora o como resolvemos??"; accepted proposal: keep `.pi/settings.json` from upstream, do not port local package removal. User: "eso, sigue".
L4: User selected "Cadena sobre una rama de integración (recomendada)". Forecast roughly 1,400 authored changed lines including existing regression tests; keep cohesive per-behavior slices (refresh alone is about 459 lines, do not compress tests to fit a heuristic). No PR/push/merge currently authorized.
L5: Created and registered clean same-clone worktree `.worktrees/local-fixes-main-034` at `e6a8c42a801a79fb40413e66d1f6f3501abe6525`. Original branch `fix/mm31-citation-evidence` remains at `96681cf0` with 20 model overrides and 25 untracked entries untouched (plus the new integration worktree container). Context backstop requires delegation of bounded implementation units. Workers do not commit; parent verifies and commits reviewable work units.
