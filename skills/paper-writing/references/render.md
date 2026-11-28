## A diagram that compiles, or says why: `render` and `place`

Three more modules, from `a-diagram-that-compiles-or-says-why`:
`paper_latex.py` (the sole holder of `subprocess` in this skill — an AST
scan, `NoSubprocessScanTests`, holds every other script to zero),
`paper_figure.py` (source/manifest layout, stop A, the compile pipeline,
the repair-budget ledger), and `paper_obligation.py` (components,
separation, caption, mandatory — pure functions over the contract's own
`figure:` declaration, never a hardcoded section or block id).

Each diagram id resolves to `paper/Figures/<id>.tex` (standalone TikZ, one
`% node: <label>` comment per component), a sibling `<id>.diagram.json`
manifest (`components`, `encodings`, `caption`), and — once compiled —
`<id>.pdf` beside them. `main.tex` receives the figure only through the
existing `substitute` verb's `\includegraphics`; no TikZ byte ever enters
`main.tex`.

**Provenance (optional `provenance` key).** So a figure can be redrawn
later (a font fix, a renamed symbol) from what the repository holds, the
manifest records the script that generates it and the data it plots:
`"provenance": {"script": {"path": "<repo-relative>", "sha256": "<hex>"},
"inputs": [{"path": "<repo-relative>", "sha256": "<hex>"}, ...]}`.
`figure provenance` writes it; never hand-compute the digests. A
hand-drawn diagram records its own `paper/Figures/<id>.tex` as the script
and no `--input` (an empty `inputs` list is a recorded fact, not a gap).
`render` and `figure audit` add `provenanceWarnings`, a list of
`{code, role, path, message}` (`role` is `script`, `input`, or `inputs` for
the list itself), and never refuse or spend a repair attempt on them:
`FIGURE_PROVENANCE_UNRECORDED` (no script, or no input list),
`FIGURE_PROVENANCE_OUTSIDE_REPOSITORY` (an absolute path or one escaping
the repository), `FIGURE_PROVENANCE_MISSING` (the file is gone) and
`FIGURE_PROVENANCE_CHANGED` (its sha256 differs; re-run `figure provenance`
after a deliberate change) and `FIGURE_PROVENANCE_UNREADABLE` (the file exists
but cannot be read). A manifest without the key renders and audits
exactly as before, with the two `UNRECORDED` warnings.

| Verb | What it does | Refuses |
| --- | --- | --- |
| `render --figure-id <id> [--paper <dir>]` | Compiles `<id>.tex` standalone via exactly one `latexmk` call, cross-checks the manifest both directions, and scans stop A before ever spawning the compiler; every non-refused result carries `provenanceWarnings` (advisory) | `DIAGRAM_SOURCE_ABSENT`, `MANIFEST_SOURCE_MISMATCH`, `DIAGRAM_PLOTS_DATA`, `LATEX_TOOLCHAIN_ABSENT`, `LATEX_LOG_ABSENT`, `LATEX_OUTCOME_UNEXPLAINED`, `LATEX_PACKAGE_ABSENT`, `REPAIR_BUDGET_SPENT` |
| `render --figure-id <id> --section <section-id> --block <id> [--sections <dir>] [--paper <dir>]` | The same compile, and then the full obligation suite (components — only when the block declares `components_from`, excludes, caption, mandatory, cross-diagram separation) against the block's own `figure:` declaration | adds `MALFORMED_FIGURE_OBLIGATION`, `COMPONENT_MISMATCH`, `COMPONENTS_FACT_UNRESOLVED`, `COMPONENTS_FACT_NOT_A_LIST`, `EXCLUDED_COMPONENT`, `SHARED_COMPONENT`, `CAPTION_INCOMPLETE`, `MANDATORY_DIAGRAM_ABSENT` |
| `render --figure-id <id> --acknowledge-reset [--paper <dir>]` | The explicit operator acknowledgement that clears a spent ledger — compiles nothing, never combined with a compile in the same call | (none beyond `render`'s own) |
| `place --figure-id <id> --pdf <path> --provenance <path> [--paper <dir>]` | Places an already-measured figure's PDF — compiles nothing, requires a provenance record naming the run that produced it, and measures the PDF first (`paper_place.py`, the same rules `figure-review measure` reports): a plot carries a text layer, no full-page background, no margin wider than 4 pt, no in-figure title, and every text span prints between 0.70 and 0.90 x the body at the provenance's `printedWidthFraction` of `\textwidth` (1.0 by default; `figureKind: image` exempts a photograph from the text-layer rule only). No override: the fix is the figure or its declared width. With a built venue (`paper/venues/<slug>/` holding `build.json` and `main.tex`) the output adds `venueWarnings`: the same floor measured at the same `printedWidthFraction` on each built venue's page (its own body size and `\textwidth`, read from the venue `main.tex`), one entry per venue the figure prints below 0.70 x that body or wider than that text, each with `issues`, `detail` and the `remedy` (the body size and printed width to redraw at). A warning never refuses; with no built venue the output is unchanged | `DIAGRAM_SOURCE_ABSENT` (reused: the named artifact this call needs is absent), `FIGURE_PDF_UNREADABLE`, `FIGURE_PROVENANCE_INVALID`, `FIGURE_MEASUREMENT_UNAVAILABLE`, `FIGURE_NO_TEXT_LAYER`, `FIGURE_FULL_PAGE_BACKGROUND`, `FIGURE_MARGIN_WASTE`, `FIGURE_IN_FIGURE_TITLE`, `FIGURE_TEXT_BELOW_PRINT_FLOOR`, `FIGURE_TEXT_ABOVE_PRINT_CAP` |
| `figure optimize --figure-id <id> [--in-place \| --output <path>] [--strip-comments] [--no-compile] [--paper <dir>]` | Rewrites one diagram's TikZ source: prunes the libraries it can **prove** unused, adds the ones it detects as missing, factors repeated option lists into one `\tikzset`, then compiles the candidate and commits it only on a `success` verdict. `background=2pt` headers, relative positioning, and `% node:` markers are preserved by construction | `DIAGRAM_SOURCE_ABSENT`, `DIAGRAM_PLOTS_DATA`, `MANIFEST_SOURCE_MISMATCH`, `LATEX_TOOLCHAIN_ABSENT`, `LATEX_PACKAGE_ABSENT`, `LATEX_OUTCOME_UNEXPLAINED` |
| `figure optimize --file <path.tex> [--strip-comments]` | Dry run: prints the optimized candidate for one source path and writes nothing (no manifest, so no cross-check applies) | `DIAGRAM_SOURCE_ABSENT` |
| `figure provenance --figure-id <id> --script <path> [--input <path> ...] [--paper <dir>]` | Records the generating script and every data input in `<id>.diagram.json`'s `provenance` key, each as a repository-relative path with its sha256, replacing an earlier record and keeping every other key; checks every path before writing, so a refusal leaves the manifest byte-identical | `DIAGRAM_SOURCE_ABSENT` (no manifest), `PAPER_OUTSIDE_REPOSITORY`, `TARGET_UNREADABLE` |
| `figure audit --figure-id <id> --section <id> [--block <id>] [--sections <dir>] [--paper <dir>]` | Compares the manifest's declared components — **not** every `\node{}` string — against the section prose (the contract body plus the section's own `<section>.*` blocks in `paper/main.tex`; an absent or unparseable `main.tex` leaves the contract body alone), and the `components_from` fact's list against both. Emits `verdict` (`pass`/`fail`/`unmeasured`) plus `unmatched_nodes`, `missing_pipeline_steps`, `label_mismatches`, `warnings`, `remediation`, `provenanceWarnings` (advisory, never changes the verdict), and writes `figure_audit.json` beside the figure's ledger | `DIAGRAM_SOURCE_ABSENT`, `SECTION_CONTRACTS_UNREADABLE`, `SECTION_UNKNOWN`, `BLOCK_ABSENT` |
| `figure audit --file <path.tex> --manifest <path.json> --section <id> [--block <id>]` | The same audit for a figure outside `paper/Figures/`; `--file` requires `--manifest` | as above |

