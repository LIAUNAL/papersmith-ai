## Paper construction flow (observational and measurement line)

This workspace builds an **observational or measurement study**: a study of
data the operator collects or holds, without assigning an intervention, in one
of three variants with their reporting checklist: observational (STROBE),
diagnostic or clinical validation (STARD 2015) and measurement instrument
(COSMIN). It was created with `smith init --kind observational-measurement`
or moved here with `smith kind set observational-measurement`
(`paper_kind: "observational-measurement"` in `.papersmith/config.json`).
There is no proposal, no experiment and no remote run. The study keeps its
records under `protocol/`, `study/`, `datasets/` and `analysis/`, written by
the shared empirical tools, and `/observational-measurement` routes to them
and reports where the study stands (`/observational-measurement status`).
Every tool refuses when a stage's input is missing.

1. **Harness**: `smith status .` and `smith audit . --check-drift`;
   `/upgrade-project` when the workspace runs an older release.
2. **Plausibility and paper type**: `/plausibility <the idea in at least two
   sentences>` scouts the state of the art; on acceptance, `/paper-type`
   records the type and the variant the operator agrees in
   `.papersmith/paper_type.json`. The variant chooses the reporting
   checklist: `strobe`, `stard-2015` or `cosmin`.
3. **Study protocol** (gate G-STUDY-PROTOCOL): `/study-protocol-deliberation`
   keeps the protocol as managed revisions
   `protocol/study-protocol-<slug>-vNN.md`: the research question, exactly
   one primary outcome, the secondary outcomes, the design, the eligibility,
   the sample size with its justification and the analysis plan. The
   operator approves a revision with `python
   skills/_core/empirical/study_cli.py protocol approve --root . --by <name>`,
   which pins it by its hash in `study/protocol.lock.json`; a later revision
   is an amendment (`study_cli.py protocol amend --root . --by <name>
   --reason <why>`).
4. **Ethics and registration**: the operator records the ethics approval
   (`study_cli.py ethics record --root . --by <name> --committee <name>
   --code <code> --date <date> --consent <route>`) and the registration
   (`study_cli.py registration record --root . --by <name> --registry <name>
   --id <id> --date <date>`), each with `--not-applicable --reason <why>`
   when it does not apply. Both refuse until the protocol is approved and
   current, and an amendment marks them stale.
5. **Data**: the operator collects the data. `python
   skills/datasets/scripts/datasets_cli.py --root . own --slug <slug> --by
   <name> --statement <how it may be used>` registers it; `datasets_cli.py
   --root . dictionary init --slug <slug> --file <csv>` scaffolds the data
   dictionary the operator completes and `dictionary check --slug <slug>`
   validates; `datasets_cli.py --root . qc --slug <slug> --file <csv>`
   measures its quality against the dictionary, and `datasets_cli.py --root
   . deidentify --slug <slug> --by <name> --statement <how>` records how the
   columns it flags as personal data were removed or transformed.
6. **Analysis**: every analysis goes through the append-only log
   `analysis/log.jsonl`: `python skills/_core/empirical/analysis_cli.py run
   --root . --outcome <id> --input <data> --output <result> -- <command>`
   wraps a script, and `analysis_cli.py record --root . --outcome <id> --by
   <name> --tool <name>` is the operator's entry for a GUI tool. The label is
   computed, never chosen: confirmatory only for an outcome and plan entry of
   the current locked protocol, exploratory otherwise.
   `analysis_cli.py status --root .` lists the runs and their labels.
7. **Participant flow**: `python skills/_core/participant_flow/flow_cli.py
   template strobe|stard-2015 --root . --write` writes the empty
   `study/flow.json`; the operator enters every count;
   `flow_cli.py check --root .` validates the arithmetic, `flow_cli.py render
   --root .` draws `paper/Figures/participant-flow.svg` and `flow_cli.py
   signoff --root . --by <name>` records the operator's sign-off, stale after
   any edit.
8. **Scaffolding, declarations and writing**: `/paper-writing` opens the
   `paper/` tree from the study's section contracts in `sections/`. The
   study facts come from the records: `paper_cli.py mark revisions --root
   protocol --revision-prefix v --ordinal-digits 2` marks the protocol
   revisions, and `paper_cli.py observe --report <report> --protocol
   protocol --flow study/flow.json` reconciles the protocol, sample,
   outcomes, analysis plan and participant flow against disk. The
   `study-registration` and `ethics-approval` declarations repeat what step 4
   recorded. Every number is copied from a record; every claim cites its
   source.
9. **Figures and paper**: `/figure-review <figure id>` and the compiled
   `paper/main.pdf`, as in the experimental line.
10. **Reporting check, verification, final judge and audit**: `python
    skills/_core/checklists/checklist_cli.py check --guideline <the
    variant's checklist> --root .` answers each item `satisfied`, `missing`
    or `needs-judgment`; journals ask for it as a supplementary file.
    `paper_cli.py verify` adds the study checks: a primary outcome switched
    without an amendment fails, and exploratory analyses reported as
    confirmatory are flagged. The `paper-reviewer` judges the compiled paper
    on the `empirical-study` rubric, recorded with `paper_cli.py review
    --input <round.json>`. `smith audit .` and `/skill-audit <subject>`
    report; they never repair.

The human gates are the plausibility acceptance, the agreed paper type, the
protocol approval and its amendments (G-STUDY-PROTOCOL), the ethics and
registration records, the data-use statement and de-identification record,
and the participant-flow sign-off. The assistant never generates measurements
or data, and never records ethics, consent, data collection, sign-offs or the
choice of the primary outcome on the operator's behalf: every such record
names the operator with `--by`.
