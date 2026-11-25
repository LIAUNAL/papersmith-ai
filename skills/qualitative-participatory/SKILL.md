---
name: qualitative-participatory
description: "Trigger: a qualitative-participatory workspace (`smith init --kind qualitative-participatory`, or `smith kind set qualitative-participatory`) builds a qualitative or mixed-methods study, an expert consensus or foresight study, or an experience report (`/qualitative-participatory [status|<stage>]`). Routes each stage to the shared empirical tools and the qualitative core (protocol and its lock, ethics and consent, transcript registrations, consensus panel, plan and rounds, MICMAC, codebook versions and the theme sign-off, verbatim quotes, the srqr, coreq or accord checklist, the qualitative-study final judge) and reports where the study stands. Never generates data, never writes or edits a transcript, never invents or polishes a quote, never enters a rating and never records a decision on the operator's behalf."
---

# Qualitative, participatory or consensus study

This is the line skill of a qualitative-participatory workspace: a study built
on people's accounts and judgement. It owns no script and no record of its
own. It routes each stage to the shared empirical tools and the qualitative
core and assembles their status into one overview, so the agent always knows
the next step the study owes. The workspace's `CLAUDE.md` (and every other
harness entrypoint) states the line's flow; this skill follows it.

The catalogue type is `qualitative-participatory`
(`python -m skills._core.paper_types.registry list`). Its variant, agreed with
`/paper-type` and recorded in `.papersmith/paper_type.json`, chooses the
reporting checklist:

| Variant | What it is | Checklist |
|---|---|---|
| `qualitative-mixed` | case studies, interviews, focus groups, participatory research and mixed-methods designs | `srqr` (SRQR); `coreq` (COREQ) is the alternative for a study of interviews or focus groups |
| `consensus-foresight` | expert panels: Delphi, structural foresight (MICMAC, MACTOR), scenarios, practice guidelines agreed by consensus | `accord` (ACCORD) |
| `experience-report` | a teaching innovation or a programme described with what it taught, without a formal evaluation of its effect | none: the final judge and the operator's judgment only |

The catalogue names `srqr` for the qualitative-mixed variant; when the study
rests on interviews or focus groups, the operator may report against `coreq`
instead, and the final judge accepts either.

## When to use it

- `/qualitative-participatory` or `/qualitative-participatory status`: the
  overview below, then the next step.
- `/qualitative-participatory <stage>` (`protocol`, `ethics`, `fieldwork`,
  `rounds`, `analysis`, `writing`, `quotes`, `checklist`): run that stage's
  tools as the table below says, after checking the stage before it.

An experimental, review or other empirical workspace never receives this
skill; there, `/paper-type` and `smith kind set` decide whether the idea moves
to this line.

## Status overview

Run each command from the workspace root and read its JSON; `<id>` is the
variant's checklist (`srqr`, `coreq` or `accord`; none for an experience
report):

```bash
python skills/_core/empirical/study_cli.py status --root .
python skills/_core/qualitative/qual_cli.py status --root .
python skills/_core/qualitative/consensus_cli.py status --root .
python skills/_core/qualitative/consensus_cli.py round status --root .
python skills/_core/qualitative/consensus_cli.py micmac status --root .
python skills/_core/checklists/checklist_cli.py check --guideline <id> --root . --json
```

Report, in the operator's language, one line per stage (protocol lock and its
amendments, ethics record, transcripts registered and current with their
counts by kind, codebook version, theme sign-off current or stale, consensus
plan, panel size, rounds recorded and current with the items at consensus,
MICMAC computation current or stale, checklist items satisfied, missing or
needing judgment), each with its state as the tools printed it, then the first
stage that is not done and the command that does it. A qualitative or mixed
study has no consensus records and a consensus study may have no transcripts:
report an absent record of the other variant as not used, never as owed. Copy
states, counts and identifiers from the JSON; never estimate one. No tool
prints a transcript's text or a member's comment, and the agent never opens a
transcript to report on it.

## Stages and their tools

| Stage | Who acts | Gate or record |
|---|---|---|
| Case, panel or experience and its framework | the agent drafts with the operator (`/study-protocol-deliberation`); the operator approves; a consensus study records its plan | G-STUDY-PROTOCOL (optional for an experience report), `study/protocol.lock.json`, the consensus plan under `study/consensus/` |
| Ethics and consent | the operator records the approval and the consent route, consent to be quoted included | G-ETHICS (not applicable allowed for an experience report without participant data), `study/ethics.json` |
| Fieldwork, rounds or implementation | the operator conducts, transcribes, de-identifies and registers every file; a consensus study registers its panel and each round's responses | G-TRANSCRIPTS (qualitative or mixed), `study/transcripts.json`; G-ROUNDS (consensus), `study/consensus/` |
| Coding, consensus or reflection | the agent may propose codes and themes in a draft; the operator records each codebook version and signs the themes off; the operator records the MICMAC computation | G-ANALYSIS, `study/codebook.json`, `study/themes.json` |
| Integration with prior work | the agent, from the accepted state of the art and the literature the introduction names | the discussion's integration block |
| Writing | the agent, from the records (`/paper-writing`); quotes only as `\pquote{<code>}{<text>}` | `ethics-approval` declaration, the protocol fact |
| Quotes, checklist and judge | the agent runs the checks and reports; the operator decides | `qual_cli.py quotes check`, `srqr`, `coreq` or `accord`, `paper-reviewer` on the `qualitative-study` rubric |

