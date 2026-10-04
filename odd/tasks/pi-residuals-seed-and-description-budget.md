# The two residuals of the Pi projection: the seed and the budget

Branch: `feat/pi-portability`, off `4948697`. Closes the two open items recorded
in `odd/tasks/pi-projection-pi-actually-reads.md` ("Residual limitations") and in
the predecessor's out-of-scope list. No merge: the operator keeps `main` at
`69ec01c`.

## Why

Both items are the same shape of defect: a surface that works in a workspace
`init` creates today, and does not in a workspace that predates the change.

1. **`upgrade` cannot seed `.pi/settings.json`.** `init._write_workspace_seed`
   writes it only when the workspace declares `pi` (`init.py:145-154`), and
   `manifest.PRESERVE_PATTERNS` then protects it (`manifest.py:62-76`). A
   workspace created before that commit therefore has no Pi skill discovery at
   all, and `upgrade` — the command whose entire job is to synchronize framework
   files — reports nothing to do. The file is not a kit file and not a rendered
   projection, so no existing path in `upgrade` can reach it.

2. **Two skill descriptions exceed the Agent Skills description budget.** Pi's
   `dist/core/skills.js:11` is `MAX_DESCRIPTION_LENGTH = 1024`, and
   `validateDescription` (`skills.js:80-87`) rejects anything longer as a spec
   violation; Pi warns and still loads, other harnesses may enforce. Measured
   over the nine shipped skills, exactly two exceed it — `remote-execution`
   1814, `paper-writing` 1680 — and the next longest is 624, so the ceiling is
   not tight for the other seven.

   The budget matters twice over, because `generators.derive_command_description`
   (`generators.py:123-137`) takes the **first sentence** of the description as
   the slash command's own `description:` in `.claude/commands/*.md` and
   `.opencode/commands/*.md`. `paper-writing`'s first sentence is 1233
   characters, so the defect also lands in the command menu of two other
   harnesses.

## Decisions

1. **Seeding is a third category, and it is not "preserved".**
   `PRESERVE_PATTERNS` answers "never overwrite or delete"; it is silent on
   "absent because the workspace predates me". The seed table answers the second
   question without weakening the first: a declared-tool seed is written only
   when the path is **absent**, is never overwritten, and never enters the
   manifest baseline — `manifest.synchronized_paths` excludes preserved paths on
   purpose (`manifest.py:301-306`), and baselining an operator-editable file
   would report drift that no `upgrade` can clear.

2. **The gate is the declared tool set**, not "the template exists". A workspace
   that does not declare `pi` must not receive `.pi/settings.json`, the same way
   `init` does not write it (`tests/test_papersmith_init.py:140`).

3. **Descriptions keep every trigger and lose only what the body already says.**
   The rule for the rewrite is mechanical and reviewable: every claim removed
   from `description` must already be stated in the same `SKILL.md` body. The
   verb inventories, the `kagglesdk` pin, `CredentialHandle`, the `latexmk`
   detail and the OpenAlex/Crossref/arXiv targets are all in the body already —
   the description was restating them. Facts that live **only** in the
   description (`Stdlib-only`, `keyless`, `fail-closed`, `Offline`) stay, in
   compressed form.

4. **Sentence one is the command description.** Because
   `derive_command_description` keeps the first sentence, the compressed trigger
   inventory is placed as sentence one, and the constraints as sentence two:
   sentence two is read by a skill router and harmlessly ignored by a command
   menu.

5. **The budget gets a test, not a lint.** A regression guard for the spec limit
   belongs in the suite (T4), so the next description that grows past 1024 fails
   a test instead of a warning nobody reads.

## Tasks

- [x] T1 — RED first: a test proving an upgrade of a workspace whose
      `.pi/settings.json` was deleted recreates it when `pi` is declared and
      leaves it absent when it is not, plus the untouched-when-present case.
      Four failures before the implementation, naming the missing behaviour.
