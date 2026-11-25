---
{
  "section": "introduction",
  "position": 3,
  "mode": {
    "value": "argument",
    "source": {
      "file": "sections/03-introduction.md",
      "quote": "The introduction argues why this question needs this study and states what the study set out to measure."
    }
  },
  "blocks": [
    {
      "id": "intro-context",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "discovery",
      "produces_facts": [
        {
          "value": "problem-statement",
          "source": {
            "file": "sections/03-introduction.md",
            "quote": "The problem-statement says what is not yet known about the population, the condition or the measure, and why it matters."
          }
        }
      ]
    },
    {
      "id": "intro-evidence-gap",
      "requires_facts": [
        {
          "value": "problem-statement",
          "source": {
            "file": "sections/03-introduction.md",
            "quote": "The gap is what the existing studies leave unanswered for this population and setting."
          }
        }
      ],
      "requires_declarations": [],
      "citations": "discovery",
      "after": [
        {
          "target": "introduction.intro-context",
          "source": {
            "file": "sections/03-introduction.md",
            "quote": "The gap is what the existing studies leave unanswered for this population and setting."
          }
        }
      ],
      "produces_facts": [
        {
          "value": "gap",
          "source": {
            "file": "sections/03-introduction.md",
            "quote": "The gap is what the existing studies leave unanswered for this population and setting."
          }
        }
      ]
    },
    {
      "id": "intro-objectives",
      "requires_facts": [
        {
          "value": "gap",
          "source": {
            "file": "sections/03-introduction.md",
            "quote": "The contributions are the objectives of the locked protocol and the prespecified hypotheses."
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none",
      "after": [
        {
          "target": "introduction.intro-evidence-gap",
          "source": {
            "file": "sections/03-introduction.md",
            "quote": "The contributions are the objectives of the locked protocol and the prespecified hypotheses."
          }
        }
      ],
      "produces_facts": [
        {
          "value": "contributions",
          "source": {
            "file": "sections/03-introduction.md",
            "quote": "The contributions are the objectives of the locked protocol and the prespecified hypotheses."
          }
        }
      ]
    },
    {
      "id": "intro-skeleton",
      "requires_facts": [
        {
          "value": "skeleton",
          "source": {
            "file": "sections/03-introduction.md",
            "quote": "The skeleton is the order of the sections that follow."
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none"
    }
  ]
}
---

# Introduction (observational and measurement studies line)

STROBE items 2 (background and rationale) and 3 (objectives), STARD 2015
items 3 and 4, COSMIN 2.0 items I1 to I4. The introduction argues why this question needs this study and states what the study set out to measure.

**Extent** 450–900 words · 4 to 6 paragraphs

## Block `intro-context`

The problem-statement says what is not yet known about the population, the condition or the measure, and why it matters. The burden of the condition, the decision a clinician, a manager or a
researcher faces, and the measurement or estimate that would inform it. Every
claim is cited from the literature; nothing here comes from this study's data.
For a diagnostic accuracy study, name the intended use and the clinical role
of the index test (STARD 2015 item 26 asks for it again in the discussion);
for a measurement-instrument study, name the construct, the population and the
context of use the instrument is meant for.

## Block `intro-evidence-gap`

The gap is what the existing studies leave unanswered for this population and setting. Name the closest studies and what each measured, in which population and with
which design, and say what remains open: a population not studied, an
estimate that is imprecise or inconsistent across studies, an instrument whose
measurement properties are unknown in this context, a test never compared
with an accepted reference standard. A gap is never a lack stated without the
studies that leave it open.

## Block `intro-objectives`

The contributions are the objectives of the locked protocol and the prespecified hypotheses. They are written as one paragraph of 100–200 words in running prose: the
research question of `protocol/study-protocol-<slug>-vNN.md`, the primary
outcome with its time point, the secondary outcomes, and each hypothesis the
protocol states before the data were analysed. A hypothesis formed after
seeing the data is never presented here; it belongs to the exploratory
analyses of the results. No numbered or bulleted list of contributions.

## Block `intro-skeleton`

The skeleton is the order of the sections that follow. One agenda paragraph,
one sentence per section, opened by *The remainder of this paper is organized
as follows:*. Omit it when the venue's structure makes it redundant.

## LIA house style

No paper of this line has been measured yet: the rules below carry the group's writing rules from the experimental and review lines to an observational or measurement study, and the extent at the top of this contract stays the target. They read the records the line keeps: the locked protocol revision `protocol/study-protocol-<slug>-vNN.md` and `study/protocol.lock.json`, the ethics and registration records under `study/`, the data dictionaries and quality reports under `datasets/`, the analysis log `analysis/log.jsonl` and the participant flow counts `study/flow.json`.

**Measured size.** None yet; the extent above follows the group's method papers, whose introductions run four to six paragraphs.

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

- A claim of the background without a citation that holds it.
- A result of this study reported in the introduction: results belong to the results section.
- A gap stated as a lack (*few studies have examined*) without naming the closest studies and what each leaves open.
- An objective, outcome or hypothesis that the locked protocol does not state, or a primary outcome other than the protocol's.
- A hypothesis presented as prespecified when it was formed after the data were seen.
- Contributions given as a numbered or bulleted list instead of the objectives paragraph.
- A roadmap that names a section that does not exist, or skips one.
- A citation used as the subject of a sentence.

## Inputs

### External inputs

| Input | Unblocks |
|---|---|
| `problem-statement` — The gap is what the existing studies leave unanswered for this population and setting. | `intro-evidence-gap` |
| `gap` — The contributions are the objectives of the locked protocol and the prespecified hypotheses. | `intro-objectives` |
| `skeleton` — The skeleton is the order of the sections that follow. | `intro-skeleton` |

### Internal chain

| Block | Depends on |
|---|---|
| `introduction.intro-evidence-gap` — The gap is what the existing studies leave unanswered for this population and setting. | `introduction.intro-context` |
| `introduction.intro-objectives` — The contributions are the objectives of the locked protocol and the prespecified hypotheses. | `introduction.intro-evidence-gap` |
