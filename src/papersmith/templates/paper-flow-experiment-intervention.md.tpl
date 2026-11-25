## Paper construction flow (experiment-intervention line)

This workspace builds an **experiment or intervention**: a study that assigns
a treatment and measures its effect against a control, in one of two variants
with their reporting checklist: a trial with people (`human-trial`, CONSORT
2025: `consort-2025`) and a field, crop or animal experiment
(`field-experiment`, ARRIVE 2.0: `arrive-2`; a plot or crop experiment reports
against its design and analysis items where they apply). It was created with
`smith init --kind experiment-intervention` or moved here with `smith kind set
experiment-intervention` (`paper_kind: "experiment-intervention"` in
`.papersmith/config.json`). There is no proposal, no experiment campaign and
no remote run. The study keeps its records under `protocol/`, `study/`,
`datasets/` and `analysis/`, written by the shared empirical tools, and
`/experiment-intervention` routes to them and reports where the study stands
(`/experiment-intervention status`). Every tool refuses when a stage's input
is missing.

1. **Harness**: `smith status .` and `smith audit . --check-drift`;
   `/upgrade-project` when the workspace runs an older release.
2. **Plausibility and paper type**: `/plausibility <the idea in at least two
   sentences>` scouts the state of the art; on acceptance, `/paper-type`
   records the type and the variant the operator agrees in
   `.papersmith/paper_type.json`. The variant chooses the reporting
   checklist: `consort-2025` or `arrive-2`.
3. **Protocol and registration** (gates G-STUDY-PROTOCOL and
   G-REGISTRATION): `/study-protocol-deliberation` keeps the protocol as
   managed revisions `protocol/study-protocol-<slug>-vNN.md`: the research
   question, the intervention and the comparator, exactly one primary
   outcome, the secondary outcomes and the harms, the design, the
   eligibility, the sample size with its justification and the analysis
   plan. The operator approves a revision with `python
   skills/_core/empirical/study_cli.py protocol approve --root . --by
   <name>`, which pins it by its hash in `study/protocol.lock.json`; a later
   revision is an amendment (`python skills/_core/empirical/study_cli.py
   protocol amend --root . --by <name> --reason <why>`). The operator then
   records the registration (`python skills/_core/empirical/study_cli.py
   registration record --root . --by <name> --registry <name> --id <id>
   --date <date> --first-enrolment <date>`). A trial with people must be
   registered prospectively, on or before its first enrolment: a
   retrospective registration leaves G-REGISTRATION failed and the paper
   states it with its reason, never as prospective. A field experiment
   without a registry records `--not-applicable --reason <why>`.
4. **Ethics and consent** (gate G-ETHICS): the operator records the approval
   of the ethics or animal ethics committee and the consent route (`python
   skills/_core/empirical/study_cli.py ethics record --root . --by <name>
   --committee <name> --code <code> --date <date> --consent <route>`), or
   records it as not applicable (`--not-applicable --reason <why>`). Both
   records refuse until the protocol is approved and current, and an
   amendment marks them stale.
5. **Allocation, blocks and sample size** (gate G-ALLOCATION): the operator
   generates the allocation sequence with their own tool or service, keeps it
   concealed, and records it: `python skills/_core/empirical/study_cli.py
   allocation record --root . --by <name> --file <the operator's allocation
   list> --method <simple, block, stratified, minimisation or cluster>
   --concealment <how the sequence was concealed>` (with `--block-size <n>`
   and `--strata <text>` when they apply). The record binds the list's sha256
   to the protocol lock; `python skills/_core/empirical/study_cli.py
   allocation status --root .` shows it current or stale (the list changed or
   removed, or the protocol amended). For a field experiment the blocks,
   plots and experimental units are part of the locked protocol.
