# Provider Auth Specification

## Purpose

Per-provider authentication mode (`account` or `api`), a write-only credential store for API keys, and strict routing of each key to its own provider.

## Requirements

### Requirement: Auth mode per provider

Each provider MUST have an auth mode of `account` or `api`, chosen by the user and persisted per project. When no mode is stored for a provider (existing or new projects), the effective mode MUST be `account`. Antigravity MUST support `account` only.

#### Scenario: Default mode

- GIVEN a project with no stored mode for `claude`
- WHEN the mode is read
- THEN the effective mode is `account`

#### Scenario: Mode persists

- GIVEN the user selects `api` for `opencode`
- WHEN the project is reopened
- THEN `opencode` is still in `api` mode

#### Scenario: Antigravity API mode refused

- GIVEN the active provider is Antigravity
- WHEN `api` mode is requested
- THEN the request is rejected with a readable message and the mode stays `account`

### Requirement: API mode requires a stored key

A provider MUST NOT switch to `api` mode, and a turn in `api` mode MUST NOT start, unless a key is stored for that provider. Without a key, API mode MUST be reported as not configured and the turn refused with a readable message.

#### Scenario: Switch without key

- GIVEN no key is stored for `claude`
- WHEN the user switches `claude` to `api`
- THEN the switch is rejected and API mode is shown as not configured

#### Scenario: Turn without key

- GIVEN a project stored in `api` mode whose key was later deleted
- WHEN the user sends a message
- THEN no process starts and the chat shows a message asking for a key

### Requirement: Credential store

API keys MUST be stored only in a file with owner-only permissions (0600) inside a directory with owner-only permissions (0700) under the user's configuration area, outside every project. The directory and file MUST NOT be symbolic links. A key MUST NOT be stored in any project file.

#### Scenario: Key saved

- GIVEN no store exists
- WHEN the user saves a key
- THEN the directory is created as 0700 and the file as 0600
- AND no file inside the project contains the key

#### Scenario: Wrong permissions

- GIVEN the key file is readable by other users
- WHEN a key is read or saved
- THEN the operation is refused with a readable message and no key is used

#### Scenario: Symlinked store

- GIVEN the store directory or file is a symbolic link
- WHEN a key is read or saved
- THEN the operation is refused and nothing is written through the link

#### Scenario: Unreadable or corrupt file

- GIVEN the key file cannot be read or cannot be parsed
- WHEN a turn in `api` mode starts
- THEN the turn is refused with a readable message
- AND the file content is not shown or overwritten

### Requirement: Write-only exposure

The browser MUST receive, per provider, only whether a key is set and at most its last four characters. No route MUST return a stored key in full or in part beyond that.

#### Scenario: Status query

- GIVEN a stored key `sk-abcdef1234`
- WHEN the key status is requested
- THEN the response says it is set and shows at most `1234`

#### Scenario: Read-back attempt

- GIVEN a stored key
- WHEN any route, export, history entry or error response is inspected
- THEN the full key appears in none of them

#### Scenario: Key replaced and deleted

- GIVEN a stored key
- WHEN the user saves a new one or deletes it
- THEN the old value is no longer retrievable and status reflects the change

### Requirement: Redaction

A key MUST NOT appear in logs, diagnostics, chat history, snapshots, event streams or error details, including when a provider echoes it.

#### Scenario: Provider echoes key

- GIVEN a provider error message that contains the key
- WHEN the error is surfaced
- THEN the key is replaced by a mask in the chat, history and logs

#### Scenario: Failed save

- GIVEN saving a key fails
- WHEN the error is logged and shown
- THEN neither contains the key

### Requirement: Key routing

A key MUST be passed only to its own provider and, for `opencode`, only the key of the model's vendor. A key for one vendor MUST NOT reach another provider or vendor.

#### Scenario: Cross-vendor isolation

- GIVEN keys stored for `claude` and for an `opencode` vendor
- WHEN an `opencode` turn runs in `api` mode
- THEN only that vendor's key is in the child environment
- AND the `claude` key is absent

#### Scenario: Account mode passes no stored key

- GIVEN a stored key and `account` mode
- WHEN a turn runs
- THEN the stored key is not passed to the child

### Requirement: Account mode login guidance

In `account` mode the system MUST rely on the provider CLI's own login. When no CLI login exists, the turn MUST end with a readable error and the chat MUST show a hint naming the login step.

#### Scenario: No CLI login

- GIVEN `account` mode and the CLI is not logged in
- WHEN a turn runs and authentication fails
- THEN the chat shows a readable error and a login hint
- AND no stored key is used as a fallback
