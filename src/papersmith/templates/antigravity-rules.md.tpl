# {{title}} — Antigravity Rules

Generated from `.claude/` by `papersmith` {{version}}.

- Treat `papersmith.yaml` as the workspace configuration.
- Treat `.claude/agents/` as the canonical agent definition tree. Antigravity
  agents are generated from it into `.agents/agents/<name>.md`; edit the
  source, never the generated file.
- Read the relevant `skills/*/SKILL.md` before invoking a capability.
- Antigravity invokes each skill as `/<name>` through the `.agents/skills` link
  to `skills/`; no command files are generated. Read the skill's
  `skills/<name>/SKILL.md` first.
- Keep research artifacts under their declared workspace directories.

## Research topic

{{topic}}

## Available agents

{{agents}}

{{language_rule}}

{{paper_flow}}
