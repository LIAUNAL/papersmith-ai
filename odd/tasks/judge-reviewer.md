# Judge-reviewer: no venue name in the flow

Objective: the dashboard, the skills, the agents, the docs and every generated artifact name the reviewing judge "judge-reviewer" (Spanish UI: "juez-revisor") and never "NeurIPS".
Branch: feat/judge-reviewer. Delivery: ask-on-risk. Test runner: pytest (`.micromamba/envs/papersmith/bin/python -m pytest`) and node tests.

## Specs

- S1 "ajusta el flujo para que no se mencione el termino neurips en ninguna parte del tablero o de los artefagtos o en la definicion de skills o agentes, simplemente aue se llame agente juez-revisor (o la mejor traduccion que encuentres al ingles)"

## Tasks

- [x] T1 [S1] rename identifiers (step id neurips_review → judge_review, NEURIPS_JUDGE_OWED → JUDGE_REVIEW_OWED, i18n keys) and every user-facing and agent/skill text; tests follow — inline

## Log

- L1 (2026-11-08) "ajusta el flujo para que no se mencione el termino neurips en ninguna parte del tablero o de los artefagtos o en la definicion de skills o agentes, simplemente aue se llame agente juez-revisor (o la mejor traduccion que encuentres al ingles)"
- L2 Evidence: 203 occurrences in 40 tracked files (skills/_core 14, agents ×4 mirrors, skills ×5, docs, CLAUDE.md and mirrors, tests). Workspace data stores no "neurips" key (qmleegV2: only ai-history and ingested PDFs), so the identifiers rename without a data migration. English name chosen: "judge-reviewer".
- L3 T1 done: every tracked mention renamed (agents ×4 mirrors, skills, dashboard, i18n, docs, CLAUDE.md and mirrors, tests); harness projection clean; related suites: only the failures main already has.
