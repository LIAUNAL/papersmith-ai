---
{
  "section": "results",
  "position": 5,
  "mode": {
    "value": "transposition",
    "source": {
      "file": "sections/05-results.md",
      "quote": "Every count comes from study/flow.json or the operator's unit table and every estimate from an output the analysis log hashes."
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
            "quote": "The participant-flow is the operator's counts of units randomised, receiving the intervention, followed and analysed in each arm, checked and signed."
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none",
      "optional": true
    },
    {
      "id": "r-units-table",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none",
      "optional": true
    },
    {
      "id": "r-recruitment",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none"
    },
    {
      "id": "r-baseline",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none"
    },
    {
      "id": "r-outcomes-estimation",
      "requires_facts": [
        {
          "value": "outcomes",
          "source": {
            "file": "sections/05-results.md",
            "quote": "The outcomes of the locked protocol are reported in its order, the primary outcome first, for each group with the number analysed."
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none"
    },
    {
      "id": "r-harms",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none"
    },
    {
      "id": "r-ancillary",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none"
    }
  ]
}
---

# Results (experiment and intervention line)

CONSORT 2025 items 22 to 28, ARRIVE 2.0 items 3, 10 and 16. Every count comes from study/flow.json or the operator's unit table and every estimate from an output the analysis log hashes.
The results report; interpretation, comparison with other studies and
implications wait for the discussion.

**Extent** 900–2200 words · the flow diagram or the unit table, one table of baseline characteristics, one table per outcome family

## Block `r-participant-flow` (variant `human-trial`, required there; optional otherwise)

CONSORT 2025 item 22. The participant-flow is the operator's counts of units randomised, receiving the intervention, followed and analysed in each arm, checked and signed.
Required in a workspace of the `human-trial` variant: a trial with people
always reports its flow. The block graph declares this block optional because
a field experiment may never keep a flow; for a `human-trial` workspace the
requirement is enforced by the command center board's G-FLOW gate, not by the
block graph: the gate stays failed while the flow is missing, its counts
inconsistent, or its figure stale or unsigned. For each group, the numbers randomly
assigned, receiving the intended intervention, followed up and analysed for
the primary outcome, with the losses and exclusions after randomisation and
their reasons, copied from `study/flow.json`. The flow diagram
`paper/Figures/participant-flow.svg`, drawn from those counts by `python
skills/_core/participant_flow/flow_cli.py render --root .` and signed by the
operator (`flow_cli.py signoff --by <operator>`), is cited here before it
appears; `flow_cli.py status --root .` must report the figure current and the
sign-off current before the block is drafted. A `field-experiment` workspace
writes this block only when the operator kept a flow, and otherwise reports
its units in `r-units-table`. The assistant never enters, corrects or
completes a count: an inconsistent count goes back to the operator.

## Block `r-units-table` (variant `field-experiment`, optional)

Written only in a workspace of the `field-experiment` variant (ARRIVE 2.0
items 3 and 10); a `human-trial` workspace reports its flow in
`r-participant-flow` instead. One table, from the operator's records, with a
row per treatment and columns for the experimental units allocated, the units
excluded or lost with their reasons, and the units analysed for each outcome;
the experimental unit is the one `m-field-units` named.

## Block `r-recruitment`

CONSORT 2025 items 23 and 24. The dates of the periods of recruitment and
follow-up (for a field experiment, of sowing or arrival, of each treatment
application and of harvest or the end of the experiment), and why the trial
ended or was stopped. Then how the intervention and the comparator were
actually delivered: adherence and any departure from what was planned.

## Block `r-baseline`

CONSORT 2025 item 25. A table of the baseline characteristics of each group
(demographic and clinical, or the initial state of the units), with the number
of units with missing data for each. Baseline differences are described, never
tested for significance.

## Block `r-outcomes-estimation`

CONSORT 2025 item 26, ARRIVE 2.0 item 10. The outcomes of the locked protocol are reported in its order, the primary outcome first, for each group with the number analysed.
Only entries that `analysis/log.jsonl` labels confirmatory support a
confirmatory claim (`python skills/_core/empirical/analysis_cli.py status
--root .`): for each outcome, the result in each group and the estimated
effect with its 95% confidence interval, cited from the output of such an
entry; for a binary outcome, both the absolute and the relative effect. The
denominator of each analysis is stated and whether it was the analysis
population the plan defined. A planned outcome that was not analysed is
reported as not analysed, with the reason, never dropped.

## Block `r-harms`

CONSORT 2025 item 27, ARRIVE 2.0 item 16. All important harms or unintended
effects in each group, with the number of units affected and the number of
events, as the operator recorded them; for an experiment with animals, the
adverse events and the animals that reached a humane end point. A trial that
assessed harms and observed none says so; one that did not assess them says
that too.

## Block `r-ancillary`

CONSORT 2025 item 28. Every other analysis done (subgroups, sensitivity
analyses, adjusted analyses not in the plan), each labelled exploratory as
`analysis/log.jsonl` labels it, with the reason the log gives (no entry of the
locked analysis plan, or no current protocol lock when it ran). An exploratory
result is stated with its estimate and precision and called hypothesis
generating; it never supports a confirmatory claim in the abstract, the
discussion or the conclusions.

## LIA house style

No paper of this line has been measured yet: the rules below carry the group's writing rules from the experimental and review lines to a trial or a controlled experiment, and the extent at the top of this contract stays the target. They read the records the line keeps: the locked protocol revision `protocol/study-protocol-<slug>-vNN.md` and `study/protocol.lock.json`, the ethics and registration records under `study/`, the operator's allocation record `study/allocation.json`, the data dictionaries and quality reports under `datasets/`, the analysis log `analysis/log.jsonl` and the flow counts `study/flow.json`.

**Measured size.** None yet; a CONSORT results section of this extent opens on the flow figure, then the baseline table and one table per outcome family.

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

- A table of two columns or two rows whose values a bar or pie chart, or the sentence, could carry.
- A `human-trial` paper whose results leave `r-participant-flow` unopened, or a flow figure that is stale or not signed by the operator.
- A unit table (`r-units-table`) written in a workspace of the `human-trial` variant, or a field-experiment paper that reports neither its flow nor its unit table.
- A count that differs from `study/flow.json` or the operator's records.
- An estimate with no analysis-log entry whose output holds it, or without its confidence interval.
- A confirmatory claim supported by an entry the analysis log labels exploratory.
- An exploratory or subgroup analysis not labelled exploratory, or presented as a main result.
- A primary outcome other than the locked protocol's, or a planned outcome silently left out.
- No harms reported, or harms reported without the number of units affected in each group.
- Baseline differences tested for significance.
- An interpretation, a comparison with other studies or a recommendation: those belong to the discussion.

## Inputs

### External inputs

| Input | Unblocks |
|---|---|
| `participant-flow` — The participant-flow is the operator's counts of units randomised, receiving the intervention, followed and analysed in each arm, checked and signed. | `r-participant-flow` |
| `outcomes` — The outcomes of the locked protocol are reported in its order, the primary outcome first, for each group with the number analysed. | `r-outcomes-estimation` |

### Internal chain

None: no block of this section waits on another block.
