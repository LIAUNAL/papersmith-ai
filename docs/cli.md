# The CLI commands

Moved out of the README (#79). `smith --help` and `smith <command> --help` are the source of truth; this page explains each command. Back to the [README](../README.md).

Every command runs as `papersmith <command> [options] [<dir>]`. `<dir>` defaults
to the current directory and has to point at an initialized workspace, except for
`init`. Global flag: `--version`.

| Command | What it does |
|---------|----------|
| `init` | Creates a standalone research workspace |
| `upgrade` | Syncs the framework's scaffolding while preserving the research |
| `status` | Reports workspace health, proposals, runs and inbox |
| `ingest` | Ingests a literature PDF or URL into Markdown |
| `deliberate` | Talks to the `proposal-deliberation` engine |
| `implement` | Delegates to the `proposal-implementation` harness |
| `run` | Runs a compute profile (local / Kaggle / Slurm) |
| `remote` | Packs, pushes and follows remote jobs directly |
| `target` | Lists, selects and checks compute targets |
| `audit` | Audits the structure and detects drift in what was generated |
| `ui` | Serves the local Paper Command Center (DAG, gates, sections, wiring) |
| `mcp` | Exposes the orchestrator and the paper verbs over Model Context Protocol |

### `smith init [<dir>]`

```bash
smith init ~/papers/sparse-ae \
  --title "Sparse Autoencoder Audit" \
  --topic "mechanistic interpretability" \
  --remote kaggle
```

| Flag | Effect |
|------|--------|
| `--title TEXT` | Paper title, written into the workspace documents |
| `--topic TEXT` | Research topic |
| `--tools TEXT` | Runtimes to provision, comma-separated |
| `--remote {kaggle,local,slurm}` | Default compute target (default: `kaggle`) |
| `<dir>` | Where the workspace goes; omitted, it is the current directory (`smith init` alone sets up the folder you are in, on every operating system) |
| `--import-existing` | Explicitly initialize a nonempty directory while preserving existing files: keeps its `README.md`, merges papersmith's block into its `.gitignore`, and refuses any other file or symlink collision before copying |
| `--no-npm` | Skips the best-effort `npm install` (offline/hermetic use) |
| `--no-env` | Skips provisioning the workspace's Python environment; `smith ui` refuses until `python3 scripts/setup_env.py install` is run |
| `--progress` | Forces a plain-text progress log with an estimate of the time left; useful in CI, where the bar is noise and the log is what matters |
| `--no-progress` | Draws no progress even when the output is a terminal |
| `--allow-dirty-kit` | Initializes even when the kit has uncommitted changes in its distributed paths, or when its git state cannot be read; the workspace records that it came from such a kit (see [Kit provenance](#kit-provenance)) |

By default `smith init` refuses a nonempty destination. For a directory with
existing research files, use `smith init <dir> --import-existing` (or
`smith init --import-existing` from inside it): it scaffolds alongside them.
Two root files nearly every repository has are not collisions: an existing
`README.md` is kept as it is, and an existing `.gitignore` keeps every line and
gains papersmith's managed block on top (the same merge `smith upgrade` does).
Any other existing generated path (`CLAUDE.md`, a `.gitkeep`, `package.json`…)
is refused rather than replaced. It is not an upgrade of an existing
Papersmith workspace; use `smith upgrade` for that. The merge requires filesystem
support for no-follow, directory-relative operations and fails closed if it is
unavailable. A failed merge attempts to remove only scaffold paths it can still
identify; concurrent directory moves or later npm/environment provisioning may
leave new artifacts requiring manual cleanup. Filesystem races and external
installers mean this is not an atomic transaction or a guarantee against other
processes changing the destination.

The step that dominates the run is environment provisioning, and until 0.9.0 it
ran with its output captured: several minutes with no signal at all. `init` now
draws a bar with an estimate of the time left on a terminal, and prints the log of
the two child processes it runs. The estimate starts from declared values and
recalibrates against the pace the run itself measures; a step that overruns its
share moves the number up rather than contradicting itself. When the output is not
a terminal — a pipe, the MCP server, the suite — nothing is printed, so a stream
another program is reading stays clean.

Creates `.papersmith/`, `guidance/{paper-guide,reference-papers,data-paper}/`,
`proposals/`, `paper/`, `experiments/`, `implementations/`, `kaggle-inbox/`,
plus the kit copy and its manifest. The full shape of the tree is in
[Inside the workspace](../README.md#inside-the-workspace).

### `smith upgrade [<dir>]`

```bash
smith upgrade ~/papers/sparse-ae
```

| Flag | Effect |
|------|--------|
| `--tools TEXT` | Replaces the active runtime generators |
| `--force` | Forces framework files to be written |
| `--allow-downgrade` | Allows installing a framework version older than the one the workspace records |
| `--no-migrate` | Syncs the framework files without migrating artifacts; the recorded version does not advance |
| `--plan-migrations` | Reports the pending artifact migrations and exits without writing anything |
| `--allow-dirty-kit` | Syncs even when the kit has uncommitted changes or an unreadable git state; the workspace records it |

It only touches files the framework manages — never `guidance/`,
`proposals/`, `paper/`, `experiments/`, `implementations/`, `kaggle-inbox/`,
`papersmith.yaml`, `package.json`, `README.md` or the `.env*` files.
Against a kit checkout without reinstalling:
`PAPERSMITH_KIT_ROOT=/path/to/papersmith-ai smith upgrade <dir>`.

#### Kit provenance

Since 0.14.0, `init` and every `upgrade` write `.papersmith/kit-source.json`:
the framework version, the commit the kit came from, whether it had uncommitted
changes (`dirty`) and where the CLI resolved it from (`checkout`, `bundled` or
`override`). `smith status` shows it on the `Kit source:` line. A workspace
created before 0.14.0 does not have it and `status` says
`unknown (recorded before 0.14.0)`; the next `upgrade` writes it, so no
migration is needed.

With an editable install (`pipx install -e`) the kit is the live checkout,
uncommitted edits included. That is why `init` and `upgrade` refuse, before
writing a byte, when the paths the kit distributes (`skills/`, `sections/`,
`.claude/agents/`, the provisioning scripts, `requirements.txt` and
`src/papersmith/`) have changes or untracked files, and also when the kit's git
state cannot be determined (no `git`, the tree is not a repository): unknown is
treated as dirty, not as clean. Commit or stash the changes, or repeat with
`--allow-dirty-kit`; the record then carries `allowedDirty: true`. The bundled
kit of a wheel install records the commit `scripts/build-kit.py` captured when
it was built; a kit built from a dirty tree is refused too. If that kit carries
no provenance (it was built before 0.14.0 or without git), it is admitted with
the commit unknown, because its bytes are a frozen copy, not live edits. The
variable `PAPERSMITH_ALLOW_DIRTY_KIT=1` is equivalent to the flag; it exists for
the test suite, which runs from a checkout that is almost always dirty.

#### Artifact migrations

Syncing files is not enough. A release can change the shape of an artifact the
workspace already produced, and the new scaffolding is then left reading old
state with nothing to notice. That is why `upgrade` runs artifact migrations in
a single place: after copying the kit, because a migration may need the scripts
and assets of the release that just arrived, and before writing
`.papersmith/version`.

One rule with no exceptions follows from that order. **The recorded version
advances when that version's migrations are done.** If one fails, the marker
stays where it was, the command exits non-zero and the next run retries.
`--no-migrate` does not move the marker either when something was left pending:
advancing it there would turn the flag into a way of recording a release the
artifacts never reached, and `status`'s `version_match` would report that as
agreement.

The manifest is the opposite case and is written every time. It describes files,
and the files did move; withholding it would make `status` report everything it
had just synced as drift.

There are two classes of migration. One is **version-bound** and runs once, when
the workspace sits below its gate and the installed kit at it or above; it is
recorded in `.papersmith/migrations.json` and does not repeat. The other is a
**convergence** migration: it has no gate, asks the file system through a
read-only probe and is evaluated on every run, because the next release can
change what there is to converge on. A workspace that already satisfies it writes
nothing.

The current version ships two convergence migrations:

- **`sota-pool-scaffold`** creates `sota-pool/.gitkeep` in workspaces older than
  the release that began scaffolding the graph pool.
- **`atlas-render-refresh`** re-renders `sota-pool/atlas.html` when its atlas,
  its renderer or the viewer bundle it inlines changed. The decision is taken
  from hashes stored in `sota-pool/.atlas-render.json`, not from modification
  dates: the mtime of a copy says when the file was written, and `upgrade`
  rewrites it for reasons that have nothing to do with the page.

When the recorded version cannot be ordered — the marker was lost, or it says
something without a number — a version-bound migration cannot be placed on
either side of its gate. It is reported as `undetermined` and never applied:
migrating artifacts under a relation nobody established is exactly the silence
the downgrade guard already removes on the file side. Convergence migrations are
unaffected, because they ask the disk.

`--plan-migrations` is not called `--dry-run` on purpose. That name would suggest
it also previews the kit copy, the per-harness projections and the orphan sweep,
and it does not: a flag should not overstate its scope.

A damaged `.papersmith/migrations.json` makes `upgrade` refuse before writing a
byte, alongside the downgrade guard and for the same reason. Reading it as empty
would re-apply every migration it was recording. `status` answers differently on
purpose: it reports it as a warning, because a command that only informs and
also crashes leaves the workspace with no way to ask what is wrong with it.

### `smith status [<dir>]`

```bash
smith status --json
```

| Flag | Effect |
|------|--------|
| `--json` | Machine-readable snapshot (versions, proposals, runs, inbox) |
| `--verbose` | Also prints the projection notes (`note: ...`) to stderr |

The projection notes (for example `agent 'x': tool 'WebSearch' has no Pi tool;
not granted`, a Claude tool another runtime cannot grant) are emitted by `init`
and `upgrade` when they write the projections. `status` no longer repeats them
as a `UserWarning` on every call: they go into `framework.generator_notes` in
the JSON and are printed only with `--verbose`.

It includes the kit provenance the workspace recorded (`Kit source:`; see
[Kit provenance](#kit-provenance)).

The proposal stage (`Proposal: <file> (<stage>)`) is derived from the engine's
state for the latest managed revision: `published` when its publication receipt
(`.proposal-deliberation/receipts/<file>.json`) is committed and its
`documentShaAfter` is the document's current digest, `edited-after-publication`
when the bytes changed afterwards, and `draft` when there is no committed
receipt. The legacy `proposals/deliberated/` and `proposals/accepted/` folders
are still read first, for old workspaces.

Reports the drifted files by name; the exit code stays `0` while drift is
reported (a non-zero code is a known gap, recorded as a follow-up).

### `smith ingest <file_or_url> [<dir>]`

```bash
smith ingest https://arxiv.org/abs/2309.08600
smith ingest ~/Downloads/reference-paper.pdf --ocr
```

| Flag | Effect |
|------|--------|
| `--ocr` | Balanced OCR-oriented extraction mode (heavier, for scans) |

Downloads/classifies the reference, extracts it to Markdown with LaTeX equations
and figure files (one folder per paper) and refreshes the index. The first run
downloads ~1.5 GB of Surya weights when the environment was not pre-provisioned.

It accepts only PDFs (a local `.pdf` or an arXiv/OpenReview/PDF URL); any other
source is refused, and the message names the two routes for material that is
already text, both owned by `proposal-deliberation`: Markdown to seed a new
proposal goes in `guidance/paper-guide/` (read by `CREATE_INITIAL_REVISION`),
and an existing draft that must become v1 as it stands goes in `proposals/` and
is adopted with `ADOPT_INITIAL_REVISION`.

### `smith deliberate [<dir>]`

```bash
smith deliberate . --action status
smith deliberate . --action init --instruction "First sentence. Second sentence."
smith deliberate . --action adopt --revision draft.md --instruction "Adopt as v1."
smith deliberate . --request-file request.json
```

| Flag | Effect |
|------|--------|
| `--action ACTION` | The engine's real operation (`status`, `init`, `adopt`, successors…) or a supported alias |
| `--request JSON` / `--request-file FILE` | Raw JSON object / the file holding it |
| `--serve` | Persistent JSON-lines mode |
| `--revision FILE` | Managed source file the operation applies to |
| `--instruction TEXT`, `--query TEXT` | Instruction / query payloads |
| `--selected-entry-id ID`, `--decisions JSON` | Resolved edit decisions, for mutation operations |
| `--accept`, `--acceptance-token TOKEN` | Accept a `CREATE_SUCCESSOR` preview |
| `--withdrawal-operation-id ID`, `--withdrawal-reason TEXT` | Withdraw a published revision |
| `--prior-conclusion TEXT` | Prior conclusion for follow-up operations |

Runs the deterministic, AST-verified deliberation engine, keyless and local (no
state operation calls a model).

`--action adopt` is `ADOPT_INITIAL_REVISION`: it turns an unmanaged `.md` in
`proposals/`, named with `--revision`, into v1, and like every operation except
`status` and `resolve` it requires `--instruction`. The bridge has no
`--dry-run`; a preview of `init` or `adopt` is requested with `--request` and
`"dryRun": true`, which the bridge passes to the engine unchanged:

```bash
smith deliberate . --request '{"operation":"ADOPT_INITIAL_REVISION","sourceFilename":"draft.md","instruction":"Adopt as v1.","dryRun":true}'
```

### `smith implement [<dir>]`

```bash
smith implement . --action verify --target implementations/demo
smith implement . --action probe --target implementations/demo
```

`--action` is required. The bridge runs only these actions: `env`, `name`,
`plan`, `apply`, `admit`, `handoff`, `compose`, `probe` (alias `benchmark`) and
`verify`. Supporting flags: `--target`, `--name`, `--plan`, `--finding`,
`--entry-text`, `--python`, `--shards`, `--revision`; whatever follows the known
flags is forwarded as `extra` to `implementation_cli.py`.

`--action materialize` still works, but it is an alias of `apply` (the layout
migration approved with `--plan`), **not** of the engine's `materialize`
(`--stage`/`--authored`/`--adopt`). Every use prints a note to stderr; write it
as `--action apply`.

The rest of the engine's commands do not go through the bridge and are run
directly with the skill's launcher, which sets the domain profile:

```bash
python3 skills/proposal-implementation/scripts/implementation_cli.py materialize \
  --target implementations/demo --name Demo --stage scaffold --plan plan.json --seed 7
```

Direct: `walk`, `materialize`, `adopt`, `position`, `discuss`, `propose`,
`gate`, `offer`, `close`, `step`, `settle`, `defect` (and `agree` in
`experimental-implementation`, with its own `implementation_cli.py`). Asking the
bridge for one of them (except `materialize`, the alias above) refuses and names
this route. If you set `IMPLEMENTATION_DOMAIN_PROFILE` by hand, it must be an
absolute path (a relative one is refused with
`IMPLEMENTATION_DOMAIN_PROFILE_NOT_ABSOLUTE`). The commands that write the
ledger (`position`, `propose`, `gate`, `offer`, `close`, `step`, `settle`,
`defect`, `walk`) require `--session <id>`; what that id is is in
`skills/proposal-implementation/references/usage.md`, "Session ids".

### `smith run <profile> [<dir>]`

```bash
smith run smoke_and_invariants --dry-run
smith run sweep_training --target kaggle-gpu-pool --consent <token>
```

| Flag | Effect |
|------|--------|
| `--target NAME` | Overrides the profile's compute target |
| `--dry-run` | Plans only — records the command, dispatches nothing |
| `--shard VALUE` | Runs a single shard of the campaign |
| `--consent TOKEN` | Consent token for remote submission (forwarded, enforced downstream) |
| `--implementation NAME` | The `implementations/` directory that `{target}` and `{target_python}` name (default: the only one there is) |

Profile placeholders: `{paper_slug}` (the workspace folder name), `{job_id}`,
`{shard_value}`, and since 0.14.0 `{target}` (`implementations/<name>`) and
`{target_python}` (the interpreter of the target's own `.venv`, created by the
implementation skill's `env` command). The default `smoke_and_invariants`
profile runs `{target_python} -m pytest {target}/tests/test_invariants.py`,
never a `pytest` from the PATH. If the target cannot be resolved (none or
several in `implementations/` without `--implementation`, or no `.venv` when the
profile names `{target_python}`), `run` refuses before dispatching or recording
anything; `--dry-run` does not refuse and reports it in `target_resolution`. A
pre-0.14.0 profile that names `implementations/{paper_slug}` keeps working
while that directory exists; if it does not, `run` refuses and says which lines
to change (`papersmith.yaml` is yours: `upgrade` does not rewrite it).

Dispatches per provider (local subprocess / Kaggle submit / `sbatch` over ssh)
and appends each job to `.papersmith/runs_ledger.jsonl`. The Python processes it
launches on the local machine (the local job and the Kaggle submit) run with
`PYTHONDONTWRITEBYTECODE=1`, as do the skill scripts the CLI invokes: they leave
no `__pycache__` inside the workspace.

### `smith remote {pack,push,status,pull,sync} [<dir>]`

```bash
smith remote pack --target kaggle-gpu-pool --entrypoint train.py
smith remote status --job <job-id>
smith remote pull --job <job-id> --dest ./results
```

Key flags: `--target`, `--entrypoint`, `--backend`, `--account`, `--job`,
`--submission-id`, `--dest`, `--consent`, `--smoke`, `--unit` (campaign scope,
repeatable), `--force`, `--resolve`, plus the job-definition flags (`--service`,
`--job-name`, `--product`, `--commit`, `--repo-url`, `--repo-ref`,
`--run-module`, `--run-function`, `--clone-path`, `--regenerate`). Extra tokens
are forwarded to `remote_cli.py`. A real submission spends quota: prefer
`--smoke` and `--dry-run` first (see
[Remote compute, carefully](../README.md#remote-compute-carefully)).

### `smith target {list,set,check}`

```bash
smith target list
smith target set kaggle-gpu-pool
smith target check
smith target check slurm-cluster
```

- `list [<dir>]` — configured targets, marking the active one with `*`.
- `set <name> [<dir>]` — persists the default target in `.papersmith/config.json`.
- `check [<name>] [<dir>]` — connectivity test: `local` looks for Python, `kaggle`
  goes through the accounts helper, `remote-ssh` tries
  `ssh -o BatchMode=yes -o ConnectTimeout=5 <host> true`.

### `smith audit [<dir>]`

```bash
smith audit --check-drift
```

| Flag | Effect |
|------|--------|
| `--check-drift` | Also reports drift in generated files as findings (never repairs) |
| `--verbose` | With `--check-drift`, also prints the projection notes to stderr (the same as `status --verbose`) |

Audits the workspace's structure and consistency. It is bound to the `skill-audit`
subject today; drift is reported, not fixed.

> **Note:** `kaggle-accounts` (validate/remove/list/discover/materialize) has no
> `smith` subcommand yet — it runs as
> `python3 skills/kaggle-accounts/scripts/accounts_cli.py …` or indirectly
> through `target check`.

### `smith ui [<dir>]`

```bash
smith ui --port 8080
smith ui ~/papers/sparse-ae --no-browser
smith ui --export-static ./dashboard-static
```

| Flag | Effect |
|------|--------|
| `--host HOST` | Bind address (default `127.0.0.1`) |
| `--port PORT` | Preferred port; if it is taken, the next free one |
| `--no-browser` | Does not open the browser |
| `--export-static <dir>` | Copies the dashboard build to `<dir>` and exits |
| `--allowed-host HOST:PORT` | Also accepts that `Host` header (repeatable); only forwarded to the backend when supplied |
| `--allow-unauthenticated-network` | Permits a non-loopback `--host` (see *Network exposure* below); only forwarded when supplied |
| `--no-terminal` | Does not offer the dashboard's support terminal (it is only ever offered on a loopback bind) |

Serves the **Paper Command Center**: a local dashboard inside the workspace with
its two flows, the four quality gates, the ten-section matrix and the health of
the harness wiring. It updates live over Server-Sent Events, with a 300 ms
debounce on `sections/`, `openspec/`, `experiments/` and `papersmith.yaml`.

The backend lives in `skills/_core/command_center/` (part of the kit, so it
travels with every workspace) and runs standalone without Node/npm:

```bash
python -m skills._core.command_center.server --port 8080
```

**The two flows.** The *Pipeline* tab draws the overall flow: the twelve stages of
the architecture diagram, in order, plus the audit path across them where the four
gates land. Each stage lights up from what is on disk — `sota-pool/`, `guidance/`,
`proposals/`, `implementations/`, `.experimental-deliberation/`, `experiments/`,
the credentials store, the inbox, `paper/Figures/` and `sections/` — and a stage
with no artifact is reported inactive saying what is missing, never with an
invented progress. The *Writing* tab draws the writing flow: one section per node,
in render order, each with its state, its words and its blocks. The edges do not
live in the frontend: the extractor sends them in the payload (`pipeline_chain`
and `gate_links`), so the dashboard cannot contradict the diagram.

Endpoints: `/api/state`, `/api/health/wiring`, `/api/health/run-wiring-smoke`
(POST) and `/api/events` (SSE); the dashboard build is served at `/`. The frontend
is built once with `npm run setup:ui` (it installs from the lockfile) and then
`npm run build:ui`, which emits into `skills/_core/command_center/static/`;
`npm run dev:ui` starts the Vite server with a proxy to the backend for work on
the interface. The install step uses `npm ci` and not `npm install` on purpose:
`install` rewrites the lockfile with the local npm's metadata, and that noise does
not belong to any dependency change. The end-to-end smoke is
`bash scripts/command-center-smoke.sh`.

**Light theme.** The dashboard uses a single light theme, defined by colour tokens
in `ui/src/styles.css`; a Vitest test rejects any literal colour outside `:root`
and checks the contrast (WCAG AA) of the token pairs.

**Clickable diagram and deep links.** Every node (stage, gate, section) and every
edge of the pipeline diagram can be selected with the mouse or the keyboard
(Enter or Space on the focused element, Escape to close) and opens a detail panel
with its data, its connections and its history. The selection goes into the URL
(`#pipeline?el=gate%3Awriting-readiness`), so a link opens that element directly.

**History in memory.** The *History* tab shows what changed since the dashboard
started: section state and blocks, word counts, gates, stages, wiring health and
the smoke. It lives in memory (a ring of 1,000 entries per process; nothing is
written to disk), so it is lost when the server restarts.
`GET /api/history?boot_id=<id>&after_seq=<n>` returns pages of entries oldest
first (`element`, `kind` and `limit` are optional; an invalid `element` or `kind`
answers 422); the response carries `has_more`, `reset` (another process: a reload
is needed) and `gap` (older entries were dropped). New entries arrive over SSE as
`history_append`.

**Allowed-host list.** The server only accepts the `Host` header of its own bind
address (`<host>:<port>`, IPv6 in brackets), plus `127.0.0.1:<port>`,
`localhost:<port>` and `[::1]:<port>` on a loopback bind, and answers 421 to any
other, which stops DNS-rebinding pages. Another host (when forwarding a
port, for instance) is accepted with the repeatable flag
`smith ui --allowed-host HOST:PORT`. With `npm --prefix ui run dev` the Vite
proxy keeps the `Host` `localhost:5173`; the backend is started like this (the
module accepts the same flag):

```bash
python -m skills._core.command_center.server --port 8080 --allowed-host localhost:5173
```

**Network exposure.** The dashboard has no authentication: whoever reaches its
port can read the workspace, edit it through the PDF annotations, and start its
compile and wiring-smoke runs. So it only serves on a loopback address
(`127.0.0.1` by default, `localhost`, `::1` or another `127.x.y.z`) and refuses
any other `--host`, `0.0.0.0` included, with exit code 2. To use it from another
machine, keep the loopback bind and forward the port over SSH
(`ssh -L 8080:127.0.0.1:8080 <server>`, then open `http://localhost:8080/`; a
different local port needs `--allowed-host localhost:<port>`). On a network you
trust, such as a container whose port is published only to its host,
`--allow-unauthenticated-network` lifts the refusal. The `Host` check stays on,
so name every address clients use with `--allowed-host`.

**A new workspace starts clean.** `smith init` copies only the framework (the
kit's skills, section contracts, agents and setup scripts) into an empty folder
and seeds `papersmith.yaml`; it never copies artifacts, graphs or data from
another project. The dashboard draws every part of the *Mapa Conceptual &
Modelo* tab — novelty pillars, hypotheses, concept-map layers, proof-of-concept
experiments, equations — from the workspace itself, and shows a neutral "pending
deliberation" state until its own proposal and experiments exist. A workspace may
provide `.papersmith/model_spec.json` and `.papersmith/novelty_graph.json` to
draw its own model and novelty graph; nothing project-specific ships with the
framework (`tests/test_clean_init.py` scans the kit and a fresh workspace's
dashboard for traces of earlier projects).

**Math panel and Socratic tutor.** *Mapa Conceptual & Modelo → Matemática &
Tutor* shows the paper's own mathematics as LaTeX rendered by KaTeX 0.16.22
(vendored, offline): a lema, then one card per equation (heading, display
equation, a one-line *Conexión*, variables), beside a compact *Idea y novedad*
card (central idea, novelty, problem, contributions, key equation).
`GET /api/model/math` builds it from the latest
`proposals/research-concept-<slug>-rNN.md` (every `$$`-fenced block with its
`\tag{N}`, the heading above it and the first sentence after it) and its
`.sky.json` overlay, else from `.papersmith/model_spec.json`; an empty
workspace says so instead of inventing equations. The **tutor** beside it is
the `math-tutor` skill: drop, paste or pick photos of your hand-written pages
(PNG/JPEG/WebP, up to 8 MiB, at most 6 per turn), write, choose *Preguntar*,
*Explícame* or *Evalúame*, and each turn runs the `math-tutor` agent headless
with your own agent CLI — `claude -p` with only the `Read` tool, the turn's JSON
schema, no MCP and only local settings, or `pi -p` as a fallback — so no API key
lives in the dashboard. The tutor reads the image back as LaTeX and parts, asks
one question at a time, rates understanding 0–4 (*reconoce*, *explica*,
*deriva*, *justifica*) with evidence quoted from you, and ties every step to the
paper's novelty. Uploads and the thread live in `.papersmith/math-tutor/`. Routes
(behind the terminal's secret cookie and origin guards):
`GET|DELETE /api/terminal/tutor/thread`, `POST /api/terminal/tutor/images`,
`GET /api/terminal/tutor/images/<id>` and `POST /api/terminal/tutor/turn`.

**Graph toolbar and cross-panel links.** The *Atlas* tab keeps its three graph
switches and adds **⚡ Regenerar grafo** (the SOTA atlas through
`POST /api/atlas/build`, same as `smith atlas build`; on the novelty graph it
rebuilds the view) and **🧩 Disposición de grupos**, which asks the atlas frame to
rearrange its systems by family cluster and back. The dashboard and the
sandboxed atlas frame talk through `postMessage`: the dashboard sends
`{type: 'atlas-command', command: 'group-layout' | 'sky-layout' | 'toggle-layout' | 'reset' | 'pause' | 'resume' | 'view-2d' | 'view-3d'}`
(`pause` while another tab is shown, so the atlas stops drawing; it loads the
first time its tab opens, and it also stops while the browser hides the page) and the atlas answers `{type: 'atlas-layout', mode}` and, on a click,
`{type: 'atlas-planet-selected', key, label, slot, system: {id, title}}`. A
selected node shows **📄 Ver en PDF** (finds the node's label, or its system's
title, in the compiled PDF's text and jumps to that page) and **🗂️ Ver
artefacto** (opens `sota-pool/atlas.json` in the artifact viewer).

**Smith CLI assistant ("CLI de apoyo").** The round button at the bottom right,
with Smith's face, opens a floating xterm.js console (780×520, maximizable;
closing it only hides it, the session keeps running) bound to a pseudo-terminal
in the workspace root. The agent picker offers **herdr** (default: it focuses or
creates the herdr workspace labelled after the project, so the console mirrors
your herdr panes), `claude`, `opencode`, `pi` and a login shell; binaries are also
found in `~/.local/bin`, `~/.npm-global/bin`, Homebrew and `~/.cargo/bin`, and the
choice is remembered. **🖥️ Ghostty** (or WezTerm) opens herdr on the project in a
native terminal. The footer shows the agent and project path, a *Comandos smith…*
menu (`smith status`, `smith atlas build`, `smith audit` in the shell; the projected
slash commands in an agent) and *Limpiar*. The server answers the terminal
capability queries full-screen TUIs send (DA1, OSC 10/11, `?u`, `?996n`, `16t`) on
the PTY itself and strips them from the output, keystrokes are coalesced, and the
console refits and repaints when the tab regains focus. Each phase card has
**⌨️ Enviar a CLI**, which types that phase's command and waits for your Enter;
**▶ Ejecutar** keeps its own path. Routes: `GET /api/terminal/agents`,
`GET /api/terminal/tools`, `POST /api/terminal/launch-external`,
`POST /api/terminal/sessions`, `GET /api/terminal/sessions/<id>` (agent and
liveness, for a reload to reattach), `POST /api/terminal/sessions/<id>/input` (`data`, or
`cols`/`rows` to resize), `DELETE /api/terminal/sessions/<id>` and
`GET /api/terminal/sessions/<id>/stream` (SSE, base64 `output` frames then `exit`;
it waits for output and pings every 15 s). A closed console drops its stream
unless a phase is running, and reattaches when opened again.
At most four live sessions; they close with the server. The console is a shell
with your privileges, so it is only offered on a loopback bind
(`smith ui --no-terminal` turns it off). Each server start creates a secret: the
browser it opens (or the `dashboard login URL` it prints, for `--no-browser`) goes
through `GET /api/terminal/login?token=…`, which sets an HttpOnly, SameSite=Strict
cookie, and every terminal route requires it, so another local user or a `curl`
without the token gets `403`. Every call must also be same-origin: a foreign
`Origin` or `Sec-Fetch-Site`, a missing `X-Papersmith-Terminal: 1` header or a
non-JSON body answers `403`.

**Branding.** The LabIA UNAL logo appears once, centred in the footer on a white
badge; the header carries Smith's avatar and the laboratory line only. The footer
names the framework version the workspace was last initialized or upgraded to
(`/api/status` → `framework_version`).

**Live PDF preview.** The *Previsualización PDF* tab renders `paper/main.pdf`
with pdf.js 3.11.174, vendored in `skills/_core/command_center/static/vendor/`
(no network). `GET /api/pdf` answers with an `ETag` and `Cache-Control: no-cache`
(`304` when `If-None-Match` matches), and `/api/status` reports
`run_details.pdf_mtime`; when a recompile moves that token the open preview
reloads in place and keeps the page you were reading.

**Paper preview (read-only).** Two GET routes, no writes:
`GET /api/paper/preview` returns the sections in the same order and with the same
ids as `/api/state`, with the plain text of each block of `paper/main.tex`
(markers `%% paper-writing block <id> begin|end`), its `\cite{...}` keys, words,
`written` and the `truncated`/`duplicate` flags, plus the PDF state (`pdf.main`
with `stale` when `main.tex` is newer than `main.pdf`, and the list of figures;
both carry `mtime` in milliseconds, which the UI appends as `?v=` to reload the
PDF and the thumbnails on recompile) and `sections_dir` (`status`: `ok`, `absent`,
`unsafe` when `sections/` is a symlink pointing out of the workspace, and
`truncated` when there are more than 100 non-canonical sections; the canonical
ones always resolve by name). The declarations and provenance regions are
ignored; a block with no closing marker is dropped, and with repeated ids the
first one wins (marked `duplicate`). `GET /api/paper/file?name=<n>` serves only
`main.pdf` (`paper/main.pdf`) and `figures/<id>.pdf|png` (the real directory is
`paper/Figures/`, with a capital F). Id rule: a single segment `[A-Za-z0-9._-]`,
no separators, no NUL and no leading dot, up to 100 characters (stricter than
`paper_figure.py`). Responses: 400 for a malformed name, 404 for absent or not
allowed, 413 above 25 MiB; fixed headers `Content-Type` by extension, `nosniff`,
`inline`, `X-Frame-Options: SAMEORIGIN` and `no-store`. It carries no CSP
`sandbox` (it would break the PDF viewer) and does not accept `Range` (the whole
file is sent). Read limits: `main.tex` 2 MiB (above that, status `too_large` and
no content), each section contract 256 KiB, 32 KiB of text per block and 200 KiB
of text in total (with `truncated`). Every read resolves the path, requires it to
stay inside the workspace (a symlink that escapes gives `unsafe`/404) and
requires it to be a regular file. papersmith does not generate `main.pdf`: the
file not existing is normal. The `Host` protection (421) covers these routes only
on a loopback bind; on a non-loopback bind there is no `Host` filtering.

**The *Preview* tab.** Shows the text of the written blocks and the compiled PDF
in one view. On the left the sections appear in order with their state; each block
is painted as escaped plain text (never as HTML: a `<b>` or a `<script>` in
`main.tex` is shown literally), the `\cite{...}` keys come out as chips, unwritten
blocks show a marker with their id, and every truncation or duplicate id is
reported, along with `main.tex` absent, too large, unsafe or unreadable, and
"Preview truncated" when the response ceiling is reached. On the right, if
`paper/main.pdf` exists it is embedded in an `<iframe>` with a *stale* badge when
`main.tex` is newer than the PDF; when it does not exist, the text explains that
papersmith does not compile the full paper and that it has to be built
separately. Below, the figures of `paper/Figures/` are listed with an *Open* link
(PNGs with a thumbnail). It loads when the tab is opened (`#preview`) and is
requested again when the workspace state changes over SSE, without overlapping
requests; a failure shows the error with *Retry*.

**SOTA atlas (read-only, backend).** Two GET routes over `sota-pool/atlas.json`
and `sota-pool/atlas.html` (the `plausibility` skill writes them; the dashboard
never writes or regenerates them). `GET /api/atlas` returns `json` and `html` with
their status (`ok`, `absent`, `too_large`, `unsafe`, and for the JSON also
`unreadable` or `invalid`) and size, `stale` (`atlas.json` newer than
`atlas.html`; `null` when either is missing), `mtime` in milliseconds (the UI
appends it as `?v=` to the iframe to reload it), `validation` (`ok`, `failed` with
`errors`, up to 50, or `unavailable` with `detail`) and `summary` (systems with
id, title, number of planets and families; number of links; count by `rel`;
evidence with system, planet, origin and date, up to 100) or `null`. An invalid
JSON gives `json.status: invalid` and `validation.status: failed`, never a 500.
`GET /api/atlas/view` serves the bytes of `atlas.html` (404 when it is missing,
unsafe or not a regular file; 413 above 2 MiB) with
`Content-Type: text/html; charset=utf-8`, `Content-Security-Policy:
sandbox allow-scripts; default-src 'none'; script-src 'unsafe-inline'; style-src
'unsafe-inline'; img-src data:`, `nosniff`, `no-store`,
`X-Frame-Options: SAMEORIGIN` and `Referrer-Policy: no-referrer`. Every read
resolves the path, requires it to stay inside the workspace (a symlink that
escapes is `unsafe`) and requires it to be a regular file, and checks the size
(2 MiB per file) before reading. **Workspace Python execution:** to validate, the
server loads `skills/plausibility/scripts/check_atlas.py` from the workspace
itself (a fixed path, never derived from the request) and calls its validator
inside the server process, writing no bytecode; it is a code-execution surface, so
the dashboard should not be pointed at a workspace you do not trust. If the script
is missing, cannot be loaded or fails, `validation.status` is `unavailable` with
the reason. The `Host` protection (421) covers these routes only on a loopback
bind; on a non-loopback bind there is no `Host` filtering.

**The Atlas tab.** `#atlas` consumes the routes above. On the left, a native
summary (text always escaped): a table of systems with planets and families, the
number of links and a breakdown by `rel`, a bounded evidence list ("showing N of
evidence_total"), and a validation chip (`valid`; `failed` with the first errors
and "N more"; `unavailable` with the reason). On the right, the constellation:
`atlas.html` inside an `<iframe src="/api/atlas/view" sandbox="allow-scripts"
referrerpolicy="no-referrer">`, without `allow-same-origin` (the HTML runs in an
opaque origin and cannot read the dashboard). The states are explained on screen:
no atlas ("No atlas yet. Run the plausibility skill..."), `atlas.json` too large,
unsafe, unreadable or invalid, "JSON present, HTML missing" (`scripts/render_atlas.py`
is needed), HTML without JSON, and a STALE badge when `atlas.json` is newer than
`atlas.html`. The atlas files are not watched: they are requested when the tab is
opened and with the *Refresh* button (without overlapping requests; a failure
shows the error with *Retry* and keeps the previous data). Note: Chromium does not
paint an isolated iframe that falls outside the viewport in `--full-page` captures
(at 700x900 it comes out blank); inside the viewport it is complete.

**Decisions line (read-only, backend).** `GET /api/decisions` mixes, when asked,
normalized events `{ts, source, kind, summary, ref}` from records the workspace
already keeps; it writes nothing and stores no snapshots. Sources: `declarations`
(the `%% paper-writing declarations` region of `paper/main.tex`; `ts` is
`recorded`, and that region only keeps the CURRENT state: earlier values cannot be
recovered), `proposal` and `experiment` (`receipts/*.json` and
`lifecycle/v1/transitions/*.json` in `.proposal-deliberation/` and
`.experimental-deliberation/`) and `remote-execution` (the `ledger.jsonl` under
`implementations/<repo>/<Name>/.remote-execution/`, discovered exactly two levels
down, without recursion; `kaggle-inbox/` is never read). Edit receipts carry no
timestamp: their events have `ts: null`, come after the dated ones (by file name)
and the mtime is never used; the initial-revision receipt
(`CREATE_INITIAL_REVISION`) does carry `createdAt`, used as `ts` ("Created initial
revision r01"). Transitions use `committedAt`; every outcome (`COMMITTED`,
`ALREADY_COMMITTED`, `REJECTED`, `INCONSISTENT`, `RECOVERY_REQUIRED`) has its
summary. Everything is read as plain JSON without repeating the lifecycle's hash
and consistency checks, so those events carry `verified: false` (the UI marks them
as *unverified*). Order: dated ones newest first, with a stable tie-break by
source; an unreadable `ts` counts as `null`. Each source returns `status` (`ok`,
`absent`, `unreadable`, `too_large`) and `count` in `sources`, so a broken source
does not break the response. Ceilings: 500 events per source and 1000 in total
(`truncated` and `total`), `main.tex` 2 MiB, 256 KiB per receipt or transition,
500 files per sidecar directory, 20 ledgers of up to 2 MiB and 2000 lines each
(the most recent 2000 lines are kept and `detail` counts the older ones ignored;
malformed lines are skipped and counted in `detail`). Optional filters: `source=`
(comma-separated list; 422 on an unknown name) and `limit=` (1 to 1000). Every
read resolves the path, requires it to stay inside the workspace and to be a
regular file, and checks the size before reading. There is no author field: it is
never recorded. The `Host` protection (421) covers the route only on a loopback
bind.

**The Decisions tab.** `#decisions` consumes `/api/decisions` when it opens and
with the *Refresh* button (the sources are not watched; without overlapping
requests; an inline error with *Retry*, keeping the previous data). It shows the
events as they arrive (dated ones newest first; then, under the *Undated*
subheading, the edit receipts with no timestamp). Each row carries the date as UTC
text (`YYYY-MM-DD HH:MM:SS UTC`), a source label (declarations, proposal,
experiment, remote ledger), the kind, the summary and the `ref` path as text (it
is not a link). Rows with `verified: false` show *unverified* with the title "Read
from the lifecycle files without hash or consistency checks.", and rows carrying
`note` show it in grey (declarations only keep the current value). Above, a status
chip per source (`ok`, `absent`, `unreadable`, `too_large`, with its count,
`detail` and the *truncated* mark), checkboxes to filter by source in the client
and, when the response was truncated, "Showing N of total". All text is escaped.
There is no link to the Sections tab: the tab has no per-element anchors and a
declaration's id does not allow deriving the section without heuristics, so it is
omitted on purpose.

**Visual checker.** `scripts/command-center-visual-check.mjs` opens the dashboard
in Chromium, captures every tab at 1280x800, 1600x1000 and 700x900 (bottom sheet)
and fails on console errors:

```bash
node scripts/command-center-visual-check.mjs --out /tmp/shots --full-page --click-check --drag-check
```

| Flag | Effect |
|------|--------|
| `--out <dir>` | Capture directory (required) |
| `--url <url>` | Dashboard to check (default `http://127.0.0.1:8099/`) |
| `--tabs a,b` / `--viewports 1280x800,...` | Narrows tabs or sizes |
| `--full-page` | Captures the whole page, not only the viewport |
| `--drag-check` | Checks that dragging the canvas does not open the panel |
| `--click-check` | Clicks a stage, a gate, a section and an edge, and tries the keyboard |
| `--timeout <s>` / `--chromium <path>` | Time limit and Chromium executable |

It is a development tool (it needs Chromium); it does not run in CI. The UI tests
(`npm --prefix ui test`) do run in CI.

### `smith atlas build [<dir>]`

```bash
smith atlas build
smith atlas build ~/papers/sparse-ae --json
```

| Flag | Effect |
|------|--------|
| `--json` | Prints the result object instead of one line |

Regenerates the SOTA atlas page, the same action as the dashboard's
**⚡ Regenerar grafo** button (`POST /api/atlas/build`). It runs the workspace's
own `skills/plausibility/scripts/check_atlas.py` on `sota-pool/atlas.json` (with
`--pool sota-pool/candidates.json` when the pool exists) and, only when the
checker is green, `render_atlas.py` to `sota-pool/atlas.html`. A failing atlas
never replaces a good page. Exit `0` when the page was written, `1` otherwise.
The route answers `200`, `404` (no `atlas.json` or no scripts), `422` (the
checker or renderer refused) or `504` (timeout), always with
`{ok, stage, detail}` plus the system, planet and link counts on success.

### `smith mcp {serve,inspect,print-config,kaggle}`

```bash
smith mcp serve --workspace ~/papers/sparse-ae
smith mcp inspect
smith mcp print-config --workspace ~/papers/sparse-ae
```

Exposes the workspace orchestrator and the `paper-writing` verbs to any Model
Context Protocol client over `stdio` (JSON-RPC 2.0).

- `serve --workspace <dir>` — starts the MCP server over `stdio`, bound to a single workspace.
- `inspect` — prints the capability catalogue as JSON (the source of truth).
- `print-config [--workspace <dir>]` — emits the configuration fragment for the host being configured (Claude Code, OpenCode).

- `kaggle activate [--token-stdin] [--no-verify] [--replace] [--workspace <dir>]` — activates Kaggle's official MCP server (`https://www.kaggle.com/mcp`, registered as `kaggle` by `init` and `upgrade`). It reads a `KGAT_` token (kaggle.com/settings → Account → API → Generate New Token) from a hidden prompt, verifies it with a read-only `get_accelerator_quota` call, and stores it where Kaggle's own client reads it, `~/.kaggle/access_token` (directory `0700`, file `0600` on POSIX), so the same token serves the `kaggle` CLI and `kagglesdk`. A different token already there is kept unless `--replace`. A token the official client left in `access_token` or `access_token.txt` is used as is, and the location 0.20 used (`$XDG_CONFIG_HOME/papersmith/kaggle-mcp-token`) still reads. The dashboard injects it as `KAGGLE_API_TOKEN` into the sessions its CLI assistant starts, unless that variable is already exported; on POSIX a stored file that is a symlink or readable by others is never used.
- `kaggle status [--verify]` — reports where the token comes from, never its value, plus the detected environment (macOS, Linux, WSL or Windows; zsh, bash, fish or PowerShell) and the exact command and profile file to export it outside the dashboard.
- `kaggle deactivate` — removes the stored token files (the official client reads the same file, so this signs out the `kaggle` CLI too).

`smith init` and `smith upgrade` print one offline line about the activation state (no network call) and warn when Pi or Antigravity are wired but `npx`, which their `mcp-remote` bridge needs, is missing. `pip install` runs no post-install step, so nothing is checked there.

The dashboard's Experimentos tab shows the activation state and runs `smith mcp kaggle activate` in the CLI assistant.

The full catalogue of 38 tools (15 read-only and 23 mutating), the
`papersmith://` resources and the security model are documented in detail in
**[docs/mcp.md](../docs/mcp.md)**.

---
