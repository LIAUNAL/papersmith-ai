# Test fixtures

Most directories here are small hand-written inputs named after the test that
reads them. One is different and is documented here because it is generated.

## `workspace_v0_13_0/`: a populated 0.13.0 workspace

What `smith upgrade` has to carry forward is a workspace that a real
release produced, so this one was produced by the 0.13.0 release itself.
`scripts/build-v0_13_0-fixture.py` extracts `git archive 55dcb4e` (the commit
whose `src/papersmith/__init__.py` reads `0.13.0`; that release has no tag)
into a scratch directory and drives that tree's own CLI and engines:
`papersmith init --no-env --no-npm`, a proposal v1 and one successor, an
experiments v1, and one implementation target with its scaffold receipt and
seal file, both implementation skills' declared holders (`AGREED.md`,
`Experimental_AGREED.md`) with settled items, and their position ledger. The
content is generic, nothing paper-specific.

**Why a committed snapshot rather than building it at test time.** Building
needs git history (`git archive 55dcb4e`) and the repository's
`node_modules`, and takes seconds. A snapshot makes the test deterministic
and independent of both. Rebuilding is only for when the fixture has to hold
something new.

**What is stored.**

- `workspace.tar.gz`: the workspace minus the framework files that `init`
  copied or rendered and nothing touched since. Those are the paths the
  workspace's own `.papersmith/manifest.json` records whose bytes still match
  the recorded hash, about 8 MB of skill tree and projections. `upgrade`
  writes every one of them again whether the old bytes are there or not, so
  leaving them out does not change what an upgrade produces.
  `.papersmith/version` and `.gitignore` are always kept: the first is the
  marker the upgrade reads, and the second is the one rendered file a user
  is expected to edit, so its 0.13.0 bytes are part of what is tested.
  Everything the workspace made itself is kept byte for byte, including the
  target's own `.git`, because the engine refuses a target that is not a git
  repository.
- `contents.sha256`: every member and its digest, in `sha256sum` format, so a
  review can read what changed. The test checks that the archive matches it.

The archive is deterministic for a given tree (sorted members, zeroed owners
and mtimes, no gzip timestamp). It is an archive and not loose files because
the workspace carries its own `.gitignore`, and this repository's git would
apply it and drop most of the content.

**Rebuilding.**

```
.micromamba/envs/papersmith/bin/python scripts/build-v0_13_0-fixture.py
```

It needs `node_modules` (`npm ci`). A rebuild produces different bytes: the
engines stamp wall-clock times into receipts, state and ledger events, and
other records hash those, so nothing here strips or rewrites them. Treat a
rebuild as a new snapshot and commit both files together.

**Reader.** `tests/test_upgrade_v0_13_0_workspace.py` extracts the archive,
records the digest of every member, runs today's `upgrade`, and asserts that
only the files listed in its `INTENDED_CHANGES` moved, that every registered
migration applied or was already satisfied, that `audit --check-drift` is
clean, and that the deliberation consistency audit and implementation
`verify` still read what 0.13.0 wrote. A later release's migration that is
meant to change one of these files adds it to `INTENDED_CHANGES` with the
reason.
