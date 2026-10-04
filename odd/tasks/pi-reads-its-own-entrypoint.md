# Pi reads its own entrypoint, and the two descriptions fit the budget

Branch: `feat/pi-harness-verification`, off `a67d616`. Ports D1 and D2 of
`odd/tasks/pi-harness-verification.md` onto current `main`. D3 and D4 are
explicitly out of scope and stay open in that file.

## Why

Two defects verified against Pi's own runtime, not against this repository's
prose. Full evidence in `odd/tasks/pi-harness-verification.md`.

**D1 — `PI.md` is never read by Pi.** Pi's context-file candidates are exactly
`AGENTS.override.md`, `AGENTS.md`, `AGENTS.MD`, `CLAUDE.md`, `CLAUDE.MD`
(`dist/core/resource-loader.js:32-47`, first match wins), confirmed by the CLI's
own `--no-context-files, -nc  Disable AGENTS.md and CLAUDE.md discovery and
loading`. The end-to-end probe confirmed the consequence: Pi loaded
`~/.pi/agent/AGENTS.md` and this repository's `CLAUDE.md`, and never `PI.md`. A
Pi-only workspace received **one** context file — the operator's — while 7.1K of
routing documentation sat unread beside it.

Pi does read `.pi/APPEND_SYSTEM.md` (`dist/core/resource-loader.js:825`). That is
the entrypoint to use.

**D2 — Two shipped descriptions exceed the Agent Skills limit.** Pi's
`MAX_DESCRIPTION_LENGTH = 1024` (`dist/core/skills.js:11`); `paper-writing` ships
1680 characters and `remote-execution` 1814. Pi warns and still loads, so nothing
fails and no test notices. Any harness that enforces the spec rejects both.

## Reference material

The design is not new. `feat/pi-portability` implemented it and was deleted
without merge; the five commits survive as dangling objects and the relevant
diff is captured at:

    odd/reference/pi-portability-D1D2.patch

that is `git diff 69ec01c 13b1ef5` restricted to the D1/D2 paths. **Read it
first.** It is the reviewed design, including the reasons in its commit bodies.
The base moved from `69ec01c` (0.4.0) to `a67d616` (0.5.1 + 5), so it is a
re-application, not a cherry-pick.

## Design, and why each part is there

1. **`.pi/APPEND_SYSTEM.md` replaces `PI.md`.** `pi.md.tpl` keeps its filename
   and becomes the template for the new path; `PI.md` leaves the tree, the
   generator, and every enumeration that named it. `render_files` maps
   `"pi": (".pi/APPEND_SYSTEM.md", "pi.md.tpl")`.
2. **`.pi/settings.json` replaces the `.pi/skills` symlink.** Its content is
   `{"skills": ["../skills"]}`; Pi's project settings resolve from the `<cwd>/.pi`
   base directory, so the entry reaches the canonical tree with no symlink. This
   is the real reason to prefer it, and it is stronger than the portability
   argument recorded in the old branch: with the symlink a clone discovers no
   skills until a human runs the setup script — the verification had to create
   the link by hand to see any — while a versioned settings file needs no step.
3. **Seeded, not rendered.** `.pi/settings.json` is operator-editable, so it is
   written once and then owned: `generators.SEED_OUTPUTS` plus
   `generators.seed_missing()` write it only into its absence, never overwrite,
   and never baseline it. `init._write_workspace_seed` seeds it at creation;
   `upgrade` calls `seed_missing` so a workspace that predates the file receives
   it. `manifest.PRESERVE_PATTERNS` gains `.pi/settings.json` so `upgrade` cannot
   clobber an operator's edit afterwards.
4. **`bridges/audit.py` gains `_EXTRA_STATIC["pi"] = (".pi/settings.json",)`**, so
   a workspace that later stops declaring `pi` still has its leftover reported as
   surplus rather than silently ignored.
5. **`.pi/skills` leaves `HARNESSES`** in `scripts/setup-harnesses.sh`, with the
   reason recorded in the script's own header where the next reader looks.
6. **D2 keeps every trigger.** The rewrite compresses what the `SKILL.md` body
   already states; it does not drop routing signal. `description` is the routing
   signal every harness uses, so this is a behavioural edit, not a formatting
   one. `description`'s first sentence is also what `derive_command_description`
   takes for the generated `/skill` and slash-command descriptions.

