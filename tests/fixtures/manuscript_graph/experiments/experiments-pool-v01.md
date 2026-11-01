# Experiments protocol v01

**Validation scheme:** 5-fold cross-validation

## Experiment [exp:e1] — Calibrated attention versus mean pooling

- **Hypothesis:** Calibrated attention improves AUC over mean pooling.
- **Success criterion:** AUC gain of at least 0.02.

## Experiment [exp:e2] — Graph prior ablation

- **Hypothesis:** The graph prior reduces fold variance.
- **Success criterion:** Lower standard deviation across folds.
