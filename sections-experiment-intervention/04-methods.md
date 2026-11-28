---
{
  "section": "methods",
  "position": 4,
  "mode": {
    "value": "transposition",
    "source": {
      "file": "sections/04-methods.md",
      "quote": "The methods transcribe the locked protocol and the trial's records; they never describe a step that was not run."
    }
  },
  "blocks": [
    {
      "id": "m-trial-design",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "resolution"
    },
    {
      "id": "m-participants-settings",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "resolution"
    },
    {
      "id": "m-interventions",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "resolution"
    },
    {
      "id": "m-outcomes",
      "requires_facts": [
        {
          "value": "outcomes",
          "source": {
            "file": "sections/04-methods.md",
            "quote": "The outcomes are the primary and secondary outcomes of the locked protocol, each with its measure, its analysis metric and its time point."
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none"
    },
    {
      "id": "m-sample-size",
      "requires_facts": [
        {
          "value": "sample",
          "source": {
            "file": "sections/04-methods.md",
            "quote": "The sample is the planned number of participants or experimental units of the locked protocol, with its justification."
          }
        }
      ],
      "requires_declarations": [],
      "citations": "resolution"
    },
    {
      "id": "m-randomisation",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none"
    },
    {
      "id": "m-blinding",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none"
    },
    {
      "id": "m-statistical-methods",
      "requires_facts": [
        {
          "value": "analysis-plan",
          "source": {
            "file": "sections/04-methods.md",
            "quote": "The analysis-plan is the locked protocol's primary analysis, its estimand, the handling of missing data and multiplicity."
          }
        }
      ],
      "requires_declarations": [],
      "citations": "resolution"
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
            "quote": "The study-registration is stated with the registry, the record, the registration date and the first enrolment."
          }
        }
      ],
      "citations": "none"
    },
    {
      "id": "m-ethics-consent",
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
    },
    {
      "id": "m-field-units",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "resolution",
      "optional": true
    },
    {
      "id": "m-mixed-models",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "resolution",
      "optional": true
    },
    {
      "id": "m-animals-husbandry",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "resolution",
      "optional": true
    }
  ]
}
---

# Methods (experiment and intervention line)

The methods transcribe the locked protocol and the trial's records; they never describe a step that was not run.
Open with one sentence naming the reporting guideline the study follows, cited:
CONSORT 2025 for a randomised trial with people (Hopewell et al., 2025,
doi:10.1136/bmj-2024-081123), ARRIVE 2.0 for an experiment with animals
(Percie du Sert et al., 2020, doi:10.1371/journal.pbio.3000410); a plot or
crop field experiment reports against the design and analysis items of
ARRIVE 2.0 where they apply, since no formal checklist exists for it. The
blocks below follow CONSORT 2025 items 2, 3 and 8 to 21 and the ARRIVE 2.0
Essential 10; `python skills/_core/checklists/checklist_cli.py check
--guideline <id> --root .` reports which items still lack their text. A
deviation from the locked protocol is reported where it happened and again in
the limitations.

**Extent** 1000–2200 words · the flow diagram belongs to the results · at least as many figures (the design layout or the timeline) as tables

## Block `m-trial-design`

CONSORT 2025 items 9 and 10, ARRIVE 2.0 item 1. The design named early and in
the guideline's words: parallel group, crossover, factorial or cluster, with
the allocation ratio and the framework (superiority, non-inferiority with its
margin, or equivalence); for a field experiment, the completely randomised,
randomised complete block, Latin square or split-plot layout, the groups
compared and the controls. The design is the one of the locked protocol;
every important change made after the trial started (eligibility, outcomes,
analysis) is an amendment of the protocol, reported with its reason and date.

## Block `m-participants-settings`

CONSORT 2025 items 8, 11 and 12, ARRIVE 2.0 item 3. The settings and
locations where the data were collected, with the countries, the sites and
the dates; the eligibility criteria of the locked protocol for participants
and, when they apply, for the sites and the people who delivered the
intervention; and how patients or the public were involved in the design,
conduct or reporting, or that they were not. For a field experiment, the site,
season, soil and climate, and the inclusion and exclusion criteria of the
animals, plants or plots, with any unit excluded and why. The operator
recruited the participants or prepared the units; the text reports how, from
the operator's own account.

## Block `m-interventions`

CONSORT 2025 item 13, ARRIVE 2.0 item 9. The intervention and the comparator
of each group in enough detail to be repeated: what was given or done, by whom
and with which training, how, where, when and how often, for how long, how
adherence was promoted and assessed, and any tailoring or modification the
protocol allowed. The intervention is the one the operator delivered; a
departure from the protocol is stated as such.

## Block `m-outcomes`

