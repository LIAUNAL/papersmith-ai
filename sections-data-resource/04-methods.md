---
{
  "section": "methods",
  "position": 4,
  "mode": {
    "value": "transposition",
    "source": {
      "file": "sections/04-methods.md",
      "quote": "The methods transcribe the locked collection protocol and the operator's records; they never describe a step that was not run."
    }
  },
  "blocks": [
    {
      "id": "m-collection-protocol",
      "requires_facts": [
        {
          "value": "protocol",
          "source": {
            "file": "sections/04-methods.md",
            "quote": "The protocol is the collection protocol the operator locked, named with its location and every amendment to it."
          }
        }
      ],
      "requires_declarations": [],
      "citations": "resolution"
    },
    {
      "id": "m-sources-consent",
      "requires_facts": [
        {
          "value": "sample",
          "source": {
            "file": "sections/04-methods.md",
            "quote": "The sample is the participants, sources or items the protocol planned, and the ethics approval and the consent route under which they were collected."
          }
        }
      ],
      "requires_declarations": [
        {
          "value": "ethics-approval",
          "source": {
            "file": "sections/04-methods.md",
            "quote": "The sample is the participants, sources or items the protocol planned, and the ethics approval and the consent route under which they were collected."
          }
        }
      ],
      "citations": "resolution"
    },
    {
      "id": "m-curation-documentation",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "resolution"
    },
    {
      "id": "m-preprocessing-labeling",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "resolution"
    }
  ]
}
---

# Methods (data-resource line)

The methods transcribe the locked collection protocol and the operator's records; they never describe a step that was not run.
Datasheets for Datasets, paraphrased: how the data were acquired, who was involved
and under which conditions, which ethical review and consent applied, and what
preprocessing, cleaning or labeling was done. Enough detail for someone else to
collect comparable data.

**Extent** 700–1600 words · subsections per block

## Block `m-collection-protocol`

The protocol is the collection protocol the operator locked, named with its location and every amendment to it. The design of the collection: the instruments, devices, forms or sources
used, the setting and the period, the sampling strategy, and the planned
records, as the locked revision `protocol/study-protocol-<slug>-vNN.md`
states them and `study/protocol.lock.json` pins them (the operator approved
it with `study_cli.py protocol approve`). Each amendment is reported with its
date and reason.

## Block `m-sources-consent`

The sample is the participants, sources or items the protocol planned, and the ethics approval and the consent route under which they were collected. Who or what the records come from, how they were recruited or selected and
how many the protocol planned against how many were collected. The ethics
approval comes from the operator's record (`study_cli.py ethics record`,
`study/ethics.json`: committee, code, date and consent route), or the reason
it does not apply when no person is involved. The permission to release the
data comes from the registry: the operator's own-data statement
(`datasets_cli.py --root . own`) or the licence decision of a third-party
source (`datasets_cli.py --root . license`).

## Block `m-curation-documentation`

The curation and documentation follow the data dictionary the operator validated. How the raw records were organized, named, versioned and documented: the
folder layout, the naming scheme and the data dictionary
`datasets/<slug>/dictionary.json` (one entry per variable with its type,
unit, allowed values and missing codes), validated with
`datasets_cli.py --root . dictionary check`.

## Block `m-preprocessing-labeling`

The preprocessing and labeling are the steps run on the raw records, each traced to its run or its operator's statement. Each cleaning, conversion, segmentation or labeling step, with the tool and
its version, as the analysis log `analysis/log.jsonl` hashes its script,
inputs and outputs. For annotations: the guidelines, who annotated (their
training, never their identity) and how disagreements were resolved. The
de-identification of personal data is the operator's statement recorded with
`datasets_cli.py --root . deidentify`. Raw records kept beside the processed
ones are named.

## LIA house style

No data descriptor of this line has been measured yet: the rules below carry the group's writing rules from the experimental and observational lines to a data resource, and the extent at the top of this contract stays the target. They read the records the line keeps: the locked protocol revision `protocol/study-protocol-<slug>-vNN.md` and `study/protocol.lock.json`, the ethics record `study/ethics.json`, the datasets registry `datasets/registry.json` (the own-data statement or the licence decision, the de-identification statement and the deposit record), each dataset's dictionary `datasets/<slug>/dictionary.json` and quality report `datasets/<slug>/qc.json`, and the analysis log `analysis/log.jsonl`.

**Measured size.** None yet; data descriptors in the group's venues give methods 700 to 1600 words.

**Human boundaries (every section of this line).**

- **No generated data.** The assistant never generates measurements or data: it never generates, labels or alters data, never writes, imputes, relabels, filters or resamples a record of the resource, and never presents a toy set (`/datasets synth`) as part of it. Every count, value, label distribution, quality figure and baseline score in the paper comes from the operator's files and the records listed above; a value without a record is left out and reported as missing.
- **Human decisions.** Data collection, consent, licence and deposit stay human, and so do the ethics approval, the choice of primary outcome, the collection protocol, the annotation guidelines and who annotates. The paper reports the locked protocol and the operator's records (`study_cli.py ethics record`, `datasets_cli.py own` or `license`, `deidentify` and `deposit`, each signed with `--by`) and never proposes, changes or completes any of them.

**Writing (every section of this line).**

- **Sentences average 18–27 words.** One claim and its qualifier per sentence.
- **One voice.** First person plural for what the authors did (*we recorded*, *we annotated*, *we deposited*), past tense for every step that was run, present tense for what the resource contains and how it is accessed.
- **Citations are numeric, in square brackets, and close the claim they support** (`[4]`, `[7,9]`, `[12–15]`). A citation is never the grammatical subject of a sentence.
- **The resource is described, not sold.** A data descriptor reports what was collected, how and how well; it draws no scientific conclusion from the data and makes no claim that the baselines decide a research question.
- **Transitions come from the relation between claims.** A stock connector (*In addition*, *Furthermore*, *Additionally*, *Moreover*) is the exception: never the same one twice within five sentences.
- **No promotional adjectives.** *Revolutionary*, *transformative*, *pivotal*, *comprehensive*, *crucial*, *novel*, *large-scale* say nothing a reader can check; state the counts instead.
- **A table has at least three columns and three rows.** A two-column or two-row table is a grid with nothing to cross: one or two values go in the sentence. A figure is drawn by a script from the resource's records, its provenance recorded with `paper_cli.py figure provenance`, and placed with `paper_cli.py place`.
- **Every number comes from a record.** Counts of files, records, participants and labels from `datasets/<slug>/qc.json` and the registry, variables and units from the dictionary, baseline scores from the outputs of the analysis log, planned values (sources, sample, annotation scheme, analysis plan) from the locked protocol revision, never recounted or retyped by hand.

## Disqualifiers

- A collection step, source or count that the locked protocol and the records do not hold.
- Personal data released without the de-identification statement, or a consent route the ethics record does not name.
- A third-party source released without an allowed licence decision.
- A labeling or cleaning step with no run in the analysis log and no operator statement.
- An annotator named by identity, or a participant identifiable from the text.

## Inputs

### External inputs

| Input | Unblocks |
|---|---|
| `protocol` — The protocol is the collection protocol the operator locked, named with its location and every amendment to it. | `m-collection-protocol` |
| `sample` — The sample is the participants, sources or items the protocol planned, and the ethics approval and the consent route under which they were collected. | `m-sources-consent` |
| `ethics-approval` — The sample is the participants, sources or items the protocol planned, and the ethics approval and the consent route under which they were collected. | `m-sources-consent` |

### Internal chain

None: no block of this section waits on another block.
