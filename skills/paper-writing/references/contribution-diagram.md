# The contribution diagram

The figure that closes Materials and Methods (`sections/01-materials-and-methods.md`,
block `mm-proposal`, "The summary diagram"). It is the one picture of the paper a
reader can study alone: with only this figure and its caption, they can say what
enters the method, what each stage does to it, what is new, what is optimized and
what comes out.

The `diagram-author` agent reads this guide before drafting the figure. The guide is
general on purpose: it fixes the parts, their order and their visual grammar, never
the content of any one paper. A network, a kernel method, a probabilistic model and a
processing pipeline all fit it; section 3 says how the core changes between them.

## What is checked, and what is only drawn

Two layers share the figure, and only one of them is checked mechanically.

- **The contribution panels are the components.** Each panel carries one
  `% node: <label>` marker in the source, its label is the roster name exactly as the
  section defines it, and the manifest's `components` lists them in the roster's
  order. The Components Check, the excluded-class check and the caption check read
  only these labels (`skills/paper-writing/scripts/paper_obligation.py`).
- **Everything else is context, and carries no marker.** Inputs, encoders, embedding
  spaces, heads, losses, outputs and the legend are drawn without `% node:`, so the
  checks never count them, and the figure audit never reports them as phantom
  components. Context is what makes the figure detailed; it is never what makes it
  pass.

A label that is both (a contribution that is also an encoder) is a panel: mark it once.

## Anatomy and reading order

Read left to right, top to bottom, in this order of columns:

```
 inputs ──▶ representation ──▶ core stages ──▶ heads / outputs
                                  │  ① contribution panel ──▶ L_1 ─┐
                                  │  ② contribution panel ──▶ L_2 ─┼─▶ total objective
                                  └──────────── outputs ──▶ L_0 ───┘
                                                         legend (corner)
```

- One spine: the main data flow runs along one row or one column. Branches leave the
  spine and come back to it or to the objective; they never cross it.
- Contribution panels sit where the method uses them, in roster order, and are
  numbered ①, ② … in that order. When the method uses them in another order, the
  numbers still follow the roster, and the arrows carry the real order.
- The objectives converge on one total objective box at the right edge or the bottom
  edge, never in the middle of the flow.
- Four to six columns at most. A figure that needs more is two figures, and only the
  first one closes the section.

A worked reading of the anatomy: in a domain-adaptation figure, labeled source
bags and unlabeled target bags enter on the left as glyph tiles. Two encoders map
them into one framed embedding space, where per-instance relevance bars weight each
bag. Weighted bag vectors feed a shared classifier, whose source prediction meets
its label in a source loss and whose target prediction emits pseudo-labels and
confidences along dashed conditioning arrows. A common kernel matrix feeds two
numbered contribution panels, one global and one local, each holding its own
small equation and loss. All three losses meet in a total objective box, and a
legend in the corner decodes arrows and domain colors.

## 1. Inputs

The data enter **as mathematical objects**, never as a named dataset.

- Name each input by its symbol and its shape: $X \in \mathbb{R}^{C \times T}$,
  bags $B_i = \{x_{i1}, \dots, x_{in_i}\}$, labels $y_i$, a graph $G = (V, E)$.
- When the method treats inputs differently (labeled and unlabeled, source and
  target, train and query), draw one framed group per role, with its own tint.
- Draw a few representative items as glyph tiles: at most four, then an ellipsis
  (`\cdots` or `\vdots`) for the rest. Glyph shape may encode class (circle,
  square, triangle), and the caption decodes it.
- Never: the dataset's name, subject counts, sampling rates, montages, acquisition
  protocols. Those are the experimental setup's; here they are the excluded class
  `dataset`.

## 2. Representation

How the inputs become what the core works on.

- An encoder or feature map is a trapezium narrowing toward its output, labeled with
  its role in words and its symbol with parameters ($F_{\theta}$, $f_{\phi}$).
- A shared space (embedding space, feature space, Hilbert space, token sequence) is one
  framed region that holds the representations of every input role, so the reader
  sees that they are comparable.
- State dimensions only where the method depends on them ($z \in \mathbb{R}^{d}$,
  $d = 4$). Never a layer count or a width chosen by tuning: that is a
  hyperparameter, and it belongs to the experimental setup.

## 3. Core stages

Choose one of two drawings, never both.

- **A network architecture**, when the method is a learned network: one shape per
  block type (trapezium for an encoder, stacked rectangles for repeated layers with a
  `\times L` badge, a circle with $\oplus$ or $\otimes$ for a merge, a small grid for
  an attention or kernel matrix, a circuit strip for a quantum layer). Tensors
  between blocks are thin pills labeled by symbol.
