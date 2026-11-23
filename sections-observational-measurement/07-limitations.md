---
{
  "section": "limitations",
  "position": 7,
  "mode": {
    "value": "argument",
    "source": {
      "file": "sections/07-limitations.md",
      "quote": "A limitation names a restriction of what the paper reports, and its likely direction and size."
    }
  },
  "blocks": [
    {
      "id": "lim-reported",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "resolution",
      "produces_facts": [
        {
          "value": "limitations",
          "source": {
            "file": "sections/07-limitations.md",
            "quote": "The limitations are the sources of bias and imprecision in the reported results."
          }
        }
      ]
    },
    {
      "id": "lim-protocol-deviations",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none"
    }
  ]
}
---

# Limitations (observational and measurement studies line)

STROBE item 19, STARD 2015 item 26, COSMIN 2.0 limitations items. A limitation names a restriction of what the paper reports, and its likely direction and size.
It may be typeset as the last subsection of the discussion when the venue
prefers it.

**Extent** 180–450 words · 1 or 2 paragraphs

## Block `lim-reported`

The limitations are the sources of bias and imprecision in the reported results.
Each item names a decision or a boundary of the study (who was recruited and
how, what was measured and with which instrument, which confounders were not
measured, how much data were missing, how many were lost to follow-up, the
achieved size against the planned one), states the bias or imprecision it can
introduce, and gives its likely direction and size and its consequence for a
named result. A limitation is never a feeling (*results should be interpreted
with caution*), and an item that cites the literature on the bias it names is
preferred.

## Block `lim-protocol-deviations`

Every difference between the paper and the locked protocol: each amendment
with its reason (`study/protocol.lock.json`), a registration made after the
first enrolment, a planned analysis not done, and the analyses the log labels
exploratory. A switch of primary outcome is stated here with the amendment
that declared it; without one, `paper_cli.py verify` fails and the paper is
not ready.

## LIA house style

No paper of this line has been measured yet: the rules below carry the group's writing rules from the experimental and review lines to an observational or measurement study, and the extent at the top of this contract stays the target. They read the records the line keeps: the locked protocol revision `protocol/study-protocol-<slug>-vNN.md` and `study/protocol.lock.json`, the ethics and registration records under `study/`, the data dictionaries and quality reports under `datasets/`, the analysis log `analysis/log.jsonl` and the participant flow counts `study/flow.json`.

**Measured size.** None yet; the group's method papers state three to five limitation items in one paragraph.

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

- A limitation that names no decision or boundary of the study, or one without its likely effect on a reported result.
- Unmeasured confounding, selection, missing data or loss to follow-up left unsaid when it applies.
- An amendment, a retrospective registration or a planned analysis not done left unsaid.
- A limitation about something the paper does not report.

## Inputs

### External inputs

None: every block reads the study's records and the operator's declarations.

### Internal chain

None: no block of this section waits on another block.
