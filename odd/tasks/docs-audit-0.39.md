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
- L1 (2026-10-29, T1 inventory, read-only explore): counts OK (26 agents, 18 skills, install line v0.39.0, `model: sonnet` on 3 agents documented). Gaps: `preflight` (flags incl. `--deadline-block`, `--unit`) and `generate-jobs` (incl. 0.39 options) absent from docs/skills.md and docs/cli.md; `generate-job --dataset` + `DATASET_*`/`WORKSPACE_WITHOUT_DATASET` codes absent from docs; `STEP_*`, `SCHEDULE_*`, `STEPS_UNREADABLE`, `JSON_NEEDS_ACCOUNT` to confirm in the remote-execution refusal table and mirror in docs/skills.md; docs/skills.md:~1855 says the adapter seam has "exactly six operations" without the optional hooks (`interpreter_check`, `account_check`, `accelerator_request`, `INPUT_DATASETS_HOST`, `CARRY_UPLOAD`); kaggle-accounts `validate --account --json` absent; Colab continuation (`carry: uploaded`, `carry: no-share`/`carryWarning`) absent; `remaining` row lacks `unknown`/`refetch`; docs/skills.md has no section for `remote-parallelism` (plan, schedule, quota weeks, `measureFirst`, timing probe, schema 2) nor for `experiments-tutor` (also missing pre-0.37: datasets, experiment-diagrams, hyperparameter-search, math-tutor); dashboard per-candidate run options absent from docs/cli.md; `src/papersmith/core/colab.py:5-8` docstring says 0.7.5 while `PINNED_VERSION = "0.6.0"` (confirm); optuna/matplotlib are target-side dependencies (refused `optuna-missing`), undocumented in requirements.txt; google-colab-cli is a `uv tool`, not a Python dependency (say so). Unverified: stage references and tutor gitignore entries in docs.
- L2 (2026-10-29, T3, parent): `gh release view` bodies of v0.37.0, v0.38.0 and v0.39.0 match their CHANGELOG sections (whitespace-insensitive diff: no difference). The repository has no description and no topics.
