---
{
  "section": "materials-and-methods",
  "position": 5,
  "mode": {
    "value": "transposition",
    "source": {
      "file": "sections/01-materials-and-methods.md",
      "quote": "The proposal already exists."
    }
  },
  "blocks": [
    {
      "id": "mm-preamble",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none",
      "optional": true,
      "after": [
        {
          "target": "materials-and-methods.mm-proposal",
          "source": {
            "file": "sections/01-materials-and-methods.md",
            "quote": "It names the subsections that follow and their order."
          }
        }
      ]
    },
    {
      "id": "mm-dataset",
      "requires_facts": [
        {
          "value": "dataset",
          "source": {
            "file": "sections/01-materials-and-methods.md",
            "quote": "The dataset — when this section owns it"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "resolution",
      "optional": true
    },
    {
      "id": "mm-borrowed-machinery",
      "requires_facts": [
        {
          "value": "formulation",
          "source": {
            "file": "sections/01-materials-and-methods.md",
            "quote": "The mathematical formulation of the proposal"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "resolution"
    },
    {
      "id": "mm-proposal",
      "requires_facts": [
        {
          "value": "formulation",
          "source": {
            "file": "sections/01-materials-and-methods.md",
            "quote": "The mathematical formulation of the proposal"
          }
        }
      ],
      "requires_declarations": [],
      "citations": "resolution",
      "produces_facts": [
        {
          "value": "contributions",
          "source": {
            "file": "sections/01-materials-and-methods.md",
            "quote": "This section defines the contributions."
          }
        }
      ],
      "after": [
        {
          "target": "materials-and-methods.mm-borrowed-machinery",
          "source": {
            "file": "sections/01-materials-and-methods.md",
            "quote": "state the proposal as a delta on the borrowed machinery, with an explicit reference to the previous equation by number"
          }
        },
        {
          "target": "materials-and-methods.mm-dataset",
          "source": {
            "file": "sections/01-materials-and-methods.md",
            "quote": "The proposal is always the last block of the section. Without exception."
          }
        }
      ],
      "figure": {
        "components_from": "contributions",
        "ordered": true,
        "excludes": ["dataset", "baseline"],
        "caption_enumerates": true,
        "caption_decodes": true,
        "mandatory": true
      }
    }
  ]
}
---
# Materials and Methods

**Extent** 1000–3950 words · 2 to 9 subsections
**Carries** the problem setup, the borrowed machinery, the proposal (its interpretability mechanism included), and one summary diagram
**Does not carry** any result, measured number, comparison, or evaluation protocol

This section defines the contributions. It names each one here and gives it its
formal definition, in the notation everything downstream reuses; the introduction
receives that list and drafts from it.

## Nothing is decided here

The proposal already exists. This section does not choose it, improve it, or argue
for it — it carries an existing formulation into this structure. Where the section
looks like it is deciding something, it is reporting a decision taken elsewhere.

## Preamble

Optional: seven of the group's ten measured papers have none, and their first
subsection starts at once. When written, it is one paragraph of 60–120 words, no
citations, naming the method once. It names the subsections that follow and their order. Nothing else — no motivation,
no problem, no result.

## Subsection order

Three slots, with the problem setup opening the formal part. The third slot is
invariant. Each slot is tied to one element the introduction already stated, and
that tie is what keeps the section from re-arguing the paper.

| Slot | Subsections | Paragraphs | Words each | Realizes from the introduction |
|---|---|---|---|---|
| 1 — The dataset, when this section owns it | 1 or 2 | 3–12 | 300–1000 | the application named in the motivation; the datasets it named |
| Problem setup (opens the formal part) | 0 or 1 | 1–4 | 80–350 | the problem, formalized |
| 2 — The borrowed machinery | 1 to 3, one per pillar | 3–12 each | 180–1480 | the pillars, one to one, in the introduction's order |
| 3 — **The proposal** | 1 to 3, one per contribution or one with the roster | 3–12 each | 380–1420 | the novelty: each contribution, under the property it delivers |

**What never appears here:** the motivation (zero sentences), the evaluation of the
proposal, and anything measured. Training, hyperparameter search, metrics, baselines,
validation protocol and statistics belong to the experimental setup, always.

**The dataset placement is a structural decision, and it is taken once.** If the
dataset belongs to this section it goes first, and the section opens on the data. If
it belongs to the experimental setup instead, this section starts directly on the
machinery and stays purely formal — carrying no figure other than the proposal's
diagram. The decision changes the contract of both sections, so it is recorded rather
than improvised.

**The proposal is always the last block of the section. Without exception.** When it
spans several subsections, they are consecutive and nothing follows them.

## Slot 1 — The dataset

3 to 12 paragraphs, in one subsection or two (synthetic and real, or one per source).
One or two figures — the acquisition protocol, always, for a real dataset, and
representative samples when they help. Zero to two
tables — variable lists or summary statistics. Few equations: the segmentation or
windowing that defines a sample is the usual one.

Paragraph sequence:

1. Why these data answer the question, and their provenance.
2. One paragraph per dataset or site, when there are several.
3. Acquisition — protocol, sensors, task — pointing to its acquisition-protocol
   diagram, which closes the dataset explanation.
4. What was discarded, then the preprocessing kept.
5. How a sample is built, with its notation.
6. When subjects or sources repeat, how they stay together so nothing leaks across
   a split; the split itself is the experimental setup's.

Open according to whose data it is:

- **Own or constructed data:** provenance and time span in the first sentence, then
  the objective that justifies those variables.
- **Public data:** why *these* sets answer the question, and what makes them differ
  from one another.

**State what was discarded before stating what was kept** — exclusions, quality
filters, removed records.

**A real dataset closes on its acquisition-protocol diagram.** When the data were
captured — recorded from patients, subjects, machines, plants or sites, as opposed to
generated by a simulator — the explanation of each real dataset ends on a figure the
`diagram-author` agent draws following `skills/paper-writing/references/data-acquisition-diagram.md`:
the capture in the order it happened (who or what is measured, the set-up, the task or
operating condition, the acquisition chain, the stored record, how a sample is cut).
Its stages are illustrated with domain pictograms from
`skills/paper-writing/references/pictograms.tex` — a patient wearing an EEG cap, a
generator or a machine — never boxes alone. It is the last artefact of the dataset
explanation, and the acquisition paragraph references it before it appears. A
synthetic set has no capture to show and gets no such figure.

**This is where the credit debt from the introduction is paid.** A dataset named in
the introduction without a reference is named here with one.

## Problem setup

The formal part opens on the problem, stated in symbols: one to four paragraphs,
either as their own subsection or as the opening paragraphs of the first machinery
subsection. Input and output spaces, the labels or annotations, and the formal goal —
the estimator, objective, or `\arg\min` the proposal will answer. Each property the
introduction's problem statement names is given here the same name it carries there.
No citation is needed unless the setup itself is borrowed.

## Slot 2 — The borrowed machinery

One to three subsections, each a body of existing theory the proposal needs — **one
per pillar the introduction names, in the introduction's order.** This is where the
bulk of the paper's mathematics lives.

Paragraph sequence of each subsection: notation, then one paragraph per equation
with its *where* clause, then the reading the proposal relies on.

**The machinery closes on the gap.** The last paragraph of the subsection the proposal
modifies states, in one or two sentences, the limitation of that borrowed piece in the
words the problem statement uses — *this term is a cross-entropy, so it degrades
under label noise*. It is technical, never the application's motivation, and it is the
only place the problem returns before the proposal.

**Ordered so that each subsection uses only symbols the previous ones declared.** It
is a chain of notation, not a list of topics.

**Each subsection opens by declaring notation, before any equation.** No mathematical
subsection opens on an equation. Use set-builder notation with an explicit index
domain for a collection.

**Developed only to the depth the proposal uses it.** More than that is related work
leaking in.

## Slot 3 — The proposal

Always last. The least cited part of the paper. One to three subsections: one per
contribution, or one that carries them all and closes on the roster.

**Interpretability is a contribution of this section when the paper claims it.** Its
mechanism — the attribution map, the relevance score, the readable parameter — is
defined here with its equation, like any other contribution. What it reveals on data
is a result.

**The evaluation of the proposal is never a contribution of this section.** Protocol,
metrics, baselines and statistics are the experimental setup's, always.

**1. Opening: name the method and state its setting.** Where possible, state the
proposal as a delta on the borrowed machinery, with an explicit reference to the
previous equation by number — so the reader knows exactly what changed relative to
what was just read. One sentence may recall the gap the machinery closed on; no more.

**2. Its own notation**, if the proposal introduces symbols the machinery did not
have.

**3. The contributions, defined, in the order this section establishes.** The
introduction's list follows this order, never the reverse. Each one: what it
introduces, its equation, and the symbol it leaves available to the next. Each
contribution is defined here and nowhere else.

**Each contribution is defined under the property it delivers**, named in the same
words the problem statement uses for that property. The introduction's contribution
list then reuses that exact name. That shared name is what makes the chain from the
problem to the evidence traceable rather than merely plausible.

**4. The general combination.** The single expression that brings every contribution
together — the sum, the composite objective, or whatever applies to the case. Two
positions, both admissible: at the end, building the pieces and closing on the
integration; or at the start, stating the complete objective with its constraints and
then taking it apart.

This is the only place in the paper where all the contributions appear together, and
it is the payoff of the notation chain: **every symbol in it must trace back to a
prior declaration.** One that does not means the chain broke earlier.

When the contribution is a system rather than a formulation, the combination is
carried by the enumeration of stages and by the diagram. There the diagram is not a
summary — it is the combination itself.

**The contribution list must be readable as a list, in the diagram's own order.** Two
structures satisfy that, and only one of them is ever needed:

- **Each contribution is its own subsection.** The sectioning already is the ordered
  list — its headings name the contributions, in order, and a reader meets them as
  structure rather than as prose. Nothing further is required, and an `\item` roster
  repeating those same headings a few lines later is redundancy, not a mandate.
- **The contributions are run into the prose.** Then the list has no other form, and
  one is written immediately before the closing pointer: one LaTeX `\item` per
  contribution, naming it exactly as defined above, in the diagram's own order,
  nothing more per item.

Either way, what the section's own Components Check reads back against the diagram is
that ordered list of names — whichever of the two carries it.

**Inference, when the model is probabilistic.** The predictive distribution or its
moments close the formulation, after the general combination and before the pointer.

**5. The closing: pointer and summary diagram.** Mandatory. The last prose sentence
points to the figure by number and says what it summarizes; the figure follows
immediately.

**Optional, and only where there is something to say:** a clause on convergence or
stability, distinguishing the consistency of the estimator from the empirical
convergence of training. It belongs here and not in the experimental setup — that
section is past-tense procedure, and a convergence argument is a present-tense claim
about the formulation.

### The summary diagram

- **It summarizes the contribution in detail.** A reader who sees only this figure and
  its caption can say what enters the method, what each stage does, what is new, what
  is optimized and what comes out. Its parts, in reading order: the inputs as
  mathematical objects (symbols and shapes, never a named dataset); the representation
  they are mapped into; the core stages, drawn as a network architecture when the
  method is a network and as a flowchart otherwise; one numbered panel per
  contribution, holding its mechanism and its key equation; the losses, meeting in the
  total objective that the general combination states; the outputs, by symbol and
  meaning; and a legend for its arrows and colours. The guide
  `skills/paper-writing/references/contribution-diagram.md` gives each part, the
  visual grammar and the size budget.
- **Its contribution panels are the contribution list**: exactly the same components,
  in the same order, under the same names this section's own roster gives them. Each
  panel carries the source's `% node:` marker; the inputs, stages, losses and outputs
  around them are context and carry none.
- **The caption enumerates the panels in that order** and decodes anything the figure
  encodes — if there are colours, the caption says what each one means.
- **It shows the method, not the experiment.** No dataset and no baseline appears in
  it, as a panel or as context; those belong to the experimental setup's own diagram.
  A box appearing in both means one of the two is wrong. Neither does a metric or a
  measured value: the figure carries the basic mathematics of the method, never a
  result.
- **The Components Check this diagram undergoes compares it against this same
  block's own roster.** That is intra-block drift, never cross-section
  corroboration — nothing outside this block is consulted.

## Every artefact is referenced before it appears

Any numbered object — figure, table, or panel — is referenced in the body **before**
it appears, and the pointer resolves to the exact sub-element when the artefact has
parts. An artefact appearing with no prior reference is either misplaced or dead.

## Continuity

Everything must read as continuous, and continuity here is checkable rather than felt.

**Every symbol traces to its declaration.** Each subsection uses only what the
previous ones declared, and the proposal opens by naming what it takes from the
machinery.

**No symbol is reused for a different quantity.** When two quantities would naturally
collide on the same letter, separate them with a diacritic and declare both in the
same sentence, so the reader sees the distinction once.

**A diacritic marks a relation to an already-declared object**, never decoration.
Four uses:

- the same object after a transformation;
- an estimator of a declared quantity;
- a normalized version of a declared quantity;
- the disambiguation of two distinct quantities that would share a letter.

## Extent counts prose, never mathematics

Every word count in this contract measures the prose. A displayed equation, its
label and its number are not prose and count toward no extent here.

**A formulation whose mathematics is long is not thereby a formulation that must be
cut.** The mathematics transfers as it stands; what the extent constrains is what is
written around it — the notation that declares its symbols, the sentence that
announces each expression, and the reading that follows it. When a subsection runs
past its extent, the prose is what tightens, never the derivation.

A section that drops steps of its own source's mathematics to fit a word budget has
misread the budget. Nothing in this contract licenses that.

## Equations: display and number are two separate decisions

**Display by readability.** An expression that cannot be read inline — multi-line,
carrying constraints, summing over indices — is displayed. What reads in a running
line stays in the text.

**Number every displayed equation.** The group's papers number all of them, so a
reader can name any expression by its number. Numbering is not a promise of a later
reference; what this section owes is that each number it does cite exists.

**Referenced equations are named by number** across subsections and across sections.
That cross-reference is what makes the notation chain verifiable.

**A reference reaches back, it never reaches one line up.** The sentence following a
displayed equation carries what follows from it — the consequence, the reading, the
next step — in its own words. Opening that sentence by naming the equation the reader
has just finished is redundancy, not a cross-reference. The same holds within a
paragraph: one pointer per equation is enough, and a second one in the same paragraph
says nothing the first did not.

## Ambiguity between the equation and the code

An equation can be written correctly and still admit two readings — an objective
summing over all classes when some are absent from a batch, a normalization whose
domain is not stated.

**Where a reading is ambiguous, the correct one is stated in the paragraph of the
component it belongs to**, as a clause, not as a separate paragraph. Which reading is
correct is a fact about the implementation, not about the mathematics: it is read off
what the code computes.

**What is a value or a procedure does not belong here** — batch size, learning rate,
schedule, hardware. Those are the experimental setup's.

**But every knob the method exposes is named here**, even when its value is set
elsewhere. The experimental setup may not introduce a parameter that does not exist
in this section.

**The same cut applies to a parameter choice.** If the choice changes the *form* of
the objective, it is stated here as a clause in the component's paragraph. If it is a
value chosen inside a fixed form, it belongs to the experimental setup.

## Citations

Citation density drops sharply here — roughly four to ten times lower than in the
introduction. That is not restraint: the introduction cites claims about the field,
and this section cites **objects**.

**The citation attaches to the object it credits, wherever that object sits in the
sentence.** This differs from the introduction, where the citation supports a claim
and therefore closes the sentence. When what is credited here is a claim rather than
an object, it closes the sentence too.

**A borrowed mathematical object arrives with its provenance attached to the sentence
that announces it, before the equation appears.** The reader sees whose definition it
is at the moment of reading it, not at the end of the paragraph.

Five things are cited:

1. the origin of a borrowed definition or estimator;
2. the origin of a named algorithm or component;
3. the provenance of the data — who publishes it and where it is available;
4. the justification that a variable matters, in the dataset subsection;
5. a property asserted about the method that others already established.

**Borrowed is cited, own is not.** No equation of the proposal carries a citation.

## Avoid re-motivating

The concrete redundancy risk in this section is motivation. The problem was stated in
the introduction and the gap was closed before this section. Here a contribution is
**defined**, not justified. One purpose clause per contribution is enough; a paragraph
explaining why the problem matters is repeated material.

## LIA house style

Measured on the group's ten Q1 method papers of 2025–2026 (SJR 2025), Elsevier first and MDPI after: items A008, A017, A018, A003, A006, A007, A009, A021, A022 and A026 of the lab's bank of articles. Ranges are minimum–median–maximum across the papers that have the section; a typeset line is about 12 words in a single-column layout. The ranges describe how the group writes; the extent at the top of this contract stays the target.

**Measured size.** 14–25–46 paragraphs; about 1010–2210–5900 words, the maximum an
outlier that generates its own dataset; 50–200 words per paragraph; 2–4–6
subsections; 5–21–35 displayed equations; 4–10–28 citations; 0–2–3 figures, usually
the architecture.

**Measured placement.** Seven of ten have no preamble. Six of ten own their dataset.
Each pillar the introduction names gets its own borrowed subsection, and the proposal
comes last, one subsection per contribution in half of them. The motivation is never
restated; the problem returns in one to three technical sentences, as the gap of a
borrowed piece just before the proposal.

**Shape.** The section is titled *Materials and Methods*. It opens on the dataset
when the section owns it, or on the problem setup and its notation; the borrowed
machinery follows, one subsection per pillar, and each component of the proposal then
gets its own subsection, named after it (*The proposed method's architecture*, *Loss
function*), with the general combination and, for a probabilistic model, the
predictive distribution last. Training and evaluation are the experimental setup's.

**Notation.**

- **Scalars are italic**: lowercase for values and indices (*x*, *n*, *t*),
  uppercase for counts and dimensions (*N*, *C*, *T*, *K*), each count paired with
  its lowercase index. Sums carry both limits, `\sum_{n=1}^{N}`.
- **Vectors are bold lowercase** (`\mathbf{x}`), **matrices bold uppercase**
  (`\mathbf{X}`), and **tensors bold uppercase too**, told apart from matrices by the
  shape they are declared with (`\mathbf{X} \in \mathbb{R}^{C \times T \times F}`).
  Greek vectors and matrices use `\boldsymbol{}`. The group's papers split between
  upright and italic bold; a paper picks one and never mixes them.
- **Every variable is declared at first use with its space**: *Let*
  `\mathbf{X} \in \mathbb{R}^{C \times T}` *denote …*. Number sets are blackboard
  (`\mathbb{R}`, `\mathbb{N}`), and so are expectation and divergence
  (`\mathbb{E}`, `\mathbb{D}_{\mathrm{KL}}`).
- **Calligraphic letters are for sets, spaces, distributions and losses**:
  `\mathcal{D}`, `\mathcal{X}`, `\mathcal{H}`, `\mathcal{N}(\mathbf{0}, \mathbf{I})`,
  `\mathcal{L}`. A loss term carries an upright subscript, `\mathcal{L}_{\mathrm{rec}}`.
- **Operators are upright**: `\operatorname{tr}`, `\operatorname{diag}`,
  `\operatorname{vec}`, `\operatorname{softmax}`, `\log`, `\exp`. Transpose is
  `^{\top}`, never a superscript *T*; Hadamard product `\odot`; Kronecker product
  `\otimes`; norms `\lVert \cdot \rVert_2`; inner product
  `\langle \cdot, \cdot \rangle`; an argument slot is `(\cdot)`; `\arg\min` and
  `\arg\max` take their variable underneath.
- **Parameters and accents**: learnable parameters are `\theta`, subscripted by the
  operator they belong to (`f_{\theta}`); hyperparameters are Greek letters declared
  with their domain (`\gamma \geq 0`). A hat marks an estimate or prediction
  (`\hat{y}`), a tilde a transformed or intermediate quantity
  (`\tilde{\mathbf{Z}}`), a bar a mean, a star an optimum (`\theta^{*}`).
- **An equation is part of a sentence.** The sentence before it ends in a colon or
  in *as*; the equation closes with a comma or a period; the sentence after it opens
  in lower case with *where* and defines every new symbol — one to five per clause,
  closed by *respectively* when they pair with a list.

**Writing.**

- **Sentences average 21–27 words.** Long enough to carry one claim and its qualifier, never a chain of three clauses.
- **One voice for the whole paper.** First person plural (*we propose*) or impersonal (*this work introduces*), chosen once; procedures that were run go in the passive past (*was evaluated using*).
- **Transitions come from the relation between claims, not from a list.** Name the relation first (contrast, cause, consequence, elaboration, example) and carry it with the sentence's own content: a clause (*yet*, *so*, *although*), a subject that points back (*that gap*, *this cost*), or no connector at all when the order of the sentences already says it. A stock connector (*However*, *Moreover*, *Notably*, *Specifically*, *In particular*, *Overall*, *Taken together*) is the exception: never the same one twice within five sentences, never most of a paragraph's openings, and a synthesis opener (*Overall*, *Taken together*) at most once per section.
- ***because* and *where* keep their jobs.** *because* states a cause the method or the data establish, at most once every few sentences and never stacked (*because …, and because …*); *where* opens the clause after an equation that defines its symbols, and nowhere else in prose (use *in which*, *when*, or two sentences). An evaluation is its own sentence, not a trailing *, which indicates …*.
- **The method has one name.** Expanded with its acronym at first use in each of the abstract and the body, then *the proposed* followed by the acronym.
- **Definitions are in the present tense.** *The encoder maps*, *the loss
  penalizes* — the method is described as it is, not as it was built.
- **A borrowed component is cited where it is named**, right after its name; the
  proposal's own equations carry no citation.
- **A figure is the subject of its sentence**: *Figure 2 illustrates the
  architecture*. It is never *Fig.*, and never a bare parenthesis.

## Inputs

Nothing here waits for an experiment. But it does wait for the code to exist.

### External inputs

| Input | Unblocks |
|---|---|
| The **mathematical formulation** of the proposal | `mm-borrowed-machinery`, `mm-proposal` |
| The **dataset** — when this section owns it | `mm-dataset` |

### Internal chain

| Block | Depends on |
|---|---|
| `materials-and-methods.mm-proposal` — stated as a delta on the borrowed machinery, with an explicit reference to the previous equation by number | `materials-and-methods.mm-borrowed-machinery` — the borrowed theory whose declared equations the proposal references |
| `materials-and-methods.mm-proposal` — always the last block of the section, without exception | `materials-and-methods.mm-dataset` — the dataset subsection, when this section owns it |
| `materials-and-methods.mm-preamble` — it names the subsections that follow and their order | `materials-and-methods.mm-proposal` — the last of the subsections it must name, so the preamble is written once every subsection it announces exists |

### Structural decisions

- **The correct reading of an ambiguous equation** is decided by the
  implementation — what the code computes, not what the equation says. This
  is a decision recorded in the affected component's own paragraph, not a
  dependency on any other block.

## Disqualifiers

- A real dataset whose explanation does not close on its acquisition-protocol diagram,
  or whose diagram is boxes alone, with no domain pictogram.
- A symbol used without being declared, or declared twice with different meanings.
- Two distinct quantities sharing a letter with no diacritic separating them, or a
  diacritic that marks no relation to an already-declared object.
- A symbol in the general combination that traces to no prior declaration.
- The proposal not being the last block of the section, or its subsections not
  consecutive.
- A borrowed subsection for a pillar the introduction never named, or a named pillar
  with no subsection.
- The machinery handing over to the proposal without stating the gap of the piece the
  proposal modifies.
- More than two sentences of problem restatement before a contribution, or any
  sentence of the application's motivation.
- An interpretability contribution named in the introduction whose mechanism is not
  defined here.
- An evaluation protocol, metric, baseline, split, or statistical test described here,
  or presented as a contribution.
- A contribution defined here that the introduction did not name, or named there and
  not defined here.
- Contributions in a different order than the introduction named them.
- The summary diagram missing.
- The contribution list readable in neither form — neither one subsection per
  contribution nor an ordered roster immediately before the closing pointer — or a
  roster written when the contributions are already subsections.
- A dataset or a baseline appearing in the summary diagram.
- A contribution defined under a different name than the property it delivers carries
  in the problem statement and the introduction.
- A parameter used by the experimental setup that is named nowhere here.
- An artefact that appears before any reference to it, or that nothing references at
  all.
- A pointer to a whole artefact when the value is in one of its parts.
- A diagram whose components differ in number, order, or naming from the contribution
  list.
- A caption that does not decode what the figure encodes.
- Borrowed theory developed past the depth the proposal uses.
- An equation displayed and numbered that no sentence ever references, defines no
  contribution, and is not the general combination.
- A mathematical subsection opening on an equation instead of on notation.
- An equation referenced by number in the sentence immediately following its own
  display, or referenced twice by number within one paragraph.
- An ambiguous equation left with both readings open.
- A batch size, learning rate, schedule, or hardware detail stated here.
- A convergence argument moved to the experimental setup.
- A citation on an equation of the proposal.
- A borrowed definition whose announcing sentence carries no citation.
- A dataset described here and left unreferenced.
- A paragraph re-motivating the problem.
- A result, a measured number, or a comparison.
- A vector, matrix or tensor typeset without bold, or two bold styles mixed in the section.
- A variable used before its space and dimensions are declared.
- A displayed equation without a number, or one referred to as *Eq.* instead of *Equation (n)*.
- A transpose written as a superscript *T* instead of `^{\top}`.
