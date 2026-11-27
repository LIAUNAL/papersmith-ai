# Illustrative results before performance (applied-AI line)
Objective: in applied-AI (experimental line) papers, the Results show what the novelty does at its basic stages before any aggregate performance artefact, and the experiment flow plans and records what those illustrations need. Branch `feat/illustrative-results` (worktree papersmith-ai-worktrees/illustrative-results); release 0.86.0. Runner: `.venv/bin/python -m pytest` (run e2e files serially; for the full suite use TMPDIR=/tmp; /tmp is a 16 GB tmpfs, so clean pytest temp before a full run).

## Specs
- S1: operator request (2026-11-27), verbatim: «vamos ahira con un cambio en el flujo papersmtih para papers ia aplicada. cuando se trabaje con series de tiempp, tareas de regreson o similares, antes de poner los resultados de rendimiento en error, r2 o sinilar, deben mostrarae resuktados ilustrativos de las etapas basicas de la novedad. por ejemplo. si usamos redes informadas por fisica, modelos transformers, arquitecturas nuevas, mostrar imagenes tipo imshow, o plots donde se muestre ejemplos relevantes de la representacion mejorada. si se proponen regularizadores o loss nuevos o mejorados, mostrar como convergen y como ibteractuan los terminos relevantes del loss o regularizados. ademas, mostrar para el toyset y para unos de los dataset relaes o semisinteticos mas relevantes del paper, ejemplos de prediccion, ilustrando input o ventana de entrada, y salida estimada contrastada contra el target y los metodos del estado del arte mas relevantes. si es posible, incluir rangos de confianza o variabbilidad segun el modelo usado o mediante tecncias de monte carlo o dropout montecarlo. si la tarea es clasifiqcion o clustering o similar, incluir espacios latentes en puntos claves de la arquitectura usada o propuesta usando umap tsne o similares, para ilustrar la capacidad de representacion y separabilidad o agrupamiento. añadir matrices de confusion y curvas toc si es el caso. ajusta papersmith, push y release»
- S2: the rule. The experimental line's results contract carries it, verbatim:
  "Illustrative results before performance. Before any aggregate performance artefact (error, R², accuracy and the like), the Results show what the novelty does at its basic stages: (a) the improved representation: for a physics-informed network, a transformer or a new architecture, imshow maps or plots of the relevant internal quantities on representative examples; (b) for a new or modified loss or regularizer, how it converges and how its terms interact during training; (c) for time series, regression and similar tasks, prediction examples on the toy set and on the most relevant real or semi-synthetic dataset, showing the input window and the estimated output against the target and the most relevant state-of-the-art comparators, with a confidence or variability band when the model provides one or Monte Carlo or Monte Carlo dropout can estimate it; (d) for classification, clustering and similar tasks, latent spaces at key points of the architecture (UMAP, t-SNE or similar) that show representation and separability or grouping, plus confusion matrices and ROC curves where they apply."
  - A new results block, `rd-illustrative`, sits before `rd-general-task` and carries these figures.
  - The experimental-setup contract declares the illustrative instruments: which examples, which comparators, which band method.
- S3: the experiment flow plans and records them:
  - experimental-deliberation: the protocol declares the illustrative artefacts per item (a)-(d) that apply.
  - experimental-implementation: the runs record what the illustrations need, under Results:
    - per-term loss histories;
    - representative input windows, predictions, targets, comparator predictions and bands;
    - representation snapshots;
    - 2-D embeddings with labels, confusion counts, ROC points.
  - experiments-reviewer: missing illustrative records is a finding.
- S4: ps_figures helpers, house style, drawing only from given arrays (no UMAP or t-SNE dependency):
  - `forecast_plot(ax, t_input, y_input, t_output, target, predictions, *, bands=None)`: the input window, then the target, the proposal and comparators, with optional (low, high) bands per prediction;
  - `loss_terms_plot(ax, steps, terms, *, log=True)`: per-term curves, optionally with their total;
  - `heatmap_plot(ax, matrix, *, x_labels=None, y_labels=None, colorbar=True)`: imshow of a representation;
  - `embedding_plot(ax, coords, labels)`: a 2-D scatter by label;
  - `confusion_matrix_plot(ax, matrix, labels, *, normalize=False)`;
  - `roc_plot(ax, curves)`: name to (fpr, tpr[, auc]), with the chance diagonal.
- S5: agents and docs:
  - paper-reviewer: a Results that opens on aggregate metrics without the illustrations is a weakness (Quality and Clarity);
  - redactor; paper-writing SKILL.md; docs/skills.md; CHANGELOG.
  - Spanish contract copies (es/sections) updated with their SOURCES.json hashes.

## Tasks
| ID | Specs | Route | Status | Evidence |
| --- | --- | --- | --- | --- |
| T1 | S2, S5 | delegated (Writer trigger a: parallel with T2, disjoint surfaces) | done | results and setup contracts, new block, es copies, agents, docs, tests |
| T2 | S3, S4 | delegated (Writer trigger a) | done | experiment flow skills, experiments-reviewer, ps_figures helpers, tests |
| T3 | S1 | inline | done | seam (harness sync, full suite), CHANGELOG, merge, release 0.86.0, cleanup |

## Log
- L1 (2026-11-27): operator request, verbatim in S1.
- Context from 0.85.0/0.85.1: there is no shared base contract; the rules sit per line, and the experimental line's contracts live in sections/01-03. es copies are under skills/_core/command_center/static/i18n/es/sections with SOURCES.json hashes. The contract digests are pinned in tests/test_paper_contract.py. ps_figures is at skills/experimental-implementation/assets/kit/ps_figures.py; its tests must keep matplotlib imports inside try/except ImportError (forge gate).
- L2 (2026-11-27): T2 done.
  - Six ps_figures helpers, pure-Python validation.
  - experimental-deliberation: "Declaring the illustrative results"; experimental-implementation: Results/illustrative/** recording table; experiments-reviewer: a missing record is a major finding.
  - Tests: 145 + 29 + 28 passed; with matplotlib 35 passed, 1 pre-existing pypdfium2 failure.
  - `loss_terms_plot` draws a term named "total" as the total.
- L3 (2026-11-27): T1 done: rd-illustrative is a required block (there is no clean "required when declared" mechanism); setup block 10; es copies; reviewer and redactor.
  - Parent closed: the dashboard writing templates en/es (35-55 %, block 0b), the server.py block guide and its server-es strings; a forge-floor admission for experimental-deliberation "latent"; the paper-writing SKILL rewords item (d) without "latent" (the paper-writing vocabulary leak test); experiments-reviewer "the implementation skill" -> `experimental-implementation`; the status characterization goldens updated.
  - Full suite -n 6: 28 failed. A serial rerun left 4 real ones, all fixed; the rerun of the failing ids then passed 33/33.
