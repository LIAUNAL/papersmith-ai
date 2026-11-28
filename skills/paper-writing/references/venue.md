## Venue adaptation: `venue`

A journal asks for its own document class, section list, limits, declarations
and reference style; smith's base template (`sections/*.md`, `paper/main.tex`)
asks for its own. `venue` measures the one against the other and builds the
journal's file **without ever writing `paper/main.tex` or `sections/`**.
Everything about one journal lives under `paper/venues/<slug>/`. Choose the
journal first (`/journal-finder` ranks candidates into
`paper/journal-candidates.json`); formatting for a venue comes after the venue
is chosen, not before.

```
selected -> requirements -> template -> audited -> planned -> approved -> built (-> compiled)
```

`planned` and `approved` are only owed while the audit holds a `blocker`
finding; an audit with none goes from `audited` straight to `built`.

```bash
.venv/bin/python skills/paper-writing/scripts/paper_cli.py venue select --slug eswa --candidate S1001
.venv/bin/python skills/paper-writing/scripts/paper_cli.py venue requirements --slug eswa --file paper/venues/eswa/requirements.draft.json
.venv/bin/python skills/paper-writing/scripts/paper_cli.py venue acquire --slug eswa --texlive elsarticle
.venv/bin/python skills/paper-writing/scripts/paper_cli.py venue diff --slug eswa
.venv/bin/python skills/paper-writing/scripts/paper_cli.py venue plan --slug eswa --file paper/venues/eswa/plan.draft.md
.venv/bin/python skills/paper-writing/scripts/paper_cli.py venue approve --slug eswa --statement "<the operator's words>" --plan-sha256 <hex>
.venv/bin/python skills/paper-writing/scripts/paper_cli.py venue build --slug eswa
```

Every verb accepts `--paper <dir>`, prints one JSON object, and on a refusal
exits 2 having written nothing.

