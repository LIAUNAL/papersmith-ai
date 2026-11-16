# The support terminal on a network bind, behind a login secret

Objective: `smith ui`'s support terminal (and the API-key routes behind its guard) can run on a non-loopback bind, but only behind real authentication; without the opt-in nothing changes and every missing or invalid auth state keeps the terminal off.
Branch: feat/network-terminal-auth (from main 0.73.0, worktree ../papersmith-ai-worktrees/network-terminal-auth). Delivery: ask-on-risk; the operator asked for a commit and a PR when done. Test runner: pytest (`.micromamba/envs/papersmith/bin/python -m pytest`) and node for the console harness.

## Specs

- S1 (Request) Let the support terminal work on a non-loopback bind only behind real authentication; do not simply remove the loopback guard. An opt-in flag enables it only when a secret is configured; without it the terminal stays disabled off loopback.
- S2 When enabled, the secret is required on every terminal route (start, input, resize, the SSE stream and the rest) and on the keys routes that share the guard, compared with `hmac.compare_digest`; a missing or wrong secret is refused with 401/403 and never logged.
- S3 A random secret is generated at start when none is supplied, printed once in the start banner, and reaches the browser as an HttpOnly, SameSite=Strict cookie after a one-time login step that redirects; never in the SSE URL or in logs.
- S4 The Host allow-list and the per-server cookie checks stay; an Origin check blocks cross-site state-changing terminal requests.
- S5 `--help` for `--no-terminal` and the new flag, the "Terminal disabled" message and the docs that describe a loopback-only terminal name the enabling flag.
- S6 The change lives in the upstream source, not in a workspace's copied `skills/` (which `smith upgrade` overwrites and `smith audit --check-drift` flags).
- S7 (design decision, security) The printed or file secret only logs in: `/api/terminal/login` trades it for a second secret, new at each start, that is the cookie. A long-lived file secret is never stored in a browser, and a cookie dies with its server.
- S8 (design decision) Over plain HTTP to a network address browsers send no `Sec-Fetch-Site`, so on a network bind a state-changing terminal request must carry this server's `Origin`. The page's self-activation (`POST /api/terminal/activate`) answers 403 there, and the browser `smith ui` opens gets the plain dashboard URL.
- S9 (design decision) `--terminal-token-file` follows the API keys' private-file rule (`skills/_core/api_keys.py`): a regular file owned by the user, not a symlink, mode 600, in a directory that is not a symlink, holding 32 to 256 URL-safe characters. Any other file, or `--network-terminal` beside `--no-terminal` or on a loopback host, exits 2.
- S10 (finding) On main, uvicorn's access log records the loopback login URL with its secret, `--log-level trace` logs the query string in each ASGI scope, and a terminal cookie with non-ASCII bytes answers 500 (`hmac.compare_digest` raises on non-ASCII str). All three are fixed on every bind.

## Tasks

- [x] T1 [S1, S6, S9] `--network-terminal` and `--terminal-token-file` in the server parser and `smith ui` (forwarded only when given; a relative token path read from the caller's directory), `resolve_terminal`, `read_login_token` — inline
- [x] T2 [S2, S7, S10] `TerminalManager.login_token` beside the per-start cookie `token`; `_same_secret` compares UTF-8 bytes and counts any odd value as a wrong secret; the login route sets the cookie and redirects — inline
- [x] T3 [S4, S8] `Origin` required on mutating terminal and key requests on a network bind; activation refused there; the browser opens the plain URL — inline
- [x] T4 [S3, S10] Start banner (one login URL per address a browser may use; a file secret never printed); `RedactLoginToken` on `uvicorn.access` and `uvicorn.asgi`, installed by the app at startup — inline
- [x] T5 [S5] Help texts, `cli.disabled` and `keys.unavailableHtml` (en, es), docs/terminals.md and docs/cli.md (plus three stale sentences saying non-loopback binds skip the Host check, wrong since #96) — inline
- [x] T6 [S1-S10] tests/test_command_center_network_terminal.py (31 tests); the terminal, office and console-activation tests follow the login/cookie split — inline

## Log

- L1 (2026-11-11) Baseline: clean main 0.73.0 fails 9 tests that depend on this machine (the wiring smoke, 5 forge-gate interpreter tests, 2 skill-audit, the slot-queue golden); the branch fails the same 9.
- L2 RED on main 9b9994b9, GREEN on the branch (real uvicorn on 127.0.0.1): the login secret appeared in `uvicorn.access` (`GET /api/terminal/login?token=<secret>`), now `token=[REDACTED]`; a non-ASCII terminal cookie on `GET /api/terminal/tools` answered 500, now 403.
- L3 Mutations: disabling each protection in turn (cookie check, Origin rule, access-log and trace redaction, the token URL kept from the browser, refused activation, cookie distinct from the login secret, terminal off without the opt-in, loose token file, file secret kept out of the banner) — all 11 caught by at least one test.
- L4 End to end: the real server bound to 0.0.0.0 inside an unprivileged network namespace (`unshare -rn`, so only the namespace's loopback), with a generated and with a file secret: 403 without the cookie or the Origin, 421 for a foreign Host, 303 on login, a session streamed its output; the generated secret appeared once in all output (the banner), the file secret never; access lines show `token=[REDACTED]`.
- L5 Tests: the related suites 381 passed; the full suite (`-n 8`) 10003 passed, 9 failed (the L1 set), 20 skipped.
- L6 Not verified: a browser on a second machine, Windows, HTTPS or a reverse proxy (the cookie has no `Secure` flag), a rate limit on the login route (none), the login URL left in browser history, cookies shared across ports of one host.
