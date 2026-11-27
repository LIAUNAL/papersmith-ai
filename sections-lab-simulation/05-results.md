---
{
  "section": "results",
  "position": 5,
  "mode": {
    "value": "transposition",
    "source": {
      "file": "sections/05-results.md",
      "quote": "Every value comes from a registered data file, an uncertainty budget or an output the analysis log hashes, and carries its expanded uncertainty."
    }
  },
  "blocks": [
    {
      "id": "r-calibration",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none"
    },
    {
      "id": "r-sample-characterization",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none",
      "optional": true
    },
    {
      "id": "r-model-verification",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none",
      "optional": true
    },
    {
      "id": "r-observables",
      "requires_facts": [
        {
          "value": "outcomes",
          "source": {
            "file": "sections/05-results.md",
            "quote": "The outcomes of the locked protocol are reported in its order, the primary observable first."
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none"
    },
    {
      "id": "r-uncertainty-budgets",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none"
    },
    {
      "id": "r-parameter-sweeps",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none"
    }
  ]
}
---

# Results (lab and simulation line)

GUM clause 7.2, paraphrased. Every value comes from a registered data file, an uncertainty budget or an output the analysis log hashes, and carries its expanded uncertainty.
The results report; interpretation, comparison with other studies and
implications wait for the discussion.

**Extent** 900–2200 words · the calibration table, one figure per observable (its values across conditions with their expanded uncertainties as error bars, or a line over the parameter grid), one uncertainty budget table per quantity of the primary observable · at least as many figures as tables

## Block `r-calibration`

The calibration results against known values come first, because every later
value rests on them. For each reference material, standard sample or benchmark
case: its known value with its uncertainty, the value obtained with the
expanded uncertainty of its budget, their difference and whether it lies
within the combined expanded uncertainty; and the calibration state of each
instrument as `python skills/_core/measurement/measure_cli.py status --root .`
reports it (current, or past due with the reason the operator recorded). A
check that failed is reported as failed, with what the operator did next.

## Block `r-sample-characterization` (variant `materials`, optional)

Written only in a workspace of the `materials` variant; the
`modelling-simulation` variant leaves it unopened. The achieved sample matrix
(the samples made, measured and excluded, with the reasons) and the
characterization that confirms what each sample is (phase, composition,
thickness, morphology), each value with its uncertainty, before the
observables.

## Block `r-model-verification` (variant `modelling-simulation`, optional)

Written only in a workspace of the `modelling-simulation` variant; the
`materials` variant leaves it unopened. The convergence results (the outputs
against the mesh, the time step or the number of samples, and the setting
chosen), the verification against the analytical solution or the benchmark
case, and the comparison with measured reference data through both
uncertainties, before the observables; then the achieved parameter grid and
every run that failed or did not converge, with the reason.

## Block `r-observables`

GUM 7.2.1 to 7.2.6, paraphrased. The outcomes of the locked protocol are reported in its order, the primary observable first. Each value comes from its budget in
`study/uncertainty/<quantity>.json` and is written as the estimate, its
expanded uncertainty, the coverage factor with the level of confidence it
gives, and the unit, with the relative uncertainty when it helps the reader.
The uncertainty keeps at most two significant digits and the estimate is
rounded to the same decimal place. Only entries that `analysis/log.jsonl`
labels confirmatory support a confirmatory claim (`python
skills/_core/empirical/analysis_cli.py status --root .`). A planned observable
that was not measured or computed is reported as such, with the reason, never
dropped, and the correlation between two output quantities used together is
stated. Each observable is drawn as a figure: its values across conditions with
their expanded uncertainties as error bars, a line over the parameter grid, or
a heat map over two parameters; a table carries an observable only when a reader
must look up its values exactly.

## Block `r-uncertainty-budgets`

GUM 7.2.7, paraphrased. One budget table per quantity of the primary observable
(and per condition set when the budgets differ), copied from
`study/uncertainty/<quantity>.json`: each component with its type (A or B), its
source, its standard uncertainty, its sensitivity coefficient and its
contribution, then the combined standard uncertainty, the effective degrees of
freedom, the coverage factor and the expanded uncertainty. The dominant
component is named. A budget the measurement core reports stale is computed
again before it is copied.

## Block `r-parameter-sweeps`

Every sweep and every other analysis, each labelled as `analysis/log.jsonl`
labels it: the confirmatory sweeps of the locked analysis plan first, then the
exploratory ones with the reason the log gives (no entry of the locked analysis
plan, or no current protocol lock when it ran). A trend across a sweep is
stated with the uncertainty of each point and of every fitted parameter. An
exploratory result is called hypothesis generating; it never supports a
confirmatory claim in the abstract, the discussion or the conclusions.

## LIA house style

No paper of this line has been measured yet: the rules below carry the group's writing rules from the experimental and observational lines to a laboratory or simulation study, and the extent at the top of this contract stays the target. They read the records the line keeps: the locked protocol revision `protocol/study-protocol-<slug>-vNN.md` and `study/protocol.lock.json`, the instrument records `study/instruments.json`, the raw data registrations `study/measurements.json`, the uncertainty budgets `study/uncertainty/<quantity>.json` and the analysis log `analysis/log.jsonl`.

**Measured size.** None yet; a laboratory or simulation results section of this extent opens on the calibration table, then one figure per observable and the budget tables.

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

- A table of two columns or two rows whose values a plot, or the sentence, could carry.
- A value without its expanded uncertainty, coverage factor and unit, or one that differs from its budget.
- A value with no registered data file, budget or analysis-log entry behind it.
- A calibration check against known values not reported, or a failed one left out.
- A confirmatory claim supported by an entry the analysis log labels exploratory, or an exploratory sweep not labelled exploratory.
- A simulated value called measured.
- A primary observable other than the locked protocol's, or a planned observable silently left out.
- An interpretation, a comparison with other studies or a recommendation: those belong to the discussion.
- A variant block (`r-sample-characterization`, `r-model-verification`) written in a workspace of another variant.

## Inputs

### External inputs

| Input | Unblocks |
|---|---|
| `outcomes` — The outcomes of the locked protocol are reported in its order, the primary observable first. | `r-observables` |

### Internal chain

None: no block of this section waits on another block.
