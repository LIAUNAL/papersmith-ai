---
description: "Trigger: run, track and fetch remote work on Kaggle or Colab workers through `remote_cli` (generate-job, preflight, smoke, readiness, submit, status, poll, fetch, reconcile)."
---

Read `skills/remote-execution/SKILL.md` and follow it for this task. Before you act on the text below, score it with the prompt gate unless it carries `[prompt-gate: approved]`, the operator asked to launch it as is, or this skill is `prompt-gate`: pipe the text verbatim on stdin, through a quoted heredoc whose delimiter does not occur in it, to `python -m skills._core.command_center.prompt_gate check --skill remote-execution`. On `"verdict": "pass"` follow the skill with the text unchanged and say at most one line about the gate; on `fail`, or when the command cannot run, read `skills/prompt-gate/SKILL.md` and continue from its Step 1 result. Treat the text below as `$ARGUMENTS`:

$ARGUMENTS