6. **Intervention and follow-up** (gate G-DATA-QC): the operator delivers the
   intervention and collects the data. `python
   skills/datasets/scripts/datasets_cli.py --root . own --slug <slug> --by
   <name> --statement <how it may be used>` registers it; `python
   skills/datasets/scripts/datasets_cli.py --root . dictionary init --slug
   <slug> --file <csv>` scaffolds the data dictionary the operator completes
   and `python skills/datasets/scripts/datasets_cli.py --root . dictionary
   check --slug <slug>` validates; `python
   skills/datasets/scripts/datasets_cli.py --root . qc --slug <slug> --file
   <csv>` measures its quality against the dictionary, and `python
   skills/datasets/scripts/datasets_cli.py --root . deidentify --slug <slug>
   --by <name> --statement <how>` records how the columns it flags as
   personal data were removed or transformed.
7. **Pre-specified analysis**: every analysis goes through the append-only
   log `analysis/log.jsonl`: `python skills/_core/empirical/analysis_cli.py
   run --root . --outcome <id> --input <data> --output <result> --
   <command>` wraps a script, and `python
   skills/_core/empirical/analysis_cli.py record --root . --outcome <id> --by
   <name> --tool <name>` is the operator's entry for a GUI tool. The label is
   computed, never chosen: confirmatory only for an outcome and plan entry of
   the current locked protocol, exploratory otherwise. `python
   skills/_core/empirical/analysis_cli.py status --root .` lists the runs and
   their labels.
8. **Flow of units** (gate G-FLOW, required for a trial with people): `python
   skills/_core/participant_flow/flow_cli.py template consort-2025 --root .
   --arm <arm> --arm <arm> --write` writes the empty `study/flow.json` with
   one column per arm; the operator enters every count; `python
   skills/_core/participant_flow/flow_cli.py check --root .` validates the
   arithmetic, `python skills/_core/participant_flow/flow_cli.py render --root
   .` draws `paper/Figures/participant-flow.svg` and `python
   skills/_core/participant_flow/flow_cli.py signoff --root . --by <name>`
   records the operator's sign-off, stale after any edit. A field experiment
   may keep the same flow or report its experimental units in a table.
9. **Scaffolding, declarations and writing**: `/paper-writing` opens the
   `paper/` tree from the line's section contracts in `sections/`. The study
   facts come from the records: `python
   skills/paper-writing/scripts/paper_cli.py mark revisions --root protocol
   --revision-prefix v --ordinal-digits 2` marks the protocol revisions, and
   `python skills/paper-writing/scripts/paper_cli.py observe --report
   <report> --protocol protocol --flow study/flow.json` reconciles the
   protocol, sample, outcomes, analysis plan and participant flow against
   disk. The `study-registration` and `ethics-approval` declarations repeat
   what steps 3 and 4 recorded; the randomisation is written from the
   allocation record, never from the list. Every number is copied from a
   record; every claim cites its source.
10. **Figures and paper**: `/figure-review <figure id>` and the compiled
    `paper/main.pdf`, as in the experimental line.
11. **Reporting check, verification, final judge and audit**: `python
    skills/_core/checklists/checklist_cli.py check --guideline consort-2025
    --root .` for a trial with people, or `python
    skills/_core/checklists/checklist_cli.py check --guideline arrive-2 --root
    .` for a field experiment, answers each item `satisfied`, `missing` or
    `needs-judgment`; journals ask for it as a supplementary file. `python
    skills/paper-writing/scripts/paper_cli.py verify` adds the study checks: a
    primary outcome switched without an amendment fails, and exploratory
    analyses reported as confirmatory are flagged. The `paper-reviewer`
    judges the compiled paper on the `empirical-study` rubric, recorded with
    `python skills/paper-writing/scripts/paper_cli.py review --input
    <round.json>`. `smith audit .` and `/skill-audit <subject>` report; they
    never repair.

The human gates are the plausibility acceptance, the agreed paper type, the
protocol approval and its amendments (G-STUDY-PROTOCOL), the registration
(G-REGISTRATION), the ethics record (G-ETHICS), the allocation record
(G-ALLOCATION), the data-use statement and de-identification record, and the
flow sign-off (G-FLOW). The assistant never generates measurements or data,
and never generates, reads out or alters the allocation sequence. The
decisions on ethics, consent, data collection and the choice of primary
outcome stay human: every such record names the operator with `--by`.
