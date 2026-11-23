---
name: observational-measurement
description: "Trigger: an observational-measurement workspace (`smith init --kind observational-measurement`, or `smith kind set observational-measurement`) builds an observational, diagnostic-validation or measurement-instrument study (`/observational-measurement [status|<stage>]`). Routes each stage to the shared empirical tools (study protocol and its lock, ethics and registration records, own data with dictionary, QC and de-identification, the labelled analysis log, the participant flow, the reporting checklist of the agreed variant: STROBE, STARD 2015 or COSMIN) and reports where the study stands. Never generates measurements or data and never records a decision on the operator's behalf."
---

# Observational and measurement study

This is the line skill of an observational-measurement workspace: a study of
data the operator collects or holds, without assigning an intervention. It
owns no script and no record of its own. It routes each stage to the shared
empirical tools and assembles their status into one overview, so the agent
always knows the next step the study owes. The workspace's `CLAUDE.md` (and
every other harness entrypoint) states the line's flow; this skill follows it.

The catalogue type is `observational-measurement`; its variants choose the
reporting checklist (`python -m skills._core.paper_types.registry list`, the
variant's `checklist`):

| Variant | Reporting checklist | Participant flow template |
|---|---|---|
| `observational` | `strobe` (STROBE) | `strobe` |
| `diagnostic-validation` | `stard-2015` (STARD 2015) | `stard-2015` |
| `measurement-instrument` | `cosmin` (COSMIN Reporting Guideline 2.0) | `strobe`, when participants are sampled |

The agreed variant is `agreed_variant` in `.papersmith/paper_type.json`. When
none is recorded, ask the operator which variant the study is and suggest
`/paper-type`; never pick one for them.

## When to use it

- `/observational-measurement` or `/observational-measurement status`: the
  overview below, then the next step.
- `/observational-measurement <stage>` (`protocol`, `ethics`, `registration`,
  `data`, `analysis`, `flow`, `writing`, `checklist`): run that stage's tools
  as the table below says, after checking the stage before it.

An experimental or review workspace never receives this skill; there,
`/paper-type` and `smith kind set` decide whether the idea moves to this line.

## Status overview

Run each command from the workspace root and read its JSON:

```bash
python skills/_core/empirical/study_cli.py status --root .
python skills/_core/empirical/analysis_cli.py status --root .
python skills/_core/participant_flow/flow_cli.py status --root .
python skills/datasets/scripts/datasets_cli.py --root . status
python skills/_core/checklists/checklist_cli.py check --guideline <the variant's checklist> --root . --json
```

Report, in the operator's language, one line per stage (protocol lock and its
amendments, ethics, registration, data with dictionary, QC and
de-identification, analysis runs with their confirmatory or exploratory
label, participant flow and its sign-off, checklist items satisfied, missing
or needing judgment), each with its state as the tools printed it, then the
first stage that is not done and the command that does it. Copy states and
counts from the JSON; never estimate one.

## Stages and their tools

| Stage | Who acts | Tools |
|---|---|---|
| Protocol | the agent drafts with the operator; the operator approves | `/study-protocol-deliberation`; `study_cli.py protocol approve\|amend --by <operator>` (G-STUDY-PROTOCOL) |
| Ethics | the operator | `study_cli.py ethics record --by <operator>` (or `--not-applicable --reason`) |
| Registration | the operator | `study_cli.py registration record --by <operator>` (or `--not-applicable --reason`) |
| Data | the operator collects; the agent runs the checks | `datasets_cli.py --root . own --by <operator>`, `dictionary init\|check`, `qc`, `deidentify --by <operator>` |
| Analysis | the agent wraps the operator's analysis; the operator attests GUI work | `analysis_cli.py run ... -- <command>`, `analysis_cli.py record --by <operator>`, `analysis_cli.py status` |
| Participant flow | the operator enters the counts and signs | `flow_cli.py template strobe\|stard-2015 --write`, `check`, `render`, `signoff --by <operator>` |
| Writing | the agent, from the records | `/paper-writing` (study facts with `paper_cli.py observe --protocol protocol --flow study/flow.json`; declarations `study-registration` and `ethics-approval`) |
| Checklist and judge | the agent reports; the operator decides | `checklist_cli.py check --guideline <id>`, `paper_cli.py verify`, `paper-reviewer` on the `empirical-study` rubric |

`study_cli.py` and `analysis_cli.py` live in `skills/_core/empirical/`,
`flow_cli.py` in `skills/_core/participant_flow/`, `checklist_cli.py` in
`skills/_core/checklists/`, `datasets_cli.py` in `skills/datasets/scripts/` and
`paper_cli.py` in `skills/paper-writing/scripts/`. Each prints one JSON object
and refuses with a typed error when its input is missing; read the refusal and
report it, never work around it.

## What it never does

- It never generates, simulates, imputes or edits a measurement, a datum or a
  participant-flow count. The operator collects the data and enters the
  counts; a toy set (`datasets_cli.py synth`) never stands in for study data.
- It never records an ethics approval, a consent route, a registration, a
  data-use statement, a de-identification, a protocol approval or amendment,
  or a sign-off on the operator's behalf: every such command takes the
  operator's name with `--by`, given by the operator in this conversation.
- It never chooses or changes the primary outcome; that is the operator's
  decision in the protocol, and a change is an amendment.
- It never relabels an exploratory analysis as confirmatory; the label is
  computed by `analysis_cli.py` from the locked protocol.
- It never passes a gate or marks a checklist item satisfied that the
  checklist engine reports as `needs-judgment`.
