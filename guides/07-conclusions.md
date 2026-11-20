# Conclusions

> **Notice.** This guide is a modified derivative of `sections/07-conclusions.md` from papersmith-ai (https://github.com/Daprosero/papersmith-ai, commit `1f09516`), licensed under the Apache License, Version 2.0. A copy of the license is provided as `LICENSE-papersmith-ai.txt` in this folder. Caztor removed the parts that belong to the source project's own tooling, reworded a few sentences, added the notes below, and appended the section "Shared conventions".
>
> **Advisory.** This guide is advice, not a set of rules. The user's request, the document's own structure and the venue template take precedence over it; use the guide for the advice that remains. It describes a research article. The word counts, paragraph counts and other extents are typical ranges for a research article, not limits. For theses, reports and reviews, map the functions the guide describes onto that document's own sections and do not copy its headings or ranges. The list of disqualifiers names common weaknesses to check a draft against. The guide never licenses stating anything the user has not provided: facts, numbers, results and references come from the user's own files.

**Extent** 375–500 words · 3 or 4 paragraphs
**Does not carry** equations, figures, or tables
**Carries** citations in one place only: the future-work block

The conclusions are read by people who will not read the paper. They must stand
alone. They add nothing — every claim here already exists earlier, in more detail.

## Four functional blocks

| Block | Paragraphs | Words |
|---|---|---|
| 1 — The proposal and its components | 1, always the first | 60–226 |
| 2 — The results recap | 1 or 2 | 100–180 each |
| 3 — The consequence beyond the method | own paragraph, or the close of block 2 | ~50–120 |
| 4 — Future work | 1, always last | 55–180 |

Blocks 2 and 3 may share a paragraph; blocks 1 and 4 never merge with anything.

## Block 1 — The proposal and its components

Past tense. Full name, acronym, and the category of the artefact. Then the N
components restated, in one of three forms:

- **`First / Second / Third`** as separate sentences, after announcing the count;
- **an inline list** inside a single sentence — the most compact form;
- **prose with connectives** — *integrating A … the incorporation of B allows … 
  furthermore C*.

**Same count, same order, same names** as the introduction's contribution list and
the methods section's subsections.

**Close on what distinguishes the method from its alternatives** — the property, not
the number. What it does not require, what it does not need modified, what it does
not depend on.

## Block 2 — The results recap

Named competitors, named axes, and the specific finding with the conditions under
which it held.

**One or two paragraphs, and the number of experimental scenarios decides.** Two
dissimilar scenarios take one paragraph each. A single scenario may still split into
result and mechanism — what the numbers were, and what the pattern was consistent
with.

**Figures are permitted, with dispersion, but they are not the norm.** Quote a value
only when the value is the point; otherwise stay in comparatives. A quoted figure
must match the results section exactly.

## Block 3 — The consequence beyond the method

What the reader takes away, past the fact that the method worked. Not a result and
not a contribution — a consequence. It answers *so what*.

Two flavours; the paper picks by whose problem it is:

- **For whoever implements it** — the cost of adoption is low: nothing needs
  modifying, the architecture drops into existing pipelines, prediction time falls.
- **For whoever lives the problem** — something becomes possible that was not: the
  factor behind a prediction can be traced back, the decision path is auditable where
  regulation demands it.

It may be its own paragraph or the closing sentences of block 2. It is the only part
of the section that speaks to someone outside the sub-field.

## Block 4 — Future work

Always last. **The only block in the section that cites** — one reference per
direction, showing the direction is live in the literature. Everything before it
cites nothing.

**Future work is the relevant subset of the limitations, with a reference per
direction.** Each direction answers a stated limitation.

**The reduction goes one way only.** A limitation may be left without a direction —
not everything is meant to be repaired. But no direction is left without a limitation
motivating it: **a direction with no corresponding limitation means the limitation
was never declared**, not that the direction is unnecessary. Fix it by declaring the
limitation, not by dropping the direction.

That is what makes the coupling between the two sections checkable.

Each direction is specific enough to be a paper — an extension named, not a hope.
The block closes on the applicability those directions would widen.

## Optional

**A scope caveat.** When the results could be read as a finding about the domain
rather than about the model, say which one they are. This carries the same
attribution discipline as a quoted figure: state what the claim belongs to.

## Drafting order

Everything except the abstract must exist. The abstract is written after this
section, because it compresses it.

## Disqualifiers

- A claim, number, or property that appears nowhere earlier in the paper.
- A component list disagreeing with the introduction or the methods section in count,
  order, or naming.
- Block 1 not first, or block 4 not last.
- Block 1 closing on a number instead of on the distinguishing property.
- A quoted figure that does not match the results section exactly.
- A future-work direction that answers no stated limitation.
- A citation anywhere outside the future-work block.
- A future-work direction with no reference.
- A future-work direction too vague to be a paper.
- An equation, a figure, or a table.
- Limitations developed here instead of in the results section.
- Over 500 or under 375 words.
- A section that cannot be read without having read the paper.

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
