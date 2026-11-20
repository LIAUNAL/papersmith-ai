# Delta for Agent Definitions

## ADDED Requirements

### Requirement: Writing guide core

The shared section of every definition MUST contain a compact advisory writing core that points to `.caztor/guides/INDEX.md`. The shared section MUST be byte-identical across all definitions.

#### Scenario: Identical core

- GIVEN the three definitions
- WHEN their shared sections are compared
- THEN they are byte-identical and include the core and the pointer

### Requirement: Guide read exception

Every definition MUST allow reading `.caztor/build/last-compile.log` and files under `.caztor/guides/`, both read-only, and MUST NOT grant any other access under `.caztor/`.

#### Scenario: Guide read allowed

- GIVEN a definition
- WHEN its text is checked
- THEN reading `.caztor/guides/` is permitted and writing there is not

#### Scenario: Compile log still readable

- GIVEN a definition
- WHEN its text is checked
- THEN reading `.caztor/build/last-compile.log` is permitted and writing it is not

#### Scenario: Other internal state

- GIVEN a definition
- WHEN its text is checked
- THEN no other `.caztor/` path is readable or writable

### Requirement: Definition size bound

Every definition MUST be smaller than 32 KiB.

#### Scenario: Within bound

- GIVEN any definition
- WHEN its size is measured
- THEN it is under 32768 bytes

#### Scenario: Over bound

- GIVEN a definition at or above 32768 bytes
- WHEN the size check runs
- THEN the check fails naming the definition

## MODIFIED Requirements

### Requirement: Provisioning

The system MUST provision a provider's definition into the project in the location that provider reads, and MUST be idempotent. Provisioning MUST run when a turn starts for a provider, MUST write only that provider's definition (plus the shared writing guides), and MUST complete before the pre-turn snapshot is taken.
(Previously: provisioned only the provider's definition)

#### Scenario: First provisioning

- GIVEN a project without definitions
- WHEN a turn starts for `claude`
- THEN only the `claude` definition is written, plus the shared guides
- AND provisioning completes before the pre-turn snapshot is taken

#### Scenario: Repeat provisioning

- GIVEN definitions are already provisioned
- WHEN provisioning runs again
- THEN no duplicates are created and content is unchanged

### Requirement: Definition change resets the conversation

When a provider's definition or isolation level changes, the next turn MUST start a new conversation and the chat MUST say so. Introducing the writing core and read exception counts as a definition change and MUST cause exactly one reset per provider.
(Previously: no statement about the guide change)

#### Scenario: Definition updated

- GIVEN an ongoing `claude` conversation and a changed definition
- WHEN the next turn starts
- THEN a new conversation begins and the chat states that the conversation was reset

#### Scenario: Single reset on upgrade

- GIVEN a conversation started with a definition lacking the guide core
- WHEN the upgraded definition is provisioned and two turns follow
- THEN the first turn resets once and states it
- AND the second turn continues that conversation without a reset

### Requirement: Removable

Provisioned files, including provisioned writing guides, MUST be removable without affecting other project files.
(Previously: covered definitions and the marked block only)

#### Scenario: Cleanup

- GIVEN provisioned files exist
- WHEN the user removes the marked block and definitions
- THEN the project returns to its prior state

#### Scenario: Cleanup with guides

- GIVEN definitions and unmodified guides are provisioned
- WHEN cleanup runs
- THEN the guides are removed and unrelated files are unchanged
