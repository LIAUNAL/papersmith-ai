# SOTA constellation coverage and a safe 3D start

Objective: no reference the paper cites stays out of the SOTA constellation, and a 3D sky too slow to start falls back to 2D instead of hanging.
Branch: feat/atlas-coverage. Delivery: ask-on-risk. Test runner: pytest (`tests/`) and Playwright (`ui/e2e`).

## Specs

- S1 "si el primer segundo dentro del tablero iba lento agregalo como regla para pasar a 2D y evitar que se cuelge." The slow-start rule comes back; it is not remembered as the operator's choice.
- S2 "explora en que partes del flujoo fases deberimaos actualizar el grafo sota, para evitar que referencias del paper queden sin citar. ajusta e implementa esos cambio." A coverage report of the references the proposal and the manuscript cite that the constellation does not draw, shown where the flow can act on it, with the phases' instructions updated.
- S3 "actualiza en qmleegv2 para que el grafo sota quede completo." Every reference qmleegV2 cites is drawn in its constellation.
- S4 "comit mergea push release y borra ramas".

## Tasks

- [ ] T1 [S1] restore the slow-start fallback without storing it — inline
- [ ] T2 [S2] `atlas_coverage.py`, `smith atlas coverage`, `GET /api/atlas/coverage`, Atlas tab notice with its button, phase instructions — inline
- [ ] T3 [S3] qmleegV2: resolve the manuscript references, add them to the pool, draw them — delegated (agent work on the workspace)
- [ ] T4 [S4] commit, merge, push, release, delete branches — inline

## Log

- L1 (2026-11-08) "si el primer segundo dentro del tablero iba lento agregalo como regla para pasar a 2D y evitar que se cuelge. luego explora en que partes del flujoo fases deberimaos actualizar el grafo sota, para evitar que referencias del paper queden sin citar. ajusta e implementa esos cambio. actualiza en qmleegv2 para que el grafo sota quede completo. comit mergea push release y borra ramas"
- L2 Evidence: qmleegV2's constellation draws 45 systems after a sota-grapher run added the 21 proposal references it lacked; `smith atlas cited` reports 50 manuscript references outside the pool. paper/refs.bib has 58 entries and no abstracts, and paper/.paper-writing/references.json does not exist (`resolve --references` never ran), so those references cannot enter the pool, whose planets need a verbatim abstract quote.
- L3 Flow points: Phase 2 draws the constellation from the pool; Phase 4 step 4 and Phase 5 cite pool references (a journal pass can add pool references the constellation never drew); Phase 8 `bib build` and `resolve --references` add manuscript references that may be outside the pool.
