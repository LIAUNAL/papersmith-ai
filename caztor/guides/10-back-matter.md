# Back Matter

> **Notice.** This guide is a modified derivative of `sections/10-back-matter.md` from papersmith-ai (https://github.com/Daprosero/papersmith-ai, commit `1f09516`), licensed under the Apache License, Version 2.0. A copy of the license is provided as `LICENSE-papersmith-ai.txt` in this folder. Caztor removed the parts that belong to the source project's own tooling, reworded a few sentences, added the notes below, and appended the section "Shared conventions".
>
> **Advisory.** This guide is advice, not a set of rules. The user's request, the document's own structure and the venue template take precedence over it; use the guide for the advice that remains. It describes a research article. The word counts, paragraph counts and other extents are typical ranges for a research article, not limits. For theses, reports and reviews, map the functions the guide describes onto that document's own sections and do not copy its headings or ranges. The list of disqualifiers names common weaknesses to check a draft against. The guide never licenses stating anything the user has not provided: facts, numbers, results and references come from the user's own files.

The administrative block that sits after the conclusions and before the references.
It is not scientific prose — it is the paper's accountability surface: who did what,
who paid, where the data and code are, and what could bias the work.

Each block is a bold inline label followed by prose. No section headings, no
subsections. This is the most mechanical part of the paper and the most likely to be
wrong at submission, because nobody treats it as writing.

## The blocks, in this order

| Block | Required | Words |
|---|---|---|
| Author Contributions | yes | 37–44 |
| Funding | yes | 55 per project |
| Data Availability Statement | yes | 7–22 |
| Conflicts of Interest | yes | one sentence |
| Acknowledgments | only if there is a project to thank | ~25 |
| Appendices | only if the paper needs them | — |

## Author Contributions

A formula, which is why its length barely varies. The CRediT roles, semicolon
separated, each followed by the initials of the authors who held it, comma separated
with *and* before the last. Then the standing closing sentence stating that all
authors have read and agreed to the published version.

**Every author appears in at least one role.** The roles are the ones each author
confirmed, not the ones inferred from the work.

## Funding

One entry per grant. Each carries the project's **exact registered title**, in its
original language, the funder, and the grant code. When a grant supports a specific
author rather than the work as a whole, name that author with it.

Grant codes are copied from the funding records, never retyped from memory.

## Data Availability Statement

The repository URL plus the date it was checked. The URL must resolve, and it must
hold the code that produced the reported numbers.

When the data cannot be published, say so in one line and give the route to request
it. Do not point at a repository holding only code while implying it holds the data.

State what is public and what is not — they are different claims.

## Conflicts of Interest

One sentence declaring none.

The one case that needs more: when an author is affiliated with an organization with
an interest in the results — typically the one that supplied the data — name the
affiliation explicitly and repeat the declaration for that author. Silence about a
known affiliation is the failure this block exists to prevent.

## Acknowledgments

Present only when there is a project or institution to thank that is not already
named under funding. One or two sentences.

## Appendices

Used when material is necessary to reproduce the work but would break the flow of
the section that needs it — verbatim artefacts, or a full parameter table when the
experimental setup carries only the values that were reasoned about.

Lettered, with subsections numbered under their letter. **Each appendix is referenced
from the body section that needs it**; one that nothing references is dead weight.

Whether the paper has appendices at all is decided per paper.

## Drafting order

Every block here is an external fact, not a decision. None of it is derived from the
paper.

## Disqualifiers

- An author with no role.
- A role attributed without the author confirming it.
- A grant title or code reproduced from memory rather than copied.
- A repository URL that does not resolve, or that holds code unable to produce the
  reported numbers.
- A missing access date on the URL.
- A data availability statement claiming public data that is not public.
- A known interested affiliation left undeclared.
- An appendix that no body section references.
- Appendix content that contradicts the experimental setup.

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
