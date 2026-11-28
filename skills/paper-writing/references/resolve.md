## No claim without a source that holds it: `resolve`

Search comes first, always — but search itself runs through the agent's own
MCP (the `discovery` role; each harness registers its servers in `.mcp.json`,
`opencode.json`, `.pi/mcp.json` or `.agents/mcp_config.json`), never through
this CLI. A connector that needs a key, such as `asta`, is searched only when
`smith keys status <connector> --json` reports `"source": "env"`; what it
generates — a summary, a snippet — points at a paper and is never evidence. `resolve` is the
CLI-side half: given an identifier and a named connector (or `auto`: the
role's connectors in their configured order), it fetches metadata over stdlib
`urllib`, keyless by default, and caches the result on disk keyed by its own
digest.

```bash
.venv/bin/python skills/paper-writing/scripts/paper_cli.py resolve \
    --identifier 10.1000/example --resolver openalex --role resolution
```

| Verb | What it does | Refuses |
| --- | --- | --- |
| `resolve --identifier <id> --resolver {openalex,crossref,arxiv,semantic-scholar,asta,auto} [--role <role>] [--paper <dir> \| --cache-dir <dir>]` | Resolves one identifier's metadata through one named connector, or with `auto` through the role's connectors in order (the first whole record with an abstract, reported with its `attempts`), and caches it: under `<paper>/.paper-writing/metadata/` by default, or as `<dir>/<metadata_digest>.json` with `--cache-dir` | `PAPER_OUTSIDE_REPOSITORY`, `PAPERSMITH_CONFIG_UNREADABLE`, `UNKNOWN_ROLE`, `DISCOVERY_UNAVAILABLE`, `RESOLVER_ROLE_EMPTY`, `RESOLVER_UNREACHABLE`, `RESOLVER_REFUSED`, `IDENTIFIER_UNRESOLVED` |

| `resolve --references [--force] [--role <role>] [--paper <dir>]` | Resolves every key `main.tex` cites, or every `refs.bib` entry when the manuscript's citation commands are not ones `bib` reads, into `paper/.paper-writing/references.json`; prints how many were `resolved`, `not_found`, `unreachable`, `reused` and `with_abstract` | `PAPER_OUTSIDE_REPOSITORY`, `PAPER_ABSENT`, `PAPERSMITH_CONFIG_UNREADABLE`, `UNKNOWN_ROLE`, `RESOLVER_ROLE_EMPTY` |

**`resolve --references` keeps what the paper cites beside `refs.bib`.** Run it
after the citations change, because `bib build` rewrites `refs.bib` and carries
no abstract. Then run `smith atlas coverage .`: a cited key the SOTA
constellation draws only as a placeholder (no system of its own) goes to the
`sota-scout` agent, which adds it to `sota-pool/candidates.json` with the
abstract `resolve --references` stored, and to the `sota-grapher` agent, which
draws it. A key's identifiers ask the `resolution` role's connectors in its
configured order, each record kept whole from one connector: the first with an
abstract, else the first that found the work. Crossref never returns an
abstract, so it is asked last and only for a work no other connector holds; an
arXiv id asks Asta (with its key) and arXiv; and while no abstract was found, a
title search (Asta's, then OpenAlex's) is accepted only on an exact normalized
title (a near title is `not_found`). Ai2's Asta is asked only once its key is
set: without the key, a role naming it behaves exactly as without it. A
connector that refuses the operator's key, or a keyed one that fails, is set
aside for the rest of the run and listed in the summary's `connectors_down`. Each record is `{status, resolver, identifier, title,
abstract, year, venue, link, digest, retrieved}`, with `status` one of `resolved`,
`not_found` or `unreachable`, and the keys are sorted. A rerun reuses `resolved`
records and asks again for the rest; `--force` asks again for all of them, and a
failure never replaces a `resolved` record. Requests pause between each other, and
after three consecutive unreachable keys the rest are recorded without asking. An
identifier in the bib is trusted as it stands: only a title search compares titles.
That title search confirms a paper the manuscript already cites, and never
discovers one: finding new papers stays with the agent's MCP.
The dashboard's cited-papers view reads the sidecar last, after the bib and the
SOTA pool, and `verify`'s `references` check reads it. The manuscript graph does
not, so it changes no layer's staleness.

**`--cache-dir` is for callers that are not writing a paper.** `bib` and
`full_text` look a resolution up only under `paper/.paper-writing/metadata/`,
so paper-writing's own calls pass nothing. The plausibility agents borrow
`resolve` before any paper exists and pass `--cache-dir sota-pool/metadata`,
which keeps their caches beside the pool and leaves `paper/` untouched. The
two flags are one choice: passing both is a usage error. A directory outside
the repository refuses `PAPER_OUTSIDE_REPOSITORY` before any request.

**Every role can be emptied in `papersmith.yaml`.** An empty `resolution`
role refuses `RESOLVER_ROLE_EMPTY` rather than silently resolving nothing,
and so does asking a keyed connector (Asta) whose key is not set;
an unreachable connector refuses `RESOLVER_UNREACHABLE` with a non-zero
exit, never a silent empty result, and a service that refuses the operator's
configured key refuses `RESOLVER_REFUSED` — never `IDENTIFIER_UNRESOLVED`,
because the paper was never looked up.

**The `papersmith.yaml` reader fails closed.** `paper_resolve.parse_yaml_subset` reads nested
mappings, scalars, block lists of scalars and block lists of mappings (an `authors:` list of
`- name: ...` items with nested `email:`/`orcid:` keys becomes a list of dicts), and keys after
such a list (`paper_writing.roles`) are kept. Any line it cannot place -- a deeper indentation
it does not own, a list item where a key belongs -- refuses `PAPERSMITH_CONFIG_UNREADABLE`
naming that line, never a partial read that later surfaces as `RESOLVER_ROLE_EMPTY`.

**Asta's records.** Ai2's Asta answers with the Semantic Scholar corpus: the
record's abstract is the paper's own (never the model-written `tldr`, and never
markup stripped into text), and its `full_text_url` is always `null` — Asta is
not a full-text connector. Ai2's terms ask that work done with Asta acknowledge
it: `verify`'s `references` check lists the cited keys resolved through Asta and
adds a note, never a failure. `contact` (a courtesy `mailto` for
OpenAlex's polite pool) is read from `papersmith.yaml`, never hardcoded, and
is never a secret — leaving it empty just means requests go out without it.

**No verdict lives in this CLI.** Whether a source's text actually supports
a claim is a judgment the agent makes by reading a located span
(`EvidenceSpan.locate`, `paper_evidence.py`) — this module only ever proves
a span is real, byte for byte; it never decides what the span means.

`bib build` rebuilds `paper/refs.bib` WHOLE, sorted, exclusively from
cached resolved metadata — never appended, never hand-typed:

```bash
.venv/bin/python skills/paper-writing/scripts/paper_cli.py bib build
```

| Verb | What it does | Refuses |
| --- | --- | --- |
| `bib build [--guidance <dir>]` | Rebuilds `refs.bib` from the cached, resolved AND ingested evidence records of the keys `main.tex` cites; a key dropped from the text leaves the bibliography while its records stay in the append-only store; checks both `\cite{}`/entry directions; a cited entry already in `refs.bib` with no evidence record refuses `ENTRY_UNSOURCED` before writing, leaving the file byte for byte | `ENTRY_UNSOURCED`, `ENTRY_NOT_INGESTED`, `CITE_WITHOUT_ENTRY` |
| `bib refresh --cite-key <key> --metadata-digest <digest> [--resolver <r>] [--guidance <dir>]` | Relinks the record `bib build` reads for `<key>` to fresher cached metadata of the same work: appends one copy changing only `resolver` and `metadata_digest` | `ENTRY_UNSOURCED`, `ENTRY_NOT_INGESTED` |

**`bib build` prefers the published record and normalizes what connectors send.** An entry whose metadata is the arXiv preprint (venue `arXiv`/`CoRR`, or a `10.48550/` DOI) takes the venue, year and DOI of a published record of the same normalized title already on disk: first the key's `resolved` record in `.paper-writing/references.json`, then any cached resolution under `.paper-writing/metadata/`. Authors and title stay the evidence record's own, and a `% published record: <provenance>` comment rides above the entry. With no such record it stays arXiv and the verb's JSON names the key under `warnings`; nothing is fetched, so offline it warns and never fails. HTML character references (`&amp;`, `&amp;amp;`, `&lt;`, `&#38;`) are decoded until none remain, then LaTeX-escaped once, so the rebuild is idempotent. Entry types follow the venue: none is `@misc`; a data-repository DOI (Zenodo, figshare, Dryad, Dataverse, PhysioNet, OpenNeuro, Mendeley Data, UCI) whose venue is not a journal or proceedings is `@misc` with `howpublished`; a proceedings venue (proceedings, conference, workshop, PMLR, NeurIPS, ICML, ICLR, ...) is `@inproceedings` with `booktitle`; anything else, including *Proceedings of the IEEE*, PNAS and *Proc. R. Soc.*, is `@article` with `journal`. Entries no rule touches are written byte for byte as before.

