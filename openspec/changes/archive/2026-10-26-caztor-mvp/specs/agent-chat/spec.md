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

The panel MUST show the active provider's CLI logo at its top, with a text fallback when the logo is unavailable. Logo assets MUST be the vendors' official, unmodified assets, and their origin MUST be recorded in a notice file. The provider name in text is shown only when the logo is unavailable.

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
