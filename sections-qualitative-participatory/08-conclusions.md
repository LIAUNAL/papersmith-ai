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
            "quote": "The contributions are answered in the order of the research questions, each by its reported finding."
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
            "quote": "The contributions are answered in the order of the research questions, each by its reported finding."
          }
        },
        {
          "target": "introduction.intro-purpose",
          "source": {
            "file": "sections/08-conclusions.md",
            "quote": "The contributions are answered in the order of the research questions, each by its reported finding."
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
        }
      ]
    }
  ]
}
---

# Conclusions (qualitative and participatory line)

SRQR item 18 (contribution to the field). Conclusions add nothing: every claim
already exists earlier in the paper.

**Extent** 150–400 words · 2 or 3 paragraphs

## Block `concl-answers`

The contributions are answered in the order of the research questions, each by
its reported finding. One or two sentences per research question: the theme,
the consensus or the lesson that answers it, worded as the material allows,
with no effect claimed for an experience report.

## Block `concl-future`

The limitations bound every conclusion; each future direction answers one of
them. Two to four directions (a perspective or a setting not yet heard, a
further panel or round, a formal evaluation of the innovation an experience
report described), each citing a reference that supports it.

## LIA house style

No paper of this line has been measured yet: the rules below carry the group's writing rules from the experimental and review lines to a qualitative, participatory or consensus study, and the extent at the top of this contract stays the target. They read the records the line keeps: the locked protocol revision `protocol/study-protocol-<slug>-vNN.md` and `study/protocol.lock.json` when the study has one, the ethics record `study/ethics.json`, the transcript register `study/transcripts.json`, the codebook versions `study/codebook.json`, the theme sign-offs `study/themes.json` and, for a consensus study, the panel, plan, rounds and MICMAC records under `study/consensus/`.

**Measured size.** None yet; a conclusion of this extent answers the research questions in one paragraph and names the directions in another.

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

- A new claim, a new number, or a number that differs from the results.
- A research question without its answer, or a conclusion that rests on a theme the operator did not sign off.
- An effect of the innovation claimed in an experience report.
- A future direction that answers no limitation, or one without a reference that supports it.
- A closing appeal (*further research is needed*) in place of a direction.

## Inputs

### External inputs

| Input | Unblocks |
|---|---|
| `contributions` — The contributions are answered in the order of the research questions, each by its reported finding. | `concl-answers` |
| `limitations` — The limitations bound every conclusion; each future direction answers one of them. | `concl-future` |

### Internal chain

| Block | Depends on |
|---|---|
| `conclusions.concl-answers` — The contributions are answered in the order of the research questions, each by its reported finding. | `introduction.intro-purpose` |
| `conclusions.concl-future` — The limitations bound every conclusion; each future direction answers one of them. | `limitations.lim-reported` |
