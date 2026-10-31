---
name: plausibility
description: "Trigger: explore a research idea before any ingestion — scout ~25 SOTA references from their abstracts, map the pool to one solar-system constellation HTML, then discuss the hypothesis' plausibility against that SOTA with quoted evidence. Three stretches, one command, no ingestion."
---

# Plausibility

Before a single PDF is ingested, an idea needs two things: a map of the
territory, and an honest reading of where the idea stands on it. This skill
does both in three stretches — scout the literature, draw the
constellation, then deliberate the plausibility — and nothing here ingests,
files into `guidance/`, or publishes. Those are later stages with their own
doors.

## An idea composed by the dashboard

An operator who arrives without a clear idea can use the dashboard's
thematic help: 3 to 5 keywords are searched in the Banco LIA (the
`banco-lia` MCP server) and the dashboard proposes a draft idea naming the
keywords, the matching topics and a few LIA items. The operator edits and
approves it, and it reaches this skill as the argument of `/plausibility`
like any other idea. Treat it as such: the two-sentence minimum still
applies, and the stretches below run unchanged. The LIA items it names are
the lab's own continuity context (projects `H*`/`P*` as background, articles
by title and DOI), never SOTA evidence: they enter the pool only if the
scout finds them as references on their own merits, and the report never
cites the draft's items as state of the art.

## The three stretches

| Stretch | Delegated to | Begins after | Ends at | Measure this before delegating |
| --- | --- | --- | --- | --- |
| Scout | this skill delegates to the `sota-scout` agent | the idea is stated in at least two sentences | the pool: 25 candidates with abstracts, 3 to 5 families, and the provisional plausibility note | the stated idea — scouting an unstated idea invents its own question |
| Constellation | this skill delegates to the `sota-grapher` agent | the pool holds its 25 candidates | the single `atlas.html` beside `atlas.json`, plus the checker's green run | the pool file exists with 25 resolved candidates — mapping fewer invents coverage |
| Screen | this skill delegates to the `novelty-screener` agent | the hypothesis is stated and the pool holds its candidates | the plausibility report — graded claims, ranked top 5, and one closing paragraph on where the proposal stands — with what remains owed | the stated hypothesis plus the pool — an empty pool is the scout's to fill, not this stretch's to invent; the borrowed `resolve` runs only to confirm the top 5, and nothing here files into `guidance/` |

What moves is execution, never doctrine: every rule for scouting and
mapping lives below, every rule for screening lives in the agent's own
section, and each agent's first instruction is to load this file. The
grapher drives the checker and the renderer in its own loop; those two
scripts are the only shell commands that loop may invoke, and the
screener's one shell command is the borrowed `resolve` invocation.

## When a delegated agent cannot be spawned

Each stretch this skill delegates is defined in full by its own agent file:
`.claude/agents/novelty-screener.md`, `.claude/agents/sota-grapher.md`,
`.claude/agents/sota-scout.md`. When an agent cannot be spawned — the harness
has no sub-agent mechanism, the agent is not registered in this session, or
the spawn itself fails — perform the stretch inline: read that agent's
definition file and follow it as written, from the beginning it states to the
end it states, holding any gate this skill sets before the stretch, and returning the
report shape it specifies. Its `tools:` line still bounds the stretch: an act
that would need a tool outside that list is a stop, not a workaround. Say in
the reply that the stretch ran inline and why the agent could not be spawned.

## The pool

Scouting writes `sota-pool/candidates.json`: at most 25 entries, each with
identifier, resolver, title, year, venue, abstract (quoted verbatim from the
source, never paraphrased), source URL, retrieval date, and its provisional
family. A candidate without an abstract does not exist for the map — a
title is not a territory. The pool is research content: it travels
gitignored, like everything under `sota-pool/`.

What each resolver can and cannot give the pool, measured from
`paper_resolve.py`:

- **OpenAlex** returns the year, the venue and, when OpenAlex holds one, the
  abstract (rebuilt in reading order from its inverted index).
- **Crossref** never returns an abstract: publishers ship it as JATS markup,
  and stripping tags would mint a quote no source printed, so the resolver
  reports `abstract: null`. Its `year` is the record's `issued` year (else
  its `published` year), `null` when Crossref gives neither. Resolve a DOI
  through OpenAlex for its abstract; when neither resolver has one, the
  candidate stays out of the pool (it cannot be quoted,
  and the checker's `--pool` run refuses any planet citing it with
  `EVIDENCE_ABSTRACT_MISSING`).
- **arXiv** returns the abstract (the entry's own `<summary>`, whitespace
  collapsed) with `venue: "arXiv"` and the year of the entry's `<published>`
  stamp (the first version's submission date, not a later venue's). An entry
  without a readable stamp reports `year: null`; never guess one.

Each candidate carries the `identifier` it was resolved by and its
`source_url`; a planet's `evidence.origin` names one of those two, which is
how the checker finds the abstract a quote claims.

