# generate-jobs options: generate every remote job in one call without falling back to generate-job

Objective: `remote_cli generate-jobs` expresses everything a real project's jobs need, so a campaign never has to regenerate jobs one by one.
Branch: `feat/generate-jobs-options` (from `origin/main` 1392aed0, v0.38.0). Delivery: with release 0.39.0. Tests: `~/Documents/papers_smith/papersmith-ai/.micromamba/envs/papersmith/bin/python -m pytest -q -n 6`.

## Specs

- S0. The operator's request, verbatim (2026-10-29): "puedes resolver 2 para mejorar smith?", where 2 was: "`generate-jobs` (0.38.0) no alcanza para estos jobs. No expresa los kwargs de smoke por job, la ruta extra `Results/checkpoints` ni `--input-dataset`, y además regeneraría el job ya terminado de e5. Los cuatro jobs se regeneran uno por uno con `generate-job --regenerate`, y e5 no se toca. Lo anoté como mejora para smith."
- S1. Per-job smoke kwargs: a remote `__steps__` entry may declare its own smoke kwargs (and smoke module/function/required evidence) that `generate-jobs` uses for that job; the CLI gains `--smoke-kwargs-for <step> '<json>'` (repeatable) that wins over the step's declaration; the global `--smoke-kwargs` still applies to every job without its own. A `{"steps": [<job>]}`-style per-job value is expressible.
- S2. Extra carry paths: a step may declare carry paths beyond its `produces`; the CLI gains `--carry-path-for <step> <path>` (repeatable). Carry paths are still validated exactly as `generate-job --carry-path` validates them.
- S3. Input datasets: `generate-jobs` accepts `--input-dataset <owner/slug>` (repeatable, every job of a service that attaches inputs) and `--input-dataset-for <step> <owner/slug>`, recorded exactly as `generate-job --input-dataset` records them (no `datasetChecks` unless `--dataset` is also given).
- S4. Selection: `--only <step>` (repeatable) and `--skip <step>` (repeatable) choose which remote steps are generated; unknown step names are refused before anything is written; skipped steps are listed under `skipped` with the reason. Without them, behavior is today's.
- S5. Every job `generate-jobs` writes is byte-identical to what `generate-job` writes with the equivalent flags (test per option); existing `generate-jobs` calls without the new options produce identical output to v0.38.0. Docs (remote-execution SKILL "Every job at once", help text, refusal table), CHANGELOG `## Unreleased`.

## Tasks

- T1 (S1-S5) options + equivalence tests + docs -- implemented (L2), awaiting review
- T2 independent verifier (item 3: CLI and run-config contracts) -- pending

## Log

- L1 (2026-10-29, QMLEEG regeneration): `generate-jobs` 0.38.0 could not express per-job smoke kwargs (`{"steps":[<job>]}`), the extra carry path `Results/checkpoints` (e1/e2/e3), or `--input-dataset` (only `--dataset`, which adds `datasetChecks`), and it would regenerate `tools/colab/e5_run_end_to_end` (a finished remote step in `__steps__`); the four jobs were regenerated one by one with `generate-job --regenerate`.
- L2 (2026-10-29, T1): step keys `smoke` (`module`/`function`/`kwargs`/`requiredEvidence`, each optional, each winning over the command's smoke option) and `carry` (read by `job_plan.step_smoke`/`step_carry`, malformed -> that row `STEP_DECLARATION_MALFORMED`); flags `--smoke-kwargs-for` (JSON object, once per step, wins over both), `--carry-path-for`, `--input-dataset` (only jobs whose adapter declares `INPUT_DATASETS_ROOT`, per S3's wording), `--input-dataset-for` (any service), `--only`, `--skip` (`job_plan.select_steps`: `STEP_UNKNOWN` for a non-remote name, `STEP_SELECTION_CONFLICT` for only+skip on one step, a `--*-for` on a step left out, or an empty selection; both before any write). Tests: `tests/test_generate_jobs_options.py` (25): byte-identity against `generate-job` per option, and a v0.38.0 golden captured before the change (passed RED and GREEN). RED 23 failed / 2 passed (argparse: unrecognized arguments); GREEN 25 passed.
