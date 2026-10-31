---
name: journal-finder
description: "Trigger: the paper has a title and an abstract and the operator wants journals worth sending it to, in a quartile range they choose (`/journal-finder Q1-Q2 [--oa-only] [--max-apc <usd>] [--limit N]`). Runs a bounded OpenAlex search for works like the paper (free Crossref, Europe PMC and DOAJ fallbacks when OpenAlex is unavailable), ranks the journals that published them with quartile (SCImago SJR when imported, a labelled OpenAlex proxy, else unknown), open-access state, APC, h-index and a review-time estimate, then reads each shortlisted journal's aims and scope and writes `paper/journal-candidates.md`. Never submits, never contacts an editor, never invents a quartile, impact factor, APC or acceptance rate."
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
/journal-finder Q1-Q2 [--oa-only] [--max-apc <usd>] [--max-review-days N] [--limit N] [--source auto|openalex|crossref] [--include-unknown-quartile]
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
| Contact email | `PAPERSMITH_CONTACT_EMAIL`, optional | requests go out without it; it is never hard-coded (Crossref's polite pool uses it as `mailto`) |
| OpenAlex key | `OPENALEX_API_KEY`, optional but advised | keyless OpenAlex is a small demo allowance; see "Get an OpenAlex key" |
| Semantic Scholar key | `SEMANTIC_SCHOLAR_API_KEY`, optional | Semantic Scholar is not queried at all |

## The flow

1. **Check the ground.** Run `status`; it names the candidates already on disk
   and the SJR file in use. No SJR file means every quartile will be a proxy
   (or unknown when OpenAlex is unavailable), so tell the operator before the
   search, not after.
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
     published", never a guess (a DOAJ price in another currency is in
     `doaj.apc_max` and is never converted).
   - *Quartile and its source*: `sjr` with the year, or `openalex-proxy` stated
     as an approximation, or "quartile unknown" for `quartile_source: "unknown"`
     (never a guess). Never a quartile without its source.
   - *Providers*: the JSON's `providers` and `fallback`, and the candidate's
     `sources`, copied as they are: when `fallback.used` is true the markdown
     opens by saying which sources answered and what is missing.
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
python3 skills/journal-finder/scripts/journal_cli.py search --workspace . --quartiles Q1-Q2 [--oa-only] [--max-apc N] [--max-review-days N] [--limit N] [--source auto|openalex|crossref] [--include-unknown-quartile] [--sjr <csv>] [--out <path>] [--no-cache]
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
`excluded_count`, and by reason in `excluded_reasons` (`record_unavailable`,
`quartile_unknown`, `quartile_range`, `not_oa`, `apc_above_max`,
`review_time_above_max`).

A journal whose quartile is unknown (`quartile: null`, `quartile_source:
"unknown"`: no imported SJR row and no OpenAlex proxy) is excluded by default
and counted in `excluded_reasons.quartile_unknown`; `--include-unknown-quartile`
keeps it, flagged `quartile-unknown`, ignoring the range for it. A note names
`sjr-import` and `OPENALEX_API_KEY` as the two ways to get a quartile.

`paper/journal-candidates.json` is schema 1: `generated_at`, `source`,
`providers`, `fallback`, `query` (`title`, `keywords`, `terms`, `phrases`,
`search_mode`, `facets`, `topics`, `cited`, `fallback`, `scoring`),
`quartiles`, `filters`, `quartile_source_summary`, `sjr` (`file`, `year`, or
null), `candidates`, `excluded_count`, `excluded_reasons`, `notes`,
`api_calls`. Each candidate carries `rank`, `fit_score`, `fit`, `facets`,
`similar_works_count`, `similar_works`, `cited_in_paper_count`, `topics`, `quartile`, `quartile_source`, `sjr` or
`proxy`, `is_oa`, `is_in_doaj`, `apc_usd`, `doaj`, `h_index`,
`mean_citedness_2yr`, `review_time`, `sources` and `flags`.

### Providers and the fallback chain

OpenAlex now asks for a free API key for real use; keyless calls are a small
demo allowance. `--source` chooses the chain:

