---
{
  "section": "title-and-keywords",
  "position": 1,
  "mode": {
    "value": "transposition",
    "source": {
      "file": "sections/01-title-and-keywords.md",
      "quote": "The title names the design with the words the methods use."
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
            "quote": "The contributions of the trial, its objectives and the intervention it tested, decide the title."
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
            "quote": "The contributions of the trial, its objectives and the intervention it tested, decide the title."
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

# Title and Keywords (experiment and intervention line)

CONSORT 2025 item 1 (the title identifies the study as a randomised trial).
The title names the design with the words the methods use.
A trial with people says that it is a randomised trial, and a cluster,
crossover, factorial or non-inferiority trial says which; a field experiment
names its design (a randomised complete block, split-plot or Latin square
experiment) and the crop, species or system studied.

**Extent** 10–25 words · keywords 4–6

## Block `title`

The contributions of the trial, its objectives and the intervention it tested, decide the title. The title states the intervention and its comparator, the outcome
domain, the population or the experimental system and the design, in this
order: "<intervention> versus <comparator> for <outcome> in <population or
system>: a <design>". No claim of benefit, no question form, no result stated
as a verb (*X improves Y*), and no acronym that the abstract does not expand.

## Block `keywords`

The keyword-bounds and the classification-line come from the venue. Four to six keywords, none repeating a word of the title, the design
included as one of them (*randomised controlled trial*, *cluster randomised
trial*, *randomised complete block design*).

## LIA house style

No paper of this line has been measured yet: the rules below carry the group's writing rules from the experimental and review lines to a trial or a controlled experiment, and the extent at the top of this contract stays the target. They read the records the line keeps: the locked protocol revision `protocol/study-protocol-<slug>-vNN.md` and `study/protocol.lock.json`, the ethics and registration records under `study/`, the operator's allocation record `study/allocation.json`, the data dictionaries and quality reports under `datasets/`, the analysis log `analysis/log.jsonl` and the flow counts `study/flow.json`.

**Measured size.** None yet; a CONSORT title of this group's empirical work runs 12 to 20 words in two parts joined by a colon.

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

- [block: title] A title of a trial with people that does not say it is randomised, or a field-experiment title that names no design.
- [block: title] A title that states the result (*X improves Y*, *X is effective for Y*).
- [block: title] A promotional or evaluative word in the title (*Novel*, *Revolutionizing*, *Comprehensive*).
- [block: title, keywords] A keyword that repeats a word of the title.
- [block: title] An acronym in the title that the abstract does not expand.

## Sources

- The locked protocol revision (`protocol/study-protocol-<slug>-vNN.md`): the intervention, the comparator, the design and the primary outcome, which fix the words of the title.

## Inputs

### External inputs

| Input | Unblocks |
|---|---|
| `contributions` — The contributions of the trial, its objectives and the intervention it tested, decide the title. | `title` |
| `keyword-bounds` — The keyword-bounds and the classification-line come from the venue. | `keywords` |
| `classification-line` — The keyword-bounds and the classification-line come from the venue. | `keywords` |

### Internal chain

| Block | Depends on |
|---|---|
| `title-and-keywords.title` — The contributions of the trial, its objectives and the intervention it tested, decide the title. | `introduction.intro-objectives` |
