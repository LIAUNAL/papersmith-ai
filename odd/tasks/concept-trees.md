Objective: present the problem as a cited problem tree and relate novelty pillars to hypotheses in a second tree, in the Concept Map & Model panel.
Branch: feat/concept-trees, stacked on feat/paper-explorer-clusters (19f033d3, unmerged, Mac only until pushed). Delivery: ask-on-risk. Test runner: pytest.

## Specs

- S1. "el problema en el panel se presente de forma similar al arbol de problemas, con reglas de redaccion similares, pero en ingles, y vamos a incluir un perfil mas tecnico en la redaccion". Rules adapted from Morfeo (guiaProyectosIA_Agente.md): the central problem is a negative state, qualifier + measurable variable + population or context; no opening with "Lack of", "Absence of", "No", "Need for", "Requires" or an infinitive; effects are never the solution.
- S2. "el problema central debe incluir al menos dos referecnais que lo referencien".
- S3. "se deben construir de dos a tres causas directas, cada uno con al menos dos citas que lo referencien, y sus respectivos efectos". Approved design: effects hang from the central problem and declare `caused_by`.
- S4. "luego vamos a construir un arbol similar que relacione los pilares de la novedad y las hipotesis".
- S5. "se deben incluir min dos pilares, tambien con al menos dos referncias en cada pilar que los sustenten".
- S6. "dicho arbol relacionar los pilares de novedad con las hipotesis, que tambien deben incluir al menos dos referencias". Approved design: each hypothesis has `pillars: [...]`, many to many.
- S7. "asegurate de que las referecnias de arbol de problemas y el arbol pilares novedad e hipotesis sean de artiuclos q1 o q2 de max 4 años de antiguedad".
- S8. Approved design decisions: the rule applies only to the two trees (layers, equations and experiments keep the current rule); a quartile counts only when it comes from the SJR CSV; conferences and preprints stay out of the trees; the cap of 5 citations per idea stays; migration invents no content.

## Tasks

- T0 [S8] inline. Sync ignored QMLEEG files from the Mac, branch on the Mac feature. Done: pool 24, citations check passes, no commit.
- T1 [S1, S3, S4, S5, S6] inline. Tree schema and English writing validator with tests. Done, 026a34cd.
- T2 [S2, S3, S5, S6, S7, S8] inline. Citation kinds, per-kind rules, quartile and age check. Done, 026a34cd.
- T3 [S1, S4] inline. Render both trees in the panel with en/es labels. Done, checked on a live dashboard capture.
- T4 [S1-S8] inline. Gates, proposal-deliberation skill, harness guides, docs. Done.
- T5 [S1-S7] inline. Apply to QMLEEG. Pending, separate phase, needs a new literature search and the SJR CSV.

## Log

- L1 (2026-11-07, verbatim): "ahora, vamos a ajustar papersmith, en el panel  de mapa de concepto y math, donde aparece el problema, pilares, novedad y hipotesis. revsia el flujo y reglas que tenemos en Redaccion propuestas morfeo, la idea es que el problema en el panel se presente de forma similar al arbol de problemas, con reglas de redaccion similares, pero en ingles, y vamos a incluir un perfil mas tecnico en la redaccion, el problema central debe incluir al menos dos referecnais que lo referencien, y se deben construir de dos a tres causas directas, cada uno con al menos dos citas que lo referencien, y sus respectivos efectos. luego vamos a construir un arbol similar que relacione los pilares de la novedad y las hipotesis. se deben incluir min dos pilares, tambien con al menos dos referncias en cada pilar que los sustenten, y dicho arbol relacionar los pilares de novedad con las hipotesis, que tambien deben incluir al menos dos referencias. asegurate de que las referecnias de arbol de problemas y el arbol pilares novedad e hipotesis sean de artiuclos q1 o q2 de max 4 años de antiguedad. explorar opciones, diseño, posibles inconsistencias para depurar, presentame el plan antes de implementar"
- L2 (2026-11-07, verbatim): "apruebo plan".
- L3. Routes: all inline, no writer trigger holds (one dependent behavior chain). Risk: item 3, model_spec and gates are contracts others consume.
- L4. Deviation from the plan: quartiles live in `sota-pool/journal-ranks.json`, not in `candidates.json`, because several modules depend on the pool's `metadata_digest`. Assumption: every pillar must reach a hypothesis, so the second tree has no loose node. sota-scout gained a journal pass with its own budget, because the pool budget of 25 was almost spent.
- L5. Evidence: full suite 9330 passed, 42 failed (39 tests plus subtests). All 39 failing tests also fail on base 19f033d3, for lack of a local environment in this clone; none is exclusive to the branch. Next: independent verifier, then T5, which needs the SJR CSV.
- L6. Independent verifier: S1-S8 pass; 2 blockers fixed with their tests: `rank` erased ranks when Crossref failed, and the `check` message changed with no tree involved. Advisories also fixed: non-object spec in math_view, article before a forbidden opener, false positives on "No-reference" and "To date", effects wording, duplicate pillar and hypothesis ids, Crossref parse errors, infinite years, non-list tree fields in the panel, wrong docstring. Left open: int ids in `hypotheses[].pillars`, and the stepper showing "7 of 7" with no reason while only a tree finding is open.
- L7. Native review of the 3 commits over 19f033d3, lineage review-6e00d7e559c011b4, lenses risk, resilience and reliability: approved and acknowledged. The first candidate from main exceeded the context budget and created nothing.
- L8. Non-blocking review findings left as later work: `rank` with an empty pool erases ranks; an outage still reports ok; an effect without `caused_by` passes when another effect covers the causes; the default SJR table path has no test; the age rule reopens the gate each January; the stepper gives no reason when only a tree finding is open.
