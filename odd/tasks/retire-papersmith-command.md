# Retire the `papersmith` command: `smith` is the only CLI

Objective: the package installs one console script, `smith`; the `papersmith` alias kept since 0.19.0 is removed, and workspaces whose MCP files still launch it are repaired by `smith upgrade`.
Branch: chore/retire-papersmith-command (worktree ../papersmith-ai-worktrees/retire-papersmith-command). Delivery: ask-on-risk. Test runner: pytest (`.micromamba/envs/papersmith/bin/python -m pytest`) and `node --test`.

## Specs

- S1 "make a plan to remove the old papersmith cli tool (now only smith cli will be used)"
- S2 (design decision) Keep everything that is not the command: the `papersmith-ai` package, the `papersmith` module, the micromamba env, `papersmith.yaml`, `.papersmith/`, the MCP server key `"papersmith"`, its `papersmith.*` tools and `LEGACY_BLOCK_BEGINS` (pre-0.19 `.gitignore` markers).
- S3 (design decision) 0.2.0-0.18.x printed and documented `"command": "papersmith"` for the MCP server; those files are workspace-owned and preserved by `upgrade`, so a convergence migration (`mcp-legacy-papersmith-command`) rewrites only that field, under any server key, and leaves explicit paths and non-object files alone. A version-gated migration cannot ship (`test_the_shipped_registry_declares_no_gate_at_or_below_this_release`).
- S4 (design decision) Changing the `.gitignore` template comment must not turn the old comment into a "workspace line" when a pre-0.14.0 file (no markers) is converted: `RETIRED_BLOCK_LINES` lists template lines earlier releases carried, the same idea as `LEGACY_BLOCK_BEGINS`.

## Tasks

- [x] T1 [S1] `pyproject.toml` installs only `smith`; `test_only_smith_is_installed` replaces `test_both_entry_points_stay_installed` — inline
- [x] T2 [S3] `RetireLegacyCommand` convergence migration + `tests/test_migration_legacy_command.py` (unit + a real `upgrade`) — inline
- [x] T3 [S4] `gitignore.tpl` comment names `smith`; `RETIRED_BLOCK_LINES` keeps the 0.13.0 conversion clean — inline
- [x] T4 [S1] Living docs (`README.md`, `docs/cli.md` incl. the migration list, `tests/fixtures/README.md`, `kit.py`), the dashboard's "smith CLI verified" label (+ es), the Node tests' `.venv/bin/smith` — inline
- [ ] T5 Release note in CHANGELOG 0.70.0 (written in the release commit, per `docs/releasing.md`)

## Log

- L1 (2026-11-09) Mapped: no shipped code resolves or runs the `papersmith` binary (MCP snippet, bridge, dashboard, doctor, smoke scripts use `smith` or `python -m papersmith.cli`). History is left as written: CHANGELOG <= 0.19.0, `odd/tasks/*`, `openspec/changes/archive/*`, the v0.13.0 fixture tarball and `tests/fixtures/README.md:13`.
- L2 RED: `test_only_smith_is_installed` failed on the second script; `tests/test_migration_legacy_command.py` failed to import `RetireLegacyCommand`. After the template edit, `test_lines_added_to_a_0_13_0_file_survive_its_conversion` failed with the old comment kept below the block, which is what S4 fixes.
- L3 Release-note text for 0.70.0 (0.69.0 was released from main on 2026-11-10 while this branch was in review, with the alias still installed): "Removed: the `papersmith` command (an alias of `smith` since 0.19.0). Use `smith`. `smith upgrade` repoints workspace MCP entries that still launch it; edit user-level configs (`~/.claude.json`, `~/.gemini/config/mcp_config.json`, `agy mcp add` registrations) by hand; if a dangling `papersmith` stays on `PATH` after `pipx upgrade`, run `pipx reinstall papersmith-ai`."
- L-release (2026-11-10) Merged into main and released 0.71.0 (merge onto main, release prep 5bc865eb, tag v0.71.0); remote branch deleted after merge.