- **`auto`** (default): OpenAlex first. When it cannot answer (no response, a
  `429` for a spent quota, `401`/`403` key required, a 5xx, a network error, or
  no journal record fetched) the search continues with the fallback chain
  instead of refusing, and says so: `fallback: {used: true, code:
  "openalex-unavailable", reason}` and a note. A bad request or the total
  deadline is still a refusal.
- **`openalex`**: today's behaviour; `NETWORK_UNAVAILABLE` when OpenAlex is
  unavailable.
- **`crossref`**: skips OpenAlex (`fallback.code` is `requested`).

The fallback chain, per signal:

- **Similar works.** Crossref `/works?query=<quoted phrases>&filter=type:journal-article,from-pub-date:<6 years ago>&rows=100`,
  one query per facet, polite pool (`mailto` from `PAPERSMITH_CONTACT_EMAIL`,
  at most three list requests per second; override `PAPERSMITH_CROSSREF_URL`).
  **Europe PMC** (`/search?resultType=core&format=json`, preprints and
  non-article records dropped; override `PAPERSMITH_EUROPEPMC_URL`) is
  queried, and merged into the same aggregate, when the paper looks
  biomedical: a keyword or a phrase of the application facet contains a
  biomedical word (EEG, clinical, disease, neuro..., brain, cancer, ...). The
  method facet and the abstract never trigger it; `query.fallback.europepmc`
  reports `queried`, the `matched` words and the rule. **Semantic Scholar**
  (`/graph/v1/paper/search`, journal venues with an ISSN; override
  `PAPERSMITH_SEMANTICSCHOLAR_URL`) is queried only when
  `SEMANTIC_SCHOLAR_API_KEY` is set, sent in the `x-api-key` header and never
  stored. Works are counted once per DOI (else title and year) however many
  providers or facets found them and aggregated per journal by normalised ISSN
  (any of its numbers; a work carrying two ISSNs joins the two), else by
  normalised container title; journal articles only, up to three examples.
- **Cited venues.** DOIs of `paper/refs.bib` resolve through Crossref
  `/works/<doi>` (container title, ISSN; arXiv DOIs belong to DataCite and are
  not asked); a reference that names a journal matches, by normalised title, a
  journal the search already found. A name never creates a journal.
- **Journal record.** The SJR file when imported (publisher, h-index,
  quartile, categories); **DOAJ** `/api/search/journals/issn:<issn>` (override
  `PAPERSMITH_DOAJ_URL`) for open-access state, APC (`apc.has_apc`, the USD
  price as `apc_usd`, every price in `doaj.apc_max`; a journal DOAJ lists
  without APC has `apc_usd: 0`), review process and subjects; Crossref
  `/journals/<issn>` for the publisher when nobody else named it. A journal
  absent from DOAJ has `is_in_doaj: false`, `is_oa: null`, `apc_usd: null`
  (absence proves nothing about access); when DOAJ itself failed `is_in_doaj`
  is `null`. `--oa-only` therefore drops journals DOAJ does not list.
- **`topic_overlap` without OpenAlex topics.** It compares the content words
  of the paper's keywords and facet phrases with the SJR categories and DOAJ
  subjects of the journal (share of the paper's words they contain, divided by
  the maximum over the journals as usual). `query.scoring.topic_overlap_basis`
  is `"subjects"` here and `"openalex-topics"` on the OpenAlex path. A journal
  with neither source scores 0, and the signal drops out (weights rescaled)
  when it is 0 for every journal. The application gate uses the same overlap
  against the application phrases only.

Transparency. `providers` is `{similar_works: [...], cited_venues: [...],
metadata: [...], quartile: "sjr"|"openalex-proxy"|"unknown"}`, each list in the
order openalex, crossref, europepmc, semanticscholar, sjr, doaj; `quartile` is
`sjr` when any candidate has an SJR quartile, else `openalex-proxy` when any has a
proxy, else `unknown`. Each candidate's `sources` lists the providers that
contributed to it. The agent copies both into the markdown and never claims a
source that did not answer.

**Get an OpenAlex key.** Create a free account at openalex.org, copy the key
from openalex.org/settings/api and `export OPENALEX_API_KEY=...`. A free key
gives about USD 1 per day of usage, 10x the keyless budget. The skill never
asks for the key on the operator's behalf and never prints it.

