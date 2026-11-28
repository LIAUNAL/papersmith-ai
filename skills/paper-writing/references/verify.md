## The couplings hold, or they do not: `verify`

Ten contracts state obligations that span two sections. A finished
`paper/main.tex` can satisfy every section alone and still be incoherent
across them — `verify` is a read-only report over five cross-section
couplings, citation integrity, contract currency, and the checks listed
below. It
never writes a byte, under any input, including every refusal path, and it
never repairs anything it finds — `skill-audit`'s own shape, reused here.

```bash
.venv/bin/python skills/paper-writing/scripts/paper_cli.py couplings --file couplings.json
.venv/bin/python skills/paper-writing/scripts/paper_cli.py verify
```

| Verb | What it does | Refuses |
| --- | --- | --- |
| `couplings --file <path\|->` | Validates a JSON couplings record's shape and writes it WHOLE, atomically, to `paper/couplings.json` — never merged with what was there before | `COUPLINGS_INPUT_UNREADABLE`, `COUPLINGS_RECORD_MALFORMED` |
| `verify [--sections <dir>]` | Read-only report: `contribution-list`, `chain`, `gap`, `artefacts`, `future-work`, `citations`, `contract-currency`, `figure-semantics`, `language`, `references` (every cited key has a record in `.paper-writing/references.json`; a missing record fails, while `not_found` and `unreachable` pass with a note in `limits`, so an abstract is never required; a cited key with no title on disk (`not_found`, `unreachable`) or no abstract also lands in the report's top-level `warnings` as `CITED_SOURCE_WITHOUT_TITLE` or `CITED_SOURCE_WITHOUT_ABSTRACT` with its keys: visible, never a failure, so offline work is never blocked; three more advisory `warnings` screen the citations lexically: `CITED_MORE_THAN_ONCE` (only when `couplings.json` declares `citation_policy.cite_once`; each repeated key with its count), `QUOTE_SHARES_NO_TERM_WITH_CLAIM` (an evidence record judged `holds` whose quote shares no content term with its claim; its `records` name the block) and `SOURCE_SHARES_NO_TERM_WITH_PAPER` (a cited source whose title and abstract share no content term with the paper's title, abstract and declared contributions: possibly off-field). A flagged citation may still be right; correct the quote or the source, or keep it knowingly — the final judge reads it either way), `figure-table-balance` (the figure environments, `figure` and `figure*`, against the table environments, `table`, `table*` and `longtable`, inside the blocks of the Methods and Results sections — `materials-and-methods`, `experimental-setup`, `results-and-discussion`, `methods`, `results`, `discussion`, `data-records`, `technical-validation`, `hardware-description`, `validation-characterization`, read off the `<section>.<id>` block markers; passes when figures / (figures + tables) is at least 0.6, fails below, and passes with no table at all (figures only, or no float), the counts saying which; a manuscript whose markers name no section is counted over the body before the back matter, said in `limits`; the evidence names both counts, the ratio, the threshold and the blocks counted), `caption-length` (the words of every `\caption[short]{long}` in `main.tex`, its long title read brace-balanced: commands are stripped while their text arguments keep their words, `\ref`, `\cite` and `\label` count as no word, and an inline math span counts as one; a caption must be at most four lines (checked as at most 70 words), so one over 70 words fails, naming its label or its first five words with its count; no caption at all passes with `max_words` 0; a supplement's captions are not read, said in `limits`); plus, under its own `structure` key, `back-matter-order` (every declaration block above the `\bibliography` line, appendices below it; `unmeasured` `NO_BIBLIOGRAPHY` when there is none), `own-paragraph` (every block whose section contract opens a paragraph with it — the introduction's paragraphs 2–7, the related-work panorama, closing and synthesis pointer, the limitations' failure-mode paragraph, the conclusions' findings and future-work blocks, and every declaration — opens a paragraph of its own, never running into the block before them; `write` and `humanize --apply` open those bodies on a blank line) and `appendix-length` (an appendix whose estimated printed extent is one page or less fails, naming `materials-and-methods` or `experimental-setup` as where its content belongs), which `clean` also requires to pass | `DECLARATION_RECORD_ABSENT` |

