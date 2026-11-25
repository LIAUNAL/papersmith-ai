---
{
  "section": "introduction",
  "position": 3,
  "mode": {
    "value": "argument",
    "source": {
      "file": "sections/03-introduction.md",
      "quote": "The introduction argues why this question needs this study and states what the study set out to measure or simulate."
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
            "quote": "The problem-statement says what is not yet known about the material, the process or the system, and why it matters."
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
            "quote": "The gap is what the existing studies leave unanswered for this material, process or model."
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
            "quote": "The gap is what the existing studies leave unanswered for this material, process or model."
          }
        }
      ],
      "produces_facts": [
        {
          "value": "gap",
          "source": {
            "file": "sections/03-introduction.md",
            "quote": "The gap is what the existing studies leave unanswered for this material, process or model."
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

# Introduction (lab and simulation line)

The introduction argues why this question needs this study and states what the study set out to measure or simulate.

**Extent** 450–900 words · 4 to 6 paragraphs

## Block `intro-context`

The problem-statement says what is not yet known about the material, the process or the system, and why it matters. The application or the physical question, the property or the quantity
that decides it, and why its value, or its value under these conditions, is
needed. Every claim is cited from the literature; nothing here comes from this
study's data.

## Block `intro-evidence-gap`

The gap is what the existing studies leave unanswered for this material, process or model. Name the closest studies and what each measured or simulated, on which
material or system, with which method and with which uncertainty, and say what
remains open: a composition or a process window not covered, values that
disagree beyond their stated uncertainties, a quantity reported without its
uncertainty, a model never checked against known values. A gap is never a lack
stated without the studies that leave it open.

## Block `intro-objectives`

The contributions are the objectives of the locked protocol and the prespecified hypotheses. They are written as one paragraph of 100–200 words in running prose:
the research question of `protocol/study-protocol-<slug>-vNN.md`, the primary
observable, the secondary observables, and each hypothesis the protocol states
before the data or the runs existed. A hypothesis formed after seeing the
results is never presented here; it belongs to the exploratory analyses of the
results. No numbered or bulleted list of contributions.

## Block `intro-skeleton`

The skeleton is the order of the sections that follow. One agenda paragraph, one sentence per section, opened by *The remainder
of this paper is organized as follows:*. Omit it when the venue's structure
makes it redundant.

## LIA house style

No paper of this line has been measured yet: the rules below carry the group's writing rules from the experimental and observational lines to a laboratory or simulation study, and the extent at the top of this contract stays the target. They read the records the line keeps: the locked protocol revision `protocol/study-protocol-<slug>-vNN.md` and `study/protocol.lock.json`, the instrument records `study/instruments.json`, the raw data registrations `study/measurements.json`, the uncertainty budgets `study/uncertainty/<quantity>.json` and the analysis log `analysis/log.jsonl`.

**Measured size.** None yet; the extent above follows the group's method papers, whose introductions run four to six paragraphs.

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

- A claim of the background without a citation that holds it.
- A result of this study reported in the introduction: results belong to the results section.
- A gap stated as a lack (*few studies have examined*) without naming the closest studies and what each leaves open.
- An objective, observable or hypothesis that the locked protocol does not state, or a primary observable other than the protocol's.
- A hypothesis presented as prespecified when it was formed after the results were seen.
- Contributions given as a numbered or bulleted list instead of the objectives paragraph.
- A roadmap that names a section that does not exist, or skips one.
- A citation used as the subject of a sentence.

## Inputs

### External inputs

| Input | Unblocks |
|---|---|
| `problem-statement` — The gap is what the existing studies leave unanswered for this material, process or model. | `intro-evidence-gap` |
| `gap` — The contributions are the objectives of the locked protocol and the prespecified hypotheses. | `intro-objectives` |
| `skeleton` — The skeleton is the order of the sections that follow. | `intro-skeleton` |

### Internal chain

| Block | Depends on |
|---|---|
| `introduction.intro-evidence-gap` — The gap is what the existing studies leave unanswered for this material, process or model. | `introduction.intro-context` |
| `introduction.intro-objectives` — The contributions are the objectives of the locked protocol and the prespecified hypotheses. | `introduction.intro-evidence-gap` |
