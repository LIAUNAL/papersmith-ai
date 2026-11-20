# Related Work

> **Notice.** This guide is a modified derivative of `sections/05-related-work.md` from papersmith-ai (https://github.com/Daprosero/papersmith-ai, commit `1f09516`), licensed under the Apache License, Version 2.0. A copy of the license is provided as `LICENSE-papersmith-ai.txt` in this folder. Caztor removed the parts that belong to the source project's own tooling, reworded a few sentences, added the notes below, and appended the section "Shared conventions".
>
> **Advisory.** This guide is advice, not a set of rules. The user's request, the document's own structure and the venue template take precedence over it; use the guide for the advice that remains. It describes a research article. The word counts, paragraph counts and other extents are typical ranges for a research article, not limits. For theses, reports and reviews, map the functions the guide describes onto that document's own sections and do not copy its headings or ranges. The list of disqualifiers names common weaknesses to check a draft against. The guide never licenses stating anything the user has not provided: facts, numbers, results and references come from the user's own files.

**Extent** 820–1700 words
**Does not carry** equations
**Carries** one block per stated problem, and one synthesis figure or table

Every claim here belongs to someone else's work, and the section argues what those works together leave unsolved.

## Whether the section exists

This is one decision with two criteria, and either one is enough to create the
section:

- **Does the lineage need more than one paragraph per problem?** If every problem is
  discharged in a single paragraph, the material stays compressed in the
  introduction.
- **Is the comparison table wanted?** The synthesis artefact lives here and nowhere
  else.

**If the section does not exist:** there is no panorama paragraph, there is no
synthesis artefact anywhere in the paper, and the introduction's state-of-the-art
block expands to one paragraph per stated problem. The table does not move to another
section — it is lost together with the section.

The decision governs two places at once, so it is taken before drafting either.

## Global structural rule

Five blocks. The third repeats — once per stated problem.

1. preamble
2. general panorama of the problem
3. one block per specific problem
4. closing: open fronts and the gap
5. synthesis artefact

**The organizing principle is one unit per stated problem**, the same principle that
governs the introduction's state-of-the-art block. What differs is what the unit is
made of: a paragraph in the introduction, a block of paragraphs here.

**The cut between the two places:** the introduction retains, per problem, the family
whose limitation motivates the contribution. Everything else that attacked that same
problem is a variant, and it lives here.

## Block 1 — Preamble

One paragraph of about 40 words, two sentences, **no citations**. It names the blocks
that follow and their order. Nothing else.

It is the only paragraph in the section that does not close on a limitation, because
it characterizes no family.

## Block 2 — General panorama of the problem

One paragraph, about 150 words. Take the **general problem** — the one that names the
paradigm, not the difficulties — and state the whole trajectory the literature
travelled: where the field came from and where it moved.

It is panorama, not review: develop no family and attribute no particular limitation.
Its job is to let the blocks that follow start directly on their problem.

## Block 3 — One block per specific problem

As many blocks as the problem statement declares specific problems. Two or three.
Each block is made of:

- **one paragraph carrying the main lineage** — the same family the introduction
  retained, here with its full progression;
- **one or two further paragraphs** carrying the variants, the alternative
  strategies, and the partial attempts that attacked the same problem and that the
  introduction left out.

Every paragraph closes on the limitation of its family. Every block closes on what
none of its families resolved.

**Each block opens by naming its problem and stating its own trajectory** before
walking it, and **starts from the close of the previous block**: the deficiency the
previous problem ended on is what motivates the next. The blocks are a chain, not
parallel islands.

Paragraph size: 130–300 words. Nothing in this section runs longer than 300 words.

**The blocks weigh about the same.** A block of 700 words against one of 220 says the
second problem was mentioned rather than reviewed.

### Two ways to walk a block, chosen by the nature of the problem

**Chronological** — when the problem is *how has this task been solved*. A task has a
history.

1. the founding family, with what it provides and its structural limitation;
2. intermediate families, one paragraph each, each starting from the previous
   limitation;
3. the most recent family, which is either the one the proposal **adopts** — and the
   paragraph closes by saying why it is suitable — or the one it **displaces**, and
   the paragraph closes on a limitation.

**Taxonomic** — when the problem is *how has this property been achieved*. A property
has no history; it has types.

1. state the whole taxonomy in a short paragraph that develops none of it;
2. declare which branch is the relevant one and why;
3. walk that branch, family by family, each paragraph on its limitation.

Because the unit here is a block and not a paragraph, a discarded branch can take a
paragraph of its own instead of a single sentence. That is what the extra room in
this section is for.

## Block 4 — Closing: open fronts and the gap

One paragraph, 100–125 words, 3 to 5 sentences.

1. **A recapitulation formula.**
2. **Name the fronts left open — as many as there are blocks.** Two blocks, two
   fronts.
3. **State which of them the proposal attacks**, closing on the proposal by name.

**The gap is not always methodological.** A work may be limited by its mechanism, but
also by the **task** it solves or by the **data** it uses: close in method and remote
in scope. When the gap is one of scope rather than mechanism, say so explicitly — a
reader who knows that work will otherwise wonder why it did not already suffice.

## Block 5 — Synthesis artefact

An evolution figure or a comparison table.

**Its dimensions are the properties on which the proposal wins** — they are derived
from the contributions, not from whatever is easy to tabulate. The proposal's row is
the only one holding every column.

It goes after the closing, preceded by **a one-sentence pointer paragraph that names
the dimensions in the body** before the table appears. The variant is one artefact
per block of block 3, placed at that block's close; in that case the pointer is the
block's last sentence.

Name the dimensions in the body, never only in the table header.

## Every artefact is referenced before it appears

The synthesis artefact — and any other figure or table this section carries — is
referenced in the body **before** it appears, with the pointer resolving to the exact
sub-element when it has parts. An artefact appearing with no prior reference is either
misplaced or dead.

## Thematic, not catalogue

The paragraph is about **families**, not about individual works. The subject of the
sentences is the family or the capability.

**Reliable marker of cataloguing: the citation used as a noun phrase** — *the work in
[N] uses*, *the method of [N] combines*. If it appears, the section is cataloguing.

**Soft signal: fewer than twenty words per sentence.** A thematic paragraph runs 24 to
27; a catalogue drops to 13–18 because it packs one short sentence per work. This is
an indication, not proof — the ranges touch at the edge.

The underlying reason: **a catalogue cannot close on a gap, because it never produced
one.** If the paragraph enumerates works instead of characterizing families, nothing
is left to synthesize.

## Citations

- **At the end of the sentence it supports.** One sentence, one attributed claim. A
  sentence that would need two citations is two sentences. Collapse ranges.
- **Never as a noun phrase.**
- **Two to six per paragraph.** That is the actionable number; the total of distinct
  references is the consequence, not the target.
- **Every limitation attributed to prior work carries a citation**, preferably one
  from that literature rather than from the authors themselves.
- This section is not necessarily more cited than the introduction. What changes is
  the depth per family.

## Drafting order

**Nothing here depends on a measurement.** The section is written in full before a
single experiment runs. Every block traces back to the problem statement, which comes
from the contributions, which come from the mathematical formulation — the root of
this section is the formulation.

## Disqualifiers

- A block that corresponds to no stated problem.
- A stated problem with no block.
- A preamble that reviews a family, or that carries a citation.
- A panorama that attributes a limitation to a particular family.
- A paragraph that does not close on a limitation.
- A block that does not close on what none of its families resolved.
- A block that does not start from the close of the previous one.
- A limitation attributed without a citation.
- A paragraph over 300 words.
- Blocks of grossly unequal weight.
- The closing paragraph missing.
- Fronts named in the closing that do not match the number of blocks.
- The synthesis artefact missing.
- An artefact whose dimensions are not the properties the proposal declares.
- Dimensions named only in the table header and not in the body.
- An artefact that appears before any reference to it, or that nothing references at
  all.
- A citation used as a noun phrase.
- A citation anywhere but at the end of the sentence it supports.
- An equation.
- A family developed both here and across the introduction's state-of-the-art block:
  when this section exists, that block is a summary.
- A variant named in the introduction: variants belong here.
- The gap of this section and the gap of the introduction disagreeing.

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
