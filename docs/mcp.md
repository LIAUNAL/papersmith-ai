# PaperSmith as an MCP server

`smith mcp serve` exposes the workspace orchestrator and the paper-writing
verbs to any Model Context Protocol host over stdio. It is a thin projection:
every tool wraps an existing `smith` CLI contract, so nothing is
reimplemented and no new runtime dependency is added.

## Requirements

- Python 3.11 or newer.
- `smith` on `PATH` (`pipx install git+https://github.com/LIAUNAL/papersmith-ai.git`,
  always the latest `main`, or the workspace's own environment).
- An initialized workspace. The server binds to one workspace root, and every
  path argument it accepts must resolve inside that root.

## The lab bank (`banco-lia`)

`smith init` and `smith upgrade` register the lab's article and project bank
([LIAUNAL/bancoProyectosPapersLIA](https://github.com/LIAUNAL/bancoProyectosPapersLIA))
for every declared harness, served by `uvx --from
git+https://github.com/LIAUNAL/bancoProyectosPapersLIA banco-lia-mcp`:

| Harness | File | Entry |
|---|---|---|
| Claude Code | `.mcp.json` | `mcpServers.banco-lia` (`type: stdio`) |
| OpenCode | `opencode.json` | `mcp.banco-lia` (`type: local`) |
| Pi | `.pi/mcp.json` | `mcpServers.banco-lia` |
| Antigravity / agy | `.agents/mcp_config.json` | `mcpServers.banco-lia` |

`.mcp.json`, `.pi/mcp.json` and `.agents/mcp_config.json` belong to the
workspace: upgrade adds or refreshes only the `banco-lia` entry and keeps every
other server. A file that is not valid JSON is left untouched and reported as a
warning. `opencode.json` is a rendered file, so upgrade rewrites it whole.
The `papersmith` server itself is never written to any of them; use
`smith mcp print-config` for it. `uv` must be on `PATH` for the harness to
start the bank.

## Wiring

The server is launched by the client as a subprocess; there is nothing to run
by hand. `smith mcp print-config` emits the snippet for the host you are
configuring, with the bound workspace filled in — treat its output as
authoritative.

### Claude Code (`.mcp.json`)

```json
{
  "mcpServers": {
    "papersmith": {
      "command": "smith",
      "args": ["mcp", "serve", "--workspace", "/path/to/your/workspace"]
    }
  }
}
```

### OpenCode (`opencode.json`)

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "papersmith": {
      "type": "local",
      "command": ["smith", "mcp", "serve", "--workspace", "/path/to/your/workspace"],
      "enabled": true
    }
  }
}
```

### Antigravity CLI / agy (`.agents/mcp_config.json` or `~/.gemini/config/mcp_config.json`)

```json
{
  "mcpServers": {
    "papersmith": {
      "command": "smith",
      "args": ["mcp", "serve", "--workspace", "/path/to/your/workspace"]
    }
  }
}
```

Or register via CLI:
```bash
agy mcp add papersmith -- smith mcp serve --workspace /path/to/your/workspace
```

## Protocol

- Revision `2026-07-28`, with `2025-11-25` accepted for compatibility. Any other
  requested revision is refused with JSON-RPC error `-32022`, carrying the
  supported list and the revision that was requested.
- Transport: stdio, UTF-8, newline-delimited JSON-RPC 2.0 — one message per
  line. stdout is the wire and carries nothing else.
- `server/discover` is implemented; `initialize` is answered for clients that
  still open with it.

## Tools

`readOnlyHint` is a hint, not an enforcement: hosts must treat annotations from
any server as advisory. It is still set honestly here, so a client can label
and auto-approve sensibly.

### Read-only

| Tool | What it wraps | readOnly | destructive | openWorld |
|---|---|---|---|---|
| `papersmith.workspace_status` | `smith status --json` | ✅ | — | — |
| `papersmith.workspace_audit` | `smith audit --check-drift`; reports drift, never repairs it | ✅ | — | — |
| `papersmith.ingest_fragment` | `pdf_fragment.py`: one page, heading section, display equation (LaTeX), search hits or the outline of an ingested paper, never the whole document | ✅ | — | — |
| `papersmith.target_list` | configured compute targets | ✅ | — | — |
| `papersmith.target_check` | target connectivity — runs `ssh` for a remote-ssh target | ✅ | — | ✅ |
| `papersmith.paper_status` | the paper's block table | ✅ | — | — |
| `papersmith.paper_contract` | the section corpus, or one file's parsed header | ✅ | — | — |
| `papersmith.paper_readiness` | per-block writable/blocked state | ✅ | — | — |
| `papersmith.paper_order` | the writing order from the block graph | ✅ | — | — |
| `papersmith.paper_observe` | validate an insumos-observer report; never writes | ✅ | — | — |
| `papersmith.paper_plan` | guidance classes, declaration/fact fill state, provenance | ✅ | — | — |
| `papersmith.paper_verify` | couplings, citation integrity, contract currency | ✅ | — | — |
| `papersmith.paper_phases` | what can I write now — waves with per-block readiness, opened, provenance | ✅ | — | — |
| `papersmith.paper_packet` | one block's own contract prose plus reference heading outlines, plus its bound source sections | ✅ | — | — |
| `papersmith.paper_reuse` | which already-ingested, evidence-classed papers carry no verdict for one block's open claims | ✅ | — | — |
| `papersmith.paper_exhaustion` | corpus-wide exhaustion state — lists only, never deletes | ✅ | — | — |

### Mutating

| Tool | What it wraps | readOnly | destructive | openWorld |
|---|---|---|---|---|
| `papersmith.workspace_init` | create a workspace under the bound root; skips npm and the environment download unless asked | — | — | ✅ |
| `papersmith.workspace_upgrade` | sync framework files, preserving all research artifacts | — | ✅ | — |
| `papersmith.target_set` | persist the default compute target | — | — | — |
| `papersmith.ingest_add` | ingest a PDF or URL; long-running, may download model weights the first time a page needs the heavy engine | — | — | ✅ |
| `papersmith.paper_scaffold` | create/re-enter `paper/` idempotently | — | — | — |
| `papersmith.paper_open` | insert an empty block pair | — | — | — |
| `papersmith.paper_substitute` | replace one block's body, or adopt a hand edit | — | ✅ | — |
| `papersmith.paper_declare` | record a declaration or fact resolution | — | — | — |
| `papersmith.paper_bib_build` | rebuild `paper/refs.bib` from cached metadata | — | — | — |
| `papersmith.paper_write` | judge an already-drafted, already-audited block | — | ✅ | — |
| `papersmith.paper_place` | place an already-measured figure's PDF | — | — | — |
| `papersmith.paper_validate` | the citation gate: submit one verdict, write on success | — | ✅ | — |
| `papersmith.paper_skeleton` | open the empty section/block structure from two structural decisions | — | — | — |
| `papersmith.paper_bind` | record which source sections feed one block's bindable requirement, or reopen a binding | — | — | — |
| `papersmith.paper_mark_revisions` | record a source root's revision rule | — | — | — |
| `papersmith.paper_mark_class` | record a `guidance/` folder's class | — | — | — |
| `papersmith.paper_separate` | score a proposed source-section cut; records the separation round on success | — | — | — |
| `papersmith.paper_full_text` | fetch one already-resolved identifier's PDF into `guidance/<section>/` | — | — | ✅ |
| `papersmith.paper_couplings` | validate and write `paper/couplings.json` whole; `--file -` is refused over MCP | — | — | — |
| `papersmith.deliberate` | the deterministic proposal-deliberation engine | — | — | — |
| `papersmith.implement` | the proposal-implementation harness | — | ✅ | — |
| `papersmith.run` | an execution profile — planning only unless consented | — | — | ✅ |
| `papersmith.remote` | remote-execution pack/push/status/pull/sync | — | ✅ | ✅ |

`papersmith.paper_validate` is **not** read-only: it appends an evidence record
when a claim is given and substitutes the block body once every claim is
satisfied. `papersmith.paper_resolve` and `papersmith.paper_render` are
deliberately not exposed — `resolve` reaches the network and `render` shells out
to `latexmk`. `papersmith.paper_full_text` is the one exposed paper tool that
reaches the network: it fetches one already-resolved identifier's PDF into
`guidance/<section>/`, so its `openWorld` hint is set.

## Resources

| URI | What it serves |
|---|---|
| `papersmith://workspace/status` | machine-readable workspace snapshot |
| `papersmith://workspace/config` | the workspace's `papersmith.yaml`, secret-shaped values redacted |
| `papersmith://workspace/runs` | the runs ledger tail, with `command` redacted |
| `papersmith://paper/blocks` | the paper's block table |
| `papersmith://paper/contract` | the section corpus contract |
| `papersmith://paper/plan` | guidance, declarations and provenance state |
| `papersmith://paper/refs` | the paper's own `paper/refs.bib` |

The runs resource redacts the ledger's `command` field because the orchestrator
records a remote dispatch command verbatim, including its `--consent` operand.

## Safety model

- **One bound root.** Every path argument is resolved and must stay inside the
  workspace; anything else is refused `WORKSPACE_ESCAPE`. Resources take no
  caller-supplied path at all.
- **Declared types, checked first.** Every argument must match the type its
  schema declares (`"false"` is not a boolean, `true` is not an integer) and
  any declared `enum`; anything else is refused `INVALID_ARGUMENT` before argv
  is built, so no child runs.
- **Closed stdin.** Children are spawned with `stdin` closed, so `--body -` is
  refused `STDIN_NOT_AVAILABLE_OVER_MCP` rather than reading the JSON-RPC wire.
- **Captured stdout.** A child's stdout can never reach the wire.
- **Environment allowlist, deny-wins.** A token-shaped name is dropped even when
  a broader allow prefix would match it.
- **Consent is never implied.** A non-dry `papersmith.run` and a
  `papersmith.remote` push are refused `CONSENT_REQUIRED` without an explicit
  consent token. Planning (`--dry-run`) is the default.
- **No network listener.** stdio only. There is no HTTP transport and no auth
  layer, because there is no socket to reach.
- **Fail-closed refusals keep their own name.** A skill script's refusal code
  (`RESOLVER_UNREACHABLE`, `PAPER_ABSENT`, …) is preserved verbatim rather than
  flattened into a generic error.

## Verifying a build

```bash
smith mcp inspect          # the capability catalog as JSON — the source of truth
smith mcp print-config     # the wiring snippet for the bound workspace
pytest tests/test_mcp_*.py      # protocol, seam guard, drift, confinement, wiring
```

`smith mcp inspect` is what this document's tool list is checked against:
a drift test fails if the two disagree.
