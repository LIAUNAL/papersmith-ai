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
- T1 [S1, S3, S4, S5, S6] inline. Tree schema and English writing validator with tests. Pending.
- T2 [S2, S3, S5, S6, S7, S8] inline. Citation kinds, per-kind rules, quartile and age check. Pending.
- T3 [S1, S4] inline. Render both trees in the panel with en/es labels. Pending.
- T4 [S1-S8] inline. Gates, proposal-deliberation skill, harness guides, docs. Pending.
- T5 [S1-S7] inline. Apply to QMLEEG. Pending, separate phase, needs a new literature search and the SJR CSV.

## Log

- L1 (2026-11-07, verbatim): "ahora, vamos a ajustar papersmith, en el panel  de mapa de concepto y math, donde aparece el problema, pilares, novedad y hipotesis. revsia el flujo y reglas que tenemos en Redaccion propuestas morfeo, la idea es que el problema en el panel se presente de forma similar al arbol de problemas, con reglas de redaccion similares, pero en ingles, y vamos a incluir un perfil mas tecnico en la redaccion, el problema central debe incluir al menos dos referecnais que lo referencien, y se deben construir de dos a tres causas directas, cada uno con al menos dos citas que lo referencien, y sus respectivos efectos. luego vamos a construir un arbol similar que relacione los pilares de la novedad y las hipotesis. se deben incluir min dos pilares, tambien con al menos dos referncias en cada pilar que los sustenten, y dicho arbol relacionar los pilares de novedad con las hipotesis, que tambien deben incluir al menos dos referencias. asegurate de que las referecnias de arbol de problemas y el arbol pilares novedad e hipotesis sean de artiuclos q1 o q2 de max 4 años de antiguedad. explorar opciones, diseño, posibles inconsistencias para depurar, presentame el plan antes de implementar"
- L2 (2026-11-07, verbatim): "apruebo plan".
- L3. Routes: all inline, no writer trigger holds (one dependent behavior chain). Risk: item 3, model_spec and gates are contracts others consume.