- **A flowchart**, when the method is a procedure, an estimator or a pipeline that is
  not one differentiable network: rounded rectangles for stages, a diamond only for a
  real branching decision, and a loop arrow for an iteration with its stopping rule
  in a short label.

Either way, at most six to eight core blocks; a block that a reader cannot connect to
an equation of the section does not belong in the figure.

## 4. Contribution panels

Each contribution is one framed panel, and this is where the figure says what is new.

- The panel's title is a numbered badge and the roster name: `① Class-conditional
  alignment`. The title text is the `% node:` label, character for character.
- The panel uses the `focal` role of the visual grammar (below): a thicker outline,
  a light warm tint, the title in bold. Nothing outside a panel is focal.
- Inside, the panel shows the mechanism in its smallest readable form: its inputs as
  arrows entering the frame, one or two inner blocks, its key equation, and its loss
  leaving the frame toward the objectives.
- When the paper claims interpretability, its mechanism (the attribution map, the
  relevance score, the readable parameter) is a panel like any other.
- A borrowed component the contribution builds on is context, drawn plainly outside
  the panels. Highlighting it would claim it.

## 5. Mathematics inside the figure

The figure carries the basic mathematics of the proposal, not its derivation.

- One or two short display expressions per contribution panel, and one for the total
  objective. Each is the section's own equation, with the same symbols. When the
  equation is numbered in the text, a small `(N)` after it lets the reader find it.
- Symbols on arrows and blocks are the ones the section declares: no symbol may
  appear in the figure that the prose never introduces, and none may change meaning.
- Write math in TikZ nodes as `$…$`, at the same explicit font size as the label
  around it. A fraction or a sum that does not fit its box at that size is shortened
  (name the term, write it in full in the text); the font is never shrunk.
- Never: intermediate steps, proofs, numeric values of hyperparameters, or a result.

## 6. Objectives

Every loss term is drawn, and all of them meet once.

- Each loss is a pill labeled with its symbol ($\mathcal{L}_{\text{src}}$,
  $\mathcal{L}_{\text{glob}}$, $\mathcal{L}_{\text{loc}}$), placed where its
  operands meet: a supervised loss beside the prediction and its label, a
  contribution's loss at the edge of its panel.
- A two-headed arrow between a prediction and its target says "compared by this
  loss".
- One total objective box receives every loss and shows the general combination of
  the section (item 4 of Slot 3), e.g.
  $\mathcal{L}_{\text{total}} = \mathcal{L}_{\text{src}} + \lambda_1 \mathcal{L}_{\text{glob}} + \lambda_2 \mathcal{L}_{\text{loc}}$,
  with the weights as symbols, never their values.
- A method without a training loss (an estimator, a closed-form solution, a
  probabilistic model) replaces this box by its criterion or its inference: the
  posterior, the predictive distribution, the optimization problem it solves.

## 7. Outputs

What the method returns, by symbol and meaning.

- Each output is labeled with its symbol and a two-to-four-word description:
  $\hat{y}$, class probabilities, hard pseudo-labels, entropy confidence, a saliency
  map $I(c, t)$.
- A miniature (a bar glyph for a distribution, a small heat grid for a map) may show
  the output's kind. It is schematic: drawn with fixed illustrative shapes, never from
  measured numbers (`DIAGRAM_PLOTS_DATA` refuses a plotted series).

## 8. Auxiliary flows

Arrows carry two independent facts, as in the experiment diagrams.

- Semantics: data flow is solid, supervision and conditioning are dashed (a
  pseudo-label or a confidence fed back into a loss), feedback curves back, and an
  inhibition ends blunt.
- Prominence: the spine is primary (dark, thick); every other arrow is secondary
  (gray, thinner). The difference must survive grayscale.
- Arrows are routed orthogonally (`|-`, `-|`) along shared lanes, enter a block from
  the side that faces their source, and never run through a label or a panel title.

## 9. Legend and caption

- An in-figure legend in a corner (bottom right by default) decodes the arrow types
  and the role tints, in a dashed frame, with entries of two to four words. It is
  context, never a component.
- The caption still decodes everything (`caption_decodes`): every entry of the
  manifest's `encodings` appears in the caption verbatim, so the figure reads
  correctly even where the legend is cropped.
- The caption enumerates the contribution panels in roster order
  (`caption_enumerates`), by the same names, and says in one opening sentence what the
  whole figure summarizes.

## Style: the configured grammar, restated

Every rule already enforced on paper figures applies; this list restates the ones the
figure meets most often, so it is written right the first time.

- **Header and width.** `\documentclass[tikz,border=2pt]{standalone}`. The figure
  prints at the full text width (`widthFraction` 1.0; a `figure*` in a two-column
  template), so design it at that width and keep the scale near 1.
- **Explicit sizes only.** `\fontsize{<pt>}{<1.2 pt>}\selectfont`, never `\small`,
  `\footnotesize` or any relative switch. At the printed width every size lies
  between 0.70 and 0.90 x the manuscript body size. Three sizes at most: panel
  titles, labels, and sub- or superscripts inside math (which TeX scales itself).
- **No overflow.** Hyphenation off (`\hyphenpenalty=10000 \exhyphenpenalty=10000`),
  every box wider than its longest word: an `Overfull \hbox` fails the audit. When a
  label does not fit, shorten it or widen the box.
- **No overlaps.** No two labels intersect, no label crosses a frame it does not sit
  inside, no arrowhead touches a label. Leave at least one label height between
  neighboring frames.
- **Labels.** Written in sentence case, two to four words, never Title Case. Two font weights:
  bold for panel titles and the total objective, regular for everything else.
- **Roles.** `state` (data or a feature at rest) is a pale pill; `focal` (a
  contribution panel) is a warm tint with a thick outline; `context` (an encoder, a
  head, a loss) is a plain restrained frame; `group` (an input role, a shared space) is
  a light wash behind its members, never a heavy box.
- **Palette.** Ink `#20252B` for text and primary arrows; cool `#4F7CAC` and warm
  `#D96855` for the two input roles when there are two; warm `#E09F3E` for the
  contribution panels' outline; pale tints of the same hues for fills; gray for
  secondary arrows. Hue is decoration: value and stroke weight carry the meaning, so
  the figure reads in grayscale. No background fill.
