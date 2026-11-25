# Local Server Security Specification

## Purpose

Protecting the local server and the user's machine from other processes and web pages.

## Requirements

### Requirement: Loopback bind

The server MUST listen on loopback interfaces only, unless the host starts it with an explicit `--host` address and at least one `--public-name`. Binding beyond loopback without a public name MUST be refused at start.

#### Scenario: Non-loopback address

- GIVEN the server is running without `--host`
- WHEN a connection is attempted via a non-loopback address
- THEN it is refused

#### Scenario: Exposed without a name

- GIVEN `--host 0.0.0.0` and no public name
- WHEN the server starts
- THEN it refuses to start with a message naming `--public-name`, and nothing is bound

### Requirement: Host and Origin allowlists

The server MUST reject requests whose Host header is not on a fixed allowlist, and requests carrying an Origin not on a fixed allowlist. The allowlists hold the loopback authority and the public names given at start (`http://` origins, or `https://` with `--secure`); they are never derived from a request.

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

### Requirement: Credential routes are write-only

Credential routes MUST accept a key only through a JSON body, MUST require the launch token like every other route, and MUST NOT return a key in any response. Responses MUST carry only set or not set and at most the last four characters. Keys MUST NOT appear in URLs, headers returned to the client, or server logs.

#### Scenario: Save and echo check

- GIVEN a valid token and a JSON body with a key
- WHEN the key is saved
- THEN the response contains no key and at most the last four characters

#### Scenario: Missing token

- GIVEN a credential request without the launch token
- WHEN received
- THEN it is rejected and the store is unchanged

#### Scenario: Wrong content type or foreign origin

- GIVEN a credential write declaring a form content type, or carrying a foreign Origin
- WHEN received
- THEN it is rejected and the store is unchanged

#### Scenario: Read-back route probing

- GIVEN a stored key
- WHEN any GET, error path or malformed request touches a credential route
- THEN no response body, header or log line contains the key

### Requirement: Collaborator sessions

A collaborator MUST sign in only with an invite the host creates, a link plus a random access key, and MUST NEVER receive the host's launch token. The link MUST hold no secret and MUST sign no one in by itself. The users store MUST live outside every project, MUST be readable by the owner only, and MUST hold only SHA-256 hashes of session secrets and access keys.

#### Scenario: Invite link plus access key

- GIVEN an invite the host created for a lifetime they chose, from 10 minutes to 365 days (7 days when none is given)
- WHEN its link (`/invite/<id>`, an id of at least 96 random bits) is fetched any number of times, by a browser or a preview bot
- THEN each answer is the same small sign-in form, with no script and no cookie, and the store is unchanged
- AND posting the right access key (at least 80 random bits, accepted with or without dashes and in either case) from an allowed `Origin`, as a form or as JSON, sets an HttpOnly, SameSite=Strict session cookie (`Secure` with `--secure` or https) and moves on to the app
- AND the same key signs in a second browser, until the invite expires
- AND a wrong key, an unknown link, an expired or locked invite, or a first-version one-time link gets the same 403 answer without a cookie and without saying why
- AND a lifetime outside 10 minutes to 365 days is refused with 400 (`invalid_lifetime`)

#### Scenario: Expiry ends the sessions

- GIVEN browsers signed in with an access key
- WHEN the key's expiry passes
- THEN the key is refused, and every session made with it is treated as having no session

#### Scenario: Invite lock

- GIVEN an invite
- WHEN 10 wrong keys are posted to its link
- THEN even the right key is refused, and the host's listing shows the invite as locked

#### Scenario: Revoke one access key

- GIVEN a collaborator with two access keys, a browser signed in with each
- WHEN the host revokes one key
- THEN the browser signed in with it is treated as having no session, and the other keeps working

#### Scenario: First-version store

- GIVEN a users store of the first version, with sessions and an unused one-time invite
- WHEN the server loads it
- THEN its sessions keep working until revoked, the one-time invite is refused and listed as "old invite, create a new one", and the file is written in the new format on the next change

#### Scenario: Page token per person

- GIVEN a browser with a collaborator's session cookie
- WHEN it loads the app page
- THEN the page carries that session's own token, not the launch token, and API requests pass only with the cookie and that token together

#### Scenario: No session on an exposed server

- GIVEN a server started with a public name
- WHEN a browser without a session loads the app page, even through loopback
- THEN it gets a page asking for an invite link and its access key, with no app and no token; the host signs in once with the host link printed at start

