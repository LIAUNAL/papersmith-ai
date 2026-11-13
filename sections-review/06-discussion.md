---
{
  "section": "discussion",
  "position": 6,
  "mode": {
    "value": "argument",
    "source": {
      "file": "sections/06-discussion.md",
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
            "file": "sections/06-discussion.md",
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
            "file": "sections/06-discussion.md",
            "quote": "The contributions are revisited one by one with what the evidence supports."
          }
        },
        {
          "target": "introduction.intro-objectives",
          "source": {
            "file": "sections/06-discussion.md",
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
            "file": "sections/06-discussion.md",
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
            "file": "sections/06-discussion.md",
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

## Block `d-principal-findings`

The contributions are revisited one by one with what the evidence supports. One paragraph per research question, interpreting the
pattern, never restating the tables.

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
