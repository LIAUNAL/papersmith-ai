---
{
  "section": "discussion",
  "position": 6,
  "mode": {
    "value": "argument",
    "source": {
      "file": "sections/06-discussion.md",
      "quote": "The discussion interprets the reported results against the objectives and against other studies, and states no result the results section does not report."
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
      "id": "d-generalizability",
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

# Discussion (experiment and intervention line)

CONSORT 2025 item 29, ARRIVE 2.0 items 17 and 18. The discussion interprets the reported results against the objectives and against other studies, and states no result the results section does not report.
The limitations have their own section; the discussion refers to them where
they bound an interpretation.

**Extent** 600–1300 words · 4 to 7 paragraphs · at least as many figures as tables

## Block `d-key-results`

The contributions are revisited one by one with the confirmatory result that answers each objective. One or two sentences per objective, in the order of the
introduction, each stating the effect estimate already reported and its
precision, never a new number. A result the analysis log labels exploratory is
named as exploratory here too.

## Block `d-interpretation`

CONSORT 2025 item 29, ARRIVE 2.0 item 17. The gap the introduction stated is the yardstick: say how far the results close it.
An interpretation consistent with the results that balances benefits and
harms and weighs the precision of the estimates, the multiplicity of analyses
and the results of other trials: compare each key result with the closest
studies named in the introduction, what agrees, what differs and the likely
reason (population, intervention, comparator, setting, design). Every
comparison cites the study it compares with. A non-significant difference is
not read as evidence of no effect; the confidence interval says which effects
remain compatible with the data.

## Block `d-generalizability`

ARRIVE 2.0 item 18. The external validity of the results: to which
populations, settings, sites, seasons, species or systems they apply, given who
or what was enrolled, where and when, and which they do not reach; for an
animal experiment, its relevance to other species or to people.

## Block `d-implications`

What the results mean for practice, for policy or for further research, each
implication traceable to a reported confirmatory result and weighed against
the harms reported: an exploratory finding supports a hypothesis to test in a
new trial, not a recommendation.

## LIA house style

No paper of this line has been measured yet: the rules below carry the group's writing rules from the experimental and review lines to a trial or a controlled experiment, and the extent at the top of this contract stays the target. They read the records the line keeps: the locked protocol revision `protocol/study-protocol-<slug>-vNN.md` and `study/protocol.lock.json`, the ethics and registration records under `study/`, the operator's allocation record `study/allocation.json`, the data dictionaries and quality reports under `datasets/`, the analysis log `analysis/log.jsonl` and the flow counts `study/flow.json`.

**Measured size.** None yet; a CONSORT discussion of this extent opens on the key results and closes on the implications.

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

- A result or a number that the results section does not report.
- A claim about other studies without a citation that holds it.
- An interpretation that weighs benefits and leaves the harms reported unsaid.
- A non-significant result read as proof of no effect, or an exploratory result discussed as if it were confirmatory.
- No comparison with the closest studies the introduction named.
- A generalization to a population, setting or species the trial did not enrol.
- An implication or recommendation stronger than the confirmatory results allow, or a closing appeal with no result behind it.

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
