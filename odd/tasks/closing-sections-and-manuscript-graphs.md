# Closing sections, AI declaration, cited atlas and manuscript summary graph

Objective: re-measure conclusions and back matter on the group's ten Q1 papers, add a venue-aware AI-use declaration generated from the pipeline record, stop framing style metrics as AI-detection evasion, refresh the SOTA atlas from the citations, and build a manuscript summary graph.
Branch: feat/closing-sections-and-manuscript-graphs. Delivery: ask-on-risk (merge authorized by the user). Tests: `.micromamba/envs/papersmith/bin/pytest`.

## Specs

- S1: "realiza el mismo tipo de analisis para conclousiones, agradecimientos, y explora la opciones de inlcuir uso de la ia, y que otras secciones deberiamos incluir" — apply to `sections/07-conclusions.md` and `sections/10-back-matter.md` the measured pattern: conclusions 350–950 words, 3–6 paragraphs, block 2 one paragraph per contribution, at most one headline number per contribution identical to the results; back matter adds an AI-use declaration (always; venue-aware placement and wording: Elsevier own section before references with the Elsevier template, MDPI/IEEE inside Acknowledgments), ethics (IRB) and informed consent, code availability, supplementary materials, highlights and graphical abstract (Elsevier), abbreviations (optional); funding placement follows the venue. The contracts stay general for any domain.
- S2: the AI declaration is generated from the pipeline record (`skills/_core/command_center/ai_history.py`): tools/models, agent roles per phase, sections drafted by agents, human approval gates, verification steps; a declaration contradicting that record is a disqualifier; AI used in code or experiments also gets a Methods sentence.
- S3: fix the review advisories: methods extent "2 to 6 subsections" vs a table allowing up to 8; set-up extent 800–2500 too tight for the added blocks.
- S4: reorient `paper_ai_metrics.py` and the humanization verb to writing-quality metrics, never to hiding AI use (Springer Nature forbids presenting AI output as human-derived); the F5 invariants stay.
- S5: "explora tambien en el flujo de smith que se actualice el grafo sota del tablero al depurar el manuscrito y completar todas las citas" — derived layer `sota-pool/atlas.manuscript.json` (never mutating `atlas.json`): each SOTA system marked cited / not cited with the citing blocks and claims, plus cited papers absent from the pool; triggered when `bib build` passes and `verify` is clean, and on compile; the watcher covers `sota-pool/`.
- S6: "explora la construccion de un grafo mas que permita resumir el manuscrito: con el topic, el problema definido con sus pilares, sus hipotesis, el sota principal, la matematica y concetos relevantes base y de la novedad, los experientos planteados, los hallazgos obtenidos, y las conclusiones principales" — `manuscript_graph.py`, `.papersmith/manuscript_graph.json`, a fourth view in the Atlas tab; pillars produced by proposal-deliberation; base vs novelty math split by `mm-borrowed-machinery` vs `mm-proposal`.
- S7: "si, implementalo en ese orden, mergea y actualiza qmleeg".

## Tasks

- [x] T1 [S1,S2,S3] contracts 07 and 10, AI declaration from the pipeline record, advisories — delegated writer (worktree) — b9dcf5fe, 9870f837, 1a54dd76
- [x] T2 [S4] style metrics reorientation — delegated writer (worktree) — cd34b0cb; callers migrated in 66bd2841
- [x] T3 [S5] cited atlas layer and triggers — delegated writer — 93f66306
- [x] T4 [S6] manuscript summary graph — delegated writer — dea4829e
- [x] T5 [S7] version bump (264b7234), full suite (8775 passed, 3 known failures), independent verifier (S1-S6 PASS, no blockers), review in three slices (approved: review-35058e9844a16ff4, review-8781b499f22657e7, review-0f04953e3dbee9df), merge, smith reinstall, QMLEEG upgrade — inline

## Log

- L1 (2026-11-01): "realiza el mismo tipo de analisis para conclousiones, agradecimientos, y explora la opciones de inlcuir uso de la ia, y que otras secciones deberiamos incluir. explora tambien en el flujo de smith que se actualice el grafo sota del tablero al depurar el manuscrito y completar todas las citas, y explora la construccion de un grafo mas que permita resumir el manuscrito: con el topic, el problema definido con sus pilares, sus hipotesis, el sota principal, la matematica y concetos relevantes base y de la novedad, los experientos planteados, los hallazgos obtenidos, y las conclusiones principales"
- L2 (2026-11-01): "si, implementalo en ese orden, mergea y actualiza qmleeg" — approves the four-step plan presented in the analysis (contracts 07/10 + AI declaration; ai_metrics reorientation; cited atlas; manuscript graph).
- L3: evidence of the analysis in the session scratchpad (`cb/`, `sr/`, `mm/` per paper notes).
- L4: T1-T4 delivered; RDD reviews approved for main+T2 (review-b9bba0cb087a225f); review of the full candidate pending. Open: summary view opened in a new tab stays English (server-es.json not wired to that render).
- L5: the whole-feature review hit lens_context_budget_exceeded; the user chose "revisa en tres partes". All three slices approved with advisories only.
- L6: follow-up advisories (non-blocking) to address in a later hardening pass:
  - T1: conclusions paragraph cap contradiction (sections/07-conclusions.md:101-102); paper_ai_usage drafting attribution hardcoded, misleading code flag, methods sentence on any event, drafted-only refusal (paper_ai_usage.py:71-108); packet reads the HOME harness (paper_cli.py:2414); venue journal non-dict (paper_venue.py:1937).
  - T3: bib refresh trigger untested and unguarded recheck (paper_cli.py:1580-1613); panel masks fetch errors (atlas-manuscript-panel.js:69-78); unbounded evidence digest on poll (atlas_manuscript.py:105-113); tests after the main guard (tests/test_paper_ai_metrics.py:560); private paper_bib internals used (atlas_manuscript.py:155).
  - T4: dropped pillar refusal (manuscript_graph.py:312-334); number-mention edges (533-539); sys.path mutation (168-174); panel bypasses apiUrl and polls with a full rescan (manuscript-graph-panel.js:49,112); view route unguarded (server.py:2494); English-only new-tab view.
