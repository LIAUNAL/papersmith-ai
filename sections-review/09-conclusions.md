---
{
  "section": "conclusions",
  "position": 9,
  "mode": {
    "value": "transposition",
    "source": {
      "file": "sections/09-conclusions.md",
      "quote": "Conclusions add nothing: every claim already exists earlier in the review."
    }
  },
  "blocks": [
    {
      "id": "concl-answers",
      "requires_facts": [
        {
          "value": "contributions",
          "source": {
            "file": "sections/09-conclusions.md",
            "quote": "The contributions — the answer to each research question — in the order of the introduction."
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none",
      "after": [
        {
          "target": "discussion",
          "source": {
            "file": "sections/09-conclusions.md",
            "quote": "The contributions — the answer to each research question — in the order of the introduction."
          }
        },
        {
          "target": "introduction.intro-objectives",
          "source": {
            "file": "sections/09-conclusions.md",
            "quote": "The contributions — the answer to each research question — in the order of the introduction."
          }
        }
      ]
    },
    {
      "id": "concl-future",
      "requires_facts": [
        {
          "value": "limitations",
          "source": {
            "file": "sections/09-conclusions.md",
            "quote": "The limitations bound every conclusion; the future directions come from the discussion."
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none",
      "after": [
        {
          "target": "limitations",
          "source": {
            "file": "sections/09-conclusions.md",
            "quote": "The limitations bound every conclusion; the future directions come from the discussion."
          }
        },
        {
          "target": "limitations.lim-evidence",
          "source": {
            "file": "sections/09-conclusions.md",
            "quote": "The limitations bound every conclusion; the future directions come from the discussion."
          }
        }
      ]
    }
  ]
}
---

# Conclusions (review line)

Conclusions add nothing: every claim already exists earlier in the review.

**Extent** 300–600 words · 3 to 5 paragraphs

## Block `concl-answers`

The contributions — the answer to each research question — in the order of the introduction. One or two sentences each.

## Block `concl-future`

The limitations bound every conclusion; the future directions come from the discussion. Three to five directions, each traceable to a challenge of the
discussion.

## LIA house style

Measured on the group's MDPI review A029 (Cardona-Álvarez, Álvarez-Meza and Castellanos-Dominguez, *Computers* 2025, 14(5):194, doi:10.3390/computers14050194): about 9500 words of body, 168 references of which 102 are included studies, one figure (the PRISMA 2020 flow) and six tables. The ranges describe how the group writes a review; the extent at the top of this contract stays the target, and the disqualifiers below also correct what a PRISMA referee flags in A029.

**Measured size.** 409 words: insights per technology, referring back to the comparison table, then one paragraph of future research.

**What A029 does and the review line keeps:** one paragraph of answers per theme, then the future research. **What it changes:** the answers follow the research questions, and the closing names directions instead of a general appeal.

**Writing (every review section).**

- **Sentences average 18–27 words** (A029: median 22). One claim and its qualifier per sentence.
- **One voice.** First person plural for what the review did (*we searched*, *we grouped*), past tense for every step that was run, present tense for what the evidence shows (*the included studies agree*).
- **Citations are numeric, in square brackets, and close the claim they support.** A review cites groups of included studies: list them with commas (`[12,15,19]`), or as a range when they are consecutive in the reference list (`[36–39]`). A citation is never the grammatical subject of a sentence.
- **Transitions come from the relation between claims.** A stock connector (*In addition*, *Furthermore*, *Additionally*, *Moreover*) is the exception: never the same one twice within five sentences. A029 opens 14 sentences with *In addition* and 16 with *Furthermore* or *Additionally*; that is the pattern to avoid.
- **No promotional adjectives.** *Revolutionary*, *transformative*, *pivotal*, *comprehensive*, *crucial*, *novel* say nothing a reader can check; state what the evidence shows instead.
- **Every number comes from a record.** Counts from `review/prisma.json`, study values from `review/extraction.jsonl`, never recounted by hand.

## Disqualifiers

- A new claim, a new citation, or a number that differs from the results.
- A research question without its answer.
- A direction that the discussion does not raise.
- A closing appeal (*a digitally inclusive future*, *fostering collaboration*) in place of a direction.

## Inputs

### External inputs

| Input | Unblocks |
|---|---|
| `contributions` — The contributions — the answer to each research question — in the order of the introduction. | `concl-answers` |
| `limitations` — The limitations bound every conclusion; the future directions come from the discussion. | `concl-future` |

### Internal chain

| Block | Depends on |
|---|---|
| `conclusions.concl-answers` — The contributions — the answer to each research question — in the order of the introduction. | `introduction.intro-objectives` |
| `conclusions.concl-future` — The limitations bound every conclusion; the future directions come from the discussion. | `limitations.lim-evidence` |
