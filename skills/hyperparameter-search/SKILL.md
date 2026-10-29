---
name: hyperparameter-search
description: "Trigger: the experimental deliberation judged a hyperparameter search worthwhile and the protocol declares one — validate its plan (one trial budget for every arm, baselines included; a seeded sampler; nested inside each outer fold's training subjects; nothing the experiments test tuned; the importance evaluator named), estimate its cost from a timing probe, and after the search ran, record per arm and outer fold a summary with hyperparameter importance, contour and optimization-history figures, read back for the dashboard. Optuna studies under the target's own venv; a stdlib CLI, no network, no API keys. Never launches a search."
---

# Hyperparameter search

A search for the settings an experiment leaves open, run so that the
comparison it feeds stays fair, and recorded so that a reader sees what the
search found rather than only the value it chose.

A search is not a default step. It runs **only when the experimental
deliberation judged it worthwhile** — many settings without published
defaults, or a comparison that would be unfair without one — and the protocol
then declares it in a Hyperparameter Search subsection (space, budget,
nesting, sampler seed, evaluator, and what it never tunes). This skill
validates that declaration, estimates its cost, and reports what the search
left behind. The search library is Optuna (Akiba et al., KDD 2019,
doi 10.1145/3292500.3330701), installed in the target's own venv and nowhere
else.

## The objective flow

**Why this skill was invoked, and where it has to arrive.** Declared here and
in `OBJECTIVE_FLOW` (`scripts/hpo_cli.py`), held equal by a test. Every
refusal prints the flow, so a blocked session knows which stage it is behind.

| Stage | Establishes | Behind when |
|---|---|---|
| `planned` | plan accepts <Name>/hpo/plan.json: one trial budget for every arm, a seeded sampler, a search nested inside each outer fold, nothing the experiments test tuned, and the importance evaluator named | no <Name>/hpo/plan.json exists, or plan refuses it |
| `searched` | one study per arm and outer fold, named <arm>-fold<k>, ran its declared trials into <Name>/hpo/studies.db where it was placed | <Name>/hpo/studies.db is missing or holds no study for an arm and fold the plan declares |
| `reported` | report wrote Results/hpo/<study>/summary.json with its importance, contour and history figures for every study, and status read them back | status lists a missing study or a missing figure |

**Arrival:** a recorded search per arm and outer fold, with its importance and contour figures read back, whose tuned values are then frozen per outer fold for every seed of the full run.

**Two stops are a person's:**

1. **Whether to search at all.** The experimental deliberation decides it and
   the protocol declares it; this skill never adds a search the protocol does
   not hold.
2. **The launch.** This skill never launches anything. A search placed on a
   remote GPU notebook is generated, rehearsed and launched like any full run,
   through `remote-execution` and behind the operator's consent and gate.

## The doctrine

- **Nested, never on the test subjects.** The search runs inside each outer
  fold, on that fold's training subjects only, scored on an inner validation
  split of them (`nested.innerValidation`); the outer fold's test subjects are
  never seen by any trial. A search scored on the test fold reports a tuned
  test score, not a generalisation estimate.
- **An equal trial budget for every arm, baselines included.** One `nTrials` for
  every arm. A proposed method tuned for a hundred trials against a baseline
  left at its defaults measures the budget, not the method.
- **Never tune what the experiments test.** An independent variable an
  experiment varies (a model size, a number of components) is listed under
  `fixed` and may not appear in `space`.
- **A seeded sampler.** `sampler.seed` is required, so the same plan proposes
  the same trials; pruning (`MedianPruner`) is declared with its start-up and
  warm-up counts, or `none`.
