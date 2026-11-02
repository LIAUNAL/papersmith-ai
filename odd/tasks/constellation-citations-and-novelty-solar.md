# Constellation citations and 3D solar novelty graph

Objective: synchronize the 3D SOTA constellation with all manuscript citations (both in-pool and extra cited systems), run this synchronization upon validating/writing Introduction, Related Work, and Materials and Methods, transform the Novelty Graph into the 3D solar constellation style (solar systems per node, highly informative, Three.js offline renderer), and upgrade/test in QMLEEG.
Branch: feat/constellation-citations-and-novelty-solar. Delivery: inline + upgrade QMLEEG. Tests: `.micromamba/envs/papersmith/bin/pytest`.

## Specs

- S1: "en el panel de grafos, el grafo constelacion 3D deberia estar actualizado con todas las citas del mansucrito" — `atlas_manuscript.py` defines `sync_constellation_citations` which updates `sota-pool/atlas.json` and `sota-pool/atlas.html` with every cited reference in the manuscript (in-pool systems marked as cited with their citing blocks, extra cited systems added as full solar systems in the "Manuscript Citations" family with planets for blocks, topics, claims and BibTeX details).
- S2: "este proceso debe correrse al validar la construccion de introduccion, related work y materials and methods, corrige dicho flujo y actualiza smith y qmleeg" — wire the citation synchronization trigger in `paper_cli.py` (`cmd_validate`, `cmd_write`, `cmd_verify`, `cmd_bib`), `src/papersmith/core/atlas.py` (`smith atlas build/cited`) and `atlas_build.py` when validating or writing blocks belonging to `introduction`, `related-work`, or `materials-and-methods`.
- S3: "luego, el grafo de novedad deberia seguir el mismo estilo de constelacion 3D y debe ser mas informativo, usando el mismo principio de sistemas solares por nodo, actualiza el flujo y actualiza dicho grafo en smith" — transform `novelty_graph.py` to convert novelty nodes into full solar systems (star at orbit 0, question/claim/gap/domain at orbit 1, family/blocks at orbit 2, metrics/references at orbit 3) and render via the offline Three.js `render_atlas` celestial viewer.
- S4: "actualiza y prueba en qmleeg" — upgrade QMLEEG with the new smith kit, update QMLEEG's `.papersmith/novelty_graph.json` with the enriched solar metadata, rebuild `sota-pool/atlas.html`, and verify both the 3D constellation and novelty graph views.

## Tasks

- [x] T1 [S1] `atlas_manuscript.py` constellation synchronization with manuscript citations
- [x] T2 [S2] Flow integration in `paper_cli.py`, `core/atlas.py`, and `atlas_build.py` for Introduction, Related Work, and Materials and Methods
- [x] T3 [S3] 3D solar constellation renderer and solar system generator in `novelty_graph.py`
- [x] T4 [S1,S2,S3] Mirror kit files to `src/papersmith/_kit/` and update `kit-manifest.json`
- [x] T5 [S1,S2,S3] Unit and integration tests for constellation citations and novelty solar graph
- [x] T6 [S4] Upgrade and test in QMLEEG project

## Verification Evidence

- `tests/test_constellation_citations_and_novelty_solar.py`: 6 passed.
- Atlas and paper writing test suite (97 tests): 97 passed.
- In `QMLEEG`:
  - `smith atlas cited --sync /Users/andresalvarez/Documents/QMLEEG`: exits 0, 36/50 systems cited (18 in-pool + 32 extra citations outside the pool). Generated `sota-pool/atlas.html` (874 KB offline Three.js constellation).
  - `smith atlas novelty /Users/andresalvarez/Documents/QMLEEG`: exits 0, 7 contribution systems, 64 semantic links. Generated `.papersmith/novelty_graph.html` (647 KB offline Three.js constellation).
  - `paper_cli.py validate` with blocks belonging to `introduction`, `related-work`, and `materials-and-methods`: triggers automatic sync of `atlas.manuscript.json` and `sota-pool/atlas.html`. Blocks outside these sections do not run redundant constellation builds.
