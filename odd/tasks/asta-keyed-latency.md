# Asta lookups that stay silent are asked again

Objective: the dashboard's key Verify and the citation resolver stop reporting a working Asta key as unreachable when Asta is slow to answer a keyed lookup.
Branch: fix/asta-keyed-latency (from main 0.73.0, worktree ../papersmith-ai-worktrees/asta-keyed-latency). Delivery: ask-on-risk. Test runner: pytest (`.micromamba/envs/papersmith/bin/python -m pytest`).

## Specs

- S1 (Report) The dashboard's API keys panel showed "Could not reach the service (unreachable: The read operation timed out)" for a stored, working Asta key.
- S2 (finding, measured live 2026-11-11) Keyless `get_paper` calls answered in 0.4-0.7 s. Keyed ones answered in 0.4-0.7 s or only after 30.5-30.8 s or 60.6 s, with a `: ping` every 15 s meanwhile, and a fresh request usually answered at once. Verify waited 10 s per read (20 s in all); the resolver's lookup allowed 30 s.
- S3 (design decision) Raising the deadlines would still lose the 60 s answers and make every slow one cost half a minute: a lookup silent for `asta_protocol.LOOKUP_ATTEMPT_SECONDS` (5 s) is asked again until the call's deadline. A refusal, a missing paper, an HTTP error or a tool error is never retried by this rule.

## Tasks

- [x] T1 [S3] `asta_protocol`: `LOOKUP_ATTEMPT_SECONDS`, `AstaError.timed_out` — inline
- [x] T2 [S1, S3] `api_keys.verify`: attempts within a 30 s deadline — inline
- [x] T3 [S3] `paper_resolve._asta_call(attempt_seconds=…)` for `get_paper` lookups; title searches unchanged — inline
- [x] T4 tests (verify and resolver: a silent lookup asked again, silent attempts ending at the deadline) and docs (cli.md, skills.md) — inline

## Log

- L1 (2026-11-11) RED on main 9b9994b9: the 4 new tests fail; GREEN with the change.
- L2 Live with the operator's key: 12 of 12 verifies ok (0.4-16 s, before: about 1 in 3 unreachable, the rest up to 30 s); 6 of 6 DOI lookups resolved (0.4-6.4 s).
- L3 Full suite (`-n 8`): 9972 passed, 9 failed, the same 9 that fail on clean main on this machine.
- L4 Not changed: journal-finder (60 s per call, searches) and the agents' MCP timeout (60 s).
