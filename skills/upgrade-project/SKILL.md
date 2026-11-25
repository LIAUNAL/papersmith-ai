---
name: upgrade-project
description: "Trigger: a workspace created by `smith init` is running an older release and needs the current one — its skills, agents, slash commands, harness wiring and artifact shapes brought up to the installed distribution. Delegates every write to `smith upgrade`, which owns the kit copy, the projections, the orphan sweep and the artifact migrations; this skill never copies a file or edits an artifact itself. Refuses before writing when the directory is not a workspace or the CLI is unreachable, and names the one command that fixes each. Verbs: `plan` previews pending migrations and writes nothing; `apply` performs the upgrade; `status` reports the recorded version against the installed one."
---

# Upgrade Project

A workspace is not a checkout. `smith init` copies a release's skills,
renders its slash commands and agents for every harness, and records which
release the workspace received in `.papersmith/version`. Nothing about that is
live: when the installed distribution moves ahead, the workspace keeps the
release it was born with until someone upgrades it.

This skill is the in-workspace surface for that upgrade. It exists because the
work was only reachable from a terminal, which meant that an agent working
inside a workspace could see that the workspace was stale and could not do
anything about it.

## What this skill does not do

It performs no upgrade of its own. Every byte written is written by
`smith upgrade`, and that is deliberate: the upgrade is not a file copy.
It is a kit copy, a symlink repair, a re-derivation of every projection, an
orphan sweep over previously-baselined dynamic paths, and an ordered run of
artifact migrations — with the version marker written last, and only when the
artifacts actually reached that version.

A reimplementation here would be a second answer to all of that, and two
answers that can disagree are worse than one that can be wrong. So this skill
decides *whether* to call the CLI and *with which arguments*, and reports what
it said. Nothing else.

It also never decides to upgrade on its own. A stale workspace is a fact to
report; moving it is the user's call.

## Preflight, before anything is written

Two conditions are checked first, because both fail better before a write than
during one.

**Is this a workspace?** `.papersmith/manifest.json` must exist. The CLI checks
this too and refuses with exit 1, but checking here lets the refusal name the
directory the user is actually in.

```
test -f .papersmith/manifest.json
```

Absent, refuse and say so plainly: this directory was not created by
`smith init`, and `smith init .` is what creates one. Do not offer to
run `init` as a recovery — initializing a directory somebody believed was
already a workspace is how a misunderstanding becomes a tree of files.

**Is the CLI reachable?** The workspace vendors no copy of the `papersmith`
package, so the upgrade can only come from the installed distribution.

```
smith --version
```

If that fails, try `python -m papersmith.cli --version`, which works whenever
the distribution is importable even if no console script landed on `PATH`.

Note the module path: it is `papersmith.cli`, not `papersmith`. The package
ships no `__main__.py`, so `python -m papersmith` fails with "'papersmith' is a
package and cannot be directly executed" — a message that looks like a broken
install and is not one. The entry point is `papersmith.cli:main`.

If neither answers, refuse with the installation command rather than a guess:

```
pipx install git+https://github.com/LIAUNAL/papersmith-ai.git
```

A workspace cannot upgrade itself from inside; saying that clearly is more
useful than attempting a fallback that cannot exist.

## The verbs

### `plan` — what would a migration do

```
smith upgrade . --plan-migrations
```

Reports the migrations that would run and exits having written nothing.

Be precise about what this previews, because the flag is deliberately not
called `--dry-run`: it covers **migrations only**. The kit copy, the
projections and the orphan sweep are not previewed by it and have no preview at
all. Telling a user "this is a dry run" would be false.

### `apply` — perform the upgrade

```
smith upgrade .
```

Copies the current kit, repairs the per-harness `skills` links, rewrites
`.papersmith/config.json`, re-renders every projection, sweeps orphans, runs
the pending migrations, and writes `.papersmith/version` last.

Flags worth knowing, with what each actually changes:

- `--tools <a,b,c>` — replace the workspace's `active_tools`. Omitted, the
  declared set is kept. This is how a workspace gains or drops a harness.
- `--force` — write kit files whose hashes already match. Normally a matching
  hash is skipped; this is for a workspace whose files were edited in place.
- `--no-migrate` — sync files, skip artifact migrations. The version marker
  then stays where it was, which is correct rather than unfortunate: the
  artifacts did not reach the new version, so the workspace must not claim they
  did.
- `--allow-downgrade` — install an older kit over a newer workspace. Deliberately
  separate from `--force`. Never add it to recover from a refusal without
  saying what it does first; a refusal here is usually a sign that the wrong
  distribution is installed.
- `--allow-dirty-kit` — upgrade even though the kit source carries uncommitted
  changes under its shipped paths, or its git state cannot be determined.
  Without it the CLI refuses before writing anything (exit 1), because a
  workspace built from uncommitted kit edits carries bytes no commit names.
  The usual cause is an editable install whose checkout has local edits. Never
  add the flag to get past the refusal without telling the user what it
  records: the workspace's kit-source record then says `allowedDirty: true`.

### `status` — how far behind is this workspace

```
smith status
```

