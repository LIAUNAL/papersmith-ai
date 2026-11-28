---
description: "Trigger: ingest reference PDFs into high-fidelity Markdown (LaTeX equations, Markdown tables, figures as files), locally and keyless, routing each page to a fast text-layer path or to Docling only when it needs it."
---

Read `skills/paper-ingestion/SKILL.md` and follow it for this task. Before you act on the text below, score it with the prompt gate unless it carries `[prompt-gate: approved]`, the operator asked to launch it as is, or this skill is `prompt-gate`: pipe the text verbatim on stdin, through a quoted heredoc whose delimiter does not occur in it, to `python -m skills._core.command_center.prompt_gate check --skill paper-ingestion`. On `"verdict": "pass"` follow the skill with the text unchanged and say at most one line about the gate; on `fail`, or when the command cannot run, read `skills/prompt-gate/SKILL.md` and continue from its Step 1 result. Treat the text below as `$ARGUMENTS`:

$ARGUMENTS