**`figure optimize`'s two guards run even under `--no-compile`.** The manifest
cross-check and stop A are pure text checks, independent of the compiler, so
the shortcut skips the compiler and nothing else; a candidate failing either is
discarded with the original left byte-identical. A repairable compile failure
is likewise an ordinary outcome, not a refusal: the call returns `status: ok`
with `verdict: "rolled_back"` and the diagnostics. A library `optimize` cannot
recognize it never removes — it only prunes what it can prove unused.

**`figure audit`'s findings are a verdict, never a refusal.** A `fail` is a
successful call (`status: ok`, `verdict: fail`), the same way `render` treats a
repairable compile failure as the loop's ordinary cost. `unmeasured` exists so
"could not check" never reads as "checked and clean": a figure whose contract
declares no `components_from`, or a call that omits `--block`, reports
`unmeasured` rather than a vacuous pass.

**Every successful compile is audited at print size.** `render` runs the
shared diagram audit (`skills/_core/figure/diagram_audit.py`, the same one
`experiment-diagrams` runs) on the compiled PDF, its log and its source:
no `Overfull \hbox`/`\vbox` in the log; no relative size switch
(`\tiny` ... `\Huge`, `\small`, `\footnotesize`) — every size is an
explicit `\fontsize{<pt>}{<1.2 pt>}\selectfont`; no two text spans
intersecting and no span crossing a drawn frame it is not inside; every
span printing between 0.70 and 0.90 x the manuscript body size (`paper/main.tex`'s
class option, 10 pt without one) once the figure is scaled to its declared
inclusion width — the manifest's optional `widthFraction` (the
`width=<f>\textwidth` its `\includegraphics` uses, 1.0 by default) and
`textWidthPt` (by default the width `paper/main.tex`'s `geometry` margins
leave, else the A4 article width for the body size); and no
background canvas or content margin wider than 4 pt. A failing audit is a
repairable `failure` like any other: it spends one attempt, returns the
`audit` and one diagnostic per finding, and leaves the PDF in scratch
(`preview`) instead of `Figures/<id>.pdf`. Size each font for the width
the figure prints at (`diagram_audit.role_font_pt(body_pt, scale)` gives
the sizes per role); when a label does not fit, shorten it or widen its
box, never shrink the font. `figure optimize` reports a relative switch as
a warning before a compile is spent.

**A repairable failure is an ordinary outcome, not a refusal.** `render`
returns `"status": "ok"`, `"verdict": "failure"` with the parsed
diagnostics and `attemptsUsed`/`budgetRemaining` for a compile that failed
but is still within its four-attempt budget — spending an attempt is the
loop's ordinary cost. Only the fifth attempt for an id refuses
`REPAIR_BUDGET_SPENT`, naming every distinct diagnostic and source digest
already tried; the budget survives edits between attempts (keyed to the id
alone, never reset by a new digest) and is cleared only by an explicit
operator acknowledgement (deleting the ledger file — `paper/.paper-writing/
figures/<id>/ledger.json` — **is** that acknowledgement, made explicit
rather than pretended-secure). A missing `.sty` refuses
`LATEX_PACKAGE_ABSENT` and spends nothing: redrawing cannot fix an absent
package.