#### Scenario: Host-only management

- GIVEN a collaborator's session
- WHEN it calls `/api/users`, creates an invite, revokes someone, or trusts the project's CLI configuration
- THEN it is refused with 403 (`host_only`), while its own chat, providers, keys and sign-ins, files and compile keep working

#### Scenario: Revoke

- GIVEN a collaborator signed in on a browser
- WHEN the host revokes them
- THEN their next request and page load are treated as having no session

#### Scenario: Guessing

- GIVEN one remote address
- WHEN it posts more than 20 wrong access keys or used host links, or fails more than 20 cookie checks, in a minute
- THEN further failures are refused with 429 until the minute passes
- AND a valid session cookie, a valid access key or a valid host link from the same address still works

#### Scenario: Single-user answers unchanged

- GIVEN a server started without a public name
- WHEN the host calls `GET /api/session`
- THEN the answer has no `user` field, as before collaborators existed

#### Scenario: Compiles once collaborators can reach the server

- GIVEN a server started with a public name
- WHEN anyone, the host included, starts a compile
- THEN it runs in the bubblewrap sandbox whatever `sandboxedCompile` says, or is refused with `sandbox_required` and a readable message when the sandbox cannot be used
- AND only the host can change `sandboxedCompile`; a collaborator gets 403

#### Scenario: Collaborator turns run in bubblewrap

- GIVEN a collaborator's agent turn with any provider
- WHEN the runner starts the CLI
- THEN it runs inside bubblewrap with new namespaces except the network, a new session and `--die-with-parent`, the system tree and the CLI's install folder read-only, an empty tmpfs over the host's home, and only the project and the collaborator's private home (as `HOME`) writable
- AND no D-Bus socket, no `XDG_RUNTIME_DIR`, no other person's private folder and nothing else of Caztor's config folder is mounted
- AND when bwrap is missing or its `--version` probe of the CLI fails, the turn is refused with `isolation_failed` and never runs unsandboxed
- AND the host's turns run exactly as before, without bubblewrap

#### Scenario: The project's .caztor is hidden from a collaborator's turn

- GIVEN a project with the host's chat, state (trust records, sessions), snapshots and opencode configuration folder in `.caztor/`
- WHEN a collaborator's turn reads or writes there
- THEN `.caztor/` is an empty tmpfs: only `agents`, `guides` and `build` show, read-only, and `opencode-xdg`, `opencode-data-api`, `pi-sessions` and `pi-agent-api` are the collaborator's own folders from `<private home>/.caztor-turns/<project key>/`
- AND the project's existing `.claude/`, `.opencode/`, `.agents/`, `.mcp.json` and `opencode.json[c]` are read-only; a file it creates changes the fingerprint, so the host's next turn asks for confirmation again
- AND a CLI installed under a prefix in the host's home mounts only its package folder; a broad folder of the host's home is never mounted

#### Scenario: A link a turn leaves is never mounted from the host's side

- GIVEN a collaborator's turn left a link at `.claude`, `.opencode`, `.agents`, `.mcp.json` or `opencode.json[c]` (for example `.claude -> ../..`), a shared `.caztor/` folder is a link, or a link replaced one of their own turn folders
- WHEN the next collaborator turn or sign-in starts
- THEN every bind source taken from the project is checked again for that spec, never remembered: it and each folder above it up to the project must be no link, and its real path must stay inside the project
- AND a linked or missing configuration path or shared folder is not bound, so the link resolves only within the sandbox's own view (the project and the tmpfs), and a dangling one does not stop the turn
- AND a turn folder of the private home that is not a plain folder, or a `.caztor` that is a link, refuses the turn with `isolation_failed`

#### Scenario: The host's opencode configuration folder holds only opencode's own files

- GIVEN `.caztor/opencode-xdg` holds a configuration that can run programs, or any file opencode does not write there
- WHEN the host's opencode turn starts
- THEN the folder is emptied first, and opencode's own schema-only config, `.gitignore` and plugin package are kept otherwise

#### Scenario: A turn stays its owner's

- GIVEN a turn a collaborator ran, running or finished, before or after a restart
- WHEN anyone else, the host included, follows it, or undoes it
- THEN following answers 409 while it runs and 404 once it ended, with nothing of the turn, and undo answers `not_your_turn`
- AND `/api/chat/history` offers its undo only to its owner
- AND a project only the host uses writes nothing new and the host undoes as before
