---
{
  "section": "title-and-keywords",
  "position": 1,
  "mode": {
    "value": "transposition",
    "source": {
      "file": "sections/01-title-and-keywords.md",
      "quote": "The title names the study design with the words the methods use."
    }
  },
  "blocks": [
    {
      "id": "title",
      "requires_facts": [
        {
          "value": "contributions",
          "source": {
            "file": "sections/01-title-and-keywords.md",
            "quote": "The contributions of the study, its objectives and what it measured, decide the title."
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none",
      "after": [
        {
          "target": "introduction.intro-objectives",
          "source": {
            "file": "sections/01-title-and-keywords.md",
            "quote": "The contributions of the study, its objectives and what it measured, decide the title."
          }
        }
      ]
    },
    {
      "id": "keywords",
      "requires_facts": [],
      "requires_declarations": [
        {
          "value": "keyword-bounds",
          "source": {
            "file": "sections/01-title-and-keywords.md",
            "quote": "The keyword-bounds and the classification-line come from the venue."
          }
        },
        {
          "value": "classification-line",
          "source": {
            "file": "sections/01-title-and-keywords.md",
            "quote": "The keyword-bounds and the classification-line come from the venue."
          }
        }
      ],
      "citations": "none"
    }
  ]
}
---

# Title and Keywords (observational and measurement studies line)

STROBE item 1a, STARD 2015 item 1 and COSMIN 2.0 item T1. The title names the study design with the words the methods use.
A cohort, case-control or cross-sectional study says which; a diagnostic
accuracy study says that it estimates diagnostic accuracy and names at least
one accuracy measure; a measurement-instrument study says that it evaluates
measurement properties of a named instrument, for a stated construct and
population.

**Extent** 10–25 words · keywords 4–6

## Block `title`

The contributions of the study, its objectives and what it measured, decide the title. The title states what was measured or estimated (the exposure and the outcome,
the index test and the target condition, or the instrument and its construct),
the population and setting, and the design, in this order: "<what was measured>
in <population and setting>: a <design> study". No claim of novelty, no
question form, no result stated as a verb (*X reduces Y*), and no acronym that
the abstract does not expand.

## Block `keywords`

The keyword-bounds and the classification-line come from the venue. Four to
six keywords, none repeating a word of the title, the design included as one
of them (*cross-sectional study*, *diagnostic accuracy*, *measurement
properties*).

## LIA house style

No paper of this line has been measured yet: the rules below carry the group's writing rules from the experimental and review lines to an observational or measurement study, and the extent at the top of this contract stays the target. They read the records the line keeps: the locked protocol revision `protocol/study-protocol-<slug>-vNN.md` and `study/protocol.lock.json`, the ethics and registration records under `study/`, the data dictionaries and quality reports under `datasets/`, the analysis log `analysis/log.jsonl` and the participant flow counts `study/flow.json`.

**Measured size.** None yet; a STROBE or STARD title of this group's empirical work runs 12 to 20 words in two parts joined by a colon.

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

- A title that does not name the design (cohort, case-control, cross-sectional, diagnostic accuracy, measurement properties).
- A title that states a causal effect the design cannot support (*X reduces Y*, *the impact of X on Y*) for an observational study.
- A promotional or evaluative word in the title (*Novel*, *Revolutionizing*, *Comprehensive*).
- A keyword that repeats a word of the title.
- An acronym in the title that the abstract does not expand.

## Sources

- The locked protocol revision (`protocol/study-protocol-<slug>-vNN.md`): the research question, the design and the primary outcome, which fix the words of the title.

## Inputs

### External inputs

| Input | Unblocks |
|---|---|
| `contributions` — The contributions of the study, its objectives and what it measured, decide the title. | `title` |
| `keyword-bounds` — The keyword-bounds and the classification-line come from the venue. | `keywords` |
| `classification-line` — The keyword-bounds and the classification-line come from the venue. | `keywords` |

### Internal chain

| Block | Depends on |
|---|---|
| `title-and-keywords.title` — The contributions of the study, its objectives and what it measured, decide the title. | `introduction.intro-objectives` |
