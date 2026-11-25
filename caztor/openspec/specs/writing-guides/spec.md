# Writing Guides Specification

## Purpose

Advisory section-writing guidance for academic documents, distilled from Apache-2.0 sources, provisioned read-only into the project and obtained through a replaceable source.

## Requirements

### Requirement: Guide content

The system MUST provide ten per-section guides and an `INDEX.md`. Each guide MUST cover the section's function, sequence, extent, exclusions, cross-section coherence, citation and acronym conventions, and disqualifiers. No guide MAY contain pipeline-specific content from the origin (agents, stages, tooling or commands of the source project).

#### Scenario: Complete set

- GIVEN the built-in guide source
- WHEN its documents are listed
- THEN there are ten section guides, `INDEX.md` and a copy of the Apache-2.0 license text
- AND each section guide covers the listed topics

#### Scenario: Pipeline terms absent

- GIVEN any guide or `INDEX.md`
- WHEN its text is checked against the list of origin pipeline terms
- THEN no term is found

### Requirement: Advisory stance

Each guide MUST state that it is advisory, that the document's own structure and venue template take precedence, and that it applies to theses, reports and reviews as well as articles. Guides MUST NOT instruct the agent to assert content the user did not provide; such rules MUST defer to the citation-integrity prohibitions.

#### Scenario: Precedence stated

- GIVEN any guide
- WHEN its text is checked
- THEN it names document structure and venue template as taking precedence and names the non-article genres

#### Scenario: Conflicting template

- GIVEN a venue template whose section order differs from a guide
- WHEN the agent drafts that section
- THEN the template order is followed and the guide is used only for the remaining advice

### Requirement: Guide source port

Guides MUST be obtained through a guide-source port returning guide documents. A built-in source MUST be the default and the fallback. A different source MUST be substitutable without changing provisioning behavior.

#### Scenario: Default source

- GIVEN no other source is configured
- WHEN guides are provisioned
- THEN the built-in source supplies them

#### Scenario: Substituted source

- GIVEN a test source returning different documents
- WHEN guides are provisioned through it
- THEN those documents are written

#### Scenario: Source missing or unreadable

- GIVEN the configured source is absent, unreadable or returns an error
- WHEN guides are provisioned
- THEN the built-in source is used
- AND if the built-in source is also unreadable, the turn still starts and a readable error names the unavailable guides

### Requirement: Provisioning of guides

The system MUST provision the ten guides, `INDEX.md` and a copy of the Apache-2.0 license text (for example `LICENSE-papersmith-ai.txt`) into `.caztor/guides/` for every provider, idempotently, before the pre-turn snapshot. Written files MUST be tracked by content hash. They MUST be hidden from the file tree and rejected by file operations.

#### Scenario: First provisioning

- GIVEN a project without `.caztor/guides/`
- WHEN a turn starts for any provider
- THEN all twelve files (ten guides, `INDEX.md`, the license copy) exist there and are hash-tracked
- AND they do not appear in the tree

#### Scenario: Repeat provisioning

- GIVEN guides are provisioned and unchanged
- WHEN provisioning runs again
- THEN no file is rewritten

### Requirement: Tampered, deleted or user-authored guides

A tracked provisioned file (guide, `INDEX.md` or license copy) whose content no longer matches its tracked hash MUST be treated as user-modified and left untouched, reported as skipped, with an explicit replace action. A tracked file deleted from the project MUST be restored on the next provisioning. A file at a provisioned path that Caztor did not write MUST NOT be overwritten and MUST be reported as skipped.

#### Scenario: Tampered guide

- GIVEN a provisioned guide was edited
- WHEN provisioning runs
- THEN the file is unchanged and reported as skipped

#### Scenario: Tampered license copy

- GIVEN the provisioned license copy was edited
- WHEN provisioning runs
- THEN the file is unchanged and reported as skipped

#### Scenario: Deleted guide

- GIVEN a tracked guide file was deleted
- WHEN provisioning runs
- THEN the file is rewritten from the source

#### Scenario: User-authored file

- GIVEN a user file exists at a guide path with no tracking entry
- WHEN provisioning runs
- THEN the file is unchanged and reported as skipped

#### Scenario: Explicit replace

- GIVEN a guide was skipped
- WHEN the user chooses replace
- THEN it is overwritten from the source

### Requirement: Guide removal

Removal MUST delete only provisioned files (guides, `INDEX.md`, license copy) whose content still matches their tracked hash, and MUST leave modified or user-authored files.

#### Scenario: Clean removal

- GIVEN unmodified provisioned files including the license copy
- WHEN removal runs
- THEN all twelve are deleted and other project files are unaffected

#### Scenario: Modified guide kept

- GIVEN one guide was edited
- WHEN removal runs
- THEN that file remains

#### Scenario: Modified license copy kept

- GIVEN the license copy was edited
- WHEN removal runs
- THEN that file remains

### Requirement: Apache-2.0 attribution

The repository MUST include a copy of the Apache-2.0 license and a `NOTICE.md` entry naming the origin project and commit `1f09516`. Each distilled guide MUST carry a modification notice with the source path and commit. The project MUST receive the license text together with the derived guides, as part of the provisioned set.

#### Scenario: License travels with guides

- GIVEN guides are provisioned into a project
- WHEN `.caztor/guides/` is listed
- THEN it contains the Apache-2.0 license copy alongside the guides

#### Scenario: Attribution present

- GIVEN the built-in guides
- WHEN each is checked
- THEN it carries a notice with source path and commit
- AND the license copy and `NOTICE.md` entry exist

#### Scenario: Missing notice

- GIVEN a guide without a modification notice
- WHEN the attribution check runs
- THEN the check fails naming that guide
