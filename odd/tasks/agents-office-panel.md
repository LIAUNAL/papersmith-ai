# Agents Office Panel (0.70.0)

Objective: A new `smith ui` panel, **Agents Office**, inspired by Weherd (amalvarezme/weherd): a live, spatial view of the agents defined in smith — orchestrator included — working in the smith flow, plus a "grand brain / memory" area illustrating the interaction with Engram. Zero additional cost: vanilla JS canvas (no three.js download, no paid APIs, no prompt injection), reusing the existing terminal session APIs.
Branch: feat/agents-office-panel. Delivery: reviewable slices.

## Specs

- S1 (Office state API): A server-side office state module (suggest `skills/_core/command_center/office.py`) answers `GET /api/office/state` with one JSON snapshot: `agents` (every agent `terminal.default_agents()` knows, each with `available`, live session state from the terminal manager, and phase-run activity when it has one), `orchestrator` (the smith orchestrator stretch: derived from the enabled/authorized terminal state and the current phase runs), and `memory` (Engram availability measured on the host: `engram` on PATH, and a bounded in-memory ring of recently observed Engram interactions detected in terminal output, e.g. `mem_`/`engram` command lines). Absent or disabled pieces report `unavailable` reasons; nothing is invented.
- S2 (Agents Office panel): A new dashboard tab renders a 2.5D isometric office on a `<canvas>` in vanilla JS (`static/office-panel.js`, no build step, no external 3D library): the orchestrator's desk at the center, one desk per smith agent, and a distinct **grand-brain memory area** for Engram. Agent desks animate by live state (working / blocked-idle / absent), flow lines pulse orchestrator↔agent and orchestrator↔brain when the state or the Engram ring changes. Clicking an agent's desk focuses the existing CLI console on that agent (reuses the agent picker); the panel stays read-only: no close, no input, no destructive action of any kind (Weherd's shotgun is deliberately excluded).
- S3 (Activation & flow): When the tab activates, the panel polls `/api/office/state` (~2s), shows connection state honestly (authorized/unauthorized/disabled mirror the terminal's own states and reuse the activation banner semantics), and shows the smith flow: which agents are live in sessions and which phase runs are active. When the office cannot be measured (terminal disabled), the panel says so instead of drawing fiction.
- S4 (Docs, i18n, cache): New i18n keys in BOTH `en.js` and `es.js` (parity suite), a `?v=` cache token bump for the new script in `index.html`, and a `docs/` description (terminals.md or a new page + index row).

## Tasks

- [x] T1 [S1] Office state module + `/api/office/state` endpoint + tests
- [x] T2 [S2, S3] `office-panel.js` canvas office + tab + i18n + tests
- [x] T3 [S4] Docs, verification suites, cache token

## Tasks (extension)

- [x] T4 [S2] Agent identity cards: role + model (where measurable) on every desk, and a click-open task card naming the task the agent is performing right now (phase-run instruction when one exists, else its session/last activity); every field absent from the data stays `unknown`, never invented

## Log

- L1 (2026-11-10) User request (verbatim): "explora e implementa un nuevo panel en smith ui que se agents office, inspirado en weherd donde se pueda ver el flujo de los agentes definidos en smith incluido orquestador, y anadele un espacio en la oficina tipo gran cerebro o memoria que ilustre la interaccion con engram. ese panel al activarse debe permitir ver el flujo de agentes que estan trabajando desde el flujo smith y sus agentes".
- L2 (2026-11-10) User addition (verbatim): "incluye la posibilidad de a cada agente se le vea rol y modelo y si se le da clic encima se muestre la tarea que esta realizando" -> S2/T4 amended.
- L3 (2026-11-10) Implementation evidence: T1 office.py + TerminalManager.session_facts + GET /api/office/state (commit b5eb5546; NOTE: committed on main before the feature branch existed — deviation logged, merged state is identical); T2 office-panel.js canvas + tab + i18n en/es + card with role/model/task (eb04dbda, feat/agents-office-panel). Slice boundaries: T1 ~150 lines, T2 ~620 lines.
- L4 (2026-11-10) Verification: test_command_center_office, test_dashboard_i18n (i18n parity incl. office keys; no-Spanish scan clean), test_command_center_terminal, test_command_center_journals, test_svg_audit — 240 passed. Pre-existing environment failure (not a regression, reproduced on the clean tree): test_command_center_smoke fails because this checkout has no .venv (the wiring-smoke leg needs it). T3 docs/terminals.md "The Agents Office panel" section.
