# Changelog

Notable changes to papersmith-ai, newest first.

This file starts at 0.2.0. `0.1.0` was set in the commit that created the
package and never moved again across more than a thousand commits, so there
is no honest way to reconstruct a release history for it — its record is the
git log, and pretending otherwise would put a fabricated summary where a
reader expects a kept one.

Versions follow [semantic versioning](https://semver.org): while the first
number is `0`, breaking changes can still arrive without a major bump.

## 0.36.0

### Added

- Historia con IA shows a decision graph. Each phase is split into rounds: an
  operator turn (the phase command or a follow-up) and what answered it, or a
  persisted decision (a deliberation edit, a transition, a fact, a remote
  submission) when no chat round holds it. Every round is classified as
  success (the operator approved it, or it closed a passed phase), rework (an
  error or declined fact, a relaunched command or submission, or a next turn
  asking to correct it), iteration or pending (the open end of a phase that
  has not passed). A strip above the diagram totals them and links the rounds
  still to be decided; each phase box shows its counts; the selected phase
  draws its rounds as a chain with a loop over every rework, and clicking a
  round shows the operator turn against the reply and highlights its events.
  The timeline shows only the main interactions (operator turns, the replies
  that answer them, errors) unless asked for everything. `/api/ai-history`
  adds `rounds`, `total_rounds` and `decision_summary` per phase and
  `decision_summary` and `pending` to the view.
- The `paper-reviewer` agent reviews the compiled paper (`paper-writing`,
  stretch verify) and, in an advisory proposal mode, a proposal revision
  before acceptance: it fills the NeurIPS 2026 main-track review form and
  grounds pertinence, novelty and coherence in quoted evidence from the paper,
  proposal, results and SOTA pool.

### Fixed

- Historia con IA no longer counts harness-injected user turns (background
  task notifications, command caveats, persisted output) as operator
  iterations.

## 0.35.0

### Added

- A remote job can declare the public datasets it reads:
  `generate-job --input-dataset <owner>/<slug>` (repeatable) records
  `inputDatasets` in `run-config.json`; a malformed or repeated ref refuses at
  generation and on every read, so a hand-edited one refuses at `submit`
  before anything is sent. A pushed Kaggle kernel is non-interactive and
  cannot attach a dataset at run time (`New Datasets cannot be attached in
  non-interactive sessions`), so the Kaggle adapter now names the declared
  datasets in the pushed `kernel-metadata.json`'s `dataset_sources`, which the
  driver maps onto the save-kernel request's `dataset_data_sources`. The
  capability is the optional `Adapter.INPUT_DATASETS_ROOT` (the ABC keeps six
  operations): `submit` hands that root to the job as `inputRoot` and reports
  `inputs: attached`; a service without it (Colab) reports `inputs:
  unsupported`. Before the entrypoint, the runner searches the input root for
  each ref's slug and exports `FORGE_INPUT_DATASETS`, a JSON object mapping
  each ref to its mounted directory, or to `null` when it was not attached, so
  the target downloads it instead. A job declaring no inputs is byte-identical
  to before.

## 0.34.0

### Added

- An experiment diagram can be validated from the conversation with an agent,
  not only with the dashboard's "Validar diagrama":
  `diagram_cli.py validate --target <repo> --name <Name> --kind poc|experiments
  --png-sha256 <hex> --operator-statement "<the operator's words>"` writes the
  same `<Name>/diagrams/<kind>.validated.json` the button writes, plus
  `"via": "chat"` and the operator's statement verbatim, so `submit`'s
  `DIAGRAM_NOT_VALIDATED` check reads it unchanged. The hash (full, or a prefix
  of at least 12 hex characters) must match the current PNG; a mismatch, an
  invalid hash, an empty statement, a missing PNG or spec, an absent approval
  marker or a `diagrams/` folder leaving the product refuses
  (`PNG_HASH_MISMATCH`, `PNG_HASH_INVALID`, `STATEMENT_EMPTY`, `DIAGRAM_ABSENT`,
  `SPEC_ABSENT`, `APPROVAL_ABSENT`, `DIAGRAMS_OUTSIDE_PRODUCT`) and writes
  nothing. An agent runs it only after the operator explicitly approves that
  diagram in the current conversation, never on its own initiative. `render`
  still drops the record, whichever way it was validated.
- `diagram_cli.py status` reports each validated diagram's `provenance`
  (`via` `chat` or `dashboard`, the time, the statement), and the Experimentos
  panel says "validado por chat" or "validado en el tablero" beside it. The
  dashboard's record keeps its shape.

## 0.33.0

### Added

- A job can carry a private repository's pinned code instead of cloning it:
  `generate-job --code-bundle` archives the declared clone paths (and the
  run/smoke notebook) at the pinned commit with `git archive`, never the
  working tree, writes `code-bundle.tar.gz` beside `run-config.json` and
  records `codeBundle {file, format, sha256, bytes}`. Only a service whose
  adapter declares the optional capability `CODE_BUNDLE_MAX_BYTES` accepts
  it; the Kaggle adapter does (786,432 compressed bytes, a conservative bound
  because the service documents no notebook source limit) and pushes the
  bytes inside the private notebook. The remote is never probed and no
  credential is read; every local pin condition still applies. `submit` and
  the runner both verify the sha256, and the runner unpacks instead of
  cloning, refusing absolute, `..`, `.git`, link and out-of-clone-path
  entries, then writes `.git/HEAD` with the pinned commit so a notebook's
  repository-root cell resolves the bundled clone as it does a cloned one.
  `submit` also rebuilds the bundle from the pin and compares its files. New
  refusal codes: `CODE_BUNDLE_NOT_CARRIED`, `CODE_BUNDLE_TOO_LARGE`,
  `CODE_BUNDLE_UNSAFE_ENTRY`, `CODE_BUNDLE_MISMATCH`,
  `CODE_BUNDLE_WITH_REPO_CREDENTIAL` (`--code-bundle` with `--repo-credential`). Without the flag a job
  is generated, pushed and run exactly as before.

## 0.32.0

### Added

- A continuation now carries the previous session's output automatically. A
  job declares the paths a continuation needs with `generate-job
  --carry-path <path>` (repeatable, relative to the product folder, e.g.
  `Results/checkpoints`, `hpo/studies`), recorded as `carryPaths`. When a
  campaign `submit` sends units an earlier submission left remaining (its
  `partial.json` lists them, or `fetch` kept its partial output), the
  continuation goes to the account that produced them and, on Kaggle, the
  earlier kernel is added to the pushed metadata's `kernel_sources`, with no
  hand-written entry. The runner copies the declared paths from the mounted
  output into its working directory before the entrypoint runs and exports
  `FORGE_CARRY_IN`; a missing mount or path is logged and the unit starts
  fresh. The `submitted` event records `carriedFrom`, and each submission in
  `submit`'s output reports `carry` (`attached`, `unsupported`, `fresh`). A
  job that declares no carry paths behaves exactly as before.
- No push replaces an output a continuation still reads. Every job of a job
  declaring carry paths (each campaign share, a single send, a rehearsal)
  is handed the refs pending continuations read from, and Kaggle pushes to
  the first alternate kernel not among them (`<slug>-carry`,
  `<slug>-carry-2`, ...) instead: a fresh share never overwrites the kernel
  another share of its campaign mounts, two continuations never push each
  other's source, a later campaign of fresh units leaves pending sources
  intact, and a kernel never names itself as its own source. `--carry-path
  .` is refused.
- No push replaces a kernel that is still running. The refs of submissions
  of the same entrypoint that are submitted but not yet settled are
  protected too, for every job folder, including one that declares no carry
  paths: a second campaign started while the first runs pushes to
  `<slug>-carry` (or the next free alternate) instead of a new version of
  the running kernel. This changes such a job only when something is in
  flight, and then only by the `carryProtected` key in its run config; with
  nothing in flight it is byte-identical to before.
- `distribute` and `submit` place a continuation unit on the worker that
  produced its checkpoint when that worker is in the pool (it waits
  `unplaced` when that worker is full). One whose worker is not in the pool
  refuses `CARRY_WORKER_MISMATCH`, naming the worker; `submit --no-carry`
  starts such units fresh instead.
- On Colab, which has no kernel inputs, nothing is carried automatically and
  `submit` reports `carry: unsupported` for the continuation.

## 0.31.0

### Added

- Parallel campaigns over several accounts. A campaign `submit` now sends one
  job per concurrent slot a worker was granted (a Kaggle account runs two at
  once), each with its round-robin share of the units, its own submission id
  and its own ledger lane; on Kaggle, slot 2 and later get their own kernel
  (`-slot-<n>`). A worker granted one slot submits exactly as before. If the
  backend answers two slots of one campaign with the same submission id,
  `submit` refuses `DUPLICATE_SUBMISSION_ID` before recording the repeat.
- A campaign `submit` refuses `CAMPAIGN_WORKERS_NOT_READY`, and `gate --unit`
  refuses `NOT_READY`, unless every worker the campaign will use has its own
  passing rehearsal at the current pin. The refusal names the workers that
  still need one: rehearse on each of them first.
- `walk` and `launch-plan` report `concurrentLaunches`: every remote step whose
  inputs are already produced is `launchable`, so steps placed on different
  services (for example one arm on Colab, another on Kaggle) can be launched
  at the same time, each through its own `propose`/`offer`/`gate`. Steps that
  read another step's product are listed as `waiting`, with what they wait on.
  With a single launchable step the output is unchanged.
- `remote-parallelism assess` takes each account's own limits with `--account
  <owner>:<service>:<sessions>:<session_hours>:<quota_hours>[:<tier>]`
  (repeatable) or `--accounts-file <json>`, instead of one set of values for all
  accounts. An account with an `unknown` quota is reported, not checked. The
  uniform flags print exactly what they printed before.
- New read-only `remote-parallelism schedule` verb: given the project's remote
  steps (`--plan plan.json`), it puts each step on one service and its units on
  that service's accounts so the project ends as early as possible, respects
  step dependencies and the doctrine (one service per campaign, split along
  seeds/folds/subjects, never by arm), and reports the makespan against the
  serial one and the quota used per account. It never launches anything.
- The Experimentos panel shows remote runs per worker for each product: worker,
  service (from the worker id: `colab` or `colab:<owner>` is Colab, a bare
  username is Kaggle), each lane (entrypoint and slot) with its state, units
  when the ledger records them (otherwise the granted capacity), submission id
  and last update. Slots of one worker are grouped under it; at most 24 workers
  and 20 lanes per worker are listed. The existing "Últimas ejecuciones" list is
  unchanged.
- Each remote backend now declares how long one of its sessions may run
  continuously (Kaggle GPU: 12 hours; Colab Pro: 24 hours), so you no longer
  have to type the limit yourself. `submit` writes it into the job folder.
- The runner passes `FORGE_SESSION_DEADLINE` (epoch seconds: session start plus
  the limit, minus a safety margin) to your code. Read it, save a checkpoint,
  and stop starting new folds, seeds or trials before it, so the session ends
  as a normal completion and its output is kept.
- Colab keeps its list of written files up to date while the run is going, so
  you can `fetch` in the middle of a long run. If the session is later killed
  or reclaimed, what survives is what an earlier fetch already brought back.
- `submit` records which units each campaign submission carries
  (`submitted.units`). The new read-only `remaining` verb lists which declared
  units have no complete result yet, so the next campaign sends only those.
- A campaign `submit` refuses `LEDGER_EVENT_TOO_LARGE`, before sending
  anything, when a slot's units would not fit in one ledger line.
- `remote-parallelism schedule` and `assess` check that each unit fits one
  session with a margin: a unit whose duration plus setup is over 80% of the
  account's session limit is refused (`unit-over-session-margin`, or
  `split-first` in `assess`). Split it along seeds, folds or subjects, or
  declare the step `resumable` with a `checkpointMinutes` interval; a resumable
  unit is then planned over chained sessions on the same account, paying the
  setup in each one.
- The walk and build agents, and the `proposal-implementation` and
  `experimental-implementation` skills, now state the rule: every remote unit
  fits one session or checkpoints and resumes; after a cut session, `fetch`,
  then `remaining`, and resend only what is left. On Kaggle a checkpoint can be
  carried to the next session as the previous kernel's output
  (`kernel_sources`, read at `/kaggle/input/notebooks/<owner>/<slug>/`);
  papersmith does not attach it automatically yet. On Colab, upload it.

### Changed

- A job is identified by its service and its name. Two job folders with the
  same name under different services no longer shadow each other in the job
  lookup, the readiness map or the flow. When a name is ambiguous, `gate` and
  `launch-plan` refuse `JOB_SERVICE_AMBIGUOUS`: pass `--service <service>`,
  the service the step declares.

### Fixed

- `fetch` no longer records a failed, timed-out or reclaimed run as
  `returned`. It records it as `errored`, with `runState` (`failed` or
  `unknown`) and `artifactPath`, and keeps whatever came back under
  `.remote-execution/partial/` instead of a results tree, so the partial
  result can still be read and later fetches are not blocked. On Kaggle, only a
  `COMPLETE` kernel counts as a complete result.
- Readiness is per worker. `readiness` used to read only the latest rehearsal
  of a job, whatever account ran it, so rehearsing a second account made the
  first one not ready: two accounts could never be ready at the same time.
  Each worker is now judged by its own latest rehearsal.
- The implementation `probe` now reads each job folder's own readiness, so a
  job whose rehearsal passed is reported as `launch`. Before, it was never
  reported as `launch` and kept asking for a rehearsal that was already done.

- The experiments panel now shows figures and tables kept in one folder per
  experiment: a file in a `figures` or `tables` folder at any depth under
  `Results/` (for example `Results/e1/figures/`), and `Results/<experiment>/summary.json`.
  Only `Results/figures/`, `Results/tables/` and `Results/summary.json` were read
  before, so a product with `Results/e1/`, `Results/e2/` ... showed none of them.
- Run records the panel never shows (for example `Results/<experiment>/runs/*.json`)
  no longer use up the 200-file limit per product, which used to stop the scan
  before a campaign's figures were reached. The walk itself is bounded separately
  and warns when it stops.

## 0.30.3

### Changed

- The Smith Doctor tab no longer waits on serial probes. The wiring check
  runs the skills' front-door `--help` probes concurrently, keeping their
  order; an expired report is served while one background rebuild replaces
  it (re-measuring still rebuilds in line); and `smith ui` prepares the
  report at startup, so the first visit is immediate.


## 0.30.2

### Changed

- The Historia con IA and Experimentos tabs no longer block on load.
  Historia con IA reads each chat session incrementally: a visit parses only
  the lines appended since the last one and skips lines that hold no turn
  before parsing them (0.37 s to 0.01 s per visit on a workspace with a
  39 MB session). Experimentos serves its interpreter and CLI probes from
  cache past their 5-minute TTL while one background run refreshes them,
  instead of waiting ~3.5 s for four serial probes, and `smith ui` fills both
  caches in the background at start.

## 0.30.1

### Changed

- The Historia con IA phase detail lists the phase's artifacts (its evidence
  files, newest first, with type, size and date) and every interaction that
  names a workspace file shows its path. Each path is a link that opens the
  file in a window over the dashboard, in the dashboard's own style: Markdown,
  JSON and LaTeX rendered as in the Artefactos viewer (with a source toggle),
  PDFs and images embedded, HTML and code as their source. The window can
  hand the file to the Artefactos tab or a new tab and closes with Esc. Paths
  outside the workspace are never linked.

## 0.30.0

### Added

- The command center has a **Historia con IA** tab, before Telemetría y
  Costos. Its diagram draws every phase followed by its gate: red when the
  phase has not run, orange when it shows errors, rework (more than one
  proposal revision or deliberation edit) or iterations with the operator,
  green when it passed directly. Clicking a phase shows its summarised
  history: decisions, revisions and the chat turns of the workspace's
  Claude Code, Pi and OpenCode sessions, attributed to the phase whose
  command opened them. Antigravity keeps no readable chat history and is
  reported as such. `GET /api/ai-history` serves it read-only; an agent
  running outside WSL is pointed to with `PAPERSMITH_CLAUDE_CODE_SESSIONS`,
  `PAPERSMITH_PI_SESSIONS` or `PAPERSMITH_OPENCODE_SESSIONS`.

## 0.29.0

### Added

- `datasets prepare --seeds <n> <n> ...` writes one subject-wise split per
  seed under `repetitions` in `splits.json`, for repeated cross-validation,
  and lists every repetition's folds in `PREPARATION.md`. Each repetition
  takes the subjects largest first in size strata of `--folds` subjects that
  its seed shuffles, so folds stay balanced and every seed gives its own split.
  The first repetition is also the top-level `assignment`, so readers of a
  single split keep working. Two seeds that give the same split are refused
  `identical-repetitions`; `--seed` and `--seeds` together, or a repeated
  seed, are refused `bad-argument`.

### Fixed

- `datasets prepare --seed` now warns `inert-seed` when every subject has a
  different size. Its split sorts subjects by size after the seeded shuffle,
  so the seed only breaks ties between equal-sized subjects: on such a
  dataset every seed gives the same split, and a protocol that repeats its
  cross-validation over several seeds would have repeated one split. The
  split itself is unchanged, so existing preparations reproduce.

## 0.28.1

### Fixed

- A ladder item `@step <step>` whose step runs remotely (declared
  `placement: "remote"` with a `job`, or named after a job folder) is now
  measured from the main remote-execution ledger: `position` ticks it once a
  `fetch` has returned a current result for that job, at the job's current pin
  as recorded by the runner's own `bootstrap.json`. A pending or errored
  submission, a smoke-only record or a result from an older pin leaves it
  unmeasured, with the reason. Local `@step` items are unchanged.

## 0.28.0

### Added

- `launch-plan`, a read-only implementation command that lists what a job
  still needs before launch (`propose`, `offer`, `gate`, `submit`), the
  refusal each act would raise now, and the exact next command. It reuses the
  acts' own checks and writes nothing.
- `verify` reports `launchLadder` when the AGREED ladder is missing a
  `@rehearsal <job>` item for a remote step or has ticked items no
  measurement backs, so both surface before `generate-job` instead of at the
  gate.
- New targets are scaffolded with `src/<Package>/remote_stamp.py`, which
  writes the `shard.json` evidence stamp under the remote runner (commit,
  source digest, device), and `tests/test_remote_readiness.py`, which checks
  the stamp and guards the forward against mixing devices. Existing targets
  get both with one more `materialize --stage scaffold`.

### Changed

- `generate-job` clones the run notebook on its own when no declared clone
  path covers it, so a change to an unrelated notebook no longer stales the
  pin. Declaring the whole notebooks folder still works and still pins every
  notebook in it.
- `position --reconcile` inserts a missing `@rehearsal <job>` item right
  before the step that runs that job remotely, instead of appending it.

### Fixed

- The `generate-job` import and read scanner recognizes the kit's own
  notebook bootstrap cell and its `ROOT / "src"` path insert, which no longer
  require `--accept-unresolved` or `--accept-unresolved-reads`.
- The walk agents and the remote-execution doctrine say to fetch a Colab run
  as soon as `poll` reports it complete, because the service reclaims the
  idle session and its results with it.

## 0.27.0

### Fixed

- `fetch` asked while a remote run is still going no longer leaves an empty
  `.partial/` folder that refused every later fetch of the same submission. A
  partial that holds any bytes keeps the existing refusal.
- Notebooks fetched from Colab come back as JSON. google-colab-cli 0.6.0
  writes a downloaded notebook as a Python dict repr; the adapter now restores
  it, through `ast.literal_eval`, so the remote bytes are never executed.
- `smoke record --from-artifact` accepts the fetched rehearsal folder and reads
  the `shard.json` inside it. When the stamp is missing, the refusal says the
  smoke must write it into its working directory.

### Added

- `generate-job` reports a `warnings` entry when a smoke block declares no
  `--smoke-required-evidence`, since such a rehearsal passes on any stamp.

## 0.26.1

### Fixed

- The Experimentos tab opens with an "Antes de lanzar" notice listing every
  experiment diagram still awaiting validation, each linked to its product, so
  the diagrams no longer sit below eight setup sections.
- A dashboard server started before `smith upgrade` keeps the old release's
  code in memory while serving the new panel, so diagram buttons went missing
  and "Validar diagrama" reached no route. `/api/experiments` now reports the
  release the server started with and the workspace's current one, and the
  panel asks for a restart when they differ.
- The dashboard's page and scripts are served with `Cache-Control: no-cache`,
  so a reload after an upgrade revalidates them instead of running a cached
  panel.

## 0.26.0

### Added

- **`smith doctor` and the Smith Doctor tab.** `smith doctor [<dir>] [--json]`
  prints one table of project health rows (`ok`, `absent`, `warn`, `fail`):
  framework versions and drift, the workspace interpreter's packages, external
  tools (TeX, rasterizers, git, node, micromamba; found on `PATH` or in the
  known TeX directories, so macOS, Linux and WSL behave alike), skills,
  agents and the dashboard's phases. It exits `4` when a row fails. The
  dashboard shows the same rows in a new **Smith Doctor** tab after
  Telemetría y Costos (`GET /api/doctor`, cached 30 s; "Volver a revisar"
  re-measures).
- **`experiment-diagrams`, a skill that draws the proof of concept and the
  full experiments.** `derive --target <repo> --name <Name> --kind
  poc|experiments` drafts a diagram spec from the product's approval
  (`AGREED.md` or `Experimental_AGREED.md`, refused `APPROVAL_ABSENT` without
  it) and the revision it names; `render --spec <path>` validates it
  (`SPEC_INVALID` naming the field), writes `diagrams/<kind>.tex` from
  papersmith's own TikZ library, compiles it with shell escape disabled and
  rasterizes it to PNG (`TEX_TOOLCHAIN_ABSENT` / `RASTER_TOOLCHAIN_ABSENT`
  when the tools are missing, the `.tex` kept); `status` reports what exists.
  The design discipline (one claim, one spine, one focal zone, a shape per
  role, two connector prominences, grayscale-safe palette) restates the ideas
  of Sivia (github.com/exsinger-hub/Sivia) in the skill's own words. The two
  implementation skills call it once each approval is settled.

- **Colab jobs ask for a GPU by default.** The Colab adapter now registers
  a default accelerator (`cuda`, `sm_75`), as the Kaggle adapter already did,
  so `generate-job --service colab` with no `--accelerator-*` flags writes the
  `accelerator` block and `submit` requests `--gpu T4`. A runtime that arrives
  without CUDA is refused at the worker's bootstrap gate, so a CPU smoke no
  longer passes as ready. Before, such a job ran on CPU silently. Ask for an
  A100 or H100 with `--accelerator-kind cuda --accelerator-architecture sm_80`
  (or `sm_90`).

### Fixed

- **`generate-job` no longer hangs on a system credential helper.** The
  pin-published probe dropped `HOME` (so `~/.gitconfig`) but still read the
  system git config, and Homebrew's git names `osxkeychain` there. With no
  `HOME`, that helper waited on the macOS keychain until the 240 s budget
  expired, so a published commit was refused as unconfirmable whenever
  `--repo-credential` was given. Every `_run_git` call now resets
  `credential.helper` to empty through `GIT_CONFIG_COUNT`, so only the probe's
  own askpass answers.

- **One TeX and rasterizer search on every platform.** `smith doctor`,
  `experiment-diagrams`, the dashboard's paper compile and its health panel
  now look on `PATH` first and then in the same directories (MacTeX's
  `/Library/TeX/texbin`, Homebrew, `/usr/local/bin` and TeX Live's
  `/usr/local/texlive`, `/opt/texlive` and `~/texlive` trees, newest year
  first). The dashboard no longer compiles only when TeX sits in a macOS
  directory or on `PATH`, and its health panel reports `pdflatex`, `xelatex`,
  `lualatex` and `latexmk`.

- **`smith ui` opens the browser on WSL and headless Linux.** Under WSL the
  dashboard is handed to the Windows browser with `wslview`, then
  `explorer.exe`, before Python's `webbrowser`; on Linux without `DISPLAY` or
  `WAYLAND_DISPLAY` the URL is printed instead of starting a text browser on
  the server's terminal. macOS is unchanged.

- **LF line endings everywhere.** A root `.gitattributes` keeps text files,
  and shell scripts explicitly, at LF in every checkout, so a clone made by
  Windows git into `/mnt/c` still runs `setup-harnesses.sh` under WSL; images,
  fonts, PDF and cmap assets are marked binary. No tracked file changes bytes.

- **Dashboard live updates on a Windows drive under WSL.** When the workspace
  resolves under `/mnt/<letter>/`, the watcher polls (`force_polling`), since
  inotify sees no change made from Windows there. `docs/wsl-dashboard.md` now
  recommends the Linux filesystem, names the Developer Mode requirement for
  symlinks on `/mnt/c` and `localhostForwarding=true`, and lists how
  `smith ui` opens the browser.

## 0.25.0

### Added

- **A `capacity` toy profile in the datasets skill.** `synth --kind eeg
  --profile capacity --rule {monotone,interaction,frequency-two}
  [--d-prime D] --seed K` writes one replicate of fresh training, validation
  and test subjects (60, 10 and 100 by default, 12 epochs each, the
  19-channel montage) as a float32 `.npy` with a JSON sidecar: narrowband
  Theta, Beta and Alpha over an AR(1) background, neighbour mixing, frontal
  blinks and a class effect on the frontal and central channels, under a
  monotone rule graded by d′ (Bayes limit Phi(d′/2)), an interaction rule
  and a frequency-two rule. The generator (`scripts/capacity_toy.py`) is
  stdlib and seeded, so a remote notebook regenerates a replicate instead of
  downloading it. Options the profile cannot honour are refused; a replicate
  already written needs `--force` (`member-exists`).

## 0.24.0

### Changed

- **A run past 20 minutes locally goes to the cloud.** `remote-parallelism
  estimate` now reports `placement` per stage and `placementRules`: a stage
  whose local upper bound exceeds 1200 s is placed on the fastest measured
  cloud host, or on none with a request to time one first. The dashboard's
  run options apply the same limit to both stages (it was 30 minutes, proof of
  concept only) and state the rules above the table; `local_poc_limit_seconds`
  is replaced by `local_limit_seconds` and `poc_budget_seconds`.
- **A proof of concept is sized to 5 hours.** `placement.pocBudget` reads
  `within`, `exceeds` or `unmeasured` on the host the proof of concept is
  placed on, and the dashboard flags `excede 5 h`; the implementation skills,
  the experimental deliberation, the walk and build agents and the paper flow
  say to reduce the design before the pilot instead.

## 0.23.1

### Fixed

- **A successor no longer drops decisions silently.** `CREATE_SUCCESSOR` with
  a single `selectedEntryId` and `resolvedDecisions` for other sections too
  applied only the selected section's decision and published the rest away;
  it now refuses with `DECISIONS_OUTSIDE_SELECTION`, naming the other loci in
  `outsideSelection`, before any preview. Batches that name only other loci
  keep their existing refusals.
- **The forge interpreter no longer needs optuna or matplotlib.**
  `hyperparameter-search`'s `optuna_report.py` runs under the target's venv;
  its imports are now guarded, so the forge gate stops counting them as forge
  requirements (0.23.0 failed `test_the_named_interpreter_carries_every_import_the_forge_requires`).

### Security

- **Command center binds to loopback unless a network bind is asked for**, and
  keeps the Host header check on (#96).
- **Command center escapes scouted candidates and refuses cross-origin
  actions** (#99).
- **remote-execution sends the Kaggle credential only to Kaggle origins.**
- **Setup pins micromamba and verifies its SHA-256 before running it.**
- **Deliberation rejects path traversal** in managed revision names and
  sidecar writes.

## 0.23.0

### Added

- **Hyperparameter search with Optuna, when the deliberation judges it
  worthwhile.** A new `hyperparameter-search` skill validates a plan
  (`<Name>/hpo/plan.json`: one trial budget for every arm, baselines
  included; a seeded sampler; a search nested inside each outer fold's
  training subjects; nothing the experiments test tuned; the importance
  evaluator always named, because Optuna 5 defaults to PED-ANOVA), estimates
  its cost from `Results/timing.json` as an upper bound, and after the search
  ran writes one `Results/hpo/<arm>-fold<k>/summary.json` per study with
  hyperparameter importance, contour and optimization-history figures. It
  never launches a search: remote runs still go through `remote-execution`
  and the operator's launch.
- **The Experimentos tab shows the search.** Best parameters per arm and
  fold, importance bars labelled with their evaluator, and the contour,
  importance and history figures; Phase 5 lists the optional search as
  sub-phase 5.10 (the later sub-phases move to 5.11–5.13).
- The experimental-deliberation and experimental-implementation skills say
  when a search is worth declaring and where its step sits.

## 0.22.1

### Fixed

- **Toy sets for subject-level protocols.** `datasets synth --label-per
  subject` gives every subject one class, balanced across subjects; the
  default `trial` (classes alternating within each subject) is unchanged byte
  for byte. A protocol that decides per subject could not be piloted on the
  old shape, because a subject carrying both classes has no label to score.

## 0.22.0

### Added

- **Processing-time estimates for the proof of concept and the full run.** A
  short timing probe (one epoch of one fold per arm, on the target's own
  interpreter) writes `Results/timing.json` with the device and the scales
  copied from the approved protocol; `remote-parallelism estimate` turns it
  into a range per stage and per host (mean of per-arm means × epochs × folds
  × seeds × arms, plus measured setup, ±20%), and a remote host is estimated
  only from its own measurements, never from local timings. The
  implementation skills and the walk and build agents report the estimate
  before asking for a pilot or a launch.
- **Local environment and run options in the Experimentos tab.** "Entorno
  local" shows the workspace micromamba environment, each implementation
  venv with its Python version, the libraries it declares and which are
  installed or missing, and the device torch sees (one isolated probe per
  interpreter, cached). "Opciones de corrida" lists, for the proof of concept
  and the full experiments, local, Kaggle and Colab with availability, the
  estimate or "sin medir", the reason and a recommendation. Fase 5 gains
  "Estimar tiempo y elegir dónde correr".
- **Google Colab beside Kaggle, under a team model.** Several accounts per
  service, one per person: `smith team add|list|remove` keeps
  `.papersmith/team.json` (owners, their Kaggle username and Colab tier; no
  secrets, git-ignored) and refuses a member without `--attest` or an
  account already owned by someone else. `smith colab login|status` signs
  each owner in with the official `google-colab-cli` (pinned 0.6.0) under a
  private per-owner `HOME`, the only thing that isolates its token; papersmith
  never opens a file inside it. The remote-execution Colab backend exposes one
  worker per owner and refuses a free-tier account as a worker of a split
  campaign, quoting the Colab FAQ, which disallows "using multiple accounts to
  work around access or resource usage restrictions" and distributed workers
  on free runtimes. Kaggle's own terms could not be read, so the same
  one-account-per-person rule applies. `smith init` and `smith upgrade`
  register Google's official Colab MCP server (pinned commit) for every
  harness; it drives a notebook open in the browser, for interactive work.
  `remote-parallelism` now counts distinct owners, excludes free Colab tiers
  from splits and refuses mixing services in one campaign unless the shard
  stamps are declared identical. The Experimentos tab adds Colab rows to the
  services table, a team table and a Colab activation box with
  environment-specific steps.
- **Remote services table in the Experimentos tab.** A short table states, for
  the official MCP server, the official CLI, the token, the worker accounts,
  the remote rehearsals and the weekly GPU quota, whether each is active,
  inactive, not installed or unverified, with the one command that activates
  it run through the CLI assistant. Offline on every poll; the CLI version is
  cached and the quota is read only on `smith mcp kaggle status --verify`.
- **`remote-parallelism` skill.** `assess` decides from measured inputs (unit
  duration, units, accounts, sessions per account, session limit, weekly
  quota, setup cost) whether a proof of concept or a campaign is worth
  spreading over several remote GPU accounts: serial, single-account and
  parallel makespans, speed-up, quota per account and a verdict
  (`parallelize`, `single-account`, `split-first`). `checklist` and
  `stamp-fields` state the reproducibility rules: split only along the
  declared axis and never by arm, seed from the unit id, identical commit,
  environment and accelerator on every account, a per-shard environment
  stamp declared identical across shards, deterministic flags, one rehearsal
  per account. The walk, build, reviewer and replicator agents run it before
  generating jobs for more than one unit; the verdict never authorizes a
  launch.

### Fixed

- **A stopped or expired phase run no longer stays stuck.** The tracker reads
  the server's verdict before its quiet expiry, and a run that was stopped or
  stopped being followed reads verified once its phase passes, instead of
  showing "detenida" for a phase that is already PASS.

## 0.21.1

### Added

- **`datasets synth --profile theta-beta`.** An EEG toy set whose Theta (6 Hz)
  to Beta (20 Hz) power ratio depends on the class, for proofs of concept of
  methods that rest on that biomarker. The default `alpha` profile is
  unchanged byte for byte.

## 0.21.0

### Added

- **Data and comparison-method replication in the paper flow.** Phase 5 gains
  two explicit steps, "Datos: toy set siempre y dataset oficial" (`/datasets`)
  and "Réplica de métodos de comparación" (`paper-replicator`), in the phase
  actions, the dashboard sub-phases (5.6 and 5.7) and the entrypoints' paper
  flow. The Flujo Archify diagram draws a datasets lane (`dataset-scout`,
  `dataset-curator`, the upload-consent gate), the replication row and
  `experiments-reviewer`, and the same pane lists every agent of the project
  (`GET /api/agents`): role, skill, stage, tools, the phase or phases it acts
  in, and the harnesses it is projected to.
- **`paper-replicator` adopts published code first.** It searches for the
  paper's own code and records the search; when code exists it is pinned to a
  commit with its license and audited against the paper (`match`,
  `deviation`, `unspecified`) and run through its own tests plus the
  invariant tests and toy-set smoke run; reimplementation from the paper is
  the fallback.
- **`paper-replicator` agent.** A `proposal-implementation` stretch
  (`fidelity`) that reimplements a referenced method with no public code from
  its ingested Markdown and the cited papers it depends on: plan, analyze,
  code, then invariant tests and a toy-set smoke run before any GPU run, with a
  `REPLICATION.md` table tying every hyperparameter to a section or equation or
  marking it `unspecified`. It runs as a subagent of the active Claude Code,
  OpenCode or Pi session on that session's model: no API key and no external
  LLM service.
- **`datasets` skill with `dataset-scout` and `dataset-curator`.** A stdlib
  CLI (`synth`, `search`, `license`, `qc`, `prepare`, `publish`, `status`)
  over a `datasets/registry.json`: a seeded toy set for every proof of
  concept, search across the remote dataset host's MCP, Hugging Face,
  OpenNeuro and Zenodo (Google Dataset Search only as a manual link), license
  decisions that refuse NC, ND and credentialed sources unless overridden,
  quality reports, one stratified group split shared by the proof of concept
  and the full experiments, and private publishing through the official
  client with an explicit consent per dataset and a separate one before it
  becomes public. The Experimentos tab lists the registered datasets.
- **Kaggle MCP instructions follow the environment.** The activation box and
  `smith mcp kaggle status` detect macOS, Linux, WSL or Windows, the login
  shell (zsh, bash, fish, PowerShell) and the user, and print the export
  command and profile file for that combination instead of fixed text; WSL and
  Windows get a note on where the token lives. The token now lives where
  Kaggle's own client keeps it, `~/.kaggle/access_token`, so one token serves
  the MCP server, the `kaggle` CLI and `kagglesdk`; a token already there is
  reused, a different one is never overwritten without `--replace`, and the
  0.20 location still reads. `smith init` and `smith upgrade` print an offline
  activation line and warn when `npx` is missing for Pi or Antigravity.
- **`smith mcp kaggle activate|status|deactivate`.** Activates the official
  Kaggle MCP server for this user: a hidden prompt (or `--token-stdin`) takes
  a `KGAT_` token, a read-only `get_accelerator_quota` call verifies it
  (`--no-verify` skips the call), and it is stored outside every workspace in
  `$XDG_CONFIG_HOME/papersmith/kaggle-mcp-token` (`0600`). The dashboard's CLI
  assistant passes it as `KAGGLE_API_TOKEN` to the sessions it starts unless
  that variable is already exported; a symlinked or group-readable file is
  never used. The Experimentos tab shows the activation state and has buttons
  that run `smith mcp kaggle activate` and `status --verify` in the CLI
  assistant, which also offers both as quick commands.
- **Kaggle's official MCP server in every workspace.** `smith init` and
  `smith upgrade` register `kaggle` (https://www.kaggle.com/mcp) beside
  `banco-lia`: streamable HTTP in `.mcp.json` and `opencode.json`, the pinned
  `mcp-remote@0.14.3` stdio bridge in `.pi/mcp.json` and
  `.agents/mcp_config.json`. Public tools answer without a token; account
  tools (`save_notebook` with `enableGpu`/`machineShape`, session status,
  outputs, accelerator quota) read a `KGAT_` token from `KAGGLE_API_TOKEN`,
  which no file holds. Other servers in those files are kept.
- **Significance tests chosen by experiment type.** `experimental-deliberation`
  gains a "Choosing the significance test by experiment type" section: a table
  mapping each design (two models on shared folds, three or more variants, one
  fixed test set, an ordered factor, an exponential decay, repeated measures
  per subject) to its recommended test, plus multiple-comparison corrections,
  effect sizes and the optional Bayesian signed-rank with ROPE. Every
  experiment now names its test, correction, effect size and confidence
  interval, and declares convergence curves and a significance table among its
  expected outputs. It also states that a paired Wilcoxon over n = 5 folds
  cannot reach p < 0.05 (smallest two-sided exact p is 0.0625). The
  `experimental-validation` agent suggests a test per experiment type, backed
  by a source it actually searched.
- **`experiments-reviewer` agent.** A read-only review stretch of
  `experimental-implementation`, between instrumentation and the rehearsal:
  code quality, optimisation (batched simulation, exact-gradient simulators,
  data caching, mixed precision), remote GPU use (whether a job that requests
  a GPU actually runs on CUDA, and when CPU is faster), and whether the
  protocol's statistical tests are implemented and fit the design. It returns
  findings and never repairs.
- **Results layout documented.** `experimental-implementation` states where
  measurements land so the dashboard can show them: `Results/history*`,
  `Results/figures/`, `Results/tables/`, `Results/summary.json` and
  `Results/significance*.json`, with the significance record's keys.
- **Experiments tab in the command center.** A new "Experimentos" tab, placed
  before "Secciones del Paper", reads `GET /api/experiments`: proof-of-concept
  products (`AGREED.md`) and full-experiment products
  (`Experimental_AGREED.md`) with convergence charts that are always shown
  (empty state when no history exists), figures, tables, the significance
  table, artifacts pinned in `Results/panel.json`, run status folded from each
  product's remote ledger, and the expected reports the latest experiments
  revision declares. A help box explains how to launch and monitor proof of
  concept and full experiments remotely (papersmith CLI, the service's own CLI
  and its MCP server), GPU use, optimisation, and which significance test to
  report. `/api/artifact` now serves `.svg` as `image/svg+xml` under a
  sandboxing Content-Security-Policy.

## 0.20.0

### Added

- **banco-lia MCP registered for every harness.** `smith init` and
  `smith upgrade` now register the lab's article and project bank as the
  `banco-lia` MCP server for every declared harness (Claude Code, OpenCode, Pi,
  Antigravity), keeping any other server already in those files. `uv` must be
  on `PATH` to start it (see `docs/mcp.md`).
- **TeX / compiled toggle for the dashboard's mathematics.** The "Mapa
  Conceptual & Modelo" tab keeps each formula's LaTeX source beside its KaTeX
  rendering; a button in the concept-map and math panel headers switches the
  whole tab between both views and the browser remembers the choice.
  Concept-map layers, pillars, hypotheses and proof-of-concept text now compile
  `$…$` math, still escaped before insertion.

### Fixed

- **Model-tab contrast in the light theme.** The header banner follows the
  theme, workspace spec colours are lightened or darkened to keep WCAG AA
  contrast, and badges, hypothesis cards and secondary text no longer fall
  below 4.5:1.

## 0.19.5

### Fixed

- **Pi package cache is ignored by Git.** Added `.pi/npm/` to `.gitignore` and
  to `src/papersmith/templates/gitignore.tpl` so dynamic package resolution by
  Pi (such as `npm:pi-web-access` declared in `.pi/settings.json`) does not
  leave untracked files in the repository or in generated workspaces.

## 0.19.4

### Changed

- **The section contracts carry the lab's house style.** Each contract that
  governs prose (`01`–`09`) gains a `## LIA house style` section measured on the
  group's ten Q1 method papers of 2025–2026 (SJR 2025): the paragraph, word and
  line ranges of the section, its citation density, its rhetorical moves and
  the wording the group uses. The methods contract adds the notation rules —
  bold lowercase vectors, bold uppercase matrices and tensors, declared spaces,
  calligraphic sets and losses, upright operators, `^{\top}`, punctuated
  equations followed by a *where* clause — and now numbers every displayed
  equation. The title range moves to 10–13 words, and the methods and results
  contracts add disqualifiers for notation and for unreported significance or
  bold. The Spanish copies shown in the dashboard follow.

## 0.19.3

### Changed

- **The gates moved into "Pipeline y Avance".** The "Compuertas (Gates)" tab
  is gone; its panel now closes the pipeline tab, below the phases it guards,
  and an old `#gates` link opens it there. "Telemetría y Costos" moved to the
  last tab, after "Artefactos".
- **The section drawer reads in Spanish.** "Inspeccionar Reglas & Artefacto"
  in the paper-sections tab shows each section contract translated, plus the
  section title, its status and the contract's terms. The contracts under
  `sections/` stay in English, because the writing engine checks their quotes
  against their own text. A translation is shown only while the workspace's
  contract is byte-identical to the one it was made from; an edited contract
  shows as itself.

### Fixed

- `smith upgrade` again rewrites the `.gitignore` managed block of workspaces
  created before 0.19.0. That release renamed the command in the block's
  opening marker, so upgrade read the old marker as malformed and left the
  file alone, reporting it as drift.

## 0.19.2

### Added

- **Opt-in initialization in an existing directory.** `smith init --import-existing`
  stages the framework before merging it into a nonempty directory and does not
  overwrite existing files: it keeps the directory's `README.md`, merges its
  managed block into an existing `.gitignore`, and refuses any other collision.
  The default still requires an empty destination. See the init section of the
  README for rollback limits.
- **`smith init` defaults to the current directory.** `<dir>` is optional on
  every operating system; `smith init` alone sets up the folder it runs in, and
  a path still installs there.
- **Pi workspaces declare `pi-web-access`.** `init` writes `.pi/settings.json`
  with that package, and `upgrade` adds the file to a workspace that lacks it,
  so Pi installs the web tools its agents use once the project is trusted. An
  existing `.pi/settings.json` is never changed.

### Fixed

- **The dashboard opens a Windows browser from WSL** if Linux has no browser
  handler. `--no-browser` and ordinary Linux/macOS launches are unchanged.
- Pi agent projections map Claude's `WebSearch` and `WebFetch` to the
  `pi-web-access` tools `web_search` and `fetch_content`. Generated agents no
  longer report misleading missing-tool warnings.
- The paper-ingestion audit recognizes all eight current CLI flags.
- WSL environment provisioning includes `python-build`, and packaging checks
  distinguish a runnable build tool from the checkout's `build/` directory.

## 0.19.1

### Changed

- **Phases run in the herdr session by default.** "Ejecutar" on a phase card
  now types its slash command into the command center's herdr session when
  herdr is installed, as RedaccionPropuestas does, instead of closing herdr and
  opening claude/opencode/pi. Without herdr, the phase opens a new claude
  session (or the first installed agent). The operator can still pick another
  agent per phase.

## 0.19.0

### Changed

- **`smith` is the canonical command.** Help, usage and error messages, the
  MCP client snippet (`smith mcp serve`), the command center's phase actions,
  generated workspace docs and the README now use `smith init`,
  `smith upgrade`, `smith status` and the rest. The `papersmith` entry point
  stays installed as a compatibility alias and reports itself as `smith`.

### Added

- **Page-routed, license-unrestricted paper ingestion.** The default engine is
  now `auto`: each page is probed without a model and digital prose is read by
  pypdfium2 in milliseconds; only display-equation, table and scanned pages go
  to Docling through its page range (formulas as LaTeX with Granite-Docling on
  MLX on Apple Silicon or CodeFormulaV2 on CUDA, TableFormer only on table pages,
  RapidOCR only on scans). Every page is cached by the PDF's SHA-256 and
  verified before reuse (`--verify-cache`). Each paper gains a `<stem>.json`
  page map with references kept by page, and `pdf_fragment.py` / the MCP tool
  `papersmith.ingest_fragment` return one page, section, equation or search hit
  without the whole document. New flags `--engine` and `--no-cache`; new keys
  `cache` and `formulas_on_cpu`.

- **2D constellation and a lighter SOTA sky.** `atlas.html` opens a canvas
  2D view of the same scene when the 3D sky cannot or should not run (no
  WebGL, a software renderer, under 4 GB of memory or 4 cores, or under 20 fps
  in its first seconds) and says why; a view button and `?view=2d|3d` switch
  by hand. System names replace the overlapping title sprites and appear only
  where they fit. The home view fits every planet in the frame, the canvas
  keeps one pixel per CSS pixel on zoomed-out displays, orbit rings and family
  ties are one draw call each, an idle sky is not redrawn, and either view
  stops drawing while the page is hidden. New toolbar controls turn, tilt and
  pause rotation. Playwright checks in `ui/e2e/atlas.spec.ts`.

- **Live run tracker for pipeline phases.** "Ejecutar" opens a tracker in the
  phase drawer and marks the card as running. It follows the run through five
  steps: command sent, agent working (the terminal's output), the phase's
  evidence files appearing or changing, the server's verdict, and the phases the
  verdict unlocked. It polls every 3 s while a run is open and shows a notice
  when a phase is verified.
- **Evidence and prerequisites per phase.** `/api/status` lists, for each phase,
  the files it is judged by (count and last change), whether it is unlocked, and
  which phase blocks it. A phase is locked until the one before it passes (Fase
  1 and the transversal Fase 11 are never locked). A locked phase can still be
  run with an explicit override, since each skill still refuses missing input.
- **The operator picks the agent, and one session follows the pipeline.**
  - Each guided prompt has an agent selector (claude, opencode or pi).
  - It proposes the agent of the session already open, else the last one chosen.
  - It says whether the phase continues in that session or opens one.
  - Later phases reuse the same session. A new one opens only when the operator
    picks another agent or ticks "Nueva sesión", always after a confirmation.
  - A phase's `papersmith` command runs inside the open agent session as
    `!command` instead of replacing it with a shell.
  - The chosen agent is remembered across reloads.
- `POST /api/phase/run` answers with the phase's verdict (`status`, `verified`,
  `evidence`).
- **Follow a running phase from any tab.**
  - A click on the run dock (bottom left) opens the run's tracking panel in
    place, with the same checkpoints as the drawer. The operator stays on the tab
    they were on.
  - The panel opens the agent's terminal and says when the phase's session is no
    longer open. "Abrir en Pipeline" still leads to the drawer.
  - **"Detener proceso"** interrupts the agent's turn (Esc, or Ctrl-C in the
    shell) after a confirmation. It keeps the session and marks the run as
    stopped.
- `GET /api/terminal/sessions/{id}` reports a session's agent and whether it is
  alive, so a reloaded page can reattach to it.

### Changed

- **Marker is no longer the default ingestion engine nor installed by default.**
  Its model weights are free only below USD 5M in funding or revenue; every
  default engine now carries no copyleft and no revenue or user threshold.
  `engine: marker` still works as an explicit opt-in after
  `pip install marker-pdf==2.0.0`, and says why. The installer drops PyMuPDF
  (AGPL, unused) for pypdfium2, and `--no-ingestion` keeps the fast path.

- **A lighter dashboard, with the same views.**
  - `/api/status` reuses the module constants, YAML and PDF page count it
    parsed, until the file changes. On a real workspace a call went from
    about 31 ms to about 10 ms, and phase evidence is still read on every call.
  - A terminal output stream waits for the agent's output instead of waking
    every 12 ms. Its keep-alive ping is unchanged.
  - Closing the terminal window drops its stream only when no phase is
    running. During a run, the tracker keeps reading the agent's activity.
    Opening the window again reattaches the session.
  - The 3D atlas loads the first time its tab opens, and stops drawing while
    another tab is shown (new `atlas-command` `pause` / `resume`). Atlases
    regenerated with "Regenerar grafo" pick this up.
  - The browser's own PDF viewer fetches the PDF only when it is shown.
  - The run dock updates its clock in place instead of rebuilding itself
    every second.

### Fixed

- **A reload no longer kills the agent of a running phase.** While a phase run is
  live, the page keeps the CLI session on unload and reattaches to it on load.
- **A terminal reconnect no longer draws its output twice.** The stream replays
  the session from its start, so the screen is cleared before the replay.
- **Fase 11 can pass.** Verifying the audit phase runs `papersmith audit
  --check-drift` and records the verdict in `.papersmith/audit.json`. The phase
  passes only on a clean audit; nothing wrote that file before.
- The artifacts list refreshes when files change, and lists `experiments/*.md`.
- **"Ejecutar" in a phase drawer did nothing.** The drawer stops click
  propagation, so the phase console's document listener never received the
  click. The phase console and the run tracker now listen in the capture phase.
- When the agent opens with a startup question, the phase drawer now says
  which one. For Claude's folder-trust prompt it tells the operator to choose
  "Yes, I trust this folder" in the terminal and run again. The dashboard never
  answers that prompt itself.
- **A refused or stalled phase run is visible.** A long idea written as one
  run-on sentence (commas, no full stops) counted as one sentence and was refused
  with only a small grey hint, so nothing ran and no tracker appeared. Now a long
  text counts one sentence per 12 words, a refusal shows a red error box, and the
  drawer scrolls to the tracker when a run starts.
  - A floating dock (bottom-left, every tab) shows each followed run's progress
    and opens its phase.
  - When the agent stops writing for 20 s, the tracker and a notice say it
    finished its turn or is waiting for an answer in the terminal.

## 0.18.0

### Added

- **Runnable pipeline phases.** Each card of *Fases del Pipeline Metodológico
  de Redacción* opens a console. A guided text box shows the stage's rules and
  sends its slash command to an agent of the support terminal: for example
  `/plausibility <idea>`, which needs at least two sentences. The console also
  offers the phase's real `papersmith` command (run in the shell) and links to
  the panel that owns the work (concept map, math tutor, PoC board, sections,
  PDF preview, gates).
  - A slash command switches the terminal from herdr or shell to claude,
    opencode or pi.
  - The console never answers an agent's startup question (folder trust) with
    the command's Enter.
- **Paper construction flow in every harness.** The eleven phases, including the
  concept-map and mathematics discussion with `/math-tutor` and the
  proof-of-concept and experiment stages, are written into `CLAUDE.md`,
  `OPENCODE.md`, `.pi/APPEND_SYSTEM.md` and `.agents/AGENTS.md` from one
  template.
- **The archify flow draws the dashboard.** A new lane covers `/math-tutor`,
  `papersmith ui`'s phase console, `/api/model/math` and the tutor's thread.

### Changed

- The dashboard opens on *Flujo Archify*; *Pipeline y Avance* follows.
- Phase commands shown in the dashboard are commands that exist. `papersmith
  run --stage …`, `papersmith audit --figures` and `papersmith init
  --harness-only` never did.

### Fixed

- `POST /api/phase/run` routes by stage. It used to send *Fase 8* (writing) to the
  figures check, and *Fase 10* to the audit message. *Fase 10* now compiles the
  PDF only when `paper/main.tex` exists, and an unknown phase gets a 422.

## 0.17.1

### Fixed

- **A new workspace inherits nothing from older projects.** The dashboard no
  longer ships another project's specification, novelty graph, hypotheses,
  concept map, proof-of-concept results, candidate counts, phase messages,
  titles or an absolute flow-diagram path. The *Mapa Conceptual & Modelo* tab is
  drawn from the workspace's own `.papersmith/model_spec.json` (and, new,
  `.papersmith/novelty_graph.json`) or shows neutral pending states; phase
  actions report what is on disk; the framework's flow diagram ships with the
  dashboard. A guard test scans every shipped kit file and a fresh workspace's
  dashboard for traces of earlier projects.
- **Math tutor uploads and sources.** A polyglot image (a valid header followed
  by HTML or script) is refused; a proposal revision resolving outside the
  workspace is ignored; an invalid `model_spec.json` is not named as the math
  panel's source.

## 0.17.0

### Added

- **Math panel in LaTeX.** *Mapa Conceptual & Modelo → Matemática & Tutor* shows
  the paper's own equations rendered by KaTeX 0.16.22 (vendored, offline) as
  minimalist cards — heading, display equation, one-line *Conexión*, variables —
  under a lema, built by `GET /api/model/math` from the latest
  `proposals/research-concept-<slug>-rNN.md` (`$$`-fenced blocks with
  `\tag{N}`, outside code fences) and its `.sky.json`, else
  `.papersmith/model_spec.json`. Every equation the panel can show is compiled
  by KaTeX in strict mode in the test suite. The old hand-typed Unicode
  pseudo-math is gone.
- **Idea y novedad card**: central idea, novelty, problem, contributions and the
  key equation, beside the equations.
- **`math-tutor` skill and agent (Socratic tutor).** Drop, paste or pick photos
  of hand-written pages in the panel; each turn runs the agent headless with the
  user's own `claude -p` (only `Read`, JSON schema, no MCP, local settings only,
  stdin closed) or `pi -p`, reads the page back as LaTeX, asks one question,
  rates understanding 0–4 with quoted evidence and ties every step to the
  paper's novelty. Uploads and the thread live in `.papersmith/math-tutor/`;
  routes under `/api/terminal/tutor/` behind the terminal secret. Also
  available as `/math-tutor` in every harness.

## 0.16.1

### Changed

- **Smith CLI assistant.** The dashboard console becomes a round button at the
  bottom right with Smith's face (status badge, pulse) that opens a 780×520
  floating terminal, maximizable and hidden rather than closed. **herdr** is the
  default agent: the session focuses or creates the herdr workspace labelled
  after the project, so the console mirrors your herdr panes; `claude`,
  `opencode`, `pi` and a login shell remain, found also in `~/.local/bin`,
  `~/.npm-global/bin`, Homebrew and `~/.cargo/bin`, and the choice is remembered.
  **🖥️ Ghostty/WezTerm** opens herdr on the project in a native terminal
  (`GET /api/terminal/tools`, `POST /api/terminal/launch-external`). The server
  answers the capability queries full-screen TUIs send on the PTY itself,
  keystrokes are coalesced, and the console repaints when the tab regains focus.
  Only the herdr agent drops inherited `HERDR*` variables.
- **LabIA UNAL branding.** The laboratory logo now ships with the dashboard and
  appears only in the bottom-centre footer; the header keeps Smith's avatar and
  the laboratory line. The footer shows the workspace's framework version
  (`/api/status` → `framework_version`).

## 0.16.0

### Added

- **Graph toolbar: "⚡ Regenerar grafo" and "🧩 Disposición de grupos".**
  The dashboard's *Atlas* tab regenerates the SOTA atlas from
  `sota-pool/atlas.json` through `POST /api/atlas/build` (the workspace's own
  `check_atlas.py`, then `render_atlas.py`; a failing atlas never replaces a good
  page), and asks the atlas frame to regroup its systems by family cluster and
  back. The atlas page carries the same toggle; its default sky is unchanged.
- **`smith atlas build [<dir>] [--json]`.** The same rebuild from a terminal.
- **Cross-panel links.** Clicking a planet reports it to the dashboard, which
  offers *Ver en PDF* (finds the node in the compiled PDF and jumps to the page)
  and *Ver artefacto* (opens `sota-pool/atlas.json`).
- **Live PDF preview.** pdf.js 3.11.174 now ships with the dashboard;
  `/api/pdf` revalidates with an `ETag`, `/api/status` reports
  `run_details.pdf_mtime`, and an open preview reloads on recompile keeping the
  page being read (a reload that catches `main.pdf` mid-write keeps the current
  document and retries).
- **Support terminal ("CLI de apoyo").** A floating xterm.js console on a PTY in
  the workspace root (shell, `claude`, `opencode`, `pi`), with quick commands and
  *Enviar a CLI* on every phase card. Loopback only, a per-server secret set by
  the printed login URL as an HttpOnly SameSite=Strict cookie, same-origin
  guards, at most four live sessions; `smith ui --no-terminal` turns it off.
- **`smith` alias and dynamic dashboard state.** `smith` is installed next to
  `papersmith`, and the command center reads the project's model and novelty
  data from the workspace instead of hardcoded values.

## 0.15.0

### Added

- **PDF preview annotation unmarking suite with selective category controls and layer toggles.**
  The continuous PDF preview tab incorporates fine-grained unmarking controls:
  individual item unmarking checkboxes, selective category buttons for comments,
  strikethroughs, and humanization remarks, as well as a master toggle to clear
  all annotations. In addition, an annotation layer visibility control allows toggling
  annotations without permanently discarding them, and a topbar quick unmark dropdown
  makes annotation filtering accessible from anywhere in the document view.
- **3D Semantic Novelty Graph structured in 8 narrative pillars.**
  The 3D novelty knowledge graph models the scientific paper's narrative core across
  eight explicit thematic clusters:
  1. *Applications of interest* (`aplicaciones`)
  2. *Central problem* (`problema_central`)
  3. *Top 5 nearest State-of-the-Art benchmarks* (`sota_cercano`)
  4. *Core novelty and 2–3 key claims* (`novedad_central`)
  5. *Evaluated benchmark datasets* (`datasets`)
  6. *Performance metrics and comparative baselines* (`metricas_metodos`)
  7. *Top 3 empirical conclusions* (`conclusiones`)
  8. *Top 2–3 future research directions* (`trabajo_futuro`)
  Node sizes and distances are calibrated with constellation visual styling, smooth
  OrbitControls damping, auto-rotation yield on user interaction, and isolated mouse-wheel
  scroll delegation so the dashboard page remains smoothly scrollable without 3D canvas trapping.
- **Friendly web artifact and writing rules viewer.**
  Inspection drawers for paper section canonical blocks, operational writing rules, and
  intermediate phase artifacts now render cleanly formatted Markdown via `marked.min.js`,
  including structured tables, alert callouts, and code blocks, with a seamless toggle
  between formatted Web View and raw JSON/Markdown source.
- **Continuous multi-page PDF manuscript preview.**
  The manuscript preview tab renders documents in a continuous vertical scroll flow
  with page jump indicators, zoom controls, fit-to-width mode, and automatic resolution
  of partially drafted manuscript versions as research phases advance.
- **Interactive research lifecycle phase execution.**
  Workflow tracking in both CLI and dashboard enables step-by-step phase advancement
  (plausibility, SOTA matrix, experimental formulation, proof of concept, and section-by-section
  manuscript drafting) with illuminated phase badges and live status indicators.
- **Tabular candidate matrix for State-of-the-Art exploration.**
  The SOTA candidate matrix presents paper discovery candidates in a modern, user-friendly
  table layout with instant multi-field searching, metric score filters, and expandable abstract drawers.
- **High-tech Agent Smith anime companion branding.**
  Canonical character artwork and matching high-resolution favicons are integrated across
  the dashboard topbar, browser tabs, and documentation.

### Fixed

- **Deliberation engine turn preview flag stripping.**
  `call_engine_with_acceptance` strips premature `acceptSuccessor` flags during preview
  turns, ensuring safe dry-run candidate generation before explicit user acceptance.

## 0.14.0

### Fixed

- **MCP workspace resolution handles symlinked roots on macOS and Linux.**
  `resolve_under` resolves the workspace root before evaluating `relative_to`,
  preventing false `WORKSPACE_ESCAPE` refusals when the root path traverses
  standard operating system symlinks (such as `/var` pointing to `/private/var`
  on macOS).
- **An adopted finding reaches a terminal state instead of blocking the
  audit forever.** Once `proposal-deliberation` published a remedy and the
  target was re-bound to the successor revision, four readers disagreed about
  the finding: `verify`'s `remediesWithoutValidation` still demanded the
  `test_remedy_<id>` that `audit.migration` demands be retired, `admit
  --revision <successor>` ruled the finding inadmissible because the text the
  remedy replaces is gone (which is what adoption means), and the
  compatibility audit kept reporting `needs-deliberation` for the notation the
  remedy had introduced. The audit could only reach `ok` by deleting the
  finding. All of them now read one shared adoption state
  (`finding_adoption`): an adopted finding keeps its evidence
  (`test_finding_<id>` and its entry in `tests/findings.py`), owes no remedy
  validation, introduces no notation, and owes only the move `migration`
  checks. `admit` rules it admissible with an `adopted` verdict naming the
  revision and the expected form that confirmed it. `changed-unrecognized`
  (the replaced text gone, nothing expected in its place) is not adoption and
  stays inadmissible. Shared by `experimental-implementation`, which runs the
  same engine. The sealed CLI corpora already carried an adopted finding and
  had characterized the defect (ruled inadmissible, listed as unvalidated);
  their `verify` and `admit` goldens move accordingly.
- **Sibling implementation skills no longer collide on each other's
  checklist holder.** Once `proposal-implementation` had settled items into
  its declared `<Name>/AGREED.md`, `experimental-implementation` (declared
  holder `Experimental_AGREED.md`) refused every `position`/`settle` write on
  the same target with `HOLDER_UNDECLARED`, and both exits it offered —
  rename the sibling's file, or adopt its name — were destructive to the
  sibling. The same held in the other direction. `holder_resolution` now sets
  aside every holder filename a profile sharing the engine declares, derived
  from each `impl_profile.py` next to the loaded one (reading only
  `PROFILE["holder"]["filename"]`; a profile that cannot be read contributes
  nothing, so its file still refuses). A target holding only the sibling's
  holder resolves create-on-absent and the skill writes its own holder beside
  it. A checklist no skill declares still refuses, and the refusal and its
  question never name a sibling's holder as a file to rename. The read side
  follows the same rule: the agreements reader (`verify`, `close`)
  and the position reader (`verify`, `probe`, `gate`, `close`, `discuss`, `settle`, `offer`, `step`) no
  longer read the sibling's holder as this skill's, so its open items stop
  appearing as this skill's open agreements and its position block stops
  standing in for this skill's position.
- **`probe` no longer hides the pilot ladder when nothing is comparable.** A
  target whose comparison arms live inside its own package has no prior-work
  package under `src/`, so `probe` answered `nothing-to-compare` before any
  other rung, even with declared steps still short at pilot and, later, with
  every step finished at pilot and none placed. `pilot-first` and
  `pilot-decisions` never fired, so neither the rung question nor one
  per-step placement question was ever published. Comparability now answers
  the comparison only: with no baseline, `probe` returns `pilot-first` while a
  declared step is short and `pilot-decisions` (with its per-step questions)
  once the pilot is complete and a step is undecided, and
  `nothing-to-compare` only after both are settled. Shared by
  `experimental-implementation`.
- **A freshly scaffolded target no longer fails its own `verify`.**
  `materialize --stage scaffold` writes the kit's seal,
  `src/<Package>/report_digest.py`, which implements no claim and so declares
  no `__provenance__`; `verify` listed it under `missingProvenance` and read
  `fidelity: drift` on a target nobody had touched, under both implementation
  skills. The seal is now exempt only while it is still the kit's file: its
  path is a scaffold destination with a kit source (derived from the scaffold
  table, not a hand list), and its bytes equal today's kit source or the
  `writtenSha256` the scaffold receipt's `materialized` entry recorded (so a
  seal written by an earlier release still counts). An `adopted` or
  `authored` entry does not count, and a modified copy is reported as before.
- **`close` is reachable for a proposal-only target, and witness-less
  agreements have a recorded closing act.** `close` refused
  `POSITION_ABSENT` on every target without a position, and a position can
  only name execution witnesses (a step, notebook, record, rehearsed job or
  shard), so a target with no flow could pass only by installing an item
  pointing at a witness that does not exist. A position is now owed only
  when the target declares part of a flow (`__levels__`, `__steps__`,
  `__records__`, a shard root or a job folder); otherwise `close` checks the
  agreement and discussion axes, skips the refresh, and records the close
  over an empty sequence. Separately, an agreement no test could ever
  witness (a scoping decision, a premise, a deferral) could be ticked only
  by hand, so `agreements` stayed `open` unless someone edited the holder
  outside every command. `settle --done --unwitnessed --reason <text>` now
  ticks such a line and writes the operator's reason and the session to the
  ledger. It is never counted as witnessed: `agreements.witness` names it
  under `decided`. `--done` on a line that names a witness is unchanged, and
  `--unwitnessed` on such a line refuses `SETTLE_WITNESS_PRESENT`. Shared by
  `experimental-implementation`.
- **Deliberation gives one candidate the same verdict at v1 creation,
  preview and accept, and a code span is no longer a heading.** The three
  points ran three validation sets: `CREATE_INITIAL_REVISION` ran only the
  canonical-form rules, the `CREATE_SUCCESSOR` preview ran only the
  orchestrator's candidate validator, and only the accept turn ran the
  workspace's pre-publish set. The shared standalone-ATX check also read a
  backtick span such as `` `## Results` `` as a heading fused with prose. So
  a v1 carrying an inline-code `## ` published, every successor preview
  answered `awaiting_acceptance`, and every accept refused
  `atx-heading-standalone`: no successor could be published until unrelated
  text was reworded. The check now masks CommonMark code spans (a backtick
  run closed by a run of exactly the same length, on one line) before it
  looks for a fused marker; a marker outside code still refuses, and a span
  that crosses a line ending stays unmasked. The preview now runs the accept
  turn's own pre-publish validation (`successorCandidateRefusal`, the same
  function `derive_successor` runs before writing) and v1 runs the guarded
  first write's (`initialCandidateRefusal`). Both deliberation skills share
  the engine.
- **The two experimental skills agree on what an experiment heading is.**
  `experimental-deliberation` writes and validates an experiment as a heading
  carrying its `[exp:<id>]` declaration (cited as `[tests:<id>]` or `(Exp.
  <id>)`), while `experimental-implementation` located experiments only by a
  bare `## N` heading and counted only digit prose citations (`Exp. 3`). A
  document written the deliberation's way declared no experiment to the
  implementation skill, so every finding locus read as unknown and `compose`
  refused every replacement; documents had to carry both forms (`## N` wrapping a `###
  Experiment [exp:EN]` heading). The convention now lives in one file,
  `skills/_core/conventions/experiments.json` (identifier class, declaration
  and citation markers, prose form), read by both skills: the deliberation's
  `reference-experimental.ts`/`profile.ts` through `experiment-convention.ts`,
  and the implementation's `impl_profile.py`. The implementation skill now
  locates an experiment by a heading of any level carrying `[exp:<id>]`, its
  block running to the next heading of the same or a higher level, and counts
  `(Exp. <id>)` citations. `[claims:N]` crossings into the proposal are
  unchanged.
- **Each implementation skill binds its own document lineage.** On a target
  both `proposal-implementation` and `experimental-implementation` work on, the
  two read the same `src/<Package>/__init__.py`, and `__implementation__`'s
  `revision` held one name that each skill read as a revision of its own
  document. Bound to the proposal, the experimental skill's `verify` searched
  `experiments/` for a proposal family, discovered nothing and reported
  `fidelity: unknown` (and the reverse for the proposal skill); keeping one
  skill current meant re-binding away from the other. `revision` may now name
  one revision per document label, `{"proposal": "r03.md", "experiments":
  "experiments-<slug>-v02.md"}`; each skill reads only its own document 0's
  label. The scaffold template's comment named `proposals/` under both skills;
  it now names the loading skill's own document directory and label.

- **`init` and `upgrade` no longer copy unreleased framework code silently.**
  From an editable install the kit is the live checkout, and both commands
  copied it uncommitted edits included, with nothing recording which commit a
  workspace came from. Every `init` and every `upgrade` now writes
  `.papersmith/kit-source.json` (`version`, `commit`, `dirty`, `source`:
  `checkout`, `bundled` or `override`, `recordedAt`), and `papersmith status`
  reports it on a `Kit source:` line and under `framework.kit_source` in
  `--json`. A kit source tree with uncommitted or untracked changes under its
  shipped paths (`skills/`, `sections/`, `.claude/agents/`, the provisioning
  scripts, `requirements.txt`, `src/papersmith/`) refuses before anything is
  written, and so does one whose git state cannot be determined (unknown is
  treated as dirty). `--allow-dirty-kit` proceeds and records
  `allowedDirty: true`; the MCP `workspace_init` and `workspace_upgrade` tools
  forward it as `allow_dirty_kit`. `scripts/build-kit.py` now embeds the
  commit and dirty flag of the tree it copied into `kit-manifest.json`, so a
  wheel install records the commit it was built from; a bundled kit built
  dirty refuses too, and one built without provenance is admitted with the
  commit unknown. `upgrade --plan-migrations` writes nothing and does not
  refuse.

- **Scripts the CLI launches no longer write bytecode into the workspace.**
  `run_script` (every bridged skill script, from `audit` to `target check`)
  and `papersmith run`'s local job and Kaggle submission children inherited
  the parent environment unchanged, so a skill script importing a sibling
  module left `__pycache__/` inside the workspace's `skills/` kit copy. They
  now run with `PYTHONDONTWRITEBYTECODE=1` (one helper,
  `bridges.python.script_environment`; an explicit caller value still wins),
  the rule the MCP bridge and the dashboard child already followed.

- **One `upgrade` across a release now ends with `audit --check-drift`
  clean.** The routing docs (`CLAUDE.md`, `OPENCODE.md`,
  `.pi/APPEND_SYSTEM.md`, `.agents/AGENTS.md`) state the version the workspace
  records, and `upgrade` rendered them before it moved `.papersmith/version`.
  So every upgrade from an older release left them naming the old version,
  `audit --check-drift` reported them as generator drift, and only a second
  `upgrade` cleared it. They are now rendered again once the marker moves.
  Found by upgrading the populated 0.13.0 fixture below.

- **Deliberation engine state is ignored like the content it describes.**
  The workspace `.gitignore` keeps research content local (`proposals/*`,
  `experiments/*` and the rest), but `.proposal-deliberation/` and
  `.experimental-deliberation/`, where the two deliberation engines keep each
  revision's state, receipts and permanent locks, were neither tracked nor
  ignored. That state embeds and hashes the revisions the file already keeps
  local, so committing it published them, and it grows to megabytes. Both are
  now ignored, together with `backup/proposals/` and `backup/experiments/`,
  where the deliberation skills move revisions and their sidecars when
  reconciling a base. The set is checked against every `skills/*/profile.ts`
  the kit ships (its `artifact.sidecarRoot`, read through the engine) and by
  running the engine and asking git what it would track. The other skills'
  engine state already lives inside ignored folders (`paper/.paper-writing/`,
  `implementations/<target>/...`, `sota-pool/`).
- **`upgrade` no longer overwrites lines a workspace added to its
  `.gitignore`.** The file was re-rendered whole on every upgrade, so a user's
  own ignore lines were lost, and until then `status` and `audit
  --check-drift` reported the edit as drift. The framework's lines now sit in
  a delimited managed block: `upgrade` rewrites the block and keeps every line
  outside it, and drift is measured on the block alone. A file with no block
  yet (every workspace made before 0.14.0) is converted on its next upgrade:
  replaced whole when it is byte-identical to what the framework last wrote
  (the manifest's digest), and otherwise given the block with every line the
  block does not already carry kept below it, in order. Malformed markers
  are never guessed at: the file is left as it is, the run reports it as not
  written, and it stays drift until repaired.
- **The plausibility flow no longer starts a `paper/` tree.** `sota-scout`
  and `novelty-screener` confirm candidates through paper-writing's
  `resolve`, which cached every answer under `paper/.paper-writing/metadata/`
  by default, so exploring an idea wrote paper content before any paper
  existed. `resolve` gains `--cache-dir <dir>` (caches as
  `<dir>/<metadata_digest>.json`, refused outside the repository with
  `PAPER_OUTSIDE_REPOSITORY`, mutually exclusive with `--paper`), and both
  agents now pass `--cache-dir sota-pool/metadata`, keeping their caches in
  the pool. paper-writing's own calls pass nothing and keep caching under
  `paper/`, where `bib` and `full_text` read. The test reads the invocation out
  of each agent's definition and runs it against a workspace's shipped
  `paper_cli.py`.
- **`verify` reports per-section drift for the section labels revisions
  actually carry.** The implementation engine counted a heading as a section
  only when its first token was a bare number followed by a space
  (`## 3. Title`). Headings with an identifier label (`### O1. Objective`), a
  dotted label (`### 3.1`) or a label alone on the line (`## 3`, the legacy
  experiments form) produced no sections. `changedSections` stayed empty and
  `__provenance__["sections"]` was never compared with what moved, so only
  the file-level revision drift worked. The label grammar now lives once, in
  `skills/_core/conventions/sections.json`, and both implementation profiles
  pass it to the engine as `documents[0].section_heading`.
  `experimental-implementation` adds the experiment heading's `[exp:<id>]` as
  a marker, so its drift is reported per experiment id. A labelled heading
  nested under another is its own section and still part of its parent, and
  the parent covers the same lines it did before. `proposal-deliberation`
  documents the labels to use for sections that should be tracked.
- **`settle` places items in the order they were settled, never inside the
  position block, and `--reverse` opens its own heading.** The create path
  inserted each new item at the section's first checklist line, so a
  section read newest first. On the holder `position` creates, that first
  line is the position block's own item, so the documented
  `settle --under "## Ladder"` wrote into the block and `verify` then refused
  `POSITION_ITEM_MALFORMED`. A new item is now appended after the section's
  last checklist item, skipping the block's lines. If the section's only
  items are the block's, the new item goes right after `<!-- /position -->`.
  `settle --reverse` refused `SETTLE_HEADING_ABSENT` until someone added
  `## Reversed` by hand; now the first reversal adds that heading at the end
  of the file, in the same write as the deletion. A tick still cannot be
  undone. The correction path, now documented, is `settle --reverse` on the
  ticked line (the explanation and the ledger event stay) followed by a new
  `settle --under`.
- **`position.attainedLevel` no longer claims a rung nothing ran.** A
  sequence with no leveled (`:level`) witness reported the ladder's top
  rung, so an all-two-state position aimed at `pilot` read `attainedLevel:
  full` with no full-scale run behind it. With nothing leveled, attainment is
  now the rung the position aims at (`targetLevel`), and `null` when the aim
  is not on the ladder. Sequences with leveled witnesses read as before.
- **`verify`'s `prose` check no longer reports the engine's own writes.**
  After re-binding to a successor revision, `prose.staleRevisions` named the
  position block header in `<Name>/AGREED.md`, which records the revision it
  was derived from, and `prose.unresolvedSymbols` named the
  `` `test_<id>` `` witness token that `settle --attach` had written. In a
  checklist holder (this skill's declared filename or a sibling skill's), the
  check now skips the position block's opener and closer lines, the witness
  token at the end of an agreement line, and the append-only `## Reversed`
  section. The rest of the holder is still checked, including an
  agreement's own text, and the same lines in any other document are still
  reported.
- **An implementation skill no longer runs under the other skill's profile
  inherited from the environment.** Each launcher `setdefault`s its own
  `IMPLEMENTATION_DOMAIN_PROFILE`, so an explicit value wins. A shell, or an
  earlier process that ran the other skill, could leave the other skill's
  `impl_profile.py` exported, and this skill then read the other skill's
  documents and holder (for example `AGREED.md` from
  `experimental-implementation`) without saying so. Both launchers now refuse
  `IMPLEMENTATION_DOMAIN_PROFILE_SIBLING` (exit `2`, before the engine loads)
  when the inherited value resolves to another skill's own profile, naming
  both profiles. Any other explicit value, such as a test fixture profile,
  still wins. The test that leaked this skill's profile into later tests of
  the same process now restores the environment.
- **The engine's ambiguous-family mutation test no longer rewrites the
  shipped engine.** `tests/test_implementation_pair.py` wrote its mutation
  into `skills/_core/implementation/engine/implementation_engine.py` and
  restored it on cleanup, so a parallel worker could run the mutated engine
  and a crash could leave `MUTATED` in the tree. It now mutates a scratch
  copy of the engine tree and runs a copy of the launcher against it; the
  shipped file is asserted unchanged. Test-only: nothing a workspace runs
  changes.
- **Executing a kit-placed notebook is no longer structure drift.** Running
  `verification.ipynb` or `probe.ipynb` in place rewrites its outputs,
  execution counts and kernel metadata, and `verify` reported the notebook in
  `structure.scaffoldDrift`/`harnessDrift` until `materialize --authored`
  re-sealed it. A notebook destination's seal now also reads its source
  content (each cell's type and source, in order): the materialize stages,
  `--authored` and `--adopt` record it as `writtenSourceSha256`, and a match
  on either the full bytes or the source content is sealed. A changed cell
  source or cell type still drifts, and a notebook that is not readable JSON
  is compared on its full bytes only. Receipts written by 0.13.0 keep
  reading: an engine-written entry's source content is rebuilt from the kit
  and trusted only when it hashes to the entry's `writtenSha256`.
- **An unmeasured `@step` mark now says why, and what the step digest
  covers.** A step's verdict counts only while `suite_digest` (every `.py`
  under `src/` and `tests/`, plus the environment manifests) still matches,
  so a test-only edit turned every earlier step mark unmeasured with nothing
  saying so. The scope is kept: a step's callable may run the suite, read a
  file under `tests/` or spawn a subprocess, and the engine cannot see which,
  so a narrower digest could leave a mark satisfied over code the step runs.
  Each unmeasured `@step` item in a position state's `unmeasured` list now
  carries `reason` (no verdict yet, or the last run no longer counts, with
  the exact `step` command that clears it) and `digestScope`. Documented in
  `SKILL.md` and `references/usage.md`, with the advice to commit code and
  tests before the first pilot step.
- **A cost forecast says what parallelism its duration was taken at.**
  `probe`'s `search.costForecast` and the benchmark's `projectedCost` scale
  one recorded duration, and read it as if runs never competed: a pilot on
  eight workers took 2.42 times the projection, one arm about five times.
  Both now carry `parallelism`, `contention` and `basis`. A record whose
  `reduction` names `parallelism` (a positive integer) is projected from
  that run's own duration, `contention: "included"`, holding at that
  parallelism only. Otherwise the forecast is labelled single-process with
  `contention: "unmeasured"`, and no contention factor is supplied. A
  malformed `parallelism` is echoed as `parallelismMalformed` and never read.

- **A successor locus is matched by its heading's own words, and an outer
  section can be named.** `RESOLVE_TARGET` (and `CREATE_SUCCESSOR`'s
  `selectedEntryId`/`selectedEntryIds`, which share its resolver) tested each
  query word as a substring of the heading line, so `O1` also matched
  `O10` and blocked; two headings carrying the same words tied even when
  one of them was exactly the query; and nested matches collapsed to the
  innermost one, so once `### Synthetic data` existed `## Data` could not be
  targeted at all and a label line directly under it could not be edited.
  A query word now matches a whole heading token (a dotted identifier such
  as `3.1` stays one token; the parts of a hyphenated word still count); a
  heading whose words are exactly the query's, ignoring its section label
  (read from `_core/conventions/sections.json`) and stopwords, outranks one
  that merely contains them; and a query opening with level marks (`## Data`)
  considers only headings of that level. Nested matches are no longer
  collapsed: the gate decides on the scores. A blocked result lists every
  candidate with its level marks and its real heading path
  (`### Methods › Setup`), and `RESOLVE_TARGET` returns them as
  `candidates`.

- **A successor that inherits a link to the previous revision's companion
  artifacts says so.** Nothing in the engine writes the companion-picture
  line: the deliberation links `proposals/<revision>.graph.html` (rendered
  from `<revision>.sky.json`) from the revision's own text. A successor copies
  every byte outside its locus, so r02 kept pointing at r01's picture and
  nothing flagged it. `CREATE_SUCCESSOR` now reports every reference in the
  successor to a file named after another managed revision with a suffix
  other than `.md`, as `staleCompanionReferences` (`reference`, `revision`,
  `inherited`), on the preview, on the published result and in the receipt.
  The engine never rewrites the line or renders the picture; a replacement of
  the line inside the successor, deliberated and validated like any other
  edit, clears the flag.

- **A successor can delete the document's first section.** A managed
  revision opens with the artifact marker line and one newline, so removing
  the first section left the marker and the next heading one line break
  apart, and `derive_successor`'s removal-join check refused it as
  `successor-markdown-block-safety` (since A6 already at the preview, as
  `CANDIDATE_VALIDATION_FAILED`). The marker is an HTML comment line no block
  can fuse into, so a removal whose left side is exactly the marker is now a
  clean join; every other single-newline join is still refused.

- **`experimental-deliberation`'s usage guide names the heading v1 really
  writes.** It said source fragments are pasted under `## Paper Guide
  Reference`; the renderer writes this profile's `sourceReferenceHeading`,
  `## Reference Sources`, as `SKILL.md` already said. The usage-doc drift test
  now holds every heading the guide and `SKILL.md` say the engine writes
  ("under a `## X` heading", "the `## X` block") against the v1 the worked
  example actually renders and the profile's change header.

- **`verify` reports a notebook that is not a notebook instead of crashing.**
  A file under `<Name>/Notebooks/` whose bytes were not UTF-8, were not JSON,
  or were JSON whose top level is not an object made `verify` (and `probe`)
  exit with a traceback: the seal check and the prose check read it without
  the guard the execution check already had, and the execution check itself
  crashed on a JSON array or string. Every notebook reader now shares one
  read (`read_notebook_document`). The file is reported as `unreadable`,
  `sealed: false`, `sourcesMatch: null`, listed under `unsealed`, and the
  notebooks verdict reads `drift`, so it never passes for a sealed report.

- **`papersmith status` reads a proposal's stage from the engine's own
  state.** It probed only the legacy `proposals/deliberated/` and
  `proposals/accepted/` folders, which nothing writes any more, so every
  current proposal printed as `(draft)`. The latest managed revision's stage
  now comes from its publication receipt
  (`.proposal-deliberation/receipts/<file>.json`): `published` when the
  receipt is committed and its `documentShaAfter` is the document's current
  digest, `edited-after-publication` when the bytes changed since, `draft`
  when no committed receipt exists. The legacy folders are still read first,
  so an old workspace keeps its stage.

- **A fresh target walks `env` -> `plan` -> `apply` -> `materialize` without
  a hand commit in between.** `env` built `.venv/` before anything ignored
  it, so the `plan` that follows refused `DIRTY_WORKTREE` on a `git init`
  target, and the `pip install -e .` that `env` prints left an untracked
  `src/<dist>.egg-info/` that refused the next clean-requiring step again.
  `env` now appends `.venv/` and `*.egg-info/` to the clone's own
  `.git/info/exclude` before it builds anything (reported as `excluded`), so
  no tracked file changes and anything else untracked still refuses. The
  `.gitignore` block `apply` and `materialize --stage scaffold` author also
  carries `*.egg-info/` (not a scaffold gap on its own). The plan approved
  before `apply` stays `PLAN_STALE` for `materialize` (apply carried out its
  `createDirs`); the refusal now says so and the lifecycle (re-plan once
  `apply` has run) is documented in `proposal-implementation`'s usage guide.
  Shared by `experimental-implementation`.

- **The array backend is declared, not inferred from a helper's imports.**
  The kit's `tests/conftest.py` and `tests/sweep.py` imported numpy for a
  seeded generator, so a target whose modules compute in torch read as
  `mixed` and `probe` routed it to `convert` with no way out. Both kit files
  are now backend-neutral (`random.Random`, `SEED`, `configuration_seed`),
  the scaffold `pyproject.toml` (template and default) lists no array
  backend, and a target may state `__backend__ = "torch"` (or `"numpy"`,
  `"jax"`, `"tensorflow"`) in `src/<Package>/__init__.py`: `probe`'s
  `backend` then follows it (`declared-unmet` when no package file imports
  it; any other value is `unrecognized-backend`, never trainable). With
  nothing stated, import inference is unchanged. `env --torch cpu|gpu
  [--torch-version X]` adds the torch build to `nextCommand`: CPU uses the
  PyTorch CPU index and an exact `torch==X+cpu` pin (refusing
  `TORCH_VERSION_REQUIRED` without an exact release), GPU the default
  index's build. Shared by `experimental-implementation`.

- **The default `smoke_and_invariants` profile runs the target's own
  interpreter against the target.** It substituted the workspace folder name
  for `{paper_slug}` (`implementations/<workspace>/tests/...`, a directory
  no target is named after) and ran `pytest` from PATH. `papersmith run`
  now resolves two new placeholders, `{target}` (`implementations/<name>`,
  the only directory there or the one `--implementation <name>` picks) and
  `{target_python}` (that target's `.venv` interpreter), and the
  `papersmith init` template uses them (`{target_python} -m pytest
  {target}/tests/test_invariants.py`; the remote profiles name `{target}`).
  An unresolvable target (none, several without `--implementation`, an
  unknown name, or no `.venv` when `{target_python}` is named) refuses before
  anything is dispatched or recorded; `--dry-run` reports it under
  `target_resolution` instead. Profiles naming neither placeholder run as
  written.

- **A sibling's profile from another skills tree no longer passes the
  launcher.** The `IMPLEMENTATION_DOMAIN_PROFILE_SIBLING` guard compared
  skills roots only, so an inherited `impl_profile.py` of the other
  implementation skill from a second checkout or workspace was accepted and,
  for example, `experimental-implementation` read `AGREED.md`. Both
  launchers now read the skill a profile declares (the skill directory of
  its `PROFILE["cli"]["path"]`) and refuse any other skill's profile
  wherever it lives; this skill's own profile, and a fixture profile naming
  this launcher, still run. A sibling in the same tree is still refused by
  path even when it cannot be loaded.
- **A first revision's title and section heading no longer end in a full
  stop.** `CREATE_INITIAL_REVISION` takes the title from the idea's first
  sentence and the section heading from its second, and kept each sentence's
  terminal punctuation, so v1 opened with `# My idea.`. Both headings now drop
  their terminal `.`, `!` or `?` run (punctuation inside the sentence is kept);
  the slug is unchanged. Taking the heading from the second sentence and
  repeating the idea verbatim as the section body stay as they were and are now
  documented as intended: the headings are labels capped at 200 characters, the
  body is the only place the whole idea survives. Both deliberation skills'
  `SKILL.md` and `references/usage.md` state the derivation; the proposal
  usage example, a single sentence that `INITIAL_IDEA_SINGLE_SENTENCE` refused,
  now has two.
- **The 65,536-character instruction cap is enforced on the CLI, documented,
  and reported.** `proposal_deliberation_execute` declared `instruction` as
  `maxLength: 65536`, but the CLI host calls the tool directly and nothing on
  that path read the schema, so the cap a Pi session met did not exist for
  `cli.mjs` and no document stated it. One exported constant
  (`MAX_INSTRUCTION_CHARACTERS`) now feeds the schema and a check at the top of
  the tool's `execute`: a longer instruction is refused on every operation and
  host with `INSTRUCTION_TOO_LONG` (`nextAction: "shorten_instruction"`),
  nothing written. The `CREATE_SUCCESSOR` preview and the
  `CREATE_INITIAL_REVISION` result carry
  `instructionBudget: { limit, used, remaining }`. Both deliberation skills'
  `SKILL.md` and `references/usage.md` state the cap.
- **The first revision's source window is reported, warns when it cuts, and
  can be widened.** `CREATE_INITIAL_REVISION` reads at most 4000 bytes across
  every declared source, in declaration order (for the experiments domain the
  data paper first), and cut the crossing document mid-text and skipped every
  later one in silence: a data paper over 4000 bytes left the managed proposal
  out of v1 with nothing saying so. Every result that composed a document now
  carries `sourceWindow` (`limitBytes`, `loadedBytes`, one
  `{path, bytes, loadedBytes, status}` per document) and a
  `SOURCE_WINDOW_TRUNCATED` warning naming what was cut or left out;
  `sourceWindowBytes` (1 to 262144) widens the window for one creation
  (`SOURCE_WINDOW_INVALID` outside that range, `SOURCE_WINDOW_UNSUPPORTED` on
  another operation). The experimental `SKILL.md` no longer claims that only
  `<source>/<folder>/<folder>.md` is loaded and that `proposals/` contributes
  presence only (flat files have been read since the flat pass); both rules,
  the order and the window are documented in both skills.
- **An experiments plan can state its fixed settings in a table.**
  `report-table-fabricated-value` refused any digit in a body cell past column
  one of every table but a baselines table, so `| learning rate | 3e-4 |`
  blocked `CREATE_INITIAL_REVISION` and every successor as a "fabricated
  result". A table whose first header cell is, whole and case-insensitively,
  `Parameter`, `Parameters`, `Hyperparameter` or `Hyperparameters` is now a
  parameters table: a declaration of settings the plan fixes, exempt from the
  rule and from the baseline rules. Every other table keeps the rule, including
  one whose first header cell merely contains the word (`Parameter count`) or
  carries it in another column. Documented in `experimental-deliberation`'s
  `SKILL.md` and its usage example.
- **A remedy test's control is recognized however it calls the
  implementation.** `audit.remediesWithoutControl` accepted a
  `test_remedy_<id>` only when it called a name imported with `from <Package>
  import <name>` directly by that bare name, so `kernel.f(...)`,
  `import <Package>.kernel as k; k.f(...)`, `<Package>.kernel.f(...)` and a
  same-file helper doing any of those were reported as having no control,
  holding the audit at `incomplete`. The detection now follows attribute calls
  to the name they start from and same-file helpers to a fixed point. It still
  requires a call into the target's own package: importing without calling,
  passing a function along uncalled, and calling an unrelated import remain no
  control. Shared by `experimental-implementation`. Documented in
  `proposal-implementation`'s `references/usage.md`.
- **The objects stage follows the approved object map instead of a fixed
  file name.** `materialize --stage objects` always wrote
  `src/<Package>/module.py`, and `verify`'s `structure.objectGaps` reported it
  missing on any target without it, even one whose map had been written as
  modules of their own names, so the structure could not read `ok` without a
  file nobody asked for. `--module <name>` now names the module the stage
  writes (`src/<Package>/<name>.py`, from the same template, sealed and
  releasable with `--authored` like `module.py`), refusing
  `MODULE_NAME_INVALID` and `MODULE_STAGE_MISMATCH` for a name that cannot be
  a module file or a mode other than `--stage objects`. Without the flag the
  module destination is owed, and written, only while the package holds no
  module of its own. Targets that already carry `module.py` verify unchanged.
  Documented in `proposal-implementation`'s `SKILL.md` step 9 and
  `references/usage.md`.
- **Kit placeholders are filled when their value is known, and fail clearly
  when not.** `materialize` substituted only `{{PKG}}` and `{{SEED}}`, leaving
  values the engine already held to be filled by hand: the product name, the
  bound revision (`tests/test_smoke.py`, `tests/admissibility.py`, the
  verification notebook) and the module name. Unfilled, they failed as
  `'r01.md' != '{{REVISION}}'`, a remedy refused "against revision
  '{{REVISION}}'", or a collection `SyntaxError` for `def {{FUNCTION_NAME}}`.
  The scaffold stage now fills `{{NAME}}`, and `{{REVISION}}` when the target
  declares one or the approved plan was taken with `plan --revision`. The
  objects stage fills `{{REVISION}}`, `{{NAME}}` and `{{MODULE}}` in what it
  writes, and fills the same tokens into every scaffold file still
  byte-identical to its receipt, re-sealing each entry (listed under an
  additive `filled` key); a file somebody edited is never touched. Whatever is
  still unanswered fails naming the step that answers it: `admissibility.py`
  and `test_smoke.py` say the revision or the module is not known yet, and the
  kit's `conftest.py` collects a test file whose placeholders keep it from
  parsing as one failing item naming them. Receipts record each entry's
  substitutions. Documented in `proposal-implementation`'s `SKILL.md` steps 5
  and 9 and `references/usage.md`.

- **`status` and `audit --check-drift` no longer print projection warnings
  on every call.** Both re-render the runtime projections to compare them,
  and rendering the Pi agents emitted a multi-line `UserWarning` (`agent
  '<name>': tool 'WebSearch' has no Pi tool; not granted`) each time, so a
  healthy workspace read as faulty in a read-only command. The two commands
  now collect those notes: `status --json` carries them under
  `framework.generator_notes`, and `status --verbose` / `audit --check-drift
  --verbose` print them to stderr as `note: ...`. `init` and `upgrade`, which
  write the projections, still emit them as before. Documented in the
  manual's `status` and `audit` reference.

- **`proposal-implementation`'s docs name the checklist holder it declares.**
  `SKILL.md` (the checklist doctrine, the `agreements` status row and the
  `close` refusal row) and `references/usage.md` still called the holder
  `AGREEMENTS.md`, a name from one early commit; the profile declares
  `AGREED.md`, which is the file `settle` writes. A new drift test checks that
  every `*AGREE*.md` a skill's docs spell is a holder some implementation
  profile declares.

- **`materialize --authored`/`--adopt` say which paths they accept.** Naming
  any other path refused `NOT_A_KIT_DESTINATION` with "is not one of this
  stage's kit destinations" and nothing else, and no doc listed the set. The
  refusal detail now lists every accepted path (for `--authored`, including a
  file the objects stage recorded under a `--module` name), and
  `proposal-implementation`'s `references/usage.md` lists the set under "The
  sealed set", kept equal to the engine's `all_kit_destinations` by a test.

- **`papersmith implement` says what it bridges and what it does not.** The
  bridge runs nine of the engine's commands (`env`, `name`, `plan`, `apply`,
  `admit`, `handoff`, `compose`, `probe`, `verify`), and its `--action
  materialize` was an undocumented alias of `apply` — the layout migration —
  while the engine's own `materialize --stage/--authored/--adopt` was
  unreachable through it. The alias keeps working and now prints a note on
  stderr saying which command it runs and how to reach the engine's
  `materialize`; an unsupported action is refused naming the bridged commands
  and the direct `implementation_cli.py` route; `--action`'s help lists both.
  The manual's `papersmith implement` section lists the direct-only commands
  (a test keeps it equal to the engine's `COMMANDS` minus the bridge).
- **Direct engine use documents its two inputs.** `proposal-implementation`'s
  `SKILL.md` and `references/usage.md`, `experimental-implementation`'s
  `SKILL.md` and the manual now state that a hand-set
  `IMPLEMENTATION_DOMAIN_PROFILE` must be absolute
  (`IMPLEMENTATION_DOMAIN_PROFILE_NOT_ABSOLUTE`), and define the `--session`
  id the ledger-writing commands require: chosen by the caller, one per
  working session, one shell-safe token, stamped verbatim as attribution and
  never validated.

- **The `sota-grapher` agent runs the atlas checker with the pool.** Its
  repair loop ran `check_atlas.py sota-pool/atlas.json` without `--pool`, so
  the quote-fidelity guard added to the checker never ran inside the stretch
  that draws the quotes. The agent now runs
  `check_atlas.py sota-pool/atlas.json --pool sota-pool/candidates.json`; the
  OpenCode, Pi and `.agents` projections are regenerated from it, and a test
  reads every agent definition that runs the checker on the atlas.

- **`resolve` reads the year arXiv and Crossref send.** `paper_resolve.py`
  hard-coded `year: None` for both, although an arXiv entry carries
  `<published>` and a Crossref record carries `issued`/`published`
  date-parts, so every `refs.bib` entry resolved through them lacked a year
  and the plausibility pool had to derive one by hand. arXiv now reports the
  year of `<published>`; Crossref reports `issued`'s year, else
  `published`'s. A missing, `null` or non-integer date still reports `null`.
  Documented in `plausibility`'s `SKILL.md`.

- **Every skill that delegates to a generated agent says what to do when the
  agent cannot be spawned.** Only `proposal-implementation` and
  `paper-writing` covered a harness without sub-agents, and none said to
  follow the agent's own definition. Each of the eight skills an agent binds
  to now carries "When a delegated agent cannot be spawned": perform the
  stretch inline by following `.claude/agents/<name>.md` as written, within
  its `tools:` line, and say so in the reply (`paper-writing` adds that an
  inline audit is not independent of the draft). A test derives the
  agent-to-skill binding from each agent's `Skill:` line.

- **`papersmith ingest` says it takes PDFs only, and where other material
  goes.** A non-PDF path or URL was refused with "must be a PDF path" and no
  way forward. Both refusals now name the two `proposal-deliberation` routes
  for material that is already text: `guidance/paper-guide/` to seed a new
  proposal (`CREATE_INITIAL_REVISION`), and `proposals/` +
  `ADOPT_INITIAL_REVISION` for a draft that should become v1 as written.
  Documented in `paper-ingestion`'s `SKILL.md` and the manual's `ingest`
  reference.

- **The manual no longer gives line counts for the implementation launcher.**
  The `experimental-implementation` section said the launcher was 24 lines
  and the profile 278; they are 65 and 352. The counts are dropped rather
  than updated, so they cannot go stale again, and the launcher's row now
  says it also refuses a sibling skill's profile
  (`IMPLEMENTATION_DOMAIN_PROFILE_SIBLING`, exit 2).

- **`upgrade-project` describes the `.gitignore` managed block.** Its
  `SKILL.md` said only that hand-edited files outside the protected patterns
  are replaced, which since the managed block was added is no longer true of
  `.gitignore`. It now says that `upgrade` re-renders only the block between
  the two marker lines and keeps every line outside it, how a pre-0.14.0 file
  is converted, and that malformed markers leave the file untouched and
  reported as unsynchronized.

- **`INITIAL_IDEA_SINGLE_SENTENCE` says what is missing.** The refusal of a
  one-sentence idea came with the message for an empty one ("Provide a
  non-empty idea in instruction."). It now says the idea needs at least two
  sentences (title and section heading), what ends a sentence, and that
  nothing was written. Both deliberation skills share it.

- **`papersmith deliberate --action adopt` runs `ADOPT_INITIAL_REVISION`.**
  The bridge listed every engine operation except adoption, so `--action
  adopt` and `--action ADOPT_INITIAL_REVISION` were refused as unsupported and
  the operation was reachable only through a raw `--request`. The alias passes
  `--revision` as `sourceFilename` and, like every operation but `status` and
  `resolve`, needs `--instruction`; a missing `--revision` is refused before
  the engine starts. The bridge still has no `--dry-run` flag; the preview is
  a raw `--request` carrying `"dryRun": true`, which the bridge passes through
  unchanged (README). A test now reads the engine's operation list and fails
  if any operation has no bridge route.

- **An experiments v1 no longer pastes the proposal's reserved marker.**
  Every published proposal revision opens with the engine's reserved artifact
  marker line, and the experiments domain reads `proposals/` as a source. v1
  pasted that line verbatim. Since v1 runs the successor's pre-publish
  validation, `CREATE_INITIAL_REVISION` was refused
  (`INITIAL_REVISION_CANDIDATE_VALIDATION_FAILED`, `initial-candidate-limit`)
  whenever a proposal fitted in the source window, which is the normal flow,
  and the message asked for a repair of a source that cannot be repaired. In
  0.13.0 the v1 was written, and no successor could ever be accepted from it.
  The source window now neutralises every reserved marker it loads, in both
  deliberation skills and in a chat's first turn: a marker comment line is
  removed, any other occurrence of a reserved marker name becomes plain text,
  and NUL bytes are dropped. The `sourceWindow` entry for that document
  reports `reservedMarkersRemoved`. The validation itself is unchanged and
  still refuses a v1 or successor carrying a reserved marker.
  A v1 written by 0.13.0 keeps its bytes. A successor that keeps its copied
  markers is refused at preview with `successor-copied-artifact-marker`, which
  names the sections that hold them and the repair. A successor that replaces
  those sections without the marker lines is accepted: a field that only reads
  the source (`oldText`, `anchor`) may span a copied marker line, and the
  accept turn's source read accepts exact copied marker lines, never any other
  reserved byte. Every preview refused by that pre-publish validation now
  carries `nextAction: "repair_candidate"` and one blocker with the rule's
  code, message and repair step, where it used to answer only
  `CANDIDATE_VALIDATION_FAILED` with `nextAction: "inspect_error"`.

- **A shared target's headline fidelity judges only its own lineage.** On a
  target both implementation skills share, `__implementation__.revision` maps
  one revision per document label, and each skill's modules carry their own
  lineage's revision. The whole-tree `fidelity.staleModules` compared every
  module against this skill's revision, so the other skill's module read
  "bound to an older revision, but none of its sections moved" and
  `fidelity.status` was `drift` for both skills, while `fidelityByDocument`
  read `ok` for both documents. main's engine shows the same with a
  single-string binding (the only form it reads; it crashes on the mapping).
  A module whose revision is in another label's filename family is now
  listed in `fidelity.otherLineageModules` (`module`, `label`, `revision`)
  and kept out of `staleModules`, `drift` and the headline. A module of the
  skill's own lineage goes stale as before, and a bare-string binding is
  unchanged.

- **A refused `position` or `settle` writes no holder.** On a product folder
  with no declared holder yet, both commands wrote the holder's scaffold
  (`# Agreed` / `## Ladder`) first and checked their arguments after, so a
  call refused `POSITION_TARGET_LEVEL_REQUIRED` (exit 2) left an empty holder
  behind, and so did `POSITION_TARGET_LEVEL_UNKNOWN`,
  `POSITION_LEVELS_UNDECLARED`, the record checks, and every `settle` refusal
  past holder resolution (`SETTLE_HEADING_ABSENT`, `SETTLE_TEXT_ABSENT`, ...).
  Pre-existing on 0.13.0. The scaffold is now the base the write is spliced
  into and reaches the disk with it, under the same compare-and-swap; a
  refused call leaves the tree byte-identical.

- **A witness-less agreement can be placed by `settle`.** Placing a line
  needed `--about` and an answered discussion, and `settle --done
  --unwitnessed` closes only a line that exists, so a scoping decision with
  no position sequence had to be written into the holder by hand.
  `settle --under <heading> --unwitnessed --reason <why> --text <line>` now
  places it, unticked and bound to no discussion, and logs the reason
  (`about: null`, `unwitnessed: true`, `done: false`). `--about`, `--witness`
  and `--supersedes` are refused with it (`SETTLE_UNWITNESSED_CONFLICT`),
  `--reason` stays required, and closing the line is still the separate
  `--done --unwitnessed` act. Only that closing act is named under
  `agreements.witness.decided`.

- **The board now lists the agents that work in each tramo, and it was missing
  three.** `AGENT_STAGES` carried 16 of the 19 shipped agent definitions, and the
  ones it lacked were exactly the plausibility ones — `sota-scout`,
  `sota-grapher` and `novelty-screener` — so the board's Plausibility tramo
  showed no agents while the flow drawing beside it showed three. Nothing failed,
  because an unmapped agent is dropped in silence. A test now holds the mapped
  set equal to the shipped set, so the next agent that nobody maps fails the
  build instead of disappearing from the board.

### Added

- **Antigravity CLI (`agy`) harness portability and tooling alias.** `papersmith init`
  and `papersmith upgrade` now accept `--tools agy` as an alias for `antigravity`,
  enabling direct projection of Google Antigravity configuration files (`.agents/AGENTS.md`
  and `.agents/skills/`) without duplicate tool registration errors when combining flags.
  Added `scripts/gen-agy.py` as an alias entrypoint for `scripts/gen-antigravity.py`.
  Remote execution guard hooks (`refuse_offpath_push.py`) support Antigravity's `PreToolUse`
  event payload and JSON allow/deny output format, and Antigravity setup instructions
  are documented in `docs/guard-hooks.md` and `docs/mcp.md`.
- **A populated 0.13.0 workspace fixture, and a test that upgrades it.**
  `tests/fixtures/workspace_v0_13_0/` holds a workspace produced by the
  0.13.0 release itself (`scripts/build-v0_13_0-fixture.py` drives that
  tree's own CLI and engines): two managed proposal revisions and one
  experiments revision with their receipts, state and locks, and an
  implementation target with its scaffold receipt and seal file, both
  implementation skills' holders with settled items, and their position
  ledger. `tests/test_upgrade_v0_13_0_workspace.py` upgrades it with the
  current CLI and asserts that nothing it holds changes except the listed
  `.papersmith/` records, that every registered migration applies or is
  already satisfied, that `audit --check-drift` is clean, and that the
  deliberation consistency audit and both implementation `verify` runs still
  read what 0.13.0 wrote. `tests/fixtures/README.md` documents how it is built
  and stored.
- **`CREATE_INITIAL_REVISION --dry-run`: see the first revision before it
  exists.** A successful creation leaves
  `<sidecarRoot>/locks/initial-revision.lock` in place for good (the
  slug-independent single-winner guard), so the only way to see v1's filename,
  derived headings and canonical-form verdict was to create it, after which
  every further attempt is refused. `cli.mjs --dry-run` (or `"dryRun": true`
  in the request) runs every check and the composition and returns
  `status: "preview"` with the would-be `targetFilename`, `canonicalMetadata`
  and composed `markdown`, without taking the lock or writing anything. A
  present lock is reported as the `MANAGED_PROPOSAL_ALREADY_EXISTS` the real
  call would meet and is never touched. `dryRun` on any other operation is
  refused `DRY_RUN_UNSUPPORTED` rather than ignored. Existing locks are neither
  removed nor reinterpreted. Documented in both deliberation skills' `SKILL.md`
  and `references/usage.md`.
- **A successor receipt can record why the change was made and who decided
  it.** Receipts kept only an `instructionHash`, so a published revision could
  not say why it existed or whether a person or an agent took the call.
  `CREATE_SUCCESSOR` accepts two optional fields, `rationale` (at most 2000
  characters) and `decider` (`agent` or `human`), and the successor's receipt
  records them verbatim beside the hash. Malformed values are refused
  `DECISION_RECORD_INVALID` at the preview, and either field on another
  operation `DECISION_RECORD_UNSUPPORTED`. Documented in both deliberation
  skills' `SKILL.md` and `references/usage.md`.
- **`ADOPT_INITIAL_REVISION`: adopting an existing document as v1 gets the
  same state, receipt and validation as creating one.** Both deliberation
  skills offered "adopt it as v1" and the only way was by hand (prepend the
  marker, rename the file), which left no committed state and no receipt
  (`runConsistencyAudit` reported `MISSING_MANIFEST`) and skipped the
  canonical-form gate and pre-publish validation, so a document breaking the
  domain's rules entered the lineage unexamined. The new operation, with
  `sourceFilename` naming an unmanaged `.md` in the managed directory, runs
  that gate and publishes the file's bytes through the creation path itself
  (lock, exclusive write, state, receipt with `operation:
  "CREATE_INITIAL_REVISION"` and an additive `adoptedFrom`), named after its
  first `# ` title; the source is left in place for the agent to back up. With
  `sourceFilename` naming an old hand-adopted v1 it is the explicit repair
  path: after the same gate it writes that revision's state and receipt,
  bytes untouched, and refuses one that already has a receipt
  (`ADOPTION_ALREADY_RECORDED`). Accepts `--dry-run`. Documented in both
  deliberation skills' decision trees, operation tables and usage.
- **An audit that found nothing can be ruled on.** `admit` refused
  `NO_FINDINGS` whenever `tests/findings.py` declared an empty list, so a
  target whose audit found no defect could never record it and `verify` stayed
  at `audit: none`, the answer a never-audited target gets. `admit
  --no-findings` now records an empty ruling (`"findings": {}`,
  `"noFindings": true`) bound to the revision's bytes; `verify` reads it as
  `audit: ok` with an additive `noFindings` key, and as `incomplete` once the
  revision moves. Plain `admit` on an empty list still refuses `NO_FINDINGS`
  (its detail now names the flag), and the flag with findings declared refuses
  `FINDINGS_DECLARED`. Shared by `experimental-implementation`, which runs the
  same engine. Documented in `proposal-implementation`'s `SKILL.md` step 11
  and `references/usage.md`.
- **A defect that lives in the prose can be declared as a finding.** A
  finding's correction was only expressible as one numbered equation rewritten
  in place: the kit's `test_audit.py` required a non-empty `remedy_equations`,
  `compose` substitutes at the equation's own `\tag{n}`, and `verify` kept
  asking for a `remedy_block` that nobody can write for a sentence with no tag.
  A finding may now declare `"remedy_in_prose": True` with its remedy locus
  list empty and no `remedy_block`: it is admitted on the same notation and
  adoption checks, never listed under `localRemediesNotWritten` (so no
  `toDiscuss` entry), and `handoff` defers it as `prose-remedy` to a
  deliberation session of its own. Declaring it beside remedy loci, or with a
  value other than `True`, is ruled inadmissible; without the flag an empty
  locus list reads exactly as before. The kit's `findings.py` documents the
  field and `test_audit.py` accepts it. Shared by `experimental-implementation`.
  Documented in both implementation skills' `SKILL.md` and
  `proposal-implementation`'s `references/usage.md`.
- **An experiments document can declare a proposal claim out of scope.**
  `agree` reported every declared claim no experiment cites as
  `untested:<id>`, and the only way past one was `--acknowledge
  untested:<id>`, request-scoped by design and so retyped on every call, with
  nothing in either document recording the decision. The shared experiment
  convention (`skills/_core/conventions/experiments.json`) now registers an
  `outOfScope` marker, `[out-of-scope:<id>]`; the experimental profile's
  crossing reads it (an optional `cross_citation.out_of_scope` pattern, held to
  the one-group rule), and `agree` subtracts a declared, uncited claim marked
  that way from `untested` and echoes it under `outOfScope`. The marker clears
  nothing else: a citation to an undeclared claim stays `absent`, a marker
  naming an undeclared claim subtracts nothing, and a document without one
  reads exactly as before. Documented in `experimental-deliberation`'s
  `SKILL.md` (where the document is written) and `experimental-implementation`'s
  `SKILL.md` and `references/usage.md`.

- **`paper-ingestion` can OCR every page instead of trusting a poor text
  layer.** Marker rebuilds digital tables from the PDF's own text layer
  (`tables_pdftext`) in both `fast` and `balanced` mode, so a text layer that
  is present but poor produced confidently garbled tables and switching
  `--mode` could not avoid it. `extract_pdf.py --force-ocr` (or
  `force_ocr: true` under `paper_ingestion:` in `papersmith.yaml`) hands
  Marker its `force_ocr` option: no text layer is extracted and every page,
  tables included, is rebuilt by OCR. Off by default; a non-boolean
  `force_ocr` is a configuration error reported before any model loads.
  Documented in the skill's `SKILL.md` ("Tables from a poor text layer") and
  the manual.

- **`walk` commits under a subject the target's convention accepts.** The
  walker commits what each step produced (`step` refuses on a dirty tree), and
  the subject was fixed at `walk: <step>`, so a target enforcing Conventional
  Commits through a hook or a lint refused the walk's commits or carried
  history its own policy rejects. `walk --commit-template '<subject>'` now
  shapes it, with `{step}` as the one placeholder (`chore(walk): {step}`).
  The default stays `walk: {step}`. A template with no `{step}`, any other
  brace, or more than one line is refused `WALK_COMMIT_TEMPLATE_MALFORMED`
  before anything runs. Shared by both implementation skills; documented in
  `proposal-implementation`'s `SKILL.md` and `references/usage.md`, and in
  `experimental-implementation`'s `SKILL.md`.

- **The plausibility checker can hold every quote to its abstract.**
  `check_atlas.py` certified shape only, so a paraphrase or an invented
  sentence dressed as a quote ran green. `check_atlas.py <atlas> --pool
  sota-pool/candidates.json` now requires each planet's `evidence.origin` to
  name a pool candidate (`identifier`, `source_url` or `url`;
  `EVIDENCE_ORIGIN_NOT_IN_POOL`), that candidate to hold an abstract
  (`EVIDENCE_ABSTRACT_MISSING`), and the quote to be a verbatim substring of
  it (`EVIDENCE_QUOTE_NOT_IN_ABSTRACT`); whitespace runs compare collapsed,
  nothing else is normalized. An unreadable or malformed pool exits 2. The
  plausibility `SKILL.md` documents the invocation and, measured from
  `paper_resolve.py`, what each resolver cannot give the pool: Crossref never
  returns an abstract (and reports no year), arXiv reports `year: null` and
  `venue: "arXiv"`.
- **`paper-writing` says which language its blocks are written in, and it is
  English.** Nothing in that skill stated it, so the answer was whatever language
  the session happened to be speaking. `proposal-implementation` has declared the
  split for its own artifacts for releases — *"Every artifact stays English ...
  The conversation does not."* — and the skill that writes the manuscript was the
  exception. A manuscript written in a language nobody chose is a defect that
  stays invisible until someone who was not part of the conversation reads it.
- **A prose pass, with a list it may not touch.** A written block can be edited
  for prose --- vocabulary, phrasing, sentence rhythm, the connective between two
  sentences. It may not change a citation or its identifier, a number or
  statistic, the methodology as stated, or the technical terms that block's
  contract names; changing one of those is a **failure rather than a warning**,
  the same class `UNBOUND_SENTENCE` and `SPAN_NOT_IN_SOURCE` already catch.
  It is opt-in, it never writes to `main.tex` itself --- its output goes through
  `open` and `substitute`, so the engine's proof that not one byte outside the
  target block moved still holds for it --- and it runs as a checklist with
  nothing installed, so an operator-wired humanizer is an accelerator inside the
  contract rather than a prerequisite for it.
  **What it is not:** a way to lower an AI-detection score. It adds no digressions
  to read as humanly edited and changes no claim. A rewrite shaped so that a
  classifier reads the text differently is shaped by something other than the
  evidence, and this forge's invariant is that every claim is tied to its own.
- **`plausibility` gains its acceptance gate.** The third stretch ends at the
  plausibility report, and the ranked top 5 it hands to the ingestion stage is a
  list of PDFs somebody is about to be sent looking for. Nothing approved that
  list before the next stage acted on it. The gate is deliberately narrow: it
  approves the reading and not the idea, and this skill publishes and files
  nothing by design. Every re-screen is a new reading and carries its own gate,
  because an earlier acceptance of an earlier report is not an acceptance of this
  one — and presenting the report while proceeding anyway is the failure the
  section exists to prevent.

### Changed

- **Workspace support policy: a live workspace is upgraded, never
  re-initialized.** This supersedes the 0.8.0 note "existing workspaces are
  not migrated; re-run `papersmith init` in a fresh workspace", which would
  discard a paper's ledgers, receipts, seals and managed revisions. From
  0.14.0 on, every release that changes the shape of something a workspace
  already holds ships, in the same release, a migration in `upgrade`'s
  registry or a compatibility read that keeps the old shape reading, and says
  which under Behaviour changes. Workspaces recorded at 0.12.0 or later (the
  first release with artifact migrations) are supported; older ones still
  upgrade, but pre-0.12.0 shape changes have no migration (0.8.0's
  `.antigravity/` files are not removed). Documented in `docs/releasing.md`
  ("Workspace support policy"), the `upgrade-project` skill and the manual.

### Behaviour changes

- `admit` returns a new `adopted` map (present only when some finding is
  adopted), and `tests/admissibility.json` carries
  an optional `adopted` key on each adopted finding's verdict. Both are
  additive: rulings written by 0.13.0 carry no such key and keep reading
  unchanged, so no migration is needed.
- `verify`'s `audit` gains an `adopted` map, present only when some finding is
  adopted. A target whose only blocker was
  an adopted finding now reads `audit: ok` instead of `incomplete` or
  `needs-deliberation`.
- Under a profile declaring more than one document, adoption is read from the
  document(s) a finding names, the same text `admit` already checked the
  marker against, instead of always from document 0.
- A target holding the other implementation skill's declared holder (and no
  holder of this skill's own) no longer refuses `HOLDER_UNDECLARED` on
  `position --sequence`, `position --reconcile` or `settle`: the write creates
  this skill's declared holder with its scaffold and leaves the sibling's file
  byte-identical. Workspaces that already created their own holder by hand
  keep resolving it as declared; no migration is needed.
- `verify`'s `agreements` (and the same reader in `close`) no
  longer counts the other implementation skill's declared holder: a target
  whose only checklist is the sibling's now reads `agreements: absent` instead
  of the sibling's items, and a new `siblingHolders` list names the skipped
  file. The key is present only when such a file exists, so other targets read
  byte-identically. The position section likewise reads `absent` until this
  skill installs its own block, instead of the sibling's.
- `probe` on a target with no prior-work package under `src/` and a declared
  `__steps__` flow now answers `pilot-first` or `pilot-decisions` where it
  used to answer `nothing-to-compare`, and publishes those rungs' questions
  in `resolve` and `toDiscuss`. Targets that declare no flow, or whose pilot
  is complete and every step decided, still read `nothing-to-compare`. No
  stored artefact changes shape; no migration is needed.
- `verify`'s `fidelity.missingProvenance` no longer names
  `src/<Package>/report_digest.py` while it is unmodified, so a target whose
  only provenance gap was the seal now reads a non-`drift` fidelity status.
  Existing 0.13.0 targets benefit without any action: the exemption also
  accepts the bytes their own scaffold receipt recorded. The receipt shape is
  unchanged; no migration is needed.
- `close` on a target declaring no flow now records the close (status
  `closed`, `positionOwed: false`) where it used to refuse `POSITION_ABSENT`.
  A target declaring any part of a flow still refuses, and the detail now
  names what it declares. `positionOwed` is absent whenever a position was
  owed.
- `verify`'s `agreements.witness` gains `decided` (lines closed by `settle
  --done --unwitnessed`, with reason, session and time) and `handTicked`
  (ticked witness-less lines with no such record), each present only when
  non-empty. Lines ticked by hand in a 0.13.0 holder keep counting as
  settled and stay under `unwitnessed`; they are now also named under
  `handTicked`. The `settle` ledger event and response carry `unwitnessed`
  and `reason` only on the new act. Additive; no migration is needed.
- `SETTLE_NOT_WITNESSED`'s detail and question now name `--unwitnessed` for a
  line no test could witness. Three new refusals: `SETTLE_UNWITNESSED_CONFLICT`,
  `SETTLE_REASON_REQUIRED` (a work state whose question asks the operator
  why) and `SETTLE_WITNESS_PRESENT`.
- `proposal-deliberation` and `experimental-deliberation`: a successor
  preview whose candidate the accept turn would refuse now answers `blocked`
  / `CANDIDATE_VALIDATION_FAILED` instead of `awaiting_acceptance`; the
  validation carries the accept turn's refusal under `candidateValidation`,
  `results.prePublish` and `prePublishApplicable`. Such a token could never
  be spent, so no publishable flow changes.
- `CREATE_INITIAL_REVISION` refuses a composed v1 that fails the structural
  pre-publish validation (oversized or reserved bytes, malformed display
  blocks, a heading fused into prose outside code) with
  `INITIAL_REVISION_CANDIDATE_VALIDATION_FAILED` and `nextAction:
  repair_candidate_markdown`, where it used to publish a v1 that blocked
  every successor. A heading marker inside a code span now passes at all
  three points. Existing managed revisions, receipts and ledgers are not
  re-validated and keep reading; a 0.13.0 v1 that carries an inline-code
  `## ` becomes able to publish successors. No migration is needed.
- `experimental-implementation` reads experiments documents in three forms:
  the canonical heading carrying `[exp:<id>]`, and both legacy forms (a bare
  `## N`, and `## N` wrapping an `[exp:<id>]` heading). Managed revisions are
  never rewritten: a 0.13.0 experiments document keeps every id it declared
  (`N`), and a legacy dual block also declares its nested `<id>`, so findings,
  `__provenance__` claims and `admissibility.json` rulings that cite `N` keep
  reading, and new ones may cite `<id>`. Inside one legacy block both ids name
  the same experiment: `compose` accepts a replacement carrying both (a new,
  optional `block_locator.block_aliases` profile leaf, off unless declared;
  `proposal-implementation` does not declare it and is unchanged). The
  migration is a compatibility read; no workspace artefact changes shape and
  no `upgrade` migration is needed.
- `__implementation__["revision"]` accepts a mapping keyed by document label.
  A bare string keeps its meaning (the reading skill's own document) and reads
  exactly as before under both skills; nothing rewrites existing declarations,
  and the engine still writes `"revision": ""` into new scaffolds (only the
  comment above it changed). A mapping without the reading skill's label
  leaves that skill's revision unanswered (never another lineage's name): with
  empty `premises` the declaration reads `undeclared` with a detail naming the
  label, otherwise `materialize --stage objects` refuses
  `OBJECT_MAP_NOT_APPROVED` naming `revision`. A non-string value under the
  label reads `undeclared`. The reader's contract carries the full mapping as
  `revisionByDocument`. Declarations live in target repositories under
  `implementations/`, not in the workspace kit, so no `upgrade` migration
  applies.
- `papersmith init` and `papersmith upgrade` refuse (exit 1) when the kit
  they resolve is a checkout or `PAPERSMITH_KIT_ROOT` tree with uncommitted
  changes under its shipped paths, or whose git state cannot be read. Users of
  an editable install with local edits will meet this; commit the edits, or
  pass `--allow-dirty-kit` (`PAPERSMITH_ALLOW_DIRTY_KIT=1` is the same
  override, used by the test suite). Wheel installs are unaffected unless the
  wheel was built from a dirty tree.
- A workspace created by 0.13.0 or earlier has no kit-source record:
  `status` reports `Kit source: unknown (recorded before 0.14.0)` until the
  next `upgrade`, which writes it. Nothing else changes shape and no migration
  is needed; the record is not a framework-managed file, so `audit
  --check-drift` and `status`'s drift list do not report it.
- `papersmith run` on a `local` target now runs the profile's command with
  `PYTHONDONTWRITEBYTECODE=1`, so the job writes no `.pyc` files (into the
  workspace or the target it imports); imports are recompiled on each run.
  No stored artefact changes; no migration is needed.
- After an `upgrade` that moves the version marker, the routing docs name the
  new version in the same run. No stored artefact changes; no migration is
  needed.
- The workspace `.gitignore` changes shape on the next `upgrade`: the
  framework's lines move into a block between two marker lines, and lines the
  workspace added stay below it. It now ignores `.proposal-deliberation/`,
  `.experimental-deliberation/`, `backup/proposals/` and
  `backup/experiments/`. No registry migration is needed: `upgrade` re-renders
  `.gitignore` on every run, and that render now merges into the existing file
  (converting a 0.13.0 file as described under Fixed) instead of replacing it,
  which `tests/test_workspace_gitignore.py` checks against the 0.13.0
  fixture. Ignoring a path does not untrack it: a workspace that already
  committed engine state keeps it in git until `git rm -r --cached
  .proposal-deliberation .experimental-deliberation` is run, which is the
  user's call.
- The plausibility agents' `resolve` calls cache under `sota-pool/metadata/`
  instead of `paper/.paper-writing/metadata/`. Caches an earlier run already
  left under `paper/` are valid paper-writing caches (same record, same key)
  and keep reading; nothing moves them and no migration is needed. A
  workspace that wants them gone can delete
  `paper/.paper-writing/metadata/` while no paper has been started.
- `verify`'s `fidelity.drift[].changedSections`/`touchedSections` and
  `fidelity.benchmark.changedSections`/`armsReached` now list identifier,
  dotted and label-only sections. A change inside `3.1` reports both `3` and
  `3.1`. A drift entry whose sections now resolve reads
  `sections it declares have changed` where it used to read `bound to an older
  revision, but none of its sections moved`. A numbered parent's digest covers
  the same lines as before, so existing numbered `__provenance__` references
  keep matching what they matched. Under `experimental-implementation`,
  sections are experiment ids (`E1`) and legacy `## N` numbers. The
  implementation profile gains an optional `documents[N].section_heading`
  leaf (refused as `IMPLEMENTATION_DOMAIN_PROFILE_INVALID_SECTION_HEADING`
  when malformed; a profile that does not declare it reads no sections). This
  is reader-side only: no stored artefact changes and no migration is needed.
- `settle --under` appends after the section's last item instead of placing
  the item first. In a holder that 0.13.0 wrote newest first, the existing
  lines stay where they are and new items follow them, so the section reads
  as the old newest-first run followed by an oldest-first run. Nothing is
  reordered or rewritten. A section whose only items are the position
  block's receives the item right after the block. `settle --reverse` with no
  `## Reversed` heading now adds one at the end of the file instead of
  refusing `SETTLE_HEADING_ABSENT`, a code that path no longer raises. More
  than one heading still refuses `SETTLE_HEADING_AMBIGUOUS`. Holders and
  ledgers keep their shape, so no migration is needed.
- `verify`'s `position.attainedLevel` for a sequence with no leveled witness
  is the header's `targetLevel` instead of the ladder's top rung. `gate` and
  the launch menu read the same value. On a ladder of three or more rungs, a
  launch from such a position now needs the position to aim at the launch
  rung (`levels[-2]` or above). One aimed at a lower rung refuses
  `RUNG_NOT_ATTAINED` where it used to pass, and re-sealing with
  `position --target-level <rung>` is the exit, which the rung-skip rule
  allows for such a sequence. Sealing is otherwise unchanged. Nothing stored
  changes shape and no migration is needed.
- `verify`'s `prose.staleRevisions` and `prose.unresolvedSymbols` list fewer
  entries for targets whose holders carry a position block, witness tokens or
  a `## Reversed` section. Both keys were report-only and never moved a
  status. This changes the reading only: no migration is needed.
- Running either implementation launcher with `IMPLEMENTATION_DOMAIN_PROFILE`
  set to the other implementation skill's `impl_profile.py` now refuses
  `IMPLEMENTATION_DOMAIN_PROFILE_SIBLING` instead of running under that
  profile. Unset the variable. Nothing stored changes and no migration is
  needed.
- `verify` no longer lists an executed kit notebook under
  `structure.scaffoldDrift` or `structure.harnessDrift`, and new receipt
  entries for notebook destinations carry an extra `writtenSourceSha256` key.
  The key is additive: receipts without it keep reading (full bytes, or the
  source content rebuilt from the kit for an engine-written entry), so no
  migration is needed. A legacy `authored` or `adopted` notebook entry still
  drifts on execution until its next `materialize --authored`.
- Unmeasured `@step` entries in a position state's `unmeasured` list carry
  two new keys, `reason` and `digestScope`; the `sequence` entries and every
  verdict are unchanged. Step events keep their digest, so marks recorded by
  0.13.0 read exactly as before. No migration is needed.
- `search.costForecast` and `projectedCost` gain `parallelism`,
  `contention` and `basis` (and `parallelismMalformed` when that key is
  unreadable) wherever they carry a projection; `projectedSeconds` is
  unchanged. Search records are read, never rewritten, so no migration is
  needed.

- Locus queries resolve differently only where they were wrong: a word that
  matched part of a heading word no longer matches (`O1` vs `O10`); a query
  naming an outer heading exactly (`Data`) now resolves to it instead of a
  nested heading sharing the word; a query whose candidates nest within the
  gate's margin blocks and lists both instead of silently picking the
  innermost; and a query opening with `#` level marks only considers headings
  of that level. Entry ids, labels and tags (the non-successor resolver) are
  untouched. A blocked `RESOLVE_TARGET` result gains a `candidates` array;
  managed revisions, receipts and locks are not read differently, so no
  migration is needed.

- A `CREATE_SUCCESSOR` preview, its published result and the successor's
  receipt gain an optional `staleCompanionReferences` array, present only
  when the successor names another revision's companion artifact. Receipts
  written by 0.13.0 carry no such key and keep validating on read; no
  existing revision is rewritten and no migration is needed.

- A file under `<Name>/Notebooks/` that is not a JSON notebook object now
  yields a `verify`/`probe` payload (the notebook `unreadable`, listed under
  `unsealed`, notebooks verdict `drift`) where 0.13.0 exited 1 with a
  traceback. Nothing on disk is read differently; no migration is needed.

- `papersmith status` prints `published` (or `edited-after-publication`)
  where it printed `draft` for a revision the engine published, and its JSON
  `proposal` object gains a `receipt` key (`null`, or `operation` and
  `document_matches`). Nothing on disk is read differently or rewritten; no
  migration is needed.

- `env` appends `.venv/` and `*.egg-info/` to the target clone's
  `.git/info/exclude` (once; its JSON gains `excluded`), and a `.gitignore`
  block authored by `apply` or `materialize --stage scaffold` gains
  `*.egg-info/`. Existing `.gitignore` files are not rewritten, the scaffold
  gap list is unchanged (so `verify` reads an existing target exactly as
  before), and no receipt or ledger changes; no migration is needed.

- `probe`'s `backend` gains `declared` and `source`, and two states
  (`declared-unmet`, `unrecognized-backend`) that only a target stating
  `__backend__` can reach; an existing target states nothing and reads
  exactly as before. `env` gains `--torch`/`--torch-version` and a `torch`
  key (`{"variant": null, "args": []}` without the flag). A newly
  scaffolded target gets the backend-neutral `conftest.py`/`sweep.py` and a
  `pyproject.toml` with `dependencies = []`; files already in a target are
  never rewritten and their receipts are untouched, so no migration is
  needed.

- `papersmith.yaml` is the user's and `upgrade` never rewrites it, so a
  workspace initialized before 0.14.0 keeps its `smoke_and_invariants`
  profile. Where that profile's `implementations/{paper_slug}` names a
  directory that does not exist, `papersmith run` now refuses before
  dispatch and names the edit (`{target}`, `{target_python} -m pytest`);
  where it exists, the profile runs exactly as before. A `--dry-run` of such
  a profile, and every run of a profile naming the new placeholders, records
  a `target_resolution` key in its ledger row. No migration (user-owned file).

- An `IMPLEMENTATION_DOMAIN_PROFILE` naming the other implementation skill's
  profile from a different skills tree now exits `2` with
  `IMPLEMENTATION_DOMAIN_PROFILE_SIBLING` where 0.13.0 ran against it.
  Nothing on disk is read differently; no migration is needed.

- A v1 created by `CREATE_INITIAL_REVISION` from now on carries headings
  without terminal punctuation (`# Title`, not `# Title.`). Existing managed
  revisions are never rewritten and keep their headings; an idea whose two
  sentences differ only in their terminal punctuation is now refused with
  `INITIAL_IDEA_SINGLE_SENTENCE`. No migration is needed.

- Through `cli.mjs`, an `instruction` longer than 65,536 characters (an idea,
  for `CREATE_INITIAL_REVISION`) is now refused with `INSTRUCTION_TOO_LONG`
  where 0.13.0 accepted it. The successor preview and the first revision's
  result gain an additive `instructionBudget` key. Nothing on disk changes; no
  migration is needed.

- A deliberation request carrying `dryRun` on an operation other than
  `CREATE_INITIAL_REVISION` is now refused with `DRY_RUN_UNSUPPORTED` (nothing
  runs); 0.13.0 ignored the unknown field and executed the operation. Existing
  creation locks are untouched; no migration is needed.

- `CREATE_INITIAL_REVISION` results gain additive `sourceWindow` and, when a
  source was cut or left out, `warnings` keys; the default window (4000 bytes)
  and what v1 contains for a given set of sources are unchanged. A request
  carrying `sourceWindowBytes` outside 1..262144, or on another operation, is
  refused. No migration is needed.

- `experimental-deliberation` now accepts digits in the body of a table whose
  first header cell is `Parameter(s)` or `Hyperparameter(s)`; such a document
  was refused by 0.13.0. Every other table is judged exactly as before, and
  published revisions are unaffected. No migration is needed.

- Successor receipts may carry two new optional keys, `rationale` and
  `decider`, only when the request supplied them. The change is additive:
  receipts written by 0.13.0 carry neither and keep validating and reading
  unchanged, so no migration is needed.

- A first revision adopted by hand in 0.13.0 (no state, no receipt) keeps
  reading unchanged and is never rewritten by `upgrade`; the consistency audit
  still reports `MISSING_MANIFEST` for it until `ADOPT_INITIAL_REVISION` is run
  on it explicitly, which writes the state and a receipt carrying
  `adoptedFrom`. `ADOPT_INITIAL_REVISION` joins the CLI's accepted operations.
  No migration is needed.

- `admit` accepts `--no-findings`, and `tests/admissibility.json` may carry an
  additive `noFindings` key; `verify`'s `audit` reports `ok` (with
  `"noFindings": true`) for an empty audit ruled that way. Without the flag an
  empty findings list still refuses `NO_FINDINGS` and still reads
  `audit: none`; existing rulings carry no such key and read unchanged, so no
  migration is needed.

- `handoff` can return a new `deferredBecause` value, `prose-remedy`, only for
  a finding that declares `"remedy_in_prose": True`; findings without the key
  are sized, admitted and reported exactly as before. A target scaffolded
  before 0.14.0 keeps its own `tests/test_audit.py`, which still requires a
  non-empty `remedy_equations`; to declare a prose finding there, apply the
  kit's two-line change to that file and re-seal it with `materialize
  --authored tests/test_audit.py`. No migration is needed.

- `verify`'s `audit.remediesWithoutControl` may list fewer tests than 0.13.0
  did: a remedy test that calls the package through a module attribute or a
  same-file helper is no longer listed, so such a target can move from
  `audit: incomplete` to its next state. Nothing on disk changes; no migration
  is needed.

- An experiments document carrying `[out-of-scope:<id>]` markers now gets
  those claims subtracted from `agree`'s `untested` list, and an agreed `agree`
  payload gains an `outOfScope` key when any is marked. Published experiments
  revisions without the marker read and agree exactly as before, and
  `--acknowledge` is unchanged. The convention file gains one additive key; no
  migration is needed.

- `verify`'s `structure.objectGaps` no longer names `src/<Package>/module.py`
  on a target whose package already holds modules of its own, so such a target
  can now read `structure: ok`; `materialize --stage objects` then writes only
  the two test files. `materialize` accepts `--module`. Targets carrying
  `module.py` and every existing receipt read exactly as before; no migration
  is needed.

- `materialize --stage scaffold` now writes `{{NAME}}` (and `{{REVISION}}`
  when known) already filled, and `materialize --stage objects` now rewrites
  scaffold destinations that still carry `{{REVISION}}`/`{{NAME}}`/`{{MODULE}}`
  and are byte-identical to their receipt, updating those receipt entries'
  `writtenSha256` and `substitutions`; its result gains an additive `filled`
  key. Scaffold files of an existing target that were edited, adopted or
  declared authored are left untouched, and receipts written by 0.13.0 keep
  verifying unchanged (an executed notebook sealed before 0.14.0 is still read
  through the same legacy reconstruction). Kit files already on disk are not
  replaced; the clearer failure messages reach a target scaffolded from this
  release on. No migration is needed.

- `paper-ingestion`'s `extract_pdf.py` accepts a fifth flag, `--force-ocr`,
  and `papersmith.yaml` an optional `paper_ingestion.force_ocr` boolean.
  Existing configurations carry no such key and convert exactly as before;
  the skill-audit roster for `paper-ingestion` moves from 4 to 5 accepted
  flags. No migration is needed.

- `walk` accepts `--commit-template`; without it the walked commits keep the
  exact `walk: <step>` subject and body as before. No receipt or ledger
  records the message, so nothing on disk changes. No migration is needed.

- `papersmith status` and `papersmith audit --check-drift` are quiet about
  projection notes by default; pass `--verbose` to see them. `status --json`
  gains an additive `framework.generator_notes` list. Nothing on disk changes;
  no migration is needed.

- `check_atlas.py` without `--pool` behaves exactly as before; an existing
  `atlas.json` checked with `--pool` may now fail where a quote was
  paraphrased or cites an origin outside the pool. `_failures(atlas)` keeps
  its one-argument form for the command center. No migration is needed.

- `papersmith implement --action materialize` still runs `apply`, and now
  prints a one-line note on stderr pointing at `--action apply`. Its stdout
  and exit code are unchanged.

- `papersmith upgrade` rewrites `.claude/agents/sota-grapher.md` and its
  OpenCode/Pi/`.agents` projections, so the grapher's checker run now
  refuses an atlas whose quotes are not verbatim in the pool's abstracts
  (verified on a scratch workspace initialized from the previous commit).

- Metadata caches written before this release keep their `year: null` and
  keep reading: the cache key is the digest of the raw response, which
  reading one more field does not change, and `bib` checks only that key.
  Re-resolving the same identifier rewrites the same cache file with the
  year filled, and the next `refs.bib` rebuild gains a `year` field.

- `papersmith ingest` refuses exactly the sources it refused before; only the
  refusal text is longer (it keeps its old prefix, then names
  `guidance/paper-guide/` and `ADOPT_INITIAL_REVISION`). Exit code unchanged.

- `CREATE_INITIAL_REVISION` refusing a one-sentence idea keeps its code
  (`INITIAL_IDEA_SINGLE_SENTENCE`) and `nextAction` (`supply_initial_idea`);
  only the blocker's `message` text changes. An empty idea keeps its old
  message.

- `papersmith deliberate --action adopt` (or `--action ADOPT_INITIAL_REVISION`)
  now runs adoption instead of refusing it as an unsupported action. Every
  other action builds the same request as before.

- `CREATE_INITIAL_REVISION` reads declared sources with reserved markers
  neutralised, so an experiments v1 whose window holds a published proposal is
  created instead of refused, and its `## Reference Sources` no longer carries
  the proposal's marker line. A source entry in `sourceWindow` gains
  `reservedMarkersRemoved` when something was neutralised (absent otherwise).
- A `CREATE_SUCCESSOR` preview refused by the accept turn's pre-publish
  validation keeps `message: "CANDIDATE_VALIDATION_FAILED"`, but `nextAction`
  becomes `repair_candidate` (was `inspect_error`) and a `blockers` entry
  names the rule. Canonical-form refusals are unchanged.
- An experiments v1 written by 0.13.0 with copied proposal markers (the
  fixture's `experiments-*-v01.md` has two) now takes a successor that replaces
  the sections holding them; its own bytes, receipt and state are untouched.
- `verify` output gains `fidelity.otherLineageModules` (`[]` unless the
  target binds a per-label `revision` mapping). On a shared target, the
  other skill's modules leave `staleModules` and `drift`, so the headline
  `fidelity.status` can turn from `drift` to `ok`.
- A refused `position` or `settle` on a product folder without its holder
  no longer creates `<Name>/AGREED.md` (or `Experimental_AGREED.md`); the
  next accepted write creates it, with the same scaffold.
- `settle --unwitnessed --reason` without `--done` used to be refused
  `SETTLE_UNWITNESSED_CONFLICT`; with `--under` it now places a line, and
  without `--under` it is refused `SETTLE_UNDER_REQUIRED`.
## 0.13.0

### Added

- **`/upgrade-project` brings the upgrade inside the workspace.**
  `papersmith upgrade` has existed since 0.12.0 and was reachable only from a
  terminal, so an agent working inside a workspace could see that the workspace
  was running an older release and could do nothing about it. The twelfth skill
  closes that: `skills/upgrade-project/SKILL.md`, projected as a slash command
  to `.claude/commands/`, `.opencode/commands/` and `.pi/prompts/`.
  It delegates every write to `papersmith upgrade` and reimplements nothing ---
  the upgrade is a kit copy, a symlink repair, a re-derivation of every
  projection, an orphan sweep and an ordered migration run, with the version
  marker written last, and a second implementation of that is a second answer
  that can disagree with the first. What the skill adds is the two preflight
  refusals that fail better before a write than during one (this is not a
  workspace; the CLI is unreachable), the flag semantics including why
  `--plan-migrations` must not be described as a dry run, and how to read a
  non-zero exit instead of summarizing it as done.

- **The package is publishable to an index, and is not published yet.**
  `pyproject.toml` gained what a published version needs — an SPDX licence
  expression, project URLs, classifiers, and the manual as the long description —
  and `.github/workflows/publish.yml` runs the Node suite, builds the kit,
  inspects both archives and installs the built wheel into a clean virtualenv
  before it uploads anything, because everything above that can pass on an
  artifact that still cannot do its job. It authenticates through Trusted
  Publishing: PyPI verifies a short-lived OIDC token naming this repository, this
  workflow and the `pypi` environment, so no durable credential sits in the
  repository to leak or rotate. It runs on a published release rather than on a
  push, because a version number is spent forever, and it can be rehearsed with
  `gh workflow run publish.yml -f dry_run=true`. The matching publisher on
  pypi.org is configured outside the repository and does not exist yet, which is
  why this release is a draft: the first publication stays a human step.

### Changed

- **The Paper Command Center speaks the architecture diagram's visual
  language, in two themes.** A reader moving from
  `docs/diagrams/papersmith-pi-flow.html` to `papersmith ui` crossed a visual
  seam that carried no information: different type, different elevation,
  different palette, for the same stages and the same gates. Light stays
  `:root`, dark arrives as `[data-theme='dark']`, and the choice persists ---
  the system preference decides the first visit, an explicit choice wins after
  that, and `light` is the floor when storage cannot be read at all.
  Archify publishes no stylesheet, so the signature is transcribed rather than
  imported: elevation as glow instead of drop shadow, radius by opposition
  (pills at 999px against structure at 1px), and tracking by opposition (tight
  on headings, wide on uppercase micro-labels). Archify's infrastructure-role
  hues are deliberately not adopted --- its frontend/backend/database taxonomy
  says nothing about a paper pipeline, so stage, gate and section keep their
  meaning and only their hues move. On the canvas a node's role is now a full
  stroke over a translucent fill of the same hue, the way the diagram states
  it, instead of an accent bar on one edge.

- **The repository lives in the LIAUNAL organization.** The install URLs and the
  badge in the manual, the package metadata, the MCP catalogue and the release
  guide moved from `Daprosero/papersmith-ai` in one commit. GitHub redirects the
  old address, so existing checkouts and pinned URLs keep resolving. The flow
  diagram's recorded source evidence still cites `Daprosero/papersmith-ai` at the
  revision it was read from, which is provenance rather than an address.

### Added

- **The style contract understands two themes, and still refuses literal
  colour.** `ui/src/styles.test.ts` was generalized from a single `:root` to a
  theme map: it reads both blocks, excises both from the text its
  literal-colour rule inspects, resolves dark tokens through a light fallback
  the way the cascade does, and runs every WCAG AA contrast assertion once per
  theme. The contract was extended, never weakened; both themes pass on every
  surface, badge fill, node, edge label and terminal.
- **Browser checks for behaviour and layout.** 255 jsdom tests could not see a
  clipped label or an overlapping control, because jsdom computes no layout.
  Playwright now runs `ui`-local as `npm run test:e2e` against the real FastAPI
  server serving the committed bundle --- not `vite preview`, which resolves
  assets differently and skips the `Host` validation that has broken the
  dashboard before. It waits on `body[data-ready]`, the signal `App.tsx`
  already published. Functional: tab activation and singularity, deep links
  surviving a reload, node selection opening an addressable detail panel, and
  the theme switch actually repainting --- asserted through computed
  `backgroundColor`, because an attribute that changes while the paint does not
  is the failure worth catching. Layout: text clipped by its own box,
  horizontal spill past the viewport, pairwise control overlap, a 24px minimum
  hit target, and the element panel's geometry on both sides of the 900px
  breakpoint.
  It earned its place on the first run: the new uppercase tabs spilled past an
  820px viewport. Bisecting against the pre-restyle stylesheet proved it was a
  regression introduced by this work rather than a pre-existing defect, and the
  tab strip now wraps. Horizontal scroll was rejected for hiding the last tabs
  behind a gesture nobody announces.
  It is deliberately not in `npm run test:all`, which does not run the vitest
  suite either; wiring a browser suite into a gate that skips the unit suite
  would be backwards.

## 0.12.0

### Added

- **`upgrade` migrates workspace artifacts, not only framework files.** The
  recorded `.papersmith/version` is now a claim about a workspace's artifacts
  rather than about which skills tree it holds, and a release that changes an
  artifact's shape can carry an older workspace to it. Migrations run in one
  place — after the kit is copied, because a migration may need the scripts and
  assets of the release that just arrived, and before the version marker is
  written. The mechanism is `src/papersmith/core/migrations.py`.
- **Two classes of migration, and only one of them is recorded.** A
  version-bound migration runs once, when the workspace sits below its gate and
  the installed kit at or above it, and lands in `.papersmith/migrations.json`
  so it cannot run twice. A convergence migration has no gate: it asks the
  filesystem through a read-only probe and is evaluated on every run, because
  the next release can change what it converges toward.
- **`sota-pool/` is a declared directory instead of a survivor.** It holds
  `candidates.json` and `atlas.json` from the scouting agents plus the derived
  `atlas.html`, and it survived upgrades only because `upgrade` deletes nothing
  it did not baseline first. This release ships two convergence migrations:
  `sota-pool-scaffold` creates the pool's `.gitkeep` in older workspaces, and
  `atlas-render-refresh` re-renders `sota-pool/atlas.html` when its atlas, its
  renderer or the vendored viewer bundle it inlines has changed — decided by
  hashes stored in `sota-pool/.atlas-render.json` and never by modification
  times, because `upgrade` rewrites files for reasons that have nothing to do
  with the page.
- **`status` reports pending migrations**, and `upgrade` gained
  `--plan-migrations`, which reports the pending set and writes nothing. It is
  deliberately not named `--dry-run`: that name would imply the kit copy, the
  harness projections and the orphan sweep were previewed as well, and they are
  not.

### Changed

- **The version marker advances only when that version's migrations are done.**
  A failed migration leaves `.papersmith/version` where it was, exits non-zero,
  and the next run retries. `--no-migrate` does not advance it either — doing so
  would record a release the workspace never reached and let `status`'s
  `version_match` report that as agreement. The manifest is the opposite case
  and is always written: it describes files, and the files did move.
- **A version that cannot be ordered refuses rather than guesses.** With the
  marker missing or unreadable, a version-bound migration is reported
  `undetermined` and never applied: migrating artifacts under a relation nobody
  established is the silence the downgrade guard already removed on the file
  side. Convergence migrations are unaffected, because they ask the disk.
- **The downgrade guard and the migration gate share one ordering
  implementation** (`migrations.version_order`), replacing `upgrade`'s own
  `_version_order`.

### Fixed

- **Four `test_papersmith_upgrade` fixtures derive a version newer than the
  kit's instead of pinning `0.9.0`.** A fresh workspace records the
  *distribution* version, so once the package moved past `0.9.0` those fixtures
  turned their own setup upgrade into a downgrade that the guard correctly
  refused: the guard doing its job while the tests asserted the opposite. They
  had been failing the CI gate since `0.10.0`.

## 0.11.0

### Changed

- **The proposal tramo reports its two artifacts separately.** It was lit only
  by `proposals/*.md`, so a published revision and a published revision with
  its graph read the same to the board. It now counts the revisions and the sky
  graphs (`proposals/*.graph.html`), names both in its detail, and reports
  their ratio as its progress -- a revision without its graph is exactly the
  half-done state worth showing.
- **The Pi flow diagram names both artifacts** on `proposals/` and draws a
  dashed `atlas.json` edge from `sota-grapher` to `deliberation-publish`. A
  sixth node in that carril did not survive the diagram's own gates. With a cell
  narrow enough to leave the figure readable, validation reports
  `layout/constraint`: `/experimental-implementation` is ~185px of label in a
  176px cell, and connections shortened with it fall under their 24px floor.
  With cells and gaps wide enough for both, the six-column viewBox reaches
  1370px, where `composition/desktop-readability` projects 8px source text at
  5.43px against its 6px floor. The graph therefore travels as the second
  artifact of the tramo's existing node, which is how the extractor counts it.

### Added

- **The proposal's sky graph is a step of the flow.** Stage 3's graph -- the
  SOTA constellation with the proposal inside it -- was documented, tested and
  run by nobody: the architecture diagram had no node for it, the *Pipeline*
  tab could not see it, and no agent produced it. Three surfaces now carry it.
  `deliberation-publish` now requires the overlay — reporting it as `owed`
  rather than inventing a relation to have something to draw — runs the skill's
  three commands in order (merge, check, render), and reports the rendered path,
  `proposals/<revision>.graph.html`, with the checker's verdict and whether the
  published revision names it. The deliberation's own skill now pins *when* the
  overlay is authored -- before the change is accepted, because the successor's
  text is what names the picture -- and the publish stretch has no `Write`, so
  an overlay it cannot find is reported rather than manufactured.

## 0.10.0

### Changed

- **The dashboard's flow is the architecture diagram's flow.** The Paper Command
  Center's *Pipeline* tab drew six stages invented inside the extractor --
  `ingestion`, `deliberation`, `experiments`, `drafting`, `auditing`,
  `publishing` -- while `docs/diagrams/papersmith-pi-flow.html` drew the same
  project as twelve numbered tramos plus a transversal audit lane, and nothing
  compared the two. The board now draws those twelve tramos in the diagram's
  order, with the diagram's main chain as the edges, and each tramo lights up
  from its own artifact on disk: `sota-pool/`, `guidance/`, `proposals/`,
  `implementations/`, `.experimental-deliberation/`, `experiments/`, the
  accounts store, the inbox, `paper/Figures/`, `sections/`. A tramo with no
  artifact reports what is missing instead of an invented progress. The chain
  travels in the payload (`pipeline_chain`, `gate_links`), so the drawing cannot
  disagree with the stage list it is drawn from -- which is how it disagreed
  before.

### Added

- **The writing flow, section by section.** A new *Writing* tab draws the
  paper's ten sections in rendering order, each with its live status, its word
  count and its blocks, as a flow of its own.
- **`npm run build:ui` and `npm run dev:ui`.** Rebuilding or serving the
  dashboard meant knowing to run `npm install` and `vite build` inside `ui/`,
  and the repository offered no script for either half.

## 0.9.0

### Added

- **`papersmith init` reports its own progress.** A bar with an estimate of the
  time left, plus the streamed log of the two child processes it runs —
  `npm install` and the workspace's environment provisioning — which until now
  ran with their output captured: minutes of silence, and on a cold cache up to
  the whole provisioning timeout. The estimate starts from declared priors and
  is recalibrated with the pace the run measures, so a step that overruns its
  share moves the number instead of contradicting it. `--progress` forces a
  plain log for CI, `--no-progress` silences the bar, and a pipe stays silent by
  default — which is what keeps the MCP server's child invocation readable.

## 0.8.0

### Changed

- **The Pi entrypoint is the file Pi reads.** The `pi` runtime's generated
  entrypoint moves from `PI.md` at the workspace root to
  `.pi/APPEND_SYSTEM.md`. Pi never read `PI.md`: its project context candidates
  are `AGENTS.override.md`, `AGENTS.md`, `AGENTS.MD`, `CLAUDE.md` and
  `CLAUDE.MD`, while a trusted project `.pi/APPEND_SYSTEM.md` is appended to the
  system prompt and takes precedence over the operator's own agent-level append
  instead of combining with it. `upgrade` retires a baselined `PI.md` — nothing
  else could, since a static entrypoint is deliberately outside the orphan rule
  — and `audit` names a leftover one, in any workspace, as surplus. A `PI.md`
  this tool never wrote is the operator's file and is never removed.
- **The SOTA atlas is a 3D sky.** `/plausibility`'s `sota-pool/atlas.html`
  now draws the constellation with three.js instead of an inline SVG plane:
  family neighborhoods at their own heights, one tilted orbital plane per
  system, arcs between systems, orbit/zoom/fly-to controls. It is still one
  self-contained file that opens offline and renders byte-identically from the
  same atlas: `render_atlas.py` (stdlib-only) precomputes the scene and inlines
  the vendored viewer `skills/plausibility/assets/atlas3d.bundle.js`, rebuilt
  with `npm run build:atlas-viewer` (pinned `three` and `esbuild`
  devDependencies). The planet popup now builds its text with `textContent`.

### Fixed

- **Skill descriptions fit the ceiling the harness enforces.** Pi caps a
  skill's `description` at 1024 UTF-16 code units
  (`MAX_DESCRIPTION_LENGTH`), and `paper-writing` sat at 1680 while
  `remote-execution` sat at 1814; Pi warned and loaded both anyway, so nothing
  ever failed. They now measure 1015 and 923, and
  `tests/test_skill_descriptions.py` holds the budget — in UTF-16 code units,
  because that is the unit JS `length` counts and therefore the unit the
  ceiling is written in. No claim was dropped on the way: `remote-execution`'s
  provenance date for the pinned `kagglesdk` (`since 2025-07-11`) moved into
  the body beside the pin, where it had never been written down.
- **Pi agents no longer list unsourced `mcp`/`mcpScript` tools.** The
  `.pi/agents` projection skips `WebSearch`/`WebFetch` with a note instead of
  mapping them to names Pi does not document. The Antigravity
  `commandExecutionPolicy` values are documented as having undocumented
  semantics; its output is unchanged.
- **Workspace `.gitignore` covers the skills links.** A new workspace now
  ignores `.claude/skills`, `.opencode/skills`, `.pi/skills` and
  `.agents/skills` (the generated symlinks to `skills/`), so `git add .` no
  longer commits them.

### Added

Interactive Paper Command Center: a light theme, a clickable diagram and a
session history.

- **The proposal travels with its own sky.** Stage 3 ships a 3D graph beside the
  published revision — the SOTA constellation with the proposal inside it, drawn
  by the same vendored viewer. `merge_proposal_sky.py` merges the pool
  (`sota-pool/atlas.json`) with the proposal's overlay
  (`proposals/<revision>.sky.json`) into one atlas, and the existing
  `render_atlas.py` draws it, so the proposal's main idea, the topics it takes
  from the SOTA papers, its one novelty claim, the issue it could resolve and
  its three to five contribution concepts are nodes with real edges into the
  papers they touch — the relationship is drawn rather than asserted. The atlas
  gains one optional slot, `contribution` (orbit 1, zero to five planets), which
  a paper leaves empty; the three-to-five range belongs to the merger, because
  it is the overlay's contract and not the constellation's, and the pool's own
  checker stays the single authority on families, orbits and evidence.
  `render_atlas.py` also gains `--title`, so one viewer can name another
  domain's sky instead of borrowing a title that would be false for it.
- **Read-only paper preview routes in the command center.**
  `GET /api/paper/preview` returns sections (extractor order and ids) with
  plain-text block bodies from `paper/main.tex`, citation keys, `written`,
  truncation/duplicate flags, PDF/figure info (with an `mtime` in ms used as
  a `?v=` cache-buster) and `sections_dir` (`ok`/`absent`/`unsafe`, `truncated`
  past 100 non-canonical sections); `GET /api/paper/file?name=`
  serves only `main.pdf` and `figures/<id>.pdf|png` (real directory
  `paper/Figures/`; id is one `[A-Za-z0-9._-]` segment, no leading dot, at most
  100 characters). Reads are size-capped before reading (`main.tex` 2 MiB,
  sections 256 KiB, 200 KiB of text per response, 25 MiB per file with 413),
  resolved and contained in the workspace, regular files only. Responses carry
  `nosniff`, `X-Frame-Options: SAMEORIGIN` and `no-store`; there is no CSP
  sandbox and no `Range` support. The `Host` allow-list (421) covers them only on
  loopback binds; non-loopback binds do no `Host` filtering.
- **Preview tab.** `#preview` shows the written block text (escaped plain text,
  citation keys as chips, placeholders for unwritten blocks, truncation and
  `main.tex` status notices) beside the compiled `paper/main.pdf` in an
  `<iframe>` (with a stale badge) and a list of `paper/Figures` files. It is
  fetched when the tab opens and refetched when the workspace revision changes,
  with an inline error and Retry. The visual checker covers the tab.
- **Atlas tab.** `#atlas` shows a native summary of `sota-pool/atlas.json`
  (systems, planets, families, link and relation counts, a capped evidence list,
  a validation chip) beside `atlas.html` in an
  `<iframe sandbox="allow-scripts">` without `allow-same-origin`. Every text is
  escaped; absent, too-large, unsafe, unreadable, invalid, missing-HTML,
  missing-JSON and STALE states are explained. The atlas is not watched, so it is
  fetched when the tab opens and on a Refresh button, with an inline error and
  Retry. The visual checker covers the tab and waits for the frame fetch.
- **Decisions tab.** `#decisions` renders `/api/decisions` as a read-only
  timeline: dated events newest first, then an "Undated" group for edit receipts; each
  row shows a UTC timestamp, a source chip, the kind, the summary and the `ref`
  as plain text, an "unverified" label for lifecycle records read without hash
  checks, and muted notes. Per-source status chips (ok, absent, unreadable,
  too_large, counts, detail, truncated), a client-side source filter and a
  "Showing N of total" notice. Fetched when the tab opens and on Refresh, with an
  inline error and Retry; all text is escaped. No Sections link (not cleanly
  derivable). The visual checker covers the tab.
- **Read-only decisions timeline route in the command center.**
  `GET /api/decisions` merges, on request, normalized events
  `{ts, source, kind, summary, ref}` from the declarations region of
  `paper/main.tex` (only the current state is stored, so earlier values are not
  recoverable), the `.proposal-deliberation/` and `.experimental-deliberation/`
  receipts and lifecycle transitions, and the remote-execution ledgers at
  `implementations/<repo>/<Name>/.remote-execution/ledger.jsonl` (exactly two
  levels, no recursion; `kaggle-inbox/` is never read). Edit receipts have no
  timestamp, so their events carry `ts: null` and sort after dated events (file
  mtime is never used); the initial-revision receipt carries `createdAt`, which is
  its `ts` ("Created initial revision r01"); deliberation events are plain-JSON reads without the
  lifecycle hash checks and carry `verified: false` (to be shown as
  "unverified"). Newest first with a stable tie-break; each source reports
  `status` (`ok`, `absent`, `unreadable`, `too_large`) so one broken source never
  fails the response. Caps: 500 events per source, 1000 total (`truncated`),
  `main.tex` 2 MiB, 256 KiB per receipt or transition, 500 files per sidecar
  directory, 20 ledgers of 2 MiB and 2000 lines each (the newest 2000 lines are kept; `detail`
  counts the oldest ones ignored). Optional `source=` (422 on
  an unknown name) and `limit=` (1 to 1000). Nothing is written. The `Host`
  allow-list (421) covers it only on loopback binds.
- **Read-only SOTA atlas routes in the command center.** `GET /api/atlas`
  reports the state of `sota-pool/atlas.json` and `atlas.html` (ok, absent,
  too_large, unsafe, unreadable, invalid), staleness (json newer than html),
  the workspace checker's verdict (`ok`, `failed` with up to 50 errors,
  `unavailable`) and a summary (systems, families, links, relations, evidence).
  Each file entry carries an `mtime` (ms) the UI uses as `?v=` on the iframe;
  `GET /api/atlas/view` serves `atlas.html` (404 absent/unsafe, 413 over 2 MiB)
  under `Content-Security-Policy: sandbox allow-scripts; default-src 'none';
  script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:`,
  `nosniff`, `no-store`, `X-Frame-Options: SAMEORIGIN` and
  `Referrer-Policy: no-referrer`. Reads are size-capped (2 MiB), resolved and
  contained in the workspace, regular files only; nothing is written or
  regenerated. Validation loads the workspace's own
  `skills/plausibility/scripts/check_atlas.py` from that one fixed path and runs
  it inside the server process (workspace Python execution: only serve trusted
  workspaces); a missing or failing script yields `unavailable`. The `Host`
  allow-list (421) covers both routes only on loopback binds.
- **Light theme.** The dashboard uses one light theme built on colour tokens;
  Vitest guards reject colour literals outside `:root` and check WCAG AA
  contrast for the token pairs. The state and health payloads now load
  independently, so a slow health measurement no longer keeps the page on
  "Loading".
- **Clickable pipeline diagram with deep links.** Every stage, gate, section
  and edge can be selected with the mouse or the keyboard and opens a detail
  panel (fields, connections, history). The selection lives in the URL hash
  (`#pipeline?el=<id>`), so links open the element directly.
- **In-memory history.** A History tab and `GET /api/history` (cursor paging
  with `boot_id`, `after_seq`, `has_more`, `reset` and `gap`) record section,
  gate, stage, health and smoke changes since the server started, and
  `history_append` streams new entries over SSE. Nothing is written to disk.
- **Host allow-list.** On loopback binds the server answers 421 to a `Host`
  header it does not recognise; `papersmith ui --allowed-host HOST:PORT`
  (repeatable) adds one, for example `--allowed-host localhost:5173` when
  running `npm run dev`. Stage history entries now say what changed.
- **Visual checker and UI tests.** `scripts/command-center-visual-check.mjs`
  screenshots every tab in Chromium (`--full-page`, `--click-check`,
  `--drag-check`); the Node CI job now also runs `npm ci --prefix ui` and the
  Vitest suite (`npm test --prefix ui`).

Harness parity: skills, commands, agents and guards in each harness, wired by
`init` and `upgrade`, with an honest report of what is not.

- **Per-harness wiring summary.** `init` and `upgrade` print one line per active
  harness (`skills`, `commands`, `agents`, `plugins` as `wired`, `unsupported`,
  `failed` or `blocked`) and add a `wiring` key to their results. The support
  matrix lives in `generators.HARNESS_CAPABILITIES`, derived from the constants
  `render_files` writes through; exit codes and existing keys are unchanged.
  The health inspector's structural fallback also checks agents and the
  plugin/extension. The README table of what each harness wires is tested
  against that matrix.
- **README support matrix and Antigravity note.** The README now carries the
  sourced per-harness support matrix (with source URLs and the 2026-10-02 date)
  and states why Antigravity gets no command files (workflows are deprecated in
  favour of skills); its commands cell reads "unsupported — vía skills". Nothing
  generated changes.
- **Link-failure warnings.** Skill-link failures (an `OSError`, or a real
  directory at a link path) are reported by `init` and `upgrade` instead of
  being skipped silently.
- **OpenCode agents.** `init` and `upgrade` project each `.claude/agents/*.md`
  definition into `.opencode/agents/<name>.md` with `mode: subagent` and a
  least-privilege `permission` block mapped from the Claude `tools:` list
  (unknown tools are never granted and are reported). `upgrade` removes agents
  whose source disappeared.
- **Antigravity agents.** `init` and `upgrade` generate `.agents/agents/<name>.md`
  from the `.claude/agents/` sources (explicit `tools` allow-list mapped to
  Antigravity tool names, `commandExecutionPolicy` `off` unless the agent has a
  shell tool). Stale ones are removed on upgrade. Sourced from
  https://antigravity.google/docs/subagents and /docs/hooks.
- **Pi prompt templates.** `init` and `upgrade` project one prompt template per
  skill under `.pi/prompts/<name>.md` (the same body as the Claude Code and
  OpenCode commands, with `$ARGUMENTS`), and `upgrade` removes the ones whose
  skill disappeared.
- **Pi off-path push guard.** `init` and `upgrade` generate
  `.pi/extensions/refuse-offpath-push.js` for workspaces that declare `pi`: a
  `tool_call` extension that shells out to the same Python guard as the OpenCode
  plugin (a tripwire, not a gate) and fails open when the guard, python, or the
  event is unusable. `docs/guard-hooks.md` documents an opt-in Claude Code hook
  snippet (never written to `.claude/settings.json`) and records that an
  Antigravity guard is unsupported until its hook input schema is verified.
- **Antigravity `.agents/skills` link.** `init`, `upgrade` and
  `scripts/setup-harnesses.sh` link `.agents/skills` to `skills/`, so skills can
  be invoked as `/name`. Antigravity still gets no command files.
- **Docs.** `docs/harness-support-matrix.md` (sourced per-harness support) and
  `docs/guard-hooks.md`; the README now states per harness what is wired,
  unsupported or opt-in.

### Changed

- **The health check is per enabled tool.** It requires each harness link and
  commands directory only for the tools the workspace enables, instead of
  reporting drift for every known harness.
- **Antigravity uses only documented locations.** Skills at `.agents/skills`,
  agents at `.agents/agents/` and the rules entrypoint at `.agents/AGENTS.md`.
  `.antigravity/rules.md` and `.antigravity/skills` are no longer generated.
  Pre-1.0 breaking change: existing workspaces are not migrated; re-run
  `papersmith init` in a fresh workspace.
- `upgrade` also removes stale `.pi/agents` files whose source disappeared.
- Pi agents need the third-party `pi-subagents` package; Pi core has no
  sub-agents.
- Unverified before release: that real Antigravity lists `.agents/skills/<name>`
  as `/name`, and whether Pi shows a trust prompt for project `.pi/prompts`. If
  the Antigravity premise fails, ship the Pi part alone.

## 0.7.1

### Fixed

- **The clean-context gate fails when the gate itself fails.** `scripts/clean_context_gate.py`
  only compared the empty-HOME run with the decoy-HOME run, so a suite that
  failed the same way under both exited 0. The empty home is the machine with
  no personal context, so its own failure now fails the step. Its temporary
  homes are also removed on SIGTERM (a cancelled CI job) and when a read-only
  file is left under HOME, and a leftover is reported instead of ignored.

### Changed

- **CI runs the suite once per job, not twice.** The plain `pytest` step is
  gone: the gate already runs the declared suite under an empty HOME, and
  with the fix above it fails on that run's own failure. About eleven minutes
  less per Python job.
- **The README installs the latest `main`**, never a pinned tag, and its
  counts (CLI commands, skills, agents, MCP tools), flag tables, badges and CI
  description now match the code.

## 0.7.0

### Added

- **Pi receives the agent roster.** The nineteen agent definitions existed
  only under `.claude/agents/`, while Pi discovers agents at
  `<cwd>/.pi/agents/*.md` -- so in that harness a delegated stretch had no agent
  to land on, and a flow could stall asking the operator about routing that did
  not exist. The kit renderer now projects each definition onto Pi's shape:
  front matter travels verbatim except `tools:`, mapped onto Pi's tool names
  (`WebSearch`/`WebFetch` onto the MCP gateway the agent bodies already
  prefer), and the body's `.claude/skills/` references become the
  harness-neutral `skills/` link every workspace already carries. It is a
  rendered path, so `init`, `upgrade`, `status` and the drift check pick it up
  from the one path authority -- and nothing is forked: the projection derives
  from `.claude/agents/` on every run. A malformed definition, an absent or
  unsafe name, or an unreadable file is skipped with a warning, never raised
  on.
- **A fresh workspace ships the `paper_writing` connector roles.** Without
  them, `paper_cli.py resolve` refused `RESOLVER_ROLE_EMPTY` before any
  literature work could start -- and that front door is what the scout and the
  screener both depend on. The seeded block mirrors this repository's own:
  OpenAlex/Crossref/arXiv for resolution, and full-text only for the two
  connectors whose own resolved metadata names a fetchable PDF. `contact` is
  seeded empty on purpose; it is the operator's courtesy address for OpenAlex's
  polite pool, never a shared credential.

### Fixed

- **`init` no longer aborts a workspace's provisioning on the editable
  install.** The provisioner ran `pip install -e <root>` unconditionally and
  with `check=True`, and a workspace is not a Python project -- no
  `pyproject.toml`, no `setup.py`, only `requirements.txt`. Pip refused with
  "does not appear to be a Python project", the step aborted before
  `marker-pdf`, and the workspace reported `OCR Engine Missing` while its conda
  environment was otherwise fine: `fastapi` imported and `papersmith ui` ran.
  The editable install now runs only where there is a Python project to
  install, which is the framework checkout, and says so when it skips.
- **`resolve` accepts the identifier a user actually pastes.**
  `arXiv:1512.03385` was sent to the arXiv API with its prefix, and that feed
  answers entry-less -- measured: 706 bytes with no `<entry>`, against 2814 for
  the bare id -- so the command died on a traceback instead of returning
  metadata. One case-insensitive `arXiv:` prefix and surrounding whitespace are
  stripped before the query, and a feed that names no work now refuses as
  `IDENTIFIER_UNRESOLVED`, the code the contract already documented.
- **Both offline smoke wrappers are hermetic again.** They called `init` with
  `--no-npm` and no `--no-env`, so the wrapper provisioned a real
  multi-gigabyte environment: the wiring smoke built one inside its own 180s
  test timeout and failed there, while its header promises "no npm, no
  network". Neither line had changed since it was written -- `init` gained the
  provisioning step two days later -- and the guard written to catch exactly
  this swept `tests/` only, so it stayed green over both callers. The wrappers
  pass `--no-env` now, and the guard sweeps `scripts/` and `.github/` too.

### Internal

- `.gitignore` covers the `.venv` symlink CI creates. The directory form
  (`.venv/`) does not match a symlink, so `git status` reported the workflow's
  own artifact as untracked.

## 0.6.0

### Added

- **`papersmith ui`: the Paper Command Center.** A local dashboard and
  health/wiring control plane for an initialized workspace, reachable through
  one command. It serves the workspace's own state -- paper metadata, the ten
  section contracts, the four quality gates, the pipeline stages, and the
  evidence ledgers -- over `/api/state`, reports harness, skill, agent and
  environment wiring over `/api/health/wiring`, and streams changes over SSE
  within about a second of a section edit. The backend ships in the kit
  (`skills/_core/command_center/`), so a workspace can run
  `python -m skills._core.command_center.server` standalone with no Node/npm
  dependency in the paper directory; the React/Vite dashboard is committed as a
  built bundle beside it, and `--export-static` writes a copy anywhere. The
  server is read-only: it observes a paper and never edits one.

### Changed

- **`init` reports a wired harness `skills` link like every other kit file,
  and `upgrade` repairs one.** Each harness (`claude`, `opencode`, `pi`,
  `antigravity`) reaches the kit through a relative `skills` symlink. A
  filesystem that could not create one used to read as a silent success; it now
  surfaces as a gap. The link never overwrites real, non-symlinked content at the
  same path, and `upgrade` re-links a stale one. A hermetic smoke script,
  `scripts/cli-paper-wiring-smoke.sh`, asserts the four links, agent and
  slash-command parity across the harnesses, and live repair.
- **`init` provisions the workspace environment, and `papersmith ui` resolves
  the interpreter that provisioning creates.** `init` runs the workspace's own
  `scripts/setup_env.py install` (fail-soft, skipped with `--no-env`), so the
  dashboard works straight after `init` instead of exiting on a raw
  `ModuleNotFoundError`. `ui` looks for `.micromamba/envs/papersmith` first, then
  a `.venv`, and refuses with the one command that provisions the environment
  when neither can import the backend.

### Fixed

- **`scripts/setup_env.py` installs the command center's dependencies.**
  `fastapi`, `uvicorn`, `watchfiles` and `pydantic` were declared in the kit's
  `requirements.txt` but never installed, so the environment the gate names could
  not load the server's tests. They are installed from the same list now.

## 0.5.1

### Added

- **`settle --attach --replace`: re-pointing a proof is not retracting a
  claim.** A checklist line's `` `test_<id>` `` witness could be attached
  once and never moved -- `--attach` refused `SETTLE_ALREADY_WITNESSED` on a
  line that already carried one, and the only path that reached a re-point
  was `--reverse` followed by a fresh placement, which de-ticks and
  un-witnesses a line that was already measured and closed. `--replace`
  closes that gap as a modifier on `--attach`'s own write, not a sixth mode:
  the mark is never touched (mark-blind between a ticked and an open line),
  and every other byte of the holder file is identical before and after the
  call. Three new refusals guard it, all `INVOCATION_DEFECT`:
  `SETTLE_REPLACE_CONFLICT` (`--replace` without `--attach`),
  `SETTLE_NOTHING_TO_REPLACE` (the located line carries no witness at all --
  plain `--attach` is the create path), and `SETTLE_WITNESS_UNCHANGED` (the
  incoming token equals the one already there). Performs no read of
  `tests/`: gating on whether a witness names a real test stays exactly
  where it already was, at `verify`/`close`. The previous token is recorded
  as `replacedWitness` in both the `settle` ledger event and the command's
  response, beside an always-present `replace` boolean that mirrors the
  other four mode flags on every `settle` call.

### Changed

- The one sealed `settle` case's declared golden delta did not materialize:
  that case already refuses `SETTLE_NOT_DISCUSSED` before reaching the
  success path where `replace`/`replacedWitness` would appear, a
  pre-existing condition unrelated to this change. `tests/seal/digests.json`
  is therefore unchanged -- recaptured and confirmed byte-identical, not
  regenerated.

## 0.5.0

### Added

- **`figure-review`, the tenth skill: the eye that looks at the rendered
  diagram.** `render` compiled a figure to PDF and `figure audit` judged it
  against the prose, and nothing ever looked at the picture. Overlapping boxes,
  text running off the canvas and bad connections were all reported
  `unmeasured` -- honestly, but unmeasured, and the socket for the skill that
  would measure them had been written and left empty.

  The skill rasterizes the already-compiled `Figures/<id>.pdf` through the
  first of `pdftoppm`, `pdftocairo`, `gs`, `sips` that resolves, decodes the
  PNG with a stdlib `zlib` reader, and computes what a raster can actually
  support. It calls `latexmk` never, so it spends nothing against `render`'s
  repair budget, and it imports nothing into `paper-writing` -- the join is
  `--visual-report <path>`, a report already on disk read as plain data. A
  test now holds that import edge absent rather than leaving it true by
  accident.

  What it reports is graded by what can be known, and the grading is the
  point:

  - **A verdict** for `out-of-bounds` and `overlap` -- computed, numeric,
    with intersecting boxes in pixel and point coordinates, and reported as
    unnamed regions. The raster found the collision; the source names the
    nodes, and nothing here joins them.
  - **A number with no verdict** for `canvas-occupancy`. "Too much whitespace"
    is a judgement about composition, so the fraction is reported and nothing
    fails on it.
  - **An announced silence** for legibility, style, connection correctness and
    which component an overlap belongs to, each with a named reason.
  - **An assisted reading** for what the agent itself sees. It is labelled,
    never appears in a verdict field, and may never upgrade an `unmeasured`
    dimension to `pass`.

  `out-of-bounds` is itself `unmeasured` when the source declares no border: a
  standalone TikZ canvas is fitted to its own ink, so without one there is no
  way to tell ink that ran off from a canvas that was drawn to fit.

- **`figure audit`'s report carries a `visual` key**, always present, never
  null, supplied by the caller and unable to change the semantic verdict. A
  visual `fail` beside a semantic `pass` leaves the top-level verdict at
  `pass`, and a test holds that in both places it could regress.

### Fixed

- **`figure-auditor`'s precondition is a command instead of a belief.** It read
  "when that skill is available in this session" with nothing measuring it; it
  now runs the skill's front door and quotes the exit.
- **`legibility`'s reason for being unmeasured was false.** It named a missing
  image tool. Glyph metrics come from the PDF's text layer, not an image, so
  the tool was never the obstacle -- legibility is a threshold judgement, and
  the reason code now says so. Deferring behind an honest reason is a note;
  deferring behind a false one is the defect this release exists to remove.

### Internal

- Five sequential work units, each mutation-proved: every lock was broken on
  purpose with the mutation a weaker lock would have survived, and watched to
  go red. One lock did survive its mutation and was rewritten -- it had been
  comparing literals rather than calling the function it claimed to guard.
- A file this repository tracked inside the target's own repository, under a
  path its own `.gitignore` declares it does not carry, is tracked no longer.

## 0.4.0

### Added

- **A step now reports the product the repository was told to ignore.** A
  `__steps__` step declares what it writes, `step` already compares those
  declared roots against what the run actually wrote, and nothing asked whether
  those written files were ones `.gitignore` excludes. So a step could declare a
  product, produce it, and have git skip it silently: the declaration read
  satisfied, the run read clean, and the artifact never entered history. Nobody
  finds out until someone looks for a file that was never committed.

  `wrote` now carries `ignored` -- always present, `[]` when clean -- the subset
  of the run's own written paths the repository's ignore rules exclude, plus an
  `ignoredNote` when it is non-empty. Both readings reach the terminal ledger
  event, so the finding is durable rather than printed once.

  It reports and never refuses, for the reason `undeclaredProduces` already
  gives: it grades an act already taken. The step has run and the files are on
  disk; refusing now undoes nothing and hides the finding behind an error.

  The check runs over the paths actually written, never over the bare declared
  roots. A declared root checked against a content-only rule (`Results/*`)
  answers "not ignored" truthfully and uselessly, because every file under it
  is. That distinction is what the test fixture proves: its rule is anchored to
  the product folder, because an unanchored rule matches the product-relative
  path at the repository root just as well and would pass with the path join
  deleted.

### Internal

- This repository's own `.gitignore` already stated the insight behind the above
  by hand, in the one file whose whole job is declaring what does not ship: *"una
  regla escrita nombrando lo que existia ese dia no alcanza a lo que nace
  despues"*. It was applied to two subtrees one at a time and derived nowhere.

## 0.3.1

### Fixed

- **The `pin-published` refusal no longer prescribes a push nobody measured.**
  It appended the same remedy -- push it and re-pin -- to every failure it
  caught, so a remote answering `not our ref`, a DNS failure, a proxy refusal
  and a scratch `git init` that could not write all arrived at one sentence
  telling the operator to push. Nothing in the skill had ever asked how much
  that push would carry. The refusal now takes one of two shapes, chosen only
  by whether the weight could be read and never by how large it is: measured
  states the count and keeps the remedy; unmeasurable states what is known and
  prescribes nothing. That second shape is not new to this codebase -- the
  `GitTimeoutError` branch one block above has always named no remedy, because
  a question that could not be finished being asked is not the remote saying
  no. That branch is untouched here; it was the model, not the patient.

  The reader is local and transfers nothing. It matches a configured remote to
  `--repo-url` by exact string comparison, resolves the cached
  `refs/remotes/<name>/<branch>`, and counts commits. Two remotes sharing one
  URL resolve to unmeasurable rather than picking one: they are independent
  caches fetched at different moments, so a choice between them is an answer
  the operator cannot audit. The measurement is therefore often unavailable,
  and that is the intended trade -- a weight anchored on the wrong remote is a
  number that looks measured and is not.

  The clause states an exact distance from the cache and claims nothing about
  the remote now. An earlier draft called that number a floor. It is a ceiling
  on the real push: a remote that moved forward since the last fetch needs
  fewer objects, not more. Both framings over-claim, and over-claiming from a
  true measurement is the defect this change exists to close.

## 0.3.0

### Fixed

- **A campaign submitted with `--unit` now distributes the work.** Both
  per-submission facts already reached the worker — the packer splits the unit
  list across workers and writes each worker's own slice, `--smoke` sets the
  mode the same way, and the adapter merges both into the job folder's
  `run-config.json`. Nothing read them. Every worker received its slice in a
  file nobody opened and ran the identical whole job, so a distributed
  campaign distributed the ledger and not the work. `submission_environment()`
  is now the one place either name is decided, applied by both the notebook
  and callable branches and kept separate from `kernel_environment()`, which
  the callable branch has no clone or `PYTHONPATH` to compose for. An absent
  mode or absent units leave the environment as it was rather than
  substituting an empty string for a value nobody declared; a DECLARED empty
  list still sets the variable, because only a present key can say that zero
  units was the answer.
- **`lfs` names the large files that are real content.** It reported the
  pointers by path and the materialized side by tally, so a reader needing one
  specific checkpoint could not tell whether it had arrived — while the
  skill's own table promises to report which files are which.

### Internal

- The D2 grounding tripwire counts recorded runs before judging, instead of
  failing permanently. Below ten it announces the silence; at or above it, it
  applies the falsifier and either names what fired or asks for the discharge.
  A permanently red test is not a signal, and this repository has already paid
  for that lesson once.
- `init`'s tests derive the recorded version from the kit instead of restating
  `0.1.0`, a literal that passed for a thousand commits and broke on the first
  real bump.

## 0.2.0

The first release where the version means anything: `0.1.0` had been frozen
since the package skeleton, so nothing downstream could tell two builds
apart.

### Fixed

- **The provisioned environment can now run the suites.** `setup_env.py`
  built an environment missing `nbformat`, `nbclient`, an editable install of
  this project, and `ipykernel`. Running the configured gate under it failed
  31 tests. `nbclient` pulls in `jupyter_client`, which knows how to talk to
  a kernel, and never `ipykernel`, which runs the cells — so that last gap
  surfaced as a child process exiting non-zero rather than as a missing
  module.
- **`npm run setup` runs.** It invoked bare `python`, which does not exist on
  a machine that has only `python3`, while the script it calls documented
  `python3` in its own usage. Same for `setup:env`, `clean:env` and two
  README instructions.
- **The test gate names the environment this project provisions.** It named
  bare `pytest`, resolved by the caller's `PATH` — measured resolving to a
  Python 3.9 install that cannot import this project at all.
- **`upgrade` refuses to move a workspace backwards.** It read the kit's
  version and wrote it in three places while comparing only for equality, so
  installing an older kit rolled a workspace back in silence and reported the
  older version as the new truth. A deliberate rollback now needs
  `--allow-downgrade`, which is its own flag: `--force` already means "write
  even when the bytes match" and must not double as permission to change
  version.
- **Ingesting a paper no longer deletes its appendix.** `strip_references`
  cut from the references heading to the end of the document. Measured on a
  116-document corpus: five papers place supplementary material after their
  references, and the cut removed 52% to 74% of each file — a generalization
  bound, a derivation, dataset details, an algorithm's specification. Every
  references section is now cut, and only up to the next heading, which also
  makes the operation idempotent.
- **A failed remote run reports why.** The Colab executor records its reason
  in `status.json`, bounded on purpose; `poll` reported the exit code alone
  and dropped it. Separately, the "session not found" test matched that
  phrase anywhere in a helper's output, including the run's own recorded
  error — so a run whose error contained those words was reported as a
  vanished session, which means *evidence missing* rather than *this failed*.

### Added

- **Each `write` run records its grounding counts** to
  `paper/.paper-writing/grounding-runs.jsonl`, one line per completed run.
  A ruling that shipped without a numeric threshold named ten recorded runs
  as its falsifier, and nothing recorded them.
- **A `--allow-downgrade` flag** on `papersmith upgrade`.

### Changed

- **`upgrade` now refuses where it used to proceed.** Installing an older kit
  over a newer workspace was accepted silently; it now raises unless
  `--allow-downgrade` is given. For anyone driving `upgrade` from a script
  this is a breaking change, and under strict conventional commits its commit
  deserved a `!` it did not carry. Recording it here because a reader looking
  for what broke looks in this file, not in a commit subject.

  Worth naming the reason it was missed: across the 817 commits between
  `0.1.0` and this release, not one carried `!` or `BREAKING CHANGE`. The
  marker has never been used in this repository, so a version derived from
  commit types cannot answer whether a major bump is owed -- the input for
  that question was never written down.
- **Pin conditions are named by id, never by position.** Two conditions had
  been inserted into the middle of the list; the doctrine table renumbered
  itself and 55 prose references across four files did not, leaving two
  different functions documented under the same ordinal.

### Internal

Guards added for defects that were previously invisible: the two version
sources are held to each other, the gate's interpreter is probed against
every import the suites and their assets actually require plus a notebook
kernel, scratch fixtures are held to resolving their paths (a macOS symlink
had four tests failing over correct code), and the end-to-end suite's line
budget now counts code rather than taxing the explanations beside it.
