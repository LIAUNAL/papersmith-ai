---
{
  "section": "methods",
  "position": 4,
  "mode": {
    "value": "transposition",
    "source": {
      "file": "sections/04-methods.md",
      "quote": "The methods transcribe the locked protocol and the measurement records; they never describe a step that was not run."
    }
  },
  "blocks": [
    {
      "id": "m-design",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "resolution"
    },
    {
      "id": "m-sample-matrix",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "resolution",
      "optional": true
    },
    {
      "id": "m-model-definition",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "resolution",
      "optional": true
    },
    {
      "id": "m-protocol",
      "requires_facts": [
        {
          "value": "protocol",
          "source": {
            "file": "sections/04-methods.md",
            "quote": "The protocol is the revision the operator locked, named with its location and every amendment to it."
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none"
    },
    {
      "id": "m-observables",
      "requires_facts": [
        {
          "value": "outcomes",
          "source": {
            "file": "sections/04-methods.md",
            "quote": "The outcomes are the primary observable and the secondary observables of the locked protocol, each with its measurand, its unit and how it was measured or computed."
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none"
    },
    {
      "id": "m-replicates-grid",
      "requires_facts": [
        {
          "value": "sample",
          "source": {
            "file": "sections/04-methods.md",
            "quote": "The sample is the number of replicates per condition or the parameter grid of the locked protocol, with its justification."
          }
        }
      ],
      "requires_declarations": [],
      "citations": "resolution"
    },
    {
      "id": "m-calibration",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "resolution"
    },
    {
      "id": "m-uncertainty",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "resolution"
    },
    {
      "id": "m-analysis",
      "requires_facts": [
        {
          "value": "analysis-plan",
          "source": {
            "file": "sections/04-methods.md",
            "quote": "The analysis-plan is the locked protocol's primary model, the fits and comparisons it plans and how outliers and failed runs are handled."
          }
        }
      ],
      "requires_declarations": [],
      "citations": "resolution"
    }
  ]
}
---

# Methods (lab and simulation line)

The methods transcribe the locked protocol and the measurement records; they never describe a step that was not run.
The blocks below follow the reporting of uncertainty of GUM clause 7
(JCGM 100:2008, items 7.1.2 to 7.1.4 and 7.2.7, paraphrased);
`python skills/_core/checklists/checklist_cli.py check --guideline gum-reporting --root .`
reports which items still lack their text. A deviation from the locked
protocol is reported where it happened and again in the limitations.

**Extent** 900–2000 words · a table of instruments, one uncertainty budget table per quantity of the primary observable

## Block `m-design`

The design named early: the factors varied and their levels (a composition
series, a temperature or pressure range, a set of processing conditions) or
the parameter space of the model, the conditions held fixed (ambient
temperature and humidity, atmosphere, boundary conditions), and the laboratory
or computing facility and the period in which the samples were made and
measured or the runs executed, with dates. When a procedure follows a
published standard or method, cite it and state every departure from it (GUM
7.1.2). The design is the one of the locked protocol; a different design is a
protocol amendment, stated as such.

## Block `m-sample-matrix` (variant `materials`, optional)

Written only in a workspace of the `materials` variant; the
`modelling-simulation` variant leaves it unopened. The sample matrix: every
sample or specimen with its identifier, the precursors with their suppliers
and purities, and the synthesis, deposition or processing route, each step
with its temperature, time, atmosphere, rates and equipment; then the
characterization techniques used (structural, compositional, morphological,
functional), each with its instrument, its settings and the instrument record
it uses in `study/instruments.json`. A sample excluded after it was made is
reported in the results with the reason.

## Block `m-model-definition` (variant `modelling-simulation`, optional)

Written only in a workspace of the `modelling-simulation` variant; the
`materials` variant leaves it unopened. The model: the governing equations or
analytical relations, the assumptions and their domain of validity, the
geometry and the boundary and initial conditions; the solver (the code and its
version, the discretization, the time step or the mesh, the tolerances); the
parameters, each with its value, unit and source (measured, taken from the
literature with its citation, or fitted, and to which data); and the
convergence criteria with the mesh, time-step or sample-size study that shows
the outputs no longer depend on them. The code that runs the model is the
operator's, pinned by the version or the commit the analysis log records.

## Block `m-protocol`

The protocol is the revision the operator locked, named with its location and every amendment to it. Read the lock with `python skills/_core/empirical/study_cli.py
protocol status --root .`: the revision, its sha256 and each amendment with
its reason and date. A study whose protocol was locked after its first
measurement or run says so.

## Block `m-observables`

GUM 7.2.1, paraphrased: the measurand fully defined. The outcomes are the primary observable and the secondary observables of the locked protocol, each with its measurand, its unit and how it was measured or computed. The primary
observable is named first, exactly as the protocol names it and with its
identifier; the paper never changes it, and an observable added after the
protocol was locked is reported as such. Each measurand is defined completely
enough that its value is unique at the stated conditions (temperature,
pressure, sample state), under the quantity name the measurement core
registers it with in `study/measurements.json`.

## Block `m-replicates-grid`

The sample is the number of replicates per condition or the parameter grid of the locked protocol, with its justification. The number of independent replicates per condition (separate
samples, separate preparations or runs with new seeds, saying which) and why
it suffices for the precision targeted, or the parameter grid (each
parameter's range and step, or the design of the sweep) and why it covers the
question. A replicate is a separate realization: repeated readings of one
specimen are reported as repeated readings, never as new samples. The achieved
number belongs to the results.

## Block `m-calibration`

Calibration against known values, GUM 7.1.4, paraphrased. Every instrument
from its record in `study/instruments.json` (`python
skills/_core/measurement/measure_cli.py instrument status --root .`): the
model, the serial number, the resolution, the calibration certificate with its
date and due date, and the uncertainty the certificate states with its
coverage factor or its distribution. Then the check against a known value: the
reference material, standard sample or analytical solution used, its certified
or known value with its uncertainty and source, and how its readings were
taken and registered. For a simulation, the known value is an analytical
solution, a benchmark case or a measured reference that the model reproduces
before it is used. Every correction applied (zero offset, drift, temperature)
and every constant used is given with its source and its uncertainty. An
instrument used past its due date is reported with the reason the operator
recorded.

## Block `m-uncertainty`

GUM clause 7 (7.1.4 and 7.2.7), paraphrased. The measurement model, the
function that gives each output quantity from its inputs, then for each
quantity the uncertainty budget the measurement core computed
(`study/uncertainty/<quantity>.json`, read with `python
skills/_core/measurement/measure_cli.py uncertainty status --root .`): the
type A component from the scatter of the replicates (the number of readings,
their standard deviation and its degrees of freedom), the type B components
from the instrument records (the uncertainty the certificate states and the
resolution, each with its assumed distribution), the sensitivity coefficient
of each input, the combined standard uncertainty, the effective degrees of
freedom from the Welch-Satterthwaite formula, and the expanded uncertainty
with its coverage factor and the level of confidence that factor gives, or the
declared factor with its basis. Correlations between inputs are stated, or
their absence justified, and a component left out is named with the reason.

## Block `m-analysis`

The analysis-plan is the locked protocol's primary model, the fits and comparisons it plans and how outliers and failed runs are handled. Describe the analysis as planned: the fits, regressions or
comparisons with their models and estimators, how a result is compared with a
known value or with another condition (a difference judged against the
combined expanded uncertainty, a normalized error), how outliers and failed
runs are handled, and the software with its version as the log records it.
Then say which analyses were confirmatory and which exploratory, as the
analysis log labels them (`python skills/_core/empirical/analysis_cli.py
status --root .`): an analysis that maps to an entry of the locked analysis
plan is confirmatory, every other analysis (an extra sweep, a refit, a new
condition) is exploratory and is called so.

## LIA house style

No paper of this line has been measured yet: the rules below carry the group's writing rules from the experimental and observational lines to a laboratory or simulation study, and the extent at the top of this contract stays the target. They read the records the line keeps: the locked protocol revision `protocol/study-protocol-<slug>-vNN.md` and `study/protocol.lock.json`, the instrument records `study/instruments.json`, the raw data registrations `study/measurements.json`, the uncertainty budgets `study/uncertainty/<quantity>.json` and the analysis log `analysis/log.jsonl`.

**Measured size.** None yet; a laboratory or simulation methods section of this extent covers each block in prose, with a table of instruments when there are more than three.

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

- A table of two columns or two rows whose values a plot, or the sentence, could carry.
- A step described that has no record: no protocol field, instrument record, registered data file, analysis-log entry or operator record behind it.
- A primary observable, factor level, parameter grid or number of replicates that differs from the locked protocol without the amendment that changed it.
- Repeated readings of one specimen counted as independent replicates.
- An instrument without its calibration certificate and due date, or a correction or constant without its source.
- An uncertainty budget that leaves out a component without saying why, or an expanded uncertainty without its coverage factor and level of confidence.
- A model parameter without its value, unit and source, or a simulation without its convergence study.
- An analysis described as planned that the locked analysis plan does not contain, or no statement of which analyses were confirmatory and which exploratory.
- A variant block (`m-sample-matrix`, `m-model-definition`) written in a workspace of another variant.

## Inputs

### External inputs

| Input | Unblocks |
|---|---|
| `protocol` — The protocol is the revision the operator locked, named with its location and every amendment to it. | `m-protocol` |
| `outcomes` — The outcomes are the primary observable and the secondary observables of the locked protocol, each with its measurand, its unit and how it was measured or computed. | `m-observables` |
| `sample` — The sample is the number of replicates per condition or the parameter grid of the locked protocol, with its justification. | `m-replicates-grid` |
| `analysis-plan` — The analysis-plan is the locked protocol's primary model, the fits and comparisons it plans and how outliers and failed runs are handled. | `m-analysis` |

### Internal chain

None: no block of this section waits on another block.
