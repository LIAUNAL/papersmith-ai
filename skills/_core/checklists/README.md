# Reporting-guideline checklists

A checklist engine that checks what a manuscript reports, not only that a
section exists. Each reporting guideline is one data file under
`guidelines/`; `engine.py` evaluates a workspace against it and
`checklist_cli.py` is the front door.

```
python skills/_core/checklists/checklist_cli.py list
python skills/_core/checklists/checklist_cli.py show <id>
python skills/_core/checklists/checklist_cli.py check --guideline <id> --root . [--json]
```

`list` and `show` print one JSON object; `check` prints a table, or one JSON
object with `--json`. A refusal prints `{"ok": false, "error", "message"}` and
exits 2: `USAGE`, `GUIDELINE_UNKNOWN`, `GUIDELINE_INVALID`, `NOT_A_WORKSPACE`
(the root has no `.papersmith/`).

## Results

Every item gets one status, with the evidence each rule used:

| Status | Meaning |
| --- | --- |
| `satisfied` | Every rule passed and the item has no judgment question. Only items whose content a rule checks completely reach it. |
| `missing` | A target is unwritten or does not exist in this workspace, a record is absent, or a content rule failed. Each failing rule says why. |
| `needs-judgment` | Everything the rules can check passed; a reader answers the item's `question`. The engine never turns it into `satisfied`. |

Each item also reports `presence`: the targets, files, records, commands and
declarations alone. For PRISMA 2020, `presence` equals the verdict of
`review_cli.py checklist` on the same workspace (the parity test in
`tests/test_checklist_engine.py`).

## Shipped guidelines

| Id | Guideline | Items | Targets |
| --- | --- | --- | --- |
| `prisma-2020` | PRISMA 2020 main checklist | 27 | the review line's blocks (ported from `review_cli.py`'s `CHECKLIST`) |
| `strobe` | STROBE combined checklist (cohort, case-control, cross-sectional) | 22 | generic section names |
| `stard-2015` | STARD 2015 | 30 | generic section names |

Sub-items (STROBE 6a/6b, STARD 10a/10b, …) are folded into their numbered
item, whose question names every part.

## How blocks and declarations are read

The same way `review_cli.py` reads them: the workspace's own
`skills/paper-writing/scripts/paper_cli.py status` and `phases`, run as
subprocesses once `paper/main.tex` exists. A block is written when its body is
not empty (its digest differs from the empty body's); its text is the slice of
`paper/main.tex` between its markers at the region `status` reports. Running
the workspace's copy keeps the reader at the version the workspace writes with
and imports nothing from paper-writing into this process.

A target is a section (`methods`, any of its blocks written) or a block
(`methods.m-eligibility`). Targets are given per paper line
(`{"review": [...]}`) or for every line (`{"default": [...]}`). The engine
resolves them against the workspace's `sections/` contracts and the blocks of
`paper/main.tex`; a target this workspace does not have is `missing` with the
reason and the sections it does declare.

## Data file schema

```json
{
  "schema": 1,
  "id": "strobe",
  "name": "STROBE (combined checklist)",
  "version": "2007 (checklist version 4)",
  "url": "https://www.strobe-statement.org/checklists/",
  "citation": "von Elm E et al. Lancet 2007;370:1453-7",
  "item_count": 22,
  "items": [
    {"number": 1, "section": "Title and abstract", "topic": "Title and abstract",
     "targets": {"default": ["title-and-keywords", "abstract"]},
     "evidence": [{"kind": "term", "any": ["cohort", "case-control", "cross-sectional"]}],
     "question": "Beyond naming the design, does the abstract summarise the study in a balanced way?"}
  ]
}
```

`citation` and `lines` (the paper lines the guideline applies to, e.g. `["review"]`) are optional. `item_count` must equal the number of
items, and items are numbered 1..n in order. An item with no content rule must
have a `question`: presence alone never satisfies an item. `load_guideline`
refuses a file with any problem (`GUIDELINE_INVALID`, every problem listed).

## Predicate vocabulary

| Kind | Fields | Passes when |
| --- | --- | --- |
| `text` (implicit) | the item's `targets` | every target holds text |
| `file` | `path` | the file exists |
| `record` | `path`, optional `pointer` or `field` + `values` | the JSON document (or the JSONL rows) exists and is not empty; with `pointer` (dotted, list indices as digits) the value there is not empty; with `field`/`values` the rows' `field` takes every listed value |
| `declaration` | `name` | paper-writing records that declaration |
| `command` | `script`, `argv`, `expect` | the workspace's `script` (a `.py` under `skills/`), run with `argv` (`{root}` becomes the workspace path), prints a JSON object whose keys equal `expect` (reuses a skill's own validator, e.g. `review_cli.py protocol check`) |
| `number` | `path`, `pointer`, optional `in` | the number the JSON record holds at `pointer` appears in the text (`1,234`, `1{,}234` and `1234` are equal) |
| `term` | `any`, optional `in` | one of the terms appears in the text as whole words, case, accents and dashes folded |

`text`, `file`, `record`, `declaration` and `command` are presence rules;
`number` and `term` are content rules. `in` lists the targets whose text a
content rule reads; it defaults to the item's targets. Paths are relative to
the workspace and never leave it. Anything these predicates cannot decide is
the item's `question`.

## Adding a guideline

1. Find the official checklist and its URL (EQUATOR Network or the
   guideline's own site). Count its numbered items and keep its numbering.
2. Write `guidelines/<id>.json`: one entry per numbered item, a short
   paraphrased `topic` (at most 60 characters), its `section`, its targets and
   the rules that can be decided deterministically. When unsure what an item
   covers, give it only a `question`.
3. Add the guideline's id and item count to
   `test_every_shipped_guideline_validates_with_its_documented_item_count` and
   a test for each content rule (one workspace where it passes, one where it
   fails).

## Copyright rule

Reporting guidelines are copyrighted publications. A data file stores the item
number, a short paraphrased topic, the guideline's URL and citation, and
questions written in our own words. It never stores the item text. Readers
follow the URL for the wording; the validator caps topics at 60 characters and
questions at 200.
