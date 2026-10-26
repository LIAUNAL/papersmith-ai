# Papersmith AI — OpenCode Entrypoint

Minimal harness entrypoint. This file does not duplicate guidance; it only routes
to the canonical sources of truth so a single set of docs drives every harness.

## Canonical context

- **Project context**: `openspec/project-context.md`
- **Domain guidelines**: `guidance/paper-guide/` (user drop-zone; loaded automatically by `proposal-deliberation`, optional at rest)
- **Available capabilities (skills)**: `skills/*/SKILL.md`
- **Repository maintenance (issues and PRs)**: `maintainer/skills/backlog-steward/SKILL.md` (repo-only; never shipped to workspaces)

## Skills

Skills live once at the repository-root `skills/` tree and are projected into
`.opencode/skills` by `npm run setup:harnesses`. Read each skill's `SKILL.md`
before invoking it; it is the source of truth for that capability.

## Slash commands

The eleven top-level skills are projected as OpenCode slash commands under
`.opencode/commands/` by `python scripts/sync-repo-harness.py`. Each command body
loads its `skills/<name>/SKILL.md` and takes your text as `$ARGUMENTS`. That
directory is a derived artifact — regenerate it with the script (`--check` reports
drift and exits non-zero) instead of editing it by hand.

## Safety plugin

`.opencode/plugins/refuse-offpath-push.js` is generated and auto-discovered. It
relays every `bash` invocation to
`skills/remote-execution/scripts/hooks/refuse_offpath_push.py`, so the predicate
has exactly one authority. It refuses — with a thrown error naming the matched
surface — a command that names a service's push surface without also invoking
`remote_cli.py`, and it degrades loudly rather than silently allowing when the
guard cannot be loaded. It is a tripwire, not a gate.

## Agents

`.opencode/agents/<name>.md` files are projected from `.claude/agents/` by
`python scripts/sync-repo-harness.py` (`mode: subagent`, with a `permission`
block mapped from each source `tools:` list). Edit the source in
`.claude/agents/`, never the projection.

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
   `proposals/research-concept-<slug>-rNN.md`. Mathematics goes in
   `$$ … \tag{N} $$` display blocks.
   - **Concept map and mathematics**: before implementing a revision, discuss
     its pillars, hypotheses and concept layers (dashboard: Mapa Conceptual &
     Modelo) and its equations with `/math-tutor`, the Socratic tutor that
     also reads hand-written pages.
5. **Proof of concept and experiments**, in this order:
   `/experimental-deliberation` writes the protocol in `experiments/`; a toy
   set (`/datasets synth`); replication of the comparison methods;
   the proof of concept (`/proposal-implementation`); a timing estimate;
   an optional hyperparameter search (`/hyperparameter-search`);
   the full experiments (`/experimental-implementation`); the code review
   (`experiments-reviewer`); the remote rehearsal; and the operator's launch.
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
   - **Remote runs**: one account per person and service
     (`smith team add … --attest`), `/kaggle-accounts validate`, then
     `/remote-execution`: generate-job → submit --smoke → fetch --smoke /
     smoke record → readiness → gate → submit → status / poll → fetch.
   Only the operator authorizes a launch.
6. **Scaffolding**: `/paper-writing` opens the `paper/` tree and its section
   contracts.
7. **Declarations**: `/paper-writing mark …` records each decision of the
   paper (authorship, funding, data and code, ethics, language, style).
8. **Writing**: `/paper-writing` writes one named block at a time. Every
   claim needs a source that holds it (`resolve`).
9. **Figures**: `/figure-review <figure id>` checks a compiled
   `paper/Figures/<id>.pdf`.
10. **Paper**: compile `paper/main.tex` to `paper/main.pdf` (dashboard:
    Previsualización PDF).
11. **Audit** (transversal): `smith audit .` and `/skill-audit <subject>`.
    Audits report; they never repair.

The human gates are plausibility acceptance, proposal and experimental
acceptance, and launch authorization. An agent never passes a gate on the
operator's behalf.
