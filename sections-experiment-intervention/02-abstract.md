---
{
  "section": "abstract",
  "position": 2,
  "mode": {
    "value": "transposition",
    "source": {
      "file": "sections/02-abstract.md",
      "quote": "Every number in the abstract is copied from the methods and the results; the abstract adds nothing."
    }
  },
  "blocks": [
    {
      "id": "abs-background-objectives",
      "requires_facts": [
        {
          "value": "contributions",
          "source": {
            "file": "sections/02-abstract.md",
            "quote": "The background and objectives come from the trial's contributions and its research question."
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none",
      "after": [
        {
          "target": "introduction.intro-objectives",
          "source": {
            "file": "sections/02-abstract.md",
            "quote": "The background and objectives come from the trial's contributions and its research question."
          }
        }
      ]
    },
    {
      "id": "abs-methods",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none",
      "after": [
        {
          "target": "methods",
          "source": {
            "file": "sections/02-abstract.md",
            "quote": "The methods slot follows the methods section: design, setting, participants or experimental units, the intervention and comparator, the primary outcome, how the units were allocated and who was blinded."
          }
        }
      ]
    },
    {
      "id": "abs-results",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none",
      "after": [
        {
          "target": "results",
          "source": {
            "file": "sections/02-abstract.md",
            "quote": "The results slot follows the results section: the number randomised and analysed in each group and the estimate of the primary outcome with its precision, and the important harms."
          }
        }
      ]
    },
    {
      "id": "abs-conclusions",
      "requires_facts": [
        {
          "value": "limitations",
          "source": {
            "file": "sections/02-abstract.md",
            "quote": "The limitations of what is reported come from the limitations section."
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none",
      "after": [
        {
          "target": "limitations.lim-reported",
          "source": {
            "file": "sections/02-abstract.md",
            "quote": "The limitations of what is reported come from the limitations section."
          }
        }
      ]
    },
    {
      "id": "abs-registration",
      "requires_facts": [],
      "requires_declarations": [
        {
          "value": "study-registration",
          "source": {
            "file": "sections/02-abstract.md",
            "quote": "The study-registration names the registry and the record, or states that the trial was not registered."
          }
        }
      ],
      "citations": "none"
    }
  ]
}
---

# Abstract (experiment and intervention line)

CONSORT 2025 item 1 (a structured abstract, following CONSORT for Abstracts)
and ARRIVE 2.0 item 11. Every number in the abstract is copied from the methods and the results; the abstract adds nothing.
Structured (Background, Methods, Results, Conclusions, Registration) unless the
venue asks for one paragraph; the venue's word limit wins over the extent
below.

**Extent** 200–350 words · the venue's structured headings, or one paragraph

## Slot `abs-background-objectives`

The background and objectives come from the trial's contributions and its research question. One or two sentences: why the question matters and the objective,
with the prespecified hypothesis when the protocol states one.

## Slot `abs-methods`

The methods slot follows the methods section: design, setting, participants or experimental units, the intervention and comparator, the primary outcome, how the units were allocated and who was blinded. For a field experiment, the experimental unit, the blocks and the
number of replicates.

## Slot `abs-results`

The results slot follows the results section: the number randomised and analysed in each group and the estimate of the primary outcome with its precision, and the important harms. Every estimate carries its interval (*95% CI*), never a p-value
alone, and an exploratory result, when one is mentioned, is called
exploratory.

## Slot `abs-conclusions`

The limitations of what is reported come from the limitations section. One sentence on the main limitation and one on the interpretation,
weighing benefits and harms, no stronger than the confirmatory analysis allows.

## Slot `abs-registration`

The study-registration names the registry and the record, or states that the trial was not registered. A trial with people registered after its first enrolment is called
retrospectively registered, with the reason the operator recorded.

## LIA house style

No paper of this line has been measured yet: the rules below carry the group's writing rules from the experimental and review lines to a trial or a controlled experiment, and the extent at the top of this contract stays the target. They read the records the line keeps: the locked protocol revision `protocol/study-protocol-<slug>-vNN.md` and `study/protocol.lock.json`, the ethics and registration records under `study/`, the operator's allocation record `study/allocation.json`, the data dictionaries and quality reports under `datasets/`, the analysis log `analysis/log.jsonl` and the flow counts `study/flow.json`.

**Measured size.** None yet; a CONSORT for Abstracts summary of this extent fills each structured heading in one to three sentences.

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

- No number randomised or analysed per group, or a number that differs from `study/flow.json`.
- A primary estimate without its interval, or a p-value given in place of an estimate.
- A primary outcome other than the one of the locked protocol.
- An exploratory or subgroup result presented as a confirmatory finding.
- No mention of harms in a trial with people.
- A trial with people without its registration, or a retrospective registration not called so.
- A citation, or a claim the body does not make.

## Inputs

### External inputs

| Input | Unblocks |
|---|---|
| `contributions` — The background and objectives come from the trial's contributions and its research question. | `abs-background-objectives` |
| `limitations` — The limitations of what is reported come from the limitations section. | `abs-conclusions` |
| `study-registration` — The study-registration names the registry and the record, or states that the trial was not registered. | `abs-registration` |

### Internal chain

| Block | Depends on |
|---|---|
| `abstract.abs-background-objectives` — The background and objectives come from the trial's contributions and its research question. | `introduction.intro-objectives` |
| `abstract.abs-conclusions` — The limitations of what is reported come from the limitations section. | `limitations.lim-reported` |
