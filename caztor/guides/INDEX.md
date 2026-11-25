# Writing guides

These guides are advisory advice for writing the sections of an academic document. The user's request, the document's own structure and the venue template take precedence over them. They describe a research article; for theses, reports and reviews, map the functions they describe onto that document's own sections and do not copy headings or extents. Word counts and other extents are typical ranges, not limits. The guides never license stating anything the user has not provided.

They are derived from the section guides of papersmith-ai, licensed under the Apache License, Version 2.0 (the license text is in `LICENSE-papersmith-ai.txt`). Each guide carries its own notice.

## How to use them

1. Read this index.
2. Open only the guide for the section being written or revised.
3. Apply the advice that fits the document and ignore the rest.

## Guides

| Guide | Section | Function |
|---|---|---|
| `01-materials-and-methods.md` | Materials and Methods | Defines the contributions formally: the dataset, the borrowed theory, the proposal and its notation. |
| `02-experimental-setup.md` | Experimental Set-Up | Turns the method into a protocol: the comparison design, the metrics, the compared methods and the training details. |
| `03-results-and-discussion.md` | Results and Discussion | Presents the evidence for each claim and explains each result next to its number. |
| `04-limitations.md` | Limitations | States what the reported results do not establish, tied to decisions in the method and the design. |
| `05-related-work.md` | Related Work | Argues what prior work, taken together, leaves unsolved, one block per stated problem. |
| `06-introduction.md` | Introduction | Motivates the problem, states the gap, presents the proposal and its evaluation, and announces the structure. |
| `07-conclusions.md` | Conclusions | Restates the proposal, the results, their consequence and the future work, for readers who skip the paper. |
| `08-abstract.md` | Abstract | Compresses the whole argument into one self-contained paragraph. |
| `09-title-and-keywords.md` | Title and Keywords | Shapes the title as one claim and the keywords as the retrieval surface. |
| `10-back-matter.md` | Back Matter | Covers author contributions, funding, data availability, conflicts of interest, acknowledgments and appendices. |

## Coherence across sections

- The introduction, the abstract and the conclusions restate the contributions of the methods section with the same count, order and names; the title selects among them.
- A problem keeps one name through the introduction, the contribution, the experimental set-up and the results.
- The gap stated in the introduction and the gap closing the related work say the same thing at different depths.
- Every future-work direction in the conclusions answers a limitation that the limitations section declares.
- The abstract compresses the conclusions, so it is written after them; it adds nothing the paper does not establish.
