# Visual Finding Boundary Specification

## Purpose

A rasterized figure supports some measurements and not others, and an agent
that can read the raster produces a third, different kind of output. This
spec pins the boundary between those three: which visual dimensions carry a
computed verdict, which are an announced silence with a named reason, and
where an agent's own reading of a raster is allowed to live. The boundary
exists to stop a judgement from being dressed as a measurement, and to stop
`unmeasured` from quietly becoming `pass` once an eye is in the loop.

This spec does not compute anything itself — `figure-raster` computes the
Tier 1 facts this spec classifies, and `diagram-obligation` owns the schema
slot the classified findings land in.

## Requirements

### Requirement: Every Visual Dimension Is Classified Into Exactly One Tier

Every visual dimension reported by the figure pipeline MUST be classified into
exactly one of three tiers: a Tier 1 **computed verdict** (`out-of-bounds`,
`overlap` from the raster; `min-printed-font`, `background`, `whitespace`,
`in-figure-title` from the figure PDF), a Tier 1 **evidence-only** fact
carrying no verdict (`canvas-occupancy`), or a Tier 2 **announced silence** —
`unmeasured` paired with a named reason code (connection/arrow correctness,
style/aesthetics/legend quality, and which component an overlap belongs to).
No dimension MAY exist outside this classification, and no dimension MAY be
reported as `pass` on the strength of a judgement rather than a computation.

#### Scenario: Canvas occupancy is never a failing condition

- GIVEN a rasterized figure whose lower band is measured as almost entirely
  background
- WHEN the visual findings are assembled
- THEN `canvas-occupancy` is reported as a number with no `pass`/`fail` value,
  even though it is the most visually striking fact measured

#### Scenario: Printed font size is a measured verdict against a declared floor

- GIVEN a figure PDF with a text layer, the manuscript body size (the
  `\documentclass` size option, 10 pt without one) and the width the figure
  prints at
- WHEN the visual findings are assembled
- THEN `min-printed-font` reads `pass` only when every text span (labels,
  ticks, legends, annotations), scaled to that printed width, is at least
  0.70 x the body size, and `fail` naming each offending span otherwise —
  the former `legibility` silence (`LEGIBILITY_IS_A_THRESHOLD_JUDGEMENT`) is
  replaced by this declared, measured rule

#### Scenario: A figure without a text layer leaves the printed font unmeasured

- GIVEN a figure PDF that carries no text layer (raster-only, or text
  converted to outlines)
- WHEN the visual findings are assembled
- THEN `min-printed-font` is reported `unmeasured` with reason
  `NO_TEXT_LAYER`, never `pass`

#### Scenario: Overlap ownership without a name is an announced silence

- GIVEN an `overlap` finding reporting two colliding regions by coordinates
  only
- WHEN the visual findings are assembled
- THEN which declared component either region belongs to is reported
  `unmeasured` with reason `UNATTRIBUTED_INK`, distinct from the `overlap`
  verdict itself

### Requirement: Every Dimension Is Always Present, Never Absent or Null

The assembled visual findings MUST include every classified dimension on
every call, regardless of what was actually measured. A dimension that was
not measured MUST default to `{"verdict": "unmeasured", "reason": "<code>"}`.
A dimension MUST NEVER be an absent key, and MUST NEVER be `null`.

#### Scenario: An unmeasured call still carries every dimension

- GIVEN a call where no rasterizer ran and nothing was measured
- WHEN the visual findings are read
- THEN every classified dimension is present as a key, each carrying
  `"verdict": "unmeasured"` and a named reason — reading any dimension by key
  MUST NOT raise a missing-key error

### Requirement: A Visual Verdict Never Changes the Semantic Verdict

No value of any visual dimension's `verdict` — including `fail` on
`out-of-bounds` or `overlap` — MAY change `figure audit`'s top-level semantic
`verdict` (`pass` | `fail` | `unmeasured`, owned by `diagram-obligation`'s
Figure-Prose Semantic Audit). The two verdicts MUST remain independently
readable in the same report.

#### Scenario: A visual failure alongside a clean semantic audit stays a pass

- GIVEN a figure whose semantic audit reaches `pass` and whose visual overlap
  check reaches `fail`
- WHEN the combined report is assembled
- THEN the top-level `verdict` remains `pass`, and `visual.overlap.verdict`
  independently reads `fail`

### Requirement: An Agent's Assisted Reading Is Labelled, Never a Verdict

An agent's own reading of a rasterized PNG MUST be reported under an explicit
`assistedReading` label, separate from every `visual.<dimension>.verdict`
field. Content placed under `assistedReading` MUST NOT be written into any
`visual.<dimension>.verdict` field, and it MUST NEVER cause an `unmeasured`
dimension to be reported as `pass`.

#### Scenario: A confident reading does not change the measured printed font

- GIVEN an agent that read the raster and judged the text legible, on a
  figure whose `min-printed-font` measured `fail` (or `unmeasured`)
- WHEN the agent composes its report
- THEN that judgement appears only under `assistedReading`, and
  `visual.min-printed-font.verdict` keeps its measured value, unchanged by
  the agent's reading

#### Scenario: A named suspicion does not resolve unattributed overlap

- GIVEN an agent that read the raster and suspects which two declared
  components an unnamed overlap finding belongs to
- WHEN the agent composes its report
- THEN that suspicion appears only under `assistedReading`, and the
  overlap-ownership dimension remains `unmeasured` with reason
  `UNATTRIBUTED_INK`

### Requirement: A Toolchain Refusal Is Not an Unmeasured Visual Finding

When the rasterizer toolchain refuses because no fallback link resolved, that
refusal MUST propagate as the reason every visual dimension is reported
`unmeasured` — the refusal itself is not, and must not be reported as, an
`unmeasured` dimension.

#### Scenario: An agent quotes the refusal as the unmeasured reason

- GIVEN a `RASTER_TOOLCHAIN_ABSENT` refusal from `figure-review`
- WHEN the agent reports the visual dimensions it could not measure
- THEN every visual dimension is reported `unmeasured`, quoting the exact
  refusal code as the reason, rather than a generic or invented reason
