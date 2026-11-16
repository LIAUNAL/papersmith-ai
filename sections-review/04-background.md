---
{
  "section": "background",
  "position": 4,
  "mode": {
    "value": "argument",
    "source": {
      "file": "sections/04-background.md",
      "quote": "The background gives the reader the vocabulary and the open problems the synthesis is organized against; it reports no included study's finding."
    }
  },
  "blocks": [
    {
      "id": "bg-definitions",
      "requires_facts": [
        {
          "value": "problem-statement",
          "source": {
            "file": "sections/04-background.md",
            "quote": "The problem-statement fixes which terms and which open problems the background must cover."
          }
        }
      ],
      "requires_declarations": [],
      "citations": "discovery",
      "after": [
        {
          "target": "introduction.intro-rationale",
          "source": {
            "file": "sections/04-background.md",
            "quote": "The problem-statement fixes which terms and which open problems the background must cover."
          }
        }
      ]
    },
    {
      "id": "bg-evolution",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "discovery",
      "optional": true
    },
    {
      "id": "bg-open-problems",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "discovery"
    }
  ]
}
---

# Background (review line)

The background gives the reader the vocabulary and the open problems the synthesis is organized against; it reports no included study's finding.
It sits between the introduction and the methods, as in the group's reviews,
and it is cited from textbooks, standards, surveys and seminal papers, not
from the included studies' results.

**Extent** 900–1800 words · 2 to 4 subsections

## Block `bg-definitions`

The problem-statement fixes which terms and which open problems the background must cover. A subsection of main definitions: each term the review uses, one
definition each with the source that holds it. A description list (`term:
definition [n]`) is the one place a review uses a list in running prose.
Define a term once; later sections use it without redefining it.

## Block `bg-evolution` (optional)

How the field reached its current state, in chronological order and in two
or three paragraphs: the generations of approaches, what each solved, and
what it left open. Omit it when the history adds nothing to the questions.

## Block `bg-open-problems`

The open problems the field faces, as a short list of named classes (for
example interoperability, real-time processing, compliance). These classes
are the ones the results classify the included studies against, with the
same names, so the reader meets each name here first.

## LIA house style

Measured on the group's MDPI review A029 (Cardona-Álvarez, Álvarez-Meza and Castellanos-Dominguez, *Computers* 2025, 14(5):194, doi:10.3390/computers14050194): about 9500 words of body, 168 references of which 102 are included studies, one figure (the PRISMA 2020 flow) and six tables. The ranges describe how the group writes a review; the extent at the top of this contract stays the target, and the disqualifiers below also correct what a PRISMA referee flags in A029.

**Measured size.** 1522 words in four subsections (main definitions, historical evolution, main issues, automation), the definitions as a bulleted glossary of seven terms, each with one citation.

**The moves A029 makes and the review line keeps:** definitions first, then evolution, then the issues the rest of the paper is organized around. **What it changes:** the open problems named here become the problem classes of the results with the same words; A029 names its issues in Section 2.3 and classifies the studies by a differently worded list in Table 3.

**Writing (every review section).**

- **Sentences average 18–27 words** (A029: median 22). One claim and its qualifier per sentence.
- **One voice.** First person plural for what the review did (*we searched*, *we grouped*), past tense for every step that was run, present tense for what the evidence shows (*the included studies agree*).
- **Citations are numeric, in square brackets, and close the claim they support.** A review cites groups of included studies: list them with commas (`[12,15,19]`), or as a range when they are consecutive in the reference list (`[36–39]`). A citation is never the grammatical subject of a sentence.
- **Transitions come from the relation between claims.** A stock connector (*In addition*, *Furthermore*, *Additionally*, *Moreover*) is the exception: never the same one twice within five sentences. A029 opens 14 sentences with *In addition* and 16 with *Furthermore* or *Additionally*; that is the pattern to avoid.
- **No promotional adjectives.** *Revolutionary*, *transformative*, *pivotal*, *comprehensive*, *crucial*, *novel* say nothing a reader can check; state what the evidence shows instead.
- **Every number comes from a record.** Counts from `review/prisma.json`, study values from `review/extraction.jsonl`, never recounted by hand.

## Disqualifiers

- A definition without a citation.
- A term defined twice, or defined differently in another section.
- A finding of an included study: the background describes the field, the results synthesize the studies.
- An open problem that the results never use as a class, or a class of the results that the background never names.
- A subsection unrelated to any research question.

## Inputs

### External inputs

| Input | Unblocks |
|---|---|
| `problem-statement` — The problem-statement fixes which terms and which open problems the background must cover. | `bg-definitions` |

### Internal chain

| Block | Depends on |
|---|---|
| `background.bg-definitions` — The problem-statement fixes which terms and which open problems the background must cover. | `introduction.intro-rationale` |
