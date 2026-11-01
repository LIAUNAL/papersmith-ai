# Coupling Verification Specification

## Purpose

Read-only classification of the five cross-section couplings (contribution
list, chain, the gap, diagram disjointness, future-work⊆limitations) against
declared block data (`paper/couplings.json`, this change's own read-only
declaration record — reconciled from an earlier "`paper-declarations`,
Phase 3" wording; see `Requirement: Declaration Record Presence Gates The
Run`) and the rendered bytes of `paper/main.tex`. Every coupling publishes
its own classification as a data field — never left to be inferred from
prose.

## Requirements

### Requirement: Verdict Vocabulary And Classification Field

Every coupling entry MUST carry `id`, `classification`
(`mechanical`|`assisted`|`out-of-reach`) and `verdict`
(`pass`|`fail`|`unmeasured`). `unmeasured` MUST NOT be folded into `pass`.

| # | Coupling | Classification |
|---|---|---|
| 1 | Contribution list identity | mechanical |
| 2 | Chain word identity | mechanical |
| 3 | The gap (intro 3 / related-work 4) | assisted |
| 4 | Diagram cell disjointness | mechanical |
| 5 | Future work ⊆ limitations | mechanical (totality, citation key) + out-of-reach (relevance, specificity) |

#### Scenario: Classification always present

- GIVEN any completed `verify` run
- WHEN the report is read
- THEN every coupling entry carries a `classification` field, never prose alone

### Requirement: Coupling 1 — Contribution List Identity

MUST compare the four declared ordered lists (intro 4b, methods slot 3,
abstract slot 4, conclusions block 1) for count, order and naming equality.

#### Scenario: M1 — reordered names fail

- GIVEN two of the four lists share names but differ in order
- WHEN coupling 1 runs
- THEN it reports `fail`

### Requirement: Coupling 2 — Chain Word Identity

MUST test literal string equality per chain link
(problem→contribution→property→instrument→evidence) and set closure over
declared problems/contributions/blocks. Identity, never synonymy, is the
contract's own test.

#### Scenario: M2 — synonym breaks identity

- GIVEN one chain link is replaced by a synonym that is not a substring of
  the original word
- WHEN coupling 2 runs
- THEN it reports `fail`

### Requirement: Coupling 3 — The Gap Is Assisted

Presence of both closings — the two blocks that `produces_facts` names as
`gap`'s corroborated producers (`fact-production`'s duplicate-producer
carve-out), resolved from the corpus's own producer declarations rather than
from every block that happens to name `gap` — and front-count/front-list
equality MUST be computed mechanically. "The same thing at different
depths" MUST NOT be computed; the payload MUST publish both closing texts
and both front lists verbatim, and the reading's own verdict MUST be
`unmeasured` until a human rules. `verify` MUST NOT answer or gate on that
reading (resolves proposal question 4: nobody closes it here).
(Previously: the pair was derived by scanning every block's `requires_facts`
for `gap`, which resolved to `rw-closing` and `experimental-setup.
es-assessment` — the wrong second block, since `es-assessment` names `gap`
for an unrelated reason and `introduction.block-3`, the design's intended
counterpart, did not name `gap` at all until this change.)

#### Scenario: Assisted payload published

- GIVEN both blocks exist with declared fronts
- WHEN coupling 3 runs
- THEN mechanical sub-checks report `pass`/`fail`, the depth-reading
  sub-check reports `unmeasured`, and both full texts appear in the payload

#### Scenario: Pairing resolves to the two corroborated producers of gap

- GIVEN `gap` produced by both `related-work.rw-closing` and
  `introduction.block-3` (the corroborated pair `fact-production`'s
  duplicate-producer carve-out allows), with
  `experimental-setup.es-assessment` separately naming `gap` in its own
  `requires_facts` for an unrelated purpose
- WHEN coupling 3 runs
- THEN the pair it evaluates is (`rw-closing`, `introduction.block-3`), and
  `es-assessment` is not treated as the coupling's counterpart

#### Scenario: Mutation — reverting to consumer-scan pairing is caught

- GIVEN the pairing derivation mutated to select its counterpart by
  scanning every `requires_facts` consumer of `gap`, rather than the fact's
  two declared producers
- WHEN the pairing test runs against the fixture where `es-assessment` also
  names `gap`
- THEN it fails, since the mutated derivation would select `es-assessment`
  as the counterpart instead of `introduction.block-3`
### Requirement: Coupling 4 — Diagram Cell Disjointness

Results-artefact cells MUST be found among declared setup-diagram cells.
The methods-diagram side is derived from coupling 1's contribution list,
never separately declared. A cell shared between setup and the derived
methods side is a failure.

#### Scenario: M4a — undeclared cell fails

- GIVEN a results artefact naming a cell absent from the declared setup
  diagram
- WHEN coupling 4 runs
- THEN it reports `fail`

#### Scenario: M4b — a shared box fails

- GIVEN a contribution name is added to the setup diagram's own cells
- WHEN coupling 4 runs
- THEN it reports `fail` for non-empty intersection with the derived methods
  side

### Requirement: Coupling 5 — Future Work ⊆ Limitations

Direction→limitation totality and the shared citation key (contract 04,
movement 5) MUST be computed and classified mechanical. "Relevant subset"
and "specific enough to be a paper" MUST be classified `out-of-reach` and
reported `unmeasured` — never attempted.

#### Scenario: M5 — an unanswered direction fails

- GIVEN a future-work direction answering no declared limitation
- WHEN coupling 5 runs
- THEN the totality sub-check reports `fail`

### Requirement: Declared-Name Literal Presence Limit

A check comparing declared names MUST also verify the name occurs literally
in its own block's rendered bytes. That presence check proves the words are
there, never that the block enumerates them completely or in order — the
payload MUST state this limit alongside any `pass` verdict that depends on it.

#### Scenario: Declared name absent from bytes

- GIVEN a declared contribution name that never appears in its block's text
- WHEN the presence check runs
- THEN it reports `fail`, distinct from a cross-list mismatch

### Requirement: Declaration Record Presence Gates The Run

An entirely absent or empty `paper/couplings.json` declaration record MUST
refuse `DECLARATION_RECORD_ABSENT` for the whole run — never reported as
clean, never as `unmeasured` per coupling. A present record with one block
carrying no per-block declaration entry (hand-written or `--adopt`ed,
resolves proposal question 2) MUST report `unmeasured` only for the
couplings that depend on that block, and MUST NOT refuse the run.

**Reconciled from this requirement's earlier `%% paper-writing
declarations` region wording** (`sdd-apply`, `the-couplings-hold-or-they-
do-not`): design.md's own decision reads the declaration record from
`paper/couplings.json`, read-only, never from the `declarations` region
`paper_declarations.py` already owns for a different, unrelated vocabulary
(the seven operator-supplied declarations and ten fact resolutions,
`the-paper-carries-its-own-decisions`) — that region's own payload shape
was never fixed for per-block coupling data, and reading it here would
define another change's record from downstream. `paper/couplings.json` is
untracked, like `main.tex` itself, and this change reads it without ever
writing it.

#### Scenario: M6 — empty declaration record refuses

- GIVEN `paper/couplings.json` is absent, empty, or carries no declared
  blocks
- WHEN `verify` runs
- THEN it refuses `DECLARATION_RECORD_ABSENT`, writes nothing, exits non-zero

#### Scenario: An undeclared block reports unmeasured, not pass

- GIVEN `paper/couplings.json` exists but one block has no entry
- WHEN a coupling reading that block's declared data runs
- THEN it reports `unmeasured` for that coupling only

### Requirement: Fixture-Backed Reachability

Since no landed phase writes a per-block declaration record yet, this
capability's own fixtures MUST include a fully-declared synthetic
`paper/main.tex` sufficient to drive every coupling to both a reachable-red
and a reachable-green outcome, executed by the test suite today.

#### Scenario: Fixture proves both directions

- GIVEN the fully-declared synthetic fixture
- WHEN the suite runs it unmutated, then once per named mutation (M1, M2,
  M4, M5, M6)
- THEN the unmutated run reports `pass` on every mechanical coupling, and
  each mutation flips its own coupling to `fail` or the whole run to refuse
