Add Pi (pi coding agent 1.4.0), PaperSmith's fourth harness, as Caztor's fifth chat provider, behind a "More" dropdown.
Branch: feat/pi-provider. Delivery: ask-on-risk. Test runner: `npx vitest run`, `npx tsc -b`, browser checks in `e2e/`.

## Specs

- S1: "que otros agentes tienen harnesses en papersmith? creo que pi? que otros? implementa todos los que tenga papersmith". PaperSmith supports Claude Code, OpenCode, Antigravity and Pi (`~/papersmith-ai/src/papersmith/core/manifest.py:186`). Pi is the only one missing, so Caztor adds Pi as provider `pi`.
- S2: "en la zona de selccion, deja los 4 que tenemos como principales y los otros en una barra desplegable". Claude, opencode, Codex and Antigravity stay as the radio buttons. Pi, and any later extra provider, is chosen from a dropdown next to them. When an extra provider is active, the dropdown shows it as selected.
- S3 (assumption, from the map): a turn runs `pi -p --mode json -na -ne --no-mcp -ns -np --no-themes -nc --offline --tools read,edit,write,grep,find,ls -xt 'mcp__*'`, with the agent prompt from a provisioned `.caztor/agents/pi.md` passed as `--system-prompt <file>` and `--append-system-prompt ""`. A runtime guard stops the turn on any tool outside that list. Isolation is partial (global settings and login load), with a notice like Antigravity's.
- S4 (assumption): sessions use `--session-id <uuid>` per conversation and `--session-dir <root>/.caztor/pi-sessions`.
- S5 (assumption): account mode uses Pi's own login (hint: run `pi`, then `/login`). API mode uses per-vendor slots like opencode (`pi:<vendor>`), given to the child as that vendor's env var, never as `--api-key`.
- S6 (assumption): failure is read from `message_end.stopReason` / `errorMessage` and `auto_retry_end`, not the exit code, which is 0 in json mode. Exit 1 with "No models available" means not signed in.
- S7 (assumption): Pi has no logo in the repository, so it shows its name.

## Tasks

- T1 S1 S3-S7 delegated (context backstop): core id, auth slots, agent target, `agents/pi.md`, provisioning, mapper, runner, server wiring, tests, README, specs.
- T2 S2 delegated with T1: the selector dropdown.
- T3 parent: assessment, independent verifier, browser check, report.

## Log

- L1 (2026-11-02): "que otros agentes tienen harnesses en papersmith? creo que pi? que otros? implementa todos los que tenga papersmith y en la zona de selccion, deja los 4 que tenemos como principales y los otros en una barra desplegable"
- L2 (2026-11-02): "dale, implementa pi"
- L3: Map facts: Pi 1.4.0 at /home/linuxbrew/.linuxbrew/bin/pi; docs in its package `docs/`. Nobody is signed in to Pi on this machine (`pi --list-models` prints "No models"), so no real turn can be run; fixtures follow docs/json.md and docs/message-types.md. Pi core has no agent files. JSON mode exits 0 on a failed response.
- L4 (2026-11-02, T1+T2 writer): implemented S1-S7. Pi is provider `pi` (core ids, `pi:<vendor>` slots, `.caztor/agents/pi.md` target), `agents/pi.md`, mapper and runner under `packages/adapters-local/src/providers/pi/`, server wiring, the "More providers" dropdown, README, PENDING and openspec. Deviation: api mode also sets `PI_CODING_AGENT_DIR` to an empty `.caztor/pi-agent-api`, so a saved login cannot win over the key (as opencode does). The API refusal messages now list all five providers. Checks: `npx vitest run` 3168 passed, `npx tsc -b` exit 0, web build ok, real Pi detection test passed. Next: T3.
- L5: Independent verifier: one blocker, fixed. Pi reads a positional argument starting with `@` as a file even after `--` (`dist/cli/args.js:24-27`), so a message like `@/etc/hosts` would have pulled in that file. The prompt now goes on stdin, which Pi uses as the message as it is (`dist/cli/initial-message.js`). Regression tests added. No second independent run.
