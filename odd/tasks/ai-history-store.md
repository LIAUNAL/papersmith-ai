Objective: keep every user prompt and agent answer of every harness in a persistent, git-tracked workspace store, and make the iteration and success graph honest.
Branch: feat/ai-history-store from main (24d31dab). Delivery: ask-on-risk. Test runner: pytest.

## Specs

- S1. "debe quedar el historial de los prompt del usuario y las respuestas que da el agente, algunas no se estna guardando, o quean incompletas".
- S2. "revisa y ajsuta, sin romper, sino mas bien mejorar el analisis grafo de iteraciones y exitos para hacer seguimiento el historial de interaccion con el agente de ia".
- S3. Plan item 1, approved: a persistent store in `.papersmith/ai-history/`, full text, incremental import.
- S4. Plan item 2, approved: keep every turn, with an unassigned phase for turns before the first phase command.
- S5. Plan item 3, approved: separate iteration, correction, tool error and success, with metrics per phase.
- S6. Plan item 4, approved: import what still exists on the Mac.
- S7. "decido git para todos los proyectos seguir historial ia": the store is tracked by git in every workspace, with secrets filtered before saving.

## Tasks

- T1 [S3, S4, S7] inline. Store, full-text capture, secret filter, git tracking. Pending.
- T2 [S1, S4] inline. Lost turns: queued prompts, non-phase commands, tutors, subagents, subdirectories, false turns. Pending.
- T3 [S2, S5] inline. Graph metrics and panel. Pending.
- T4 [S6] inline. Import from the Mac into QMLEEG. Pending.

## Log

- L1 (2026-11-07, verbatim): "luego, revisa en papersmith, como etamos guardando historial IA, debe quedar el historial de los prompt del usuario y las respuestas que da el agente, algunas no se estna guardando, o quean incompletas. revisa y ajsuta, sin romper, sino mas bien mejorar el analisis grafo de iteraciones y exitos para hacer seguimiento el historial de interaccion con el agente de ia"
- L2 (2026-11-07, verbatim): "trabaja el plan 1 a 4 y decido git para todos los proyectos seguir historial ia"
- L3. Routes: all inline, one dependent chain. Risk: item 1 (persisted format) and item 3 (shared record).
