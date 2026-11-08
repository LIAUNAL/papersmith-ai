# SOTA constellation coverage and a safe 3D start

Objective: no reference the paper cites stays out of the SOTA constellation, and a 3D sky too slow to start falls back to 2D instead of hanging.
Branch: feat/atlas-coverage. Delivery: ask-on-risk. Test runner: pytest (`tests/`) and Playwright (`ui/e2e`).

## Specs

- S1 "si el primer segundo dentro del tablero iba lento agregalo como regla para pasar a 2D y evitar que se cuelge." The slow-start rule comes back; it is not remembered as the operator's choice.
- S2 "explora en que partes del flujoo fases deberimaos actualizar el grafo sota, para evitar que referencias del paper queden sin citar. ajusta e implementa esos cambio." A coverage report of the references the proposal and the manuscript cite that the constellation does not draw, shown where the flow can act on it, with the phases' instructions updated.
- S3 "actualiza en qmleegv2 para que el grafo sota quede completo." Every reference qmleegV2 cites is drawn in its constellation.
- S4 "comit mergea push release y borra ramas".

## Tasks

- [x] T1 [S1] restore the slow-start fallback without storing it — inline — b9546102
- [x] T2 [S2] `atlas_coverage.py`, `smith atlas coverage`, `GET /api/atlas/coverage`, Atlas tab notice with its button, phase instructions — inline — 364a0b6e
- [x] T3 [S3] qmleegV2: resolve the manuscript references, add them to the pool, draw them — delegated — qmleegV2 aee87c4 (sota-pool is gitignored by the workspace)
- [x] T4 [S4] commit, merge, push, release, delete branches — inline — v0.66.0 (c23f5284)

## Log

- L1 (2026-11-08) "si el primer segundo dentro del tablero iba lento agregalo como regla para pasar a 2D y evitar que se cuelge. luego explora en que partes del flujoo fases deberimaos actualizar el grafo sota, para evitar que referencias del paper queden sin citar. ajusta e implementa esos cambio. actualiza en qmleegv2 para que el grafo sota quede completo. comit mergea push release y borra ramas"
- L2 Evidence: qmleegV2's constellation draws 45 systems after a sota-grapher run added the 21 proposal references it lacked; `smith atlas cited` reports 50 manuscript references outside the pool. paper/refs.bib has 58 entries and no abstracts, and paper/.paper-writing/references.json does not exist (`resolve --references` never ran), so those references cannot enter the pool, whose planets need a verbatim abstract quote.
- L3 Flow points: Phase 2 draws the constellation from the pool; Phase 4 step 4 and Phase 5 cite pool references (a journal pass can add pool references the constellation never drew); Phase 8 `bib build` and `resolve --references` add manuscript references that may be outside the pool.
- L4 T2 finding: `atlas_build` and `atlas_manuscript.refresh` already redraw the manuscript's citations as "Manuscript Citations" placeholders, but the sota-grapher instructions rendered with `render_atlas.py` alone, which dropped them; the agent now rebuilds with `smith atlas build .`. Coverage: proposal references not drawn by any atlas.json system, manuscript placeholders split by pool membership.
- L5 T3 delegated: resolve --references, sota-scout records, sota-grapher systems in qmleegV2; full suite running for the release.
- L6 (2026-11-08) Operator: "sube el limite de familias a 7" — check_atlas.py now accepts 3 to 7 families (85a2cd38); qmleegV2's 16 methodology references moved from F1 to F6.
- L7 T3 result: resolve --references resolved 47 of 58 keys (36 with an abstract); 29 manuscript references drawn from their abstracts; atlas 74 systems, 725 planets, 396 links, 6 families, check green. 21 stay placeholders: 10 not found and 11 with no abstract in OpenAlex (4 have arXiv versions; arXiv answered 429). `smith atlas coverage .` exits 1 on those 21.
