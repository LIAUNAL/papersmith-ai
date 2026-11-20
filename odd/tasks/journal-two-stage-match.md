# Suggested journals: two-stage match (scope filter, then similar papers in the top 5)

Objective: suggested journals publish papers like this one in topic, research approach, contribution kind, AI use and mathematical depth, for both scopes.
Branch: `feat/journal-two-stage-match` · delivery: ask-on-risk · runner: `.venv/bin/python -m pytest`.

## Specs

- S1 (two stages) "primero filtra segun nombre de revista y scopes y luego con las top 5 de match, reafina el match buscando papers en cada revista del top 5 match que hablem de temas parecidos a los del papers"
- S2 (dimensions) "asegurwte de revisar el match entre las novedades del paper, las tecncias empleadas o los tipos de analisis, por ej. investigacion cuantitatvia, cualitatvia, hibrida, uso de ia, papers tipo generla, use inspired, de metodo  o concepto, etc." and "mira tambien si incluyen matematica, si son mas descriptivos, etc para que los journals sugeridos si tengan relacion con el paper"
- S3 (both scopes) "tanto de revistas internacionales como nacionales"
- S4 (agreed design, L2) the paper and each sampled work get a lexical research profile (approach quantitative/qualitative/mixed, AI use, kind general (method)/theory/use-inspired/concept/review (L4), math mathematical/moderate/descriptive); the paper's kind comes from `contribution_type` in `.papersmith/model_spec.json` when present; each top-N journal gets a style match from its similar works and the top N are re-ordered by it; the panel shows the evidence. Deterministic rules, no LLM. Constraint carried from journal-scope-publindex L3: do not tune the rules to one paper.

## Tasks

- [x] T1 [S2,S4] `research_profile.py`: lexical classifier (EN/ES), paper profile from the LaTeX (equation density + text + contribution_type), journal shares and match score; unit tests — inline
- [x] T2 [S1,S3,S4] `journal_cli.py`: `--refine-top N` (default 5, env PAPERSMITH_JOURNAL_REFINE_TOP), per-journal OpenAlex works query (source filter + paper phrases, latest works when none match), re-rank the top N by `refined_score`, `query.refinement`, degrade with a note on any failure; both scopes; CLI tests with FakeApi; docstring + SKILL.md — inline
- [x] T3 [S4] panel: paper profile line, per-journal style match and sampled works in the evidence cell, fit sort follows the CLI rank; en/es strings; panel tests — inline
- [ ] T4 commit work units; native review per policy

## Log

- L1 (2026-11-20) user request verbatim: "explira en la busqueda de papers, tanto de revistas internacionales como nacionales, asegurwte de revisar el match entre las novedades del paper, las tecncias empleadas o los tipos de analisis, por ej. investigacion cuantitatvia, cualitatvia, hibrida, uso de ia, papers tipo generla, use inspired, de metodo  o concepto, etc. primero filtra segun nombre de revista y scopes y luego con las top 5 de match, reafina el match buscando papers en cada revista del top 5 match que hablem de temas parecidos a los del papers, mira tambien si incluyen matematica, si son mas descriptivos, etc para que los journals sugeridos si tengan relacion con el paper"
- L2 (2026-11-20) Exploration: international fit = 0.45 similar works + 0.30 cited + 0.25 OpenAlex topic overlap (no aims/scope text exists in OpenAlex; works are searched globally and grouped by journal, abstracts never fetched); national = 0.5 subfield affinity + 0.3 lexical scope overlap + 0.2 cited. No per-journal search and no paper-type/method/math classification anywhere. Proposed the design in S4 (lexical, reproducible, offline-testable; less nuance than an LLM). User: "si".
- L3 Routing: inline (one dependent chain CLI -> panel; no writer reason). Existing tests count OpenAlex calls, so the test harness sets PAPERSMITH_JOURNAL_REFINE_TOP=0 and the refinement tests turn it on.
- L4 T1: tests/test_research_profile.py RED (module absent), then GREEN 14/14. Kinds follow the reviewer's contribution types (general, theory, use-inspired, concept) plus review for journal surveys, so the paper's recorded `contribution_type` maps one to one.
- L5 T2: CLI tests (tests/test_journal_finder_refine.py, 9 international + national + docs) written after the code; RED shown afterwards by running them against the base journal_cli.py (9 failed), GREEN with the change. Existing journal-finder suites 251 passed with the harness setting PAPERSMITH_JOURNAL_REFINE_TOP=0. Live check against api.openalex.org: `primary_location.source.id:<S>,from_publication_date,type:article` with a quoted OR search and with `sort=publication_date:desc` both answer, abstracts included.
- L6 T3: panel tests (3) RED against the base journals-panel.js (3 failed), GREEN with the change; i18n catalogue tests pass. The fit sort follows the CLI rank only when `query.refinement.applied`, so older candidate files sort as before.
- L7 Native review 45c501d5..1a8d95b6 (resilience, reliability): approved, acknowledged, authority burned (lineage review-4bda9aa8efe60f71). Advisories fixed next as their own commit, each with RED first: a journal with no sample was sorted on its bare relative fit and could jump above a sampled one (now only refined journals trade places, among the places they held); the national stage did not skip when OpenAlex had just failed the subfield profile (now skipped with a note, no per-journal call); the default top of 5 and an invalid PAPERSMITH_JOURNAL_REFINE_TOP were untested (now tested). Not changed: the national stage always uses the response cache, as the national scope refuses --no-cache.
