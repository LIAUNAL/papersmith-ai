---
name: systematic-review
description: "Trigger: a review workspace (`smith init --kind review`) builds a systematic review paper with no experiments, following PRISMA 2020 (`/systematic-review scope|protocol|search|screen|appraise|extract|synthesize|checklist`). Keeps every stage's record under review/ (protocol, logged searches, deduplicated records, two-reviewer screening with Cohen's kappa, appraisal, extraction), counts the PRISMA flow and draws its diagram, and reports the 27-item checklist. Keyless: OpenAlex, Crossref and Europe PMC, plus RIS/BibTeX exports from Scopus, Web of Science, IEEE Xplore or ACM."
---

# Systematic review (PRISMA 2020)

A systematic review earns its place in a journal by being reproducible: a
reader must be able to rerun the search, see why each study left, and check
every number of the flow diagram. This skill keeps that trail as records under
`review/` and lets the paper be written from them, never from memory. It is
the review line's counterpart of the experimental flow: no proposal, no
experiments, no remote runs. The reporting standard is the PRISMA 2020
statement (Page et al., 2021, BMJ 372:n71, doi:10.1136/bmj.n71); for software
engineering topics the Kitchenham and Charters guidelines add the quality
checklist.

Every command below is `python skills/systematic-review/scripts/review_cli.py
<verb> --root .` (the `--root` goes before the verb) and prints one JSON
object; a refusal prints `{"ok": false, "error": <CODE>, "message": …}` and
exits 2. Read the refusal and fix its cause; never edit a `review/*.jsonl`
file by hand to get past one.

## Inputs

| Input | Source | When absent |
|---|---|---|
| A review workspace | `smith init --kind review` (`paper_kind: "review"`) | the experimental line has no `review/`; tell the operator to start a review workspace |
| The topic | the operator's words after `/systematic-review scope` | ask for it in at least two sentences |
| The protocol | `review/protocol.json`, approved by the operator | `PROTOCOL_ABSENT`, `PROTOCOL_INVALID`, `PROTOCOL_NOT_APPROVED` |
| Database exports | RIS or BibTeX files the operator downloads from Scopus, Web of Science, IEEE Xplore, ACM | only the open sources are searched; say so in the limitations |
| Full texts | `/paper-ingestion <PDF or URL>` into `guidance/` | the record is decided `not-retrieved` at full text |

## Stages

### 1. `scope`: is a new review needed?

`review_cli.py scope --query "<topic words>"` lists existing reviews on the
topic (OpenAlex, `type:review`) into `review/scope.json`. Read their titles,
years and scopes with the operator: the new review's gap is what they leave
unanswered (scope, period, method). Scope searches are not part of the PRISMA
flow.

### 2. `protocol`: the plan, approved before any search

`review_cli.py init` writes `review/protocol.json` with placeholders. Fill it
with the operator, in English:

- `objective` and `research_questions` (`RQ1`, … each with its PICOC:
  population, intervention, comparison, outcomes, context);
- `criteria.inclusion` (`I1`, …) and `criteria.exclusion` (`E1`, …), each
  with its reason; full-text exclusions must name one of these ids;
- `sources`: one entry per database with the exact query string to run
  (`openalex`, `crossref`, `europepmc` are run by this skill; any other name,
  such as `scopus`, documents a query the operator runs and exports);
- `date_range`, `languages`, `publication_types`;
- `screening.reviewers` (2 by default: the agent may be one, the operator is
  always another);
- `appraisal`: the checklist (`QA1`, …), the answer scale and an optional
  exclusion threshold;
- `extraction.fields`: the data items (`text`, `number`, `category` with
  `options`, `list`).

`protocol check` lists what is missing. The operator reads it and approves:
`protocol approve --by "<operator name>"` (gate **G-PROTOCOL**). The agent
never approves on the operator's behalf. A change after approval is an
amendment, `protocol amend --by <name> --reason "<why>"`, which the methods
must report. Registration (PROSPERO for health topics, OSF otherwise) is
recorded as the `review-registration` declaration of `/paper-writing`.

### 3. Identification

- `search --source openalex|crossref|europepmc [--max N]` runs that source's
  query from the protocol, bounded by its date range, and logs date, query,
  total hits and records retrieved in `review/searches.jsonl`. When the source
  reports more hits than were retrieved, narrow the query or raise `--max`:
  PRISMA counts what was retrieved.
- `import --file <export.ris|.bib> --source scopus --query "<as run>"` adds a
  database export with the query the operator ran.
- `dedupe` marks duplicates (same DOI, then same normalized title and year);
  the first record identified is kept.

