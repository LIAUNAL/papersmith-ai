# Pi off-path push tripwire

Branch: `feat/pi-portability` (base `69ec01c` — `release: 0.4.0`)
Scope authorized by the operator: **only** the Pi safety tripwire. The other
three Pi gaps found during exploration (`inert PI.md`, missing `.pi/prompts`,
manual `.pi/skills` projection) were left open by that decision and are now
closed by `odd/tasks/pi-projection-pi-actually-reads.md`:

- the inert `PI.md` -> `.pi/APPEND_SYSTEM.md`, because Pi's context-file
  candidates never included `PI.md`;
- the missing `.pi/prompts` -> deliberately still absent, because
  `enableSkillCommands` defaults to true and Pi already exposes each loaded
  skill as `/skill:<name>`;
- the manual `.pi/skills` projection -> a seeded `.pi/settings.json` whose
  `"../skills"` entry reaches the canonical tree with no symlink, which also
  removes Pi's dependence on `ln -sfn` (never portable here, never tested on
  Windows).

## Why this exists

The forge ships a tripwire against a shape that already happened once: a
hand-rolled probe lost `mode=smoke` and ran a full-scale search on a metered
account. The predicate lives in exactly one place —
`skills/remote-execution/scripts/hooks/refuse_offpath_push.py` — and each
harness relays to it rather than re-implementing it.

Today only OpenCode relays. Claude Code has the contract the hook was written
for but no committed wiring (`settings.json` is gitignored). **Pi has nothing.**

## Gap evidence (verified, not assumed)

- OpenCode relay: `.opencode/plugins/refuse-offpath-push.js`, generated from
  `src/papersmith/templates/opencode-plugin.js.tpl`; registered in
  `generators.py` (`if tool == "opencode":`) and in
  `bridges/audit.py` `_EXTRA_STATIC`.
- Pi extension surface exists and can block: `pi.on("tool_call", handler)`
  returning `ToolCallEventResult` `{ block: true, reason }`
  (`dist/core/extensions/types.d.ts:887-896,1014`); Pi loads project
  extensions from `.pi/extensions/` after project trust
  (`docs/configuration.md` "Project `.pi` directory").
- Pi runtime contract that constrains the design: *"A `tool_call` handler
  failure blocks the tool as a fail-safe"* (`docs/extensions.md` §Errors and
  cleanup). So the relay **must never throw**, including while degrading.
  This is the deliberate divergence from the OpenCode plugin, which refuses by
  throwing.
- Pi's `ExtensionContext` exposes `cwd` and nothing like a project root
  (`types.d.ts:218`), so the relay resolves the workspace root by walking up
  from `ctx.cwd` to the hook path.
- Pi extension entry point must be the **default export**
  (`jiti.import(path, { default: true })`); a named export makes Pi reject the
  module and take every `pi` command down with it.

## Decisions

1. **Block, never throw.** Refusal returns `{ block: true, reason }`. The whole
   handler body is wrapped so an unexpected failure degrades loudly instead of
   blocking every bash command in the session.
2. **One authority.** The relay shells out to the Python hook with the same
   `{ tool_name: "Bash", tool_input: { command } }` payload OpenCode already
   sends. No predicate is copied into TypeScript.
3. **Degrade loudly, once per process, then allow.** Same policy and same
   capability probe as the OpenCode relay (load the hook, compare
   `_load_push_surfaces()` against every `PUSH_SURFACE` literal ast-parsed from
   the adapters), because a silently-off tripwire is worse than a noisy one.
4. **Repo projection mirrors OpenCode.** `.opencode/plugins/` is versioned while
   `.opencode/skills` is ignored; Pi gets the same split. Today `.gitignore`
   ignores `.pi/` wholesale, which would make a versioned extension impossible.
5. **Honest bound preserved.** Tripwire, never a gate. `python -c`, heredocs and
   script files defeat substring matching; the load-bearing precondition stays
   `_verify_launch_authorization()` inside `remote_cli.py`.

## Allowed edit surfaces

- `src/papersmith/templates/pi-extension.ts.tpl` (new)
- `src/papersmith/templates/pi.md.tpl`
- `src/papersmith/generators.py`
- `src/papersmith/bridges/audit.py`
- `scripts/sync-repo-harness.py`
- `.gitignore`
- `.pi/extensions/refuse-offpath-push.ts` (new, generated artifact)
- `tests/pi-extension.test.mjs` (new)
- `tests/test_papersmith_generators.py`
- `tests/test_papersmith_init.py`
- `tests/test_workspace_commands_e2e.py`
- `tests/test_workspace_agents_e2e.py`
- `README.md`

Note: `tests/test_workspace_agents_e2e.py` was added to this list after the
writer flagged that the delegated task required editing it (the routing-doc
surface test now asserts `PI.md` names the extension and the hook) while this
document's list omitted it. The writer's report is the record of the deviation.

## Tasks

Strict TDD is active for this repository (`openspec/config.yaml`:
`strict_tdd: true`), so each task below is closed only with observed RED and
GREEN evidence.

- [x] T1 — The generated relay. RED first: `tests/pi-extension.test.mjs`
      asserting the **real generated artifact** behaves like the OpenCode relay
      (allows a clean command, ignores non-bash tools, blocks an off-path push,
      allows the same command through `remote_cli.py`, warns exactly once while
      degrading, and never throws). Then GREEN: the extension template, the
      generator surface, the audit registration, and the expected-rendered-file
      assertions that enumerate Pi's static outputs.
      Closed by `10f35cd` (one `feat(pi):` work-unit commit).
