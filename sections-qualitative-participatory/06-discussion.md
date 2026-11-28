---
{
  "section": "discussion",
  "position": 6,
  "mode": {
    "value": "argument",
    "source": {
      "file": "sections/06-discussion.md",
      "quote": "The discussion interprets the reported findings against the purpose and against prior work, and states no finding the results section does not report."
    }
  },
  "blocks": [
    {
      "id": "d-key-findings",
      "requires_facts": [
        {
          "value": "contributions",
          "source": {
            "file": "sections/06-discussion.md",
            "quote": "The contributions are revisited one by one with the finding that answers each research question."
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none",
      "after": [
        {
          "target": "results",
          "source": {
            "file": "sections/06-discussion.md",
            "quote": "The contributions are revisited one by one with the finding that answers each research question."
          }
        },
        {
          "target": "introduction.intro-purpose",
          "source": {
            "file": "sections/06-discussion.md",
            "quote": "The contributions are revisited one by one with the finding that answers each research question."
          }
        }
      ]
    },
    {
      "id": "d-integration",
      "requires_facts": [
        {
          "value": "gap",
          "source": {
            "file": "sections/06-discussion.md",
            "quote": "The gap the introduction stated is the yardstick: say how far the findings close it."
          }
        }
      ],
      "requires_declarations": [],
      "citations": "discovery",
      "after": [
        {
          "target": "introduction.intro-gap",
          "source": {
            "file": "sections/06-discussion.md",
            "quote": "The gap the introduction stated is the yardstick: say how far the findings close it."
          }
        }
      ]
    },
    {
      "id": "d-transferability",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "resolution"
    },
    {
      "id": "d-implications",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none"
    },
    {
      "id": "d-experience-lessons",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none",
      "optional": true
    }
  ]
}
---

# Discussion (qualitative and participatory line)

SRQR item 18 (integration with prior work, implications, transferability and
contribution to the field), ACCORD's discussion items. The discussion
interprets the reported findings against the purpose and against prior work,
and states no finding the results section does not report. The limitations
have their own section; the discussion refers to them where they bound an
interpretation.

**Extent** 700–1400 words · 4 to 7 paragraphs · at least as many figures as tables

## Block `d-key-findings`

The contributions are revisited one by one with the finding that answers each
research question. One or two sentences per research question, in the order of
the introduction, each stating a theme, a consensus result or a lesson already
reported, never a new one.

## Block `d-integration`

SRQR item 18. The gap the introduction stated is the yardstick: say how far
the findings close it. Integrate the findings with prior work and theory:
compare each main finding with the closest studies the introduction named,
what agrees, what differs and the likely reason (people, setting, approach,
period), and how the findings support, elaborate or challenge earlier
conclusions or theory. Every comparison cites the study it compares with.

## Block `d-transferability`

SRQR item 18. The transferability of the findings: to which people, settings
and conditions they may apply, given who took part, where and when, described
richly enough that a reader can judge the fit with their own context, and
which they do not reach. A qualitative finding is never generalised
statistically to a population, and a consensus speaks for its panel, not for
every expert.

## Block `d-implications`

What the findings mean for practice, policy, teaching or further research,
each implication traceable to a reported finding: a theme or a consensus
supports a recommendation only as far as its material and its panel allow, and
an experience report offers what it taught as a lesson for others to try, not
as a proven result.

## Block `d-experience-lessons` (variant `experience-report`, optional)

Written only in a workspace of the `experience-report` variant; another
workspace leaves it unopened. It reflects on what it taught: what worked and
what did not, what the authors would change, the conditions another team would
need to adapt it, and the questions a formal evaluation would have to answer,
each lesson traced to what the results report.

## LIA house style

No paper of this line has been measured yet: the rules below carry the group's writing rules from the experimental and review lines to a qualitative, participatory or consensus study, and the extent at the top of this contract stays the target. They read the records the line keeps: the locked protocol revision `protocol/study-protocol-<slug>-vNN.md` and `study/protocol.lock.json` when the study has one, the ethics record `study/ethics.json`, the transcript register `study/transcripts.json`, the codebook versions `study/codebook.json`, the theme sign-offs `study/themes.json` and, for a consensus study, the panel, plan, rounds and MICMAC records under `study/consensus/`.

**Measured size.** None yet; an SRQR discussion of this extent opens on the key findings and closes on the implications.

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
- Figures over tables. In Methods and Results, present comparisons, distributions, trends, effects with their intervals and time series as data figures (line, bar, dot-and-whisker or forest, violin or box plots, heat maps) or diagrams. Keep a table only for values a reader must look up exactly (settings, hyperparameters, dataset, participant or hardware characteristics, metadata) or when the venue requires one. Among the floats of Methods and Results, aim at about 60 % figures and 40 % tables.
- A figure or table caption is at most four lines: a title that says what the float shows, plus the one definition a reader needs to read it. Notation and further definitions go in a table note below the table or in the text.
- **Every number comes from a record.** Counts of participants and transcripts from `study/transcripts.json` or the panel record, agreement, medians and interquartile ranges from the recorded round results, MICMAC ranks from the recorded computation, planned values (sample, rounds, threshold) from the locked protocol and the consensus plan, never recounted or retyped by hand.

## Disqualifiers

- A finding, a quote or a number that the results section does not report.
- A claim about other studies without a citation that holds it.
- No comparison with the closest studies the introduction named.
- A qualitative finding generalised statistically to a population, or a panel's consensus presented as the view of every expert.
- An implication stronger than the findings allow, or a closing appeal with no finding behind it.
- [block: d-experience-lessons] An experience-report block (`d-experience-lessons`) written in a workspace of another variant.
- In an experience report, an effect of the innovation (better learning, higher performance) claimed without an evaluation that measured it.

## Inputs

### External inputs

| Input | Unblocks |
|---|---|
| `contributions` — The contributions are revisited one by one with the finding that answers each research question. | `d-key-findings` |
| `gap` — The gap the introduction stated is the yardstick: say how far the findings close it. | `d-integration` |

### Internal chain

| Block | Depends on |
|---|---|
| `discussion.d-key-findings` — The contributions are revisited one by one with the finding that answers each research question. | `introduction.intro-purpose` |
| `discussion.d-integration` — The gap the introduction stated is the yardstick: say how far the findings close it. | `introduction.intro-gap` |
