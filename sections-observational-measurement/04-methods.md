---
{
  "section": "methods",
  "position": 4,
  "mode": {
    "value": "transposition",
    "source": {
      "file": "sections/04-methods.md",
      "quote": "The methods transcribe the locked protocol and the study's records; they never describe a step that was not run."
    }
  },
  "blocks": [
    {
      "id": "m-design-setting",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "resolution"
    },
    {
      "id": "m-participants",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none"
    },
    {
      "id": "m-variables-outcomes",
      "requires_facts": [
        {
          "value": "outcomes",
          "source": {
            "file": "sections/04-methods.md",
            "quote": "The outcomes are the primary and secondary outcomes of the locked protocol, each with its measure and time point."
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none"
    },
    {
      "id": "m-reference-standard",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "resolution",
      "optional": true
    },
    {
      "id": "m-data-sources",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "resolution"
    },
    {
      "id": "m-bias",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "resolution"
    },
    {
      "id": "m-study-size",
      "requires_facts": [
        {
          "value": "sample",
          "source": {
            "file": "sections/04-methods.md",
            "quote": "The sample is the planned size of the locked protocol with its justification."
          }
        }
      ],
      "requires_declarations": [],
      "citations": "resolution"
    },
    {
      "id": "m-statistical-methods",
      "requires_facts": [
        {
          "value": "analysis-plan",
          "source": {
            "file": "sections/04-methods.md",
            "quote": "The analysis-plan is the locked protocol's primary model, covariates, handling of missing data and multiplicity."
          }
        }
      ],
      "requires_declarations": [],
      "citations": "resolution"
    },
    {
      "id": "m-measurement-properties",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "resolution",
      "optional": true
    },
    {
      "id": "m-protocol-registration",
      "requires_facts": [
        {
          "value": "protocol",
          "source": {
            "file": "sections/04-methods.md",
            "quote": "The protocol is the revision the operator locked, named with its location and every amendment to it."
          }
        }
      ],
      "requires_declarations": [
        {
          "value": "study-registration",
          "source": {
            "file": "sections/04-methods.md",
            "quote": "The study-registration is stated with the registry, the record and its dates."
          }
        }
      ],
      "citations": "none"
    },
    {
      "id": "m-ethics",
      "requires_facts": [],
      "requires_declarations": [
        {
          "value": "ethics-approval",
          "source": {
            "file": "sections/04-methods.md",
            "quote": "The ethics-approval names the committee, the approval code and date, and the consent route the operator recorded."
          }
        }
      ],
      "citations": "none"
    }
  ]
}
---

# Methods (observational and measurement studies line)

The methods transcribe the locked protocol and the study's records; they never describe a step that was not run.
Open with one sentence naming the reporting guideline the study follows, cited:
STROBE for an observational study (von Elm et al., 2007,
doi:10.1371/journal.pmed.0040296), STARD 2015 for a diagnostic accuracy study
(Bossuyt et al., 2015, doi:10.1136/bmj.h5527), the COSMIN reporting guideline
for a study of measurement properties. The blocks below follow STROBE items 4
to 12, STARD 2015 items 5 to 18 and the general methods items of COSMIN 2.0;
`python skills/_core/checklists/checklist_cli.py check --guideline <id> --root .`
reports which items still lack their text. A deviation from the locked
protocol is reported where it happened and again in the limitations.

**Extent** 900–1800 words · the participant flow figure belongs to the results

## Block `m-design-setting`

STROBE items 4 and 5, STARD 2015 items 5 and 8. The design named early and in
the guideline's words (prospective or retrospective cohort, case-control,
cross-sectional; a diagnostic accuracy study with its data collection planned
before or after the index test and the reference standard were done; a study
of the measurement properties of a named instrument), then the setting: the
locations, the periods of recruitment, exposure, follow-up and data collection,
with dates. The design is the one of the locked protocol; a different design
is a protocol amendment, stated as such.

## Block `m-participants`

STROBE item 6, STARD 2015 items 6, 7 and 9, COSMIN 2.0 general methods. The
eligibility criteria of the locked protocol, the sources and methods of
selecting participants, and how they were recruited: consecutive, random or
convenience series, and, for a diagnostic accuracy study, whether recruitment
was based on presenting symptoms or on prior test results. For a cohort, the
follow-up; for a case-control study, how cases and controls were ascertained
and chosen; for a matched design, the matching criteria. The operator collected
the data and recruited the participants; the text reports how, from the
operator's own account.

## Block `m-variables-outcomes`

STROBE item 7, COSMIN 2.0 general methods (the construct and the instrument
versions). The outcomes are the primary and secondary outcomes of the locked protocol, each with its measure and time point.
The primary outcome is named first, exactly as the protocol names it and with
its identifier; the paper never changes it, and an outcome added after the
protocol was locked is reported as such. Then the exposures, predictors,
potential confounders and effect modifiers, each with its definition and, when
it applies, the diagnostic criteria used.

## Block `m-reference-standard` (variant `diagnostic-validation`, optional)

Written only in a workspace of the `diagnostic-validation` variant (STARD 2015
items 10 to 13); the other variants leave it unopened. The index test and the
reference standard, each in enough detail to be repeated; the rationale for
choosing the reference standard; the definition and rationale of the test
positivity cut-offs or result categories, saying which were prespecified and
which were exploratory; and whether the readers of the index test and of the
reference standard knew the other result or the clinical information.

## Block `m-data-sources`

STROBE item 8, COSMIN 2.0 general methods. For each variable, the source of
the data and the method of measurement, transcribed from the data dictionary
the operator completed (`datasets/<slug>/dictionary.json`: each variable's
type, unit, levels and how it was measured), with the instrument, its version
and its calibration when one applies. The quality report of the data
(`datasets/<slug>/qc.json`) is summarized, and how personal identifiers were
removed or transformed is stated from the de-identification record when the
dictionary flags identifying columns. When the measurement is the same in
several groups, say that it was comparable.

## Block `m-bias`

STROBE item 9. Every effort made to address potential sources of bias
(selection, information, confounding, loss to follow-up), as the protocol
planned it, each with the bias it addresses. A source of bias that was not
addressed is not hidden here; it is named in the limitations.

## Block `m-study-size`

STROBE item 10, STARD 2015 item 18. The sample is the planned size of the locked protocol with its justification.
The calculation (the expected value, the precision or power targeted, the
assumptions and the source of each one) or, when the size was fixed by the
available data, that reason and the precision it allows. The achieved size
belongs to the results.

## Block `m-statistical-methods`

STROBE items 11 and 12, STARD 2015 items 14 to 17. The analysis-plan is the locked protocol's primary model, covariates, handling of missing data and multiplicity.
Describe the primary analysis as planned: the model and the estimate it
reports, how quantitative variables were handled and why any grouping was
chosen, how confounding was controlled, the subgroup and interaction
analyses, how missing data and indeterminate results were handled, how loss
to follow-up (cohort), matching (case-control) or the sampling strategy
(cross-sectional) were addressed, and the sensitivity analyses. Then say which
analyses were confirmatory and which exploratory, as the analysis log labels
them (`python skills/_core/empirical/analysis_cli.py status --root .`): an
analysis that maps to an entry of the locked analysis plan is confirmatory,
every other analysis is exploratory and is called so. Name the software and
its version as the log records them.

## Block `m-measurement-properties` (variant `measurement-instrument`, optional)

Written only in a workspace of the `measurement-instrument` variant (COSMIN
2.0 items on each measurement property); the other variants leave it
unopened. For each measurement property evaluated, the design and the
statistical method, with the hypotheses or criteria set before the analysis:
dimensionality (structural validity, the factor model and its fit criteria),
internal consistency, reliability (the design of the repeated measurements,
the time interval, the stability of the participants between them and the
intraclass correlation model), measurement error (the standard error of
measurement or the smallest detectable change), validity (hypotheses testing
for construct validity, with the expected direction and size of each
correlation or difference, cross-cultural validity, criterion validity against
a named gold standard) and responsiveness (the change expected and how it was
anchored). A property not evaluated is not described.

## Block `m-protocol-registration`

STARD 2015 items 28 and 29. The protocol is the revision the operator locked, named with its location and every amendment to it.
Read the lock with `python skills/_core/empirical/study_cli.py protocol status
--root .`: the revision, its sha256 and each amendment with its reason and
date. The study-registration is stated with the registry, the record and its dates.
A registration dated after the first enrolment is called retrospective, and a
study that was not registered says so.

## Block `m-ethics`

The ethics-approval names the committee, the approval code and date, and the consent route the operator recorded.
Transcribe the operator's ethics record (`study/ethics.json`); a study that
needed no approval states the reason the operator recorded. The assistant
never writes that consent was obtained, waived or not needed unless the
operator's record says so.

## LIA house style

No paper of this line has been measured yet: the rules below carry the group's writing rules from the experimental and review lines to an observational or measurement study, and the extent at the top of this contract stays the target. They read the records the line keeps: the locked protocol revision `protocol/study-protocol-<slug>-vNN.md` and `study/protocol.lock.json`, the ethics and registration records under `study/`, the data dictionaries and quality reports under `datasets/`, the analysis log `analysis/log.jsonl` and the participant flow counts `study/flow.json`.

**Measured size.** None yet; a STROBE or STARD methods section of this extent covers every item in prose, with a table of variables when there are more than five.

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

- A table of two columns or two rows whose values a bar or pie chart, or the sentence, could carry.
- A step described that has no record: no protocol field, dictionary entry, analysis-log entry or operator record behind it.
- A primary outcome, design, eligibility criterion or sample size that differs from the locked protocol without the amendment that changed it.
- A sample size given without its justification, or the achieved size reported here instead of in the results.
- An analysis described as planned that the locked analysis plan does not contain.
- No statement of which analyses were confirmatory and which exploratory.
- A variable without its source and method of measurement, or a measurement whose dictionary entry is blank.
- An ethics approval, consent route or registration that the operator's records do not hold, or a registration after the first enrolment not called retrospective.
- A variant block (`m-reference-standard`, `m-measurement-properties`) written in a workspace of another variant.

## Inputs

### External inputs

| Input | Unblocks |
|---|---|
| `outcomes` — The outcomes are the primary and secondary outcomes of the locked protocol, each with its measure and time point. | `m-variables-outcomes` |
| `sample` — The sample is the planned size of the locked protocol with its justification. | `m-study-size` |
| `analysis-plan` — The analysis-plan is the locked protocol's primary model, covariates, handling of missing data and multiplicity. | `m-statistical-methods` |
| `protocol` — The protocol is the revision the operator locked, named with its location and every amendment to it. | `m-protocol-registration` |
| `study-registration` — The study-registration is stated with the registry, the record and its dates. | `m-protocol-registration` |
| `ethics-approval` — The ethics-approval names the committee, the approval code and date, and the consent route the operator recorded. | `m-ethics` |

### Internal chain

None: no block of this section waits on another block.
