# Does Pi actually work here? A three-tier verification of the Pi surface

Branch: `feat/pi-harness-verification`, off `a67d616` (unreleased `main`). The
operator deleted `feat/pi-portability` and asked whether the Pi functionality
works on the release baseline. This file records the answer, not a fix.

## Why

`feat/pi-portability` carried the Pi work and was deleted without merge. Two of
its task files (`pi-projection-pi-actually-reads.md`,
`pi-residuals-seed-and-description-budget.md`) had recorded Pi defects and this
repository's fixes for them. Deleting the branch removed the fixes and left the
defects live on `main`, so "does Pi work" is a question with a checkable answer
rather than an assumption either way.

The verification deliberately does not trust this repository's prose. `PI.md`
and `.pi/README.md` both describe what Pi reads; neither is Pi. Every claim below
was reproduced against Pi's own runtime.

## Method

Three tiers, weakest to strongest. A finding is only reported when the strongest
tier available agrees.

1. **Source** — Pi `0.87.1` at
   `/Users/andresalvarez/.npm-global/lib/node_modules/@earendil-works/pi-coding-agent`.
2. **Loader probe** — `DefaultResourceLoader` + `loadProjectContextFiles` from
   `dist/index.js`, driven with an explicit `cwd`. Reports discovered skills,
   project context files, and diagnostics without spending a model call.
3. **End-to-end** — the real `pi` binary, `-p --no-session`, against this
   checkout, asked to name the skills and context files it was given.

## What works

- **P1 — The `.pi/skills` projection is real.** `scripts/setup-harnesses.sh`
  builds four relative links (`.claude`, `.pi`, `.opencode`, `.antigravity` →
  `../skills`). Pi's project skills directory is `<cwd>/.pi/skills`
  (`dist/config.js:403` `CONFIG_DIR_NAME = ".pi"`; `dist/core/skills.js:351`
  `resolve(cwd, CONFIG_DIR_NAME, "skills")`). Tiers 2 and 3 both confirm it.
- **P2 — End-to-end, Pi sees all ten forge skills.** The real binary reported
  the ten skill names plus the operator's own, with no manual wiring beyond the
  link. This is the strongest evidence in the file: not inference, a run.
- **P3 — This repository's `.gitignore` ignores the four links**, so a rebuilt
  symlink is not a repository change. That is the `a67d616` fix, and it holds.
- **P4 — `.pi/README.md` travels**, so `.pi/` exists in a fresh clone and a
  collaborator does not read three harness directories as four-minus-one.
- **P5 — The forge generates a Pi surface for `--tools pi`**: `PI.md` and
  `.pi/gentle-ai/persona.json`. `pi` is a first-class member of
  `generators.ALL_TOOLS`.
- **P6 — 43 Python tests pass** (`test_harness_parity.py`,
  `test_papersmith_generators.py`, `test_workspace_skills_e2e.py`), 18 subtests
  included.

## What does not work

### D1 — `PI.md` is never read by Pi

Pi's context-file candidates are exactly `AGENTS.override.md`, `AGENTS.md`,
`AGENTS.MD`, `CLAUDE.md`, `CLAUDE.MD`, and `loadContextFileFromDir` returns the
**first** match (`dist/core/resource-loader.js:32-47`). The CLI states the same
thing: `--no-context-files, -nc   Disable AGENTS.md and CLAUDE.md discovery and
loading`. `PI.md` is in neither list.

Confirmed end-to-end. In this checkout Pi loaded:

```
CONTEXT: /Users/andresalvarez/.pi/agent/AGENTS.md, <repo>/CLAUDE.md
```

`PI.md` is absent. In a workspace generated with `--tools pi`, Pi loaded
**exactly one** context file — the operator's own — while `PI.md`, 7.1K of
routing documentation, sat unread in the same directory.

The consequence is not cosmetic. `PI.md` routes to `skills/*/SKILL.md`, and Pi
instead received `CLAUDE.md`, the Claude projection. A Pi-only workspace is
routed by the other harness's file.

This is the defect `pi-projection-pi-actually-reads.md` fixed by replacing the
unread file with `.pi/APPEND_SYSTEM.md` (which Pi does read, at
`dist/core/resource-loader.js:825`). That fix is on the deleted branch.

### D2 — Two shipped descriptions exceed Pi's Agent Skills limit

`dist/core/skills.js:11` sets `MAX_DESCRIPTION_LENGTH = 1024`. The loader probe
reports exactly two diagnostics, in this repository and in a generated
workspace alike:

