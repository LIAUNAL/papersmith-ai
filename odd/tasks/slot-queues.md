# Slot queues: one session runs a queue of units instead of one unit per slot

Objective: a campaign with more units than an account's concurrent slots places every unit in one launch, as a queue per session that fits the session margin, instead of leaving the rest unplaced for later campaigns.
Branch: `feat/slot-queues` (from `origin/main` 0ab5cecd, v0.39.0). Delivery: release after verification. Tests: `~/Documents/papers_smith/papersmith-ai/.micromamba/envs/papersmith/bin/python -m pytest -q -n 6`.

## Specs

- S0. The operator's choice, verbatim (2026-10-29): "Tandas ahora (recomendado)", whose description read: "Reconcilio la escalera y lanzo 4 subestudios ya (fold1/2 -a y -b); yo encadeno las tandas 2 y 3 con `remaining`, abriendo su compuerta con esta misma autorización. En paralelo mejoro smith para que una sesión pueda llevar varias unidades."
- S1. `distribute` (and `submit --unit` in campaign mode) places every unit: units beyond the granted slots join per-slot queues, balanced by the measured per-unit estimate when a timing record exists (else by count), so each slot's queue fits the service's session margin (80% of the session limit, with setup per session counted once); a queue that cannot fit is split into chained sessions on the same account (the session-chain rule) rather than left unplaced. Units are never duplicated across slots.
- S2. The runner and `FORGE_RUN_UNITS` carry the whole queue for a slot (the target runs the units in order and writes `partial.json` with what remains, as today); `remaining` and continuation work per slot exactly as for one-unit shares.
- S3. The consent token and gate bind the full unit list and its placement (slot -> queue), so a launch whose placement differs from the gated one is refused; existing one-unit-per-slot campaigns (units <= slots) produce byte-identical placements and records to v0.39.0.
- S4. `schedule`/`plan` report the same placement (`queues` per account/slot) and makespan as `distribute` would launch.
- S5. Docs (remote-execution and remote-parallelism SKILLs, help text), CHANGELOG `## Unreleased`; doctrine names no service.

## Tasks

- T1 (S1-S3) queued placement in packer/distribute/submit + runner units + gate binding + tests -- pending
- T2 (S4, S5) schedule/plan agreement + docs -- pending
- T3 independent verifier (items 3, 5: gate/consent binding, remote launches) -- pending

## Log

- L1 (2026-10-29, QMLEEG HPO launch): `packer.distribute()` asks each worker for `requested=len(units)`, clamped to the Kaggle cap 2; `slot_shares()` makes one job per granted slot; in campaign mode no flag limits a worker to one slot (`--requested` only for single sends; `--worker` excludes `--unit`); places are capped at the sum of granted slots, so 10 HPO sub-studies on two accounts launched as 4 one-unit sessions with 6 unplaced.
