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

# Discussion (observational and measurement studies line)

STROBE items 18, 20 and 21, STARD 2015 items 26 and 27, COSMIN 2.0 discussion
items. The discussion interprets the reported results against the objectives and against other studies, and states no result the results section does not report.
The limitations have their own section; the discussion refers to them where
they bound an interpretation.

**Extent** 600–1300 words · 4 to 7 paragraphs

## Block `d-key-results`

STROBE item 18. The contributions are revisited one by one with the confirmatory result that answers each objective.
One or two sentences per objective, in the order of the introduction, each
stating the estimate already reported and its direction, never a new number.
A result the analysis log labels exploratory is named as exploratory here too.

## Block `d-interpretation`

STROBE item 20, COSMIN 2.0 discussion items. The gap the introduction stated is the yardstick: say how far the results close it.
A cautious overall interpretation that weighs the objectives, the
limitations, the multiplicity of analyses and the results of similar studies:
compare each key result with the closest studies named in the introduction,
what agrees, what differs and the likely reason (population, setting, design,
measurement). Every comparison cites the study it compares with. An
association is not interpreted as an effect, and an alternative explanation
(confounding, selection, measurement error, chance) is discussed before it is
set aside.

## Block `d-generalizability`

STROBE item 21. The external validity of the results: to which populations,
settings and uses they apply, given who was recruited, where and when, and
which they do not reach. For a diagnostic accuracy study, the intended use and
the clinical role of the index test in that light; for a measurement
instrument, the populations and contexts in which its measurement properties
now have evidence.

## Block `d-implications`

STARD 2015 item 27. What the results mean for practice, for policy or for
further research, each implication traceable to a reported result and no
stronger than the design allows: an observational association supports a
hypothesis to test, not a recommendation to intervene.

## LIA house style

No paper of this line has been measured yet: the rules below carry the group's writing rules from the experimental and review lines to an observational or measurement study, and the extent at the top of this contract stays the target. They read the records the line keeps: the locked protocol revision `protocol/study-protocol-<slug>-vNN.md` and `study/protocol.lock.json`, the ethics and registration records under `study/`, the data dictionaries and quality reports under `datasets/`, the analysis log `analysis/log.jsonl` and the participant flow counts `study/flow.json`.

**Measured size.** None yet; the extent above follows the group's method papers, whose discussions run four to seven paragraphs.

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

- A result or a number that the results section does not report.
- A claim about other studies without a citation that holds it.
- A causal interpretation of an observational association whose analysis plan names no causal estimand.
- An exploratory result discussed as if it were confirmatory.
- No comparison with the closest studies the introduction named.
- A generalization to a population or setting the study did not recruit from.
- An implication or recommendation stronger than the design allows, or a closing appeal with no result behind it.

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
