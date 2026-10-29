# {{title}} — OpenCode Entrypoint

Generated from the canonical `.claude/` agent definitions by `papersmith`
{{version}}. Read the workspace configuration and the relevant skill before
changing research artifacts.

## Canonical context

- **Workspace configuration**: `papersmith.yaml`
- **Domain guidelines**: `guidance/paper-guide/`
- **Skills**: `skills/*/SKILL.md`
- **Research topic**: {{topic}}

## Agents

{{agents}}

## Slash commands

Every top-level skill under `skills/` is also generated as a slash command in
`.opencode/commands/<name>.md`, so it can be invoked directly. Each command body
loads that skill's `SKILL.md` and passes your text through as `$ARGUMENTS`. The
directory is a framework artifact: `smith audit --check-drift` reports drift
and `smith upgrade` restores it, so do not edit it by hand.

## Safety plugin

`.opencode/plugins/refuse-offpath-push.js` is generated and auto-discovered by
OpenCode. It relays each `bash` invocation to the `remote-execution` skill's own
`refuse_offpath_push.py`, so the predicate has exactly one authority and a second
service is covered by that service's own adapter. It refuses — with a thrown error
naming the matched surface — a command that names a service's push surface without
also invoking `remote_cli.py`, and it degrades loudly rather than silently
allowing when the guard cannot be loaded. It is a tripwire, not a gate.

{{language_rule}}

{{paper_flow}}
