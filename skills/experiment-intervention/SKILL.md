---
name: experiment-intervention
description: "Trigger: an experiment-intervention workspace (`smith init --kind experiment-intervention`, or `smith kind set experiment-intervention`) builds a trial with people or a field, crop or animal experiment (`/experiment-intervention [status|<stage>]`). Routes each stage to the shared empirical tools (protocol and its lock, prospective registration, ethics and consent, the operator's allocation record, data dictionary, quality checks and de-identification, the labelled analysis log, the flow of units, the consort-2025 or arrive-2 checklist, the empirical-study final judge) and reports where the study stands. Never generates data, never generates, reads out or alters the allocation sequence, and never records a decision on the operator's behalf."
---

# Experiment or intervention

This is the line skill of an experiment-intervention workspace: a study that
assigns a treatment and measures its effect against a control. It owns no
script and no record of its own. It routes each stage to the shared empirical
tools and assembles their status into one overview, so the agent always knows
the next step the study owes. The workspace's `CLAUDE.md` (and every other
harness entrypoint) states the line's flow; this skill follows it.

The catalogue type is `experiment-intervention`
(`python -m skills._core.paper_types.registry list`). Its variant, agreed with
`/paper-type` and recorded in `.papersmith/paper_type.json`, chooses the
reporting checklist:

| Variant | What it is | Checklist |
|---|---|---|
| `human-trial` | a clinical, educational or consumer trial that assigns an intervention to people | `consort-2025` (CONSORT 2025) |
| `field-experiment` | plots, blocks, crops or animals under controlled treatments | `arrive-2` (ARRIVE 2.0; a plot or crop experiment reports against its design and analysis items where they apply) |

## When to use it

- `/experiment-intervention` or `/experiment-intervention status`: the
  overview below, then the next step.
- `/experiment-intervention <stage>` (`protocol`, `registration`, `ethics`,
  `allocation`, `data`, `analysis`, `flow`, `writing`, `checklist`): run that
  stage's tools as the table below says, after checking the stage before it.

An experimental, review or other empirical workspace never receives this
skill; there, `/paper-type` and `smith kind set` decide whether the idea moves
to this line.

## Status overview

Run each command from the workspace root and read its JSON; `<id>` is the
variant's checklist (`consort-2025` or `arrive-2`):

```bash
python skills/_core/empirical/study_cli.py status --root .
python skills/_core/empirical/study_cli.py allocation status --root .
python skills/datasets/scripts/datasets_cli.py --root . status
python skills/_core/empirical/analysis_cli.py status --root .
python skills/_core/participant_flow/flow_cli.py status --root .
python skills/_core/checklists/checklist_cli.py check --guideline <id> --root . --json
```

Report, in the operator's language, one line per stage (protocol lock and its
amendments, registration prospective or retrospective, ethics record,
allocation record current or stale, dictionary valid or not, quality report
current or stale and any de-identification owed, analysis runs with their
confirmatory or exploratory label, flow counts valid and signed, checklist
items satisfied, missing or needing judgment), each with its state as the
tools printed it, then the first stage that is not done and the command that
does it. Copy states, counts and identifiers from the JSON; never estimate
one. The allocation status gives the method, the concealment and whether the
record is current; never open the allocation list it names.

## Stages and their tools

| Stage | Who acts | Gate or record |
|---|---|---|
| Protocol | the agent drafts with the operator (`/study-protocol-deliberation`); the operator approves | G-STUDY-PROTOCOL, `study/protocol.lock.json` |
| Registration | the operator registers the trial and records it with the first enrolment date | G-REGISTRATION (prospective for a trial with people), `study/registration.json` |
| Ethics and consent | the operator records the approval of the ethics or animal ethics committee and the consent route | G-ETHICS, `study/ethics.json` |
| Allocation, blocks and sample size | the operator generates and conceals the sequence with their own tool and records it | G-ALLOCATION, `study/allocation.json` |
| Intervention and follow-up | the operator delivers the intervention and collects every data file; the agent scaffolds the dictionary and runs the checks | G-DATA-QC, `datasets/<slug>/dictionary.json`, `datasets/<slug>/qc.json` |
| Pre-specified analysis | the agent wraps the operator's scripts; the operator attests GUI work | `analysis/log.jsonl`, each entry labelled confirmatory or exploratory |
| Flow of units | the operator enters and signs every count | G-FLOW (required for a trial with people), `study/flow.json` |
| Writing | the agent, from the records (`/paper-writing`) | study facts: protocol, sample, outcomes, analysis plan, participant flow |
| Checklist and judge | the agent reports; the operator decides | `consort-2025` or `arrive-2`, `paper-reviewer` on the `empirical-study` rubric |

