# Literature Search Specification

## Purpose

Connector roles and the agent/CLI split that finds and resolves sources, without a
skill or a validator ever knowing a connector's name. Search comes first, always;
what varies is the query, selected by the block's `citations` regime.

## Requirements

### Requirement: Connector Roles Are Configuration, Never Code

`papersmith.yaml` MUST map the roles `discovery`, `resolution`, and `full-text` to
ordered connector lists. Adding, removing, reordering, or replacing a connector MUST
be a configuration edit. Code MAY state what a connector can do (the identifier kinds
it resolves, whether it ever carries an abstract, whether it needs a key) and MUST NOT
choose which connector a role uses. A connector that needs a key MUST be skipped in
every role while its key is not configured, so that a role naming it behaves, without
the key, exactly as the same role without it. A connector that never carries an
abstract MUST be asked after every connector of the role that can.

#### Scenario: A role maps to a connector

- GIVEN `papersmith.yaml` declares a `resolution` role bound to OpenAlex
- WHEN the CLI resolves a citation
- THEN it uses the connector named by the `resolution` role, read from config

#### Scenario: A keyed connector without its key is skipped

- GIVEN `resolution` lists `asta, openalex, crossref, arxiv` and no Asta key is configured
- WHEN references are resolved
- THEN no request reaches Asta, and the request sequence equals that of the same role
  without `asta`

#### Scenario: The configured order decides who answers first

- GIVEN the same role and a configured Asta key
- WHEN a DOI is resolved with `--resolver auto` or `--references`
- THEN Asta is asked first, OpenAlex only when Asta has no abstract or cannot answer,
  and Crossref last

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

Resolution and metadata retrieval MUST run through the CLI, using only the Python
standard library's `urllib`, against Asta (Ai2's Semantic Scholar tools, reached over
MCP streamable HTTP), OpenAlex, Crossref, arXiv, and Semantic Scholar (Graph API,
keyless public shared pool), and MUST be keyless by default. OpenAlex (its `api_key`
parameter) and Asta (its `x-api-key` header) MAY carry the operator's optional
per-user key. A key MUST be read only from the environment (`OPENALEX_API_KEY`,
`ASTA_API_KEY`) or the per-user store `smith keys` and the dashboard write, never from
`papersmith.yaml`, a workspace file, or source code, and MUST NOT be written to any
cache, metadata blob, digest input, `refs.bib`, `references.json`, log, refusal
detail, or stdout. Where an endpoint accepts a polite-pool contact parameter
(OpenAlex's documented `mailto` parameter), the CLI's resolution requests MUST include
it, sourced from configuration, never hardcoded: `mailto` is a courtesy contact, not a
secret, and OpenAlex's own documentation states this convention. The CLI MAY call a
connector's identifier lookup and exact-title lookup only; it MUST NOT call an open
topic search or a snippet search (`search_papers_by_relevance`, `snippet_search`) and
MUST NOT read a model-generated field (`tldr`).

#### Scenario: Resolution call carries mailto

- GIVEN the CLI issues an OpenAlex resolution request
- WHEN the request is built
- THEN it includes a `mailto` query parameter sourced from configuration

#### Scenario: Resolution stays keyless by default

- GIVEN no key is configured
- WHEN the CLI resolves a citation
- THEN no request carries `api_key` or `x-api-key`, and the source holds no credential

#### Scenario: A configured OpenAlex key rides only OpenAlex calls

- GIVEN the operator configured an OpenAlex key
- WHEN the CLI resolves a DOI and later fetches a full-text PDF
- THEN the OpenAlex request carries the key, and the PDF fetch, the cached record, its
  digest, stdout, and every refusal detail do not

#### Scenario: The digest ignores the transport's framing

- GIVEN two Asta answers that differ only in the keep-alive pings around them
- WHEN each is resolved
- THEN both records carry the same `metadata_digest`, taken over the tool's own text

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
CLI exit code. A connector that rejects the operator's configured key MUST refuse
`RESOLVER_REFUSED` with a non-zero exit code, never `IDENTIFIER_UNRESOLVED`. Asking a
connector that needs a key it does not have MUST refuse `RESOLVER_ROLE_EMPTY` before
any request. In a chain (`--resolver auto`, `--references`), a refused or unreachable
connector is recorded and the next one is asked. None of them MUST return a silent
empty result. A `none`-regime block MUST remain writable with every connector
unreachable.

#### Scenario: A rejected key refuses by name, and the chain moves on

- GIVEN a configured key the service rejects
- WHEN one identifier is resolved through that connector
- THEN it refuses `RESOLVER_REFUSED`, naming no part of the key; in a chain the next
  connector answers instead, and a batch sets the connector aside for the rest of the run

#### Scenario: A stalled connector costs a bounded wait

- GIVEN a connector that answers only keep-alive pings
- WHEN it is asked for a record
- THEN the call gives up at its total deadline, not at the per-read timeout the pings
  keep resetting

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

#### Scenario: Snippet text never becomes evidence

- GIVEN Asta returns a snippet or a `tldr` for a paper
- WHEN that paper is cited
- THEN no snippet or `tldr` text is stored, quoted, or compared; quotes come only from
  a stored abstract or an ingested source

### Requirement: One Connector Writes Each Record

In a chain, the record kept MUST come whole from one connector: the first, in role
order, that returns an abstract, else the first that found the work. Fields MUST NOT
be merged across connectors; `resolver` and `metadata_digest` name that connector and
the bytes it returned. An abstract MUST be text its source printed: never stripped of
markup and never generated. A connector outside the `full-text` role reports
`full_text_url: null`.

#### Scenario: Asta has no abstract, OpenAlex does

- GIVEN Asta holds the work without an abstract and OpenAlex holds it with one
- WHEN the DOI is resolved through the chain
- THEN the record is OpenAlex's, whole, with `resolver: openalex`

#### Scenario: Asta has the abstract OpenAlex lacks

- GIVEN Asta holds the abstract and is asked first
- WHEN the DOI is resolved through the chain
- THEN the record carries `resolver: asta` and Asta's own abstract

#### Scenario: A generated summary is never an abstract

- GIVEN an Asta paper whose `abstract` is null and whose `tldr` is set
- WHEN it is resolved
- THEN its record's `abstract` is `null`

### Requirement: Asta's Use Is Acknowledged, Never Enforced

Ai2's terms ask that work done with the Asta Scientific Corpus Tool acknowledge it.
When a cited key's record was resolved through Asta, `verify`'s references check MUST
list it and add a note naming that acknowledgement; its verdict MUST NOT change.

#### Scenario: An Asta-resolved reference earns a note, not a failure

- GIVEN a cited key whose `references.json` record has `resolver: asta`
- WHEN `verify` runs its references check
- THEN the check lists the key with a note about acknowledging Ai2's Asta, and its
  verdict is what it would be without the note
