# Agent Definitions Specification

## Purpose

One agent definition per provider, specialized in academic paper writing, provisioned into the project.

## Requirements

### Requirement: One definition per provider

The system MUST ship exactly one `.md` agent definition for each of `opencode`, `claude`, `codex`, `antigravity`, `pi`, describing that provider's strengths and characteristics and specializing in academic paper writing.
(Previously: four providers, without `pi`)

#### Scenario: Definitions present

- GIVEN the product sources
- WHEN definitions are enumerated
- THEN there are four, one per provider, each with a provider-specific section

### Requirement: Behavioral prohibitions

Every definition MUST forbid fabricating citations and MUST forbid executing shell commands.

#### Scenario: Prohibitions stated

- GIVEN any definition
- WHEN its text is checked
- THEN it contains both prohibitions

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
### Requirement: Writing guide core

The shared section of every definition MUST contain a compact advisory writing core that points to `.caztor/guides/INDEX.md`. The shared section MUST be byte-identical across all four definitions.
(Previously: byte-identical across three definitions)

#### Scenario: Identical core

- GIVEN the four definitions
- WHEN their shared sections are compared
- THEN they are byte-identical and include the core and the pointer

#### Scenario: Divergent section

- GIVEN one definition whose shared section differs by one byte
- WHEN the comparison runs
- THEN the check fails naming that definition

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

### Requirement: Antigravity definition

The Antigravity definition MUST be provisioned at `.agents/agents/caztor.md`, MUST restrict the agent to file read and file edit tools, and MUST apply the shared academic-writing section and guide pointer. Provisioning MUST follow the same idempotence, skip-if-modified and removal rules as the other definitions.

#### Scenario: Provisioned for Antigravity

- GIVEN a project without definitions
- WHEN a turn starts for Antigravity
- THEN only `.agents/agents/caztor.md` is written, plus the shared guides

#### Scenario: Tools restricted

- GIVEN the Antigravity definition
- WHEN its text is checked
- THEN it permits only file read and file edit tools and states that shell commands are forbidden

#### Scenario: User-modified file

- GIVEN the user edited `.agents/agents/caztor.md`
- WHEN a turn starts for Antigravity
- THEN the file is left unchanged and reported as skipped

### Requirement: Pi definition

Pi reads no agent files, so its definition MUST be plain Markdown, provisioned at `.caztor/agents/pi.md` and passed to Pi as its system prompt. It MUST name Pi's file tools, MUST apply the shared academic-writing section and guide pointer, and MUST tell the agent to leave the project's `.pi/` alone. Provisioning MUST follow the same idempotence, skip-if-modified and removal rules as the other definitions, and MUST never write into `.pi/`.

#### Scenario: Provisioned for Pi

- GIVEN a project without definitions
- WHEN a turn starts for Pi
- THEN only `.caztor/agents/pi.md` is written, plus the shared guides, and no `.pi/` folder appears
