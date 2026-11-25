## Paper construction flow (qualitative-participatory line)

This workspace builds a **qualitative, participatory or consensus study**: a
study built on people's accounts and judgement, in one of three variants with
their reporting checklist: a qualitative or mixed-methods study
(`qualitative-mixed`, SRQR: `srqr`, or COREQ: `coreq` for a study of
interviews or focus groups), an expert consensus or foresight study
(`consensus-foresight`, ACCORD: `accord`) and an experience report
(`experience-report`, no reporting checklist). It was created with `smith init
--kind qualitative-participatory` or moved here with `smith kind set
qualitative-participatory` (`paper_kind: "qualitative-participatory"` in
`.papersmith/config.json`). There is no proposal, no experiment campaign and
no remote run. The study keeps its records under `protocol/` and `study/`,
written by the shared empirical tools and the qualitative core, and
`/qualitative-participatory` routes to them and reports where the study stands
(`/qualitative-participatory status`). Every tool refuses when a stage's input
is missing.

1. **Harness**: `smith status .` and `smith audit . --check-drift`;
   `/upgrade-project` when the workspace runs an older release.
2. **Plausibility and paper type**: `/plausibility <the idea in at least two
   sentences>` scouts the state of the art; on acceptance, `/paper-type`
   records the type and the variant the operator agrees in
   `.papersmith/paper_type.json`. The variant chooses the reporting
   checklist: `srqr` (or `coreq`), `accord`, or none for an experience report.
   A vague idea can be shaped first with `/idea-shaping` (`smith idea`).
3. **Case, panel or experience and its framework** (gate G-STUDY-PROTOCOL,
   optional for an experience report): `/study-protocol-deliberation` keeps
   the protocol as managed revisions `protocol/study-protocol-<slug>-vNN.md`:
   the research question, the approach and its paradigm, the case or the
   setting, the sampling and its sufficiency criterion, the data collection
   and the analysis plan; for a consensus study, the panel, the rating scale,
   the consensus threshold and the number of rounds, fixed before the first
   round. The operator approves a revision with `python
   skills/_core/empirical/study_cli.py protocol approve --root . --by
   <name>`, which pins it by its hash in `study/protocol.lock.json`; a later
   revision is an amendment (`python skills/_core/empirical/study_cli.py
   protocol amend --root . --by <name> --reason <why>`). A consensus study
   then records its plan against the locked protocol: `python
   skills/_core/qualitative/consensus_cli.py plan record --root . --rounds <n>
   --threshold <percent> --scale <scale> --agree-from <rating> --by <name>`.
4. **Ethics and consent** (gate G-ETHICS): the operator records the approval
   of the ethics committee and the consent route, including consent to be
   quoted (`python skills/_core/empirical/study_cli.py ethics record --root .
   --by <name> --committee <name> --code <code> --date <date> --consent
   <route>`), or records it as not applicable (`--not-applicable --reason
   <why>`), which an experience report without participant data may do. The
   record refuses until the protocol is approved and current, and an
   amendment marks it stale.
5. **Fieldwork, rounds or implementation** (gates G-TRANSCRIPTS and
   G-ROUNDS): the operator conducts the interviews, focus groups or
   observation, transcribes and de-identifies the material, and registers
   each file: `python skills/_core/qualitative/qual_cli.py transcripts add
   --root . --file <file> --participant <code> --consent <how consent was
   given> --deidentified <how it was de-identified> --by <name>` (with `--kind
   focus-group`, `field-note` or `document` when it applies); `python
   skills/_core/qualitative/qual_cli.py transcripts status --root .` shows
   every registration current or stale (G-TRANSCRIPTS, for a qualitative or
   mixed study). A consensus study registers its panel by anonymised codes
   (`python skills/_core/qualitative/consensus_cli.py panel add --root .
   --member <code> --expertise <expertise> --by <name>`) and each round's
   response file in order (`python skills/_core/qualitative/consensus_cli.py
   round record --root . --round <k> --file <responses> --by <name>`;
   G-ROUNDS passes when every planned round is recorded and current). An
   experience report keeps the operator's own records of what was done.
6. **Coding, consensus or reflection** (gate G-ANALYSIS): the assistant may
   propose codes and themes in a draft file; the operator records each
   codebook version (`python skills/_core/qualitative/qual_cli.py codebook
   record --root . --file <codebook> --by <name>`) and signs the themes off
   (`python skills/_core/qualitative/qual_cli.py themes signoff --root .
   --file <themes> --by <name>`), bound to the codebook version and to every
   transcript; `python skills/_core/qualitative/qual_cli.py themes status
   --root .` shows the sign-off current or stale. A consensus study reads its
   agreement per item from `python skills/_core/qualitative/consensus_cli.py
   round status --root .` and, for a structural analysis, records the MICMAC
   computation from the operator's influence matrix (`python
   skills/_core/qualitative/consensus_cli.py micmac compute --root . --file
   <matrix> --by <name>`; MACTOR and scenarios stay narrative). An experience
   report reflects on what was done and what it taught.
7. **Integration with prior work**: the discussion compares each finding with
   the closest studies of the accepted state of the art and the literature
   the introduction names, each comparison cited.
8. **Scaffolding, declarations and writing**: `/paper-writing` opens the
   `paper/` tree from the line's section contracts in `sections/`. When the
   study has a protocol, `python skills/paper-writing/scripts/paper_cli.py
   mark revisions --root protocol --revision-prefix v --ordinal-digits 2`
   marks its revisions. The `ethics-approval` declaration repeats what step 4
   recorded. Every participant quote is written `\pquote{<code>}{<text>}`,
   copied verbatim from a registered transcript of that participant; every
   count and agreement figure is copied from a record; every claim cites its
   source.
9. **Figures and paper**: `/figure-review <figure id>` and the compiled
   `paper/main.pdf`, as in the experimental line.
10. **Reporting check, quotes, verification, final judge and audit**:
    `python skills/_core/checklists/checklist_cli.py check --guideline srqr
    --root .` (or `python skills/_core/checklists/checklist_cli.py check
    --guideline coreq --root .` for an interview or focus-group study) for a
    qualitative or mixed study, or `python
    skills/_core/checklists/checklist_cli.py check --guideline accord --root
    .` for a consensus study, answers each item `satisfied`, `missing` or
    `needs-judgment`; an experience report has no checklist. `python
    skills/_core/qualitative/qual_cli.py quotes check --root .` requires
    every quote verbatim in a current transcript of its participant, and
    `python skills/paper-writing/scripts/paper_cli.py verify` runs the same
    check (`quote-not-verbatim`). The `paper-reviewer` judges the compiled
    paper on the `qualitative-study` rubric, recorded with `python
    skills/paper-writing/scripts/paper_cli.py review --input <round.json>`.
    `smith audit .` and `/skill-audit <subject>` report; they never repair.

The human gates are the plausibility acceptance, the agreed paper type, the
protocol approval and its amendments (G-STUDY-PROTOCOL), the ethics record
(G-ETHICS), the transcript registrations (G-TRANSCRIPTS), the consensus plan
and rounds (G-ROUNDS) and the codebook versions and theme sign-off
(G-ANALYSIS). The assistant never generates data, never writes or edits a
transcript, never invents or polishes a quote and never enters a rating. The
decisions on ethics, consent, data collection and the analytic sign-off stay
human: every such record names the operator with `--by`.
