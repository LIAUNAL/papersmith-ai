# Papersmith AI — Google Antigravity Rules

Minimal harness entrypoint. This file does not duplicate guidance; it only routes
to the canonical sources of truth so a single set of docs drives every harness.

## Canonical context

- **Project context**: `openspec/project-context.md`
- **Domain guidelines**: `guidance/paper-guide/` (user drop-zone; loaded automatically by `proposal-deliberation`, optional at rest)
- **Available capabilities (skills)**: `skills/*/SKILL.md`
- **Release procedure**: `docs/releasing.md`
- **Repository maintenance (issues and PRs)**: `maintainer/skills/backlog-steward/SKILL.md` (repo-only; never shipped to workspaces)

## Skills

Skills live once at the repository-root `skills/` tree and are projected into
`.agents/skills` by `npm run setup:harnesses`. Read each skill's `SKILL.md`
before invoking it; it is the source of truth for that capability.

## Invoking skills

Antigravity invokes each skill as `/<name>` through the `.agents/skills` link to
`skills/`; no command files are generated. Read the skill's `skills/<name>/SKILL.md`
before the work starts; that file remains the source of truth.

## Agents

Antigravity agents are generated from `.claude/agents/` into
`.agents/agents/<name>.md` by `python scripts/sync-repo-harness.py`. Edit the
source definition, never the generated file.

## Note on this file's location

This file is Antigravity's rules entrypoint (`.agents/AGENTS.md`, documented as a
directory-scoped rules file). `.antigravity/rules.md` and `.antigravity/skills`
are no longer generated; see `docs/harness-support-matrix.md`.

## Language

Reply to the human in the language they write in (Spanish or English).
Everything else stays English regardless of the conversation language: skills,
agent definitions, delegations and messages between agents, tool inputs, and
every generated artifact (code, comments, docs, commit messages, the data files
the dashboard displays under `.papersmith/` and `sota-pool/`, and paper
internals unless the paper declares another language). The dashboard's language
selector translates its own labels, never a workspace file, so a file written in
Spanish shows Spanish under English; only the conversation with an agent
follows the human's language.

## Paper construction flow

These are the eleven phases the command center (`smith ui`) shows under
"Pipeline y Avance", in order. Each phase card runs its stage: a slash command
`/<skill> <text>` typed into an agent, a `smith` command, or a link to the
panel that owns the work. The dashboard locks each phase until the one before
it is verified from its evidence on disk, with an explicit override, and every
skill refuses when its input is missing.

1. **Harness**: `smith status .` and `smith audit . --check-drift`;
   `/upgrade-project` when the workspace runs an older release.
2. **Plausibility**: `/plausibility <the idea in at least two sentences>`. It
   scouts about 25 SOTA references, draws `sota-pool/atlas.html` and grades the
   claims. Nothing is ingested until the operator accepts the report.
3. **Ingestion**: `/paper-ingestion <PDF or URL>` (or `smith ingest`)
   turns the accepted top 5 into Markdown under `guidance/`, with equations
   as LaTeX.
