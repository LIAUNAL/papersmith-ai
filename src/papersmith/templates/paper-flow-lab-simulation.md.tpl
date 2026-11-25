## Paper construction flow (lab and simulation line)

This workspace builds a **laboratory or simulation study**: a physical-science
study that fixes its samples or its model, checks its instruments or its model
against reference values, and reports every value with its GUM uncertainty, in
one of two variants: materials (synthesis, deposition or processing and the
characterization of the samples) and modelling-simulation (an analytical or
numerical model, its solver and its parameters). Both report on the
`gum-reporting` checklist (GUM, JCGM 100:2008, clause 7). It was created with
`smith init --kind lab-simulation` or moved here with `smith kind set
lab-simulation` (`paper_kind: "lab-simulation"` in `.papersmith/config.json`).
There is no proposal, no experiment campaign and no remote run. The study
keeps its records under `protocol/`, `study/` and `analysis/`, written by the
shared empirical tools and the measurement core, and `/lab-simulation` routes
to them and reports where the study stands (`/lab-simulation status`). Every
tool refuses when a stage's input is missing.

1. **Harness**: `smith status .` and `smith audit . --check-drift`;
   `/upgrade-project` when the workspace runs an older release.
2. **Plausibility and paper type**: `/plausibility <the idea in at least two
   sentences>` scouts the state of the art; on acceptance, `/paper-type`
   records the type and the variant the operator agrees in
   `.papersmith/paper_type.json`: `materials` or `modelling-simulation`.
   A vague idea can be shaped first with `/idea-shaping` (`smith idea`).
3. **Sample matrix or model definition**: the operator decides what the study
   varies and holds fixed. For `materials`, the samples to make (the
   compositions, the process conditions, the specimens per condition) and the
   characterization techniques; for `modelling-simulation`, the model, its
   solver, its parameters and their sources, and the convergence criteria.
   The decision is written into the protocol of the next step, never chosen
   by the assistant.
4. **Synthesis or simulation protocol** (gate G-STUDY-PROTOCOL):
   `/study-protocol-deliberation` keeps the protocol as managed revisions
   `protocol/study-protocol-<slug>-vNN.md`: the research question, exactly one
   primary outcome (the primary observable), the secondary observables, the
   design (the sample matrix or the model), the sample size as the replicates
   per condition or the parameter grid with its justification, and the
   analysis plan. The operator approves a revision with `python
   skills/_core/empirical/study_cli.py protocol approve --root . --by <name>`,
   which pins it by its hash in `study/protocol.lock.json`; a later revision
   is an amendment (`python skills/_core/empirical/study_cli.py protocol amend
   --root . --by <name> --reason <why>`). When the samples come from people
   or animals the operator records the ethics approval (`python
   skills/_core/empirical/study_cli.py ethics record --root . --by <name>
   --committee <name> --code <code> --date <date> --consent <route>`), and
   otherwise records it as not applicable (`--not-applicable --reason <why>`).
5. **Characterization or observables**: the operator measures the samples or
   runs the model and writes each raw data file. An instrument is recorded
   before its readings (step 6), then the operator registers each file by its
   sha256: `python skills/_core/measurement/measure_cli.py data register
   --root . --file <csv> --quantity <name> --unit <unit> --instrument <id>
   --replicate-column <column> --by <name>`, with one `--condition
   <key=value>` per condition the file was taken under. The core never writes
   into a registered file; `python skills/_core/measurement/measure_cli.py
   data status --root .` reports a file changed since its registration. A
   simulation run goes through the analysis log of step 7, which hashes the
   model code, its inputs and its outputs.
