# Agents Office 3D (smith agents + Engram)

Objective: rebuild the Agents Office panel as a Three.js office in the style of weherd (local fork at ~/Documents/3DOfficeAI, origin amalvarezme/weherd), with the 29 smith agents plus the orchestrator and an Engram memory space; agents animate by measured state.
Branch: feat/agents-office-3d. Delivery: ask-on-risk. Runner: `.venv/bin/python -m pytest` (+ node harness tests).

## Specs

- S1 (Roster): the office shows the agents defined in smith — every `.claude/agents/*.md` of the workspace (29 today, read through `agents_view.get_agents_view`) — "incluido orquestador": the orchestrator is the main CLI session; the CLI programs (claude, opencode, pi, herdr, antigravity, shell) are no longer desks, only where the orchestrator runs.
- S2 (3D like weherd): "hazlo con el diseño 3D que usa weherd, mire el repo que tenemos en esta maquina, veririca que librerias usa, funcionalidad etc, y usa su nismo tipo d eofiicna". Same library (three.js 0.183.0, vendored, no network, no build step) and the same kind of office.
- S3 (Engram space): "añade un espacio para la interaccion con la memoria engram".
- S4 (Mechanics): "los agentes deben tener mecanicas que ilustren si estan en ejecucion de tarea, o disponibles o salvando o cargando informacion de la memoria engram". States: working (task running), available, saving to Engram, loading from Engram — each derived from measured facts (live CLI session output, phase runs), never invented.
- S5 (Kept guarantees from 0.70.0): read-only panel; same authorization semantics as the terminal; i18n keys in en.js and es.js; docs updated; cache token.

## Tasks

- [x] T1 [S1, S4] Server: office state from agents_view roster + per-agent state detection (invocation + Engram save/load attribution) + tests — inline
- [x] T2 [S2, S3, S4] Vendor three.js 0.183.0 + office3d scene (weherd style) + Engram space + state animations + tests — inline
- [x] T3 [S5] i18n, docs/terminals.md, vendor README, cache token, e2e screenshot — inline

## Log

- L1 (2026-11-10) User request (verbatim): "sí, rehazlo con los 29 agentes y el orquestador pero hazlo con el diseño 3D que usa weherd, mire el repo que tenemos en esta maquina, veririca que librerias usa, funcionalidad etc, y usa su nismo tipo d eofiicna y añade un espacio para la interaccion con la memoria engram, los agentes deben tener mecanicas que ilustren si estan en ejecucion de tarea, o disponibles o salvando o cargando informacion de la memoria engram"
- L2 Context: previous answer found the 0.70.0 office used terminal.default_agents() (CLI programs) as desks. Weherd deps: three ^0.183.0, @xterm/xterm, ws, vite.
- L3 Risk: item 5 (new vendored dependency three.js 0.183.0, MIT).
- L4 Weherd map (~/Documents/3DOfficeAI/src/office.ts): three ^0.183 only, no addons, everything procedural; ortho camera (28,34,36); desks/people/labels/coffee wing ported to static/office3d.js. Coffee lounge replaced by the Engram core.
- L5 Found and fixed a 0.70.0 defect: the office route /api/office/state sat outside the terminal cookie path (/api/terminal), so a browser never sent the cookie and the office always read unauthorized. Now served at /api/terminal/office (old path kept). Risk: item 2 (authorization surface) + item 5 (vendored dependency).
- L6 Evidence: tests/test_command_center_office.py 25 passed; test_dashboard_i18n 51 passed; real Chromium e2e with a fake agent CLI: states sota-scout:saving, redactor:loading, diagram-author:working, orchestrator:working, 36 stream cubes, 2 memory cubes, card opens on click, no page errors (scratchpad e2e/office-*.png).
- L7 (2026-11-10) User (verbatim): "despues de revisar los cambios, utiliza el proyecto papersmitharxiv oara que valides funcionamiento del cli smith sin tener cargado agente o herdr, y el panel de agentes office incluyendo la interaccion de los agentes de smith con orquestador y con engram". Live run on smithPaperArxiv with real Claude Code: CLI activated from a cookie-less tab; office showed orchestrator loading, math-tutor working, orchestrator saving (Engram count 2874->2875). Found Claude Code repaints with cursor moves and folds MCP calls; added office.Screen + store-count direction (055a2bd5), hardened after verifier blockers (1d1834df). No smith agent has Engram tools: only the orchestrator touches Engram.
- L8 (2026-11-10) User (verbatim): "sí, merge a main, push y release". Released 0.72.0: feature merge 34c23e8b, release prep a274db86, release merge c943eb5f, tag v0.72.0 pushed; GitHub release published. Gentle AI review: server slice approved; scene slice declined after provider defect #4571 (occurrence reported); whole branch exceeds lens budget.
