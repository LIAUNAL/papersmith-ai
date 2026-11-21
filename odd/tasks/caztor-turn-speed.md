Faster chat turns in Caztor (all providers), measured before and after.
Branch: papersmith-ai `pr/caztor-embed`. Delivery: single-pr (same PR as caztor-vendor). Runners: vitest + tsc (caztor/).

## Specs

- S1. "revisa la velocidad de respuesta, no solo en pi sino en todos, siento que está muy lento, quizas es el json? o que puede ser, arreglalo": find where a turn's time goes and cut it, for every provider.
- S2. "cambia el  Soy el asistente de escritura de Caztor. por  Soy el asistente de escritura de PaperSmith": the writing assistant presents itself as PaperSmith's.

## Tasks

- [x] T1 [S2] Agent definitions: "You are the writing assistant of PaperSmith, built into its local LaTeX editor."; heading "PaperSmith academic writing agent". Route: inline. Commit: 25a4d28c.
- [ ] T2 [S1] A tutor's structured answer shows each field as soon as it is complete while the JSON streams, not only "reply". Route: inline.
- [ ] T3 [S1] Pi keeps the prompt cache for an hour (PI_CACHE_RETENTION=long), so a pause over 5 minutes does not reprocess the whole conversation. Route: inline.
- [ ] T4 [S1] The provider check (`detect`: `--version`, Pi `--list-models`) is reused for a minute instead of spawned before every turn. Route: inline.
- [ ] T5 [S1] The per-turn project snapshot does less work when nothing changed. Route: inline.

## Log

- L1 (2026-11-20) "revisa la velocidad de respuesta, no solo en pi sino en todos, siento que está muy lento, quizas es el json? o que puede ser, arreglalo. ademas, cambia el  Soy el asistente de escritura de Caztor. por  Soy el asistente de escritura de PaperSmith"
- L2 (2026-11-20) Measured (Pi session logs and a timing harness on a copy of the workspace, 2855 walked files, 2.1 GB): Caztor adds ~2.4 s before the agent starts (Pi alone starts in 0.26 s): detect ~0.6 s, snapshot capture ~0.9 s warm (3.4 s cold), prune ~0.17 s, diff after the turn ~0.3 s. The model side dominates: the final tutor answer is 2400-3800 output tokens (17-26 s) plus ~700 reasoning tokens; the first call of each turn reads 0 cached tokens and re-writes 40-55k because the pauses between questions (330-549 s) outlast the 5-minute cache. While the JSON streams only "reply" is shown; the other fields appear together at the end.
