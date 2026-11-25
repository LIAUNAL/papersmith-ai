# Agent Definitions Specification

## Purpose

One agent definition per provider, specialized in academic paper writing, provisioned into the project.

## Requirements

### Requirement: One definition per provider

The system MUST ship exactly one `.md` agent definition for each of `opencode`, `claude`, `codex`, describing that provider's strengths and characteristics and specializing in academic paper writing.

#### Scenario: Definitions present

- GIVEN the product sources
- WHEN definitions are enumerated
- THEN there are three, one per provider, each with a provider-specific section

### Requirement: Behavioral prohibitions

Every definition MUST forbid fabricating citations and MUST forbid executing shell commands.

#### Scenario: Prohibitions stated

- GIVEN any definition
- WHEN its text is checked
- THEN it contains both prohibitions

### Requirement: Provisioning

The system MUST provision a provider's definition into the project in the location that provider reads, and MUST be idempotent. Provisioning MUST run when a turn starts for a provider, MUST write only that provider's definition, and MUST complete before the pre-turn snapshot is taken.

#### Scenario: First provisioning

- GIVEN a project without definitions
- WHEN a turn starts for `claude`
- THEN only the `claude` definition is written
- AND provisioning completes before the pre-turn snapshot is taken

#### Scenario: Repeat provisioning

- GIVEN definitions are already provisioned
- WHEN provisioning runs again
- THEN no duplicates are created and content is unchanged

### Requirement: User-modified definition

A native definition file that the user modified or authored MUST NOT be overwritten; the system MUST report it as skipped and MUST offer an explicit replace action.

#### Scenario: Modified file skipped

- GIVEN the user edited the provisioned `claude` definition
- WHEN a turn starts for `claude`
- THEN the file is left unchanged and reported as skipped

#### Scenario: Explicit replace

- GIVEN a definition was skipped
- WHEN the user chooses replace
- THEN the file is overwritten with the shipped definition

### Requirement: Definition change resets the conversation

When a provider's definition or isolation level changes, the next turn MUST start a new conversation and the chat MUST say so.

#### Scenario: Definition updated

- GIVEN an ongoing `claude` conversation and a changed definition
- WHEN the next turn starts
- THEN a new conversation begins and the chat states that the conversation was reset

### Requirement: Marked block preservation

A shared instructions file (`AGENTS.md`) MUST receive Caztor content only inside a marked block; content outside the block MUST be preserved byte for byte.

#### Scenario: Existing AGENTS.md

- GIVEN `AGENTS.md` has user content
- WHEN provisioning runs
- THEN the marked block is added and user content is unchanged

#### Scenario: Update block

- GIVEN a marked block exists with older text
- WHEN provisioning runs
- THEN only the block content is replaced

### Requirement: Removable

Provisioned files MUST be removable without affecting other project files.

#### Scenario: Cleanup

- GIVEN provisioned files exist
- WHEN the user removes the marked block and definitions
- THEN the project returns to its prior state
