# measurement

The measurement core shared by the hardware and lab-simulation lines
(decision F1 of `odd/tasks/paper-type-lines.md`): the instruments, the raw
data files the operator produced, an uncertainty budget per quantity and the
agreement of a device with a reference device.

**The assistant never generates measurements or data.** The operator measures,
writes the CSV files and registers them with `--by`; the core binds each file
by its sha256 and only reads it. No verb writes into or edits a registered
file, drops a missing value or fills one in: a cell that is not a finite
number is refused (`VALUE_INVALID`) and the operator fixes the file. Every
computation is bound to the hashes of its inputs, so a changed file or a new
instrument record makes it `stale` until it is computed again.

## Files

| File | Holds | Written by |
| --- | --- | --- |
| `study/instruments.json` | every instrument record, history kept | `instrument add --by` |
| `study/measurements.json` | every registration of a raw data file, history kept | `data register --by` |
| `study/uncertainty/<quantity>.json` | the budgets of a quantity, one per condition set | `uncertainty compute` |
| `study/agreement.json` | one analysis per device file and reference file pair | `agreement compute` |

An instrument entry:

```json
{"by": "Ana Ruiz", "at": "2026-11-23T10:00:00Z", "id": "caliper-1", "model": "Mitutoyo 500-196",
 "serial": "SN-001", "resolution": {"value": 0.01, "unit": "mm"},
 "stated_uncertainty": {"value": 0.02, "unit": "mm", "distribution": "normal", "coverage_k": 2.0},
 "calibration_certificate": "LAB-CAL-2026-17", "calibrated": "2026-01-10", "due": "2027-01-10"}
```

`stated_uncertainty` is `null` when the certificate states none, and a
`rectangular` one has `"coverage_k": null` (its value is the half-width). A
later entry for the same id needs `--reason` and carries it; the identical
entry is refused (`RECORD_UNCHANGED`). The latest entry of an id is the
instrument.

A registration:

```json
{"by": "Ana Ruiz", "at": "...", "path": "data/length.csv", "sha256": "<hex>", "rows": 5,
 "columns": ["replicate", "length"], "quantity": "length", "unit": "mm", "value_column": "length",
 "replicate_column": "replicate", "instrument": "caliper-1", "conditions": {"temperature": "20 C"}}
```

The value column defaults to the quantity's name. Registering a path again
needs `--reason` (for instance after the operator corrected the file).

A budget holds `quantity`, `unit`, `conditions`, `computed_at`, `model`,
`inputs` (`files`: path, sha256, rows; `instrument`: id and the sha256 of the
entry used), `type_a` (`n`, `mean`, `sd`, `u`, `dof`), `components` (each
`name`, `type`, `source`, `u`, `unit`, `dof` (`null` = infinite),
`sensitivity`, `contribution`), `combined_standard_uncertainty`,
`effective_dof` (`null` = infinite), `coverage` (`method` `student-t`,
`normal` or `declared`; `k`; `level`; `dof_used`), `expanded_uncertainty`,
`result` (`value`, `expanded_uncertainty`, `unit`, `k`, `level`) and
`calibration` (`due`, `checked_on`, `state`, `override`).

An agreement analysis holds `device` and `reference` (path, sha256,
instrument, value column), `pair_column`, `quantity`, `unit`, `n`, `unpaired`
(the pair ids found in one file only), `bland_altman` (`n`, `bias`,
`sd_differences`, `multiplier`, `loa_lower`, `loa_upper`), `icc` (`form`,
`n`, `k`, `ms_rows`, `ms_columns`, `ms_error`, `value`), `computed_at` and
`warnings`.

## CLI

```bash
python skills/_core/measurement/measure_cli.py instrument add --id caliper-1 --model "<model>" --serial "<serial>" \
    --resolution "0.01 mm" [--stated-uncertainty "0.02 mm" --distribution normal --coverage-k 2] \
    --calibration-certificate "<certificate>" --calibrated YYYY-MM-DD --due YYYY-MM-DD [--reason "<why>"] --by "<operator>" --root .
python skills/_core/measurement/measure_cli.py instrument status [--on YYYY-MM-DD] --root .
python skills/_core/measurement/measure_cli.py data register --file data/length.csv --quantity length --unit mm \
    --instrument caliper-1 [--value-column length] [--replicate-column replicate] [--condition temperature="20 C"] \
    [--reason "<why>"] --by "<operator>" --root .
python skills/_core/measurement/measure_cli.py data status --root .
python skills/_core/measurement/measure_cli.py uncertainty compute --quantity length [--condition key=value]... \
    [--sensitivity resolution=1]... [--coverage-k 2 | --level 0.95] \
    [--allow-past-due --by "<operator>" --reason "<why the readings still hold>"] --root .
python skills/_core/measurement/measure_cli.py uncertainty status --root .
python skills/_core/measurement/measure_cli.py agreement compute --device-file data/device.csv \
    --reference-file data/reference.csv --pair-column sample [--value-column length] --root .
python skills/_core/measurement/measure_cli.py agreement status --root .
python skills/_core/measurement/measure_cli.py status [--on YYYY-MM-DD] --root .
```

Each verb prints one JSON object. A refusal is `{"ok": false, "error":
<CODE>, "message": ...}` with exit code 1; a usage error exits 2. The codes
are listed in the docstring of `measure_cli.py`; the ones an operator meets
most are `DATA_CHANGED` (re-register the file), `CALIBRATION_PAST_DUE, OVERRIDE_NOT_NEEDED (an override given while the calibration is current)`,
`REPLICATES_TOO_FEW`, `CONDITIONS_MIXED` (name a `--condition` set),
`UNIT_MISMATCH` (declare a sensitivity coefficient) and `PAIRS_TOO_FEW`.

