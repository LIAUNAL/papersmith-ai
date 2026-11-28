---
name: data-resource
description: "Trigger: a data-resource workspace builds a data descriptor for a corpus, dataset or benchmark (`/data-resource [status|<stage>]`). Routes each stage to the shared empirical tools and reports where it stands; never alters data."
---

# Data resource

**Scope.** A data-resource workspace (`smith init --kind data-resource`, or `smith kind set data-resource`) builds a data descriptor for a corpus, dataset or benchmark the operator collected (`/data-resource [status|<stage>]`). Routes each stage to the shared empirical tools and the datasets skill (collection protocol and its lock, ethics and consent, own-data statement or licence, data dictionary, quality checks and de-identification, the labelled analysis log for baselines, the operator's deposit record, the datasheets checklist, the data-descriptor final judge) and reports where the resource stands. Never generates, labels or alters data and never records a decision on the operator's behalf.

This is the line skill of a data-resource workspace: a corpus, dataset or
benchmark that the operator collected and releases, written as a data
descriptor (background and summary, methods, data records, technical
validation, usage notes, code availability). It owns no script and no record
of its own. It routes each stage to the shared empirical tools and the
datasets skill and assembles their status into one overview, so the agent
always knows the next step the resource owes. The workspace's `CLAUDE.md`
(and every other harness entrypoint) states the line's flow; this skill
follows it.

The catalogue type is `data-resource`
(`python -m skills._core.paper_types.registry list`); it has no variants and
reports on the `datasheets` checklist (Datasheets for Datasets, Gebru et al.,
Commun. ACM 2021), whose items target the data descriptor's sections.

## When to use it

- `/data-resource` or `/data-resource status`: the overview below, then the
  next step.
- `/data-resource <stage>` (`protocol`, `ethics`, `dictionary`, `qc`,
  `baselines`, `deposit`, `writing`, `checklist`): run that stage's tools as
  the table below says, after checking the stage before it.

An experimental, review or other empirical workspace never receives this
skill; there, `/paper-type` and `smith kind set` decide whether the idea moves
to this line.

## Status overview

Run each command from the workspace root and read its JSON:

```bash
python skills/_core/empirical/study_cli.py status --root .
python skills/datasets/scripts/datasets_cli.py --root . status
python skills/_core/empirical/analysis_cli.py status --root .
python skills/_core/checklists/checklist_cli.py check --guideline datasheets --root . --json
```

Report, in the operator's language, one line per stage (protocol lock and its
amendments, ethics record, own-data statement or licence decision, dictionary
valid or not, quality report current or stale and any de-identification owed,
baseline runs with their confirmatory or exploratory label, deposit recorded,
current or stale, checklist items satisfied, missing or needing judgment),
each with its state as the tools printed it, then the first stage that is not
done and the command that does it. Copy states, counts and identifiers from
the JSON; never estimate one.

## Stages and their tools

| Stage | Who acts | Gate or record |
|---|---|---|
| Collection protocol | the agent drafts with the operator (`/study-protocol-deliberation`); the operator approves | G-STUDY-PROTOCOL, `study/protocol.lock.json` |
| Ethics, consent and licence | the operator records the ethics approval (or why none applies) and the own-data statement or the source's licence | G-ETHICS, `study/ethics.json`, `datasets/registry.json` |
| Collection, curation and documentation | the operator collects and writes every data file; the agent scaffolds the dictionary, the operator completes it | `datasets/<slug>/dictionary.json` |
| Quality checks | the agent runs the checks on the operator's files; the operator de-identifies personal data and records how | G-DATA-QC, `datasets/<slug>/qc.json` |
| Baselines | the agent wraps the operator's preprocessing, agreement and baseline scripts; the operator attests GUI work | `analysis/log.jsonl`, each entry labelled confirmatory or exploratory |
| Deposit | the operator deposits the files and records the identifier and licence | G-DEPOSIT, the deposit record in `datasets/registry.json` |
| Writing | the agent, from the records (`/paper-writing`) | study facts: protocol, sample, outcomes, analysis plan |
| Checklist and judge | the agent reports; the operator decides | `datasheets`, `paper-reviewer` on the `data-descriptor` rubric |