- **Strokes.** Connectors 1.4-1.9 pt, outlines 1.3-1.8 pt, panel outlines at the top
  of that range.
- **Layout code.** Every option list used twice is one `\tikzset` style; positions
  are relative (`right=of`, `below=of`), never absolute coordinates that depend on a
  sibling's size; load only the libraries the source uses.

## Size budget

- 15 to 30 drawn blocks in total, of which the contribution panels are two to five.
- Nesting at most two levels inside a panel (panel, inner block).
- At most four glyph tiles per input role, and an ellipsis for the rest.
- One display equation per panel and one in the total objective is the norm; two per
  panel is the limit.

A figure over budget is cut, not shrunk: merge stages the text treats as one, move a
borrowed detail into the text, keep the panels whole.

## Never in the figure

- The dataset's name, its sizes and its acquisition (the excluded class `dataset`).
- Any baseline or competing method (the excluded class `baseline`).
- Evaluation: a metric, a protocol, a split, a statistical test.
- A measured value of any kind: an accuracy, a curve, a learned weight, a plotted
  series.
- Implementation detail: frameworks, file names, hardware, hyperparameter values.

## The manifest

The manifest lists the contribution panels as `components`, in roster order, and every
visual encoding the caption must decode. An example for a two-contribution method:

```json
{
  "components": ["Class-conditional alignment", "Personalized source references"],
  "encodings": ["blue", "red", "solid arrows", "dashed arrows", "numbered panels"],
  "caption": "Overview of the proposed method, from the input bags to the total objective. Encoders map labeled source bags (blue) and unlabeled target bags (red) into a common embedding space, where relevance weights build bag representations for a shared classifier. Two numbered panels hold the contributions: (1) Class-conditional alignment, which matches source and target bags class by class through a quadratic Renyi entropy of the common bag kernel; and (2) Personalized source references, which build for each target bag a weighted reference from its most similar source bags. Between them, solid arrows carry data and dashed arrows carry pseudo-labels and confidences that condition the alignment. The source, global and local losses add up to the total objective.",
  "widthFraction": 1.0
}
```

## Before calling `render`

1. Every contribution panel carries `% node:` with its roster name, and nothing else
   does.
2. The manifest's `components` equal the roster, in order; the `contributions` fact
   is declared (`declare --fact contributions --value '[...]'`).
3. Every symbol in the figure is declared in the section's prose, and every equation
   in a panel is the section's own.
4. No dataset name, baseline, metric or measured value appears anywhere in the
   figure, context included.
5. Every encoding in the manifest appears verbatim in the caption, and the caption
   names the panels in roster order.
6. `figure optimize`, then `render --figure-id <id> --section 01-materials-and-methods
   --block mm-proposal`, then the visual pass.
