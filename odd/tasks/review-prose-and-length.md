# Review prose, protocol diagram, reference budget and manuscript length

Objective: tighten the review line's prose and figures, cap its references, and bound every manuscript's length.
Branch: `feat/review-prose-and-protocol-diagram` · delivery: single-pr (one release) · runner: `.venv/bin/python -m pytest`.

## Specs

- S1 (review introduction) "en la introduccion evita usar la division RQ y luego los items de innovacion por renglones cortos, procura construir un parrafo de propuesta antes del parrafo de agenda, que iluestre la idea, novedad y los puntos clave del review."
- S2 (review open problems) "la seccion de open problems debes estructurala de una manera mas cohesionada, y coherente, evita usar items con negrital, genera parrafos de 6 o 8 renglones, con citas relevants que ilustren los problemas descritos, usa conectores para ilar las ideas de cohesionada y coherente, usando las reglas del redacto smith, evitando claudismos, usando los patrones de escritura que tenemos definidos, y buscando resaltar de forma humanizada los puntos claves." Applied to the background's open problems and, as the same pattern, the discussion's challenges (assumption: the discussion block is the second "open problems" place).
- S3 (review methods) "en la seccion de metodos, cuando explicas el metodo prisma en una tabla, en lugar de la tabla genera un diagrama de flujo, usando los agentes, skills y estrategias que tenemos definidos, para que expliques el diagrama prisma adaptada al tema y review de interes."
- S4 (review references) "para la estrstegia o flujo de paper de revision con prisma, ajusra para que el numero total de referencia sea de 100 a 200. si encientras mas, depura y delimita a las mas relevantes o de trabajaos de mayoe impacto segun el cuartil de la revista y la relacion con los temas tratados."
- S5 (tables, both lines) "para el articulo de revusion y para articulos de investigacion convencionales, procura evitar tablas de solo dos columnas o solo dos filas, explora siempre si es posible construir graficas tipo pastel o barras para que la informacion sea amigable e intuitiva en esos casos."
- S6 (review results) "para los articulos de revision, en la seccion de resultados, evita usar referencias o notacion RQ, favorece la inclusoon de parrafos conectaros segun las ideas y discusiones provistas."
- S7 (length, both lines) "asegurate de que la extension de los articulos no sea de mas de 45  paginas a una columna, incluyendo referencias (toma como base la plantilla de elsevier en modo submitted para estimar la cantidad max permitida, o 25 paginas a doble  columana en plantilla elsevier)"
- S8 delivery: "ajusta estos cambios, saca comit, mergea push y release"

## Tasks

- [x] T1 [S1-S3] review contracts 03/04/07/05 + systematic-review skill + tests — inline — f4a65b73
- [x] T2 [S4] `review_cli.py prioritize` + contracts 05/06, skill, template, docs, tests (RED observed) — inline — f4a65b73
- [x] T3 [S5] table-shape rule in experimental 02/03 (+ Spanish copies, re-captured digests) and review contracts — f4a65b73; `manuscript_qa` table-shape finding (RED observed) — inline
- [x] T4 [S6] review results without RQ notation, connected paragraphs — inline — f4a65b73
- [x] T5 [S7] Elsevier-equivalent page estimate in `manuscript_qa` (45 single-column / 25 two-column, RED observed) + contract/skill/CLI notes — inline
- [ ] T6 [S8] commit, merge, push, release

## Log

- L1 (2026-11-19) "vamos a realizar algunos cambios para el estilo articulo de revision: 1) ... 2) ... 3) ... ajusta estos cambios, saca comit, mergea push y release" (S1-S3, S8 verbatim above).
- L2 (2026-11-19) S4 added mid-turn verbatim above.
- L3 (2026-11-19) S5-S7 added mid-turn verbatim above.
- L4 T1/T2 evidence: tests/test_review_line.py + tests/test_systematic_review.py 35 passed; full suite 10528 passed, failures only xdist-flaky (`test_proposal_implementation` toy targets, `test_skill_audit` — both fail on base under -n 16 and pass alone). Experimental `sections/` untouched for S1-S4.
- L5 S7 calibration: canonical main.tex is `article` 11pt onecolumn review mode, so its page count is not Elsevier's; elsarticle is not installed and the CTAN download was denied, so the estimate uses declared constants (words, references and floats per elsarticle preprint 12pt page) that a later calibration can replace.
- L6 T3-T5: experimental contract edits needed their Spanish copies retranslated (SOURCES.json sha256) and the PRE_MIGRATION_BODY_DIGESTS of 02/03 re-captured; the QA fixture's header-plus-one-row table is now a table-shape finding (expected). Full suite: 10538 passed; the only other failures are xdist-flaky test_skill_audit cases that pass alone (389) and fail on base under -n 16.
- L7 Native review ea25948d..e2f78e6c (readability, reliability): approved, acknowledged (lineage review-f91f16326e6743d5). Advisory follow-ups fixed in the next commit: the table-shape disqualifier was duplicated in experimental 02/03 (digest and Spanish source sha re-captured), `prioritize` crashed on a non-UTF-8 SJR table (now unranked with a note), and the page estimate ignored `\input`/`\include` (now expanded against the main document's folder). Left as noted: the two-column estimate is a fixed 25/45 ratio of the single-column one; nested tabulars are not split.
