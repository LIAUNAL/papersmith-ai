# Session limits, checkpoints and resume

Objective: no remote run loses hours of compute to a service's continuous-run limit or a reclaimed session: every unit fits a session with margin or checkpoints and resumes, and only the remaining units are sent again.
Branch: `feat/session-checkpoints` (from `feat/parallel-campaigns` e7d1ae83). Delivery: released together with parallel campaigns; push, merge and release are the operator's. Tests: pytest from the main checkout's micromamba env (`-n 6`), `npm test`.

## Specs

- S0. The operator's request, verbatim (2026-10-27): "ten en cuenta los tiempos de ejecucion continua que permite kaggle y colab, debes asegurarte de dejar checkpoints para no perder horas de proceso, y en caso tal partir los folds por sesiones o guardar checkpoints para continuar con nuevas horas de computo continuo. ajsuta esto en el flujo, como relga para los agentes desde papersmith, y aplicalo en qmleeg". Approved as phase 1 (2026-10-27: "sí, avanza con la fase 1 y autorizo la prueba en Kaggle").
- S1. Session limits declared by each adapter (continuous run time per session for its accelerator), not only typed by the user.
- S2. Session-fit check: a unit whose upper-bound duration plus setup exceeds 80% of its service's session limit is refused (or must be declared resumable from a checkpoint) by `schedule`/`assess` and by `distribute`/`submit` when per-unit minutes are known; the refusal says to split the unit or declare a checkpoint.
- S3. Session deadline: the runner passes `FORGE_SESSION_DEADLINE` (epoch seconds = session start + limit − margin) to the target; documented so target code stops starting new units/trials before it, checkpoints and exits cleanly.
- S4. Incremental persistence: Colab keeps a running manifest so a killed or reclaimed session still returns the files already written; `fetch` returns them.
- S5. Honest states: a failed or timed-out run is never recorded `returned`; a partial result is recorded and recoverable instead of blocking later fetches.
- S6. Remaining units: each submission records its units; a read reports which declared units have no complete result, and the next campaign sends only those.
- S7. Rule for agents: remote-execution, remote-parallelism and the build/walk agents state that every unit fits one session with margin or checkpoints and resumes; long units are split (e.g. by fold) or checkpointed.

## Tasks

- T1 (S1, S3, S4, S5, S6, S7 remote-execution doctrine) delegated writer, worktree `session-checkpoints-a` — pending
- T2 (S2, S7 remote-parallelism doctrine) delegated writer, worktree `session-checkpoints-b` — pending
- T3 (S7 agents and implementation skills) parent at integration — pending
- T4 live Kaggle verification of attaching a previous kernel's output (phase 2 prerequisite; authorized) — parent — pending
- T5 integration with parallel campaigns, full suite vs baseline, independent verifier — pending

## Log

- L1 (2026-10-27, user): see S0.
- L2: exploration: no adapter declares a session limit; assess's unitsOverSessionLimit is advisory; runner passes FORGE_CLONE_ROOT/COMMIT/RUN_MODE/RUN_UNITS only; Colab files.json/status.json written at run end (executor.py:242-270) so a reclaimed session returns nothing; Kaggle fetch always complete=True so failed/timeout is recorded returned; submitted_event has no units; Kaggle metadata passthrough refuses dataset/kernel sources (kaggle_driver.py:168-212); Colab has a generic _upload (colab.py:1212).
