---
{
  "section": "methods",
  "position": 4,
  "mode": {
    "value": "transposition",
    "source": {
      "file": "sections/04-methods.md",
      "quote": "The methods transcribe the protocol, the operator's records and the operator's account of the fieldwork; they never describe a step that was not run."
    }
  },
  "blocks": [
    {
      "id": "m-approach-paradigm",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "resolution"
    },
    {
      "id": "m-researcher-reflexivity",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none"
    },
    {
      "id": "m-context",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none"
    },
    {
      "id": "m-sampling",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "resolution"
    },
    {
      "id": "m-ethics-consent",
      "requires_facts": [],
      "requires_declarations": [
        {
          "value": "ethics-approval",
          "source": {
            "file": "sections/04-methods.md",
            "quote": "The ethics-approval names the committee, the approval code and date, and the consent route the operator recorded."
          }
        }
      ],
      "citations": "none"
    },
    {
      "id": "m-data-collection",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none"
    },
    {
      "id": "m-units-of-study",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none"
    },
    {
      "id": "m-data-processing",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none",
      "optional": true
    },
    {
      "id": "m-data-analysis",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "resolution"
    },
    {
      "id": "m-trustworthiness",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "resolution"
    },
    {
      "id": "m-protocol",
      "requires_facts": [
        {
          "value": "protocol",
          "source": {
            "file": "sections/04-methods.md",
            "quote": "The protocol is the revision the operator locked, named with its location and every amendment to it."
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none",
      "optional": true
    },
    {
      "id": "m-consensus-panel",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none",
      "optional": true
    },
    {
      "id": "m-consensus-definition",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "resolution",
      "optional": true
    },
    {
      "id": "m-consensus-rounds",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none",
      "optional": true
    },
    {
      "id": "m-experience-setting",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none",
      "optional": true
    },
    {
      "id": "m-experience-innovation",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "resolution",
      "optional": true
    }
  ]
}
---

# Methods (qualitative and participatory line)

The methods transcribe the protocol, the operator's records and the operator's
account of the fieldwork; they never describe a step that was not run. Open
with one sentence naming the reporting guideline the study follows, cited:
SRQR for a qualitative or mixed study (O'Brien et al., 2014,
doi:10.1097/ACM.0000000000000388), or COREQ when the study rests on interviews
or focus groups (Tong et al., 2007, doi:10.1093/intqhc/mzm042); ACCORD for a
consensus study (Gattrell et al., 2024, doi:10.1371/journal.pmed.1004326). An
experience report follows no reporting guideline and says so. The blocks below
follow SRQR items 5 to 15; `python skills/_core/checklists/checklist_cli.py
check --guideline <id> --root .` reports which items still lack their text. A
departure from the protocol is reported where it happened and again in the
limitations.

**Extent** 1000–2200 words · a table of the participants' characteristics, in ranges or categories · at least as many figures (the analysis process, the sampling or the round design as a diagram) as tables

## Block `m-approach-paradigm`

SRQR item 5. The qualitative approach (ethnography, grounded theory, case
study, phenomenology, narrative research, thematic or content analysis,
participatory action research) or the mixed-methods design, and the research
paradigm it rests on (for example postpositivist, constructivist or critical),
with the reason they fit the research question. A consensus study names its
method (Delphi, modified Delphi, nominal group, RAND/UCLA appropriateness,
structural foresight) and why expert judgement answers the question; an
experience report says that it describes and reflects on an experience and
does not evaluate it. The approach is the one of the protocol when the study
has one.

## Block `m-researcher-reflexivity`

SRQR item 6, COREQ items 1 to 8. The researchers' characteristics that may
influence the research (their training and experience, their relationship with
the participants or the setting before the study began, their assumptions
about the phenomenon) and how they were taken into account: the interaction
between those characteristics and the research questions, the approach, the
methods and the findings. This is the operator's own account; the assistant
never states a researcher's background, relationship or assumption that the
operator did not give.

## Block `m-context`

SRQR item 7. The setting and the site where the study took place and the
salient contextual factors: the place, the organisation or the community, the
period, and the social, economic, cultural or institutional conditions that
bear on the phenomenon, as the operator described them.

## Block `m-sampling`

SRQR item 8, COREQ items 10 to 13. How and why the participants, documents or
events were selected (purposive, theoretical, snowball, maximum variation or
convenience sampling, with the criteria), how they were approached, and the
criterion for deciding that no further sampling was needed: the sufficiency of
the sample as the operator judged it (data saturation, information power or
the planned number), never asserted without the operator's account. For an
interview or focus-group study, the number of participants and of transcripts
comes from `python skills/_core/qualitative/qual_cli.py transcripts status
--root .`, never recounted; for a consensus study, from the panel record.
Refusals and withdrawals are reported with their reasons.

## Block `m-ethics-consent`

SRQR item 9. The ethics-approval names the committee, the approval code and
date, and the consent route the operator recorded. Transcribe the operator's
ethics record (`study/ethics.json`): the committee and the approval, how
informed consent was obtained, from whom and for which uses (recording,
quotation in publications, data sharing), and how confidentiality was
protected. An experience report that holds no participant data states that
ethics approval was not applicable, with the reason the operator recorded. The
assistant never writes that consent was obtained, waived or not needed unless
the operator's record says so.

## Block `m-data-collection`

SRQR item 10, COREQ items 14 to 23. The types of data collected (interviews,
focus groups, observation, field notes, documents, questionnaires), the
procedures (who collected the data, where, when, for how long, in which
language, whether the guide was piloted, whether participants were seen more
than once), and how the methods changed during the study in response to what
was learned, with the reason. The instruments (the interview or focus-group
guide, the observation protocol, the consensus questionnaire) are described
and, when the venue allows, supplied as supplementary material. The operator
collected the material; the text reports how, from the operator's own account.

## Block `m-units-of-study`

SRQR item 11. The number and the relevant characteristics of the participants,
documents or events included (role, experience, sector, age range, or the
documents' type and period) and the level of participation (who took part in
each interview or focus group). The characteristics come from the operator's
records and are reported at the level that keeps each participant
unidentifiable: a small group is described in ranges or categories, never so
that a reader could name a person.

## Block `m-data-processing` (variant `qualitative-mixed`, required there; optional otherwise)

SRQR item 12, COREQ items 22 to 24. Written in every workspace of the
`qualitative-mixed` variant: a study of interviews, focus groups or field
notes always reports how its material was processed. The block graph declares
this block optional because a consensus study or an experience report may keep
no transcripts; for a `qualitative-mixed` workspace the requirement is held by
the command center board's G-TRANSCRIPTS gate, which stays failed while no
transcript is registered or a registered file changed. Read the register with
`python skills/_core/qualitative/qual_cli.py transcripts status --root .` and
report from it: the transcription (verbatim or summarised, and by whom), how
each file was de-identified (the statement the operator recorded with it),
whether transcripts were returned to participants, how the material was stored
and protected, and the number of transcripts and field notes of each kind. The
text never quotes a transcript here and never reproduces a de-identified
passage; a stale registration (the file changed since it was registered) is
not described until the operator registers it again.

## Block `m-data-analysis`

SRQR item 13, COREQ items 24 to 28. The process by which inferences and themes
were developed: who coded, how the coding frame was developed (inductively,
deductively or both), how many coders, how disagreements were resolved, and
the software used. Read the records with `python
skills/_core/qualitative/qual_cli.py codebook status --root .` and `python
skills/_core/qualitative/qual_cli.py themes status --root .`: each codebook
version the operator recorded and the operator's sign-off of the themes, bound
to a codebook version and to every transcript it rests on. The themes are the
ones the operator signed off, and a stale sign-off (the themes, the codebook
or a transcript changed since) is not described until the operator signs the
themes off again. For a consensus study, how agreement was computed from the
response files, which `m-consensus-definition` states; for an experience
report, how the authors reflected on the experience and on which records.

## Block `m-trustworthiness`

SRQR item 14. The techniques used to enhance the trustworthiness and
credibility of the analysis (member checking, an audit trail, triangulation of
sources or methods, peer debriefing, double coding, negative case analysis,
reflexive memos), each as the operator applied it and with its rationale; a
technique that was not used is not claimed.

## Block `m-protocol` (optional)

Written when the study has a protocol: in practice in every
`qualitative-mixed` and `consensus-foresight` workspace, whose protocol the
board's G-STUDY-PROTOCOL gate holds, and optional for an `experience-report`
workspace that kept none. The protocol is the revision the operator locked,
named with its location and every amendment to it. Read the lock with `python
skills/_core/empirical/study_cli.py protocol status --root .`: the revision,
its sha256 and each amendment with its reason and date; say where the protocol
can be accessed, and name the registration when the operator recorded one.

## Block `m-consensus-panel` (variant `consensus-foresight`, optional)

Written only in a workspace of the `consensus-foresight` variant (ACCORD's
steering committee and panel items); another workspace leaves it unopened. Who
ran the study (the steering committee or the facilitators and their roles),
how the panel members were identified and recruited, the expertise each was
chosen for, and how many were invited and how many took part, read from
`python skills/_core/qualitative/consensus_cli.py status --root .`, where each
member is an anonymised code with the expertise the operator registered.
Members are never named.

## Block `m-consensus-definition` (variant `consensus-foresight`, optional)

Written only in a workspace of the `consensus-foresight` variant (ACCORD's
items on assessing consensus); another workspace leaves it unopened. The
definition of consensus pre-specified in the protocol: the rating scale, the
rating from which a response counts as agreement, the threshold (the share of
members that must agree) and the number of planned rounds, read from the
consensus plan with `python skills/_core/qualitative/consensus_cli.py status
--root .`, which binds the plan to the locked protocol; then how agreement was
computed from the response files (percent agreement, median and interquartile
range). A plan recorded again after the rounds began is reported with the
reason the operator gave, and a threshold changed after a round was seen is
never presented as pre-specified.

## Block `m-consensus-rounds` (variant `consensus-foresight`, optional)

Written only in a workspace of the `consensus-foresight` variant (ACCORD's
items on the questionnaire and the feedback); another workspace leaves it
unopened. How the rounds ran: the questionnaire of the first round and how its
items were generated (from the literature, the protocol or an open first
round), the mode and the period of each round, the reminders, the feedback
members received between rounds (the group's median and interquartile range or
distribution, the anonymised comments) and how items were added, merged,
reworded or dropped between rounds, with the reason. A round's responses come
only from the file the operator registered.

## Block `m-experience-setting` (variant `experience-report`, optional)

Written only in a workspace of the `experience-report` variant; another
workspace leaves it unopened. The context and setting of the experience: the
institution and its programme, the course or the service, the people involved
and their roles, the period, and the problem or the need that prompted the
innovation, as the authors lived and recorded it.

## Block `m-experience-innovation` (variant `experience-report`, optional)

Written only in a workspace of the `experience-report` variant; another
workspace leaves it unopened. The innovation or programme in enough detail for
another team to adapt it: its aims, the ideas or the literature it drew on,
its components and materials, who delivered it, how and how often, and how it
changed along the way.

## LIA house style

No paper of this line has been measured yet: the rules below carry the group's writing rules from the experimental and review lines to a qualitative, participatory or consensus study, and the extent at the top of this contract stays the target. They read the records the line keeps: the locked protocol revision `protocol/study-protocol-<slug>-vNN.md` and `study/protocol.lock.json` when the study has one, the ethics record `study/ethics.json`, the transcript register `study/transcripts.json`, the codebook versions `study/codebook.json`, the theme sign-offs `study/themes.json` and, for a consensus study, the panel, plan, rounds and MICMAC records under `study/consensus/`.

**Measured size.** None yet; an SRQR methods section of this extent covers every item in prose, with a table of the participants' characteristics.

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

- A table of two columns or two rows whose values a bar or pie chart, or the sentence, could carry.
- A step described that has no record or no account of the operator's behind it.
- An approach or paradigm left unnamed, or one that differs from the protocol without the amendment that changed it.
- No account of the researchers' characteristics and reflexivity.
- A sufficiency of the sample asserted without the criterion the operator applied, or a count of participants or transcripts that differs from `study/transcripts.json` or the panel record.
- An ethics approval or consent route that the operator's records do not hold.
- A participant named, or described so that a reader could identify them.
- A `qualitative-mixed` paper whose methods leave `m-data-processing` unopened, or a transcript quoted or reproduced in the methods.
- Themes described from a codebook version or a sign-off that is stale or absent.
- A trustworthiness technique claimed that the operator did not apply.
- A consensus-foresight block (`m-consensus-panel`, `m-consensus-definition`, `m-consensus-rounds`) written in a workspace of another variant, or a threshold presented as pre-specified that the protocol and the consensus plan do not hold.
- An experience-report block (`m-experience-setting`, `m-experience-innovation`) written in a workspace of another variant.

## Inputs

### External inputs

| Input | Unblocks |
|---|---|
| `ethics-approval` — The ethics-approval names the committee, the approval code and date, and the consent route the operator recorded. | `m-ethics-consent` |
| `protocol` — The protocol is the revision the operator locked, named with its location and every amendment to it. | `m-protocol` |

### Internal chain

None: no block of this section waits on another block.
