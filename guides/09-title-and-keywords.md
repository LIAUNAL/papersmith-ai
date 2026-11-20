# Title and Keywords

> **Notice.** This guide is a modified derivative of `sections/09-title-and-keywords.md` from papersmith-ai (https://github.com/Daprosero/papersmith-ai, commit `1f09516`), licensed under the Apache License, Version 2.0. A copy of the license is provided as `LICENSE-papersmith-ai.txt` in this folder. Caztor removed the parts that belong to the source project's own tooling, reworded a few sentences, added the notes below, and appended the section "Shared conventions".
>
> **Advisory.** This guide is advice, not a set of rules. The user's request, the document's own structure and the venue template take precedence over it; use the guide for the advice that remains. It describes a research article. The word counts, paragraph counts and other extents are typical ranges for a research article, not limits. For theses, reports and reviews, map the functions the guide describes onto that document's own sections and do not copy its headings or ranges. The list of disqualifiers names common weaknesses to check a draft against. The guide never licenses stating anything the user has not provided: facts, numbers, results and references come from the user's own files.

**Extent** title 11–15 words · keywords 4–8
**Carries** no number, no percentage, no claim of superiority

The title is the paper's only irrevocable claim: it is what gets cited, indexed and
searched. The keywords are the retrieval surface — the terms a reader who needs this
paper will type without knowing it exists.

## The title is a slot machine

| Slot | Required | What it is |
|---|---|---|
| Acronym, followed by a colon | no | The name the method is meant to carry in the literature |
| Article | no | *A* or *An* |
| **Property adjective** | **yes** | The property the contribution adds — and it comes first |
| **Mechanism** | **yes** | What the method is made of, named explicitly |
| Artefact noun | no | *Framework*, *approach*, *network* — the category of the thing |
| **Task** | **yes** | What the method is for |
| Domain or place | no | Only when the work is bound to it |

**The three required slots come from the proposal**: the property is the one the
contributions add, the mechanism is what realizes them, the task is the one the
problem statement named.

**The property adjective comes first**, right after the article or the acronym. The
title opens on the property, not on the mechanism — it is the first thing the reader
reads.

**Three slots are optional, and each has a condition.** The artefact noun is dropped
when the mechanisms themselves are the title. The domain or place appears only when
the work does not transfer beyond it. The acronym appears only when it is meant to
become the method's public name, and then it takes a colon and the abstract expands
it.

## Dashes do two different jobs

**A hyphen joins a modifier pair** — two words that together modify a third.

**An en dash joins co-equal terms in a series** — dimensions of the same rank, none
modifying another.

Confusing them changes what the title says: with a hyphen, the first term of a
co-equal series reads as a modifier of the last.

## What never appears in the title

No number, no percentage, no comparative, no claim of superiority. The title states
what the thing is, not how well it did.

Title case, with prepositions and articles in lower case.

## Keywords

**Four to eight, separated by semicolons.** Lower case by default; acronyms in capitals;
proper nouns keep their case.

**They are not a restatement of the title.** Roughly a third repeat a term the title
already carries; the rest add something the title had no room for. A keyword list
that only echoes the title has wasted its whole retrieval surface.

**What the added ones carry**, in three kinds:

1. **The mechanisms the title omitted** — the estimator, the architecture, the
   reduction method, whatever did not fit.
2. **The data modality or the population** — the kind of data, the task family, the
   concrete condition or setting studied.
3. **The property in its searchable form.** The title carries the adjective; the
   keyword carries the noun.

**Ordered broadest to most specific:** the task or domain first, then the property,
then the machinery.

**Every keyword appears in the body.** A keyword absent from the paper is a keyword
invented for the search engine.

## The classification line

Some journals require a subject-classification code after the keywords. That is an
external requirement, not a style decision: take it from the target journal's
instructions, along with the permitted keyword count.

## Disqualifiers

- Under 10 or over 16 words in the title.
- No property adjective, or one that is not first.
- No mechanism named.
- No task named.
- A number, a percentage, or a claim of superiority.
- An acronym in the title without a colon, or one the abstract does not expand.
- A domain or place named when the work is not bound to it.
- A hyphen where co-equal terms in a series need an en dash.
- Fewer than 4 or more than 8 keywords, or a count the target journal does not permit.
- A keyword list that only repeats title terms.
- A keyword absent from the body.
- A missing classification line when the target journal requires one.

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
