# Provider Auth Specification

## Purpose

Per-provider authentication mode (`account` or `api`), a write-only credential store for API keys, and strict routing of each key to its own provider.

## Requirements

### Requirement: Auth mode per provider

Each provider MUST have an auth mode of `account` or `api`, chosen by the user and persisted per project. When no mode is stored for a provider (existing or new projects), the effective mode MUST be `account`. Antigravity MUST support `account` only. Pi MUST support both.

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

#### Scenario: Login learned from turns

- GIVEN `account` mode
- WHEN a turn completes, or ends with an authentication error
- THEN the provider is listed as signed in, or as signed out, until the server stops

#### Scenario: No CLI login

- GIVEN `account` mode and the CLI is not logged in
- WHEN a turn runs and authentication fails
- THEN the chat shows a readable error and a login hint
- AND no stored key is used as a fallback

### Requirement: Pi keys per vendor

Pi's API keys MUST be kept per vendor in slots named `pi:<vendor>`, the vendor taken from the `provider/` prefix of the chosen model, for the vendors Caztor can map to Pi's environment variables (`anthropic`, `openai`, `google`, `openrouter`, `groq`, `xai`, `mistral`, `deepseek`, `cerebras`, `opencode`). In `api` mode a turn MUST give the key to the child only as that vendor's environment variable, never as `--api-key` or another argument, and MUST point Pi's agent folder at an empty one inside `.caztor`, so a saved login cannot win over the key. Without a model there is no vendor, so `api` mode MUST need a model.

#### Scenario: Key routed by vendor

- GIVEN Pi in `api` mode with the model `anthropic/claude-sonnet-4-5` and a key in `pi:anthropic`
- WHEN a turn starts
- THEN `ANTHROPIC_API_KEY` holds that key, no other vendor variable is set, and the key is in no argument

#### Scenario: No model in api mode

- GIVEN Pi in `api` mode and no model
- WHEN a turn is requested
- THEN no process starts and the turn ends with `model_required`

### Requirement: Keys and logins per person

The host's API keys MUST stay in `<config>/caztor/credentials.json`; a collaborator's MUST be in `<config>/caztor/users/<user id>/credentials.json` with the same rules (0700 folders, a 0600 file, no links, owned by the server's user). The provider listing, the auth-mode switch and the key routes MUST use the caller's own model, mode, keys and login state. A collaborator's turn MUST run with a private folder, `<config>/caztor/users/<user id>/home` (0700, never inside a project), as `HOME`, `CLAUDE_CONFIG_DIR=<home>/.claude`, `CODEX_HOME=<home>/.codex`, `XDG_CONFIG_HOME`, `XDG_DATA_HOME`, `XDG_STATE_HOME` and `XDG_CACHE_HOME` under it, and `PI_CODING_AGENT_DIR=<home>/.pi/agent`; for agy only `HOME`, with `DBUS_SESSION_BUS_ADDRESS` and `XDG_RUNTIME_DIR` removed. None of the host's login variables reach it. The host's turns MUST keep the server's environment unchanged.

#### Scenario: Separate keys

- GIVEN Ana stored a Claude key and the host did not
- WHEN each lists the providers
- THEN Ana sees her key as set (last four characters only) and the host sees none

#### Scenario: Private folder

- GIVEN a collaborator's first turn
- WHEN it starts
- THEN their private folder exists with mode 0700 outside every project and the CLI's HOME points at it

#### Scenario: Hostile user id

- GIVEN a user id such as `../x`, `a/b` or `host`
- WHEN it would name a history, key or private folder
- THEN it is refused and nothing is created

### Requirement: Browser sign-in per person

In account mode a person MUST be able to sign in to a provider's CLI from the browser. The server runs the CLI's own login and relays its text: for a collaborator inside their sandbox with their private folder as `HOME` and every CLI's config folder, for the host without a sandbox, with the server's environment, from a fresh empty folder of its own. The commands are `claude auth login --claudeai` (no terminal, pasted code on stdin), `codex login --device-auth` (no terminal, device code), `opencode auth login -p openai -m "ChatGPT Pro/Plus (headless)"` (no terminal, device code) or opencode's own menu in a terminal, `pi` in a terminal made by util-linux `script` with `/login` typed once it is quiet, and `agy` in a terminal (signed out it starts with its login menu). Each person MUST have at most one sign-in at a time; starting another MUST end the first, also when both start at once. Only its owner MUST see, feed or cancel it. A sign-in MUST end after 10 minutes, and when nobody follows it for a minute. An input line MUST be at most 2048 characters with no control characters. A pasted line MUST never be shown back, and known token and key shapes MUST be masked. When the CLI exits 0 (Pi: when it writes its `auth.json`; agy: when `agy models` succeeds in the same sandbox) the login state of that person and provider MUST become `signed_in`.

#### Scenario: Collaborator signs in to Claude

- GIVEN a collaborator in account mode for `claude`
- WHEN they choose Sign in, open the relayed link and paste the code
- THEN `claude auth login --claudeai` runs in bubblewrap with their private home, the code reaches its stdin, the code is not shown back, and on exit 0 their login is `signed_in` while the host's is unchanged

#### Scenario: Device code shown

- GIVEN a collaborator signs in to `codex`
- WHEN the CLI prints its one-time code
- THEN the dialog shows the code with a copy button and the link opens in a new tab with `rel="noopener"`

#### Scenario: One sign-in per person, owner only

- GIVEN Ana has a sign-in running
- WHEN Bo or the host asks for it, sends to it or cancels it
- THEN they get nothing of it (no sign-in, or 404)
- AND when Ana starts another sign-in, the first one's process group is signalled

#### Scenario: Unattended sign-in ends

- GIVEN a sign-in nobody answers
- WHEN 10 minutes pass, or a minute passes with nobody following it
- THEN the process group gets SIGTERM, then SIGKILL, and the login state does not change

#### Scenario: No sandbox

- GIVEN the server cannot sandbox a collaborator (no bwrap, or the probe fails)
- WHEN the collaborator starts a sign-in
- THEN it is refused with `isolation_failed` and nothing runs

#### Scenario: Host sign-in

- GIVEN the host chooses Sign in
- WHEN the sign-in starts
- THEN the CLI runs without a sandbox, with the server's environment, in a fresh empty folder made for it (0700, under `$TMPDIR` or `/tmp`) and removed once it ends, never the project folder a collaborator's turn can write; the terminal hint stays shown as a fallback

### Requirement: Trust of a project's CLI configuration is the host's

The record of the host's confirmation of a project's CLI configuration MUST be an HMAC of the provider, the project path and the files' fingerprint with a key kept in `<config>/caztor/trust.key` (600, outside every project, never mounted). A plain fingerprint, a record of the old format or one sealed for another project MUST NOT count. Only the host MAY confirm; a collaborator MUST get 403 `host_only`.

#### Scenario: Forged trust record

- GIVEN a project whose `opencode.json` can run programs
- WHEN someone who can write the project stores the files' plain fingerprint in `.caztor/state.json`
- THEN the configuration is still shown as not confirmed and the host's turn is refused with `isolation_failed`
