# Figures over tables in Methods and Results (every paper line)
Objective: make every smith paper line favour data figures and diagrams over tables in its Methods and Results sections, aiming at about 60 % figures and 40 % tables, checked by `verify`. Branch `feat/figures-over-tables` (worktree papersmith-ai-worktrees/figures-over-tables); delivery: merge --no-ff, release 0.85.0. Runner: `.venv/bin/python -m pytest`.

## Specs
- S1: operator request (2026-11-27), verbatim: «revisa en paper smith proyecto base, ajusta las reglas de redaccion agentes y flujos para favorecer la construccion de figuras en resultados y metodos en lugar de tablas, buscando una relacin 60 a 40 % entre figuras y tablas. ajustalo para que dicha regal se aplique a todos los tipos de papers que se construyen en smith. ajusta papersmith, valida, comit mergea push release birra ramas megeadas, luego actualiza smith en la maquina y en este lroyecto»
- S2: the shared rule. Every line's Methods and Results contracts carry it, in the same words:
  - The rule, verbatim: "Figures over tables. In Methods and Results, present comparisons, distributions, trends, effects with their intervals and time series as data figures (line, bar, dot-and-whisker or forest, violin or box plots, heat maps) or diagrams. Keep a table only for values a reader must look up exactly (settings, hyperparameters, dataset, participant or hardware characteristics, metadata) or when the venue requires one. Among the floats of Methods and Results, aim at about 60 % figures and 40 % tables."
  - Per line: the Extent lines of those contracts allow at least as many figures as tables. Conflicting sentences, such as "one table per outcome family", are rewritten to the rule.
- S3: a verify check `figure-table-balance`.
  - Classification: mechanical.
  - Counting: the figure environments (`figure`, `figure*`) and table environments (`table`, `table*`, `longtable`) inside the blocks of the line's Methods and Results/Discussion sections (data-resource: data records and technical validation; hardware: hardware description and validation/characterization). If no section map is available, it falls back to the manuscript body before the back matter.
  - Verdict: pass when figures / (figures + tables) >= 0.6; fail below; unmeasured (reason from the closed list, or a new documented reason) when those sections hold no float.
  - The evidence names both counts and the ratio.
- S4: chart helpers in `skills/experimental-implementation/assets/kit/ps_figures.py`, beside `apply_style` and `save_figure`, so a run script can draw the usual result figures in the house style:
  - `interval_plot(ax, labels, estimates, low, high, *, reference=None)`: dot-and-whisker / forest;
  - `grouped_bars(ax, groups, series, *, errors=None)`;
  - `distribution_plot(ax, samples, *, kind="violin")`, with kind violin or box;
  - `line_plot(ax, x, series, *, bands=None)`.
- S5: agents and docs steer the same way:
  - the redactor;
  - the paper-reviewer's Clarity criterion: a table-heavy Results is a weakness;
  - the venue-adapter: venue limits still win;
  - the figure-review advisory text, which says "values belong in the prose or a table": a data figure becomes the first option;
  - the manuscript_qa advice;
  - paper-writing SKILL.md, where the check is listed with the chart helpers;
  - docs/skills.md;
  - CHANGELOG.

- S6: operator request (2026-11-27), verbatim: «ajusra tambien las reglas de smith para que los captions de las figuras y tablas no excedan los 4 renglones»
  - Every line's contracts carry the rule sentence, verbatim: "A figure or table caption is at most four lines: a title that says what the float shows, plus the one definition a reader needs to read it. Notation and further definitions go in a table note below the table or in the text."
  - verify check `caption-length` (mechanical) counts the words of each `\caption{...}` in the manuscript: LaTeX commands are stripped, and an inline math span counts as one word. It fails when a caption exceeds 70 words, about four lines at a single-column width; the evidence lists each offending caption (its label or first words) with its count. It covers the main manuscript, and the supplement when the workspace builds one with its sources.
  - The redactor and the paper-reviewer (Clarity) apply it.

## Tasks
| ID | Specs | Route | Status | Evidence |
| --- | --- | --- | --- | --- |
| T1 | S2 | delegated (Writer trigger a: parallel with T2 and T3, disjoint surfaces) | done | contracts of all eight lines + their pinned tests |
| T2 | S3, S5 | delegated (Writer trigger a) | done | verify check, agents, skill docs, advisories, tests |
| T3 | S4 | delegated (Writer trigger a) | done (uncommitted) | ps_figures chart helpers + tests |
| T5 | S6 | delegated (follow-ups to the T1 and T2 writers, same surfaces) | done | caption rule in contracts (T1), caption-length check, agents and docs (T2) |
| T4 | S1 | inline | pending | seam check (full suite, harness sync), CHANGELOG, merge, release 0.85.0, cleanup |

## Log
- L1 (2026-11-27): operator request, verbatim in S1 (made from the Paper_EEIA session).
- L2 (2026-11-27): an explorer mapped the code.
  - No shared base contract: the "at least three columns" table rule is pasted into each line's contract. Section dirs per line: `src/papersmith/core/manifest.py:65-165`.
  - No verify check counts floats: rosters at `skills/paper-writing/scripts/paper_verify.py:75-148`, functions at :1044-1062.
  - `place` only copies a PDF with provenance; there are no chart helpers (ps_figures has only apply_style and save_figure).
  - Pinned tests: `tests/test_paper_contract.py:1040-1064` (body digests), `tests/test_review_line.py:305-315`, `tests/test_manuscript_qa.py:203`.
  - Release: docs/releasing.md; current version 0.84.6.
- L3 (2026-11-27): T3 done. ps_figures gains interval_plot, grouped_bars, distribution_plot and line_plot, which use the active colour cycle (the module has no palette). Tests: 13 passed and 8 skipped in .venv (no matplotlib there); 21 passed in a scratch venv with matplotlib; test_implementation_domain_lock 28 passed.
- L4 (2026-11-27): operator «ajusra tambien las reglas de smith para que los captions de las figuras y tablas no excedan los 4 renglones» -> S6, T5.
- L5 (2026-11-27): T1 writer: S2 and S6 are in 23 Methods and Results contracts plus 7 float-holding ones (related work, hardware 02-08). Table-pushing sentences were rewritten per line. New test test_figures_over_tables_contracts (RED 81 fails -> GREEN); named suite 343 passed.
  - Open: the Spanish copies es/sections 01, 02, 03 and 05 are stale (4 failures in test_command_center_section_translation); the phrase "one comparison table per theme" remains in review_board.py, server-es.json and paper-flow-review.md.tpl. Both were handed back to T1 with an extended surface.
  - caztor/ is an imported third-party source, left alone.
  - Decision: the caption-length threshold is 70 words (60 is too tight for caption_decodes contracts); S6 updated.
- L6 (2026-11-27): T2 writer: the figure-table-balance and caption-length checks; agents (redactor, paper-reviewer, venue-adapter); figure-review and manuscript_qa advice; SKILL.md; docs/skills.md. Section map from the block markers (union of the section ids across lines). Parent decisions: 70 words; vacuous pass (no table / no caption -> pass, never unmeasured, so clean does not change for papers with nothing to violate); count the separate discussion sections; fix the pins in test_paper_figure_audit and test_paper_coherence.