**The SOTA atlas follows the citations.** When the workspace holding
`paper/` also holds `sota-pool/atlas.json`, a `bib build` (or a `bib
refresh` that leaves both `\cite{}`/entry directions clean), a `verify` whose
`citations` check passes, and a successful dashboard compile each rebuild
`sota-pool/atlas.manuscript.json` (`skills/_core/command_center/atlas_manuscript.py`):
every atlas system marked cited or not, with the blocks and claims that cite it,
plus the cited papers absent from the pool. `atlas.json` is never modified. The
result rides in the verb's JSON under `atlas_manuscript`; a builder error is a
`warning` there and never changes the verb's status or exit code. Without an
atlas the output is unchanged. On demand: `smith atlas cited`.

**The compiled manuscript gets a visual QA pass.** A successful dashboard
compile (and `smith paper qa [--json] [<dir>]` on demand) runs
`skills/_core/figure/manuscript_qa.py` over `paper/main.pdf`: the text block of
each page is inferred from its body lines (running headers, footers and page
numbers set apart), and any text span, image, figure or drawn path passing it by
more than 1 pt is an `overflow` finding; text inside a figure placement or a
ruled table region printing outside [0.70, 0.90] × body is
`figure-font`/`table-font`, each naming its `bound` (`floor` or `cap`); each
`Overfull \hbox` of `main.log` is `overfull`, with its source lines and page. It
writes `paper/.qa/qa.json` (with the sha256 of the `main.pdf` it measured, so
staleness is detectable) and 100 dpi page images under `paper/.qa/pages/`; the
dashboard's PDF preview tab lists the findings with page thumbnails
(`GET /api/paper/qa`), and `smith audit` prints the stored count and staleness.
A QA error is a `warning` under `manuscript_qa` and never fails the compile.
**Length budget (both lines).** A manuscript runs at most 45 pages in Elsevier's submission layout (elsarticle `preprint,12pt`, one column), references included, or 25 in its two-column layout (`5p`). The canonical review-mode manuscript is not Elsevier-sized, so the QA pass estimates Elsevier pages from `main.tex`: 1 front-matter page + prose words / 450 + 0.5 per figure or table + unique cited references / 14 (`page_budget` in `qa.json`; a compiled elsarticle is measured against its own layout instead). Past the limit it reports a `page-budget` finding and a warning line in the PDF tab. Plan for it while drafting: about 11,000 words of body for a review at 200 references and 8 floats, about 13,000 for an experimental paper at 40 references and 12 floats; shorten the prose, merge floats, or cut references to the most relevant when it runs over. Every `tabular` of two columns or fewer, or two rows or fewer, is a `table-shape` finding: a bar or pie chart, or the sentence, carries those values better.
**Why not Playwright:** it renders HTML, not PDFs, so it cannot see where
pdfTeX placed a glyph; the check reads the PDF itself (pypdfium2 geometry,
poppler rasters). Playwright stays for the dashboard UI (`ui/e2e`).

