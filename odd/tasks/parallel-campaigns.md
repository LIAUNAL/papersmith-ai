# Parallel campaigns over several accounts and services

Objective: when a project compares several methods and has several remote accounts (here one Colab Pro account and two Kaggle accounts of two team members), papersmith places and launches the work in parallel without breaking the reproducibility doctrine.
Branch: `feat/parallel-campaigns` (from `origin/main` 6a2c9d97, v0.30.2). Delivery: one release after integration; push, merge and release are the operator's. Tests: `pytest` from the main checkout's micromamba env, `npm test` with `node_modules` linked.

## Specs

- S0. The operator's request, verbatim (2026-10-27): "explora para que cuando debemos comparar varios metodos, y tenemos varias cuentas disponibles en colab y kaggle, se ajsuten y se manden en paralelo, como en este caso tenemos colab y dos de kaggle. explora y ajusta el flujo general de papersmith para ello, luego analiza como aca podemos aprovechar las tres cuentas al tiimpo para optimizar tiempos." The doctrine is kept: a campaign is split along seed/fold/subject blocks, never by arm (`axis-not-arm`); one campaign runs on one service unless the shards' environment stamps are declared identical and `verify --shards` confirms it (`one-service-per-campaign`); readiness is per worker (`rehearse-each-account`). Parallelism across services therefore happens between campaigns (steps), and within a campaign across accounts of its service.
- S1. One submission per granted slot (remote-execution). A worker whose capacity is 2 (Kaggle) gets up to two concurrent submissions, each carrying its share of the units, instead of one job running all of its units in sequence. Existing single-send and single-slot behaviour is unchanged.
- S2. Readiness per worker at the launch gate. A campaign's gate and submit refuse unless every worker the distribution will use has its own passing rehearsal at the current pin; the refusal names the workers that still need one.
- S3. Jobs are identified by (service, job). Two job folders with the same job name under different services no longer shadow each other in the engine's job lookup, readiness map and flow.
- S4. Concurrent launch of independent remote steps. The walk and `launch-plan` report every remote step whose inputs are already produced (its `reads` are satisfied by earlier steps' `produces`), so steps placed on different services can be launched at the same time, each through its own propose/offer/gate; a step that reads another's product waits for it.
- S5. Heterogeneous accounts in planning (remote-parallelism). `assess` takes per-service account limits (concurrent sessions, session wall-time, weekly quota) instead of one value for all accounts, and a planning verb assigns the project's remote steps to services and their units to that service's accounts so the overall makespan is minimal, respecting step dependencies and the doctrine; it reports the plan and its makespan against the serial one, and never launches.
- S6. The command center shows remote runs per worker (state, units, service) from the ledger.

## Tasks

- T1 (S1, S2 remote-execution side) delegated writer, worktree `parallel-campaigns-a` — pending
- T2 (S2 engine side, S3, S4) delegated writer, worktree `parallel-campaigns-b` — pending
- T3 (S5) delegated writer, worktree `parallel-campaigns-c` — pending
- T4 (S6) parent, after integration — pending
- T5 integration: merge A/B/C, seal/domain-lock/roster repins, docs, CHANGELOG, full suite vs baseline, independent verifier (gate and consent are high risk) — pending

Route evidence: Writer trigger (a) parallelism — three units with disjoint edit surfaces (remote-execution scripts; implementation engine; remote-parallelism), each heavier than a subagent start, launched together; and (b) the parent's long-session backstop.

## Log

- L1 (2026-10-27, user): "antes, explora para que cuando debemos comparar varios metodos, y tenemos varias cuentas disponibles en colab y kaggle, se ajsuten y se manden en paralelo, como en este caso tenemos colab y dos de kaggle. explora y ajusta el flujo general de papersmith para ello, luego analiza como aca podemos aprovechar las tres cuentas al tiimpo para optimizar tiempos. y ten cuidado que otra sesino acaba de hacer cambios de smith y esta sacando nueva release, asegurte de traer esos cambios y luego aplicar los tuyos"
- L2 (2026-10-27, user): "sí, una es de otro miembro del equipo" — QMLEEG's team.json lists one member (amalvarezme: Kaggle amalvarezme, Colab pro); the teammate's Kaggle account must be added by `smith team add ... --attest` and validated before it can be a worker.
- L3: Exploration (read-only) findings that ground S1-S6: distribute deals units round-robin and one job per worker runs its units serially (remote_cli.py:1257-1312); gate binds one entrypoint with worker=None (remote_cli.py:712-770); smokeReady keyed by job name and checks the latest smoke worker only (implementation_engine.py:11156-11218); _job_folder_named returns the first sorted match (17044-17054); walk_plan stops at the first launch (12702-12774); assess takes one set of account limits (parallelism_cli.py:265-290); assess refuses --axis arm (88, 279); dashboard has no per-worker runs (remote_services.py:259-284).
