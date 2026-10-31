---
name: journal-finder
description: "Trigger: the paper has a title and an abstract and the operator wants journals worth sending it to, in a quartile range they choose (`/journal-finder Q1-Q2 [--oa-only] [--max-apc <usd>] [--limit N]`). Runs a bounded OpenAlex search for works like the paper, ranks the journals that published them with quartile (SCImago SJR when imported, a labelled OpenAlex proxy otherwise), open-access state, APC, h-index and a review-time estimate, then reads each shortlisted journal's aims and scope and writes `paper/journal-candidates.md`. Never submits, never contacts an editor, never invents a quartile, impact factor, APC or acceptance rate."
---

# Journal finder

A paper is ready to leave the lab when its text is settled; where it goes is a
separate decision, and it deserves evidence rather than a hunch. This skill
turns the paper's own title, abstract and keywords into a ranked shortlist of
journals that already publish work like it, then reads what those journals say
about their own scope and writes the case for each one. Nothing here is ever
submitted, and no editor is contacted.

## Usage

```
/journal-finder Q1-Q2 [--oa-only] [--max-apc <usd>] [--max-review-days N] [--limit N]
```

The quartile argument is a single quartile (`Q1`) or an ascending contiguous
range (`Q2-Q3`, `Q1-Q4`), case-insensitive. The default `--limit` is 15, the
maximum 50.

## Inputs

| Input | Where it comes from | If it is missing |
| --- | --- | --- |
| Title, abstract, keywords | `paper/main.tex` (`\title`, the `abstract` environment, `\keywords`, a `keyword` or `IEEEkeywords` block or a `Keywords:` line); else the title and abstract files under `paper/sections/` | `PAPER_ABSENT`: write the title and the abstract first |
| Quartile range | the argument of `/journal-finder` | `QUARTILE_RANGE_INVALID` |
| SJR file | `~/.cache/papersmith/sjr/scimagojr-<year>.csv`, imported once with `sjr-import` (or the dashboard's upload) | not an error: the quartile becomes the `openalex-proxy` approximation, labelled as such |
| Contact email | `PAPERSMITH_CONTACT_EMAIL`, optional | requests go out without it; it is never hard-coded |

## The flow

1. **Check the ground.** Run `status`; it names the candidates already on disk
   and the SJR file in use. No SJR file means every quartile will be a proxy,
   so tell the operator before the search, not after.
2. **Search.** Run the CLI. It writes `paper/journal-candidates.json` and
   prints the same object.
3. **Read each shortlisted journal's aims and scope** from its own website
   (`homepage_url`, then the "aims and scope" or "about the journal" page),
   with the web tools. A page that cannot be reached is reported as unread;
   the journal is never described from memory.
4. **Write `paper/journal-candidates.md`**, one section per journal, in the
   CLI's rank order, each holding:
   - *Why it fits*: a sentence quoted from the paper beside a sentence quoted
     from the journal's scope, and the similar works the CLI found
     (title, year, DOI) as the evidence of fit.
   - *Scope risks*: what the scope page excludes or emphasises that the paper
     does not match.
   - *OA and APC*: copied from the JSON; `apc_usd: null` reads "APC not
     published in OpenAlex", never a guess.
   - *Quartile and its source*: `sjr` with the year, or `openalex-proxy` stated
     as an approximation. Never one without the other.
   - *Review time*: the computed estimate with `n` and its source. A
     time-to-first-decision the journal itself declares may be added only with
     the page URL, labelled "declared by the journal", beside the computed
     estimate, never in place of it.
5. **Stop.** The operator chooses; the skill never writes to a journal.

The CLI's numbers (rank, fit score, quartile, APC, h-index, review time) are
the CLI's. The markdown explains them; it never edits, reorders or rounds them
into a different story.

## The CLI

Run from the workspace root. One JSON object on stdout per call; a refusal is
`{"ok": false, "error": CODE, "message": ...}` with exit 2 and nothing written.

```
python3 skills/journal-finder/scripts/journal_cli.py search --workspace . --quartiles Q1-Q2 [--oa-only] [--max-apc N] [--max-review-days N] [--limit N] [--sjr <csv>] [--out <path>]
python3 skills/journal-finder/scripts/journal_cli.py sjr-import --file <path> [--year YYYY]
python3 skills/journal-finder/scripts/journal_cli.py status --workspace .
```

`search` reads the paper, asks OpenAlex for works like it, keeps the journals
those works appeared in and aggregates per journal: how many similar works,
and up to three examples. It then fetches each journal's record (publisher,
OA and DOAJ state, APC, h-index, 2-year mean citedness, main field). The fit
score is the journal's similar-works count over the largest count the search
found, so the best-represented journal scores 1.0. OpenAlex requires every
search term in the full text, so the paper's top terms are tried six at a time
and the lowest-weighted one is dropped until at least 50 works match; the
terms actually used are `query.terms` and each dropped term is named in
`notes`.

`--oa-only` keeps fully open-access journals. `--max-apc N` drops journals
whose published APC is above N USD and keeps those with no published APC,
flagged `apc-unknown`. `--max-review-days N` drops journals whose median
review time is above N days and keeps those without data, flagged
`review-time-unknown`. Journals dropped by any filter are counted in
`excluded_count`.