`uncertainty compute` selects the current registrations of the quantity:
those with exactly the `--condition` set given, or all of them when they share
one set. They must share a unit and an instrument, and each file must still
hash as registered. A past-due calibration (after the `due` date, checked
today) is refused unless the operator passes `--allow-past-due --by <name>
--reason <text>`, which the budget records. `agreement compute` warns, without
refusing, when an instrument is past due.

## Formulas

The measurand is a direct measurement, Y = the mean of the readings, with
instrument corrections of zero expectation (the model the budget records).
References are to JCGM 100:2008, *Evaluation of measurement data: Guide to
the expression of uncertainty in measurement* (GUM).

| Step | Formula | GUM |
| --- | --- | --- |
| Type A | mean q̄ = Σ q_k / n; s² = Σ (q_k − q̄)² / (n − 1); u_A = s / √n; ν_A = n − 1 (n ≥ 2) | 4.2.1 eq. (3), 4.2.2 eq. (4), 4.2.3 eq. (5), 4.2.6 |
| Type B, stated normal | u = U / k, U and k from the calibration certificate | 4.3.3 |
| Type B, stated rectangular | u = a / √3, a the half-width | 4.3.7 eq. (7) |
| Type B, resolution | rectangular of half-width δx / 2: u = δx / (2√3) | F.2.2.1 |
| Type B degrees of freedom | ν → ∞ (limits taken as exactly known) | G.4.2, eq. (G.3) with Δu → 0 |
| Combination | u_c = √(Σ (c_i u_i)²), uncorrelated inputs, c_i the sensitivity coefficient (1 unless declared) | 5.1.2 eq. (10), 5.1.3 |
| Effective degrees of freedom | ν_eff = u_c⁴ / Σ ((c_i u_i)⁴ / ν_i), Welch-Satterthwaite; infinite terms add nothing; ν_eff = ∞ when all are | G.4.1 eq. (G.2b) |
| Coverage factor | k = t_{(1+p)/2}(ν), ν = ν_eff truncated to the next lower integer; the normal quantile when ν_eff = ∞; or a declared k | G.3, G.4.1 (step 3 and its note), 6.3, Table G.2 |
| Expanded uncertainty | U = k u_c; reported as Y = q̄ ± U | 6.2.1 eq. (18), 7.2.3 |

A component whose unit differs from the quantity's unit is refused unless its
sensitivity coefficient is declared (`--sensitivity <component>=<c>`), which
converts it; the core never converts units itself.

**Student t quantile.** `stats.t_quantile` inverts the t distribution function
by bisection (relative width 10⁻¹³). The distribution function is
F(t) = 1 − ½ I_{ν/(ν+t²)}(ν/2, ½) for t > 0 (Abramowitz and Stegun 26.7.1 with
26.5.27), the regularized incomplete beta I_x(a, b) evaluated by its continued
fraction with the modified Lentz method (Press et al., *Numerical Recipes*,
3rd ed., section 6.4). The tests check it against the two-sided 95 % table to
three decimals for ν = 1 to 100 and against GUM Table G.2 (p = 95.45 %) to two.

**Bland-Altman** (Bland and Altman, *Lancet* 1986;327(8476):307-310): for the
n pairs present in both files, d_i = device_i − reference_i; bias = d̄;
s_d with n − 1; 95 % limits of agreement d̄ ± 1.96 s_d. At least 3 pairs.

**ICC(2,1)**, two-way random effects, absolute agreement, single measures
(Shrout and Fleiss, *Psychol Bull* 1979;86(2):420-428; ICC(A,1) in McGraw and
Wong, *Psychol Methods* 1996;1(1):30-46; reporting form as in Koo and Li,
*J Chiropr Med* 2016;15(2):155-163). For n subjects and k raters (here k = 2,
device and reference), from the two-way ANOVA mean squares of rows (MSR),
columns (MSC) and error (MSE):

ICC(2,1) = (MSR − MSE) / (MSR + (k − 1) MSE + k (MSC − MSE) / n)

with MSR = k Σ_i (x̄_i· − x̄)² / (n − 1), MSC = n Σ_j (x̄_·j − x̄)² / (k − 1) and
MSE = (SST − SSR − SSC) / ((n − 1)(k − 1)). `value` is `null` when the
denominator is not positive. The tests reproduce Shrout and Fleiss's Table 2
(ICC(2,1) = .29). Koo and Li advise interpreting the ICC by its 95 %
confidence interval; the core reports the point estimate and leaves the
interpretation to the operator.

## Readers

`records.py` holds side-effect-free readers for the board, the Study panel and
the gates; none writes, creates a directory or raises on a corrupt file
(each reports `{"state": "corrupt", "message": ...}`):

| Reader | Returns |
| --- | --- |
| `instruments_state(root, on=None)` | `absent`, `corrupt` or `recorded` with each instrument's latest entry, `calibration` (`current`/`past-due` on `on`, today by default), `entries`, `entry_sha256`, and `past_due` |
| `data_state(root)` | each registered file with `state` `current`, `changed` or `missing` |
| `budget_state(root)` | each budget's summary with `state` `current` or `stale` and `reasons` (`input-changed`, `input-missing`, `registration-changed`, `inputs-added`, `instrument-changed`) |
| `agreement_state(root)` | each analysis with `state` and `reasons` (`device-` or `reference-` `changed`, `missing`, `reregistered`) |
| `measurement_status(root, on=None)` | all four and `warnings` (`CALIBRATION_PAST_DUE`, `DATA_CHANGED`, `DATA_MISSING`, `BUDGET_STALE`, `AGREEMENT_STALE`, `*_CORRUPT`) |

`stats.py` holds the pure statistics (`t_quantile`, `type_a`, `combine`,
`coverage`, `bland_altman`, `icc_2_1`).