The commands of each stage, run from the workspace root; `<...>` is a value
the operator gives or a record names, never one the agent invents:

```bash
# Protocol (after /study-protocol-deliberation)
python skills/_core/empirical/study_cli.py protocol approve --root . --by <operator>
python skills/_core/empirical/study_cli.py protocol amend --root . --by <operator> --reason <why>
# Registration: prospective means on or before the first enrolment (otherwise --not-applicable --reason <why>)
python skills/_core/empirical/study_cli.py registration record --root . --by <operator> --registry <name> --id <id> --date <date> --first-enrolment <date>
# Ethics and consent (otherwise --not-applicable --reason <why>)
python skills/_core/empirical/study_cli.py ethics record --root . --by <operator> --committee <name> --code <code> --date <date> --consent <route>
# Allocation: the operator's own list (add --block-size <n> and --strata <text> when they apply)
python skills/_core/empirical/study_cli.py allocation record --root . --by <operator> --file <the operator's allocation list> --method <simple, block, stratified, minimisation or cluster> --concealment <how the sequence was concealed>
python skills/_core/empirical/study_cli.py allocation status --root .
# Intervention and follow-up: the operator's data
python skills/datasets/scripts/datasets_cli.py --root . own --slug <slug> --by <operator> --statement <how the data may be used>
python skills/datasets/scripts/datasets_cli.py --root . dictionary init --slug <slug> --file <csv>
python skills/datasets/scripts/datasets_cli.py --root . dictionary check --slug <slug>
python skills/datasets/scripts/datasets_cli.py --root . qc --slug <slug> --file <csv>
python skills/datasets/scripts/datasets_cli.py --root . deidentify --slug <slug> --by <operator> --statement <how>
# Pre-specified analysis
python skills/_core/empirical/analysis_cli.py run --root . --outcome <id> --input <data> --output <result> -- <command>
python skills/_core/empirical/analysis_cli.py record --root . --outcome <id> --by <operator> --tool <name>
python skills/_core/empirical/analysis_cli.py status --root .
# Flow of units (one --arm per arm of the protocol)
python skills/_core/participant_flow/flow_cli.py template consort-2025 --root . --arm <arm> --arm <arm> --write
python skills/_core/participant_flow/flow_cli.py check --root .
python skills/_core/participant_flow/flow_cli.py render --root .
python skills/_core/participant_flow/flow_cli.py signoff --root . --by <operator>
# Writing (inside /paper-writing)
python skills/paper-writing/scripts/paper_cli.py mark revisions --root protocol --revision-prefix v --ordinal-digits 2
python skills/paper-writing/scripts/paper_cli.py observe --report <report> --protocol protocol --flow study/flow.json
# Checklist and judge
python skills/_core/checklists/checklist_cli.py check --guideline consort-2025 --root .
python skills/_core/checklists/checklist_cli.py check --guideline arrive-2 --root .
python skills/paper-writing/scripts/paper_cli.py verify
python skills/paper-writing/scripts/paper_cli.py review --input <round.json>
```

`study_cli.py` and `analysis_cli.py` live in `skills/_core/empirical/`,
`flow_cli.py` in `skills/_core/participant_flow/`, `datasets_cli.py` in
`skills/datasets/scripts/` (see `skills/datasets/SKILL.md`),
`checklist_cli.py` in `skills/_core/checklists/` and `paper_cli.py` in
`skills/paper-writing/scripts/`. Each prints one JSON object and refuses with
a typed error when its input is missing; read the refusal and report it, never
work around it.

## What it never does

- It never generates measurements or data: it never writes, imputes, edits or
  simulates a record of the study, and never lets a toy set (`/datasets
  synth`) stand in for the study's data.
- It never generates, reads out or alters the allocation sequence: it never
  opens the operator's allocation list, never prints a unit's assignment and
  never suggests one; the record holds only the list's hash.
- It never enrols participants, delivers the intervention or collects data:
  ethics, consent, data collection and the choice of primary outcome stay
  human.
- It never records a protocol approval or amendment, a registration, an
  ethics record, an allocation, an own-data statement, a de-identification or
  a flow sign-off on the operator's behalf: every such command takes the
  operator's name with `--by`, given by the operator in this conversation.
- It never presents a retrospective registration as prospective, and never
  relabels an exploratory analysis as confirmatory; the label is computed by
  `analysis_cli.py` from the locked protocol.
- It never passes a gate or marks a checklist item satisfied that the
  checklist engine reports as `needs-judgment`.