- [x] T2 — The seeding mechanism: `generators.SEED_OUTPUTS` beside
      `TOOL_OUTPUTS`, `generators.seed_missing`, its consumption in `upgrade`,
      and `seeded_files` / `unseeded_files` in the returned summary.
- [x] T3 — The two descriptions rewritten to fit the budget, with every dropped
      claim verified present in the body (see "What moved, and where it lives").
- [x] T4 — `tests/test_skill_descriptions.py`: the budget, the name/directory
      agreement, the one-line frontmatter shape and the trigger convention, over
      every shipped skill.
- [x] T5 — Kit rebuild, CHANGELOG `0.5.0`, README (Pi paragraph + feature list),
      and the two comments that described the old mechanism.
- [x] T6 — Checks: focused modules, full pytest, `npm test`,
      `sync-repo-harness.py --check`, plus independent verification of every
      claim above.

## What moved, and where it lives

The description rewrite follows one mechanical rule: a claim leaves a
`description` only if the same file's body already states it. Verified clause by
clause against the pre-change text:

| Left the description | Body home |
| --- | --- |
| `(ids, requirements, writing order)` | lines 53-55 (ids, requirements, placement), 64/207/274 (writing order) |
| `empty`, `two structural decisions inferred off disk` | 18, 337, 1056 |
| verb inventories (24 and 13 verbs) | paper-writing 16-40; remote-execution `## The commands` |
| `from cached resolved metadata` | 679-681, verbatim |
| `before it ever reaches main.tex` | 1036-1037, verbatim |
| `Offline except resolve/render (latexmk)` | 57-62 (`## Environment`-style boundary), 1086/1304 |
| `submit`'s by-path rule, `kaggle-accounts list --json`, Basic-auth | remote-execution 511-513, 560-566 |
| worker identity, capacity clamp, `KAGGLE_API_TOKEN` mechanics | 512, 521, 553-557 |

Claims with no other home were **kept**, compressed: `Stdlib-only`, `keyless`,
`fail-closed` (no body statement), the capacity clamp and worker auto-selection
(no literal body statement), the pinned `kagglesdk` client and the
`CredentialHandle` shape. `remote-execution` keeps the phrases its own doctrine
pin asserts on (`kaggle_driver.py`, `kagglesdk`) and avoids all four retired
phrases that test bans.

Measured after the rewrite: `remote-execution` 923, `paper-writing` 1015 (of
1024), next longest 624. The derived command description for `paper-writing`
drops from 1233 to 961 characters, because sentence one is now the compressed
trigger inventory and the constraints are sentence two.

## Accepted trade-off

An operator who deletes `.pi/settings.json` on purpose gets it back on the next
`upgrade`. The escape hatch is the declared tool set — removing `pi` also makes
`audit` report the leftover `.pi/` surface as surplus — and it is stated in the
CHANGELOG rather than left to be discovered.

## Verification

- `.venv/bin/python -m pytest tests/test_skill_descriptions.py tests/test_papersmith_upgrade.py tests/test_papersmith_init.py tests/test_papersmith_generators.py tests/test_workspace_skills_e2e.py`
- `.venv/bin/python -m pytest`
- `npm test`
- `python3 scripts/sync-repo-harness.py --check`
- `python3 scripts/build-kit.py` after the `skills/` edit

## Known environmental failures

`npm run test:all`'s `test:py` leg is `.micromamba/envs/papersmith/bin/pytest`
and `.micromamba/` does not exist in this checkout; `.venv/bin/python -m pytest`
is the equivalent and what CI runs. Five `GateInterpreterTests` failures are
pre-existing and environmental, at base too.

## Evidence

- Commits: `e34d8c7` (the seed), `be84434` (the two descriptions plus the four
  regenerated command projections), `ce81d38` (changelog, README, the two
  corrected comments). Nothing pushed and nothing merged; the branch is three
  commits past the pushed tip `4948697`.
