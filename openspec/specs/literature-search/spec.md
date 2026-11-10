# Literature Search Specification

## Purpose

Connector roles and the agent/CLI split that finds and resolves sources, without a
skill or a validator ever knowing a connector's name. Search comes first, always;
what varies is the query, selected by the block's `citations` regime.

## Requirements

### Requirement: Connector Roles Are Configuration, Never Code

`papersmith.yaml` MUST map the roles `discovery`, `resolution`, and `full-text` to
connectors. Adding, removing, or replacing a connector MUST be a configuration edit;
no skill script or validator MUST name a connector directly.

#### Scenario: A role maps to a connector

- GIVEN `papersmith.yaml` declares a `resolution` role bound to OpenAlex
- WHEN the CLI resolves a citation
- THEN it uses the connector named by the `resolution` role, read from config

### Requirement: Regime Selects the Query, Never the Skill

The query issued and the connector role invoked MUST be derived from the block's
declared `citations` regime (`discovery` | `resolution` | `none`). No section id,
block id, density number, or placement rule MUST appear in search or resolution code.

#### Scenario: Discovery issues an open search

- GIVEN a block with `citations: discovery`
- WHEN the search is invoked for a claim in that block
- THEN an open topic search runs against the `discovery` role's connectors

#### Scenario: Resolution issues a targeted lookup

- GIVEN a block with `citations: resolution`
- WHEN the search is invoked for a named object in that block
- THEN a targeted lookup by object name/identifier runs against the `resolution`
  role's connectors, never an open topic search

### Requirement: Discovery Runs Through the Agent's MCP

Discovery search MUST run through the agent's configured MCP servers (the operator's
`.mcp.json`), never through the CLI. A hallucinated discovery candidate is acceptable
input because it is re-checked at resolution.

#### Scenario: Discovery candidate reaches resolution

- GIVEN an MCP discovery call returns a candidate source
- WHEN the citation pipeline processes it
- THEN the candidate is passed to CLI-side resolution before any citation is accepted

### Requirement: Resolution Runs Through the CLI Over Stdlib `urllib`

Resolution and metadata retrieval MUST run through the CLI, keyless, using only the
Python standard library's `urllib`, against OpenAlex, Crossref, arXiv, and Semantic
Scholar (Graph API, keyless public shared pool). Where an endpoint accepts a
polite-pool contact parameter (OpenAlex's documented `mailto`
parameter), the CLI's resolution requests MUST include it, sourced from
configuration, never hardcoded — this keeps the "keyless" claim intact: `mailto` is
a courtesy contact, not a secret, and OpenAlex's own documentation states this
convention.

#### Scenario: Resolution call carries mailto

- GIVEN the CLI issues an OpenAlex resolution request
- WHEN the request is built
- THEN it includes a `mailto` query parameter sourced from configuration

#### Scenario: Resolution stays keyless

- GIVEN the CLI resolution path
- WHEN inspected for credentials
- THEN it holds no API key, token, or secret for any of the three connectors

### Requirement: The Fetcher Writes the Entry

The tool that fetched the resolved metadata bytes MUST be the same tool that writes
the `refs.bib` entry. No component may synthesize a `refs.bib` entry from data it did
not itself fetch over the network.

#### Scenario: CLI-fetched metadata becomes the entry

- GIVEN the CLI resolves a DOI and receives metadata bytes
- WHEN a `refs.bib` entry is written for that citation
- THEN the CLI that fetched those bytes is the writer of record

### Requirement: Unreachable Connectors Refuse By Name

An unreachable discovery connector MUST refuse `DISCOVERY_UNAVAILABLE`; an
unreachable resolution connector MUST refuse `RESOLVER_UNREACHABLE` with a non-zero
CLI exit code. Neither MUST return a silent empty result. A `none`-regime block MUST
remain writable with every connector unreachable.

#### Scenario: Resolver unreachable refuses by name

- GIVEN every resolution connector is unroutable
- WHEN the CLI attempts resolution for a citation
- THEN it refuses `RESOLVER_UNREACHABLE` and exits non-zero, writing no entry

#### Scenario: A none block is unaffected

- GIVEN every connector is unreachable
- WHEN a `citations: none` block is written
- THEN it is written successfully with no refusal

#### Scenario: The refusal guard is provably load-bearing

- GIVEN the `RESOLVER_UNREACHABLE` guard is disabled by mutation
- WHEN the corresponding refusal test runs
- THEN the test fails, proving the guard was reachable and enforced

### Requirement: Consensus Is Excluded From the Verdict Path

No connector that answers "does the literature support X" MUST participate in
citation validation. A verdict MUST be decided only against a stored verbatim span
from an ingested source.

#### Scenario: Consensus cannot supply a verdict

- GIVEN the Consensus connector is configured and reachable
- WHEN a citation is validated
- THEN the verdict is decided from a stored span, and no Consensus response
  contributes to `holds`/`does-not-hold`/`insufficient`
