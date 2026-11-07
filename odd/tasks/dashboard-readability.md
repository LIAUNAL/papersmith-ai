# Dashboard readability, text size and experiments panel

Objective: a text-size control for the dashboard, a header and tab strip that hold at every size and screen, and a reorganised Experiments panel.
Branch: feat/dashboard-readability. Delivery: ask-on-risk. Test runner: pytest (`tests/`) and Playwright (`ui/e2e`, `cd ui; PYTHONPATH=../src:.. npx playwright test`).

## Specs

- S1 "revisa la armonia y vidualizacion del tablero. aumenta el tamaño de los textos x2." The operator chose a control (2026-11-07): "Control A−/A+": a selector in the top bar with ×1, ×1.25, ×1.5 and ×2, remembered per browser; the header and the tabs are redesigned to hold at every size.
- S2 "revisa el panel de experimentos, explora alternativad para mejorar la visualizacion de los paneles y secciones. explora ocultar paneles de secciones, reorganizar su presentacion, revisa el orden logico de lo que se muestra segun el flujo y buscando una interaccion mas fluida con el usuario". Exploration first: present the alternatives before changing the panel.
- S3 "asegurate de usar playwrigth para verificar funcionalidad y estilo visual. revisa responsive para que se adapte a distintas resoluciones de pantalla y en movil". Every change is checked with Playwright at desktop, tablet and phone widths, at every text size.

## Tasks

- [x] T1 [S1, S3] text-size control, header and tab strip that hold at every size and width — inline — 3060b618
- [x] T2 [S2, S3] Experiments panel: map its sections against the flow, present alternatives (hide, reorder, collapse) — inline — decided in L7
- [x] T3 [S2, S3] apply the chosen Experiments layout — inline — 0b6d7b62

## Log

- L1 (2026-11-07) "ahora, revisa la armonia y vidualizacion del tablero. aumenta el tamaño de los textos x2. luego, revisa el panel de experimentos, explora alternativad para mejorar la visualizacion de los paneles y secciones. explora ocultar paneles de secciones, reorganizar su presentacion, revisa el orden logico de lo que se muestra segun el flujo y buscando una interaccion mas fluida con el usuario"
- L2 Evidence: 425 font sizes are declared in rem, most between 0.72 and 0.85rem (11.5-13.6 px). A Playwright capture with the root at 32 px (×2) wraps the brand title over five lines, pushes the header past half the screen and the tabs off the right edge; ×1.5 does the same in part.
- L3 (2026-11-07) Operator answer: "Control A−/A+ (Recommended)".
- L4 (2026-11-07) "asegurate de usar playwrigth para verificar funcionalidad y estilo visual. revisa responsive para que se adapte a distintas resoluciones de pantalla y en movil"
- L5 T1 done in 3060b618: text-size.js (root font scale ×1-×2, localStorage), wrapping header, responsive guards. Playwright scan of 12 tabs × 390/820/1440 px × ×1/×2 finds no element past the right edge; ui/e2e/shipped/text-size.spec.ts (5 tests) and the 49 shipped specs pass. Known: the iframes (atlas, manuscript summary) keep their own size.
- L6 (2026-11-07) T2 evidence: the Experiments tab of QMLEEG is about 39,000 px tall (about 43 screens). The PoC → verification → full stepper appears after about 5,000 px of infrastructure (Kaggle MCP, Colab, remote services, local environment, run options, team, help), and results take about 32,000 px (27,500 for the full experiments, 4,800 for the PoC).
- L7 (2026-11-07) Operator answer: "Orden del flujo (Recommended)": one page in flow order, every section collapsible with its state remembered, the stepper with the next action on top, the infrastructure grouped at the end in a collapsed block, each product's summary first with its detail on demand. Preview chosen: stepper → protocol → datasets → proof of concept → full experiments → PoC vs full → before launching → infrastructure → experiments tutor.
- L8 T3 done in 0b6d7b62: stepper (with "Next:" badge) and the launch warning first, then protocol, datasets, PoC, full, comparison, other, and the infrastructure fold; folds keyed ["section", name], remembered in localStorage papersmith.expFolds; product detail behind ["detail", path]; tutor folded at the end. The launch warning stays on top, not at the end as in the preview, because tests/test_command_center_experiment_diagrams.py pins it before the datasets and it blocks launching. tests/test_command_center_run_options.py now pins the new order. Evidence: QMLEEG Experiments tab 39,235 px → 3,584 px at 1440 px; the 12-tab spill scan stays empty; ui/e2e/shipped/experiments-layout.spec.ts (3 tests) passes.
