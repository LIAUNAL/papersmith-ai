# Materials and Methods

> **Notice.** This guide is a modified derivative of `sections/01-materials-and-methods.md` from papersmith-ai (https://github.com/Daprosero/papersmith-ai, commit `1f09516`), licensed under the Apache License, Version 2.0. A copy of the license is provided as `LICENSE-papersmith-ai.txt` in this folder. Caztor removed the parts that belong to the source project's own tooling, reworded a few sentences, added the notes below, and appended the section "Shared conventions".
>
> **Advisory.** This guide is advice, not a set of rules. The user's request, the document's own structure and the venue template take precedence over it; use the guide for the advice that remains. It describes a research article. The word counts, paragraph counts and other extents are typical ranges for a research article, not limits. For theses, reports and reviews, map the functions the guide describes onto that document's own sections and do not copy its headings or ranges. The list of disqualifiers names common weaknesses to check a draft against. The guide never licenses stating anything the user has not provided: facts, numbers, results and references come from the user's own files.

**Extent** 560–3950 words · 2 to 5 subsections
**Carries** the borrowed machinery, the proposal, and one summary diagram
**Does not carry** any result, measured number, or comparison

This section defines the contributions. It names each one here and gives it its
formal definition, in the notation everything downstream reuses; the introduction
receives that list and drafts from it.

## Nothing is decided here

The proposal already exists. This section does not choose it, improve it, or argue
for it — it carries an existing formulation into this structure. Where the section
looks like it is deciding something, it is reporting a decision taken elsewhere.

## Preamble

One paragraph of about 40 words, two sentences, no citations. It names the
subsections that follow and their order. Nothing else.

## Subsection order

Three slots. The third is invariant.

| Slot | Subsections | Words each |
|---|---|---|
| 1 — The dataset, when this section owns it | 1 | 550–1000 |
| 2 — The borrowed machinery | 1 to 3 | 180–1480 |
| 3 — **The proposal** | 1 | 380–1420 |

**The dataset placement is a structural decision, and it is taken once.** If the
dataset belongs to this section it goes first, and the section opens on the data. If
it belongs to the experimental setup instead, this section starts directly on the
machinery and stays purely formal — carrying no figure other than the proposal's
diagram. The decision changes the requirements of both sections, so it is recorded rather
than improvised.

**The proposal is always the last subsection.** Without exception.

## Slot 1 — The dataset

6 to 12 paragraphs. One or two figures — acquisition protocol, or representative
samples. Zero to two tables — variable lists. Few or no equations.

Open according to whose data it is:

- **Own or constructed data:** provenance and time span in the first sentence, then
  the objective that justifies those variables.
- **Public data:** why *these* sets answer the question, and what makes them differ
  from one another.

**State what was discarded before stating what was kept** — exclusions, quality
filters, removed records.

**This is where the credit debt from the introduction is paid.** A dataset named in
the introduction without a reference is named here with one.

## Slot 2 — The borrowed machinery

One to three subsections, each a body of existing theory the proposal needs. This is
where the bulk of the paper's mathematics lives.

**Ordered so that each subsection uses only symbols the previous ones declared.** It
is a chain of notation, not a list of topics.

**Each subsection opens by declaring notation, before any equation.** No mathematical
subsection opens on an equation. Use set-builder notation with an explicit index
domain for a collection.

**Developed only to the depth the proposal uses it.** More than that is related work
leaking in.

## Slot 3 — The proposal

Always last. The least cited subsection of the paper.

**1. Opening: name the method and state its setting.** Where possible, state the
proposal as a delta on the borrowed machinery, with an explicit reference to the
previous equation by number — so the reader knows exactly what changed relative to
what was just read.

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

Either way, what is read back against the diagram is
that ordered list of names — whichever of the two carries it.

**5. The closing: pointer and summary diagram.** Mandatory. The last prose sentence
points to the figure by number and says what it summarizes; the figure follows
immediately.

**Optional, and only where there is something to say:** a clause on convergence or
stability, distinguishing the consistency of the estimator from the empirical
convergence of training. It belongs here and not in the experimental setup — that
section is past-tense procedure, and a convergence argument is a present-tense claim
about the formulation.

### The summary diagram

- **It is the visual form of the contribution list**: it contains exactly the same
  components, in the same order, under the same names this section's own roster
  gives them.
- **The caption enumerates them in that order** and decodes anything the figure
  encodes — if there are colours, the caption says what each one means.
- **It shows the method, not the experiment.** No dataset and no baseline appears in
  it; those belong to the experimental setup's own diagram. A box appearing in both
  means one of the two is wrong.
- **The diagram is read back against this same section's own roster.** Nothing outside this section is consulted.

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

Every word count in this guide measures the prose. A displayed equation, its
label and its number are not prose and count toward no extent here.

**A formulation whose mathematics is long is not thereby a formulation that must be
cut.** The mathematics transfers as it stands; what the extent constrains is what is
written around it — the notation that declares its symbols, the sentence that
announces each expression, and the reading that follows it. When a subsection runs
past its extent, the prose is what tightens, never the derivation.

A section that drops steps of its own source's mathematics to fit a word budget has
misread the budget. Nothing in this guide licenses that.

## Equations: display and number are two separate decisions

**Display by readability.** An expression that cannot be read inline — multi-line,
carrying constraints, summing over indices — is displayed. What reads in a running
line stays in the text.

**Number by reference.** Number it if it will be referenced by number later, if it
defines a contribution, or if it is the general combination. A displayed equation
nobody will name again is displayed without a number.

Numbering by reflex is the common failure: it produces long runs of numbered
expressions that no sentence in the paper ever mentions.

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

## Drafting order

Nothing here waits for an experiment, but it does wait for the implementation to exist, because this section describes what the code computes.

## Disqualifiers

- A symbol used without being declared, or declared twice with different meanings.
- Two distinct quantities sharing a letter with no diacritic separating them, or a
  diacritic that marks no relation to an already-declared object.
- A symbol in the general combination that traces to no prior declaration.
- The proposal not being the last subsection.
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

## Shared conventions

This section is Caztor's own summary of rules that recur across the guides. It is not part of the source text; each rule names the guides it summarizes.

- Place a citation at the end of the sentence it supports: one sentence, one attributed claim, and a sentence that would need two citations is two sentences. (Summarizes the guides 05-related-work and 06-introduction.)
- Never use a citation as a noun phrase ("the work in [N] does X"): write about families of work and ideas, and let the citation close the sentence. (Summarizes the guides 05-related-work and 06-introduction.)
- Cite what is borrowed and do not cite what is the document's own. A citation that credits an object (a definition, an estimator, a dataset, an instrument) attaches to that object. (Summarizes the guides 01-materials-and-methods and 02-experimental-setup.)
- Expand every acronym at its first appearance, including the name of the document's own method, and use the acronym alone afterwards. (Summarizes the guides 06-introduction and 08-abstract.)
- State the count before enumerating components or contributions, and keep the same count, order and names wherever the list is repeated. (Summarizes the guides 06-introduction, 07-conclusions and 08-abstract.)
- Give each property, problem and component the same name everywhere it appears, not a synonym. (Summarizes the guides 03-results-and-discussion and 06-introduction.)
- Refer to every figure and table in the text before it appears, and point at the exact part of it that holds the value. (Summarizes the guides 01-materials-and-methods, 02-experimental-setup, 03-results-and-discussion and 05-related-work.)
- In summarizing parts (the abstract and the conclusions) add no claim, number or property that the body does not establish, and quote a figure only when it matches the results exactly. (Summarizes the guides 07-conclusions and 08-abstract.)
- Never state a fact, number, result or reference the user has not provided. Ask for it, or leave a visible placeholder. (Caztor's own rule.)