The protocol's primary outcome is the variable or label the resource is built
to measure, and its sample size is the planned number of sources,
participants or records. The commands of each stage, run from the workspace
root; `<...>` is a value the operator gives or a record names, never one the
agent invents:

```bash
# Collection protocol (after /study-protocol-deliberation)
python skills/_core/empirical/study_cli.py protocol approve --root . --by <operator>
python skills/_core/empirical/study_cli.py protocol amend --root . --by <operator> --reason <why>
# Ethics, when the records come from people (otherwise --not-applicable --reason <why>)
python skills/_core/empirical/study_cli.py ethics record --root . --by <operator> --committee <name> --code <code> --date <date> --consent <route>
# The right to release: own data, or the licence of a third-party source
python skills/datasets/scripts/datasets_cli.py --root . own --slug <slug> --by <operator> --statement <how the data may be used>
python skills/datasets/scripts/datasets_cli.py --root . license --slug <slug> --source-license <licence as the source states it>
# Curation and documentation
python skills/datasets/scripts/datasets_cli.py --root . dictionary init --slug <slug> --file <csv>
python skills/datasets/scripts/datasets_cli.py --root . dictionary check --slug <slug>
# Quality checks (add --label <column> and --group <column> when the records carry them)
python skills/datasets/scripts/datasets_cli.py --root . qc --slug <slug> --file <csv>
python skills/datasets/scripts/datasets_cli.py --root . deidentify --slug <slug> --by <operator> --statement <how>
# Baselines, preprocessing and annotator agreement
python skills/_core/empirical/analysis_cli.py run --root . --outcome <id> --script <code> --input <data> --output <result> -- <command>
python skills/_core/empirical/analysis_cli.py record --root . --outcome <id> --by <operator> --tool <name>
python skills/_core/empirical/analysis_cli.py status --root .
# Deposit, after the operator deposited the files (add --scheme handle|ark|accession for a non-DOI identifier)
python skills/datasets/scripts/datasets_cli.py --root . deposit --slug <slug> --repository <repository> --identifier <identifier> --license <licence> --by <operator>
python skills/datasets/scripts/datasets_cli.py --root . status
# Writing (inside /paper-writing)
python skills/paper-writing/scripts/paper_cli.py mark revisions --root protocol --revision-prefix v --ordinal-digits 2
python skills/paper-writing/scripts/paper_cli.py observe --report <report> --protocol protocol
# Checklist and judge
python skills/_core/checklists/checklist_cli.py check --guideline datasheets --root .
python skills/paper-writing/scripts/paper_cli.py verify
python skills/paper-writing/scripts/paper_cli.py review --input <round.json>
```

`study_cli.py` and `analysis_cli.py` live in `skills/_core/empirical/`,
`datasets_cli.py` in `skills/datasets/scripts/` (see `skills/datasets/SKILL.md`),
`checklist_cli.py` in `skills/_core/checklists/` and `paper_cli.py` in
`skills/paper-writing/scripts/`. Each prints one JSON object and refuses with
a typed error when its input is missing; read the refusal and report it, never
work around it.

## What it never does

- It never generates, labels or alters data: it never writes, imputes,
  relabels, filters or resamples a record of the resource, never annotates
  on the annotators' behalf, and never lets a toy set (`/datasets synth`)
  stand in for the resource.
- It never collects data, contacts participants, deposits files or uploads
  anything: collection, consent, licence and deposit stay human.
- It never records an ethics approval, an own-data statement, a licence
  decision, a de-identification, a protocol approval or amendment, or a
  deposit on the operator's behalf: every such command takes the operator's
  name with `--by`, given by the operator in this conversation.
- It never chooses or changes the primary outcome, the sources, the annotation
  scheme or the licence; those are the operator's decisions in the protocol
  and the registry, and a change is an amendment or a new record.
- It never relabels an exploratory baseline as confirmatory; the label is
  computed by `analysis_cli.py` from the locked protocol.
- It never passes a gate or marks a checklist item satisfied that the
  checklist engine reports as `needs-judgment`.