CONSORT 2025 items 14 and 15, ARRIVE 2.0 item 6. The outcomes are the primary and secondary outcomes of the locked protocol, each with its measure, its analysis metric and its time point.
The primary outcome is named first, exactly as the protocol names it and with
its identifier; the paper never changes it, and an outcome added after the
protocol was locked is reported as such. Then how the harms were defined and
assessed (systematically or as reported by participants, by whom and when).
For an animal or field experiment, the outcome measures with the unit on
which each was measured.

## Block `m-sample-size`

CONSORT 2025 item 16, ARRIVE 2.0 item 2. The sample is the planned number of participants or experimental units of the locked protocol, with its justification.
The calculation (the effect size that matters, its source, the variability
assumed, the power and the significance level, the expected attrition) or,
for a field experiment, the number of replicates and the reason for it; then
the interim analyses and stopping guidelines the protocol set, or that there
were none. The achieved numbers belong to the results.

## Block `m-randomisation`

CONSORT 2025 items 17 to 19, ARRIVE 2.0 item 4. Read the operator's
allocation record with `python skills/_core/empirical/study_cli.py allocation
status --root .`, and report from it: the sequence generation (the method the
operator recorded: simple, block, stratified, minimisation or cluster, with
the block size and the strata when recorded, and the tool or service that
generated the sequence); the allocation concealment mechanism, as the operator
recorded it, and the steps that kept the sequence hidden until each unit was
assigned; and the implementation (who generated the sequence, who enrolled
the participants or prepared the units, and who assigned them), from the
operator's own account. The text never states the sequence, a unit's
assignment or the order of the list; the allocation list is never opened to
write this block. A stale allocation record (the list changed or removed, or
the protocol amended since it was recorded) is not described until the
operator records it again.

## Block `m-blinding`

CONSORT 2025 item 20, ARRIVE 2.0 item 5. Who was blinded after assignment
(participants, care providers or those who delivered the intervention,
outcome assessors, data analysts) and how, how the interventions were made
alike when that applies, and who knew the assignment. A trial in which
blinding was not possible says so and names who knew.

## Block `m-statistical-methods`

CONSORT 2025 item 21, ARRIVE 2.0 item 7. The analysis-plan is the locked protocol's primary analysis, its estimand, the handling of missing data and multiplicity.
Describe the primary analysis as planned: the estimand, the analysis
population (intention to treat or another, defined), the model and the effect
measure it reports with its precision, the covariates and stratification
factors adjusted for, how missing data were handled, and the methods of any
additional analyses (subgroups, sensitivity analyses). Then say which analyses
were confirmatory and which exploratory, as the analysis log labels them
(`python skills/_core/empirical/analysis_cli.py status --root .`): an analysis
that maps to an entry of the locked analysis plan is confirmatory, every other
analysis is exploratory and is called so. Name the software and its version
as the log records them.

## Block `m-protocol-registration`

CONSORT 2025 items 2, 3 and 10, ARRIVE 2.0 item 19. The protocol is the revision the operator locked, named with its location and every amendment to it.
Read the lock with `python skills/_core/empirical/study_cli.py protocol status
--root .`: the revision, its sha256 and each amendment with its reason and
date; say where the protocol and the statistical analysis plan can be
accessed. The study-registration is stated with the registry, the record, the registration date and the first enrolment. Transcribe the operator's registration record
(`study/registration.json`). A trial with people is registered prospectively,
on or before its first enrolment; a registration dated after the first
enrolment is called retrospective and the paper states the reason the
operator recorded, never presents it as prospective. A study that was not
registered says so, with the reason the operator recorded.

## Block `m-ethics-consent`

ARRIVE 2.0 item 14. The ethics-approval names the committee, the approval code and date, and the consent route the operator recorded.
Transcribe the operator's ethics record (`study/ethics.json`): for a trial
with people, how informed consent was obtained and from whom; for an
experiment with animals, the animal ethics committee and the licence. A study
that needed no approval states the reason the operator recorded. The assistant
never writes that consent was obtained, waived or not needed unless the
operator's record says so.

## Block `m-field-units` (variant `field-experiment`, optional)

Written only in a workspace of the `field-experiment` variant (ARRIVE 2.0
items 1 to 3); a `human-trial` workspace leaves it unopened. The layout of the
experiment: the blocks and how they were laid out against the known gradients
(slope, soil, light, shed), the plots or pens and their size, and the
experimental unit, the smallest unit to which a treatment was independently
assigned (a plot, a pen, a cage, a litter or an animal). Then the true
replication: the number of experimental units per treatment, kept distinct
from repeated measurements or subsamples taken within a unit, which are
pseudoreplication and never count as replicates.

