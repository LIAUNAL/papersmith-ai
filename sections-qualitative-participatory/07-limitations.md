---
{
  "section": "limitations",
  "position": 7,
  "mode": {
    "value": "argument",
    "source": {
      "file": "sections/07-limitations.md",
      "quote": "A limitation names a restriction of what the paper reports, and its consequence for a reported finding."
    }
  },
  "blocks": [
    {
      "id": "lim-reported",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "resolution",
      "produces_facts": [
        {
          "value": "limitations",
          "source": {
            "file": "sections/07-limitations.md",
            "quote": "The limitations are the boundaries of the material and the analysis behind the reported findings."
          }
        }
      ]
    },
    {
      "id": "lim-protocol-deviations",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none"
    },
    {
      "id": "lim-experience-limits",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none",
      "optional": true
    }
  ]
}
---

# Limitations (qualitative and participatory line)

SRQR item 19, ACCORD's discussion items. A limitation names a restriction of
what the paper reports, and its consequence for a reported finding. It may be
typeset as the last subsection of the discussion when the venue prefers it.

**Extent** 180–450 words · 1 or 2 paragraphs

## Block `lim-reported`

The limitations are the boundaries of the material and the analysis behind the
reported findings. Each item names a decision or a boundary of the study (who
took part and who did not, the sufficiency of the sample, the researchers'
position, the language and the setting of the fieldwork, a single coder, the
response in each round, a panel drawn from one country or discipline), states
how it bounds a reported finding, and gives its consequence for the
credibility or the transferability of that finding. A limitation is never a
feeling (*results should be interpreted with caution*), and an item that cites
the literature on the boundary it names is preferred.

## Block `lim-protocol-deviations`

Every difference between the paper and the protocol when the study has one:
each amendment with its reason (`study/protocol.lock.json`), a consensus plan
recorded again after the rounds began with its reason, a sampling or a data
collection that departed from the plan, and a late change of the codebook or
of the theme sign-off. A study without a protocol (an experience report may
have none) says so.

## Block `lim-experience-limits` (variant `experience-report`, optional)

Written only in a workspace of the `experience-report` variant; another
workspace leaves it unopened. The honest limits of an experience report: it
describes one experience, in one setting, from the authors' own position, and
makes no effect claim, because no evaluation measured one; the authors' double
role as designers and narrators, and the records the account rests on.

## LIA house style

No paper of this line has been measured yet: the rules below carry the group's writing rules from the experimental and review lines to a qualitative, participatory or consensus study, and the extent at the top of this contract stays the target. They read the records the line keeps: the locked protocol revision `protocol/study-protocol-<slug>-vNN.md` and `study/protocol.lock.json` when the study has one, the ethics record `study/ethics.json`, the transcript register `study/transcripts.json`, the codebook versions `study/codebook.json`, the theme sign-offs `study/themes.json` and, for a consensus study, the panel, plan, rounds and MICMAC records under `study/consensus/`.

**Measured size.** None yet; an SRQR limitations paragraph of this extent names three to five boundaries, each with its consequence.

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

- A limitation that names no decision or boundary of the study, or one without its consequence for a reported finding.
- The researchers' position, the sufficiency of the sample or the people who declined left unsaid when they apply.
- An amendment, a re-recorded consensus plan or a departure from the protocol left unsaid.
- An experience-report block (`lim-experience-limits`) written in a workspace of another variant, or an experience report that leaves it unopened.
- A limitation about something the paper does not report.

## Inputs

### External inputs

None: every block reads the study's records and the operator's declarations.

### Internal chain

None: no block of this section waits on another block.