### 4. Screening (two stages, two reviewers)

- `queue --stage ta --reviewer <name>` lists the records a reviewer still owes
  at title/abstract.
- `screen --stage ta --record R0001 --reviewer <name> --decision
  include|exclude [--reason E<n>] [--note …]`. When the agent screens, it
  writes one decision per record with the criterion that decided it, from the
  title and abstract only; uncertain records are included, so the full text
  decides.
- `conflicts --stage ta` lists disagreements; the operator settles each with
  `screen … --final`.
- `kappa --stage ta` reports the agreement; the methods report it.
- Full text (`--stage ft`) repeats this on the records kept, after
  `/paper-ingestion` retrieves them: `include`, `exclude --reason E<n>`
  (mandatory) or `not-retrieved`.

### 5. Appraisal and extraction

- `appraise --record R… --reviewer <name> --answers '{"QA1": "yes", …}'` for
  every included study (all questions answered).
- `extract --record R… --extractor <name> --data '{"method": {"value": "…",
  "quote": "…"}}'`: every value carries the quote (or page) of the study that
  holds it. The agent extracts from the ingested Markdown; the operator checks
  a sample.

### 6. Synthesis

- `prisma` writes `review/prisma.json`; `flow` draws the PRISMA 2020 flow
  diagram to `paper/Figures/prisma-flow.svg` from those counts.
- `biblio` writes per-year and per-venue counts and keyword co-occurrence to
  `review/biblio.json` (from the included studies, or the screened records
  before any is included).
- The taxonomy is built by the agent with the operator from
  `review/extraction.jsonl`: the themes (each answering a research question),
  the problem classes (the background's open problems, with the same names)
  and the dimensions each theme is compared along, with one comparison table
  per theme. The results are a comparative synthesis: each paragraph compares
  several studies along one dimension, the citation closes the sentence and is
  never its subject, and each sub-theme closes on what the evidence supports.
  The section contracts in `sections/` hold the full rules.

### 7. Writing and reporting check

`/paper-writing` writes the review sections (`sections/` holds the review
contracts in a review workspace). Every count is copied from
`review/prisma.json`. `checklist` maps the 27 PRISMA 2020 items to the blocks
that report each and the record that evidences it, and lists the items still
owed, each with what is missing: `record:<name>` (a `review/` record not on
file yet), `text:<block>` (a block of `paper/main.tex` that holds no text, as
`paper_cli.py status` reports it) or `declaration:review-registration` (item
24). Journals ask for the completed checklist as a supplementary file.

The protocol's `languages` and `publication_types` are not search filters
(the open APIs do not apply them uniformly): they are eligibility criteria,
applied at screening through the protocol's exclusion criteria.

## Outputs

`review/protocol.json`, `review/protocol.lock.json`, `review/searches.jsonl`,
`review/records.jsonl`, `review/screening.jsonl`, `review/appraisal.jsonl`,
`review/extraction.jsonl`, `review/prisma.json`, `review/biblio.json`,
`review/scope.json`, `paper/Figures/prisma-flow.svg`.

## Refusals

`PROTOCOL_ABSENT`, `PROTOCOL_INVALID`, `PROTOCOL_EXISTS`,
`PROTOCOL_NOT_APPROVED`, `PROTOCOL_CHANGED` (amend it),
`PROTOCOL_ALREADY_APPROVED`, `PROTOCOL_UNCHANGED`, `APPROVER_MISSING`,
`AMENDMENT_REASON_MISSING`, `SOURCE_NOT_IN_PROTOCOL`, `SOURCE_UNAVAILABLE`,
`QUERY_TOO_SHORT`, `QUERY_MISSING`, `IMPORT_FILE_ABSENT`, `IMPORT_EMPTY`,
`NO_RECORDS`, `RECORD_NOT_ELIGIBLE`, `DECISION_INVALID`, `REASON_MISSING`,
`REASON_UNKNOWN`, `REASON_UNEXPECTED`, `REVIEWER_MISSING`,
`REVIEWERS_AMBIGUOUS`, `RECORD_NOT_INCLUDED`, `ANSWERS_INCOMPLETE`,
`ANSWER_UNKNOWN`, `FIELD_UNKNOWN`, `DATA_INVALID`, `ARGUMENT_INVALID`,
`RECORDS_CORRUPT`, `USAGE`.

## Rules

- The agent never approves the protocol, never settles a conflict with
  `--final` and never signs as the operator.
- A stage never runs on an unapproved or silently changed protocol.
- Nothing is scraped: databases without an open API come in as the
  operator's exports.
- Numbers in the paper come from `review/prisma.json` and the records, never
  from a recount by hand.
