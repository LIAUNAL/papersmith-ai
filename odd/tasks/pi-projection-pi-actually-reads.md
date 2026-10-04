# The Pi projection becomes a surface Pi actually reads

Branch: `feat/pi-portability`. Closes three of the four gaps left open by
`odd/tasks/pi-offpath-push-tripwire.md` (its "observation carried forward" and
its out-of-scope list). Item 4 of that batch is a documentation boundary and is
tracked separately below.

## Why

The `pi` runtime generator produced a file Pi does not read, and a skill tree Pi
could not discover. Both were verified against Pi's own runtime, not its prose:

- `dist/core/resource-loader.js:33-47` — Pi's context-file candidates are
  `AGENTS.override.md`, `AGENTS.md`, `AGENTS.MD`, `CLAUDE.md`, `CLAUDE.MD`, and
  the function returns the **first** match. `PI.md` is in none of them. In a
  generated workspace Pi therefore read `CLAUDE.md` — routing it to
  `.claude/skills` and `.claude/commands/`, both wrong for Pi.
- `dist/core/resource-loader.js:633` — Pi discovers project skills at
  `<cwd>/.pi/skills`, which `papersmith init` never creates;
  `scripts/setup-harnesses.sh` builds it only when a human runs it.
- `dist/core/settings-manager.js:823` — `enableSkillCommands` defaults to `true`,
  so a loaded skill is already exposed as `/skill:<name>`. Generating
  `.pi/prompts/<skill>.md` would duplicate nine commands that exist natively.
- `dist/core/package-manager.js:714` — `projectBaseDir = join(cwd, ".pi")`, so a
  project settings entry resolves from `.pi/`; `"../skills"` reaches the
  canonical tree.

## Decisions (operator-approved)

1. **The Pi entrypoint is `.pi/APPEND_SYSTEM.md`, and `PI.md` disappears.** Pi
   appends it to the project system prompt (`resource-loader.js:825`). Chosen
   over `AGENTS.md` so Pi-specific routing does not leak into every other
   harness that reads a neutral name. It requires project trust, like every
   other `.pi/` resource.
2. **Discover skills through `.pi/settings.json`, seeded once and preserved.**
   `{"skills": ["../skills"]}` needs no symlink, so Pi stops depending on the
   one mechanism this repository never made portable: `ln -sfn` is already
   degraded on Windows and nothing tests it. It follows the existing precedent
   exactly — `init._write_workspace_seed` writes `papersmith.yaml` and
   `package.json` once and `PRESERVE_PATTERNS` keeps `upgrade` from clobbering
   operator edits.
3. **No `.pi/prompts` are generated.** Pi exposes `/skill:<name>` natively once
   the skills load (decision 2). Nine generated wrappers around a command that
   already exists is duplication, and this repository states its position on
   that plainly: "This file does not duplicate guidance; it only routes to the
   canonical sources of truth so a single set of docs drives every harness."
   The gap was never "no prompts"; it was "no skills".
4. **`.pi/skills` leaves the harness link script.** With decision 2 in place,
   keeping the link would be a second mechanism for one job. The original
   justification here -- that Pi would warn nine times about a name collision --
   was **refuted by the runtime probe**: Pi dedupes skills by canonical path
   (`skills.js` `realPathSet`), so a stale `.pi/skills` symlink alongside the
   settings entry still produced the same 23 skills and the same two
   diagnostics. The link still goes, for the reason that survives: it is the one
   mechanism this repository never made portable and nothing tests on Windows,
   and the settings entry needs no symlink at all.

## Known trade-off, accepted and documented

`docs/configuration.md` states that for `SYSTEM.md` and `APPEND_SYSTEM.md` the
trusted project file **takes precedence** over the agent-directory file, and the
two are not combined. A workspace's `.pi/APPEND_SYSTEM.md` therefore suppresses
an operator's own `~/.pi/agent/APPEND_SYSTEM.md` inside that workspace. The
current operator has no such file, so nothing regresses here; it must be stated
in the template's own text rather than discovered later.

## Allowed edit surfaces

- src/papersmith/generators.py
- src/papersmith/core/init.py
- src/papersmith/core/manifest.py
- src/papersmith/bridges/audit.py
- src/papersmith/templates/pi.md.tpl
- src/papersmith/templates/pi-settings.json.tpl
- scripts/setup-harnesses.sh
- scripts/sync-repo-harness.py
- .gitignore
- .pi/APPEND_SYSTEM.md
- .pi/settings.json
- PI.md
- tests/test_papersmith_generators.py
- tests/test_papersmith_init.py
- tests/test_papersmith_upgrade.py
- tests/test_workspace_commands_e2e.py
- tests/test_workspace_agents_e2e.py
- tests/test_papersmith_executor.py
- tests/pi-extension.test.mjs
- README.md
- CHANGELOG.md
- openspec/project-context.md

## Tasks

Strict TDD is active (`openspec/config.yaml` → `strict_tdd: true`).

- [x] T1 — The Pi surface. RED first: assertions that a generated workspace
      carries `.pi/APPEND_SYSTEM.md` and `.pi/settings.json` and no `PI.md`, and
      that the settings entry preserves operator edits across `upgrade`. Then
      GREEN: the generator contract, the seed, `PRESERVE_PATTERNS`, the
      `_EXTRA_STATIC` surplus entry, the template rewrite, and every
      enumeration that named `PI.md`. Closed by `7dd5d2d`.
- [x] T2 — The link script drops `.pi/skills`, with the reason recorded where
      the next reader will look, and the projection test updated to match. It
      landed in the same commit as T1 because the two changes share
      `tests/test_workspace_commands_e2e.py` and the link removal is the direct
      consequence of the seed, not an independent decision.
