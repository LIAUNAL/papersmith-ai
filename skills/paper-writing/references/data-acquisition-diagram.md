# The acquisition-protocol diagram

When a paper describes a **real dataset**, the explanation of that dataset ends on a
figure that shows how the data were captured. It is drawn by the `diagram-author`
agent, it is the **last artefact of the dataset explanation** (in Materials and
Methods, `mm-dataset`, or in the Experimental Set-Up, `es-dataset`, wherever the paper
placed the dataset), and the acquisition paragraph points to it before it appears.

A synthetic or simulated set does not get one: there is no capture to show. Its
generator is defined in the text, with its equation.

## What the figure answers

One question: *how did a raw record come to exist?* Read left to right (or top to
bottom), the figure walks the capture in the order it happened:

1. **Who or what is measured** — the participants, patients, plant, machine or site.
2. **The set-up** — sensors, their placement, the montage or the instrumented point.
3. **The task or operating condition** — the stimulus, the protocol phase, the load
   or regime during which the record was taken.
4. **The acquisition chain** — amplifier, logger or meter, with the sampling rate and
   the reference when the text gives them.
5. **The stored record** — one file, trial or session per unit, with its label.
6. **How a sample is cut** — the windowing or segmentation that turns a record into
   the samples the methods consume, when the text defines one.

Every value written in the figure (a channel count, a sampling rate, a window length)
is taken from the dataset paragraphs. A value the text does not state is not drawn.

## Pictograms, not only boxes

Each stage carries an **illustration of what it is**, drawn as a vector pictogram: a
patient wearing an EEG cap, a seated subject, a stimulus screen, an amplifier, a
computer, a database; for energy and industry, a wind turbine, a generator, an electric
machine, a sensor probe. A diagram made only of labelled boxes does not meet this
guide: **at least two stages carry a pictogram, chosen from the domain the dataset
comes from.**

The pictograms live in `skills/paper-writing/references/pictograms.tex`, a library of
TikZ `pic`s with no text and no fonts, so the audit reads them as drawn shapes.
**Copy the `\definecolor` lines and the `\tikzset` entries the figure uses** into the
figure's own standalone source; never `\input` the library. A domain the library does
not cover gets a new pictogram drawn the same way — strokes in the ink colour, fills in
the pale tints, no text inside — added to the figure's source, and, when it will serve
other papers, to the library.

## Never in the figure

- A measured result, a score, a curve — the figure shows the protocol, not what came
  of it (`DIAGRAM_PLOTS_DATA` refuses plotted data before any compile).
- The proposal's internals or any model: the figure stops at the samples.
- A raster image, a photograph, or an icon font: everything is vector TikZ.
- A value the dataset paragraphs do not state.

## Style and size

The figure obeys every rule of the configured diagram grammar, as the contribution
diagram does (`references/contribution-diagram.md`, "Style: the configured grammar,
restated"): `\documentclass[tikz,border=2pt]{standalone}`, explicit
`\fontsize{..}{..}` sizes printing between 0.70 and 0.90 x the body size, hyphenation
off, no overlaps, sentence-case labels, no background fill, readable in grayscale.

- Four to seven stages in one row (or two rows), each a frame holding its pictogram,
  with a label of at most three short lines under it.
- Design it at the width it prints at (`widthFraction` 1.0 is the full text width) so
  the scale stays near 1; a figure scaled down below that width pushes its labels
  under the 0.70 floor.
- Label nodes take `inner sep=0pt` and a `text width` no wider than their frame, so the
  content reaches the page edge within the 4 pt margin the audit allows.

## Example

A five-stage EEG protocol. The line `% <pictograms>` stands for the `\definecolor`
lines and the `pics/...` entries copied from `pictograms.tex`.

```latex
\documentclass[tikz,border=2pt]{standalone}
\usetikzlibrary{arrows.meta,positioning}
\hyphenpenalty=10000 \exhyphenpenalty=10000
\begin{document}
% <pictograms>
\begin{tikzpicture}[
  node distance=4mm and 6mm,
  stage/.style={draw=pgink, line width=1.3pt, rounded corners=3pt, fill=white,
    minimum width=24mm, minimum height=24mm, inner sep=0pt},
  label/.style={font=\fontsize{8.5}{10.2}\selectfont, align=center, text width=24mm, inner sep=0pt},
  flow/.style={-{Stealth[length=2.6mm]}, draw=pgink, line width=1.6pt},
  ]
  % node: participants
  \node[stage] (p) {};
  \pic[scale=0.85] at ([yshift=3mm]p.center) {pg eeg patient};
  \node[label, below=1.5mm of p.south] {Children seated, eyes open, 19-channel cap};
  % node: stimulus task
  \node[stage, right=of p] (s) {};
  \pic[scale=0.85] at ([yshift=3mm]s.center) {pg stimulus screen};
  \node[label, below=1.5mm of s.south] {Visual attention task on a screen};
  % node: acquisition chain
  \node[stage, right=of s] (a) {};
  \pic[scale=0.85] at ([yshift=3mm]a.center) {pg amplifier};
  \node[label, below=1.5mm of a.south] {Amplifier at 128 Hz, ear reference};
  % node: stored records
  \node[stage, right=of a] (r) {};
  \pic[scale=0.85] at ([yshift=3mm]r.center) {pg database};
  \node[label, below=1.5mm of r.south] {One record per child with its label};
  % node: sample construction
  \node[stage, right=of r] (w) {};
  \pic[scale=0.85] at ([yshift=3mm]w.center) {pg signal traces};
  \node[label, below=1.5mm of w.south] {Windows of 4 s kept per child};
  \draw[flow] (p) -- (s); \draw[flow] (s) -- (a); \draw[flow] (a) -- (r); \draw[flow] (r) -- (w);
\end{tikzpicture}
\end{document}
```

Its manifest, `paper/Figures/<id>.diagram.json`, names one component per marked stage:

```json
{
  "components": ["participants", "stimulus task", "acquisition chain", "stored records", "sample construction"],
  "encodings": ["framed pictograms", "arrows"],
  "caption": "Acquisition protocol of the EEG dataset, in the order of capture. Framed pictograms show each stage: participants, stimulus task, acquisition chain, stored records and sample construction; arrows follow a record from the child to the samples.",
  "widthFraction": 1.0
}
```

## Before calling `render`

- The figure is the last artefact of the dataset explanation, and the acquisition
  paragraph references it before it appears.
- At least two stages carry a domain pictogram; no raster or icon font.
- Every value in the figure is stated in the dataset paragraphs.
- Every `% node:` marker matches a manifest component, and the reverse.
