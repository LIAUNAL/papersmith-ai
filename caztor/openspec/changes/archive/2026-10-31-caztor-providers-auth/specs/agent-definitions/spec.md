# Delta for Agent Definitions

## ADDED Requirements

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

## MODIFIED Requirements

### Requirement: One definition per provider

The system MUST ship exactly one `.md` agent definition for each of `opencode`, `claude`, `codex`, `antigravity`, describing that provider's strengths and characteristics and specializing in academic paper writing.
(Previously: three providers, without `antigravity`)

#### Scenario: Definitions present

- GIVEN the product sources
- WHEN definitions are enumerated
- THEN there are four, one per provider, each with a provider-specific section

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
