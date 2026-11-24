---
{
  "section": "usage-notes",
  "position": 7,
  "mode": {
    "value": "argument",
    "source": {
      "file": "sections/07-usage-notes.md",
      "quote": "The usage notes tell a reader how the resource may and may not be used, how to access it and who maintains it."
    }
  },
  "blocks": [
    {
      "id": "un-intended-uses",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "resolution"
    },
    {
      "id": "un-limitations",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "resolution",
      "produces_facts": [
        {
          "value": "limitations",
          "source": {
            "file": "sections/07-usage-notes.md",
            "quote": "The limitations name what the resource does not cover and the uses it should not serve."
          }
        }
      ]
    },
    {
      "id": "un-access-conditions",
      "requires_facts": [],
      "requires_declarations": [
        {
          "value": "repository-url",
          "source": {
            "file": "sections/07-usage-notes.md",
            "quote": "The access conditions are the licence and any restriction the deposit and the consent impose."
          }
        }
      ],
      "citations": "none"
    },
    {
      "id": "un-maintenance",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none"
    }
  ]
}
---

# Usage Notes (data-resource line)

The usage notes tell a reader how the resource may and may not be used, how to access it and who maintains it.
Datasheets for Datasets, paraphrased: the uses the dataset was built for, the
uses it should not serve, how it is distributed and under which terms, and who
supports and updates it.

**Extent** 200–600 words · one paragraph per block

## Block `un-intended-uses`

The intended uses are the tasks and questions the collection protocol built the resource for. The tasks and analyses the resource supports, with the tools or formats that
read it, citing the work that uses comparable data.

## Block `un-limitations`

The limitations name what the resource does not cover and the uses it should not serve. Coverage (populations, settings, periods or labels missing), known biases
from the sampling or the annotation, quality issues the technical validation
reported, and the uses the data should not serve (for instance identifying
participants or decisions about individuals).

## Block `un-access-conditions`

The access conditions are the licence and any restriction the deposit and the consent impose. The licence of the deposit record, the repository's access route, and any
controlled-access condition the consent or the ethics approval imposes, with
who grants access and how.

## Block `un-maintenance`

The maintenance says who maintains the resource, how errors are reported and how versions are released. The maintainer and contact route, how errata are reported, and the
versioning of the deposit (each new version is a new deposit record).

## LIA house style

No data descriptor of this line has been measured yet: the rules below carry the group's writing rules from the experimental and observational lines to a data resource, and the extent at the top of this contract stays the target. They read the records the line keeps: the locked protocol revision `protocol/study-protocol-<slug>-vNN.md` and `study/protocol.lock.json`, the ethics record `study/ethics.json`, the datasets registry `datasets/registry.json` (the own-data statement or the licence decision, the de-identification statement and the deposit record), each dataset's dictionary `datasets/<slug>/dictionary.json` and quality report `datasets/<slug>/qc.json`, and the analysis log `analysis/log.jsonl`.

**Measured size.** None yet; the extent above follows the group's descriptor drafts.

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

- An intended use that the locked protocol and the records do not support.
- A limitation the technical validation reported and the notes leave out.
- Access terms that differ from the licence of the deposit record or the consent.
- No maintainer or contact route.

## Inputs

### External inputs

| Input | Unblocks |
|---|---|
| `repository-url` — The access conditions are the licence and any restriction the deposit and the consent impose. | `un-access-conditions` |

### Internal chain

None: no block of this section waits on another block.
