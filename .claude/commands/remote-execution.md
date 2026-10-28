---
description: "Trigger: durable record of what a repository has submitted to a remote worker, what came back, and how much to submit at once: the append-only ledger and the fold that derives per-entrypoint state, the capacity clamp and worker auto-selection, the `remote_cli` front door (`submit` with its path guard, `status`, `poll`, `fetch`, `reconcile`, `distribute`, `remaining`, `generate-job`, `smoke`, `record`, `readiness`, `preflight`, `generate-jobs`), the backend-agnostic adapter seam (ABC, frozen shapes, registry), and one shipped backend -- `adapters/kaggle.py`, the only file here allowed to name a service, shelling out to `adapters/kaggle_driver.py`, the only one allowed to import the pinned `kagglesdk` client."
---

Read `skills/remote-execution/SKILL.md` and follow it for this task. Treat the text below as `$ARGUMENTS`:

$ARGUMENTS