## Block `m-mixed-models` (variant `field-experiment`, optional)

Written only in a workspace of the `field-experiment` variant when the
analysis plan names a mixed model; a `human-trial` workspace leaves it
unopened (its clustering belongs to `m-statistical-methods`). The model as
the locked plan states it: the fixed effects (treatment and its
interactions), each random effect (block, plot within block, animal, year or
site) and why it is random, the covariance structure of repeated measures,
the error distribution and link, how the degrees of freedom were computed,
and how the model was checked.

## Block `m-animals-husbandry` (variant `field-experiment`, optional)

Written only in a `field-experiment` workspace whose experiment used animals
(ARRIVE 2.0 items 8, 15 and 16); a plot or crop experiment and a
`human-trial` workspace leave it unopened. The animals (species, strain or
breed, sex, age or developmental stage, weight, source), their housing and
husbandry (housing, enrichment, diet, light cycle), and their care and
monitoring: the welfare checks, the humane end points set before the
experiment and the steps taken to reduce pain and distress, as the operator
recorded them.

## LIA house style

No paper of this line has been measured yet: the rules below carry the group's writing rules from the experimental and review lines to a trial or a controlled experiment, and the extent at the top of this contract stays the target. They read the records the line keeps: the locked protocol revision `protocol/study-protocol-<slug>-vNN.md` and `study/protocol.lock.json`, the ethics and registration records under `study/`, the operator's allocation record `study/allocation.json`, the data dictionaries and quality reports under `datasets/`, the analysis log `analysis/log.jsonl` and the flow counts `study/flow.json`.

**Measured size.** None yet; a CONSORT methods section of this extent covers every item in prose, with a table of the interventions when there are more than two groups.

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
- Figures over tables. In Methods and Results, present comparisons, distributions, trends, effects with their intervals and time series as data figures (line, bar, dot-and-whisker or forest, violin or box plots, heat maps) or diagrams. Keep a table only for values a reader must look up exactly (settings, hyperparameters, dataset, participant or hardware characteristics, metadata) or when the venue requires one. Among the floats of Methods and Results, aim at about 60 % figures and 40 % tables.
- A figure or table caption is at most four lines: a title that says what the float shows, plus the one definition a reader needs to read it. Notation and further definitions go in a table note below the table or in the text.
- **Every number comes from a record.** Counts from `study/flow.json` or the operator's unit table, estimates from the outputs of the analysis log, planned values (sample size, outcomes, analysis plan) from the locked protocol revision, never recounted or retyped by hand.

## Disqualifiers

- A table of two columns or two rows whose values a bar or pie chart, or the sentence, could carry.
- A step described that has no record: no protocol field, allocation record, dictionary entry, analysis-log entry or operator record behind it.
- A design, eligibility criterion, primary outcome or sample size that differs from the locked protocol without the amendment that changed it.
- A sample size given without its justification, or the achieved numbers reported here instead of in the results.
- An allocation sequence, a unit's assignment or the order of the allocation list stated in the paper, or a randomisation described from a stale or absent allocation record.
- No allocation concealment mechanism, or a concealment the operator's allocation record does not hold.
- No statement of who was blinded, or of who knew the assignment when blinding was not possible.
- An analysis described as planned that the locked analysis plan does not contain, or no statement of which analyses were confirmatory and which exploratory.
- An ethics approval, consent route or registration that the operator's records do not hold, or a registration after the first enrolment not called retrospective with its reason.
- [block: m-field-units, m-mixed-models, m-animals-husbandry] A field-experiment block (`m-field-units`, `m-mixed-models`, `m-animals-husbandry`) written in a workspace of the `human-trial` variant, or `m-animals-husbandry` written for an experiment without animals.
- Subsamples or repeated measurements of one experimental unit counted as replicates.

## Inputs

### External inputs

| Input | Unblocks |
|---|---|
| `outcomes` — The outcomes are the primary and secondary outcomes of the locked protocol, each with its measure, its analysis metric and its time point. | `m-outcomes` |
| `sample` — The sample is the planned number of participants or experimental units of the locked protocol, with its justification. | `m-sample-size` |
| `analysis-plan` — The analysis-plan is the locked protocol's primary analysis, its estimand, the handling of missing data and multiplicity. | `m-statistical-methods` |
| `protocol` — The protocol is the revision the operator locked, named with its location and every amendment to it. | `m-protocol-registration` |
| `study-registration` — The study-registration is stated with the registry, the record, the registration date and the first enrolment. | `m-protocol-registration` |
| `ethics-approval` — The ethics-approval names the committee, the approval code and date, and the consent route the operator recorded. | `m-ethics-consent` |

### Internal chain

None: no block of this section waits on another block.
