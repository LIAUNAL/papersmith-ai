---
name: datasets
description: "Trigger: give the proof of concept and the full experiments data to stand on — a seeded toy set always, then a real dataset searched for across official paper repositories, Kaggle, Hugging Face, OpenNeuro and Zenodo, with its source license checked, its quality measured, one official subject-wise preparation both stages read, and private publishing to Kaggle only on the operator's consent. Stdlib-only CLI, no venv, no API keys."
---

# Datasets

Data the experiments can stand on, and a record of why it may be used.

A proof of concept should never wait on a download, so a **seeded toy set**
comes first and always. The real dataset comes second, and the questions that
matter about it are not technical: *may we use it, may we redistribute it, is
it what it claims to be, and is the split the one the paper reports?* Each
answer is written to disk — `datasets/registry.json` and one folder per
dataset — so a later session reads it instead of re-deciding it.

## The objective flow

**Why this skill was invoked, and where it has to arrive.** Declared here and
in `OBJECTIVE_FLOW` (`scripts/datasets_cli.py`), held equal by a test. Every
refusal prints the flow, so a blocked session knows which stage it is behind.

| Stage | Establishes | Behind when |
|---|---|---|
| `toy` | a seeded synthetic set exists, so the proof of concept never waits on real data | the registry holds no entry with role toy |
| `sourced` | candidate real datasets were searched for; every hit is on disk with its URL and date | no `datasets/search-*.json` and no full entry names a source URL |
| `licensed` | the source license was read and mapped to a decision before any data moves | no decision, or refused without an override |
| `checked` | shape, gaps, balance and subject structure are measured in `qc.json` | qc missing or `fail` |
| `prepared` | one versioned subject-wise split both experiment stages read, tied to the source sha256 | no `PREPARATION.md` + `splits.json` |
| `published` | the prepared set sits on the remote dataset host, private unless made public on consent | no remote ref recorded |

**Arrival:** a toy set and a licensed, checked, prepared dataset that the proof of concept and the full experiments both read, published privately only on the operator's consent.

**Three stops are a person's, and the CLI enforces each one:**

1. **License override** — a refused source license (non-commercial, no
   derivatives, credentialed / data use agreement, unknown) stays refused
   unless the operator gives `--override "<reason>"`; the reason is recorded.
2. **Upload consent** — `publish` is a dry run unless `--consent <slug>`
   repeats the dataset's slug exactly. Consent is per dataset, never global.
3. **Public consent** — a dataset is created private. `--public` takes effect
   only together with `--consent-public <slug>`, a second, separate token.

**Own data adds a fourth.** Data the operator collected has no source license
to classify: `own --by <operator> --statement "<data-use statement>"` records
the operator's own statement of how it may be used, and `--by` names that
operator.

An agent never types any of these tokens on its own initiative: they are the
operator's words, relayed.

## Accepted operations

```
python3 skills/datasets/scripts/datasets_cli.py [--root <workspace>] <verb> ...
```

