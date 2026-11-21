Faster chat turns in Caztor (all providers), measured before and after.
Branch: papersmith-ai `pr/caztor-embed`. Delivery: single-pr (same PR as caztor-vendor). Runners: vitest + tsc (caztor/).

## Specs

- S1. "revisa la velocidad de respuesta, no solo en pi sino en todos, siento que está muy lento, quizas es el json? o que puede ser, arreglalo": find where a turn's time goes and cut it, for every provider.
- S2. "cambia el  Soy el asistente de escritura de Caztor. por  Soy el asistente de escritura de PaperSmith": the writing assistant presents itself as PaperSmith's.

## Tasks

- [x] T1 [S2] Agent definitions: "You are the writing assistant of PaperSmith, built into its local LaTeX editor."; heading "PaperSmith academic writing agent". Route: inline. Commit: 25a4d28c.
- [x] T2 [S1] A tutor's structured answer shows each field as soon as it begins while the JSON streams, not only "reply". Route: inline. Commit: bf239014.
- [x] T3 [S1] Pi keeps the prompt cache for an hour (PI_CACHE_RETENTION=long), so a pause over 5 minutes does not reprocess the whole conversation. Route: inline. Commit: ceb9a87f.
- [x] T4 [S1] The provider check (`detect`: `--version`, Pi `--list-models`) is reused for a minute instead of spawned before every turn; a not-installed result is never reused. Route: inline. Commit: ea54fa64.
- [x] T5 [S1] The per-turn project snapshot keeps earlier manifests in memory and lists stored copies once. Route: inline. Commit: 0b85f629.

## Log

- L1 (2026-11-20) "revisa la velocidad de respuesta, no solo en pi sino en todos, siento que está muy lento, quizas es el json? o que puede ser, arreglalo. ademas, cambia el  Soy el asistente de escritura de Caztor. por  Soy el asistente de escritura de PaperSmith"
- L2 (2026-11-20) Measured (Pi session logs and a timing harness on a copy of the workspace, 2855 walked files, 2.1 GB): Caztor adds ~2.4 s before the agent starts (Pi alone starts in 0.26 s): detect ~0.6 s, snapshot capture ~0.9 s warm (3.4 s cold), prune ~0.17 s, diff after the turn ~0.3 s. The model side dominates: the final tutor answer is 2400-3800 output tokens (17-26 s) plus ~700 reasoning tokens; the first call of each turn reads 0 cached tokens and re-writes 40-55k because the pauses between questions (330-549 s) outlast the 5-minute cache. While the JSON streams only "reply" is shown; the other fields appear together at the end.
- L3 (2026-11-20) Verification: Caztor 3619 tests green, tsc clean. Timing harness on the copy of the workspace: capture 900 -> ~330 ms, prune 170 -> ~15 ms, detect skipped within a minute (was ~0.6 s); Caztor's work before the agent starts goes from ~1.7 s to ~0.35 s. Replaying the three real tutor answers in 40-character steps: the question shows from character ~3500-4000 instead of only at the end (~5100-5900), the parsed answer never shrinks, and every final block still parses. Pi requests ttl "1h" from Anthropic with PI_CACHE_RETENTION=long (checked in Pi's anthropic-messages code); a live check was not possible: Pi with the Anthropic account now answers "Third-party apps now draw from your extra usage, not your plan limits."
