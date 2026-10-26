# cloud-placement-and-poc-budget
Objective: two general placement rules in the papersmith flow — a run whose local estimate exceeds 20 minutes goes to a cloud host (Colab or Kaggle), and a proof of concept is sized to at most 5 hours — enforced in the estimate verb, the dashboard's run options, the doctrine and the agents.
Branch: feat/cloud-placement-and-poc-budget · Delivery: single merge (merge, push and release are the operator's decision) · Runners: `.micromamba/envs/papersmith/bin/pytest -n 8 --dist loadfile`, `npm test`.

## Specs

- S1 (cloud over 20 min): "considera pruebas siempre en nube, colab o kaggle, si en local tardan mas de 20 min. reajusta dicja regla para el fluko general de smith".
- S2 (PoC budget): "la prieba de cocbepto no debera tardar mas de 5 h, ajusta dicha regla en el flujo de smith generla".
- S3 (QMLEEG E5): "plantea la mejor opcion para estad pruebas" — a recommendation to the operator, no code.
- Context (user, same message): "la cuenta de colab andresmarino07@gmail.com es pro" — already recorded as `colab tier pro` in QMLEEG's team; nothing to change.
- Assumption: both limits read the estimate's upper bound (+20%), so a run is placed by the conservative end of its range.

## Tasks

- T1 [S1,S2] `estimate` reports a placement verdict per stage (local limit 1200 s, PoC budget 18000 s) + SKILL.md + tests — route: inline — pending
- T2 [S1,S2] dashboard run options: 20-minute local limit for both stages, PoC budget warning, panel note + tests — route: inline — pending
- T3 [S1,S2] doctrine (proposal-implementation, experimental-implementation, experimental-deliberation), walk/build agents, paper-flow template, projections, suite — route: inline — pending

## Log

- L1 (2026-10-25, user verbatim): "la cuenta de colab andresmarino07@gmail.com es pro, considera pruebas siempre en nube, colab o kaggle, si en local tardan mas de 20 min. reajusta dicja regla para el fluko general de smith, y plantea la mejor opcion para estad pruebas. la prieba de cocbepto no debera tardar mas de 5 h, ajusta dicha regla en el flujo de smith generla"
- L2 Map: `estimate` (parallelism_cli.py:519) has no threshold; run_options.py:42 `LOCAL_POC_LIMIT = 30*60` applies to PoC only; doctrine sections in the two implementation skills must not name a service (tests/test_estimate_doctrine.py::test_the_sections_name_no_service).
