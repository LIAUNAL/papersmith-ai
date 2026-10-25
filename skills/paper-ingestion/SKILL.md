---
name: paper-ingestion
description: "Trigger: ingest reference PDFs into high-fidelity Markdown (LaTeX equations, Markdown tables, figures as files), locally and keyless, routing each page to a fast text-layer path or to Docling only when it needs it. License-unrestricted engines. One folder per paper: pdf + lean .md + .json page map + figure images."
---

# Paper Ingestion

Convert each source PDF into a lean, high-fidelity Markdown file an agent can
read directly — body text in reading order, equations as LaTeX, tables as
Markdown. Each paper becomes a **self-contained folder**: `pdf + md + figure
images`. Figures are separate image files the `.md` references (loaded on demand,
not embedded), and the references/bibliography section is dropped. Runs locally
with no API keys.

**PDFs only.** Neither this skill nor `smith ingest` (its workspace
bridge) reads Markdown, text or HTML; `smith ingest` refuses any other
source and names the two routes that do. Material that is already text goes
through `proposal-deliberation` instead: Markdown a new proposal should be
seeded from goes under `guidance/paper-guide/` (`CREATE_INITIAL_REVISION`
reads it), and an existing draft that should become v1 as written goes into
`proposals/` and is adopted with `ADOPT_INITIAL_REVISION`.

## The objective flow

**Why this skill was invoked, and where it has to arrive.** Declared here and in
`OBJECTIVE_FLOW`, held equal by a test, and independent of what is on disk. A
listing of what has been ingested answers *where am I*; this answers *what is
this for*, which no listing implies. The one path a refusal takes carries it.

**Purpose:** turn a paper into the form it can actually be used in — equations
as LaTeX, tables as tables, figures as files — not a PDF that was processed.

| Stage | Establishes | Behind you when |
| --- | --- | --- |
| `filed` | The PDF sits inside a topic folder of its own, which is what makes it a paper rather than a download | it is no longer reported among the unfiled |
| `extracted` | The Markdown exists beside it, with its figures written as files rather than left inside the page | the paper folder holds the document and its images |
| `readable` | The equations are LaTeX and the tables are Markdown, so a later reader can quote a formula rather than describe a picture of one | this is the arrival; it is behind nobody |

**Arrival:** a document a person can read and a later session can cite, which a PDF is not.

**Arrival is an artefact somebody can read and cite, never a PDF that was
processed.** That distinction is this skill's whole reason to exist: a PDF is
already on disk and already unusable as evidence — its equations are pictures,
its tables are ink, and nothing downstream can quote it.

**No stop here is a person's**, and the list says so by being empty rather than
absent: ingestion asks nobody, and a reader meeting a missing key would have to
guess whether that meant none or meant nobody wrote it down.



## What this skill delegates, and to whom

Extraction is one stretch and it runs in an agent of its own. What stays in the
conversation is the part that needs a person: which loose PDFs are unfiled, and
what the report says afterwards.

| Stretch | Delegated to | Begins after | Ends at | Measure this before delegating |
| --- | --- | --- | --- | --- |
| Extract | this skill delegates to the `paper-ingestion` agent | the PDFs to ingest are named | the artefacts a person can read and cite | each named PDF sits inside a topic folder of its own; a loose one is the operator's to file and not this stretch's to guess at |

What moves is execution, never doctrine: every rule stays here, and the agent's
first instruction is to load this file.

## When a delegated agent cannot be spawned

The stretch this skill delegates is defined in full by its agent file:
`.claude/agents/paper-ingestion.md`. When that agent cannot be spawned — the
harness has no sub-agent mechanism, the agent is not registered in this
session, or the spawn itself fails — perform the stretch inline: read the
definition file and follow it as written, from the beginning it states to the
end it states, holding any gate this skill sets before the stretch, and returning the
report shape it specifies. Its `tools:` line still bounds the stretch: an act
that would need a tool outside that list is a stop, not a workaround. Say in
the reply that the stretch ran inline and why the agent could not be spawned.

## Activation Contract

Accept an optional loose PDF path, or discover the source roots from
`papersmith.yaml` and scan them. Validate configuration before doing any work.
Extraction is performed by the bundled script running inside the skill's
dedicated virtualenv.

## Engines, routing and licenses

The default engine, `auto`, decides **page by page** (`scripts/pdf_pipeline.py`),
loading no model to decide:

| Page | Route | Engine |
| --- | --- | --- |
| digital prose (inline math reads as Unicode) | `text` | pypdfium2, milliseconds per page |
| no text and no page-sized image | `empty` | pypdfium2 |
| a display equation (a line set mostly in math fonts) | `math` | Docling + formula model → LaTeX |
| a table caption or numeric rows | `table` | Docling + TableFormer (fast mode) |
| an image and no text layer | `scan` | Docling + RapidOCR |

