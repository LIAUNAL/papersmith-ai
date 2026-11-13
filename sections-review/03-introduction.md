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

## Block `intro-rationale`

The problem-statement says why the topic needs a synthesis now. The field, its growth (publication counts from the search may
be cited from the results), the decisions practitioners or researchers face,
and why primary studies alone do not settle them. Cited from the literature,
never from the included studies' results.

## Block `intro-existing-reviews`

The gap is what existing reviews leave unanswered: scope, period, or method. Name the closest existing reviews (found with the same search
or a dedicated one), what each covered and when, and the joint gap that this
review closes. A review published after the last one cited here would
reopen the gap, so the search date is stated in the methods.

## Block `intro-objectives`

The contributions are the research questions and what the review delivers for each. State the objective in one sentence and list the research
questions (RQ1, RQ2, …) exactly as `review/protocol.json` words them, with the
PICOC elements (population, intervention, comparison, outcomes, context) when
the question is evaluative. Close with the contributions as a numbered list:
the map, the taxonomy, the comparison, the open challenges.

## Block `intro-skeleton`

The skeleton is the order of the sections that follow. One sentence per section.

## Sources

- `review/protocol.json` (research questions, PICOC).
- The existing reviews retrieved during identification.

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
