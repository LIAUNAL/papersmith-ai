# Delta for Agent Chat

## ADDED Requirements

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

When Antigravity is active, the chat MUST show a permanent notice that its global configuration may be loaded and that isolation is partial.

#### Scenario: Notice visible

- GIVEN Antigravity is active
- WHEN the chat renders
- THEN the partial-isolation notice is visible and cannot be dismissed permanently

## MODIFIED Requirements

### Requirement: Provider header

The panel MUST show the active provider's CLI logo at its top, with a text fallback when the logo is unavailable. This applies to Antigravity as well. Logo assets MUST be the vendors' official, unmodified assets, and their origin MUST be recorded in a notice file. The provider name in text is shown only when the logo is unavailable.
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