The shipped venue catalog (`venue catalog`, or one venue with
`venue catalog --slug <slug>`) is read-only data about the major venues
(NeurIPS, ICML, IEEE conferences and Transactions, Elsevier, Springer LNCS,
Frontiers, MDPI): which TeX Live class a venue's template uses, where its
official guidelines live, and the exact `acquire` command its class origin
implies. It is data, never shipped templates: the forge ships no document
class, so the class or style archive itself always arrives per workspace
through `venue acquire` (`venue list` reports the catalog beside the
workspace's own venues).

| Verb | What it does | Refuses |
| --- | --- | --- |
| `select --slug <s> (--candidate <openalex id> \| --journal <name> --issn <issn> [--publisher <name>])` | Writes `venue.json`: the journal (name, ISSNs, publisher, homepage), and the quartile, its source and the review-time estimate copied from `paper/journal-candidates.json`; a candidate missing optional fields is tolerated. A manual selection records the publisher only when `--publisher` names it; without one the venue reads as the `neutral` back-matter family, so name it for an Elsevier, MDPI or IEEE journal. The slug is lowercase letters, digits and hyphens | `VENUE_SLUG_INVALID`, `SELECT_MODE_REQUIRED`, `SELECT_MODE_CONFLICT`, `ISSN_INVALID`, `CANDIDATES_ABSENT`, `CANDIDATE_UNKNOWN`, `VENUE_EXISTS`, `PAPER_ABSENT` |
| `requirements --slug <s> --file <json>` | Validates and stores `requirements.json` (schema 1): `guidelines_urls`, `document_class`, `sections`, `limits`, `declarations_required`, `reference_style`, `extras`. **Every requirement carries the `quote` from the guidelines and the `url` it came from** | `VENUE_ABSENT`, `REQUIREMENTS_INVALID`, `REQUIREMENT_UNSOURCED`, `PAPER_OUTSIDE_REPOSITORY` |
| `acquire --slug <s> (--texlive <class> \| --file <zip\|cls\|sty\|bst\|tex> --url <origin>)` | Records `template.json`. A class TeX Live carries is recorded by name and the path `kpsewhich` resolves (also searched in `/Library/TeX/texbin` and `/usr/local/texlive/*/bin/*`). A publisher template is copied into `template/` with its origin url, sha256 and date; an archive is extracted only if no member escapes the directory, none is a symlink and the size and entry caps hold, and nothing is left behind otherwise | `VENUE_ABSENT`, `ACQUIRE_MODE_REQUIRED`, `ACQUIRE_MODE_CONFLICT`, `TEMPLATE_CLASS_INVALID`, `TEXLIVE_UNAVAILABLE`, `TEMPLATE_ABSENT`, `TEMPLATE_ORIGIN_REQUIRED`, `TEMPLATE_FILE_UNSUPPORTED`, `TEMPLATE_UNSAFE` |
| `diff --slug <s> [--sections <dir>]` | Writes `audit.json`: smith's section contracts (`paper_contract.parse`: ids, `position`, the `**Extent**` prose read best-effort) and the written `main.tex` (blocks, declarations, keyword count, abstract/title/main-text word counts, figures, tables, cited references, the class and bibliography-style lines) against `requirements.json`. Findings: `missing-section`, `extra-section`, `out-of-order`, `over-limit`, `under-limit`, `missing-declaration`, `class-mismatch`, `reference-style-mismatch`, `missing-extra`, `undecidable`; each with a `severity` (`blocker`, `major`, `minor`), the smith side, the venue side with its quote and url, the affected block ids, and `resolved_by` (`build`, `text-change`, `operator-decision`). The audit records the sha256 of `main.tex` and of `requirements.json` it was computed from | `VENUE_ABSENT`, `REQUIREMENTS_ABSENT`, `TEMPLATE_ABSENT`, `PAPER_ABSENT`, `SECTION_CONTRACTS_UNREADABLE`, `MALFORMED_HEADER` and the marker codes |
| `plan --slug <s> --file <md>` | Stores the agent's plan as `plan.md` and returns its sha256. The plan must cite at least one finding id from the audit; storing it **resets any earlier approval** | `AUDIT_ABSENT`, `PLAN_UNREADABLE`, `PLAN_REFERENCES_NO_FINDING` |
| `approve --slug <s> --statement "<words>" --plan-sha256 <hex>` | Records `approval.json` with the operator's statement verbatim, bound to the current plan's hash (the dashboard button writes the same record with `via: dashboard`) | `STATEMENT_EMPTY`, `PLAN_ABSENT`, `PLAN_HASH_MISMATCH` |
| `build --slug <s>` | Assembles `paper/venues/<slug>/main.tex`: the venue's class line, the canonical preamble minus the packages the class owns (reported as `preamble.skipped`; package, command-definition and hook statements such as `\AtBeginDocument{\linenumbers}` are kept, anything else is dropped and reported), front matter mapped from the title, abstract and keyword blocks for `elsarticle`/`IEEEtran`/`llncs` (any other class keeps the canonical title block, an outer `minipage` included, and `\maketitle`), every canonical block copied **verbatim with its markers** in the venue's section order, every heading line the canonical file writes between blocks (`\section`, `\subsection`, starred or not, with its label) kept as written -- a section that opens with a `\subsection` line (Limitations inside Results) travels right after the section before it, and `build` writes a `\section` of its own only for a section with no heading line. The `\author` block is parsed (`parse_author_block`: the revealed-author form of `sections/09-title-and-keywords.md`, with or without its outer `minipage`; one author line with superscript indices and `*`, one affiliation per index -- wrapped lines are joined --, an `E-mails:` line with one address per author in author order, an `ORCID: <surname> <id>; ...` line, a corresponding-author line) into the class's own commands: elsarticle `\author[affN]{Name\corref{cor1}\fnref{orcidN}}`, `\ead`, `\cortext`, `\fntext` and `\address[affN]`; IEEEtran `\IEEEauthorblockN`/`\IEEEauthorblockA`; llncs `\inst`, `\thanks`, `\orcidID`, `\institute` and `\email`. For elsarticle the written `bm-highlights` itemize becomes `\begin{highlights}...\end{highlights}` inside the front matter, after the abstract, and the block travels inside the `\iffalse` copy instead of among the declarations, `\bibliographystyle` from the requirements and `\bibliography{../../refs}`. Sections the venue does not list are kept after its own; sections smith lacks are reported, never invented. The back matter always renders after the content sections and before the bibliography, the AI-use declaration last, and `bm-appendices` after the bibliography, whatever order the venue lists or the canonical file holds (`sections.appendices_after_references`). Writes `build.json`. **Every figure the venue file includes is measured on the venue's page** (`figure_print`, in the output and in `build.json`): the venue's body size and `\textwidth` come from its own `main.tex` (the class and options from the requirements, any kept `geometry`), the same reader and font measurement `place` uses; each placed data figure (`<id>.provenance.json`) and rendered diagram (`<id>.diagram.json`) is measured at the width its `\includegraphics` declares. A figure whose smallest text prints below 0.70 x the venue body, or wider than the venue `\textwidth`, is a finding (`issues`: `below-print-floor`, `wider-than-text`) with its `remedy`: redraw at the venue's body and printed width, naming both (for a data figure, the `ps_figures.apply_style` call). The build does not fail on it; `figure_print.status` reads `unmeasured` without `pypdfium2` | `PLAN_NOT_APPROVED`, `AUDIT_STALE`, `AUDIT_ABSENT`, `TEMPLATE_ABSENT`, `REQUIREMENTS_ABSENT`, `BLOCK_HAND_EDITED`, `TITLE_BLOCK_UNPARSEABLE`, `HIGHLIGHTS_UNPARSEABLE` |
| `status --slug <s>`, `list` | Read-only: the state, the step flags, the finding counts, whether the audit is stale, and the next action | `VENUE_ABSENT`, `VENUE_SLUG_INVALID` |

**The approval gate.** `build` refuses `PLAN_NOT_APPROVED` while the audit holds
a `blocker` finding and `approval.json` does not carry the sha256 of the
current `plan.md`. An approval for a plan that was since replaced does not
count. `build` also refuses `AUDIT_STALE` when `main.tex` or `requirements.json`
changed after `diff`, so it never answers to findings that no longer exist.
It verifies each canonical block's digest first and refuses `BLOCK_HAND_EDITED`
for a hand edit, naming the block.

**Text changes go through `write`, and only through it.** Shortening the
abstract, adding a data-availability statement, renaming or merging a section:
each is applied by the existing loop (redactor, then contract-auditor, then
`write --draft --audit`), one block at a time, after the approval. No `venue`
verb edits a block. A section the venue needs and smith lacks is a plan item
the operator decides, never something drafted on the agent's own authority.
After each applied item, re-run `diff` and read the findings that remain.

**Compiling the venue file.** The venue `main.tex` compiles from
`paper/venues/<slug>/` (`pdflatex`, `bibtex`, `pdflatex` twice). For a
publisher template `build` and `status` report `compile_env`
(`TEXINPUTS`/`BSTINPUTS` pointing at `./template//`); a TeX Live class needs
none.

**The venue stretch delegates to the `venue-adapter` agent.** It reads the
journal's author guidelines and template, drafts the requirements (each one a
quote and a url, none invented), reads `audit.json`, alerts on sections to
adjust, sections missing and every inconsistency between smith's base template
and the venue's, and proposes a plan only when one is prudent (no plan when the
audit is clean apart from the class and preamble). It iterates the plan with
the operator until the operator approves its exact text. It has no write tool
and no shell: the orchestrator saves the requirements and the plan it returns,
runs the verbs, and applies the approved text changes through `write`. It
never submits the paper.