The borrowed `resolve` caches every answer it gives. Both agents pass
`--cache-dir sota-pool/metadata`, so those caches stay in the pool too, one
`<metadata_digest>.json` per resolution. Without that flag `resolve` caches
under `paper/.paper-writing/metadata/`, which is paper-writing's own place,
and exploring an idea would start a paper tree before any paper exists.

## The planets

Every system carries exactly these slots. Counts are exact where stated,
and the 20-planet limit per system is absolute.

| Slot | Planets | Orbit | What it holds |
| --- | --- | --- | --- |
| `sun` | exactly 1 | 0 | The paper: title at the center |
| `branch` | 0 to 2 | 1 | Research branches the paper claims |
| `topic_app` | exactly 1 | 1 | The topic as the application domain states it |
| `topic_ai` | exactly 1 | 1 | The same topic framed as an AI problem |
| `problem` | exactly 1 | 1 | The problem the paper faces, in one claim |
| `application` | exactly 1 | 1 | Where it lands in the world |
| `family` | exactly 1 | 2 | The group this system belongs to: one family per paper, 3 to 5 families per pool |
| `novelty` | exactly 1 | 1 | What the paper adds over those families |
| `contribution` | 0 to 5 | 1 | Concepts argued beyond the one novelty claim: empty for a paper, 3 to 5 for a proposal overlaid on the pool |
| `result` | 1 to 3 | 3 | Punctual results, one claim per planet |
| `conclusion` | 1 to 2 | 3 | Conclusions, one claim per node |

A family the abstracts themselves name carries `provenance: stated`. A
family grouped out of scattered methods carries `provenance: grouped`.
A paper belongs to exactly one family; the pool holds 3 to 5 families
total. Families are groups of systems, not labels sprayed over every
paper — a family name appearing on every system is a family that
distinguishes nothing.

## Edges

Two scopes, one closed set of relations (`about`, `addresses`, `extends`,
`contradicts`, `supports`, `yields`, `shares-family-with`): edges inside
one system name how that paper connects its own claims; edges between
systems of the same family name how siblings touch — a citation, an
extension, a shared method; edges across families name the rare bridges —
a contradiction, an import. No self-loops; every endpoint names a planet
id that exists in the named system. An edge no abstract supports is a
drawing, not a finding. Systems draw grouped by family on the plane, so a
family reads as a neighborhood, not a legend entry.

## Output contract

Beside the pool, never inside any paper folder (there are no paper folders
yet — nothing is ingested):

- `sota-pool/atlas.json`: systems, planets, edges. Every planet carries
  `evidence: {origin, quote, retrieved}` — origin names the abstract's
  source URL or identifier, quote is copied verbatim, retrieved is the
  date. A paraphrase is not a quote and fails the check.
- `sota-pool/atlas.html`: the single navigable file, all systems in one
  shared 3D sky, rendered deterministically from `atlas.json` by
  `scripts/render_atlas.py` — same atlas, same sky, every run. Never
  hand-edited — a hand touch is regenerated away on the next run.

## The checker and the renderer

`scripts/check_atlas.py` (stdlib-only) is the bound that holds. It refuses,
with exit 1 naming every violation: more than 20 planets in a system, a
duplicated planet id, an edge endpoint with no planet, a self-loop, a slot
outside the table, a slot count outside its row, a `rel` outside the closed
set, a planet without a non-empty `origin` and `quote`, fewer than 25
systems when the pool promises 25. Exit 2 is usage or unreadable input —
nothing was judged. The checker reads the atlas; it never reads the web.

Run it against the pool, so a quote is held to the abstract it claims:

```
python3 skills/plausibility/scripts/check_atlas.py sota-pool/atlas.json --pool sota-pool/candidates.json
```

With `--pool`, every planet's `evidence.origin` must name a pool candidate
(its `identifier`, `source_url` or `url`; `EVIDENCE_ORIGIN_NOT_IN_POOL`
otherwise), that candidate must hold an abstract (`EVIDENCE_ABSTRACT_MISSING`),
and the `quote` must be a verbatim substring of it
(`EVIDENCE_QUOTE_NOT_IN_ABSTRACT`). Runs of whitespace compare collapsed — a
line break is layout — and nothing else is normalized: case, punctuation and
words must match. A pool that cannot be read as a list of candidates (or
`{"candidates": [...]}`) exits 2 (`POOL_UNREADABLE`, `POOL_NOT_JSON`,
`POOL_MALFORMED`). A green `--pool` run certifies that every quote is in the
stored abstract, which is still not that the abstract supports the planet;
without `--pool` a green run certifies shape alone. The proposal-overlaid
atlas (`atlas.with-proposal.json`) is checked without `--pool`: its proposal
system quotes the proposal, not the pool, and its SOTA systems are the ones
this run already held to the pool.

