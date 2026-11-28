---
description: "Trigger: an operator wants to consult, question and iterate on the decisions behind a paper's experiments — network architecture, hyperparameters and their search, ablation studies, statistical significance tests, the purpose of the toy-set experiment, training strategies, upper bounds (the oracle and reference results a method is measured against), the methods compared and the fidelity of their implementation, validation scheme and leakage, compute budget and reproducibility — from the dashboard's experiments panel or any harness."
---

Read `skills/experiments-tutor/SKILL.md` and follow it for this task. Before you act on the text below, score it with the prompt gate unless it carries `[prompt-gate: approved]`, the operator asked to launch it as is, or this skill is `prompt-gate`: pipe the text verbatim on stdin, through a quoted heredoc whose delimiter does not occur in it, to `python -m skills._core.command_center.prompt_gate check --skill experiments-tutor`. On `"verdict": "pass"` follow the skill with the text unchanged and say at most one line about the gate; on `fail`, or when the command cannot run, read `skills/prompt-gate/SKILL.md` and continue from its Step 1 result. Treat the text below as `$ARGUMENTS`:

$ARGUMENTS
