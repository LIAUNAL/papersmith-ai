# Agent Providers Specification

## Purpose

Selecting and running the `opencode`, `claude` and `codex` CLIs behind one normalized event model.

## Requirements

### Requirement: Provider detection

The system MUST detect which provider CLIs are installed and list `opencode`, `claude`, `codex` as selectable. An uninstalled provider MUST be shown as unavailable with a clear reason and MUST NOT break the app.

#### Scenario: Codex missing

- GIVEN `codex` is not installed
- WHEN the selector renders
- THEN `codex` appears unavailable with a "not installed" reason and cannot start a turn
- AND the other providers work normally

### Requirement: Provider selection

The user MUST be able to switch the active provider; the choice MUST persist per project.

#### Scenario: Switch provider

- GIVEN `claude` is active
- WHEN the user selects `opencode`
- THEN the header and next turn use `opencode`

### Requirement: Normalized events

Every provider MUST be mapped to one event model covering text output, tool activity, file edits, errors and turn completion, so the chat is provider-agnostic.

#### Scenario: Equivalent turns

- GIVEN the same prompt run on `claude` and `opencode`
- WHEN events are normalized
- THEN both yield the same event kinds despite different delivery granularity

#### Scenario: Unknown event

- GIVEN a provider emits an unrecognized event
- WHEN it is received
- THEN it is ignored without ending the turn

### Requirement: Per-provider model setting

The user MUST be able to set a model per provider. `opencode` MUST NOT start a turn without an explicit model. A model value MUST be validated before use and MUST be rejected when it could be read as a command-line option.

#### Scenario: opencode without model

- GIVEN no model is set for `opencode`
- WHEN the user sends a message
- THEN the turn is not started and the user is asked to set a model

#### Scenario: Option-like model

- GIVEN a model value beginning with `--`
- WHEN the user saves it
- THEN it is rejected with a readable message

### Requirement: Error surfacing

Rejected models, authentication failures, crashes and malformed output MUST end the turn with a readable error event. A turn that ends without a completion event, or produces repeated unparseable output, MUST end failed with a readable error.

#### Scenario: Auth failure

- GIVEN the provider reports an authentication failure
- WHEN the turn runs
- THEN the chat shows a readable error and the turn ends failed

#### Scenario: Abrupt exit

- GIVEN the CLI exits non-zero without a completion event
- WHEN the process ends
- THEN the turn ends failed with a readable message

#### Scenario: Unparseable output

- GIVEN a provider repeatedly emits unparseable output
- WHEN the repetition threshold is reached
- THEN the turn ends failed with a readable error

### Requirement: Isolation from global configuration

Provider CLIs MUST run without the user's global hooks, MCP servers and global instruction files, and with file read and edit tools only, where the CLI supports it. When isolation cannot be applied, the chat MUST show a notice.

#### Scenario: Isolated run

- GIVEN a supporting CLI and global hooks configured by the user
- WHEN a turn runs
- THEN no global hook, MCP server or global instruction file is loaded
- AND only file read and edit tools are available

#### Scenario: Isolation unavailable

- GIVEN a CLI that cannot be isolated
- WHEN a turn starts
- THEN the chat shows a notice that isolation is not applied

### Requirement: Isolation violation

If a provider reports a tool outside the allowed set at turn start, the turn MUST be aborted with a readable error.

#### Scenario: Unexpected tool

- GIVEN the provider reports a shell tool at turn start
- WHEN the report is received
- THEN the turn is aborted with a readable error

### Requirement: Project CLI configuration

If the fallback isolation level would run hooks or MCP servers defined in the project, the system MUST ask for confirmation once per project before the first turn.

#### Scenario: Project hooks

- GIVEN fallback isolation and project-defined hooks
- WHEN the first turn is requested
- THEN the user is asked to confirm, and the turn runs only after confirmation

#### Scenario: Already confirmed

- GIVEN the user confirmed for this project
- WHEN a later turn starts
- THEN no confirmation is requested

### Requirement: Codex command execution

The product MUST disclose that Codex can execute commands inside its own sandbox.

#### Scenario: Codex disclosure

- GIVEN `codex` is selected
- WHEN the chat is shown
- THEN a disclosure states that Codex can execute commands inside its own sandbox

### Requirement: Safe process launch

Providers MUST be launched without a shell, with arguments passed as discrete values, in the project directory.

#### Scenario: Metacharacters

- GIVEN a prompt containing `; rm -rf ~`
- WHEN the turn starts
- THEN the text is delivered as data and no shell interprets it
