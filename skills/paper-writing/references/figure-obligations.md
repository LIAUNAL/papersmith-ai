## A diagram that compiles, or says why: `render` and `place` (the data-figure boundary, obligations and figure delegations)

**The data-figure boundary, measured, not assumed.** Stop A
(`paper_figure.scan_data_boundary`) refuses `DIAGRAM_PLOTS_DATA`
pre-compile on a plotting package, a `\begin{axis}`, an external table
read, an `\input`/`\include` escaping `paper/Figures/`, or an embedded
coordinate series over the illustrative threshold. Stop B is the compile's
own sandbox (`cwd` = `paper/Figures/`, `-outdir` = scratch, child env
carrying `openin_any=p`/`openout_any=p`/`shell_escape=f`) — **measured
against a real TeX Live 2026 install, not merely declared**: `shell_escape=f`
genuinely blocks `\write18`, but `openin_any=p` does **not** block a literal
absolute-path `\input{...}` on this engine (an explicit absolute path never
goes through kpathsea's search algorithm at all). Stop A's pre-compile
source scan is therefore the primary, load-bearing defense against that
exact vector — never something resting on the env var alone. Placing a
measured figure is `place`, entirely outside the compile path: no
`latexmk` call, no ledger, no stop-A scan.

**Obligations are read, never known.** A block's `figure:` declaration
(`ordered`, `excludes`, `caption_enumerates`, `caption_decodes`,
`mandatory` — all five required; `components_from` OPTIONAL,
`paper_contract.py`'s `_parse_figure`) is read entirely off the contract;
`paper_obligation.py`'s pure functions (`check_components`,
`check_excluded`, `check_shared_components`, `check_caption`,
`check_mandatory`) check it against a manifest, never against a hardcoded
section or block id. When `components_from` names a fact, the Components
Check's expected list is DERIVED — never operator-supplied. A declared
fact reads its own declared resolution (`declare --fact <id> --value
'["a", "b"]'`, read back through `paper_declarations.read_fact`). A
produced fact (`contributions`, produced by
`materials-and-methods.mm-proposal`) reads its producer block's own text in
`main.tex`, in either of the two forms the methods contract admits for the
list: the `\item` roster, one line per element; or, when the block holds
no `\item` line at all, one `\subsection` per element, its printed title
naming it, in order (`\subsection*` counts; `\subsection[short]{long}`
yields the long title; whitespace inside a title collapses to one space;
`\subsubsection` and `%`-commented headings never count). A roster present
beside subsections is the list — the contract's "one that carries them all
and closes on the roster" has both — and whether a roster merely repeats
subsections is that contract's disqualifier, for `contract-auditor` to
judge. It refuses `COMPONENTS_FACT_UNRESOLVED` when the fact was never
declared (or its producer is not written yet) and
`COMPONENTS_FACT_NOT_A_LIST` when a declared resolution does not parse as a
JSON array of strings, or a producer block yields neither `\item` lines nor
`\subsection` titles. `figure audit --block` resolves its expected list
through the same route. `components_from`'s named fact must equal the FULL
expected list by contract — section 01's methods diagram IS the
contribution list, so `components_from: contributions` alone suffices. A
block whose diagram is a composite crossing over several categories of
content, none of which alone is the full list (section 02's closing
diagram: data, methods, axes, metrics, qualitative instruments, the
repetition unit), declares NO `components_from` at all — the Components
Check simply does not run for it, honestly, rather than being wired to one
fact's partial value and silently inverting (measured directly by
`a-diagram-that-compiles-or-says-why`'s own corrective verify: the prior
`components_from: dataset` reading refused a prose-compliant diagram and
passed a degenerate one). Deleting a `figure:` key removes the whole
obligation with zero code changed. A block whose contract states the
synthesis artefact may be a diagram **or** a table (section 05's block 5)
carries no diagram obligation at all when the operator's choice leaves no
`<id>.tex` — a legal table triggers nothing.

**Drafting the diagram itself delegates to the `diagram-author` agent.**
It authors the `.tex`/`.diagram.json` pair and drives its own `render`
loop up to the repair budget, stopping at `REPAIR_BUDGET_SPENT` or an
unrecoverable refusal for the operator to resolve — it never clears a spent
ledger itself. For the figure that closes Materials and Methods, the agent first
reads `skills/paper-writing/references/contribution-diagram.md`: the parts that
figure summarizes (inputs as mathematical objects, representation, core stages,
numbered contribution panels with their equations, losses and total objective,
outputs, legend), its visual grammar and its size budget.

**Auditing a diagram against its own prose delegates to the `figure-auditor` agent.**
It runs `figure audit` and reports that JSON as the authoritative
semantic verdict, and measures whether the visual half (overlaps, legibility,
out-of-bounds text) is answerable by running `figure-review probe` and
quoting its exit — bounding those dimensions to the `figure-review` skill's
checklist when the probe resolves a rasterizer link, and reporting them
`unmeasured` quoting the probe's own refusal code when it does not — and
checks typographic parity between the figure's preamble and the paper's own
font setup. It never repairs the figure and never reports a visual verdict it
did not measure.

**Judging a rendered diagram by eye delegates to the `figure-visual-reviewer` agent.**
After `render` reports `success` (its audit reads `pass`), one read-only
pass over a preview of at most 1400 px judges what no script can: legibility
at print scale, centring and balance, overlaps and crowding a reader would
see, and whether labels and arrows read correctly. It returns `PASS`, or
`FAIL` with concrete fixes for `diagram-author`, and adds an `UNCERTAINTY:`
line instead of failing when it cannot decide. It never edits anything and
runs once per drawing.

**Measure this before delegating (figure-visual-reviewer):** confirm
`render`'s last reply for the id reads `"verdict": "success"` with
`audit.verdict` `pass` and that `paper/Figures/<id>.pdf` exists; a visual
pass over a figure the mechanical audit already fails spends a model call
on what the diagnostics already say.

**Measure this before delegating (figure-auditor):** confirm the block's
`figure:` declaration is readable (`contract --file <path>`) and that the
figure's `<id>.tex` and `<id>.diagram.json` both exist; an agent asked to audit
a figure it cannot read cannot distinguish "clean" from "unreadable."

**On a harness with no Task-tool delegation** (OpenCode projects these
agents as `mode: subagent` per `OPENCODE.md`, Antigravity reads them from
`.agents/agents/` per `.agents/AGENTS.md`, and Pi reads its projection only
when the third-party `pi-subagents` package is installed per
`.pi/APPEND_SYSTEM.md`; a Pi session without that package, or any session
whose agent is not registered, has none):
run this stretch in-process, as one step, in the same order, holding to the
same measure-before-delegating gate before starting. The tool boundary the
agent would have enforced (`figure-auditor` cannot write to disk) becomes
the orchestrator's own discipline to hold, not a structural guarantee —
treat any action that would have needed a scoped-out tool as a stop, not a
workaround.
