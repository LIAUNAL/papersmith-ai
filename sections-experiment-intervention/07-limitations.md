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

# Limitations (experiment and intervention line)

CONSORT 2025 item 30, ARRIVE 2.0 item 17. A limitation names a restriction of what the paper reports, and its likely direction and size.
It may be typeset as the last subsection of the discussion when the venue
prefers it.

**Extent** 180–450 words · 1 or 2 paragraphs

## Block `lim-reported`

The limitations are the sources of bias and imprecision in the reported results.
Each item names a decision or a boundary of the trial (who or what was
enrolled and how, the blinding that was not possible, the adherence achieved,
the losses to follow-up and the missing data, the achieved numbers against
the planned ones, the precision of the primary estimate, multiplicity),
states the bias or imprecision it can introduce, and gives its likely
direction and size and its consequence for a named result. A limitation is
never a feeling (*results should be interpreted with caution*), and an item
that cites the literature on the bias it names is preferred.

## Block `lim-protocol-deviations`

Every difference between the paper and the locked protocol: each amendment
with its reason (`study/protocol.lock.json`), a registration made after the
first enrolment with its reason, an allocation recorded again after a change,
a planned analysis not done, and the analyses the log labels exploratory. A
switch of primary outcome is stated here with the amendment that declared it;
without one, `paper_cli.py verify` fails and the paper is not ready.

## LIA house style

No paper of this line has been measured yet: the rules below carry the group's writing rules from the experimental and review lines to a trial or a controlled experiment, and the extent at the top of this contract stays the target. They read the records the line keeps: the locked protocol revision `protocol/study-protocol-<slug>-vNN.md` and `study/protocol.lock.json`, the ethics and registration records under `study/`, the operator's allocation record `study/allocation.json`, the data dictionaries and quality reports under `datasets/`, the analysis log `analysis/log.jsonl` and the flow counts `study/flow.json`.

**Measured size.** None yet; a CONSORT limitations paragraph of this extent names three to five restrictions, each with its likely effect.

**Human boundaries (every section of this line).**

- **No generated data.** The assistant never generates measurements or data, and never generates, reads out or alters the allocation sequence: every count, measurement, estimate and interval in the paper comes from the operator's records (`study/flow.json`, the datasets registered as own data, the outputs the analysis log hashes), never from a model, a simulation presented as an observation, or an imputation the analysis plan did not declare. The allocation list is the operator's file, bound by its sha256 in `study/allocation.json`; the paper states how the sequence was generated and concealed, never the sequence. A value without a record is left out and reported as missing.
- **Human decisions.** The decisions on ethics, consent, data collection and the choice of primary outcome stay human: the paper reports the operator's ethics record, the consent route, the allocation the operator recorded, how the operator delivered the intervention and collected the data, and the primary outcome of the locked protocol, and never proposes, changes or completes any of them.

**Writing (every section of this line).**

- **Sentences average 18–27 words.** One claim and its qualifier per sentence.
- **One voice.** First person plural for what the trial did (*we randomised*, *we measured*), past tense for every step that was run, present tense for what the results show.
- **Citations are numeric, in square brackets, and close the claim they support** (`[4]`, `[7,9]`, `[12–15]`). A citation is never the grammatical subject of a sentence.
- **Effects are estimated, not asserted.** A treatment effect is the between-group estimate of the primary analysis with its 95% confidence interval (*the mean difference was 4.2 points, 95% CI 1.1 to 7.3*), never a p-value alone, a within-group change or a verb that outruns the estimate (*transformed*, *proved*); an exploratory comparison is never written as an effect of the intervention.
- **Transitions come from the relation between claims.** A stock connector (*In addition*, *Furthermore*, *Additionally*, *Moreover*) is the exception: never the same one twice within five sentences.
- **No promotional adjectives.** *Revolutionary*, *transformative*, *pivotal*, *comprehensive*, *crucial*, *novel* say nothing a reader can check; state what the data show instead.
- **A table has at least three columns and three rows.** A two-column or two-row table is a grid with nothing to cross: counts or measures across categories become a bar chart, the shares of one whole (at most six parts) a pie chart, and one or two values go in the sentence. The chart is drawn by a script from the study's records, its provenance recorded with `paper_cli.py figure provenance`, and placed with `paper_cli.py place`.
- **Every number comes from a record.** Counts from `study/flow.json` or the operator's unit table, estimates from the outputs of the analysis log, planned values (sample size, outcomes, analysis plan) from the locked protocol revision, never recounted or retyped by hand.

## Disqualifiers

- A limitation that names no decision or boundary of the trial, or one without its likely effect on a reported result.
- Blinding not achieved, losses to follow-up or missing data left unsaid when they apply.
- An amendment, a retrospective registration or a planned analysis not done left unsaid.
- A limitation about something the paper does not report.

## Inputs

### External inputs

None: every block reads the study's records and the operator's declarations.

### Internal chain

None: no block of this section waits on another block.
