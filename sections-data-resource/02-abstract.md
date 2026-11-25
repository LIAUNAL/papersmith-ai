---
{
  "section": "abstract",
  "position": 2,
  "mode": {
    "value": "transposition",
    "source": {
      "file": "sections/02-abstract.md",
      "quote": "Every count in the abstract is copied from the data records and the technical validation; the abstract adds nothing."
    }
  },
  "blocks": [
    {
      "id": "abs-background-objectives",
      "requires_facts": [
        {
          "value": "contributions",
          "source": {
            "file": "sections/02-abstract.md",
            "quote": "The background and the purpose come from the resource's contributions."
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none",
      "after": [
        {
          "target": "background-summary.bs-summary",
          "source": {
            "file": "sections/02-abstract.md",
            "quote": "The background and the purpose come from the resource's contributions."
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
            "quote": "The methods slot follows the methods section: the collection protocol, the sources and their consent, and the curation."
          }
        }
      ]
    },
    {
      "id": "abs-data-records",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none",
      "after": [
        {
          "target": "data-records",
          "source": {
            "file": "sections/02-abstract.md",
            "quote": "The data records slot follows the data records section: the counts, the formats and the repository with its persistent identifier."
          }
        }
      ]
    },
    {
      "id": "abs-validation",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none",
      "after": [
        {
          "target": "technical-validation",
          "source": {
            "file": "sections/02-abstract.md",
            "quote": "The validation slot follows the technical validation section: the quality checks and, when reported, the baselines."
          }
        }
      ]
    },
    {
      "id": "abs-reuse",
      "requires_facts": [
        {
          "value": "limitations",
          "source": {
            "file": "sections/02-abstract.md",
            "quote": "The reuse sentence comes from the usage notes and their limitations."
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none",
      "after": [
        {
          "target": "usage-notes.un-limitations",
          "source": {
            "file": "sections/02-abstract.md",
            "quote": "The reuse sentence comes from the usage notes and their limitations."
          }
        }
      ]
    }
  ]
}
---

# Abstract (data-resource line)

Every count in the abstract is copied from the data records and the technical validation; the abstract adds nothing.
A data descriptor's abstract says what the resource is, how it was collected,
what it holds, how its quality was checked and where it is deposited. One
paragraph, no citations; the venue's word limit wins over the extent below.

**Extent** 120–200 words · one paragraph

## Slot `abs-background-objectives`

The background and the purpose come from the resource's contributions. One or two sentences: the gap the resource fills and what it lets others
study or evaluate.

## Slot `abs-methods`

The methods slot follows the methods section: the collection protocol, the sources and their consent, and the curation. One or two sentences on how, where, when and from whom or what the records
were collected, and how they were annotated or processed.

## Slot `abs-data-records`

The data records slot follows the data records section: the counts, the formats and the repository with its persistent identifier. The number of files, records, participants or items and their formats, as
the data records section counts them, and the repository and identifier of
the deposit.

## Slot `abs-validation`

The validation slot follows the technical validation section: the quality checks and, when reported, the baselines. One sentence on the quality checks and, when baselines are reported, their
result as the technical validation writes it, labelled exploratory unless the
locked protocol names it.

## Slot `abs-reuse`

The reuse sentence comes from the usage notes and their limitations. One sentence on the intended uses and the main limitation of the resource.

## LIA house style

No data descriptor of this line has been measured yet: the rules below carry the group's writing rules from the experimental and observational lines to a data resource, and the extent at the top of this contract stays the target. They read the records the line keeps: the locked protocol revision `protocol/study-protocol-<slug>-vNN.md` and `study/protocol.lock.json`, the ethics record `study/ethics.json`, the datasets registry `datasets/registry.json` (the own-data statement or the licence decision, the de-identification statement and the deposit record), each dataset's dictionary `datasets/<slug>/dictionary.json` and quality report `datasets/<slug>/qc.json`, and the analysis log `analysis/log.jsonl`.

**Measured size.** None yet; the venue's limit (often 170 words) decides.

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

- A count that differs from the data records or the technical validation.
- A deposit, identifier or licence the deposit record does not hold.
- A baseline score presented as a finding, or an exploratory baseline presented as confirmatory.
- A citation, or a claim the body does not make.

## Inputs

### External inputs

| Input | Unblocks |
|---|---|
| `contributions` — The background and the purpose come from the resource's contributions. | `abs-background-objectives` |
| `limitations` — The reuse sentence comes from the usage notes and their limitations. | `abs-reuse` |

### Internal chain

| Block | Depends on |
|---|---|
| `abstract.abs-background-objectives` — The background and the purpose come from the resource's contributions. | `background-summary.bs-summary` |
| `abstract.abs-reuse` — The reuse sentence comes from the usage notes and their limitations. | `usage-notes.un-limitations` |