Reports the recorded version against the installed one. Prefer this over
reading `.papersmith/version` directly: the marker is a claim about artifacts,
and `status` is where that claim is interpreted.

It also reports which framework build the workspace came from, on the
`Kit source:` line: version, commit, whether the kit was dirty, and whether it
was a checkout, the bundled kit or a `PAPERSMITH_KIT_ROOT` override. Every
`init` and `upgrade` writes this to `.papersmith/kit-source.json`. A workspace
created before 0.14.0 reads `unknown (recorded before 0.14.0)` until its next
upgrade writes the record; no migration is involved.

## Which workspaces can be upgraded

Say this plainly when a user asks whether their workspace is too old, and
never suggest re-initializing a live workspace instead: `smith init` in a
fresh directory leaves behind every ledger, receipt, seal, managed revision and
lock the paper accumulated.

- Workspaces recorded at **0.12.0 or later** are supported. From 0.14.0 on,
  every release that changes the shape of something a workspace already holds
  ships a migration (or a compatibility read that keeps the old shape working)
  in the same release, so `upgrade` is always the path forward.
- An **older** workspace still upgrades: files are synchronized and the
  convergence migrations run. Shape changes released before 0.12.0 shipped no
  migration, so leftovers can remain (0.8.0's `.antigravity/` files are not
  removed).
- A workspace with **no recorded version** upgrades too, but version-gated
  migrations are reported `undetermined` and never applied.
- A recorded version that is **unorderable** (`nightly`) or **newer than the
  installed kit** refuses; `--allow-downgrade` is the override, and a refusal
  here usually means the wrong distribution is installed.

The maintainer side of this policy lives in `docs/releasing.md`, section
"Workspace support policy".

## What is never overwritten

The upgrade preserves the user's own work by pattern, not by hope. The
protected set covers the directories that hold authored research output and
the files that carry a workspace's own configuration and identity, including
its environment files.

Read the set from `PRESERVE_PATTERNS` in `src/papersmith/core/manifest.py`
rather than from a list restated here. A roster copied into prose is a roster
that drifts the first time the real one changes, and the question a user asks
-- "will this overwrite my work?" -- deserves the current answer, not the
answer that was current when this file was written.

State that when asked whether an upgrade is safe, and state its limit honestly:
there is **no backup and no dry run for files**. A file outside those patterns
that was edited by hand will be replaced by the release's own copy. If a user
has such edits, the answer is to commit them first — a working tree under
version control is the backup the CLI does not provide.

### `.gitignore`: the framework owns one block, not the file

`.gitignore` is the one rendered file a workspace is expected to edit, so the
framework writes its lines between two marker lines (`# >>> papersmith managed
block: ...` and `# <<< papersmith managed block ends: ...`). `upgrade`
re-renders that block and keeps every line outside it, above or below, byte
for byte. `status` and `audit --check-drift` compare only the block, so a line
the workspace added is not drift. The marker text and the merge rules live in
`MANAGED_BLOCK_BEGIN`, `MANAGED_BLOCK_END` and `merge_managed` in
`src/papersmith/generators.py`.

A file with no block yet (every workspace created before 0.14.0) is converted
on its next upgrade: replaced whole when it is byte-identical to what the
framework last wrote, and otherwise given the block, with every line the block
does not already carry kept below it in order. Markers that are malformed (a
lone marker, a repeated one, or the two in the wrong order) are never guessed
at: the file is left as it is, the report lists it under **unsynchronized**,
and it stays drift until the markers are repaired. Edit outside the block, not
inside it: a line added inside the block is replaced on the next upgrade.

### The paper line is kept

`upgrade` never changes a workspace's line. It reads `paper_kind` from
`.papersmith/config.json` (absent means `experimental`) and keeps it, and the
kit it copies is filtered for that line (`manifest.kit_layout`): files only
another line receives (its section contracts, its line skill, its folders) are
never copied in, and a non-experimental line's contracts are served at
`sections/`. A section contract the workspace edited is kept and reported as
`Kept edited contract: <path>`; `smith upgrade --force` replaces it with the
kit's. Moving a workspace to another line is not an upgrade: it is
`smith kind set <type> --by <name>` after `/paper-type` has scored the idea
(see `docs/cli.md`), which records the agreement and then runs the upgrade for
the new line.

## Reading the result

The report names the workspace, the version, the count of changed files, and
then four things that are warnings rather than failures:

- **unsynchronized** — a kit file could not be written. The upgrade continued.
- **stranded** — an orphan could not be deleted. It is still there.
- **link warnings** — a harness `skills` symlink was blocked.
- **"recorded version stays at X"** — the marker did not advance, because the
  artifacts did not reach the new version. With `--no-migrate` this is
  expected; without it, read the migration lines above it, because something
  failed.

Exit codes: `0` success; `1` a user error (not a workspace, corrupt manifest or
ledger, refused downgrade, refused dirty or unknown kit source, unknown tool
name); `2` a source error (the installed
distribution carries no kit); `4` a migration failed.

Report a non-zero exit as a failure with its message. An upgrade that printed a
migration failure and exited 4 did not succeed, and a summary that calls it done
is the one outcome this skill must never produce.
