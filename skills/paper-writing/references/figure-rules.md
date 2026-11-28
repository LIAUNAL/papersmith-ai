## A diagram that compiles, or says why: `render` and `place` (figure rules)

**Figures over tables.** Every line's Methods and Results contracts carry
the same rule: "Figures over tables. In Methods and Results, present comparisons, distributions, trends, effects with their intervals and time series as data figures (line, bar, dot-and-whisker or forest, violin or box plots, heat maps) or diagrams. Keep a table only for values a reader must look up exactly (settings, hyperparameters, dataset, participant or hardware characteristics, metadata) or when the venue requires one. Among the floats of Methods and Results, aim at about 60 % figures and 40 % tables." A data figure is drawn by the run script, not by
`render` (stop A, in `references/figure-obligations.md`, refuses a diagram
that plots data), with the chart
helpers in `skills/experimental-implementation/assets/kit/ps_figures.py`,
beside `apply_style` and `save_figure`:
`interval_plot(ax, labels, estimates, low, high, *, reference=None)` for a
dot-and-whisker or forest plot, `grouped_bars(ax, groups, series, *,
errors=None)`, `distribution_plot(ax, samples, *, kind="violin")` (violin or
box) and `line_plot(ax, x, series, *, bands=None)`. The PDF it saves enters
the paper through `place`. `verify` measures the balance
(`figure-table-balance`).

**Illustrative results before performance.** The experimental line's
results contract (`sections/03-results-and-discussion.md`) carries the rule
"Illustrative results before performance. Before any aggregate performance artefact (error, R², accuracy and the like), the Results show what the novelty does at its basic stages: (a) the improved representation: for a physics-informed network, a transformer or a new architecture, imshow maps or plots of the relevant internal quantities on representative examples; (b) for a new or modified loss or regularizer, how it converges and how its terms interact during training; (c) for time series, regression and similar tasks, prediction examples on the toy set and on the most relevant real or semi-synthetic dataset, showing the input window and the estimated output against the target and the most relevant state-of-the-art comparators, with a confidence or variability band when the model provides one or Monte Carlo or Monte Carlo dropout can estimate it; (d) for classification, clustering and similar tasks, two-dimensional projections of the internal representations at key points of the architecture (UMAP, t-SNE or similar) that show representation and separability or grouping, plus confusion matrices and ROC curves where they apply."
Those figures live in a required block, `rd-illustrative`, which comes
before `rd-general-task` in the derived order (an `after` edge). The
experimental-setup contract's assessment declares what they read: the
representative examples, the comparators, the band method (model-native,
Monte Carlo or Monte Carlo dropout) and the embedding method and its points.
The run script draws them with the `ps_figures` helpers
`forecast_plot` (input window, target, proposal and comparators, with
optional bands), `loss_terms_plot` (per-term loss curves),
`heatmap_plot` (an imshow of a representation), `embedding_plot` (a 2-D
scatter by label, from coordinates the run computed),
`confusion_matrix_plot` and `roc_plot`, and `place` puts the PDFs in the
paper.

**Captions are short.** "A figure or table caption is at most four lines: a title that says what the float shows, plus the one definition a reader needs to read it. Notation and further definitions go in a table note below the table or in the text." `verify` counts the words of every caption
(`caption-length`): at most four lines (checked as at most 70 words).
