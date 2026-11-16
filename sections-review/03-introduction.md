---
{
  "section": "introduction",
  "position": 3,
  "mode": {
    "value": "argument",
    "source": {
      "file": "sections/03-introduction.md",
      "quote": "The introduction argues why a systematic review of this question is needed and what it answers."
    }
  },
  "blocks": [
    {
      "id": "intro-rationale",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "discovery",
      "produces_facts": [
        {
          "value": "problem-statement",
          "source": {
            "file": "sections/03-introduction.md",
            "quote": "The problem-statement says why the topic needs a synthesis now."
          }
        }
      ]
    },
    {
      "id": "intro-existing-reviews",
      "requires_facts": [
        {
          "value": "problem-statement",
          "source": {
            "file": "sections/03-introduction.md",
            "quote": "The gap is what existing reviews leave unanswered: scope, period, or method."
          }
        }
      ],
      "requires_declarations": [],
      "citations": "discovery",
      "after": [
        {
          "target": "introduction.intro-rationale",
          "source": {
            "file": "sections/03-introduction.md",
            "quote": "The gap is what existing reviews leave unanswered: scope, period, or method."
          }
        }
      ],
      "produces_facts": [
        {
          "value": "gap",
          "source": {
            "file": "sections/03-introduction.md",
            "quote": "The gap is what existing reviews leave unanswered: scope, period, or method."
          }
        }
      ]
    },
    {
      "id": "intro-objectives",
      "requires_facts": [
        {
          "value": "gap",
          "source": {
            "file": "sections/03-introduction.md",
            "quote": "The contributions are the research questions and what the review delivers for each."
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none",
      "after": [
        {
          "target": "introduction.intro-existing-reviews",
          "source": {
            "file": "sections/03-introduction.md",
            "quote": "The contributions are the research questions and what the review delivers for each."
          }
        }
      ],
      "produces_facts": [
        {
          "value": "contributions",
          "source": {
            "file": "sections/03-introduction.md",
            "quote": "The contributions are the research questions and what the review delivers for each."
          }
        }
      ]
    },
    {
      "id": "intro-skeleton",
      "requires_facts": [
        {
          "value": "skeleton",
          "source": {
            "file": "sections/03-introduction.md",
            "quote": "The skeleton is the order of the sections that follow."
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none"
    }
  ]
}
---

# Introduction (review line)

PRISMA 2020 items 3 (rationale) and 4 (objectives). The introduction argues
why a systematic review of this question is needed and what it answers.

**Extent** 500–900 words · 4 to 7 paragraphs

## Block `intro-rationale`

The problem-statement says why the topic needs a synthesis now. The field, its growth (publication counts from the search may
be cited from the results), the decisions practitioners or researchers face,
and why primary studies alone do not settle them. Cited from the literature,
never from the included studies' results.

## Block `intro-existing-reviews`

The gap is what existing reviews leave unanswered: scope, period, or method. Name the closest existing reviews (`review/scope.json`), what
each covered and when, and the joint gap that this review closes. A review
published after the last one cited here would reopen the gap, so the search
date is stated in the methods.

## Block `intro-objectives`

The contributions are the research questions and what the review delivers for each. State the objective in one sentence and list the research
questions (RQ1, RQ2, …) exactly as `review/protocol.json` words them, with the
PICOC elements (population, intervention, comparison, outcomes, context) when
the question is evaluative. Close with the contributions as a numbered list:
the map, the taxonomy, the comparison, the open challenges.

## Block `intro-skeleton`

The skeleton is the order of the sections that follow. One sentence per section, opened by *The remainder of this
paper is organized as follows:*.

## LIA house style

Measured on the group's MDPI review A029 (Cardona-Álvarez, Álvarez-Meza and Castellanos-Dominguez, *Computers* 2025, 14(5):194, doi:10.3390/computers14050194): about 9500 words of body, 168 references of which 102 are included studies, one figure (the PRISMA 2020 flow) and six tables. The ranges describe how the group writes a review; the extent at the top of this contract stays the target, and the disqualifiers below also correct what a PRISMA referee flags in A029.

**Measured size.** 637 words, seven citation markers, no list.

**The moves A029 makes and the review line keeps:** the field and its life cycle; the deficiency of the literature; the scope (the technologies the review covers); the objective; the roadmap. **What it changes:** A029 says it formulated research questions but never states them, and claims a *lack of comprehensive analysis* without naming a single earlier review. Here the research questions are listed verbatim and the gap is measured against the reviews `scope` found.

**Writing (every review section).**

- **Sentences average 18–27 words** (A029: median 22). One claim and its qualifier per sentence.
- **One voice.** First person plural for what the review did (*we searched*, *we grouped*), past tense for every step that was run, present tense for what the evidence shows (*the included studies agree*).
- **Citations are numeric, in square brackets, and close the claim they support.** A review cites groups of included studies: list them with commas (`[12,15,19]`), or as a range when they are consecutive in the reference list (`[36–39]`). A citation is never the grammatical subject of a sentence.
- **Transitions come from the relation between claims.** A stock connector (*In addition*, *Furthermore*, *Additionally*, *Moreover*) is the exception: never the same one twice within five sentences. A029 opens 14 sentences with *In addition* and 16 with *Furthermore* or *Additionally*; that is the pattern to avoid.
- **No promotional adjectives.** *Revolutionary*, *transformative*, *pivotal*, *comprehensive*, *crucial*, *novel* say nothing a reader can check; state what the evidence shows instead.
- **Every number comes from a record.** Counts from `review/prisma.json`, study values from `review/extraction.jsonl`, never recounted by hand.

## Disqualifiers

- Research questions that are not listed, or that differ in wording from `review/protocol.json`.
- A gap stated as a lack (*a notable deficiency in comprehensive analysis*) without naming the closest existing reviews and what each leaves out.
- A finding of an included study reported in the introduction: findings belong to the results.
- A contributions list whose count or order differs from the research questions it answers.
- A roadmap that names a section that does not exist, or skips one.
- A citation used as the subject of a sentence.

## Inputs

### External inputs

| Input | Unblocks |
|---|---|
| `problem-statement` — The gap is what existing reviews leave unanswered: scope, period, or method. | `intro-existing-reviews` |
| `gap` — The contributions are the research questions and what the review delivers for each. | `intro-objectives` |
| `skeleton` — The skeleton is the order of the sections that follow. | `intro-skeleton` |

### Internal chain

| Block | Depends on |
|---|---|
| `introduction.intro-existing-reviews` — The gap is what existing reviews leave unanswered: scope, period, or method. | `introduction.intro-rationale` |
| `introduction.intro-objectives` — The contributions are the research questions and what the review delivers for each. | `introduction.intro-existing-reviews` |
