# Asta (Ai2) as an alternative to OpenAlex, with keys asked in the smith UI

Objective: Ai2's Asta (the Semantic Scholar corpus, over MCP streamable HTTP) becomes an alternative to OpenAlex in the citation resolver, journal-finder and the agents' discovery; the Asta and OpenAlex keys are entered once in the dashboard (or `smith keys`), and once the Asta key is there, Asta is asked first.
Branches (stacked, worktree ../papersmith-ai-worktrees/asta-connector): feat/api-keys (S2) -> feat/asta-resolver (S3) -> feat/asta-discovery (S4). Delivery: ask-on-risk; the operator asked for push + PR when done. Test runner: pytest (`.micromamba/envs/papersmith/bin/python -m pytest`) and `node --test`.

## Specs

- S1 "add the use asta as an alternative to openalex" with the documentation https://allenai.org/asta/resources/mcp
- S2 Scope chosen by the operator: citation resolver, agent discovery (MCP) and journal finder. The accepted-lab check (`citations_cli rank`) stays OpenAlex + operator: Asta gives affiliations as free text, not ROR ids.
- S3 "also i need to be part to ask the user where to put asta key, the smith UI, and openalex key too" — both keys are asked for in the smith UI.
- S4 "if the asta key is avalible use asta, are set in smith UI" — no key: behaviour exactly as today (OpenAlex default); Asta key present: Asta preferred, the rest fall through.
- S5 (design decision, measured live 2026-11-09) Asta is stateless MCP streamable HTTP: `tools/call` without `initialize`, replies always `text/event-stream` with `: ping` every 15 s, so callers bound total wall time; a tool's answer and its errors travel in `result.content[*].text` with HTTP 200 ("... not found", "HTTP status 403 Forbidden."); an empty `x-api-key` is keyless; unkeyed searches stall (> 60-120 s) while id lookups answer in ~1 s.
- S6 (design decision, measured) Coverage complements OpenAlex: `10.1016/j.neunet.2014.09.003` has an abstract only in Asta, `10.1109/5.726791` only in OpenAlex, `10.1038/nature14539` is not in Asta. So Asta is a fall-through on "not found" and "no abstract", and each record kept comes whole from one connector.
- S7 (design decision, security) One key store for three interpreters: `skills/_core/api_keys.py`, standard library only, loaded by path by the skill scripts, the dashboard and `smith`. `$XDG_CONFIG_HOME/papersmith/keys/<provider>` (0700/0600), an exported variable wins, no output carries a value; the dashboard routes sit behind the terminal's cookie and guards (loopback only) and refuse writes without `Origin`.
- S8 (design decision, license) Ai2's Asta Scientific Corpus Tool License: academic and non-commercial use, attribution, personal key. Shown in the panel and docs; papersmith never requests a key on the operator's behalf (OpenAlex's 401 body advertises an agent endpoint for that, which is not used).

## Tasks

- [x] T1 [S5] `skills/_core/literature/asta_protocol.py`: request, SSE/JSON reader with a total deadline, error classification from tool text, paper parsing — inline
- [x] T2 [S3, S7] `skills/_core/api_keys.py`: store/read/status/clear/verify, session env, literal scrub; conftest isolates the store (`PAPERSMITH_KEYS_DIR`), the clean-context gate plants private decoys — inline
- [x] T3 [S3] `smith keys set|status|clear` + offline `smith doctor` rows — inline
- [x] T4 [S3, S7] Dashboard: `keys_view.py`, `/api/terminal/keys*` routes, session injection, the Doctor tab's API keys panel (`keys-panel.js`, en/es), prompts in the plausibility card and the journals panel, hidden in snapshots — inline
- [x] T5 [S7] Leak hardening: archive and public-copy masking, journal error tail, experiments-tutor deny rule for a moved store, MCP bridge pin, forge `.gitignore` `.env*` — inline
- [ ] T6 [S1, S4, S6] Resolver `asta` + OpenAlex key + roles + migration + spec (S3 slice)
- [ ] T7 [S1, S4] journal-finder Asta provider (S3 slice)
- [ ] T8 [S1, S4] Asta MCP server in the four harnesses + the scout's gated grant (S4 slice)

## Log

- L1 (2026-11-09) Probed the live endpoint (initialize, tools/list: 8 tools incl. undocumented `get_paper_batch`; get_paper keyed/keyless/bogus key; searches keyless) and OpenAlex (keyless budget `x-ratelimit-limit-usd: 0.1`; bad `api_key` -> HTTP 401 pointing at https://openalex.org/settings/api-key).
- L2 Baseline: clean `main` in a worktree fails 9 tests that depend on the machine (the gate's `.micromamba` interpreter path, skill-audit's live `claude -p`, slot-queue golden timing, the wiring smoke). They fail identically with and without these changes.
