# Abstract

> **Notice.** This guide is a modified derivative of `sections/08-abstract.md` from papersmith-ai (https://github.com/Daprosero/papersmith-ai, commit `1f09516`), licensed under the Apache License, Version 2.0. A copy of the license is provided as `LICENSE-papersmith-ai.txt` in this folder. Caztor removed the parts that belong to the source project's own tooling, reworded a few sentences, added the notes below, and appended the section "Shared conventions".
>
> **Advisory.** This guide is advice, not a set of rules. The user's request, the document's own structure and the venue template take precedence over it; use the guide for the advice that remains. It describes a research article. The word counts, paragraph counts and other extents are typical ranges for a research article, not limits. For theses, reports and reviews, map the functions the guide describes onto that document's own sections and do not copy its headings or ranges. The list of disqualifiers names common weaknesses to check a draft against. The guide never licenses stating anything the user has not provided: facts, numbers, results and references come from the user's own files.

**Extent** 216–280 words · 7–14 sentences · **one paragraph**
**Does not carry** citations, equations, figures, tables, or section references
**Unit of composition** the sentence, not the paragraph

The abstract is the whole argument at one-fiftieth scale, and for most readers it is
the whole paper. It must be self-contained: no forward reference, no undefined
acronym, nothing that only makes sense after reading further. Every sentence here
compresses something the paper already establishes, and nothing in it reaches
outside this work.

## Global structural rule

Seven **functional slots**, in fixed order. Slot and sentence are not the same unit:
five of the seven expand. The shortest form is one sentence per slot; the longest
expands slots 1, 2, 4, 5, and 6 to reach fourteen.

| Slot | Function | Sentences | Words per sentence |
|---|---|---|---|
| 1 | Context | 1–2 | 9–31 |
| 2 | Problem | 1–2 | 15–29 |
| 3 | **The proposal, named** | **1, always** | 15–34 |
| 4 | Announcement and components | 1 inline, or 1 + N | 49–85 inline |
| 5 | Validation | 1–4 | 14–35 |
| 6 | Result or secondary contribution | 1–2 | 16–31 |
| 7 | **Verdict** | **1, always, and last** | 11–28 |

Two slots never expand and never move: the proposal occupies exactly one sentence,
and the verdict occupies exactly one sentence and is the last one in the abstract.

The components slot is the longest sentence — or the longest block — of the abstract.
It is the only place where the sentence is deliberately stretched; everywhere else,
compress.

## What the abstract drops

The abstract carries the same argument as the introduction, minus two of its blocks:

- **The state of the art does not get a slot.** It survives as half a clause inside
  slot 2, in the form *existing methods struggle to …*. Nothing more: no family is
  named, no lineage is walked.
- **The organization of the article never appears.** No section is named or
  referenced.

## Drafting order

The slots are not written in reading order; the same drafting dependencies apply as for the introduction. Four of the seven are draftable before anything is measured.

## Slot 1 — Context

One or two sentences. State the field and the phenomenon that motivates the work, and
why failure there is costly.

Anchor it in the condition, population, or process the dataset contains, not in the
family of techniques employed — the same rule that governs the introduction's opening
block. A single sentence suffices when the domain is common knowledge; a technical
domain needs two, one to place the field and one to narrow to the specific scenario.

## Slot 2 — Problem

One or two sentences. Open with an adversative — the gap is stated against the
context, not alongside it.

Name the specific shortcoming, never "challenges remain". Two sentences are used when
there are two distinct deficiencies, one per sentence. The state of the art is
absorbed here as a single clause attributing the shortcoming to existing methods.

When the problems must be satisfied together, say so in this slot: the word carrying
that simultaneity is what turns two limitations into one gap.

## Slot 3 — The proposal, named

**Exactly one sentence.** Never split, never moved.

It carries four things: the full name, the acronym in parentheses, the category of
the artefact, and the one mechanism that makes it new. The purpose clause mirrors the
deficiencies of slot 2, in the same order.

The first-person verb introducing the proposal appears exactly once in the whole
abstract. Everything before this sentence belongs to other people's work.

## Slot 4 — Announcement and components

**The number of items is the number of contributions the proposal has.** It is
inherited, never a drafting target. Announce the count before enumerating it.

Two forms are available. Choose one and hold it — never mix them.

**Inline.** Announcement and list in a single sentence, ending the announcement in a
colon, roman enumerators, semicolons between items. One sentence of 49 to 85 words.
Maximum compression.

**Expanded.** The announcement becomes its own short sentence, ending in a period, and
each component gets a sentence of its own opening with an ordinal. More legible, and
it makes each component quotable on its own.

Each item states what the component is and what function it performs. The clause
claiming an achieved effect is the part that waits for the results.

Do not open an item with a first-person verb instead of the component's name.

## Slot 5 — Validation

One to four sentences, in this order: scenario, data or tasks, methods compared
against, criteria or metrics, complementary analyses.

Name everything by its proper name. When the slot expands, each of those elements
takes its own sentence, in that order — the scenario is never stated after the
result.

Every property the proposal claims must have its instrument named here.

## Slot 6 — Result or secondary contribution

One or two sentences. This is where the secondary contribution lands — the property
that no component delivers and that an analysis answers instead, typically the one
that is not about performance.

### Figures are permitted here, under three conditions

A figure is admitted only when the figure **is** the fact being framed. This is the
one place in the paper where a number appears outside the results section, and it
exists because the abstract is read on its own: a result that must be framed has
nowhere else to land. The introduction never carries one.

1. **It is a permission, not a convention.** If the abstract works in comparatives, it
   stays in comparatives. A figure is not decoration for the verdict.
2. **The figure states what it belongs to, in the same sentence.** If the number
   characterizes a base component rather than the contribution, say so explicitly.
   Without that clause the abstract claims credit that is not its own.
3. **The unit is one framed fact, not one number.** A single fact may need two values
   to state it; that is one, not two.

A figure quoted here is bound to the results section and must match it exactly.

## Slot 7 — Verdict

**Exactly one sentence, the last one, and among the shortest.** 11 to 28 words.

It states the direction of the outcome and names the axes on which the work improves
— the same axes stated as requirements in slot 2. It opens with a summative adverbial
or a confirmation formula.

It introduces nothing: no new property, no new number, no new claim.

## Cross-cutting conventions

- **One paragraph.** No line breaks, no bullets, no headings.
- **No citations of any kind**, including to the authors' own prior work.
- **Expand every acronym on first appearance**, including the proposal's own. A
  domain dense in acronyms expands all of them, however many that is.
- **State the count before enumerating it.**
- The enumeration form here is distinct from the introduction's: roman numerals
  inline, or ordinals one per sentence. The count, order, and naming must match the
  introduction's list and the components of the methods section.

## Disqualifiers

- More than one paragraph.
- A citation, an equation, a figure, a table, or a section reference.
- An unexpanded acronym.
- Over 300 or under 200 words.
- A missing slot. All seven are present even in the shortest form.
- The proposal split across two sentences, or not carrying its full name, acronym,
  category, and mechanism.
- The verdict not last, or expanded beyond one sentence, or introducing something new.
- The components slot not being the longest of the abstract.
- Inline and expanded component forms mixed.
- A component count, order, or naming that disagrees with the introduction or the
  methods section.
- The count announced without being enumerated, or enumerated without being announced.
- The evaluation scenario stated after the result it produced.
- A named family of prior methods, or a walked lineage: that belongs to the state of
  the art, which has no slot here.
- A section named or referenced.
- A quoted figure with no statement of what it belongs to.
- A quoted figure that does not match the results section exactly.
- A property claimed with no instrument named in slot 5.
- A forward reference of any kind.

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
