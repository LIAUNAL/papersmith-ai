---
{
  "section": "discussion",
  "position": 7,
  "mode": {
    "value": "argument",
    "source": {
      "file": "sections/07-discussion.md",
      "quote": "The discussion interprets the results against other evidence and turns them into challenges and directions."
    }
  },
  "blocks": [
    {
      "id": "d-principal-findings",
      "requires_facts": [
        {
          "value": "contributions",
          "source": {
            "file": "sections/07-discussion.md",
            "quote": "The contributions are revisited one by one with what the evidence supports."
          }
        }
      ],
      "requires_declarations": [],
      "citations": "resolution",
      "after": [
        {
          "target": "results",
          "source": {
            "file": "sections/07-discussion.md",
            "quote": "The contributions are revisited one by one with what the evidence supports."
          }
        },
        {
          "target": "introduction.intro-objectives",
          "source": {
            "file": "sections/07-discussion.md",
            "quote": "The contributions are revisited one by one with what the evidence supports."
          }
        }
      ]
    },
    {
      "id": "d-other-evidence",
      "requires_facts": [
        {
          "value": "gap",
          "source": {
            "file": "sections/07-discussion.md",
            "quote": "The gap the introduction stated is the yardstick: say how far the evidence closes it."
          }
        }
      ],
      "requires_declarations": [],
      "citations": "discovery",
      "after": [
        {
          "target": "introduction.intro-existing-reviews",
          "source": {
            "file": "sections/07-discussion.md",
            "quote": "The gap the introduction stated is the yardstick: say how far the evidence closes it."
          }
        }
      ]
    },
    {
      "id": "d-challenges-directions",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "resolution"
    },
    {
      "id": "d-implications",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none"
    }
  ]
}
---

# Discussion (review line)

PRISMA 2020 item 23a and 23d. The discussion interprets the results against other evidence and turns them into challenges and directions.
It reads the synthesis along a cross-cutting axis chosen with the operator
(a life cycle, a pipeline, a level of maturity) that cuts across the themes,
so that it says something the thematic subsections could not.

**Extent** 450–1200 words

## Block `d-principal-findings`

The contributions are revisited one by one with what the evidence supports. One paragraph per stage of the cross-cutting axis or per
research question, interpreting the pattern and citing the groups of studies
that support it, never restating the tables.

## Block `d-other-evidence`

The gap the introduction stated is the yardstick: say how far the evidence closes it. Compare with the existing reviews named in the introduction:
what agrees, what this review adds, what contradicts them and why
(scope, period, criteria).

## Block `d-challenges-directions`

The open challenges the included studies share, each with the studies that
report it, and the research directions that follow, ordered by how much
evidence supports them.

## Block `d-implications`

What practitioners, researchers and policymakers can do with the synthesis.

## LIA house style

Measured on the group's MDPI review A029 (Cardona-Álvarez, Álvarez-Meza and Castellanos-Dominguez, *Computers* 2025, 14(5):194, doi:10.3390/computers14050194): about 9500 words of body, 168 references of which 102 are included studies, one figure (the PRISMA 2020 flow) and six tables. The ranges describe how the group writes a review; the extent at the top of this contract stays the target, and the disqualifiers below also correct what a PRISMA referee flags in A029.

**Measured size.** 436 words of discussion, organized along the data life cycle (generation, storage, processing, transmission), citing groups of studies as ranges (*[36–39]*).

**What A029 does and the review line keeps:** a discussion organized along an axis that crosses the themes, citing groups of studies. **What it changes:** A029 does not compare its findings with earlier reviews; here `d-other-evidence` does.

**Writing (every review section).**

- **Sentences average 18–27 words** (A029: median 22). One claim and its qualifier per sentence.
- **One voice.** First person plural for what the review did (*we searched*, *we grouped*), past tense for every step that was run, present tense for what the evidence shows (*the included studies agree*).
- **Citations are numeric, in square brackets, and close the claim they support.** A review cites groups of included studies: list them with commas (`[12,15,19]`), or as a range when they are consecutive in the reference list (`[36–39]`). A citation is never the grammatical subject of a sentence.
- **Transitions come from the relation between claims.** A stock connector (*In addition*, *Furthermore*, *Additionally*, *Moreover*) is the exception: never the same one twice within five sentences. A029 opens 14 sentences with *In addition* and 16 with *Furthermore* or *Additionally*; that is the pattern to avoid.
- **No promotional adjectives.** *Revolutionary*, *transformative*, *pivotal*, *comprehensive*, *crucial*, *novel* say nothing a reader can check; state what the evidence shows instead.
- **Every number comes from a record.** Counts from `review/prisma.json`, study values from `review/extraction.jsonl`, never recounted by hand.

## Disqualifiers

- A paragraph that restates a table or a subsection of the results.
- A direction that no challenge of the included studies supports.
- No comparison with the existing reviews the introduction named.
- A claim stronger than the risk of bias and the number of studies allow.
- A promotional adjective, or a closing appeal to collaboration among stakeholders with no finding behind it.

## Inputs

### External inputs

| Input | Unblocks |
|---|---|
| `contributions` — The contributions are revisited one by one with what the evidence supports. | `d-principal-findings` |
| `gap` — The gap the introduction stated is the yardstick: say how far the evidence closes it. | `d-other-evidence` |

### Internal chain

| Block | Depends on |
|---|---|
| `discussion.d-principal-findings` — The contributions are revisited one by one with what the evidence supports. | `introduction.intro-objectives` |
| `discussion.d-other-evidence` — The gap the introduction stated is the yardstick: say how far the evidence closes it. | `introduction.intro-existing-reviews` |
