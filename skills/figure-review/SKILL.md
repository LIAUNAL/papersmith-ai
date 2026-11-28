---
name: figure-review
description: "Trigger: check whether a compiled `paper/Figures/<id>.pdf` reads as a picture: rasterize and measure overflow, collisions, occupancy, text size, background and margins (`probe`, `raster`, `measure`). Reports only; never repairs or compiles."
---

# Figure Review

**Scope.** After `render` has already written a compiled figure to `paper/Figures/<id>.pdf`, and a reader needs to know whether the picture itself reads — not the prose that describes it. Turns an already-compiled PDF into pixels and computes the geometric facts a raster can actually support: whether ink runs off the canvas, whether ink regions collide, and how much of the canvas is occupied. Also reads the figure PDF's own text layer and drawing for four declared rules: every text span prints between 0.70 and 0.90 x the manuscript body, no full-page background, no margin wider than 4 pt, no in-figure title. Reports advisories beside them: values printed inside the figure, floats under 90% of the text width, float-only pages and large gaps in the compiled manuscript. Never repairs a figure, never compiles LaTeX, never judges style. Verbs: `probe` names the rasterizer this machine will use; `raster` produces the PNG and its provenance; `measure` reports every dimension.

`render` compiles a diagram source to a PDF and stops there. `figure audit`
then checks that PDF's declared manifest against the prose that describes it.
Between the two, nothing ever looks at the picture — every visual dimension is
reported `unmeasured`, honestly, because nobody ever rasterized it.

This skill closes that gap, and only that gap. It consumes a PDF `render`
already produced; it never compiles anything, and it never touches the
per-figure repair budget that guards `render`'s own compile attempts. Its job
ends at pixels, the facts a raster can actually support, and four declared
rules read from the figure PDF itself — it never repairs a figure.

## What this skill answers, and what it refuses to

**Answerable from pixels alone, with a computed verdict:**

- Whether non-background ink sits inside the outermost pixel row or column of
  the raster — ink running off the canvas.
- Whether two ink regions' bounding boxes collide — reported by coordinates
  only, never by a component's name, because a raster carries no names.

**A number worth reporting, with no verdict attached:**

- How much of the canvas each band occupies. A canvas that is a third blank
  is a fact, not a failing condition; deciding whether that is "too much" is a
  composition judgement this skill does not make.

**Read from the PDF, with a computed verdict** (`measure`; the rules live in
`skills/_core/figure/figure_dimensions.py`, the same ones `paper-writing`'s
`place` refuses with):

- `printed-font-range` — every text span (labels, ticks, legends,
  annotations), at its printed size, is between 0.70 and 0.90 x the
  manuscript body (`skills/_core/figure/print_scale.py`); a `fail` names
  `TEXT_BELOW_PRINT_FLOOR` or `TEXT_ABOVE_PRINT_CAP` and each offending
  span its `bound`. It was the floor-only `min-printed-font` before 0.54
  (`figure_dimensions.DEPRECATED_DIMENSION_ALIASES` maps the old key). The printed size is the span size
  times the printed width / the PDF width. The printed width is
  `--printed-width-pt`, else the figure's `\includegraphics` `width=`/`scale=`
  in `--main-tex` (default `<paper>/main.tex`, `\input` files included),
  resolved against `\textwidth`, `\linewidth` and an enclosing minipage or
  subfigure, else natural size. The body is `--body-pt`, else the size the
  compiled `--main-log` (default `<main-tex>.log`) shows the class loaded
  (`size11.clo`, `scrsize11pt.clo`, `mem11.clo`, IEEEtran's "This is a 10
  point document."), else the `\documentclass[<N>pt]` option, else 10 pt.
  `\textwidth` is geometry's or typearea's line in the log, else a known
  one-column class default. The report's `sources` names where each of the
  three values came from. A PDF without a text layer is `unmeasured`
  (`NO_TEXT_LAYER`).
- `background` — a filled rectangle covering the page (`FULL_PAGE_BACKGROUND`).
- `whitespace` — a margin wider than 4 pt between the drawn content and the
  page (`MARGIN_WASTE`, naming the sides).
- `in-figure-title` — a row of text above every drawn path, as large as the
  axis labels and at least 30 % of the width, crossed by no path
  (`TITLE_BELONGS_IN_CAPTION`, naming the text): the caption carries it.

An unreadable PDF leaves these four `unmeasured` with `PDF_UNREADABLE`; the
raster dimensions are still reported.

**Advisories** (the report's `advisories`, beside the roster; each reads
`advisory`, `pass` or `unmeasured` with a reason, and none fails the figure
or the call):

- `numeric-text` — a row of words carrying a value (`acc = 0.93`, `n = 120`,
  `87.5%`) or an isolated decimal or percentage not aligned with two other
  numbers the way tick labels are (`NUMERIC_TEXT_IN_FIGURE`): a value is
  shown first by a data figure's own marks (a bar's height, a point with its
  interval, read off the axis), then stated in the prose, and only then
  listed in a table; never printed as text inside the picture. This follows
  paper-writing's figures-over-tables rule for Methods and Results (about
  60 % figures and 40 % tables, `verify`'s `figure-table-balance`).