- **The importance evaluator is always named.** Optuna 5.0 defaults to
  PED-ANOVA, and on one toy study fANOVA (Hutter, Hoos and Leyton-Brown,
  ICML 2014, https://proceedings.mlr.press/v32/hutter14.html) and PED-ANOVA
  ranked the same two parameters differently, so the plan names its
  evaluator (`fanova`, `ped-anova` or `mean-decrease-impurity`), seeds the
  ones that take a seed, and may name a second as a `check`.
- **Importance and contours are descriptive, never a hypothesis test.** They
  say which settings moved the objective in this search and where the good
  region lay; they carry no p-value and sustain no claim of the paper. The
  experiments' own significance tests stay the only evidence.
- **Frozen afterwards.** The tuned values are frozen per outer fold and
  reused for every seed of the full run; the full run never searches again.

## The plan

`<target>/<Name>/hpo/plan.json`, schema 1:

```json
{"schema": 1,
 "objective": {"metric": "<name>", "direction": "minimize" | "maximize"},
 "sampler": {"name": "TPESampler", "seed": <int>},
 "pruner": {"name": "MedianPruner" | "none", "nStartupTrials": <int>, "nWarmupSteps": <int>},
 "nTrials": <int>, "maxEpochs": <int>,
 "nested": {"outerFolds": <int>, "innerValidation": "<text>"},
 "arms": ["<arm id>", ...],
 "space": [{"name": "<param>", "kind": "float" | "int" | "categorical",
            "low": <num>, "high": <num>, "log": <bool>, "choices": [...]}],
 "fixed": ["<independent variable the experiments test>", ...],
 "importance": {"evaluator": "fanova" | "ped-anova" | "mean-decrease-impurity",
                "seed": <int>, "check": "<second evaluator or null>"}}
```

**Study naming.** One study per arm and outer fold, `study_name =
"<arm>-fold<k>"` with `k` counting from 1, all in one storage,
`sqlite:///<target>/<Name>/hpo/studies.db`. The experiments code creates and
optimises the studies with the plan's sampler, seed and pruner; this skill
reads them.

**The estimate.** `plan --timing <Name>/Results/timing.json` (the timing
probe's record, `skills/remote-parallelism/SKILL.md`) reports, per
host, `nTrials × arms × outerFolds × maxEpochs × secondsPerUnit` (the mean of
that host's measurements) as a range, ±20%. It is an upper bound: every trial
is counted at its full epoch budget, and pruning and early stopping only lower
it. A host with no measurement reads `unmeasured`; local timings never stand
in for a remote host.

The timing probe writes schema 2 and upgrades a schema 1 record in place, so
both are read. On schema 2 the estimate is keyed by candidate (`local-cpu-4`,
`local-mps`, `<host>:<owner>/<machine>`; an upgraded schema 1 row keeps its
host as its candidate), each from its own rows at its fastest measured
setting (`settings` names it), with its `candidate` and `host`. One host may
hold CPU and accelerator rows: they are never pooled, and `mixed-devices` is
refused only when one candidate was timed on two devices. `local` and every
`--host` with no candidate measured read `unmeasured`. Schema 2 is validated
by remote-parallelism's own reader, so its refusals read the same there and
here.

## The report

Per study, `<target>/<Name>/Results/hpo/<study>/summary.json`, the shape the
dashboard's experiments panel reads:

```json
{"schema": 1, "study": "<arm>-fold<k>", "arm": "<arm>", "fold": <int | null>,
 "objective": {"metric", "direction"}, "sampler": {"name", "seed"}, "pruner": "<name | none>",
 "nTrials": <int>, "complete": <int>, "pruned": <int>, "failed": <int>,
 "bestValue": <float | null>, "bestParams": {...}, "space": [...as plan],
 "importance": {"evaluator": "<name>", "seed": <int | null>, "values": {"<param>": <float>}},
 "importanceCheck": {"evaluator": "<name>", "values": {...}} | null,
 "contourParams": ["<param>", ...],
 "figures": {"contour": "<file>", "importance": "<file>", "history": "<file>"},
 "optunaVersion": "<x.y.z>", "generatedAt": "<ISO-8601>"}
```

Beside it, each figure as PNG and PDF: `contour` (the matrix of the top three
parameters by the declared evaluator, or every pair when fewer),
`importance` (the declared evaluator's importances) and `history` (the
optimization history). Each `figures` entry names its PNG (`contour.png`,
`importance.png`, `history.png`), relative to the summary's folder. A
figure that cannot be drawn — fewer than two complete trials, or a single
parameter for a contour — is `null`, with the reason in `"notes": [...]`.

## Accepted operations

```
python3 skills/hyperparameter-search/scripts/hpo_cli.py <verb> ...
```

| Verb | What it does |
|---|---|
| `plan` | `--file <plan.json> [--timing <timing.json>] [--host <host>:<owner> ...]`: validates the plan under every rule above and prints `{plan, valid, studies, storage, trialsPerStudy, trialsTotal, arms, outerFolds, sampler, importance, fixed, launchAuthorization: false}`; with `--timing`, adds `estimate` per host (`{seconds, low, high, secondsPerUnit, measurements, device, formula}` or `"unmeasured"`) and `range`. `local` and every measured host are always reported; each `--host` adds a row. On a schema 2 record the rows are per candidate and add `{candidate, host, settings}` |
| `report` | `--target <repo> --name <Name> [--python <path>]`: runs `<target>/.venv/bin/python -I scripts/optuna_report.py` (or `--python`) over `<Name>/hpo/studies.db` and the plan, writing each study's summary and figures under `<Name>/Results/hpo/`; prints `{results, summaries, notes, python}` |
| `status` | `--target <repo> --name <Name>`: reads `<Name>/Results/hpo/*/summary.json` and prints each study's `study`, `arm`, `fold`, `trials`, `complete`, `pruned`, `bestValue`, `bestParams`, `topParameter`, `evaluator`, `figures` and `missingFigures`, plus `missingStudies` against the plan, `unreadable` and the `stage` reached |

Success prints one JSON object on stdout. A refusal prints
`{"error", "message", "objective"}` on stderr and exits 2.

### Error codes

| Error code | Meaning |
|---|---|
| `plan-missing` | the plan file does not exist |
| `plan-invalid` | the plan is not schema 1: not JSON, a missing key, a bad objective, arms, pruner, `nTrials` or `maxEpochs` |
| `unequal-budget` | `nTrials` is given per arm; one budget holds for every arm, baselines included |
| `unseeded-sampler` | `sampler.seed` is missing or not a whole number |
| `bad-space` | no parameter, a duplicate, an unknown kind, `low >= high`, `log` with `low <= 0`, or a categorical with fewer than two choices |
| `tunes-fixed` | a parameter in `space` is listed in `fixed`: an independent variable under test is never tuned |
| `not-nested` | more than one outer fold and no `innerValidation` statement |
| `bad-evaluator` | the importance evaluator is outside the closed set, unseeded where it or its `check` takes a seed, or its `check` repeats it |
| `timing-missing` | `--timing` names no file, or `--host` was given without `--timing`: run the timing probe first |
| `timing-invalid` | the timing record is not schema 1 or 2, a schema 2 record fails remote-parallelism's reader, or a measurement lacks a host, a device, unit `epoch` or a positive `secondsPerUnit` |
| `mixed-devices` | one host (schema 1) or one candidate (schema 2) was timed on more than one device; timing is never pooled across machines |
| `target-missing` | `--target` is not a directory |
| `bad-name` | `--name` is not one product folder name |
| `storage-missing` | `<Name>/hpo/studies.db` does not exist: the search has not run, or its storage was not fetched |
| `venv-missing` | the target has no `.venv` interpreter, or `--python` names no file |
| `optuna-missing` | that interpreter cannot import optuna and matplotlib |
| `report-failed` | `optuna_report.py` exited non-zero or printed no JSON |

## Compatibility

Runs unchanged under **Claude Code, OpenCode and Pi**: `hpo_cli.py` is plain
`python3` with no third-party imports, no network and no API keys.
`optuna_report.py` is the one script that imports the search library and
matplotlib, and it runs only under the target's own venv, never the system
Python.

## Output Reporting

For `plan`, report whether it passed, the studies it names, the total trial
count and, with a timing record, each host's range and formula, every host
that reads `unmeasured`, and that the range is an upper bound shown before the
search, never authorization. For `report` and `status`, report per study the
best value and parameters, the top parameter by the named evaluator, the
figures written and every note, and say that importance and contours are
descriptive. Speak the user's language; flags, paths and field names are never
translated.
