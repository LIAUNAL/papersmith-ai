---
{
  "section": "title-and-keywords",
  "position": 1,
  "mode": {
    "value": "transposition",
    "source": {
      "file": "sections/01-title-and-keywords.md",
      "quote": "The title names the report as a systematic review."
    }
  },
  "blocks": [
    {
      "id": "title",
      "requires_facts": [
        {
          "value": "contributions",
          "source": {
            "file": "sections/01-title-and-keywords.md",
            "quote": "The contributions of the review — what it maps, compares or concludes — decide the title."
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none",
      "after": [
        {
          "target": "introduction.intro-objectives",
          "source": {
            "file": "sections/01-title-and-keywords.md",
            "quote": "The contributions of the review — what it maps, compares or concludes — decide the title."
          }
        }
      ]
    },
    {
      "id": "keywords",
      "requires_facts": [],
      "requires_declarations": [
        {
          "value": "keyword-bounds",
          "source": {
            "file": "sections/01-title-and-keywords.md",
            "quote": "The keyword-bounds and the classification-line come from the venue."
          }
        },
        {
          "value": "classification-line",
          "source": {
            "file": "sections/01-title-and-keywords.md",
            "quote": "The keyword-bounds and the classification-line come from the venue."
          }
        }
      ],
      "citations": "none"
    }
  ]
}
---

# Title and Keywords (review line)

PRISMA 2020 item 1: The title names the report as a systematic review. A
scoping review, a meta-analysis or a systematic mapping says so instead, with
the same words the methods use.

## Block `title`

The contributions of the review — what it maps, compares or concludes — decide the title. The title states the topic (the population, phenomenon or technology
reviewed), the scope that bounds it (domain, period when it matters) and the
review type, in this order: "<topic> in <scope>: a systematic review". No
claim of novelty, no question form, no acronym that the abstract does not
expand. 10 to 20 words.

## Block `keywords`

The keyword-bounds and the classification-line come from the venue. Four to six keywords, none repeating a word of the title, the review
type included as one of them ("systematic review" or "PRISMA").

## Sources

- `review/protocol.json`: the research questions and the PICOC elements, which
  fix the topic and scope words.

## Inputs

### External inputs

| Input | Unblocks |
|---|---|
| `contributions` — The contributions of the review — what it maps, compares or concludes — decide the title. | `title` |
| `keyword-bounds` — The keyword-bounds and the classification-line come from the venue. | `keywords` |
| `classification-line` — The keyword-bounds and the classification-line come from the venue. | `keywords` |

### Internal chain

| Block | Depends on |
|---|---|
| `title-and-keywords.title` — The contributions of the review — what it maps, compares or concludes — decide the title. | `introduction.intro-objectives` |
