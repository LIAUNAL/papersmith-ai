---
{
  "section": "limitations",
  "position": 8,
  "mode": {
    "value": "argument",
    "source": {
      "file": "sections/08-limitations.md",
      "quote": "Two kinds of limitation, kept apart: those of the evidence and those of the review process."
    }
  },
  "blocks": [
    {
      "id": "lim-evidence",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none",
      "produces_facts": [
        {
          "value": "limitations",
          "source": {
            "file": "sections/08-limitations.md",
            "quote": "Two kinds of limitation, kept apart: those of the evidence and those of the review process."
          }
        }
      ]
    },
    {
      "id": "lim-review-process",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none"
    }
  ]
}
---

# Limitations (review line)

PRISMA 2020 items 23b and 23c. Two kinds of limitation, kept apart: those of the evidence and those of the review process.
It may be typeset as the last subsection of the discussion, as the group does.

**Extent** 120–400 words · 1 or 2 paragraphs

## Block `lim-evidence`

Risk of bias across the included studies, heterogeneity of designs and
metrics, missing reporting, small samples, and publication bias.

## Block `lim-review-process`

Sources not searched, language and date limits, grey literature excluded,
single-reviewer steps, the use of a language model as a screener, and any
deviation from the protocol. Each with its likely effect on the conclusions.

## LIA house style

Measured on the group's MDPI review A029 (Cardona-Álvarez, Álvarez-Meza and Castellanos-Dominguez, *Computers* 2025, 14(5):194, doi:10.3390/computers14050194): about 9500 words of body, 168 references of which 102 are included studies, one figure (the PRISMA 2020 flow) and six tables. The ranges describe how the group writes a review; the extent at the top of this contract stays the target, and the disqualifiers below also correct what a PRISMA referee flags in A029.

**Measured size.** About 170 words in one paragraph closing the discussion: no risk-of-bias assessment, no certainty grading (GRADE), a narrative synthesis, and a protocol not registered.

**What A029 does and the review line keeps:** an honest list of what the process did not do. **What it changes:** each limitation now states its likely effect on the conclusions.

**Writing (every review section).**

- **Sentences average 18–27 words** (A029: median 22). One claim and its qualifier per sentence.
- **One voice.** First person plural for what the review did (*we searched*, *we grouped*), past tense for every step that was run, present tense for what the evidence shows (*the included studies agree*).
- **Citations are numeric, in square brackets, and close the claim they support.** A review cites groups of included studies: list them with commas (`[12,15,19]`), or as a range when they are consecutive in the reference list (`[36–39]`). A citation is never the grammatical subject of a sentence.
- **Transitions come from the relation between claims.** A stock connector (*In addition*, *Furthermore*, *Additionally*, *Moreover*) is the exception: never the same one twice within five sentences. A029 opens 14 sentences with *In addition* and 16 with *Furthermore* or *Additionally*; that is the pattern to avoid.
- **No promotional adjectives.** *Revolutionary*, *transformative*, *pivotal*, *comprehensive*, *crucial*, *novel* say nothing a reader can check; state what the evidence shows instead.
- **Every number comes from a record.** Counts from `review/prisma.json`, study values from `review/extraction.jsonl`, never recounted by hand.

## Disqualifiers

- A limitation without its likely effect on the conclusions.
- An unregistered protocol, a single-reviewer step, a language-model screener or an unsearched major database left unsaid when it applies.
- A limitation of the evidence mixed with one of the review process in the same sentence.

## Inputs

### External inputs

None: every block reads the records under `review/` and the operator's declarations.

### Internal chain

None: no block of this section waits on another block.
