# Papersmith AI — Pi harness directory

Pi's entrypoint is `APPEND_SYSTEM.md` here. Pi appends it to the project system
prompt, which is why it lives in this directory and not at the repository root:
Pi's context-file candidates are only `AGENTS.override.md`, `AGENTS.md`,
`AGENTS.MD`, `CLAUDE.md` and `CLAUDE.MD`, so a root-level `PI.md` was never
read.

`settings.json` is how Pi finds the skills:

```json
{
  "skills": ["../skills"]
}
```

Pi resolves project settings from the `<cwd>/.pi` base directory, so that
`"../skills"` entry reaches the canonical repository-root `skills/` tree with no
symlink and no setup step. Every workspace `papersmith init` creates gets the
same file, so Pi discovers the ten skills with nothing to run first.

There is deliberately no `.pi/skills` link. Pi dedupes skills by canonical path,
so the old link would not have collided; it would only have been a second
mechanism for one job, and `ln -sfn` is the one projection this repository never
made portable. `.gitignore` still matches `.pi/skills` so a stale link left by
an earlier run of `scripts/setup-harnesses.sh` is not a repository change;
nothing builds it anymore.

This file exists so the directory itself travels with the repository. Without
it a collaborator cloning the repo sees `.claude/`, `.opencode/` and
`.antigravity/` and no `.pi/` at all, and reasonably concludes Pi is not a
supported harness. Pi is supported.

`APPEND_SYSTEM.md` and `settings.json` are versioned. `gentle-ai/` (the
generated persona) is derived and stays ignored.

Pi receives no generated slash commands. It loads every workspace skill through
`settings.json` and exposes each natively as `/skill:<name>`, so no command
files are generated for it; the agent reads `skills/<name>/SKILL.md` before the
work starts.
