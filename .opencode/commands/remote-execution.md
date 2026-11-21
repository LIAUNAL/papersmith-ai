---
description: "Trigger: durable record of what a repository has submitted to a remote worker, what came back, and how much to submit at once: the append-only ledger and the fold that derives per-entrypoint state, the capacity clamp and worker auto-selection, the `remote_cli` front door (`submit` with its path guard, `status`, `poll`, `fetch`, `reconcile`, `distribute`, `remaining`, `generate-job`, `smoke`, `record`, `readiness`, `preflight`, `generate-jobs`, `prune-caches`), the backend-agnostic adapter seam (ABC, frozen shapes, registry), and one shipped backend -- `adapters/kaggle.py`, the only file here allowed to name a service, shelling out to `adapters/kaggle_driver.py`, the only one allowed to import the pinned `kagglesdk` client."
---

Read `skills/remote-execution/SKILL.md` and follow it for this task. Before you act on the text below, apply the prompt gate of `skills/prompt-gate/SKILL.md` to it (skip the gate when the text carries `[prompt-gate: approved]`, when the operator asked to launch it as is, or when this skill is `prompt-gate`). Treat the text below as `$ARGUMENTS`:

$ARGUMENTS