### How the fit score is built

Three signals, each in 0..1, exposed per candidate as
`fit: {similar_works, cited_in_paper, topic_overlap}` and described in
`query.scoring`:

```
fit_score = 0.45 * similar_works + 0.3 * cited_in_paper + 0.25 * topic_overlap
```

- **`similar_works`**: works like the paper published by the journal, counted
  once per distinct work. The search is OpenAlex `search` with quoted key
  phrases joined by `OR` (`"graph neural networks" OR "few-shot
  learning" OR ...`), limited to journal articles of the last six years.
  Phrases come from the keywords (weight 3, a single-word keyword is
  allowed), the title (weight 2: runs of content words between punctuation and
  function words, at most four words each; hyphenated compounds such as
  *self-supervised* stay whole) and the abstract's bigrams that occur at least
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
`pubmed`, `europepmc`, `doaj`, `semanticscholar`), whether the cache was on and where, and the OpenAlex budget:
`budget.state` is `ok` (the answers carried `x-ratelimit-remaining-usd`),
`exhausted` (a request was refused for a spent quota) or `unknown`, with
`remaining_usd`, `limit_usd` and `retry_after_seconds` when known. A retry
counts as a call made.

OpenAlex's keyless budget is a demo allowance (USD 0.10 per day, shared by
everyone behind one IP address; a free key raises it to USD 1 per day), and
one journal search spends roughly USD 0.01 to 0.04 of it, depending on how
many candidates need the proxy's count queries: a handful of searches a day
without a key, a few dozen with one. Successful answers are therefore kept in
`~/.cache/papersmith/journal-finder/http/` (override with
`PAPERSMITH_JOURNAL_CACHE_DIR`), keyed by the request without credentials
or contact email (the Semantic Scholar key is a header and never part of it),
for every service: a search lives one day, any other lookup seven. Errors are
never stored, an unreadable or unwritable cache is just a miss, and
`--no-cache` neither reads nor writes it. Review-time lookups carry the
current date in their request, so they are reused on the same day only.

A `429` that asks for a wait of more than 60 seconds is a spent quota, not a
burst: the CLI does not retry it. If it happens on the first search the
refusal with `--source openalex` is `NETWORK_UNAVAILABLE` and its message names
the wait and `OPENALEX_API_KEY`; with the default `auto` the search continues
with the fallback chain and a note says how to get the key. A free key has its
own daily budget and is sent only when that variable is set. Later in a search it degrades that step with a note and
`budget.state` reads `exhausted`. The agent tells the operator which of the
two happened and never retries in a loop.

### Where the quartile comes from

- **`sjr`**: the SCImago file the operator imported, matched by any ISSN
  (hyphens ignored, never by title). The best quartile decides the range
  filter; the per-category quartiles and the SJR value ride along.
- **`unknown`**: no SJR row and no OpenAlex proxy (OpenAlex unavailable, or it
  has no citedness for the journal). `quartile` is `null`; see
  `--include-unknown-quartile`.
- **`openalex-proxy`**: used when no SJR file is imported or the journal is
  not in it, and OpenAlex answered. It is the share of OpenAlex core journals of the same field with
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
| `NETWORK_UNAVAILABLE` | `--source openalex`: OpenAlex cannot be reached within the bounded retries and deadline, or its daily quota is spent (the message gives the wait and names `OPENALEX_API_KEY`); `auto`/`crossref`: the fallback providers could not be reached either; the total deadline passed | report it and point to the OpenAlex key guide; never fall back to remembered journals |
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
| No SJR file imported | Say so before searching: every quartile will be `openalex-proxy` (or `unknown` with the fallback chain); offer the download link |
| `fallback.used` is true | Say which sources answered (`providers`), that the quartile may be unknown and that `mean_citedness_2yr` is absent; show the OpenAlex key guide; never present fallback output as OpenAlex |
| `excluded_reasons.quartile_unknown` > 0 | Tell the operator the count and offer `--include-unknown-quartile`, `sjr-import` or an `OPENALEX_API_KEY` |
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
