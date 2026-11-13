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
abstract adds nothing. 200 to 300 words unless the venue says otherwise;
headed (Background, Methods, Results, Conclusions) when the venue asks for a
structured abstract, one paragraph otherwise.

## Slot `abs-background-objectives` (items 1-2)

The background and objectives come from the review's contributions and research questions. One or two sentences: why the question matters and the explicit
objective or research questions.

## Slot `abs-methods` (items 3-6)

The methods slot follows the methods section: eligibility criteria, information sources with their last search date, risk-of-bias tool and synthesis method.

## Slot `abs-results` (items 7-9)

The results slot follows the results section: the number of included studies and records, their main characteristics and the main result of each research question.

## Slot `abs-discussion` (items 10-11)

The limitations of the evidence come from the limitations section. One sentence on the limitations of the evidence (risk of bias,
inconsistency, imprecision) and one on the interpretation and implications.

## Slot `abs-other` (items 12-13)

Funding (from the back matter) and registration. The review-registration names the registry and the record, or states that the protocol was not registered.

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
