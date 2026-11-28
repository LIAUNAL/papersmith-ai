---
name: lab-simulation
description: "Trigger: a lab-simulation workspace builds a laboratory, materials or modelling-simulation study (`/lab-simulation [status|<stage>]`). Routes each stage to the shared empirical tools and the measurement core; never generates data."
---

# Laboratory and simulation study

**Scope.** A lab-simulation workspace (`smith init --kind lab-simulation`, or `smith kind set lab-simulation`) builds a laboratory or simulation study, variant materials or modelling-simulation (`/lab-simulation [status|<stage>]`). Routes each stage to the shared empirical tools and the measurement core (study protocol and its lock, instruments and calibration against known values, registered raw data, GUM uncertainty budgets, the labelled analysis log, the gum-reporting checklist, the measurement-science final judge) and reports where the study stands. Never generates measurements or data and never records a decision on the operator's behalf.

This is the line skill of a lab-simulation workspace: a physical-science study
that defines its samples or its model, calibrates against known values, sweeps
its conditions or parameters and reports every value with its GUM
uncertainty. It owns no script and no record of its own. It routes each stage
to the shared empirical tools and the measurement core and assembles their
status into one overview, so the agent always knows the next step the study
owes. The workspace's `CLAUDE.md` (and every other harness entrypoint) states
the line's flow; this skill follows it.

The catalogue type is `lab-simulation`
(`python -m skills._core.paper_types.registry list`); both variants report on
the `gum-reporting` checklist (GUM, JCGM 100:2008, clause 7):

| Variant | The study defines | Methods block | Results block |
|---|---|---|---|
| `materials` | the sample matrix: synthesis, deposition or processing, and the characterization techniques | `m-sample-matrix` | `r-sample-characterization` |
| `modelling-simulation` | the model, its solver, its parameters and its convergence | `m-model-definition` | `r-model-verification` |

The agreed variant is `agreed_variant` in `.papersmith/paper_type.json`. When
none is recorded, ask the operator which variant the study is and suggest
`/paper-type`; never pick one for them. A variant block of the other variant
stays unopened.

## When to use it

- `/lab-simulation` or `/lab-simulation status`: the overview below, then the
  next step.
- `/lab-simulation <stage>` (`protocol`, `calibration`, `data`,
  `uncertainty`, `analysis`, `open-data`, `writing`, `checklist`): run that
  stage's tools as the table below says, after checking the stage before it.

An experimental, review or other empirical workspace never receives this
skill; there, `/paper-type` and `smith kind set` decide whether the idea moves
to this line.

## Status overview

Run each command from the workspace root and read its JSON:

```bash
python skills/_core/empirical/study_cli.py status --root .
python skills/_core/measurement/measure_cli.py status --root .
python skills/_core/empirical/analysis_cli.py status --root .
python skills/_core/checklists/checklist_cli.py check --guideline gum-reporting --root . --json
```

Report, in the operator's language, one line per stage (protocol lock and its
amendments, instruments and the state of each calibration, registered data
files and any changed since registration, uncertainty budgets current or
stale, analysis runs with their confirmatory or exploratory label, checklist
items satisfied, missing or needing judgment), each with its state as the
tools printed it, then the first stage that is not done and the command that
does it. Copy states, values and counts from the JSON; never estimate one.

## Stages and their tools

| Stage | Who acts | Gate or record |
|---|---|---|
| Sample matrix or model | the operator decides; the agent writes it into the protocol draft | the design of the protocol |
| Protocol | the agent drafts with the operator (`/study-protocol-deliberation`); the operator approves | G-STUDY-PROTOCOL, `study/protocol.lock.json` |
| Calibration | the operator records each instrument from its certificate and measures the known values | G-CALIBRATION, `study/instruments.json` |
| Data | the operator measures or runs the model and registers each raw file | `study/measurements.json` (sha256 per file) |
| Uncertainty | the agent computes the budgets from the registered files and instruments | `study/uncertainty/<quantity>.json` |
| Analysis | the agent wraps the operator's fits, sweeps and model runs; the operator attests GUI work | `analysis/log.jsonl`, each entry labelled confirmatory or exploratory |
| Open data and code | the operator deposits the files and the code | the `repository-url` declaration |
| Writing | the agent, from the records (`/paper-writing`) | study facts: protocol, sample, outcomes, analysis plan |
| Checklist and judge | the agent reports; the operator decides | `gum-reporting`, `paper-reviewer` on the `measurement-science` rubric |

