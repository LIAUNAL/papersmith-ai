---
{
  "section": "introduction",
  "position": 3,
  "mode": {
    "value": "argument",
    "source": {
      "file": "sections/03-introduction.md",
      "quote": "The introduction argues why this question needs this trial and states what the trial set out to estimate."
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
            "quote": "The problem-statement says what is not yet known about the intervention, its comparator and the outcome, and why it matters."
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
            "quote": "The gap is what the existing trials and experiments leave unanswered for this population or system."
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
            "quote": "The gap is what the existing trials and experiments leave unanswered for this population or system."
          }
        }
      ],
      "produces_facts": [
        {
          "value": "gap",
          "source": {
            "file": "sections/03-introduction.md",
            "quote": "The gap is what the existing trials and experiments leave unanswered for this population or system."
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

# Introduction (experiment and intervention line)

CONSORT 2025 items 6 (background and rationale) and 7 (objectives on benefits
and harms), ARRIVE 2.0 items 12 and 13. The introduction argues why this question needs this trial and states what the trial set out to estimate.

**Extent** 450–900 words · 4 to 6 paragraphs

## Block `intro-context`

The problem-statement says what is not yet known about the intervention, its comparator and the outcome, and why it matters. The burden of the condition or the problem of the system, the
decision a clinician, teacher, producer or manager faces, and the effect
estimate that would inform it. Every claim is cited from the literature;
nothing here comes from this trial's data. For a field experiment, the
agronomic, ecological or animal question and why a controlled experiment
answers it.

## Block `intro-evidence-gap`

The gap is what the existing trials and experiments leave unanswered for this population or system. Name the closest trials, systematic reviews or experiments and
what each estimated, in which population or system and with which design, and
say what remains open: an intervention never compared with this comparator,
an effect estimated imprecisely or inconsistently, a population or setting not
studied, a harm never measured. Equipoise is stated from that evidence. A gap
is never a lack stated without the studies that leave it open.

## Block `intro-objectives`

The contributions are the objectives of the locked protocol and the prespecified hypotheses. They are written as one paragraph of 100–200 words in running
prose: the research question of `protocol/study-protocol-<slug>-vNN.md`, the
primary outcome with its time point, the secondary outcomes, the harms the
protocol set out to assess, and each hypothesis the protocol states before the
data were analysed, with its framework (superiority, non-inferiority or
equivalence). A hypothesis formed after seeing the data is never presented
here; it belongs to the ancillary analyses of the results. No numbered or
bulleted list of contributions.

## Block `intro-skeleton`

The skeleton is the order of the sections that follow. One agenda paragraph, one sentence per section, opened by *The
remainder of this paper is organized as follows:*. Omit it when the venue's
structure makes it redundant.

## LIA house style

No paper of this line has been measured yet: the rules below carry the group's writing rules from the experimental and review lines to a trial or a controlled experiment, and the extent at the top of this contract stays the target. They read the records the line keeps: the locked protocol revision `protocol/study-protocol-<slug>-vNN.md` and `study/protocol.lock.json`, the ethics and registration records under `study/`, the operator's allocation record `study/allocation.json`, the data dictionaries and quality reports under `datasets/`, the analysis log `analysis/log.jsonl` and the flow counts `study/flow.json`.

**Measured size.** None yet; a CONSORT introduction of this extent runs from the problem to the evidence gap to the objectives paragraph.

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

- A claim of the background without a citation that holds it.
- A result of this trial reported in the introduction: results belong to the results section.
- A gap stated as a lack (*few trials have examined*) without naming the closest studies and what each leaves open.
- An objective, outcome or hypothesis that the locked protocol does not state, or a primary outcome other than the protocol's.
- Objectives that name benefits and no harms when the protocol set out to assess harms.
- A hypothesis presented as prespecified when it was formed after the data were seen.
- Contributions given as a numbered or bulleted list instead of the objectives paragraph.
- A roadmap that names a section that does not exist, or skips one.

## Inputs

### External inputs

| Input | Unblocks |
|---|---|
| `problem-statement` — The gap is what the existing trials and experiments leave unanswered for this population or system. | `intro-evidence-gap` |
| `gap` — The contributions are the objectives of the locked protocol and the prespecified hypotheses. | `intro-objectives` |
| `skeleton` — The skeleton is the order of the sections that follow. | `intro-skeleton` |

### Internal chain

| Block | Depends on |
|---|---|
| `introduction.intro-evidence-gap` — The gap is what the existing trials and experiments leave unanswered for this population or system. | `introduction.intro-context` |
| `introduction.intro-objectives` — The contributions are the objectives of the locked protocol and the prespecified hypotheses. | `introduction.intro-evidence-gap` |
