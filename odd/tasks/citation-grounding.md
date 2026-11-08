# Citation grounding: every SOTA citation quotes its reference's abstract

Objective: each citation in `.papersmith/citations.json` carries a verbatim quote of the pool record's abstract that holds the idea, checked deterministically, plus a reverse map of which ideas each reference supports (issue #160).
Branch: feat/citation-grounding. Delivery: ask-on-risk. Test runner: pytest (`.micromamba/envs/papersmith/bin/python -m pytest`).

## Specs

- S1 "si, abre el issue e implementa la primera idea" — the first idea: "En vez de un `sota-scout` que asigna una sola familia por paper, cada referencia del pool quedaría ligada a los pilares, hipótesis, ecuaciones o secciones que su abstract respalda", "chequeado de forma determinista".
- S2 Operator decision (2026-11-08): "Obligatorio ya" — a citation without a quote is owed; Phase 4's SOTA citations step and G-EXP-POC reopen until every citation is grounded, qmleegV2 included.

## Tasks

- [x] T1 [S1, S2] citations.py: required `quote` checked verbatim against the pool abstract; `routes` in state(); `citations_cli.py routes`; quote shown by the panels — inline
- [x] T2 [S1] skills and docs that write citations ask for the quote (proposal-deliberation, experimental-deliberation, results README, CLAUDE.md flow text) — inline
- [x] T3 [S1] tests and fixtures; full suite compared with main — inline

## Log

- L1 (2026-11-08) "si, abre el issue e implementa la primera idea"
- L2 (2026-11-08) Operator answer: "Obligatorio ya".
- L3 Issue #160 opened.
- L4 T1–T3 done: 7 RED → GREEN tests in tests/test_sota_citations.py (quote required, verbatim, 20–300 characters, no-abstract refusal, routes in state and CLI, quote in the panels). Full suite: 37 failing ids, every one also failing on main (doctor, smoke, MCP e2e, skill_audit, CLI e2e: environmental here; header digest, roster and 06-introduction translation: fixed in PR #161).
