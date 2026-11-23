---
name: hardware
description: "Trigger: a hardware workspace (`smith init --kind hardware`, or `smith kind set hardware`) builds an open hardware or instrument paper in the HardwareX template (`/hardware [status|<stage>]`). Routes each stage to the shared tools (the study protocol whose lock signs the specifications, G-SPEC; the measurement core's instruments, registered raw files and uncertainty budgets, G-CALIBRATION; agreement with a reference device, G-AGREEMENT; ethics, registration and participant flow when people take part; the `hardwarex` and `gum-reporting` checklists; the `measurement-science` final judge) and reports where the work stands. Never generates measurements or data and never records a decision on the operator's behalf."
---

# Hardware or instrument

This is the line skill of a hardware workspace: a device, sensor or
instrument the operator designs, builds and validates against a reference
device, written in the HardwareX article template. It owns no script and no
record of its own. It routes each stage to the shared tools and assembles
their status into one overview, so the agent always knows the next step the
work owes. The workspace's `CLAUDE.md` (and every other harness entrypoint)
states the line's flow; this skill follows it.

The catalogue type is `hardware` (`python -m skills._core.paper_types.registry
list`); it has no variants and names its checklist on the family: `hardwarex`
(the HardwareX article template). Every uncertainty is also checked against
`gum-reporting` (GUM clause 7), and the final judge uses the
`measurement-science` rubric.

## When to use it

- `/hardware` or `/hardware status`: the overview below, then the next step.
- `/hardware <stage>` (`specifications`, `design`, `build`, `calibration`,
  `agreement`, `validation`, `open`, `writing`, `checklist`): run that
  stage's tools as the table below says, after checking the stage before it.

An experimental, review or observational workspace never receives this
skill; there, `/paper-type` and `smith kind set` decide whether the idea
moves to this line.

## Status overview

Run each command from the workspace root and read its JSON:

```bash
python skills/_core/empirical/study_cli.py status --root .
python skills/_core/measurement/measure_cli.py status --root .
python skills/_core/participant_flow/flow_cli.py status --root .
python skills/_core/checklists/checklist_cli.py check --guideline hardwarex --root . --json
python skills/_core/checklists/checklist_cli.py check --guideline gum-reporting --root . --json
```

Report, in the operator's language, one line per stage (the signed
specifications and their amendments, each instrument and its calibration due
date, the registered raw files, each uncertainty budget and whether it is
current, the agreement with the reference device, ethics and registration
when people take part, the checklist items satisfied, missing or needing
judgment), each with its state as the tools printed it, then the first stage
that is not done and the command that does it. Copy states, values and counts
from the JSON; never estimate one.

## Stages and their tools

| Stage | Who acts | Gate or record |
|---|---|---|
| Specifications | the agent drafts with the operator (`/study-protocol-deliberation`); the operator approves | G-SPEC, `study/protocol.lock.json` |
| Design files and bill of materials | the operator | the open repository, the `repository-url` declaration |
| Build | the operator | the build steps and photographs the operator keeps |
| Calibration and uncertainty | the operator records instruments and raw files; the agent computes the budgets | G-CALIBRATION, `study/instruments.json`, `study/measurements.json`, `study/uncertainty/` |
| Agreement | the agent computes from the operator's registered files | G-AGREEMENT, `study/agreement.json` |
| Validation with people | the operator, only when people take part | the ethics and registration records, `study/flow.json` and its sign-off |
| Writing | the agent, from the records (`/paper-writing`) | the HardwareX section contracts in `sections/` |
| Checklist and judge | the agent reports; the operator decides | `hardwarex`, `gum-reporting`, `paper-reviewer` on the `measurement-science` rubric |

G-SPEC is the study protocol's lock: the protocol revision holds the
requirements and specifications (what the hardware must measure, the primary
performance outcome and its acceptance criterion, the secondary
specifications, the validation design and the number of units, replicates and
paired readings), and the operator's approval pins it by its hash.

The commands of each stage, run from the workspace root; `<...>` is a value
the operator gives or a record names, never one the agent invents:

```bash
# Specifications (after /study-protocol-deliberation)
python skills/_core/empirical/study_cli.py protocol approve --root . --by <operator>
python skills/_core/empirical/study_cli.py protocol amend --root . --by <operator> --reason <why>
# Design files and bill of materials
python skills/paper-writing/scripts/paper_cli.py declare --declaration repository-url --value <url>
# Calibration and uncertainty
python skills/_core/measurement/measure_cli.py instrument add --root . --id <id> --model <model> --serial <serial> --resolution <value unit> --calibration-certificate <certificate> --calibrated <date> --due <date> --by <operator>
python skills/_core/measurement/measure_cli.py instrument status --root .
python skills/_core/measurement/measure_cli.py data register --root . --file <csv> --quantity <name> --unit <unit> --instrument <id> --by <operator>
python skills/_core/measurement/measure_cli.py uncertainty compute --root . --quantity <name>
python skills/_core/measurement/measure_cli.py uncertainty status --root .
# Agreement with the reference device (both files registered first)
python skills/_core/measurement/measure_cli.py agreement compute --root . --device-file <csv> --reference-file <csv> --pair-column <column>
python skills/_core/measurement/measure_cli.py agreement status --root .
# Validation with people (each also takes --not-applicable --reason <why>)
python skills/_core/empirical/study_cli.py ethics record --root . --by <operator> --committee <name> --code <code> --date <date> --consent <route>
python skills/_core/empirical/study_cli.py registration record --root . --by <operator> --registry <name> --id <id> --date <date>
python skills/_core/participant_flow/flow_cli.py template strobe --root . --write
python skills/_core/participant_flow/flow_cli.py signoff --root . --by <operator>
# Checklist and judge
python skills/_core/checklists/checklist_cli.py check --guideline hardwarex --root .
python skills/_core/checklists/checklist_cli.py check --guideline gum-reporting --root .
python skills/paper-writing/scripts/paper_cli.py verify
python skills/paper-writing/scripts/paper_cli.py review --input <round.json>
```

`study_cli.py` lives in `skills/_core/empirical/`, `measure_cli.py` in
`skills/_core/measurement/`, `flow_cli.py` in `skills/_core/participant_flow/`,
`checklist_cli.py` in `skills/_core/checklists/` and `paper_cli.py` in
`skills/paper-writing/scripts/`. Each prints one JSON object and refuses with
a typed error when its input is missing; read the refusal and report it,
never work around it.

## What it never does

- It never generates, simulates, imputes or edits a measurement, a reading,
  a price or a participant count. The operator produces every raw file and
  registers it; `measure_cli.py` binds the file by its hash and never writes
  into it. A datasheet value is never reported as a measurement of this
  hardware.
- It never records an instrument, a calibration, a registered file, a
  protocol approval or amendment, an ethics approval, a consent route, a
  registration or a sign-off on the operator's behalf: every such command
  takes the operator's name with `--by`, given by the operator in this
  conversation. `--allow-past-due` is the operator's decision, with the
  operator's reason.
- It never chooses or changes the primary performance outcome or its
  acceptance criterion; that is the operator's decision in the protocol, and
  a change is an amendment.
- It never reports a budget or an agreement the status marks stale, and never
  marks a checklist item satisfied that the checklist engine reports as
  `needs-judgment`.
