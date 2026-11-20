# Agent Chat Specification

## Purpose

The chat panel for conversing with a provider agent that edits the project.

## Requirements

### Requirement: Designed message UI

The chat MUST present messages in a designed UI consistent with the page and MUST NOT be styled as a terminal.

#### Scenario: Message rendering

- GIVEN an exchange of user and agent messages
- WHEN rendered
- THEN messages appear as styled bubbles or blocks with no terminal prompt, cursor or raw escape output

### Requirement: Provider header

The panel MUST show the active provider's CLI logo at its top, with a text fallback when the logo is unavailable. This applies to Antigravity and Pi as well. Logo assets MUST be the vendors' official, unmodified assets, and their origin MUST be recorded in a notice file. The provider name in text is shown only when the logo is unavailable.
(Previously: did not name Antigravity)

#### Scenario: Logo shown

- GIVEN the logo asset loads
- WHEN the header renders
- THEN the logo is shown and the provider name is not repeated as text

#### Scenario: Logo fallback

- GIVEN the logo asset fails to load
- WHEN the header renders
- THEN the provider name is shown as text

#### Scenario: Asset origin recorded

- GIVEN the shipped logo assets
- WHEN the notice file is checked
- THEN it records the origin of each asset

#### Scenario: Antigravity header

- GIVEN Antigravity is active
- WHEN the header renders
- THEN its logo is shown, or its name as text when no logo asset is shipped

### Requirement: Streaming at any granularity

The chat MUST render incremental agent output both as token-level deltas and as whole text parts, without loss, duplication or reordering.

#### Scenario: Token deltas

- GIVEN the provider emits small text deltas
- WHEN they arrive
- THEN the message grows progressively and the final text equals their concatenation

#### Scenario: Whole parts

- GIVEN the provider emits complete text parts
- WHEN each arrives
- THEN it appears as a whole and the final text is complete

### Requirement: Tool activity cards

Tool use MUST appear as cards showing the tool name, target and status (running, done, failed).

#### Scenario: File edit card

- GIVEN the agent edits `main.tex`
- WHEN the event arrives
- THEN a card shows the edit and its status

### Requirement: Stop

The user MUST be able to stop a running turn; the agent process MUST terminate and the turn MUST end as cancelled.

#### Scenario: Stop mid-turn

- GIVEN a turn is running
- WHEN the user presses Stop
- THEN the process ends and the turn is marked cancelled

### Requirement: Session continuity

Follow-up messages MUST continue the same provider conversation until the user starts a new chat.

#### Scenario: Follow-up

- GIVEN a completed turn
- WHEN the user sends another message
- THEN the agent has the prior context

#### Scenario: New chat

- GIVEN an existing conversation
- WHEN the user starts a new chat
- THEN no prior context is carried over

### Requirement: Readable errors and busy state

Provider failures MUST appear in the chat as readable messages. While a turn runs, sending MUST be disabled.

#### Scenario: Provider error

- GIVEN the provider rejects the request
- WHEN the error event arrives
- THEN the chat shows its message in plain language and the turn ends as failed

#### Scenario: Send while busy

- GIVEN a turn is running
- WHEN the user sends another message
- THEN the send action is disabled and no second turn starts

### Requirement: Changed-files summary

Each finished turn MUST show its changed files, or "No files changed", and MUST show an undo action only for the undoable turn.

#### Scenario: Summary with undo

- GIVEN the latest turn changed `a.tex`
- WHEN it finishes
- THEN the chat lists `a.tex` and shows an undo action

#### Scenario: No changes

- GIVEN a turn changed nothing
- WHEN it finishes
- THEN the chat shows "No files changed" and no undo action

#### Scenario: Older turn

- GIVEN a turn that is not the undoable one
- WHEN the chat renders
- THEN that turn shows no undo action

### Requirement: Chat history

The chat MUST restore the visible conversation for the active provider after a page reload. A dropped connection MUST NOT stop a running turn.

#### Scenario: Reload

- GIVEN a conversation with `claude`
- WHEN the page is reloaded
- THEN the visible conversation is restored