4. **Proposal deliberation**: `/proposal-deliberation` keeps managed revisions
   `proposals/research-concept-<slug>-rNN.md`, built in this order: the
   central problem and its pillars, then the hypotheses each pillar predicts,
   then the mathematics in `$$ … \tag{N} $$` display blocks. Each step stays
   locked until the one before it exists on disk; the dashboard's
   Mapa Conceptual & Modelo tab shows the three steps with a "Generar y
   deliberar" button that types the step's `/proposal-deliberation` into the
   agent.
   - **Concept map and mathematics**: before implementing a revision, discuss
     its pillars, hypotheses and concept layers and its equations with
     `/math-tutor`, the Socratic tutor that also reads hand-written pages.
   - **Concept trees**: `novelty.problem_tree` in
     `.papersmith/model_spec.json` holds the central problem, its 2 to 3
     direct causes and their effects; at least 2 pillars each reach a
     hypothesis through its `pillars` field. Every statement and citation
     reason is in English. The central problem and the
     causes state a negative condition, never "Lack of", "No", "Need for",
     "Requires" or an infinitive. The problem, each cause, each pillar and
     each hypothesis cite Q1 or Q2 journal articles at most 4 years old,
     checked against `sota-pool/journal-ranks.json`, which `python
     skills/_core/results/citations_cli.py rank --root .` writes from the SJR
     table. A preprint also counts when an author belongs to an accepted lab,
     found in OpenAlex or confirmed by the operator with `citations_cli.py lab`.
     The fourth step stays open until both trees hold.
   - **SOTA citations**: every pillar, hypothesis, concept-map layer and
     numbered equation is justified by 2 to 5 references of
     `sota-pool/candidates.json`, each with its reason, in
     `.papersmith/citations.json`, and shown beside the idea. This is the
     phase's fourth step, launched from its button in the stepper; `python
     skills/_core/results/citations_cli.py check --root .` says what is owed.
   - **Contribution type**: once the hypotheses are discussed and the
     mathematics and the novelty proposed, the `paper-reviewer` agent
     classifies the proposal's NeurIPS contribution type
     (`contribution_type` in `.papersmith/model_spec.json`), shown right after
     the hypotheses. This NeurIPS judge is the phase's fifth step: the
     "Lanzar el juez NeurIPS" button, on that card and in the stepper, launches
     it, and Phase 5 stays locked until it records a type.
5. **Proof of concept and experiments**, in this order:
   `/experimental-deliberation` writes the protocol in `experiments/`; a toy
   set (`/datasets synth`); replication of the comparison methods;
   the proof of concept (`/proposal-implementation`), done when its
   `Results/discussion.json` is complete; the operator's verification of
   that proof of concept (G-EXP-POC: its results and contrasted hypotheses,
   in the Novedad & Hallazgos tab or with `smith novelty approve --gate
   poc`); a timing estimate; an optional hyperparameter search
   (`/hyperparameter-search`); the full experiments
   (`/experimental-implementation`), locked until G-EXP-POC passes; the code
   review (`experiments-reviewer`); the remote rehearsal; and the operator's
   launch. The Experimentos tab steps through SOTA citations → proof of
   concept → verify → full experiment with one button each.
   - **Experiment citations**: every experiment of the latest protocol carries
     its 2 to 5 SOTA citations in `.papersmith/citations.json`, launched from
     the Experimentos tab. Until then `/proposal-implementation` and
     `/experimental-implementation` stay locked and G-EXP-POC refuses its
     approval (`SOTA_CITATIONS_OWED`).
   - **Data**: `/datasets synth|search|license|qc|prepare|publish` gives both
     stages a seeded toy set always and one official dataset (agents
     `dataset-scout`, `dataset-curator`): license checked, quality measured,
     one subject-wise preparation, published privately only with the
     operator's consent.
   - **Replication of comparison methods**: `/proposal-implementation` hands
     each baseline paper to `paper-replicator`, which looks for the paper's
     published code first, adopts it pinned and audits it against the paper,
     and reimplements the method only when no code exists.
   - **Timing and placement**: a short timing probe in `Results/timing.json`
     before the pilot and again before the full run; the dashboard's
     Experimentos tab lists the local, Kaggle and Colab options, and
     `/remote-parallelism` (`estimate`, then `assess --owners <distinct
     owners>`) decides whether to split a campaign. A run whose local
     estimate exceeds 20 minutes runs on Colab or Kaggle, never locally, and
     a proof of concept is sized to at most 5 hours where it runs.
   - **Hyperparameter search** (only when the deliberation judged it
     worthwhile): `/hyperparameter-search plan|report|status` runs an
     Optuna search nested inside each outer fold, with the same trial
     budget for every arm and a declared importance evaluator; its contour
     and importance plots land in `Results/hpo/` and the Experimentos tab
     shows them. It runs remotely like the full runs.
   - **Experiment diagrams**: when the proof of concept is approved
     (`AGREED.md`) and again when the full experiments are
     (`Experimental_AGREED.md`), `/experiment-diagrams poc` and then
     `/experiment-diagrams experiments` (or the Experimentos tab's
     "Generar diagrama") draw each one as a TikZ figure. The operator
     validates each one in that tab ("Validar diagrama") or by approving it
     explicitly in the conversation, which the agent then records with
     `diagram_cli.py validate` (the operator's words verbatim and the hash
     of the PNG shown); `submit` refuses `DIAGRAM_NOT_VALIDATED` until then,
     and drawing it again asks again.
   - **Experiments tutor**: in the Experimentos tab, `/experiments-tutor`
     explains, questions and evaluates each design decision (architecture,
     hyperparameters, ablations, significance tests, the toy set, training,
     upper bounds, baselines and their implementation) from the protocol,
     the approvals, the code and the results; it never invents a number, and
     a change of decision goes back to `/experimental-deliberation`.
   - **Remote runs**: accounts associated with distinct emails
     (`smith team add … [--email <email>] --attest`), `/kaggle-accounts validate`, then
     `/remote-execution`: generate-job → submit --smoke → fetch --smoke /
     smoke record → readiness → gate → submit → status / poll → fetch.
   - **Findings and novelty**: once a stage's discussion is complete, the
     `paper-reviewer` agent classifies the NeurIPS contribution type of its
     findings (`contribution_type` in `Results/discussion.json`). The
     Novedad & Hallazgos tab launches that judge from a button on its
     contribution-type card, and G-EXP-POC and G-NOVELTY refuse their approval
     (`NEURIPS_JUDGE_OWED`) while a complete discussion of that stage has no
     type. The tab contrasts the hypothesis verdicts with the SOTA
     pool and the operator records `G-NOVELTY` (`smith novelty approve` or
     `iterate`) before the paper is written.
   Only the operator authorizes a launch. The phase passes only with a
   published protocol with every experiment cited, a proof of concept
   discussed and verified, and a full
   experiment discussed.
6. **Scaffolding**: `/paper-writing` opens the `paper/` tree and its section
   contracts.
7. **Declarations**: `/paper-writing mark …` records each decision of the
   paper (authorship, funding, data and code, ethics, language, style).
8. **Writing**: `/paper-writing` writes one named block at a time. Every
   claim needs a source that holds it (`resolve`). `refs.bib` comes from
   `bib build`, never from hand edits. After the citations change, run
   `resolve --references`: it stores each cited paper's metadata and abstract
   in `paper/.paper-writing/references.json`, and `verify` fails while a cited
   key has no record there. A paper it cannot resolve, offline included, keeps
   a record and passes with a note.
9. **Figures**: `/figure-review <figure id>` checks a compiled
   `paper/Figures/<id>.pdf`.
10. **Paper**: compile `paper/main.tex` to `paper/main.pdf` (dashboard:
    the PDF preview tab, whose style and redundancy panel scores each
    section from 0 to 100).
11. **Audit** (transversal): `smith audit .` and `/skill-audit <subject>`.
    Audits report; they never repair.

The human gates are plausibility acceptance, proposal and experimental
acceptance, the proof-of-concept verification (G-EXP-POC), the novelty
decision (G-NOVELTY) and launch authorization. An agent never passes a gate
on the operator's behalf.
