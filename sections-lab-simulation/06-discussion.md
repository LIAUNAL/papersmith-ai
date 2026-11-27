---
{
  "section": "discussion",
  "position": 6,
  "mode": {
    "value": "argument",
    "source": {
      "file": "sections/06-discussion.md",
      "quote": "The discussion interprets the reported results against the objectives, the known values and other studies, and states no result the results section does not report."
    }
  },
  "blocks": [
    {
      "id": "d-key-results",
      "requires_facts": [
        {
          "value": "contributions",
          "source": {
            "file": "sections/06-discussion.md",
            "quote": "The contributions are revisited one by one with the confirmatory result that answers each objective."
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none",
      "after": [
        {
          "target": "results",
          "source": {
            "file": "sections/06-discussion.md",
            "quote": "The contributions are revisited one by one with the confirmatory result that answers each objective."
          }
        },
        {
          "target": "introduction.intro-objectives",
          "source": {
            "file": "sections/06-discussion.md",
            "quote": "The contributions are revisited one by one with the confirmatory result that answers each objective."
          }
        }
      ]
    },
    {
      "id": "d-interpretation",
      "requires_facts": [
        {
          "value": "gap",
          "source": {
            "file": "sections/06-discussion.md",
            "quote": "The gap the introduction stated is the yardstick: say how far the results close it."
          }
        }
      ],
      "requires_declarations": [],
      "citations": "discovery",
      "after": [
        {
          "target": "introduction.intro-evidence-gap",
          "source": {
            "file": "sections/06-discussion.md",
            "quote": "The gap the introduction stated is the yardstick: say how far the results close it."
          }
        }
      ]
    },
    {
      "id": "d-validity-range",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "resolution"
    },
    {
      "id": "d-implications",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none"
    }
  ]
}
---

# Discussion (lab and simulation line)

The discussion interprets the reported results against the objectives, the known values and other studies, and states no result the results section does not report.
The limitations have their own section; the discussion refers to them where
they bound an interpretation.

**Extent** 600–1300 words · 4 to 7 paragraphs · at least as many figures as tables

## Block `d-key-results`

The contributions are revisited one by one with the confirmatory result that answers each objective. One or two sentences per objective, in the order of the introduction,
each stating the value already reported with its uncertainty, never a new
number. A result the analysis log labels exploratory is named as exploratory
here too.

## Block `d-interpretation`

The gap the introduction stated is the yardstick: say how far the results close it. Compare each key result with the closest values of the studies named
in the introduction: two values agree or differ only through both
uncertainties (a difference against the combined expanded uncertainty, a
normalized error), and a value reported elsewhere without its uncertainty is
said to be so. Explain the agreement or the difference (material, process,
conditions, model assumptions), and discuss the alternative explanations
(a measurement artefact, sample-to-sample variability, a model assumption, a
numerical error) before setting them aside. Every comparison cites the study
it compares with.

## Block `d-validity-range`

The range over which the results hold: the compositions, process conditions,
temperatures or parameter values the study covered, and the domain of validity
of the model. A value outside that range is an extrapolation and is called so.

## Block `d-implications`

What the results mean for the application, the process or further research,
each implication traceable to a reported result and no stronger than its
uncertainty allows.

## LIA house style

No paper of this line has been measured yet: the rules below carry the group's writing rules from the experimental and observational lines to a laboratory or simulation study, and the extent at the top of this contract stays the target. They read the records the line keeps: the locked protocol revision `protocol/study-protocol-<slug>-vNN.md` and `study/protocol.lock.json`, the instrument records `study/instruments.json`, the raw data registrations `study/measurements.json`, the uncertainty budgets `study/uncertainty/<quantity>.json` and the analysis log `analysis/log.jsonl`.

**Measured size.** None yet; the extent above follows the group's method papers, whose discussions run four to seven paragraphs.

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
- Figures over tables. In Methods and Results, present comparisons, distributions, trends, effects with their intervals and time series as data figures (line, bar, dot-and-whisker or forest, violin or box plots, heat maps) or diagrams. Keep a table only for values a reader must look up exactly (settings, hyperparameters, dataset, participant or hardware characteristics, metadata) or when the venue requires one. Among the floats of Methods and Results, aim at about 60 % figures and 40 % tables.
- A figure or table caption is at most four lines: a title that says what the float shows, plus the one definition a reader needs to read it. Notation and further definitions go in a table note below the table or in the text.
- **Every number comes from a record.** Values and uncertainties from `study/uncertainty/<quantity>.json`, instrument data from `study/instruments.json`, fits and sweeps from the outputs of the analysis log, planned values (replicates, parameter grid, observables, analysis plan) from the locked protocol revision, never recounted or retyped by hand.

## Disqualifiers

- A result or a number that the results section does not report.
- A claim about other studies without a citation that holds it.
- An agreement or a difference claimed without comparing both uncertainties.
- An exploratory result discussed as if it were confirmatory.
- No comparison with the closest studies the introduction named.
- A generalization beyond the compositions, conditions or parameter range the study covered.
- An implication or recommendation stronger than the uncertainty allows, or a closing appeal with no result behind it.

## Inputs

### External inputs

| Input | Unblocks |
|---|---|
| `contributions` — The contributions are revisited one by one with the confirmatory result that answers each objective. | `d-key-results` |
| `gap` — The gap the introduction stated is the yardstick: say how far the results close it. | `d-interpretation` |

### Internal chain

| Block | Depends on |
|---|---|
| `discussion.d-key-results` — The contributions are revisited one by one with the confirmatory result that answers each objective. | `introduction.intro-objectives` |
| `discussion.d-interpretation` — The gap the introduction stated is the yardstick: say how far the results close it. | `introduction.intro-evidence-gap` |