- RED, observed before the implementation: four failures in
  `tests/test_papersmith_upgrade.py`, one of them
  `AssertionError: the workspace still cannot discover Pi skills`.
- GREEN, focused: `tests/test_papersmith_upgrade.py` + init + generators + kit
  65 passed; `tests/test_skill_descriptions.py` 5 passed / 36 subtests;
  `tests/test_remote_execution.py -k DoctrinePin` 14 passed;
  `tests/test_papersmith_generators.py` + `test_workspace_skills_e2e.py` +
  `test_skill_audit.py` 425 passed / 3 skipped / 1303 subtests.
- `npm test`: 663 pass, 0 fail.
- End-to-end probe through the real CLI, not the module: a scratch workspace
  created with `tools=("claude", "pi")` had `.pi/settings.json` deleted, then
  `.venv/bin/python -m papersmith.cli upgrade` printed
  `Framework version: 0.5.0; changed files: 1` and
  `Seeded '.pi/settings.json' (absent, and the workspace declares its runtime)`;
  the file came back as `{"skills": ["../skills"]}` and the manifest did not
  list it.
- The new guard was proven to fail rather than merely to pass: padding a
  description to 1800 reported `description is 1800 UTF-16 code units, 776 over
  the 1024 the Agent Skills spec allows`; the mutated file was restored from git
  and `git status` shows only the intended paths.
- Kit rebuilt after the `skills/` edit (`python3 scripts/build-kit.py`, 219
  files, version 0.5.0) and both rewritten `SKILL.md` files verified byte-equal
  to the canonical tree.
- `python3 scripts/sync-repo-harness.py --check`: clean, 20 files.

## Independent verification

A `gentle-ai-verify` task with no part in the implementation ran the suites and
re-derived every claim from the code, from the files, and from its own scratch
probes (nothing taken on trust, no repository mutation, `git status --porcelain`
empty before and after). Verified at `ce81d38`:

| Claim | Result |
| --- | --- |
| A — seeding gated on declared tools, absent-only | verified (`upgrade.py:186,214`, `generators.py:47-49,343-346`, plus a behavioural probe) |
| B — never baselined, operator edit survives | verified, mechanism and probe |
| C — `seeded_files`/`unseeded_files` and the CLI line | verified through the installed console script; a second run reports 0 changes |
| D — every description within 1024 UTF-16 units | verified by its own computation over all nine; 0 over |
| E — no claim left the descriptions without a body home | verified clause by clause, **with one exception** (below) |
| F — the budget test is not vacuous | verified in a scratch copy only: 1136 units reported `1136 not less than or equal to 1024`; a control run passed |
| G — projections carry the derived first sentence | verified byte-equal for all four; `sync --check` clean at 20 files |

Commands: `tests/test_papersmith_upgrade.py` + `tests/test_skill_descriptions.py`
26 passed; `tests/test_remote_execution.py` 789 passed / 1 skipped / 0 failed;
`npm test` 663/0; full `.venv/bin/python -m pytest` `5 failed, 5190 passed, 8
skipped` where the five are exactly the pre-existing `GateInterpreterTests`
(established from the test and the unchanged `package.json`, not by checking
out the base).

### The one exception, and its fix

The provenance date "a standalone distribution since 2025-07-11" left the
`remote-execution` description and the body only said "a STANDALONE
distribution, not vendored inside the `kaggle` CLI" — so the date survived in
`requirements.txt` and nowhere in that skill. The verification flagged it as the
single removed claim with no body occurrence, which is precisely the rule this
change committed to. Fixed in `b3994db` by restoring the date beside the pin it
belongs to (body, `## Environment`), kit rebuilt.

### What the last two commits changed

`b3994db` and `13b1ef5` (the restored date, plus two tests the suite lacked:
seeding when `pi` is added through `--tools`, and a dangling symlink at the seed
path) touch no production file. Proven rather than asserted:
`git diff ce81d38..HEAD -- src/` is empty, so `src/` is byte-identical to the
state the verification covered.
