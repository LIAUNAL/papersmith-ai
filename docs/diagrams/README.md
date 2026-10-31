# The Pi flow diagram

`papersmith-pi-flow.html` is this repository's flow of record: the twelve
numbered tramos plus the transversal audit lane, drawn from the repository's own
files. Two sub-lanes sit beside the numbered ones without being
tramos of their own: `1a` (the optional thematic help before `/plausibility`:
keywords typed in the phase-2 box, the `banco-lia` MCP's `search_bank`, and the
operator's approval of the proposed prompt, which is then launched as
`/plausibility <draft>`), `3b` (the concept map and the math tutor), `4a`
(datasets: `dataset-scout`, `dataset-curator`, the operator's upload consent and
`datasets/`, feeding the toy set to the proof of concept and the official
preparation to the experiments) and `8a` (the Novelty & Findings assessment
between the measured results and the writing: the dashboard panel, the
`G-NOVELTY` operator gate, `.papersmith/novelty_gate.json` and `smith novelty`).
Two lanes take a second row, since a sixth column would break the width cap
below: implementation, for `paper-replicator` -- published code first,
reimplementation otherwise -- and for the proof of concept's
`Results/discussion.json` (gates sub-phase 5.8); experimental implementation, for
the full run's `Results/discussion.json` (5.11) and the
`Results/reviewer_report.json` of `experiments-reviewer` (5.12). The dashboard's *Pipeline* tab transcribes it — `PIPELINE_STAGES`,
`PIPELINE_CHAIN`, `GATE_SOURCES` and `AGENT_STAGES` in
`skills/_core/command_center/state_extractor.py` — and
`tests/test_command_center_state.py` holds the transcription, so the drawing and
the board cannot drift apart without a failing test. One family is drawn and
deliberately not on the board: the human stops, which the drawing shows inline
(the approval of the thematic-help draft, the plausibility report's acceptance,
the two deliberation acceptances, the launch authorization, `G-NOVELTY`). An
acceptance leaves no artifact to read -- `G-NOVELTY` does record its decision in
`novelty_gate.json`, but it is the operator's decision, not a verdict computed
from artifacts -- so `GATE_SOURCES` carries the verdict gates that land in the
audit lane and none of the stops.

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
```

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

## The PNG

The page draws at whatever width the viewport gives it, so the frame is a
capture decision rather than part of the artifact. The committed PNG is 1400px
wide at **device pixel ratio 1**, captured full-page with `?embed=1` (which is
what drops the viewer's own chrome). A browser driver needs those three
parameters; the ratio is the one that is easy to get wrong, because the default
capture comes out at 2× and a 2800px file is four times the bytes for a drawing
nobody reads at that size.