| Skill | `description` length | Limit |
| --- | --- | --- |
| `paper-writing` | 1680 | 1024 |
| `remote-execution` | 1814 | 1024 |

Pi warns and still loads, so nothing fails — the defect is a warning nobody
reads, and any harness that enforces the spec rejects both. Fixed by `be84434`
on the deleted branch, guarded there by `tests/test_skill_descriptions.py`, a
file `main` does not have.

### D3 — Generated workspaces do not ignore the harness links

`src/papersmith/templates/gitignore.tpl` carries **none** of `.claude/skills`,
`.pi/skills`, `.opencode/skills`, `.antigravity/skills`. Measured with
`git check-ignore` in a workspace from `papersmith init`:

| Path | This repo | Generated workspace |
| --- | --- | --- |
| `.claude/skills` | ignored | **not ignored** |
| `.pi/skills` | ignored | **not ignored** |
| `.opencode/skills` | ignored | **not ignored** |
| `.antigravity/skills` | ignored | **not ignored** |

`a67d616` fixed this contract at the repository root and did not carry it into
the template, so every workspace the forge produces reproduces the defect the
commit was written to close — for all four harnesses, not only Pi. A generated
workspace also receives no `.pi/README.md`, so `.pi/` is invisible there in
exactly the way `a67d616` describes.

D3 is **new**: `git diff a67d616 13b1ef5 -- src/papersmith/templates/gitignore.tpl`
is empty, so the deleted branch did not fix it either.

### D4 — The parity guard cannot see D3

`tests/test_harness_parity.py:26` binds `GITIGNORE = FORGE_ROOT / ".gitignore"`.
It derives its harness roster from the setup script, which is the right idea,
but it reads the repository's own `.gitignore` and never the template that ships
to users. The guard therefore passes while D3 is live, and would keep passing
after any number of generated workspaces reproduced it.

## Not a defect, but load-bearing

`.pi/skills` is a **trust-requiring** project resource: `skills` is a member of
`TRUST_REQUIRING_PROJECT_CONFIG_RESOURCES` (`dist/core/trust-manager.js:8-16`).
A fresh clone whose path is absent from `~/.pi/agent/trust.json` does not load
the project skills until the operator grants trust. This checkout is already
trusted, which is why the probe without `--approve` still found the ten skills.
Anyone reading a "works" result here should know that precondition rather than
rediscover it as an intermittent failure.

## Verification

```
python3 -m unittest tests.test_harness_parity -v
.venv/bin/python -m pytest tests/test_harness_parity.py \
    tests/test_papersmith_generators.py tests/test_workspace_skills_e2e.py -q
node /tmp/pi-probe.mjs "$PWD"                     # loader probe, 10 skills, 2 diagnostics
pi -p --no-session --approve --model nan/deepseek-v4-flash "<name skills and context files>"
PYTHONPATH=src .venv/bin/python -m papersmith.cli init <tmp>/ws --tools pi --no-npm
git check-ignore -q .pi/skills                    # in the generated workspace
```

The `.pi/skills` link in this checkout was created surgically
(`ln -sfn ../skills .pi/skills`) rather than by `npm run setup:harnesses`,
because the script `rm -rf`s each harness target and `.claude/skills` is here a
real directory holding six stale entries of the eleven. The script's own
behaviour was verified in an isolated copy instead.

## Tasks

- [x] T1 — Verify the skill projection at all three tiers. Closed by the probe
      and the end-to-end run recorded above.
- [x] T2 — Verify what Pi loads as project context, against the runtime and the
      CLI. Closed by D1.
- [x] T3 — Verify the forge's Pi surface in a workspace from `papersmith init`.
      Closed by D3.
- [x] T4 — **Decided by the operator: port D1 and D2, leave D3 and D4 open.**
      The port lives in `odd/tasks/pi-reads-its-own-entrypoint.md` (T1–T5 closed
      there, with the measured results). D1 and D2 had fixes on the deleted
      branch and are now re-applied on this one; D3 and D4 are still live and
      still unassigned, which is why this file's D3/D4 sections stay as written.

## Findings carried forward, not fixed here

- `odd/` is untracked and **not** ignored on `main`, so `git add -A` would
  commit machine-state task files. The deleted branch's `.gitignore` added
  `odd/` with the same rationale it gives for `.atl/`; `main` does not.
- `.claude/skills` in this checkout is a real directory with six stale entries,
  not a symlink. Harmless while it is ignored, but it is not the layout the
  setup script converges to, and nothing tests it.
