---
{
  "section": "abstract",
  "position": 2,
  "mode": {
    "value": "transposition",
    "source": {
      "file": "sections/02-abstract.md",
      "quote": "Every element of the abstract is copied from the methods and the results; the abstract adds nothing."
    }
  },
  "blocks": [
    {
      "id": "abs-background-purpose",
      "requires_facts": [
        {
          "value": "contributions",
          "source": {
            "file": "sections/02-abstract.md",
            "quote": "The background and purpose come from the study's contributions and its research question."
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none",
      "after": [
        {
          "target": "introduction.intro-purpose",
          "source": {
            "file": "sections/02-abstract.md",
            "quote": "The background and purpose come from the study's contributions and its research question."
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
            "quote": "The methods slot follows the methods section: the approach, the setting, the participants or the panel and how they were sampled, the data collection and the analysis."
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
            "quote": "The results slot follows the results section: the main themes, the consensus reached and not reached, or what was done and observed."
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
    }
  ]
}
---

# Abstract (qualitative and participatory line)

SRQR item 2 (a summary of the key elements of the study: background, purpose,
methods, results and conclusions), ACCORD's title and abstract items for a
consensus study. Every element of the abstract is copied from the methods and
the results; the abstract adds nothing. Structured (Background, Methods,
Results, Conclusions) unless the venue asks for one paragraph; the venue's
word limit wins over the extent below.

**Extent** 200–350 words · the venue's structured headings, or one paragraph

## Slot `abs-background-purpose`

The background and purpose come from the study's contributions and its
research question. One or two sentences: why the phenomenon matters and the
purpose or the research question.

## Slot `abs-methods`

The methods slot follows the methods section: the approach, the setting, the
participants or the panel and how they were sampled, the data collection and
the analysis. For a consensus study, the panel, the number of rounds and the
pre-specified consensus threshold; for an experience report, the setting and
the period.

## Slot `abs-results`

The results slot follows the results section: the main themes, the consensus
reached and not reached, or what was done and observed. A theme is named as
the results name it; a quote in the abstract is verbatim, with its participant
code, or left out.

## Slot `abs-conclusions`

The limitations of what is reported come from the limitations section. One
sentence on the main limitation and one on the implications, no stronger than
the material allows; an experience report claims no effect.

## LIA house style

No paper of this line has been measured yet: the rules below carry the group's writing rules from the experimental and review lines to a qualitative, participatory or consensus study, and the extent at the top of this contract stays the target. They read the records the line keeps: the locked protocol revision `protocol/study-protocol-<slug>-vNN.md` and `study/protocol.lock.json` when the study has one, the ethics record `study/ethics.json`, the transcript register `study/transcripts.json`, the codebook versions `study/codebook.json`, the theme sign-offs `study/themes.json` and, for a consensus study, the panel, plan, rounds and MICMAC records under `study/consensus/`.

**Measured size.** None yet; an SRQR summary of this extent fills each structured heading in one to three sentences.

**Human boundaries (every section of this line).**

- **No generated data.** The assistant never generates data, never writes or edits a transcript, never invents or polishes a quote and never enters a rating: every participant code, count, theme, quote, rating, agreement figure and MICMAC rank in the paper comes from the operator's records (the transcripts the operator registered, the codebook versions and the signed-off themes, the panel, plan and rounds under `study/consensus/`), never from a model or from a paraphrase presented as a participant's words. A participant is named only by the code the register holds, and a quote is the transcript's own words, verbatim, written `\pquote{<code>}{<text>}`. A value without a record is left out and reported as missing.
- **Human decisions.** The decisions on ethics, consent, data collection and the analytic sign-off stay human: the paper reports the operator's ethics record and consent route, how the operator recruited the participants or the panel and collected the material, the codebook versions the operator recorded and the themes or consensus results the operator signed off or recorded, and never proposes, changes or completes any of them. The assistant may propose codes and themes in a draft; only the operator's record makes them the study's.

**Writing (every section of this line).**

- **Sentences average 18–27 words.** One claim and its qualifier per sentence.
- **One voice.** First person plural for what the researchers did (*we interviewed*, *we coded*), past tense for every step that was run, present tense for what the themes or the panel's results show.
- **Citations are numeric, in square brackets, and close the claim they support** (`[4]`, `[7,9]`, `[12–15]`). A citation is never the grammatical subject of a sentence.
- **Claims stay within the material.** A theme is an interpretation of the coded material supported by the participants' own words, never a count of how many said something presented as prevalence; a consensus is the agreement the rounds measured against the pre-specified threshold, never a majority read as consensus; an experience report describes what happened and what it taught, never an effect it did not evaluate.
- **Transitions come from the relation between claims.** A stock connector (*In addition*, *Furthermore*, *Additionally*, *Moreover*) is the exception: never the same one twice within five sentences.
- **No promotional adjectives.** *Revolutionary*, *transformative*, *pivotal*, *comprehensive*, *crucial*, *novel* say nothing a reader can check; state what the material shows instead.
- **A table has at least three columns and three rows.** A two-column or two-row table is a grid with nothing to cross: counts across categories become a bar chart, the shares of one whole (at most six parts) a pie chart, and one or two values go in the sentence. The chart is drawn by a script from the study's records, its provenance recorded with `paper_cli.py figure provenance`, and placed with `paper_cli.py place`.
- **Every number comes from a record.** Counts of participants and transcripts from `study/transcripts.json` or the panel record, agreement, medians and interquartile ranges from the recorded round results, MICMAC ranks from the recorded computation, planned values (sample, rounds, threshold) from the locked protocol and the consensus plan, never recounted or retyped by hand.

## Disqualifiers

- A number of participants, panel members, rounds or items that differs from the operator's records.
- A theme, consensus result or lesson that the results do not report.
- A participant quote that the results do not report verbatim with its code.
- A consensus claimed for an item below the pre-specified threshold.
- An effect of the innovation claimed in an experience report.
- A citation, or a claim the body does not make.

## Inputs

### External inputs

| Input | Unblocks |
|---|---|
| `contributions` — The background and purpose come from the study's contributions and its research question. | `abs-background-purpose` |
| `limitations` — The limitations of what is reported come from the limitations section. | `abs-conclusions` |

### Internal chain

| Block | Depends on |
|---|---|
| `abstract.abs-background-purpose` — The background and purpose come from the study's contributions and its research question. | `introduction.intro-purpose` |
| `abstract.abs-conclusions` — The limitations of what is reported come from the limitations section. | `limitations.lim-reported` |
