Connect Caztor to PaperSmith workspaces, add a project navigator, and add a manual dark mode.
Branch: feat/workspaces-navigator. Delivery: ask-on-risk. Test runner: `npx vitest run`, browser checks in `e2e/`.

## Specs

- S1: "agregues la opcion de conectarse a workspaces de papersmith". Caztor finds folders holding `papersmith.yaml` or `.papersmith/config.json`, and opens them. Nothing changes in the PaperSmith repository.
- S2: "que se pueda conectar a estos espacios facilmente". They are listed without typing a path, by scanning `~/papers` (assumption: `CAZTOR_PAPERS_DIR` overrides it).
- S3: "una ventana como en herdr en donde estàn los proyectos para navegar entre ellos de forma sencillo". A collapsible left rail with up, down and enter, the active project marked. Any folder can be added by path (assumption).
- S4: "agrega el modo oscuro". A visible control with System, Light and Dark. The choice persists. The PDF page stays white (assumption).
- S5 (assumption): switching is refused while a turn runs, and unsaved edits are saved first. A failed save stops the switch.
- S6 (assumption): the compile main falls back to `paper/main.tex`, PaperSmith's contract path. Caztor does not scaffold it. The engine stays Tectonic.

## Tasks

- T1 S4 inline: theme tokens, store, control, logo.
- T2 S1 S2 S6 inline: catalog adapter and compile fallback.
- T3 S3 S5 inline: per-project runtime and `/api/projects` routes. High risk (item 2).
- T4 S3 S5 inline: rail, switching, `project_changed`.
- T5 all inline: docs, browser checks, real workspace check, independent verifier. Done; verifier found 5 blockers, all fixed in one batch.

## Log

- L1 (2026-11-01): "está super bien, ahora, quiero que le agregues la opcion de conectarse a workspaces de papersmith, te dije que tambienquiero volverlo una extension de papersmith entonces que se pueda conectar a estos espacios facilmente, tambien quiero una ventana como en herdr en donde estàn los proyectos para navegar entre ellos de forma sencillo y agrega el modo oscuro"
- L2: Extension meaning, the user's answer: "Solo Caztor (Recomendado)". The offered text said Caztor's agents can use PaperSmith's MCP. Not in this delivery, because the runners deliberately refuse MCP; it stays pending and is reported.
- L3: Facts from the map: PaperSmith has no global registry and no plugin entry points. Neither real workspace has `paper/main.tex` yet. Dark mode already follows the OS, so the missing part is the manual control.
- L4: A browser run over a copy of a real workspace showed PaperSmith's cache in the tree and `skills/kaggle-accounts/store` reachable. Both are hidden now. Large trees start folded, except `paper`. `paper/main.tex` with `\\input` of a sibling compiled with Tectonic.
- L5: Verifier blockers fixed: parent of home could be opened; the Kaggle store was reachable by links and by moving a parent; older undo snapshots became unreadable; a stale tab could overwrite the new project; `light-dark()` broke the dialog shadow. Rechecked with regression tests, not a second independent run.
- L6 (2026-11-02): "en la parte de proyectos agrega tambien un boton para crear proyectos". Done: + button, plain LaTeX project in the papers folder.
- L7 (2026-11-02): "haz que Caztor proteja los marcadores de bloque. haz que castor identifique el main y cuando se abra un workspace de papersmith que sepa cual es, y si no existe aun ese main, que se pregunte si se quiere crearlo, con las especificaciones de papersmith para que lo pueda identificar papersmith". Done: editor filter, save refusal, agent instruction, main detection, scaffold identical to `paper_scaffold.py` (empty files), asked first.
