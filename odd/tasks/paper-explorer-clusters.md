Objective: every Papersmith project carries reference metadata (abstracts) for what it cites, one tolerant BibTeX parser, and idea clusters in the Graph Atlas; shipped as a release, then applied to QMLEEG.
Branch: feat/paper-explorer-clusters. Delivery: single branch merged per docs/releasing.md (user asked for commit, merge, push, release). Test runner: .micromamba/envs/papersmith/bin/pytest.

## Specs

- S1. QMLEEG fixed: "resuelve los problemas en qmleeg".
- S2. New projects do not repeat it: "ajusta el flujo para que en nuevos proyectos no vuelva a pasar, respecto a la inclusion de abstract para tener mas informacion".
- S3. "asegurarse de que parser se actualice": `atlas_manuscript._bib_fields` stops losing entries; one shared tolerant parser.
- S4. "resuelve clusters de ideas".
- S5. Order: "primero dejalo listo en el flujo general de smith, comit, mergea push y release".
- S6. Then: "luego actualiza en local y en qmleeg, y actualiza y corre lo que falte en qmleeg para que quede actualizado".
- S7. From the earlier request, still binding: "asegurate de que estos cambios sean funcionales para cualquer otro proyecto de paper lanzado con smith, no solo para qmleeg".

Design decisions (assumptions of the parent, not user strings):
- D1. `parse_bib` and `plain_text` move to `skills/paper-writing/scripts/paper_bib.py` (atlas_manuscript is loaded by path, a relative import fails there); `paper_explorer` and `_bib_fields` both use them.
- D2. `resolve` stays the only network path: add `paper_cli.py resolve --references`. For each cited key: identifier from bib (DOI, arXiv) through the existing resolver chain; otherwise an OpenAlex title search accepted only on an exact normalized title match. Crossref returns no abstract by design, so a DOI must also try OpenAlex. Respect the existing network role, timeouts and `RESOLVER_UNREACHABLE`.
- D3. Results go to a sidecar `paper/.paper-writing/references.json`, not refs.bib (`bib build` rewrites refs.bib): per key `{status: resolved | not_found | unreachable, resolver, identifier, title, abstract, year, venue, link, digest, retrieved}`. Deterministic key order. Nothing invented: a title mismatch is `not_found`.
- D4. `verify` gains a check that every cited key has a sidecar record. Coverage, not abstract presence: `not_found` and `unreachable` pass with a visible note, so offline work is never blocked.
- D5. `bib build` refuses before writing when it would drop existing refs.bib entries for lack of evidence records (hazard: it truncates, then raises).
- D6. Explorer order for a value: bib, then pool, then sidecar.
- D7. Clusters are a computed, labelled view of the explorer, never manuscript graph nodes. Stdlib, deterministic: TF-IDF over title, abstract and keywords plus co-citation, family and shared-idea bonuses, a kNN similarity graph, Louvain-style modularity with sorted iteration. Labels are the distinctive terms, and the answer states the method and signals.

## Tasks

- T1 [S2,S3,S7] parser move, `_bib_fields`, bib build guard, `resolve --references`, sidecar, verify check, flow text. Route: delegated, parallel writer (context backstop plus independent unit). Status: done.
- T2 [S4,S7] `paper_clusters.py`, panel UI, i18n. Route: delegated, parallel writer. Status: done.
- T3 [S4] wire clusters into `paper_explorer.cited_papers`, seam check. Route: inline. Status: done, full suite 9405 passed, only the expected version test failed.
- T4 [S5] merge, release 0.62.0, push, GitHub release. Route: inline. Status: pending.
- T5 [S1,S6] local install, QMLEEG upgrade, resolve, rebuild layers, verify. Route: inline. Status: pending.

## Log

- L1 (2026-11-06, verbatim): "resulevo los problemas en qmleeg y ajusta el flujo para que en nuevos proyectos no vuelva a pasar, respecto a la inclusion de abstract para tener mas informacion, asegurarse de que parser se actualice, y resuelve clusters de ideas, primero dejalo listo en el flujo general de smith, comit, mergea push y release y luego actualiza en local y en qmleeg, y actualiza y corre lo que falte en qmleeg para que quede actualizado"
- L2 Evidence: QMLEEG refs.bib has no `% resolver=` comments, so `bib build` never wrote it; no evidence ledger exists; `verify` compares keys only; `bib build` there would truncate an untracked file. Rebuilding the evidence ledger needs ingested sources and is not part of these tasks.
- L3 Commit 7fbe3b77 holds the explorer; RDD review granted by the user on that commit, running.
- L4 Review of 7fbe3b77 approved and acknowledged; its advisory findings were fixed in T1 and T2.
- L5 Decision: `search_title` kept with a named exception in the `test_paper_evidence.py` guard. It confirms an already cited paper on an exact title and finds no new literature; without it entries lacking a DOI or arXiv id get no abstract.
- L6 Live rehearsal on a QMLEEG copy: 47 of 58 resolved, 36 with abstract, 10 not_found, 1 unreachable. Resolved titles agree with the bib except `akiba2019optuna`, which OpenAlex abbreviates. The not_found titles differ from what OpenAlex holds (barry2003eeg, banchi2021measuring), so refs.bib may hold wrong titles; left for the user, not edited.
