# Dashboard readability, text size and experiments panel

Objective: a text-size control for the dashboard, a header and tab strip that hold at every size and screen, and a reorganised Experiments panel.
Branch: feat/dashboard-readability. Delivery: ask-on-risk. Test runner: pytest (`tests/`) and Playwright (`ui/e2e`, `cd ui; PYTHONPATH=../src:.. npx playwright test`).

## Specs

- S1 "revisa la armonia y vidualizacion del tablero. aumenta el tamaño de los textos x2." The operator chose a control (2026-11-07): "Control A−/A+": a selector in the top bar with ×1, ×1.25, ×1.5 and ×2, remembered per browser; the header and the tabs are redesigned to hold at every size.
- S2 "revisa el panel de experimentos, explora alternativad para mejorar la visualizacion de los paneles y secciones. explora ocultar paneles de secciones, reorganizar su presentacion, revisa el orden logico de lo que se muestra segun el flujo y buscando una interaccion mas fluida con el usuario". Exploration first: present the alternatives before changing the panel.
- S3 "asegurate de usar playwrigth para verificar funcionalidad y estilo visual. revisa responsive para que se adapte a distintas resoluciones de pantalla y en movil". Every change is checked with Playwright at desktop, tablet and phone widths, at every text size.

## Tasks

- [x] T1 [S1, S3] text-size control, header and tab strip that hold at every size and width — inline — 3060b618
- [ ] T2 [S2, S3] Experiments panel: map its sections against the flow, present alternatives (hide, reorder, collapse) — inline, read-only until the operator chooses
- [ ] T3 [S2, S3] apply the chosen Experiments layout — inline, after T2's decision

## Log

- L1 (2026-11-07) "ahora, revisa la armonia y vidualizacion del tablero. aumenta el tamaño de los textos x2. luego, revisa el panel de experimentos, explora alternativad para mejorar la visualizacion de los paneles y secciones. explora ocultar paneles de secciones, reorganizar su presentacion, revisa el orden logico de lo que se muestra segun el flujo y buscando una interaccion mas fluida con el usuario"
- L2 Evidence: 425 font sizes are declared in rem, most between 0.72 and 0.85rem (11.5-13.6 px). A Playwright capture with the root at 32 px (×2) wraps the brand title over five lines, pushes the header past half the screen and the tabs off the right edge; ×1.5 does the same in part.
- L3 (2026-11-07) Operator answer: "Control A−/A+ (Recommended)".
- L4 (2026-11-07) "asegurate de usar playwrigth para verificar funcionalidad y estilo visual. revisa responsive para que se adapte a distintas resoluciones de pantalla y en movil"
- L5 T1 done in 3060b618: text-size.js (root font scale ×1-×2, localStorage), wrapping header, responsive guards. Playwright scan of 12 tabs × 390/820/1440 px × ×1/×2 finds no element past the right edge; ui/e2e/shipped/text-size.spec.ts (5 tests) and the 49 shipped specs pass. Known: the iframes (atlas, manuscript summary) keep their own size.