**The manuscript summary graph follows the same events.** In a workspace
(`papersmith.yaml` present) the same `bib build`/`bib refresh`, `verify` and
compile also rebuild `.papersmith/manuscript_graph.json`
(`skills/_core/command_center/manuscript_graph.py`): topic, problem and pillars,
hypotheses, the cited SOTA, the base mathematics
(`materials-and-methods.mm-borrowed-machinery`) apart from the novelty
mathematics (`materials-and-methods.mm-proposal`), experiments, findings and the
first sentence of each `conclusions.concl-block-*`, each node naming its source
and blocks, and a missing source marked `missing` with the phase that fills it.
It rides under `manuscript_graph` with the same warning-only rule. So the graph
reads well, keep each displayed equation `\label`ed and reference the borrowed
equation the proposal builds on with `\eqref`. On demand: `smith atlas summary`.

**`bib refresh` relinks metadata; it never judges support.** After a
re-`resolve` caches better metadata (a year, a venue) for a DOI or arXiv id
already cited, `bib refresh` points the citation at it without re-quoting
the source:

```bash
.venv/bin/python skills/paper-writing/scripts/paper_cli.py bib refresh \
  --cite-key smith2024 --metadata-digest <digest printed by resolve>
```

It selects the same last-write-wins record `bib build` reads, and appends a
copy to that record's own block store whose claim, quote, span, verdict,
round, block and identifier are byte-identical; only `resolver` (taken from
the new cache; `--resolver`, when given, must equal it) and
`metadata_digest` change. Prior lines are never edited and no
`.papersmith-evidence.json` manifest is written. Because nothing is
re-judged, the source's `guidance/` class is not re-checked — that is the
point for a source judged before its folder became `style-reference` — while
`validate` still refuses any NEW quote from such a folder. Every check runs
before the one write. It refuses `ENTRY_UNSOURCED` when no record carries
the key, when either the current or the new cache is missing or not filed
under its own digest, when `--resolver` disagrees, when the record and both
caches do not name the same work, or when the record does not end the last
store holding the key (an appended copy would not supersede it); and
`ENTRY_NOT_INGESTED` when the record has no located `holds`/`does-not-hold`
span or its `source_md` is no longer an ingested paper. "The same work" is
one normalized identifier: a DOI compares without its `https://doi.org/` or
`doi:` prefix and case-insensitively; an arXiv id compares without its
`arXiv:` prefix, `arxiv.org/abs|pdf/` URL or `.pdf` suffix but WITH its
version, so `2401.00001v2` never matches `2401.00001`, and a DOI never
matches an arXiv id. Refreshing to the digest already recorded writes
nothing and reports `"refreshed": false`.

