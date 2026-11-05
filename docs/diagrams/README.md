# The Pi flow diagram

`papersmith-pi-flow.html` is this repository's flow of record, drawn from the
repository's own files. Its numbered lanes are the eleven phases the dashboard
shows under *Pipeline y Avance* (`phase_actions.STAGES`), from `1 · Harness` to
`11 · Audit (transversal)`, and a lettered lane is a sub-lane of the phase whose
number it carries:

- `2a`: the optional thematic help before `/plausibility` (keywords typed in the
  phase-2 box, the `banco-lia` MCP's `search_bank`, and the operator's approval
  of the proposed prompt, launched as `/plausibility <draft>`);
- `4a`: the proposal's ordered steps on the *Mapa Conceptual* tab — the central
  problem and its pillars, then the hypotheses, then the mathematics, each locked
  until the one before it exists — with the `paper-reviewer`'s NeurIPS
  contribution type classified after the hypotheses (`.papersmith/model_spec.json`)
  and the `/math-tutor`;
- `5` and `5a` to `5g`: Phase 5 in the order the harness entrypoints state it —
  the protocol (`/experimental-deliberation`), the datasets (toy set, then the
  official preparation), the replication of the comparison methods and the proof
  of concept with its `Results/discussion.json` (gates sub-phase 5.8), the
  proof-of-concept verification gate `G-EXP-POC` (the operator, in the Novedad
  tab's card, the Experimentos stepper or `smith novelty --gate poc`; sub-phase
  5.9), the full experiments that only start after it (their discussion gates
  5.12 and `experiments-reviewer`'s `Results/reviewer_report.json` gates 5.13),
  the credentials, the remote rehearsal and launch, and the findings: their
  NeurIPS contribution type and the `G-NOVELTY` operator gate
  (`.papersmith/novelty_gate.json`, `smith novelty`), which releases the writing;
- `6` to `10`: scaffolding, declarations, writing, figures and the paper, whose
  PDF preview carries the style and redundancy panel;
- `10a`: journal choice and venue adaptation after the compiled PDF
  (`/journal-finder` ranks journals from OpenAlex works and sources, with the SJR
  quartile from an imported CSV or a labelled OpenAlex proxy and a review time
  estimated from Crossref and then PubMed; the operator chooses a journal in the
  PDF Preview tab; the `venue-adapter` agent states each requirement with a quote
  and a url; the operator approves the plan bound to its sha256, text changes go
  only through `write`, and `venue build` assembles
  `paper/venues/<slug>/main.pdf` without writing `paper/main.tex`). It is a
  serpentine of three rows, so that every turn between rows is a short vertical
  edge; `venue-adapter` is mapped to `paper` in `AGENT_STAGES`.

The dashboard's workspace board transcribes it — `PIPELINE_STAGES`,
`PIPELINE_CHAIN`, `GATE_SOURCES` and `AGENT_STAGES` in
`skills/_core/command_center/state_extractor.py` — with one tramo per phase and
Phase 5 as five tramos (protocol, proof of concept, full experiments,
credentials, remote run), in the same order. `tests/test_command_center_state.py`
holds the transcription and `tests/test_flow_consistency.py` holds the lane
numbering against the eleven phases, so the drawing and the board cannot drift
apart without a failing test. The human stops are drawn inline and are not
verdict gates on the board: the approval of the thematic-help draft, the
plausibility report's acceptance, the two deliberation acceptances, the
proof-of-concept verification, the launch authorization and `G-NOVELTY`. An
acceptance is the operator's decision, not a verdict computed from artifacts —
`G-EXP-POC` and `G-NOVELTY` do record theirs in `novelty_gate.json` — so
`GATE_SOURCES` carries the verdict gates that land in the audit lane and none of
the stops.

| File | What it is |
| --- | --- |
| `papersmith-pi-flow.html` | The artifact: self-contained, offline, no network at view time |
| `papersmith-pi-flow.png` | The same drawing as an image, for readers who do not open HTML |
| `papersmith-pi-flow.build.mjs` | The source |
| `locales/es.json` | The translation table the rendered page embeds, vendored from Archify 3.0.1 (MIT) |

The source is here, and not only in the throwaway `.archify/` folder it was
authored in, because a diagram whose source lives outside the repository cannot
be regenerated from a clone — and one nobody can regenerate stops being evidence
and becomes an assertion. It was untracked until 0.11.0.

## Regenerating

Requirements: Node, and the Archify skill at the version the artifact was
rendered with (**3.0.1** — the bytes are the renderer's, so the version is part
of the recipe). The candidate records the repository revision it describes in
`meta.repository.revision`, and every node's `sources` names the path and line
range it was transcribed from, so the drawing is checkable against the code
rather than trusted.

```bash
SCRATCH=$(mktemp -d)
node docs/diagrams/papersmith-pi-flow.build.mjs "$SCRATCH/candidate.json"
node ~/.claude/skills/archify/bin/archify.mjs finalize architecture \
  "$SCRATCH/candidate.json" "$SCRATCH/papersmith-pi-flow.html" \
  --repo-root . --quality showcase --out-dir "$SCRATCH/evidence" --json
cp "$SCRATCH/papersmith-pi-flow.html" docs/diagrams/papersmith-pi-flow.html
cp "$SCRATCH/papersmith-pi-flow.html" skills/_core/command_center/static/papersmith-flow.html
```

The dashboard serves the second copy in its *Flujo Archify* tab, and
`tests/test_command_center_neutral_defaults.py` holds the two byte-identical.

`finalize` runs the four gates — showcase validation, delivery, strict
provenance check, and a real-browser check — and a passing receipt means all
four passed. A non-zero exit is never success.

`--out-dir` keeps each run's browser evidence apart from the last one: reusing a
directory whose artifact bytes have changed is refused, and that refusal is
about evidence ownership rather than about the drawing. Two gates have measured
teeth worth knowing before editing the layout: `layout/constraint` refuses a node
label wider than its cell or a connection shorter than 24px, and
`composition/desktop-readability` refuses a figure whose projected node text
falls under 6px at a 1440px viewport. That second cap is arithmetic rather than
"roughly": the rendered edge labels are 8px and the desktop budget is 930px, so
the projected text is `8 * 930 / width`, and reaching 6px puts the ceiling at
exactly 1240px. Six columns cannot get under it -- at the 24px connection
minimum and the 186px node width the longest command label needs, six columns
floor at `30 + 6*186 + 5*24 + 70 = 1312` -- which is why the flow is drawn in
five and why the plausibility gate is a `security` edge from `novelty-screener`
to `sota-pool/` rather than a node of its own.

The component count has a cap as well, and it is the renderer's rather than a
gate's: Archify's grid search, which routes an edge around nodes it has no
relationship with, gives up on a scene of more than 80 obstacles
(`maximumObstacleCount`), and an authored `via` cannot replace it, because only
two automatic routes may cross (with a halo) -- an authored crossing is a
showcase error. The flow is at 103 components, so every edge has to be routable
without the grid: between row neighbours, straight down a column, or through
the corridor between two rows. That is why the dashed `replication` ->
`expBuild` arrow is gone (its relation lives in the `expBuild` tag and in the
*Flow rules* card), and why a label sits only on an edge that leaves its row:
`composition/label-gap` refuses a label on the 24px gap between row neighbours.
Any new edge that only the grid can route fails at the current size.

## The PNG

The page draws at whatever width the viewport gives it, so the frame is a
capture decision rather than part of the artifact. The committed PNG is 1400px
wide at **device pixel ratio 1**, captured full-page with `?embed=1` (which is
what drops the viewer's own chrome); it is 1400x4013 for the current drawing. A browser driver needs those three
parameters; the ratio is the one that is easy to get wrong, because the default
capture comes out at 2× and a 2800px file is four times the bytes for a drawing
nobody reads at that size.
