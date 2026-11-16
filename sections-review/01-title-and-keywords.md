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

**Extent** 10–20 words · keywords 4–6

## Block `title`

The contributions of the review — what it maps, compares or concludes — decide the title. The title states the topic (the population, phenomenon or technology
reviewed), the scope that bounds it (domain, period when it matters) and the
review type, in this order: "<topic> in <scope>: a systematic review". No
claim of novelty, no question form, no acronym that the abstract does not
expand.

## Block `keywords`

The keyword-bounds and the classification-line come from the venue. Four to six keywords, none repeating a word of the title, the review
type included as one of them ("systematic review" or "PRISMA").

## LIA house style

Measured on the group's MDPI review A029 (Cardona-Álvarez, Álvarez-Meza and Castellanos-Dominguez, *Computers* 2025, 14(5):194, doi:10.3390/computers14050194): about 9500 words of body, 168 references of which 102 are included studies, one figure (the PRISMA 2020 flow) and six tables. The ranges describe how the group writes a review; the extent at the top of this contract stays the target, and the disqualifiers below also correct what a PRISMA referee flags in A029.

**Measured size.** Title 10 words, in two parts joined by a colon (topic: *Insights and Trends*); five keywords.

**What A029 does and the review line keeps:** a two-part title whose first part names the topic and the technologies. **What it changes:** A029's title opens on a promotional verb (*Revolutionizing*) and leaves the review type to the journal's article-type label; PRISMA 2020 asks the title itself to say *systematic review*.

**Writing (every review section).**

- **Sentences average 18–27 words** (A029: median 22). One claim and its qualifier per sentence.
- **One voice.** First person plural for what the review did (*we searched*, *we grouped*), past tense for every step that was run, present tense for what the evidence shows (*the included studies agree*).
- **Citations are numeric, in square brackets, and close the claim they support.** A review cites groups of included studies: list them with commas (`[12,15,19]`), or as a range when they are consecutive in the reference list (`[36–39]`). A citation is never the grammatical subject of a sentence.
- **Transitions come from the relation between claims.** A stock connector (*In addition*, *Furthermore*, *Additionally*, *Moreover*) is the exception: never the same one twice within five sentences. A029 opens 14 sentences with *In addition* and 16 with *Furthermore* or *Additionally*; that is the pattern to avoid.
- **No promotional adjectives.** *Revolutionary*, *transformative*, *pivotal*, *comprehensive*, *crucial*, *novel* say nothing a reader can check; state what the evidence shows instead.
- **Every number comes from a record.** Counts from `review/prisma.json`, study values from `review/extraction.jsonl`, never recounted by hand.

## Disqualifiers

- A title that does not name the review type (systematic review, scoping review, mapping study, meta-analysis).
- A promotional or evaluative word in the title (*Revolutionizing*, *Transforming*, *Novel*).
- A keyword that repeats a word of the title.
- An acronym in the title that the abstract does not expand.

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
