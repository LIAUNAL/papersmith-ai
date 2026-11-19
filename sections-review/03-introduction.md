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

The contributions are the research questions and what the review delivers for each. They are written as one proposal paragraph of 120–220 words, placed
immediately before the agenda paragraph, in running prose: no RQ1, RQ2 …
labels, no numbered or bulleted list, no bold lead-ins and no short lines of
innovation items. The paragraph illustrates three things in this order:

- **The idea**: what the review synthesizes and how, in the review's one voice
  (*this review examines …*, *we synthesize …*), naming the population and
  the context of the protocol's PICOC elements when the question is
  evaluative.
- **The novelty**: what the review does that the closest reviews named in
  `intro-existing-reviews` do not (scope, period, method), stated against
  that gap rather than with an adjective.
- **The key points**: each question of `review/protocol.json`, carried as a
  clause of the paragraph that keeps its meaning (*we ask which …, how …,
  and what …*), each tied to what the review delivers for it (the map, the
  taxonomy, the comparison, the open problems) in the same order as the
  protocol.

The research questions keep their RQ labels in `review/protocol.json` and the
methods; the introduction tells them as one argument, so the reader meets the
proposal before the roadmap instead of a checklist.

## Block `intro-skeleton`

The skeleton is the order of the sections that follow. One agenda paragraph after the proposal paragraph, one sentence per
section, opened by *The remainder of this paper is organized as follows:*.

## LIA house style

Measured on the group's MDPI review A029 (Cardona-Álvarez, Álvarez-Meza and Castellanos-Dominguez, *Computers* 2025, 14(5):194, doi:10.3390/computers14050194): about 9500 words of body, 168 references of which 102 are included studies, one figure (the PRISMA 2020 flow) and six tables. The ranges describe how the group writes a review; the extent at the top of this contract stays the target, and the disqualifiers below also correct what a PRISMA referee flags in A029.

**Measured size.** 637 words, seven citation markers, no list.

**The moves A029 makes and the review line keeps:** the field and its life cycle; the deficiency of the literature; the scope (the technologies the review covers); the objective; the roadmap. **What it changes:** A029 says it formulated research questions but never states them, and claims a *lack of comprehensive analysis* without naming a single earlier review. Here the research questions are carried by a proposal paragraph that keeps their meaning, ahead of the agenda paragraph, and the gap is measured against the reviews `scope` found. The review line does not adopt the experimental introduction's colon-and-items contribution list: a review's contribution is one argument, told in prose.

**Writing (every review section).**

- **Sentences average 18–27 words** (A029: median 22). One claim and its qualifier per sentence.
- **One voice.** First person plural for what the review did (*we searched*, *we grouped*), past tense for every step that was run, present tense for what the evidence shows (*the included studies agree*).
- **Citations are numeric, in square brackets, and close the claim they support.** A review cites groups of included studies: list them with commas (`[12,15,19]`), or as a range when they are consecutive in the reference list (`[36–39]`). A citation is never the grammatical subject of a sentence.
- **Transitions come from the relation between claims.** A stock connector (*In addition*, *Furthermore*, *Additionally*, *Moreover*) is the exception: never the same one twice within five sentences. A029 opens 14 sentences with *In addition* and 16 with *Furthermore* or *Additionally*; that is the pattern to avoid.
- **No promotional adjectives.** *Revolutionary*, *transformative*, *pivotal*, *comprehensive*, *crucial*, *novel* say nothing a reader can check; state what the evidence shows instead.
- **A table has at least three columns and three rows.** A two-column or two-row table is a grid with nothing to cross: counts or measures across categories become a bar chart, the shares of one whole (at most six parts) a pie chart, and one or two values go in the sentence. The chart is drawn by a script from the review's records, its provenance recorded with `paper_cli.py figure provenance`, and placed with `paper_cli.py place`.
- **Every number comes from a record.** Counts from `review/prisma.json`, study values from `review/extraction.jsonl`, never recounted by hand.

## Disqualifiers

- Research questions set apart under RQ1, RQ2 … labels, or as a numbered or bulleted list, in the introduction.
- Contributions or innovation points given as short lines (a numbered list, bullets, bold lead-ins, or a colon followed by items) instead of the proposal paragraph.
- No proposal paragraph before the agenda paragraph, or one that leaves out the idea, the novelty against the closest reviews, or the key points.
- A question of `review/protocol.json` missing from the proposal paragraph, carried with a different meaning, or one the protocol does not ask.
- A gap stated as a lack (*a notable deficiency in comprehensive analysis*) without naming the closest existing reviews and what each leaves out.
- A finding of an included study reported in the introduction: findings belong to the results.
- Key points whose order differs from the research questions they answer.
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
