Refine the Caztor editor embedded in the smith ui PDF tab before the pull request.
Branches: CaozCompilator `feat/smith-embed`, papersmith-ai `feat/caztor-embed`. Delivery: ask-on-risk. Runners: vitest + tsc (Caztor), pytest (smith).

## Specs

- S1. "como no hay harnesses de codex, vamos a quitarlo y dejar ahi PI": Codex leaves the chat's provider choices; Pi takes its visible place.
- S2. "hay un error y es que se borra el historial de mensajes de respuesta, solo quedan los enviados": the assistant's replies stay in the chat history.
- S3. "quitemos la linea superior en donde está caztor y el theme, que automaticamente tenga el mismo theme que papersmith": embedded, Caztor shows no top bar, and its theme follows the dashboard's (light/dark), including when the dashboard theme changes.
- S4. "no me gusta que salga el sign in en las cuentas cuando ya se ha iniciado sesion, debe identificar que cuentas se han abierto en ese workspace de papersmith": a provider account already signed in for that workspace is recognised and not offered a sign-in.
- S5. "me gustaría que en el chat, estén las opciones de papersmith de / smith math tutor, experimentor tutor, etc... (todas los demas agentes que tenga papersmith)": the chat's `/` menu offers every PaperSmith agent of the workspace.
- S6. "que resalte con un amarillo suave las partes del texto del paper que está explicando y que esta resaltacion se pueda activar y desactivar": the passages of the paper the assistant explains are highlighted soft yellow in the LaTeX editor and the PDF (L2), with a toggle.
- S7. "debemos dejar bien consolidado antes de mandar el pr": every check green, docs updated, branches ready for the pull request.

## Tasks

- [x] T1 [S1] Web provider choices: Pi replaces Codex in the logo row; no "More" menu; Codex dropped from the default order. Route: inline. Commit: CaozCompilator f0f7d3f.
- [x] T2 [S2] History: snapshot walk skips environment/dependency folders at any depth; turn_started carries at most 20 unprotected paths plus a count; a stored turn never loses its text events. Route: inline. Commit: CaozCompilator 51d6494.
- [x] T3 [S3] Embedded: no top bar; theme set by the dashboard over the bridge (initial and on change). Caztor web + smith page. Route: inline. Commit: CaozCompilator af11945, papersmith-ai 5e174c8b.
- [x] T4 [S4] Sign-in state seeded from the provider's own credentials (Claude, Pi, opencode) when the server starts. Route: inline. Commit: CaozCompilator 68ce680.
- [x] T5 [S5] PaperSmith agents of the workspace offered in the `/` menu and run as that agent. Route: inline. Commit: CaozCompilator 0f03459, 70af750.
- [x] T6 [S6] Soft-yellow highlight of the passages the latest reply explains, in the editor and the PDF, with a toggle. Route: inline. Commit: CaozCompilator 8f3b2c4, 70af750.
- [ ] T7 [S7] Consolidation: full suites, docs, smith kit and workspace copy, pull request description. Route: inline. Done: suites, docs (ff4d0b91), kit, Caztor review. Pending: smith review, PR target.

## Log

- L1 (2026-11-19) "mi profesor me pidió mandar la pr, por lo que vamos a refinar esto. como no hay harnesses de codex, vamos a quitarlo y dejar ahi PI. hay un error y es que se borra el historial de mensajes de respuesta, solo quedan los enviados. quitemos la linea superior en donde está caztor y el theme, que automaticamente tenga el mismo theme que papersmith. ademas, no me gusta que salga el sign in en las cuentas cuando ya se ha iniciado sesion, debe identificar que cuentas se han abierto en ese workspace de papersmith, debemos dejar bien consolidado antes de mandar el pr. ademas, me gustaría que en el chat, estén las opciones de papersmith de / smith math tutor, experimentor tutor, etc... (todas los demas agentes que tenga papersmith) y que resalte con un amarillo suave las partes del texto del paper que está explicando y que esta resaltacion se pueda activar y desactivar"
- L2 (2026-11-19) Highlight location answered: "Editor y PDF (Recomendado)".
- L3 Mapping (explorer, 2026-11-19) and reproduction: the server stores replies correctly in a small project (claude.jsonl holds the `text` events; a browser reload keeps them). In this workspace the per-turn snapshot walks `.micromamba/` and nested `.venv` (~166k files): every file past the snapshot limits goes into `turn_started.unprotected`, which makes the event several MB; `storedLine` then exceeds 256 KB even after shortening texts and essential-only filtering, and writes `events: []`, keeping only the prompt. TurnSummary also renders the whole list. Evidence: a 3,340-file copy already yields a 20 KB `turn_started`; `snapshot-store.ts:33` excludes only `.git` and `node_modules` anywhere.
- L4 (2026-11-19) Verification: Caztor 3522 tests green, tsc clean; smith 1295 green (smoke deselected, needs .venv). Live: math-tutor turns read skills/math-tutor/SKILL.md; highlights 3 marks in the editor and 7 on the PDF after scrolling; toggle clears both; theme and no top bar verified embedded.
- L5 (2026-11-20) Caztor native review lineage review-99ec6d6d69a95dcc (risk, resilience, reliability): one CRITICAL, a .caztor/build.seal link could make trust-build overwrite a host file; fixed in 2d36560 (30 lines, links refused), targeted validation approved, acknowledged. Earlier lineage review-e884d0464b2ca547 stays open (needs maintainer authorization to abandon).
