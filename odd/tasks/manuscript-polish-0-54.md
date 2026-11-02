# Manuscript polish: related-work table, figure/table text range, declarations order, English-only text, humanization

Objective: tighten five manuscript rules in the section contracts, agents and checks, keep the flow consistent, release, and rebuild QMLEEG.
Branch: feat/manuscript-polish-0-54. Delivery: merge, push and release authorized by the user. Tests: `.micromamba/envs/papersmith/bin/pytest`.

## Specs

- S1: "la tabla que resume el related work, debe tener en 7 a 12 trabajos, segun los mas relevanes y los pilares y contribuciones, familiar y aristas (el agente redactor debe analizar la mejor forma de presentarla para que sea clara, concisa y precisa."
- S2: "para el revisor de figuras y tablas, asegurate de que el tamñao de los textos en figuras tablas, lables, ticks, legend etc, este entre el 70% y el 90% del tamaño del texto del manuscrito."
- S3: "la seccion declarations, que esta despues de referencias, debe ir antes de referencias."
- S4: "asegurate de que los textos que aparecen por definir, o en español en el texto, sean en ingles, el texto no puede llevar nada en español, todo en ingles."
- S5: "revisa las reglas de humanizacion, suena monotono y redundante, revisa el uso de conectores, la transicion entre ideas, el uso de because ,where ,y ciertas palabras y estrucutras suenan muy roboticas. mejora el agente y skill de humanizacion y redundancia."
- S6: "ajusta el flujo, revisa que no se rompa nada, que los contratos actualizados de escrito del manuscrito sean consistentes con estos cmabios, verifica, comit, mergea push, actuliza smith, release, acutliza en local smith, actualiza qmleeg y reconstruye el manuscrito de qmleeg con etos cambios"

## Tasks

- U1 [S1] related-work synthesis table rule (contract 05, redactor) — delegated writer (worktree)
- U2 [S2] text size range 0.70–0.90 × body in figures and tables (print_scale, figure-review, place, diagram audit, diagram_cli, ps_figures, table lint, manuscript QA, agents) — delegated writer (worktree)
- U3 [S3] declarations/back matter before the references (contract 10, manuscript assembly, venue placement) — delegated writer (worktree)
- U4 [S4] English-only manuscript: no Spanish and no placeholders (contract 09 blinding placeholder, a checker in write/verify/QA) — delegated writer (worktree)
- U5 [S5] humanization and redundancy: metrics, ai-auditor agent, humanize skill, writing rules in contracts — delegated writer (worktree)
- U6 [S6] integrate: Spanish copies + digests, consistency pass across contracts, full suite, verifier, review, release, QMLEEG rebuild — inline/delegated

## Log

- L1 (2026-11-02): "corrige pendientes 1 al 4. luego, vamos con los siguientes ajustes en los contratos de las secciones del manuscrito: la tabla que resume el related work, debe tener en 7 a 12 trabajos, segun los mas relevanes y los pilares y contribuciones, familiar y aristas (el agente redactor debe analizar la mejor forma de presentarla para que sea clara, concisa y precisa. para el revisor de figuras y tablas, asegurate de que el tamñao de los textos en figuras tablas, lables, ticks, legend etc, este entre el 70% y el 90% del tamaño del texto del manuscrito. la seccion declarations, que esta despues de referencias, debe ir antes de referencias. asegurate de que los textos que aparecen por definir, o en español en el texto, sean en ingles, el texto no puede llevar nada en español, todo en ingles. revisa las reglas de humanizacion, suena monotono y redundante, revisa el uso de conectores, la transicion entre ideas, el uso de because ,where ,y ciertas palabras y estrucutras suenan muy roboticas. mejora el agente y skill de humanizacion y redundancia. ajusta el flujo, revisa que no se rompa nada, que los contratos actualizados de escrito del manuscrito sean consistentes con estos cmabios, verifica, comit, mergea push, actuliza smith, release, acutliza en local smith, actualiza qmleeg y reconstruye el manuscrito de qmleeg con etos cambios"
- L2: writers do not touch mirrors (Spanish copies, `SOURCES.json`, `PRE_MIGRATION_BODY_DIGESTS`); U6 updates them once after merging.
