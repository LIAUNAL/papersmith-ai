# Delta for Turn Snapshots

## MODIFIED Requirements

### Requirement: Snapshot scope and retention

Snapshots MUST exclude internal state, `.git/`, `node_modules/`, provisioned agent directories, provisioned writing guides under `.caztor/guides/`, and large binary build artifacts, MUST be stored under `.caztor/`, and SHOULD retain the last 20 turns.
(Previously: provisioned writing guides were not named in the exclusions)

#### Scenario: Retention

- GIVEN 20 retained turns
- WHEN a new snapshot is taken
- THEN the oldest is discarded and its undo is shown as unavailable

#### Scenario: Excluded paths

- GIVEN `node_modules/` and `.git/` exist
- WHEN a snapshot is taken
- THEN neither is included

#### Scenario: Guides excluded

- GIVEN provisioned guides exist under `.caztor/guides/`
- WHEN a snapshot is taken
- THEN no guide file is included
- AND a guide rewritten by provisioning never appears in a changed-files list or an undo