A hand-typed entry (no `resolver`/`metadata_digest` provenance) refuses
`ENTRY_UNSOURCED` before a single byte of `refs.bib` is rewritten — checked
entirely offline, since the provenance is either cached already or it is not.

**Resolved is not ingested.** `no-citation-before-its-paper-is-ingested`
(item 2) adds a second, independent requirement: a citation's cached
metadata may not reach `refs.bib` until the paper it cites has actually
been ingested — a DOI can resolve against OpenAlex while the PDF itself
still sits unread. `entry_from_record` checks both, and a record that
resolved but was never ingested refuses `ENTRY_NOT_INGESTED` by name,
naming the record's own cite key. **The match is never a guess**: a
resolved DOI/arXiv id and a `guidance/<root>/<paper>/` folder name have no
free correspondence, and pairing them by similarity risks silently citing
the wrong paper's metadata against the right paper's text. Instead this
reuses the one link that is already exact — `record["source_md"]`, the
literal path `EvidenceSpan.locate` verified a real quote against when
`validate --quote ... --source-md ...` built the evidence record — and
confirms that path still resolves to a real `guidance/<root>/<paper>/
<paper>.md` (`paper_guidance.is_ingested_source`, the same two-level shape
`ingested_papers` walks). A record whose evidence span was never located
(`insufficient`, or hand-built with no `source_md`) carries no such link
and refuses the same way.

`validate` is the single gate: submit one judged verdict for one claim
(the agent's own reading of a located span decides `holds` vs
`does-not-hold`; omitting `--quote`/`--source-md` records `insufficient`),
then check the block's round-bounded satisfaction, and write only when
every claim the block has evidence for holds:

```bash
.venv/bin/python skills/paper-writing/scripts/paper_cli.py validate \
    --block intro.claim --claim "the dataset holds 12000 labeled examples" \
    --quote "holds 12,000 labeled examples" --source-md guidance/06-introduction/paper1.md \
    --verdict holds --cite-key smith2024 --body body.tex
```

| Verb | What it does | Refuses |
| --- | --- | --- |
| `validate --block <id> [--claim ... --quote ... --source-md ... --verdict holds\|does-not-hold] [--body <path\|->] [--sentence <json>] [--regime <r> \| --section-md <path>] [--guidance <dir>]` | Optionally records one evidence submission, then reports `pending`/`satisfied`/`written`, or refuses on exhaustion | `SPAN_NOT_IN_SOURCE`, `VALIDATE_VERDICT_REQUIRED`, `EVIDENCE_EXHAUSTED`, `CITATION_MULTI_CLAIM_SENTENCE`, `CITATION_NOUN_PHRASE`, `CITATION_NOT_AT_SENTENCE_END`, `CITATION_DETACHED_FROM_OBJECT`, `CITATION_UNDER_NONE_REGIME`, `CONTRACT_HEADER_ABSENT`, `SOURCE_STYLE_REFERENCE`, `SOURCE_NOT_EVIDENCE` |

`--section-md <path>` reads `--block`'s `citations` regime straight from an
already-headered `sections/*.md` file, instead of typing `--regime` by
hand; an explicit `--regime` always wins when both are given.

**A `--source-md` that resolves inside a `guidance/` folder is gated by
that folder's own registry class** (`plan`'s `style-reference`/`evidence`
classification, above — never a second classifier). A folder classed
`style-reference` refuses `SOURCE_STYLE_REFERENCE`: that class feeds STYLE
only, and a quote lifted from one is not evidence no matter how well it
locates. A folder classed anything else — `unclassified` included — refuses
`SOURCE_NOT_EVIDENCE`: `evidence` is the one class this gate accepts. A
`--source-md` that does not resolve under `guidance/` at all is outside
this gate's business and is never refused here.

**Three search rounds per block, then exhaustion.** `insufficient` fails a
claim exactly as `does-not-hold` does — never a soft `holds`. On the third
round with claims still unsupported, `validate` refuses
`EVIDENCE_EXHAUSTED` naming every unsupported claim, and
`paper_block.substitute` is never reached: the write sits strictly inside
the all-satisfied branch.

**Placement dispatches on regime, never one universal rule.** Under
`discovery`, a citation must close the sentence it supports and a
noun-phrase citation is prohibited; under `resolution`, a citation attaches
to the object it credits wherever that sits, and a noun-phrase citation is
exactly what that asks for; under `none`, no citation is allowed at all.
