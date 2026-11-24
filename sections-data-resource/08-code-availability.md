---
{
  "section": "code-availability",
  "position": 8,
  "mode": {
    "value": "transposition",
    "source": {
      "file": "sections/08-code-availability.md",
      "quote": "The code availability names the code that collected, processed and validated the data and where it is."
    }
  },
  "blocks": [
    {
      "id": "ca-code",
      "requires_facts": [],
      "requires_declarations": [
        {
          "value": "repository-url",
          "source": {
            "file": "sections/08-code-availability.md",
            "quote": "The code is the scripts of the analysis log and the collection tools, with their repository, version and licence."
          }
        }
      ],
      "citations": "none"
    }
  ]
}
---

# Code Availability (data-resource line)

The code availability names the code that collected, processed and validated the data and where it is.
Every script that produced a deposited file or a reported figure is named with
its location, version and licence.

**Extent** 40–200 words · one paragraph

## Block `ca-code`

The code is the scripts of the analysis log and the collection tools, with their repository, version and licence. The repository of the code (the `repository-url` declaration), the version
or commit, the licence, and the scripts the analysis log hashes for the
preprocessing, the quality checks and the baselines, with the language and
library versions. When no custom code was used, say so.

## LIA house style

No data descriptor of this line has been measured yet: the rules below carry the group's writing rules from the experimental and observational lines to a data resource, and the extent at the top of this contract stays the target. They read the records the line keeps: the locked protocol revision `protocol/study-protocol-<slug>-vNN.md` and `study/protocol.lock.json`, the ethics record `study/ethics.json`, the datasets registry `datasets/registry.json` (the own-data statement or the licence decision, the de-identification statement and the deposit record), each dataset's dictionary `datasets/<slug>/dictionary.json` and quality report `datasets/<slug>/qc.json`, and the analysis log `analysis/log.jsonl`.

**Measured size.** None yet; one short paragraph in the group's descriptor drafts.

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

- A script that produced a deposited file or a reported figure and is not named.
- Code available only on request without the reason stated.

## Inputs

### External inputs

| Input | Unblocks |
|---|---|
| `repository-url` — The code is the scripts of the analysis log and the collection tools, with their repository, version and licence. | `ca-code` |

### Internal chain

None: no block of this section waits on another block.
