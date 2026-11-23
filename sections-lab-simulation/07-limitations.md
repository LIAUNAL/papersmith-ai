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
            "quote": "The limitations are the sources of bias and uncertainty in the reported results."
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

# Limitations (lab and simulation line)

A limitation names a restriction of what the paper reports, and its likely direction and size.
It may be typeset as the last subsection of the discussion when the venue
prefers it.

**Extent** 180–450 words · 1 or 2 paragraphs

## Block `lim-reported`

The limitations are the sources of bias and uncertainty in the reported results. Each item names a decision or a boundary of the study (the samples
made and how, the instruments and their calibration, the number of replicates
against the planned one, the parameter range covered, the model assumptions and
the numerical settings), states the bias or the uncertainty it can introduce,
and gives its likely direction and size and its consequence for a named
result, using the dominant component of the budget when it applies. A
limitation is never a feeling (*results should be interpreted with caution*),
and an item that cites the literature on the effect it names is preferred.

## Block `lim-protocol-deviations`

Every difference between the paper and the locked protocol: each amendment
with its reason (`study/protocol.lock.json`), an instrument used past its
calibration due date with the reason the operator recorded, a planned sweep or
analysis not done, and the analyses the log labels exploratory. A switch of
primary observable is stated here with the amendment that declared it; without
one, `paper_cli.py verify` fails and the paper is not ready.

## LIA house style

No paper of this line has been measured yet: the rules below carry the group's writing rules from the experimental and observational lines to a laboratory or simulation study, and the extent at the top of this contract stays the target. They read the records the line keeps: the locked protocol revision `protocol/study-protocol-<slug>-vNN.md` and `study/protocol.lock.json`, the instrument records `study/instruments.json`, the raw data registrations `study/measurements.json`, the uncertainty budgets `study/uncertainty/<quantity>.json` and the analysis log `analysis/log.jsonl`.

**Measured size.** None yet; the group's method papers state three to five limitation items in one paragraph.

**Human boundaries (every section of this line).**

- **No generated data.** The assistant never generates measurements or data: every measured value, simulated output, uncertainty and estimate in the paper comes from the operator's records (the raw data files registered in `study/measurements.json`, the budgets under `study/uncertainty/`, the outputs the analysis log hashes, the runs of the operator's model code among them), never from a value typed by hand, a run the operator did not plan, or a simulation presented as a measurement. A value without a record is left out and reported as missing.
- **Human decisions.** The decisions on the sample matrix or the model, the parameter grid, the instruments and their calibration, data collection and the choice of the primary observable stay human: the paper reports the locked protocol and the operator's records and never proposes, changes or completes any of them.

**Writing (every section of this line).**

- **Sentences average 18–27 words.** One claim and its qualifier per sentence.
- **One voice.** First person plural for what the study did (*we deposited*, *we measured*, *we simulated*), past tense for every step that was run, present tense for what the results show.
- **Citations are numeric, in square brackets, and close the claim they support** (`[4]`, `[7,9]`, `[12–15]`). A citation is never the grammatical subject of a sentence.
- **A value carries its uncertainty.** Every measured or computed value is written with its expanded uncertainty, its coverage factor and its unit; the uncertainty keeps at most two significant digits and the value is rounded to the same decimal place.
- **A simulation is not a measurement.** A simulated value is called simulated or computed, never measured, and a model output is compared with a measurement only through both uncertainties.
- **Transitions come from the relation between claims.** A stock connector (*In addition*, *Furthermore*, *Additionally*, *Moreover*) is the exception: never the same one twice within five sentences.
- **No promotional adjectives.** *Revolutionary*, *transformative*, *pivotal*, *comprehensive*, *crucial*, *novel* say nothing a reader can check; state what the data show instead.
- **A table has at least three columns and three rows.** A two-column or two-row table is a grid with nothing to cross: values across conditions become a plot with error bars, and one or two values go in the sentence. The plot is drawn by a script from the study's records, its provenance recorded with `paper_cli.py figure provenance`, and placed with `paper_cli.py place`.
- **Every number comes from a record.** Values and uncertainties from `study/uncertainty/<quantity>.json`, instrument data from `study/instruments.json`, fits and sweeps from the outputs of the analysis log, planned values (replicates, parameter grid, observables, analysis plan) from the locked protocol revision, never recounted or retyped by hand.

## Disqualifiers

- A limitation that names no decision or boundary of the study, or one without its likely effect on a reported result.
- A calibration past due, a missing uncertainty component or a convergence not reached left unsaid when it applies.
- An amendment or a planned sweep or analysis not done left unsaid.
- A limitation about something the paper does not report.

## Inputs

### External inputs

None: every block reads the study's records and the operator's declarations.

### Internal chain

None: no block of this section waits on another block.