**Measure this before delegating (venue-adapter):** confirm
`paper/venues/<slug>/venue.json` exists (`status --slug <s>`), `paper/main.tex`
exists and no section under `sections/` is empty, and note whether
`requirements.json`, `template.json` and `audit.json` exist and whether
`audit_stale` is true; an adapter asked to plan against a stale audit judges
a manuscript that is gone.

**On a harness with no Task-tool delegation:** run the stretch in-process, in
the same order, holding to the same gate; its `tools:` line (read, search and
fetch only) is then the orchestrator's own discipline, not a structural
guarantee.

| Situation | Action |
| --- | --- |
| `requirements` refuses `REQUIREMENT_UNSOURCED` | Every requirement needs the guideline's own words and the page url. Quote it or drop it; never paraphrase a limit into existence |
| `diff` reports a `blocker` | The venue cannot be built until the operator approves a plan covering it: draft the plan, show it whole, iterate |
| `plan` refuses `PLAN_REFERENCES_NO_FINDING` | Cite each item by a finding id from `audit.json`, e.g. `[over-limit:abstract_words]` |
| `approve` refuses `PLAN_HASH_MISMATCH` | The plan changed after the operator read it; show the current plan and its hash again |
| `build` refuses `AUDIT_STALE` | The manuscript or the requirements changed since `diff`; re-run it |
| `build` refuses `BLOCK_HAND_EDITED` | A canonical block was edited by hand; read it, then `substitute --adopt` if the edit is deliberate |
| `build` refuses `TITLE_BLOCK_UNPARSEABLE` | The `\author` block cannot be mapped into the class's author commands (an unknown superscript marker, an index no affiliation defines, e-mails that do not match the authors one to one, an ORCID that matches no single author, an environment other than one outer `minipage`); the detail names it. Rewrite the title block in the revealed-author form of `sections/09-title-and-keywords.md` |
| `build` refuses `HIGHLIGHTS_UNPARSEABLE` | The class sets the highlights in its own environment and `bm-highlights` holds no itemize with `\item` lines; write the highlights as one itemize |
| `build` reports a `figure_print` finding | The figure is sized for the canonical layout (an 11 pt figure in a 12 pt venue prints below the venue floor). Redraw it at the body size and printed width the `remedy` names, then `place` it again (its `venueWarnings` must be empty) and rebuild |
| `acquire` refuses `TEMPLATE_UNSAFE` | The archive has a member that escapes the directory, a symlink, or is past the size cap; do not extract it by hand either, ask for the publisher's original |
