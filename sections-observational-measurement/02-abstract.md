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
            "quote": "The background and objectives come from the study's contributions and its research question."
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
            "quote": "The background and objectives come from the study's contributions and its research question."
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
            "quote": "The methods slot follows the methods section: design, setting, participants, the primary outcome and how it was measured, and the main analysis."
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
            "quote": "The results slot follows the results section: the number of participants analysed and the main estimate of the primary outcome with its precision."
          }
        }
      ]
    },
    {
      "id": "abs-conclusions",
      "requires_facts": [
        {
          "value": "limitations",
          "source": {
            "file": "sections/02-abstract.md",
            "quote": "The limitations of what is reported come from the limitations section."
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none",
      "after": [
        {
          "target": "limitations.lim-reported",
          "source": {
            "file": "sections/02-abstract.md",
            "quote": "The limitations of what is reported come from the limitations section."
          }
        }
      ]
    },
    {
      "id": "abs-registration",
      "requires_facts": [],
      "requires_declarations": [
        {
          "value": "study-registration",
          "source": {
            "file": "sections/02-abstract.md",
            "quote": "The study-registration names the registry and the record, or states that the study was not registered."
          }
        }
      ],
      "citations": "none"
    }
  ]
}
---

# Abstract (observational and measurement studies line)

STROBE item 1b, STARD 2015 item 2 (structured summary) and COSMIN 2.0 items
A1 to A5. Every number in the abstract is copied from the methods and the results; the abstract adds nothing.
One paragraph unless the venue asks for a structured abstract (Background,
Methods, Results, Conclusions); the venue's word limit wins over the extent
below.

**Extent** 200–300 words · one paragraph, or the venue's structured headings

## Slot `abs-background-objectives`

The background and objectives come from the study's contributions and its research question. One or two sentences: why the question matters and the objective, with the
prespecified hypothesis when the protocol states one.

## Slot `abs-methods`

The methods slot follows the methods section: design, setting, participants, the primary outcome and how it was measured, and the main analysis. For a diagnostic accuracy study, the index test and the reference standard; for a
measurement-instrument study, the instrument and the measurement properties
evaluated.

## Slot `abs-results`

The results slot follows the results section: the number of participants analysed and the main estimate of the primary outcome with its precision. Every estimate carries its interval (*95% CI*), never a p-value alone, and an
exploratory result, when one is mentioned, is called exploratory.

## Slot `abs-conclusions`

The limitations of what is reported come from the limitations section. One
sentence on the main limitation and one on the interpretation, no stronger
than the design and the confirmatory analyses allow.

## Slot `abs-registration`

The study-registration names the registry and the record, or states that the study was not registered. A registration dated after the first enrolment is
called retrospective.

## LIA house style

No paper of this line has been measured yet: the rules below carry the group's writing rules from the experimental and review lines to an observational or measurement study, and the extent at the top of this contract stays the target. They read the records the line keeps: the locked protocol revision `protocol/study-protocol-<slug>-vNN.md` and `study/protocol.lock.json`, the ethics and registration records under `study/`, the data dictionaries and quality reports under `datasets/`, the analysis log `analysis/log.jsonl` and the participant flow counts `study/flow.json`.

**Measured size.** None yet; the venue's limit (often 250 words) decides.

**Human boundaries (every section of this line).**

- **No generated data.** The assistant never generates measurements or data: every count, measurement, estimate and interval in the paper comes from the operator's records (`study/flow.json`, the datasets registered as own data, the outputs the analysis log hashes), never from a model, a simulation presented as an observation, or an imputation the analysis plan did not declare. A value without a record is left out and reported as missing.
- **Human decisions.** The decisions on ethics, consent, data collection and the choice of primary outcome stay human: the paper reports the operator's ethics record, the consent route, how the operator collected the data and the primary outcome of the locked protocol, and never proposes, changes or completes any of them.

**Writing (every section of this line).**

- **Sentences average 18–27 words.** One claim and its qualifier per sentence.
- **One voice.** First person plural for what the study did (*we enrolled*, *we measured*), past tense for every step that was run, present tense for what the results show.
- **Citations are numeric, in square brackets, and close the claim they support** (`[4]`, `[7,9]`, `[12–15]`). A citation is never the grammatical subject of a sentence.
- **Associations stay associations.** An observational estimate is written as an association (*was associated with*, *was higher in*), never as an effect (*caused*, *improved*, *led to*), unless the locked analysis plan names a causal estimand and the adjustment set that supports it.
- **Transitions come from the relation between claims.** A stock connector (*In addition*, *Furthermore*, *Additionally*, *Moreover*) is the exception: never the same one twice within five sentences.
- **No promotional adjectives.** *Revolutionary*, *transformative*, *pivotal*, *comprehensive*, *crucial*, *novel* say nothing a reader can check; state what the data show instead.
- **A table has at least three columns and three rows.** A two-column or two-row table is a grid with nothing to cross: counts or measures across categories become a bar chart, the shares of one whole (at most six parts) a pie chart, and one or two values go in the sentence. The chart is drawn by a script from the study's records, its provenance recorded with `paper_cli.py figure provenance`, and placed with `paper_cli.py place`.
- **Every number comes from a record.** Counts from `study/flow.json`, estimates from the outputs of the analysis log, planned values (sample size, outcomes, analysis plan) from the locked protocol revision, never recounted or retyped by hand.

## Disqualifiers

- No number of participants analysed, or a number that differs from `study/flow.json`.
- A primary estimate without its interval, or a p-value given in place of an estimate.
- A primary outcome other than the one of the locked protocol.
- An exploratory result presented as a confirmatory finding.
- A causal claim for an observational design whose analysis plan names no causal estimand.
- A citation, or a claim the body does not make.

## Inputs

### External inputs

| Input | Unblocks |
|---|---|
| `contributions` — The background and objectives come from the study's contributions and its research question. | `abs-background-objectives` |
| `limitations` — The limitations of what is reported come from the limitations section. | `abs-conclusions` |
| `study-registration` — The study-registration names the registry and the record, or states that the study was not registered. | `abs-registration` |

### Internal chain

| Block | Depends on |
|---|---|
| `abstract.abs-background-objectives` — The background and objectives come from the study's contributions and its research question. | `introduction.intro-objectives` |
| `abstract.abs-conclusions` — The limitations of what is reported come from the limitations section. | `limitations.lim-reported` |
