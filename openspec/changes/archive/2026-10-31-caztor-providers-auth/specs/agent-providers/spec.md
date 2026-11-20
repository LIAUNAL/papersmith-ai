# Delta for Agent Providers

## ADDED Requirements

### Requirement: Child environment per auth mode

The environment of each provider process MUST be built from the provider's auth mode. In Claude `account` mode the variables `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN` and `ANTHROPIC_BASE_URL` MUST be removed, even when exported in the server environment, so a subscription is never silently overridden. In `api` mode only the key stored for that provider (for `opencode`, the model vendor's key) MUST be added. Keys of other vendors MUST NOT be passed.

#### Scenario: Exported key in account mode

- GIVEN `ANTHROPIC_API_KEY` is exported in the server environment and Claude is in `account` mode
- WHEN a turn starts
- THEN the child environment contains none of the three variables

#### Scenario: Claude API mode

- GIVEN Claude is in `api` mode with a stored key
- WHEN a turn starts
- THEN the child receives that key and no other vendor's key

#### Scenario: opencode vendor key only

- GIVEN `opencode` in `api` mode with a model of vendor A and keys stored for A and B
- WHEN a turn starts
- THEN only A's key is in the child environment

### Requirement: Antigravity provider

The system MUST offer Antigravity (`agy`) as a fourth provider with account login only, mapped to the normalized event model. It MUST be detected like other providers and, when its CLI is not installed or not signed in, MUST appear unavailable with a clear reason.

#### Scenario: Antigravity listed

- GIVEN `agy` is installed and signed in
- WHEN the selector renders
- THEN Antigravity is selectable

#### Scenario: Not installed

- GIVEN `agy` is not installed
- WHEN the selector renders
- THEN Antigravity is unavailable with a "not installed" reason and the others work

#### Scenario: Not signed in

- GIVEN `agy` is installed without a login
- WHEN a turn is requested
- THEN the turn is refused or ends failed with a readable login hint

#### Scenario: Normalized turn

- GIVEN a successful Antigravity turn
- WHEN events are normalized
- THEN text, tool activity, file edits and completion appear as in other providers

### Requirement: Antigravity partial isolation

Antigravity MUST be run with file read and edit tools only and MUST be isolated from global configuration as far as the CLI allows. Because the CLI can load global configuration, the isolation MUST be reported as partial, with a permanent notice, whenever Antigravity is active.

#### Scenario: Global configuration loaded

- GIVEN the user has global Antigravity configuration
- WHEN a turn starts
- THEN the turn runs with the partial-isolation notice shown
- AND file read and edit tools only are requested

#### Scenario: Notice always present

- GIVEN any Antigravity turn
- WHEN the chat is shown
- THEN the notice is visible

### Requirement: Antigravity tool guard

If Antigravity reports a tool outside the file read and edit set, the turn MUST be aborted with a readable error and the process terminated.

#### Scenario: Disallowed tool reported

- GIVEN Antigravity reports a tool step outside the allowed set, including one with no clear name (the tools listed by its `init` event are not used, because real runs list `run_command` regardless of the definition)
- WHEN the report is received
- THEN the turn is aborted with a readable error

#### Scenario: Allowed tools only

- GIVEN Antigravity reports only read and edit tools
- WHEN the turn runs
- THEN the turn proceeds normally

## MODIFIED Requirements

### Requirement: Provider detection

The system MUST detect which provider CLIs are installed and list `opencode`, `claude`, `codex`, `antigravity` as selectable. An uninstalled provider MUST be shown as unavailable with a clear reason and MUST NOT break the app. Availability in `api` mode MUST depend on a stored key, and in `account` mode on the CLI only.
(Previously: three providers and no mode-dependent availability)

#### Scenario: Codex missing

- GIVEN `codex` is not installed
- WHEN the selector renders
- THEN `codex` appears unavailable with a "not installed" reason and cannot start a turn
- AND the other providers work normally

#### Scenario: API mode without key

- GIVEN a provider in `api` mode with no stored key
- WHEN the selector renders
- THEN API mode is shown as not configured and no turn starts

### Requirement: Isolation from global configuration

Provider CLIs MUST run without the user's global hooks, MCP servers and global instruction files, and with file read and edit tools only, where the CLI supports it. When isolation cannot be applied, or can be applied only in part, the chat MUST show a notice.
(Previously: no case for partial isolation)

#### Scenario: Isolated run

- GIVEN a supporting CLI and global hooks configured by the user
- WHEN a turn runs
- THEN no global hook, MCP server or global instruction file is loaded
- AND only file read and edit tools are available

#### Scenario: Isolation unavailable

- GIVEN a CLI that cannot be isolated
- WHEN a turn starts
- THEN the chat shows a notice that isolation is not applied

#### Scenario: Isolation partial

- GIVEN a CLI whose isolation is partial
- WHEN a turn starts
- THEN the chat shows a notice stating what is not isolated

### Requirement: Isolation violation

If a provider reports a tool outside the allowed set at turn start, the turn MUST be aborted with a readable error. This applies to every provider including Antigravity.
(Previously: did not name Antigravity)

#### Scenario: Unexpected tool

- GIVEN the provider reports a shell tool at turn start
- WHEN the report is received
- THEN the turn is aborted with a readable error

### Requirement: Project CLI configuration

If the fallback isolation level would run hooks or MCP servers defined in the project, the system MUST ask for confirmation once per project before the first turn. For Antigravity, if the project's `.agents/` directory contains configuration that can run programs (hooks, MCP servers, commands), the system MUST ask for confirmation once per project before the first turn.
(Previously: no Antigravity trust gate)

#### Scenario: Project hooks

- GIVEN fallback isolation and project-defined hooks
- WHEN the first turn is requested
- THEN the user is asked to confirm, and the turn runs only after confirmation

#### Scenario: Already confirmed

- GIVEN the user confirmed for this project
- WHEN a later turn starts
- THEN no confirmation is requested

#### Scenario: Executable `.agents/` configuration

- GIVEN a project whose `.agents/` defines a program-running hook or server
- WHEN the first Antigravity turn is requested
- THEN the user is asked to confirm and the turn does not run until confirmed

#### Scenario: Gate declined

- GIVEN the user declines the confirmation
- WHEN the request is handled
- THEN no process starts and the chat states why

#### Scenario: Inert `.agents/`

- GIVEN `.agents/` contains only Caztor's definition
- WHEN the first Antigravity turn is requested
- THEN no confirmation is requested