6. **Calibration against known values** (gate G-CALIBRATION): the operator
   records every instrument from its calibration certificate: `python
   skills/_core/measurement/measure_cli.py instrument add --root . --id <id>
   --model <model> --serial <serial> --resolution <value-and-unit>
   --calibration-certificate <certificate> --calibrated <date> --due <date>
   --by <name>`, adding `--stated-uncertainty <value-and-unit> --distribution
   normal|rectangular` (and the certificate's `--coverage-k` for a normal
   one) when the certificate states an uncertainty. The readings of a
   reference material or a standard sample are registered like any data file
   (`--condition reference=<material>`) and their result is compared with the
   known value; a simulation reproduces an analytical solution or a benchmark
   case first. `python skills/_core/measurement/measure_cli.py instrument
   status --root .` reports each calibration current or past due.
7. **Uncertainty, replicates or statistical error**: `python
   skills/_core/measurement/measure_cli.py uncertainty compute --root .
   --quantity <name>` (one `--condition <key=value>` per condition set)
   writes the GUM budget `study/uncertainty/<quantity>.json`: type A from the
   replicates, type B from the instrument records, the combined standard
   uncertainty, the effective degrees of freedom and the expanded uncertainty
   with its coverage factor (`--level <p>` or a declared `--coverage-k <k>`).
   It refuses an instrument past its calibration due date unless the
   operator overrides it (`--allow-past-due --by <name> --reason <why>`).
   Every fit, comparison and sweep goes through the append-only log
   `analysis/log.jsonl`: `python skills/_core/empirical/analysis_cli.py run
   --root . --outcome <id> --script <code> --input <data> --output <result>
   -- <command>` wraps a script or a model run, and `python
   skills/_core/empirical/analysis_cli.py record --root . --outcome <id> --by
   <name> --tool <name>` is the operator's entry for a GUI tool. The label is
   computed, never chosen: confirmatory only for an outcome and plan entry of
   the current locked protocol, exploratory otherwise. `python
   skills/_core/empirical/analysis_cli.py status --root .` lists the runs and
   their labels, and `python skills/_core/measurement/measure_cli.py status
   --root .` reports the instruments, the data files and the budgets.
8. **Open data and code**: the operator deposits the registered raw data
   files, the model and analysis code and the budgets in a repository; the
   `repository-url` declaration of the back matter (data and code
   availability) names it.
9. **Scaffolding, declarations and writing**: `/paper-writing` opens the
   `paper/` tree from the study's section contracts in `sections/`. The
   study facts come from the records: `python
   skills/paper-writing/scripts/paper_cli.py mark revisions --root protocol
   --revision-prefix v --ordinal-digits 2` marks the protocol revisions, and
   `python skills/paper-writing/scripts/paper_cli.py observe --report
   <report> --protocol protocol` reconciles the protocol, the sample, the
   outcomes and the analysis plan against disk. Every value is copied from a
   record with its expanded uncertainty; every claim cites its source.
10. **Figures and paper**: `/figure-review <figure id>` and the compiled
    `paper/main.pdf`, as in the experimental line.
11. **Reporting check, verification, final judge and audit**: `python
    skills/_core/checklists/checklist_cli.py check --guideline gum-reporting
    --root .` answers each item `satisfied`, `missing` or `needs-judgment`;
    journals may ask for it as a supplementary file. `python
    skills/paper-writing/scripts/paper_cli.py verify` adds the study checks:
    a primary outcome switched without an amendment fails, and exploratory
    analyses reported as confirmatory are flagged. The `paper-reviewer`
    judges the compiled paper on the `measurement-science` rubric, recorded
    with `python skills/paper-writing/scripts/paper_cli.py review --input
    <round.json>`. `smith audit .` and `/skill-audit <subject>` report; they
    never repair.

The human gates are the plausibility acceptance, the agreed paper type, the
protocol approval and its amendments (G-STUDY-PROTOCOL), the instrument and
calibration records (G-CALIBRATION), every raw data registration and every
override of a past-due calibration. The assistant never generates
measurements or data, and never records an instrument, a calibration, a data
registration, an ethics record, a sign-off of any record, the parameter grid
or the choice of the primary observable on the operator's behalf: every such
record names the operator with `--by`.