`paper/journal-candidates.json` is schema 1: `generated_at`, `query`
(`title`, `keywords`, `terms`), `quartiles`, `filters`,
`quartile_source_summary`, `sjr` (`file`, `year`, or null), `candidates`,
`excluded_count`, `notes`. Each candidate carries `rank`, `fit_score`,
`similar_works_count`, `similar_works`, `quartile`, `quartile_source`, `sjr`
or `proxy`, `is_oa`, `is_in_doaj`, `apc_usd`, `h_index`,
`mean_citedness_2yr`, `review_time` and `flags`.

### Where the quartile comes from

- **`sjr`**: the SCImago file the operator imported, matched by any ISSN
  (hyphens ignored, never by title). The best quartile decides the range
  filter; the per-category quartiles and the SJR value ride along.
- **`openalex-proxy`**: used when no SJR file is imported or the journal is
  not in it. It is the share of OpenAlex core journals of the same field with
  a higher 2-year mean citedness: under 25% above is Q1, under 50% Q2, under
  75% Q3, else Q4. It approximates a citation percentile and is **not** an SJR
  quartile; every place that shows it says so.

scimagojr.com sits behind a browser challenge, so this skill never scrapes it.
The operator downloads the CSV once from
https://www.scimagojr.com/journalrank.php ("Download data") and runs
`sjr-import`. The latest imported year is used, and a file older than two
years adds a note to the output.

### Review-time estimate

Each candidate carries `review_time`: the median and quartiles of the days
between `received` and `accepted` over the journal's latest 40 research
articles of the last three years, with `accept_to_online_median_days` when
the source dates the online publication. The chain is Crossref assertions
first (deposited by Springer Nature and others), then PubMed `esummary`
history (NCBI etiquette: `tool=papersmith`, the contact email and
`NCBI_API_KEY` when set, at most three requests per second), then
`source: "none"`. Fewer than five dated articles also reads as `none`, with
`n` kept. It estimates submission-to-acceptance and includes revision rounds;
it is **not** the time to first decision, and the markdown says so.

## Refusals

| Code | When | What the agent does |
| --- | --- | --- |
| `QUARTILE_RANGE_INVALID` | the range is not `Q1`, `Q2-Q3`, `Q1-Q4`... ascending and contiguous | ask for a valid range; never guess one |
| `PAPER_ABSENT` | no title and no abstract can be read | send the operator to write them; never search on a topic they typed instead |
| `NETWORK_UNAVAILABLE` | OpenAlex cannot be reached within the bounded retries and deadline | report it; never fall back to remembered journals |
| `SJR_FILE_INVALID` | the CSV lacks `Title`, `Issn`, `SJR`, `SJR Best Quartile`, `Categories` or `Publisher`, is empty, or has no year | say which column is missing and point to the download page |
| `FILTER_INVALID` | `--limit`, `--max-apc` or `--max-review-days` is not a valid number | correct the flag |
| `WORKSPACE_ABSENT` | `--workspace` is not a directory | fix the path |
| `CANDIDATES_UNREADABLE` | `status` found a `journal-candidates.json` that is not valid | re-run `search`; never repair it by hand |
| `USAGE` | a flag or verb the CLI does not know | read the usage above |
| `INTERNAL_ERROR` | the CLI hit a bug (exit 1) | quote the message to the operator; do not retry in a loop |

A refusal writes nothing. A review-time step that fails never fails the
search: that journal reads `source: "none"` and `notes` says why.

## What this skill never does

- It never submits a manuscript, fills a submission form or contacts an editor.
- It never invents a quartile, an impact factor, an APC or an acceptance rate.
  A figure the CLI did not print and a page the agent did not read are not
  facts. No impact factor is reported at all: none of the sources here
  publishes it.
- It never presents the proxy as SJR. `openalex-proxy` travels with every
  proxy quartile, in the JSON and in the markdown.
- It never changes the ranking numbers the CLI produced, and never hand-edits
  `paper/journal-candidates.json`.
- It never scrapes scimagojr.com or any page that answers with a browser
  challenge.
- It never edits the paper, its blocks or its template. Adapting a manuscript
  to a chosen journal is another skill's job.
- It never hard-codes or sends the operator's email beyond the polite contact
  fields the services ask for, and only when `PAPERSMITH_CONTACT_EMAIL` is set.

## Decision gates

| Situation | Action |
| --- | --- |
| No SJR file imported | Say so before searching: every quartile will be `openalex-proxy`; offer the download link |
| Fewer journals than `--limit` | Report the short list and the notes; never pad it from memory |
| A journal's scope page cannot be read | Mark it "scope page unread" and keep its numbers; never paraphrase a page not read |
| The scope contradicts the paper | Say so under *Scope risks*; the rank does not change |
| `review_time.source` is `none` | Write "no public data"; never estimate from the publisher's reputation |
| The operator asks for a quartile the data cannot support | Refuse the claim, offer the proxy label or the SJR import |

## Measure before you assert

Quote the paper from the file in the same pass, and quote the journal from the
page fetched in the same pass. A fit argument built on a scope page read last
week, or on a journal remembered from training, sounds like a finding and gets
acted on like one.
