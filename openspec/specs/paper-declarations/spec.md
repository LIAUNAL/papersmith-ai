# Paper Declarations Specification

## Purpose

`main.tex` carries a `declarations` region holding two record kinds —
operator-supplied declarations and fact resolutions — collected
progressively, fixed once recorded, and reopened only by name. Neither
record kind ever widens the other's closed vocabulary, both of which
Phase 2 (`section-contract`) already fixes: seven declaration ids
(`author-roles`, `grant-title`, `grant-code`, `repository-url`,
`keyword-bounds`, `classification-line`, `ethics-approval`) and ten fact ids (`formulation`,
`contributions`, `problem-statement`, `gap`, `dataset`,
`experimental-design`, `implementation`, `results`, `limitations`,
`skeleton`).

## Requirements

### Requirement: Declarations Region Grammar

A single `declarations` region MUST exist as `%% paper-writing declarations
begin sha256=<hex>` … `%% paper-writing declarations end`, with `<hex>` a
digest over the region's own body, recomputed and checked before every
write. A mismatch MUST refuse `DECLARATIONS_HAND_EDITED` (work-state) and
MUST NOT overwrite the region.

#### Scenario: A hand-edited region refuses

- GIVEN a `declarations` region whose body was edited outside `declare`
- WHEN `declare` writes to it
- THEN it refuses `DECLARATIONS_HAND_EDITED` and writes nothing

### Requirement: Invisible to Phase 1's Block Scanner

The `declarations` region's marker lines MUST NOT start with Phase 1's
exact block prefix, `b"%% paper-writing block"` (`paper_block.py:56`,
`MARKER_PREFIX`). A test in this skill's mutation-proof convention
(the `MutationProofTests` shape already used by `tests/test_paper_writing.py`)
MUST assert the two prefixes are disjoint by construction, and MUST fail
red if `MARKER_PREFIX` is narrowed or widened to overlap the declarations
prefix. This is load-bearing: Phase 1's scanner skipping every non-matching
line is the entire mechanism that keeps a `declarations` region readable as
prose by Phase 1 rather than as a malformed block.

#### Scenario: Phase 1's status sees no block in a declarations-only file

- GIVEN a `main.tex` holding only a well-formed `declarations` region and
  no `%% paper-writing block` markers
- WHEN Phase 1's `status` runs
- THEN it reports zero blocks and refuses nothing

#### Scenario: Narrowing the block prefix is caught

- GIVEN `MARKER_PREFIX` mutated to a substring of the declarations prefix
- WHEN the disjointness test runs
- THEN it fails red

### Requirement: Two Record Kinds, Each Vocabulary Closed to the Other

The `declarations` region holds `declaration` records (ids from the six
operator-input vocabulary) and `fact-resolution` records (ids from the ten
fact vocabulary). `declare` MUST refuse `NOT_A_DECLARATION` (invocation-
defect) when asked to record a fact id as a `declaration`, and MUST refuse
`NOT_A_FACT` (invocation-defect) when asked to record a declaration id as a
`fact-resolution`. `contributions` MUST always be recorded as fact 2 of
ten, never as a seventh declaration.

#### Scenario: contributions is a fact, not a declaration

- GIVEN `declare` is invoked recording `contributions` as a `declaration`
- WHEN it runs
- THEN it refuses `NOT_A_DECLARATION` naming `contributions`

#### Scenario: Mutation 6 — the closed vocabulary stays closed

- GIVEN the validator behind `requires_declarations` is mutated to also
  accept `contributions` (a fact-resolution id)
- WHEN the vocabulary-boundary test runs
- THEN it fails red — the mutation must be executed against the real
  validator, not merely asserted against a fixture the test itself wrote

### Requirement: Progressive Filling, Fixing, and Explicit Reopening

Every record starts `unfilled`. `declare` sets its value once, which fixes
it immediately: a further `declare` call naming the same id without
`--reopen` MUST refuse `DECLARATION_FIXED` (work-state), naming the id and
its current value. `--reopen <id>` MUST clear the fixed state for exactly
that id and no other.

#### Scenario: A fixed entry refuses a plain overwrite

- GIVEN `author-roles` was already declared
- WHEN `declare` is called again on `author-roles` without `--reopen`
- THEN it refuses `DECLARATION_FIXED`

#### Scenario: Reopen admits a new value

- GIVEN `author-roles` is fixed
- WHEN `--reopen author-roles` runs, then `declare` sets a new value
- THEN the new value is recorded and the region's digest updates

### Requirement: Reopening Invalidates Exactly the Blocks That Named It

`--reopen <id>` MUST derive the affected block set by scanning every
section contract's parsed `blocks` (Phase 2's `ContractHeader.blocks`) for
entries whose `requires_facts` or `requires_declarations` contains `<id>`,
and MUST mark stale, in the `provenance` region, exactly that set. A block
whose contract does not name `<id>` MUST be left untouched.

#### Scenario: Reopen narrows to the naming blocks

- GIVEN three written blocks, two of which declare `requires_declarations:
  [repository-url]` and one of which does not
- WHEN `--reopen repository-url` runs
- THEN the two naming blocks are marked stale and the third is unchanged

#### Scenario: Mutation 5 — over-invalidation is caught

- GIVEN `--reopen`'s scope computation is mutated to mark every written
  block stale regardless of its contract
