---
description: "Trigger: the experimental deliberation judged a hyperparameter search worthwhile and the protocol declares one — validate its plan (one trial budget for every arm, baselines included; a seeded sampler; nested inside each outer fold's training subjects; nothing the experiments test tuned; the importance evaluator named), estimate its cost from a timing probe, and after the search ran, record per arm and outer fold a summary with hyperparameter importance, contour and optimization-history figures, read back for the dashboard."
---

Read `skills/hyperparameter-search/SKILL.md` and follow it for this task. Before you act on the text below, score it with the prompt gate unless it carries `[prompt-gate: approved]`, the operator asked to launch it as is, or this skill is `prompt-gate`: pipe the text verbatim on stdin, through a quoted heredoc whose delimiter does not occur in it, to `python -m skills._core.command_center.prompt_gate check --skill hyperparameter-search`. On `"verdict": "pass"` follow the skill with the text unchanged and say at most one line about the gate; on `fail`, or when the command cannot run, read `skills/prompt-gate/SKILL.md` and continue from its Step 1 result. Treat the text below as `$ARGUMENTS`:

$ARGUMENTS
