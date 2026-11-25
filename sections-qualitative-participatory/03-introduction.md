---
{
  "section": "introduction",
  "position": 3,
  "mode": {
    "value": "argument",
    "source": {
      "file": "sections/03-introduction.md",
      "quote": "The introduction argues why this phenomenon needs this study and states what the study set out to understand."
    }
  },
  "blocks": [
    {
      "id": "intro-problem",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "discovery",
      "produces_facts": [
        {
          "value": "problem-statement",
          "source": {
            "file": "sections/03-introduction.md",
            "quote": "The problem-statement says what is not yet understood about the phenomenon, for whom, and why it matters."
          }
        }
      ]
    },
    {
      "id": "intro-gap",
      "requires_facts": [
        {
          "value": "problem-statement",
          "source": {
            "file": "sections/03-introduction.md",
            "quote": "The gap is what the existing studies leave unexplained for these people, this setting or this question."
          }
        }
      ],
      "requires_declarations": [],
      "citations": "discovery",
      "after": [
        {
          "target": "introduction.intro-problem",
          "source": {
            "file": "sections/03-introduction.md",
            "quote": "The gap is what the existing studies leave unexplained for these people, this setting or this question."
          }
        }
      ],
      "produces_facts": [
        {
          "value": "gap",
          "source": {
            "file": "sections/03-introduction.md",
            "quote": "The gap is what the existing studies leave unexplained for these people, this setting or this question."
          }
        }
      ]
    },
    {
      "id": "intro-purpose",
      "requires_facts": [
        {
          "value": "gap",
          "source": {
            "file": "sections/03-introduction.md",
            "quote": "The contributions are the purpose and the research questions of the study, as the protocol states them when the study has one."
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none",
      "after": [
        {
          "target": "introduction.intro-gap",
          "source": {
            "file": "sections/03-introduction.md",
            "quote": "The contributions are the purpose and the research questions of the study, as the protocol states them when the study has one."
          }
        }
      ],
      "produces_facts": [
        {
          "value": "contributions",
          "source": {
            "file": "sections/03-introduction.md",
            "quote": "The contributions are the purpose and the research questions of the study, as the protocol states them when the study has one."
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

# Introduction (qualitative and participatory line)

SRQR items 3 (problem formulation) and 4 (purpose or research question),
ACCORD's introduction items for a consensus study. The introduction argues why
this phenomenon needs this study and states what the study set out to
understand.

**Extent** 450–900 words · 4 to 6 paragraphs

## Block `intro-problem`

The problem-statement says what is not yet understood about the phenomenon,
for whom, and why it matters. The phenomenon, the people or the setting it
concerns, and the decision, practice or policy that understanding it would
inform. Every claim is cited from the literature; nothing here comes from this
study's material. For a consensus study, the question the panel is asked to
settle and why expert judgement is the evidence available; for an experience
report, the problem in teaching or practice that the innovation answered.

## Block `intro-gap`

The gap is what the existing studies leave unexplained for these people, this
setting or this question. Name the closest qualitative, consensus or
descriptive studies and what each found, with which people, setting and
approach, and say what remains open: a perspective never heard, a setting not
studied, a question on which the evidence disagrees or does not exist, a
practice never described. A gap is never a lack stated without the studies
that leave it open.

## Block `intro-purpose`

The contributions are the purpose and the research questions of the study, as
the protocol states them when the study has one. They are written as one
paragraph of 100–200 words in running prose: the purpose of the study and its
research questions, the paradigm or the theory that frames them when the study
has one, and, for a consensus study, what the panel was asked to agree on. A
question formed after the material was analysed is never presented here as the
study's question. No numbered or bulleted list of contributions.

## Block `intro-skeleton`

The skeleton is the order of the sections that follow. One agenda paragraph,
one sentence per section, opened by *The remainder of this paper is organized
as follows:*. Omit it when the venue's structure makes it redundant.

## LIA house style

No paper of this line has been measured yet: the rules below carry the group's writing rules from the experimental and review lines to a qualitative, participatory or consensus study, and the extent at the top of this contract stays the target. They read the records the line keeps: the locked protocol revision `protocol/study-protocol-<slug>-vNN.md` and `study/protocol.lock.json` when the study has one, the ethics record `study/ethics.json`, the transcript register `study/transcripts.json`, the codebook versions `study/codebook.json`, the theme sign-offs `study/themes.json` and, for a consensus study, the panel, plan, rounds and MICMAC records under `study/consensus/`.

**Measured size.** None yet; an SRQR introduction of this extent runs from the problem to the gap to the purpose paragraph.

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

- A claim of the background without a citation that holds it.
- A finding or a participant quote of this study in the introduction: findings belong to the results.
- A gap stated as a lack (*few studies have explored*) without naming the closest studies and what each leaves open.
- A purpose or a research question that the protocol does not state, when the study has a protocol.
- A question formed after the analysis presented as the study's question.
- Contributions given as a numbered or bulleted list instead of the purpose paragraph.
- A roadmap that names a section that does not exist, or skips one.

## Inputs

### External inputs

| Input | Unblocks |
|---|---|
| `skeleton` — The skeleton is the order of the sections that follow. | `intro-skeleton` |

### Internal chain

The two facts the blocks pass along are produced in this section, not supplied from outside it.

| Block | Depends on |
|---|---|
| `introduction.intro-gap` — needs the `problem-statement`: what is not yet understood about the phenomenon, for whom, and why it matters. | `introduction.intro-problem` — produces the `problem-statement` |
| `introduction.intro-purpose` — needs the `gap`: what the existing studies leave unexplained for these people, this setting or this question. | `introduction.intro-gap` — produces the `gap` |
