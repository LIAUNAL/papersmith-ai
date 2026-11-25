---
{
  "section": "background-summary",
  "position": 3,
  "mode": {
    "value": "argument",
    "source": {
      "file": "sections/03-background-summary.md",
      "quote": "The background and summary argue why this resource is needed and say what it holds and how it was made."
    }
  },
  "blocks": [
    {
      "id": "bs-context",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "discovery",
      "produces_facts": [
        {
          "value": "problem-statement",
          "source": {
            "file": "sections/03-background-summary.md",
            "quote": "The problem-statement says which question or task needs data like these and why the existing data do not serve it."
          }
        }
      ]
    },
    {
      "id": "bs-prior-resources",
      "requires_facts": [
        {
          "value": "problem-statement",
          "source": {
            "file": "sections/03-background-summary.md",
            "quote": "The gap is what the closest existing datasets, corpora or benchmarks leave out for this task."
          }
        }
      ],
      "requires_declarations": [],
      "citations": "discovery",
      "after": [
        {
          "target": "background-summary.bs-context",
          "source": {
            "file": "sections/03-background-summary.md",
            "quote": "The gap is what the closest existing datasets, corpora or benchmarks leave out for this task."
          }
        }
      ],
      "produces_facts": [
        {
          "value": "gap",
          "source": {
            "file": "sections/03-background-summary.md",
            "quote": "The gap is what the closest existing datasets, corpora or benchmarks leave out for this task."
          }
        }
      ]
    },
    {
      "id": "bs-summary",
      "requires_facts": [
        {
          "value": "gap",
          "source": {
            "file": "sections/03-background-summary.md",
            "quote": "The contributions are the resource itself: what it holds, how it was collected and what it lets others do."
          }
        }
      ],
      "requires_declarations": [],
      "citations": "none",
      "after": [
        {
          "target": "background-summary.bs-prior-resources",
          "source": {
            "file": "sections/03-background-summary.md",
            "quote": "The contributions are the resource itself: what it holds, how it was collected and what it lets others do."
          }
        }
      ],
      "produces_facts": [
        {
          "value": "contributions",
          "source": {
            "file": "sections/03-background-summary.md",
            "quote": "The contributions are the resource itself: what it holds, how it was collected and what it lets others do."
          }
        }
      ]
    },
    {
      "id": "bs-prior-use",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "resolution",
      "optional": true
    }
  ]
}
---

# Background and Summary (data-resource line)

The background and summary argue why this resource is needed and say what it holds and how it was made.
Datasheets for Datasets asks first why the dataset was created, for which task
and which gap it fills, and who created and funded it; this section answers
those questions for a reader who has not seen the data.

**Extent** 400–800 words · 3 to 5 paragraphs

## Block `bs-context`

The problem-statement says which question or task needs data like these and why the existing data do not serve it. The research field, the task or the questions the resource serves, and why
they need data of this kind. Every claim is cited from the literature; nothing
here comes from the resource's own records.

## Block `bs-prior-resources`

The gap is what the closest existing datasets, corpora or benchmarks leave out for this task. Name the closest existing resources and what each holds (size, population,
modality, annotation, licence and access), and say what remains open: a
population, language, setting or modality not covered, annotations missing, a
licence that forbids reuse, no documentation. A gap is never a lack stated
without the resources that leave it open.

## Block `bs-summary`

The contributions are the resource itself: what it holds, how it was collected and what it lets others do. One paragraph of 100–200 words in running prose: the records, the sources
and the collection period, the annotations, the deposit, and the uses the
resource was built for, with the purpose stated in the locked protocol. Who
collected the data and who funded it come from the back matter. No numbered
or bulleted list of contributions.

## Block `bs-prior-use`

Earlier publications that used the resource, or a previous version of it, are cited when they exist. Each publication that already used the data, or a previous release of the
resource, cited with what it used; omitted when there is none.

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

- A claim of the background without a citation that holds it.
- A gap stated as a lack (*few datasets exist*) without naming the closest resources and what each leaves open.
- A finding drawn from the resource's own data.
- A purpose or a use that the locked protocol does not state.
- Contributions given as a numbered or bulleted list instead of the summary paragraph.
- A citation used as the subject of a sentence.

## Inputs

### External inputs

| Input | Unblocks |
|---|---|
| `problem-statement` — The gap is what the closest existing datasets, corpora or benchmarks leave out for this task. | `bs-prior-resources` |
| `gap` — The contributions are the resource itself: what it holds, how it was collected and what it lets others do. | `bs-summary` |

### Internal chain

| Block | Depends on |
|---|---|
| `background-summary.bs-prior-resources` — The gap is what the closest existing datasets, corpora or benchmarks leave out for this task. | `background-summary.bs-context` |
| `background-summary.bs-summary` — The contributions are the resource itself: what it holds, how it was collected and what it lets others do. | `background-summary.bs-prior-resources` |
