---
{
  "section": "title-and-keywords",
  "position": 1,
  "mode": {
    "value": "transposition",
    "source": {
      "file": "sections/01-title-and-keywords.md",
      "quote": "The title names the approach with the words the methods use."
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
            "quote": "The contributions of the study, its purpose and the phenomenon it examined, decide the title."
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none",
      "after": [
        {
          "target": "introduction.intro-purpose",
          "source": {
            "file": "sections/01-title-and-keywords.md",
            "quote": "The contributions of the study, its purpose and the phenomenon it examined, decide the title."
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

# Title and Keywords (qualitative and participatory line)

SRQR item 1 (the title names the nature and topic of the study and its
approach). The title names the approach with the words the methods use. A
qualitative study names its approach or design (a case study, an ethnography,
a grounded theory study, a thematic analysis of interviews, a participatory
action research study, a mixed-methods study); a consensus study names its
method (a Delphi study, a nominal group, a structural foresight analysis); an
experience report says that it is one.

**Extent** 10–25 words · keywords 4–6

## Block `title`

The contributions of the study, its purpose and the phenomenon it examined,
decide the title. The title states the phenomenon, the people or the setting
and the approach, in this order: "<phenomenon> among <people> in <setting>: a
<approach>". No claim of effect, no question form, no finding stated as a verb
(*X improves Y*), and no acronym that the abstract does not expand. A
participant's words in a title are a verbatim quote that the results report
with its code, or no quote at all.

## Block `keywords`

The keyword-bounds and the classification-line come from the venue. Four to
six keywords, none repeating a word of the title, the approach included as one
of them (*qualitative research*, *thematic analysis*, *Delphi technique*,
*experience report*).

## LIA house style

No paper of this line has been measured yet: the rules below carry the group's writing rules from the experimental and review lines to a qualitative, participatory or consensus study, and the extent at the top of this contract stays the target. They read the records the line keeps: the locked protocol revision `protocol/study-protocol-<slug>-vNN.md` and `study/protocol.lock.json` when the study has one, the ethics record `study/ethics.json`, the transcript register `study/transcripts.json`, the codebook versions `study/codebook.json`, the theme sign-offs `study/themes.json` and, for a consensus study, the panel, plan, rounds and MICMAC records under `study/consensus/`.

**Measured size.** None yet; a title of this group's qualitative work runs 12 to 20 words in two parts joined by a colon.

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

- [block: title] A title that names no approach (a qualitative study, a case study, a Delphi study, an experience report).
- [block: title] A title that states an effect or a finding (*X improves Y*, *X is effective for Y*).
- [block: title] A participant's words in the title that are not a verbatim quote the results report.
- [block: title] A promotional or evaluative word in the title (*Novel*, *Revolutionizing*, *Comprehensive*).
- [block: title, keywords] A keyword that repeats a word of the title.
- [block: title] An acronym in the title that the abstract does not expand.

## Sources

- The locked protocol revision (`protocol/study-protocol-<slug>-vNN.md`), when the study has one: the phenomenon, the people, the setting and the approach, which fix the words of the title.

## Inputs

### External inputs

| Input | Unblocks |
|---|---|
| `contributions` — The contributions of the study, its purpose and the phenomenon it examined, decide the title. | `title` |
| `keyword-bounds` — The keyword-bounds and the classification-line come from the venue. | `keywords` |
| `classification-line` — The keyword-bounds and the classification-line come from the venue. | `keywords` |

### Internal chain

| Block | Depends on |
|---|---|
| `title-and-keywords.title` — The contributions of the study, its purpose and the phenomenon it examined, decide the title. | `introduction.intro-purpose` |
