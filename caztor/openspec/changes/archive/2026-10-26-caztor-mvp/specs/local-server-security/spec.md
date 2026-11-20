# Local Server Security Specification

## Purpose

Protecting the local server and the user's machine from other processes and web pages.

## Requirements

### Requirement: Loopback bind

The server MUST listen on loopback interfaces only.

#### Scenario: Non-loopback address

- GIVEN the server is running
- WHEN a connection is attempted via a non-loopback address
- THEN it is refused

### Requirement: Host and Origin allowlists

The server MUST reject requests whose Host header is not on a fixed allowlist, and requests carrying an Origin not on a fixed allowlist.

#### Scenario: Rebinding attempt

- GIVEN a request with Host `evil.example`
- WHEN received
- THEN it is rejected

#### Scenario: Foreign origin

- GIVEN a request with an Origin from another site
- WHEN received
- THEN it is rejected

State-changing requests MUST declare a JSON content type, except file upload which MUST declare a binary stream content type; cross-origin preflight requests MUST be refused.

#### Scenario: Wrong content type

- GIVEN a state-changing request declaring a form content type
- WHEN received
- THEN it is rejected

#### Scenario: Preflight

- GIVEN a cross-origin preflight request
- WHEN received
- THEN it is refused

### Requirement: Launch token

The server MUST generate a per-launch secret token and MUST require it on every API request, including read requests. In production the token MUST exist in memory only; a token supplied through the environment MUST be honored only in development mode.

#### Scenario: Missing token

- GIVEN any API request, including a read, without the token
- WHEN received
- THEN it is rejected and nothing changes

#### Scenario: Environment token in production

- GIVEN production mode and a token supplied through the environment
- WHEN the server starts
- THEN the supplied token is ignored and a new in-memory token is generated

#### Scenario: Environment token in development

- GIVEN development mode and a token supplied through the environment
- WHEN the server starts
- THEN that token is honored

#### Scenario: Token rotates

- GIVEN a token from a previous launch
- WHEN used after restart
- THEN it is rejected

### Requirement: Path containment

The file API MUST confine all paths to the project root.

#### Scenario: Escape attempt

- GIVEN a request path resolving outside the root
- WHEN received
- THEN it is rejected

### Requirement: No shell spawning

Child processes MUST be spawned without a shell, with arguments as discrete values.

#### Scenario: Injection attempt

- GIVEN user input containing shell metacharacters reaches a spawn
- WHEN the process starts
- THEN the input is not interpreted by a shell

### Requirement: Disclosed limits

The product SHOULD disclose to the user that compile and agent processes are not confined to the project for file reads. The notice MUST cover compile and agent processes, MUST state that content read by an agent is sent to the model provider, and MUST be acknowledged once per project.

#### Scenario: Disclosure

- GIVEN a project whose notice was not acknowledged
- WHEN the user opens it
- THEN a notice describes the limitation and the provider data flow

#### Scenario: Acknowledged once

- GIVEN the user acknowledged the notice for a project
- WHEN the project is opened again
- THEN the notice is not shown again
