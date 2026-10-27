# PoC launch smoothing

Objective: a future proof of concept configures, rehearses and launches a remote step without the refusal-by-refusal loop the QMLEEG E5 launch went through.
Branch: `feat/poc-launch-smoothing` (from `origin/main` 8bfd8c2d, v0.27.0). Delivery: one release (0.28.0) after integration. Tests: `pytest` from the main checkout's micromamba env (`~/Documents/papers_smith/papersmith-ai/.micromamba/envs/papersmith/bin/pytest`), `npm test` with `node_modules` linked from the main checkout.

## Specs

User's list (approved items 1-5, quoted from the assistant's proposal the user accepted with "sí, implementa del 1 al 5 y saca la release"):

- S1. "Clonar solo el notebook que corre el job, no toda la carpeta `Notebooks/`." A job whose clone paths include a whole notebooks folder went stale when an unrelated notebook in that folder changed, forcing re-smoke, re-propose, offer and gate. `generate-job` must make the run notebook itself the clone unit by default, so an unrelated notebook change does not stale the pin. Existing explicit `--clone-path` uses keep working.
- S2. "Verificar la escalera antes de `generate-job`, no en el lanzamiento." Two late surprises: (a) a remote step had no `@rehearsal <job>` item in the AGREED ladder, so `offer` never published a `launch`; (b) earlier ladder items were ticked but unbacked (`POSITION_UNBACKED`). `verify` (and `position --reconcile`) report/insert a `@rehearsal <job>` item before a remote step that lacks one, and `generate-job` (or the walk's pre-check) reports unbacked items before a job is generated.
- S3. "Un comando que diga qué falta para lanzar." A read-only command (`launch-plan`) lists, for a job, the remaining acts in order (`propose`, `offer`, `gate`, `submit`), the blocker each one would raise now (readiness, rehearsal witness, unbacked items, missing/stale proposal, diagram validation), and the exact next command. It never writes.
- S4. "El scaffold del repositorio objetivo debería traer de serie: un helper que escriba `shard.json` bajo el runner; un test que corra el forward en `meta` y verifique que no se mezclan dispositivos." Writes only when `FORGE_RUN_MODE` is set, into the working directory, carrying the commit, a source digest and the device kind/name.
- S5. "El escáner de `generate-job` debería reconocer la celda de arranque de los notebooks del kit." The kit's byte-identical notebook bootstrap cell (repository root resolution: `sys.path` insert of `ROOT/src`, reads under `.git`) must not produce `unresolvedImports`/`unresolvedReads` that force `--accept-unresolved`/`--accept-unresolved-reads`. Anything else the scanner flags today is still flagged.

## Tasks

- T-A (S1, S5) delegated writer, worktree `poc-launch-smoothing-a` — pending
- T-B (S2, S3) delegated writer, worktree `poc-launch-smoothing-b` — pending
- T-C (S4) delegated writer, worktree `poc-launch-smoothing-c` — pending
- T-D integration: merge A/B/C, full suites, CHANGELOG, release 0.28.0 — pending

Route evidence: Writer trigger (a) parallelism — three units with disjoint edit surfaces (remote-execution generate-job; implementation engine ladder/launch; target scaffold), each heavier than a subagent start, launched together.

## Log

- L1 (2026-10-26, user): "sí, avísame cuando terminen y corre e5_report. luego mira que deberias ajustar en papersmith para que futuros proyectos en prueba de concpeto corran y se configuran sin errores y de manera efiicente"
- L2 (2026-10-26, user): "sí, implementa del 1 al 5 y saca la release"
- L3: Field evidence from QMLEEG E5: clone path `QMLEEG-DRU/Notebooks` staled by a `poc_report` re-run (submit refused: "these declared clone paths differ ... QMLEEG-DRU/Notebooks/poc_report.ipynb"); `offer` published only `run-step` until `@rehearsal e5_run_end_to_end` was added; `gate` refused `POSITION_UNBACKED` (items 1-3) and `GATE_PROPOSAL_UNKNOWN` twice (no proposal; proposal staled by re-pin); generate-job refused "sys.path mutation is uncertain" and 12 uncertain reads incl. the kit bootstrap's `.git` reads; the target needed a hand-written shard.json writer and a device fix (zero_state on CPU).
