## Paper construction flow (review line)

This workspace builds a **systematic review** that follows the PRISMA 2020
statement (Page et al., 2021, doi:10.1136/bmj.n71): no experiments, no
proposal, no remote runs. It was created with `smith init --kind review`
(`paper_kind: "review"` in `.papersmith/config.json`). Every stage writes its
records under `review/`, and `/systematic-review` (its
`skills/systematic-review/scripts/review_cli.py`) runs and checks them; the
skill refuses when a stage's input is missing. The command center (`smith ui`)
shows these ten steps as its phases, each read from its records under
`review/` and locked until the one before it passes, with the operator's
gates among them: G-PROTOCOL, the screening sign-off and the synthesis
acceptance. It hides the experimental line's views (concept map, experiments,
novelty, SOTA constellation).

1. **Harness**: `smith status .` and `smith audit . --check-drift`;
   `/upgrade-project` when the workspace runs an older release.
2. **Scoping**: `/systematic-review scope <the topic in at least two
   sentences>` runs a preliminary search for existing reviews on the topic,
   so the protocol states the gap they leave. `/plausibility` may be used to
   draw the field's constellation in `sota-pool/`.
3. **Protocol** (PRISMA items 5-7, 24): `/systematic-review protocol` writes
   `review/protocol.json`: the objective, the research questions (RQ1, …)
   with their PICOC elements, the inclusion and exclusion criteria with their
   reasons, the information sources with one query string per source, the
   date range, the languages, the screening and appraisal plan and the
   extraction fields. `review_cli.py protocol check` validates it. The
   operator approves it (`review_cli.py protocol approve --by <name>`, gate
   G-PROTOCOL) before any search; a later edit is an amendment, logged with
   its reason. Registration (PROSPERO, OSF) is recorded with
   `/paper-writing declare review-registration`.
4. **Identification** (item 16, top of the flow diagram): `review_cli.py
   search --source openalex|crossref|europepmc` runs the protocol's query for
   that source and logs the date, the exact query and the count in
   `review/searches.jsonl`; exports the operator downloads from Scopus, Web of
   Science, IEEE Xplore or ACM (RIS or BibTeX) enter with `review_cli.py
   import --file <export> --source <name> --query "<as run>"`. `review_cli.py
   dedupe` removes duplicates by DOI, then by normalized title and year.
5. **Screening** (item 8): two independent reviewers decide every record,
   first on title and abstract (`review_cli.py screen --stage ta`), then on
   the full text of the ones kept (`--stage ft`, with one exclusion reason of
   the protocol). The agent may act as one reviewer, the operator is always
   the other; `review_cli.py queue --stage ta --reviewer <name>` lists what a
   reviewer still owes, `review_cli.py conflicts --stage ta` the disagreements
   to resolve (`screen --final`), and `review_cli.py kappa --stage ta` the
   agreement. Full texts are retrieved and turned into Markdown with
   `/paper-ingestion`. The review cites 100 to 200 references: when more
   studies pass, `review_cli.py prioritize` ranks them by topical relation to
   the protocol and journal quartile (SJR), and, once the operator agrees,
   `prioritize --apply --criterion E<n> --reviewer <name>` records the excess
   as full-text exclusions under the protocol's budget criterion. When every
   record is decided and no conflict is left, the operator signs the screening
   off (`review_cli.py signoff --gate screening --by <name>`); the sign-off
   stays current while `review/screening.jsonl` is unchanged.
6. **Appraisal and extraction** (items 9-11): `review_cli.py appraise` records
   each included study's quality answers with the protocol's checklist, and
   `review_cli.py extract` its data items, validated against the protocol's
   extraction fields. Every extracted value carries the quote or page that
   holds it.
7. **Synthesis** (items 12-22): `review_cli.py prisma` counts the flow into
   `review/prisma.json`, `review_cli.py flow` draws the PRISMA 2020 flow
   diagram (`paper/Figures/prisma-flow.svg`), `review_cli.py biblio` the
   counts per year and venue and the keyword co-occurrence
   (`review/biblio.json`), and the agent builds, with the operator, the
   taxonomy of themes, the problem classes and one evidence figure per theme
   (an evidence map, a forest plot, or the studies charted by dimension), with
   at most one comparison table, from `review/extraction.jsonl`. The methods' protocol flow diagram
   (`protocol-flow`, the PRISMA phases adapted to the topic, no counts) is
   drawn by the `diagram-author` agent, compiled with `paper_cli.py render`
   and checked with `/figure-review` before its block is written.
   The operator accepts the synthesis (`review_cli.py signoff --gate synthesis
   --by <name>`, current while `review/prisma.json` and the flow diagram are
   unchanged) before the writing starts.
   The whole paper fits 45 single-column Elsevier pages (25 two-column),
   references included: about 11,000 words of body at 200 references;
   `smith paper qa` estimates it (`page_budget`).
8. **Scaffolding, declarations and writing**: `/paper-writing` opens the
   `paper/` tree from the review section contracts in `sections/` (title,
   abstract after PRISMA 2020 for Abstracts, introduction, background, methods,
   results as a comparative thematic synthesis,
   discussion, limitations, conclusions, back matter), records the
   declarations (`review-registration` included) and writes one block at a
   time. Every count is copied from `review/prisma.json`; every claim about a
   study cites it.
9. **Figures and paper**: `/figure-review <figure id>` and the compiled
   `paper/main.pdf`, as in the experimental line.
10. **Reporting check and audit**: `review_cli.py checklist` lists the 27
    PRISMA 2020 items with the record or section that satisfies each and the
    ones still owed; journals ask for this checklist as a supplementary file.
    `smith audit .` and `/skill-audit <subject>` report; they never repair.

The human gates are the protocol approval (G-PROTOCOL), the screening
decisions the operator signs as a reviewer, the resolution of conflicts, the
screening sign-off and the acceptance of the synthesis (`review/signoffs.json`).
An agent never decides a gate or signs as the second reviewer on the
operator's behalf.