#### Scenario: Connection drop

- GIVEN a turn is running
- WHEN the connection to the page drops and returns
- THEN the turn kept running and its output is shown

### Requirement: Auth mode toggle

The chat MUST show, for the active provider, its auth mode and let the user switch between `account` and `api`. Antigravity MUST show `account` only. A mode that cannot be used (API without key) MUST be shown as not configured.

#### Scenario: Switch to API with key

- GIVEN a key is stored for the active provider
- WHEN the user selects `api`
- THEN the chat shows API mode as active

#### Scenario: API not configured

- GIVEN no key is stored
- WHEN the toggle renders
- THEN API mode is marked not configured and selecting it prompts for a key

#### Scenario: Antigravity toggle

- GIVEN Antigravity is active
- WHEN the toggle renders
- THEN only account mode is offered

### Requirement: Masked key form

The chat MUST offer a masked, write-only key form per provider that shows only set or not set and at most the last four characters, and lets the user replace or delete the key. The field MUST NOT be pre-filled and the key MUST be cleared from the page after submission.

#### Scenario: Saved key display

- GIVEN a key was saved
- WHEN the form renders
- THEN it shows "set" and at most the last four characters, with an empty field

#### Scenario: Submission clears field

- GIVEN the user submits a key
- WHEN the request completes, successfully or not
- THEN the field is emptied and the key is not shown in any message

### Requirement: Login hints

In `account` mode the chat MUST show a hint naming how to sign in to the provider's CLI when no login is detected.

#### Scenario: Hint shown

- GIVEN `account` mode and no CLI login
- WHEN the chat renders or a turn fails for authentication
- THEN a hint explains the CLI login step

### Requirement: Partial-isolation notice

When Antigravity or Pi is active, the chat MUST show a permanent notice that its global configuration may be loaded and that isolation is partial.

#### Scenario: Notice visible

- GIVEN Antigravity is active
- WHEN the chat renders
- THEN the partial-isolation notice is visible and cannot be dismissed permanently

### Requirement: More providers dropdown

The selector MUST show Claude Code, opencode, Codex and Antigravity as radio buttons, and every other provider (Pi, and any later one) in an accessible "More providers" dropdown next to them. When an extra provider is active, the dropdown MUST show it as selected and no radio is checked. The arrow keys MUST move only among the radio buttons. Pi has no logo in the repository, so its name is shown as text.

#### Scenario: Choosing Pi

- GIVEN Claude Code is active
- WHEN the user picks Pi in the dropdown
- THEN Pi becomes the active provider

#### Scenario: Pi active

- GIVEN Pi is active
- WHEN the selector renders
- THEN the dropdown shows Pi and no radio is checked

### Requirement: Chat per person

Each person MUST have their own chat history, agent sessions and provider and model choice in a shared project. The host's MUST stay where a single-user project keeps them (`.caztor/chat/<provider>.jsonl` and the top-level fields of `.caztor/state.json`), so a project only the host uses is unchanged on disk; a collaborator's MUST be in `.caztor/chat/<user id>/<provider>.jsonl` and under `users.<user id>` in the state file. A user id MUST be one plain segment wherever it names a path. A project MUST run one turn at a time, whoever runs it. Snapshots MUST stay shared, since the files are.

#### Scenario: Separate conversations

- GIVEN the host and two collaborators in one project
- WHEN each sends a message
- THEN each one's history and resumed session are only their own

#### Scenario: Someone else's turn

- GIVEN Ana's turn is running
- WHEN another person sends a message, or stops or follows Ana's turn
- THEN it is refused with "Ana has a turn running. Wait for it to finish."

#### Scenario: Undo of someone else's turn

- GIVEN Ana's turn ended and is the latest one
- WHEN another person undoes it
- THEN nothing is restored and the answer says that only Ana can undo it
- AND the history of the others offers no undo for it

#### Scenario: Old state file

- GIVEN a state file written before collaborators existed
- WHEN the project opens
- THEN it loads unchanged, and saving the host's choices writes no `users` key
