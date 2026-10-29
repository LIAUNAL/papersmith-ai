# {{title}} — Claude Code Entrypoint

This standalone paper workspace is managed by `papersmith` {{version}}.

## Canonical context

- **Workspace configuration**: `papersmith.yaml`
- **Domain guidelines**: `guidance/paper-guide/`
- **Available capabilities**: `skills/*/SKILL.md`
- **Research topic**: {{topic}}

## Canonical agents

{{agents}}

The `.claude/agents/` tree is the single source of truth for agent
definitions. Other harness documents are generated projections; do not fork
their instructions manually.

## Slash commands

Every top-level skill under `skills/` is also generated as a slash command in
`.claude/commands/<name>.md`, so it can be invoked directly. Each command body
loads that skill's `SKILL.md` and passes your text through as `$ARGUMENTS`. The
directory is a framework artifact: `smith audit --check-drift` reports drift
and `smith upgrade` restores it, so do not edit it by hand.

{{language_rule}}

{{paper_flow}}