| Verb | What it does |
|---|---|
| `synth` | `--slug --kind {classification,eeg} --seed --n-subjects --n-per-subject --channels --length --sfreq [--profile {alpha,theta-beta,capacity}] [--label-per {trial,subject}] [--force]`: seeded toy CSV + `datasets/<slug>/TOY.md` with the generating parameters; role `toy`. Same seed, same bytes. For `eeg`, `--profile alpha` (default) is a 10 Hz rhythm whose band power depends on the class; `--profile theta-beta` is a Theta (6 Hz) and a Beta (20 Hz) rhythm whose ratio depends on the class (class 1 elevated), needing `--sfreq` above 40 Hz; both add a per-subject gain and Gaussian noise. `--label-per subject` gives every subject one class (balanced across subjects), which a protocol that decides per subject needs; the default `trial` alternates classes within each subject. `--profile capacity` is described below |
| `search` | `--query [--hosts ...] [--limit]`: queries every host module (official MCP `search_datasets` on Kaggle, Hugging Face Hub, OpenNeuro GraphQL, Zenodo) and writes `datasets/search-<date>.json` with every hit `{host, ref, title, url, license, retrieved}`. A host that fails is recorded, never fatal. Google Dataset Search has no API: its link is printed for a manual look |
| `license` | `--slug --source-license "<text>" [--override "<reason>"] [--title] [--source-url] [--role]`: decision `allowed` / `refused` / `overridden`, mapped to a host license name (`CC0-1.0`, `CC-BY-4.0`, `CC-BY-SA-4.0`, `ODbL-1.0`, `CC-BY-NC-4.0`, `CC-BY-NC-SA-4.0`, `other`); creates the full entry when missing |
| `own` | `--slug --by <operator> --statement "<text>" [--title]`: registers the operator's own data — role `own`, `source.kind` `own`, `data_use{statement, by, recorded, history?}` — in place of a license classification (the license record reads `own data`, decision `allowed`, host license `other`). Running it again replaces the statement and keeps the previous ones under `history`. It never turns a `toy` or `full` entry into own data, and `license` never reclassifies an own entry (`role-conflict`) |
| `dictionary` | `init --slug --file <csv> [--force]`: scaffolds `datasets/<slug>/dictionary.json` with one entry per header column (type inferred, levels for a small category, PII flagged from the column name, everything else blank for the operator to fill). `check --slug`: validates it and lists the PII columns. See [Own data and the data dictionary](#own-data-and-the-data-dictionary) |
| `qc` | `--slug --file <csv> [--label col] [--group col]`: rows/columns, missing values, constant columns, duplicates, class balance, group (subject) counts and single-class groups, numeric ranges → `datasets/<slug>/qc.json` (with the file's `sha256`), status `pass` / `warn` / `fail` with reasons. When `datasets/<slug>/dictionary.json` exists, it is validated first and the data is checked against it into `domain_checks`; own data without a dictionary warns |
| `prepare` | `--slug --file <csv> --label col --group col [--folds 5] [--seed <n> \| --seeds <n> <n> ...]`: stratified group k-fold by subject (no subject in two folds) → `splits.json` + `PREPARATION.md` (source sha256, steps, parameters, per-fold counts); each run is a new preparation version. `--seed` writes one split; its seed only breaks ties between equal-sized subjects, so when every subject differs in size the output carries an `inert-seed` warning. `--seeds` writes one split per seed under `repetitions` (repeated cross-validation): subjects are taken largest first in size strata of `--folds` subjects that the seed shuffles, so each seed gives its own split; the first repetition is also the top-level `assignment` |
| `publish` | `--slug --owner <user> [--version-notes] [--keyword ...] [--consent <slug>] [--public --consent-public <slug>] [--dry-run]`: builds `datasets/<slug>/remote/` (`dataset-metadata.json` + copies of the files) and, on consent, runs `kaggle datasets create -p <dir>` (private; `-u` only with both public flags) or `kaggle datasets version -p <dir> -m <notes>` when the dataset already exists; records the remote ref, visibility and version; prints how a notebook mounts it |
| `status` | registry summary: slug, role, title, license decision, qc status, preparation, remote |

Success prints one JSON object on stdout. A refusal prints
`{"error", "message", "objective"}` on stderr and exits 2:

| Error code | Meaning |
|---|---|
| `bad-slug` | slug is not 1–50 lowercase letters, digits and hyphens |
| `slug-exists` | `synth` onto a registered slug without `--force` |
| `member-exists` | `synth --profile capacity` onto a replicate file that already exists without `--force` |
| `unknown-slug` | the verb needs a registered dataset; run `synth` or `license` first |
| `bad-argument` | a size parameter is not positive |
| `file-missing` | a named or registered file does not exist |
| `file-outside-workspace` | a file resolves outside the workspace root |
| `bad-column` | `--label` / `--group` is not a column of the file |
| `bad-folds` | fewer than 2 folds |
| `too-few-groups` | fewer subjects than folds: a subject would land in two folds |
| `identical-repetitions` | two of the `--seeds` give the same split; choose seeds whose splits differ |
| `unknown-host` | `--hosts` names no host module |
| `license-not-allowed` | `publish` without an `allowed` or `overridden` decision |
| `bad-owner` | the remote account name is malformed |
| `bad-metadata` | the metadata the host requires is invalid (title 6–50 chars, subtitle 20–80, `owner/slug` id, one known license) or two files share a name |
| `public-consent-missing` | `--public` without `--consent-public <slug>` matching |
| `public-on-existing` | `--public` on a dataset that already exists; visibility is changed on the host, never here |
| `no-publisher` | no host module declares a publisher |
| `host-cli-missing` | the official `kaggle` client is not installed |
| `host-cli-failed` | the official client exited non-zero; nothing is recorded |
| `role-conflict` | `own` on a `toy` or `full` slug, or `license` on an own slug |
| `operator-missing` | `own --by` is blank: the statement must name the operator |
| `statement-missing` | `own --statement` is blank |
| `dictionary-missing` | `dictionary check` on a dataset with no `dictionary.json` |
| `dictionary-exists` | `dictionary init` over an existing dictionary without `--force` |
| `dictionary-unreadable` | `dictionary.json` is not JSON, or not an object with a `columns` list |
| `dictionary-unknown-type` | a column's type is not `number`, `integer`, `category`, `text`, `date` or `boolean` |
| `dictionary-range-not-numeric` | a range on a column whose type is not `number` or `integer` |
| `dictionary-empty-levels` | a `category` column without levels |
| `dictionary-duplicate-column` | a column declared twice (or repeated in the header `init` reads) |
| `dictionary-bad-entry` | any other malformed entry: a blank name, a range that is not `{min, max}` numbers with min ≤ max, repeated or non-string levels, levels on a non-category column, non-string missing codes, unit or description, a non-boolean `pii` |

## The capacity profile

`synth --kind eeg --profile capacity --rule {monotone,interaction,frequency-two} [--d-prime D] --seed K
[--n-train 60 --n-val 10 --n-test 100 --n-per-subject 12 --length 256 --sfreq 128] [--force]` writes one
replicate of a family of toy sets meant to test what a classifier can represent, not just whether the
pipeline runs (`scripts/capacity_toy.py`, stdlib, generator version 1):

- **Fresh subjects per replicate.** Each replicate draws its own training, validation and test subjects,
  one class per subject, balanced within each group (so every group size is even). Because the generator
  yields independent subjects without limit, an experiment can score on new subjects instead of
  cross-validating; that holds for synthetic data only.
- **Signal.** The 19-channel montage of the declared dataset (Fp1 ... Pz in its own order); narrowband Theta,
  Beta and Alpha over an AR(1) red-noise background, each channel mixed with its two neighbours, frontal eye
  blinks in a fraction of the epochs; the class effect acts on the frontal and central channels only.
- **Rules.** `monotone` draws the subject's log Theta/Beta offset from N(+-d'/2, 1) by class, so the
  subject-level Bayes limit is Phi(d'/2) (`--d-prime` is required and positive); `interaction` draws
  independent Theta and Beta deviations, class 1 when both deviate in the same direction, so the log ratio
  carries no class; `frequency-two` draws a Theta deviation u uniform over one period, class 1 where
  cos(2u) > 0. `--d-prime` with another rule is refused, as are `--n-subjects`, `--channels` other than 19,
  `--label-per trial` and an `--sfreq` at or below 60 Hz: an option this profile cannot honour is never
  silently ignored.
- **Files.** `datasets/<slug>/<rule>[-d<d'>]-s<seed>.npy` (little-endian float32, epochs x channels x
  samples, readable by `numpy.load`) and a `.json` sidecar with the subjects, their split, clean label and
  deviation, the per-epoch subject/split/label, the parameters and the `.npy` sha256. All replicates share one
  registry entry (role `toy`) whose `files` lists them, and one `TOY.md` that describes the family. Label
  noise belongs to the experiment, which flips training labels itself; the files carry clean labels only.

## Own data and the data dictionary

Data the operator collected — a cohort, a survey, field plots, lab records —
enters with `own` instead of `license`: the question is not what a source's
license permits but what the operator's consent, ethics approval and agreements
allow, and only the operator can state that. For own data, `own` stands for the
`sourced` and `licensed` stages; `qc`, `prepare` and `publish` (still only on
`--consent`) work as for any entry.

`datasets/<slug>/dictionary.json` describes each column:

```json
{"slug": "cohort", "file": "data/cohort.csv", "sha256": "…", "created": "2026-11-22",
 "columns": [{"name": "sbp", "type": "number", "unit": "mmHg", "range": {"min": 60, "max": 240},
              "levels": null, "missing_codes": ["999"], "description": "systolic blood pressure", "pii": false}]}
```

`type` is one of `number`, `integer`, `category` (with its non-empty
`levels`), `text`, `date` (ISO `YYYY-MM-DD`) or `boolean` (`true/false`,
`yes/no`, `t/f`, `y/n`, `1/0`, any case). `range` applies to `number` and
`integer` only; either bound may be null. `missing_codes` are exact strings
counted as missing, besides the generic blanks and `na`/`nan`/`null`/`none`.
`pii` marks a column that identifies a person. `dictionary init` only
scaffolds: the operator (or the curator, with the operator) reviews every
field, then `dictionary check` validates it.

With a dictionary, `qc` counts the declared missing codes as missing (in
`missing`, and out of `ranges`), withholds the ranges and class values of PII
columns, records the dictionary's path and sha256 under `dictionary`, and fills
`domain_checks` with one item per finding: `{check, column, severity, count,
rows?, values?, …}`. `rows` are the first five data rows (1 is the first row
under the header); `values` are up to three distinct offending values, never
given for a PII column.

| Check | Severity | Finding |
|---|---|---|
| `absent-column` | `fail` | declared in the dictionary, absent from the file |
| `type-mismatch` | `fail` | a present value is not of the declared type |
| `out-of-range` | `warn` | a numeric value outside the declared range |
| `unknown-level` | `warn` | a category value outside the declared levels |
| `undeclared-column` | `warn` | in the file, not in the dictionary |
| `pii-column` | `warn` | a PII column is in the file (count of present values): confirm it may be |
| `missing-codes` | `info` | how many values were declared missing codes |

The status rule: any `fail` check fails the report; any `warn` check turns a
`pass` into a `warn`; `info` changes nothing; the stdlib checks keep their own
rules. Own data with no dictionary warns. The file's `sha256` stays in
`qc.json`, so what is checked can be bound to what is analysed.

## Workspace state

`datasets/registry.json` is a list of entries:
`{slug, role: "toy"|"full"|"own", title, source{kind, url, retrieved},
license{source_name, decision, host_license, reason, override?},
data_use?{statement, by, recorded, history?},
files, qc{status, report}, preparation{manifest, splits, version, sha256},
remote{ref, visibility, version}}`. One folder `datasets/<slug>/` holds
`TOY.md`, `dictionary.json`, `qc.json`, `splits.json`, `PREPARATION.md` and
the `remote/` upload folder.

**The preparation is the official one.** The proof of concept and the full
experiments both read `datasets/<slug>/splits.json`; neither re-splits in its
own code. When the preparation changes, `prepare` writes a new version and
`PREPARATION.md` says so, so a result can always be traced to the split and
the source sha256 it ran on.

## Quality checks beyond the stdlib

`qc` measures what the standard library can, and the dictionary's domain
checks fill `domain_checks` on their own. For EEG, the `dataset-curator`
agent may also run domain checks in the workspace environment — for example
MNE-Python for channel names, sampling rate and flat or saturated channels,
or PyPREP for bad-channel detection — and append each check, its tool version
and its verdict to the `domain_checks` list of the same `qc.json`. Those tools
are optional and never a dependency of this CLI.

## Publishing and mounting

Publishing uses the **official client** (`pip install kaggle` in the
operator's environment), which reads the token itself from
`~/.kaggle/access_token` or the exported `KAGGLE_API_TOKEN` — the same
convention `smith mcp kaggle activate` writes. This skill never reads, stores,
prints or passes the token. Search uses the official remote MCP's public
`search_datasets`, which answers without one.

A notebook attaches the dataset as an input and finds it under
`/kaggle/input/`; the exact sub-path can vary, so discover it with
`os.walk('/kaggle/input')` rather than hard-coding it.

A remote job declares a registry dataset as its input with `remote_cli
generate-job --dataset <slug>` (or `generate-jobs --dataset <slug>`), which
reads this registry through `job_input()` in `scripts/datasets_cli.py`: the
published remote when it is public, else the public dataset page the source
URL names on a host whose module declares `ref_from_url`, with the
preparation's sha256 values recorded for the target to check. It uploads
nothing; an unpublished or private dataset is refused naming `publish` with
the operator's consent.

## Delegation

| Stretch | Delegated to |
|---|---|
| `sourced` → `licensed` | this skill delegates to the `dataset-scout` agent: web search of the paper's official repository and data statement, the `search` verb, and a `license` decision per candidate; it returns ranked candidates with URLs and decisions |
| `toy`, `checked` → `published` | this skill delegates to the `dataset-curator` agent: `synth`, fetching a licensed source, `qc`, `prepare`, and `publish` only with the operator's consent tokens |

**Measure this before delegating.** Run `status` first. The scout needs a
stated research question or paper; the curator needs, for real data, an entry
whose license decision is `allowed` or `overridden`, and for `publish`, the
operator's `--consent <slug>` already given in the conversation.

## When a delegated agent cannot be spawned

Each stretch this skill delegates is defined in full by its own agent file:
`.claude/agents/dataset-scout.md`, `.claude/agents/dataset-curator.md`. When an
agent cannot be spawned — the harness has no sub-agent mechanism, the agent is
not registered in this session, or the spawn itself fails — perform the
stretch inline: read that agent's definition file and follow it as written,
from the beginning it states to the end it states, holding every gate this
skill sets (license override, upload consent, public consent), and returning
the report shape it specifies. Its `tools:` line still bounds the stretch: an
act that would need a tool outside that list is a stop, not a workaround. Say
in the reply that the stretch ran inline and why the agent could not be
spawned.

## Compatibility

Runs unchanged under **Claude Code, OpenCode and Pi**: the CLI is plain
`python3` with no third-party imports, the agents run on the active session's
own model and subscription, and nothing here calls an LLM API or needs an API
key. Network is used only by `search` and `publish`.

## Personal data

EEG and other physiological recordings — the kind a brain-signal workspace
uses — can contain **personal data** (identifiers in headers, dates, health
information). Checking that a dataset is de-identified, that its consent and
license allow the intended use and redistribution, and that publishing it is
lawful where the operator works is the **operator's responsibility**. When in
doubt, keep it private or do not upload it.

## Output Reporting

Report what changed: entries created, decisions recorded, qc status and
reasons, the preparation version, and the remote ref with its visibility.
Speak the user's language; slugs, paths and flags are never translated.
