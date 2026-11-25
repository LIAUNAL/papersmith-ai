---
{
  "section": "abstract",
  "position": 2,
  "mode": {
    "value": "transposition",
    "source": {
      "file": "sections/02-abstract.md",
      "quote": "Every value in the abstract is copied with its uncertainty from the methods and the results; the abstract adds nothing."
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
            "quote": "The methods slot follows the methods section: the sample matrix or the model, the protocol, the instruments and their calibration, and how the uncertainty was evaluated."
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
            "quote": "The results slot follows the results section: the primary observable with its expanded uncertainty, its coverage factor and its unit."
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
    }
  ]
}
---

# Abstract (lab and simulation line)

GUM clause 7.2.1, paraphrased: the abstract reports the result of the primary
observable with its uncertainty and its unit. Every value in the abstract is copied with its uncertainty from the methods and the results; the abstract adds nothing.
One paragraph unless the venue asks for a structured abstract (Background,
Methods, Results, Conclusions); the venue's word limit wins over the extent
below.

**Extent** 200–300 words · one paragraph, or the venue's structured headings

## Slot `abs-background-objectives`

The background and objectives come from the study's contributions and its research question. One or two sentences: why the question matters and the objective, with
the prespecified hypothesis when the protocol states one.

## Slot `abs-methods`

The methods slot follows the methods section: the sample matrix or the model, the protocol, the instruments and their calibration, and how the uncertainty was evaluated. For a materials study, the synthesis or processing route and the
characterization techniques; for a modelling or simulation study, the model,
its solver and the known values it was checked against.

## Slot `abs-results`

The results slot follows the results section: the primary observable with its expanded uncertainty, its coverage factor and its unit. Written exactly as the results write it (the estimate, the expanded
uncertainty, the coverage factor and the unit), with the number of replicates
or the extent of the parameter grid. An exploratory result, when one is
mentioned, is called exploratory.

## Slot `abs-conclusions`

The limitations of what is reported come from the limitations section. One sentence on the main limitation and one on the interpretation, no
stronger than the uncertainty and the confirmatory analyses allow.

## LIA house style

No paper of this line has been measured yet: the rules below carry the group's writing rules from the experimental and observational lines to a laboratory or simulation study, and the extent at the top of this contract stays the target. They read the records the line keeps: the locked protocol revision `protocol/study-protocol-<slug>-vNN.md` and `study/protocol.lock.json`, the instrument records `study/instruments.json`, the raw data registrations `study/measurements.json`, the uncertainty budgets `study/uncertainty/<quantity>.json` and the analysis log `analysis/log.jsonl`.

**Measured size.** None yet; the venue's limit (often 250 words) decides.

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

- A value without its uncertainty or its unit, or one that differs from the results.
- A primary observable other than the one of the locked protocol.
- A simulated value presented as a measured one.
- An exploratory result presented as a confirmatory finding.
- A citation, or a claim the body does not make.

## Inputs

### External inputs

| Input | Unblocks |
|---|---|
| `contributions` — The background and objectives come from the study's contributions and its research question. | `abs-background-objectives` |
| `limitations` — The limitations of what is reported come from the limitations section. | `abs-conclusions` |

### Internal chain

| Block | Depends on |
|---|---|
| `abstract.abs-background-objectives` — The background and objectives come from the study's contributions and its research question. | `introduction.intro-objectives` |
| `abstract.abs-conclusions` — The limitations of what is reported come from the limitations section. | `limitations.lim-reported` |
