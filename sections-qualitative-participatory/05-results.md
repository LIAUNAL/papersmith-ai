---
{
  "section": "results",
  "position": 5,
  "mode": {
    "value": "transposition",
    "source": {
      "file": "sections/05-results.md",
      "quote": "Every theme, quote, count and agreement figure comes from a record the operator kept or signed off."
    }
  },
  "blocks": [
    {
      "id": "r-synthesis",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none"
    },
    {
      "id": "r-links-to-data",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none",
      "optional": true
    },
    {
      "id": "r-consensus-rounds",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none",
      "optional": true
    },
    {
      "id": "r-consensus-dissent",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none",
      "optional": true
    },
    {
      "id": "r-consensus-micmac",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none",
      "optional": true
    },
    {
      "id": "r-consensus-scenarios",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "resolution",
      "optional": true
    },
    {
      "id": "r-experience-what-was-done",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none",
      "optional": true
    }
  ]
}
---

# Results (qualitative and participatory line)

SRQR items 16 and 17, COREQ items 29 to 32, ACCORD's results items. Every
theme, quote, count and agreement figure comes from a record the operator kept
or signed off. The results report; interpretation, comparison with other
studies and implications wait for the discussion.

**Extent** 1000–2500 words · one table of the themes and subthemes, or one table of the items with their agreement per round

## Block `r-synthesis`

SRQR item 16, COREQ items 30 to 32. The main findings. For a
`qualitative-mixed` study, the themes and subthemes of the version the
operator signed off (`python skills/_core/qualitative/qual_cli.py themes
status --root .` must report the sign-off current before the block is
drafted), each with its definition and its relation to the others, the diverse
and minor themes as well as the major ones, and a table or a diagram of the
themes when it helps. For a consensus study, the items that reached consensus
and those that did not, which the consensus blocks report round by round; for
an experience report, what was observed, which `r-experience-what-was-done`
reports. A theme never rests on a count of how many participants said
something presented as prevalence, and a theme the operator did not sign off
is never reported.

## Block `r-links-to-data` (variant `qualitative-mixed`, required there; optional otherwise)

SRQR item 17, COREQ item 29. Written in every workspace of the
`qualitative-mixed` variant: the evidence that substantiates each theme, the
participants' own words. The block graph declares this block optional because
a consensus study or an experience report may hold no transcripts. Each
participant quote is written `\pquote{<code>}{<text>}`, with the participant's
code from `study/transcripts.json` and the text copied verbatim from a current
registered transcript of that participant: the same words, spelling,
punctuation and order, an omission written as two quotes, never corrected,
shortened inside, merged with another participant's words or invented. `python
skills/_core/qualitative/qual_cli.py quotes check --root .` finds every quote
and fails on one that is not verbatim, and `python
skills/paper-writing/scripts/paper_cli.py verify` reports the same failure as
`quote-not-verbatim`. Quotes show the range of each theme, contrasting views
included, and come from across the participants rather than one voice for all.

## Block `r-consensus-rounds` (variant `consensus-foresight`, optional)

Written only in a workspace of the `consensus-foresight` variant (ACCORD's
items on the results of each round); another workspace leaves it unopened. The
results of each round, read from `python
skills/_core/qualitative/consensus_cli.py round status --root .`: the members
invited and responding, and for each item the number of ratings, the percent
agreement, the median and the interquartile range, whether it reached the
pre-specified threshold and its change from the previous round. One table of
the items with their agreement per round, then the final list of agreed items
in the wording of the last round. A round whose record is stale (its response
file, the plan or the protocol changed since) is not reported until the
operator records it again; the assistant never enters, corrects or completes a
rating.

## Block `r-consensus-dissent` (variant `consensus-foresight`, optional)

Written only in a workspace of the `consensus-foresight` variant; another
workspace leaves it unopened. The items that did not reach consensus
(non-consensus) and the items dropped between rounds, with their final
agreement, and the dissent the panel expressed: the spread of the ratings and,
when the operator summarised them, the reasons members gave, from the
operator's summary and never attributed to a named or identifiable member.
Non-consensus is a result: it is reported, never omitted or reworded as
agreement.

## Block `r-consensus-micmac` (variant `consensus-foresight`, optional)

Written only in a `consensus-foresight` workspace whose study ran a structural
analysis; another workspace leaves it unopened. The MICMAC map read from
`python skills/_core/qualitative/consensus_cli.py micmac status --root .`: the
variables of the operator's influence matrix, their direct and indirect
influence and dependence, the power at which the rankings became stable, and
each variable's quadrant as the computation records it, drawn as the
influence-dependence map by a script from the recorded computation. A stale
computation (the matrix changed since) is not reported until the operator
computes it again.

## Block `r-consensus-scenarios` (variant `consensus-foresight`, optional)

Written only in a `consensus-foresight` workspace whose study analysed the
actors' strategies or built scenarios; another workspace leaves it unopened.
MACTOR's actors and their objectives, and the scenarios built from the
influential variables, reported as narrative: the construction of the operator
and the panel, with the method followed and its sources, never a computed
result that smith did not compute and never a forecast stated as a finding.

## Block `r-experience-what-was-done` (variant `experience-report`, optional)

Written only in a workspace of the `experience-report` variant; another
workspace leaves it unopened. It reports what was done, in the order it
happened: the activities, who took part and how many, what the authors
observed and the records they kept (course records, the authors' notes, the
feedback participants gave), each observation stated as an observation, with
no effect inferred from it. A count comes from the authors' records.

## LIA house style

No paper of this line has been measured yet: the rules below carry the group's writing rules from the experimental and review lines to a qualitative, participatory or consensus study, and the extent at the top of this contract stays the target. They read the records the line keeps: the locked protocol revision `protocol/study-protocol-<slug>-vNN.md` and `study/protocol.lock.json` when the study has one, the ethics record `study/ethics.json`, the transcript register `study/transcripts.json`, the codebook versions `study/codebook.json`, the theme sign-offs `study/themes.json` and, for a consensus study, the panel, plan, rounds and MICMAC records under `study/consensus/`.

**Measured size.** None yet; an SRQR results section of this extent opens on the table of themes and gives each theme its paragraph and its quotes.

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

- A table of two columns or two rows whose values a bar or pie chart, or the sentence, could carry.
- A theme the operator did not sign off, or themes reported from a stale sign-off.
- A theme supported only by a count of participants presented as prevalence.
- A `qualitative-mixed` paper whose results leave `r-links-to-data` unopened, or a theme with no participant's words behind it.
- A participant quote not written `\pquote{<code>}{<text>}`, not found verbatim in a current registered transcript of that participant, or attributed to a name.
- A consensus-foresight block (`r-consensus-rounds`, `r-consensus-dissent`, `r-consensus-micmac`, `r-consensus-scenarios`) written in a workspace of another variant.
- An agreement figure, median or interquartile range that differs from the round results, or an item reported as agreed below the pre-specified threshold.
- Items without consensus left out, or reworded as agreement.
- A MICMAC rank or quadrant from a stale or absent computation, or a scenario presented as a computed result.
- An experience-report block (`r-experience-what-was-done`) written in a workspace of another variant, or an observation stated as an effect.
- An interpretation, a comparison with other studies or a recommendation: those belong to the discussion.

## Inputs

### External inputs

None: every block reads the study's records and the operator's account.

### Internal chain

None: no block of this section waits on another block.
