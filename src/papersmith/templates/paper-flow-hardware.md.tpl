## Paper construction flow (hardware line)

This workspace builds an **open hardware or instrument paper**: a device,
sensor or instrument the operator designs, builds and validates against a
reference, written in the HardwareX article template with every uncertainty
reported as the GUM asks. It was created with `smith init --kind hardware` or
moved here with `smith kind set hardware` (`paper_kind: "hardware"` in
`.papersmith/config.json`). There is no proposal, no experiment and no remote
run. The line keeps its records under `protocol/`, `study/`, `datasets/` and
`analysis/`, written by the shared empirical tools and the measurement core
(`skills/_core/measurement/measure_cli.py`), and `/hardware` routes to them
and reports where the work stands (`/hardware status`). Every tool refuses
when a stage's input is missing.

1. **Harness**: `smith status .` and `smith audit . --check-drift`;
   `/upgrade-project` when the workspace runs an older release.
2. **Plausibility and paper type**: `/plausibility <the idea in at least two
   sentences>` scouts the state of the art and the comparable devices; on
   acceptance, `/paper-type` records the type the operator agrees in
   `.papersmith/paper_type.json`. The reporting checklists are `hardwarex`
   and `gum-reporting`.
   A vague idea can be shaped first with `/idea-shaping` (`smith idea`).
3. **Requirements and specifications** (gate G-SPEC):
   `/study-protocol-deliberation` keeps the hardware's protocol as managed
   revisions `protocol/study-protocol-<slug>-vNN.md`: what the hardware must
   measure or do and for whom (the research question), the primary
   performance outcome with its acceptance criterion (for example the limits
   of agreement allowed against the reference device), the secondary
   specifications (range, resolution, cost, power, size), the design of the
   validation, the operating conditions, the number of units, replicates and
   paired readings with their justification, and the analysis plan
   (uncertainty budgets and agreement). The operator signs the
   specifications by approving a revision with `python
   skills/_core/empirical/study_cli.py protocol approve --root . --by <name>`,
   which pins it by its hash in `study/protocol.lock.json`; a later change is
   an amendment (`study_cli.py protocol amend --root . --by <name> --reason
   <why>`). The paper's specifications table reports the hardware as built
   against these signed values.
4. **Design files and bill of materials**: the operator keeps the editable
   design files (CAD, schematic and layout projects, firmware and software
   sources) and the bill of materials with its purchase records in an open
   repository with a DOI (OSF, Mendeley Data or Zenodo), recorded as the
   `repository-url` declaration (`python
   skills/paper-writing/scripts/paper_cli.py declare --declaration
   repository-url --value <url>`). The assistant never estimates a price or
   invents a part.
5. **Build**: the operator builds the hardware and keeps the build steps,
   photographs and the design decisions that the build instructions will
   report.
6. **Calibration and uncertainty** (gate G-CALIBRATION): the operator
   records every reference and test instrument with its calibration
   certificate (`python skills/_core/measurement/measure_cli.py instrument
   add --root . --id <id> --model <model> --serial <serial> --resolution
   <value unit> --calibration-certificate <certificate> --calibrated <date>
   --due <date> --by <name>`), registers each raw measurement file the
   operator produced by its hash (`measure_cli.py data register --root .
   --file <csv> --quantity <name> --unit <unit> --instrument <id> --by
   <name>`) and computes each uncertainty budget from those files and
   instruments (`measure_cli.py uncertainty compute --root . --quantity
   <name>`), written to `study/uncertainty/<quantity>.json`. The gate passes
   when every instrument is calibrated and not past due and every budget is
   current; a past-due instrument needs `--allow-past-due --by <name>
   --reason <why>`, the operator's decision.
7. **Agreement with a reference device** (gate G-AGREEMENT): the device's
   and the reference device's paired readings, each registered first with
   `data register` and told apart by a condition (`--condition role=device`,
   `--condition role=reference`: one uncertainty budget is computed per
   instrument and condition set, never across two instruments), give the
   Bland-Altman bias, the limits of agreement and
   ICC(2,1) (`python skills/_core/measurement/measure_cli.py agreement
   compute --root . --device-file <csv> --reference-file <csv> --pair-column
   <column>`), written to `study/agreement.json` and stale when either file
   changes. `measure_cli.py status --root .` reports instruments, data,
   budgets and agreement in one object.
8. **Field or user validation**: when people take part (users in a field
   trial, a usability study, measurements on participants), the protocol of
   step 3 covers them and the operator records the ethics approval (`python
   skills/_core/empirical/study_cli.py ethics record --root . --by <name>
   --committee <name> --code <code> --date <date> --consent <route>`) and the
   registration (`study_cli.py registration record --root . --by <name>
   --registry <name> --id <id> --date <date>`), each with `--not-applicable
   --reason <why>` when it does not apply; the participant counts go to
   `study/flow.json` (`python skills/_core/participant_flow/flow_cli.py
   template strobe --root . --write`, then `flow_cli.py signoff --root . --by
   <name>`). A bench-only validation records both as not applicable.
9. **Open design files and data**: before writing, the repository of step 4
   holds the final design files, the firmware, the bill of materials and the
   raw measurement files registered in `study/measurements.json`, under the
   open licenses the specifications table will state.
10. **Scaffolding, declarations and writing**: `/paper-writing` opens the
    `paper/` tree from the line's HardwareX section contracts in `sections/`
    (specifications table, hardware in context, hardware description, design
    files, bill of materials, build and operation instructions, validation
    and characterization). The `protocol` and `outcomes` facts come from the
    locked revision; every value in the validation section is copied from
    `study/instruments.json`, `study/uncertainty/` and `study/agreement.json`;
    every claim cites its source. `/figure-review <figure id>` checks each
    figure and `paper/main.pdf` is compiled as in the experimental line.
11. **Reporting check and final judge**: `python
    skills/_core/checklists/checklist_cli.py check --guideline hardwarex
    --root .` and `checklist_cli.py check --guideline gum-reporting --root .`
    answer each item `satisfied`, `missing` or `needs-judgment`.
    `paper_cli.py verify` runs the paper checks. The `paper-reviewer` judges
    the compiled paper on the `measurement-science` rubric (design validity,
    calibration and traceability, uncertainty, reproducibility and open
    materials, agreement or validation), recorded with `paper_cli.py review
    --input <round.json>`.
12. **Audit** (transversal): `smith audit .` and `/skill-audit <subject>`
    report; they never repair.

The human gates are the plausibility acceptance, the agreed paper type, the
signed specifications and their amendments (G-SPEC), the instrument and
calibration records and every registered measurement file (G-CALIBRATION),
the agreement inputs (G-AGREEMENT) and, when people take part, the ethics and
registration records and the participant-flow sign-off. The assistant never
generates measurements or data, and never records ethics, consent, data
collection, a calibration, a sign-off or the choice of the primary outcome on
the operator's behalf: every such record names the operator with `--by`.
