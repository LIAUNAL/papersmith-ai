---
{
  "section": "technical-validation",
  "position": 6,
  "mode": {
    "value": "transposition",
    "source": {
      "file": "sections/06-technical-validation.md",
      "quote": "The technical validation reports the checks that support the quality of the data, as the operator's records hold them."
    }
  },
  "blocks": [
    {
      "id": "tv-quality-checks",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none"
    },
    {
      "id": "tv-annotator-agreement",
      "requires_facts": [],
      "requires_declarations": [],
      "citations": "none",
      "optional": true
    },
    {
      "id": "tv-baselines",
      "requires_facts": [
        {
          "value": "outcomes",
          "source": {
            "file": "sections/06-technical-validation.md",
            "quote": "The baselines are the reference results the outcomes and the analysis plan of the locked protocol name, each from a run in the analysis log."
          }
        },
        {
          "value": "analysis-plan",
          "source": {
            "file": "sections/06-technical-validation.md",
            "quote": "The baselines are the reference results the outcomes and the analysis plan of the locked protocol name, each from a run in the analysis log."
          }
        }
      ],
      "requires_declarations": [],
      "citations": "resolution"
    }
  ]
}
---

# Technical Validation (data-resource line)

The technical validation reports the checks that support the quality of the data, as the operator's records hold them.
This section replaces results and discussion: it shows that the data are what
the methods say they are, and draws no scientific conclusion from them.

**Extent** 300–1000 words · one subsection per block

## Block `tv-quality-checks`

The quality checks are the results of the quality report the operator's data produced. Missing values, duplicates, out-of-range values against the dictionary,
class or label balance and subject structure, copied from
`datasets/<slug>/qc.json` as `datasets_cli.py --root . qc` wrote it against
the current files and dictionary. A check that failed is reported with what
was done about it.

## Block `tv-annotator-agreement`

The agreement between annotators is reported when the resource carries labels. This block is optional: only when the records carry human labels. The
agreement statistic named in the protocol, computed on the doubly annotated
subset by a run in `analysis/log.jsonl`, with the size of that subset and how
disagreements were resolved.

## Block `tv-baselines`

The baselines are the reference results the outcomes and the analysis plan of the locked protocol name, each from a run in the analysis log. Each baseline model or reference method with its split, metric and score,
copied from the outputs of its run in `analysis/log.jsonl` (`analysis_cli.py
run` or the operator's `record` for a GUI tool), with its label as the log
computed it: confirmatory only when the locked protocol names the outcome and
the plan, exploratory otherwise. A baseline shows the data can be used; it
is not a claim about the task.

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

- A quality figure that the quality report does not hold, or a report older than the current files or dictionary.
- An agreement statistic without its subset size, or for labels the resource does not carry.
- A baseline score with no run in the analysis log, or an exploratory baseline presented as confirmatory.
- A scientific conclusion drawn from the data.

## Inputs

### External inputs

| Input | Unblocks |
|---|---|
| `outcomes` — The baselines are the reference results the outcomes and the analysis plan of the locked protocol name, each from a run in the analysis log. | `tv-baselines` |
| `analysis-plan` — The baselines are the reference results the outcomes and the analysis plan of the locked protocol name, each from a run in the analysis log. | `tv-baselines` |

### Internal chain

None: no block of this section waits on another block.
