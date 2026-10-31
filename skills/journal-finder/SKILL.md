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
     from the journal's scope, the similar works the CLI found (title, year,
     DOI) and the `fit` components (similar works, references of the paper
     published there, shared topics) as the evidence of fit.
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
python3 skills/journal-finder/scripts/journal_cli.py search --workspace . --quartiles Q1-Q2 [--oa-only] [--max-apc N] [--max-review-days N] [--limit N] [--sjr <csv>] [--out <path>] [--no-cache]
python3 skills/journal-finder/scripts/journal_cli.py sjr-import --file <path> [--year YYYY]
python3 skills/journal-finder/scripts/journal_cli.py status --workspace .
```

`search` reads the paper, asks OpenAlex for works like it, keeps the journals
those works appeared in and aggregates per journal: how many similar works,
and up to three examples. It also resolves the journals the paper already
cites and reads the OpenAlex topics of the matched and the cited works. It
then fetches each journal's record (publisher, OA and DOAJ state, APC,
h-index, 2-year mean citedness, main field, main topics) and combines the
three signals into the fit score (next section). The journals fetched are the
top 30 to 60 by similar-works count plus up to 20 cited ones, so a journal the
paper cites stays in the list even when no similar work was published there.

`--oa-only` keeps fully open-access journals. `--max-apc N` drops journals
whose published APC is above N USD and keeps those with no published APC,
flagged `apc-unknown`. `--max-review-days N` drops journals whose median
review time is above N days and keeps those without data, flagged
`review-time-unknown`. Journals dropped by any filter are counted in
`excluded_count`.

`paper/journal-candidates.json` is schema 1: `generated_at`, `query`
(`title`, `keywords`, `terms`, `phrases`, `search_mode`, `facets`, `topics`,
`cited`, `scoring`), `quartiles`, `filters`, `quartile_source_summary`, `sjr`
(`file`, `year`, or null), `candidates`, `excluded_count`, `notes`,
`api_calls`. Each candidate carries `rank`, `fit_score`, `fit`, `facets`,
`similar_works_count`, `similar_works`, `cited_in_paper_count`, `topics`, `quartile`, `quartile_source`, `sjr` or
`proxy`, `is_oa`, `is_in_doaj`, `apc_usd`, `h_index`, `mean_citedness_2yr`,
`review_time` and `flags`.

### How the fit score is built

Three signals, each in 0..1, exposed per candidate as
`fit: {similar_works, cited_in_paper, topic_overlap}` and described in
`query.scoring`:

```
fit_score = 0.45 * similar_works + 0.3 * cited_in_paper + 0.25 * topic_overlap
```

- **`similar_works`**: works like the paper published by the journal, counted
  once per distinct work. The search is OpenAlex `search` with quoted key
  phrases joined by `OR` (`"data re-uploading" OR "variational quantum
  circuits" OR ...`), limited to journal articles of the last six years.
  Phrases come from the keywords (weight 3, a single-word keyword is
  allowed), the title (weight 2: runs of content words between punctuation and
  function words, at most four words each; hyphenated compounds such as
  *re-uploading* stay whole) and the abstract's bigrams that occur at least
  twice and share a word with a keyword or title phrase; a phrase inside a
  longer keyword or title phrase is dropped (only a longer keyword absorbs a
  keyword), and so is a title phrase that contains a multi-word keyword.
  OpenAlex ranks by relevance, so works matching several phrases come first.
  When the OR query for a facet matches fewer than 50 works, that query is
  dropped with a note; when none is left, or the paper yields no phrase, the
  CLI falls back to the AND relaxation of single terms (`query.terms`,
  `search_mode: "terms-and-relaxation"`, each dropped term named in `notes`),
  because OpenAlex's plain `search` requires every term. `query.phrases` lists
  the phrases queried and `query.search_mode` is `"phrases-or"` otherwise.

  **Facets.** A paper that applies a method to a domain must not be ranked
  by the method alone. The application is the title's tail after its first
  ` for `, ` applied to `, ` towards ` or ` toward `
  (`query.facets.tail`); a phrase belongs to the application facet when it
  shares a word with that tail, or comes from a keyword that does
  ("Electroencephalography (EEG)" follows its acronym), and to the method
  facet otherwise. With both facets present each gets its own OR query and at
  most five phrases, so neither takes more than half the query, and half of
  the 200-work reading budget (`query.facets.queries` reports phrases, works
  matched and works read per facet). Each candidate reports the distinct
  works each facet found as `facets.method` and `facets.application`. When
  both facets were searched, a journal none of whose similar works matched an
  application phrase and whose topics overlap the application works' topics
  by less than 0.05 (`facets.application_topic_overlap`) has its `fit_score`
  multiplied by 0.5 (`facets.gate`, `query.scoring.facet_gate`) and carries the
  flag `no-application-evidence`: it still appears, and the agent says why it
  is lower. A title without such a marker has one facet and no gate.
