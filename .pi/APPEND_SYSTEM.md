# Papersmith AI — Pi Runtime

Minimal harness entrypoint. This file does not duplicate guidance; it only routes
to the canonical sources of truth so a single set of docs drives every harness.
Pi appends it to the project system prompt.

## Canonical context

- **Project context**: `openspec/project-context.md`
- **Domain guidelines**: `guidance/paper-guide/` (user drop-zone; loaded automatically by `proposal-deliberation`, optional at rest)
- **Available capabilities (skills)**: `skills/*/SKILL.md`

## Skills

Skills live once at the repository-root `skills/` tree and are discovered through
`.pi/settings.json`, whose `"../skills"` entry resolves to that tree. Read each
skill's `SKILL.md` before invoking it; it is the source of truth for that
capability.

## Invoking skills

Pi loads every workspace skill and exposes it natively as `/skill:<name>`, so no
command files are generated for Pi. Invoke a capability by asking for it by name
or as `/skill:<name>`; the agent reads `skills/<name>/SKILL.md` before the work
starts, and that file remains the source of truth.

## Precedence

A trusted project `.pi/APPEND_SYSTEM.md` takes precedence over the operator's
own `~/.pi/agent/APPEND_SYSTEM.md`, and the two are never combined. This file
therefore suppresses the operator's own system-prompt append inside this
workspace.
