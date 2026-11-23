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

# Conclusions (observational and measurement studies line)

COSMIN 2.0 conclusions item; STROBE and STARD 2015 carry it in the discussion.
Conclusions add nothing: every claim already exists earlier in the paper.

**Extent** 150–400 words · 2 or 3 paragraphs

## Block `concl-answers`

The contributions are answered in the order of the objectives, each by its confirmatory result.
One or two sentences per objective, worded as the design allows: an
association for an observational study, an accuracy estimate for a diagnostic
study, a statement of which measurement properties have sufficient evidence
for an instrument.

## Block `concl-future`

The limitations bound every conclusion; each future direction answers one of them.
Two to four directions (a design that would address the confounding, a
population not yet studied, a property not yet evaluated, a confirmatory study
of an exploratory finding), each citing a reference that supports it.

## LIA house style

No paper of this line has been measured yet: the rules below carry the group's writing rules from the experimental and review lines to an observational or measurement study, and the extent at the top of this contract stays the target. They read the records the line keeps: the locked protocol revision `protocol/study-protocol-<slug>-vNN.md` and `study/protocol.lock.json`, the ethics and registration records under `study/`, the data dictionaries and quality reports under `datasets/`, the analysis log `analysis/log.jsonl` and the participant flow counts `study/flow.json`.

**Measured size.** None yet; the group's method papers close in two or three paragraphs.

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

- A new claim, a new number, or a number that differs from the results.
- An objective without its answer, or a conclusion drawn from an exploratory analysis.
- A causal conclusion from an observational design whose analysis plan names no causal estimand.
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
