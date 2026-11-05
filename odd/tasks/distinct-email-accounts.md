# distinct-email-accounts
Objective: Accept multiple Kaggle or Colab accounts in the project flow, provided each account is associated with a distinct email address.
Branch: feat/distinct-email-accounts · Delivery: single merge · Runners: `.micromamba/envs/papersmith/bin/pytest` and `npm run -s test:node`.

## Specs

- **S1** — `smith team add` supports `--email <address>`, validated via standard email regex, and stored in `.papersmith/team.json` under the member record (`email`).
- **S2** — Multi-account acceptance rule: Multiple accounts for the same service (Kaggle or Colab) are permitted across the project, provided each account is associated with a distinct email address. `team.py:add_member` refuses with a clear error if the same email is reused for two accounts of the same service.
- **S3** — Attestation: Update attestation text and `--attest` message to confirm distinct email association (`owns and operates each account under a distinct registered email address`).
- **S4** — Documentation and UI updates: Update `README.md`, `skills/remote-parallelism/SKILL.md`, `skills/kaggle-accounts/SKILL.md`, `skills/remote-execution/SKILL.md`, `skills/_core/command_center/static/i18n/es.js`, `en.js`, `papersmith-flow.html` and adapters to reflect the rule: multiple accounts per service are accepted when associated with distinct emails.
- **S5** — Test suite: Unit tests in `tests/test_team_registry.py` and gating tests verifying distinct emails, duplicate email rejection per service, and backward compatibility for entries without email.

## Tasks

- T1 [S1-S5] Implement `--email` flag, validation, duplicate email check per service, update attestation, adapters, docs, i18n, and tests. Status: done; 205/205 pytest passed.

## Log

- L1 (2026-11-05, user verbatim): "antes de trabajar 1 a 3, explorar las reglas para enlazar cuentas de kaggle y colab desde smith, ajusta la regla para que se acepten varias cuentas de kaggle o colab en el flujo del proeycto, desde que esten asociados a correos distintos"
