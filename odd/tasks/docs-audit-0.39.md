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

- T1 (S1, S4) inventory -- done (L1, table in L3)
- T2 (S2) fixes -- done (L3)
- T3 (S3) GitHub release notes check -- pending

## Log
- L1 (2026-10-29, T1 inventory, read-only explore): counts OK (26 agents, 18 skills, install line v0.39.0, `model: sonnet` on 3 agents documented). Gaps: `preflight` (flags incl. `--deadline-block`, `--unit`) and `generate-jobs` (incl. 0.39 options) absent from docs/skills.md and docs/cli.md; `generate-job --dataset` + `DATASET_*`/`WORKSPACE_WITHOUT_DATASET` codes absent from docs; `STEP_*`, `SCHEDULE_*`, `STEPS_UNREADABLE`, `JSON_NEEDS_ACCOUNT` to confirm in the remote-execution refusal table and mirror in docs/skills.md; docs/skills.md:~1855 says the adapter seam has "exactly six operations" without the optional hooks (`interpreter_check`, `account_check`, `accelerator_request`, `INPUT_DATASETS_HOST`, `CARRY_UPLOAD`); kaggle-accounts `validate --account --json` absent; Colab continuation (`carry: uploaded`, `carry: no-share`/`carryWarning`) absent; `remaining` row lacks `unknown`/`refetch`; docs/skills.md has no section for `remote-parallelism` (plan, schedule, quota weeks, `measureFirst`, timing probe, schema 2) nor for `experiments-tutor` (also missing pre-0.37: datasets, experiment-diagrams, hyperparameter-search, math-tutor); dashboard per-candidate run options absent from docs/cli.md; `src/papersmith/core/colab.py:5-8` docstring says 0.7.5 while `PINNED_VERSION = "0.6.0"` (confirm); optuna/matplotlib are target-side dependencies (refused `optuna-missing`), undocumented in requirements.txt; google-colab-cli is a `uv tool`, not a Python dependency (say so). Unverified: stage references and tutor gitignore entries in docs.
- L2 (2026-10-29, T3, parent): `gh release view` bodies of v0.37.0, v0.38.0 and v0.39.0 match their CHANGELOG sections (whitespace-insensitive diff: no difference). The repository has no description and no topics.
- L3 (2026-10-29, T2 fixes and S4 inventory; scope widened by the operator to 0.37.0-0.40.0): every L1 gap fixed, docs-only (no behavior change; `src/papersmith/core/colab.py` changes its docstring only). Inventory:

| Change (release) | Where a reader finds it | Status |
|---|---|---|
| `preflight` and its checks, flags incl. `--unit`, `--deadline-block`, `--candidate`, repeatable `--entrypoint` (0.37, 0.38, 0.39) | README "Jobs checked before they run"; docs/cli.md `smith remote`; docs/skills.md 8 (commands table, "Before the first rehearsal") | fixed |
| `generate-jobs`, all flags incl. 0.39 `--smoke-kwargs-for`, `--carry-path-for`, `--input-dataset[-for]`, `--only`, `--skip`, step `smoke`/`carry` (0.37, 0.39) | README; docs/cli.md `smith remote`; docs/skills.md 8 ("Every job at once") | fixed |
| `generate-job --dataset`, `--workspace`, `DATASET_*`, `DATASETS_SKILL_MISSING`, `WORKSPACE_WITHOUT_DATASET` (0.37) | README; docs/cli.md; docs/skills.md 8 ("Job inputs", refusal table), 13 | fixed |
| `STEPS_UNREADABLE`, `SCHEDULE_UNREADABLE`, `SCHEDULE_IS_A_PLAN`, `STEP_UNKNOWN`, `STEP_SELECTION_CONFLICT`, `STEP_DECLARATION_MALFORMED`, `CARRY_WORKER_MISMATCH`, `PLACEMENT_NOT_CONSENTED` (0.37-0.40) | confirmed in `skills/remote-execution/SKILL.md` "Refusal codes"; mirrored in docs/skills.md 8 | fixed |
| `JSON_NEEDS_ACCOUNT`, `validate --account <username> --json` (0.37) | a kaggle-accounts code, not remote-execution (confirmed in `accounts_cli.py` and its SKILL.md); README Kaggle bullet; docs/skills.md 7 | fixed |
| Adapter seam: six abstract operations plus optional capabilities and the preflight hooks `interpreter_check`, `account_check`, `accelerator_request` (0.37, 0.39) | docs/skills.md 8 modules table | fixed (was "exactly six operations" alone) |
| Colab continuation `carry: uploaded`, `CARRY_UPLOAD`; `carry: no-share` + `carryWarning`; two-layout restore (0.39) | README "Runs longer than one session"; docs/skills.md 8 ("Continuations carry their checkpoints") | fixed |
| `remaining` `unknown` + `refetch` (0.39) | docs/skills.md 8 commands table; docs/cli.md | fixed |
| Slot queues, `queues`/`sessionFit`, `done`/`inFlight`, two-part token `<campaign>.<placement>`, lowest free slot per share, `schedule`/`plan` `queues` and `queueMakespanMinutes` (0.40) | README "Campaigns larger than the pool"; docs/cli.md; docs/skills.md 8 ("Slot queues", distribute row), 16 | fixed |
| `remote-parallelism` `plan`, `schedule`, quota weeks, `--resumable`, `measureFirst`, timing probe, schema 2 (0.38, 0.39) | README "Placement by measurement" (already); docs/skills.md 16 (new) | fixed |
| `experiments-tutor` skill, agent, routes, thread (0.38) | README rows 6b and agents (already); docs/cli.md (already); docs/skills.md 18 (new) | fixed |
| Pre-0.37 skills missing from the tour: `datasets`, `experiment-diagrams`, `hyperparameter-search`, `math-tutor` | docs/skills.md 13, 14, 15, 17 (new, brief) | fixed |
| Dashboard per-candidate run options and the recorded plan's pick (0.38) | docs/cli.md `smith ui` "Run options" | fixed |
| Tutor gitignore entries `.papersmith/math-tutor/`, `.papersmith/experiments-tutor/` (0.38; L1 unverified) | were undocumented; README workspace `.gitignore` paragraph; docs/cli.md; docs/skills.md 17, 18 | fixed |
| Stage references `references/next-step-<nextStep>.md` (0.38; L1 unverified) | README (the agents section, `Stage reference:` paragraph) already documents them | verified, no change |
| `generate-job --accelerator-kind cpu` (0.38) | README "Placement by measurement" (already) | verified |
| `model: sonnet` on three agents (0.38) | README agents table (L1) | verified |
| optuna/matplotlib target-side (`optuna-missing`); Colab CLI a `uv tool` pinned 0.6.0 | requirements.txt closing comment | fixed |
| `colab.py` docstring "0.7.5" vs `PINNED_VERSION = "0.6.0"` | both written in 1a2726dc; not a deliberate comparison, a measurement note naming a version other than the pin. Docstring now names the pin and keeps the 0.7.5 measurement, citing the adapter's 0.6.0 record | fixed (docstring only) |
| README.es.md stale counts ("doce", "diecinueve") | count-free wording | fixed |
| docs/skills.md duplicate `---` before section 9 | removed | fixed |
| Install line v0.40.0, counts of agents/skills | README (L1, re-checked: v0.40.0) | verified |