- [x] T2 — The repo-level projection. Refine the `.pi/` ignore rule, teach
      `scripts/sync-repo-harness.py` to project `.pi/extensions/`, write the
      generated artifact, and document the relay in `pi.md.tpl` and the README
      Pi row. Closed by `7e91dd4` (one `feat(pi):` work-unit commit);
      `--check` clean is its acceptance evidence.
- [x] T3 — Release hygiene, added as a blocker the independent verification
      found. `tests/test_version_sources.py` refuses a tagged release whose
      shipped roots changed while the version stood still, so those two commits
      left the suite red: 6 failures total, 5 pre-existing and environmental,
      1 introduced by this branch. Operator chose `0.5.0` (minor: the change is
      additive). Both version literals moved together and `CHANGELOG.md` gained
      its `## 0.5.0` section, which the other assertion in that file demands.
      The bundled kit was rebuilt because `init` stamps a workspace's version
      from the kit manifest (`init.py:192`), not from `__version__` — a stale
      kit would have shipped 0.5.0 code under a 0.4.0 label. Closed by
      `c7f1832` (one `chore(release):` work-unit commit).

## Verification

- `node --test tests/pi-extension.test.mjs` — the focused gate, in isolation.
- `npm test` — node suite (`tests/**/*.mjs`), the exact CI leg.
- `.venv/bin/python -m pytest` — Python suite; see the environmental note below
  for why this is the exact runner and not `npm run test:all`.
- `python scripts/sync-repo-harness.py --check` — must report clean and exit 0
  once T2 lands.
- Negative control: with `.pi/extensions/refuse-offpath-push.ts` deleted from a
  copy of the generated workspace, the refusal case must fail — proving the gate
  tests the relay and not the environment.

## Known environmental failures

- `npm run test:all` cannot be the runner here: its `test:py` leg is
  `.micromamba/envs/papersmith/bin/pytest`, and `.micromamba/` does not exist in
  this checkout (`scripts/setup_env.py` provisions it). The equivalent, and what
  CI itself runs, is `.venv/bin/python -m pytest`. This is pre-existing and
  unrelated to this change.

## Evidence

- Commits on `feat/pi-portability`: `10f35cd` (T1, generated relay + gate),
  `7e91dd4` (T2, checked-in projection + docs), `c7f1832` (T3, version 0.5.0 +
  changelog).
- Independent verification of T1/T2 (read-only, adversarial) held 7 of 7 claims:
  never-throws on 8 degradation paths not covered by the shipped test; refusal
  blocks naming the real `kernels_push` surface from the real adapters; the
  default export is what Pi's loader requires; the artifact is byte-identical to
  the template's render (sha256 `774e5706...a0ee`); `audit` reports a planted
  `.pi/extensions/` file as surplus ONLY at HEAD and not at base (exit 3 vs 0);
  the ignore split behaves and the artifact is tracked in `7e91dd4`; and no
  pre-existing assertion was relaxed. It also found the T3 blocker.
- `pi.md.tpl`'s `## Safety extension` section landed with T1, not T2 as this
  document first said, because `tests/test_workspace_agents_e2e.py` asserts it
  and that assertion is part of T1's gate. Splitting it would have made T1 red.
- Writer-reported evidence: RED `9 fail` reporting the missing deliverable before
  implementation; GREEN `10 pass`; `npm test` `663 pass / 0 fail`;
  `python3 scripts/sync-repo-harness.py --check` -> `clean (20 files)`;
  4 pytest modules `95 passed, 141 subtests passed`; negative control reproduced
  by deleting the artifact from a workspace copy.
- Environment: `require_non_forge_interpreter()` guard untouched; the node gate
  falls back to `python3` + `PYTHONPATH=src` when `.venv/bin/papersmith` is
  absent, exactly as the OpenCode gate does.
- Known environmental failures, pre-existing and reproduced at base: the 5
  `tests/test_forge_gate.py::GateInterpreterTests` tests fail because
  `.micromamba/envs/papersmith` was never provisioned in this checkout.
- Final independent verification at `c7f1832` (after T3): `npm test` 663 pass /
  0 fail; `.venv/bin/python -m pytest` `5 failed, 5179 passed, 8 skipped` where
  the 5 are exactly the pre-existing `GateInterpreterTests`; 
  `sync-repo-harness.py --check` clean (20 files); version agrees end-to-end
  (`package.json`, `papersmith.__version__`, `pyproject` still derived, and a real
  `papersmith init` stamps `0.5.0` from the rebuilt kit); every factual claim in
  the `## 0.5.0` changelog section checked against the code and supported; the 10
  node gate tests present as `ok 118`-`ok 127` with zero skips. No new defect.

## Observation carried forward (not fixed, no claim made)

The extension's load contract is proven through the loader Pi itself uses
(`jiti.import(path, { default: true })`) and by reading Pi's own loader, not by
a live `pi` session: a real end-to-end run needs project trust for this
checkout, which is a user decision. Note also that
`pi -ne -e <file> --help` does NOT validate an extension — a named-export and a
throwing-factory file both exit 0 — so that probe is inconclusive and must not
be cited as evidence.