- WHEN the over-invalidation guard test runs
- THEN it fails red

### Requirement: insumos-observer Reports Fact Satisfaction, Decides Nothing

The `insumos-observer` agent MUST read its four declared input sources and
report, for each of the ten facts, whether it is satisfied. It MUST NOT
write to the `declarations` region, MUST NOT call `declare`, and MUST NOT
recommend or select a value. This is a checkable property: an executed
run of the agent against a fixture repository MUST leave the
`declarations` region's digest unchanged.

#### Scenario: An observation run changes nothing on disk

- GIVEN a repository with an existing `declarations` region
- WHEN `insumos-observer` runs and reports fact satisfaction
- THEN the `declarations` region's body and digest are byte-identical
  before and after the run

### Requirement: declare Is Registered Into paper_cli.py

`declare` MUST be added as a subcommand of the existing `paper_cli.py`
dispatch, returning the same `{"status": "ok", ...}` /
`{"status": "refused", "code": ..., "detail": ...}` JSON shape every other
verb returns. Every refusal code it can raise MUST appear in
`paper_cli.REFUSAL_CLASSIFICATION`, classified `invocation-defect` or
`work-state`, held to the same roster-derivation test
(`reachable_paper_refusal_codes`) that already governs the four existing
verbs in both directions.

#### Scenario: A new declare refusal is classified

- GIVEN `declare` raises `DECLARATION_FIXED`
- WHEN the roster-derivation test runs
- THEN `DECLARATION_FIXED` is present in `REFUSAL_CLASSIFICATION` and
  classified `work-state`

### Requirement: The Declarations Region Is The Single Source Any Reader Consults

Any reader that reports satisfied facts or declarations for a `paper_dir` —
including `readiness` (`writing-readiness`) — MUST derive that state by
parsing this same `declarations` region, never from a separately memorized
or separately persisted copy. A fact whose producer is a block
(`fact-production`) is excluded from this region entirely: its satisfaction
is derived from that producer block's own written status, and this region
never holds — and is never consulted for — a resolution of it.
(Previously: every fact's satisfied state, produced or not, was read from
this region alone, with no carve-out for a fact a block produces.)

#### Scenario: A second reader reads the same region, not a copy

- GIVEN a `declarations` region recording `formulation` as satisfied
- WHEN two independent verbs (`declare --reopen`'s report and `readiness`)
  each need to know whether `formulation` is satisfied
- THEN both derive the same answer from parsing this one region, and
  neither reads a separate cache

#### Scenario: A produced fact's satisfaction bypasses this region

- GIVEN a `declarations` region holding no entry for `gap`, and
  `related-work.rw-closing` (gap's producer) already written
- WHEN a reader asks whether `gap` is satisfied
- THEN it answers satisfied from `rw-closing`'s written status, never by
  finding — or failing to find — an entry for `gap` in this region
### Requirement: Skeleton Presence Is Read From Opened Block Ids, Never From A Declaration Record

The two skeleton-startup decisions (`skeleton-startup`) are inferred from
`main.tex`'s opened block ids, not recorded as a `declaration` or
`fact-resolution` in this region. A `declare` call attempting to record
either decision under a declaration or fact id MUST refuse — neither
decision is a member of the six-declaration or ten-fact closed vocabularies
this spec already fixes.

#### Scenario: The skeleton decisions are not declarable

- GIVEN an attempt to `declare` "related-work-present" as a declaration id
- WHEN `declare` validates the id
- THEN it refuses `UNKNOWN_DECLARATION`, because the skeleton decision is
  read from disk, never recorded in this region
### Requirement: declare Refuses A Produced Fact

`declare` MUST refuse `PRODUCED_FACT_UNDECLARABLE` (work-state) when asked to
record a `fact-resolution` for a fact id that has a producing block
(`fact-production`), naming the fact id and its producing block. Only a fact
resolving to an external source (`FACT_SOURCE_ROOT`) may be recorded through
this region; a produced fact's satisfaction is read from its producer's own
written status, never authored twice.

#### Scenario: Declaring a produced fact refuses

- GIVEN `gap` classified PRODUCED, with `related-work.rw-closing` as its
  producer
- WHEN `declare --fact gap --value ...` is invoked
- THEN it refuses `PRODUCED_FACT_UNDECLARABLE` naming `gap` and
  `related-work.rw-closing`

#### Scenario: Declaring an external fact is unaffected

- GIVEN `formulation`, resolved from `FACT_SOURCE_ROOT`, with no producing
  block
- WHEN `declare --fact formulation --value ...` is invoked
- THEN it records the fact resolution as before, with no refusal

## Acceptance Criteria

- A second session resumes by reading a `declarations` region rather than
  re-asking any of its recorded values.
- Recording a fact resolution never admits a seventh declaration id, and
  recording a declaration never admits a fact id — proven by an executed
  mutation of the validator (Mutation 6), not asserted in prose.
- A fixed entry refuses overwrite; `--reopen` narrows to exactly the naming
  blocks, proven by an executed over-invalidation mutation (Mutation 5).
- The declarations/provenance marker prefix and Phase 1's block prefix are
  proven disjoint by an executed narrowing mutation (Mutation 1), not by
  static inspection alone.
- `insumos-observer` is proven, not merely documented, to leave the
  declarations region unchanged after a run.