Consecutive heavy pages go to Docling in one call, through its page range, and
table structure and OCR run only on the pages that need them. Every page is
cached under `.papersmith/cache/ingestion/`, keyed by the PDF's SHA-256, the
route, the engine version and its options; an entry records the hashes of its
Markdown and figures and is re-checked before use (`--verify-cache` checks them
all). Re-ingesting a paper, or the same PDF fetched again under another name,
converts nothing twice. A page Docling fails on inside a run is never cached
empty: it is read on the fast path and its sidecar row says so, and the next
run converts it again.

The formula model depends on the hardware, because on the wrong device it is
unusable: Granite-Docling-258M on MLX on Apple Silicon (7 s for a page of six
equations), CodeFormulaV2 on CUDA. On a CPU-only machine it takes about 40 s per
formula, so math pages stay on the fast path there unless `formulas_on_cpu: true`.
When Docling is not installed (`--no-ingestion`), `auto` reads every page on the
fast path and says so; `engine: docling` refuses instead.

**Every default engine is license-unrestricted** — no copyleft and no revenue or
user threshold: pypdfium2 (Apache-2.0 / BSD-3-Clause; PDFium BSD), Docling and
docling-core/-parse/-ibm-models (MIT), docling-layout-heron (Apache-2.0),
Granite-Docling-258M (Apache-2.0), CodeFormulaV2 (CDLA-Permissive-2.0), RapidOCR
(Apache-2.0), mlx / mlx-vlm (MIT). `engine: marker` remains as an explicit
opt-in: its code is Apache-2.0 but its model weights use a modified OpenRAIL-M
license, free only for research, personal use and organizations under USD 5M in
funding or revenue; the run prints that notice. MinerU was ruled out for the
same reason (a license required above USD 20M monthly revenue or 100M MAU).

