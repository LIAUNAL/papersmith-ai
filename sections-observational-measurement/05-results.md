---
{
  "section": "results",
  "position": 5,
  "mode": {
    "value": "transposition",
    "source": {
      "file": "sections/05-results.md",
      "quote": "Every count comes from study/flow.json and every estimate from an output the analysis log hashes."
    }
  },
  "blocks": [
    {
      "id": "r-participant-flow",
      "requires_facts": [
        {
          "value": "participant-flow",
          "source": {
            "file": "sections/05-results.md",
            "quote": "The participant-flow is the operator's counts at each stage of the study, checked and signed."
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none"
    },
    {
      "id": "r-descriptive",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none"
    },
    {
      "id": "r-main-results",
      "requires_facts": [
        {
          "value": "outcomes",
          "source": {
            "file": "sections/05-results.md",
            "quote": "The outcomes of the locked protocol are reported in its order, the primary outcome first."
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none"
    },
    {
      "id": "r-diagnostic-accuracy",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none",
      "optional": true
    },
    {
      "id": "r-measurement-properties",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none",
      "optional": true
    },
    {
      "id": "r-other-analyses",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none"
    }
  ]
}
---

# Results (observational and measurement studies line)

STROBE items 13 to 17, STARD 2015 items 19 to 25, COSMIN 2.0 results items. Every count comes from study/flow.json and every estimate from an output the analysis log hashes.
The results report; interpretation, comparison with other studies and
implications wait for the discussion.

**Extent** 900–2200 words · the participant flow figure, one table of participant characteristics, one figure per outcome family (its estimates with their 95% intervals as a dot-and-whisker or forest plot) · at least as many figures as tables

## Block `r-participant-flow`

STROBE item 13, STARD 2015 item 19. The participant-flow is the operator's counts at each stage of the study, checked and signed.
The numbers of individuals potentially eligible, examined for eligibility,
confirmed eligible, included, completing follow-up and analysed, with the
reasons for non-participation at each stage, copied from `study/flow.json`.
The flow diagram `paper/Figures/participant-flow.svg`, drawn from those counts
by `python skills/_core/participant_flow/flow_cli.py render --root .` and
signed by the operator (`flow_cli.py signoff --by <operator>`), is cited here
before it appears; `flow_cli.py status --root .` must report the figure current
and the sign-off current before the block is drafted. The assistant never
enters, corrects or completes a count: an inconsistent count goes back to the
operator.

## Block `r-descriptive`

STROBE item 14, STARD 2015 item 20, COSMIN 2.0 sample characteristics. The
characteristics of the participants (demographic, clinical, social) and the
information on exposures and potential confounders, as a table from the
analysis outputs, with the number of participants with missing data for each
variable of interest. For a cohort, the follow-up time (average and total);
for a diagnostic accuracy study, the distribution of the severity of disease
and of alternative diagnoses in those without the target condition.

## Block `r-main-results`

STROBE items 15 and 16, STARD 2015 item 24. The outcomes of the locked protocol are reported in its order, the primary outcome first.
Only entries that `analysis/log.jsonl` labels confirmatory support a
confirmatory claim (`python skills/_core/empirical/analysis_cli.py status
--root .`): each estimate is cited from the output of such an entry, with its
precision (a 95% confidence interval), unadjusted and, when planned, adjusted
for the confounders the protocol named, saying which and why. A planned
outcome that was not analysed is reported as not analysed, with the reason,
never dropped. Category boundaries of a grouped continuous variable are given,
and relative risks are translated into absolute risks when that is meaningful.
The estimates of an outcome family are drawn as one dot-and-whisker or forest
plot with their 95% intervals, unadjusted beside adjusted; their exact values go
in the text, or in a table only when the venue requires one.

## Block `r-diagnostic-accuracy` (variant `diagnostic-validation`, optional)

Written only in a workspace of the `diagnostic-validation` variant (STARD 2015
items 21 to 25); the other variants leave it unopened. The time interval and
any clinical intervention between the index test and the reference standard,
the cross tabulation of the index test results (or their distribution) by the
results of the reference standard, the estimates of diagnostic accuracy
(sensitivity, specificity, predictive values, likelihood ratios or the area
under the curve, with the ROC curve as a figure) with their 95% confidence intervals, the indeterminate and
missing results and how they were handled, and any adverse events from
performing the index test or the reference standard.

## Block `r-measurement-properties` (variant `measurement-instrument`, optional)

Written only in a workspace of the `measurement-instrument` variant (COSMIN 2.0
results items per measurement property); the other variants leave it
unopened. For each measurement property the methods announced, in the same
order, the result with its precision and against the hypothesis or criterion
set before the analysis: the factor structure and its fit, internal
consistency per dimension, the reliability coefficient with its model, the
standard error of measurement or the smallest detectable change, the
proportion of hypotheses confirmed for construct validity, criterion validity
and responsiveness. A property whose criterion was not met is reported as not
met.

## Block `r-other-analyses`

STROBE item 17, STARD 2015 item 25. Every other analysis done (subgroups,
interactions, sensitivity analyses), each labelled exploratory as
`analysis/log.jsonl` labels it, with the reason the log gives (no entry of the
locked analysis plan, or no current protocol lock when it ran). An exploratory
result is stated with its estimate and precision and called hypothesis
generating; it never supports a confirmatory claim in the abstract, the
discussion or the conclusions.

## LIA house style

No paper of this line has been measured yet: the rules below carry the group's writing rules from the experimental and review lines to an observational or measurement study, and the extent at the top of this contract stays the target. They read the records the line keeps: the locked protocol revision `protocol/study-protocol-<slug>-vNN.md` and `study/protocol.lock.json`, the ethics and registration records under `study/`, the data dictionaries and quality reports under `datasets/`, the analysis log `analysis/log.jsonl` and the participant flow counts `study/flow.json`.

**Measured size.** None yet; a STROBE or STARD results section of this extent opens on the flow figure, then the characteristics table and one figure per outcome family.

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
- Figures over tables. In Methods and Results, present comparisons, distributions, trends, effects with their intervals and time series as data figures (line, bar, dot-and-whisker or forest, violin or box plots, heat maps) or diagrams. Keep a table only for values a reader must look up exactly (settings, hyperparameters, dataset, participant or hardware characteristics, metadata) or when the venue requires one. Among the floats of Methods and Results, aim at about 60 % figures and 40 % tables.
- A figure or table caption is at most four lines: a title that says what the float shows, plus the one definition a reader needs to read it. Notation and further definitions go in a table note below the table or in the text.
- **Every number comes from a record.** Counts from `study/flow.json`, estimates from the outputs of the analysis log, planned values (sample size, outcomes, analysis plan) from the locked protocol revision, never recounted or retyped by hand.

## Disqualifiers

- A table of two columns or two rows whose values a bar or pie chart, or the sentence, could carry.
- A count that differs from `study/flow.json`, or a flow figure that is stale or not signed by the operator.
- An estimate with no analysis-log entry whose output holds it, or without its confidence interval.
- A confirmatory claim supported by an entry the analysis log labels exploratory.
- An exploratory analysis not labelled exploratory, or a subgroup result presented as a main result.
- A primary outcome other than the locked protocol's, or a planned outcome silently left out.
- Missing data not reported per variable.
- An interpretation, a comparison with other studies or a recommendation: those belong to the discussion.
- [block: r-diagnostic-accuracy, r-measurement-properties] A variant block (`r-diagnostic-accuracy`, `r-measurement-properties`) written in a workspace of another variant.

## Inputs

### External inputs

| Input | Unblocks |
|---|---|
| `participant-flow` — The participant-flow is the operator's counts at each stage of the study, checked and signed. | `r-participant-flow` |
| `outcomes` — The outcomes of the locked protocol are reported in its order, the primary outcome first. | `r-main-results` |

### Internal chain

None: no block of this section waits on another block.
