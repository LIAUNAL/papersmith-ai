---
{
  "section": "methods",
  "position": 4,
  "mode": {
    "value": "transposition",
    "source": {
      "file": "sections/04-methods.md",
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
            "file": "sections/04-methods.md",
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
Open with one sentence stating that the review follows the PRISMA 2020
statement (Page et al., 2021, doi:10.1136/bmj.n71), and, for software
engineering topics, the Kitchenham and Charters guidelines. Every block below
maps to PRISMA 2020 items; `python skills/systematic-review/scripts/review_cli.py
checklist --root .` reports which items still lack a section.

## Block `m-protocol-registration` (item 24)

The review-registration is stated with the protocol's location and any amendment to it. When the protocol was registered after the search started, say so.

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

How data were extracted (form fields from `review/extraction-schema.json`, who
extracted, how it was verified) and the list of data items: outcomes and the
other variables sought (study characteristics, methods, datasets, metrics).

## Block `m-risk-of-bias` (item 11)

The appraisal tool (the Kitchenham quality checklist, CASP, JBI, MMAT or
RoB 2 for randomized trials), its questions and scoring, how many reviewers
applied it, and whether a threshold excluded studies.

## Block `m-synthesis` (items 12-13)

Effect measures when outcomes were combined, and the synthesis method:
narrative or thematic synthesis, the taxonomy and how it was built, tabulation,
meta-analysis (model, heterogeneity), bibliometric analysis (counts per year and
venue, keyword co-occurrence) and any sensitivity analysis.

## Block `m-certainty` (items 14-15, optional)

Reporting-bias assessment and the certainty of evidence (GRADE) when the
review makes evaluative claims.

## Sources

- `review/protocol.json`, `review/searches.jsonl`, `review/screening.jsonl`,
  `review/appraisal.jsonl`, `review/extraction.jsonl`.

## Inputs

### External inputs

| Input | Unblocks |
|---|---|
| `review-registration` — The review-registration is stated with the protocol's location and any amendment to it. | `m-protocol-registration` |

### Internal chain

None: no block of this section waits on another block.