Measured on Apple Silicon (arXiv 1706.03762, 15 pages; 1312.6114, 14 pages),
warm models: `auto` 21.5 s and 28.6 s, with 7 and 10 pages on Docling; Marker
`fast` 6.8 s and 28.2 s. `auto` returned more display equations as LaTeX (6 and
30, against Marker's 1 and 23). A cached re-ingestion took 0.2 s.

## Environment (one-time)

The engines live in an isolated micromamba environment
(`papersmith`) so it never pollutes system Python. A new machine is provisioned
with one idempotent command that works on macOS, Linux, and Windows:

```
python scripts/setup_env.py install
# or, on macOS/Linux: ./skills/paper-ingestion/setup.sh
```

The provisioner installs both dependency kinds a `requirements.txt` alone cannot:

- **Python deps** (`requirements.txt`): `pypdfium2` (the fast path, from
  conda-forge with the base packages, so it is always there), `docling` (the heavy
  pages), `mlx-vlm` on Apple Silicon, `PyYAML` — plus `pytorch`/`torchvision`,
  `numpy`, `jsonschema` and `kagglesdk` from conda-forge.
- **Marker, opt-in only**: `pip install marker-pdf==2.0.0` inside the environment
  (see the license note above); its OCR backend `llama-server` still comes from
  conda-forge's `llama.cpp`.

The script detects the hardware and installs the matching PyTorch build:
`pytorch-gpu` when an NVIDIA GPU is present, `pytorch-cpu` otherwise. Override the
choice with `--cpu` or `--cuda`. Skip the heavy ingestion engine with `--no-ingestion`
(the pypdfium2 fast path stays, so digital PDFs still ingest),
and tear everything down with `python scripts/setup_env.py clean` (`--full`
also removes the bootstrapped micromamba).

Requirements: Python 3.10+ to run the provisioner itself; micromamba is
downloaded automatically if missing.

**No `.env` / no keys.** Ingestion is fully keyless — the only runtime env var,
`PYTORCH_ENABLE_MPS_FALLBACK=1` (Apple Silicon), is set by the script itself. To
point at a llama.cpp outside the environment, export `LLAMA_CPP_BINARY`.

## How to execute

Always invoke through the environment:

```
micromamba run -n papersmith python \
  skills/paper-ingestion/scripts/extract_pdf.py [--list] [--engine {auto,pdfium,docling,marker}] [--mode {fast,balanced}] [--force-ocr] [--no-cache] [<loose-pdf>…]
```

- `--list`: report the pending loose PDFs and exit. Loads no model, moves no file.
- No argument: discover the source roots, then ingest every **loose** PDF in them.
- `<loose-pdf>…`: ingest exactly those loose PDFs.
- `--file <pdf> --into <topic>`: file one unfiled PDF into a topic folder under the
  base, creating it when new. Moves one file, converts nothing, loads no model.
- `--mode {fast,balanced}`: override the configured `mode` for this run.
- `--force-ocr`: OCR every page instead of reading the PDF's text layer, for this
  run. See [Tables from a poor text layer](#tables-from-a-poor-text-layer).
- `--engine {auto,pdfium,docling,marker}`: override the configured engine for this
  run. `pdfium` keeps every page on the fast path and loads no model.
- `--no-cache`: convert every page again and store nothing.
- `--verify-cache`: re-check every cached page against its recorded hashes and exit
  (`1` when any fails); ingests nothing.

## Confirmation (required)

**Never ingest without asking first.** Ingestion *moves* the user's PDFs, so
discovery and execution are two separate steps:

1. Run with `--list`. This is free — it loads no model, so asking costs nothing.
2. Report what was found: each paper's path and page count.
3. Ask the user **which papers to ingest**, as a multi-select over the listed
   PDFs. Never assume the whole batch is wanted; a PDF may be sitting in a
   source root by accident, and ingesting it displaces it.
4. Run again passing only the approved paths as arguments. If the user approves
   nothing, stop and ingest nothing.

Running with no argument ingests everything unattended and therefore skips the
user's decision — use it only when the user has explicitly asked for exactly
that. The one loose PDF case is not an exception: one paper still gets moved,
so one paper still gets confirmed.

## A PDF in the base belongs to no topic yet, and nothing files it for you

The base's children are topics. A PDF dropped in the base itself, beside those
folders rather than inside one, is pending and invisible at the same time:
discovery only promotes children, so nothing finds it and the run reports that
every paper is already in its folder.

The script reports these separately and **ingests none of them**. Converting one
where it lies would make it a topic of its own, and the next run would read that
folder as already ingested and leave it there permanently — a stray paper turned
into a permanent category, silently.

So it is a question, not a default:

1. Report each unfiled PDF with its page count, and the topics that exist now.
2. **Ask which topic it belongs in** — one of the existing ones, or a new one
   whose name the user gives. Never pick for them: the topics are the user's
   filing system and the paper's subject is not something to infer from a
   filename.
3. Run `--file <pdf> --into <topic>` with the answer. The PDF lands loose inside
   that topic, which makes it ordinary pending work.
4. Then the normal confirmation applies — filing is not ingestion, and moving a
   paper into a folder never authorizes converting it.

If the user does not want to file it, leave it. It stays reported on every run,
which is the correct end state for a decision nobody has made yet.

**Loose PDF = not yet ingested.** A PDF sitting directly in a source root is
pending; once ingested it lives inside its own `<stem>/` folder, so it is no
longer loose and is skipped. To re-ingest, delete the paper's folder (leaving the
PDF loose) and run again — that deletion is the only forced re-ingestion path,
because an existing non-empty `<stem>/` folder is refused rather than merged
into.

The first page that needs Docling downloads its models (layout, TableFormer, the
formula model; about 1 GB with the MLX formula model), cached thereafter. A paper
with no heavy page loads no model at all.

## Failure Semantics

Ingestion is **transactional per paper**. Conversion runs in a staging directory
beside the paper and the PDF is moved in only once its `.md` and figures exist.
A paper that fails to convert stays **loose**, so the next run retries it — a
failure never leaves a PDF stranded in a folder with no `.md`, which the next
run would read as "already ingested".

Exit codes: `0` success or nothing to do, `1` at least one paper failed (the
rest were still ingested), `2` configuration, argument, or environment error —
nothing was touched.

## Output Contract

For a loose `<root>/foo.pdf`, produce `<root>/foo/` containing:

- `foo.pdf` — the source PDF, moved in.
- `foo.md` — lean Markdown: text, LaTeX equations, Markdown tables. The
  references/bibliography section is stripped. Figures are **referenced**
  (`![](_page_4_Figure_2.jpeg)`), not embedded.
- `foo.json` — the page map (`schema: papersmith.ingestion/v1`): the PDF's SHA-256;
  per page its route, the reason, the engine that read it, whether it came from the
  cache, and its character range in the `.md`; headings, display equations (LaTeX)
  and figures with their page; the references **kept here by page** even though
  the `.md` drops them; the engines and versions; timings.
- the figure image files the `.md` references, flat in the same folder.

Each page's block in the `.md` opens with `<!-- page N -->`. No `normalized/`, no
base64, no manifest.

## Reading part of a paper

`scripts/pdf_fragment.py` answers with one piece of an ingested paper, never the
whole document, from its `.json` map (stdlib only, read-only):

```
python skills/paper-ingestion/scripts/pdf_fragment.py guidance/<topic>/<paper> \
  {--page N | --heading TEXT | --equation K | --search TEXT | --outline} [--max-chars 6000] [--json]
```

Exit `0` found, `1` nothing matched, `2` usage error or unreadable paper. Agents
reach the same through the MCP tool `papersmith.ingest_fragment` (read-only).

## Configuration (`papersmith.yaml`)

```yaml
paper_ingestion:
  engine: auto            # auto | pdfium | docling | marker (opt-in, see licenses)
  mode: fast              # fast: route pages | balanced: every page through Docling
  formulas_on_cpu: false  # optional: run the formula model on a CPU-only machine (slow)
  cache: true             # optional: per-page cache keyed by the PDF's SHA-256
  strip_references: true  # drop the references/bibliography section at the end
  force_ocr: false        # optional: OCR every page, never read the PDF's text layer
  source_base: guidance   # source roots are discovered under here, every run
  source_roots: []        # optional: extra roots outside source_base
```

## Source Root Discovery

Source roots are **rediscovered on every run**. A folder directly under
`source_base` becomes a source root when it holds at least one loose PDF. So
adding a new category of papers (e.g. a `guidance/datasets/` folder for papers
describing the research dataset) is just: create the folder, drop the PDFs in,
run. No configuration edit.

Two boundaries make that safe:

- **A loose PDF is required.** Ingestion *moves* files. Requiring a PDF you put
  there yourself is what keeps an unrelated folder under the base from ever
  being touched.
- **Exactly one level down.** A folder nested inside a source root is never
  scanned, because a subfolder means "paper already ingested". `guidance/` itself
  is a container of roots, not a root: loose PDFs sitting directly in it are
  ignored.

A folder holding only already-ingested papers is not a new root — its PDFs are
not loose — and is correctly left alone.

`source_roots` still works for roots that live outside `source_base`; explicit
entries are added to whatever was discovered. A `source_base` that is not a
folder is a configuration error, not an empty discovery.

## Fidelity & Verification

This skill **interprets** content for maximum fidelity — it reconstructs
equations as LaTeX and tables as Markdown cells. That interpretation can be
wrong (a misread digit, a garbled symbol). The source PDF sits in the same
folder as the `.md`: verify anything load-bearing against it, and the `.json`
says which engine read each page. Prefer `balanced` mode when fidelity matters
more than speed. Known limits of the fast path: inline mathematics reads as
Unicode, a vector figure (drawn, not embedded as an image) is not written as a
file, and a table the probe missed reads as text lines.

### Tables from a poor text layer

With `engine: auto`, `--force-ocr` sends every page to Docling with RapidOCR.
With `engine: marker`: in **both** modes Marker rebuilds a digital table from the PDF's own text layer
(`tables_pdftext`) and falls back to OCR only when its reconstruction scores low.
A text layer that is present but poor — split ligatures, interleaved columns, a
broken font map — therefore yields a table that is confidently wrong, and
switching `mode` does not avoid it. `--force-ocr` (or `force_ocr: true` in the
configuration, for every run) hands Marker its `force_ocr` option: no text layer
is extracted, and every page, tables included, is rebuilt by OCR. It is slower and
off by default, because a good text layer is exact and OCR is not. To redo one
paper this way, delete its folder (leaving the PDF loose) and ingest it again with
the flag.

## Decision Gates

| Situation | Action |
| --- | --- |
| Malformed/missing configuration | Report the error; do nothing |
| `source_base` set to something that is not a folder | Report the error; do nothing |
| Neither `source_base` nor `source_roots` configured | Report the error; do nothing |
| A folder under `source_base` with no loose PDF | Not a source root; leave it untouched |
| Unknown `engine`/`mode`, or a value of the wrong type (`strip_references`/`force_ocr`/`cache`/`formulas_on_cpu` not a boolean) | Report the error before loading the engine; do nothing |
| Loose PDFs present | List them, ask which to ingest, ingest only those |
| User approves a subset | Ingest exactly the approved paths; leave the rest loose |
| User approves nothing | Stop; move no file |
| No loose PDFs (all in folders) | Report nothing to do; do not re-ingest |
| Argument that is missing, not a PDF, a directory, or already ingested | Refuse before loading the engine; move nothing |
| A paper's `<stem>/` folder already exists and is not empty | Refuse that paper; say to delete the folder to re-ingest |
| pypdfium2 missing, or the named engine (`docling`, `marker`) not installed | Report it and point at `setup.sh`; move nothing |
| `engine: auto` and Docling not installed | Read every page on the fast path; say so on stderr and in the `.json` |
| A single file fails | Report that file; leave it loose; continue with the rest |

## Output Reporting

On success, emit only a brief confirmation of which papers were ingested. On
error, report only the error. No config dumps, path listings, or per-page tables.

**Speak the user's language.** Everything addressed to the user — the pending
list, the confirmation question and its options, the success or error report —
goes in the language the user is writing in, not in the language of this
document. The script's own stdout stays English: it is data to read, not a
message to relay verbatim. Paths, filenames, flags, and exit codes are never
translated.
