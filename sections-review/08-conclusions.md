---
{
  "section": "conclusions",
  "position": 8,
  "mode": {
    "value": "transposition",
    "source": {
      "file": "sections/08-conclusions.md",
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
            "file": "sections/08-conclusions.md",
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
            "file": "sections/08-conclusions.md",
            "quote": "The contributions — the answer to each research question — in the order of the introduction."
          }
        },
        {
          "target": "introduction.intro-objectives",
          "source": {
            "file": "sections/08-conclusions.md",
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
            "file": "sections/08-conclusions.md",
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
            "file": "sections/08-conclusions.md",
            "quote": "The limitations bound every conclusion; the future directions come from the discussion."
          }
        },
        {
          "target": "limitations.lim-evidence",
          "source": {
            "file": "sections/08-conclusions.md",
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

## Block `concl-answers`

The contributions — the answer to each research question — in the order of the introduction. One or two sentences each.

## Block `concl-future`

The limitations bound every conclusion; the future directions come from the discussion. Three to five directions, each traceable to a challenge of the
discussion.

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
