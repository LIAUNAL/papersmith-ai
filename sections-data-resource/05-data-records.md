---
{
  "section": "data-records",
  "position": 5,
  "mode": {
    "value": "transposition",
    "source": {
      "file": "sections/05-data-records.md",
      "quote": "The data records say where the resource is deposited and what each file holds, as the deposit record and the dictionary state them."
    }
  },
  "blocks": [
    {
      "id": "dr-deposit",
      "requires_facts": [],
      "requires_declarations": [
        {
          "value": "repository-url",
          "source": {
            "file": "sections/05-data-records.md",
            "quote": "The deposit is the repository, the persistent identifier and the licence of the operator's deposit record."
          }
        }
      ],
      "citations": "none"
    },
    {
      "id": "dr-files-formats",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none"
    },
    {
      "id": "dr-dictionary",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none",
      "after": [
        {
          "target": "data-records.dr-files-formats",
          "source": {
            "file": "sections/05-data-records.md",
            "quote": "The dictionary is the variables of the resource, each with its type, its unit and its allowed values."
          }
        }
      ]
    }
  ]
}
---

# Data Records (data-resource line)

The data records say where the resource is deposited and what each file holds, as the deposit record and the dictionary state them.
A reader learns here where to get the data and what they will find: the
repository, the persistent identifier, the licence, the files, their formats
and their variables.

**Extent** 250–700 words · one table of files

## Block `dr-deposit`

The deposit is the repository, the persistent identifier and the licence of the operator's deposit record. Copied from the deposit record that `datasets_cli.py --root . status` prints
for the dataset (recorded by the operator with `datasets_cli.py --root .
deposit --by`): the repository, the DOI or other persistent identifier with
its scheme, the licence, the version and the date, and the data citation in
the reference list. A deposit whose record is stale (a file changed, added or
missing since it was recorded) is not described until the operator records
it again.

## Block `dr-files-formats`

The files are the deposited files, their formats, their sizes and how they are organized. One table of the deposited files or folders (name, format, size or record
count, content), as the deposit record lists them by sha256 and
`datasets/<slug>/qc.json` counts their rows and columns. Open, documented
formats are named with their version.

## Block `dr-dictionary`

The dictionary is the variables of the resource, each with its type, its unit and its allowed values. The variables, labels and metadata fields, summarised from the validated
`datasets/<slug>/dictionary.json` and deposited with the data; codes for
missing values are stated.

## LIA house style

No data descriptor of this line has been measured yet: the rules below carry the group's writing rules from the experimental and observational lines to a data resource, and the extent at the top of this contract stays the target. They read the records the line keeps: the locked protocol revision `protocol/study-protocol-<slug>-vNN.md` and `study/protocol.lock.json`, the ethics record `study/ethics.json`, the datasets registry `datasets/registry.json` (the own-data statement or the licence decision, the de-identification statement and the deposit record), each dataset's dictionary `datasets/<slug>/dictionary.json` and quality report `datasets/<slug>/qc.json`, and the analysis log `analysis/log.jsonl`.

**Measured size.** None yet; the files table carries most of this section.

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

- A repository, identifier or licence that the deposit record does not hold, or a stale deposit described as current.
- A file, count or format that the deposit record and the quality report do not hold.
- A variable missing from the dictionary, or a missing-value code left undefined.
- Data available only on request without the reason and the access route stated.

## Inputs

### External inputs

| Input | Unblocks |
|---|---|
| `repository-url` — The deposit is the repository, the persistent identifier and the licence of the operator's deposit record. | `dr-deposit` |

### Internal chain

| Block | Depends on |
|---|---|
| `data-records.dr-dictionary` — The dictionary is the variables of the resource, each with its type, its unit and its allowed values. | `data-records.dr-files-formats` |