- `width-share` — every figure and table float printed under 90 % of
  `\textwidth` (`NARROW_FLOAT`). A figure's width is its widest row of
  graphics or minipages in `main.tex`; a table's is its declared width
  (`tabularx`, `tabular*`, `\resizebox`), else its widest rule in
  `--main-pdf` (default `<main-tex>.pdf`). `TEXT_WIDTH_UNKNOWN` or
  `MANUSCRIPT_SOURCE_ABSENT` when it cannot be read.
- `page-whitespace` — per page of the compiled manuscript, whether it holds
  only floats (`FLOAT_ONLY_PAGE`) and every vertical gap of at least 72 pt
  (`LARGE_GAP`, as a forced `[H]` float leaves); the last page's trailing gap
  is not reported. `MANUSCRIPT_PDF_ABSENT`, `PDF_UNREADABLE` or
  `PDF_READER_ABSENT` when it cannot be read.

**Never answerable from pixels, and never claimed to be:** arrow
or connection correctness, style, aesthetics, legend quality, and which
declared component an overlap belongs to. Each of these stays an announced
silence — `unmeasured` with a reason naming exactly why — rather than a guess
dressed up as a measurement. A `pass` on any of these would be strictly worse
than today's honest silence.

## The front door is a command, not a session claim

Whether this skill is usable is a fact anyone can check by running it, never
an agent's unverified claim that it happens to be "available in this
session." The front door answers `--help` and reports which rasterizer this
machine will use.

```
python scripts/review_cli.py probe [--json]
python scripts/review_cli.py raster --pdf <path/to/example-figure.pdf> [--dpi 150] [--out <dir>]
python scripts/review_cli.py measure --pdf <path/to/example-figure.pdf> [--out <dir>] [--tex <path>]
                                     [--body-pt <pt>] [--main-tex <path>] [--main-log <path>]
                                     [--main-pdf <path>] [--printed-width-pt <pt>]
```

`probe` names the first tool this skill's fallback chain finds — in order,
`pdftoppm`, `pdftocairo`, `gs`, `sips` — and exits 2 naming every one of the
four it probed, plus the exact `PATH` it searched, when none resolves. That
refusal is never reported as an `unmeasured` visual dimension: an absent tool
is an unreadable invocation, not a dimension this skill declined to judge.
Whoever consumes the refusal (an agent, another verb) quotes it as the reason
every dimension went unmeasured.

`raster` writes a PNG plus its provenance (which tool produced it, at what
DPI, and whether that DPI was requested or derived) beside the figure it
rasterized. It reads no ledger and writes no ledger: a full pass — successful
or one where every fallback link fails — leaves `render`'s repair budget
byte-identical, because rasterizing a picture that already exists is not a
compile.

## What this skill never does

- It never invokes a LaTeX toolchain and never opens a repair-budget ledger,
  under any code path, including a failed rasterization.
- It never repairs or redraws a figure. Reading the picture and deciding what
  to change about it are different jobs, kept apart on purpose.
- It never imports another skill's scripts, and no other skill imports this
  one's. The two sides meet only through a plain-data file on disk.
- It never reports a judgement — style, "does this look right" —
  as a measurement. Two boxes that merely sit close together, or an arrow that
  merely looks thin, are not findings this skill produces; only a computed
  collision or an out-of-bounds pixel is.

## Subprocess boundary

`raster.py` is the only module in this skill permitted to spawn a process —
every rasterizer link this skill can reach lives behind that one seam, pinned
by this skill's own test suite the same way `paper-writing` pins its own.
Every invocation is a list of arguments, never a composed shell string, and
the figure path is always resolved to an absolute path before it reaches
argv, so a path beginning with a dash is never mistaken for a flag.
