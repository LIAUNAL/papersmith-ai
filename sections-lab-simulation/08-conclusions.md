---
{
  "section": "conclusions",
  "position": 8,
  "mode": {
    "value": "transposition",
    "source": {
      "file": "sections/08-conclusions.md",
      "quote": "Conclusions add nothing: every claim already exists earlier in the paper."
    }
  },
  "blocks": [
    {
      "id": "concl-answers",
      "requires_facts": [
        {
          "value": "contributions",
          "source": {
            "file": "sections/08-conclusions.md",
            "quote": "The contributions are answered in the order of the objectives, each by its confirmatory result."
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none",
      "after": [
        {
          "target": "discussion",
          "source": {
            "file": "sections/08-conclusions.md",
            "quote": "The contributions are answered in the order of the objectives, each by its confirmatory result."
          }
        },
        {
          "target": "introduction.intro-objectives",
          "source": {
            "file": "sections/08-conclusions.md",
            "quote": "The contributions are answered in the order of the objectives, each by its confirmatory result."
          }
        }
      ]
    },
    {
      "id": "concl-future",
      "requires_facts": [
        {
          "value": "limitations",
          "source": {
            "file": "sections/08-conclusions.md",
            "quote": "The limitations bound every conclusion; each future direction answers one of them."
          }
        }
      ],
      "requires_declarations": [],
      "citations": "resolution",
      "after": [
        {
          "target": "limitations",
          "source": {
            "file": "sections/08-conclusions.md",
            "quote": "The limitations bound every conclusion; each future direction answers one of them."
          }
        },
        {
          "target": "limitations.lim-reported",
          "source": {
            "file": "sections/08-conclusions.md",
            "quote": "The limitations bound every conclusion; each future direction answers one of them."
          }
        }
      ]
    }
  ]
}
---

# Conclusions (lab and simulation line)

Conclusions add nothing: every claim already exists earlier in the paper.

**Extent** 150–400 words · 2 or 3 paragraphs

## Block `concl-answers`

The contributions are answered in the order of the objectives, each by its confirmatory result. One or two sentences per objective, each value written with its
expanded uncertainty as the results report it, and no claim wider than the
range of conditions or parameters the study covered.

## Block `concl-future`

The limitations bound every conclusion; each future direction answers one of them. Two to four directions (a composition or a condition not yet covered,
a lower uncertainty from the dominant component of the budget, a model
assumption to relax, a confirmatory study of an exploratory finding), each
citing a reference that supports it.

## LIA house style

No paper of this line has been measured yet: the rules below carry the group's writing rules from the experimental and observational lines to a laboratory or simulation study, and the extent at the top of this contract stays the target. They read the records the line keeps: the locked protocol revision `protocol/study-protocol-<slug>-vNN.md` and `study/protocol.lock.json`, the instrument records `study/instruments.json`, the raw data registrations `study/measurements.json`, the uncertainty budgets `study/uncertainty/<quantity>.json` and the analysis log `analysis/log.jsonl`.

**Measured size.** None yet; the group's method papers close in two or three paragraphs.

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

- A new claim, a new number, or a number that differs from the results.
- An objective without its answer, or a conclusion drawn from an exploratory analysis.
- A value without its uncertainty, or a conclusion beyond the range the study covered.
- A future direction that answers no limitation, or one without a reference that supports it.
- A closing appeal (*further research is needed*) in place of a direction.

## Inputs

### External inputs

| Input | Unblocks |
|---|---|
| `contributions` — The contributions are answered in the order of the objectives, each by its confirmatory result. | `concl-answers` |
| `limitations` — The limitations bound every conclusion; each future direction answers one of them. | `concl-future` |

### Internal chain

| Block | Depends on |
|---|---|
| `conclusions.concl-answers` — The contributions are answered in the order of the objectives, each by its confirmatory result. | `introduction.intro-objectives` |
| `conclusions.concl-future` — The limitations bound every conclusion; each future direction answers one of them. | `limitations.lim-reported` |
