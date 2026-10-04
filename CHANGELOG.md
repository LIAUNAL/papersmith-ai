# Changelog

Notable changes to papersmith-ai, newest first.

This file starts at 0.2.0. `0.1.0` was set in the commit that created the
package and never moved again across more than a thousand commits, so there
is no honest way to reconstruct a release history for it — its record is the
git log, and pretending otherwise would put a fabricated summary where a
reader expects a kept one.

Versions follow [semantic versioning](https://semver.org): while the first
number is `0`, breaking changes can still arrive without a major bump.

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

### Fixed

- **Pi reads its own entrypoint now, and its two longest descriptions fit the
  Agent Skills budget.** Pi's context-file candidates are only
  `AGENTS.override.md`, `AGENTS.md`, `AGENTS.MD`, `CLAUDE.md` and `CLAUDE.MD`,
  so the repository-root `PI.md` a Pi workspace shipped was never read: Pi was
  routed by the Claude projection while 7.1K of Pi routing documentation sat
  unread beside it. The entrypoint is now `.pi/APPEND_SYSTEM.md`, which Pi
  appends to the project system prompt, and the canonical `skills/` tree is
  discovered through the seeded, operator-owned `.pi/settings.json`
  (`"../skills"`) -- no symlink, no setup step, so `.pi/skills` left the
  harness roster. Separately, `paper-writing` (1680) and `remote-execution`
  (1814) exceeded Pi's `MAX_DESCRIPTION_LENGTH = 1024`; both descriptions were
  compressed to fit (1015 and 923) with every routing trigger kept, and the
  provenance of the pinned `kagglesdk==0.1.37` dependency moved from the
  `remote-execution` description into its body, so compressing it deleted no
  fact. `tests/test_skill_descriptions.py` holds the ceiling.

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
