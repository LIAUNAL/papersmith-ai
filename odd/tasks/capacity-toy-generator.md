# capacity-toy-generator
Objective: a `capacity` EEG toy profile in the datasets skill that generates, per replicate, fresh training, validation and test subjects under three class rules (monotone with separation d′, interaction, frequency-two), with realistic background, rhythms, mixing and blinks — the generator QMLEEG experiments v05 E5 declares.
Branch: feat/capacity-toy-generator · Delivery: single merge (merge, push and release are the operator's decision) · Runners: `.micromamba/envs/papersmith/bin/pytest -n 8 --dist loadfile`, `npm test`.

## Specs

- S1 (user): "sí, empieza por el generador y el runner de E5" — this document covers the generator; the runner lives in the QMLEEG target repository.
- S2 (from v05 E5, Data Sources per Stage): "each replicate with 170 freshly generated subjects (60 for training, 10 for validation and 100 for testing, one label per subject, balanced within each group), 12 epochs per subject, 19 channels and 256 samples per epoch at 128 Hz"; "narrowband Theta (4-8 Hz), Beta (13-30 Hz) and Alpha (8-12 Hz) activity over an aperiodic 1/f background ..., mixed across neighbouring channels to imitate volume conduction, with frontal eye-blink artifacts in a fraction of the epochs and the class effect confined to the fronto-central channels".
- S3 (from v05 E5, Protocol): the monotone rule's subject log Theta/Beta offset ~ N(±d′/2, 1) by class; interaction: independent Gaussian Theta and Beta deviations, class one when both deviate in the same direction; frequency-two: a Theta deviation uniform over one period, class one where cos(2u) > 0.
- Constraint (skill doctrine): the datasets CLI stays stdlib-only and seeded: same parameters, same bytes.
- Assumption: the generator writes float32 `.npy` plus a JSON sidecar (a 170-subject CSV is ~100 MB); label noise is applied by the runner, so the generator stores the clean label only.

## Tasks

- T1 [S2,S3] `skills/datasets/scripts/capacity_toy.py` (stdlib generator + npy writer) and `synth --profile capacity` (rule, d′, group sizes, sidecar, TOY.md, registry) + SKILL.md + tests — route: inline — done

## Log

- L1 (2026-10-25, user verbatim): "sí, empieza por el generador y el runner de E5"
- L2 Evidence (2026-10-25): with the first parameters the interaction and frequency-two oracles reached only 0.65 and 0.66 test BA (below the 0.75 degree-one limit); the per-subject gain and the Alpha jitter dominated the absolute Theta feature. Tuned to effectGain 1.0, rhythmScale 3.0, subjectGainLogSd 0.05, alphaLogSd 0.25: oracle test BA monotone 0.903 / 0.820 / 0.680 for d′ 3.0 / 1.5 / 1.0 (Bayes 0.933 / 0.773 / 0.691), interaction 0.917 (least-squares linear 0.533), frequency-two 0.850 (linear 0.520); 3 seeds, 100 test subjects; ~7 s per 170-subject replicate.
- L3 Verification: datasets tests 66 passed incl. 4 new (RED before the CLI change); forge gate green once the module is tracked; floor-vocabulary guard required renaming "latent" to "deviation" and "Bayes ceiling" to "Bayes limit"; full suite 7110 passed plus the expected version-hygiene failure (release pending).
