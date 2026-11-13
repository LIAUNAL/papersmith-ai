---
{
  "section": "abstract",
  "position": 2,
  "mode": {
    "value": "transposition",
    "source": {
      "file": "sections/02-abstract.md",
      "quote": "Every number in the abstract is copied from the methods and the results; the abstract adds nothing."
    }
  },
  "blocks": [
    {
      "id": "abs-background-objectives",
      "requires_facts": [
        {
          "value": "contributions",
          "source": {
            "file": "sections/02-abstract.md",
            "quote": "The background and objectives come from the review's contributions and research questions."
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none",
      "after": [
        {
          "target": "introduction.intro-objectives",
          "source": {
            "file": "sections/02-abstract.md",
            "quote": "The background and objectives come from the review's contributions and research questions."
          }
        }
      ]
    },
    {
      "id": "abs-methods",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none",
      "after": [
        {
          "target": "methods",
          "source": {
            "file": "sections/02-abstract.md",
            "quote": "The methods slot follows the methods section: eligibility criteria, information sources with their last search date, risk-of-bias tool and synthesis method."
          }
        }
      ]
    },
    {
      "id": "abs-results",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none",
      "after": [
        {
          "target": "results",
          "source": {
            "file": "sections/02-abstract.md",
            "quote": "The results slot follows the results section: the number of included studies and records, their main characteristics and the main result of each research question."
          }
        }
      ]
    },
    {
      "id": "abs-discussion",
      "requires_facts": [
        {
          "value": "limitations",
          "source": {
            "file": "sections/02-abstract.md",
            "quote": "The limitations of the evidence come from the limitations section."
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none",
      "after": [
        {
          "target": "limitations.lim-evidence",
          "source": {
            "file": "sections/02-abstract.md",
            "quote": "The limitations of the evidence come from the limitations section."
          }
        }
      ]
    },
    {
      "id": "abs-other",
      "requires_facts": [],
      "requires_declarations": [
        {
          "value": "review-registration",
          "source": {
            "file": "sections/02-abstract.md",
            "quote": "The review-registration names the registry and the record, or states that the protocol was not registered."
          }
        }
      ],
      "citations": "none"
    }
  ]
}
---

# Abstract (review line)

Structured after the PRISMA 2020 for Abstracts checklist (12 items). Every
number in the abstract is copied from the methods and the results; the
abstract adds nothing. One paragraph unless the venue asks for a structured
abstract (Background, Methods, Results, Conclusions); the venue's word limit
wins over the extent below (MDPI: 200 words).

**Extent** 150–250 words · one paragraph

## Slot `abs-background-objectives` (items 1-2)

The background and objectives come from the review's contributions and research questions. One or two sentences: why the question matters and the explicit
objective or research questions.

## Slot `abs-methods` (items 3-6)

The methods slot follows the methods section: eligibility criteria, information sources with their last search date, risk-of-bias tool and synthesis method.
One or two sentences: "Following PRISMA 2020, we searched <sources> up to
<date> and included <n> studies …".

## Slot `abs-results` (items 7-9)

The results slot follows the results section: the number of included studies and records, their main characteristics and the main result of each research question.
One sentence per theme of the synthesis, each stating a finding, not a topic.

## Slot `abs-discussion` (items 10-11)

The limitations of the evidence come from the limitations section. One sentence on the limitations of the evidence (risk of bias,
inconsistency, imprecision) and one on the interpretation and implications.

## Slot `abs-other` (items 12-13)

Funding (from the back matter) and registration. The review-registration names the registry and the record, or states that the protocol was not registered.

## LIA house style

Measured on the group's MDPI review A029 (Cardona-Álvarez, Álvarez-Meza and Castellanos-Dominguez, *Computers* 2025, 14(5):194, doi:10.3390/computers14050194): about 9500 words of body, 168 references of which 102 are included studies, one figure (the PRISMA 2020 flow) and six tables. The ranges describe how the group writes a review; the extent at the top of this contract stays the target, and the disqualifiers below also correct what a PRISMA referee flags in A029.

**Measured size.** 182 words, one paragraph, eight sentences, no number and no citation.

**What A029 does and the review line keeps:** one unstructured paragraph that names the scope, the technologies and the challenges. **What it changes:** A029's abstract reports no method and no count, and closes on calls to action (*calls for innovative research*, *advocates for interdisciplinary approaches*); a PRISMA abstract states the sources, the number of included studies and one finding per theme.

**Writing (every review section).**

- **Sentences average 18–27 words** (A029: median 22). One claim and its qualifier per sentence.
- **One voice.** First person plural for what the review did (*we searched*, *we grouped*), past tense for every step that was run, present tense for what the evidence shows (*the included studies agree*).
- **Citations are numeric, in square brackets, and close the claim they support.** A review cites groups of included studies: list them with commas (`[12,15,19]`), or as a range when they are consecutive in the reference list (`[36–39]`). A citation is never the grammatical subject of a sentence.
- **Transitions come from the relation between claims.** A stock connector (*In addition*, *Furthermore*, *Additionally*, *Moreover*) is the exception: never the same one twice within five sentences. A029 opens 14 sentences with *In addition* and 16 with *Furthermore* or *Additionally*; that is the pattern to avoid.
- **No promotional adjectives.** *Revolutionary*, *transformative*, *pivotal*, *comprehensive*, *crucial*, *novel* say nothing a reader can check; state what the evidence shows instead.
- **Every number comes from a record.** Counts from `review/prisma.json`, study values from `review/extraction.jsonl`, never recounted by hand.

## Disqualifiers

- No number of included studies, or a number that differs from `review/prisma.json`.
- No mention of the method (PRISMA 2020 and the sources searched).
- A sentence that announces a topic (*the paper examines the challenges*) instead of stating a finding.
- A call to action with no finding behind it (*calls for*, *advocates for*, *underscores the urgent need*).
- A citation, or a claim the body does not make.

## Inputs

### External inputs

| Input | Unblocks |
|---|---|
| `contributions` — The background and objectives come from the review's contributions and research questions. | `abs-background-objectives` |
| `limitations` — The limitations of the evidence come from the limitations section. | `abs-discussion` |
| `review-registration` — The review-registration names the registry and the record, or states that the protocol was not registered. | `abs-other` |

### Internal chain

| Block | Depends on |
|---|---|
| `abstract.abs-background-objectives` — The background and objectives come from the review's contributions and research questions. | `introduction.intro-objectives` |
| `abstract.abs-discussion` — The limitations of the evidence come from the limitations section. | `limitations.lim-evidence` |