The commands of each stage, run from the workspace root; `<...>` is a value
the operator gives or a record names, never one the agent invents:

```bash
# Case, panel or experience and its framework (after /study-protocol-deliberation)
python skills/_core/empirical/study_cli.py protocol approve --root . --by <operator>
python skills/_core/empirical/study_cli.py protocol amend --root . --by <operator> --reason <why>
python skills/_core/qualitative/consensus_cli.py plan record --root . --rounds <n> --threshold <percent> --scale <scale> --agree-from <rating> --by <operator>
# Ethics and consent (otherwise --not-applicable --reason <why>)
python skills/_core/empirical/study_cli.py ethics record --root . --by <operator> --committee <name> --code <code> --date <date> --consent <route>
# Fieldwork: one registration per participant and file (add --kind focus-group, field-note or document when it applies)
python skills/_core/qualitative/qual_cli.py transcripts add --root . --file <file> --participant <code> --consent <how consent was given> --deidentified <how it was de-identified> --by <operator>
python skills/_core/qualitative/qual_cli.py transcripts status --root .
# Rounds: the panel by anonymised codes, then each round's response file in order
python skills/_core/qualitative/consensus_cli.py panel add --root . --member <code> --expertise <expertise> --by <operator>
python skills/_core/qualitative/consensus_cli.py round record --root . --round <k> --file <responses> --by <operator>
# Coding, consensus or reflection
python skills/_core/qualitative/qual_cli.py codebook record --root . --file <codebook> --by <operator>
python skills/_core/qualitative/qual_cli.py codebook status --root .
python skills/_core/qualitative/qual_cli.py themes signoff --root . --file <themes> --by <operator>
python skills/_core/qualitative/qual_cli.py themes status --root .
python skills/_core/qualitative/consensus_cli.py round status --root .
python skills/_core/qualitative/consensus_cli.py micmac compute --root . --file <matrix> --by <operator>
# Writing (inside /paper-writing; when the study has a protocol)
python skills/paper-writing/scripts/paper_cli.py mark revisions --root protocol --revision-prefix v --ordinal-digits 2
# Quotes, checklist and judge
python skills/_core/qualitative/qual_cli.py quotes check --root .
python skills/_core/checklists/checklist_cli.py check --guideline srqr --root .
python skills/_core/checklists/checklist_cli.py check --guideline coreq --root .
python skills/_core/checklists/checklist_cli.py check --guideline accord --root .
python skills/paper-writing/scripts/paper_cli.py verify
python skills/paper-writing/scripts/paper_cli.py review --input <round.json>
```

A participant quote is written in the paper as `\pquote{<code>}{<text>}`,
with the participant's registered code and the transcript's words verbatim,
and defined once in the preamble, for example:

```latex
\newcommand{\pquote}[2]{``#2''~(#1)}
```

`qual_cli.py quotes check` and `paper_cli.py verify` (`quote-not-verbatim`)
fail on a quote that is not found word for word in a current transcript of
that participant; the fix is the transcript's own words, never a closer
paraphrase.

`study_cli.py` lives in `skills/_core/empirical/`, `qual_cli.py` and
`consensus_cli.py` in `skills/_core/qualitative/` (see
`skills/_core/qualitative/README.md`), `checklist_cli.py` in
`skills/_core/checklists/` and `paper_cli.py` in
`skills/paper-writing/scripts/`. Each prints one JSON object and refuses with
a typed error when its input is missing; read the refusal and report it, never
work around it.

## What it never does

- It never generates data: it never writes, imputes, edits or simulates a
  record of the study, and never lets a toy set or a synthetic interview stand
  in for the study's material.
- It never writes or edits a transcript, never invents or polishes a quote
  and never enters a rating: it never transcribes on the operator's behalf,
  never alters a registered file, never prints a transcript or a member's
  comment, and never writes a quote that is not the transcript's own words.
- It never recruits participants or panel members, conducts an interview or
  a round, or collects material: ethics, consent, data collection and the
  analytic sign-off stay human.
- It never records a protocol approval or amendment, a consensus plan, an
  ethics record, a transcript registration, a panel member, a round, a
  codebook version, a theme sign-off or a MICMAC computation on the
  operator's behalf: every such command takes the operator's name with
  `--by`, given by the operator in this conversation. It may propose codes and
  themes in a draft file; only the operator records them.
- It never presents an item below the pre-specified threshold as consensus,
  never claims an effect for an experience report, never passes a gate and
  never marks a checklist item satisfied that the checklist engine reports as
  `needs-judgment`.
