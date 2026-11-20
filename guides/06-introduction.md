# Introduction

> **Notice.** This guide is a modified derivative of `sections/06-introduction.md` from papersmith-ai (https://github.com/Daprosero/papersmith-ai, commit `1f09516`), licensed under the Apache License, Version 2.0. A copy of the license is provided as `LICENSE-papersmith-ai.txt` in this folder. Caztor removed the parts that belong to the source project's own tooling, reworded a few sentences, added the notes below, and appended the section "Shared conventions".
>
> **Advisory.** This guide is advice, not a set of rules. The user's request, the document's own structure and the venue template take precedence over it; use the guide for the advice that remains. It describes a research article. The word counts, paragraph counts and other extents are typical ranges for a research article, not limits. For theses, reports and reviews, map the functions the guide describes onto that document's own sections and do not copy its headings or ranges. The list of disqualifiers names common weaknesses to check a draft against. The guide never licenses stating anything the user has not provided: facts, numbers, results and references come from the user's own files.

**Extent** 900–1650 words · 7–13 paragraphs
**Does not carry** equations, figures, or tables
**Carries** 18–41 distinct references, concentrated in blocks 1 to 3

## Global structural rule

Six **argumentative functions**, in fixed order, distributed across 7–13 paragraphs.
Function and paragraph are not the same unit: blocks 2 and 3 expand.

1. why the topic matters
2. which concrete problems must be solved
3. existing solutions solve them only in part
4. a proposal whose contributions answer those problems
5. how each promised property is validated
6. how the rest of the article is organized

**Intended correspondence:** `problem i → state-of-the-art limitation i →
contribution i → property i → instrument i → evidence i`. The chain starts at the
problem, not at the contribution: a contribution delivering a property that no
declared problem needed has nothing motivating it.

**The property carries the same name through every link** — not a synonym, the same
words. If the problem is named one way in block 2, the contribution delivers that,
block 5 names the instrument for that, and the results block is about that. Without
the shared name the chain is interpretable rather than checkable.

The requirement is the strong half: no stated problem is left without an answer, and
no declared property is left without an identifiable form of evaluation. A problem
may be answered by **a component of the proposal or by an analysis in the
evaluation** — not necessarily by a component. The one-to-one correspondence is a
preference, not a requirement.

## Drafting order

These blocks are not written in reading order. Each block is drafted as
soon as its input exists. **Two blocks admit a partial form**: they are written from
the design and completed from the measurement.

### What is writable before measuring

With the proposal formulated and the dataset chosen, before a single experiment has
run, blocks **1, 2, 3, 4a, 4b in partial form, and 6** are all draftable. With the
experimental design settled, **5 in partial form** is added.

The results contribute only the closing of two blocks that are already written: the
achieved effect of each contribution, and the evidence sentence. The introduction is
built in full before measuring; measuring completes it, it does not originate it.

### The loop that must be closed by hand

**The results rule.** They can contradict the effect a contribution promised, and
when they do, the text is corrected to match them — never the reverse.

The correction does not stop at 4b. Block 2 was derived from that contribution, and
block 3 from block 2. On completing 4b, walk the chain backwards and verify that
every stated problem still has an answer and that no contribution is left without a
problem motivating it. This is the only point in the section where measurement can
invalidate what is already written.

In practice most of the chain survives, which is why the chain is worth following
rather than waiting: a contradicted effect usually revises one item and one clause,
not the argument.

## Block 1 — Contextualization

**Function.** Introduce the application domain and the phenomenon motivating the
work, its relevance, and the general need that justifies studying it.

**Sequence.** domain → phenomenon of interest → relevance → general need.

**Extent.** One paragraph, 145–200 words. A second is admitted only under the
condition below. Never three.

**The phenomenon is fixed by the data, not by the method.** Anchor the context in the
condition, population, or process that the dataset actually contains. Changing the
dataset rewrites this paragraph entirely even when the method is identical: state
domain, phenomenon, and relevance over what was measured, not over the family of
techniques employed. A context written about the method leaves the reader without
knowing what the work is about.

**Do not name the dataset here.** What anchors the context is the condition,
population, or process, not the dataset's name — the name belongs to block 5.

**When it splits in two.** The paragraph must traverse all four dimensions and close
by leading into the technical problem. Split it only when the move from broad domain
to specific scenario requires an explicit change of scale — from the general field to
the concrete population, institution, or territory of the study — and forcing it into
one paragraph produces an artificial transition sentence. Outside that case, one.

**Does not belong here.** The proposal, its name, its components, its contributions,
or any experimental detail.

## Block 2 — Problem statement

**Function.** Turn the general need into a concrete technical problem, and decompose
it into the specific problems the proposal resolves.

**Sequence.** general problem → specific 1 → specific 2 → [specific 3] →
requirements an adequate solution should satisfy.

**Extent.** 1–3 paragraphs, 130–365 words.

**Nest the problems: a general one naming the paradigm, and the specific ones inside
it.** The general problem is the name of the field or the task, not a difficulty; the
specific ones are the difficulties. State the general one first, acknowledging that
it is only partially resolved, and open the enumeration only after that.

**Name the problems with the accepted terminology of the state of the art.** This is
not cosmetic: the name of each problem is the search key with which block 3 will find
its literature. A problem described in private vocabulary instead of the field's has
no methodological family addressing it, and block 3 is left with nothing to chain.

**Each specific problem corresponds to a capability the proposal incorporates** —
which is why this block is derived from the contributions, read backwards. Introduce
no difficulty that the work will not address.

**Close by consolidating the requirements** an adequate solution should satisfy. That
closing is what enables the gap in block 3, and its terms are the axes the evaluation
will measure: state them in the same words block 5 will later use.

**Count.** Two or three specific problems.

## Block 3 — State of the art and gap

**Function.** Present the families of methods that have addressed the problems of
block 2, organized **around those problems and not as an enumeration of works or
authors**.

**Per family:** which problem it addresses → what advantage it provides → what
limitation it retains.
**Overall:** existing solutions → advances → limitations → joint gap.

**The extent depends on whether the article has its own Related Work section.** That
is a decision about the structure of the manuscript, and it is taken before drafting
the block.

**The organizing principle is the same either way: one unit per stated problem.** What
differs is what the unit is made of — a paragraph here, a block of paragraphs in the
dedicated section.

**With a Related Work section — a single paragraph, 230–380 words.** This paragraph is
the summary of that section. Per problem, one or two sentences: the family whose
limitation motivates the contribution, and that limitation. Variants and alternative
strategies are not named here — they live in the section. The paragraph closes on the
joint gap.

**When a Related Work section exists, this block is written after it.** It summarizes
the section, and a summary cannot precede what it summarizes. Without that section,
the block depends only on the problem statement.

**The cut between the two places:** this block retains, per problem, the family whose
limitation motivates the contribution. Everything else that attacked that same
problem is a variant, and it belongs to the dedicated section.

**Without a Related Work section — one paragraph per stated problem, 130–300 words
each, 550–990 words in total.** Each problem receives its own paragraph, which walks
the families that have attacked it in progression and ends in what none of them
resolved. Expand each method's nomenclature on first appearance. Organizing by
problem rather than chronologically is what makes the correspondence with block 2
explicit.

**Two clarifications, so that nothing is added here by analogy with the dedicated
section.** No panorama paragraph is added to the introduction: blocks 1 and 2 already
do that work, and duplicating it is noise. And the chronological and taxonomic ways
of walking a problem do not apply where the unit is a paragraph — here there is one
family and its limitation, with no taxonomy to lay out.

**The progression chains.** Each paragraph, and each family within a paragraph,
starts from the limitation of the previous one, and that chaining is explicit in the
opening sentence: the new family appears *because* the previous one failed at
something named. A chronological enumeration that does not chain limitations is not a
state of the art — it is a list.

**The closing is the joint gap, and the conjunction is what makes it a gap.** It is
not enough to say that each family has limitations: establish that existing solutions
resolve the problems **separately and not simultaneously**, and therefore do not
jointly satisfy the requirements stated at the end of block 2. The word expressing
that simultaneity must be present.

**When a Related Work section exists, this gap and that section's closing gap say the
same thing at different depths.** They are one claim stated twice, and they must
agree.

**Ordering exception.** The block may be split, advancing one half before block 2,
when the problem cannot be stated without first presenting the enabling technology.
In that case the order is: enabler → problem → families.

## Block 4 — Proposal and contributions

**Function.** Present the method by name and purpose, the core idea articulating its
components, and enumerate the contributions.

**Sequence.** presentation → overall objective → core idea → contribution 1 → 2 → …

**Extent. Two physical paragraphs, 120–180 words in total.**

### Paragraph 4a — the prose. Three movements, two or three sentences.

1. **Presentation and objective.** Full name, acronym in parentheses, the category of
   the artefact, and a purpose clause **mirroring the specific problems of block 2 in
   the same order**. The verb is first-person plural and appears **exactly once in the
   whole introduction**: everything before it is other people's work.
2. **The core idea.** One sentence, one mechanism, without mathematics and without
   symbols. It is what makes the proposal new, not what it does.
3. **The announcement.** Close the paragraph by stating the number of components and
   ending in a colon, which is what opens the list. Announce the count before
   enumerating it, always.

### Paragraph 4b — the list.

**The number of items is the number of contributions the proposal has.** It is
inherited, never a drafting target. What drafting requires is only that the count be
announced in 4a before being enumerated here, and that the list agree in count,
order, and naming with the components of the methods section.

Open each item with **the name of the component followed by a colon**, and continue
with a single sentence stating what it does and which previously stated problem it
resolves. Those names are the ones the methods section defines — this list uses the
same ones, in the same order.

Do not open items with a first-person verb instead of a component name: without a
name, the component cannot be referred to again later.

**The achieved-effect clause is the part that waits for the results.** What each
contribution introduces and what function it performs come from the formulation; the
effect it is claimed to achieve comes from the measurement.

**No citations.** From here to the end of the introduction, cite nothing.

## Block 5 — Evaluation of the proposal

**Function.** Summarize how the proposal is validated, in direct correspondence with
the stated contributions.

**Sequence.** evaluation scenario → data or tasks → comparison methods → criteria or
metrics → complementary analyses → general evidence.

**Extent.** One paragraph, 65–135 words.

**Name everything by its proper name:** the datasets, the methods compared against,
and the axes over which the comparison is swept. Name the complementary analyses too,
because they are what answer the properties no contribution covers — typically the
ones that are not about performance.

**Naming a dataset here does not credit it.** No citation appears in this block. An
external dataset carries a credit obligation, and it is discharged where the dataset
is described — in the datasets subsection — with its reference there. Naming it here
without a reference is correct; leaving it unreferenced where it is described is not.

**Every property declared in block 4 must have its identifiable form of evaluation
here.** Performance, robustness, interpretability, stability, efficiency, coherence,
generalization: if it was promised, it is evaluated, and this is where the instrument
is named — **under the same name the problem and the contribution gave it**.

**The first five movements come from the experimental design; only the closing comes
from the results.** Scenario, data, comparisons, criteria, and complementary analyses
are all decidable before anything runs.

**Close in evidence, not in values.** State the direction of the result and the axes
on which it improves, without quoting any figure, percentage, or table. Numbers
belong to the results section.

## Block 6 — Organization of the article

**Function.** Orient the reader about the structure. Nothing more.

**Extent.** One paragraph, 32–42 words.

It is a fixed formula:

`The remainder of this paper is organized as follows: Section [N] [verb] the [content]. … Finally, Section [N] [verb] the concluding remarks.`

- One clause per section, in order.
- Each section appears in exactly one clause. Adjacent sections with a related
  function may share one.
- The verb varies by section (`introduces`, `presents`, `describes`, `reviews`,
  `details`, `discusses`).
- The final clause opens with `Finally,` or `Lastly,`.

**Introduce no new argument, problem, contribution, method, or result.**

## Cross-cutting conventions

- **Place the citation at the end of the sentence it supports.** One sentence, one
  attributed claim. A sentence that would need two citations is two sentences.
  Collapse ranges.
- **Do not use the citation as a noun phrase** — *the work in [N] does X*, *the
  method of [N] combines*. It turns the argument into a catalogue of individual works
  instead of an account of families.
- **Density:** one citation every one or two sentences in blocks 1 to 3; **no
  citations from block 4 onward**.
- **Every assertion about the field carries a citation.** Assertions about the
  proposal itself carry none.
- **Expand acronyms on first appearance**, the acronym alone thereafter — including
  the proposal's own.
- **State the count before enumerating**, in any block that enumerates.
- **No equations, figures, or tables anywhere in the section.**

## Disqualifiers

- An equation, a figure, or a table.
- A context written about the family of methods instead of the phenomenon the dataset
  contains.
- The dataset named in block 1.
- A dataset named in block 5 and left unreferenced where it is described.
- Three paragraphs of contextualization.
- A specific problem answered by neither a component of the proposal nor an analysis
  in the evaluation.
- A problem named in private vocabulary instead of the accepted terminology of the
  field.
- Block 2 without its closing statement of requirements.
- A paragraph of block 3 that does not end in a limitation.
- Block 3 without a joint-gap closing, or with a gap stated as a sum of separate
  limitations.
- This block's gap and the Related Work section's closing gap disagreeing.
- Block 3 over roughly 400 words when a Related Work section exists, or under roughly
  500 when it does not.
- A variant or alternative strategy named in block 3 when a Related Work section
  exists: those belong to that section.
- Block 3 written as a summary of a Related Work section that does not yet exist.
- A panorama paragraph added to the introduction.
- The count announced in 4a not matching the number of items in 4b.
- The list in 4b differing in count, order, or naming from the components of the
  methods section.
- A contribution motivated by no problem in block 2.
- A property declared in block 4 with no evaluation named in block 5.
- A property named differently in blocks 2, 4 and 5 — a synonym instead of the same
  words.
- A figure, percentage, or value in block 5.
- A citation anywhere from block 4 onward.
- A citation placed anywhere but at the end of the sentence it supports.
- A citation used as a noun phrase.
- Block 6 missing, or naming sections that do not exist, or repeating one.
- A completed 4b whose achieved effects were not checked back against block 2 and,
  through it, block 3.

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