**`contribution-list` holds only the blocks that enumerate.** A block that
requires the contributions fact and names at least one declared contribution
literally must name all of them in the declared order; a block that names
none of them (a title, an abstract's background, a related-work synthesis)
only reads the fact and is listed under `reading_blocks`. No enumerating
block at all is a `fail`. **`chain` needs its role labels:** when no block
requiring the problem statement carries a `Problem:` ... `Evidence:` line,
it reports `unmeasured`, reason `CHAIN_ROLES_ABSENT`, instead of failing a
paper written in plain prose.

**Three values, never two.** Every check's own `verdict` is `pass`, `fail`
or `unmeasured` — `unmeasured` is never folded into `pass`. Two new modules
carry this: `paper_coupling_evidence.py` (every disk read `verify`
performs — named to avoid colliding with `paper_evidence.py`, the
claim<->source evidence module `no-claim-without-a-source-that-holds-it`
already ships) and `paper_verify.py` (the pure checks and the report
they assemble; an AST lock and an executed before/after content manifest
both hold it, and `paper_coupling_evidence.py`, to writing nothing).

**The eighth check, `figure-semantics`, reads a dict and imports nothing.**
`paper_verify.py` is held to an import allowlist of exactly `re`, so it can
neither parse JSON nor reach the auditor. The invocation therefore lives in
`paper_coupling_evidence.gather()` — the module that already owns every disk
read — which runs `paper_figure_audit.audit_semantics` over each figure — against
the contract bodies plus the `main.tex` blocks of every section whose contract
declares a `figure:` obligation — and stores the **already-computed report dict** on `Evidence.figure_semantics`.
`paper_verify.py` maps that dict's verdict into its own closed
`pass|fail|unmeasured` vocabulary and never touches a `Path`-typed field. No
figure at all reports `unmeasured`, reason `NO_FIGURE_DECLARED`; a figure the
audit could not compare reports `unmeasured`, reason
`FIGURE_SEMANTICS_UNMEASURED`. The dependency direction is one-way:
`paper_coupling_evidence.py` may import `paper_figure_audit.py`; the auditor
may not import the reader or `paper_verify.py`.

**The ninth check, `language`, reads a scan `cmd_verify` hands in.**
`cmd_verify` runs `paper_language.scan` over the `main.tex` bytes `gather()`
already read and passes the result to `paper_verify.run(..., language=)`,
the same way it resolves `optional_block_ids`. A Spanish prose line or a
placeholder marker (`por definir`, `TODO`, `TBD`, `FIXME`, `\todo`) fails
the check and names its line; a `run()` handed no scan reports
`unmeasured`, reason `LANGUAGE_NOT_SCANNED`, never a silent pass.

**`verify` reads its own declaration record, `paper/couplings.json` —
read-only, untracked like `main.tex` itself.** `couplings` is its producer:
`{"blocks": {...}, "facts": {"contributions": [...], "limitations": [...]},
"chain": {"links": [{"word": ...}, ...]}, "artefacts": {"setup_cells":
[...], "results_artefacts": [...]}, "future_work": {"directions": [{"id":
..., "limitation": ..., "cite_key": ...}, ...]}, "citation_policy":
{"cite_once": true}}` — every field but `blocks` optional (`citation_policy`
is the opt-in rule that each source is cited once and cross-referenced
afterwards), `paper_couplings.validate_couplings_shape` checked
BEFORE a byte is written, so a malformed shape is diagnosed at write time
rather than surfacing later as a confusing `unmeasured`. Unlike `refs.bib`
(never hand-typed, above), this content is legitimately hand-authored: the
operator's own judgment about the paper's structure, not something a
connector resolves. An entirely absent or empty record refuses
`DECLARATION_RECORD_ABSENT` for the whole run: nothing is known about any
coupling, so per-check `unmeasured` across the board would bury the fact
that nothing was checked at all. One block missing its own entry inside an
otherwise-present record is narrower — `unmeasured`, reason
`BLOCK_NOT_DECLARED`, for the couplings that depend on that block only; the
run still proceeds and every other check still reports a real verdict.
Which blocks a check reads is itself derived, never hardcoded or
record-declared: the set is every block whose contract `requires_facts`
names the relevant fact, read through `paper_contract.parse` over
`sections/*.md` headers. An unreadable or headerless corpus reports
`unmeasured`, reason `SECTION_CONTRACTS_UNREADABLE`; a fact no block
requires reports `unmeasured`, reason `NO_BLOCK_REQUIRES_FACT` — never zero
comparisons reported as agreement.

**Contract currency reads the `provenance` region `the-paper-carries-its-
own-decisions` already writes at `substitute --contract` time — `verify`
never writes it.** An absent or empty region reports check `contract-
currency` alone `unmeasured`, reason `CONTRACT_RECORD_ABSENT`, and the run
still exits `0`: every other check still reports. Editing one block's
guidance changes the whole-file contract hash and flags every block of
that section stale, not only the edited one — inherited from that region's
own accepted over-reporting tradeoff, never narrowed here.

**Coupling 3 (the gap) can never read `pass`.** Its own vocabulary is the
single value `unmeasured`, reason `ASSISTED_READING_REQUIRED` — `verify`
never guesses and never gates on "the same thing at different depths."
What it publishes instead: both blocks' closing sentences verbatim with
byte offsets, both front lists with counts, and three mechanical
sub-results (both closings present, fronts equal, front counts equal) as
named booleans — evidence a human can act on without making the reading
themselves.

**Coherence warnings (#180, #183).** `verify` also reports, under its own `coherence` key, eleven advisory checks computed by `paper_coherence.py`: `caption-results`, `caption-interpretation`, `caption-duplicates`, `caption-identifiers` (a caption states what the artefact is and decodes its key: no result values, interpretive verbs, sentences repeated from the body, or identifier codes such as `K1`, `r0h0`, `subject-v300`), `overclaiming` and `claims-findings` (abstract and introduction claims need a results sentence sharing a number or two key terms), `not-performed` (excluded or not-run work outside the limitations), `symbol-redefinition` (the methods' `$x$ denotes ...` table against later definitions) `naming-consistency` (variants of the declared contribution and chain names), `iteration-history` (a sentence narrating the rounds, attempts, pilot runs or proof of concept behind the final experiments, in any section) and `future-work-uncited` (a future-work sentence in the conclusions with no `\cite`). Each entry is `severity: warning` with verdict `pass`, `warn` or `unmeasured`, its findings and its rule; none counts toward `holds`/`fails`/`unmeasured` or changes `clean`.

**Study checks (S7).** In a workspace with a study protocol (a managed revision under `protocol/`, `study/protocol.lock.json` or `analysis/log.jsonl`), `verify` also reports, under its own `study` key, four checks computed by `paper_coherence.run_study` from the manuscript, its `outcomes` fact and the disk read of `skills/_core/empirical/analysis_log.py` (`manuscript_inputs`). An applied-AI or review workspace has none of these files and gets no `study` key: its report is unchanged. In a study workspace whose kit does not ship that module, or whose module fails, the four checks are still reported, `unmeasured` (`CHECK_FAILED`) with the reason under `evidence.unavailable`, so the hard check never disappears silently.

- `primary-outcome-switch` (`severity: error`, verdict `pass`, `fail` or `unmeasured`): the primary outcome the `outcomes` fact names by protocol id (`declare --fact outcomes --value "primary: O1 -- HbA1c at 12 weeks; secondary: O2"`; `Primary outcome:` and `Primary outcomes:` read the same, the id in either case) must be the primary outcome of the revision `study/protocol.lock.json` pins, read by the study protocol's parser. A primary that differs from the one first approved passes only because an amendment of the lock moved it there (`evidence.declared_switches` names the amendment and its reason); any other difference is a `fail` and makes `clean` false, leaving `holds`/`fails`/`unmeasured` untouched. `unmeasured` when the protocol is not locked (`PROTOCOL_NOT_LOCKED`), its locked bytes are gone (`PROTOCOL_LOCK_NOT_CURRENT`), node cannot run the parser (`PROTOCOL_PARSER_UNAVAILABLE`), or the fact is undeclared or names no single primary id (`OUTCOMES_FACT_UNDECLARED`, `PRIMARY_OUTCOME_UNNAMED`); `unmeasured` never changes `clean`. The fact, not the prose, is the source: it is the paper's declared decision, bound by its basis to `protocol/`, and it names the outcome by the id the lock pins.
- `exploratory-as-confirmatory` (warning): a results sentence citing an outcome the way the protocol does (`(Outcome O3)`, `[outcome:O3]`) that only exploratory entries of the analysis log support, and that does not say so (`exploratory`, `post hoc`, `hypothesis-generating`).
- `outcome-not-in-protocol` (warning): the log analysed an outcome the locked protocol does not name.
- `protocol-outcome-not-analysed` (warning): an outcome of the locked protocol has no confirmatory entry in the log.

The analysis log and its labels are the empirical module's ([`skills/_core/empirical/README.md`](../_core/empirical/README.md)); an agent never relabels an entry and never changes the `outcomes` fact to silence a switch.

### Putting back matter in order: `reorder`

`verify` reports `back-matter-order`; `reorder` repairs it, using the same
check to decide which blocks are out of place. A declaration block
(`back-matter.*`, not an appendix) found after the reference list moves to
just above it (above a `\bibliographystyle` line directly over it); an
appendix block found before the reference list moves to just after its last
line (`\end{thebibliography}` for a hand-written list). Each block moves whole
and byte for byte, every byte outside the blocks keeps its order, and the
result must pass `back-matter-order` before anything is written.

```bash
.venv/bin/python skills/paper-writing/scripts/paper_cli.py reorder          # report the moves
.venv/bin/python skills/paper-writing/scripts/paper_cli.py reorder --apply  # write them
```

| Verb | What it does | Refuses |
| --- | --- | --- |
| `reorder [--apply]` | Reports `moves` (`block`, `from_line`, `to`: `before-references` or `after-references`, in document order), `changed`, `applied` and the resulting `back_matter_order` verdict. Writes only with `--apply`, through the same compare-and-swap, one-deep pre-image and atomic replace `substitute` uses. Already in order: no moves and nothing written, so a second `--apply` is a no-op | `REORDER_LAYOUT_AMBIGUOUS` (no reference list, more than one, a reference list inside a block, a `thebibliography` with no end, or a block to move that ends the file without a newline), `TEX_MOVED`, plus the marker codes `status` refuses |

`reorder` refusing `REORDER_LAYOUT_AMBIGUOUS` names the layout it could not
read; fix that by hand (keep one reference list, outside every block), then
run it again.

### Decision Gates (verify)

| Situation | Action |
| --- | --- |
| `verify` refuses `DECLARATION_RECORD_ABSENT` | `paper/couplings.json` is missing or empty — run `couplings --file <path>` with a record naming at least `blocks`, then run `verify` again |
| `couplings` refuses `COUPLINGS_RECORD_MALFORMED` | The given record's shape does not match what `verify`'s checks read (`blocks` empty/absent, or a known field wrong-typed) — fix the record and resubmit; nothing was written |
| A check reports `unmeasured`, reason `BLOCK_NOT_DECLARED` | Only the block(s) that check depends on have no entry in the record; every other check still ran |
| A check reports `unmeasured`, reason `SECTION_CONTRACTS_UNREADABLE` | The `sections/` corpus itself could not be read — `contract`/`order` first, then re-run `verify` |
| Coupling `gap` reports `unmeasured` | This is unconditional, not a defect — read the published closings and front lists yourself; `verify` never closes this one |
| `contract-currency` reports `unmeasured`, reason `CONTRACT_RECORD_ABSENT` | No block was ever written through `write` or `substitute --contract`; every other check still reports |
