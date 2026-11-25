## Paper construction flow (data-resource line)

This workspace builds a **data resource**: a corpus, dataset or benchmark that
the operator collected and releases for others, written as a data descriptor
(background and summary, methods, data records, technical validation, usage
notes, code availability) and reported on the `datasheets` checklist
(Datasheets for Datasets, Gebru et al., Commun. ACM 2021). It was created with
`smith init --kind data-resource` or moved here with `smith kind set
data-resource` (`paper_kind: "data-resource"` in `.papersmith/config.json`).
There is no proposal, no experiment campaign and no remote run. The resource
keeps its records under `protocol/`, `study/`, `datasets/` and `analysis/`,
written by the shared empirical tools and the datasets skill, and
`/data-resource` routes to them and reports where the resource stands
(`/data-resource status`). Every tool refuses when a stage's input is missing.

1. **Harness**: `smith status .` and `smith audit . --check-drift`;
   `/upgrade-project` when the workspace runs an older release.
2. **Plausibility and paper type**: `/plausibility <the idea in at least two
   sentences>` scouts the state of the art and the closest existing
   resources; on acceptance, `/paper-type` records the type the operator
   agrees in `.papersmith/paper_type.json`.
3. **Collection protocol** (gate G-STUDY-PROTOCOL):
   `/study-protocol-deliberation` keeps the protocol as managed revisions
   `protocol/study-protocol-<slug>-vNN.md`: the purpose of the resource, the
   sources or participants and how they are sampled, the planned records and
   their size with its justification, the annotation scheme when the records
   are labelled, the primary outcome (the variable or label the resource is
   built to measure) and the analysis plan of any baseline. The operator
   approves a revision with `python skills/_core/empirical/study_cli.py
   protocol approve --root . --by <name>`, which pins it by its hash in
   `study/protocol.lock.json`; a later revision is an amendment (`python
   skills/_core/empirical/study_cli.py protocol amend --root . --by <name>
   --reason <why>`).
4. **Ethics, consent and licence** (gate G-ETHICS): when the records come
   from people the operator records the ethics approval and the consent
   route (`python skills/_core/empirical/study_cli.py ethics record --root .
   --by <name> --committee <name> --code <code> --date <date> --consent
   <route>`), and otherwise records it as not applicable (`--not-applicable
   --reason <why>`). The right to release the data is a registry record: the
   operator's own data with their data-use statement (`python
   skills/datasets/scripts/datasets_cli.py --root . own --slug <slug> --by
   <name> --statement <how the data may be used>`), or the licence decision
   of a third-party source (`python skills/datasets/scripts/datasets_cli.py
   --root . license --slug <slug> --source-license <licence as the source
   states it>`).
5. **Collection, curation and documentation**: the operator collects the
   records and writes each data file; the assistant never collects, writes or
   edits one. The data dictionary is scaffolded from a file's header (`python
   skills/datasets/scripts/datasets_cli.py --root . dictionary init --slug
   <slug> --file <csv>`), completed by the operator (type, unit, allowed
   values, missing codes, PII flags) and validated with `python
   skills/datasets/scripts/datasets_cli.py --root . dictionary check --slug
   <slug>`.
6. **Quality checks** (gate G-DATA-QC): `python
   skills/datasets/scripts/datasets_cli.py --root . qc --slug <slug> --file
   <csv>` (with `--label <column>` and `--group <column>` when the records
   carry them) writes `datasets/<slug>/qc.json` against the dictionary. When
   the dictionary flags personal data, the operator removes or transforms it
   and records how with `python skills/datasets/scripts/datasets_cli.py
   --root . deidentify --slug <slug> --by <name> --statement <how>`.
7. **Baselines**: every preprocessing step, labeling script, agreement
   statistic and baseline goes through the append-only log
   `analysis/log.jsonl`: `python skills/_core/empirical/analysis_cli.py run
   --root . --outcome <id> --script <code> --input <data> --output <result>
   -- <command>` wraps a script, and `python
   skills/_core/empirical/analysis_cli.py record --root . --outcome <id> --by
   <name> --tool <name>` is the operator's entry for a GUI tool. The label is
   computed, never chosen: a baseline is confirmatory only when the locked
   protocol names its outcome and plan, exploratory otherwise. `python
   skills/_core/empirical/analysis_cli.py status --root .` lists the runs and
   their labels.
8. **Deposit** (gate G-DEPOSIT): the operator deposits the files in a
   repository and obtains the persistent identifier; the assistant never
   uploads. The operator then records it: `python
   skills/datasets/scripts/datasets_cli.py --root . deposit --slug <slug>
   --repository <repository> --identifier <DOI or other identifier> --license
   <licence> --by <name>`, which binds the record to the sha256 of every
   registered file. `python skills/datasets/scripts/datasets_cli.py --root .
   status` shows the deposit and whether it is current or stale (a file
   changed, added or missing since it was recorded); a stale deposit is
   recorded again after the new version is deposited. The `repository-url`
   declaration of the back matter (data and code availability) names it.
9. **Scaffolding, declarations and writing**: `/paper-writing` opens the
   `paper/` tree from the data descriptor's section contracts in
   `sections/`. The study facts come from the records: `python
   skills/paper-writing/scripts/paper_cli.py mark revisions --root protocol
   --revision-prefix v --ordinal-digits 2` marks the protocol revisions, and
   `python skills/paper-writing/scripts/paper_cli.py observe --report
   <report> --protocol protocol` reconciles the protocol, the sample, the
   outcomes and the analysis plan against disk. Every count is copied from a
   record; every claim cites its source.
10. **Figures and paper**: `/figure-review <figure id>` and the compiled
    `paper/main.pdf`, as in the experimental line.
11. **Reporting check, verification, final judge and audit**: `python
    skills/_core/checklists/checklist_cli.py check --guideline datasheets
    --root .` answers each item `satisfied`, `missing` or `needs-judgment`;
    journals may ask for the datasheet as a supplementary file. `python
    skills/paper-writing/scripts/paper_cli.py verify` adds the study checks:
    a primary outcome switched without an amendment fails, and exploratory
    baselines reported as confirmatory are flagged. The `paper-reviewer`
    judges the compiled paper on the `data-descriptor` rubric, recorded with
    `python skills/paper-writing/scripts/paper_cli.py review --input
    <round.json>`. `smith audit .` and `/skill-audit <subject>` report; they
    never repair.

The human gates are the plausibility acceptance, the agreed paper type, the
protocol approval and its amendments (G-STUDY-PROTOCOL), the ethics record and
the own-data statement or licence decision (G-ETHICS), every de-identification
statement, and the deposit record (G-DEPOSIT). The assistant never generates
measurements or data: it never generates, labels or alters data, and never
records a collection, a consent route, an ethics record, a licence decision, a
de-identification, a deposit, a sign-off of any record or the choice of the
primary outcome on the operator's behalf. Collection, consent, licence and
deposit stay human: every such record names the operator with `--by`.
