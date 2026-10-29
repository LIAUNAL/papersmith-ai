# Language surfaces: English repository and artifacts, ES/EN dashboard, reply-language rule

Objective: every repository document and artifact is English; the dashboard can be shown in English or Spanish from a selector; the smith agent in the dashboard CLI panel replies in the language the user writes in, while skills, agents, artifacts and internal interactions stay English.
Branch: `feat/language-surfaces` (from main 56b5e857, v0.40.0 + docs). Delivery: release 0.41.0. Python: `~/Documents/papers_smith/papersmith-ai/.micromamba/envs/papersmith/bin/python`, `PAPERSMITH_KIT_ROOT=$PWD PYTHONPATH=$PWD/src`. Never run npm.

## Specs

- S0. Operator request, verbatim (2026-10-29): "borra ramas o worktrees ya mergeados, corrige o mergea las alertas de dependabot. luego, ajusta el proyecto, para que toda la documentacion, readme, y demas esten en ingles, y genera un boton o selector en el smith ui tablero, para que la informacion del tablero se pieda presentar en español o en ingles. ademas, asegurste de que el agente smith del cli abako a la derecha respondar en español o ingles segun lo que interactue con el usuario. los artefsctos, skills, agentes defindios y sus interacciones interneas siempre sersn en ingles"
- S1. "toda la documentacion, readme, y demas esten en ingles": every shipped document is English (the two root `MANTENIMIENTO-*.md` translated and renamed; `README.es.md` removed; Spanish strings in generators and projected doctrine translated). Exceptions that stay: verbatim operator quotes in `odd/tasks/` (provenance), accent-folding examples and vocabulary data in skills/docs, `docs/diagrams/locales/es.json`, and the dashboard's Spanish catalogue (S2). A repo-wide guard test enforces this with that explicit allowlist.
- S2. "un boton o selector en el smith ui tablero, para que la informacion del tablero se pieda presentar en español o en ingles": the dashboard served at `/` (`skills/_core/command_center/static/index.html` and its panels) has an EN/ES selector in the header; English is the default; the choice persists across reloads; every visible UI string, including labels the Python server returns, renders in the selected language; `<html lang>` follows it.
- S3. "el agente smith del cli abako a la derecha respondar en español o ingles segun lo que interactue con el usuario": the agents launched in the dashboard CLI panel (claude, opencode, pi; and the headless tutors) carry an instruction to reply in the language the user writes in.
- S4. "los artefsctos, skills, agentes defindios y sus interacciones interneas siempre sersn en ingles": the same doctrine states that skills, agent definitions, delegations between agents, and every generated artifact (code, docs, papers' internal files, commits) are English regardless of the conversation language; projections stay in sync (`scripts/sync-repo-harness.py --check`).

## Tasks

- T1 (S1, S3, S4) docs to English, doctrine rule in the projection source and tutors, language guard -- pending
- T2 (S2) dashboard i18n: catalogue, selector, panels and server labels -- pending
- T3 independent verification and release 0.41.0 -- pending

## Log

- L1 (2026-10-29): exploration found `/` serves the vanilla `static/index.html` (lang="es", about 99 Spanish text nodes, about 180 accented strings in 10 panel scripts); the React app in `ui/` is not loaded by `/`. No i18n library. Server labels in Spanish: `phase_actions.py:29`, `run_options.py:211`, `terminal.py:260-266` descriptions. Precedent: `/api/section-translation` serves Spanish copies of English contracts. No shipped doctrine on reply/artifact language; the panel launches bare `claude`/`opencode`/`pi` argv in the workspace, which load `CLAUDE.md`/`AGENTS.md`/`OPENCODE.md`/`.pi/APPEND_SYSTEM.md`.
