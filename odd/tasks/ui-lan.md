# `smith ui --lan`: the dashboard and its terminal on the home network in one switch

Objective: an operator reaches the dashboard and its support terminal from the other machines on their network without naming the machine's address or managing a secret by hand, and nothing changes for anyone who does not ask for it.
Branch: feat/ui-lan (from main 2901217d, worktree ../papersmith-ai-worktrees/ui-lan). Delivery: ask-on-risk. Test runner: pytest (`.micromamba/envs/papersmith/bin/python -m pytest`).

## Specs

- S1 (Request) `smith ui` reachable from the other machines on the network with as little friction as possible: no address typed, no secret copied at each start.
- S2 (design decision, security) Opt-in only: `--lan`, or `PAPERSMITH_UI_LAN=1` as the default, `--no-lan` to override. Without it the argv to the backend is unchanged.
- S3 (design decision, security) The Host allow-list is never a wildcard: `--lan` adds this machine's own non-loopback addresses (link-local IPv6 excluded), its host name, `<hostname>.local` and the loopback names. A DNS-rebinding page arrives under its own name and still gets 421.
- S4 The terminal's login secret is kept in `~/.config/papersmith/terminal-token` (or `--terminal-token-file`), created once with `O_EXCL|O_NOFOLLOW`, mode 600 in a mode-700 folder, so it passes the backend's private-file rule; printed only at creation, inside the login URLs to bookmark; an existing file or symlink is never rewritten.
- S5 Only the wrapper changes (`src/papersmith/core/ui.py`); the backend and its checks stay as #176 left them, so a workspace needs no `smith upgrade`.

## Tasks

- [x] T1 [S1-S5] `--lan`, `lan_requested`, `default_token_file`, `ensure_token_file`, `machine_addresses`, `lan_hosts` in `src/papersmith/core/ui.py` — inline
- [x] T2 [S2-S4] `SmithUiLanTests` and `LanHostsTests` in tests/test_command_center_network_terminal.py — inline
- [x] T3 [S1] docs/cli.md (flag row and "One switch for your home network"), docs/terminals.md — inline

## Log

- L1 (2026-11-12) End to end inside `unshare -rn` (real `smith ui --lan` on the mvia workspace, two starts): token file 600 in a 700 folder; Host `intel2.local:8765` and `127.0.0.1:8765` 200, `evil.example:8765` 421; terminal tools 403 without login, wrong secret 403, right secret 303, then 200 with the cookie; the secret appears in the output only on the first start (two bookmark URLs), never on the second, never in argv.
- L2 Not verified: macOS and Windows address discovery (`ifconfig` fallback untested here), a browser on a second machine, `.local` resolution on the operator's other devices.
- L3 (2026-11-12) Operator asked for LAN, Tailscale and public reach with low friction. Added: the Tailscale MagicDNS name (`tailscale status --json`, Self.DNSName, checked as a DNS name) joins the Host list and the bookmarks; a warning on stderr when a public IPv4 is served on 0.0.0.0. Not done (security): public exposure of the unauthenticated dashboard over plain HTTP. Not verified: a running tailscaled (not running on this machine; parsing tested with a stubbed `tailscale`).
- L4 (2026-11-12) Operator report: a phone at 192.168.1.9 opened the plain `--lan` dashboard and the terminal stayed blank with "Could not open a browser here" (the activation answers 403 on a network bind, and a file secret is never printed). Added: `/api/terminal/agents` reports `network`; on a network bind the console shows a password form instead of Activate and posts the secret to `POST /api/terminal/login` (JSON body; same-origin, `Origin` required, 10 wrong secrets per minute then 429), which sets the same cookie. Tests: `PageLoginTests` (7) and two console harness tests; mutations (no Origin guard, no rate limit, no network branch) each caught. End to end in `unshare -rn` with the real server: no Origin 403, wrong 403, right 200 and the cookie authorizes; the secret never in the server output. Not verified: a real phone browser and its password manager.
