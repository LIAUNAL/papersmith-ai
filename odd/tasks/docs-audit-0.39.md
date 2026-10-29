# Docs audit 0.37-0.39: every change since 0.36.0 is documented in the README, docs and GitHub

Objective: a reader of the README, docs/, requirements, the skill and agent documentation and the GitHub releases learns every user-visible change shipped in 0.37.0, 0.38.0 and 0.39.0, with no stale statement left.
Branch: `docs/audit-0.39` (from `origin/main` 0ab5cecd, v0.39.0). Delivery: patch release 0.39.1 if anything shipped changes, else docs-only commit on main. Tests: `~/Documents/papers_smith/papersmith-ai/.micromamba/envs/papersmith/bin/python -m pytest -q -n 6`.

## Specs

- S0. The operator's request, verbatim (2026-10-29): "despues de lanzar los experimentos de qmleeg, revisa el readme de smith y requirements, la documentacion de agentes, skills, etc, que todo lo que hemos actulizado hasta este realice este docuementado en github y readme"
- S1. Inventory every user-visible change in CHANGELOG 0.37.0, 0.38.0 and 0.39.0 (commands, flags, refusal codes, dashboard features, agents, skills, models, doctrine rules, dependencies) and, for each, the place a reader would look for it: README sections, docs/cli.md, docs/skills.md, docs/harness-support-matrix.md, docs/mcp.md, docs/releasing.md, each skill's SKILL.md and references, agent files, `--help` output.
- S2. Fix every gap or stale statement found (missing command/flag/agent in README or docs; old version numbers in install lines; counts of agents/skills/commands; requirements.txt and package pins matching what the code imports, e.g. the Colab CLI, kagglesdk, optuna; harness projections in sync). No behavior change.
- S3. GitHub: the release notes of v0.37.0, v0.38.0 and v0.39.0 match their CHANGELOG sections (fix with `gh release edit` if they differ); the repository description/topics mention nothing stale.
- S4. Report the inventory as a table (change -> where documented -> status) in the Log.

## Tasks

- T1 (S1, S4) inventory -- pending
- T2 (S2) fixes -- pending
- T3 (S3) GitHub release notes check -- pending

## Log