## The trap: `a67d616` contradicts this design

`tests/test_harness_parity.py` was added by `a67d616`, **after** the old branch
was written. It derives its roster from the script's `HARNESSES` array and
asserts `len(found) >= 4` and `"Pi" in labels`. Removing `.pi/skills` from that
array makes both assertions fail — `len` becomes 3.

That guard is not wrong, it is answering the old question. Its premise is "Pi is
a harness served by a link"; the design says "Pi is a harness served by a settings
entry". The guard must be rewritten to its real invariant: **every harness the
setup script serves has its generated link ignored and its directory carried by a
committed file** — and Pi, no longer in that roster, is instead covered by the
assertion that its discovery path needs no generated link at all. Do not delete
the guard and do not weaken it to a passing shape; move it to the invariant that
still holds.

The same commit's `.pi/README.md` must be rewritten: it currently says the
directory looks empty because the link is generated, which stops being true.

## Allowed edit surfaces

- src/papersmith/generators.py
- src/papersmith/core/init.py
- src/papersmith/core/manifest.py
- src/papersmith/core/upgrade.py
- src/papersmith/bridges/audit.py
- src/papersmith/templates/pi.md.tpl
- src/papersmith/templates/pi-settings.json.tpl
- scripts/setup-harnesses.sh
- .gitignore
- .pi/APPEND_SYSTEM.md
- .pi/settings.json
- .pi/README.md
- PI.md
- skills/paper-writing/SKILL.md
- skills/remote-execution/SKILL.md
- tests/test_harness_parity.py
- tests/test_papersmith_generators.py
- tests/test_papersmith_init.py
- tests/test_papersmith_upgrade.py
- tests/test_papersmith_executor.py
- tests/test_workspace_agents_e2e.py
- tests/test_workspace_commands_e2e.py
- tests/test_skill_descriptions.py
- README.md
- CHANGELOG.md
- openspec/project-context.md

## Explicitly out of scope

The old branch bundled a fourth feature, a Pi extension refusing off-path pushes
(`pi-extension.ts.tpl`, `.pi/extensions/refuse-offpath-push.ts`,
`tests/pi-extension.test.mjs`, and the `scripts/sync-repo-harness.py` projection
that carries it). **Do not port it.** `generators.TOOL_OUTPUTS["pi"]` therefore
becomes `(".pi/APPEND_SYSTEM.md", ".pi/gentle-ai/persona.json")` — without the
extensions path the reference diff shows. `scripts/sync-repo-harness.py` is not
edited at all. `src/papersmith/__init__.py` is not bumped: `main` is already at
0.5.1 and the reference's bump predates it.

Also out of scope: D3 (`gitignore.tpl` does not ignore the four links) and D4
(the parity guard cannot see it).

## Tasks

Strict TDD is active (`openspec/config.yaml` → `strict_tdd: true`). Write the
failing assertion first, watch it fail for the stated reason, then make it pass.

- [x] **T1 — D1: the entrypoint.** RED: a generated workspace carries
      `.pi/APPEND_SYSTEM.md` and `.pi/settings.json`, carries no `PI.md`, and
      `upgrade` seeds the settings file into a workspace that predates it without
      touching an existing one. GREEN: the generator mapping, the templates, the
      `SEED_OUTPUTS`/`seed_missing` pair, the `init` seed, the
      `PRESERVE_PATTERNS` entry, and the `_EXTRA_STATIC` surplus entry.
- [x] **T2 — D1: the repository's own surface.** `.pi/APPEND_SYSTEM.md` and
      `.pi/settings.json` are added, `PI.md` is deleted, `.gitignore`'s `.pi`
      block is corrected, `scripts/setup-harnesses.sh` drops `.pi/skills` with
      its reason, and `tests/test_harness_parity.py` is moved to the invariant
      that survives.
- [x] **T3 — D1: docs.** `.pi/README.md`, `README.md`'s harness table and
      projection paragraph, `openspec/project-context.md`, and a CHANGELOG
      entry. These are the files whose text asserts what Pi reads, and the old
      text asserts the opposite of what ships.