- **`cited_in_paper`**: how many of the paper's references appeared in the
  journal. The CLI reads `paper/refs.bib` (any `paper/*.bib` when that file is
  absent) and resolves DOIs, and arXiv ids as `10.48550/arxiv.<id>`, through
  `/works?filter=doi:a|b|c` in batches of at most 50 (at most 4 batches). A
  reference with no DOI that names a journal is looked up by exact normalised
  journal name (at most 15 lookups, the exact name among the first 25 matches); preprint servers and datasets are never
  looked up. Only journal-hosted works count. `query.cited` reports the
  entries, how many resolved by DOI or by name, how many did not, and the
  most-cited journals; each candidate carries `cited_in_paper_count`.
- **`topic_overlap`**: the paper's OpenAlex topic distribution (the topics of
  the matched works of each facet, blended with those of the cited works when
  there are any, every part weighing the same; `query.topics`) against the journal's own topic distribution
  (`topics[].count` normalised), as a histogram intersection. Each candidate
  lists its main `topics`.

Each component is divided by its maximum over the journals evaluated, so the
best journal on a signal scores 1.0 on it. A component that is zero for every
journal (no bibliography, no topics returned) drops out and the remaining
weights are rescaled to sum to 1; `query.scoring.active` names the components
in force and `query.scoring.weights` the effective weights. The same numbers
rebuild every `fit_score` that carries no gate:
`round(sum(weights[k] * fit[k]), 4)`; a gated one is that value times 0.5.

A failing cited-venue lookup never fails the search: the signal degrades and
`notes` says why. The agent reports the components when it explains a rank and
never presents a journal that appears only through a citation as one that
publishes similar work.

### Calls, the cache and the OpenAlex budget

`api_calls` reports how many HTTP requests the search made and how many it
served from disk, in total and per service (`openalex`, `crossref`,
`pubmed`), whether the cache was on and where, and the OpenAlex budget:
`budget.state` is `ok` (the answers carried `x-ratelimit-remaining-usd`),
`exhausted` (a request was refused for a spent quota) or `unknown`, with
`remaining_usd`, `limit_usd` and `retry_after_seconds` when known. A retry
counts as a call made.

OpenAlex's keyless budget is small (USD 0.10 per day, shared by everyone
behind one IP address, roughly a hundred searches) and one search spends a
noticeable part of it. Successful answers are therefore kept in
`~/.cache/papersmith/journal-finder/http/` (override with
`PAPERSMITH_JOURNAL_CACHE_DIR`), keyed by the request without credentials
or contact email: a search lives one day, any other lookup seven. Errors are
never stored, an unreadable or unwritable cache is just a miss, and
`--no-cache` neither reads nor writes it. Review-time lookups carry the
current date in their request, so they are reused on the same day only.

A `429` that asks for a wait of more than 60 seconds is a spent quota, not a
burst: the CLI does not retry it. If it happens on the first search the
refusal is `NETWORK_UNAVAILABLE` and its message names the wait and
`OPENALEX_API_KEY`; a free key has its own daily budget and is sent only when
that variable is set. Later in a search it degrades that step with a note and
`budget.state` reads `exhausted`. The agent tells the operator which of the
two happened and never retries in a loop.

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
| `NETWORK_UNAVAILABLE` | OpenAlex cannot be reached within the bounded retries and deadline, or its daily quota is spent (the message gives the wait and names `OPENALEX_API_KEY`) | report it; never fall back to remembered journals |
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
