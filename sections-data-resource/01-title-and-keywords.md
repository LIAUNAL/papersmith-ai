---
{
  "section": "title-and-keywords",
  "position": 1,
  "mode": {
    "value": "transposition",
    "source": {
      "file": "sections/01-title-and-keywords.md",
      "quote": "The title names the resource, what it holds and the population, domain or task it covers, with the words the methods use."
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
            "quote": "The contributions of the resource, what it holds and what it lets others do, decide the title."
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none",
      "after": [
        {
          "target": "background-summary.bs-summary",
          "source": {
            "file": "sections/01-title-and-keywords.md",
            "quote": "The contributions of the resource, what it holds and what it lets others do, decide the title."
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

# Title and Keywords (data-resource line)

The title names the resource, what it holds and the population, domain or task it covers, with the words the methods use.
A data descriptor names the data, not a finding: the kind of records (recordings,
images, annotated texts, measurements), what they capture and where or from whom
they come.

**Extent** 8–20 words · keywords 4–6

## Block `title`

The contributions of the resource, what it holds and what it lets others do, decide the title. The title states the kind of records, what they capture and the population,
source or setting, and may name the resource by its short name once the
abstract expands it ("<short name>: <records> of <what> from <population or
source>"). No finding, no question form, no result stated as a verb, and no
claim of size or quality the data records section does not count.

## Block `keywords`

The keyword-bounds and the classification-line come from the venue. Four to six keywords, none repeating a word of the title, the kind of
resource (*dataset*, *corpus*, *benchmark*) included as one of them.

## LIA house style

No data descriptor of this line has been measured yet: the rules below carry the group's writing rules from the experimental and observational lines to a data resource, and the extent at the top of this contract stays the target. They read the records the line keeps: the locked protocol revision `protocol/study-protocol-<slug>-vNN.md` and `study/protocol.lock.json`, the ethics record `study/ethics.json`, the datasets registry `datasets/registry.json` (the own-data statement or the licence decision, the de-identification statement and the deposit record), each dataset's dictionary `datasets/<slug>/dictionary.json` and quality report `datasets/<slug>/qc.json`, and the analysis log `analysis/log.jsonl`.

**Measured size.** None yet; data descriptor titles in the group's venues run 8 to 20 words.

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

- A title that names no kind of records, no content or no population, source or setting.
- A title that states a finding, or a size or quality the data records do not count.
- A promotional or evaluative word in the title (*Novel*, *Large-scale*, *Comprehensive*).
- A keyword that repeats a word of the title.
- An acronym or short name in the title that the abstract does not expand.

## Sources

- The locked protocol revision (`protocol/study-protocol-<slug>-vNN.md`): the sources, the population and the records collected, which fix the words of the title.

## Inputs

### External inputs

| Input | Unblocks |
|---|---|
| `contributions` — The contributions of the resource, what it holds and what it lets others do, decide the title. | `title` |
| `keyword-bounds` — The keyword-bounds and the classification-line come from the venue. | `keywords` |
| `classification-line` — The keyword-bounds and the classification-line come from the venue. | `keywords` |

### Internal chain

| Block | Depends on |
|---|---|
| `title-and-keywords.title` — The contributions of the resource, what it holds and what it lets others do, decide the title. | `background-summary.bs-summary` |