The protocol's primary outcome is the primary observable, and its sample size
is the number of replicates per condition or the parameter grid. The commands
of each stage, run from the workspace root; `<...>` is a value the operator
gives or a record names, never one the agent invents:

```bash
# Protocol (after /study-protocol-deliberation)
python skills/_core/empirical/study_cli.py protocol approve --root . --by <operator>
python skills/_core/empirical/study_cli.py protocol amend --root . --by <operator> --reason <why>
# Ethics, only when the samples come from people or animals (otherwise --not-applicable --reason <why>)
python skills/_core/empirical/study_cli.py ethics record --root . --by <operator> --committee <name> --code <code> --date <date> --consent <route>
# Calibration (add --stated-uncertainty <value-and-unit> --distribution normal|rectangular [--coverage-k <k>] from the certificate)
python skills/_core/measurement/measure_cli.py instrument add --root . --id <id> --model <model> --serial <serial> --resolution <value-and-unit> --calibration-certificate <certificate> --calibrated <date> --due <date> --by <operator>
python skills/_core/measurement/measure_cli.py instrument status --root .
# Data (one --condition <key=value> per condition; a reference material as --condition reference=<material>)
python skills/_core/measurement/measure_cli.py data register --root . --file <csv> --quantity <name> --unit <unit> --instrument <id> --replicate-column <column> --by <operator>
python skills/_core/measurement/measure_cli.py data status --root .
# Uncertainty (--level <p> or a declared --coverage-k <k>; a past-due calibration only with the operator's override)
python skills/_core/measurement/measure_cli.py uncertainty compute --root . --quantity <name>
python skills/_core/measurement/measure_cli.py uncertainty compute --root . --quantity <name> --allow-past-due --by <operator> --reason <why the readings still hold>
python skills/_core/measurement/measure_cli.py uncertainty status --root .
# Analysis: fits, comparisons, sweeps and model runs
python skills/_core/empirical/analysis_cli.py run --root . --outcome <id> --script <code> --input <data> --output <result> -- <command>
python skills/_core/empirical/analysis_cli.py record --root . --outcome <id> --by <operator> --tool <name>
python skills/_core/empirical/analysis_cli.py status --root .
# Writing (inside /paper-writing)
python skills/paper-writing/scripts/paper_cli.py mark revisions --root protocol --revision-prefix v --ordinal-digits 2
python skills/paper-writing/scripts/paper_cli.py observe --report <report> --protocol protocol
# Checklist and judge
python skills/_core/checklists/checklist_cli.py check --guideline gum-reporting --root .
python skills/paper-writing/scripts/paper_cli.py verify
python skills/paper-writing/scripts/paper_cli.py review --input <round.json>
```

`study_cli.py` and `analysis_cli.py` live in `skills/_core/empirical/`,
`measure_cli.py` in `skills/_core/measurement/` (its records and formulas in
`skills/_core/measurement/README.md`), `checklist_cli.py` in
`skills/_core/checklists/` and `paper_cli.py` in
`skills/paper-writing/scripts/`. Each prints one JSON object and refuses with
a typed error when its input is missing; read the refusal and report it, never
work around it.

## What it never does

- It never generates measurements or data: it never writes, simulates on its
  own initiative, imputes or edits a measured value, a simulated output or a
  raw data file. The operator measures, runs the model and registers each
  file; a toy set (`/datasets synth`) never stands in for study data, and a
  simulated value is never reported as a measured one.
- It never records an instrument, a calibration, a data registration, an
  ethics record, a protocol approval or amendment, or an override of a
  past-due calibration on the operator's behalf: every such command takes the
  operator's name with `--by`, given by the operator in this conversation.
- It never chooses or changes the primary observable, the sample matrix, the
  model or the parameter grid; those are the operator's decisions in the
  protocol, and a change is an amendment.
- It never relabels an exploratory analysis as confirmatory; the label is
  computed by `analysis_cli.py` from the locked protocol.
- It never passes a gate or marks a checklist item satisfied that the
  checklist engine reports as `needs-judgment`.
