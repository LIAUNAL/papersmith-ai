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
- Before acting on the text given to `/<name>`, score it with the prompt gate:
  pipe the text verbatim on stdin to
  `python -m skills._core.command_center.prompt_gate check --skill <name>`.
  On `"verdict": "pass"` follow the skill with the text unchanged; on `fail`,
  or when the command cannot run, read `skills/prompt-gate/SKILL.md` and
  follow it: alert, propose an improved prompt or ask clarifying questions,
  and wait for the operator. Skip the gate when the text carries
  `[prompt-gate: approved]`, when the operator asked to launch it as is, or
  for `/prompt-gate` itself.
- Keep research artifacts under their declared workspace directories.

## Research topic

{{topic}}

## Available agents

{{agents}}

{{language_rule}}

{{paper_flow}}