- [x] **T4 — D2: the budget.** RED: a test that every shipped skill's
      `description` fits 1024 characters and that the routing triggers of the two
      rewritten skills are all still present. GREEN: the two `description`
      rewrites, keeping every trigger and dropping only what the body restates.
- [x] **T5 — Close.** See *Results* below: every check reported as passed,
      failed, or skipped, and the five failures are environmental and named.

## Verification

    .venv/bin/python -m pytest tests/ -q
    DELIBERATION_DOMAIN_PROFILE=$PWD/skills/proposal-deliberation/profile.ts node --test "tests/**/*.mjs"

`npm run test:py` and therefore `npm run test:all` are **broken in this
checkout**: `package.json` invokes `.micromamba/envs/papersmith/bin/pytest` and
there is no `.micromamba` directory. Use the `.venv` runner above and report the
discrepancy rather than silently substituting.

Baseline before any edit, measured: 653 Node tests pass, 0 fail; the Python
suites named above pass. Any regression is the change's.

End-to-end confirmation of D1, and the one place this file's first draft was
wrong about its own subject.

The original probe asked `loadProjectContextFiles` to print `.pi/APPEND_SYSTEM.md`.
It cannot, and never could: `loadContextFileFromDir` iterates exactly
`AGENTS.override.md`, `AGENTS.md`, `AGENTS.MD`, `CLAUDE.md`, `CLAUDE.MD`, which is
**why D1 exists at all**. A file Pi appends to the system prompt is not a context
file; asking the context-file API about it returns the same two paths before and
after the change, so the first draft's probe would have reported a correct fix as
a failure. The runtime reaches the file through a separate private path,
`discoverAppendSystemPromptFile()`, and exposes it here:

    node -e "import('/Users/andresalvarez/.npm-global/lib/node_modules/@earendil-works/pi-coding-agent/dist/index.js').then(async m => { const cwd = process.cwd(); const agentDir = m.getAgentDir(); const l = new m.DefaultResourceLoader({cwd, agentDir}); await l.reload(); console.log('context:', m.loadProjectContextFiles({cwd, agentDir}).map(c => c.path)); console.log('append:', l.getAppendSystemPromptSources()); })"

## Results

Measured on the uncommitted working tree, `feat/pi-harness-verification`, by an
independent read-only verifier and reproduced where noted.

| Check | Result |
| --- | --- |
| Node suite (`node --test "tests/**/*.mjs"`) | **pass** — `653` tests, `0` fail, `0` skipped, matching the baseline exactly |
| `tests/test_skill_descriptions.py` | **pass** — 5 tests, 40 subtests |
| `tests/test_harness_parity.py` | **pass** — 4 tests, including `test_pi_is_discovered_without_a_generated_link` |
| D2 lengths, measured in UTF-16 code units | **pass** — `paper-writing` 1015 (was 1680), `remote-execution` 923 (was 1814); every `description` still opens `Trigger: ` |
| D1 runtime, append-source probe | **pass** — `append: [{path: <repo>/.pi/APPEND_SYSTEM.md}]`; the project file wins, the operator's global file is not combined |
| D1 runtime, context-file probe | **pass, and unchanged by design** — `context: [~/.pi/agent/AGENTS.md, <repo>/CLAUDE.md]` before and after |
| Python suite (`.venv/bin/python -m pytest tests/ -q`) | **failed, environmental** — `5 failed, 5290 passed, 8 skipped` in 717s |
| `npm run test:py` / `npm run test:all` | **skipped** — point at `.micromamba/envs/papersmith/bin/pytest`, which does not exist |

The five failures are all in `tests/test_forge_gate.py::GateInterpreterTests` and
all report one fact: the gate names `.micromamba/envs/papersmith/bin/pytest` and
no file is there. They are **not** the change's. The failing assertion's entire
input set is `package.json`'s `test:py` script, `scripts/setup_env.py`'s
`MAMBA_ROOT`/`ENV_NAME`, and `tests/test_forge_gate.py` itself — and `git diff`
is empty for all three. The same missing directory is what breaks
`npm run test:py`, which this file already recorded as broken before any edit.
Provisioning the environment (`npm run setup`) is what closes them, not a change
to this port.

Still open, deliberately: D3 and D4 in `pi-harness-verification.md`. Nothing here
touches `gitignore.tpl` or the guard's blind spot.