`scripts/render_atlas.py` (stdlib-only) turns a green atlas into the HTML:
every system in one shared 3D sky — family neighborhoods at their own
heights, each system on its own tilted orbital plane — intra-system links as
segments, inter-system links as arcs running planet to planet. The renderer
computes the whole scene and writes it as a JSON data island; the vendored
three.js viewer `assets/atlas3d.bundle.js` is inlined verbatim and only
draws it, so there is no CDN and no network at view time. Rebuild that
bundle with `npm run build:atlas-viewer` only when `assets/atlas3d/viewer.js`
changes (see `assets/atlas3d/README.md`); rendering never needs Node.
When the computer has no suitable GPU (no WebGL, a software renderer, little
memory or few cores, or a 3D sky that draws too slowly) the page opens a
lighter 2D constellation of the same scene and says why; a toolbar button and
`?view=2d` / `?view=3d` switch views. System names appear where they do not
overlap, and the page draws nothing while it is hidden.
Drag orbits the sky and the wheel zooms. Clicking a planet shows its detail
and abstract quote; a family filter dims what does not belong; hovering a
planet highlights its links across systems; double-clicking flies to it.
The "Disposición de grupos" button regroups the sky live — each whole system
slides so a family's systems cluster together on a flat grid — and pressing it
again restores the precomputed sky; it is presentation only and never changes
`atlas.json` or the data island. Framed by the dashboard, the page accepts its
`atlas-command` messages and reports layout changes and planet selections back
(contract in `assets/atlas3d/README.md`). Family
ties — the dashed curves joining same-named family planets — are
presentation computed from shared identity, never findings: families are
the only planets two systems may share by name, so the curve draws what
the data already says. Exit 1 on a
red atlas — the renderer never draws what the checker refused; exit 2 is usage,
unreadable input or a missing viewer bundle.

`--title <text>` names the page in both the tab title and the heading, because a
caller who names it means both places it is read. Stage 3 is that caller: it
renders this constellation with a proposal inside it, and a page headed "SOTA
constellation — one sky" would be false for it. The default stays this
constellation's own words, and the name is escaped, since a proposal title is
text and not markup.

## Screening: the dialogue

The third stretch is a conversation, not a batch job. The screener splits
the hypothesis into claims and grades each one — `provisional-novel`,
`provisional-known`, `provisional-tension`, `provisional-contradicted` —
always quoted, always marked provisional until ingestion. The operator
adjusts the idea mid-dialogue and asks for re-screening; every pass is a
fresh report, because the agent keeps no state between passes beyond the
conversation itself. The stretch ends at the report plus the ranked top 5
for the later ingestion stage — never at a publication, never at a filing.

## The acceptance gate

The third stretch ends at the report, and the report is not handed on until the
operator accepts it. This is the skill's one human stop, and it is a stop rather
than a notice: the ranked top 5 that leaves here is a list of PDFs somebody is
about to be sent looking for, and a list nobody approved sends the next stage
after papers the operator never asked for.

What acceptance covers is narrow, and stating the edges is the point:

- It approves **the reading**, not the idea. The graded claims, the ranked top 5
  and the closing paragraph on where the proposal stands are what the operator
  accepts or sends back. The idea is the operator's own and needs no blessing.
- It publishes nothing. This skill never publishes.
- It files nothing. Nothing here reaches `guidance/`.

Every pass is a fresh report, so every pass gets its own gate. Re-screening after
an adjustment is a new reading, and the acceptance of the previous one does not
carry over to it.

**Presenting the report and proceeding in the same turn is the failure this
section exists to prevent.** A gate that cannot be refused is a summary. The
operator has to be able to say no and have that change what happens next.

## Decision gates

| Situation | Action |
| --- | --- |
| Idea under two sentences | Refuse before searching; scouting an unstated idea invents its own question |
| The idea comes from the dashboard's thematic help | Treat it as any stated idea: two sentences still apply, and its LIA items are continuity context, never SOTA evidence |
| Fewer than 25 resolvable candidates | Report the pool short with what was tried; never pad with unquoted entries |
| More than 5 families | Keep the 5 the abstracts lean on hardest and say which were left out |
| The checker refuses | Fix the atlas and re-run, up to 3 repair passes; then stop with the violations quoted in `owed` |
| A quote is not verbatim in its abstract | Copy the passage from the pool's abstract again, or drop the planet; never edit the abstract to fit the quote |
| A claim has no abstract passage | The planet does not exist; a quoteless planet is a drawing |
| The report is not accepted | Hand nothing to ingestion. Ask what to change and re-screen; the top 5 does not travel on an unaccepted report |

## Measure before you assert

Never write a planet whose quote was not read in the same pass from the
abstract its evidence names, and never grade a claim whose abstract was not
read in the same reply. An invented quote sounds like a finding and gets
acted on like one.
