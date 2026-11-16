---
{
  "section": "methods",
  "position": 5,
  "mode": {
    "value": "transposition",
    "source": {
      "file": "sections/05-methods.md",
      "quote": "The methods transcribe the protocol and the logs under review/; they never describe a step that was not run."
    }
  },
  "blocks": [
    {
      "id": "m-protocol-registration",
      "requires_facts": [],
      "requires_declarations": [
        {
          "value": "review-registration",
          "source": {
            "file": "sections/05-methods.md",
            "quote": "The review-registration is stated with the protocol's location and any amendment to it."
          }
        }
      ],
      "citations": "resolution"
    },
    {
      "id": "m-eligibility",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none"
    },
    {
      "id": "m-information-sources",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "resolution"
    },
    {
      "id": "m-search-strategy",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none"
    },
    {
      "id": "m-selection-process",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "resolution"
    },
    {
      "id": "m-data-collection",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none"
    },
    {
      "id": "m-risk-of-bias",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "resolution"
    },
    {
      "id": "m-synthesis",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "resolution"
    },
    {
      "id": "m-certainty",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "resolution",
      "optional": true
    }
  ]
}
---

# Methods (review line)

The methods transcribe the protocol and the logs under review/; they never describe a step that was not run.
Titled *Research Methodology* when the venue or the group prefers it. Open
with one sentence stating that the review follows the PRISMA 2020 statement
(Page et al., 2021, doi:10.1136/bmj.n71), and, for software engineering
topics, the Kitchenham and Charters guidelines. Every block below maps to
PRISMA 2020 items; `python skills/systematic-review/scripts/review_cli.py
checklist --root .` reports which items still lack a section.

**Extent** 800–1500 words · one protocol table, the PRISMA flow figure

## Block `m-protocol-registration` (item 24)

The review-registration is stated with the protocol's location and any amendment to it. When the protocol was registered after the search started, say so.
A table summarizes the protocol in its phases (planning, search, selection,
extraction and synthesis), one row per phase with what was done and the
record that holds it.

## Block `m-eligibility` (item 5)

Inclusion and exclusion criteria from `review/protocol.json`, each with its
reason, and how studies were grouped for the synthesis: study design, years,
language, publication type (peer-reviewed journal and conference papers,
grey literature or not).

## Block `m-information-sources` (item 6)

Every database, registry and other source with the date it was last searched
(`review/searches.jsonl`), plus citation chasing (backward and forward
snowballing) and contact with authors when done.

## Block `m-search-strategy` (item 7)

The full query string for each source, exactly as run, with its filters and
limits. When it is long, the full strings go to a supplementary table and the
text shows one of them.

## Block `m-selection-process` (item 8)

Who screened (number of reviewers and whether they worked independently), the
two stages (titles and abstracts, then full texts), how disagreements were
resolved, the agreement measured (Cohen's kappa from `review_cli.py kappa`),
and any automation tool used, including the language model that acted as a
second screener and how its decisions were checked.

## Block `m-data-collection` (items 9-10)

How data were extracted (the protocol's extraction fields, who extracted, how
it was verified) and the list of data items: outcomes and the other variables
sought (study characteristics, methods, datasets, metrics).

## Block `m-risk-of-bias` (item 11)

The appraisal tool (the Kitchenham quality checklist, CASP, JBI, MMAT or
RoB 2 for randomized trials), its questions and scoring, how many reviewers
applied it, and whether a threshold excluded studies.

## Block `m-synthesis` (items 12-13)

The synthesis method: how the taxonomy of themes and the problem classes
were built (from the background's open problems and the extracted data, with
the operator), the comparison dimensions each theme is read along, the
comparison tables, and any meta-analysis (model, heterogeneity), bibliometric
analysis or sensitivity analysis. When a study can fall in several themes,
say so here.

## Block `m-certainty` (items 14-15, optional)

Reporting-bias assessment and the certainty of evidence (GRADE) when the
review makes evaluative claims.

## LIA house style

Measured on the group's MDPI review A029 (Cardona-Álvarez, Álvarez-Meza and Castellanos-Dominguez, *Computers* 2025, 14(5):194, doi:10.3390/computers14050194): about 9500 words of body, 168 references of which 102 are included studies, one figure (the PRISMA 2020 flow) and six tables. The ranges describe how the group writes a review; the extent at the top of this contract stays the target, and the disqualifiers below also correct what a PRISMA referee flags in A029.

**Measured size.** 985 words; the PRISMA 2020 flow (Figure 1), a four-phase protocol table (Table 1), the distribution of the included studies by topic and by addressed problem (Tables 2 and 3) and a qualitative comparison of the technologies (Table 4).

**What A029 does and the review line keeps:** the protocol table, the flow figure cited in the text, and the sources with the period searched (2020 to 2024). **What it changes:** A029 lists its keywords as examples (*Keywords such as …*) instead of the query strings as run, gives no last search date per source, names no number of screeners and no agreement, and assesses no risk of bias; each of those is a PRISMA item a referee checks. The classification tables move to the results, where PRISMA reports study characteristics.

**Writing (every review section).**

- **Sentences average 18–27 words** (A029: median 22). One claim and its qualifier per sentence.
- **One voice.** First person plural for what the review did (*we searched*, *we grouped*), past tense for every step that was run, present tense for what the evidence shows (*the included studies agree*).
- **Citations are numeric, in square brackets, and close the claim they support.** A review cites groups of included studies: list them with commas (`[12,15,19]`), or as a range when they are consecutive in the reference list (`[36–39]`). A citation is never the grammatical subject of a sentence.
- **Transitions come from the relation between claims.** A stock connector (*In addition*, *Furthermore*, *Additionally*, *Moreover*) is the exception: never the same one twice within five sentences. A029 opens 14 sentences with *In addition* and 16 with *Furthermore* or *Additionally*; that is the pattern to avoid.
- **No promotional adjectives.** *Revolutionary*, *transformative*, *pivotal*, *comprehensive*, *crucial*, *novel* say nothing a reader can check; state what the evidence shows instead.
- **Every number comes from a record.** Counts from `review/prisma.json`, study values from `review/extraction.jsonl`, never recounted by hand.

## Disqualifiers

- A search strategy given as example keywords (*terms such as*) instead of the full query string of each source as run.
- A source named without the date it was last searched.
- A count that differs from `review/prisma.json`.
- A selection process without the number of reviewers, how conflicts were settled, and the agreement measured.
- No risk-of-bias tool, or *not assessed* without the limitations saying so.
- A step described that has no record under `review/`.
- A language model used as a screener or an extractor and not reported.

## Inputs

### External inputs

| Input | Unblocks |
|---|---|
| `review-registration` — The review-registration is stated with the protocol's location and any amendment to it. | `m-protocol-registration` |

### Internal chain

None: no block of this section waits on another block.
