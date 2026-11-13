---
{
  "section": "results",
  "position": 5,
  "mode": {
    "value": "argument",
    "source": {
      "file": "sections/05-results.md",
      "quote": "Every count comes from review/prisma.json and every study characteristic from review/extraction.jsonl."
    }
  },
  "blocks": [
    {
      "id": "r-study-selection",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none"
    },
    {
      "id": "r-study-characteristics",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "resolution"
    },
    {
      "id": "r-risk-of-bias",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "resolution"
    },
    {
      "id": "r-bibliometrics",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none",
      "optional": true
    },
    {
      "id": "r-research-questions",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "resolution",
      "after": [
        {
          "target": "introduction.intro-objectives",
          "source": {
            "file": "sections/05-results.md",
            "quote": "One subsection per research question, in the order and with the wording of the introduction."
          }
        }
      ]
    }
  ]
}
---

# Results (review line)

PRISMA 2020 items 16 to 22. Every count comes from review/prisma.json and every study characteristic from review/extraction.jsonl.

## Block `r-study-selection` (item 16)

The flow of records: identified per source, duplicates removed, screened,
excluded at title and abstract, reports sought and not retrieved, assessed in
full text, excluded with each reason and its count, and included. The PRISMA
2020 flow diagram (`paper/Figures/prisma-flow.svg`, drawn by `review_cli.py
flow`) is cited here. Name studies that looked eligible but were excluded,
with the reason.

## Block `r-study-characteristics` (item 17)

A table of the included studies: reference, year, venue, setting or domain,
method, data, evaluation and outcomes, from the extraction form.

## Block `r-risk-of-bias` (item 18)

The appraisal of each included study (a table or a figure) and the overall
pattern.

## Block `r-bibliometrics` (optional)

Publications per year, per venue and per country, and the keyword
co-occurrence map from `review_cli.py biblio`, each described in one or two
sentences that state what the figure shows, not what it means.

## Block `r-research-questions` (items 19-22)

One subsection per research question, in the order and with the wording of the introduction.
Each answers its question from the included studies only, cites every study
it summarizes, and presents the taxonomy, tables and syntheses the methods
announced. Interpretation waits for the discussion.

## Inputs

### External inputs

None: every block reads the records under `review/` and the operator's declarations.

### Internal chain

| Block | Depends on |
|---|---|
| `results.r-research-questions` — One subsection per research question, in the order and with the wording of the introduction. | `introduction.intro-objectives` |