- [x] T3 — Docs: README's harness table and projection paragraph,
      `openspec/project-context.md`, and the `## 0.5.0` CHANGELOG section
      extended to cover this (0.5.0 is not tagged, so it is the honest home for
      the change rather than a second bump). Closed by `cff38a4`.

## Corrections made while reviewing, and two the verification forced

All four are accuracy defects inside files this change already touched.

Found by the parent reviewing the writer's diff:

1. `pi.md.tpl` still opened with "This workspace is a deterministic projection
   of the `.claude/` SSOT", which its own body contradicts — the agent
   definitions come from `.claude/agents/` but the skills come from `skills/`.
   Reworded to say which tree feeds which. (The sibling `opencode.md.tpl`
   carries the same `.claude/` SSOT phrasing and was deliberately left alone:
   changing one of a pair is worse than leaving both, and changing both is a
   separate decision.)
2. The earlier `## 0.5.0` "Internal" bullet still called `.pi/skills` "the
   harness link", which the new bullet in the same section supersedes.
   Corrected.

Found by independent verification, fixed in `4948697`:

3. **The stated consequence was false.** Four places claimed a `.pi/skills` link
   alongside the settings entry would make Pi load every skill twice and warn
   nine times. A probe with a stale `../skills` symlink planted in a workspace
   returned the same 23 skills and the same two diagnostics: Pi dedupes skills
   by canonical path (`skills.js`, `realPathSet`). The link still goes — it is
   the one mechanism this repository never made portable and nothing tests on
   Windows — but the honest reason is "a second mechanism for one job".
4. **The repository's own entrypoint omitted the trade-off.** The root
   `.pi/APPEND_SYSTEM.md` said nothing about precedence while the generated
   template did, and the root file is the one Pi reads here. It now states it,
   which verification confirmed against `resource-loader.js:824-833` (a single
   return, never combined).

## Findings surfaced by the end-to-end probe, deliberately NOT fixed here

A `DefaultResourceLoader` probe against this checkout reports 23 discovered
skills (the nine forge skills plus the operator's own) and exactly two
diagnostics, both pre-existing content defects in shipped skills:

- `skills/paper-writing/SKILL.md` — description 1680 characters
- `skills/remote-execution/SKILL.md` — description 1814 characters

Pi's Agent Skills limit is 1024. Pi warns and still loads them; other harnesses
may enforce it. Not fixed here because `description` is the routing signal every
harness uses, so shortening it changes how those two skills are selected — a
behavioural decision about the forge's own skills, not a mechanical fix, and
outside this change's scope.

## Verification

- `node --test tests/pi-extension.test.mjs`
- `.venv/bin/python -m pytest tests/test_papersmith_generators.py tests/test_papersmith_init.py tests/test_papersmith_upgrade.py tests/test_workspace_commands_e2e.py tests/test_workspace_agents_e2e.py tests/test_papersmith_executor.py`
- `python3 scripts/sync-repo-harness.py --check`
- `npm test`

## Known environmental failures

npm run test:all

The line above fails at base too: its `test:py` leg is
`.micromamba/envs/papersmith/bin/pytest` and `.micromamba/` does not exist in
this checkout. `.venv/bin/python -m pytest` is the equivalent, and what CI runs.

## Evidence

- Commits: `7dd5d2d` (the projection: entrypoint, seed, link removal, tests),
  `cff38a4` (docs).
- Writer evidence: RED `6 failed` naming the missing `.pi/APPEND_SYSTEM.md` and
  `.pi/settings.json` before implementation; GREEN `142 passed` across seven
  focused modules; conditional seed proven in both directions; upgrade
  preservation proven byte-for-byte and absent from `changed_files`.
- Parent end-to-end probe, through Pi's own loader rather than a test:
  `getSkills()` returns 23 skills including all nine forge skills, and
  `getAppendSystemPromptSources()` returns exactly this checkout's
  `.pi/APPEND_SYSTEM.md` — so both new surfaces are read at runtime, not merely
  present on disk.
- The gitignored kit snapshot (`src/papersmith/_kit`) was rebuilt
  (`python3 scripts/build-kit.py`) after the script change: `setup-harnesses.sh`
  there still carried the removed `.pi/skills` entry, which would have shipped a
  stale link script in an installed distribution.
- Independent verification (`4948697` is the fix commit it produced): 8 of 8
  claims held except the precedence one, falsified only for the repository copy
  and now fixed. `node --test tests/pi-extension.test.mjs` 10 pass; `npm test`
  663 pass / 0 fail; `.venv/bin/python -m pytest` `5 failed, 5181 passed, 8
  skipped` with the 5 being exactly the pre-existing `GateInterpreterTests`;
  `sync-repo-harness.py --check` clean (20 files). It independently reproduced
  the loader probe: 23 skills from this checkout and from a fresh `/tmp`
  workspace with no `.pi/skills`, this checkout's append as the single system
  prompt source, the conditional seed in both directions, and an
  operator-edited `.pi/settings.json` surviving `upgrade` byte-for-byte
  (sha256 identical, absent from `changed_files`). It also confirmed no
  pre-existing assertion was weakened: every removed line in `tests/` was a
  `PI.md` enumeration or the `.pi/skills` link entry, each replaced.

## Residual limitations
- `upgrade` does not seed `.pi/settings.json` into a workspace created before
  this change. Only `init` seeds it, and `PRESERVE_PATTERNS` only guarantees
  that a later `upgrade` leaves it alone. An existing workspace with `pi`
  declared therefore needs the file written once by hand, or a re-init. `init`
  was the surface this task named, so upgrade seeding is left as a separate
  decision rather than smuggled in.
